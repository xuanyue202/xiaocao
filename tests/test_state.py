from __future__ import annotations

import json
import sqlite3

import pytest

from xiaocao.strategy.state import (
    NEUTRAL_STATE,
    StateVector,
    _compute_continuity,
    _compute_duan_ban_recovery,
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
