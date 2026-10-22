from dataclasses import replace
import json

import pytest

from tests.test_book_b_live_lifecycle import _plan, _record_fill
from xiaocao.research.app_b_lifecycle_report import build_lifecycle_report

pytestmark = pytest.mark.app_simulation


def test_report_keeps_estimated_profit_separate_from_missing_actual_fees(tmp_path):
    buy = _record_fill(tmp_path, _plan(trade_date="2026-08-31"), price=10, event_id="buy")
    _record_fill(tmp_path, _plan(side="SELL", lot_id=buy.plan_id), price=11, event_id="sell")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.jsonl")}
    report = build_lifecycle_report(tmp_path)
    lot = report["lots"][0]
    assert lot["remaining_shares"] == 0 and lot["estimated_realized_pnl"] > 0
    assert lot["confirmed_realized_pnl"] is None
    assert lot["assistance_basis"] == "unclassified"  # Fill alone does not prove an automation claim.
    assert report["headline_confirmed_profit"] is None
    assert not (tmp_path / "accounting.sqlite3").exists()
    assert before == {p: p.read_bytes() for p in before}


def test_explicit_assistance_is_not_counted_as_automatic_execution(tmp_path):
    _record_fill(tmp_path, replace(_plan(), plan_id="user-assisted:one"), price=10, event_id="buy")
    assert build_lifecycle_report(tmp_path)["lots"][0]["assistance_basis"] == "explicit_user_assistance"


def test_corrupt_execution_chain_cannot_produce_lifecycle_report(tmp_path):
    _record_fill(tmp_path, _plan(), price=10, event_id="buy")
    path = tmp_path / "events.jsonl"
    row = json.loads(path.read_text())
    row["receipt"]["filled_shares"] = 200
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError):
        build_lifecycle_report(tmp_path)
