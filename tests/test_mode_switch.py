from __future__ import annotations

from pathlib import Path

import pytest

from xiaocao.strategy.mode_switch import (
    ACTIVE,
    COLD,
    PROVISIONAL,
    ModeEvidenceRow,
    annotate_candidates,
    confidence_map_from_decisions,
    decide_mode,
    fast_health_fields,
    load_live_executable_evidence,
    plan_board_lot_orders,
    select_executable_candidates,
    target_weights,
)


def _calendar(n: int = 40) -> list[str]:
    return [f"2026-06-{day:02d}" for day in range(1, n + 1)]


def _day_rows(day: str, mode_return: float, *, mode: str = "M", count: int = 2) -> list[ModeEvidenceRow]:
    rows = [
        ModeEvidenceRow(day, f"M{i}.{day}", mode, mode_return, market_return_pct=0.0)
        for i in range(count)
    ]
    rows.append(ModeEvidenceRow(day, f"BASE.{day}", "BASE", 0.0, market_return_pct=0.0))
    return rows


def test_formal_window_activates_only_on_positive_lcb() -> None:
    days = _calendar()
    positive = [row for day in days[:10] for row in _day_rows(day, 3.0)]
    negative = [row for day in days[:10] for row in _day_rows(day, -3.0, mode="BAD")]
    evidence = positive + negative

    active = decide_mode("M", days[12], evidence, days)
    cold = decide_mode("BAD", days[12], evidence, days)

    assert active.state == ACTIVE
    assert active.selected_window == 5
    assert active.windows[20].signals == 20
    assert active.windows[20].alpha_pool_lcb80 > 0
    assert cold.state == COLD
    assert cold.max_picks == 0

    confidence = confidence_map_from_decisions({"M": active, "BAD": cold})
    assert confidence["M"]["confidence"] > 50
    assert confidence["BAD"]["confidence"] < 50
    assert confidence["M"]["mode_confidence_source"] == "live executable allocation-weighted dual alpha"

    [adjusted] = annotate_candidates([{
        "code": "A.XSHE",
        "mode": "M",
        "rank_score": 100.0,
        "mode_confidence": 90.0,
    }], {"M": active})
    assert adjusted["mode_exec_rank_score"] < 100.0
    assert adjusted["mode_exec_mode_confidence"] == confidence["M"]["confidence"]


def test_previous_trading_day_outcome_cannot_leak_into_morning_decision() -> None:
    days = _calendar()
    evidence = [row for day in days[:9] for row in _day_rows(day, -2.0)]
    asof = days[11]
    base = decide_mode("M", asof, evidence, days)
    # days[10] is D-1 for asof=days[11], so its D+1 close is not known yet.
    leaked = evidence + _day_rows(days[10], 100.0)
    with_future_row = decide_mode("M", asof, leaked, days)

    assert base.state == COLD
    assert with_future_row.state == base.state
    assert with_future_row.reason == base.reason
    assert with_future_row.latest_evidence_date == days[8]


def test_fast_recent_strength_promotes_directly_to_active() -> None:
    days = _calendar()
    evidence = []
    for day, ret in zip(days[4:7], (2.0, 3.0, 4.0)):
        evidence.extend(_day_rows(day, ret, count=2))

    decision = decide_mode("M", days[8], evidence, days)

    assert decision.state == ACTIVE
    assert decision.max_picks == 1
    assert decision.selected_window == 5
    assert decision.windows[5].signals == 6
    assert decision.windows[5].alpha_pool_without_best is not None
    assert decision.windows[5].alpha_market_without_best is not None
    assert decision.windows[20].signal_days < 8


def test_formal_window_requires_robust_market_alpha_too() -> None:
    days = _calendar()
    evidence = []
    for day in days[:10]:
        evidence.extend([
            ModeEvidenceRow(day, f"M.{day}", "M", 1.0, market_return_pct=2.0),
            ModeEvidenceRow(day, f"BASE.{day}", "BASE", 0.0, market_return_pct=2.0),
        ])

    decision = decide_mode("M", days[12], evidence, days)

    assert decision.windows[20].alpha_pool_lcb80 > 0
    assert decision.windows[20].alpha_market_lcb80 is not None
    assert decision.windows[20].alpha_market_lcb80 < 0
    assert decision.state == COLD


