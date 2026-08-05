"""Hourly WeChat official-account discovery and remote Markdown acquisition.

The local node discovers exact publishers through the stateless ``wechat-cli``
surface and hands the remote sole writer only a self-hashed public article URL
plus identity metadata.  The remote node uses OpenCLI to materialize the full
article and its images before any model reads the evidence.  Image semantics
are written as Markdown and deterministically appended to the article.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from .enrichment_types import EnrichmentDiagnosticError, EnrichmentError


BEIJING = ZoneInfo("Asia/Shanghai")
DEFAULT_WECHAT_CLI = Path("/opt/homebrew/bin/wechat-cli")
DEFAULT_WITHIN = "48h"
DEFAULT_OPENCLI_COMMAND = ("opencli",)
OFFICIAL_ACCOUNT_KOLS: dict[str, dict[str, str]] = {
    "刘少狙击营": {
        "kol_id": "kol-liushao-jujiying",
        "author": "刘少狙击营",
    },
    "A也叫艾利克斯": {
        "kol_id": "kol-a-alex",
        "author": "A也叫艾利克斯",
    },
}
DEFAULT_PUBLISHERS = tuple(OFFICIAL_ACCOUNT_KOLS)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_LINK = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))"
    r"(?:\s+['\"][^)]*['\"])?\s*\)"
)
_URL_FIELDS = ("__biz", "mid", "idx", "sn", "chksm")
_LOCAL_TERMINAL = {"historical_baseline", "completed"}
_REMOTE_TERMINAL = {"decided"}
_MAX_CAPSULE_BYTES = 64 * 1024
_MAX_ARTICLE_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_NOTES_BYTES = 1024 * 1024


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        payload = (_canonical(value) + "\n").encode("utf-8")
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise EnrichmentError("official-account ledger append made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _timestamp(value: Any, *, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnrichmentError(f"official-account {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise EnrichmentError(f"official-account {field} needs a timezone")
    return parsed.astimezone(BEIJING).isoformat(timespec="seconds")


def _article_url(value: Any) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() != (
        "mp.weixin.qq.com"
    ):
        raise EnrichmentError("official-account article URL is invalid")
    query = parse_qs(parsed.query, keep_blank_values=False)
    if any(not query.get(field) for field in _URL_FIELDS[:4]):
        raise EnrichmentError("official-account article identity is incomplete")
    normalized_query = [
        (field, query[field][0]) for field in _URL_FIELDS if query.get(field)
    ]
    return urlunsplit(
        ("https", "mp.weixin.qq.com", "/s", urlencode(normalized_query), "")
    )


def _normalized_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _page_publish_time(value: Any) -> datetime:
    raw = str(value or "").strip()
    for pattern in ("%Y年%m月%d日 %H:%M:%S", "%Y年%m月%d日 %H:%M"):
        try:
            return datetime.strptime(raw, pattern).replace(tzinfo=BEIJING)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnrichmentError(
            "official-account OpenCLI publish time is invalid"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(BEIJING)


def _looks_like_challenge(text: str) -> bool:
    markers = (
        "secitptpage/verify.html",
        'id="js_verify"',
        "id='js_verify'",
    )
    if any(marker in text for marker in markers):
        return True
    if "环境异常" in text and any(
        marker in text
        for marker in ("完成验证后即可继续访问", "去验证", "请输入验证码")
    ):
        return True
    visible = re.sub(r"\s+", "", text)
    return "请输入验证码" in visible and len(visible) < 300


def _article_text_characters(markdown: str) -> int:
    text = _IMAGE_LINK.sub("", markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[#>*_`~|\-\s]", "", text)
    return len(text)


def _discovery_version(item: dict[str, Any]) -> str:
    return _sha256_text(
        _canonical(
            {
                "article_id": item["article_id"],
                "publisher": item["publisher"],
                "title": item["title"],
                "source_url": item["source_url"],
                "published_at": item["published_at"],
                "received_at": item["received_at"],
            }
        )
    )


def parse_official_account_articles(
    payload: dict[str, Any],
    *,
    publishers: tuple[str, ...] = DEFAULT_PUBLISHERS,
) -> list[dict[str, Any]]:
    """Validate and normalize exact-publisher discovery metadata."""
    if not isinstance(payload, dict):
        raise EnrichmentError("official-account response is invalid")
    if payload.get("failures") not in (None, []):
        raise EnrichmentDiagnosticError(
            "official-account scan is incomplete",
            category="source_error",
            code="wechat_official_scan_incomplete",
            stage="wechat_official_scan",
        )
    updates = payload.get("updates")
    if not isinstance(updates, list):
        raise EnrichmentError("official-account updates are invalid")
    allowed = set(publishers)
    items: dict[str, dict[str, Any]] = {}
    for raw in updates:
        if not isinstance(raw, dict):
            continue
        publisher = str(raw.get("publisher") or "").strip()
        if publisher not in allowed:
            continue
        article_id = str(raw.get("id") or "").strip().lower()
        title = str(raw.get("title") or "").strip()
        if not _SHA256.fullmatch(article_id) or not title:
            raise EnrichmentError("official-account article binding is invalid")
        profile = OFFICIAL_ACCOUNT_KOLS.get(publisher)
        if profile is None:
            raise EnrichmentError("official-account KOL is not registered")
        item = {
            "identity": f"wechat-official:{article_id}",
            "article_id": article_id,
            "kol_id": profile["kol_id"],
            "author": profile["author"],
            "publisher": publisher,
            "title": title,
            "source_url": _article_url(raw.get("url")),
            "published_at": _timestamp(raw.get("published_at"), field="published_at"),
            "received_at": _timestamp(raw.get("received_at"), field="received_at"),
        }
        item["discovery_version"] = _discovery_version(item)
        items[item["identity"]] = item
    return sorted(
        items.values(),
        key=lambda item: (item["published_at"], item["publisher"], item["identity"]),
    )


class WechatCliOfficialAccountReader:
    """Credential-safe ``subscription-updates`` reader."""

    def __init__(
        self,
        publishers: tuple[str, ...] = DEFAULT_PUBLISHERS,
        *,
        executable: Path | str = DEFAULT_WECHAT_CLI,
        within: str = DEFAULT_WITHIN,
        runner: Callable[..., Any] = subprocess.run,
    ):
        normalized = tuple(dict.fromkeys(str(row).strip() for row in publishers))
        if not normalized or any(row not in OFFICIAL_ACCOUNT_KOLS for row in normalized):
            raise EnrichmentError("official-account publisher configuration is invalid")
        self.publishers = normalized
        self.executable = Path(executable).expanduser().resolve()
        self.within = str(within).strip()
        self._runner = runner

    def __call__(self) -> dict[str, Any]:
        if not self.executable.is_file():
            raise EnrichmentDiagnosticError(
                "wechat-cli is unavailable",
                category="configuration",
                code="wechat_cli_missing",
                stage="wechat_official_scan",
            )
        command = [str(self.executable), "subscription-updates", "--within", self.within]
        for publisher in self.publishers:
            command.extend(("--publisher", publisher))
        command.extend(("--format", "json"))
        try:
            result = self._runner(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            value = json.loads(result.stdout)
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentDiagnosticError(
                "wechat-cli official-account scan timed out",
                category="timeout",
                code="wechat_official_scan_timeout",
                stage="wechat_official_scan",
            ) from exc
        except (subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
            raise EnrichmentDiagnosticError(
                "wechat-cli official-account scan failed",
                category="source_error",
                code="wechat_official_scan_failed",
                stage="wechat_official_scan",
            ) from exc
        if not isinstance(value, dict):
            raise EnrichmentError("official-account response is invalid")
        return value


def _capsule(item: dict[str, Any]) -> dict[str, Any]:
    handoff_id = _sha256_text(
        f"{item['identity']}\n{item['discovery_version']}"
    )
    value: dict[str, Any] = {
        "schema_version": 2,
        "handoff_kind": "wechat_official_url",
        "handoff_id": handoff_id,
        "source_identity": item["identity"],
        "article_id": item["article_id"],
        "discovery_version": item["discovery_version"],
        "kol_id": item["kol_id"],
        "author": item["author"],
        "source": "微信公众号",
        "publisher": item["publisher"],
        "title": item["title"],
        "source_url": item["source_url"],
        "published_at": item["published_at"],
        "received_at": item["received_at"],
        "content_transport": "public_url_only",
        "large_payload_local_bytes": 0,
        "coordinator_source_video_bytes": 0,
    }
    value["handoff_sha256"] = _sha256_text(_canonical(value))
    return value


def validate_official_account_capsule(value: Any) -> dict[str, Any]:
    """Validate one portable URL-only article handoff."""
    if not isinstance(value, dict):
        raise EnrichmentError("official-account handoff is invalid")
    unsigned = dict(value)
    expected = str(unsigned.pop("handoff_sha256", ""))
    publisher = str(value.get("publisher") or "").strip()
    profile = OFFICIAL_ACCOUNT_KOLS.get(publisher)
    article_id = str(value.get("article_id") or "")
    identity = f"wechat-official:{article_id}"
    forbidden = {
        "description",
        "evidence_text",
        "markdown",
        "article_body",
        "local_path",
        "media_path",
        "video_path",
    }
    if (
        value.get("schema_version") != 2
        or value.get("handoff_kind") != "wechat_official_url"
        or not _SHA256.fullmatch(str(value.get("handoff_id") or ""))
        or not _SHA256.fullmatch(article_id)
        or value.get("source_identity") != identity
        or not _SHA256.fullmatch(str(value.get("discovery_version") or ""))
        or profile is None
        or value.get("kol_id") != profile["kol_id"]
        or value.get("author") != profile["author"]
        or value.get("source") != "微信公众号"
        or value.get("content_transport") != "public_url_only"
        or value.get("large_payload_local_bytes") != 0
        or value.get("coordinator_source_video_bytes") != 0
        or forbidden.intersection(value)
        or expected != _sha256_text(_canonical(unsigned))
    ):
        raise EnrichmentError("official-account handoff binding is invalid")
    normalized = {
        "identity": identity,
        "article_id": article_id,
        "publisher": publisher,
        "title": str(value.get("title") or "").strip(),
        "source_url": _article_url(value.get("source_url")),
        "published_at": _timestamp(value.get("published_at"), field="published_at"),
        "received_at": _timestamp(value.get("received_at"), field="received_at"),
    }
    if not normalized["title"] or _discovery_version(normalized) != value.get(
        "discovery_version"
    ):
        raise EnrichmentError("official-account handoff discovery binding is invalid")
    expected_handoff = _sha256_text(
        f"{identity}\n{value['discovery_version']}"
    )
    if value.get("handoff_id") != expected_handoff:
        raise EnrichmentError("official-account handoff identity is invalid")
    return dict(value)


class OfficialAccountSubscription:
    """Exactly-once local scan and remote-task URL dispatch state machine."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        reader: Callable[[], dict[str, Any]],
        handoff_exchange: Callable[[dict[str, Any]], dict[str, Any]],
        publishers: tuple[str, ...] = DEFAULT_PUBLISHERS,
        clock: Callable[[], datetime] | None = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.manifest_path = self.output_dir / "manifest.json"
        self.events_path = self.output_dir / "events.jsonl"
        self.reader = reader
        self.handoff_exchange = handoff_exchange
        self.publishers = tuple(publishers)
        self.clock = clock or (lambda: datetime.now(BEIJING))

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            raise EnrichmentError("official-account clock needs a timezone")
        return value.astimezone(BEIJING).isoformat(timespec="seconds")

    def _load(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"schema_version": 2, "publishers": list(self.publishers), "items": {}}
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("official-account manifest is invalid") from exc
        if (
            value.get("schema_version") != 2
            or value.get("publishers") != list(self.publishers)
            or not isinstance(value.get("items"), dict)
        ):
            raise EnrichmentError("official-account manifest is invalid")
        return value

    def _save(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = self._now()
        _atomic_json(self.manifest_path, manifest)

    def _poll(self, manifest: dict[str, Any]) -> None:
        observed = parse_official_account_articles(
            self.reader(), publishers=self.publishers
        )
        unseen = [item for item in observed if item["identity"] not in manifest["items"]]
        if "initialized_at" not in manifest:
            eligible: set[str] = set()
            for publisher in self.publishers:
                publisher_items = [
                    item for item in unseen if item["publisher"] == publisher
                ]
                if publisher_items:
                    eligible.add(publisher_items[-1]["identity"])
            for item in unseen:
                manifest["items"][item["identity"]] = {
                    **item,
                    "status": (
                        "discovered"
                        if item["identity"] in eligible
                        else "historical_baseline"
                    ),
                    "updated_at": self._now(),
                }
            manifest["initialized_at"] = self._now()
        else:
            for item in unseen:
                manifest["items"][item["identity"]] = {
                    **item,
                    "status": "discovered",
                    "updated_at": self._now(),
                }
        self._save(manifest)

    def _dispatch(
        self,
        manifest: dict[str, Any],
        item: dict[str, Any],
    ) -> dict[str, Any]:
        capsule = _capsule(item)
        capsule_path = self.output_dir / "handoffs" / f"{capsule['handoff_id']}.json"
        if capsule_path.is_file():
            if capsule_path.stat().st_size > _MAX_CAPSULE_BYTES:
                raise EnrichmentError("official-account handoff is too large")
            try:
                prior = json.loads(capsule_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError("official-account handoff is invalid") from exc
            if prior != capsule:
                raise EnrichmentError("official-account handoff changed after claim")
        else:
            _atomic_json(capsule_path, capsule)
        request = {
            "event": "daily_remote_handoff_input_required",
            "adapter": "wechat_official_account",
            "action": "dispatch_wechat_official_handoff",
            "subscription_id": item["identity"],
            "handoff_id": capsule["handoff_id"],
            "capsule_path": str(capsule_path),
            "instructions": (
                "Send the complete credential-free URL capsule, never this local "
                "path, to the existing remote Xiaocao task. Keep "
                "scripts/kol_daily.py import-wechat-official alive and write the "
                "exact compact JSON value to stdin. The import must not treat "
                "discovery metadata as article evidence."
            ),
            "required_response": {
                "action": "dispatch_wechat_official_handoff",
                "subscription_id": item["identity"],
                "handoff_id": capsule["handoff_id"],
                "accepted": True,
                "readback_status": "accepted|already_present",
                "remote_thread_id": "existing registered remote task id",
                "remote_host_id": "registered remote host id",
            },
        }
        response = self.handoff_exchange(request)
        if (
            not isinstance(response, dict)
            or response.get("action") != request["action"]
            or response.get("subscription_id") != item["identity"]
            or response.get("handoff_id") != capsule["handoff_id"]
            or response.get("accepted") is not True
            or response.get("readback_status") not in {"accepted", "already_present"}
            or not str(response.get("remote_thread_id") or "").strip()
            or not str(response.get("remote_host_id") or "").strip()
        ):
            raise EnrichmentError(
                "official-account remote handoff lacks acceptance readback"
            )
        completed = {
            **item,
            "status": "completed",
            "handoff_id": capsule["handoff_id"],
            "handoff_path": str(capsule_path),
            "remote_thread_id": str(response["remote_thread_id"]),
            "remote_host_id": str(response["remote_host_id"]),
            "remote_readback_status": str(response["readback_status"]),
            "updated_at": self._now(),
        }
        manifest["items"][item["identity"]] = completed
        self._save(manifest)
        _append_jsonl(
            self.events_path,
            {
                "schema_version": 2,
                "event": "official_account_url_handoff_completed",
                "identity": item["identity"],
                "publisher": item["publisher"],
                "handoff_id": capsule["handoff_id"],
                "occurred_at": completed["updated_at"],
            },
        )
        return completed

    def run_once(self) -> dict[str, Any]:
        manifest = self._load()
        self._poll(manifest)
        pending = sorted(
            (
                dict(item)
                for item in manifest["items"].values()
                if item.get("status") not in _LOCAL_TERMINAL
            ),
            key=lambda item: (item["published_at"], item["publisher"], item["identity"]),
        )
        completed = [self._dispatch(manifest, item) for item in pending]
        return {
            "status": "no_update",
            "publisher_count": len(self.publishers),
            "handoff_dispatched_count": len(completed),
            "handoff_ids": [str(item["handoff_id"]) for item in completed],
        }


class OfficialAccountOpenCliAcquirer:
    """Run the validated OpenCLI browser workflow and verify its artifacts."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        opencli_command: tuple[str, ...] = DEFAULT_OPENCLI_COMMAND,
        runner: Callable[..., Any] = subprocess.run,
        timeout: int = 120,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.opencli_command = tuple(opencli_command)
        if not self.opencli_command:
            raise EnrichmentError("official-account OpenCLI command is empty")
        self._runner = runner
        self.timeout = int(timeout)

    def _images(self, markdown_path: Path, source_root: Path) -> list[dict[str, Any]]:
        markdown = markdown_path.read_text(encoding="utf-8")
        refs = [left or right for left, right in _IMAGE_LINK.findall(markdown)]
        assets: list[dict[str, Any]] = []
        remote_refs: list[str] = []
        seen: set[Path] = set()
        for ref in refs:
            parsed = urlsplit(ref)
            if parsed.scheme in {"http", "https"}:
                remote_refs.append(ref)
                continue
            if parsed.scheme:
                raise EnrichmentError("official-account image reference is invalid")
            clean = unquote(ref.split("#", 1)[0].split("?", 1)[0])
            path = (markdown_path.parent / clean).resolve()
            if not path.is_relative_to(source_root) or not path.is_file():
                raise EnrichmentError("official-account image artifact is missing")
            if path in seen:
                continue
            seen.add(path)
            payload = path.read_bytes()
            if not payload:
                raise EnrichmentError("official-account image artifact is empty")
            assets.append(
                {
                    "index": len(assets) + 1,
                    "path": str(path),
                    "bytes": len(payload),
                    "sha256": _sha256_bytes(payload),
                }
            )
        if remote_refs:
            raise EnrichmentDiagnosticError(
                "OpenCLI did not materialize every official-account image",
                category="source_error",
                code="wechat_official_image_download_incomplete",
                stage="wechat_official_opencli",
            )
        return assets

    def __call__(self, item: dict[str, Any]) -> dict[str, Any]:
        handoff_id = str(item["handoff_id"])
        source_root = (self.output_dir / handoff_id).resolve()
        source_root.mkdir(parents=True, exist_ok=True)
        command = [
            *self.opencli_command,
            "weixin",
            "download",
            "--url",
            str(item["source_url"]),
            "--output",
            str(source_root),
            "--download-images",
            "true",
            "--window",
            "background",
            "-f",
            "json",
        ]
        try:
            result = self._runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentDiagnosticError(
                "official-account OpenCLI timed out",
                category="timeout",
                code="wechat_official_opencli_timeout",
                stage="wechat_official_opencli",
            ) from exc
        except OSError as exc:
            raise EnrichmentDiagnosticError(
                "official-account OpenCLI is unavailable",
                category="configuration",
                code="wechat_official_opencli_missing",
                stage="wechat_official_opencli",
            ) from exc
        if result.returncode != 0:
            raise EnrichmentDiagnosticError(
                "official-account OpenCLI command failed",
                category="source_error",
                code="wechat_official_opencli_failed",
                stage="wechat_official_opencli",
                exit_code=int(result.returncode),
            )
        try:
            rows = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise EnrichmentDiagnosticError(
                "official-account OpenCLI returned invalid JSON",
                category="source_error",
                code="wechat_official_opencli_invalid_json",
                stage="wechat_official_opencli",
            ) from exc
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise EnrichmentError("official-account OpenCLI result is invalid")
        row = rows[0]
        status = str(row.get("status") or "").strip()
        status_lower = status.lower()
        if "verification required" in status_lower or any(
            marker in status
            for marker in ("请输入验证码", "环境异常", "去验证")
        ):
            raise EnrichmentDiagnosticError(
                "wechat_official_captcha_required",
                category="user_action",
                code="wechat_official_captcha_required",
                stage="wechat_official_opencli",
            )
        if status != "success":
            raise EnrichmentDiagnosticError(
                "official-account OpenCLI did not produce an article",
                category="source_error",
                code="wechat_official_opencli_unsuccessful",
                stage="wechat_official_opencli",
            )
        if _normalized_text(row.get("title")) != _normalized_text(item["title"]):
            raise EnrichmentDiagnosticError(
                "official-account OpenCLI title mismatch",
                category="source_error",
                code="wechat_official_title_mismatch",
                stage="wechat_official_validation",
            )
        if _normalized_text(row.get("author")) != _normalized_text(item["publisher"]):
            raise EnrichmentDiagnosticError(
                "official-account OpenCLI publisher mismatch",
                category="source_error",
                code="wechat_official_publisher_mismatch",
                stage="wechat_official_validation",
            )
        page_time = _page_publish_time(row.get("publish_time"))
        discovery_time = datetime.fromisoformat(str(item["published_at"]))
        if discovery_time.tzinfo is None:
            raise EnrichmentError("official-account discovery time is invalid")
        discovery_time = discovery_time.astimezone(BEIJING)
        delta = abs((page_time - discovery_time).total_seconds())
        if page_time.date() != discovery_time.date() or delta > 300:
            raise EnrichmentDiagnosticError(
                "official-account page publish time mismatch",
                category="source_error",
                code="wechat_official_publish_time_mismatch",
                stage="wechat_official_validation",
            )
        saved_raw = str(row.get("saved") or "").strip()
        saved = Path(saved_raw).expanduser()
        if not saved.is_absolute():
            raise EnrichmentError("official-account OpenCLI saved path is not absolute")
        saved = saved.resolve()
        if not saved.is_relative_to(source_root) or not saved.is_file():
            raise EnrichmentError("official-account OpenCLI saved path is invalid")
        size = saved.stat().st_size
        if size <= 0 or size > _MAX_ARTICLE_BYTES:
            raise EnrichmentError("official-account Markdown size is invalid")
        payload = saved.read_bytes()
        try:
            markdown = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EnrichmentError("official-account Markdown is not UTF-8") from exc
        if _looks_like_challenge(markdown):
            raise EnrichmentDiagnosticError(
                "wechat_official_captcha_required",
                category="user_action",
                code="wechat_official_captcha_required",
                stage="wechat_official_validation",
            )
        if (
            _normalized_text(item["title"]) not in _normalized_text(markdown[:4096])
            or _normalized_text(item["publisher"]) not in _normalized_text(markdown[:4096])
            or _article_text_characters(markdown) < 100
        ):
            raise EnrichmentDiagnosticError(
                "official-account Markdown failed the completeness gate",
                category="source_error",
                code="wechat_official_markdown_incomplete",
                stage="wechat_official_validation",
            )
        images = self._images(saved, source_root)
        return {
            "opencli_status": status,
            "opencli_saved_path": str(saved),
            "raw_markdown_path": str(saved),
            "raw_markdown_bytes": len(payload),
            "raw_markdown_sha256": _sha256_bytes(payload),
            "body_text_characters": _article_text_characters(markdown),
            "page_publish_time": page_time.isoformat(timespec="seconds"),
            "publish_time_delta_seconds": int(delta),
            "image_assets": images,
            "image_count": len(images),
        }


class OfficialAccountInbox:
    """Remote immutable import, OpenCLI acquisition, and Markdown evidence."""

    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.manifest_path = self.output_dir / "inbox_manifest.json"
        self.events_path = self.output_dir / "inbox_events.jsonl"

    def _load(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"schema_version": 2, "items": {}}
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("official-account inbox manifest is invalid") from exc
        if value.get("schema_version") != 2 or not isinstance(value.get("items"), dict):
            raise EnrichmentError("official-account inbox manifest is invalid")
        return value

    def _save_item(self, item: dict[str, Any]) -> dict[str, Any]:
        manifest = self._load()
        handoff_id = str(item["handoff_id"])
        if handoff_id not in manifest["items"]:
            raise EnrichmentError("official-account inbox item disappeared")
        manifest["items"][handoff_id] = item
        _atomic_json(self.manifest_path, manifest)
        return dict(item)

    def import_capsule(self, value: Any) -> dict[str, Any]:
        capsule = validate_official_account_capsule(value)
        encoded = (
            json.dumps(capsule, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if len(encoded) > _MAX_CAPSULE_BYTES:
            raise EnrichmentError("official-account handoff is too large")
        manifest = self._load()
        handoff_id = str(capsule["handoff_id"])
        prior = manifest["items"].get(handoff_id)
        if prior is not None:
            if prior.get("handoff_sha256") != capsule["handoff_sha256"]:
                raise EnrichmentError("official-account handoff conflicts with prior import")
            return {
                "status": "already_present",
                "handoff_id": handoff_id,
                "source_identity": capsule["source_identity"],
            }
        capsule_path = self.output_dir / "imported_handoffs" / f"{handoff_id}.json"
        _atomic_bytes(capsule_path, encoded)
        item = {
            key: capsule[key]
            for key in (
                "handoff_id",
                "handoff_sha256",
                "source_identity",
                "article_id",
                "discovery_version",
                "kol_id",
                "author",
                "source",
                "publisher",
                "title",
                "source_url",
                "published_at",
                "received_at",
                "content_transport",
            )
        }
        item.update({"status": "imported", "capsule_path": str(capsule_path)})
        manifest["items"][handoff_id] = item
        _atomic_json(self.manifest_path, manifest)
        _append_jsonl(
            self.events_path,
            {
                "schema_version": 2,
                "event": "official_account_url_handoff_imported",
                "handoff_id": handoff_id,
                "source_identity": capsule["source_identity"],
                "handoff_sha256": capsule["handoff_sha256"],
            },
        )
        return {
            "status": "accepted",
            "handoff_id": handoff_id,
            "source_identity": capsule["source_identity"],
        }

    def status(self) -> dict[str, Any]:
        manifest = self._load()
        items = list(manifest["items"].values())
        return {
            "item_count": len(items),
            "pending_count": sum(
                1 for item in items if item.get("status") not in _REMOTE_TERMINAL
            ),
            "items": [
                {
                    key: item[key]
                    for key in (
                        "handoff_id",
                        "source_identity",
                        "publisher",
                        "title",
                        "published_at",
                        "status",
                    )
                }
                for item in sorted(
                    items,
                    key=lambda row: (
                        str(row.get("published_at") or ""),
                        str(row.get("source_identity") or ""),
                    ),
                )
            ],
        }

    def pending_items(self) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self._load()["items"].values()
            if item.get("status") not in _REMOTE_TERMINAL
        ]

    @staticmethod
    def _verify_file(path_value: Any, expected_sha256: Any, *, label: str) -> Path:
        path = Path(str(path_value or "")).expanduser().resolve()
        if (
            not path.is_file()
            or not _SHA256.fullmatch(str(expected_sha256 or ""))
            or _sha256_bytes(path.read_bytes()) != expected_sha256
        ):
            raise EnrichmentError(f"official-account {label} changed")
        return path

    def acquire(
        self,
        item: dict[str, Any],
        *,
        acquirer: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        handoff_id = str(item["handoff_id"])
        current = self._load()["items"].get(handoff_id)
        if not isinstance(current, dict):
            raise EnrichmentError("official-account inbox item disappeared")
        if current.get("status") in {"acquired", "evidence_ready", "decided"}:
            self._verify_file(
                current.get("raw_markdown_path"),
                current.get("raw_markdown_sha256"),
                label="raw Markdown",
            )
            return dict(current)
        try:
            receipt = acquirer(dict(current))
        except EnrichmentDiagnosticError as exc:
            failed = {
                **current,
                "status": (
                    "verification_required"
                    if exc.diagnostic_code == "wechat_official_captcha_required"
                    else "imported"
                ),
                "last_acquisition_failure": {
                    "category": exc.diagnostic_category,
                    "code": exc.diagnostic_code,
                    "stage": exc.diagnostic_stage,
                },
            }
            self._save_item(failed)
            _append_jsonl(
                self.events_path,
                {
                    "schema_version": 2,
                    "event": "official_account_acquisition_failed",
                    "handoff_id": handoff_id,
                    **failed["last_acquisition_failure"],
                },
            )
            raise
        if not isinstance(receipt, dict):
            raise EnrichmentError("official-account acquisition receipt is invalid")
        acquired = {
            **current,
            **receipt,
            "status": "acquired",
        }
        acquired.pop("last_acquisition_failure", None)
        self._verify_file(
            acquired.get("raw_markdown_path"),
            acquired.get("raw_markdown_sha256"),
            label="raw Markdown",
        )
        self._save_item(acquired)
        _append_jsonl(
            self.events_path,
            {
                "schema_version": 2,
                "event": "official_account_markdown_acquired",
                "handoff_id": handoff_id,
                "raw_markdown_sha256": acquired["raw_markdown_sha256"],
                "raw_markdown_bytes": acquired["raw_markdown_bytes"],
                "image_count": acquired["image_count"],
            },
        )
        return acquired

    def prepare_image_request(self, item: dict[str, Any]) -> dict[str, Any] | None:
        if item.get("status") in {"evidence_ready", "decided"}:
            return None
        if item.get("status") != "acquired":
            raise EnrichmentError("official-account article is not acquired")
        raw_path = self._verify_file(
            item.get("raw_markdown_path"),
            item.get("raw_markdown_sha256"),
            label="raw Markdown",
        )
        images = item.get("image_assets")
        if not isinstance(images, list):
            raise EnrichmentError("official-account image inventory is invalid")
        verified: list[dict[str, Any]] = []
        for expected_index, image in enumerate(images, start=1):
            if not isinstance(image, dict) or image.get("index") != expected_index:
                raise EnrichmentError("official-account image inventory is invalid")
            path = self._verify_file(
                image.get("path"), image.get("sha256"), label="image artifact"
            )
            verified.append(
                {
                    "index": expected_index,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": image["sha256"],
                }
            )
        if not verified:
            return None
        request_path = self.output_dir / "image_requests" / f"{item['handoff_id']}.json"
        request = {
            "schema_version": 1,
            "event": "daily_official_article_image_input_required",
            "adapter": "wechat_official_account",
            "identity": item["source_identity"],
            "publisher": item["publisher"],
            "title": item["title"],
            "raw_markdown_path": str(raw_path),
            "raw_markdown_sha256": item["raw_markdown_sha256"],
            "images": verified,
            "image_request_path": str(request_path),
            "required_output": (
                "Write UTF-8 Markdown headed `# 图片信息转写`. Inspect every image "
                "exactly once. For each image include its index and SHA-256, mark "
                "information-bearing or decorative, transcribe all decision-relevant "
                "text/chart/table information, and state uncertainty. Do not copy the "
                "article body and do not return JSON."
            ),
        }
        if request_path.is_file():
            try:
                prior = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError("official-account image request is invalid") from exc
            if prior != request:
                raise EnrichmentError("official-account image request changed")
        else:
            _atomic_json(request_path, request)
        return request

    def materialize_evidence(
        self,
        item: dict[str, Any],
        *,
        image_notes_path: Path | str | None = None,
    ) -> dict[str, Any]:
        current = self._load()["items"].get(str(item["handoff_id"]))
        if not isinstance(current, dict):
            raise EnrichmentError("official-account inbox item disappeared")
        if current.get("status") in {"evidence_ready", "decided"}:
            self._verify_file(
                current.get("evidence_path"),
                current.get("evidence_sha256"),
                label="evidence Markdown",
            )
            return dict(current)
        if current.get("status") != "acquired":
            raise EnrichmentError("official-account article is not acquired")
        raw_path = self._verify_file(
            current.get("raw_markdown_path"),
            current.get("raw_markdown_sha256"),
            label="raw Markdown",
        )
        raw_text = raw_path.read_text(encoding="utf-8").rstrip()
        images = current.get("image_assets") or []
        notes_text: str
        notes_sha256: str | None = None
        notes_path_value: str | None = None
        if images:
            if image_notes_path is None:
                raise EnrichmentError("official-account image notes are missing")
            notes_path = Path(image_notes_path).expanduser().resolve()
            if not notes_path.is_file() or notes_path.stat().st_size > _MAX_IMAGE_NOTES_BYTES:
                raise EnrichmentError("official-account image notes are invalid")
            notes_payload = notes_path.read_bytes()
            try:
                notes_text = notes_payload.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise EnrichmentError("official-account image notes are not UTF-8") from exc
            if "图片信息转写" not in notes_text or len(notes_text) < 50:
                raise EnrichmentError("official-account image notes are incomplete")
            for image in images:
                self._verify_file(
                    image.get("path"), image.get("sha256"), label="image artifact"
                )
                if str(image["sha256"]) not in notes_text:
                    raise EnrichmentError(
                        "official-account image notes do not cover every image"
                    )
            notes_sha256 = _sha256_bytes(notes_payload)
            notes_path_value = str(notes_path)
        else:
            if image_notes_path is not None:
                raise EnrichmentError("official-account article has no images to annotate")
            notes_text = "# 图片信息转写\n\n正文没有需要逐图读取的图片。"
        evidence_text = (
            raw_text
            + "\n\n---\n\n"
            + "## 图片证据文字化\n\n"
            + "以下逐图记录覆盖正文中的全部图片；"
            + "装饰图也会明确标为无新增信息。"
            + "后续分析以这些文字记录为图片信息入口，"
            + "原图和 SHA-256 仅用于审计。\n\n"
            + notes_text
            + "\n"
        )
        evidence_path = self.output_dir / "evidence" / f"{current['handoff_id']}.md"
        evidence_payload = evidence_text.encode("utf-8")
        if evidence_path.is_file():
            if evidence_path.read_bytes() != evidence_payload:
                raise EnrichmentError("official-account evidence changed after claim")
        else:
            _atomic_bytes(evidence_path, evidence_payload)
        evidence_sha256 = _sha256_bytes(evidence_payload)
        ready = {
            **current,
            "status": "evidence_ready",
            "publication_version": evidence_sha256,
            "evidence_scope": "complete_article_markdown_with_image_notes",
            "evidence_path": str(evidence_path),
            "evidence_sha256": evidence_sha256,
            "evidence_bytes": len(evidence_payload),
            "image_notes_path": notes_path_value,
            "image_notes_sha256": notes_sha256,
        }
        self._save_item(ready)
        _append_jsonl(
            self.events_path,
            {
                "schema_version": 2,
                "event": "official_account_evidence_materialized",
                "handoff_id": ready["handoff_id"],
                "evidence_sha256": evidence_sha256,
                "evidence_bytes": len(evidence_payload),
                "image_count": len(images),
            },
        )
        return ready

    def prepare_analysis_request(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("status") not in {"evidence_ready", "decided"}:
            raise EnrichmentError("official-account evidence is not ready")
        evidence_path = self._verify_file(
            item.get("evidence_path"),
            item.get("evidence_sha256"),
            label="evidence Markdown",
        )
        request_path = self.output_dir / "analysis_requests" / f"{item['handoff_id']}.json"
        request = {
            "schema_version": 2,
            "event": "daily_analysis_input_required",
            "adapter": "wechat_official_account",
            "identity": item["source_identity"],
            "version_key": item["publication_version"],
            "kol_id": item["kol_id"],
            "author": item["author"],
            "source": item["source"],
            "publisher": item["publisher"],
            "title": item["title"],
            "published_at": item["published_at"],
            "page_publish_time": item["page_publish_time"],
            "evidence_path": str(evidence_path),
            "evidence_sha256": item["evidence_sha256"],
            "evidence_scope": item["evidence_scope"],
            "author_reference_policy": (
                "作者身份代词尚未审定；读者文案使用公众号全名，"
                "避免性别代词。"
            ),
            "required_content_value": "low_density|promoted(report_only|alert_eligible)",
            "analysis_request_path": str(request_path),
        }
        if request_path.is_file():
            try:
                prior = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "official-account analysis request is invalid"
                ) from exc
            if prior != request:
                raise EnrichmentError(
                    "official-account analysis request changed after claim"
                )
        else:
            _atomic_json(request_path, request)
        return request

    def decide(
        self,
        item: dict[str, Any],
        *,
        bundle_path: Path | str,
        pipeline: Any,
        sender: Callable[[str, str], dict[str, str]],
    ) -> dict[str, Any]:
        handoff_id = str(item["handoff_id"])
        result_path = self.output_dir / "decisions" / handoff_id / "result.json"
        state_path = self.output_dir / "decisions" / handoff_id / "state.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                prior_result = Path(str(state["decision_result_path"]))
            except (OSError, json.JSONDecodeError, KeyError) as exc:
                raise EnrichmentError("official-account decision state is invalid") from exc
            if (
                not prior_result.is_file()
                or _sha256_bytes(prior_result.read_bytes())
                != state.get("decision_result_sha256")
            ):
                raise EnrichmentError("official-account decision result changed")
            manifest = self._load()
            stored = manifest["items"].get(handoff_id)
            if not isinstance(stored, dict):
                raise EnrichmentError("official-account inbox item disappeared")
            if stored.get("status") != "decided":
                manifest["items"][handoff_id] = {
                    **stored,
                    "status": "decided",
                    "decision_result_path": str(prior_result),
                    "decision_result_sha256": state["decision_result_sha256"],
                }
                _atomic_json(self.manifest_path, manifest)
            return {**state, "idempotent_replay": True}
        bundle_file = Path(bundle_path).expanduser().resolve()
        if not bundle_file.is_file():
            raise EnrichmentError("official-account decision bundle is missing")
        try:
            bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("official-account decision bundle is invalid") from exc
        items = bundle.get("items") if isinstance(bundle, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise EnrichmentError("official-account decision needs one item")
        decision_item = items[0]
        required_bindings = {
            "source": item["source"],
            "author": item["author"],
            "title": item["title"],
            "published_at": item["published_at"],
            "evidence_path": item["evidence_path"],
            "evidence_sha256": item["evidence_sha256"],
        }
        if any(decision_item.get(key) != value for key, value in required_bindings.items()):
            raise EnrichmentError("official-account decision changed source evidence")
        paper_account = getattr(getattr(pipeline, "book", None), "account", None)
        if (
            not isinstance(paper_account, dict)
            or paper_account.get("book") != "KOL-US"
            or paper_account.get("paper_only") is not True
        ):
            raise EnrichmentError(
                "official-account decision pipeline lacks paper-only contract"
            )
        try:
            result = pipeline.process(bundle)
            if result.get("status") == "failed":
                raise EnrichmentError(
                    "official-account decision failed: "
                    + ",".join(str(row) for row in result.get("failures") or [])
                )
            result["wechat_delivery"] = pipeline.deliver_wechat(result, sender=sender)
            terminal = result["items"][0]["daily_terminal"]
            if not isinstance(terminal, dict):
                raise EnrichmentError("official-account decision lacks terminal")
        except Exception as exc:
            if isinstance(exc, EnrichmentError):
                raise
            raise EnrichmentError("official-account decision pipeline failed") from exc
        _atomic_json(result_path, result)
        result_sha256 = _sha256_bytes(result_path.read_bytes())
        state = {
            "status": "decided",
            "handoff_id": handoff_id,
            "source_identity": item["source_identity"],
            "publication_version": item["publication_version"],
            "decision_bundle_path": str(bundle_file),
            "decision_bundle_sha256": _sha256_bytes(bundle_file.read_bytes()),
            "decision_result_path": str(result_path),
            "decision_result_sha256": result_sha256,
        }
        _atomic_json(state_path, state)
        manifest = self._load()
        stored = manifest["items"].get(handoff_id)
        if not isinstance(stored, dict):
            raise EnrichmentError("official-account inbox item disappeared")
        manifest["items"][handoff_id] = {
            **stored,
            "status": "decided",
            "decision_result_path": str(result_path),
            "decision_result_sha256": result_sha256,
        }
        _atomic_json(self.manifest_path, manifest)
        _append_jsonl(
            self.events_path,
            {
                "schema_version": 2,
                "event": "official_account_decided",
                "handoff_id": handoff_id,
                "source_identity": item["source_identity"],
                "decision_result_sha256": result_sha256,
            },
        )
        return {**state, "idempotent_replay": False}
