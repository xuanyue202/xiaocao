from __future__ import annotations

from datetime import datetime

import scripts.live_recommend as live_recommend
from scripts.live_recommend import (
    _annotate_recommendation_score,
    _basket_params,
    _basket_price,
    _entry_price,
    _open_fit,
    _open_risk_penalty,
    _open_pct_from_entry,
    _price_limit_pct,
    _profile_stop,
    _rank_candidates,
    _run_strategy_when_ready,
    _scale_exec_cap_pct,
    _seconds_until_recommendation_start,
    _select_candidates,
    _select_standby_candidates,
)
from xiaocao.utils.trading_session import A_SHARE_TZ


def _dt(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 4, 30, hour, minute, second, tzinfo=A_SHARE_TZ)


class _FakeClient:
    def second_line_detail_info(self, codes: str):
        return {
            codes: {
                "code": codes,
                "tradeDate": "20260430",
                "open": 145.0,
                "preClose": 152.3,
            }
        }

    def date_kline(self, code: str, count: int = 10, freq: str = "D", adj: str = "qfq"):
        return []

    def stock_call_auction(self, code: str, date_iso: str):
        return [
            {
                "code": code,
                "tradeTimestamp": "092459",
                "trade": 143.0,
                "preClose": 152.3,
            }
        ]


def test_waits_until_auction_close_for_today_between_920_and_925() -> None:
    assert _seconds_until_recommendation_start("2026-04-30", _dt(9, 20)) == 301.0
    assert _seconds_until_recommendation_start("2026-04-30", _dt(9, 24, 59)) == 2.0
    assert _seconds_until_recommendation_start("2026-04-30", _dt(9, 25)) == 1.0


def test_does_not_wait_outside_today_auction_window() -> None:
    assert _seconds_until_recommendation_start("2026-04-30", _dt(9, 19, 59)) == 0.0
    assert _seconds_until_recommendation_start("2026-04-30", _dt(9, 25, 1)) == 0.0
    assert _seconds_until_recommendation_start("2026-04-29", _dt(9, 20)) == 0.0


def test_entry_price_prefers_final_realtime_open_over_indicative_auction(monkeypatch) -> None:
    monkeypatch.setattr("scripts.live_recommend._today_iso", lambda: "2026-04-30")

    price, source, pre_close = _entry_price(_FakeClient(), "688507.XSHG", "2026-04-30")

    assert price == 145.0
    assert source == "realtime_open"
    assert pre_close == 152.3


def test_open_pct_is_derived_from_final_entry_price() -> None:
    assert round(_open_pct_from_entry(145.0, 152.3, -6.11), 2) == -4.79


def test_open_fit_prefers_controlled_low_open_for_rebound_modes() -> None:
    assert _open_fit("绿断低吸", -3.0) > _open_fit("绿断低吸", -8.8)
    assert _open_fit("绿断低吸", -3.0) > _open_fit("绿断低吸", 3.0)


def test_rank_candidates_uses_alpha_score_with_open_as_risk_penalty() -> None:
    candidates = [
        {"code": "A", "mode": "首红断低吸", "xcjw": 170, "cjs": 8, "open_pct_change": 4.5},
        {"code": "B", "mode": "绿断低吸", "xcjw": 250, "cjs": 80, "open_pct_change": -3.0},
        {"code": "C", "mode": "N字低吸", "xcjw": 280, "cjs": 20, "open_pct_change": -8.9},
    ]

    ranked = _rank_candidates(candidates)

    assert [row["code"] for row in ranked] == ["B", "C", "A"]
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]
    assert ranked[2]["open_risk_penalty"] > 0


def test_open_risk_penalty_catches_extreme_execution_shapes() -> None:
    assert _open_risk_penalty("绿断低吸", -3.0) == 0.0
    assert _open_risk_penalty("绿断低吸", -8.5) > 0.0
    assert _open_risk_penalty("接力低弱转1", 2.0) == 0.0
    assert _open_risk_penalty("接力低弱转1", 6.0) > 0.0


def test_recommendation_score_uses_mode_confidence() -> None:
    candidate = {"code": "A", "mode": "绿断低吸", "xcjw": 250, "cjs": 80, "open_pct_change": -3.0}

    low = _annotate_recommendation_score(candidate, {"绿断低吸": {"confidence": 20}})
    neutral = _annotate_recommendation_score(candidate, {})
    high = _annotate_recommendation_score(candidate, {"绿断低吸": {"confidence": 80}})

    assert low["rank_score"] < neutral["rank_score"] < high["rank_score"]


