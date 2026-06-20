"""Verify both compounding flywheels are wired and able to spin.

No network, never trades — inspects wiring + accumulated artifacts and reports
health. Exits non-zero if a critical check fails (so it can gate automations).
See docs/FLYWHEEL.md.

    python3 scripts/flywheel_selfcheck.py
    python3 scripts/flywheel_selfcheck.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import flywheel  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    report = flywheel.check_flywheel(root=ROOT, env=dict(os.environ))

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        cap, capa = report["capital_flywheel"], report["capability_flywheel"]
        print(f"flywheel: {'🟢 SPINNING' if report['spinning'] else '🔴 NOT WIRED'}")
        print("capital flywheel (money compounds):")
        print(f"  safety paper-only : {cap['safety_paper_only']}  ({cap['safety_reason']})")
        print(f"  automation steps  : {', '.join(cap['automation_steps']) or 'none'}")
        print(f"  decision journal  : {cap['journal_entries']} entries")
        print(f"  book A / book B   : {cap['book_a_present']} / {cap['book_b_present']}")
        print("capability flywheel (the system gets smarter):")
        print(f"  training rows     : {capa['training_rows']}")
        print(f"  ledger verdicts   : {capa['ledger_entries']}")
        print(f"  optimize wired    : {capa['optimize_step_wired']}")
        for w in report["warnings"]:
            print(f"  ⚠ {w}")

    raise SystemExit(0 if report["spinning"] else 1)


if __name__ == "__main__":
    main()
