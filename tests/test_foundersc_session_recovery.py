"""Original-owner one-reset and one-login fences; no real APP actions."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from xiaocao.runner_recovery import _hash
from xiaocao.live.foundersc_session_recovery import recover_session
from xiaocao.live.foundersc_native_ax import FounderscNativeAXError
from xiaocao.live.morning_observability import dependency_user_action
from scripts.book_b_live_morning import _automatic_dependency_retry

pytestmark = [pytest.mark.app_simulation, pytest.mark.app_authentication]
NOW = datetime(2026, 10, 12, 1, 3, tzinfo=timezone.utc)
FP = "263******022"


class Native:
    def __init__(self):
        self.actions = []
        self.payload = {"surface_state": "client_login_required", "screen_locked": False,
            "trade_account_fingerprint_count": 1, "trade_account_fingerprint": FP,
            "app_running": True, "accessibility_trusted": True, "secure_field_count": 1}
    def reply(self, payload): return SimpleNamespace(as_dict=lambda: dict(payload))
    def probe(self, **kwargs): return self.reply(self.payload)
    def terminate_rejected_session(self, **kwargs):
        self.actions.append("terminate")
        return self.reply({"status": "session_terminated", "action": {"succeeded": True}})
    def fill_client_login_from_keychain(self, **kwargs):
        self.actions.append("fill")
        return self.reply({"status": "client_login_password_filled", "trade_account_fingerprint": FP,
            "trade_account_fingerprint_count": 1})


def fixture(root, monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-book-b-live-morning")
    monkeypatch.setenv("CODEX_THREAD_ID", "original-owner")
    path = root / "runs/dependencies/request.json"
    path.parent.mkdir(parents=True)
    health = {"state": "not_attempted", "password_action_attempted": False,
        "confirmation_pressed": False, "failure_category": "trade_password_incorrect",
        "trade_account_fingerprint": FP, "attempt_id": "a"*32}
    binding = {"automation_id": "xiaocao-book-b-live-morning", "owner_thread_id": "original-owner",
        "runner_pid": os.getpid(), "preparation_deadline": (NOW+timedelta(minutes=30)).isoformat()}
    record = {"binding": binding, "request_sha256": _hash(binding), "status": "waiting", "sequence": 1,
        "failures": [{"evidence": health}]}
    path.write_text(json.dumps(record))
    hp = root / "credential_health" / (hashlib.sha256(FP.encode()).hexdigest()+".json")
    hp.parent.mkdir(); hp.write_text(json.dumps(health))
    return path, hp


def step(path, native, phase):
    return recover_session(path, native=native, phase=phase, now=lambda: NOW,
        launch=lambda: SimpleNamespace(returncode=0))


def test_stale_no_action_error_routes_to_reset_instead_of_655_unlock_probes():
    health = {"state": "not_attempted", "password_action_attempted": False,
        "confirmation_pressed": False, "failure_category": "trade_password_incorrect"}
    health["user_action"] = dependency_user_action("NATIVE_AX_UNLOCK_NOT_ATTEMPTED", health)
    assert health["user_action"]["recovery_kind"] == "app_session_reset"
    assert not _automatic_dependency_retry({"code": "NATIVE_AX_UNLOCK_NOT_ATTEMPTED", "evidence": health})


def test_original_request_one_restart_fill_and_login_claim(tmp_path, monkeypatch):
    path, hp = fixture(tmp_path, monkeypatch); native = Native()
    assert step(path, native, "restart")["status"] == "restarted"
    with pytest.raises(ValueError, match="ALREADY_CLAIMED"):
        step(path, native, "restart")
    assert step(path, native, "fill")["status"] == "captcha_waiting"
    with pytest.raises(ValueError, match="ALREADY_CLAIMED"):
        step(path, native, "fill")
    assert json.loads(hp.read_text())["state"] == "attempt_claimed"
    assert step(path, native, "claim-login")["status"] == "login_confirmation_claimed"
    with pytest.raises(ValueError, match="ALREADY_CLAIMED"):
        step(path, native, "claim-login")
    assert native.actions == ["terminate", "fill"]


@pytest.mark.parametrize("fault", ["owner", "automation", "deadline", "uncertain", "account", "request_hash"])
def test_invalid_or_uncertain_original_stops_before_any_reset(tmp_path, monkeypatch, fault):
    path, hp = fixture(tmp_path, monkeypatch); native = Native()
    if fault == "owner": monkeypatch.setenv("CODEX_THREAD_ID", "other-owner")
    if fault == "automation": monkeypatch.setenv("CODEX_AUTOMATION_ID", "other-automation")
    if fault == "deadline":
        record=json.loads(path.read_text()); record["binding"]["preparation_deadline"]=NOW.isoformat()
        record["request_sha256"]=_hash(record["binding"]); path.write_text(json.dumps(record))
    if fault in {"uncertain", "account"}:
        health=json.loads(hp.read_text())
        if fault == "uncertain": health.update(state="unproven_no_retry", failure_category="transport_unproven")
        else: health["trade_account_fingerprint"]="999******999"
        hp.write_text(json.dumps(health))
    if fault == "request_hash":
        record=json.loads(path.read_text()); record["request_sha256"]="bad";path.write_text(json.dumps(record))
    with pytest.raises((ValueError, FounderscNativeAXError)): step(path, native, "restart")
    assert native.actions == []


def test_timeout_after_reset_claim_cannot_repeat_termination(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch); native = Native()
    def lost(**kwargs): native.actions.append("terminate"); raise RuntimeError("transport_lost")
    native.terminate_rejected_session=lost
    with pytest.raises(RuntimeError): step(path, native, "restart")
    with pytest.raises(ValueError, match="ALREADY_CLAIMED"): step(path, native, "restart")
    assert native.actions == ["terminate"]


@pytest.mark.parametrize("attempted", [False, True])
def test_failed_termination_preserves_native_action_evidence_without_replay(tmp_path, monkeypatch, attempted):
    path, _ = fixture(tmp_path, monkeypatch)
    native = Native()
    result = {"status": "session_reset_unproven", "reason": "bound termination not proven",
        "action": {"attempted": attempted, "succeeded": False, "confirm_pressed": False}}
    def failed(**kwargs):
        native.actions.append("terminate")
        return native.reply(result)
    native.terminate_rejected_session = failed
    with pytest.raises(ValueError, match="TERMINATION_UNPROVEN"):
        step(path, native, "restart")
    record = json.loads(path.with_suffix(".session-reset.json").read_text())
    receipt = Path(record["termination_receipt_path"])
    assert json.loads(receipt.read_text()) == result
    assert record["termination_receipt_sha256"] == _hash(result)
    assert record["state"] == "termination_unproven"
    with pytest.raises(ValueError, match="ALREADY_CLAIMED"):
        step(path, native, "restart")
    assert native.actions == ["terminate"]


def test_wrong_new_login_account_never_reads_saved_password(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch); native = Native();step(path, native, "restart")
    native.payload["trade_account_fingerprint"]="999******999"
    with pytest.raises(ValueError, match="NEW_LOGIN_ACCOUNT_UNPROVEN"): step(path, native, "fill")
    assert native.actions == ["terminate"]


def test_ready_readback_closes_fence_and_signals_original_once(tmp_path, monkeypatch):
    path, hp = fixture(tmp_path, monkeypatch); native = Native()
    for phase in ("restart", "fill", "claim-login"): step(path, native, phase)
    native.payload.update(surface_state="trade_ready", secure_field_count=0, side="buy", helper_version=16,
        capabilities={"prepare": True, "submit": True})
    assert step(path, native, "finish")["status"] == "account_ready_recheck_signalled"
    assert json.loads(hp.read_text())["state"] == "verified_by_account_bound_readback"
    signal = path.with_suffix(".resume.json").read_bytes()
    with pytest.raises(ValueError, match="ALREADY_CLAIMED"): step(path, native, "finish")
    assert path.with_suffix(".resume.json").read_bytes() == signal


def test_waiting_for_session_lock_rechecks_original_deadline(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import xiaocao.live.foundersc_session_recovery as recovery
    path, _ = fixture(tmp_path, monkeypatch); native = Native(); clock = [NOW]
    @contextmanager
    def delayed():
        clock[0] += timedelta(hours=1)
        yield
    monkeypatch.setattr(recovery, "app_session", delayed)
    with pytest.raises(ValueError, match="DEADLINE_EXPIRED"):
        recover_session(path, native=native, phase="restart", now=lambda: clock[0])
    assert native.actions == []


@pytest.mark.parametrize("phase", ["fill", "claim-login"])
def test_other_uncertain_attempt_cannot_be_overwritten(tmp_path, monkeypatch, phase):
    path, hp = fixture(tmp_path, monkeypatch); native = Native()
    step(path, native, "restart")
    if phase == "claim-login": step(path, native, "fill")
    before = list(native.actions)
    hp.write_text(json.dumps({"state": "unproven_no_retry", "attempt_id": "other", "trade_account_fingerprint": FP}))
    with pytest.raises(ValueError, match="CREDENTIAL_FENCE_CHANGED"): step(path, native, phase)
    assert native.actions == before
    assert json.loads(hp.read_text())["attempt_id"] == "other"


@pytest.mark.parametrize("fault", [None, "uncertain", "wrong_account", "error"])
def test_new_authenticated_session_autolock_is_a_separate_claim(tmp_path, monkeypatch, fault):
    path, hp = fixture(tmp_path, monkeypatch); native = Native()
    for phase in ("restart", "fill", "claim-login"): step(path, native, phase)
    native.payload["surface_state"] = "authentication_required"
    def unlock(**kwargs):
        native.actions.append("new-session-unlock")
        native.payload.update(surface_state="trade_ready", secure_field_count=0, side="buy", helper_version=16,
            capabilities={"prepare": True, "submit": True})
        return native.reply({"status": "unlocked", "trade_account_fingerprint": FP, "action": {"unlock_path_proven": True}})
    native.unlock_from_keychain = unlock
    if fault == "uncertain":
        h=json.loads(hp.read_text());h["state"]="unproven_no_retry";hp.write_text(json.dumps(h))
    if fault == "wrong_account": native.payload["trade_account_fingerprint"]="999******999"
    if fault == "error": native.payload["unlock_failure_category"]="trade_password_incorrect"
    if fault:
        original_claim = path.with_suffix(".session-reset.json").read_bytes()
        original_health = hp.read_bytes()
        with pytest.raises(ValueError): step(path, native, "finish")
        assert native.actions == ["terminate", "fill"]
        assert path.with_suffix(".session-reset.json").read_bytes() == original_claim
        assert hp.read_bytes() == original_health
    else:
        assert step(path, native, "finish")["status"] == "account_ready_recheck_signalled"
        assert native.actions == ["terminate", "fill", "new-session-unlock"]
        with pytest.raises(ValueError, match="ALREADY_CLAIMED"): step(path, native, "finish")


def test_premature_finish_keeps_login_claim_for_ordinary_readiness(tmp_path, monkeypatch):
    path, health_path = fixture(tmp_path, monkeypatch)
    native = Native()
    step(path, native, "restart")
    step(path, native, "fill")
    step(path, native, "claim-login")
    native.payload["surface_state"] = "query_only"
    result = step(path, native, "finish")
    assert result["status"] == "ordinary_trade_readback_required"
    record = json.loads(path.with_suffix(".session-reset.json").read_text())
    assert record["state"] == "login_confirmation_claimed"
    assert native.actions == ["terminate", "fill"]
    assert json.loads(health_path.read_text())["state"] == "attempt_claimed"
