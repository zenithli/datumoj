import {DEFAULT_POLICY, deriveView, validateReceipt} from './model.js';

const MAX_RESPONSE_BYTES = 65536;
class PollError extends Error {}
const fail = code => { throw new PollError(code); };

async function readJSON(response) {
  if (!response?.ok || response.redirected) fail('E_HTTP');
  const declared = response.headers?.get('content-length');
  if (declared !== null && declared !== undefined && Number(declared) > MAX_RESPONSE_BYTES) fail('E_RESPONSE_SIZE');
  let text;
  if (response.body?.getReader) {
    const reader = response.body.getReader();
    const chunks = [];
    let length = 0;
    try {
      for (;;) {
        const {done, value} = await reader.read();
        if (done) break;
        length += value.byteLength;
        if (length > MAX_RESPONSE_BYTES) fail('E_RESPONSE_SIZE');
        chunks.push(value);
      }
      const bytes = new Uint8Array(length);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      try { text = new TextDecoder('utf-8', {fatal: true}).decode(bytes); } catch { fail('E_JSON'); }
    } catch (error) {
      try { await reader.cancel(); } catch { /* Preserve the original safe error. */ }
      throw error;
    } finally { reader.releaseLock?.(); }
  } else {
    text = await response.text();
    if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) fail('E_RESPONSE_SIZE');
  }
  let value;
  try { value = JSON.parse(text); } catch { fail('E_JSON'); }
  try { return validateReceipt(value); } catch { fail('E_RECEIPT'); }
}

// Partial order across generated_at AND all four observed_at axes. A missing
// timestamp cannot establish ordering. Mixed directions are incomparable.
function receiptOrder(previous, next) {
  if (!previous) return 'accept';
  const left = [previous.generated_at, ...Object.values(previous.nas).map(item => item.observed_at)];
  const right = [next.generated_at, ...Object.keys(previous.nas).map(key => next.nas[key].observed_at)];
  let newer = false, older = false;
  for (let index = 0; index < left.length; index++) {
    if (left[index] === right[index]) continue;
    if (left[index] === null || right[index] === null) return 'unordered';
    if (right[index] > left[index]) newer = true;
    else older = true;
  }
  if (older && newer) return 'unordered';
  if (older) return 'older';
  if (!newer && !sameEvidence(previous, next)) return 'unordered';
  return 'accept';
}
function sameEvidence(a, b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.hasOwn(b, key) && sameEvidence(a[key], b[key]));
}

export function createPoller({
  fetch: fetchReceipt = (...args) => globalThis.fetch(...args),
  setTimeout: later = (callback, delay) => globalThis.setTimeout(callback, delay),
  clearTimeout: cancel = id => globalThis.clearTimeout(id),
  now = () => Date.now(), render,
  policy = DEFAULT_POLICY, intervalMs = 60000, timeoutMs = 10000,
} = {}) {
  if (![fetchReceipt, later, cancel, now, render].every(value => typeof value === 'function')
    || !Number.isFinite(intervalMs) || intervalMs <= 0
    || !Number.isFinite(timeoutMs) || timeoutMs <= 0) fail('E_CONFIG');
  let running = false, autoRefresh = true, epoch = 0, tickTimer = null, inFlight = null;
  let receipt = null, transportState = 'error', lastError = null, warning = null, lastSuccessfulReadAt = null;

  function emit() {
    render(deriveView(receipt, now(), policy, transportState), {
      loading: inFlight !== null, autoRefresh, lastError, warning, lastSuccessfulReadAt,
    });
  }
  function schedule() {
    tickTimer = later(() => {
      tickTimer = null;
      if (!running) return;
      emit(); // Ages evidence even when auto-fetch is off or a request is pending.
      if (autoRefresh) refresh();
      schedule();
    }, intervalMs);
  }
  function refresh() {
    if (!running) return Promise.resolve();
    if (inFlight) return inFlight.promise;
    const token = {epoch, abort: new AbortController(), timer: null, promise: null, cancelRequest: null};
    inFlight = token;
    const deadline = new Promise((_, reject) => {
      token.cancelRequest = () => reject(new PollError('E_STOPPED'));
      token.timer = later(() => {
        reject(new PollError('E_TIMEOUT'));
        token.abort.abort();
      }, timeoutMs);
    });
    const work = Promise.resolve().then(() => {
      if (!running || epoch !== token.epoch || inFlight !== token) fail('E_STOPPED');
      return fetchReceipt('./status.json', {
        method: 'GET', cache: 'no-store', credentials: 'same-origin', redirect: 'error', signal: token.abort.signal,
      });
    }).then(readJSON);
    token.promise = Promise.race([work, deadline]).then(next => {
      if (!running || epoch !== token.epoch || inFlight !== token) return;
      const order = receiptOrder(receipt, next);
      if (order !== 'accept') {
        transportState = 'unordered'; lastError = null;
        warning = order === 'older' ? 'E_OLDER_RECEIPT' : 'E_UNORDERED_RECEIPT';
      } else {
        receipt = next; transportState = 'ok'; lastError = null; warning = null;
        const readAt = now();
        const date = typeof readAt === 'number' && Number.isFinite(readAt) ? new Date(readAt) : null;
        lastSuccessfulReadAt = date && date.getUTCFullYear() >= 1 && date.getUTCFullYear() <= 9999
          ? `${date.toISOString().slice(0, 19)}Z` : null;
      }
    }).catch(error => {
      if (!running || epoch !== token.epoch || inFlight !== token) return;
      transportState = 'error'; warning = null;
      lastError = error instanceof PollError ? error.message : 'E_FETCH';
    }).finally(() => {
      cancel(token.timer);
      if (!running || epoch !== token.epoch || inFlight !== token) return;
      inFlight = null;
      emit();
    });
    emit();
    return token.promise;
  }
  function start() {
    if (running) return;
    running = true; epoch++;
    emit(); refresh(); schedule();
  }
  function stop() {
    if (!running) return;
    running = false; epoch++;
    if (tickTimer !== null) cancel(tickTimer);
    tickTimer = null;
    if (inFlight) {
      cancel(inFlight.timer);
      inFlight.cancelRequest();
      inFlight.abort.abort();
      inFlight = null;
    }
  }
  function setAutoRefresh(enabled) {
    if (typeof enabled !== 'boolean') fail('E_CONFIG');
    autoRefresh = enabled;
    if (running) emit();
  }
  function visibilityReturn() {
    if (!running) return;
    emit();
    if (autoRefresh) return refresh();
  }
  function getState() {
    return {running, loading: inFlight !== null, autoRefresh, transportState, lastError, warning, lastSuccessfulReadAt,
      receipt: receipt === null ? null : JSON.parse(JSON.stringify(receipt))};
  }
  return {start, stop, refresh, setAutoRefresh, visibilityReturn, getState};
}
