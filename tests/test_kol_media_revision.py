from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_kol_xiaocao_live import _capture_fixture, _probe_runner, _sha256
from xiaocao.kol.capture import CaptureJobStore, SnifferError
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.mailbox import MailboxLedger, LiangHuiMailboxClient, MailboxError
from xiaocao.kol.media_revision import prepare_media_revision, resume_media_revision
from xiaocao.kol.xiaocao_live import XiaocaoLiveService


def fixture(tmp_path):
    ledger, capture, media, _ = _capture_fixture(tmp_path)
    store = CaptureJobStore(ledger)
    current = store.latest(capture)
    task = current['download_task']
    task['meta']['labels']['hls_duration_sec'] = '6228.206'
    store.transition(current, 'download_completed', download_task=task)
    provider = deepcopy(task)
    provider['meta']['opts']['path'] = str(media.parent)
    calls = []
    def prepare(task_id, **kwargs):
        calls.append(('prepare', task_id))
        provider['status'] = 'pause'
        provider['meta']['opts']['name'] = 'target-compressed (1).mp4'
        labels = provider['meta']['labels']
        labels.update(media_repair_revision='a'*64, media_repair_previous_sha256=kwargs['original_sha256'])
        return {'id': task_id, 'previous_name': media.name, 'previous_sha256': kwargs['original_sha256'],
                'name': provider['meta']['opts']['name'], 'revision': 'a'*64, 'status': 'pause'}
    def resume(task_id):
        calls.append(('resume', task_id));provider['status']='running';return {'id':task_id}
    sniffer = SimpleNamespace(tasks=lambda: [deepcopy(provider)], prepare_stream_revision=prepare, resume_task=resume)
    service = XiaocaoLiveService(tmp_path/'live', capture_ledger=ledger, sniffer_client=sniffer,
                                runner=_probe_runner(media, 6190.762887))
    handoff_id='b'*64
    capsule={'schema_version':2,'capture_job_id':capture,'handoff_id':handoff_id,'media_sha256':_sha256(media),'large_payload_local_bytes':0}
    canonical=lambda value: json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    capsule['handoff_sha256']=hashlib.sha256(canonical(capsule).encode()).hexdigest()
    capsule_path=tmp_path/'original-handoff.json';capsule_path.write_text(canonical(capsule))
    service._append('cloud_handoff_published', capture_job_id=capture, media_sha256=_sha256(media),
                    handoff_id=handoff_id, netdisk_job_id='original-upload',
                    handoff_path=str(capsule_path),handoff_sha256=_sha256(capsule_path))
    mailbox=MailboxLedger(tmp_path/'mailbox')
    mailbox.append('mailbox_send_attempted', handoff_id=handoff_id, mailbox_id='kol.handoff', message_id=handoff_id,
                   object_kind='video', title='original', content_sha256='c'*64)
    absence={'operation':'get_mailbox_message', 'arguments':{'mailbox_id':'kol.handoff','message_id':handoff_id},
             'error_code':'NOT_FOUND'}
    return service,capture,media,mailbox,absence,calls,provider


def test_same_task_revision_preserves_original_and_claims(tmp_path):
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    original=media.read_bytes();task=service.capture_store.latest(capture)['download_task_id']
    first=prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    again=prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    assert first==again and calls==[('prepare',task)]
    assert media.read_bytes()==original and first['job_id']==capture and first['download_task_id']==task
    assert first['media_repair']['previous_netdisk_job_id']=='original-upload'
    assert mailbox.outstanding_handoffs()==[]
    running=resume_media_revision(service,capture)
    resume_media_revision(service,capture)
    assert calls==[('prepare',task),('resume',task)]
    assert running['media_repair']['state']=='running'
    assert len([r for r in mailbox.events() if r['event']=='mailbox_send_attempted'])==1
    client=LiangHuiMailboxClient(mailbox,exchange=lambda _:pytest.fail('no old send'))
    with pytest.raises(MailboxError,match='rejected'):
        client.publish_handoff({'handoff_id':'b'*64},object_kind='video',title='original')


