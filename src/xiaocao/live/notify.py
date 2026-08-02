"""Multi-channel notifier for live alerts and the daily digest.

Channels:
  - macos  : local osascript "Glass" popup (only on darwin).
  - wecom  : OpenClaw wecom-app-relay POST /send — activates when
             XIAOCAO_WECOM_RELAY_URL, XIAOCAO_WECOM_RELAY_TOKEN, and
             XIAOCAO_WECOM_USER_IDS (or legacy XIAOCAO_WECOM_USER_ID) are set.
             A silent no-op when unset, so the loop runs unchanged until you
             wire the relay.

Borrowed from QuantDinger's multi-channel signal_notifier, kept lightweight
(requests only, no new deps). Real-money operation needs alerts that reach a
phone, not just the Mac in front of you — see docs/OPERATING_CONTRACT.md.

Notifications never raise: a failed channel returns an error string and the
trading loop continues.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ENV_NOTIFY_ENV_FILE = "XIAOCAO_NOTIFY_ENV_FILE"
ENV_WECOM_RELAY_URL = "XIAOCAO_WECOM_RELAY_URL"
ENV_WECOM_RELAY_TOKEN = "XIAOCAO_WECOM_RELAY_TOKEN"
ENV_WECOM_USER_IDS = "XIAOCAO_WECOM_USER_IDS"
ENV_WECOM_USER_ID = "XIAOCAO_WECOM_USER_ID"
ENV_WECOM_TO_USER = "XIAOCAO_WECOM_TO_USER"  # backward-friendly alias
ENV_KOL_WECOM_USER_IDS = "XIAOCAO_KOL_WECOM_USER_IDS"
ENV_WECOM_ACCOUNT_ID = "XIAOCAO_WECOM_ACCOUNT_ID"
ENV_WECOM_INSECURE = "XIAOCAO_WECOM_INSECURE"
WECOM_TEXT_MAX_BYTES = 2048
WECOM_CHUNK_DELAY_SECONDS = 0.2
_SMART_SPLIT_MIN_RATIO = 0.6
_WECOM_BOUNDARY_PATTERNS = (
    re.compile(r"\n\n+"),
    re.compile(r"\n"),
    re.compile(r"""[。！？.!?；;:：](?:["'”’」』）】》]*)?(?:\s+|$)"""),
    re.compile(r"[,，、](?:\s+|$)"),
    re.compile(r"\s+"),
)

# poster(url, json_payload, *, headers, verify) -> (status_code, text).
# Injectable for tests; _post_json also accepts the old two-arg shape.
Poster = Callable[..., "tuple[int, str]"]


def macos_notify(title: str, body: str) -> str:
    if sys.platform != "darwin":
        return "skipped (not darwin)"
    try:
        title_safe = title.replace('"', '\\"').replace("'", "\\'")
        body_safe = body.replace('"', '\\"').replace("'", "\\'")
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{body_safe}" with title "{title_safe}" sound name "Glass"',
            ],
            check=False, capture_output=True, timeout=5,
        )
        return "ok"
    except Exception as exc:  # noqa: BLE001 — notifications must never crash the loop
        return f"error: {type(exc).__name__}"


def _default_poster(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    verify: bool = True,
) -> tuple[int, str]:
    import requests  # local import so importing this module never requires requests

    resp = requests.post(url, json=payload, headers=headers, timeout=8, verify=verify)
    return resp.status_code, resp.text


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    verify: bool = True,
    poster: Poster | None = None,
) -> tuple[int, str]:
    if poster is None:
        return _default_poster(url, payload, headers=headers, verify=verify)
    try:
        return poster(url, payload, headers=headers, verify=verify)
    except TypeError:
        # Existing tests/helpers used a two-argument poster before headers were
        # needed. Keep that injectable shape working.
        return poster(url, payload)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_first(src: dict[str, str] | os._Environ[str], *names: str) -> str:
    for name in names:
        value = str(src.get(name, "")).strip()
        if value:
            return value
    return ""


def _wecom_user_ids(
    src: dict[str, str] | os._Environ[str],
    *,
    audience: str | None = None,
) -> tuple[str, ...]:
    preferred = (ENV_KOL_WECOM_USER_IDS,) if audience == "kol" else ()
    raw = _env_first(
        src,
        *preferred,
        ENV_WECOM_USER_IDS,
        ENV_WECOM_USER_ID,
        ENV_WECOM_TO_USER,
    )
    values = raw.replace(";", ",").replace("\n", ",").split(",")
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        out[key] = value
    return out


def _merged_env(src: dict[str, str] | os._Environ[str]) -> dict[str, str]:
    env = dict(src)
    explicit = _env_first(env, ENV_NOTIFY_ENV_FILE)
    candidates = [Path(explicit).expanduser()] if explicit else [
        Path.cwd() / "output" / "live" / "notify.env",
        Path.home() / ".xiaocao" / "notify.env",
    ]
    for path in candidates:
        file_env = _parse_env_file(path)
        if file_env:
            merged = file_env
            merged.update(env)  # process env wins over file env
            return merged
    return env


