"""趋势主线 signal primitives — the 趋势 体系's selection core.

Promoted (not rewritten) from the validated research scripts:
  - scripts/research_trend_longhold.py  (trailing/cum + long-hold selection; XH-018
    showed +6~20pp vs avg-theme at quarterly rebalance — the VALIDATED signal)
  - scripts/research_rotation_mainline.py (rotation-frequency persistence)

Cache-only by construction: reads block_category_rank_v3 (model=0) from the SQLite
cache; the per-concept daily return is `prePctChangeRate` (verified sane —
算力芯片 cumulates +75%/yr). No live API, backtest-safe — same as state.py.

Two selectors are exposed (both pure):
  - `select_by_trend_strength` : top-M concepts by trailing-L return (XH-018 signal)
  - `select_by_rotation_freq`  : top-M by persistence in the top-K rank (小草 轮动频率)
The trend book's VALIDATED long-hold baseline uses trend-strength; rotation is kept
for comparison (it only ever tested ≈0 at SHORT holds — untested long, see XH-013).

This is a 法-level 体系 sibling of strategy/rules.py (短线低吸), both consuming the
shared 道 (regime/StateVector) but NEVER each other. Nothing here enters the
deterministic spine until a trend_guards PASS + §10 gate (OPERATING_CONTRACT §2).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from xiaocao.api.cache import iter_cached_responses

ENDPOINT = "/stock/xiao_cao_block_category_rank_v3"


def load_concept_panel(cache_path: str | Path) -> dict[str, Any]:
    """Load the named-concept rank panel from cache.

    Returns {"num": {date: {concept: num}}, "ret": {date: {concept: pct}},
             "name": {concept: str}, "days": [sorted trading dates]}.
    `num` is 小草's concept-strength score; `ret` is the concept's daily % return.
    """
    num: dict[str, dict[str, float]] = defaultdict(dict)
    ret: dict[str, dict[str, float]] = defaultdict(dict)
    name: dict[str, str] = {}
    for params_json, data in iter_cached_responses(str(cache_path), ENDPOINT, include_params=True):
        try:
            p = json.loads(params_json).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        if p.get("model") != 0 or not isinstance(data, dict):
            continue
        d = p.get("date")
        lst = data.get("localCategoryRankList") or data.get("globalCategoryRankList")
        if not (d and isinstance(lst, list)):
            continue
        for it in lst:
            if not isinstance(it, dict):
                continue
            cc = it.get("categoryCode")
            if not cc:
                continue
            num[d][cc] = float(it.get("num") or 0.0)
            v = it.get("prePctChangeRate")
            if isinstance(v, (int, float)):
                ret[d][cc] = float(v)
            if it.get("name"):
                name[cc] = it["name"]
    days = sorted(d for d in num if num[d])
    return {"num": dict(num), "ret": dict(ret), "name": name, "days": days}


def cum_return(ret: dict, days: list, concept: str, i0: int, i1: int) -> float | None:
    """Compounded return (percent) of a concept over (days[i0], days[i1]]."""
    if not (0 <= i0 < i1 < len(days)):
        return None
    c = 1.0
    for j in range(i0 + 1, i1 + 1):
        v = ret.get(days[j], {}).get(concept)
        if v is None:
            return None
        c *= 1.0 + v / 100.0
    return (c - 1.0) * 100.0


def trailing_strength(ret: dict, days: list, concept: str, i: int, L: int) -> float | None:
    """Trailing L-day compounded return (percent) ending at days[i]."""
    return cum_return(ret, days, concept, i - L, i)


def rotation_frequency(num: dict, days: list, i: int, W: int, K: int) -> dict[str, float]:
    """Per-concept fraction of the trailing W days it sat in the top-K by num."""
    cnt: dict[str, int] = defaultdict(int)
    lo = max(0, i - W + 1)
    for j in range(lo, i + 1):
        top = sorted(num.get(days[j], {}).items(), key=lambda t: t[1], reverse=True)[:K]
        for cc, _ in top:
            cnt[cc] += 1
    span = i - lo + 1
    return {cc: c / span for cc, c in cnt.items()} if span else {}


def select_by_trend_strength(panel: dict, i: int, *, L: int, M: int) -> list[str]:
    """VALIDATED (XH-018) selector: top-M concepts by trailing-L compounded return."""
    ret, days = panel["ret"], panel["days"]
    if i < L:
        return []
    scored = []
    for cc in panel["num"].get(days[i], {}):
        s = trailing_strength(ret, days, cc, i, L)
        if s is not None:
            scored.append((s, cc))
    scored.sort(reverse=True)
    return [cc for _, cc in scored[:M]]


def select_by_rotation_freq(panel: dict, i: int, *, W: int, K: int, M: int) -> list[str]:
    """小草 轮动频率 selector: top-M concepts by top-K persistence over trailing W."""
    if i < W - 1:  # need a full W-day window [i-W+1, i]
        return []
    freq = rotation_frequency(panel["num"], panel["days"], i, W, K)
    return [cc for cc, _ in sorted(freq.items(), key=lambda t: t[1], reverse=True)[:M]]
