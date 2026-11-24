"""Read-only preflight for a stopped recorded-course checkpoint.

This module never resumes a task, mutates a checkpoint, or handles tickets.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from .enrichment_types import EnrichmentError, compressed_media_name


def _regular(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise EnrichmentError('recorded terminal evidence unavailable') from exc
    if not stat.S_ISREG(mode):
        raise EnrichmentError('recorded terminal evidence is not a regular file')


def _sha(path: Path) -> str:
    _regular(path)
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect_terminal_task(current: dict[str, Any], tasks: list[dict[str, Any]],
                          *, output_root: Path) -> dict[str, Any]:
    """Bind one stopped original task to unchanged local checkpoint evidence.

    Caller must obtain `tasks` via the complete provider-page reconciliation API.
    The result authorizes no provider action or reset.
    """
    binding = current.get('recorded_replay_binding') or {}
    recording = binding.get('recording') or {}
    candidate = current.get('candidate') or {}
    task_id = str(current.get('download_task_id') or '')
    cid = str(candidate.get('id') or '')
    resource = str(recording.get('resource_id') or '')
    file_id = str(binding.get('media_file_id') or '')
    if (current.get('status') != 'download_failed' or current.get('user_resume_required') is True
        or not task_id or not cid or current.get('candidate_key') != 'id:' + cid
        or binding.get('candidate_id') != cid or binding.get('capture_job_id') != current.get('job_id')
        or current.get('expected_media_file_id') != file_id
        or not re.fullmatch(r'v_[0-9a-f]{24}', resource)
        or not re.fullmatch(r'[0-9]{8,}', file_id)
        or (current.get('expected_source') or {}).get('source_resource_id') != resource
        or (binding.get('finite_playlist') or {}).get('ended') is not True):
        raise EnrichmentError('recorded terminal original binding invalid')
    if any(str(t.get('status') or '').lower() in {'running', 'ready', 'wait'} for t in tasks):
        raise EnrichmentError('active provider task blocks recorded terminal repair')
    found = [t for t in tasks if t.get('id') == task_id]
    if len(found) != 1:
        raise EnrichmentError('recorded terminal task is absent or ambiguous')
    task = found[0]
    meta = task.get('meta') or {}
    labels = meta.get('labels') or (meta.get('req') or {}).get('labels') or {}
    opts = meta.get('opts') or {}
    from urllib.parse import urlsplit
    from .recorded_recovery import RECORDED_MEDIA_HOSTS, resource_hash
    original_url=str((meta.get('req') or {}).get('url') or '')
    original_resource=urlsplit(original_url)
    if (original_resource.scheme!='https' or original_resource.netloc not in RECORDED_MEDIA_HOSTS
        or original_resource.username is not None or original_resource.password is not None or original_resource.fragment
        or resource_hash(original_url)!=binding.get('media_resource_sha256')):
        raise EnrichmentError('recorded terminal provider original resource changed')
    for other in tasks:
        if other is task:
            continue
        other_meta = other.get('meta') or {}
        other_req = other_meta.get('req') or {}
        other_labels = other_meta.get('labels') or other_req.get('labels') or {}
        other_opts = other_meta.get('opts') or {}
        other_url = str(other_req.get('url') or '')
        other_resource=urlsplit(other_url)
        same_resource = bool(other_url and other_resource.scheme=='https'
            and other_resource.netloc in RECORDED_MEDIA_HOSTS
            and other_resource.username is None and other_resource.password is None and not other_resource.fragment
            and other_resource.path==original_resource.path)
        if (other_labels.get('capture_id') == cid or same_resource
            or (other_labels.get('recorded_resource_id') == resource and other_labels.get('recorded_media_file_id') == file_id)
            or (opts.get('path') and opts.get('name') and other_opts.get('path') == opts.get('path') and other_opts.get('name') == opts.get('name'))):
            raise EnrichmentError('recorded terminal has another matching provider effect')
    if (task.get('status') not in {'pause', 'error'} or task.get('protocol') != 'stream'
        or labels.get('capture_id') != cid or labels.get('recorded_resource_id') != resource
        or labels.get('recorded_media_file_id') != file_id
        or labels.get('type') != 'live_capture' or labels.get('compress_inline') != 'true'
        or labels.get('checkpoint_basis') != 'verified_hls_segments'):
        raise EnrichmentError('recorded terminal provider binding invalid')
    directory = Path(str(opts.get('path') or ''))
    name = str(opts.get('name') or '')
    prior_opts = ((current.get('download_task') or {}).get('meta') or {}).get('opts') or {}
    if (not directory.is_absolute() or directory.resolve() != output_root.resolve()
        or str(prior_opts.get('path') or '') != str(directory) or prior_opts.get('name') != name
        or not name or Path(name).name != name or not name.endswith('-compressed.mp4')):
        raise EnrichmentError('recorded terminal output binding invalid')
    media = directory / name
    media_hash = _sha(media)
    cache = Path(str(media) + '.hls-cache')
    if cache.is_symlink() or not cache.is_dir():
        raise EnrichmentError('recorded terminal checkpoint unavailable')
    terminal, checkpoint = cache / 'terminal.json', cache / 'binding.json'
    _regular(terminal); _regular(checkpoint)
    try:
        if terminal.stat().st_size > 4096 or checkpoint.stat().st_size > 4096:
            raise ValueError('oversized checkpoint')
        terminal_value = json.loads(terminal.read_text())
        checkpoint_value = json.loads(checkpoint.read_text())
    except (OSError, ValueError, TypeError) as exc:
        raise EnrichmentError('recorded terminal checkpoint invalid') from exc
    segments = (binding.get('finite_playlist') or {}).get('segments')
    if (terminal_value not in ({'status': 401}, {'status': 403})
        or set(checkpoint_value) != {'Binding', 'Manifest', 'Segments'}
        or not all(re.fullmatch(r'[0-9a-f]{64}', str(checkpoint_value.get(k) or ''))
                   for k in ('Binding', 'Manifest'))
        or checkpoint_value.get('Manifest') != (binding.get('finite_playlist') or {}).get('sha256')
        or type(segments) is not int or checkpoint_value.get('Segments') != segments
        or str(labels.get('checkpoint_segments')) != str(segments)):
        raise EnrichmentError('recorded terminal checkpoint binding invalid')
    proofs = list(cache.glob('*.bin.json'))
    if len(proofs) > segments:
        raise EnrichmentError('recorded terminal checkpoint has extra proofs')
    for proof in proofs:
        _regular(proof)
        try:
            value = json.loads(proof.read_text())
        except (OSError, ValueError) as exc:
            raise EnrichmentError('recorded terminal segment proof invalid') from exc
        blob = Path(str(proof)[:-5])
        if (not re.fullmatch(r'[0-9a-f]{64}\.[a-zA-Z0-9]{1,8}\.bin', blob.name)
            or not isinstance(value, dict) or set(value) != {'sha256', 'size'}
            or type(value.get('size')) is not int or value['size'] <= 0):
            raise EnrichmentError('recorded terminal segment proof mismatch')
        blob_hash = _sha(blob)
        if blob.stat().st_size != value['size'] or blob_hash != value.get('sha256'):
            raise EnrichmentError('recorded terminal segment proof mismatch')
    return {'capture_job_id': current['job_id'], 'task_id': task_id, 'candidate_id': cid,
            'resource_id': resource, 'media_file_id': file_id, 'task_status': task['status'],
            'terminal_status': terminal_value['status'], 'partial_path': str(media), 'checkpoint_segments': segments,
            'verified_cached_segments': len(proofs), 'partial_size_bytes': media.stat().st_size,
            'partial_sha256': media_hash, 'checkpoint_binding_sha256': _sha(checkpoint),
            'terminal_sha256': _sha(terminal)}


def _verified_same_file_alias(service: Any, binding: dict[str, Any], proof: dict[str, Any]) -> dict[str, Any]:
    """Prove the merchant-issued alias retains the exact path and original file."""
    from urllib.parse import urlsplit
    from .recorded_recovery import RECORDED_MEDIA_HOSTS, resource_hash
    keys=('identity','capture_job_id','source_message_sha256','published_at','recording',
          'app_id','media_file_id','material_id')
    if any(proof.get(k)!=binding.get(k) for k in keys):
        raise EnrichmentError('recorded terminal alias changed original source or file')
    rows=service.sniffer.candidates()
    original=[row for row in rows if row.get('id')==binding.get('candidate_id')]
    alias=[row for row in rows if row.get('id')==proof.get('candidate_id')]
    if len(original)!=1 or len(alias)!=1:
        raise EnrichmentError('recorded terminal alias candidate is ambiguous')
    old, new=original[0],alias[0]
    old_url,new_url=str(old.get('url') or ''),str(new.get('url') or '')
    before,after=urlsplit(old_url),urlsplit(new_url)
    merchant=f"https://{binding['app_id']}.h5.xiaoeknow.com/xe.material-center.play/getPlayUrl"
    if (any(u.scheme!='https' or u.netloc not in RECORDED_MEDIA_HOSTS or u.username is not None
            or u.password is not None or u.fragment for u in (before,after))
        or not before.path or before.path!=after.path
        or old.get('media_type')!='m3u8' or new.get('media_type')!='m3u8'
        or old.get('source_url')!=merchant or new.get('source_url')!=merchant
        or old.get('source_path')!='/xe.material-center.play/getPlayUrl'
        or new.get('source_path')!='/xe.material-center.play/getPlayUrl'
        or resource_hash(old_url)!=binding.get('media_resource_sha256')
        or resource_hash(new_url)!=proof.get('media_resource_sha256')):
        raise EnrichmentError('recorded terminal alias host, path or merchant changed')
    return {'original_candidate_id':binding['candidate_id'],'alias_candidate_id':proof['candidate_id'],
            'original_resource_sha256':binding['media_resource_sha256'],
            'alias_resource_sha256':proof['media_resource_sha256'],
            'original_host':before.netloc,'alias_host':after.netloc,
            'provider_path_sha256':hashlib.sha256(before.path.encode()).hexdigest(),
            'media_file_id':binding['media_file_id'],'material_id':binding['material_id']}


def _durable_transition(store: Any, current: dict[str, Any], event: str, **changes: Any) -> dict[str, Any]:
    """Persist an exact claim before crossing a provider-effect boundary."""
    result = store.transition(current, event, **changes)
    path = Path(store.path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        actual = path.lstat()
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (actual.st_dev, actual.st_ino):
            raise EnrichmentError('recorded terminal claim ledger changed')
        os.fsync(fd)
    finally:
        os.close(fd)
    if store.latest(current['job_id']) != result:
        raise EnrichmentError('recorded terminal durable claim readback changed')
    return result


def _require_prior_absence_receipt(current: dict[str, Any], preflight: dict[str, Any]) -> None:
    prior = current.get('media_repair') or {}
    if not prior:
        return
    receipt = prior.get('absence_receipt') or {}
    backend = receipt.get('backend_restart_receipt') or {}
    known = (current.get('recorded_terminal_backend_receipt'),
             current.get('recorded_terminal_backend_followup_receipt'),
             current.get('recorded_terminal_backend_reconciled_followup_receipt'))
    if (prior.get('state') != 'absence_verified' or prior.get('preflight') != preflight
        or prior.get('prior_attempt') or receipt.get('preflight') != preflight
        or receipt.get('task_id') != preflight['task_id']
        or receipt.get('provider_revision_absent') is not True or receipt.get('task_reservation_absent') is not True
        or not backend or backend not in known or backend.get('capture_job_id') != preflight['capture_job_id']
        or backend.get('task_id') != preflight['task_id']):
        raise EnrichmentError('recorded terminal prior absence receipt changed')


def prepare_terminal_revision(service: Any, item: dict[str, Any], proof_path: Path,
                              *, output_root: Path) -> dict[str, Any]:
    """Prepare one retained terminal task after fresh same-file evidence.

    Call with the existing source slot held. The claim is durable before the
    backend reserves an output; an uncertain claim is never blindly resubmitted.
    """
    from .recorded_recovery import collect_recorded_proof, validate_recorded_proof
    from .xiaocao_wechat import XiaocaoLiveCaptureDriver
    identity = str(item.get('identity') or '')
    capture_id = str(item.get('capture_job_id') or '')
    current = service.capture_store.latest(capture_id)
    if not current or (current.get('media_repair') and current['media_repair'].get('state') != 'absence_verified'):
        raise EnrichmentError('recorded terminal revision already claimed; reconcile exact task')
    if any(current.get(k) for k in ('media_sha256','netdisk_job_id','handoff_id')):
        raise EnrichmentError('recorded terminal has downstream binding; reconcile first')
    if item.get('human_playback_deferred') or current.get('user_resume_required'):
        raise EnrichmentError('recorded terminal revision is deferred')
    proof_path = Path(proof_path)
    if proof_path.is_symlink():
        raise EnrichmentError('recorded terminal alias proof is a symlink')
    proof_path = proof_path.resolve()
    item_root = Path(service.output_dir).resolve()
    if not proof_path.is_relative_to(item_root) or not proof_path.is_file():
        raise EnrichmentError('recorded terminal alias proof outside original')
    proof = json.loads(proof_path.read_text())
    validate_recorded_proof(proof, item, capture_id)
    binding = current.get('recorded_replay_binding') or {}
    alias_binding = _verified_same_file_alias(service,binding,proof)
    driver = XiaocaoLiveCaptureDriver(item_root.parent.parent)
    driver._service = lambda _identity: service
    fresh = collect_recorded_proof(item_root.parent.parent, identity, capture_id,
        proof['candidate_id'], player_duration=proof['player_duration_seconds'],
        player_left=proof['player_left'], driver=driver,
        observation_path=proof['observation_receipt_path'])
    if fresh != proof:
        raise EnrichmentError('recorded terminal alias proof changed after observation')
    for event in ('media_validated','netdisk_prepared','netdisk_upload_claimed','cloud_handoff_claimed','cloud_handoff_published'):
        if service._event(event, capture_job_id=capture_id):
            raise EnrichmentError('recorded terminal has downstream effect; reconcile first')
    preflight = inspect_terminal_task(current, service.sniffer.complete_tasks_for_reconciliation(),
                                      output_root=output_root)
    _require_prior_absence_receipt(current, preflight)
    task_id = preflight['task_id']
    if (current.get('checkpoint_resume_claim') or {}).get('task_id') != task_id or (current.get('checkpoint_resume_receipt') or {}).get('id') != task_id:
        raise EnrichmentError('recorded prior checkpoint attempt is not reconciled')
    prior = {'state':'preparing', 'previous_media_path':preflight['partial_path'],
             'previous_media_sha256':preflight['partial_sha256'],
             'previous_media_size_bytes':preflight['partial_size_bytes'],
             'task_id':task_id, 'candidate_id':preflight['candidate_id'],
             'alias_candidate_id':proof['candidate_id'], 'alias_binding':alias_binding, 'proof_path':str(proof_path),
             'proof_sha256':_sha(proof_path), 'preflight':preflight}
    if current.get('media_repair'):
        prior['prior_attempt'] = current['media_repair']
    latest = service.capture_store.latest(capture_id)
    if latest != current:
        raise EnrichmentError('recorded terminal capture changed before claim')
    claimed = _durable_transition(service.capture_store,current, 'recorded_terminal_revision_claimed', media_repair=prior)
    receipt = service.sniffer.prepare_recorded_terminal_revision(task_id,
        candidate_id=preflight['candidate_id'], resource_id=preflight['resource_id'],
        media_file_id=preflight['media_file_id'], partial_sha256=preflight['partial_sha256'],
        manifest_sha256=binding['finite_playlist']['sha256'],
        resource_sha256=binding['media_resource_sha256'], checkpoint_binding_sha256=preflight['checkpoint_binding_sha256'],
        terminal_sha256=preflight['terminal_sha256'], alias_candidate_id=proof['candidate_id'])
    tasks = service.sniffer.complete_tasks_for_reconciliation()
    selected = [task for task in tasks if task.get('id') == task_id]
    task = selected[0] if len(selected) == 1 else {}
    meta = task.get('meta') or {}; labels = meta.get('labels') or (meta.get('req') or {}).get('labels') or {}
    opts = meta.get('opts') or {}; name = str(receipt.get('name') or '')
    if (any(t.get('status') in {'running','ready','wait'} for t in tasks)
        or task.get('status') != 'pause' or receipt.get('id') != task_id
        or receipt.get('previous_sha256') != preflight['partial_sha256']
        or receipt.get('previous_name') != Path(preflight['partial_path']).name
        or not re.fullmatch(r'[0-9a-f]{64}', str(receipt.get('revision') or ''))
        or labels.get('media_repair_revision') != receipt.get('revision')
        or labels.get('recorded_ticket_alias_id') != proof['candidate_id']
        or Path(name).name != name or not compressed_media_name(name) or name == receipt['previous_name']
        or opts.get('name') != name or Path(str(opts.get('path') or '')).resolve() != output_root.resolve()):
        raise EnrichmentError('recorded terminal prepared task readback changed')
    repair = {**prior, 'state':'prepared', 'backend_receipt':receipt,
              'revision':receipt['revision'], 'media_basename':name}
    return service.capture_store.transition(claimed,'recorded_terminal_revision_prepared',
                                            status='downloading',media_repair=repair)


def resume_terminal_revision(service: Any, capture_id: str) -> dict[str, Any]:
    """Claim and start the exact prepared provider task once, without pausing peers."""
    current = service.capture_store.latest(capture_id)
    repair = (current or {}).get('media_repair') or {}
    if not current or current.get('user_resume_required') or repair.get('state') not in {'prepared','resume_claimed','running'}:
        raise EnrichmentError('recorded terminal resume requires an unconsumed prepared revision')
    task_id, revision = str(repair.get('task_id') or ''), str(repair.get('revision') or '')
    tasks = service.sniffer.complete_tasks_for_reconciliation()
    exact = [task for task in tasks if task.get('id') == task_id]
    if len(exact) != 1:
        raise EnrichmentError('recorded terminal resume provider state is busy or ambiguous')
    if repair.get('state') in {'resume_claimed','running'}:
        task=exact[0]; meta=task.get('meta') or {}
        labels=meta.get('labels') or (meta.get('req') or {}).get('labels') or {}
        opts=meta.get('opts') or {}
        if (task.get('status') not in {'running','done'} or labels.get('media_repair_revision')!=revision
            or labels.get('capture_id')!=repair.get('candidate_id') or opts.get('name')!=repair.get('media_basename')):
            raise EnrichmentError('claimed recorded terminal resume requires exact effect reconciliation')
        if repair.get('state')=='running':
            return current
        return _durable_transition(service.capture_store,current,'recorded_terminal_resume_reconciled',
            status='downloading',media_repair={**repair,'state':'running',
                'resume_readback':{'id':task_id,'revision':revision,'status':task['status']}})
    if any(t.get('status') in {'running','ready','wait'} for t in tasks):
        raise EnrichmentError('recorded terminal resume provider state is busy or ambiguous')
    meta = exact[0].get('meta') or {}; labels = meta.get('labels') or (meta.get('req') or {}).get('labels') or {}
    if (exact[0].get('status') != 'pause' or labels.get('media_repair_revision') != revision
        or labels.get('capture_id') != repair.get('candidate_id')):
        raise EnrichmentError('recorded terminal resume provider binding changed')
    if service.capture_store.latest(capture_id) != current:
        raise EnrichmentError('recorded terminal capture changed before resume')
    claimed = _durable_transition(service.capture_store,current,'recorded_terminal_resume_claimed',
        media_repair={**repair,'state':'resume_claimed'})
    receipt = service.sniffer.start_recorded_terminal_revision(task_id, revision=revision)
    tasks = service.sniffer.complete_tasks_for_reconciliation()
    exact = [task for task in tasks if task.get('id') == task_id]
    if (receipt != {'id':task_id,'revision':revision} or len(exact) != 1
        or exact[0].get('status') not in {'running','done'}):
        raise EnrichmentError('recorded terminal resume needs exact provider reconciliation')
    return service.capture_store.transition(claimed,'recorded_terminal_download_started',
        status='downloading',media_repair={**repair,'state':'running','resume_receipt':receipt})


def _verify_terminal_original(sub: Any, item: dict[str, Any], current: dict[str, Any]):
    """Rejoin the original source, configured course and retained recording."""
    from .replay_catalog import ReplayCatalogConfig, verify_catalogue_binding, verify_original
    from .xiaocao_wechat import parse_xiaocao_live_messages, read_original_history
    identity, capture_id = str(item.get('identity') or ''), str(item.get('capture_job_id') or '')
    binding=current.get('recorded_replay_binding') or {}
    recording=binding.get('recording') or {}
    if (current.get('job_id')!=capture_id or current.get('source_subscription_id')!=identity
        or current.get('source_published_at')!=item.get('published_at')
        or current.get('source_message_sha256')!=item.get('message_sha256')
        or binding.get('identity')!=identity or binding.get('capture_job_id')!=capture_id
        or binding.get('published_at')!=item.get('published_at')
        or binding.get('source_message_sha256')!=item.get('message_sha256')):
        raise EnrichmentError('recorded terminal original source binding changed')
    originals=parse_xiaocao_live_messages(read_original_history(sub.history_reader,item['published_at']))
    verify_original(item,identity,originals)
    root=Path(sub.output_dir).resolve()
    config=ReplayCatalogConfig.from_dict(json.loads((root.parent/'native_share_bridge.json').read_text())['replay_catalog'])
    verify_catalogue_binding(config,item,originals)
    source=current.get('expected_source') or {}
    if (binding.get('app_id')!=config.app_id or recording.get('course_id')!=config.course_id
        or source.get('source_app_id')!=config.app_id
        or source.get('source_identity')!=f"xiaoetong:{config.app_id}:{recording.get('resource_id')}"):
        raise EnrichmentError('recorded terminal course binding changed')
    return config


def observe_terminal_alias(sub: Any, item: dict[str, Any], service: Any, *, output_root: Path) -> Path:
    """Observe a fresh authorized alias for one already-bound failed recording."""
    from datetime import datetime
    from urllib.parse import urlencode
    from zoneinfo import ZoneInfo
    from .human_playback import enable_capture_listener_pac
    from .recorded_flow import _validate_recorded_browser_response
    from .recorded_recovery import collect_recorded_proof
    from .replay_catalog import ReplayCatalogReader, match_original

    root = Path(sub.output_dir).resolve()
    identity, capture_id = str(item['identity']), str(item['capture_job_id'])
    current = service.capture_store.latest(capture_id)
    if (not current or item.get('human_playback_deferred') or
        (current.get('media_repair') and current['media_repair'].get('state') != 'absence_verified')):
        raise EnrichmentError('recorded terminal alias requires a reconciled original')
    preflight = inspect_terminal_task(current, service.sniffer.complete_tasks_for_reconciliation(), output_root=output_root)
    _require_prior_absence_receipt(current, preflight)
    binding = current.get('recorded_replay_binding') or {}
    config = _verify_terminal_original(sub,item,current)
    clock = sub.clock()
    published = datetime.fromisoformat(item['published_at'])
    if clock.tzinfo is None or published.tzinfo is None:
        raise EnrichmentError('recorded terminal timestamp is naive')
    now = clock.astimezone(ZoneInfo('Asia/Shanghai'))
    published = published.astimezone(now.tzinfo)
    earliest = published.replace(hour=11 if published.hour < 12 else 21,minute=0,second=0,microsecond=0)
    if item.get('announced_start_at'):
        announced = datetime.fromisoformat(item['announced_start_at'])
        if announced.tzinfo is None:
            raise EnrichmentError('recorded terminal announced timestamp is naive')
        earliest=max(earliest,announced.astimezone(now.tzinfo))
    if now < earliest:
        raise EnrichmentError('recorded terminal replay check is not due')
    reader = ReplayCatalogReader(config)
    try:
        selected = match_original(reader.read(), item['published_at'])
    finally:
        reader.session.close()
    old_recording = binding.get('recording') or {}
    recording_keys = ('title','resource_id','duration_seconds','course_id')
    if (not selected or any(selected.get(k) != old_recording.get(k) for k in recording_keys)
        or selected.get('resource_id') != preflight['resource_id']):
        raise EnrichmentError('recorded terminal catalogue changed original recording')
    enable_capture_listener_pac()
    folder = root/'items'/identity
    claim_path = folder/f'recorded-terminal-observation-{sub.human_entry_session_id}.json'
    claim = {'identity':identity,'capture_job_id':capture_id,'resource_id':selected['resource_id'],
             'observed_after':now.isoformat()}
    with claim_path.open('x') as f:
        json.dump(claim,f); f.write('\n'); f.flush(); os.fsync(f.fileno())
    request = dict(event='daily_browser_input_required',adapter='xiaocao_wechat_live',
        action='observe_authorized_recorded_course',subscription_id=identity,capture_job_id=capture_id,
        recording=selected,observation_receipt_path=str(claim_path),course_url=config.learning_url,
        recording_entry='catalogue_row',
        recording_url=f"{config.origin}/p/course/video/{selected['resource_id']}?"+urlencode(dict(product_id=config.course_id,course_id=config.course_id)),
        instructions='在已有授权的历史课程列表中打开精确日期和标题的录像，核对资源和有限时长并离开播放器；不要操作微信或导出票据。',
        required_response=dict(action='observe_authorized_recorded_course',subscription_id=identity,
            one_of=[dict(status='observed',candidate_id='non-empty string',player_duration_seconds='positive finite number',player_left=True),
                    dict(status='account_login_required')]))
    response = sub._exchange_browser(request,item)
    sub._validate_browser_response(request,response)
    _validate_recorded_browser_response(response)
    if response['status']=='account_login_required':
        from .enrichment_types import EnrichmentDiagnosticError
        exc = EnrichmentDiagnosticError('recorded course account login is required',category='authentication_error',
            code='recorded_course_account_login_required',stage='recorded_course_authorization')
        exc.waiting_items=[dict(identity=identity,capture_job_id=capture_id,stage='recorded_course_authorization')]
        raise exc
    fresh = service.capture_store.latest(capture_id)
    if fresh != current or inspect_terminal_task(fresh,service.sniffer.complete_tasks_for_reconciliation(),output_root=output_root)!=preflight:
        raise EnrichmentError('recorded terminal original changed after browser observation')
    proof=collect_recorded_proof(root,identity,capture_id,response['candidate_id'],
        player_duration=response['player_duration_seconds'],player_left=response['player_left'],
        driver=sub.capture_driver,observation_path=claim_path)
    _verified_same_file_alias(service,binding,proof)
    proof_path=folder/f'recorded-terminal-proof-{sub.human_entry_session_id}.json'
    with proof_path.open('x') as f:
        json.dump(proof,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    return proof_path


def _require_shared_backend_idle(service: Any) -> None:
    """Read only shared ownership; never initialize or drain another source."""
    import sqlite3
    from xiaocao.yangsheng.runtime import ENABLED, DEFAULT_ROOT
    from xiaocao.yangsheng.native import request
    if not ENABLED.is_file():
        return
    health=request(getattr(service.sniffer,'base_url','http://127.0.0.1:2022'),'/api/shared-capture/status')
    if health.get('enabled') is not True or health.get('post_processing_active') != []:
        raise EnrichmentError('shared backend processing is active or unverified')
    database=DEFAULT_ROOT/'catalog.sqlite'
    if not database.is_file() or database.is_symlink():
        raise EnrichmentError('shared backend ownership ledger is unavailable')
    connection=sqlite3.connect(f'file:{database}?mode=ro',uri=True,timeout=2)
    try:
        unresolved=connection.execute(
            'SELECT COUNT(*) FROM jobs j WHERE NOT EXISTS '
            '(SELECT 1 FROM artifacts a WHERE a.publisher=j.publisher AND a.replay=j.replay)'
        ).fetchone()[0]
    except sqlite3.Error as exc:
        raise EnrichmentError('shared backend ownership ledger cannot be verified') from exc
    finally:
        connection.close()
    if unresolved:
        raise EnrichmentError('shared backend has unfinished owned tasks')


def restart_terminal_backend(sub: Any, service: Any, item: dict[str, Any], *, output_root: Path,
                             replacement_binary: Path, replacement_sha256: str) -> dict[str, Any]:
    """Reconcile and replace the sole backend for this existing failed task."""
    from .xiaocao_live import _sha256_file
    from xiaocao.yangsheng.capture import lifecycle_lease
    capture_id=str(item.get('capture_job_id') or '')
    current=service.capture_store.latest(capture_id)
    if (not current or item.get('human_playback_deferred') or current.get('user_resume_required')
        or (current.get('media_repair') and current['media_repair'].get('state') not in {'preparing','absence_verified'})
        or not re.fullmatch(r'[0-9a-f]{64}',replacement_sha256)):
        raise EnrichmentError('recorded terminal backend repair is not eligible')
    _verify_terminal_original(sub,item,current)
    ready=service.start()
    if ready.get('capture_job_id')!=capture_id:
        raise EnrichmentError('recorded terminal backend resumed another capture')
    with lifecycle_lease(closing=True):
        current=service.capture_store.latest(capture_id)
        if (not current or current.get('user_resume_required') or
            (current.get('media_repair') and current['media_repair'].get('state') not in {'preparing','absence_verified'})):
            raise EnrichmentError('recorded terminal capture changed before backend repair')
        before=inspect_terminal_task(current,service.sniffer.complete_tasks_for_reconciliation(),output_root=output_root)
        if ((current.get('checkpoint_resume_claim') or {}).get('task_id')!=before['task_id']
            or (current.get('checkpoint_resume_receipt') or {}).get('id')!=before['task_id']):
            raise EnrichmentError('recorded checkpoint effect is not reconciled')
        for event in ('media_validated','netdisk_prepared','netdisk_upload_claimed','cloud_handoff_claimed','cloud_handoff_published'):
            if service._event(event,capture_job_id=capture_id):
                raise EnrichmentError('recorded terminal has downstream effect; reconcile first')
        _require_shared_backend_idle(service)
        installed=Path(service.sniffer_binary).resolve()
        if not installed.is_file():
            raise EnrichmentError('recorded terminal backend is unavailable')
        installed_sha=_sha256_file(installed)
        pending = (current.get('media_repair') or {}).get('state') == 'preparing'
        if pending:
            _check_absent_terminal_preparation(service,item,current,output_root=output_root)
            if installed_sha == replacement_sha256:
                raise EnrichmentError('pending recorded preparation requires a separately claimed backend restart')
        pairs = [('recorded_terminal_backend_claim','recorded_terminal_backend_receipt'),
                 ('recorded_terminal_backend_followup_claim','recorded_terminal_backend_followup_receipt'),
                 ('recorded_terminal_backend_reconciled_followup_claim','recorded_terminal_backend_reconciled_followup_receipt')]
        claim_field = receipt_field = None
        predecessor = None
        for claim_key, receipt_key in pairs:
            claim, receipt = current.get(claim_key), current.get(receipt_key)
            if not claim:
                claim_field, receipt_field = claim_key, receipt_key
                break
            if (claim.get('capture_job_id') != capture_id or claim.get('task_id') != before['task_id']
                or claim.get('preflight') != before):
                raise EnrichmentError('recorded terminal prior backend claim changed')
            if claim.get('replacement_sha256') == replacement_sha256:
                claim_field, receipt_field = claim_key, receipt_key
                if installed_sha not in {claim.get('previous_sha256'),replacement_sha256}:
                    raise EnrichmentError('recorded terminal backend identity changed')
                break
            if (not receipt or receipt.get('capture_job_id') != capture_id or receipt.get('task_id') != before['task_id']
                or receipt.get('backend_sha256') != claim.get('replacement_sha256')):
                raise EnrichmentError('recorded terminal prior backend effect is not reconciled')
            predecessor = claim
        if claim_field is None:
            raise EnrichmentError('recorded terminal backend repair chain exhausted')
        prior = current.get(claim_field)
        if not prior:
            if predecessor and installed_sha != predecessor['replacement_sha256']:
                raise EnrichmentError('recorded terminal prior backend identity changed')
            prior={'capture_job_id':capture_id,'task_id':before['task_id'],
                   'replacement_sha256':replacement_sha256,'previous_sha256':installed_sha,'preflight':before}
            current=_durable_transition(service.capture_store,current,'recorded_terminal_backend_claimed',
                                        **{claim_field:prior})
        if installed_sha!=replacement_sha256:
            replacement=Path(replacement_binary)
            if (replacement.is_symlink() or not replacement.is_file() or replacement.resolve().parent!=installed.parent
                or _sha256_file(replacement)!=replacement_sha256):
                raise EnrichmentError('recorded terminal replacement binary binding invalid')
            result=service._replace_sniffer_for_repair(current,replacement_binary=replacement,preserve_native_arm=True)
            if result.get('capture_job_id')!=capture_id or _sha256_file(installed)!=replacement_sha256:
                raise EnrichmentError('recorded terminal backend installation not verified')
        after=service.capture_store.latest(capture_id)
        again=inspect_terminal_task(after,service.sniffer.complete_tasks_for_reconciliation(),output_root=output_root)
        if again!=before:
            raise EnrichmentError('recorded terminal provider effect changed after backend restart')
        receipt={'capture_job_id':capture_id,'task_id':before['task_id'],'backend_sha256':replacement_sha256}
        if after.get(receipt_field) and after[receipt_field] != receipt:
            raise EnrichmentError('recorded terminal prior backend receipt changed')
        if not after.get(receipt_field):
            after=_durable_transition(service.capture_store,after,'recorded_terminal_backend_reconciled',
                                      **{receipt_field:receipt})
        if pending:
            _check_absent_terminal_preparation(service,item,after,output_root=output_root)
            repair=after['media_repair']
            _durable_transition(service.capture_store,after,'recorded_terminal_preparation_absence_verified',
                media_repair={**repair,'state':'absence_verified','absence_receipt':{
                    'task_id':before['task_id'],'preflight':before,'provider_revision_absent':True,
                    'task_reservation_absent':True,'backend_restart_receipt':receipt}})
        return {'status':'ready',**receipt,'preflight':before}


def _check_absent_terminal_preparation(service: Any, item: dict[str, Any], current: dict[str, Any], *, output_root: Path) -> None:
    """Record a proven absent reservation before a separate same-task attempt.

    Caller holds the source slot and exclusive lifecycle lease. This read-only
    check alone never proves an in-flight request is gone or permits a retry.
    """
    capture_id = str(item.get('capture_job_id') or '')
    repair = (current or {}).get('media_repair') or {}
    if (not current or current.get('status') != 'download_failed' or current.get('user_resume_required')
        or item.get('human_playback_deferred') or repair.get('state') != 'preparing'
        or repair.get('prior_attempt')):
        raise EnrichmentError('recorded terminal absence reconciliation is not eligible')
    tasks = service.sniffer.complete_tasks_for_reconciliation()
    preflight = inspect_terminal_task(current, tasks, output_root=output_root)
    if preflight != repair.get('preflight') or preflight['task_id'] != repair.get('task_id'):
        raise EnrichmentError('recorded terminal original task changed during absence reconciliation')
    task = next(t for t in tasks if t.get('id') == preflight['task_id'])
    meta = task.get('meta') or {}; labels = meta.get('labels') or (meta.get('req') or {}).get('labels') or {}
    if any(labels.get(key) for key in ('media_repair_revision','recorded_ticket_repair_revision','recorded_ticket_alias_id')):
        raise EnrichmentError('recorded terminal provider revision exists')
    for event in ('media_validated','netdisk_prepared','netdisk_upload_claimed','cloud_handoff_claimed','cloud_handoff_published'):
        if service._event(event,capture_job_id=capture_id):
            raise EnrichmentError('recorded terminal downstream effect requires reconciliation')
    # The backend creates an empty output before it writes the reservation
    # marker. A crash in that interval must never look like an absent effect.
    original = Path(preflight['partial_path'])
    duplicate = re.compile(re.escape(original.stem) + r' \([1-9][0-9]*\)' + re.escape(original.suffix) + r'$')
    for path in output_root.iterdir():
        if duplicate.fullmatch(path.name):
            raise EnrichmentError('recorded terminal unbound revision output exists')
    for marker in output_root.glob('*.reservation.json'):
        _regular(marker)
        if marker.stat().st_size > 4096:
            raise EnrichmentError('recorded terminal reservation cannot be reconciled')
        try:
            value = json.loads(marker.read_text())
        except (OSError, ValueError) as exc:
            raise EnrichmentError('recorded terminal reservation cannot be reconciled') from exc
        if not isinstance(value,dict) or not isinstance(value.get('task_id'),str):
            raise EnrichmentError('recorded terminal reservation cannot be reconciled')
        if value['task_id'] == preflight['task_id']:
            raise EnrichmentError('recorded terminal reservation exists')
    if service.capture_store.latest(capture_id) != current:
        raise EnrichmentError('recorded terminal claim changed during absence reconciliation')


def reconcile_terminal_preparation(service: Any, item: dict[str, Any], *, output_root: Path) -> dict[str, Any]:
    """Reconcile an exact reserved task before reinstalling its RAM-only ticket."""
    from copy import deepcopy
    from .recorded_recovery import collect_recorded_proof, validate_recorded_proof
    from .xiaocao_wechat import XiaocaoLiveCaptureDriver
    capture_id, identity = str(item['capture_job_id']), str(item['identity'])
    current=service.capture_store.latest(capture_id); repair=(current or {}).get('media_repair') or {}
    if (not current or current.get('user_resume_required') or item.get('human_playback_deferred')
        or repair.get('state') not in {'preparing','prepared'}):
        raise EnrichmentError('recorded terminal preparation is not reconcilable')
    path=Path(str(repair.get('proof_path') or ''))
    item_root=Path(service.output_dir).resolve()
    if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(item_root)
        or _sha(path)!=repair.get('proof_sha256')):
        raise EnrichmentError('recorded terminal retained alias proof changed')
    proof=json.loads(path.read_text()); validate_recorded_proof(proof,item,capture_id)
    binding=current.get('recorded_replay_binding') or {}
    if (proof.get('candidate_id')!=repair.get('alias_candidate_id')
        or _verified_same_file_alias(service,binding,proof)!=repair.get('alias_binding')):
        raise EnrichmentError('recorded terminal retained alias changed original file')
    driver=XiaocaoLiveCaptureDriver(item_root.parent.parent); driver._service=lambda _:service
    observed=collect_recorded_proof(item_root.parent.parent,identity,capture_id,proof['candidate_id'],
        player_duration=proof['player_duration_seconds'],player_left=proof['player_left'],
        driver=driver,observation_path=proof['observation_receipt_path'])
    if observed!=proof:
        raise EnrichmentError('recorded terminal retained ticket evidence is no longer fresh')
    tasks=service.sniffer.complete_tasks_for_reconciliation(); task_id=str(repair.get('task_id') or '')
    exact=[task for task in tasks if task.get('id')==task_id]
    if len(exact)!=1 or any(t.get('status') in {'running','ready','wait'} for t in tasks):
        raise EnrichmentError('recorded terminal preparation provider state is busy or ambiguous')
    task=exact[0]; meta=task.get('meta') or {}; labels=meta.get('labels') or (meta.get('req') or {}).get('labels') or {}
    opts=meta.get('opts') or {}; revision=str(labels.get('media_repair_revision') or '')
    if (task.get('status')!='pause' or not re.fullmatch(r'[0-9a-f]{64}',revision)
        or labels.get('recorded_ticket_alias_id')!=repair['alias_candidate_id']
        or labels.get('media_repair_previous_sha256')!=repair['previous_media_sha256']
        or labels.get('media_repair_previous_name')!=Path(repair['previous_media_path']).name
        or opts.get('name')==labels.get('media_repair_previous_name')):
        raise EnrichmentError('recorded terminal preparation effect is uncertain')
    # Reconstruct only the immutable old output view to recheck its actual bytes
    # and checkpoint; no provider state is altered by this projection.
    projected=deepcopy(task); projected['meta']['opts']['name']=Path(repair['previous_media_path']).name
    projected['status']=repair['preflight']['task_status']
    old_tasks=[projected if t.get('id')==task_id else t for t in tasks]
    old_current={**current,'status':'download_failed'}
    preflight=inspect_terminal_task(old_current,old_tasks,output_root=output_root)
    if preflight!=repair.get('preflight'):
        raise EnrichmentError('recorded terminal original checkpoint changed during reconciliation')
    receipt=service.sniffer.prepare_recorded_terminal_revision(task_id,
        candidate_id=repair['candidate_id'],resource_id=preflight['resource_id'],
        media_file_id=preflight['media_file_id'],partial_sha256=preflight['partial_sha256'],
        manifest_sha256=binding['finite_playlist']['sha256'],resource_sha256=binding['media_resource_sha256'],
        checkpoint_binding_sha256=preflight['checkpoint_binding_sha256'],terminal_sha256=preflight['terminal_sha256'],
        alias_candidate_id=repair['alias_candidate_id'])
    if (receipt.get('id')!=task_id or receipt.get('revision')!=revision
        or receipt.get('previous_sha256')!=repair['previous_media_sha256']
        or receipt.get('previous_name')!=Path(repair['previous_media_path']).name
        or receipt.get('name')!=opts.get('name') or not compressed_media_name(str(receipt.get('name') or ''))):
        raise EnrichmentError('recorded terminal reconciled reservation changed')
    if repair.get('state')=='prepared' and repair.get('backend_receipt')!=receipt:
        raise EnrichmentError('recorded terminal prior preparation receipt changed')
    reconciled={**repair,'state':'prepared','backend_receipt':receipt,'revision':revision,'media_basename':receipt['name']}
    return _durable_transition(service.capture_store,current,'recorded_terminal_preparation_reconciled',
                               status='downloading',media_repair=reconciled)
