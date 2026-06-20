"""Tests for the knowledge ledger (src/xiaocao/research/ledger.py)."""
from __future__ import annotations

from xiaocao.research import guards, ledger


def _verdict(spread_positive=True):
    trades = []
    for i in range(10):
        s = 0.01 if spread_positive else -0.01
        trades.append({"day": f"2026-05-{i + 1:02d}", "strat_ret": s, "base_ret": 0.0})
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
