"""Pure helpers that normalize raw Xiaocao API response shapes.

These functions are intentionally side-effect-free and have no `self` —
extracting them keeps `XiaocaoClient` focused on transport and lets tests
exercise normalization with fixture payloads.
"""
from __future__ import annotations

from typing import Any, Iterable

from .errors import ApiSchemaError


def normalize_api_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def as_list_of_dicts(result: Any, context: str) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "list", "rows", "result"):
            if isinstance(result.get(key), list):
                return result[key]
        return [value for value in result.values() if isinstance(value, dict)]
    raise ApiSchemaError(f"Unexpected {context} response shape: {type(result).__name__}")


def as_list(result: Any) -> list[Any]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "list", "rows", "result"):
            if isinstance(result.get(key), list):
                return result[key]
        return list(result.values())
    return []


def split_code(value: Any) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = str(value).split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return str(value), None


def percent(value: Any) -> Any:
    """Divide backend's "百倍" percentage fields by 100; pass non-numeric through."""
    try:
        return None if value is None else float(value) / 100
    except (TypeError, ValueError):
        return value


def normalize_kline_rows(result: Any, freq: str, adj: str) -> list[dict[str, Any]]:
    output = []
    for row in reversed(as_list(result)):
        if not isinstance(row, dict):
            continue
        stock_code, market_code = split_code(row.get("code"))
        output.append(
            {
                "stockId": row.get("code"),
                "stockCode": stock_code,
                "marketCode": market_code,
                "stockName": row.get("codeName"),
                "freq": freq,
                "adj": adj,
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "preClose": row.get("preClose"),
                "pctChange": row.get("pctChange"),
                "pctChangeRate": percent(row.get("pctChangeRate")),
                "turnoverRate": percent(row.get("turnoverRatio")),
                "vol": row.get("vol"),
                "amt": row.get("amt"),
                "tradeDate": row.get("tradeDate"),
                "tradeTime": row.get("tradeTime", "000000"),
                "isLimitUp": row.get("isLimitUp"),
                "stockCodeType": row.get("stockCodeType"),
                "ma5": row.get("ma5"),
                "ma10": row.get("ma10"),
                "ma20": row.get("ma20"),
                "ma30": row.get("ma30"),
                "ma60": row.get("ma60"),
            }
        )
    return output


def normalize_minute_line_rows(result: Any, market_code: str | None = None) -> list[dict[str, Any]]:
    output = []
    all_amt = 0
    all_vol = 0
    for row in as_list(result):
        if not isinstance(row, dict):
            continue
        stock_code, row_market = split_code(row.get("code"))
        all_amt += row.get("amt") or 0
        all_vol += row.get("vol") or 0
        resolved_market = market_code or row_market
        stock_id = f"{stock_code}.{resolved_market}" if stock_code and resolved_market else row.get("code")
        output.append(
            {
                "stockId": stock_id,
                "stockCode": stock_code,
                "marketCode": resolved_market,
                "stockName": row.get("codeName"),
                "freq": "1min",
                "trade": row.get("trade"),
                "preClose": row.get("trade") - row.get("pctChange") if row.get("trade") is not None and row.get("pctChange") is not None else None,
                "pctChange": row.get("pctChange"),
                "pctChangeRate": percent(row.get("pctChangeRate")),
                "vol": row.get("vol"),
                "amt": row.get("amt"),
                "allAmt": all_amt,
                "allVol": all_vol,
                "avePrice": all_amt / all_vol if all_vol else None,
                "tradeDate": row.get("tradeDate"),
                "tradeTime": f"{row.get('tradeTime')}00" if row.get("tradeTime") else None,
            }
        )
    return output


def technical_payload(stock_ids: Iterable[str] | str | None, indicator: str, **params: Any) -> dict[str, Any]:
    payload = {"indicators": indicator, **params}
    if stock_ids is None:
        return payload
    if isinstance(stock_ids, str):
        payload["code"] = stock_ids
    else:
        payload["code"] = ",".join(stock_ids)
    return payload


def normalize_technical_rows(result: Any, minute: bool) -> list[dict[str, Any]]:
    output = []
    for row in as_list(result):
        if not isinstance(row, dict):
            continue
        stock_code, market_code = split_code(row.get("code"))
        trade_date = row.get("tradeDate")
        trade_time = row.get("tradeTime")
        output.append(
            {
                **row,
                "stockId": row.get("code"),
                "stockCode": stock_code,
                "marketCode": market_code,
                "stockName": row.get("codeName"),
                "tradeDate": trade_date,
                "tradeTime": f"{trade_time}00" if minute and trade_time else ("000000" if not minute else trade_time),
                "pctChangeRate": percent(row.get("pctChangeRate")),
                "turnoverRate": percent(row.get("turnoverRatio")),
            }
        )
    return list(reversed(output)) if output and looks_descending(output) else output


def looks_descending(rows: list[dict[str, Any]]) -> bool:
    if len(rows) < 2:
        return False
    first = str(rows[0].get("tradeDate") or "")
    second = str(rows[1].get("tradeDate") or "")
    return first > second
