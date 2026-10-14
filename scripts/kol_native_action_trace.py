#!/usr/bin/env python3
"""Export exact local native-action evidence without operating any app."""

import argparse
import json
from pathlib import Path

from xiaocao.kol.native_action_trace import export_trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout-file", type=Path, required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--not-before", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--capture-job-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--subscription-dir", type=Path,
                        default=Path("output/live/kol_xiaocao_live/wechat_subscription"))
    args = parser.parse_args()
    try:
        result = export_trace(**vars(args))
    except (ValueError, OSError) as error:
        parser.exit(2, f"trace export rejected: {type(error).__name__}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
