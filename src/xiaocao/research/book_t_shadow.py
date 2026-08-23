"""Book T v2 shadow runner and research-consumption gate.

The module deliberately stops at a research seam.  A caller supplies one
hash-bound, frozen market input containing the existing Book T control and the
v2 selection plan plus their deterministic simulated execution outcomes.  The
runner validates that both variants consumed the same assumptions, records
their executable paths, and returns a namespaced artifact.  It never opens the
paper ledger and never writes positions, accounts, or trades.

The second public seam consumes a collection of daily runs.  It reports the
engineering burn-in separately from the strategy sample floor and delegates
return/drawdown/walk-forward/non-bull judgement to ``trend_guards``.  A
``PASS`` therefore means "research evidence is consumable", not "promotion is
authorized".
"""
from __future__ import annotations

import copy
import json
import math
from collections import defaultdict
from datetime import date as calendar_date
from pathlib import Path
from typing import Any, Mapping, Sequence

from xiaocao.kol.publication import canonical_sha256
from xiaocao.live.instrument_contract import (
    InstrumentContractError,
    contract_from_record,
    validate_market_data,
)
from xiaocao.research import trend_guards
from xiaocao.research.book_t_v2_lifecycle import (
    BookTV2EvidenceError,
    engineering_burn_in_gate,
    lifecycle_summary,
    validate_lifecycle,
)


BOOK_T_SHADOW_SCHEMA_VERSION = 1
BOOK_T_SHADOW_NAMESPACE = "book_t_v2_shadow"
BOOK_T_SHADOW_INPUT_NAMESPACE = "book_t_v2_shadow_input"
BOOK_T_SHADOW_PROTOCOL_ID = "trend-book-t-v2-shadow-v1"
BOOK_T_SHADOW_MIN_BURN_IN_DAYS = 20
BOOK_T_SHADOW_MIN_STRATEGY_DAYS = 60
BOOK_T_SHADOW_MIN_VALID_DECISIONS = 50
BOOK_T_CONTROL_ARTIFACT_PATHS = {
    "positions": "output/live/positions.jsonl",
    "account": "output/live/paper_account_T.json",
    "trades": "output/live/paper_trades.jsonl",
}


class BookTShadowError(ValueError):
    """Raised when a shadow input cannot be safely replayed."""


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise BookTShadowError("Book T shadow input must be JSON-compatible") from exc


def _text(value: Any) -> str:
    return str(value or "").strip()


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BookTShadowError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise BookTShadowError(f"{field} must be finite")
    return number


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BookTShadowError(f"{field} must be an object")
    return dict(value)


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise BookTShadowError(f"{field} must be a list")
    return list(value)


def _date(as_of: Any) -> str:
    value = _text(as_of)
    if len(value) < 10 or value[4] != "-" or value[7] != "-":
        raise BookTShadowError(f"as_of must start with an ISO date: {as_of!r}")
    try:
        calendar_date.fromisoformat(value[:10])
    except ValueError as exc:
        raise BookTShadowError(f"as_of must contain a real ISO date: {as_of!r}") from exc
    return value[:10]


def _row_date(
    row: Mapping[str, Any],
    field: str,
    candidates: Sequence[str],
    *,
    required: bool = True,
) -> str | None:
    for name in candidates:
        value = row.get(name)
        if value not in (None, ""):
            return _date(value)
    if required:
        raise BookTShadowError(f"{field} must carry one of: {', '.join(candidates)}")
    return None


def _assert_same_day(value: str | None, expected: str, field: str) -> None:
    if value != expected:
        raise BookTShadowError(f"{field} date {value!r} does not match frozen day {expected}")


