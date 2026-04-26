"""Cache-only replay tooling.

Reads the artifacts produced by `xiaocao backtest run --no-adaptive-modes` (the
seed run that populated SQLite cache + mode_history), then re-evaluates
candidate gate configs WITHOUT touching the API.

Universe = every signal that has a recorded next-day outcome. Each tuning
script imports `load_universe()` and feeds it through a `gate_fn(sig) -> bool`
(active=True / shadow=False) to compute train/test stats.

Train  = 2025-12-01 .. 2026-03-31
Test   = 2026-04-01 .. 2026-04-30  (held out)
"""
from __future__ import annotations

import csv
import glob
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402

SEED_DIR = ROOT / "output" / "xiaocao_5month_seed"
CACHE_DB = ROOT / "output" / ".cache" / "xiaocao.db"

TRAIN_START = "2025-12-01"
TRAIN_END = "2026-03-31"  # inclusive
TEST_START = "2026-04-01"
TEST_END = "2026-04-30"  # inclusive


@dataclass(frozen=True)
class SignalRecord:
    """Flat signal + outcome row for offline tuning."""

    date: str
    code: str
    mode: str
    return_pct: float
    open_pct: float
    excIndustryCode: str | None
    blockCodeList: tuple[str, ...]
    blockCategoryCodeList: tuple[str, ...]
    raw: dict[str, Any]  # full signal dict for ad-hoc fields

    def in_train(self) -> bool:
        return TRAIN_START <= self.date <= TRAIN_END

    def in_test(self) -> bool:
        return TEST_START <= self.date <= TEST_END

    def blocks(self) -> set[str]:
        out: set[str] = set()
        if self.excIndustryCode:
            out.add(self.excIndustryCode)
        out.update(self.blockCodeList)
        out.update(self.blockCategoryCodeList)
        return out


def _normalize_codes(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(p.strip() for p in value.split(",") if p.strip())
    if isinstance(value, list):
        return tuple(str(p) for p in value if p)
    return ()


def load_universe(
    seed_dir: Path = SEED_DIR,
) -> list[SignalRecord]:
    """Load every signal that has an outcome.

    Joins signals_<date>.json (universe) with trades.csv (returnPct) on
    (date, mode, code). Drops signals from the last day (no next-day price).
    """
    trades_path = seed_dir / "trades.csv"
    if not trades_path.exists():
        raise SystemExit(f"missing {trades_path} — run seed backtest first")
    keyed: dict[tuple[str, str, str], dict[str, Any]] = {}
    with trades_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            keyed[(row["buyDate"], row["mode"], row["code"])] = row

    out: list[SignalRecord] = []
    for path in sorted(seed_dir.glob("signals_*.json")):
        date = path.stem.replace("signals_", "")
        sigs = json.loads(path.read_text(encoding="utf-8"))
        for s in sigs:
            mode = s.get("mode") or ""
            code = s.get("code") or ""
            tr = keyed.get((date, mode, code))
            if tr is None:
                # Last-day signals have no outcome (no follow-up trading day)
                continue
            try:
                ret = float(tr["returnPct"])
                op = float(tr.get("openPctChange") or 0.0)
            except (TypeError, ValueError):
                continue
            out.append(
                SignalRecord(
                    date=date,
                    code=str(code),
                    mode=str(mode),
                    return_pct=ret,
                    open_pct=op,
                    excIndustryCode=(s.get("excIndustryCode") or None) and str(s.get("excIndustryCode")),
                    blockCodeList=_normalize_codes(s.get("blockCodeList")),
                    blockCategoryCodeList=_normalize_codes(s.get("blockCategoryCodeList")),
                    raw=s,
                )
            )
    return out


def trade_days_in_universe(universe: list[SignalRecord]) -> list[str]:
    return sorted({s.date for s in universe})


@dataclass
class StatBlock:
    n: int
    avg: float
    median: float
    win_rate: float
    sum: float
    best: float
    worst: float

    def fmt(self) -> str:
        if self.n == 0:
            return "n=0"
        return (
            f"n={self.n:>3} avg={self.avg:+5.2f}% win={self.win_rate:>4.1f}%"
            f" median={self.median:+5.2f}% sum={self.sum:+6.1f}%"
        )


def stats(values: list[float]) -> StatBlock:
    if not values:
        return StatBlock(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    wins = sum(1 for v in values if v > 0)
    return StatBlock(
        n=len(values),
        avg=statistics.mean(values),
        median=statistics.median(values),
        win_rate=wins / len(values) * 100,
        sum=sum(values),
        best=max(values),
        worst=min(values),
    )


def evaluate(
    universe: list[SignalRecord],
    gate_fn: Callable[[SignalRecord], bool],
) -> tuple[StatBlock, StatBlock, StatBlock, StatBlock]:
    """Return (train_active, train_shadow, test_active, test_shadow) stats."""
    ta, ts, va, vs = [], [], [], []
    for sig in universe:
        active = gate_fn(sig)
        if sig.in_train():
            (ta if active else ts).append(sig.return_pct)
        elif sig.in_test():
            (va if active else vs).append(sig.return_pct)
    return stats(ta), stats(ts), stats(va), stats(vs)


# ---------------------------------------------------------------------------
# Candidate gate constructors
# ---------------------------------------------------------------------------

VALIDATED_EXCLUDE = {"接力低弱转2", "方向内绿盘低吸前3名"}


def gate_validated_baseline(max_open_pct: float = 6.0) -> Callable[[SignalRecord], bool]:
    """The current 'validated' profile baseline: exclude two bad modes + open-pct cap."""

    def gate(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        if sig.open_pct >= max_open_pct:
            return False
        return True

    return gate


def gate_with_adaptive(
    cache: SQLiteCache,
    trade_days: list[str],
    n_min_by_window: dict[int, int] | None = None,
    avg_threshold_by_window: dict[int, float] | None = None,
    exclude_modes: set[str] | None = None,
    max_open_pct: float = 6.0,
    require_main_line: set[str] | None = None,  # if set, signal must hit this set per-day
    exclude_main_line: set[str] | None = None,  # if set, signal must NOT hit
) -> Callable[[SignalRecord], bool]:
    """Build a gate that combines all knobs."""
    from xiaocao.strategy.adaptive import decide_mode_state

    excl = exclude_modes if exclude_modes is not None else VALIDATED_EXCLUDE

    def gate(sig: SignalRecord) -> bool:
        if sig.mode in excl:
            return False
        if sig.open_pct >= max_open_pct:
            return False
        if require_main_line is not None and not (sig.blocks() & require_main_line):
            return False
        if exclude_main_line is not None and (sig.blocks() & exclude_main_line):
            return False
        # adaptive last (most expensive)
        d = decide_mode_state(
            sig.mode,
            sig.date,
            cache,
            n_min_by_window=n_min_by_window,
            avg_threshold_by_window=avg_threshold_by_window,
            trade_days=trade_days,
        )
        return d.active

    return gate


def open_cache() -> SQLiteCache:
    return SQLiteCache(CACHE_DB)
