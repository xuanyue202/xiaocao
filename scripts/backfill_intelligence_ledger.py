#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import agent_signals, intelligence, intelligence_policy  # noqa: E402


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


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def rebuild_stock_intelligence_signals(path: Path, signals: list[dict[str, Any]]) -> None:
    kept: list[dict[str, Any]] = []
    if path.exists():
        for row in _read_jsonl(path):
            if str(row.get("source") or "") == "stock_intelligence":
                continue
            kept.append(row)
    _write_jsonl(path, kept + signals)


def normalize_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        date = str(row.get("date") or row.get("tradeDate") or "")[:10]
        code = str(row.get("code") or row.get("stockId") or "")
        if not date or not code:
            continue
        name = str(row.get("name") or "")
        normalized = intelligence.normalize_stock_intelligence_record(
            row,
            date=date,
            code=code,
            name=name,
        )
        out[(date, code)] = normalized
    return [out[key] for key in sorted(out)]


def merge_signal_snapshots(live: Path, records: list[dict[str, Any]]) -> int:
    path = live / "signal_snapshots.jsonl"
    if not path.exists() or not records:
        return 0
    by_key = {
        (str(row.get("date") or "")[:10], str(row.get("code") or "")): row
        for row in records
        if row.get("date") and row.get("code")
    }
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        d = str(row.get("date") or "")[:10]
        if d:
            by_date.setdefault(d, []).append(row)
    short_by_date = {
        d: intelligence.short_shadow_rank_map(rows)
        for d, rows in by_date.items()
    }
    touched_dates = set(by_date)
    changed = 0
    out: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            d = str(row.get("date") or "")[:10]
            if d in touched_dates:
                row["intelligence_long_star"] = False
                row["intelligence_long_rank"] = 9999
                row["intelligence_long_score"] = None
                row["intelligence_long_threshold"] = 0.2
                row["intelligence_long_surface"] = "shadow_ab"
                row["ai_intelligence_short_star"] = False
                row["ai_intelligence_short_rank"] = 9999
                row["ai_intelligence_short_score"] = None
                row["ai_intelligence_short_threshold"] = 0.2
                row["ai_intelligence_short_surface"] = "shadow_ab"
                rec = by_key.get((d, str(row.get("code") or "")))
                if rec is not None:
                    row["stock_sentiment_score"] = rec.get("score")
                    row["stock_sentiment_label"] = rec.get("label")
                    row["stock_sentiment_summary"] = rec.get("summary")
                    row["stock_sentiment_source"] = rec.get("source")
                    row["stock_sentiment_decision_used"] = bool(rec.get("decision_used", False))
                    row["stock_sentiment_target_set"] = rec.get("target_set")
                    row["stock_sentiment_data_quality"] = rec.get("data_quality")
                    row["stock_sentiment_evidence_state"] = rec.get("evidence_state")
                    row["stock_sentiment_authority"] = rec.get("authority", 0)
                    row["stock_sentiment_relevance_counts"] = rec.get("relevance_counts") or {}
                    row["score_source"] = rec.get("score_source")
                    row["agent_score"] = rec.get("agent_score")
                    row["agent_short_score"] = rec.get("agent_short_score")
                    row["agent_trend_score"] = rec.get("agent_trend_score")
                    row["veto_flags"] = rec.get("veto_flags") or []
                    row["intelligence_factor_score_source"] = rec.get("score_source")
                    row["intelligence_factor_keyword_score"] = rec.get("keyword_score")
                    row["intelligence_factor_agent_score"] = rec.get("agent_score")
                    row["intelligence_factor_short_score"] = rec.get("agent_short_score")
                    row["intelligence_factor_trend_score"] = rec.get("agent_trend_score")
                    row["intelligence_factor_trend_label"] = rec.get("trend_label")
                    row["intelligence_veto_flags"] = rec.get("veto_flags") or []
                    veto_state = intelligence_policy.hard_veto_state(rec, asof=f"{d}T09:30:00+08:00")
                    row["ai_hard_veto"] = bool(veto_state.get("hard_veto"))
                    row["ai_hard_veto_event_types"] = veto_state.get("event_types") or []
                    row["ai_hard_veto_reason"] = veto_state.get("reason") or ""
                    usage = rec.get("usage") if isinstance(rec.get("usage"), dict) else {}
                    exit_composite_input = bool(usage.get("exit_composite_input", False))
                    if rec.get("score_source") == "agent_review":
                        exit_composite_input = False
                    row["stock_sentiment_exit_composite_input"] = exit_composite_input
                    row["stock_sentiment_buy_ranking_used"] = bool(usage.get("buy_ranking", False))
                    short_flags = short_by_date.get(d, {}).get(str(row.get("code") or ""))
                    if short_flags:
                        row.update(short_flags)
                changed += 1
            out.append(json.dumps(row, ensure_ascii=False, default=str))
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize cached one-line intelligence and backfill AgentSignalLedger.")
    ap.add_argument("--live-dir", default=str(ROOT / "output" / "live"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    live = Path(args.live_dir)
    history_path = live / "stock_sentiment_history.jsonl"
    current_path = live / "stock_sentiment.json"
    ledger_path = live / "agent_signals.jsonl"
    normalized = normalize_history(_read_jsonl(history_path))
    signals = agent_signals.signals_from_intelligence_records(normalized)
    snapshot_rows = 0
    if not args.dry_run:
        _write_jsonl(history_path, normalized)
        if normalized:
            latest_date = max(str(row.get("date") or "")[:10] for row in normalized)
            current = [row for row in normalized if str(row.get("date") or "")[:10] == latest_date]
            current_path.write_text(json.dumps(current, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        rebuild_stock_intelligence_signals(ledger_path, signals)
        snapshot_rows = merge_signal_snapshots(live, normalized)
    print(
        f"normalized={len(normalized)} signals={len(signals)} snapshot_rows={snapshot_rows} "
        f"history={history_path} ledger={ledger_path} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