def test_raw_qibao_benchmark_uses_rank_score_as_primary() -> None:
    candidate = {
        "code": "A",
        "mode": "标杆短线起爆",
        "jssb": 4.0,
        "qibaoRankScore": 228.0,
        "open_pct_change": 2.0,
    }

    annotated = _annotate_recommendation_score(candidate, {})

    assert annotated["primary_score"] == 228.0
    assert annotated["primary_score_label"] == "qibaoRankScore"


def test_promoted_qibao_benchmark_modes_use_rank_score_as_primary() -> None:
    for mode in ("高开标杆起爆", "强攻标杆起爆"):
        annotated = _annotate_recommendation_score({
            "code": "A",
            "mode": mode,
            "jssb": 4.0,
            "qibaoRankScore": 216.0,
            "open_pct_change": 8.0,
        }, {})

        assert annotated["primary_score"] == 216.0
        assert annotated["primary_score_label"] == "qibaoRankScore"


def test_basket_params_are_mode_specific_and_confidence_adjusted() -> None:
    low_premium, low_cap, low_exec_cap = _basket_params("绿断低吸", confidence=60)
    momentum_premium, momentum_cap, momentum_exec_cap = _basket_params("接力低弱转1", confidence=60)

    assert low_premium == 2.0
    assert low_premium <= momentum_premium
    assert low_cap == 2.0
    assert low_exec_cap == 2.0
    assert momentum_cap == 10.0
    assert momentum_exec_cap == 6.0

    raw_premium, raw_cap, raw_exec_cap = _basket_params("标杆短线起爆", confidence=60)
    assert raw_premium == 1.68
    assert raw_cap == 6.0
    assert raw_exec_cap == 4.5

    high_premium, high_cap, high_exec_cap = _basket_params("高开标杆起爆", confidence=60)
    assert high_premium == 1.48
    assert high_cap == 10.0
    assert high_exec_cap == 8.0

    strong_premium, strong_cap, strong_exec_cap = _basket_params("强攻标杆起爆", confidence=60)
    assert strong_premium == 1.28
    assert strong_cap == 20.0
    assert strong_exec_cap == 18.0


def test_first_red_break_basket_allows_two_percent_price_priority_on_flat_open() -> None:
    premium, cap, exec_cap = _basket_params("首红断低吸", confidence=67.6)
    price, rule = _basket_price(
        entry_price=5.78,
        pre_close=5.78,
        premium_pct=premium,
        cap_pct=cap,
        exec_cap_pct=exec_cap,
    )

    assert premium == 2.0
    assert round(price, 2) == 5.90
    assert rule == "entry+2.0%"


def test_breakout_absorb_basket_does_not_chase_above_preclose_cap() -> None:
    premium, cap, exec_cap = _basket_params("红断低吸", confidence=80)
    price, rule = _basket_price(
        entry_price=10.15,
        pre_close=10.00,
        premium_pct=premium,
        cap_pct=cap,
        exec_cap_pct=exec_cap,
    )

    assert premium == 2.0
    assert price == 10.2
    assert rule == "cap preClose+2.0%"


def test_momentum_basket_uses_two_percent_fill_room_until_execution_cap() -> None:
    premium, cap, exec_cap = _basket_params("接力低弱转1", confidence=90)
    price, rule = _basket_price(
        entry_price=3.65,
        pre_close=3.49,
        premium_pct=premium,
        cap_pct=cap,
        exec_cap_pct=exec_cap,
    )

    assert premium >= 2.0
    assert round(price / 3.49 - 1.0, 4) <= 0.06
    assert rule == "exec cap preClose+6.0%"


def test_execution_cap_scales_by_price_limit_regime() -> None:
    assert _price_limit_pct("600303.XSHG", "曙光股份") == 10.0
    assert _price_limit_pct("300750.XSHE", "宁德时代") == 20.0
    assert _price_limit_pct("688507.XSHG", "索辰科技") == 20.0
    assert _price_limit_pct("920001.BJSE", "北交样例") == 30.0
    assert _price_limit_pct("600000.XSHG", "ST样例") == 5.0

    assert _scale_exec_cap_pct(6.0, 10.0) == 6.0
    assert _scale_exec_cap_pct(6.0, 20.0) == 8.0
    assert _scale_exec_cap_pct(6.0, 30.0) == 10.0
    assert _scale_exec_cap_pct(6.0, 50.0) == 12.0


