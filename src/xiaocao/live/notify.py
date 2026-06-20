"""Multi-channel notifier for live alerts and the daily digest.

Channels:
  - macos  : local osascript "Glass" popup (only on darwin).
  - feishu : group-bot webhook — activates when XIAOCAO_FEISHU_WEBHOOK is set,
             optionally signed with XIAOCAO_FEISHU_SECRET. A silent no-op when
             unset, so the loop runs unchanged until you wire a bot.

Borrowed from QuantDinger's multi-channel signal_notifier, kept lightweight
(requests only, no new deps). Real-money operation needs alerts that reach a
phone, not just the Mac in front of you — see docs/OPERATING_CONTRACT.md.

Notifications never raise: a failed channel returns an error string and the
trading loop continues.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Callable

ENV_FEISHU_WEBHOOK = "XIAOCAO_FEISHU_WEBHOOK"
ENV_FEISHU_SECRET = "XIAOCAO_FEISHU_SECRET"

# poster(url, json_payload) -> (status_code, text). Injectable for tests.
Poster = Callable[[str, dict[str, Any]], "tuple[int, str]"]


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


def _feishu_sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _default_poster(url: str, payload: dict[str, Any]) -> tuple[int, str]:
    import requests  # local import so importing this module never requires requests

    resp = requests.post(url, json=payload, timeout=8)
    return resp.status_code, resp.text


def feishu_notify(
    webhook: str,
    title: str,
    body: str,
    *,
    secret: str | None = None,
    poster: Poster | None = None,
    now: datetime | None = None,
) -> str:
    """Post a text message to a Feishu/Lark group-bot webhook. Returns a status
    string; never raises."""
    payload: dict[str, Any] = {"msg_type": "text", "content": {"text": f"{title}\n{body}"}}
    if secret:
        ts = int((now or datetime.now(timezone.utc)).timestamp())
        payload["timestamp"] = str(ts)
        payload["sign"] = _feishu_sign(secret, ts)
    try:
        status, text = (poster or _default_poster)(webhook, payload)
    except Exception as exc:  # noqa: BLE001
        return f"error: {type(exc).__name__}"
    return "ok" if (status == 200 and _feishu_ok(text)) else f"http {status}: {text[:120]}"


def _feishu_ok(text: str) -> bool:
    """A Feishu webhook reports failures as HTTP 200 with an error JSON body
    (e.g. {"code":19021,"msg":"sign match fail ..."}), so a loose substring match
    like `"ok" in text` would treat "token"/"book"/"lookup" error bodies as
    success and silently swallow a HARD_STOP / kill-switch alert. Parse the result
    code: success is StatusCode==0 / code==0 (or an empty body)."""
    if not text:
        return True
    try:
        body = json.loads(text)
    except (ValueError, TypeError):
        # non-JSON 200 body: trust only the explicit success markers.
        return '"StatusCode":0' in text or '"code":0' in text
    if not isinstance(body, dict):
        return False
    code = body.get("code", body.get("StatusCode", 0))
    try:
        return int(code) == 0
    except (TypeError, ValueError):
        return False


def notify(
    title: str,
    body: str,
    *,
    macos: bool = False,
    env: dict[str, str] | None = None,
    poster: Poster | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    """Fan a message out to the enabled channels. Returns {channel: status}.

    macos is opt-in (callers gate it on a --no-notify flag); feishu auto-enables
    when XIAOCAO_FEISHU_WEBHOOK is present.
    """
    src = os.environ if env is None else env
    results: dict[str, str] = {}
    if macos:
        results["macos"] = macos_notify(title, body)
    webhook = str(src.get(ENV_FEISHU_WEBHOOK, "")).strip()
    if webhook:
        secret = str(src.get(ENV_FEISHU_SECRET, "")).strip() or None
        results["feishu"] = feishu_notify(webhook, title, body, secret=secret, poster=poster, now=now)
    return results
