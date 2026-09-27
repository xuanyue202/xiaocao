#!/usr/bin/env python3
"""Escalate a proven morning blocker to the configured trading WeCom relay."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.api.client import XiaocaoClient
from xiaocao.api.preflight import authentication_preflight
from xiaocao.config import load_settings
from xiaocao.live.notify import notify, wecom_transport_readiness
from xiaocao.live.trading_execution import TradingIncidentOutbox


DEFAULT_OUTBOX = Path("output/live/morning_preflight_incidents.jsonl")
_CODE = re.compile(r"[A-Z][A-Z0-9_:-]{0,95}\Z")


def _safe_code(value: object, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if _CODE.fullmatch(candidate) else fallback


def _read_receipt(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("PREFLIGHT_RECEIPT_UNTRUSTED")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("PREFLIGHT_RECEIPT_UNREADABLE") from None
    if not isinstance(payload, dict):
        raise ValueError("PREFLIGHT_RECEIPT_INVALID")
    return payload


def assess_market_auth(trade_date: str) -> dict:
    settings = load_settings(None)
    client = XiaocaoClient(base_url=settings.base_url, timeout=8, retries=0, cache=None)
    receipt = authentication_preflight(client, trade_date)
    check = receipt["checks"][0]
    reason = _safe_code(
        check.get("auth_failure_category") or receipt.get("reason"),
        "MARKET_PREFLIGHT_BLOCKED",
    )
    return {
        "kind": "market-auth", "trade_date": trade_date,
        "status": receipt["status"], "reason": reason if receipt["status"] == "blocked" else None,
        "evidence": "fresh_official_authentication_probe",
    }


def assess_receipt(kind: str, trade_date: str, path: Path) -> dict:
    payload = _read_receipt(path)
    if kind == "book-b":
        if payload.get("trade_date") != trade_date or not payload.get("run_id"):
            raise ValueError("PREFLIGHT_RECEIPT_DATE_OR_RUN_MISMATCH")
        status = str(payload.get("status") or "")
        if status not in {"completed", "no_action", "skipped", "blocked", "failed"}:
            raise ValueError("PREFLIGHT_RECEIPT_STATUS_INVALID")
        reason = _safe_code(payload.get("reason"), "BOOK_B_MORNING_BLOCKED")
        stage = _safe_code(payload.get("failed_stage"), "UNPROVEN_STAGE")
        evidence = f"run_id={payload['run_id']} stage={stage} receipt={path.resolve()}"
    elif kind == "producer":
        if payload.get("market_date") != trade_date or payload.get("automation") != "morning-prerecommend":
            raise ValueError("PREFLIGHT_RECEIPT_DATE_OR_RUN_MISMATCH")
        status = str(payload.get("deterministic_status") or "")
        if status not in {"succeeded", "failed", "blocked"}:
            raise ValueError("PREFLIGHT_RECEIPT_STATUS_INVALID")
        reason = "PRODUCER_DETERMINISTIC_FAILED" if status != "succeeded" else None
        evidence = f"exit_code={payload.get('exit_code')} receipt={path.resolve()}"
    else:
        raise ValueError("PREFLIGHT_KIND_INVALID")
    return {
        "kind": kind, "trade_date": trade_date,
        "status": "blocked" if status in {"blocked", "failed"} else "ready",
        "reason": reason if status in {"blocked", "failed"} else None,
        "evidence": evidence,
    }


def deliver_blocker(
    assessment: dict, *, outbox: TradingIncidentOutbox,
    sender=notify,
) -> dict:
    result = {key: assessment[key] for key in ("kind", "trade_date", "status", "reason")}
    if assessment["status"] != "blocked":
        return {**result, "delivery": "not_needed"}
    incident_id = hashlib.sha256(
        f"{assessment['trade_date']}|{assessment['kind']}|{assessment['reason']}".encode()
    ).hexdigest()
    result["incident_id"] = incident_id
    if outbox.delivered(incident_id):
        return {**result, "delivery": "already_delivered"}
    title = "小草早盘预检加急"
    body = (
        f"日期={assessment['trade_date']} 检查={assessment['kind']} "
        f"故障={assessment['reason']}\n"
        f"证据={assessment['evidence']}\n"
        "请加急处理；原交易和冻结安全门保持有效，不补造订单或推荐。"
    )
    if not outbox.enqueue(incident_id=incident_id, title=title, body=body):
        return {**result, "delivery": "already_delivered"}
    readiness = wecom_transport_readiness(audience="trading")
    if readiness["status"] != "configured":
        return {**result, "delivery": "transport_unconfigured",
                "transport_missing": readiness["missing"]}
    try:
        transport = sender(title, body, audience="trading")
    except Exception:
        return {**result, "delivery": "unproven"}
    if isinstance(transport, dict) and transport.get("wecom") == "ok":
        outbox.mark_delivered(incident_id, {"wecom": "ok"})
        return {**result, "delivery": "delivered"}
    return {**result, "delivery": "unproven"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today")
    parser.add_argument("--kind", choices=("transport", "market-auth", "book-b", "producer"), required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--outbox", type=Path, default=DEFAULT_OUTBOX)
    args = parser.parse_args(argv)
    trade_date = (
        datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        if args.date == "today" else date.fromisoformat(args.date).isoformat()
    )
    if args.kind == "transport":
        readiness = wecom_transport_readiness(audience="trading")
        print(json.dumps({"kind": "transport", "trade_date": trade_date,
                          **readiness},
                         ensure_ascii=False, sort_keys=True))
        return 0 if readiness["status"] == "configured" else 2
    if args.kind == "market-auth":
        if args.receipt is not None:
            parser.error("--receipt is not used for market-auth")
        try:
            assessment = assess_market_auth(trade_date)
        except Exception:
            # A broken probe is itself an opening failure. Never serialize the
            # exception; it may contain a remote response or local config.
            assessment = {"kind": "market-auth", "trade_date": trade_date,
                          "status": "blocked", "reason": "MARKET_PREFLIGHT_PROBE_ERROR",
                          "evidence": "fresh_official_authentication_probe_failed"}
    else:
        if args.receipt is None:
            parser.error("--receipt is required for book-b and producer")
        try:
            assessment = assess_receipt(args.kind, trade_date, args.receipt)
        except ValueError as error:
            assessment = {"kind": args.kind, "trade_date": trade_date,
                          "status": "blocked", "reason": _safe_code(str(error), "PREFLIGHT_EVIDENCE_INVALID"),
                          "evidence": f"receipt={args.receipt.resolve()}"}
    result = deliver_blocker(assessment, outbox=TradingIncidentOutbox(args.outbox))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
