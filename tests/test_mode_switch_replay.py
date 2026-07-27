from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.research_mode_switch_replay import run_replay


def test_replay_uses_shared_mode_gate_and_settles_terminal_batch(tmp_path: Path) -> None:
    evidence_days = [
        "2026-05-18",
        "2026-05-19",
        "2026-05-20",
        "2026-05-21",
        "2026-05-22",
        "2026-05-25",
        "2026-05-26",
        "2026-05-27",
    ]
    rows = []
    for day in evidence_days:
        for index in range(2):
            rows.append({
                "date": day,
                "code": f"M{index}.{day}.XSHE",
                "mode": "M",
                "is_live": True,
                "book": "B",
                "executable_fillable": True,
                "executable_entry_price": 10.0,
                "executable_net_ret": 3.0,
                "market_return_pct": 0.0,
                "rank_score": 10.0,
                "k_score": 1.0,
                "p_score": 1.0,
            })
        rows.append({
            "date": day,
            "code": f"BASE.{day}.XSHE",
            "mode": "BASE",
            "is_live": True,
            "book": "B",
            "executable_fillable": True,
            "executable_entry_price": 10.0,
            "executable_net_ret": 0.0,
            "market_return_pct": 0.0,
            "rank_score": 1.0,
            "k_score": 0.0,
            "p_score": 0.0,
        })
    rows.append({
        "date": "2026-06-01",
        "code": "LOSS.XSHE",
        "name": "Terminal loss",
        "mode": "M",
        "is_live": True,
        "book": "B",
        "executable_fillable": True,
        "executable_entry_price": 10.0,
        "executable_entry_basis": "test_fill",
        "executable_net_ret": -10.0,
        "market_return_pct": 0.0,
        "rank_score": 100.0,
        "k_score": 1.0,
        "p_score": 1.0,
    })
    training = tmp_path / "training.parquet"
    pd.DataFrame(rows).to_parquet(training, index=False)
    trade_days = evidence_days + ["2026-05-28", "2026-05-29", "2026-06-01"]

    result = run_replay(
        training_path=training,
        start="2026-06-01",
        end="2026-06-01",
        initial_capital=100000.0,
        fee_rate=0.0001,
        trade_days=trade_days,
    )

    assert result["summary"]["trade_days"] == 1
    assert result["summary"]["positions"] == 1
    assert result["summary"]["return_pct"] < 0
    assert result["summary"]["max_drawdown_pct"] > 0
    assert result["daily"][0]["equity_close"] == 100000.0
    assert result["daily"][0]["batch_market_return_pct"] == 0.0
    assert result["daily"][0]["mode_states"]["M"]["state"] == "ACTIVE"
    assert result["mode_audit"][0]["state"] == "ACTIVE"