def _research_floor(value: Any, minimum: int, field: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise BookTShadowError(f"{field} must be an integer") from exc
    if isinstance(value, bool) or normalized < minimum:
        raise BookTShadowError(f"{field} cannot be below the protocol minimum {minimum}")
    return normalized


def _hash_body(value: Mapping[str, Any], hash_field: str) -> str:
    body = copy.deepcopy(dict(value))
    body.pop(hash_field, None)
    receipt = body.get("binding_receipt")
    if isinstance(receipt, Mapping):
        receipt = dict(receipt)
        receipt.pop(hash_field, None)
        body["binding_receipt"] = receipt
    return canonical_sha256(body)


def _require_hash(value: Mapping[str, Any], hash_field: str, field: str) -> str:
    actual = _text(value.get(hash_field))
    if not actual:
        raise BookTShadowError(f"{field}.{hash_field} is required")
    expected = _hash_body(value, hash_field)
    if actual != expected:
        raise BookTShadowError(f"{field}.{hash_field} does not match payload")
    return actual


def _require_digest(value: Any, field: str) -> str:
    digest = _text(value)
    if len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
        raise BookTShadowError(f"{field} must be a SHA-256 digest")
    return digest.lower()


def _bind_hash(value: Mapping[str, Any], hash_field: str, field: str) -> dict[str, Any]:
    body = _json_copy(value)
    if not isinstance(body, dict):
        raise BookTShadowError(f"{field} must be an object")
    actual = _text(body.get(hash_field))
    if actual and actual != _hash_body(body, hash_field):
        raise BookTShadowError(f"{field}.{hash_field} does not match payload")
    body[hash_field] = _hash_body(body, hash_field)
    return body


def _bind_market_input(value: Mapping[str, Any]) -> dict[str, Any]:
    return _bind_hash(value, "market_input_sha256", "market_input")


def _bind_selection(value: Mapping[str, Any], *, shadow: bool) -> dict[str, Any]:
    field = "selection_plan_sha256" if shadow else "selection_sha256"
    return _bind_hash(value, field, "shadow.selection_plan" if shadow else "control.selection")


def _selection_codes(selection: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    direct = selection.get("selected_codes")
    if isinstance(direct, list):
        codes.extend(_text(code) for code in direct if _text(code))
    actions = selection.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, Mapping) and _text(action.get("code")):
                codes.append(_text(action.get("code")))
    themes = selection.get("selected_themes")
    if isinstance(themes, list):
        for theme in themes:
            if not isinstance(theme, Mapping):
                continue
            instruments = theme.get("instruments")
            if isinstance(instruments, list):
                for instrument in instruments:
                    if isinstance(instrument, Mapping) and _text(instrument.get("code")):
                        codes.append(_text(instrument.get("code")))
    return sorted(set(codes))


def _bind_variant(
    value: Mapping[str, Any],
    *,
    shadow: bool,
    market_hash: str,
    lifecycle: bool = False,
) -> dict[str, Any]:
    variant = _json_copy(value)
    if not isinstance(variant, dict):
        raise BookTShadowError("variant must be an object")

    if shadow:
        plan = variant.get("selection_plan")
        if not isinstance(plan, Mapping):
            raise BookTShadowError("shadow.selection_plan is required")
        variant["selection_plan"] = _bind_selection(plan, shadow=True)
        variant.pop("selection", None)
    else:
        selection = variant.get("selection")
        if not isinstance(selection, Mapping):
            raise BookTShadowError("control.selection is required")
        variant["selection"] = _bind_selection(selection, shadow=False)
        receipt = variant.get("control_receipt")
        if not isinstance(receipt, Mapping):
            raise BookTShadowError("control.control_receipt is required")
        variant["control_receipt"] = _bind_hash(
            receipt,
            "receipt_sha256",
            "control.control_receipt",
        )
        variant.pop("selection_plan", None)

    selection_value = variant.get("selection_plan") if shadow else variant.get("selection")
    derived_codes = set(_selection_codes(_mapping(selection_value, "variant.selection")))
    if "expected_fill_codes" not in variant:
        expected_codes = sorted(derived_codes)
    else:
        expected_codes = _list(variant.get("expected_fill_codes"), "variant.expected_fill_codes")
        if {_text(code) for code in expected_codes if _text(code)} != derived_codes:
            raise BookTShadowError("variant.expected_fill_codes do not match the bound selection")
    variant["expected_fill_codes"] = [str(code) for code in expected_codes if _text(code)]
    if not variant["expected_fill_codes"] and not lifecycle:
        raise BookTShadowError("variant.expected_fill_codes must not be empty")

    roles = _list(variant.get("source_roles"), "variant.source_roles")
    variant["source_roles"] = sorted({_text(role) for role in roles if _text(role)})

    for field in ("fills", "holds"):
        raw_rows = variant.get(field, []) if lifecycle else variant.get(field)
        rows = _list(raw_rows, f"variant.{field}")
        bound_rows: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            item = _mapping(row, f"variant.{field}[{index}]")
            existing = _text(item.get("market_input_sha256"))
            if existing and existing != market_hash:
                raise BookTShadowError(
                    f"variant.{field}[{index}].market_input_sha256 does not match market input"
                )
            item["market_input_sha256"] = market_hash
            bound_rows.append(item)
        variant[field] = bound_rows
    return variant


def _validate_input_dates(body: Mapping[str, Any]) -> None:
    frozen_day = _date(body.get("as_of"))
    market = _mapping(body.get("market_input"), "market_input")
    market_day = _row_date(
        market,
        "market_input",
        ("market_date", "as_of", "trade_date", "date"),
    )
    _assert_same_day(market_day, frozen_day, "market_input")
    if market.get("is_trading_day") is not True:
        raise BookTShadowError("market_input.is_trading_day must be true")
    try:
        trading_day_index = int(market.get("trading_day_index"))
    except (TypeError, ValueError) as exc:
        raise BookTShadowError("market_input.trading_day_index is required") from exc
    if isinstance(market.get("trading_day_index"), bool) or trading_day_index < 0:
        raise BookTShadowError("market_input.trading_day_index must be non-negative")
    for name in ("control", "shadow"):
        variant = _mapping(body.get(name), name)
        selection_key = "selection_plan" if name == "shadow" else "selection"
        selection = _mapping(variant.get(selection_key), f"{name}.{selection_key}")
        selection_day = _row_date(
            selection,
            f"{name}.{selection_key}",
            ("as_of", "trade_date", "date"),
        )
        _assert_same_day(selection_day, frozen_day, f"{name}.{selection_key}")
        for index, row in enumerate(_list(variant.get("fills"), f"{name}.fills")):
            fill = _mapping(row, f"{name}.fills[{index}]")
            fill_day = _row_date(
                fill,
                f"{name}.fills[{index}]",
                ("as_of", "trade_date", "date"),
            )
            _assert_same_day(fill_day, frozen_day, f"{name}.fills[{index}]")
        for index, row in enumerate(_list(variant.get("holds"), f"{name}.holds")):
            hold = _mapping(row, f"{name}.holds[{index}]")
            hold_day = _row_date(
                hold,
                f"{name}.holds[{index}]",
                ("as_of", "valuation_date", "trade_date", "date"),
            )
            _assert_same_day(hold_day, frozen_day, f"{name}.holds[{index}]")


def _validate_control_receipt(
    receipt: Mapping[str, Any],
    *,
    as_of: str,
    require_daily_semantics: bool = False,
) -> dict[str, Any]:
    value = _mapping(receipt, "control.control_receipt")
    _require_hash(value, "receipt_sha256", "control.control_receipt")
    expected = {
        "consumer": "book_t_v1_control",
        "producer": "kronos_screen/scripts/paper_record.py",
        "mode": "trend-only",
        "book": "T",
    }
    for field, expected_value in expected.items():
        if _text(value.get(field)) != expected_value:
            raise BookTShadowError(
                f"control.control_receipt.{field} must be {expected_value!r}"
            )
    _assert_same_day(
        _row_date(value, "control.control_receipt", ("as_of", "trade_date", "date")),
        as_of,
        "control.control_receipt",
    )
    artifact_hashes = _mapping(value.get("artifact_hashes"), "control.control_receipt.artifact_hashes")
    artifact_paths = _mapping(value.get("artifact_paths"), "control.control_receipt.artifact_paths")
    for artifact, expected_path in BOOK_T_CONTROL_ARTIFACT_PATHS.items():
        if _text(artifact_paths.get(artifact)) != expected_path:
            raise BookTShadowError(
                f"control.control_receipt.artifact_paths.{artifact} must be {expected_path!r}"
            )
        _require_digest(
            artifact_hashes.get(artifact),
            f"control.control_receipt.artifact_hashes.{artifact}",
        )
    if require_daily_semantics:
        semantics = _mapping(
            value.get("daily_semantics"),
            "control.control_receipt.daily_semantics",
        )
        _assert_same_day(
            _row_date(
                semantics,
                "control.control_receipt.daily_semantics",
                ("as_of", "trade_date", "date"),
            ),
            as_of,
            "control.control_receipt.daily_semantics",
        )
        _list(
            semantics.get("actions"),
            "control.control_receipt.daily_semantics.actions",
        )
        _mapping(
            semantics.get("selection"),
            "control.control_receipt.daily_semantics.selection",
        )
        semantics_hash = _require_digest(
            value.get("daily_semantics_sha256"),
            "control.control_receipt.daily_semantics_sha256",
        )
        if canonical_sha256(semantics) != semantics_hash:
            raise BookTShadowError(
                "control.control_receipt.daily_semantics_sha256 does not match payload"
            )
    return value


def bind_book_t_shadow_input(value: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze and hash one daily control/shadow input.

    This is the producer-side helper.  It only adds missing content hashes; an
    existing mismatched hash is rejected.  The returned object is suitable for
    ``run_book_t_shadow`` and can be persisted as the next morning's frozen
    research input.
    """

    body = _json_copy(value)
    if not isinstance(body, dict):
        raise BookTShadowError("Book T shadow input must be an object")
    if int(body.get("schema_version", 0)) != BOOK_T_SHADOW_SCHEMA_VERSION:
        raise BookTShadowError("unsupported Book T shadow input schema_version")
    namespace = _text(body.get("namespace"))
    if namespace not in {"", BOOK_T_SHADOW_INPUT_NAMESPACE}:
        raise BookTShadowError(f"unexpected shadow input namespace: {namespace}")
    body["namespace"] = BOOK_T_SHADOW_INPUT_NAMESPACE
    _date(body.get("as_of"))
    lifecycle = isinstance(body.get("evidence_lifecycle"), Mapping)

    market = _mapping(body.get("market_input"), "market_input")
    market = _bind_market_input(market)
    market_hash = _text(market["market_input_sha256"])
    body["market_input"] = market

    assumptions = _mapping(body.get("assumptions"), "assumptions")
    body["assumptions"] = assumptions
    for name in ("budget_ratio", "fee_rate", "fill_model", "liquidity_model", "settlement_model"):
        if name not in assumptions:
            raise BookTShadowError(f"assumptions.{name} is required")

    for name, shadow in (("control", False), ("shadow", True)):
        body[name] = _bind_variant(
            _mapping(body.get(name), name),
            shadow=shadow,
            market_hash=market_hash,
            lifecycle=lifecycle,
        )

    if lifecycle:
        try:
            body["evidence_lifecycle"] = validate_lifecycle(body["evidence_lifecycle"])
        except (BookTV2EvidenceError, KeyError, TypeError) as exc:
            raise BookTShadowError(f"invalid evidence_lifecycle: {exc}") from exc

    _validate_input_dates(body)
    body.pop("input_sha256", None)
    body["input_sha256"] = canonical_sha256(body)
    return body


def _validate_bound_input(value: Mapping[str, Any]) -> dict[str, Any]:
    body = _json_copy(value)
    if not isinstance(body, dict):
        raise BookTShadowError("Book T shadow input must be an object")
    if _text(body.get("namespace")) != BOOK_T_SHADOW_INPUT_NAMESPACE:
        raise BookTShadowError("Book T shadow input namespace is not frozen")
    if int(body.get("schema_version", 0)) != BOOK_T_SHADOW_SCHEMA_VERSION:
        raise BookTShadowError("unsupported Book T shadow input schema_version")
    _date(body.get("as_of"))
    lifecycle = isinstance(body.get("evidence_lifecycle"), Mapping)
    if lifecycle:
        try:
            body["evidence_lifecycle"] = validate_lifecycle(body["evidence_lifecycle"])
        except (BookTV2EvidenceError, KeyError, TypeError) as exc:
            raise BookTShadowError(f"invalid evidence_lifecycle: {exc}") from exc
    actual = _text(body.get("input_sha256"))
    if not actual:
        raise BookTShadowError("input_sha256 is required")
    unsigned = dict(body)
    unsigned.pop("input_sha256", None)
    if actual != canonical_sha256(unsigned):
        raise BookTShadowError("input_sha256 does not match frozen input")

    market = _mapping(body.get("market_input"), "market_input")
    market_hash = _require_hash(market, "market_input_sha256", "market_input")
    for name in ("control", "shadow"):
        _bind_variant(
            _mapping(body.get(name), name),
            shadow=name == "shadow",
            market_hash=market_hash,
            lifecycle=lifecycle,
        )
    _validate_input_dates(body)
    return body


def _validate_etf_contract(
    row: Mapping[str, Any],
    *,
    as_of: str,
    fee_rate: float,
    fill_price: float,
    field_prefix: str,
) -> dict[str, Any]:
    try:
        contract = contract_from_record(row, strict=True)
    except InstrumentContractError as exc:
        raise BookTShadowError(f"{field_prefix} ETF instrument contract is not verified: {exc}") from exc
    assert contract is not None
    if contract.instrument_type != "etf":
        raise BookTShadowError(f"{field_prefix} ETF instrument contract type is invalid")
    if contract.code != _text(row.get("code")):
        raise BookTShadowError(f"{field_prefix} ETF instrument contract code does not match fill code")
    if int(row.get("lot_size") or 0) != contract.lot_size:
        raise BookTShadowError(f"{field_prefix} ETF lot_size does not match instrument contract")
    if _text(row.get("settlement_cycle")) != contract.settlement_cycle:
        raise BookTShadowError(f"{field_prefix} ETF settlement_cycle does not match instrument contract")
    if not math.isclose(contract.buy_fee_rate, fee_rate, rel_tol=0.0, abs_tol=1e-12):
        raise BookTShadowError(f"{field_prefix} ETF buy fee does not match frozen fee assumption")
    facts = row.get("market_data_facts")
    if not isinstance(facts, Mapping):
        raise BookTShadowError(f"{field_prefix} ETF market_data_facts is required")
    validation = validate_market_data(
        row,
        realtime=facts.get("realtime"),
        minute_rows=facts.get("minute_rows", facts.get("minute")),
        daily_rows=facts.get("daily_rows", facts.get("daily")),
        liquidity=facts.get("liquidity"),
        as_of=as_of,
        source=_text(row.get("market_data_source") or facts.get("source")),
    )
    if not validation.ok:
        raise BookTShadowError(
            f"{field_prefix} ETF market data contract is not verified: {validation.reason}"
        )
    minute_rows = facts.get("minute_rows", facts.get("minute"))
    minute_prices = [
        _finite(item.get("trade"), f"{field_prefix}.market_data_facts.minute.trade")
        for item in minute_rows
        if isinstance(item, Mapping) and item.get("trade") not in (None, "")
    ]
    if not minute_prices or not min(minute_prices) <= fill_price <= max(minute_prices):
        raise BookTShadowError(
            f"{field_prefix} ETF fill_price is outside validated minute trade facts"
        )
    return {
        "instrument_contract_buy_fee_rate": contract.buy_fee_rate,
        "instrument_contract_sell_fee_rate": contract.sell_fee_rate,
        "market_data_validation": validation.reason,
    }


def _validate_fill_rows(
    variant: Mapping[str, Any],
    *,
    market_hash: str,
    assumptions: Mapping[str, Any],
    as_of: str,
    field_prefix: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fills = _list(variant.get("fills"), f"{field_prefix}.fills")
    expected = {_text(code) for code in _list(variant.get("expected_fill_codes"), f"{field_prefix}.expected_fill_codes")}
    budget_ratio = _finite(assumptions.get("budget_ratio"), "assumptions.budget_ratio")
    fee_rate = _finite(assumptions.get("fee_rate"), "assumptions.fee_rate")
    account_equity = _finite(
        assumptions.get("account_equity", assumptions.get("initial_capital", 100000.0)),
        "assumptions.account_equity",
    )
    if not (0.0 < budget_ratio <= 1.0) or fee_rate < 0.0 or account_equity <= 0.0:
        raise BookTShadowError("budget, fee, and account assumptions are invalid")
    seen: set[str] = set()
    seen_fill_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    filled_notional = 0.0
    for index, raw in enumerate(fills):
        row = _mapping(raw, f"{field_prefix}.fills[{index}]")
        code = _text(row.get("code"))
        if not code:
            raise BookTShadowError(f"{field_prefix}.fills[{index}].code is required")
        fill_id = _text(row.get("fill_id"))
        if not fill_id:
            raise BookTShadowError(f"{field_prefix}.fills[{index}].fill_id is required")
        if fill_id in seen_fill_ids:
            raise BookTShadowError(f"{field_prefix}.fills[{index}] duplicates fill_id {fill_id}")
        seen_fill_ids.add(fill_id)
        if _text(row.get("market_input_sha256")) != market_hash:
            raise BookTShadowError(f"{field_prefix}.fills[{index}].market_input_sha256 mismatch")
        fill_day = _row_date(
            row,
            f"{field_prefix}.fills[{index}]",
            ("as_of", "trade_date", "date"),
        )
        _assert_same_day(fill_day, as_of, f"{field_prefix}.fills[{index}]")
        status = _text(row.get("status")).lower()
        if status not in {"filled", "skipped", "blocked"}:
            raise BookTShadowError(f"{field_prefix}.fills[{index}].status is invalid")
        if code in seen:
            raise BookTShadowError(f"{field_prefix}.fills[{index}] duplicates code {code}")
        item = dict(row)
        item["code"] = code
        item["fill_id"] = fill_id
        item["status"] = status
        if status == "filled":
            if _text(row.get("side")).upper() != "BUY":
                raise BookTShadowError(f"{field_prefix}.fills[{index}] side must be BUY")
            price = _finite(row.get("fill_price"), f"{field_prefix}.fills[{index}].fill_price")
            shares = _finite(row.get("shares"), f"{field_prefix}.fills[{index}].shares")
            notional = _finite(row.get("notional"), f"{field_prefix}.fills[{index}].notional")
            fee = _finite(row.get("fee"), f"{field_prefix}.fills[{index}].fee")
            if price <= 0 or shares <= 0 or notional <= 0 or fee < 0:
                raise BookTShadowError(f"{field_prefix}.fills[{index}] has invalid fill economics")
            if not math.isclose(price * shares, notional, rel_tol=0.0, abs_tol=0.02):
                raise BookTShadowError(f"{field_prefix}.fills[{index}].notional does not match price*shares")
            if not math.isclose(fee, notional * fee_rate, rel_tol=0.0, abs_tol=0.02):
                raise BookTShadowError(f"{field_prefix}.fills[{index}].fee does not match frozen fee assumption")
            if _text(row.get("instrument_type")).lower() not in {"equity", "stock", "etf"}:
                raise BookTShadowError(f"{field_prefix}.fills[{index}].instrument_type is invalid")
            tradability = _text(
                row.get("tradability_status") or row.get("instrument_status")
            ).lower()
            if tradability not in {"eligible", "tradable", "active", "ok"}:
                raise BookTShadowError(
                    f"{field_prefix}.fills[{index}] tradability is not verified"
                )
            if _text(row.get("liquidity_status")).lower() not in {"verified", "liquid", "eligible"}:
                raise BookTShadowError(f"{field_prefix}.fills[{index}] liquidity is not verified")
            if _text(row.get("market_contract_status")).lower() not in {"verified", "eligible"}:
                raise BookTShadowError(f"{field_prefix}.fills[{index}] market contract is not verified")
            if _text(row.get("instrument_type")).lower() == "etf":
                try:
                    lot_size = int(row.get("lot_size"))
                except (TypeError, ValueError) as exc:
                    raise BookTShadowError(f"{field_prefix}.fills[{index}].lot_size is required for ETF") from exc
                if (
                    lot_size <= 0
                    or not math.isclose(shares, round(shares), rel_tol=0.0, abs_tol=1e-9)
                    or int(round(shares)) % lot_size
                ):
                    raise BookTShadowError(f"{field_prefix}.fills[{index}] ETF shares do not match lot_size")
                if _text(row.get("settlement_cycle")) not in {"T+0", "T+1"}:
                    raise BookTShadowError(f"{field_prefix}.fills[{index}].settlement_cycle is unknown for ETF")
                if _text(row.get("market_data_source")).lower() not in {"p-xcapi", "xiaocao_api", "proprietary"}:
                    raise BookTShadowError(f"{field_prefix}.fills[{index}] ETF market source is not proprietary")
                if _text(row.get("market_price_field")).lower() != "trade":
                    raise BookTShadowError(f"{field_prefix}.fills[{index}] ETF minute price field is not trade")
                contract_fields = _validate_etf_contract(
                    row,
                    as_of=as_of,
                    fee_rate=fee_rate,
                    fill_price=price,
                    field_prefix=f"{field_prefix}.fills[{index}]",
                )
                item.update(contract_fields)
            filled_notional += notional
        else:
            if not _text(row.get("skip_reason")):
                raise BookTShadowError(f"{field_prefix}.fills[{index}].skip_reason is required")
        seen.add(code)
        normalized.append(item)
    if filled_notional > account_equity * budget_ratio + 0.02:
        raise BookTShadowError(f"{field_prefix}.fills exceed frozen theme budget")
    missing = sorted(expected - seen)
    if missing:
        raise BookTShadowError(f"{field_prefix}.fills missing expected codes: {missing}")
    unexpected = sorted(seen - expected)
    if unexpected:
        raise BookTShadowError(f"{field_prefix}.fills contain unexpected codes: {unexpected}")
    return normalized, [row for row in normalized if row["status"] == "filled"]


def _validate_holds(
    variant: Mapping[str, Any],
    *,
    market_hash: str,
    filled_rows: Sequence[Mapping[str, Any]],
    as_of: str,
    field_prefix: str,
) -> list[dict[str, Any]]:
    holds = _list(variant.get("holds"), f"{field_prefix}.holds")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    intervals: dict[str, list[tuple[str, str]]] = defaultdict(list)
    filled_by_id = {
        _text(row.get("fill_id")): row
        for row in filled_rows
        if _text(row.get("fill_id"))
    }
    for index, raw in enumerate(holds):
        row = _mapping(raw, f"{field_prefix}.holds[{index}]")
        if _text(row.get("market_input_sha256")) != market_hash:
            raise BookTShadowError(f"{field_prefix}.holds[{index}].market_input_sha256 mismatch")
        code = _text(row.get("code"))
        if not code:
            raise BookTShadowError(f"{field_prefix}.holds[{index}].code is required")
        observation_day = _row_date(
            row,
            f"{field_prefix}.holds[{index}]",
            ("as_of", "valuation_date", "trade_date", "date"),
        )
        _assert_same_day(observation_day, as_of, f"{field_prefix}.holds[{index}]")
        entry = _text(row.get("entry"))
        if not entry:
            raise BookTShadowError(f"{field_prefix}.holds[{index}].entry is required")
        entry_day = _date(entry)
        exit_value = _text(row.get("exit") or row.get("exit_date") or row.get("end"))
        if not exit_value:
            raise BookTShadowError(f"{field_prefix}.holds[{index}].exit is required")
        exit_day = _date(exit_value)
        if exit_day < entry_day or exit_day > (observation_day or as_of):
            raise BookTShadowError(f"{field_prefix}.holds[{index}] has an invalid hold interval")
        hold_id = _text(row.get("hold_id")) or code
        identity = (hold_id, entry_day, exit_day)
        if identity in seen:
            raise BookTShadowError(f"{field_prefix}.holds[{index}] duplicates hold path {identity[0]}")
        seen.add(identity)
        for previous_entry, previous_exit in intervals[code]:
            if entry_day <= previous_exit and previous_entry <= exit_day:
                raise BookTShadowError(f"{field_prefix}.holds[{index}] overlaps hold path {code}")
        intervals[code].append((entry_day, exit_day))
        item = dict(row)
        item["code"] = code
        item["entry"] = entry
        item["exit"] = exit_value
        item["as_of"] = observation_day
        fill_reference = _text(row.get("fill_reference"))
        if not fill_reference:
            raise BookTShadowError(f"{field_prefix}.holds[{index}].fill_reference is required")
        fill = filled_by_id.get(fill_reference)
        item["executable"] = bool(
            fill
            and code == _text(fill.get("code"))
            and _text(row.get("theme_id")) == _text(fill.get("theme_id"))
            and _text(row.get("expression_type")) == _text(fill.get("expression_type"))
        )
        item["fill_reference"] = fill_reference
        item["strat_ret"] = _finite(row.get("strat_ret"), f"{field_prefix}.holds[{index}].strat_ret")
        item["base_ret"] = _finite(row.get("base_ret"), f"{field_prefix}.holds[{index}].base_ret")
        item["theme_id"] = _text(row.get("theme_id")) or "unresolved"
        normalized.append(item)
    return normalized


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, int(math.floor((len(ordered) - 1) * fraction))))
    return ordered[index]


def _compound(values: Sequence[float]) -> float:
    equity = 1.0
    for value in values:
        equity *= 1.0 + float(value) / 100.0
    return (equity - 1.0) * 100.0


def _variant_summary(
    variant: Mapping[str, Any],
    fills: Sequence[Mapping[str, Any]],
    holds: Sequence[Mapping[str, Any]],
    assumptions: Mapping[str, Any],
) -> dict[str, Any]:
    filled_notional = sum(_finite(row.get("notional"), "fill.notional") for row in fills)
    fees = sum(_finite(row.get("fee"), "fill.fee") for row in fills)
    base = _finite(assumptions.get("account_equity", assumptions.get("initial_capital", 100000.0)), "assumptions.account_equity")
    weights: dict[str, float] = defaultdict(float)
    for row in fills:
        weights[_text(row.get("theme_id")) or "unresolved"] += _finite(row.get("notional"), "fill.notional")
    total_weight = sum(weights.values())
    normalized = {key: value / total_weight for key, value in weights.items()} if total_weight else {}
    returns = [_finite(row.get("strat_ret"), "hold.strat_ret") for row in holds]
    base_returns = [_finite(row.get("base_ret"), "hold.base_ret") for row in holds]
    alphas = [strat - benchmark for strat, benchmark in zip(returns, base_returns)]
    conditional: dict[str, dict[str, Any]] = {}
    for row in holds:
        key = f"{_text(row.get('instrument_type')) or 'unknown'}:{_text(row.get('expression_type')) or 'unknown'}"
        entry = conditional.setdefault(key, {"holds": 0, "alpha_sum": 0.0, "strat_sum": 0.0})
        entry["holds"] += 1
        entry["alpha_sum"] += _finite(row.get("strat_ret"), "hold.strat_ret") - _finite(row.get("base_ret"), "hold.base_ret")
        entry["strat_sum"] += _finite(row.get("strat_ret"), "hold.strat_ret")
    for entry in conditional.values():
        count = max(1, int(entry["holds"]))
        entry["alpha_mean"] = entry.pop("alpha_sum") / count
        entry["strat_mean"] = entry.pop("strat_sum") / count

    return {
        "filled_count": len(fills),
        "skipped_count": sum(1 for row in variant.get("fills", []) if _text(row.get("status")).lower() == "skipped"),
        "blocked_count": sum(1 for row in variant.get("fills", []) if _text(row.get("status")).lower() == "blocked"),
        "filled_notional": round(filled_notional, 8),
        "fees": round(fees, 8),
        "turnover": round(filled_notional / base, 8) if base > 0 else 0.0,
        "theme_concentration": {
            "risk_unit": "theme_slot",
            "hhi": round(sum(weight * weight for weight in normalized.values()), 8),
            "max_theme_weight": round(max(normalized.values(), default=0.0), 8),
            "theme_weights": {key: round(value, 8) for key, value in sorted(normalized.items())},
        },
        "relative_theme_beta": {
            "mean_return": round(sum(base_returns) / len(base_returns), 8) if base_returns else 0.0,
            "compounded_return": round(_compound(base_returns), 8),
        },
        "returns": {
            "strat_compounded": round(_compound(returns), 8),
            "base_compounded": round(_compound(base_returns), 8),
            "alpha_mean": round(sum(alphas) / len(alphas), 8) if alphas else 0.0,
        },
        "left_tail": {
            "min": round(min(returns, default=0.0), 8),
            "p10": round(_percentile(returns, 0.10), 8),
        },
        "conditional_results": conditional,
    }


def _decision_fingerprint(selection_plan: Mapping[str, Any]) -> str:
    """Identify a substantive selection decision, excluding daily bindings."""

    body = copy.deepcopy(dict(selection_plan))
    for field in (
        "as_of",
        "snapshot_sha256",
        "universe_sha256",
        "portfolio_sha256",
        "decision_revision",
        "selection_plan_sha256",
        "binding_receipt",
    ):
        body.pop(field, None)
    input_hashes = body.get("input_hashes")
    if isinstance(input_hashes, Mapping):
        body.pop("input_hashes", None)
    return canonical_sha256(body)


def _validate_variant(
    value: Mapping[str, Any],
    *,
    name: str,
    shadow: bool,
    market_hash: str,
    as_of: str,
    assumptions: Mapping[str, Any],
    lifecycle: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    variant = _mapping(value, name)
    receipt: dict[str, Any] | None = None
    if not shadow:
        receipt = _validate_control_receipt(
            _mapping(variant.get("control_receipt"), f"{name}.control_receipt"),
            as_of=as_of,
            require_daily_semantics=lifecycle,
        )
        if lifecycle and _text(variant.get("daily_semantics_sha256")) != _text(
            receipt.get("daily_semantics_sha256")
        ):
            raise BookTShadowError(
                f"{name}.daily_semantics_sha256 does not match the control receipt"
            )
    if shadow:
        plan = _mapping(variant.get("selection_plan"), f"{name}.selection_plan")
        _require_hash(plan, "selection_plan_sha256", f"{name}.selection_plan")
        for field in ("snapshot_sha256", "universe_sha256", "portfolio_sha256"):
            if _text(plan.get(field)):
                _require_digest(plan.get(field), f"{name}.selection_plan.{field}")
            elif _text(plan.get("plan_status")) == "ready":
                raise BookTShadowError(f"{name}.selection_plan.{field} is required for a ready plan")
        if _text(plan.get("plan_status")) == "ready":
            receipt = _mapping(plan.get("binding_receipt"), f"{name}.selection_plan.binding_receipt")
            if _text(receipt.get("status")) != "validated":
                raise BookTShadowError(f"{name}.selection_plan.binding_receipt is not validated")
            for field in ("snapshot_sha256", "universe_sha256", "portfolio_sha256"):
                if _text(receipt.get(field)) != _text(plan.get(field)):
                    raise BookTShadowError(
                        f"{name}.selection_plan.binding_receipt.{field} mismatch"
                    )
        if plan.get("daily_reevaluation_complete") is not True:
            raise BookTShadowError("shadow selection plan did not complete daily reevaluation")
    else:
        selection = _mapping(variant.get("selection"), f"{name}.selection")
        _require_hash(selection, "selection_sha256", f"{name}.selection")
    fills, filled = _validate_fill_rows(
        variant,
        market_hash=market_hash,
        assumptions=assumptions,
        as_of=as_of,
        field_prefix=name,
    )
    holds = _validate_holds(
        variant,
        market_hash=market_hash,
        filled_rows=filled,
        as_of=as_of,
        field_prefix=name,
    )
    output = dict(variant)
    output["source_roles"] = sorted({_text(role) for role in _list(variant.get("source_roles"), f"{name}.source_roles") if _text(role)})
    output["fills"] = fills
    output["holds"] = holds
    output["summary"] = _variant_summary(
        output,
        filled,
        [row for row in holds if row.get("executable") is True],
        assumptions,
    )
    return output, filled, holds


def run_book_t_shadow(value: Mapping[str, Any]) -> dict[str, Any]:
    """Run one frozen day through the v1 control/v2 shadow comparison seam."""

    frozen = _validate_bound_input(value)
    as_of = _date(frozen["as_of"])
    assumptions = _mapping(frozen.get("assumptions"), "assumptions")
    market = _mapping(frozen.get("market_input"), "market_input")
    market_hash = _text(market["market_input_sha256"])
    lifecycle_value = frozen.get("evidence_lifecycle")
    lifecycle = isinstance(lifecycle_value, Mapping)
    control, control_fills, control_holds = _validate_variant(
        frozen["control"],
        name="control",
        shadow=False,
        market_hash=market_hash,
        as_of=as_of,
        assumptions=assumptions,
        lifecycle=lifecycle,
    )
    shadow, shadow_fills, shadow_holds = _validate_variant(
        frozen["shadow"],
        name="shadow",
        shadow=True,
        market_hash=market_hash,
        as_of=as_of,
        assumptions=assumptions,
        lifecycle=lifecycle,
    )

    shadow_plan = _mapping(shadow.get("selection_plan"), "shadow.selection_plan")
    decision_fingerprint = _decision_fingerprint(shadow_plan)
    expected_codes = {_text(code) for code in _list(shadow.get("expected_fill_codes"), "shadow.expected_fill_codes")}
    filled_codes = {
        _text(row.get("code"))
        for row in shadow.get("fills", [])
        if _text(row.get("status")).lower() == "filled"
    }
    valid_reasons: list[str] = []
    if lifecycle:
        try:
            frozen_lifecycle = validate_lifecycle(lifecycle_value)
        except (BookTV2EvidenceError, TypeError) as exc:
            raise BookTShadowError(f"invalid evidence_lifecycle: {exc}") from exc
        lifecycle_decision = next(
            event
            for event in frozen_lifecycle["stages"]
            if event.get("stage") == "decision"
        )
        decision_data = _mapping(lifecycle_decision.get("data"), "evidence_lifecycle.decision.data")
        control_receipt = _mapping(control.get("control_receipt"), "control.control_receipt")
        if _text(decision_data.get("control_receipt_sha256")) != _text(
            control_receipt.get("receipt_sha256")
        ):
            valid_reasons.append("control_receipt_lifecycle_mismatch")
        if _text(decision_data.get("selection_plan_sha256")) != _text(
            shadow_plan.get("selection_plan_sha256")
        ):
            valid_reasons.append("selection_plan_lifecycle_mismatch")
        status_by_code = {
            _text(row.get("code")): _text(row.get("status")).lower()
            for row in shadow.get("fills", [])
        }
        if not expected_codes.issubset(status_by_code):
            valid_reasons.append("shadow_fill_outcome_incomplete")
        if any(status not in {"filled", "skipped", "blocked"} for status in status_by_code.values()):
            valid_reasons.append("shadow_fill_status_invalid")
        if shadow_plan.get("daily_reevaluation_complete") is not True:
            valid_reasons.append("daily_reevaluation_incomplete")
        # An empty selection with an explicit selector plan is a valid
        # engineering day: the producer has proven the full chain and chosen
        # not to invent an instrument when the evidence is insufficient.
    else:
        if not expected_codes.issubset(filled_codes):
            valid_reasons.append("shadow_fill_outcome_incomplete")
        if any(row.get("executable") is not True for row in shadow.get("holds", [])):
            valid_reasons.append("non_executable_hold_path")
        if shadow_plan.get("plan_status") != "ready":
            valid_reasons.append("selection_plan_not_executable")
        if not shadow.get("holds"):
            valid_reasons.append("shadow_hold_path_missing")
        if not shadow_plan.get("selected_themes"):
            valid_reasons.append("no_theme_decision")

    control_comp = control["summary"]["returns"]["strat_compounded"]
    shadow_comp = shadow["summary"]["returns"]["strat_compounded"]
    replay_key = canonical_sha256(
        {
            "input_sha256": frozen["input_sha256"],
            "market_input_sha256": market_hash,
            "control_selection": control.get("selection") or control.get("selection_plan"),
            "shadow_selection_plan": shadow_plan,
        }
    )
    return {
        "schema_version": BOOK_T_SHADOW_SCHEMA_VERSION,
        "namespace": BOOK_T_SHADOW_NAMESPACE,
        "as_of": frozen["as_of"],
        "market_date": as_of,
        "input_sha256": frozen["input_sha256"],
        "market_input_sha256": market_hash,
        "assumptions": assumptions,
        "frozen_input": copy.deepcopy(frozen),
        **({"evidence_lifecycle": copy.deepcopy(frozen_lifecycle)} if lifecycle else {}),
        "source_roles": shadow["source_roles"],
        "control": {**control, "fills": control["fills"], "holds": control["holds"]},
        "shadow": {**shadow, "fills": shadow["fills"], "holds": shadow["holds"]},
        "comparison": {
            "same_market_input": True,
            "same_assumptions": canonical_sha256(assumptions) == canonical_sha256(frozen["assumptions"]),
            "shadow_minus_control_compounded_return": round(shadow_comp - control_comp, 8),
            "shadow_minus_control_fees": round(shadow["summary"]["fees"] - control["summary"]["fees"], 8),
            "shadow_minus_control_turnover": round(
                shadow["summary"]["turnover"] - control["summary"]["turnover"], 8
            ),
        },
        "engineering": {
            "snapshot_bound": bool(_text(shadow_plan.get("snapshot_sha256"))),
            "universe_bound": bool(_text(shadow_plan.get("universe_sha256"))),
            "selection_plan_bound": bool(_text(shadow_plan.get("selection_plan_sha256"))),
            "control_receipt_bound": True,
            "decision_fingerprint": decision_fingerprint,
            "daily_reevaluation_complete": shadow_plan.get("daily_reevaluation_complete") is True,
            "fills_complete": not valid_reasons,
            "valid_theme_decision": not valid_reasons,
            "engineering_day_valid": not valid_reasons if lifecycle else None,
            "evidence_lifecycle_bound": lifecycle,
            "outcome_status": (
                _text(frozen_lifecycle.get("outcome_status")) if lifecycle else "matured"
            ),
            "outcome_matured": (
                any(event.get("stage") == "matured" for event in frozen_lifecycle.get("stages", []))
                if lifecycle
                else True
            ),
            "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0},
        },
        "validity_reasons": valid_reasons,
        "replay_key": replay_key,
    }


def _run_values(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    seen_trading_day_indices: set[int] = set()
    seen_hold_paths: dict[str, set[tuple[str, str]]] = {"control": set(), "shadow": set()}
    seen_hold_intervals: dict[str, list[tuple[str, str, str]]] = {"control": [], "shadow": []}
    for index, raw in enumerate(runs):
        run = _mapping(raw, f"runs[{index}]")
        if _text(run.get("namespace")) != BOOK_T_SHADOW_NAMESPACE:
            raise BookTShadowError(f"runs[{index}] is not a Book T v2 shadow artifact")
        day = _date(run.get("as_of"))
        if day in seen_dates:
            raise BookTShadowError(f"duplicate shadow trading day: {day}")
        seen_dates.add(day)
        mutations = _mapping(run.get("engineering", {}), f"runs[{index}].engineering").get("formal_ledger_mutations")
        if mutations != {"positions": 0, "account": 0, "trades": 0}:
            raise BookTShadowError("Book T v2 shadow artifact claims formal ledger mutation")
        frozen = _mapping(run.get("frozen_input"), f"runs[{index}].frozen_input")
        expected = run_book_t_shadow(frozen)
        if canonical_sha256(run) != canonical_sha256(expected):
            raise BookTShadowError(f"runs[{index}] is not a replay of its frozen input")
        if _date(expected.get("as_of")) != day:
            raise BookTShadowError(f"runs[{index}] frozen input date mismatch")
        market = _mapping(frozen.get("market_input"), f"runs[{index}].frozen_input.market_input")
        trading_day_index = int(market.get("trading_day_index"))
        if trading_day_index in seen_trading_day_indices:
            raise BookTShadowError(
                f"duplicate authoritative trading day index: {trading_day_index}"
            )
        seen_trading_day_indices.add(trading_day_index)
        for name in ("control", "shadow"):
            variant = _mapping(run.get(name), f"runs[{index}].{name}")
            for hold_index, raw_hold in enumerate(_list(variant.get("holds"), f"runs[{index}].{name}.holds")):
                hold = _mapping(raw_hold, f"runs[{index}].{name}.holds[{hold_index}]")
                identity = (
                    _text(hold.get("hold_id")) or _text(hold.get("code")),
                    _date(hold.get("entry")),
                )
                if identity in seen_hold_paths[name]:
                    raise BookTShadowError(
                        f"overlapping or duplicate {name} hold path: {identity[0]}"
                    )
                seen_hold_paths[name].add(identity)
                code = _text(hold.get("code"))
                entry = _date(hold.get("entry"))
                exit_value = _date(hold.get("exit"))
                for previous_code, previous_entry, previous_exit in seen_hold_intervals[name]:
                    if code == previous_code and entry <= previous_exit and previous_entry <= exit_value:
                        raise BookTShadowError(
                            f"overlapping {name} hold interval for {code}"
                        )
                seen_hold_intervals[name].append((code, entry, exit_value))
        values.append(run)
    return sorted(values, key=lambda row: str(row.get("as_of")))


def _validated_lifecycle_events(
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    seen_stages: set[tuple[str, str]] = set()
    stage_order = {"daily_mark": 0, "exit": 1, "matured": 2}
    last_stage_by_decision: dict[str, int] = {}
    for index, raw in enumerate(events):
        event = _mapping(raw, f"lifecycle_events[{index}]")
        event_id = _text(event.get("event_id"))
        unsigned = dict(event)
        unsigned.pop("event_id", None)
        if not event_id or event_id != canonical_sha256(unsigned):
            raise BookTShadowError(f"lifecycle_events[{index}] failed integrity validation")
        decision_id = _text(event.get("decision_id"))
        stage = _text(event.get("stage"))
        if not decision_id or stage not in {"daily_mark", "exit", "matured"}:
            raise BookTShadowError(f"lifecycle_events[{index}] has an invalid decision/stage")
        if event.get("namespace") != "book_t_v2_evidence" or event.get(
            "protocol_id"
        ) != "book-t-v2-evidence-lifecycle-v1":
            raise BookTShadowError(f"lifecycle_events[{index}] protocol is invalid")
        try:
            schema_version = int(event.get("schema_version", 0))
        except (TypeError, ValueError) as exc:
            raise BookTShadowError(f"lifecycle_events[{index}] schema is invalid") from exc
        if schema_version != 1:
            raise BookTShadowError(f"lifecycle_events[{index}] schema is invalid")
        if not isinstance(event.get("data"), Mapping):
            raise BookTShadowError(f"lifecycle_events[{index}].data must be an object")
        key = (decision_id, stage)
        if key in seen_stages:
            raise BookTShadowError(f"duplicate lifecycle event stage: {decision_id}:{stage}")
        previous_rank = last_stage_by_decision.get(decision_id, -1)
        if stage_order[stage] < previous_rank:
            raise BookTShadowError(f"lifecycle event stages are out of order: {decision_id}")
        seen_stages.add(key)
        last_stage_by_decision[decision_id] = stage_order[stage]
        values.append(event)
    stages_by_decision: dict[str, set[str]] = defaultdict(set)
    for event in values:
        stages_by_decision[_text(event.get("decision_id"))].add(_text(event.get("stage")))
    for decision_id, stages in stages_by_decision.items():
        if "exit" in stages and "daily_mark" not in stages:
            raise BookTShadowError(f"exit event has no daily mark: {decision_id}")
        if "matured" in stages and "exit" not in stages:
            raise BookTShadowError(f"matured event has no exit: {decision_id}")
    return values


def _matured_holds(
    run: Mapping[str, Any],
    *,
    lifecycle: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matured = [event for event in events if _text(event.get("stage")) == "matured"]
    if not matured:
        return []
    fill_by_code = {
        _text(row.get("code")): row
        for row in _list(_mapping(run.get("shadow"), "run.shadow").get("fills"), "run.shadow.fills")
        if _text(row.get("code")) and _text(row.get("status")).lower() == "filled"
    }
    rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    decision_day = _date(lifecycle.get("as_of"))
    for event in matured:
        data = _mapping(event.get("data"), "lifecycle_event.data")
        outcome_rows = _list(data.get("rows"), "lifecycle_event.data.rows")
        for index, raw in enumerate(outcome_rows):
            outcome = _mapping(raw, f"lifecycle_event.data.rows[{index}]")
            code = _text(outcome.get("code"))
            if not code or code in seen_codes:
                raise BookTShadowError("matured outcome codes must be unique and non-empty")
            fill = fill_by_code.get(code)
            if fill is None:
                raise BookTShadowError(
                    f"matured outcome has no canonical shadow fill: {code}"
                )
            outcome_day = _row_date(
                outcome,
                f"lifecycle_event.data.rows[{index}]",
                ("as_of", "trade_date", "date"),
            )
            if outcome_day < decision_day:
                raise BookTShadowError("matured outcome precedes its decision day")
            rows.append(
                {
                    "hold_id": f"matured:{_text(lifecycle.get('decision_id'))}:{code}",
                    "code": code,
                    "entry": decision_day,
                    "exit": outcome_day,
                    "as_of": decision_day,
                    "fill_reference": _text(fill.get("fill_id")),
                    "executable": True,
                    "strat_ret": _finite(outcome.get("strat_ret"), "matured.strat_ret"),
                    "base_ret": _finite(outcome.get("base_ret"), "matured.base_ret"),
                    "theme_id": _text(outcome.get("theme_id") or fill.get("theme_id")) or "unresolved",
                    "instrument_type": _text(
                        outcome.get("instrument_type") or fill.get("instrument_type")
                    ) or "unknown",
                    "expression_type": _text(
                        outcome.get("expression_type") or fill.get("expression_type")
                    ) or "unknown",
                    "outcome_event_id": _text(event.get("event_id")),
                }
            )
            seen_codes.add(code)
    return rows


def _coverage(runs: Sequence[Mapping[str, Any]], holds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    themes: set[str] = set()
    roles: set[str] = set()
    instruments: set[str] = set()
    expressions: set[str] = set()
    filled = skipped = blocked = 0
    etf_candidates = 0
    etf_contract_exclusions = 0
    non_executable_hold_paths = 0
    non_tradable_filled_outcomes = 0
    for run in runs:
        shadow = _mapping(run.get("shadow"), "run.shadow")
        executable_fill_rows = [
            row
            for row in _list(shadow.get("fills"), "run.shadow.fills")
            if _text(_mapping(row, "run.shadow.fill").get("status")).lower() == "filled"
        ]
        if executable_fill_rows:
            roles.update(_text(role) for role in shadow.get("source_roles", []) if _text(role))
        non_executable_hold_paths += sum(
            1
            for row in _list(shadow.get("holds"), "run.shadow.holds")
            if _mapping(row, "run.shadow.hold").get("executable") is not True
        )
        for row in shadow.get("fills", []):
            status = _text(row.get("status")).lower()
            filled += status == "filled"
            skipped += status == "skipped"
            blocked += status == "blocked"
            if status == "filled":
                if _text(row.get("theme_id")):
                    themes.add(_text(row.get("theme_id")))
                if _text(row.get("instrument_type")):
                    instruments.add(_text(row.get("instrument_type")))
                if _text(row.get("expression_type")):
                    expressions.add(_text(row.get("expression_type")))
            if status == "filled" and _text(
                row.get("tradability_status") or row.get("instrument_status")
            ).lower() not in {"eligible", "tradable", "active", "ok"}:
                non_tradable_filled_outcomes += 1
            if _text(row.get("instrument_type")).lower() == "etf":
                etf_candidates += 1
                if status != "filled":
                    etf_contract_exclusions += 1
    for row in holds:
        if _text(row.get("theme_id")):
            themes.add(_text(row.get("theme_id")))
        if _text(row.get("instrument_type")):
            instruments.add(_text(row.get("instrument_type")))
        if _text(row.get("expression_type")):
            expressions.add(_text(row.get("expression_type")))
    positive = [max(0.0, _finite(row.get("strat_ret"), "hold.strat_ret") - _finite(row.get("base_ret"), "hold.base_ret")) for row in holds]
    positive_total = sum(positive)
    winner_share = max(positive, default=0.0) / positive_total if positive_total > 0 else 0.0
    return {
        "unique_themes": len(themes),
        "themes": sorted(themes),
        "source_roles": len(roles),
        "source_role_names": sorted(roles),
        "instrument_types": len(instruments),
        "instrument_type_names": sorted(instruments),
        "expression_types": len(expressions),
        "expression_type_names": sorted(expressions),
        "filled_outcomes": filled,
        "skipped_outcomes": skipped,
        "blocked_outcomes": blocked,
        "non_tradable_filled_outcomes": non_tradable_filled_outcomes,
        "non_executable_hold_paths": non_executable_hold_paths,
        "etf_candidates": etf_candidates,
        "etf_contract_exclusions": etf_contract_exclusions,
        "etf_contract_exclusion_rate": round(
            etf_contract_exclusions / etf_candidates if etf_candidates else 0.0,
            8,
        ),
        "winner_alpha_share": round(winner_share, 8),
    }


def evaluate_book_t_shadow(
    runs: Sequence[Mapping[str, Any]],
    *,
    min_burn_in_days: int = BOOK_T_SHADOW_MIN_BURN_IN_DAYS,
    min_strategy_days: int = BOOK_T_SHADOW_MIN_STRATEGY_DAYS,
    min_valid_decisions: int = BOOK_T_SHADOW_MIN_VALID_DECISIONS,
    n_tried: int = 1,
    min_holds: int = 8,
    lifecycle_events: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluate daily shadow artifacts without authorizing promotion."""

    min_burn_in_days = _research_floor(
        min_burn_in_days,
        BOOK_T_SHADOW_MIN_BURN_IN_DAYS,
        "min_burn_in_days",
    )
    min_strategy_days = _research_floor(
        min_strategy_days,
        BOOK_T_SHADOW_MIN_STRATEGY_DAYS,
        "min_strategy_days",
    )
    min_valid_decisions = _research_floor(
        min_valid_decisions,
        BOOK_T_SHADOW_MIN_VALID_DECISIONS,
        "min_valid_decisions",
    )
    if int(n_tried) < 1:
        raise BookTShadowError("n_tried must be >= 1")
    ordered = _run_values(runs)
    lifecycle_mode = any(isinstance(run.get("evidence_lifecycle"), Mapping) for run in ordered)
    if lifecycle_mode and any(
        not isinstance(run.get("evidence_lifecycle"), Mapping) for run in ordered
    ):
        raise BookTShadowError("cannot mix lifecycle and legacy shadow runs")
    validated_events = _validated_lifecycle_events(lifecycle_events)
    if validated_events and not lifecycle_mode:
        raise BookTShadowError("lifecycle events require lifecycle shadow runs")
    events_by_decision: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in validated_events:
        events_by_decision[_text(event.get("decision_id"))].append(event)
    effective_runs: list[dict[str, Any]] = [copy.deepcopy(run) for run in ordered]
    lifecycle_rows = [
        validate_lifecycle(_mapping(run.get("evidence_lifecycle"), "run.evidence_lifecycle"))
        for run in ordered
    ] if lifecycle_mode else []
    known_decision_ids = {_text(row.get("decision_id")) for row in lifecycle_rows}
    if any(_text(event.get("decision_id")) not in known_decision_ids for event in validated_events):
        raise BookTShadowError("lifecycle event is not bound to a supplied frozen decision")
    for run, lifecycle in zip(effective_runs, lifecycle_rows):
        decision_events = events_by_decision.get(_text(lifecycle.get("decision_id")), [])
        matured_holds = _matured_holds(
            run,
            lifecycle=lifecycle,
            events=decision_events,
        )
        if matured_holds:
            shadow = _mapping(run.get("shadow"), "run.shadow")
            shadow["holds"] = list(shadow.get("holds", [])) + matured_holds
            run["shadow"] = shadow
        engineering = _mapping(run.get("engineering"), "run.engineering")
        engineering["outcome_matured"] = any(
            _text(event.get("stage")) == "matured" for event in decision_events
        )
        engineering["outcome_status"] = (
            "matured"
            if engineering["outcome_matured"]
            else _text(lifecycle.get("outcome_status"))
        )
        run["engineering"] = engineering
    shadow_holds = [
        row
        for run in effective_runs
        for row in _mapping(run["shadow"], "run.shadow").get("holds", [])
        if _mapping(row, "run.shadow.hold").get("executable") is True
    ]
    control_holds = [
        row
        for run in effective_runs
        for row in _mapping(run["control"], "run.control").get("holds", [])
        if _mapping(row, "run.control.hold").get("executable") is True
    ]
    shadow_verdict = trend_guards.evaluate_trend(
        shadow_holds,
        n_tried=n_tried,
        cache_only=True,
        min_holds=min_holds,
    )
    control_verdict = trend_guards.evaluate_trend(
        control_holds,
        n_tried=n_tried,
        cache_only=True,
        min_holds=min_holds,
    )
    coverage = _coverage(effective_runs, shadow_holds)
    valid_decision_fingerprints = {
        _text(_mapping(run.get("engineering"), "run.engineering").get("decision_fingerprint"))
        for run in effective_runs
        if _mapping(run.get("engineering"), "run.engineering").get("valid_theme_decision") is True
        and (
            not lifecycle_mode
            or _mapping(run.get("engineering"), "run.engineering").get("outcome_matured") is True
        )
    }
    valid_decisions = len(valid_decision_fingerprints - {""})
    real_lifecycle_rows = [
        row
        for row in lifecycle_rows
        if row.get("run_mode") == "real"
        and _mapping(row.get("provenance"), "run.evidence_lifecycle.provenance").get("is_rehearsal") is False
    ]
    matured_decision_ids = {
        _text(event.get("decision_id"))
        for event in validated_events
        if _text(event.get("stage")) == "matured"
    }
    matured_real_days = sum(
        _text(row.get("decision_id")) in matured_decision_ids
        for row in real_lifecycle_rows
    )
    counted_runs = [
        run
        for run in ordered
        if not lifecycle_mode
        or (
            isinstance(run.get("evidence_lifecycle"), Mapping)
            and _text(run["evidence_lifecycle"].get("run_mode")).lower() == "real"
            and _mapping(run["evidence_lifecycle"].get("provenance"), "run.evidence_lifecycle.provenance").get("is_rehearsal") is False
        )
    ]
    trading_days = len(counted_runs)
    trading_day_indices = sorted(
        int(
            _mapping(
                _mapping(run.get("frozen_input"), "run.frozen_input").get("market_input"),
                "run.frozen_input.market_input",
            ).get("trading_day_index")
        )
        for run in counted_runs
    )
    trading_days_contiguous = (
        not trading_day_indices
        or trading_day_indices == list(
            range(trading_day_indices[0], trading_day_indices[-1] + 1)
        )
    )
    hard_rejections: list[str] = []
    if not ordered:
        hard_rejections.append("no_shadow_runs")
    if any(not _mapping(run.get("engineering"), "run.engineering").get("daily_reevaluation_complete") for run in ordered):
        hard_rejections.append("daily_reevaluation_incomplete")
    if any(_mapping(run.get("engineering"), "run.engineering").get("formal_ledger_mutations") != {"positions": 0, "account": 0, "trades": 0} for run in ordered):
        hard_rejections.append("formal_ledger_mutation")
    if any(
        not _text(_mapping(run.get("engineering"), "run.engineering").get("decision_fingerprint"))
        for run in ordered
    ):
        hard_rejections.append("decision_unbound")
    if not trading_days_contiguous:
        hard_rejections.append("trading_day_gap")
    if not lifecycle_mode:
        if coverage["unique_themes"] < 2:
            hard_rejections.append("single_theme")
        if coverage["source_roles"] < 2:
            hard_rejections.append("single_kol")
        if coverage["instrument_types"] < 2 or coverage["expression_types"] < 2:
            hard_rejections.append("single_expression_type")
        if coverage["non_tradable_filled_outcomes"]:
            hard_rejections.append("non_tradable_return")
        if coverage["non_executable_hold_paths"]:
            hard_rejections.append("non_executable_hold_path")
        if coverage["winner_alpha_share"] >= 0.5:
            hard_rejections.append("single_winner")
    if ordered and any(not _text(run.get("market_input_sha256")) for run in ordered):
        hard_rejections.append("market_input_unbound")

    evidence_summary = (
        lifecycle_summary(lifecycle_rows, events=validated_events)
        if lifecycle_mode
        else None
    )
    pending: list[str] = []
    if trading_days < int(min_burn_in_days):
        pending.append("engineering_burn_in")
    if trading_days < int(min_strategy_days) or valid_decisions < int(min_valid_decisions):
        pending.append("strategy_sample_floor")
    outcome_pending = 0
    if lifecycle_mode:
        outcome_pending = int((evidence_summary or {}).get("outcome_pending", 0))
        if outcome_pending:
            pending.append("outcome_pending")
    if hard_rejections:
        status = "REJECTED"
    elif pending:
        status = "pending_observation"
    elif shadow_verdict["verdict"] != "PASS":
        status = "REJECTED"
        hard_rejections.append("trend_guards")
    else:
        status = "PASS"

    burn_in_gate = (
        engineering_burn_in_gate(
            lifecycle_rows,
            required_days=int(min_burn_in_days),
        )
        if lifecycle_mode
        else None
    )

    def aggregate_summary(name: str) -> dict[str, Any]:
        all_fill_rows = [
            row
            for run in effective_runs
            for row in _mapping(run[name], f"run.{name}").get("fills", [])
        ]
        all_fills = [row for row in all_fill_rows if _text(row.get("status")).lower() == "filled"]
        all_holds = [
            row
            for run in effective_runs
            for row in _mapping(run[name], f"run.{name}").get("holds", [])
            if _mapping(row, f"run.{name}.hold").get("executable") is True
        ]
        return _variant_summary(
            {"fills": all_fill_rows},
            all_fills,
            all_holds,
            _mapping(ordered[0].get("assumptions"), "run.assumptions") if ordered else {"account_equity": 100000.0},
        )

    aggregate_control = aggregate_summary("control")
    aggregate_shadow = aggregate_summary("shadow")

    return {
        "schema_version": BOOK_T_SHADOW_SCHEMA_VERSION,
        "namespace": BOOK_T_SHADOW_NAMESPACE,
        "protocol_id": BOOK_T_SHADOW_PROTOCOL_ID,
        "status": status,
        "pending_reasons": pending,
        "rejected_reasons": hard_rejections,
        "sample": {
            "trading_days": trading_days,
            "trading_day_indices": trading_day_indices,
            "trading_days_contiguous": trading_days_contiguous,
            "valid_theme_decisions": valid_decisions,
            "min_burn_in_days": int(min_burn_in_days),
            "min_strategy_days": int(min_strategy_days),
            "min_valid_decisions": int(min_valid_decisions),
            "burn_in_complete": trading_days >= int(min_burn_in_days),
            "strategy_floor_complete": trading_days >= int(min_strategy_days) and valid_decisions >= int(min_valid_decisions),
            "real_trading_days": len(real_lifecycle_rows) if lifecycle_mode else trading_days,
            "rehearsal_days_excluded": len(ordered) - len(real_lifecycle_rows) if lifecycle_mode else 0,
            "outcome_pending": outcome_pending,
            "outcome_matured": matured_real_days if lifecycle_mode else len(shadow_holds),
        },
        "engineering": {
            "hash_bound": all(bool(_text(run.get("input_sha256")) and _text(run.get("market_input_sha256"))) for run in ordered),
            "shadow_isolated": all(_mapping(run.get("engineering"), "run.engineering").get("formal_ledger_mutations") == {"positions": 0, "account": 0, "trades": 0} for run in ordered),
            "daily_reevaluation_complete": all(_mapping(run.get("engineering"), "run.engineering").get("daily_reevaluation_complete") is True for run in ordered),
            "burn_in_complete": trading_days >= int(min_burn_in_days),
            "trading_days_contiguous": trading_days_contiguous,
            "real_day_only_gate": lifecycle_mode,
            "outcome_pending": outcome_pending,
        },
        "coverage": coverage,
        "metrics": {
            "control": aggregate_control,
            "shadow": aggregate_shadow,
            "shadow_verdict": shadow_verdict,
            "control_verdict": control_verdict,
            "left_tail": {
                "shadow_min": min((_finite(row.get("strat_ret"), "hold.strat_ret") for row in shadow_holds), default=0.0),
                "control_min": min((_finite(row.get("strat_ret"), "hold.strat_ret") for row in control_holds), default=0.0),
            },
        },
        "shadow_verdict": shadow_verdict,
        "control_verdict": control_verdict,
        "comparison": {
            "control": aggregate_control,
            "shadow": aggregate_shadow,
            "shadow_compounded_alpha": shadow_verdict["compounded"]["alpha"],
            "control_compounded_alpha": control_verdict["compounded"]["alpha"],
            "shadow_minus_control_alpha": round(
                shadow_verdict["compounded"]["alpha"] - control_verdict["compounded"]["alpha"], 8
            ),
        },
        "parameters": {"n_tried": int(n_tried), "min_holds": int(min_holds)},
        "evidence_lifecycle": evidence_summary,
        "burn_in_gate": burn_in_gate,
    }


def _write_json(path: Path, value: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
    )


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _atomic_write_text(
        path,
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str) + "\n" for row in rows),
    )


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _render_report(evaluation: Mapping[str, Any], *, run_id: str) -> str:
    sample = _mapping(evaluation.get("sample"), "evaluation.sample")
    coverage = _mapping(evaluation.get("coverage"), "evaluation.coverage")
    shadow = _mapping(evaluation.get("shadow_verdict"), "evaluation.shadow_verdict")
    control = _mapping(evaluation.get("control_verdict"), "evaluation.control_verdict")
    shadow_metrics = _mapping(_mapping(evaluation.get("metrics"), "evaluation.metrics").get("shadow"), "evaluation.metrics.shadow")
    control_metrics = _mapping(_mapping(evaluation.get("metrics"), "evaluation.metrics").get("control"), "evaluation.metrics.control")
    shadow_compounded = _mapping(shadow.get("compounded"), "evaluation.shadow_verdict.compounded")
    control_compounded = _mapping(control.get("compounded"), "evaluation.control_verdict.compounded")
    shadow_walk_forward = _mapping(shadow.get("walk_forward"), "evaluation.shadow_verdict.walk_forward")
    shadow_non_bull = _mapping(shadow.get("non_bull"), "evaluation.shadow_verdict.non_bull")
    shadow_concentration = _mapping(shadow_metrics.get("theme_concentration"), "evaluation.metrics.shadow.theme_concentration")
    shadow_left_tail = _mapping(shadow_metrics.get("left_tail"), "evaluation.metrics.shadow.left_tail")
    return "\n".join(
        [
            "# Book T v2 shadow research",
            "",
            f"- run_id: `{run_id}`",
            f"- status: `{evaluation.get('status')}`",
            f"- protocol: `{evaluation.get('protocol_id')}`",
            "",
            "## Consumer gate",
            "",
            f"- trading days: {sample.get('trading_days', 0)} / {sample.get('min_strategy_days', 0)}",
            f"- valid theme decisions: {sample.get('valid_theme_decisions', 0)} / {sample.get('min_valid_decisions', 0)}",
            f"- engineering burn-in: `{sample.get('burn_in_complete')}`",
            f"- outcome lifecycle: pending {sample.get('outcome_pending', 0)} / matured {sample.get('outcome_matured', 0)}",
            f"- trend guards: `{shadow.get('verdict')}`",
            f"- pending: `{', '.join(evaluation.get('pending_reasons') or []) or 'none'}`",
            f"- rejected: `{', '.join(evaluation.get('rejected_reasons') or []) or 'none'}`",
            "",
            "## Control versus shadow economics",
            "",
            f"- compounded return: control {control_compounded.get('strat', 0.0):+.3f}% / shadow {shadow_compounded.get('strat', 0.0):+.3f}%",
            f"- compounded theme beta: control {control_compounded.get('base', 0.0):+.3f}% / shadow {shadow_compounded.get('base', 0.0):+.3f}%",
            f"- compounded alpha: control {control_compounded.get('alpha', 0.0):+.3f}pp / shadow {shadow_compounded.get('alpha', 0.0):+.3f}pp",
            f"- max drawdown: control {control.get('max_drawdown', 0.0):.3f}% / shadow {shadow.get('max_drawdown', 0.0):.3f}%",
            f"- left tail: min {shadow_left_tail.get('min', 0.0):+.3f}% / p10 {shadow_left_tail.get('p10', 0.0):+.3f}%",
            f"- turnover: control {control_metrics.get('turnover', 0.0):.3%} / shadow {shadow_metrics.get('turnover', 0.0):.3%}",
            f"- fees: control {control_metrics.get('fees', 0.0):.2f} / shadow {shadow_metrics.get('fees', 0.0):.2f}",
            f"- concentration HHI/max theme: {shadow_concentration.get('hhi', 0.0):.4f} / {shadow_concentration.get('max_theme_weight', 0.0):.1%}",
            f"- walk-forward alpha: train {shadow_walk_forward.get('train_alpha', 0.0):+.3f}pp / test {shadow_walk_forward.get('test_alpha', 0.0):+.3f}pp",
            f"- non-bull alpha: {shadow_non_bull.get('alpha_mean', 0.0):+.3f}pp (n={shadow_non_bull.get('n_holds', 0)})",
            "",
            "## Conditional expression results",
            "",
            "```json",
            json.dumps(shadow_metrics.get("conditional_results", {}), ensure_ascii=False, sort_keys=True),
            "```",
            "",
            "## Coverage and anti-concentration",
            "",
            f"- themes: {coverage.get('unique_themes', 0)} ({', '.join(coverage.get('themes') or [])})",
            f"- source roles: {coverage.get('source_roles', 0)}",
            f"- instrument types: {coverage.get('instrument_types', 0)}",
            f"- expression types: {coverage.get('expression_types', 0)}",
            f"- ETF contract exclusions: {coverage.get('etf_contract_exclusions', 0)}/{coverage.get('etf_candidates', 0)} ({float(coverage.get('etf_contract_exclusion_rate', 0.0)):.1%})",
            f"- non-executable hold paths excluded: {coverage.get('non_executable_hold_paths', 0)}",
            f"- largest positive-alpha share: {float(coverage.get('winner_alpha_share', 0.0)):.1%}",
            "",
            "The artifact is shadow-only: it does not mutate positions, accounts, or trades.",
            "",
        ]
    )


