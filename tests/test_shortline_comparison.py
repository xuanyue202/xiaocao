import copy
import hashlib
import json
from datetime import date

import pytest

from xiaocao.research.shortline_comparison import SELECTORS, compare_shortline, render_comparison, observe_shortline_research


def label(day, code="000001.XSHE", value=3.0, **fields):
    return {"date": day, "code": code, "book": "B", "is_live": True,
            "executable_fillable": True, "executable_net_ret": value,
            **{key: True for key in SELECTORS}, **fields}


def position(book, pnl, **fields):
    return {"book": book, "code": "000001.XSHE", "mode": "N字低吸", "entry_date": "2026-10-01",
            "exit_date": "2026-10-02", "status": "closed", "shares": 100, "entry_price": 10,
            "entry_cash_out": 1000.1, "realized_pnl": pnl, **fields}


def compare(positions=(), training=()):
    return compare_shortline(list(positions), list(training), start="2026-10-01", end="2026-10-21")


def test_comparison_preserves_cash_days_and_missing_label_denominators():
    rows = [label("2026-10-01"), label("2026-10-02", mode_exec_star=False),
            label("2026-10-03", value=None), label("2026-10-04", kp_star=None),
            label("2026-10-05", code="830001.BJSE", value=999),
            label("2026-10-06", book="T", value=999)]
    original = copy.deepcopy(rows)
    report = compare(training=rows)
    assert rows == original
    assert report["coverage"]["candidate_rows"] == 5
    assert report["coverage"]["complete_label_days"] == 2
    assert report["coverage"]["excluded_incomplete_label_days"] == ["2026-10-03", "2026-10-05"]
    assert report["coverage"]["excluded_incomplete_flag_days"] == ["2026-10-04"]
    metrics = {row["selector"]: row for row in report["common_date_diagnostic"]}
    assert metrics["kp_star"]["mean_three_slot_measure_pct"] == 1
    assert metrics["mode_exec_star"]["mean_three_slot_measure_pct"] == .5
    assert report["portfolio_return"] is None and report["promotion_eligible"] is False


def test_exit_pairs_exclude_future_exits_and_different_entry_economics():
    rows = [position("A", 10), position("B", 20),
            position("A", 50, code="000002.XSHE"), position("B", 90, code="000002.XSHE", shares=200),
            position("A", 50, code="000003.XSHE"), position("B", 90, code="000003.XSHE", exit_date="2026-10-22")]
    pair = compare(positions=rows)["paired_exit"]
    assert pair["eligible_pairs"] == 1
    assert pair["mean_b_minus_a_pp"] == pytest.approx(10 / 1000.1 * 100)
    assert pair["excluded"] == {"shares_mismatch": 1, "not_both_closed": 1}


def test_duplicate_candidates_or_invalid_economics_are_not_silently_dropped():
    with pytest.raises(ValueError, match="DUPLICATE_TRAINING"):
        compare(training=[label("2026-10-01"), label("2026-10-01")])
    with pytest.raises(ValueError, match="ECONOMICS_INVALID"):
        compare(positions=[position("A", 1), position("B", float("nan"))])


def test_missing_flags_and_empty_inputs_are_unknown_not_zero_return():
    report = compare()
    assert report["paired_exit"]["mean_b_minus_a_pp"] is None
    assert all(row["mean_executable_label_pct"] is None for row in report["selector_labels"])
    assert all(row["mean_three_slot_measure_pct"] is None for row in report["common_date_diagnostic"])


def test_fill_evidence_discloses_both_sides_and_weaker_pair_basis():
    rows = []
    for index, (a_basis, b_basis) in enumerate([
        ({"entry_price_basis": "opening_window_vwap"}, {"entry_price_basis": "opening_window_vwap"}),
        ({"entry_price_basis": "opening_window_vwap"}, {"fill_fallback": True}),
        ({}, {"entry_price_basis": "retry_realtime_after_limit_reject"}),
        ({"entry_price_basis": "opening_window_vwap"}, {}),
    ]):
        code = f"00000{index}.XSHE"
        rows += [position("A", 10, code=code, **a_basis), position("B", 20, code=code, **b_basis)]
    report = compare(positions=rows)
    evidence = report["paired_exit"]["fill_evidence"]
    assert evidence["counts"] == {"reported_window": 1, "fallback": 1, "proxy": 1, "unknown": 1}
    assert evidence["proxy_including_fallback_proportion"] == .5
    assert evidence["classified_proportion"] == .75
    assert evidence["confirmed_execution_count"] == 0
    assert evidence["by_book"]["A"]["counts"]["unknown"] == 1
    assert report["traded_mode_cohorts"][0]["closed_fill_evidence"]["counts"] == evidence["counts"]
    assert report["paired_exit"]["eligible_pairs"] == 4
    # Exercise empty and populated render paths without locking narrative text.
    render_comparison(report)
    render_comparison(compare())


def test_report_rejects_input_replaced_during_data_health_check(tmp_path, monkeypatch):
    import runpy
    from pathlib import Path
    script = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/research_shortline_comparison.py"))
    live = tmp_path / "output/live"
    live.mkdir(parents=True)
    (live / "positions.jsonl").write_bytes(b"[]")
    (live / "training_rows.parquet").write_bytes(b"before")

    def check(_):
        (live / "training_rows.parquet").write_bytes(b"after")
        return {"critical": 0}

    monkeypatch.setattr(script["data_health"], "check", check)
    monkeypatch.setattr("sys.argv", ["research", "--data-root", str(tmp_path), "--end", "2026-10-21"])
    with pytest.raises(ValueError, match="INPUT_CHANGED_DURING_HEALTH_CHECK"):
        script["main"]()


def test_weekly_observer_requires_exact_saved_inputs_and_observation_clock():
    report = compare()
    inputs = {"output/research/shortline_comparisons/inputs/positions.jsonl": b"[]",
              "output/research/shortline_comparisons/inputs/training.parquet": b"fixture"}
    report.update(observed_at="2026-10-21T17:00:00+08:00",
                  inputs=[{"path": path, "sha256": hashlib.sha256(raw).hexdigest()} for path, raw in inputs.items()])
    raw = json.dumps(report).encode()
    path = "output/research/shortline_comparisons/2026-10-21-" + hashlib.sha256(raw).hexdigest() + ".json"
    contents = {**inputs, path: raw}
    result = observe_shortline_research(contents, as_of=date(2026, 10, 21))
    assert result["current_window_report_observed"] and result["status"] == "observed"
    assert observe_shortline_research(contents, as_of=date(2026, 10, 20))["status"] == "missing"
    contents[next(iter(inputs))] = b"changed"
    result = observe_shortline_research(contents, as_of=date(2026, 10, 21))
    assert result["status"] == "missing" and result["invalid"] == [path]