def test_window_statistics_follow_dynamic_batch_exposure_weights() -> None:
    days = _calendar()
    evidence = []
    for day in days[:4]:
        evidence.extend(_day_rows(day, 10.0, count=1))
    for day in days[4:8]:
        evidence.extend(_day_rows(day, -8.0, count=2))

    decision = decide_mode("M", days[10], evidence, days)
    stats = decision.windows[20]

    expected = (4 * 0.25 * 10.0 + 4 * 0.45 * -8.0) / (4 * 0.25 + 4 * 0.45)
    assert stats.raw_return_mean == pytest.approx(expected)
    assert stats.weighting == "validated_25_45_50_by_mode_signal_count"
    assert stats.effective_days < stats.signal_days
    assert decision.state == COLD


def test_recent_dual_alpha_deterioration_cools_active_mode_to_one_pick() -> None:
    days = _calendar()
    evidence = []
    for day in days[:8]:
        evidence.extend(_day_rows(day, 5.0, count=2))
    for day in days[8:11]:
        evidence.extend(_day_rows(day, -4.0, count=2))

    decision = decide_mode("M", days[12], evidence, days)

    assert decision.windows[20].alpha_pool_lcb80 > 0
    assert decision.windows[20].alpha_market_lcb80 is not None
    assert decision.windows[20].alpha_market_lcb80 > 0
    assert decision.windows[5].alpha_market_mean is not None
    assert decision.windows[5].alpha_market_mean < 0
    assert decision.state == PROVISIONAL
    assert decision.selected_window == 5
    assert decision.max_picks == 1
    assert "cooling from ACTIVE" in decision.reason


def test_fast_health_warns_when_one_winner_masks_a_negative_majority() -> None:
    days = _calendar()
    evidence = []
    for day in days[:8]:
        evidence.extend(_day_rows(day, 5.0, count=2))
    evidence.extend(_day_rows(days[8], 20.0, count=2))
    for day in days[9:13]:
        evidence.extend(_day_rows(day, -2.0, count=2))

    decision = decide_mode("M", days[14], evidence, days)
    health = fast_health_fields(decision)

    assert decision.state == ACTIVE
    assert decision.windows[5].alpha_pool_mean > 0
    assert decision.windows[5].alpha_market_mean is not None
    assert decision.windows[5].alpha_market_mean > 0
    assert decision.windows[5].positive_alpha_days == 1
    assert health["mode_fast_health"] == "DETERIORATING"
    assert health["mode_fast_authority"] == "shadow_only"


def _candidate(code: str, mode: str, state: str, score: float, *, k: float = 0.0, p: float = 0.0) -> dict:
    return {
        "code": code,
        "mode": mode,
        "mode_state": state,
        "mode_trade_eligible": state in {ACTIVE, PROVISIONAL},
        "rank_score": score,
        "k_score": k,
        "p_score": p,
    }


def test_selector_excludes_cold_and_takes_one_representative_per_mode() -> None:
    candidates = [
        _candidate("COLD.XSHE", "cold", COLD, 999),
        _candidate("A1.XSHE", "active", ACTIVE, 90),
        _candidate("A2.XSHE", "active", ACTIVE, 80),
        _candidate("A3.XSHE", "active", ACTIVE, 70),
        _candidate("P1.XSHE", "probation", PROVISIONAL, 100),
        _candidate("P2.XSHE", "probation", PROVISIONAL, 95),
        _candidate("920001.BJSE", "active", ACTIVE, 1000),
    ]

    rows = select_executable_candidates(candidates, top_n=3)
    selected = [row for row in rows if row["mode_exec_star"]]

    assert "COLD.XSHE" not in {row["code"] for row in selected}
    assert "920001.BJSE" not in {row["code"] for row in selected}
    assert sum(row["mode"] == "probation" for row in selected) == 1
    assert sum(row["mode"] == "active" for row in selected) == 1


def test_active_mode_contributes_only_its_best_ranked_stock() -> None:
    rows = select_executable_candidates([
        _candidate("A1.XSHE", "active", ACTIVE, 90),
        _candidate("A2.XSHE", "active", ACTIVE, 80),
        _candidate("A3.XSHE", "active", ACTIVE, 70),
    ])
    selected = [row for row in rows if row["mode_exec_star"]]
    assert len(selected) == 1
    assert selected[0]["code"] == "A1.XSHE"
    assert selected[0]["mode_exec_target_weight"] == pytest.approx(0.50)


def test_target_weights_match_dynamic_batch_contract() -> None:
    assert target_weights([ACTIVE]) == pytest.approx([0.50])
    assert target_weights([ACTIVE, ACTIVE]) == pytest.approx([0.25, 0.25])
    assert target_weights([ACTIVE, ACTIVE, ACTIVE]) == pytest.approx([1 / 6] * 3)
    assert target_weights([PROVISIONAL]) == pytest.approx([1 / 6])
    assert target_weights([ACTIVE, PROVISIONAL]) == pytest.approx([1 / 3, 1 / 6])


