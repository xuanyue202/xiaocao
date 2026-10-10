"""Exercise recovery through the public daily shell, without market/APP effects."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("step,program,event,channel", [
    ("morning-prerecommend", "scripts/live_recommend.py", "market_dependency_recovery_wait", "stderr"),
    ("morning-execute", "scripts/wait_for_morning_freeze.py", "morning_bundle_repair_required", "stdout"),
])
def test_public_shell_delivers_recovery_before_original_child_finishes(tmp_path, step, program, event, channel):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "auto_daily.sh"
    script.write_bytes((REPO / "scripts/auto_daily.sh").read_bytes())
    binary = tmp_path / ".venv/bin/python"
    binary.parent.mkdir(parents=True)
    marker = tmp_path / "repair-done"
    binary.write_text(f'''#!{sys.executable}
import json, os, sys, time
if sys.argv[1:3] == ['-m', 'xiaocao.live.runtime_evidence']:
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
if sys.argv[1:3] == ['-m', 'xiaocao']:
    print('2026-09-30'); sys.exit(0)
if sys.argv[1] == {program!r}:
    print(json.dumps({{'event': {event!r}, 'request_path': '/exact/request.json',
         'failure_category': 'MARKET_LOGIN_CAPTCHA_REQUIRED', 'password': 'must-not-leak',
         'candidates': ['private-candidate']}}), file=sys.{channel}, flush=True)
    deadline = time.monotonic()+6
    while not os.path.exists({str(marker)!r}) and time.monotonic()<deadline: time.sleep(.02)
    sys.exit(0 if os.path.exists({str(marker)!r}) else 7)
''')
    binary.chmod(0o755)
    identity = "xiaocao-daily-morning" if step == "morning-prerecommend" else "xiaocao-daily-morning-execution"
    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "XIAOCAO_ROOT": str(tmp_path),
           "CODEX_AUTOMATION_ID": identity, "CODEX_THREAD_ID": "fixture",
           "XIAOCAO_BOOK_T_V2_RUN_MODE": "rehearsal", "XIAOCAO_BOOK_T_V2_REHEARSAL_DATE": "2026-09-30"}
    process = subprocess.Popen(["bash", str(script), step], cwd=tmp_path, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = queue.Queue()
    def read(stream):
        for line in stream:
            lines.put(line)
    readers = [threading.Thread(target=read, args=(stream,)) for stream in (process.stdout, process.stderr)]
    for reader in readers:
        reader.start()
    seen = []
    try:
        while True:
            line = lines.get(timeout=3)
            seen.append(line)
            if line.startswith('{') and json.loads(line).get("event") == event:
                assert process.poll() is None
                assert not marker.exists()
                assert "must-not-leak" not in line and "private-candidate" not in line
                assert json.loads(line)["request_path"] == "/exact/request.json"
                break
    finally:
        marker.touch()
        process.wait(timeout=10)
        for reader in readers:
            reader.join(timeout=2)
    assert process.returncode == 0


@pytest.mark.app_simulation
def test_client_login_is_agent_recovery_but_uncertain_password_remains_fenced():
    from xiaocao.live.morning_observability import dependency_user_action
    action = dependency_user_action("NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:client_login_required")
    assert action["required"] is False
    assert action["recovery_kind"] == "app_client_login"
    assert dependency_user_action("NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:client_login_required",
                                  {"state": "unproven_no_retry"})["required"] is True


@pytest.mark.app_simulation
def test_keychain_timeout_with_typed_no_action_evidence_retries(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "scripts"))
    from scripts.book_b_live_morning import _automatic_dependency_retry
    failure = {"code": "NATIVE_AX_KEYCHAIN_READ_TIMEOUT", "evidence": {
        "state": "not_attempted", "helper_status": "not_invoked",
        "password_action_attempted": False, "confirmation_pressed": False,
        "failure_category": "keychain_pre_action", "user_action": {"required": False}}}
    assert _automatic_dependency_retry(failure)
    failure["evidence"]["password_action_attempted"] = True
    assert not _automatic_dependency_retry(failure)


@pytest.mark.app_simulation
@pytest.mark.parametrize("surface", ["client_login_required", "app_absent"])
@pytest.mark.parametrize("state", ["attempt_claimed", "unproven_no_retry", "unknown", "corrupt", "wrong_account", "absent"])
def test_cold_adapter_reads_previous_process_health_before_login_route(tmp_path, surface, state):
    health = tmp_path / "health.json"
    if state != "absent":
        health.write_text("[]" if state == "corrupt" else json.dumps({
            "trade_account_fingerprint": "999******999" if state == "wrong_account" else "123******890",
            "state": state}))
    code = '''
import json, sys
from pathlib import Path
from types import SimpleNamespace
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter
from xiaocao.live.foundersc_native_ax import FounderscNativeAXError
from xiaocao.live.morning_observability import dependency_user_action
from xiaocao.live import foundersc_session
foundersc_session.session_path = lambda: Path(sys.argv[1]).parent / "app.lock"
class Native:
    def probe(self, **kwargs):
        return SimpleNamespace(as_dict=lambda: {"surface_state": sys.argv[2]})
    def unlock_from_keychain(self, **kwargs):
        raise AssertionError("cold probe must not attempt a credential")
adapter = FounderscNativeAXBrokerAdapter(native=Native(),
    expected_fund_account_fingerprint="123******890", credential_health_path=Path(sys.argv[1]))
try:
    adapter.ensure_native_ready(unlock_once=True)
except FounderscNativeAXError as exc:
    print(json.dumps(dependency_user_action(str(exc), adapter.credential_health)))
'''
    result = subprocess.run([sys.executable, "-c", code, str(health), surface],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        capture_output=True, text=True, check=True, timeout=10)
    action = json.loads(result.stdout)
    assert action["required"] is (state != "absent")
    assert (action.get("recovery_kind") == "app_client_login") is (state == "absent")


@pytest.mark.parametrize("source_changed", [False, True])
def test_terminal_producer_releases_failed_book_b_without_fabricating_freeze(tmp_path, monkeypatch, source_changed):
    from scripts.wait_for_morning_freeze import wait_for_morning_freeze
    live = tmp_path / "output/live"
    run = live / "auto/runs/producer"
    run.mkdir(parents=True)
    manifest = {"run_id": "producer", "automation": "morning-prerecommend",
        "automation_id": "xiaocao-daily-morning", "thread_id": "producer-owner",
        "market_date": "2026-09-30", "started_at": "2026-09-30T01:18:00+00:00"}
    (run / "manifest.json").write_text(json.dumps(manifest))
    terminal = {"run_id": "producer", "automation": "morning-prerecommend",
        "market_date": "2026-09-30", "deterministic_status": "failed", "process_exit_code": 1,
        "evidence": {"manifest_path": str((run / "manifest.json").resolve())}}
    if source_changed:
        terminal.update(process_exit_code=0, exit_code=78, terminal_reason="source_changed",
                        source_integrity={"status": "changed", "changed_sources": ["scripts/live_recommend.py"]})
    (run / "terminal.json").write_text(json.dumps(terminal))
    monkeypatch.setattr("scripts.wait_for_morning_freeze.time.sleep",
                        lambda _: pytest.fail("terminal producer must not wait indefinitely"))
    result = wait_for_morning_freeze(date="2026-09-30", live_dir=live,
        timeout_sec=-1, poll_sec=2, snapshot_path=live / "book_b_live_freeze_2026-09-30.jsonl")
    assert result["status"] == "producer_failed"
    assert result["producer_receipt"] == str((run / "terminal.json").resolve())
    assert not (live / "book_b_live_freeze_2026-09-30.jsonl").exists()


def test_newer_running_producer_and_unbound_terminal_do_not_end_wait(tmp_path):
    from scripts.wait_for_morning_freeze import _producer_terminal_failure
    live = tmp_path / "output/live"
    runs = live / "auto/runs"
    for name, started in (("old", "01:18"), ("new", "01:23")):
        run = runs / name
        run.mkdir(parents=True)
        (run / "manifest.json").write_text(json.dumps({"run_id": name,
            "automation": "morning-prerecommend", "automation_id": "xiaocao-daily-morning",
            "thread_id": name, "market_date": "2026-09-30", "started_at": f"2026-09-30T{started}:00+00:00"}))
    (runs / "old/terminal.json").write_text(json.dumps({"run_id": "old",
        "automation": "morning-prerecommend", "market_date": "2026-09-30",
        "deterministic_status": "failed", "process_exit_code": 1,
        "evidence": {"manifest_path": str((runs / "old/manifest.json").resolve())}}))
    assert _producer_terminal_failure(live, "2026-09-30") is None
    (runs / "new/terminal.json").write_text((runs / "old/terminal.json").read_text())
    assert _producer_terminal_failure(live, "2026-09-30") is None


@pytest.mark.parametrize("payload", [[], None, {"source_integrity": []}])
def test_malformed_producer_evidence_cannot_end_missing_bundle_wait(tmp_path, payload):
    from scripts.wait_for_morning_freeze import _producer_terminal_failure
    live = tmp_path / "output/live"
    run = live / "auto/runs/producer"
    run.mkdir(parents=True)
    path = run / "manifest.json"
    path.write_text(json.dumps(payload))
    assert _producer_terminal_failure(live, "2026-09-30") is None
    path.write_text(json.dumps({"run_id": "producer", "automation": "morning-prerecommend",
        "automation_id": "xiaocao-daily-morning", "thread_id": "owner", "market_date": "2026-09-30",
        "started_at": "2026-09-30T01:18:00+00:00"}))
    (run / "terminal.json").write_text(json.dumps(payload))
    assert _producer_terminal_failure(live, "2026-09-30") is None


def test_non_recovery_and_malformed_stream_events_are_ignored():
    from xiaocao.live.runtime_evidence import recovery_event_line
    for row in ([], None, {"event": []}, {"event": "other"}):
        assert recovery_event_line(json.dumps(row)) is None


def test_public_shell_runs_book_t_once_after_terminal_producer_failure(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "auto_daily.sh"
    script.write_bytes((REPO / "scripts/auto_daily.sh").read_bytes())
    binary = tmp_path / ".venv/bin/python"
    binary.parent.mkdir(parents=True)
    calls = tmp_path / "paper-calls.jsonl"
    binary.write_text(f'''#!{sys.executable}
import json, os, sys
if sys.argv[1:3] == ['-m', 'xiaocao.live.runtime_evidence']:
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
if sys.argv[1:3] == ['-m', 'xiaocao']:
    print('2026-09-30'); sys.exit(0)
if sys.argv[1] == 'scripts/wait_for_morning_freeze.py':
    os.execv(sys.executable, [sys.executable, {str(REPO / 'scripts/wait_for_morning_freeze.py')!r}, *sys.argv[2:]])
if sys.argv[1] == 'kronos_screen/scripts/paper_record.py':
    with open({str(calls)!r}, 'a') as f: f.write(json.dumps(sys.argv[2:])+'\\n')
''')
    binary.chmod(0o755)
    run = tmp_path / "output/live/auto/runs/producer"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"run_id": "producer",
        "automation": "morning-prerecommend", "automation_id": "xiaocao-daily-morning",
        "thread_id": "producer-owner", "market_date": "2026-09-30", "started_at": "2026-09-30T01:18:00+00:00"}))
    (run / "terminal.json").write_text(json.dumps({"run_id": "producer",
        "automation": "morning-prerecommend", "market_date": "2026-09-30",
        "deterministic_status": "failed", "process_exit_code": 1,
        "evidence": {"manifest_path": str((run / "manifest.json").resolve())}}))
    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "XIAOCAO_ROOT": str(tmp_path),
           "CODEX_AUTOMATION_ID": "xiaocao-daily-morning-execution", "CODEX_THREAD_ID": "fixture",
           "XIAOCAO_BOOK_T_V2_RUN_MODE": "rehearsal", "XIAOCAO_BOOK_T_V2_REHEARSAL_DATE": "2026-09-30"}
    result = subprocess.run(["bash", str(script), "morning-execute"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "ORIGINAL_PRODUCER_TERMINAL_WITHOUT_BUNDLE" in result.stdout
    assert len(calls.read_text().splitlines()) == 1
    assert "--trend-only" in json.loads(calls.read_text())
    assert not (tmp_path / "output/live/book_b_live_freeze_2026-09-30.jsonl").exists()
