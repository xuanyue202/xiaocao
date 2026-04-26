from __future__ import annotations

import pytest

from xiaocao.strategy.regime import (
    MODE_REGIME_FIT,
    REGIME_LABELS,
    classify_regime,
    limit_down_count,
    limit_up_count,
    mode_allowed_in,
    negative_total,
    positive_total,
)


def _ov(positive: list[int], negative: list[int], level_zero: int = 100) -> dict:
    """Build a market_overview-shaped dict from level lists [L1..L7]."""
    out = {"levelZero": level_zero}
    for i, v in enumerate(positive, start=1):
        out[f"positiveLevel{['One','Two','Three','Four','Five','Six','Seven'][i-1]}"] = v
    for i, v in enumerate(negative, start=1):
        out[f"negativeLevel{['One','Two','Three','Four','Five','Six','Seven'][i-1]}"] = v
    return out


def test_total_helpers():
    ov = _ov([1, 2, 3, 4, 5, 6, 7], [10, 20, 30, 40, 50, 60, 70])
    assert positive_total(ov) == 28
    assert negative_total(ov) == 280
    assert limit_up_count(ov) == 7
    assert limit_down_count(ov) == 70


def test_explicit_limit_up_keys_take_priority():
    ov = _ov([0, 0, 0, 0, 0, 0, 5], [0, 0, 0, 0, 0, 0, 5])
    ov["limitUpCount"] = 99
    ov["limitDownCount"] = 88
    assert limit_up_count(ov) == 99
    assert limit_down_count(ov) == 88


def test_classify_bear_on_high_limit_down():
    ov = _ov([100] * 7, [200] * 7)  # neg/pos = 2:1; not bear yet
    ov["negativeLevelSeven"] = 60  # limit-down ≥ 50 → bear
    assert classify_regime(ov) == "bear"


def test_classify_bear_on_lopsided_negative():
    # neg / pos ≥ 3 → bear, regardless of limit-down count
    ov = _ov([100, 0, 0, 0, 0, 0, 0], [400, 0, 0, 0, 0, 0, 0])
    assert classify_regime(ov) == "bear"


def test_classify_divergence_on_big_cap_open_drop():
    ov = _ov([1000, 0, 0, 0, 0, 0, 0], [800, 0, 0, 0, 0, 0, 0])
    assert classify_regime(ov, big_cap_avg_open_pct=-3.0) == "divergence"


def test_classify_trend_strong_with_limit_ups():
    ov = _ov([2000, 500, 200, 100, 50, 10, 35], [800, 100, 50, 0, 0, 0, 0])
    assert classify_regime(ov, big_cap_avg_open_pct=0.5) == "trend_strong"


def test_classify_trend_continuing_when_big_cap_holds():
    ov = _ov([1500, 100, 50, 20, 10, 0, 5], [1000, 200, 50, 0, 0, 0, 0])
    assert classify_regime(ov, big_cap_avg_open_pct=-0.3) == "trend_continuing"


def test_classify_recovery_when_big_caps_weak_but_pos_majority():
    ov = _ov([1500, 100, 50, 20, 10, 0, 5], [1000, 200, 50, 0, 0, 0, 0])
    assert classify_regime(ov, big_cap_avg_open_pct=-1.5) == "recovery"


def test_classify_divergence_negative_majority_not_bear():
    ov = _ov([800, 0, 0, 0, 0, 0, 0], [1500, 0, 0, 0, 0, 0, 0])  # 1.875x not 3x
    assert classify_regime(ov) == "divergence"


def test_classify_neutral_on_empty_overview():
    assert classify_regime(None) == "neutral"
    assert classify_regime({}) == "neutral"


@pytest.mark.parametrize("regime", REGIME_LABELS)
def test_mode_allowed_in_returns_bool(regime: str):
    assert isinstance(mode_allowed_in("接力低弱转1", regime), bool)


