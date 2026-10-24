/** Local image analysis and guarded capture checkpoints for the CUA-only controller. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import net from 'node:net';
import {fileURLToPath} from 'node:url';
const runtimeRepoRoot=fileURLToPath(new URL('../',import.meta.url));
const execute=promisify(execFile);
const exec=(file,args,options={})=>execute(file,args,{timeout:3000,maxBuffer:1024*1024,...options});
const sha=b=>createHash('sha256').update(b).digest('hex');
const controllerUrl=new URL('./kol_native_course_allow.mjs',import.meta.url);
const {runOpenAllow,prepareStaleConfirmationReset}=await import(controllerUrl.href+'?source='+sha(await fs.readFile(controllerUrl)));
const json=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const requireThat=(ok,reason)=>{if(!ok){const error=Error(reason);error.safeReason=reason;throw error;}};
const recent=(t,maxAgeMs=180000)=>Number.isFinite(Date.parse(t))&&Date.now()-Date.parse(t)>=0&&Date.now()-Date.parse(t)<maxAgeMs;
// A pre-input runtime repair may reuse its entry within the runner's activation
// deadline; plan, Browser and readiness proofs still require fresh three-minute reads.
const recentEntry=t=>recent(t,20*60*1000);

async function requireNativeEntryEnabled(root) {
  let config;
  try {
    config=await json(path.join(root,'output/live/kol_xiaocao_live/native_share_bridge.json'));
  } catch {
    requireThat(false,'native_entry_configuration_unreadable');
  }
  requireThat(config!==null&&!Array.isArray(config)&&typeof config==='object','native_entry_configuration_unreadable');
  const hold=config.activation_hold;
  requireThat(hold===undefined||(hold!==null&&!Array.isArray(hold)&&typeof hold==='object'&&typeof hold.active==='boolean'),'native_entry_configuration_unreadable');
  requireThat(hold?.active!==true,'native_entry_suspended');
  return config;
}

export async function requireEndpointAbsent(port,connect=net.createConnection) {
  await new Promise((resolve,reject)=>{
    const socket=connect({host:'127.0.0.1',port});
    const fail=()=>{socket.destroy();reject(Error('diagnostic_endpoint_not_proven_absent'));};
    socket.setTimeout(1000,fail);socket.once('connect',fail);
    socket.once('error',error=>{socket.destroy();if(error.code==='ECONNREFUSED')resolve();else reject(Error('diagnostic_endpoint_not_proven_absent'));});
  });
}

export function visionRecognizer(binary) {
  return async bytes=>{
    const dir=await fs.mkdtemp(path.join(os.tmpdir(),'kol-current-frame-'));
    try {
      await fs.chmod(dir,0o700);const image=path.join(dir,'frame.png');
      await fs.writeFile(image,bytes,{mode:0o600});
      const r=await exec(binary,[image],{timeout:5000,maxBuffer:1024*1024});return JSON.parse(r.stdout);
    }finally{await fs.rm(dir,{recursive:true,force:true});}
  };
}
async function networkProof(plan,enable=false) {
  await requireNativeEntryEnabled(runtimeRepoRoot);
  const service=plan.readiness.network_service;
  requireThat(typeof service==='string'&&service.length>0&&!service.startsWith('-'),'network_service_invalid');
  const route=(await exec('/sbin/route',['-n','get','default'])).stdout;
  const iface=/^\s*interface:\s*(\S+)/m.exec(route)?.[1];
  const order=(await exec('/usr/sbin/networksetup',['-listnetworkserviceorder'])).stdout;
  const names=[...order.matchAll(/\(\d+\) (.+)\n\(Hardware Port: [^\n]*Device: ([^)]+)\)/g)].filter(m=>m[2]===iface).map(m=>m[1]);
  requireThat(names.length===1&&names[0]===service,'network_service_changed');
  if(plan.mode==='capture') {
    const response=await fetch('http://127.0.0.1:2022/api/status',{signal:AbortSignal.timeout(3000)});
    const status=await response.json();requireThat(response.ok&&status.code===0,'capture_api_unhealthy');
    for(const port of [2022,2023]){
      const listeners=(await exec('/usr/sbin/lsof',['-nP','-a','-p',String(plan.readiness.same_pid),`-iTCP:${port}`,'-sTCP:LISTEN','-Fp'])).stdout;
      requireThat(listeners.split('\n').includes(`p${plan.readiness.same_pid}`),'capture_listener_process_mismatch');
    }
  } else {
    for(const port of [2022,2023])await requireEndpointAbsent(port);
  }
  let pac=(await exec('/usr/sbin/networksetup',['-getautoproxyurl',service])).stdout;
  if(!enable)requireThat(pac.includes('Enabled: No'),'entry_requires_pac_off');
  if(plan.mode==='diagnostic')requireThat(/Enabled: No/.test(pac),'diagnostic_requires_pac_off');
  if(enable&&plan.mode==='capture'){
    const response=await fetch('http://127.0.0.1:2023/proxy.pac',{signal:AbortSignal.timeout(3000)});
    requireThat(response.ok,'capture_pac_unhealthy');
    if(!pac.includes('URL: http://127.0.0.1:2023/proxy.pac')||!pac.includes('Enabled: Yes')){
      await exec('/usr/sbin/networksetup',['-setautoproxyurl',service,'http://127.0.0.1:2023/proxy.pac']);
      await exec('/usr/sbin/networksetup',['-setautoproxystate',service,'on']);
    }
    pac=(await exec('/usr/sbin/networksetup',['-getautoproxyurl',service])).stdout;
    requireThat(pac.includes('URL: http://127.0.0.1:2023/proxy.pac')&&pac.includes('Enabled: Yes'),'capture_pac_readback_failed');
  }
  return {verified:true,mode:plan.mode,network_service:service,pac_sha256:sha(pac)};
}

export function validateInputWindow(proof,{title,width,height,windowId}={}) {
  requireThat(proof?.title===title&&proof.match_count===1&&Number.isSafeInteger(proof.window_id),'bridge_window_not_unique');
  requireThat(proof.on_current_screen===true,'bridge_window_not_on_current_screen');
  requireThat(windowId===undefined||windowId===proof.window_id,'bridge_input_window_changed');
  const sx=width/proof.width,sy=height/proof.height;
  requireThat([1,2].some(scale=>Math.abs(sx-scale)<.01&&Math.abs(sy-scale)<.01),'bridge_input_geometry_changed');
  return proof;
}
export function createInputWindowGuard(readWindow) {
  let windowId;
  return async frame=>{
    const proof=await readWindow(frame);
    requireThat(windowId===undefined||proof.window_id===windowId,'bridge_input_window_changed');
    windowId=proof.window_id;
    return proof;
  };
}
async function requireInputWindow(plan,frame,windowId) {
  await requireNativeEntryEnabled(runtimeRepoRoot);
  const binary=path.resolve(plan.window_binary??'');
  requireThat(path.dirname(binary)===path.join(plan.repo_root,'output/live/kol_native_atomic')&&/^window-[a-f0-9]{16}$/.test(path.basename(binary)),'window_checker_path_invalid');
  requireThat(sha(await fs.readFile(binary))===plan.window_binary_sha256,'window_checker_changed');
  const title=/^Window:\s*"([^"]*)"/m.exec(frame.state)?.[1];
  requireThat(['草料二维码','见势擒龙团'].includes(title),'bridge_input_title_invalid');
  const result=await exec(binary,[title]);
  return validateInputWindow(JSON.parse(result.stdout),{title,width:frame.ocr.width,height:frame.ocr.height,windowId});
}

export async function validatePlan(plan,{requireEntry=true}={}) {
  requireThat(plan.schema_version===1&&['capture','diagnostic'].includes(plan.mode),'plan_schema_invalid');
  requireThat(recent(plan.prepared_at),'plan_expired');
  requireThat(/^kol-wechat-[a-f0-9]{24}$/.test(plan.identity)&&/^kol-[a-f0-9]{12}$/.test(plan.capture_job_id),'plan_identity_invalid');
  requireThat(/^[a-f0-9]{64}$/.test(plan.message_sha256),'plan_message_invalid');
  requireThat(plan.readiness?.identity===plan.identity&&plan.readiness.capture_job_id===plan.capture_job_id&&recent(plan.readiness.observed_at),'readiness_binding_invalid');
  if(plan.mode==='capture')requireThat(plan.readiness.singleton_healthy===true&&Number.isSafeInteger(plan.readiness.same_pid)&&plan.readiness.same_pid>1,'readiness_process_invalid');
  const root=path.resolve(plan.repo_root), sub=path.join(root,'output/live/kol_xiaocao_live/wechat_subscription');
  const manifest=await json(path.join(sub,'manifest.json')), item=manifest.items[plan.identity];
  requireThat(item?.capture_job_id===plan.capture_job_id&&item.message_sha256===plan.message_sha256,'original_binding_changed');
  const config=await requireNativeEntryEnabled(root);
  requireThat(config.last_configured_subscription_id===plan.identity&&config.last_configured_message_sha256===plan.message_sha256,'bridge_binding_changed');
  const proof=await json(plan.browser_proof_path);
  requireThat(recent(proof.observed_at)&&proof.component_reopened===true&&proof.identity===plan.identity&&proof.capture_job_id===plan.capture_job_id&&proof.saved_target===plan.saved_target,'browser_proof_invalid');
  requireThat(proof.editor_url===config.editor_url&&plan.saved_target===`#小程序://见势擒龙团/${item.mini_program_token}`,'saved_target_changed');
  if(requireEntry){
    const entry=await json(plan.entry_proof_path);
    requireThat(entry.identity===plan.identity&&entry.capture_job_id===plan.capture_job_id&&entry.status==='entry_launched_once'&&recentEntry(entry.launched_at),'entry_proof_invalid');
  }else requireThat(plan.mode==='capture','reset_requires_original_capture');
  if(plan.mode==='diagnostic')requireThat(/^[a-f0-9]{64}$/.test(plan.explicit_ui_diagnostic_authorization_sha256),'diagnostic_authorization_missing');
  else {
    const lines=(await fs.readFile(path.join(sub,'items',plan.identity,'capture_jobs.jsonl'),'utf8')).trim().split('\n');
    const capture=JSON.parse(lines.at(-1));
    requireThat(capture.job_id===plan.capture_job_id,'capture_ledger_binding_changed');
    requireThat(item.status!=='completed'&&capture.status==='awaiting_capture'&&!capture.download_task_id&&!capture.candidate&&!item.handoff_path,'capture_already_bound');
    const events=(await fs.readFile(path.join(sub,'items',plan.identity,'events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
    const started=events.filter(r=>['sniffer_started','sniffer_resumed'].includes(r.event)).at(-1);
    requireThat(started?.process_pid===plan.readiness.same_pid,'capture_process_binding_changed');
  }
  requireThat(path.dirname(path.resolve(plan.vision_binary))===path.join(root,'output/live/kol_native_atomic')&&/^vision-[a-f0-9]{16}$/.test(path.basename(plan.vision_binary)),'recognizer_path_invalid');
  requireThat(sha(await fs.readFile(plan.vision_binary))===plan.vision_binary_sha256,'recognizer_changed');
  return {validated:true};
}

export async function claimExecution(planPath,plan,{resumePreinput=false}={}) {
  const entry=await json(plan.entry_proof_path);
  requireThat(entry.identity===plan.identity&&entry.capture_job_id===plan.capture_job_id&&recentEntry(entry.launched_at),'entry_proof_invalid');
  const entryKey=sha(JSON.stringify([plan.identity,plan.capture_job_id,new Date(entry.launched_at).toISOString()]));
  const dir=path.join(plan.repo_root,'output/live/kol_native_atomic/claims');await fs.mkdir(dir,{recursive:true,mode:0o700});
  const claimPath=path.join(dir,entryKey+'.json');
  let claim;
  try{claim=await fs.open(claimPath,'wx',0o600);}catch(error){
    if(error.code!=='EEXIST'||!resumePreinput)throw error;
    const original=await json(claimPath);
    requireThat(original.plan_sha256===sha(await fs.readFile(planPath)),'preinput_plan_changed');
    const audit=await fs.readFile(path.resolve(planPath)+'.events.jsonl','utf8');
    const rows=audit.trim().split('\n').map(JSON.parse);
    requireThat(rows.length>=3&&rows.every(r=>r.identity===plan.identity&&r.capture_job_id===plan.capture_job_id&&r.stage==='B0'&&['observation_requested','observation_received','stopped'].includes(r.event))&&rows.at(-1).event==='stopped'&&['execution_error','bridge_not_current','target_not_ready'].includes(rows.at(-1).reason),'preinput_resume_not_proven');
    const observations=rows.slice(0,-1);
    requireThat(observations.length%2===0&&observations.every((r,i)=>r.event===(i%2?'observation_received':'observation_requested')&&Number.isFinite(Date.parse(r.at))&&(i===0||Date.parse(r.at)>=Date.parse(observations[i-1].at))),'preinput_audit_incomplete');
    requireThat(observations.filter((_,i)=>i%2).every(r=>/^[a-f0-9]{64}$/.test(r.ax_sha256)&&/^[a-f0-9]{64}$/.test(r.image_sha256)),'preinput_hash_missing');
    claim=await fs.open(path.join(dir,entryKey+'.preinput-resume.json'),'wx',0o600);
    await claim.writeFile(JSON.stringify({identity:plan.identity,capture_job_id:plan.capture_job_id,original_claim:entryKey,prior_audit_sha256:sha(audit),reason:'zero_dispatch_window_binding_repaired',claimed_at:new Date().toISOString()})+'\n');
    await claim.sync();await claim.close();return;
  }
  try{await claim.writeFile(JSON.stringify({identity:plan.identity,capture_job_id:plan.capture_job_id,entry_key:entryKey,plan_sha256:sha(await fs.readFile(planPath)),claimed_at:new Date().toISOString()})+'\n');await claim.sync();}finally{await claim.close();}
}

export async function runAtomicCourseAllow({app,planPath,emit=()=>{},resumePreinput=false}) {
  const plan=await json(planPath);await validatePlan(plan);await networkProof(plan);await claimExecution(planPath,plan,{resumePreinput});
  const audit=path.resolve(planPath)+'.events.jsonl';
  const record=async event=>{
    const row={...event,identity:plan.identity,capture_job_id:plan.capture_job_id};
    const file=await fs.open(audit,'a',0o600);
    try{await file.writeFile(JSON.stringify(row)+'\n');await file.sync();}finally{await file.close();}
    emit('KOL_ATOMIC_EVENT '+JSON.stringify(row)+'\n');
  };
  const result=await runOpenAllow({app,recognize:visionRecognizer(plan.vision_binary),record,beforeAllow:()=>networkProof(plan,true),beforeInput:createInputWindowGuard(frame=>requireInputWindow(plan,frame))});
  return {...result,identity:plan.identity,capture_job_id:plan.capture_job_id,audit_sha256:sha(await fs.readFile(audit)),audit_path:audit};
}

/** Before issuing an entry, prepare one exact visible Cancel on the original job. */
export async function prepareStaleBridgeReset({app,planPath,emit=()=>{}}) {
  const plan=await json(planPath);await validatePlan(plan,{requireEntry:false});await networkProof(plan);
  const audit=path.resolve(planPath)+'.reset-events.jsonl';
  const record=async event=>{
    const row={...event,identity:plan.identity,capture_job_id:plan.capture_job_id};
    const file=await fs.open(audit,'a',0o600);
    try{await file.writeFile(JSON.stringify(row)+'\n');await file.sync();}finally{await file.close();}
    emit('KOL_RESET_EVENT '+JSON.stringify(row)+'\n');
  };
  const prepared=await prepareStaleConfirmationReset({app,recognize:visionRecognizer(plan.vision_binary),record});
  const presenceFrame={state:'Window: \"草料二维码\", App: 微信.',ocr:{width:prepared.frame_width,height:prepared.frame_height}};
  const windowProof=await requireInputWindow(plan,presenceFrame);
  const dir=path.join(plan.repo_root,'output/live/kol_native_atomic/claims');await fs.mkdir(dir,{recursive:true,mode:0o700});
  const claimPath=path.join(dir,plan.capture_job_id+'.stale-confirmation-reset.json');
  const claim=await fs.open(claimPath,'wx',0o600);
  try{await claim.writeFile(JSON.stringify({...prepared,identity:plan.identity,capture_job_id:plan.capture_job_id,
    plan_path:path.resolve(planPath),window_id:windowProof.window_id,plan_sha256:sha(await fs.readFile(planPath))})+'\n');await claim.sync();}finally{await claim.close();}
  return {...prepared,identity:plan.identity,capture_job_id:plan.capture_job_id,claim_path:claimPath};
}

