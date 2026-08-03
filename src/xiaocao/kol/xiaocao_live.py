"""Resumable Xiaocao live capture-to-decisions orchestration.

The broadband phase owns the sniffer, compressed media validation, proxy
cleanup, and any large upload.  Once the exact cloud video is ready, this
module publishes a lightweight handoff; later coordinator runs use only that
handoff and the Netdisk job ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .capture import (
    CaptureJobStore,
    SnifferClient,
    SnifferError,
    resolve_candidate,
)
from ._shared import DecisionError
from .claim_coverage import (
    build_claim_extraction_request,
    validate_claim_coverage,
)
from .author_profiles import semantic_author_profile
from .enrichment_types import EnrichmentError
from .netdisk_enrichment import NetdiskEnrichmentService


DEFAULT_CAPTURE_LEDGER = Path("output/live/kol_capture_jobs.jsonl")
DEFAULT_OUTPUT = Path("output/live/kol_xiaocao_live")
DEFAULT_NETDISK_OUTPUT = Path("output/live/kol_netdisk_enrichment")
DEFAULT_DECISION_OUTPUT = Path("output/live/kol_intelligence")
DEFAULT_SNIFFER_DIR = Path("/Users/bytedance/coding/wx_channels_download")
DEFAULT_SNIFFER_BINARY = DEFAULT_SNIFFER_DIR / "wx_video_download_macos_arm64"
REQUIRED_COVERAGE_ROWS = {
    "todays_market_diagnosis",
    "next_session_playbook",
    "next_several_session_base_case",
    "style_market_cap_regime",
    "market_board_sector_hierarchy",
    "position_risk_budget",
    "named_asset_inventory",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_NETDISK = {
    "video_ready",
    "transcript_claimed",
    "transcript_requested",
    "transcript_ready",
    "ai_note_claimed",
    "ai_note_requested",
    "ai_note_ready",
    "transcript_captured",
    "verified",
    "decided",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_json(path: Path | str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EnrichmentError(f"invalid JSON evidence: {source}") from exc
    if not isinstance(value, dict):
        raise EnrichmentError("JSON evidence must be an object")
    return value


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EnrichmentError(
                f"invalid JSONL evidence at {source}:{line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise EnrichmentError(
                f"invalid JSONL evidence at {source}:{line_number}"
            )
        rows.append(value)
    return rows


def validate_cleanup_evidence(value: dict[str, Any]) -> None:
    proxy = value.get("proxy_flags")
    listeners = value.get("listeners")
    if (
        value.get("process_gone") is not True
        or value.get("api_status_unavailable") is not True
        or not isinstance(listeners, dict)
        or listeners.get("2022") is not False
        or listeners.get("2023") is not False
        or not isinstance(proxy, dict)
        or any(
            int(proxy.get(name, -1)) != 0
            for name in (
                "HTTPEnable",
                "HTTPSEnable",
                "ProxyAutoConfigEnable",
                "SOCKSEnable",
            )
        )
        or not str(value.get("observed_at") or "").strip()
    ):
        raise EnrichmentError("capture cleanup proof is incomplete")


def _evidence_time(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise EnrichmentError(f"invalid evidence timestamp: {field}") from exc
    if parsed.tzinfo is None:
        raise EnrichmentError(f"evidence timestamp has no timezone: {field}")
    return parsed


def validate_coverage_matrix(
    item: dict[str, Any],
    *,
    evidence_text: str,
) -> None:
    coverage = item.get("trade_information_coverage")
    if not isinstance(coverage, dict) or set(coverage) != REQUIRED_COVERAGE_ROWS:
        raise EnrichmentError("Ticket 03 trade-information coverage is incomplete")
    for name in sorted(REQUIRED_COVERAGE_ROWS):
        row = coverage.get(name)
        if not isinstance(row, dict) or row.get("status") not in {
            "present",
            "absent",
        }:
            raise EnrichmentError(f"Ticket 03 coverage row is invalid: {name}")
        if row["status"] == "absent":
            if not str(row.get("reason") or "").strip():
                raise EnrichmentError(
                    f"Ticket 03 absent coverage row needs a reason: {name}"
                )
            continue
        quotes = row.get("evidence_quotes")
        if (
            not isinstance(quotes, list)
            or not quotes
            or any(
                not isinstance(quote, str)
                or not quote.strip()
                or quote not in evidence_text
                for quote in quotes
            )
        ):
            raise EnrichmentError(
                f"Ticket 03 coverage quotes are not evidence-bound: {name}"
            )
        for field in ("reader_meaning", "horizon", "triggers", "falsifiers"):
            field_value = row.get(field)
            if field in {"triggers", "falsifiers"}:
                valid = (
                    isinstance(field_value, list)
                    and bool(field_value)
                    and all(
                        isinstance(entry, str) and entry.strip()
                        for entry in field_value
                    )
                )
            else:
                valid = isinstance(field_value, str) and bool(field_value.strip())
            if not valid:
                raise EnrichmentError(
                    f"Ticket 03 coverage row needs {field}: {name}"
                )
    inventory = coverage["named_asset_inventory"].get("assets")
    if not isinstance(inventory, list):
        raise EnrichmentError("Ticket 03 named-asset inventory must be a list")
    for asset in inventory:
        if not isinstance(asset, dict) or any(
            not str(asset.get(field) or "").strip()
            for field in ("surface_form", "role", "resolution_status")
        ):
            raise EnrichmentError("Ticket 03 named-asset row is invalid")
        if asset["resolution_status"] == "resolved":
            if any(
                not str(asset.get(field) or "").strip()
                for field in ("official_name", "market")
            ):
                raise EnrichmentError(
                    "Ticket 03 resolved asset needs official name and market"
                )
        elif not str(asset.get("exclusion_reason") or "").strip():
            raise EnrichmentError(
                "Ticket 03 unresolved asset needs an exclusion reason"
            )


def validate_decision_bundle(
    bundle_path: Path | str,
    *,
    transcript_path: Path,
    transcript_sha256: str,
) -> dict[str, Any]:
    bundle = _read_json(bundle_path)
    items = bundle.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise EnrichmentError("Ticket 03 requires exactly one decision item")
    item = items[0]
    if item.get("decision_status") not in {
        "actionable_signal",
        "no_actionable_signal",
    }:
        raise EnrichmentError("Ticket 03 decision_status is invalid")
    if item.get("knowledge_status") not in {
        "reusable_knowledge",
        "no_reusable_knowledge",
    }:
        raise EnrichmentError("Ticket 03 knowledge_status is invalid")
    if not str(item.get("knowledge_reason") or "").strip():
        raise EnrichmentError("Ticket 03 knowledge branch needs a reason")
    if Path(str(item.get("evidence_path") or "")).expanduser().resolve() != (
        transcript_path.resolve()
    ):
        raise EnrichmentError("Ticket 03 bundle uses the wrong transcript")
    if str(item.get("evidence_sha256") or transcript_sha256) != transcript_sha256:
        raise EnrichmentError("Ticket 03 bundle transcript hash does not match")
    evidence_text = transcript_path.read_text(encoding="utf-8")
    validate_coverage_matrix(item, evidence_text=evidence_text)
    try:
        validate_claim_coverage(
            item,
            evidence_text=evidence_text,
            evidence_sha256=transcript_sha256,
        )
    except DecisionError as exc:
        raise EnrichmentError(
            "Ticket 03 investment-claim coverage is incomplete"
        ) from exc
    if not isinstance(item.get("market_outlook"), dict):
        raise EnrichmentError("Ticket 03 market-level conclusion is missing")
    book = item.get("book_kol_us")
    if (
        not isinstance(book, dict)
        or book.get("decision") not in {"trade", "no_trade"}
        or (
            book.get("decision") == "no_trade"
            and not str(book.get("reason") or "").strip()
        )
    ):
        raise EnrichmentError("Ticket 03 Book KOL-US result is incomplete")
    return bundle


class XiaocaoLiveService:
    """One status surface for the broadband and coordinator phases."""

    def __init__(
        self,
        output_dir: Path | str = DEFAULT_OUTPUT,
        *,
        capture_ledger: Path | str = DEFAULT_CAPTURE_LEDGER,
        netdisk_output: Path | str = DEFAULT_NETDISK_OUTPUT,
        decision_output: Path | str = DEFAULT_DECISION_OUTPUT,
        sniffer_binary: Path | str = DEFAULT_SNIFFER_BINARY,
        sniffer_client: SnifferClient | None = None,
        netdisk_service: NetdiskEnrichmentService | None = None,
        popen: Callable[..., Any] = subprocess.Popen,
        runner: Callable[..., Any] = subprocess.run,
        clock: Callable[[], datetime] = _now,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"
        self.capture_store = CaptureJobStore(capture_ledger)
        self.netdisk = netdisk_service or NetdiskEnrichmentService(netdisk_output)
        self.decision_output = Path(decision_output).expanduser().resolve()
        self.sniffer_binary = Path(sniffer_binary).expanduser().resolve()
        self.sniffer = sniffer_client or SnifferClient()
        self._popen = popen
        self._runner = runner
        self._clock = clock

    def _append(self, event: str, **fields: Any) -> dict[str, Any]:
        row = {
            "schema_version": 1,
            "event": event,
            "updated_at": self._clock().isoformat(timespec="seconds"),
            **fields,
        }
        _append_jsonl(self.events_path, row)
        return row

    def events(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows

    def import_handoff_capsule(self, capsule: dict[str, Any]) -> dict[str, Any]:
        """Import one portable cloud-ready job without trusting local paths."""
        if not isinstance(capsule, dict) or capsule.get("schema_version") != 2:
            raise EnrichmentError("remote handoff capsule schema is invalid")
        expected_handoff_sha256 = str(capsule.get("handoff_sha256") or "")
        unsigned = dict(capsule)
        unsigned.pop("handoff_sha256", None)
        if (
            not _SHA256.fullmatch(expected_handoff_sha256)
            or _sha256_text(_canonical(unsigned)) != expected_handoff_sha256
        ):
            raise EnrichmentError("remote handoff capsule hash is invalid")
        handoff_id = str(capsule.get("handoff_id") or "")
        capture_job_id = str(capsule.get("capture_job_id") or "")
        media_sha256 = str(capsule.get("media_sha256") or "")
        media_basename = str(capsule.get("media_basename") or "")
        job_id = str(capsule.get("netdisk_job_id") or "")
        netdisk_path = f"/课程/自己的课/小草/{media_basename}"
        if (
            capsule.get("source") != "xiaocao"
            or capsule.get("author") != "小草"
            or capsule.get("provider") != "baidu_consumer_page"
            or capsule.get("large_payload_local_bytes") != 0
            or not _SHA256.fullmatch(handoff_id)
            or not capture_job_id
            or not _SHA256.fullmatch(media_sha256)
            or not media_basename
            or "/" in media_basename
            or "\\" in media_basename
            or job_id != f"kol-netdisk-{media_sha256[:16]}"
            or capsule.get("cloud_reference") != f"baidu:{netdisk_path}"
        ):
            raise EnrichmentError("remote handoff capsule binding is invalid")
        try:
            media_size_bytes = int(capsule.get("media_size_bytes") or 0)
            media_duration_seconds = float(
                capsule.get("media_duration_seconds") or 0
            )
        except (TypeError, ValueError) as exc:
            raise EnrichmentError(
                "remote handoff capsule media metadata is invalid"
            ) from exc
        if media_size_bytes <= 0 or media_duration_seconds <= 0:
            raise EnrichmentError("remote handoff capsule media metadata is invalid")

        snapshot = capsule.get("netdisk_job_snapshot")
        expected_snapshot_sha256 = str(
            capsule.get("netdisk_job_snapshot_sha256") or ""
        )
        if (
            not isinstance(snapshot, dict)
            or not _SHA256.fullmatch(expected_snapshot_sha256)
            or _sha256_text(_canonical(snapshot)) != expected_snapshot_sha256
        ):
            raise EnrichmentError("remote Netdisk job snapshot hash is invalid")
        forbidden = {
            "video_path",
            "media_path",
            "browser_evidence",
            "browser_liveness",
        }
        if forbidden.intersection(snapshot):
            raise EnrichmentError("remote Netdisk job snapshot is not portable")
        if (
            snapshot.get("schema_version") != 1
            or snapshot.get("status") != "video_ready"
            or snapshot.get("provider") != "baidu_consumer_page"
            or snapshot.get("job_id") != job_id
            or snapshot.get("netdisk_directory") != "/课程/自己的课/小草"
            or snapshot.get("netdisk_path") != netdisk_path
            or snapshot.get("video_basename") != media_basename
            or snapshot.get("video_sha256") != media_sha256
            or snapshot.get("video_sha256_kind") != "content_sha256"
            or snapshot.get("video_size_bytes") != media_size_bytes
            or float(snapshot.get("video_duration_seconds") or 0)
            != media_duration_seconds
            or snapshot.get("source_mode") != "cloud_handoff"
            or snapshot.get("large_payload_local_bytes") != 0
            or snapshot.get("handoff_id") != handoff_id
        ):
            raise EnrichmentError("remote Netdisk job snapshot binding is invalid")

        handoff_path = (
            self.output_dir
            / "imported_handoffs"
            / f"{capture_job_id}.json"
        )
        existing_handoff_event = self._event(
            "cloud_handoff_imported",
            capture_job_id=capture_job_id,
        )
        if existing_handoff_event is not None:
            existing_path = Path(
                str(existing_handoff_event.get("handoff_path") or "")
            ).expanduser().resolve()
            if (
                not existing_path.is_file()
                or _sha256_file(existing_path)
                != existing_handoff_event.get("handoff_file_sha256")
                or _read_json(existing_path) != capsule
            ):
                raise EnrichmentError("remote handoff receipt changed")
        else:
            _atomic_json(handoff_path, capsule)
            self._append(
                "cloud_handoff_imported",
                status="handoff_imported",
                capture_job_id=capture_job_id,
                live_id=str(capsule.get("live_id") or ""),
                media_sha256=media_sha256,
                netdisk_job_id=job_id,
                handoff_id=handoff_id,
                handoff_path=str(handoff_path),
                handoff_self_sha256=expected_handoff_sha256,
                handoff_file_sha256=_sha256_file(handoff_path),
                coordinator_large_payload_local_bytes=0,
                next="remote_coordinator",
            )

        with self.netdisk.store.job_lock(job_id):
            try:
                current = self.netdisk.store.latest(job_id)
            except EnrichmentError as exc:
                if "not found" not in str(exc):
                    raise
                current = None
            if current is not None:
                if (
                    current.get("handoff_id") != handoff_id
                    or current.get("video_sha256") != media_sha256
                    or current.get("netdisk_path") != netdisk_path
                ):
                    raise EnrichmentError(
                        "remote handoff conflicts with the existing Netdisk job"
                    )
                return {**current, "idempotent_replay": True}
            now = self._clock().isoformat(timespec="seconds")
            row = {
                **snapshot,
                "event": "netdisk_remote_handoff_imported",
                "browser_control_blocked": True,
                "imported_at": now,
                "updated_at": now,
            }
            self.netdisk.store.append(row)
            return {**row, "idempotent_replay": False}

    def _imported_handoff(self, capture_job_id: str) -> dict[str, Any] | None:
        event = self._event(
            "cloud_handoff_imported",
            capture_job_id=capture_job_id,
        )
        if event is None:
            return None
        path = Path(str(event.get("handoff_path") or "")).expanduser().resolve()
        if (
            not path.is_file()
            or _sha256_file(path) != event.get("handoff_file_sha256")
        ):
            raise EnrichmentError("remote handoff receipt changed")
        capsule = _read_json(path)
        unsigned = dict(capsule)
        self_hash = str(unsigned.pop("handoff_sha256", ""))
        if (
            capsule.get("capture_job_id") != capture_job_id
            or capsule.get("handoff_id") != event.get("handoff_id")
            or capsule.get("media_sha256") != event.get("media_sha256")
            or capsule.get("netdisk_job_id") != event.get("netdisk_job_id")
            or capsule.get("large_payload_local_bytes") != 0
            or self_hash != event.get("handoff_self_sha256")
            or self_hash != _sha256_text(_canonical(unsigned))
        ):
            raise EnrichmentError("remote handoff receipt binding is invalid")
        return capsule

    def latest(self) -> dict[str, Any] | None:
        rows = self.events()
        return rows[-1] if rows else None

    def _event(
        self,
        name: str,
        *,
        capture_job_id: str | None = None,
    ) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in reversed(self.events())
                if row.get("event") == name
                and (
                    capture_job_id is None
                    or row.get("capture_job_id") == capture_job_id
                )
            ),
            None,
        )

    def status(self) -> dict[str, Any]:
        current = self.latest()
        if current is None:
            return {"status": "not_started", "next": "run"}
        surface = {
            key: current[key]
            for key in (
                "event",
                "status",
                "capture_job_id",
                "live_id",
                "media_sha256",
                "netdisk_job_id",
                "transcript_sha256",
                "decision_result_sha256",
                "next",
                "updated_at",
            )
            if key in current
        }
        capture_job_id = str(current.get("capture_job_id") or "")
        if (
            capture_job_id
            and current.get("event") == "capture_armed"
        ):
            capture = self.capture_store.latest(capture_job_id)
            if capture is not None:
                surface["event"] = str(capture.get("event") or surface["event"])
                surface["status"] = str(capture.get("status") or surface["status"])
                surface["updated_at"] = str(
                    capture.get("updated_at") or surface["updated_at"]
                )
                if capture.get("candidate"):
                    surface["live_id"] = str(
                        (capture["candidate"] or {}).get("live_id") or ""
                    )
                if capture.get("media_path"):
                    surface["media_path"] = str(capture["media_path"])
                surface["next"] = (
                    "rerun"
                    if surface["status"] != "awaiting_capture"
                    else "user_playback"
                )
        return surface

    def _sniffer_pids(self) -> list[int]:
        if not self.sniffer_binary.is_file():
            return []
        result = self._runner(
            ["ps", "-ax", "-o", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
        )
        expected = str(self.sniffer_binary)
        pids = []
        for line in result.stdout.splitlines():
            pieces = line.strip().split(maxsplit=1)
            if len(pieces) == 2 and pieces[1].split()[0] == expected:
                pids.append(int(pieces[0]))
        return pids

    def start(self) -> dict[str, Any]:
        """Start or reconcile the sniffer, arm baseline, and emit one prompt."""
        armed = self._event("capture_armed")
        if armed is not None:
            pids = self._sniffer_pids()
            try:
                sniffer_status = self.sniffer.status()
            except SnifferError:
                sniffer_status = None
            if len(pids) > 1:
                raise EnrichmentError("multiple exact sniffer processes are running")
            if not pids and sniffer_status is None:
                if not self.sniffer_binary.is_file():
                    raise EnrichmentError(
                        f"sniffer binary not found: {self.sniffer_binary}"
                    )
                process = self._popen(
                    [str(self.sniffer_binary)],
                    cwd=str(self.sniffer_binary.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                pids = [int(process.pid)]
                for _ in range(50):
                    try:
                        sniffer_status = self.sniffer.status()
                        break
                    except SnifferError:
                        time.sleep(0.1)
                if len(pids) != 1 or sniffer_status is None:
                    raise EnrichmentError("sniffer did not resume healthy")
                self._append(
                    "sniffer_resumed",
                    status="healthy",
                    capture_job_id=armed["capture_job_id"],
                    process_pid=pids[0],
                    executable=str(self.sniffer_binary),
                    sniffer_version=str(sniffer_status.get("version") or ""),
                    baseline_sha256=armed["baseline_sha256"],
                    prompt_replayed=False,
                )
            elif len(pids) != 1 or sniffer_status is None:
                raise EnrichmentError("sniffer process/API health is inconsistent")
            return {
                **armed,
                "idempotent_replay": True,
                "prompt": None,
            }
        if not self.sniffer_binary.is_file():
            raise EnrichmentError(f"sniffer binary not found: {self.sniffer_binary}")
        claim = self._event("sniffer_start_claimed")
        if claim is None:
            claim = self._append(
                "sniffer_start_claimed",
                status="starting",
                idempotency_key=_sha256_text(f"start:{self.sniffer_binary}"),
                executable=str(self.sniffer_binary),
            )
        pids = self._sniffer_pids()
        try:
            sniffer_status = self.sniffer.status()
        except SnifferError:
            sniffer_status = None
        if len(pids) > 1:
            raise EnrichmentError("multiple exact sniffer processes are running")
        if not pids and sniffer_status is None:
            process = self._popen(
                [str(self.sniffer_binary)],
                cwd=str(self.sniffer_binary.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            pids = [int(process.pid)]
            for _ in range(50):
                try:
                    sniffer_status = self.sniffer.status()
                    break
                except SnifferError:
                    time.sleep(0.1)
        if len(pids) != 1 or sniffer_status is None:
            raise EnrichmentError("sniffer did not become healthy")
        receipt = self._append(
            "sniffer_started",
            status="healthy",
            process_pid=pids[0],
            executable=str(self.sniffer_binary),
            sniffer_version=str(sniffer_status.get("version") or ""),
            start_claim_idempotency_key=claim["idempotency_key"],
        )
        capture = self.capture_store.arm(
            self.sniffer.candidates(),
            sniffer_status=sniffer_status,
        )
        prompt_id = _sha256_text(f"prompt:{capture['job_id']}")
        armed = self._append(
            "capture_armed",
            status="awaiting_capture",
            capture_job_id=capture["job_id"],
            baseline_count=len(capture.get("baseline_candidate_keys") or []),
            baseline_sha256=_sha256_text(
                _canonical(capture.get("baseline_candidate_keys") or [])
            ),
            process_pid=receipt["process_pid"],
            prompt_id=prompt_id,
            next="user_playback",
        )
        return {
            **armed,
            "idempotent_replay": False,
            "prompt": (
                "请现在打开企业微信里的“小草”目标卡片，必要时输入密码；"
                "目标播放器一弹出即可，无需持续播放或等待。"
            ),
        }

    @staticmethod
    def _matching_tasks(
        capture: dict[str, Any],
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidate = capture.get("candidate") or {}
        expected_live = str(candidate.get("live_id") or "")
        matches = []
        for task in tasks:
            req = ((task.get("meta") or {}).get("req") or {})
            labels = req.get("labels") or {}
            if (
                str(labels.get("live_id") or "") == expected_live
                and str(labels.get("type") or "") == "live_capture"
                and str(labels.get("compress") or "").lower() == "true"
            ):
                matches.append(task)
        return matches

    def advance_capture(self, capture_job_id: str) -> dict[str, Any]:
        current = self.capture_store.latest(capture_job_id)
        if current is None:
            raise EnrichmentError("capture job does not exist")
        if current.get("status") == "awaiting_capture":
            candidates = self.sniffer.candidates()
            detected = self.capture_store.detect_capture(current, candidates)
            if detected is None:
                return {
                    "event": "capture_pending",
                    "status": "awaiting_capture",
                    "capture_job_id": capture_job_id,
                }
            current = detected
        if current.get("status") == "captured":
            current = self.capture_store.transition(
                current,
                "download_claimed",
                status="download_claimed",
                download_idempotency_key=_sha256_text(
                    f"download:{current['candidate_key']}"
                ),
            )
        if current.get("status") == "download_claimed":
            tasks = self.sniffer.tasks()
            matches = self._matching_tasks(current, tasks)
            if len(matches) > 1:
                raise EnrichmentError("multiple download tasks match one live_id")
            if matches:
                task_id = str(matches[0]["id"])
            else:
                candidate = resolve_candidate(current, self.sniffer.candidates())
                if candidate is None:
                    raise EnrichmentError("captured live is unavailable for download")
                task_id = self.sniffer.start_download(candidate)
            current = self.capture_store.transition(
                current,
                "download_started",
                status="downloading",
                download_task_id=task_id,
            )
        if current.get("status") == "downloading":
            current = (
                self.capture_store.reconcile_download(current, self.sniffer.tasks())
                or current
            )
        if current.get("status") == "download_failed":
            candidate = resolve_candidate(current, self.sniffer.candidates())
            if candidate is None:
                raise EnrichmentError("failed live is unavailable for exact retry")
            claimed = self.capture_store.transition(
                current,
                "download_retry_claimed",
                status="download_retry_claimed",
                retry_idempotency_key=_sha256_text(
                    f"retry:{current['candidate_key']}"
                ),
            )
            task_id = self.sniffer.start_download(candidate, force=True)
            current = self.capture_store.transition(
                claimed,
                "download_restarted",
                status="downloading",
                download_task_id=task_id,
            )
        return current

    def reconcile_completed_capture(self, capture_job_id: str) -> dict[str, Any]:
        """Recover a complete compressed artifact after a sniffer interruption."""
        current = self.capture_store.latest(capture_job_id)
        if current is None:
            raise EnrichmentError("capture job does not exist")
        if current.get("status") == "downloaded":
            return {**current, "idempotent_replay": True}
        if current.get("status") != "downloading":
            raise EnrichmentError("capture is not awaiting download reconciliation")

        task_id = str(current.get("download_task_id") or "")
        matches = [
            task
            for task in self.sniffer.tasks()
            if str(task.get("id") or "") == task_id
        ]
        if len(matches) != 1:
            raise EnrichmentError("exact interrupted download task is unavailable")
        task = matches[0]
        if str(task.get("status") or "").lower() != "pause":
            raise EnrichmentError("interrupted download task is not durably paused")
        if str(task.get("protocol") or "").lower() != "stream":
            raise EnrichmentError("interrupted download task is not a stream capture")

        candidate = current.get("candidate") or {}
        meta = task.get("meta") or {}
        req = meta.get("req") or {}
        labels = req.get("labels") or meta.get("labels") or {}
        opts = meta.get("opts") or {}
        live_id = str(candidate.get("live_id") or "")
        capture_id = str(candidate.get("id") or "")
        if (
            not live_id
            or not capture_id
            or str(labels.get("live_id") or "") != live_id
            or str(labels.get("capture_id") or "") != capture_id
            or str(labels.get("type") or "") != "live_capture"
            or str(labels.get("compress") or "").lower() != "true"
            or str(labels.get("compress_inline") or "").lower() != "true"
        ):
            raise EnrichmentError("paused task does not prove the compressed capture path")

        source_name = str(candidate.get("filename") or "")
        expected_name = (
            source_name.removesuffix(".mp4") + "-compressed.mp4"
            if source_name.endswith(".mp4")
            else ""
        )
        task_name = str(task.get("name") or opts.get("name") or "")
        directory = str(opts.get("path") or "")
        if not expected_name or task_name != expected_name or not directory:
            raise EnrichmentError("paused task media target does not match the capture")
        media = (Path(directory).expanduser() / task_name).resolve()
        if not media.is_file() or media.stat().st_size <= 0:
            raise EnrichmentError("paused task compressed artifact is missing")
        raw_name = media.name.removesuffix("-compressed.mp4") + ".mp4"
        if (media.parent / raw_name).exists():
            raise EnrichmentError("interrupted capture retained a raw source video")

        try:
            expected_duration = float(labels.get("hls_duration_sec") or 0)
        except (TypeError, ValueError) as exc:
            raise EnrichmentError("paused task has invalid HLS duration evidence") from exc
        if expected_duration < 60:
            raise EnrichmentError("paused task is missing HLS duration evidence")
        result = self._runner(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size",
                "-of",
                "json",
                str(media),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            probe = json.loads(result.stdout)["format"]
            duration = float(probe["duration"])
            size = int(probe["size"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise EnrichmentError("paused compressed capture could not be probed") from exc
        tolerance = max(15.0, expected_duration * 0.01)
        if duration < 60 or abs(duration - expected_duration) > tolerance:
            raise EnrichmentError("paused compressed capture duration does not match HLS")

        return self.capture_store.transition(
            current,
            "download_completed_reconciled",
            status="downloaded",
            download_task=task,
            media_path=str(media),
            provider_status_observed="pause",
            media_size_bytes=size,
            media_duration_seconds=duration,
            expected_duration_seconds=expected_duration,
            reconciliation_reason="sniffer_interrupted_after_complete_media",
        )

    @staticmethod
    def _capture_contract(capture: dict[str, Any]) -> dict[str, Any]:
        candidate = capture.get("candidate")
        task = capture.get("download_task")
        labels = ((task or {}).get("meta") or {}).get("labels") or {}
        live_id = str((candidate or {}).get("live_id") or "")
        if (
            capture.get("status") != "downloaded"
            or not live_id
            or capture.get("candidate_key") != f"live:{live_id}"
            or f"live:{live_id}" in set(capture.get("baseline_candidate_keys") or [])
            or str(labels.get("live_id") or "") != live_id
            or str(labels.get("type") or "") != "live_capture"
            or str(labels.get("compress") or "").lower() != "true"
            or str(labels.get("compress_inline") or "").lower() != "true"
        ):
            raise EnrichmentError("capture ledger does not prove the Ticket 03 path")
        return {
            "live_id": live_id,
            "capture_id": str((candidate or {}).get("id") or ""),
            "captured_at": str((candidate or {}).get("captured") or ""),
            "title": str((candidate or {}).get("title") or ""),
        }

    def validate_media(self, capture_job_id: str) -> dict[str, Any]:
        capture = self.capture_store.latest(capture_job_id)
        if capture is None:
            raise EnrichmentError("capture job does not exist")
        identity = self._capture_contract(capture)
        media = Path(str(capture.get("media_path") or "")).expanduser().resolve()
        if (
            not media.is_file()
            or not media.name.endswith("-compressed.mp4")
            or media.stat().st_size <= 0
        ):
            raise EnrichmentError("compressed capture artifact is missing or invalid")
        raw_name = media.name.removesuffix("-compressed.mp4") + ".mp4"
        if (media.parent / raw_name).exists():
            raise EnrichmentError("normal capture path retained a raw source video")
        result = self._runner(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size",
                "-of",
                "json",
                str(media),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            probe = json.loads(result.stdout)["format"]
            duration = float(probe["duration"])
            size = int(probe["size"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise EnrichmentError("compressed capture could not be probed") from exc
        labels = ((capture.get("download_task") or {}).get("meta") or {}).get(
            "labels"
        ) or {}
        expected_duration = float(labels.get("hls_duration_sec") or duration)
        tolerance = max(15.0, expected_duration * 0.01)
        if duration < 60 or abs(duration - expected_duration) > tolerance:
            raise EnrichmentError("compressed capture duration is implausible")
        media_sha = _sha256_file(media)
        existing = self._event("media_validated")
        if (
            existing
            and existing.get("capture_job_id") == capture_job_id
            and existing.get("media_sha256") == media_sha
        ):
            return {**existing, "idempotent_replay": True}
        return self._append(
            "media_validated",
            status="media_validated",
            capture_job_id=capture_job_id,
            live_id=identity["live_id"],
            capture_id=identity["capture_id"],
            captured_at=identity["captured_at"],
            media_path=str(media),
            media_basename=media.name,
            media_sha256=media_sha,
            media_size_bytes=size,
            media_duration_seconds=duration,
            raw_source_retained=False,
            idempotent_replay=False,
        )

    def cleanup_snapshot(self) -> dict[str, Any]:
        pids = self._sniffer_pids()
        listeners: dict[str, bool] = {}
        for port in (2022, 2023):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(0.2)
                listeners[str(port)] = client.connect_ex(("127.0.0.1", port)) == 0
        try:
            self.sniffer.status()
            api_unavailable = False
        except SnifferError:
            api_unavailable = True
        result = self._runner(
            ["scutil", "--proxy"],
            check=True,
            capture_output=True,
            text=True,
        )
        flags = {}
        for name in (
            "HTTPEnable",
            "HTTPSEnable",
            "ProxyAutoConfigEnable",
            "SOCKSEnable",
        ):
            match = re.search(rf"\b{name}\s*:\s*(\d+)", result.stdout)
            flags[name] = int(match.group(1)) if match else -1
        return {
            "process_gone": not pids,
            "listeners": listeners,
            "api_status_unavailable": api_unavailable,
            "proxy_flags": flags,
            "observed_at": self._clock().isoformat(timespec="seconds"),
        }

    def cleanup_sniffer(self, *, capture_job_id: str) -> dict[str, Any]:
        existing = self._event(
            "capture_cleanup_completed",
            capture_job_id=capture_job_id,
        )
        if existing is not None:
            return {**existing, "idempotent_replay": True}
        self._append(
            "capture_cleanup_claimed",
            status="cleanup_claimed",
            idempotency_key=_sha256_text("xiaocao-sniffer-cleanup"),
        )
        pids = self._sniffer_pids()
        if len(pids) > 1:
            raise EnrichmentError("multiple exact sniffer processes block cleanup")
        if pids:
            os.kill(pids[0], signal.SIGINT)
            for _ in range(100):
                if not self._sniffer_pids():
                    break
                time.sleep(0.1)
        proof = self.cleanup_snapshot()
        proof["capture_job_id"] = capture_job_id
        validate_cleanup_evidence(proof)
        proof_path = self.output_dir / "receipts" / "capture_cleanup.json"
        _atomic_json(proof_path, proof)
        return self._append(
            "capture_cleanup_completed",
            status="cleanup_completed",
            cleanup_evidence_path=str(proof_path),
            cleanup_evidence_sha256=_sha256_file(proof_path),
            **proof,
        )

    def _publish_handoff(
        self,
        *,
        capture_job_id: str,
        media: dict[str, Any],
        netdisk: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self._event(
            "cloud_handoff_published",
            capture_job_id=capture_job_id,
        )
        if existing is not None:
            return {**existing, "idempotent_replay": True}
        claim = self._append(
            "cloud_handoff_claimed",
            status="handoff_claimed",
            capture_job_id=capture_job_id,
            media_sha256=media["media_sha256"],
            netdisk_job_id=netdisk["job_id"],
            idempotency_key=_sha256_text(
                f"handoff:{capture_job_id}:{netdisk['job_id']}"
            ),
        )
        handoff_id = str(claim["idempotency_key"])
        media_basename = str(media["media_basename"])
        netdisk_directory = "/课程/自己的课/小草"
        netdisk_path = f"{netdisk_directory}/{media_basename}"
        snapshot = {
            "schema_version": 1,
            "status": "video_ready",
            "provider": "baidu_consumer_page",
            "job_id": netdisk["job_id"],
            "netdisk_directory": netdisk_directory,
            "netdisk_path": netdisk_path,
            "video_basename": media_basename,
            "video_sha256": media["media_sha256"],
            "video_sha256_kind": "content_sha256",
            "video_size_bytes": media["media_size_bytes"],
            "video_duration_seconds": media["media_duration_seconds"],
            "source_mode": "cloud_handoff",
            "large_payload_local_bytes": 0,
            "handoff_id": handoff_id,
        }
        handoff = {
            "schema_version": 2,
            "source": "xiaocao",
            "author": "小草",
            "handoff_id": handoff_id,
            "capture_job_id": capture_job_id,
            "live_id": media["live_id"],
            "captured_at": media["captured_at"],
            "media_basename": media_basename,
            "media_sha256": media["media_sha256"],
            "media_size_bytes": media["media_size_bytes"],
            "media_duration_seconds": media["media_duration_seconds"],
            "netdisk_job_id": netdisk["job_id"],
            "cloud_reference": f"baidu:{netdisk_path}",
            "provider": "baidu_consumer_page",
            "large_payload_local_bytes": 0,
            "published_at": self._clock().isoformat(timespec="seconds"),
            "netdisk_job_snapshot": snapshot,
            "netdisk_job_snapshot_sha256": _sha256_text(_canonical(snapshot)),
        }
        handoff["handoff_sha256"] = _sha256_text(_canonical(handoff))
        path = self.output_dir / "handoffs" / f"{capture_job_id}.json"
        _atomic_json(path, handoff)
        return self._append(
            "cloud_handoff_published",
            status="handoff_published",
            capture_job_id=capture_job_id,
            live_id=media["live_id"],
            media_sha256=media["media_sha256"],
            netdisk_job_id=netdisk["job_id"],
            handoff_path=str(path),
            handoff_sha256=_sha256_file(path),
            handoff_claim_idempotency_key=claim["idempotency_key"],
            coordinator_large_payload_local_bytes=0,
            next="coordinator",
        )

    def _advance_imported_handoff(
        self,
        handoff: dict[str, Any],
        *,
        opencli_session: str,
        opencli_profile: str | None,
        audit_path: Path | str | None,
        bundle_path: Path | str | None,
        sender: Callable[[str, str], dict[str, Any]] | None,
    ) -> dict[str, Any]:
        capture_job_id = str(handoff["capture_job_id"])
        netdisk_job_id = str(handoff["netdisk_job_id"])
        state = self.netdisk.status(netdisk_job_id)
        if state.get("status") not in {"transcript_captured", "verified", "decided"}:
            state = self.netdisk.advance_opencli(
                netdisk_job_id,
                session=opencli_session,
                profile=opencli_profile,
            )
        if state.get("status") == "transcript_captured":
            if audit_path is None:
                return {
                    "event": "xiaocao_live_audit_input_required",
                    "status": "transcript_captured",
                    "scope": "post_handoff",
                    "capture_job_id": capture_job_id,
                    "netdisk_job_id": netdisk_job_id,
                    "transcript_path": state["transcript_path"],
                    "transcript_sha256": state["transcript_sha256"],
                    "video_sha256": state["video_sha256"],
                    "next": "provide_audit_path",
                }
            state = self.netdisk.verify_transcript(
                netdisk_job_id,
                audit_path=audit_path,
            )
        if state.get("status") == "verified":
            if bundle_path is None:
                return {
                    "event": "xiaocao_live_analysis_input_required",
                    "status": "verified",
                    "scope": "post_handoff",
                    "author": "小草",
                    "author_profile": semantic_author_profile("小草"),
                    "capture_job_id": capture_job_id,
                    "netdisk_job_id": netdisk_job_id,
                    "transcript_path": state["transcript_path"],
                    "transcript_sha256": state["transcript_sha256"],
                    "required_coverage_rows": sorted(REQUIRED_COVERAGE_ROWS),
                    "investment_claim_extraction": build_claim_extraction_request(
                        state["transcript_path"],
                        evidence_sha256=str(state["transcript_sha256"]),
                    ),
                    "next": "provide_bundle_path",
                }
            validate_decision_bundle(
                bundle_path,
                transcript_path=Path(state["transcript_path"]),
                transcript_sha256=str(state["transcript_sha256"]),
            )
            if sender is None:
                raise EnrichmentError("Ticket 03 decision sender is required")
            state = self.netdisk.decide(
                netdisk_job_id,
                bundle_path=bundle_path,
                decision_output_dir=self.decision_output,
                sender=sender,
            )
        if state.get("status") == "decided" and bundle_path is not None:
            requested_bundle = Path(bundle_path).expanduser().resolve()
            requested_bundle_sha = _sha256_file(requested_bundle)
            if requested_bundle_sha != state.get("decision_bundle_sha256"):
                validate_decision_bundle(
                    requested_bundle,
                    transcript_path=Path(state["transcript_path"]),
                    transcript_sha256=str(state["transcript_sha256"]),
                )
                if sender is None:
                    raise EnrichmentError(
                        "Ticket 03 decision revision sender is required"
                    )
                state = self.netdisk.decide(
                    netdisk_job_id,
                    bundle_path=requested_bundle,
                    decision_output_dir=self.decision_output,
                    sender=sender,
                )
        if state.get("status") != "decided":
            return {
                "event": "xiaocao_live_coordinator_pending",
                "status": state.get("status"),
                "scope": "post_handoff",
                "capture_job_id": capture_job_id,
                "netdisk_job_id": netdisk_job_id,
                "coordinator_large_payload_local_bytes": 0,
                "next": "rerun_coordinator",
            }
        decided = self._event(
            "xiaocao_live_handoff_decided",
            capture_job_id=capture_job_id,
        )
        if decided is None:
            self._append(
                "xiaocao_live_handoff_decided",
                status="decided",
                scope="post_handoff",
                capture_job_id=capture_job_id,
                live_id=str(handoff.get("live_id") or ""),
                media_sha256=str(handoff["media_sha256"]),
                handoff_id=str(handoff["handoff_id"]),
                netdisk_job_id=netdisk_job_id,
                transcript_sha256=state["transcript_sha256"],
                decision_result_sha256=state["decision_result_sha256"],
                coordinator_large_payload_local_bytes=0,
                next="acceptance_audit",
            )
        elif (
            decided.get("decision_result_sha256")
            != state.get("decision_result_sha256")
        ):
            self._append(
                "xiaocao_live_handoff_decision_revised",
                status="decided",
                scope="post_handoff",
                capture_job_id=capture_job_id,
                live_id=str(handoff.get("live_id") or ""),
                media_sha256=str(handoff["media_sha256"]),
                handoff_id=str(handoff["handoff_id"]),
                netdisk_job_id=netdisk_job_id,
                transcript_sha256=state["transcript_sha256"],
                decision_result_sha256=state["decision_result_sha256"],
                coordinator_large_payload_local_bytes=0,
                next="acceptance_audit",
            )
        return self._audit_imported_acceptance(capture_job_id, handoff)

    def advance(
        self,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None = None,
        audit_path: Path | str | None = None,
        bundle_path: Path | str | None = None,
        sender: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        capture = self.capture_store.latest(capture_job_id)
        if capture is None:
            imported_handoff = self._imported_handoff(capture_job_id)
            if imported_handoff is None:
                raise EnrichmentError("capture job does not exist")
            return self._advance_imported_handoff(
                imported_handoff,
                opencli_session=opencli_session,
                opencli_profile=opencli_profile,
                audit_path=audit_path,
                bundle_path=bundle_path,
                sender=sender,
            )
        if capture.get("status") != "downloaded":
            capture = self.advance_capture(capture_job_id)
            if capture.get("status") != "downloaded":
                return {
                    "event": "xiaocao_live_pending",
                    "status": capture.get("status"),
                    "capture_job_id": capture_job_id,
                    "next": "rerun",
                }
        media = self.validate_media(capture_job_id)
        cleanup = self._event(
            "capture_cleanup_completed",
            capture_job_id=capture_job_id,
        )
        if cleanup is None:
            cleanup = self.cleanup_sniffer(capture_job_id=capture_job_id)
        validate_cleanup_evidence(cleanup)
        handoff = self._event(
            "cloud_handoff_published",
            capture_job_id=capture_job_id,
        )
        if handoff is None:
            netdisk = self.netdisk.prepare(media["media_path"])
            if str(netdisk.get("status") or "") not in _TERMINAL_NETDISK:
                netdisk = self.netdisk.advance_opencli(
                    netdisk["job_id"],
                    session=opencli_session,
                    profile=opencli_profile,
                )
            if str(netdisk.get("status") or "") not in _TERMINAL_NETDISK:
                return {
                    "event": "xiaocao_live_upload_pending",
                    "status": netdisk.get("status"),
                    "capture_job_id": capture_job_id,
                    "netdisk_job_id": netdisk["job_id"],
                    "next": "rerun_broadband",
                }
            handoff = self._publish_handoff(
                capture_job_id=capture_job_id,
                media=media,
                netdisk=netdisk,
            )
            return handoff
        netdisk_job_id = str(handoff["netdisk_job_id"])
        state = self.netdisk.status(netdisk_job_id)
        if state.get("status") not in {"transcript_captured", "verified", "decided"}:
            state = self.netdisk.advance_opencli(
                netdisk_job_id,
                session=opencli_session,
                profile=opencli_profile,
            )
        if state.get("status") == "transcript_captured":
            if audit_path is None:
                return {
                    "event": "xiaocao_live_audit_input_required",
                    "status": "transcript_captured",
                    "capture_job_id": capture_job_id,
                    "netdisk_job_id": netdisk_job_id,
                    "transcript_path": state["transcript_path"],
                    "transcript_sha256": state["transcript_sha256"],
                    "video_sha256": state["video_sha256"],
                    "next": "provide_audit_path",
                }
            state = self.netdisk.verify_transcript(
                netdisk_job_id,
                audit_path=audit_path,
            )
        if state.get("status") == "verified":
            if bundle_path is None:
                return {
                    "event": "xiaocao_live_analysis_input_required",
                    "status": "verified",
                    "author": "小草",
                    "author_profile": semantic_author_profile("小草"),
                    "capture_job_id": capture_job_id,
                    "netdisk_job_id": netdisk_job_id,
                    "transcript_path": state["transcript_path"],
                    "transcript_sha256": state["transcript_sha256"],
                    "required_coverage_rows": sorted(REQUIRED_COVERAGE_ROWS),
                    "investment_claim_extraction": (
                        build_claim_extraction_request(
                            state["transcript_path"],
                            evidence_sha256=str(state["transcript_sha256"]),
                        )
                    ),
                    "next": "provide_bundle_path",
                }
            validate_decision_bundle(
                bundle_path,
                transcript_path=Path(state["transcript_path"]),
                transcript_sha256=str(state["transcript_sha256"]),
            )
            if sender is None:
                raise EnrichmentError("Ticket 03 decision sender is required")
            state = self.netdisk.decide(
                netdisk_job_id,
                bundle_path=bundle_path,
                decision_output_dir=self.decision_output,
                sender=sender,
            )
        if state.get("status") == "decided" and bundle_path is not None:
            requested_bundle = Path(bundle_path).expanduser().resolve()
            requested_bundle_sha = _sha256_file(requested_bundle)
            if requested_bundle_sha != state.get("decision_bundle_sha256"):
                validate_decision_bundle(
                    requested_bundle,
                    transcript_path=Path(state["transcript_path"]),
                    transcript_sha256=str(state["transcript_sha256"]),
                )
                if sender is None:
                    raise EnrichmentError(
                        "Ticket 03 decision revision sender is required"
                    )
                state = self.netdisk.decide(
                    netdisk_job_id,
                    bundle_path=requested_bundle,
                    decision_output_dir=self.decision_output,
                    sender=sender,
                )
        if state.get("status") != "decided":
            return {
                "event": "xiaocao_live_coordinator_pending",
                "status": state.get("status"),
                "capture_job_id": capture_job_id,
                "netdisk_job_id": netdisk_job_id,
                "coordinator_large_payload_local_bytes": 0,
                "next": "rerun_coordinator",
            }
        decided = next(
            (
                row
                for row in reversed(self.events())
                if row.get("capture_job_id") == capture_job_id
                and row.get("event")
                in {
                    "xiaocao_live_decided",
                    "xiaocao_live_decision_revised",
                }
            ),
            None,
        )
        if decided is None:
            decided = self._append(
                "xiaocao_live_decided",
                status="decided",
                capture_job_id=capture_job_id,
                live_id=media["live_id"],
                media_sha256=media["media_sha256"],
                netdisk_job_id=netdisk_job_id,
                transcript_sha256=state["transcript_sha256"],
                decision_result_sha256=state["decision_result_sha256"],
                coordinator_large_payload_local_bytes=0,
                next="acceptance_audit",
            )
        elif (
            decided.get("decision_result_sha256")
            != state.get("decision_result_sha256")
        ):
            decided = self._append(
                "xiaocao_live_decision_revised",
                status="decided",
                capture_job_id=capture_job_id,
                live_id=media["live_id"],
                media_sha256=media["media_sha256"],
                netdisk_job_id=netdisk_job_id,
                transcript_sha256=state["transcript_sha256"],
                decision_result_sha256=state["decision_result_sha256"],
                coordinator_large_payload_local_bytes=0,
                next="acceptance_audit",
            )
        return self.audit_acceptance(capture_job_id)

    def _audit_imported_acceptance(
        self,
        capture_job_id: str,
        handoff: dict[str, Any],
    ) -> dict[str, Any]:
        """Audit only the remote-owned side of one immutable handoff."""
        existing = self._event(
            "xiaocao_live_handoff_acceptance_ready",
            capture_job_id=capture_job_id,
        )
        netdisk_job_id = str(handoff.get("netdisk_job_id") or "")
        netdisk_state = self.netdisk.status(netdisk_job_id)
        if (
            existing is not None
            and existing.get("decision_result_sha256")
            == netdisk_state.get("decision_result_sha256")
        ):
            return {**existing, "idempotent_replay": True}

        transcript_path = Path(
            str(netdisk_state.get("transcript_path") or "")
        ).expanduser().resolve()
        transcript_sha = str(netdisk_state.get("transcript_sha256") or "")
        transcript_characters = int(
            netdisk_state.get("transcript_character_count") or 0
        )
        if (
            netdisk_state.get("status") != "decided"
            or netdisk_state.get("video_sha256") != handoff.get("media_sha256")
            or not transcript_path.is_file()
            or not _SHA256.fullmatch(transcript_sha)
            or _sha256_file(transcript_path) != transcript_sha
            or transcript_characters < 1000
            or int(netdisk_state.get("ai_note_template_no") or -1) != 1
            or not str(netdisk_state.get("ai_note_triggered_at") or "").strip()
            or netdisk_state.get("ai_note_completion_required") is not False
        ):
            raise EnrichmentError(
                "Ticket 03 remote transcript or AI-note proof is incomplete"
            )

        bundle_path = Path(
            str(netdisk_state.get("decision_bundle_path") or "")
        ).expanduser().resolve()
        if (
            not bundle_path.is_file()
            or _sha256_file(bundle_path)
            != netdisk_state.get("decision_bundle_sha256")
        ):
            raise EnrichmentError("Ticket 03 remote decision bundle receipt changed")
        bundle = validate_decision_bundle(
            bundle_path,
            transcript_path=transcript_path,
            transcript_sha256=transcript_sha,
        )
        bundle_item = bundle["items"][0]

        result_path = Path(
            str(netdisk_state.get("decision_result_path") or "")
        ).expanduser().resolve()
        if (
            not result_path.is_file()
            or _sha256_file(result_path)
            != netdisk_state.get("decision_result_sha256")
        ):
            raise EnrichmentError("Ticket 03 remote decision result receipt changed")
        decision_result = _read_json(result_path)
        result_items = decision_result.get("items")
        if (
            not isinstance(result_items, list)
            or len(result_items) != 1
            or not isinstance(result_items[0], dict)
        ):
            raise EnrichmentError("Ticket 03 remote decision result is incomplete")
        result_item = result_items[0]
        if (
            not isinstance(result_item.get("claims"), list)
            or not result_item.get("claims")
            or not str(result_item.get("synthesis") or "").strip()
            or not isinstance(result_item.get("market_validation"), dict)
            or not isinstance(result_item.get("market_outlook"), dict)
            or not isinstance(result_item.get("household_recommendation"), dict)
        ):
            raise EnrichmentError(
                "Ticket 03 remote judgment or advice layer is missing"
            )

        household = netdisk_state.get("household_notification")
        book = netdisk_state.get("book_kol_us")
        if (
            not isinstance(household, dict)
            or household.get("status") != "delivered"
            or not _SHA256.fullmatch(
                str(household.get("idempotency_key") or "")
            )
            or not isinstance(book, dict)
            or book.get("book") != "KOL-US"
            or book.get("paper_only") is not True
            or book.get("status") not in {"filled", "no_trade"}
            or not _SHA256.fullmatch(str(book.get("idempotency_key") or ""))
            or (
                book.get("status") == "no_trade"
                and not str(book.get("reason") or "").strip()
            )
        ):
            raise EnrichmentError("Ticket 03 remote dual-output receipts are incomplete")

        netdisk_events = [
            row
            for row in self.netdisk.store.read()
            if row.get("job_id") == netdisk_job_id
        ]
        decision_events = _read_jsonl(self.decision_output / "events.jsonl")
        notification_key = str(household["idempotency_key"])
        book_key = str(book["idempotency_key"])
        notification_claims = [
            row
            for row in decision_events
            if row.get("event") == "notification_send_claimed"
            and row.get("idempotency_key") == notification_key
        ]
        notification_receipts = [
            row
            for row in decision_events
            if row.get("event") == "notification_delivered"
            and row.get("idempotency_key") == notification_key
        ]
        paper_rows = [
            row
            for row in _read_jsonl(
                self.decision_output / "book_kol_us" / "decisions.jsonl"
            )
            if row.get("idempotency_key") == book_key
        ]
        side_effect_counts = {
            "handoff_import": sum(
                row.get("event") == "cloud_handoff_imported"
                and row.get("capture_job_id") == capture_job_id
                for row in self.events()
            ),
            "transcript_request": sum(
                row.get("event") == "netdisk_transcript_requested"
                for row in netdisk_events
            ),
            "ai_note_request": sum(
                row.get("event") == "netdisk_ai_note_triggered"
                for row in netdisk_events
            ),
            "household_notification": len(notification_receipts),
            "book_kol_us": len(paper_rows),
        }
        if (
            side_effect_counts
            != {
                "handoff_import": 1,
                "transcript_request": 1,
                "ai_note_request": 1,
                "household_notification": 1,
                "book_kol_us": 1,
            }
            or len(notification_claims) != 1
            or sum(
                row.get("event") == "netdisk_decisions_completed"
                for row in netdisk_events
            )
            != 1
        ):
            raise EnrichmentError(
                "Ticket 03 remote side effects are not exactly once"
            )

        handoff_event = self._event(
            "cloud_handoff_imported",
            capture_job_id=capture_job_id,
        )
        assert handoff_event is not None
        acceptance = {
            "schema_version": 1,
            "ticket": "03-xiaocao-live-to-decisions",
            "scope": "post_handoff",
            "status": "awaiting_user_confirmation",
            "upstream_attestation": {
                "capture_job_id": capture_job_id,
                "live_id": handoff.get("live_id"),
                "handoff_id": handoff["handoff_id"],
                "handoff_self_sha256": handoff["handoff_sha256"],
                "media_basename": handoff["media_basename"],
                "media_sha256": handoff["media_sha256"],
                "media_size_bytes": handoff["media_size_bytes"],
                "media_duration_seconds": handoff["media_duration_seconds"],
                "cloud_reference": handoff["cloud_reference"],
                "large_payload_local_bytes": 0,
            },
            "enrichment": {
                "provider": netdisk_state.get("provider"),
                "netdisk_job_id": netdisk_job_id,
                "transcript_sha256": transcript_sha,
                "transcript_character_count": transcript_characters,
                "audit_sha256": netdisk_state.get("audit_sha256"),
                "ai_note_template_no": 1,
                "ai_note_completion_required": False,
                "decision_bundle_sha256": netdisk_state.get(
                    "decision_bundle_sha256"
                ),
                "decision_result_sha256": netdisk_state.get(
                    "decision_result_sha256"
                ),
            },
            "decision_quality": {
                "decision_status": bundle_item["decision_status"],
                "knowledge_status": bundle_item["knowledge_status"],
                "market_first": True,
                "source_claims_separate_from_system_judgment": True,
                "current_market_validation_separate": True,
                "trade_information_coverage": bundle_item[
                    "trade_information_coverage"
                ],
            },
            "outputs": {
                "household_status": "delivered",
                "household_advisory_only": True,
                "household_idempotency_key": notification_key,
                "book": "KOL-US",
                "book_paper_only": True,
                "book_status": book["status"],
                "book_no_trade_reason": (
                    str(book.get("reason") or "")
                    if book["status"] == "no_trade"
                    else None
                ),
                "book_idempotency_key": book_key,
            },
            "side_effect_counts": side_effect_counts,
            "rerun_external_side_effect_count": 0,
            "created_at": self._clock().isoformat(timespec="seconds"),
        }
        acceptance_path = (
            self.output_dir
            / "acceptance"
            / f"{capture_job_id}.post-handoff.json"
        )
        _atomic_json(acceptance_path, acceptance)
        return self._append(
            "xiaocao_live_handoff_acceptance_ready",
            status="awaiting_user_confirmation",
            scope="post_handoff",
            capture_job_id=capture_job_id,
            live_id=str(handoff.get("live_id") or ""),
            media_sha256=str(handoff["media_sha256"]),
            handoff_id=str(handoff["handoff_id"]),
            handoff_file_sha256=handoff_event["handoff_file_sha256"],
            netdisk_job_id=netdisk_job_id,
            transcript_sha256=transcript_sha,
            decision_result_sha256=netdisk_state["decision_result_sha256"],
            acceptance_evidence_path=str(acceptance_path),
            acceptance_evidence_sha256=_sha256_file(acceptance_path),
            new_external_side_effect_count=0,
            idempotent_replay=False,
            next="user_confirmation",
        )

    def audit_acceptance(self, capture_job_id: str) -> dict[str, Any]:
        """Prove the completed real chain without replaying any side effect."""
        imported_handoff = self._imported_handoff(capture_job_id)
        if (
            self.capture_store.latest(capture_job_id) is None
            and imported_handoff is not None
        ):
            return self._audit_imported_acceptance(
                capture_job_id,
                imported_handoff,
            )
        existing = self._event(
            "xiaocao_live_acceptance_ready",
            capture_job_id=capture_job_id,
        )
        if existing is not None:
            existing_netdisk_job_id = str(
                existing.get("netdisk_job_id") or ""
            )
            if existing_netdisk_job_id:
                current_netdisk = self.netdisk.status(
                    existing_netdisk_job_id
                )
                if (
                    existing.get("decision_result_sha256")
                    == current_netdisk.get("decision_result_sha256")
                ):
                    return {**existing, "idempotent_replay": True}
        decided = self._event(
            "xiaocao_live_decided",
            capture_job_id=capture_job_id,
        )
        if decided is None:
            raise EnrichmentError("Ticket 03 real chain has not reached decisions")

        media = self.validate_media(capture_job_id)
        cleanup = self._event(
            "capture_cleanup_completed",
            capture_job_id=capture_job_id,
        )
        handoff_event = self._event(
            "cloud_handoff_published",
            capture_job_id=capture_job_id,
        )
        if cleanup is None or handoff_event is None:
            raise EnrichmentError("Ticket 03 cleanup or handoff receipt is missing")
        validate_cleanup_evidence(cleanup)
        if cleanup.get("capture_job_id") != capture_job_id:
            raise EnrichmentError("Ticket 03 cleanup is bound to another capture")

        cleanup_path = Path(
            str(cleanup.get("cleanup_evidence_path") or "")
        ).expanduser().resolve()
        handoff_path = Path(
            str(handoff_event.get("handoff_path") or "")
        ).expanduser().resolve()
        if (
            not cleanup_path.is_file()
            or _sha256_file(cleanup_path)
            != cleanup.get("cleanup_evidence_sha256")
            or not handoff_path.is_file()
            or _sha256_file(handoff_path) != handoff_event.get("handoff_sha256")
        ):
            raise EnrichmentError("Ticket 03 local receipt hash changed")
        handoff = _read_json(handoff_path)
        handoff_self_hash = str(handoff.get("handoff_sha256") or "")
        handoff_without_hash = dict(handoff)
        handoff_without_hash.pop("handoff_sha256", None)
        if (
            handoff.get("capture_job_id") != capture_job_id
            or handoff.get("live_id") != media.get("live_id")
            or handoff.get("media_sha256") != media.get("media_sha256")
            or handoff.get("large_payload_local_bytes") != 0
            or handoff_event.get("coordinator_large_payload_local_bytes") != 0
            or "media_path" in handoff
            or "video_path" in handoff
            or handoff_self_hash != _sha256_text(_canonical(handoff_without_hash))
        ):
            raise EnrichmentError("Ticket 03 lightweight handoff is invalid")

        netdisk_job_id = str(handoff.get("netdisk_job_id") or "")
        netdisk_state = self.netdisk.status(netdisk_job_id)
        netdisk_events = [
            row
            for row in self.netdisk.store.read()
            if row.get("job_id") == netdisk_job_id
        ]
        browser_events = [
            row
            for row in netdisk_events
            if row.get("event")
            in {
                "netdisk_browser_liveness_ready",
                "netdisk_upload_claimed",
                "netdisk_video_ready",
            }
        ]
        if not browser_events:
            raise EnrichmentError("Ticket 03 browser chronology is missing")
        cleanup_at = _evidence_time(
            cleanup.get("observed_at"),
            field="cleanup.observed_at",
        )
        first_browser_at = min(
            _evidence_time(row.get("updated_at"), field="netdisk.updated_at")
            for row in browser_events
        )
        if cleanup_at > first_browser_at:
            raise EnrichmentError(
                "Ticket 03 Netdisk action began before capture cleanup completed"
            )

        transcript_path = Path(
            str(netdisk_state.get("transcript_path") or "")
        ).expanduser().resolve()
        transcript_sha = str(netdisk_state.get("transcript_sha256") or "")
        transcript_characters = int(
            netdisk_state.get("transcript_character_count") or 0
        )
        if (
            netdisk_state.get("status") != "decided"
            or netdisk_state.get("video_sha256") != media.get("media_sha256")
            or not transcript_path.is_file()
            or not _SHA256.fullmatch(transcript_sha)
            or _sha256_file(transcript_path) != transcript_sha
            or transcript_characters < 1000
            or int(netdisk_state.get("ai_note_template_no") or -1) != 1
            or not str(netdisk_state.get("ai_note_triggered_at") or "").strip()
            or netdisk_state.get("ai_note_completion_required") is not False
        ):
            raise EnrichmentError(
                "Ticket 03 transcript or independent AI-note proof is incomplete"
            )

        bundle_path = Path(
            str(netdisk_state.get("decision_bundle_path") or "")
        ).expanduser().resolve()
        if (
            not bundle_path.is_file()
            or _sha256_file(bundle_path)
            != netdisk_state.get("decision_bundle_sha256")
        ):
            raise EnrichmentError("Ticket 03 decision bundle receipt changed")
        bundle = validate_decision_bundle(
            bundle_path,
            transcript_path=transcript_path,
            transcript_sha256=transcript_sha,
        )
        bundle_item = bundle["items"][0]

        result_path = Path(
            str(netdisk_state.get("decision_result_path") or "")
        ).expanduser().resolve()
        if (
            not result_path.is_file()
            or _sha256_file(result_path)
            != netdisk_state.get("decision_result_sha256")
        ):
            raise EnrichmentError("Ticket 03 decision result receipt changed")
        decision_result = _read_json(result_path)
        result_items = decision_result.get("items")
        if (
            not isinstance(result_items, list)
            or len(result_items) != 1
            or not isinstance(result_items[0], dict)
        ):
            raise EnrichmentError("Ticket 03 decision result is incomplete")
        result_item = result_items[0]
        if (
            not isinstance(result_item.get("claims"), list)
            or not result_item.get("claims")
            or not str(result_item.get("synthesis") or "").strip()
            or not isinstance(result_item.get("market_validation"), dict)
            or not isinstance(result_item.get("market_outlook"), dict)
            or not isinstance(result_item.get("household_recommendation"), dict)
        ):
            raise EnrichmentError(
                "Ticket 03 claim, judgment, validation, or advice layer is missing"
            )

        household = netdisk_state.get("household_notification")
        book = netdisk_state.get("book_kol_us")
        if (
            not isinstance(household, dict)
            or household.get("status") != "delivered"
            or not _SHA256.fullmatch(
                str(household.get("idempotency_key") or "")
            )
            or not isinstance(book, dict)
            or book.get("book") != "KOL-US"
            or book.get("paper_only") is not True
            or book.get("status") not in {"filled", "no_trade"}
            or not _SHA256.fullmatch(str(book.get("idempotency_key") or ""))
            or (
                book.get("status") == "no_trade"
                and not str(book.get("reason") or "").strip()
            )
        ):
            raise EnrichmentError("Ticket 03 dual-output receipts are incomplete")

        decision_events = _read_jsonl(self.decision_output / "events.jsonl")
        notification_key = str(household["idempotency_key"])
        book_key = str(book["idempotency_key"])
        notification_claims = [
            row
            for row in decision_events
            if row.get("event") == "notification_send_claimed"
            and row.get("idempotency_key") == notification_key
        ]
        notification_receipts = [
            row
            for row in decision_events
            if row.get("event") == "notification_delivered"
            and row.get("idempotency_key") == notification_key
        ]
        paper_rows = [
            row
            for row in _read_jsonl(
                self.decision_output / "book_kol_us" / "decisions.jsonl"
            )
            if row.get("idempotency_key") == book_key
        ]
        capture_rows = [
            row
            for row in self.capture_store.events()
            if row.get("job_id") == capture_job_id
        ]
        side_effect_counts = {
            "capture": sum(
                row.get("event") == "capture_detected" for row in capture_rows
            ),
            "upload": sum(
                row.get("event") == "netdisk_upload_started"
                for row in netdisk_events
            ),
            "transcript_request": sum(
                row.get("event") == "netdisk_transcript_requested"
                for row in netdisk_events
            ),
            "ai_note_request": sum(
                row.get("event") == "netdisk_ai_note_triggered"
                for row in netdisk_events
            ),
            "household_notification": len(notification_receipts),
            "book_kol_us": len(paper_rows),
        }
        if (
            side_effect_counts
            != {
                "capture": 1,
                "upload": 1,
                "transcript_request": 1,
                "ai_note_request": 1,
                "household_notification": 1,
                "book_kol_us": 1,
            }
            or len(notification_claims) != 1
            or sum(
                row.get("event") == "netdisk_decisions_completed"
                for row in netdisk_events
            )
            != 1
            or sum(
                row.get("event") == "cloud_handoff_published"
                and row.get("capture_job_id") == capture_job_id
                for row in self.events()
            )
            != 1
        ):
            raise EnrichmentError("Ticket 03 side effects are not exactly once")

        acceptance = {
            "schema_version": 1,
            "ticket": "03-xiaocao-live-to-decisions",
            "status": "awaiting_user_confirmation",
            "capture": {
                "capture_job_id": capture_job_id,
                "live_id": media["live_id"],
                "media_basename": media["media_basename"],
                "media_sha256": media["media_sha256"],
                "media_size_bytes": media["media_size_bytes"],
                "media_duration_seconds": media["media_duration_seconds"],
                "raw_source_retained": False,
            },
            "cleanup": {
                "observed_at": cleanup["observed_at"],
                "evidence_sha256": cleanup["cleanup_evidence_sha256"],
                "completed_before_first_netdisk_browser_action": True,
            },
            "handoff": {
                "handoff_sha256": handoff_event["handoff_sha256"],
                "netdisk_job_id": netdisk_job_id,
                "coordinator_large_payload_local_bytes": 0,
            },
            "enrichment": {
                "provider": netdisk_state.get("provider"),
                "transcript_sha256": transcript_sha,
                "transcript_character_count": transcript_characters,
                "audit_sha256": netdisk_state.get("audit_sha256"),
                "ai_note_template_no": 1,
                "ai_note_completion_required": False,
                "decision_bundle_sha256": netdisk_state.get(
                    "decision_bundle_sha256"
                ),
                "decision_result_sha256": netdisk_state.get(
                    "decision_result_sha256"
                ),
            },
            "decision_quality": {
                "decision_status": bundle_item["decision_status"],
                "knowledge_status": bundle_item["knowledge_status"],
                "market_first": True,
                "source_claims_separate_from_system_judgment": True,
                "current_market_validation_separate": True,
                "trade_information_coverage": bundle_item[
                    "trade_information_coverage"
                ],
            },
            "outputs": {
                "household_status": "delivered",
                "household_advisory_only": True,
                "household_idempotency_key": notification_key,
                "book": "KOL-US",
                "book_paper_only": True,
                "book_status": book["status"],
                "book_no_trade_reason": (
                    str(book.get("reason") or "")
                    if book["status"] == "no_trade"
                    else None
                ),
                "book_idempotency_key": book_key,
            },
            "side_effect_counts": side_effect_counts,
            "rerun_external_side_effect_count": 0,
            "user_interaction": {
                "playback_prompt_count": 1,
                "steps": [
                    "open_target_enterprise_wechat_card",
                    "enter_password_if_required",
                    "play",
                ],
                "active_time_target_minutes": 5,
            },
            "created_at": self._clock().isoformat(timespec="seconds"),
        }
        acceptance_name = f"{capture_job_id}.json"
        if existing is not None:
            acceptance_name = (
                f"{capture_job_id}."
                f"{str(netdisk_state['decision_result_sha256'])[:16]}.json"
            )
        acceptance_path = self.output_dir / "acceptance" / acceptance_name
        _atomic_json(acceptance_path, acceptance)
        return self._append(
            "xiaocao_live_acceptance_ready",
            status="awaiting_user_confirmation",
            capture_job_id=capture_job_id,
            live_id=media["live_id"],
            media_sha256=media["media_sha256"],
            netdisk_job_id=netdisk_job_id,
            transcript_sha256=transcript_sha,
            decision_result_sha256=netdisk_state["decision_result_sha256"],
            acceptance_evidence_path=str(acceptance_path),
            acceptance_evidence_sha256=_sha256_file(acceptance_path),
            new_external_side_effect_count=0,
            idempotent_replay=False,
            next="user_confirmation",
        )

    def reconcile_existing(
        self,
        capture_job_id: str,
        *,
        cleanup_evidence_path: Path | str,
        acceptance_evidence_path: Path | str,
    ) -> dict[str, Any]:
        """Bind historical real receipts without replaying an external action."""
        media = self.validate_media(capture_job_id)
        cleanup_path = Path(cleanup_evidence_path).expanduser().resolve()
        cleanup = _read_json(cleanup_path)
        validate_cleanup_evidence(cleanup)
        acceptance_path = Path(acceptance_evidence_path).expanduser().resolve()
        acceptance = _read_json(acceptance_path)
        capture = acceptance.get("capture")
        enrichment = acceptance.get("enrichment")
        outputs = acceptance.get("outputs")
        if not all(isinstance(value, dict) for value in (capture, enrichment, outputs)):
            raise EnrichmentError("Ticket 03 acceptance evidence is incomplete")
        if (
            capture.get("capture_job_id") != capture_job_id
            or capture.get("live_id") != media["live_id"]
            or capture.get("media_sha256") != media["media_sha256"]
            or capture.get("media_size_bytes") != media["media_size_bytes"]
            or capture.get("media_duration_seconds") != media["media_duration_seconds"]
        ):
            raise EnrichmentError("Ticket 03 capture acceptance binding failed")
        netdisk_job_id = str(enrichment.get("netdisk_job_id") or "")
        state = self.netdisk.status(netdisk_job_id)
        browser_events = [
            row
            for row in self.netdisk.store.read()
            if row.get("job_id") == netdisk_job_id
            and row.get("event")
            in {
                "netdisk_browser_liveness_ready",
                "netdisk_upload_claimed",
                "netdisk_video_ready",
            }
        ]
        if not browser_events:
            raise EnrichmentError("Ticket 03 browser-action chronology is missing")
        cleanup_at = _evidence_time(
            cleanup.get("observed_at"),
            field="cleanup.observed_at",
        )
        first_browser_at = min(
            _evidence_time(row.get("updated_at"), field="netdisk.updated_at")
            for row in browser_events
        )
        if cleanup_at > first_browser_at:
            raise EnrichmentError(
                "Ticket 03 Netdisk action began before capture cleanup completed"
            )
        if (
            state.get("status") != "decided"
            or state.get("video_sha256") != media["media_sha256"]
            or state.get("transcript_sha256") != enrichment.get("transcript_sha256")
            or state.get("audit_sha256") != enrichment.get("audit_sha256")
            or state.get("decision_result_sha256")
            != outputs.get("decision_result_sha256")
        ):
            raise EnrichmentError("Ticket 03 enrichment/output binding failed")
        transcript = Path(str(state.get("transcript_path") or "")).resolve()
        if (
            not transcript.is_file()
            or _sha256_file(transcript) != state.get("transcript_sha256")
        ):
            raise EnrichmentError("Ticket 03 complete transcript is missing or changed")
        validation_item = acceptance.get("decision_quality")
        if not isinstance(validation_item, dict):
            raise EnrichmentError("Ticket 03 decision-quality evidence is missing")
        validate_coverage_matrix(
            validation_item,
            evidence_text=transcript.read_text(encoding="utf-8"),
        )
        household = state.get("household_notification")
        book = state.get("book_kol_us")
        if (
            not isinstance(household, dict)
            or household.get("status") != "delivered"
            or household.get("idempotency_key")
            != outputs.get("household_idempotency_key")
            or not isinstance(book, dict)
            or book.get("book") != "KOL-US"
            or book.get("paper_only") is not True
            or book.get("idempotency_key") != outputs.get("book_idempotency_key")
            or (
                book.get("status") == "no_trade"
                and not str(book.get("reason") or "").strip()
            )
        ):
            raise EnrichmentError("Ticket 03 dual-output receipts are incomplete")
        if acceptance.get("side_effect_counts") != {
            "capture": 1,
            "upload": 1,
            "transcript_request": 1,
            "ai_note_request": 1,
            "household_notification": 1,
            "book_kol_us": 1,
        }:
            raise EnrichmentError("Ticket 03 side-effect counts are not exactly once")
        existing = self._event(
            "xiaocao_live_acceptance_reconciled",
            capture_job_id=capture_job_id,
        )
        if existing is not None:
            return {**existing, "idempotent_replay": True}
        handoff = {
            "schema_version": 1,
            "capture_job_id": capture_job_id,
            "live_id": media["live_id"],
            "media_basename": media["media_basename"],
            "media_sha256": media["media_sha256"],
            "netdisk_job_id": netdisk_job_id,
            "cloud_reference": (
                "baidu:/课程/自己的课/小草/" + media["media_basename"]
            ),
            "large_payload_local_bytes": 0,
            "reconciled_at": self._clock().isoformat(timespec="seconds"),
        }
        handoff_path = self.output_dir / "handoffs" / f"{capture_job_id}.json"
        _atomic_json(handoff_path, handoff)
        return self._append(
            "xiaocao_live_acceptance_reconciled",
            status="awaiting_user_confirmation",
            capture_job_id=capture_job_id,
            live_id=media["live_id"],
            media_sha256=media["media_sha256"],
            netdisk_job_id=netdisk_job_id,
            transcript_sha256=state["transcript_sha256"],
            decision_result_sha256=state["decision_result_sha256"],
            cleanup_evidence_sha256=_sha256_file(cleanup_path),
            acceptance_evidence_sha256=_sha256_file(acceptance_path),
            handoff_sha256=_sha256_file(handoff_path),
            coordinator_large_payload_local_bytes=0,
            new_external_side_effect_count=0,
            idempotent_replay=False,
            next="user_confirmation",
        )

    def confirm(self, *, confirmation: str) -> dict[str, Any]:
        current = self.latest()
        if (
            current is None
            or current.get("status") not in {
                "awaiting_user_confirmation",
                "completed",
            }
        ):
            raise EnrichmentError("Ticket 03 has no acceptance awaiting confirmation")
        if current.get("status") == "completed":
            return {**current, "idempotent_replay": True}
        if confirmation != "target_live_and_decision_value_confirmed":
            raise EnrichmentError("Ticket 03 confirmation value is invalid")
        return self._append(
            "xiaocao_live_completed",
            status="completed",
            capture_job_id=current["capture_job_id"],
            live_id=current["live_id"],
            media_sha256=current["media_sha256"],
            netdisk_job_id=current["netdisk_job_id"],
            transcript_sha256=current["transcript_sha256"],
            decision_result_sha256=current["decision_result_sha256"],
            user_confirmation=confirmation,
            new_external_side_effect_count=0,
            next="none",
        )
