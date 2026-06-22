#!/usr/bin/env python3
"""Xiaocao knowledge surfacing + freshness self-check (read-only governance).

The distilled 小草 knowledge layer (playbook / regime timeline / candidate
hypotheses / verdict ledger) only COMPOUNDS if it is (a) discoverable, (b)
surfaced at the right moment, and (c) flagged when stale. This script is the
single entry point that does all three — it reads, never writes, and never
touches the deterministic spine.

Usage:
    python3 scripts/xiaocao_knowledge.py             # full digest
    python3 scripts/xiaocao_knowledge.py --posture   # compact posture prior (morning surface)
    python3 scripts/xiaocao_knowledge.py --check      # exit 1 if posture prior is STALE (for automation)

Consumed by: auto_daily.sh (morning surfaces posture, eod flags staleness),
and any agent following .codex/skills/xiaocao-trading/SKILL.md. See
reference/experience/README.md for the knowledge-base index.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTURE = ROOT / "reference/experience/posture_current.json"
HYPS = ROOT / "reference/experience/xiaocao_hypotheses.jsonl"
LEDGER = ROOT / "kronos_screen/HYPOTHESES.jsonl"
PLAYBOOK = ROOT / "docs/XIAOCAO_PLAYBOOK.md"
TIMELINE = ROOT / "reference/experience/REGIME_TIMELINE.md"


def _today() -> _dt.date:
    return _dt.date.today()


def _load_posture() -> dict | None:
    if not POSTURE.exists():
        return None
    return json.loads(POSTURE.read_text(encoding="utf-8"))


def _staleness(posture: dict) -> tuple[bool, int]:
    """Return (is_stale, days_past_valid_until)."""
    try:
        vu = _dt.date.fromisoformat(str(posture.get("valid_until", "")))
    except ValueError:
        return True, 0
    delta = (_today() - vu).days
    return delta > 0, delta


def _load_hyps() -> list[dict]:
    if not HYPS.exists():
        return []
    out = []
    for line in HYPS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(json.loads(line))
    return out


def _load_verdicts() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def render_posture(posture: dict | None, compact: bool = False) -> str:
    if not posture:
        return "现行 posture 先验：缺失（无 posture_current.json）— 按纯 live data 决策。"
    stale, days = _staleness(posture)
    tag = f"⚠ STALE（已过期 {days} 天，需重蒸馏新转录）" if stale else f"current（valid_until {posture.get('valid_until')}）"
    lines = [
        f"小草 posture 先验 [{tag}] · as_of {posture.get('as_of')} · regime={posture.get('regime')}",
        f"  风格：{posture.get('dominant_style')}",
    ]
    if not compact:
        lines.append(f"  方向排序：{' > '.join(posture.get('style_ranking', []))}")
        lines.append(f"  龙头：{', '.join(posture.get('leaders', []))} · 风向标：{posture.get('watch_flag','')}")
        lines.append(f"  时间轴：{posture.get('time_horizon','')}")
        lines.append("  失效条件（任一触发即减仓/离场）：")
        for f in posture.get("falsifiers", []):
            lines.append(f"    - {f}")
    lines.append("  ⓘ 判断先验，仅供 agent 判断/叙述，不进脊柱、不自动改参。")
    return "\n".join(lines)


def render_hyps(hyps: list[dict], verdicts: list[dict]) -> str:
    if not hyps:
        return "候选假设账本：空。"
    cand = [h for h in hyps if str(h.get("status", "")).startswith("candidate")]
    tested = [h for h in hyps if str(h.get("status", "")).startswith("tested")]
    cand.sort(key=lambda h: -int(h.get("priority", 0)))
    lines = [f"候选假设账本（reference/experience/xiaocao_hypotheses.jsonl）：{len(cand)} candidate / {len(tested)} tested"]
    lines.append("  待操作化（按 priority，top 5）：")
    for h in cand[:5]:
        lines.append(f"    - [{h.get('priority')}] {h.get('id')} ({h.get('category')}): {str(h.get('claim',''))[:70]}…")
    if tested:
        lines.append("  已测：" + ", ".join(f"{h.get('id')}={h.get('status').split(':')[-1]}" for h in tested))
    if verdicts:
        v = {x.get("id"): x.get("verdict") for x in verdicts}
        lines.append(f"  verdict 账本（kronos_screen/HYPOTHESES.jsonl）：{len(verdicts)} 条 — " +
                     ", ".join(f"{k}={vv}" for k, vv in v.items()))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--posture", action="store_true", help="compact posture prior only (morning surface)")
    ap.add_argument("--check", action="store_true", help="exit 1 if posture prior is STALE")
    a = ap.parse_args()

    posture = _load_posture()

    if a.check:
        if not posture:
            print("xiaocao-knowledge: 缺 posture_current.json — 视为 STALE")
            raise SystemExit(1)
        stale, days = _staleness(posture)
        if stale:
            print(f"xiaocao-knowledge: posture 先验 STALE（过期 {days} 天，需重蒸馏新转录并更新 posture_current.json）")
            raise SystemExit(1)
        print(f"xiaocao-knowledge: posture 先验 current（valid_until {posture.get('valid_until')}）")
        return

    if a.posture:
        print(render_posture(posture, compact=True))
        return

    print("=" * 72)
    print("小草知识层 · 现状一览（read-only；索引见 reference/experience/README.md）")
    print("=" * 72)
    print(render_posture(posture))
    print()
    print(render_hyps(_load_hyps(), _load_verdicts()))
    print()
    print(f"判断手册：{PLAYBOOK.relative_to(ROOT)}（道-法-术-纪律 + 实时盘面判断表）")
    print(f"posture 时间线：{TIMELINE.relative_to(ROOT)}（逐日 + 现行 posture + 回测提醒）")


if __name__ == "__main__":
    main()
