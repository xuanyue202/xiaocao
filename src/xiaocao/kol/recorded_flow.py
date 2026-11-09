"""Catalogue-first local acquisition; the native room route stays archived."""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .enrichment_types import EnrichmentError, EnrichmentDiagnosticError
from .human_playback import enable_capture_listener_pac
from .recorded_recovery import bind_recorded_recovery, collect_recorded_proof
from .replay_catalog import ReplayCatalogConfig, inspect_original, verify_original


def recorded_mode(config_path):
    if not config_path.exists():
        return False
    try:
        config=json.loads(config_path.read_text())
        if not isinstance(config,dict):raise ValueError('invalid root')
        value=config.get('replay_catalog',{})
        if not isinstance(value,dict):raise ValueError('invalid catalogue')
    except (OSError,ValueError,TypeError) as exc:
        raise EnrichmentDiagnosticError('native entry configuration unreadable',category='contract_error',
            code='native_entry_configuration_unreadable',stage='native_entry') from exc
    mode=value.get('acquisition_mode','native_human')
    if mode not in {'recorded_course','native_human'}:
        raise EnrichmentError('unknown recorded acquisition mode')
    return mode=='recorded_course'


def annotate_inventory(originals,config_path):
    """A configured, explicitly labelled history link is navigation inventory."""
    if not recorded_mode(config_path):return originals
    value=json.loads(config_path.read_text())['replay_catalog']
    config=ReplayCatalogConfig.from_dict(value)
    navigation=value.get('navigation_source_url')
    if not navigation:return originals
    for row in originals:
        peers=[p for p in originals if p.get('entry_kind')=='wechat_mini_program'
            and p.get('mini_program_name')=='见势擒龙团'
            and p.get('message_sha256')==row.get('message_sha256')
            and p.get('published_at')==row.get('published_at')
            and p.get('contact_username')==row.get('contact_username')]
        if (row.get('recorded_navigation_marker') and row.get('source_url')==navigation
            and row.get('recorded_navigation_url_sha256')==hashlib.sha256(navigation.encode()).hexdigest()
            and len(peers)==1 and peers[0].get('mini_program_token')==config.mini_program_token):
            row.update(recorded_inventory_reason='catalogue_navigation',alternate_entry_of=peers[0]['identity'])
    return originals


def check_recorded_playback(sub,manifest,item,*,reason):
    if item.get('activated') is True or reason=='captured_window_cleanup' or item.get('human_playback_deferred'):
        return item
    root=sub.output_dir.resolve();identity=item['identity'];capture_id=item['capture_job_id']
    config=ReplayCatalogConfig.from_dict(json.loads((root.parent/'native_share_bridge.json').read_text())['replay_catalog'])
    from .xiaocao_wechat import parse_xiaocao_live_messages
    verify_original(item,identity,parse_xiaocao_live_messages(sub.history_reader()))
    now=sub.clock().astimezone(ZoneInfo('Asia/Shanghai'))
    published=datetime.fromisoformat(item['published_at']).astimezone(now.tzinfo)
    earliest=published.replace(hour=11 if published.hour<12 else 21,minute=0,second=0,microsecond=0)
    if item.get('announced_start_at'):
        earliest=max(earliest,datetime.fromisoformat(item['announced_start_at']).astimezone(now.tzinfo))
    def wait(code,deadline):
        return sub._transition(manifest,item,'awaiting_playback',acquisition_mode='recorded_course',
            recorded_catalog_state=code,recorded_next_poll_at=deadline.isoformat())
    if now<earliest:
        return wait('replay_check_not_due',earliest)
    due=item.get('recorded_next_poll_at')
    if due and now<datetime.fromisoformat(due):
        return item
    service=sub.capture_driver._service(identity)
    current=service.capture_store.latest(capture_id) or {}
    binding=current.get('recorded_replay_binding')
    if binding:
        bind_recorded_recovery(root,identity,capture_id,Path(binding['proof_path']),driver=sub.capture_driver)
        manifest.update(sub._load())
        return manifest['items'][identity]
    # A bound effect cannot be replaced by a catalogue result.
    sub.capture_driver.require_idle_human_entry(identity,capture_id)
    result=inspect_original(config,item,now=now)
    recording=result.get('recording')
    if not recording:
        return wait('recording_not_published',now+timedelta(seconds=300))
    sub.capture_driver.prepare_human_playback(identity,capture_id)
    enable_capture_listener_pac()
    folder=root/'items'/identity
    claim_path=folder/f'recorded-observation-{sub.human_entry_session_id}.json'
    if claim_path.exists():
        claim=json.loads(claim_path.read_text())
        if (claim.get('identity')!=identity or claim.get('capture_job_id')!=capture_id
            or claim.get('resource_id')!=recording['resource_id']):
            raise EnrichmentError('recorded observation changed original')
    else:
        claim=dict(identity=identity,capture_job_id=capture_id,resource_id=recording['resource_id'],
            observed_after=now.isoformat())
        with claim_path.open('x') as f:json.dump(claim,f);f.write('\n')
    request=dict(event='daily_browser_input_required',adapter='xiaocao_wechat_live',
        action='observe_authorized_recorded_course',subscription_id=identity,capture_job_id=capture_id,
        recording=recording,observation_receipt_path=str(claim_path),
        course_url=f'{config.origin}/p/course/ecourse/{config.course_id}',
        recording_url=f"{config.origin}/p/course/video/{recording['resource_id']}?"+urlencode(dict(product_id=config.course_id,course_id=config.course_id)),
        instructions='仅用已登录Browser正常打开精确历史录制；核对日期标题和有限时长，捕获实际HTTP后离开播放器。不要操作微信或打开直播间，不导出票据。',
        required_response=dict(action='observe_authorized_recorded_course',subscription_id=identity,
            status='observed|account_login_required',
            candidate_id='exact observed candidate; omit when account login is required',
            player_duration_seconds='actual finite duration; omit when account login is required',
            player_left='true; omit when account login is required'))
    response=sub._exchange_browser(request,item)
    sub._validate_browser_response(request,response)
    if response.get('status')=='account_login_required':
        error=EnrichmentDiagnosticError(
            'recorded course account login is required',
            category='authentication_error',
            code='recorded_course_account_login_required',
            stage='recorded_course_authorization',
        )
        error.waiting_items=[dict(identity=identity,capture_job_id=capture_id,
            stage='recorded_course_authorization')]
        raise error
    sub.capture_driver.require_idle_human_entry(identity,capture_id)
    proof=collect_recorded_proof(root,identity,capture_id,response['candidate_id'],
        player_duration=response['player_duration_seconds'],player_left=response['player_left'],
        driver=sub.capture_driver,observation_path=claim_path)
    proof_path=claim_path.with_name(claim_path.name.replace('recorded-observation-','recorded-proof-'))
    if proof_path.exists():
        if json.loads(proof_path.read_text())!=proof:
            raise EnrichmentError('recorded retained proof changed')
    else:
        with proof_path.open('x') as f:json.dump(proof,f,ensure_ascii=False,indent=2);f.write('\n')
    bind_recorded_recovery(root,identity,capture_id,proof_path,driver=sub.capture_driver)
    manifest.update(sub._load())
    return manifest['items'][identity]
