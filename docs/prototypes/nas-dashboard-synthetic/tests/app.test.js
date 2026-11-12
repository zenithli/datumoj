import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mountDashboard} from '../web/app.js';

const fixture=JSON.parse(readFileSync(new URL('../examples/synthetic-status.json',import.meta.url)));
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
class Node {
  textContent='';className='';disabled=false;checked=true;hidden=false;listeners=new Map();
  set innerHTML(_value) { throw new Error('Unsafe HTML assignment'); }
  addEventListener(name,callback){this.listeners.set(name,callback);}
  fire(name){this.listeners.get(name)?.({target:this});}
}
function harness(fetcher=async()=>({ok:true,text:async()=>JSON.stringify(fixture)})) {
  const nodes=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match=>[match[1],new Node()]));
  const events=new Map(),windowEvents=new Map(),timers=new Map();let next=0,calls=0;
  const document={visibilityState:'visible',getElementById:id=>nodes.get(id),addEventListener:(name,fn)=>events.set(name,fn)};
  const window={addEventListener:(name,fn)=>windowEvents.set(name,fn)};
  const controller=mountDashboard({document,window,controllerOptions:{
    fetch:async(...args)=>{calls++;return fetcher(...args);},
    setTimeout:(fn,ms)=>{timers.set(++next,{fn,ms});return next;},clearTimeout:id=>timers.delete(id),
    now:()=>Date.parse('2000-01-02T12:00:00Z'),
  }});
  return {nodes,events,windowEvents,timers,controller,calls:()=>calls};
}

test('HTML has prominent synthetic boundary, local assets, accessible controls and all evidence sections',()=>{
  assert.match(html,/演示候选 · 合成数据 · 未接入真实 NAS/);
  assert.match(html,/<html[^>]+lang="zh-CN"/);
  assert.match(html,/id="live-status"[^>]+aria-live="polite"/);
  assert.match(html,/id="auto-refresh"[^>]+checked/);
  assert.match(html,/60 秒/);
  assert.match(html,/采集节奏未确认/);
  assert.match(html,/不能据此删除/);
  assert.match(html,/Content-Security-Policy/);
  assert.deepEqual([...html.matchAll(/(?:src|href)="([^"]+)"/g)].map(m=>m[1]).filter(value=>!value.startsWith('#')),['./styles.css','./welcome.css','./welcome-scene.svg','./app.js','./welcome.js','./welcome-scene.svg']);
  for(const key of ['last_attempt','inventory_check','content_check','restore_check']) {
    assert.match(html,new RegExp(`id="${key}-status"`));assert.match(html,new RegExp(`id="${key}-time"`));
  }
});

test('real poller binds textContent and shows historical samples without current pass',async()=>{
  const h=harness();await flush();
  assert.equal(h.calls(),1);
  assert.equal(h.nodes.get('last_attempt-status')?.textContent,'未知');
  assert.equal(h.nodes.get('last_attempt-reason')?.textContent,'采集节奏未确认');
  assert.equal(h.nodes.get('inventory-checked')?.textContent,'120');
  assert.equal(h.nodes.get('content-checked')?.textContent,'12');
  assert.equal(h.nodes.get('restore-checked')?.textContent,'3');
  assert.equal(h.nodes.get('job-result')?.textContent,'任务成功（历史记录）');
  assert.equal(h.nodes.get('receipt-generated')?.textContent,fixture.generated_at);
  assert.match(h.nodes.get('live-status')?.textContent??'',/合成回执/);
  assert.equal(h.nodes.get('refresh')?.disabled,false);
  h.controller.stop();
});

test('manual and auto controls, visibility, pagehide and pageshow use the real controller',async()=>{
  const h=harness();await flush();
  assert.equal(typeof h.nodes.get('refresh')?.listeners.get('click'),'function');
  h.nodes.get('refresh').fire('click');await flush();assert.equal(h.calls(),2);
  h.nodes.get('auto-refresh').checked=false;h.nodes.get('auto-refresh').fire('change');
  assert.equal(h.controller.getState().autoRefresh,false);
  h.events.get('visibilitychange')();await flush();assert.equal(h.calls(),2);
  h.nodes.get('auto-refresh').checked=true;h.nodes.get('auto-refresh').fire('change');
  h.events.get('visibilitychange')();await flush();assert.equal(h.calls(),3);
  h.windowEvents.get('pagehide')();assert.equal(h.timers.size,0);
  h.windowEvents.get('pageshow')();await flush();assert.equal(h.calls(),4);
  h.controller.stop();
});

test('read failure is explicit, safe, and keeps historical counts only',async()=>{
  let n=0;const h=harness(async()=>{if(++n>1)throw new Error('/fake/SECRET_VALUE');return {ok:true,text:async()=>JSON.stringify(fixture)};});
  await flush();await h.controller.refresh();
  assert.match(h.nodes.get('live-status')?.textContent??'',/读取失败/);
  assert.equal(h.nodes.get('last_attempt-status')?.textContent,'未知');
  assert.equal(h.nodes.get('inventory-checked')?.textContent,'120');
  assert.equal(h.nodes.get('last_attempt-reason')?.textContent,'读取失败，当前状态未知');
  assert.equal([...h.nodes.values()].some(node=>node.textContent.includes('SECRET_VALUE')),false);
  h.controller.stop();
});

test('untrusted text is rejected before display, never inserted as HTML',async()=>{
  const r=structuredClone(fixture);r.nas.last_attempt.result='<img src=x onerror=alert(1)>';
  const h=harness(async()=>({ok:true,text:async()=>JSON.stringify(r)}));await flush();
  assert.equal(h.nodes.get('job-result')?.textContent,'未知');
  assert.equal(h.nodes.get('inventory-checked')?.textContent,'未知');
  assert.equal([...h.nodes.values()].some(node=>node.textContent.includes('<img')),false);
  assert.match(h.nodes.get('live-status')?.textContent??'',/读取失败/);
  h.controller.stop();
});

test('unknown restore scope does not acquire a sample claim in historical result text',async()=>{
  const r=structuredClone(fixture);r.nas.restore_check.scope='unknown';
  const h=harness(async()=>({ok:true,text:async()=>JSON.stringify(r)}));await flush();
  assert.equal(h.nodes.get('restore-scope')?.textContent,'未知');
  assert.equal(h.nodes.get('restore-result')?.textContent,'通过（历史记录）');
  assert.equal(h.nodes.get('restore_check-status')?.textContent,'未知');
  h.controller.stop();
});

test('datumoj project identity and separately labelled page-read time are visible',async()=>{
  assert.match(html,/datumoj · NAS/);
  assert.doesNotMatch(html,/NAS Lens/);
  assert.match(html,/上次成功读取示例文件（UTC）/);
  assert.match(html,/仅页面读取，不是 NAS 观测或备份时间/);
  const h=harness();await flush();
  assert.equal(h.nodes.get('page-read-time')?.textContent,'2000-01-02T12:00:00Z');
  h.controller.stop();
});
