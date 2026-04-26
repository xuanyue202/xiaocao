from __future__ import annotations

from typing import Any

from xiaocao.api.client import RANK_MODEL_FOCUS

from .adaptive import tag_signals
from .regime import classify_regime, derive_proxy_regime, mode_allowed_in
from .rules import check_direction_dixi, check_dixi, check_lianban, check_qibao, pick_big_ones
from .state import StateVector, build_state_index, get_state

MAX_OPEN_PCT_CHANGE = 6.0


# Per-cache StateVector index, built once on first use. Keyed by (cache_path,
# id(cache)) so distinct SQLiteCache instances don't share. Memoized at module
# scope because run_strategy is called once per backtest day; rebuilding the
# state index per call would re-read all date_kline cache rows (~hundreds of
# MB) every time.
_STATE_INDEX_CACHE: dict[tuple[str, int], dict[str, StateVector]] = {}


def _state_for_date(date_iso: str, cache: Any) -> StateVector | None:
    """Lookup the StateVector for `date_iso`, building the per-cache index lazily."""
    if cache is None or not hasattr(cache, "path"):
        return None
    key = (str(cache.path), id(cache))
    index = _STATE_INDEX_CACHE.get(key)
    if index is None:
        index = build_state_index(cache)
        _STATE_INDEX_CACHE[key] = index
    return get_state(date_iso, index)


