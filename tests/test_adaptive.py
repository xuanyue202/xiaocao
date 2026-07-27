from __future__ import annotations

from xiaocao.api.cache import SQLiteCache
from xiaocao.strategy.adaptive import (
    AUXILIARY_MODE_AUTHORITY,
    DEFAULT_AVG_THRESHOLD_BY_WINDOW,
    adaptive_mode_filter,  # back-compat alias
    decide_mode_state,
    regime_modulated_thresholds,
    tag_signals,
)


def test_regime_modulated_thresholds_default_zero_returns_base():
    out = regime_modulated_thresholds(None, fitness=0)
    assert out == DEFAULT_AVG_THRESHOLD_BY_WINDOW


def test_regime_modulated_thresholds_positive_fitness_has_no_authority():
    out = regime_modulated_thresholds(None, fitness=+1.0)
    assert out == DEFAULT_AVG_THRESHOLD_BY_WINDOW


def test_regime_modulated_thresholds_negative_fitness_has_no_authority():
    out = regime_modulated_thresholds(None, fitness=-1.0)
    assert out == DEFAULT_AVG_THRESHOLD_BY_WINDOW


def test_regime_modulated_thresholds_precondition_fail_has_no_authority():
    from xiaocao.strategy.regime import PRECONDITION_FAIL
    out = regime_modulated_thresholds(None, fitness=PRECONDITION_FAIL)
    assert out == DEFAULT_AVG_THRESHOLD_BY_WINDOW


