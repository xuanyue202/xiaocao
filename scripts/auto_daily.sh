#!/usr/bin/env bash
# Daily xiaocao paper-trade + data-accumulation automation (the compounding flywheel).
#   auto_daily.sh morning-prerecommend # ~09:23: recommend + freeze review queue, then exit for prompt delivery
#   auto_daily.sh morning-execute      # ~09:25: consume frozen artifacts + review rendezvous + paper-record
#   auto_daily.sh morning              # manual compatibility: run both stages in one shell
#   auto_daily.sh eod        # ~15:05 (after close): tick capture + forward A/B/F + monitor + settle + digest->WeCom + pipeline health
#   auto_daily.sh optimize   # ~weekly (trading Fri): capability flywheel — judge short-line + trend pipelines and record to the ledger
#   auto_daily.sh weekly     # Friday evening: deep flywheel review plan (Codex applies/finalizes evidence-backed changes)
# Capital flywheel: morning entries -> intraday staged exits -> eod settle/digest.
# Capability flywheel: eod accumulates training_rows + Book-T evidence -> optimize judges & records to kronos_screen/HYPOTHESES.jsonl.
# Trading-day guarded (skips weekends/holidays), logs to output/live/auto/.
set -uo pipefail
ROOT="${XIAOCAO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PY="$ROOT/.venv/bin/python"
cd "$ROOT" || exit 1
STEP="${1:-}"
TODAY="$(date +%F)"
LOG_DIR="$ROOT/output/live/auto"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${TODAY}_${STEP}.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
_finalize_flow() {
  local status=$?
  if [ -n "${STEP:-}" ] && [ -f "${LOG:-}" ]; then
    "$PY" scripts/build_run_flow.py --automation "$STEP" --date "$TODAY" --log "$LOG" --exit-code "$status" >>"$LOG" 2>&1 || true
    "$PY" scripts/build_context_pack.py --date "$TODAY" --phase "$STEP" >>"$LOG" 2>&1 || true
  fi
  return "$status"
}
trap _finalize_flow EXIT

# --- trading-day guard: `calendar latest` returns the latest trading day <= today ---
# weekly is an audit/review loop, not a trading action; it still runs on holiday Fridays.
if [ "$STEP" != "weekly" ]; then
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
fi

