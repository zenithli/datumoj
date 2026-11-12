import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createPoller} from '../web/poller.js';

const base = JSON.parse(readFileSync(new URL('../examples/synthetic-status.json',import.meta.url)));
const fixture = () => structuredClone(base);
const policy = {lastAttemptMaxAgeMs:3600000,inventoryMaxAgeMs:3600000,contentMaxAgeMs:7200000,restoreMaxAgeMs:86400000,futureSkewMs:300000};
const flush = async () => { for(let i=0;i<20;i++) await Promise.resolve(); };
const deferred = () => { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no;}); return {promise,resolve,reject}; };
const response = receipt => ({ok:true,redirected:false,headers:{get:()=>null},text:async()=>JSON.stringify(receipt)});

class Clock {
  time=Date.parse('2000-01-02T12:00:00Z'); next=1; tasks=new Map();
  now=()=>this.time;
  setTimeout=(fn,delay)=>{const id=this.next++;this.tasks.set(id,{fn,at:this.time+delay});return id;};
  clearTimeout=id=>this.tasks.delete(id);
  async tick(ms) {
    const target=this.time+ms;
    for(;;) {
      const due=[...this.tasks].filter(([,t])=>t.at<=target).sort((a,b)=>a[1].at-b[1].at)[0];
      if(!due) break;
      this.time=due[1].at;this.tasks.delete(due[0]);due[1].fn();await flush();
    }
    this.time=target;await flush();
  }
}
function setup(fetcher) {
  const clock=new Clock(), calls=[], renders=[];
  const fetch=async (url,options)=>{calls.push({url,options});return fetcher(calls.length,options);};
  const controller=createPoller({fetch,setTimeout:clock.setTimeout,clearTimeout:clock.clearTimeout,now:clock.now,render:(view,meta)=>renders.push({view,meta}),policy});
  return {clock,calls,renders,controller,last:()=>renders.at(-1)};
}

// Mutations caught: clearing the last valid receipt, dropping epoch guards,
// releasing a manual request lock early, or allowing chronological regression.
test('initial unknown, successful fetch, fixed same-origin URL and request options',async()=>{
  const s=setup(()=>response(fixture()));s.controller.start();await flush();
  assert.equal(s.calls.length,1);
  assert.equal(s.calls[0].url,'./status.json');
  assert.equal(s.calls[0].options.cache,'no-store');
  assert.equal(s.calls[0].options.credentials,'same-origin');
  assert.equal(s.calls[0].options.redirect,'error');
  assert.equal(s.renders[0].view.items.last_attempt.currentStatus,'unknown');
  assert.equal(s.last().view.items.last_attempt.currentStatus,'job_completed');
  assert.equal(s.last().meta.loading,false);
  s.controller.stop();
});

test('repeated manual refresh shares one in-flight request',async()=>{
  const pending=deferred();const s=setup(()=>pending.promise);
  s.controller.start();await flush();
  const a=s.controller.refresh(),b=s.controller.refresh();
  assert.equal(a,b);assert.equal(s.calls.length,1);
  pending.resolve(response(fixture()));await a;await flush();
  assert.equal(s.last().view.items.last_attempt.currentStatus,'job_completed');
  s.controller.stop();
});

test('timeout aborts and retains only historical evidence; late response ignored',async()=>{
  const late=deferred();const s=setup(n=>n===1?response(fixture()):late.promise);
  s.controller.start();await flush();s.controller.refresh();await flush();
  await s.clock.tick(10000);
  assert.equal(s.calls[1].options.signal.aborted,true);
  assert.equal(s.last().meta.lastError,'E_TIMEOUT');
  assert.equal(s.last().view.items.last_attempt.currentStatus,'unknown');
  assert.equal(s.last().view.items.last_attempt.historical.result,'success');
  const snapshots=s.renders.length;
  late.resolve(response({...fixture(),generated_at:'2000-01-03T12:00:00Z'}));await flush();
  assert.equal(s.renders.length,snapshots);
  assert.equal(s.last().view.generatedAt,'2000-01-02T12:00:00Z');
  s.controller.stop();
});

