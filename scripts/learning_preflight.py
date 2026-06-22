#!/usr/bin/env python3
"""Governance pre-flight for the learning substrate — fail-closed on dirty data.

Runs xiaocao.research.data_guard over the mode_history training substrate before
the capability flywheel trusts it: catches zero/null-padded history, staleness,
and the execution-juiced-PnL convention trap. Complements data_doctor (which
checks duplicate snapshots etc.). Exit 1 on a critical finding so auto_daily can
skip the learning record.

Usage: python3 scripts/learning_preflight.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research import data_guard as dg  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"


def main() -> int:
    if not DB.exists():
        print("learning_preflight: no cache db — skip")
        return 0
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT trade_date, return_pct FROM mode_history WHERE mode NOT LIKE '/stock/%'").fetchall()
    finally:
        con.close()
    if not rows:
        print("learning_preflight: empty mode_history — skip")
        return 0
    recs = [{"day": d, "ret": r} for d, r in rows]
    today = date.today().isoformat()
    rep = dg.audit(recs, "ret", today=today, max_lag_days=12, treat_as_returns=True)
    print(f"learning_preflight: mode_history valid_range={rep['valid_range']} ok={rep['ok']}")
    for w in rep["warnings"]:
        print(f"  ⚠ {w}")
    # The PnL-convention warning is informational (mode_history IS realized PnL by
    # design); only zero-padding / staleness are critical for fail-closed.
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
