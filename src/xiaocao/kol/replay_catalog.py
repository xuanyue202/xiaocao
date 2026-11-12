"""Credential-free inventory of the merchant's published recorded courses.

This reads catalogue metadata, not a player, and never exports media tickets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests

from .enrichment_types import EnrichmentDiagnosticError
from .human_playback import _course_title_key


class ReplayCatalogError(EnrichmentDiagnosticError):
    """A safe diagnostic; remote response bodies must not enter error messages."""

    def __init__(self, code: str):
        super().__init__(code, category="provider_contract_error",
                         code=code, stage="recorded_catalog")


@dataclass(frozen=True)
class ReplayCatalogConfig:
    app_id: str
    course_id: str
    mini_program_token: str
    navigation_source_url: str | None = None

    @classmethod
    def from_dict(cls, value: dict) -> "ReplayCatalogConfig":
        if not isinstance(value, dict):
            raise ReplayCatalogError("catalog_configuration_invalid")
        fields = [value.get(k) for k in ("app_id", "course_id", "mini_program_token")]
        if any(not isinstance(v, str) for v in fields) or not all(
            re.fullmatch(pattern, v) for pattern, v in zip(
                (r"app[A-Za-z0-9]+", r"course_[A-Za-z0-9]+", r"[A-Za-z0-9]+"), fields
            )
        ):
            raise ReplayCatalogError("catalog_configuration_invalid")
        navigation = value.get("navigation_source_url")
        if navigation is not None:
            from .xiaocao_wechat import _normalized_live_url
            if (not isinstance(navigation, str)
                or _normalized_live_url(navigation) != navigation):
                raise ReplayCatalogError("catalog_configuration_invalid")
        return cls(*fields, navigation_source_url=navigation)

    @property
    def origin(self) -> str:
        return f"https://{self.app_id}.h5.xiaoeknow.com"

    @property
    def page_url(self) -> str:
        return f"{self.origin}/p/course/ecourse/preview/{self.course_id}"

    @property
    def learning_url(self) -> str:
        return (
            f"{self.origin}/p/course/ecourse/{self.course_id}"
            f"?app_id={self.app_id}&sub_course_list_mode=0"
        )


class ReplayCatalogReader:
    def __init__(self, config: ReplayCatalogConfig, *, session=None):
        self.config = config
        self.session = session if session is not None else requests.Session()
        if session is None:
            # In particular, do not silently use the operator's ~/.netrc.
            self.session.trust_env = False

    def _start(self) -> None:
        # The public site sets its anonymous session cookie before API reads.
        # Keep it in this session only; do not borrow browser/native credentials.
        url = self.config.page_url
        for _ in range(4):
            response = self.session.get(url, timeout=15, allow_redirects=False)
            if response.status_code == 200:
                return
            if response.status_code not in {301, 302, 303, 307, 308}:
                raise ReplayCatalogError("catalog_page_unavailable")
            target = urljoin(url, response.headers.get("Location", ""))
            expected, actual = urlsplit(self.config.page_url), urlsplit(target)
            if ((actual.scheme, actual.netloc, actual.path)
                != (expected.scheme, expected.netloc, expected.path)):
                raise ReplayCatalogError("catalog_page_redirect_changed")
            url = target
        raise ReplayCatalogError("catalog_page_redirect_incomplete")

    def _post(self, path: str, params: dict) -> dict:
        response = self.session.post(
            self.config.origin + path,
            data={f"bizData[{k}]": str(v) for k, v in params.items()},
            timeout=15, allow_redirects=False,
        )
        if response.status_code != 200:
            raise ReplayCatalogError("catalog_api_unavailable")
        try:
            value = response.json()
        except (ValueError, TypeError):
            raise ReplayCatalogError("catalog_api_invalid_json") from None
        if (not isinstance(value, dict) or type(value.get("code")) is not int
            or value["code"] != 0 or not isinstance(value.get("data"), dict)):
            raise ReplayCatalogError("catalog_api_rejected")
        return value["data"]

    def read(self) -> list[dict]:
        self._start()
        rows, expected_total = [], None
        for page in range(1, 11):
            data = self._post(
                "/xe.course.business_go.avoidlogin.e_course.resource_catalog_list.get/1.0.0",
                {"app_id": self.config.app_id, "resource_id": "",
                 "course_id": self.config.course_id, "p_id": 0, "order": "asc",
                 "page": page, "page_size": 50, "sub_course_id": "",
                 "is_display_auth_sections": 0},
            )
            total, batch = data.get("total"), data.get("list")
            if (type(total) is not int or not 0 <= total <= 500
                or not isinstance(batch, list) or len(batch) > 50
                or data.get("has_chapter") not in (None, False, 0)
                or (expected_total is not None and expected_total != total)):
                raise ReplayCatalogError("catalog_scan_incomplete")
            expected_total = total
            for row in batch:
                if (not isinstance(row, dict) or row.get("course_id") != self.config.course_id
                    or not re.fullmatch(r"v_[0-9a-f]{24}", str(row.get("chapter_id", "")))
                    or row.get("resource_type") != 3
                    or not isinstance(row.get("chapter_title"), str)
                    or type(row.get("video_length")) is not int or row["video_length"] <= 0
                    or row.get("jump_url") != f"/p/course/video/{row['chapter_id']}"):
                    raise ReplayCatalogError("catalog_resource_binding_invalid")
                rows.append({"resource_id": row["chapter_id"], "title": row["chapter_title"],
                    "duration_seconds": row["video_length"], "course_id": self.config.course_id,
                    "page_url": self.config.origin + row["jump_url"]})
            if len(rows) >= total:
                if len(rows) != total or len({r['resource_id'] for r in rows}) != total:
                    raise ReplayCatalogError("catalog_scan_incomplete")
                return rows
            if len(batch) != 50:
                raise ReplayCatalogError("catalog_scan_incomplete")
        raise ReplayCatalogError("catalog_scan_incomplete")

    def inspect_access(self, resource: dict) -> dict:
        # Metadata only. Do not decode or return video_urls, play_sign or cookies.
        data = self._post("/xe.course.business_go.video.detail_info.get/2.0.0",
            {"app_id": self.config.app_id, "resource_id": resource["resource_id"],
             "product_id": self.config.course_id})
        info = data.get("video_info") or {}
        if (not isinstance(info, dict) or info.get("resource_id") != resource["resource_id"]
            or info.get("video_length") != resource["duration_seconds"]):
            raise ReplayCatalogError("recorded_detail_binding_invalid")
        keys = ("is_available", "is_free", "is_subscribe", "is_try", "is_unlock")
        flags = {k: data.get(k) for k in keys}
        if any(type(v) is not int or v not in {0, 1} for v in flags.values()):
            raise ReplayCatalogError("recorded_access_flags_invalid")
        if type(info.get("is_drm")) is not int or info["is_drm"] not in {0, 1}:
            raise ReplayCatalogError("recorded_access_flags_invalid")
        return {"session_kind": "anonymous", **flags, "is_drm": info["is_drm"],
            "download_attempted": False}


def match_original(rows: list[dict], published_at: str) -> dict | None:
    published = datetime.fromisoformat(published_at)
    if published.tzinfo is None:
        raise ReplayCatalogError("original_timestamp_naive")
    published = published.astimezone(ZoneInfo("Asia/Shanghai"))
    session = "早盘" if published.hour < 12 else "复盘"
    date = f"{published.month}月{published.day}日"
    titles = {f"大师班{session}直播{date}", f"大师班{session}直播{date}YJ",
              f"{date}大师班{session}直播", f"{date}{session}大师班直播"}
    segments = [r for r in rows if any(re.fullmatch(
        re.escape(title) + r"片段[1-9][0-9]*", _course_title_key(r['title'])
    ) for title in titles)]
    if segments:
        raise ReplayCatalogError("recorded_course_multipart_requires_assembly")
    matches = [r for r in rows if _course_title_key(r['title']) in titles]
    if len(matches) > 1:
        raise ReplayCatalogError("recorded_session_ambiguous")
    if not matches:
        # Same date with different session wording is evidence to investigate,
        # not proof that the recording is unpublished or the same course.
        if any(re.fullmatch(
                   re.escape(date) + r".{1,8}大师班直播(?:YJ)?",
                   _course_title_key(r['title']))
               and not any(other in _course_title_key(r['title'])
                           for other in ({"早盘", "复盘"} - {session}))
               for r in rows):
            raise ReplayCatalogError("recorded_session_title_unverified")
    return matches[0] if matches else None


def verify_original(item: dict, identity: str, originals: list[dict]) -> None:
    """Reconcile the manifest with the cached original, before any HTTP read."""
    if item.get('identity') != identity:
        raise ReplayCatalogError('original_identity_changed')
    exact = [row for row in originals if row.get('identity') == identity]
    keys = ('identity', 'published_at', 'message_sha256', 'mini_program_name',
            'mini_program_token', 'contact', 'contact_username')
    if len(exact) != 1 or any(item.get(k) != exact[0].get(k) for k in keys):
        raise ReplayCatalogError('original_history_binding_changed')


def catalogue_navigation_peer(config: ReplayCatalogConfig, item: dict,
                              originals: list[dict]) -> dict | None:
    """Join one branded share and one exact labelled URL in the same message."""
    if (item.get("entry_kind") != "wechat_mini_program"
        or item.get("mini_program_name") != "见势擒龙团"
        or not re.fullmatch(r"[A-Za-z0-9]+", str(item.get("mini_program_token", "")))
        or not config.navigation_source_url
        or not item.get("contact") or not item.get("contact_username")):
        return None
    keys = ("message_sha256", "published_at", "contact", "contact_username")
    peers = [row for row in originals
             if all(row.get(k) == item.get(k) for k in keys)]
    minis = [row for row in peers if row.get("entry_kind") == "wechat_mini_program"]
    urls = [row for row in peers
            if row.get("source_url") == config.navigation_source_url
            and row.get("recorded_navigation_marker") is True
            and row.get("recorded_navigation_url_sha256") == hashlib.sha256(
                config.navigation_source_url.encode()).hexdigest()]
    if len(minis) != 1 or len(urls) != 1 or minis[0].get("identity") != item.get("identity"):
        return None
    return urls[0]


def verify_catalogue_binding(config: ReplayCatalogConfig, item: dict,
                             originals: list[dict] | None = None) -> None:
    if (not re.fullmatch(r"kol-wechat-[0-9a-f]{24}", str(item.get("identity", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("message_sha256", "")))):
        raise ReplayCatalogError("original_catalog_binding_invalid")
    if originals is not None:
        verify_original(item, item["identity"], originals)
    if item.get("mini_program_token") == config.mini_program_token:
        return
    if originals is None or catalogue_navigation_peer(config, item, originals) is None:
        raise ReplayCatalogError("original_catalog_binding_invalid")


def inspect_original(config: ReplayCatalogConfig, item: dict, *, inspect_access=False,
                     originals: list[dict] | None = None,
                     session=None, now: datetime | None = None) -> dict:
    verify_catalogue_binding(config, item, originals)
    published = datetime.fromisoformat(item['published_at'])
    now = now or datetime.now(ZoneInfo('Asia/Shanghai'))
    if (published.tzinfo is None or now.tzinfo is None
        or not timedelta(0) <= now - published <= timedelta(hours=72)):
        raise ReplayCatalogError("original_outside_current_recovery_window")
    reader = ReplayCatalogReader(config, session=session)
    try:
        rows = reader.read()
        selected = match_original(rows, item['published_at'])
        result = {"status": "recorded_replay_candidate_found" if selected else "recorded_replay_not_listed",
            "identity": item['identity'], "capture_job_id": item.get('capture_job_id'),
            "source_message_sha256": item['message_sha256'], "published_at": item['published_at'],
            "catalog_page_url": config.page_url, "catalog_count": len(rows),
            "catalog_metadata_sha256": hashlib.sha256(json.dumps(rows, ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            "recording": selected, "session_verified": False, "download_attempted": False}
        if selected and inspect_access:
            result['access'] = reader.inspect_access(selected)
        return result
    except requests.RequestException:
        raise ReplayCatalogError("catalog_transport_unavailable") from None
    finally:
        if session is None:
            reader.session.close()
