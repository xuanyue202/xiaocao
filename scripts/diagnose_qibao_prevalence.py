"""红盘起爆主攻 prevalence 调研 (Plan A1, unblocks 7.1.2).

Question: 报告 §7.1.2 说 8 个月 mode_history 仅 1 笔 红盘起爆主攻 active。是因为
  (a) qibao 池本身就稀  (b) jssb >= STRONG_JW(200) 太严  (c) pct ∈ (0,4] 太严
  (d) 联合精度过严

For each cached trading day:
  pool         = focus_xiao_cao_index/get_code_list_v2 with groups="2" (qibao)
  enriched     = xiao_cao_index_v2 lookups merged across the day's chunks
  count:
    n_total          : pool ∩ enriched
    n_jssb_ge_200    : jssb ≥ STRONG_JW
    n_jssb_ge_150    : jssb ≥ QUALIFIED_JW (relaxed)
    n_pct_in_0_4     : pct ∈ (0, 4]
    n_pct_in_0_5     : pct ∈ (0, 5] (relaxed)
    n_not_limitup    : isLimitUp != 1
    n_active_main    : 三者联合 (jssb≥200, pct∈(0,4], !isLimitUp)
    n_active_relaxed_jssb : (jssb≥150, pct∈(0,4], !isLimitUp)
    n_active_relaxed_pct  : (jssb≥200, pct∈(0,5], !isLimitUp)
    n_active_relaxed_both : (jssb≥150, pct∈(0,5], !isLimitUp)

Decision tree at the bottom of the markdown:
  median(n_active_main) ≥ 5 / day → 联合精度 OK，问题在别处（mode signal 后置过滤）
  ≥ 5 only after relaxing jssb       → STRONG_JW=200 太严，建议 175 或 150
  ≥ 5 only after relaxing pct        → pct∈(0,4] 太严，建议 (0,5]
  需要双向放宽                       → 两个 threshold 都要松
  双向放宽都 < 5 / day               → 池子本身稀，需要换 pool 或换 mode

Usage:
  python3 scripts/diagnose_qibao_prevalence.py
Outputs:
  stdout: per-date table + summary
  output/diagnose_qibao_prevalence.md
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402

CACHE_PATH = ROOT / "output" / ".cache" / "xiaocao.db"
OUTPUT_MD = ROOT / "output" / "diagnose_qibao_prevalence.md"

STRONG_JW = 200       # 红盘起爆主攻
QUALIFIED_JW = 150    # 方向红盘起爆 / relaxed
PCT_HARD = 4.0
PCT_RELAXED = 5.0


def load_pool_by_date() -> dict[str, list[str]]:
    """{date_iso: [stockId,...]} — only groups='2' (qibao)."""
    out: dict[str, list[str]] = {}
    from xiaocao.api.cache import iter_cached_responses

    rows = iter_cached_responses(CACHE_PATH, "/stock/focus_xiao_cao_index/get_code_list_v2", include_params=True)
    for pj, data in rows:
        try:
            params = json.loads(pj).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        if str(params.get("groups")) != "2":
            continue
        date = str(params.get("date") or "")[:10]
        if not date:
            continue
        codes = data.get("data") if isinstance(data, dict) else None
        if isinstance(codes, list):
            out[date] = list(codes)
    return out


def load_enriched_by_date() -> dict[str, dict[str, dict]]:
    """{date_iso: {stockCode: detail_dict}} — merged across chunks."""
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    from xiaocao.api.cache import iter_cached_responses

    rows = iter_cached_responses(CACHE_PATH, "/stock/xiao_cao_index_v2", include_params=True)
    for pj, data in rows:
        try:
            params = json.loads(pj).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        date = str(params.get("date") or "")[:10]
        if not date:
            continue
        if isinstance(data, dict):
            for code, detail in data.items():
                if isinstance(detail, dict):
                    out[date][str(code)] = detail
    return dict(out)


def _pct(detail: dict) -> float:
    """Match rules.check_qibao precedence: entityPctChangeRate > pctChangeRate > pctChange."""
    for key in ("entityPctChangeRate", "pctChangeRate", "pctChange"):
        v = detail.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _num(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def evaluate(date: str, pool: list[str], enriched: dict[str, dict]) -> dict:
    """Counts for one date."""
    n_total = 0
    n_jssb_200 = 0
    n_jssb_150 = 0
    n_pct_4 = 0
    n_pct_5 = 0
    n_not_limitup = 0
    n_red = 0  # 0 < pct < 9.5 (strictly red 板, not 涨停)
    active_main = 0
    active_rj = 0
    active_rp = 0
    active_rb = 0
    examples_main: list[tuple[str, float, float]] = []  # (code, jssb, pct)

    for code in pool:
        d = enriched.get(code)
        if not d:
            continue
        n_total += 1
        jssb = _num(d.get("jssb"))
        pct = _pct(d)
        is_lu = _num(d.get("isLimitUp")) == 1
        not_lu = not is_lu

        if jssb >= STRONG_JW:
            n_jssb_200 += 1
        if jssb >= QUALIFIED_JW:
            n_jssb_150 += 1
        if 0 < pct <= PCT_HARD:
            n_pct_4 += 1
        if 0 < pct <= PCT_RELAXED:
            n_pct_5 += 1
        if not_lu:
            n_not_limitup += 1
        if 0 < pct < 9.5:
            n_red += 1

        # Joint (current rule + relaxations)
        if jssb >= STRONG_JW and 0 < pct <= PCT_HARD and not_lu:
            active_main += 1
            if len(examples_main) < 3:
                examples_main.append((code, jssb, pct))
        if jssb >= QUALIFIED_JW and 0 < pct <= PCT_HARD and not_lu:
            active_rj += 1
        if jssb >= STRONG_JW and 0 < pct <= PCT_RELAXED and not_lu:
            active_rp += 1
        if jssb >= QUALIFIED_JW and 0 < pct <= PCT_RELAXED and not_lu:
            active_rb += 1

    return {
        "date": date,
        "pool_size": len(pool),
        "n_total": n_total,
        "n_jssb_200": n_jssb_200,
        "n_jssb_150": n_jssb_150,
        "n_pct_4": n_pct_4,
        "n_pct_5": n_pct_5,
        "n_not_limitup": n_not_limitup,
        "n_red": n_red,
        "active_main": active_main,
        "active_relax_jssb": active_rj,
        "active_relax_pct": active_rp,
        "active_relax_both": active_rb,
        "examples_main": examples_main,
    }


def _stats(values: list[int]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "min": min(values),
        "p25": statistics.quantiles(values, n=4)[0] if len(values) >= 4 else min(values),
        "median": statistics.median(values),
        "p75": statistics.quantiles(values, n=4)[2] if len(values) >= 4 else max(values),
        "max": max(values),
        "mean": round(statistics.mean(values), 2),
        "sum": sum(values),
        "ge_5": sum(1 for v in values if v >= 5),
    }


def render_md(per_date: list[dict], summary: dict) -> str:
    lines: list[str] = []
    lines.append("# 红盘起爆主攻 prevalence 调研 (Plan A1)")
    lines.append("")
    lines.append(f"- Cache: `{CACHE_PATH.relative_to(ROOT)}`")
    lines.append(f"- Trading days analyzed: **{len(per_date)}**")
    lines.append(f"- STRONG_JW={STRONG_JW}, QUALIFIED_JW={QUALIFIED_JW}, PCT_HARD={PCT_HARD}, PCT_RELAXED={PCT_RELAXED}")
    lines.append("")
    lines.append("## Across-date stats (per-day counts)")
    lines.append("")
    lines.append("| metric | n_days | min | p25 | median | p75 | max | mean | sum | days≥5 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for key, label in [
        ("pool_size", "qibao pool size"),
        ("n_total", "pool ∩ enriched"),
        ("n_jssb_200", "jssb ≥ 200"),
        ("n_jssb_150", "jssb ≥ 150"),
        ("n_pct_4", "0 < pct ≤ 4"),
        ("n_pct_5", "0 < pct ≤ 5"),
        ("n_red", "0 < pct < 9.5 (any 红)"),
        ("active_main", "**ACTIVE main** (jssb≥200 + pct∈(0,4] + !LU)"),
        ("active_relax_jssb", "active relax jssb (≥150)"),
        ("active_relax_pct", "active relax pct (≤5)"),
        ("active_relax_both", "active relax both"),
    ]:
        s = summary[key]
        if not s.get("n"):
            lines.append(f"| {label} | 0 | – | – | – | – | – | – | – | – |")
        else:
            lines.append(
                f"| {label} | {s['n']} | {s['min']} | {s['p25']} | {s['median']} | "
                f"{s['p75']} | {s['max']} | {s['mean']} | {s['sum']} | {s['ge_5']} |"
            )
    lines.append("")

    lines.append("## Decision")
    lines.append("")
    main_med = summary["active_main"].get("median", 0)
    rj_med = summary["active_relax_jssb"].get("median", 0)
    rp_med = summary["active_relax_pct"].get("median", 0)
    rb_med = summary["active_relax_both"].get("median", 0)
    main_sum = summary["active_main"].get("sum", 0)

    lines.append(f"- median(active_main) = **{main_med}** / day, sum = **{main_sum}**")
    lines.append(f"- median(active_relax_jssb=150) = {rj_med} / day")
    lines.append(f"- median(active_relax_pct=5) = {rp_med} / day")
    lines.append(f"- median(active_relax_both) = {rb_med} / day")
    lines.append("")

    if main_med >= 5:
        verdict = "**A. 联合精度足够**：median ≥ 5 候选/天，prevalence 不是瓶颈。报告里 1 笔成交的原因在 candidates → mode_signal → trade 的下游链条（adaptive 阈值、score gate、direction 过滤等），不是 rule 本身。下一步：A2/A3 走完，再看 rules→trades 的转化率。"
    elif rj_med >= 5 and rp_med < 5:
        verdict = f"**B. STRONG_JW=200 太严**：放宽到 150 后 median {rj_med} 候选/天可用。建议把 红盘起爆主攻 的 jssb 门槛降到 175 或 150，配合现有 pct∈(0,4]。"
    elif rp_med >= 5 and rj_med < 5:
        verdict = f"**C. pct∈(0,4] 太严**：放宽到 (0,5] 后 median {rp_med} 候选/天可用。建议 pct 上限提到 5。"
    elif rb_med >= 5 and rj_med < 5 and rp_med < 5:
        verdict = f"**D. 单方放宽都不够，需要双向放宽**：jssb→150 + pct→(0,5] 后 median {rb_med}。建议两侧同时松。"
    else:
        verdict = f"**E. 池子本身稀**：所有 4 种 active 计数 median 都 < 5。问题不在 jssb / pct 阈值，在 qibao pool 来源（groups='2'）里达到任何 红盘+起爆 形态的样本就少。下一步要么换 pool 来源（如直接扫全市场 sortId=39），要么放弃这个 mode 在 1-day backtest 的位置。"

    lines.append(verdict)
    lines.append("")

    lines.append("## Per-date detail (first 30 days + last 10)")
    lines.append("")
    lines.append("| date | pool | enriched | jssb≥200 | pct∈(0,4] | active_main | active_rj | active_rp | active_rb |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    show = per_date[:30] + (per_date[-10:] if len(per_date) > 40 else [])
    seen = set()
    for r in show:
        if r["date"] in seen:
            continue
        seen.add(r["date"])
        lines.append(
            f"| {r['date']} | {r['pool_size']} | {r['n_total']} | {r['n_jssb_200']} | "
            f"{r['n_pct_4']} | **{r['active_main']}** | {r['active_relax_jssb']} | "
            f"{r['active_relax_pct']} | {r['active_relax_both']} |"
        )
    lines.append("")

    examples = []
    for r in per_date:
        for code, jssb, pct in r["examples_main"]:
            examples.append((r["date"], code, jssb, pct))
        if len(examples) >= 20:
            break
    if examples:
        lines.append("## Sample active_main candidates (up to 20)")
        lines.append("")
        lines.append("| date | code | jssb | pct |")
        lines.append("|---|---|---|---|")
        for date, code, jssb, pct in examples[:20]:
            lines.append(f"| {date} | {code} | {jssb:.1f} | {pct:.2f}% |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    if not CACHE_PATH.exists():
        sys.exit(f"Cache not found: {CACHE_PATH}")

    pool_by_date = load_pool_by_date()
    enriched_by_date = load_enriched_by_date()

    common = sorted(set(pool_by_date) & set(enriched_by_date))
    if not common:
        sys.exit("No overlapping dates between qibao pool cache and xiao_cao_index_v2 cache.")

    per_date = [
        evaluate(d, pool_by_date[d], enriched_by_date[d]) for d in common
    ]

    summary = {
        key: _stats([r[key] for r in per_date])
        for key in (
            "pool_size", "n_total", "n_jssb_200", "n_jssb_150", "n_pct_4", "n_pct_5",
            "n_red", "active_main", "active_relax_jssb", "active_relax_pct", "active_relax_both",
        )
    }

    md = render_md(per_date, summary)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(md, encoding="utf-8")

    print(f"Days analyzed: {len(per_date)}")
    print(f"Active main (median/day): {summary['active_main'].get('median', 0)}")
    print(f"Active main (sum): {summary['active_main'].get('sum', 0)}")
    print(f"Active relax-jssb median: {summary['active_relax_jssb'].get('median', 0)}")
    print(f"Active relax-pct median: {summary['active_relax_pct'].get('median', 0)}")
    print(f"Active relax-both median: {summary['active_relax_both'].get('median', 0)}")
    print(f"Wrote: {OUTPUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
