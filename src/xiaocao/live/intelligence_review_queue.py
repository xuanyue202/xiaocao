"""Build a zero-fetch queue for agent intelligence reviews."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _date_rows(rows: list[dict[str, Any]], market_date: str) -> list[dict[str, Any]]:
    return [r for r in rows if str(r.get("date") or r.get("market_date") or "")[:10] == market_date]


def _stock_review_map(live_dir: Path, market_date: str) -> dict[str, dict[str, Any]]:
    rows = _date_rows(_read_jsonl(live_dir / "stock_sentiment_history.jsonl"), market_date)
    return {str(r.get("code") or ""): r for r in rows if r.get("code")}


def _open_book_b_map(live_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(live_dir / "positions.jsonl"):
        if row.get("status", "open") != "open":
            continue
        if str(row.get("book") or "B") != "B":
            continue
        code = str(row.get("code") or "")
        if code:
            out[code] = row
    return out


def _evidence_titles(row: dict[str, Any], *, limit: int = 5) -> list[str]:
    evidence = row.get("evidence")
    if not isinstance(evidence, list):
        return []
    titles: list[str] = []
    for item in evidence[:limit]:
        if isinstance(item, dict) and item.get("title"):
            titles.append(str(item.get("title")))
    return titles


def _priority(row: dict[str, Any], open_book_b: dict[str, dict[str, Any]]) -> tuple[int, list[str]]:
    code = str(row.get("code") or "")
    ctx = row.get("candidate_context") if isinstance(row.get("candidate_context"), dict) else {}
    reasons: list[str] = []
    score = 0
    if code in open_book_b:
        score += 100
        reasons.append("open_book_b_position")
    if ctx.get("mode_exec_star"):
        score += 90
        reasons.append("mode_exec_star")
    elif ctx.get("vb_star"):
        score += 80
        reasons.append("vb_star")
    elif ctx.get("kp_star"):
        score += 70
        reasons.append("kp_star")
    if ctx.get("mode_star"):
        score += 20
        reasons.append("mode_star")
    if ctx.get("qibaoBenchmarkLayer") == "paper_buy":
        score += 10
        reasons.append("qibao_benchmark_paper_buy")
    if str(row.get("data_quality") or "") == "ok":
        score += 5
        reasons.append("evidence_ok")
    evidence_count = int(row.get("evidence_count") or 0)
    score += min(evidence_count, 5)
    if evidence_count:
        reasons.append(f"evidence_count={evidence_count}")
    return score, reasons


def build_review_queue(
    *,
    live_dir: Path,
    market_date: str,
    limit: int = 8,
    now: datetime | None = None,
) -> dict[str, Any]:
    market_date = market_date[:10]
    now = now or datetime.now()
    evidence_rows = _date_rows(_read_jsonl(live_dir / f"intelligence_evidence_{market_date}.jsonl"), market_date)
    reviews = _stock_review_map(live_dir, market_date)
    open_book_b = _open_book_b_map(live_dir)

    items: list[dict[str, Any]] = []
    for row in evidence_rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        review = reviews.get(code, {})
        reviewed = str(review.get("score_source") or "") == "agent_review"
        if reviewed:
            continue
        ctx = row.get("candidate_context") if isinstance(row.get("candidate_context"), dict) else {}
        score, reasons = _priority(row, open_book_b)
        if score <= 0:
            continue
        open_position = open_book_b.get(code, {})
        items.append({
            "code": code,
            "name": row.get("name") or ctx.get("name") or open_position.get("name"),
            "priority": score,
            "priority_reasons": reasons,
            "review_scope": "short",
            "score_source": review.get("score_source") or "pending_agent_review",
            "data_quality": row.get("data_quality"),
            "evidence_count": row.get("evidence_count") or 0,
            "evidence_ref": f"output/live/intelligence_evidence_{market_date}.jsonl#code={code}",
            "candidate_context": {
                "mode": ctx.get("mode"),
                "rank_score": ctx.get("rank_score"),
                "primary_score": ctx.get("primary_score"),
                "quality_tag": ctx.get("quality_tag"),
                "kp_star": ctx.get("kp_star"),
                "vb_star": ctx.get("vb_star"),
                "vb_rank": ctx.get("vb_rank"),
                "mode_star": ctx.get("mode_star"),
                "mode_exec_star": ctx.get("mode_exec_star"),
                "mode_exec_rank": ctx.get("mode_exec_rank"),
                "mode_exec_target_weight": ctx.get("mode_exec_target_weight"),
                "mode_state": ctx.get("mode_state"),
                "mode_state_window": ctx.get("mode_state_window"),
                "mode_alpha_pool": ctx.get("mode_alpha_pool"),
                "mode_alpha_pool_lcb80": ctx.get("mode_alpha_pool_lcb80"),
                "open_pct_change": ctx.get("open_pct_change"),
                "auc_pct": ctx.get("auc_pct"),
                "qibaoBenchmarkKind": ctx.get("qibaoBenchmarkKind"),
                "qibaoBenchmarkLayer": ctx.get("qibaoBenchmarkLayer"),
            },
            "open_position": {
                "entry_date": open_position.get("entry_date"),
                "entry_price": open_position.get("entry_price"),
                "profile": open_position.get("profile"),
                "shares": open_position.get("shares"),
            } if open_position else None,
            "top_evidence_titles": _evidence_titles(row),
        })

    items.sort(key=lambda item: (-int(item.get("priority") or 0), str(item.get("code") or "")))
    selected = items[: max(0, limit)]
    return {
        "schema_version": 1,
        "market_date": market_date,
        "generated_at": now.isoformat(timespec="seconds"),
        "fetch_policy": "zero_fetch_existing_artifacts_only",
        "review_scope": "short",
        "status": "ready" if selected else "empty",
        "counts": {
            "evidence_rows": len(evidence_rows),
            "pending_items": len(items),
            "selected_items": len(selected),
            "open_book_b_positions": len(open_book_b),
            "score_source": dict(Counter(str(r.get("score_source") or "pending_agent_review") for r in reviews.values())),
        },
        "items": selected,
    }


def write_review_queue(path: Path, queue: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(queue, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
