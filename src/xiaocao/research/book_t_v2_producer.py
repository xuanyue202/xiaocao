"""Production-owned Book T v2 shadow-day producer.

This is the single deep adapter behind the morning shell hook.  It assembles
published KOL readbacks, the reviewed theme registry, current catalog facts,
the paper Book T portfolio, the dated v1 control receipt, and the selector's
hash-bound plan.  It never computes a fill itself: a v1 trade is reused only
as a canonical readback; otherwise the v2 action is an explicit skip/block.

The ``capsule`` argument is an injected adapter used by isolated integration
tests.  It has the same shape as the real source readbacks and is never read
by the normal production path.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import date as calendar_date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from xiaocao.kol.publication import PublicationLedger, canonical_sha256
from xiaocao.research.book_t_v2_lifecycle import (
    BookTV2EvidenceError,
    append_events,
    build_daily_mark_event,
    build_initial_lifecycle,
    lifecycle_summary,
    validate_lifecycle,
)
from xiaocao.research.book_t_shadow import bind_book_t_shadow_input
from xiaocao.strategy.book_t_selector import select_book_t
from xiaocao.strategy.theme_instrument_resolver import resolve_theme_instruments
from xiaocao.strategy.trend_snapshot import build_trend_snapshot


BOOK_T_V2_PRODUCER_VERSION = "book-t-v2-production-adapters-v1"
BOOK_T_V2_INPUT_SCHEMA_VERSION = 1
BOOK_T_V2_SHADOW_INPUT_PATH = "output/live/book_t_v2_shadow_input_{date}.json"
BOOK_T_V2_RESEARCH_DIR = "output/research/book_t_v2_shadow"
BOOK_T_V2_CALENDAR_PATH = "output/live/book_t_v2_trading_calendar.json"

_ZERO_MUTATIONS = {"positions": 0, "account": 0, "trades": 0}


class BookTV2ProducerError(RuntimeError):
    """The production adapter cannot create an honest dated input."""


def _copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise BookTV2ProducerError("producer payload must be canonical JSON") from exc


def _text(value: Any) -> str:
    return str(value or "").strip()


def _date(value: Any) -> str:
    text = _text(value)
    try:
        calendar_date.fromisoformat(text[:10])
    except ValueError as exc:
        raise BookTV2ProducerError(f"invalid producer date: {value!r}") from exc
    return text[:10]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BookTV2ProducerError(f"cannot read JSON source {path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BookTV2ProducerError(f"cannot read JSONL source {path}: {exc}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BookTV2ProducerError(f"invalid JSONL source {path}:{number}") from exc
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _calendar_date(row: Mapping[str, Any]) -> str | None:
    value = row.get("calDate") or row.get("tradeDate") or row.get("date") or row.get("day")
    if value is None:
        return None
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _is_open(row: Mapping[str, Any]) -> bool:
    value = row.get("isOpen")
    if value is None:
        value = row.get("is_open")
    return value in {1, "1", True, "true", "TRUE", "open", "OPEN"}


def _normal_code(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("code")
        or row.get("block_code")
        or row.get("blockCode")
        or row.get("category_code")
        or row.get("categoryCode")
        or row.get("stockId")
        or row.get("stockCode")
        or row.get("fundCode")
    )


def _normal_catalog_rows(rows: Any, *, instrument_type: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = _copy(dict(raw))
        code = _normal_code(row)
        if not code:
            continue
        row["code"] = code
        if instrument_type == "block":
            row.setdefault("block_code", code)
        row.setdefault("instrument_type", instrument_type)
        normalized.append(row)
    return normalized


def _load_receipt(root: Path, date_iso: str) -> dict[str, Any]:
    path = root / f"output/live/book_t_v1_control_receipt_{date_iso}.json"
    receipt = _read_json(path)
    if not isinstance(receipt, dict):
        raise BookTV2ProducerError(f"dated v1 control receipt is not an object: {path}")
    unsigned = dict(receipt)
    actual = _text(unsigned.pop("receipt_sha256", ""))
    if not actual or actual != canonical_sha256(unsigned):
        raise BookTV2ProducerError(f"dated v1 control receipt failed integrity validation: {path}")
    if _text(receipt.get("as_of"))[:10] != date_iso:
        raise BookTV2ProducerError(f"dated v1 control receipt is not for {date_iso}")
    semantics = receipt.get("daily_semantics")
    semantics_hash = _text(receipt.get("daily_semantics_sha256"))
    if not isinstance(semantics, Mapping) or semantics_hash != canonical_sha256(semantics):
        raise BookTV2ProducerError(
            "dated v1 control receipt has no exact daily decision/action/fill semantics"
        )
    if _text(semantics.get("as_of"))[:10] != date_iso:
        raise BookTV2ProducerError("dated v1 control semantics are not for the receipt date")
    selection = semantics.get("selection")
    if not isinstance(selection, Mapping) or _text(selection.get("as_of"))[:10] != date_iso:
        raise BookTV2ProducerError("dated v1 control selection semantics are not date-bound")
    artifact_paths = receipt.get("artifact_paths")
    artifact_hashes = receipt.get("artifact_hashes")
    expected_paths = {
        "positions": "output/live/positions.jsonl",
        "account": "output/live/paper_account_T.json",
        "trades": "output/live/paper_trades.jsonl",
    }
    if not isinstance(artifact_paths, Mapping) or not isinstance(artifact_hashes, Mapping):
        raise BookTV2ProducerError("dated v1 control receipt is missing artifact bindings")
    for name, relative in expected_paths.items():
        if _text(artifact_paths.get(name)) != relative:
            raise BookTV2ProducerError(f"dated v1 control receipt path mismatch for {name}")
        target = root / relative
        if not target.exists():
            raise BookTV2ProducerError(f"dated v1 control artifact is missing: {target}")
        actual_artifact_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_artifact_hash != _text(artifact_hashes.get(name)).lower():
            raise BookTV2ProducerError(f"dated v1 control artifact changed after receipt: {name}")
    return receipt


def _load_publications(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    ledger = PublicationLedger(root / "output/live/kol_daily/publications")
    try:
        events = ledger.events()
    except Exception as exc:
        return [], [f"publication_ledger_read:{type(exc).__name__}"]
    keys = sorted({_text(row.get("publication_key")) for row in events if _text(row.get("publication_key"))})
    readbacks: list[dict[str, Any]] = []
    errors: list[str] = []
    for key in keys:
        try:
            status = ledger.status(key)
        except Exception as exc:
            errors.append(f"publication_status:{key}:{type(exc).__name__}")
            continue
        if status.get("completed") is True:
            artifact = status.get("artifact")
            records = artifact.get("records", []) if isinstance(artifact, Mapping) else []
            viewpoint_count = sum(
                1
                for row in records
                if isinstance(row, Mapping) and _text(row.get("kind")) == "viewpoint"
            )
            evaluation_count = sum(
                1
                for row in records
                if isinstance(row, Mapping) and _text(row.get("kind")) == "viewpoint_evaluation"
            )
            if viewpoint_count == 1 and evaluation_count == 1:
                readbacks.append(status)
            else:
                errors.append(
                    f"publication_shape_skipped:{key}:viewpoints={viewpoint_count}:evaluations={evaluation_count}"
                )
    return readbacks, errors


def _load_dated_optional(root: Path, stem: str, date_iso: str) -> Any | None:
    path = root / f"output/live/{stem}_{date_iso}.json"
    if not path.exists():
        return None
    return _read_json(path)


def _load_portfolio(root: Path) -> dict[str, Any]:
    live = root / "output/live"
    account_path = live / "paper_account_T.json"
    account = _read_json(account_path) if account_path.exists() else {}
    if not isinstance(account, dict):
        account = {}
    positions = [
        row
        for row in _read_jsonl(live / "positions.jsonl")
        if _text(row.get("book")) == "T" and _text(row.get("status") or "open").lower() == "open"
    ]
    cash = float(account.get("cash") or 0.0)
    open_cost = sum(float(row.get("gross_notional") or row.get("entry_cash_out") or 0.0) for row in positions)
    return {
        "as_of": None,
        "book": "T",
        "account_equity": round(cash + open_cost, 8),
        "account": _copy(account),
        "positions": _copy(positions),
        "source": "output/live/paper_account_T.json+positions.jsonl",
        "formal_ledger_mutations": _copy(_ZERO_MUTATIONS),
    }


def _load_real_sources(root: Path, date_iso: str, *, client: Any = None) -> dict[str, Any]:
    """Read production adapters with bounded, cache-aware degradation."""

    errors: list[str] = []
    publications, publication_errors = _load_publications(root)
    errors.extend(publication_errors)
    registry_path = root / "reference/experience/book_t_v2_theme_registry.json"
    if not registry_path.exists():
        raise BookTV2ProducerError(f"reviewed theme registry is missing: {registry_path}")
    registry = _read_json(registry_path)
    if not isinstance(registry, dict):
        raise BookTV2ProducerError("reviewed theme registry is not an object")
    client = client
    etfs: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    stocks: list[dict[str, Any]] = []
    calendar_rows: list[dict[str, Any]] = []
    if client is None:
        try:
            from xiaocao.api.client import XiaocaoClient

            client = XiaocaoClient()
        except Exception as exc:
            errors.append(f"api_client_init:{type(exc).__name__}")
    if client is not None:
        try:
            etfs = _normal_catalog_rows(client.etf_info(date_iso), instrument_type="etf")
        except Exception as exc:
            errors.append(f"etf_catalog:{type(exc).__name__}")
        try:
            blocks = _normal_catalog_rows(
                client.get_block_category_rank_v3(date_iso, model=0),
                instrument_type="block",
            )
        except Exception as exc:
            errors.append(f"block_catalog:{type(exc).__name__}")
        try:
            stocks = _normal_catalog_rows(client.stock_info(), instrument_type="equity")
        except Exception as exc:
            errors.append(f"stock_catalog:{type(exc).__name__}")
        try:
            calendar_rows = [
                dict(row)
                for row in client.get_trade_cal("2020-01-01", date_iso, "SSE", 1)
                if isinstance(row, Mapping)
            ]
        except Exception as exc:
            errors.append(f"trading_calendar:{type(exc).__name__}")
    calendar_dates = sorted(
        {
            day
            for row in calendar_rows
            if _is_open(row)
            for day in [_calendar_date(row)]
            if day and day <= date_iso
        }
    )
    if date_iso not in calendar_dates:
        cached_calendar = root / BOOK_T_V2_CALENDAR_PATH
        if cached_calendar.exists():
            cached = _read_json(cached_calendar)
            if isinstance(cached, dict):
                calendar_dates = sorted(
                    set(calendar_dates)
                    | {
                        str(day)[:10]
                        for day in cached.get("open_dates", [])
                        if str(day)[:10] <= date_iso
                    }
                )
    if date_iso not in calendar_dates:
        raise BookTV2ProducerError(
            f"authoritative trading calendar does not prove {date_iso}; "
            + (", ".join(sorted(set(errors))) if errors else "no open calendar row")
        )
    _atomic_json(
        root / BOOK_T_V2_CALENDAR_PATH,
        {"source": "p-xcapi", "open_dates": calendar_dates, "as_of": date_iso},
    )
    portfolio = _load_portfolio(root)
    quote_rows = etfs + stocks
    quotes = {
        _normal_code(row): {
            "open": row.get("open"),
            "last": row.get("last") or row.get("trade") or row.get("close"),
            "source": row.get("source") or row.get("provenance", {}).get("source"),
        }
        for row in quote_rows
        if _normal_code(row)
    }
    return {
        "publications": publications,
        "publication_errors": errors,
        "theme_registry": registry,
        "catalog": {
            "version": f"book-t-v2-catalog-{date_iso}",
            "theme_registry": registry,
            "blocks": blocks,
            "etfs": etfs,
            "stocks": stocks,
        },
        "portfolio": portfolio,
        "market_input": {
            "market_date": date_iso,
            "is_trading_day": True,
            "trading_day_index": calendar_dates.index(date_iso),
            "quotes": quotes,
            "liquidity": {
                _normal_code(row): row.get("liquidity") or {"status": "unknown"}
                for row in quote_rows
                if _normal_code(row)
            },
            "source": "p-xcapi_cache_first",
            "calendar_source": "p-xcapi_trade_cal",
        },
        "xiaocao_context": _load_dated_optional(root, "book_t_v2_context", date_iso),
        "agent_draft": _load_dated_optional(root, "book_t_v2_judgment_draft", date_iso)
        or {
            "themes": [],
            "status": "pending_observation",
            "reason": "dated_structured_judgment_draft_unavailable",
        },
        "market_validation": {},
        "adapter_errors": sorted(set(errors)),
    }


def _instrument_map(catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for key in ("etfs", "stocks"):
        for row in catalog.get(key, []) if isinstance(catalog.get(key), list) else []:
            if isinstance(row, Mapping) and _normal_code(row):
                output[_normal_code(row)] = dict(row)
    return output


def _action_codes(plan: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    for raw in plan.get("actions", []):
        if not isinstance(raw, Mapping):
            continue
        action = _text(raw.get("action")).lower()
        code = _text(raw.get("code"))
        if code and action in {"open", "buy", "paired_switch", "replace", "rebalance_buy"}:
            codes.append(code)
    return sorted(set(codes))


def _control_fill_rows(
    receipt: Mapping[str, Any],
    *,
    date_iso: str,
    market_hash: str,
    catalog: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    semantics = receipt["daily_semantics"]
    selection = _copy(dict(semantics["selection"]))
    actions = selection.get("actions") if isinstance(selection.get("actions"), list) else []
    instrument_by_code = _instrument_map(catalog)
    fills: list[dict[str, Any]] = []
    selected_codes = sorted({_text(code) for code in selection.get("selected_codes", []) if _text(code)})
    for raw in actions:
        if not isinstance(raw, Mapping):
            continue
        code = _text(raw.get("code"))
        if not code or str(raw.get("side") or "BUY").upper() != "BUY":
            continue
        kind = _text(raw.get("kind")).lower()
        try:
            raw_price = float(raw.get("price")) if raw.get("price") not in (None, "") else None
        except (TypeError, ValueError):
            raw_price = None
        try:
            raw_shares = float(raw.get("shares")) if raw.get("shares") not in (None, "") else None
        except (TypeError, ValueError):
            raw_shares = None
        try:
            raw_notional = float(raw.get("notional")) if raw.get("notional") not in (None, "") else None
        except (TypeError, ValueError):
            raw_notional = None
        try:
            raw_fee = float(raw.get("fee")) if raw.get("fee") not in (None, "") else None
        except (TypeError, ValueError):
            raw_fee = None
        is_fill = (
            kind == "trade"
            and raw_price is not None
            and raw_shares is not None
            and raw_notional is not None
            and raw_fee is not None
            and raw_price > 0
            and raw_shares > 0
            and raw_notional > 0
            and raw_fee >= 0
        )
        instrument = instrument_by_code.get(code, {})
        status = "filled" if is_fill else "skipped"
        row: dict[str, Any] = {
            "as_of": date_iso,
            "market_input_sha256": market_hash,
            "code": code,
            "fill_id": f"v1-control-{_text(raw.get('event_sha256')) or canonical_sha256(raw)}",
            "theme_id": "v1_control",
            "instrument_type": "etf" if _text(instrument.get("instrument_type")).lower() == "etf" else "equity",
            "expression_type": "v1_control",
            "status": status,
            "side": "BUY",
            "fill_price": raw_price if is_fill else None,
            "shares": raw_shares if is_fill else 0.0,
            "notional": raw_notional if is_fill else 0.0,
            "fee": raw_fee if is_fill else 0.0,
            "liquidity_status": "verified" if is_fill else "unavailable",
            "market_contract_status": "verified" if is_fill else "unknown",
            "tradability_status": "eligible" if is_fill else "blocked",
            "market_data_source": "p-xcapi",
            "market_price_field": "trade",
            "skip_reason": None if is_fill else (_text(raw.get("reason")) or "V1_CONTROL_NO_FILL_READBACK"),
        }
        fills.append(row)
    by_code = {str(row["code"]): row for row in fills}
    for code in selected_codes:
        if code not in by_code:
            fills.append(
                {
                    "as_of": date_iso,
                    "market_input_sha256": market_hash,
                    "code": code,
                    "fill_id": f"v1-control-blocked-{code}-{date_iso}",
                    "theme_id": "v1_control",
                    "instrument_type": "equity",
                    "expression_type": "v1_control",
                    "status": "blocked",
                    "skip_reason": "V1_CONTROL_ACTION_READBACK_MISSING",
                }
            )
    selection["as_of"] = date_iso
    return selection, sorted(fills, key=lambda row: (str(row.get("code")), str(row.get("fill_id"))))


def _shadow_fill_rows(
    plan: Mapping[str, Any],
    *,
    date_iso: str,
    market_hash: str,
    catalog: Mapping[str, Any],
    control_fills: list[Mapping[str, Any]],
    source_roles: list[str],
) -> list[dict[str, Any]]:
    instrument_by_code = _instrument_map(catalog)
    control_by_code = {
        _text(row.get("code")): row
        for row in control_fills
        if _text(row.get("code"))
    }
    expression_by_code: dict[str, tuple[str, str]] = {}
    for theme in plan.get("selected_themes", []) if isinstance(plan.get("selected_themes"), list) else []:
        if not isinstance(theme, Mapping):
            continue
        theme_id = _text(theme.get("theme_id")) or "unresolved"
        expression = _text(theme.get("expression_type")) or "unknown"
        for instrument in theme.get("instruments", []) if isinstance(theme.get("instruments"), list) else []:
            if isinstance(instrument, Mapping) and _text(instrument.get("code")):
                expression_by_code[_text(instrument.get("code"))] = (theme_id, expression)
    rows: list[dict[str, Any]] = []
    for code in _action_codes(plan):
        theme_id, expression = expression_by_code.get(code, ("unresolved", "unknown"))
        instrument = instrument_by_code.get(code, {})
        control = control_by_code.get(code)
        is_verified_control_fill = control is not None and _text(control.get("status")).lower() == "filled"
        instrument_type = "etf" if _text(instrument.get("instrument_type")).lower() == "etf" else "equity"
        if is_verified_control_fill and instrument_type != "etf":
            rows.append(
                {
                    **_copy(dict(control)),
                    "fill_id": f"v2-shadow-{date_iso}-{code}",
                    "theme_id": theme_id,
                    "expression_type": expression,
                    "market_input_sha256": market_hash,
                    "source_roles": sorted(source_roles),
                }
            )
            continue
        reason = (
            "V2_ETF_CONTRACT_OR_MARKET_DATA_UNVERIFIED"
            if instrument_type == "etf"
            else "V2_CANONICAL_MARKET_FILL_READBACK_UNAVAILABLE"
        )
        rows.append(
            {
                "as_of": date_iso,
                "market_input_sha256": market_hash,
                "code": code,
                "fill_id": f"v2-shadow-skip-{date_iso}-{code}",
                "theme_id": theme_id,
                "instrument_type": instrument_type,
                "expression_type": expression,
                "status": "blocked",
                "skip_reason": reason,
                "source_roles": sorted(source_roles),
            }
        )
    return sorted(rows, key=lambda row: (str(row.get("code")), str(row.get("fill_id"))))


def _source_roles(snapshot: Mapping[str, Any]) -> list[str]:
    # The snapshot keeps the source identity in its hash-bound input summary.
    summary = snapshot.get("input_summary_sha256")
    return ["published_kol_readback"] if summary else []


def build_book_t_v2_shadow_day(
    root: Path | str,
    date_iso: str,
    *,
    run_mode: str = "real",
    capsule: Mapping[str, Any] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Assemble one frozen v2 input from real adapters or an injected capsule."""

    root = Path(root).resolve()
    day = _date(date_iso)
    mode = _text(run_mode).lower()
    if mode not in {"real", "rehearsal"}:
        raise BookTV2ProducerError("run_mode must be real or rehearsal")
    receipt = _load_receipt(root, day)
    sources = _copy(dict(capsule)) if capsule is not None else _load_real_sources(root, day, client=client)
    market_input = sources.get("market_input")
    if not isinstance(market_input, Mapping):
        raise BookTV2ProducerError("market_input adapter did not return an object")
    market_input = _copy(dict(market_input))
    market_input["market_date"] = day
    market_input["is_trading_day"] = True
    try:
        market_input["trading_day_index"] = int(market_input["trading_day_index"])
    except (TypeError, ValueError) as exc:
        raise BookTV2ProducerError("market_input.trading_day_index is not authoritative") from exc
    as_of = _text(sources.get("as_of")) or f"{day}T01:25:00Z"
    if _date(as_of) != day:
        raise BookTV2ProducerError("producer as_of is not bound to the trading day")
    generated_at = _text(sources.get("generated_at")) or as_of
    publications = sources.get("publications") if isinstance(sources.get("publications"), list) else []
    snapshot = build_trend_snapshot(
        as_of,
        published_sources=publications,
        xiaocao_context=sources.get("xiaocao_context"),
        market_validation=sources.get("market_validation") or {},
        agent_draft=sources.get("agent_draft") or {"themes": []},
        generated_at=generated_at,
    )
    snapshot_value = snapshot.to_dict()
    catalog = sources.get("catalog")
    if not isinstance(catalog, Mapping):
        raise BookTV2ProducerError("catalog adapter did not return an object")
    universe = resolve_theme_instruments(snapshot, catalog)
    portfolio = sources.get("portfolio")
    if not isinstance(portfolio, Mapping):
        raise BookTV2ProducerError("portfolio adapter did not return an object")
    portfolio_value = _copy(dict(portfolio))
    portfolio_value["as_of"] = day
    plan = select_book_t(portfolio_value, snapshot, universe)
    plan_value = plan.to_dict()

    assumptions = {
        "budget_ratio": 0.30,
        "account_equity": float(portfolio_value.get("account_equity") or 100000.0),
        "fee_rate": float(
            portfolio_value.get("account", {}).get("fee_rate")
            if isinstance(portfolio_value.get("account"), Mapping)
            and portfolio_value.get("account", {}).get("fee_rate") not in (None, "")
            else 0.0001
        ),
        "fill_model": "canonical_v1_fill_readback_or_explicit_skip",
        "liquidity_model": "proprietary_current_facts",
        "settlement_model": "instrument_contract",
    }
    market_bound = _copy(market_input)
    market_bound["observed_at"] = as_of
    control_selection, control_fills = _control_fill_rows(
        receipt,
        date_iso=day,
        market_hash="pending",
        catalog=catalog,
    )
    # The market hash is a content hash, so fill rows are finalized only after
    # the market payload is frozen.
    from xiaocao.kol.publication import canonical_sha256 as _sha

    market_hash = _sha(market_bound)
    for row in control_fills:
        row["market_input_sha256"] = market_hash
    shadow_fills = _shadow_fill_rows(
        plan_value,
        date_iso=day,
        market_hash=market_hash,
        catalog=catalog,
        control_fills=control_fills,
        source_roles=_source_roles(snapshot_value),
    )
    control_selection["daily_semantics_sha256"] = _text(receipt["daily_semantics_sha256"])
    control_variant = {
        "selection": control_selection,
        "control_receipt": _copy(dict(receipt)),
        "source_roles": ["v1_control"],
        "expected_fill_codes": sorted({_text(row.get("code")) for row in control_fills if _text(row.get("code"))}),
        "fills": control_fills,
        "holds": [],
        "daily_semantics_sha256": _text(receipt["daily_semantics_sha256"]),
    }
    shadow_variant = {
        "selection_plan": plan_value,
        "source_roles": _source_roles(snapshot_value),
        "expected_fill_codes": sorted({_text(row.get("code")) for row in shadow_fills if _text(row.get("code"))}),
        "fills": shadow_fills,
        "holds": [],
    }
    lifecycle = build_initial_lifecycle(
        decision_id=f"book-t-v2:{day}:{plan_value['selection_plan_sha256'][:16]}",
        as_of=day,
        observed_at=as_of,
        trading_day_index=int(market_bound["trading_day_index"]),
        run_mode=mode,
        snapshot_sha256=_text(plan_value.get("snapshot_sha256")),
        universe_sha256=_text(plan_value.get("universe_sha256")),
        selection_plan_sha256=_text(plan_value.get("selection_plan_sha256")),
        portfolio_sha256=_text(plan_value.get("portfolio_sha256")),
        control_receipt_sha256=_text(receipt.get("receipt_sha256")),
        fills=shadow_fills,
        daily_reevaluation_complete=plan_value.get("daily_reevaluation_complete") is True,
    )
    body = {
        "schema_version": BOOK_T_V2_INPUT_SCHEMA_VERSION,
        "namespace": "book_t_v2_shadow_input",
        "as_of": as_of,
        "market_input": market_bound,
        "assumptions": assumptions,
        "control": control_variant,
        "shadow": shadow_variant,
        "evidence_lifecycle": lifecycle,
        "bindings": {
            "snapshot": snapshot_value,
            "universe": universe.to_dict(),
            "selection_plan": plan_value,
            "portfolio": portfolio_value,
        },
        "producer": {
            "version": BOOK_T_V2_PRODUCER_VERSION,
            "run_mode": mode,
            "source_readbacks": {
                "published_kol_count": len(publications),
                "theme_registry_version": catalog.get("theme_registry", {}).get("version") if isinstance(catalog.get("theme_registry"), Mapping) else None,
                "catalog_version": catalog.get("version"),
                "v1_control_receipt_sha256": receipt.get("receipt_sha256"),
            },
            "adapter_errors": sorted({_text(error) for error in sources.get("adapter_errors", []) if _text(error)}),
        },
    }
    try:
        return bind_book_t_shadow_input(body)
    except (ValueError, KeyError, TypeError) as exc:
        raise BookTV2ProducerError(f"producer assembled an invalid frozen input: {exc}") from exc


