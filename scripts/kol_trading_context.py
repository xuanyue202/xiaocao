#!/usr/bin/env python3
"""Read published multi-KOL context into a rebuildable local evidence cache."""

from __future__ import annotations

import argparse
import json

from xiaocao.kol.trading_context import TradingContextError, build_trading_context, summarize_context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["context"])
    parser.add_argument("--ledger", action="append", default=[], help="Additional production events.jsonl; repeatable")
    parser.add_argument("--report-id", action="append", default=[], help="Load an additional registered report body")
    parser.add_argument("--read-report-id", action="append", default=None, help="Read only these exact registered IDs remotely; reuse other fresh caches")
    parser.add_argument("--cache-only", action="store_true", help="No MCP calls; expose stale/missing coverage")
    parser.add_argument("--summary", action="store_true", help="Print compact path/hash/coverage/counts; keep full cache")
    parser.add_argument("--author", action="append", default=[], help="Declare expected coverage; does not filter authors")
    parser.add_argument("--latest-per-author", type=int, default=3)
    parser.add_argument("--as-of", help="Aware ISO timestamp; disallows evidence first observed after this time")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-cache-age-seconds", type=float, default=300)
    parser.add_argument("--history-max-cache-age-seconds", type=float, default=86400)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument("--total-timeout-seconds", type=float, default=120)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-read-calls", type=int, default=None, help="Default: registered manifest record count times bounded attempts")
    args = parser.parse_args(argv)
    try:
        context = build_trading_context(
            as_of=args.as_of, ledger_paths=args.ledger, report_ids=args.report_id,
            read_report_ids=[] if args.cache_only else args.read_report_id,
            registered_authors=args.author, latest_per_author=args.latest_per_author,
            refresh=args.refresh, max_cache_age_seconds=args.max_cache_age_seconds,
            history_max_cache_age_seconds=args.history_max_cache_age_seconds,
            timeout_seconds=args.timeout_seconds, total_timeout_seconds=args.total_timeout_seconds,
            retries=args.retries, max_read_calls=args.max_read_calls,
        )
    except TradingContextError as exc:
        print(json.dumps({"status": "blocked", "code": str(exc)}, ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "context_build_failed"}))
        return 2
    print(json.dumps(summarize_context(context) if args.summary else context, ensure_ascii=False, sort_keys=True))
    # registry_only is always explicit; it alone is not an operational failure.
    failed = context["coverage"]["missing_authors"] or not context["coverage"]["registered_longitudinal_complete"]
    failed = failed or not context["coverage"].get("selected_reports_fresh", True)
    failed = failed or any(reason["code"] == "report_id_not_registered"
                           for reason in context["coverage"].get("incomplete_reasons", []))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
