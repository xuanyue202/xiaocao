#!/usr/bin/env python3
"""Run the isolated native-Founder/Book-B live morning seam.

This command starts independently of ``auto_daily.sh`` and uses only the
native Founder App.  It waits only for the dated deterministic freeze, then
requests a bounded independently reviewed judgment before advancing immutable
plans through the durable broker execution module.  It
never initializes OpenCLI or waits for/writes a simulated fill.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.book_b_live_morning import (  # noqa: E402
    BookBLiveMorningConfig,
    load_book_b_live_capital_basis,
    reconcile_prior_day_canary_unknowns,
    run_book_b_live_morning,
    write_book_b_live_morning_receipt,
)
from xiaocao.live.capital_keychain import KeychainCapitalRuntime  # noqa: E402
from xiaocao.live.book_b_live_recovery import run_book_b_live_recovery  # noqa: E402
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight  # noqa: E402
from xiaocao.live.trading_runner import build_foundersc_native_execution  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.live.live_decision_support import calendar_provider, digest, read_policy  # noqa: E402
from wait_for_morning_freeze import wait_for_morning_freeze  # noqa: E402


from xiaocao.live.morning_observability import review_brief, review_notice, terminal_notice, dependency_user_action
from xiaocao.automation_run import automation_run, current_automation_id, runner_identity, validate_automation_identity
from xiaocao.live.morning_notifications import AUTOMATION_ID, MorningNotifications
from xiaocao.runner_recovery import DependencyRecovery

_OUTPUT_LOCK = threading.Lock()


def _automatic_dependency_retry(failure: dict) -> bool:
    evidence = failure.get("evidence") or {}
    if (evidence.get("state") != "not_attempted"
            or (evidence.get("user_action") or {}).get("required")
            or evidence.get("password_action_attempted") is not False
            or evidence.get("confirmation_pressed") is not False):
        return False
    if failure.get("code") == "NATIVE_AX_UNLOCK_NOT_ATTEMPTED":
        return True
    return (failure.get("code") == "NATIVE_AX_KEYCHAIN_READ_TIMEOUT"
            and evidence.get("helper_status") == "not_invoked"
            and evidence.get("failure_category") == "keychain_pre_action"
            and evidence.get("password_action_attempted") is False
            and evidence.get("confirmation_pressed") is False)


def _emit_json(payload: dict) -> None:
    # Delivery and execution events share stdout. Keep each JSON line intact.
    with _OUTPUT_LOCK:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _china_date() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _morning_calendar_check(trade_date: str) -> dict:
    """Prove today's exchange session before any native or notification work."""
    settings = load_settings(None)
    client = XiaocaoClient(base_url=settings.base_url, timeout=8, retries=0, cache=None)
    clock = datetime.combine(date.fromisoformat(trade_date), datetime.min.time(),
                             tzinfo=ZoneInfo("Asia/Shanghai"))
    days = calendar_provider(client)(clock)
    latest = max(days)
    if latest > trade_date:
        raise ValueError("MORNING_CALENDAR_FUTURE_DATE")
    return {"source": "xiaocao:/stock/trade_cal", "exchange": "SSE",
            "trade_date": trade_date, "latest_trading_date": latest,
            "status": "trading_day" if latest == trade_date else "non_trading_day"}


def _emit_stage(stage: str, observed_at: datetime) -> None:
    """Emit only state transitions; the operator stream is not a poll log."""
    _emit_json({
        "event": "book_b_live_stage",
        **runner_identity(current_automation_id() or AUTOMATION_ID, "scripts/book_b_live_morning.py"),
        "stage": stage,
        "observed_at": observed_at.isoformat(),
    })


def _wait_for_submit_window(target: datetime, *, heartbeat=None) -> None:
    """Keep the early task alive, but never wait across an unexpected window."""
    while True:
        current = datetime.now(target.tzinfo or ZoneInfo("Asia/Shanghai"))
        remaining = (target - current).total_seconds()
        if remaining <= 0:
            return
        if remaining > 15 * 60:
            raise RuntimeError("LIVE_SUBMIT_WINDOW_TOO_FAR")
        if heartbeat is not None:
            heartbeat()
        time.sleep(min(30.0, remaining))


def _passguard_evidence() -> dict:
    """State the unproven native-control boundary without reading its password."""
    return {
        "status": "pending",
        "trade_password_keychain_read": False,
        "unattended_recovery_proven": False,
        "policy": "fail_closed_if_prompted",
    }


