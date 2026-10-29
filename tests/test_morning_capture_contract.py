"""Offline capture, recovery and publication contracts; no APP or network calls."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

from xiaocao.live.source_observation import observation_current, require_capture_inputs, CaptureInputsExpired


def readiness(now=None, codes=None):
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    return {"sources": [{"source": "pool", "status": "populated", "observed_at": stamp}],
        "completeness": "observed_responses", "price_enrichment": {"status": "complete",
            "observed_at": stamp, "unpriced_codes": [], "observations": [{"code": code, "observed_at": stamp} for code in (codes or ["000001.XSHE"])]}}


@pytest.mark.parametrize('offset,valid', [(0, True), (60, True), (60.01, False), (-1, False)])
def test_observation_uses_start_and_rejects_future(offset, valid):
    now = datetime.now(timezone.utc)
    assert observation_current({"observed_at": (now - timedelta(seconds=offset)).isoformat(),
        "completed_at": now.isoformat()}, now=now) is valid


def test_each_price_and_source_must_be_current_at_capture():
    now = datetime.now(timezone.utc)
    proof = readiness(now)
    require_capture_inputs(proof, now=now)
    proof['price_enrichment']['observations'][0]['observed_at'] = (now-timedelta(seconds=61)).isoformat()
    with pytest.raises(CaptureInputsExpired, match='PRICE_EXPIRED'):
        require_capture_inputs(proof, now=now)
    for value in [None, 'invalid', '2026-10-19T09:25:00']:
        assert not observation_current({'observed_at': value}, now=now)


def test_expiry_after_lock_wait_creates_no_checkpoint(tmp_path, monkeypatch):
    import xiaocao.live.morning_bundle as bundle
    monkeypatch.setenv('CODEX_AUTOMATION_ID', 'xiaocao-daily-morning')
    monkeypatch.setenv('CODEX_THREAD_ID', 'owner')
    now = datetime.now(timezone.utc)
    proof = readiness(now - timedelta(seconds=59))
    clock = [now]
    original = bundle._lock.__enter__
    def enter(lock):
        result = original(lock)
        clock[0] += timedelta(seconds=2)
        return result
    monkeypatch.setattr(bundle._lock, '__enter__', enter)
    row = {"date": "2026-10-19", "book": "B", "code": "000001.XSHE", "mode": "test", "is_live": True}
    with pytest.raises(CaptureInputsExpired):
        bundle.publish_captured_batch(tmp_path, '2026-10-19', snapshot=(json.dumps(row)+'\n').encode(),
            strategy_sha='a'*40, source_readiness=proof, timing={},
            precommit=lambda: require_capture_inputs(proof, now=clock[0]))
    assert not list(tmp_path.rglob('checkpoint.json'))
    assert not (tmp_path/'morning_bundle_commit_2026-10-19.json').exists()


def test_raw_directory_response_is_immutable_and_distinct_from_normalization(tmp_path, monkeypatch):
    from xiaocao.api.client import XiaocaoClient
    from xiaocao.datasource.api_source import ApiDataSource
    monkeypatch.chdir(tmp_path)
    client = XiaocaoClient(base_url='https://example.invalid')
    raw = [{"code": "000001.XSHE", "statusType": 1, "vendorExtension": 1}]
    monkeypatch.setattr(client, '_do_post', lambda *args: raw)
    hashes, normalized = [], []
    for extension in [1, 2]:
        raw[0]['vendorExtension'] = extension
        source = ApiDataSource(client, resolve_security_universe=True)
        source.begin_observation(1)
        source._load_security_directory('2026-10-19')
        record = source.observations[0]
        evidence = record['raw_response']
        content = Path(evidence['path']).read_bytes()
        assert hashlib.sha256(content).hexdigest() == evidence['sha256']
        assert json.loads(content)[0]['vendorExtension'] == extension
        hashes.append(evidence['sha256']); normalized.append(record['response_sha256'])
    assert hashes[0] != hashes[1] and normalized[0] == normalized[1]


def test_price_only_gap_is_forwarded_once_with_evidence(tmp_path, monkeypatch, capsys):
    import scripts.live_recommend as recommend
    from xiaocao.live.runtime_evidence import recovery_event_line
    monkeypatch.setattr(recommend, 'OUT_DIR', tmp_path)
    monkeypatch.setattr(recommend, '_today_iso', lambda: '2026-10-19')
    elapsed = [0]
    monkeypatch.setattr(recommend._time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(recommend._time, 'sleep', lambda s: elapsed.__setitem__(0, elapsed[0]+s))
    source = SimpleNamespace(readiness={})
    def strategy(*args, **kwargs):
        source.readiness = readiness()
        return [{'code': '000001.XSHE', 'mode': 'test'}]
    monkeypatch.setattr(recommend, 'run_strategy', strategy)
    recommend._run_strategy_when_ready('2026-10-19', source, timeout_sec=-1, poll_sec=2,
        confirm_sec=0, stable_samples=1, price_probe=lambda _: ['000001.XSHE'] if elapsed[0]<4 else [])
    events = [json.loads(v) for line in capsys.readouterr().err.splitlines() if (v:=recovery_event_line(line))]
    assert len(events) == 1
    event = events[0]
    assert event['source_gaps'][0]['missing_codes'] == ['000001.XSHE']
    assert event['first_observed_at'] and event['last_observed_at']
    assert Path(event['evidence_path']).exists()


def recovery(tmp_path, monkeypatch):
    from xiaocao.live.morning_source_recovery import SourceRecovery
    from xiaocao.live.runtime_evidence import source_manifest
    from xiaocao.utils.trading_session import A_SHARE_TZ
    day = datetime.now(A_SHARE_TZ).date().isoformat()
    run = tmp_path/'output/live/auto/runs/original'
    run.mkdir(parents=True)
    for name in ['scripts/auto_daily.sh', 'pyproject.toml', 'docs/OPERATING_CONTRACT.md']:
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('fixture')
    hashes = source_manifest(tmp_path)
    manifest = {'run_id': 'original', 'automation_id': 'xiaocao-daily-morning', 'thread_id': 'owner',
        'market_date': day, 'source_manifest_sha256': hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        'source_hashes': hashes, 'execution_root': str(tmp_path)}
    (run/'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setenv('CODEX_AUTOMATION_ID', 'xiaocao-daily-morning')
    monkeypatch.setenv('CODEX_THREAD_ID', 'owner')
    return SourceRecovery(run,tmp_path/'output/live',day,(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat())


def test_source_recheck_is_same_owner_same_process_and_exactly_once(tmp_path, monkeypatch):
    from xiaocao.live.morning_source_recovery import signal_recheck
    owner = recovery(tmp_path, monkeypatch)
    try:
        event = owner.waiting(readiness())
        path = Path(event['request_path'])
        assert signal_recheck(path)['status'] == 'recheck_signaled_not_ready'
        with pytest.raises(FileExistsError):
            signal_recheck(path)
        assert owner.consume() and not owner.consume()
        with pytest.raises(ValueError, match='NOT_WAITING'):
            signal_recheck(path)
    finally:
        owner.close()


@pytest.mark.parametrize('fault,reason', [('owner','OWNER_MISMATCH'), ('closed','NOT_WAITING'),
    ('terminal','ALREADY_TERMINAL'), ('committed','ALREADY_COMMITTED'), ('code','BEHAVIOR_CHANGED')])
def test_source_recheck_fences_no_revival(tmp_path, monkeypatch, fault, reason):
    from xiaocao.live.morning_source_recovery import signal_recheck
    owner = recovery(tmp_path, monkeypatch)
    try:
        path = Path(owner.waiting(readiness())['request_path'])
        if fault == 'owner': monkeypatch.setenv('CODEX_THREAD_ID','other')
        if fault == 'closed': owner._state('closed')
        if fault == 'terminal': (owner.run_dir/'terminal.json').write_text('{}')
        if fault == 'committed': (owner.live_dir/f'morning_bundle_commit_{owner.date}.json').write_text('{}')
        if fault == 'code': (tmp_path/'scripts/auto_daily.sh').write_text('changed')
        with pytest.raises(ValueError, match=reason): signal_recheck(path)
        assert not list(path.parent.glob('*.claim.json'))
    finally:
        owner.close()


def test_pipeline_does_not_promote_late_bundle_to_app_success(tmp_path, monkeypatch):
    from xiaocao.live.morning_pipeline import pipeline_status
    day = '2026-10-19'
    def put(relative,value):
        p=tmp_path/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
    from xiaocao.live.morning_bundle import publish_captured_batch
    monkeypatch.setenv('CODEX_AUTOMATION_ID','xiaocao-daily-morning')
    monkeypatch.setenv('CODEX_THREAD_ID','producer')
    publish_captured_batch(tmp_path,day,snapshot=b'',strategy_sha='a'*40,source_readiness=readiness(),timing={})
    put('book_b_live_execution/runs/checklists/one.json',{'schema_version':1,'items':{'identity_calendar':{},'kol_projection':{},'orders':{}},'binding':{'automation_id':'xiaocao-book-b-live-morning',
        'trade_date':day,'owner_thread_id':'app-owner','runner_pid':123,'preparation_deadline':day+'T09:35:00+08:00'}})
    put(f'book_b_live_execution/runs/history/{day}-one.json',{'trade_date':day,'run_id':day+'-one',
        'runner_identity':{'automation_id':'xiaocao-book-b-live-morning','owner_thread_id':'app-owner','runner_pid':123},
        'status':'blocked','reason':'DATED_FREEZE_NOT_PROVEN'})
    # Input/packet artifacts carry the same owner binding but are not owners.
    checklist = json.loads((tmp_path/'book_b_live_execution/runs/checklists/one.json').read_text())
    put('book_b_live_execution/runs/checklists/input.kol-inputs.json', {'schema_version':1,'binding':checklist['binding']})
    put('book_b_live_execution/runs/checklists/duplicate.json', checklist)
    result=pipeline_status(tmp_path,day)
    assert len(result['app']) == 1
    assert result['bundle']['status']=='ready'
    assert result['app'][0]['terminal_receipts'][0]['status']=='blocked'
    assert result['app'][0]['preparation_deadline']==day+'T09:35:00+08:00'


def test_derived_pipeline_bad_structure_and_write_failure_do_not_veto(tmp_path, monkeypatch):
    import xiaocao.live.morning_pipeline as pipeline
    path=tmp_path/'auto/runs/other/manifest.json';path.parent.mkdir(parents=True);path.write_text('[1]')
    assert pipeline.pipeline_status(tmp_path,'2026-10-19')['owners']==[]
    def fail(*args,**kwargs): raise OSError('readonly diagnostics')
    monkeypatch.setattr(pipeline,'atomic_write',fail)
    assert pipeline.save_pipeline_status(tmp_path,'2026-10-19')['status']=='degraded'


def test_raw_directory_proof_survives_full_revalidation(tmp_path, monkeypatch):
    from xiaocao.api.client import XiaocaoClient
    from xiaocao.datasource.api_source import ApiDataSource
    monkeypatch.chdir(tmp_path)
    client=XiaocaoClient(base_url='https://example.invalid')
    monkeypatch.setattr(client,'_do_post',lambda *args:[{'code':'000001.XSHE','statusType':1}])
    source=ApiDataSource(client,resolve_security_universe=True)
    source.begin_observation(1);source._load_security_directory('2026-10-19')
    before=source.observations[0]['raw_response']
    assert source.revalidate_observation(2)
    after=source.observations[0]['raw_response']
    assert after['sha256']==before['sha256']
    assert Path(after['path']).exists()
    assert Path(source.observations[0]['response_path']).exists()


def test_source_expired_budget_or_interrupted_claim_never_replays(tmp_path, monkeypatch):
    from xiaocao.live.morning_source_recovery import signal_recheck
    owner=recovery(tmp_path,monkeypatch)
    try:
        owner.binding['preparation_deadline']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        path=Path(owner.waiting(readiness())['request_path'])
        with pytest.raises(ValueError,match='DEADLINE_EXPIRED'):signal_recheck(path)
        assert not list(path.parent.glob('*.claim.json'))
        owner.binding['preparation_deadline']=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()
        path=Path(owner.waiting(readiness())['request_path'])
        path.with_suffix('.claim.json').write_text('{"status":"uncertain"}')
        with pytest.raises(FileExistsError):signal_recheck(path)
        assert not path.with_suffix('.signal.json').exists()
    finally:owner.close()


def test_missing_individual_price_proof_cannot_be_replaced_by_fresh_probe_time():
    proof=readiness()
    with pytest.raises(CaptureInputsExpired,match='PRICE_COVERAGE_UNPROVED'):
        require_capture_inputs(proof,required_codes={'000001.XSHE','000002.XSHE'})


def test_pipeline_rejects_wrong_day_and_missing_app_identity_without_writes(tmp_path):
    from xiaocao.live.morning_pipeline import pipeline_status
    day='2026-10-19'
    (tmp_path/f'morning_bundle_ready_{day}.json').write_text(json.dumps({'market_date':'2026-10-18','status':'ready','checkpoint_sha256':'a'*64}))
    root=tmp_path/'book_b_live_execution/runs';(root/'checklists').mkdir(parents=True);(root/'history').mkdir()
    (root/'checklists/empty.json').write_text(json.dumps({'binding':{'trade_date':day,'automation_id':'xiaocao-book-b-live-morning'}}))
    (root/f'history/{day}-empty.json').write_text(json.dumps({'trade_date':day,'status':'completed',
        'runner_identity':{'automation_id':'xiaocao-book-b-live-morning'}}))
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result=pipeline_status(tmp_path,day)
    assert result['bundle']['status']=='unproved' and result['bundle']['checkpoint_sha256'] is None
    assert result['app']==[]
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_entry_prices_batch_complete_identity_and_fallback(tmp_path, monkeypatch):
    import scripts.live_recommend as recommend
    day = recommend._today_iso()
    monkeypatch.setattr(recommend, 'OUT_DIR', tmp_path)
    calls = []
    class Client:
        def second_line_detail_info(self, codes):
            calls.append(codes)
            return {code:{'code':code,'tradeDate':day.replace('-',''),'open':10.,'preClose':9.}
                    for code in codes.split(',') if code != '000009.XSHE'}
    fallback = []
    monkeypatch.setattr(recommend, '_entry_price', lambda client,code,date:
                        fallback.append(code) or (11.,'fallback',9.))
    codes = [f'{i:06d}.XSHE' for i in range(1,20)]
    result, evidence = recommend._batch_entry_prices(Client(),codes,day)
    assert len(calls) == 3 and len(result) == 19
    assert fallback == ['000009.XSHE']
    assert result['000009.XSHE']['value'][0] == 11.
    assert all(row['value'][0] == 10. for code,row in result.items() if code != '000009.XSHE')
    assert sum(len(row['request_codes']) for row in evidence) == 19
    for row in evidence:
        assert hashlib.sha256(Path(row['raw_path']).read_bytes()).hexdigest() == row['raw_sha256']


def test_missing_price_retry_and_fallback_bypass_empty_http_cache(tmp_path,monkeypatch):
    import scripts.live_recommend as recommend
    from xiaocao.api.client import XiaocaoClient
    from xiaocao.api.cache import SQLiteCache
    from xiaocao.api.errors import ApiAuthError
    day=recommend._today_iso();code='000001.XSHE'
    monkeypatch.setattr(recommend,'OUT_DIR',tmp_path)
    client=XiaocaoClient(cache=SQLiteCache(tmp_path/'cache.sqlite3'))
    calls=[]
    def post(path,payload):
        calls.append(path)
        if len(calls)<3:return []
        return {code:{'code':code,'tradeDate':day.replace('-',''),'open':10.,'preClose':9.}}
    monkeypatch.setattr(client,'_do_post',post)
    monkeypatch.setattr(client,'second_line_detail_info',lambda codes:client.post('/stock/detail',{'codes':codes}))
    monkeypatch.setattr(recommend,'_entry_price',lambda c,code,date:
                        (c.post('/stock/fallback',{'code':code}) and 11. or None,'fallback',9.))
    first,_=recommend._batch_entry_prices(client,[code],day)
    second,_=recommend._batch_entry_prices(client,[code],day)
    assert first[code]['value'][0] is None and second[code]['value'][0]==10.
    assert calls==['/stock/detail','/stock/fallback','/stock/detail']
    def rejected(*args):raise ApiAuthError('auth failed')
    monkeypatch.setattr(client,'second_line_detail_info',rejected)
    with pytest.raises(ApiAuthError):recommend._batch_entry_prices(client,[code],day)
