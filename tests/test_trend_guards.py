from __future__ import annotations

from xiaocao.research import trend_guards as tg


def _holds(diffs, base=1.0, regimes=None, turnover=0.3):
    """Build holds with strat = base + diff per hold; regimes optional list."""
    regimes = regimes or ["trend_strong"] * len(diffs)
    out = []
    for i, d in enumerate(diffs):
        out.append({"entry": f"2025-{i+1:02d}-01", "strat_ret": base + d,
                    "base_ret": base, "regime": regimes[i], "turnover": turnover})
    return out


def test_compounded_and_drawdown():
    # strat returns +10,-20,+10 -> equity 1.1, 0.88, 0.968; peak 1.1; mdd=(1.1-0.88)/1.1
    holds = [{"entry": f"d{i}", "strat_ret": r, "base_ret": 0.0} for i, r in enumerate([10, -20, 10])]
    v = tg.evaluate_trend(holds, min_holds=1, min_nonbull_holds=99)
    assert abs(v["max_drawdown"] - (1.1 - 0.88) / 1.1 * 100) < 1e-6
    assert v["compounded"]["base"] == 0.0


def test_clear_pass():
    # 10 holds, consistently positive per-hold alpha with variance, half in non-bull
    # regimes (also positive), low turnover.
    diffs = [1.5, 0.6, 1.2, 0.8, 1.0, 1.3, 0.7, 1.1, 0.9, 1.4]
    regimes = ["trend_strong", "bear", "trend_continuing", "divergence", "trend_strong",
               "bear", "trend_strong", "neutral", "trend_strong", "divergence"]
    v = tg.evaluate_trend(_holds(diffs, regimes=regimes), n_tried=1)
    assert v["verdict"] == "PASS", v["rejected_by"]
    assert v["non_bull"]["known"] and v["non_bull"]["alpha_mean"] > 0


def test_rejects_negative_alpha():
    diffs = [-0.5, 0.3, -0.8, 0.1, -0.4, -0.2, 0.2, -0.6, -0.1, -0.3]
    v = tg.evaluate_trend(_holds(diffs))
    assert v["verdict"] == "REJECTED"
    assert "compounded_alpha_positive" in v["rejected_by"]


def test_fail_closed_when_non_bull_unverifiable():
    # Strong positive alpha but ALL holds in a bull regime -> cannot verify non-bull
    diffs = [1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 0.7, 1.0, 1.1, 0.95]
    v = tg.evaluate_trend(_holds(diffs, regimes=["trend_strong"] * 10))
    assert "survives_non_bull" in v["rejected_by"]
    assert not v["non_bull"]["known"]
    assert any("non-bull" in w for w in v["warnings"])


def test_enough_holds_gate():
    v = tg.evaluate_trend(_holds([1.0, 1.0, 1.0]), min_holds=8)
    assert "enough_holds" in v["rejected_by"]


def test_bonferroni_tightens_alpha():
    diffs = [0.6, 0.4, 0.5, 0.55, 0.45, 0.5, 0.52, 0.48, 0.5, 0.5]
    v1 = tg.evaluate_trend(_holds(diffs), n_tried=1)
    v20 = tg.evaluate_trend(_holds(diffs), n_tried=20)
    assert v20["significance"]["effective_alpha"] < v1["significance"]["effective_alpha"]
