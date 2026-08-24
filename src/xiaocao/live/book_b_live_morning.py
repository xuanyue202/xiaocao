"""Independent morning orchestration for future real-capital Book B execution.

This module consumes the dated deterministic freeze and broker-sourced
allocation facts directly.  It never waits for paper fills and writes only to
its own execution namespace.  The broker adapter and the capital safety gate
remain responsible for deciding whether an external submit is possible.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .book_b_allocation import BookBAllocationFacts
from .trading_execution import (
    BrokerReceipt,
    BrokerStatus,
    ExecutionReceipt,
    ExecutionState,
    TradePlan,
)
from .trading_runner import (
    frozen_rows_digest,
    plans_from_frozen_rows,
    read_frozen_rows,
)


_PAPER_LEDGER_NAMES = frozenset(
    {
        "positions.jsonl",
        "paper_trades.jsonl",
        "paper_account.json",
        "paper_account_T.json",
        "paper_ledger.lock",
    }
)
_BOOK_B_INITIAL_CAPITAL = 30_000.0
_SETTLEMENT_REQUIRING_STATES = frozenset(
    {"submitted", "acknowledged", "partial", "filled", "unknown", "reconciling"}
)


@dataclass(frozen=True)
class BookBLiveMorningConfig:
    trade_date: str
    freeze_path: Path
    allocation_facts_path: Path
    state_dir: Path
    dated_freeze_receipt: dict | None = None
    logical_account_id: str = "primary"


@dataclass(frozen=True)
class BookBLiveMorningReceipt:
    trade_date: str
    status: str
    reason: str
    plan_count: int
    execution_receipts: tuple[dict, ...]
    preparation_receipts: tuple[dict, ...]
    freeze_path: str
    allocation_facts_path: str
    state_path: str
    preflight_receipt: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BookBLiveCapitalBasis:
    settled_nav: float
    current_open_exposure: float
    source: str


def load_book_b_live_capital_basis(
    state_dir: Path,
) -> BookBLiveCapitalBasis:
    """Return the first-batch basis or require a settled post-fill receipt."""
    root = Path(state_dir)
    ownership = root / "book_b_ownership_evidence.jsonl"
    try:
        has_owned_fill = ownership.is_file() and bool(ownership.read_text(encoding="utf-8").strip())
    except OSError as exc:
        raise ValueError("LIVE_BOOK_B_OWNERSHIP_EVIDENCE_UNREADABLE") from exc
    if has_owned_fill:
        raise ValueError("LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED")

    events = root / "events.jsonl"
    if events.is_file():
        try:
            lines = events.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError("LIVE_BOOK_B_EXECUTION_EVIDENCE_UNREADABLE") from exc
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("LIVE_BOOK_B_EXECUTION_EVIDENCE_INVALID") from exc
            if not isinstance(event, dict):
                raise ValueError("LIVE_BOOK_B_EXECUTION_EVIDENCE_INVALID")
            receipt = event.get("receipt")
            receipt = receipt if isinstance(receipt, dict) else {}
            state = str(event.get("state") or receipt.get("state") or "").strip().lower()
            try:
                filled_shares = int(receipt.get("filled_shares") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("LIVE_BOOK_B_EXECUTION_EVIDENCE_INVALID") from exc
            if state in _SETTLEMENT_REQUIRING_STATES or filled_shares > 0:
                raise ValueError("LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED")
    return BookBLiveCapitalBasis(
        settled_nav=_BOOK_B_INITIAL_CAPITAL,
        current_open_exposure=0.0,
        source="initial_book_b_capital",
    )


def _eligible_buy_rows(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("book") == "B"
        and row.get("is_live") is True
        and row.get("mode_exec_star") is True
        and row.get("mode_trade_eligible") is True
        and (
            "executable_fillable" not in row
            or row.get("executable_fillable") is True
        )
    ]


def _read_completed_freeze(
    config: BookBLiveMorningConfig,
    dated_freeze_receipt: dict,
) -> list[dict]:
    try:
        rows = read_frozen_rows(config.freeze_path, date=config.trade_date)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(f"FROZEN_EVIDENCE_UNAVAILABLE:{exc}") from exc
    expected_count = dated_freeze_receipt.get("snapshot_row_count")
    if not isinstance(expected_count, int) or expected_count < 0:
        raise ValueError("DATED_FREEZE_SNAPSHOT_NOT_BOUND")
    if expected_count != len(rows):
        raise ValueError("FROZEN_SNAPSHOT_ROW_COUNT_MISMATCH")
    digest = frozen_rows_digest(rows)
    if str(dated_freeze_receipt.get("snapshot_sha256") or "") != digest:
        raise ValueError("FROZEN_SNAPSHOT_DIGEST_MISMATCH")
    strategy_run_id = str(dated_freeze_receipt["strategy_run_id"])
    return [
        {
            **row,
            "strategy_run_id": strategy_run_id,
            "snapshot_ref": (
                f"{config.freeze_path}:{config.trade_date}:"
                f"sha256:{digest}:{row.get('code') or 'unknown'}"
            ),
        }
        for row in rows
    ]


def _load_allocation(
    config: BookBLiveMorningConfig,
    payload: dict | None = None,
) -> BookBAllocationFacts:
    if payload is None:
        try:
            payload = json.loads(config.allocation_facts_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError("LIVE_ALLOCATION_FACTS_MISSING") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("LIVE_ALLOCATION_FACTS_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("LIVE_ALLOCATION_FACTS_INVALID")
    capsule_hash = str(payload.get("allocation_capsule_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", capsule_hash):
        raise ValueError("LIVE_ALLOCATION_CAPSULE_UNPROVEN")
    capsule_payload = {
        key: value
        for key, value in payload.items()
        if key != "allocation_capsule_sha256"
    }
    recomputed_capsule_hash = hashlib.sha256(
        json.dumps(
            capsule_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    if recomputed_capsule_hash != capsule_hash:
        raise ValueError("LIVE_ALLOCATION_CAPSULE_HASH_MISMATCH")
    raw_date = str(payload.get("trade_date") or "")[:10]
    if not raw_date:
        raise ValueError("LIVE_ALLOCATION_TRADE_DATE_MISSING")
    if raw_date != config.trade_date:
        raise ValueError("LIVE_ALLOCATION_TRADE_DATE_MISMATCH")
    if str(payload.get("environment") or "").strip().lower() != "live":
        raise ValueError("LIVE_ALLOCATION_ENVIRONMENT_NOT_LIVE")
    if str(payload.get("logical_account_id") or "").strip() != config.logical_account_id:
        raise ValueError("LIVE_ALLOCATION_ACCOUNT_MISMATCH")
    if str(payload.get("account_binding") or "").strip().lower() not in {"bound", "proven"}:
        raise ValueError("LIVE_ALLOCATION_ACCOUNT_BINDING_UNPROVEN")
    if str(payload.get("source") or "").strip().lower() != "foundersc_reconcile":
        raise ValueError("LIVE_ALLOCATION_SOURCE_UNPROVEN")
    if str(payload.get("capital_basis_source") or "").strip() != "initial_book_b_capital":
        raise ValueError("LIVE_ALLOCATION_CAPITAL_BASIS_UNPROVEN")
    receipt_hash = str(payload.get("broker_receipt_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", receipt_hash):
        raise ValueError("LIVE_ALLOCATION_RECEIPT_UNPROVEN")
    binding_hash = str(payload.get("fund_account_binding_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", binding_hash):
        raise ValueError("LIVE_ALLOCATION_ACCOUNT_BINDING_UNPROVEN")
    broker_receipt = payload.get("broker_receipt")
    if not isinstance(broker_receipt, dict):
        raise ValueError("LIVE_ALLOCATION_RECEIPT_UNPROVEN")
    recomputed_hash = hashlib.sha256(
        json.dumps(
            broker_receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    if recomputed_hash != receipt_hash:
        raise ValueError("LIVE_ALLOCATION_RECEIPT_HASH_MISMATCH")
    receipt_binding = str(broker_receipt.get("account_binding") or "").strip().lower()
    if (
        str(broker_receipt.get("status") or "") != "allocation_reconciled"
        or str(broker_receipt.get("trade_date") or "")[:10] != config.trade_date
        or str(broker_receipt.get("environment") or "").strip().lower() != "live"
        or str(broker_receipt.get("logical_account_id") or "").strip()
        != config.logical_account_id
        or receipt_binding not in {"bound", "proven"}
        or str(broker_receipt.get("fund_account_binding_sha256") or "").strip().lower()
        != binding_hash
        or str(broker_receipt.get("observed_at") or "")
        != str(payload.get("broker_observed_at") or "")
    ):
        raise ValueError("LIVE_ALLOCATION_RECEIPT_BINDING_MISMATCH")
    summary = broker_receipt.get("allocation_summary")
    if not isinstance(summary, dict) or summary.get("complete") is not True:
        raise ValueError("LIVE_ALLOCATION_RECEIPT_UNPROVEN")
    values = summary.get("values")
    if not isinstance(values, dict):
        raise ValueError("LIVE_ALLOCATION_RECEIPT_UNPROVEN")
    try:
        broker_total_assets = float(values["总资产"])
        broker_market_value = float(values["证券市值"])
        broker_cash = float(values["可用资金"])
        top_total_assets = float(payload["broker_total_assets"])
        top_market_value = float(payload["broker_securities_market_value"])
        top_cash = float(payload["available_cash"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("LIVE_ALLOCATION_RECEIPT_UNPROVEN") from exc
    pairs = (
        (broker_total_assets, top_total_assets),
        (broker_market_value, top_market_value),
        (broker_cash, top_cash),
    )
    if any(
        not math.isfinite(left)
        or not math.isfinite(right)
        or not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-6)
        for left, right in pairs
    ):
        raise ValueError("LIVE_ALLOCATION_ECONOMIC_BINDING_MISMATCH")
    facts = BookBAllocationFacts.from_dict(payload)
    return facts


def _assert_isolated_state(config: BookBLiveMorningConfig) -> None:
    state = config.state_dir.resolve()
    for name in _PAPER_LEDGER_NAMES:
        ledger = (config.freeze_path.parent / name).resolve()
        if state == ledger or state in ledger.parents:
            raise ValueError(f"LIVE_STATE_OVERLAPS_PAPER_LEDGER:{name}")


def _assert_dated_freeze(config: BookBLiveMorningConfig, receipt: dict | None) -> dict:
    if not isinstance(receipt, dict):
        raise ValueError("DATED_FREEZE_NOT_PROVEN")
    if str(receipt.get("status") or "") != "ready":
        raise ValueError("DATED_FREEZE_NOT_PROVEN")
    if str(receipt.get("market_date") or "")[:10] != config.trade_date:
        raise ValueError("DATED_FREEZE_DATE_MISMATCH")
    if str(receipt.get("queue_status") or "") not in {"ready", "empty"}:
        raise ValueError("DATED_FREEZE_QUEUE_NOT_READY")
    digest = str(receipt.get("snapshot_sha256") or "")
    row_count = receipt.get("snapshot_row_count")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("DATED_FREEZE_SNAPSHOT_NOT_BOUND")
    if not isinstance(row_count, int) or row_count < 0:
        raise ValueError("DATED_FREEZE_SNAPSHOT_NOT_BOUND")
    if not str(receipt.get("strategy_run_id") or "").strip():
        raise ValueError("DATED_FREEZE_RUN_NOT_BOUND")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(receipt.get("strategy_sha") or "")):
        raise ValueError("DATED_FREEZE_STRATEGY_SHA_NOT_BOUND")
    return receipt


def _rollup(receipts: list[ExecutionReceipt]) -> tuple[str, str]:
    if not receipts:
        return "no_action", "NO_EXECUTABLE_STAR_E"
    states = {receipt.state for receipt in receipts}
    if states <= {ExecutionState.FILLED, ExecutionState.CANCELLED}:
        return "completed", "BROKER_TERMINAL"
    if states <= {ExecutionState.SKIPPED}:
        return "skipped", receipts[0].reason or "BROKER_SKIPPED"
    if ExecutionState.REJECTED in states:
        rejected = next(receipt for receipt in receipts if receipt.state == ExecutionState.REJECTED)
        return "blocked", rejected.reason or "BROKER_REJECTED"
    return "unresolved", next((receipt.reason for receipt in receipts if receipt.reason), "RECONCILE_REQUIRED")


def _write_json_atomic(target: Path, payload: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def _write_receipt(config: BookBLiveMorningConfig, receipt: BookBLiveMorningReceipt) -> None:
    target = config.state_dir / "runs" / f"{config.trade_date}.json"
    _write_json_atomic(target, receipt.as_dict())


def _no_action_receipt(config: BookBLiveMorningConfig) -> BookBLiveMorningReceipt:
    return BookBLiveMorningReceipt(
        trade_date=config.trade_date,
        status="no_action",
        reason="NO_EXECUTABLE_STAR_E",
        plan_count=0,
        execution_receipts=(),
        preparation_receipts=(),
        freeze_path=str(config.freeze_path),
        allocation_facts_path=str(config.allocation_facts_path),
        state_path=str(config.state_dir),
    )


def _blocked_receipt(
    config: BookBLiveMorningConfig,
    reason: str,
    preparation_receipts: tuple[dict, ...] = (),
) -> BookBLiveMorningReceipt:
    return BookBLiveMorningReceipt(
        trade_date=config.trade_date,
        status="blocked",
        reason=reason,
        plan_count=0,
        execution_receipts=(),
        preparation_receipts=preparation_receipts,
        freeze_path=str(config.freeze_path),
        allocation_facts_path=str(config.allocation_facts_path),
        state_path=str(config.state_dir),
    )


def _assert_prepare_only(plan: TradePlan, receipt: BrokerReceipt) -> dict:
    status = receipt.normalized_status()
    if status != BrokerStatus.PREPARED:
        reason = receipt.reason or receipt.error_code or status.value
        raise ValueError(f"LIVE_PREPARE_ONLY_NOT_PROVEN:{reason}")
    if receipt.account_binding != "proven":
        raise ValueError("LIVE_PREPARE_ONLY_ACCOUNT_BINDING_UNPROVEN")
    readback = receipt.field_readback
    if any(readback.get(key) is not False for key in ("submitted", "saved", "started")):
        raise ValueError("LIVE_PREPARE_ONLY_SIDE_EFFECT_UNSAFE")
    if readback.get("form_closed") is not True:
        raise ValueError("LIVE_PREPARE_ONLY_FORM_NOT_CLOSED")
    expected = {
        "code": plan.code,
        "side": plan.side,
        "shares": plan.shares,
        "limit_price": plan.limit_price,
    }
    if receipt.echoed != expected:
        raise ValueError("LIVE_PREPARE_ONLY_FIELD_READBACK_MISMATCH")
    timed_readback = {
        "strategy_name": (
            f"xiaocao-readback-{plan.trade_date}-{str(plan.code).split('.', 1)[0]}"
        ),
        "date": plan.trade_date,
        "hour": "9",
        "minute": "30",
    }
    has_timed_readback = any(key in readback for key in timed_readback)
    if has_timed_readback and any(
        str(readback.get(key) or "") != value
        for key, value in timed_readback.items()
    ):
        raise ValueError("LIVE_PREPARE_ONLY_TIMED_FIELD_READBACK_MISMATCH")
    result = {
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "status": BrokerStatus.PREPARED.value,
        "account_binding": "proven",
        "template_name": receipt.template_name,
        "template_version": receipt.template_version,
        "echoed": dict(receipt.echoed),
        "submitted": False,
        "saved": False,
        "started": False,
        "form_closed": True,
    }
    if has_timed_readback:
        result.update(timed_readback)
    return result


def run_book_b_live_morning(
    config: BookBLiveMorningConfig,
    *,
    execute: Callable[[TradePlan], ExecutionReceipt],
    preflight: Callable[[], dict] | None = None,
    restore_environment: Callable[[], dict] | None = None,
    read_allocation_facts: Callable[[], dict] | None = None,
    wait_for_dated_freeze: Callable[[], dict] | None = None,
    prepare_only: Callable[[TradePlan], BrokerReceipt] | None = None,
    wait_for_submit_window: Callable[[datetime], None] | None = None,
    wait_for_reconcile: Callable[[], None] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> BookBLiveMorningReceipt:
    """Consume one dated freeze and advance immutable live plans exactly once.

    The caller supplies one execution callable, normally the durable Founder
    execution module.  Tests use an in-memory adapter at the same seam.
    """
    if (preflight is None) != (restore_environment is None):
        raise ValueError("LIVE_ENVIRONMENT_CALLBACKS_MUST_BE_PAIRED")
    if config.logical_account_id != "primary":
        raise ValueError("LIVE_LOGICAL_ACCOUNT_MUST_BE_PRIMARY")
    _assert_isolated_state(config)
    preflight_attempted = False
    environment_receipt: dict | None = None
    preparation_receipts: list[dict] = []
    receipt: BookBLiveMorningReceipt
    restore_failure: str | None = None
    try:
        try:
            if preflight is not None:
                preflight_attempted = True
                environment_receipt = preflight()
                if str(environment_receipt.get("environment") or "").lower() != "live":
                    raise ValueError("LIVE_ENVIRONMENT_NOT_PROVEN")
            allocation: BookBAllocationFacts | None = None
            if read_allocation_facts is not None:
                allocation_payload = read_allocation_facts()
                allocation = _load_allocation(config, allocation_payload)
                _write_json_atomic(config.allocation_facts_path, allocation_payload)
            dated_freeze_receipt = (
                wait_for_dated_freeze()
                if wait_for_dated_freeze is not None
                else config.dated_freeze_receipt
            )
            dated_freeze_receipt = _assert_dated_freeze(config, dated_freeze_receipt)
            frozen_rows = _read_completed_freeze(config, dated_freeze_receipt)
            if not frozen_rows:
                receipt = _no_action_receipt(config)
            else:
                rows = _eligible_buy_rows(frozen_rows)
                if not rows:
                    receipt = _no_action_receipt(config)
                else:
                    allocation = allocation or _load_allocation(config)
                    plans = plans_from_frozen_rows(
                        rows,
                        environment="live",
                        logical_account_id=config.logical_account_id,
                        strategy_sha=str(dated_freeze_receipt["strategy_sha"]),
                        now=now(),
                        side="BUY",
                        allocation=allocation,
                    )
                    if prepare_only is not None:
                        preparation_receipts = [
                            _assert_prepare_only(plan, prepare_only(plan))
                            for plan in plans
                        ]
                    if wait_for_submit_window is not None:
                        submit_at = max(
                            plan.submit_not_before or plan.created_at
                            for plan in plans
                        )
                        if now() < submit_at:
                            wait_for_submit_window(submit_at)
                        if now() < submit_at:
                            raise ValueError("LIVE_SUBMIT_WINDOW_NOT_REACHED")
                    execution_receipts = []
                    for plan in plans:
                        execution_receipt = execute(plan)
                        for _attempt in range(3):
                            needs_mapping = (
                                execution_receipt.state == ExecutionState.UNKNOWN
                                or (
                                    execution_receipt.next_action
                                    in {"reconcile", "reconcile_only"}
                                    and not execution_receipt.broker_order_id
                                )
                            )
                            if not needs_mapping:
                                break
                            if wait_for_reconcile is not None:
                                wait_for_reconcile()
                            execution_receipt = execute(plan)
                        execution_receipts.append(execution_receipt)
                    status, reason = _rollup(execution_receipts)
                    receipt = BookBLiveMorningReceipt(
                        trade_date=config.trade_date,
                        status=status,
                        reason=reason,
                        plan_count=len(plans),
                        execution_receipts=tuple(item.as_dict() for item in execution_receipts),
                        preparation_receipts=tuple(preparation_receipts),
                        freeze_path=str(config.freeze_path),
                        allocation_facts_path=str(config.allocation_facts_path),
                        state_path=str(config.state_dir),
                    )
        except (OSError, ValueError, RuntimeError) as exc:
            receipt = _blocked_receipt(
                config,
                str(exc),
                tuple(preparation_receipts),
            )
    finally:
        if preflight_attempted and restore_environment is not None:
            try:
                restored = restore_environment()
                if str(restored.get("environment") or "").strip().lower() != "mock":
                    raise ValueError("MOCK_ENVIRONMENT_NOT_PROVEN")
            except Exception as exc:
                restore_failure = f"ENVIRONMENT_RESTORE_FAILED:{exc}"
    if restore_failure is not None:
        receipt = replace(receipt, status="blocked", reason=restore_failure)
    if environment_receipt is not None:
        receipt = replace(receipt, preflight_receipt=environment_receipt)
    _write_receipt(config, receipt)
    return receipt


__all__ = [
    "BookBLiveCapitalBasis",
    "BookBLiveMorningConfig",
    "BookBLiveMorningReceipt",
    "load_book_b_live_capital_basis",
    "run_book_b_live_morning",
]
