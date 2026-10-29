from datetime import datetime

import pytest

from xiaocao.automation_run import automation_run, current_automation_id, validate_automation_identity


def test_only_same_automation_slot_is_busy(tmp_path):
    with automation_run("remote-writer", "2026-09-28", root=tmp_path) as writer:
        assert current_automation_id() == "remote-writer"
        with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as morning:
            assert current_automation_id() == "book-b-morning"
            assert writer["status"] == morning["status"] == "acquired"
            with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as duplicate:
                assert duplicate["status"] == "busy"
                assert duplicate["owner"]["automation_id"] == "book-b-morning"
        assert current_automation_id() == "remote-writer"
    with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as next_run:
        assert next_run["status"] == "acquired"


def test_entrypoint_rejects_foreign_task_identity(monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "remote-writer")
    with pytest.raises(ValueError, match="AUTOMATION_ENTRYPOINT_ID_MISMATCH"):
        validate_automation_identity("book-b-morning", "book-b-morning")
    monkeypatch.delenv("CODEX_AUTOMATION_ID")
    with pytest.raises(ValueError, match="AUTOMATION_ENTRYPOINT_ID_MISMATCH"):
        validate_automation_identity("book-b-morning", "remote-writer")
    validate_automation_identity("book-b-morning", "book-b-morning")


def header_fixture(root, monkeypatch, *, first=None, created='2026-09-07T02:25:00Z', automation='xiaocao-intraday-monitor-05'):
    import json
    thread = 'fixture-thread'
    monkeypatch.setenv('CODEX_THREAD_ID', thread)
    monkeypatch.setenv('CODEX_AUTOMATION_ID', automation)
    monkeypatch.setenv('CODEX_HOME', str(root))
    path=root/'sessions/2026/09/07/test-fixture-thread.jsonl';path.parent.mkdir(parents=True)
    def user(text):return {'type':'response_item','payload':{'role':'user','content':[{'text':text}]}}
    rows=[{'type':'session_meta','payload':{'id':thread,'timestamp':created}},
          user(first or f'Automation: fixture\nAutomation ID: {automation}'),
          user(f'Automation: copied\nAutomation ID: {automation}')]
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    return path


def test_initial_header_and_date_are_proved_before_monitor_actions(tmp_path, monkeypatch):
    from xiaocao.automation_run import validate_scheduler_header, validate_monitor_scheduler
    header_fixture(tmp_path,monkeypatch)
    result=validate_scheduler_header('xiaocao-intraday-monitor-05',date='2026-09-07',now=datetime.fromisoformat('2026-09-07T10:25:00+08:00'))
    assert result['thread_id']=='fixture-thread' and len(result['header_sha256'])==64
    assert validate_monitor_scheduler(date='2026-09-07',phase='sparse',now=datetime.fromisoformat('2026-09-07T10:25:00+08:00'))==result
    with pytest.raises(ValueError,match='ENTRYPOINT_ID_MISMATCH'):
        validate_monitor_scheduler(date='2026-09-07',phase='opening',now=datetime.fromisoformat('2026-09-07T10:25:00+08:00'))


@pytest.mark.parametrize('fault', ['copied_header','wrong_date','wrong_id'])
def test_old_or_human_task_cannot_claim_today_by_copied_header(tmp_path,monkeypatch,fault):
    from xiaocao.automation_run import validate_scheduler_header
    options={'first':'Please inspect this automation'} if fault=='copied_header' else {}
    if fault=='wrong_date':options['created']='2026-09-06T02:25:00Z'
    if fault=='wrong_id':options['first']='Automation: foreign\nAutomation ID: foreign'
    header_fixture(tmp_path,monkeypatch,**options)
    with pytest.raises(ValueError,match='INITIAL_SCHEDULER'):
        validate_scheduler_header('xiaocao-intraday-monitor-05',date='2026-09-07',now=datetime.fromisoformat('2026-09-07T10:25:00+08:00'))


def test_injected_agents_prelude_precedes_actual_scheduler_header(tmp_path,monkeypatch):
    import json
    from xiaocao.automation_run import validate_scheduler_header
    path=header_fixture(tmp_path,monkeypatch)
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    prelude={'type':'response_item','payload':{'role':'user','content':[{'text':
        '# AGENTS.md instructions for /repo\n<INSTRUCTIONS>rules</INSTRUCTIONS>\n<environment_context>env</environment_context>'}]}}
    rows.insert(1,prelude);path.write_text('\n'.join(json.dumps(row) for row in rows))
    assert validate_scheduler_header('xiaocao-intraday-monitor-05',date='2026-09-07',now=datetime.fromisoformat('2026-09-07T10:25:00+08:00'))['thread_id']=='fixture-thread'


def test_matching_old_header_cannot_claim_a_past_day_now(tmp_path,monkeypatch):
    from xiaocao.automation_run import validate_scheduler_header
    header_fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='INITIAL_SCHEDULER_DATE_MISMATCH'):
        validate_scheduler_header('xiaocao-intraday-monitor-05',date='2026-09-07',
            now=datetime.fromisoformat('2026-09-08T10:25:00+08:00'))
