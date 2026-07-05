from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from kronos_screen.scripts.forward_eval import day_mean, ensure_training_schema  # noqa: E402


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
    assert "intelligence_long_star" in out.columns
    assert "regime" in out.columns
    assert "direction_rank" in out.columns
    assert bool(out.loc[out["code"] == "A.XSHE", "qibao_benchmark_star"].iloc[0]) is True
    assert bool(out.loc[out["code"] == "B.XSHE", "qibao_benchmark_star"].iloc[0]) is False


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