def _market_observed_at(value: object, trade_date: str) -> str:
    text = str(value or "").strip()
    for fmt in ("%H:%M:%S:%f", "%H:%M:%S", "%H%M%S"):
        try:
            clock = datetime.strptime(text, fmt).time()
        except ValueError:
            continue
        return datetime.combine(
            date.fromisoformat(trade_date),
            clock,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ).isoformat()
    raise RuntimeError("LIVE_MARKET_GUARD_TIMESTAMP_UNPROVEN")


def _fresh_market_guard(client: XiaocaoClient, row: dict, trade_date: str) -> dict:
    code = str(row.get("code") or "")
    payload = client.second_line_detail_info(code)
    detail = payload.get(code) if isinstance(payload, dict) else None
    if not isinstance(detail, dict) or str(detail.get("code") or "") != code:
        raise RuntimeError("LIVE_MARKET_GUARD_CODE_UNPROVEN")
    raw_date = str(detail.get("tradeDate") or "")
    observed_date = (
        f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        if len(raw_date) >= 8 and raw_date[:8].isdigit()
        else raw_date[:10]
    )
    if observed_date != trade_date:
        raise RuntimeError("LIVE_MARKET_GUARD_DATE_MISMATCH")
    return {
        "market_guard_required": True,
        "market_guard_status": detail.get("tradeStatus"),
        "market_price": detail.get("trade"),
        "down_price": detail.get("downPrice"),
        "market_observed_at": _market_observed_at(
            detail.get("tradeTimestamp"), trade_date
        ),
    }


