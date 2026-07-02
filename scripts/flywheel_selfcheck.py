"""Verify the THREE coupled compounding flywheels are wired and turning.

No network, never trades — inspects wiring + accumulated artifacts and reports
health. ① capital (钱滚钱) and ② capability (经验滚经验) turn each day; ③ strategy
(本事变强) is the actuator leg — an intentional human gate, reported honestly as
open/blocked/closed rather than drawn as a closed arc. Exits non-zero only if an
OPERATIONAL (① / ②) critical check fails (so it can gate automations).
See docs/FLYWHEEL.md.

    python3 scripts/flywheel_selfcheck.py
    python3 scripts/flywheel_selfcheck.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import flywheel, notify  # noqa: E402


def maybe_escalate_blocked(report: dict, env: dict, *, poster=None) -> dict | None:
    """Escalate when ③ strategy is BLOCKED — a validated edge (a PASS verdict) is
    pending with NO actuator wired, so the system has learned something it cannot
    apply. This is a real anomaly, not by-design idle: it needs a HUMAN decision
    (apply via strategy/params.py / retrain, under the train+test guard) — the
    agent must NEVER auto-change a param. Pushes a WeCom alert (no-op without a
    relay config). Returns the notify result, or None when not blocked."""
    strat = report.get("strategy_flywheel", {})
    if strat.get("status") != "blocked":
        return None
    ids = strat.get("pending_pass_verdicts") or []
    title = "③ 策略飞轮 BLOCKED — 有验证过的 edge 待人工应用"
    body = (
        f"PASS pending: {', '.join(ids) or '(?)'}。某假设已过纪律护栏，但 actuator 未接线"
        f"(scripts/apply_verdict.py 不存在)。人工决定是否经 strategy/params.py 改参/重训"
        f"(受 train+test 双改善 guard)；agent 不得自动改参。"
    )
    return notify.notify(title, body, env=env, poster=poster)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--notify-blocked", action="store_true",
                    help="push a WeCom escalation if the strategy flywheel is BLOCKED")
    a = ap.parse_args()

    report = flywheel.check_flywheel(root=ROOT, env=dict(os.environ))

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        cap, capa, strat = (
            report["capital_flywheel"], report["capability_flywheel"], report["strategy_flywheel"])
        rings = report["rings"]
        cap_dot = "🟢" if cap["status"] == "spinning" else "🔴"
        capa_dot = "🟢" if capa["status"] == "wired" else "🔴"
        strat_dot = {"closed": "🟢", "open": "🟡", "blocked": "🔴"}[strat["status"]]

        print(f"flywheels: {'🟢 OPERATIONAL' if report['spinning'] else '🔴 NOT WIRED'} "
              f"(① 资金 / ② 能力 自动转；③ 策略 = 人工门)  大环闭合: {rings['fully_closed']}")
        print(f"{cap_dot} ① capital flywheel (钱滚钱):")
        print(f"     safety paper-only : {cap['safety_paper_only']}  ({cap['safety_reason']})")
        print(f"     automation steps  : {', '.join(cap['automation_steps']) or 'none'}")
        print(f"     decision journal  : {cap['journal_entries']} entries")
        print(f"     book A / book B   : {cap['book_a_present']} / {cap['book_b_present']}")
        print(f"{capa_dot} ② capability flywheel (经验滚经验):")
        print(f"     training rows     : {capa['training_rows']}")
        print(f"     ledger verdicts   : {capa['ledger_entries']}")
        print(f"     optimize wired    : {capa['optimize_step_wired']}")
        print(f"     already_refuted   : {capa['already_refuted_wired']} (runner consults the ledger)")
        cal = capa.get("calibration", {})
        cal_dot = "🟢" if cal.get("wired") else "🔴"
        print(f"{cal_dot} ②b calibration loops (判断层校准 — sensor-only, → human gate):")
        print(f"     posture / exit    : scored {cal.get('posture_scored', 0)} / {cal.get('exit_scored', 0)}"
              f"  (recorded {cal.get('posture_recorded', 0)} / {cal.get('exit_recorded', 0)})")
        print(f"     distill wired     : {cal.get('distill_wired', False)}  | "
              f"candidates staged : {cal.get('candidates_staged', 0)} (promote → research → §10)")
        print(f"     consumer (sweep)  : {cal.get('sweep_wired', False)}  (backlog ranked/retired by flywheel_sweep.py)")
        print(f"{strat_dot} ③ strategy flywheel (本事变强) — {strat['status']}:")
        print(f"     actuator wired    : {strat['actuator_wired']}  (PASS→改参/重训)")
        print(f"     PASS pending      : {strat['pending_pass_verdicts'] or 'none'}")
        print(f"     {strat['note']}")
        k = report.get("knowledge", {})
        c2t, t2p = k.get("candidate_to_tested"), k.get("tested_to_pass")
        getting_smarter = "🟢 smarter" if (c2t or 0) >= 0.25 else "🟡 heavier"
        c2t_s = f"{c2t:.0%}" if c2t is not None else "—"
        t2p_s = f"{t2p:.0%}" if t2p is not None else "—"
        age = k.get("oldest_untested_age_days")
        oldest_s = (k.get("oldest_untested") or "—") + (f" ({age}d)" if age is not None else "")
        print(f"📊 knowledge scoreboard (② 判断层是否在变聪明,不只是变重): {getting_smarter}")
        print(f"     transcripts/cands : {k.get('transcripts_distilled')} distilled / "
              f"{k.get('candidates_total')} candidates ({k.get('candidate_assertions')} mentions, "
              f"dedup {k.get('dedup_ratio')})")
        print(f"     candidate→tested  : {k.get('candidates_tested')}/{k.get('candidates_total')} = {c2t_s}"
              f"   tested→PASS: {k.get('candidates_passed')}/{k.get('candidates_tested')} = {t2p_s}")
        print(f"     retired / untested: {k.get('candidates_retired')} retired / "
              f"{k.get('candidates_untested')} untested  | median recurrence "
              f"{k.get('median_recurrence')}  | oldest untested {oldest_s}")
        print(f"     action log / todo : {k.get('action_log_rows', 0)} rows / "
              f"{k.get('instrumentation_todos', 0)} instrumentation todo(s)")
        print(f"three-ring coupling : ①→② {rings['capital_to_capability']} | "
              f"②→③ {rings['capability_to_strategy']} | ③→① {rings['strategy_to_capital']}")
        for w in report["warnings"]:
            print(f"  ⚠ {w}")

    if a.notify_blocked:
        res = maybe_escalate_blocked(report, dict(os.environ))
        if res is not None:
            print(f"strategy BLOCKED — escalation pushed: {res}")

    raise SystemExit(0 if report["spinning"] else 1)


if __name__ == "__main__":
    main()