# Strategy profiles bundle related tuning knobs under a name. CLI exposes
# `--profile NAME`. Add new presets here; do not call this from outside the
# strategy package.
STRATEGY_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
    },
    # Cross-window validated (March + April 2026 backtest, both windows passed
    # on `avg` metric). Drops two modes that systematically lost money:
    #   - 接力低弱转2  (高开追涨;       baseline avg -3.75%, win 25%)
    #   - 方向内绿盘低吸前3名 (baseline avg -1.93%, win 33%)
    # Net effect: signal count drops ~30%, avg/win improve materially across
    # both windows. See docs/strategy_validation.md for the validation report.
    "validated": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
        "exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"],
    },
    # Experimental: add the off-main-line filter on top of `validated`. Smaller
    # sample (~13 trades cross-window) but stronger uplift in the test. Anchored
    # in 小草 0413-A: 短线 / 弱转强 模式 hunt for "新轮动卡位" — directions NOT
    # yet in the established main-line.
    "validated_off_main_line": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
        "exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"],
        "exclude_main_line": True,
    },
    # Validated against 4-month TRAIN (2025-12 → 2026-03, 158 candidate trades)
    # and held-out TEST (2026-04, 17 trades). Combines:
    #   1. exclude_modes (validated profile)
    #   2. exclude_main_line=True (per 0413-A: 短线模式 hunt off-mainline)
    #   3. adaptive_modes=True (default in CLI)
    # Effect on TEST window:
    #   baseline n=9 avg=+4.68% win=55.6%
    #   v2       n=5 avg=+7.83% win=80.0%   (Δavg +3.16%, Δwin +24.4pp)
    # Cross-window robust on 3/4 TRAIN months; Feb26 is ~flat (-0.4% avg, +0.9pp win).
    # Adaptive default (1,2,3 | -5,-3,-2) confirmed near-optimal by 1620-config grid.
    # See reports/strategy_tuning_2025-12_2026-04.md for the full study.
    "validated_v2": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
        "exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"],
        "exclude_main_line": True,
        # v2: adaptive uses the LEGACY regime-label-based fitness (5-bucket
        # discrete via classify_regime → mode_regime_fitness). No StateVector.
        "state_aware_adaptive": False,
    },
    # validated_v3 (RECOMMENDED — supersedes v2 after 8-month head-to-head):
    # same structural filters as v2; the adaptive layer uses the new continuous
    # state-fitness framework (3 axes: reward density × risk polarity ×
    # continuity, derived per-day from cached date_kline + block_rank), with
    # mode-specific preconditions for special cases (断板 modes need
    # duan_ban_recovery ≥ 0.55, calibrated from 8-month tertile analysis).
    #
    # 8-month head-to-head TRAIN result (vs v2):
    #   avg  +2.91% → +3.07% (Δ +0.16%)
    #   win  61.4% → 61.8%   (Δ +0.4pp)
    #   sum  +203.7% → +208.9% (Δ +5.2%)
    #   per-month: Dec/Jan tied, Feb +1.34%, Mar +0.15%, Apr +0.80% — 0 regressions
    #
    # The framework went through 3 iterations to reach this:
    #   v3.0: symmetric SCALE=2 → over-shadowed (4 winners shadowed, NET loss)
    #   v3.1: asymmetric (only relax for f>0) → still slightly worse than v2
    #   v3.2: SCALE=5/3.5/2.5 calibrated to match legacy bucket effect → wins
    #   v3.3: + DBR threshold 0.45→0.55 from win/loss tertile data → final
    #
    # See reports/strategy_state_framework_2025-09_2026-04.md and
    # reports/strategy_winners_losers_2025-09_2026-03.md for full derivation,
    # ablation history, and the diagnostics that drove each iteration.
    "validated_v3": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
        "exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"],
        "exclude_main_line": True,
        "state_aware_adaptive": True,
    },
    # validated_v5 (RECOMMENDED — Plan B shipped 2026-04-26):
    #
    # Same signal generation as validated_v3 (state-fitness adaptive, 12-mode
    # profile, exclude 接力低弱转2 + 方向内绿盘低吸前3名). The change is on the
    # SCORING side only:
    #
    #   - hold_days = 5  (was 1)
    #   - exit_rule = "max_dd"  (was "next_close")
    #   - max_dd_pct = 2.0  (peak-to-trough trailing stop in %)
    #
    # This means: enter at 9:30 open as before (T+1 compatible 9:25 集合竞价
    # path), but instead of selling at next-day close, hold up to 5 trading
    # days with a trailing stop that triggers when the position retraces 2%
    # from its post-entry peak HIGH.
    #
    # 8-month TRAIN+TEST result vs validated_v3 (1d):
    #   avg  +3.40% → +6.39% (Δ +2.99pp)
    #   win  56.2% → 56.2%   (unchanged)
    #   sum  +248.1% → +466.6% (Δ +88%)
    #   per-month: 4/4 TRAIN months improved (+1.42pp..+5.06pp avg lift),
    #              TEST month -0.47pp on n=5 (small-sample noise)
    #
    # See `reports/multi_day_validation_2026-04-26.md` for full sub-month
    # decomposition + max_dd threshold sweep + look-ahead bias fix.
    #
    # Caveats:
    #   - dd=2% is the optimum on this 8mo window; cross-window validation
    #     (May-Jun 2026 / 2024 historical) recommended before considering
    #     promotion to absolute default
    #   - changes ALL existing P&L metrics' interpretation; old 1d numbers
    #     no longer directly comparable to v5 numbers
    "validated_v5": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
        "exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"],
        "exclude_main_line": True,
        "state_aware_adaptive": True,
        # Phase B scoring defaults — read by run_backtest CLI handler.
        "hold_days": 5,
        "exit_rule": "max_dd",
        "max_dd_pct": 2.0,
    },
    # validated_v6 (AGGRESSIVE — Plan E cross-window verified 2026-04-26):
    #
    # Same as validated_v5 but with tighter trailing stop:
    #   - hold_days = 3   (was 5; 3d_dd2 ≈ 5d_dd2 empirically, simplification)
    #   - exit_rule = "max_dd"
    #   - max_dd_pct = 0.5  (was 2.0; tighter stop locks in more profit on
    #                       winners, accepts -0.5% lock-in on losers)
    #
    # Cross-window head-to-head (8mo Sep25-Apr26 + xwin Apr-Aug 2025):
    #   variant     |  8mo avg  | xwin avg  | sum (both)
    #   1d (v3)     | +3.40%    | -0.14%    | +234.8%
    #   3d_dd2 (v5) | +6.42%    | +2.30%    | +686.6%
    #   3d_dd0.5    | **+6.88%**| **+3.04%**| **+790.5%**
    #
    # Both independent windows agreed dd=0.5% is optimal (NOT over-fit). The
    # gap is bigger in the bear-leaning xwin (+0.77pp) than the bull-leaning
    # 8mo (+0.46pp), suggesting tight stops protect more in tougher regimes.
    #
    # Trade-off vs v5: win rate drops (8mo 56%→48%, xwin 39%→23%). More
    # frequent small losses (-0.5% lock-in) + occasional bigger winners. The
    # AVG and SUM both improve, but psychological pattern is different from
    # v5. Choose based on trader preference.
    #
    # Brokerage / slippage NOT modeled — in real trading, ~0.5% slippage on
    # stop fills could erode dd=0.5% advantage more than dd=2.0%. Verify on
    # paper trading before ship-to-production.
    "validated_v6": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
        "exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"],
        "exclude_main_line": True,
        "state_aware_adaptive": True,
        # Aggressive Phase B+E: 3d hold + tight 0.5% trailing stop
        "hold_days": 3,
        "exit_rule": "max_dd",
        "max_dd_pct": 0.5,
    },
    # validated_v3_4 (CANDIDATE — Plan A8, requires robustness gate to ship):
    #
    # Two structural changes vs v3:
    #
    # 1. **DBR preconditions dropped** for 绿断/红断/首红断 (per A3 calibration in
    #    output/calibrate_dbr_per_mode.md): the DBR distributions for winners and
    #    losers OVERLAP for all 6 calibrated modes (Δ_med ∈ [-0.14, +0.00]),
    #    sometimes anti-predictive. v3.6 had observed 100% precondition fail for
    #    绿断 — root cause was DBR isn't a useful gate, not threshold tuning.
    #
    # 2. **Two new bonus axes** wired into mode_fitness:
    #    - wants_momentum (5d cumulative 大盘 mean pct, normalized to [0,1])
    #    - wants_limitup_density (focus pool 涨停 ratio, normalized to [0,1])
    #    First-principles per report §4: 接力 wants high momentum + high limitup;
    #    断板低吸 wants low momentum + low/mid limitup (oversold rebound regime).
    #
    # mode_fitness math: `0.7 * base_3axis + 0.3 * mean(active_new_axes)`. The
    # 0.7 weight on the existing 3 axes preserves v3 dominance while letting
    # the 2 new axes modulate. When both new axes are "any" (e.g., for unknown
    # modes), v3.4 collapses to v3 exactly.
    #
    # Robustness gate to run before ship:
    #   xiaocao backtest run --start 2025-12-01 --end 2026-04-30 \
    #     --warmup-start 2025-09-01 --workers 6 --kline-count 200 \
    #     --profile validated_v3_4
    #   compare TRAIN/TEST avg/win/sum + 4 子月份 vs validated_v3.
    "validated_v3_4": {
        "block_model": RANK_MODEL_FOCUS,
        "category_model": 0,
        "sort_id": 40,
        "direction_sort_key": "directionCjs",
        "pool_sort_key": None,
        "max_per_direction": None,
        "exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"],
        "exclude_main_line": True,
        "state_aware_adaptive": True,
        "use_v3_4_profiles": True,  # plumb to tag_signals → mode_fitness
    },
}


