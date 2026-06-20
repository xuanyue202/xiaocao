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

import re
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


def _automation_steps(auto_daily: Path) -> list[str]:
    if not auto_daily.exists():
        return []
    text = auto_daily.read_text(encoding="utf-8")
    # steps are the case labels: `morning)` `eod)` `optimize)`
    return [m for m in ("morning", "eod", "optimize") if re.search(rf"^\s*{m}\)", text, re.MULTILINE)]


def _source_mentions(path: Path, token: str) -> bool:
    """Cheap wiring probe: does a script reference a symbol? Used to verify the
    capability runner actually consults already_refuted (not dead code)."""
    try:
        return token in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _pending_pass_ids(ledger_path: Path) -> list[str]:
    """Hypotheses whose LATEST ledger verdict is PASS — a validated edge that the
    strategy flywheel should actuate. Empty today (K->P is REJECTED); a non-empty
    list with no actuator wired is a real gap, not a by-design idle."""
    latest: dict[str, str] = {}
    for e in ledger.read_all(ledger_path):
        hid = e.get("id")
        if hid is not None:
            latest[hid] = e.get("verdict")
    return [hid for hid, v in latest.items() if v == "PASS"]


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

    # --- ③ strategy flywheel: PASS -> param change / retrain (ACTUATOR) ----- #
    # The actuator leg is intentionally a human gate today. It is "open" (idle by
    # design) when no PASS is pending, "blocked" (a real gap) if a validated edge
    # exists but nothing can apply it, and "closed" only once an actuator is wired.
    actuator_wired = (root / "scripts" / "apply_verdict.py").exists()
    pending_pass = _pending_pass_ids(ledger_path)
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
        "pending_pass_verdicts": pending_pass,
        "status": strat_status,
        "note": "PASS→改参/重训目前是人工门(受 strategy/params.py 冻结约束)；尚未自动闭环",
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
    return {
        "capital_flywheel": capital,
        "capability_flywheel": capability,
        "strategy_flywheel": strategy,
        "rings": rings,
        "spinning": all(critical),
        "warnings": _warnings(capital, capability, strategy),
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
    return w
