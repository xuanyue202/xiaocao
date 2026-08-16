from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from xiaocao.api import XiaocaoClient, XiaocaoError
from xiaocao.api.catalog import (
    DYNAMIC_INDEX_TYPES,
    ENDPOINTS,
    INDICATORS_BACKEND,
    INDICATORS_FRONTEND_ONLY,
    KLINE_ADJUSTMENTS,
    KLINE_FREQS,
    RANK_MODELS,
    SORT_DIRECTIONS,
    SORT_TARGET_TYPES,
    SORT_V2_FIELDS,
    STOCK_GROUPS,
    named_rows,
    resolve_dynamic_index_type,
    resolve_rank_model,
    resolve_sort_direction,
    resolve_sort_id,
)
from xiaocao.api.client import RANK_MODEL_FULL
from xiaocao.config import load_settings
from xiaocao.datasource import ApiDataSource, LocalDataSource
from xiaocao.output import write_output
from xiaocao.report import build_daily_report
from xiaocao.backtest import run_backtest
from xiaocao.strategy import run_strategy
from xiaocao.strategy.runner import STRATEGY_PROFILES
from xiaocao.utils.dates import lookback_start, normal_date, today_str
from xiaocao.utils.trading_session import latest_completed_trade_date


GROUPS = {key: item.value for key, item in STOCK_GROUPS.items()}


def main(argv: list[str] | None = None) -> None:
    argv = _normalize_global_args(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return
    try:
        args.handler(args)
    except XiaocaoError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xiaocao")
    parser.add_argument("--config")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--retries", type=int)
    parser.add_argument("--format", choices=["table", "json", "csv", "markdown"])
    parser.add_argument("--output")
    parser.add_argument(
        "--cache",
        default="output/.cache/xiaocao.db",
        help="持久化缓存 SQLite 路径；默认 output/.cache/xiaocao.db。--no-cache 禁用",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用持久化缓存，强制每次都打 API",
    )

    sub = parser.add_subparsers(dest="command")
    _calendar(sub.add_parser("calendar"))
    _data(sub.add_parser("data"))
    _index(sub.add_parser("index"))
    _block(sub.add_parser("block"))
    _quote(sub.add_parser("quote"))
    _market(sub.add_parser("market"))
    _indicator(sub.add_parser("indicator"))
    _strategy(sub.add_parser("strategy"))
    _backtest(sub.add_parser("backtest"))
    _report(sub.add_parser("report"))
    _config(sub.add_parser("config"))
    _catalog(sub.add_parser("catalog"))
    _cache(sub.add_parser("cache"))
    return parser


def _calendar(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="calendar_command")
    p = sub.add_parser("trade-days")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.set_defaults(handler=calendar_trade_days)

    p = sub.add_parser("latest")
    p.add_argument("--date", default="today")
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=calendar_latest)

    p = sub.add_parser("next")
    p.add_argument("--date", required=True)
    p.set_defaults(handler=calendar_next)


def _data(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="data_command")
    p = sub.add_parser("pool")
    p.add_argument("--date", required=True)
    p.add_argument("--group", choices=sorted(GROUPS), required=True)
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=data_pool)

    p = sub.add_parser("sort")
    p.add_argument("--date", required=True)
    p.add_argument("--sort-id", type=int)
    p.add_argument("--sort-key")
    p.add_argument("--sort", choices=sorted(SORT_DIRECTIONS), default="desc")
    p.add_argument("--target-type", choices=sorted(SORT_TARGET_TYPES), default="stock")
    p.add_argument("--stock-file")
    p.add_argument("--from-pool", choices=sorted(GROUPS))
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=data_sort)


def _index(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="index_command")
    p = sub.add_parser("stock")
    p.add_argument("--date", required=True)
    p.add_argument("--codes")
    p.add_argument("--from-pool", choices=sorted(GROUPS))
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=index_stock)

    p = sub.add_parser("dynamic")
    p.add_argument("--date", required=True)
    p.add_argument("--index-type", type=int)
    p.add_argument("--index-name", choices=sorted(DYNAMIC_INDEX_TYPES))
    p.set_defaults(handler=index_dynamic)

    p = sub.add_parser("industry-dynamic")
    p.add_argument("--date", required=True)
    p.add_argument("--index-type", type=int)
    p.add_argument("--index-name", choices=sorted(DYNAMIC_INDEX_TYPES))
    p.set_defaults(handler=index_industry_dynamic)


def _block(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="block_command")
    p = sub.add_parser("rank")
    p.add_argument("--date", required=True)
    p.add_argument("--model", type=int)
    p.add_argument("--rank-model", choices=sorted(RANK_MODELS), default="focus")
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=block_rank)

    p = sub.add_parser("category-rank")
    p.add_argument("--date", required=True)
    p.add_argument("--model", type=int)
    p.add_argument("--rank-model", choices=sorted(RANK_MODELS), default="full")
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=block_category_rank)

    p = sub.add_parser("score")
    p.add_argument("--date", required=True)
    p.set_defaults(handler=block_score)

    p = sub.add_parser("detail")
    p.add_argument("--code", required=True)
    p.add_argument("--date", required=True)
    p.set_defaults(handler=block_detail)

    p = sub.add_parser("kline")
    p.add_argument("--code", required=True)
    p.add_argument("--count", type=int, default=120)
    p.add_argument("--freq", default="D")
    p.add_argument("--adj", default="bfq")
    p.add_argument("--code-type", default="0")
    p.add_argument("--param-time", default="")
    p.set_defaults(handler=block_kline)

    p = sub.add_parser("stocks")
    p.add_argument("--date", required=True)
    p.add_argument("--block-code", default="")
    p.add_argument("--industry-block-code", default="")
    p.add_argument("--category-code", default="")
    p.add_argument("--pattern-code", default="")
    p.set_defaults(handler=block_stocks)


def _quote(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="quote_command")
    p = sub.add_parser("realtime")
    p.add_argument("--codes", required=True)
    p.add_argument("--raw-line", action="store_true", help="返回 second_line 原始分时线；默认返回更完整的 second_line_detail_info")
    p.set_defaults(handler=quote_realtime)

    p = sub.add_parser("minute")
    p.add_argument("--code", required=True)
    p.add_argument("--freq", default="1min")
    p.add_argument("--adj", default="bfq")
    p.add_argument("--trade-date", help="历史日期 YYYY-MM-DD 或 YYYYMMDD；与 --count 一起传则返回该日全程 1min K（不传仅返回今日 live）")
    p.add_argument("--count", type=int, help="拉取分钟数；241 = 一个交易日全程 (9:30-15:00)。Backend 需要此参数才走历史路径")
    p.add_argument("--code-type", type=int, default=0)
    p.set_defaults(handler=quote_minute)

    p = sub.add_parser("history")
    p.add_argument("--code")
    p.add_argument("--codes")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--freq", default="D")
    p.add_argument("--adj", default="qfq")
    p.add_argument("--code-type", default="0")
    p.add_argument("--param-time", default="")
    p.set_defaults(handler=quote_history)

    p = sub.add_parser("auction")
    p.add_argument("--code", required=True)
    p.add_argument("--date", required=True)
    p.set_defaults(handler=quote_auction)


