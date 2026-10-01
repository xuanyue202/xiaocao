"""Frozen legacy paper facts; no APP, API, account writer or market calls."""
import json
from copy import deepcopy
from datetime import date

import pytest

from xiaocao.research.weekly_production_adapter import build_production_observations, render_production_observations


# Cash facts from the production 2026-06-12 Book-A lot (display prices rounded).
POSITION = {
    "book": "A", "code": "300264.XSHE", "entry_date": "2026-06-12",
    "entry_price": 10.22, "shares": 1600, "gross_notional": 16352.0,
    "entry_fee": 1.64, "entry_cash_out": 16353.64, "status": "closed",
    "exit_date": "2026-06-15", "exit_price": 8.86, "exit_fee": 1.42,
    "exit_cash_in": 14174.58, "realized_pnl": -2179.06,
    "entry_price_basis": "open_reference",
}
BUY = {"book": "A", "code": "300264.XSHE", "date": "2026-06-12",
       "side": "BUY", "price": 10.22, "shares": 1600,
       "gross_notional": 16352.0, "fee": 1.64, "ts": "2026-06-12T12:04:09"}
SELL = {"book": "A", "code": "300264.XSHE", "date": "2026-06-15",
        "side": "SELL", "price": 8.86, "shares": 1600,
        "gross_notional": 14176.0, "fee": 1.42, "realized_pnl": -2179.06}


def frozen(positions=None, trades=None):
    return {"output/live/positions.jsonl": encode([POSITION] if positions is None else positions),
            "output/live/paper_trades.jsonl": encode([BUY, SELL] if trades is None else trades)}


def encode(rows):
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


def observe(contents=None, as_of=date(2026, 6, 19)):
    return build_production_observations(frozen() if contents is None else contents, as_of=as_of)


def test_consumes_real_legacy_cash_facts_without_claiming_nav_or_timeliness():
    report = observe()
    assert report["counts"]["valid"] == 1
    assert report["books"]["A"]["closed_cash_net_change"] == -2179.06
    assert report["books"]["A"]["entry_fee"] == 1.64
    assert report["books"]["A"]["exit_fee"] == 1.42
    assert report["latest_record_date"] == "2026-06-15"
    assert report["timeliness_proven"] is False
    assert report["books"]["B"]["closed_cash_net_change"] is None


def test_ambiguous_exit_cannot_validly_close_either_lot():
    second = {**POSITION, "entry_date": "2026-06-11"}
    second_buy = {**BUY, "date": "2026-06-11"}
    report = observe(frozen([POSITION, second], [BUY, second_buy, SELL]))
    assert report["counts"]["valid"] == 0
    assert report["counts"]["unknown"] == 2
    assert report["books"]["A"]["closed_cash_net_change"] is None


@pytest.mark.parametrize("field,value", [
    ("book", None), ("entry_fee", None), ("entry_fee", True),
    ("entry_cash_out", "NaN"), ("shares", -1), ("shares", 1.5),
    ("entry_price", 999), ("entry_date", "bad"), ("exit_date", "2026-06-10"),
    ("exit_fee", None), ("realized_pnl", 0), ("status", "unknown"),
])
def test_invalid_cash_identity_stays_unknown_without_crashing(field, value):
    changed = {**POSITION, field: value}
    report = observe(frozen([changed]))
    assert report["counts"]["valid"] == 0
    assert report["counts"]["unknown"] == 1
    assert report["books"]["A"]["closed_cash_net_change"] is None


@pytest.mark.parametrize("trade_index,field,value", [
    (0, "fee", 1.63), (0, "shares", 1700), (0, "gross_notional", 16353),
    (0, "price", 10.3), (1, "fee", 1.43), (1, "realized_pnl", -2000),
    (1, "entry_date", "2026-06-11"),
])
def test_cross_source_conflicts_do_not_repair_original_truth(trade_index, field, value):
    trades = deepcopy([BUY, SELL])
    trades[trade_index][field] = value
    row = {**POSITION, "_rederive_note": "historical repricing", "ledger_repair_id": "unverified"}
    report = observe(frozen([row], trades))
    assert report["counts"]["unknown"] == 1
    assert report["books"]["A"]["closed_cash_net_change"] is None
    assert next(item for item in report["audit"] if item["source"].endswith("positions.jsonl"))["repair_link_status"] == "unverified_original_to_rederived_link"


@pytest.mark.parametrize("positions,trades", [([POSITION, POSITION], [BUY, SELL]),
                                             ([POSITION], [BUY, BUY, SELL]),
                                             ([POSITION], [BUY, SELL, SELL])])
def test_duplicates_fail_closed(positions, trades):
    report = observe(frozen(positions, trades))
    assert report["counts"]["valid"] == 0
    assert report["counts"]["unknown"] == len(positions)


