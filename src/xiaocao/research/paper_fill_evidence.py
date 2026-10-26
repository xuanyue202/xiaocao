"""Shared classification of saved paper entry labels, never execution proof."""
from __future__ import annotations

from collections import Counter

from xiaocao.live.paper_entry_cost import CONSERVATIVE_COST_BASIS


WINDOW_BASES = {CONSERVATIVE_COST_BASIS, "opening_window_vwap", "opening_window_vwap_capped_by_limit"}


def classify_paper_fill(row: dict) -> str:
    basis = str(row.get("entry_price_basis") or row.get("price_basis") or row.get("fill_basis") or "")
    if row.get("fill_fallback") or "fallback" in basis:
        return "fallback"
    if basis in WINDOW_BASES:
        return "reported_window"
    if "retry" in basis or "proxy" in basis:
        return "proxy"
    return "unknown"


def summarize_paper_fills(classes: list[str]) -> dict:
    counts = Counter(classes)
    total = len(classes)
    return {
        "count": total,
        "counts": {key: counts[key] for key in ("reported_window", "fallback", "proxy", "unknown")},
        "classified_proportion": (total - counts["unknown"]) / total if total else None,
        "fallback_proportion": counts["fallback"] / total if total else None,
        "proxy_including_fallback_proportion": (counts["fallback"] + counts["proxy"]) / total if total else None,
        "confirmed_execution_count": 0,
        "interpretation": "saved_model_labels_without_original_window_hash_and_clock_verification",
    }
