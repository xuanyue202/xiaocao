from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from xiaocao.live.book_b_live_morning import (
    BookBLiveMorningConfig,
    load_book_b_live_capital_basis,
    run_book_b_live_morning,
)
from xiaocao.live.trading_execution import (
    BrokerReceipt,
    BrokerStatus,
    ExecutionReceipt,
    ExecutionState,
)
from xiaocao.live.trading_runner import frozen_rows_digest


def _frozen_row() -> dict:
    return {
        "date": "2026-08-24",
        "book": "B",
        "is_live": True,
        "mode_exec_star": True,
        "mode_trade_eligible": True,
        "executable_fillable": True,
        "mode_state": "ACTIVE",
        "mode": "mode-a",
        "mode_exec_target_weight": 0.5,
        "code": "000001.XSHE",
        "name": "测试标的",
        "open": 10.0,
        "basket_price": 10.10,
        "market_guard_status": "ok",
    }


def _ready_freeze() -> dict:
    return {
        "status": "ready",
        "reason": "dated_frozen_evidence_ready",
        "market_date": "2026-08-24",
        "queue_status": "ready",
        "selected_items": 1,
        "snapshot_sha256": frozen_rows_digest([_frozen_row()]),
        "snapshot_row_count": 1,
        "strategy_run_id": "morning-freeze:2026-08-24:test",
        "strategy_sha": "c" * 40,
    }


def _canonical_sha256(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _live_allocation_payload() -> dict:
    binding_hash = "b" * 64
    broker_receipt = {
        "template_name": "foundersc-quant/reconcile",
        "template_version": 3,
        "status": "allocation_reconciled",
        "trade_date": "2026-08-24",
        "environment": "live",
        "logical_account_id": "primary",
        "account_binding": "bound",
        "fund_account_binding_sha256": binding_hash,
        "observed_at": "2026-08-24T01:20:00+00:00",
        "allocation_summary": {
            "complete": True,
            "values": {"总资产": 100_000.0, "证券市值": 0.0, "可用资金": 30_000.0},
        },
    }
    payload = {
        "trade_date": "2026-08-24",
        "environment": "live",
        "logical_account_id": "primary",
        "account_binding": "bound",
        "fund_account_binding_sha256": binding_hash,
        "settled_nav": 30_000,
        "available_cash": 30_000,
        "current_open_exposure": 0,
        "capital_basis_source": "initial_book_b_capital",
        "broker_total_assets": 100_000,
        "broker_securities_market_value": 0,
        "source": "foundersc_reconcile",
        "broker_observed_at": "2026-08-24T01:20:00+00:00",
        "broker_receipt": broker_receipt,
        "broker_receipt_sha256": _canonical_sha256(broker_receipt),
    }
    payload["allocation_capsule_sha256"] = _canonical_sha256(payload)
    return payload


def test_live_morning_rejects_snapshot_rows_before_dated_freeze_is_complete(
    tmp_path: Path,
) -> None:
    freeze = tmp_path / "signal_snapshots.jsonl"
    freeze.write_text(json.dumps(_frozen_row()) + "\n", encoding="utf-8")
    allocation = tmp_path / "allocation.json"
    allocation.write_text(
        json.dumps(
            {
                "settled_nav": 30_000,
                "available_cash": 30_000,
                "source": "foundersc_reconcile",
            }
        ),
        encoding="utf-8",
    )
    calls = []

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
        ),
        execute=lambda plan: calls.append(plan),
        now=lambda: datetime(2026, 8, 24, 1, 24, tzinfo=timezone.utc),
    )

    assert receipt.status == "blocked"
    assert receipt.reason == "DATED_FREEZE_NOT_PROVEN"
    assert calls == []


def test_live_morning_accepts_a_proven_empty_freeze_without_snapshot_rows(
    tmp_path: Path,
) -> None:
    (tmp_path / "empty-snapshots.jsonl").write_text("", encoding="utf-8")
    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=tmp_path / "empty-snapshots.jsonl",
            allocation_facts_path=tmp_path / "missing-allocation.json",
            state_dir=tmp_path / "state",
            dated_freeze_receipt={
                **_ready_freeze(),
                "queue_status": "empty",
                "selected_items": 0,
                "snapshot_sha256": frozen_rows_digest([]),
                "snapshot_row_count": 0,
            },
        ),
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
    )

    assert receipt.status == "no_action"
    assert receipt.reason == "NO_EXECUTABLE_STAR_E"


