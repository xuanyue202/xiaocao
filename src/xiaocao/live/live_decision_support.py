"""Live-only KOL consumption and observed Book B risk evidence.

No paper state, broker actions, capital keys or settlement writer live here.
Missing inception evidence blocks buys; it never synthesizes a seed settlement.
The fixed-capital ownership replay proves zero external flow. A cash difference
is an unproved flow requiring review, never an inferred deposit/new seed.
The historical writer did not guarantee daily settlements. Validate every
existing file and require the calendar's latest completed day, but disclose
intermediate gaps without treating unknown historical highs as zero or new
capital. High water means the seed, validated settlements and observed marks.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from .account_risk import AccountRiskReceipt, NAV_BASIS, NavObservation, evaluate_account_risk
from .book_b_live_lifecycle import (
    BookBLiveAccountState,
    _load_intent_index,
    _read_jsonl_strict,
    _validate_execution_fill_coverage,
    _validate_ownership_chain,
    project_book_b_live_account,
)
from .kol_policy import buy_adjustment, load_decision

_CHINA = ZoneInfo("Asia/Shanghai")
_CAPITAL = 30_000.0


def digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("LIVE_POLICY_SYMLINK_UNPROVEN")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("LIVE_POLICY_OBJECT_REQUIRED")
    return value


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("LIVE_RISK_AWARE_TIMESTAMP_REQUIRED")
    return parsed


def _number(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("LIVE_RISK_FINITE_NUMBER_REQUIRED")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("LIVE_RISK_FINITE_NUMBER_REQUIRED")
    return result


def calendar_provider(client) -> Callable[[datetime], list[str]]:
    """One explicit exchange-calendar query per date, reused within a run."""
    cache: dict[str, list[str]] = {}

    def read(now: datetime) -> list[str]:
        today = now.astimezone(_CHINA).date().isoformat()
        if today not in cache:
            rows = client.get_trade_cal("2020-01-01", today, "SSE", 1)
            days = []
            for row in rows:
                raw = str(row.get("calDate") or row.get("tradeDate") or row.get("date") or "")
                if len(raw) == 8 and raw.isdigit():
                    raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
                if row.get("isOpen", row.get("is_open")) not in (1, "1", True, "true", "TRUE", "open", "OPEN"):
                    raise ValueError("LIVE_RISK_CALENDAR_OPEN_STATUS_UNPROVEN")
                days.append(date.fromisoformat(raw).isoformat())
            if not days:
                raise ValueError("LIVE_RISK_CALENDAR_MISSING")
            cache[today] = sorted(set(days))
        return cache[today]

    return read


def expected_settlement_date(now: datetime, trading_dates: Iterable[str]) -> str:
    local = _time(now.isoformat()).astimezone(_CHINA)
    today = local.date().isoformat()
    days = sorted(set(trading_dates))
    for day in days:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("LIVE_RISK_CALENDAR_INVALID")
    completed = [day for day in days if day < today or (day == today and local.hour >= 15)]
    if not completed:
        raise ValueError("LIVE_RISK_CALENDAR_MISSING")
    return completed[-1]


def _ownership_cash(state_dir: Path) -> tuple[dict, list[dict]]:
    rows, _head = _validate_ownership_chain(
        _read_jsonl_strict(state_dir / "book_b_ownership_evidence.jsonl")
    )
    _validate_execution_fill_coverage(state_dir, rows)
    intents = _load_intent_index(state_dir)
    cash = Decimal("30000")
    by_head = {None: cash}
    for row in rows:
        intent = intents.get(row["plan_id"])
        if (row.get("logical_account_id") != "primary" or intent is None
                or digest(intent) != row["plan_hash"]):
            raise ValueError("LIVE_RISK_OWNERSHIP_ACCOUNT_OR_INTENT_MISMATCH")
        fee = _number(intent.get("fee_rate", 0.0001))
        if not 0 <= fee < 1:
            raise ValueError("LIVE_RISK_FEE_INVALID")
        # Ownership serializes exact notionals as decimal strings; its chain
        # validator above has already checked their numeric shape and range.
        notional = _number(Decimal(str(row["fill_notional"])))
        cash += notional * ((1 - fee) if row["side"] == "SELL" else -(1 + fee))
        by_head[row["event_hash"]] = cash
    return by_head, rows


def _verify_nav(payload: dict, cash_by_head: dict) -> None:
    head = payload.get("ownership_head_sha256")
    cash = _number(payload["cash"])
    if head not in cash_by_head or cash.quantize(Decimal("0.01")) != cash_by_head[head].quantize(Decimal("0.01")):
        raise ValueError("LIVE_RISK_EXTERNAL_FLOW_OR_OWNERSHIP_UNPROVEN")
    if "external_flow_total" in payload and _number(payload["external_flow_total"]) != 0:
        raise ValueError("LIVE_RISK_EXTERNAL_FLOW_REVIEW_REQUIRED")
    if "initial_capital" in payload and _number(payload["initial_capital"]) != 30000:
        raise ValueError("LIVE_RISK_INITIAL_CAPITAL_MISMATCH")
    liquidation = _number(payload["liquidation_value_after_fee"])
    nav = _number(payload["settled_nav"])
    if abs(nav - cash - liquidation) > Decimal("0.01"):
        raise ValueError("LIVE_RISK_NAV_EQUATION_INVALID")
    lots = payload["lots"]
    if not isinstance(lots, list) or (head is None and lots):
        raise ValueError("LIVE_RISK_LOTS_UNPROVEN")
    if abs(sum((_number(lot["liquidation_value_after_fee"]) for lot in lots), Decimal(0)) - liquidation) > Decimal("0.01"):
        raise ValueError("LIVE_RISK_NAV_LOTS_MISMATCH")


def load_live_nav_history(state_dir: Path, *, asof: datetime,
                          trading_dates: Iterable[str], diagnostics: dict | None = None) -> list[NavObservation]:
    """Verify EVERY immutable settlement, including old hashes and chronology."""
    root = Path(state_dir)
    days = sorted(set(trading_dates))
    expected = expected_settlement_date(asof, days)
    cash_by_head, ownership = _ownership_cash(root)
    if any(row["trade_date"] > asof.astimezone(_CHINA).date().isoformat() for row in ownership):
        raise ValueError("LIVE_RISK_FUTURE_OWNERSHIP")
    history = []
    paths = sorted((root / "settlements").glob("*.json"))
    if not paths:
        raise ValueError("LIVE_RISK_HISTORY_OR_EXPLICIT_SEED_PROOF_REQUIRED")
    for path in paths:
        payload = _read(path)
        claimed = payload.pop("settlement_sha256", None)
        if digest(payload) != claimed:
            raise ValueError("LIVE_RISK_SETTLEMENT_HASH_MISMATCH")
        day = payload.get("trade_date")
        if day != path.stem or day not in days:
            raise ValueError("LIVE_RISK_SETTLEMENT_DATE_MISMATCH")
        if (payload.get("schema_version") != 1 or payload.get("status") != "settled" or payload.get("environment") != "live"
                or payload.get("logical_account_id") != "primary"
                or payload.get("account_binding") != "proven"
                or payload.get("capital_basis_source") != "broker_reconciled_book_b_nav"
                or payload.get("book", "B") != "B"
                or payload.get("account_id", "live:B") != "live:B"
                or payload.get("nav_basis", NAV_BASIS) != NAV_BASIS):
            raise ValueError("LIVE_RISK_SETTLEMENT_ACCOUNT_MISMATCH")
        settled = _time(payload["settled_at"])
        observed = _time(payload["broker_snapshot_observed_at"])
        for stamp in (settled, observed):
            local = stamp.astimezone(_CHINA)
            if stamp > asof or local.date().isoformat() != day or local.hour < 15:
                raise ValueError("LIVE_RISK_SETTLEMENT_FUTURE_OR_PRE_CLOSE")
        if observed > settled or (settled - observed).total_seconds() > 300:
            raise ValueError("LIVE_RISK_SETTLEMENT_SNAPSHOT_STALE")
        prefix = [row for row in ownership if row["trade_date"] <= day]
        if payload.get("ownership_head_sha256") != (prefix[-1]["event_hash"] if prefix else None):
            raise ValueError("LIVE_RISK_SETTLEMENT_OWNERSHIP_DATE_MISMATCH")
        _verify_nav(payload, cash_by_head)
        if any(lot["entry_date"] > day for lot in payload["lots"]):
            raise ValueError("LIVE_RISK_FUTURE_OWNED_LOT")
        history.append(NavObservation(day, float(payload["settled_nav"]), "live:B", _CAPITAL,
                                      0.0, NAV_BASIS, "settled", settled.isoformat(), claimed))
    inception = min([history[0].date] + [row["trade_date"] for row in ownership])
    required = [day for day in days if inception <= day <= expected]
    actual = {row.date for row in history}
    gaps = [day for day in required if day not in actual]
    if diagnostics is not None:
        diagnostics.update({"history_gaps": gaps, "missing_historical_high_water": bool(gaps),
            "high_water_basis": "seed_validated_settlements_and_observed_marks",
            "verified_settlement_dates": sorted(actual),
            "supporting_health": "degraded" if gaps else "healthy"})
    if history[-1].date != expected:
        raise ValueError("LIVE_RISK_LATEST_SETTLEMENT_REQUIRED:" + expected)
    return history


def evaluate_live_risk(state_dir: Path, *, now: datetime,
                       trading_dates_provider: Callable[[datetime], Iterable[str]] | None = None,
                       account: BookBLiveAccountState | None = None,
                       account_snapshot_provider: Callable[[], dict] | None = None,
                       receipt_root: Path | None = None,
                       now_provider: Callable[[], datetime] | None = None) -> AccountRiskReceipt:
    """Persist every result under a lock so intraday peaks/pause survive restart.

    ``account`` must be the just-completed lifecycle projection. Alternatively
    supply its broker snapshot port. There is deliberately no numeric NAV port.
    Storage failure is returned as a buy block; SELL/reconcile callers continue.
    """
    root = Path(state_dir)
    path = (Path(receipt_root) if receipt_root is not None else root / "account_risk") / "live_B.jsonl"
    previous = None
    expected = ""
    history = []
    mark = None
    error = None
    history_diagnostics: dict = {}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            events = _read_jsonl_strict(path)
            head = None
            for event in events:
                body = dict(event)
                claimed = body.pop("event_hash", None)
                if body.get("previous_hash") != head or digest(body) != claimed:
                    raise ValueError("PREVIOUS_RECEIPT_INVALID")
                raw = dict(event["receipt"])
                raw["reasons"] = tuple(raw["reasons"])
                previous = AccountRiskReceipt(**raw)
                head = claimed
            try:
                if trading_dates_provider is None:
                    raise ValueError("LIVE_RISK_CALENDAR_PROVIDER_REQUIRED")
                days = list(trading_dates_provider(now))
                expected = expected_settlement_date(now, days)
                history = load_live_nav_history(root, asof=now, trading_dates=days,
                                                diagnostics=history_diagnostics)
                if account_snapshot_provider is not None:
                    snapshot = account_snapshot_provider()
                    if now_provider is not None:
                        # Native readback completes after the request clock.
                        # Evaluate against completion, never a pre-read asof.
                        now = now_provider()
                        days = list(trading_dates_provider(now))
                        completed_date = expected_settlement_date(now, days)
                        if completed_date != expected:
                            expected = completed_date
                            history = load_live_nav_history(root, asof=now, trading_dates=days,
                                                            diagnostics=history_diagnostics)
                    account = project_book_b_live_account(root, snapshot,
                                trade_date=now.astimezone(_CHINA).date().isoformat(), now=now)
                if not isinstance(account, BookBLiveAccountState) or account.logical_account_id != "primary":
                    raise ValueError("LIVE_RISK_RECONCILED_CURRENT_NAV_REQUIRED")
                cash_by_head, _ = _ownership_cash(root)
                if account.ownership_head_sha256 != next(reversed(cash_by_head)):
                    raise ValueError("LIVE_RISK_CURRENT_OWNERSHIP_CHANGED")
                _verify_nav(account.as_dict(), cash_by_head)
                mark = NavObservation(account.trade_date, account.settled_nav, "live:B", _CAPITAL,
                                      0.0, NAV_BASIS, "reconciled", account.broker_snapshot_observed_at,
                                      digest(account.as_dict()))
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                error = str(exc) or type(exc).__name__
            receipt = evaluate_account_risk(history, current_nav=mark, asof=now, account_id="live:B",
                        initial_capital=_CAPITAL, expected_settlement_date=expected, previous_receipt=previous)
            if error:
                receipt = replace(receipt, status="BLOCKED", deploy_factor=0.0, nav=None,
                                  drawdown_pct=None, review_required=True,
                                  reasons=tuple(sorted(set(receipt.reasons) | {error})))
            warnings = {"HIGH_WATER_BASIS_SEED_VALIDATED_SETTLEMENTS_AND_OBSERVED_MARKS"}
            if history_diagnostics.get("history_gaps"):
                warnings.add("HISTORICAL_SETTLEMENT_GAPS:" + ",".join(history_diagnostics["history_gaps"]))
            receipt = replace(receipt, reasons=tuple(sorted(set(receipt.reasons) | warnings)))
            event = {"receipt": receipt.as_dict(), "previous_hash": head,
                     "history_coverage": history_diagnostics}
            event["event_hash"] = digest(event)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return receipt
    except (OSError, ValueError, TypeError, KeyError) as exc:
        receipt = evaluate_account_risk([], asof=now, account_id="live:B", initial_capital=_CAPITAL,
                                        expected_settlement_date=expected, previous_receipt=previous)
        return replace(receipt, reasons=tuple(sorted(set(receipt.reasons) |
                       {"PREVIOUS_RECEIPT_INVALID", str(exc) or type(exc).__name__})))


def read_policy(root: Path | None, now: datetime) -> dict:
    if root is None:
        return {"status": "neutral", "book": "B", "runtime": "live", "reason": "POLICY_NOT_CONFIGURED"}
    return load_decision(root, book="B", runtime="live", now=now)


def buy_cap(decision: dict, risk: AccountRiskReceipt, code: str, base_factor: float) -> dict:
    adjustment = buy_adjustment(decision, code)
    factor = min(base_factor, adjustment["scale"], risk.deploy_factor)
    if not math.isfinite(factor) or not 0 <= factor <= 1:
        raise ValueError("LIVE_POLICY_FACTOR_INVALID")
    return {**adjustment, "effective_deploy_factor": factor,
            "skip": adjustment["skip"] or factor == 0,
            "decision_sha256": decision.get("decision_sha256"), "risk_receipt": risk.as_dict()}


def plan_audit_path(state_dir: Path, plan_id: str) -> Path:
    key = hashlib.sha256(plan_id.encode()).hexdigest()[:24]
    return Path(state_dir) / "decision_support" / "plan_policy" / f"{key}.json"


def bind_plan_audit(state_dir: Path, plan, evidence: dict) -> dict:
    path = plan_audit_path(state_dir, plan.plan_id)
    payload = {"schema_version": 1, "plan_id": plan.plan_id, "plan_hash": plan.plan_hash,
               "book": "B", "runtime": "live", **evidence}
    payload["audit_sha256"] = digest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if path.exists():
            if _read(path) != payload:
                raise ValueError("LIVE_PLAN_POLICY_IMMUTABILITY_VIOLATION")
        else:
            _write(path, payload)
    return payload


def read_plan_audit(state_dir: Path, plan) -> dict | None:
    path = plan_audit_path(state_dir, plan.plan_id)
    if not path.exists():
        return None
    payload = _read(path)
    claimed = payload.pop("audit_sha256", None)
    if digest(payload) != claimed or payload.get("plan_hash") != plan.plan_hash or payload.get("plan_id") != plan.plan_id:
        raise ValueError("LIVE_PLAN_POLICY_BINDING_MISMATCH")
    return {**payload, "audit_sha256": claimed}
