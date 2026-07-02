"""Live decision-context builders — the pure/file-based inputs to the composite
score, extracted from scripts/live_monitor.py so they become independently
unit-testable (they feed the staged-exit decision but were only covered
indirectly before).

Extracted verbatim; behaviour is unchanged. Only the single-copy, deterministic
builders live here — the client-dependent regime/smallgrass builders stay in
live_monitor (they need a live XiaocaoClient and aren't duplicated). See
docs/OPERATING_CONTRACT.md §2.

NOTE: `_load_stock_sentiment_map` is intentionally NOT unified here. live_monitor
and live_recommend have DIVERGENT copies (live_monitor computes+clamps a score
and drops unparseable items; live_recommend stores the raw item) — reconciling
them is a semantic decision that needs validation, not a mechanical dedup.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xiaocao.live.exit_policy import clamp


def load_signal_snapshot_map(path: Path) -> dict[tuple[str, str, str], dict[str, object]]:
    """Latest snapshot per (date, code, book) from signal_snapshots.jsonl.

    Legacy rows without `book` are Book B.
    """
    if not path.exists():
        return {}
    out: dict[tuple[str, str, str], dict[str, object]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            code = str(row.get("code") or "")
            date = str(row.get("date") or "")[:10]
            if not code or not date:
                continue
            book = str(row.get("book") or "B")
            key = (date, code, book)
            prev = out.get(key)
            if prev is None or str(row.get("captured_at") or "") >= str(prev.get("captured_at") or ""):
                out[key] = row
    return out


def kronos_context(position: dict, snapshot_map: dict[Any, dict[str, object]]) -> dict[str, object]:
    code = str(position.get("code") or "")
    entry_date = str(position.get("entry_date") or "")[:10]
    book = str(position.get("book") or "B")
    row = snapshot_map.get((entry_date, code, book)) or snapshot_map.get((entry_date, code)) or {}

    def _num(key: str) -> float | None:
        value = row.get(key, position.get(key))
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    p_score = _num("p_score")
    k_score = _num("k_score")
    score = 0.0
    if p_score is not None:
        score += 0.6 * clamp(p_score / 3.0)
    if k_score is not None:
        score += 0.2 * clamp(k_score / 3.0)
    if bool(row.get("vb_star", position.get("vb_star", False))):
        score += 0.2
    elif bool(row.get("kp_star", position.get("kp_star", False))):
        score += 0.1
    return {
        "score": round(clamp(score), 4),
        "p_score": p_score,
        "k_score": k_score,
        "vb_star": bool(row.get("vb_star", position.get("vb_star", False))),
        "kp_star": bool(row.get("kp_star", position.get("kp_star", False))),
    }


def stock_sentiment_context(
    code: str,
    *,
    smallgrass: dict[str, object],
    sentiment_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    external = sentiment_map.get(code)
    proxy_score = float(smallgrass.get("score", 0.0) or 0.0)
    if external is not None:
        ext_score = float(external.get("score", 0.0) or 0.0)
        score = clamp(0.7 * ext_score + 0.3 * proxy_score)
        source = "external+smallgrass"
    else:
        ext_score = None
        score = clamp(proxy_score)
        source = str(smallgrass.get("source") or "smallgrass_proxy")
    return {
        "score": round(score, 4),
        "source": source,
        "external_score": ext_score,
        "proxy_score": round(proxy_score, 4),
    }
