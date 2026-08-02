"""Deterministic, resumable video enrichment for KOL evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import wraps
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from .enrichment_types import (
    EnrichmentError,
    validate_decision_completion,
    validate_decision_process_result,
)
from .enrichment_store import EnrichmentJobStore
from .runtime_paths import resolve_repo_owned_path


class ProviderRejected(EnrichmentError):
    """The provider explicitly rejected a request before accepting a task."""


class ProviderOutcomeUncertain(EnrichmentError):
    """The provider call may have succeeded but returned no durable identity."""


def _job_locked(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def wrapper(self: "VideoEnrichmentService", job_id: str, *args: Any, **kwargs: Any) -> Any:
        with self._job_lock(job_id):
            return method(self, job_id, *args, **kwargs)

    return wrapper


@dataclass(frozen=True)
class PublishedAudio:
    publication_reference: str
    speech_url: str = field(repr=False)


class S3AudioPublisher:
    """Publish one prepared audio object and verify its content hash."""

    def __init__(
        self,
        *,
        runner: Callable[..., Any] = subprocess.run,
        expires_in_seconds: int = 24 * 60 * 60,
    ):
        self.runner = runner
        self.expires_in_seconds = expires_in_seconds

    def _run(self, command: list[str]) -> Any:
        result = self.runner(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise EnrichmentError(
                f"object publication command failed ({command[1]}): "
                f"{str(result.stderr).strip()}"
            )
        return result

    def publish(
        self,
        audio_path: Path | str,
        *,
        s3_prefix: str,
        audio_sha256: str,
    ) -> PublishedAudio:
        audio = Path(audio_path).expanduser().resolve()
        if not audio.is_file() or _sha256_file(audio) != audio_sha256:
            raise EnrichmentError("audio object source is missing or changed")
        parsed = urlsplit(str(s3_prefix))
        if (
            parsed.scheme != "s3"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.hostname != parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise EnrichmentError("S3 prefix must be a stable s3://bucket/path reference")
        prefix = parsed.path.strip("/")
        key_parts = [part for part in (prefix, audio_sha256[:16], audio.name) if part]
        key = "/".join(key_parts)
        reference = f"s3://{parsed.netloc}/{key}"
        public_access = self._run([
            "aws",
            "s3api",
            "get-public-access-block",
            "--bucket",
            parsed.netloc,
            "--query",
            "PublicAccessBlockConfiguration",
            "--output",
            "json",
        ])
        try:
            public_access_policy = json.loads(public_access.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise EnrichmentError("S3 public-access policy response is invalid") from exc
        required_public_blocks = {
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        }
        if not all(public_access_policy.get(key) is True for key in required_public_blocks):
            raise EnrichmentError("audio bucket requires full S3 public-access block")
        self._run([
            "aws",
            "s3",
            "cp",
            str(audio),
            reference,
            "--only-show-errors",
            "--metadata",
            f"xiaocao-sha256={audio_sha256}",
        ])
        head = self._run([
            "aws",
            "s3api",
            "head-object",
            "--bucket",
            parsed.netloc,
            "--key",
            key,
            "--query",
            "Metadata.xiaocao-sha256",
            "--output",
            "text",
        ])
        if str(head.stdout).strip() != audio_sha256:
            raise EnrichmentError("published audio hash metadata does not match local evidence")
        public_grants = self._run([
            "aws",
            "s3api",
            "get-object-acl",
            "--bucket",
            parsed.netloc,
            "--key",
            key,
            "--query",
            "Grants[?Grantee.URI!=null].Grantee.URI",
            "--output",
            "json",
        ])
        try:
            grants = json.loads(public_grants.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise EnrichmentError("S3 object ACL response is invalid") from exc
        if grants != []:
            raise EnrichmentError("published audio object has a public ACL grant")
        presigned = self._run([
            "aws",
            "s3",
            "presign",
            reference,
            "--expires-in",
            str(self.expires_in_seconds),
        ])
        speech_url = str(presigned.stdout).strip()
        url = urlsplit(speech_url)
        if url.scheme != "https" or not url.netloc or not url.path.lower().endswith(".wav"):
            raise EnrichmentError("object publisher did not return an HTTPS .wav URL")
        return PublishedAudio(
            publication_reference=reference,
            speech_url=speech_url,
        )


class BaiduAasrClient:
    """Minimal client for Baidu's complete audio-file transcription API."""

    CREATE_URL = "https://aip.baidubce.com/rpc/2.0/aasr/v1/create"
    QUERY_URL = "https://aip.baidubce.com/rpc/2.0/aasr/v1/query"
    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"

    def __init__(
        self,
        *,
        access_token: str,
        session: Any | None = None,
    ):
        if not str(access_token).strip():
            raise EnrichmentError("Baidu AASR access token is required")
        self._access_token = str(access_token).strip()
        self._session = session or requests.Session()

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        *,
        session: Any | None = None,
    ) -> "BaiduAasrClient":
        values = environ if environ is not None else os.environ
        active_session = session or requests.Session()
        direct = str(values.get("BAIDU_AASR_ACCESS_TOKEN") or "").strip()
        if direct:
            return cls(access_token=direct, session=active_session)
        api_key = str(values.get("BAIDU_AASR_API_KEY") or "").strip()
        secret_key = str(values.get("BAIDU_AASR_SECRET_KEY") or "").strip()
        if not api_key or not secret_key:
            raise EnrichmentError(
                "configure BAIDU_AASR_ACCESS_TOKEN or both BAIDU_AASR_API_KEY "
                "and BAIDU_AASR_SECRET_KEY"
            )
        try:
            response = active_session.post(
                cls.TOKEN_URL,
                params={
                    "grant_type": "client_credentials",
                    "client_id": api_key,
                    "client_secret": secret_key,
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise EnrichmentError("Baidu AASR access-token request failed") from exc
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise EnrichmentError("Baidu AASR access-token response omitted access_token")
        return cls(access_token=token, session=active_session)

    def submit(self, speech_url: str) -> dict[str, str]:
        parsed = urlsplit(str(speech_url))
        if parsed.scheme != "https" or not parsed.netloc or not parsed.path.lower().endswith(".wav"):
            raise EnrichmentError("AASR speech URL must be an HTTPS .wav URL")
        try:
            response = self._session.post(
                self.CREATE_URL,
                params={"access_token": self._access_token},
                json={
                    "speech_url": speech_url,
                    "format": "wav",
                    "pid": 80006,
                    "rate": 16000,
                    "smooth_text": 0,
                    "filter_sensitive": 0,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, OSError) as exc:
            raise ProviderOutcomeUncertain("Baidu AASR create outcome is uncertain") from exc
        except (ValueError, TypeError) as exc:
            raise ProviderOutcomeUncertain("Baidu AASR create returned invalid data") from exc
        if payload.get("error_code") is not None:
            raise ProviderRejected(
                f"Baidu AASR rejected create request: {payload.get('error_msg', 'unknown error')}"
            )
        task_id = str(payload.get("task_id") or "").strip()
        task_status = str(payload.get("task_status") or "").strip()
        if not task_id or task_status != "Created":
            raise ProviderOutcomeUncertain(
                "Baidu AASR create response omitted a durable Created task"
            )
        return {"task_id": task_id, "task_status": task_status}

    def query(self, task_id: str) -> dict[str, Any]:
        identity = str(task_id).strip()
        if not identity:
            raise EnrichmentError("Baidu AASR query requires a task id")
        try:
            response = self._session.post(
                self.QUERY_URL,
                params={"access_token": self._access_token},
                json={"task_ids": [identity]},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, OSError, ValueError, TypeError) as exc:
            raise EnrichmentError("Baidu AASR query request failed") from exc
        if payload.get("error_code") is not None:
            raise EnrichmentError(
                f"Baidu AASR rejected query request: {payload.get('error_msg', 'unknown error')}"
            )
        if not isinstance(payload.get("tasks_info"), list):
            raise EnrichmentError("Baidu AASR query response omitted tasks_info")
        return payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_bytes(content)
    temporary.replace(path)


def _timestamp(milliseconds: int) -> str:
    seconds, millis = divmod(int(milliseconds), 1000)
    minutes, second = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{second:02d}.{millis:03d}"


class VideoEnrichmentService:
    """Public single-video seam for the ticket-02 enrichment state machine."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        runner: Callable[..., Any] = subprocess.run,
        aasr_client: Any | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.store = EnrichmentJobStore(output_dir)
        self.output_dir = self.store.output_dir
        self.events_path = self.store.events_path
        self.lock_dir = self.store.lock_dir
        self.runner = runner
        self.aasr_client = aasr_client
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())

    @contextmanager
    def _job_lock(self, job_id: str):
        with self.store.job_lock(job_id):
            yield

    def _events(self) -> list[dict[str, Any]]:
        return self.store.read()

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        return self.store.append(row)

    def _latest(self, job_id: str) -> dict[str, Any]:
        return self.store.latest(job_id)

    def _runtime_path(self, value: Path | str) -> Path:
        return resolve_repo_owned_path(value, anchor=self.output_dir)

    def status(self, job_id: str | None = None) -> dict[str, Any]:
        return self.store.status(job_id)

    def _run(self, command: list[str]) -> Any:
        result = self.runner(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise EnrichmentError(
                f"external command failed ({command[0]}): {str(result.stderr).strip()}"
            )
        return result

    def _raw_task(
        self, current: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        raw_path = Path(str(current.get("raw_response_path") or ""))
        if (
            not raw_path.is_file()
            or _sha256_file(raw_path) != current.get("raw_response_sha256")
        ):
            raise EnrichmentError("raw AASR response is missing or changed")
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("raw AASR response is invalid JSON") from exc
        task = next(
            (
                row
                for row in raw.get("tasks_info") or []
                if str(row.get("task_id") or "") == current.get("provider_task_id")
            ),
            None,
        )
        if task is None or task.get("task_status") != "Success":
            raise EnrichmentError("raw AASR response does not contain this successful task")
        return raw, task

    @staticmethod
    def _segments(task: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
        result = task.get("task_result") or {}
        try:
            duration_ms = int(result["audio_duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EnrichmentError("AASR result omitted audio_duration") from exc
        rows: list[dict[str, Any]] = []
        prior_begin = -1
        for segment in result.get("detailed_result") or []:
            try:
                begin = int(segment["begin_time"])
                end = int(segment["end_time"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EnrichmentError("AASR segment omitted a valid time range") from exc
            texts = segment.get("res")
            if isinstance(texts, str):
                texts = [texts]
            if (
                begin < prior_begin
                or begin < 0
                or end < begin
                or not isinstance(texts, list)
                or not texts
                or any(not isinstance(text, str) or not text.strip() for text in texts)
            ):
                raise EnrichmentError("AASR detailed_result is not source-ordered complete text")
            rows.append({"begin_time": begin, "end_time": end, "texts": texts})
            prior_begin = begin
        if duration_ms <= 0 or not rows:
            raise EnrichmentError("AASR result has no usable transcript segments")
        if any(segment["end_time"] > duration_ms for segment in rows):
            raise EnrichmentError("AASR segment exceeds audio_duration")
        return duration_ms, rows

    def _probe(self, media_path: Path) -> dict[str, Any]:
        result = self._run([
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,sample_rate,channels,bits_per_sample",
            "-of",
            "json",
            str(media_path),
        ])
        try:
            payload = json.loads(result.stdout)
            audio = next(
                stream
                for stream in payload.get("streams") or []
                if stream.get("codec_type") == "audio"
            )
            duration = float((payload.get("format") or {})["duration"])
        except (json.JSONDecodeError, KeyError, StopIteration, TypeError, ValueError) as exc:
            raise EnrichmentError(f"ffprobe returned invalid media metadata: {media_path}") from exc
        return {"duration_seconds": duration, "audio": audio}

    def prepare(self, video_path: Path | str) -> dict[str, Any]:
        video = Path(video_path).expanduser().resolve()
        if not video.is_file():
            raise EnrichmentError(f"source video not found: {video}")
        if not video.name.endswith("-compressed.mp4"):
            raise EnrichmentError("ticket 02 requires a completed -compressed.mp4 source")
        video_sha256 = _sha256_file(video)
        job_id = f"kol-enrich-{video_sha256[:16]}"
        with self._job_lock(job_id):
            return self._prepare_locked(video, video_sha256, job_id)

    def _prepare_locked(
        self, video: Path, video_sha256: str, job_id: str
    ) -> dict[str, Any]:
        try:
            current = self._latest(job_id)
        except EnrichmentError as exc:
            if "not found" not in str(exc):
                raise
            current = None
        if current:
            if current.get("video_sha256") not in {None, video_sha256}:
                raise EnrichmentError("prepared source hash cannot change")
            audio_path = Path(str(current.get("audio_path") or ""))
            if not audio_path.is_absolute():
                audio_path = (Path.cwd() / audio_path).resolve()
            if (
                audio_path.is_file()
                and _sha256_file(audio_path) == current.get("audio_sha256")
            ):
                normalized = {
                    **current,
                    "video_path": str(video),
                    "video_basename": video.name,
                    "video_sha256": video_sha256,
                    "audio_path": str(audio_path),
                }
                if normalized != current:
                    normalized["updated_at"] = self.now().isoformat(timespec="seconds")
                    self._append(normalized)
                return {**normalized, "idempotent_replay": True}
            if current.get("status") != "prepared":
                raise EnrichmentError(
                    "advanced enrichment cannot regress after prepared audio changed"
                )

        source_probe = self._probe(video)
        artifact_dir = self.output_dir / "artifacts" / job_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        audio_path = artifact_dir / f"{video.stem}.wav"
        temporary_audio = artifact_dir / f".{video.stem}.partial.wav"
        if temporary_audio.exists():
            temporary_audio.unlink()
        self._run([
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(temporary_audio),
        ])
        if not temporary_audio.is_file():
            raise EnrichmentError("ffmpeg returned success without an audio artifact")
        temporary_audio.replace(audio_path)
        audio_probe = self._probe(audio_path)
        audio = audio_probe["audio"]
        audio_spec = {
            "codec_name": audio.get("codec_name"),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "channels": int(audio.get("channels") or 0),
            "bits_per_sample": int(audio.get("bits_per_sample") or 0),
        }
        if audio_spec != {
            "codec_name": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
            "bits_per_sample": 16,
        }:
            raise EnrichmentError(f"prepared audio does not meet the AASR contract: {audio_spec}")
        row = {
            "schema_version": 1,
            "event": "audio_prepared",
            "status": "prepared",
            "job_id": job_id,
            "provider": "baidu_aasr",
            "video_path": str(video),
            "video_basename": video.name,
            "video_sha256": video_sha256,
            "video_size_bytes": video.stat().st_size,
            "video_duration_seconds": source_probe["duration_seconds"],
            "audio_path": str(audio_path),
            "audio_sha256": _sha256_file(audio_path),
            "audio_size_bytes": audio_path.stat().st_size,
            "audio_duration_seconds": audio_probe["duration_seconds"],
            "audio_spec": audio_spec,
            "created_at": _now_iso(),
        }
        self._append(row)
        return {**row, "idempotent_replay": False}

    @_job_locked
    def submit(
        self,
        job_id: str,
        *,
        speech_url: str,
        publication_reference: str,
    ) -> dict[str, Any]:
        current = self._latest(job_id)
        if current.get("provider_task_id"):
            return {**current, "idempotent_replay": True}
        if current.get("status") == "submit_uncertain":
            raise EnrichmentError(
                "prior AASR submission outcome is uncertain; reconcile it before retrying"
            )
        if current.get("status") not in {"prepared", "published"}:
            raise EnrichmentError("only a prepared or published job can be submitted")
        audio_path = Path(str(current.get("audio_path") or ""))
        if (
            not audio_path.is_file()
            or _sha256_file(audio_path) != current.get("audio_sha256")
        ):
            raise EnrichmentError("prepared audio is missing or changed")
        if self.aasr_client is None:
            raise EnrichmentError("Baidu AASR client is not configured")
        reference = str(publication_reference).strip()
        parsed_reference = urlsplit(reference)
        if (
            not parsed_reference.scheme
            or not parsed_reference.netloc
            or parsed_reference.username is not None
            or parsed_reference.password is not None
            or parsed_reference.query
            or parsed_reference.fragment
        ):
            raise EnrichmentError("publication reference must be stable and secret-free")
        submitted_at = self.now()
        if submitted_at.tzinfo is None:
            raise EnrichmentError("enrichment clock must include a timezone")
        if current.get("status") == "published":
            if current.get("publication_reference") != reference:
                raise EnrichmentError("published audio reference cannot change during submit")
        else:
            current = self._append({
                **current,
                "event": "audio_published",
                "status": "published",
                "publication_reference": reference,
                "updated_at": submitted_at.isoformat(timespec="seconds"),
            })
        claimed = self._append({
            **current,
            "event": "transcription_submit_claimed",
            "status": "submit_claimed",
            "submission_claimed_at": submitted_at.isoformat(timespec="seconds"),
            "updated_at": submitted_at.isoformat(timespec="seconds"),
        })
        try:
            provider = self.aasr_client.submit(speech_url)
        except ProviderRejected as exc:
            self._append({
                **current,
                "event": "transcription_submit_rejected",
                "status": "published",
                "provider_error": str(exc),
                "updated_at": self.now().isoformat(timespec="seconds"),
            })
            raise
        except EnrichmentError as exc:
            self._append({
                **claimed,
                "event": "transcription_submit_uncertain",
                "status": "submit_uncertain",
                "provider_error": str(exc),
                "updated_at": self.now().isoformat(timespec="seconds"),
            })
            raise
        row = {
            **claimed,
            "event": "transcription_submitted",
            "status": "submitted",
            "provider_task_id": provider["task_id"],
            "provider_task_status": provider["task_status"],
            "publication_reference": reference,
            "aasr_request": {
                "format": "wav",
                "pid": 80006,
                "rate": 16000,
                "smooth_text": 0,
                "filter_sensitive": 0,
            },
            "poll_count": 0,
            "submitted_at": submitted_at.isoformat(timespec="seconds"),
            "next_poll_at": (submitted_at + timedelta(minutes=5)).isoformat(
                timespec="seconds"
            ),
            "updated_at": submitted_at.isoformat(timespec="seconds"),
        }
        self._append(row)
        return {**row, "idempotent_replay": False}

    @_job_locked
    def poll(self, job_id: str) -> dict[str, Any]:
        current = self._latest(job_id)
        if current.get("status") in {"transcribed", "rendered", "verified", "decided"}:
            return {**current, "idempotent_replay": True}
        if current.get("status") not in {"submitted", "running"}:
            raise EnrichmentError("only a submitted or running job can be polled")
        now = self.now()
        if now.tzinfo is None:
            raise EnrichmentError("enrichment clock must include a timezone")
        try:
            next_poll = datetime.fromisoformat(str(current["next_poll_at"]))
        except (KeyError, ValueError) as exc:
            raise EnrichmentError("enrichment job has an invalid next_poll_at") from exc
        if now < next_poll:
            self._append({
                **current,
                "event": "poll_blocked",
                "poll_blocked_at": now.isoformat(timespec="seconds"),
                "reason": "provider poll is not due",
            })
            raise EnrichmentError(
                f"provider poll is not due before {next_poll.isoformat(timespec='seconds')}"
            )
        if self.aasr_client is None:
            raise EnrichmentError("Baidu AASR client is not configured")
        poll_count = int(current.get("poll_count") or 0) + 1

        def fail_poll(reason: str) -> None:
            delay_minutes = min(60, 5 * (2**poll_count))
            self._append({
                **current,
                "event": "transcription_poll_failed",
                "status": "running",
                "provider_error": reason,
                "poll_count": poll_count,
                "last_polled_at": now.isoformat(timespec="seconds"),
                "next_poll_at": (now + timedelta(minutes=delay_minutes)).isoformat(
                    timespec="seconds"
                ),
                "updated_at": now.isoformat(timespec="seconds"),
            })

        try:
            raw_response = self.aasr_client.query(
                str(current.get("provider_task_id") or "")
            )
        except EnrichmentError as exc:
            fail_poll(str(exc))
            raise
        task = next(
            (
                row
                for row in raw_response.get("tasks_info") or []
                if str(row.get("task_id") or "") == current.get("provider_task_id")
            ),
            None,
        )
        if task is None:
            reason = "Baidu AASR query omitted the requested task"
            fail_poll(reason)
            raise EnrichmentError(reason)
        provider_status = str(task.get("task_status") or "")
        if provider_status in {"Created", "Running"}:
            delay_minutes = min(60, 5 * (2**poll_count))
            row = {
                **current,
                "event": "transcription_polled",
                "status": "running",
                "provider_task_status": provider_status,
                "poll_count": poll_count,
                "last_polled_at": now.isoformat(timespec="seconds"),
                "next_poll_at": (now + timedelta(minutes=delay_minutes)).isoformat(
                    timespec="seconds"
                ),
                "updated_at": now.isoformat(timespec="seconds"),
            }
            self._append(row)
            return {**row, "idempotent_replay": False}
        if provider_status == "Failure":
            result = task.get("task_result") or {}
            row = {
                **current,
                "event": "transcription_failed",
                "status": "failed",
                "provider_task_status": provider_status,
                "provider_error": {
                    "err_no": result.get("err_no"),
                    "err_msg": result.get("err_msg"),
                },
                "poll_count": poll_count,
                "last_polled_at": now.isoformat(timespec="seconds"),
                "updated_at": now.isoformat(timespec="seconds"),
            }
            self._append(row)
            return {**row, "idempotent_replay": False}
        if provider_status != "Success":
            reason = f"unsupported Baidu AASR task status: {provider_status}"
            fail_poll(reason)
            raise EnrichmentError(reason)
        task_result = task.get("task_result") or {}
        if not task_result.get("result") or not task_result.get("detailed_result"):
            reason = "successful AASR task omitted complete transcript data"
            fail_poll(reason)
            raise EnrichmentError(reason)
        artifact_dir = self.output_dir / "artifacts" / job_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        raw_path = artifact_dir / "baidu_aasr_response.json"
        raw_bytes = (
            json.dumps(raw_response, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        temporary = artifact_dir / ".baidu_aasr_response.partial.json"
        temporary.write_bytes(raw_bytes)
        temporary.replace(raw_path)
        row = {
            **current,
            "event": "transcription_completed",
            "status": "transcribed",
            "provider_task_status": provider_status,
            "poll_count": poll_count,
            "last_polled_at": now.isoformat(timespec="seconds"),
            "raw_response_path": str(raw_path),
            "raw_response_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "updated_at": now.isoformat(timespec="seconds"),
        }
        row.pop("next_poll_at", None)
        self._append(row)
        return {**row, "idempotent_replay": False}

    @_job_locked
    def render(self, job_id: str) -> dict[str, Any]:
        current = self._latest(job_id)
        if current.get("status") in {"rendered", "verified", "decided"}:
            transcript_path = Path(str(current.get("transcript_path") or ""))
            if (
                transcript_path.is_file()
                and _sha256_file(transcript_path) == current.get("transcript_sha256")
            ):
                return {**current, "idempotent_replay": True}
        if current.get("status") != "transcribed":
            raise EnrichmentError("only a transcribed job can be rendered")
        _raw, task = self._raw_task(current)
        duration_ms, segments = self._segments(task)
        artifact_dir = self.output_dir / "artifacts" / job_id
        basename = Path(str(current.get("video_basename") or job_id)).stem
        transcript_path = artifact_dir / f"{basename}.md"
        plain_path = artifact_dir / f"{basename}.txt"
        plain_lines = [text for segment in segments for text in segment["texts"]]
        markdown_lines = [
            f"# {basename}",
            "",
            f"- Provider: `{current.get('provider')}`",
            f"- Provider task: `{current.get('provider_task_id')}`",
            f"- Source video SHA-256: `{current.get('video_sha256')}`",
            f"- Prepared audio SHA-256: `{current.get('audio_sha256')}`",
            "",
            "## 完整逐字稿",
            "",
        ]
        for segment in segments:
            interval = (
                f"[{_timestamp(segment['begin_time'])}–"
                f"{_timestamp(segment['end_time'])}]"
            )
            markdown_lines.extend(
                f"{interval} {text}" for text in segment["texts"]
            )
        markdown = "\n".join(markdown_lines) + "\n"
        plain = "\n".join(plain_lines) + "\n"
        _atomic_write(transcript_path, markdown.encode("utf-8"))
        _atomic_write(plain_path, plain.encode("utf-8"))
        now = self.now()
        row = {
            **current,
            "event": "transcript_rendered",
            "status": "rendered",
            "transcript_path": str(transcript_path),
            "transcript_sha256": _sha256_file(transcript_path),
            "plain_transcript_path": str(plain_path),
            "plain_transcript_sha256": _sha256_file(plain_path),
            "rendered_segment_count": len(segments),
            "rendered_text_entry_count": len(plain_lines),
            "audio_duration_ms": duration_ms,
            "updated_at": now.isoformat(timespec="seconds"),
        }
        self._append(row)
        return {**row, "idempotent_replay": False}

    @_job_locked
    def verify(self, job_id: str, *, audit_path: Path | str) -> dict[str, Any]:
        current = self._latest(job_id)
        supplied_audit = Path(audit_path).expanduser().resolve()
        if not supplied_audit.is_file():
            raise EnrichmentError(f"content audit not found: {supplied_audit}")
        audit_bytes = supplied_audit.read_bytes()
        audit_sha256 = hashlib.sha256(audit_bytes).hexdigest()
        if current.get("status") in {"verified", "decided"}:
            if current.get("audit_sha256") == audit_sha256:
                return {**current, "idempotent_replay": True}
            raise EnrichmentError("verified enrichment cannot silently replace its content audit")
        if current.get("status") != "rendered":
            raise EnrichmentError("only a rendered transcript can be verified")
        _raw, task = self._raw_task(current)
        duration_ms, segments = self._segments(task)
        transcript_path = self._runtime_path(
            str(current.get("transcript_path") or "")
        )
        plain_path = Path(str(current.get("plain_transcript_path") or ""))
        if (
            not transcript_path.is_file()
            or _sha256_file(transcript_path) != current.get("transcript_sha256")
            or not plain_path.is_file()
            or _sha256_file(plain_path) != current.get("plain_transcript_sha256")
        ):
            raise EnrichmentError("rendered transcript is missing or changed")
        raw_lines = [text for segment in segments for text in segment["texts"]]
        rendered_lines = plain_path.read_text(encoding="utf-8").splitlines()
        task_result = task.get("task_result") or {}
        complete_result = task_result.get("result")
        if isinstance(complete_result, str):
            complete_result = [complete_result]
        if (
            not isinstance(complete_result, list)
            or not complete_result
            or any(not isinstance(value, str) for value in complete_result)
        ):
            raise EnrichmentError("AASR result omitted complete transcript text")
        normalize = lambda value: "".join(str(value).split())
        result_detail_parity = normalize("".join(complete_result)) == normalize(
            "".join(raw_lines)
        )
        timeline_gaps = [segments[0]["begin_time"]]
        timeline_gaps.extend(
            max(0, right["begin_time"] - left["end_time"])
            for left, right in zip(segments, segments[1:])
        )
        timeline_gaps.append(max(0, duration_ms - segments[-1]["end_time"]))
        max_gap_ms = max(timeline_gaps)
        max_gap_limit_ms = max(120_000, duration_ms * 0.2)
        middle_start = duration_ms * 0.4
        middle_end = duration_ms * 0.6
        opening_end = min(60_000, duration_ms * 0.1)
        ending_start = duration_ms - min(60_000, duration_ms * 0.1)
        coverage = {
            "opening": segments[0]["begin_time"] <= opening_end,
            "middle": any(
                segment["end_time"] >= middle_start
                and segment["begin_time"] <= middle_end
                for segment in segments
            ),
            "ending": segments[-1]["end_time"] >= ending_start,
            "raw_render_parity": rendered_lines == raw_lines,
            "result_detail_parity": result_detail_parity,
            "max_gap_within_limit": max_gap_ms <= max_gap_limit_ms,
        }
        try:
            audit = json.loads(audit_bytes)
        except json.JSONDecodeError as exc:
            self._append({
                **current,
                "event": "content_verification_failed",
                "status": "rendered",
                "reason": "invalid_audit_json",
                "error_type": type(exc).__name__,
                "updated_at": self.now().isoformat(timespec="seconds"),
            })
            raise EnrichmentError("content audit is invalid JSON") from exc
        if not isinstance(audit, dict):
            self._append({
                **current,
                "event": "content_verification_failed",
                "status": "rendered",
                "reason": "content audit must be a JSON object",
                "updated_at": self.now().isoformat(timespec="seconds"),
            })
            raise EnrichmentError("content audit must be a JSON object")
        checks = audit.get("checks")
        required_positions = {"opening", "middle", "ending"}
        required_categories = {"direction_or_negation", "number", "proper_name"}
        if audit.get("video_sha256") != current.get("video_sha256"):
            raise EnrichmentError("content audit video hash does not match the source")
        if (
            not isinstance(checks, list)
            or len(checks) != len(required_positions)
            or any(not isinstance(row, dict) for row in checks)
            or {row.get("position") for row in checks} != required_positions
        ):
            raise EnrichmentError("content audit requires opening, middle, and ending checks")
        categories: set[str] = set()
        full_text = "\n".join(raw_lines)
        for check in checks:
            excerpt = str(check.get("transcript_excerpt") or "").strip()
            heard = str(check.get("heard_text") or "").strip()
            try:
                timestamp_ms = int(check["timestamp_ms"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EnrichmentError("content audit check requires timestamp_ms") from exc
            matching_segment = next(
                (
                    segment
                    for segment in segments
                    if segment["begin_time"] <= timestamp_ms <= segment["end_time"]
                    and excerpt in "".join(segment["texts"])
                ),
                None,
            )
            position = str(check.get("position") or "")
            position_matches = {
                "opening": 0 <= timestamp_ms <= opening_end,
                "middle": middle_start <= timestamp_ms <= middle_end,
                "ending": ending_start <= timestamp_ms <= duration_ms,
            }.get(position, False)
            normalized_excerpt = "".join(excerpt.split())
            normalized_heard = "".join(heard.split())
            if (
                check.get("passed") is not True
                or not excerpt
                or not heard
                or excerpt not in full_text
                or matching_segment is None
                or not position_matches
                or normalized_excerpt != normalized_heard
            ):
                raise EnrichmentError("content audit contains an unverified spot check")
            values = check.get("categories") or []
            if not isinstance(values, list):
                raise EnrichmentError("content audit categories must be a list")
            categories.update(str(value) for value in values)
        if not all(coverage.values()) or not required_categories.issubset(categories):
            self._append({
                **current,
                "event": "content_verification_failed",
                "status": "rendered",
                "coverage": coverage,
                "audit_categories": sorted(categories),
                "reason": "coverage or required audit category is incomplete",
            })
            raise EnrichmentError("transcript content verification is incomplete")
        durable_audit_path = self.output_dir / "artifacts" / job_id / "content_audit.json"
        _atomic_write(durable_audit_path, audit_bytes)
        now = self.now()
        row = {
            **current,
            "event": "content_verified",
            "status": "verified",
            "coverage": coverage,
            "audit_categories": sorted(required_categories),
            "audit_path": str(durable_audit_path),
            "audit_sha256": audit_sha256,
            "updated_at": now.isoformat(timespec="seconds"),
        }
        self._append(row)
        return {**row, "idempotent_replay": False}

    @_job_locked
    def decide(
        self,
        job_id: str,
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
        sender: Callable[[str, str], dict[str, str]],
        pipeline: Any | None = None,
    ) -> dict[str, Any]:
        current = self._latest(job_id)
        bundle_file = Path(bundle_path).expanduser().resolve()

        def record_failure(
            stage: str,
            exc: BaseException,
            *,
            bundle_sha256: str | None = None,
        ) -> None:
            row = {
                **current,
                "event": "decision_failed",
                "status": current.get("status"),
                "failure_stage": stage,
                "error_type": type(exc).__name__,
                "updated_at": self.now().isoformat(timespec="seconds"),
            }
            if bundle_sha256 is not None:
                row["decision_bundle_sha256"] = bundle_sha256
            self._append(row)

        if not bundle_file.is_file():
            exc = EnrichmentError(f"decision bundle not found: {bundle_file}")
            record_failure("bundle_not_found", exc)
            raise exc
        try:
            bundle_bytes = bundle_file.read_bytes()
        except OSError as exc:
            record_failure("bundle_read", exc)
            raise EnrichmentError("decision bundle could not be read") from exc
        bundle_sha256 = hashlib.sha256(bundle_bytes).hexdigest()
        if current.get("status") == "decided" and current.get(
            "decision_bundle_sha256"
        ) == bundle_sha256:
            replay = {**current}
            for field in (
                "transcript_path",
                "decision_bundle_path",
                "decision_result_path",
            ):
                resolved = self._runtime_path(str(replay.get(field) or ""))
                if resolved.is_file():
                    replay[field] = str(resolved)
            return {**replay, "idempotent_replay": True}
        if current.get("status") not in {"verified", "decided"}:
            exc = EnrichmentError("only a verified transcript can enter decisions")
            record_failure(
                "invalid_predecessor", exc, bundle_sha256=bundle_sha256
            )
            raise exc
        transcript_path = self._runtime_path(
            str(current.get("transcript_path") or "")
        )
        if (
            not transcript_path.is_file()
            or _sha256_file(transcript_path) != current.get("transcript_sha256")
        ):
            exc = EnrichmentError("verified transcript is missing or changed")
            record_failure(
                "transcript_missing_or_changed", exc, bundle_sha256=bundle_sha256
            )
            raise exc
        try:
            bundle = json.loads(bundle_bytes)
        except json.JSONDecodeError as exc:
            record_failure("invalid_bundle_json", exc, bundle_sha256=bundle_sha256)
            raise EnrichmentError("decision bundle is invalid JSON") from exc
        items = bundle.get("items") if isinstance(bundle, dict) else None
        if not isinstance(items, list) or len(items) != 1:
            exc = EnrichmentError(
                "one video enrichment job requires exactly one decision item"
            )
            record_failure("invalid_bundle_items", exc, bundle_sha256=bundle_sha256)
            raise exc
        if not isinstance(items[0], dict):
            exc = EnrichmentError("decision bundle item must be a JSON object")
            record_failure("invalid_bundle_item", exc, bundle_sha256=bundle_sha256)
            raise exc
        evidence_path = self._runtime_path(
            str(items[0].get("evidence_path") or "")
        )
        if evidence_path != transcript_path.resolve():
            exc = EnrichmentError(
                "decision bundle evidence_path must be the verified transcript"
            )
            record_failure("evidence_path_mismatch", exc, bundle_sha256=bundle_sha256)
            raise exc
        if pipeline is None:
            from .decisions import DecisionPipeline
            from .household import LiangHuiMcpClient

            pipeline = DecisionPipeline(
                Path(decision_output_dir),
                household_context_loader=LiangHuiMcpClient.from_config().load_context,
            )

        try:
            result = pipeline.process(bundle)
        except Exception as exc:
            record_failure("process", exc, bundle_sha256=bundle_sha256)
            raise EnrichmentError("ticket 01 decision pipeline failed") from exc
        try:
            validate_decision_process_result(result)
        except EnrichmentError as exc:
            record_failure("process_result", exc, bundle_sha256=bundle_sha256)
            raise exc
        try:
            result["wechat_delivery"] = pipeline.deliver_wechat(result, sender=sender)
        except Exception as exc:
            record_failure("wechat_delivery", exc, bundle_sha256=bundle_sha256)
            raise EnrichmentError("household advisory delivery failed") from exc
        try:
            notification, paper = validate_decision_completion(result)
        except EnrichmentError as exc:
            record_failure("completion_result", exc, bundle_sha256=bundle_sha256)
            raise
        decision_result_path = self.output_dir / "artifacts" / job_id / "decision_result.json"
        result_bytes = (
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        _atomic_write(decision_result_path, result_bytes)
        household_summary = {
            key: notification[key]
            for key in ("idempotency_key", "status", "receipt")
            if notification.get(key) is not None
        }
        paper_summary = {
            key: paper[key]
            for key in (
                "status",
                "book",
                "paper_only",
                "ticker",
                "side",
                "reason",
                "idempotency_key",
            )
            if paper.get(key) is not None
        }
        now = self.now()
        row = {
            **current,
            "event": "decisions_completed",
            "status": "decided",
            "decision_bundle_path": str(bundle_file),
            "decision_bundle_sha256": bundle_sha256,
            "decision_result_path": str(decision_result_path),
            "decision_result_sha256": hashlib.sha256(result_bytes).hexdigest(),
            "household_notification": household_summary,
            "book_kol_us": paper_summary,
            "updated_at": now.isoformat(timespec="seconds"),
        }
        self._append(row)
        return {**row, "idempotent_replay": False}
