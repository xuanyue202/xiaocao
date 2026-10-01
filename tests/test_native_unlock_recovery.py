"""Password confirmations stay fenced until independent account readiness."""
from __future__ import annotations

import json

import pytest

from xiaocao.live.foundersc_native_ax import FounderscNativeAXError, NativeAXReceipt
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter

pytestmark = pytest.mark.app_simulation
ACCOUNT = "123******890"


class UnlockNative:
    def __init__(self, *, post_surface="authentication_required", post_account=ACCOUNT):
        self.calls = 0
        self.post_surface = post_surface
        self.post_account = post_account

    def probe(self, *, table_audit=False):
        return NativeAXReceipt({
            "status": self.post_surface if self.calls else "authentication_required",
            "surface_state": self.post_surface if self.calls else "authentication_required",
            "trade_account_fingerprint": self.post_account if self.calls else ACCOUNT,
            "trade_account_fingerprint_count": 1,
            "app_running": True, "screen_locked": False, "accessibility_trusted": True,
            "helper_version": 14, "capabilities": {},
        })

    def unlock_from_keychain(self, *, explicitly_enabled):
        assert explicitly_enabled
        self.calls += 1
        return NativeAXReceipt({"status": "unlocked", "surface_state": "query_only",
            "secure_field_cleared_before_set": True,
            "action": {"attempted": True, "confirm_pressed": True}})


@pytest.mark.parametrize("surface,account", [
    ("authentication_required", ACCOUNT), ("query_only", "999******999"),
])
def test_helper_success_cannot_clear_claim_before_bound_fresh_probe(tmp_path, surface, account):
    native = UnlockNative(post_surface=surface, post_account=account)
    health = tmp_path / "health.json"
    def adapter():
        return FounderscNativeAXBrokerAdapter(native=native,
            expected_fund_account_fingerprint=ACCOUNT, credential_health_path=health)
    with pytest.raises(FounderscNativeAXError):
        adapter().ensure_native_ready(unlock_once=True)
    assert json.loads(health.read_text())["state"] == "unproven_no_retry"
    if surface == "authentication_required":
        with pytest.raises(FounderscNativeAXError, match="PRIOR_ATTEMPT"):
            adapter().ensure_native_ready(unlock_once=True)
    assert native.calls == 1


@pytest.mark.parametrize("helper_status", ["unlocked", "unlock_unproven"])
def test_slow_refresh_uses_only_bounded_reads_and_preserves_attempt(tmp_path, monkeypatch, helper_status):
    sleeps = []
    monkeypatch.setattr("xiaocao.live.foundersc_native_broker.time.sleep", sleeps.append)
    class SlowNative(UnlockNative):
        post_reads = 0
        def probe(self, *, table_audit=False):
            if self.calls:
                self.post_reads += 1
                if self.post_reads == 3:
                    self.post_surface = "query_only"
            return super().probe(table_audit=table_audit)
        def unlock_from_keychain(self, *, explicitly_enabled):
            result = super().unlock_from_keychain(explicitly_enabled=explicitly_enabled).as_dict()
            result["status"] = helper_status
            return NativeAXReceipt(result)
    native = SlowNative()
    health = tmp_path / "health.json"
    adapter = FounderscNativeAXBrokerAdapter(native=native,
        expected_fund_account_fingerprint=ACCOUNT, credential_health_path=health)
    result = adapter.ensure_native_ready(unlock_once=True)
    assert result["account_binding"] == "proven" and native.calls == 1
    assert sleeps == [0.25, 0.75]
    receipt = json.loads(health.read_text())
    assert receipt["readback_attempts"] == 3 and receipt["stage"] == "ready"
    archived = list((tmp_path / "health-attempts").glob("*.json"))
    assert len(archived) == 1 and json.loads(archived[0].read_text()) == receipt


def test_error_receipt_never_reconfirms_or_polls_to_hide_wrong_password(tmp_path):
    class ErrorNative(UnlockNative):
        def unlock_from_keychain(self, *, explicitly_enabled):
            result = super().unlock_from_keychain(explicitly_enabled=explicitly_enabled).as_dict()
            result.update(status="unlock_unproven", unlock_failure_category="trade_password_incorrect",
                unlock_remaining_attempts=4)
            return NativeAXReceipt(result)
        def probe(self, *, table_audit=False):
            assert not self.calls, "Wrong-password receipt must stop immediately"
            return super().probe(table_audit=table_audit)
    adapter = FounderscNativeAXBrokerAdapter(native=ErrorNative(),
        expected_fund_account_fingerprint=ACCOUNT, credential_health_path=tmp_path / "health.json")
    with pytest.raises(FounderscNativeAXError, match="TRADE_PASSWORD_INCORRECT:remaining=4"):
        adapter.ensure_native_ready(unlock_once=True)
    assert adapter.credential_health["state"] == "unproven_no_retry"


def test_success_receipt_followed_by_transport_failure_stays_fenced(tmp_path):
    class BrokenProbe(UnlockNative):
        def probe(self, *, table_audit=False):
            if self.calls:
                raise FounderscNativeAXError("NATIVE_AX_COMMAND_TIMEOUT")
            return super().probe(table_audit=table_audit)
    native = BrokenProbe()
    health = tmp_path / "health.json"
    adapter = FounderscNativeAXBrokerAdapter(native=native,
        expected_fund_account_fingerprint=ACCOUNT, credential_health_path=health)
    with pytest.raises(FounderscNativeAXError, match="TIMEOUT"):
        adapter.ensure_native_ready(unlock_once=True)
    receipt = json.loads(health.read_text())
    assert receipt["state"] == "unproven_no_retry"
    assert receipt["stage"] == "readback_transport_unproven"
    assert native.calls == 1


def test_unlock_diagnostics_do_not_persist_arbitrary_helper_text():
    result = FounderscNativeAXBrokerAdapter._sanitized_unlock_evidence({"unlock_evidence": {
        "stage": "PASSWORD_TEXT", "total_ms": float("nan"), "password": "fixture-secret",
        "snapshots": [{"phase": "preconfirm", "window_bounds": {"x": "fixture-secret"},
            "secure_field_value": "fixture-secret", "account_bound": True, "window_count": 1}],
    }})
    assert "fixture-secret" not in json.dumps(result)
    assert "PASSWORD_TEXT" not in json.dumps(result)
    assert result["snapshots"] == [{"phase": "preconfirm", "account_bound": True, "window_count": 1}]
