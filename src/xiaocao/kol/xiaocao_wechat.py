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
    SnifferError,
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
_GOOSE_LIVE_MINI_PROGRAM = re.compile(
    r"#小程序://(?P<name>鹅直播)/(?P<token>[A-Za-z0-9_-]{8,128})"
)
_XIAOETONG_SOURCE_IDENTITY = re.compile(
    r"^xiaoetong:(?P<app_id>app[A-Za-z0-9]+):(?P<live_id>l_[A-Za-z0-9]+)$"
)
_TERMINAL = {"historical_baseline", "superseded", "completed"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_FILE_ID = re.compile(r"^[0-9]{8,32}$")
_MAX_HANDOFF_BYTES = 1024 * 1024
_CAPTURE_PROGRESS_POLL_SECONDS = 30
_PLAYBACK_RECHECK_MINUTES = 20
_LOCAL_CAPTURE_FIRST_HOUR = 7
_LOCAL_CAPTURE_LAST_HOUR = 22
_PLAYBACK_PAGE_STATES = {
    "account_login_required",
    "waiting_to_start",
    "live",
    "replay_generating",
    "playable",
    "password_required",
    "source_temporarily_unavailable",
    "unknown",
}
XIAOCAO_PLAYBACK_ROUTE_H5 = "xiaoetong_h5"
XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM = "wechat_mini_program"
_PLAYBACK_ROUTES = frozenset(
    {
        XIAOCAO_PLAYBACK_ROUTE_H5,
        XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
    }
)
_MINI_PROGRAM_PLAYBACK_STATES = _PLAYBACK_PAGE_STATES | {
    "mini_program_media_observed",
    "mini_program_waiting",
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
    local = observed_at.astimezone(BEIJING)
    elapsed = local.minute % _PLAYBACK_RECHECK_MINUTES
    deadline = (local + timedelta(
        minutes=_PLAYBACK_RECHECK_MINUTES - elapsed
    )).replace(
        second=0,
        microsecond=0,
    )
    if deadline.hour < _LOCAL_CAPTURE_FIRST_HOUR:
        deadline = deadline.replace(
            hour=_LOCAL_CAPTURE_FIRST_HOUR,
            minute=0,
        )
    elif deadline.hour > _LOCAL_CAPTURE_LAST_HOUR:
        deadline = (deadline + timedelta(days=1)).replace(
            hour=_LOCAL_CAPTURE_FIRST_HOUR,
            minute=0,
        )
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
        or (
            host.endswith(".h5.xeknow.com")
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
        for match in _GOOSE_LIVE_MINI_PROGRAM.finditer(raw_message):
            mini_program_name = match.group("name")
            mini_program_token = match.group("token")
            identity = "kol-wechat-" + _sha256_text(
                f"{username}\n{published.isoformat()}\n"
                f"#小程序://{mini_program_name}/{mini_program_token}"
            )[:24]
            items[identity] = {
                "identity": identity,
                "contact": contact,
                "contact_username": username,
                "published_at": published.isoformat(timespec="seconds"),
                "entry_kind": "wechat_mini_program",
                "mini_program_name": mini_program_name,
                "mini_program_token": mini_program_token,
                "message_sha256": _sha256_text(raw_message),
            }
        # Discovery is already bound to the exact registered contact.  Message
        # copy is not a stable contract, so iterate every URL and rely on the
        # Xiaoetong allowlist here plus exact live/recorded browser binding
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
    def prepare_playback(self, identity: str, capture_job_id: str) -> dict[str, Any]: ...

    def bind_mini_program_capture(
        self,
        identity: str,
        capture_job_id: str,
        *,
        source_identity: str,
        candidate_id: str,
    ) -> dict[str, Any]: ...

    def arm(
        self,
        identity: str,
        page_url: str | None,
        *,
        media_file_id: str | None = None,
    ) -> dict[str, Any]: ...

    def advance(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None,
        recorded_media_url: str | None = None,
    ) -> dict[str, Any]: ...

    def advance_capture(
        self,
        identity: str,
        capture_job_id: str,
        *,
        recorded_media_url: str | None = None,
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

    def arm(
        self,
        identity: str,
        page_url: str | None,
        *,
        media_file_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self._service(identity).start(
                page_url=page_url,
                media_file_id=media_file_id,
            )
        except SnifferError as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao sniffer request failed",
                category="transport_error",
                code="sniffer_request_failed",
                stage="source_run",
            ) from exc

    def prepare_playback(self, identity: str, capture_job_id: str) -> dict[str, Any]:
        service = self._service(identity)
        capture = service.capture_store.latest(capture_job_id)
        if capture is None or capture.get("status") != "awaiting_capture":
            raise EnrichmentError("native playback requires the existing awaiting capture")
        ready = service.start()
        if ready.get("capture_job_id") != capture_job_id:
            raise EnrichmentError("native playback resumed a different capture")
        return ready

    def advance(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None,
        recorded_media_url: str | None = None,
    ) -> dict[str, Any]:
        service = self._service(identity)
        published = self.published_handoff(identity, capture_job_id)
        if published is not None:
            return {**published, "idempotent_replay": True}
        capture = service.capture_store.latest(capture_job_id)
        if capture is None or capture.get("status") != "downloaded":
            service.start()
        try:
            return service.advance(
                capture_job_id,
                opencli_session=opencli_session,
                opencli_profile=opencli_profile,
                recorded_media_url=recorded_media_url,
            )
        except InvalidSourcePage as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao recorded media URL binding failed",
                category="contract_error",
                code="recorded_media_url_binding_invalid",
                stage="compressed_capture",
            ) from exc
        except SnifferError as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao sniffer request failed",
                category="transport_error",
                code="sniffer_request_failed",
                stage="source_run",
            ) from exc

    def bind_mini_program_capture(
        self,
        identity: str,
        capture_job_id: str,
        *,
        source_identity: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        """Bind the UI observation to a fresh, exact sniffer candidate."""
        source_match = _XIAOETONG_SOURCE_IDENTITY.fullmatch(source_identity)
        if source_match is None or not candidate_id:
            raise EnrichmentError("native capture identity is missing")
        service = self._service(identity)
        current = service.capture_store.latest(capture_job_id)
        if current is None:
            raise EnrichmentError("native capture job is missing")
        if current.get("status") != "awaiting_capture":
            if (
                (current.get("expected_source") or {}).get("source_identity")
                == source_identity
                and (current.get("candidate") or {}).get("id") == candidate_id
            ):
                return current
            raise EnrichmentError("native capture was already bound differently")
        app_id = source_match.group("app_id")
        live_id = source_match.group("live_id")
        candidates = [
            row for row in service.sniffer.candidates()
            if row.get("id") == candidate_id and row.get("live_id") == live_id
        ]
        if len(candidates) != 1:
            raise EnrichmentError("native capture candidate is missing or ambiguous")
        candidate = candidates[0]
        source_host = urlsplit(str(candidate.get("source_url") or "")).hostname
        if source_host not in {
            f"{app_id}.{surface}.{domain}"
            for surface in ("h5", "mp")
            for domain in ("xiaoeknow.com", "xe-live.com")
        }:
            raise EnrichmentError("native capture candidate belongs to another app")
        try:
            captured_at = datetime.fromisoformat(str(candidate.get("captured") or ""))
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=BEIJING)
            armed_at = datetime.fromisoformat(current["created_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EnrichmentError("native capture timestamp is invalid") from exc
        if captured_at <= armed_at:
            raise EnrichmentError("native capture candidate predates its arm")
        media = urlsplit(str(candidate.get("url") or ""))
        if (
            media.scheme != "https"
            or candidate.get("media_type") != "m3u8"
            or re.fullmatch(r"playlist(?:_eof|\.f[0-9]+)?\.m3u8", Path(media.path).name)
            is None
        ):
            raise EnrichmentError("native capture is not a finite replay candidate")
        page_url = f"https://{app_id}.h5.xiaoeknow.com/v4/course/alive/{live_id}"
        current = service.capture_store.transition(
            current,
            "mini_program_source_bound",
            expected_source=canonical_xiaoetong_source(page_url),
        )
        bound = service.capture_store.bind_source_candidate(
            current, candidates, candidate_id=candidate_id,
        )
        if bound is None:
            raise EnrichmentError("native capture could not bind its candidate")
        return bound

    def advance_capture(
        self,
        identity: str,
        capture_job_id: str,
        *,
        recorded_media_url: str | None = None,
    ) -> dict[str, Any]:
        """Reconcile the exact source job before requesting another UI action."""

        service = self._service(identity)
        capture = service.capture_store.latest(capture_job_id)
        if capture is None or capture.get("status") != "downloaded":
            service.start()
        try:
            return service.advance_capture(
                capture_job_id,
                recorded_media_url=recorded_media_url,
            )
        except InvalidSourcePage as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao recorded media URL binding failed",
                category="contract_error",
                code="recorded_media_url_binding_invalid",
                stage="compressed_capture",
            ) from exc
        except SnifferError as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao sniffer request failed",
                category="transport_error",
                code="sniffer_request_failed",
                stage="source_run",
            ) from exc

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

    def needs_recorded_media_url(
        self,
        identity: str,
        capture_job_id: str,
    ) -> bool:
        capture = self._service(identity).capture_store.latest(capture_job_id)
        expected = (capture or {}).get("expected_source") or {}
        resource_id = str(expected.get("source_resource_id") or "")
        return bool(
            capture
            and resource_id.startswith("v_")
            and capture.get("status") != "downloaded"
        )


class XiaocaoWechatLiveSubscription:
    """Exactly-once WeChat discovery and capture state machine.

    ``xiaoetong_h5`` remains a compatibility route for direct callers and
    historical tests.  The local Xiaocao runtime selects
    ``wechat_mini_program`` so a provider-paused H5 player is not a download
    dependency.
    """

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
        playback_route: str = XIAOCAO_PLAYBACK_ROUTE_H5,
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
        self.playback_route = str(playback_route or "").strip()
        if self.playback_route not in _PLAYBACK_ROUTES:
            raise ValueError(
                f"unsupported Xiaocao playback route: {self.playback_route}"
            )
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
        if (parsed.hostname or "").lower().endswith(".mp.xiaoeknow.com"):
            return cls._canonical_page(page_url)
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
        return redirect_identity == expected_source_identity

    @classmethod
    def _is_bound_account_login_page(
        cls,
        page_url: str,
        *,
        expected_page_url: str,
        expected_source_identity: str,
    ) -> bool:
        """Accept a direct MP wrapper as a bound login observation."""
        try:
            canonical_page, canonical_identity = cls._canonical_page(page_url)
        except EnrichmentError:
            return False
        return canonical_identity == expected_source_identity

    @classmethod
    def _is_bound_provider_block_redirect(
        cls,
        page_url: str,
        *,
        expected_page_url: str,
        expected_source_identity: str,
    ) -> bool:
        parsed = urlsplit(page_url.strip())
        expected = urlsplit(expected_page_url)
        identity_parts = expected_source_identity.split(":", 2)
        if (
            len(identity_parts) != 3
            or identity_parts[0] != "xiaoetong"
            or not identity_parts[1]
        ):
            return False
        app_id = identity_parts[1]
        pieces = [piece for piece in parsed.path.split("/") if piece]
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != f"{app_id}.block.xiaoeeye.com"
            or expected.netloc.lower() != f"{app_id}.h5.xiaoeknow.com"
            or len(pieces) != 4
            or re.fullmatch(r"v[0-9]+", pieces[0]) is None
            or pieces[1:3] != ["course", "alive"]
            or pieces[3] != identity_parts[2]
        ):
            return False
        try:
            canonical_page, canonical_identity = cls._canonical_page(
                expected_page_url
            )
        except EnrichmentError:
            return False
        return (
            canonical_page == expected_page_url
            and canonical_identity == expected_source_identity
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
            # Short live windows need the next configured 20-minute boundary.
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
        waiting_item["playback_route"] = str(
            item.get("playback_route") or self.playback_route
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
            recorded_media_url=self._media_url_if_needed(item),
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
        if self.playback_route == XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM:
            return self._check_mini_program_playback(
                manifest,
                item,
                reason=reason,
            )
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
                "If a course-password gate is visible, enter the supplied password "
                "and submit it. As soon as the bound page has a current video, use "
                "the same Browser tab's page-level control to set and read back "
                "video.muted=true and video.volume=0; use the tab cdp capability's "
                "scoped Runtime.evaluate when custom player controls are hidden. "
                "Then start playback and prove advancing media time. If it is "
                "waiting to start, live without replay, or generating a replay, "
                "return that state without waiting for it to change. If the same "
                "app and resource redirect "
                "to its block.xiaoeeye.com page, return "
                "source_temporarily_unavailable. If the page first lands on a "
                "generic Xiaoetong unavailable or personal-center shell, derive "
                "the same app/resource block URL by replacing the .h5.xiaoeknow.com "
                "host suffix with .block.xiaoeeye.com, navigate the same tab to "
                "that exact path, and return the resulting bound block URL. Do not "
                "report source_temporarily_unavailable for an unrelated URL."
            ),
            "required_response": {
                "action": "activate_xiaoetong_playback",
                "subscription_id": item["identity"],
                "page_url": item["page_url"],
                "page_state": (
                    "account_login_required|waiting_to_start|live|"
                    "replay_generating|playable|password_required|unknown"
                    "|source_temporarily_unavailable"
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
                or self._is_bound_account_login_page(
                    response_url,
                    expected_page_url=item["page_url"],
                    expected_source_identity=item["source_identity"],
                )
            )
        ):
            raise EnrichmentDiagnosticError(
                "Xiaoetong account login is required",
                category="authentication_error",
                code="xiaoetong_account_login_required",
                stage="playback_authorization",
            )
        if page_state == "source_temporarily_unavailable":
            if (
                activated
                or response.get("password_used") is True
                or not self._is_bound_provider_block_redirect(
                    response_url,
                    expected_page_url=item["page_url"],
                    expected_source_identity=item["source_identity"],
                )
            ):
                raise EnrichmentError(
                    "browser provider block is not bound to the live page"
                )
            return self._transition(
                manifest,
                item,
                "awaiting_playback",
                observed_page_state=page_state,
                password_used=False,
            )
        response_page, response_identity = self._canonical_page(response_url)
        if (
            response_identity != item["source_identity"]
            or page_state not in _PLAYBACK_PAGE_STATES
        ):
            raise EnrichmentError("browser did not check the bound live page")
        return self._transition(
            manifest,
            item,
            "playback_activated" if activated else "awaiting_playback",
            page_url=response_page,
            observed_page_state=page_state,
            password_used=response.get("password_used") is True,
            playback_route=self.playback_route,
        )

    def _check_mini_program_playback(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any]:
        """Use native WeChat playback while keeping the H5 identity anchor.

        The mini-program is the user-visible playback surface.  The local
        ``wx_channels_download`` sniffer observes its requests and the source
        job later proves the same ``live_id`` before creating a download task.
        No signed media URL is accepted from this structured input.
        """
        expected_source_identity = str(item.get("source_identity") or "")
        expected_live_id = (
            expected_source_identity.rsplit(":", 1)[-1]
            if expected_source_identity
            else ""
        )
        native_entry = item.get("entry_kind") == "wechat_mini_program"
        request = {
            "event": "daily_browser_input_required",
            "adapter": "xiaocao_wechat_live",
            "action": "activate_xiaoetong_mini_program",
            "subscription_id": item["identity"],
            "check_reason": reason,
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "operator": "agent",
            "user_action_required": False,
            "ui_policy": {
                "app_bundle_id": "com.tencent.xinWeChat",
                "surface": "visible_foreground_ui",
                "action_mode": "one_action_then_state_readback",
                "max_activation_attempts": 1,
            },
            "password_policy": {
                "only_if_password_gate_visible": True,
                "password": self.password,
            },
            "instructions": (
                "用 wechat-cli 已定位的原始联系人和发布时间，在本机微信中只打开"
                "该条原始 #小程序://鹅直播/ 消息一次；不要复制发送消息、猜测 URL "
                "Scheme，或反复拉起小程序。若小程序显示课程口令门，只在可见口令门"
                "输入提供的口令。"
                if native_entry
                else
                "在本机微信中打开 source_url 对应的同一场小鹅通小程序回放，"
                "不要打开或依赖浏览器 H5 播放页。若小程序显示课程口令门，"
                "只在可见口令门输入提供的口令。选择与 source_url 对应的历史回放；"
            ) + (
                "让目标画面开始请求媒体即可，不需要持续播放。确认本机"
                "wx_channels_download 已观察到媒体请求，并从其无凭证日志确认"
                + (
                    "该次新候选的 live_id 和 app_id。"
                    if native_entry
                    else "live_id 与要求的 live_id 完全一致。"
                )
                + "不要返回签名 m3u8、Cookie、"
                "密钥或其他请求头；返回布尔型 media_request_observed 和绑定字段。"
            ),
            "required_response": {
                "action": "activate_xiaoetong_mini_program",
                "subscription_id": item["identity"],
                "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
                "source_identity": (
                    expected_source_identity
                    or "xiaoetong:<observed_app_id>:<observed_live_id>"
                ),
                "live_id": expected_live_id or "observed l_ live_id",
                "operator": "agent",
                "page_state": (
                    "account_login_required|waiting_to_start|live|"
                    "replay_generating|playable|password_required|unknown|"
                    "mini_program_media_observed|mini_program_waiting"
                ),
                "activated": "boolean",
                "media_request_observed": "boolean",
                "password_used": "boolean",
                "page_url": (
                    "optional canonical H5 identity anchor; omit when the native "
                    "mini-program supplied no page URL"
                ),
            },
        }
        if native_entry:
            request.update({
                "contact": item["contact"],
                "published_at": item["published_at"],
                "mini_program_name": item["mini_program_name"],
                "mini_program_token": item["mini_program_token"],
            })
            request["required_response"]["candidate_id"] = (
                "exact fresh finite replay candidate id; omit if not observed"
            )
        else:
            request.update({
                "source_url": item["source_url"],
                "page_url": item["page_url"],
                "launch_resolver_command": [
                    ".venv/bin/python", "scripts/kol_xiaoetong_launch.py",
                    "--source-url", item["source_url"],
                    "--expected-identity", expected_source_identity,
                ],
            })
            request["instructions"] = (
                "先以 PYTHONPATH=src 执行 launch_resolver_command，只解析官方链接。"
                "同一任务已 armed 且限定域名 PAC 健康时，执行返回的 launch_command "
                "一次；若当前已是目标小程序则不重开。只用商户生成且校验场次一致的 "
                "Scheme，不猜参数。解析失败再用可见原始消息入口；不要把主聊天窗口"
                "白色截图当作微信退出。后续密码、播放在可见小程序窗口操作。"
            ) + request["instructions"]
        self.capture_driver.prepare_playback(item["identity"], item["capture_job_id"])
        response = self.browser_exchange(request)
        self._validate_browser_response(request, response)
        if (
            response.get("playback_surface")
            != XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM
        ):
            raise EnrichmentError(
                "WeChat mini-program playback binding is invalid"
            )

        observed_source_identity = str(response.get("source_identity") or "")
        observed_live_id = str(response.get("live_id") or "")
        source_match = _XIAOETONG_SOURCE_IDENTITY.fullmatch(
            observed_source_identity
        )
        if expected_live_id:
            source_bound = (
                observed_source_identity == expected_source_identity
                and observed_live_id == expected_live_id
            )
        else:
            source_bound = bool(
                source_match
                and observed_live_id
                and source_match.group("live_id") == observed_live_id
            )

        response_url = str(response.get("page_url") or "").strip()
        if response_url:
            response_page, response_identity = self._canonical_page(response_url)
            if response_identity != observed_source_identity:
                raise EnrichmentError(
                    "WeChat mini-program page anchor changed its live binding"
                )
        else:
            response_page = str(item.get("page_url") or "")

        page_state = str(
            response.get("page_state")
            or ("playable" if response.get("activated") is True else "unknown")
        ).strip()
        if page_state not in _MINI_PROGRAM_PLAYBACK_STATES:
            raise EnrichmentError(
                "WeChat mini-program returned an unknown playback state"
            )
        if page_state == "account_login_required":
            raise EnrichmentDiagnosticError(
                "Xiaoetong account login is required",
                category="authentication_error",
                code="xiaoetong_account_login_required",
                stage="playback_authorization",
            )
        media_request_observed = response.get("media_request_observed") is True
        if (expected_live_id or media_request_observed) and not source_bound:
            raise EnrichmentError(
                "WeChat mini-program playback binding is invalid"
            )
        activated = response.get("activated") is True and media_request_observed
        if native_entry and activated:
            self.capture_driver.bind_mini_program_capture(
                item["identity"],
                item["capture_job_id"],
                source_identity=observed_source_identity,
                candidate_id=str(response.get("candidate_id") or ""),
            )
        fields: dict[str, Any] = {
            "observed_page_state": page_state,
            "password_used": response.get("password_used") is True,
            "playback_route": self.playback_route,
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "media_request_observed": media_request_observed,
        }
        if response_page:
            fields["page_url"] = response_page
        if source_bound and (expected_live_id or activated):
            fields.update({
                "source_identity": observed_source_identity,
                "source_resource_id": observed_live_id,
            })
            candidate_id = str(response.get("candidate_id") or "").strip()
            if candidate_id:
                fields["candidate_id"] = candidate_id
        return self._transition(
            manifest,
            item,
            "playback_activated" if activated else "awaiting_playback",
            **fields,
        )

    def _recorded_media_url(self, item: dict[str, Any]) -> str | None:
        resource_id = str(item.get("source_identity") or "").rsplit(":", 1)[-1]
        if not resource_id.startswith("v_"):
            return None
        request = {
            "event": "daily_browser_input_required",
            "adapter": "xiaocao_wechat_live",
            "action": "resolve_xiaoetong_media_url",
            "subscription_id": item["identity"],
            "page_url": item["page_url"],
            "media_file_id": item["media_file_id"],
            "instructions": (
                "Read the currently playing page's actual HTTPS m3u8 network "
                "request. Return the full short-lived URL whose path is bound "
                "to the supplied media_file_id. Do not return cookies, DRM "
                "keys, or unrelated request headers."
            ),
            "required_response": {
                "action": "resolve_xiaoetong_media_url",
                "subscription_id": item["identity"],
                "page_url": item["page_url"],
                "media_file_id": item["media_file_id"],
                "media_url": "full short-lived signed HTTPS m3u8 URL",
            },
        }
        response = self.browser_exchange(request)
        self._validate_browser_response(request, response)
        if (
            response.get("page_url") != item["page_url"]
            or response.get("media_file_id") != item["media_file_id"]
        ):
            raise EnrichmentError("browser media URL response is not bound")
        media_url = str(response.get("media_url") or "").strip()
        if not media_url:
            raise EnrichmentError("browser media URL response is missing")
        return media_url

    def _media_url_if_needed(self, item: dict[str, Any]) -> str | None:
        predicate = getattr(
            self.capture_driver,
            "needs_recorded_media_url",
            None,
        )
        if not callable(predicate) or not predicate(
            item["identity"],
            item["capture_job_id"],
        ):
            return None
        return self._recorded_media_url(item)

    def _resolve_page(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
    ) -> dict[str, Any]:
        request = {
            "event": "daily_browser_input_required",
            "adapter": "xiaocao_wechat_live",
            "action": "resolve_xiaoetong_page",
            "subscription_id": item["identity"],
            "source_url": item["source_url"],
            "playback_route": self.playback_route,
            "instructions": (
                "Resolve only the stable Xiaoetong app/resource identity needed to "
                "arm the capture job. The H5 page may be provider-paused; do not "
                "treat H5 playback as proof of download readiness."
                if self.playback_route
                == XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM
                else "Resolve the current Xiaoetong page and its playback state."
            ),
            "required_response": {
                "action": "resolve_xiaoetong_page",
                "subscription_id": item["identity"],
                "page_url": "current Xiaoetong MP wrapper or H5 page URL",
                "page_state": (
                    "account_login_required|playable|password_required|unknown"
                ),
                "media_file_id": (
                    "digits from the bound video element for a recorded-video "
                    "page; omit for a live page"
                ),
            },
        }
        if self.playback_route == XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM:
            request["launch_resolver_command"] = [
                ".venv/bin/python", "scripts/kol_xiaoetong_launch.py",
                "--source-url", item["source_url"],
            ]
            request["instructions"] = (
                "First run launch_resolver_command with PYTHONPATH=src; it is "
                "read-only and validates the merchant-issued WeChat launch link. "
                "Return its page_url with page_state=unknown, then let the runner "
                "arm before executing any launch_command. If no launch plan is "
                "available, resolve the supplied URL through the visible browser. "
            ) + request["instructions"]
        response = self.browser_exchange(request)
        self._validate_browser_response(request, response)
        observed_page_state = str(
            response.get("page_state") or "unknown"
        ).strip()
        page_url, source_identity = self._canonical_browser_page(
            str(response.get("page_url") or ""),
            page_state=observed_page_state,
        )
        resource_id = source_identity.rsplit(":", 1)[-1]
        media_file_id = str(response.get("media_file_id") or "").strip()
        if (
            (
                resource_id.startswith("v_")
                and not _MEDIA_FILE_ID.fullmatch(media_file_id)
            )
            or (not resource_id.startswith("v_") and media_file_id)
        ):
            raise EnrichmentError("browser recorded media binding is invalid")
        fields: dict[str, Any] = {
            "page_url": page_url,
            "source_identity": source_identity,
            "observed_page_state": observed_page_state,
            "playback_route": self.playback_route,
        }
        if media_file_id:
            fields["media_file_id"] = media_file_id
        return self._transition(
            manifest,
            item,
            "page_resolved",
            **fields,
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

        if (
            item["status"] == "discovered"
            and item.get("entry_kind") == "wechat_mini_program"
        ):
            if self.playback_route != XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM:
                raise EnrichmentError("native entry requires the mini-program route")
            item = self._transition(
                manifest,
                item,
                "page_resolved",
                observed_page_state="unknown",
                playback_route=self.playback_route,
            )
        elif item["status"] == "discovered":
            item = self._resolve_page(manifest, item)

        if (
            item["status"] == "page_resolved"
            and str(item.get("source_identity") or "")
            .rsplit(":", 1)[-1]
            .startswith("v_")
            and not item.get("media_file_id")
        ):
            item = self._resolve_page(manifest, item)

        if item["status"] == "page_resolved":
            armed = self.capture_driver.arm(
                item["identity"],
                str(item.get("page_url") or "") or None,
                media_file_id=str(item.get("media_file_id") or "") or None,
            )
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
        capture_reconciled = False
        resource_id = str(item.get("source_identity") or "").rsplit(":", 1)[-1]
        if (
            item["status"] in {"capture_armed", "awaiting_playback"}
            and resource_id.startswith("l_")
        ):
            capture_state = self.capture_driver.advance_capture(
                item["identity"],
                item["capture_job_id"],
            )
            source_job_status = str(
                capture_state.get("source_job_status") or ""
            )
            capture_reconciled = (
                capture_state.get("status") != "awaiting_capture"
                or source_job_status
                in {"playlist_detected", "task_created"}
            )

        if item["status"] == "capture_armed" and not capture_reconciled:
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

        if item["status"] == "awaiting_playback" and not capture_reconciled:
            item = self._check_playback(
                manifest,
                item,
                reason="awaiting_playback",
            )
            playback_checked = True
            if item["status"] == "awaiting_playback":
                return self._waiting(item, {"status": "awaiting_playback"})

        try:
            state = self.capture_driver.advance(
                item["identity"],
                item["capture_job_id"],
                opencli_session=opencli_session,
                opencli_profile=opencli_profile,
                recorded_media_url=self._media_url_if_needed(item),
            )
        except InvalidSourcePage as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao recorded media URL binding failed",
                category="contract_error",
                code="recorded_media_url_binding_invalid",
                stage="compressed_capture",
            ) from exc
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
                recorded_media_url=self._media_url_if_needed(item),
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
