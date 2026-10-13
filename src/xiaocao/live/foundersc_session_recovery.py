"""One original-owner session rebuild, followed by one visual CAPTCHA login."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from xiaocao.runner_recovery import _hash, _write, signal_recheck
from .foundersc_native_broker import FounderscNativeAXBrokerAdapter
from .foundersc_session import app_session
from .morning_observability import dependency_user_action


def recover_session(request_path: Path, *, native, phase: str,
                    now=None, launch=None) -> dict:
    now = now or (lambda: datetime.now(timezone.utc))
    request_path = Path(request_path).absolute()
    if request_path.resolve() != request_path or request_path.parent.name != "dependencies" or request_path.parent.parent.name != "runs":
        raise ValueError("SESSION_RESET_CANONICAL_REQUEST_REQUIRED")
    request = json.loads(request_path.read_text())
    binding = request["binding"]
    if (request.get("status") != "waiting" or _hash(binding) != request.get("request_sha256")
            or binding.get("owner_thread_id") != os.environ.get("CODEX_THREAD_ID")
            or not binding.get("owner_thread_id")
            or binding.get("automation_id") != "xiaocao-book-b-live-morning"
            or os.environ.get("CODEX_AUTOMATION_ID") != binding["automation_id"]):
        raise ValueError("SESSION_RESET_OWNER_REQUEST_MISMATCH")
    deadline = datetime.fromisoformat(binding["preparation_deadline"])
    clock = now()
    if deadline.utcoffset() is None or clock.utcoffset() is None or clock >= deadline:
        raise ValueError("SESSION_RESET_ORIGINAL_DEADLINE_EXPIRED")
    pid = binding.get("runner_pid")
    if type(pid) is not int or pid <= 0:
        raise ValueError("SESSION_RESET_ORIGINAL_RUNNER_UNPROVEN")
    os.kill(pid, 0)
    evidence = request["failures"][-1]["evidence"]
    fingerprint = evidence["trade_account_fingerprint"]
    state_dir = request_path.parent.parent.parent
    account_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
    health_path = state_dir / "credential_health" / (account_hash + ".json")
    adapter = FounderscNativeAXBrokerAdapter(native=native,
        expected_fund_account_fingerprint=fingerprint, credential_health_path=health_path)
    reset_path = request_path.with_suffix(".session-reset.json")

    def verify_owner():
        fresh = json.loads(request_path.read_text())
        if fresh.get("status") != "waiting" or fresh.get("binding") != binding or fresh.get("request_sha256") != request["request_sha256"]:
            raise ValueError("SESSION_RESET_OWNER_REQUEST_MISMATCH")
        if now() >= deadline:
            raise ValueError("SESSION_RESET_ORIGINAL_DEADLINE_EXPIRED")
        os.kill(pid, 0)

    with app_session(), reset_path.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        verify_owner()
        health = adapter._previous_credential_health()
        record = json.loads(reset_path.read_text()) if reset_path.exists() else None
        if record and (record["request_sha256"] != request["request_sha256"]
                       or record["account_hash"] != account_hash
                       or record["owner_thread_id"] != binding["owner_thread_id"]
                       or record.get("record_sha256") != _hash({k:v for k,v in record.items() if k != "record_sha256"})):
            raise ValueError("SESSION_RESET_CLAIM_MISMATCH")

        def save(state, **facts):
            nonlocal record
            record = {**record, "state": state, **facts}
            record.pop("record_sha256", None)
            record["record_sha256"] = _hash(record)
            _write(reset_path, record)

        def probe_login():
            payload = native.probe().as_dict()
            if (payload.get("surface_state") != "client_login_required"
                    or payload.get("screen_locked") is not False
                    or payload.get("trade_account_fingerprint_count") != 1
                    or payload.get("trade_account_fingerprint") != fingerprint
                    or payload.get("unlock_failure_category") in {"account_locked", "attempt_budget_exhausted", "trade_password_incorrect"}
                    or type(payload.get("unlock_remaining_attempts")) is int and payload["unlock_remaining_attempts"] <= 1):
                raise ValueError("SESSION_RESET_NEW_LOGIN_ACCOUNT_UNPROVEN")
            if now() >= deadline:
                raise ValueError("SESSION_RESET_ORIGINAL_DEADLINE_EXPIRED")
            return payload

        if phase == "restart":
            if record is not None:
                raise ValueError("SESSION_RESET_ALREADY_CLAIMED_READBACK_ONLY")
            if (health.get("trade_account_fingerprint") != fingerprint
                    or dependency_user_action("", health).get("recovery_kind") != "app_session_reset"):
                raise ValueError("SESSION_RESET_REJECTION_OR_NO_ACTION_UNPROVEN")
            record = {"schema_version": 1, "request_sha256": request["request_sha256"],
                "account_hash": account_hash, "previous_attempt_id": health.get("attempt_id"),
                "previous_health_sha256": _hash(health),
                "attempt_id": uuid.uuid4().hex, "owner_thread_id": binding["owner_thread_id"],
                "preparation_deadline": deadline.isoformat(), "claimed_at": clock.isoformat()}
            save("termination_claimed")
            verify_owner()
            result = native.terminate_rejected_session(expected_fingerprint=fingerprint).as_dict()
            termination_path = request_path.with_suffix(".session-reset-termination.json")
            if termination_path.exists():
                raise ValueError("SESSION_RESET_TERMINATION_EVIDENCE_CONFLICT")
            _write(termination_path, result)
            save("termination_observed", termination_receipt_path=str(termination_path),
                 termination_receipt_sha256=_hash(result))
            if result.get("status") != "session_terminated" or (result.get("action") or {}).get("succeeded") is not True:
                save("termination_unproven")
                raise ValueError("SESSION_RESET_TERMINATION_UNPROVEN")
            save("launch_claimed")
            verify_owner()
            launched = (launch or (lambda: subprocess.run(
                ["/usr/bin/open", "-b", "com.fzzq.Mac2020"], capture_output=True, timeout=15)))()
            if launched.returncode != 0:
                raise ValueError("SESSION_RESET_FIXED_BUNDLE_LAUNCH_UNPROVEN")
            save("launched")
            return {"status": "restarted", "reset_path": str(reset_path),
                "next_action": "select_trade_account_then_reprobe_and_fill", "preparation_deadline": deadline.isoformat()}
        if record is None:
            raise ValueError("SESSION_RESET_ORIGINAL_CLAIM_REQUIRED")
        if phase == "fill":
            if record["state"] != "launched":
                raise ValueError("SESSION_RESET_FILL_ALREADY_CLAIMED")
            if _hash(health) != record.get("previous_health_sha256") or dependency_user_action("", health).get("recovery_kind") != "app_session_reset":
                raise ValueError("SESSION_RESET_CREDENTIAL_FENCE_CHANGED")
            probe_login()
            verify_owner()
            save("password_fill_claimed")
            adapter._save_credential_health({"trade_account_fingerprint": fingerprint,
                "state": "attempt_claimed", "attempt_id": record["attempt_id"],
                "stage": "fresh_client_login_after_session_reset", "observed_at": now().isoformat(),
                "previous_attempt_id": record["previous_attempt_id"], "reset_request_sha256": request["request_sha256"]})
            filled = native.fill_client_login_from_keychain(explicitly_enabled=True).as_dict()
            if (filled.get("status") != "client_login_password_filled"
                    or filled.get("trade_account_fingerprint") != fingerprint
                    or filled.get("trade_account_fingerprint_count") != 1):
                raise ValueError("SESSION_RESET_PASSWORD_FILL_UNPROVEN")
            fill_path = request_path.with_suffix(".session-reset-fill.json")
            if fill_path.exists():
                raise ValueError("SESSION_RESET_FILL_EVIDENCE_CONFLICT")
            _write(fill_path, filled)
            save("captcha_waiting", fill_status="client_login_password_filled",
                 fill_receipt_path=str(fill_path), fill_receipt_sha256=_hash(filled))
            return {"status": "captcha_waiting", "reset_path": str(reset_path),
                "next_action": "fresh_screenshot_four_digits_readback_then_claim_login"}
        if phase == "claim-login":
            if record["state"] != "captcha_waiting":
                raise ValueError("SESSION_RESET_LOGIN_ALREADY_CLAIMED")
            if (health.get("state") != "attempt_claimed" or health.get("attempt_id") != record["attempt_id"]
                    or health.get("reset_request_sha256") != request["request_sha256"]):
                raise ValueError("SESSION_RESET_CREDENTIAL_FENCE_CHANGED")
            probe_login()
            verify_owner()
            save("login_confirmation_claimed")
            return {"status": "login_confirmation_claimed", "next_action": "press_unique_login_once_then_finish"}
        if phase == "finish":
            if record["state"] not in {"launched", "captcha_waiting", "login_confirmation_claimed"}:
                raise ValueError("SESSION_RESET_FINISH_ALREADY_CLAIMED")
            confirmed_login = record["state"] == "login_confirmation_claimed"
            save("finish_claimed")
            verify_owner()
            payload = native.probe().as_dict()
            if confirmed_login and payload.get("surface_state") == "authentication_required":
                # A newly authenticated session can auto-lock before the
                # ordinary trade page is opened. This is a separate unlock,
                # never a replay of the already confirmed client Login.
                if (health.get("state") != "attempt_claimed"
                        or health.get("attempt_id") != record["attempt_id"]
                        or health.get("reset_request_sha256") != request["request_sha256"]
                        or payload.get("trade_account_fingerprint") != fingerprint
                        or payload.get("trade_account_fingerprint_count") != 1
                        or payload.get("screen_locked") is not False
                        or payload.get("unlock_failure_category") is not None
                        or type(payload.get("unlock_remaining_attempts")) is int and payload["unlock_remaining_attempts"] <= 1):
                    raise ValueError("SESSION_RESET_NEW_SESSION_UNLOCK_UNPROVEN")
                verify_owner()
                unlock_id = uuid.uuid4().hex
                save("post_login_unlock_claimed", post_login_unlock_attempt_id=unlock_id)
                adapter._save_credential_health({"state": "attempt_claimed", "attempt_id": unlock_id,
                    "trade_account_fingerprint": fingerprint, "parent_attempt_id": record["attempt_id"],
                    "reset_request_sha256": request["request_sha256"],
                    "stage": "new_authenticated_session_autolock", "observed_at": now().isoformat()})
                unlocked = native.unlock_from_keychain(explicitly_enabled=True).as_dict()
                if (unlocked.get("status") != "unlocked" or unlocked.get("trade_account_fingerprint") != fingerprint
                        or (unlocked.get("action") or {}).get("unlock_path_proven") is not True):
                    raise ValueError("SESSION_RESET_NEW_SESSION_UNLOCK_UNPROVEN")
            # A manual same-account recovery can also finish the one request.
            adapter.ensure_native_ready(require_order_capability=True, unlock_once=False)
            if now() >= deadline:
                raise ValueError("SESSION_RESET_ORIGINAL_DEADLINE_EXPIRED")
            save("ready", verified_at=now().isoformat())
            verify_owner()
            result = signal_recheck(request_path)
            return {**result, "reset_path": str(reset_path), "status": "account_ready_recheck_signalled"}
        raise ValueError("SESSION_RESET_PHASE_INVALID")