def _market(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="market_command")
    p = sub.add_parser("second-line")
    p.add_argument("--codes", required=True)
    p.set_defaults(handler=market_second_line)

    p = sub.add_parser("second-line-detail")
    p.add_argument("--codes", required=True)
    p.set_defaults(handler=market_second_line_detail)

    p = sub.add_parser("overview")
    p.set_defaults(handler=market_overview)

    p = sub.add_parser("stock-info")
    p.set_defaults(handler=market_stock_info)

    p = sub.add_parser("etf-info")
    p.add_argument("--date", help="目录交易日 YYYY-MM-DD 或 YYYYMMDD；默认今天")
    p.set_defaults(handler=market_etf_info)

    p = sub.add_parser("environment")
    p.add_argument("--date", required=True)
    p.add_argument("--codes", default="9A0001,9A0002,9A0003,9B0001,9B0002,9B0003,9C0001,9A0004,9B0004,9A0005,9B0005,9C0002")
    p.add_argument("--code-type", type=int, default=0)
    p.add_argument("--fool-mode", type=int, default=0)
    p.set_defaults(handler=market_environment)

    p = sub.add_parser("env-selection")
    p.add_argument("--date", required=True)
    p.set_defaults(handler=market_env_selection)

    p = sub.add_parser("env-minute")
    p.add_argument("--code", required=True)
    p.add_argument("--date")
    p.add_argument("--freq", default="1min")
    p.add_argument("--adj", default="bfq")
    p.set_defaults(handler=market_env_minute)

    p = sub.add_parser("week-stats")
    p.set_defaults(handler=market_week_stats)

    p = sub.add_parser("each-trade")
    p.add_argument("--code", required=True)
    p.add_argument("--count", type=int)
    p.add_argument("--code-type", type=int, default=0)
    p.add_argument("--is-less", type=int, default=0)
    p.set_defaults(handler=market_each_trade)

    p = sub.add_parser("technical")
    p.add_argument("--history", action="store_true")
    p.add_argument("--param", action="append", default=[], help="原样透传 key=value，可重复")
    p.set_defaults(handler=market_technical)


    p = sub.add_parser("minute-line")
    p.add_argument("--code", required=True)
    p.add_argument("--freq", default="1min")
    p.add_argument("--adj", default="bfq")
    p.add_argument("--trade-date", help="历史日期；与 --count 一起传则返回该日全程 1min K")
    p.add_argument("--count", type=int, help="分钟数；241 = 一个交易日全程")
    p.add_argument("--code-type", type=int, default=0)
    p.set_defaults(handler=market_minute_line)

    p = sub.add_parser("kline")
    p.add_argument("--code")
    p.add_argument("--codes")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--freq", default="D")
    p.add_argument("--adj", default="qfq")
    p.add_argument("--code-type", default="0")
    p.add_argument("--param-time", default="")
    p.set_defaults(handler=market_kline)

    p = sub.add_parser("auction")
    p.add_argument("--code", required=True)
    p.add_argument("--date", required=True)
    p.set_defaults(handler=market_auction)


def _indicator(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="indicator_command")

    sg = sub.add_parser("smallgrass", help="小草核心技术指标 (smallGrass) preset")
    sg_sub = sg.add_subparsers(dest="indicator_action")

    p = sg_sub.add_parser("current")
    p.add_argument("--code")
    p.add_argument("--codes")
    p.set_defaults(handler=indicator_smallgrass_current)

    p = sg_sub.add_parser("history")
    p.add_argument("--code", required=True)
    p.add_argument("--freq", choices=sorted(KLINE_FREQS), default="D")
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--adj", choices=sorted(KLINE_ADJUSTMENTS))
    p.add_argument("--trade-date")
    p.set_defaults(handler=indicator_smallgrass_history)

    q = sub.add_parser("query", help="按 backend 接受的 indicators 值查询")
    q_sub = q.add_subparsers(dest="indicator_action")

    p = q_sub.add_parser("current")
    p.add_argument("--indicator", required=True, choices=sorted(INDICATORS_BACKEND))
    p.add_argument("--code")
    p.add_argument("--codes")
    p.set_defaults(handler=indicator_query_current)

    p = q_sub.add_parser("history")
    p.add_argument("--indicator", required=True, choices=sorted(INDICATORS_BACKEND))
    p.add_argument("--code", required=True)
    p.add_argument("--freq", choices=sorted(KLINE_FREQS), default="D")
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--adj", choices=sorted(KLINE_ADJUSTMENTS))
    p.add_argument("--trade-date")
    p.set_defaults(handler=indicator_query_history)


def _strategy(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="strategy_command")
    p = sub.add_parser("run")
    p.add_argument("--date", required=True)
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int)
    p.add_argument("--sort-key")
    p.add_argument("--direction-sort-key", default="directionCjs")
    p.add_argument("--pool-sort-key")
    p.add_argument("--max-per-direction", type=int)
    p.add_argument("--profile", choices=sorted(STRATEGY_PROFILES))
    p.add_argument("--exclude-modes", help="逗号分隔的模式名，跳过这些模式的信号")
    p.add_argument(
        "--explain",
        action="store_true",
        help="输出每个信号的可解释报告（state 5轴、profile 偏好、per-axis align、辅助权限、scores、flags），markdown 格式",
    )
    p.set_defaults(handler=strategy_run)


