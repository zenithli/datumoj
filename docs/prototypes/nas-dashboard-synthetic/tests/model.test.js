import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateReceipt, deriveView, DEFAULT_POLICY} from '../web/model.js';

const original = JSON.parse(readFileSync(new URL('../examples/synthetic-status.json', import.meta.url)));
const fixture = () => structuredClone(original);
const now = Date.parse('2000-01-02T12:00:00Z');
const policy = {lastAttemptMaxAgeMs:3600000, inventoryMaxAgeMs:3600000, contentMaxAgeMs:7200000, restoreMaxAgeMs:86400000, futureSkewMs:300000};
const statuses = view => Object.values(view.items).map(item => item.currentStatus);

// Production mutations these tests catch: accepting extras, confusing generated time
// with observed time, renewing stale evidence, or conflating the four evidence scopes.
test('canonical fixture is valid and is not mutated', () => {
  const receipt = fixture();
  assert.equal(validateReceipt(receipt), receipt);
  const before = JSON.stringify(receipt);
  const view = deriveView(receipt, now, policy);
  assert.deepEqual(statuses(view), ['job_completed','matched_snapshot','matched_sample','passed_sample']);
  assert.equal(view.items.last_attempt.historical.result, 'success');
  assert.equal(JSON.stringify(receipt), before);
  assert.equal(view.dataMode, 'synthetic');
});

const invalidCases = [
  ['null receipt', () => null, 'E_OBJECT'],
  ['empty receipt', () => ({}), 'E_FIELDS'],
  ['schema boolean', r => ({...r,schema_version:true}), 'E_SCHEMA'],
  ['reported mode', r => ({...r,data_mode:'reported'}), 'E_MODE'],
  ['nested unknown secret', r => {r.nas.content_check.secret='/fake/private/SECRET_VALUE'; return r;}, 'E_FIELDS'],
  ['constructor key', r => {r.nas.restore_check.constructor='fake'; return r;}, 'E_FIELDS'],
  ['prototype key', r => {r.nas.prototype={}; return r;}, 'E_FIELDS'],
  ['own __proto__ key', r => {Object.defineProperty(r.nas,'__proto__',{value:'fake',enumerable:true}); return r;}, 'E_FIELDS'],
  ['bad prototype', r => {Object.setPrototypeOf(r.nas, {fake:'secret'}); return r;}, 'E_OBJECT'],
  ['array object', r => {r.nas.content_check=[]; return r;}, 'E_OBJECT'],
  ['boolean count', r => {r.nas.content_check.checked_objects=true; return r;}, 'E_COUNT'],
  ['fraction count', r => {r.nas.content_check.checked_objects=1.5; return r;}, 'E_COUNT'],
  ['negative count', r => {r.nas.last_attempt.error_count=-1; return r;}, 'E_COUNT'],
  ['unsafe count', r => {r.nas.content_check.checked_objects=9007199254740992; return r;}, 'E_COUNT'],
  ['nonfinite count', r => {r.nas.content_check.checked_objects=Infinity; return r;}, 'E_COUNT'],
  ['mismatch over checked', r => {r.nas.content_check.hash_mismatches=13; return r;}, 'E_RELATION'],
  ['inventory mismatch over checked', r => {r.nas.inventory_check.missing_objects=121; return r;}, 'E_RELATION'],
  ['invalid calendar day', r => ({...r,generated_at:'2000-02-30T12:00:00Z'}), 'E_TIME'],
  ['year zero', r => ({...r,generated_at:'0000-01-01T00:00:00Z'}), 'E_TIME'],
  ['timezone offset', r => ({...r,generated_at:'2000-01-02T12:00:00+00:00'}), 'E_TIME'],
  ['milliseconds', r => ({...r,generated_at:'2000-01-02T12:00:00.000Z'}), 'E_TIME'],
  ['future observed', r => {r.nas.content_check.observed_at='2000-01-03T00:00:00Z';return r;}, 'E_RELATION'],
  ['future start', r => {r.nas.last_attempt.started_at='2000-01-03T00:00:00Z';return r;}, 'E_RELATION'],
  ['start after completed', r => {r.nas.last_attempt.started_at='2000-01-02T11:51:00Z';return r;}, 'E_RELATION'],
  ['observed before completed', r => {r.nas.last_attempt.observed_at='2000-01-02T11:49:00Z';return r;}, 'E_RELATION'],
  ['null generated', r => ({...r,generated_at:null}), 'E_TIME'],
  ['bad scope', r => {r.nas.restore_check.scope='all';return r;}, 'E_ENUM'],
];
for (const [name, change, code] of invalidCases) test(`validator rejects ${name} without echoing data`, () => {
  assert.throws(() => validateReceipt(change(fixture())), error => error.message === code);
});

test('safe integer maximum and leap date accepted; nullable fields stay null', () => {
  const receipt=fixture();
  receipt.generated_at='2000-02-29T12:00:00Z';
  receipt.nas.content_check.checked_objects=9007199254740991;
  receipt.nas.last_attempt.started_at=null;
  receipt.nas.last_attempt.error_count=null;
  assert.doesNotThrow(() => validateReceipt(receipt));
  assert.equal(receipt.nas.last_attempt.started_at,null);
});

test('default cadence is unconfirmed and all current statuses unknown', () => {
  const view=deriveView(fixture(), now, DEFAULT_POLICY);
  assert.deepEqual(statuses(view), ['unknown','unknown','unknown','unknown']);
  assert.equal(view.items.last_attempt.reason,'cadence_unconfirmed');
  assert.equal(view.items.last_attempt.historical.result,'success');
});

