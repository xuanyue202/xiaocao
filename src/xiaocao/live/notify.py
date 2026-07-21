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
import subprocess
import sys
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
    _ = now  # kept for a stable notify() call signature in tests/callers
    payload: dict[str, Any] = {
        "accountId": account_id or "default",
        "userId": user_id,
        "text": f"{title}\n{body}",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        status, text = _post_json(
            _normalize_wecom_send_url(relay_url),
            payload,
            headers=headers,
            verify=not insecure,
            poster=poster,
        )
    except Exception as exc:  # noqa: BLE001
        return f"error: {type(exc).__name__}"
    return "ok" if (200 <= status < 300 and _wecom_ok(text)) else f"http {status}: {text[:120]}"


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
    src = _merged_env(os.environ) if env is None else env
    results: dict[str, str] = {}
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
            statuses = {
                user_id: wecom_notify(
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
                user_id: status for user_id, status in statuses.items() if status != "ok"
            }
            results["wecom"] = (
                "ok"
                if not failures
                else "failed recipients: "
                + "; ".join(f"{user_id}={status}" for user_id, status in failures.items())
            )
    return results
