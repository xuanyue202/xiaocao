"""Local WeChat discovery for resumable Xiaocao web-live capture.

This adapter keeps the hourly coordinator on metadata only.  Browser playback
is delegated through a small request/response exchange and all video bytes are
owned by :class:`XiaocaoLiveService` and the external sniffer/downloader.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from .capture import (
    InvalidSourcePage,
    canonical_xiaoetong_source,
    resolve_xiaoetong_h5_page,
)
from .enrichment_types import EnrichmentDiagnosticError, EnrichmentError
from .xiaocao_live import (
    DEFAULT_DECISION_OUTPUT,
    DEFAULT_NETDISK_OUTPUT,
    XiaocaoLiveService,
)


BEIJING = ZoneInfo("Asia/Shanghai")
DEFAULT_CONTACT = "福利官小花四-刘丹（执业编号:A0380125080026）"
DEFAULT_WECHAT_CLI = Path("/opt/homebrew/bin/wechat-cli")
_MESSAGE = re.compile(r"^\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]")
_URL = re.compile(r"https://[^\s）)】》>，,；;]+")
_TERMINAL = {"historical_baseline", "completed"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_HANDOFF_BYTES = 1024 * 1024


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _normalized_live_url(raw: str) -> str | None:
    parsed = urlsplit(raw.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return None
    pieces = [piece for piece in parsed.path.split("/") if piece]
    is_short = (
        (host.endswith(".xet.tech") and len(pieces) == 2 and pieces[0] == "s")
        or (
            host.endswith(".xetslk.com")
            and len(pieces) == 2
            and pieces[0] in {"s", "sl"}
        )
    )
    if is_short:
        return urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))
    try:
        source = canonical_xiaoetong_source(raw)
    except InvalidSourcePage:
        return None
    return (
        f"https://{source['source_host']}/v4/course/alive/"
        f"{source['source_resource_id']}"
    )


def parse_xiaocao_live_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract credential-free live-link identities from ``wechat-cli`` JSON."""
    if not isinstance(payload, dict):
        raise EnrichmentError("WeChat history response is invalid")
    if payload.get("failures") not in (None, []):
        raise EnrichmentDiagnosticError(
            "WeChat history is incomplete",
            category="source_error",
            code="wechat_history_incomplete",
            stage="wechat_scan",
        )
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise EnrichmentError("WeChat history messages are invalid")
    contact = str(payload.get("chat") or "").strip()
    username = str(payload.get("username") or "").strip()
    if not contact or not username:
        raise EnrichmentError("WeChat history contact binding is missing")

    items: dict[str, dict[str, Any]] = {}
    for raw_message in messages:
        if not isinstance(raw_message, str):
            continue
        timestamp = _MESSAGE.match(raw_message)
        if timestamp is None:
            continue
        if not ({"草神", "小草"}.intersection({
            token for token in ("草神", "小草") if token in raw_message
        })):
            continue
        if "直播" not in raw_message and "学习地址" not in raw_message:
            continue
        published = datetime.strptime(
            timestamp.group("time"), "%Y-%m-%d %H:%M"
        ).replace(tzinfo=BEIJING)
        for match in _URL.findall(raw_message):
            source_url = _normalized_live_url(match)
            if source_url is None:
                continue
            identity = "kol-wechat-" + _sha256_text(
                f"{username}\n{published.isoformat()}\n{source_url}"
            )[:24]
            items[identity] = {
                "identity": identity,
                "contact": contact,
                "contact_username": username,
                "published_at": published.isoformat(timespec="seconds"),
                "source_url": source_url,
                "message_sha256": _sha256_text(raw_message),
            }
    return sorted(
        items.values(),
        key=lambda item: (item["published_at"], item["identity"]),
    )


class CaptureDriver(Protocol):
    def arm(self, identity: str, page_url: str) -> dict[str, Any]: ...

    def advance(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None,
    ) -> dict[str, Any]: ...


