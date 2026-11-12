// Browser validates parsed objects. Duplicate text keys are rejected by the builder,
// not by JSON.parse. Only builder-canonical, synthetic receipts are supported.
const OBJECT_KEYS = Object.freeze({
  receipt: ['schema_version', 'data_mode', 'generated_at', 'nas'],
  nas: ['last_attempt', 'inventory_check', 'content_check', 'restore_check'],
  last_attempt: ['observed_at', 'started_at', 'completed_at', 'result', 'error_count'],
  inventory_check: ['observed_at', 'scope', 'checked_objects', 'missing_objects', 'size_mismatches'],
  content_check: ['observed_at', 'scope', 'checked_objects', 'hash_mismatches'],
  restore_check: ['observed_at', 'scope', 'result', 'checked_objects'],
});
const AGE_KEYS = Object.freeze({
  last_attempt: 'lastAttemptMaxAgeMs', inventory_check: 'inventoryMaxAgeMs',
  content_check: 'contentMaxAgeMs', restore_check: 'restoreMaxAgeMs',
});
export const DEFAULT_POLICY = Object.freeze({
  lastAttemptMaxAgeMs: null, inventoryMaxAgeMs: null,
  contentMaxAgeMs: null, restoreMaxAgeMs: null, futureSkewMs: 300000,
});
const fail = code => { throw new Error(code); };

function exactObject(value, keys) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) fail('E_OBJECT');
  const actual = Reflect.ownKeys(value);
  if (actual.length !== keys.length || actual.some(key => !keys.includes(key))) fail('E_FIELDS');
  if (actual.some(key => !Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), 'value'))) fail('E_OBJECT');
}
function timestamp(value, nullable = true) {
  if (value === null && nullable) return null;
  if (typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(value)
    || value.startsWith('0000')) fail('E_TIME');
  const ms = Date.parse(value);
  if (!Number.isFinite(ms) || new Date(ms).toISOString().replace('.000Z', 'Z') !== value) fail('E_TIME');
  return ms;
}
function count(value) {
  if (value !== null && (!Number.isSafeInteger(value) || value < 0)) fail('E_COUNT');
}
function enumeration(value, choices) {
  if (!choices.includes(value)) fail('E_ENUM');
}
function boundedMismatches(item, keys) {
  if (item.checked_objects !== null && keys.some(key => item[key] !== null && item[key] > item.checked_objects)) fail('E_RELATION');
}

function validateParsedReceipt(value) {
  exactObject(value, OBJECT_KEYS.receipt);
  if (value.schema_version !== 1) fail('E_SCHEMA');
  if (value.data_mode !== 'synthetic') fail('E_MODE');
  const generated = timestamp(value.generated_at, false);
  exactObject(value.nas, OBJECT_KEYS.nas);
  for (const key of OBJECT_KEYS.nas) {
    const item = value.nas[key];
    exactObject(item, OBJECT_KEYS[key]);
    const observed = timestamp(item.observed_at);
    if (observed !== null && observed > generated) fail('E_RELATION');
  }
  const job = value.nas.last_attempt;
  enumeration(job.result, ['unknown', 'running', 'success', 'failed']);
  count(job.error_count);
  const start = timestamp(job.started_at);
  const completed = timestamp(job.completed_at);
  const observed = timestamp(job.observed_at);
  if ((start !== null && start > generated) || (completed !== null && completed > generated)
    || (start !== null && completed !== null && start > completed)
    || (observed !== null && completed !== null && observed < completed)) fail('E_RELATION');
  const inventory = value.nas.inventory_check;
  enumeration(inventory.scope, ['unknown', 'reported_snapshot']);
  for (const key of ['checked_objects', 'missing_objects', 'size_mismatches']) count(inventory[key]);
  boundedMismatches(inventory, ['missing_objects', 'size_mismatches']);
  const content = value.nas.content_check;
  enumeration(content.scope, ['unknown', 'sample', 'all_in_snapshot']);
  count(content.checked_objects); count(content.hash_mismatches);
  boundedMismatches(content, ['hash_mismatches']);
  const restore = value.nas.restore_check;
  enumeration(restore.scope, ['unknown', 'sample']);
  enumeration(restore.result, ['unknown', 'passed', 'failed']);
  count(restore.checked_objects);
  return value;
}

