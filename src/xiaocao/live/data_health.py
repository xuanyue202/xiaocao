"""Data-health doctor — guard the flywheel's honesty against dirty data.

The real data hazard for xiaocao is not "the proprietary API is down" (that is
unavoidable for the core signal, and cache-first already covers history) — it is
**dirty data silently faking the evaluation**. The 06-01 triple-snapshot bug made
the A/B verdict meaningless ("-0.49 vs -1.01 cushion 是脏数据假象"). This module
catches that class of problem offline, so the compounding loop never learns from
a 真的谎言. Used by scripts/data_doctor.py and surfaced in the daily digest.

Each check returns findings: {"check", "severity" (info|warn|critical), "detail"}.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from xiaocao.live.sell_blocks import load_blocked_sell_keys


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def duplicate_snapshots(live_dir: Path) -> list[dict[str, Any]]:
    """Flag (date, code, is_live, book) keys with >1 row in signal_snapshots.jsonl —
    the exact corruption that faked the A/B verdict. capture_signals replaces a
    day's rows idempotently now, so any duplicate is a regression."""
    rows = _read_jsonl(live_dir / "signal_snapshots.jsonl")
    keys = Counter(
        (r.get("date"), r.get("code"), bool(r.get("is_live")), str(r.get("book") or "B"))
        for r in rows
    )
    dups = {k: n for k, n in keys.items() if n > 1}
    if not dups:
        return []
    worst = sorted(dups.items(), key=lambda kv: -kv[1])[:5]
    return [{
        "check": "duplicate_snapshots",
        "severity": "critical",
        "detail": f"{len(dups)} duplicate (date,code,is_live,book) keys in signal_snapshots.jsonl "
                  f"(e.g. {worst}) — dedupe before trusting any A/B verdict",
    }]


def incomplete_ledger_transaction(live_dir: Path) -> list[dict[str, Any]]:
    """A prepared multi-file commit must be recovered before trusting ledgers."""
    pending = live_dir / ".ledger_txn" / "pending.json"
    if not pending.exists():
        return []
    return [{
        "check": "incomplete_ledger_transaction",
        "severity": "critical",
        "detail": (
            f"prepared ledger transaction remains at {pending}; run the next ledger writer "
            "or accounts.recover_ledger_transaction under the canonical lock before evaluation"
        ),
    }]


def unlabeled_closed_positions(live_dir: Path) -> list[dict[str, Any]]:
    """Positions or trades missing explicit accounting ownership.

    The function name is retained for CLI/check compatibility, but the
    invariant now covers the complete ledger.  Read paths may still tolerate
    historical rows; every current writer fails closed instead.
    """
    positions = _read_jsonl(live_dir / "positions.jsonl")
    trades = _read_jsonl(live_dir / "paper_trades.jsonl")
    unlabeled_positions = [p for p in positions if not p.get("book")]
    unlabeled_trades = [t for t in trades if not t.get("book")]
    if not unlabeled_positions and not unlabeled_trades:
        return []
    examples = [str(row.get("code")) for row in (unlabeled_positions + unlabeled_trades)[:8]]
    return [{
        "check": "unlabeled_closed_positions",
        "severity": "warn",
        "detail": (
            f"{len(unlabeled_positions)} position(s) and {len(unlabeled_trades)} trade(s) "
            f"lack an explicit `book` label (e.g. {', '.join(examples)}) — backfill only "
            f"from provable ledger identity; do not silently default accounting ownership"
        ),
    }]


def account_reconciles(live_dir: Path, *, tolerance: float = 1.0) -> list[dict[str, Any]]:
    """Book B account realized_pnl must equal the sum of closed book-B positions'
    realized_pnl. A drift means trades or account updates were lost. An absent
    `book` is treated as B for legacy compatibility (see unlabeled_closed_positions,
    which flags such rows so they can't silently absorb a book-A close)."""
    acct = _read_json(live_dir / "paper_account.json")
    if not acct:
        return []
    positions = _read_jsonl(live_dir / "positions.jsonl")
    closed_sum = sum(
        float(p.get("realized_pnl") or 0.0)
        for p in positions
        if p.get("book", "B") == "B" and p.get("status") == "closed"
    )
    acct_realized = float(acct.get("realized_pnl") or 0.0)
    drift = acct_realized - closed_sum
    if abs(drift) > tolerance:
        return [{
            "check": "account_reconciles",
            "severity": "warn",
            "detail": f"book B realized_pnl {acct_realized:+.2f} vs sum of closed positions "
                      f"{closed_sum:+.2f} (drift {drift:+.2f} > {tolerance})",
        }]
    return []


def account_reconciles_book_t(live_dir: Path, *, tolerance: float = 1.0) -> list[dict[str, Any]]:
    """Book T account realized_pnl must equal closed book-T positions."""
    acct = _read_json(live_dir / "paper_account_T.json")
    if not acct:
        return []
    positions = _read_jsonl(live_dir / "positions.jsonl")
    closed_sum = sum(
        float(p.get("realized_pnl") or 0.0)
        for p in positions
        if p.get("book") == "T" and p.get("status") == "closed"
    )
    acct_realized = float(acct.get("realized_pnl") or 0.0)
    drift = acct_realized - closed_sum
    if abs(drift) > tolerance:
        return [{
            "check": "account_reconciles_book_t",
            "severity": "warn",
            "detail": f"book T realized_pnl {acct_realized:+.2f} vs sum of closed positions "
                      f"{closed_sum:+.2f} (drift {drift:+.2f} > {tolerance})",
        }]
    return []


