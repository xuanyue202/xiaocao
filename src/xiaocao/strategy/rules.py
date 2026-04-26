from __future__ import annotations

from typing import Any

SUPER_JW = 300
STRONG_JW = 200
QUALIFIED_JW = 150


def pick_big_ones(items: list[dict[str, Any]], upper_num: int = 5) -> list[dict[str, Any]]:
    ranked = [item for item in items if isinstance(item, dict) and _num(item.get("num")) > 0]
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


def check_lianban(details: list[dict[str, Any]], picked_block: list[dict[str, Any]], picked_category: list[dict[str, Any]], date: str, state: Any = None) -> list[dict[str, Any]]:
    """state kwarg accepted for API symmetry but currently unused (v3.5 score scaling rejected — see _compare_jw docstring)."""
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


def check_dixi(details: list[dict[str, Any]], picked_block: list[dict[str, Any]], picked_category: list[dict[str, Any]], date: str, state: Any = None) -> list[dict[str, Any]]:
    """state kwarg unused (v3.5 score scaling rejected)."""
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
    state: Any = None,
) -> list[dict[str, Any]]:
    output = []
    for rank, detail in enumerate(details[:3], start=1):
        focus = _direction_obj(detail, picked_block, picked_category)
        if _num(detail.get("isBottom")) == 1 and _compare_jw(detail, STRONG_JW, focus):
            output.append(_signal(date, "方向低位低吸", detail, focus, f"方向内低吸排名{rank} + 低位 + 竞王达标"))
        if _num(detail.get("isDownBroken")) == 1 and _compare_jw(detail, QUALIFIED_JW, focus) and _num(detail.get("cjs")) > 0:
            output.append(_signal(date, "方向内绿盘低吸前3名", detail, focus, f"方向内低吸排名{rank} + 绿断 + 低吸有分"))
    return output


def check_qibao(
    details: list[dict[str, Any]],
    picked_block: list[dict[str, Any]],
    picked_category: list[dict[str, Any]],
    date: str,
    state: Any = None,
) -> list[dict[str, Any]]:
    """红盘起爆 (red-board explosion).

    First-principles per 0410 / 0412 / 0419: 起爆 finds stocks where the algorithm
    signals strong attack potential (high jssb score) BEFORE the price has moved
    much. Buy point is when the stock has just turned positive ("红盘") but is
    not yet stretched (低涨幅 / 低位卡位). 0419: "9:31-9:35 排名上来但涨幅还不高的".

    Rules emit two variants:
      - 红盘起爆主攻 (jssb ≥ STRONG_JW=200, currently red, pctChange in (0, 4]):
        algorithm-confirmed core attack candidate, in the 0-4% sweet spot
      - 方向红盘起爆 (jssb ≥ QUALIFIED_JW=150 with direction support, pctChange in (0, 3]):
        weaker score but direction共振, tighter pct cap

    Both modes filter out:
      - already 涨停 (isLimitUp == 1)
      - jssb floor: bail out of the sorted iteration once below QUALIFIED_JW/1.3
        (per the dixi pattern — input is sorted by jssb descending)
      - negative pctChange (not yet 红盘)
    """
    output = []
    for detail in details:
        focus = _direction_obj(detail, picked_block, picked_category)
        if _num(detail.get("jssb")) < QUALIFIED_JW / 1.3:
            break
        if _num(detail.get("isLimitUp")) == 1:
            continue
        pct = _num(
            detail.get("entityPctChangeRate")
            or detail.get("pctChangeRate")
            or detail.get("pctChange")
        )
        if pct <= 0 or pct >= 9.5:
            continue  # not 红盘 yet, OR already at 涨停 (≥+9.5%)
        # 红盘起爆主攻: high jssb + 0 < pct ≤ 4
        if pct <= 4.0 and _compare_score(detail, "jssb", STRONG_JW, focus):
            output.append(_signal(
                date, "红盘起爆主攻", detail, focus,
                "高分起爆 + 红盘 + 涨幅可控",
            ))
        # 方向红盘起爆: lower jssb + direction共振 + tighter pct
        elif (
            pct <= 3.0
            and focus["direction"]
            and _compare_score(detail, "jssb", QUALIFIED_JW, focus)
        ):
            output.append(_signal(
                date, "方向红盘起爆", detail, focus,
                "方向红盘起爆 + 涨幅低位",
            ))
    return output


def _compare_score(detail: dict[str, Any], score_field: str, threshold: float, focus: dict[str, Any]) -> bool:
    """Generalization of `_compare_jw` to any score field (xcjw / jssb / cjs / jsjl).

    Direction support discounts the threshold by 1.3 — same convention used for
    xcjw across check_lianban / check_dixi / check_direction_dixi.
    """
    score = _num(detail.get(score_field))
    return score >= threshold or (focus["direction"] and score >= threshold / 1.3)


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


def _compare_jw(detail: dict[str, Any], threshold: float, focus: dict[str, Any], state_fitness: float = 0.0) -> bool:
    """xcjw >= threshold (or threshold/1.3 if direction-supported).

    NOTE: state_fitness param exists for API compatibility but is IGNORED.
    State-modulated score scaling was tried in v3.5 (`_compare_score_v3` in the
    plan) — empirically a NET LOSS:
      v3.3 active n=73 avg=+3.40% sum=+248%
      v3.5 active n=135 avg=+1.00% sum=+135%
    Even ±15% state-based scaling created 57 new lower-quality signals that
    diluted the universe. The 300/200/150 score thresholds genuinely are
    千锤百炼 — they shouldn't be relaxed even softly. State-modulation belongs
    at the adaptive layer (where it works), NOT the rules layer.
    """
    score = _num(detail.get("xcjw"))
    return score >= threshold or (focus["direction"] and score >= threshold / 1.3)


def _compare_score(detail: dict[str, Any], score_field: str, threshold: float, focus: dict[str, Any], state_fitness: float = 0.0) -> bool:
    """Like `_compare_jw` but for any score field. state_fitness ignored (see above)."""
    score = _num(detail.get(score_field))
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
        # Block memberships are needed downstream to annotate signals against
        # the rolling main-line set. Three different code spaces co-exist:
        # - blockCodeList: 东财板块 (.DDBK), fine-grained themes
        # - blockCategoryCodeList: 大类 (.BKDL)
        # - excIndustryCode: 中信行业 (.ZHBK), what xiao_cao_industry_block_rank
        #   actually uses, so this is the field that intersects with main-line.
        "blockCodeList": detail.get("blockCodeList") or detail.get("industryBlockCodeList"),
        "blockCategoryCodeList": detail.get("blockCategoryCodeList"),
        "excIndustryCode": _exc_industry_code(detail),
    }


def _exc_industry_code(detail: dict[str, Any]) -> str | None:
    items = detail.get("excIndustryStockList") or []
    if isinstance(items, list) and items and isinstance(items[0], dict):
        code = items[0].get("code")
        if code:
            return str(code)
    return None


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


