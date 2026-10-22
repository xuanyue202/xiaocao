import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {EventEmitter} from 'node:events';
import {claimExecution,requireEndpointAbsent,validatePlan} from '../scripts/kol_native_course_runtime.mjs';

test('copying the plan or entry file cannot repeat the same entry dispatch',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'kol-atomic-claim-'));
  try{
    const entry={identity:'original',capture_job_id:'same',launched_at:new Date().toISOString()};
    await fs.writeFile(path.join(root,'entry.json'),JSON.stringify(entry));
    const plan={identity:entry.identity,capture_job_id:entry.capture_job_id,repo_root:root,entry_proof_path:path.join(root,'entry.json')};
    const first=path.join(root,'a.json'),second=path.join(root,'b.json');
    await fs.writeFile(first,JSON.stringify(plan));await claimExecution(first,plan);
    const copiedEntry=path.join(root,'copy.json');await fs.writeFile(copiedEntry,JSON.stringify(entry,null,2));
    const copy={...plan,entry_proof_path:copiedEntry};await fs.writeFile(second,JSON.stringify(copy));
    await assert.rejects(claimExecution(second,copy),{code:'EEXIST'});
    assert.equal((await fs.readdir(path.join(root,'output/live/kol_native_atomic/claims'))).length,1);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
function connector(result) {
  return ()=>{const socket=new EventEmitter();socket.destroy=()=>{};socket.setTimeout=(_ms,cb)=>{if(result==='timeout')queueMicrotask(cb);};
    queueMicrotask(()=>{if(result==='connect')socket.emit('connect');else if(result!=='timeout')socket.emit('error',{code:result});});return socket;};
}
test('only explicit refusal proves capture endpoint absent',async()=>{
  await requireEndpointAbsent(2022,connector('ECONNREFUSED'));
  for(const result of ['timeout','connect','ECONNRESET','EACCES'])await assert.rejects(requireEndpointAbsent(2022,connector(result)),/not_proven_absent/);
});
test('stale or mismatched readiness fails before local network access',async()=>{
  const plan={schema_version:1,mode:'capture',prepared_at:new Date().toISOString(),identity:'kol-wechat-7dc6259d8cf7507c1d0ed781',capture_job_id:'kol-5b7178fd4cc1',message_sha256:'f'.repeat(64),readiness:{identity:'other',capture_job_id:'kol-5b7178fd4cc1',observed_at:new Date().toISOString()}};
  await assert.rejects(validatePlan(plan),/readiness_binding_invalid/);
  plan.readiness.identity=plan.identity;plan.readiness.observed_at='2020-01-01T00:00:00Z';
  await assert.rejects(validatePlan(plan),/readiness_binding_invalid/);
});
test('preinput repair retains history, allows only a single zero-dispatch resume',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'kol-preinput-'));
  try{
    const entry={identity:'original',capture_job_id:'same',launched_at:new Date().toISOString()};
    const entryPath=path.join(root,'entry.json');await fs.writeFile(entryPath,JSON.stringify(entry));
    const plan={...entry,repo_root:root,entry_proof_path:entryPath};const p=path.join(root,'plan.json');await fs.writeFile(p,JSON.stringify(plan));
    await claimExecution(p,plan);
    const row=(event,extra={})=>({...entry,stage:'B0',event,at:new Date().toISOString(),...extra});
    const prefix=[row('observation_requested'),row('observation_received',{ax_sha256:'a'.repeat(64),image_sha256:'b'.repeat(64)})];
    const audit=p+'.events.jsonl';
    for(const bad of [
      [...prefix,row('state_rejected',{reason:'security_relogin'}),row('stopped',{reason:'execution_error'})],
      [...prefix,row('dispatch_requested'),row('stopped',{reason:'execution_error'})],
      [row('observation_received'),row('stopped',{reason:'execution_error'})],
      [row('observation_requested'),row('observation_received'),row('stopped',{reason:'execution_error'})],
    ]){await fs.writeFile(audit,bad.map(JSON.stringify).join('\n')+'\n');await assert.rejects(claimExecution(p,plan,{resumePreinput:true}));}
    const good=[...prefix,row('stopped',{reason:'execution_error'})].map(JSON.stringify).join('\n')+'\n';await fs.writeFile(audit,good);
    await claimExecution(p,plan,{resumePreinput:true});await assert.rejects(claimExecution(p,plan,{resumePreinput:true}),{code:'EEXIST'});
    assert.equal(await fs.readFile(audit,'utf8'),good);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
