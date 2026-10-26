"""Local WeChat discovery for resumable Xiaocao mini-program live capture.

This adapter keeps the hourly coordinator on metadata only.  A Xiaoetong H5
URL can establish a credential-free source identity, but playback happens only
in the native WeChat mini-program.  All video bytes are owned by
:class:`XiaocaoLiveService` and the external sniffer/downloader.
"""

from __future__ import annotations

import fcntl
from copy import deepcopy
import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from .capture import (
    InvalidSourcePage,
    SnifferError,
    canonical_xiaoetong_source,
    resolve_xiaoetong_h5_page,
    _safe_candidate,
)
from .enrichment_types import (
    EnrichmentDiagnosticError, EnrichmentError, NativePlaybackInputTimeout,
)
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
_XIAOCAO_LIVE_MINI_PROGRAM = re.compile(
    r"#小程序://(?P<name>鹅直播|见势擒龙团)/(?P<token>[A-Za-z0-9_-]{8,128})"
)
_XIAOETONG_SOURCE_IDENTITY = re.compile(
    r"^xiaoetong:(?P<app_id>app[A-Za-z0-9]+):(?P<live_id>l_[A-Za-z0-9]+)$"
)
_TERMINAL = {"historical_baseline", "superseded", "completed", "expired", "unsupported_application", "unsupported_resource"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_HANDOFF_BYTES = 1024 * 1024
_CAPTURE_PROGRESS_POLL_SECONDS = 30
_PLAYBACK_RECHECK_MINUTES = 20
_LOCAL_CAPTURE_FIRST_HOUR = 7
_LOCAL_CAPTURE_LAST_HOUR = 22
_NATIVE_SHARE_BRIDGE_CONFIG = Path("output/live/kol_xiaocao_live/native_share_bridge.json")
_PLAYBACK_PAGE_STATES = {
    "mac_locked_manual_unlock_required",
    "wechat_client_login_required",
    "waiting_to_start",
    "live",
    "replay_generating",
    "playable",
    "password_required",
    "source_temporarily_unavailable",
    "unknown",
}
XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM = "wechat_mini_program"
_NATIVE_PLAYBACK_REPAIR_CODES = {
    "unknown": "native_playback_state_unresolved",
    "mini_program_waiting": "native_playback_state_unresolved",
    "password_required": "native_course_password_unresolved",
    "password_input_incomplete": "native_course_password_input_incomplete",
    "native_bridge_policy_denied": "native_bridge_policy_denied",
    "native_bridge_target_unverified": "native_bridge_target_unverified",
    "native_window_input_unavailable": "native_window_input_unavailable",
}
_MINI_PROGRAM_PLAYBACK_STATES = _PLAYBACK_PAGE_STATES | {
    "mini_program_consent_required",
    "mini_program_media_observed",
    "mini_program_waiting",
} | _NATIVE_PLAYBACK_REPAIR_CODES.keys()


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _media_resource_key(value: Any) -> str:
    """Compare observed media resources without retaining signed queries."""
    parsed = urlsplit(str(value or ""))
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
    ):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _native_v2_merchant_lineage(
    candidate: dict[str, Any], *, app_id: str, live_id: str,
    armed_at: datetime, captured_at: datetime, debug_root: Path | None,
    public_probe: bool = False,
) -> dict[str, Any]:
    """Reopen singleton-owned native responses; never trust global live context."""
    origin = urlsplit(str(candidate.get("source_url") or ""))
    resource = _media_resource_key(candidate.get("url"))
    if (debug_root is None or origin.scheme != "https" or origin.username or origin.password
        or origin.hostname != "xet.kj1team.cn" or app_id != "appsnm3rlcp3566"
        or origin.path != "/_alive/v2/get_lookback_url"
        or candidate.get("source_path") != origin.path
        or candidate.get("json_path") not in {"data.miniAliveVideoUrl", "data.aliveVideoUrl"}
        or not resource):
        raise EnrichmentError("native v2 capture lacks verified merchant source")
    root = debug_root.resolve()
    try:
        events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines() if line]
    except (OSError, ValueError) as exc:
        raise EnrichmentError("native v2 merchant response evidence unavailable") from exc
    evidence = {}
    # Candidate timestamps have second precision. Compare the same clock bin,
    # not an invented chronology derived from UI or network timing.
    upper = captured_at.replace(microsecond=0) + timedelta(seconds=1)
    for event in events:
        u = urlsplit(str(event.get("url") or ""))
        if (event.get("kind") != "response.body" or event.get("status") != 200
            or u.scheme != "https" or u.hostname != origin.hostname
            or u.path not in {"/_alive/v3/base_info", origin.path}):
            continue
        try:
            observed = datetime.fromisoformat(str(event["at"]))
            if observed.tzinfo is None or not armed_at < observed < upper:
                continue
            path = Path(str(event["file"])).resolve()
            if not path.is_relative_to(root / "json") or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            body = path.read_bytes()
            payload = json.loads(body)
            if not isinstance(payload, dict) or type(payload.get("code")) is not int or payload["code"] != 0 or not isinstance(payload.get("data"), dict):
                continue
        except (OSError, KeyError, TypeError, ValueError):
            continue
        evidence[u.path] = (payload["data"], observed, hashlib.sha256(body).hexdigest())
    base = evidence.get("/_alive/v3/base_info")
    replay = evidence.get(origin.path)
    if not base or not replay:
        raise EnrichmentError("native v2 capture lacks post-arm merchant responses")
    info = base[0].get("alive_info") or {}
    if (not isinstance(info, dict) or info.get("app_id") != app_id or info.get("alive_id") != live_id
        or replay[0].get("aliveReviewUrl") != f"/{live_id}.m3u8"
        or base[1] > replay[1]
        or _media_resource_key(replay[0].get(candidate["json_path"].split(".")[-1])) != resource):
        raise EnrichmentError("native v2 response conflicts with exact merchant/media identity")
    finite = {}
    if Path(urlsplit(resource).path).name != "playlist_eof.m3u8":
        if info.get("alive_state") != 3:
            raise EnrichmentError("native replay course has not ended")
        try:
            finite = _observed_native_finite_playlist(candidate, root, armed_at, captured_at)
        except EnrichmentError:
            if not public_probe:
                raise
            # Only the actual merchant-issued public recording, never a
            # redacted signed URL, is eligible for this explicit cache probe.
            raw = replay[0].get(candidate["json_path"].split(".")[-1])
            parsed = urlsplit(str(raw or ""))
            if (parsed.scheme != "https" or parsed.hostname != "live-ex-speed.xiaoeknow.com"
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or str(raw) != resource):
                raise EnrichmentError("native manifest probe requires a public merchant resource")
            result = subprocess.run(["/usr/bin/curl", "-fsS", "--max-time", "20",
                "--proxy", "http://127.0.0.1:2023", "-H", "Cache-Control: no-cache", raw],
                capture_output=True, timeout=25)
            if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
                raise EnrichmentError("native public manifest probe failed")
            # Acceptance still comes from the singleton's observed HTTP body,
            # not from curl's stdout, and certificate validation stays enabled.
            finite = _observed_native_finite_playlist(candidate, root, armed_at, captured_at)
    return {
        "method": "native_v2_merchant_response",
        "media_resource_sha256": _sha256_text(resource),
        "metadata_anchors": [{"candidate_id": candidate["id"], "source_host": origin.hostname,
            "source_path": origin.path, "json_path": candidate["json_path"],
            "response_sha256": replay[2], "base_info_sha256": base[2],
            "app_id": app_id, "live_id": live_id}],
        **({"finite_playlist": finite} if finite else {}),
    }


def _observed_native_finite_playlist(candidate, root, armed_at, captured_at):
    """Only a singleton-saved, post-arm ended VOD response proves this format."""
    resource = _media_resource_key(candidate.get("url"))
    media = urlsplit(resource)
    if media.hostname not in {"live-ex-speed.xiaoeknow.com", "encrypt-k-vod.xet.tech"} or not media.path.endswith(".m3u8"):
        raise EnrichmentError("unreviewed native replay playlist host")
    for line in reversed((root / "events.jsonl").read_text().splitlines()):
        try:
            event = json.loads(line)
            if (event.get("kind") != "response.body" or event.get("status") != 200
                or _media_resource_key(event.get("url")) != resource):
                continue
            observed = datetime.fromisoformat(event["at"])
            if not armed_at < observed <= captured_at + timedelta(minutes=20):
                continue
            path = Path(event["file"]).resolve()
            if not path.is_relative_to(root / "m3u8") or path.stat().st_size > 2 * 1024 * 1024:
                continue
            body = path.read_bytes()
            lines = body.decode().strip().splitlines()
            durations = [float(v.split(":", 1)[1].split(",", 1)[0]) for v in lines if v.startswith("#EXTINF:")]
            segments = [v for v in lines if v.strip() and not v.startswith("#")]
            if (lines[0] != "#EXTM3U" or lines[-1] != "#EXT-X-ENDLIST"
                or any(v.startswith("#EXT-X-PLAYLIST-TYPE:") and v != "#EXT-X-PLAYLIST-TYPE:VOD" for v in lines)
                or not durations
                or len(durations) != len(segments)
                or not all(math.isfinite(v) and v > 0 for v in durations) or sum(durations) < 60):
                continue
            return {"candidate_id": candidate["id"], "media_resource_sha256": _sha256_text(resource),
                "response_sha256": hashlib.sha256(body).hexdigest(), "observed_at": observed.isoformat(),
                "ended": True, "segment_count": len(durations), "duration_seconds": sum(durations)}
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            continue
    raise EnrichmentError("native replay lacks an observed ended VOD playlist")


