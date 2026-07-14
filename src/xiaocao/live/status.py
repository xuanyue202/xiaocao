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
from xiaocao.live.ab_attribution import paired_exit_attribution


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _load_positions(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _holding_identity(row: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(row.get("code") or ""),
        str(row.get("entry_date") or "")[:10],
        int(row.get("shares") or 0),
    )


def _valuation_status(
    snapshot: dict[str, Any],
    *,
    account: dict[str, Any],
    open_positions: list[dict[str, Any]],
    market_date: str,
) -> tuple[str, str]:
    if not snapshot:
        return "missing", "no holdings snapshot"
    snapshot_date = str(snapshot.get("date") or "")[:10]
    if snapshot_date != market_date:
        return "stale", f"snapshot date {snapshot_date or 'missing'} != market date {market_date}"
    snapshot_ids = sorted(_holding_identity(row) for row in (snapshot.get("holdings") or []))
    position_ids = sorted(_holding_identity(row) for row in open_positions)
    if snapshot_ids != position_ids:
        return "mismatch", "snapshot holdings do not match open position ledger"
    for key in ("cash", "realized_pnl", "total_fees"):
        if key not in snapshot:
            return "mismatch", f"snapshot missing account total {key}"
        if key not in account:
            return "mismatch", f"account missing total {key}"
        if abs(_f(snapshot.get(key)) - _f(account.get(key))) > 0.01:
            return "mismatch", f"snapshot {key} does not match account ledger"
    return "fresh", "snapshot date, holdings identity, and account totals match"


def build_digest(
    *,
    live_dir: Path,
    market_date: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    holdings_snap = _load_json(live_dir / "paper_holdings.json")
    holdings_t_snap = _load_json(live_dir / "paper_holdings_T.json")
    acct_b = _load_json(live_dir / "paper_account.json")
    acct_a_path = live_dir / "paper_account_A.json"
    acct_a = _load_json(acct_a_path)
    acct_t_path = live_dir / "paper_account_T.json"
    acct_t = _load_json(acct_t_path)
    positions_path = live_dir / "positions.jsonl"
    all_positions = _load_positions(positions_path)
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
    open_a = [
        row for row in all_positions
        if row.get("book") == "A" and row.get("status", "open") == "open"
    ]
    book_a_open_cost = round(sum(_f(p.get("entry_cash_out")) for p in open_a), 2)
    book_a.update({
        "open_positions": len(open_a),
        "open_entry_cash_out": book_a_open_cost,
        # Book A is a reference book settled at next close; we do not maintain a
        # live mark-to-market snapshot for it. Cost-basis equity prevents the
        # cash line from being misread as total account size.
        "cost_basis_equity": round(book_a["cash"] + book_a_open_cost, 2) if book_a_present else 0.0,
    })
    book_t_present = acct_t_path.exists() and bool(acct_t)
    open_t = [
        row for row in all_positions
        if row.get("book") == "T" and row.get("status", "open") == "open"
    ]
    book_t_open_cost = round(sum(_f(p.get("entry_cash_out")) for p in open_t), 2)
    book_t_cost_equity = round(_f(acct_t.get("cash")) + book_t_open_cost, 2) if book_t_present else 0.0
    t_valuation_status, t_valuation_reason = _valuation_status(
        holdings_t_snap,
        account=acct_t,
        open_positions=open_t,
        market_date=market_date,
    )
    t_marked = t_valuation_status == "fresh"
    book_t = {
        "cash": _f(acct_t.get("cash")),
        "realized_pnl": _f(acct_t.get("realized_pnl")),
        "total_fees": _f(acct_t.get("total_fees")),
        "equity": (
            _f(holdings_t_snap.get("total_equity_after_exit_fee"))
            if t_marked else book_t_cost_equity
        ),
        "unrealized_pnl": (
            _f(holdings_t_snap.get("unrealized_pnl_after_fee")) if t_marked else None
        ),
        "open_positions": len(open_t),
        "open_entry_cash_out": book_t_open_cost,
        "cost_basis_equity": book_t_cost_equity,
        "equity_basis": "marked_snapshot" if t_marked else "cost_basis",
        "valuation_status": t_valuation_status,
        "valuation_reason": t_valuation_reason,
        "valuation_as_of": str(holdings_t_snap.get("ts") or holdings_t_snap.get("date") or "") or None,
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

    ab_paired = paired_exit_attribution(all_positions)
    return {
        "market_date": market_date,
        "generated_at": (now or datetime.now()).isoformat(timespec="seconds"),
        "book_b": book_b,
        "book_a": book_a,
        "book_a_present": book_a_present,
        "book_t": book_t,
        "book_t_present": book_t_present,
        # Retained as raw accounting compatibility only. Different cohorts and
        # notionals make this unsuitable for exit-policy attribution.
        "ab_realized_delta": (
            round(book_b["realized_pnl"] - book_a["realized_pnl"], 2) if book_a_present else None
        ),
        "ab_realized_delta_authority": "accounting_only",
        "ab_paired_exit": ab_paired,
        "ab_paired_exit_edge_pp": ab_paired.get("mean_b_minus_a_pp"),
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


def _format_ab_summary(digest: dict[str, Any]) -> str:
    delta = digest.get("ab_realized_delta")
    if delta is None:
        accounting = "A/B 累计账面差: N/A（Book A 未结算/缺失）。"
    else:
        accounting = (
            f"A/B 累计账面差: {_money(delta, signed=True)}（B-A，仅会计信息；"
            "样本数、仓位或结算进度可能不同，不可直接归因）。"
        )
    paired = digest.get("ab_paired_exit") or {}
    n = int(paired.get("eligible_pairs") or 0)
    edge = paired.get("mean_b_minus_a_pp")
    if not n or edge is None:
        comparison = "配对退出样本: N/A（暂无同股票/同日/同价/同股数且双方已结算的样本）。"
    else:
        comparison = (
            f"配对退出样本: n={n}，平均归一化收益 B-A {_pct(edge, signed=True).replace('%', 'pp')}，"
            f"B 优于 A {int(paired.get('b_better_pairs') or 0)}/{n}；仅描述性统计。"
        )
    return f"{accounting}\n- {comparison}"


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
            f"open虚拟持仓成本 {_money(a.get('open_entry_cash_out'))}，"
            f"成本口径权益 {_money(a.get('cost_basis_equity'))}，"
            f"已实现 {_money(a['realized_pnl'], signed=True)}。"
        )
    else:
        lines.append("- book A 验证账本（next-close）：未结算/缺失。")
    t = d.get("book_t") or {}
    if d.get("book_t_present"):
        if t.get("valuation_status") == "fresh":
            lines.append(
                f"- book T 趋势模拟账本：权益 {_money(t.get('equity'))}，现金 {_money(t.get('cash'))}，"
                f"持仓 {t.get('open_positions', 0)} 只，已实现 {_money(t.get('realized_pnl'), signed=True)}，"
                f"未实现 {_money(t.get('unrealized_pnl'), signed=True)}。"
            )
        else:
            lines.append(
                f"- book T 趋势模拟账本：成本口径权益 {_money(t.get('cost_basis_equity'))}，"
                f"现金 {_money(t.get('cash'))}，持仓 {t.get('open_positions', 0)} 只，"
                f"已实现 {_money(t.get('realized_pnl'), signed=True)}；估值 N/A "
                f"（{_fmt_optional(t.get('valuation_status'))}: {_fmt_optional(t.get('valuation_reason'))}）。"
            )
    lines.append(f"- {_format_ab_summary(d)}")
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