test('missing receipt gives load error and all unknown', () => {
  const view=deriveView(null,now,policy);
  assert.equal(view.loadError,'E_OBJECT');
  assert.deepEqual(statuses(view), ['unknown','unknown','unknown','unknown']);
});

test('missing observed time is never invented from generated time', () => {
  const r=fixture(); r.nas.inventory_check.observed_at=null;
  const item=deriveView(r,now,policy).items.inventory_check;
  assert.equal(item.currentStatus,'unknown'); assert.equal(item.reason,'missing_observed_at');
  assert.equal(item.observedAt,null); assert.equal(item.historical.checked_objects,120);
});

test('four independent age limits and exact equality boundary', () => {
  const view=deriveView(fixture(),now,{...policy,lastAttemptMaxAgeMs:300000,inventoryMaxAgeMs:1800001,contentMaxAgeMs:6000000,restoreMaxAgeMs:75600001});
  assert.deepEqual(statuses(view),['unknown','matched_snapshot','unknown','passed_sample']);
  assert.equal(view.items.last_attempt.reason,'expired');
  assert.equal(view.items.content_check.reason,'expired');
  const later=deriveView(fixture(),now+10800000,policy);
  assert.deepEqual(statuses(later),['unknown','unknown','unknown','unknown']);
});

test('new generation cannot renew old observation', () => {
  const r=fixture(); r.generated_at='2000-02-01T12:00:00Z';
  assert.deepEqual(statuses(deriveView(r,Date.parse(r.generated_at),policy)),['unknown','unknown','unknown','unknown']);
});

test('future beyond skew is unknown; within skew allowed', () => {
  const view=deriveView(fixture(),now-600001,policy);
  assert.equal(view.items.last_attempt.currentStatus,'unknown');
  assert.equal(view.items.last_attempt.reason,'future_observation');
  const edge=deriveView(fixture(),now-600000,policy);
  assert.equal(edge.items.last_attempt.currentStatus,'job_completed');
});

test('invalid clock or policy suppresses every current conclusion', () => {
  for (const bad of [NaN,Infinity,undefined,'2000-01-02']) assert.deepEqual(statuses(deriveView(fixture(),bad,policy)),['unknown','unknown','unknown','unknown']);
  for (const bad of [null,{}, {...policy,contentMaxAgeMs:-1},{...policy,futureSkewMs:Infinity}]) assert.deepEqual(statuses(deriveView(fixture(),now,bad)),['unknown','unknown','unknown','unknown']);
});

test('fetch failure keeps labelled historical evidence but no current status', () => {
  const view=deriveView(fixture(),now,policy,'error');
  assert.deepEqual(statuses(view),['unknown','unknown','unknown','unknown']);
  assert.equal(view.items.last_attempt.reason,'transport_error');
  assert.equal(view.items.last_attempt.historical.result,'success');
});

test('failed latest job and running job are independent from matching checks', () => {
  const r=fixture();r.nas.last_attempt.result='failed';r.nas.last_attempt.error_count=4;
  assert.deepEqual(statuses(deriveView(r,now,policy)),['failed','matched_snapshot','matched_sample','passed_sample']);
  r.nas.last_attempt.result='running';r.nas.last_attempt.completed_at=null;
  assert.equal(deriveView(r,now,policy).items.last_attempt.currentStatus,'running');
  r.nas.last_attempt.result='success';
  assert.equal(deriveView(r,now,policy).items.last_attempt.currentStatus,'unknown');
});

test('zero checks, unknown counts or unknown scopes cannot prove a pass', () => {
  for (const key of ['inventory_check','content_check','restore_check']) {
    const r=fixture();r.nas[key].checked_objects=0;
    assert.equal(deriveView(r,now,policy).items[key].currentStatus,'unknown');
  }
  const r=fixture();r.nas.inventory_check.missing_objects=null;r.nas.content_check.hash_mismatches=null;r.nas.restore_check.scope='unknown';
  assert.deepEqual(statuses(deriveView(r,now,policy)),['job_completed','unknown','unknown','unknown']);
});

test('scope labels distinguish sample content from snapshot content', () => {
  const r=fixture();r.nas.content_check.scope='all_in_snapshot';
  const view=deriveView(r,now,policy);
  assert.equal(view.items.content_check.currentStatus,'matched_snapshot');
  assert.equal(view.items.content_check.scope,'all_in_snapshot');
  assert.equal(view.items.restore_check.currentStatus,'passed_sample');
  assert.equal(Object.hasOwn(view,'safe'),false);
  assert.equal(Object.hasOwn(view,'deleteAuthorized'),false);
});

test('nonzero differences fail within the declared scope', () => {
  const r=fixture();r.nas.inventory_check.size_mismatches=1;r.nas.content_check.hash_mismatches=1;r.nas.restore_check.result='failed';
  assert.deepEqual(statuses(deriveView(r,now,policy)),['job_completed','differences','failed','failed']);
});

test('validator sanitizes unexpected object inspection errors', () => {
  const hostile=new Proxy({}, {getPrototypeOf(){throw new Error('/fake/SECRET_VALUE');}});
  assert.throws(()=>validateReceipt(hostile),error=>error.message==='E_OBJECT');
  assert.equal(deriveView(hostile,now,policy).loadError,'E_OBJECT');
});

test('future skew is the contract-fixed five minutes, not a bypass knob', () => {
  const view=deriveView(fixture(),now,{...policy,futureSkewMs:86400000});
  assert.deepEqual(statuses(view),['unknown','unknown','unknown','unknown']);
  assert.equal(view.items.last_attempt.reason,'policy_invalid');
});
