from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from types import SimpleNamespace

import pytest

from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.netdisk_enrichment import NetdiskEnrichmentService

NOW = datetime.fromisoformat('2026-10-14T10:00:00+08:00')


def setup_upload(tmp_path, monkeypatch):
    clock = [NOW]
    service = NetdiskEnrichmentService(tmp_path / 'ledger', now=lambda: clock[0],
                                       use_opencli_upload_template=True)
    media = tmp_path / 'course-compressed.mp4'
    media.write_bytes(b'validated compressed artifact')
    current = {'job_id': 'kol-netdisk-test12345', 'status': 'upload_claimed',
               'event': 'netdisk_upload_started', 'video_path': str(media),
               'video_basename': media.name, 'video_size_bytes': media.stat().st_size,
               'video_sha256': hashlib.sha256(media.read_bytes()).hexdigest(),
               'upload_started_at': NOW.isoformat()}
    service.store.append(current)
    proof = {'status': 'ready_to_upload', 'claimId': current['job_id'],
             'targetName': media.name, 'directory': service.netdisk_directory,
             'url': 'https://pan.baidu.com/disk/main', 'uploaded': False, 'uploadTarget': '',
             'exactCountBefore': 0,
             'surfaceState': {'targetInTransferUi': True,
                'transferQueue': {'complete': True, 'rowCount': 1, 'targetCount': 1,
                                  'successfulCount': 0},
                'targetUiRows': [{'rowText': media.name + '\n1M\n0B/s',
                                 'rowClassName': 'status-uploading file-list',
                                 'progressWidths': ['0%'],
                                 'rowControls': [{'title': '暂停'}, {'title': '取消'}]}]}}
    calls = []
    uncertain = [False]

    def run(**kwargs):
        calls.append(kwargs)
        if kwargs.get('repair_stalled'):
            # Recovery is claimed before any browser operation, without a held
            # job lock. A lost result must permanently consume that claim.
            assert service.store.latest(current['job_id'])['stalled_upload_repair_claimed_at']
            if uncertain[0]:
                return SimpleNamespace(returncode=1, stdout='[]')
            receipt = {'status': 'existing_upload_resumed', 'claimId': current['job_id'],
                       'targetName': media.name, 'directory': service.netdisk_directory,
                       'uploaded': False, 'pausedReadback': True, 'resumedReadback': True}
            return SimpleNamespace(returncode=0, stdout=json.dumps([receipt]))
        assert kwargs.get('inspect_only') is True
        return SimpleNamespace(returncode=0, stdout=json.dumps([deepcopy(proof)]))

    monkeypatch.setattr(service, '_opencli_upload_template_process', run)
    return service, current['job_id'], clock, proof, calls, uncertain, media


def test_same_queue_repair_preserves_upload_and_never_attaches(tmp_path, monkeypatch):
    service, job, clock, proof, calls, _, _ = setup_upload(tmp_path, monkeypatch)
    before = service.store.latest(job)
    service.observe_stalled_upload(job)
    clock[0] += timedelta(minutes=5)
    result = service.repair_stalled_upload(job, repair_authorized=True)
    assert result['status'] == 'upload_claimed'
    assert result['event'] == 'netdisk_stalled_upload_resumed'
    assert result['upload_started_at'] == before['upload_started_at']
    assert result['video_sha256'] == before['video_sha256']
    assert sum(call.get('repair_stalled') is True for call in calls) == 1
    assert all(call.get('inspect_only') is True or call.get('repair_stalled') is True for call in calls)
    with pytest.raises(EnrichmentError, match='not eligible'):
        service.repair_stalled_upload(job, repair_authorized=True)


def test_repair_waits_for_observed_stall_and_authorization(tmp_path, monkeypatch):
    service, job, clock, _, calls, _, _ = setup_upload(tmp_path, monkeypatch)
    with pytest.raises(EnrichmentError, match='authorization'):
        service.repair_stalled_upload(job)
    assert not calls
    service.observe_stalled_upload(job)
    clock[0] += timedelta(seconds=299)
    with pytest.raises(EnrichmentError, match='five minutes'):
        service.repair_stalled_upload(job, repair_authorized=True)
    assert not service.store.latest(job).get('stalled_upload_repair_claimed_at')


@pytest.mark.parametrize('unsafe', ['progress', 'paused', 'other_name', 'cloud', 'multiple', 'incomplete'])
def test_repair_refuses_progress_user_pause_or_ambiguous_target(tmp_path, monkeypatch, unsafe):
    service, job, clock, proof, calls, _, _ = setup_upload(tmp_path, monkeypatch)
    service.observe_stalled_upload(job)
    clock[0] += timedelta(minutes=5)
    row = proof['surfaceState']['targetUiRows'][0]
    if unsafe == 'progress':
        row['progressWidths'] = ['1%']
    elif unsafe == 'paused':
        row['rowClassName'] = 'status-paused file-list'
        row['rowControls'] = [{'title': '继续'}]
    elif unsafe == 'other_name':
        proof['targetName'] = 'different.mp4'
    elif unsafe == 'cloud':
        proof['exactCountBefore'] = 1
    elif unsafe == 'multiple':
        proof['surfaceState']['transferQueue']['rowCount'] = 2
    elif unsafe == 'incomplete':
        proof['surfaceState']['transferQueue']['complete'] = False
    with pytest.raises(EnrichmentError):
        service.repair_stalled_upload(job, repair_authorized=True)
    assert not any(call.get('repair_stalled') for call in calls)


def test_changed_media_is_not_recovered(tmp_path, monkeypatch):
    service, job, clock, _, calls, _, media = setup_upload(tmp_path, monkeypatch)
    service.observe_stalled_upload(job)
    clock[0] += timedelta(minutes=5)
    media.write_bytes(b'changed')
    with pytest.raises(EnrichmentError, match='source changed'):
        service.repair_stalled_upload(job, repair_authorized=True)
    assert not any(call.get('repair_stalled') for call in calls)


def test_uncertain_resume_is_never_repeated(tmp_path, monkeypatch):
    service, job, clock, _, calls, uncertain, _ = setup_upload(tmp_path, monkeypatch)
    service.observe_stalled_upload(job)
    clock[0] += timedelta(minutes=5)
    uncertain[0] = True
    with pytest.raises(EnrichmentError, match='uncertain'):
        service.repair_stalled_upload(job, repair_authorized=True)
    with pytest.raises(EnrichmentError, match='not eligible'):
        service.repair_stalled_upload(job, repair_authorized=True)
    assert sum(call.get('repair_stalled') is True for call in calls) == 1


@pytest.mark.parametrize('scenario', ['success', 'progress', 'paused_initial', 'ambiguous',
                                      'incomplete', 'wrong_folder', 'denied', 'error_after_pause'])
def test_production_adapter_only_recovers_exact_paused_transfer(scenario):
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['node', 'tests/fixtures/kol_upload_recovery.mjs', scenario],
                   cwd=root, check=True, capture_output=True, text=True, timeout=10)
