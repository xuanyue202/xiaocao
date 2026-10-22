import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {EventEmitter} from 'node:events';
import {spawnSync} from 'node:child_process';
import {claimExecution,requireEndpointAbsent,validatePlan} from '../scripts/kol_native_course_runtime.mjs';

test('capture health checkpoint works without a global process in the CUA host',()=>{
  const script=String.raw`
    import assert from 'node:assert/strict';
    import fs from 'node:fs/promises';
    import vm from 'node:vm';
    import {promisify} from 'node:util';
    const source=await fs.readFile('scripts/kol_native_course_runtime.mjs','utf8');
    let livenessChecks=0;
    let listenerPid=123;
    const child={execFile:()=>{}};
    child.execFile[promisify.custom]=async(file,args)=>{
      if(file==='/usr/sbin/lsof'){assert.equal(args[3],'123');livenessChecks++;}
      return {stdout:
      file==='/sbin/route'?'interface: en0\n':
      args[0]==='-listnetworkserviceorder'?'(1) Wi-Fi\n(Hardware Port: Wi-Fi, Device: en0)\n':
      args[0]==='-getautoproxyurl'?'Enabled: No\n':'p'+listenerPid+'\n'};
    };
    const context=vm.createContext({URL,Buffer,AbortSignal,fetch:async()=>({ok:true,json:async()=>({code:0})})});
    const modules=new Map();
    const module=new vm.SourceTextModule(source+'\nexport {networkProof};',{
      context,initializeImportMeta:meta=>{meta.url=new URL('./scripts/kol_native_course_runtime.mjs', 'file://'+process.cwd()+'/').href;},
      importModuleDynamically:async()=>{
        const stub=new vm.SyntheticModule(['runOpenAllow'],function(){this.setExport('runOpenAllow',()=>{});},{context});
        await stub.link(()=>{});await stub.evaluate();return stub;
      }
    });
    await module.link(async name=>{
      if(modules.has(name))return modules.get(name);
      assert.notEqual(name,'node:process');
      const exports=name==='node:child_process'?child:await import(name);
      const linked=new vm.SyntheticModule(Object.keys(exports),function(){for(const [key,value] of Object.entries(exports))this.setExport(key,value);},{context});
      modules.set(name,linked);return linked;
    });
    await module.evaluate();
    const result=await module.namespace.networkProof({mode:'capture',readiness:{network_service:'Wi-Fi',same_pid:123}});
    assert.equal(result.verified,true);assert.equal(livenessChecks,2);
    listenerPid=456;
    await assert.rejects(module.namespace.networkProof({mode:'capture',readiness:{network_service:'Wi-Fi',same_pid:123}}),/capture_listener_process_mismatch/);
  `;
  const result=spawnSync(process.execPath,['--experimental-vm-modules','--input-type=module','-e',script],{cwd:new URL('..',import.meta.url),encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
});

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
test('pre-input repair can retain its original entry only within the activation deadline',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'kol-entry-age-'));
  try{
    const entry={identity:'original',capture_job_id:'same',launched_at:new Date(Date.now()-4*60*1000).toISOString()};
    const entryPath=path.join(root,'entry.json');await fs.writeFile(entryPath,JSON.stringify(entry));
    const plan={...entry,repo_root:root,entry_proof_path:entryPath};const p=path.join(root,'plan.json');await fs.writeFile(p,JSON.stringify(plan));
    await claimExecution(p,plan);await assert.rejects(claimExecution(p,plan),{code:'EEXIST'});
    entry.launched_at=new Date(Date.now()-21*60*1000).toISOString();await fs.writeFile(entryPath,JSON.stringify(entry));
    await assert.rejects(claimExecution(p,plan),/entry_proof_invalid/);
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
