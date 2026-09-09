from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from kronos_screen.scripts.forward_eval import (  # noqa: E402
    _is_known_executable,
    _market_return_map,
    day_mean,
    ensure_training_schema,
)


class _IndexClient:
    def __init__(self, missing: str | None = None, invalid: str | None = None):
        self.missing = missing
        self.invalid = invalid

    def date_kline(self, code, **_kwargs):
        if code == self.missing:
            return []
        if code == self.invalid:
            return [
                {"tradeDate": "2026-07-10", "open": -100.0, "close": 100.0},
                {"tradeDate": "2026-07-13", "open": 101.0, "close": 102.0},
            ]
        return [
            {"tradeDate": "2026-07-10", "open": 100.0, "close": 100.0},
            {"tradeDate": "2026-07-13", "open": 101.0, "close": 102.0},
        ]


def test_training_schema_adds_qibao_benchmark_star_from_layer() -> None:
    df = pd.DataFrame([
        {
            "date": "2026-06-30",
            "code": "A.XSHE",
            "mode": "高开标杆起爆",
            "qibaoBenchmarkLayer": "paper_buy",
            "net_realized_ret": 8.0,
        },
        {"date": "2026-06-30", "code": "B.XSHE", "mode": "绿断低吸", "net_realized_ret": 1.0},
    ])

    out = ensure_training_schema(df)

    assert "mode_confidence_source" in out.columns
    assert "book" in out.columns
    assert out["book"].fillna("B").tolist() == ["B", "B"]
    assert "rawQibaoRank" in out.columns
    assert "qibaoBenchmarkKind" in out.columns
    assert "is_main_line" in out.columns
    assert "is_big_cap" in out.columns
    assert "ai_intelligence_short_star" in out.columns
    assert "mode_exec_star" in out.columns
    assert "mode_exec_rank_score" in out.columns
    assert "mode_exec_mode_confidence" in out.columns
    assert "mode_state" in out.columns
    assert "executable_fillable" in out.columns
    assert "executable_net_ret" in out.columns
    assert "intelligence_long_star" in out.columns
    assert "regime" in out.columns
    assert "direction_rank" in out.columns
    assert bool(out.loc[out["code"] == "A.XSHE", "qibao_benchmark_star"].iloc[0]) is True
    assert bool(out.loc[out["code"] == "B.XSHE", "qibao_benchmark_star"].iloc[0]) is False


def test_unknown_executable_nan_is_not_treated_as_cached_result() -> None:
    assert not _is_known_executable({
        "executable_fillable": float("nan"),
        "executable_skip_reason": float("nan"),
    })


def test_missing_market_evidence_is_not_a_terminal_cached_label() -> None:
    assert not _is_known_executable({
        "executable_fillable": False,
        "executable_skip_reason": "LIMIT_DOWN_CHECK_UNAVAILABLE",
    })


def test_historical_fill_checks_market_facts_at_entry_clock() -> None:
    from kronos_screen.scripts.forward_eval import _historical_opening_fill
    from kronos_screen.scripts.paper_record import _fill_price_from_window

    row = {
        "date": "2026-09-08", "code": "600371.XSHG",
        "open": 15.37, "basket_price": 15.6866,
        "market_guard_required": True, "market_guard_status": "T100",
        "market_price": 15.37, "down_price": 13.56,
        "market_observed_at": "2026-09-08T09:25:00+08:00",
    }
    window = {"low": 15.37, "high": 15.50, "vwap": 15.40, "last": 15.40}
    # The normal actuator still uses wall-clock freshness, not replay time.
    expired = {**row, "date": "2020-01-02", "market_observed_at": "2020-01-02T09:25:00+08:00"}
    assert _fill_price_from_window(expired, window=window, limit_premium_pct=0.5)[0] is None
    assert _historical_opening_fill(row, window)[0] == pytest.approx(15.40)
    legacy = {**row, "captured_at": "2026-09-08T09:25:54", "market_observed_at": "09:25:00:140"}
    assert _historical_opening_fill(legacy, window)[0] == pytest.approx(15.40)
    assert _historical_opening_fill({**legacy, "captured_at": "2026-09-07T09:25:54"}, window)[0] is None
    for invalid in (
        {"down_price": None},
        {"market_guard_required": None, "down_price": None},
        {"market_guard_required": False, "market_observed_at": None},
        {"market_observed_at": "2026-09-07T09:25:00+08:00"},
        {"market_observed_at": "2026-09-08T09:00:00+08:00"},
        {"market_guard_status": "suspended"},
        {"market_price": 13.56},
    ):
        assert _historical_opening_fill({**row, **invalid}, window)[0] is None


