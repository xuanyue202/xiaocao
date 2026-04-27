from __future__ import annotations

from typing import Any

import pytest

from xiaocao.api import XiaocaoClient
from xiaocao.datasource.api_source import ApiDataSource

from tests.conftest import (
    assert_date_like,
    assert_dict,
    assert_has_any_key,
    assert_non_empty_list,
    assert_number_like,
    assert_required_keys,
    assert_stock_code,
    sample,
)


@pytest.mark.e2e
def test_trade_calendar_contract(client: XiaocaoClient, recent_trade_date: str) -> None:
    rows = client.get_trade_cal(recent_trade_date, recent_trade_date)
    assert_non_empty_list(rows, "trade_cal exact latest day")
    row = assert_dict(rows[0], "trade_cal row")
    date_key = assert_has_any_key(row, {"calDate", "tradeDate", "date", "day"}, "trade_cal row")
    assert_date_like(row[date_key], "trade_cal date")

    next_rows = client.next_trade_cal(recent_trade_date, recent_trade_date)
    assert isinstance(next_rows, list), f"next_trade_cal must return list, got {type(next_rows).__name__}"
    if next_rows:
        next_row = assert_dict(next_rows[0], "next_trade_cal row")
        next_date_key = assert_has_any_key(next_row, {"calDate", "tradeDate", "date", "day"}, "next_trade_cal row")
        assert_date_like(next_row[next_date_key], "next_trade_cal date")


@pytest.mark.e2e
def test_stock_pool_contracts(pools: dict[str, list[str]]) -> None:
    assert set(pools) == {"jieli", "jingwang", "hpqb", "dixi"}
    for name, codes in pools.items():
        assert isinstance(codes, list), f"{name}: pool must be list"
        assert len(codes) == len(set(codes)), f"{name}: pool contains duplicate codes"
        for code in codes[:50]:
            assert_stock_code(code, f"{name} pool")
    assert len(pools["jingwang"]) >= len(pools["dixi"]), (
        "jingwang is expected to be a broad stock universe; if this fails, "
        f"group mapping may have changed. sizes={ {k: len(v) for k, v in pools.items()} }"
    )


@pytest.mark.e2e
def test_xiao_cao_index_v2_contract(client: XiaocaoClient, recent_trade_date: str, sample_codes: list[str]) -> None:
    rows = client.get_xiao_cao_index_v2(recent_trade_date, sample_codes)
    assert_non_empty_list(rows, "xiao_cao_index_v2")
    by_code = {_stock_code_from_row(row): row for row in rows if isinstance(row, dict)}
    missing_codes = set(sample_codes) - set(by_code)
    assert not missing_codes, f"xiao_cao_index_v2 missing requested codes {sorted(missing_codes)}. sample={sample(rows)}"

    for code in sample_codes:
        row = assert_dict(by_code[code], f"xiao_cao_index_v2 row {code}")
        assert_stock_code(code, f"xiao_cao_index_v2 row {code}")
        assert_has_any_key(row, {"code", "stockCode"}, f"xiao_cao_index_v2 row {code}")
        assert_has_any_key(row, {"codeName", "name", "stockName"}, f"xiao_cao_index_v2 row {code}")
        for numeric_key in ("xcjw", "cjs", "jsjl", "jssb"):
            assert numeric_key in row, f"xiao_cao_index_v2 row {code}: missing numeric field {numeric_key}. row={sample(row)}"
            assert_number_like(row[numeric_key], f"xiao_cao_index_v2 row {code}.{numeric_key}")
        for flag_key in ("isWeak", "isDownBroken", "isUpBroken", "isHalf", "isBottom"):
            assert flag_key in row, f"xiao_cao_index_v2 row {code}: missing flag field {flag_key}. row={sample(row)}"


@pytest.mark.e2e
@pytest.mark.parametrize("sort_id", [8, 40])
def test_sort_v2_contract(client: XiaocaoClient, recent_trade_date: str, pools: dict[str, list[str]], sort_id: int) -> None:
    pool_name = "jieli" if sort_id == 40 else "dixi"
    requested = pools[pool_name][:20]
    rows = client.sort_v2(requested, sort_id=sort_id, date=recent_trade_date)
    assert_non_empty_list(rows, f"sort_v2 sort_id={sort_id}")
    returned_codes = [_stock_code_from_sort_row(row) for row in rows]
    returned_codes = [code for code in returned_codes if code]
    assert returned_codes, f"sort_v2 sort_id={sort_id}: no parseable stock codes. sample={sample(rows)}"
    for code in returned_codes[:50]:
        assert_stock_code(code, f"sort_v2 sort_id={sort_id}")

    datasource_codes = ApiDataSource(client).sort_codes(recent_trade_date, requested, sort_id=sort_id)
    assert datasource_codes, f"ApiDataSource.sort_codes sort_id={sort_id} returned empty list"
    assert set(datasource_codes).issubset(set(requested)), (
        "ApiDataSource.sort_codes must filter sort_v2 responses back to requested stockIds. "
        f"unexpected={sorted(set(datasource_codes) - set(requested))}"
    )


