from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_ledger_books.py"
SPEC = importlib.util.spec_from_file_location("backfill_ledger_books", SCRIPT)
assert SPEC and SPEC.loader
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)


def test_plan_backfill_only_uses_provable_position_identity():
    positions = [
        {
            "code": "000001.XSHE", "entry_date": "2026-06-01",
            "exit_date": "2026-06-02", "source": "auto:vb_star", "status": "closed",
        },
        {
            "book": "T", "code": "000002.XSHE", "entry_date": "2026-06-01",
            "status": "open", "source": "auto:trend_book",
        },
    ]
    trades = [
        {"side": "BUY", "code": "000001.XSHE", "date": "2026-06-01", "source": "auto:vb_star"},
        {"side": "SELL", "code": "000001.XSHE", "date": "2026-06-02"},
        {"book": "T", "side": "BUY", "code": "000002.XSHE", "date": "2026-06-01"},
    ]

    fixed_positions, fixed_trades, report = backfill.plan_backfill(positions, trades)

    assert [row["book"] for row in fixed_positions] == ["B", "T"]
    assert [row["book"] for row in fixed_trades] == ["B", "B", "T"]
    assert report["positions_backfilled"] == 1
    assert report["trades_backfilled"] == 2
    assert report["position_changes"][0]["proof"] == "exclusive_writer_source:auto:vb_star"
    assert report["trade_changes"][1]["proof"] == "unique_position_identity"


def test_plan_backfill_accepts_current_book_b_writer_source_without_position():
    _, trades, report = backfill.plan_backfill([], [{
        "side": "BUY", "code": "301191.XSHE", "date": "2026-07-13",
        "source": "auto:mode_exec_star",
    }])
    assert trades[0]["book"] == "B"
    assert report["trades_backfilled"] == 1


def test_plan_backfill_refuses_unprovable_or_ambiguous_trade():
    with pytest.raises(RuntimeError, match="cannot prove book"):
        backfill.plan_backfill([], [{
            "side": "SELL", "code": "UNKNOWN", "date": "2026-06-02",
        }])

    positions = [
        {"book": "A", "code": "X", "entry_date": "2026-06-01", "exit_date": "2026-06-02"},
        {"book": "B", "code": "X", "entry_date": "2026-06-01", "exit_date": "2026-06-02"},
    ]
    with pytest.raises(RuntimeError, match="ambiguous"):
        backfill.plan_backfill(positions, [{
            "side": "SELL", "code": "X", "date": "2026-06-02",
        }])


def test_plan_backfill_refuses_conflicting_trade_facts():
    positions = [{
        "book": "B", "code": "X", "entry_date": "2026-06-01", "exit_date": "2026-06-02",
        "shares": 100, "exit_price": 10.0, "realized_pnl": 5.0,
    }]

    with pytest.raises(RuntimeError, match="cannot prove book"):
        backfill.plan_backfill(positions, [{
            "side": "SELL", "code": "X", "date": "2026-06-02",
            "shares": 200, "price": 9.0, "realized_pnl": -10.0,
        }])


def test_reconstruct_existing_repair_evidence_is_count_exact():
    positions = [{
        "book": "B", "code": "X", "entry_date": "2026-06-01", "exit_date": "2026-06-02",
        "shares": 100, "entry_price": 10.0, "exit_price": 10.1,
        "realized_pnl": 9.0, "source": "auto:vb_star",
    }]
    trades = [
        {"book": "B", "side": "BUY", "code": "X", "date": "2026-06-01",
         "shares": 100, "price": 10.0, "source": "auto:vb_star"},
        {"book": "B", "side": "SELL", "code": "X", "date": "2026-06-02",
         "shares": 100, "price": 10.1, "realized_pnl": 9.0},
    ]

    evidence = backfill.reconstruct_existing_repair_evidence(
        positions, trades, expected_positions=1, expected_trades=2,
    )

    assert evidence["audit_confidence"] == "reconstructed_after_fact"
    assert len(evidence["position_changes"]) == 1
    assert len(evidence["trade_changes"]) == 2