def test_market_return_requires_all_four_index_components() -> None:
    complete = _market_return_map(_IndexClient(), ["2026-07-10"], {})
    incomplete = _market_return_map(
        _IndexClient(missing="399006.XSHE"), ["2026-07-10"], {}
    )
    invalid = _market_return_map(
        _IndexClient(invalid="399006.XSHE"), ["2026-07-10"], {}
    )

    assert complete["2026-07-10"] == pytest.approx(2.0)
    assert "2026-07-10" not in incomplete
    assert "2026-07-10" not in invalid
    assert _is_known_executable({
        "executable_fillable": False,
        "executable_skip_reason": "NO_USER_BOARD_PERMISSION",
    })


def test_training_schema_normalizes_block_metadata_for_parquet(tmp_path) -> None:
    df = pd.DataFrame([
        {
            "date": "2026-07-03",
            "code": "A.XSHE",
            "mode": "绿断低吸",
            "blockCodeList": ["BK001", "BK002"],
            "blockCategoryCodeList": ["CAT001"],
            "net_realized_ret": 1.0,
        },
        {
            "date": "2026-07-03",
            "code": "B.XSHE",
            "mode": "红断低吸",
            "blockCodeList": "BK003",
            "blockCategoryCodeList": "",
            "net_realized_ret": -1.0,
        },
    ])

    out = ensure_training_schema(df)

    assert out["blockCodeList"].tolist() == ["BK001,BK002", "BK003"]
    assert out["blockCategoryCodeList"].tolist() == ["CAT001", ""]
    out.to_parquet(tmp_path / "training_rows.parquet", index=False)


def test_qibao_benchmark_day_mean_is_independent_variant() -> None:
    df = ensure_training_schema(pd.DataFrame([
        {
            "date": "2026-06-30",
            "code": "A.XSHE",
            "mode": "强攻标杆起爆",
            "net_realized_ret": 10.0,
        },
        {"date": "2026-06-30", "code": "B.XSHE", "mode": "绿断低吸", "net_realized_ret": -2.0},
        {"date": "2026-07-01", "code": "C.XSHE", "mode": "标杆短线起爆", "net_realized_ret": 4.0},
    ]))

    assert day_mean(df, "net_realized_ret", "qibao_benchmark_star").tolist() == [10.0, 4.0]


def test_ai_intelligence_short_day_mean_is_independent_variant() -> None:
    df = ensure_training_schema(pd.DataFrame([
        {
            "date": "2026-07-01",
            "code": "A.XSHE",
            "ai_intelligence_short_star": True,
            "net_realized_ret": 3.0,
        },
        {
            "date": "2026-07-01",
            "code": "B.XSHE",
            "ai_intelligence_short_star": False,
            "net_realized_ret": -1.0,
        },
        {
            "date": "2026-07-02",
            "code": "C.XSHE",
            "ai_intelligence_short_star": True,
            "net_realized_ret": 5.0,
        },
    ]))

    assert day_mean(df, "net_realized_ret", "ai_intelligence_short_star").tolist() == [3.0, 5.0]


def test_training_schema_backfills_ai_short_from_legacy_intelligence_long() -> None:
    df = ensure_training_schema(pd.DataFrame([
        {
            "date": "2026-07-01",
            "code": "A.XSHE",
            "intelligence_long_star": True,
            "intelligence_long_score": 0.5,
            "net_realized_ret": 3.0,
        },
    ]))

    assert bool(df["ai_intelligence_short_star"].iloc[0]) is True
    assert df["ai_intelligence_short_score"].iloc[0] == 0.5
