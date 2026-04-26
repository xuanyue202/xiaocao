from __future__ import annotations

import json
import sqlite3

import pytest

from xiaocao.strategy.state import (
    NEUTRAL_STATE,
    StateVector,
    _compute_continuity,
    _compute_duan_ban_recovery,
    _compute_limitup_density,
    _compute_momentum,
    _compute_reward_density,
    _compute_risk_polarity,
    build_state_index,
    get_state,
)


def test_reward_density_counts_motion_stocks() -> None:
    # 4 / 10 stocks have |pct| >= 2.0
    pcts = [3.0, -2.5, 0.5, 1.0, -0.5, 0.0, -1.5, 5.0, 0.2, -2.1]
    assert _compute_reward_density(pcts) == pytest.approx(0.4)


def test_reward_density_empty_neutral() -> None:
    assert _compute_reward_density([]) == 0.5


def test_risk_polarity_counts_positive() -> None:
    pcts = [1.0, 2.0, -3.0, 0.5, -1.0]
    assert _compute_risk_polarity(pcts) == pytest.approx(0.6)  # 3/5


def test_continuity_overlap_normalized() -> None:
    today = ["A", "B", "C", "D", "E"]
    yesterday = ["A", "B", "X", "Y", "Z"]
    score, overlap = _compute_continuity(today, yesterday)
    assert overlap == 2
    assert score == pytest.approx(0.4)


def test_continuity_no_yesterday_neutral() -> None:
    score, overlap = _compute_continuity(["A", "B"], [])
    assert score == 0.5 and overlap == 0


def test_duan_ban_recovery_maps_median_to_unit() -> None:
    # 3 stocks were "近涨停 but 断板" yesterday (8 ≤ pct < 9.5)
    yesterday = {"A": 8.5, "B": 9.0, "C": 8.2, "D": 5.0, "E": 9.7}
    # Today: A flat, B +5%, C -3% — median = 0.0 → recovery = 0.5
    today = {"A": 0.0, "B": 5.0, "C": -3.0, "D": 1.0, "E": -2.0}
    rec, n = _compute_duan_ban_recovery(today, yesterday)
    assert n == 3
    assert rec == pytest.approx(0.5)


def test_duan_ban_recovery_strong_bounce() -> None:
    yesterday = {"A": 8.5, "B": 9.0, "C": 8.2}
    today = {"A": 5.0, "B": 5.0, "C": 5.0}  # all +5 → median +5 → (5+10)/20 = 0.75
    rec, _ = _compute_duan_ban_recovery(today, yesterday)
    assert rec == pytest.approx(0.75)


def test_duan_ban_recovery_no_candidates_neutral() -> None:
    yesterday = {"A": 1.0, "B": 2.0}
    today = {"A": -1.0, "B": -1.0}
    rec, n = _compute_duan_ban_recovery(today, yesterday)
    assert n == 0 and rec == 0.5


def test_momentum_neutral_when_empty() -> None:
    mom, n = _compute_momentum([])
    assert mom == 0.5 and n == 0


def test_momentum_positive_week_saturates_high() -> None:
    # 5 days of +3% mean each → cumulative +15 → clamped to +1 → momentum = 1.0
    mom, n = _compute_momentum([3.0, 3.0, 3.0, 3.0, 3.0])
    assert n == 5 and mom == pytest.approx(1.0)


def test_momentum_negative_week_saturates_low() -> None:
    mom, n = _compute_momentum([-3.0, -3.0, -3.0, -3.0, -3.0])
    assert n == 5 and mom == pytest.approx(0.0)


def test_momentum_balanced_returns_neutral() -> None:
    # Sum 0 → momentum 0.5
    mom, _ = _compute_momentum([1.5, -1.5, 0.8, -0.8, 0.0])
    assert mom == pytest.approx(0.5)


def test_momentum_partial_window() -> None:
    # 3 days of +1% each → +3 / 10 = 0.3 → (0.3+1)/2 = 0.65
    mom, n = _compute_momentum([1.0, 1.0, 1.0])
    assert n == 3 and mom == pytest.approx(0.65)


def test_momentum_in_built_state_index_window(tmp_path) -> None:
    """Verify build_state_index threads daily mean pct → momentum across dates."""
    cache_path = tmp_path / "c.db"
    rows = []
    # 6 dates, 30 stocks each, all +2% → cumulative +12 → clamped → momentum 1.0 by day 5
    for d_offset in range(6):
        date = f"2026-04-{20+d_offset:02d}"
        for i in range(30):
            rows.append({"code": f"C{i:03d}", "tradeDate": date, "pctChangeRate": 2.0})
    _seed_kline_cache(cache_path, rows)

    class FakeCache:
        path = str(cache_path)

    idx = build_state_index(FakeCache())
    # Day 5 (last) should have cumulative 5d × 2% = 10 → clamped → 1.0
    last_state = idx["2026-04-25"]
    assert last_state.momentum == pytest.approx(1.0)
    assert last_state.n_momentum == 5
    # Day 1 has only 1 sample in window → +2% / 10 = 0.2 → (0.2+1)/2 = 0.6
    first_state = idx["2026-04-20"]
    assert first_state.n_momentum == 1
    assert first_state.momentum == pytest.approx(0.6)