def prepare_book_t_v2_shadow_day(
    root: Path | str,
    date_iso: str,
    *,
    run_mode: str = "real",
    capsule: Mapping[str, Any] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Create an idempotent dated input and a small producer readback."""

    root = Path(root).resolve()
    day = _date(date_iso)
    frozen = build_book_t_v2_shadow_day(
        root,
        day,
        run_mode=run_mode,
        capsule=capsule,
        client=client,
    )
    input_path = root / BOOK_T_V2_SHADOW_INPUT_PATH.format(date=day)
    if input_path.exists():
        existing = _read_json(input_path)
        if not isinstance(existing, Mapping) or _text(existing.get("input_sha256")) != _text(frozen.get("input_sha256")):
            raise BookTV2ProducerError(f"dated shadow input already exists with a different identity: {input_path}")
    else:
        _atomic_json(input_path, frozen)
    lifecycle = validate_lifecycle(frozen["evidence_lifecycle"])
    readback = {
        "schema_version": 1,
        "producer": BOOK_T_V2_PRODUCER_VERSION,
        "as_of": day,
        "input_sha256": frozen["input_sha256"],
        "decision_id": lifecycle["decision_id"],
        "run_mode": lifecycle["run_mode"],
        "outcome_status": lifecycle["outcome_status"],
        "intended_actions": len(frozen["shadow"]["expected_fill_codes"]),
        "fill_or_skip_rows": len(frozen["shadow"]["fills"]),
        "formal_ledger_mutations": _copy(_ZERO_MUTATIONS),
        "adapter_errors": frozen.get("producer", {}).get("adapter_errors", []),
    }
    _atomic_json(root / f"output/live/book_t_v2_shadow_producer_{day}.json", readback)
    return {"input": input_path, "readback": root / f"output/live/book_t_v2_shadow_producer_{day}.json", **readback}


def record_book_t_v2_daily_mark(
    root: Path | str,
    date_iso: str,
    *,
    marks: list[Mapping[str, Any]] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Append a close mark for the immutable morning decision."""

    root = Path(root).resolve()
    day = _date(date_iso)
    input_path = root / BOOK_T_V2_SHADOW_INPUT_PATH.format(date=day)
    frozen = _read_json(input_path)
    if not isinstance(frozen, Mapping):
        raise BookTV2ProducerError("frozen shadow input is not an object")
    lifecycle = validate_lifecycle(frozen.get("evidence_lifecycle") or {})
    mark_rows = [_copy(dict(row)) for row in (marks or [])]
    if marks is None:
        filled_codes = [
            _text(row.get("code"))
            for row in frozen.get("shadow", {}).get("fills", [])
            if isinstance(row, Mapping) and _text(row.get("status")).lower() == "filled"
        ]
        if client is None and filled_codes:
            try:
                from xiaocao.api.client import XiaocaoClient

                client = XiaocaoClient()
            except Exception:
                client = None
        if client is not None:
            for code in filled_codes:
                try:
                    bars = client.minute_line(code, trade_date=day, count=241)
                    rows = bars if isinstance(bars, list) else []
                    priced = [row for row in rows if isinstance(row, Mapping) and row.get("trade") not in (None, "")]
                    latest = priced[-1] if priced else None
                    mark_rows.append(
                        {
                            "as_of": day,
                            "code": code,
                            "price": latest.get("trade") if latest else None,
                            "status": "observed" if latest else "unavailable",
                            "source": "p-xcapi.minute_line.trade" if latest else "p-xcapi.minute_line_unavailable",
                        }
                    )
                except Exception as exc:
                    mark_rows.append(
                        {
                            "as_of": day,
                            "code": code,
                            "status": "unavailable",
                            "reason": f"MARKET_MARK_UNAVAILABLE:{type(exc).__name__}",
                            "source": "p-xcapi.minute_line",
                        }
                    )
        for code in filled_codes:
            if not any(_text(row.get("code")) == code for row in mark_rows):
                mark_rows.append(
                    {
                        "as_of": day,
                        "code": code,
                        "status": "unavailable",
                        "reason": "MARKET_MARK_ADAPTER_NOT_CONFIGURED",
                        "source": "book_t_v2_eod_adapter",
                    }
                )
    event = build_daily_mark_event(
        lifecycle,
        observed_at=f"{day}T07:10:00Z",
        marks=mark_rows,
    )
    event_path = root / BOOK_T_V2_RESEARCH_DIR / "evidence_events.jsonl"
    all_events = append_events(event_path, [event])
    decision_events = [
        row for row in all_events if _text(row.get("decision_id")) == _text(lifecycle["decision_id"])
    ]
    summary = lifecycle_summary([lifecycle], events=decision_events)
    summary["decision_id"] = lifecycle["decision_id"]
    summary["event_path"] = str(event_path)
    _atomic_json(root / BOOK_T_V2_RESEARCH_DIR / f"evidence_summary_{day}.json", summary)
    return summary


__all__ = [
    "BOOK_T_V2_PRODUCER_VERSION",
    "BookTV2ProducerError",
    "build_book_t_v2_shadow_day",
    "prepare_book_t_v2_shadow_day",
    "record_book_t_v2_daily_mark",
]
