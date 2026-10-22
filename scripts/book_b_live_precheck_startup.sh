#!/usr/bin/env bash
# Keep the two independent 14:25 checks in the original retained process.
set -uo pipefail

runtime_thread="${CODEX_THREAD_ID:-}"
if [[ "${CODEX_AUTOMATION_ID:-}" != "xiaocao-intraday-risk-precheck-1425" || -z "${runtime_thread//[[:space:]]/}" ]]; then
  echo "PRECHECK_AUTOMATION_IDENTITY_REQUIRED" >&2
  exit 78
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 78

# Each entrypoint retains its calendar, wall-clock and economic guards.
paper_exit=0
PYTHONPATH=src .venv/bin/python scripts/live_monitor.py --execute-sells || paper_exit=$?
echo "precheck branch=paper exit=$paper_exit"

app_exit=0
PYTHONPATH=src .venv/bin/python scripts/book_b_live_intraday.py --date today --phase precheck --execute-sells || app_exit=$?
echo "precheck branch=app exit=$app_exit"

# The research model runs after both independent production checkpoints.
PYTHONPATH=src .venv/bin/python scripts/research_book_b_forward.py --phase monitor --checkpoint-phase precheck || echo "research branch=app-b-forward status=degraded"

if (( paper_exit != 0 )); then
  exit "$paper_exit"
fi
exit "$app_exit"
