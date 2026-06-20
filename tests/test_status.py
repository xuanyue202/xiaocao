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
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    assert d["book_b"]["realized_pnl"] == -4191.0
    assert d["book_a"]["realized_pnl"] == 410.0
    # the headline: live stop policy minus validated next-close policy
    assert d["ab_realized_delta"] == -4601.0
    assert d["book_b"]["open_positions"] == 1
    assert d["today"]["automation"] == "live_monitor"
    assert d["today"]["triggered"][0]["sell_reason"] == "TRAILING_STOP"


def test_format_digest_is_readable_and_has_key_numbers(tmp_path):
    _seed(tmp_path, b_realized=-4191.0, a_realized=410.0)
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    text = S.format_digest(d)
    assert "book A" in text and "book B" in text and "A/B realized" in text
    assert "青龙管业" in text


def test_digest_tolerates_missing_files(tmp_path):
    # No live files at all -> defaults, never raises.
    d = S.build_digest(live_dir=tmp_path, market_date="2026-06-19")
    assert d["book_b"]["open_positions"] == 0 and d["ab_realized_delta"] == 0.0
    assert d["today"] == {}
