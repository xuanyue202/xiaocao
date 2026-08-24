"""Keychain-backed two-condition capital-action safety boundary.

xiaocao remains paper-by-default. This module is the seam that gates the isolated
Book-B real-capital path. It is borrowed in spirit from QuantDinger's two
non-negotiable safety properties (MCP_SETUP.md): *paper-only by default*, and
*live execution requires BOTH a token flag AND a server flag*; plus the design
principle that **research never shares a code path with live capital**.

Contract (also stated in docs/OPERATING_CONTRACT.md):

  - Paper / sensor / research actions are ALWAYS allowed — research must never be
    blocked by the capital gate, and the daily sensor (book A, data capture) must
    never stop.
  - A REAL-CAPITAL action (an order that moves real money at a broker) requires
    TWO required conditions, neither of which the scheduled live task creates:
      1. `XIAOCAO_LIVE_TRADING_ENABLED=true`                 (operational toggle)
      2. A signed authorization file (default `output/live/live_authorization.json`)
         whose HMAC validates against `XIAOCAO_LIVE_SIGNING_KEY`.  The 09:20
         runner obtains both values from fixed macOS Keychain items through
         `capital_keychain.py` and passes this mapping in-process only; neither
         value is installed in `os.environ`, argv, logs, or receipts.  The
         authorization is **scoped** (max per-order notional, optional side/code
         allowlist) and **expires**. It is normally minted by the interactive
         `scripts/authorize_live.py`, never by the scheduled task.

  Both Keychain items and the authorization HMAC belong to the same macOS login
  principal. This is therefore an operator-approved runtime gate, not two
  cryptographically independent principals and not proof that another process
  running as the same user could never mint a file.

  Every decision — ALLOW or DENY — is appended to `output/live/safety_audit.jsonl`.

The Founder bridge must pass through `require_capital_action(...)` before its
single submit boundary, and the contract tests prove missing conditions deny it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Action kinds that NEVER require a capital key. Research/sensor/paper must run
# unconditionally so the compounding loop and the kill-switch sensor stay alive.
ALWAYS_ALLOWED_KINDS = frozenset({"paper", "sensor", "research", "simulation"})
REAL_CAPITAL_KIND = "real_capital"

DEFAULT_AUTH_PATH = Path("output/live/live_authorization.json")
DEFAULT_AUDIT_PATH = Path("output/live/safety_audit.jsonl")

ENV_LIVE_ENABLED = "XIAOCAO_LIVE_TRADING_ENABLED"
ENV_SIGNING_KEY = "XIAOCAO_LIVE_SIGNING_KEY"

# Fields covered by the HMAC signature (sorted, compact JSON). `signature` itself
# is excluded. Changing this list is a breaking change to issued authorizations.
SIGNED_FIELDS = ("scope", "max_notional", "sides", "codes", "expires_at", "issued_at", "note")


class CapitalActionDenied(RuntimeError):
    """Raised when a real-capital action is attempted without both valid keys."""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    kind: str
    reason: str
    code: str | None = None
    side: str | None = None
    notional: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Signing (used by scripts/authorize_live.py to mint, and here to verify).
# --------------------------------------------------------------------------- #
def _canonical_payload(auth: dict[str, Any]) -> bytes:
    body = {k: auth.get(k) for k in SIGNED_FIELDS}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(auth: dict[str, Any], signing_key: str) -> str:
    """Return the hex HMAC-SHA256 of the authorization's signed fields."""
    return hmac.new(signing_key.encode("utf-8"), _canonical_payload(auth), hashlib.sha256).hexdigest()


