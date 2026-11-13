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
        path.write_text(json.dumps({'themes':[], 'reason':'explicitly reviewed no supported theme'}))
    await_judgment(tmp_path,'2026-11-16',wait_seconds=120,emit=events.append,now=lambda:clock[0],sleep=deliver)
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