def test_live_morning_requires_explicit_fillable_evidence(tmp_path: Path) -> None:
    freeze = tmp_path / "signal_snapshots.jsonl"
    row = _frozen_row()
    row.pop("executable_fillable")
    freeze.write_text(json.dumps(row) + "\n", encoding="utf-8")
    allocation = tmp_path / "allocation.json"
    allocation.write_text(json.dumps(_live_allocation_payload()), encoding="utf-8")

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
            dated_freeze_receipt={
                **_ready_freeze(),
                "snapshot_sha256": frozen_rows_digest([row]),
            },
        ),
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
    )

    assert receipt.status == "no_action"
    assert receipt.reason == "NO_EXECUTABLE_STAR_E"


@pytest.mark.parametrize(
    ("payload_update", "reason"),
    [
        ({"trade_date": None}, "LIVE_ALLOCATION_TRADE_DATE_MISSING"),
        ({"trade_date": "2026-08-23"}, "LIVE_ALLOCATION_TRADE_DATE_MISMATCH"),
        ({"environment": "mock"}, "LIVE_ALLOCATION_ENVIRONMENT_NOT_LIVE"),
        ({"logical_account_id": "other"}, "LIVE_ALLOCATION_ACCOUNT_MISMATCH"),
        ({"account_binding": "not_proven"}, "LIVE_ALLOCATION_ACCOUNT_BINDING_UNPROVEN"),
        ({"source": "explicit"}, "LIVE_ALLOCATION_SOURCE_UNPROVEN"),
        ({"broker_receipt_sha256": "a" * 64}, "LIVE_ALLOCATION_RECEIPT_HASH_MISMATCH"),
        ({"available_cash": 29_000}, "LIVE_ALLOCATION_CAPSULE_HASH_MISMATCH"),
    ],
)
def test_live_morning_requires_dated_broker_bound_allocation_facts(
    tmp_path: Path,
    payload_update: dict,
    reason: str,
) -> None:
    freeze = tmp_path / "signal_snapshots.jsonl"
    freeze.write_text(json.dumps(_frozen_row()) + "\n", encoding="utf-8")
    allocation = tmp_path / "allocation.json"
    payload = {**_live_allocation_payload(), **payload_update}
    if reason != "LIVE_ALLOCATION_CAPSULE_HASH_MISMATCH":
        payload_without_hash = {
            key: value
            for key, value in payload.items()
            if key != "allocation_capsule_sha256"
        }
        payload["allocation_capsule_sha256"] = _canonical_sha256(payload_without_hash)
    allocation.write_text(json.dumps(payload), encoding="utf-8")

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
            dated_freeze_receipt=_ready_freeze(),
        ),
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
    )

    assert receipt.status == "blocked"
    assert receipt.reason == reason


def test_live_morning_requires_broker_cash_to_match_allocation_cash(tmp_path: Path) -> None:
    freeze = tmp_path / "signal_snapshots.jsonl"
    freeze.write_text(json.dumps(_frozen_row()) + "\n", encoding="utf-8")
    payload = _live_allocation_payload()
    payload["available_cash"] = 29_000
    payload["allocation_capsule_sha256"] = _canonical_sha256(
        {key: value for key, value in payload.items() if key != "allocation_capsule_sha256"}
    )
    allocation = tmp_path / "allocation.json"
    allocation.write_text(json.dumps(payload), encoding="utf-8")

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
            dated_freeze_receipt=_ready_freeze(),
        ),
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
    )

    assert receipt.status == "blocked"
    assert receipt.reason == "LIVE_ALLOCATION_ECONOMIC_BINDING_MISMATCH"


def test_live_morning_restores_mock_even_when_freeze_is_blocked(tmp_path: Path) -> None:
    events = []

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=tmp_path / "missing.jsonl",
            allocation_facts_path=tmp_path / "missing-allocation.json",
            state_dir=tmp_path / "state",
        ),
        preflight=lambda: (
            events.append("live"),
            {"status": "environment_switched", "environment": "live"},
        )[1],
        restore_environment=lambda: (
            events.append("mock"),
            {"status": "environment_switched", "environment": "mock"},
        )[1],
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
    )

    assert receipt.status == "blocked"
    assert receipt.reason == "DATED_FREEZE_NOT_PROVEN"
    assert events == ["live", "mock"]


