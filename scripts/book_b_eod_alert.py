#!/usr/bin/env python3
"""Deliver a blocked APP EOD notice from its exact archived receipt, without APP access."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.trading_change_notice import deliver_pending, enqueue_notice, pending_notices  # noqa: E402
from xiaocao.live.eod_automation_gate import AUTOMATION_ID  # noqa: E402


def notify_eod_blocker(receipt_path: Path, *, root: Path = ROOT,
                       sender=None, readiness=None) -> dict:
    """Bind the original owner and persist the send claim before transport."""
    path = Path(receipt_path).resolve()
    raw = path.read_bytes()
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict) or receipt.get("phase") != "eod"
            or receipt.get("route") != "native-app"
            or receipt.get("execute_sells_requested") is not False
            or path.name != f"{receipt.get('run_id')}.json"
            or path.parent.name != "archive" or path.parent.parent.name != "intraday"
            or Path(str(receipt.get("run_receipt_path") or "")).resolve() != path):
        raise ValueError("EOD_NOTICE_RECEIPT_INVALID")
    identity = receipt.get("automation_identity")
    if (not isinstance(identity, dict)
            or identity.get("automation_id") != AUTOMATION_ID
            or identity.get("branch") != "app"
            or identity.get("trade_date") != receipt.get("trade_date")
            or os.environ.get("CODEX_AUTOMATION_ID") != AUTOMATION_ID
            or not os.environ.get("CODEX_THREAD_ID")
            or identity.get("thread_id") != os.environ["CODEX_THREAD_ID"]):
        raise ValueError("EOD_NOTICE_OWNER_MISMATCH")
    claim_path = root / "output/live/eod_task_slots" / AUTOMATION_ID / f"{receipt['trade_date']}-app.json"
    if (Path(str(identity.get("claim_path") or "")).resolve() != claim_path.resolve()
            or json.loads(claim_path.read_text()) != identity):
        raise ValueError("EOD_NOTICE_SLOT_MISMATCH")
    reason = str(receipt.get("reason") or "")
    if receipt.get("status") != "blocked" or reason in {
        "LIVE_BOOK_B_CHECKPOINT_ALREADY_RUNNING", "LIVE_BOOK_B_CALENDAR_UNPROVEN",
    }:
        return {"status": "not_applicable"}
    if "client_login_required" in reason:
        explanation = "方正客户端登录尚未完成。请在原登录任务完成当次验证码确认。"
    elif reason == "LIVE_BOOK_B_EOD_OPEN_EXECUTION_RECONCILE_REQUIRED":
        explanation = "仍有自有委托未取得精确终态证明，继续逐单对账。"
    else:
        explanation = "账户或结算证据未通过完整核验，需要检查本次异常回执。"
    body = f"{receipt['trade_date']} APP Book B 盘后结算受阻。\n{explanation}\n"
    body += "本次未完成不可变结算；账户观测不代表结算净值。没有创建或重发订单。"
    order_ids = sorted({str(row['broker_order_id'])
        for row in receipt.get('reconciliation_receipts', [])
        if isinstance(row, dict) and row.get('broker_order_id')
        and row.get('state') in {'unknown', 'claimed', 'submitted', 'acknowledged', 'partial', 'reconciling'}})
    if order_ids:
        body += "\n待核实委托：" + "、".join(order_ids)
    identifier = hashlib.sha256(b"book-b-eod\0" + raw).hexdigest()
    outbox = root / "output/live/book_b_eod_incident_notices.jsonl"
    enqueue_notice(outbox, identifier=identifier, title="小草盘后：APP 结算受阻", body=body)
    options = {}
    if sender is not None:
        options["sender"] = sender
    if readiness is not None:
        options["readiness"] = readiness
    results = deliver_pending(outbox, **options)
    delivery = next((row for row in results if row["incident_id"] == identifier),
                    {"incident_id": identifier, "delivery": "already_delivered"})
    return {**delivery, "receipt_path": str(path),
            "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "pending_count": len(pending_notices(outbox))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = notify_eod_blocker(args.receipt)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("delivery") in {"delivered", "already_delivered"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
