"""Tests for the status digest (src/xiaocao/live/status.py)."""
from __future__ import annotations

import json

from xiaocao.live import status as S


def _seed(live_dir, *, b_realized, a_realized):
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / "paper_account.json").write_text(json.dumps({
        "cash": 62000.0, "realized_pnl": b_realized, "total_fees": 47.0,
    }), encoding="utf-8")
    (live_dir / "paper_account_A.json").write_text(json.dumps({
        "cash": 56500.0, "realized_pnl": a_realized,
    }), encoding="utf-8")
    (live_dir / "paper_holdings.json").write_text(json.dumps({
        "date": "2026-06-19", "cash": 62000.0,
        "total_equity_after_exit_fee": 95000.0, "unrealized_pnl_after_fee": -120.0,
        "open_positions": 1,
        "holdings": [{"code": "002457.XSHE", "name": "青龙管业", "profile": "v5",
                      "net_ret_pct": -1.2, "dd_pct": 3.1}],
    }), encoding="utf-8")
    (live_dir / "decision_journal.jsonl").write_text(json.dumps({
        "run_id": "live_monitor:2026-06-19:x", "automation": "live_monitor",
        "market_date": "2026-06-19", "ts": "2026-06-19T14:56:00",
        "posture": {"regime": "weak", "score": -0.3},
        "deterministic": {
            "triggered": [{"code": "002457.XSHE", "name": "青龙管业", "sell_reason": "TRAILING_STOP"}],
            "deferred": [], "holds": [],
        },
    }) + "\n", encoding="utf-8")


def test_digest_assembles_books_and_ab_spread(tmp_path):
    _seed(tmp_path, b_realized=-4191.0, a_realized=410.0)
    (tmp_path / "positions.jsonl").write_text(json.dumps({
        "book": "A", "status": "open", "entry_cash_out": 10000.0,
    }) + "\n", encoding="utf-8")
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    assert d["book_b"]["realized_pnl"] == -4191.0
    assert d["book_a"]["realized_pnl"] == 410.0
    assert d["book_a"]["open_positions"] == 1
    assert d["book_a"]["open_entry_cash_out"] == 10000.0
    assert d["book_a"]["cost_basis_equity"] == 66500.0
    # the headline: live stop policy minus validated next-close policy
    assert d["ab_realized_delta"] == -4601.0
    assert d["book_b"]["open_positions"] == 1
    assert d["today"]["automation"] == "live_monitor"
    assert d["today"]["triggered"][0]["sell_reason"] == "TRAILING_STOP"


def test_format_digest_is_readable_and_has_key_numbers(tmp_path):
    _seed(tmp_path, b_realized=-4191.0, a_realized=410.0)
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    text = S.format_digest(d)
    assert "book A" in text and "book B" in text and "A/B 累计账面差" in text
    assert "青龙管业" in text
    assert "不可直接归因" in text
    assert "配对退出样本" in text


def test_digest_includes_book_t_when_present(tmp_path):
    _seed(tmp_path, b_realized=-4191.0, a_realized=410.0)
    (tmp_path / "paper_account_T.json").write_text(json.dumps({
        "cash": 21000.0, "realized_pnl": 123.0, "total_fees": 3.0,
    }), encoding="utf-8")
    (tmp_path / "paper_holdings_T.json").write_text(json.dumps({
        "date": "2026-06-19", "book": "T", "cash": 21000.0,
        "realized_pnl": 123.0, "total_fees": 3.0,
        "total_equity_after_exit_fee": 30500.0,
        "unrealized_pnl_after_fee": 500.0,
        "open_positions": 1,
        "holdings": [{"code": "T.XSHE", "entry_date": "2026-06-18", "shares": 100,
                      "cost": 9500.0}],
    }), encoding="utf-8")
    (tmp_path / "positions.jsonl").write_text(json.dumps({
        "book": "T", "status": "open", "code": "T.XSHE", "entry_date": "2026-06-18",
        "shares": 100, "entry_cash_out": 9500.0,
    }) + "\n", encoding="utf-8")

    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    assert d["book_t_present"] is True
    assert d["book_t"]["open_positions"] == 1
    assert d["book_t"]["realized_pnl"] == 123.0
    assert d["book_t"]["valuation_status"] == "fresh"
    assert "book T" in S.format_digest(d)


def test_stale_book_t_snapshot_falls_back_to_cost_basis_without_fake_unrealized(tmp_path):
    _seed(tmp_path, b_realized=-4191.0, a_realized=410.0)
    (tmp_path / "paper_account_T.json").write_text(json.dumps({
        "cash": 500.0, "realized_pnl": -100.0, "total_fees": 3.0,
    }), encoding="utf-8")
    (tmp_path / "positions.jsonl").write_text(json.dumps({
        "book": "T", "status": "open", "code": "T.XSHE", "entry_date": "2026-07-13",
        "shares": 100, "entry_cash_out": 9500.0,
    }) + "\n", encoding="utf-8")
    (tmp_path / "paper_holdings_T.json").write_text(json.dumps({
        "date": "2026-07-13", "cash": 500.0, "realized_pnl": -100.0,
        "total_fees": 3.0, "total_equity_after_exit_fee": 9000.0,
        "unrealized_pnl_after_fee": -1000.0, "open_positions": 1,
        "holdings": [{"code": "T.XSHE", "entry_date": "2026-07-13", "shares": 100}],
    }), encoding="utf-8")

    d = S.build_digest(live_dir=tmp_path, market_date="2026-07-14")

    assert d["book_t"]["open_positions"] == 1
    assert d["book_t"]["valuation_status"] == "stale"
    assert d["book_t"]["equity"] == 10000.0
    assert d["book_t"]["equity_basis"] == "cost_basis"
    assert d["book_t"]["unrealized_pnl"] is None
    assert "估值 N/A" in S.format_digest(d)


