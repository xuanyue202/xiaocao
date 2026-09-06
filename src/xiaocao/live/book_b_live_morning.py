"""Independent morning orchestration for future real-capital Book B execution.

This module consumes the dated deterministic freeze and broker-sourced
allocation facts directly.  It never waits for paper fills and writes only to
its own execution namespace.  The broker adapter and the capital safety gate
remain responsible for deciding whether an external submit is possible.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .book_b_allocation import BookBAllocationFacts, allocate_frozen_rows, validate_allocation_rows
from .account_risk import AccountRiskReceipt
from .live_decision_support import (
    bind_plan_audit, buy_cap, evaluate_live_risk, read_plan_audit, read_policy,
)
from xiaocao.strategy.mode_switch import plan_board_lot_orders
from .book_b_live_lifecycle import (
    load_latest_book_b_live_settlement,
    open_execution_plan_ids,
    ownership_head_sha256,
    validate_broker_account_snapshot,
)
from .trading_execution import (
    BrokerReceipt,
    BrokerStatus,
    ExecutionReceipt,
    ExecutionStore,
    ExecutionState,
    TradePlan,
    account_writer_lock,
    trade_plan_from_frozen_row,
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
    {
        "claimed",
        "submitted",
        "acknowledged",
        "partial",
        "filled",
        "unknown",
        "reconciling",
    }
)


@dataclass(frozen=True)
class BookBLiveMorningConfig:
    trade_date: str
    freeze_path: Path
    allocation_facts_path: Path
    state_dir: Path
    dated_freeze_receipt: dict | None = None
    logical_account_id: str = "primary"
    policy_root: Path | None = None


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
    environment_restoration: dict | None = None
    capital_runtime: dict | None = None
    open_plan_reconciliations: tuple[dict, ...] = ()
    prior_reconciliations: tuple[dict, ...] = ()
    policy_consumptions: tuple[dict, ...] = ()
    review_rendezvous: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BookBLiveCapitalBasis:
    settled_nav: float
    current_open_exposure: float
    source: str
    receipt_sha256: str | None = None


def load_book_b_live_capital_basis(
    state_dir: Path,
) -> BookBLiveCapitalBasis:
    """Return the first-batch basis or require a settled post-fill receipt."""
    root = Path(state_dir)
    settlement = load_latest_book_b_live_settlement(root)
    if settlement is not None:
        if open_execution_plan_ids(root):
            raise ValueError("LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED")
        if settlement.get("ownership_head_sha256") != ownership_head_sha256(root):
            raise ValueError("LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED")
        try:
            settled_nav = float(settlement["settled_nav"])
            exposure = float(settlement["current_open_exposure"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("LIVE_BOOK_B_SETTLEMENT_INVALID") from exc
        if (
            not math.isfinite(settled_nav)
            or settled_nav <= 0
            or not math.isfinite(exposure)
            or exposure < 0
        ):
            raise ValueError("LIVE_BOOK_B_SETTLEMENT_INVALID")
        return BookBLiveCapitalBasis(
            settled_nav=settled_nav,
            current_open_exposure=exposure,
            source="broker_reconciled_book_b_nav",
            receipt_sha256=str(settlement.get("settlement_sha256") or "") or None,
        )
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
        events_by_plan: dict[str, list[dict]] = {}
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
            if filled_shares > 0:
                raise ValueError("LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED")
            plan_id = str(event.get("plan_id") or receipt.get("plan_id") or "").strip()
            if not plan_id:
                raise ValueError("LIVE_BOOK_B_EXECUTION_EVIDENCE_INVALID")
            events_by_plan.setdefault(plan_id, []).append(event)
        for plan_id, plan_events in events_by_plan.items():
            latest = plan_events[-1]
            receipt = latest.get("receipt")
            receipt = receipt if isinstance(receipt, dict) else {}
            latest_state = str(
                latest.get("state") or receipt.get("state") or ""
            ).strip().lower()
            if latest_state in _SETTLEMENT_REQUIRING_STATES:
                raise ValueError("LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED")
            had_unsettled_boundary = any(
                str(
                    event.get("state")
                    or (
                        event.get("receipt", {}).get("state")
                        if isinstance(event.get("receipt"), dict)
                        else ""
                    )
                    or ""
                ).strip().lower() in _SETTLEMENT_REQUIRING_STATES
                for event in plan_events[:-1]
            )
            if not had_unsettled_boundary:
                continue
            if not (
                _prior_day_absence_event_proven(plan_id, plan_events)
                or _mapped_zero_fill_terminal_event_proven(plan_id, plan_events)
                or _pre_entrust_zero_fill_terminal_event_proven(
                    plan_id, plan_events
                )
            ):
                raise ValueError("LIVE_BOOK_B_SETTLED_NAV_RECONCILE_REQUIRED")
    return BookBLiveCapitalBasis(
        settled_nav=_BOOK_B_INITIAL_CAPITAL,
        current_open_exposure=0.0,
        source="initial_book_b_capital",
        receipt_sha256=None,
    )


def _event_chain_proven(
    plan_id: str,
    plan_events: list[dict],
) -> bool:
    previous_hash: str | None = None
    expected_sequence = 1
    for event in plan_events:
        if event.get("plan_id") != plan_id:
            return False
        if event.get("sequence") != expected_sequence:
            return False
        if event.get("previous_hash") != previous_hash:
            return False
        claimed_hash = str(event.get("event_hash") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", claimed_hash):
            return False
        canonical = dict(event)
        canonical.pop("event_hash", None)
        recomputed = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        if recomputed != claimed_hash:
            return False
        previous_hash = claimed_hash
        expected_sequence += 1
    return True


def _prior_day_absence_event_proven(
    plan_id: str,
    plan_events: list[dict],
) -> bool:
    """Verify one hash-chained terminal broker-absence transition."""
    parts = plan_id.split(":")
    if len(parts) < 4 or parts[0] not in {"book-b", "book-b-canary"}:
        return False
    trade_date = parts[1]
    if (
        not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date)
        or not _event_chain_proven(plan_id, plan_events)
    ):
        return False
    latest = plan_events[-1]
    receipt = latest.get("receipt")
    if not isinstance(receipt, dict):
        return False
    proof = receipt.get("locator_proof")
    if not isinstance(proof, dict):
        return False
    order_filter = proof.get("historical_order_date_filter")
    deal_filter = proof.get("historical_deal_date_filter")
    filters = (order_filter, deal_filter)
    return (
        latest.get("kind") == "reconcile_receipt"
        and latest.get("state") == "rejected"
        and receipt.get("state") == "rejected"
        and receipt.get("absence_proof") is True
        and receipt.get("account_binding") == "proven"
        and receipt.get("filled_shares") == 0
        and receipt.get("reason") == "prior_day_broker_absence_proven"
        and receipt.get("event_id") == latest.get("event_id")
        and proof.get("exact_order_match_count") == 0
        and proof.get("exact_deal_match_count") == 0
        and proof.get("target_holding_shares") == 0
        and all(isinstance(item, dict) for item in filters)
        and all(item.get("applied") is True for item in filters)
        and all(item.get("start") == trade_date for item in filters)
        and all(item.get("end") == trade_date for item in filters)
    )


def _mapped_zero_fill_terminal_event_proven(
    plan_id: str,
    plan_events: list[dict],
) -> bool:
    """Accept a real mapped order only after a zero-fill broker terminal."""
    if not _event_chain_proven(plan_id, plan_events):
        return False
    latest = plan_events[-1]
    receipt = latest.get("receipt")
    if not isinstance(receipt, dict):
        return False
    state = str(latest.get("state") or receipt.get("state") or "").strip().lower()
    order_id = str(receipt.get("broker_order_id") or "").strip()
    strategy_id = str(receipt.get("broker_strategy_id") or "").strip()
    if receipt.get("reason") == "native_prior_day_zero_fill_order_expired":
        # Older code manufactured CANCELLED from an ACCEPTED/已报 historical
        # row. That inference is not a broker terminal and must never release
        # capital, even if a legacy event was already persisted.
        return False
    mapped_submit = any(
        isinstance(event.get("receipt"), dict)
        and event.get("kind") == "submit_receipt"
        and event["receipt"].get("receipt_mapping") is True
        and event["receipt"].get("broker_order_id") == order_id
        and event["receipt"].get("broker_strategy_id") == strategy_id
        for event in plan_events[:-1]
    )
    durable_claims = [
        event
        for event in plan_events[:-1]
        if event.get("kind") == "durable_claim"
        and isinstance(event.get("receipt"), dict)
        and int(event["receipt"].get("attempt") or 0) >= 1
    ]
    proven_claim_ids = {
        str(event["receipt"].get("submit_claim_id") or "").strip()
        for event in durable_claims
        if _complete_submit_claim_event_proven(event)
    }
    recovered_mapped_submit = any(
        claim_id
        and any(
            event.get("kind") == "submit_unknown"
            and isinstance(event.get("receipt"), dict)
            and event["receipt"].get("submit_chain_uncertain") is True
            and event["receipt"].get("submit_claim_id") == claim_id
            and int(event["receipt"].get("attempt") or 0) >= 1
            for event in plan_events[:-1]
        )
        and any(
            event.get("kind") == "reconcile_receipt"
            and event.get("state") in {"acknowledged", "partial"}
            and isinstance(event.get("receipt"), dict)
            and event["receipt"].get("receipt_mapping") is True
            and event["receipt"].get("broker_order_id") == order_id
            and event["receipt"].get("broker_strategy_id") == strategy_id
            and event["receipt"].get("submit_claim_id") == claim_id
            for event in plan_events[:-1]
        )
        for claim_id in proven_claim_ids
    )
    return (
        state in {"cancelled", "rejected"}
        and latest.get("kind") in {
            "submit_receipt",
            "reconcile_receipt",
            "cancel_receipt",
            "cancel_claim_reconciled",
        }
        and receipt.get("state") == state
        and receipt.get("broker_status") == state
        and receipt.get("receipt_mapping") is True
        and receipt.get("account_binding") in {"proven", "bound"}
        and receipt.get("filled_shares") == 0
        and int(receipt.get("attempt") or 0) >= 1
        and bool(order_id)
        and bool(strategy_id)
        and receipt.get("event_id") == latest.get("event_id")
        and (mapped_submit or recovered_mapped_submit)
    )


def _complete_submit_claim_event_proven(event: dict) -> bool:
    """Require the durable claim id and the complete pre-submit baseline."""
    receipt = event.get("receipt")
    details = event.get("details")
    if not isinstance(receipt, dict) or not isinstance(details, dict):
        return False
    claim_id = str(receipt.get("submit_claim_id") or "").strip()
    proof = receipt.get("locator_proof")
    if not claim_id or not isinstance(proof, dict):
        return False
    baseline_ids = proof.get("baseline_order_ids")
    baseline_count = proof.get("baseline_order_count")
    observed_at = str(proof.get("baseline_observed_at") or "").strip()
    try:
        parsed_observed_at = datetime.fromisoformat(
            observed_at.replace("Z", "+00:00")
        )
    except ValueError:
        return False
    return bool(
        details.get("claim_id") == claim_id
        and isinstance(details.get("requested_shares"), int)
        and details["requested_shares"] > 0
        and isinstance(baseline_ids, list)
        and all(str(order_id or "").strip() for order_id in baseline_ids)
        and isinstance(baseline_count, int)
        and baseline_count == len(baseline_ids)
        and parsed_observed_at.tzinfo is not None
        and proof.get("baseline_order_readback_mode")
            in {"strict_confidence", "bounded_known_status_zero_fill"}
        and isinstance(proof.get("baseline_bounded_low_confidence_headers"), list)
        and isinstance(proof.get("baseline_targeted_order_reread_used"), bool)
        and proof.get("comparison") == "code+side+price+quantity+new_order_id"
    )


def _pre_entrust_zero_fill_terminal_event_proven(
    plan_id: str,
    plan_events: list[dict],
) -> bool:
    """Accept only a hash-chained broker rejection before order entrust."""
    if not _event_chain_proven(plan_id, plan_events):
        return False
    latest = plan_events[-1]
    receipt = latest.get("receipt")
    if not isinstance(receipt, dict):
        return False
    return (
        latest.get("kind") == "submit_receipt"
        and latest.get("state") == "rejected"
        and receipt.get("state") == "rejected"
        and receipt.get("broker_status") == "rejected"
        and receipt.get("reason") == "pre_entrust_rejected"
        and receipt.get("receipt_mapping") is True
        and receipt.get("account_binding") in {"proven", "bound"}
        and receipt.get("filled_shares") == 0
        and receipt.get("submit_chain_uncertain") is False
        and not receipt.get("broker_order_id")
        and not receipt.get("broker_strategy_id")
        and int(receipt.get("attempt") or 0) == 1
        and receipt.get("event_id") == latest.get("event_id")
    )


def _intent_datetime(value: object, *, required: bool) -> datetime | None:
    if value in (None, ""):
        if required:
            raise ValueError("LIVE_PLAN_INTENT_DATETIME_MISSING")
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("LIVE_PLAN_INTENT_DATETIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError("LIVE_PLAN_INTENT_DATETIME_INVALID")
    return parsed


def _trade_plan_from_intent(
    payload: dict,
    *,
    require_canary: bool = False,
) -> TradePlan:
    raw = payload.get("plan")
    if not isinstance(raw, dict):
        raise ValueError("LIVE_PLAN_INTENT_INVALID")
    try:
        plan = TradePlan(
            plan_id=str(raw["plan_id"]),
            strategy_run_id=str(raw["strategy_run_id"]),
            snapshot_ref=str(raw["snapshot_ref"]),
            strategy_sha=str(raw["strategy_sha"]),
            trade_date=str(raw["trade_date"]),
            book=str(raw["book"]),
            logical_account_id=str(raw["logical_account_id"]),
            environment=str(raw["environment"]),
            code=str(raw["code"]),
            name=str(raw["name"]),
            side=str(raw["side"]),
            shares=int(raw["shares"]),
            limit_price=float(raw["limit_price"]),
            basket_price=(
                float(raw["basket_price"])
                if raw.get("basket_price") is not None
                else None
            ),
            market_guard_status=str(raw["market_guard_status"]),
            created_at=_intent_datetime(raw["created_at"], required=True),
            recovery_deadline=_intent_datetime(
                raw["recovery_deadline"], required=True
            ),
            owned_lot_id=raw.get("owned_lot_id"),
            submit_not_before=_intent_datetime(
                raw.get("submit_not_before"), required=False
            ),
            price_rule=str(raw.get("price_rule") or ""),
            market_guard_required=raw.get("market_guard_required") is True,
            market_guard_observed_at=_intent_datetime(
                raw.get("market_guard_observed_at"), required=False
            ),
            market_guard_latest_price=(
                float(raw["market_guard_latest_price"])
                if raw.get("market_guard_latest_price") is not None
                else None
            ),
            market_guard_down_price=(
                float(raw["market_guard_down_price"])
                if raw.get("market_guard_down_price") is not None
                else None
            ),
            allocation_proof_hash=raw.get("allocation_proof_hash"),
            sell_authorized=raw.get("sell_authorized") is True,
            sell_reason=raw.get("sell_reason"),
            sell_decision_phase=raw.get("sell_decision_phase"),
            sell_decision_at=_intent_datetime(
                raw.get("sell_decision_at"), required=False
            ),
            sell_block_reason=raw.get("sell_block_reason"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("LIVE_PLAN_"):
            raise
        raise ValueError("LIVE_PLAN_INTENT_INVALID") from exc
    if (
        payload.get("schema_version") != 1
        or payload.get("plan_hash") != plan.plan_hash
        or plan.book != "B"
        or plan.environment != "live"
        or plan.logical_account_id != "primary"
        or (
            payload.get("plan_id") not in (None, plan.plan_id)
            if require_canary
            else payload.get("plan_id") != plan.plan_id
        )
        or not plan.plan_id.startswith(
            "book-b-canary:" if require_canary else "book-b:"
        )
    ):
        raise ValueError("LIVE_PLAN_INTENT_BINDING_MISMATCH")
    return plan


def _trade_plan_from_canary_intent(payload: dict) -> TradePlan:
    return _trade_plan_from_intent(payload, require_canary=True)


def _plan_intent_path(state_dir: Path, plan_id: str) -> Path:
    digest = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:24]
    return Path(state_dir) / "plan_intents" / f"{digest}.json"


@contextmanager
def _plan_intent_lock(state_dir: Path):
    intent_dir = Path(state_dir) / "plan_intents"
    intent_dir.mkdir(parents=True, exist_ok=True)
    handle = (intent_dir / ".lock").open("a+", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _plan_semantics(plan: TradePlan) -> dict:
    payload = plan.canonical_payload()
    # These timestamps record when the first process materialized the intent.
    # Every economic, evidence and safety field must remain byte-equivalent.
    payload.pop("created_at", None)
    payload.pop("submit_not_before", None)
    return payload


def _bind_durable_plan_intents(
    config: BookBLiveMorningConfig,
    plans: list[TradePlan],
) -> list[TradePlan]:
    """Persist each immutable live plan before prepare/submit and reuse it.

    A later process must reconcile with the original plan hash rather than
    regenerating ``created_at`` and accidentally creating a conflicting plan.
    """
    store = ExecutionStore(Path(config.state_dir) / "events.jsonl")
    bound: list[TradePlan] = []
    with account_writer_lock(
        Path(config.state_dir) / "account_writer_locks",
        config.logical_account_id,
    ):
        with _plan_intent_lock(config.state_dir):
            for generated in plans:
                path = _plan_intent_path(config.state_dir, generated.plan_id)
                if not path.exists():
                    if store.current(generated.plan_id) is not None:
                        raise ValueError("LIVE_PLAN_INTENT_MISSING")
                    _write_json_atomic(
                        path,
                        {
                            "schema_version": 1,
                            "plan_id": generated.plan_id,
                            "plan_hash": generated.plan_hash,
                            "plan": generated.canonical_payload(),
                        },
                    )
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ValueError("LIVE_PLAN_INTENT_INVALID") from exc
                if not isinstance(payload, dict):
                    raise ValueError("LIVE_PLAN_INTENT_INVALID")
                persisted = _trade_plan_from_intent(payload)
                if (
                    payload.get("schema_version") != 1
                    or payload.get("plan_id") != persisted.plan_id
                    or _plan_semantics(persisted) != _plan_semantics(generated)
                ):
                    raise ValueError("LIVE_PLAN_INTENT_BINDING_MISMATCH")
                current = store.current(persisted.plan_id)
                if current is not None and current.plan_hash != persisted.plan_hash:
                    raise ValueError("LIVE_PLAN_INTENT_EVENT_HASH_MISMATCH")
                bound.append(persisted)
    return bound


def read_durable_live_plan_intent(payload: dict) -> TradePlan:
    """Public lifecycle reader for one canonical live intent capsule."""
    return _trade_plan_from_intent(payload)


def bind_durable_live_plan_intents(
    state_dir: Path,
    plans: list[TradePlan],
) -> list[TradePlan]:
    """Public lifecycle writer using the morning seam's exact intent contract."""
    return _bind_durable_plan_intents(
        BookBLiveMorningConfig(
            trade_date="",
            freeze_path=Path("unused"),
            allocation_facts_path=Path("unused"),
            state_dir=Path(state_dir),
        ),
        plans,
    )


