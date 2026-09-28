import json
from xiaocao.live.morning_notifications import MorningNotifications, message


def test_all_milestones_deliver_once_and_retain_proof(tmp_path):
    sent = []
    def sender(title, body, recipient):
        sent.append((title, body, recipient))
        return {"status": "ok", "retry_safety": "not_needed"}
    notices = MorningNotifications("2026-09-28", root=tmp_path, sender=sender,
                                   recipients=lambda: ("configured-user",))
    for _ in range(2):
        notices.publish("preflight-start")
        notices.publish("ready")
        notices.publish("result", {"run_id": "original", "status": "completed", "orders": [
            {"plan_id": "owned-plan", "state": "filled", "filled_shares": 100, "broker_order_id": "123"}]})
    results = notices.close()
    assert len(sent) == 3
    assert all(r["status"] == "delivered" and r["delivered_at"] for r in results)
    assert "成交股数 100" in sent[2][1]


def test_preflight_problem_keeps_golden_window_and_ready_notices_live(tmp_path):
    sent = []
    notices = MorningNotifications("2026-09-28", root=tmp_path,
        sender=lambda title, body, recipient: sent.append(body) or {"status": "ok"},
        recipients=lambda: ("user",))
    notices.publish("preflight-problem", {"reason": "DEPENDENCY_DOWN", "request_path": "/original/request"})
    assert not notices.terminal.is_set()
    notices.publish("ready")
    notices.publish("result", {"status": "completed"})
    assert len(notices.close()) == 3
    assert "原 runner 保持等待" in sent[0]


def test_delivery_proof_is_emitted_before_runner_close(tmp_path):
    from threading import Event
    observed, results = Event(), []
    def callback(result):
        results.append(result)
        observed.set()
    notices = MorningNotifications("2026-09-28", root=tmp_path,
        sender=lambda *args: {"status": "ok"}, recipients=lambda: ("user",), on_delivery=callback)
    notices.publish("preflight-start")
    assert observed.wait(2)
    assert results[0]["status"] == "delivered" and results[0]["delivered_at"]
    assert not notices.terminal.is_set()
    notices.close()


def test_retry_never_resends_delivered_or_uncertain_recipient(tmp_path):
    sent = []
    def sender(title, body, recipient):
        sent.append(recipient)
        if recipient == "safe" and sent.count(recipient) == 1:
            return {"status": "failed", "retry_safety": "safe", "failure_phase": "connect"}
        if recipient == "uncertain":
            return {"status": "uncertain", "retry_safety": "uncertain"}
        return {"status": "ok"}
    def build():
        return MorningNotifications("2026-09-28", root=tmp_path, sender=sender,
                                    recipients=lambda: ("delivered", "safe", "uncertain"))
    first = build()
    first.publish("result", {"status": "blocked", "failed_stage": "preflight", "reason": "UNLOCK_UNPROVEN"})
    assert first.close()[0]["status"] == "pending"
    later = build()
    later.retry_pending()
    assert later.close()[0]["status"] == "pending"
    assert sent.count("delivered") == sent.count("uncertain") == 1
    assert sent.count("safe") == 2
    title, body = message("result", "2026-09-28", {"status": "blocked", "failed_stage": "preflight", "reason": "UNLOCK_UNPROVEN"})
    assert "问题" in title and "UNLOCK_UNPROVEN" in body and "未进入" in body


def test_delivery_exception_remains_uncertain_after_restart(tmp_path):
    calls = []
    def sender(*args):
        calls.append(args)
        raise TimeoutError()
    first = MorningNotifications("2026-09-28", root=tmp_path, sender=sender, recipients=lambda: ("user",))
    first.publish("ready")
    first.close()
    later = MorningNotifications("2026-09-28", root=tmp_path, sender=sender, recipients=lambda: ("user",))
    later.retry_pending()
    later.close()
    assert len(calls) == 1
    assert list(json.loads(next(tmp_path.glob("*.json")).read_text())["recipients"].values())[0]["status"] == "uncertain"


def test_queued_ack_is_reported_as_problem_not_fill():
    title, body = message("result", "2026-09-28", {"status": "unresolved", "orders": [
        {"state": "acknowledged", "filled_shares": 0, "broker_order_id": "123"}]})
    assert "问题" in title and "未决 1" in body and "成交股数 0" in body


def test_notification_storage_failure_does_not_block_runner(monkeypatch, tmp_path):
    from xiaocao.live import morning_notifications as module
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(module, "_write", fail)
    notices = MorningNotifications("2026-09-28", root=tmp_path)
    assert notices.publish("ready") is None
    assert notices.close()[0]["status"] == "pending"


def test_golden_window_reports_unproved_outcome_without_stopping_recovery(tmp_path):
    from datetime import datetime
    timers, sent = [], []
    class Timer:
        def __init__(self, delay, callback):
            self.delay, self.callback = delay, callback
            timers.append(self)
        def start(self):
            pass
        def cancel(self):
            pass
        def join(self):
            pass
    def sender(t, b, r):
        sent.append((t, b))
        return {"status": "ok"}
    notices = MorningNotifications("2026-09-28", root=tmp_path, sender=sender, recipients=lambda: ("user",))
    notices.arm_golden_window(now=datetime.fromisoformat("2026-09-28T09:00:00+08:00"), timer_factory=Timer)
    assert timers[0].delay == 1800
    timers[0].callback()
    notices.publish("result", {"status": "completed", "run_id": "original"})
    assert len(notices.close()) == 2
    assert "暂未证明" in sent[0][1] and "委托 0" not in sent[0][1]
    assert "结果" in sent[1][0]
