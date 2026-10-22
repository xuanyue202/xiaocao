import assert from 'node:assert/strict';
import test from 'node:test';
import { runOpenAllow } from '../scripts/kol_native_course_allow.mjs';

const line = (text, x, y, w=.3, h=.04) => ({text, confidence:.5,bounding_box:[x,y,w,h]});
const bridge = {state:'Window: "草料二维码", App: 微信.', screenshot:Buffer.from('bridge')};
const allow = {state:bridge.state,screenshot:Buffer.from('allow')};
const brand = {state:'Window: "见势擒龙团", App: 微信.',screenshot:Buffer.from('brand')};
const images = {
  bridge:{width:828,height:1560,lines:[line('见势擒龙团 | 打开当前课程',.2,.7,.6)]},
  allow:{width:828,height:1560,lines:[line('即将打开“见势擒龙团”小程序',.2,.5,.6),line('取消',.2,.35,.1),line('允许',.65,.35,.1)]},
  brand:{width:2048,height:1624,lines:[line('此为加密直播',.4,.7),line('请输入课程密码',.4,.5)]},
};
function harness(frames=[bridge,bridge,allow,allow,brand], mutate=()=>{}) {
  const calls=[], records=[];let index=0;
  const app={getAXStateAndScreenshot:async()=>{calls.push('read');return structuredClone(frames[Math.min(index++,frames.length-1)]);},click:async p=>{calls.push('click');assert(p.every(Number.isFinite));}};
  const recognize=async bytes=>{const r=structuredClone(images[Buffer.from(bytes).toString()]);mutate(r);return r;};
  return {calls,records,options:{app,recognize,record:async r=>records.push(structuredClone(r)),beforeAllow:async()=>{calls.push('pac');return {verified:true};}}};
}
test('one invocation observes and dispatches each action once without model callbacks',async()=>{
  const h=harness();const r=await runOpenAllow(h.options);
  assert.equal(r.status,'brand_ready');assert.deepEqual(h.calls,['read','read','click','read','pac','read','click','read']);
  assert.equal(h.records.filter(r=>r.event==='dispatch_requested').length,2);
  assert(!JSON.stringify(h.records).includes('请输入'));assert(!JSON.stringify(h.records).includes('base64'));
});
test('wrong brand cannot reach Allow or PAC',async()=>{
  const h=harness(undefined,r=>{for(const l of r.lines)l.text=l.text.replace('即将打开“见势擒龙团”','即将打开“其他程序”');});
  const r=await runOpenAllow(h.options);assert.equal(r.status,'stopped');assert.deepEqual(h.calls,['read','read','click','read']);
});
test('unchanged B1 result never retries or enables PAC',async()=>{
  const h=harness([bridge,bridge,bridge]);const r=await runOpenAllow(h.options);assert.equal(r.status,'stopped');assert.equal(r.reason,'render_not_ready');assert.equal(h.calls.filter(c=>c==='click').length,1);
});
test('ambiguous current course buttons stop before any input',async()=>{
  const h=harness(undefined,r=>{if(r.lines[0].text.includes('打开当前'))r.lines.push(r.lines[0]);});
  assert.equal((await runOpenAllow(h.options)).status,'stopped');assert.deepEqual(h.calls,['read']);
});
test('security stops before input, and raw text is not exported',async()=>{
  const h=harness(undefined,r=>r.lines.push(line('为了你的账号安全，请重新登录',.1,.1)));
  const r=await runOpenAllow(h.options);assert.equal(r.reason,'security_relogin');assert.deepEqual(h.calls,['read']);
  assert(!JSON.stringify(h.records).includes('为了'));
});
test('uncertain click retains pending dispatch and makes one passive readback',async()=>{
  const h=harness();h.options.app.click=async()=>{h.calls.push('click');throw Error('timeoutReached');};
  const r=await runOpenAllow(h.options);assert.equal(r.status,'stopped');assert.equal(r.reason,'native_input_uncertain');
  assert.deepEqual(h.calls,['read','read','click','read']);assert(h.records.some(r=>r.event==='dispatch_unknown'));
});
test('PAC failure stops before B2',async()=>{
  const h=harness();h.options.beforeAllow=async()=>{h.calls.push('pac');throw Error('private diagnostic');};
  const r=await runOpenAllow(h.options);assert.equal(r.reason,'pac_checkpoint_failed');assert.deepEqual(h.calls,['read','read','click','read','pac']);
});
test('changed window during checkpoint stops before Allow',async()=>{
  const h=harness([bridge,bridge,allow,{state:'Window: "微信", App: 微信.',screenshot:Buffer.from('bridge')}]);
  const r=await runOpenAllow(h.options);assert.equal(r.reason,'bridge_not_current');assert.deepEqual(h.calls,['read','read','click','read','pac','read']);
});
test('uncertain OCR never supplies a click point',async()=>{
  const h=harness(undefined,r=>{r.lines[0].confidence=.3;});
  assert.equal((await runOpenAllow(h.options)).reason,'target_recognition_uncertain');assert.deepEqual(h.calls,['read']);
});
test('same window title in another App cannot receive input',async()=>{
  const h=harness([{...bridge,state:'Window: "草料二维码", App: Other.'}]);
  assert.equal((await runOpenAllow(h.options)).reason,'wrong_native_app');assert.deepEqual(h.calls,['read']);
});
test('direct brand navigation does not imply capture PAC was ready',async()=>{
  const h=harness([bridge,bridge,brand]);assert.equal((await runOpenAllow(h.options)).reason,'brand_opened_without_allow');assert.deepEqual(h.calls,['read','read','click','read']);
});
test('empty window with disabled chats preserves the first abnormal observation',async()=>{
  const h=harness([{...bridge,state:'Window: "", App: 微信.\n33 (disabled) 聊天'}]);
  assert.equal((await runOpenAllow(h.options)).reason,'empty_window_disabled_chat');
  assert(h.records.some(r=>r.event==='state_rejected'&&r.reason==='empty_window_disabled_chat'));
  assert.deepEqual(h.calls,['read']);
});
test('security takes precedence when the same frame also has disabled chats',async()=>{
  const h=harness([{...bridge,state:'Window: "", App: 微信.\n33 (disabled) 聊天\n为了你的账号安全，请重新登录'}]);
  assert.equal((await runOpenAllow(h.options)).reason,'security_relogin');assert.deepEqual(h.calls,['read']);
});
test('confirmation animation is awaited within the same invocation without another B1',async()=>{
  const h=harness([bridge,bridge,bridge,allow,allow,brand]);
  assert.equal((await runOpenAllow(h.options)).status,'brand_ready');
  assert.equal(h.calls.filter(c=>c==='click').length,2);
});
test('one failed observation after Allow is retained and passively recovered without input',async()=>{
  const h=harness();const original=h.options.app.getAXStateAndScreenshot;let reads=0;
  h.options.app.getAXStateAndScreenshot=async()=>{reads++;if(reads===5)throw Error('transition read failed');return original();};
  assert.equal((await runOpenAllow(h.options)).status,'brand_ready');
  assert.equal(h.calls.filter(c=>c==='click').length,2);
  assert(h.records.some(r=>r.event==='observation_failed'&&r.reported_error_code==='observation_error'));
});
test('policy denial on a post-Allow observation does not retry',async()=>{
  const h=harness();const original=h.options.app.getAXStateAndScreenshot;let reads=0;
  h.options.app.getAXStateAndScreenshot=async()=>{reads++;if(reads===5)throw Error('policy denied');return original();};
  assert.equal((await runOpenAllow(h.options)).reason,'native_bridge_policy_denied');assert.equal(reads,5);
});
