#!/usr/bin/env python3
"""Build/accept authority-zero opening preparation; assemble a current delta packet."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from xiaocao.kol.trading_decision import read_json
from xiaocao.kol import opening_preparation as prep
from xiaocao.runner_recovery import _hash


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inputs", "template", "accept", "packet"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    for name in ("input", "projection-summary", "binding", "draft", "review", "dispatch", "context", "preparation", "request"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args(argv)
    needed = {"inputs": ("projection_summary", "binding"), "template": ("input",),
              "accept": ("input", "draft", "review", "dispatch", "context"),
              "packet": ("input", "preparation", "request")}[args.command]
    if any(getattr(args, key) is None for key in needed):
        parser.error("Required: " + ", ".join("--" + k.replace("_", "-") for k in needed))
    now = datetime.now(timezone.utc)
    try:
        if args.command == "inputs":
            value = prep.input_payload(read_json(args.projection_summary), binding=read_json(args.binding), repo_root=args.root)
        elif args.command == "template":
            value = prep.draft_template(args.input)
        elif args.command == "accept":
            value = prep.accept_preparation(args.input, read_json(args.draft), read_json(args.review),
                    read_json(args.dispatch), read_json(args.context), now=now)
        else:
            value = prep.opening_packet(args.preparation, args.input, read_json(args.request), now=now)
        path = prep.write_artifact(args.output_dir, value, "." + args.command + ".json")
        if args.command == "accept" and value["binding"].get("automation_id") == "xiaocao-daily-morning-execution":
            from xiaocao.live.paper_morning_kol import register_preparation
            register_preparation(args.root, path, value)
        print(json.dumps({"status": "prepared" if args.command == "accept" else "written", "authority": 0,
            "path": str(path), "sha256": prep.canonical_sha256(value),
            "input_sha256": _hash(value) if args.command == "inputs" else value.get("input_sha256"),
            "preparation_sha256": value.get("preparation_sha256"), "packet_sha256": value.get("packet_sha256")}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc) if str(exc).startswith(("KOL_PREPARATION_", "PAPER_KOL_")) else type(exc).__name__, "authority": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
