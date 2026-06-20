"""Tests for the capability-flywheel data transform (scripts/continuous_optimize.py).

Verifies the per-trade construction: each selected pick is paired against its
day's take-all mean (the counterfactual), so the guards see the honest per-trade
question — not a day-weighted headline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from xiaocao.research import guards

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import continuous_optimize as co  # noqa: E402


def _df():
    return pd.DataFrame([
        {"date": "2026-06-01", "code": "A", "kp_star": True, "net_realized_ret": 2.0},
        {"date": "2026-06-01", "code": "B", "kp_star": False, "net_realized_ret": 0.0},
        {"date": "2026-06-02", "code": "C", "kp_star": True, "net_realized_ret": -1.0},
        {"date": "2026-06-02", "code": "D", "kp_star": False, "net_realized_ret": 1.0},
        {"date": "2026-06-03", "code": "E", "kp_star": True, "net_realized_ret": float("nan")},  # no outcome
    ])


def test_build_results_pairs_each_pick_against_leave_one_out_baseline():
    res = co.build_results(_df(), "kp_star")
    # LEAVE-ONE-OUT baseline (pick excluded from the take-all mean):
    #   day 1: base for A = (2+0 - 2)/(2-1) = 0.0
    #   day 2: base for C = (-1+1 - (-1))/(2-1) = 1.0 ; day 3 dropped (NaN)
    assert res == [
        {"day": "2026-06-01", "strat_ret": 2.0, "base_ret": 0.0},
        {"day": "2026-06-02", "strat_ret": -1.0, "base_ret": 1.0},
    ]


def test_build_results_with_timestamp_dates_is_not_silently_zeroed():
    # The audited critical bug: a Timestamp-typed `date` column made the baseline
    # lookup miss and default to 0.0 for every pick, passing a LOSING strategy.
    import pandas as pd
    df = _df()
    df["date"] = pd.to_datetime(df["date"])  # Timestamp dtype, as a real parquet may store
    res = co.build_results(df, "kp_star")
    assert len(res) == 2
    # baselines must be the real leave-one-out values, NOT a fabricated 0.0
    assert res[0]["base_ret"] == 0.0 and res[1]["base_ret"] == 1.0


def test_losing_strategy_with_timestamp_dates_is_not_a_false_positive():
    # pick +0.5 on days where the rest average +2.0 -> the pick LOSES to take-all.
    # The old bug zeroed the baseline and reported a fabricated +0.5 spread (PASS).
    import pandas as pd
    rows = []
    for d in range(12):
        day = f"2026-06-{d + 1:02d}"
        rows.append({"date": day, "code": "PICK", "kp_star": True, "net_realized_ret": 0.5})
        for k in range(3):
            rows.append({"date": day, "code": f"O{k}", "kp_star": False, "net_realized_ret": 2.0})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    res = co.build_results(df, "kp_star")
    # every pick's baseline is the +2.0 non-pick mean -> spread -1.5, not +0.5
    assert all(abs(r["base_ret"] - 2.0) < 1e-9 for r in res)
    v = guards.evaluate_hypothesis(res, n_tried=1)
    assert v["per_trade"]["spread"] < 0 and v["verdict"] == "REJECTED"


def test_is_new_information_gates_ledger_appends():
    # The capability flywheel re-evaluates every run, but the ledger is a
    # changelog: only a missing or CHANGED verdict is worth appending. This is
    # what makes ledger.already_refuted load-bearing rather than dead code.
    rej = {"verdict": "REJECTED", "rejected_by": ["significant"]}
    assert co.is_new_information(None, rej) is True                       # first time -> record
    assert co.is_new_information(rej, rej) is False                       # unchanged -> skip
    assert co.is_new_information(rej, {"verdict": "PASS", "rejected_by": []}) is True   # flipped
    assert co.is_new_information(                                          # same verdict, new failing guard
        rej, {"verdict": "REJECTED", "rejected_by": ["significant", "enough_days"]}) is True


def test_build_results_empty_when_no_picks():
    df = _df()
    df["kp_star"] = False
    assert co.build_results(df, "kp_star") == []


def test_build_results_handles_missing_variant_column():
    assert co.build_results(_df(), "vb_star") == []
