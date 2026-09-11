#!/usr/bin/env bash
set -euo pipefail

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
  'intraday|closing|14:55|book.?b|founder|reconcile|kol|UNKNOWN|settlement' \
  /Users/xuanyue202/.codex/memories/MEMORY.md || true

PYTHONPATH=src .venv/bin/python scripts/book_b_live_intraday.py --date today --phase closing --execute-sells
