"""Flywheel self-check — verify both compounding loops are wired and able to spin.

Capital flywheel:  morning entries -> intraday staged exits -> eod settle/digest.
                   Compounds money; depends on the deterministic spine + the
                   paper/real safety boundary + book A/B + kill-switch.
Capability flywheel: eod accumulates training_rows -> the discipline-guarded
                   research harness judges the pipeline -> verdicts accrue in the
                   knowledge ledger -> gated retrain. Compounds what the system
                   has learned.

`check_flywheel()` returns a structured health report and is the engine behind
`scripts/flywheel_selfcheck.py`. It performs NO network I/O and never trades —
it only inspects wiring and accumulated artifacts. See docs/FLYWHEEL.md.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from xiaocao.live import safety
from xiaocao.research import guards as _guards  # noqa: F401  (import proves the harness is wired)


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
        "book_a_present": (live / "paper_account_A.json").exists(),
        "book_b_present": (live / "paper_account.json").exists(),
    }

    # --- capability flywheel: data -> guards -> ledger ---------------------- #
    capability = {
        "training_rows": _parquet_rows(live / "training_rows.parquet"),
        "ledger_entries": _count_lines(root / "kronos_screen" / "HYPOTHESES.jsonl"),
        "optimize_step_wired": "optimize" in steps,
        "guards_importable": True,  # imported at module load; reaching here proves it
    }

    # --- overall: can it spin? --------------------------------------------- #
    critical = [
        capital["safety_paper_only"],          # never trade real money by accident
        capital["automation_complete"],         # the daily loop is wired
        capability["optimize_step_wired"],      # the capability loop is wired
        capability["guards_importable"],
    ]
    return {
        "capital_flywheel": capital,
        "capability_flywheel": capability,
        "spinning": all(critical),
        "warnings": _warnings(capital, capability),
    }


def _warnings(capital: dict[str, Any], capability: dict[str, Any]) -> list[str]:
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
    return w