def _native_direct_media_lineage(
    candidate: dict[str, Any],
    observations: list[dict[str, Any]],
    *,
    app_id: str,
    live_id: str,
    armed_at: datetime,
    captured_at: datetime,
    debug_root: Path | None = None,
) -> dict[str, Any]:
    """Require merchant lookback evidence for a directly requested CDN replay.

    The CDN observation is the fresh capture. Earlier metadata only proves its
    app/live lineage; it must never replace the selected candidate or ticket.
    """
    resource = _media_resource_key(candidate.get("url"))
    source = urlsplit(str(candidate.get("source_url") or ""))
    if source.hostname == "xet.kj1team.cn":
        return _native_v2_merchant_lineage(candidate, app_id=app_id, live_id=live_id,
            armed_at=armed_at, captured_at=captured_at, debug_root=debug_root)
    if (
        not resource or _media_resource_key(candidate.get("source_url")) != resource
        or candidate.get("source_path") != source.path
        or candidate.get("json_path")
        or Path(source.path).name != "playlist_eof.m3u8"
    ):
        raise EnrichmentError("native capture candidate belongs to another app")
    anchors = []
    for row in observations:
        if _media_resource_key(row.get("url")) != resource:
            continue
        origin = urlsplit(str(row.get("source_url") or ""))
        merchant = re.fullmatch(
            r"(?P<app_id>app[A-Za-z0-9]+)\."
            r"(?:(?:h5|mp)\.(?:xiaoeknow\.com|xe-live\.com)"
            r"|h5\.(?:xiaoe-live\.com|xetsdkspace\.com))",
            origin.hostname or "",
        )
        if (
            merchant is None or origin.scheme != "https"
            or origin.username is not None or origin.password is not None
            or origin.path != "/_alive/v3/get_lookback_list"
            or row.get("source_path") != origin.path
            or row.get("media_type") != "m3u8"
            or not re.fullmatch(
                r"data\[[0-9]+\]\.line_sharpness\[[0-9]+\]\.url",
                str(row.get("json_path") or ""),
            )
        ):
            continue
        if merchant.group("app_id") != app_id or row.get("live_id") != live_id:
            raise EnrichmentError("native media has conflicting merchant identity")
        try:
            observed_at = datetime.fromisoformat(str(row.get("captured") or ""))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=BEIJING)
        except ValueError:
            continue
        if row.get("id") and armed_at < observed_at <= captured_at:
            anchors.append({
                "candidate_id": row["id"], "source_host": origin.hostname,
                "source_path": origin.path, "json_path": row["json_path"],
            })
    if not anchors:
        raise EnrichmentError("native CDN capture lacks matching merchant lookback evidence")
    return {
        "method": "direct_manifest_with_merchant_lookback",
        "media_resource_sha256": _sha256_text(resource),
        "metadata_anchors": sorted(anchors, key=lambda row: row["candidate_id"]),
    }


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
    if host == "wxmpurl.cn":
        # Discovery retains the merchant entry only. The launch resolver must
        # independently verify Goose Live and the embedded app/live binding.
        if (parsed.netloc == host and not parsed.query and not parsed.fragment
                and re.fullmatch(r"/[A-Za-z0-9_-]{1,128}", parsed.path)):
            return raw.strip()
        return None
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
        for match in _XIAOCAO_LIVE_MINI_PROGRAM.finditer(raw_message):
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
    def validate_handoff_media(self, identity: str, capture_job_id: str, capsule: dict[str, Any]) -> None: ...

    def can_expire_wait(self, identity: str, capture_job_id: str) -> bool: ...

    def prepare_playback(self, identity: str, capture_job_id: str) -> dict[str, Any]: ...

    def bind_mini_program_capture(
        self,
        identity: str,
        capture_job_id: str,
        *,
        source_identity: str,
        candidate_id: str,
        observed_after: datetime | None = None,
    ) -> dict[str, Any]: ...

    def arm(
        self,
        identity: str,
        page_url: str | None,
    ) -> dict[str, Any]: ...

    def advance(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None,
    ) -> dict[str, Any]: ...

    def advance_capture(
        self,
        identity: str,
        capture_job_id: str,
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

    def can_expire_wait(self, identity: str, capture_job_id: str) -> bool:
        """Only retire an unbound idle capture; preserve every media/job claim."""
        capture = self._service(identity).capture_store.latest(capture_job_id)
        return bool(
            capture
            and capture.get("status") == "awaiting_capture"
            and not any(capture.get(key) for key in (
                "candidate_id", "task_id", "source_job_id", "expected_source",
                "native_unbound_media", "candidate", "download_task_id",
                "download_idempotency_key", "media_path", "retained_live_observation",
            ))
        )

    def arm(
        self,
        identity: str,
        page_url: str | None,
    ) -> dict[str, Any]:
        try:
            return self._service(identity).start(page_url=page_url)
        except SnifferError as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao sniffer request failed",
                category="transport_error",
                code="sniffer_request_failed",
                stage="source_run",
            ) from exc

    def can_resume_unbound_native_repair(self, identity: str, capture_job_id: str) -> bool:
        """A held native observation is neither idle nor accepted media."""
        capture = self._service(identity).capture_store.latest(capture_job_id) or {}
        observed = capture.get("native_unbound_media") or {}
        return bool(
            capture.get("status") == "awaiting_capture"
            and capture.get("native_repair_armed_at")
            and observed.get("source_accepted") is False
            and _SHA256.fullmatch(str(observed.get("media_resource_sha256") or ""))
            and _XIAOETONG_SOURCE_IDENTITY.fullmatch(str(observed.get("source_identity_observed") or ""))
            and not any(capture.get(key) for key in (
                "expected_source", "candidate", "source_job_id", "download_task_id", "task_id",
            ))
        )

    def prepare_playback(self, identity: str, capture_job_id: str) -> dict[str, Any]:
        service = self._service(identity)
        capture = service.capture_store.latest(capture_job_id)
        if (
            capture and capture.get("status") == "captured"
            and capture.get("event") == "capture_detected"
            and not any(capture.get(key) for key in (
                "expected_source", "source_job_id", "download_task_id", "task_id",
                "native_unbound_media", "native_media_lineage", "netdisk_job_id",
                "download_idempotency_key", "media_path", "handoff_id",
            ))
        ):
            manifest_path = self.output_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            item = manifest.get("items", {}).get(identity, {})
            candidate = capture.get("candidate") or {}
            live_wait = (
                isinstance(candidate, dict)
                and item.get("media_request_observed") is True
                and item.get("observed_page_state") == "live"
                and item.get("activated") is False
                and item.get("playback_window_closed") is True
                and candidate.get("host") == "liveplay-mp.xiaoeknow.com"
                and candidate.get("media_type") in {"m3u8", "flv"}
                and bool(candidate.get("id"))
                and bool(candidate.get("live_id"))
                and capture.get("candidate_key") == f"live:{candidate['live_id']}"
            )
            if (
                item.get("capture_job_id") == capture_job_id
                and item.get("entry_kind") == "wechat_mini_program"
                and item.get("status") == "awaiting_playback"
                and not item.get("source_identity")
                and not any(item.get(key) for key in ("candidate_id", "task_id", "handoff_id"))
                and (item.get("media_request_observed") is False or live_wait)
            ):
                # Preserve observations and the original baseline/ID. Neither
                # a global candidate nor a live stream is accepted finite media.
                observation = ({"retained_live_observation": {
                    "candidate": candidate,
                    "candidate_key": capture.get("candidate_key"),
                    "observed_page_state": "live",
                    "media_request_observed": True,
                    "playback_window_closed": True,
                    "source_accepted": False,
                }} if live_wait else {
                    "rejected_global_candidate": candidate,
                    "rejected_global_candidate_key": capture.get("candidate_key"),
                })
                capture = service.capture_store.transition(
                    capture, "live_observation_wait_reconciled" if live_wait else "unaccepted_global_observation_reconciled",
                    status="awaiting_capture",
                    **observation,
                    candidate=None, candidate_key=None,
                )
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
    ) -> dict[str, Any]:
        service = self._service(identity)
        published = self.published_handoff(identity, capture_job_id)
        if published is not None:
            return {**published, "idempotent_replay": True}
        capture = service.capture_store.latest(capture_job_id)
        manifest_path = self.output_dir / "manifest.json"
        if capture is not None and manifest_path.is_file():
            original = json.loads(manifest_path.read_text(encoding="utf-8"))["items"].get(identity)
            if not isinstance(original, dict) or original.get("capture_job_id") != capture_job_id:
                raise EnrichmentError("original publication is not bound to this capture")
            timestamp = datetime.fromisoformat(str(original["published_at"]))
            if timestamp.tzinfo is None or not _SHA256.fullmatch(str(original.get("message_sha256") or "")):
                raise EnrichmentError("original publication timestamp/hash is invalid")
            fields = {"source_published_at": original["published_at"],
                "source_event_date": timestamp.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                "source_subscription_id": identity, "source_message_sha256": original["message_sha256"]}
            if any(capture.get(key) is not None and capture[key] != value for key, value in fields.items()):
                raise EnrichmentError("original publication evidence changed")
            if any(capture.get(key) != value for key, value in fields.items()):
                capture = service.capture_store.transition(capture, "source_publication_bound", **fields)
        if capture is None or capture.get("status") != "downloaded":
            service.start()
        try:
            return service.advance(
                capture_job_id,
                opencli_session=opencli_session,
                opencli_profile=opencli_profile,
            )
        except InvalidSourcePage as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao live source identity is invalid",
                category="contract_error",
                code="xiaocao_live_source_identity_invalid",
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
        observed_after: datetime | None = None,
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
        unbound_identity = (current.get("native_unbound_media") or {}).get("source_identity_observed")
        if unbound_identity and unbound_identity != source_identity:
            raise EnrichmentError("native repair changed the observed source identity")
        observations = service.sniffer.candidates()
        candidates = [row for row in observations if row.get("id") == candidate_id]
        signatures = {(_media_resource_key(row.get("url")), row.get("live_id"),
            _media_resource_key(row.get("source_url")), row.get("source_path"), row.get("json_path")) for row in candidates}
        if not candidates or len(signatures) != 1 or any(row.get("live_id") != live_id for row in candidates):
            raise EnrichmentError("native capture candidate is missing or ambiguous")
        # A numeric, unsigned recording may be observed again after a backend
        # repair with the same URL-derived ID. Retain its actual latest timestamp.
        candidate = max(candidates, key=lambda row: str(row.get("captured") or ""))
        candidates = [candidate]
        try:
            captured_at = datetime.fromisoformat(str(candidate.get("captured") or ""))
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=BEIJING)
            armed_at = datetime.fromisoformat(
                current.get("native_repair_armed_at") or current["created_at"]
            )
            if observed_after is not None:
                if observed_after.tzinfo is None:
                    raise ValueError("naive human playback boundary")
                armed_at = max(armed_at, observed_after)
        except (KeyError, TypeError, ValueError) as exc:
            raise EnrichmentError("native capture timestamp is invalid") from exc
        if captured_at <= armed_at:
            raise EnrichmentError("native capture candidate predates its arm")
        media = urlsplit(str(candidate.get("url") or ""))
        if (
            media.scheme != "https"
            or candidate.get("media_type") != "m3u8"
            or (re.fullmatch(r"playlist(?:_eof|\.f[0-9]+)?\.m3u8", Path(media.path).name)
                is None and (media.hostname != "live-ex-speed.xiaoeknow.com"
                    or urlsplit(str(candidate.get("source_url") or "")).hostname != "xet.kj1team.cn"))
        ):
            raise EnrichmentError("native capture is not a finite replay candidate")
        source_host = urlsplit(str(candidate.get("source_url") or "")).hostname
        lineage = {}
        if current.get("native_repair_armed_at") or source_host not in {
            f"{app_id}.{surface}.{domain}"
            for surface in ("h5", "mp")
            for domain in ("xiaoeknow.com", "xe-live.com")
        }:
            lineage = _native_direct_media_lineage(
                candidate, observations, app_id=app_id, live_id=live_id,
                armed_at=armed_at, captured_at=captured_at,
                debug_root=(service.sniffer_binary.parent / "elive_live_debug") if hasattr(service, "sniffer_binary") else None,
            )
        old_resource = (current.get("native_media_lineage") or current.get("native_unbound_media") or {}).get("media_resource_sha256")
        if current.get("native_repair_armed_at") and old_resource != lineage.get("media_resource_sha256"):
            raise EnrichmentError("native repair changed the bound media resource")
        page_url = f"https://{app_id}.h5.xiaoeknow.com/v4/course/alive/{live_id}"
        current = service.capture_store.transition(
            current,
            "mini_program_source_bound",
            expected_source=canonical_xiaoetong_source(page_url),
            native_media_lineage=lineage,
        )
        bound = service.capture_store.bind_source_candidate(
            current, candidates, candidate_id=candidate_id,
        )
        if bound is None:
            raise EnrichmentError("native capture could not bind its candidate")
        return bound

    def prepare_human_playback(self, identity: str, capture_job_id: str) -> dict[str, Any]:
        service = self._service(identity)
        capture = service.capture_store.latest(capture_job_id)
        if not capture or not (capture.get("expected_source") and capture.get("candidate")):
            return self.prepare_playback(identity, capture_job_id)
        # A crash after exact binding may precede the manifest write. Resume the
        # original armed capture without clearing or replacing its accepted source.
        resumed = service.start()
        if resumed.get("capture_job_id") != capture_job_id:
            raise EnrichmentError("human playback resumed a different capture")
        return resumed

    def observe_human_playback(self, identity: str, capture_job_id: str, *,
                               observed_after: datetime,
                               expected_source: str = "") -> dict[str, Any]:
        """Select only a unique fresh merchant source; the existing binder proves media."""
        service = self._service(identity)
        sources: dict[str, list[dict[str, Any]]] = {}
        for row in service.sniffer.candidates():
            try:
                captured = datetime.fromisoformat(str(row.get("captured") or ""))
                if captured.tzinfo is None:
                    captured = captured.replace(tzinfo=BEIJING)
                if captured <= observed_after:
                    continue
            except ValueError:
                continue
            if row.get("media_type") != "m3u8" or not str(row.get("live_id") or "").startswith("l_"):
                continue
            media = urlsplit(str(row.get("url") or ""))
            if (media.scheme != "https" or not (
                Path(media.path).name == "playlist_eof.m3u8"
                or media.hostname == "live-ex-speed.xiaoeknow.com"
                or re.fullmatch(r"playlist(?:\.f[0-9]+)?\.m3u8", Path(media.path).name)
            )):
                continue
            origin = urlsplit(str(row.get("source_url") or ""))
            merchant = re.fullmatch(
                r"(?P<app>app[A-Za-z0-9]+)\.(?:h5|mp)\.(?:xiaoeknow\.com|xe-live\.com)",
                origin.hostname or "",
            )
            app = merchant.group("app") if merchant else (
                "appsnm3rlcp3566" if origin.hostname == "xet.kj1team.cn"
                and origin.path == "/_alive/v2/get_lookback_url" else ""
            )
            if not app or (not expected_source and app != "appsnm3rlcp3566"):
                continue
            source = f"xiaoetong:{app}:{row['live_id']}"
            if expected_source and source != expected_source:
                continue
            sources.setdefault(source, []).append(row)
        if len(sources) != 1:
            return {"observed": False, "reason": "ambiguous_sources" if sources else "media_pending"}
        source, candidates = next(iter(sources.items()))
        candidate = max(candidates, key=lambda row: (str(row.get("captured") or ""), str(row.get("id") or "")))
        if not expected_source:
            return {"observed": False, "reason": "source_confirmation_required",
                    "source_identity": source, "candidate_id": str(candidate.get("id") or ""),
                    "live_id": str(candidate["live_id"])}
        try:
            self.bind_mini_program_capture(identity, capture_job_id,
                source_identity=source, candidate_id=str(candidate.get("id") or ""),
                observed_after=observed_after)
        except EnrichmentError as exc:
            if any(value in str(exc) for value in (
                "unavailable", "lacks", "has not ended", "not a finite", "candidate is missing",
            )):
                return {"observed": False, "reason": "finite_media_not_yet_verified"}
            raise
        return {"observed": True, "source_identity": source,
                "candidate_id": str(candidate["id"]), "live_id": str(candidate["live_id"])}

    def refresh_failed_native_capture(
        self, identity: str, capture_job_id: str, *, candidate_id: str,
    ) -> dict[str, Any]:
        """Renew only the same media after a zero-byte, durably held failure."""
        service = self._service(identity)
        current = service.capture_store.latest(capture_job_id)
        if current is None or current.get("status") != "download_retry_claimed":
            raise EnrichmentError("native download repair is not durably held")
        source_identity = (current.get("expected_source") or {}).get("source_identity", "")
        match = _XIAOETONG_SOURCE_IDENTITY.fullmatch(source_identity)
        old_lineage = current.get("native_media_lineage") or {}
        if match is None or not old_lineage.get("media_resource_sha256"):
            raise EnrichmentError("native download repair lacks original media identity")
        old_candidate = current.get("candidate") or {}
        task = next((row for row in service.sniffer.tasks()
                     if row.get("id") == current.get("download_task_id")), None)
        labels = (((task or {}).get("meta") or {}).get("req") or {}).get("labels") or {}
        # Unfinished persisted tasks are restored as paused, even when the last
        # in-memory failure was not saved. Require the exact backend-repair task.
        restored_repair_pause = bool(
            task and task.get("status") == "pause"
            and current.get("repair_task_id") == task.get("id")
            and re.fullmatch(
                r"[0-9a-f]{64}", str(current.get("repaired_binary_sha256") or ""),
            )
        )
        if (
            task is None or not (task.get("status") == "error" or restored_repair_pause)
            or int((task.get("progress") or {}).get("downloaded") or 0) != 0
            or labels.get("capture_id") != old_candidate.get("id")
            or labels.get("live_id") != match.group("live_id")
        ):
            raise EnrichmentError("native download failure is uncertain")
        observations = service.sniffer.candidates()
        matches = [row for row in observations if row.get("id") == candidate_id
                   and row.get("live_id") == match.group("live_id")]
        if len(matches) != 1 or matches[0].get("media_type") != "m3u8":
            raise EnrichmentError("native repair candidate is missing or ambiguous")
        candidate = matches[0]
        try:
            armed_at = datetime.fromisoformat(current["native_repair_armed_at"])
            captured_at = datetime.fromisoformat(candidate["captured"])
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=BEIJING)
        except (KeyError, ValueError, TypeError) as exc:
            raise EnrichmentError("native repair timestamp is invalid") from exc
        if captured_at <= armed_at:
            raise EnrichmentError("native repair candidate predates the repair arm")
        lineage_armed_at = armed_at
        if old_lineage.get("metadata_anchors"):
            # A native client may cache course metadata while requesting a fresh
            # signed manifest. Revalidate the previously bound identity anchor,
            # not its credentials; ticket freshness still uses the repair arm.
            try:
                original_arm = datetime.fromisoformat(current["created_at"])
                previous_capture = datetime.fromisoformat(old_candidate["captured"])
                if previous_capture.tzinfo is None:
                    previous_capture = previous_capture.replace(tzinfo=BEIJING)
                if original_arm.tzinfo is None or not original_arm < previous_capture < armed_at:
                    raise ValueError("invalid prior capture interval")
            except (KeyError, ValueError, TypeError) as exc:
                raise EnrichmentError("native repair prior lineage timestamp is invalid") from exc
            prior_matches = [row for row in observations if row.get("id") == old_candidate.get("id")
                             and _safe_candidate(row) == old_candidate]
            if len(prior_matches) != 1:
                raise EnrichmentError("native repair prior observation changed")
            prior_lineage = _native_direct_media_lineage(
                prior_matches[0], observations, app_id=match.group("app_id"),
                live_id=match.group("live_id"), armed_at=original_arm,
                captured_at=previous_capture,
                debug_root=(service.sniffer_binary.parent / "elive_live_debug") if hasattr(service, "sniffer_binary") else None,
            )
            if prior_lineage != old_lineage:
                raise EnrichmentError("native repair prior merchant lineage changed")
            lineage_armed_at = original_arm
        lineage = _native_direct_media_lineage(
            candidate, observations, app_id=match.group("app_id"),
            live_id=match.group("live_id"), armed_at=lineage_armed_at, captured_at=captured_at,
            debug_root=(service.sniffer_binary.parent / "elive_live_debug") if hasattr(service, "sniffer_binary") else None,
        )
        if lineage["media_resource_sha256"] != old_lineage["media_resource_sha256"]:
            raise EnrichmentError("native repair changed the bound media resource")
        return service.capture_store.transition(
            current, "native_media_ticket_renewed", status="download_failed",
            previous_candidate_id=old_candidate["id"], candidate=_safe_candidate(candidate),
            native_media_lineage=lineage,
        )

    def advance_capture(
        self,
        identity: str,
        capture_job_id: str,
    ) -> dict[str, Any]:
        """Reconcile the exact source job before requesting another UI action."""

        service = self._service(identity)
        capture = service.capture_store.latest(capture_job_id)
        if capture is None or capture.get("status") != "downloaded":
            service.start()
        if capture and capture.get("status") == "awaiting_capture" and (
            capture.get("native_repair_armed_at") or not capture.get("expected_source")
        ):
            # An unbound native lease must come through the reviewed observation
            # and exact lineage binder, never historical/global live-id detection.
            return {"status": "awaiting_capture", "capture_job_id": capture_job_id}
        try:
            return service.advance_capture(
                capture_job_id,
            )
        except InvalidSourcePage as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao live source identity is invalid",
                category="contract_error",
                code="xiaocao_live_source_identity_invalid",
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
        capture = service.capture_store.latest(capture_job_id) or {}
        media_sha = None
        if capture.get("media_repair"):
            if capture.get("status") != "downloaded":
                return None
            media_sha = service.validate_media(capture_job_id)["media_sha256"]
        return next((event for event in reversed(service.events())
            if event.get("event") == "cloud_handoff_published"
            and event.get("capture_job_id") == capture_job_id
            and (media_sha is None or event.get("media_sha256") == media_sha)), None)

    def validate_handoff_media(self, identity: str, capture_job_id: str, capsule: dict[str, Any]) -> None:
        """Revalidate local bytes before the first external mailbox effect."""
        media = self._service(identity).validate_media(capture_job_id)
        for field in ("capture_job_id", "media_sha256", "media_size_bytes", "media_duration_seconds"):
            if media.get(field) != capsule.get(field):
                raise EnrichmentError("Xiaocao handoff media no longer matches its capsule")

