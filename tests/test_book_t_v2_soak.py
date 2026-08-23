from __future__ import annotations

import json

import pytest

import scripts.book_t_v2_soak as soak
from scripts.book_t_v2_soak import (
    evaluate_daily_stability_soak,
    evaluate_engineering_burn_in,
    main,
)


def _soak_inputs(
    indices: list[int],
    *,
    rehearsal_indices: set[int] | None = None,
) -> list[dict]:
    rehearsals = rehearsal_indices or set()
    return [
        {
            "as_of": f"2026-08-{index:02d}",
            "evidence_lifecycle": {
                "run_mode": "real",
                "provenance": {"is_rehearsal": index in rehearsals},
                "trading_day_index": index,
                "engineering_day": {"replayable": True},
            },
        }
        for index in indices
    ]


def _patch_valid_engineering_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        soak,
        "run_book_t_shadow",
        lambda _value: {
            "engineering": {
                "formal_ledger_mutations": {
                    "positions": 0,
                    "account": 0,
                    "trades": 0,
                },
                "daily_reevaluation_complete": True,
                "evidence_lifecycle_bound": True,
                "engineering_day_valid": True,
            }
        },
    )
    monkeypatch.setattr(soak, "validate_lifecycle", lambda value: value)


def test_five_day_daily_stability_soak_stays_pending_without_real_inputs() -> None:
    result = evaluate_daily_stability_soak([])

    assert result["status"] == "pending"
    assert result["gate"] == "daily_stability_soak"
    assert result["required_real_trading_days"] == 5
    assert result["real_trading_days"] == 0
    assert result["strategy_promotion_authorized"] is False


def test_daily_stability_soak_floor_cannot_be_lowered_below_five_days() -> None:
    with pytest.raises(ValueError, match="below five"):
        evaluate_daily_stability_soak([], required_days=4)


def test_daily_stability_cli_writes_a_separate_pending_verdict(tmp_path) -> None:
    assert main(["--root", str(tmp_path), "--gate", "daily-stability", "--json"]) == 0

    path = (
        tmp_path
        / "output/research/book_t_v2_shadow/daily_stability_soak_verdict.json"
    )
    verdict = json.loads(path.read_text(encoding="utf-8"))
    assert verdict["gate"] == "daily_stability_soak"
    assert verdict["required_real_trading_days"] == 5
    assert verdict["status"] == "pending"


def test_five_real_days_accept_daily_gate_but_not_twenty_day_gate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _soak_inputs([1, 2, 3, 4, 5])
    _patch_valid_engineering_rows(monkeypatch)
    monkeypatch.setattr(soak, "_load_inputs", lambda _root: inputs)

    assert main(["--root", str(tmp_path), "--gate", "daily-stability"]) == 0
    assert main(["--root", str(tmp_path), "--gate", "engineering-burn-in"]) == 0

    daily = json.loads(
        (
            tmp_path
            / "output/research/book_t_v2_shadow/daily_stability_soak_verdict.json"
        ).read_text(encoding="utf-8")
    )
    burn_in = json.loads(
        (
            tmp_path
            / "output/research/book_t_v2_shadow/engineering_burn_in_verdict.json"
        ).read_text(encoding="utf-8")
    )
    assert daily["status"] == "accepted"
    assert daily["real_trading_days"] == 5
    assert burn_in["status"] == "pending"
    assert burn_in["required_real_trading_days"] == 20


def test_rehearsal_is_excluded_and_real_day_gap_blocks_five_day_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_valid_engineering_rows(monkeypatch)
    inputs = _soak_inputs([1, 2, 3, 4, 5, 6], rehearsal_indices={3})

    result = evaluate_daily_stability_soak(inputs)

    assert result["real_trading_days"] == 5
    assert result["rehearsal_days_excluded"] == 1
    assert result["contiguous"] is False
    assert result["status"] == "pending"
    assert "real_trading_day_gap" in result["engineering_failures"]


def test_twenty_day_burn_in_stays_pending_without_real_inputs() -> None:
    result = evaluate_engineering_burn_in([])

    assert result["status"] == "pending"
    assert result["gate"] == "engineering_burn_in"
    assert result["required_real_trading_days"] == 20
    assert result["real_trading_days"] == 0
    assert result["rehearsal_days_excluded"] == 0
    assert result["strategy_promotion_authorized"] is False


def test_engineering_burn_in_floor_cannot_be_lowered_below_twenty_days() -> None:
    with pytest.raises(ValueError, match="below twenty"):
        evaluate_engineering_burn_in([], required_days=19)
