"""Shared short-line mode qualification and executable candidate selection.

The live recommendation, Book-B paper actuator, and historical replay must use
this module together.  Mode qualification is upstream of stock ranking:

* Every eligible mode contributes at most its highest-ranked stock each day.
* Recent dual-alpha strength promotes a mode directly to ACTIVE; deterioration
  reduces a formally ACTIVE mode to PROVISIONAL.
* COLD / UNKNOWN modes remain in the shadow dataset but cannot be bought.

Only executable all-hit forward labels may open the gate.  Signal days retain
the validated 25%/45%/50% evidence weights, and an
ACTIVE mode must robustly beat both the same-day executable pool and the
four-index benchmark.  The statistical open-to-next-close labels remain useful
research context, but have no trading authority here.
"""
from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ACTIVE = "ACTIVE"
PROVISIONAL = "PROVISIONAL"
COLD = "COLD"
UNKNOWN = "UNKNOWN"

# Recovered from the accepted 2026-07-10 fill-aware reform replay.  Windows are
# checked shortest-first; the first informative window owns the decision.
FORMAL_WINDOWS: tuple[tuple[int, int, int], ...] = (
    (20, 8, 12),
    (60, 15, 20),
    (120, 8, 10),
)
LCB80_Z = 0.8416212335729143
FAST_WINDOW = 5
FAST_MIN_DAYS = 3
FAST_MIN_SIGNALS = 5
FAST_MIN_POSITIVE_DAYS = 3

EVIDENCE_TOTAL_BY_SIGNAL_COUNT = {1: 0.25, 2: 0.45, 3: 0.50}
TARGET_TOTAL_BY_COUNT = {1: 0.50, 2: 0.50, 3: 0.50}
PROVISIONAL_TARGET_WEIGHT = 1.0 / 6.0
MAX_SINGLE_WEIGHT = 0.50
MODE_CONFIDENCE_WEIGHT = 0.25
EVIDENCE_WEIGHTING = "validated_25_45_50_by_mode_signal_count"


@dataclass(frozen=True)
class ModeEvidenceRow:
    signal_date: str
    code: str
    mode: str
    net_return_pct: float
    source: str = "live_executable_all_hit"
    market_return_pct: float | None = None


@dataclass(frozen=True)
class ModeWindowStats:
    window_days: int
    signal_days: int
    signals: int
    market_days: int
    effective_days: float
    raw_return_mean: float
    alpha_pool_mean: float
    alpha_pool_lcb80: float
    positive_alpha_days: int
    alpha_pool_without_best: float | None
    alpha_market_mean: float | None
    alpha_market_lcb80: float | None
    positive_market_alpha_days: int
    alpha_market_without_best: float | None
    latest_signal_date: str | None
    weighting: str = EVIDENCE_WEIGHTING


@dataclass(frozen=True)
class ModeDecision:
    mode: str
    state: str
    max_picks: int
    selected_window: int | None
    reason: str
    windows: dict[int, ModeWindowStats]
    evidence_source: str
    latest_evidence_date: str | None

    @property
    def trade_eligible(self) -> bool:
        return self.state in {ACTIVE, PROVISIONAL}


