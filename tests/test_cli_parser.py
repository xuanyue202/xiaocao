from __future__ import annotations

from xiaocao.cli import build_parser
from xiaocao.cli import _index_type_selector, _rank_model_selector, _sort_selector


def test_quote_realtime_parser_defaults_to_detail_api() -> None:
    args = build_parser().parse_args(["quote", "realtime", "--codes", "000001.XSHG,300750.XSHE"])

    assert args.command == "quote"
    assert args.quote_command == "realtime"
    assert args.codes == "000001.XSHG,300750.XSHE"
    assert args.raw_line is False
    assert args.handler.__name__ == "quote_realtime"


def test_quote_history_parser_exposes_kline_controls() -> None:
    args = build_parser().parse_args(
        [
            "quote",
            "history",
            "--code",
            "000001.XSHG",
            "--count",
            "60",
            "--freq",
            "D",
            "--adj",
            "qfq",
            "--code-type",
            "0",
            "--param-time",
            "2026-04-24",
        ]
    )

    assert args.command == "quote"
    assert args.quote_command == "history"
    assert args.code == "000001.XSHG"
    assert args.codes is None
    assert args.count == 60
    assert args.freq == "D"
    assert args.adj == "qfq"
    assert args.code_type == "0"
    assert args.param_time == "2026-04-24"
    assert args.handler.__name__ == "quote_history"


def test_quote_history_parser_accepts_batch_codes() -> None:
    args = build_parser().parse_args(
        [
            "quote",
            "history",
            "--codes",
            "000001.XSHG,300750.XSHE",
            "--count",
            "20",
        ]
    )

    assert args.command == "quote"
    assert args.quote_command == "history"
    assert args.code is None
    assert args.codes == "000001.XSHG,300750.XSHE"
    assert args.count == 20
    assert args.handler.__name__ == "quote_history"


def test_market_kline_keeps_compatibility_with_extended_kline_controls() -> None:
    args = build_parser().parse_args(
        [
            "market",
            "kline",
            "--code",
            "300750.XSHE",
            "--count",
            "120",
            "--freq",
            "D",
            "--adj",
            "qfq",
            "--param-time",
            "2026-04-24",
        ]
    )

    assert args.command == "market"
    assert args.market_command == "kline"
    assert args.code == "300750.XSHE"
    assert args.codes is None
    assert args.count == 120
    assert args.param_time == "2026-04-24"
    assert args.handler.__name__ == "market_kline"


def test_market_kline_parser_accepts_batch_codes() -> None:
    args = build_parser().parse_args(
        [
            "market",
            "kline",
            "--codes",
            "000001.XSHG,300750.XSHE",
            "--count",
            "20",
        ]
    )

    assert args.command == "market"
    assert args.market_command == "kline"
    assert args.code is None
    assert args.codes == "000001.XSHG,300750.XSHE"
    assert args.count == 20
    assert args.handler.__name__ == "market_kline"


def test_data_sort_parser_accepts_sort_key_and_semantic_controls() -> None:
    args = build_parser().parse_args(
        [
            "data",
            "sort",
            "--date",
            "latest",
            "--from-pool",
            "dixi",
            "--sort-key",
            "directionCjs",
            "--sort",
            "asc",
            "--target-type",
            "stock",
        ]
    )

    assert args.command == "data"
    assert args.data_command == "sort"
    assert args.sort_key == "directionCjs"
    assert args.sort == "asc"
    assert _sort_selector(args) == "directionCjs"
    assert args.handler.__name__ == "data_sort"


def test_rank_and_dynamic_parser_accept_named_parameters() -> None:
    rank_args = build_parser().parse_args(["block", "rank", "--date", "latest", "--rank-model", "full"])
    dynamic_args = build_parser().parse_args(["index", "dynamic", "--date", "latest", "--index-name", "default"])

    assert _rank_model_selector(rank_args) == 0
    assert _index_type_selector(dynamic_args) == 1


