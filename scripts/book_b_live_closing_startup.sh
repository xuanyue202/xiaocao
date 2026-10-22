#!/usr/bin/env bash
set -euo pipefail

runtime_thread="${CODEX_THREAD_ID:-}"
if [[ "${CODEX_AUTOMATION_ID:-}" != "xiaocao-intraday-monitor-1455" || -z "${runtime_thread//[[:space:]]/}" ]]; then
  echo "CLOSING_AUTOMATION_IDENTITY_REQUIRED" >&2
  exit 78
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

required_files=(
  /Users/xuanyue202/.codex/automations/xiaocao-intraday-monitor-1455/memory.md
  .codex/skills/xiaocao-trading/SKILL.md
  .codex/skills/xiaocao-trading/references/automation-intraday.md
  .codex/skills/xiaocao-trading/references/book-b-live-repair.md
  .codex/skills/xiaocao-trading/references/kol-trading-judgment.md
)

for required_file in "${required_files[@]}"; do
  sed -n '1,$p' "$required_file"
done

rg -n -i -m 80 \
  'intraday|closing|14:45|book.?b|founder|reconcile|kol|UNKNOWN|settlement' \
  /Users/xuanyue202/.codex/memories/MEMORY.md || true

PYTHONPATH=src .venv/bin/python -m xiaocao.live.closing_startup

app_exit=0
PYTHONPATH=src .venv/bin/python scripts/book_b_live_intraday.py --date today --phase closing --execute-sells || app_exit=$?
echo "closing branch=app exit=$app_exit"

paper_exit=0
PYTHONPATH=src .venv/bin/python scripts/live_monitor.py --execute-sells || paper_exit=$?
echo "closing branch=paper exit=$paper_exit"

# The research model runs after both independent production checkpoints.
PYTHONPATH=src .venv/bin/python scripts/research_book_b_forward.py --phase monitor --checkpoint-phase closing || echo "research branch=app-b-forward status=degraded"

if (( app_exit != 0 )); then
  exit "$app_exit"
fi
exit "$paper_exit"
