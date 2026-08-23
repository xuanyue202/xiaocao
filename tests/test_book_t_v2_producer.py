from __future__ import annotations

import hashlib
import json

import pytest

from xiaocao.kol.publication import canonical_sha256
from xiaocao.research.book_t_shadow import evaluate_book_t_shadow, run_book_t_shadow
from xiaocao.research.book_t_v2_producer import (
    BookTV2ProducerError,
    prepare_book_t_v2_shadow_day,
    record_book_t_v2_daily_mark,
)


def _receipt(root, date_iso: str) -> None:
    live = root / "output" / "live"
    live.mkdir(parents=True)
    files = {
        "positions": live / "positions.jsonl",
        "account": live / "paper_account_T.json",
        "trades": live / "paper_trades.jsonl",
    }
    files["positions"].write_text("", encoding="utf-8")
    files["account"].write_text('{"cash": 100000, "fee_rate": 0.0001}\n', encoding="utf-8")
    files["trades"].write_text("", encoding="utf-8")
    semantics = {
        "as_of": date_iso,
        "book": "T",
        "selection": {"as_of": date_iso, "selected_codes": [], "actions": []},
        "actions": [],
        "trade_count": 0,
        "skip_count": 0,
        "position_transition_count": 0,
    }
    body = {
        "consumer": "book_t_v1_control",
        "producer": "kronos_screen/scripts/paper_record.py",
        "mode": "trend-only",
        "book": "T",
        "as_of": date_iso,
        "artifact_paths": {
            "positions": "output/live/positions.jsonl",
            "account": "output/live/paper_account_T.json",
            "trades": "output/live/paper_trades.jsonl",
        },
        "artifact_hashes": {
            key: hashlib.sha256(path.read_bytes()).hexdigest()
            for key, path in files.items()
        },
        "daily_semantics": semantics,
        "daily_semantics_sha256": canonical_sha256(semantics),
    }
    (live / f"book_t_v1_control_receipt_{date_iso}.json").write_text(
        json.dumps({**body, "receipt_sha256": canonical_sha256(body)}, sort_keys=True),
        encoding="utf-8",
    )


def test_producer_builds_pending_shadow_input_from_injected_source_adapters(tmp_path) -> None:
    date_iso = "2026-08-21"
    _receipt(tmp_path, date_iso)
    capsule = {
        "publications": [],
        "agent_draft": {
            "themes": [],
            "status": "pending_observation",
            "reason": "no dated structured judgment in rehearsal",
        },
        "market_validation": {},
        "catalog": {
            "version": "catalog-rehearsal",
            "theme_registry": {"version": "registry-rehearsal", "themes": [], "changes": []},
            "blocks": [],
            "etfs": [],
            "stocks": [],
        },
        "portfolio": {
            "as_of": date_iso,
            "account_equity": 100000,
            "positions": [],
            "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0},
        },
        "market_input": {
            "market_date": date_iso,
            "is_trading_day": True,
            "trading_day_index": 42,
            "quotes": {},
            "liquidity": {},
            "source": "isolated_rehearsal_capsule",
        },
    }

    result = prepare_book_t_v2_shadow_day(
        tmp_path,
        date_iso,
        run_mode="rehearsal",
        capsule=capsule,
    )
    frozen = json.loads(result["input"].read_text(encoding="utf-8"))
    run = run_book_t_shadow(frozen)
    evaluation = evaluate_book_t_shadow([run])

    assert frozen["input_sha256"]
    assert frozen["bindings"]["snapshot"]["snapshot_sha256"]
    assert frozen["bindings"]["universe"]["universe_sha256"]
    assert frozen["bindings"]["selection_plan"]["selection_plan_sha256"]
    assert frozen["bindings"]["portfolio"]["account_equity"] == 100000
    assert frozen["evidence_lifecycle"]["outcome_status"] == "not_applicable"
    assert run["engineering"]["engineering_day_valid"] is True
    assert run["engineering"]["outcome_matured"] is False
    assert evaluation["status"] == "pending_observation"
    assert evaluation["sample"]["real_trading_days"] == 0
    assert evaluation["sample"]["rehearsal_days_excluded"] == 1
    assert "engineering_burn_in" in evaluation["pending_reasons"]

    mark = record_book_t_v2_daily_mark(tmp_path, date_iso, marks=[])
    assert mark["stage_counts"]["daily_mark"] == 1
    assert mark["outcome_matured"] == 0


def test_producer_rejects_control_artifact_changed_after_receipt(tmp_path) -> None:
    date_iso = "2026-08-21"
    _receipt(tmp_path, date_iso)
    (tmp_path / "output/live/positions.jsonl").write_text("changed\n", encoding="utf-8")

    with pytest.raises(BookTV2ProducerError, match="artifact changed"):
        prepare_book_t_v2_shadow_day(
            tmp_path,
            date_iso,
            run_mode="rehearsal",
            capsule={
                "catalog": {"version": "test", "theme_registry": {}, "blocks": [], "etfs": [], "stocks": []},
                "portfolio": {"account_equity": 100000, "positions": []},
                "market_input": {"market_date": date_iso, "is_trading_day": True, "trading_day_index": 1},
                "publications": [],
                "agent_draft": {"themes": []},
            },
        )
