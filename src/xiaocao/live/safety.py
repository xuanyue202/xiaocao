"""Two-key capital-action safety boundary.

xiaocao is **paper-only today**. This module is the *seam* that keeps it that way
by construction, and makes the eventual paper -> real transition a config flip
rather than a refactor. It is borrowed in spirit from QuantDinger's two
non-negotiable safety properties (MCP_SETUP.md): *paper-only by default*, and
*live execution requires BOTH a token flag AND a server flag*; plus the design
principle that **research never shares a code path with live capital**.

Contract (also stated in docs/OPERATING_CONTRACT.md):

  - Paper / sensor / research actions are ALWAYS allowed — research must never be
    blocked by the capital gate, and the daily sensor (book A, data capture) must
    never stop.
  - A REAL-CAPITAL action (an order that moves real money at a broker) requires
    TWO independent keys, **neither of which an agent operating the repo can
    self-grant**:
      1. ENV  `XIAOCAO_LIVE_TRADING_ENABLED=true`            (operational toggle)
      2. A signed authorization file (default `output/live/live_authorization.json`)
         whose HMAC validates against `XIAOCAO_LIVE_SIGNING_KEY` — a secret the
         *human* holds and that an automation's environment does not carry. The
         authorization is **scoped** (max per-order notional, optional side/code
         allowlist) and **expires**. It is minted only by the interactive
         `scripts/authorize_live.py`, never by an automation.

  Every decision — ALLOW or DENY — is appended to `output/live/safety_audit.jsonl`.

There are intentionally NO real-capital call sites yet: this module exists so that
when a broker bridge is added, the *only* way to place a real order is to pass
through `require_capital_action(...)`, and the contract test proves a missing key
hard-denies it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
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
    auth: dict[str, Any] = {
        "scope": scope,
        "max_notional": float(max_notional),
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
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def live_trading_enabled(env: dict[str, str] | None = None) -> bool:
    src = os.environ if env is None else env
    return str(src.get(ENV_LIVE_ENABLED, "")).strip().lower() == "true"


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
    if not provided or not hmac.compare_digest(provided, expected):
        return None, "invalid signature (tampered or wrong signing key)"
    expires = _parse_iso(auth.get("expires_at"))
    if expires is None:
        return None, "authorization missing/invalid expires_at"
    if (now or _utcnow()) >= expires:
        return None, f"authorization expired at {auth.get('expires_at')}"
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

    # Real-capital path: require BOTH keys.
    if not live_trading_enabled(env):
        decision = Decision(False, kind, f"key 1 missing: {ENV_LIVE_ENABLED} != true", code, side, notional)
        _audit(decision, audit_path)
        return decision

    auth, reason = load_authorization(auth_path=auth_path, env=env, now=now)
    if auth is None:
        decision = Decision(False, kind, f"key 2 missing: {reason}", code, side, notional)
        _audit(decision, audit_path)
        return decision

    # Scope checks.
    sides = auth.get("sides")
    if sides and side is not None and side.upper() not in {str(s).upper() for s in sides}:
        decision = Decision(False, kind, f"side {side!r} out of authorized scope {sides}", code, side, notional)
        _audit(decision, audit_path)
        return decision

    codes = auth.get("codes")
    if codes and code is not None and code not in set(codes):
        decision = Decision(False, kind, f"code {code!r} out of authorized scope", code, side, notional)
        _audit(decision, audit_path)
        return decision

    max_notional = auth.get("max_notional")
    if max_notional is not None and notional is not None and float(notional) > float(max_notional) + 1e-6:
        decision = Decision(
            False, kind,
            f"notional {notional:.2f} exceeds authorized max {float(max_notional):.2f}",
            code, side, notional,
        )
        _audit(decision, audit_path)
        return decision

    decision = Decision(
        True, kind, "two-key authorized",
        code, side, notional,
        details={"scope": auth.get("scope"), "expires_at": auth.get("expires_at")},
    )
    _audit(decision, audit_path)
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


def _audit(decision: Decision, audit_path: Path | None) -> None:
    if audit_path is None:
        return
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
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        # Auditing must never crash the trading loop; a failed audit write is
        # itself a (rare) anomaly the caller's own logging will surface.
        pass