def _write_review_immutable(path: Path, payload: dict) -> None:
    """Publish complete JSON atomically without replacing a prior artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".review-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or json.loads(path.read_text(encoding="utf-8")) != payload:
                raise ValueError("LIVE_REVIEW_ARTIFACT_IMMUTABILITY_VIOLATION")
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _validate_preflight_continuation(path: Path, state_dir: Path, trade_date: str,
                                    *, legacy_budget: float | None = None,
                                    legacy_deadline: str | None = None,
                                    now: datetime | None = None) -> dict:
    """Bind a no-effect archived failure; terminal results cannot be replayed."""
    prior = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(prior, dict):
        raise ValueError("LIVE_PREFLIGHT_CONTINUATION_BINDING_UNPROVEN")
    run_id = str(prior.get("run_id") or "")
    suffix = run_id.removeprefix(trade_date + "-")
    archive = state_dir / "runs" / "history"
    expected = archive / f"{run_id}.json"
    identity = prior.get("runner_identity") or {}
    if not isinstance(identity, dict):
        raise ValueError("LIVE_PREFLIGHT_CONTINUATION_BINDING_UNPROVEN")
    if (not run_id.startswith(trade_date + "-")
            or len(suffix) != 12 or any(c not in "0123456789abcdef" for c in suffix)
            or path.is_symlink() or path.resolve() != expected.resolve()
            or not prior.get("state_path")
            or Path(prior["state_path"]).resolve() != state_dir.resolve()
            or prior.get("trade_date") != trade_date
            or prior.get("status") != "blocked" or prior.get("failed_stage") != "preflight"
            or prior.get("plan_count") != 0
            or prior.get("persisted_plan_ids") != [] or prior.get("execution_receipts") != []
            or prior.get("preparation_receipts") != []
            or identity.get("automation_id") != AUTOMATION_ID
            or identity.get("entrypoint") != "scripts/book_b_live_morning.py"
            or not os.environ.get("CODEX_THREAD_ID")
            or identity.get("owner_thread_id") != os.environ["CODEX_THREAD_ID"]):
        raise ValueError("LIVE_PREFLIGHT_CONTINUATION_BINDING_UNPROVEN")
    for receipt_path in archive.glob(f"{trade_date}-*.json"):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or not isinstance(receipt.get("runner_identity", {}), dict):
            raise ValueError("LIVE_PREFLIGHT_CONTINUATION_BINDING_UNPROVEN")
        if (receipt_path != expected and receipt.get("runner_identity", {}).get("automation_id") == AUTOMATION_ID
                and (receipt.get("recovery_of") == run_id
                     or receipt.get("status") in {"completed", "no_action", "skipped"}
                     or receipt.get("persisted_plan_ids") or receipt.get("execution_receipts"))):
            raise ValueError("LIVE_PREFLIGHT_CONTINUATION_ALREADY_CONSUMED")
    for intent_path in (state_dir / "plan_intents").glob("*.json"):
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        if not isinstance(intent, dict) or not isinstance(intent.get("plan"), dict):
            raise ValueError("LIVE_PLAN_INTENT_INVALID")
        plan = intent.get("plan") or {}
        if plan.get("trade_date") == trade_date and plan.get("side") == "BUY":
            raise ValueError("LIVE_PREFLIGHT_CONTINUATION_USE_EXACT_PLAN_RECOVERY")
    budget = prior.get("preparation_budget_seconds")
    if budget is None:
        budget = legacy_budget
    if (not isinstance(budget, (int, float)) or isinstance(budget, bool)
            or not math.isfinite(budget) or not 0 < budget <= 2100):
        raise ValueError("LIVE_PREFLIGHT_ORIGINAL_BUDGET_UNPROVEN")
    started = datetime.fromisoformat(prior["stage_times"]["started"])
    finished = datetime.fromisoformat(prior["stage_times"]["finished"])
    clock = now or datetime.now(timezone.utc)
    if (started.tzinfo is None or finished.tzinfo is None or clock.tzinfo is None
            or started > finished or finished > clock
            or started.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() != trade_date):
        raise ValueError("LIVE_PREFLIGHT_ORIGINAL_CLOCK_UNPROVEN")
    deadline_text = prior.get("preparation_deadline") or legacy_deadline
    if not deadline_text:
        raise ValueError("LIVE_PREFLIGHT_ORIGINAL_DEADLINE_UNPROVEN")
    deadline = datetime.fromisoformat(deadline_text)
    if deadline.tzinfo is None or deadline > started + timedelta(seconds=budget):
        raise ValueError("LIVE_PREFLIGHT_ORIGINAL_CLOCK_UNPROVEN")
    if clock >= deadline:
        raise ValueError("LIVE_PREFLIGHT_ORIGINAL_BUDGET_EXHAUSTED")
    return {"receipt": prior, "receipt_sha256": digest(prior),
            "budget_seconds": float(budget), "deadline": deadline.isoformat()}


def _claim_preflight_continuation(state_dir: Path, binding: dict) -> None:
    """Claim before any native/secret action; interrupted claims stay fenced."""
    prior = binding["receipt"]
    claim = state_dir / "runs" / "preflight_continuations" / f"{prior['run_id']}.json"
    if claim.exists():
        raise ValueError("LIVE_PREFLIGHT_CONTINUATION_ALREADY_CLAIMED")
    _write_review_immutable(claim, {
        "original_run_id": prior["run_id"], "original_receipt_sha256": binding["receipt_sha256"],
        "preparation_deadline": binding["deadline"], "budget_seconds": binding["budget_seconds"],
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "runner_identity": runner_identity(AUTOMATION_ID, "scripts/book_b_live_morning.py"),
        "state": "claimed",
    })


def _review_rendezvous(request: dict, *, now=None, sleep=None, monotonic=None,
                       poll_seconds: float = 1.0) -> dict:
    """Expose one read-only request and wait for independently published policy.

    The parent performs full-source reasoning/review while this process waits.
    This consumer never invokes a model, publishes a decision, or touches keys.
    The existing entry deadline and two-minute wait budget apply.
    Neither backdates a late read; 09:30 is not a preparation cutoff.
    """
    now = now or (lambda: datetime.now(ZoneInfo("Asia/Shanghai")))
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    started = monotonic()
    payload = dict(request)
    # K/P are optional supporting scores. Legacy frozen rows may represent
    # their missing values as NaN; expose null in the review copy only and
    # retain an explicit conversion record plus the original freeze digest.
    # Never normalize execution fields or infinities into valid evidence.
    candidates = [dict(row) for row in payload.get("candidates", [])]
    missing_values = []
    for index, row in enumerate(candidates):
        for field in ("k_score", "p_score"):
            value = row.get(field)
            if isinstance(value, float) and math.isnan(value):
                row[field] = None
                missing_values.append({"candidate_index": index, "code": row.get("code"),
                                       "field": field, "source_value": "NaN"})
    if missing_values:
        payload["candidates"] = candidates
        payload["candidate_missing_values"] = missing_values
    requested = datetime.fromisoformat(payload["requested_at"])
    entry_deadline = datetime.fromisoformat(payload["entry_deadline"])
    if requested.utcoffset() is None or entry_deadline.utcoffset() is None:
        raise ValueError("LIVE_REVIEW_AWARE_TIME_REQUIRED")
    budget = float(payload["max_wait_seconds"])
    if not math.isfinite(budget) or budget < 0 or not math.isfinite(poll_seconds) or poll_seconds <= 0:
        raise ValueError("LIVE_REVIEW_WAIT_BUDGET_INVALID")
    budget = min(120.0, budget)
    deadline = min(entry_deadline, requested + timedelta(seconds=budget))
    payload["max_wait_seconds"] = budget
    payload["freeze_path"] = str(Path(payload["freeze_path"]).resolve())
    payload["policy_root"] = str(Path(payload["policy_root"]).resolve())
    identifier = digest(payload)
    root = Path(payload["policy_root"]).parent / "context" / "live_review_requests"
    request_path = root / f"{identifier}.request.json"
    receipt_path = root / f"{identifier}.receipt.json"
    artifact = {**payload, "request_id": identifier, "request_sha256": identifier}
    _write_review_immutable(request_path, artifact)
    brief_path = root / f"{identifier}.brief.json"
    _write_review_immutable(brief_path, review_brief(artifact))
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        if (receipt_path.is_symlink() or receipt.get("receipt_sha256") != digest(body)
                or receipt.get("request_id") != identifier):
            raise ValueError("LIVE_REVIEW_RECEIPT_BINDING_MISMATCH")
        return receipt
    _emit_json(review_notice(artifact, request_path, receipt_path, brief_path))
    latest: dict = {}
    status, reason = "timed_out", "LIVE_REVIEW_TIMEOUT_NEUTRAL_FALLBACK"
    while True:
        current = now()
        remaining = min(budget - (monotonic() - started), (deadline - current).total_seconds())
        latest = read_policy(Path(payload["policy_root"]), current)
        # A slow read must not backdate a decision past the deadline. A
        # zero-budget lookup may reuse a policy only before the entry cutoff.
        if now() >= entry_deadline or (budget > 0 and (monotonic() - started >= budget or now() >= deadline)):
            break
        if latest.get("status") == "blocked":
            status, reason = "blocked", str(latest["reason"])
            break
        if latest.get("status") == "validated":
            as_of = datetime.fromisoformat(latest["record"]["decision"]["as_of"].replace("Z", "+00:00"))
            status = "validated"
            reason = "LIVE_REVIEW_REUSED_VALIDATED_POLICY" if as_of < requested else "LIVE_REVIEW_NEW_VALIDATED_POLICY"
            break
        if remaining <= 0 or monotonic() - started >= budget or now() >= deadline:
            break
        sleep(min(1.0, poll_seconds, remaining))
    receipt = {
        "schema_version": "book-b-live-review-receipt.v1", "request_id": identifier,
        "request_sha256": identifier, "request_path": str(request_path), "receipt_path": str(receipt_path),
        "requested_at": requested.isoformat(), "completed_at": now().isoformat(),
        "entry_deadline": entry_deadline.isoformat(), "max_wait_seconds": budget,
        "waited_seconds": max(0.0, monotonic() - started), "status": status, "reason": reason,
        "supporting_health": "healthy" if status == "validated" else "degraded",
        "fallback": "neutral" if status == "timed_out" else None,
        "last_policy_status": latest.get("status"), "decision_id": latest.get("decision_id"),
        "decision_sha256": latest.get("decision_sha256"),
    }
    receipt["receipt_sha256"] = digest(receipt)
    _write_review_immutable(receipt_path, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today")
    parser.add_argument(
        "--freeze",
        default="output/live/book_b_live_freeze_{date}.jsonl",
        help="Immutable dated producer freeze; {date} is expanded",
    )
    parser.add_argument(
        "--allocation-facts",
        default="output/live/book_b_live_allocation_facts_{date}.json",
        help="Broker-sourced allocation facts; {date} is expanded",
    )
    parser.add_argument("--state-dir", default="output/live/book_b_live_execution")
    parser.add_argument("--policy-root", default="output/live/kol_policy/decisions")
    parser.add_argument(
        "--route",
        choices=("native-app",),
        default="native-app",
        help="Native Founder App only; OpenCLI trading/view is sunset",
    )
    parser.add_argument("--freeze-wait-seconds", type=float, default=2100.0)
    parser.add_argument("--resume-plan-id", help="Resume only this existing durable plan; never regenerate candidates")
    parser.add_argument("--resume-preflight-receipt", type=Path,
                        help="Continue this same-owner blocked preflight with the original preparation budget")
    parser.add_argument("--original-preparation-budget-seconds", type=float,
                        help="Explicit original argv budget for legacy receipts without recorded budget")
    parser.add_argument("--original-preparation-deadline",
                        help="Proved aware absolute original deadline for legacy receipts")
    parser.add_argument("--recovery-action", choices=("resume", "reconcile", "close"), default="resume")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--automation-id", default=AUTOMATION_ID,
                        help="Task-local deduplication identity; never use a remote writer's identity")
    args = parser.parse_args(argv)
    try:
        validate_automation_identity(AUTOMATION_ID, args.automation_id)
        if not os.environ.get("CODEX_AUTOMATION_ID") or not os.environ.get("CODEX_THREAD_ID"):
            raise ValueError("AUTOMATION_RUNTIME_IDENTITY_UNPROVEN")
    except ValueError as exc:
        _emit_json({"status": "blocked", "reason": str(exc),
                    **runner_identity(AUTOMATION_ID, "scripts/book_b_live_morning.py")})
        return 2
    if args.recovery_action != "resume" and not args.resume_plan_id:
        parser.error("--recovery-action requires --resume-plan-id")

    trade_date = _china_date() if args.date == "today" else args.date
    if args.resume_preflight_receipt and args.resume_plan_id:
        parser.error("preflight continuation cannot be combined with plan recovery")
    if (args.original_preparation_budget_seconds is not None or args.original_preparation_deadline) and not args.resume_preflight_receipt:
        parser.error("original preparation budget requires the exact preflight receipt")
    with automation_run(args.automation_id, trade_date,
                        root=Path.home() / "Library/Caches/xiaocao/automation-runs") as lock:
        if lock["status"] == "busy":
            _emit_json({**lock, "status": "no_op", "reason": "SAME_AUTOMATION_RUNNING"})
            return 0
        if not args.resume_plan_id:
            # An exact recovery is a separate explicit instruction; routine
            # holiday wakes must not touch the APP or historical orders.
            try:
                calendar = _morning_calendar_check(trade_date)
            except Exception as exc:
                calendar = {"status": "unproven", "trade_date": trade_date,
                            "failure_category": getattr(exc, "failure_category", None)
                            or type(exc).__name__}
            if calendar["status"] != "trading_day":
                blocked = calendar["status"] == "unproven"
                result = {"status": "blocked" if blocked else "no_action",
                          "reason": "MORNING_CALENDAR_UNPROVEN" if blocked else "NON_TRADING_DAY",
                          "trade_date": trade_date, "calendar": calendar,
                          "observed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                          "runner_identity": runner_identity(args.automation_id, "scripts/book_b_live_morning.py")}
                path = Path(args.state_dir) / "runs" / "calendar" / (digest(result) + ".json")
                _write_review_immutable(path, result)
                _emit_json({**result, "receipt_path": str(path.resolve())})
                return 2 if blocked else 0
        if not args.resume_plan_id and not args.resume_preflight_receipt:
            from xiaocao.utils.business_clock import wait_for_business_time
            from datetime import time as wall_time
            wait_for_business_time(trade_date, wall_time(9, 0))
        args.preflight_continuation = None
        if args.resume_preflight_receipt:
            try:
                binding = _validate_preflight_continuation(args.resume_preflight_receipt,
                    Path(args.state_dir), trade_date, legacy_budget=args.original_preparation_budget_seconds,
                    legacy_deadline=args.original_preparation_deadline)
                _claim_preflight_continuation(Path(args.state_dir), binding)
                args.preflight_continuation = binding
            except (OSError, ValueError, KeyError, TypeError) as exc:
                _emit_json({"status": "blocked", "reason": str(exc) if isinstance(exc, ValueError)
                            else "LIVE_PREFLIGHT_CONTINUATION_BINDING_UNPROVEN",
                            **runner_identity(AUTOMATION_ID, "scripts/book_b_live_morning.py")})
                return 2
        notices = MorningNotifications(trade_date, automation_id=args.automation_id,
            on_delivery=lambda result: _emit_json({"event": "book_b_wecom_delivery", **result}))
        try:
            if args.recovery_action != "close":
                notices.arm_golden_window()
                notices.publish("preflight-start")
            return _run(args, notices)
        except Exception as exc:
            # Early configuration faults also need a result; never send raw
            # exception text from a credential-bearing setup boundary.
            notices.publish("result", {"status": "blocked", "failed_stage": "preflight",
                                       "reason": "MORNING_SETUP_FAILED:" + type(exc).__name__,
                                       "user_action": dependency_user_action(str(exc)),
                                       "user_action_required": dependency_user_action(str(exc))["required"]})
            raise
        finally:
            try:
                notices.close()
            except Exception:
                _emit_json({"event": "book_b_wecom_delivery", "status": "unproven"})


def _run(args, notices):
    trade_date = _china_date() if args.date == "today" else args.date
    absolute_preparation_deadline = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, args.freeze_wait_seconds))
    preparation_deadline = time.monotonic() + max(0.0, args.freeze_wait_seconds)
    prior_preflight = None
    continuation = getattr(args, "preflight_continuation", None)
    if continuation:
        prior_preflight = continuation["receipt"]
        deadline = datetime.fromisoformat(continuation["deadline"])
        absolute_preparation_deadline = deadline
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise ValueError("LIVE_PREFLIGHT_ORIGINAL_BUDGET_EXHAUSTED")
        preparation_deadline = time.monotonic() + max(0.0, remaining)
    freeze_path = Path(str(args.freeze).format(date=trade_date))
    allocation_path = Path(str(args.allocation_facts).format(date=trade_date))
    if args.resume_plan_id and args.recovery_action == "close":
        config = BookBLiveMorningConfig(
            trade_date=trade_date, freeze_path=freeze_path, allocation_facts_path=allocation_path,
            state_dir=Path(args.state_dir), resume_plan_id=args.resume_plan_id,
        )
        receipt = run_book_b_live_recovery(config, plan_id=args.resume_plan_id, action="close")
        _emit_json(receipt.as_dict())
        return 0
    capital_runtime = KeychainCapitalRuntime()
    capital_receipt = capital_runtime.preflight()
    if capital_receipt["status"] != "ready":
        blocked = {
            "runner_identity": runner_identity(args.automation_id, "scripts/book_b_live_morning.py"),
            "trade_date": trade_date,
            "status": "blocked",
            "reason": "LIVE_CAPITAL_RUNTIME_NOT_READY",
            "capital_runtime": capital_receipt,
        }
        notices.publish("result", blocked)
        _emit_json(blocked)
        return 2
    keychain = FounderscKeychainPreflight()
    keychain_receipt = keychain.run(read_trade_secret=True)
    required_keychain_fields = (
        "trade_item_present",
        "trade_account_present",
        "trade_secret_readable",
        "trade_secret_nonempty",
    )
    keychain_error = "FOUNDER_NATIVE_TRADE_KEYCHAIN_NOT_READY"
    if not all(keychain_receipt.get(key) is True for key in required_keychain_fields):
        raise RuntimeError(keychain_error)
    trade_account_fingerprint = keychain.trade_account_fingerprint()
    if not trade_account_fingerprint:
        raise RuntimeError("FOUNDER_TRADE_ACCOUNT_FINGERPRINT_MISSING")
    def build_native():
        return build_foundersc_native_execution(args.state_dir,
            scoped_buy_preflight=not bool(args.resume_plan_id),
            expected_fund_account_fingerprint=trade_account_fingerprint,
            safety_env_provider=capital_runtime.safety_env,
            # Preserve each incident/takeover locally; the morning result
            # owns the single external summary, including pending orders.
            notifier=lambda title, body: {"wecom": "deferred_to_morning_result"})
    # Initial helper/build faults belong to the original durable preflight,
    # with its repair budget, rather than an early setup exit.
    execution, broker = build_native() if args.resume_plan_id else (None, None)
    prior_reconciliations: tuple[dict, ...] = ()
    api_settings = load_settings(None)
    market_client = XiaocaoClient(
        base_url=api_settings.base_url,
        timeout=api_settings.timeout,
        retries=api_settings.retries,
        cache=None,
    )

    from xiaocao.live.buy_preflight import (
        allocation_from_buy_preflight, current_owned_book_b_codes,
        pretrade_account, validate_buy_preflight,
    )
    from xiaocao.live.book_b_live_lifecycle import ownership_head_sha256
    from xiaocao.live.live_decision_support import evaluate_live_risk
    trading_calendar = calendar_provider(market_client)
    buying_snapshot = None
    buying_head = None
    def current_buy_snapshot():
        nonlocal buying_snapshot, buying_head
        current = datetime.now(ZoneInfo("Asia/Shanghai"))
        head = ownership_head_sha256(Path(args.state_dir))
        if buying_snapshot is not None and buying_head == head:
            try:
                return validate_buy_preflight(buying_snapshot, trade_date, current)
            except ValueError:
                pass
        codes = current_owned_book_b_codes(Path(args.state_dir))
        buying_snapshot = broker.read_buy_preflight_snapshot(trade_date=trade_date, owned_codes=codes)
        buying_head = head
        return buying_snapshot

    def current_buy_risk(clock):
        account = pretrade_account(Path(args.state_dir), current_buy_snapshot(),
            trade_date=trade_date, now=datetime.now(ZoneInfo("Asia/Shanghai")))
        return evaluate_live_risk(Path(args.state_dir), now=datetime.now(ZoneInfo("Asia/Shanghai")),
            account=account, trading_dates_provider=trading_calendar,
            receipt_root=Path(args.policy_root).parent / "account_risk")

    def read_allocation_facts() -> dict:
        nonlocal prior_reconciliations
        # The core reconciles open ordinary intents before this callback.
        prior_reconciliations = reconcile_prior_day_canary_unknowns(
            Path(args.state_dir),
            trade_date=trade_date,
            execute=lambda plan: execution.execute(plan, broker),
        )
        if not args.resume_plan_id:
            snapshot = current_buy_snapshot()
            current = datetime.now(ZoneInfo("Asia/Shanghai"))
            account = pretrade_account(Path(args.state_dir), snapshot,
                trade_date=trade_date, now=current)
            basis = load_book_b_live_capital_basis(Path(args.state_dir),
                trade_date=trade_date, current_account=account)
            return allocation_from_buy_preflight(snapshot, basis, now=current)
        basis = load_book_b_live_capital_basis(Path(args.state_dir))
        allocation_kwargs = {
            "trade_date": trade_date,
            "logical_account_id": "primary",
            "settled_nav": basis.settled_nav,
            "current_open_exposure": basis.current_open_exposure,
            "capital_basis_source": basis.source,
            "expected_fund_account_fingerprint": trade_account_fingerprint,
        }
        allocation_kwargs["capital_basis_receipt_sha256"] = basis.receipt_sha256
        return broker.read_live_allocation_facts(
            **allocation_kwargs,
        )

    def preflight() -> dict:
        nonlocal execution, broker
        if broker is None:
            execution, broker = build_native()
        refresh = getattr(getattr(broker, "native", None), "refresh_helper", None)
        if refresh:
            refresh()
        broker.ensure_login()
        native_receipt = broker.ensure_native_ready(
            require_order_capability=True,
            unlock_once=True,
        )
        environment_receipt = broker.ensure_environment(
            target="live",
            expected_current="any",
            logical_account_id="primary",
        )
        return {
            **environment_receipt,
            "website_authentication": {
                "status": "not_used",
                "route": "native-app",
                "reason": "OpenCLI trading/view is sunset",
            },
            "passguard": {
                **_passguard_evidence(),
                "status": "native_trade_ready",
                "trade_password_keychain_read": True,
                "unattended_recovery_proven": True,
                "single_attempt_unlock_available": True,
            },
            "native_order_surface": native_receipt,
        }

    def restore_environment() -> dict:
        return {
            "status": "native_environment_restore_not_applicable",
            "environment": "not_applicable",
            "route": "native-app",
        }

    def read_live_heartbeat() -> dict:
        refresh = getattr(getattr(broker, "native", None), "refresh_helper", None)
        if refresh:
            refresh()
        return broker.ensure_environment(
            target="live",
            expected_current="live",
            logical_account_id="primary",
        )

    def recovery_event(event):
        failures = event.get("failures") or []
        _emit_json({k: event.get(k) for k in ("event", "status", "request_path", "request_sha256", "sequence")}
            | {"reason": failures[-1]["code"] if failures else None,
               "recovery_kind": ((failures[-1].get("evidence") or {}).get("user_action") or {}).get("recovery_kind")
               if failures else None})

    recovery = DependencyRecovery(
        root=Path(args.state_dir) / "runs" / "dependencies",
        identity={**runner_identity(args.automation_id, "scripts/book_b_live_morning.py"), "trade_date": trade_date},
        deadline=preparation_deadline,
        boundary=datetime.fromisoformat(trade_date + "T09:24:00+08:00"),
        # These callbacks only read readiness / perform one fenced unlock.
        # Economic, strategy and order errors outside them are never retried.
        recoverable=lambda exc: True,
        on_event=recovery_event,
        on_failure=lambda record: notices.publish("preflight-problem", {
            "run_id": record["binding"]["request_id"] + ":" + record["failures"][-1]["code"],
            "reason": record["failures"][-1]["code"], "request_path": record["request_path"],
            "user_action": record["failures"][-1]["evidence"]["user_action"],
            "user_action_required": record["failures"][-1]["evidence"]["user_action"]["required"]}),
        evidence=lambda: getattr(broker, "credential_health", {}),
        failure_evidence=lambda exc: {**getattr(broker, "credential_health", {}),
            "user_action": dependency_user_action(str(exc), getattr(broker, "credential_health", {}))},
        automatic_retry=_automatic_dependency_retry,
    )
    def live_heartbeat():
        return read_live_heartbeat() if args.resume_plan_id else recovery.run(read_live_heartbeat)

    config = BookBLiveMorningConfig(
        trade_date=trade_date,
        freeze_path=freeze_path,
        allocation_facts_path=allocation_path,
        state_dir=Path(args.state_dir),
        logical_account_id="primary",
        policy_root=Path(args.policy_root),
        resume_plan_id=args.resume_plan_id,
    )
    runner = run_book_b_live_recovery if args.resume_plan_id else run_book_b_live_morning
    recovery_args = {"plan_id": args.resume_plan_id, "action": args.recovery_action} if args.resume_plan_id else {}
    def progress(stage, observed_at):
        _emit_stage(stage, observed_at)
        if stage == "freeze_wait":
            notices.publish("ready")

    receipt = runner(
        config,
        **recovery_args,
        preflight=preflight if args.resume_plan_id else lambda: recovery.run(preflight),
        restore_environment=restore_environment,
        read_allocation_facts=read_allocation_facts,
        refresh_market_guard=lambda row: _fresh_market_guard(
            market_client, row, trade_date
        ),
        wait_for_dated_freeze=lambda: wait_for_morning_freeze(
            date=trade_date,
            live_dir=freeze_path.parent,
            timeout_sec=0 if args.resume_plan_id else max(0.0, preparation_deadline - time.monotonic()),
            poll_sec=args.poll_seconds,
            snapshot_path=freeze_path,
            heartbeat=live_heartbeat,
            dependency_notice=_emit_json,
        ),
        prepare_only=(lambda plan: broker.prepare_readonly(
            plan,
            expected_fund_account_fingerprint=trade_account_fingerprint,
        )) if args.resume_plan_id else None,
        wait_for_submit_window=lambda target: _wait_for_submit_window(
            target,
            heartbeat=live_heartbeat,
        ),
        wait_for_reconcile=lambda: time.sleep(1.0),
        execute=lambda plan: execution.execute(plan, broker),
        submission_scope=lambda plans: broker.submission_batch(plans),
        trading_dates_provider=trading_calendar,
        risk_provider=None if args.resume_plan_id else current_buy_risk,
        account_snapshot_provider=lambda: broker.read_live_account_snapshot(
            trade_date=trade_date, logical_account_id="primary",
            expected_fund_account_fingerprint=trade_account_fingerprint,
        ),
        review_rendezvous=lambda request: _review_rendezvous(request, poll_seconds=args.poll_seconds),
        on_progress=progress,
    )
    receipt = replace(
        receipt,
        recovery_of=prior_preflight["run_id"] if prior_preflight else receipt.recovery_of,
        preparation_budget_seconds=continuation["budget_seconds"] if continuation else args.freeze_wait_seconds,
        preparation_deadline=absolute_preparation_deadline.isoformat(),
        runner_identity=runner_identity(args.automation_id, "scripts/book_b_live_morning.py"),
        capital_runtime=capital_receipt,
        open_plan_reconciliations=receipt.open_plan_reconciliations,
        prior_reconciliations=prior_reconciliations,
        dependency_recovery=recovery.snapshot(),
    )
    write_book_b_live_morning_receipt(config, receipt)
    payload = receipt.as_dict()
    notice = terminal_notice(payload, config.state_dir / "runs" / "history" / f"{receipt.run_id}.json")
    notices.publish("result", notice)
    _emit_json(notice)
    return 0 if receipt.status in {"completed", "no_action", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
