#!/usr/bin/env bash
# Daily xiaocao paper-trade + data-accumulation automation.
#   auto_daily.sh morning   # ~09:23 (self-waits to 9:25): recommend + ★/★B + auction snapshot + paper-record
#   auto_daily.sh eod        # ~15:05 (after close): tick-flow capture + forward A/B + monitor
# Trading-day guarded (skips weekends/holidays), logs to output/live/auto/.
set -uo pipefail
ROOT="/Users/bytedance/coding/xiaocao"
PY="$ROOT/.venv/bin/python"
cd "$ROOT" || exit 1
STEP="${1:-}"
TODAY="$(date +%F)"
LOG_DIR="$ROOT/output/live/auto"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${TODAY}_${STEP}.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# --- trading-day guard: `calendar latest` returns the latest trading day <= today ---
CALENDAR_STATUS=1
CALENDAR_OUTPUT=""
CALENDAR_MAX_RETRIES=3
for attempt in $(seq 1 "$CALENDAR_MAX_RETRIES"); do
  CALENDAR_OUTPUT="$("$PY" -m xiaocao calendar latest --date today 2>&1)"
  CALENDAR_STATUS=$?
  if [ $CALENDAR_STATUS -eq 0 ]; then
    break
  fi
  log "交易日历查询失败 (attempt ${attempt}/${CALENDAR_MAX_RETRIES})"
  printf '%s\n' "$CALENDAR_OUTPUT" | tee -a "$LOG"
  if [ "$attempt" -lt "$CALENDAR_MAX_RETRIES" ]; then
    sleep 2
  fi
done
if [ $CALENDAR_STATUS -ne 0 ]; then
  log "交易日历查询最终失败 — skip $STEP"
  exit $CALENDAR_STATUS
fi
LATEST="$(printf '%s\n' "$CALENDAR_OUTPUT" | tail -1 | tr -d '[:space:]')"
if [ -z "$LATEST" ]; then
  log "交易日历查询为空 — skip $STEP"
  exit 1
fi
if [ "$LATEST" != "$TODAY" ]; then
  log "非交易日 (today=$TODAY, latest_trading=$LATEST) — skip $STEP"; exit 0
fi

case "$STEP" in
  morning)
    log "morning: live_recommend (self-waits to 9:25)"
    "$PY" scripts/live_recommend.py --no-stdout >>"$LOG" 2>&1
    log "paper-record ★B picks"
    "$PY" kronos_screen/scripts/paper_record.py --date "$TODAY" --initial-capital 100000 --fee-rate 0.0001 --deploy-ratio 0.5 --max-total-exposure-ratio 0.67 --quality-governor shadow >>"$LOG" 2>&1
    log "morning done -> output/live/recommend_${TODAY}.md"
    ;;
  eod)
    log "eod: tick-flow capture"
    "$PY" kronos_screen/scripts/eod_capture.py >>"$LOG" 2>&1
    log "forward_eval (A/B + accumulate training rows)"
    "$PY" kronos_screen/scripts/forward_eval.py --live-only --fee-rate 0.0001 >>"$LOG" 2>&1
    log "monitor open paper positions"
    "$PY" scripts/live_monitor.py --execute-sells >>"$LOG" 2>&1 || true
    log "settle book A (validated next-close reference)"
    "$PY" kronos_screen/scripts/settle_book_a.py >>"$LOG" 2>&1 || true
    log "pnl decomposition (pick_alpha / entry_slippage / exit_timing)"
    "$PY" kronos_screen/scripts/decompose_pnl.py >>"$LOG" 2>&1 || true
    log "eod done"
    ;;
  *)
    echo "usage: auto_daily.sh {morning|eod}"; exit 2;;
esac