def _normalize_wecom_send_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    if not url:
        return ""
    path = url.split("?", 1)[0].rstrip("/")
    if path.endswith("/send"):
        return url
    return f"{url}/send"


def _utf8_prefix_index(text: str, max_bytes: int) -> int:
    total = 0
    for index, character in enumerate(text):
        size = len(character.encode("utf-8"))
        if total + size > max_bytes:
            return index
        total += size
    return len(text)


def _smart_utf8_split_index(text: str, max_bytes: int) -> int:
    hard_index = max(1, _utf8_prefix_index(text, max_bytes))
    prefix = text[:hard_index]
    minimum = max(1, int(hard_index * _SMART_SPLIT_MIN_RATIO))
    for pattern in _WECOM_BOUNDARY_PATTERNS:
        boundaries = [
            match.end()
            for match in pattern.finditer(prefix)
            if match.end() >= minimum
        ]
        if boundaries:
            return boundaries[-1]
    return hard_index


def split_wecom_text_by_bytes(
    text: str,
    max_bytes: int = WECOM_TEXT_MAX_BYTES,
) -> list[str]:
    """Split without losing text or breaking UTF-8 code points."""
    if not text or max_bytes <= 0:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while len(remaining.encode("utf-8")) > max_bytes:
        split_index = _smart_utf8_split_index(remaining, max_bytes)
        chunks.append(remaining[:split_index])
        remaining = remaining[split_index:]
    if remaining:
        chunks.append(remaining)
    return chunks


def wecom_notify(
    relay_url: str,
    title: str,
    body: str,
    *,
    token: str,
    user_id: str,
    account_id: str = "default",
    insecure: bool = False,
    poster: Poster | None = None,
    now: datetime | None = None,
) -> str:
    """Post a text message through OpenClaw's wecom-app-relay /send endpoint.
    Returns a status string; never raises."""
    return str(
        wecom_notify_detailed(
            relay_url,
            title,
            body,
            token=token,
            user_id=user_id,
            account_id=account_id,
            insecure=insecure,
            poster=poster,
            now=now,
        )["detail"]
    )


def _exception_type_chain(exc: BaseException) -> set[str]:
    names: set[str] = set()
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        names.add(type(current).__name__)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
        pending.extend(value for value in current.args if isinstance(value, BaseException))
    return names


def _wecom_exception_result(
    exc: Exception,
    *,
    chunk_prefix: str,
    partial_delivery: bool,
) -> dict[str, Any]:
    error_type = type(exc).__name__
    detail = f"{chunk_prefix}error: {error_type}"
    safe_connect_errors = {
        "ConnectTimeout",
        "ConnectionRefusedError",
        "NameResolutionError",
        "NewConnectionError",
        "gaierror",
    }
    if not partial_delivery and _exception_type_chain(exc) & safe_connect_errors:
        return {
            "status": "failed",
            "detail": detail,
            "retry_safety": "safe",
            "failure_phase": "connect",
        }
    return {
        "status": "uncertain",
        "detail": detail,
        "retry_safety": "uncertain",
        "failure_phase": "response",
    }


