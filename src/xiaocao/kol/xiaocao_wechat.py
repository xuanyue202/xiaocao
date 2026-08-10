"""Local WeChat discovery for resumable Xiaocao web-live capture.

This adapter keeps the hourly coordinator on metadata only.  Browser playback
is delegated through a small request/response exchange and all video bytes are
owned by :class:`XiaocaoLiveService` and the external sniffer/downloader.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, urlsplit, urlunsplit
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
_TERMINAL = {"historical_baseline", "superseded", "completed"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_HANDOFF_BYTES = 1024 * 1024
_CAPTURE_PROGRESS_POLL_SECONDS = 30
_LOCAL_CAPTURE_FIRST_HOUR = 7
_PLAYBACK_PAGE_STATES = {
    "account_login_required",
    "waiting_to_start",
    "live",
    "replay_generating",
    "playable",
    "password_required",
    "unknown",
}


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _next_local_playback_recheck(observed_at: datetime) -> datetime:
    if observed_at.tzinfo is None:
        raise EnrichmentError("Xiaocao WeChat clock needs a timezone")
    deadline = (observed_at.astimezone(BEIJING) + timedelta(hours=1)).replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    if deadline.hour < _LOCAL_CAPTURE_FIRST_HOUR:
        deadline = deadline.replace(hour=_LOCAL_CAPTURE_FIRST_HOUR)
    return deadline


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
        published = datetime.strptime(
            timestamp.group("time"), "%Y-%m-%d %H:%M"
        ).replace(tzinfo=BEIJING)
        # Discovery is already bound to the exact registered contact.  Message
        # copy is not a stable contract, so iterate every URL and rely on the
        # Xiaoetong allowlist here plus exact ``/course/alive/`` browser binding
        # before a capture job can be armed.
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

    def published_handoff(
        self,
        identity: str,
        capture_job_id: str,
    ) -> dict[str, Any] | None: ...


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
        published = self.published_handoff(identity, capture_job_id)
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

    def published_handoff(
        self,
        identity: str,
        capture_job_id: str,
    ) -> dict[str, Any] | None:
        service = self._service(identity)
        return next(
            (
                event
                for event in reversed(service.events())
                if event.get("event") == "cloud_handoff_published"
                and event.get("capture_job_id") == capture_job_id
            ),
            None,
        )


class XiaocaoWechatLiveSubscription:
    """Exactly-once WeChat discovery and browser/capture state machine."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        history_reader: Callable[[], dict[str, Any]],
        browser_exchange: Callable[[dict[str, Any]], dict[str, Any]],
        handoff_exchange: Callable[..., dict[str, Any]] | None = None,
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
        self.handoff_exchange = handoff_exchange or browser_exchange
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

    def _supersede_older_unarmed_previews(
        self,
        manifest: dict[str, Any],
    ) -> None:
        discovered = sorted(
            (
                dict(item)
                for item in manifest["items"].values()
                if item.get("status") == "discovered"
            ),
            key=lambda item: (item["published_at"], item["identity"]),
        )
        if len(discovered) < 2:
            return
        newest = discovered[-1]
        for item in discovered[:-1]:
            self._transition(
                manifest,
                item,
                "superseded",
                superseded_by=newest["identity"],
            )

    @staticmethod
    def _next_pending(manifest: dict[str, Any]) -> dict[str, Any] | None:
        pending = [
            dict(item)
            for item in manifest["items"].values()
            if item.get("status") not in _TERMINAL
        ]
        if not pending:
            return None
        browser_critical = [
            item
            for item in pending
            if item.get("status")
            in {
                "discovered",
                "page_resolved",
                "capture_armed",
                "awaiting_playback",
            }
        ]
        if browser_critical:
            return max(
                browser_critical,
                key=lambda item: (item["published_at"], item["identity"]),
            )
        inflight_captures = [
            item
            for item in pending
            if item.get("status") == "playback_activated"
        ]
        if inflight_captures:
            return max(
                inflight_captures,
                key=lambda item: (item["published_at"], item["identity"]),
            )
        handoffs = [
            item for item in pending if item.get("status") == "handoff_ready"
        ]
        if handoffs:
            return min(
                handoffs,
                key=lambda item: (item["published_at"], item["identity"]),
            )
        return max(
            pending,
            key=lambda item: (item["published_at"], item["identity"]),
        )

    @staticmethod
    def _canonical_page(page_url: str) -> tuple[str, str]:
        try:
            canonical = resolve_xiaoetong_h5_page(page_url)
            source = canonical_xiaoetong_source(canonical)
        except InvalidSourcePage as exc:
            raise EnrichmentError("browser did not resolve a Xiaoetong live page") from exc
        return canonical, source["source_identity"]

    @classmethod
    def _canonical_browser_page(
        cls,
        page_url: str,
        *,
        page_state: str,
    ) -> tuple[str, str]:
        if page_state != "account_login_required":
            return cls._canonical_page(page_url)
        parsed = urlsplit(page_url.strip())
        redirect_urls = parse_qs(parsed.query).get("redirect_url", [])
        if (
            parsed.scheme != "https"
            or parsed.path
            != "/p/t/free/v1/basic-platform/h5_basic/login/auth"
            or len(redirect_urls) != 1
        ):
            raise EnrichmentError("browser account login redirect is invalid")
        redirect = urlsplit(redirect_urls[0])
        if (parsed.hostname or "").lower() != (redirect.hostname or "").lower():
            raise EnrichmentError("browser account login redirect changed host")
        return cls._canonical_page(redirect_urls[0])

    @classmethod
    def _is_bound_account_login_redirect(
        cls,
        page_url: str,
        *,
        expected_page_url: str,
        expected_source_identity: str,
    ) -> bool:
        parsed = urlsplit(page_url.strip())
        expected = urlsplit(expected_page_url)
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower()
            != (expected.hostname or "").lower()
            or parsed.path
            != "/p/t/free/v1/basic-platform/h5_basic/login/auth"
        ):
            return False
        redirect_urls = parse_qs(parsed.query).get("redirect_url", [])
        if len(redirect_urls) != 1:
            return False
        try:
            redirect_page, redirect_identity = cls._canonical_page(
                redirect_urls[0]
            )
        except EnrichmentError:
            return False
        return (
            redirect_page == expected_page_url
            and redirect_identity == expected_source_identity
        )

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
        waiting_item = {
            "identity": item["identity"],
            "published_at": item["published_at"],
            "status": status,
            "stage": stage,
            "capture_job_id": str(item.get("capture_job_id") or ""),
        }
        deadline_base = self.clock()
        if status == "awaiting_playback":
            # Lifecycle rechecks follow the configured local hourly window.
            deadline = _next_local_playback_recheck(deadline_base)
        else:
            if deadline_base.tzinfo is None:
                raise EnrichmentError("Xiaocao WeChat clock needs a timezone")
            deadline = deadline_base.astimezone(BEIJING) + timedelta(
                seconds=_CAPTURE_PROGRESS_POLL_SECONDS
            )
        waiting_item["next_poll_not_before"] = deadline.isoformat(
            timespec="seconds"
        )
        return {
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [waiting_item],
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
        del manifest
        lock_path = self.output_dir / ".handoff-dispatch.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return self._waiting(
                    item,
                    {
                        "event": "xiaocao_live_upload_pending",
                        "status": "handoff_dispatch_in_progress",
                    },
                )
            current_manifest = self._load()
            current = current_manifest["items"].get(item["identity"])
            if not isinstance(current, dict):
                raise EnrichmentError("Xiaocao handoff item disappeared")
            if current.get("status") == "completed":
                return {
                    "status": "no_update",
                    "handoff_dispatched": False,
                    "already_completed": True,
                    "identity": current["identity"],
                    "capture_job_id": current["capture_job_id"],
                }
            if current.get("status") != "handoff_ready":
                raise EnrichmentError("Xiaocao handoff is not ready")
            return self._dispatch_handoff_locked(current_manifest, current)

    def _dispatch_handoff_locked(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
    ) -> dict[str, Any]:
        capsule = self._load_handoff(item)
        media_basename = str(capsule.get("media_basename") or "").strip()
        if (
            not media_basename
            or Path(media_basename).name != media_basename
            or not Path(media_basename).stem.strip()
        ):
            raise EnrichmentError(
                "Xiaocao handoff lacks a safe media basename title"
            )
        response = self.handoff_exchange(
            capsule,
            object_kind="video",
            title=Path(media_basename).stem.strip(),
        )
        if (
            not isinstance(response, dict)
            or response.get("handoff_id") != capsule["handoff_id"]
            or response.get("status") != "Handoff完成"
            or response.get("mailbox_outcome") not in {
                "created",
                "already_present",
            }
            or not _SHA256.fullmatch(
                str(response.get("content_sha256") or "")
            )
        ):
            raise EnrichmentError("Xiaocao mailbox handoff lacks creation readback")
        completed = self._transition(
            manifest,
            item,
            "completed",
            handoff_id=capsule["handoff_id"],
            mailbox_id="kol.handoff",
            mailbox_message_id=capsule["handoff_id"],
            mailbox_content_sha256=str(response["content_sha256"]),
            mailbox_readback_status=str(response["mailbox_outcome"]),
        )
        return {
            "status": "no_update",
            "handoff_dispatched": True,
            "identity": completed["identity"],
            "capture_job_id": completed["capture_job_id"],
        }

    def dispatch_published_handoff(self) -> dict[str, Any]:
        """Dispatch one already-published handoff without rescanning or advancing."""
        manifest = self._load()
        ready = sorted(
            (
                dict(item)
                for item in manifest["items"].values()
                if item.get("status") == "handoff_ready"
            ),
            key=lambda item: (item["published_at"], item["identity"]),
        )
        if ready:
            return self._dispatch_handoff(manifest, ready[0])

        candidates = sorted(
            (
                dict(item)
                for item in manifest["items"].values()
                if item.get("status") not in _TERMINAL
                and str(item.get("capture_job_id") or "")
            ),
            key=lambda item: (item["published_at"], item["identity"]),
        )
        for item in candidates:
            state = self.capture_driver.published_handoff(
                item["identity"],
                item["capture_job_id"],
            )
            if state is None:
                continue
            if (
                state.get("event") != "cloud_handoff_published"
                or state.get("status") != "handoff_published"
                or state.get("capture_job_id") != item["capture_job_id"]
            ):
                raise EnrichmentError("published Xiaocao handoff is not bound")
            item = self._transition(
                manifest,
                item,
                "handoff_ready",
                handoff_path=str(state.get("handoff_path") or ""),
            )
            return self._dispatch_handoff(manifest, item)
        return {"status": "no_update"}

    def continue_cloud_handoff(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None = None,
    ) -> dict[str, Any]:
        """Advance one exact upload claim through authoritative acceptance."""
        manifest = self._load()
        item = manifest["items"].get(identity)
        if not isinstance(item, dict):
            raise EnrichmentError("Xiaocao cloud handoff item is missing")
        if str(item.get("capture_job_id") or "") != capture_job_id:
            raise EnrichmentError("Xiaocao cloud handoff capture binding changed")
        if item.get("status") == "completed":
            return {
                "status": "no_update",
                "handoff_dispatched": False,
                "already_completed": True,
                "identity": identity,
                "capture_job_id": capture_job_id,
            }
        if item.get("status") == "handoff_ready":
            return self._dispatch_handoff(manifest, item)
        if item.get("status") not in {
            "capture_armed",
            "awaiting_playback",
            "playback_activated",
        }:
            raise EnrichmentError("Xiaocao cloud handoff is not resumable")

        state = self.capture_driver.advance(
            identity,
            capture_job_id,
            opencli_session=opencli_session,
            opencli_profile=opencli_profile,
        )
        state_capture_job_id = str(state.get("capture_job_id") or "")
        if state_capture_job_id and state_capture_job_id != capture_job_id:
            raise EnrichmentError("Xiaocao cloud handoff advance is not bound")
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
        if state.get("event") != "xiaocao_live_upload_pending":
            raise EnrichmentError("Xiaocao cloud handoff regressed before upload")
        if item.get("status") != "playback_activated":
            item = self._transition(manifest, item, "playback_activated")
        return self._waiting(item, state)

    def _check_playback(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any]:
        request = {
            "event": "daily_browser_input_required",
            "adapter": "xiaocao_wechat_live",
            "action": "activate_xiaoetong_playback",
            "subscription_id": item["identity"],
            "page_url": item["page_url"],
            "check_reason": reason,
            "password_policy": {
                "only_if_password_gate_visible": True,
                "password": self.password,
            },
            "instructions": (
                "Refresh the bound page and inspect its visible lifecycle state. "
                "If it is directly playable, play it without entering a password. "
                "If a password gate is visible, enter the supplied password and "
                "submit it, then start playback. If it is waiting to start, live "
                "without replay, or generating a replay, return that state without "
                "waiting for it to change."
            ),
            "required_response": {
                "action": "activate_xiaoetong_playback",
                "subscription_id": item["identity"],
                "page_url": item["page_url"],
                "page_state": (
                    "account_login_required|waiting_to_start|live|"
                    "replay_generating|playable|password_required|unknown"
                ),
                "activated": "boolean",
                "password_used": "boolean",
            },
        }
        response = self.browser_exchange(request)
        self._validate_browser_response(request, response)
        response_url = str(response.get("page_url") or "")
        activated = response.get("activated") is True
        page_state = str(
            response.get("page_state")
            or ("playable" if activated else "unknown")
        ).strip()
        if (
            not activated
            and response.get("password_used") is not True
            and page_state in {"account_login_required", "unknown"}
            and (
                (
                    page_state == "account_login_required"
                    and response_url == item["page_url"]
                )
                or self._is_bound_account_login_redirect(
                    response_url,
                    expected_page_url=item["page_url"],
                    expected_source_identity=item["source_identity"],
                )
            )
        ):
            raise EnrichmentError("Xiaoetong account login is required")
        response_page, response_identity = self._canonical_page(response_url)
        if (
            response_page != item["page_url"]
            or response_identity != item["source_identity"]
            or page_state not in _PLAYBACK_PAGE_STATES
        ):
            raise EnrichmentError("browser did not check the bound live page")
        return self._transition(
            manifest,
            item,
            "playback_activated" if activated else "awaiting_playback",
            observed_page_state=page_state,
            password_used=response.get("password_used") is True,
        )

    def run_once(
        self,
        *,
        opencli_session: str,
        opencli_profile: str | None = None,
        only_identity: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load()
        if only_identity is None:
            self._poll(manifest)
            self._supersede_older_unarmed_previews(manifest)
            item = self._next_pending(manifest)
        else:
            item = manifest["items"].get(only_identity)
            if not isinstance(item, dict):
                raise EnrichmentError(
                    "Xiaocao narrow resume item is missing"
                )
            item = dict(item)
            if item.get("status") in _TERMINAL:
                return {
                    "status": "no_update",
                    "identity": only_identity,
                    "already_completed": True,
                }
        if item is None:
            return {"status": "no_update"}

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
                    "page_state": (
                        "account_login_required|playable|password_required|unknown"
                    ),
                },
            }
            response = self.browser_exchange(request)
            self._validate_browser_response(request, response)
            observed_page_state = str(
                response.get("page_state") or "unknown"
            ).strip()
            page_url, source_identity = self._canonical_browser_page(
                str(response.get("page_url") or ""),
                page_state=observed_page_state,
            )
            item = self._transition(
                manifest,
                item,
                "page_resolved",
                page_url=page_url,
                source_identity=source_identity,
                observed_page_state=observed_page_state,
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

        playback_checked = False
        if item["status"] == "capture_armed":
            item = self._check_playback(
                manifest,
                item,
                reason="initial",
            )
            playback_checked = True
            if item["status"] == "awaiting_playback":
                return self._waiting(item, {"status": "awaiting_playback"})

        if item["status"] == "handoff_ready":
            return self._dispatch_handoff(manifest, item)

        state = self.capture_driver.advance(
            item["identity"],
            item["capture_job_id"],
            opencli_session=opencli_session,
            opencli_profile=opencli_profile,
        )
        if (
            not playback_checked
            and item["status"] in {"awaiting_playback", "playback_activated"}
            and state.get("source_job_status") == "awaiting_playback"
        ):
            item = self._check_playback(
                manifest,
                item,
                reason="awaiting_playback",
            )
            if item["status"] == "awaiting_playback":
                return self._waiting(item, {"status": "awaiting_playback"})
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
        if (
            state.get("event") == "xiaocao_live_upload_pending"
            and item.get("status") != "playback_activated"
        ):
            item = self._transition(manifest, item, "playback_activated")
        return self._waiting(item, state)
