#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from xiaocao.live import agent_signals, intelligence  # noqa: E402
from backfill_intelligence_ledger import _read_jsonl, _write_jsonl, merge_signal_snapshots, normalize_history  # noqa: E402


def _load_review(args: argparse.Namespace) -> dict[str, Any]:
    if args.review_json:
        payload = json.loads(args.review_json)
    elif args.review_file:
        payload = json.loads(Path(args.review_file).read_text(encoding="utf-8"))
    else:
        payload = {}
    payload.update({
        "label": args.label or payload.get("label"),
        "summary": args.summary or payload.get("summary"),
        "thesis": args.thesis or payload.get("thesis"),
        "confidence": args.confidence if args.confidence is not None else payload.get("confidence", 0.0),
        "action_bias": args.action_bias or payload.get("action_bias") or ("long_shadow" if args.scope == "short" else "trend_review"),
        "horizon": args.scope,
        "reviewer": args.reviewer or payload.get("reviewer") or "codex_agent",
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
    })
    if args.scope == "short":
        payload.pop("trend_score", None)
        short_score = args.short_score if args.short_score is not None else args.score
        payload["short_score"] = short_score if short_score is not None else payload.get("short_score", payload.get("agent_score", payload.get("score")))
    else:
        for key in ("score", "short_score", "agent_score"):
            payload.pop(key, None)
        payload["trend_score"] = args.trend_score if args.trend_score is not None else payload.get("trend_score")
    if args.evidence_for:
        payload["evidence_for"] = args.evidence_for
    if args.evidence_against:
        payload["evidence_against"] = args.evidence_against
    if args.risk:
        payload["risks"] = args.risk
    if args.veto_flag:
        payload["veto_flags"] = [json.loads(item) for item in args.veto_flag]
    if args.score_elapsed_ms is not None:
        payload["score_elapsed_ms"] = args.score_elapsed_ms
    if args.scorer_mode:
        payload["scorer_mode"] = args.scorer_mode
    if args.evidence_freeze_ref:
        payload["evidence_freeze_ref"] = args.evidence_freeze_ref
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Write an agent-reviewed AI intelligence factor into live artifacts.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--code", required=True)
    ap.add_argument("--scope", choices=("short", "trend"), default="short",
                    help="short runs in the morning fast path; trend is a separate slower review")
    ap.add_argument("--score", type=float, default=None, help="alias for --short-score")
    ap.add_argument("--short-score", type=float, default=None, help="fast short-line agent score in [-1,1]")
    ap.add_argument("--trend-score", type=float, default=None, help="slower trend agent score in [-1,1]; use with --scope trend")
    ap.add_argument("--label", default="")
    ap.add_argument("--summary", default="")
    ap.add_argument("--thesis", default="")
    ap.add_argument("--confidence", type=float, default=None)
    ap.add_argument("--action-bias", default="", help="long_shadow/trend_review/avoid/neutral")
    ap.add_argument("--evidence-for", action="append", default=[])
    ap.add_argument("--evidence-against", action="append", default=[])
    ap.add_argument("--risk", action="append", default=[])
    ap.add_argument("--reviewer", default="codex_agent")
    ap.add_argument("--review-json", default="")
    ap.add_argument("--review-file", default="")
    ap.add_argument("--veto-flag", action="append", default=[],
                    help="JSON object from the hard-veto taxonomy; repeatable")
    ap.add_argument("--score-elapsed-ms", type=int, default=None)
    ap.add_argument("--scorer-mode", default="", help="parent|subagent|offline_replay")
    ap.add_argument("--evidence-freeze-ref", default="")
    ap.add_argument("--live-dir", default=str(ROOT / "output" / "live"))
    args = ap.parse_args()
    if args.scope == "short":
        if args.trend_score is not None:
            ap.error("--scope short must not include --trend-score; run a separate --scope trend pass later")
        if args.score is None and args.short_score is None and not args.review_json and not args.review_file:
            ap.error("--scope short requires --short-score/--score or a review payload")
    if args.scope == "trend":
        if args.score is not None or args.short_score is not None:
            ap.error("--scope trend must not include --short-score/--score; short is a separate morning pass")
        if args.trend_score is None and not args.review_json and not args.review_file:
            ap.error("--scope trend requires --trend-score or a review payload")

    live = Path(args.live_dir)
    history_path = live / "stock_sentiment_history.jsonl"
    rows = normalize_history(_read_jsonl(history_path))
    key = (args.date[:10], args.code)
    found = False
    review = _load_review(args)
    out: list[dict[str, Any]] = []
    for row in rows:
        if (str(row.get("date") or "")[:10], str(row.get("code") or "")) == key:
            row = intelligence.apply_agent_review(row, review)
            found = True
        out.append(row)
    if not found:
        print(f"no intelligence evidence row found for {key}; run live_recommend/backfill first", file=sys.stderr)
        return 1
    _write_jsonl(history_path, out)
    latest_date = max(str(row.get("date") or "")[:10] for row in out)
    current = [row for row in out if str(row.get("date") or "")[:10] == latest_date]
    (live / "stock_sentiment.json").write_text(
        json.dumps(current, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    agent_signals.upsert_signals(live / "agent_signals.jsonl", agent_signals.signals_from_intelligence_records(out))
    snapshot_rows = merge_signal_snapshots(live, out)
    if args.scope == "short":
        short_score = args.short_score if args.short_score is not None else args.score
        score_text = "None" if short_score is None else f"{short_score:+.2f}"
    else:
        score_text = "None" if args.trend_score is None else f"{args.trend_score:+.2f}"
    print(f"agent_review applied scope={args.scope} date={args.date[:10]} code={args.code} score={score_text} snapshot_rows={snapshot_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