def run_strategy(
    date: str,
    source: Any,
    modes: set[str] | None = None,
    block_model: int = RANK_MODEL_FOCUS,
    category_model: int = 0,
    sort_id: int | str = 40,
    *,
    direction_sort_key: int | str = "directionCjs",
    pool_sort_key: int | str | None = None,
    max_per_direction: int | None = None,
    exclude_modes: set[str] | None = None,
    profile: str | None = None,
    # --- B-track structural enrichment (道+法层) -----------------------------
    regime: str | None = None,
    market_overview: dict[str, Any] | None = None,
    big_cap_avg_open_pct: float | None = None,
    mainline_blocks: set[str] | None = None,
    bigcap_codes: set[str] | None = None,
    regime_gate: bool = False,
    require_main_line: bool = False,
    exclude_main_line: bool = False,
    max_open_pct: float | None = None,
    adaptive_modes: bool = False,
    adaptive_cache: Any | None = None,
    adaptive_trade_days: list[str] | None = None,
    state_aware_adaptive: bool = True,
    use_v3_4_profiles: bool = False,
) -> list[dict[str, Any]]:
    """Generate signals for `date`, annotated with regime / main-line / big-cap.

    The new B-track parameters are all optional and additive:

    - regime / market_overview / big_cap_avg_open_pct: regime label, either
      pre-computed (`regime=...`) or derived from `market_overview` and the
      big-cap average open-pct.
    - mainline_blocks: block codes considered main-line (rolling N days).
      Used to annotate signals; only enforced when `require_main_line=True`.
    - bigcap_codes: stockId set of big-caps; used to annotate signals.
    - regime_gate: when True, signals from modes not allowed in this regime
      are dropped (per `regime.MODE_REGIME_FIT`).
    - require_main_line: when True, signals whose parent block is not in
      `mainline_blocks` are dropped.
    - max_open_pct: override for the global MAX_OPEN_PCT_CHANGE filter.

    All gates default to OFF — the function preserves backward-compatible
    behavior when no enrichment is provided.
    """
    if profile:
        preset = STRATEGY_PROFILES.get(profile)
        if preset is None:
            raise ValueError(f"Unknown strategy profile {profile!r}. Known: {sorted(STRATEGY_PROFILES)}")
        block_model = preset["block_model"]
        category_model = preset["category_model"]
        sort_id = preset["sort_id"]
        direction_sort_key = preset["direction_sort_key"]
        pool_sort_key = preset["pool_sort_key"]
        max_per_direction = preset["max_per_direction"]
        if "exclude_modes" in preset and exclude_modes is None:
            exclude_modes = set(preset["exclude_modes"]) if preset["exclude_modes"] else None
        if "exclude_main_line" in preset and not exclude_main_line:
            exclude_main_line = bool(preset["exclude_main_line"])
        if "state_aware_adaptive" in preset:
            state_aware_adaptive = bool(preset["state_aware_adaptive"])
        if "use_v3_4_profiles" in preset:
            use_v3_4_profiles = bool(preset["use_v3_4_profiles"])

    # Resolve regime if caller passed market_overview but not the label.
    if regime is None and market_overview is not None:
        regime = classify_regime(market_overview, big_cap_avg_open_pct)

    block_rank = source.get_industry_block_rank(date, block_model)
    category_rank = source.get_block_category_rank(date, category_model)
    picked_block = pick_big_ones(block_rank, 5)
    picked_category = pick_big_ones(category_rank, 3)

    pool_sort = pool_sort_key if pool_sort_key is not None else 38

    output = []
    requested = modes or set()
    if not requested or requested.intersection({"all", "jieli", "lianban"}):
        lianban_codes = source.get_pool(date, "jieli")
        if hasattr(source, "sort_codes"):
            lianban_codes = source.sort_codes(date, lianban_codes, pool_sort)
        lianban_details = source.get_stock_index(date, lianban_codes)
        output.extend(check_lianban(lianban_details, picked_block, picked_category, date))
    if not requested or requested.intersection({"all", "dixi", "duanban"}):
        dixi_codes = source.get_pool(date, "dixi")
        if hasattr(source, "sort_codes"):
            dixi_codes = source.sort_codes(date, dixi_codes, pool_sort)
        dixi_details = source.get_stock_index(date, dixi_codes)
        output.extend(check_dixi(dixi_details, picked_block, picked_category, date))
    if not requested or requested.intersection({"all", "direction"}):
        output.extend(
            _run_direction_dixi(
                date,
                source,
                picked_block,
                picked_category,
                direction_sort_key,
                max_per_direction,
            )
        )
    if not requested or requested.intersection({"all", "qibao", "jssb", "hpqb"}):
        # 红盘起爆 pool. Sort by xiaocaoJSSB (sort_id=39) so the rule's break-on-low-score
        # iteration matches the dixi/lianban convention (input sorted by score desc).
        qibao_codes = source.get_pool(date, "qibao")
        if hasattr(source, "sort_codes"):
            qibao_codes = source.sort_codes(date, qibao_codes, "xiaocaoJSSB")
        qibao_details = source.get_stock_index(date, qibao_codes)
        output.extend(check_qibao(qibao_details, picked_block, picked_category, date))

    if exclude_modes:
        # Tag-only: signals from excluded modes stay in the output but are
        # marked shadow (adaptive_active=False). They still get scored and
        # written to mode_history so the mode's track record stays honest.
        new_output: list[dict[str, Any]] = []
        for row in output:
            if row.get("mode") in exclude_modes:
                row = dict(row)
                row["adaptive_active"] = False
                note = f"excluded by --exclude-modes: {row.get('mode')}"
                prev = row.get("adaptive_reason") or ""
                row["adaptive_reason"] = f"{prev}; {note}" if prev else note
            new_output.append(row)
        output = new_output

    # Annotate each signal with regime / main-line / big-cap status.
    output = _annotate_signals(output, regime, mainline_blocks, bigcap_codes)

    # Optional gates (off by default — these are evaluated in `backtest validate`).
    if regime_gate and regime:
        output = [r for r in output if mode_allowed_in(r.get("mode") or "", regime)]
    if require_main_line and mainline_blocks is not None:
        output = [r for r in output if r.get("is_main_line")]
    elif exclude_main_line and mainline_blocks is not None:
        # Inverse filter: keep only signals OFF the main-line. Hypothesis: our
        # rule modes (短线/弱转强/低吸) hunt for new direction rotations that
        # haven't yet entered the established main-line, per 小草 0413-A.
        output = [r for r in output if not r.get("is_main_line")]
    if adaptive_modes and adaptive_cache is not None:
        # Tag-only: every signal stays in the output; tag determines whether
        # it counts toward actual P&L (active=True) or shadow (active=False).
        # state_aware_adaptive=True (v3): use continuous StateVector fitness.
        # state_aware_adaptive=False (v2): legacy regime-label discrete fitness.
        # use_v3_4_profiles=True (v3.4): use MODE_PROFILE_V3_4 with momentum +
        # limitup_density bonus axes and dropped DBR preconditions.
        state = _state_for_date(date, adaptive_cache) if state_aware_adaptive else None
        adaptive_regime = regime if regime is not None else derive_proxy_regime(date, adaptive_cache)
        from .regime import MODE_PROFILE, MODE_PROFILE_V3_4
        profiles_arg = MODE_PROFILE_V3_4 if use_v3_4_profiles else MODE_PROFILE
        output, _ = tag_signals(
            output,
            date,
            adaptive_cache,
            trade_days=adaptive_trade_days,
            regime=adaptive_regime,
            state=state,
            mode_profiles=profiles_arg,
        )

    cap = max_open_pct if max_open_pct is not None else MAX_OPEN_PCT_CHANGE
    return _dedupe_signals(_filter_open_pct(output, cap))