test('stop and restart isolate epochs even when old fetch ignores abort',async()=>{
  const first=deferred(),second=deferred();const s=setup(n=>n===1?first.promise:second.promise);
  s.controller.start();await flush();s.controller.stop();
  assert.equal(s.calls[0].options.signal.aborted,true);
  s.controller.start();await flush();assert.equal(s.calls.length,2);
  const newer=fixture();newer.generated_at='2000-01-03T12:00:00Z';
  second.resolve(response(newer));await flush();
  first.resolve(response(fixture()));await flush();
  assert.equal(s.last().view.generatedAt,newer.generated_at);
  assert.equal(s.last().meta.loading,false);
  s.controller.stop();assert.equal(s.clock.tasks.size,0);
  const before=s.renders.length;await s.clock.tick(180000);assert.equal(s.renders.length,before);assert.equal(s.calls.length,2);
});

test('network, HTTP, invalid JSON and invalid contract fail closed with safe codes',async()=>{
  for(const [kind,broken,code] of [
    ['network',()=>{throw new Error('/fake/SECRET_VALUE');},'E_FETCH'],
    ['http',()=>({ok:false}),'E_HTTP'],
    ['json',()=>({ok:true,text:async()=>'{secret'}),'E_JSON'],
    ['schema',()=>response({...fixture(),data_mode:'reported'}),'E_RECEIPT'],
  ]) {
    const s=setup(n=>n===1?response(fixture()):broken());s.controller.start();await flush();
    await s.controller.refresh();
    assert.equal(s.last().meta.lastError,code,kind);
    assert.equal(s.last().view.items.last_attempt.currentStatus,'unknown',kind);
    assert.equal(s.last().view.items.inventory_check.historical.checked_objects,120,kind);
    assert.equal(JSON.stringify(s.last()).includes('SECRET_VALUE'),false);
    s.controller.stop();
  }
});

test('oversized response is rejected, including streamed body; redirected response refused',async()=>{
  const cases=[
    {ok:true,text:async()=> ' '.repeat(65537)},
    {ok:true,headers:{get:()=> '65537'},text:async()=>JSON.stringify(fixture())},
    {ok:true,body:{getReader:()=>({read:async()=>({done:false,value:new Uint8Array(65537)}),cancel:async()=>{}})}},
    {ok:true,redirected:true,text:async()=>JSON.stringify(fixture())},
  ];
  for(const broken of cases) {
    const s=setup(()=>broken);s.controller.start();await flush();
    assert.equal(s.last().view.items.last_attempt.currentStatus,'unknown');
    assert.equal(s.last().meta.lastError,broken.redirected?'E_HTTP':'E_RESPONSE_SIZE');
    s.controller.stop();
  }
});

test('old or incomparable receipt cannot silently replace newer historical evidence',async()=>{
  const old=fixture();old.generated_at='2000-01-02T11:56:00Z';
  const incomparable=fixture();incomparable.generated_at='2000-01-02T12:01:00Z';incomparable.nas.inventory_check.observed_at='2000-01-02T11:29:00Z';
  for(const [incoming,code] of [[old,'E_OLDER_RECEIPT'],[incomparable,'E_UNORDERED_RECEIPT']]) {
    const s=setup(n=>response(n===1?fixture():incoming));s.controller.start();await flush();await s.controller.refresh();
    assert.equal(s.last().view.generatedAt,base.generated_at);
    assert.equal(s.last().meta.warning,code);
    assert.equal(s.last().view.items.inventory_check.observedAt,base.nas.inventory_check.observed_at);
    assert.equal(s.last().view.items.inventory_check.currentStatus,'unknown');
    s.controller.stop();
  }
});

