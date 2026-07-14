from __future__ import annotations

import json

from scripts import research_paper_vs_market as report


class FakeClient:
    def __init__(self, rows_by_code):
        self.rows_by_code = rows_by_code

    def date_kline(self, code, **_kwargs):
        return self.rows_by_code.get(code, [])


def test_index_report_merges_reconstructed_end_bar(tmp_path) -> None:
    reconstructed = tmp_path / "daily_reconstructed.jsonl"
    reconstructed.write_text(json.dumps({
        "code": "IDX", "date": "20260714", "open": 110, "high": 120,
        "low": 108, "close": 115, "source": "minute_reconstructed",
    }) + "\n", encoding="utf-8")
    client = FakeClient({"IDX": [{"tradeDate": "2026-06-01", "open": 100, "close": 101}]})

    rows = report.index_report(
        client,
        start="2026-06-01",
        end="2026-07-14",
        index_map={"IDX": "指数"},
        count=80,
        reconstructed_path=reconstructed,
    )

    assert rows[0]["open_to_close_pct"] == 15.0
    assert rows[0]["end_source"] == "minute_reconstructed"


def test_missing_index_makes_aggregate_na_instead_of_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(report, "client", lambda: FakeClient({}))
    monkeypatch.setattr(report, "paper_stats", lambda *_args: {
        "start": "2026-06-01", "end": "2026-07-14", "return_pct": -0.54,
        "equity": 99460.0, "cash": 1000.0, "realized_pnl": -500.0,
        "unrealized_pnl": -40.0, "buy_count": 1, "closed_count": 1,
        "open_count": 0, "closed_avg_ret_pct": -0.5,
        "closed_median_ret_pct": -0.5, "closed_win_rate_pct": 0.0,
        "mode_breakdown": [], "exit_breakdown": [], "pnl_decompose": {},
    })
    monkeypatch.setattr(report, "RECONSTRUCTED_DAILY", tmp_path / "missing.jsonl")

    built = report.build_report("2026-06-01", "2026-07-14", {"IDX": "指数"}, 80)

    assert built["index_avg_open_to_close_pct"] is None
    assert built["paper_vs_index_avg_open_pp"] is None
    assert "N/A" in report.markdown(built)


def test_zero_or_missing_index_price_is_invalid_not_zero_return(tmp_path) -> None:
    client = FakeClient({"IDX": [
        {"tradeDate": "2026-06-01", "open": None, "close": 100},
        {"tradeDate": "2026-07-14", "open": 110, "close": 0},
    ]})

    rows = report.index_report(
        client, start="2026-06-01", end="2026-07-14",
        index_map={"IDX": "指数"}, count=80,
        reconstructed_path=tmp_path / "missing.jsonl",
    )

    assert rows[0]["error"] == "invalid non-positive start/end price"


def test_custom_single_index_never_authorizes_four_index_aggregate(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(report, "client", lambda: FakeClient({
        "IDX": [
            {"tradeDate": "2026-06-01", "open": 100, "close": 100},
            {"tradeDate": "2026-07-14", "open": 110, "close": 110},
        ],
    }))
    monkeypatch.setattr(report, "paper_stats", lambda *_args: {
        "start": "2026-06-01", "end": "2026-07-14", "return_pct": 1.0,
    })
    monkeypatch.setattr(report, "RECONSTRUCTED_DAILY", tmp_path / "missing.jsonl")

    built = report.build_report("2026-06-01", "2026-07-14", {"IDX": "指数"}, 80)

    assert built["index_coverage"] == "0/4"
    assert built["index_avg_open_to_close_pct"] is None
