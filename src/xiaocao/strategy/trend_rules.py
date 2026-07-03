"""Book T trend-candidate generator.

Book T is a separate paper-only long-hold book. It is not a short-line mode and
does not consume Book-B picks. The generator below turns current main-line
category ranks into a small basket of large-cap constituents, while keeping the
paper basket aligned with the current Xiaocao posture: stay exposed to trend,
but do not turn defensive/old-direction strength into a trend buy.
"""
from __future__ import annotations

from typing import Any, Iterable

from xiaocao.strategy.bigcap import bigcap_codes
from xiaocao.strategy.params import TREND_LOOKBACK_L, TREND_REBALANCE_R, TREND_TOP_M, TREND_TRAIL_DD

TREND_MODE = "趋势主线"
DEFAULT_BASKET_PREMIUM_PCT = 0.8
DEFAULT_CATEGORY_SCAN_MULTIPLIER = 3

EXTERNAL_DIRECTION_KEYWORDS = (
    "银行",
    "保险",
    "证券",
    "券商",
    "医药",
    "药",
    "白酒",
    "酿酒",
    "零售",
    "酒店",
    "旅游",
    "航空",
    "煤炭",
    "石油",
)

POSTURE_ALIGNED_KEYWORDS = (
    "电子",
    "半导体",
    "芯片",
    "存储",
    "元器件",
    "pcb",
    "cpo",
    "通信",
    "光模块",
    "光电",
    "玻璃基板",
    "科创",
    "20cm",
    "机器人",
    "智造",
    "算力",
    "ai硬件",
    "京东方",
)

ALIGNMENT_PRIORITY = {"aligned": 0, "neutral": 1, "external": 2}
TREND_SWITCH_POLICY_HELD = "hold_exposure; paired_morning_switch_when_replacement_ready"
TREND_SWITCH_POLICY_NEW_BUY = (
    "prefer_aligned_low_turnover; block_external; paired_switch_external_when_replacement_ready"
)
TREND_SWITCH_EXECUTION_EXIT = "paired_morning_switch"
TREND_SWITCH_EXECUTION_REPLACEMENT = "paired_morning_replacement"
TREND_EXIT_POSTURE_MISMATCH = "TREND_POSTURE_MISMATCH"
TREND_EXIT_REBALANCE = "TREND_REBALANCE_R"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _code(row: dict[str, Any]) -> str:
    return str(row.get("stockId") or row.get("code") or row.get("stockCode") or "").strip()


def _name(row: dict[str, Any]) -> str:
    return str(row.get("stockName") or row.get("codeName") or row.get("name") or "").strip()


def _category_code(row: dict[str, Any]) -> str:
    return str(row.get("categoryCode") or row.get("code") or row.get("blockCode") or "").strip()


def _category_name(row: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("categoryName") or row.get("blockName") or "").strip()


def _category_strength(row: dict[str, Any]) -> float:
    for key in ("num", "trendScore", "score", "value"):
        if row.get(key) not in (None, ""):
            return _num(row.get(key))
    return 0.0


def _match_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for keyword in keywords:
        if keyword.lower() in lowered:
            return keyword
    return None


def classify_trend_alignment(
    *,
    code: str = "",
    name: str = "",
    category_name: str = "",
    category_code: str = "",
) -> dict[str, str]:
    """Classify a Book-T candidate against the current paper posture.

    `external` is a hard block for new buys and a paired-switch cue for existing
    Book-T paper rows after T+1, but only when the morning run has a replacement
    ready. `aligned` gets preference. `neutral` is allowed only as a low-turnover
    fallback to keep the trend sleeve invested when no better aligned
    representative exists.
    """
    text = " ".join(str(v or "") for v in (code, name, category_name, category_code))
    external = _match_keyword(text, EXTERNAL_DIRECTION_KEYWORDS)
    if external:
        return {
            "trend_alignment": "external",
            "trend_alignment_reason": f"外部旧方向/防守方向:{external}",
        }
    aligned = _match_keyword(text, POSTURE_ALIGNED_KEYWORDS)
    if aligned:
        return {
            "trend_alignment": "aligned",
            "trend_alignment_reason": f"小草趋势主线相关:{aligned}",
        }
    return {
        "trend_alignment": "neutral",
        "trend_alignment_reason": "非外部旧方向；仅作趋势仓位兜底候选",
    }


def _extract_codes(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_extract_codes(item))
        return _dedupe(out)
    if isinstance(value, dict):
        for key in ("data", "codes", "stockCodes", "stockIds", "codeList", "list"):
            if key in value:
                return _extract_codes(value[key])
        code = value.get("code") or value.get("stockCode") or value.get("stockId")
        return [str(code)] if code else []
    return []


