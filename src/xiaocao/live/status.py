"""Situational-awareness status digest — one snapshot consumed by the agent,
the human, and WeCom.

Assembles the live state (book B vs the validated book A, today's deterministic
decisions, open holdings) from the standard output/live/* files into a single
structured digest, so a waking agent or a daily push doesn't re-scrape seven
files. The book A vs book B realized spread is the headline: it answers "is the
live stop layer helping or hurting vs the validated next-close policy?" — the
exact divergence iteration-7 was built to surface. See OPERATING_CONTRACT §3-4.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from xiaocao.live import journal


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_digest(
    *,
    live_dir: Path,
    market_date: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    holdings_snap = _load_json(live_dir / "paper_holdings.json")
    acct_b = _load_json(live_dir / "paper_account.json")
    acct_a_path = live_dir / "paper_account_A.json"
    acct_a = _load_json(acct_a_path)
    # A missing/unparseable book-A account must NOT masquerade as realized 0.0:
    # ab_realized_delta would then collapse to book B's entire PnL and be reported
    # as "stops helped/hurt" against an empty baseline — the exact self-deceiving
    # signal iteration-7's A/B comparison exists to avoid. Gate the spread on this.
    book_a_present = acct_a_path.exists() and bool(acct_a)
    market_date = market_date or holdings_snap.get("date") or date.today().isoformat()

    book_b = {
        "cash": _f(acct_b.get("cash", holdings_snap.get("cash"))),
        "realized_pnl": _f(acct_b.get("realized_pnl", holdings_snap.get("realized_pnl"))),
        "total_fees": _f(acct_b.get("total_fees", holdings_snap.get("total_fees"))),
        "equity": _f(holdings_snap.get("total_equity_after_exit_fee")),
        "unrealized_pnl": _f(holdings_snap.get("unrealized_pnl_after_fee")),
        "open_positions": int(holdings_snap.get("open_positions") or 0),
    }
    book_a = {
        "cash": _f(acct_a.get("cash")),
        "realized_pnl": _f(acct_a.get("realized_pnl")),
    }

    latest = journal.latest(market_date=market_date, path=live_dir / "decision_journal.jsonl")
    today: dict[str, Any] = {}
    if latest:
        det = latest.get("deterministic") or {}
        today = {
            "automation": latest.get("automation"),
            "ts": latest.get("ts"),
            "posture": latest.get("posture") or {},
            "triggered": det.get("triggered") or [],
            "deferred": det.get("deferred") or [],
            "n_holds": len(det.get("holds") or []),
        }

    holdings = [
        {
            "code": h.get("code"), "name": h.get("name"), "profile": h.get("profile"),
            "net_ret_pct": h.get("net_ret_pct"), "dd_pct": h.get("dd_pct"),
        }
        for h in (holdings_snap.get("holdings") or [])
    ]

    return {
        "market_date": market_date,
        "generated_at": (now or datetime.now()).isoformat(timespec="seconds"),
        "book_b": book_b,
        "book_a": book_a,
        "book_a_present": book_a_present,
        # live stop policy minus validated next-close policy: >0 = stops helped.
        # None (not 0.0) when book A is absent — the spread is undefined, never faked.
        "ab_realized_delta": (
            round(book_b["realized_pnl"] - book_a["realized_pnl"], 2) if book_a_present else None
        ),
        "today": today,
        "holdings": holdings,
    }


def _money(value: Any, *, signed: bool = False) -> str:
    val = _f(value)
    if signed:
        return f"{val:+,.0f}"
    return f"{val:,.0f}"


def _pct(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    val = _f(value)
    sign = "+" if signed else ""
    return f"{val:{sign}.2f}%"


def _fmt_optional(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    return str(value)


def _holding_hint(h: dict[str, Any]) -> str:
    net = _f(h.get("net_ret_pct"))
    dd = _f(h.get("dd_pct"))
    if dd >= 8:
        return "回撤偏大，重点盯盘"
    if net >= 8 and dd <= 2:
        return "盈利领先，继续按规则观察"
    if net > 0:
        return "盈利中，跟随止盈规则"
    if net < 0:
        return "浮亏中，按规则处理"
    return "等待下一次纪律检查"


def _format_ab_summary(delta: Any) -> str:
    if delta is None:
        return "A/B realized 差: N/A。Book A 还没结算/缺失，这里先不硬算。"
    value = _f(delta)
    if value > 0:
        explain = "止损/退出层目前比 next-close 验证口径多赚。"
    elif value < 0:
        explain = "止损/退出层目前跑输 next-close 验证口径；这是证据，不是报错。"
    else:
        explain = "两种退出口径目前打平。"
    return f"A/B realized 差: {_money(value, signed=True)}（book B - book A）。{explain}"


def format_digest_body(d: dict[str, Any]) -> str:
    """Human-oriented message body for phone pushes and CLI output.

    Keep the structured field names that agents depend on (book A/book B,
    A/B realized), but add short Chinese explanations so the digest reads like
    a daily account note instead of a raw table dump.
    """
    b, a = d["book_b"], d["book_a"]
    lines = [
        "结论",
        f"- book B 实盘止损账本：总权益 {_money(b['equity'])}，现金 {_money(b['cash'])}，"
        f"持仓 {b['open_positions']} 只。",
        f"- 已实现 {_money(b['realized_pnl'], signed=True)}，未实现 "
        f"{_money(b['unrealized_pnl'], signed=True)}。",
    ]
    if d.get("book_a_present"):
        lines.append(
            f"- book A 验证账本（next-close）：现金 {_money(a['cash'])}，"
            f"已实现 {_money(a['realized_pnl'], signed=True)}。"
        )
    else:
        lines.append("- book A 验证账本（next-close）：未结算/缺失。")
    lines.append(f"- {_format_ab_summary(d.get('ab_realized_delta'))}")
    today = d.get("today") or {}
    if today:
        pos = today.get("posture") or {}
        lines.extend([
            "",
            "今日决策",
            f"- {_fmt_optional(today.get('automation'))}: regime {_fmt_optional(pos.get('regime'))}，"
            f"score {_fmt_optional(pos.get('score'))}；触发卖 {len(today.get('triggered') or [])}，"
            f"递延 {len(today.get('deferred') or [])}，继续持有 {today.get('n_holds')}",
        ])
        for t in today.get("triggered") or []:
            lines.append(
                f"- 卖出触发：{_fmt_optional(t.get('name'))} "
                f"{_fmt_optional(t.get('code'))}，原因 {_fmt_optional(t.get('sell_reason'))}"
            )
    else:
        lines.extend([
            "",
            "今日决策",
            "- 暂无最新决策日志；这条只展示账本和持仓快照。",
        ])
    if d.get("holdings"):
        lines.extend(["", "持仓"])
        for i, h in enumerate(d["holdings"], 1):
            lines.append(
                f"{i}. {_fmt_optional(h.get('name'))} {_fmt_optional(h.get('code'))} "
                f"[{_fmt_optional(h.get('profile'))}]："
                f"{_pct(h.get('net_ret_pct'), signed=True)}，回撤 {_pct(h.get('dd_pct'))}"
                f"（{_holding_hint(h)}）"
            )
    else:
        lines.extend(["", "持仓", "- 当前无 open 持仓。"])
    return "\n".join(lines)


def format_digest(d: dict[str, Any]) -> str:
    return f"小草盘后 {d['market_date']}\n{format_digest_body(d)}"
