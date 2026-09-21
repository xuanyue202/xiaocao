from __future__ import annotations

import pytest

from xiaocao.live.foundersc_native_ax import FounderscNativeAXError, NativeAXReceipt
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter


class WrongTradePasswordNative:
    def probe(self, *, table_audit: bool = False) -> NativeAXReceipt:
        assert table_audit is True
        return NativeAXReceipt({
            "status": "authentication_required",
            "surface_state": "authentication_required",
            "app_running": True,
            "accessibility_trusted": True,
            "screen_locked": False,
            "trade_account_fingerprint": "123******890",
            "trade_account_fingerprint_count": 1,
            "capabilities": {"prepare": False, "submit": False},
        })

    def unlock_from_keychain(self, *, explicitly_enabled: bool) -> NativeAXReceipt:
        assert explicitly_enabled is True
        return NativeAXReceipt({
            "status": "unlock_unproven",
            "surface_state": "authentication_required",
            "unlock_failure_category": "trade_password_incorrect",
            "unlock_remaining_attempts": 4,
            "secure_field_cleared_before_set": True,
        })


def test_unlock_failure_preserves_only_sanitized_category_and_attempt_budget() -> None:
    adapter = FounderscNativeAXBrokerAdapter(
        native=WrongTradePasswordNative(),
        expected_fund_account_fingerprint="123******890",
    )

    with pytest.raises(
        FounderscNativeAXError,
        match=(
            "NATIVE_AX_UNLOCK_UNPROVEN_NO_RETRY:TRADE_PASSWORD_INCORRECT:"
            "remaining=4:field_cleared=true"
        ),
    ):
        adapter.ensure_native_ready(unlock_once=True)
