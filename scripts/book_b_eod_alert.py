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


def _incident_key(receipt: dict, *, closed_plan_ids: frozenset[str] = frozenset()) -> str:
    review = receipt.get("eod_review") or {}
    active = review.get("active_plan_ids")
    orders = sorted((str(r.get("plan_id") or ""), str(r.get("broker_order_id") or ""),
                     str(r.get("state") or ""), r.get("filled_shares", 0), r.get("remaining_shares", 0))
        for r in receipt.get("reconciliation_receipts", [])
        if r.get("state") in {"unknown", "claimed", "submitted", "acknowledged", "partial", "reconciling"}
        and r.get("plan_id") not in closed_plan_ids
        and (active is None or r.get("plan_id") in active))
    snapshot = receipt.get("broker_snapshot") or {}
    accounting = (receipt.get("account") or {}).get("accounting") or {}
    body = {"account": snapshot.get("fund_account_binding_sha256")
            or accounting.get("fund_account_binding_sha256") or "primary",
            "reason": receipt.get("reason"), "orders": orders,
            "active_plans": sorted(set(active) - closed_plan_ids if active is not None else {r[0] for r in orders if r[0]})}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _legacy_claim(outbox: Path, archive_dir: Path, receipt: dict) -> dict | None:
    """Bind an old delivery only through its exact immutable archive hash."""
    from xiaocao.live.incident_delivery import notice_retired
    if not outbox.exists():
        return None
    claims, delivered = {}, set()
    for line in outbox.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status") == "pending":
            claims[row["incident_id"]] = row
        elif row.get("status") == "delivered":
            delivered.add(row["incident_id"])
    matches = []
    closed = frozenset(r["plan_id"] for r in (receipt.get("eod_review") or {}).get(
        "historical_order_resolutions", []))
    for path in archive_dir.glob("*.json"):
        raw = path.read_bytes()
        old_id = hashlib.sha256(b"book-b-eod\0" + raw).hexdigest()
        if old_id not in claims:
            continue
        old = json.loads(raw)
        if _incident_key(old, closed_plan_ids=closed) == _incident_key(receipt, closed_plan_ids=closed):
            matches.append({"incident_id": old_id,
                "delivery": "retired_by_user" if notice_retired(outbox, old_id)
                else "already_delivered" if old_id in delivered else "pending_reconcile",
                "legacy_receipt_path": str(path)})
    # An uncertain legacy send takes precedence over another confirmed copy.
    return next((r for r in matches if r["delivery"] == "pending_reconcile"),
                matches[0] if matches else None)


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
    review = receipt.get("eod_review")
    if review and not review.get("active_plan_ids"):
        return {"status": "not_actionable", "reason": "ACCOUNTING_EVIDENCE_TRACKED_LOCALLY"}
    if "client_login_required" in reason:
        explanation = "方正客户端登录尚未完成。请在原登录任务完成当次验证码确认。"
    elif reason == "LIVE_BOOK_B_EOD_OPEN_EXECUTION_RECONCILE_REQUIRED":
        explanation = "存在仍影响当前账户的委托状态待核，原任务负责继续核对。"
    else:
        explanation = "账户或结算证据未通过完整核验，需要检查本次异常回执。"
    body = f"{receipt['trade_date']} APP Book B 盘后核对未完成。\n{explanation}\n"
    body += "该状态来自小草内部核对，不表示券商现金被冻结。"
    if review:
        labels = {"execution": "委托状态", "cash": "资金归属/现金差异", "fees": "实际费用"}
        body += "\n全部待核项：" + "、".join(labels.get(r["kind"], r["kind"])
            for r in review.get("blockers", []))
    order_ids = sorted({str(row['broker_order_id'])
        for row in receipt.get('reconciliation_receipts', [])
        if isinstance(row, dict) and row.get('broker_order_id')
        and row.get('state') in {'unknown', 'claimed', 'submitted', 'acknowledged', 'partial', 'reconciling'}})
    if review:
        order_ids = sorted({str(row['broker_order_id']) for row in receipt.get('reconciliation_receipts', [])
            if row.get('plan_id') in review['active_plan_ids'] and row.get('broker_order_id')})
    if order_ids:
        body += "\n待核实委托：" + "、".join(order_ids)
    identifier = _incident_key(receipt)
    outbox = root / "output/live/book_b_eod_incident_notices.jsonl"
    legacy = _legacy_claim(outbox, path.parent, receipt)
    if legacy:
        return {**legacy, "receipt_path": str(path), "pending_count": len(pending_notices(outbox))}
    enqueue_notice(outbox, identifier=identifier, title="小草盘后：账户核对需要关注", body=body)
    options = {}
    if sender is not None:
        options["sender"] = sender
    if readiness is not None:
        options["readiness"] = readiness
    results = deliver_pending(outbox, incident_ids={identifier}, **options)
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
