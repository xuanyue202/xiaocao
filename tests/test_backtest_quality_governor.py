from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")  # backtest quality governor is pandas-based; skip (not error) if absent

from kronos_screen.scripts.backtest_quality_governor import _evaluate, _prepare  # noqa: E402


def test_quality_governor_backtest_uses_slot_cash_sizing() -> None:
    df = pd.DataFrame([
        {
            "dataset": "next_close",
            "date": "2026-01-01",
            "variant": "no_gate_k50_p_top3",
            "code": "A.XSHE",
            "mode": "绿断低吸",
            "ret": 10.0,
            "P": 0.0,
            "primary": 200.0,
        },
        {
            "dataset": "next_close",
            "date": "2026-01-01",
            "variant": "no_gate_k50_p_top3",
            "code": "B.XSHE",
            "mode": "绿断低吸",
            "ret": -10.0,
            "P": 0.0,
            "primary": 100.0,
        },
    ])
    prepared = _prepare(df)

    summary, daily, false_negative = _evaluate(
        prepared,
        policies=["no_governor", "primary_ge_150"],
        fee_rate=0.0,
        price_col=None,
        slot_notional=10000.0,
    )

    no_gate = daily[daily["policy"] == "no_governor"].iloc[0]
    primary = daily[daily["policy"] == "primary_ge_150"].iloc[0]
    assert no_gate["ret"] == 0.0
    assert primary["ret"] == 5.0
    assert primary["kept_slots"] == 1
    assert primary["cash_slots"] == 1
    assert summary.loc[summary["policy"] == "primary_ge_150", "rejected_trades"].iloc[0] == 1
    assert false_negative.loc[false_negative["policy"] == "primary_ge_150", "rejected_trades"].iloc[0] == 1
