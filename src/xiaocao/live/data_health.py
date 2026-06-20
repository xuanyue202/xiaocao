"""Data-health doctor — guard the flywheel's honesty against dirty data.

The real data hazard for xiaocao is not "the proprietary API is down" (that is
unavoidable for the core signal, and cache-first already covers history) — it is
**dirty data silently faking the evaluation**. The 06-01 triple-snapshot bug made
the A/B verdict meaningless ("-0.49 vs -1.01 cushion 是脏数据假象"). This module
catches that class of problem offline, so the compounding loop never learns from
a 真的谎言. Used by scripts/data_doctor.py and surfaced in the daily digest.

Each check returns findings: {"check", "severity" (info|warn|critical), "detail"}.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def duplicate_snapshots(live_dir: Path) -> list[dict[str, Any]]:
    """Flag (date, code, is_live) keys with >1 row in signal_snapshots.jsonl —
    the exact corruption that faked the A/B verdict. capture_signals replaces a
    day's rows idempotently now, so any duplicate is a regression."""
    rows = _read_jsonl(live_dir / "signal_snapshots.jsonl")
    keys = Counter((r.get("date"), r.get("code"), bool(r.get("is_live"))) for r in rows)
    dups = {k: n for k, n in keys.items() if n > 1}
    if not dups:
        return []
    worst = sorted(dups.items(), key=lambda kv: -kv[1])[:5]
    return [{
        "check": "duplicate_snapshots",
        "severity": "critical",
        "detail": f"{len(dups)} duplicate (date,code,is_live) keys in signal_snapshots.jsonl "
                  f"(e.g. {worst}) — dedupe before trusting any A/B verdict",
    }]


def account_reconciles(live_dir: Path, *, tolerance: float = 1.0) -> list[dict[str, Any]]:
    """Book B account realized_pnl must equal the sum of closed book-B positions'
    realized_pnl. A drift means trades or account updates were lost."""
    acct = _read_json(live_dir / "paper_account.json")
    if not acct:
        return []
    positions = _read_jsonl(live_dir / "positions.jsonl")
    closed_sum = sum(
        float(p.get("realized_pnl") or 0.0)
        for p in positions
        if p.get("book", "B") == "B" and p.get("status") == "closed"
    )
    acct_realized = float(acct.get("realized_pnl") or 0.0)
    drift = acct_realized - closed_sum
    if abs(drift) > tolerance:
        return [{
            "check": "account_reconciles",
            "severity": "warn",
            "detail": f"book B realized_pnl {acct_realized:+.2f} vs sum of closed positions "
                      f"{closed_sum:+.2f} (drift {drift:+.2f} > {tolerance})",
        }]
    return []


def stale_open_positions(live_dir: Path, *, today: str | None = None, max_days: int = 10) -> list[dict[str, Any]]:
    """Book B positions open far longer than the v5/v6 hold horizon — they should
    have exited; a stale one means the monitor/settle path skipped them."""
    today_d = date.fromisoformat(today) if today else date.today()
    stale = []
    for p in _read_jsonl(live_dir / "positions.jsonl"):
        if p.get("book", "B") != "B" or p.get("status", "open") != "open":
            continue
        try:
            entry = date.fromisoformat(str(p.get("entry_date")))
        except (TypeError, ValueError):
            continue
        if (today_d - entry).days > max_days:
            stale.append(f"{p.get('code')}({p.get('entry_date')})")
    if stale:
        return [{
            "check": "stale_open_positions",
            "severity": "warn",
            "detail": f"{len(stale)} book-B position(s) open > {max_days}d: {', '.join(stale[:8])}",
        }]
    return []


def check(live_dir: Path, *, today: str | None = None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    findings += duplicate_snapshots(live_dir)
    findings += account_reconciles(live_dir)
    findings += stale_open_positions(live_dir, today=today)
    return {
        "findings": findings,
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "warn": sum(1 for f in findings if f["severity"] == "warn"),
        "ok": not findings,
    }
