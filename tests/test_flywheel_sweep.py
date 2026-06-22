"""Tests for the flywheel sweep (scripts/flywheel_sweep.py): it ranks the untested
backlog by test-priority and surfaces PASS — it must EXCLUDE tested/retired, rank by
recurrence then age, and NEVER mutate the spine."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("flywheel_sweep", ROOT / "scripts" / "flywheel_sweep.py")
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)


def test_rank_queue_excludes_tested_and_retired_ranks_by_recurrence_then_age():
    entries = [
        {"id": "XH-A", "source_dates": ["2026-06-01", "2026-06-10", "2026-06-15"],  # rec 3
         "status": "candidate", "operationalization": "用 cache 的 date_kline 做配对检验"},
        {"id": "XH-B", "source_dates": ["2026-06-02"], "status": "candidate",         # rec 1, cache
         "operationalization": "走 research_run.py walk-forward"},
        {"id": "XH-C", "source_dates": ["2026-06-01"], "status": "candidate",         # rec 1, no cache, older
         "operationalization": "看小草怎么说"},
        {"id": "XH-D", "source_dates": ["2026-06-03"], "status": "tested:REJECTED"},   # excluded
        {"id": "XH-E", "source_dates": ["2026-06-03"], "retired_on": "2026-06-20",     # excluded
         "status": "candidate"},
    ]
    q = sw.rank_queue(entries, today=date(2026, 6, 25))
    ids = [r["id"] for r in q]
    assert ids == ["XH-A", "XH-B", "XH-C"]                  # tested + retired excluded
    assert q[0]["recurrence"] == 3 and q[0]["rank"] == 1    # highest recurrence first
    # same recurrence (B,C): cache-expressible B floats above non-cache C
    assert ids.index("XH-B") < ids.index("XH-C")
    assert q[0]["age_days"] == 24                            # 2026-06-01 -> 06-25


def test_cache_expressible_detects_runnable_ops():
    assert sw._cache_expressible({"operationalization": "用 cache date_kline 逐笔配对"}) is True
    assert sw._cache_expressible({"operationalization": "走 research_exit_priors.py"}) is True
    assert sw._cache_expressible({"operationalization": "等小草下次直播确认"}) is False


def test_pass_evidence_lists_only_pass():
    entries = [{"id": "XH-1", "last_verdict": "PASS"}, {"id": "XH-2", "last_verdict": "REJECTED"},
               {"id": "XH-3"}]
    assert sw.pass_evidence(entries) == ["XH-1"]