def _seed_kline_cache(cache_path, rows: list[dict]) -> None:
    """Write fake date_kline cache entries. Each call appends one row group."""
    with sqlite3.connect(str(cache_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_cache (
                endpoint TEXT NOT NULL,
                params_hash TEXT NOT NULL,
                params_json TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                historical INTEGER NOT NULL,
                response_json TEXT NOT NULL,
                PRIMARY KEY (endpoint, params_hash)
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO api_cache VALUES (?, ?, ?, ?, ?, ?)",
            (
                "/stock/date_kline",
                str(hash(json.dumps(rows, sort_keys=True))),
                "{}",
                0, 1,
                json.dumps(rows),
            ),
        )
        conn.commit()


def test_build_state_index_skips_dates_with_few_samples(tmp_path) -> None:
    """Dates with < 30 stock samples are skipped from the index."""
    cache_path = tmp_path / "c.db"
    # Only 3 samples for 2026-04-23 — should be skipped
    rows = [
        {"code": f"C{i}", "tradeDate": "2026-04-23", "pctChangeRate": 1.0}
        for i in range(3)
    ]
    _seed_kline_cache(cache_path, rows)

    class FakeCache:
        path = str(cache_path)

    idx = build_state_index(FakeCache())
    assert "2026-04-23" not in idx


def test_build_state_index_includes_dates_with_enough_samples(tmp_path) -> None:
    cache_path = tmp_path / "c.db"
    # 35 samples — passes the n>=30 threshold
    rows = [
        {"code": f"C{i:03d}", "tradeDate": "2026-04-23",
         "pctChangeRate": 3.0 if i % 2 == 0 else -1.0}
        for i in range(35)
    ]
    _seed_kline_cache(cache_path, rows)

    class FakeCache:
        path = str(cache_path)

    idx = build_state_index(FakeCache())
    assert "2026-04-23" in idx
    state = idx["2026-04-23"]
    # 18 even-index → +3% (>=2); 17 odd → -1% (<2): reward = 18/35
    assert state.reward == pytest.approx(18 / 35)
    # 18 positive: risk = 18/35
    assert state.risk == pytest.approx(18 / 35)


def test_get_state_returns_neutral_for_missing_date() -> None:
    s = get_state("2026-04-99", state_index={})
    assert s == NEUTRAL_STATE
    assert s.reward == 0.5 and s.risk == 0.5


def test_state_vector_is_immutable() -> None:
    s = StateVector(reward=0.7, risk=0.6, continuity=0.5, duan_ban_recovery=0.5)
    with pytest.raises(Exception):
        s.reward = 0.9  # frozen dataclass


def test_state_vector_default_momentum_neutral() -> None:
    """StateVector without explicit momentum defaults to 0.5 (back-compat)."""
    s = StateVector(reward=0.5, risk=0.5, continuity=0.5, duan_ban_recovery=0.5)
    assert s.momentum == 0.5
    assert s.n_momentum == 0
    assert s.limitup_density == 0.0  # 0 means "no signal", different from neutral 0.5


def test_limitup_density_empty_returns_zero() -> None:
    assert _compute_limitup_density([]) == 0.0


def test_limitup_density_no_limitup_zero() -> None:
    pcts = [3.0, -2.0, 5.0, 0.0, 8.0]  # max 8 < 9.5
    assert _compute_limitup_density(pcts) == 0.0


def test_limitup_density_saturates_at_5pct() -> None:
    # 5 / 100 = 5% → exactly saturates to 1.0
    pcts = [9.6] * 5 + [0.0] * 95
    assert _compute_limitup_density(pcts) == pytest.approx(1.0)


def test_limitup_density_above_saturation_clamped() -> None:
    # 10 / 100 = 10% → clamped to 1.0
    pcts = [9.6] * 10 + [0.0] * 90
    assert _compute_limitup_density(pcts) == pytest.approx(1.0)


def test_limitup_density_partial() -> None:
    # 1 / 100 = 1% → 1% / 5% = 0.2
    pcts = [9.6] + [0.0] * 99
    assert _compute_limitup_density(pcts) == pytest.approx(0.2)


def test_limitup_density_in_state_index(tmp_path) -> None:
    """build_state_index populates limitup_density per day."""
    cache_path = tmp_path / "c.db"
    rows = []
    # 30 stocks: first 3 have pct 10% (涨停, 10%>=9.5), rest 0% → 3/30=10% → clamped to 1.0
    for i in range(30):
        rows.append({
            "code": f"C{i:03d}", "tradeDate": "2026-04-23",
            "pctChangeRate": 10.0 if i < 3 else 0.0,
        })
    _seed_kline_cache(cache_path, rows)

    class FakeCache:
        path = str(cache_path)

    idx = build_state_index(FakeCache())
    assert idx["2026-04-23"].limitup_density == pytest.approx(1.0)