/** Dispatch exactly the prepared Cancel. The caller reads back in its next CUA call. */
export async function cancelPreparedStaleBridgeReset({app,reset}) {
  await requireNativeEntryEnabled(runtimeRepoRoot);
  requireThat(/^kol-[a-f0-9]{12}$/.test(reset?.capture_job_id),'reset_capture_invalid');
  const claimPath=path.join(runtimeRepoRoot,'output/live/kol_native_atomic/claims',reset.capture_job_id+'.stale-confirmation-reset.json');
  requireThat(path.resolve(reset.claim_path)===claimPath,'reset_claim_path_invalid');
  const claim=await json(claimPath);
  requireThat(recent(claim.prepared_at,30000),'reset_preparation_expired');
  requireThat(claim.prepared_at===reset.prepared_at&&JSON.stringify(claim.cancel_point)===JSON.stringify(reset.cancel_point)
    &&claim.identity===reset.identity&&claim.capture_job_id===reset.capture_job_id
    &&claim.frame_sha256===reset.frame_sha256,'reset_claim_changed');
  const plan=await json(claim.plan_path);
  requireThat(sha(await fs.readFile(claim.plan_path))===claim.plan_sha256,'reset_plan_changed');
  await requireInputWindow(plan,{state:'Window: \"草料二维码\", App: 微信.',ocr:{width:claim.frame_width,height:claim.frame_height}},claim.window_id);
  const dispatch=await fs.open(claimPath+'.dispatch','wx',0o600);
  try{await dispatch.writeFile(JSON.stringify({claimed_at:new Date().toISOString(),claim_sha256:sha(await fs.readFile(claimPath))})+'\n');await dispatch.sync();}finally{await dispatch.close();}
  await app.click(claim.cancel_point);
  return {status:'cancel_dispatched',identity:claim.identity,capture_job_id:claim.capture_job_id,media_accepted:false};
}