class WechatCliHistoryReader:
    """Credential-safe ``wechat-cli history`` boundary."""

    def __init__(
        self,
        contact: str = DEFAULT_CONTACT,
        *,
        executable: Path | str = DEFAULT_WECHAT_CLI,
        limit: int = 80,
        runner: Callable[..., Any] = subprocess.run,
    ):
        self.contact = str(contact)
        self.executable = Path(executable).expanduser().resolve()
        self.limit = int(limit)
        self._runner = runner

    def __call__(self) -> dict[str, Any]:
        if not self.executable.is_file():
            raise EnrichmentDiagnosticError(
                "wechat-cli is unavailable",
                category="configuration",
                code="wechat_cli_missing",
                stage="wechat_scan",
            )
        try:
            result = self._runner(
                [
                    str(self.executable),
                    "history",
                    self.contact,
                    "--limit",
                    str(self.limit),
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            value = json.loads(result.stdout)
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentDiagnosticError(
                "wechat-cli history timed out",
                category="timeout",
                code="wechat_history_timeout",
                stage="wechat_scan",
            ) from exc
        except (subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
            raise EnrichmentDiagnosticError(
                "wechat-cli history failed",
                category="source_error",
                code="wechat_history_failed",
                stage="wechat_scan",
            ) from exc
        if not isinstance(value, dict):
            raise EnrichmentError("WeChat history response is invalid")
        if str(value.get("chat") or "") != self.contact:
            raise EnrichmentError("WeChat history resolved another contact")
        return value


class XiaocaoLiveCaptureDriver:
    """Own per-subscription capture ledgers while sharing cloud enrichment."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        decision_output: Path | str = DEFAULT_DECISION_OUTPUT,
        netdisk_output: Path | str = DEFAULT_NETDISK_OUTPUT,
        service_factory: Callable[..., XiaocaoLiveService] = XiaocaoLiveService,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.decision_output = Path(decision_output).expanduser().resolve()
        self.netdisk_output = Path(netdisk_output).expanduser().resolve()
        self._service_factory = service_factory

    def _service(self, identity: str) -> XiaocaoLiveService:
        item_dir = self.output_dir / "items" / identity
        return self._service_factory(
            item_dir,
            capture_ledger=item_dir / "capture_jobs.jsonl",
            netdisk_output=self.netdisk_output,
            decision_output=self.decision_output,
        )

    def arm(self, identity: str, page_url: str) -> dict[str, Any]:
        return self._service(identity).start(page_url=page_url)

    def advance(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None,
    ) -> dict[str, Any]:
        service = self._service(identity)
        published = next(
            (
                event
                for event in reversed(service.events())
                if event.get("event") == "cloud_handoff_published"
                and event.get("capture_job_id") == capture_job_id
            ),
            None,
        )
        if published is not None:
            return {**published, "idempotent_replay": True}
        capture = service.capture_store.latest(capture_job_id)
        if capture is None or capture.get("status") != "downloaded":
            service.start()
        return service.advance(
            capture_job_id,
            opencli_session=opencli_session,
            opencli_profile=opencli_profile,
        )


class XiaocaoWechatLiveSubscription:
    """Exactly-once WeChat discovery and browser/capture state machine."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        history_reader: Callable[[], dict[str, Any]],
        browser_exchange: Callable[[dict[str, Any]], dict[str, Any]],
        capture_driver: CaptureDriver,
        contact: str = DEFAULT_CONTACT,
        password: str = "666",
        clock: Callable[[], datetime] | None = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.manifest_path = self.output_dir / "manifest.json"
        self.events_path = self.output_dir / "events.jsonl"
        self.history_reader = history_reader
        self.browser_exchange = browser_exchange
        self.capture_driver = capture_driver
        self.contact = str(contact)
        self.password = str(password)
        self.clock = clock or (lambda: datetime.now(BEIJING))

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            raise EnrichmentError("Xiaocao WeChat clock needs a timezone")
        return value.astimezone(BEIJING).isoformat(timespec="seconds")

    def _load(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"schema_version": 1, "items": {}}
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("Xiaocao WeChat manifest is invalid") from exc
        if value.get("schema_version") != 1 or not isinstance(
            value.get("items"), dict
        ):
            raise EnrichmentError("Xiaocao WeChat manifest is invalid")
        return value

    def _save(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = self._now()
        _atomic_json(self.manifest_path, manifest)

    def _transition(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
        status: str,
        **fields: Any,
    ) -> dict[str, Any]:
        updated = {
            **item,
            **fields,
            "status": status,
            "updated_at": self._now(),
        }
        manifest["items"][updated["identity"]] = updated
        self._save(manifest)
        _append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "event": "subscription_transition",
                "identity": updated["identity"],
                "status": status,
                "capture_job_id": str(updated.get("capture_job_id") or ""),
                "updated_at": updated["updated_at"],
            },
        )
        return updated

    def _poll(self, manifest: dict[str, Any]) -> None:
        payload = self.history_reader()
        if str(payload.get("chat") or "") != self.contact:
            raise EnrichmentError("WeChat history resolved another contact")
        observed = parse_xiaocao_live_messages(payload)
        new_items = [
            item for item in observed if item["identity"] not in manifest["items"]
        ]
        if "initialized_at" not in manifest:
            for item in new_items[:-1]:
                manifest["items"][item["identity"]] = {
                    **item,
                    "status": "historical_baseline",
                    "updated_at": self._now(),
                }
            new_items = new_items[-1:]
            manifest["initialized_at"] = self._now()
        for item in new_items:
            manifest["items"][item["identity"]] = {
                **item,
                "status": "discovered",
                "updated_at": self._now(),
            }
        self._save(manifest)

    @staticmethod
    def _canonical_page(page_url: str) -> tuple[str, str]:
        try:
            canonical = resolve_xiaoetong_h5_page(page_url)
            source = canonical_xiaoetong_source(canonical)
        except InvalidSourcePage as exc:
            raise EnrichmentError("browser did not resolve a Xiaoetong live page") from exc
        return canonical, source["source_identity"]

    @staticmethod
    def _validate_browser_response(
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        if (
            not isinstance(response, dict)
            or response.get("action") != request["action"]
            or response.get("subscription_id") != request["subscription_id"]
        ):
            raise EnrichmentError("browser response is not bound to the request")

    def _waiting(self, item: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        status = str(state.get("status") or item.get("status") or "waiting")
        stage = (
            "cloud_handoff"
            if state.get("event") == "xiaocao_live_upload_pending"
            else "compressed_capture"
        )
        return {
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [{
                "identity": item["identity"],
                "published_at": item["published_at"],
                "status": status,
                "stage": stage,
                "capture_job_id": str(item.get("capture_job_id") or ""),
            }],
        }

    @staticmethod
    def _load_handoff(item: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(item.get("handoff_path") or "")).expanduser().resolve()
        if not path.is_file() or path.stat().st_size > _MAX_HANDOFF_BYTES:
            raise EnrichmentError("Xiaocao handoff is missing or too large")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("Xiaocao handoff is invalid") from exc
        if not isinstance(value, dict):
            raise EnrichmentError("Xiaocao handoff is invalid")
        expected = str(value.get("handoff_sha256") or "")
        unsigned = dict(value)
        unsigned.pop("handoff_sha256", None)
        if (
            value.get("schema_version") != 2
            or value.get("capture_job_id") != item.get("capture_job_id")
            or value.get("large_payload_local_bytes") != 0
            or not _SHA256.fullmatch(str(value.get("handoff_id") or ""))
            or not _SHA256.fullmatch(str(value.get("media_sha256") or ""))
            or expected != _sha256_text(_canonical(unsigned))
            or "media_path" in value
            or "video_path" in value
        ):
            raise EnrichmentError("Xiaocao handoff binding is invalid")
        return value

    def _dispatch_handoff(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
    ) -> dict[str, Any]:
        capsule = self._load_handoff(item)
        request = {
            "event": "daily_remote_handoff_input_required",
            "adapter": "xiaocao_wechat_live",
            "action": "dispatch_xiaocao_handoff",
            "subscription_id": item["identity"],
            "capture_job_id": item["capture_job_id"],
            "handoff_id": capsule["handoff_id"],
            "handoff_path": item["handoff_path"],
            "instructions": (
                "Read and validate the lightweight capsule, then use the newest "
                "current-hour remote writer task on the registered "
                "MacBook-Pro-6.local host; never use a stale long-lived task or "
                "one waiting on approval. "
                "Reconcile the remote thread and handoff_id before any retry; "
                "return only after target-task readback proves acceptance."
            ),
            "required_response": {
                "action": "dispatch_xiaocao_handoff",
                "subscription_id": item["identity"],
                "handoff_id": capsule["handoff_id"],
                "accepted": True,
                "readback_status": "accepted|already_present",
                "remote_thread_id": "current-hour remote writer task id",
                "remote_host_id": "registered remote host id",
            },
        }
        response = self.browser_exchange(request)
        self._validate_browser_response(request, response)
        remote_thread_id = str(response.get("remote_thread_id") or "").strip()
        remote_host_id = str(response.get("remote_host_id") or "").strip()
        if (
            response.get("handoff_id") != capsule["handoff_id"]
            or response.get("accepted") is not True
            or response.get("readback_status")
            not in {"accepted", "already_present"}
            or not remote_thread_id
            or not remote_host_id
        ):
            raise EnrichmentError("remote Xiaocao handoff lacks acceptance readback")
        completed = self._transition(
            manifest,
            item,
            "completed",
            handoff_id=capsule["handoff_id"],
            remote_thread_id=remote_thread_id,
            remote_host_id=remote_host_id,
            remote_readback_status=str(response["readback_status"]),
        )
        return {
            "status": "no_update",
            "handoff_dispatched": True,
            "identity": completed["identity"],
            "capture_job_id": completed["capture_job_id"],
        }

    def run_once(
        self,
        *,
        opencli_session: str,
        opencli_profile: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load()
        self._poll(manifest)
        pending = sorted(
            (
                item
                for item in manifest["items"].values()
                if item.get("status") not in _TERMINAL
            ),
            key=lambda item: (item["published_at"], item["identity"]),
        )
        if not pending:
            return {"status": "no_update"}
        item = dict(pending[0])

        if item["status"] == "discovered":
            request = {
                "event": "daily_browser_input_required",
                "adapter": "xiaocao_wechat_live",
                "action": "resolve_xiaoetong_page",
                "subscription_id": item["identity"],
                "source_url": item["source_url"],
                "required_response": {
                    "action": "resolve_xiaoetong_page",
                    "subscription_id": item["identity"],
                    "page_url": "current Xiaoetong MP wrapper or H5 page URL",
                    "page_state": "playable|password_required|unknown",
                },
            }
            response = self.browser_exchange(request)
            self._validate_browser_response(request, response)
            page_url, source_identity = self._canonical_page(
                str(response.get("page_url") or "")
            )
            item = self._transition(
                manifest,
                item,
                "page_resolved",
                page_url=page_url,
                source_identity=source_identity,
                observed_page_state=str(response.get("page_state") or "unknown"),
            )

        if item["status"] == "page_resolved":
            armed = self.capture_driver.arm(item["identity"], item["page_url"])
            capture_job_id = str(armed.get("capture_job_id") or "")
            if not capture_job_id:
                raise EnrichmentError("Xiaocao capture did not return a job identity")
            item = self._transition(
                manifest,
                item,
                "capture_armed",
                capture_job_id=capture_job_id,
            )

        if item["status"] == "capture_armed":
            request = {
                "event": "daily_browser_input_required",
                "adapter": "xiaocao_wechat_live",
                "action": "activate_xiaoetong_playback",
                "subscription_id": item["identity"],
                "page_url": item["page_url"],
                "password_policy": {
                    "only_if_password_gate_visible": True,
                    "password": self.password,
                },
                "instructions": (
                    "Refresh the bound page. If it is directly playable, play it "
                    "without entering a password. If a password gate is visible, "
                    "enter the supplied password and submit it, then start playback. "
                    "Return after media requests begin."
                ),
                "required_response": {
                    "action": "activate_xiaoetong_playback",
                    "subscription_id": item["identity"],
                    "page_url": item["page_url"],
                    "activated": True,
                    "password_used": "boolean",
                },
            }
            response = self.browser_exchange(request)
            self._validate_browser_response(request, response)
            response_page, response_identity = self._canonical_page(
                str(response.get("page_url") or "")
            )
            if (
                response_page != item["page_url"]
                or response_identity != item["source_identity"]
                or response.get("activated") is not True
            ):
                raise EnrichmentError("browser did not activate the bound live page")
            item = self._transition(
                manifest,
                item,
                "playback_activated",
                password_used=response.get("password_used") is True,
            )

        if item["status"] == "handoff_ready":
            return self._dispatch_handoff(manifest, item)

        state = self.capture_driver.advance(
            item["identity"],
            item["capture_job_id"],
            opencli_session=opencli_session,
            opencli_profile=opencli_profile,
        )
        if (
            state.get("event") == "cloud_handoff_published"
            and state.get("status") == "handoff_published"
        ):
            item = self._transition(
                manifest,
                item,
                "handoff_ready",
                handoff_path=str(state.get("handoff_path") or ""),
            )
            return self._dispatch_handoff(manifest, item)
        return self._waiting(item, state)
