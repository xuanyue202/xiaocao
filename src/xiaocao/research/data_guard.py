"""Data-governance pre-flight guards — executable DATA_QUALITY.md.

This session burned three round-trips on data-governance traps, not analysis bugs.
Each is now a mechanical check so the learning pipeline fail-closes instead of
training on garbage. The guiding rule: **request-reachable range ≠ data-valid
range** — never trust that a value is real just because a row exists for that date.

The four traps, as guards:
  - data_valid_floor   : coverage vs CONTENT — catches zero/null-padded history
                         (concept returns were 0 before 2024-05 → fake +20~28pp).
  - trailing           : the lookahead-safe trailing window — use it for ANY
                         feature acted on at day i (a window including i faked a
                         +0.78 Sharpe sit-out edge that reversed once lagged).
  - looks_like_realized_pnl : a right-skewed (mean≫median) series is execution-
                         juiced PnL, not a raw price change — don't compare it to
                         a price series (the mode_history +2.3%/median−1.3% trap).
  - staleness          : data older than max_lag (the date_kline feed froze ~3wk).

`audit()` runs them and returns a report the flywheel can gate on.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def data_valid_floor(
    records: Sequence[Mapping[str, Any]], value_key: str, *, date_key: str = "day"
) -> dict[str, Any]:
    """First/last date with GENUINELY valid content vs the full date span.

    A date counts as valid only if it has at least one non-null, non-zero value.
    A large gap between span and valid range is the "coverage ≠ data" trap.
    """
    by_date: dict[str, list] = defaultdict(list)
    for r in records:
        d = r.get(date_key)
        if d is not None:
            by_date[str(d)].append(r.get(value_key))
    all_dates = sorted(by_date)
    valid = [d for d in all_dates
             if any(v is not None and v != 0 for v in by_date[d])]
    zero_dates = [d for d in all_dates if d not in set(valid)]
    return {
        "span": (all_dates[0], all_dates[-1]) if all_dates else (None, None),
        "valid_range": (valid[0], valid[-1]) if valid else (None, None),
        "n_dates": len(all_dates),
        "n_valid": len(valid),
        "n_zero_or_null": len(zero_dates),
        "coverage_is_data": len(zero_dates) == 0,
    }


def trailing(values: Sequence[Any], i: int, window: int, *, include_current: bool = False) -> list:
    """Lookahead-SAFE trailing slice ending at index i.

    By default EXCLUDES index i — the position/feature you act on at day i must not
    read day i's own outcome. Use this everywhere instead of hand-rolled slices
    (the hand-rolled `series[lo:i+1]` is exactly what caused the lookahead bug).
    """
    hi = i + 1 if include_current else i
    lo = max(0, hi - window)
    return list(values[lo:hi])


def looks_like_realized_pnl(returns: Sequence[float], *, gap: float = 1.0) -> dict[str, Any]:
    """Heuristic: is this a clean price-change series or execution-juiced PnL?

    A strongly right-skewed series (mean ≫ median, or mean>0 while median<0) is a
    realized strategy PnL (low win-rate, fat right tail) — comparing it to a raw
    price-change series is an apples-to-oranges 真实的谎言. Flags that case.
    """
    xs = [float(x) for x in returns if x is not None]
    if len(xs) < 8:
        return {"suspect_realized_pnl": False, "mean": 0.0, "median": 0.0, "n": len(xs)}
    m, med = _mean(xs), _median(xs)
    suspect = (m - med > gap) or (m > 0 and med < 0)
    return {"suspect_realized_pnl": bool(suspect), "mean": m, "median": med, "n": len(xs)}


def staleness(
    records: Sequence[Mapping[str, Any]], today: str, *, max_lag_days: int = 10, date_key: str = "day"
) -> dict[str, Any]:
    """Is the freshest data more than max_lag_days (calendar) behind today?"""
    from datetime import date
    dates = [str(r.get(date_key)) for r in records if r.get(date_key)]
    if not dates:
        return {"stale": True, "max_date": None, "lag_days": None}
    mx = max(dates)
    try:
        lag = (date.fromisoformat(today) - date.fromisoformat(mx[:10])).days
    except ValueError:
        return {"stale": False, "max_date": mx, "lag_days": None}
    return {"stale": lag > max_lag_days, "max_date": mx, "lag_days": lag}


def audit(
    records: Sequence[Mapping[str, Any]], value_key: str, *, today: str | None = None,
    date_key: str = "day", max_lag_days: int = 10, treat_as_returns: bool = False,
) -> dict[str, Any]:
    """Composite pre-flight. `ok=False` => the learning step should fail-closed."""
    floor = data_valid_floor(records, value_key, date_key=date_key)
    warnings: list[str] = []
    critical = False
    if not floor["coverage_is_data"]:
        frac = floor["n_zero_or_null"] / max(1, floor["n_dates"])
        msg = (f"{floor['n_zero_or_null']}/{floor['n_dates']} dates are zero/null — "
               f"data-valid range {floor['valid_range']} ⊂ span {floor['span']}; "
               f"pin the backtest to the valid range")
        warnings.append(msg)
        if frac > 0.10:
            critical = True
    if treat_as_returns:
        pnl = looks_like_realized_pnl([r.get(value_key) for r in records])
        if pnl["suspect_realized_pnl"]:
            warnings.append(
                f"series looks like execution-juiced PnL (mean {pnl['mean']:+.2f} ≫ "
                f"median {pnl['median']:+.2f}) — do NOT compare to a raw price-change series")
    if today is not None:
        st = staleness(records, today, max_lag_days=max_lag_days, date_key=date_key)
        if st["stale"]:
            warnings.append(f"stale: freshest {st['max_date']} is {st['lag_days']}d behind {today}")
            critical = True
    return {"ok": not critical, "valid_range": floor["valid_range"], "warnings": warnings}
