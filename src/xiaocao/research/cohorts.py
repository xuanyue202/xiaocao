"""Research/watchlist cohorts that sit between raw pools and live strategy.

These cohorts are observable evidence surfaces. They are intentionally not part
of the deterministic trading spine: a cohort member can be a benchmark,
watchlist, or research sample without becoming an emitted buy signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


QIBAO_BUYABLE_BENCHMARK = "qibao_raw_top10_elec20_buyable"
QIBAO_HIGH_OPEN_WATCH = "qibao_raw_top10_elec20_high_open_watch"
QIBAO_LIMITLIKE_WATCH = "qibao_raw_top10_elec20_limitlike_watch"


@dataclass(frozen=True)
class CohortDefinition:
    id: str
    layer: str
    label: str
    authority: int
    description: str


QIBAO_COHORTS: dict[str, CohortDefinition] = {
    QIBAO_BUYABLE_BENCHMARK: CohortDefinition(
        id=QIBAO_BUYABLE_BENCHMARK,
        layer="benchmark",
        label="raw qibao top10 buyable benchmark",
        authority=0,
        description="raw qibao top10 + electronic/20cm + red + open<=6 + not limit-like",
    ),
    QIBAO_HIGH_OPEN_WATCH: CohortDefinition(
        id=QIBAO_HIGH_OPEN_WATCH,
        layer="watchlist",
        label="raw qibao high-open continuation watch",
        authority=0,
        description="raw qibao top10 + electronic/20cm + red + open>6 + not limit-like",
    ),
    QIBAO_LIMITLIKE_WATCH: CohortDefinition(
        id=QIBAO_LIMITLIKE_WATCH,
        layer="watchlist",
        label="raw qibao limit-like/long-entity watch",
        authority=0,
        description="raw qibao top10 + electronic/20cm + red + near 20cm limit or long entity",
    ),
}


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def code_of(row: dict[str, Any]) -> str:
    return str(row.get("code") or row.get("stockCode") or row.get("stockId") or "")


def name_of(row: dict[str, Any]) -> str:
    return str(row.get("codeName") or row.get("name") or row.get("stockName") or "")


def is_board20(code: str) -> bool:
    return code.startswith(("300", "301", "688"))


def is_electronic(row: dict[str, Any]) -> bool:
    items = row.get("excIndustryStockList") or []
    if not isinstance(items, list):
        return False
    return any(
        isinstance(item, dict)
        and (item.get("code") == "T08.ZHBK" or item.get("codeName") == "电子")
        for item in items
    )


def open_pct(row: dict[str, Any]) -> float:
    return num(row.get("openPctChangeRate") or row.get("openPctChange"))


def entity_pct(row: dict[str, Any]) -> float:
    return num(row.get("entityPctChangeRate") or row.get("pctChangeRate") or row.get("pctChange"))


def total_pct(row: dict[str, Any]) -> float:
    return num(row.get("pctChangeRate") or row.get("pctChange") or row.get("entityPctChangeRate"))


def is_red(row: dict[str, Any]) -> bool:
    return entity_pct(row) > 0


def is_near20_or_long_entity(row: dict[str, Any]) -> bool:
    code = code_of(row)
    return (
        is_board20(code)
        and (total_pct(row) >= 18.0 or num(row.get("limitupdays")) > 0)
    ) or entity_pct(row) >= 9.5


def qibao_base_eligible(row: dict[str, Any], raw_rank: int) -> bool:
    return (
        raw_rank <= 10
        and (is_electronic(row) or is_board20(code_of(row)))
        and is_red(row)
    )


def classify_qibao_raw_cohorts(row: dict[str, Any], raw_rank: int) -> list[str]:
    """Return cohort ids for a raw-qibao row at a 1-based JSSB rank."""
    if not qibao_base_eligible(row, raw_rank):
        return []
    limitlike = is_near20_or_long_entity(row)
    if limitlike:
        return [QIBAO_LIMITLIKE_WATCH]
    if open_pct(row) > 6.0:
        return [QIBAO_HIGH_OPEN_WATCH]
    return [QIBAO_BUYABLE_BENCHMARK]


def qibao_snapshot_record(date: str, row: dict[str, Any], raw_rank: int, cohort_id: str) -> dict[str, Any]:
    definition = QIBAO_COHORTS[cohort_id]
    code = code_of(row)
    return {
        "date": date,
        "cohort_id": cohort_id,
        "layer": definition.layer,
        "authority": definition.authority,
        "code": code,
        "name": name_of(row),
        "raw_rank": raw_rank,
        "open_pct": open_pct(row),
        "pct": total_pct(row),
        "entity_pct": entity_pct(row),
        "jssb": num(row.get("jssb")),
        "xcjw": num(row.get("xcjw")),
        "short_line": num(row.get("shortLineScore")),
        "electronic": is_electronic(row),
        "board20": is_board20(code),
        "near20_or_long_entity": is_near20_or_long_entity(row),
        "limitupdays": num(row.get("limitupdays")),
        "note": definition.description,
    }
