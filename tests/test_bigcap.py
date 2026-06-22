from __future__ import annotations

import pytest

from xiaocao.strategy.bigcap import bigcap_codes, is_bigcap, split_by_bigcap


def _row(stock_id: str, shares: int, status: int = 1) -> dict:
    # Mirrors real XiaocaoClient.stock_info() rows: `code` + `statusType`
    # (1 = 普通股 tradable, 99 = index/non-tradable). No `type`/`stockId`.
    return {"code": stock_id, "statusType": status, "tradableAShare": shares}


def test_bigcap_picks_top_pct_by_shares():
    rows = [_row(f"S{i}", 1000 - i) for i in range(10)]
    out = bigcap_codes(rows, top_pct=0.2)
    assert out == {"S0", "S1"}  # top 2 of 10


def test_bigcap_skips_non_status_1():
    rows = [
        _row("idx", 10**12, status=99),  # index — must be skipped
        _row("susp", 10**11, status=5),  # non-tradable — must be skipped
        _row("A", 100),
        _row("B", 50),
    ]
    out = bigcap_codes(rows, top_pct=0.5)
    assert out == {"A"}  # 50% of 2 valid candidates = 1


def test_bigcap_real_cached_schema():
    # Exact shape the live API returns (see output/.cache/xiaocao.db): tradable
    # stocks are statusType==1; indices are statusType==99 with tradableAShare==0;
    # there is NO `type` field. The old `type==1` filter skipped EVERYTHING here.
    rows = [
        {"code": "000001.XSHG", "codeName": "上证指数", "statusType": 99, "tradableAShare": 0},
        {"code": "600519.XSHG", "codeName": "贵州茅台", "statusType": 1, "tradableAShare": 1_256_000_000},
        {"code": "000001.XSHE", "codeName": "平安银行", "statusType": 1, "tradableAShare": 19_405_600_653},
    ]
    out = bigcap_codes(rows, top_pct=1.0)
    assert out == {"600519.XSHG", "000001.XSHE"}  # both tradable, index dropped


def test_bigcap_legacy_type_fallback():
    # Older/fixture rows without statusType still work via the `type` fallback.
    rows = [
        {"stockId": "A", "type": 1, "tradableAShare": 100},
        {"stockId": "idx", "type": 99, "tradableAShare": 10**9},
    ]
    assert bigcap_codes(rows, top_pct=1.0) == {"A"}


def test_bigcap_handles_zero_or_missing_shares():
    rows = [
        _row("A", 100),
        _row("B", 0),
        {"code": "C", "statusType": 1, "tradableAShare": None},
        {"statusType": 1, "tradableAShare": 99999},  # no code/stockId
    ]
    assert bigcap_codes(rows, top_pct=1.0) == {"A"}


def test_bigcap_empty_input():
    assert bigcap_codes([], top_pct=0.2) == set()


def test_bigcap_min_shares_floor():
    rows = [_row(f"S{i}", 1000 - i * 100) for i in range(10)]
    # top 20% by percentile would be S0+S1 (1000, 900), but min_shares=950 → only S0
    assert bigcap_codes(rows, top_pct=0.2, min_shares=950) == {"S0"}


def test_bigcap_invalid_top_pct():
    with pytest.raises(ValueError):
        bigcap_codes([_row("A", 1)], top_pct=0)
    with pytest.raises(ValueError):
        bigcap_codes([_row("A", 1)], top_pct=1.5)


def test_is_bigcap_basic():
    s = {"A", "B"}
    assert is_bigcap("A", s)
    assert not is_bigcap("C", s)
    assert not is_bigcap(None, s)


def test_split_by_bigcap_preserves_order():
    rows = [{"code": "A"}, {"code": "B"}, {"code": "C"}, {"code": "A"}]
    big, other = split_by_bigcap(rows, {"A"}, code_field="code")
    assert [r["code"] for r in big] == ["A", "A"]
    assert [r["code"] for r in other] == ["B", "C"]