def wecom_notify_detailed(
    relay_url: str,
    title: str,
    body: str,
    *,
    token: str,
    user_id: str,
    account_id: str = "default",
    insecure: bool = False,
    poster: Poster | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Post one recipient and preserve whether a retry is provably safe."""
    _ = now  # kept for a stable notify() call signature in tests/callers
    chunks = split_wecom_text_by_bytes(f"{title}\n{body}")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    for index, chunk in enumerate(chunks, start=1):
        payload: dict[str, Any] = {
            "accountId": account_id or "default",
            "userId": user_id,
            "text": chunk,
        }
        try:
            status, response_text = _post_json(
                _normalize_wecom_send_url(relay_url),
                payload,
                headers=headers,
                verify=not insecure,
                poster=poster,
            )
        except Exception as exc:  # noqa: BLE001
            chunk_prefix = (
                f"chunk {index}/{len(chunks)} "
                if len(chunks) > 1
                else ""
            )
            return _wecom_exception_result(
                exc,
                chunk_prefix=chunk_prefix,
                partial_delivery=index > 1,
            )
        if not (
            200 <= status < 300
            and _wecom_ok(response_text)
        ):
            chunk_prefix = (
                f"chunk {index}/{len(chunks)} "
                if len(chunks) > 1
                else ""
            )
            return {
                "status": "failed",
                "detail": f"{chunk_prefix}http {status}: {response_text[:120]}",
                "retry_safety": "requires_reconciliation",
                "failure_phase": "relay_response",
            }
        if index < len(chunks):
            time.sleep(WECOM_CHUNK_DELAY_SECONDS)
    return {
        "status": "ok",
        "detail": "ok",
        "retry_safety": "not_needed",
        "failure_phase": None,
    }


def _wecom_ok(text: str) -> bool:
    """Relay /send can fail as HTTP 200 with a JSON error body, so parse the
    structured result instead of trusting a substring such as "ok" in errmsg."""
    if not text:
        return True
    try:
        body = json.loads(text)
    except (ValueError, TypeError):
        return text.strip().lower() in {"ok", "success"}
    if not isinstance(body, dict):
        return False
    if "ok" in body:
        return bool(body.get("ok"))
    if "success" in body:
        return bool(body.get("success"))
    for key in ("errcode", "code", "StatusCode"):
        if key in body:
            try:
                return int(body.get(key)) == 0
            except (TypeError, ValueError):
                return False
    return False


def notify(
    title: str,
    body: str,
    *,
    macos: bool = False,
    env: dict[str, str] | None = None,
    poster: Poster | None = None,
    now: datetime | None = None,
    audience: str | None = None,
) -> dict[str, str]:
    """Fan a message out to the enabled channels. Returns {channel: status}.

    macos is opt-in (callers gate it on a --no-notify flag); wecom auto-enables
    when the XIAOCAO_WECOM_* relay env vars are present.
    """
    detailed = notify_detailed(
        title,
        body,
        macos=macos,
        env=env,
        poster=poster,
        now=now,
        audience=audience,
    )
    return {
        key: str(value)
        for key, value in detailed.items()
        if key != "wecom_recipients"
    }


def notify_detailed(
    title: str,
    body: str,
    *,
    macos: bool = False,
    env: dict[str, str] | None = None,
    poster: Poster | None = None,
    now: datetime | None = None,
    audience: str | None = None,
) -> dict[str, Any]:
    """Fan out while retaining per-recipient relay outcomes for reconciliation."""
    src = _merged_env(os.environ) if env is None else env
    results: dict[str, Any] = {}
    if macos:
        results["macos"] = macos_notify(title, body)
    relay_url = _env_first(src, ENV_WECOM_RELAY_URL)
    token = _env_first(src, ENV_WECOM_RELAY_TOKEN)
    user_ids = _wecom_user_ids(src, audience=audience)
    if relay_url or token or user_ids:
        missing = []
        if not relay_url:
            missing.append(ENV_WECOM_RELAY_URL)
        if not token:
            missing.append(ENV_WECOM_RELAY_TOKEN)
        if not user_ids:
            missing.append(ENV_WECOM_USER_IDS)
        if missing:
            results["wecom"] = "not configured: missing " + ", ".join(missing)
        else:
            account_id = _env_first(src, ENV_WECOM_ACCOUNT_ID) or "default"
            recipient_results = {
                user_id: wecom_notify_detailed(
                    relay_url,
                    title,
                    body,
                    token=token,
                    user_id=user_id,
                    account_id=account_id,
                    insecure=_truthy(_env_first(src, ENV_WECOM_INSECURE)),
                    poster=poster,
                    now=now,
                )
                for user_id in user_ids
            }
            failures = {
                user_id: value["detail"]
                for user_id, value in recipient_results.items()
                if value["status"] != "ok"
            }
            results["wecom"] = (
                "ok"
                if not failures
                else "failed recipients: "
                + "; ".join(f"{user_id}={status}" for user_id, status in failures.items())
            )
            results["wecom_recipients"] = recipient_results
    return results


def configured_wecom_recipients(
    *,
    env: dict[str, str] | None = None,
    audience: str | None = None,
) -> tuple[str, ...]:
    """Return configured recipient identities without exposing relay credentials."""
    src = _merged_env(os.environ) if env is None else env
    return _wecom_user_ids(src, audience=audience)


def send_wecom_recipient_detailed(
    title: str,
    body: str,
    recipient: str,
    *,
    env: dict[str, str] | None = None,
    audience: str | None = None,
    poster: Poster | None = None,
) -> dict[str, Any]:
    """Send exactly one already-configured recipient for a transport handoff."""
    src = _merged_env(os.environ) if env is None else env
    allowed = _wecom_user_ids(src, audience=audience)
    if recipient not in allowed:
        return {
            "status": "failed",
            "detail": "recipient not configured",
            "retry_safety": "not_allowed",
            "failure_phase": "preflight",
        }
    relay_url = _env_first(src, ENV_WECOM_RELAY_URL)
    token = _env_first(src, ENV_WECOM_RELAY_TOKEN)
    if not relay_url or not token:
        return {
            "status": "failed",
            "detail": "relay not configured",
            "retry_safety": "not_allowed",
            "failure_phase": "preflight",
        }
    return wecom_notify_detailed(
        relay_url,
        title,
        body,
        token=token,
        user_id=recipient,
        account_id=_env_first(src, ENV_WECOM_ACCOUNT_ID) or "default",
        insecure=_truthy(_env_first(src, ENV_WECOM_INSECURE)),
        poster=poster,
    )
