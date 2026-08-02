#!/usr/bin/env python3
"""Send an approved cross-node KOL reminder transport request exactly once."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol._shared import atomic_write_json
from xiaocao.kol.notification_transport import (
    NotificationTransport,
    NotificationTransportError,
)
from xiaocao.live.notify import (
    configured_wecom_recipients,
    send_wecom_recipient_detailed,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="self-hashed transport request JSON")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/live/kol_notification_transport"),
    )
    args = parser.parse_args()

    value = json.loads(args.request.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        parser.error("transport request must be a JSON object")
    transport = NotificationTransport(
        args.output_dir,
        configured_recipients=lambda: configured_wecom_recipients(audience="kol"),
    )
    receipt = transport.send(
        value,
        sender=lambda title, body, recipient: send_wecom_recipient_detailed(
            title,
            body,
            recipient,
            audience="kol",
        ),
    )
    receipt_path = args.output_dir / "receipts" / f"{value['handoff_id']}.json"
    atomic_write_json(receipt_path, receipt)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "handoff_id": receipt["handoff_id"],
                "receipt_sha256": receipt["receipt_sha256"],
                "receipt_path": str(receipt_path.resolve()),
                "recipients": sorted(receipt["recipient_receipts"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NotificationTransportError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