def blocked_sell_executions(live_dir: Path) -> list[dict[str, Any]]:
    """A market-rejected sell must not become a same-day closed position.

    This cross-ledger invariant catches independent writers that ignore the
    execution result and settle from a theoretical close price instead.
    """
    # A morning liquidity block may clear.  A block observed after the 14:55
    # discipline gate cannot be followed by another executable session that day.
    blocked = load_blocked_sell_keys(live_dir / "alerts.jsonl", not_before_time="14:55")
    if not blocked:
        return []
    contradictions: list[tuple[str, str, str, str]] = []
    for position in _read_jsonl(live_dir / "positions.jsonl"):
        if position.get("status") != "closed":
            continue
        key = (
            str(position.get("book") or "B"),
            str(position.get("exit_date") or "")[:10],
            str(position.get("code") or ""),
            str(position.get("entry_date") or "")[:10],
        )
        if key in blocked:
            contradictions.append(key)
    if not contradictions:
        return []
    examples = ", ".join(
        f"{book}:{code}({entry}->{exit})"
        for book, exit, code, entry in contradictions[:5]
    )
    return [{
        "check": "blocked_sell_executions",
        "severity": "critical",
        "detail": (
            f"{len(contradictions)} position(s) were recorded closed on a day their sell was "
            f"blocked by market liquidity: {examples} — repair the ledger before trusting PnL"
        ),
    }]


def stale_open_positions(live_dir: Path, *, today: str | None = None, max_days: int = 10) -> list[dict[str, Any]]:
    """Book B positions open far longer than the v5/v6 hold horizon — they should
    have exited; a stale one means the monitor/settle path skipped them."""
    today_d = date.fromisoformat(today) if today else date.today()
    stale = []
    for p in _read_jsonl(live_dir / "positions.jsonl"):
        if p.get("book", "B") != "B" or p.get("status", "open") != "open":
            continue
        try:
            entry = date.fromisoformat(str(p.get("entry_date")))
        except (TypeError, ValueError):
            continue
        if (today_d - entry).days > max_days:
            stale.append(f"{p.get('code')}({p.get('entry_date')})")
    if stale:
        return [{
            "check": "stale_open_positions",
            "severity": "warn",
            "detail": f"{len(stale)} book-B position(s) open > {max_days}d: {', '.join(stale[:8])}",
        }]
    return []


def stale_market_cache(
    cache_path: Path,
    *,
    reconstructed_path: Path | None = None,
    today: str | None = None,
    max_days: int = 10,
) -> list[dict[str, Any]]:
    """The historical daily-bar / mode-return cache silently goes stale when the
    upstream date_kline feed lags. In June 2026 the date_kline endpoint froze at
    2026-05-29 (~3 weeks behind) while live_recommend's `except: rows=[]` swallowed
    the empty result — so the learning substrate (mode_history) and proxy regime
    quietly ran on end-May data for weeks with no alarm. This surfaces it: if the
    newest mode_history trade_date is more than `max_days` calendar days behind
    today, forward_eval / hypothesis tests are running on a frozen daily feed.

    Read-only, stdlib sqlite. Returns [] if the cache is absent/unreadable (a
    missing cache is not a dirty-data finding)."""
    import sqlite3

    if not cache_path.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{cache_path}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT max(trade_date) FROM mode_history WHERE length(trade_date)=10"
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    latest = row[0] if row and row[0] else None
    if not latest:
        return []
    today_d = date.fromisoformat(today) if today else date.today()
    try:
        gap = (today_d - date.fromisoformat(latest)).days
    except ValueError:
        return []
    reconstructed_latest: str | None = None
    if reconstructed_path is not None:
        reconstructed_dates = [
            str(row.get("date") or "")
            for row in _read_jsonl(reconstructed_path)
            if row.get("date")
        ]
        normalized = [
            f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 and value.isdigit() else value[:10]
            for value in reconstructed_dates
        ]
        reconstructed_latest = max(normalized, default=None)
        if reconstructed_latest:
            try:
                reconstructed_gap = (today_d - date.fromisoformat(reconstructed_latest)).days
            except ValueError:
                reconstructed_gap = max_days + 1
            if reconstructed_gap <= max_days:
                return []
    if gap > max_days:
        return [{
            "check": "stale_market_cache",
            "severity": "warn",
            "detail": (
                f"日线数据(mode_history/date_kline)停在 {latest}，距今 {gap} 天，"
                f"minute 重建最新={reconstructed_latest or 'missing'} — 可用日线桥也陈旧，"
                f"forward_eval/假设检验可能在用陈旧日线。"
            ),
        }]
    return []


def check(
    live_dir: Path, *, today: str | None = None, cache_path: Path | None = None
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    findings += incomplete_ledger_transaction(live_dir)
    findings += duplicate_snapshots(live_dir)
    findings += account_reconciles(live_dir)
    findings += account_reconciles_book_t(live_dir)
    findings += blocked_sell_executions(live_dir)
    findings += unlabeled_closed_positions(live_dir)
    findings += stale_open_positions(live_dir, today=today)
    # Cache lives at output/.cache/xiaocao.db (sibling of output/live); callers
    # may override. A missing cache yields no finding.
    cp = cache_path if cache_path is not None else live_dir.parent / ".cache" / "xiaocao.db"
    findings += stale_market_cache(
        cp,
        reconstructed_path=live_dir / "daily_reconstructed.jsonl",
        today=today,
    )
    return {
        "findings": findings,
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "warn": sum(1 for f in findings if f["severity"] == "warn"),
        "ok": not findings,
    }
