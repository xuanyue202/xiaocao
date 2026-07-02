"""Book T trend-candidate generator.

Book T is a separate paper-only long-hold book. It is not a short-line mode and
does not consume Book-B picks. The generator below turns the current main-line
category ranks into a small basket of large-cap constituents, leaving execution,
accounting and exits to the deterministic live scripts.
"""
from __future__ import annotations

from typing import Any, Iterable

from xiaocao.strategy.bigcap import bigcap_codes
from xiaocao.strategy.params import TREND_LOOKBACK_L, TREND_REBALANCE_R, TREND_TOP_M, TREND_TRAIL_DD

TREND_MODE = "趋势主线"
DEFAULT_BASKET_PREMIUM_PCT = 0.8


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


def _select_representative(
    codes: list[str],
    *,
    stock_info: dict[str, dict[str, Any]],
    bigcap_set: set[str],
) -> tuple[str | None, bool]:
    if not codes:
        return None, False
    ranked = sorted(
        _dedupe(codes),
        key=lambda code: (
            0 if code in bigcap_set else 1,
            -_num((stock_info.get(code) or {}).get("tradableAShare")),
            code,
        ),
    )
    code = ranked[0] if ranked else None
    return code, bool(code in bigcap_set) if code else False


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
    category_count = max_positions if category_count is None else max(1, int(category_count))
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
        code, is_big = _select_representative(codes, stock_info=stock_info, bigcap_set=bigcaps)
        if not code or code in used_codes:
            continue
        used_codes.add(code)
        info = stock_info.get(code) or {}
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
        })
        if len(candidates) >= max_positions:
            break

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
            "reason": (
                f"Book T {c['category_name'] or c['category_code']} "
                f"r{c['category_rank']} bigcap={bool(c['is_big_cap'])}"
            ),
        })
        out.append(enriched)
    return out
