from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts import research_exit_priors as rep


def _trade(**overrides) -> rep.EnrichedTrade:
    data = {
        "day": "2026-01-03",
        "mode": "首红断低吸",
        "code": "000001.XSHE",
        "return_pct": -5.0,
        "detail_present": True,
        "blocks": frozenset({"BK001"}),
        "mainline_strict": False,
        "mainline_relaxed": False,
        "big_cap": False,
        "primary_score": 120.0,
        "primary_score_label": "xcjw+0.8*cjs",
        "pct_change_rate": -1.0,
        "open_pct": 0.2,
        "strong_hold_strict": False,
        "strong_hold_relaxed": False,
    }
    data.update(overrides)
    return rep.EnrichedTrade(**data)


def test_normalize_date_accepts_cache_formats() -> None:
    assert rep.normalize_date("20260105") == "2026-01-05"
    assert rep.normalize_date("2026-01-05 09:30:00") == "2026-01-05"
    assert rep.normalize_date("8a8b7c") is None


def test_load_mode_history_filters_invalid_endpoint_and_duplicates(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE mode_history (mode TEXT, trade_date TEXT, code TEXT, return_pct REAL)")
        conn.executemany(
            "INSERT INTO mode_history VALUES (?, ?, ?, ?)",
            [
                ("首红断低吸", "2026-01-05", "000001.XSHE", 1.2),
                ("首红断低吸", "2026-01-05", "000001.XSHE", 1.2),
                ("/stock/date_kline", "2026-01-05", "000002.XSHE", 0.0),
                ("首红断低吸", "hash-row", "000003.XSHE", 0.0),
                ("首红断低吸", "2026-01-06", "", 0.0),
            ],
        )
    trades, invalid, summary = rep.load_mode_history(db)
    assert trades == [rep.ModeTrade(day="2026-01-05", mode="首红断低吸", code="000001.XSHE", return_pct=1.2)]
    assert summary["valid_rows"] == 1
    assert summary["invalid_rows"] == 4
    assert summary["invalid_reason_counts"] == {
        "duplicate_mode_day_code": 1,
        "endpoint_row": 1,
        "invalid_trade_date": 1,
        "missing_code": 1,
    }
    assert {row["reason"] for row in invalid} == set(summary["invalid_reason_counts"])


def test_build_mainline_by_date_uses_prior_days_only() -> None:
    days = ["2026-01-01", "2026-01-02", "2026-01-03"]
    ranks = {
        "2026-01-01": [{"code": "BK001", "score": 10}],
        "2026-01-02": [{"code": "BK001", "score": 9}],
        "2026-01-03": [{"code": "BK999", "score": 100}],
    }
    out = rep.build_mainline_by_date(days, ranks, window=2, topk=1, min_hits=2)
    assert out["2026-01-01"] == set()
    assert out["2026-01-02"] == set()
    assert out["2026-01-03"] == {"BK001"}


def test_result_rows_cash_out_when_candidate_rejects_trade() -> None:
    candidate = rep.candidates()[0]
    kept = _trade(return_pct=3.0, mainline_strict=True)
    skipped = _trade(code="000002.XSHE", return_pct=-5.0, mainline_strict=False)
    rows, coverage = rep.result_rows([kept, skipped], candidate)
    assert coverage["eligible_rows"] == 2
    assert coverage["kept_rows"] == 1
    assert rows[0]["strat_ret"] == 3.0 and rows[0]["base_ret"] == 3.0
    assert rows[1]["strat_ret"] == 0.0 and rows[1]["base_ret"] == -5.0


def test_bucket_report_rejects_collapsed_robustness_bucket() -> None:
    rows = []
    for i in range(25):
        rows.append({
            "day": f"2026-01-{i % 20 + 1:02d}",
            "mode": "首红断低吸",
            "mainline_strict": False,
            "strat_ret": 0.0,
            "base_ret": 1.0,
        })
    report = rep.bucket_report(rows, min_bucket_trades=20)
    assert report["l2_pass"] is False
    assert any(item["group"] == "quarter" for item in report["collapse_buckets"])


def test_live_path_report_is_read_only_counter(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    (live_dir / "positions.jsonl").write_text(
        "\n".join([
            json.dumps({"book": "B", "status": "open"}),
            json.dumps({"book": "A", "status": "closed", "exit_reason": "HARD_STOP"}),
        ]),
        encoding="utf-8",
    )
    (live_dir / "alerts.jsonl").write_text(
        json.dumps({"alert": "SELL_BLOCKED"}) + "\n" + json.dumps({"alert": "SELL_TRIGGERED"}) + "\n",
        encoding="utf-8",
    )
    (live_dir / "paper_trades.jsonl").write_text(json.dumps({"side": "SELL"}) + "\n", encoding="utf-8")
    before = {path.name: path.read_text(encoding="utf-8") for path in live_dir.iterdir()}
    report = rep.live_path_report(live_dir)
    after = {path.name: path.read_text(encoding="utf-8") for path in live_dir.iterdir()}
    assert before == after
    assert report["read_only"] is True
    assert report["book_b_rows"] == 1
    assert report["sell_blocked_alerts"] == 1
    assert report["paper_sell_trades"] == 1
