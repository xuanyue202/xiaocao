#!/usr/bin/env python3
"""Build/accept authority-zero opening preparation; assemble a current delta packet."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from xiaocao.kol.trading_decision import read_json
from xiaocao.kol import opening_preparation as prep
from xiaocao.runner_recovery import _hash


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inputs", "rolling-inputs", "template", "accept", "packet"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fresh-through", help="rolling reuse must remain valid through this aware timestamp")
    for name in ("input", "projection-summary", "binding", "draft", "review", "dispatch", "context", "preparation", "request"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args(argv)
    needed = {"inputs": ("projection_summary", "binding"), "rolling-inputs": (), "template": ("input",),
              "accept": ("input", "draft", "review", "dispatch", "context"),
              "packet": ("input", "preparation", "request")}[args.command]
    if any(getattr(args, key) is None for key in needed):
        parser.error("Required: " + ", ".join("--" + k.replace("_", "-") for k in needed))
    now = datetime.now(timezone.utc)
    started = perf_counter()
    reuse_audit = {}
    try:
        if args.command == 'rolling-inputs':
            from xiaocao.kol import rolling_preparation as rolling
            from xiaocao.kol.trading_context import build_trading_context, write_trading_projection
            if os.environ.get('CODEX_AUTOMATION_ID') != rolling.OWNER or not os.environ.get('CODEX_THREAD_ID'):
                raise ValueError('KOL_PREPARATION_ROLLING_OWNER_REQUIRED')
            through = prep.aware(args.fresh_through) if args.fresh_through else now
            if through < now:
                raise ValueError('KOL_PREPARATION_REUSE_HORIZON_PAST')
            reuse_audit = {'fresh_through': through.isoformat()}
            summary = write_trading_projection(build_trading_context(repo_root=args.root,
                read_report_ids=[], include_report_bodies=False, as_of=now), repo_root=args.root)
            try:
                cached = rolling.registered(args.root, now=now)
                if cached is not None:
                    if prep.aware(cached[1]['draft']['valid_until']) <= through:
                        reuse_audit['rebuild_reason'] = 'PREPARATION_EXPIRES_BEFORE_USE'
                        cached = None
                    else:
                        rolling.validate_current_sources(cached[1], now=through)
            except ValueError as exc:
                if str(exc) not in {'KOL_PREPARATION_ROLLING_SOURCE_EXPIRED', 'KOL_PREPARATION_RULES_CHANGED',
                                    'KOL_PREPARATION_ROLLING_INPUT_ALTERED'}:
                    raise
                cached = None
                reuse_audit['rebuild_reason'] = str(exc)
            if (cached is not None and cached[1]['source_fingerprint'] == prep.read_projection(summary)['source_fingerprint']
                    and prep.viewpoint_units(prep.read_projection(cached[1]['projection'])) ==
                    prep.viewpoint_units(prep.read_projection(summary))):
                print(json.dumps({'status': 'reused', 'authority': 0, 'path': str(cached[0]),
                    'preparation_sha256': cached[1]['preparation_sha256'],
                    **reuse_audit,
                    'elapsed_seconds': perf_counter()-started}))
                return 0
            binding = {'automation_id': rolling.OWNER, 'owner_thread_id': os.environ['CODEX_THREAD_ID'],
                'trade_date': now.astimezone(prep.TZ).date().isoformat(), 'scope': 'source_reasoning_only'}
            value = rolling.input_payload(summary, binding=binding, repo_root=args.root)
        elif args.command == "inputs":
            value = prep.input_payload(read_json(args.projection_summary), binding=read_json(args.binding), repo_root=args.root)
        elif args.command == "template":
            value = prep.draft_template(args.input)
        elif args.command == "accept":
            value = prep.accept_preparation(args.input, read_json(args.draft), read_json(args.review),
                    read_json(args.dispatch), read_json(args.context), now=now)
        else:
            value = prep.opening_packet(args.preparation, args.input, read_json(args.request), now=now)
        path = prep.write_artifact(args.output_dir, value, "." + args.command + ".json")
        if args.command == 'accept' and value['binding'].get('automation_id') == 'xiaocao-book-b-live-morning':
            from xiaocao.kol.selection_preview import register_preparation
            register_preparation(args.input.resolve(), path, value)
        if args.command == 'accept' and value.get('schema_version') == 'kol-opening-preparation.v2':
            from xiaocao.kol.rolling_preparation import register
            register(args.input, path, value)
        if args.command == "accept" and value["binding"].get("automation_id") == "xiaocao-daily-morning-execution":
            from xiaocao.live.paper_morning_kol import register_preparation
            register_preparation(args.root, path, value)
        print(json.dumps({"status": "prepared" if args.command == "accept" else "written", "authority": 0,
            "path": str(path), "sha256": prep.canonical_sha256(value),
            "input_sha256": _hash(value) if args.command == "inputs" else value.get("input_sha256"),
            "preparation_sha256": value.get("preparation_sha256"), "packet_sha256": value.get("packet_sha256"),
            **reuse_audit, 'elapsed_seconds': perf_counter()-started}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc) if str(exc).startswith(("KOL_PREPARATION_", "PAPER_KOL_")) else type(exc).__name__, "authority": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
