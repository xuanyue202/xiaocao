import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from xiaocao.kol.capture import CaptureJobStore, resolve_candidate
from xiaocao.kol.recorded_recovery import (
    collect_recorded_proof, bind_recorded_recovery, validate_recorded_proof,
)
from xiaocao.kol.enrichment_types import EnrichmentError


IDENTITY='kol-wechat-'+'a'*24
CAPTURE='kol-original'
RESOURCE='v_6aeac14ce4b023c0863c984c'
APP='appsnm3rlcp3566'
COURSE='course_Example123'
ORIGIN=f'https://{APP}.h5.xiaoeknow.com'
MEDIA='https://encrypt-k-vod.xet.tech/account/c700e05f5001834826931137742/drm/v.f421220.m3u8'


@pytest.fixture
def recorded(tmp_path,monkeypatch):
    root=tmp_path/'subscription';folder=root/'items'/IDENTITY;folder.mkdir(parents=True)
    item=dict(identity=IDENTITY,capture_job_id=CAPTURE,mini_program_token='Token123',
        mini_program_name='见势擒龙团',message_sha256='b'*64,published_at='2026-11-04T09:04:00+08:00',
        status='awaiting_playback',contact='registered',contact_username='exact',entry_kind='wechat_mini_program')
    (root/'manifest.json').write_text(json.dumps({'schema_version':1,'items':{IDENTITY:item}}))
    (tmp_path/'native_share_bridge.json').write_text(json.dumps({'replay_catalog':dict(
        app_id=APP,course_id=COURSE,mini_program_token='Token123')}))
    claim=folder/'observation.json';claim.write_text(json.dumps(dict(identity=IDENTITY,
        capture_job_id=CAPTURE,resource_id=RESOURCE,observed_after='2026-11-04T15:09:59+08:00')))
    debug=tmp_path/'backend'/'elive_live_debug';(debug/'json').mkdir(parents=True);(debug/'m3u8').mkdir()
    rows=[dict(chapter_id=RESOURCE,chapter_title='大师班早盘直播11月4日',video_length=2311,course_id=COURSE)]
    payloads={
        '/xe.course.business_go.avoidlogin.e_course.resource_catalog_list.get/1.0.0':dict(subscribe=1,available=1,list=rows),
        '/xe.course.business_go.video.detail_info.get/2.0.0':dict(video_info=dict(app_id=APP,resource_id=RESOURCE,video_length=2311,play_sign='opaque-private',material_id='m_exact')),
        '/xe.material-center.play/getPlayUrl':{'opaque-private':dict(material_id='m_exact',play_list=dict(url=MEDIA+'?sign=private'))},
    }
    events=[]
    for n,(route,data) in enumerate(payloads.items()):
        p=debug/'json'/f'{n}.json';p.write_text(json.dumps(dict(code=0,data=data)))
        events.append(dict(kind='response.body',status=200,url=ORIGIN+route,at='2026-11-04T15:10:26+08:00',file=str(p)))
    hls=debug/'m3u8'/'actual.m3u8';hls.write_text('#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:2310.761,\na.ts\n#EXT-X-ENDLIST\n')
    events.append(dict(kind='response.body',status=200,url=MEDIA,at='2026-11-04T15:10:28+08:00',file=str(hls)))
    (debug/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    candidate=dict(id='exact',live_id='l_reused_room',title='wrong evening context',filename='wrong.mp4',
        captured='2026-11-04 15:10:26',media_type='m3u8',url=MEDIA,source_url=ORIGIN+'/xe.material-center.play/getPlayUrl')
    store=CaptureJobStore(folder/'capture_jobs.jsonl')
    store._append(dict(job_id=CAPTURE,status='awaiting_capture',created_at='2026-11-04T13:59:56+08:00',baseline_candidate_keys=[]))
    service=SimpleNamespace(sniffer_binary=tmp_path/'backend'/'binary',capture_store=store,
        sniffer=SimpleNamespace(candidates=lambda:[copy.deepcopy(candidate)]))
    class Driver:
        def _service(self,identity):assert identity==IDENTITY;return service
        def require_idle_human_entry(self,identity,capture_id):
            current=store.latest(capture_id)
            if current.get('status')!='awaiting_capture' or current.get('expected_source'):
                raise EnrichmentError('not idle')
    driver=Driver()
    import xiaocao.kol.xiaocao_wechat as wechat
    monkeypatch.setattr(wechat,'WechatCliHistoryReader',lambda:lambda:{})
    monkeypatch.setattr(wechat,'parse_xiaocao_live_messages',lambda _: [item])
    proof=collect_recorded_proof(root,IDENTITY,CAPTURE,'exact',player_duration=2310.761,
        player_left=True,driver=driver,observation_path=claim)
    return root,item,driver,service,candidate,proof,folder


def test_recorded_proof_binds_merchant_course_media_and_finite_playlist_without_tickets(recorded):
    _,item,_,_,_,proof,_=recorded
    validate_recorded_proof(proof,item,CAPTURE)
    assert proof['media_file_id']=='5001834826931137742'
    assert proof['finite_playlist']['ended'] is True
    assert 'sign=private' not in json.dumps(proof)


def test_reused_candidate_needs_fresh_exact_hls_after_new_observation(recorded):
    root,_,driver,_,_,_,folder=recorded
    p=folder/'observation.json';claim=json.loads(p.read_text())
    claim['observed_after']='2026-11-04T15:10:27+08:00';p.write_text(json.dumps(claim))
    debug=root.parent/'backend'/'elive_live_debug'
    events=[json.loads(v) for v in (debug/'events.jsonl').read_text().splitlines()]
    for e in events[:-1]:e['at']='2026-11-04T15:10:28+08:00'
    (debug/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    result=collect_recorded_proof(root,IDENTITY,CAPTURE,'exact',player_duration=2310.761,
        player_left=True,driver=driver,observation_path=p)
    assert result['candidate_id']=='exact'
    events[-1]['at']='2026-11-04T15:10:26+08:00'
    (debug/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    with pytest.raises(EnrichmentError,match='finite media evidence unavailable'):
        collect_recorded_proof(root,IDENTITY,CAPTURE,'exact',player_duration=2310.761,
            player_left=True,driver=driver,observation_path=p)


@pytest.mark.parametrize('field,value',[('entitled_course',False),('player_left',False),
    ('identity','kol-wechat-'+'c'*24),('source_message_sha256','c'*64)])
def test_recorded_proof_rejects_changed_authority_or_original(recorded,field,value):
    _,item,_,_,_,proof,_=recorded
    with pytest.raises(EnrichmentError):validate_recorded_proof({**proof,field:value},item,CAPTURE)


def test_binding_keeps_capture_and_transport_id_and_corrects_only_recorded_presentation(recorded):
    root,_,driver,service,candidate,proof,folder=recorded
    path=folder/'proof.json';path.write_text(json.dumps(proof))
    result=bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    assert result['capture_job_id']==CAPTURE and result['download_started'] is False
    current=service.capture_store.latest(CAPTURE)
    assert current['expected_source']['source_resource_id']==RESOURCE
    assert current['candidate']['live_id']=='l_reused_room'
    assert current['candidate_key']=='id:exact'
    resolved=resolve_candidate(current,[candidate])
    assert resolved['filename']=='20261104 大师班早盘直播11月4日.mp4'
    assert resolved['recorded_resource_id']==RESOURCE
    assert resolved['recorded_media_file_id']=='5001834826931137742'
    assert resolve_candidate(current,[{**candidate,'url':MEDIA.replace('v.f421220','v.f999')}]) is None
    bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    assert service.capture_store.latest(CAPTURE)['candidate_key']=='id:exact'


def test_changed_raw_merchant_evidence_blocks_binding(recorded):
    root,_,driver,_,_,proof,folder=recorded
    Path(proof['catalog_evidence']['path']).write_text(json.dumps(dict(code=0,data=dict(subscribe=0,available=1,list=[]))))
    path=folder/'proof.json';path.write_text(json.dumps(proof))
    with pytest.raises(EnrichmentError):bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)


def test_changed_merchant_evidence_blocks_backend_replacement(recorded):
    from xiaocao.kol.recorded_recovery import restart_recorded_backend
    root,_,driver,service,_,proof,folder=recorded
    path=folder/'proof.json';path.write_text(json.dumps(proof))
    Path(proof['play_evidence']['path']).unlink()
    service._replace_sniffer_for_repair=lambda *a,**k:pytest.fail('replacement must not run')
    with pytest.raises((EnrichmentError,FileNotFoundError)):
        restart_recorded_backend(root,IDENTITY,CAPTURE,path,Path('replacement'),driver=driver)


def test_browser_reply_deadline_includes_partial_line():
    import importlib.util
    import os
    spec=importlib.util.spec_from_file_location('recorded_cli',Path(__file__).parents[1]/'scripts/kol_recorded_recovery.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    read_fd,write_fd=os.pipe()
    try:
        os.write(write_fd,b'{')
        with os.fdopen(read_fd,'rb') as stream:
            with pytest.raises(ValueError,match='timeout'):
                module.read_reply(stream,timeout=0.02)
    finally:
        os.close(write_fd)


@pytest.mark.parametrize('change',['key','material'])
def test_unrelated_play_response_cannot_supply_recording_media(recorded,change):
    root,_,driver,_,_,proof,folder=recorded
    p=Path(proof['play_evidence']['path']);data=json.loads(p.read_text())
    if change=='key':data['data']['other-opaque']=data['data'].pop('opaque-private')
    else:data['data']['opaque-private']['material_id']='m_other'
    p.write_text(json.dumps(data))
    with pytest.raises(EnrichmentError,match='detail/play response mapping'):
        collect_recorded_proof(root,IDENTITY,CAPTURE,'exact',player_duration=2310.761,
            player_left=True,driver=driver,observation_path=folder/'observation.json')


def test_existing_foreign_candidate_is_not_rebound_or_reported_success(recorded):
    root,_,driver,service,_,proof,folder=recorded
    store=service.capture_store
    store.transition(store.latest(CAPTURE),'capture_detected',status='captured',candidate=dict(id='other'),
        expected_source=dict(source_identity='other'),candidate_key='id:other')
    path=folder/'proof.json';path.write_text(json.dumps(proof))
    before=store.events()
    with pytest.raises(EnrichmentError,match='existing candidate binding differs'):
        bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    assert store.events()==before


def test_partial_source_bind_can_resume_same_proof_without_new_observation(recorded):
    import hashlib
    from xiaocao.kol.capture import canonical_xiaoetong_source
    root,_,driver,service,_,proof,folder=recorded
    path=folder/'proof.json';body=json.dumps(proof).encode();path.write_bytes(body)
    binding={**proof,'proof_path':str(path),'proof_sha256':hashlib.sha256(body).hexdigest()}
    store=service.capture_store
    store.transition(store.latest(CAPTURE),'recorded_course_source_bound',
        expected_source=canonical_xiaoetong_source(ORIGIN+'/p/course/video/'+RESOURCE),
        expected_media_file_id=proof['media_file_id'],recorded_replay_binding=binding)
    result=bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    assert result['capture_job_id']==CAPTURE
    assert store.latest(CAPTURE)['candidate_key']=='id:exact'
    assert len(list(folder.glob('observation*')))==1


def test_partial_binding_with_conflicting_source_cannot_be_overwritten(recorded):
    import hashlib
    root,_,driver,service,_,proof,folder=recorded
    path=folder/'proof.json';body=json.dumps(proof).encode();path.write_bytes(body)
    binding={**proof,'proof_path':str(path),'proof_sha256':hashlib.sha256(body).hexdigest()}
    store=service.capture_store
    store.transition(store.latest(CAPTURE),'recorded_course_source_bound',
        expected_source=dict(source_identity='other'),expected_media_file_id='9999999999',
        recorded_replay_binding=binding)
    before=store.events()
    with pytest.raises(EnrichmentError,match='partial binding changed'):
        bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    assert store.events()==before


@pytest.mark.parametrize('transport',['l_reused_room',''])
def test_complete_recorded_acceptance_survives_cleanup_and_rejects_changed_file_label(recorded,monkeypatch,transport):
    import hashlib
    from xiaocao.kol.xiaocao_capture_acceptance import inspect_acceptance
    root,_,driver,service,candidate,proof,folder=recorded
    candidate['live_id']=transport
    path=folder/'proof.json';path.write_text(json.dumps(proof))
    bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    labels=dict(capture_id='exact',live_id=transport,recorded_resource_id=RESOURCE,
        recorded_media_file_id=proof['media_file_id'],type='live_capture',compress='true',
        compress_inline='true',hls_duration_sec='2310.761')
    store=service.capture_store
    store.transition(store.latest(CAPTURE),'download_completed',status='downloaded',download_task_id='exact-task',
        download_task=dict(id='exact-task',status='done',meta=dict(labels=labels)))
    media=folder/'video-compressed.mp4';media.write_bytes(b'valid')
    events=[dict(event=e,capture_job_id=CAPTURE,live_id=transport,media_path=str(media),
        media_sha256=hashlib.sha256(media.read_bytes()).hexdigest(),updated_at='2026-11-04T15:50:00+08:00')
        for e in ['media_validated','cloud_handoff_published']]
    (folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    m=json.loads((root/'manifest.json').read_text());m['items'][IDENTITY]['status']='completed'
    (root/'manifest.json').write_text(json.dumps(m))
    monkeypatch.setattr('xiaocao.kol.xiaocao_capture_acceptance.subprocess.run',lambda *a,**k:
        SimpleNamespace(returncode=0,stdout=json.dumps({'format':{'duration':'2310.761'}})))
    def offline(_):raise AssertionError('must not query a cleaned backend')
    result=inspect_acceptance(root,[IDENTITY],required_count=1,fetch_json=offline,probe_media=lambda _:True)
    assert result['status']=='passed',result
    assert result['items'][0]['checks']['recorded_course_surface'] is True
    assert 'wechat_mini_program_surface' not in result['items'][0]['checks']
    current=store.latest(CAPTURE);current['download_task']['meta']['labels']['recorded_media_file_id']='wrong'
    store.transition(current,'changed')
    assert inspect_acceptance(root,[IDENTITY],required_count=1,fetch_json=offline,probe_media=lambda _:True)['status']=='failed'


def test_recorded_ticket_refresh_preserves_original_candidate_and_claim(recorded):
    from xiaocao.kol.recorded_recovery import refresh_recorded_ticket
    root,_,driver,service,candidate,proof,folder=recorded
    original=folder/'proof.json';original.write_text(json.dumps(proof))
    bind_recorded_recovery(root,IDENTITY,CAPTURE,original,driver=driver)
    store=service.capture_store;store.transition(store.latest(CAPTURE),'download_claimed',status='download_claimed')
    fresh={**candidate,'id':'fresh-ticket','live_id':''}
    service.sniffer.candidates=lambda:[candidate,fresh]
    service.sniffer.complete_tasks_for_reconciliation=lambda:[]
    renewed=collect_recorded_proof(root,IDENTITY,CAPTURE,'fresh-ticket',player_duration=2310.761,
        player_left=True,driver=driver,observation_path=folder/'observation.json')
    path=folder/'fresh-proof.json';path.write_text(json.dumps(renewed))
    current=refresh_recorded_ticket(root,IDENTITY,CAPTURE,path,driver=driver)
    assert current['candidate_key']=='id:exact'
    assert current['recorded_replay_binding']['candidate_id']=='exact'
    assert current['status']=='download_claimed'
    resolved=resolve_candidate(current,[candidate,fresh])
    assert resolved['id']=='exact' and resolved['recorded_ticket_candidate_id']=='fresh-ticket'
    service.sniffer.complete_tasks_for_reconciliation=lambda:[dict(status='done',meta=dict(req=dict(url=MEDIA+'?sign=private')))]
    before=store.events()
    with pytest.raises(EnrichmentError,match='provider effect'):
        refresh_recorded_ticket(root,IDENTITY,CAPTURE,path,driver=driver)
    assert store.events()==before


def _recorded_sub(recorded,monkeypatch,now):
    from datetime import datetime
    import xiaocao.kol.recorded_flow as flow
    from xiaocao.kol.xiaocao_wechat import XiaocaoWechatLiveSubscription
    root,item,driver,service,_,proof,_=recorded
    sub=XiaocaoWechatLiveSubscription(root,history_reader=lambda:{},capture_driver=driver,
        browser_exchange=lambda request:dict(action=request['action'],subscription_id=IDENTITY,
            candidate_id='exact',player_duration_seconds=2310.761,player_left=True),
        clock=lambda:datetime.fromisoformat(now))
    monkeypatch.setattr(flow,'enable_capture_listener_pac',lambda:None)
    driver.prepare_human_playback=lambda *a:None
    monkeypatch.setattr(flow,'inspect_original',lambda *a,**k:dict(recording=proof['recording']))
    return flow,sub,item


def test_catalog_first_flow_never_enters_before_readiness_or_uses_legacy_notice(recorded,monkeypatch):
    flow,sub,item=_recorded_sub(recorded,monkeypatch,'2026-11-04T10:50:00+08:00')
    item.update(human_playback_started_at='2026-11-04T09:05:00+08:00')
    sub.browser_exchange=lambda _:pytest.fail('early Browser entry')
    result=flow.check_recorded_playback(sub,sub._load(),item,reason='initial')
    assert result['recorded_catalog_state']=='replay_check_not_due'
    waiting=sub._waiting(result,dict(status='awaiting_playback'))['waiting_items'][0]
    assert waiting['stage']=='recorded_catalog' and waiting['next_poll_not_before']=='2026-11-04T11:00:00+08:00'


def test_catalog_first_not_published_wait_does_not_open_reused_room(recorded,monkeypatch):
    flow,sub,item=_recorded_sub(recorded,monkeypatch,'2026-11-04T15:09:59+08:00')
    monkeypatch.setattr(flow,'inspect_original',lambda *a,**k:dict(recording=None))
    sub.browser_exchange=lambda _:pytest.fail('must not fall back to live room')
    result=flow.check_recorded_playback(sub,sub._load(),item,reason='initial')
    assert result['recorded_catalog_state']=='recording_not_published'
    assert result['recorded_next_poll_at']=='2026-11-04T15:14:59+08:00'


def test_catalog_first_flow_binds_same_capture_using_normal_recorded_browser(recorded,monkeypatch):
    flow,sub,item=_recorded_sub(recorded,monkeypatch,'2026-11-04T15:09:59+08:00')
    result=flow.check_recorded_playback(sub,sub._load(),item,reason='initial')
    assert result['status']=='playback_activated' and result['capture_job_id']==CAPTURE
    assert result['playback_surface']=='authorized_recorded_course_web'
    assert result.get('human_confirmed_source_identity') is None


def test_recorded_mode_requires_explicit_descriptor_and_rejects_typos(tmp_path):
    from xiaocao.kol.recorded_flow import recorded_mode
    p=tmp_path/'config.json';p.write_text('{}');assert recorded_mode(p) is False
    p.write_text(json.dumps(dict(replay_catalog=dict(acquisition_mode='recorded_course'))));assert recorded_mode(p) is True
    p.write_text(json.dumps(dict(replay_catalog=dict(acquisition_mode='typo'))))
    with pytest.raises(EnrichmentError):recorded_mode(p)


@pytest.mark.parametrize('value',[[],dict(replay_catalog=[]),'invalid-json'])
def test_recorded_mode_configuration_errors_use_existing_safe_diagnostic(tmp_path,value):
    from xiaocao.kol.recorded_flow import recorded_mode
    from xiaocao.kol.enrichment_types import EnrichmentDiagnosticError
    p=tmp_path/'config.json';p.write_text(value if isinstance(value,str) else json.dumps(value))
    with pytest.raises(EnrichmentDiagnosticError) as exc:recorded_mode(p)
    assert exc.value.diagnostic_code=='native_entry_configuration_unreadable'


@pytest.mark.parametrize('has_runtime_labels',[False,True])
def test_recorded_prestart_repair_matches_sealed_same_task_media_only(recorded,has_runtime_labels):
    from xiaocao.kol.media_revision import _unstarted_finite_task
    root,_,driver,service,_,proof,folder=recorded
    path=folder/'proof.json';path.write_text(json.dumps(proof))
    bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    current=service.capture_store.latest(CAPTURE)
    opts=dict(path=str(folder),name='video-compressed.mp4')
    labels=dict(capture_id='exact',recorded_resource_id=RESOURCE,recorded_media_file_id=proof['media_file_id'],hls_finite='true')
    if not has_runtime_labels:labels.pop('hls_finite')
    task=dict(progress=dict(downloaded=0),meta=dict(opts=opts,req=dict(url=MEDIA+'?sign=private',labels=labels)))
    current['download_task']=copy.deepcopy(task)
    assert _unstarted_finite_task(task,folder/opts['name'],current) is True
    task['meta']['req']['labels']['recorded_media_file_id']='other'
    assert _unstarted_finite_task(task,folder/opts['name'],current) is False


@pytest.mark.parametrize('changed',[False,True])
def test_recorded_without_transport_room_resumes_original_paused_task(recorded,changed):
    from xiaocao.kol.xiaocao_live import XiaocaoLiveService
    root,_,driver,service,candidate,proof,folder=recorded
    candidate['live_id']=''
    path=folder/'proof.json';path.write_text(json.dumps(proof))
    bind_recorded_recovery(root,IDENTITY,CAPTURE,path,driver=driver)
    labels=dict(capture_id='exact',live_id='',type='live_capture',compress='true',compress_inline='true',
        recorded_resource_id=RESOURCE,recorded_media_file_id=proof['media_file_id'])
    if changed:labels['recorded_media_file_id']='wrong'
    task=dict(id='same-task',status='pause',protocol='stream',meta=dict(labels=labels))
    calls=[]
    sniffer=SimpleNamespace(tasks=lambda:[task],resume_task=lambda tid:(calls.append(tid) or dict(id=tid)))
    actual=XiaocaoLiveService(folder,capture_ledger=service.capture_store.path,sniffer_client=sniffer)
    actual.capture_store.transition(actual.capture_store.latest(CAPTURE),'download_started',status='downloading',download_task_id='same-task')
    if changed:
        with pytest.raises(EnrichmentError):actual.resume_interrupted_capture(CAPTURE)
        assert calls==[]
    else:
        assert actual.resume_interrupted_capture(CAPTURE)['download_task_id']=='same-task'
        assert calls==['same-task']


def test_future_fixed_navigation_notice_is_not_a_same_day_recording():
    from xiaocao.kol.xiaocao_wechat import parse_xiaocao_live_messages
    base='[2026-11-03 22:06] 小草: '
    mini='#小程序://见势擒龙团/Token123'
    header='存好别丢，短期以后听课固定这一个链接。明天早盘，到点点开。'
    payload=dict(chat='registered',username='exact',messages=[base+header+mini+'\n文字复盘总结：今天行情'])
    rows=parse_xiaocao_live_messages(payload)
    assert rows[0]['recorded_inventory_reason']=='future_fixed_entry_notice'
    payload['messages']=[base+mini+'\n文字复盘总结：'+header]
    assert 'recorded_inventory_reason' not in parse_xiaocao_live_messages(payload)[0]


def test_url_beside_mini_program_is_not_silently_treated_as_navigation():
    from xiaocao.kol.xiaocao_wechat import parse_xiaocao_live_messages
    rows=parse_xiaocao_live_messages(dict(chat='registered',username='exact',messages=[
        '[2026-11-04 09:04] 小草: #小程序://见势擒龙团/Token123 历史回放 https://yv9lc.xetslk.com/s/4uRHyc']))
    mini=next(r for r in rows if r.get('entry_kind')=='wechat_mini_program')
    alternate=next(r for r in rows if r.get('source_url'))
    assert 'recorded_inventory_reason' not in alternate
    assert 'alternate_entry_of' not in alternate
    assert alternate['message_sha256']==mini['message_sha256']


def test_inventory_execution_filter_is_mode_scoped_and_preserves_bound_work():
    from xiaocao.kol.xiaocao_wechat import XiaocaoWechatLiveSubscription
    item=dict(identity=IDENTITY,status='capture_armed',published_at='2026-11-03T22:06:00+08:00',
        recorded_inventory_reason='future_fixed_entry_notice',recorded_inventory_eligible=True)
    manifest=dict(items={IDENTITY:item})
    assert XiaocaoWechatLiveSubscription._next_pending(manifest,recorded=True) is None
    assert XiaocaoWechatLiveSubscription._next_pending(manifest,recorded=False)['identity']==IDENTITY
    item['recorded_inventory_eligible']=False
    assert XiaocaoWechatLiveSubscription._next_pending(manifest,recorded=True)['identity']==IDENTITY


@pytest.mark.parametrize('prefix',['','②','2. ','2、'])
@pytest.mark.parametrize('change',[None,'different_url','no_role','wrong_token','query','fragment','slash'])
def test_catalogue_navigation_needs_exact_descriptor_role_and_same_original(tmp_path,change,prefix):
    from xiaocao.kol.xiaocao_wechat import parse_xiaocao_live_messages
    from xiaocao.kol.recorded_flow import annotate_inventory
    cfg=tmp_path/'bridge.json';cfg.write_text(json.dumps(dict(replay_catalog=dict(app_id=APP,course_id=COURSE,
        mini_program_token='Token123',acquisition_mode='recorded_course',navigation_source_url='https://yv9lc.xetslk.com/s/4uRHyc'))))
    token='Other123' if change=='wrong_token' else 'Token123'
    url='https://yv9lc.xetslk.com/s/other' if change=='different_url' else 'https://yv9lc.xetslk.com/s/4uRHyc'
    url+={'query':'?course=other','fragment':'#other','slash':'/'}.get(change,'')
    role='独立另一课程：' if change=='no_role' else '历史直播回放点击链接学习：'
    rows=parse_xiaocao_live_messages(dict(chat='registered',username='exact',messages=[
        f'[2026-11-04 09:04] 小草: #小程序://见势擒龙团/{token}\n{prefix}{role}{url}']))
    rows=annotate_inventory(rows,cfg);share=next(r for r in rows if r.get('source_url'))
    assert ('recorded_inventory_reason' in share)==(change is None)


def test_numbered_catalogue_notice_discovery_and_exact_resume_have_no_capture_effect(tmp_path):
    from xiaocao.kol.xiaocao_wechat import (
        DEFAULT_CONTACT, XiaocaoWechatLiveSubscription, parse_xiaocao_live_messages,
    )
    root=tmp_path/'subscription';root.mkdir()
    config=tmp_path/'native_share_bridge.json'
    config.write_text(json.dumps(dict(replay_catalog=dict(app_id=APP,course_id=COURSE,
        mini_program_token='Token123',acquisition_mode='recorded_course',
        navigation_source_url='https://yv9lc.xetslk.com/s/4uRHyc'))))
    history=dict(chat=DEFAULT_CONTACT,username='exact',messages=[
        '[2026-11-04 22:37] ①盘前早盘+晚盘：#小程序://见势擒龙团/Token123\n\n'
        '②历史直播回放点击链接学习：https://yv9lc.xetslk.com/s/4uRHyc\n'
        '链接存好别丢，以后听课固定这一个链接，明天早盘，到点点开。'])
    originals=parse_xiaocao_live_messages(history)
    items={r['identity']:{**r,'status':'discovered'} for r in originals}
    share=next(r for r in originals if r.get('source_url'))
    # Reproduce the already-discovered item from the old parser.
    items[share['identity']].pop('recorded_navigation_marker')
    (root/'manifest.json').write_text(json.dumps(dict(schema_version=1,
        initialized_at='2026-11-04T06:00:00+08:00',items=items)))
    driver=SimpleNamespace()
    sub=XiaocaoWechatLiveSubscription(root,history_reader=lambda:history,
        browser_exchange=lambda _:pytest.fail('navigation must not request Browser'),
        capture_driver=driver,clock=lambda:__import__('datetime').datetime.fromisoformat(
            '2026-11-05T07:00:00+08:00'))
    result=sub.run_once(opencli_session='test',only_identity=share['identity'])
    assert result['inventory_only'] is True and result['already_completed'] is False
    sub.discover()
    saved=sub._load()
    assert sub._next_pending(saved,recorded=True) is None
    assert saved['items'][share['identity']]['status']=='discovered'
    assert saved['items'][share['identity']]['recorded_inventory_eligible'] is True
    assert all(not item.get('capture_job_id') for item in saved['items'].values())


def test_catalogue_role_in_unrelated_copy_is_not_navigation(tmp_path):
    from xiaocao.kol.xiaocao_wechat import parse_xiaocao_live_messages
    for prefix in ('备注：', '③另外一门课 ', 'x'):
        rows=parse_xiaocao_live_messages(dict(chat='registered',username='exact',messages=[
            '[2026-11-04 22:37] #小程序://见势擒龙团/Token123\n'
            f'{prefix}历史直播回放点击链接学习：https://yv9lc.xetslk.com/s/4uRHyc']))
        assert not any(row.get('recorded_navigation_marker') for row in rows)


def test_catalogue_navigation_does_not_hide_an_altered_url_with_same_canonical_identity(tmp_path):
    from xiaocao.kol.xiaocao_wechat import parse_xiaocao_live_messages
    from xiaocao.kol.recorded_flow import annotate_inventory
    cfg=tmp_path/'bridge.json'
    cfg.write_text(json.dumps(dict(replay_catalog=dict(app_id=APP,course_id=COURSE,
        mini_program_token='Token123',acquisition_mode='recorded_course',
        navigation_source_url='https://yv9lc.xetslk.com/s/4uRHyc'))))
    rows=parse_xiaocao_live_messages(dict(chat='registered',username='exact',messages=[
        '[2026-11-04 22:37] #小程序://见势擒龙团/Token123\n'
        '②历史直播回放点击链接学习：https://yv9lc.xetslk.com/s/4uRHyc\n'
        '③另外一门课程：https://yv9lc.xetslk.com/s/4uRHyc?course=other']))
    share=next(row for row in annotate_inventory(rows,cfg) if row.get('source_url'))
    assert not share.get('recorded_navigation_marker')
    assert not share.get('recorded_inventory_reason')
