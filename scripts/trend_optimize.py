#!/usr/bin/env python3
"""趋势 book offline baseline — judged by trend_guards (NOT the short-line guards).

Productionizes scripts/research_trend_longhold.py: builds non-overlapping holds
from the validated trend-strength selector (mainline_signal), labels each hold's
entry regime (proxy regime from cached date_kline), and runs them through
src/xiaocao/research/trend_guards.py — the compounded / max-dd / turnover /
walk-forward / per-hold-significance / survives-non-bull instrument.

The point is the HONEST OOS verdict: does XH-018's +6~20pp survive walk-forward
and non-bull regimes, on enough INDEPENDENT (non-overlapping) holds to mean
anything? Cache-only. Usage: python3 scripts/trend_optimize.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache, iter_cached_responses  # noqa: E402
from xiaocao.research import trend_guards  # noqa: E402
from xiaocao.strategy import mainline_signal as ms  # noqa: E402
from xiaocao.strategy import regime as regime_mod  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"

# Pre-registered configs (honest n_tried = len). L=trend lookback, R=hold/rebalance,
# M=# concepts, sel='trend'|'rotation'. Spans short (more holds, churn) -> long
# (more alpha, fewer independent holds) to expose the holds-vs-alpha tension.
CONFIGS = [
    {"L": 60, "R": 20, "M": 3, "sel": "trend"},
    {"L": 60, "R": 30, "M": 3, "sel": "trend"},
    {"L": 60, "R": 40, "M": 3, "sel": "trend"},
    {"L": 60, "R": 60, "M": 3, "sel": "trend"},
    {"L": 20, "R": 20, "M": 3, "sel": "trend"},
    {"L": 60, "R": 30, "M": 3, "sel": "rotation", "W": 20, "K": 5},
]


def regime_known_dates() -> set[str]:
    """Dates where date_kline genuinely has a breadth sample (so a proxy regime is
    real, not the 'neutral' default returned for missing dates)."""
    cnt: dict[str, int] = defaultdict(int)
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list):
            for k in data:
                if isinstance(k, dict) and k.get("tradeDate") and k.get("code"):
                    cnt[k["tradeDate"]] += 1
    return {d for d, c in cnt.items() if c >= 30}


def build_holds(panel, cache, known, cfg):
    days = panel["days"]
    L, R, M = cfg["L"], cfg["R"], cfg["M"]
    holds = []
    prev: set[str] = set()
    i = max(L, cfg.get("W", 0))
    while i < len(days) - R:
        if cfg["sel"] == "trend":
            picks = ms.select_by_trend_strength(panel, i, L=L, M=M)
        else:
            picks = ms.select_by_rotation_freq(panel, i, W=cfg["W"], K=cfg["K"], M=M)
        sf = [ms.cum_return(panel["ret"], days, c, i, i + R) for c in picks]
        sf = [x for x in sf if x is not None]
        allf = [ms.cum_return(panel["ret"], days, c, i, i + R) for c in panel["num"][days[i]]]
        allf = [x for x in allf if x is not None]
        if sf and len(allf) >= 10:
            picks_set = set(picks)
            reg = regime_mod.derive_proxy_regime(days[i], cache) if days[i] in known else "unknown"
            holds.append({
                "entry": days[i],
                "strat_ret": sum(sf) / len(sf),
                "base_ret": sum(allf) / len(allf),
                "regime": reg,
                "turnover": (len(picks_set - prev) / M) if prev else 0.0,
            })
            prev = picks_set
        i += R
    return holds


def main():
    panel = ms.load_concept_panel(DB)
    cache = SQLiteCache(DB)
    known = regime_known_dates()
    days = panel["days"]
    print(f"concept panel: {len(days)} days ({days[0]}..{days[-1]}); regime-known dates: {len(known)}")
    print(f"instrument: trend_guards (compounded/dd/turnover/walk-forward/per-hold-t/survives-non-bull)")
    print(f"n_tried (Bonferroni) = {len(CONFIGS)}\n")

    for cfg in CONFIGS:
        holds = build_holds(panel, cache, known, cfg)
        v = trend_guards.evaluate_trend(holds, n_tried=len(CONFIGS), cache_only=True)
        c = v["compounded"]
        wf = v["walk_forward"]
        nb = v["non_bull"]
        tag = f"{cfg['sel']} L{cfg['L']}/R{cfg['R']}/M{cfg['M']}"
        mark = "✅PASS" if v["verdict"] == "PASS" else "❌" + ",".join(v["rejected_by"])
        print(f"{tag:<22} holds={v['n_holds']:<3} "
              f"strat={c['strat']:+6.1f}% base={c['base']:+6.1f}% alpha={c['alpha']:+6.1f}pp "
              f"mdd={v['max_drawdown']:4.1f}% turn={v['turnover']:.0%}")
        print(f"{'':<22} wf train={wf['train_alpha']:+.1f}/test={wf['test_alpha']:+.1f}pp  "
              f"per-hold α={v['per_hold']['alpha_mean']:+.2f}% win={v['per_hold']['win']:.0%} "
              f"t={v['significance']['t']:+.2f} p={v['significance']['p']:.3f}  "
              f"non-bull α={nb['alpha_mean']:+.2f}% (n={nb['n_holds']})")
        print(f"{'':<22} -> {mark}")
        for w in v["warnings"]:
            print(f"{'':<22}    ⚠ {w}")
        print()


if __name__ == "__main__":
    main()
