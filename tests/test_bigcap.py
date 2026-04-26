from __future__ import annotations

import pytest

from xiaocao.strategy.bigcap import bigcap_codes, is_bigcap, split_by_bigcap


def _row(stock_id: str, shares: int, type_: int = 1) -> dict:
    return {"stockId": stock_id, "type": type_, "tradableAShare": shares}


def test_bigcap_picks_top_pct_by_shares():
    rows = [_row(f"S{i}", 1000 - i) for i in range(10)]
    out = bigcap_codes(rows, top_pct=0.2)
    assert out == {"S0", "S1"}  # top 2 of 10


def test_bigcap_skips_non_type_1():
    rows = [
        _row("idx", 10**12, type_=5),  # index — must be skipped
        _row("blk", 10**11, type_=99),  # block — must be skipped
        _row("A", 100),
        _row("B", 50),
    ]
    out = bigcap_codes(rows, top_pct=0.5)
    assert out == {"A"}  # 50% of 2 valid candidates = 1


def test_bigcap_handles_zero_or_missing_shares():
    rows = [
        _row("A", 100),
        _row("B", 0),
        {"stockId": "C", "type": 1, "tradableAShare": None},
        {"type": 1, "tradableAShare": 99999},  # no stockId
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