def _backtest(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="backtest_command")
    p = sub.add_parser("run")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    # Global --output (defined on the top-level parser) supplies the output directory.
    # Default: output/xiaocao_backtest_<start>_<end>.
    p.add_argument("--modes", help="逗号分隔策略模式")
    p.add_argument("--sort-id", type=int)
    p.add_argument("--sort-key")
    p.add_argument("--direction-sort-key", default="directionCjs")
    p.add_argument("--pool-sort-key")
    p.add_argument("--max-per-direction", type=int)
    p.add_argument("--profile", choices=sorted(STRATEGY_PROFILES))
    p.add_argument("--exclude-modes", help="逗号分隔的模式名，跳过这些模式的信号")
    p.add_argument("--kline-count", type=int, default=30, help="每只票拉的日 K 数量")
    p.add_argument("--quiet", action="store_true", help="抑制每日进度输出")
    p.add_argument("--workers", type=int, default=1, help="并行处理的天数数量；>1 时跨天并发")
    p.add_argument("--no-enrich", action="store_true", help="禁用 regime/main-line/big-cap 标注")
    p.add_argument("--mainline-window", type=int, default=3)
    p.add_argument("--mainline-topk", type=int, default=5)
    p.add_argument("--mainline-min-hits", type=int, help="主线判定的最少命中天数；默认=window（最严）")
    p.add_argument("--bigcap-top-pct", type=float, default=0.2)
    p.add_argument("--regime-gate", action="store_true", help="按 regime 过滤模式")
    p.add_argument("--require-main-line", action="store_true", help="只保留主线方向内的信号")
    p.add_argument("--exclude-main-line", action="store_true", help="只保留主线方向之外的信号")
    p.add_argument("--max-open-pct", type=float, help="覆盖默认 6.0 的开幅过滤上限")
    p.add_argument(
        "--adaptive-modes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="按 mode_history 滚动表现自适应启停模式；--no-adaptive-modes 禁用",
    )
    p.add_argument(
        "--reset-mode-history",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="adaptive 运行前清空当前窗口的 mode_history。设为 False 可让多次 run 累积，适合 strict-dormant 验证",
    )
    p.add_argument(
        "--warmup-start",
        help="预热起始日期（YYYY-MM-DD）；该日期到 --start 之间的交易作为种子写入 mode_history，不计入 summary",
    )
    # Plan B — multi-day persistence scoring (profile may set defaults)
    p.add_argument(
        "--hold-days",
        type=int,
        default=None,
        help="持仓 N 个交易日后退出。未指定时由 profile 决定（v5 默认 5, v3 默认 1）",
    )
    p.add_argument(
        "--exit-rule",
        choices=["next_close", "hold_to_n", "max_dd", "max_favorable"],
        default=None,
        help="exit 规则。未指定时由 profile 决定（v5 默认 max_dd, v3 默认 next_close）",
    )
    p.add_argument(
        "--max-dd-pct",
        type=float,
        default=None,
        help="max_dd 回撤止损 % 阈值。未指定时由 profile 决定（v5 默认 2.0, fallback 5.0）",
    )
    # Plan D — intraday entry-timing modes
    p.add_argument(
        "--entry-rule",
        choices=["open", "confirmation_935"],
        default="open",
        help=(
            "入场规则：open=9:30 开盘价 (默认；= 9:25 集合竞价 fill at 9:30)；"
            "confirmation_935=9:35 close（要求 9:30-9:35 有回撤；冲高未回撤则跳过）。"
            "后者为可选'9:35 加仓'信号，与 9:25 集合竞价头寸独立"
        ),
    )
    p.add_argument(
        "--intraday-dd-threshold",
        type=float,
        default=1.5,
        help="confirmation_935 入场要求的回撤阈值 %（默认 1.5）",
    )
    p.set_defaults(handler=backtest_run)

    v = sub.add_parser("validate", help="跨多窗口 A/B 验证策略改动；防止单窗口过拟合")
    v.add_argument(
        "--windows",
        required=True,
        help="逗号分隔的多窗口；每个窗口写作 START:END，例：2026-03-01:2026-03-31,2026-04-01:2026-04-24",
    )
    v.add_argument(
        "--variant",
        required=True,
        help="变体附加参数，作为单字符串传入（shlex 拆分）。例：'--require-main-line --max-open-pct 4'",
    )
    v.add_argument(
        "--metric",
        choices=["avg", "median", "win_rate"],
        default="avg",
        help="判定 PASS 的主指标；默认 avg",
    )
    # Global --output (defined on the top parser) supplies the validation
    # output directory.  Default: output/validation_<timestamp>.
    v.add_argument("--workers", type=int, default=4)
    v.set_defaults(handler=backtest_validate)


def _report(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="report_command")
    p = sub.add_parser("daily")
    p.add_argument("--date", required=True)
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int)
    p.add_argument("--sort-key")
    p.add_argument("--top-blocks", type=int, default=5)
    p.add_argument("--no-extras", action="store_true", help="跳过 market_overview / 方向详情 / 技术指标拉取")
    p.set_defaults(handler=report_daily)

    p = sub.add_parser("premarket")
    p.add_argument("--date", default="latest")
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int)
    p.add_argument("--sort-key")
    p.add_argument("--top-blocks", type=int, default=5)
    p.add_argument("--no-extras", action="store_true", help="跳过 market_overview / 方向详情 / 技术指标拉取")
    p.set_defaults(handler=report_premarket)

    p = sub.add_parser("afterclose")
    p.add_argument("--date", default="latest")
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int)
    p.add_argument("--sort-key")
    p.add_argument("--top-blocks", type=int, default=5)
    p.add_argument("--no-extras", action="store_true", help="跳过 market_overview / 方向详情 / 技术指标拉取")
    p.set_defaults(handler=report_afterclose)


def _config(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="config_command")
    p = sub.add_parser("show")
    p.set_defaults(handler=config_show)


def _catalog(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="catalog_command")

    p = sub.add_parser("list")
    p.set_defaults(handler=catalog_list)

    p = sub.add_parser("describe")
    p.add_argument("name")
    p.set_defaults(handler=catalog_describe)

    p = sub.add_parser("sort-keys")
    p.set_defaults(handler=catalog_sort_keys)

    p = sub.add_parser("groups")
    p.set_defaults(handler=catalog_groups)

    p = sub.add_parser("rank-models")
    p.set_defaults(handler=catalog_rank_models)

    p = sub.add_parser("index-types")
    p.set_defaults(handler=catalog_index_types)

    p = sub.add_parser("freqs")
    p.set_defaults(handler=catalog_freqs)

    p = sub.add_parser("adjs")
    p.set_defaults(handler=catalog_adjs)

    p = sub.add_parser("indicators")
    p.set_defaults(handler=catalog_indicators)


def _cache(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="cache_command")

    p = sub.add_parser("stats", help="查看 SQLite cache 当前体量")
    p.add_argument("--archive", action="store_true", help="查看 archive DB，而不是 hot DB")
    p.set_defaults(handler=cache_stats)

    p = sub.add_parser("maintain", help="归档大明细历史缓存，并清理不再持久化的 realtime 行")
    p.add_argument("--hot-days", type=int, default=365, help="大明细历史缓存 hot DB 保留天数，默认 365")
    p.add_argument("--archive-path", help="archive DB 路径；默认与 --cache 同目录，形如 xiaocao.archive.db")
    p.add_argument("--dry-run", action="store_true", help="只统计将要处理的行数，不写入")
    p.add_argument("--vacuum", action="store_true", help="维护后执行 VACUUM 收缩 hot DB 文件")
    p.set_defaults(handler=cache_maintain)


def calendar_trade_days(args: argparse.Namespace) -> None:
    client = _client(args)
    write_output(client.get_trade_cal(args.start, args.end), _fmt(args), args.output)


def calendar_latest(args: argparse.Namespace) -> None:
    settings = load_settings(args.config)
    target = _resolve_simple_date(args.date)
    if args.source == "local":
        latest = LocalDataSource(settings.data_dir).latest_date(target)
    else:
        client = _client(args)
        rows = client.get_trade_cal(lookback_start(target), target, settings.exchange, 1)
        latest = _latest_from_calendar(rows)
    write_output({"latest": latest}, _fmt(args), args.output)


def calendar_next(args: argparse.Namespace) -> None:
    client = _client(args)
    target = normal_date(args.date)
    rows = client.next_trade_cal(target, target)
    write_output(rows, _fmt(args), args.output)


