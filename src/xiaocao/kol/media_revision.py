"""Explicit same-capture repair versions, preserving original media and effects."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .enrichment_types import EnrichmentDiagnosticError, EnrichmentError, compressed_media_name
from .mailbox import MailboxLedger


def _task(service: Any, task_id: str) -> dict[str, Any]:
    matches = [row for row in service.sniffer.tasks() if row.get('id') == task_id]
    if len(matches) != 1:
        raise EnrichmentError('exact media revision task is unavailable')
    return matches[0]


def _labels(task: dict[str, Any]) -> dict[str, Any]:
    meta = task.get('meta') or {}
    return meta.get('labels') or (meta.get('req') or {}).get('labels') or {}


def prepare_media_revision(service: Any, capture_job_id: str, *, repair_authorized: bool,
                           mailbox_ledger: MailboxLedger,
                           not_found_readback: dict[str, Any]) -> dict[str, Any]:
    """Claim one paused output revision; never create a capture or download task."""
    if not repair_authorized:
        raise EnrichmentError('same-item media revision requires explicit authorization')
    current = service.capture_store.latest(capture_job_id)
    if not current:
        raise EnrichmentError('original capture is missing')
    prior = current.get('media_repair')
    if isinstance(prior, dict) and prior.get('backend_receipt'):
        return current
    if not prior:
        if current.get('status') != 'downloaded':
            raise EnrichmentError('media revision requires a previously completed artifact')
        try:
            service.validate_media(capture_job_id)
        except EnrichmentDiagnosticError as exc:
            if exc.diagnostic_code != 'compressed_media_duration_mismatch':
                raise
        else:
            raise EnrichmentError('complete media cannot be restarted')
        media = Path(str(current.get('media_path') or ''))
        with media.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        rejected = service._event('media_integrity_rejected', capture_job_id=capture_job_id)
        handoff = service._event('cloud_handoff_published', capture_job_id=capture_job_id)
        if not rejected or rejected.get('media_sha256') != sha or not handoff or handoff.get('media_sha256') != sha:
            raise EnrichmentError('rejected artifact and original cloud claim are not bound')
        from .xiaocao_wechat import XiaocaoWechatLiveSubscription
        capsule_path = Path(str(handoff.get('handoff_path') or ''))
        if not capsule_path.is_file() or hashlib.sha256(capsule_path.read_bytes()).hexdigest() != handoff.get('handoff_sha256'):
            raise EnrichmentError('original handoff receipt hash changed')
        capsule = XiaocaoWechatLiveSubscription._load_handoff({'handoff_path':str(capsule_path), 'capture_job_id':capture_job_id})
        handoff_id = capsule.get('handoff_id')
        if not re.fullmatch(r'[a-f0-9]{64}', str(handoff_id or '')) or capsule.get('media_sha256') != sha:
            raise EnrichmentError('original handoff capsule binding is invalid')
        mailbox_ledger.reject_unpublished_handoff(handoff_id, not_found_readback=not_found_readback)
        prior = {'state': 'preparing', 'previous_media_path': str(media),
                 'previous_media_sha256': sha, 'previous_media_size_bytes': media.stat().st_size,
                 'previous_handoff_id': handoff_id,
                 'previous_netdisk_job_id': handoff['netdisk_job_id'],
                 'claimed_at': datetime.now(timezone.utc).isoformat()}
        current = service.capture_store.transition(current, 'media_revision_claimed', media_repair=prior)
        dispatch = True
    else:
        dispatch = False
    candidate = current.get('candidate') or {}
    task_id = str(current.get('download_task_id') or '')
    task = _task(service, task_id)
    labels = _labels(task)
    if (not task_id or labels.get('capture_id') != candidate.get('id')
        or labels.get('live_id') != candidate.get('live_id')):
        raise EnrichmentError('media revision changed the original task identity')
    if dispatch:
        receipt = service.sniffer.prepare_stream_revision(task_id, candidate_id=candidate['id'],
            live_id=candidate['live_id'], original_sha256=prior['previous_media_sha256'])
        task = _task(service, task_id)
    else:
        labels = _labels(task)
        if labels.get('media_repair_previous_sha256') != prior['previous_media_sha256'] or not labels.get('media_repair_revision'):
            raise EnrichmentError('media revision preparation is uncertain; do not dispatch again')
        receipt = {'id': task_id, 'previous_name': Path(prior['previous_media_path']).name,
                   'previous_sha256': labels['media_repair_previous_sha256'],
                   'name': (task.get('meta') or {}).get('opts', {}).get('name'),
                   'revision': labels['media_repair_revision'], 'status': task.get('status'),
                   'reconciled_from': 'exact_provider_task_labels'}
    labels = _labels(task)
    name = str(receipt.get('name') or '')
    if (receipt.get('id') != task_id or receipt.get('previous_sha256') != prior['previous_media_sha256']
        or receipt.get('previous_name') != Path(prior['previous_media_path']).name
        or not compressed_media_name(name) or Path(name).name != name
        or name == Path(prior['previous_media_path']).name
        or task.get('status') != 'pause' or labels.get('media_repair_revision') != receipt.get('revision')
        or not re.fullmatch(r'[a-f0-9]{64}', str(receipt.get('revision') or ''))
        or Path((task.get('meta') or {}).get('opts', {}).get('path', '')).resolve()
        != Path(prior['previous_media_path']).parent.resolve()
        or (task.get('meta') or {}).get('opts', {}).get('name') != name):
        raise EnrichmentError('prepared media revision lacks exact paused task readback')
    repair = {**prior, 'state': 'prepared', 'backend_receipt': receipt,
              'revision': receipt['revision'], 'media_basename': name}
    return service.capture_store.transition(current, 'media_revision_prepared',
        status='downloading', media_repair=repair)


def resume_media_revision(service: Any, capture_job_id: str, *, user_resume_authorized: bool = False) -> dict[str, Any]:
    """Consume one exact resume claim for the prepared original task."""
    current = service.capture_store.latest(capture_job_id)
    repair = (current or {}).get('media_repair') or {}
    if (current or {}).get('user_resume_required') is True and not user_resume_authorized:
        raise EnrichmentError('user-paused media revision requires explicit resume authorization')
    if repair.get('state') not in {'prepared', 'resume_claimed', 'running'}:
        raise EnrichmentError('media revision is not prepared')
    task_id = str(current.get('download_task_id') or '')
    task = _task(service, task_id)
    if _labels(task).get('media_repair_revision') != repair.get('revision'):
        raise EnrichmentError('media revision resume binding changed')
    if repair.get('state') != 'prepared':
        if task.get('status') in {'running', 'done'}:
            return current
        raise EnrichmentError('claimed media revision resume is uncertain; reconcile same task')
    if task.get('status') != 'pause':
        raise EnrichmentError('prepared media revision is not paused')
    current = service.capture_store.transition(current, 'media_revision_resume_claimed',
        media_repair={**repair, 'state': 'resume_claimed'}, user_resume_required=False)
    receipt = service.sniffer.resume_task(task_id)
    task = _task(service, task_id)
    if receipt.get('id') != task_id or task.get('status') not in {'running', 'done'}:
        raise EnrichmentError('media revision resume lacks exact running task readback')
    return service.capture_store.transition(current, 'media_revision_download_started',
        status='downloading', media_repair={**repair, 'state': 'running', 'resume_receipt': receipt})


def resume_checkpoint_download(service: Any, capture_job_id: str, *,
                               user_resume_authorized: bool = False) -> dict[str, Any]:
    """Resume one observed checkpoint failure, without any new task creation."""
    current = service.capture_store.latest(capture_job_id)
    if not current or current.get('status') not in {'downloading', 'download_failed'}:
        raise EnrichmentError('checkpoint capture is not interrupted')
    if current.get('user_resume_required') is True and not user_resume_authorized:
        raise EnrichmentError('user-paused checkpoint requires explicit resume authorization')
    task_id = str(current.get('download_task_id') or '')
    task = _task(service, task_id)
    labels = _labels(task)
    candidate = current.get('candidate') or {}
    if (labels.get('checkpoint_basis') != 'verified_hls_segments'
        or labels.get('capture_id') != candidate.get('id') or labels.get('live_id') != candidate.get('live_id')
        or labels.get('type') != 'live_capture' or labels.get('compress_inline') != 'true'):
        raise EnrichmentError('checkpoint does not bind the original compressed task')
    if task.get('status') == 'running' and current.get('checkpoint_resume_claim'):
        return current
    if task.get('status') not in {'error', 'pause'}:
        raise EnrichmentError('checkpoint task is not stopped')
    failure = str(task.get('updatedAt') or '')
    if not failure:
        raise EnrichmentError('checkpoint failure lacks a provider observation boundary')
    if (current.get('checkpoint_resume_claim') or {}).get('failure_updated_at') == failure:
        raise EnrichmentError('checkpoint resume already claimed; reconcile uncertain dispatch')
    claim = {'task_id': task_id, 'failure_updated_at': failure, 'candidate_id': candidate['id']}
    current = service.capture_store.transition(current, 'checkpoint_resume_claimed',
        checkpoint_resume_claim=claim, user_resume_required=False)
    receipt = service.sniffer.resume_task(task_id)
    task = _task(service, task_id)
    if receipt.get('id') != task_id or task.get('status') not in {'running', 'done'}:
        raise EnrichmentError('checkpoint resume lacks exact running task readback')
    return service.capture_store.transition(current, 'checkpoint_download_resumed',
        status='downloading', checkpoint_resume_receipt=receipt)


def install_stopped_checkpoint_repair(service: Any, capture_job_id: str, *, replacement_binary: Path) -> dict[str, Any]:
    """Replace only a stopped bound checkpoint backend, preserving native arm."""
    current = service.capture_store.latest(capture_job_id)
    if not current or current.get('status') not in {'downloading', 'download_failed'} or current.get('user_resume_required'):
        raise EnrichmentError('checkpoint backend repair requires an Agent-owned interrupted download')
    task = _task(service, str(current.get('download_task_id') or ''))
    labels = _labels(task)
    candidate = current.get('candidate') or {}
    if (task.get('status') not in {'pause', 'error'} or task.get('protocol') != 'stream'
        or labels.get('checkpoint_basis') != 'verified_hls_segments'
        or labels.get('capture_id') != candidate.get('id') or labels.get('live_id') != candidate.get('live_id')
        or labels.get('compress_inline') != 'true' or labels.get('type') != 'live_capture'
        or any(t.get('status') in {'running', 'ready', 'wait'} for t in service.sniffer.tasks())):
        raise EnrichmentError('checkpoint backend repair lacks exact stopped singleton task binding')
    opts = (task.get('meta') or {}).get('opts') or {}
    media = Path(str(opts.get('path') or '')) / str(opts.get('name') or '')
    repair = current.get('media_repair') or {}
    if (not compressed_media_name(media.name) or media.name != repair.get('media_basename')
        or labels.get('media_repair_revision') != repair.get('revision')
        or media.parent.resolve() != Path(str(repair.get('previous_media_path') or '')).parent.resolve()):
        raise EnrichmentError('checkpoint backend repair output revision changed')
    cache = Path(str(media) + '.hls-cache')
    binding = cache / 'binding.json'
    if not binding.is_file() or (cache / 'terminal.json').exists():
        raise EnrichmentError('checkpoint backend repair requires a non-terminal bound cache')
    claim = {'task_id':task['id'], 'candidate_id':candidate['id'],
             'binding_sha256':hashlib.sha256(binding.read_bytes()).hexdigest(),
             'replacement_sha256':hashlib.sha256(replacement_binary.read_bytes()).hexdigest()}
    if current.get('checkpoint_backend_repair_claim') == claim:
        raise EnrichmentError('checkpoint backend replacement already claimed; reconcile before replay')
    current = service.capture_store.transition(current,'checkpoint_backend_repair_claimed',
        checkpoint_backend_repair_claim=claim)
    result = service._replace_sniffer_for_repair(current,replacement_binary=replacement_binary,preserve_native_arm=True)
    if hashlib.sha256(binding.read_bytes()).hexdigest() != claim['binding_sha256']:
        raise EnrichmentError('checkpoint binding changed across backend repair')
    restored = _task(service, task['id'])
    if restored.get('status') not in {'pause', 'error'} or _labels(restored).get('media_repair_revision') != repair['revision']:
        raise EnrichmentError('checkpoint task changed across backend repair')
    return result
