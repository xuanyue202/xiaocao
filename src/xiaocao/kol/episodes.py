"""Deterministic logical-content grouping for multi-part KOL videos.

The source adapter may provide an explicit episode id and part order.  When it
does not, this module recognizes a conservative set of filename suffixes.  It
never infers across authors, sources, or automatic source directories, and
ambiguous/incomplete candidates are returned as pauses instead of being
silently processed as standalone videos.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any


_BRACKETED_PART = re.compile(
    r"^(?P<base>.+?)\s*[\(\[（【]\s*(?P<marker>[^)\]）】]+?)\s*[\)\]）】]$",
    re.IGNORECASE,
)
_KEYWORD_PART = re.compile(
    r"^(?P<base>.+?)[\s._-]+"
    r"(?:(?:part|pt|segment|seg|clip)\s*|第\s*)"
    r"(?P<marker>[0-9一二三四五六七八九十百]+"
    r"(?:\s*(?:/|of)\s*[0-9一二三四五六七八九十百]+)?)"
    r"\s*(?:段|集|篇)?$",
    re.IGNORECASE,
)
_BARE_PART = re.compile(
    r"^(?P<base>.+?)[\s._-]+"
    r"(?P<marker>0*[0-9]{1,3}|[A-Za-z]|上|中|下|前|后)"
    r"\s*(?:段|集|篇)?$",
    re.IGNORECASE,
)
_MARKER_PREFIX = re.compile(
    r"^(?:(?:part|pt|segment|seg|clip)\s*|第\s*)",
    re.IGNORECASE,
)
_MARKER_SUFFIX = re.compile(r"\s*(?:段|集|篇)$", re.IGNORECASE)
_EXPECTED_COUNT = re.compile(
    r"^(?P<index>[0-9一二三四五六七八九十百]+)"
    r"\s*(?:/|of)\s*"
    r"(?P<count>[0-9一二三四五六七八九十百]+)$",
    re.IGNORECASE,
)
_SEMANTIC_LABELS = {"上", "中", "下", "前", "后"}
AUTO_EPISODE_SETTLE_SECONDS = 300


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _chinese_integer(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if all(character in digits for character in text):
        number = 0
        for character in text:
            number = number * 10 + digits[character]
        return number
    if "百" in text:
        hundreds, remainder = text.split("百", 1)
        hundred_value = digits.get(hundreds, 1 if not hundreds else -1)
        if hundred_value < 0:
            return None
        tail = _chinese_integer(remainder) if remainder else 0
        if tail is None:
            return None
        return hundred_value * 100 + tail
    if "十" in text:
        tens, ones = text.split("十", 1)
        tens_value = digits.get(tens, 1 if not tens else -1)
        ones_value = digits.get(ones, 0 if not ones else -1)
        if tens_value < 0 or ones_value < 0:
            return None
        return tens_value * 10 + ones_value
    return digits.get(text)


def _integer(value: str) -> int | None:
    text = str(value or "").strip()
    if text.isdigit():
        parsed = int(text)
        return parsed if parsed > 0 else None
    parsed = _chinese_integer(text)
    return parsed if parsed is not None and parsed > 0 else None


def _clean_base(value: str) -> str:
    return re.sub(r"[\s._-]+$", "", str(value or "").strip())


def _marker(
    value: str,
) -> tuple[str, int | None, int | None, str] | None:
    raw = str(value or "").strip()
    cleaned = _MARKER_PREFIX.sub("", raw)
    cleaned = _MARKER_SUFFIX.sub("", cleaned).strip()
    expected = _EXPECTED_COUNT.fullmatch(cleaned)
    if expected:
        index = _integer(expected.group("index"))
        count = _integer(expected.group("count"))
        if index is None or count is None:
            return None
        return raw, index, count, "numeric"
    if cleaned in _SEMANTIC_LABELS:
        return raw, None, None, "semantic"
    index = _integer(cleaned)
    if index is not None:
        return raw, index, None, "numeric"
    if len(cleaned) == 1 and cleaned.isascii() and cleaned.isalpha():
        return raw, ord(cleaned.upper()) - ord("A") + 1, None, "alpha"
    return None


def _part_hint(row: dict[str, Any]) -> dict[str, Any] | None:
    explicit_id = str(row.get("episode_id") or "").strip()
    explicit_index = row.get("part_index")
    if explicit_id or explicit_index is not None:
        try:
            index = int(explicit_index)
            count = (
                int(row["part_count"])
                if row.get("part_count") is not None
                else None
            )
        except (TypeError, ValueError):
            return {
                "invalid": True,
                "reason": "ambiguous_episode_metadata",
            }
        title = str(row.get("episode_title") or "").strip()
        if (
            not explicit_id
            or not title
            or index <= 0
            or count is not None
            and (count <= 0 or index > count)
        ):
            return {
                "invalid": True,
                "reason": "ambiguous_episode_metadata",
            }
        return {
            "base": title,
            "episode_key": f"explicit:{explicit_id}",
            "expected_count": count,
            "grouping_method": "explicit_metadata",
            "index": index,
            "label": str(row.get("part_label") or index),
            "marker_kind": "explicit",
        }

    stem = PurePosixPath(str(row.get("name") or "")).stem
    match = _BRACKETED_PART.fullmatch(stem)
    pattern_kind = "bracketed"
    if match is None:
        match = _KEYWORD_PART.fullmatch(stem)
        pattern_kind = "keyword"
    if match is None:
        match = _BARE_PART.fullmatch(stem)
        pattern_kind = "bare"
    if match is None:
        return None
    parsed = _marker(match.group("marker"))
    base = _clean_base(match.group("base"))
    if parsed is None or not base:
        return None
    label, index, expected_count, marker_kind = parsed
    parent = str(PurePosixPath(str(row["path"])).parent)
    return {
        "base": base,
        "episode_key": (
            "automatic:"
            + _sha256_text(
                "\n".join(
                    (
                        str(row.get("source") or ""),
                        str(row.get("author") or ""),
                        parent,
                        base.casefold(),
                    )
                )
            )
        ),
        "expected_count": expected_count,
        "grouping_method": "filename_suffix",
        "index": index,
        "label": label,
        "marker_kind": marker_kind,
        "pattern_kind": pattern_kind,
    }


def _resolved_semantic_indexes(hints: list[dict[str, Any]]) -> dict[str, int]:
    labels = {str(hint["label"]).strip() for hint in hints}
    if labels == {"上", "下"}:
        return {"上": 1, "下": 2}
    if labels == {"前", "后"}:
        return {"前": 1, "后": 2}
    return {"上": 1, "中": 2, "下": 3, "前": 1, "后": 2}


def _ambiguity(
    key: str,
    reason: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "episode_candidate_key": key,
        "reason": reason,
        "source": str(rows[0].get("source") or ""),
        "author": str(rows[0].get("author") or ""),
        "paths": sorted(str(row.get("path") or "") for row in rows),
        "component_identities": sorted(
            str(row.get("identity") or "") for row in rows
        ),
    }


def _episode_unit(
    key: str,
    members: list[tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    members.sort(key=lambda pair: int(pair[1]["index"]))
    rows = [pair[0] for pair in members]
    hints = [pair[1] for pair in members]
    title = str(hints[0]["base"])
    parents = {str(PurePosixPath(str(row["path"])).parent) for row in rows}
    parent = next(iter(parents))
    component_versions = [
        {
            "identity": row["identity"],
            "part_index": hint["index"],
            "version_key": row["version_key"],
        }
        for row, hint in members
    ]
    identity = _sha256_text(
        "\n".join(
            (
                "logical-video-episode",
                str(rows[0]["source"]),
                str(rows[0]["author"]),
                key,
            )
        )
    )
    version_key = _sha256_text(
        "\n".join((identity, _canonical(component_versions)))
    )
    parts = []
    for row, hint in members:
        parts.append(
            {
                **row,
                "part_index": int(hint["index"]),
                "part_label": str(hint["label"]),
                "part_count": len(rows),
            }
        )
    declared_count = any(
        hint.get("expected_count") is not None
        or hint.get("grouping_method") == "explicit_metadata"
        for hint in hints
    )
    return {
        "identity": identity,
        "version_key": version_key,
        "provider_identity_sha256": _sha256_text(
            _canonical(
                [
                    row.get("provider_identity_sha256")
                    for row in rows
                ]
            )
        ),
        "source": rows[0]["source"],
        "author": rows[0]["author"],
        "path": str(PurePosixPath(parent) / title),
        "name": f"{title}.episode",
        "is_dir": False,
        "is_episode": True,
        "media_type": "video",
        "size": sum(int(row.get("size") or 0) for row in rows),
        "uploaded_at": max(int(row.get("uploaded_at") or 0) for row in rows),
        "modified_at": max(int(row.get("modified_at") or 0) for row in rows),
        "remote_activity_at": max(
            max(
                int(row.get("uploaded_at") or 0),
                int(row.get("modified_at") or 0),
            )
            for row in rows
        ),
        "version_first_seen_at": max(
            str(row.get("version_first_seen_at") or "") for row in rows
        ),
        "first_seen_at": min(
            str(row.get("first_seen_at") or row.get("version_first_seen_at") or "")
            for row in rows
        ),
        "present": all(row.get("present") is True for row in rows),
        "episode_id": key,
        "episode_title": title,
        "part_count": len(rows),
        "grouping_method": hints[0]["grouping_method"],
        "completion_contract": (
            "declared_part_count"
            if declared_count
            else "quiescent_filename_group"
        ),
        "settle_seconds": 0 if declared_count else AUTO_EPISODE_SETTLE_SECONDS,
        "parts": parts,
    }


def assemble_video_units(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return standalone videos, complete episodes, and fail-closed pauses."""
    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    standalone: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for row in rows:
        if row.get("media_type") != "video":
            continue
        hint = _part_hint(row)
        if hint is None:
            standalone.append({**row, "is_episode": False})
            continue
        if hint.get("invalid"):
            invalid.append(
                _ambiguity(
                    f"invalid:{row.get('identity')}",
                    str(hint["reason"]),
                    [row],
                )
            )
            continue
        key = "\n".join(
            (
                str(row.get("source") or ""),
                str(row.get("author") or ""),
                str(hint["episode_key"]),
            )
        )
        groups.setdefault(key, []).append((row, hint))

    units = list(standalone)
    ambiguities = list(invalid)
    for key, candidates in groups.items():
        rows_for_group = [row for row, _hint in candidates]
        hints = [hint for _row, hint in candidates]
        if len(candidates) < 2:
            hint = hints[0]
            if (
                hint.get("grouping_method") == "explicit_metadata"
                or hint.get("pattern_kind") == "keyword"
            ):
                ambiguities.append(
                    _ambiguity(
                        key,
                        "episode_waiting_for_companions",
                        rows_for_group,
                    )
                )
            else:
                # A lone filename such as ``recording_1.mp4`` or
                # ``lesson (1).mp4`` is commonly a provider/camera suffix, not
                # durable proof of a multi-part publication.  Only an explicit
                # declaration or a Part/Segment/第N段 marker may hold a single
                # file for companions.  Once two weakly marked siblings exist
                # they are still grouped and receive the normal quiescence
                # window before work begins.
                standalone.append({**rows_for_group[0], "is_episode": False})
            continue
        if len({hint["base"] for hint in hints}) != 1:
            ambiguities.append(
                _ambiguity(
                    key,
                    "ambiguous_episode_metadata",
                    rows_for_group,
                )
            )
            continue
        parents = {
            str(PurePosixPath(str(row["path"])).parent)
            for row in rows_for_group
        }
        if len(parents) != 1:
            ambiguities.append(
                _ambiguity(
                    key,
                    "ambiguous_episode_directory",
                    rows_for_group,
                )
            )
            continue
        semantic_indexes = _resolved_semantic_indexes(hints)
        for hint in hints:
            if hint["marker_kind"] == "semantic":
                hint["index"] = semantic_indexes.get(str(hint["label"]).strip())
        indexes = [hint.get("index") for hint in hints]
        if (
            any(not isinstance(index, int) or index <= 0 for index in indexes)
            or len(set(indexes)) != len(indexes)
        ):
            ambiguities.append(
                _ambiguity(
                    key,
                    "ambiguous_episode_order",
                    rows_for_group,
                )
            )
            continue
        expected_counts = {
            int(hint["expected_count"])
            for hint in hints
            if hint.get("expected_count") is not None
        }
        if len(expected_counts) > 1:
            ambiguities.append(
                _ambiguity(
                    key,
                    "ambiguous_episode_count",
                    rows_for_group,
                )
            )
            continue
        expected_count = next(iter(expected_counts), max(indexes))
        if (
            expected_count != len(candidates)
            or set(indexes) != set(range(1, expected_count + 1))
        ):
            ambiguities.append(
                _ambiguity(
                    key,
                    "incomplete_episode",
                    rows_for_group,
                )
            )
            continue
        units.append(_episode_unit(key, candidates))

    units.extend(
        row
        for row in standalone
        if all(row.get("identity") != unit.get("identity") for unit in units)
    )
    units.sort(
        key=lambda row: (
            str(row.get("source") or ""),
            str(row.get("path") or ""),
            str(row.get("identity") or ""),
        )
    )
    ambiguities.sort(
        key=lambda row: (
            str(row.get("source") or ""),
            str(row.get("paths") or ""),
        )
    )
    return {"units": units, "ambiguities": ambiguities}
