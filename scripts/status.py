"""Print (and optionally push) the live situational-awareness digest.

One snapshot for the agent, the human, and WeCom: book B vs the validated
book A, today's deterministic decisions, and open holdings. See
docs/OPERATING_CONTRACT.md §3-4.

    python3 scripts/status.py                  # human digest
    python3 scripts/status.py --json           # structured digest
    python3 scripts/status.py --push-wecom      # also push to WeCom relay
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import status as status_mod  # noqa: E402
from xiaocao.live.incident_delivery import enqueue_notice, deliver_pending  # noqa: E402

LIVE_DIR = ROOT / "output" / "live"


def push_digest(digest: dict) -> dict:
    """Deliver identical dated text once through the shared durable send claim."""
    title = f"小草盘后 {digest['market_date']}"
    body = status_mod.format_digest_body(digest)
    identifier = hashlib.sha256(
        f"paper-eod-status\0{digest['market_date']}\0{title}\0{body}".encode("utf-8")
    ).hexdigest()
    outbox = LIVE_DIR / "paper_eod_status_notices.jsonl"
    enqueue_notice(outbox, identifier=identifier, title=title, body=body)
    results = deliver_pending(outbox, incident_ids={identifier})
    return next((row for row in results if row["incident_id"] == identifier),
                {"incident_id": identifier, "delivery": "already_delivered"})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="market date (YYYY-MM-DD); defaults to the latest snapshot date")
    ap.add_argument("--json", action="store_true", help="print the structured digest")
    ap.add_argument("--push-wecom", action="store_true", help="also push the digest to WeCom relay")
    ap.add_argument("--push-feishu", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()

    digest = status_mod.build_digest(live_dir=LIVE_DIR, market_date=a.date)
    if a.json:
        print(json.dumps(digest, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(status_mod.format_digest(digest))

    if a.push_wecom or a.push_feishu:
        try:
            results = push_digest(digest)
        except (OSError, ValueError) as exc:
            # A failed claim must never fall back to an unclaimed transport call.
            results = {"delivery": "blocked", "reason": type(exc).__name__}
        degraded = results["delivery"] not in {"delivered", "already_delivered"}
        prefix = "supporting-layer degraded: " if degraded else ""
        print(f"[push] {prefix}{results}", file=sys.stderr)



if __name__ == "__main__":
    main()
