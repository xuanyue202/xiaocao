"""Durable, recipient-bound morning notices independent of APP execution."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _clock():
    return datetime.now(timezone.utc).isoformat()


def _cause(reason: object) -> str:
    code = str(reason or "")
    if "OPEN_EXECUTION_RECONCILE_REQUIRED" in code:
        return "历史委托尚缺成交或撤单终态证明，新增买入已暂停。"
    if "SETTLEMENT" in code or "SETTLED_NAV" in code:
        return "最近结算证据不完整，新增买入已暂停。"
    if "AUTH" in code or "LOGIN" in code or "UNLOCK" in code or "KEYCHAIN" in code:
        return "行情认证或 APP 登录未通过，暂不能执行。"
    if "NO_NEW_BUY" in code or "NO_EXECUTABLE" in code or "NO_CANDIDATE" in code:
        return "当前候选或风险条件不允许新增买入。"
    if "CAPITAL" in code or "CASH" in code:
        return "资金证明未通过，新增买入已暂停。"
    return "执行检查尚未通过，系统保留原证据继续处理。"


def _order_line(row: dict) -> str:
    parts = str(row.get("plan_id") or "").split(":")
    code = row.get("code") or (parts[2] if len(parts) > 2 else "标的待核对")
    side = row.get("side") or (parts[3] if len(parts) > 3 else "")
    label = {"filled": "已成交", "cancelled": "已撤单", "rejected": "已拒绝",
             "skipped": "已跳过", "acknowledged": "已收单，等待成交",
             "partial": "部分成交", "unknown": "状态待核对"}.get(row.get("state"), "状态待核对")
    action = {"BUY": "买入", "SELL": "卖出"}.get(side, "")
    fill = row.get("filled_shares")
    quantity = (f"，已确认成交 {fill} 股" if isinstance(fill, (int, float))
                and row.get("fill_quantity_proven") is True else "，成交数量待核对")
    return f"{code} {action}：{label}{quantity}（单号 {row.get('broker_order_id') or '未取得'}）。"


def message(kind: str, trade_date: str, facts: dict) -> tuple[str, str]:
    if kind == "preflight-start":
        return "Book B 晨间预检启动", f"交易日 {trade_date}，APP 服务端仿真预检已启动。"
    if kind == "ready":
        return "Book B APP 预检 ready", f"交易日 {trade_date}，APP 会话和账户预检通过，等待不可变冻结；行情、资金和策略门仍在动作时重新核验。"
    if kind == "preflight-problem":
        return "小草早盘：需要你协助", (f"{trade_date}，尚未进入开盘交易。\n"
            f"原因：{_cause(facts.get('reason'))}\n"
            f"需要你处理：{(facts.get('user_action') or {}).get('request') or '请打开 Codex 查看具体请求。'}")
    if kind not in {"result", "golden-window"}:
        raise ValueError("MORNING_NOTIFICATION_KIND_INVALID")
    orders = facts.get("orders") or []
    pending = facts.get("pending_orders") or []
    status = facts.get("status", "unproven")
    ok = status in {"completed", "no_action", "skipped"} and not pending and not facts.get("pending_evidence_unproven")
    preflight = facts.get("failed_stage") == "preflight"
    title = "小草早盘：执行结果" if ok else "小草早盘：执行受阻"
    lines = [f"{trade_date} APP 仿真"]
    if kind == "golden-window":
        title = "小草早盘：执行仍未确认"
        lines.append("结果：09:30 尚未取得完整交易回执，委托和成交数量暂未证明。")
        lines.append("系统继续处理，确认结果后再通知；暂不需要你操作。")
    else:
        if preflight:
            lines.append("结果：未进入开盘交易，本次没有新增委托。")
        elif orders:
            lines.append(f"结果：本次 {len(orders)} 笔委托；逐单确认情况如下。")
        else:
            lines.append("结果：本次没有新增买入。")
        if not ok or not orders:
            lines.append(f"原因：{_cause(facts.get('reason'))}")
        lines.extend(_order_line(row) for row in orders)
        if pending:
            lines.append(f"另有 {len(pending)} 笔历史委托待核对：")
            lines.extend(_order_line(row) for row in pending)
        if facts.get("pending_evidence_unproven"):
            lines.append("历史委托证据暂无法读取，未决数量尚未证明。")
        if facts.get("user_action_required") is True:
            lines.append(f"需要你处理：{(facts.get('user_action') or {}).get('request') or '请打开 Codex 查看具体请求。'}")
        elif pending or not ok:
            lines.append("需要你处理：暂不需要操作。系统负责精确对账；未决委托不会自动重发。")
        else:
            lines.append("需要你处理：无需操作。")
    lines.append("详细证据保存在 Codex 本次任务中。")
    return title, "\n".join(lines)


def result_fingerprint(facts: dict) -> str:
    """Business evidence identity excludes run IDs, receipt paths and clocks."""
    fields = ("plan_id", "state", "broker_order_id", "filled_shares", "fill_price",
              "remaining_shares", "reason", "next_action", "submit_chain_uncertain",
              "cancel_chain_uncertain", "fill_quantity_proven")
    content = {k: facts.get(k) for k in ("status", "reason", "failed_stage")}
    for name in ("orders", "pending_orders"):
        content[name] = sorted(({k: row.get(k) for k in fields}
            for row in facts.get(name) or []), key=lambda row: str(row["plan_id"]))
    action = facts.get("user_action") or {}
    content.update(user_action_required=facts.get("user_action_required") is True,
                   user_action={"required": action.get("required") is True, "request": action.get("request")},
                   pending_evidence_unproven=facts.get("pending_evidence_unproven") is True)
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def local_only(record: dict) -> bool:
    return (record.get("delivery_policy") == "local_only"
            or record.get("kind") in {"preflight-start", "ready"}
            or (record.get("kind") == "preflight-problem"
                and record.get("user_action_required") is not True))


class MorningNotifications:
    def __init__(self, trade_date: str, *, automation_id=AUTOMATION_ID,
                 root=DEFAULT_ROOT, sender=None, recipients=None, on_delivery=None):
        self.trade_date, self.automation_id = trade_date, automation_id
        self.root = Path(root)
        self.sender = sender or (lambda t, b, r: send_wecom_recipient_detailed(t, b, r, audience="trading"))
        self.recipients = recipients or (lambda: configured_wecom_recipients(audience="trading"))
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="morning-wecom")
        self.futures = []
        self.failures = []
        self.timer = None
        self.terminal = threading.Event()
        self.on_delivery = on_delivery

    def _enqueue(self, path):
        future = self.pool.submit(self.send, path)
        self.futures.append(future)
        if self.on_delivery:
            def delivered(completed):
                try:
                    result = completed.result()
                except Exception:
                    result = {"status": "pending", "reason": "MORNING_NOTICE_READBACK_UNPROVEN"}
                self.on_delivery(result)
            future.add_done_callback(delivered)

    def arm_golden_window(self, *, now=None, timer_factory=threading.Timer):
        clock = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        boundary = datetime.fromisoformat(self.trade_date + "T09:30:00+08:00")
        remaining = (boundary - clock).total_seconds()
        if 0 < remaining <= 1800:
            def checkpoint():
                if not self.terminal.is_set():
                    self.publish("golden-window", {"status": "pending",
                        "reason": "GOLDEN_WINDOW_TERMINAL_NOT_PROVEN"})
            self.timer = timer_factory(remaining, checkpoint)
            self.timer.daemon = True
            self.timer.start()

    def publish(self, kind: str, facts: dict | None = None):
        if kind == "result":
            self.terminal.set()
            if self.timer is not None:
                self.timer.cancel()
        try:
            return self._publish(kind, facts)
        except OSError:
            # Notification storage is supporting work, never an execution gate.
            self.failures.append({"kind": kind, "status": "pending",
                                  "reason": "MORNING_NOTICE_STORAGE_UNPROVEN"})
            if self.on_delivery:
                self.on_delivery(self.failures[-1])
            return None

    def _publish(self, kind: str, facts: dict | None = None):
        facts = facts or {}
        title, body = message(kind, self.trade_date, facts)
        identity = facts.get("run_id") or "original"
        legacy_key = hashlib.sha256(f"{self.automation_id}|{self.trade_date}|{kind}|{identity}".encode()).hexdigest()
        if kind == "result":
            # Recovery runs with unchanged business results do not warrant
            # another message. Clocks, paths and run IDs are audit data.
            identity = result_fingerprint(facts)
        elif kind == "preflight-problem":
            # One dependency request can change from an agent repair into a
            # human-only action without changing its sanitized failure code.
            identity = f"{identity}:{result_fingerprint({k: facts.get(k) for k in ('reason', 'user_action_required', 'user_action')})}"
        key = hashlib.sha256(f"{self.automation_id}|{self.trade_date}|{kind}|{identity}".encode()).hexdigest()
        equivalence_unproven = False
        legacy_path = self.root / f"{legacy_key}.json"
        if legacy_path.exists() and (kind != "preflight-problem" or (
            json.loads(legacy_path.read_text()).get("user_action_required") is True
        ) == (facts.get("user_action_required") is True)):
            key = legacy_key  # Preserve equivalent delivered/uncertain claims.
        elif kind == "result":
            alias, equivalence_unproven = self._legacy_result_alias(identity)
            key = alias or key
        path = self.root / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not path.exists():
                _write(path, {"notification_id": key, "automation_id": self.automation_id,
                              "trade_date": self.trade_date, "kind": kind, "title": title,
                              "body": body, "created_at": _clock(), "recipients": {},
                              "user_action_required": facts.get("user_action_required") is True,
                              **({"result_fingerprint": identity} if kind == "result" else {}),
                              **({"delivery_policy": "reconcile_only", "status": "pending_reconcile",
                                  "reason": "LEGACY_MORNING_RESULT_EQUIVALENCE_UNPROVEN"}
                                 if equivalence_unproven else {})})
            if kind in {"preflight-start", "ready"} or (
                kind == "preflight-problem" and facts.get("user_action_required") is not True
            ) or facts.get("reason") == "NON_TRADING_DAY":
                record = json.loads(path.read_text())
                record["delivery_policy"] = "local_only"
                if record.get("status") != "delivered":
                    record["status"] = "recorded_only"
                _write(path, record)
                return key
        self._enqueue(path)
        return key

    def _legacy_result_alias(self, fingerprint: str) -> tuple[str | None, bool]:
        """Bind old delivery claims to exact receipts before semantic migration."""
        from .morning_observability import terminal_notice
        unproven = False
        expected_root = (self.root.parent / "book_b_live_execution/runs/history").resolve()
        for path in sorted(self.root.glob("*.json")):
            with path.with_suffix(".lock").open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                record = json.loads(path.read_text())
                if (record.get("automation_id") != self.automation_id
                    or record.get("trade_date") != self.trade_date or record.get("kind") != "result"):
                    continue
                prior = record.get("result_fingerprint")
                if not prior:
                    try:
                        match = re.search(r"^回执：(.+)$", record.get("body", ""), re.MULTILINE)
                        if not match:
                            raise ValueError("LEGACY_RECEIPT_MISSING")
                        raw_path = Path(match.group(1))
                        receipt = raw_path.resolve()
                        if raw_path.is_symlink() or receipt.parent != expected_root:
                            raise ValueError("LEGACY_RECEIPT_NOT_BOUND")
                        payload = json.loads(receipt.read_text())
                        old_id = hashlib.sha256(f"{self.automation_id}|{self.trade_date}|result|{payload['run_id']}".encode()).hexdigest()
                        if payload.get("trade_date") != self.trade_date or record.get("notification_id") != old_id or path.stem != old_id:
                            raise ValueError("LEGACY_RECEIPT_IDENTITY_MISMATCH")
                        prior = result_fingerprint(terminal_notice(payload, receipt, include_durable_pending=False))
                    except (OSError, ValueError, KeyError):
                        unproven = True
                        continue
                    record["result_fingerprint"] = prior
                    _write(path, record)  # Keep body, times and recipient claims intact.
                if prior == fingerprint:
                    return record["notification_id"], False
        return None, unproven

    def send(self, path: Path):
        with path.with_suffix(".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            record = json.loads(path.read_text())
            if local_only(record):
                return {"notification_id": record["notification_id"], "kind": record["kind"],
                        "status": "recorded_only", "receipt_path": str(path.resolve()), "delivered_at": None}
            if record.get("delivery_policy") == "reconcile_only":
                return {"notification_id": record["notification_id"], "kind": record["kind"],
                        "status": "pending_reconcile", "receipt_path": str(path.resolve()), "delivered_at": None}
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
            if (record.get("automation_id") == self.automation_id
                and record.get("status") != "delivered"
                and not local_only(record)
                and record.get("delivery_policy") != "reconcile_only"):
                self._enqueue(path)

    def close(self):
        self.terminal.set()
        if self.timer is not None:
            self.timer.cancel()
            self.timer.join()
        self.pool.shutdown(wait=True)
        results = list(self.failures)
        for future in self.futures:
            try:
                results.append(future.result())
            except Exception:
                results.append({"status": "pending", "reason": "MORNING_NOTICE_READBACK_UNPROVEN"})
        return results