def test_board_lot_planner_accepts_research_weight_resolver() -> None:
    candidates = [
        {
            "code": "000001.XSHE",
            "mode": "first",
            "mode_state": ACTIVE,
            "execution_price": 10.0,
        },
        {
            "code": "000002.XSHE",
            "mode": "second",
            "mode_state": ACTIVE,
            "execution_price": 20.0,
        },
    ]

    planned = plan_board_lot_orders(
        candidates,
        nav=100_000.0,
        cash_limit=50_000.0,
        fee_rate=0.0,
        weight_resolver=lambda rows: [0.125] * len(rows),
    )

    assert len(planned) == 2
    assert sum(row["mode_exec_planned_cash_out"] for row in planned) == pytest.approx(25_000.0)
    assert [row["mode_exec_target_weight"] for row in planned] == pytest.approx([0.125, 0.125])


def test_board_lot_planner_can_stress_test_higher_single_weight() -> None:
    planned = plan_board_lot_orders(
        [{
            "code": "000001.XSHE",
            "mode": "same",
            "mode_state": ACTIVE,
            "execution_price": 10.0,
        }],
        nav=100_000.0,
        cash_limit=50_000.0,
        fee_rate=0.0,
        weight_resolver=lambda rows: [0.50] * len(rows),
        max_single_weight=0.50,
    )

    assert len(planned) == 1
    assert planned[0]["mode_exec_planned_cash_out"] == pytest.approx(50_000.0)
    assert planned[0]["mode_exec_target_weight"] == pytest.approx(0.50)


def test_board_lot_planner_falls_through_unrepresentable_high_price_name() -> None:
    rows = [
        {**_candidate("HIGH.XSHE", "high", ACTIVE, 100), "execution_price": 1000.0},
        {**_candidate("A.XSHE", "first", ACTIVE, 90), "execution_price": 10.0},
        {**_candidate("B.XSHE", "second", ACTIVE, 80), "execution_price": 12.0},
    ]
    planned = plan_board_lot_orders(
        rows,
        nav=100000.0,
        cash_limit=50000.0,
        fee_rate=0.0001,
    )
    codes = {row["code"] for row in planned}
    assert "HIGH.XSHE" not in codes
    assert codes == {"A.XSHE", "B.XSHE"}
    assert all(int(row["mode_exec_planned_shares"]) % 100 == 0 for row in planned)


def test_board_lot_planner_scales_weights_under_kill_switch() -> None:
    rows = [
        {**_candidate("A.XSHE", "first", ACTIVE, 90), "execution_price": 16.94},
        {**_candidate("B.XSHE", "second", ACTIVE, 80), "execution_price": 37.23},
    ]
    planned = plan_board_lot_orders(
        rows,
        nav=98358.86,
        cash_limit=24589.72,
        fee_rate=0.0001,
        max_batch_ratio=0.25,
        target_scale=0.5,
    )

    assert [row["code"] for row in planned] == ["A.XSHE", "B.XSHE"]
    assert [row["mode_exec_target_weight"] for row in planned] == pytest.approx([0.125, 0.125])
    assert sum(row["mode_exec_planned_cash_out"] for row in planned) <= 24589.72


def test_board_lot_planner_notional_cap_cannot_bypass_shared_slot_rules() -> None:
    rows = [
        {**_candidate(f"A{i}.XSHE", "active", ACTIVE, 100 - i), "execution_price": 10.0}
        for i in range(5)
    ]
    planned = plan_board_lot_orders(
        rows,
        nav=100000.0,
        cash_limit=50000.0,
        fee_rate=0.0001,
        per_position_cash_cap=12000.0,
    )

    assert len(planned) == 1
    assert all(float(row["mode_exec_planned_cash_out"]) <= 12000.0 for row in planned)


def test_loader_refuses_theoretical_return_as_gate_evidence(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    path = tmp_path / "training.parquet"
    pd.DataFrame([{
        "date": "2026-06-01",
        "code": "A.XSHE",
        "mode": "M",
        "is_live": True,
        "net_realized_ret": 10.0,
    }]).to_parquet(path, index=False)
    assert load_live_executable_evidence(path) == []

    pd.DataFrame([{
        "date": "2026-06-01",
        "code": "A.XSHE",
        "mode": "M",
        "is_live": True,
        "book": "B",
        "executable_fillable": True,
        "executable_net_ret": 3.0,
    }]).to_parquet(path, index=False)
    rows = load_live_executable_evidence(path)
    assert len(rows) == 1
    assert rows[0].net_return_pct == 3.0
