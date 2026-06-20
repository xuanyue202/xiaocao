"""Data-health doctor — catch dirty data before it fakes the evaluation.

Run before trusting any A/B verdict, and daily as a sanity gate. No network.
Exits non-zero on a critical finding (e.g. duplicate snapshots). See
src/xiaocao/live/data_health.py.

    python3 scripts/data_doctor.py
    python3 scripts/data_doctor.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import data_health  # noqa: E402

LIVE_DIR = ROOT / "output" / "live"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    report = data_health.check(LIVE_DIR)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if report["ok"]:
            print("🟢 data health: OK (no dirty-data findings)")
        else:
            print(f"data health: {report['critical']} critical, {report['warn']} warn")
            for f in report["findings"]:
                icon = "🔴" if f["severity"] == "critical" else "🟡"
                print(f"  {icon} [{f['check']}] {f['detail']}")
    raise SystemExit(1 if report["critical"] else 0)


if __name__ == "__main__":
    main()
