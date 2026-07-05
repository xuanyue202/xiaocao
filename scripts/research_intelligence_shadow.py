#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


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
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def _load_training_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd  # type: ignore
    except Exception:
        print("pandas is required to read training_rows.parquet; install xiaocao[data]", file=sys.stderr)
        return []
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    return df.to_dict("records")


def _ret(row: dict[str, Any]) -> float | None:
    value = row.get("net_realized_ret", row.get("realized_ret"))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rets = [float(r["ret"]) for r in rows if r.get("ret") is not None]
    days = sorted({str(r.get("date")) for r in rows if r.get("date")})
    return {
        "n": len(rets),
        "days": len(days),
        "mean_ret": (sum(rets) / len(rets)) if rets else None,
        "win_rate": (sum(1 for r in rets if r > 0) / len(rets)) if rets else None,
    }


def evaluate(
    *,
    sentiment_rows: list[dict[str, Any]],
    training_rows: list[dict[str, Any]],
    start: str,
    end: str,
    threshold: float,
) -> dict[str, Any]:
    returns: dict[tuple[str, str], dict[str, Any]] = {}
    for row in training_rows:
        key = (str(row.get("date") or "")[:10], str(row.get("code") or ""))
        ret = _ret(row)
        if key[0] and key[1] and ret is not None:
            returns[key] = {"ret": ret, "mode": row.get("mode"), "book": row.get("book", "B")}

    joined: list[dict[str, Any]] = []
    for row in sentiment_rows:
        d = str(row.get("date") or "")[:10]
        code = str(row.get("code") or "")
        if not d or not code or d < start or d > end:
            continue
        ret_row = returns.get((d, code))
        if ret_row is None:
            continue
        try:
            score = float(row.get("score", row.get("sentiment_score", 0.0)) or 0.0)
        except (TypeError, ValueError):
            continue
        joined.append({
            "date": d,
            "code": code,
            "name": row.get("name"),
            "score": score,
            "label": row.get("label"),
            "ret": ret_row["ret"],
            "target_set": row.get("target_set"),
            "data_quality": row.get("data_quality", "legacy"),
        })

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in joined:
        buckets["all"].append(row)
        if row["score"] >= threshold:
            buckets["bullish"].append(row)
        elif row["score"] <= -threshold:
            buckets["bearish"].append(row)
        else:
            buckets["neutral"].append(row)
    summary = {name: _summary(rows) for name, rows in buckets.items()}
    all_mean = summary.get("all", {}).get("mean_ret")
    for name, item in summary.items():
        mean_ret = item.get("mean_ret")
        item["edge_vs_all"] = (mean_ret - all_mean) if mean_ret is not None and all_mean is not None else None
    return {
        "schema_version": 1,
        "source": "stock_sentiment_history + training_rows",
        "shadow_only": True,
        "start": start,
        "end": end,
        "threshold": threshold,
        "joined_rows": len(joined),
        "summary": summary,
        "coverage_note": "This uses existing cached sentiment evidence only; no historical news backfill or API fetch is performed.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate one-line intelligence as a shadow signal using existing real rows.")
    ap.add_argument("--sentiment", default=str(ROOT / "output" / "live" / "stock_sentiment_history.jsonl"))
    ap.add_argument("--training-rows", default=str(ROOT / "output" / "live" / "training_rows.parquet"))
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--threshold", type=float, default=0.2)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    end = args.end[:10]
    start = args.start[:10] if args.start else (date.fromisoformat(end) - timedelta(days=365)).isoformat()
    result = evaluate(
        sentiment_rows=_read_jsonl(Path(args.sentiment)),
        training_rows=_load_training_rows(Path(args.training_rows)),
        start=start,
        end=end,
        threshold=args.threshold,
    )
    out = Path(args.output) if args.output else ROOT / "output" / "research" / f"intelligence_shadow_{end}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, default=str))
    print(f"shadow_result -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
