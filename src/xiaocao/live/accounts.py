"""Account & position I/O — the single source for real-money accounting state.

This logic was duplicated, with already-divergent signatures, between
scripts/live_monitor.py and kronos_screen/scripts/paper_record.py. Two copies of
the load/save/append logic for the book A/B ledger is the most dangerous kind of
duplication: a drift here silently breaks reconciliation. Both scripts now call
these functions so there is one tested implementation. Behaviour is identical to
the former paper_record (parametrized) version. See docs/OPERATING_CONTRACT.md §3.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_account(path: Path, initial_capital: float, fee_rate: float) -> dict[str, Any]:
    """Load a paper account, filling defaults; create a fresh one if absent."""
    if path.exists():
        with path.open(encoding="utf-8") as f:
            account = json.load(f)
        account.setdefault("initial_capital", initial_capital)
        account.setdefault("cash", initial_capital)
        account.setdefault("fee_rate", fee_rate)
        account.setdefault("realized_pnl", 0.0)
        account.setdefault("total_fees", 0.0)
        return account
    return {
        "initial_capital": initial_capital,
        "cash": initial_capital,
        "fee_rate": fee_rate,
        "realized_pnl": 0.0,
        "total_fees": 0.0,
        "created_at": now_iso(),
    }


def save_account(account: dict[str, Any], path: Path) -> None:
    """Atomically persist the account (tmp + replace), stamping updated_at."""
    path.parent.mkdir(parents=True, exist_ok=True)
    account["updated_at"] = now_iso()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def append_jsonl(record: dict[str, Any], path: Path) -> None:
    """Append one record to a jsonl audit stream (trades, etc.)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def load_positions(path: Path) -> list[dict[str, Any]]:
    """Load all position records (skips blank and #-comment lines; tolerates
    malformed lines). Callers filter by book/status as needed."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def position_key(position: dict[str, Any]) -> tuple[str, str]:
    return str(position.get("entry_date", "")), str(position.get("code", ""))
