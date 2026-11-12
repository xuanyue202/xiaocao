"""Bind a normally authorized recorded course to an existing unbound capture."""
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from .capture import canonical_xiaoetong_source
from .enrichment_types import EnrichmentError
from .replay_catalog import ReplayCatalogConfig, match_original, verify_original


RECORDED_MEDIA_HOSTS = {
    "encrypt-k-vod.xet.tech",
    "t-vod.h5.xed.plus",
}


def resource_hash(url):
    p = urlsplit(str(url))
    return hashlib.sha256(urlunsplit((p.scheme,p.netloc,p.path,'','')).encode()).hexdigest()


def _evidence(root, since, path):
    result = None
    for line in (root/'events.jsonl').open():
        e = json.loads(line)
        u = urlsplit(str(e.get('url','')))
        if (e.get('kind') != 'response.body' or e.get('status') != 200
            or datetime.fromisoformat(e['at']) < since or u.path != path
            or u.hostname != 'appsnm3rlcp3566.h5.xiaoeknow.com'):
            continue
        p = Path(e['file']).resolve()
        if not p.is_relative_to(root/'json') or not p.is_file() or p.stat().st_size > 2*1024*1024:
            raise EnrichmentError('recorded response evidence path invalid')
        body = p.read_bytes()
        value = json.loads(body)
        if value.get('code') != 0 or not isinstance(value.get('data'),dict):
            raise EnrichmentError('recorded response rejected')
        result = (value['data'],{'path':str(p),'sha256':hashlib.sha256(body).hexdigest()})
    if result is None:
        raise EnrichmentError('recorded response evidence missing')
    return result


def _strings(value):
    if isinstance(value,str):
        yield value
    elif isinstance(value,dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value,list):
        for v in value:
            yield from _strings(v)


