"""Strategy & risk parameter registry — the single declarative source of truth.

Consolidates the thresholds that were scattered across rules.py, exit_policy.py,
quality_governor.py and paper_record.py into one place, making the **frozen vs
tunable** boundary explicit. Borrowed in spirit from QuantDinger's `# @param`
metadata, but as a central registry.

Consumer wiring (important): `strategy/rules.py` and `live/exit_policy.py` IMPORT
their values from this registry, so an edit here changes their behavior directly.
`kronos_screen/quality_governor.py` and `paper_record.py` keep their own literal
copies (they are kronos-tier scripts) and are kept in sync only by the
value-equality drift test (tests/test_params.py) — editing a value here does NOT
propagate to them; it makes the drift test fail until their literal is also
updated. Treat that test failure as the signal to update both.

CRITICAL: registry values are frozen against unattended tuning. A value changes
only after the research/human gate documented in `docs/OPERATING_CONTRACT.md`;
paper-only promotions must say so in their provenance instead of being described
as validated real-capital parameters. The 2026-07-10 Book-B mode-switch gate set
the daily batch cap to 50% and the overlapping T+1 exposure cap to 100%. The
`range` is only a research search space, never permission to auto-tune.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Param:
    name: str
    value: Any
    owner: str            # where it is consumed
    note: str             # what it does / validation provenance
    range: tuple | None = None  # (lo, hi[, step]) search space for the research harness
    frozen: bool = True   # only the research harness may flip this, after a PASS verdict


REGISTRY: dict[str, Param] = {
    # --- 一级筛选 mode thresholds (rules.py) -------------------------------- #
    "SUPER_JW": Param("SUPER_JW", 300, "strategy.rules", "小草竞王 super tier; 接力低弱转1 gate", (200, 400, 25)),
    "STRONG_JW": Param("STRONG_JW", 200, "strategy.rules", "strong tier; 接力/低位/起爆 base gate", (150, 300, 25)),
    "QUALIFIED_JW": Param("QUALIFIED_JW", 150, "strategy.rules", "qualified tier; 低吸/方向 base gate", (100, 200, 25)),
    "DIRECTION_DISCOUNT": Param("DIRECTION_DISCOUNT", 1.3, "strategy.rules",
                                "板块方向共振时阈值除以此 (threshold/1.3)", (1.1, 1.6, 0.1)),
    "RAW_QIBAO_RANK_TOP_N": Param(
        "RAW_QIBAO_RANK_TOP_N", 10, "strategy.rules",
        "raw qibao rank 标杆分支: 取小草红盘起爆 raw rank 前 N; XH-037 PASS 2025-07-01..2026-06-29",
        (5, 20, 1),
    ),
    "RAW_QIBAO_OPEN_PCT_CAP": Param(
        "RAW_QIBAO_OPEN_PCT_CAP", 6.0, "strategy.rules",
        "raw qibao rank 标杆分支: 可控开幅上限; XH-037 PASS 2025-07-01..2026-06-29",
        (3.0, 8.0, 0.5),
    ),
    "RAW_QIBAO_HIGH_OPEN_PCT_CAP": Param(
        "RAW_QIBAO_HIGH_OPEN_PCT_CAP", 10.0, "strategy.rules",
        "raw qibao rank 高开标杆分支: open 6-10; XH-037 follow-up PASS + 2026-06-30 human gate for paper-only",
        (8.0, 12.0, 0.5),
    ),
    # --- 二级筛选 quality governor (quality_governor.py) -------------------- #
    "PRIMARY_THRESHOLD": Param("PRIMARY_THRESHOLD", 150.0, "kronos_screen.quality_governor",
                               "K->P primary_score 下限; below => weak_primary (shadow default)", (100.0, 200.0, 10.0)),
    # --- 出场 staged exit (live/exit_policy.py) ----------------------------- #
    "PROFILE_DD": Param("PROFILE_DD", {"v5": 2.0, "v6": 0.5}, "live.exit_policy",
                        "soft trailing dd%% per profile; executed at 14:55 not intraday"),
    "PROFILE_HARD_DD": Param("PROFILE_HARD_DD", {"v5": 8.0, "v6": 8.0}, "live.exit_policy",
                             "intraday hard floor dd%% — the ONLY stop executed intraday"),
    # --- 仓位/资金 sizing (paper_record.py) --------------------------------- #
    "DEPLOY_RATIO": Param("DEPLOY_RATIO", 0.5, "kronos_screen.paper_record",
                          "Book-B daily batch cap / settled NAV; 2026-07-10 human-gated paper mode switch",
                          (0.25, 1.0, 0.25)),
    "MAX_TOTAL_EXPOSURE_RATIO": Param(
        "MAX_TOTAL_EXPOSURE_RATIO", 1.0, "kronos_screen.paper_record",
        "Book-B overlapping T+1 gross exposure cap / settled NAV; paper-only human gate 2026-07-10",
        (0.5, 1.0, 0.1),
    ),
    "FEE_RATE": Param("FEE_RATE", 0.0001, "kronos_screen.paper_record", "one-way transaction fee (1bp)", None),
}


# --- Book T (趋势主线) — paper-only simulation defaults ---------------------- #
# These frozen values drive the Book-T PAPER simulator only. They are not evidence
# that a trend-selection edge has passed; the edge still needs trend_guards
# (compounded / max-dd / turnover / vs-beta) + §10 before it can graduate into
# the validated live SSOT above. The point of consuming them now is to start
# accumulating a real, separate trend-book ledger without contaminating Book B or
# continuous_optimize.
BOOK_T_PROPOSED: dict[str, Param] = {
    "TREND_BUDGET_RATIO": Param(
        "TREND_BUDGET_RATIO", 0.30, "trend.allocator (paper-only)",
        "PAPER: equity share allocated to Book T vs 短线; not a validated edge", (0.0, 0.5, 0.1)),
    "TREND_LOOKBACK_L": Param(
        "TREND_LOOKBACK_L", 60, "trend.mainline_signal (paper-only)",
        "PAPER: trailing trend-strength lookback (trading days); XH-018 prior L=60-120", (20, 120, 20)),
    "TREND_REBALANCE_R": Param(
        "TREND_REBALANCE_R", 60, "trend.allocator (paper-only)",
        "PAPER: rebalance/hold horizon (days); the +6~20pp alpha lived at R>=60 (long-hold), "
        "R=20 churn ~0", (20, 120, 20)),
    "TREND_TOP_M": Param(
        "TREND_TOP_M", 3, "trend.trend_rules (paper-only)",
        "PAPER: # mainline big-caps held (小草 平铺 2-3 最强)", (2, 5, 1)),
    "TREND_TRAIL_DD": Param(
        "TREND_TRAIL_DD", 12.0, "trend.exit_policy (paper-only)",
        "PAPER: wider trailing dd%%; MUST stay disjoint from "
        "the short-line strong-hold predicate", (8.0, 20.0, 2.0)),
}


def get(name: str) -> Any:
    return REGISTRY[name].value


def as_dict() -> dict[str, Any]:
    return {k: p.value for k, p in REGISTRY.items()}


# Convenience module-level constants for direct import by consumers, so the
# registry is the authoritative definition site (not just documentation).
SUPER_JW = REGISTRY["SUPER_JW"].value
STRONG_JW = REGISTRY["STRONG_JW"].value
QUALIFIED_JW = REGISTRY["QUALIFIED_JW"].value
DIRECTION_DISCOUNT = REGISTRY["DIRECTION_DISCOUNT"].value
RAW_QIBAO_RANK_TOP_N = REGISTRY["RAW_QIBAO_RANK_TOP_N"].value
RAW_QIBAO_OPEN_PCT_CAP = REGISTRY["RAW_QIBAO_OPEN_PCT_CAP"].value
RAW_QIBAO_HIGH_OPEN_PCT_CAP = REGISTRY["RAW_QIBAO_HIGH_OPEN_PCT_CAP"].value
PRIMARY_THRESHOLD = REGISTRY["PRIMARY_THRESHOLD"].value
PROFILE_DD = REGISTRY["PROFILE_DD"].value
PROFILE_HARD_DD = REGISTRY["PROFILE_HARD_DD"].value
DEPLOY_RATIO = REGISTRY["DEPLOY_RATIO"].value
MAX_TOTAL_EXPOSURE_RATIO = REGISTRY["MAX_TOTAL_EXPOSURE_RATIO"].value
FEE_RATE = REGISTRY["FEE_RATE"].value

TREND_BUDGET_RATIO = BOOK_T_PROPOSED["TREND_BUDGET_RATIO"].value
TREND_LOOKBACK_L = BOOK_T_PROPOSED["TREND_LOOKBACK_L"].value
TREND_REBALANCE_R = BOOK_T_PROPOSED["TREND_REBALANCE_R"].value
TREND_TOP_M = BOOK_T_PROPOSED["TREND_TOP_M"].value
TREND_TRAIL_DD = BOOK_T_PROPOSED["TREND_TRAIL_DD"].value
