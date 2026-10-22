#!/usr/bin/env python3
"""Read-only, cache-only short-term comparisons with immutable input snapshots."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import data_health  # noqa: E402
from xiaocao.research.shortline_comparison import compare_shortline, render_comparison  # noqa: E402
from xiaocao.utils.atomic_files import atomic_write  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    root = args.data_root.resolve()
    live = root / "output/live"
    names = ["positions.jsonl", "training_rows.parquet"]
    try:
        inputs = {name: (live / name).read_bytes() for name in names}
    except FileNotFoundError:
        print(json.dumps({"status": "blocked", "reason": "SHORTLINE_INPUT_MISSING"}))
        return 2
    health = data_health.check(live)
    if health["critical"]:
        print(json.dumps({"status": "blocked", "reason": "DATA_DOCTOR_CRITICAL", "critical": health["critical"]}))
        return 2
    if any((live / name).read_bytes() != raw for name, raw in inputs.items()):
        raise ValueError("SHORTLINE_INPUT_CHANGED_DURING_HEALTH_CHECK")
    import pandas as pd

    positions = [json.loads(line) for line in inputs["positions.jsonl"].decode().splitlines() if line.strip()]
    frame = pd.read_parquet(io.BytesIO(inputs["training_rows.parquet"]))
    training = frame.astype(object).where(pd.notna(frame), None).to_dict("records")
    result = compare_shortline(positions, training, start=args.start, end=args.end)
    if any((live / name).read_bytes() != raw for name, raw in inputs.items()):
        raise ValueError("SHORTLINE_INPUT_CHANGED_DURING_READ")
    result.update(observed_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                  data_doctor={key: health[key] for key in ("ok", "critical", "warn")})
    directory = ROOT / "output/research/shortline_comparisons"
    result["inputs"] = []
    for name, raw in inputs.items():
        sha = hashlib.sha256(raw).hexdigest()
        saved = directory / "inputs" / (sha + "-" + name)
        atomic_write(saved, raw, immutable=True)
        result["inputs"].append({"source": str(live / name), "path": str(saved.relative_to(ROOT)), "sha256": sha})
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode()
    sha = hashlib.sha256(raw).hexdigest()
    path = directory / f"{args.end}-{sha}.json"
    atomic_write(path, raw, immutable=True)
    atomic_write(path.with_suffix(".md"), render_comparison(result).encode(), immutable=True)
    print(json.dumps({"status": result["status"], "path": str(path), "sha256": sha,
                      "paired_exits": result["paired_exit"]["eligible_pairs"], "coverage": result["coverage"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
