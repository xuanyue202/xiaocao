"""User-authorized authentication-only APP tests, without order effects.

On 2026-10-13 the user explicitly exempted login repair/tests from the market
hours test window. An opt-in must never authorize order preparation/submission,
cancellation, or a strategy/accounting runner.
"""
from __future__ import annotations
import os

AUTH_TEST_ENV = "XIAOCAO_APP_AUTHENTICATION_TEST"
AUTH_COMMANDS = frozenset({"probe", "version", "check-dialogs", "focus-unlock",
    "terminate-rejected-session", "unlock-stdin", "fill-client-login-stdin", "read-query", "open-order-surface", "open-query-surface"})


def authentication_test_mode() -> bool:
    return os.environ.get(AUTH_TEST_ENV) == "1"


def require_authentication_command(command: str) -> None:
    if authentication_test_mode() and command not in AUTH_COMMANDS:
        raise RuntimeError("AUTHENTICATION_TEST_ORDER_ACTION_FORBIDDEN:" + command)
