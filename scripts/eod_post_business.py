"""Run one prescribed statement/research/feedback command with an exit receipt."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.eod_post_business import COMMANDS, run_step


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=COMMANDS, required=True)
    args = parser.parse_args()
    result = run_step(ROOT, args.step, env=os.environ)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(result["exit_code"])
