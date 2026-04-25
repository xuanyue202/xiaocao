from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from xiaocao.api import XiaocaoClient, XiaocaoError
from xiaocao.api.client import RANK_MODEL_FULL
from xiaocao.config import load_settings
from xiaocao.datasource import ApiDataSource, LocalDataSource
from xiaocao.output import write_output
from xiaocao.report import build_daily_report
from xiaocao.strategy import run_strategy
from xiaocao.utils.dates import lookback_start, normal_date, today_str


GROUPS = {
    "jieli": 0,
    "lianban": 0,
    "jingwang": 1,
    "hpqb": 2,
    "qibao": 2,
    "dixi": 3,
}


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

    sub = parser.add_subparsers(dest="command")
    _calendar(sub.add_parser("calendar"))
    _data(sub.add_parser("data"))
    _index(sub.add_parser("index"))
    _block(sub.add_parser("block"))
    _quote(sub.add_parser("quote"))
    _market(sub.add_parser("market"))
    _strategy(sub.add_parser("strategy"))
    _report(sub.add_parser("report"))
    _config(sub.add_parser("config"))
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
    p.add_argument("--sort-id", type=int, default=40)
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
    p.add_argument("--index-type", type=int, default=0)
    p.set_defaults(handler=index_dynamic)


def _block(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="block_command")
    p = sub.add_parser("rank")
    p.add_argument("--date", required=True)
    p.add_argument("--model", type=int, default=1)
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=block_rank)

    p = sub.add_parser("category-rank")
    p.add_argument("--date", required=True)
    p.add_argument("--model", type=int, default=0)
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.set_defaults(handler=block_category_rank)

    p = sub.add_parser("score")
    p.add_argument("--date", required=True)
    p.set_defaults(handler=block_score)

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

    p = sub.add_parser("environment")
    p.add_argument("--date", required=True)
    p.add_argument("--codes", default="9A0001,9A0002,9A0003,9B0001,9B0002,9B0003,9C0001,9A0004,9B0004,9A0005,9B0005,9C0002")
    p.add_argument("--code-type", type=int, default=0)
    p.add_argument("--fool-mode", type=int, default=0)
    p.set_defaults(handler=market_environment)

    p = sub.add_parser("minute-line")
    p.add_argument("--code", required=True)
    p.add_argument("--freq", default="1min")
    p.add_argument("--adj", default="bfq")
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


def _strategy(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="strategy_command")
    p = sub.add_parser("run")
    p.add_argument("--date", required=True)
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int, default=40)
    p.set_defaults(handler=strategy_run)


def _report(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="report_command")
    p = sub.add_parser("daily")
    p.add_argument("--date", required=True)
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int, default=40)
    p.set_defaults(handler=report_daily)

    p = sub.add_parser("premarket")
    p.add_argument("--date", default="latest")
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int, default=40)
    p.set_defaults(handler=report_premarket)

    p = sub.add_parser("afterclose")
    p.add_argument("--date", default="latest")
    p.add_argument("--source", choices=["api", "local"], default="api")
    p.add_argument("--modes")
    p.add_argument("--sort-id", type=int, default=40)
    p.set_defaults(handler=report_afterclose)


def _config(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="config_command")
    p = sub.add_parser("show")
    p.set_defaults(handler=config_show)


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
    if args.source == "api":
        sorted_codes = source.sort_codes(date_value, codes, args.sort_id)
    else:
        sorted_codes = source.sort_codes(date_value, codes, args.sort_id)
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
    write_output(_client(args).get_xiao_cao_dynamic_index(date_value, args.index_type), _fmt(args), args.output)


def block_rank(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    write_output(source.get_industry_block_rank(date_value, args.model), _fmt(args), args.output)


def block_category_rank(args: argparse.Namespace) -> None:
    source = _source(args)
    date_value = _resolve_date(args.date, args.source, args)
    write_output(source.get_block_category_rank(date_value, args.model), _fmt(args), args.output)


def block_score(args: argparse.Namespace) -> None:
    write_output(_client(args).get_block_score(_resolve_simple_date(args.date)), _fmt(args), args.output)


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
    write_output(_client(args).minute_line(args.code, args.freq, args.adj), _fmt(args), args.output)


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


def market_minute_line(args: argparse.Namespace) -> None:
    write_output(_client(args).minute_line(args.code, args.freq, args.adj), _fmt(args), args.output)


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
        sort_id=args.sort_id,
    )
    output = args.output
    if output is None and _fmt(args) == "csv":
        output = str(Path(settings.output_dir) / f"result_{date_value}.csv")
    write_output(rows, _fmt(args), output)


def report_daily(args: argparse.Namespace) -> None:
    _report_common(args, purpose="盘前参考 / 盘后复盘", title_suffix="小草模式日报")


def report_premarket(args: argparse.Namespace) -> None:
    _report_common(
        args,
        purpose="盘前参考：用最近一个已完成交易日的数据，生成今日观察方向与候选信号",
        title_suffix="小草盘前参考",
        default_dir="reports/premarket",
    )


def report_afterclose(args: argparse.Namespace) -> None:
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
    date_value = _resolve_date(args.date, args.source, args)
    settings = load_settings(args.config)
    modes = {item.strip() for item in args.modes.split(",")} if args.modes else None
    signals = run_strategy(
        date_value,
        source,
        modes=modes,
        block_model=settings.block_model,
        category_model=settings.category_model,
        sort_id=args.sort_id,
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
            sort_id=args.sort_id,
        )
        if isinstance(source, ApiDataSource):
            performance = _signal_performance(_client(args), previous_date, date_value, previous_signals)
    fmt = args.format or "markdown"
    output = args.output
    if fmt == "json":
        extra = _report_extras(args, source, date_value, settings)
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
        **_report_extras(args, source, date_value, settings),
    )
    if output is None:
        output = str(Path(default_dir) / f"{date_value}.md")
    _write_text(report, output)


def config_show(args: argparse.Namespace) -> None:
    write_output(load_settings(args.config).__dict__, "json", args.output)


def _client(args: argparse.Namespace) -> XiaocaoClient:
    settings = load_settings(args.config)
    return XiaocaoClient(
        base_url=args.base_url or settings.base_url,
        timeout=args.timeout or settings.timeout,
        retries=args.retries if args.retries is not None else settings.retries,
    )


def _source(args: argparse.Namespace) -> Any:
    settings = load_settings(args.config)
    if args.source == "local":
        return LocalDataSource(settings.data_dir)
    return ApiDataSource(_client(args), settings.hpqb_state, settings.lpdx_state)


def _fmt(args: argparse.Namespace) -> str:
    settings = load_settings(args.config)
    return args.format or settings.output_format


def _report_extras(args: argparse.Namespace, source: Any, date_value: str, settings: Any) -> dict[str, Any]:
    if not isinstance(source, ApiDataSource):
        return {}
    client = _client(args)
    return {
        "blockScore": client.get_block_score(date_value),
        "dynamicIndex": client.get_xiao_cao_dynamic_index(date_value, 0),
        "environment": client.xiao_cao_environment_second_line_v2(date_value),
    }


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


def _normalize_global_args(argv: list[str]) -> list[str]:
    options_with_values = {"--config", "--base-url", "--timeout", "--retries", "--format", "--output"}
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