@pytest.mark.parametrize('invalid',['unauthorized','wrong_message','receipted','complete','wrong_task'])
def test_revision_rejects_unsafe_preconditions(tmp_path,invalid):
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    if invalid=='wrong_message':absence['arguments']['message_id']='d'*64
    if invalid=='receipted':
        prior=mailbox.handoff_state('b'*64);mailbox.append('mailbox_send_receipted',**{k:v for k,v in prior.items() if k not in {'event','event_id','schema_version'}})
    if invalid=='complete':service._runner=_probe_runner(media,6228.206)
    if invalid=='wrong_task':provider['meta']['labels']['capture_id']='other'
    with pytest.raises(EnrichmentError):
        prepare_media_revision(service,capture,repair_authorized=invalid!='unauthorized',mailbox_ledger=mailbox,not_found_readback=absence)
    assert calls==[] and media.is_file()


def test_uncertain_preparation_reconciles_without_dispatching_again(tmp_path):
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    original=service.sniffer.prepare_stream_revision
    def uncertain(*args,**kwargs):
        original(*args,**kwargs);raise SnifferError('response lost')
    service.sniffer.prepare_stream_revision=uncertain
    with pytest.raises(SnifferError):
        prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    reconciled=prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    assert len(calls)==1
    assert reconciled['media_repair']['backend_receipt']['reconciled_from']=='exact_provider_task_labels'


def test_failed_revision_cannot_fall_through_to_replacement_download(tmp_path):
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    resume_media_revision(service,capture)
    provider['status']='error'
    service.sniffer.start_download=lambda *a,**k:pytest.fail('never create replacement task')
    service.sniffer.candidates=lambda:pytest.fail('never reselect media for a checkpoint task')
    with pytest.raises(EnrichmentError,match='checkpoint'):
        service.advance_capture(capture)
    assert service.capture_store.latest(capture)['download_task_id']==provider['id']


def test_checkpoint_resume_keeps_task_and_deduplicates_uncertain_dispatch(tmp_path):
    from xiaocao.kol.media_revision import resume_checkpoint_download
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    current=service.capture_store.latest(capture)
    service.capture_store.transition(current,'download_failed',status='download_failed')
    provider['status']='error';provider['updatedAt']='failure-1'
    provider['meta']['labels']['checkpoint_basis']='verified_hls_segments'
    resumed=resume_checkpoint_download(service,capture)
    resume_checkpoint_download(service,capture)
    assert resumed['download_task_id']==provider['id']
    assert calls==[('resume',provider['id'])]
    provider['status']='error'
    with pytest.raises(EnrichmentError,match='already claimed'):
        resume_checkpoint_download(service,capture)
    provider['updatedAt']='failure-2'
    resume_checkpoint_download(service,capture)
    assert len(calls)==2


def test_finite_early_failure_does_not_force_new_task(tmp_path):
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    provider['status']='error';provider['meta']['labels']['hls_finite']='true'
    current=service.capture_store.latest(capture)
    service.capture_store.transition(current,'download_progress',status='downloading')
    service.sniffer.start_download=lambda *a,**k:pytest.fail('replacement forbidden')
    service.sniffer.candidates=lambda:pytest.fail('reselection forbidden')
    with pytest.raises(EnrichmentError,match='checkpoint'):
        service.advance_capture(capture)


def test_revision_publishes_new_hash_and_preserves_old_capsule(tmp_path):
    import json
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    old_path=tmp_path/'old-capsule.json';old_path.write_text('original immutable')
    old=service._event('cloud_handoff_published',capture_job_id=capture)
    service._append('cloud_handoff_published',**{k:v for k,v in old.items() if k not in {'event','updated_at','handoff_path'}},handoff_path=str(old_path))
    # A prepared repair allows a separate capsule; old event remains readable.
    current=service.capture_store.latest(capture)
    service.capture_store.transition(current,'media_revision_prepared',media_repair={'revision':'a'*64})
    new=media.with_name('target-compressed (1).mp4');new.write_bytes(b'corrected')
    metadata={'media_sha256':_sha256(new),'media_path':str(new),'media_basename':new.name,
              'media_size_bytes':new.stat().st_size,'media_duration_seconds':6228.206,
              'live_id':current['candidate']['live_id'],'captured_at':'2026-10-21T06:41:28+08:00'}
    published=service._publish_handoff(capture_job_id=capture,media=metadata,netdisk={'job_id':'new-upload'})
    assert published['netdisk_job_id']=='new-upload'
    assert Path(published['handoff_path'])!=old_path
    assert old_path.read_text()=='original immutable'
    assert json.loads(Path(published['handoff_path']).read_text())['media_sha256']==_sha256(new)
    assert service._publish_handoff(capture_job_id=capture,media=metadata,netdisk={'job_id':'new-upload'})['idempotent_replay']