def test_live_morning_restores_mock_before_propagating_unexpected_error(
    tmp_path: Path,
) -> None:
    events = []

    with pytest.raises(TypeError, match="unexpected"):
        run_book_b_live_morning(
            BookBLiveMorningConfig(
                trade_date="2026-08-24",
                freeze_path=tmp_path / "missing.jsonl",
                allocation_facts_path=tmp_path / "missing-allocation.json",
                state_dir=tmp_path / "state",
            ),
            preflight=lambda: (
                events.append("live"),
                {"status": "environment_switched", "environment": "live"},
            )[1],
            restore_environment=lambda: (
                events.append("mock"),
                {"status": "environment_switched", "environment": "mock"},
            )[1],
            wait_for_dated_freeze=lambda: (_ for _ in ()).throw(TypeError("unexpected")),
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
        )

    assert events == ["live", "mock"]


def test_live_morning_requires_preflight_and_restore_callbacks_as_a_pair(
    tmp_path: Path,
) -> None:
    events = []

    with pytest.raises(ValueError, match="LIVE_ENVIRONMENT_CALLBACKS_MUST_BE_PAIRED"):
        run_book_b_live_morning(
            BookBLiveMorningConfig(
                trade_date="2026-08-24",
                freeze_path=tmp_path / "missing.jsonl",
                allocation_facts_path=tmp_path / "missing-allocation.json",
                state_dir=tmp_path / "state",
            ),
            preflight=lambda: events.append("live") or {"environment": "live"},
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
        )

    assert events == []


def test_live_morning_rejects_any_logical_account_except_primary(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LIVE_LOGICAL_ACCOUNT_MUST_BE_PRIMARY"):
        run_book_b_live_morning(
            BookBLiveMorningConfig(
                trade_date="2026-08-24",
                freeze_path=tmp_path / "missing.jsonl",
                allocation_facts_path=tmp_path / "missing-allocation.json",
                state_dir=tmp_path / "state",
                logical_account_id="other",
            ),
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
        )


def test_live_morning_produces_allocation_facts_before_waiting_for_freeze(
    tmp_path: Path,
) -> None:
    allocation = tmp_path / "book_b_live_allocation_facts_2026-08-24.json"
    freeze = tmp_path / "empty.jsonl"
    freeze.write_text("", encoding="utf-8")
    events = []

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
        ),
        read_allocation_facts=lambda: (
            events.append("allocation"),
            _live_allocation_payload(),
        )[1],
        wait_for_dated_freeze=lambda: (
            events.append("freeze"),
            {
                **_ready_freeze(),
                "queue_status": "empty",
                "selected_items": 0,
                "snapshot_sha256": frozen_rows_digest([]),
                "snapshot_row_count": 0,
            },
        )[1],
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
    )

    assert receipt.status == "no_action"
    assert events == ["allocation", "freeze"]
    assert json.loads(allocation.read_text(encoding="utf-8"))["source"] == "foundersc_reconcile"


def test_live_morning_rejects_snapshot_changed_after_freeze_receipt(tmp_path: Path) -> None:
    freeze = tmp_path / "signal_snapshots.jsonl"
    changed = {**_frozen_row(), "basket_price": 10.20}
    freeze.write_text(json.dumps(changed) + "\n", encoding="utf-8")

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=tmp_path / "allocation.json",
            state_dir=tmp_path / "state",
            dated_freeze_receipt=_ready_freeze(),
        ),
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
    )

    assert receipt.status == "blocked"
    assert receipt.reason == "FROZEN_SNAPSHOT_DIGEST_MISMATCH"


