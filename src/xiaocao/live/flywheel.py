"""Flywheel self-check — verify the THREE coupled compounding loops are wired.

The system is three snowballs that feed each other (① produces data for ②, ②
produces validated edge for ③, ③ produces a stronger strategy back into ①):

① Capital flywheel (钱滚钱):  morning entries -> intraday staged exits -> eod
                   settle/digest. Depends on the deterministic spine + the
                   paper/real safety boundary + book A/B + kill-switch.
② Capability flywheel (经验滚经验): eod accumulates training_rows -> the
                   discipline-guarded research harness judges the pipeline ->
                   verdicts accrue in the knowledge ledger; already_refuted gates
                   re-recording dead directions. Compounds what the system knows.
③ Strategy flywheel (本事变强): a PASS verdict -> change a param (params.py, the
                   only edit path, frozen-guarded) or retrain a model -> a
                   stronger strategy tomorrow. This is the ACTUATOR leg; it is
                   intentionally a HUMAN gate today (auto-flipping params would
                   violate the train+test discipline) and on real data no
                   hypothesis PASSes, so it correctly idles. Reported honestly as
                   open/blocked/closed rather than drawn as a closed arc.

`check_flywheel()` returns a structured health report and is the engine behind
`scripts/flywheel_selfcheck.py`. It performs NO network I/O and never trades —
it only inspects wiring and accumulated artifacts. See docs/FLYWHEEL.md.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import date
from pathlib import Path
from typing import Any

from xiaocao.live import journal, safety
from xiaocao.research import guards as _guards  # noqa: F401  (import proves the harness is wired)
from xiaocao.research import ledger
from xiaocao.strategy import params


def _last_journal_date(path: Path) -> str | None:
    dates = [r.get("market_date") for r in journal.read_all(path) if r.get("market_date")]
    return max(dates) if dates else None


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


def _parquet_rows(path: Path) -> int | None:
    if not path.exists():
        return 0
    try:
        import pandas as pd
        return len(pd.read_parquet(path))
    except Exception:
        return None  # pandas missing or unreadable — unknown, not zero


def _max_jsonl_date(path: Path, key: str) -> str | None:
    """Freshest value of `key` across a jsonl file (skipping `#` comment + blank lines).
    Used for calibration-loop liveness."""
    if not path.exists():
        return None
    dates = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            v = json.loads(s).get(key)
        except json.JSONDecodeError:
            continue
        if v:
            dates.append(str(v))
    return max(dates) if dates else None


def _jsonl_entries(path: Path) -> list[dict]:
    """Parsed JSON records from a jsonl file, skipping `#` comment + blank lines."""
    out: list[dict] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out


def knowledge_scoreboard(root: Path, *, today: date | None = None) -> dict[str, Any]:
    """The ②-layer scoreboard: is the knowledge flywheel getting SMARTER, or just heavier?

    Counting raw lines hides the real failure mode — ingest outrunning grading. These
    ratios make it falsifiable: a candidate→tested ratio trending to zero, or an
    oldest-untested age climbing, is the 'append-only producer with no consumer' signal.
    Pure read of tracked artifacts; never gates (WARN-only upstream)."""
    today = today or date.today()
    distilled = root / "reference" / "experience" / "distilled"
    backlog = root / "reference" / "experience" / "xiaocao_hypotheses.jsonl"
    ledger_path = root / "kronos_screen" / "HYPOTHESES.jsonl"
    action_log = root / "reference" / "experience" / "distill_action_log.jsonl"

    transcripts = len(list(distilled.glob("*.json"))) if distilled.exists() else 0
    entries = _jsonl_entries(backlog)
    verdicts: dict[str, str] = {}
    for e in _jsonl_entries(ledger_path):
        if e.get("id") and e.get("verdict"):
            verdicts[str(e["id"])] = str(e["verdict"])

    def retired(e: dict) -> bool:
        return bool(e.get("retired_on")) or str(e.get("status", "")).startswith("retired")

    def passed(e: dict) -> bool:
        return verdicts.get(str(e.get("id"))) == "PASS" or e.get("last_verdict") == "PASS"

    def tested(e: dict) -> bool:
        # research touched it: a ledger verdict, a folded-in verdict, or a non-candidate status
        st = str(e.get("status", ""))
        return (str(e.get("id")) in verdicts or bool(e.get("last_verdict"))
                or st.startswith(("tested", "SHELVED", "evidence")) or retired(e))

    total = len(entries)
    assertions = sum(len(e.get("source_dates") or []) for e in entries)   # transcript-level mentions
    n_tested = sum(1 for e in entries if tested(e))
    n_passed = sum(1 for e in entries if passed(e))
    n_retired = sum(1 for e in entries if retired(e))
    untested = [e for e in entries if not tested(e)]
    recurrences = sorted(len(e.get("source_dates") or []) for e in entries)
    median_recurrence = (statistics.median(recurrences) if recurrences else 0)

    oldest_dates = [min(e.get("source_dates")) for e in untested if e.get("source_dates")]
    oldest_unscored = min(oldest_dates) if oldest_dates else None
    oldest_age_days = None
    if oldest_unscored:
        try:
            oldest_age_days = (today - date.fromisoformat(oldest_unscored)).days
        except (TypeError, ValueError):
            pass
    action_rows = _jsonl_entries(action_log)
    instrumentation_todos = [
        e for e in action_rows
        if str(e.get("instrumentation_todo", "")).strip().lower()
        not in {"", "none", "no_change", "not_applicable", "no_issue_created"}
    ]

    return {
        "transcripts_distilled": transcripts,
        "candidates_total": total,
        "candidate_assertions": assertions,             # sum of source_dates (pre-dedup mentions)
        "dedup_ratio": round(total / assertions, 2) if assertions else None,  # <1 = recurrence-merge working
        "candidates_tested": n_tested,
        "candidates_passed": n_passed,
        "candidates_retired": n_retired,
        "candidates_untested": len(untested),
        "candidate_to_tested": round(n_tested / total, 2) if total else None,
        "tested_to_pass": round(n_passed / n_tested, 2) if n_tested else None,
        "median_recurrence": median_recurrence,
        "oldest_untested": oldest_unscored,
        "oldest_untested_age_days": oldest_age_days,
        "action_log_rows": len(action_rows),
        "instrumentation_todos": len(instrumentation_todos),
    }


def _knowledge_warnings(k: dict[str, Any]) -> list[str]:
    """WARN-only: surface the 'ingest outruns grading' decay before it rots the flywheel."""
    w: list[str] = []
    total, c2t = k.get("candidates_total", 0), k.get("candidate_to_tested")
    if total >= 15 and c2t is not None and c2t < 0.25:
        w.append(f"KNOWLEDGE: backlog grading is falling behind ingest "
                 f"({k['candidates_tested']}/{total} tested = {c2t:.0%}) — run scripts/flywheel_sweep.py "
                 f"to prioritize/retire (ingest is outrunning the verdict rate)")
    age = k.get("oldest_untested_age_days")
    if age is not None and age > 30:
        w.append(f"KNOWLEDGE: oldest untested candidate is {age}d old (since {k['oldest_untested']}) — "
                 f"the backlog has a stale tail nothing is consuming")
    return w


def _automation_steps(auto_daily: Path) -> list[str]:
    if not auto_daily.exists():
        return []
    text = auto_daily.read_text(encoding="utf-8")
    # steps are the case labels: `morning)` `eod)` `optimize)` etc.
    return [m for m in ("morning", "eod", "optimize", "sweep", "weekly")
            if re.search(rf"^\s*{m}\)", text, re.MULTILINE)]


def _source_mentions(path: Path, token: str) -> bool:
    """Cheap wiring probe: does a script reference a symbol? Used to verify the
    capability runner actually consults already_refuted (not dead code)."""
    try:
        return token in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _applied_verdict_ids(path: Path) -> set[str]:
    """Verdicts that have already been consumed by a paper/simulation actuator.

    This is deliberately separate from the verdict ledger: PASS/REJECTED records
    answer "is the edge validated?", while this file answers "has that validated
    edge been wired into the exploratory paper/simulation layer yet?".
    """
    out: set[str] = set()
    for e in _jsonl_entries(path):
        hid = e.get("id")
        status = str(e.get("status", "applied")).lower()
        if hid and status in {"applied", "consumed"}:
            out.add(str(hid))
    return out


def _pending_pass_ids(ledger_path: Path, *, applied_path: Path | None = None) -> list[str]:
    """Hypotheses whose LATEST ledger verdict is PASS — a validated edge that the
    strategy flywheel should actuate. Empty today (K->P is REJECTED); a non-empty
    list with no actuator wired is a real gap, not a by-design idle."""
    latest: dict[str, str] = {}
    for e in ledger.read_all(ledger_path):
        hid = e.get("id")
        if hid is not None:
            latest[hid] = e.get("verdict")
    applied = _applied_verdict_ids(applied_path) if applied_path else set()
    return [hid for hid, v in latest.items() if v == "PASS" and hid not in applied]


def check_flywheel(
    *,
    root: Path,
    env: dict[str, str] | None = None,
    auth_path: Path | None = None,
) -> dict[str, Any]:
    live = root / "output" / "live"
    auth_path = auth_path if auth_path is not None else (live / "live_authorization.json")

    # --- capital flywheel: safety boundary must hold paper-only ------------- #
    decision = safety.authorize_capital_action(
        kind="real_capital", side="BUY", code="000001.XSHG", notional=1.0,
        auth_path=auth_path, audit_path=None, env=env if env is not None else {},
    )
    paper_only = not decision.allowed
    steps = _automation_steps(root / "scripts" / "auto_daily.sh")

    capital = {
        "safety_paper_only": paper_only,
        "safety_reason": decision.reason,
        "automation_steps": steps,
        "automation_complete": {"morning", "eod"}.issubset(set(steps)),
        "journal_entries": _count_lines(live / "decision_journal.jsonl"),
        "last_journal_date": _last_journal_date(live / "decision_journal.jsonl"),
        "book_a_present": (live / "paper_account_A.json").exists(),
        "book_b_present": (live / "paper_account.json").exists(),
    }
    capital["status"] = "spinning" if (paper_only and capital["automation_complete"]) else "broken"

    # --- ② capability flywheel: data -> guards -> ledger -------------------- #
    ledger_path = root / "kronos_screen" / "HYPOTHESES.jsonl"
    capability = {
        "training_rows": _parquet_rows(live / "training_rows.parquet"),
        "ledger_entries": _count_lines(ledger_path),
        "optimize_step_wired": "optimize" in steps,
        "guards_importable": True,  # imported at module load; reaching here proves it
        # already_refuted is load-bearing only if the runner actually consults it:
        "already_refuted_wired": _source_mentions(
            root / "scripts" / "continuous_optimize.py", "already_refuted"),
    }
    capability["status"] = (
        "wired" if (capability["optimize_step_wired"] and capability["guards_importable"]) else "broken"
    )

    # --- calibration loops (judgment-layer learning, part of ②) ------------- #
    # The posture + exit calibration sensors score deterministic decisions against the
    # realized forward outcome and stage falsifiable candidates for the human gate. They
    # used to be sidecars the self-check was blind to; now they are a MONITORED leg, so a
    # silent break (unwired step / stalled scorer) surfaces as a WARNING. They are
    # sensor-only — never a critical gate (a broken sensor must not halt the capital loop).
    auto_daily = root / "scripts" / "auto_daily.sh"
    calibration = {
        "posture_score_wired": _source_mentions(auto_daily, "posture_calibration.py"),
        "exit_score_wired": _source_mentions(auto_daily, "exit_calibration.py"),
        "distill_wired": _source_mentions(auto_daily, "--distill"),
        "sweep_wired": _source_mentions(auto_daily, "flywheel_sweep.py"),  # the backlog CONSUMER
        "posture_recorded": _count_lines(live / "posture_calls.jsonl"),
        "posture_scored": _count_lines(live / "posture_calibration.jsonl"),
        "posture_last_recorded": _max_jsonl_date(live / "posture_calls.jsonl", "date"),
        "exit_recorded": _count_lines(live / "exit_calls.jsonl"),
        "exit_scored": _count_lines(live / "exit_calibration.jsonl"),
        "candidates_staged": _count_lines(live / "calibration_candidates.jsonl"),
    }
    calibration["wired"] = calibration["posture_score_wired"] and calibration["exit_score_wired"]
    capability["calibration"] = calibration

    # --- ③ strategy flywheel: PASS -> param change / retrain (ACTUATOR) ----- #
    # The actuator leg is intentionally a human gate today. It is "open" (idle by
    # design) when no PASS is pending, "blocked" (a real gap) if a validated edge
    # exists but nothing can apply it, and "closed" only once an actuator is wired.
    actuator_wired = (root / "scripts" / "apply_verdict.py").exists()
    applied_path = root / "reference" / "experience" / "applied_verdicts.jsonl"
    applied_pass = sorted(_applied_verdict_ids(applied_path))
    pending_pass = _pending_pass_ids(ledger_path, applied_path=applied_path)
    params_frozen = all(p.frozen for p in params.REGISTRY.values())
    if actuator_wired:
        strat_status = "closed"
    elif pending_pass:
        strat_status = "blocked"
    else:
        strat_status = "open"  # by design: human gate, nothing validated to apply
    strategy = {
        "actuator_wired": actuator_wired,
        "params_frozen": params_frozen,
        "applied_pass_verdicts": applied_pass,
        "pending_pass_verdicts": pending_pass,
        "status": strat_status,
        "note": "PASS→纸面/模拟改动可以由 weekly 自动审计落地；实盘/核心参数仍受人工门和冻结约束",
    }

    # --- the three-ring coupling: does ① feed ② feed ③ feed ① ? ------------- #
    tr = capability["training_rows"]
    rings = {
        "capital_to_capability": bool(capital["automation_complete"]) and tr != 0 and capital["journal_entries"] > 0,
        "capability_to_strategy": len(pending_pass) > 0,   # a validated edge to pass on
        "strategy_to_capital": actuator_wired,
    }
    rings["fully_closed"] = all(rings.values())

    # spinning = the OPERATIONAL loops (① + ②) turn each day. The actuator (③) is a
    # deliberate human gate, so its open state does NOT make the system "not wired".
    critical = [
        capital["safety_paper_only"],          # never trade real money by accident
        capital["automation_complete"],         # the daily loop is wired
        capability["optimize_step_wired"],      # the capability loop is wired
        capability["guards_importable"],
    ]
    knowledge = knowledge_scoreboard(root)
    return {
        "capital_flywheel": capital,
        "capability_flywheel": capability,
        "strategy_flywheel": strategy,
        "knowledge": knowledge,
        "rings": rings,
        "spinning": all(critical),
        "warnings": _warnings(capital, capability, strategy) + _knowledge_warnings(knowledge),
    }


def _warnings(capital: dict[str, Any], capability: dict[str, Any], strategy: dict[str, Any]) -> list[str]:
    w: list[str] = []
    if not capital["safety_paper_only"]:
        w.append("CRITICAL: real-capital action is NOT blocked — live trading may be enabled")
    if not capital["automation_complete"]:
        w.append("capital flywheel incomplete: auto_daily.sh missing morning/eod step")
    if not capability["optimize_step_wired"]:
        w.append("capability flywheel not wired: auto_daily.sh missing `optimize` step")
    tr = capability["training_rows"]
    if tr == 0:
        w.append("no accumulated training_rows yet — capability flywheel has no data to judge")
    elif tr is None:
        w.append("training_rows present but unreadable here (pandas unavailable)")
    if capital["journal_entries"] == 0:
        w.append("decision journal empty — runs are not yet recording structured decisions")
    # STRATEGY: a validated edge with nowhere to go is a real gap (not by-design idle).
    if strategy["status"] == "blocked":
        w.append(
            f"STRATEGY: {len(strategy['pending_pass_verdicts'])} PASS verdict(s) pending "
            f"({', '.join(strategy['pending_pass_verdicts'])}) but no actuator wired "
            f"(scripts/apply_verdict.py) — a validated edge is not being applied"
        )
    # LIVENESS: wiring can be intact while the loop has silently stopped running.
    lj = capital.get("last_journal_date")
    if lj:
        try:
            gap = (date.today() - date.fromisoformat(lj)).days
            if gap > 5:
                w.append(f"LIVENESS: newest decision-journal entry is {lj} ({gap}d old) — the loop may have stalled")
        except (TypeError, ValueError):
            pass
    # CALIBRATION (judgment-layer learning) — WARN only, never gates the capital loop.
    cal = capability.get("calibration", {})
    if not cal.get("wired", True):
        w.append("CALIBRATION: not wired — auto_daily.sh eod missing posture/exit_calibration "
                 "--score (the judgment-calibration loop won't compound)")
    elif not cal.get("distill_wired", True):
        w.append("CALIBRATION: scoring wired but --distill is not — flagged rules won't reach the "
                 "candidate backlog / human gate")
    elif not cal.get("sweep_wired", True):
        w.append("KNOWLEDGE: the backlog CONSUMER is not scheduled — auto_daily.sh missing "
                 "flywheel_sweep.py (candidates accrete with nothing ranking/retiring them)")
    pl = cal.get("posture_last_recorded")
    if pl:  # posture records every trading day, so staleness => the scorer stalled
        try:
            gap = (date.today() - date.fromisoformat(pl)).days
            if gap > 7:
                w.append(f"CALIBRATION LIVENESS: posture last recorded {pl} ({gap}d old) — the "
                         f"judgment-calibration loop may have stalled")
        except (TypeError, ValueError):
            pass
    return w