def test_decide_mode_state_positive_fitness_cannot_reenable_bad_mode(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # 5d avg = -5.5% × 6 trades. Default 5d thr=-5 → trips shadow at fitness=0.
    cache.record_trades([
        {"mode": "M", "buyDate": d, "code": f"C{i}", "returnPct": -5.5}
        for i, d in enumerate([
            "2026-04-16", "2026-04-17", "2026-04-18",
            "2026-04-21", "2026-04-22", "2026-04-23",
        ])
    ])
    base = decide_mode_state("M", "2026-04-25", cache, regime_fitness=0)
    with_aux = decide_mode_state("M", "2026-04-25", cache, regime_fitness=+1.0)
    assert base.active is False, base.reason
    assert with_aux.active is False, with_aux.reason
    assert with_aux.reason == base.reason


def _seed(cache: SQLiteCache, mode: str, dates_returns: list[tuple[str, float]]) -> None:
    rows = [
        {"mode": mode, "buyDate": d, "code": f"C{i:03d}", "returnPct": r}
        for i, (d, r) in enumerate(dates_returns)
    ]
    cache.record_trades(rows)


def test_decide_no_cache_keeps_mode_enabled():
    d = decide_mode_state("X", "2026-04-25", cache=None)
    assert d.enabled is True


def test_decide_zero_history_marks_shadow(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    d = decide_mode_state("X", "2026-04-25", cache)
    # Tier 4: 20 trading days no evidence → SHADOW (active=False)
    assert d.active is False
    assert "Tier4" in d.reason


def test_decide_a_rule_double_window_disable(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # Trades strong enough to clear both 5d (≤-5%) and 10d (≤-3%) thresholds.
    _seed(cache, "M", [
        ("2026-04-16", -6.0),
        ("2026-04-17", -7.0),
        ("2026-04-18", -5.0),
        ("2026-04-21", -8.0),
        ("2026-04-22", -6.0),
        ("2026-04-23", -7.0),
    ])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.active is False
    assert "Tier1" in d.reason
    assert "双窗口确认" in d.reason


def test_decide_a_rule_one_window_positive_keeps_enabled(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # 5-day window has avg > 0; 10-day has avg < 0 — A rule requires BOTH bad.
    _seed(cache, "M", [
        ("2026-04-15", -5.0),  # in 10d only
        ("2026-04-16", -5.0),  # in 10d only
        ("2026-04-17", -5.0),  # in 10d only (>= 8 days back)
        ("2026-04-22", +3.0),  # in both 5d and 10d
        ("2026-04-23", +3.0),
        ("2026-04-24", +2.0),
    ])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.enabled is True


def test_decide_sparse_10d_only_disables_when_below_threshold(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # Seeds 8-10 calendar days back: 5d window empty, 10d has them.
    # Strong enough negatives to clear 10d threshold (≤-3%).
    _seed(cache, "M", [
        ("2026-04-15", -5.0),
        ("2026-04-16", -4.0),
        ("2026-04-17", -6.0),
    ])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.active is False
    # 10d alone — Tier 2 single-window (or Tier 3 fallback)
    assert "Tier2" in d.reason or "Tier3" in d.reason


def test_decide_20d_fallback(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # Trades are 13-15 days old — 5d and 10d both empty, 20d has them.
    _seed(cache, "M", [
        ("2026-04-10", -3.0),
        ("2026-04-11", -2.0),
        ("2026-04-12", -2.0),
    ])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.enabled is False
    assert "Tier3" in d.reason


def test_decide_20d_fallback_positive_keeps_enabled(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    _seed(cache, "M", [
        ("2026-04-10", +5.0),
        ("2026-04-11", +3.0),
        ("2026-04-12", +2.0),
    ])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.enabled is True


def test_decide_no_recent_history_marks_shadow_via_tier4(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # All trades > 20 calendar days back → all windows uninformative → Tier 4
    _seed(cache, "M", [
        ("2026-03-01", -10.0),
        ("2026-03-02", -10.0),
    ])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.active is False
    assert "Tier4" in d.reason


def test_decide_single_recent_trade_with_strong_negative_disables(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # Single trade in last 5 days, strongly negative (≤-5%) → Tier 2 5d disable
    _seed(cache, "M", [("2026-04-23", -8.0)])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.active is False
    assert "Tier2" in d.reason
    assert "5d" in d.reason


def test_decide_single_recent_trade_with_mild_negative_keeps_active(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # Single -3% trade in 5d: avg -3% > thr5 (-5%) → enabled
    _seed(cache, "M", [("2026-04-23", -3.0)])
    d = decide_mode_state("M", "2026-04-25", cache)
    assert d.active is True
    assert "Tier2" in d.reason
    assert "正向" in d.reason


def test_record_trades_round_trip(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    cache.record_trades([
        {"mode": "M", "buyDate": "2026-04-20", "code": "X", "returnPct": 1.5},
        {"mode": "M", "buyDate": "2026-04-21", "code": "Y", "returnPct": -2.5},
    ])
    s = cache.mode_window_stats("M", "2026-04-25", 5)
    assert s["n"] == 2
    assert abs(s["avg"] - (-0.5)) < 1e-9


def test_record_trades_skips_invalid_rows(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    cache.record_trades([
        {"mode": "M", "buyDate": "2026-04-20", "code": "X", "returnPct": 1.0},
        {"mode": None, "buyDate": "2026-04-21", "code": "Y", "returnPct": 2.0},  # skip
        {"mode": "M", "buyDate": None, "code": "Z", "returnPct": 3.0},  # skip
    ])
    s = cache.mode_window_stats("M", "2026-04-25", 5)
    assert s["n"] == 1


def test_tag_signals_preserves_all_rows_with_active_flag(tmp_path):
    cache = SQLiteCache(tmp_path / "c.db")
    # Bad: strong negatives crossing both 5d (-5%) and 10d (-3%) thresholds
    _seed(cache, "Bad", [
        ("2026-04-16", -7.0),
        ("2026-04-17", -8.0),
        ("2026-04-18", -6.0),
        ("2026-04-22", -7.0),
        ("2026-04-23", -8.0),
        ("2026-04-24", -6.0),
    ])
    _seed(cache, "Good", [
        ("2026-04-22", +2.0),
        ("2026-04-23", +3.0),
        ("2026-04-24", +1.0),
    ])
    rows = [
        {"mode": "Bad", "code": "A"},
        {"mode": "Good", "code": "B"},
    ]
    tagged, decisions = tag_signals(rows, "2026-04-25", cache)
    # All rows preserved (no drops) — they're tagged, not filtered
    assert [r["code"] for r in tagged] == ["A", "B"]
    by_code = {r["code"]: r for r in tagged}
    assert by_code["A"]["adaptive_active"] is False  # bad mode → shadow
    assert by_code["B"]["adaptive_active"] is True   # good mode → active
    assert "adaptive_reason" in by_code["A"]
    assert by_code["A"]["adaptive_auxiliary_authority"] == AUXILIARY_MODE_AUTHORITY
    assert by_code["B"]["adaptive_regime_fitness"] == 0.0
    assert decisions["Bad"].active is False
    assert decisions["Good"].active is True


def test_tag_signals_records_precondition_failure_without_shadow_authority(tmp_path):
    from xiaocao.strategy.state import StateVector

    cache = SQLiteCache(tmp_path / "c.db")
    _seed(cache, "绿断低吸", [("2026-04-23", +2.0)])
    state = StateVector(
        reward=0.5,
        risk=0.5,
        continuity=0.5,
        duan_ban_recovery=0.1,
    )
    tagged, decisions = tag_signals(
        [{"mode": "绿断低吸", "code": "A"}],
        "2026-04-25",
        cache,
        state=state,
    )

    assert decisions["绿断低吸"].active is True
    assert tagged[0]["adaptive_active"] is True
    assert tagged[0]["adaptive_regime_fitness"] == "PRECONDITION_FAIL"
    assert tagged[0]["adaptive_auxiliary_authority"] == AUXILIARY_MODE_AUTHORITY


def test_adaptive_mode_filter_alias_still_works(tmp_path):
    """Back-compat: old name should be a synonym for tag_signals."""
    cache = SQLiteCache(tmp_path / "c.db")
    rows = [{"mode": "X", "code": "A"}]
    tagged, _ = adaptive_mode_filter(rows, "2026-04-25", cache)
    assert tagged[0]["code"] == "A"
    assert "adaptive_active" in tagged[0]