def test_live_capital_basis_uses_30000_only_before_any_owned_fill(tmp_path: Path) -> None:
    basis = load_book_b_live_capital_basis(tmp_path)
    assert basis.settled_nav == 30_000
    assert basis.current_open_exposure == 0

    (tmp_path / "book_b_ownership_evidence.jsonl").write_text(
        json.dumps({"kind": "fill_observed", "book": "B", "shares": 100}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED"):
        load_book_b_live_capital_basis(tmp_path)


def test_live_capital_basis_blocks_after_fill_event_even_if_ownership_write_failed(
    tmp_path: Path,
) -> None:
    (tmp_path / "events.jsonl").write_text(
        json.dumps(
            {
                "kind": "ledger_write_failed",
                "state": "filled",
                "receipt": {
                    "state": "filled",
                    "filled_shares": 100,
                    "broker_order_id": "broker-1",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED"):
        load_book_b_live_capital_basis(tmp_path)


def test_live_morning_consumes_freeze_without_paper_fill_or_ledger_mutation(
    tmp_path: Path,
) -> None:
    live_root = tmp_path / "output" / "live"
    live_root.mkdir(parents=True)
    freeze = live_root / "signal_snapshots.jsonl"
    freeze.write_text(json.dumps(_frozen_row(), ensure_ascii=False) + "\n", encoding="utf-8")
    allocation = live_root / "book_b_live_allocation_facts_2026-08-24.json"
    allocation.write_text(
        json.dumps(_live_allocation_payload())
        + "\n",
        encoding="utf-8",
    )
    sentinels = {}
    for name in (
        "positions.jsonl",
        "paper_trades.jsonl",
        "paper_account.json",
        "paper_account_T.json",
    ):
        path = live_root / name
        path.write_text(f"sentinel:{name}\n", encoding="utf-8")
        sentinels[path] = path.read_bytes()

    seen = []

    def execute(plan):
        seen.append(plan)
        return ExecutionReceipt(
            plan.plan_id,
            plan.plan_hash,
            ExecutionState.REJECTED,
            reason="NO_ROUTE_PROVEN",
            remaining_shares=plan.shares,
        )

    events = []

    def preflight():
        events.append("preflight")
        return {"status": "environment_switched", "environment": "live"}

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=live_root / "book_b_live_execution",
            dated_freeze_receipt=_ready_freeze(),
        ),
        execute=lambda plan: (events.append("execute"), execute(plan))[1],
        preflight=preflight,
        restore_environment=lambda: (
            events.append("restore"),
            {"status": "environment_switched", "environment": "mock"},
        )[1],
        now=lambda: datetime(2026, 8, 24, 1, 24, tzinfo=timezone.utc),
    )

    assert receipt.status == "blocked"
    assert receipt.reason == "NO_ROUTE_PROVEN"
    assert len(seen) == 1
    assert seen[0].environment == "live"
    assert seen[0].strategy_sha == "c" * 40
    assert seen[0].limit_price == 10.05
    assert seen[0].shares == 1_400
    assert events == ["preflight", "execute", "restore"]
    assert all(path.read_bytes() == before for path, before in sentinels.items())
    assert (live_root / "book_b_live_execution" / "runs" / "2026-08-24.json").exists()


def test_live_morning_runs_auditable_prepare_only_before_execution(tmp_path: Path) -> None:
    freeze = tmp_path / "signal_snapshots.jsonl"
    freeze.write_text(json.dumps(_frozen_row(), ensure_ascii=False) + "\n", encoding="utf-8")
    allocation = tmp_path / "allocation.json"
    allocation.write_text(json.dumps(_live_allocation_payload()), encoding="utf-8")
    events: list[str] = []

    def prepare_only(plan):
        events.append("prepare")
        return BrokerReceipt(
            status=BrokerStatus.PREPARED,
            requested_shares=plan.shares,
            account_binding="proven",
            echoed={
                "code": plan.code,
                "side": plan.side,
                "shares": plan.shares,
                "limit_price": plan.limit_price,
            },
            field_readback={
                "strategy_name": "xiaocao-readback-2026-08-24-000001",
                "date": "2026-08-24",
                "hour": "9",
                "minute": "30",
                "submitted": False,
                "saved": False,
                "started": False,
                "form_closed": True,
            },
        )

    def execute(plan):
        events.append("execute")
        return ExecutionReceipt(
            plan.plan_id,
            plan.plan_hash,
            ExecutionState.REJECTED,
            reason="NO_ROUTE_PROVEN",
            remaining_shares=plan.shares,
        )

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
            dated_freeze_receipt=_ready_freeze(),
        ),
        preflight=lambda: events.append("live") or {"environment": "live"},
        restore_environment=lambda: events.append("mock") or {"environment": "mock"},
        prepare_only=prepare_only,
        execute=execute,
        now=lambda: datetime(2026, 8, 24, 1, 24, tzinfo=timezone.utc),
    )

    assert events == ["live", "prepare", "execute", "mock"]
    assert receipt.reason == "NO_ROUTE_PROVEN"
    assert len(receipt.preparation_receipts) == 1
    assert receipt.preparation_receipts[0]["status"] == "prepared"
    assert receipt.preparation_receipts[0]["submitted"] is False
    assert receipt.preparation_receipts[0]["saved"] is False
    assert receipt.preparation_receipts[0]["started"] is False
    assert receipt.preparation_receipts[0]["form_closed"] is True
    assert receipt.preparation_receipts[0]["strategy_name"] == (
        "xiaocao-readback-2026-08-24-000001"
    )
    assert receipt.preparation_receipts[0]["date"] == "2026-08-24"
    assert receipt.preparation_receipts[0]["hour"] == "9"
    assert receipt.preparation_receipts[0]["minute"] == "30"


@pytest.mark.parametrize(
    ("prepare_receipt", "reason"),
    [
        (
            BrokerReceipt(status=BrokerStatus.UNKNOWN, reason="not proven"),
            "LIVE_PREPARE_ONLY_NOT_PROVEN:not proven",
        ),
        (
            BrokerReceipt(
                status=BrokerStatus.PREPARED,
                account_binding="proven",
                echoed={
                    "code": "000001.XSHE",
                    "side": "BUY",
                    "shares": 1_400,
                    "limit_price": 10.05,
                },
                field_readback={
                    "strategy_name": "xiaocao-readback-2026-08-24-000001",
                    "date": "2026-08-24",
                    "hour": "9",
                    "minute": "30",
                    "submitted": False,
                    "saved": True,
                    "started": False,
                    "form_closed": True,
                },
            ),
            "LIVE_PREPARE_ONLY_SIDE_EFFECT_UNSAFE",
        ),
    ],
)
def test_live_morning_blocks_before_execution_when_prepare_only_is_unproven(
    tmp_path: Path,
    prepare_receipt: BrokerReceipt,
    reason: str,
) -> None:
    freeze = tmp_path / "signal_snapshots.jsonl"
    freeze.write_text(json.dumps(_frozen_row()) + "\n", encoding="utf-8")
    allocation = tmp_path / "allocation.json"
    allocation.write_text(json.dumps(_live_allocation_payload()), encoding="utf-8")
    executed: list[object] = []

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
            dated_freeze_receipt=_ready_freeze(),
        ),
        prepare_only=lambda _plan: prepare_receipt,
        execute=lambda plan: executed.append(plan),
        now=lambda: datetime(2026, 8, 24, 1, 24, tzinfo=timezone.utc),
    )

    assert receipt.status == "blocked"
    assert receipt.reason == reason
    assert executed == []


