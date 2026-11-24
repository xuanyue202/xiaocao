import hashlib
import json
from pathlib import Path

import pytest

from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.recorded_terminal_repair import inspect_terminal_task


@pytest.fixture
def stopped(tmp_path):
    resource, file_id, cid = 'v_' + 'a'*24, '5001834828749775294', 'candidate'
    media = tmp_path/'recording-compressed.mp4'
    media.write_bytes(b'partial')
    cache = Path(str(media)+'.hls-cache'); cache.mkdir()
    (cache/'terminal.json').write_text(json.dumps({'status':403}))
    (cache/'binding.json').write_text(json.dumps({'Binding':'a'*64,'Manifest':'b'*64,'Segments':2}))
    blob = cache/(('c'*64)+'.ts.bin'); blob.write_bytes(b'verified-segment')
    Path(str(blob)+'.json').write_text(json.dumps({'sha256':hashlib.sha256(blob.read_bytes()).hexdigest(), 'size':blob.stat().st_size}))
    from xiaocao.kol.recorded_recovery import resource_hash
    old_url='https://t-vod.h5.xed.plus/account/12345678'+file_id+'/drm/v.f123.m3u8'
    current = {'job_id':'original','status':'download_failed','download_task_id':'task',
        'candidate_key':'id:'+cid,'candidate':{'id':cid},'expected_media_file_id':file_id,
        'download_task':{'meta':{'opts':{'path':str(tmp_path),'name':media.name}}},
        'expected_source':{'source_resource_id':resource},
        'recorded_replay_binding':{'candidate_id':cid,'capture_job_id':'original','media_file_id':file_id,
          'recording':{'resource_id':resource}, 'media_resource_sha256':resource_hash(old_url),
          'finite_playlist':{'ended':True,'segments':2,'sha256':'b'*64}}}
    task = {'id':'task','status':'pause','protocol':'stream','meta':{'req':{'url':old_url},'opts':{'path':str(tmp_path),'name':media.name},
        'labels':{'capture_id':cid,'recorded_resource_id':resource,'recorded_media_file_id':file_id,
          'type':'live_capture','compress_inline':'true','checkpoint_basis':'verified_hls_segments','checkpoint_segments':'2'}}}
    return current,task,cache,tmp_path


def test_terminal_preflight_preserves_all_original_bytes(stopped):
    current,task,cache,root = stopped
    before = {p.name:p.read_bytes() for p in cache.iterdir()}
    result = inspect_terminal_task(current,[task],output_root=root)
    assert result['task_id']=='task' and result['verified_cached_segments']==1
    assert result['terminal_status']==403 and result['partial_size_bytes']==7
    assert before == {p.name:p.read_bytes() for p in cache.iterdir()}


def test_terminal_preflight_fails_closed_on_ambiguous_or_changed_evidence(stopped):
    current,task,cache,root = stopped
    for tasks in ([task, task], [task, {'id':'other','status':'running'}],
                  [task, {'id':'other','status':'done','meta':{'labels':{'capture_id':'candidate'}}}], []):
        with pytest.raises(EnrichmentError): inspect_terminal_task(current,tasks,output_root=root)
    with pytest.raises(EnrichmentError):
        inspect_terminal_task({**current,'expected_media_file_id':'99999999'},[task],output_root=root)
    blob = next(cache.glob('*.ts.bin')); blob.write_bytes(b'wrong')
    with pytest.raises(EnrichmentError): inspect_terminal_task(current,[task],output_root=root)