const VALIDATION_CODES = new Set(['E_OBJECT', 'E_FIELDS', 'E_SCHEMA', 'E_MODE', 'E_TIME', 'E_COUNT', 'E_ENUM', 'E_RELATION']);
export function validateReceipt(value) {
  try { return validateParsedReceipt(value); }
  catch (error) {
    fail(VALIDATION_CODES.has(error?.message) ? error.message : 'E_OBJECT');
  }
}

function validPolicy(policy) {
  try {
    exactObject(policy, [...Object.values(AGE_KEYS), 'futureSkewMs']);
    return Object.values(AGE_KEYS).every(key => policy[key] === null
      || (Number.isFinite(policy[key]) && policy[key] >= 0))
      && policy.futureSkewMs === 300000;
  } catch { return false; }
}
function semanticStatus(key, item) {
  if (key === 'last_attempt') {
    if (item.result === 'failed' || item.result === 'running') return item.result;
    return item.result === 'success' && item.completed_at !== null ? 'job_completed' : 'unknown';
  }
  if (item.scope === 'unknown') return 'unknown';
  if (key === 'inventory_check') {
    if (item.missing_objects > 0 || item.size_mismatches > 0) return 'differences';
    return item.checked_objects > 0 && item.missing_objects === 0 && item.size_mismatches === 0
      ? 'matched_snapshot' : 'unknown';
  }
  if (key === 'content_check') {
    if (item.hash_mismatches > 0) return 'failed';
    if (!(item.checked_objects > 0) || item.hash_mismatches !== 0) return 'unknown';
    return item.scope === 'sample' ? 'matched_sample' : 'matched_snapshot';
  }
  if (item.result === 'failed') return 'failed';
  return item.result === 'passed' && item.checked_objects > 0 ? 'passed_sample' : 'unknown';
}

export function deriveView(receipt, nowMs, policy, transportState = 'ok') {
  let loadError = null;
  try { validateReceipt(receipt); } catch (error) { loadError = error.message; }
  const clockValid = typeof nowMs === 'number' && Number.isFinite(nowMs)
    && Math.abs(nowMs) <= 8640000000000000;
  const policyValid = validPolicy(policy);
  const items = {};
  for (const key of OBJECT_KEYS.nas) {
    const historical = loadError ? null : {...receipt.nas[key]};
    const observedAt = historical?.observed_at ?? null;
    const ageMs = observedAt !== null && clockValid ? nowMs - Date.parse(observedAt) : null;
    let reason = null;
    if (loadError) reason = 'invalid_receipt';
    else if (transportState !== 'ok') reason = transportState === 'unordered' ? 'chronology_warning' : 'transport_error';
    else if (!clockValid) reason = 'clock_invalid';
    else if (!policyValid) reason = 'policy_invalid';
    else if (observedAt === null) reason = 'missing_observed_at';
    else if (ageMs < -policy.futureSkewMs) reason = 'future_observation';
    else if (policy[AGE_KEYS[key]] === null) reason = 'cadence_unconfirmed';
    else if (ageMs >= policy[AGE_KEYS[key]]) reason = 'expired';
    const currentStatus = reason ? 'unknown' : semanticStatus(key, historical);
    if (!reason && currentStatus === 'unknown') reason = 'incomplete_evidence';
    items[key] = {
      currentStatus, reason, observedAt, ageMs,
      scope: historical?.scope ?? null, historical,
    };
  }
  return {
    dataMode: loadError ? null : receipt.data_mode,
    generatedAt: loadError ? null : receipt.generated_at,
    transportState, loadError, items,
  };
}