def write_book_t_shadow_artifacts(
    runs: Sequence[Mapping[str, Any]],
    evaluation: Mapping[str, Any],
    *,
    output_dir: Path,
    run_id: str,
    frozen_inputs: Sequence[Mapping[str, Any]],
    git_state: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    """Persist a namespaced research run; no formal ledger path is accepted."""

    ordered = _run_values(runs)
    if len(frozen_inputs) != len(ordered):
        raise BookTShadowError("frozen_inputs and runs must have the same length")
    run_token = str(run_id).strip()
    if not run_token or Path(run_token).name != run_token or run_token in {".", ".."}:
        raise BookTShadowError("run_id must be a single safe path component")
    root = Path(output_dir) / run_token
    root.mkdir(parents=True, exist_ok=True)
    frozen = [_validate_bound_input(value) for value in frozen_inputs]
    if [str(run.get("input_sha256")) for run in ordered] != [str(value.get("input_sha256")) for value in frozen]:
        raise BookTShadowError("frozen_inputs do not match daily shadow runs")
    frozen_input_sha256 = canonical_sha256(frozen)
    existing_manifest = root / "manifest.json"
    if existing_manifest.exists():
        try:
            previous = json.loads(existing_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BookTShadowError(f"existing shadow manifest is unreadable: {existing_manifest}") from exc
        previous_sha = _text(_mapping(previous, "existing manifest").get("inputs", {}).get("frozen_input_sha256"))
        if previous_sha and previous_sha != frozen_input_sha256:
            raise BookTShadowError("run_id already contains a different frozen input")
    frozen_path = root / "frozen_inputs.json"
    daily_path = root / "daily_runs.jsonl"
    fills_path = root / "simulated_fills.jsonl"
    holds_path = root / "hold_paths.jsonl"
    verdict_path = root / "verdict.json"
    report_path = root / "report.md"
    manifest_path = root / "manifest.json"
    _write_json(frozen_path, frozen)
    _write_jsonl(daily_path, ordered)
    _write_jsonl(
        fills_path,
        [
            {"as_of": run["as_of"], "variant": "control", **row}
            for run in ordered
            for row in _mapping(run["control"], "run.control").get("fills", [])
        ]
        + [
            {"as_of": run["as_of"], "variant": "v2_shadow", **row}
            for run in ordered
            for row in _mapping(run["shadow"], "run.shadow").get("fills", [])
        ],
    )
    _write_jsonl(
        holds_path,
        [
            {"as_of": run["as_of"], "variant": "control", **row}
            for run in ordered
            for row in _mapping(run["control"], "run.control").get("holds", [])
        ]
        + [
            {"as_of": run["as_of"], "variant": "v2_shadow", **row}
            for run in ordered
            for row in _mapping(run["shadow"], "run.shadow").get("holds", [])
        ],
    )
    _write_json(verdict_path, dict(evaluation))
    _atomic_write_text(report_path, _render_report(evaluation, run_id=str(run_id)))

    manifest = {
        "schema_version": BOOK_T_SHADOW_SCHEMA_VERSION,
        "namespace": BOOK_T_SHADOW_NAMESPACE,
        "run_id": str(run_id),
        "protocol_id": BOOK_T_SHADOW_PROTOCOL_ID,
        "parameters": {
            "n_tried": evaluation.get("parameters", {}).get("n_tried", 1),
            "min_holds": evaluation.get("parameters", {}).get("min_holds", 8),
            "cache_only": True,
            "min_burn_in_days": evaluation.get("sample", {}).get("min_burn_in_days"),
            "min_strategy_days": evaluation.get("sample", {}).get("min_strategy_days"),
            "min_valid_decisions": evaluation.get("sample", {}).get("min_valid_decisions"),
        },
        "inputs": {
            "frozen_inputs": str(frozen_path),
            "frozen_input_sha256": frozen_input_sha256,
            "market_input_sha256": sorted({_text(run.get("market_input_sha256")) for run in ordered}),
            "n_days": len(ordered),
            "n_valid_decisions": evaluation.get("sample", {}).get("valid_theme_decisions", 0),
        },
        "artifacts": {
            "manifest": str(manifest_path),
            "verdict": str(verdict_path),
            "report": str(report_path),
            "daily_runs": str(daily_path),
            "simulated_fills": str(fills_path),
            "hold_paths": str(holds_path),
        },
        "verdict": {
            "status": evaluation.get("status"),
            "pending_reasons": evaluation.get("pending_reasons", []),
            "rejected_reasons": evaluation.get("rejected_reasons", []),
        },
        "diagnostics": {
            "coverage": evaluation.get("coverage", {}),
            "engineering": evaluation.get("engineering", {}),
            "sample": evaluation.get("sample", {}),
            "comparison": evaluation.get("comparison", {}),
            "evidence_lifecycle": evaluation.get("evidence_lifecycle"),
            "burn_in_gate": evaluation.get("burn_in_gate"),
        },
        "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0},
        "git": dict(git_state or {"commit": None, "dirty": False}),
    }
    _write_json(manifest_path, manifest)
    return {
        "root": root,
        "frozen_inputs": frozen_path,
        "daily_runs": daily_path,
        "simulated_fills": fills_path,
        "hold_paths": holds_path,
        "verdict": verdict_path,
        "report": report_path,
        "manifest": manifest_path,
    }


__all__ = [
    "BOOK_T_CONTROL_ARTIFACT_PATHS",
    "BOOK_T_SHADOW_MIN_BURN_IN_DAYS",
    "BOOK_T_SHADOW_MIN_STRATEGY_DAYS",
    "BOOK_T_SHADOW_MIN_VALID_DECISIONS",
    "BOOK_T_SHADOW_INPUT_NAMESPACE",
    "BOOK_T_SHADOW_NAMESPACE",
    "BOOK_T_SHADOW_PROTOCOL_ID",
    "BOOK_T_SHADOW_SCHEMA_VERSION",
    "BookTShadowError",
    "bind_book_t_shadow_input",
    "evaluate_book_t_shadow",
    "run_book_t_shadow",
    "write_book_t_shadow_artifacts",
]
