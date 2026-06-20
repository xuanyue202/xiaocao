"""Tests for the research discipline guardrails (src/xiaocao/research/guards.py).

The decisive test mirrors the plan's verification: a day-weighting artifact (the
"+254% cum" trick) must be REJECTED, not laundered into a validated headline.
"""
from __future__ import annotations

from xiaocao.research import guards


def _genuine_edge_trades():
    # 12 days, 3 trades/day, a small consistent +0.01 per-trade edge with mild
    # day jitter so variance > 0 -> statistically significant, train+test both +.
    trades = []
    for i in range(12):
        day = f"2026-01-{i + 1:02d}"
        jitter = 0.001 * ((i % 3) - 1)  # -0.001, 0, +0.001
        for _ in range(3):
            trades.append({"day": day, "strat_ret": 0.01 + jitter, "base_ret": 0.0})
    return trades


def test_genuine_consistent_edge_passes():
    v = guards.evaluate_hypothesis(_genuine_edge_trades(), n_tried=1)
    assert v["verdict"] == "PASS", v["rejected_by"]
    assert v["per_trade"]["spread"] > 0
    assert v["walk_forward"]["consistent"] is True
    assert v["guards"]["significant"] is True


def test_day_weighting_artifact_is_rejected():
    # 7 days with ONE trade each at a big +0.5 edge (few trades, big edge) and
    # 1 day with 50 trades at -0.1 (many trades, small loss). Day-weighting makes
    # the spread look strongly positive; per-trade equal weighting makes it
    # negative — the exact "真的谎言" the guard must catch.
    trades = []
    for i in range(7):
        trades.append({"day": f"2026-02-{i + 1:02d}", "strat_ret": 0.5, "base_ret": 0.0})
    for _ in range(50):
        trades.append({"day": "2026-02-08", "strat_ret": -0.1, "base_ret": 0.0})
    v = guards.evaluate_hypothesis(trades, n_tried=1)
    assert v["day_weighted"]["spread"] > 0          # the inflated headline
    assert v["per_trade"]["spread"] < 0             # the honest number
    assert v["guards"]["survives_per_trade_equal_weight"] is False
    assert v["verdict"] == "REJECTED"
    assert "survives_per_trade_equal_weight" in v["rejected_by"]


def test_train_test_inconsistency_is_rejected():
    # Edge only in the first half of days (train), gone in the second (test).
    trades = []
    for i in range(6):
        trades.append({"day": f"2026-03-{i + 1:02d}", "strat_ret": 0.05, "base_ret": 0.0})
    for i in range(6, 12):
        trades.append({"day": f"2026-03-{i + 1:02d}", "strat_ret": -0.05, "base_ret": 0.0})
    v = guards.evaluate_hypothesis(trades, n_tried=1)
    assert v["walk_forward"]["consistent"] is False
    assert "walk_forward_consistent" in v["rejected_by"] and v["verdict"] == "REJECTED"


def test_too_few_days_is_rejected():
    trades = [{"day": "2026-04-01", "strat_ret": 0.02, "base_ret": 0.0} for _ in range(20)]
    v = guards.evaluate_hypothesis(trades, n_tried=1, min_days=8)
    assert v["guards"]["enough_days"] is False and "enough_days" in v["rejected_by"]


def test_multiple_comparison_tightens_significance():
    # A marginal edge significant at alpha=0.05 but not after Bonferroni for many
    # tries -> rejected, with a multiple-comparison warning.
    trades = _genuine_edge_trades()
    v1 = guards.evaluate_hypothesis(trades, n_tried=1)
    vmany = guards.evaluate_hypothesis(trades, n_tried=1)  # baseline
    assert v1["significance"]["effective_alpha"] == 0.05
    v_strict = guards.evaluate_hypothesis(trades, n_tried=100)
    assert v_strict["significance"]["effective_alpha"] < 0.001
    assert any("multiple comparison" in w for w in v_strict["warnings"])


def test_cache_only_false_is_rejected():
    v = guards.evaluate_hypothesis(_genuine_edge_trades(), n_tried=1, cache_only=False)
    assert v["guards"]["cache_only"] is False and "cache_only" in v["rejected_by"]
