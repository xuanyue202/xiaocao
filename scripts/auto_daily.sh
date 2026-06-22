#!/usr/bin/env bash
# Daily xiaocao paper-trade + data-accumulation automation (the compounding flywheel).
#   auto_daily.sh morning   # ~09:23 (self-waits to 9:25): recommend + ★/★B + auction snapshot + paper-record
#   auto_daily.sh eod        # ~15:05 (after close): tick capture + forward A/B + monitor + settle + digest->WeCom + pipeline health
#   auto_daily.sh optimize   # ~weekly (trading Fri): capability flywheel — judge live pipeline under the discipline guards + record to the ledger
# Capital flywheel: morning entries -> intraday staged exits -> eod settle/digest.
# Capability flywheel: eod accumulates training_rows -> optimize judges & records to kronos_screen/HYPOTHESES.jsonl.
# Trading-day guarded (skips weekends/holidays), logs to output/live/auto/.
set -uo pipefail
ROOT="${XIAOCAO_ROOT:-$HOME/coding/xiaocao}"
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
    log "surface 小草 posture prior (judgment lens only; NOT a filter on the deterministic picks)"
    "$PY" scripts/xiaocao_knowledge.py --posture >>"$LOG" 2>&1 || true
    log "morning done -> output/live/recommend_${TODAY}.md"
    ;;
  eod)
    log "eod: tick-flow capture"
    "$PY" kronos_screen/scripts/eod_capture.py >>"$LOG" 2>&1
    # date_kline (daily OHLCV) feed lags weeks; reconstruct today's daily bar from
    # minute (current) for held + signalled codes so the learning substrate stays
    # current. Rate-limited (API throttles on bursts). Non-fatal.
    log "refresh daily bars from minute (bypass lagging date_kline feed)"
    "$PY" scripts/refresh_daily_cache.py >>"$LOG" 2>&1 || true
    # data health GATES the capability (learning) half: a critical finding (e.g.
    # duplicate snapshots) must NOT be fed into training_rows/the ledger, or the
    # flywheel learns from a 真的谎言. The capital half (monitor/settle/digest)
    # still runs for visibility.
    log "data health check (catch dirty data before trusting A/B)"
    if "$PY" scripts/data_doctor.py >>"$LOG" 2>&1; then DATA_OK=1; else DATA_OK=0; fi
    if [ "$DATA_OK" = "1" ]; then
      log "forward_eval (A/B + accumulate training rows)"
      "$PY" kronos_screen/scripts/forward_eval.py --live-only --fee-rate 0.0001 >>"$LOG" 2>&1
    else
      log "data health CRITICAL — SKIPPING forward_eval + capability record (won't learn from dirty data)"
    fi
    log "monitor open paper positions"
    "$PY" scripts/live_monitor.py --execute-sells >>"$LOG" 2>&1 || true
    log "settle book A (validated next-close reference)"
    "$PY" kronos_screen/scripts/settle_book_a.py >>"$LOG" 2>&1 || true
    log "pnl decomposition (pick_alpha / entry_slippage / exit_timing)"
    "$PY" kronos_screen/scripts/decompose_pnl.py >>"$LOG" 2>&1 || true
    log "status digest -> WeCom relay (capital flywheel visibility; book A/B spread)"
    "$PY" scripts/status.py --push-wecom >>"$LOG" 2>&1 || true
    # Capability flywheel: health-check daily, RECORD a dated verdict weekly (Fri)
    # so the loop turns automatically without a separate scheduler — but only on
    # clean data. On-demand recording is still `auto_daily.sh optimize`.
    if [ "$DATA_OK" != "1" ]; then
      log "capability flywheel SKIPPED (data health critical)"
    elif [ "$(date +%u)" = "5" ]; then
      log "capability flywheel (weekly Fri): judge + record verdict -> ledger"
      "$PY" scripts/continuous_optimize.py --record >>"$LOG" 2>&1 || true
    else
      log "pipeline health check (capability flywheel, no record)"
      "$PY" scripts/continuous_optimize.py >>"$LOG" 2>&1 || true
    fi
    # Three-flywheel health on the dashboard every eod. ① capital + ② capability
    # auto-turn; ③ strategy is a human gate. --notify-blocked escalates to WeCom
    # ONLY if a PASS verdict is pending with no actuator (a validated edge with
    # nowhere to go) — a real anomaly the human must act on, never auto-applied.
    log "flywheel self-check (3 飞轮健康度；③ 策略 actuator 状态)"
    "$PY" scripts/flywheel_selfcheck.py --notify-blocked >>"$LOG" 2>&1 || true
    log "小草 posture freshness check (flag if the distilled prior has gone stale)"
    "$PY" scripts/xiaocao_knowledge.py --check >>"$LOG" 2>&1 || log "⚠ 小草 posture STALE — 重蒸馏最新转录并更新 reference/experience/posture_current.json"
    log "eod done"
    ;;
  optimize)
    log "capability flywheel: judge live pipeline under discipline guards + record to ledger"
    "$PY" scripts/continuous_optimize.py --record >>"$LOG" 2>&1 || true
    log "optimize done -> kronos_screen/HYPOTHESES.jsonl"
    ;;
  *)
    echo "usage: auto_daily.sh {morning|eod|optimize}"; exit 2;;
esac