class XiaocaoWechatLiveSubscription:
    """Exactly-once WeChat discovery and capture state machine.

    The browser/H5 route is identity-resolution-only. Playback and media
    evidence are always owned by the native WeChat mini-program and sniffer.
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
        playback_route: str = XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
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
        if self.playback_route != XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM:
            raise ValueError(
                "Xiaocao web playback is sunset; use the WeChat mini-program route"
            )
        self.clock = clock or (lambda: datetime.now(BEIJING))

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            raise EnrichmentError("Xiaocao WeChat clock needs a timezone")
        return value.astimezone(BEIJING).isoformat(timespec="seconds")

    def _load(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            value = {"schema_version": 1, "items": {}}
            self._manifest_baseline = deepcopy(value)
            return value
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("Xiaocao WeChat manifest is invalid") from exc
        if value.get("schema_version") != 1 or not isinstance(
            value.get("items"), dict
        ):
            raise EnrichmentError("Xiaocao WeChat manifest is invalid")
        self._manifest_baseline = deepcopy(value)
        return value

    def _save(self, manifest: dict[str, Any]) -> None:
        # Native/browser waits may outlive another item's transition. Atomic
        # rename alone prevents torn JSON, not a stale whole-manifest overwrite.
        baseline = getattr(self, "_manifest_baseline", {"schema_version": 1, "items": {}})
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with (self.output_dir / "manifest.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self._load()
            merged = deepcopy(current)
            for identity, incoming in manifest["items"].items():
                original = baseline["items"].get(identity)
                if incoming == original:
                    continue
                durable = current["items"].get(identity)
                if durable != original and durable != incoming:
                    raise EnrichmentError("Xiaocao WeChat item changed during continuation")
                merged["items"][identity] = deepcopy(incoming)
            for key, value in manifest.items():
                if key not in {"items", "updated_at"} and value != baseline.get(key):
                    merged[key] = deepcopy(value)
            merged["updated_at"] = self._now()
            _atomic_json(self.manifest_path, merged)
            manifest.clear()
            manifest.update(merged)
            self._manifest_baseline = deepcopy(merged)

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

    def discover(self) -> dict[str, Any]:
        """Persist original-message inventory without activating any capture."""
        manifest = self._load()
        previous = set(manifest["items"])
        self._poll(manifest)
        expired = self.expire_stale_waits(manifest)
        pending = sorted(
            (item for item in manifest["items"].values()
             if item.get("status") not in _TERMINAL),
            key=lambda item: (item["published_at"], item["identity"]),
            reverse=True,
        )
        result = {
            "status": "scanned",
            "scanned_at": self._now(),
            "discovered_count": len(set(manifest["items"]) - previous),
            "expired_count": len(expired),
            "pending_items": [
                {key: item[key] for key in (
                    "identity", "published_at", "status", "capture_job_id",
                ) if key in item}
                for item in pending
            ],
        }
        manifest["last_discovery"] = result
        self._save(manifest)
        return result

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

    def expire_stale_waits(
        self, manifest: dict[str, Any], *, skip_identity: str | None = None,
    ) -> list[str]:
        """Drop ungenerated entries after 72 hours without touching media work."""
        cutoff = datetime.fromisoformat(self._now()) - timedelta(hours=72)
        expired = []
        for item in list(manifest["items"].values()):
            if item["identity"] == skip_identity:
                continue
            if item.get("status") not in {
                "discovered", "page_resolved", "capture_armed", "awaiting_playback",
            }:
                continue
            published = datetime.fromisoformat(item["published_at"])
            if published.tzinfo is None or published > cutoff:
                continue
            if any(item.get(key) for key in (
                "candidate_id", "task_id", "media_request_observed", "handoff_id",
            )):
                continue
            job = item.get("capture_job_id")
            if job:
                check = getattr(self.capture_driver, "can_expire_wait", None)
                if check is None or not check(item["identity"], job):
                    continue
            self._transition(
                manifest, item, "expired",
                expiration_reason="no_media_after_72_hours",
                expired_at=self._now(),
            )
            expired.append(item["identity"])
        return expired

    def exclude_expired_backfill(self, identity: str, *, user_skip_authorized: bool) -> dict[str, Any]:
        """Preserve an expired unbound original while recording a human skip."""
        if not user_skip_authorized:
            raise EnrichmentError("backfill exclusion requires a direct user instruction")
        manifest = self._load()
        item = manifest["items"].get(identity)
        if not isinstance(item, dict) or item.get("status") != "expired":
            raise EnrichmentError("only an expired original can be excluded here")
        if any(item.get(key) for key in (
            "candidate_id", "task_id", "media_request_observed", "handoff_id", "source_identity",
        )):
            raise EnrichmentError("backfill exclusion must reconcile existing bound claims")
        job = item.get("capture_job_id")
        if job:
            check = getattr(self.capture_driver, "can_expire_wait", None)
            if not callable(check) or check(identity, job) is not True:
                raise EnrichmentError("backfill exclusion lacks an exact unbound capture")
        if item.get("manual_backfill_excluded") is True:
            return item
        return self._transition(manifest, item, "expired", manual_backfill_excluded=True,
            manual_backfill_excluded_at=self._now(), manual_backfill_exclusion_reason="direct_user_skip")

    def _prepare_manual_backfill(
        self, manifest: dict[str, Any], identity: str | None, since: str,
    ) -> None:
        """One invocation's dated authorization; never change routine expiry."""
        if not identity or re.fullmatch(r"\d{4}-\d{2}-\d{2}", since) is None:
            raise EnrichmentError("manual backfill requires an exact identity and date")
        try:
            cutoff = datetime.fromisoformat(since).replace(tzinfo=BEIJING)
        except ValueError as exc:
            raise EnrichmentError("manual backfill date is invalid") from exc
        now = datetime.fromisoformat(self._now())
        if cutoff > now:
            raise EnrichmentError("manual backfill date is in the future")
        item = manifest["items"].get(identity)
        if item and item.get("manual_backfill_excluded") is True:
            raise EnrichmentError("original entry is explicitly excluded from backfill")
        if (
            item and item.get("manual_backfill_since") == since
            and item.get("status") not in {"expired", "superseded", "historical_baseline"}
        ):
            # Active continuations retain evidence. A later routine sweep may
            # retire an idle backfill again; renewed explicit authorization must
            # revalidate its original message and reconcile the same capture.
            return
        payload = self.history_reader()
        if str(payload.get("chat") or "") != self.contact:
            raise EnrichmentError("WeChat history resolved another contact")
        matches = [
            row for row in parse_xiaocao_live_messages(payload)
            if row["identity"] == identity
            and cutoff <= datetime.fromisoformat(row["published_at"]) <= now
        ]
        if len(matches) != 1:
            raise EnrichmentError("manual backfill original entry is missing or out of range")
        original = matches[0]
        if item:
            for key, value in original.items():
                if key in item and item[key] != value:
                    raise EnrichmentError("manual backfill original evidence changed")
            item = dict(item)
        else:
            item = {**original, "status": "discovered"}
        previous = item["status"]
        if previous in {"expired", "superseded", "historical_baseline"}:
            if any(item.get(key) for key in (
                "candidate_id", "task_id", "media_request_observed", "handoff_id",
                "source_identity",
            )):
                raise EnrichmentError("manual backfill must reconcile existing bound claims")
            job = item.get("capture_job_id")
            check = getattr(self.capture_driver, "can_expire_wait", None)
            repair = getattr(self.capture_driver, "can_resume_unbound_native_repair", None)
            if job and not (
                (check is not None and check(identity, job))
                or (repair is not None and repair(identity, job))
            ):
                raise EnrichmentError("manual backfill cannot replace an existing capture")
            item["status"] = "capture_armed" if job else "discovered"
        if item["status"] in _TERMINAL:
            return
        self._transition(
            manifest, item, item["status"], manual_backfill_since=since,
            manual_backfill_requested_at=self._now(),
            manual_backfill_previous_status=previous,
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
            raise EnrichmentError(
                "launch resolver did not resolve a Xiaoetong live page"
            ) from exc
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

    def _exchange_browser(self, request: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.browser_exchange(request)
        except NativePlaybackInputTimeout as exc:
            # Keep the original manifest bindings; never create or reset a claim.
            exc.waiting_items = [{**item, "stage": exc.diagnostic_stage}]
            raise

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
        wait_code = {
            "awaiting_playback": "awaiting_playback",
            "downloading": "compressed_capture_pending",
            "upload_claimed": "upload_pending",
            "cloud_handoff": "cloud_handoff_pending",
        }.get(status, "capture_progress_pending")
        waiting_item.update({
            "category": "provider_wait",
            "code": wait_code,
        })
        observation = state.get("upload_observation")
        if isinstance(observation, dict) and stage == "cloud_handoff":
            waiting_item["upload_observation"] = observation
            if observation.get("state") in {"failed", "paused"}:
                waiting_item.update(category="transport_error",
                    code="upload_transfer_" + observation["state"],
                    diagnosis_required=True, diagnosis_owner="agent")
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
        if item.get("human_playback_started_at") and item.get("activated") is not True:
            waiting_item.update(
                status="awaiting_human_playback", stage="human_playback",
                code="human_playback_pending", operator="human",
                next_poll_not_before=item["human_playback_next_poll_at"],
                human_playback_poll_attempt=item.get("human_playback_poll_attempt", 0),
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
        self.capture_driver.validate_handoff_media(item["identity"], item["capture_job_id"], capsule)
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

    def bind_media_revision(self, identity: str, capture_job_id: str, *,
                            mailbox_ledger: Any) -> dict[str, Any]:
        """Reopen only an explicitly prepared, unpublished same-item repair."""
        manifest = self._load()
        item = manifest["items"].get(identity)
        if not isinstance(item, dict) or item.get("capture_job_id") != capture_job_id:
            raise EnrichmentError("media revision subscription binding changed")
        service = self.capture_driver._service(identity)
        capture = service.capture_store.latest(capture_job_id) or {}
        repair = capture.get("media_repair") or {}
        state = mailbox_ledger.handoff_state(str(repair.get("previous_handoff_id") or "")) or {}
        if (not repair.get("backend_receipt") or state.get("event") != "mailbox_send_rejected"
            or item.get("status") == "completed"):
            raise EnrichmentError("media revision subscription lacks unpublished repair proof")
        if item.get("media_repair_revision") == repair.get("revision"):
            return item
        if item.get("status") != "handoff_ready":
            raise EnrichmentError("media revision requires the original ready handoff")
        old = self._load_handoff(item)
        if old.get("handoff_id") != repair.get("previous_handoff_id") or old.get("media_sha256") != repair.get("previous_media_sha256"):
            raise EnrichmentError("media revision changed the original handoff")
        return self._transition(manifest, item, "playback_activated",
            media_repair_revision=repair["revision"], previous_handoff_path=item["handoff_path"],
            handoff_path=None)

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
        return self._check_mini_program_playback(
            manifest,
            item,
            reason=reason,
        )

    def _check_mini_program_playback(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any]:
        """Use native WeChat playback while keeping an H5 identity anchor.

        The mini-program is the user-visible playback surface.  The local
        ``wx_channels_download`` sniffer observes its requests and the source
        job later proves the same ``live_id`` before creating a download task.
        No signed media URL is accepted from this structured input.
        """
        from .human_playback import human_playback_enabled
        if human_playback_enabled(self.output_dir.parent / "native_share_bridge.json"):
            return self._check_human_playback(manifest, item, reason=reason)
        if item.get("human_playback_started_at"):
            raise EnrichmentError("human playback ownership changed; preserve the original wait")
        from .native_entry import require_native_entry
        require_native_entry(self.output_dir.parent / "native_share_bridge.json")
        expected_source_identity = str(item.get("source_identity") or "")
        expected_live_id = (
            expected_source_identity.rsplit(":", 1)[-1]
            if expected_source_identity
            else ""
        )
        native_entry = item.get("entry_kind") == "wechat_mini_program"
        course_app = str(item.get("mini_program_name") or "鹅直播")
        request = {
            "event": "daily_browser_input_required",
            "adapter": "xiaocao_wechat_live",
            "action": "activate_xiaoetong_mini_program",
            "subscription_id": item["identity"],
            "check_reason": reason,
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "operator": "agent",
            "user_action_required": False,
            "action_trace_policy": {
                "exporter": "scripts/kol_native_action_trace.py",
                "identity": item["identity"],
                "capture_job_id": item["capture_job_id"],
                "exact_current_thread_rollout_required": True,
                "run_start_boundary_required": True,
                "separate_input_and_readback_calls": True,
                "export_before_next_input": True,
                "marker_prefix": "KOL_ACTION:",
                "image_storage": "hash_only",
                "causal_attribution": "unproven_from_timing_alone",
                "diagnostic_auth_baseline": "explicit_user_authorized_after_browser_before_pac_launch",
            },
            "ui_policy": {
                "app_bundle_id": "com.tencent.xinWeChat",
                "surface": "visible_foreground_ui",
                "action_mode": "one_action_then_state_readback",
                "max_activation_attempts": 1,
                "playback_cleanup": "close_course_window",
                "window_close_readback_required": True,
                "coordinate_policy": "fresh_screenshot_visible_control_only_when_ax_absent",
            },
            "password_policy": {
                "only_if_password_gate_visible": True,
                "password": self.password,
            },
            "consent_policy": {
                "non_binding_privacy_notice": "agent_handle_visible_controls",
                "service_agreement": "confirmation_at_action_time",
                "sensitive_permissions": "confirmation_at_action_time",
                "readback_after_each_action": True,
                "blocked_page_state": "mini_program_consent_required",
            },
            "instructions": (
                "保留原始联系人、发布时间、应用名和分享码；先读 Skill 的"
                "references/native-share-bridge.md，复用已配置草料活码。"
                "先只用 Browser 核验编辑器和已保存分享码；不要为网页核验读取微信、"
                "截图或点击窗口菜单/草料窗口。目标已匹配时不编辑、不保存。"
                "草料网页编辑优先用 Browser 已绑定的精确编辑器标签页，不用原生"
                "Computer Use 操作网页；每次操作前核验当前编辑器 URL 和码 ID，"
                "保存后重开编辑器组件读回原分享目标，再取得一次新鲜提供方入口。"
                "浏览器核验完成后检查同一抓取服务/PAC。既有来源不明的品牌允许弹窗，"
                "先按桥接R0一次取消并读回桥页，不点允许、不换原任务；再签发并唤起一次；"
                "此后才读取微信并执行必要的 B0–B4。仅本任务已有精确课程读回时复用。"
                "明确策略拒绝不得换工具绕过。微信原生窗口按 B0–B4 操作。"
                "B1/B2 跳转未确认时，禁止追加窗口菜单探测或选择窗口；只做一次"
                "当前状态读回并继续离线诊断。仅已核验课程的关闭验收使用窗口菜单。"
                "安全重登录提示是结果，不得把最后一次菜单/截图动作标成触发原因。"
                "出现安全重登录后停止本轮原生输入、恢复本轮代理并保留原任务；"
                "人类确认恢复登录后，可按已有抓取授权续原任务及已验证入口，"
                "不以查明保护根因或更换路线为前提；登录未恢复时不自动重试。"
                "每轮重新核验保存目标、同capture就绪和当前画面，保留新鲜入口及动作日志；"
                "不复用已消耗票据、不重复未知下载/上传，也不绕过明确策略拒绝。"
                "已有精确课程窗口则复用。"
                if native_entry and course_app == "见势擒龙团"
                else
                "用 wechat-cli 已定位的原始联系人和发布时间，在本机微信中只打开"
                f"该条原始 #小程序://{course_app}/ 消息一次；不要复制发送消息、猜测 URL "
                "Scheme，或反复拉起小程序。"
                if native_entry
                else
                "仅执行已验证、商户签发的 launch_command 一次，打开 source_url 对应"
                "的同一场小鹅通小程序；不要打开或依赖浏览器 H5 播放页。"
            ) + (
                "到达精确课程小程序后，禁止再次解析、重新生成跳转票据、重开 Scheme或刷新。"
                "优先辅助功能控件；小程序只暴露窗口、没有控件时，允许基于刚读取截图"
                "点击明确可见的按钮/输入框，不复制历史坐标。普通非约束性隐私提示由 Agent"
                "处理；服务协议或敏感授权须获得当次确认后，按 Skill C1–C3 勾选、读回、"
                "同意、读回并继续同一任务。需确认时返回 mini_program_consent_required，"
                "不得误报微信手机登录。若看见课程口令门，打开"
                "输入框，输入提供的口令、读回并确认。口令通过可能自动播放；画面一旦"
                f"开始播放并被抓取后，关闭这一个{course_app}课程窗口；按 Skill 的"
                "当前应用关闭规则操作，读回窗口菜单已无该应用。新版品牌按桥接"
                "B4a–B4c 优先用当前课程的语义文件菜单关闭并独立核验；"
                "输入拒绝按桥接窗口恢复分支诊断，不重复失败点击，"
                "不以菜单调用返回或另一场成功替代当前窗口消失读回。"
                "若未自动起播，只点击一次可见播放按钮。"
                "未开播、直播中或回放生成中：按当前应用关闭规则处理并读回，不下载暖场或直播流；"
                "只有直播结束且完整回放生成才可下载。"
                "不按空格、不静音、不退出微信。关闭播放器不等于下载完成，仍需验证"
                "同一下载任务的媒体文件。确认本机"
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
                    "mac_locked_manual_unlock_required|wechat_client_login_required|mini_program_consent_required|waiting_to_start|live|"
                    "replay_generating|playable|password_required|unknown|"
                    "mini_program_media_observed|mini_program_waiting|"
                    "password_input_incomplete|native_bridge_policy_denied|"
                    "native_bridge_target_unverified|native_window_input_unavailable"
                ),
                "activated": "boolean",
                "media_request_observed": "boolean",
                "password_used": "boolean",
                "playback_window_closed": (
                    "boolean; true only after exact course window closure readback"
                ),
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
            if course_app == "见势擒龙团":
                request["native_entry_reference"] = (
                    ".codex/skills/kol-intelligence/references/native-share-bridge.md"
                )
                request["native_bridge_config_path"] = str(
                    _NATIVE_SHARE_BRIDGE_CONFIG
                )
                request["native_bridge_editor_policy"] = {
                    "surface": "browser_dom",
                    "preferred_transport": "bound_browser_tab",
                    "session": "caoliao",
                    "explicit_tab_required": True,
                    "native_computer_use_allowed": False,
                    "require_current_editor_url": True,
                    "require_bound_tab_locators": True,
                    "opencli_fallback": "only_after_exact_url_readback",
                    "saved_target_readback": "reopened_editor_component",
                    "on_explicit_policy_denial": "stop_denied_action_no_tool_bypass",
                }
                if reason != "captured_window_cleanup":
                    request["native_atomic_policy"] = {
                        "action": "open_course_then_allow",
                        "preparer": "scripts/kol_prepare_native_atomic.py",
                        "runtime": "scripts/kol_native_course_runtime.mjs",
                        "surface": "single_cua_repl_call",
                        "marker": "OPEN_ALLOW_ATOMIC",
                        "max_b1_inputs": 1, "max_b2_inputs": 1,
                        "claim_scope": "original_capture_and_provider_entry",
                        "audit": "durable_hash_only_subevents_before_next_input",
                        "media_acceptance": False,
                    }
                    request["action_trace_policy"]["atomic_exception"] = "reviewed_B1_B2_subevents_in_one_source_call"
                    request["instructions"] += (
                        "打开→允许使用native_atomic_policy的受审查脚本，在一个cua_repl调用内"
                        "完成新鲜截图识别、B1、精确品牌读回、同capture PAC检查、B2和品牌读回。"
                        "这两步改用单次真实源调用绑定的逐子步骤持久化哈希日志，不在中间返回模型"
                        "准备命令或导出；宏返回后导出源调用。其他口令/同意/关闭步骤仍按原表。"
                        "宏不签发入口、不创建任务、不接受媒体；未知或拒绝停止，不重复派发。"
                    )
                    request["window_input_recovery_policy"] = {
                        "subscription_id": item["identity"],
                        "capture_job_id": item["capture_job_id"],
                        "input_lookup_errors": ["noWindowsAvailable", "windowNotFoundAtPosition"],
                        "fullscreen_cause_requires_current_evidence": True,
                        "surface": "reviewed_cua_only",
                        "stale_confirmation_reset": {
                            "preparer": "scripts/kol_prepare_native_atomic.py --prepare-stale-reset",
                            "runtime": "scripts/kol_native_course_runtime.mjs",
                            "requires_verified_browser_target": True,
                            "requires_unbound_original_capture": True,
                            "requires_pac_off": True,
                            "max_cancel_inputs": 1,
                            "allow_input_permitted": False,
                            "readback_before_fresh_entry": True,
                        },
                        "bridge_reconstruction": {
                            "max_attempts": 1,
                            "requires_fresh_visible_caoliao_bridge": True,
                            "requires_current_space_input_failure_evidence": True,
                            "error_code_alone_satisfies_preconditions": False,
                            "requires_no_course_or_bound_media_download_upload": True,
                            "close_and_verify_bridge_absence_first": True,
                            "reopen_saved_target_before_fresh_entry": True,
                            "reuse_same_sniffer_and_capture": True,
                        },
                        "on_policy_denial": "no_tool_or_surface_bypass",
                        "on_security_relogin": "stop_native_inputs",
                    }
                    request["ui_policy"].update({
                        "unconfirmed_brand_navigation_window_menu_probe_allowed": False,
                        "security_relogin_retry_policy": "human_login_then_authorized_same_item_continuation",
                        "security_relogin_root_cause_required": False,
                        "security_relogin_unattended_retry": False,
                        "security_relogin_attribution": "observation_is_not_trigger_proof",
                    })
                    request["native_bridge_editor_policy"].update({
                        "native_ui_before_editor_readback_allowed": False,
                        "workflow_order": [
                            "browser_saved_target_readback",
                            "same_capture_sniffer_pac_readback",
                            "fresh_provider_launch_once_or_verified_course_reuse",
                            "native_activation_readback",
                        ],
                    })
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
        if item.get("mini_program_name") == "见势擒龙团" and not native_entry:
            request["mini_program_name"] = "见势擒龙团"
            request["instructions"] = (
                "保留见势擒龙团应用身份；当前已有匹配课程窗口则复用。"
                "没有窗口时使用当前商户页校验返回的品牌应用入口，不换成鹅直播。"
            ) + request["instructions"]
        if reason == "captured_window_cleanup":
            request.pop("launch_resolver_command", None)
            request["instructions"] = (
                f"同一 capture 的有限媒体已捕获。仅核对本任务{course_app}课程窗口已关闭；"
                f"若仍存在，按 Skill 当前应用关闭规则处理并读回窗口列表无{course_app}；"
                "新版品牌按桥接 B4a–B4c 优先语义文件菜单关闭并独立核验；"
                "输入拒绝按桥接窗口恢复分支诊断，不重复失败点击，"
                "不沿用另一场成功回执。"
                "已有本任务关闭读回则直接返回真实回执，不重复操作。不要唤起、重新播放、"
                "输入口令或恢复 sniffer。返回 playback_window_closed 和原身份绑定。"
            )
        else:
            self.capture_driver.prepare_playback(item["identity"], item["capture_job_id"])
        response = self._exchange_browser(request, item)
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
        if page_state in {
            "mac_locked_manual_unlock_required", "wechat_client_login_required",
            "mini_program_consent_required",
        }:
            self._transition(
                manifest, item, "awaiting_playback",
                observed_page_state=page_state,
                playback_surface=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
                activated=False,
                media_request_observed=response.get("media_request_observed") is True,
                playback_window_closed=response.get("playback_window_closed") is True,
                user_action_required=True,
            )
        if page_state == "mac_locked_manual_unlock_required":
            raise EnrichmentDiagnosticError(
                "Mac is locked and requires manual unlock",
                category="authentication_error",
                code="mac_locked_manual_unlock_required",
                stage="local_machine_unlock",
            )
        if page_state == "wechat_client_login_required":
            raise EnrichmentDiagnosticError(
                "WeChat client login is required",
                category="authentication_error",
                code="wechat_client_login_required",
                stage="wechat_client_authorization",
            )
        if page_state == "mini_program_consent_required":
            raise EnrichmentDiagnosticError(
                "native mini-program consent requires current user confirmation",
                category="authentication_error",
                code="mini_program_consent_required",
                stage="mini_program_consent",
            )
        media_request_observed = response.get("media_request_observed") is True
        unobserved_local_failure = (
            page_state in _NATIVE_PLAYBACK_REPAIR_CODES
            and response.get("activated") is not True
            and not media_request_observed
            and not observed_source_identity
            and not observed_live_id
        )
        if (
            (expected_live_id or media_request_observed)
            and not source_bound
            and not unobserved_local_failure
        ):
            raise EnrichmentError(
                "WeChat mini-program playback binding is invalid"
            )
        # Warm-up/live requests are not a completed replay, even when the
        # native window opened successfully. Preserve that evidence without
        # advancing the download. The Agent closes the waiting course window.
        replay_ready = page_state in {"mini_program_media_observed", "playable"}
        activated = (
            response.get("activated") is True
            and media_request_observed
            and replay_ready
        )
        if activated and response.get("playback_window_closed") is not True:
            item = self._transition(
                manifest, item, "awaiting_playback",
                observed_page_state=page_state,
                playback_surface=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
                activated=False,
                media_request_observed=True,
                playback_window_closed=False,
                user_action_required=False,
                source_identity=observed_source_identity,
                source_resource_id=observed_live_id,
            )
            error = EnrichmentDiagnosticError(
                "native course window closure has not been verified",
                category="input_error",
                code="native_playback_window_close_unverified",
                stage="native_playback_window_close",
            )
            error.waiting_items = [{**item, "stage": "native_playback_window_close"}]
            raise error
        if native_entry and activated and reason != "captured_window_cleanup":
            self.capture_driver.bind_mini_program_capture(
                item["identity"],
                item["capture_job_id"],
                source_identity=observed_source_identity,
                candidate_id=str(response.get("candidate_id") or ""),
            )
        fields: dict[str, Any] = {
            "observed_page_state": page_state,
            "activated": activated,
            "password_used": response.get("password_used") is True,
            "playback_route": self.playback_route,
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "media_request_observed": media_request_observed,
            "playback_window_closed": response.get("playback_window_closed") is True,
        }
        # This fresh non-authentication observation replaces an older login
        # blocker; it must not inherit user ownership from a previous attempt.
        fields["user_action_required"] = False
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
        item = self._transition(
            manifest,
            item,
            "playback_activated" if activated else "awaiting_playback",
            **fields,
        )
        if not activated and page_state not in {
            "waiting_to_start", "live", "replay_generating",
            "source_temporarily_unavailable",
        }:
            error = EnrichmentDiagnosticError(
                "native activation is unresolved; repair the same capture",
                category="input_error",
                code=_NATIVE_PLAYBACK_REPAIR_CODES.get(
                    page_state, "native_playback_activation_unverified",
                ),
                stage="native_playback_input",
            )
            error.waiting_items = [{**item, "stage": "native_playback_input"}]
            raise error
        return item

    def _check_human_playback(self, manifest: dict, item: dict, *, reason: str) -> dict:
        from .human_playback import (
            enable_capture_listener_pac, launch_verified_caoliao,
            next_human_poll, notify_human_once,
        )
        from xiaocao.yangsheng.capture import lifecycle_lease
        # Closure is human-owned. Never claim it was verified or invoke native UI.
        if reason == "captured_window_cleanup" or item.get("activated") is True:
            return item
        if item.get("mini_program_name") != "见势擒龙团":
            raise EnrichmentError("human Caoliao playback requires the original branded entry")
        now = self.clock()
        due = item.get("human_playback_next_poll_at")
        if due and now < datetime.fromisoformat(due):
            return item
        if not item.get("human_playback_started_at"):
            with lifecycle_lease():
                self.capture_driver.prepare_human_playback(item["identity"], item["capture_job_id"])
                enable_capture_listener_pac()
                nonce = item.get("human_playback_nonce") or uuid4().hex
                item = self._transition(manifest, item, item["status"], human_playback_nonce=nonce)
                folder = self.output_dir / "items" / item["identity"]
                folder.mkdir(parents=True, exist_ok=True)
                receipt = folder / f"human-entry-{nonce}.json"
                if receipt.exists():
                    launched = json.loads(receipt.read_text())
                    if (launched.get("entry_launched") is not True
                        or launched.get("identity") != item["identity"]
                        or launched.get("capture_job_id") != item["capture_job_id"]):
                        raise EnrichmentError("human entry outcome unresolved; do not relaunch")
                else:
                    request = {
                        "event": "daily_browser_input_required", "adapter": "xiaocao_wechat_live",
                        "action": "prepare_xiaoetong_human_entry", "subscription_id": item["identity"],
                        "capture_job_id": item["capture_job_id"], "operator": "human",
                        "mini_program_name": item["mini_program_name"],
                        "mini_program_token": item["mini_program_token"],
                        "native_bridge_config_path": str(self.output_dir.parent / "native_share_bridge.json"),
                        "instructions": (
                            "仅用已绑定Browser核验原草料编辑器保存的当前小程序链接；不同则按原流程"
                            "更新保存并重开组件核验。把真实新鲜的核验JSON保存到本机，返回browser_proof_path。"
                            "不要读取/截图/绑定微信，不执行打开、允许、口令、协议、播放或关闭。"
                            "程序会在收到来源凭证后只唤起草料一次，之后由人类全程操作，后台仅轮询下载器。"
                        ),
                        "required_response": {"action": "prepare_xiaoetong_human_entry",
                            "subscription_id": item["identity"], "browser_proof_path": "absolute local JSON path"},
                    }
                    response = self._exchange_browser(request, item)
                    self._validate_browser_response(request, response)
                    launched = launch_verified_caoliao(
                        config_path=self.output_dir.parent / "native_share_bridge.json", item=item,
                        proof_path=Path(str(response.get("browser_proof_path") or "")),
                        receipt_path=receipt, now=self.clock())
                item = self._transition(manifest, item, "awaiting_playback",
                    human_playback_started_at=launched["armed_at"], human_playback_poll_attempt=0,
                    human_playback_next_poll_at=next_human_poll(self.clock(), 0).isoformat(),
                    human_playback_entry_receipt=str(receipt), playback_operator="human",
                    observed_page_state="human_playback_pending", activated=False,
                    playback_window_closed=False, playback_window_cleanup_owner="human",
                    user_action_required=False)
                notify_human_once(folder / f"human-notification-{nonce}.json", published_at=item["published_at"])
                return item
        from urllib.error import URLError
        try:
            with lifecycle_lease():
                self.capture_driver.prepare_human_playback(item["identity"], item["capture_job_id"])
                enable_capture_listener_pac()
                observation = self.capture_driver.observe_human_playback(
                    item["identity"], item["capture_job_id"],
                    observed_after=datetime.fromisoformat(item["human_playback_started_at"]),
                    expected_source=str(item.get("source_identity") or item.get("human_confirmed_source_identity") or ""))
        except (SnifferError, URLError):
            observation = {"observed": False, "reason": "listener_transport_pending"}
        except EnrichmentDiagnosticError as exc:
            if exc.diagnostic_category != "transport_error":
                raise
            observation = {"observed": False, "reason": "listener_transport_pending"}
        if (observation.get("reason") == "source_confirmation_required"
            and observation.get("candidate_id") != item.get("human_source_rejected_candidate")):
            # The share token is opaque. Fresh traffic alone cannot establish
            # which original publication it belongs to. Ask the human once for
            # this exact proposed binding; never synthesize a UI observation.
            request = {
                "event": "daily_browser_input_required", "adapter": "xiaocao_wechat_live",
                "action": "confirm_xiaoetong_human_source", "operator": "human",
                "subscription_id": item["identity"], "capture_job_id": item["capture_job_id"],
                "published_at": item["published_at"],
                "source_identity": observation["source_identity"], "candidate_id": observation["candidate_id"],
                "instructions": "必须向人类确认：刚才手动打开并播放的是否为本发布时间的原课程。"
                    "不得自动回答，不读取/点击/截图微信。仅在直接人类确认后返回 human_confirmed:true，"
                    "并原样返回本请求 action/subscription_id/capture_job_id/source_identity/candidate_id。",
            }
            with lifecycle_lease():
                response = self._exchange_browser(request, item)
            self._validate_browser_response(request, response)
            if any(response.get(key) != request[key] for key in ("capture_job_id", "source_identity", "candidate_id")):
                raise EnrichmentError("human source confirmation changed its exact binding")
            if response.get("human_confirmed") is True:
                item = self._transition(manifest, item, item["status"],
                    human_confirmed_source_identity=observation["source_identity"],
                    human_confirmed_candidate_id=observation["candidate_id"],
                    human_source_confirmed_at=self._now())
                observation = {"observed": False, "reason": "confirmed_source_pending"}
            else:
                item = self._transition(manifest, item, item["status"],
                    human_source_rejected_candidate=observation["candidate_id"])
        if observation.get("observed") is True:
            return self._transition(manifest, item, "playback_activated", activated=True,
                playback_operator="human", media_request_observed=True,
                observed_page_state="mini_program_media_observed",
                source_identity=observation["source_identity"], source_resource_id=observation["live_id"],
                candidate_id=observation["candidate_id"], playback_window_closed=False,
                playback_window_cleanup_owner="human", user_action_required=False)
        attempt = int(item.get("human_playback_poll_attempt", 0)) + 1
        return self._transition(manifest, item, "awaiting_playback",
            human_playback_poll_attempt=attempt,
            human_playback_next_poll_at=next_human_poll(self.clock(), attempt).isoformat(),
            human_playback_observation=observation.get("reason", "media_pending"))

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
                "Resolve only the stable Xiaoetong live identity needed to arm the "
                "native capture. H5 is an identity anchor only: do not log in, "
                "play media, inspect player controls, or request media from it."
            ),
            "required_response": {
                "action": "resolve_xiaoetong_page",
                "subscription_id": item["identity"],
                "page_url": "current Xiaoetong MP wrapper or H5 page URL",
                "page_state": "unknown|unsupported_application",
            },
        }
        request["launch_resolver_command"] = [
            ".venv/bin/python", "scripts/kol_xiaoetong_launch.py",
            "--source-url", item["source_url"],
            "--subscription-id", item["identity"],
        ]
        request["instructions"] = (
            "First run launch_resolver_command with PYTHONPATH=src; it is "
            "read-only and validates the merchant-issued WeChat launch link. "
            "Return its generated browser_response unchanged, then let the runner "
            "arm before executing its one launch_command. If no launch plan is "
            "available, resolve the supplied URL only to a stable identity. "
        ) + request["instructions"]
        response = self._exchange_browser(request, item)
        self._validate_browser_response(request, response)
        observed_page_state = str(
            response.get("page_state") or "unknown"
        ).strip()
        if observed_page_state == "unsupported_application":
            if response.get("launch_allowed") is not False:
                raise EnrichmentError("unsupported application lacks no-launch evidence")
            return self._transition(
                manifest, item, "unsupported_application",
                diagnostic_code="unsupported_launch_application", launch_allowed=False,
            )
        if observed_page_state != "unknown":
            raise EnrichmentError("Xiaocao H5 resolution returned a playback state")
        resolved_url = urlsplit(str(response.get("page_url") or ""))
        if (
            resolved_url.scheme == "https"
            and re.fullmatch(r"app[a-z0-9]+\.h5\.xiaoeknow\.com", resolved_url.netloc)
            and re.fullmatch(r"/p/course/ecourse/preview/course_[A-Za-z0-9]+", resolved_url.path)
            and not item.get("capture_job_id")
        ):
            return self._transition(
                manifest, item, "unsupported_resource",
                page_url=urlunsplit(resolved_url._replace(query="", fragment="")),
                diagnostic_code="non_live_course_preview", launch_allowed=False,
            )
        page_url, source_identity = self._canonical_page(
            str(response.get("page_url") or ""),
        )
        resource_id = source_identity.rsplit(":", 1)[-1]
        if (
            response.get("source_identity", source_identity) != source_identity
            or response.get("live_id", resource_id) != resource_id
        ):
            raise EnrichmentError("resolver response identity differs from its page URL")
        if not resource_id.startswith("l_"):
            raise EnrichmentError(
                "Xiaocao capture supports only Xiaoetong live mini-program entries"
            )
        fields: dict[str, Any] = {
            "page_url": page_url,
            "source_identity": source_identity,
            "observed_page_state": observed_page_state,
            "playback_route": self.playback_route,
        }
        if response.get("mini_program_name") == "见势擒龙团":
            fields["mini_program_name"] = "见势擒龙团"
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
        backfill_since: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load()
        if backfill_since is not None:
            self._prepare_manual_backfill(manifest, only_identity, backfill_since)
        if only_identity is None:
            self._poll(manifest)
            self.expire_stale_waits(manifest)
            item = self._next_pending(manifest)
        else:
            self.expire_stale_waits(
                manifest, skip_identity=only_identity if backfill_since is not None else None,
            )
            item = manifest["items"].get(only_identity)
            if not isinstance(item, dict):
                source_matches = [
                    row
                    for row in manifest["items"].values()
                    if isinstance(row, dict)
                    and str(row.get("source_identity") or "") == only_identity
                ]
                if len(source_matches) != 1:
                    raise EnrichmentError(
                        "Xiaocao narrow resume item is missing"
                        if not source_matches
                        else "Xiaocao narrow resume source identity is ambiguous"
                    )
                item = source_matches[0]
            item = dict(item)
            if item.get("status") == "unsupported_application" and not item.get("capture_job_id"):
                # A user-requested exact-item retry may use a newly installed
                # application adapter. Ordinary sweeps never reactivate it.
                item = self._transition(
                    manifest, item, "discovered", recheck_reason="explicit_application_recheck",
                )
            # Explicit one-item backfill may recover a recent skipped preview.
            # Expired entries and any already-bound claims remain immutable.
            if (
                item.get("status") == "superseded"
                and not item.get("capture_job_id")
                and datetime.fromisoformat(item["published_at"])
                > datetime.fromisoformat(self._now()) - timedelta(hours=72)
            ):
                item = self._transition(
                    manifest, item, "discovered", backfill_reason="explicit_item_resume",
                )
            if item.get("status") in _TERMINAL:
                return {
                    "status": "no_update",
                    "identity": item["identity"],
                    "already_completed": item.get("status") not in {"unsupported_application", "unsupported_resource", "expired"},
                    "unsupported_resource": item.get("status") == "unsupported_resource",
                    "unsupported_application": item.get("status") == "unsupported_application",
                    **({"expired": True, "manual_backfill_excluded": item.get("manual_backfill_excluded") is True}
                       if item.get("status") == "expired" else {}),
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

        if item["status"] == "unsupported_resource":
            return {
                "status": "no_update", "identity": item["identity"],
                "unsupported_resource": True, "launch_allowed": False,
            }

        if item["status"] == "unsupported_application":
            return {
                "status": "no_update", "identity": item["identity"],
                "unsupported_application": True, "launch_allowed": False,
            }

        if (
            item["status"] == "page_resolved"
            and str(item.get("source_identity") or "")
            and not str(item.get("source_identity") or "")
            .rsplit(":", 1)[-1]
            .startswith("l_")
        ):
            raise EnrichmentError(
                "Xiaocao capture supports only Xiaoetong live mini-program entries"
            )

        if item["status"] == "page_resolved":
            armed = self.capture_driver.arm(
                item["identity"],
                str(item.get("page_url") or "") or None,
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
            and not (item.get("human_playback_started_at") and item.get("activated") is not True)
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

        if (
            capture_reconciled
            and item.get("media_request_observed") is True
            and item.get("playback_window_closed") is not True
            and item.get("playback_paused") is not True  # Historical pause receipts.
        ):
            item = self._check_mini_program_playback(
                manifest, item, reason="captured_window_cleanup",
            )
            playback_checked = True
            if item["status"] == "awaiting_playback":
                return self._waiting(item, {"status": "awaiting_playback"})

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
            )
        except InvalidSourcePage as exc:
            raise EnrichmentDiagnosticError(
                "Xiaocao live source identity is invalid",
                category="contract_error",
                code="xiaocao_live_source_identity_invalid",
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
