"""Generic dependency waits: signals request a check, never certify readiness."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.runner_recovery import DependencyRecovery, signal_recheck


class Clock:
    def __init__(self):
        self.elapsed = 0
        self.hook = lambda: None

    def now(self):
        return datetime(2026, 9, 28, 1, tzinfo=timezone.utc) + timedelta(seconds=self.elapsed)

    def sleep(self, seconds):
        self.elapsed += seconds
        self.hook()


def recovery(tmp_path, clock, events, *, deadline=20, boundary=10, on_failure=None):
    return DependencyRecovery(root=tmp_path, identity={"automation_id": "job", "owner_thread_id": None},
        deadline=deadline, boundary=clock.now() + timedelta(seconds=boundary),
        recoverable=lambda e: str(e).startswith("DEPENDENCY_DOWN"), on_event=events.append,
        on_failure=on_failure, clock=clock.now, monotonic=lambda: clock.elapsed, sleep=clock.sleep)


def test_boundary_wait_keeps_original_call_and_checks_only_once(tmp_path):
    clock, events, calls = Clock(), [], []
    def check():
        calls.append(clock.elapsed)
        if len(calls) == 1:
            raise RuntimeError("DEPENDENCY_DOWN")
        return "proved"
    wait = recovery(tmp_path, clock, events)
    assert wait.run(check) == "proved"
    assert calls == [0, 10]
    assert wait.snapshot()["requests"][0]["status"] == "recovered"
    assert [e["event"] for e in events] == ["dependency_recovery_wait", "dependency_recovered"]


def test_repair_signal_wakes_same_call_without_extending_budget(tmp_path):
    clock, events, calls = Clock(), [], []
    def check():
        calls.append(clock.elapsed)
        if len(calls) == 1:
            raise RuntimeError("DEPENDENCY_DOWN")
        return "proved"
    def signal():
        if clock.elapsed == 3:
            signal_recheck(Path(events[0]["request_path"]))
    clock.hook = signal
    wait = recovery(tmp_path, clock, events)
    assert wait.run(check) == "proved"
    assert calls == [0, 3] and wait.deadline == 20


def test_failure_after_signal_does_not_repeat_on_stale_signal(tmp_path):
    clock, events, calls = Clock(), [], []
    def check():
        calls.append(clock.elapsed)
        raise RuntimeError("DEPENDENCY_DOWN:private diagnostic must not be stored")
    clock.hook = lambda: signal_recheck(Path(events[0]["request_path"])) if clock.elapsed == 2 else None
    wait = recovery(tmp_path, clock, events)
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        wait.run(check)
    assert calls == [0, 2, 10]
    persisted = Path(events[0]["request_path"]).read_text()
    assert "private diagnostic" not in persisted
    assert json.loads(persisted)["status"] == "exhausted"


def test_wrong_binding_never_triggers_check(tmp_path):
    clock, events, calls = Clock(), [], []
    def check():
        calls.append(clock.elapsed)
        raise RuntimeError("DEPENDENCY_DOWN")
    def forge():
        if clock.elapsed == 2:
            p = Path(events[0]["request_path"])
            p.with_suffix(".resume.json").write_text(json.dumps({"request_sha256": "foreign", "sequence": 1}))
    clock.hook = forge
    wait = recovery(tmp_path, clock, events, deadline=5, boundary=10)
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        wait.run(check)
    assert calls == [0] and clock.elapsed == 5


def test_missing_credentials_is_terminal_without_wait_or_recheck(tmp_path):
    clock, events = Clock(), []
    def check():
        raise RuntimeError("CREDENTIALS_MISSING")
    with pytest.raises(RuntimeError, match="CREDENTIALS_MISSING"):
        recovery(tmp_path, clock, events).run(check)
    assert events == [] and clock.elapsed == 0


def test_signal_does_not_certify_ready(tmp_path):
    clock, events, calls = Clock(), [], []
    def check():
        calls.append(clock.elapsed)
        raise RuntimeError("DEPENDENCY_DOWN")
    clock.hook = lambda: signal_recheck(Path(events[0]["request_path"])) if clock.elapsed == 2 else None
    wait = recovery(tmp_path, clock, events, deadline=5, boundary=10)
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        wait.run(check)
    assert calls == [0, 2]
    assert wait.snapshot()["requests"][0]["status"] == "exhausted"


def test_signal_rejects_other_owner_and_completed_request(tmp_path, monkeypatch):
    clock, events = Clock(), []
    wait = recovery(tmp_path, clock, events, deadline=1, boundary=10)
    wait.identity["owner_thread_id"] = "actual-owner"
    def check():
        raise RuntimeError("DEPENDENCY_DOWN")
    with pytest.raises(RuntimeError):
        wait.run(check)
    path = Path(events[0]["request_path"])
    with pytest.raises(ValueError, match="NOT_WAITING"):
        signal_recheck(path)
    record = json.loads(path.read_text())
    record["status"] = "waiting"
    path.write_text(json.dumps(record))
    monkeypatch.setenv("CODEX_THREAD_ID", "other-owner")
    with pytest.raises(ValueError, match="OWNER_MISMATCH"):
        signal_recheck(path)


def test_hard_failure_after_recheck_ends_wait(tmp_path):
    clock, events, calls = Clock(), [], []
    def check():
        calls.append(clock.elapsed)
        raise RuntimeError("DEPENDENCY_DOWN" if len(calls) == 1 else "AUTHORITY_MISMATCH")
    wait = recovery(tmp_path, clock, events)
    with pytest.raises(RuntimeError, match="AUTHORITY_MISMATCH"):
        wait.run(check)
    assert calls == [0, 10]
    assert json.loads(Path(events[0]["request_path"]).read_text())["status"] == "terminal"


def test_typed_failure_context_is_persisted_and_available_to_notifier(tmp_path):
    from xiaocao.live.morning_observability import dependency_user_action
    clock, events, observed = Clock(), [], []
    wait = DependencyRecovery(root=tmp_path, identity={'automation_id': 'job'}, deadline=1,
        boundary=clock.now() + timedelta(seconds=10), recoverable=lambda _: True,
        on_event=events.append, on_failure=lambda row: observed.append(row['failures'][-1]['evidence']),
        failure_evidence=lambda exc: {'user_action': dependency_user_action(str(exc))},
        clock=clock.now, monotonic=lambda: clock.elapsed, sleep=clock.sleep)
    def check():
        raise RuntimeError('NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:screen_locked:private diagnostic')
    with pytest.raises(RuntimeError, match='BUDGET_EXHAUSTED'):
        wait.run(check)
    record = Path(events[0]['request_path']).read_text()
    assert 'private diagnostic' not in record
    assert observed[0]['user_action']['required']
    assert '解锁 macOS' in observed[0]['user_action']['request']


def test_proved_no_action_retry_uses_two_seconds_without_refunding_budget(tmp_path):
    clock, events, calls = Clock(), [], []
    wait = recovery(tmp_path, clock, events, deadline=12, boundary=30)
    wait.automatic_retry = lambda failure: failure["code"] == "DEPENDENCY_DOWN"
    def check():
        calls.append(clock.elapsed)
        if len(calls) < 3:
            clock.elapsed += 1  # slow dependency check
            raise RuntimeError("DEPENDENCY_DOWN")
        return "ready"
    assert wait.run(check) == "ready"
    assert calls == [0, 3, 6] and wait.deadline == 12