def test_repair_published_lookup_never_recovers_old_hash(tmp_path):
    from xiaocao.kol.xiaocao_wechat import XiaocaoLiveCaptureDriver
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    driver=XiaocaoLiveCaptureDriver(tmp_path/'sub',service_factory=lambda *a,**k:service)
    current=service.capture_store.latest(capture)
    service.capture_store.transition(current,'media_revision_prepared',status='downloading',media_repair={'revision':'a'*64})
    assert driver.published_handoff('identity',capture) is None
    new=media.with_name('target-compressed (1).mp4');new.write_bytes(b'new')
    current=service.capture_store.latest(capture)
    service.capture_store.transition(current,'download_completed',status='downloaded',media_path=str(new))
    service.validate_media=lambda _: {'media_sha256':_sha256(new)}
    assert driver.published_handoff('identity',capture) is None
    service._append('cloud_handoff_published',capture_job_id=capture,media_sha256=_sha256(new))
    assert driver.published_handoff('identity',capture)['media_sha256']==_sha256(new)


def test_revision_respects_user_pause(tmp_path):
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    prepared=prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    service.capture_store.transition(prepared,'user_pause_requested',user_resume_required=True)
    with pytest.raises(EnrichmentError,match='user-paused'):
        resume_media_revision(service,capture)
    assert calls==[('prepare',provider['id'])]
    resumed=resume_media_revision(service,capture,user_resume_authorized=True)
    assert resumed['user_resume_required'] is False


def test_revision_cleanup_accepts_raw_provider_labels_preserves_old_receipt(tmp_path):
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    current=service.capture_store.latest(capture)
    service.capture_store.transition(current,'media_revision_prepared',media_repair={'revision':'a'*64})
    labels=provider['meta'].pop('labels');labels['media_repair_revision']='a'*64
    provider['meta']['req']={'labels':labels};provider['status']='done'
    proof={'process_gone':True,'api_status_unavailable':True,'listeners':{'2022':False,'2023':False},
           'proxy_flags':{'HTTPEnable':0,'HTTPSEnable':0,'ProxyAutoConfigEnable':0,'SOCKSEnable':0},
           'capture_proxy_detached':True,'observed_at':'2026-10-21T08:00:00+08:00'}
    service.cleanup_snapshot=lambda:deepcopy(proof)
    service._sniffer_pids=lambda:[]
    service._disable_owned_capture_pac=lambda:None
    old=service.output_dir/'receipts'/'capture_cleanup.json';old.parent.mkdir(parents=True,exist_ok=True);old.write_text('original cleanup')
    result=service.cleanup_sniffer(capture_job_id=capture)
    assert result['media_repair_revision']=='a'*64
    assert Path(result['cleanup_evidence_path'])!=old
    assert old.read_text()=='original cleanup'


def test_revision_subscription_rebind_preserves_original_and_is_idempotent(tmp_path):
    from xiaocao.kol.xiaocao_wechat import XiaocaoLiveCaptureDriver, XiaocaoWechatLiveSubscription
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    prepared=prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    driver=XiaocaoLiveCaptureDriver(tmp_path/'sub',service_factory=lambda *a,**k:service)
    sub=XiaocaoWechatLiveSubscription(tmp_path/'sub',capture_driver=driver,history_reader=lambda:{},browser_exchange=lambda _:pytest.fail('no browser'))
    manifest=sub._load();path=service._event('cloud_handoff_published',capture_job_id=capture)['handoff_path']
    item={'identity':'same-original','capture_job_id':capture,'status':'handoff_ready','handoff_path':path}
    manifest['items'][item['identity']]=item;sub._save(manifest)
    result=sub.bind_media_revision(item['identity'],capture,mailbox_ledger=mailbox)
    assert result['identity']==item['identity'] and result['capture_job_id']==capture
    assert result['previous_handoff_path']==path and result['handoff_path'] is None
    assert result['status']=='playback_activated'
    assert sub.bind_media_revision(item['identity'],capture,mailbox_ledger=mailbox)==result