def make_authorization(
    *,
    scope: str,
    max_notional: float,
    signing_key: str,
    sides: list[str] | None = None,
    codes: list[str] | None = None,
    expires_at: str,
    issued_at: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Build a signed authorization dict. `expires_at`/`issued_at` are ISO-8601.

    Used by the interactive minting CLI; the agent path only ever *verifies*.
    """
    normalized_max = float(max_notional)
    if not math.isfinite(normalized_max) or normalized_max <= 0:
        raise ValueError("max_notional must be finite and positive")
    auth: dict[str, Any] = {
        "scope": scope,
        "max_notional": normalized_max,
        "sides": sorted(sides) if sides else None,
        "codes": sorted(codes) if codes else None,
        "expires_at": expires_at,
        "issued_at": issued_at or _utcnow().isoformat(timespec="seconds"),
        "note": note,
    }
    auth["signature"] = sign_payload(auth, signing_key)
    return auth


# --------------------------------------------------------------------------- #
# Verification + the gate.
# --------------------------------------------------------------------------- #
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    # Fail-closed on a NAIVE expiry: relabeling it UTC (the old behavior) silently
    # widens the real-capital window by the minter's local offset (8h for China
    # time) — a fail-OPEN on the expiry key. A hand-minted authorization MUST carry
    # an explicit tz offset; scripts/authorize_live.py already emits tz-aware UTC.
    if dt.tzinfo is None:
        return None
    return dt


def live_trading_enabled(env: dict[str, str] | None = None) -> bool:
    src = os.environ if env is None else env
    return src.get(ENV_LIVE_ENABLED) == "true"


def load_authorization(
    *,
    auth_path: Path = DEFAULT_AUTH_PATH,
    env: dict[str, str] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Load + verify the authorization file. Returns (auth, reason).

    auth is None on any failure (missing file, missing/invalid signing key,
    tampered signature, or expired). The reason string is audit-friendly.
    """
    src = os.environ if env is None else env
    if not auth_path.exists():
        return None, "no authorization file"
    signing_key = str(src.get(ENV_SIGNING_KEY, "")).strip()
    if not signing_key:
        return None, f"{ENV_SIGNING_KEY} not set"
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return None, f"unreadable authorization: {type(exc).__name__}"
    if not isinstance(auth, dict):
        return None, "authorization is not an object"
    provided = str(auth.get("signature") or "")
    expected = sign_payload(auth, signing_key)
    try:
        # compare_digest raises TypeError on non-ASCII str inputs; a crafted
        # non-ASCII signature must deny cleanly (and be audited), not crash.
        sig_ok = bool(provided) and hmac.compare_digest(provided, expected)
    except (TypeError, ValueError):
        sig_ok = False
    if not sig_ok:
        return None, "invalid signature (tampered or wrong signing key)"
    expires = _parse_iso(auth.get("expires_at"))
    if expires is None:
        return None, "authorization missing/invalid expires_at"
    if (now or _utcnow()) >= expires:
        return None, f"authorization expired at {auth.get('expires_at')}"
    try:
        max_notional = float(auth.get("max_notional"))
    except (TypeError, ValueError):
        return None, "authorization missing/invalid max_notional"
    if not math.isfinite(max_notional) or max_notional <= 0:
        return None, "authorization missing/invalid max_notional"
    return auth, "authorization valid"


def authorize_capital_action(
    *,
    kind: str,
    side: str | None = None,
    code: str | None = None,
    notional: float | None = None,
    auth_path: Path = DEFAULT_AUTH_PATH,
    audit_path: Path | None = DEFAULT_AUDIT_PATH,
    env: dict[str, str] | None = None,
    now: datetime | None = None,
) -> Decision:
    """The gate. Returns a Decision; ALWAYS writes an audit row (unless
    audit_path is None). Does not raise — callers wanting fail-closed semantics
    use `require_capital_action`.
    """
    kind = str(kind or "").strip().lower()

    if kind in ALWAYS_ALLOWED_KINDS:
        decision = Decision(True, kind, "always-allowed (paper/sensor/research)", code, side, notional)
        _audit(decision, audit_path)
        return decision

    if kind != REAL_CAPITAL_KIND:
        decision = Decision(False, kind, f"unknown action kind {kind!r}; deny-by-default", code, side, notional)
        _audit(decision, audit_path)
        return decision

    # Real-capital path: require BOTH configured conditions.
    if not live_trading_enabled(env):
        decision = Decision(False, kind, f"key 1 missing: {ENV_LIVE_ENABLED} != true", code, side, notional)
        _audit(decision, audit_path)
        return decision

    auth, reason = load_authorization(auth_path=auth_path, env=env, now=now)
    if auth is None:
        decision = Decision(False, kind, f"key 2 missing: {reason}", code, side, notional)
        _audit(decision, audit_path)
        return decision

    # Scope checks — FAIL CLOSED: if the authorization restricts an attribute but
    # the action leaves it unspecified (None), that is a DENY, not a skip. An
    # omitted notional must never bypass the max_notional cap.
    sides = auth.get("sides")
    if sides and (side is None or side.upper() not in {str(s).upper() for s in sides}):
        decision = Decision(False, kind, f"side {side!r} outside/unspecified for authorized scope {sides}", code, side, notional)
        _audit(decision, audit_path)
        return decision

    codes = auth.get("codes")
    if codes and (code is None or code not in set(codes)):
        decision = Decision(False, kind, f"code {code!r} outside/unspecified for authorized scope", code, side, notional)
        _audit(decision, audit_path)
        return decision

    max_notional = float(auth["max_notional"])
    try:
        normalized_notional = float(notional) if notional is not None else None
    except (TypeError, ValueError):
        normalized_notional = None
    notional_is_valid = (
        normalized_notional is not None
        and math.isfinite(normalized_notional)
        and normalized_notional > 0
    )
    if (
        not notional_is_valid
        or normalized_notional > max_notional + 1e-6
    ):
        audited_notional = normalized_notional if notional_is_valid else None
        decision = Decision(
            False, kind,
            f"notional {notional!r} invalid, unspecified, or exceeds authorized max {max_notional:.2f}",
            code, side, audited_notional,
        )
        _audit(decision, audit_path)
        return decision

    decision = Decision(
        True, kind, "keychain-backed capital gate authorized",
        code, side, notional,
        details={"scope": auth.get("scope"), "expires_at": auth.get("expires_at")},
    )
    # A real-capital ALLOW MUST be durably audited (OPERATING_CONTRACT §9). If the
    # audit cannot be written, fail closed rather than place an un-auditable order.
    if not _audit(decision, audit_path):
        denied = Decision(False, kind, "audit write failed — denying un-auditable real-capital action", code, side, notional)
        _audit(denied, audit_path)
        return denied
    return decision


def require_capital_action(**kwargs: Any) -> Decision:
    """Fail-closed wrapper: raises CapitalActionDenied if the action is denied.

    The ONLY supported way to reach a real broker order. A broker bridge must
    call this and place the order only on the returned (allowed) Decision.
    """
    decision = authorize_capital_action(**kwargs)
    if not decision.allowed:
        raise CapitalActionDenied(decision.reason)
    return decision


def _audit(decision: Decision, audit_path: Path | None) -> bool:
    """Append one audit row. Returns True if written (or auditing disabled). A
    real-capital ALLOW uses the return value to fail closed when it cannot be
    durably recorded; DENY/always-allowed rows stay best-effort so auditing never
    crashes the trading loop."""
    if audit_path is None:
        return True
    row = {
        "ts": _utcnow().isoformat(timespec="seconds"),
        "allowed": decision.allowed,
        "kind": decision.kind,
        "reason": decision.reason,
        "code": decision.code,
        "side": decision.side,
        "notional": decision.notional,
        **({"details": decision.details} if decision.details else {}),
    }
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        return True
    except OSError:
        return False
