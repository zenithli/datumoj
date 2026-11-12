import {test} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
const path=name=>new URL('../web/'+name,import.meta.url);
const read=name=>readFileSync(path(name),'utf8');
test('one-second welcome dismisses once and does not depend on snapshot loading',async()=>{
  assert.ok(existsSync(path('welcome.js')),'welcome module must exist');
  const {startWelcome}=await import('../web/welcome.js');
  const scheduled=[];const cover={hidden:false};
  startWelcome(cover,(fn,ms)=>scheduled.push({fn,ms}));
  assert.equal(cover.hidden,false);assert.equal(scheduled.length,1);assert.equal(scheduled[0].ms,1000);
  scheduled[0].fn();assert.equal(cover.hidden,true);scheduled[0].fn();assert.equal(cover.hidden,true);
  assert.doesNotThrow(()=>startWelcome(null));
});
test('welcome is decorative, local and placed before dashboard content',()=>{
  const html=read('index.html');
  assert.match(html,/<div id="welcome-cover"/);
  assert.ok(html.indexOf('id="welcome-cover"')<html.indexOf('class="sidebar"'));
  assert.match(html,/src="\.\/welcome-scene\.svg"/);
  assert.match(html,/<script type="module" src="\.\/welcome\.js"><\/script>/);
});
test('static artwork is original local SVG with no platform logos or downloaded assets',()=>{
  assert.ok(existsSync(path('welcome-scene.svg')),'original artwork must exist');
  const svg=read('welcome-scene.svg');
  assert.match(svg,/shape-rendering="crispEdges"/);
  assert.doesNotMatch(svg,/(?:href|src)=["\']https?:|<script|<image|<animate|openai|petbouncer|dispatch-assets/i);
});
test('CSS keeps welcome about one second even if JS fails, with reduced-motion cut',()=>{
  assert.ok(existsSync(path('welcome.css')),'welcome CSS must exist');
  const css=read('welcome.css');
  assert.match(css,/animation:\s*welcome-dismiss 1s/);
  assert.match(css,/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(css,/animation-timing-function:\s*steps\(1,end\)/);
  assert.match(css,/100%\s*\{[^}]*visibility:hidden/);
});

test('skipping restores focus only if the skip button had focus',async()=>{
  const {startWelcome}=await import('../web/welcome.js');
  let click;let focusCount=0;const cover={hidden:false};
  const skip={ownerDocument:{activeElement:null},addEventListener:(name,fn)=>{assert.equal(name,'click');click=fn;}};
  const main={focus:()=>focusCount++};
  startWelcome(cover,()=>{},skip,main);
  assert.equal(typeof click,'function');skip.ownerDocument.activeElement=skip;click();
  assert.equal(cover.hidden,true);assert.equal(focusCount,1);
});

test('welcome timeout never steals unrelated focus, skip is immediate, and hash changes cannot replay',async()=>{
  const {startWelcome}=await import('../web/welcome.js');
  const callbacks=[];let click,focused=0;
  const cover={hidden:false};const unrelated={};
  const skip={ownerDocument:{activeElement:unrelated},addEventListener:(_name,fn)=>{click=fn;}};
  startWelcome(cover,(fn,ms)=>callbacks.push({fn,ms}),skip,{focus:()=>focused++});
  assert.equal(cover.hidden,false);assert.equal(callbacks[0].ms,1000);
  callbacks[0].fn();assert.equal(cover.hidden,true);assert.equal(focused,0);
  click();assert.equal(focused,0);
  const second={hidden:false};startWelcome(second,()=>{},skip,{focus:()=>focused++});
  skip.ownerDocument.activeElement=skip;click();assert.equal(second.hidden,true);assert.equal(focused,1);
  const js=read('welcome.js');
  assert.doesNotMatch(js,/hashchange|location\.|fetch\(|localStorage|sessionStorage/);
});

test('welcome integration retains dashboard target, warning boundary and same-origin assets',()=>{
  const html=read('index.html');
  assert.match(html,/id="main" tabindex="-1"/);
  assert.match(html,/演示候选 · 合成数据 · 未接入真实 NAS/);
  assert.match(html,/id="auto-refresh"[^>]*checked/);
  assert.match(html,/<link rel="stylesheet" href="\.\/welcome.css">/);
  assert.match(html,/id="welcome-skip" type="button"/);
  assert.match(html,/<img[^>]+src="\.\/welcome-scene.svg"[^>]+alt=""/);
  assert.match(html,/aria-hidden="true"/);
});
