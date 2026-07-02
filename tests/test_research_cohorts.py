from __future__ import annotations

from xiaocao.research.cohorts import (
    QIBAO_BUYABLE_BENCHMARK,
    QIBAO_HIGH_OPEN_WATCH,
    QIBAO_LIMITLIKE_WATCH,
    classify_qibao_raw_cohorts,
    qibao_snapshot_record,
)


def _row(**overrides):
    row = {
        "code": "688001.XSHG",
        "codeName": "样本科技",
        "jssb": 8.0,
        "xcjw": 180.0,
        "shortLineScore": 160.0,
        "openPctChangeRate": 3.0,
        "pctChangeRate": 8.0,
        "entityPctChangeRate": 4.8,
        "limitupdays": 0,
        "excIndustryStockList": [{"code": "T08.ZHBK", "codeName": "电子"}],
    }
    row.update(overrides)
    return row


def test_qibao_raw_buyable_benchmark_classification() -> None:
    assert classify_qibao_raw_cohorts(_row(), 1) == [QIBAO_BUYABLE_BENCHMARK]


def test_qibao_raw_high_open_is_watchlist_not_dropped() -> None:
    assert classify_qibao_raw_cohorts(_row(openPctChangeRate=7.2), 2) == [QIBAO_HIGH_OPEN_WATCH]


def test_qibao_raw_limitlike_is_watchlist_even_when_open_is_moderate() -> None:
    row = _row(openPctChangeRate=2.8, pctChangeRate=19.8, entityPctChangeRate=16.0)
    assert classify_qibao_raw_cohorts(row, 9) == [QIBAO_LIMITLIKE_WATCH]


def test_qibao_raw_tail_rank_has_no_cohort_membership() -> None:
    assert classify_qibao_raw_cohorts(_row(), 11) == []


def test_qibao_snapshot_record_preserves_authority_zero() -> None:
    record = qibao_snapshot_record("2026-06-30", _row(openPctChangeRate=7.2), 2, QIBAO_HIGH_OPEN_WATCH)
    assert record["authority"] == 0
    assert record["layer"] == "watchlist"
    assert record["raw_rank"] == 2
    assert record["open_pct"] == 7.2
