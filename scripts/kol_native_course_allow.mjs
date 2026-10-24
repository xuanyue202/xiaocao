/** B1 → exact Allow → B2 in one CUA invocation; no UI outside the supplied App. */
import { createHash } from 'node:crypto';

const hash = value => createHash('sha256').update(value).digest('hex');
const normalize = text => text.normalize('NFKC').replace(/[\s|｜“”‘’"'、，,。.!！:：]/gu,'');
const blocked = [
  ['security_relogin', /为了你的账号安全|安全.*重新登录/u],
  ['authentication_required', /扫码登录|手机.*登录|请.*重新登录|微信登录|请登录|验证码/u],
  ['consent_required', /服务协议|用户协议|授权.*(?:位置|相机|麦克风|通讯录)/u],
];
function stop(reason) { const error = new Error(reason); error.safeReason=reason; throw error; }
function title(state) {return /^Window:\s*"([^"]*)"/m.exec(state)?.[1];}
function inspect(ocr,state) {
  if(!/^Window:\s*"[^"]*", App: 微信\./m.test(state))stop('wrong_native_app');
  if (!Number.isSafeInteger(ocr.width)||!Number.isSafeInteger(ocr.height)||ocr.width<=0||ocr.height<=0||!Array.isArray(ocr.lines))stop('invalid_ocr_frame');
  const text=ocr.lines.map(l=>l.text).join('\n');
  for(const [reason,pattern] of blocked)if(pattern.test(state+'\n'+text))stop(reason);
  if(/^Window:\s*""/m.test(state)&&/\(disabled\).*聊天/u.test(state))stop('empty_window_disabled_chat');
}
function unique(ocr,text) {
  const matches=ocr.lines.filter(l=>typeof l.text==='string'&&normalize(l.text)===text);
  if(matches.length!==1)stop('target_not_unique');
  const line=matches[0], b=line.bounding_box;
  if(!Number.isFinite(line.confidence)||line.confidence<.5)stop('target_recognition_uncertain');
  if(!Array.isArray(b)||b.length!==4||!b.every(Number.isFinite)||b[0]<0||b[1]<0||b[2]<=0||b[3]<=0||b[0]+b[2]>1.001||b[1]+b[3]>1.001)stop('invalid_target_geometry');
  return {point:[(b[0]+b[2]/2)*ocr.width,(1-b[1]-b[3]/2)*ocr.height],box:b};
}
function courseTarget(frame) {
  if(title(frame.state)!=='草料二维码')stop('bridge_not_current');
  if(frame.ocr.lines.some(l=>normalize(l.text).startsWith('即将打开')))stop('unexpected_existing_confirmation');
  return unique(frame.ocr,'见势擒龙团打开当前课程');
}
function allowTarget(frame) {
  if(title(frame.state)!=='草料二维码')stop('bridge_not_current');
  const heading=unique(frame.ocr,'即将打开见势擒龙团小程序');
  const allow=unique(frame.ocr,'允许'),cancel=unique(frame.ocr,'取消');
  if(heading.point[1]>=allow.point[1]||cancel.point[0]>=allow.point[0]||Math.abs(cancel.point[1]-allow.point[1])>frame.ocr.height*.03)stop('confirmation_geometry_mismatch');
  return allow;
}

/** Prepare one Cancel, never consume an unbound Allow or dispatch any input. */
export async function prepareStaleConfirmationReset({app,recognize,record,now=()=>new Date().toISOString()}) {
  const observe=async()=>{
    const frame=await app.getAXStateAndScreenshot({emit:false,disableDiffing:true});
    if(typeof frame.state!=='string'||!frame.screenshot?.length)stop('missing_current_frame');
    const ocr=await recognize(frame.screenshot);inspect(ocr,frame.state);
    const current={...frame,ocr};const allow=allowTarget(current);
    const cancel=unique(ocr,'取消');
    await record({schema_version:1,event:'stale_confirmation_observed',stage:'R0',at:now(),
      ax_sha256:hash(frame.state),image_sha256:hash(frame.screenshot),target_sha256:hash(JSON.stringify(cancel))});
    return {cancel,geometry_sha256:hash(JSON.stringify([unique(ocr,'即将打开见势擒龙团小程序'),allow,cancel])),frame_sha256:hash(frame.screenshot)};
  };
  const first=await observe(),second=await observe();
  if(first.geometry_sha256!==second.geometry_sha256)stop('confirmation_changed');
  return {status:'cancel_ready',cancel_point:second.cancel.point,frame_sha256:second.frame_sha256,
    prepared_at:now(),media_accepted:false};
}

export async function runOpenAllow({app,recognize,record,beforeAllow,now=()=>new Date().toISOString()}) {
  const started=performance.now();let stage='B0',current,postAllowReadRecovered=false,postAllowSent=false;
  const emit=async(event,fields={})=>record({schema_version:1,event,stage,at:now(),...fields});
  const observe=async()=>{
    await emit('observation_requested');
    let frame;
    try{frame=await app.getAXStateAndScreenshot({emit:false,disableDiffing:true});}catch(error){
      const message=String(error.message);
      const denied=/denied|forbidden|policy/i.test(message);
      const code=denied?'policy_denied':(['timeoutReached','noWindowsAvailable','windowNotFoundAtPosition'].find(c=>message.includes(c))??(message.includes('The user changed')?'app_target_changed':'observation_error'));
      await emit('observation_failed',{reported_error_code:code});
      // After B2 there are no more inputs: one same-App passive recovery only.
      if(stage==='B2'&&postAllowSent&&!postAllowReadRecovered&&!denied){postAllowReadRecovered=true;return observe();}
      stop(denied?'native_bridge_policy_denied':'native_readback_unavailable');
    }
    if(typeof frame.state!=='string'||!frame.screenshot?.length)stop('missing_current_frame');
    await emit('observation_received',{ax_sha256:hash(frame.state),image_sha256:hash(frame.screenshot)});
    const ocr=await recognize(frame.screenshot);
    try{inspect(ocr,frame.state);}catch(error){await emit('state_rejected',{reason:error.safeReason??'invalid_frame'});throw error;}
    return {...frame,ocr};
  };
  const click=async(target)=>{
    await emit('dispatch_requested',{target_sha256:hash(JSON.stringify(target))});
    try{await app.click(target.point);}catch(error){
      const code=['timeoutReached','noWindowsAvailable','windowNotFoundAtPosition'].find(c=>String(error.message).includes(c))??'unclassified_input_error';
      await emit('dispatch_unknown',{reported_error_code:code});
      // The call may have sent input: observe once; never repeat the input.
      try{await observe();}catch{/* Existing unknown dispatch remains durable. */}
      stop('native_input_uncertain');
    }
    await emit('dispatch_returned');
    if(stage==='B2')postAllowSent=true;
    return observe();
  };
  const waitForRender=async(frame,match)=>{
    const deadline=performance.now()+8000;
    for(let reads=0;;reads++){
      try{match(frame);return frame;}catch(error){
        if(!['target_not_unique','target_recognition_uncertain','confirmation_geometry_mismatch','brand_not_observed'].includes(error.safeReason))throw error;
        if(title(frame.state)!=='草料二维码')throw error;
        const headings=frame.ocr.lines.map(l=>normalize(l.text)).filter(t=>t.startsWith('即将打开'));
        if(headings.some(t=>t!=='即将打开见势擒龙团小程序'))stop('wrong_confirmation_brand');
        if(reads>=12||performance.now()>=deadline)stop('render_not_ready');
        frame=await observe();
      }
    }
  };
  try {
    current=await observe();const course=courseTarget(current);
    // Confirm a stable, fully rendered button using another current frame.
    current=await observe();const readyCourse=courseTarget(current);
    if(hash(JSON.stringify(course))!==hash(JSON.stringify(readyCourse)))stop('target_not_ready');
    stage='B1';current=await click(readyCourse);
    // Without the verified Allow boundary, capture PAC may have missed autoplay.
    if(title(current.state)==='见势擒龙团')stop('brand_opened_without_allow');
    current=await waitForRender(current,allowTarget);
    stage='PAC';await emit('checkpoint_requested');
    let checkpoint;try{checkpoint=await beforeAllow();}catch{stop('pac_checkpoint_failed');}
    if(checkpoint?.verified!==true)stop('pac_checkpoint_failed');
    await emit('checkpoint_verified',{proof_sha256:hash(JSON.stringify(checkpoint))});
    // PAC checks can take time. Re-read the exact prompt and geometry after them.
    stage='B2';current=await observe();const allow=allowTarget(current);current=await click(allow);
    current=await waitForRender(current,frame=>{if(title(frame.state)!=='见势擒龙团')stop('brand_not_observed');});
    return await finish();
  }catch(error){
    const result={status:'stopped',reason:error.safeReason??'execution_error',stage,elapsed_ms:Math.round(performance.now()-started)};
    await emit('stopped',result);return result;
  }
  async function finish(){
    const result={status:'brand_ready',stage,elapsed_ms:Math.round(performance.now()-started),media_accepted:false};
    await emit('completed',result);return result;
  }
}