def test_stopped_checkpoint_backend_repair_preserves_binding_and_task(tmp_path):
    from xiaocao.kol.media_revision import install_stopped_checkpoint_repair
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    prepared=prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    provider['protocol']='stream'
    provider['meta']['labels']['checkpoint_basis']='verified_hls_segments'
    output=media.with_name(provider['meta']['opts']['name']);cache=Path(str(output)+'.hls-cache');cache.mkdir()
    (cache/'binding.json').write_text('{"bound":"original"}')
    binary=tmp_path/'tested-candidate';binary.write_bytes(b'tested')
    def replace(current,**kwargs):
        assert kwargs['preserve_native_arm'] is True
        calls.append(('replace',current['download_task_id']));return {'capture_job_id':capture}
    service._replace_sniffer_for_repair=replace
    receipt=install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)
    assert receipt['capture_job_id']==capture and calls[-1]==('replace',provider['id'])
    assert (cache/'binding.json').read_text()=='{"bound":"original"}'
    with pytest.raises(EnrichmentError,match='already claimed'):
        install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)
    assert len(calls)==2


@pytest.mark.parametrize('blocked',['running','other_active','user_pause','terminal','wrong_revision'])
def test_checkpoint_backend_install_rejects_unverified_state(tmp_path,blocked):
    from xiaocao.kol.media_revision import install_stopped_checkpoint_repair
    service,capture,media,mailbox,absence,calls,provider=fixture(tmp_path)
    prepared=prepare_media_revision(service,capture,repair_authorized=True,mailbox_ledger=mailbox,not_found_readback=absence)
    provider['protocol']='stream'
    provider['meta']['labels']['checkpoint_basis']='verified_hls_segments'
    cache=Path(str(media.with_name(provider['meta']['opts']['name']))+'.hls-cache');cache.mkdir();(cache/'binding.json').write_text('{}')
    binary=tmp_path/'candidate';binary.write_bytes(b'tested')
    service._replace_sniffer_for_repair=lambda *a,**k:pytest.fail('must not stop backend')
    if blocked=='running':provider['status']='running'
    if blocked=='other_active':service.sniffer.tasks=lambda:[deepcopy(provider),{'id':'other','status':'running'}]
    if blocked=='user_pause':service.capture_store.transition(prepared,'user_pause',user_resume_required=True)
    if blocked=='terminal':(cache/'terminal.json').write_text('{"status":403}')
    if blocked=='wrong_revision':provider['meta']['labels']['media_repair_revision']='other'
    with pytest.raises(EnrichmentError):install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)


@pytest.mark.parametrize('blocked',[None,'different_output','published','active_other','changed_after_restore'])
def test_original_checkpoint_backend_repair_is_exact_and_unpublished(tmp_path,blocked):
    from xiaocao.kol.media_revision import install_stopped_checkpoint_repair
    ledger,capture,media,_=_capture_fixture(tmp_path)
    store=CaptureJobStore(ledger);current=store.latest(capture)
    provider=deepcopy(current['download_task']);provider['status']='error';provider['protocol']='stream'
    provider['meta']['labels']['checkpoint_basis']='verified_hls_segments'
    current=store.transition(current,'interrupted',status='download_failed',download_task=deepcopy(provider))
    calls=[]
    sniffer=SimpleNamespace(tasks=lambda:[deepcopy(provider)])
    service=XiaocaoLiveService(tmp_path/'live',capture_ledger=ledger,sniffer_client=sniffer)
    cache=Path(str(media)+'.hls-cache');cache.mkdir();(cache/'binding.json').write_text('{"original":true}')
    binary=tmp_path/'candidate';binary.write_bytes(b'tested')
    def replace(row,**kwargs):
        calls.append(row['download_task_id'])
        assert kwargs['preserve_native_arm'] is True
        if blocked=='changed_after_restore':provider['meta']['opts']['name']='other-compressed.mp4'
        return {'capture_job_id':capture}
    service._replace_sniffer_for_repair=replace
    if blocked=='different_output':provider['meta']['opts']['name']='other-compressed.mp4'
    if blocked=='published':service._append('cloud_handoff_published',capture_job_id=capture)
    if blocked=='active_other':sniffer.tasks=lambda:[deepcopy(provider),{'id':'other','status':'running'}]
    if blocked:
        with pytest.raises(EnrichmentError):install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)
        assert len(calls)==(1 if blocked=='changed_after_restore' else 0)
    else:
        assert install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)['capture_job_id']==capture
        assert calls==[provider['id']]
        assert (cache/'binding.json').read_text()=='{"original":true}'