def test_live_morning_does_not_wait_for_simulated_fill_fields(tmp_path: Path) -> None:
    freeze = tmp_path / "freeze.jsonl"
    row = _frozen_row()
    assert "sim_price" not in row and "fill_price" not in row
    freeze.write_text(json.dumps(row) + "\n", encoding="utf-8")
    allocation = tmp_path / "allocation.json"
    allocation.write_text(
        json.dumps(_live_allocation_payload()),
        encoding="utf-8",
    )

    calls = []

    def execute(plan):
        calls.append(plan)
        return ExecutionReceipt(
            plan.plan_id,
            plan.plan_hash,
            ExecutionState.SKIPPED,
            reason="LIMIT_DOWN_BUY_BLOCKED",
        )

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date="2026-08-24",
            freeze_path=freeze,
            allocation_facts_path=allocation,
            state_dir=tmp_path / "state",
            dated_freeze_receipt=_ready_freeze(),
        ),
        execute=execute,
        now=lambda: datetime(2026, 8, 24, 1, 24, tzinfo=timezone.utc),
    )

    assert receipt.status == "skipped"
    assert receipt.reason == "LIMIT_DOWN_BUY_BLOCKED"
    assert len(calls) == 1


def test_live_morning_cli_is_independent_of_auto_daily() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "book_b_live_morning.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert "waits only for the dated deterministic freeze" in result.stdout
    assert "simulated fill" in result.stdout
    assert "auto_daily.sh" in result.stdout
    assert "--initial-capital" not in result.stdout
    assert "--logical-account-id" not in result.stdout
