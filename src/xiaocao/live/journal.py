"""Structured decision journal — durable, append-only audit + cross-context continuity.

Each automation run (morning / intraday monitor / eod) appends ONE structured
record to output/live/decision_journal.jsonl. A fresh-context agent waking at
14:55 reads the journal to learn what earlier runs concluded — instead of
re-deriving the day from seven scattered files. Borrowed from QuantDinger's
agent audit trail, realized as lightweight jsonl (no Postgres). See
docs/OPERATING_CONTRACT.md §2.

A record separates what the **deterministic spine** decided from the **agent
cortex** judgment, so the two are never conflated:

    {
      "run_id", "ts", "automation", "market_date", "state_hash",
      "deterministic": {...},     # what the spine computed (sells, holdings, ...)
      "posture": {...},           # market regime inputs the spine observed
      "agent_judgment": {...}|None,  # posture call / anomaly triage (agent-written)
      "anomalies": [...],
      "actions": [...],
    }
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_PATH = Path("output/live/decision_journal.jsonl")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def state_hash(payload: Any) -> str:
    """Short, stable digest of the state a decision acted on (for dedupe/audit)."""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def append_decision(
    *,
    automation: str,
    market_date: str,
    deterministic: dict[str, Any] | None = None,
    posture: dict[str, Any] | None = None,
    agent_judgment: dict[str, Any] | None = None,
    anomalies: list[Any] | None = None,
    actions: list[Any] | None = None,
    run_id: str | None = None,
    ts: str | None = None,
    path: Path = DEFAULT_JOURNAL_PATH,
) -> dict[str, Any]:
    """Append one structured decision record; returns it. Never raises on a
    failed write (auditing must not crash the trading loop)."""
    ts = ts or _now_iso()
    deterministic = deterministic or {}
    record = {
        "run_id": run_id or f"{automation}:{market_date}:{ts}",
        "ts": ts,
        "automation": automation,
        "market_date": market_date,
        "state_hash": state_hash(deterministic.get("positions", deterministic)),
        "deterministic": deterministic,
        "posture": posture or {},
        "agent_judgment": agent_judgment,
        "anomalies": anomalies or [],
        "actions": actions or [],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass
    return record


def read_all(path: Path = DEFAULT_JOURNAL_PATH) -> list[dict[str, Any]]:
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


def read_recent(n: int = 20, *, path: Path = DEFAULT_JOURNAL_PATH) -> list[dict[str, Any]]:
    return read_all(path)[-n:]


def read_for_date(market_date: str, *, path: Path = DEFAULT_JOURNAL_PATH) -> list[dict[str, Any]]:
    return [r for r in read_all(path) if r.get("market_date") == market_date]


def latest(
    *,
    automation: str | None = None,
    market_date: str | None = None,
    path: Path = DEFAULT_JOURNAL_PATH,
) -> dict[str, Any] | None:
    """Most recent record matching the optional automation / market_date filters.

    Used by a fresh-context agent: e.g. `latest(market_date=today)` to see what
    the morning run concluded before acting at the close.
    """
    for r in reversed(read_all(path)):
        if automation is not None and r.get("automation") != automation:
            continue
        if market_date is not None and r.get("market_date") != market_date:
            continue
        return r
    return None
