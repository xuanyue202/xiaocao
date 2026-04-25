from __future__ import annotations

import json

import pytest

from xiaocao.api import XiaocaoClient
from xiaocao.datasource.api_source import ApiDataSource
from xiaocao.output.render import render_csv, render_markdown, render_table
from xiaocao.report import build_daily_report
from xiaocao.cli import _previous_trade_date, _signal_performance
from xiaocao.strategy import run_strategy

from tests.conftest import assert_dict, assert_non_empty_list, assert_stock_code, sample


@pytest.mark.e2e
def test_api_datasource_pipeline_contract(client: XiaocaoClient, recent_trade_date: str, pools: dict[str, list[str]]) -> None:
    source = ApiDataSource(client)

    dixi_codes = source.get_pool(recent_trade_date, "dixi")
    assert dixi_codes == pools["dixi"], "ApiDataSource.get_pool should preserve client pool semantics"

    sorted_codes = source.sort_codes(recent_trade_date, dixi_codes[:30], sort_id=8)
    assert sorted_codes, "ApiDataSource.sort_codes should return at least one code for a non-empty pool"
    assert set(sorted_codes).issubset(set(dixi_codes[:30])), (
        "ApiDataSource.sort_codes must not leak codes outside the requested stockIds. "
        f"unexpected={sorted(set(sorted_codes) - set(dixi_codes[:30]))}"
    )

    details = source.get_stock_index(recent_trade_date, sorted_codes[:5])
    assert_non_empty_list(details, "ApiDataSource.get_stock_index")
    assert len(details) == len(sorted_codes[:5]), f"expected one detail per code. rows={sample(details)}"
    for row in details:
        row = assert_dict(row, "stock detail")
        code = row.get("code") or row.get("stockCode")
        assert_stock_code(code, "stock detail code")


@pytest.mark.e2e
def test_strategy_report_and_renderers_on_live_api(client: XiaocaoClient, recent_trade_date: str) -> None:
    source = ApiDataSource(client)
    signals = run_strategy(recent_trade_date, source, modes={"direction"}, sort_id=8)
    assert isinstance(signals, list), f"run_strategy must return list, got {type(signals).__name__}"
    for signal in signals:
        assert_strategy_signal(signal)

    block_rank = source.get_industry_block_rank(recent_trade_date, model=1)
    category_rank = source.get_block_category_rank(recent_trade_date, model=0)
    report = build_daily_report(recent_trade_date, signals, block_rank, category_rank)
    assert f"## {recent_trade_date} 小草模式日报" in report
    assert "### 摘要" in report
    assert "### 强方向" in report
    assert "### 强方向大类" in report
    assert "### 模式结果" in report

    table = render_table(signals)
    markdown = render_markdown(signals)
    csv_text = render_csv(signals)
    if signals:
        assert "date" in table and "mode" in table and "code" in table
        assert "| date | mode | code |" in markdown
        assert csv_text.splitlines()[0].startswith("date,mode,code,name")
    else:
        assert table == "No data"
        assert markdown == "_No data_"
        assert csv_text == ""


@pytest.mark.e2e
def test_cli_json_shape_without_spawning_process(client: XiaocaoClient, recent_trade_date: str) -> None:
    source = ApiDataSource(client)
    signals = run_strategy(recent_trade_date, source, modes={"direction"}, sort_id=8)
    payload = {
        "date": recent_trade_date,
        "signals": signals,
        "blockRank": source.get_industry_block_rank(recent_trade_date, 1),
        "categoryRank": source.get_block_category_rank(recent_trade_date, 0),
        "blockScore": client.get_block_score(recent_trade_date),
        "dynamicIndex": client.get_xiao_cao_dynamic_index(recent_trade_date, 0),
        "environment": client.xiao_cao_environment_second_line_v2(recent_trade_date),
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["date"] == recent_trade_date
    assert isinstance(decoded["signals"], list)
    assert isinstance(decoded["blockRank"], list)
    assert isinstance(decoded["categoryRank"], list)
    assert decoded["blockScore"] is not None
    assert isinstance(decoded["dynamicIndex"], list)
    assert decoded["environment"] is not None
    if decoded["signals"]:
        assert_strategy_signal(decoded["signals"][0])


@pytest.mark.e2e
def test_afterclose_previous_signal_performance(client: XiaocaoClient, recent_trade_date: str) -> None:
    class Args:
        config = None
        base_url = None
        timeout = None
        retries = None

    previous_date = _previous_trade_date(recent_trade_date, "api", Args())
    assert previous_date is not None
    source = ApiDataSource(client)
    previous_signals = run_strategy(previous_date, source, modes={"jieli"}, sort_id=8)
    performance = _signal_performance(client, previous_date, recent_trade_date, previous_signals)
    assert isinstance(performance, list)
    if previous_signals:
        assert performance, "previous signals exist, so afterclose performance should contain at least one row"
        first = performance[0]
        assert "代码" in first and "收益率%" in first and "前日开盘" in first and "当日收盘" in first


def assert_strategy_signal(signal: dict) -> None:
    row = assert_dict(signal, "strategy signal")
    required = {
        "date",
        "mode",
        "code",
        "name",
        "xcjw",
        "cjs",
        "jsjl",
        "jssb",
        "pctChange",
        "openPctChange",
        "direction",
        "directionRank",
        "categoryRank",
        "reason",
    }
    missing = required - set(row)
    assert not missing, f"strategy signal missing fields {sorted(missing)}. row={sample(row)}"
    assert_stock_code(row["code"], "strategy signal code")
    assert isinstance(row["mode"], str) and row["mode"], f"strategy signal mode must be non-empty. row={sample(row)}"
    assert isinstance(row["reason"], str) and row["reason"], f"strategy signal reason must be non-empty. row={sample(row)}"