def test_catalog_parser_commands() -> None:
    args = build_parser().parse_args(["catalog", "sort-keys"])
    describe = build_parser().parse_args(["catalog", "describe", "sort_v2"])

    assert args.command == "catalog"
    assert args.catalog_command == "sort-keys"
    assert args.handler.__name__ == "catalog_sort_keys"
    assert describe.handler.__name__ == "catalog_describe"


def test_indicator_smallgrass_current_parser() -> None:
    args = build_parser().parse_args([
        "indicator", "smallgrass", "current", "--code", "300750.XSHE",
    ])
    assert args.command == "indicator"
    assert args.indicator_command == "smallgrass"
    assert args.indicator_action == "current"
    assert args.code == "300750.XSHE"
    assert args.handler.__name__ == "indicator_smallgrass_current"


def test_indicator_smallgrass_history_parser_defaults() -> None:
    args = build_parser().parse_args([
        "indicator", "smallgrass", "history",
        "--code", "300750.XSHE",
        "--freq", "D",
    ])
    assert args.indicator_action == "history"
    assert args.code == "300750.XSHE"
    assert args.freq == "D"
    assert args.count == 200
    assert args.adj is None  # filled in by handler from freq
    assert args.handler.__name__ == "indicator_smallgrass_history"


def test_indicator_query_rejects_frontend_indicator() -> None:
    import pytest
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "indicator", "query", "current", "--code", "X", "--indicator", "klinesma",
        ])


def test_indicator_query_accepts_backend_indicator() -> None:
    args = build_parser().parse_args([
        "indicator", "query", "current", "--code", "X", "--indicator", "macd",
    ])
    assert args.indicator == "macd"
    assert args.handler.__name__ == "indicator_query_current"


def test_indicator_adj_default_freq_aware() -> None:
    from xiaocao.cli import _indicator_adj_default
    assert _indicator_adj_default("1min") == "qfq"
    assert _indicator_adj_default("5min") == "qfq"
    assert _indicator_adj_default("D") == "bfq"
    assert _indicator_adj_default("W") == "bfq"


def test_catalog_extra_lookup_subcommands() -> None:
    parser = build_parser()
    freqs = parser.parse_args(["catalog", "freqs"])
    adjs = parser.parse_args(["catalog", "adjs"])
    indicators = parser.parse_args(["catalog", "indicators"])

    assert freqs.handler.__name__ == "catalog_freqs"
    assert adjs.handler.__name__ == "catalog_adjs"
    assert indicators.handler.__name__ == "catalog_indicators"


def test_cache_commands_parse() -> None:
    parser = build_parser()
    stats = parser.parse_args(["cache", "stats", "--archive"])
    maintain = parser.parse_args(["cache", "maintain", "--hot-days", "180", "--dry-run", "--vacuum"])

    assert stats.handler.__name__ == "cache_stats"
    assert stats.archive is True
    assert maintain.handler.__name__ == "cache_maintain"
    assert maintain.hot_days == 180
    assert maintain.dry_run is True
    assert maintain.vacuum is True


def test_second_batch_market_and_block_commands_parse() -> None:
    parser = build_parser()

    block_detail = parser.parse_args(["block", "detail", "--code", "980338.ZHBK", "--date", "latest"])
    block_kline = parser.parse_args(["block", "kline", "--code", "980338.ZHBK", "--count", "30"])
    env_selection = parser.parse_args(["market", "env-selection", "--date", "latest"])
    each_trade = parser.parse_args(["market", "each-trade", "--code", "300750.XSHE", "--count", "20"])
    technical = parser.parse_args(["market", "technical", "--history", "--param", "code=300750.XSHE", "--param", "freq=D"])

    assert block_detail.handler.__name__ == "block_detail"
    assert block_kline.handler.__name__ == "block_kline"
    assert env_selection.handler.__name__ == "market_env_selection"
    assert each_trade.handler.__name__ == "market_each_trade"
    assert technical.handler.__name__ == "market_technical"
    assert technical.param == ["code=300750.XSHE", "freq=D"]