def _run_direction_dixi(
    date: str,
    source: Any,
    picked_block: list[dict[str, Any]],
    picked_category: list[dict[str, Any]],
    direction_sort_key: int | str,
    max_per_direction: int | None,
) -> list[dict[str, Any]]:
    if not hasattr(source, "get_direction_codes"):
        return []
    output = []
    cap = max_per_direction if max_per_direction is not None else 10
    directions = [(item.get("blockCode"), None) for item in picked_block if item.get("blockCode")]
    directions.extend((None, item.get("categoryCode")) for item in picked_category if item.get("categoryCode"))
    for block_code, category_code in directions:
        codes = source.get_direction_codes(date, block_code=block_code, category_code=category_code)
        if not codes:
            continue
        if hasattr(source, "sort_codes"):
            codes = source.sort_codes(date, codes, direction_sort_key)
        details = source.get_stock_index(date, codes[:cap])
        output.extend(check_direction_dixi(details, picked_block, picked_category, date))
    return output


def _signal_blocks(row: dict[str, Any]) -> set[str]:
    """Pull all block-domain codes a signal's stock belongs to.

    Includes 中信行业 (ZHBK, via excIndustryCode), 东财板块 (DDBK, via
    blockCodeList), and 大类 (BKDL, via blockCategoryCodeList). The ZHBK code
    is what xiao_cao_industry_block_rank uses, so it's the field that
    intersects with the main-line set we compute from rolling block_rank.
    """
    out: set[str] = set()
    exc = row.get("excIndustryCode")
    if exc:
        out.add(str(exc))
    for key in ("blockCodeList", "blockCategoryCodeList"):
        v = row.get(key)
        if v is None:
            continue
        if isinstance(v, str):
            for part in v.split(","):
                p = part.strip()
                if p:
                    out.add(p)
        elif isinstance(v, list):
            for part in v:
                if part:
                    out.add(str(part))
    return out