def collect_recorded_proof(subscription_dir, identity, capture_id, candidate_id, *,
                           player_duration, player_left, driver, observation_path):
    root = Path(subscription_dir).resolve()
    item = json.loads((root/'manifest.json').read_text())['items'][identity]
    from .xiaocao_wechat import WechatCliHistoryReader, parse_xiaocao_live_messages
    originals=parse_xiaocao_live_messages(WechatCliHistoryReader()())
    verify_original(item,identity,originals)
    config = ReplayCatalogConfig.from_dict(json.loads((root.parent/'native_share_bridge.json').read_text())['replay_catalog'])
    from .replay_catalog import verify_catalogue_binding
    verify_catalogue_binding(config,item,originals)
    if item['capture_job_id'] != capture_id:
        raise EnrichmentError('recorded original capture changed')
    observation_path=Path(observation_path).resolve()
    if not observation_path.is_relative_to(root/'items'/identity):
        raise EnrichmentError('recorded observation outside original')
    claim_body=observation_path.read_bytes()
    claim = json.loads(claim_body)
    if claim.get('identity')!=identity or claim.get('capture_job_id')!=capture_id:
        raise EnrichmentError('recorded observation changed original')
    since = datetime.fromisoformat(claim['observed_after'])
    service = driver._service(identity)
    debug = (service.sniffer_binary.parent/'elive_live_debug').resolve()
    catalog, catalog_file = _evidence(debug,since,'/xe.course.business_go.avoidlogin.e_course.resource_catalog_list.get/1.0.0')
    detail, detail_file = _evidence(debug,since,'/xe.course.business_go.video.detail_info.get/2.0.0')
    play, play_file = _evidence(debug,since,'/xe.material-center.play/getPlayUrl')
    if catalog.get('subscribe') != 1 or catalog.get('available') != 1:
        raise EnrichmentError('normal course entitlement not verified')
    info = detail.get('video_info') or {}
    play_sign = info.get('play_sign')
    play_block = play.get(play_sign) if isinstance(play_sign,str) and play_sign else None
    if (not isinstance(play_block,dict) or not info.get('material_id')
        or play_block.get('material_id')!=info['material_id']):
        raise EnrichmentError('recorded detail/play response mapping missing')
    rows = [dict(title=r.get('chapter_title'),resource_id=r.get('chapter_id'),
            duration_seconds=r.get('video_length'),course_id=r.get('course_id')) for r in catalog.get('list',[])]
    selected = match_original(rows,item['published_at'])
    if (not selected or selected['resource_id'] != claim['resource_id']
        or selected['course_id'] != config.course_id or info.get('app_id') != config.app_id
        or info.get('resource_id') != selected['resource_id']
        or info.get('video_length') != selected['duration_seconds']
        or not math.isfinite(player_duration) or abs(player_duration-selected['duration_seconds']) > 1
        or player_left is not True):
        raise EnrichmentError('recorded browser/course binding invalid')
    candidates = [r for r in service.sniffer.candidates() if r.get('id') == candidate_id]
    if len(candidates) != 1:
        raise EnrichmentError('recorded candidate ambiguous')
    c = candidates[0]; u=urlsplit(str(c.get('url','')))
    captured=datetime.fromisoformat(c['captured']).replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    # Candidate IDs retain their first-seen time across singleton restarts.
    # Freshness comes from a new exact merchant/play/HLS response, not that clock.
    if (not datetime.fromisoformat(item['published_at']) < captured < since+timedelta(hours=1)
        or c.get('media_type') != 'm3u8'
        or c.get('source_url') != config.origin+'/xe.material-center.play/getPlayUrl'
        or u.scheme != 'https' or u.netloc not in RECORDED_MEDIA_HOSTS
        or u.username is not None or u.password is not None
        or not re.fullmatch(r'v\.f[0-9]+\.m3u8',Path(u.path).name)):
        raise EnrichmentError('recorded candidate source invalid')
    file_ids=[m.group(1) for part in u.path.split('/') if (m:=re.fullmatch(r'[0-9a-f]{8}([0-9]{8,})',part))]
    sha=resource_hash(c['url'])
    if len(file_ids)!=1 or not any(resource_hash(v)==sha for v in _strings(play_block) if v.startswith('https://')):
        raise EnrichmentError('recorded merchant media mapping missing')
    finite = None
    for line in (debug/'events.jsonl').open():
        e=json.loads(line)
        if (e.get('kind')!='response.body' or e.get('status')!=200
            or resource_hash(e.get('url',''))!=sha or datetime.fromisoformat(e['at'])<max(captured,since)):continue
        p=Path(e['file']).resolve()
        if not p.is_relative_to(debug/'m3u8') or p.stat().st_size>2*1024*1024:continue
        body=p.read_bytes(); text=body.decode(); durations=[float(x) for x in re.findall(r'#EXTINF:([0-9.]+)',text)]
        if (text.startswith('#EXTM3U') and text.strip().endswith('#EXT-X-ENDLIST')
            and '#EXT-X-PLAYLIST-TYPE:EVENT' not in text and durations
            and all(math.isfinite(v) and v>0 for v in durations)
            and abs(sum(durations)-player_duration)<1):
            finite={'path':str(p),'sha256':hashlib.sha256(body).hexdigest(),
                    'duration_seconds':sum(durations),'segments':len(durations),'ended':True}
    if finite is None:raise EnrichmentError('recorded finite media evidence unavailable')
    return dict(identity=identity,capture_job_id=capture_id,source_message_sha256=item['message_sha256'],
        published_at=item['published_at'],recording=selected,app_id=config.app_id,
        candidate_id=candidate_id,media_file_id=file_ids[0],media_resource_sha256=sha,
        material_id=info['material_id'],play_sign_sha256=hashlib.sha256(play_sign.encode()).hexdigest(),
        observed_after=since.isoformat(),player_duration_seconds=player_duration,player_left=True,
        observation_receipt_path=str(observation_path),
        observation_receipt_sha256=hashlib.sha256(claim_body).hexdigest(),
        entitled_course=True,catalog_evidence=catalog_file,detail_evidence=detail_file,
        play_evidence=play_file,finite_playlist=finite,method='authorized_recorded_course_web')


def validate_recorded_proof(proof, item, capture_id):
    recording=proof.get('recording') or {}; published=datetime.fromisoformat(item['published_at'])
    if (proof.get('identity')!=item['identity'] or proof.get('capture_job_id')!=capture_id
        or proof.get('source_message_sha256')!=item['message_sha256']
        or proof.get('published_at')!=item['published_at'] or proof.get('entitled_course') is not True
        or proof.get('player_left') is not True or proof.get('method')!='authorized_recorded_course_web'
        or match_original([recording],item['published_at'])!=recording
        or not re.fullmatch(r'v_[0-9a-f]{24}',str(recording.get('resource_id','')))
        or not re.fullmatch(r'[0-9]{8,}',str(proof.get('media_file_id','')))
        or not re.fullmatch(r'[0-9a-f]{64}',str(proof.get('media_resource_sha256','')))
        or (proof.get('finite_playlist') or {}).get('ended') is not True
        or abs(proof['finite_playlist']['duration_seconds']-recording['duration_seconds'])>1):
        raise EnrichmentError('recorded proof differs from original')
    if published.tzinfo is None:raise EnrichmentError('recorded original timestamp naive')