def test_mismatched_book_t_snapshot_never_controls_open_count_or_equity(tmp_path):
    _seed(tmp_path, b_realized=0.0, a_realized=0.0)
    (tmp_path / "paper_account_T.json").write_text(json.dumps({
        "cash": 1000.0, "realized_pnl": 0.0, "total_fees": 0.0,
    }), encoding="utf-8")
    (tmp_path / "positions.jsonl").write_text(json.dumps({
        "book": "T", "status": "open", "code": "NEW.XSHE", "entry_date": "2026-07-14",
        "shares": 100, "entry_cash_out": 9000.0,
    }) + "\n", encoding="utf-8")
    (tmp_path / "paper_holdings_T.json").write_text(json.dumps({
        "date": "2026-07-14", "cash": 1000.0, "realized_pnl": 0.0,
        "total_equity_after_exit_fee": 20000.0, "unrealized_pnl_after_fee": 10000.0,
        "open_positions": 3,
        "holdings": [{"code": "OLD.XSHE", "entry_date": "2026-07-13", "shares": 100}],
    }), encoding="utf-8")

    t = S.build_digest(live_dir=tmp_path, market_date="2026-07-14")["book_t"]

    assert t["open_positions"] == 1
    assert t["valuation_status"] == "mismatch"
    assert t["equity"] == 10000.0 and t["unrealized_pnl"] is None


def test_book_t_snapshot_missing_account_totals_is_not_fresh(tmp_path):
    _seed(tmp_path, b_realized=0.0, a_realized=0.0)
    (tmp_path / "paper_account_T.json").write_text(json.dumps({
        "cash": 1000.0, "realized_pnl": 0.0, "total_fees": 0.0,
    }), encoding="utf-8")
    (tmp_path / "positions.jsonl").write_text(json.dumps({
        "book": "T", "status": "open", "code": "T.XSHE", "entry_date": "2026-07-14",
        "shares": 100, "entry_cash_out": 9000.0,
    }) + "\n", encoding="utf-8")
    (tmp_path / "paper_holdings_T.json").write_text(json.dumps({
        "date": "2026-07-14", "total_equity_after_exit_fee": 10100.0,
        "unrealized_pnl_after_fee": 100.0,
        "holdings": [{"code": "T.XSHE", "entry_date": "2026-07-14", "shares": 100}],
    }), encoding="utf-8")

    t = S.build_digest(live_dir=tmp_path, market_date="2026-07-14")["book_t"]

    assert t["valuation_status"] == "mismatch"
    assert "missing account total cash" in t["valuation_reason"]
    assert t["equity"] == 10000.0 and t["unrealized_pnl"] is None


def test_book_t_account_missing_total_is_not_fresh(tmp_path):
    _seed(tmp_path, b_realized=0.0, a_realized=0.0)
    (tmp_path / "paper_account_T.json").write_text(json.dumps({
        "cash": 1000.0, "realized_pnl": 0.0,
    }), encoding="utf-8")
    (tmp_path / "positions.jsonl").write_text(json.dumps({
        "book": "T", "status": "open", "code": "T.XSHE", "entry_date": "2026-07-14",
        "shares": 100, "entry_cash_out": 9000.0,
    }) + "\n", encoding="utf-8")
    (tmp_path / "paper_holdings_T.json").write_text(json.dumps({
        "date": "2026-07-14", "cash": 1000.0, "realized_pnl": 0.0, "total_fees": 0.0,
        "total_equity_after_exit_fee": 10100.0, "unrealized_pnl_after_fee": 100.0,
        "holdings": [{"code": "T.XSHE", "entry_date": "2026-07-14", "shares": 100}],
    }), encoding="utf-8")

    t = S.build_digest(live_dir=tmp_path, market_date="2026-07-14")["book_t"]

    assert t["valuation_status"] == "mismatch"
    assert t["valuation_reason"] == "account missing total total_fees"


def test_push_body_omits_title_so_notify_does_not_duplicate_it(tmp_path):
    _seed(tmp_path, b_realized=-4191.0, a_realized=410.0)
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    body = S.format_digest_body(d)
    assert not body.startswith("小草盘后")
    assert "结论" in body and "持仓" in body


def test_digest_tolerates_missing_files(tmp_path):
    # No live files at all -> defaults, never raises. The A/B spread must be None
    # (undefined), NOT a fabricated 0.0, when book A is absent.
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    assert d["book_b"]["open_positions"] == 0
    assert d["book_a_present"] is False and d["ab_realized_delta"] is None
    assert d["today"] == {}


def test_ab_delta_not_faked_when_only_book_a_missing(tmp_path):
    # Book B has a real realized PnL but settle_book_a hasn't run: the spread must
    # NOT collapse to book B's entire PnL against an empty book-A baseline (the
    # exact self-deceiving "stops helped +4191" signal iteration-7 guards against).
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper_account.json").write_text(
        json.dumps({"cash": 1.0, "realized_pnl": -4191.0}), encoding="utf-8")
    (tmp_path / "paper_holdings.json").write_text(
        json.dumps({"date": "2026-06-19", "open_positions": 0, "holdings": []}), encoding="utf-8")
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    assert d["book_b"]["realized_pnl"] == -4191.0
    assert d["book_a_present"] is False and d["ab_realized_delta"] is None
    assert "N/A" in S.format_digest(d)
