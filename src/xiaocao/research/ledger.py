"""Knowledge ledger — structured record of every hypothesis the harness judged.

Append-only kronos_screen/HYPOTHESES.jsonl: the executable successor to
STATE.md's hand-written research log. Verdicts are durable and queryable, so the
capability flywheel re-evaluates a direction as data grows but does not re-litigate
a settled one by hand: continuous_optimize consults `already_refuted`/`find` and
appends only when the verdict CHANGES (the ledger is a changelog, not a heartbeat).
A new hypothesis can declare `supersedes` to mark which prior entry it revises.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Anchored to the repo root (src/xiaocao/research/ledger.py -> parents[3]) so the
# capability flywheel writes to the same ledger regardless of the caller's cwd.
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[3] / "kronos_screen" / "HYPOTHESES.jsonl"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _round(value: Any, digits: int = 6) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _metrics_from_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    """Summarize both short-line and trend guard verdicts for the ledger."""
    sig = verdict.get("significance", {})
    if "compounded" in verdict:
        comp = verdict.get("compounded", {})
        per_hold = verdict.get("per_hold", {})
        wf = verdict.get("walk_forward", {})
        non_bull = verdict.get("non_bull", {})
        return {
            "n_holds": verdict.get("n_holds"),
            "compounded_strat": _round(comp.get("strat", 0.0)),
            "compounded_base": _round(comp.get("base", 0.0)),
            "compounded_alpha": _round(comp.get("alpha", 0.0)),
            "max_drawdown": _round(verdict.get("max_drawdown", 0.0)),
            "turnover": _round(verdict.get("turnover", 0.0)),
            "per_hold_alpha_mean": _round(per_hold.get("alpha_mean", 0.0)),
            "per_hold_win": _round(per_hold.get("win", 0.0)),
            "train_alpha": _round(wf.get("train_alpha", 0.0)),
            "test_alpha": _round(wf.get("test_alpha", 0.0)),
            "non_bull_holds": non_bull.get("n_holds"),
            "non_bull_alpha_mean": _round(non_bull.get("alpha_mean", 0.0)),
            "p": _round(sig.get("p", 1.0)),
            "effective_alpha": sig.get("effective_alpha"),
        }
    pt = verdict.get("per_trade", {})
    wf = verdict.get("walk_forward", {})
    return {
        "n_trades": verdict.get("n_trades"),
        "n_days": verdict.get("n_days"),
        "per_trade_spread": _round(pt.get("spread", 0.0)),
        "train_edge": _round(wf.get("train_edge", 0.0)),
        "test_edge": _round(wf.get("test_edge", 0.0)),
        "p": _round(sig.get("p", 1.0)),
        "effective_alpha": sig.get("effective_alpha"),
    }


def record_hypothesis(
    *,
    hypothesis_id: str,
    claim: str,
    method: str,
    verdict: dict[str, Any],
    n_tried: int = 1,
    supersedes: str | None = None,
    ts: str | None = None,
    path: Path = DEFAULT_LEDGER_PATH,
) -> dict[str, Any]:
    """Distil a guards verdict into a ledger entry and append it. Returns it."""
    entry = {
        "id": hypothesis_id,
        "ts": ts or _now_iso(),
        "claim": claim,
        "method": method,
        "verdict": verdict.get("verdict"),
        "rejected_by": verdict.get("rejected_by", []),
        "metrics": _metrics_from_verdict(verdict),
        "n_tried": n_tried,
        "supersedes": supersedes,
        "warnings": verdict.get("warnings", []),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    except OSError as exc:
        # Surface (don't silently swallow): a lost verdict means the capability
        # flywheel stopped recording, which must be visible in the eod log.
        print(f"ledger: FAILED to record verdict to {path}: {exc}", file=sys.stderr)
    return entry


def read_all(path: Path = DEFAULT_LEDGER_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def find(hypothesis_id: str, *, path: Path = DEFAULT_LEDGER_PATH) -> list[dict[str, Any]]:
    return [e for e in read_all(path) if e.get("id") == hypothesis_id]


def already_refuted(hypothesis_id: str, *, path: Path = DEFAULT_LEDGER_PATH) -> bool:
    """True if the most recent verdict for this id was REJECTED — so the agent
    can skip re-running a dead direction. Latest entry wins (it may supersede)."""
    entries = find(hypothesis_id, path=path)
    if not entries:
        return False
    return entries[-1].get("verdict") == "REJECTED"