def bind_recorded_recovery(subscription_dir,identity,capture_id,proof_path,*,driver):
    root=Path(subscription_dir).resolve(); path=proof_path.resolve()
    if not path.is_relative_to(root/'items'/identity):raise EnrichmentError('recorded proof outside original')
    body=path.read_bytes();proof=json.loads(body)
    from .xiaocao_wechat import XiaocaoWechatLiveSubscription, WechatCliHistoryReader, parse_xiaocao_live_messages
    history=WechatCliHistoryReader();sub=XiaocaoWechatLiveSubscription(root,history_reader=history,
        browser_exchange=lambda _:None,capture_driver=driver)
    manifest=sub._load();item=manifest['items'][identity]
    verify_original(item,identity,parse_xiaocao_live_messages(history()))
    validate_recorded_proof(proof,item,capture_id)
    binding={**proof,'proof_path':str(path),'proof_sha256':hashlib.sha256(body).hexdigest()}
    service=driver._service(identity);current=service.capture_store.latest(capture_id)
    if (not current or item.get('capture_job_id')!=capture_id or item.get('human_playback_deferred')
        or item.get('status') in {'completed','handoff_ready'}):raise EnrichmentError('recorded recovery not eligible')
    if current.get('recorded_replay_binding') not in (None,binding):
        raise EnrichmentError('recorded recovery already bound differently')
    source=canonical_xiaoetong_source(f"https://{proof['app_id']}.h5.xiaoeknow.com/p/course/video/{proof['recording']['resource_id']}")
    if current.get('candidate'):
        if (current.get('recorded_replay_binding')!=binding
            or current.get('expected_source')!=source
            or current.get('expected_media_file_id')!=proof['media_file_id']
            or (current.get('candidate') or {}).get('id')!=proof['candidate_id']
            or current.get('candidate_key')!='id:'+proof['candidate_id']):
            raise EnrichmentError('recorded existing candidate binding differs')
        if current.get('status')!='captured':
            return dict(status='recorded_source_already_bound',identity=identity,capture_job_id=capture_id)
    if not current.get('candidate'):
        reconstructed=collect_recorded_proof(root,identity,capture_id,proof['candidate_id'],
            player_duration=proof['player_duration_seconds'],player_left=proof['player_left'],driver=driver,
            observation_path=proof['observation_receipt_path'])
        if reconstructed != proof:
            raise EnrichmentError('recorded proof differs from current merchant evidence')
        if current.get('recorded_replay_binding') is None:
            driver.require_idle_human_entry(identity,capture_id)
        elif (current.get('status')!='awaiting_capture' or current.get('download_task_id')
            or current.get('expected_source')!=source
            or current.get('expected_media_file_id')!=proof['media_file_id']):
            raise EnrichmentError('recorded partial binding changed')
        for key in ('catalog_evidence','detail_evidence','play_evidence','finite_playlist'):
            p=Path(proof[key]['path']).resolve()
            debug=(service.sniffer_binary.parent/'elive_live_debug').resolve()
            if not p.is_relative_to(debug) or hashlib.sha256(p.read_bytes()).hexdigest()!=proof[key]['sha256']:
                raise EnrichmentError('recorded evidence changed')
        candidate=next((r for r in service.sniffer.candidates() if r.get('id')==proof['candidate_id']),None)
        if not candidate or resource_hash(candidate.get('url'))!=proof['media_resource_sha256']:
            raise EnrichmentError('recorded exact candidate changed')
        current=service.capture_store.transition(current,'recorded_course_source_bound',
            expected_source=source,expected_media_file_id=proof['media_file_id'],recorded_replay_binding=binding)
        title=proof['recording']['title'];day=datetime.fromisoformat(item['published_at']).strftime('%Y%m%d')
        candidate={**candidate,'live_id':str(candidate.get('live_id') or ''),'title':title,'filename':f'{day} {title}.mp4'}
        current=service.capture_store.bind_source_candidate(current,[candidate],candidate_id=proof['candidate_id'])
        if current is None:raise EnrichmentError('recorded candidate binding failed')
    sub._transition(manifest,item,'playback_activated',activated=True,media_request_observed=True,
        playback_surface='authorized_recorded_course_web',observed_page_state='recorded_course_playable',
        source_identity=current['expected_source']['source_identity'],
        source_resource_id=proof['recording']['resource_id'],candidate_id=proof['candidate_id'],
        recorded_replay_binding=binding,playback_window_cleanup_owner='browser',user_action_required=False)
    return dict(status='recorded_source_bound',identity=identity,capture_job_id=capture_id,
                candidate_id=proof['candidate_id'],download_started=False)