def data_pool(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    rows = [{"code": code} for code in source.get_pool(date_value, args.group)]
    write_output(rows, _fmt(args), args.output)


def data_sort(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    if args.from_pool:
        codes = source.get_pool(date_value, args.from_pool)
    elif args.stock_file:
        codes = json.loads(Path(args.stock_file).read_text(encoding="utf-8"))
    else:
        codes = source.get_pool(date_value, "jingwang")
    sorted_codes = source.sort_codes(
        date_value,
        codes,
        _sort_selector(args),
        descending=resolve_sort_direction(args.sort) == 1,
        target_type=args.target_type,
    )
    write_output([{"code": code} for code in sorted_codes], _fmt(args), args.output)


def index_stock(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    if args.from_pool:
        codes = source.get_pool(date_value, args.from_pool)
    elif args.codes:
        codes = [item.strip() for item in args.codes.split(",") if item.strip()]
    else:
        raise SystemExit("ERROR: provide --codes or --from-pool")
    write_output(source.get_stock_index(date_value, codes), _fmt(args), args.output)


def index_dynamic(args: argparse.Namespace) -> None:
    date_value = _resolve_simple_date(args.date) if args.date not in {"latest", "previous"} else _resolve_date(args.date, "api", args)
    write_output(_client(args).get_xiao_cao_dynamic_index(date_value, _index_type_selector(args)), _fmt(args), args.output)


def index_industry_dynamic(args: argparse.Namespace) -> None:
    date_value = _resolve_simple_date(args.date) if args.date not in {"latest", "previous"} else _resolve_date(args.date, "api", args)
    write_output(_client(args).get_xiao_cao_industry_block_dynamic_index(date_value, _index_type_selector(args)), _fmt(args), args.output)


def block_rank(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    write_output(source.get_industry_block_rank(date_value, _rank_model_selector(args)), _fmt(args), args.output)


def block_category_rank(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    write_output(source.get_block_category_rank(date_value, _rank_model_selector(args)), _fmt(args), args.output)


def block_score(args: argparse.Namespace) -> None:
    date_value = _resolve_date(args.date, "api", args) if args.date in {"latest", "previous"} else _resolve_simple_date(args.date)
    write_output(_client(args).get_block_score(date_value), _fmt(args), args.output)


def block_detail(args: argparse.Namespace) -> None:
    date_value = _resolve_date(args.date, "api", args) if args.date in {"latest", "previous"} else _resolve_simple_date(args.date)
    write_output(_client(args).xiao_cao_block_detail(args.code, date_value), _fmt(args), args.output)


def block_kline(args: argparse.Namespace) -> None:
    write_output(
        _client(args).xiao_cao_block_date_kline(
            args.code,
            count=args.count,
            freq=args.freq,
            adj=args.adj,
            code_type=args.code_type,
            param_time=args.param_time,
        ),
        _fmt(args),
        args.output,
    )


def block_stocks(args: argparse.Namespace) -> None:
    result = _client(args).get_code_by_xiao_cao_block(
        _resolve_simple_date(args.date),
        blockCodeList=args.block_code,
        industryBlockCodeList=args.industry_block_code,
        categoryCodeList=args.category_code,
        patternCodeList=args.pattern_code,
    )
    write_output(result, _fmt(args), args.output)


def quote_realtime(args: argparse.Namespace) -> None:
    client = _client(args)
    if args.raw_line:
        result = client.second_line(args.codes)
    else:
        result = client.second_line_detail_info(args.codes)
    write_output(result, _fmt(args), args.output)


def quote_minute(args: argparse.Namespace) -> None:
    write_output(
        _client(args).minute_line(
            args.code, args.freq, args.adj,
            trade_date=getattr(args, "trade_date", None),
            count=getattr(args, "count", None),
            code_type=getattr(args, "code_type", 0),
        ),
        _fmt(args), args.output,
    )


def quote_history(args: argparse.Namespace) -> None:
    client = _client(args)
    codes = _parse_codes(args)
    if len(codes) == 1:
        result = client.date_kline(
            codes[0],
            count=args.count,
            freq=args.freq,
            adj=args.adj,
            code_type=args.code_type,
            param_time=args.param_time,
        )
    else:
        result = _flatten_kline_map(
            client.date_kline_many(
                codes,
                count=args.count,
                freq=args.freq,
                adj=args.adj,
                code_type=args.code_type,
                param_time=args.param_time,
            )
        )
    write_output(result, _fmt(args), args.output)


def quote_auction(args: argparse.Namespace) -> None:
    date_value = _resolve_date(args.date, "api", args) if args.date in {"latest", "previous"} else _resolve_simple_date(args.date)
    write_output(_client(args).stock_call_auction(args.code, date_value), _fmt(args), args.output)


def market_second_line(args: argparse.Namespace) -> None:
    write_output(_client(args).second_line(args.codes), _fmt(args), args.output)


def market_second_line_detail(args: argparse.Namespace) -> None:
    write_output(_client(args).second_line_detail_info(args.codes), _fmt(args), args.output)


def market_overview(args: argparse.Namespace) -> None:
    write_output(_client(args).market_overview(), _fmt(args), args.output)


def market_stock_info(args: argparse.Namespace) -> None:
    write_output(_client(args).stock_info(), _fmt(args), args.output)


def market_etf_info(args: argparse.Namespace) -> None:
    date_value = _resolve_simple_date(args.date) if args.date else None
    write_output(_client(args).etf_info(date_value), _fmt(args), args.output)


def market_environment(args: argparse.Namespace) -> None:
    date_value = _resolve_date(args.date, "api", args) if args.date in {"latest", "previous"} else _resolve_simple_date(args.date)
    write_output(
        _client(args).xiao_cao_environment_second_line_v2(
            date_value,
            code=args.codes,
            code_type=args.code_type,
            is_fool_mode=args.fool_mode,
        ),
        _fmt(args),
        args.output,
    )


def market_env_selection(args: argparse.Namespace) -> None:
    date_value = _resolve_date(args.date, "api", args) if args.date in {"latest", "previous"} else _resolve_simple_date(args.date)
    write_output(_client(args).xiao_cao_environment_second_line_selection(date_value), _fmt(args), args.output)


def market_env_minute(args: argparse.Namespace) -> None:
    date_value = None
    if args.date:
        date_value = _resolve_date(args.date, "api", args) if args.date in {"latest", "previous"} else _resolve_simple_date(args.date)
    write_output(_client(args).xiao_cao_environment_minute_line(args.code, date_value, args.adj, args.freq), _fmt(args), args.output)


def market_week_stats(args: argparse.Namespace) -> None:
    write_output(_client(args).xiao_cao_week_stats(), _fmt(args), args.output)


def market_each_trade(args: argparse.Namespace) -> None:
    write_output(
        _client(args).each_trade(args.code, count=args.count, code_type=args.code_type, is_less=args.is_less),
        _fmt(args),
        args.output,
    )


def _indicator_codes(args: argparse.Namespace) -> str:
    code = getattr(args, "code", None)
    codes = getattr(args, "codes", None)
    if code and codes:
        raise SystemExit("ERROR: pass --code or --codes, not both")
    if code:
        return code
    if codes:
        return codes
    raise SystemExit("ERROR: --code or --codes is required")


def _indicator_adj_default(freq: str) -> str:
    # JS K0 (~13220): minute frequencies default to qfq, others to bfq.
    return "qfq" if "min" in freq else "bfq"


def _indicator_current(args: argparse.Namespace, indicator: str) -> None:
    codes = _indicator_codes(args)
    result = _client(args).get_technical_index(stock_ids=codes, indicator=indicator)
    write_output(result, _fmt(args), args.output)


def _indicator_history(args: argparse.Namespace, indicator: str) -> None:
    freq = args.freq
    adj = args.adj or _indicator_adj_default(freq)
    result = _client(args).get_technical_index_history(
        stock_id=args.code,
        freq=freq,
        indicator=indicator,
        count=args.count,
        adj=adj,
        trade_date=getattr(args, "trade_date", None),
    )
    write_output(result, _fmt(args), args.output)


def indicator_smallgrass_current(args: argparse.Namespace) -> None:
    _indicator_current(args, "smallGrass")


def indicator_smallgrass_history(args: argparse.Namespace) -> None:
    _indicator_history(args, "smallGrass")


def indicator_query_current(args: argparse.Namespace) -> None:
    _indicator_current(args, args.indicator)


def indicator_query_history(args: argparse.Namespace) -> None:
    _indicator_history(args, args.indicator)


def market_technical(args: argparse.Namespace) -> None:
    params = _parse_key_values(args.param)
    client = _client(args)
    if args.history:
        result = client.get_technical_index_history(
            stock_id=params.pop("code", params.pop("stockId", None)),
            freq=str(params.pop("freq", "D")),
            indicator=str(params.pop("indicators", params.pop("indicator", "smallGrass"))),
            count=int(params.pop("count", 200)),
            adj=str(params.pop("adj", "qfq")),
            trade_date=params.pop("tradeDate", None),
            **params,
        )
    else:
        stock_ids = params.pop("code", params.pop("stockIds", params.pop("stockId", None)))
        result = client.get_technical_index(
            stock_ids=stock_ids,
            indicator=str(params.pop("indicators", params.pop("indicator", "smallGrass"))),
            **params,
        )
    write_output(result, _fmt(args), args.output)


def market_minute_line(args: argparse.Namespace) -> None:
    write_output(
        _client(args).minute_line(
            args.code, args.freq, args.adj,
            trade_date=getattr(args, "trade_date", None),
            count=getattr(args, "count", None),
            code_type=getattr(args, "code_type", 0),
        ),
        _fmt(args), args.output,
    )


def market_kline(args: argparse.Namespace) -> None:
    client = _client(args)
    codes = _parse_codes(args)
    if len(codes) == 1:
        result = client.date_kline(
            codes[0],
            args.count,
            args.freq,
            args.adj,
            code_type=args.code_type,
            param_time=args.param_time,
        )
    else:
        result = _flatten_kline_map(
            client.date_kline_many(
                codes,
                args.count,
                args.freq,
                args.adj,
                code_type=args.code_type,
                param_time=args.param_time,
            )
        )
    write_output(result, _fmt(args), args.output)


def market_auction(args: argparse.Namespace) -> None:
    date_value = _resolve_date(args.date, "api", args) if args.date in {"latest", "previous"} else _resolve_simple_date(args.date)
    write_output(_client(args).stock_call_auction(args.code, date_value), _fmt(args), args.output)


def strategy_run(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    settings = load_settings(args.config)
    modes = {item.strip() for item in args.modes.split(",")} if args.modes else None
    rows = run_strategy(
        date_value,
        source,
        modes=modes,
        block_model=settings.block_model,
        category_model=settings.category_model,
        sort_id=_sort_selector(args),
        direction_sort_key=getattr(args, "direction_sort_key", "directionCjs"),
        pool_sort_key=getattr(args, "pool_sort_key", None),
        max_per_direction=getattr(args, "max_per_direction", None),
        exclude_modes=_parse_exclude_modes(getattr(args, "exclude_modes", None)),
        profile=getattr(args, "profile", None),
    )
    if getattr(args, "explain", False):
        from xiaocao.strategy.explain import explain_rows
        from xiaocao.strategy.runner import _state_for_date
        client = getattr(source, "client", None)
        cache = getattr(client, "cache", None) if client is not None else None
        state = _state_for_date(date_value, cache)
        text = explain_rows(rows, state, date=date_value)
        out_path = args.output
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
        else:
            print(text)
        return
    output = args.output
    if output is None and _fmt(args) == "csv":
        output = str(Path(settings.output_dir) / f"result_{date_value}.csv")
    write_output(rows, _fmt(args), output)


def _resolve_scoring_arg(args: argparse.Namespace, name: str, fallback: Any) -> Any:
    """Pick scoring arg with priority: explicit CLI > profile preset > fallback.

    argparse defaults are None for these scoring args (hold_days, exit_rule,
    max_dd_pct) so we can distinguish "user didn't set" from "user set
    default value". STRATEGY_PROFILES["validated_v5"] etc. may carry scoring
    keys that take effect when the user picks that profile without overriding.
    """
    explicit = getattr(args, name, None)
    if explicit is not None:
        return explicit
    profile_name = getattr(args, "profile", None)
    if profile_name and profile_name in STRATEGY_PROFILES:
        preset = STRATEGY_PROFILES[profile_name]
        if name in preset:
            return preset[name]
    return fallback


def backtest_run(args: argparse.Namespace) -> None:
    settings = load_settings(args.config)
    client = _client(args)
    source = ApiDataSource(client, settings.hpqb_state, settings.lpdx_state)
    modes = {item.strip() for item in args.modes.split(",")} if args.modes else None
    output_dir = Path(args.output or f"output/xiaocao_backtest_{args.start}_{args.end}")

    progress = None
    if not args.quiet:
        def progress(date: str, n: int) -> None:
            print(f"  [{date}] {n} signals")

    summary = run_backtest(
        client,
        source,
        start=args.start,
        end=args.end,
        output_dir=output_dir,
        kline_count=args.kline_count,
        progress=progress,
        workers=getattr(args, "workers", 1),
        enrich=not getattr(args, "no_enrich", False),
        mainline_window=getattr(args, "mainline_window", 3),
        mainline_topk=getattr(args, "mainline_topk", 5),
        mainline_min_hits=getattr(args, "mainline_min_hits", None),
        bigcap_top_pct=getattr(args, "bigcap_top_pct", 0.2),
        modes=modes,
        block_model=settings.block_model,
        category_model=settings.category_model,
        sort_id=_sort_selector(args),
        direction_sort_key=getattr(args, "direction_sort_key", "directionCjs"),
        pool_sort_key=getattr(args, "pool_sort_key", None),
        max_per_direction=getattr(args, "max_per_direction", None),
        exclude_modes=_parse_exclude_modes(getattr(args, "exclude_modes", None)),
        profile=getattr(args, "profile", None),
        regime_gate=getattr(args, "regime_gate", False),
        require_main_line=getattr(args, "require_main_line", False),
        exclude_main_line=getattr(args, "exclude_main_line", False),
        max_open_pct=getattr(args, "max_open_pct", None),
        adaptive_modes=getattr(args, "adaptive_modes", False),
        reset_mode_history=getattr(args, "reset_mode_history", True),
        warmup_start=getattr(args, "warmup_start", None),
        hold_days=_resolve_scoring_arg(args, "hold_days", 1),
        exit_rule=_resolve_scoring_arg(args, "exit_rule", "next_close"),
        max_dd_pct=_resolve_scoring_arg(args, "max_dd_pct", 5.0),
        entry_rule=getattr(args, "entry_rule", "open"),
        intraday_dd_threshold=getattr(args, "intraday_dd_threshold", 1.5),
    )
    sig = summary.get("overall_signal_level", {})
    sd = summary.get("overall_stock_day_level", {})
    active = summary.get("active_signal_level", {})
    shadow = summary.get("shadow_signal_level", {})
    print(f"  signal-level:    n={sig.get('count', 0)} avg={sig.get('avg', 0):+.2f}% win={sig.get('win_rate', 0):.1f}% median={sig.get('median', 0):+.2f}%")
    print(f"  stock-day level: n={sd.get('count', 0)} avg={sd.get('avg', 0):+.2f}% win={sd.get('win_rate', 0):.1f}% median={sd.get('median', 0):+.2f}%")
    if active.get("count"):
        print(f"  ▸ active (real P&L): n={active.get('count', 0)} avg={active.get('avg', 0):+.2f}% win={active.get('win_rate', 0):.1f}%")
    if shadow.get("count"):
        print(f"  ▸ shadow (reference): n={shadow.get('count', 0)} avg={shadow.get('avg', 0):+.2f}% win={shadow.get('win_rate', 0):.1f}%")
    print(f"  artifacts -> {output_dir}/")


def backtest_validate(args: argparse.Namespace) -> None:
    """Run baseline + variant on each window; PASS only if BOTH windows improve."""
    import shlex
    from datetime import datetime as _dt

    windows = []
    for w in args.windows.split(","):
        w = w.strip()
        if ":" not in w:
            raise SystemExit(f"ERROR: window {w!r} must be START:END")
        s, e = w.split(":", 1)
        windows.append((s.strip(), e.strip()))
    if len(windows) < 2:
        raise SystemExit("ERROR: --windows must list at least 2 windows for cross-window validation")

    variant_argv = shlex.split(args.variant)

    out_root = Path(args.output or f"output/validation_{_dt.now():%Y%m%d_%H%M%S}")
    out_root.mkdir(parents=True, exist_ok=True)

    metric = args.metric
    workers = str(args.workers)
    cache_path = getattr(args, "cache", None)

    def _run_one(label: str, start: str, end: str, extra_argv: list[str]) -> dict:
        out_dir = out_root / f"{label}_{start}_{end}"
        argv = []
        if cache_path:
            argv.extend(["--cache", cache_path])
        argv.extend([
            "backtest", "run",
            "--start", start, "--end", end,
            "--workers", workers,
            "--quiet",
            "--output", str(out_dir),
        ])
        argv.extend(extra_argv)
        # Re-enter main() with constructed argv
        main(argv)
        return json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))

    def _level(summary: dict) -> dict:
        # Prefer active_signal_level (real P&L when adaptive is on); fall back
        # to overall when active is empty (e.g. --no-adaptive-modes mode).
        a = summary.get("active_signal_level") or {}
        if a.get("count"):
            return a
        return summary.get("overall_signal_level", {})

    rows = []
    for start, end in windows:
        print(f"\n=== window {start} -> {end} ===")
        base = _run_one("baseline", start, end, [])
        var = _run_one("variant", start, end, variant_argv)
        b = _level(base)
        v = _level(var)
        delta = v.get(metric, 0) - b.get(metric, 0)
        improved = delta > 0
        rows.append({
            "window": f"{start} -> {end}",
            "baseline_n": b.get("count", 0),
            "variant_n": v.get("count", 0),
            "baseline": round(b.get(metric, 0), 3),
            "variant": round(v.get(metric, 0), 3),
            "delta": round(delta, 3),
            "improved": improved,
            "baseline_win": round(b.get("win_rate", 0), 1),
            "variant_win": round(v.get("win_rate", 0), 1),
        })
        print(
            f"  baseline {metric}={b.get(metric, 0):+.2f}% win={b.get('win_rate', 0):.1f}% n={b.get('count', 0)}\n"
            f"  variant  {metric}={v.get(metric, 0):+.2f}% win={v.get('win_rate', 0):.1f}% n={v.get('count', 0)}\n"
            f"  delta    {delta:+.2f}%  improved={'YES' if improved else 'NO'}"
        )

    overall_pass = all(r["improved"] for r in rows)
    report = {
        "metric": metric,
        "variant_args": variant_argv,
        "windows": rows,
        "overall_pass": overall_pass,
        "rule": "variant must strictly improve {} on EVERY window".format(metric),
    }
    (out_root / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n>>> {'PASS' if overall_pass else 'FAIL'} on metric={metric} across {len(rows)} windows")
    print(f">>> report: {out_root / 'validation_report.json'}")
    if not overall_pass:
        raise SystemExit(1)


def _parse_exclude_modes(value: str | None) -> set[str] | None:
    if not value:
        return None
    items = {item.strip() for item in value.split(",") if item.strip()}
    return items or None


def report_daily(args: argparse.Namespace) -> None:
    _report_common(args, purpose="盘前参考 / 盘后复盘", title_suffix="小草模式日报")


def report_premarket(args: argparse.Namespace) -> None:
    args.completed_data_date = True
    _report_common(
        args,
        purpose="盘前参考：用最近一个已完成交易日的数据，生成今日观察方向与候选信号",
        title_suffix="小草盘前参考",
        default_dir="reports/premarket",
    )


def report_afterclose(args: argparse.Namespace) -> None:
    args.completed_data_date = True
    _report_common(
        args,
        purpose="盘后复盘：复盘当日环境、方向和信号，并统计上一交易日信号到当日收盘的表现",
        title_suffix="小草盘后复盘",
        default_dir="reports/afterclose",
        include_previous_performance=True,
    )


def _report_common(
    args: argparse.Namespace,
    purpose: str,
    title_suffix: str,
    default_dir: str = "reports",
    include_previous_performance: bool = False,
) -> None:
    source = _source(args)
    date_value = (
        _resolve_completed_data_date(args.date, args.source, args)
        if getattr(args, "completed_data_date", False)
        else _resolve_date(args.date, args.source, args)
    )
    settings = load_settings(args.config)
    modes = {item.strip() for item in args.modes.split(",")} if args.modes else None
    signals = run_strategy(
        date_value,
        source,
        modes=modes,
        block_model=settings.block_model,
        category_model=settings.category_model,
        sort_id=_sort_selector(args),
    )
    previous_date = _previous_trade_date(date_value, args.source, args) if include_previous_performance else None
    previous_signals = []
    performance = []
    if include_previous_performance and previous_date:
        previous_signals = run_strategy(
            previous_date,
            source,
            modes=modes,
            block_model=settings.block_model,
            category_model=settings.category_model,
            sort_id=_sort_selector(args),
        )
        if isinstance(source, ApiDataSource):
            performance = _signal_performance(_client(args), previous_date, date_value, previous_signals)
    fmt = args.format or "markdown"
    output = args.output
    if fmt == "json":
        extra = _report_extras(args, source, date_value, settings, signals)
        report_block_rank = _report_block_rank(source, date_value)
        data = {
            "date": date_value,
            "signals": signals,
            "blockRank": report_block_rank,
            "strategyBlockRank": source.get_industry_block_rank(date_value, settings.block_model),
            "categoryRank": source.get_block_category_rank(date_value, settings.category_model),
            "previousDate": previous_date,
            "previousSignals": previous_signals,
            "performance": performance,
            **extra,
        }
        write_output(data, "json", output)
        return
    if fmt in {"csv", "table"}:
        write_output(signals, fmt, output)
        return
    report = build_daily_report(
        date_value,
        signals,
        _report_block_rank(source, date_value),
        source.get_block_category_rank(date_value, settings.category_model),
        purpose=purpose,
        title=f"## {date_value} {title_suffix}",
        previous_date=previous_date,
        previousSignals=previous_signals if include_previous_performance else None,
        performance=performance if include_previous_performance else None,
        **_report_extras(args, source, date_value, settings, signals),
    )
    if output is None:
        output = str(Path(default_dir) / f"{date_value}.md")
    _write_text(report, output)


def config_show(args: argparse.Namespace) -> None:
    write_output(load_settings(args.config).__dict__, "json", args.output)


def catalog_list(args: argparse.Namespace) -> None:
    write_output([spec.as_row() for spec in ENDPOINTS.values()], _fmt(args), args.output)


def catalog_describe(args: argparse.Namespace) -> None:
    spec = ENDPOINTS.get(args.name)
    if spec is None:
        by_path = {item.path: item for item in ENDPOINTS.values()}
        spec = by_path.get(args.name)
    if spec is None:
        raise SystemExit(f"ERROR: unknown API {args.name!r}. Try: xiaocao catalog list")
    write_output(spec.as_row(), _fmt(args), args.output)


def catalog_sort_keys(args: argparse.Namespace) -> None:
    rows = [item.as_row() for item in SORT_V2_FIELDS.values()]
    rows.sort(key=lambda row: int(row["value"]))
    write_output(rows, _fmt(args), args.output)


def catalog_groups(args: argparse.Namespace) -> None:
    write_output(named_rows(STOCK_GROUPS), _fmt(args), args.output)


def catalog_rank_models(args: argparse.Namespace) -> None:
    write_output(named_rows(RANK_MODELS), _fmt(args), args.output)


def catalog_index_types(args: argparse.Namespace) -> None:
    write_output(named_rows(DYNAMIC_INDEX_TYPES), _fmt(args), args.output)


def catalog_freqs(args: argparse.Namespace) -> None:
    write_output(named_rows(KLINE_FREQS), _fmt(args), args.output)


def catalog_adjs(args: argparse.Namespace) -> None:
    write_output(named_rows(KLINE_ADJUSTMENTS), _fmt(args), args.output)


def catalog_indicators(args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for item in INDICATORS_BACKEND.values():
        row = item.as_row()
        row["scope"] = "backend"
        rows.append(row)
    for item in INDICATORS_FRONTEND_ONLY.values():
        row = item.as_row()
        row["scope"] = "frontend-only"
        rows.append(row)
    write_output(rows, _fmt(args), args.output)


def cache_stats(args: argparse.Namespace) -> None:
    from xiaocao.api.cache import SQLiteCache

    cache_path = Path(getattr(args, "cache", "output/.cache/xiaocao.db"))
    db = SQLiteCache(cache_path)
    if getattr(args, "archive", False):
        archive_path = Path(db.archive_path)
        if not archive_path.exists():
            write_output([], _fmt(args), args.output)
            return
        db = SQLiteCache(archive_path)
    write_output(db.stats(), _fmt(args), args.output)


def cache_maintain(args: argparse.Namespace) -> None:
    from xiaocao.api.cache import SQLiteCache

    cache_path = Path(getattr(args, "cache", "output/.cache/xiaocao.db"))
    db = SQLiteCache(cache_path, archive_path=getattr(args, "archive_path", None))
    result = db.maintain(
        hot_days=args.hot_days,
        archive_path=getattr(args, "archive_path", None),
        vacuum=bool(getattr(args, "vacuum", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    write_output(result, _fmt(args), args.output)


def _client(args: argparse.Namespace) -> XiaocaoClient:
    settings = load_settings(args.config)
    cache = None
    if not getattr(args, "no_cache", False):
        cache_path = getattr(args, "cache", None)
        if cache_path:
            from xiaocao.api.cache import SQLiteCache
            cache = SQLiteCache(cache_path)
    return XiaocaoClient(
        base_url=args.base_url or settings.base_url,
        timeout=args.timeout or settings.timeout,
        retries=args.retries if args.retries is not None else settings.retries,
        cache=cache,
    )


def _source(args: argparse.Namespace) -> Any:
    settings = load_settings(args.config)
    if args.source == "local":
        return LocalDataSource(settings.data_dir)
    return ApiDataSource(_client(args), settings.hpqb_state, settings.lpdx_state)


def _fmt(args: argparse.Namespace) -> str:
    settings = load_settings(args.config)
    return args.format or settings.output_format


def _sort_selector(args: argparse.Namespace) -> int | str:
    sort_key = getattr(args, "sort_key", None)
    sort_id = getattr(args, "sort_id", None)
    if sort_key:
        resolve_sort_id(sort_key)
        return sort_key
    if sort_id is not None:
        return sort_id
    return "xiaocaoCJS"


def _rank_model_selector(args: argparse.Namespace) -> int:
    model = getattr(args, "model", None)
    if model is not None:
        return model
    return resolve_rank_model(getattr(args, "rank_model", "full"))


def _index_type_selector(args: argparse.Namespace) -> int:
    index_type = getattr(args, "index_type", None)
    if index_type is not None:
        return index_type
    return resolve_dynamic_index_type(getattr(args, "index_name", None) or "jinglong")


def _report_extras(
    args: argparse.Namespace,
    source: Any,
    date_value: str,
    settings: Any,
    signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(source, ApiDataSource):
        return {}
    client = _client(args)
    extras: dict[str, Any] = {
        "blockScore": client.get_block_score(date_value),
        "dynamicIndex": client.get_xiao_cao_dynamic_index(date_value, 0),
        "environment": client.xiao_cao_environment_second_line_v2(date_value),
    }
    if getattr(args, "no_extras", False):
        return extras
    extras["marketOverview"] = _safe_call(client.market_overview)
    block_rank = source.get_industry_block_rank(date_value, RANK_MODEL_FULL)
    top_n = max(0, int(getattr(args, "top_blocks", 5)))
    extras["topBlockDetails"] = _fetch_top_block_details(client, block_rank, date_value, top_n)
    if signals:
        extras["candidateTechnical"] = _fetch_candidate_technical(client, signals)
    extras["weekStats"] = _safe_call(client.xiao_cao_week_stats)
    return extras


def _safe_call(fn: Any) -> Any:
    try:
        return fn()
    except XiaocaoError:
        return None


def _fetch_top_block_details(
    client: XiaocaoClient,
    block_rank: list[dict[str, Any]],
    date_value: str,
    top_n: int,
) -> list[dict[str, Any]]:
    if top_n <= 0 or not block_rank:
        return []
    ranked = [row for row in block_rank if isinstance(row, dict) and row.get("blockCode")]
    ranked.sort(key=lambda row: float(row.get("num") or 0), reverse=True)
    codes = [row["blockCode"] for row in ranked[:top_n]]
    out: list[dict[str, Any]] = []
    for code in codes:
        try:
            out.append(client.xiao_cao_block_detail(code, date_value))
        except XiaocaoError:
            continue
    return out


def _fetch_candidate_technical(
    client: XiaocaoClient,
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        code = sig.get("code")
        if not code or code in seen_set:
            continue
        seen.append(str(code))
        seen_set.add(str(code))
    if not seen:
        return {}
    try:
        rows = client.get_technical_index(stock_ids=seen, indicator="smallGrass")
    except XiaocaoError:
        return {}
    by_code: dict[str, Any] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = row.get("stockId") or row.get("code")
        if code:
            by_code[str(code)] = row
    return by_code


def _report_block_rank(source: Any, date_value: str) -> list[dict[str, Any]]:
    return source.get_industry_block_rank(date_value, RANK_MODEL_FULL)


def _previous_trade_date(date_value: str, source_name: str, args: argparse.Namespace) -> str | None:
    if source_name == "local":
        settings = load_settings(args.config)
        local = LocalDataSource(settings.data_dir)
        dates = sorted(path.name[:10] for path in Path(local.data_dir).glob("*_detail.csv") if path.name[:10] < date_value)
        return dates[-1] if dates else None
    rows = _client(args).get_trade_cal(lookback_start(date_value), date_value)
    dates = sorted(_calendar_date(row) for row in rows if _calendar_date(row) and _calendar_date(row) < date_value)
    return dates[-1] if dates else None


def _signal_performance(
    client: XiaocaoClient,
    previous_date: str,
    current_date: str,
    previous_signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for signal in previous_signals:
        code = signal.get("code")
        if not code:
            continue
        item = grouped.setdefault(
            str(code),
            {"代码": code, "名称": signal.get("name"), "前日模式": [], "前日竞王": signal.get("xcjw"), "前日低吸": signal.get("cjs")},
        )
        mode = signal.get("mode")
        if mode and mode not in item["前日模式"]:
            item["前日模式"].append(mode)
    try:
        kline_map = client.date_kline_many(grouped, count=20, freq="D", adj="qfq")
    except XiaocaoError:
        kline_map = {}
    output = []
    for code, row in grouped.items():
        klines = kline_map.get(code)
        if klines is None:
            try:
                klines = client.date_kline(code, count=20, freq="D", adj="qfq")
            except XiaocaoError as exc:
                row["备注"] = str(exc)
                output.append(_performance_row(row))
                continue
        by_date = {item.get("tradeDate"): item for item in klines if isinstance(item, dict)}
        prev = by_date.get(previous_date)
        current = by_date.get(current_date)
        if not prev or not current:
            row["备注"] = "缺少对应日期K线"
            output.append(_performance_row(row))
            continue
        prev_open = _to_float(prev.get("open"))
        current_close = _to_float(current.get("close"))
        if prev_open is None or current_close is None or prev_open == 0:
            row["备注"] = "价格字段不可计算"
            output.append(_performance_row(row))
            continue
        row.update(
            {
                "前日开盘": prev_open,
                "当日收盘": current_close,
                "收益率%": (current_close / prev_open - 1) * 100,
                "当日涨跌%": current.get("pctChangeRate"),
            }
        )
        output.append(_performance_row(row))
    output.sort(key=lambda item: _to_float(item.get("收益率%")) if _to_float(item.get("收益率%")) is not None else -9999, reverse=True)
    return output


def _performance_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "代码": row.get("代码"),
        "名称": row.get("名称"),
        "前日模式": ",".join(row.get("前日模式") or []),
        "前日竞王": _format_number(row.get("前日竞王")),
        "前日低吸": _format_number(row.get("前日低吸")),
        "前日开盘": _format_number(row.get("前日开盘")),
        "当日收盘": _format_number(row.get("当日收盘")),
        "收益率%": _format_number(row.get("收益率%")),
        "当日涨跌%": _format_number(row.get("当日涨跌%")),
        "备注": row.get("备注"),
    }


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: Any) -> str:
    number = _to_float(value)
    return "" if number is None else f"{number:.2f}"


def _parse_codes(args: argparse.Namespace) -> list[str]:
    raw = getattr(args, "codes", None) or getattr(args, "code", None)
    if not raw:
        raise SystemExit("ERROR: provide --code or --codes")
    codes = [item.strip() for item in str(raw).split(",") if item.strip()]
    if not codes:
        raise SystemExit("ERROR: provide --code or --codes")
    return codes


def _parse_key_values(items: list[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"ERROR: --param must be key=value, got {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise SystemExit(f"ERROR: --param key must not be empty, got {item!r}")
        output[key] = _coerce_param_value(value)
    return output


def _coerce_param_value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _flatten_kline_map(rows_by_code: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for code, rows in rows_by_code.items():
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    output.append({"code": code, **row})
                else:
                    output.append({"code": code, "value": row})
        elif isinstance(rows, dict):
            output.append({"code": code, **rows})
        else:
            output.append({"code": code, "value": rows})
    return output


def _resolve_date(value: str, source_name: str, args: argparse.Namespace | None = None) -> str:
    if value in {"today", "latest", "previous"}:
        if source_name == "local":
            settings = load_settings(args.config if args is not None else None)
            local = LocalDataSource(settings.data_dir)
            target = today_str()
            latest = local.latest_date(target)
            if value == "previous":
                dates = sorted(path.name[:10] for path in Path(local.data_dir).glob("*_detail.csv") if path.name[:10] < latest)
                return dates[-1] if dates else latest
            return target if value == "today" else latest
        if value == "today":
            return today_str()
        target = today_str()
        rows = (_client(args) if args is not None else XiaocaoClient()).get_trade_cal(lookback_start(target), target)
        latest = _latest_from_calendar(rows)
        if value == "previous":
            dates = sorted(_calendar_date(row) for row in rows if _calendar_date(row) and _calendar_date(row) < latest)
            return dates[-1] if dates else latest
        return latest
    return normal_date(value)


def _resolve_completed_data_date(value: str, source_name: str, args: argparse.Namespace | None = None) -> str:
    """Resolve a date for reports that depend on after-close aggregate endpoints."""
    if value not in {"today", "latest"}:
        return _resolve_date(value, source_name, args)
    if source_name == "local":
        return _resolve_date("latest", source_name, args)
    target = today_str()
    rows = (_client(args) if args is not None else XiaocaoClient()).get_trade_cal(lookback_start(target), target)
    dates = sorted(_calendar_date(row) for row in rows if _calendar_date(row))
    return latest_completed_trade_date(dates) if dates else target


def _normalize_global_args(argv: list[str]) -> list[str]:
    options_with_values = {"--config", "--base-url", "--timeout", "--retries", "--format", "--output", "--cache"}
    front: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in options_with_values and i + 1 < len(argv):
            front.extend([token, argv[i + 1]])
            i += 2
        elif any(token.startswith(option + "=") for option in options_with_values):
            front.append(token)
            i += 1
        else:
            rest.append(token)
            i += 1
    return front + rest


def _resolve_simple_date(value: str) -> str:
    return today_str() if value == "today" else normal_date(value)


def _write_text(text: str, output: str | None = None) -> None:
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
        sys.stdout.write("\n")


def _latest_from_calendar(rows: list[dict[str, Any]]) -> str:
    dates = sorted(filter(None, (_calendar_date(row) for row in rows)))
    if not dates:
        raise SystemExit("ERROR: no trading day returned by calendar API")
    return dates[-1]


def _calendar_date(row: dict[str, Any]) -> str | None:
    value = row.get("calDate") or row.get("tradeDate") or row.get("date") or row.get("day")
    if value is None:
        return None
    value = str(value)
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value[:10]