def _num(value: object, default: float | None = None) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def load_live_executable_evidence(path: str | Path) -> list[ModeEvidenceRow]:
    """Load the single authoritative recent mode-evidence substrate.

    Missing executable fields fail closed: theoretical ``net_realized_ret`` is
    deliberately not used as a substitute for executable shadow PnL.
    """
    source_path = Path(path)
    if not source_path.exists():
        return []
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return []
    try:
        frame = pd.read_parquet(source_path)
    except Exception:
        return []
    required = {"date", "code", "mode", "executable_net_ret", "executable_fillable"}
    if frame.empty or not required.issubset(frame.columns):
        return []

    frame = frame.copy()
    if "is_live" in frame.columns:
        frame = frame[frame["is_live"].map(_truthy)]
    if "book" in frame.columns:
        frame = frame[frame["book"].fillna("B").astype(str).eq("B")]
    frame = frame[frame["executable_fillable"].map(_truthy)]
    frame = frame[~frame["code"].astype(str).str.endswith(".BJSE")]
    frame["_ret"] = pd.to_numeric(frame["executable_net_ret"], errors="coerce")
    frame = frame[frame["_ret"].notna()]
    if frame.empty:
        return []
    frame["_date"] = frame["date"].astype(str).str[:10]
    frame["_code"] = frame["code"].astype(str)
    frame["_mode"] = frame["mode"].astype(str)
    frame = frame.sort_values(["_date", "_code"]).drop_duplicates(
        ["_date", "_code", "_mode"], keep="last"
    )
    market_col = "market_return_pct" if "market_return_pct" in frame.columns else None
    rows: list[ModeEvidenceRow] = []
    for record in frame.to_dict(orient="records"):
        market = _num(record.get(market_col)) if market_col else None
        rows.append(ModeEvidenceRow(
            signal_date=str(record["_date"]),
            code=str(record["_code"]),
            mode=str(record["_mode"]),
            net_return_pct=float(record["_ret"]),
            market_return_pct=market,
        ))
    return rows


def _normal_trade_days(trade_days: Sequence[str], evidence: Sequence[ModeEvidenceRow], asof: str) -> list[str]:
    days = {str(day)[:10] for day in trade_days if str(day)[:10] <= asof[:10]}
    days.update(row.signal_date for row in evidence if row.signal_date <= asof[:10])
    days.add(asof[:10])
    return sorted(days)


def _available_window_days(
    asof: str,
    window: int,
    trade_days: Sequence[str],
    evidence: Sequence[ModeEvidenceRow],
) -> list[str]:
    """Return signal dates knowable before ``asof`` morning.

    A D signal is sold at D+1 close and first becomes usable at D+2 morning, so
    the immediately previous trading day is excluded from the evidence window.
    """
    calendar = _normal_trade_days(trade_days, evidence, asof)
    prior = [day for day in calendar if day < asof[:10]]
    available = prior[:-1] if prior else []
    return available[-window:]


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    total_weight = sum(weights)
    if not values or total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in zip(values, weights)) / total_weight


def _weighted_mean_lcb80(
    values: Sequence[float],
    weights: Sequence[float],
) -> tuple[float, float, float]:
    """Return weighted mean, one-sided 80% LCB, and effective sample size."""
    mean = _weighted_mean(values, weights)
    if len(values) <= 1:
        return mean, float("-inf"), float(len(values))
    total_weight = sum(weights)
    squared_weight = sum(weight * weight for weight in weights)
    if total_weight <= 0 or squared_weight <= 0:
        return mean, float("-inf"), 0.0
    variance_denominator = total_weight - squared_weight / total_weight
    if variance_denominator <= 0:
        return mean, float("-inf"), 1.0
    variance = sum(
        weight * (value - mean) ** 2
        for value, weight in zip(values, weights)
    ) / variance_denominator
    effective_days = total_weight * total_weight / squared_weight
    lower = mean - LCB80_Z * math.sqrt(max(0.0, variance) / effective_days)
    return mean, lower, effective_days


def _weighted_mean_without_best(
    values: Sequence[float],
    weights: Sequence[float],
) -> float | None:
    if len(values) <= 1:
        return None
    best_index = max(range(len(values)), key=lambda index: values[index])
    remaining_values = [value for index, value in enumerate(values) if index != best_index]
    remaining_weights = [weight for index, weight in enumerate(weights) if index != best_index]
    return _weighted_mean(remaining_values, remaining_weights)


def _mode_day_weight(signal_count: int) -> float:
    return EVIDENCE_TOTAL_BY_SIGNAL_COUNT[min(3, max(1, signal_count))]