case "$STEP" in
  morning-prerecommend)
    log "morning prerecommend: live_recommend (self-waits to 9:25)"
    if ! "$PY" scripts/live_recommend.py --no-stdout >>"$LOG" 2>&1; then
      log "morning prerecommend FAILED: live_recommend did not produce a usable recommendation"
      exit 1
    fi
    log "build AI intelligence review queue (zero-fetch; no score write)"
    if ! "$PY" scripts/build_intelligence_review_queue.py --date "$TODAY" --limit "${XIAOCAO_AGENT_REVIEW_QUEUE_LIMIT:-8}" >>"$LOG" 2>&1; then
      log "morning prerecommend FAILED: dated review queue was not frozen"
      exit 1
    fi
    PRERECOMMEND_FREEZE="$("$PY" scripts/wait_for_morning_freeze.py --date "$TODAY" --timeout-sec 0 2>&1)"
    PRERECOMMEND_FREEZE_EXIT=$?
    log "morning prerecommend freeze result: $PRERECOMMEND_FREEZE"
    if [ "$PRERECOMMEND_FREEZE_EXIT" -ne 0 ]; then
      log "morning prerecommend FAILED: report and review queue did not form a valid dated freeze"
      exit "$PRERECOMMEND_FREEZE_EXIT"
    fi
    log "morning prerecommend ready -> output/live/recommend_${TODAY}.md"
    ;;
  morning-execute)
    log "morning execute: wait for dated frozen recommendation + review queue (never rerun live_recommend)"
    FREEZE_STATUS="$("$PY" scripts/wait_for_morning_freeze.py --date "$TODAY" --timeout-sec "${XIAOCAO_MORNING_FREEZE_TIMEOUT_SEC:-240}" 2>&1)"
    FREEZE_EXIT=$?
    log "morning freeze result: $FREEZE_STATUS"
    if [ "$FREEZE_EXIT" -ne 0 ]; then
      log "morning execute aborted: dated frozen evidence unavailable"
      exit "$FREEZE_EXIT"
    fi
    log "bounded agent-review rendezvous (structured review only; timeout falls back to base picks)"
    REVIEW_RENDEZVOUS="$("$PY" scripts/wait_for_agent_reviews.py --date "$TODAY" --timeout-sec "${XIAOCAO_AGENT_REVIEW_TIMEOUT_SEC:-180}" 2>&1)" || true
    log "agent-review rendezvous result: $REVIEW_RENDEZVOUS"
    log "paper-record ★E mode-qualified picks"
    if ! "$PY" kronos_screen/scripts/paper_record.py --date "$TODAY" --pick mode_exec_star --initial-capital 100000 --fee-rate 0.0001 --deploy-ratio 0.5 --max-total-exposure-ratio 1.0 --quality-governor shadow --intelligence-trade shadow >>"$LOG" 2>&1; then
      log "morning execute FAILED: Book B paper-record failed"
      exit 1
    fi
    log "paper-record Book T trend basket (paper-only, independent account)"
    "$PY" kronos_screen/scripts/paper_record.py --date "$TODAY" --initial-capital 100000 --fee-rate 0.0001 --trend-only >>"$LOG" 2>&1 || true
    log "surface 小草 posture prior (judgment lens only; NOT a filter on the deterministic picks)"
    "$PY" scripts/xiaocao_knowledge.py --posture >>"$LOG" 2>&1 || true
    log "record standing posture call (judgment-calibration loop; scored fwd at eod)"
    "$PY" scripts/posture_calibration.py --record-current >>"$LOG" 2>&1 || true
    log "morning execution done"
    ;;
  morning)
    log "morning: live_recommend (self-waits to 9:25)"
    "$PY" scripts/live_recommend.py --no-stdout >>"$LOG" 2>&1
    log "build AI intelligence review queue (zero-fetch; no score write)"
    "$PY" scripts/build_intelligence_review_queue.py --date "$TODAY" --limit "${XIAOCAO_AGENT_REVIEW_QUEUE_LIMIT:-8}" >>"$LOG" 2>&1 || true
    log "bounded agent-review rendezvous (structured review only; timeout falls back to base picks)"
    REVIEW_RENDEZVOUS="$("$PY" scripts/wait_for_agent_reviews.py --date "$TODAY" --timeout-sec "${XIAOCAO_AGENT_REVIEW_TIMEOUT_SEC:-180}" 2>&1)" || true
    log "agent-review rendezvous result: $REVIEW_RENDEZVOUS"
    log "paper-record ★E mode-qualified picks"
    "$PY" kronos_screen/scripts/paper_record.py --date "$TODAY" --pick mode_exec_star --initial-capital 100000 --fee-rate 0.0001 --deploy-ratio 0.5 --max-total-exposure-ratio 1.0 --quality-governor shadow --intelligence-trade shadow >>"$LOG" 2>&1
    log "paper-record Book T trend basket (paper-only, independent account)"
    "$PY" kronos_screen/scripts/paper_record.py --date "$TODAY" --initial-capital 100000 --fee-rate 0.0001 --trend-only >>"$LOG" 2>&1 || true
    log "surface 小草 posture prior (judgment lens only; NOT a filter on the deterministic picks)"
    "$PY" scripts/xiaocao_knowledge.py --posture >>"$LOG" 2>&1 || true
    log "record standing posture call (judgment-calibration loop; scored fwd at eod)"
    "$PY" scripts/posture_calibration.py --record-current >>"$LOG" 2>&1 || true
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
    # governance pre-flight: fail-closed if the learning substrate is zero-padded /
    # stale (data_guard / DATA_QUALITY.md). Complements data_doctor.
    if [ "$DATA_OK" = "1" ]; then
      if "$PY" scripts/learning_preflight.py >>"$LOG" 2>&1; then :; else
        DATA_OK=0; log "learning_preflight FAILED (dirty substrate) — won't learn"; fi
    fi
    if [ "$DATA_OK" = "1" ]; then
      log "forward_eval (A/B/F + executable mode evidence)"
      "$PY" kronos_screen/scripts/forward_eval.py --live-only --fee-rate 0.0001 >>"$LOG" 2>&1
      log "intelligence shadow eval (cached one-line sentiment vs realized training rows)"
      "$PY" scripts/research_intelligence_shadow.py --end "$TODAY" >>"$LOG" 2>&1 || true
    else
      log "data health CRITICAL — SKIPPING forward_eval + capability record (won't learn from dirty data)"
    fi
    log "monitor open paper positions"
    "$PY" scripts/live_monitor.py --execute-sells >>"$LOG" 2>&1 || true
    log "monitor open Book T trend positions"
    "$PY" scripts/live_monitor.py --book T --execute-sells >>"$LOG" 2>&1 || true
    log "settle book A (validated next-close reference)"
    "$PY" kronos_screen/scripts/settle_book_a.py >>"$LOG" 2>&1 || true
    log "settle book T (wide trend stop / low-turnover rebalance)"
    "$PY" kronos_screen/scripts/settle_book_t.py >>"$LOG" 2>&1 || true
    log "pnl decomposition (pick_alpha / entry_slippage / exit_timing)"
    "$PY" kronos_screen/scripts/decompose_pnl.py >>"$LOG" 2>&1 || true
    PAPER_VS_MARKET_START="${PAPER_VS_MARKET_START:-2026-06-01}"
    PAPER_VS_MARKET_OUT="output/research/paper_vs_market_${PAPER_VS_MARKET_START}_${TODAY}.md"
    log "paper vs market benchmark -> ${PAPER_VS_MARKET_OUT}"
    "$PY" scripts/research_paper_vs_market.py \
      --start "$PAPER_VS_MARKET_START" \
      --end "$TODAY" \
      --output "$PAPER_VS_MARKET_OUT" >>"$LOG" 2>&1 || true
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
      log "trend capability flywheel (weekly Fri): judge + record Book T verdict -> ledger"
      "$PY" scripts/trend_optimize.py --record >>"$LOG" 2>&1 || true
    else
      log "pipeline health check (capability flywheel, no record)"
      "$PY" scripts/continuous_optimize.py >>"$LOG" 2>&1 || true
      log "trend pipeline health check (trend_guards, no record)"
      "$PY" scripts/trend_optimize.py >>"$LOG" 2>&1 || true
    fi
    # Three-flywheel health on the dashboard every eod. ① capital + ② capability
    # auto-turn; ③ strategy is a human gate. --notify-blocked escalates to WeCom
    # ONLY if a PASS verdict is pending with no actuator (a validated edge with
    # nowhere to go) — a real anomaly the human must act on, never auto-applied.
    log "flywheel self-check (3 飞轮健康度；③ 策略 actuator 状态)"
    "$PY" scripts/flywheel_selfcheck.py --notify-blocked >>"$LOG" 2>&1 || true
    log "小草 posture freshness check (flag if the distilled prior has gone stale)"
    "$PY" scripts/xiaocao_knowledge.py --check >>"$LOG" 2>&1 || log "⚠ 小草 posture STALE — 重蒸馏最新转录并更新 reference/experience/posture_current.json"
    log "judgment calibration: score posture calls whose fwd window closed, then distill (defensive hit-rate = distill signal)"
    "$PY" scripts/posture_calibration.py --score >>"$LOG" 2>&1 || true
    "$PY" scripts/posture_calibration.py --distill >>"$LOG" 2>&1 || true
    log "exit calibration: record today's exit decisions, score closed windows, then distill (per-rule hit-rate = distill signal)"
    "$PY" scripts/exit_calibration.py --ingest --score --distill >>"$LOG" 2>&1 || true
    log "flywheel sweep: reconcile verdict ledger (retire REJECTED, tag PASS) + log the test-priority queue (backlog consumer; authority=0)"
    "$PY" scripts/flywheel_sweep.py --top 8 >>"$LOG" 2>&1 || true
    log "eod done"
    ;;
  optimize)
    log "capability flywheel: judge live short-line pipeline under discipline guards + record to ledger"
    "$PY" scripts/continuous_optimize.py --record >>"$LOG" 2>&1 || true
    log "trend capability flywheel: judge Book T under trend_guards + record to ledger"
    "$PY" scripts/trend_optimize.py --record >>"$LOG" 2>&1 || true
    log "optimize done -> kronos_screen/HYPOTHESES.jsonl"
    ;;
  sweep)
    # weekly backlog consumer: deeper ranked queue + ledger reconciliation. Report-only,
    # never promotes (authority=0). Surfaces the oldest/highest-recurrence priors to research.
    log "flywheel sweep (backlog consumer): reconcile ledger + rank ALL untested candidates by test-priority"
    "$PY" scripts/flywheel_sweep.py --top 30 >>"$LOG" 2>&1 || true
    log "sweep done (report-only; pick a top cache-expressible candidate -> research_run.py -> §10 gate)"
    ;;
  weekly)
    log "weekly deep review: record short-line + trend verdicts before planning"
    "$PY" scripts/continuous_optimize.py --record >>"$LOG" 2>&1 || true
    "$PY" scripts/trend_optimize.py --record >>"$LOG" 2>&1 || true
    log "weekly deep review: reconcile/rank backlog"
    "$PY" scripts/flywheel_sweep.py --top 30 >>"$LOG" 2>&1 || true
    log "weekly deep review: refresh distill action log"
    "$PY" scripts/distill_transcript.py --refresh-action-log >>"$LOG" 2>&1 || true
    log "weekly deep review: build fixed-input plan"
    "$PY" scripts/weekly_deep_review.py --plan --date "$TODAY" >>"$LOG" 2>&1
    log "weekly plan ready -> output/live/weekly_plan_${TODAY}.json; Codex should apply evidence-backed changes, validate, then finalize/commit"
    ;;
  *)
    echo "usage: auto_daily.sh {morning-prerecommend|morning-execute|morning|eod|optimize|sweep|weekly}"; exit 2;;
esac
