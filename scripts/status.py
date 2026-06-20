"""Print (and optionally push) the live situational-awareness digest.

One snapshot for the agent, the human, and Feishu: book B vs the validated
book A, today's deterministic decisions, and open holdings. See
docs/OPERATING_CONTRACT.md §3-4.

    python3 scripts/status.py                  # human digest
    python3 scripts/status.py --json           # structured digest
    python3 scripts/status.py --push-feishu     # also push to Feishu (needs
                                               # XIAOCAO_FEISHU_WEBHOOK)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import status as status_mod  # noqa: E402
from xiaocao.live.notify import notify  # noqa: E402

LIVE_DIR = ROOT / "output" / "live"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="market date (YYYY-MM-DD); defaults to the latest snapshot date")
    ap.add_argument("--json", action="store_true", help="print the structured digest")
    ap.add_argument("--push-feishu", action="store_true", help="also push the digest to Feishu")
    a = ap.parse_args()

    digest = status_mod.build_digest(live_dir=LIVE_DIR, market_date=a.date)
    if a.json:
        print(json.dumps(digest, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(status_mod.format_digest(digest))

    if a.push_feishu:
        text = status_mod.format_digest(digest)
        results = notify(f"小草盘后 {digest['market_date']}", text)
        if results:
            print(f"[push] {results}", file=sys.stderr)
        else:
            print("[push] no channel configured (set XIAOCAO_FEISHU_WEBHOOK)", file=sys.stderr)


if __name__ == "__main__":
    main()
