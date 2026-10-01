"""Observe frozen legacy paper ledgers without I/O or execution authority.

Amounts are recorded modeled cash facts, not portfolio NAV or APP fills. A
calendar-date cutoff cannot establish what was available at an intraday instant.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from xiaocao.live.paper_research import day, money, number

POSITIONS = "output/live/positions.jsonl"
TRADES = "output/live/paper_trades.jsonl"
BOOKS = ("A", "B", "T")


def _identity(row: dict, date_field: str) -> tuple:
    book, code = row.get("book"), row.get("code")
    if book not in BOOKS or not isinstance(code, str) or not re.fullmatch(r"\d{6}\.(XSHG|XSHE|BJSE)", code):
        raise ValueError("invalid_explicit_book_or_code")
    return book, code, day(row.get(date_field))


def _shares(row: dict) -> Decimal:
    value = number(row.get("shares"), "shares")
    if value <= 0 or value != value.to_integral_value():
        raise ValueError("shares_must_be_positive_integer")
    return value


def _amount(row: dict, key: str) -> Decimal:
    return money(row.get(key), key, nonnegative=True)


def _price(row: dict, key: str) -> Decimal:
    value = number(row.get(key), key)
    if value <= 0:
        raise ValueError(f"{key}: nonpositive price")
    return value


def _cash_equal(left: Decimal, right: Decimal, label: str) -> None:
    if left != right:
        raise ValueError(label)


def _price_matches(price: Decimal, gross: Decimal, shares: Decimal, digits: int) -> None:
    # Production stores entry at 3dp and exit at 4dp after calculating cash.
    if abs(price * shares - gross) > shares * Decimal(10) ** (-digits) / 2 + Decimal("0.005"):
        raise ValueError("price_quantity_cash_mismatch")


def _entry(row: dict) -> dict:
    shares = _shares(row)
    price = _price(row, "entry_price")
    gross, fee, cash = (_amount(row, key) for key in ("gross_notional", "entry_fee", "entry_cash_out"))
    if gross <= 0 or cash <= 0:
        raise ValueError("nonpositive_entry_cash")
    _cash_equal(gross + fee, cash, "entry_cash_identity_mismatch")
    _price_matches(price, gross, shares, 3)
    return {"shares": shares, "price": price, "gross": gross, "entry_fee": fee, "cash_out": cash}


def _trade_matches(row: dict, fact: dict, *, sell: bool = False) -> None:
    shares = _shares(row)
    _cash_equal(shares, fact["shares"], "trade_shares_mismatch")
    gross = _amount(row, "gross_notional")
    fee = _amount(row, "fee")
    _cash_equal(gross, fact["exit_gross" if sell else "gross"], "trade_gross_mismatch")
    _cash_equal(fee, fact["exit_fee" if sell else "entry_fee"], "trade_fee_mismatch")
    price = _price(row, "price")
    _price_matches(price, gross, shares, 4 if sell else 3)
    if abs(price - fact["exit_price" if sell else "price"]) > Decimal("0.00005" if sell else "0.0005"):
        raise ValueError("trade_price_mismatch")
    for key, expected in (("exit_cash_in", gross - fee),) if sell else (("entry_cash_out", gross + fee),):
        if key in row:
            _cash_equal(_amount(row, key), expected, f"trade_{key}_mismatch")
    if sell:
        _cash_equal(money(row.get("realized_pnl"), "realized_pnl"), fact["net"], "trade_realized_pnl_mismatch")


def _aggregate(facts: list[dict]) -> dict:
    closed = [row for row in facts if row["closed"]]
    return {
        "valid_lots": len(facts), "closed_lots": len(closed), "open_lots": len(facts) - len(closed),
        "entry_fee": float(sum((row["entry_fee"] for row in facts), Decimal(0))) if facts else None,
        "exit_fee": float(sum((row["exit_fee"] for row in closed), Decimal(0))) if closed else None,
        "closed_cash_net_change": float(sum((row["net"] for row in closed), Decimal(0))) if closed else None,
        "mean_closed_lot_return_pct": float(sum((row["net"] / row["cash_out"] * 100 for row in closed), Decimal(0)) / len(closed)) if closed else None,
        "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
    }


def _paired(facts: list[dict], audit: list[dict]) -> dict:
    groups = defaultdict(dict)
    for fact in facts:
        if fact["book"] in ("A", "B"):
            groups[(fact["code"], fact["entry_date"])][fact["book"]] = fact
    counts = Counter(eligible=0, open=0, unmatched=0, entry_mismatch=0, censored=0)
    differences = []
    pairs = []
    for (code, entry_date), books in sorted(groups.items()):
        if set(books) != {"A", "B"}:
            counts["unmatched"] += 1
            continue
        a, b = books["A"], books["B"]
        if any(a[key] != b[key] for key in ("price", "shares", "gross", "cash_out")):
            counts["entry_mismatch"] += 1
            continue
        if not a["closed"] or not b["closed"]:
            counts["open"] += 1
            counts["censored"] += 1
            continue
        diff = (b["net"] / b["cash_out"] - a["net"] / a["cash_out"]) * 100
        differences.append(diff)
        pairs.append({"code": code, "entry_date": entry_date, "b_minus_a_pp": float(diff)})
        counts["eligible"] += 1
    counts["unknown_lots"] = sum(row["state"] == "unknown" and row.get("book") in ("A", "B") for row in audit)
    counts["excluded"] = counts["open"] + counts["unmatched"] + counts["entry_mismatch"]
    return {**counts, "mean_b_minus_a_pp": float(sum(differences) / len(differences)) if differences else None,
            "pairs": pairs, "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias"}


def build_production_observations(contents: dict[str, bytes], *, as_of: date) -> dict:
    """Return auditable observations of the supplied frozen bytes only."""
    cutoff = day(as_of.isoformat())
    sources, parsed, bad = [], {}, []
    dates = []
    for path in (POSITIONS, TRADES):
        raw = contents.get(path)
        source = {"path": path, "status": "missing" if raw is None else "captured",
                  "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None}
        rows, source_dates = [], []
        if raw is not None:
            for line_no, line in enumerate(raw.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("expected_object")
                except (ValueError, UnicodeError):
                    bad.append({"source": path, "line": line_no, "state": "bad", "reason": "invalid_json_object"})
                    continue
                rows.append((line_no, row))
                for key in ("entry_date", "exit_date") if path == POSITIONS else ("date",):
                    try:
                        observed_day = day(row.get(key))
                    except (ValueError, TypeError):
                        continue
                    if observed_day <= cutoff:
                        dates.append(observed_day)
                        source_dates.append(observed_day)
        source["parsed_records"] = len(rows)
        source["latest_record_date"] = max(source_dates) if source_dates else None
        sources.append(source)
        parsed[path] = rows

    audit = list(bad)
    trades = defaultdict(list)
    for line_no, row in parsed[TRADES]:
        try:
            book, code, trade_day = _identity(row, "date")
            if trade_day > cutoff:
                continue
            if row.get("side") not in ("BUY", "SELL"):
                raise ValueError("invalid_side")
            trades[(book, code, trade_day, row["side"])].append((line_no, row))
        except (ValueError, TypeError) as error:
            audit.append({"source": TRADES, "line": line_no, "state": "unknown", "reason": str(error)})

    identities, sell_owners = Counter(), Counter()
    for _, row in parsed[POSITIONS]:
        try:
            identity = _identity(row, "entry_date")
            identities[identity] += 1
            if row.get("status") == "closed":
                exit_day = day(row.get("exit_date"))
                if identity[2] <= exit_day <= cutoff:
                    sell_owners[(identity[0], identity[1], exit_day, "SELL")] += 1
        except (ValueError, TypeError):
            pass
    facts, used = [], set()
    for line_no, row in parsed[POSITIONS]:
        item = {"source": POSITIONS, "line": line_no, "book": row.get("book"), "code": row.get("code"),
                "entry_date": row.get("entry_date"), "state": "unknown"}
        repair_notes = {key: row[key] for key in ("_rederive_note", "ledger_repair_id") if key in row}
        if repair_notes:
            item["historical_repair_annotation"] = repair_notes
        try:
            book, code, entry_day = _identity(row, "entry_date")
            if entry_day > cutoff:
                item.update(state="future", reason="entry_after_as_of")
                audit.append(item)
                continue
            if identities[(book, code, entry_day)] != 1:
                raise ValueError("duplicate_position_identity")
            fact = {**_entry(row), "book": book, "code": code, "entry_date": entry_day, "closed": False}
            buy_key = book, code, entry_day, "BUY"
            buys = trades.get(buy_key, [])
            if len(buys) != 1:
                raise ValueError("missing_or_duplicate_buy_trade")
            item["buy_trade_line"] = buys[0][0]
            used.add(buy_key)
            _trade_matches(buys[0][1], fact)
            if row.get("status") not in ("closed", "open"):
                raise ValueError("invalid_position_status")
            exit_day = day(row.get("exit_date")) if row["status"] == "closed" else None
            if exit_day is not None and exit_day < entry_day:
                raise ValueError("exit_before_entry")
            if row["status"] == "open" and row.get("exit_date"):
                raise ValueError("open_position_has_exit_date")
            if exit_day is not None and exit_day <= cutoff:
                cash, fee = _amount(row, "exit_cash_in"), _amount(row, "exit_fee")
                gross, price = cash + fee, _price(row, "exit_price")
                _price_matches(price, gross, fact["shares"], 4)
                net = cash - fact["cash_out"]
                _cash_equal(money(row.get("realized_pnl"), "realized_pnl"), net, "position_realized_pnl_mismatch")
                fact.update(closed=True, exit_fee=fee, exit_price=price, exit_gross=gross, net=net)
                sell_key = book, code, exit_day, "SELL"
                sells = trades.get(sell_key, [])
                if len(sells) != 1 or sell_owners[sell_key] != 1:
                    raise ValueError("missing_duplicate_or_ambiguous_sell_trade")
                item["sell_trade_line"] = sells[0][0]
                used.add(sell_key)
                _trade_matches(sells[0][1], fact, sell=True)
                if sells[0][1].get("entry_date", entry_day) != entry_day:
                    raise ValueError("sell_entry_identity_mismatch")
            else:
                # A mature SELL on an allegedly open lot is inconsistent. A future
                # closure and its future economic fields do not enter old metrics.
                if any(key[:2] == (book, code) and key[3] == "SELL" and key[2] >= entry_day and not sell_owners[key]
                       for key in trades):
                    raise ValueError("open_position_has_unmatched_mature_sell")
            item.update(state="valid", maturity="closed" if fact["closed"] else "immature")
            fact["entry_price_basis"] = row.get("entry_price_basis")
            facts.append(fact)
        except (ValueError, TypeError, OverflowError) as error:
            item["reason"] = str(error)
            if repair_notes:
                item["repair_link_status"] = "unverified_original_to_rederived_link"
        audit.append(item)

    for key, rows in trades.items():
        if key not in used:
            for line_no, _ in rows:
                audit.append({"source": TRADES, "line": line_no, "state": "unknown", "reason": "unmatched_trade"})
    counts = Counter(row["state"] for row in audit if row["source"] == POSITIONS)
    counts["bad"] = len(bad)
    counts["immature"] = sum(not fact["closed"] for fact in facts)
    counts["closed"] = sum(fact["closed"] for fact in facts)
    counts["unknown_trades"] = sum(row["source"] == TRADES and row["state"] == "unknown" for row in audit)
    for key in ("valid", "unknown", "future", "bad"):
        counts.setdefault(key, 0)
    latest = max(dates) if dates else None
    windows = {}
    for weeks in (1, 4, 12):
        start = (as_of - timedelta(days=weeks * 7 - 1)).isoformat()
        cohort = [fact for fact in facts if fact["entry_date"] >= start]
        window_audit = [row for row in audit if isinstance(row.get("entry_date"), str) and start <= row["entry_date"] <= cutoff]
        windows[f"{weeks}w"] = {"start": start, "end": cutoff, "valid_lots": len(cohort),
                               "status": "observed" if cohort else "no_valid_lots",
                               "latest_data_before_window": latest is None or latest < start,
                               "books": {book: _aggregate([fact for fact in cohort if fact["book"] == book]) for book in BOOKS},
                               "paired_exit_comparison": _paired(cohort, window_audit)}
    return {"as_of": cutoff, "sources": sources, "latest_record_date": latest,
            "staleness_calendar_days": (as_of - date.fromisoformat(latest)).days if latest else None,
            "counts": dict(counts), "books": {book: _aggregate([fact for fact in facts if fact["book"] == book]) for book in BOOKS},
            "windows": windows, "paired_exit_comparison": _paired(facts, audit), "audit": audit,
            "timeliness_proven": False,
            "fill_basis_counts": dict(Counter(fact.get("entry_price_basis") or "missing" for fact in facts)),
            "limitations": ["Legacy date/naive clocks lack verified availability time and timezone; no intraday timeliness proof.",
                            "Modeled paper fees and cash changes are not actual broker fees, executable alpha or portfolio NAV.",
                            "A/B identical-entry closed-lot comparison has selection/censoring bias and is not KOL alpha.",
                            "No no-KOL/current/challenger strategy runs inferred; no source truth repaired."]}


def render_production_observations(report: dict) -> list[str]:
    if not report:
        return ["此份旧周度计划未保存生产纸盘观察，结果缺失。"]
    counts = report["counts"]
    lines = [f"生产纸盘观察截至 {report['as_of']}；最新原记录日期 {report['latest_record_date'] or '缺失'}，"
             f"相距 {report['staleness_calendar_days']} 个自然日。",
             f"有效仓 {counts['valid']}、未知仓 {counts['unknown']}、坏记录 {counts['bad']}、未成熟仓 {counts['immature']}；"
             "旧日期/naive 时钟缺时区与可用时点证明。"]
    for book, values in report["books"].items():
        amounts = {key: "N/A" if values[key] is None else f"{values[key]:.2f}"
                   for key in ("entry_fee", "exit_fee", "closed_cash_net_change")}
        lines.append(f"Book {book}：有效/闭仓 {values['valid_lots']}/{values['closed_lots']}；"
                     f"有效子集模型买费 {amounts['entry_fee']}，卖费 {amounts['exit_fee']}，闭仓现金净变动 {amounts['closed_cash_net_change']}。")
    paired = report["paired_exit_comparison"]
    difference = "N/A" if paired['mean_b_minus_a_pp'] is None else f"{paired['mean_b_minus_a_pp']:.4f}"
    lines.append(f"同进场 A/B 闭仓配对 {paired['eligible']}，B−A均值 {difference} pp；"
                 f"有效分组排除 {paired['excluded']}（开放 {paired['open']}、未匹配 {paired['unmatched']}、进场不一致 {paired['entry_mismatch']}）；另有未知仓 {paired['unknown_lots']}。")
    for name, window in report["windows"].items():
        lines.append(f"{name} 进场窗口 {window['start']}–{window['end']}：有效 {window['valid_lots']}；"
                     f"最新数据在窗口前={window['latest_data_before_window']}。")
    lines.append("以上仅为原始现金事实的描述性观察，非组合NAV、APP成交或KOL增益；闭仓选择偏差与未成熟删失仍在。")
    return lines