def _restore_durable_plan_for_row(
    config: BookBLiveMorningConfig,
    row: dict,
    *,
    strategy_sha: str,
) -> TradePlan | None:
    plan_id = f"book-b:{config.trade_date}:{row.get('code')}:BUY"
    store = ExecutionStore(Path(config.state_dir) / "events.jsonl")
    current = store.current(plan_id)
    path = _plan_intent_path(config.state_dir, plan_id)
    if current is None and not path.is_file():
        return None
    if not path.is_file():
        raise ValueError("LIVE_PLAN_INTENT_MISSING")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("LIVE_PLAN_INTENT_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("LIVE_PLAN_INTENT_INVALID")
    persisted = _trade_plan_from_intent(payload)
    if current is not None and current.plan_hash != persisted.plan_hash:
        raise ValueError("LIVE_PLAN_INTENT_EVENT_HASH_MISMATCH")

    reconstruction_row = dict(row)
    reconstruction_row["mode_exec_planned_shares"] = persisted.shares
    reconstruction_row["allocation_proof_hash"] = persisted.allocation_proof_hash
    reconstruction_row["submit_not_before"] = (
        persisted.submit_not_before.isoformat()
        if persisted.submit_not_before is not None
        else None
    )
    reconstruction_row.update({
        "market_guard_required": persisted.market_guard_required,
        "market_guard_status": persisted.market_guard_status,
        "market_price": persisted.market_guard_latest_price,
        "down_price": persisted.market_guard_down_price,
        "market_observed_at": (
            persisted.market_guard_observed_at.isoformat()
            if persisted.market_guard_observed_at is not None
            else None
        ),
    })
    reconstructed = trade_plan_from_frozen_row(
        reconstruction_row,
        environment="live",
        logical_account_id=config.logical_account_id,
        strategy_sha=strategy_sha,
        now=persisted.created_at,
        side="BUY",
        recovery_deadline=persisted.recovery_deadline,
    )
    if reconstructed.plan_hash != persisted.plan_hash:
        raise ValueError("LIVE_PLAN_INTENT_FREEZE_MISMATCH")
    return persisted


def _materialize_or_restore_plans(
    config: BookBLiveMorningConfig,
    rows: list[dict],
    *,
    strategy_sha: str,
    allocation: BookBAllocationFacts,
    now: datetime,
    refresh_market_guard: Callable[[dict], dict] | None = None,
    policy_evidence: dict | None = None,
    check_new_plan: Callable[[TradePlan, dict], bool] | None = None,
) -> list[TradePlan]:
    restored_by_id: dict[str, TradePlan] = {}
    new_rows: list[dict] = []
    for row in rows:
        restored = _restore_durable_plan_for_row(
            config,
            row,
            strategy_sha=strategy_sha,
        )
        if restored is None:
            materialized_row = dict(row)
            if policy_evidence is not None:
                # Selection is made on the entire original batch first. A
                # skipped/unrepresentable slot stays cash, with no promotion.
                sized = policy_evidence["rows_by_code"].get(str(row.get("code")))
                if sized is None:
                    continue
                materialized_row.update(sized)
            if refresh_market_guard is not None:
                guard = refresh_market_guard(dict(row))
                if not isinstance(guard, dict):
                    raise ValueError("LIVE_MARKET_GUARD_REFRESH_INVALID")
                allowed = {
                    "market_guard_required",
                    "market_guard_status",
                    "market_price",
                    "down_price",
                    "market_observed_at",
                }
                if set(guard) - allowed:
                    raise ValueError("LIVE_MARKET_GUARD_REFRESH_UNSCOPED")
                materialized_row.update(guard)
            new_rows.append(materialized_row)
        else:
            restored_by_id[restored.plan_id] = restored
    new_plans = plans_from_frozen_rows(
        new_rows,
        environment="live",
        logical_account_id=config.logical_account_id,
        strategy_sha=strategy_sha,
        now=now,
        side="BUY",
        allocation=allocation,
    ) if new_rows else []
    if check_new_plan is not None and policy_evidence is not None:
        new_plans = [plan for plan in new_plans
                     if check_new_plan(plan, policy_evidence["by_code"][plan.code])]
    new_by_id = {
        plan.plan_id: plan
        for plan in _bind_durable_plan_intents(config, new_plans)
    }
    if policy_evidence is not None:
        for plan in new_by_id.values():
            bind_plan_audit(config.state_dir, plan, {
                **policy_evidence["by_code"][plan.code],
                "base_allocation": policy_evidence["base_allocation"],
                "allocation_capsule_sha256": policy_evidence["allocation_capsule_sha256"],
                "freeze_sha256": frozen_rows_digest(rows),
            })
    return [
        restored_by_id.get(
            f"book-b:{config.trade_date}:{row.get('code')}:BUY"
        )
        or new_by_id.get(f"book-b:{config.trade_date}:{row.get('code')}:BUY")
        for row in rows
        if f"book-b:{config.trade_date}:{row.get('code')}:BUY" in restored_by_id
        or f"book-b:{config.trade_date}:{row.get('code')}:BUY" in new_by_id
    ]


def _policy_allocation(rows: list[dict], allocation: BookBAllocationFacts,
                       decision: dict, risk: AccountRiskReceipt) -> tuple[BookBAllocationFacts, dict]:
    """Size only original allocator slots, retaining each slot's cash ceiling."""
    error = allocation.validation_error()
    if error:
        raise ValueError(error)
    evidence = {str(row["code"]): buy_cap(decision, risk, str(row["code"]), allocation.deploy_factor)
                for row in rows}
    factor = min([allocation.deploy_factor, risk.deploy_factor] +
                 [item["scale"] for item in evidence.values() if not item["skip"]])
    effective = replace(allocation, deploy_factor=factor)
    sized = []
    if any(not item["skip"] for item in evidence.values()):
        try:
            if any(row.get("mode_exec_planned_shares") in (None, "") for row in rows):
                base_rows = allocate_frozen_rows(rows, allocation)
            else:
                validate_allocation_rows(rows, allocation)
                base_rows = [dict(row) for row in rows]
        except ValueError as exc:
            if str(exc) != "ALLOCATION_EMPTY":
                raise
            base_rows = []
        for row in base_rows:
            adjustment = evidence[str(row["code"])]
            if adjustment["skip"]:
                continue
            ratio = adjustment["effective_deploy_factor"] / allocation.deploy_factor
            if ratio == 1:
                planned = [dict(row)]
            else:
                from .book_b_pricing import initial_limit_price

                price = initial_limit_price(row.get("open"), row.get("basket_price"))
                candidate = {**row, "execution_price": price}
                target = float(row["mode_exec_target_weight"]) * ratio
                planned = plan_board_lot_orders(
                    [candidate], nav=allocation.settled_nav, cash_limit=effective.cash_limit,
                    fee_rate=allocation.fee_rate, price_key="execution_price", max_candidates=1,
                    max_batch_ratio=effective.batch_ratio * effective.deploy_factor,
                    weight_resolver=lambda _subset, weight=target: [weight],
                    per_position_cash_cap=int(row["mode_exec_planned_shares"]) * price *
                                          (1 + allocation.fee_rate) * ratio,
                )
            for item in planned:
                item.pop("allocation_proof_hash", None)
                sized.append(item)
    return effective, {"rows_by_code": {str(row["code"]): row for row in sized},
                       "by_code": evidence, "base_allocation": allocation.canonical_payload()}


def reconcile_open_book_b_plans(
    state_dir: Path,
    *,
    trade_date: str,
    execute: Callable[[TradePlan], ExecutionReceipt],
) -> tuple[dict, ...]:
    """Advance only already-submitted durable plans through broker reconcile."""
    root = Path(state_dir)
    intent_dir = root / "plan_intents"
    if not intent_dir.is_dir():
        return ()
    store = ExecutionStore(root / "events.jsonl")
    open_states = {
        ExecutionState.CLAIMED,
        ExecutionState.UNKNOWN,
        ExecutionState.SUBMITTED,
        ExecutionState.ACKNOWLEDGED,
        ExecutionState.PARTIAL,
        ExecutionState.RECONCILING,
    }
    receipts: list[dict] = []
    for path in sorted(intent_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("LIVE_PLAN_INTENT_INVALID") from exc
        if not isinstance(payload, dict):
            raise ValueError("LIVE_PLAN_INTENT_INVALID")
        plan = _trade_plan_from_intent(payload)
        if plan.trade_date > trade_date:
            continue
        current = store.current(plan.plan_id)
        if current is None or current.state not in open_states:
            continue
        if current.plan_hash != plan.plan_hash:
            raise ValueError("LIVE_PLAN_INTENT_EVENT_HASH_MISMATCH")
        reconciled = execute(plan)
        durable = store.current(plan.plan_id)
        if durable is None or durable.event_id != reconciled.event_id:
            raise ValueError("LIVE_OPEN_PLAN_RECONCILE_NOT_DURABLE")
        receipts.append(reconciled.as_dict())
    return tuple(receipts)


def _plan_requires_prepare(config: BookBLiveMorningConfig, plan: TradePlan) -> bool:
    current = ExecutionStore(Path(config.state_dir) / "events.jsonl").current(
        plan.plan_id
    )
    return current is None or current.state in {
        ExecutionState.PLANNED,
        ExecutionState.VALIDATED,
        ExecutionState.PREPARED,
    }


def _uncertain_execution_plan_ids(state_dir: Path) -> tuple[str, ...]:
    """Prepared/unclaimed intents reserve plans but are not UNKNOWN effects."""
    store = ExecutionStore(Path(state_dir) / "events.jsonl")
    return tuple(plan_id for plan_id in open_execution_plan_ids(state_dir)
                 if (receipt := store.current(plan_id)) is not None
                 and receipt.state in {ExecutionState.CLAIMED, ExecutionState.UNKNOWN,
                     ExecutionState.SUBMITTED, ExecutionState.ACKNOWLEDGED,
                     ExecutionState.PARTIAL, ExecutionState.RECONCILING})


def reconcile_prior_day_canary_unknowns(
    state_dir: Path,
    *,
    trade_date: str,
    execute: Callable[[TradePlan], ExecutionReceipt],
) -> tuple[dict, ...]:
    """Advance prior canary UNKNOWN plans through read-only broker reconcile.

    The durable execution store decides the transition.  Calling ``execute``
    for an existing UNKNOWN never enters the submit path; this helper then
    requires a hash-chained terminal absence receipt before returning.
    """
    root = Path(state_dir)
    store = ExecutionStore(root / "events.jsonl")
    intent_dir = root / "canary_intents"
    if not intent_dir.is_dir():
        return ()
    receipts: list[dict] = []
    for path in sorted(intent_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("LIVE_PRIOR_CANARY_INTENT_INVALID") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("plan"), dict):
            continue
        plan = _trade_plan_from_canary_intent(payload)
        current = store.current(plan.plan_id)
        if current is None or current.state not in {
            ExecutionState.UNKNOWN,
            ExecutionState.RECONCILING,
        }:
            continue
        if plan.trade_date >= trade_date:
            continue
        if current.filled_shares != 0 or current.broker_order_id:
            raise ValueError("LIVE_PRIOR_UNKNOWN_RECONCILE_REQUIRED")
        reconciled = execute(plan)
        durable = store.current(plan.plan_id)
        if (
            reconciled.state != ExecutionState.REJECTED
            or reconciled.absence_proof is not True
            or reconciled.reason != "prior_day_broker_absence_proven"
            or durable is None
            or durable.event_id != reconciled.event_id
            or durable.absence_proof is not True
        ):
            raise ValueError("LIVE_PRIOR_UNKNOWN_RECONCILE_REQUIRED")
        receipts.append(reconciled.as_dict())
    return tuple(receipts)


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
    *,
    restoring_only: bool = False,
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
    if str(payload.get("source") or "").strip().lower() not in {
        "foundersc_reconcile",
        "foundersc_native_app",
    }:
        raise ValueError("LIVE_ALLOCATION_SOURCE_UNPROVEN")
    capital_basis_source = str(payload.get("capital_basis_source") or "").strip()
    if capital_basis_source not in {
        "initial_book_b_capital",
        "broker_reconciled_book_b_nav",
    }:
        raise ValueError("LIVE_ALLOCATION_CAPITAL_BASIS_UNPROVEN")
    capital_basis_receipt = str(
        payload.get("capital_basis_receipt_sha256") or ""
    ).strip().lower()
    if capital_basis_source == "broker_reconciled_book_b_nav" and not re.fullmatch(
        r"[0-9a-f]{64}", capital_basis_receipt
    ):
        raise ValueError("LIVE_ALLOCATION_CAPITAL_BASIS_RECEIPT_UNPROVEN")
    if capital_basis_source == "broker_reconciled_book_b_nav":
        settlement = load_latest_book_b_live_settlement(config.state_dir)
        if (
            settlement is None
            or capital_basis_receipt
            != str(settlement.get("settlement_sha256") or "").lower()
            or (_uncertain_execution_plan_ids(config.state_dir) if restoring_only
                else open_execution_plan_ids(config.state_dir))
            or settlement.get("ownership_head_sha256")
            != ownership_head_sha256(config.state_dir)
            or payload.get("settled_nav") != settlement.get("settled_nav")
            or payload.get("current_open_exposure")
            != settlement.get("current_open_exposure")
        ):
            raise ValueError("LIVE_ALLOCATION_CAPITAL_BASIS_RECEIPT_MISMATCH")
    if capital_basis_source == "initial_book_b_capital" and capital_basis_receipt:
        raise ValueError("LIVE_ALLOCATION_CAPITAL_BASIS_RECEIPT_UNEXPECTED")
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


def write_book_b_live_morning_receipt(
    config: BookBLiveMorningConfig,
    receipt: BookBLiveMorningReceipt,
) -> None:
    """Persist the final enriched receipt after wrapper-owned reconciliation."""
    _write_receipt(config, receipt)


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
    form_neutralized = bool(
        readback.get("form_closed") is True
        or readback.get("form_cleared") is True
    )
    if not form_neutralized:
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
        "form_closed": readback.get("form_closed") is True,
        "form_cleared": readback.get("form_cleared") is True,
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
    refresh_market_guard: Callable[[dict], dict] | None = None,
    wait_for_dated_freeze: Callable[[], dict] | None = None,
    prepare_only: Callable[[TradePlan], BrokerReceipt] | None = None,
    wait_for_submit_window: Callable[[datetime], None] | None = None,
    wait_for_reconcile: Callable[[], None] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    risk_provider: Callable[[datetime], AccountRiskReceipt] | None = None,
    account_snapshot_provider: Callable[[], dict] | None = None,
    trading_dates_provider: Callable[[datetime], list[str]] | None = None,
    review_rendezvous: Callable[[dict], dict] | None = None,
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
    environment_restoration: dict | None = None
    preparation_receipts: list[dict] = []
    receipt: BookBLiveMorningReceipt
    restore_failure: str | None = None
    policy_consumptions: list[dict] = []
    open_reconciliations: tuple[dict, ...] = ()
    review_receipt: dict | None = None
    review_requested_at: datetime | None = None
    snapshot_cache: dict | None = None
    snapshot_ownership_head: str | None = None

    def cached_snapshot() -> dict:
        nonlocal snapshot_cache, snapshot_ownership_head
        clock = now()
        head = ownership_head_sha256(config.state_dir)
        if snapshot_cache is not None and snapshot_ownership_head == head:
            try:
                return validate_broker_account_snapshot(snapshot_cache, trade_date=config.trade_date, now=clock)
            except ValueError:
                snapshot_cache = None
        if account_snapshot_provider is None:
            raise ValueError("LIVE_RISK_RECONCILED_CURRENT_NAV_REQUIRED")
        snapshot = validate_broker_account_snapshot(account_snapshot_provider(),
                                                    trade_date=config.trade_date, now=now())
        snapshot_cache, snapshot_ownership_head = snapshot, head
        return snapshot

    def execute_plan(plan: TradePlan) -> ExecutionReceipt:
        nonlocal snapshot_cache
        try:
            return execute(plan)
        finally:
            # Any execution may have changed broker state, including a lost
            # reply. Do not reuse a pre-action NAV at the next risk boundary.
            snapshot_cache = None

    def support() -> tuple[dict, AccountRiskReceipt]:
        clock = now()
        risk = risk_provider(clock) if risk_provider is not None else evaluate_live_risk(
            config.state_dir, now=clock,
            account_snapshot_provider=cached_snapshot if account_snapshot_provider is not None else None,
            trading_dates_provider=trading_dates_provider,
            receipt_root=config.policy_root.parent / "account_risk",
            now_provider=now,
        )
        decision = read_policy(config.policy_root, now())
        if (review_receipt is not None and review_receipt.get("status") == "timed_out"
                and review_requested_at is not None and decision.get("status") == "validated"
                and datetime.fromisoformat(decision["record"]["decision"]["as_of"].replace("Z", "+00:00")) < review_requested_at):
            decision = {"status": "neutral", "book": "B", "runtime": "live",
                        "reason": "LIVE_REVIEW_TIMEOUT_NEUTRAL_FALLBACK", "decision_id": None}
        return decision, risk

    def allow_new_risk(plan: TradePlan, original: dict | None = None) -> bool:
        if config.policy_root is None or not _plan_requires_prepare(config, plan):
            return True
        audit = original if original is not None else read_plan_audit(config.state_dir, plan)
        prior_factor = float(audit["effective_deploy_factor"]) if audit else 1.0
        decision, risk = support()
        adjustment = buy_cap(decision, risk, plan.code, allocation.deploy_factor)
        allowed = not adjustment["skip"] and adjustment["effective_deploy_factor"] >= prior_factor
        policy_consumptions.append({"plan_id": plan.plan_id, "plan_hash": plan.plan_hash,
                                    "stage": "new_intent" if original is not None else "before_action",
                                    "allowed": allowed, **adjustment})
        return allowed

    try:
        try:
            if preflight is not None:
                preflight_attempted = True
                environment_receipt = preflight()
                if str(environment_receipt.get("environment") or "").lower() != "live":
                    raise ValueError("LIVE_ENVIRONMENT_NOT_PROVEN")
            if config.policy_root is not None:
                open_reconciliations = reconcile_open_book_b_plans(
                    config.state_dir, trade_date=config.trade_date, execute=execute_plan,
                )
                if _uncertain_execution_plan_ids(config.state_dir):
                    raise ValueError("LIVE_BOOK_B_OPEN_EXECUTION_RECONCILE_REQUIRED")
            allocation: BookBAllocationFacts | None = None
            if read_allocation_facts is not None and config.policy_root is None:
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
                    all_restoring = False
                    if config.policy_root is not None:
                        all_restoring = all(_restore_durable_plan_for_row(
                            config, row, strategy_sha=str(dated_freeze_receipt["strategy_sha"]),
                        ) is not None for row in rows)
                    if config.policy_root is not None and review_rendezvous is not None:
                        new_candidates = [row for row in rows if _restore_durable_plan_for_row(
                            config, row, strategy_sha=str(dated_freeze_receipt["strategy_sha"]),
                        ) is None]
                        if new_candidates:
                            current = now().astimezone(ZoneInfo("Asia/Shanghai"))
                            review_requested_at = current
                            if (current.hour, current.minute) < (11, 30):
                                deadline = current.replace(hour=11, minute=30, second=0, microsecond=0)
                            elif (13, 0) <= (current.hour, current.minute) < (14, 57):
                                deadline = current.replace(hour=14, minute=57, second=0, microsecond=0)
                            else:
                                deadline = current
                            request = {
                                "schema_version": "book-b-live-review-request.v1",
                                "book": "B", "runtime": "live", "trade_date": config.trade_date,
                                "freeze_path": str(config.freeze_path),
                                "freeze_sha256": dated_freeze_receipt["snapshot_sha256"],
                                "strategy_sha": dated_freeze_receipt["strategy_sha"],
                                "policy_root": str(config.policy_root),
                                "candidates": [dict(row) for row in new_candidates],
                                "requested_at": current.isoformat(), "entry_deadline": deadline.isoformat(),
                                "max_wait_seconds": min(120.0, max(0.0, (deadline - current).total_seconds()))
                                    if current.date().isoformat() == config.trade_date else 0.0,
                            }
                            review_receipt = review_rendezvous(request)
                            if not isinstance(review_receipt, dict):
                                raise ValueError("LIVE_REVIEW_RENDEZVOUS_RECEIPT_INVALID")
                            if now() >= deadline:
                                raise ValueError("LIVE_REVIEW_ENTRY_WINDOW_CLOSED")
                    if config.policy_root is not None and read_allocation_facts is not None and not all_restoring:
                        allocation_payload = read_allocation_facts()
                        allocation = _load_allocation(config, allocation_payload)
                        _write_json_atomic(config.allocation_facts_path, allocation_payload)
                    allocation = allocation or _load_allocation(config, restoring_only=all_restoring)
                    effective_allocation = allocation
                    policy_evidence = None
                    if config.policy_root is not None:
                        decision, risk = support()
                        effective_allocation, policy_evidence = _policy_allocation(rows, allocation, decision, risk)
                        capsule = json.loads(config.allocation_facts_path.read_text(encoding="utf-8"))
                        policy_evidence["allocation_capsule_sha256"] = capsule["allocation_capsule_sha256"]
                        policy_consumptions.extend({"code": code, "stage": "allocation", **evidence}
                                                   for code, evidence in policy_evidence["by_code"].items())
                    plans = _materialize_or_restore_plans(
                        config,
                        rows,
                        strategy_sha=str(dated_freeze_receipt["strategy_sha"]),
                        allocation=effective_allocation,
                        now=now(),
                        refresh_market_guard=refresh_market_guard,
                        policy_evidence=policy_evidence,
                        check_new_plan=allow_new_risk,
                    )
                    if prepare_only is not None:
                        preparation_receipts = [
                            _assert_prepare_only(plan, prepare_only(plan))
                            for plan in plans
                            if _plan_requires_prepare(config, plan) and allow_new_risk(plan)
                        ]
                    if plans and wait_for_submit_window is not None:
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
                        if not allow_new_risk(plan):
                            continue
                        execution_receipt = execute_plan(plan)
                        for _attempt in range(3):
                            needs_reconcile = (
                                execution_receipt.state
                                in {
                                    ExecutionState.CLAIMED,
                                    ExecutionState.UNKNOWN,
                                    ExecutionState.SUBMITTED,
                                    ExecutionState.ACKNOWLEDGED,
                                    ExecutionState.PARTIAL,
                                    ExecutionState.RECONCILING,
                                }
                                or execution_receipt.next_action
                                in {"reconcile", "reconcile_only"}
                            )
                            if not needs_reconcile:
                                break
                            if wait_for_reconcile is not None:
                                wait_for_reconcile()
                            execution_receipt = execute_plan(plan)
                        execution_receipts.append(execution_receipt)
                        if execution_receipt.state in {
                            ExecutionState.CLAIMED, ExecutionState.UNKNOWN, ExecutionState.SUBMITTED,
                            ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL, ExecutionState.RECONCILING,
                        }:
                            break
                    status, reason = _rollup(execution_receipts)
                    if not execution_receipts:
                        status, reason = "no_action", "NO_NEW_BUY_AFTER_POLICY_RISK"
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
                restored_environment = str(
                    restored.get("environment") or ""
                ).strip().lower()
                native_not_applicable = bool(
                    restored_environment == "not_applicable"
                    and str(restored.get("status") or "").strip()
                    == "native_environment_restore_not_applicable"
                    and str(restored.get("route") or "").strip()
                    == "native-app"
                )
                if restored_environment != "mock" and not native_not_applicable:
                    raise ValueError("MOCK_ENVIRONMENT_NOT_PROVEN")
                environment_restoration = dict(restored)
            except Exception as exc:
                restore_failure = f"ENVIRONMENT_RESTORE_FAILED:{exc}"
    if restore_failure is not None:
        receipt = replace(receipt, status="blocked", reason=restore_failure)
    if environment_receipt is not None:
        receipt = replace(receipt, preflight_receipt=environment_receipt)
    if environment_restoration is not None:
        receipt = replace(
            receipt,
            environment_restoration=environment_restoration,
        )
    receipt = replace(receipt, policy_consumptions=tuple(policy_consumptions),
                      open_plan_reconciliations=open_reconciliations or receipt.open_plan_reconciliations,
                      review_rendezvous=review_receipt)
    _write_receipt(config, receipt)
    return receipt


__all__ = [
    "BookBLiveCapitalBasis",
    "BookBLiveMorningConfig",
    "BookBLiveMorningReceipt",
    "bind_durable_live_plan_intents",
    "load_book_b_live_capital_basis",
    "read_durable_live_plan_intent",
    "reconcile_open_book_b_plans",
    "reconcile_prior_day_canary_unknowns",
    "run_book_b_live_morning",
    "write_book_b_live_morning_receipt",
]
