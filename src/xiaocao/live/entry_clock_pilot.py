"""User-authorized, fixed-size APP execution experiment inside the original Book B allocation."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .book_b_capital import digest
from .trading_execution import ExecutionStore, ExecutionState, account_writer_lock
from ..utils.atomic_files import atomic_write

active_child = ContextVar("book_b_pilot_child", default=None)
CHINA = ZoneInfo("Asia/Shanghai")
TAG = ":pilot0946"
AUTH = dict(
    schema=1,
    experiment="app-0946-split-v1",
    environment="app_server_simulation",
    logical_account_id="primary",
    shares=100,
    maximum_yuan=3000,
    maximum_assignments=10,
    drawdown_budget_yuan=286.09,
    earliest="09:46:00",
    latest="09:47:00",
    source="original_native_book_b_buy",
    activation="explicit_user_choice_split_original_20261128",
)
TERMINAL = {
    ExecutionState.FILLED,
    ExecutionState.CANCELLED,
    ExecutionState.REJECTED,
    ExecutionState.SKIPPED,
}


def authorized_child(plan):
    proof = active_child.get()
    return bool(proof and proof["child_hash"] == plan.plan_hash)


def root(state):
    return Path(state) / "entry_clock_pilot"


def write(path, value):
    atomic_write(
        path,
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode(),
        immutable=True,
    )


def windows(day):
    return tuple(
        datetime.fromisoformat(f"{day}T{t}+08:00")
        for t in (AUTH["earliest"], AUTH["latest"])
    )


def enable(state, stamp):
    path = root(state) / "authorization.json"
    if not path.exists():
        write(path, dict(scope=AUTH, enabled_at=stamp.isoformat()))
    if json.loads(path.read_bytes())["scope"] != AUTH:
        raise ValueError("pilot_authorization_mismatch")


def load_assignment(state, day):
    from .book_b_live_morning import read_durable_live_plan_intent

    path = root(state) / "assignments" / (day + ".json")
    if not path.exists():
        return None
    doc = json.loads(path.read_bytes())
    if (
        doc["sha256"] != digest({k: v for k, v in doc.items() if k != "sha256"})
        or doc["day"] != day
        or doc["scope"] != AUTH
    ):
        raise ValueError("pilot_assignment_mismatch")
    original = read_durable_live_plan_intent(doc["original"])
    early = read_durable_live_plan_intent(doc["early"])
    if (
        original.trade_date != day
        or original.side != "BUY"
        or original.shares < 200
        or early.canonical_payload()
        != replace(original, shares=original.shares - 100).canonical_payload()
        or doc["child_id"] != early.plan_id + TAG
        or not 0
        < original.limit_price * 100 * 1.0001
        <= doc["paired_cash_yuan"]
        <= AUTH["maximum_yuan"]
    ):
        raise ValueError("pilot_split_mismatch")
    return doc, original, early


def capsule(plan):
    return dict(
        schema_version=1,
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        plan=plan.canonical_payload(),
    )


def owned_rows(state):
    from .book_b_live_lifecycle import (
        _read_jsonl_strict,
        _validate_ownership_chain,
        _validate_execution_fill_coverage,
    )

    rows, _ = _validate_ownership_chain(
        _read_jsonl_strict(Path(state) / "book_b_ownership_evidence.jsonl")
    )
    _validate_execution_fill_coverage(Path(state), rows)
    from .book_b_live_lifecycle import load_execution_intents

    intents = load_execution_intents(state)
    return [
        {
            **r,
            "owned_lot_id": r["plan_id"]
            if r["side"] == "BUY"
            else r.get("owned_lot_id")
            or intents.get(r["plan_id"], {}).get("owned_lot_id"),
        }
        for r in rows
    ]


def can_allocate(state, day):
    folder = root(state)
    auth = folder / "authorization.json"
    if not auth.is_file() or (folder / "pause").exists():
        return False
    authorization = json.loads(auth.read_bytes())
    if authorization["scope"] != AUTH or authorization["enabled_at"][:10] > day:
        return False
    history = sorted((folder / "assignments").glob("*.json"))
    if len(history) >= AUTH["maximum_assignments"]:
        return False
    if not history:
        return True
    rows = owned_rows(state)
    store = ExecutionStore(Path(state) / "events.jsonl")
    for f in history:
        doc, _, _ = load_assignment(state, f.stem)
        result = folder / "dispositions" / f.name
        if f.stem >= day or not result.exists():
            return False
        disposition = json.loads(result.read_bytes())
        if (
            disposition.get("assignment") != doc["sha256"]
            or disposition.get("child_id") != doc["child_id"]
            or disposition.get("day") != f.stem
        ):
            return False
        pid = doc["child_id"]
        cur = store.current(pid)
        if cur is None:
            if disposition["kind"] != "no_submit":
                return False
            continue
        if (
            cur.state not in TERMINAL
            or cur.submit_chain_uncertain
            or cur.cancel_chain_uncertain
        ):
            return False
        if cur.broker_order_id:
            parent = store.current(doc["early"]["plan_id"])
            if (
                not parent
                or not parent.broker_order_id
                or parent.broker_order_id == cur.broker_order_id
            ):
                return False
        bought = sum(
            r["shares"] for r in rows if r["side"] == "BUY" and r["plan_id"] == pid
        )
        sold = sum(
            r["shares"]
            for r in rows
            if r["side"] == "SELL" and r.get("owned_lot_id") == pid
        )
        if cur.filled_shares != bought or bought != sold:
            return False
    return True


def split_before_binding(state, day, plans, clock, *, cash_budget=None):
    """Called under the original account fence, after full-batch allocation and policy proof."""
    from .book_b_live_morning import _plan_intent_path

    if not plans:
        return plans
    saved = load_assignment(state, day)
    if saved:
        _, original, early = saved
        result = []
        for plan in plans:
            if plan.plan_id == original.plan_id:
                if (
                    replace(
                        plan,
                        created_at=original.created_at,
                        submit_not_before=original.submit_not_before,
                        market_guard_observed_at=original.market_guard_observed_at,
                        market_guard_latest_price=original.market_guard_latest_price,
                    ).plan_hash
                    != original.plan_hash
                ):
                    raise ValueError("pilot_recovery_allocation_changed")
                plan = early
            result.append(plan)
        return result
    when = clock.astimezone(CHINA)
    if when.date().isoformat() != day or when.strftime("%H%M") >= "0931":
        return plans
    try:
        if not can_allocate(state, day) or cash_budget is None:
            return plans
        available = min(float(cash_budget()), AUTH["maximum_yuan"])
        if not 0 < available <= AUTH["maximum_yuan"]:
            return plans
    except (ValueError, OSError, KeyError, TypeError):
        # Prior pilot history cannot consume the ordinary allocation.
        return plans
    eligible = sorted(
        (
            p
            for p in plans
            if p.environment == "live"
            and p.logical_account_id == "primary"
            and p.shares >= 200
            and p.side == "BUY"
            and p.trade_date == day
            and p.plan_id == f"book-b:{day}:{p.code}:BUY"
            and 0 < p.limit_price * 100 * 1.0001 <= available
        ),
        key=lambda p: (p.created_at, p.code),
    )
    if not eligible:
        return plans
    original = eligible[0]
    if _plan_intent_path(state, original.plan_id).exists():
        raise ValueError("pilot_original_already_bound")
    early = replace(original, shares=original.shares - 100)
    doc = dict(
        day=day,
        scope=AUTH,
        paired_cash_yuan=available,
        original=capsule(original),
        early=capsule(early),
        child_id=original.plan_id + TAG,
        sealed_at=clock.isoformat(),
    )
    doc["sha256"] = digest(doc)
    write(root(state) / "assignments" / (day + ".json"), doc)
    return [early if p.plan_id == original.plan_id else p for p in plans]


def run_assigned(
    config,
    morning,
    *,
    clock,
    wait,
    shadow,
    allocation_facts,
    risk,
    guard,
    submission_scope,
    execute,
):
    """Called only by the original native owner, after its ordinary result is sealed.
    A missed or vetoed child leaves the withheld shares in cash."""
    from .book_b_live_morning import (
        _load_allocation,
        _plan_intent_path,
        _bind_durable_plan_intents,
        read_durable_live_plan_intent,
    )
    from .book_b_live_lifecycle import (
        blocking_open_execution_plan_ids,
        unresolved_prior_sell_codes,
    )
    from .inherited_execution import query_codes
    from .live_decision_support import (
        read_plan_audit,
        read_policy,
        buy_cap,
        bind_plan_audit,
    )
    from .kol_policy import review_publication_fence
    from .buy_guards import evaluate_buy_market_guard

    day = config.trade_date
    state = config.state_dir
    saved = load_assignment(state, day)
    if not saved:
        return None
    doc, original, early = saved
    pid = doc["child_id"]
    done = root(state) / "dispositions" / (day + ".json")
    if done.exists():
        return json.loads(done.read_bytes())

    def finish(kind, reason, **facts):
        result = dict(
            day=day,
            child_id=pid,
            kind=kind,
            reason=reason,
            assignment=doc["sha256"],
            at=clock().isoformat(),
            **facts,
        )
        write(done, result)
        return result

    store = ExecutionStore(state / "events.jsonl")
    start, end = windows(day)
    # Do not inherit time from recovery/old follow-ups or delay ordinary receipts.
    if morning.status not in ("completed", "unresolved"):
        return finish("no_submit", "original_batch_" + morning.status)
    observed = next(
        (
            r
            for r in morning.execution_receipts
            if r["plan_id"] == early.plan_id and r["plan_hash"] == early.plan_hash
        ),
        None,
    )
    if not observed:
        return finish("no_submit", "ordinary_leg_not_observed")
    if clock() < start:
        try:
            wait(start)
        except Exception as exc:
            return finish("no_submit", "pilot_wait_failed:" + type(exc).__name__)
    with account_writer_lock(state / "account_writer_locks", config.logical_account_id):
        if done.exists():
            return json.loads(done.read_bytes())
        current = store.current(pid)
        if current or _plan_intent_path(state, pid).exists():
            return finish(
                "reconcile_only",
                "existing_child",
                receipt=current.as_dict() if current else None,
            )
        try:
            if not start <= clock() < end or (root(state) / "pause").exists():
                raise ValueError("outside_or_paused")
            if (
                json.loads((root(state) / "authorization.json").read_bytes())["scope"]
                != AUTH
            ):
                raise ValueError("authorization_mismatch")
            shadow_proof = shadow(doc)
            bound = read_durable_live_plan_intent(
                json.loads(_plan_intent_path(state, early.plan_id).read_bytes())
            )
            if bound.plan_hash != early.plan_hash:
                raise ValueError("ordinary_leg_changed")
            primary = store.current(early.plan_id)
            if (
                not primary
                or primary.plan_hash != early.plan_hash
                or primary.state
                not in (ExecutionState.FILLED, ExecutionState.CANCELLED)
                or primary.receipt_mapping is not True
                or primary.account_binding not in ("bound", "proven")
                or not primary.submit_claim_id
                or not primary.broker_strategy_id
                or not primary.broker_order_id
                or primary.submit_chain_uncertain
                or primary.cancel_chain_uncertain
            ):
                raise ValueError("ordinary_leg_unreconciled")
            if blocking_open_execution_plan_ids(
                state,
                trade_date=day,
                asof=clock(),
                defer_prior_day_sells=True,
                defer_prior_day_buys=True,
            ):
                raise ValueError("unresolved_current_execution")
            if early.code in set(query_codes(state, trade_date=day)) | set(
                unresolved_prior_sell_codes(state, trade_date=day)
            ):
                raise ValueError("inherited_same_code")
            payload = allocation_facts()
            facts = _load_allocation(config, payload, asof=clock())
            audit = read_plan_audit(state, early)
            if not audit:
                raise ValueError("original_policy_binding_missing")
            decision = read_policy(
                config.policy_root,
                clock(),
                **review_publication_fence(morning.review_rendezvous),
            )
            adjustment = buy_cap(
                decision, risk(clock()), early.code, facts.deploy_factor
            )
            override = audit.get("kol_mode_override")
            if (
                adjustment["skip"]
                or adjustment["effective_deploy_factor"]
                < audit["effective_deploy_factor"]
                or override
                and (
                    decision.get("status") != "validated"
                    or any(
                        override.get(k) != decision.get(k)
                        for k in ("decision_id", "decision_sha256")
                    )
                )
            ):
                raise ValueError("current_risk_or_policy_changed")
            if (payload.get("accounting") or {}).get("inherited_buy_isolation"):
                from .account_risk import tighten_conservative_new_risk_cap

                lower = Decimal(payload["accounting"]["conservative_risk_nav"])
                if (
                    tighten_conservative_new_risk_cap(risk(clock()), lower)
                    < audit["effective_deploy_factor"]
                ):
                    raise ValueError("inherited_risk_cap_tightened")
            available = replace(
                facts, deploy_factor=adjustment["effective_deploy_factor"]
            ).cash_limit
            amount = (
                Decimal(str(early.limit_price))
                * 100
                * (1 + Decimal(str(facts.fee_rate)))
            )
            if amount > min(
                Decimal(str(available)), Decimal(str(doc["paired_cash_yuan"]))
            ):
                raise ValueError("remaining_budget_insufficient")
            quote = guard({"code": early.code})
            ok, why, _ = evaluate_buy_market_guard(
                quote, now=clock(), require_authoritative=True
            )
            stamp = datetime.fromisoformat(quote["market_observed_at"])
            if not ok or not start <= stamp <= clock() < end:
                raise ValueError(why or "current_quote_unproven")
            from .trading_execution import _normalize_guard_status

            child = replace(
                original,
                plan_id=pid,
                shares=100,
                created_at=clock(),
                submit_not_before=start,
                recovery_deadline=end,
                market_guard_status=_normalize_guard_status(
                    quote["market_guard_status"]
                ),
                market_guard_observed_at=stamp,
                market_guard_latest_price=float(quote["market_price"]),
                market_guard_down_price=float(quote["down_price"]),
                market_guard_required=True,
            )
            if child.validation_error():
                raise ValueError(child.validation_error())
            child = _bind_durable_plan_intents(config, [child])[0]
            bind_plan_audit(
                state,
                child,
                {
                    **adjustment,
                    "original_allocation_proof": original.allocation_proof_hash,
                    "split_assignment_sha256": doc["sha256"],
                    "parent_plan_hash": early.plan_hash,
                },
            )
            with submission_scope([child]):
                if not start <= clock() < end:
                    raise ValueError("action_window_elapsed")
                token = active_child.set(
                    dict(
                        child_hash=child.plan_hash,
                        parent_plan_hash=early.plan_hash,
                        order_id=primary.broker_order_id,
                        status=primary.state.value,
                        filled=primary.filled_shares,
                    )
                )
                try:
                    receipt = execute(child)
                finally:
                    active_child.reset(token)
            if (
                not receipt.submit_claim_id
                and not receipt.broker_order_id
                and receipt.state not in TERMINAL
            ):
                from .book_b_live_recovery import close_unsubmitted_plan

                receipt = close_unsubmitted_plan(
                    state, child, reason="PILOT_UNCLAIMED_ACTION_CLOSED"
                )
            if receipt.plan_id != pid or receipt.plan_hash != child.plan_hash:
                raise ValueError("child_receipt_identity")
            if (
                receipt.broker_order_id
                and receipt.broker_order_id == primary.broker_order_id
            ):
                raise ValueError("duplicate_parent_order_id")
            return finish(
                "observed",
                receipt.state.value,
                receipt=receipt.as_dict(),
                child_hash=child.plan_hash,
                shadow_sha256=shadow_proof,
            )
        except Exception as exc:
            current = store.current(pid)
            if current or _plan_intent_path(state, pid).exists():
                from .book_b_live_recovery import close_unsubmitted_plan

                if not current or not (
                    current.submit_claim_id
                    or current.broker_order_id
                    or current.submit_chain_uncertain
                    or current.cancel_chain_uncertain
                ):
                    bound = read_durable_live_plan_intent(
                        json.loads(_plan_intent_path(state, pid).read_bytes())
                    )
                    current = close_unsubmitted_plan(
                        state, bound, reason="PILOT_UNCLAIMED_ACTION_CLOSED"
                    )
                return finish("reconcile_only", str(exc), receipt=current.as_dict())
            return finish("no_submit", str(exc))