def _terminal_service(stopped, tmp_path, monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    import xiaocao.kol.recorded_flow  # Bind its production imports before patching the collector.
    import xiaocao.kol.recorded_recovery as recovery
    from xiaocao.kol.recorded_recovery import resource_hash
    current, task, _, output_root = stopped
    cid = current['candidate']['id']
    identity = 'kol-wechat-test'
    item = {'identity':identity,'capture_job_id':'original','published_at':'2026-11-17T16:27:00+08:00',
            'message_sha256':'d'*64}
    binding = current['recorded_replay_binding']
    provider_path='/account/123456785001834828749775294/drm/v.f123.m3u8'
    old_url='https://t-vod.h5.xed.plus'+provider_path
    alias_url='https://encrypt-k-vod.xet.tech'+provider_path
    binding.update(identity=identity,source_message_sha256=item['message_sha256'],published_at=item['published_at'],
        app_id='appTest', media_resource_sha256=resource_hash(old_url), material_id='material')
    binding['recording']['course_id']='course_Example'
    current.update(source_subscription_id=identity,source_published_at=item['published_at'],source_message_sha256=item['message_sha256'])
    current['expected_source'].update(source_app_id='appTest',source_identity='xiaoetong:appTest:'+binding['recording']['resource_id'])
    current['checkpoint_resume_claim']={'task_id':'task'}
    current['checkpoint_resume_receipt']={'id':'task'}
    proof = {**binding,'candidate_id':'fresh-alias','media_resource_sha256':resource_hash(alias_url),'player_duration_seconds':100,
             'player_left':True,'observation_receipt_path':'observation'}
    root=tmp_path/'subscription'/'items'/identity; root.mkdir(parents=True)
    proof_path=root/'alias.json'; proof_path.write_text(json.dumps(proof))
    monkeypatch.setattr(recovery,'validate_recorded_proof',lambda *a: None)
    monkeypatch.setattr(recovery,'collect_recorded_proof',lambda *a,**k:proof)
    class Store:
        def __init__(self):
            self.current=deepcopy(current); self.events=[]; self.path=tmp_path/'capture-ledger.jsonl'; self.path.touch()
        def latest(self, _): return deepcopy(self.current)
        def transition(self, old, event, **changes):
            assert old == self.current
            self.current={**old,**deepcopy(changes),'event':event}; self.events.append(event)
            with self.path.open('a') as handle: handle.write(json.dumps(self.current)+'\n')
            return deepcopy(self.current)
    store=Store()
    class Sniffer:
        def __init__(self): self.task=deepcopy(task); self.calls=[]; self.fail_prepare=False
        def candidates(self):
            merchant='https://appTest.h5.xiaoeknow.com/xe.material-center.play/getPlayUrl'
            return [dict(id=cid,url=old_url,media_type='m3u8',source_url=merchant,source_path='/xe.material-center.play/getPlayUrl'),
                    dict(id='fresh-alias',url=alias_url,media_type='m3u8',source_url=merchant,source_path='/xe.material-center.play/getPlayUrl')]
        def complete_tasks_for_reconciliation(self): return [deepcopy(self.task)]
        def prepare_recorded_terminal_revision(self, task_id, **kwargs):
            assert store.events[-1]=='recorded_terminal_revision_claimed'
            self.calls.append('prepare')
            if self.fail_prepare: raise RuntimeError('lost response')
            name='recording-compressed (1).mp4'; revision='f'*64
            self.task['meta']['opts']['name']=name
            self.task['meta']['labels'].update(media_repair_revision=revision,recorded_ticket_alias_id='fresh-alias',
                media_repair_previous_sha256=kwargs['partial_sha256'],media_repair_previous_name='recording-compressed.mp4')
            return {'id':task_id,'previous_sha256':kwargs['partial_sha256'],'previous_name':'recording-compressed.mp4',
                    'name':name,'revision':revision,'status':'pause'}
        def start_recorded_terminal_revision(self, task_id, *, revision):
            assert store.events[-1]=='recorded_terminal_resume_claimed'
            self.calls.append('start'); self.task['status']='running'
            return {'id':task_id,'revision':revision}
    sniffer=Sniffer()
    service=SimpleNamespace(output_dir=root,capture_store=store,sniffer=sniffer,_event=lambda *a,**k:None)
    return service,item,proof_path,output_root


def test_terminal_revision_preserves_task_and_claims_before_effects(stopped,tmp_path,monkeypatch):
    from xiaocao.kol.recorded_terminal_repair import prepare_terminal_revision, resume_terminal_revision
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    prepared=prepare_terminal_revision(service,item,proof,output_root=root)
    assert prepared['media_repair']['state']=='prepared'
    assert prepared['download_task_id']=='task'
    with pytest.raises(EnrichmentError,match='already claimed'):
        prepare_terminal_revision(service,item,proof,output_root=root)
    started=resume_terminal_revision(service,'original')
    assert started['download_task_id']=='task' and started['media_repair']['state']=='running'
    assert service.sniffer.calls==['prepare','start']
    assert resume_terminal_revision(service,'original')['media_repair']['state']=='running'
    assert service.sniffer.calls==['prepare','start']


def test_terminal_prepare_lost_response_never_blindly_resubmits(stopped,tmp_path,monkeypatch):
    from xiaocao.kol.recorded_terminal_repair import prepare_terminal_revision
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    service.sniffer.fail_prepare=True
    with pytest.raises(RuntimeError,match='lost response'):
        prepare_terminal_revision(service,item,proof,output_root=root)
    assert service.capture_store.current['media_repair']['state']=='preparing'
    with pytest.raises(EnrichmentError,match='already claimed'):
        prepare_terminal_revision(service,item,proof,output_root=root)
    assert service.sniffer.calls==['prepare']


def test_terminal_alias_uses_same_original_and_exact_browser_shape(stopped,tmp_path,monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo
    import xiaocao.kol.recorded_terminal_repair as terminal
    import xiaocao.kol.human_playback as playback
    import xiaocao.kol.recorded_recovery as recovery
    import xiaocao.kol.replay_catalog as catalog
    import xiaocao.kol.xiaocao_wechat as wechat
    service,item,_,root=_terminal_service(stopped,tmp_path,monkeypatch)
    binding=service.capture_store.current['recorded_replay_binding']
    selected={**binding['recording'],'title':'11月17日复盘大师班直播','duration_seconds':4215,'course_id':'course_Example'}
    binding['recording']=selected
    subroot=service.output_dir.parent.parent
    (subroot.parent/'native_share_bridge.json').write_text(json.dumps({'replay_catalog':{}}))
    config=SimpleNamespace(origin='https://appExample.h5.xiaoeknow.com',learning_url='https://course.example/',course_id='course_Example',app_id='appTest')
    monkeypatch.setattr(catalog.ReplayCatalogConfig,'from_dict',lambda _ :config)
    class Reader:
        def __init__(self,_): self.session=SimpleNamespace(close=lambda:None)
        def read(self): return [selected]
    monkeypatch.setattr(catalog,'ReplayCatalogReader',Reader)
    monkeypatch.setattr(catalog,'match_original',lambda rows,published: {**rows[0], 'page_url':'https://course.example/exact'})
    monkeypatch.setattr(catalog,'verify_original',lambda *a:None)
    monkeypatch.setattr(catalog,'verify_catalogue_binding',lambda *a:None)
    monkeypatch.setattr(wechat,'read_original_history',lambda *a:{})
    monkeypatch.setattr(wechat,'parse_xiaocao_live_messages',lambda _:[])
    monkeypatch.setattr(playback,'enable_capture_listener_pac',lambda:None)
    proof={**binding,'candidate_id':'fresh-alias','media_resource_sha256':recovery.resource_hash(service.sniffer.candidates()[1]['url']),
           'player_duration_seconds':4215,'player_left':True}
    monkeypatch.setattr(recovery,'collect_recorded_proof',lambda *a,**k:proof)
    requests=[]
    def exchange(request,_item):
        requests.append(request)
        return {'action':'observe_authorized_recorded_course','subscription_id':item['identity'],
                'status':'observed','candidate_id':'fresh-alias','player_duration_seconds':4215,'player_left':True}
    sub=SimpleNamespace(output_dir=subroot,history_reader=lambda:{},clock=lambda:datetime(2026,11,24,19,tzinfo=ZoneInfo('Asia/Shanghai')),
        human_entry_session_id='test-session',capture_driver=SimpleNamespace(),_exchange_browser=exchange,
        _validate_browser_response=lambda *a:None)
    path=terminal.observe_terminal_alias(sub,item,service,output_root=root)
    assert json.loads(path.read_text())==proof
    assert {k:requests[0]['recording'][k] for k in selected}==selected and requests[0]['subscription_id']==item['identity']
    assert requests[0]['recording_url'].split('?')[0].endswith('/'+selected['resource_id'])


def test_terminal_alias_account_login_stops_without_media_claim(stopped,tmp_path,monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo
    import xiaocao.kol.recorded_terminal_repair as terminal
    import xiaocao.kol.human_playback as playback
    import xiaocao.kol.recorded_recovery as recovery
    import xiaocao.kol.replay_catalog as catalog
    import xiaocao.kol.xiaocao_wechat as wechat
    from xiaocao.kol.enrichment_types import EnrichmentDiagnosticError
    service,item,_,root=_terminal_service(stopped,tmp_path,monkeypatch)
    selected=service.capture_store.current['recorded_replay_binding']['recording']
    subroot=service.output_dir.parent.parent
    (subroot.parent/'native_share_bridge.json').write_text(json.dumps({'replay_catalog':{}}))
    config=SimpleNamespace(origin='https://appExample.h5.xiaoeknow.com',learning_url='https://course.example/',course_id='course_Example',app_id='appTest')
    monkeypatch.setattr(catalog.ReplayCatalogConfig,'from_dict',lambda _:config)
    class Reader:
        def __init__(self,_): self.session=SimpleNamespace(close=lambda:None)
        def read(self): return [selected]
    monkeypatch.setattr(catalog,'ReplayCatalogReader',Reader)
    monkeypatch.setattr(catalog,'match_original',lambda rows,published:rows[0])
    monkeypatch.setattr(catalog,'verify_original',lambda *a:None)
    monkeypatch.setattr(catalog,'verify_catalogue_binding',lambda *a:None)
    monkeypatch.setattr(wechat,'read_original_history',lambda *a:{})
    monkeypatch.setattr(wechat,'parse_xiaocao_live_messages',lambda _:[])
    monkeypatch.setattr(playback,'enable_capture_listener_pac',lambda:None)
    monkeypatch.setattr(recovery,'collect_recorded_proof',lambda *a,**k:pytest.fail('login is not media'))
    sub=SimpleNamespace(output_dir=subroot,history_reader=lambda:{},clock=lambda:datetime(2026,11,24,19,tzinfo=ZoneInfo('Asia/Shanghai')),
        human_entry_session_id='login-session',capture_driver=SimpleNamespace(),_validate_browser_response=lambda *a:None,
        _exchange_browser=lambda req,item:{'action':'observe_authorized_recorded_course','subscription_id':item['identity'],'status':'account_login_required'})
    with pytest.raises(EnrichmentDiagnosticError) as exc:
        terminal.observe_terminal_alias(sub,item,service,output_root=root)
    assert exc.value.diagnostic_code=='recorded_course_account_login_required'
    assert service.sniffer.calls==[] and service.capture_store.events==[]


def test_terminal_preparation_rejects_changed_alias_before_effect(stopped,tmp_path,monkeypatch):
    from xiaocao.kol.recorded_terminal_repair import prepare_terminal_revision
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    value=json.loads(proof.read_text()); value['media_file_id']='5001834828749775295'; proof.write_text(json.dumps(value))
    with pytest.raises(EnrichmentError,match='changed original'):
        prepare_terminal_revision(service,item,proof,output_root=root)
    assert service.sniffer.calls==[] and service.capture_store.events==[]


def test_terminal_resume_retains_claim_when_provider_reply_is_lost(stopped,tmp_path,monkeypatch):
    from xiaocao.kol.recorded_terminal_repair import prepare_terminal_revision, resume_terminal_revision
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    prepare_terminal_revision(service,item,proof,output_root=root)
    def lost(task_id, *, revision):
        service.sniffer.calls.append('start'); raise RuntimeError('reply lost')
    service.sniffer.start_recorded_terminal_revision=lost
    with pytest.raises(RuntimeError,match='reply lost'): resume_terminal_revision(service,'original')
    assert service.capture_store.current['media_repair']['state']=='resume_claimed'
    with pytest.raises(EnrichmentError,match='effect reconciliation'): resume_terminal_revision(service,'original')
    assert service.sniffer.calls==['prepare','start']
    service.sniffer.task['status']='running'
    recovered=resume_terminal_revision(service,'original')
    assert recovered['media_repair']['state']=='running' and recovered['media_repair']['resume_readback']['id']=='task'
    assert service.sniffer.calls==['prepare','start']


def test_backend_repair_reconciles_exact_task_before_and_after_replacement(stopped,tmp_path,monkeypatch):
    from contextlib import nullcontext
    from xiaocao.kol.recorded_terminal_repair import restart_terminal_backend
    import xiaocao.yangsheng.capture as yangsheng
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,_,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    monkeypatch.setattr(terminal,'_require_shared_backend_idle',lambda _:None)
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    installed=tmp_path/'backend'; installed.write_bytes(b'old')
    replacement=tmp_path/'backend.new'; replacement.write_bytes(b'new-reviewed-code')
    digest=hashlib.sha256(replacement.read_bytes()).hexdigest()
    service.sniffer_binary=installed
    service.start=lambda:{'capture_job_id':'original'}
    calls=[]
    def replace(current, *, replacement_binary, preserve_native_arm):
        assert current['download_task_id']=='task' and preserve_native_arm
        calls.append('replace'); installed.write_bytes(replacement_binary.read_bytes())
        return {'capture_job_id':'original','status':'ready'}
    service._replace_sniffer_for_repair=replace
    result=restart_terminal_backend(None,service,item,output_root=root,replacement_binary=replacement,replacement_sha256=digest)
    assert result['task_id']=='task' and result['backend_sha256']==digest and calls==['replace']
    restart_terminal_backend(None,service,item,output_root=root,replacement_binary=replacement,replacement_sha256=digest)
    assert calls==['replace']


def test_backend_repair_never_restarts_with_an_active_provider_task(stopped,tmp_path,monkeypatch):
    from contextlib import nullcontext
    from xiaocao.kol.recorded_terminal_repair import restart_terminal_backend
    import xiaocao.yangsheng.capture as yangsheng
    service,item,_,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    import xiaocao.kol.recorded_terminal_repair as terminal
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    service.start=lambda:{'capture_job_id':'original'}
    service.sniffer.complete_tasks_for_reconciliation=lambda:[service.sniffer.task,{'id':'unrelated','status':'running'}]
    service._replace_sniffer_for_repair=lambda *a,**k:pytest.fail('must not replace active backend')
    with pytest.raises(EnrichmentError,match='active provider task'):
        restart_terminal_backend(None,service,item,output_root=root,replacement_binary=tmp_path/'unused',replacement_sha256='f'*64)


def test_terminal_runtime_keeps_observation_outside_lifecycle_lock(monkeypatch,tmp_path):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from scripts import kol_daily
    import xiaocao.kol.recorded_terminal_repair as terminal
    import xiaocao.yangsheng.capture as yangsheng
    steps=[]; held=[]
    item={'identity':'original','capture_job_id':'capture'}
    service=SimpleNamespace(capture_store=SimpleNamespace(latest=lambda _:{'download_task':{'meta':{'opts':{'path':str(tmp_path)}}}}))
    monkeypatch.setattr(kol_daily,'WechatCliHistoryReader',lambda *a,**k:object())
    monkeypatch.setattr(kol_daily,'XiaocaoLiveCaptureDriver',lambda *a,**k:SimpleNamespace(_service=lambda _:service))
    monkeypatch.setattr(kol_daily,'XiaocaoWechatLiveSubscription',lambda *a,**k:SimpleNamespace(_load=lambda:{'items':{'original':item}}))
    @contextmanager
    def lease(**kwargs):
        held.append(True); steps.append('lease'); yield; held.pop()
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lease)
    monkeypatch.setattr(terminal,'restart_terminal_backend',lambda *a,**k:steps.append('restart'))
    def observe(*args,**kwargs):
        assert not held; steps.append('observe'); return tmp_path/'proof.json'
    monkeypatch.setattr(terminal,'observe_terminal_alias',observe)
    def prepare(*args,**kwargs): assert held; steps.append('prepare')
    def resume(*args,**kwargs): assert held; steps.append('resume')
    monkeypatch.setattr(terminal,'prepare_terminal_revision',prepare)
    monkeypatch.setattr(terminal,'resume_terminal_revision',resume)
    runtime=kol_daily.DailyRuntime.__new__(kol_daily.DailyRuntime)
    runtime.args=SimpleNamespace(xiaocao_wechat_contact='contact',wechat_cli=tmp_path/'cli',wechat_history_limit=80,
        xiaocao_wechat_output_dir=tmp_path/'subscription',decision_output_dir=tmp_path/'decision',xiaocao_live_password='unused')
    runtime.xiaocao_wechat=lambda *,only_identity: steps.append('continue') or {'status':'waiting'}
    assert runtime.xiaocao_recorded_terminal_repair('original',replacement_binary=tmp_path/'binary',replacement_sha256='f'*64)=={'status':'waiting'}
    assert steps==['restart','observe','lease','prepare','resume','continue']


def test_terminal_preflight_rejects_unlabelled_same_resource_task(stopped):
    from xiaocao.kol.recorded_recovery import resource_hash
    current,task,_,root=stopped
    old=task['meta']['req']['url']
    url=old.replace('t-vod.h5.xed.plus','encrypt-k-vod.xet.tech')
    other={'id':'unlabelled','status':'done','meta':{'req':{'url':url+'?redacted'}}}
    with pytest.raises(EnrichmentError,match='another matching provider effect'):
        inspect_terminal_task(current,[task,other],output_root=root)


def test_shared_backend_idle_check_never_ignores_unfinished_owned_tasks(tmp_path,monkeypatch):
    import sqlite3
    from types import SimpleNamespace
    import xiaocao.kol.recorded_terminal_repair as terminal
    import xiaocao.yangsheng.runtime as runtime
    import xiaocao.yangsheng.native as native
    enabled=tmp_path/'shared-enabled.json'; enabled.write_text('{}')
    monkeypatch.setattr(runtime,'ENABLED',enabled); monkeypatch.setattr(runtime,'DEFAULT_ROOT',tmp_path)
    monkeypatch.setattr(native,'request',lambda *a:{'enabled':True,'post_processing_active':[]})
    db=sqlite3.connect(tmp_path/'catalog.sqlite')
    db.executescript('CREATE TABLE jobs(publisher TEXT,replay TEXT); CREATE TABLE artifacts(publisher TEXT,replay TEXT); INSERT INTO jobs VALUES ("p","r");'); db.commit()
    service=SimpleNamespace(sniffer=SimpleNamespace(base_url='http://127.0.0.1:2022'))
    with pytest.raises(EnrichmentError,match='unfinished owned tasks'): terminal._require_shared_backend_idle(service)
    db.execute('INSERT INTO artifacts VALUES (?,?)',('p','r')); db.commit(); db.close()
    terminal._require_shared_backend_idle(service)
    monkeypatch.setattr(native,'request',lambda *a:{'enabled':True,'post_processing_active':['active']})
    with pytest.raises(EnrichmentError,match='processing'): terminal._require_shared_backend_idle(service)


def test_terminal_claim_fsync_failure_prevents_provider_mutation(stopped,tmp_path,monkeypatch):
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(terminal.os,'fsync',lambda _:(_ for _ in ()).throw(OSError('sync unavailable')))
    with pytest.raises(OSError,match='sync unavailable'):
        terminal.prepare_terminal_revision(service,item,proof,output_root=root)
    assert service.sniffer.calls==[]


def test_backend_repair_durable_claim_precedes_replacement(stopped,tmp_path,monkeypatch):
    from contextlib import nullcontext
    import xiaocao.kol.recorded_terminal_repair as terminal
    import xiaocao.yangsheng.capture as yangsheng
    service,item,_,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    monkeypatch.setattr(terminal,'_require_shared_backend_idle',lambda _:None)
    service.sniffer_binary=tmp_path/'backend'; service.sniffer_binary.write_bytes(b'old')
    replacement=tmp_path/'backend.new'; replacement.write_bytes(b'new'); digest=hashlib.sha256(b'new').hexdigest()
    service.start=lambda:{'capture_job_id':'original'}
    service._replace_sniffer_for_repair=lambda *a,**k:pytest.fail('replacement must wait for durable claim')
    monkeypatch.setattr(terminal.os,'fsync',lambda _:(_ for _ in ()).throw(OSError('sync unavailable')))
    with pytest.raises(OSError,match='sync unavailable'):
        terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=replacement,replacement_sha256=digest)
    assert service.sniffer_binary.read_bytes()==b'old'


def test_terminal_original_source_mismatch_blocks_before_history_and_restart(stopped,tmp_path,monkeypatch):
    from types import SimpleNamespace
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,_,_=_terminal_service(stopped,tmp_path,monkeypatch)
    current=service.capture_store.latest('original'); current['source_message_sha256']='0'*64
    sub=SimpleNamespace(history_reader=lambda:pytest.fail('must reject changed original before history'))
    with pytest.raises(EnrichmentError,match='original source binding changed'):
        terminal._verify_terminal_original(sub,item,current)


def test_preparation_response_loss_reconciles_same_reserved_task(stopped,tmp_path,monkeypatch):
    from xiaocao.kol.recorded_terminal_repair import prepare_terminal_revision, reconcile_terminal_preparation
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    original=service.sniffer.prepare_recorded_terminal_revision
    def lost_after_prepare(task_id,**kwargs):
        original(task_id,**kwargs)
        raise RuntimeError('reply lost after preparation')
    service.sniffer.prepare_recorded_terminal_revision=lost_after_prepare
    with pytest.raises(RuntimeError,match='reply lost'):
        prepare_terminal_revision(service,item,proof,output_root=root)
    assert service.capture_store.current['media_repair']['state']=='preparing'
    service.sniffer.prepare_recorded_terminal_revision=original
    recovered=reconcile_terminal_preparation(service,item,output_root=root)
    assert recovered['media_repair']['state']=='prepared' and recovered['download_task_id']=='task'
    assert service.sniffer.calls==['prepare','prepare']  # Second call is only after exact reserved-task readback.


def test_unproved_preparation_never_repeats_provider_call(stopped,tmp_path,monkeypatch):
    from xiaocao.kol.recorded_terminal_repair import prepare_terminal_revision, reconcile_terminal_preparation
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    service.sniffer.fail_prepare=True
    with pytest.raises(RuntimeError): prepare_terminal_revision(service,item,proof,output_root=root)
    with pytest.raises(EnrichmentError,match='effect is uncertain'):
        reconcile_terminal_preparation(service,item,output_root=root)
    assert service.sniffer.calls==['prepare']


def test_cross_host_alias_requires_exact_provider_path_and_merchant(stopped,tmp_path,monkeypatch):
    from copy import deepcopy
    from xiaocao.kol.recorded_terminal_repair import _verified_same_file_alias
    from xiaocao.kol.recorded_recovery import resource_hash
    service,item,proof_path,_=_terminal_service(stopped,tmp_path,monkeypatch)
    binding=service.capture_store.latest('original')['recorded_replay_binding']; proof=json.loads(proof_path.read_text())
    assert _verified_same_file_alias(service,binding,proof)['original_host']=='t-vod.h5.xed.plus'
    assert _verified_same_file_alias(service,binding,proof)['alias_host']=='encrypt-k-vod.xet.tech'
    original=service.sniffer.candidates()
    for changed in ('path','host','port','merchant','material'):
        rows=deepcopy(original); candidate=rows[1]; p=deepcopy(proof)
        if changed=='path': candidate['url']=candidate['url'].replace('/account/','/another/')
        if changed=='host': candidate['url']=candidate['url'].replace('encrypt-k-vod.xet.tech','other.h5.xed.plus')
        if changed=='port': candidate['url']=candidate['url'].replace('encrypt-k-vod.xet.tech','encrypt-k-vod.xet.tech:443')
        if changed=='merchant': candidate['source_url']='https://wrong.example/xe.material-center.play/getPlayUrl'
        if changed=='material': p['material_id']='another-material'
        p['media_resource_sha256']=resource_hash(candidate['url'])
        service.sniffer.candidates=lambda:rows
        with pytest.raises(EnrichmentError): _verified_same_file_alias(service,binding,p)


def test_followup_backend_repair_preserves_original_claim_and_requires_predecessor(stopped,tmp_path,monkeypatch):
    from contextlib import nullcontext
    import xiaocao.yangsheng.capture as yangsheng
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,_,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    monkeypatch.setattr(terminal,'_require_shared_backend_idle',lambda _:None)
    installed=tmp_path/'backend'; installed.write_bytes(b'old')
    first=tmp_path/'backend.first'; first.write_bytes(b'first'); first_sha=hashlib.sha256(b'first').hexdigest()
    second=tmp_path/'backend.second'; second.write_bytes(b'second'); second_sha=hashlib.sha256(b'second').hexdigest()
    service.sniffer_binary=installed; service.start=lambda:{'capture_job_id':'original'}; calls=[]
    def replace(current, *, replacement_binary, preserve_native_arm):
        calls.append(replacement_binary.name); installed.write_bytes(replacement_binary.read_bytes()); return {'capture_job_id':'original'}
    service._replace_sniffer_for_repair=replace
    terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=first,replacement_sha256=first_sha)
    old_claim=service.capture_store.latest('original')['recorded_terminal_backend_claim']
    terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=second,replacement_sha256=second_sha)
    result=service.capture_store.latest('original')
    assert result['recorded_terminal_backend_claim']==old_claim
    assert result['recorded_terminal_backend_receipt']['backend_sha256']==first_sha
    assert result['recorded_terminal_backend_followup_receipt']['backend_sha256']==second_sha
    terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=second,replacement_sha256=second_sha)
    assert calls==['backend.first','backend.second']


