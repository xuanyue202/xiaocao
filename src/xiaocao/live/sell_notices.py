"""Plain-language sale outcomes, derived from committed evidence, never signals."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import partial
import hashlib
import json
from pathlib import Path

from . import accounts, book_b_accounting
from .book_b_live_lifecycle import (
    _load_intent_index, _read_jsonl_strict, _sha256, _validate_ownership_chain,
)
from .incident_delivery import deliver_pending, enqueue_notice
from .notify import notify_detailed


@dataclass(frozen=True)
class SellNotice:
    title: str
    body: str
    identity: tuple


def _price(value) -> str:
    text = f"{Decimal(str(value)):.4f}".rstrip("0").rstrip(".")
    return text + ".00" if "." not in text else text + "0" if len(text.split(".")[1]) == 1 else text


def _profit(pnl, cost, *, estimated: bool = False) -> str:
    if pnl is None or cost is None or Decimal(str(cost)) <= 0:
        return "盈亏：待核算（缺少对应成交账务）"
    amount, basis = Decimal(str(pnl)), Decimal(str(cost))
    label = "盈利" if amount > 0 else "亏损" if amount < 0 else "盈亏持平"
    prefix = "账本暂计" if estimated else "扣费后"
    line = f"{prefix}{label}：{abs(amount):.2f} 元（{amount / basis * 100:+.2f}%）"
    return line + ("\n费用按计划估算，最终净利待费用核对。" if estimated else "")


def _reason(reason: str) -> str:
    return {
        "TRAILING_STOP": "价格从高点回落，达到卖出条件。",
        "TREND_TRAIL_STOP": "价格从高点回落，达到趋势持仓的卖出条件。",
        "HARD_STOP": "价格下跌达到止损条件。",
        "EOD_DISCIPLINE_1455": "收盘前不再满足继续持有条件。",
        "AI_EVENT_RISK_EXIT": "发现风险事件，按规则退出。",
        "KOL_DISCRETIONARY_EXIT": "已核验的研究判断要求退出。",
    }.get(reason, "达到策略的卖出条件。")


def paper_sell_notice(alert: dict, positions: list[dict], *, book: str,
                      trade_date: str, execute_requested: bool) -> SellNotice:
    matches = [p for p in positions if str(p.get("book") or "B") == book
               and p.get("code") == alert["code"]
               and p.get("entry_date") == alert["entry_date"]]
    position = matches[0] if len(matches) == 1 else {}
    sold = (position.get("status") == "closed"
            and position.get("exit_date") == trade_date)
    state = ("已全部卖出" if sold else "未卖出"
             if not execute_requested or position.get("status") == "open" else "卖出未确认")
    name = alert.get("name") or alert["code"]
    title = f"【纸面{book}】{name}｜{state}"
    lines = [f"{name}（{alert['code']}）", f"交易日期：{trade_date}", f"状态：{state}"]
    if sold:
        lines += [f"卖出：{position['shares']} 股，成交价 {_price(position['exit_price'])} 元",
                  f"买入价：{_price(position['entry_price'])} 元",
                  _profit(position.get("realized_pnl"), position.get("entry_cash_out"))]
    else:
        lines += ["成交价：无已确认成交", "已实现盈亏：无已确认结果",
                  "仅发出卖出提醒，未执行卖出。" if not execute_requested
                  else "请以成交记录为准；本次未查到该持仓的卖出入账记录。"]
    lines.append("原因：" + _reason(str(alert.get("sell_reason") or "")))
    return SellNotice(title, "\n".join(lines),
                      ("paper", book, alert["code"], alert["entry_date"], trade_date, state))


def app_sell_notice(receipt: dict, intent: dict, postings: list[dict]) -> SellNotice:
    """A broker acknowledgment alone cannot become a completed-sale message."""
    proven = (receipt.get("account_binding") == "proven"
              and receipt.get("receipt_mapping") is True
              and not receipt.get("submit_chain_uncertain")
              and not receipt.get("cancel_chain_uncertain"))
    filled = int(receipt.get("filled_shares") or 0) if proven else 0
    total = int(intent["shares"])
    complete = (proven and receipt.get("state") == "filled" and filled == total
                and receipt.get("remaining_shares") == 0)
    terminal_empty = (proven and not filled and receipt.get("state") in {"cancelled", "rejected"})
    state = ("已全部卖出" if complete else "部分卖出" if filled else
             "未卖出" if terminal_empty else "卖出结果待确认")
    name = intent.get("name") or intent["code"]
    title = f"【APP仿真B】{name}｜{state}"
    lines = [f"{name}（{intent['code']}）", f"交易日期：{intent['trade_date']}",
             f"状态：{state}", f"已确认卖出：{filled} / {total} 股"]
    financial_result = ""
    if filled:
        price = receipt.get("fill_price")
        lines.append(f"成交均价：{_price(price)} 元" if price else "成交均价：待核对")
        shares = sum(int(p["shares"]) for p in postings)
        cost = -sum(Decimal(str(p["cost_change"])) for p in postings)
        pnl = sum(Decimal(str(p["realized_pnl"])) for p in postings)
        financial_result = _profit(pnl if shares == filled else None, cost,
            estimated=any(p["fee_basis"] == "estimated_plan_rate" for p in postings))
        lines.append(financial_result)
        if not complete:
            lines.append("剩余部分尚未确认卖出；以上盈亏仅对应已成交部分。")
    elif terminal_empty:
        lines += ["成交价：无成交", "已实现盈亏：无（未成交）", "委托已撤销或被拒绝，仍需持有或后续处理。"]
    else:
        lines += ["成交价、盈亏：待成交确认后提供。", "已提交或等待核对，不代表已经卖出。"]
    lines += ["原因：" + _reason(str(intent.get("sell_reason") or "")),
              f"委托编号：{receipt.get('broker_order_id') or '待确认'}"]
    return SellNotice(title, "\n".join(lines),
                      ("app", intent["plan_id"], receipt.get("broker_order_id"), state,
                       filled, receipt.get("fill_price"), financial_result))


def deliver_sell_notice(outbox: Path, notice: SellNotice) -> list[dict]:
    identifier = hashlib.sha256(json.dumps(notice.identity, ensure_ascii=False).encode()).hexdigest()
    enqueue_notice(outbox, identifier=identifier, title=notice.title, body=notice.body)
    return deliver_pending(outbox, incident_ids={identifier},
                           sender=partial(notify_detailed, macos=True))


def notify_paper_sells(alerts: list[dict], *, live_dir: Path, positions_path: Path,
                       book: str, trade_date: str, execute_requested: bool) -> list[dict]:
    # Read only after the canonical transaction has returned; never infer a fill
    # from the quote that originally triggered the rule.
    with accounts.ledger_lock(accounts.ledger_lock_path(live_dir)):
        if (live_dir / ".ledger_txn/pending.json").exists():
            positions = []
        else:
            positions = accounts.load_positions(positions_path)
    results = []
    for alert in alerts:
        notice = paper_sell_notice(alert, positions, book=book, trade_date=trade_date,
                                   execute_requested=execute_requested)
        results.extend(deliver_sell_notice(live_dir / "sell_result_notices.jsonl", notice))
    return results


def notify_app_sells(payload: dict, *, state_dir: Path, outbox: Path) -> list[dict]:
    executions = list(payload.get("execution_receipts") or [])
    # Later exact reconciliation may prove fills; unchanged old zero-fill
    # UNKNOWN orders remain with their existing incident owner/outbox.
    executions += [r for r in payload.get("reconciliation_receipts") or []
                   if r.get("filled_shares", 0) > 0]
    if not executions:
        return []
    intents = _load_intent_index(state_dir)
    ownership, _ = _validate_ownership_chain(_read_jsonl_strict(
        state_dir / "book_b_ownership_evidence.jsonl"))
    try:
        postings = book_b_accounting.details(state_dir)
    except (OSError, ValueError):
        postings = []
    results = []
    for receipt in executions:
        intent = intents.get(receipt.get("plan_id"))
        if not intent or intent.get("side") != "SELL":
            continue
        if receipt.get("plan_hash") != _sha256(intent):
            raise ValueError("SELL_NOTICE_INTENT_HASH_MISMATCH")
        # Execution receipts accumulate the entire plan across replacement
        # orders. Each immutable ownership hash still binds its exact order.
        hashes = {r["event_hash"] for r in ownership
                  if r["plan_id"] == intent["plan_id"] and r["plan_hash"] == receipt["plan_hash"]}
        matched = [p for p in postings if p["kind"] == "SELL" and p["source_sha256"] in hashes
                   and p["owned_lot_id"] == intent["owned_lot_id"]]
        results.extend(deliver_sell_notice(outbox, app_sell_notice(receipt, intent, matched)))
    return results
