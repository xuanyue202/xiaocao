"""Human-readable explanation layer for strategy signals (Plan A7).

For each signal row, produce a markdown block that traces:
  - which mode / direction
  - state vector at signal date (5 axes incl momentum, limitup_density)
  - mode profile preferences (wants_reward / wants_risk / wants_continuity)
  - per-axis alignment scores
  - precondition pass/fail
  - mode_fitness aggregate
  - raw mode scores (jssb / xcjw / cjs / jsjl)
  - adaptive tag (active vs shadow) and the reason
  - direction / main-line / big-cap flags

Used by `xiaocao strategy run --explain` and as a reusable module by
intraday paper-log emitter (Phase C2).
"""
from __future__ import annotations

from typing import Any

from .regime import (
    MODE_PROFILE,
    PRECONDITION_FAIL,
    _TARGET_LEVEL,
    align,
    mode_fitness,
)
from .state import StateVector


def _flag(value: Any) -> str:
    return "Y" if value else "-"


def _num_or_dash(value: Any, fmt: str = "{:.0f}") -> str:
    if isinstance(value, (int, float)) and value:
        return fmt.format(value)
    return "-"


def _axis_line(axis_name: str, want: str, observed: float) -> str:
    if want == "any":
        return f"  - {axis_name:<10s} (any)        : obs={observed:.3f}, align +0.000 (no preference)"
    target = _TARGET_LEVEL.get(want)
    a = align(want, observed)
    if target is None:
        return f"  - {axis_name:<10s} ({want})       : obs={observed:.3f}, align {a:+.3f}"
    return (f"  - {axis_name:<10s} ({want} → tgt {target:.2f}): "
            f"obs={observed:.3f}, align {a:+.3f}")


def explain_signal(row: dict[str, Any], state: StateVector | None) -> str:
    """Return a markdown block explaining one signal."""
    code = str(row.get("code", "?"))
    name = str(row.get("name", row.get("codeName", "")))
    mode = str(row.get("mode", "?"))
    profile = MODE_PROFILE.get(mode)

    L: list[str] = []
    L.append(f"### {code} {name} — {mode}")
    L.append("")

    # Adaptive tag
    active = row.get("adaptive_active")
    reason = row.get("adaptive_reason") or ""
    L.append(f"- **adaptive**: {'ACTIVE' if active else 'SHADOW' if active is False else '—'}"
             + (f" ({reason})" if reason else ""))

    # State vector (5+ axes)
    if state is not None:
        L.append(
            f"- **state**: reward={state.reward:.3f} risk={state.risk:.3f} "
            f"continuity={state.continuity:.3f} dbr={state.duan_ban_recovery:.3f} "
            f"momentum={state.momentum:.3f} limitup={state.limitup_density:.3f}"
        )
        L.append(f"  (n_samples={state.n_samples}, n_continuity={state.n_continuity}, "
                 f"n_duan_ban={state.n_duan_ban}, n_momentum={state.n_momentum})")
    else:
        L.append("- **state**: (unavailable)")

    # Mode profile
    if profile is not None:
        L.append(
            f"- **profile**: bet={profile.direction_bet}, "
            f"wants_reward={profile.wants_reward}, wants_risk={profile.wants_risk}, "
            f"wants_continuity={profile.wants_continuity}"
            + (", precondition=present" if profile.precondition is not None else "")
        )

        # Per-axis alignment (only if state available)
        if state is not None:
            L.append("- **per-axis align**:")
            L.append(_axis_line("reward", profile.wants_reward, state.reward))
            L.append(_axis_line("risk", profile.wants_risk, state.risk))
            L.append(_axis_line("continuity", profile.wants_continuity, state.continuity))

        # mode_fitness aggregate (uses regime.py logic — single source of truth)
        f = mode_fitness(mode, state)
        if f == PRECONDITION_FAIL:
            L.append(
                "- **mode_fitness**: PRECONDITION_FAIL "
                "(shadow/ranking telemetry; no qualification authority)"
            )
        else:
            L.append(
                f"- **mode_fitness**: {f:+.3f} "
                "(shadow/ranking telemetry; no qualification authority)"
            )
        if row.get("adaptive_auxiliary_authority"):
            L.append(
                "- **auxiliary authority**: "
                f"{row['adaptive_auxiliary_authority']}"
            )
    else:
        L.append(f"- **profile**: (unknown mode `{mode}`)")

    # Raw scores
    L.append(
        f"- **raw scores**: jssb={_num_or_dash(row.get('jssb'))} "
        f"xcjw={_num_or_dash(row.get('xcjw'))} cjs={_num_or_dash(row.get('cjs'))} "
        f"jsjl={_num_or_dash(row.get('jsjl'))}"
    )

    # Flags
    L.append(
        f"- **flags**: direction={_flag(row.get('direction'))} "
        f"mainline={_flag(row.get('is_main_line'))} bigcap={_flag(row.get('is_big_cap'))} "
        f"open_pct={row.get('openPctChange') if row.get('openPctChange') is not None else '-'}"
    )

    # Reason / human-readable rule trigger
    if row.get("reason"):
        L.append(f"- **rule reason**: {row['reason']}")
    if row.get("regime"):
        L.append(f"- **regime label**: {row['regime']}")

    L.append("")
    return "\n".join(L)


def explain_rows(rows: list[dict[str, Any]], state: StateVector | None,
                 date: str | None = None) -> str:
    """Render full markdown explanation for all rows on one date."""
    L: list[str] = []
    L.append(f"# Strategy explain — {date or '(date unspecified)'}")
    L.append("")
    if state is not None:
        regime_summary = []
        if state.risk < 0.4:
            regime_summary.append("低 risk(positive_ratio)→偏空头")
        elif state.risk > 0.6:
            regime_summary.append("高 risk→偏多头")
        if state.continuity >= 0.6:
            regime_summary.append("高 continuity→主线延续")
        elif state.continuity <= 0.3:
            regime_summary.append("低 continuity→主线切换")
        if state.momentum >= 0.65:
            regime_summary.append("高 momentum→bull week")
        elif state.momentum <= 0.35:
            regime_summary.append("低 momentum→bear week")
        L.append("## State summary")
        L.append("")
        L.append(
            f"- reward={state.reward:.3f} risk={state.risk:.3f} "
            f"continuity={state.continuity:.3f} dbr={state.duan_ban_recovery:.3f} "
            f"momentum={state.momentum:.3f} limitup={state.limitup_density:.3f}"
        )
        if regime_summary:
            L.append(f"- inferred: {' | '.join(regime_summary)}")
        L.append("")
    L.append(f"## Signals ({len(rows)} total)")
    L.append("")

    # Group active vs shadow
    actives = [r for r in rows if r.get("adaptive_active") is True]
    shadows = [r for r in rows if r.get("adaptive_active") is False]
    other = [r for r in rows if r.get("adaptive_active") not in (True, False)]
    L.append(f"- ACTIVE: {len(actives)} | SHADOW: {len(shadows)} | UNTAGGED: {len(other)}")
    L.append("")

    for label, sub in [("ACTIVE", actives), ("SHADOW", shadows), ("UNTAGGED", other)]:
        if not sub:
            continue
        L.append(f"## {label} signals ({len(sub)})")
        L.append("")
        for r in sub:
            L.append(explain_signal(r, state))
    return "\n".join(L)