def test_ready_wait_continues_after_first_nonempty_until_stable(monkeypatch) -> None:
    snapshots = [
        [],
        [{"code": "A.XSHE", "mode": "接力低弱转1", "adaptive_active": None}],
        [
            {"code": "A.XSHE", "mode": "接力低弱转1", "adaptive_active": None},
            {"code": "B.XSHE", "mode": "首红断低吸", "adaptive_active": None},
        ],
        [
            {"code": "A.XSHE", "mode": "接力低弱转1", "adaptive_active": None},
            {"code": "B.XSHE", "mode": "首红断低吸", "adaptive_active": None},
        ],
    ]
    calls = {"n": 0}

    def fake_run_strategy(*args, **kwargs):
        i = min(calls["n"], len(snapshots) - 1)
        calls["n"] += 1
        return snapshots[i]

    monkeypatch.setattr(live_recommend, "_today_iso", lambda: "2026-05-25")
    monkeypatch.setattr(live_recommend, "run_strategy", fake_run_strategy)
    monkeypatch.setattr(live_recommend._time, "sleep", lambda _seconds: None)

    rows, actives = _run_strategy_when_ready(
        "2026-05-25",
        source=None,
        timeout_sec=10,
        poll_sec=1,
        confirm_sec=5,
        stable_samples=2,
    )

    assert calls["n"] == 4
    assert [row["code"] for row in rows] == ["A.XSHE", "B.XSHE"]
    assert len(actives) == 2


def test_basket_price_caps_low_absorb_at_preclose_when_chasing() -> None:
    price, rule = _basket_price(entry_price=9.96, pre_close=10.0, premium_pct=0.8, cap_pct=0.0)

    assert price == 10.0
    assert rule == "cap preClose+0.0%"


def test_basket_price_uses_entry_only_when_mode_cap_below_entry() -> None:
    price, rule = _basket_price(entry_price=10.2, pre_close=10.0, premium_pct=0.8, cap_pct=0.0)

    assert price == 10.2
    assert rule == "entry-only; cap<=preClose+0.0%"


def test_profile_stop_is_recomputed_from_actual_fill_price() -> None:
    assert _profile_stop(20.22, 2.0) == 19.8156
    assert _profile_stop(20.22, 0.5) == 20.1189


def test_select_candidates_caps_total_and_per_mode() -> None:
    candidates = [
        {"code": "A", "mode": "绿断低吸", "xcjw": 320, "cjs": 100, "open_pct_change": -3.0},
        {"code": "B", "mode": "绿断低吸", "xcjw": 300, "cjs": 80, "open_pct_change": -2.8},
        {"code": "C", "mode": "绿断低吸", "xcjw": 280, "cjs": 60, "open_pct_change": -3.2},
        {"code": "D", "mode": "红断低吸", "xcjw": 260, "cjs": 70, "open_pct_change": -3.0},
    ]

    selected, overflow = _select_candidates(candidates, max_candidates=3, max_per_mode=2)

    assert [row["code"] for row in selected] == ["A", "B", "D"]
    assert [row["code"] for row in overflow] == ["C"]


def test_select_standby_keeps_close_ranked_diversifying_candidates() -> None:
    ranked = [
        {"code": "A", "mode": "绿断低吸", "rank_score": 90, "blockCodeList": "B1"},
        {"code": "B", "mode": "接力低弱转1", "rank_score": 88, "blockCodeList": "B2"},
        {"code": "C", "mode": "N字低吸", "rank_score": 86, "blockCodeList": "B3"},
        {"code": "D", "mode": "红断低吸", "rank_score": 84, "blockCodeList": "B4"},
        {"code": "E", "mode": "方向低位低吸", "rank_score": 75, "blockCodeList": "B5"},
    ]

    standby = _select_standby_candidates(
        ranked,
        selected=ranked[:3],
        max_standby=2,
        max_rank_gap=3.0,
        max_per_mode=2,
    )

    assert [row["code"] for row in standby] == ["D"]
    assert standby[0]["standby_reason"] == "rank_gap<=3.0; diversified"


def test_select_standby_rejects_same_block_crowding() -> None:
    ranked = [
        {"code": "A", "mode": "绿断低吸", "rank_score": 90, "blockCodeList": "B1"},
        {"code": "B", "mode": "接力低弱转1", "rank_score": 88, "blockCodeList": "B2"},
        {"code": "C", "mode": "N字低吸", "rank_score": 86, "blockCodeList": "B3"},
        {"code": "D", "mode": "红断低吸", "rank_score": 84, "blockCodeList": "B2"},
    ]

    assert _select_standby_candidates(ranked, ranked[:3]) == []
