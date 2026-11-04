#!/usr/bin/env python3
"""Read published multi-KOL context into a rebuildable local evidence cache."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path

from xiaocao.kol.trading_context import (
    TradingContextError,
    build_trading_context,
    summarize_context,
    write_trading_projection,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["context", "projection", "shared"])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ledger", action="append", default=[], help="Additional production events.jsonl; repeatable")
    parser.add_argument("--report-id", action="append", default=[], help="Load an additional registered report body")
    parser.add_argument("--read-report-id", action="append", default=None, help="Read only these exact registered IDs remotely; reuse other fresh caches")
    parser.add_argument("--cache-only", action="store_true", help="No MCP calls; expose stale/missing coverage")
    parser.add_argument("--decision-sources", action="store_true", help="Read only explicit report bodies; reuse complete published writer receipts for history")
    parser.add_argument("--summary", action="store_true", help="Print compact path/hash/coverage/counts; keep full cache")
    parser.add_argument("--since-context", type=Path, help="With --summary, read changes against this already-read full context; never a substitute for reading the base")
    parser.add_argument("--author", action="append", default=[], help="Declare expected coverage; does not filter authors")
    parser.add_argument("--latest-per-author", type=int, default=3)
    parser.add_argument("--as-of", help="Aware ISO timestamp; disallows evidence first observed after this time")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-cache-age-seconds", type=float, default=300)
    parser.add_argument("--history-max-cache-age-seconds", type=float, default=86400)
    parser.add_argument("--history-fresh-through", help="Refresh history that expires before this aware timestamp; never changes evidence as-of")
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument("--total-timeout-seconds", type=float, default=120)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-read-calls", type=int, default=None, help="Default: registered manifest record count times bounded attempts")
    args = parser.parse_args(argv)
    if args.command == 'shared':
        from xiaocao.kol.shared_judgment import build
        from xiaocao.kol.opening_preparation import write_artifact
        started = perf_counter()
        try:
            observed = datetime.fromisoformat(args.as_of.replace('Z', '+00:00')) if args.as_of else datetime.now(timezone.utc)
            value = build(args.root, now=observed)
            path = write_artifact(args.root / 'output/live/kol_policy/context', value, '.shared-packet.json')
            print(json.dumps({'status':'ready', 'authority':0, 'packet_path':str(path),
                'packet_sha256':value['packet_sha256'], 'context_path':value['context_path'],
                'preparation_sha256':value['preparation_sha256'], 'coverage':value['coverage'],
                'delta_counts':{k:len(value['delta'][k]) for k in ('added','changed','removed')},
                'elapsed_seconds':perf_counter()-started}, ensure_ascii=False))
            return 0
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({'status':'deferred','authority':0,'reason':str(exc) if str(exc).startswith('KOL_PREPARATION_') else type(exc).__name__}))
            return 2
    if args.since_context and not args.summary:
        parser.error("--since-context requires --summary")
    try:
        prior = json.loads(args.since_context.read_text()) if args.since_context else None
        context = build_trading_context(
            repo_root=args.root,
            as_of=args.as_of, ledger_paths=args.ledger, report_ids=args.report_id,
            read_report_ids=[] if args.cache_only else args.read_report_id,
            registered_authors=args.author, latest_per_author=args.latest_per_author,
            include_report_bodies=args.command != "projection",
            refresh=args.refresh, max_cache_age_seconds=args.max_cache_age_seconds,
            history_max_cache_age_seconds=args.history_max_cache_age_seconds,
            history_fresh_through=args.history_fresh_through,
            timeout_seconds=args.timeout_seconds, total_timeout_seconds=args.total_timeout_seconds,
            retries=args.retries, max_read_calls=args.max_read_calls,
            decision_sources=args.decision_sources,
        )
        result = (
            write_trading_projection(context, repo_root=args.root)
            if args.command == "projection"
            else summarize_context(context, prior_context=prior)
            if args.summary
            else context
        )
    except TradingContextError as exc:
        print(json.dumps({"status": "blocked", "code": str(exc)}, ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "context_build_failed"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    # registry_only is always explicit; it alone is not an operational failure.
    failed = context["coverage"]["missing_authors"] or not context["coverage"]["registered_longitudinal_complete"]
    failed = failed or not context["coverage"].get("selected_reports_fresh", True)
    failed = failed or any(reason["code"] == "report_id_not_registered"
                           for reason in context["coverage"].get("incomplete_reasons", []))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
