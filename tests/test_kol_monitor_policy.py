from datetime import datetime
from zoneinfo import ZoneInfo

from scripts import live_monitor as monitor
from xiaocao.live.exit_policy import decide_sell_action


def decision(**overrides):
    kwargs = dict(detail={}, latest_price=10, peak=10, dd_pct=0,
                  dd_threshold=2, t1_blocked=False, hold_days=1, signal_score=0,
                  now=datetime(2026, 9, 7, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                  kol_exit={"triggered": True, "decision_id": "reviewed"})
    kwargs.update(overrides)
    return decide_sell_action({"mode": "首红断低吸", "xcjw": 100}, **kwargs)


def test_reviewed_kol_can_request_intraday_exit():
    assert decision()["sell_reason"] == "KOL_DISCRETIONARY_EXIT"


def test_kol_does_not_override_t_plus_one():
    assert decision(t1_blocked=True)["triggered"] is False


def test_hard_exit_precedes_kol_exit():
    assert decision(dd_pct=9)["sell_reason"] == "HARD_STOP"


def test_no_kol_decision_preserves_soft_exit_gate():
    result = decision(kol_exit=None, dd_pct=3)
    assert result["triggered"] is False
    assert result["deferred_sell_reason"]


def test_paper_exit_revalidates_policy_and_does_not_suppress_hard_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "OUT_DIR", tmp_path)
    monkeypatch.setattr(monitor, "ALERTS_FILE", tmp_path / "alerts.jsonl")
    monkeypatch.setattr(monitor.kol_policy, "load_decision", lambda *a, **k: {"status": "needs_refresh"})
    received = []
    def execute(rows, **kwargs):
        received.extend(rows)
        return len(rows), 0
    monkeypatch.setattr(monitor.paper_exit, "execute_simulated_sells", execute)
    rows = [{"sell_reason": "KOL_DISCRETIONARY_EXIT", "code": "603029.XSHG", "kol_decision_id": "old"},
            {"sell_reason": "HARD_STOP", "code": "600000.XSHG"}]
    assert monitor._execute_simulated_sells(object(), rows) == (1, 1)
    assert received == [rows[1]]
    assert "KOL_DECISION_REVALIDATION_REQUIRED" in (tmp_path / "alerts.jsonl").read_text()


def test_non_b_risk_does_not_load_account(monkeypatch):
    monkeypatch.setattr(monitor, "_account_file", lambda *a: (_ for _ in ()).throw(AssertionError()))
    assert monitor._record_paper_account_risk(object(), book="T")["status"] == "not_applicable"
