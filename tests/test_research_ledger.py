"""Tests for the knowledge ledger (src/xiaocao/research/ledger.py)."""
from __future__ import annotations

from xiaocao.research import guards, ledger, trend_guards


def _verdict(spread_positive=True):
    # A genuine PASS needs real day-to-day variance (a perfectly constant edge is
    # now — correctly — not significant). Jitter the positive case; make the
    # negative case clearly losing.
    trades = []
    for i in range(12):
        if spread_positive:
            strat, base = 0.01 + 0.001 * ((i % 3) - 1), 0.0
        else:
            strat, base = 0.005, 0.02
        trades.append({"day": f"2026-05-{i + 1:02d}", "strat_ret": strat, "base_ret": base})
    return guards.evaluate_hypothesis(trades, n_tried=1)


def test_record_and_read(tmp_path):
    path = tmp_path / "HYPOTHESES.jsonl"
    e = ledger.record_hypothesis(
        hypothesis_id="kp50_top3", claim="K50->P top3 beats take-all",
        method="walk-forward OOS", verdict=_verdict(True), n_tried=6, path=path,
    )
    assert e["id"] == "kp50_top3" and e["verdict"] in {"PASS", "REJECTED"}
    assert e["metrics"]["per_trade_spread"] is not None
    rows = ledger.read_all(path)
    assert len(rows) == 1 and rows[0]["n_tried"] == 6


def test_already_refuted_uses_latest_entry(tmp_path):
    path = tmp_path / "HYPOTHESES.jsonl"
    # First a rejection, then a later PASS that supersedes it.
    ledger.record_hypothesis(hypothesis_id="h", claim="c", method="m",
                             verdict=_verdict(False), path=path)
    assert ledger.already_refuted("h", path=path) is True
    ledger.record_hypothesis(hypothesis_id="h", claim="c", method="m2",
                             verdict=_verdict(True), supersedes="h", path=path)
    assert ledger.already_refuted("h", path=path) is False
    assert ledger.already_refuted("never_tried", path=path) is False


def test_record_never_raises_on_unwritable_path(tmp_path):
    blocker = tmp_path / "blk"
    blocker.write_text("x", encoding="utf-8")
    e = ledger.record_hypothesis(hypothesis_id="h", claim="c", method="m",
                                 verdict=_verdict(True), path=blocker / "nested.jsonl")
    assert e["id"] == "h"


def test_record_trend_verdict_metrics(tmp_path):
    path = tmp_path / "HYPOTHESES.jsonl"
    holds = []
    regimes = ["trend_strong", "bear", "trend_continuing", "divergence", "trend_strong",
               "bear", "trend_strong", "neutral", "trend_strong", "divergence"]
    for i, diff in enumerate([1.5, 0.6, 1.2, 0.8, 1.0, 1.3, 0.7, 1.1, 0.9, 1.4]):
        holds.append({
            "entry": f"2026-05-{i + 1:02d}",
            "strat_ret": 1.0 + diff,
            "base_ret": 1.0,
            "regime": regimes[i],
            "turnover": 0.3,
        })
    verdict = trend_guards.evaluate_trend(holds, n_tried=1)
    e = ledger.record_hypothesis(
        hypothesis_id="T_trend_L60_R20_M3",
        claim="trend book beats beta",
        method="trend_guards compounded/dd/turnover",
        verdict=verdict,
        n_tried=1,
        path=path,
    )
    assert e["metrics"]["n_holds"] == len(holds)
    assert e["metrics"]["compounded_alpha"] > 0
    assert e["metrics"]["turnover"] == 0.3