def test_future_closure_and_appended_future_rows_cannot_contaminate_history():
    original = {key: value for key, value in POSITION.items() if not key.startswith("exit_") and key != "realized_pnl"}
    original["status"] = "open"
    baseline = observe(frozen([original], [BUY]), as_of=date(2026, 6, 12))
    future = {**POSITION, "exit_fee": "bad", "realized_pnl": "bad"}
    future_entry = {**POSITION, "entry_date": "2026-07-10"}
    changed = observe(frozen([future, future_entry], [BUY, SELL, {**BUY, "date": "2026-07-10"}]), as_of=date(2026, 6, 12))
    assert changed["books"] == baseline["books"]
    assert changed["paired_exit_comparison"] == baseline["paired_exit_comparison"]
    assert changed["latest_record_date"] == baseline["latest_record_date"] == "2026-06-12"
    assert changed["counts"]["immature"] == 1
    assert changed["counts"]["future"] == 1


def test_empty_missing_and_bad_lines_are_distinct_from_zero_return():
    empty = observe(frozen([], []))
    missing = observe({})
    corrupt = observe({**frozen(), "output/live/positions.jsonl": b'no JSON\n[]\n' + encode([POSITION])})
    assert empty["books"]["A"]["entry_fee"] is None
    assert empty["books"]["A"]["mean_closed_lot_return_pct"] is None
    assert all(item["status"] == "missing" for item in missing["sources"])
    assert corrupt["counts"]["bad"] == 2
    assert corrupt["counts"]["valid"] == 1


def test_rounding_cash_priority_and_identical_entry_paired_exit_difference():
    # Recorded gross can differ from rounded display price times quantity.
    a = {**POSITION, "entry_price": 10.2204}
    b = {**a, "book": "B", "exit_cash_in": 15798.42, "exit_fee": 1.58,
         "exit_price": 9.875, "realized_pnl": -555.22}
    b_buy = {**BUY, "book": "B"}
    b_sell = {**SELL, "book": "B", "gross_notional": 15800.0, "fee": 1.58,
              "price": 9.875, "realized_pnl": -555.22}
    report = observe(frozen([a, b], [BUY, SELL, b_buy, b_sell]))
    pair = report["paired_exit_comparison"]
    assert pair["eligible"] == 1
    assert pair["mean_b_minus_a_pp"] == pytest.approx(9.929533734383048)
    assert report["books"]["B"]["closed_cash_net_change"] == -555.22
    mismatch = observe(frozen([a, {**b, "entry_price": 10.22}], [BUY, SELL, b_buy, b_sell]))
    assert mismatch["paired_exit_comparison"]["entry_mismatch"] == 1
    assert mismatch["paired_exit_comparison"]["mean_b_minus_a_pp"] is None


def test_pairing_reports_censoring_and_windows_do_not_invent_recent_records():
    b = {key: value for key, value in POSITION.items() if not key.startswith("exit_") and key != "realized_pnl"}
    b.update(book="B", status="open")
    report = observe(frozen([POSITION, b], [BUY, SELL, {**BUY, "book": "B"}]), as_of=date(2026, 10, 1))
    assert report["paired_exit_comparison"]["open"] == 1
    assert report["paired_exit_comparison"]["censored"] == 1
    assert report["paired_exit_comparison"]["eligible"] == 0
    assert report["windows"]["1w"]["latest_data_before_window"]
    assert report["windows"]["4w"]["books"]["A"]["closed_cash_net_change"] is None


def test_old_weekly_plans_can_render_missing_observations():
    assert render_production_observations({})


def test_unknown_lots_are_separate_from_excluded_pair_groups():
    report = observe(frozen([POSITION, {**POSITION, "book": "B", "entry_fee": None}]))
    assert report["paired_exit_comparison"]["excluded"] == 1
    assert report["paired_exit_comparison"]["unknown_lots"] == 1


def test_later_closure_preserves_already_matured_cohort_metrics_and_input_bytes():
    b = {key: value for key, value in POSITION.items() if not key.startswith("exit_") and key != "realized_pnl"}
    b.update(book="B", status="open")
    contents = frozen([POSITION, b], [BUY, SELL, {**BUY, "book": "B"}])
    preserved = deepcopy(contents)
    baseline = observe(contents)
    closed_b = {**POSITION, "book": "B", "exit_date": "2026-07-10"}
    later = observe(frozen([closed_b, POSITION],
                          [{**SELL, "book": "B", "date": "2026-07-10"}, SELL,
                           {**BUY, "book": "B"}, BUY]))
    assert later["books"] == baseline["books"]
    assert later["windows"] == baseline["windows"]
    assert later["paired_exit_comparison"] == baseline["paired_exit_comparison"]
    assert contents == preserved
