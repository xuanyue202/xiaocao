"""APP profit reporting consumes proved accounting without changing it."""
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3

import pytest

from xiaocao.live import book_b_accounting as ledger
from xiaocao.live import status
from tests.book_b_fee_fixtures import fee_proof
from tests.test_book_b_accounting import cash_proof, observed
from tests.test_book_b_available_capital import activate, project, with_cash
from tests.test_book_b_live_lifecycle import NOW, _plan, _record_fill, _snapshot


pytestmark = pytest.mark.app_simulation
DATE = NOW.date().isoformat()


def _funded(live_dir):
    root = live_dir / "book_b_live_execution"
    root.mkdir()
    activate(root)
    account = project(root, with_cash(_snapshot(), 100000))
    return root, account


def test_pending_fees_keep_confirmed_profit_unknown_and_app_leads(tmp_path):
    root, _ = _funded(tmp_path)
    buy = _record_fill(root, replace(_plan(), shares=6000), price=10, event_id="large")
    account = observed(root, with_cash(_snapshot(shares=6000, price=11,
        broker_fills=(("order-large", buy.code, "BUY", 6000, 10),)), 39994))
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    digest = status.build_digest(live_dir=tmp_path, market_date=DATE, now=NOW)
    app = digest["book_b_app"]
    assert app["receipt_sha256"] == account.accounting["receipt_sha256"]
    assert app["marked_nav"] == "105994.00"
    assert app["provisional_unrealized_pnl"] == "5994.00"
    assert app["cumulative_pnl"] is None and len(app["pending_fee_orders"]) == 1
    body = status.format_digest_body(digest)
    assert body.index("APP 模拟 Book B") < body.index("book B 纸面")
    assert "+5,994.00" in body and "非最终收益" in body
    assert "N/A" in body
    assert all(p.read_bytes() == data for p, data in before.items())


def test_complete_fees_and_cash_report_confirmed_loss(tmp_path):
    root, _ = _funded(tmp_path)
    snapshot = with_cash(_snapshot(observed_at=NOW + timedelta(seconds=1)), 99995)
    ledger.record_cash_event(root, cash_proof(snapshot), now=NOW + timedelta(seconds=1))
    observed(root, snapshot)

    digest = status.build_digest(live_dir=tmp_path, market_date=DATE,
        now=NOW + timedelta(seconds=2))
    assert digest["book_b_app"]["cumulative_pnl"] == "-5.00"
    assert "-5.00" in status.format_digest_body(digest)


def test_unclassified_cash_does_not_become_profit(tmp_path):
    root, _ = _funded(tmp_path)
    observed(root, with_cash(_snapshot(observed_at=NOW + timedelta(seconds=1)), 100100))
    digest = status.build_digest(live_dir=tmp_path, market_date=DATE,
        now=NOW + timedelta(seconds=2))
    app = digest["book_b_app"]
    assert app["cash_difference"] == "100.00"
    assert app["marked_nav"] == "100000.00"
    assert app["fee_status"] == "actual_fees_complete"
    assert app["cumulative_pnl"] is None


def test_old_observation_is_not_current_profit(tmp_path):
    _funded(tmp_path)
    digest = status.build_digest(live_dir=tmp_path,
        market_date=(NOW + timedelta(days=1)).date().isoformat(), now=NOW + timedelta(days=1))
    assert digest["book_b_app"]["valuation_status"] == "stale"
    body = status.format_digest_body(digest)
    assert "100,000" not in body and DATE in body


def test_new_fill_invalidates_previous_profit_observation(tmp_path):
    root, _ = _funded(tmp_path)
    _record_fill(root, _plan(), price=10, event_id="after-observation")
    app = status.build_digest(live_dir=tmp_path, market_date=DATE, now=NOW)["book_b_app"]
    assert app["valuation_status"] == "unavailable" and "marked_nav" not in app


def test_missing_future_and_invalid_evidence_do_not_report_zero_profit(tmp_path, monkeypatch):
    missing = status.build_digest(live_dir=tmp_path, market_date=DATE, now=NOW)["book_b_app"]
    assert missing == {"valuation_status": "missing"}
    _funded(tmp_path)
    future = status.build_digest(live_dir=tmp_path, market_date=DATE,
        now=NOW - timedelta(seconds=1))["book_b_app"]
    assert future["valuation_status"] == "unavailable" and "cumulative_pnl" not in future
    monkeypatch.setattr(status, "latest_observation", lambda root: {"receipt_sha256": "bad"})
    invalid = status.build_digest(live_dir=tmp_path, market_date=DATE, now=NOW)["book_b_app"]
    assert invalid["valuation_status"] == "unavailable" and "cash" not in invalid


@pytest.mark.parametrize("body", [[], None, 7, "invalid"])
def test_malformed_saved_observation_does_not_break_paper_digest(tmp_path, body):
    root, _ = _funded(tmp_path)
    with sqlite3.connect(root / "accounting.sqlite3") as db:
        db.execute("INSERT INTO observations VALUES(?,?,?)",
            ("malformed", (NOW + timedelta(seconds=1)).isoformat(), json.dumps(body)))
    digest = status.build_digest(live_dir=tmp_path, market_date=DATE,
        now=NOW + timedelta(seconds=2))
    assert digest["book_b_app"]["valuation_status"] == "unavailable"
    assert "APP 模拟 Book B" in status.format_digest_body(digest)
    assert digest["book_b"]["open_positions"] == 0


def test_partial_actual_fee_coverage_reports_adjusted_provisional_pnl(tmp_path):
    root, _ = _funded(tmp_path)
    buy = _record_fill(root, replace(_plan(), shares=300), price=10, event_id="buy")
    _record_fill(root, _plan(side="SELL", lot_id=buy.plan_id), price=11, event_id="sell1")
    snapshot = with_cash(_snapshot(shares=200, price=11,
        broker_fills=(("order-buy", buy.code, "BUY", 300, 10),
                      ("order-sell1", buy.code, "SELL", 100, 11))), 98094.89)
    ledger.record_trade_fees(root, fee_proof(root, snapshot, "order-buy", "5.00"), now=NOW)
    observed(root, snapshot)
    digest = status.build_digest(live_dir=tmp_path, market_date=DATE, now=NOW)
    app = digest["book_b_app"]
    assert app["cumulative_pnl"] is None
    assert app["provisional_realized_pnl"] == "98.22"
    assert app["provisional_unrealized_pnl"] == "196.67"
    assert [p["broker_order_id"] for p in app["pending_fee_orders"]] == ["order-sell1"]
    body = status.format_digest_body(digest)
    assert "+98.22" in body and "+196.67" in body
    assert "已核费用按实际" in body and "缺失费用按计划费率" in body