def _annotate_signals(
    rows: list[dict[str, Any]],
    regime: str | None,
    mainline_blocks: set[str] | None,
    bigcap_codes: set[str] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        annotated = dict(r)
        if regime is not None:
            annotated["regime"] = regime
        if mainline_blocks is not None:
            blocks = _signal_blocks(r)
            annotated["is_main_line"] = bool(blocks & mainline_blocks)
        if bigcap_codes is not None:
            sid = r.get("code") or r.get("stockId")
            annotated["is_big_cap"] = sid is not None and str(sid) in bigcap_codes
        out.append(annotated)
    return out


def _dedupe_signals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse rows so each (date, code) pair appears at most once.

    Why: the previous key included `mode`, so the same stock matched by
    multiple rule sets (e.g. 接力低弱转1 + 接力低弱转2) leaked through and
    inflated exposure — empirically ~20% of (date, code) pairs in the
    2026-03-01..2026-04-24 backtest had duplicate rows. This collapses
    them, keeping the first-encountered mode (rule order is
    check_lianban → check_dixi → check_direction_dixi) and stashing the
    additional mode names under `dropped_modes` for transparency.
    """
    by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    order: list[tuple[Any, Any]] = []
    for row in rows:
        key = (row.get("date"), row.get("code"))
        if key not in by_key:
            by_key[key] = dict(row)
            order.append(key)
            continue
        kept = by_key[key]
        mode = row.get("mode")
        if mode and mode != kept.get("mode"):
            dropped = kept.setdefault("dropped_modes", [])
            if mode not in dropped:
                dropped.append(mode)
    return [by_key[k] for k in order]


def _filter_open_pct(rows: list[dict[str, Any]], cap: float = MAX_OPEN_PCT_CHANGE) -> list[dict[str, Any]]:
    """Mark high-open signals as shadow rather than dropping them.

    `openPctChange >= cap` (default 6%) is high-open chase territory — empirical
    evidence shows these systematically lose money. They are still emitted and
    scored so mode_history reflects truth, but `adaptive_active=False` keeps
    them out of real P&L. This mirrors how adaptive Tier 4 marks dormant
    modes shadow without dropping them.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if _num(row.get("openPctChange")) >= cap:
            row = dict(row)
            row["adaptive_active"] = False
            note = f"openPctChange ≥ {cap}% (chasing high open)"
            prev = row.get("adaptive_reason") or ""
            row["adaptive_reason"] = f"{prev}; {note}" if prev else note
        out.append(row)
    return out


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
