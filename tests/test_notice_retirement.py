"""User-retired reminders preserve uncertain receipts and never send again."""
import json
from pathlib import Path

import pytest

from xiaocao.live.incident_delivery import (deliver_pending, enqueue_notice,
    pending_notices, retire_notice)
from xiaocao.live.morning_notifications import MorningNotifications


@pytest.fixture(autouse=True)
def forbid_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("notice retirement must never send")
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)


def test_retirement_suppresses_only_exact_claim_and_keeps_original_bytes(tmp_path):
    path = tmp_path / "incidents.jsonl"
    enqueue_notice(path, identifier="old", title="历史提醒", body="原始事实")
    enqueue_notice(path, identifier="new", title="新提醒", body="新的事实")
    before = path.read_bytes()
    retired = retire_notice(path, identifier="old", approval_reference="explicit-user-message",
                           reason="用户不再追历史通知")
    assert retire_notice(path, identifier="old", approval_reference="explicit-user-message",
                         reason="用户不再追历史通知") == retired
    assert path.read_bytes() == before and retired["status"] == "retired_by_user"
    assert [r["incident_id"] for r in pending_notices(path)] == ["new"]
    calls = []
    result = deliver_pending(path, readiness=lambda **_: {"status": "configured"},
                            sender=lambda *a, **k: calls.append(a) or {"wecom": "ok"})
    assert len(calls) == 1 and result[0]["incident_id"] == "new"
    assert not any(json.loads(line).get("status") == "delivered" and
                   json.loads(line)["incident_id"] == "old" for line in path.read_text().splitlines())


def test_retirement_cannot_preempt_future_claim_or_omit_user_direction(tmp_path):
    path = tmp_path / "incidents.jsonl"
    enqueue_notice(path, identifier="old", title="提醒", body="原始事实")
    with pytest.raises(ValueError, match="EXISTING_CLAIM"):
        retire_notice(path, identifier="future", approval_reference="user", reason="ignore")
    with pytest.raises(ValueError, match="USER_DIRECTION"):
        retire_notice(path, identifier="old", approval_reference="", reason="ignore")


def test_retired_morning_notice_is_skipped_by_retry_and_direct_send(tmp_path):
    path = tmp_path / "old.json"
    row = {"notification_id": "old", "automation_id": "xiaocao-book-b-live-morning",
           "kind": "result", "status": "pending", "recipients": {}}
    path.write_text(json.dumps(row)); before = path.read_bytes()
    retire_notice(path, identifier="old", approval_reference="user", reason="ignore")
    calls = []
    notices = MorningNotifications("retry", root=tmp_path,
        sender=lambda *a: calls.append(a), recipients=lambda: ("recipient",))
    assert notices.send(path)["status"] == "retired_by_user"
    notices.retry_pending()
    assert notices.close() == [] and not calls and path.read_bytes() == before
