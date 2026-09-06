from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from xiaocao.live import paper_decision_support as support


NOW = datetime(2026, 9, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
CODE = "000001.XSHE"


def account(nav=100000.0, **changes):
    return {"account_id": "paper:B", "initial_capital": 100000.0, "cash": nav,
            "realized_pnl": nav - 100000.0, "fee_rate": 0.0001, **changes}


def lot(**changes):
    return {"book": "B", "code": CODE, "entry_date": "2026-09-04", "shares": 1000,
            "entry_price": 10.0, "gross_notional": 10000.0, "entry_fee": 1.0,
            "entry_cash_out": 10001.0, "fee_rate": 0.0001, **changes}


def quote(**changes):
    return {"code": CODE, "price": 12.0, "observed_at": NOW.isoformat(), "source": "xiaocao_api", **changes}


def evaluate(root, acct=None, positions=None, *, now=NOW, mark=None):
    return support.evaluate_paper_risk(root, account() if acct is None else acct,
                                      [] if positions is None else positions, now=now,
                                      mark_provider=lambda code: quote() if mark is None else mark)


def test_cash_only_epoch_and_account_state_untouched(tmp_path):
    live = tmp_path / "output/live"
    live.mkdir(parents=True)
    canonical = live / "paper_account.json"
    canonical.write_text(json.dumps(account()), encoding="utf-8")
    before = canonical.read_bytes()
    (live / "book_b_live_execution").mkdir()
    (live / "book_b_live_execution/settlement.json").write_text('{"nav": 99999999}')
    receipt = evaluate(tmp_path)
    assert receipt["status"] == "NORMAL"
    assert receipt["nav"] == receipt["high_water_mark"] == 100000
    assert receipt["history_basis"] == "since_activation"
    assert receipt["tracking_epoch_started_at"]
    assert receipt["valuation"]["marks"] == []
    assert canonical.read_bytes() == before
    assert support._read_bound(support.risk_directory(tmp_path) / "risk_latest.json") == receipt


def test_nav_marks_explicit_open_b_only_and_deducts_exit_fee(tmp_path):
    positions = [lot(status="closed"), lot(book="A"), lot(book="T"),
                 lot(code="600000.XSHG", exit_date="2026-09-05", exit_price=11.0)]
    receipt = evaluate(tmp_path, account(cash=89999), positions)
    assert receipt["status"] == "NORMAL"
    assert receipt["nav"] == 101997.8
    assert receipt["valuation"]["market_value"] == 12000
    assert len(receipt["valuation"]["marks"]) == 1


@pytest.mark.parametrize("changes,reason", [
    ({"account_id": "live:B"}, "PAPER_ACCOUNT_ID_MISMATCH"),
    ({"book": "T"}, "PAPER_ACCOUNT_ID_MISMATCH"),
    ({"book": "A"}, "PAPER_ACCOUNT_ID_MISMATCH"),
    ({"runtime": "live"}, "PAPER_ACCOUNT_ID_MISMATCH"),
    ({"cash": -1}, "PAPER_NUMBER_INVALID"),
    ({"cash": float("nan")}, "PAPER_NUMBER_INVALID"),
    ({"cash": float("inf")}, "PAPER_NUMBER_INVALID"),
    ({"cash": True}, "PAPER_NUMBER_INVALID"),
    ({"cash": "100000"}, "PAPER_NUMBER_INVALID"),
    ({"cash": 120000}, "PAPER_ACCOUNT_EQUATION_FAILED"),
    ({"external_flow_total": 1}, "PAPER_EXTERNAL_FLOW_OR_FEE_INVALID"),
])
def test_bad_account_fails_closed(tmp_path, changes, reason):
    receipt = evaluate(tmp_path, account(**changes))
    assert receipt["status"] == "BLOCKED"
    assert receipt["deploy_factor"] == 0
    assert reason in receipt["reasons"]
    json.dumps(receipt, allow_nan=False)


@pytest.mark.parametrize("changes", [
    {"observed_at": (NOW - timedelta(seconds=301)).isoformat()},
    {"observed_at": (NOW - timedelta(days=1)).isoformat()},
    {"observed_at": (NOW + timedelta(seconds=1)).isoformat()},
    {"observed_at": "2026-09-06"},
    {"observed_at": "broken"},
    {"source": "public"},
    {"price": 0}, {"price": float("nan")}, {"price": float("inf")},
    {"code": "600000.XSHG"},
])
def test_missing_stale_malformed_marks_never_use_entry_cost(tmp_path, changes):
    receipt = evaluate(tmp_path, account(cash=89999), [lot()], mark=quote(**changes))
    assert receipt["status"] == "BLOCKED"
    assert receipt["nav"] is None
    assert receipt["deploy_factor"] == 0


def test_raw_proprietary_clock_requires_actual_date(tmp_path):
    mark = {"code": CODE, "trade": 12.0, "tradeDate": "20260906",
            "tradeTimestamp": "09:59:59:123", "_source": "xiaocao_api"}
    assert evaluate(tmp_path, account(cash=89999), [lot()], mark=mark)["nav"] == 101997.8
    mark.pop("tradeDate")
    assert evaluate(tmp_path, account(cash=89999), [lot()], now=NOW + timedelta(seconds=1), mark=mark)["status"] == "BLOCKED"


@pytest.mark.parametrize("bad", [
    {**lot(), "book": None}, lot(shares=100.5), lot(exit_price=0),
    lot(entry_cash_out=10000), lot(gross_notional=9000), lot(shares=0),
])
def test_malformed_lots_block(tmp_path, bad):
    assert evaluate(tmp_path, account(cash=89999), [bad])["status"] == "BLOCKED"


def test_canonical_identity_and_torn_positions_block(tmp_path):
    live = tmp_path / "output/live"
    live.mkdir(parents=True)
    (live / "paper_account.json").write_text(json.dumps(account()), encoding="utf-8")
    assert evaluate(tmp_path, account(120000))["status"] == "BLOCKED"
    (live / "positions.jsonl").write_text("broken\n", encoding="utf-8")
    receipt = evaluate(tmp_path)
    assert "PAPER_POSITION_BOOK_REQUIRED" in receipt["reasons"]


def test_hwm_ten_twenty_and_pause_survive_rebound_and_block(tmp_path):
    peak = evaluate(tmp_path, account(120000))
    reduced = evaluate(tmp_path, account(108000), now=NOW + timedelta(minutes=1))
    assert reduced["status"] == "REDUCED"
    assert reduced["drawdown_pct"] == 10
    assert reduced["deploy_factor"] == 0.5
    paused = evaluate(tmp_path, account(96000), now=NOW + timedelta(minutes=2))
    assert paused["status"] == "PAUSED" and paused["pause_latched"]
    blocked = evaluate(tmp_path, account(cash=89999), [lot()], now=NOW + timedelta(minutes=6))
    assert blocked["status"] == "BLOCKED" and blocked["high_water_mark"] == 120000
    assert blocked["pause_latched"]
    rebound = evaluate(tmp_path, account(130000), now=NOW + timedelta(minutes=7))
    assert rebound["status"] == "PAUSED" and rebound["high_water_mark"] == 130000
    assert rebound["tracking_epoch_started_at"] == peak["tracking_epoch_started_at"]
    assert rebound["previous_receipt_sha256"] == blocked["receipt_sha256"]


def test_corrupt_receipt_never_reinitializes_epoch(tmp_path):
    evaluate(tmp_path, account(120000))
    head = support.risk_directory(tmp_path) / "risk_latest.json"
    original = json.loads(head.read_text())
    original["high_water_mark"] = 100000
    head.write_text(json.dumps(original))
    before = head.read_bytes()
    for minute in (1, 2):
        receipt = evaluate(tmp_path, now=NOW + timedelta(minutes=minute))
        assert receipt["status"] == "BLOCKED"
        assert "PREVIOUS_RECEIPT_INVALID" in receipt["reasons"]
        assert head.read_bytes() == before


def test_capital_change_cannot_reset_peak(tmp_path):
    evaluate(tmp_path, account(120000))
    before = (support.risk_directory(tmp_path) / "risk_latest.json").read_bytes()
    receipt = evaluate(tmp_path, account(200000, initial_capital=200000, realized_pnl=0),
                       now=NOW + timedelta(minutes=1))
    assert receipt["status"] == "BLOCKED"
    assert "PREVIOUS_RECEIPT_INVALID" in receipt["reasons"]
    assert (support.risk_directory(tmp_path) / "risk_latest.json").read_bytes() == before


def test_mark_acquisition_is_per_code_and_rate_limited(tmp_path, monkeypatch):
    calls, sleeps = [], []
    class Client:
        def second_line_detail_info(self, code):
            calls.append(code)
            return {code: {"trade": 10.0, "tradeDate": "20260906", "tradeTimestamp": "10:00:00"}}
    monkeypatch.setattr(support.time, "sleep", sleeps.append)
    positions = [lot(), lot(entry_date="2026-09-03"), lot(code="600000.XSHG"), lot(book="T")]
    marks = support.fetch_paper_marks(Client(), positions)
    assert calls == sorted([CODE, "600000.XSHG"])
    assert sleeps == [0.6]
    assert marks[CODE]["_source"] == "xiaocao_api"


def test_lost_head_blocks_instead_of_resetting_durable_peak(tmp_path):
    evaluate(tmp_path, account(130000))
    (support.risk_directory(tmp_path) / "risk_latest.json").unlink()
    receipt = evaluate(tmp_path, now=NOW + timedelta(minutes=1))
    assert receipt["status"] == "BLOCKED"
    assert "PREVIOUS_RECEIPT_INVALID" in receipt["reasons"]
    assert not (support.risk_directory(tmp_path) / "risk_latest.json").exists()


def test_bad_capital_read_preserves_previous_hwm_and_recovers(tmp_path):
    evaluate(tmp_path, account(130000))
    blocked = evaluate(tmp_path, {}, now=NOW + timedelta(minutes=1))
    assert blocked["status"] == "BLOCKED"
    assert blocked["high_water_mark"] == 130000
    restored = evaluate(tmp_path, account(120000), now=NOW + timedelta(minutes=2))
    assert restored["status"] == "NORMAL"
    assert restored["high_water_mark"] == 130000


def test_lock_keeps_all_concurrent_peaks(tmp_path):
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda nav: evaluate(tmp_path, account(nav)),
                                 [100000, 120000, 110000, 130000]))
    assert all(row["status"] != "BLOCKED" for row in receipts)
    head = support._read_bound(support.risk_directory(tmp_path) / "risk_latest.json")
    assert head["high_water_mark"] == 130000
    assert len(list((support.risk_directory(tmp_path) / "risk_receipts").glob("*.json"))) == 4


def test_changed_fee_or_partial_positions_cannot_revalue_canonical_account(tmp_path):
    live = tmp_path / "output/live"
    live.mkdir(parents=True)
    (live / "paper_account.json").write_text(json.dumps(account(cash=89999)))
    (live / "positions.jsonl").write_text(json.dumps(lot()) + "\n")
    omitted = evaluate(tmp_path, account(cash=89999), [])
    altered_fee = evaluate(tmp_path, account(cash=89999), [lot(fee_rate=0.0)])
    assert "PAPER_CANONICAL_POSITIONS_MISMATCH" in omitted["reasons"]
    assert "PAPER_CANONICAL_POSITIONS_MISMATCH" in altered_fee["reasons"]


def test_storage_failure_never_returns_an_allow(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("simulated persistence failure")
    monkeypatch.setattr(support, "_atomic_json", fail)
    with pytest.raises(OSError, match="persistence failure"):
        evaluate(tmp_path)
