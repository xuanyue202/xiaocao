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


def snapshot(date, equity, **changes):
    return {"book": "B", "date": date, "ts": date + "T15:10:00+08:00",
            "cash": equity, "total_equity_after_exit_fee": equity,
            "initial_capital": 100000, "realized_pnl": equity - 100000,
            "unrealized_pnl_after_fee": 0, "holdings": [], "open_positions": 0,
            **changes}


def write_evidence(tmp_path, monkeypatch, snapshots, positions=()):
    monkeypatch.setattr(report, "LIVE_DIR", tmp_path)
    (tmp_path / "paper_holdings_snapshots.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in snapshots))
    (tmp_path / "positions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in positions))
    (tmp_path / "paper_account.json").write_text(json.dumps({"initial_capital": 100000, "cash": 9999999}))


def test_historical_portfolio_uses_only_dated_endpoints_and_asof_closures(tmp_path, monkeypatch):
    rows = [snapshot("2026-06-01", 110000), snapshot("2026-06-05", 121000)]
    position = {"book": "B", "code": "600000.XSHG", "entry_date": "2026-06-02",
                "shares": 100, "status": "open", "entry_cash_out": 1000, "entry_fee": 1}
    write_evidence(tmp_path, monkeypatch, rows, [position])
    before = report.paper_stats("2026-06-01", "2026-06-05")
    assert before["return_pct"] == 10.0
    assert before["closed_count"] == 0
    assert before["open_count"] == 1
    position.update(status="closed", exit_date="2026-06-08", realized_pnl=999999,
                    exit_cash_in=1000999, exit_fee=1)
    write_evidence(tmp_path, monkeypatch, rows + [snapshot("2026-06-08", 999999)], [position])
    after = report.paper_stats("2026-06-01", "2026-06-05")
    assert after == before


def test_missing_or_intraday_or_proxy_endpoint_is_explicit_unknown(tmp_path, monkeypatch):
    for rows in ([snapshot("2026-06-05", 121000)],
                 [snapshot("2026-06-01", 110000), snapshot("2026-06-05", 121000, ts="2026-06-05T14:59:00+08:00")],
                 [snapshot("2026-06-01", 110000), snapshot("2026-06-05", 121000, equity_basis="cost_basis")]):
        write_evidence(tmp_path, monkeypatch, rows)
        paper = report.paper_stats("2026-06-01", "2026-06-05")
        assert paper["return_pct"] is None
        assert paper["evidence_status"] == "unknown"
        built = {"paper": paper, "indices": []}
        assert "N/A" in report.markdown(built)
        json.dumps(paper, allow_nan=False)


def test_external_capital_is_not_portfolio_profit(tmp_path, monkeypatch):
    rows = [snapshot("2026-06-01", 100000, net_external_flows=0),
            snapshot("2026-06-05", 150000, net_external_flows=50000, realized_pnl=0)]
    write_evidence(tmp_path, monkeypatch, rows)
    assert report.paper_stats("2026-06-01", "2026-06-05")["return_pct"] is None
    (tmp_path / "paper_capital_flows.jsonl").write_text(json.dumps({
        "book": "B", "flow_id": "deposit-1", "date": "2026-06-03",
        "ts": "2026-06-03T15:10:00+08:00", "amount": 50000,
        "verified": True, "source_evidence": {"receipt": "deposit-1"},
    }) + "\n")
    paper = report.paper_stats("2026-06-01", "2026-06-05")
    assert paper["net_external_flows"] == 50000
    assert paper["period_pnl"] == 0
    assert paper["return_pct"] == 0
    assert paper["return_basis"] == "modified_dietz_eod_to_eod"


def test_invalid_snapshot_money_or_marks_and_corrupt_cohort_are_not_zero(tmp_path, monkeypatch):
    for changes in ({"cash": True}, {"total_equity_after_exit_fee": float("nan")},
                    {"total_equity_after_exit_fee": 121001},
                    {"holdings": [{"book": "B", "code": "600000.XSHG", "entry_date": "2026-06-01",
                                   "shares": 100, "cost": 1000, "liquidation_value_after_fee": 1100,
                                   "latest_time": "2026-06-04T15:00:00+08:00"}], "open_positions": 1}):
        write_evidence(tmp_path, monkeypatch, [snapshot("2026-06-01", 110000), snapshot("2026-06-05", 121000, **changes)])
        assert report.paper_stats("2026-06-01", "2026-06-05")["return_pct"] is None
    write_evidence(tmp_path, monkeypatch, [snapshot("2026-06-01", 110000), snapshot("2026-06-05", 121000)])
    (tmp_path / "positions.jsonl").write_text('broken\n')
    paper = report.paper_stats("2026-06-01", "2026-06-05")
    assert paper["closed_avg_ret_pct"] is None
    assert paper["buy_count"] is None
    assert paper["cohort_evidence_status"] == "unknown"


def test_intervening_capital_change_and_duplicate_closed_lots_are_unknown(tmp_path, monkeypatch):
    rows = [snapshot("2026-06-01", 100000), snapshot("2026-06-03", 150000, initial_capital=150000, realized_pnl=0),
            snapshot("2026-06-05", 100000)]
    write_evidence(tmp_path, monkeypatch, rows)
    assert report.paper_stats("2026-06-01", "2026-06-05")["return_pct"] is None
    lot = {"book": "B", "code": "600000.XSHG", "entry_date": "2026-06-02", "shares": 100,
           "entry_cash_out": 1000, "realized_pnl": 10, "status": "closed", "exit_date": "2026-06-03"}
    write_evidence(tmp_path, monkeypatch, [rows[0], rows[-1]], [lot, lot])
    paper = report.paper_stats("2026-06-01", "2026-06-05")
    assert paper["closed_avg_ret_pct"] is None
    assert paper["cohort_evidence_status"] == "unknown"


def test_flow_adjusted_gain_uses_dated_weight_and_preserves_four_index_unknown(tmp_path, monkeypatch):
    write_evidence(tmp_path, monkeypatch, [snapshot("2026-06-01", 100000, net_external_flows=0),
        snapshot("2026-06-05", 170000, net_external_flows=50000, realized_pnl=20000)])
    flow = {"book": "B", "flow_id": "deposit-1", "date": "2026-06-03",
            "ts": "2026-06-03T15:10:00+08:00", "amount": 50000, "verified": True,
            "source_evidence": {"receipt": "deposit-1"}}
    (tmp_path / "paper_capital_flows.jsonl").write_text(json.dumps(flow) + "\n")
    assert report.paper_stats("2026-06-01", "2026-06-05")["return_pct"] == 16.0
    flow["amount"] = 40000
    (tmp_path / "paper_capital_flows.jsonl").write_text(json.dumps(flow) + "\n")
    monkeypatch.setattr(report, "client", lambda: FakeClient({code: [
        {"tradeDate": "2026-06-01", "open": 90, "close": 100},
        {"tradeDate": "2026-06-05", "open": 100, "close": 110},
    ] for code in report.DEFAULT_INDICES}))
    built = report.build_report("2026-06-01", "2026-06-05", report.DEFAULT_INDICES, 80)
    assert built["index_avg_close_to_close_pct"] == 10.0
    assert built["paper_vs_index_avg_close_pp"] is None
    assert built["paper_vs_index_avg_open_pp"] is None
    assert "N/A" in report.markdown(built)
    assert "nan" not in report.markdown(built).lower()
