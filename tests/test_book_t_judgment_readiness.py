"""Missing research semantics never silently seal a zero-theme evidence day."""
import json
from datetime import datetime, timedelta, timezone
import pytest

from xiaocao.research.book_t_judgment_readiness import await_judgment, JudgmentInputRequired


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv('CODEX_AUTOMATION_ID','xiaocao-daily-morning-execution')
    monkeypatch.setenv('CODEX_THREAD_ID','original-paper')
    monkeypatch.setenv('XIAOCAO_DAILY_RUN_ID','original-run')


def test_missing_draft_blocks_before_api_and_input_sealing(tmp_path, monkeypatch):
    from xiaocao.research import book_t_v2_producer as producer
    monkeypatch.setattr(producer,'build_book_t_v2_shadow_day',lambda *a,**k:pytest.fail('No input may be frozen'))
    events=[]
    with pytest.raises(JudgmentInputRequired,match='DATED_JUDGMENT_MISSING'):
        producer.prepare_book_t_v2_shadow_day(tmp_path,'2026-11-16',emit=events.append)
    assert events[0]['event']=='book_t_v2_judgment_required'
    assert not (tmp_path/'output/live/book_t_v2_shadow_input_2026-11-16.json').exists()


def test_original_wait_consumes_dated_input_without_restarting(owner,tmp_path):
    clock=[datetime(2026,11,16,1,33,tzinfo=timezone.utc)]
    events=[]
    def deliver(seconds):
        clock[0]+=timedelta(seconds=seconds)
        path=tmp_path/'output/live/book_t_v2_judgment_draft_2026-11-16.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        request=json.loads(__import__('pathlib').Path(events[0]['request_path']).read_text())
        value={'themes':[], 'status':'no_supported_theme', 'reason':'reviewed no supported theme'}
        from xiaocao.kol.publication import canonical_sha256
        value['readiness_review']={'status':'reviewed','reviewer_id':'original-paper',
            'trade_date':'2026-11-16','reviewed_at':clock[0].isoformat(),
            'request_sha256':request['request_sha256'],'draft_sha256':canonical_sha256(value),
            'reason':'current published source support was checked'}
        path.write_text(json.dumps(value))
    accepted=await_judgment(tmp_path,'2026-11-16',wait_seconds=120,emit=events.append,now=lambda:clock[0],sleep=deliver)
    assert accepted['draft']['status']=='no_supported_theme'
    assert __import__('pathlib').Path(accepted['receipt_path']).is_file()
    assert len(events)==1
    request=json.loads(__import__('pathlib').Path(events[0]['request_path']).read_text())
    assert request['binding']['CODEX_THREAD_ID']=='original-paper'
    assert request['authority']=='research_only'


def test_expired_original_request_cannot_accept_late_input_or_refund_budget(owner,tmp_path):
    clock=[datetime(2026,11,16,1,33,tzinfo=timezone.utc)]
    def advance(seconds):clock[0]+=timedelta(seconds=seconds)
    with pytest.raises(JudgmentInputRequired):
        await_judgment(tmp_path,'2026-11-16',wait_seconds=1,now=lambda:clock[0],sleep=advance)
    path=tmp_path/'output/live/book_t_v2_judgment_draft_2026-11-16.json'
    path.write_text('{"themes":[]}')
    with pytest.raises(JudgmentInputRequired):
        await_judgment(tmp_path,'2026-11-16',wait_seconds=120,now=lambda:clock[0],sleep=advance)
    requests=list((tmp_path/'output/live/book_t_v2_judgment_requests/2026-11-16').glob('*.json'))
    assert len(requests)==1
    assert datetime.fromisoformat(json.loads(requests[0].read_text())['deadline'])==clock[0]


def test_research_request_is_forwarded_without_semantic_payload():
    from xiaocao.live.runtime_evidence import recovery_event_line
    result=json.loads(recovery_event_line(json.dumps({'event':'book_t_v2_judgment_required',
        'request_path':'/original/request.json','report_body':'private source'})))
    assert result['request_path']=='/original/request.json'
    assert 'report_body' not in result


def test_bare_empty_placeholder_is_not_reviewed_judgment(owner,tmp_path):
    draft=tmp_path/'output/live/book_t_v2_judgment_draft_2026-11-16.json'
    draft.parent.mkdir(parents=True)
    draft.write_text('{"themes":[]}')
    events=[]
    with pytest.raises(JudgmentInputRequired):
        await_judgment(tmp_path,'2026-11-16',emit=events.append)
    assert events[0]['event']=='book_t_v2_judgment_required'
    assert not list(draft.parent.glob('book_t_v2_judgment_requests/*/*.accepted.json'))


def test_reading_time_cannot_admit_a_reply_after_original_deadline(owner,tmp_path,monkeypatch):
    from pathlib import Path
    clock=[datetime(2026,11,16,1,33,tzinfo=timezone.utc)]
    draft=tmp_path/'output/live/book_t_v2_judgment_draft_2026-11-16.json'
    events=[]
    def deliver(seconds):
        clock[0]+=timedelta(seconds=seconds)
        request=json.loads(Path(events[0]['request_path']).read_text())
        from xiaocao.kol.publication import canonical_sha256
        value={'themes':[{'theme_id':'candidate'}]}
        value['readiness_review']={'status':'reviewed','reviewer_id':'original-paper',
            'trade_date':'2026-11-16','reviewed_at':clock[0].isoformat(),
            'request_sha256':request['request_sha256'],'draft_sha256':canonical_sha256(value),'reason':'reviewed'}
        draft.write_text(json.dumps(value))
    original=Path.read_bytes
    def slow_read(path):
        raw=original(path)
        if path==draft:clock[0]+=timedelta(seconds=120)
        return raw
    monkeypatch.setattr(Path,'read_bytes',slow_read)
    with pytest.raises(JudgmentInputRequired):
        await_judgment(tmp_path,'2026-11-16',wait_seconds=120,emit=events.append,
                       now=lambda:clock[0],sleep=deliver)
    assert not list(draft.parent.glob('book_t_v2_judgment_requests/*/*.accepted.json'))


def test_source_assembly_uses_admitted_object_after_mutable_draft_changes(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from xiaocao.research import book_t_v2_producer as producer
    monkeypatch.setattr(producer,'_load_publications',lambda *a,**k:([],[]))
    monkeypatch.setattr(producer,'_load_portfolio',lambda *a,**k:{})
    monkeypatch.setattr(producer,'_load_dated_optional',lambda root,stem,day:
        pytest.fail('Admitted draft must not be reread') if stem=='book_t_v2_judgment_draft' else None)
    registry=tmp_path/'reference/experience/book_t_v2_theme_registry.json'
    registry.parent.mkdir(parents=True);registry.write_text('{}')
    client=SimpleNamespace(etf_info=lambda *a:[],get_block_category_rank_v3=lambda *a,**k:[],
        stock_info=lambda:[],get_trade_cal=lambda *a:[{'calDate':'20261116','is_open':1}])
    admitted={'themes':[], 'status':'no_supported_theme','reason':'exact admitted content'}
    result=producer._load_real_sources(tmp_path,'2026-11-16',client=client,judgment_draft=admitted)
    assert result['agent_draft']==admitted
