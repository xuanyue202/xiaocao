"""Safe Founder Securities Keychain preflight.

The account identifiers and password bytes are process-local inputs only.  The
public receipt deliberately exposes cardinality, lengths, match booleans and
access status, never the account identifiers or secret values themselves.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable


LOGIN_SERVICE = "xiaocao.foundersc.quant.login"
TRADE_SERVICE = "xiaocao.foundersc.quant.trade"
SECURITY_COMMAND = "/usr/bin/security"

Runner = Callable[..., Any]

_ACCOUNT_PATTERN = re.compile(r'^\s*"acct"<blob>="(?P<account>.*)"$', re.MULTILINE)


@dataclass(frozen=True)
class _ItemRead:
    item_present: bool
    account: str
    secret_readable: bool
    secret_nonempty: bool
    secret_status: str


def _masked_fingerprint(account: str) -> str:
    value = str(account or "")
    if len(value) < 6:
        return ""
    return f"{value[:3]}******{value[-3:]}"


class FounderscKeychainPreflight:
    """Read the two fixed Keychain items without leaking their values."""

    def __init__(
        self,
        *,
        runner: Runner = subprocess.run,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.runner = runner
        self.timeout_seconds = max(0.1, float(timeout_seconds))

    def _metadata(self, service: str) -> tuple[bool, str]:
        command = [SECURITY_COMMAND, "find-generic-password", "-s", service]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, ""
        if int(getattr(completed, "returncode", 1)) != 0:
            return False, ""
        output = bytes(getattr(completed, "stdout", b"") or b"")
        error = bytes(getattr(completed, "stderr", b"") or b"")
        rendered = (output + b"\n" + error).decode("utf-8", errors="replace")
        match = _ACCOUNT_PATTERN.search(rendered)
        return True, match.group("account") if match else ""

    def _secret(self, service: str, *, requested: bool) -> tuple[bool, bool, str]:
        if not requested:
            return False, False, "not_requested"
        command = [
            SECURITY_COMMAND,
            "find-generic-password",
            "-w",
            "-s",
            service,
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return False, False, "timeout_or_acl_prompt"
        except OSError:
            return False, False, "security_command_unavailable"
        readable = int(getattr(completed, "returncode", 1)) == 0
        secret = bytes(getattr(completed, "stdout", b"") or b"").rstrip(b"\r\n")
        nonempty = readable and bool(secret)
        secret = b""
        return readable, nonempty, "readable" if readable else "security_command_denied"

    def _item(self, service: str, *, read_secret: bool) -> _ItemRead:
        item_present, account = self._metadata(service)
        readable, nonempty, status = self._secret(service, requested=read_secret)
        return _ItemRead(
            item_present=item_present,
            account=account,
            secret_readable=readable,
            secret_nonempty=nonempty,
            secret_status=status,
        )

    def run(
        self,
        *,
        observed_login_fingerprint: str = "",
        read_secrets: bool = False,
    ) -> dict[str, object]:
        login = self._item(LOGIN_SERVICE, read_secret=read_secrets)
        trade = self._item(TRADE_SERVICE, read_secret=read_secrets)
        observed = str(observed_login_fingerprint or "").strip()
        login_match = bool(observed) and _masked_fingerprint(login.account) == observed

        if not login.item_present or not trade.item_present:
            status = "keychain_item_missing"
        elif read_secrets and not (
            login.secret_readable
            and login.secret_nonempty
            and trade.secret_readable
            and trade.secret_nonempty
        ):
            status = "keychain_secret_access_blocked"
        elif observed and not login_match:
            status = "login_binding_mismatch"
        elif login_match:
            status = "login_binding_match_trade_page_binding_unavailable"
        else:
            status = "metadata_ready"

        return {
            "status": status,
            "login_item_present": login.item_present,
            "trade_item_present": trade.item_present,
            "login_account_present": bool(login.account),
            "trade_account_present": bool(trade.account),
            "login_account_length": len(login.account),
            "trade_account_length": len(trade.account),
            "page_fingerprint_present": bool(observed),
            "login_page_binding_match": login_match,
            "login_secret_readable": login.secret_readable,
            "login_secret_nonempty": login.secret_nonempty,
            "login_secret_status": login.secret_status,
            "trade_secret_readable": trade.secret_readable,
            "trade_secret_nonempty": trade.secret_nonempty,
            "trade_secret_status": trade.secret_status,
            "account_binding": "not_proven",
            "account_binding_reason": "trade_account_fingerprint_unavailable_on_page",
        }