def _dedupe(codes: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        code = str(code or "").strip()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _detail_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows: list[dict[str, Any]] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("code", key)
                rows.append(row)
        if rows:
            return rows
        if payload.get("code") or payload.get("stockId"):
            return [payload]
    return []


def _detail_map(payload: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _detail_rows(payload):
        code = _code(row)
        if code:
            out[code] = row
    return out


def _stock_info_maps(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    by_code = {_code(row): row for row in rows if _code(row)}
    big = bigcap_codes(rows, top_pct=0.2)
    return by_code, big


def _category_rows(client: Any, date_iso: str) -> list[dict[str, Any]]:
    rows = client.get_block_category_rank_v3(date_iso, model=0)
    if not isinstance(rows, list):
        return []
    usable = [row for row in rows if isinstance(row, dict) and _category_code(row)]
    return sorted(usable, key=_category_strength, reverse=True)


def _constituent_codes(client: Any, date_iso: str, category_code: str) -> list[str]:
    payload = client.get_code_by_xiao_cao_block(date_iso, categoryCodeList=category_code)
    return _extract_codes(payload)


def _rank_representatives(
    codes: list[str],
    *,
    stock_info: dict[str, dict[str, Any]],
    bigcap_set: set[str],
) -> list[tuple[str, bool]]:
    if not codes:
        return []
    ranked = sorted(
        _dedupe(codes),
        key=lambda code: (
            0 if code in bigcap_set else 1,
            -_num((stock_info.get(code) or {}).get("tradableAShare")),
            code,
        ),
    )
    return [(code, bool(code in bigcap_set)) for code in ranked]


def generate_trend_picks(
    client: Any,
    date_iso: str,
    *,
    max_positions: int = TREND_TOP_M,
    category_count: int | None = None,
    basket_premium_pct: float = DEFAULT_BASKET_PREMIUM_PCT,
) -> list[dict[str, Any]]:
    """Generate a small Book-T basket for paper recording.

    The function makes O(top-M) constituent calls and one batched realtime call.
    It deliberately avoids any Book-B mode field as an input; overlap with Book B
    is allowed later by keeping separate ledger rows.
    """
    max_positions = max(1, int(max_positions))
    category_count = (
        max_positions * DEFAULT_CATEGORY_SCAN_MULTIPLIER
        if category_count is None else max(1, int(category_count))
    )
    info_rows = client.stock_info()
    if not isinstance(info_rows, list):
        info_rows = []
    stock_info, bigcaps = _stock_info_maps(info_rows)
    categories = _category_rows(client, date_iso)[: max(category_count, max_positions)]

    candidates: list[dict[str, Any]] = []
    used_codes: set[str] = set()
    for rank, cat in enumerate(categories, 1):
        cat_code = _category_code(cat)
        if not cat_code:
            continue
        codes = _constituent_codes(client, date_iso, cat_code)
        picked: tuple[str, bool, dict[str, Any], dict[str, str]] | None = None
        for code, is_big in _rank_representatives(codes, stock_info=stock_info, bigcap_set=bigcaps):
            if code in used_codes:
                continue
            info = stock_info.get(code) or {}
            alignment = classify_trend_alignment(
                code=code,
                name=_name(info),
                category_name=_category_name(cat),
                category_code=cat_code,
            )
            if alignment["trend_alignment"] == "external":
                continue
            picked = (code, is_big, info, alignment)
            break
        if picked is None:
            continue
        code, is_big, info, alignment = picked
        used_codes.add(code)
        candidates.append({
            "book": "T",
            "code": code,
            "name": _name(info),
            "mode": TREND_MODE,
            "profile": "trend",
            "is_main_line": True,
            "is_big_cap": is_big,
            "category_code": cat_code,
            "category_name": _category_name(cat),
            "category_rank": rank,
            "category_score": _category_strength(cat),
            "trend_score": _num(cat.get("trendScore"), _category_strength(cat)),
            "trend_num": _num(cat.get("num"), _category_strength(cat)),
            "trend_lookback_days": TREND_LOOKBACK_L,
            "trend_rebalance_days": TREND_REBALANCE_R,
            "trend_trail_dd_pct": TREND_TRAIL_DD,
            "tradableAShare": info.get("tradableAShare"),
            "trend_alignment": alignment["trend_alignment"],
            "trend_alignment_reason": alignment["trend_alignment_reason"],
        })

    candidates = sorted(
        candidates,
        key=lambda row: (
            ALIGNMENT_PRIORITY.get(str(row.get("trend_alignment") or "neutral"), 9),
            int(_num(row.get("category_rank"), 9999)),
            -_num(row.get("category_score")),
            str(row.get("code") or ""),
        ),
    )

    if not candidates:
        return []

    detail_payload = client.second_line_detail_info(",".join(c["code"] for c in candidates))
    details = _detail_map(detail_payload)
    out: list[dict[str, Any]] = []
    for c in candidates:
        detail = details.get(str(c["code"]), {})
        open_px = _num(detail.get("open") or detail.get("trade"))
        if open_px <= 0:
            continue
        name = _name(detail) or str(c.get("name") or "")
        alignment = classify_trend_alignment(
            code=str(c.get("code") or ""),
            name=name,
            category_name=str(c.get("category_name") or ""),
            category_code=str(c.get("category_code") or ""),
        )
        if alignment["trend_alignment"] == "external":
            continue
        pre_close = _num(detail.get("preClose"))
        pct = _num(detail.get("pctChangeRate"))
        basket = round(open_px * (1.0 + basket_premium_pct / 100.0), 4)
        enriched = dict(c)
        enriched.update({
            "name": name,
            "open": open_px,
            "pre_close": pre_close or None,
            "open_pct_change": pct,
            "basket_price": basket,
            "basket_rule": f"trend_open+{basket_premium_pct:.1f}%",
            "basket_premium_pct": basket_premium_pct,
            "trend_alignment": alignment["trend_alignment"],
            "trend_alignment_reason": alignment["trend_alignment_reason"],
            "trend_switch_policy": TREND_SWITCH_POLICY_NEW_BUY,
            "reason": (
                f"Book T {c['category_name'] or c['category_code']} "
                f"r{c['category_rank']} bigcap={bool(c['is_big_cap'])} "
                f"alignment={alignment['trend_alignment']}"
            ),
        })
        out.append(enriched)
        if len(out) >= max_positions:
            break
    return out