test('null-to-known chronology and conflicting same-time evidence warn, never silently replace',async()=>{
  const missing=fixture();missing.nas.content_check.observed_at=null;
  const conflict=fixture();conflict.nas.content_check.hash_mismatches=1;
  for(const [first,next] of [[missing,fixture()],[fixture(),conflict]]) {
    const s=setup(n=>response(n===1?first:next));s.controller.start();await flush();await s.controller.refresh();
    assert.equal(s.last().meta.warning,'E_UNORDERED_RECEIPT');
    assert.deepEqual(s.controller.getState().receipt,first);
    assert.equal(s.last().view.items.content_check.currentStatus,'unknown');
    s.controller.stop();
  }
});

test('new generated time with unchanged observations does not renew evidence',async()=>{
  const next=fixture();next.generated_at='2000-01-03T12:00:00Z';
  const s=setup(n=>response(n===1?fixture():next));s.controller.start();await flush();s.controller.setAutoRefresh(false);
  await s.clock.tick(86400000);await s.controller.refresh();
  assert.equal(s.last().view.generatedAt,next.generated_at);
  assert.equal(s.last().view.items.last_attempt.currentStatus,'unknown');
  assert.equal(s.last().view.items.last_attempt.reason,'expired');s.controller.stop();
});

test('auto defaults on, off stops fetches but freshness keeps aging every minute',async()=>{
  const s=setup(()=>response(fixture()));s.controller.start();await flush();
  assert.equal(s.last().meta.autoRefresh,true);await s.clock.tick(60000);assert.equal(s.calls.length,2);
  s.controller.setAutoRefresh(false);await s.clock.tick(3300000);
  assert.equal(s.calls.length,2);assert.equal(s.last().view.items.last_attempt.currentStatus,'unknown');
  assert.equal(s.last().view.items.last_attempt.reason,'expired');
  s.controller.stop();
});

test('visibility return recalculates freshness and refreshes once without overlap',async()=>{
  const pending=deferred();const s=setup(n=>n===1?response(fixture()):pending.promise);
  s.controller.start();await flush();s.clock.time+=7200000;
  s.controller.visibilityReturn();s.controller.visibilityReturn();await flush();
  assert.equal(s.calls.length,2);assert.equal(s.last().view.items.last_attempt.currentStatus,'unknown');
  assert.equal(s.last().view.items.last_attempt.reason,'expired');
  pending.resolve(response(fixture()));await flush();s.controller.stop();
});

test('successful later receipt clears transport failure and state snapshots cannot mutate receipt',async()=>{
  const s=setup(n=>{if(n===2)throw new Error('offline');return response(fixture());});
  s.controller.start();await flush();await s.controller.refresh();await s.controller.refresh();
  assert.equal(s.last().meta.lastError,null);assert.equal(s.last().view.items.last_attempt.currentStatus,'job_completed');
  s.controller.getState().receipt.nas.last_attempt.result='failed';
  assert.equal(s.controller.getState().receipt.nas.last_attempt.result,'success');s.controller.stop();
});

test('stopping before the first fetch microtask prevents that request from starting',async()=>{
  const s=setup(()=>response(fixture()));s.controller.start();s.controller.stop();await flush();
  assert.equal(s.calls.length,0);assert.equal(s.clock.tasks.size,0);
});

test('page-read time is separate from receipt generation and observation, and retained on error',async()=>{
  const s=setup(n=>{if(n===3)throw new Error('offline');return response(fixture());});
  s.controller.start();await flush();
  assert.equal(s.last().meta.lastSuccessfulReadAt,'2000-01-02T12:00:00Z');
  await s.clock.tick(30000);await s.controller.refresh();
  assert.equal(s.last().meta.lastSuccessfulReadAt,'2000-01-02T12:00:30Z');
  assert.equal(s.last().view.generatedAt,'2000-01-02T12:00:00Z');
  assert.equal(s.last().view.items.last_attempt.observedAt,'2000-01-02T11:55:00Z');
  await s.controller.refresh();
  assert.equal(s.last().meta.lastSuccessfulReadAt,'2000-01-02T12:00:30Z');
  assert.equal(s.last().view.items.last_attempt.currentStatus,'unknown');
  s.controller.stop();
});
