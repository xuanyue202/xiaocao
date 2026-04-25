from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Any

import pytest

from xiaocao.api import XiaocaoClient


CODE_RE = re.compile(r"^\d{6}\.(XSHG|XSHE|BJSE)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMPACT_DATE_RE = re.compile(r"^\d{8}$")


@pytest.fixture(scope="session")
def client() -> XiaocaoClient:
    return XiaocaoClient(
        base_url=os.environ.get("XIAOCAO_BASE_URL", "https://p-xcapi.kjap1.cn"),
        timeout=float(os.environ.get("XIAOCAO_TEST_TIMEOUT", "15")),
        retries=int(os.environ.get("XIAOCAO_TEST_RETRIES", "2")),
    )


@pytest.fixture(scope="session")
def recent_trade_date(client: XiaocaoClient) -> str:
    today = date.today()
    start = (today - timedelta(days=45)).isoformat()
    rows = client.get_trade_cal(start, today.isoformat())
    assert_non_empty_list(rows, "trade_cal recent 45 days")
    dates = sorted(filter(None, (_row_date(row) for row in rows)))
    assert dates, f"trade_cal returned no parseable dates. sample={sample(rows)}"
    latest = dates[-1]
    assert DATE_RE.match(latest), f"latest trade date should be YYYY-MM-DD, got {latest!r}"
    assert start <= latest <= today.isoformat(), f"latest trade date {latest} is outside {start}..{today.isoformat()}"
    return latest


@pytest.fixture(scope="session")
def pools(client: XiaocaoClient, recent_trade_date: str) -> dict[str, list[str]]:
    groups = {"jieli": 0, "jingwang": 1, "hpqb": 2, "dixi": 3}
    result = {name: client.get_code_list_v2(recent_trade_date, group) for name, group in groups.items()}
    assert result["jingwang"], "jingwang pool should normally provide a broad fallback stock universe"
    assert result["dixi"], "dixi pool should provide candidates for index/sort/strategy API coverage"
    for name, codes in result.items():
        assert isinstance(codes, list), f"{name} pool must be list, got {type(codes).__name__}"
        assert len(codes) == len(set(codes)), f"{name} pool contains duplicate stock codes"
        for code in codes[:30]:
            assert_stock_code(code, f"{name} pool")
    return result


@pytest.fixture(scope="session")
def sample_codes(pools: dict[str, list[str]]) -> list[str]:
    codes = _dedupe([*pools.get("dixi", [])[:4], *pools.get("jingwang", [])[:4], *pools.get("jieli", [])[:2]])
    assert len(codes) >= 2, f"need at least two sample stock codes. pools={ {k: len(v) for k, v in pools.items()} }"
    return codes[:8]


def assert_non_empty_list(value: Any, context: str) -> None:
    assert isinstance(value, list), f"{context}: expected list, got {type(value).__name__}. sample={sample(value)}"
    assert value, f"{context}: expected non-empty list"


def assert_dict(value: Any, context: str) -> dict[str, Any]:
    assert isinstance(value, dict), f"{context}: expected dict, got {type(value).__name__}. sample={sample(value)}"
    return value


def assert_has_any_key(row: dict[str, Any], keys: set[str], context: str) -> str:
    for key in keys:
        if key in row:
            return key
    raise AssertionError(f"{context}: expected one of keys {sorted(keys)}, got keys={sorted(row.keys())}. row={sample(row)}")


def assert_required_keys(row: dict[str, Any], keys: set[str], context: str) -> None:
    missing = keys - set(row)
    assert not missing, f"{context}: missing keys {sorted(missing)}. keys={sorted(row.keys())}. row={sample(row)}"


def assert_stock_code(value: Any, context: str) -> None:
    assert isinstance(value, str), f"{context}: code must be str, got {type(value).__name__}: {value!r}"
    assert CODE_RE.match(value), f"{context}: invalid stock code format {value!r}"


def assert_date_like(value: Any, context: str) -> None:
    text = str(value)
    assert DATE_RE.match(text) or COMPACT_DATE_RE.match(text), f"{context}: invalid date format {value!r}"


def assert_number_like(value: Any, context: str, allow_none: bool = True) -> None:
    if value is None and allow_none:
        return
    try:
        float(value)
    except (TypeError, ValueError) as exc:
        raise AssertionError(f"{context}: expected number-like value, got {value!r}") from exc


def sample(value: Any, limit: int = 500) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _row_date(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    value = row.get("calDate") or row.get("tradeDate") or row.get("date") or row.get("day")
    if value is None:
        return None
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
