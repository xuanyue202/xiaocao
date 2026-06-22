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
