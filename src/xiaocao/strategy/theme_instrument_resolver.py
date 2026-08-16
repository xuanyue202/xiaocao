"""Resolve Book T v2 themes into a provenance-bound instrument universe.

The resolver is deliberately a read-only deep module.  Its public seam accepts
one frozen :class:`TrendJudgmentSnapshot` and a catalog payload, then returns a
hash-bound universe that the later deterministic selector can consume.  It
does not fetch quotes, infer a ticker from prose, calculate a score, or write
any paper account state.

Catalogs are intentionally data-driven.  Theme aliases live in the reviewed
registry supplied by the caller; they are not author-specific constants in
strategy code.  Missing or ambiguous identity and missing ETF trading
metadata remain visible in the result and fail closed as ``unresolved`` or
``ineligible`` candidates.
"""

from __future__ import annotations

import copy
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from xiaocao.kol.publication import canonical_sha256

from .trend_snapshot import TrendJudgmentSnapshot, TrendSnapshotError


UNIVERSE_SCHEMA_VERSION = 1
RESOLVER_VERSION = "book-t-v2-theme-instrument-resolver-v1"
DEFAULT_CATALOG_VERSION = "catalog-v1"
IDENTITY_ONLY_REGISTRY_VERSION = "theme-registry-identity-only-v1"

_APPROVED_ALIAS_STATUSES = frozenset({"approved", "accepted", "reviewed", "active"})
MIN_MAPPING_CONFIDENCE = 0.8
_MARKET_DATA_OK_STATUSES = frozenset({"verified", "available", "ok", "current"})
_ETF_MARKET_DATA_OK_STATUSES = frozenset({"verified"})
_SAFE_THEME_ID = re.compile(r"^[^\s]{1,160}$")


class ThemeInstrumentResolverError(ValueError):
    """The resolver input or hash-bound output violates its contract."""


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ThemeInstrumentResolverError(f"{field} is not canonical JSON") from exc


def _text(value: Any, *, field: str, required: bool = False) -> str:
    if value is None:
        if required:
            raise ThemeInstrumentResolverError(f"{field} is required")
        return ""
    result = str(value).strip()
    if required and not result:
        raise ThemeInstrumentResolverError(f"{field} is required")
    return result


def _code(value: Any, *, field: str = "code") -> str:
    result = _text(value, field=field)
    return result.upper()


def _number(value: Any) -> int | float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not parsed.is_integer():
        return parsed
    return int(parsed)


def _list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _string_values(value: Any, *, code_keys: Sequence[str] = ()) -> list[str]:
    values: list[str] = []
    for item in _list(value):
        if isinstance(item, Mapping):
            selected = ""
            for key in code_keys:
                if item.get(key) not in (None, ""):
                    selected = str(item[key])
                    break
            if selected:
                values.append(selected.strip())
        elif str(item).strip():
            values.append(str(item).strip())
    return sorted(set(values))