def _window_stats(
    mode: str,
    asof: str,
    window: int,
    evidence: Sequence[ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ModeWindowStats:
    days = set(_available_window_days(asof, window, trade_days, evidence))
    scoped = [row for row in evidence if row.signal_date in days]
    by_day: dict[str, list[ModeEvidenceRow]] = {}
    for row in scoped:
        by_day.setdefault(row.signal_date, []).append(row)

    raw_returns: list[float] = []
    alpha_pool: list[tuple[str, float]] = []
    alpha_market: list[float] = []
    day_weights: list[float] = []
    market_weights: list[float] = []
    signals = 0
    for day in sorted(by_day):
        day_rows = by_day[day]
        mode_rows = [row for row in day_rows if row.mode == mode]
        if not mode_rows:
            continue
        signals += len(mode_rows)
        mode_ret = statistics.mean(row.net_return_pct for row in mode_rows)
        pool_ret = statistics.mean(row.net_return_pct for row in day_rows)
        weight = _mode_day_weight(len(mode_rows))
        raw_returns.append(mode_ret)
        alpha_pool.append((day, mode_ret - pool_ret))
        day_weights.append(weight)
        market_values = [row.market_return_pct for row in day_rows if row.market_return_pct is not None]
        if market_values:
            alpha_market.append(mode_ret - statistics.mean(market_values))
            market_weights.append(weight)

    values = [value for _, value in alpha_pool]
    mean, lower, effective_days = _weighted_mean_lcb80(values, day_weights)
    market_mean: float | None = None
    market_lower: float | None = None
    if alpha_market:
        market_mean, market_lower, _ = _weighted_mean_lcb80(alpha_market, market_weights)
    return ModeWindowStats(
        window_days=window,
        signal_days=len(values),
        signals=signals,
        market_days=len(alpha_market),
        effective_days=effective_days,
        raw_return_mean=_weighted_mean(raw_returns, day_weights),
        alpha_pool_mean=mean,
        alpha_pool_lcb80=lower,
        positive_alpha_days=sum(value > 0 for value in values),
        alpha_pool_without_best=_weighted_mean_without_best(values, day_weights),
        alpha_market_mean=market_mean,
        alpha_market_lcb80=market_lower,
        positive_market_alpha_days=sum(value > 0 for value in alpha_market),
        alpha_market_without_best=_weighted_mean_without_best(alpha_market, market_weights),
        latest_signal_date=alpha_pool[-1][0] if alpha_pool else None,
    )


def decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ModeDecision:
    windows = {
        window: _window_stats(mode, asof, window, evidence, trade_days)
        for window, _, _ in FORMAL_WINDOWS
    }
    selected: ModeWindowStats | None = None
    state = UNKNOWN
    reason = "no executable window meets the sample floor"
    for window, min_days, min_signals in FORMAL_WINDOWS:
        stats = windows[window]
        if stats.signal_days < min_days or stats.signals < min_signals:
            continue
        selected = stats
        if stats.market_days != stats.signal_days:
            state = UNKNOWN
            reason = (
                f"{window}d benchmark incomplete: market days "
                f"{stats.market_days}/{stats.signal_days}"
            )
        elif (
            stats.alpha_pool_lcb80 > 0
            and stats.alpha_market_lcb80 is not None
            and stats.alpha_market_lcb80 > 0
        ):
            state = ACTIVE
            reason = (
                f"{window}d allocation-weighted executable dual alpha robust "
                f"(pool mean/LCB80 {stats.alpha_pool_mean:+.2f}/"
                f"{stats.alpha_pool_lcb80:+.2f}pp, market {stats.alpha_market_mean:+.2f}/"
                f"{stats.alpha_market_lcb80:+.2f}pp, days/signals "
                f"{stats.signal_days}/{stats.signals})"
            )
        else:
            state = COLD
            reason = (
                f"{window}d allocation-weighted executable dual alpha not robust "
                f"(pool mean/LCB80 {stats.alpha_pool_mean:+.2f}/"
                f"{stats.alpha_pool_lcb80:+.2f}pp, market "
                f"{(stats.alpha_market_mean or 0.0):+.2f}/"
                f"{(stats.alpha_market_lcb80 if stats.alpha_market_lcb80 is not None else float('-inf')):+.2f}pp, "
                f"days/signals {stats.signal_days}/{stats.signals})"
            )
        break

    fast = _window_stats(mode, asof, FAST_WINDOW, evidence, trade_days)
    windows[FAST_WINDOW] = fast
    fast_has_floor = (
        fast.signal_days >= FAST_MIN_DAYS
        and fast.signals >= FAST_MIN_SIGNALS
        and fast.market_days == fast.signal_days
    )
    fast_cooling = (
        state == ACTIVE
        and fast_has_floor
        and (
            fast.alpha_pool_mean <= 0
            or fast.alpha_market_mean is None
            or fast.alpha_market_mean <= 0
        )
    )
    fast_promotion = (
        fast_has_floor
        and fast.alpha_pool_mean > 0
        and fast.alpha_market_mean is not None
        and fast.alpha_market_mean > 0
        and fast.positive_alpha_days * 2 > fast.signal_days
        and fast.positive_market_alpha_days * 2 > fast.signal_days
    )
    fast_reactivation = (
        state != ACTIVE
        and fast_has_floor
        and fast.positive_alpha_days >= FAST_MIN_POSITIVE_DAYS
        and fast.positive_market_alpha_days >= FAST_MIN_POSITIVE_DAYS
        and fast.alpha_pool_without_best is not None
        and fast.alpha_pool_without_best > 0
        and fast.alpha_market_without_best is not None
        and fast.alpha_market_without_best > 0
    )
    if fast_cooling:
        state = PROVISIONAL
        selected = fast
        reason = (
            f"5d cooling from ACTIVE: allocation-weighted recent alpha "
            f"pool {fast.alpha_pool_mean:+.2f}pp / market "
            f"{(fast.alpha_market_mean or 0.0):+.2f}pp; max one pick until recovery"
        )
    elif fast_promotion:
        state = ACTIVE
        selected = fast
        reason = (
            f"5d direct ACTIVE promotion: recent dual-alpha mean and majority positive; "
            f"pool/market {fast.alpha_pool_mean:+.2f}/"
            f"{(fast.alpha_market_mean or 0.0):+.2f}pp, positive days "
            f"{fast.positive_alpha_days}/{fast.positive_market_alpha_days}/"
            f"{fast.signal_days}"
        )
    elif fast_reactivation:
        state = PROVISIONAL
        selected = fast
        reason = (
            f"5d fast dual reactivation: days/signals {fast.signal_days}/{fast.signals}, "
            f"positive pool/market days {fast.positive_alpha_days}/"
            f"{fast.positive_market_alpha_days}, alpha without best day pool/market "
            f"{fast.alpha_pool_without_best:+.2f}/"
            f"{fast.alpha_market_without_best:+.2f}pp"
        )

    usable_days = set(
        _available_window_days(
            asof,
            max(window for window, _, _ in FORMAL_WINDOWS),
            trade_days,
            evidence,
        )
    )
    latest = max(
        (row.signal_date for row in evidence if row.mode == mode and row.signal_date in usable_days),
        default=None,
    )
    sources = sorted({row.source for row in evidence if row.mode == mode})
    return ModeDecision(
        mode=mode,
        state=state,
        max_picks=1 if state in {ACTIVE, PROVISIONAL} else 0,
        selected_window=selected.window_days if selected else None,
        reason=reason,
        windows=windows,
        evidence_source="+".join(sources) if sources else "missing_executable_evidence",
        latest_evidence_date=latest,
    )


def decide_modes(
    modes: Iterable[str],
    asof: str,
    evidence: Sequence[ModeEvidenceRow],
    trade_days: Sequence[str],
) -> dict[str, ModeDecision]:
    return {
        mode: decide_mode(mode, asof, evidence, trade_days)
        for mode in sorted({str(mode) for mode in modes if str(mode)})
    }


def decision_fields(decision: ModeDecision) -> dict[str, Any]:
    selected = decision.windows.get(decision.selected_window or -1)
    confidence = _decision_confidence(decision)
    fast_health = fast_health_fields(decision)
    return {
        "mode_state": decision.state,
        "mode_state_reason": decision.reason,
        "mode_state_window": decision.selected_window,
        "mode_state_max_picks": decision.max_picks,
        "mode_trade_eligible": decision.trade_eligible,
        "mode_evidence_source": decision.evidence_source,
        "mode_evidence_latest_date": decision.latest_evidence_date,
        "mode_evidence_days": selected.signal_days if selected else 0,
        "mode_evidence_signals": selected.signals if selected else 0,
        "mode_evidence_market_days": selected.market_days if selected else 0,
        "mode_evidence_effective_days": round(selected.effective_days, 6) if selected else 0.0,
        "mode_evidence_weighting": selected.weighting if selected else EVIDENCE_WEIGHTING,
        "mode_return_raw": round(selected.raw_return_mean, 6) if selected else None,
        "mode_alpha_pool": round(selected.alpha_pool_mean, 6) if selected else None,
        "mode_alpha_pool_lcb80": round(selected.alpha_pool_lcb80, 6) if selected else None,
        "mode_alpha_market": (
            round(selected.alpha_market_mean, 6)
            if selected and selected.alpha_market_mean is not None else None
        ),
        "mode_alpha_market_lcb80": (
            round(selected.alpha_market_lcb80, 6)
            if selected and selected.alpha_market_lcb80 is not None else None
        ),
        **fast_health,
        "mode_exec_mode_confidence": confidence["confidence"],
        "mode_exec_confidence_source": confidence["mode_confidence_source"],
        "mode_exec_confidence_reason": confidence["mode_confidence_reason"],
    }


def fast_health_fields(decision: ModeDecision) -> dict[str, Any]:
    """Expose early deterioration as shadow telemetry without trade authority."""
    fast = decision.windows.get(FAST_WINDOW)
    if fast is None:
        return {
            "mode_fast_health": "INSUFFICIENT",
            "mode_fast_authority": "shadow_only",
            "mode_fast_days": 0,
            "mode_fast_signals": 0,
            "mode_fast_alpha_pool": None,
            "mode_fast_alpha_market": None,
            "mode_fast_positive_pool_days": 0,
            "mode_fast_positive_market_days": 0,
        }
    if decision.state == PROVISIONAL and decision.reason.startswith("5d cooling from ACTIVE"):
        health = "COOLING"
    elif fast.market_days != fast.signal_days:
        health = "INCOMPLETE"
    elif fast.signal_days < FAST_MIN_DAYS:
        health = "STALE" if decision.state == ACTIVE and fast.signal_days == 0 else "INSUFFICIENT"
    else:
        mean_bad = (
            fast.alpha_pool_mean <= 0
            or fast.alpha_market_mean is None
            or fast.alpha_market_mean <= 0
        )
        majority_bad = (
            fast.positive_alpha_days * 2 < fast.signal_days
            or fast.positive_market_alpha_days * 2 < fast.signal_days
        )
        if mean_bad or majority_bad:
            health = "DETERIORATING" if fast.signals >= FAST_MIN_SIGNALS else "EARLY_WARNING"
        elif (
            fast.alpha_pool_mean > 0
            and fast.alpha_market_mean is not None
            and fast.alpha_market_mean > 0
            and fast.positive_alpha_days * 2 > fast.signal_days
            and fast.positive_market_alpha_days * 2 > fast.signal_days
        ):
            health = "SUPPORTIVE"
        else:
            health = "MIXED"
    return {
        "mode_fast_health": health,
        "mode_fast_authority": "shadow_only",
        "mode_fast_days": fast.signal_days,
        "mode_fast_signals": fast.signals,
        "mode_fast_alpha_pool": round(fast.alpha_pool_mean, 6),
        "mode_fast_alpha_market": (
            round(fast.alpha_market_mean, 6) if fast.alpha_market_mean is not None else None
        ),
        "mode_fast_positive_pool_days": fast.positive_alpha_days,
        "mode_fast_positive_market_days": fast.positive_market_alpha_days,
    }


def _decision_confidence(decision: ModeDecision) -> dict[str, Any]:
    stats = decision.windows.get(decision.selected_window or -1)
    if stats is None:
        return {
            "confidence": 50.0,
            "mode_recent_avg": 0.0,
            "mode_recent_n": 0,
            "mode_confidence_source": decision.evidence_source,
            "mode_confidence_reason": "no informative executable dual-alpha window",
        }
    if stats.market_days != stats.signal_days or stats.alpha_market_mean is None:
        return {
            "confidence": 50.0,
            "mode_recent_avg": 0.0,
            "mode_recent_n": stats.signals,
            "mode_confidence_source": decision.evidence_source,
            "mode_confidence_reason": "incomplete executable market benchmark",
        }
    mean = min(stats.alpha_pool_mean, stats.alpha_market_mean)
    raw = 50.0 + max(-10.0, min(10.0, mean)) * 4.0
    shrink = min(1.0, stats.signal_days / 8.0)
    confidence = 50.0 + (raw - 50.0) * shrink
    return {
        "confidence": round(max(0.0, min(100.0, confidence)), 2),
        "mode_recent_avg": round(mean, 6),
        "mode_recent_n": stats.signals,
        "mode_confidence_source": "live executable allocation-weighted dual alpha",
        "mode_confidence_reason": (
            f"{stats.window_days}d executable conservative dual alpha {mean:+.2f}pp "
            f"(pool {stats.alpha_pool_mean:+.2f}, market {stats.alpha_market_mean:+.2f}) "
            f"days/signals {stats.signal_days}/{stats.signals}"
        ),
    }


def confidence_map_from_decisions(
    decisions: Mapping[str, ModeDecision],
) -> dict[str, dict[str, Any]]:
    """Return the live rank/basket confidence map from the same gate evidence."""
    return {mode: _decision_confidence(decision) for mode, decision in decisions.items()}


def annotate_candidates(
    candidates: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, ModeDecision],
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        mode = str(row.get("mode") or "")
        decision = decisions.get(mode)
        if decision is None:
            decision = ModeDecision(
                mode=mode,
                state=UNKNOWN,
                max_picks=0,
                selected_window=None,
                reason="mode missing from executable evidence decision",
                windows={},
                evidence_source="missing_executable_evidence",
                latest_evidence_date=None,
            )
        row.update(decision_fields(decision))
        rank_score = _num(row.get("rank_score"))
        stock_rank_score = _num(row.get("stock_rank_score"))
        if stock_rank_score is None and rank_score is not None:
            previous_confidence = _num(row.get("mode_confidence"), 50.0)
            stock_rank_score = rank_score - float(previous_confidence or 0.0) * MODE_CONFIDENCE_WEIGHT
        executable_confidence = _num(row.get("mode_exec_mode_confidence"), 50.0)
        row["mode_exec_rank_score"] = (
            round(stock_rank_score + float(executable_confidence or 0.0) * MODE_CONFIDENCE_WEIGHT, 6)
            if stock_rank_score is not None else rank_score
        )
        annotated.append(row)
    return annotated


def _rank_percentiles(rows: Sequence[dict[str, Any]], key: str) -> dict[int, float]:
    valid: list[tuple[int, float]] = []
    for index, row in enumerate(rows):
        value = _num(row.get(key))
        if value is not None:
            valid.append((index, value))
    if not valid:
        return {index: 0.5 for index in range(len(rows))}
    valid.sort(key=lambda item: item[1])
    out = {index: 0.5 for index in range(len(rows))}
    cursor = 0
    total = len(valid)
    while cursor < total:
        end = cursor + 1
        while end < total and valid[end][1] == valid[cursor][1]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        percentile = average_rank / total
        for position in range(cursor, end):
            out[valid[position][0]] = percentile
        cursor = end
    return out


def target_weights(states: Sequence[str]) -> list[float]:
    count = len(states)
    if count == 0:
        return []
    if count > 3:
        raise ValueError("short-line batch supports at most three candidates")
    provisional = sum(state == PROVISIONAL for state in states)
    active = count - provisional
    if active == 0:
        return [PROVISIONAL_TARGET_WEIGHT] * count
    total = TARGET_TOTAL_BY_COUNT[count]
    active_total = min(total - provisional * PROVISIONAL_TARGET_WEIGHT, MAX_SINGLE_WEIGHT * active)
    active_weight = max(0.0, active_total) / active
    return [PROVISIONAL_TARGET_WEIGHT if state == PROVISIONAL else active_weight for state in states]


def select_executable_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Apply the shared mode gate, soft stock rank, and target weights.

    The returned list contains all candidates with executable-star annotations;
    selected rows are also mutated in the original dictionaries when possible so
    the live capture path can persist the exact decision.
    """
    rows = [dict(candidate) for candidate in candidates]
    for row in rows:
        row.update({
            "mode_exec_star": False,
            "mode_exec_rank": 9999,
            "mode_exec_score": None,
            "mode_exec_target_weight": 0.0,
            "mode_exec_candidate_rank": 9999,
        })
    eligible = [
        row for row in rows
        if _truthy(row.get("mode_trade_eligible"))
        and not str(row.get("code") or "").endswith(".BJSE")
    ]
    for row in eligible:
        if _num(row.get("mode_exec_rank_score")) is None:
            row["mode_exec_rank_score"] = _num(row.get("rank_score"), 0.0)
    rank_pct = _rank_percentiles(eligible, "mode_exec_rank_score")
    k_pct = _rank_percentiles(eligible, "k_score")
    p_pct = _rank_percentiles(eligible, "p_score")
    for index, row in enumerate(eligible):
        row["mode_exec_score"] = 0.50 * rank_pct[index] + 0.25 * k_pct[index] + 0.25 * p_pct[index]
    eligible.sort(key=lambda row: (
        -float(row.get("mode_exec_score") or 0.0),
        -float(_num(row.get("mode_exec_rank_score"), 0.0) or 0.0),
        -float(_num(row.get("p_score"), 0.0) or 0.0),
        str(row.get("code") or ""),
    ))
    for candidate_rank, row in enumerate(eligible, 1):
        row["mode_exec_candidate_rank"] = candidate_rank

    selected: list[dict[str, Any]] = []
    selected_modes: set[str] = set()
    for row in eligible:
        mode = str(row.get("mode") or "")
        if mode in selected_modes:
            continue
        selected_modes.add(mode)
        selected.append(row)
        if len(selected) >= max(0, min(3, top_n)):
            break
    weights = target_weights([str(row.get("mode_state") or UNKNOWN) for row in selected])
    for rank, (row, weight) in enumerate(zip(selected, weights), 1):
        row["mode_exec_star"] = True
        row["mode_exec_rank"] = rank
        row["mode_exec_target_weight"] = weight

    by_key = {
        (str(row.get("code") or ""), str(row.get("mode") or "")): row
        for row in rows
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = (str(candidate.get("code") or ""), str(candidate.get("mode") or ""))
        selected_row = by_key.get(key)
        if selected_row is not None:
            candidate.update(selected_row)
    return rows


def plan_board_lot_orders(
    ranked_candidates: Sequence[Mapping[str, Any]],
    *,
    nav: float,
    cash_limit: float,
    fee_rate: float,
    price_key: str = "execution_price",
    max_candidates: int = 8,
    max_batch_ratio: float = 0.50,
    target_scale: float = 1.0,
    per_position_cash_cap: float | None = None,
    weight_resolver: Callable[[Sequence[Mapping[str, Any]]], Sequence[float]] | None = None,
    max_single_weight: float = MAX_SINGLE_WEIGHT,
) -> list[dict[str, Any]]:
    """Jointly choose up to three candidates and 100-share board lots.

    The objective follows the accepted fill-aware replay: maximize represented
    candidates first, then ranking quality, target-weight fit, and capital use.
    A price that cannot express the requested risk within 50%-150% of target is
    skipped so the next ranked candidate can be considered.
    """
    if nav <= 0 or cash_limit <= 0:
        return []
    candidates = [
        dict(row) for row in ranked_candidates[:max_candidates]
        if _num(row.get(price_key)) not in (None, 0.0)
        and str(row.get("mode_state") or "") in {ACTIVE, PROVISIONAL}
        and not str(row.get("code") or "").endswith(".BJSE")
    ]
    best: tuple[tuple[float, ...], list[dict[str, Any]], tuple[int, ...], list[float], list[float]] | None = None
    batch_cash = min(float(cash_limit), float(nav) * max_batch_ratio)
    for count in range(min(3, len(candidates)), 0, -1):
        for indices in itertools.combinations(range(len(candidates)), count):
            subset = [candidates[index] for index in indices]
            modes = [str(row.get("mode") or "") for row in subset]
            if len(modes) != len(set(modes)):
                continue
            weights = list(weight_resolver(subset)) if weight_resolver else target_weights(
                [str(row.get("mode_state")) for row in subset]
            )
            effective_weights = [float(weight) * target_scale for weight in weights]
            if (
                len(weights) != len(subset)
                or any(not math.isfinite(float(weight)) or float(weight) <= 0 for weight in effective_weights)
                or sum(effective_weights) > max_batch_ratio + 1e-9
            ):
                continue
            quantity_options: list[list[int]] = []
            representable = True
            effective_targets: list[float] = []
            for row, weight in zip(subset, effective_weights):
                price = float(_num(row.get(price_key), 0.0) or 0.0)
                lot_cash = 100.0 * price * (1.0 + fee_rate)
                target_cash = weight * nav
                if per_position_cash_cap is not None:
                    target_cash = min(target_cash, max(0.0, float(per_position_cash_cap)))
                effective_targets.append(target_cash / nav if nav > 0 else 0.0)
                lower = 0.50 * target_cash
                upper = min(1.50 * target_cash, max_single_weight * nav)
                if per_position_cash_cap is not None:
                    upper = min(upper, max(0.0, float(per_position_cash_cap)))
                center = target_cash / lot_cash
                lower_lots = max(1, math.ceil(lower / lot_cash))
                upper_lots = max(1, math.floor(upper / lot_cash))
                seeds = {
                    1,
                    lower_lots,
                    lower_lots + 1,
                    max(1, upper_lots - 1),
                    upper_lots,
                    max(1, math.floor(center) - 2),
                    max(1, math.floor(center) - 1),
                    max(1, math.floor(center)),
                    max(1, math.ceil(center)),
                    max(1, math.ceil(center) + 1),
                    max(1, math.ceil(center) + 2),
                }
                options = sorted(
                    quantity for quantity in seeds
                    if lower - 1e-6 <= quantity * lot_cash <= upper + 1e-6
                )
                if not options:
                    representable = False
                    break
                quantity_options.append(options)
            if not representable:
                continue
            for quantities in itertools.product(*quantity_options):
                costs = [
                    quantity * 100.0 * float(row[price_key]) * (1.0 + fee_rate)
                    for quantity, row in zip(quantities, subset)
                ]
                total = sum(costs)
                if total > batch_cash + 1e-6:
                    continue
                error = sum(
                    ((cost / nav) - weight) ** 2
                    for cost, weight in zip(costs, effective_targets)
                )
                objective = (-float(count), float(sum(indices)), error, -total)
                if best is None or objective < best[0]:
                    best = (objective, subset, quantities, costs, effective_targets)
        if best is not None:
            break
    if best is None:
        return []
    _, subset, quantities, costs, weights = best
    planned: list[dict[str, Any]] = []
    for row, quantity, cost, weight in zip(subset, quantities, costs, weights):
        row["mode_exec_target_weight"] = weight
        row["mode_exec_planned_shares"] = int(quantity * 100)
        row["mode_exec_planned_cash_out"] = float(cost)
        planned.append(row)
    return planned


def decision_as_dict(decision: ModeDecision) -> dict[str, Any]:
    payload = asdict(decision)
    payload["trade_eligible"] = decision.trade_eligible
    return payload
