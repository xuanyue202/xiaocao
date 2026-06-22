"""End-to-end regression test: the whole compounding flywheel turns.

Proves both loops flow through their full chain on fixtures (no network), so a
future change that silently breaks the loop fails here:

  capital:    fixtures -> flywheel self-check spinning -> status digest (A/B) ->
              data-health clean -> decision-journal continuity
  capability: training_rows -> per-trade build -> discipline guards -> ledger ->
              already_refuted memory
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")  # integration fixture writes parquet; skip (not error) if absent

from xiaocao.live import data_health, flywheel, journal, status  # noqa: E402
from xiaocao.research import guards, ledger  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import continuous_optimize as co  # noqa: E402


def _seed_repo(root: Path) -> Path:
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "auto_daily.sh").write_text(
        "case $STEP in\nmorning)\n ;;\neod)\n ;;\noptimize)\n ;;\nesac\n", encoding="utf-8")
    live = root / "output" / "live"
    live.mkdir(parents=True)
    # capital state: a closed book-B trade reconciling to the account, + book A
    (live / "paper_account.json").write_text(json.dumps({"cash": 62000.0, "realized_pnl": -150.0}), encoding="utf-8")
    (live / "paper_account_A.json").write_text(json.dumps({"cash": 56500.0, "realized_pnl": 410.0}), encoding="utf-8")
    (live / "positions.jsonl").write_text(
        json.dumps({"book": "B", "status": "closed", "code": "A", "realized_pnl": -150.0}) + "\n", encoding="utf-8")
    (live / "paper_holdings.json").write_text(json.dumps({
        "date": "2026-06-19", "cash": 62000.0, "total_equity_after_exit_fee": 95000.0,
        "unrealized_pnl_after_fee": 0.0, "open_positions": 0, "holdings": [],
    }), encoding="utf-8")
    (live / "signal_snapshots.jsonl").write_text(
        json.dumps({"date": "2026-06-19", "code": "A", "is_live": True, "captured_at": "t1"}) + "\n", encoding="utf-8")
    journal.append_decision(automation="live_monitor", market_date="2026-06-19",
                            deterministic={"open_positions": 0, "positions": []},
                            posture={"regime": "neutral"}, path=live / "decision_journal.jsonl")
    (root / "kronos_screen").mkdir(parents=True)
    return root


def test_capital_flywheel_chain(tmp_path):
    root = _seed_repo(tmp_path)
    # 1) self-check sees it wired & spinning, paper-only
    fw = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert fw["spinning"] is True and fw["capital_flywheel"]["safety_paper_only"] is True
    # 2) digest surfaces the book A/B spread
    d = status.build_digest(live_dir=root / "output" / "live", market_date="2026-06-19")
    assert d["ab_realized_delta"] == round(-150.0 - 410.0, 2)
    # 3) dirty-data doctor is clean on clean fixtures
    assert data_health.check(root / "output" / "live")["ok"] is True
    # 4) continuity: the journal records the run
    assert journal.latest(market_date="2026-06-19", path=root / "output" / "live" / "decision_journal.jsonl") is not None


def test_capability_flywheel_chain(tmp_path):
    root = _seed_repo(tmp_path)
    ledger_path = root / "kronos_screen" / "HYPOTHESES.jsonl"
    # training_rows -> per-trade results -> guards -> ledger -> memory
    rows = []
    for i in range(12):
        for _ in range(3):
            rows.append({"date": f"2026-06-{i + 1:02d}", "kp_star": True, "net_realized_ret": 0.01})
        rows.append({"date": f"2026-06-{i + 1:02d}", "kp_star": False, "net_realized_ret": 0.005})
    df = pd.DataFrame(rows)

    results = co.build_results(df, "kp_star")
    assert results and all(set(r) == {"day", "strat_ret", "base_ret"} for r in results)

    verdict = guards.evaluate_hypothesis(results, n_tried=1)
    ledger.record_hypothesis(hypothesis_id="A_kp_star", claim="c", method="m",
                             verdict=verdict, path=ledger_path)

    # the verdict is durable and queryable, and gates re-running a dead direction
    saved = ledger.read_all(ledger_path)
    assert len(saved) == 1 and saved[0]["verdict"] == verdict["verdict"]
    assert ledger.already_refuted("A_kp_star", path=ledger_path) == (verdict["verdict"] == "REJECTED")


def test_dirty_data_breaks_the_chain_loudly(tmp_path):
    # If a duplicate snapshot sneaks in, the doctor must catch it before the
    # capability flywheel learns from a faked A/B verdict.
    root = _seed_repo(tmp_path)
    live = root / "output" / "live"
    with (live / "signal_snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": "2026-06-19", "code": "A", "is_live": True, "captured_at": "t2"}) + "\n")
    report = data_health.check(live)
    assert report["ok"] is False and report["critical"] >= 1
