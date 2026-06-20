"""Tests for the capability-flywheel data transform (scripts/continuous_optimize.py).

Verifies the per-trade construction: each selected pick is paired against its
day's take-all mean (the counterfactual), so the guards see the honest per-trade
question — not a day-weighted headline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

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


def test_build_results_pairs_each_pick_against_day_takeall():
    res = co.build_results(_df(), "kp_star")
    # day 1 take-all mean = (2+0)/2 = 1.0 ; day 2 = (-1+1)/2 = 0.0 ; day 3 dropped (NaN)
    assert res == [
        {"day": "2026-06-01", "strat_ret": 2.0, "base_ret": 1.0},
        {"day": "2026-06-02", "strat_ret": -1.0, "base_ret": 0.0},
    ]


def test_build_results_empty_when_no_picks():
    df = _df()
    df["kp_star"] = False
    assert co.build_results(df, "kp_star") == []


def test_build_results_handles_missing_variant_column():
    assert co.build_results(_df(), "vb_star") == []
