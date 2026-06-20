"""Print recent structured decision-journal entries (cross-context continuity).

A fresh-context agent (e.g. the 14:55 or EOD run) reads this to learn what
earlier runs concluded *today* — instead of re-deriving the day from scattered
holdings/alerts/positions files. See docs/OPERATING_CONTRACT.md §2.

    python3 scripts/show_journal.py                       # last 10 entries
    python3 scripts/show_journal.py --date today
    python3 scripts/show_journal.py --automation morning --date 2026-06-19
    python3 scripts/show_journal.py --json                # raw records
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import journal  # noqa: E402

JOURNAL = ROOT / "output" / "live" / "decision_journal.jsonl"


def _summary(r: dict) -> str:
    det = r.get("deterministic") or {}
    pos = r.get("posture") or {}
    trig = det.get("triggered") or []
    deferred = det.get("deferred") or []
    holds = det.get("holds") or []
    head = (
        f"[{r.get('ts')}] {r.get('automation')} {r.get('market_date')} "
        f"regime={pos.get('regime')} score={pos.get('score')} "
        f"equity={det.get('equity')} cash={det.get('cash')} "
        f"open={det.get('open_positions')}"
    )
    lines = [head, f"  triggered={len(trig)} deferred={len(deferred)} holds={len(holds)}"]
    for t in trig:
        lines.append(f"    SELL {t.get('code')} {t.get('name')} — {t.get('sell_reason')}")
    for d in deferred:
        lines.append(f"    defer {d.get('code')} {d.get('name')} — {d.get('deferred_sell_reason')}")
    if r.get("agent_judgment"):
        lines.append(f"  agent_judgment: {json.dumps(r['agent_judgment'], ensure_ascii=False)}")
    if r.get("anomalies"):
        lines.append(f"  anomalies: {json.dumps(r['anomalies'], ensure_ascii=False)}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=10, help="number of recent entries; default 10")
    ap.add_argument("--date", help="filter by market date (YYYY-MM-DD or 'today')")
    ap.add_argument("--automation", help="filter by automation (morning/live_monitor/eod)")
    ap.add_argument("--json", action="store_true", help="print raw JSON records")
    a = ap.parse_args()

    rows = journal.read_all(JOURNAL)
    if a.date:
        target = date.today().isoformat() if a.date == "today" else a.date
        rows = [r for r in rows if r.get("market_date") == target]
    if a.automation:
        rows = [r for r in rows if r.get("automation") == a.automation]
    rows = rows[-a.n:]

    if not rows:
        print("(no matching decision-journal entries)")
        return
    if a.json:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, sort_keys=True))
    else:
        for r in rows:
            print(_summary(r))


if __name__ == "__main__":
    main()