def test_pending_preparation_requires_backend_drain_and_preserves_claim(stopped,tmp_path,monkeypatch):
    from contextlib import nullcontext
    import xiaocao.yangsheng.capture as yangsheng
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    monkeypatch.setattr(terminal,'_require_shared_backend_idle',lambda _:None)
    installed=tmp_path/'backend'; installed.write_bytes(b'old')
    replacement=tmp_path/'backend.new'; replacement.write_bytes(b'reviewed')
    digest=hashlib.sha256(replacement.read_bytes()).hexdigest()
    service.sniffer_binary=installed; service.start=lambda:{'capture_job_id':'original'}
    restarts=[]
    def replace(current, *, replacement_binary, preserve_native_arm):
        assert current['media_repair']['state']=='preparing'
        restarts.append(True); installed.write_bytes(replacement_binary.read_bytes())
        return {'capture_job_id':'original'}
    service._replace_sniffer_for_repair=replace
    service.sniffer.fail_prepare=True
    with pytest.raises(RuntimeError): terminal.prepare_terminal_revision(service,item,proof,output_root=root)
    old_claim=service.capture_store.latest('original')['media_repair']
    # An unchanged backend cannot prove the old request has drained.
    with pytest.raises(EnrichmentError,match='requires a separately claimed backend restart'):
        terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=installed,
            replacement_sha256=hashlib.sha256(installed.read_bytes()).hexdigest())
    assert restarts==[]
    terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=replacement,replacement_sha256=digest)
    reconciled=service.capture_store.latest('original')['media_repair']
    assert restarts==[True] and reconciled['state']=='absence_verified'
    assert {k:reconciled[k] for k in old_claim if k!='state'}=={k:v for k,v in old_claim.items() if k!='state'}
    assert reconciled['absence_receipt']['backend_restart_receipt']['backend_sha256']==digest
    service.sniffer.fail_prepare=False
    prepared=terminal.prepare_terminal_revision(service,item,proof,output_root=root)
    assert prepared['media_repair']['prior_attempt']==reconciled
    assert service.sniffer.calls==['prepare','prepare']


