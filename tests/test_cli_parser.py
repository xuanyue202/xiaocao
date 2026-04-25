from __future__ import annotations

from xiaocao.cli import build_parser


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
