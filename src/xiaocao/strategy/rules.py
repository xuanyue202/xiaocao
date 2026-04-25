from __future__ import annotations

from typing import Any

SUPER_JW = 300
STRONG_JW = 200
QUALIFIED_JW = 150


def pick_big_ones(items: list[dict[str, Any]], upper_num: int = 5) -> list[dict[str, Any]]:
    ranked = [item for item in items if _num(item.get("num")) > 0]
    ranked.sort(key=lambda item: _num(item.get("num")), reverse=True)
    if not ranked:
        return []
    top = _num(ranked[0].get("num"))
    rank = 0
    current_top = top
    picked = []
    for item in ranked[:upper_num]:
        value = _num(item.get("num"))
        if picked and (value < current_top - 20 or value < top * 0.8):
            break
        if picked and value < current_top - 5:
            rank += 1
            current_top = value
        item["r"] = rank
        picked.append(item)
    return picked


def check_lianban(details: list[dict[str, Any]], picked_block: list[dict[str, Any]], picked_category: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    output = []
    for detail in details:
        focus = _direction_obj(detail, picked_block, picked_category)
        if _num(detail.get("xcjw")) < STRONG_JW / 1.3:
            break
        if _num(detail.get("isWeak")) != 1 or _num(detail.get("ylimitupdays")) != 1 or _num(detail.get("jsjl")) <= 0:
            continue
        if _compare_jw(detail, SUPER_JW, focus):
            output.append(_signal(date, "接力低弱转1", detail, focus, "弱转强 + 昨日连板 + 竞王达标"))
        if _num(detail.get("openPctChangeRate")) >= 1.0 and _compare_jw(detail, STRONG_JW, focus):
            output.append(_signal(date, "接力低弱转2", detail, focus, "高开弱转强 + 昨日连板 + 竞王达标"))
    return output


def check_dixi(details: list[dict[str, Any]], picked_block: list[dict[str, Any]], picked_category: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    output = []
    for rank, detail in enumerate(details, start=1):
        focus = _direction_obj(detail, picked_block, picked_category)
        if _num(detail.get("xcjw")) < QUALIFIED_JW / 1.3:
            break
        if _num(detail.get("isDownBroken")) == 1 and _compare_jw(detail, QUALIFIED_JW, focus) and _num(detail.get("cjs")) > 0:
            output.append(_signal(date, "绿断低吸", detail, focus, "绿断 + 低吸有分 + 竞王达标"))
        if _num(detail.get("isUpBroken")) == 1 and _compare_jw(detail, QUALIFIED_JW, focus) and _num(detail.get("cjs")) > 0:
            output.append(_signal(date, "红断低吸", detail, focus, "红断 + 低吸有分 + 竞王达标"))
        if _num(detail.get("isFirstUpBroken")) == 1 and _compare_jw(detail, QUALIFIED_JW, focus) and _num(detail.get("cjs")) > 0:
            output.append(_signal(date, "首红断低吸", detail, focus, "首红断 + 低吸有分 + 竞王达标"))
        if rank <= 2 and _num(detail.get("isBottom")) == 1 and _compare_jw(detail, STRONG_JW, focus):
            output.append(_signal(date, "全盘低位低吸", detail, focus, "低吸池前2 + 低位 + 竞王达标"))
        if focus["direction"] and _num(detail.get("isHalf")) == 1 and _compare_jw(detail, STRONG_JW * 1.3, focus) and _num(detail.get("cjs")) > 0:
            output.append(_signal(date, "N字低吸", detail, focus, "强方向 + N字半位 + 低吸有分"))
        if focus["direction"] and _num(detail.get("isGestationLine")) == 1 and _compare_jw(detail, QUALIFIED_JW * 1.3, focus) and _num(detail.get("cjs")) > 100:
            output.append(_signal(date, "孕线低吸", detail, focus, "强方向 + 孕线 + 低吸分达标"))
    return output


def check_direction_dixi(
    details: list[dict[str, Any]],
    picked_block: list[dict[str, Any]],
    picked_category: list[dict[str, Any]],
    date: str,
) -> list[dict[str, Any]]:
    output = []
    for rank, detail in enumerate(details[:3], start=1):
        focus = _direction_obj(detail, picked_block, picked_category)
        if _num(detail.get("isBottom")) == 1 and _compare_jw(detail, STRONG_JW, focus):
            output.append(_signal(date, "方向低位低吸", detail, focus, f"方向内低吸排名{rank} + 低位 + 竞王达标"))
        if _num(detail.get("isDownBroken")) == 1 and _compare_jw(detail, QUALIFIED_JW, focus) and _num(detail.get("cjs")) > 0:
            output.append(_signal(date, "方向内绿盘低吸前3名", detail, focus, f"方向内低吸排名{rank} + 绿断 + 低吸有分"))
    return output


def _direction_obj(detail: dict[str, Any], picked_block: list[dict[str, Any]], picked_category: list[dict[str, Any]]) -> dict[str, Any]:
    block_focus = _picked(detail.get("blockCodeList") or detail.get("industryBlockCodeList"), picked_block, "blockCode")
    category_focus = _picked(detail.get("blockCategoryCodeList"), picked_category, "categoryCode")
    return {
        "direction": bool(block_focus or category_focus),
        "directionRank": _focus_rank(block_focus),
        "categoryRank": _focus_rank(category_focus),
        "directionCodes": [item["code"] for item in block_focus],
        "categoryCodes": [item["code"] for item in category_focus],
    }


def _picked(current: Any, picked: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    if isinstance(current, str):
        current = [part.strip() for part in current.split(",")] if "," in current else [current]
    if not isinstance(current, list):
        return []
    values = set(current)
    return [{"code": item.get(key), "rank": item.get("r", 0)} for item in picked if item.get(key) in values]


def _focus_rank(items: list[dict[str, Any]]) -> int:
    return int(items[0]["rank"]) if items else -1


def _compare_jw(detail: dict[str, Any], threshold: float, focus: dict[str, Any]) -> bool:
    score = _num(detail.get("xcjw"))
    return score >= threshold or (focus["direction"] and score >= threshold / 1.3)


def _signal(date: str, mode: str, detail: dict[str, Any], focus: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "date": date,
        "mode": mode,
        "code": detail.get("code") or detail.get("stockCode"),
        "name": detail.get("codeName") or detail.get("name") or detail.get("stockName"),
        "xcjw": detail.get("xcjw"),
        "cjs": detail.get("cjs"),
        "jsjl": detail.get("jsjl"),
        "jssb": detail.get("jssb"),
        "pctChange": detail.get("entityPctChangeRate") or detail.get("pctChangeRate") or detail.get("pctChange"),
        "openPctChange": detail.get("openPctChangeRate") or detail.get("openPctChange"),
        "direction": focus["direction"],
        "directionRank": focus["directionRank"],
        "categoryRank": focus["categoryRank"],
        "reason": reason,
    }


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
