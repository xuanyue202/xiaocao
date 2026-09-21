#!/usr/bin/env python3
"""Exit before pytest collection when APP simulation tests are time-blocked."""
from __future__ import annotations

import json

from xiaocao.live.app_test_window import WINDOW_DESCRIPTION, app_tests_allowed


def main() -> int:
    allowed = app_tests_allowed()
    print(json.dumps({
        "status": "open" if allowed else "closed",
        "window": WINDOW_DESCRIPTION,
        "next_action": (
            "run_app_simulation_tests"
            if allowed
            else "defer_without_collecting_tests"
        ),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if allowed else 3


if __name__ == "__main__":
    raise SystemExit(main())
