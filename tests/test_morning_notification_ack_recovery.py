import pytest

from xiaocao.live.morning_notifications import MorningNotifications, result_fingerprint


pytestmark = pytest.mark.app_simulation


def working_result():
    reason = "native_exact_order_delta_and_trade_readback"
    return {"status": "unresolved", "reason": reason, "orders": [{
        "plan_id": "book-b:2026-10-14:002531.XSHE:BUY",
        "broker_order_id": "6000110", "state": "acknowledged",
        "filled_shares": 0, "remaining_shares": 3700,
        "fill_quantity_proven": True, "submit_chain_uncertain": False,
        "cancel_chain_uncertain": False, "reason": reason,
    }]}


def test_working_recovery_delivers_once_and_fill_delivers_changed_result(tmp_path):
    sent = []
    notices = MorningNotifications("2026-10-14", root=tmp_path,
        sender=lambda *args: sent.append(args) or {"status": "ok"},
        recipients=lambda: ("user",))
    facts = working_result()
    notices.publish("result", facts)
    notices.publish("result", {**facts, "status": "blocked"})
    notices.publish("result", {**facts, "status": "completed", "orders": [{
        **facts["orders"][0], "state": "filled", "filled_shares": 3700,
        "remaining_shares": 0, "fill_price": 7.89,
    }]})
    assert all(row["status"] == "delivered" for row in notices.close())
    assert len(sent) == 2


@pytest.mark.parametrize("changed", [
    {"reason": "ACCOUNT_BINDING_UNPROVEN"},
    {"failed_stage": "execution"},
    {"user_action_required": True, "user_action": {"required": True, "request": "Restore login"}},
])
def test_new_dependency_is_not_hidden_by_working_order(changed):
    facts = working_result()
    assert result_fingerprint({**facts, "status": "blocked", **changed}) != result_fingerprint(facts)


def test_uncertain_delivery_is_not_replayed_by_recovery(tmp_path):
    sent = []
    notices = MorningNotifications("2026-10-14", root=tmp_path,
        sender=lambda *args: sent.append(args) or {"status": "uncertain"},
        recipients=lambda: ("user",))
    facts = working_result()
    notices.publish("result", facts)
    notices.publish("result", {**facts, "status": "blocked"})
    assert all(row["status"] == "pending" for row in notices.close())
    assert len(sent) == 1
