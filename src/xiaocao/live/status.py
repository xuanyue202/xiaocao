"""Situational-awareness status digest — one snapshot consumed by the agent,
the human, and Feishu.

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
    acct_a = _load_json(live_dir / "paper_account_A.json")
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
        # live stop policy minus validated next-close policy: >0 = stops helped.
        "ab_realized_delta": round(book_b["realized_pnl"] - book_a["realized_pnl"], 2),
        "today": today,
        "holdings": holdings,
    }


def format_digest(d: dict[str, Any]) -> str:
    b, a = d["book_b"], d["book_a"]
    lines = [
        f"小草盘后 {d['market_date']}",
        f"book B(实盘止损口径): equity {b['equity']:.0f} | cash {b['cash']:.0f} | "
        f"realized {b['realized_pnl']:+.0f} | 未实现 {b['unrealized_pnl']:+.0f} | 持仓 {b['open_positions']}",
        f"book A(验证口径 next_close): cash {a['cash']:.0f} | realized {a['realized_pnl']:+.0f}",
        f"A/B realized 差 (实盘止损 − 验证): {d['ab_realized_delta']:+.0f}",
    ]
    today = d.get("today") or {}
    if today:
        pos = today.get("posture") or {}
        lines.append(
            f"今日({today.get('automation')}): regime {pos.get('regime')} "
            f"score {pos.get('score')} | 触发卖 {len(today.get('triggered') or [])} "
            f"| 递延 {len(today.get('deferred') or [])} | 持有 {today.get('n_holds')}"
        )
        for t in today.get("triggered") or []:
            lines.append(f"  SELL {t.get('code')} {t.get('name')} — {t.get('sell_reason')}")
    if d.get("holdings"):
        lines.append("持仓:")
        for h in d["holdings"]:
            lines.append(
                f"  {h.get('code')} {h.get('name')} [{h.get('profile')}] "
                f"net {h.get('net_ret_pct')}% dd {h.get('dd_pct')}%"
            )
    return "\n".join(lines)
