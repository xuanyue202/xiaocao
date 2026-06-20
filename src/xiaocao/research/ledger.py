"""Knowledge ledger — structured record of every hypothesis the harness judged.

Append-only kronos_screen/HYPOTHESES.jsonl: the executable successor to
STATE.md's hand-written research log. Because verdicts are durable and queryable,
the system never re-litigates a refuted idea — it compounds what it has learned.
A new hypothesis can declare `supersedes` to mark which prior entry it revises.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_PATH = Path("kronos_screen/HYPOTHESES.jsonl")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
    pt = verdict.get("per_trade", {})
    wf = verdict.get("walk_forward", {})
    sig = verdict.get("significance", {})
    entry = {
        "id": hypothesis_id,
        "ts": ts or _now_iso(),
        "claim": claim,
        "method": method,
        "verdict": verdict.get("verdict"),
        "rejected_by": verdict.get("rejected_by", []),
        "metrics": {
            "n_trades": verdict.get("n_trades"),
            "n_days": verdict.get("n_days"),
            "per_trade_spread": round(float(pt.get("spread", 0.0)), 6),
            "train_edge": round(float(wf.get("train_edge", 0.0)), 6),
            "test_edge": round(float(wf.get("test_edge", 0.0)), 6),
            "p": round(float(sig.get("p", 1.0)), 6),
            "effective_alpha": sig.get("effective_alpha"),
        },
        "n_tried": n_tried,
        "supersedes": supersedes,
        "warnings": verdict.get("warnings", []),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass
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