@pytest.mark.parametrize('blocked', ['', 'bytes', 'cache', 'query', 'host', 'published', 'active', 'media_changed', 'install_failed', 'output_after', 'restored_labels'])
def test_precheckpoint_public_task_repair_preserves_identity(tmp_path, blocked):
    from xiaocao.kol.media_revision import install_stopped_checkpoint_repair, resume_checkpoint_download
    ledger, capture, media, _ = _capture_fixture(tmp_path)
    store = CaptureJobStore(ledger)
    current = store.latest(capture)
    media.unlink()
    task = deepcopy(current['download_task'])
    task.update(status='error', protocol='stream', updatedAt='2026-10-29T21:09:06+08:00', progress={'downloaded':0})
    task['meta']['req'] = {'url':'https://live-ex-speed.xiaoeknow.com/replay.m3u8'}
    task['meta']['labels'].update(hls_finite='true', compress_inline='true')
    store.transition(current, 'failed', status='download_failed', download_task=deepcopy(task),
        native_media_lineage={'media_resource_sha256':hashlib.sha256(task['meta']['req']['url'].encode()).hexdigest(),
            'finite_playlist':{'ended':True,'candidate_id':current['candidate']['id'],
                'media_resource_sha256':hashlib.sha256(task['meta']['req']['url'].encode()).hexdigest()}})
    calls = []
    def resume(task_id):
        calls.append(task_id)
        task['status'] = 'running'
        return {'id':task_id}
    sniffer = SimpleNamespace(tasks=lambda:[deepcopy(task)], resume_task=resume)
    service = XiaocaoLiveService(tmp_path/'live', capture_ledger=ledger, sniffer_client=sniffer)
    binary = tmp_path/'candidate'; binary.write_bytes(b'tested')
    def replace(row, **kwargs):
        task['status'] = 'pause'
        if blocked == 'restored_labels':task['meta']['labels'].pop('hls_finite')
        if blocked != 'install_failed':
            store.transition(row, 'native_backend_repaired', repaired_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
        return {'capture_job_id':capture}
    service._replace_sniffer_for_repair = replace
    if blocked == 'bytes':task['progress']['downloaded']=1
    if blocked == 'cache':Path(str(media)+'.hls-cache').mkdir()
    if blocked == 'query':task['meta']['req']['url']+='?ticket=secret'
    if blocked == 'host':task['meta']['req']['url']='https://other.test/replay.m3u8'
    if blocked == 'published':service._append('cloud_handoff_published',capture_job_id=capture)
    if blocked == 'media_changed':task['meta']['req']['url']='https://live-ex-speed.xiaoeknow.com/another.m3u8'
    if blocked == 'active':sniffer.tasks=lambda:[deepcopy(task),{'id':'other','status':'running'}]
    if blocked == 'output_after':
        install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)
        task['meta']['opts']['name']='other-compressed.mp4'
        with pytest.raises(EnrichmentError):resume_checkpoint_download(service,capture)
        assert calls == []
    elif blocked and blocked != 'restored_labels':
        with pytest.raises(EnrichmentError):install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)
        if blocked == 'install_failed':
            with pytest.raises(EnrichmentError):resume_checkpoint_download(service,capture)
        assert calls == []
    else:
        install_stopped_checkpoint_repair(service,capture,replacement_binary=binary)
        resume_checkpoint_download(service,capture)
        assert calls == [task['id']]
