"""Tests for the calibration loops as a MONITORED leg of the capability flywheel
(src/xiaocao/live/flywheel.py): wiring + liveness surface as WARNINGS, never a gate.
Self-contained fixture (no parquet) so it runs without pandas."""
from __future__ import annotations

import json

from xiaocao.live import flywheel

WIRED_EOD = """case $STEP in
morning)
  ;;
eod)
  python scripts/posture_calibration.py --score
  python scripts/posture_calibration.py --distill
  python scripts/exit_calibration.py --ingest --score --distill
  ;;
optimize)
  ;;
esac
"""

UNWIRED_EOD = """case $STEP in
morning)
  ;;
eod)
  ;;
optimize)
  ;;
esac
"""


def _root(tmp_path, *, auto_daily=WIRED_EOD, posture_date="2026-06-20", candidates=0):
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "auto_daily.sh").write_text(auto_daily, encoding="utf-8")
    live = tmp_path / "output" / "live"
    live.mkdir(parents=True, exist_ok=True)
    (live / "decision_journal.jsonl").write_text(
        json.dumps({"automation": "live_monitor", "market_date": "2026-06-20"}) + "\n", encoding="utf-8")
    (live / "paper_account.json").write_text("{}", encoding="utf-8")
    (live / "paper_account_A.json").write_text("{}", encoding="utf-8")
    if posture_date:
        (live / "posture_calls.jsonl").write_text(
            json.dumps({"date": posture_date, "posture": "neutral", "action": "neutral"}) + "\n", encoding="utf-8")
    (live / "posture_calibration.jsonl").write_text(
        json.dumps({"date": "2026-06-10", "action": "defensive", "right": True}) + "\n", encoding="utf-8")
    (live / "exit_calls.jsonl").write_text(
        json.dumps({"code": "x", "date": "2026-06-18", "action": "sell"}) + "\n", encoding="utf-8")
    (live / "exit_calibration.jsonl").write_text(
        json.dumps({"code": "x", "date": "2026-06-18", "action": "sell", "right": True}) + "\n", encoding="utf-8")
    if candidates:
        with (live / "calibration_candidates.jsonl").open("w", encoding="utf-8") as fh:
            for i in range(candidates):
                fh.write(json.dumps({"cand_key": f"k{i}"}) + "\n")
    (tmp_path / "kronos_screen").mkdir(parents=True, exist_ok=True)
    (tmp_path / "kronos_screen" / "HYPOTHESES.jsonl").write_text(
        json.dumps({"id": "x", "verdict": "REJECTED"}) + "\n", encoding="utf-8")
    return tmp_path


def test_calibration_wired_and_reported(tmp_path):
    root = _root(tmp_path, candidates=2)
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    cal = r["capability_flywheel"]["calibration"]
    assert cal["wired"] is True
    assert cal["posture_score_wired"] is True and cal["exit_score_wired"] is True
    assert cal["distill_wired"] is True
    assert cal["posture_scored"] == 1 and cal["exit_scored"] == 1
    assert cal["candidates_staged"] == 2
    assert not any("CALIBRATION" in w for w in r["warnings"])


def test_calibration_unwired_warns_but_does_not_gate(tmp_path):
    root = _root(tmp_path, auto_daily=UNWIRED_EOD)
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["capability_flywheel"]["calibration"]["wired"] is False
    assert any("CALIBRATION: not wired" in w for w in r["warnings"])
    # WARN only — the capital loop still spins (calibration is sensor-only).
    assert r["spinning"] is True


def test_calibration_liveness_warns_when_posture_stale(tmp_path):
    root = _root(tmp_path, posture_date="2026-06-01")  # >7d before today
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert any("CALIBRATION LIVENESS" in w for w in r["warnings"])
    assert r["spinning"] is True


def test_distill_unwired_warns(tmp_path):
    eod = WIRED_EOD.replace(" --distill", "")
    root = _root(tmp_path, auto_daily=eod)
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    cal = r["capability_flywheel"]["calibration"]
    assert cal["wired"] is True and cal["distill_wired"] is False
    assert any("--distill is not" in w for w in r["warnings"])


# --- knowledge scoreboard (#2): is ② getting smarter, or just heavier? ---------

def _kb_root(tmp_path, entries, ledger_rows, n_distilled):
    """Build a minimal repo tree for knowledge_scoreboard."""
    distilled = tmp_path / "reference" / "experience" / "distilled"
    distilled.mkdir(parents=True)
    for i in range(n_distilled):
        (distilled / f"2026-06-{i+1:02d}_morning.json").write_text("{}", encoding="utf-8")
    backlog = tmp_path / "reference" / "experience" / "xiaocao_hypotheses.jsonl"
    backlog.write_text("# header\n" + "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
                       encoding="utf-8")
    led = tmp_path / "kronos_screen" / "HYPOTHESES.jsonl"
    led.parent.mkdir(parents=True)
    led.write_text("\n".join(json.dumps(r) for r in ledger_rows) + "\n", encoding="utf-8")
    return tmp_path


def test_knowledge_scoreboard_counts_lifecycle(tmp_path):
    from datetime import date
    entries = [
        {"id": "XH-001", "claim": "a", "source_dates": ["2026-06-01", "2026-06-02", "2026-06-03"],
         "status": "candidate", "last_verdict": "REJECTED", "retired_on": "2026-06-20"},   # tested+retired
        {"id": "XH-002", "claim": "b", "source_dates": ["2026-06-01"], "status": "candidate"},  # untested
        {"id": "XH-003", "claim": "c", "source_dates": ["2026-06-05"], "status": "candidate"},  # untested
        {"id": "XH-004", "claim": "d", "source_dates": ["2026-06-10"], "status": "tested:PASS"},  # passed
    ]
    ledger = [{"id": "XH-004", "verdict": "PASS"}]
    root = _kb_root(tmp_path, entries, ledger, n_distilled=6)
    k = flywheel.knowledge_scoreboard(root, today=date(2026, 6, 25))

    assert k["transcripts_distilled"] == 6
    assert k["candidates_total"] == 4
    assert k["candidate_assertions"] == 6                  # 3+1+1+1 source_dates
    assert k["dedup_ratio"] == round(4 / 6, 2)             # <1 => recurrence-merge compressing
    assert k["candidates_tested"] == 2                     # XH-001 (retired/last_verdict) + XH-004 (PASS)
    assert k["candidates_passed"] == 1                     # XH-004
    assert k["candidates_retired"] == 1                    # XH-001
    assert k["candidates_untested"] == 2                   # XH-002, XH-003
    assert k["candidate_to_tested"] == 0.5
    assert k["tested_to_pass"] == 0.5
    assert k["oldest_untested"] == "2026-06-01"            # XH-002
    assert k["oldest_untested_age_days"] == 24


def test_knowledge_warning_fires_when_grading_lags(tmp_path):
    # 20 candidates, only 1 tested -> candidate_to_tested 5% -> WARN (ingest outruns grading)
    entries = ([{"id": "XH-001", "claim": "x", "source_dates": ["2026-06-01"], "status": "tested:REJECTED"}]
               + [{"id": f"XH-{i:03d}", "claim": f"c{i}", "source_dates": ["2026-06-01"], "status": "candidate"}
                  for i in range(2, 21)])
    root = _kb_root(tmp_path, entries, [], n_distilled=20)
    k = flywheel.knowledge_scoreboard(root)
    warns = flywheel._knowledge_warnings(k)
    assert any("falling behind ingest" in w for w in warns)
