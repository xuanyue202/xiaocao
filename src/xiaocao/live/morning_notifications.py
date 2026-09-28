"""Durable, recipient-bound morning notices independent of APP execution."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .notify import configured_wecom_recipients, send_wecom_recipient_detailed

AUTOMATION_ID = "xiaocao-book-b-live-morning"
DEFAULT_ROOT = Path("output/live/book_b_morning_notifications")


def _write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _clock():
    return datetime.now(timezone.utc).isoformat()


def message(kind: str, trade_date: str, facts: dict) -> tuple[str, str]:
    if kind == "preflight-start":
        return "Book B 晨间预检启动", f"交易日 {trade_date}，APP 服务端仿真预检已启动。"
    if kind == "ready":
        return "Book B APP 预检 ready", f"交易日 {trade_date}，APP 会话和账户预检通过，等待不可变冻结；行情、资金和策略门仍在动作时重新核验。"
    if kind != "result":
        raise ValueError("MORNING_NOTIFICATION_KIND_INVALID")
    orders = facts.get("orders") or []
    pending = facts.get("pending_orders") or []
    status = facts.get("status", "unproven")
    ok = status in {"completed", "no_action", "skipped"} and not pending
    title = "Book B 黄金五分钟结果" if ok else "Book B 黄金五分钟问题"
    lines = [f"交易日 {trade_date}，状态 {status}，原因 {facts.get('reason') or '-'}。"]
    if facts.get("failed_stage") == "preflight":
        lines.append("预检受阻，未进入开盘交易；未补跑原 runner。")
    lines.append(f"本次委托 {len(orders)}，成交股数 {sum(r.get('filled_shares') or 0 for r in orders)}，未决 {len(pending) + sum(r.get('state') in {'unknown', 'acknowledged', 'partial'} for r in orders)}。")
    for row in orders + pending:
        lines.append(f"{row.get('plan_id')}：{row.get('state')}，单号 {row.get('broker_order_id') or '-'}，成交 {row.get('filled_shares') or 0}；{row.get('reason') or '-'}")
    if facts.get("receipt_path"):
        lines.append(f"回执：{facts['receipt_path']}")
    return title, "\n".join(lines)


class MorningNotifications:
    def __init__(self, trade_date: str, *, automation_id=AUTOMATION_ID,
                 root=DEFAULT_ROOT, sender=None, recipients=None):
        self.trade_date, self.automation_id = trade_date, automation_id
        self.root = Path(root)
        self.sender = sender or (lambda t, b, r: send_wecom_recipient_detailed(t, b, r, audience="trading"))
        self.recipients = recipients or (lambda: configured_wecom_recipients(audience="trading"))
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="morning-wecom")
        self.futures = []
        self.failures = []

    def publish(self, kind: str, facts: dict | None = None):
        try:
            return self._publish(kind, facts)
        except OSError:
            # Notification storage is supporting work, never an execution gate.
            self.failures.append({"kind": kind, "status": "pending",
                                  "reason": "MORNING_NOTICE_STORAGE_UNPROVEN"})
            return None

    def _publish(self, kind: str, facts: dict | None = None):
        facts = facts or {}
        title, body = message(kind, self.trade_date, facts)
        identity = facts.get("run_id") or "original"
        key = hashlib.sha256(f"{self.automation_id}|{self.trade_date}|{kind}|{identity}".encode()).hexdigest()
        path = self.root / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not path.exists():
                _write(path, {"notification_id": key, "automation_id": self.automation_id,
                              "trade_date": self.trade_date, "kind": kind, "title": title,
                              "body": body, "created_at": _clock(), "recipients": {}})
        self.futures.append(self.pool.submit(self.send, path))
        return key

    def send(self, path: Path):
        with path.with_suffix(".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            record = json.loads(path.read_text())
            states = record["recipients"]
            recipients = self.recipients()
            for recipient in recipients:
                key = hashlib.sha256(recipient.encode()).hexdigest()
                prior = states.get(key, {})
                if prior.get("status") in {"delivered", "sending", "uncertain"}:
                    continue
                states[key] = {"status": "sending", "attempted_at": _clock()}
                _write(path, record)  # Crash after claim requires reconciliation.
                try:
                    result = self.sender(record["title"], record["body"], recipient)
                except Exception:
                    result = {"status": "uncertain", "retry_safety": "uncertain"}
                status = "delivered" if result.get("status") == "ok" else (
                    "failed_safe" if result.get("retry_safety") in {"safe", "not_allowed"} else "uncertain")
                states[key].update(status=status, retry_safety=result.get("retry_safety"),
                                   failure_phase=result.get("failure_phase"))
                if status == "delivered":
                    states[key]["delivered_at"] = _clock()
                _write(path, record)
            delivered = bool(recipients) and all(states[hashlib.sha256(r.encode()).hexdigest()].get("status") == "delivered" for r in recipients)
            record["status"] = "delivered" if delivered else "pending"
            _write(path, record)
            return {"notification_id": record["notification_id"], "kind": record["kind"],
                    "status": record["status"], "receipt_path": str(path.resolve()),
                    "delivered_at": max((r.get("delivered_at", "") for r in states.values()), default="") or None}

    def retry_pending(self):
        for path in self.root.glob("*.json"):
            record = json.loads(path.read_text())
            if record.get("automation_id") == self.automation_id and record.get("status") != "delivered":
                self.futures.append(self.pool.submit(self.send, path))

    def close(self):
        self.pool.shutdown(wait=True)
        results = list(self.failures)
        for future in self.futures:
            try:
                results.append(future.result())
            except Exception:
                results.append({"status": "pending", "reason": "MORNING_NOTICE_READBACK_UNPROVEN"})
        return results