@pytest.mark.parametrize('kind',['matching_marker','unknown_marker','unmarked_reservation','changed_partial','provider_revision','downstream'])
def test_pending_preparation_with_unresolved_effect_never_restarts(stopped,tmp_path,monkeypatch,kind):
    from contextlib import nullcontext
    import xiaocao.yangsheng.capture as yangsheng
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    monkeypatch.setattr(terminal,'_require_shared_backend_idle',lambda _:None)
    installed=tmp_path/'backend'; installed.write_bytes(b'old')
    replacement=tmp_path/'backend.new'; replacement.write_bytes(b'new')
    service.sniffer_binary=installed; service.start=lambda:{'capture_job_id':'original'}
    service._replace_sniffer_for_repair=lambda *a,**kw:pytest.fail('uncertain effect must not be restarted')
    service.sniffer.fail_prepare=True
    with pytest.raises(RuntimeError): terminal.prepare_terminal_revision(service,item,proof,output_root=root)
    if kind=='matching_marker': (root/'other.reservation.json').write_text(json.dumps({'task_id':'task'}))
    if kind=='unknown_marker': (root/'other.reservation.json').write_text('{}')
    if kind=='unmarked_reservation': (root/'recording-compressed (1).mp4').touch()
    if kind=='changed_partial': (root/'recording-compressed.mp4').write_bytes(b'changed')
    if kind=='provider_revision': service.sniffer.task['meta']['labels']['media_repair_revision']='a'*64
    if kind=='downstream': service._event=lambda *a,**kw:{'effect':True}
    with pytest.raises(EnrichmentError):
        terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=replacement,
            replacement_sha256=hashlib.sha256(b'new').hexdigest())
    assert service.capture_store.latest('original')['media_repair']['state']=='preparing'


