"""Conservative Book-A/Book-B exit attribution on an identical cohort."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def paired_exit_attribution(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare normalized returns only when entry identity is truly identical.

    A valid pair has one A and one B row with the same code, entry date, shares,
    and entry price; both must be closed.  This isolates the exit rule from
    cohort/allocation drift.  The result is descriptive and does not establish
    causality by itself.
    """
    grouped: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"A": [], "B": []}
    )
    for row in positions:
        book = str(row.get("book") or "B")
        if book not in {"A", "B"}:
            continue
        key = (str(row.get("entry_date") or "")[:10], str(row.get("code") or ""))
        if all(key):
            grouped[key][book].append(row)

    excluded: Counter[str] = Counter()
    pairs: list[dict[str, Any]] = []
    for (entry_date, code), books in sorted(grouped.items()):
        if not books["A"]:
            excluded["missing_book_a"] += 1
            continue
        if not books["B"]:
            excluded["missing_book_b"] += 1
            continue
        if len(books["A"]) != 1 or len(books["B"]) != 1:
            excluded["ambiguous_duplicate"] += 1
            continue
        a, b = books["A"][0], books["B"][0]
        if a.get("status") != "closed" or b.get("status") != "closed":
            excluded["not_both_closed"] += 1
            continue
        if int(a.get("shares") or 0) != int(b.get("shares") or 0):
            excluded["shares_mismatch"] += 1
            continue
        a_entry, b_entry = _f(a.get("entry_price")), _f(b.get("entry_price"))
        if a_entry is None or b_entry is None or abs(a_entry - b_entry) > 0.0001:
            excluded["entry_price_mismatch"] += 1
            continue
        a_cost, b_cost = _f(a.get("entry_cash_out")), _f(b.get("entry_cash_out"))
        a_pnl, b_pnl = _f(a.get("realized_pnl")), _f(b.get("realized_pnl"))
        if not a_cost or not b_cost or a_pnl is None or b_pnl is None:
            excluded["invalid_return_fields"] += 1
            continue
        a_ret = a_pnl / a_cost * 100.0
        b_ret = b_pnl / b_cost * 100.0
        pairs.append({
            "entry_date": entry_date,
            "code": code,
            "a_return_pct": a_ret,
            "b_return_pct": b_ret,
            "b_minus_a_pp": b_ret - a_ret,
        })

    return {
        "eligible_pairs": len(pairs),
        "candidate_keys": len(grouped),
        "mean_a_return_pct": mean(p["a_return_pct"] for p in pairs) if pairs else None,
        "mean_b_return_pct": mean(p["b_return_pct"] for p in pairs) if pairs else None,
        "mean_b_minus_a_pp": mean(p["b_minus_a_pp"] for p in pairs) if pairs else None,
        "b_better_pairs": sum(1 for p in pairs if p["b_minus_a_pp"] > 0),
        "excluded": dict(sorted(excluded.items())),
        "interpretation": "descriptive_only",
        "pairs": pairs,
    }