def _ref_values(row: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        if key in row:
            values.extend(
                _string_values(
                    row.get(key),
                    code_keys=(
                        "code",
                        "id",
                        "theme_id",
                        "name",
                        "block_code",
                        "blockCode",
                        "category_code",
                        "categoryCode",
                        "stockCode",
                        "stockId",
                        "fundCode",
                    ),
                )
            )
    return sorted(set(value for value in values if value))


def _normalize_alias(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = re.sub(r"[\s\-_./+&·,:;，。/（）()]+", "", text)
    return text


def _sort_json(values: Iterable[Any]) -> list[Any]:
    return sorted(values, key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True))


def _row_list(value: Any, *, kind: str) -> list[dict[str, Any]]:
    """Accept list, keyed-map, or common API wrapper catalog shapes."""

    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("rows", "items", "entries", "records", "list", "data"):
            nested = value.get(key)
            if isinstance(nested, (list, tuple)):
                return [dict(item) for item in nested if isinstance(item, Mapping)]
            if isinstance(nested, Mapping):
                return _row_list(nested, kind=kind)
        row_keys = {
            "block": ("block_code", "blockCode", "categoryCode", "category_code", "blockName"),
            "etf": ("code", "stockCode", "stockId", "fundCode"),
            "stock": ("code", "stockCode", "stockId"),
        }[kind]
        if any(key in value for key in row_keys):
            return [dict(value)]
        rows: list[dict[str, Any]] = []
        for key, item in value.items():
            if not isinstance(item, Mapping):
                continue
            row = dict(item)
            if kind == "block":
                row.setdefault("block_code", key)
            else:
                row.setdefault("code", key)
            rows.append(row)
        return rows
    if isinstance(value, (list, tuple)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    raise ThemeInstrumentResolverError(f"{kind}_catalog must be a list or object")


def _row_code(row: Mapping[str, Any], *, kind: str) -> str:
    if kind == "block":
        keys = ("block_code", "blockCode", "category_code", "categoryCode", "block_id", "id", "code")
    else:
        keys = ("code", "stockCode", "stockId", "fundCode", "ticker", "instrument_code")
    for key in keys:
        if row.get(key) not in (None, ""):
            return _code(row[key], field=f"{kind}.code")
    return ""


def _row_name(row: Mapping[str, Any]) -> str:
    for key in ("name", "stockName", "codeName", "fundName", "categoryName", "blockName", "display_name"):
        if row.get(key) not in (None, ""):
            return str(row[key]).strip()
    return ""


def _provenance(row: Mapping[str, Any], *, kind: str, version: str, code: str) -> dict[str, str]:
    raw = row.get("provenance") or row.get("source") or row.get("mapping_source")
    supplied_source = ""
    supplied_version = ""
    supplied_evidence_id = ""
    if isinstance(raw, Mapping):
        supplied_source = _text(raw.get("source") or raw.get("name"), field="provenance.source")
        supplied_version = _text(
            raw.get("version") or raw.get("source_version") or raw.get("catalog_version"),
            field="provenance.version",
        )
        supplied_evidence_id = _text(raw.get("evidence_id") or raw.get("evidence"), field="provenance.evidence_id")
    else:
        supplied_source = _text(raw, field="provenance.source")
    source = supplied_source
    source_version = supplied_version
    evidence_id = supplied_evidence_id
    provenance_status = "complete" if supplied_source and supplied_version and supplied_evidence_id else "incomplete"
    source = source or f"{kind}-catalog"
    source_version = source_version or version
    evidence_id = evidence_id or canonical_sha256(
        {"kind": kind, "code": code, "source": source, "source_version": source_version}
    )
    return {
        "source": source,
        "source_version": source_version,
        "evidence_id": evidence_id,
        "provenance_status": provenance_status,
        "source_id": _text(
            (raw.get("source_id") if isinstance(raw, Mapping) else None) or code,
            field="provenance.source_id",
        ),
    }


def _edge(
    edge_type: str,
    *,
    provenance: Mapping[str, Any],
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    source = _text(provenance.get("source"), field="edge.source", required=True)
    source_version = _text(provenance.get("source_version"), field="edge.source_version", required=True)
    source_id = _text(provenance.get("source_id"), field="edge.source_id", required=True)
    edge_body = {
        "edge_type": edge_type,
        **{str(key): _json_copy(value, field=f"edge.{key}") for key, value in fields.items()},
        "source": source,
        "source_version": source_version,
        "source_id": source_id,
        "evidence_id": _text(
            provenance.get("evidence_id"),
            field="edge.evidence_id",
            required=True,
        ),
        "provenance_status": _text(
            provenance.get("provenance_status") or "complete",
            field="edge.provenance_status",
            required=True,
        ),
    }
    return edge_body


def _dedupe_edges(edges: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for raw in edges:
        value = _json_copy(dict(raw), field="mapping_evidence")
        unique[canonical_sha256(value)] = value
    return [unique[key] for key in sorted(unique)]


def _instrument_refs(row: Mapping[str, Any]) -> list[str]:
    return _ref_values(
        row,
        (
            "theme_ids",
            "themes",
            "theme_id",
            "theme_names",
            "theme_aliases",
            "tracking_theme_ids",
            "tracking_themes",
        ),
    )


def _block_refs(row: Mapping[str, Any]) -> list[str]:
    return [
        _code(value, field="block_code")
        for value in _ref_values(
            row,
            (
                "block_codes",
                "block_ids",
                "blocks",
                "category_codes",
                "category_ids",
                "tracking_block_codes",
                "tracked_blocks",
                "underlying_blocks",
            ),
        )
        if _code(value, field="block_code")
    ]


def _constituent_refs(row: Mapping[str, Any]) -> list[str]:
    return [
        _code(value, field="constituent_code")
        for value in _string_values(
            row.get("constituents") or row.get("constituent_codes") or row.get("members"),
            code_keys=("code", "stockCode", "stockId", "instrument_code"),
        )
        if _code(value, field="constituent_code")
    ]


def _normalize_row(row: Mapping[str, Any], *, kind: str, version: str) -> dict[str, Any] | None:
    code = _row_code(row, kind=kind)
    if not code:
        return None
    value = _json_copy(dict(row), field=f"{kind}_catalog.row")
    value.update(
        {
            "code": code,
            "name": _row_name(row),
            "theme_refs": _instrument_refs(row),
            "block_refs": _block_refs(row),
            "provenance": _provenance(row, kind=kind, version=version, code=code),
            "catalog_kind": kind,
        }
    )
    if kind == "block":
        value["constituent_refs"] = _constituent_refs(row)
    return value


@dataclass(frozen=True)
class _ThemeDefinition:
    theme_id: str
    display_name: str
    aliases: tuple[dict[str, str], ...]
    block_codes: tuple[str, ...]
    etf_codes: tuple[str, ...]
    stock_codes: tuple[str, ...]


@dataclass(frozen=True)
class _ThemeRegistry:
    version: str
    explicit: bool
    themes: Mapping[str, _ThemeDefinition]
    alias_index: Mapping[str, tuple[str, ...]]
    changes: tuple[dict[str, Any], ...]
    payload: dict[str, Any]


def _registry_theme_rows(raw: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    themes = raw.get("themes") or raw.get("entries") or raw.get("theme_definitions")
    if isinstance(themes, Mapping):
        return [(str(key), value) for key, value in themes.items() if isinstance(value, Mapping)]
    if isinstance(themes, (list, tuple)):
        return [("", value) for value in themes if isinstance(value, Mapping)]
    reserved = {"version", "registry_version", "changes", "change_log", "metadata"}
    if raw and not any(key in raw for key in ("themes", "entries", "theme_definitions")):
        return [
            (str(key), value)
            for key, value in raw.items()
            if str(key) not in reserved and isinstance(value, Mapping)
        ]
    return []


def _alias_rows(
    theme: Mapping[str, Any],
    *,
    theme_id: str,
    change_ids: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, Any]] = []
    raw_aliases = _list(theme.get("aliases") or theme.get("approved_aliases"))
    for raw_alias in raw_aliases:
        if isinstance(raw_alias, Mapping):
            alias = _text(raw_alias.get("alias") or raw_alias.get("value") or raw_alias.get("name"), field="theme.alias")
            status = _text(raw_alias.get("status") or raw_alias.get("review_status"), field="theme.alias.status")
            approved = raw_alias.get("approved")
            confidence = raw_alias.get("confidence")
            if confidence not in (None, ""):
                try:
                    confidence_value = float(confidence)
                except (TypeError, ValueError):
                    confidence_value = -1.0
                if confidence_value < MIN_MAPPING_CONFIDENCE:
                    rejected.append({"theme_id": theme_id, "alias": alias, "reason": "alias_low_confidence"})
                    continue
            if approved is False or (status and status.casefold() not in _APPROVED_ALIAS_STATUSES):
                rejected.append({"theme_id": theme_id, "alias": alias, "reason": "alias_not_approved"})
                continue
            if any(key in raw_alias for key in ("author", "author_id", "kol_id", "source_key")):
                rejected.append({"theme_id": theme_id, "alias": alias, "reason": "author_specific_alias_forbidden"})
                continue
            change_id = _text(raw_alias.get("change_id"), field="theme.alias.change_id")
            if not change_id:
                rejected.append({"theme_id": theme_id, "alias": alias, "reason": "alias_change_record_missing"})
                continue
            if change_id not in change_ids:
                rejected.append(
                    {
                        "theme_id": theme_id,
                        "alias": alias,
                        "reason": "alias_change_record_unknown",
                        "change_id": change_id,
                    }
                )
                continue
            accepted.append(
                {
                    "alias": alias,
                    "change_id": change_id,
                }
            )
        else:
            alias = _text(raw_alias, field="theme.alias")
            if alias:
                rejected.append({"theme_id": theme_id, "alias": alias, "reason": "alias_change_record_missing"})
    return accepted, rejected


def _normalize_registry(raw: Any) -> _ThemeRegistry:
    explicit = raw is not None
    if raw is None:
        payload = {
            "version": IDENTITY_ONLY_REGISTRY_VERSION,
            "themes": [],
            "changes": [],
            "rejected_aliases": [],
        }
        return _ThemeRegistry(
            version=IDENTITY_ONLY_REGISTRY_VERSION,
            explicit=False,
            themes={},
            alias_index={},
            changes=(),
            payload=payload,
        )
    if not isinstance(raw, Mapping):
        raise ThemeInstrumentResolverError("theme_registry must be an object")
    nested = raw.get("theme_registry") or raw.get("registry")
    value = nested if isinstance(nested, Mapping) else raw
    version = _text(value.get("version") or value.get("registry_version"), field="theme_registry.version")
    version = version or "theme-registry-v1"
    changes_raw = value.get("changes") or value.get("change_log") or []
    if not isinstance(changes_raw, (list, tuple)):
        raise ThemeInstrumentResolverError("theme_registry.changes must be a list")
    changes = tuple(_sort_json(_json_copy(list(changes_raw), field="theme_registry.changes")))
    definitions: dict[str, _ThemeDefinition] = {}
    aliases: dict[str, set[str]] = {}
    rejected_aliases: list[dict[str, Any]] = []
    change_ids = {
        _text(change.get("change_id") or change.get("id"), field="theme_registry.changes.change_id")
        for change in changes
        if isinstance(change, Mapping) and (change.get("change_id") or change.get("id"))
    }
    for key, raw_theme in _registry_theme_rows(value):
        theme_id = _text(raw_theme.get("theme_id") or key, field="theme_registry.theme_id", required=True)
        if not _SAFE_THEME_ID.fullmatch(theme_id):
            raise ThemeInstrumentResolverError(f"theme_registry theme_id is invalid: {theme_id}")
        if theme_id in definitions:
            raise ThemeInstrumentResolverError(f"duplicate theme_id in registry: {theme_id}")
        display_name = _text(
            raw_theme.get("display_name") or raw_theme.get("name") or theme_id,
            field=f"theme_registry[{theme_id}].display_name",
            required=True,
        )
        accepted_aliases, rejected = _alias_rows(
            raw_theme,
            theme_id=theme_id,
            change_ids=change_ids,
        )
        rejected_aliases.extend(rejected)
        all_aliases = [{"alias": display_name, "change_id": ""}, *accepted_aliases]
        deduped_aliases: dict[str, dict[str, str]] = {}
        for alias_row in all_aliases:
            normalized = _normalize_alias(alias_row["alias"])
            if normalized:
                deduped_aliases[normalized] = alias_row
        definition = _ThemeDefinition(
            theme_id=theme_id,
            display_name=display_name,
            aliases=tuple(deduped_aliases[key] for key in sorted(deduped_aliases)),
            block_codes=tuple(
                sorted(
                    _code(item, field="theme_registry.block_code")
                    for item in _ref_values(
                        raw_theme,
                        ("block_codes", "block_ids", "blocks", "category_codes", "categories"),
                    )
                    if _code(item, field="theme_registry.block_code")
                )
            ),
            etf_codes=tuple(
                sorted(
                    _code(item, field="theme_registry.etf_code")
                    for item in _ref_values(raw_theme, ("etf_codes", "etfs", "etf_universe"))
                    if _code(item, field="theme_registry.etf_code")
                )
            ),
            stock_codes=tuple(
                sorted(
                    _code(item, field="theme_registry.stock_code")
                    for item in _ref_values(raw_theme, ("stock_codes", "stocks", "trend_stocks"))
                    if _code(item, field="theme_registry.stock_code")
                )
            ),
        )
        definitions[theme_id] = definition
        for alias in definition.aliases:
            normalized = _normalize_alias(alias["alias"])
            aliases.setdefault(normalized, set()).add(theme_id)
    payload_themes: list[dict[str, Any]] = []
    for theme_id in sorted(definitions):
        definition = definitions[theme_id]
        payload_themes.append(
            {
                "theme_id": definition.theme_id,
                "display_name": definition.display_name,
                "aliases": [dict(alias) for alias in definition.aliases],
                "block_codes": list(definition.block_codes),
                "etf_codes": list(definition.etf_codes),
                "stock_codes": list(definition.stock_codes),
            }
        )
    payload = {
        "version": version,
        "themes": payload_themes,
        "changes": list(changes),
        "rejected_aliases": _sort_json(rejected_aliases),
    }
    return _ThemeRegistry(
        version=version,
        explicit=explicit,
        themes=definitions,
        alias_index={key: tuple(sorted(value)) for key, value in aliases.items()},
        changes=changes,
        payload=payload,
    )


@dataclass(frozen=True)
class _Catalog:
    version: str
    registry: _ThemeRegistry
    blocks: tuple[dict[str, Any], ...]
    etfs: tuple[dict[str, Any], ...]
    stocks: tuple[dict[str, Any], ...]
    payload: dict[str, Any]
    digest: str


def _catalog_parts(
    catalog: Any,
    *,
    theme_registry: Any,
    block_catalog: Any,
    etf_catalog: Any,
    stock_catalog: Any,
    trend_stock_catalog: Any,
) -> tuple[Any, Any, Any, Any, str]:
    if catalog is None:
        base: Mapping[str, Any] = {}
    elif isinstance(catalog, Mapping):
        base = catalog
    else:
        raise ThemeInstrumentResolverError("catalog must be an object")
    registry = theme_registry if theme_registry is not None else base.get("theme_registry") or base.get("registry")
    blocks = block_catalog if block_catalog is not None else (
        base.get("block_catalog") or base.get("blocks") or base.get("xiaocao_blocks")
    )
    etfs = etf_catalog if etf_catalog is not None else (
        base.get("etf_catalog") or base.get("etfs") or base.get("etf_universe")
    )
    stocks = stock_catalog
    if stocks is None:
        stocks = trend_stock_catalog
    if stocks is None:
        stocks = base.get("stock_catalog") or base.get("stocks") or base.get("trend_stocks")
    version = _text(base.get("version") or base.get("catalog_version"), field="catalog.version")
    return registry, blocks, etfs, stocks, version or DEFAULT_CATALOG_VERSION


def _normalize_catalog(
    catalog: Any,
    *,
    theme_registry: Any = None,
    block_catalog: Any = None,
    etf_catalog: Any = None,
    stock_catalog: Any = None,
    trend_stock_catalog: Any = None,
) -> _Catalog:
    registry_raw, blocks_raw, etfs_raw, stocks_raw, version = _catalog_parts(
        catalog,
        theme_registry=theme_registry,
        block_catalog=block_catalog,
        etf_catalog=etf_catalog,
        stock_catalog=stock_catalog,
        trend_stock_catalog=trend_stock_catalog,
    )
    registry = _normalize_registry(registry_raw)
    blocks = tuple(
        sorted(
            (
                normalized
                for row in _row_list(blocks_raw, kind="block")
                if (normalized := _normalize_row(row, kind="block", version=version)) is not None
            ),
            key=lambda row: (row["code"], canonical_sha256(row)),
        )
    )
    etfs = tuple(
        sorted(
            (
                normalized
                for row in _row_list(etfs_raw, kind="etf")
                if (normalized := _normalize_row(row, kind="etf", version=version)) is not None
            ),
            key=lambda row: (row["code"], canonical_sha256(row)),
        )
    )
    stocks = tuple(
        sorted(
            (
                normalized
                for row in _row_list(stocks_raw, kind="stock")
                if (normalized := _normalize_row(row, kind="stock", version=version)) is not None
            ),
            key=lambda row: (row["code"], canonical_sha256(row)),
        )
    )
    payload = {
        "version": version,
        "theme_registry": registry.payload,
        "blocks": list(blocks),
        "etfs": list(etfs),
        "stocks": list(stocks),
    }
    return _Catalog(
        version=version,
        registry=registry,
        blocks=blocks,
        etfs=etfs,
        stocks=stocks,
        payload=payload,
        digest=canonical_sha256(payload),
    )


def _snapshot_payload(snapshot: TrendJudgmentSnapshot | Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(snapshot, TrendJudgmentSnapshot):
        return snapshot.to_dict(), snapshot.snapshot_sha256
    if not isinstance(snapshot, Mapping):
        raise ThemeInstrumentResolverError("snapshot must be a TrendJudgmentSnapshot or object")
    try:
        validated = TrendJudgmentSnapshot.from_payload(snapshot)
    except TrendSnapshotError as exc:
        raise ThemeInstrumentResolverError("snapshot must be a valid hash-bound snapshot") from exc
    return validated.to_dict(), validated.snapshot_sha256


def _resolve_theme_identity(
    theme: Mapping[str, Any],
    *,
    registry: _ThemeRegistry,
) -> dict[str, Any]:
    input_id = _text(theme.get("theme_id"), field="snapshot.theme.theme_id", required=True)
    display_name = _text(theme.get("display_name"), field="snapshot.theme.display_name")
    if input_id in registry.themes:
        definition = registry.themes[input_id]
        return {
            "status": "resolved",
            "theme_id": definition.theme_id,
            "display_name": definition.display_name,
            "input_theme_id": input_id,
            "input_display_name": display_name,
            "matched_by": "theme_id",
            "mapping_evidence": [
                _edge(
                    "theme_identity",
                    provenance={
                        "source": "theme_registry",
                        "source_version": registry.version,
                        "source_id": f"theme:{definition.theme_id}",
                        "evidence_id": canonical_sha256(
                            {"registry": registry.version, "theme_id": definition.theme_id}
                        ),
                    },
                    fields={"input_theme_id": input_id, "theme_id": definition.theme_id},
                )
            ],
        }
    if not registry.explicit:
        return {
            "status": "resolved",
            "theme_id": input_id,
            "display_name": display_name or input_id,
            "input_theme_id": input_id,
            "input_display_name": display_name,
            "matched_by": "snapshot_theme_id_identity_only",
            "mapping_evidence": [
                _edge(
                    "theme_identity",
                    provenance={
                        "source": "snapshot_theme_id",
                        "source_version": registry.version,
                        "source_id": input_id,
                        "evidence_id": canonical_sha256(
                            {"theme_id": input_id, "snapshot_identity": True}
                        ),
                    },
                    fields={"input_theme_id": input_id, "theme_id": input_id},
                )
            ],
        }
    candidates: set[str] = set()
    for raw_value in (
        input_id,
        display_name,
        theme.get("theme_expression"),
        theme.get("raw_theme"),
        theme.get("raw_expression"),
        *(_list(theme.get("aliases"))),
    ):
        normalized = _normalize_alias(raw_value)
        candidates.update(registry.alias_index.get(normalized, ()))
    if len(candidates) == 1:
        theme_id = next(iter(candidates))
        definition = registry.themes[theme_id]
        matched_by = "approved_alias"
        if _normalize_alias(input_id) == _normalize_alias(theme_id):
            matched_by = "theme_id"
        return {
            "status": "resolved",
            "theme_id": theme_id,
            "display_name": definition.display_name,
            "input_theme_id": input_id,
            "input_display_name": display_name,
            "matched_by": matched_by,
            "mapping_evidence": [
                _edge(
                    "theme_identity",
                    provenance={
                        "source": "theme_registry",
                        "source_version": registry.version,
                        "source_id": f"theme:{theme_id}",
                        "evidence_id": canonical_sha256(
                            {"registry": registry.version, "theme_id": theme_id}
                        ),
                    },
                    fields={
                        "input_theme_id": input_id,
                        "input_display_name": display_name,
                        "theme_id": theme_id,
                        "matched_by": matched_by,
                    },
                )
            ],
        }
    if not candidates:
        reason = "unknown_theme"
    else:
        reason = "ambiguous_theme_alias"
    return {
        "status": "unresolved",
        "theme_id": None,
        "display_name": display_name or input_id,
        "input_theme_id": input_id,
        "input_display_name": display_name,
        "matched_by": None,
        "reason": reason,
        "candidate_theme_ids": sorted(candidates),
        "mapping_evidence": [],
    }


def _row_mapping_is_confident(row: Mapping[str, Any]) -> bool:
    raw = row.get("mapping_confidence")
    if raw in (None, ""):
        raw = row.get("theme_mapping_confidence")
    if raw in (None, ""):
        raw = row.get("resolution_confidence")
    if raw in (None, ""):
        return True
    try:
        return float(raw) >= MIN_MAPPING_CONFIDENCE
    except (TypeError, ValueError):
        return False


def _row_theme_ids(row: Mapping[str, Any], *, registry: _ThemeRegistry) -> set[str]:
    if not _row_mapping_is_confident(row):
        return set()
    resolved: set[str] = set()
    for raw in row.get("theme_refs") or []:
        if raw in registry.themes:
            resolved.add(raw)
            continue
        candidates = registry.alias_index.get(_normalize_alias(raw), ())
        if len(candidates) == 1:
            resolved.add(candidates[0])
        elif not registry.explicit:
            resolved.add(raw)
    return resolved


def _registry_provenance(registry: _ThemeRegistry, theme_id: str) -> dict[str, str]:
    return {
        "source": "theme_registry",
        "source_version": registry.version,
        "source_id": f"theme:{theme_id}",
        "evidence_id": canonical_sha256({"registry": registry.version, "theme_id": theme_id}),
    }


def _row_instrument_type(row: Mapping[str, Any], *, kind: str) -> str:
    explicit = _text(row.get("instrument_type") or row.get("type"), field="instrument_type").casefold()
    if explicit in {"etf", "fund", "exchange_traded_fund"}:
        return "etf"
    if explicit in {"equity", "stock", "share"}:
        return "equity"
    return "etf" if kind == "etf" else "equity"


def _theme_instrument_edge_type(kind: str) -> str:
    return "theme_to_etf" if kind == "etf" else "theme_to_stock"


def _block_instrument_edge_type(kind: str) -> str:
    return "block_to_etf" if kind == "etf" else "block_to_stock"


def _market_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("market_data_contract") or row.get("quote_contract") or row.get("market_contract")
    if isinstance(raw, Mapping):
        return _json_copy(dict(raw), field="market_data_contract")
    if raw in (None, ""):
        return {"status": "unknown", "reason": "market_data_contract_missing"}
    return {"status": str(raw).strip()}


def _contract_component_verified(value: Any, *, require_trade_field: bool = False) -> bool:
    if isinstance(value, Mapping):
        status = _text(value.get("status"), field="market_data_contract.component.status").casefold()
        verified = value.get("verified") is True
        if status != "verified" and not verified:
            return False
        if require_trade_field:
            price_field = _text(
                value.get("price_field") or value.get("trade_field"),
                field="market_data_contract.minute.price_field",
            ).casefold()
            return price_field == "trade"
        return True
    return value is True or str(value).strip().casefold() == "verified"


def _etf_contract_reasons(contract: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    status = _text(contract.get("status"), field="market_data_contract.status").casefold()
    if status not in _ETF_MARKET_DATA_OK_STATUSES:
        reasons.extend(["etf_market_data_contract_unverified", "market_data_contract_unverified"])
    if not _contract_component_verified(contract.get("realtime")):
        reasons.append("etf_realtime_contract_unverified")
    if not _contract_component_verified(contract.get("minute"), require_trade_field=True):
        reasons.append("etf_minute_contract_unverified_or_wrong_price_field")
    if not (
        _contract_component_verified(contract.get("daily"))
        or _contract_component_verified(contract.get("settlement_data"))
        or _contract_component_verified(contract.get("settlement"))
    ):
        reasons.append("etf_daily_settlement_contract_unverified")
    if not _contract_component_verified(contract.get("fill") or contract.get("fill_semantics")):
        reasons.append("etf_fill_contract_unverified")
    return reasons


def _fee_rate(row: Mapping[str, Any], side: str) -> float | None:
    direct = _number(row.get(f"{side}_fee_rate"))
    if direct is not None:
        return float(direct)
    fees = row.get("fees") or row.get("fee_contract") or row.get("transaction_cost")
    if not isinstance(fees, Mapping):
        return None
    value = fees.get(f"{side}_fee_rate")
    if value in (None, ""):
        value = fees.get(side)
    if isinstance(value, Mapping):
        nested_value = value.get("fee_rate")
        if nested_value in (None, ""):
            nested_value = value.get("rate")
        if nested_value in (None, ""):
            nested_value = value.get("commission")
        value = nested_value
    parsed = _number(value)
    return float(parsed) if parsed is not None else None


def _etf_liquidity_status(row: Mapping[str, Any]) -> str:
    value = row.get("liquidity_status") or row.get("liquidityStatus")
    liquidity = row.get("liquidity")
    if value in (None, "") and isinstance(liquidity, Mapping):
        value = liquidity.get("status")
    return _text(value, field="instrument.liquidity_status").casefold()


def _date_only(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        text = text[:10]
    elif len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _settlement_key(value: Any) -> str:
    text = str(value or "").strip().casefold().replace(" ", "").replace("_", "").replace("-", "")
    if text in {"t+0", "t0", "0", "sameday"}:
        return "T+0"
    if text in {"t+1", "t1", "1", "nextday"}:
        return "T+1"
    return ""


def _row_reasons(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("non_tradable_reasons", "not_tradable_reasons", "tradability_reasons"):
        values.extend(str(item).strip() for item in _list(row.get(key)) if str(item).strip())
    for key in ("non_tradable_reason", "not_tradable_reason", "unavailable_reason"):
        if row.get(key) not in (None, ""):
            values.append(str(row[key]).strip())
    if row.get("tradable") is False or row.get("is_tradable") is False:
        values.append("catalog_marks_not_tradable")
    if str(row.get("status") or "").casefold() in {"suspended", "halted", "inactive", "delisted"}:
        values.append(f"instrument_status_{str(row['status']).strip().casefold()}")
    return sorted(set(values))


def _instrument_record(
    *,
    theme: Mapping[str, Any],
    row: Mapping[str, Any],
    kind: str,
    edges: Iterable[Mapping[str, Any]],
    snapshot_eligibility: str,
    snapshot_as_of: str | None = None,
) -> dict[str, Any]:
    code = _code(row.get("code"), field="instrument.code")
    instrument_type = _row_instrument_type(row, kind=kind)
    reasons = _row_reasons(row)
    if instrument_type not in {"etf", "equity"}:
        reasons.append("unsupported_instrument_type")
    if kind == "etf" and instrument_type != "etf":
        reasons.append("etf_catalog_instrument_type_mismatch")
    lot_size = _number(row.get("lot_size") or row.get("board_lot") or row.get("unit_size"))
    settlement_cycle = _text(
        row.get("settlement_cycle") or row.get("settlement") or row.get("t_plus"),
        field="settlement_cycle",
    )
    normalized_catalog_date: str | None = None
    buy_fee_rate: float | None = None
    sell_fee_rate: float | None = None
    if kind == "etf":
        if lot_size is None or not isinstance(lot_size, int) or lot_size <= 0:
            reasons.append("etf_lot_size_unknown")
        normalized_settlement = _settlement_key(settlement_cycle)
        if not settlement_cycle:
            reasons.append("etf_settlement_cycle_unknown")
        elif not normalized_settlement:
            reasons.append("etf_settlement_cycle_invalid")
        else:
            settlement_cycle = normalized_settlement
    else:
        if lot_size is None:
            lot_size = 100
        if not settlement_cycle:
            settlement_cycle = "T+1"
    contract = _market_contract(row)
    status = _text(contract.get("status"), field="market_data_contract.status").casefold()
    if kind == "etf":
        reasons.extend(_etf_contract_reasons(contract))
        buy_fee_rate = _fee_rate(row, "buy")
        sell_fee_rate = _fee_rate(row, "sell")
        if buy_fee_rate is None:
            reasons.append("etf_buy_fee_unknown")
        elif not math.isfinite(buy_fee_rate) or buy_fee_rate < 0:
            reasons.append("etf_buy_fee_invalid")
        if sell_fee_rate is None:
            reasons.append("etf_sell_fee_unknown")
        elif not math.isfinite(sell_fee_rate) or sell_fee_rate < 0:
            reasons.append("etf_sell_fee_invalid")
        catalog_trade_date = _text(
            row.get("catalog_trade_date") or row.get("tradeDate") or row.get("trade_date"),
            field="instrument.catalog_trade_date",
        )
        if not catalog_trade_date:
            reasons.append("etf_catalog_date_unknown")
            normalized_catalog_date = None
        else:
            normalized_catalog_date = _date_only(catalog_trade_date)
            if not normalized_catalog_date:
                reasons.append("etf_catalog_date_invalid")
            elif snapshot_as_of:
                normalized_as_of = _date_only(snapshot_as_of)
                if normalized_as_of:
                    age_days = (
                        date.fromisoformat(normalized_as_of)
                        - date.fromisoformat(normalized_catalog_date)
                    ).days
                    if age_days < 0 or age_days > 1:
                        reasons.append("etf_catalog_stale")
        market_status = _text(
            row.get("market_status")
            or row.get("trading_status")
            or row.get("current_status")
            or row.get("statusType")
            or row.get("status"),
            field="instrument.market_status",
        ).casefold()
        if not market_status:
            reasons.append("etf_market_status_unknown")
        elif market_status in {"halted", "suspended", "stop", "inactive", "delisted", "停牌"}:
            reasons.append("etf_market_status_not_tradable")
        elif market_status not in {"active", "tradable", "trading", "normal", "1", "true", "t"}:
            reasons.append("etf_market_status_unknown")
        liquidity_status = _etf_liquidity_status(row)
        if not liquidity_status:
            reasons.append("etf_liquidity_status_unknown")
        elif liquidity_status in {"illiquid", "insufficient", "blocked", "halted", "suspended"}:
            reasons.append("etf_liquidity_not_sufficient")
        elif liquidity_status not in {"liquid", "ok", "sufficient", "verified"}:
            reasons.append("etf_liquidity_status_unknown")
    elif status not in _MARKET_DATA_OK_STATUSES:
        reasons.append("market_data_contract_unverified")
    if any(edge.get("provenance_status") != "complete" for edge in edges):
        reasons.append("mapping_provenance_incomplete")
    reasons = sorted(set(reasons))
    record = {
        "code": code,
        "name": _row_name(row) or None,
        "instrument_type": instrument_type,
        "theme_id": theme["theme_id"],
        "snapshot_theme_eligibility": snapshot_eligibility,
        "mapping_status": "resolved",
        "mapping_evidence": _dedupe_edges(edges),
        "provenance": _dedupe_edges(edges),
        "lot_size": lot_size,
        "settlement_cycle": settlement_cycle or None,
        "market_data_contract": contract,
        "liquidity": _json_copy(row.get("liquidity"), field="instrument.liquidity") if row.get("liquidity") is not None else None,
        "trend": _json_copy(row.get("trend") or row.get("trend_quality"), field="instrument.trend") if (row.get("trend") or row.get("trend_quality")) is not None else None,
        "relative_strength": row.get("relative_strength"),
        "expression_role": _text(
            row.get("expression_role") or row.get("role"),
            field="instrument.expression_role",
        )
        or ("broad_etf" if instrument_type == "etf" else "core_trend_stock"),
        "non_tradable_reasons": reasons,
        "ineligible_reasons": reasons,
        "instrument_status": "eligible" if not reasons else "ineligible",
        "tradability_status": "eligible" if not reasons else "ineligible",
        "catalog_kind": kind,
        "catalog_provenance": _json_copy(row.get("provenance"), field="catalog_provenance"),
    }
    if instrument_type == "etf":
        output_buy_fee = (
            buy_fee_rate
            if buy_fee_rate is not None and math.isfinite(buy_fee_rate) and buy_fee_rate >= 0
            else None
        )
        output_sell_fee = (
            sell_fee_rate
            if sell_fee_rate is not None and math.isfinite(sell_fee_rate) and sell_fee_rate >= 0
            else None
        )
        record.update({
            "buy_fee_rate": output_buy_fee,
            "sell_fee_rate": output_sell_fee,
            "catalog_trade_date": normalized_catalog_date if instrument_type == "etf" else None,
            "market_status": _text(
                row.get("market_status")
                or row.get("trading_status")
                or row.get("current_status")
                or row.get("statusType")
                or row.get("status"),
                field="instrument.market_status",
            ) or None,
            "liquidity_status": _etf_liquidity_status(row) or None,
        })
    return record


def _row_edge(
    edge_type: str,
    *,
    row: Mapping[str, Any],
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    return _edge(edge_type, provenance=row["provenance"], fields=fields)


def _resolve_theme(
    raw_theme: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    catalog: _Catalog,
    snapshot_as_of: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if identity["status"] != "resolved":
        unresolved = {
            "kind": "theme",
            "input_theme_id": identity["input_theme_id"],
            "input_display_name": identity["input_display_name"],
            "reason": identity["reason"],
            "candidate_theme_ids": identity["candidate_theme_ids"],
        }
        theme_output = {
            **identity,
            "resolution_status": "unresolved",
            "snapshot_eligibility": _text(raw_theme.get("eligibility"), field="snapshot.theme.eligibility") or "wait",
            "instruments": [],
            "mapping_evidence": [],
        }
        return theme_output, [unresolved]

    theme_id = str(identity["theme_id"])
    definition = catalog.registry.themes.get(theme_id)
    block_codes = set(definition.block_codes if definition else ())
    etf_codes = set(definition.etf_codes if definition else ())
    stock_codes = set(definition.stock_codes if definition else ())
    theme_edges = list(identity["mapping_evidence"])
    block_edges: dict[str, list[dict[str, Any]]] = {}
    for block in catalog.blocks:
        relation = theme_id in _row_theme_ids(block, registry=catalog.registry) or block["code"] in block_codes
        if not relation:
            continue
        edges: list[dict[str, Any]] = []
        if theme_id in _row_theme_ids(block, registry=catalog.registry):
            edges.append(
                _row_edge(
                    "theme_to_block",
                    row=block,
                    fields={"theme_id": theme_id, "block_code": block["code"], "relation": "catalog_theme_ref"},
                )
            )
        if block["code"] in block_codes:
            edges.append(
                _edge(
                    "theme_to_block",
                    provenance=_registry_provenance(catalog.registry, theme_id),
                    fields={"theme_id": theme_id, "block_code": block["code"], "relation": "registry_mapping"},
                )
            )
        block_edges[block["code"]] = _dedupe_edges(edges)
        theme_edges.extend(edges)

    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []

    def add_candidate(
        row: Mapping[str, Any],
        *,
        kind: str,
        edges: Iterable[Mapping[str, Any]],
    ) -> None:
        row_code = _code(row.get("code"), field="instrument.code")
        if not row_code:
            return
        instrument_type = _row_instrument_type(row, kind=kind)
        key = (row_code, instrument_type)
        normalized_edges = _dedupe_edges(edges)
        existing = candidates.get(key)
        if existing is None:
            candidates[key] = {"row": dict(row), "kind": kind, "edges": normalized_edges}
            return
        existing["edges"] = _dedupe_edges([*existing["edges"], *normalized_edges])
        # Rows are pre-sorted, so selecting the lexicographically first
        # normalized row is independent of the caller's catalog order.
        if canonical_sha256(dict(row)) < canonical_sha256(existing["row"]):
            existing["row"] = dict(row)

    for kind, rows, direct_codes in (
        ("etf", catalog.etfs, etf_codes),
        ("stock", catalog.stocks, stock_codes),
    ):
        for row in rows:
            row_theme_ids = _row_theme_ids(row, registry=catalog.registry)
            row_mapping_confident = _row_mapping_is_confident(row)
            row_block_refs = set(row.get("block_refs") or []) if row_mapping_confident else set()
            direct = row["code"] in direct_codes
            matching_blocks = sorted(row_block_refs.intersection(block_edges))
            if theme_id not in row_theme_ids and not matching_blocks and not direct:
                if not row_mapping_confident and (
                    theme_id in row.get("theme_refs", [])
                    or set(row.get("block_refs") or []).intersection(block_edges)
                ):
                    unresolved.append(
                        {
                            "kind": "instrument_mapping",
                            "theme_id": theme_id,
                            "instrument_code": row["code"],
                            "reason": "low_confidence_mapping",
                        }
                    )
                continue
            edges: list[dict[str, Any]] = []
            if theme_id in row_theme_ids:
                edges.append(
                    _row_edge(
                        _theme_instrument_edge_type(kind),
                        row=row,
                        fields={"theme_id": theme_id, "instrument_code": row["code"], "instrument_type": _row_instrument_type(row, kind=kind)},
                    )
                )
            if direct:
                edges.append(
                    _edge(
                        _theme_instrument_edge_type(kind),
                        provenance=_registry_provenance(catalog.registry, theme_id),
                        fields={"theme_id": theme_id, "instrument_code": row["code"], "instrument_type": _row_instrument_type(row, kind=kind), "relation": "registry_mapping"},
                    )
                )
            for block_code in matching_blocks:
                edges.append(
                    _row_edge(
                        _block_instrument_edge_type(kind),
                        row=row,
                        fields={"theme_id": theme_id, "block_code": block_code, "instrument_code": row["code"], "instrument_type": _row_instrument_type(row, kind=kind)},
                    )
                )
                edges.extend(block_edges[block_code])
            add_candidate(row, kind=kind, edges=[*theme_edges, *edges])

        present_codes = {
            _code(row.get("code"), field="instrument.code")
            for row in rows
            if _code(row.get("code"), field="instrument.code") in direct_codes
        }
        for direct_code in sorted(direct_codes - present_codes):
            add_candidate(
                {
                    "code": direct_code,
                    "name": "",
                    "theme_refs": [],
                    "block_refs": [],
                    "provenance": {
                        **_registry_provenance(catalog.registry, theme_id),
                        "source_id": direct_code,
                    },
                    "catalog_kind": kind,
                    "_synthetic_from_registry": True,
                },
                kind=kind,
                edges=[
                    *theme_edges,
                    _edge(
                        _theme_instrument_edge_type(kind),
                        provenance=_registry_provenance(catalog.registry, theme_id),
                        fields={
                            "theme_id": theme_id,
                            "instrument_code": direct_code,
                            "instrument_type": "etf" if kind == "etf" else "equity",
                            "relation": "registry_mapping_missing_catalog_row",
                        },
                    ),
                ],
            )

    stock_by_code = {row["code"]: row for row in catalog.stocks}
    for block_code, edges in sorted(block_edges.items()):
        block = next(row for row in catalog.blocks if row["code"] == block_code)
        for constituent_code in block.get("constituent_refs") or []:
            stock = stock_by_code.get(constituent_code)
            if stock is None:
                stock = {
                    "code": constituent_code,
                    "name": "",
                    "theme_refs": [],
                    "block_refs": [block_code],
                    "provenance": block["provenance"],
                    "catalog_kind": "stock",
                    "_synthetic_from_block": True,
                }
            add_candidate(
                stock,
                kind="stock",
                edges=[
                    *theme_edges,
                    *edges,
                    _row_edge(
                        "block_to_stock",
                        row=block,
                        fields={"theme_id": theme_id, "block_code": block_code, "instrument_code": constituent_code},
                    ),
                ],
            )

    instruments: list[dict[str, Any]] = []
    for key in sorted(candidates):
        candidate = candidates[key]
        instruments.append(
            _instrument_record(
                theme={"theme_id": theme_id},
                row=candidate["row"],
                kind=candidate["kind"],
                edges=candidate["edges"],
                snapshot_eligibility=_text(raw_theme.get("eligibility"), field="snapshot.theme.eligibility") or "wait",
                snapshot_as_of=snapshot_as_of,
            )
        )
    if not instruments:
        unresolved.append(
            {
                "kind": "theme_mapping",
                "theme_id": theme_id,
                "reason": "no_block_etf_or_stock_mapping",
            }
        )
    instruments.sort(key=lambda row: (row["code"], row["instrument_type"]))
    theme_output = {
        "theme_id": theme_id,
        "display_name": identity["display_name"],
        "snapshot_display_name": identity["input_display_name"],
        "snapshot_eligibility": _text(raw_theme.get("eligibility"), field="snapshot.theme.eligibility") or "wait",
        "resolution_status": "resolved",
        "matched_by": identity["matched_by"],
        "mapping_evidence": _dedupe_edges(theme_edges),
        "instruments": instruments,
    }
    return theme_output, unresolved


@dataclass(frozen=True)
class ThemeInstrumentUniverse(Mapping[str, Any]):
    """Immutable, hash-bound output of the Book T theme resolver."""

    _canonical_payload: str
    universe_sha256: str
    snapshot_sha256: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ThemeInstrumentUniverse":
        if not isinstance(payload, Mapping):
            raise ThemeInstrumentResolverError("universe payload must be an object")
        value = _json_copy(dict(payload), field="universe payload")
        expected = _text(value.get("universe_sha256"), field="universe_sha256", required=True)
        snapshot_sha = _text(value.get("snapshot_sha256"), field="snapshot_sha256", required=True)
        body = copy.deepcopy(value)
        body.pop("universe_sha256", None)
        receipt = body.get("binding_receipt")
        if isinstance(receipt, Mapping):
            receipt = dict(receipt)
            if receipt.get("universe_sha256") != expected:
                raise ThemeInstrumentResolverError("binding receipt universe hash does not match payload")
            receipt.pop("universe_sha256", None)
            body["binding_receipt"] = receipt
        if canonical_sha256(body) != expected:
            raise ThemeInstrumentResolverError("universe hash does not match payload")
        return cls(
            _canonical_payload=json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            universe_sha256=expected,
            snapshot_sha256=snapshot_sha,
        )

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self._canonical_payload)
        if not isinstance(value, dict):
            raise ThemeInstrumentResolverError("universe payload is not an object")
        return value

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def __hash__(self) -> int:
        return hash(self.universe_sha256)


class ThemeInstrumentResolver:
    """Resolver adapter holding one normalized, immutable catalog view."""

    def __init__(
        self,
        catalog: Mapping[str, Any] | None = None,
        *,
        theme_registry: Any = None,
        block_catalog: Any = None,
        etf_catalog: Any = None,
        stock_catalog: Any = None,
        trend_stock_catalog: Any = None,
    ) -> None:
        self._catalog = _normalize_catalog(
            catalog,
            theme_registry=theme_registry,
            block_catalog=block_catalog,
            etf_catalog=etf_catalog,
            stock_catalog=stock_catalog,
            trend_stock_catalog=trend_stock_catalog,
        )

    def resolve(self, snapshot: TrendJudgmentSnapshot | Mapping[str, Any]) -> ThemeInstrumentUniverse:
        snapshot_value, snapshot_sha = _snapshot_payload(snapshot)
        raw_themes = snapshot_value.get("themes")
        if not isinstance(raw_themes, list):
            raise ThemeInstrumentResolverError("snapshot.themes must be a list")
        themes: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for raw_theme in raw_themes:
            if not isinstance(raw_theme, Mapping):
                raise ThemeInstrumentResolverError("snapshot.themes entries must be objects")
            identity = _resolve_theme_identity(raw_theme, registry=self._catalog.registry)
            theme_output, theme_unresolved = _resolve_theme(
                raw_theme,
                identity=identity,
                catalog=self._catalog,
                snapshot_as_of=str(snapshot_value.get("as_of") or "") or None,
            )
            themes.append(theme_output)
            unresolved.extend(theme_unresolved)
        themes.sort(key=lambda theme: (str(theme.get("theme_id") or ""), str(theme.get("input_theme_id") or "")))
        flat_instruments = [
            instrument
            for theme in themes
            for instrument in theme.get("instruments", [])
        ]
        flat_instruments.sort(key=lambda row: (str(row["theme_id"]), row["code"], row["instrument_type"]))
        body: dict[str, Any] = {
            "schema_version": UNIVERSE_SCHEMA_VERSION,
            "resolver_version": RESOLVER_VERSION,
            "snapshot_sha256": snapshot_sha,
            "catalog_sha256": self._catalog.digest,
            "catalog_version": self._catalog.version,
            "registry_version": self._catalog.registry.version,
            "theme_registry": self._catalog.registry.payload,
            "themes": themes,
            "instruments": flat_instruments,
            "unresolved": _sort_json(unresolved),
            "binding_receipt": {
                "status": "validated",
                "snapshot_sha256": snapshot_sha,
                "catalog_sha256": self._catalog.digest,
                "catalog_version": self._catalog.version,
                "resolver_version": RESOLVER_VERSION,
            },
        }
        universe_sha = canonical_sha256(body)
        payload = {
            **body,
            "universe_sha256": universe_sha,
            "binding_receipt": {**body["binding_receipt"], "universe_sha256": universe_sha},
        }
        return ThemeInstrumentUniverse.from_payload(payload)


def resolve_theme_instruments(
    snapshot: TrendJudgmentSnapshot | Mapping[str, Any],
    catalog: Mapping[str, Any] | None = None,
    *,
    theme_registry: Any = None,
    block_catalog: Any = None,
    etf_catalog: Any = None,
    stock_catalog: Any = None,
    trend_stock_catalog: Any = None,
) -> ThemeInstrumentUniverse:
    """Resolve one frozen snapshot into a deterministic instrument universe.

    ``catalog`` is a pure data payload.  For callers that already keep the
    sources separate, the keyword catalog arguments are accepted as adapters;
    they are normalized into the same canonical representation.  An omitted
    catalog is safe: snapshot theme identities are retained, but no instrument
    is invented and each theme records an unresolved mapping reason.
    """

    return ThemeInstrumentResolver(
        catalog,
        theme_registry=theme_registry,
        block_catalog=block_catalog,
        etf_catalog=etf_catalog,
        stock_catalog=stock_catalog,
        trend_stock_catalog=trend_stock_catalog,
    ).resolve(snapshot)


__all__ = [
    "RESOLVER_VERSION",
    "ThemeInstrumentResolver",
    "ThemeInstrumentResolverError",
    "ThemeInstrumentUniverse",
    "resolve_theme_instruments",
]
