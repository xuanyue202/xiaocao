"""Select a paper-only Book T v2 theme plan.

The selector is the deterministic seam between the evidence-bound trend
snapshot, the resolved instrument universe, and the existing Book T paper
writer.  It chooses theme risk first and expressions second.  It returns a
hash-bound plan only; it never calculates a fill, mutates a ledger, or falls
back to the legacy static ``aligned / neutral / external`` picker.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from xiaocao.kol.publication import canonical_sha256
from xiaocao.live.instrument_contract import (
    InstrumentContractError,
    contract_from_record,
    market_contract_verified,
)

from .params import TREND_BUDGET_RATIO, TREND_TOP_M
from .theme_instrument_resolver import (
    ThemeInstrumentResolverError,
    ThemeInstrumentUniverse,
)
from .trend_snapshot import TrendJudgmentSnapshot, TrendSnapshotError


SELECTION_PLAN_SCHEMA_VERSION = 1
SELECTOR_VERSION = "book-t-v2-theme-selector-v1"
MAX_THEME_SLOTS = 3
VALID_THEME_ELIGIBILITIES = frozenset({"eligible", "wait", "conflicted", "invalidated"})
VALID_SETTLEMENT_CYCLES = frozenset({"T+0", "T+1"})

_QUALITY_SCORES = {
    "strong": 1.0,
    "supportive": 0.8,
    "current": 0.8,
    "neutral": 0.5,
    "mixed": 0.45,
    "weak": 0.25,
    "broken": 0.0,
}


class BookTSelectionError(ValueError):
    """The selection input or hash-bound plan violates its contract."""


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise BookTSelectionError(f"{field} is not canonical JSON") from exc


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _bounded(value: Any, *, default: float = 0.0) -> float:
    parsed = _number(value)
    if parsed is None:
        return max(0.0, min(1.0, default))
    return max(0.0, min(1.0, parsed))


def _as_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        for key in ("rows", "items", "records", "list", "data"):
            nested = value.get(key)
            if isinstance(nested, (list, tuple)):
                return [dict(row) for row in nested if isinstance(row, Mapping)]
        return [dict(value)]
    if isinstance(value, (list, tuple)):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _date_only(value: Any) -> str | None:
    text = _text(value)
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        text = text[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _metric(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        direct = _number(row.get(key))
        if direct is not None:
            return direct
    for container_key in ("trend", "liquidity", "quality", "expression_quality"):
        container = row.get(container_key)
        if not isinstance(container, Mapping):
            continue
        for key in keys:
            nested = _number(container.get(key))
            if nested is not None:
                return nested
    return None


def _status(value: Any) -> str:
    return _text(value).casefold()


def _component_verified(value: Any, *, price_field: str | None = None) -> bool:
    if isinstance(value, Mapping):
        status = _status(value.get("status"))
        verified = value.get("verified") is True
        if status not in {"verified", "available", "ok", "current"} and not verified:
            return False
        if price_field is not None:
            return _status(value.get("price_field") or value.get("trade_field")) == price_field
        return True
    return value is True or _status(value) in {"verified", "available", "ok", "current"}


def _portfolio_equity(portfolio: Mapping[str, Any]) -> float | None:
    for key in ("account_equity", "equity", "nav", "total_equity"):
        value = _number(portfolio.get(key))
        if value is not None and value > 0:
            return value
    for container_key in ("account", "paper_account", "totals"):
        container = portfolio.get(container_key)
        if not isinstance(container, Mapping):
            continue
        for key in ("equity", "nav", "total_equity", "account_equity"):
            value = _number(container.get(key))
            if value is not None and value > 0:
                return value
    return None


def _portfolio_positions(portfolio: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("positions", "open_positions", "holdings"):
        if key in portfolio:
            rows = _as_rows(portfolio.get(key))
            return [
                row
                for row in rows
                if _status(row.get("status") or "open") not in {"closed", "sold", "exited"}
                and _text(row.get("book")) == "T"
            ]
    return []


def _portfolio_has_invalid_book(portfolio: Mapping[str, Any]) -> bool:
    for key in ("positions", "open_positions", "holdings"):
        if key not in portfolio:
            continue
        for row in _as_rows(portfolio.get(key)):
            if _status(row.get("status") or "open") in {"closed", "sold", "exited"}:
                continue
            if _text(row.get("book")) not in {"A", "B", "T"}:
                return True
        return False
    return False


def _position_settlement_cycle(
    position: Mapping[str, Any],
    universe: Mapping[str, Any],
    *,
    theme_id: str,
) -> str:
    direct = _text(position.get("settlement_cycle"))
    if direct in VALID_SETTLEMENT_CYCLES:
        return direct
    code = _text(position.get("code"))
    for theme in _as_rows(universe.get("themes")):
        if _text(theme.get("theme_id")) != theme_id:
            continue
        for instrument in _as_rows(theme.get("instruments")):
            if _text(instrument.get("code")) == code:
                settlement = _text(instrument.get("settlement_cycle"))
                if settlement in VALID_SETTLEMENT_CYCLES:
                    return settlement
    return "T+1"


def _portfolio_history(portfolio: Mapping[str, Any], theme_id: str) -> list[dict[str, Any]]:
    raw: Any = None
    for key in ("evaluation_history", "challenger_history", "selection_history", "theme_evaluations"):
        if key in portfolio:
            raw = portfolio.get(key)
            break
    if isinstance(raw, Mapping):
        raw = raw.get(theme_id, [])
    rows = _as_rows(raw)
    return [row for row in rows if _text(row.get("theme_id")) in {"", theme_id}]


def _validated_snapshot(
    value: TrendJudgmentSnapshot | Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if value is None:
        return None, None, "snapshot_missing"
    try:
        if isinstance(value, TrendJudgmentSnapshot):
            validated = value
        elif isinstance(value, Mapping):
            validated = TrendJudgmentSnapshot.from_payload(value)
        else:
            return None, None, "snapshot_type_invalid"
    except TrendSnapshotError:
        return None, None, "snapshot_binding_invalid"
    payload = validated.to_dict()
    receipt = payload.get("binding_receipt")
    if not isinstance(receipt, Mapping) or _status(receipt.get("status")) != "validated":
        return None, None, "snapshot_binding_invalid"
    return payload, validated.snapshot_sha256, None


def _validated_universe(
    value: ThemeInstrumentUniverse | Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if value is None:
        return None, None, "universe_missing"
    try:
        if isinstance(value, ThemeInstrumentUniverse):
            validated = value
        elif isinstance(value, Mapping):
            validated = ThemeInstrumentUniverse.from_payload(value)
        else:
            return None, None, "universe_type_invalid"
    except ThemeInstrumentResolverError:
        return None, None, "universe_binding_invalid"
    payload = validated.to_dict()
    receipt = payload.get("binding_receipt")
    if not isinstance(receipt, Mapping) or _status(receipt.get("status")) != "validated":
        return None, None, "universe_binding_invalid"
    return payload, validated.universe_sha256, None


def _instrument_type(row: Mapping[str, Any]) -> str:
    return _status(row.get("instrument_type") or row.get("type"))


def _instrument_failure(
    row: Mapping[str, Any],
    *,
    snapshot_as_of: str | None = None,
) -> tuple[str, str] | None:
    if not _text(row.get("code")):
        return "evidence_binding", "instrument_code_missing"
    if not isinstance(row.get("mapping_evidence"), (list, tuple)) or not row.get("mapping_evidence"):
        return "evidence_binding", "mapping_evidence_missing"
    mapping_status = _status(row.get("mapping_status") or "resolved")
    if mapping_status not in {"resolved", "eligible", "valid"}:
        return "evidence_binding", "instrument_mapping_unresolved"
    instrument_status = _status(
        row.get("instrument_status") or row.get("tradability_status") or "eligible"
    )
    reasons = row.get("ineligible_reasons") or row.get("non_tradable_reasons") or []
    if instrument_status not in {"eligible", "tradable", "valid"} or reasons:
        return "instrument_contract", "instrument_ineligible"
    instrument_type = _instrument_type(row)
    if instrument_type not in {"etf", "equity", "stock"}:
        return "instrument_contract", "instrument_type_unknown"
    lot_size = _number(row.get("lot_size"))
    if lot_size is None or lot_size <= 0 or not lot_size.is_integer():
        return "instrument_contract", "lot_size_unknown"
    settlement = _text(row.get("settlement_cycle")).replace(" ", "")
    if settlement not in VALID_SETTLEMENT_CYCLES:
        return "instrument_contract", "settlement_cycle_unknown"
    market_contract = row.get("market_data_contract") or row.get("quote_contract")
    if not isinstance(market_contract, Mapping) or not _component_verified(market_contract.get("status")):
        return "instrument_contract", "market_data_contract_unverified"
    if instrument_type == "etf":
        market_source = _status(market_contract.get("source"))
        if market_source not in {
            "xiaocao_api",
            "xiaocao",
            "proprietary_api",
            "p-xcapi",
            "p-xcapi.kjap1.cn",
        }:
            return "instrument_contract", "market_data_source_not_proprietary"
        try:
            contract = contract_from_record(row, strict=True)
        except InstrumentContractError:
            return "instrument_contract", "etf_contract_incomplete"
        if contract is None or not market_contract_verified(contract):
            return "instrument_contract", "etf_market_contract_unverified"
        catalog_trade_date = _date_only(row.get("catalog_trade_date"))
        if not catalog_trade_date:
            return "instrument_contract", "etf_catalog_date_missing"
        if snapshot_as_of:
            snapshot_date = _date_only(snapshot_as_of)
            if snapshot_date:
                age_days = (date.fromisoformat(snapshot_date) - date.fromisoformat(catalog_trade_date)).days
                if age_days < 0 or age_days > 1:
                    return "instrument_contract", "etf_catalog_stale"
        if _status(row.get("market_status")) not in {"active", "tradable", "trading", "normal", "1", "true", "t"}:
            return "instrument_contract", "etf_market_status_not_verified"
        if _status(row.get("liquidity_status")) not in {"liquid", "ok", "sufficient", "verified"}:
            return "instrument_contract", "etf_liquidity_not_verified"
    else:
        market_status = _status(row.get("market_status") or row.get("trading_status"))
        if market_status and market_status not in {"active", "tradable", "trading", "normal", "1", "true", "t"}:
            return "instrument_contract", "equity_market_status_not_verified"
    return None


def _trend_quality(row: Mapping[str, Any]) -> tuple[float | None, bool]:
    trend = row.get("trend")
    if isinstance(trend, Mapping):
        numeric = _number(trend.get("score") or trend.get("quality_score"))
        if numeric is not None:
            return _bounded(numeric), True
        quality = _status(trend.get("quality") or trend.get("status"))
        if quality in _QUALITY_SCORES:
            return _QUALITY_SCORES[quality], True
    direct = _number(row.get("trend_score") or row.get("trend_quality_score"))
    if direct is not None:
        return _bounded(direct), True
    return None, False


def _liquidity_score(row: Mapping[str, Any]) -> tuple[float | None, bool]:
    direct = _metric(row, "liquidity_score", "turnover_score")
    if direct is not None:
        return _bounded(direct), True
    liquidity = row.get("liquidity")
    if isinstance(liquidity, Mapping):
        score = _number(liquidity.get("score"))
        if score is not None:
            return _bounded(score), True
        turnover = _number(
            liquidity.get("turnover_20d")
            or liquidity.get("avg_turnover_20d")
            or liquidity.get("amount_20d")
        )
        if turnover is not None and turnover >= 0:
            return _bounded(turnover / 100_000_000), True
        status = _status(liquidity.get("status"))
        if status in {"liquid", "ok", "sufficient", "verified"}:
            return 0.75, True
    return None, False


def _fee_rates(row: Mapping[str, Any]) -> tuple[float, float]:
    buy = _number(row.get("buy_fee_rate"))
    sell = _number(row.get("sell_fee_rate"))
    if buy is None:
        buy = _number(row.get("fee_rate"))
    if sell is None:
        sell = _number(row.get("fee_rate"))
    if buy is None:
        buy = 0.0001
    if sell is None:
        sell = 0.0001
    return max(0.0, buy), max(0.0, sell)


def _correlation_to_theme(row: Mapping[str, Any], *, instrument_type: str) -> float:
    value = _metric(row, "correlation_to_theme", "theme_correlation", "correlation")
    if value is not None:
        return _bounded(value)
    return 0.65 if instrument_type == "etf" else 0.95


def _risk_contribution(row: Mapping[str, Any]) -> float:
    value = _metric(
        row,
        "risk_contribution",
        "theme_risk_contribution",
        "risk_ratio",
        "risk_score",
    )
    if value is None:
        return 1.0
    return max(0.0, value)


def _expression_quality(row: Mapping[str, Any]) -> tuple[dict[str, Any] | None, tuple[str, str] | None]:
    trend_score, trend_ready = _trend_quality(row)
    liquidity_score, liquidity_ready = _liquidity_score(row)
    relative_strength = _metric(row, "relative_strength", "relative_strength_score", "rs_score")
    if relative_strength is None:
        return None, ("expression_quality", "relative_strength_missing")
    if not trend_ready:
        return None, ("expression_quality", "trend_quality_missing")
    if not liquidity_ready:
        return None, ("expression_quality", "liquidity_missing")
    risk_contribution = _risk_contribution(row)
    if risk_contribution > 1.0:
        return None, ("expression_quality", "theme_slot_risk_exceeded")
    relative_strength = _bounded(relative_strength)
    instrument_type = _instrument_type(row)
    role = _status(row.get("expression_role") or row.get("role"))
    if instrument_type == "etf" or role in {"broad_etf", "etf", "broad"}:
        breadth = _metric(row, "breadth_score", "breadth", "coverage_score")
        breadth_score = _bounded(breadth, default=1.0 if role == "broad_etf" else 0.75)
        leader_clarity = _bounded(_metric(row, "leader_clarity"), default=0.25)
        score = (
            0.35 * breadth_score
            + 0.20 * trend_score
            + 0.15 * relative_strength
            + 0.15 * liquidity_score
        )
        kind = "etf"
    else:
        breadth_score = _bounded(_metric(row, "breadth_score", "coverage_score"), default=0.35)
        leader_default = 0.85 if trend_score >= 0.8 else 0.65
        leader_clarity = _bounded(_metric(row, "leader_clarity"), default=leader_default)
        score = (
            0.30 * leader_clarity
            + 0.20 * trend_score
            + 0.20 * relative_strength
            + 0.15 * liquidity_score
        )
        kind = "equity"
    buy_fee, sell_fee = _fee_rates(row)
    roundtrip_bps = (buy_fee + sell_fee) * 10_000
    cost_score = max(0.0, 1.0 - min(1.0, roundtrip_bps / 30.0))
    score += 0.15 * cost_score
    return {
        "score": round(score, 8),
        "instrument_type": kind,
        "breadth_score": round(breadth_score, 8),
        "leader_clarity": round(leader_clarity, 8),
        "trend_score": round(trend_score, 8),
        "relative_strength": round(relative_strength, 8),
        "liquidity_score": round(liquidity_score, 8),
        "cost_score": round(cost_score, 8),
        "correlation_to_theme": round(
            _correlation_to_theme(row, instrument_type=kind),
            8,
        ),
        "risk_contribution": round(risk_contribution, 8),
        "buy_fee_rate": buy_fee,
        "sell_fee_rate": sell_fee,
        "roundtrip_fee_bps": round(roundtrip_bps, 8),
    }, None


def _market_score(theme: Mapping[str, Any]) -> float:
    market = theme.get("market_validation")
    if not isinstance(market, Mapping):
        return 0.5
    numeric = _number(
        market.get("trend_strength")
        or market.get("score")
        or market.get("breadth_score")
        or market.get("continuation_score")
    )
    if numeric is not None:
        return _bounded(numeric)
    return {
        "support": 0.85,
        "supportive": 0.85,
        "current": 0.75,
        "neutral": 0.5,
        "risk": 0.2,
        "invalidated": 0.0,
    }.get(_status(market.get("status")), 0.5)


@dataclass(frozen=True)
class _ThemeOption:
    theme_id: str
    display_name: str
    eligibility: str
    expression: dict[str, Any]
    score: float
    candidate_rows: tuple[dict[str, Any], ...]
    rejected_rows: tuple[dict[str, Any], ...]


def _expression_instrument(
    row: Mapping[str, Any],
    quality: Mapping[str, Any],
    *,
    weight: float,
) -> dict[str, Any]:
    return {
        "code": _text(row.get("code")),
        "name": _text(row.get("name")),
        "instrument_type": quality["instrument_type"],
        "weight": weight,
        "quality": dict(quality),
    }


def _choose_expression(
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], set[str]]:
    by_type: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {"etf": [], "equity": []}
    for row, quality in candidates:
        by_type.setdefault(quality["instrument_type"], []).append((row, quality))
    for rows in by_type.values():
        rows.sort(
            key=lambda item: (
                -item[1]["score"],
                -item[1]["relative_strength"],
                _text(item[0].get("code")),
            )
        )
    best_etf = by_type["etf"][0] if by_type["etf"] else None
    best_equity = by_type["equity"][0] if by_type["equity"] else None
    selected_codes: set[str] = set()
    if best_etf and best_equity:
        etf_row, etf_quality = best_etf
        stock_row, stock_quality = best_equity
        combo_allowed = (
            etf_quality["breadth_score"] >= 0.75
            and stock_quality["leader_clarity"] >= 0.75
            and stock_quality["relative_strength"] >= 0.70
            and etf_quality["score"] >= 0.55
            and stock_quality["score"] >= 0.55
            and (
                0.5 * etf_quality["risk_contribution"]
                + 0.5 * stock_quality["risk_contribution"]
                <= 1.0
            )
        )
        if combo_allowed:
            selected_codes.update({_text(etf_row.get("code")), _text(stock_row.get("code"))})
            instruments = [
                _expression_instrument(etf_row, etf_quality, weight=0.5),
                _expression_instrument(stock_row, stock_quality, weight=0.5),
            ]
            expression_type = "etf_plus_stock"
            selection_rule = "breadth_and_clear_leader"
        elif stock_quality["leader_clarity"] >= 0.75 and stock_quality["score"] >= etf_quality["score"] - 0.05:
            selected_codes.add(_text(stock_row.get("code")))
            instruments = [_expression_instrument(stock_row, stock_quality, weight=1.0)]
            expression_type = "stock"
            selection_rule = "clear_leader"
        else:
            selected_codes.add(_text(etf_row.get("code")))
            instruments = [_expression_instrument(etf_row, etf_quality, weight=1.0)]
            expression_type = "etf"
            selection_rule = "breadth_over_unclear_leader"
    elif best_equity:
        row, quality = best_equity
        selected_codes.add(_text(row.get("code")))
        instruments = [_expression_instrument(row, quality, weight=1.0)]
        expression_type = "stock"
        selection_rule = "best_core_trend_stock"
    else:
        if best_etf is None:
            raise BookTSelectionError("theme has no eligible instrument expression")
        row, quality = best_etf
        selected_codes.add(_text(row.get("code")))
        instruments = [_expression_instrument(row, quality, weight=1.0)]
        expression_type = "etf"
        selection_rule = "best_broad_etf"
    quality_score = round(
        sum(item["weight"] * item["quality"]["score"] for item in instruments),
        8,
    )
    return {
        "expression_type": expression_type,
        "selection_rule": selection_rule,
        "quality_score": quality_score,
        "correlation_policy": "merge_all_instruments_into_one_theme_risk_slot",
        "correlation_adjusted_risk": round(
            sum(
                item["weight"] * item["quality"].get("correlation_to_theme", 1.0)
                for item in instruments
            ),
            8,
        ),
        "combined_risk_ratio": round(
            sum(
                item["weight"] * item["quality"].get("risk_contribution", 1.0)
                for item in instruments
            ),
            8,
        ),
        "instruments": instruments,
    }, selected_codes


def _theme_option(
    snapshot_theme: Mapping[str, Any],
    universe_theme: Mapping[str, Any] | None,
    *,
    snapshot_as_of: str | None = None,
) -> tuple[_ThemeOption | None, list[dict[str, Any]]]:
    theme_id = _text(snapshot_theme.get("theme_id"))
    display_name = _text(snapshot_theme.get("display_name")) or theme_id
    eligibility = _status(snapshot_theme.get("eligibility") or "wait")
    if eligibility not in VALID_THEME_ELIGIBILITIES:
        eligibility = "wait"
    rejected: list[dict[str, Any]] = []
    if universe_theme is None or _status(universe_theme.get("resolution_status")) != "resolved":
        rejected.append(
            {
                "theme_id": theme_id,
                "display_name": display_name,
                "code": None,
                "first_failure_layer": "evidence_binding",
                "reason": "theme_mapping_unresolved",
            }
        )
        return None, rejected
    instruments = _as_rows(universe_theme.get("instruments"))
    if eligibility != "eligible":
        reason = f"theme_{eligibility}"
        if instruments:
            rejected.extend(
                {
                    "theme_id": theme_id,
                    "display_name": display_name,
                    "code": _text(row.get("code")) or None,
                    "first_failure_layer": "theme_eligibility",
                    "reason": reason,
                }
                for row in instruments
            )
        else:
            rejected.append(
                {
                    "theme_id": theme_id,
                    "display_name": display_name,
                    "code": None,
                    "first_failure_layer": "theme_eligibility",
                    "reason": reason,
                }
            )
        return None, rejected
    valid: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in instruments:
        failure = _instrument_failure(row, snapshot_as_of=snapshot_as_of)
        if failure:
            rejected.append(
                {
                    "theme_id": theme_id,
                    "display_name": display_name,
                    "code": _text(row.get("code")) or None,
                    "first_failure_layer": failure[0],
                    "reason": failure[1],
                }
            )
            continue
        quality, quality_failure = _expression_quality(row)
        if quality_failure or quality is None:
            layer, reason = quality_failure or ("expression_quality", "expression_quality_missing")
            rejected.append(
                {
                    "theme_id": theme_id,
                    "display_name": display_name,
                    "code": _text(row.get("code")) or None,
                    "first_failure_layer": layer,
                    "reason": reason,
                }
            )
            continue
        valid.append((row, quality))
    if not valid:
        if not rejected:
            rejected.append(
                {
                    "theme_id": theme_id,
                    "display_name": display_name,
                    "code": None,
                    "first_failure_layer": "evidence_binding",
                    "reason": "theme_has_no_instruments",
                }
            )
        return None, rejected
    expression, selected_codes = _choose_expression(valid)
    for row, _quality in valid:
        code = _text(row.get("code"))
        if code not in selected_codes:
            rejected.append(
                {
                    "theme_id": theme_id,
                    "display_name": display_name,
                    "code": code or None,
                    "first_failure_layer": "expression_quality",
                    "reason": "expression_not_selected",
                }
            )
    return (
        _ThemeOption(
            theme_id=theme_id,
            display_name=display_name,
            eligibility=eligibility,
            expression=expression,
            score=round(0.75 * expression["quality_score"] + 0.25 * _market_score(snapshot_theme), 8),
            candidate_rows=tuple(valid),
            rejected_rows=tuple(rejected),
        ),
        rejected,
    )


def _history_result(
    portfolio: Mapping[str, Any],
    challenger: _ThemeOption,
    incumbent: _ThemeOption,
    *,
    as_of: str,
) -> dict[str, Any]:
    current_advantage = round(challenger.score - incumbent.score, 8)
    challenger_history = _portfolio_history(portfolio, challenger.theme_id)
    prior = [
        row
        for row in challenger_history
        if row.get("valid") is True
        and _text(row.get("incumbent_theme_id")) == incumbent.theme_id
        and _number(row.get("score")) is not None
        and _number(row.get("incumbent_score")) is not None
        and row.get("consecutive", row.get("consecutive_valid", True)) is not False
        and (_date_only(row.get("as_of")) or "") < (_date_only(as_of) or "")
    ]
    prior.sort(key=lambda row: (_date_only(row.get("as_of")) or "", canonical_sha256(row)))
    latest = prior[-1] if prior else None
    incumbent_score = _number(latest.get("incumbent_score")) if latest else None
    prior_score = _number(latest.get("score")) if latest else None
    prior_advantage = (
        round(prior_score - incumbent_score, 8)
        if prior_score is not None and incumbent_score is not None
        else None
    )
    challenger_fees = _expression_roundtrip_fee_bps(challenger)
    incumbent_fees = _expression_roundtrip_fee_bps(incumbent)
    roundtrip_fee_bps = round((incumbent_fees[1] + challenger_fees[0]), 8)
    required_margin = round(roundtrip_fee_bps / 10_000, 8)
    risk_delta = max(
        0.0,
        (_number(latest.get("risk_delta")) or 0.0) if latest else 0.0,
    )
    current_margin = round(current_advantage - required_margin - risk_delta, 8)
    prior_margin = (
        round(prior_advantage - required_margin - risk_delta, 8)
        if prior_advantage is not None
        else None
    )
    qualifies = bool(latest and prior_margin is not None and prior_margin > 0 and current_margin > 0)
    if not latest:
        reason = "requires_two_valid_evaluations"
    elif not qualifies:
        reason = "advantage_does_not_cover_cost_or_risk"
    else:
        reason = "two_valid_evaluations_and_cost_covered"
    return {
        "qualifies": qualifies,
        "valid_evaluations": 2 if latest and prior_margin is not None and current_margin > 0 else 1 if latest else 0,
        "prior_bound_to_incumbent": bool(latest),
        "prior_as_of": _date_only(latest.get("as_of")) if latest else None,
        "current_advantage": current_advantage,
        "prior_advantage": prior_advantage,
        "required_margin": required_margin,
        "risk_delta": risk_delta,
        "current_margin": current_margin,
        "prior_margin": prior_margin,
        "roundtrip_fee_bps": roundtrip_fee_bps,
        "reason": reason,
    }


def _expression_roundtrip_fee_bps(option: _ThemeOption) -> tuple[float, float]:
    buy = 0.0
    sell = 0.0
    for instrument in option.expression.get("instruments", []):
        quality = instrument.get("quality") or {}
        weight = _number(instrument.get("weight")) or 0.0
        buy += weight * (_number(quality.get("buy_fee_rate")) or 0.0001) * 10_000
        sell += weight * (_number(quality.get("sell_fee_rate")) or 0.0001) * 10_000
    return buy, sell


def _expression_fee_ratio(option: _ThemeOption, *, side: str) -> float:
    total = 0.0
    for instrument in option.expression.get("instruments", []):
        quality = instrument.get("quality") or {}
        weight = _number(instrument.get("weight")) or 0.0
        fee_key = "buy_fee_rate" if side == "buy" else "sell_fee_rate"
        total += weight * (_number(quality.get(fee_key)) or 0.0001)
    return total


def _option_candidate_codes(option: _ThemeOption) -> list[str]:
    return sorted(
        _text(row.get("code"))
        for row, _quality in option.candidate_rows
        if _text(row.get("code"))
    )


def _incumbent_priority(
    theme_id: str,
    positions: Mapping[str, list[dict[str, Any]]],
    options: Mapping[str, _ThemeOption],
) -> tuple[float, str]:
    scores = [
        _number(row.get("selection_score") or row.get("theme_score"))
        for row in positions.get(theme_id, [])
    ]
    score = max((value for value in scores if value is not None), default=options[theme_id].score)
    return -score, theme_id


def _render_selected(
    option: _ThemeOption,
    *,
    target_ratio: float,
    account_equity: float | None,
    decision: str,
    slot_index: int,
) -> dict[str, Any]:
    target_notional = round(account_equity * target_ratio, 2) if account_equity is not None else None
    expression = copy.deepcopy(option.expression)
    for instrument in expression["instruments"]:
        instrument["target_ratio"] = round(target_ratio * float(instrument["weight"]), 8)
        instrument["target_notional"] = (
            round(target_notional * float(instrument["weight"]), 2)
            if target_notional is not None
            else None
        )
    return {
        "theme_id": option.theme_id,
        "display_name": option.display_name,
        "decision": decision,
        "slot_index": slot_index,
        "eligibility": option.eligibility,
        "selection_score": option.score,
        "target_ratio": round(target_ratio, 8),
        "target_notional": target_notional,
        "concentration_ratio": round(target_ratio, 8),
        "risk": {
            "risk_unit": "theme_slot",
            "theme_risk_ratio": round(target_ratio, 8),
            "instrument_count": len(expression["instruments"]),
            "correlation_policy": expression["correlation_policy"],
            "correlation_adjusted_risk": expression["correlation_adjusted_risk"],
            "combined_risk_ratio": expression["combined_risk_ratio"],
        },
        "candidate_codes": _option_candidate_codes(option),
        "expression": expression,
        "reason": (
            "existing_theme_retained"
            if decision == "hold"
            else "challenger_passed_two_evaluation_hysteresis"
            if decision == "paired_switch"
            else "eligible_theme_selected"
        ),
    }


def _base_plan(
    *,
    as_of: str | None,
    snapshot_sha: str | None,
    universe_sha: str | None,
    portfolio_sha: str | None,
    budget_ratio: float,
    account_equity: float | None,
    max_theme_slots: int,
    plan_status: str,
    daily_reevaluation_complete: bool,
    new_buys_allowed: bool,
    proactive_switches_allowed: bool,
    blocking_reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SELECTION_PLAN_SCHEMA_VERSION,
        "selector_version": SELECTOR_VERSION,
        "as_of": as_of,
        "plan_status": plan_status,
        "snapshot_sha256": snapshot_sha,
        "universe_sha256": universe_sha,
        "portfolio_sha256": portfolio_sha,
        "input_hashes": {
            "snapshot_sha256": snapshot_sha,
            "universe_sha256": universe_sha,
            "portfolio_sha256": portfolio_sha,
        },
        "binding_receipt": {
            "status": "validated" if plan_status != "blocked" else "blocked",
            "snapshot_sha256": snapshot_sha,
            "universe_sha256": universe_sha,
            "portfolio_sha256": portfolio_sha,
            "selector_version": SELECTOR_VERSION,
        },
        "budget": {
            "budget_ratio": round(budget_ratio, 8),
            "account_equity": account_equity,
            "budget_notional": round(account_equity * budget_ratio, 2)
            if account_equity is not None
            else None,
            "max_theme_slots": max_theme_slots,
            "occupied_theme_slots": 0,
            "selected_theme_slots": 0,
            "target_ratio_total": 0.0,
            "target_notional_total": 0.0 if account_equity is not None else None,
            "estimated_turnover_notional": 0.0,
            "estimated_turnover_ratio": 0.0,
            "estimated_roundtrip_fee": 0.0,
        },
        "concentration": {
            "risk_unit": "theme_slot",
            "instrument_risk_merged": True,
            "max_theme_ratio": 0.0,
            "theme_ratios": {},
        },
        "daily_reevaluation_complete": daily_reevaluation_complete,
        "new_buys_allowed": new_buys_allowed,
        "proactive_switches_allowed": proactive_switches_allowed,
        "existing_risk_management_allowed": True,
        "v1_static_fallback": False,
        "risk_management": {
            "mode": "preserve_existing",
            "existing_positions_preserved": True,
            "missing_data_action": "pause_new_buys_and_proactive_switches",
        },
        "selected_themes": [],
        "actions": [],
        "paired_switches": [],
        "unselected_candidates": [],
        "blocking_reasons": blocking_reasons,
    }


def _finalize_plan(body: Mapping[str, Any]) -> BookTSelectionPlan:
    value = _json_copy(dict(body), field="selection plan")
    receipt = dict(value.get("binding_receipt") or {})
    receipt.pop("selection_plan_sha256", None)
    value["binding_receipt"] = receipt
    value.pop("selection_plan_sha256", None)
    plan_sha = canonical_sha256(value)
    value["selection_plan_sha256"] = plan_sha
    value["binding_receipt"] = {**receipt, "selection_plan_sha256": plan_sha}
    return BookTSelectionPlan.from_payload(value)


@dataclass(frozen=True)
class BookTSelectionPlan(Mapping[str, Any]):
    """Immutable, hash-bound output of ``select_book_t``."""

    _canonical_payload: str
    selection_plan_sha256: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "BookTSelectionPlan":
        if not isinstance(payload, Mapping):
            raise BookTSelectionError("selection plan payload must be an object")
        value = _json_copy(dict(payload), field="selection plan payload")
        expected = _text(value.get("selection_plan_sha256"))
        if not expected:
            raise BookTSelectionError("selection_plan_sha256 is required")
        body = copy.deepcopy(value)
        body.pop("selection_plan_sha256", None)
        receipt = body.get("binding_receipt")
        if isinstance(receipt, Mapping):
            receipt = dict(receipt)
            if receipt.get("selection_plan_sha256") != expected:
                raise BookTSelectionError("binding receipt selection plan hash does not match")
            receipt.pop("selection_plan_sha256", None)
            body["binding_receipt"] = receipt
        if canonical_sha256(body) != expected:
            raise BookTSelectionError("selection plan hash does not match payload")
        return cls(
            _canonical_payload=json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            selection_plan_sha256=expected,
        )

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self._canonical_payload)
        if not isinstance(value, dict):
            raise BookTSelectionError("selection plan payload is not an object")
        return value

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def __hash__(self) -> int:
        return hash(self.selection_plan_sha256)


def _blocked_plan(
    *,
    as_of: str | None,
    snapshot_sha: str | None,
    universe_sha: str | None,
    portfolio_sha: str | None,
    budget_ratio: float,
    max_theme_slots: int,
    account_equity: float | None,
    blocking_reasons: list[dict[str, Any]],
) -> BookTSelectionPlan:
    return _finalize_plan(
        _base_plan(
            as_of=as_of,
            snapshot_sha=snapshot_sha,
            universe_sha=universe_sha,
            portfolio_sha=portfolio_sha,
            budget_ratio=budget_ratio,
            account_equity=account_equity,
            max_theme_slots=max_theme_slots,
            plan_status="blocked",
            daily_reevaluation_complete=False,
            new_buys_allowed=False,
            proactive_switches_allowed=False,
            blocking_reasons=blocking_reasons,
        )
    )


def _collect_theme_options(
    snapshot: Mapping[str, Any],
    universe: Mapping[str, Any],
    *,
    as_of: str,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, _ThemeOption],
    list[dict[str, Any]],
]:
    snapshot_themes = {
        _text(row.get("theme_id")): row
        for row in _as_rows(snapshot.get("themes"))
        if _text(row.get("theme_id"))
    }
    universe_themes = {
        _text(row.get("theme_id")): row
        for row in _as_rows(universe.get("themes"))
        if _text(row.get("theme_id"))
    }
    options: dict[str, _ThemeOption] = {}
    rejections: list[dict[str, Any]] = []
    for theme_id in sorted(snapshot_themes):
        option, rejected = _theme_option(
            snapshot_themes[theme_id],
            universe_themes.get(theme_id),
            snapshot_as_of=as_of,
        )
        rejections.extend(rejected)
        if option is not None:
            options[theme_id] = option
    return snapshot_themes, options, rejections


def _group_incumbents(
    positions: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    incumbent_by_theme: dict[str, list[dict[str, Any]]] = {}
    unknown_positions: list[dict[str, Any]] = []
    for position in positions:
        theme_id = _text(position.get("theme_id") or position.get("theme"))
        if not theme_id:
            unknown_positions.append(position)
            continue
        incumbent_by_theme.setdefault(theme_id, []).append(position)
    return incumbent_by_theme, unknown_positions


def _select_theme_set(
    portfolio: Mapping[str, Any],
    options: Mapping[str, _ThemeOption],
    incumbent_by_theme: Mapping[str, list[dict[str, Any]]],
    unknown_positions: list[dict[str, Any]],
    *,
    as_of: str,
    account_equity: float | None,
    portfolio_book_blocked: bool,
    max_theme_slots: int,
) -> dict[str, Any]:
    incumbent_ids = set(incumbent_by_theme)
    valid_incumbent_ids = {theme_id for theme_id in incumbent_ids if theme_id in options}
    ranked_valid_incumbents = sorted(
        valid_incumbent_ids,
        key=lambda theme_id: _incumbent_priority(theme_id, incumbent_by_theme, options),
    )
    retained_incumbent_ids = set(ranked_valid_incumbents[:max_theme_slots])
    overflow_incumbent_ids = valid_incumbent_ids - retained_incumbent_ids
    final_selected: dict[str, tuple[_ThemeOption, str]] = {
        theme_id: (options[theme_id], "hold")
        for theme_id in sorted(retained_incumbent_ids)
    }
    occupied_slots = len(incumbent_ids) + len(unknown_positions)
    available_slots = max(0, max_theme_slots - occupied_slots)
    proactive_allowed = account_equity is not None and not portfolio_book_blocked
    new_allowed = account_equity is not None and not portfolio_book_blocked
    unselected_ids = sorted(set(options) - incumbent_ids)
    paired_switches: list[dict[str, Any]] = []
    replaced_from: dict[str, str] = {}
    challenger_results: dict[str, dict[str, Any]] = {}
    if occupied_slots >= max_theme_slots and proactive_allowed:
        switch_candidates: list[tuple[float, str, str, dict[str, Any]]] = []
        for challenger_id in unselected_ids:
            challenger = options[challenger_id]
            for incumbent_id in sorted(final_selected):
                result = _history_result(
                    portfolio,
                    challenger,
                    final_selected[incumbent_id][0],
                    as_of=as_of,
                )
                current = challenger_results.get(challenger_id)
                if current is None or result["current_margin"] > current["current_margin"]:
                    challenger_results[challenger_id] = {
                        **result,
                        "incumbent_theme_id": incumbent_id,
                    }
                switch_candidates.append((-challenger.score, challenger_id, incumbent_id, result))
        switch_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        used_incumbents: set[str] = set()
        for _score, challenger_id, incumbent_id, result in switch_candidates:
            if not result["qualifies"] or incumbent_id in used_incumbents or challenger_id in final_selected:
                continue
            final_selected[challenger_id] = (options[challenger_id], "paired_switch")
            final_selected.pop(incumbent_id, None)
            used_incumbents.add(incumbent_id)
            replaced_from[incumbent_id] = challenger_id
            paired_switches.append(
                {
                    "from_theme_id": incumbent_id,
                    "to_theme_id": challenger_id,
                    "hysteresis": result,
                    "reason": "challenger_two_valid_evaluations_and_cost_covered",
                }
            )
    remaining = sorted(
        (options[theme_id] for theme_id in unselected_ids if theme_id not in final_selected),
        key=lambda option: (-option.score, option.theme_id),
    )
    if new_allowed:
        for option in remaining[:available_slots]:
            final_selected[option.theme_id] = (option, "new")
    return {
        "incumbent_ids": incumbent_ids,
        "overflow_incumbent_ids": overflow_incumbent_ids,
        "final_selected": final_selected,
        "occupied_slots": occupied_slots,
        "available_slots": available_slots,
        "new_allowed": new_allowed,
        "proactive_allowed": proactive_allowed,
        "paired_switches": paired_switches,
        "replaced_from": replaced_from,
        "challenger_results": challenger_results,
    }


def _render_selected_themes(
    selection: Mapping[str, Any],
    *,
    account_equity: float | None,
    budget_ratio: float,
) -> tuple[list[dict[str, Any]], set[str], float]:
    final_selected = selection["final_selected"]
    ranked = sorted(
        final_selected.values(),
        key=lambda item: (-item[0].score, item[0].theme_id),
    )
    target_ratio = budget_ratio / len(ranked) if ranked else 0.0
    selected = [
        _render_selected(
            option,
            target_ratio=target_ratio,
            account_equity=account_equity,
            decision=decision,
            slot_index=index,
        )
        for index, (option, decision) in enumerate(ranked, 1)
    ]
    return selected, set(final_selected), target_ratio


def _validated_portfolio(
    value: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    if not isinstance(value, Mapping):
        return None, None, {
            "first_failure_layer": "portfolio_constraints",
            "reason": "portfolio_missing",
        }
    try:
        portfolio = _json_copy(dict(value), field="portfolio")
    except BookTSelectionError:
        return None, None, {
            "first_failure_layer": "evidence_binding",
            "reason": "portfolio_binding_invalid",
        }
    return portfolio, canonical_sha256(portfolio), None


def _build_actions(
    *,
    as_of: str,
    snapshot_themes: Mapping[str, Mapping[str, Any]],
    universe: Mapping[str, Any],
    incumbent_ids: set[str],
    incumbent_by_theme: Mapping[str, list[dict[str, Any]]],
    options: Mapping[str, _ThemeOption],
    selected_ids: set[str],
    overflow_incumbent_ids: set[str],
    replaced_from: Mapping[str, str],
    paired_switches: list[dict[str, Any]],
    selected_themes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for theme_id in sorted(incumbent_ids):
        if theme_id in replaced_from:
            continue
        positions = incumbent_by_theme[theme_id]
        option = options.get(theme_id)
        codes = sorted({_text(row.get("code")) for row in positions if _text(row.get("code"))})
        if option is not None and theme_id in selected_ids:
            actions.append(
                {
                    "action": "hold",
                    "theme_id": theme_id,
                    "codes": codes,
                    "reason": "existing_theme_retained",
                }
            )
            continue
        if theme_id in overflow_incumbent_ids:
            actions.append(
                {
                    "action": "wait",
                    "theme_id": theme_id,
                    "codes": codes,
                    "reason": "theme_slot_overflow",
                }
            )
            continue
        if _status(snapshot_themes.get(theme_id, {}).get("eligibility")) == "invalidated":
            for position in positions:
                entry_date = _date_only(position.get("entry_date"))
                settlement_cycle = _position_settlement_cycle(
                    position,
                    universe,
                    theme_id=theme_id,
                )
                t1_blocked = bool(
                    entry_date
                    and entry_date == _date_only(as_of)
                    and settlement_cycle != "T+0"
                )
                actions.append(
                    {
                        "action": "wait" if t1_blocked else "risk_exit",
                        "theme_id": theme_id,
                        "code": _text(position.get("code")) or None,
                        "reason": "t1_blocked" if t1_blocked else "theme_invalidated",
                        "execution_status": "blocked" if t1_blocked else "intent_only",
                        "settlement_cycle": settlement_cycle,
                    }
                )
            continue
        actions.append(
            {
                "action": "wait",
                "theme_id": theme_id,
                "codes": codes,
                "reason": "existing_theme_preserved_without_replacement",
            }
        )
    actions.extend(
        {
            "action": "paired_switch",
            "from_theme_id": switch["from_theme_id"],
            "to_theme_id": switch["to_theme_id"],
            "reason": switch["reason"],
            "hysteresis": switch["hysteresis"],
        }
        for switch in paired_switches
    )
    actions.extend(
        {
            "action": "new",
            "theme_id": selected["theme_id"],
            "reason": "eligible_theme_selected",
        }
        for selected in selected_themes
        if selected["decision"] == "new"
    )
    return actions


def _append_option_rejections(
    rejections: list[dict[str, Any]],
    *,
    options: Mapping[str, _ThemeOption],
    selected_ids: set[str],
    incumbent_ids: set[str],
    overflow_incumbent_ids: set[str],
    new_allowed: bool,
    slots_full: bool,
    challenger_results: Mapping[str, dict[str, Any]],
) -> None:
    for option in options.values():
        if option.theme_id in selected_ids:
            continue
        if any(row.get("theme_id") == option.theme_id for row in rejections):
            continue
        if option.theme_id in overflow_incumbent_ids:
            rejection = {
                "theme_id": option.theme_id,
                "display_name": option.display_name,
                "code": None,
                "first_failure_layer": "portfolio_constraints",
                "reason": "theme_slot_overflow",
            }
        elif not new_allowed:
            rejection = {
                "theme_id": option.theme_id,
                "display_name": option.display_name,
                "code": None,
                "first_failure_layer": "portfolio_constraints",
                "reason": "account_equity_missing",
            }
        elif slots_full:
            rejection = {
                "theme_id": option.theme_id,
                "display_name": option.display_name,
                "code": None,
                "first_failure_layer": (
                    "challenger_hysteresis"
                    if option.theme_id not in incumbent_ids
                    else "portfolio_constraints"
                ),
                "reason": (
                    "requires_two_valid_evaluations"
                    if option.theme_id not in incumbent_ids
                    else "theme_slot_unavailable"
                ),
            }
            if option.theme_id in challenger_results:
                rejection["hysteresis"] = challenger_results[option.theme_id]
        else:
            rejection = {
                "theme_id": option.theme_id,
                "display_name": option.display_name,
                "code": None,
                "first_failure_layer": "portfolio_constraints",
                "reason": "theme_slot_unavailable",
            }
        rejections.append(rejection)
    for option in options.values():
        rejections.extend(option.rejected_rows)


def _selection_metrics(
    selected_themes: list[dict[str, Any]],
    final_selected: Mapping[str, tuple[_ThemeOption, str]],
    paired_switches: list[dict[str, Any]],
    incumbent_by_theme: Mapping[str, list[dict[str, Any]]],
    options: Mapping[str, _ThemeOption],
    *,
    account_equity: float | None,
) -> dict[str, float]:
    selected_notional = round(sum(row["target_notional"] or 0.0 for row in selected_themes), 2)
    turnover_notional = sum(
        row["target_notional"] or 0.0
        for row in selected_themes
        if row["decision"] == "new"
    )
    for switch in paired_switches:
        replaced_positions = incumbent_by_theme.get(switch["from_theme_id"], [])
        turnover_notional += sum(
            _number(row.get("market_value") or row.get("notional") or row.get("entry_cash_out")) or 0.0
            for row in replaced_positions
        )
        new_selected = next(
            (row for row in selected_themes if row["theme_id"] == switch["to_theme_id"]),
            None,
        )
        turnover_notional += (new_selected or {}).get("target_notional") or 0.0
    estimated_fee = 0.0
    if account_equity is not None:
        for selected in selected_themes:
            if selected["decision"] not in {"new", "paired_switch"}:
                continue
            option = final_selected[selected["theme_id"]][0]
            estimated_fee += (selected["target_notional"] or 0.0) * _expression_fee_ratio(
                option,
                side="buy",
            )
        for switch in paired_switches:
            old_option = options.get(switch["from_theme_id"])
            old_notional = sum(
                _number(row.get("market_value") or row.get("notional") or row.get("entry_cash_out")) or 0.0
                for row in incumbent_by_theme.get(switch["from_theme_id"], [])
            )
            if old_option is not None:
                estimated_fee += old_notional * _expression_fee_ratio(old_option, side="sell")
    return {
        "selected_notional": selected_notional,
        "turnover_notional": round(turnover_notional, 2),
        "estimated_fee": round(estimated_fee, 2),
    }


def _ready_plan(
    *,
    as_of: str,
    snapshot_sha: str,
    universe_sha: str,
    portfolio_sha: str | None,
    budget_ratio: float,
    account_equity: float | None,
    max_theme_slots: int,
    new_allowed: bool,
    proactive_allowed: bool,
    blocking_reasons: list[dict[str, Any]],
    selected_themes: list[dict[str, Any]],
    selected_count: int,
    target_ratio: float,
    occupied_slots: int,
    actions: list[dict[str, Any]],
    paired_switches: list[dict[str, Any]],
    rejections: list[dict[str, Any]],
    metrics: Mapping[str, float],
) -> BookTSelectionPlan:
    body = _base_plan(
        as_of=as_of,
        snapshot_sha=snapshot_sha,
        universe_sha=universe_sha,
        portfolio_sha=portfolio_sha,
        budget_ratio=budget_ratio,
        account_equity=account_equity,
        max_theme_slots=max_theme_slots,
        plan_status="ready" if new_allowed else "degraded",
        daily_reevaluation_complete=True,
        new_buys_allowed=new_allowed,
        proactive_switches_allowed=proactive_allowed,
        blocking_reasons=blocking_reasons,
    )
    body["selected_themes"] = selected_themes
    body["actions"] = sorted(
        actions,
        key=lambda row: (
            _text(row.get("action")),
            _text(row.get("theme_id") or row.get("from_theme_id")),
            _text(row.get("to_theme_id")),
            _text(row.get("code")),
        ),
    )
    body["paired_switches"] = sorted(
        paired_switches,
        key=lambda row: (_text(row.get("from_theme_id")), _text(row.get("to_theme_id"))),
    )
    body["unselected_candidates"] = sorted(
        rejections,
        key=lambda row: (
            _text(row.get("theme_id")),
            _text(row.get("code")),
            _text(row.get("first_failure_layer")),
            _text(row.get("reason")),
        ),
    )
    body["budget"].update(
        {
            "occupied_theme_slots": occupied_slots,
            "selected_theme_slots": selected_count,
            "target_ratio_total": round(target_ratio * selected_count, 8),
            "target_notional_total": metrics["selected_notional"] if account_equity is not None else None,
            "estimated_turnover_notional": metrics["turnover_notional"],
            "estimated_turnover_ratio": round(metrics["turnover_notional"] / account_equity, 8)
            if account_equity
            else 0.0,
            "estimated_roundtrip_fee": metrics["estimated_fee"],
        }
    )
    body["concentration"] = {
        "risk_unit": "theme_slot",
        "instrument_risk_merged": True,
        "max_theme_ratio": round(
            max((row["target_ratio"] for row in selected_themes), default=0.0),
            8,
        ),
        "theme_ratios": {row["theme_id"]: row["target_ratio"] for row in selected_themes},
    }
    return _finalize_plan(body)


def select_book_t(
    portfolio: Mapping[str, Any] | None,
    snapshot: TrendJudgmentSnapshot | Mapping[str, Any] | None,
    universe: ThemeInstrumentUniverse | Mapping[str, Any] | None,
) -> BookTSelectionPlan:
    """Build a deterministic, paper-only Book T v2 selection plan.

    Theme eligibility and evidence binding are hard gates.  The selector
    reevaluates all incumbents before filling empty slots; when all slots are
    occupied, a challenger needs two consecutive valid evaluations and a
    positive margin after estimated replacement cost and risk difference.
    """

    budget_ratio = float(TREND_BUDGET_RATIO)
    max_theme_slots = max(1, min(MAX_THEME_SLOTS, int(TREND_TOP_M)))
    portfolio_value, portfolio_sha, portfolio_blocker = _validated_portfolio(portfolio)
    snapshot_value, snapshot_sha, snapshot_error = _validated_snapshot(snapshot)
    universe_value, universe_sha, universe_error = _validated_universe(universe)

    blocking_reasons: list[dict[str, Any]] = []
    if snapshot_error:
        blocking_reasons.append(
            {"first_failure_layer": "evidence_binding", "reason": snapshot_error}
        )
    if universe_error:
        blocking_reasons.append(
            {"first_failure_layer": "evidence_binding", "reason": universe_error}
        )
    if portfolio_blocker:
        blocking_reasons.append(portfolio_blocker)
    if snapshot_sha and universe_value:
        if _text(universe_value.get("snapshot_sha256")) != snapshot_sha:
            blocking_reasons.append(
                {"first_failure_layer": "evidence_binding", "reason": "snapshot_universe_hash_mismatch"}
            )

    evidence_blocked = any(
        row.get("first_failure_layer") == "evidence_binding"
        for row in blocking_reasons
    )
    if snapshot_value is None or universe_value is None or evidence_blocked:
        return _blocked_plan(
            as_of=_text(snapshot_value.get("as_of")) if snapshot_value else None,
            snapshot_sha=snapshot_sha,
            universe_sha=universe_sha,
            portfolio_sha=portfolio_sha,
            budget_ratio=budget_ratio,
            max_theme_slots=max_theme_slots,
            account_equity=_portfolio_equity(portfolio_value) if portfolio_value else None,
            blocking_reasons=blocking_reasons,
        )

    assert snapshot_sha is not None
    assert universe_sha is not None
    if portfolio_value is None:
        portfolio_value = {}
    account_equity = _portfolio_equity(portfolio_value)
    if account_equity is None:
        blocking_reasons.append(
            {"first_failure_layer": "portfolio_constraints", "reason": "account_equity_missing"}
        )
    portfolio_book_blocked = _portfolio_has_invalid_book(portfolio_value)
    if portfolio_book_blocked:
        blocking_reasons.append(
            {
                "first_failure_layer": "evidence_binding",
                "reason": "position_book_missing_or_invalid",
            }
        )

    as_of = _text(snapshot_value.get("as_of"))
    portfolio_positions = _portfolio_positions(portfolio_value)
    snapshot_themes, options, rejections = _collect_theme_options(
        snapshot_value,
        universe_value,
        as_of=as_of,
    )
    incumbent_by_theme, unknown_positions = _group_incumbents(portfolio_positions)
    selection = _select_theme_set(
        portfolio_value,
        options,
        incumbent_by_theme,
        unknown_positions,
        as_of=as_of,
        account_equity=account_equity,
        portfolio_book_blocked=portfolio_book_blocked,
        max_theme_slots=max_theme_slots,
    )
    selected_themes, selected_ids, target_ratio = _render_selected_themes(
        selection,
        account_equity=account_equity,
        budget_ratio=budget_ratio,
    )
    actions = _build_actions(
        as_of=as_of,
        snapshot_themes=snapshot_themes,
        universe=universe_value,
        incumbent_ids=selection["incumbent_ids"],
        incumbent_by_theme=incumbent_by_theme,
        options=options,
        selected_ids=selected_ids,
        overflow_incumbent_ids=selection["overflow_incumbent_ids"],
        replaced_from=selection["replaced_from"],
        paired_switches=selection["paired_switches"],
        selected_themes=selected_themes,
    )
    _append_option_rejections(
        rejections,
        options=options,
        selected_ids=selected_ids,
        incumbent_ids=selection["incumbent_ids"],
        overflow_incumbent_ids=selection["overflow_incumbent_ids"],
        new_allowed=selection["new_allowed"],
        slots_full=selection["occupied_slots"] >= max_theme_slots,
        challenger_results=selection["challenger_results"],
    )
    metrics = _selection_metrics(
        selected_themes,
        selection["final_selected"],
        selection["paired_switches"],
        incumbent_by_theme,
        options,
        account_equity=account_equity,
    )
    return _ready_plan(
        as_of=as_of,
        snapshot_sha=snapshot_sha,
        universe_sha=universe_sha,
        portfolio_sha=portfolio_sha,
        budget_ratio=budget_ratio,
        account_equity=account_equity,
        max_theme_slots=max_theme_slots,
        new_allowed=selection["new_allowed"],
        proactive_allowed=selection["proactive_allowed"],
        blocking_reasons=blocking_reasons,
        selected_themes=selected_themes,
        selected_count=len(selected_themes),
        target_ratio=target_ratio,
        occupied_slots=selection["occupied_slots"],
        actions=actions,
        paired_switches=selection["paired_switches"],
        rejections=rejections,
        metrics=metrics,
    )


__all__ = [
    "BookTSelectionError",
    "BookTSelectionPlan",
    "MAX_THEME_SLOTS",
    "SELECTION_PLAN_SCHEMA_VERSION",
    "SELECTOR_VERSION",
    "select_book_t",
]
