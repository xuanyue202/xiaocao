from __future__ import annotations

from typing import Any

from xiaocao.api.client import RANK_MODEL_FOCUS

from .rules import check_direction_dixi, check_dixi, check_lianban, pick_big_ones

MAX_OPEN_PCT_CHANGE = 6.0


def run_strategy(
    date: str,
    source: Any,
    modes: set[str] | None = None,
    block_model: int = RANK_MODEL_FOCUS,
    category_model: int = 0,
    sort_id: int = 40,
) -> list[dict[str, Any]]:
    block_rank = source.get_industry_block_rank(date, block_model)
    category_rank = source.get_block_category_rank(date, category_model)
    picked_block = pick_big_ones(block_rank, 5)
    picked_category = pick_big_ones(category_rank, 3)

    output = []
    requested = modes or set()
    if not requested or requested.intersection({"all", "jieli", "lianban"}):
        lianban_codes = source.get_pool(date, "jieli")
        if hasattr(source, "sort_codes"):
            lianban_codes = source.sort_codes(date, lianban_codes, 38)
        lianban_details = source.get_stock_index(date, lianban_codes)
        output.extend(check_lianban(lianban_details, picked_block, picked_category, date))
    if not requested or requested.intersection({"all", "dixi", "duanban"}):
        dixi_codes = source.get_pool(date, "dixi")
        if hasattr(source, "sort_codes"):
            dixi_codes = source.sort_codes(date, dixi_codes, 38)
        dixi_details = source.get_stock_index(date, dixi_codes)
        output.extend(check_dixi(dixi_details, picked_block, picked_category, date))
    if not requested or requested.intersection({"all", "direction"}):
        output.extend(_run_direction_dixi(date, source, picked_block, picked_category, sort_id))
    return _dedupe_signals(_filter_open_pct(output))


def _run_direction_dixi(
    date: str,
    source: Any,
    picked_block: list[dict[str, Any]],
    picked_category: list[dict[str, Any]],
    sort_id: int,
) -> list[dict[str, Any]]:
    if not hasattr(source, "get_direction_codes"):
        return []
    output = []
    directions = [(item.get("blockCode"), None) for item in picked_block if item.get("blockCode")]
    directions.extend((None, item.get("categoryCode")) for item in picked_category if item.get("categoryCode"))
    for block_code, category_code in directions:
        codes = source.get_direction_codes(date, block_code=block_code, category_code=category_code)
        if not codes:
            continue
        if hasattr(source, "sort_codes"):
            codes = source.sort_codes(date, codes, sort_id)
        details = source.get_stock_index(date, codes[:10])
        output.extend(check_direction_dixi(details, picked_block, picked_category, date))
    return output


def _dedupe_signals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for row in rows:
        key = (row.get("date"), row.get("mode"), row.get("code"))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _filter_open_pct(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _num(row.get("openPctChange")) < MAX_OPEN_PCT_CHANGE]


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