def test_reconciled_preparation_uses_third_backend_claim_without_overwrite(stopped,tmp_path,monkeypatch):
    from contextlib import nullcontext
    import xiaocao.yangsheng.capture as yangsheng
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    monkeypatch.setattr(terminal,'_require_shared_backend_idle',lambda _:None)
    installed=tmp_path/'backend'; installed.write_bytes(b'original')
    service.sniffer_binary=installed; service.start=lambda:{'capture_job_id':'original'}
    def replace(current, *, replacement_binary, preserve_native_arm):
        installed.write_bytes(replacement_binary.read_bytes()); return {'capture_job_id':'original'}
    service._replace_sniffer_for_repair=replace
    for value in (b'first', b'second'):
        candidate=tmp_path/('backend.'+value.decode()); candidate.write_bytes(value)
        terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=candidate,
            replacement_sha256=hashlib.sha256(value).hexdigest())
    before=service.capture_store.latest('original')
    old={k:v for k,v in before.items() if k.startswith('recorded_terminal_backend_')}
    service.sniffer.fail_prepare=True
    with pytest.raises(RuntimeError): terminal.prepare_terminal_revision(service,item,proof,output_root=root)
    candidate=tmp_path/'backend.third'; candidate.write_bytes(b'third')
    terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=candidate,
        replacement_sha256=hashlib.sha256(b'third').hexdigest())
    after=service.capture_store.latest('original')
    assert all(after[k]==v for k,v in old.items())
    assert after['recorded_terminal_backend_reconciled_followup_receipt']['backend_sha256']==hashlib.sha256(b'third').hexdigest()
    assert after['media_repair']['state']=='absence_verified'


