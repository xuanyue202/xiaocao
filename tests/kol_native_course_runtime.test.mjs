import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {EventEmitter} from 'node:events';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {claimExecution,requireEndpointAbsent,validatePlan,validateInputWindow} from '../scripts/kol_native_course_runtime.mjs';

test('capture health checkpoint works without a global process in the CUA host',()=>{
  const script=String.raw`
    import assert from 'node:assert/strict';
    import fs from 'node:fs/promises';
    import vm from 'node:vm';
    import {promisify} from 'node:util';
    const source=await fs.readFile('scripts/kol_native_course_runtime.mjs','utf8');
    let livenessChecks=0;
    let listenerPid=123;
    let held=false;
    let pacEnabled=false;
    const mutations=[];
    const child={execFile:()=>{}};
    child.execFile[promisify.custom]=async(file,args)=>{
      if(file==='/usr/sbin/lsof'){assert.equal(args[3],'123');livenessChecks++;}
      if(args[0]==='-setautoproxyurl')mutations.push(args);
      if(args[0]==='-setautoproxystate'){mutations.push(args);pacEnabled=args[2]==='on';}
      return {stdout:
      file==='/sbin/route'?'interface: en0\n':
      args[0]==='-listnetworkserviceorder'?'(1) Wi-Fi\n(Hardware Port: Wi-Fi, Device: en0)\n':
      args[0]==='-getautoproxyurl'?'URL: http://127.0.0.1:2023/proxy.pac\nEnabled: '+(pacEnabled?'Yes':'No')+'\n':'p'+listenerPid+'\n'};
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
      let exports=name==='node:child_process'?child:await import(name);
      if(name==='node:fs/promises'){
        const readFile=async(file,...args)=>String(file).endsWith('/native_share_bridge.json')
          ? JSON.stringify({activation_hold:{active:held}}) : fs.readFile(file,...args);
        exports={...exports,default:{...exports.default,readFile},readFile};
      }
      const linked=new vm.SyntheticModule(Object.keys(exports),function(){for(const [key,value] of Object.entries(exports))this.setExport(key,value);},{context});
      modules.set(name,linked);return linked;
    });
    await module.evaluate();
    const result=await module.namespace.networkProof({mode:'capture',readiness:{network_service:'Wi-Fi',same_pid:123}});
    assert.equal(result.verified,true);assert.equal(livenessChecks,2);
    const control={mode:'capture',keep_capture_pac_off:true,explicit_ui_diagnostic_authorization_sha256:'a'.repeat(64),readiness:{network_service:'Wi-Fi',same_pid:123}};
    // This is the production before-Allow checkpoint, with the same live backend.
    await module.namespace.networkProof(control,true);
    assert.equal(mutations.length,0);assert.equal(pacEnabled,false);
    await module.namespace.networkProof({...control,keep_capture_pac_off:false},true);
    assert.equal(mutations.length,2);assert.equal(pacEnabled,true);
    await assert.rejects(module.namespace.networkProof(control,true),/entry_requires_pac_off/);
    pacEnabled=false;
    listenerPid=456;
    await assert.rejects(module.namespace.networkProof({mode:'capture',readiness:{network_service:'Wi-Fi',same_pid:123}}),/capture_listener_process_mismatch/);
    const checksBeforeHold=livenessChecks;held=true;
    await assert.rejects(module.namespace.networkProof({mode:'capture',readiness:{network_service:'Wi-Fi',same_pid:123}}),/native_entry_suspended/);
    assert.equal(livenessChecks,checksBeforeHold);
  `;
  const result=spawnSync(process.execPath,['--experimental-vm-modules','--input-type=module','-e',script],{cwd:new URL('..',import.meta.url),encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
});

test('PAC timing control requires capture mode and explicit authorization before any I/O',async()=>{
  const plan={schema_version:1,mode:'capture',keep_capture_pac_off:true};
  await assert.rejects(validatePlan(plan),/diagnostic_authorization_missing/);
  for(const value of ['invalid',['a'.repeat(64)],{},null])
    await assert.rejects(validatePlan({...plan,explicit_ui_diagnostic_authorization_sha256:value}),/diagnostic_authorization_missing/);
  await assert.rejects(validatePlan({...plan,mode:'diagnostic',explicit_ui_diagnostic_authorization_sha256:'a'.repeat(64)}),/pac_control_requires_capture/);
  await assert.rejects(validatePlan({...plan,keep_capture_pac_off:'true'}),/pac_control_invalid/);
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


test('prepared stale Cancel dispatch is claimed once, expires and preserves an uncertain effect',async()=>{
  const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'kol-reset-dispatch-')));
  try{
    await fs.mkdir(path.join(root,'scripts'));
    for(const name of ['kol_native_course_runtime.mjs','kol_native_course_allow.mjs'])await fs.copyFile(new URL('../scripts/'+name,import.meta.url),path.join(root,'scripts',name));
    const {cancelPreparedStaleBridgeReset}=await import(path.join(root,'scripts/kol_native_course_runtime.mjs'));
    const claimPath=path.join(root,'output/live/kol_native_atomic/claims/kol-123456789abc.stale-confirmation-reset.json');
    await fs.mkdir(path.dirname(claimPath),{recursive:true});
    const configPath=path.join(root,'output/live/kol_xiaocao_live/native_share_bridge.json');
    await fs.mkdir(path.dirname(configPath),{recursive:true});
    await fs.writeFile(configPath,JSON.stringify({activation_hold:{active:false}}));
    const binary=path.join(root,'output/live/kol_native_atomic/window-'+'0'.repeat(16));
    const presence={title:'草料二维码',match_count:1,window_id:123,on_current_screen:true,width:414,height:780};
    await fs.writeFile(binary,"#!/bin/sh\nprintf '%s' '"+JSON.stringify(presence)+"'\n",{mode:0o700});
    const planPath=path.join(root,'plan.json');
    await fs.writeFile(planPath,JSON.stringify({repo_root:root,window_binary:binary,window_binary_sha256:createHash('sha256').update(await fs.readFile(binary)).digest('hex')}));
    const reset={prepared_at:new Date().toISOString(),identity:'original',capture_job_id:'kol-123456789abc',
      frame_sha256:'a'.repeat(64),cancel_point:[100,200],claim_path:claimPath,frame_width:828,frame_height:1560,window_id:123,
      plan_path:planPath,plan_sha256:createHash('sha256').update(await fs.readFile(planPath)).digest('hex')};
    await fs.writeFile(claimPath,JSON.stringify(reset));let clicks=0;
    const app={click:async point=>{assert.deepEqual(point,[100,200]);clicks++;throw Error('timeoutReached');}};
    await assert.rejects(cancelPreparedStaleBridgeReset({app,reset:{...reset,cancel_point:[300,400]}}),/reset_claim_changed/);
    const old={...reset,prepared_at:new Date(Date.now()-31000).toISOString()};
    await fs.writeFile(claimPath,JSON.stringify(old));
    await assert.rejects(cancelPreparedStaleBridgeReset({app,reset}),/reset_preparation_expired/);
    await fs.writeFile(claimPath,JSON.stringify(reset));
    const copy=path.join(root,'copy.json');await fs.copyFile(claimPath,copy);
    await assert.rejects(cancelPreparedStaleBridgeReset({app,reset:{...reset,claim_path:copy}}),/reset_claim_path_invalid/);
    await assert.rejects(cancelPreparedStaleBridgeReset({app,reset:{...reset,prepared_at:new Date(Date.now()-1000).toISOString()}}),/reset_claim_changed/);
    assert.equal(clicks,0);
    await fs.writeFile(configPath,JSON.stringify({activation_hold:{active:true}}));
    // A prepared claim cannot outlive a newly activated hold. Remove the checker
    // temporarily so a window-check attempt would fail with ENOENT instead.
    await fs.rename(binary,binary+'.held');
    await assert.rejects(cancelPreparedStaleBridgeReset({app,reset}),/native_entry_suspended/);
    assert.equal(clicks,0);
    await assert.rejects(fs.stat(claimPath+'.dispatch'),{code:'ENOENT'});
    assert.deepEqual(JSON.parse(await fs.readFile(claimPath,'utf8')),reset);
    await fs.rename(binary+'.held',binary);
    await fs.writeFile(configPath,JSON.stringify({activation_hold:{active:false}}));
    await assert.rejects(cancelPreparedStaleBridgeReset({app,reset}),/timeoutReached/);
    await assert.rejects(cancelPreparedStaleBridgeReset({app,reset}),{code:'EEXIST'});
    assert.equal(clicks,1);assert.equal(JSON.parse(await fs.readFile(claimPath,'utf8')).capture_job_id,'kol-123456789abc');
  }finally{await fs.rm(root,{recursive:true,force:true});}
});


test('readable off-screen, duplicated, resized or changed windows cannot receive input',()=>{
  const options={title:'草料二维码',width:828,height:1560,windowId:123};
  const proof={title:'草料二维码',match_count:1,window_id:123,on_current_screen:true,width:414,height:780};
  assert.equal(validateInputWindow(proof,options).window_id,123);
  for(const patch of [{on_current_screen:false},{match_count:2},{window_id:456},{width:500},{title:'微信'}])
    assert.throws(()=>validateInputWindow({...proof,...patch},options));
});


test('an activation hold rejects an otherwise bound plan before Browser, network or UI',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'kol-held-plan-'));
  try{
    const identity='kol-wechat-'+'a'.repeat(24),capture='kol-'+'b'.repeat(12),message='c'.repeat(64);
    const dir=path.join(root,'output/live/kol_xiaocao_live');await fs.mkdir(path.join(dir,'wechat_subscription'),{recursive:true});
    await fs.writeFile(path.join(dir,'wechat_subscription/manifest.json'),JSON.stringify({items:{[identity]:{capture_job_id:capture,message_sha256:message}}}));
    await fs.writeFile(path.join(dir,'native_share_bridge.json'),JSON.stringify({activation_hold:{active:true}}));
    await assert.rejects(validatePlan({schema_version:1,mode:'capture',prepared_at:new Date().toISOString(),repo_root:root,
      identity,capture_job_id:capture,message_sha256:message,readiness:{identity,capture_job_id:capture,
        observed_at:new Date().toISOString(),singleton_healthy:true,same_pid:123}}),/native_entry_suspended/);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
