#!/usr/bin/env python3
"""Capture and render cached weekly evidence without running business workflows."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research.weekly_evidence import (  # noqa: E402
    build_weekly_evidence, render_weekly_evidence, verify_snapshots,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Read-only cached evidence source")
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Observation JSON; Markdown is saved beside it")
    args = parser.parse_args()
    source, output = args.root.resolve(), args.output.resolve()
    if not source.is_dir():
        parser.error("--root must name an existing evidence directory")
    markdown = output.with_suffix(".md").resolve()
    snapshots = (output.parent / (output.stem + "_inputs")).resolve()
    # Resolve every derived destination before capturing any source bytes.
    if any(path.is_relative_to(source) for path in (output, markdown, snapshots)):
        parser.error("save observations outside the evidence source directory")
    if output.suffix != ".json":
        parser.error("--output must name a .json observation")
    report = build_weekly_evidence(source, as_of=args.date, snapshot_dir=snapshots)
    errors = verify_snapshots(report)
    if errors:
        parser.error("captured evidence verification failed: " + "; ".join(errors))
    report["observation_source_root"] = str(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown.write_text("\n".join(render_weekly_evidence(report)) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "files": len(report["input_manifest"]["files"]),
                      "research_runs": len(report["research_runs"]),
                      "comparisons": len(report["option_comparison"]["comparisons"]),
                      "manifest_sha256": report["input_manifest"]["sha256"],
                      "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