def restart_recorded_backend(subscription_dir,identity,capture_id,proof_path,replacement,*,driver):
    root=Path(subscription_dir).resolve()
    proof_path=Path(proof_path).resolve()
    if not proof_path.is_relative_to(root/'items'/identity):
        raise EnrichmentError('recorded proof outside original')
    item=json.loads((root/'manifest.json').read_text())['items'][identity]
    proof=json.loads(proof_path.read_text())
    validate_recorded_proof(proof,item,capture_id)
    service=driver._service(identity)
    current=service.capture_store.latest(capture_id)
    if current.get('recorded_replay_binding'):
        _require_unexecuted_recorded_claim(current,proof_path,service)
        from .xiaocao_wechat import WechatCliHistoryReader, parse_xiaocao_live_messages
        verify_original(item,identity,parse_xiaocao_live_messages(WechatCliHistoryReader()()))
    else:
        driver.require_idle_human_entry(identity,capture_id)
        reconstructed=collect_recorded_proof(root,identity,capture_id,proof['candidate_id'],
            player_duration=proof['player_duration_seconds'],player_left=proof['player_left'],
            driver=driver,observation_path=proof['observation_receipt_path'])
        if reconstructed!=proof:
            raise EnrichmentError('recorded repair proof differs from merchant evidence')
        if any(t.get('status') in {'running','ready','wait'} for t in service.sniffer.tasks()):
            raise EnrichmentError('active tasks block recorded backend deployment')
    result=service._replace_sniffer_for_repair(current,replacement_binary=replacement,preserve_native_arm=True)
    from .human_playback import enable_capture_listener_pac
    enable_capture_listener_pac()
    return result


def _require_unexecuted_recorded_claim(current,proof_path,service):
    binding=current.get('recorded_replay_binding') or {}
    if (current.get('status')!='download_claimed' or current.get('download_task_id')
        or str(proof_path.resolve())!=binding.get('proof_path')
        or hashlib.sha256(proof_path.read_bytes()).hexdigest()!=binding.get('proof_sha256')
        or current.get('candidate_key')!='id:'+str(binding.get('candidate_id'))
        or current.get('expected_source')!=canonical_xiaoetong_source(f"https://{binding['app_id']}.h5.xiaoeknow.com/p/course/video/{binding['recording']['resource_id']}")
        or current.get('expected_media_file_id')!=binding.get('media_file_id')):
        raise EnrichmentError('recorded download claim is not unexecuted')
    tasks=service.sniffer.complete_tasks_for_reconciliation()
    claimed=datetime.fromisoformat(binding['observed_after'])
    for task in tasks:
        meta=task.get('meta') or {};labels=meta.get('labels') or (meta.get('req') or {}).get('labels') or {}
        if (labels.get('capture_id')==binding['candidate_id']
            or resource_hash((meta.get('req') or {}).get('url',''))==binding['media_resource_sha256']
            or task.get('status') in {'running','ready','wait'}
            or (not labels.get('capture_id') and datetime.fromisoformat(task['createdAt'])>=claimed)):
            raise EnrichmentError('recorded provider effect requires reconciliation')
    return tasks


def refresh_recorded_ticket(subscription_dir,identity,capture_id,proof_path,*,driver):
    root=Path(subscription_dir).resolve();path=Path(proof_path).resolve()
    if not path.is_relative_to(root/'items'/identity):raise EnrichmentError('recorded proof outside original')
    proof=json.loads(path.read_text());item=json.loads((root/'manifest.json').read_text())['items'][identity]
    validate_recorded_proof(proof,item,capture_id)
    service=driver._service(identity);current=service.capture_store.latest(capture_id)
    binding=current.get('recorded_replay_binding') or {}
    _require_unexecuted_recorded_claim(current,Path(binding['proof_path']),service)
    keys=('identity','capture_job_id','source_message_sha256','published_at','recording','app_id','media_file_id','media_resource_sha256','material_id')
    if any(proof.get(k)!=binding.get(k) for k in keys):
        raise EnrichmentError('recorded ticket changed source or media')
    reconstructed=collect_recorded_proof(root,identity,capture_id,proof['candidate_id'],
        player_duration=proof['player_duration_seconds'],player_left=proof['player_left'],driver=driver,
        observation_path=proof['observation_receipt_path'])
    if reconstructed!=proof:raise EnrichmentError('recorded fresh ticket proof differs')
    return service.capture_store.transition(current,'recorded_ticket_refreshed',
        recorded_ticket_refresh={**proof,'proof_path':str(path),'proof_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