@pytest.mark.e2e
def test_block_rank_contracts(client: XiaocaoClient, recent_trade_date: str) -> None:
    block_rows = client.get_industry_block_rank(recent_trade_date, model=1)
    assert_non_empty_list(block_rows, "xiao_cao_industry_block_rank")
    block = assert_dict(block_rows[0], "industry block row")
    assert_required_keys(block, {"blockCode", "num"}, "industry block row")
    assert str(block["blockCode"]).endswith(".ZHBK"), f"industry block code should end with .ZHBK. row={sample(block)}"
    assert_number_like(block["num"], "industry block num", allow_none=False)
    if "tradeDate" in block:
        assert_date_like(block["tradeDate"], "industry block tradeDate")

    category_rows = client.get_block_category_rank_v3(recent_trade_date, model=0)
    assert_non_empty_list(category_rows, "xiao_cao_block_category_rank_v3")
    category = assert_dict(category_rows[0], "category rank row")
    assert_required_keys(category, {"categoryCode", "num"}, "category rank row")
    assert str(category["categoryCode"]).endswith(".BKDL"), f"category code should end with .BKDL. row={sample(category)}"
    assert_number_like(category["num"], "category rank num", allow_none=False)
    if "tradeDate" in category:
        assert_date_like(category["tradeDate"], "category rank tradeDate")

    dynamic_rows = client.get_xiao_cao_dynamic_index(recent_trade_date, index_type=0)
    assert_non_empty_list(dynamic_rows, "xiao_cao_dynamic_index")
    dynamic = assert_dict(dynamic_rows[0], "dynamic index row")
    assert_has_any_key(dynamic, {"blockCode", "categoryCode", "code"}, "dynamic index row")
    assert_has_any_key(dynamic, {"score", "num", "value"}, "dynamic index row")
    if "score" in dynamic:
        assert_number_like(dynamic["score"], "dynamic index score", allow_none=False)


@pytest.mark.e2e
def test_block_score_and_direction_stock_lookup_contract(client: XiaocaoClient, recent_trade_date: str) -> None:
    score = client.get_block_score(recent_trade_date)
    assert score is not None, "xiao_cao_block_score result must not be None"
    assert isinstance(score, (list, dict)), f"xiao_cao_block_score should return list/dict, got {type(score).__name__}: {sample(score)}"
    if isinstance(score, list) and score:
        assert_dict(score[0], "block_score first row")

    block_rows = client.get_industry_block_rank(recent_trade_date, model=1)
    assert_non_empty_list(block_rows, "industry block rows for stock lookup")
    block_code = str(assert_dict(block_rows[0], "top block row")["blockCode"])
    result = client.get_code_by_xiao_cao_block(
        recent_trade_date,
        blockCodeList=block_code,
        industryBlockCodeList=block_code,
    )
    codes = ApiDataSource(client).get_direction_codes(recent_trade_date, block_code=block_code)
    assert isinstance(result, (list, dict)), f"get_code_by_xiao_cao_block must return list/dict, got {type(result).__name__}: {sample(result)}"
    assert codes, f"get_direction_codes could not extract stock codes from block {block_code}. raw={sample(result)}"
    for code in codes[:30]:
        assert_stock_code(code, f"get_code_by_xiao_cao_block {block_code}")


@pytest.mark.e2e
def test_market_data_contracts(client: XiaocaoClient, recent_trade_date: str, sample_codes: list[str]) -> None:
    index_codes = "000001.XSHG,399001.XSHE,399006.XSHE"
    second_line = client.second_line(index_codes)
    assert second_line is not None, "second_line result must not be None"
    assert isinstance(second_line, (list, dict)), f"second_line should return list/dict, got {type(second_line).__name__}: {sample(second_line)}"

    detail = client.second_line_detail_info(index_codes)
    assert detail is not None, "second_line_detail_info result must not be None"
    assert isinstance(detail, (list, dict)), f"second_line_detail_info should return list/dict, got {type(detail).__name__}: {sample(detail)}"

    environment = client.xiao_cao_environment_second_line_v2(recent_trade_date)
    assert environment is not None, "xiao_cao_environment_second_line_v2 result must not be None"
    assert isinstance(environment, (list, dict)), (
        "xiao_cao_environment_second_line_v2 should return list/dict, "
        f"got {type(environment).__name__}: {sample(environment)}"
    )

    code = sample_codes[0]
    minute = client.minute_line(code, freq="1min", adj="bfq")
    assert minute is not None, f"minute_line {code} result must not be None"
    assert isinstance(minute, (list, dict)), f"minute_line should return list/dict, got {type(minute).__name__}: {sample(minute)}"

    kline = client.date_kline(code, count=2, freq="D", adj="qfq")
    assert_non_empty_list(kline, f"date_kline {code}")
    assert len(kline) <= 2, f"date_kline count=2 should not return more than 2 rows. rows={sample(kline)}"
    assert_dict(kline[0], f"date_kline {code} first row")

    batch_kline = client.date_kline_many(sample_codes[:2], count=2, freq="D", adj="qfq")
    assert set(batch_kline) == set(sample_codes[:2]), f"date_kline_many should preserve requested codes. rows={sample(batch_kline)}"
    for batch_code, rows in batch_kline.items():
        assert_non_empty_list(rows, f"date_kline_many {batch_code}")
        assert len(rows) <= 2, f"date_kline_many count=2 should not return more than 2 rows. rows={sample(rows)}"
        assert_dict(rows[0], f"date_kline_many {batch_code} first row")

    auction = client.stock_call_auction(code, recent_trade_date)
    assert auction is not None, f"stock_call_auction {code} result must not be None"
    assert isinstance(auction, (list, dict)), f"stock_call_auction should return list/dict, got {type(auction).__name__}: {sample(auction)}"


def _stock_code_from_row(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    code = row.get("code") or row.get("stockCode") or row.get("stockId")
    return str(code) if code else None


def _stock_code_from_sort_row(row: Any) -> str | None:
    if isinstance(row, str):
        return row
    return _stock_code_from_row(row)
