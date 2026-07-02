from __future__ import annotations

from kronos_screen.scripts import settle_book_t as sbt


def test_book_t_existing_bank_position_is_posture_mismatch_candidate() -> None:
    row = {
        "book": "T",
        "code": "601288.XSHG",
        "name": "农业银行",
        "category_name": "业绩股权类",
        "fee_rate": 0.0001,
    }

    alignment = sbt._trend_alignment_for_position(row)
    sbt._mark_trend_switch_context(row, fee_rate=0.0001, alignment=alignment)

    assert row["trend_alignment"] == "external"
    assert "银行" in row["trend_alignment_reason"]
    assert row["trend_switch_policy"] == "hold_exposure; switch_external_after_t1; otherwise_rebalance_on_R"
    assert row["trend_switch_est_roundtrip_fee_bps"] == 2.0

    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=0,
        rebalance_days=60,
        alignment=alignment,
    ) is None
    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=1,
        rebalance_days=60,
        alignment=alignment,
    ) == "TREND_POSTURE_MISMATCH"


def test_book_t_aligned_position_keeps_exposure_until_rebalance_or_trail() -> None:
    alignment = {
        "trend_alignment": "aligned",
        "trend_alignment_reason": "matched posture keyword: 半导体",
    }

    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=1,
        rebalance_days=60,
        alignment=alignment,
    ) is None
    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=60,
        rebalance_days=60,
        alignment=alignment,
    ) == "TREND_REBALANCE_R"
    assert sbt._trend_exit_reason(
        dd_pct=12.0,
        trail_dd=12.0,
        hold_days=1,
        rebalance_days=60,
        alignment=alignment,
    ) == "TREND_DAILY_TRAIL_STOP"