def test_接力低弱转2_blocked_by_risk_precondition_in_risk_off_regimes():
    # 接力低弱转2 has a precondition (state.risk >= 0.45) — in bear and
    # divergence prototype regimes (risk = 0.20 / 0.35) the precondition fails,
    # which yields PRECONDITION_FAIL → integer fitness -2 → legacy gate blocks.
    for r in ("bear", "divergence"):
        assert not mode_allowed_in("接力低弱转2", r), f"unexpected allow in {r}"
    # In risk-on regimes the precondition passes and the mode is allowed.
    for r in ("recovery", "trend_continuing", "trend_strong"):
        assert mode_allowed_in("接力低弱转2", r), f"unexpected block in {r}"


def test_unknown_mode_blocked_only_in_bear():
    assert not mode_allowed_in("某新模式", "bear")
    for r in ("divergence", "neutral", "recovery", "trend_continuing", "trend_strong"):
        assert mode_allowed_in("某新模式", r)


# --- Continuous fitness framework tests -------------------------------------

def test_align_at_target_returns_one():
    from xiaocao.strategy.regime import align
    assert align("high", 0.7) == pytest.approx(1.0)
    assert align("mid", 0.5) == pytest.approx(1.0)
    assert align("low", 0.25) == pytest.approx(1.0)
    assert align("very_high", 0.85) == pytest.approx(1.0)


def test_align_any_returns_zero():
    from xiaocao.strategy.regime import align
    for obs in (0.0, 0.3, 0.5, 0.7, 1.0):
        assert align("any", obs) == 0.0


def test_align_far_from_target_clamped_negative():
    from xiaocao.strategy.regime import align
    # very_high (target 0.85) vs observed 0 → 1 - 2.5*0.85 = -1.125 → clamped to -1
    assert align("very_high", 0.0) == pytest.approx(-1.0)


def test_mode_fitness_strong_match_positive():
    from xiaocao.strategy.regime import mode_fitness
    from xiaocao.strategy.state import StateVector
    # 红盘起爆主攻 wants reward=high, risk=high, continuity=mid
    perfect = StateVector(reward=0.7, risk=0.7, continuity=0.5,
                          duan_ban_recovery=0.5)
    f = mode_fitness("红盘起爆主攻", perfect)
    assert f >= 0.9, f"expected near-perfect fit, got {f}"


def test_mode_fitness_strong_mismatch_negative():
    from xiaocao.strategy.regime import mode_fitness
    from xiaocao.strategy.state import StateVector
    # 红盘起爆主攻 wants reward=high(0.7), risk=high(0.7), continuity=mid(0.5).
    # All 3 axes far off:
    bad = StateVector(reward=0.05, risk=0.05, continuity=0.05,
                      duan_ban_recovery=0.5)
    f = mode_fitness("红盘起爆主攻", bad)
    assert f <= -0.3, f"expected strong mismatch, got {f}"


def test_mode_fitness_precondition_failure_returns_sentinel():
    from xiaocao.strategy.regime import mode_fitness, PRECONDITION_FAIL
    from xiaocao.strategy.state import StateVector
    # 首红断低吸 needs duan_ban_recovery >= 0.45
    state = StateVector(reward=0.5, risk=0.5, continuity=0.5, duan_ban_recovery=0.30)
    assert mode_fitness("首红断低吸", state) == PRECONDITION_FAIL


def test_mode_fitness_unknown_mode_neutral():
    from xiaocao.strategy.regime import mode_fitness
    from xiaocao.strategy.state import StateVector
    state = StateVector(reward=0.7, risk=0.7, continuity=0.7, duan_ban_recovery=0.5)
    assert mode_fitness("nonexistent_mode", state) == 0.0


def test_mode_fitness_smooth_around_target():
    """Small perturbation in state should give small change in fitness.

    Use a mode WITHOUT preconditions (N字低吸 has none) to test pure
    alignment smoothness.
    """
    from xiaocao.strategy.regime import mode_fitness
    from xiaocao.strategy.state import StateVector
    s1 = StateVector(reward=0.50, risk=0.50, continuity=0.70, duan_ban_recovery=0.5)
    s2 = StateVector(reward=0.52, risk=0.50, continuity=0.70, duan_ban_recovery=0.5)
    # N字低吸 wants mid/mid/high — no precondition
    f1 = mode_fitness("N字低吸", s1)
    f2 = mode_fitness("N字低吸", s2)
    assert abs(f1 - f2) < 0.05, "small input change → big output change (jumpy)"