def test_preparation_effect_appearing_during_drain_remains_uncertain(stopped,tmp_path,monkeypatch):
    from contextlib import nullcontext
    import xiaocao.yangsheng.capture as yangsheng
    import xiaocao.kol.recorded_terminal_repair as terminal
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    monkeypatch.setattr(yangsheng,'lifecycle_lease',lambda **kw:nullcontext())
    monkeypatch.setattr(terminal,'_verify_terminal_original',lambda *a:None)
    monkeypatch.setattr(terminal,'_require_shared_backend_idle',lambda _:None)
    installed=tmp_path/'backend'; installed.write_bytes(b'old')
    candidate=tmp_path/'backend.new'; candidate.write_bytes(b'new')
    service.sniffer_binary=installed; service.start=lambda:{'capture_job_id':'original'}
    service.sniffer.fail_prepare=True
    with pytest.raises(RuntimeError): terminal.prepare_terminal_revision(service,item,proof,output_root=root)
    def effect_during_restart(current, *, replacement_binary, preserve_native_arm):
        (root/'recording-compressed (1).mp4').touch()
        installed.write_bytes(replacement_binary.read_bytes())
        return {'capture_job_id':'original'}
    service._replace_sniffer_for_repair=effect_during_restart
    with pytest.raises(EnrichmentError,match='unbound revision output'):
        terminal.restart_terminal_backend(None,service,item,output_root=root,replacement_binary=candidate,
            replacement_sha256=hashlib.sha256(b'new').hexdigest())
    assert service.capture_store.latest('original')['media_repair']['state']=='preparing'
    assert service.sniffer.calls==['prepare']


def test_changed_absence_receipt_blocks_followup(stopped,tmp_path,monkeypatch):
    from xiaocao.kol.recorded_terminal_repair import _require_prior_absence_receipt
    service,item,proof,root=_terminal_service(stopped,tmp_path,monkeypatch)
    current=service.capture_store.latest('original')
    preflight=inspect_terminal_task(current,service.sniffer.complete_tasks_for_reconciliation(),output_root=root)
    current['media_repair']={'state':'absence_verified','preflight':preflight,'absence_receipt':{'task_id':'other'}}
    with pytest.raises(EnrichmentError,match='absence receipt changed'):
        _require_prior_absence_receipt(current,preflight)
