"""Tests for the exit-calibration sensor — the correctness-critical points:
lookahead-safety of the forward window, the open-window guard, the scoring
boundaries, messy date parsing, and the per-day last-non-null-rule collapse."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("exit_calibration", ROOT / "scripts" / "exit_calibration.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)


# --- date parsing -----------------------------------------------------------

def test_norm_date_handles_messy_shapes():
    assert ec._norm_date("2026-06-15 09:51:09:830") == "2026-06-15"
    assert ec._norm_date("2026-06-02 0957") == "2026-06-02"
    assert ec._norm_date("2026-06-02") == "2026-06-02"
    assert ec._norm_date("2026-06-22T15:12:10") == "2026-06-22"
    assert ec._norm_date("") is None
    assert ec._norm_date(None) is None
    assert ec._norm_date("garbage") is None


# --- forward_return: lookahead-safety + open-window guard --------------------

def _rows(*pairs):
    return list(pairs)


def test_forward_return_excludes_decision_day():
    # decision day 2026-06-10 has a +50% return that MUST NOT count; the forward
    # window is strictly the days AFTER it.
    rows = _rows(
        ("2026-06-09", 0.00),
        ("2026-06-10", 0.50),   # decision day — excluded
        ("2026-06-11", 0.10),
        ("2026-06-12", 0.10),
    )
    fwd = ec.forward_return(rows, "2026-06-10", horizon=2)
    # (1.10 * 1.10) - 1 = 0.21 ; the 0.50 decision-day move is absent
    assert abs(fwd - 0.21) < 1e-9


def test_forward_return_decision_day_not_in_series():
    # decision made on a day not present (e.g. a halt): use the first day strictly after.
    rows = _rows(("2026-06-09", 0.05), ("2026-06-11", 0.10), ("2026-06-12", -0.10))
    fwd = ec.forward_return(rows, "2026-06-10", horizon=2)
    assert abs(fwd - ((1.10 * 0.90) - 1.0)) < 1e-9


def test_forward_return_open_window_is_none():
    rows = _rows(("2026-06-10", 0.0), ("2026-06-11", 0.10))
    assert ec.forward_return(rows, "2026-06-10", horizon=5) is None   # only 1 fwd day


def test_forward_return_no_future_is_none():
    rows = _rows(("2026-06-09", 0.0), ("2026-06-10", 0.10))
    assert ec.forward_return(rows, "2026-06-10", horizon=1) is None   # decision is last bar


def test_forward_return_refuses_window_with_corrupt_bar():
    # a +1211% BJSE listing-day / split artifact in the window -> refuse to score, do NOT
    # compound it into a falsely-confident result.
    rows = _rows(("2026-06-10", 0.0), ("2026-06-11", 0.02), ("2026-06-12", 12.11))
    assert ec.forward_return(rows, "2026-06-10", horizon=2) is None
    # but a clean window on the same series still scores
    assert abs(ec.forward_return(rows, "2026-06-10", horizon=1) - 0.02) < 1e-9


# --- scoring boundaries -----------------------------------------------------

def test_score_call_hold():
    assert ec.score_call("hold", 0.05) is True     # rose after holding -> right
    assert ec.score_call("hold", -0.05) is False
    assert ec.score_call("hold", 0.0) is False     # flat is not a win for holding


def test_score_call_sell():
    assert ec.score_call("sell", -0.05) is True    # fell after exit -> right
    assert ec.score_call("sell", 0.0) is True      # flat: exit didn't cost
    assert ec.score_call("sell", 0.05) is False    # bounced after exit -> cut a bounce


def test_score_call_none_and_unknown():
    assert ec.score_call("sell", None) is None
    assert ec.score_call("neutral", 0.1) is None


# --- rule extraction across alert classes -----------------------------------

def test_rule_of_across_classes():
    assert ec._rule_of({"sell_reason": "HARD_STOP"}) == "HARD_STOP"
    assert ec._rule_of({"reason": "TRAILING_STOP"}) == "TRAILING_STOP"
    assert ec._rule_of({"strong_hold_reason": "NEAR_LIMIT_UP"}) == "NEAR_LIMIT_UP"
    assert ec._rule_of({"latest_price": 1.0}) is None


# --- iter_decisions: one-per-day, last non-null rule wins --------------------

def test_iter_decisions_collapses_and_keeps_last_nonnull_rule(tmp_path, monkeypatch):
    # 3 polls of the same SELL_TRIGGERED on the same day; the firing rule shows up
    # only on the later polls (early poll has a null sell_reason).
    rows = [
        {"ts": "2026-06-02", "alert": "SELL_TRIGGERED", "code": "000509.XSHE",
         "name": "x", "latest_price": 4.6, "sell_reason": None, "decision_phase": "morning_assessment"},
        {"ts": "2026-06-02 0957", "alert": "SELL_TRIGGERED", "code": "000509.XSHE",
         "name": "x", "latest_price": 4.84, "sell_reason": "TRAILING_STOP", "decision_phase": "eod_discipline"},
        {"ts": "2026-06-02 1000", "alert": "SELL_TRIGGERED", "code": "000509.XSHE",
         "name": "x", "latest_price": 4.82, "sell_reason": "TRAILING_STOP", "decision_phase": "eod_discipline"},
        # a SELL_BLOCKED must be ignored (not a discretionary decision)
        {"ts": "2026-06-02", "alert": "SELL_BLOCKED", "code": "000509.XSHE", "reason": "LIMIT_DOWN_NO_BID"},
        # a suppress on a different code/day
        {"ts": "2026-06-15 09:51", "alert": "SELL_SUPPRESSED_STRONG_HOLD", "code": "600703.XSHG",
         "name": "y", "strong_hold_reason": "STRONG_TREND_HOLD"},
    ]
    f = tmp_path / "alerts.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(ec, "ALERTS", f)

    decisions = list(ec.iter_decisions())
    # one SELL_TRIGGERED (collapsed) + one SUPPRESS = 2; SELL_BLOCKED dropped
    assert len(decisions) == 2
    trig = [d for d in decisions if d["alert"] == "SELL_TRIGGERED"][0]
    assert trig["action"] == "sell"
    assert trig["rule"] == "TRAILING_STOP"          # last non-null wins, not the null first poll
    assert trig["decision_phase"] == "eod_discipline"
    assert trig["book"] == "B"
    sup = [d for d in decisions if d["alert"] == "SELL_SUPPRESSED_STRONG_HOLD"][0]
    assert sup["action"] == "hold"
    assert sup["rule"] == "STRONG_TREND_HOLD"


def test_same_day_defer_then_trigger_collapses_to_one_sell(tmp_path, monkeypatch):
    # The staged-exit design defers a soft exit intraday then executes it at 14:55 the
    # SAME day. That must count as ONE sell decision, never a hold(+defer) AND a sell on
    # the same forward path (the double-count bug).
    rows = [
        {"ts": "2026-06-15 09:37", "alert": "SELL_DEFERRED", "code": "600703.XSHG",
         "name": "x", "reason": "TRAILING_STOP"},
        {"ts": "2026-06-15 14:55", "alert": "SELL_TRIGGERED", "code": "600703.XSHG",
         "name": "x", "sell_reason": "TRAILING_STOP", "decision_phase": "eod_discipline"},
    ]
    f = tmp_path / "alerts.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(ec, "ALERTS", f)
    decisions = list(ec.iter_decisions())
    assert len(decisions) == 1
    assert decisions[0]["action"] == "sell"
    assert decisions[0]["alert"] == "SELL_TRIGGERED"
    assert decisions[0]["rule"] == "TRAILING_STOP"


def test_defer_that_holds_becomes_a_hold(tmp_path, monkeypatch):
    # A defer with NO same-day trigger = we waited and did NOT sell -> a genuine HOLD
    # (the position-level "didn't sell the dip"), labeled DEFERRED_<reason>.
    rows = [
        {"ts": "2026-06-15 09:37", "alert": "SELL_DEFERRED", "code": "600703.XSHG",
         "name": "x", "reason": "TRAILING_STOP"},
    ]
    f = tmp_path / "alerts.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(ec, "ALERTS", f)
    d = list(ec.iter_decisions())
    assert len(d) == 1
    assert d[0]["action"] == "hold"
    assert d[0]["rule"] == "DEFERRED_TRAILING_STOP"


def test_suppress_then_trigger_same_day_is_a_sell(tmp_path, monkeypatch):
    # strong-hold suppressed early, but sold at 14:55 when the strict hold no longer
    # held -> realized stance is SELL.
    rows = [
        {"ts": "2026-06-18 10:00", "alert": "SELL_SUPPRESSED_STRONG_HOLD", "code": "300522.XSHE",
         "name": "z", "strong_hold_reason": "STRONG_TREND_HOLD"},
        {"ts": "2026-06-18 14:55", "alert": "SELL_TRIGGERED", "code": "300522.XSHE",
         "name": "z", "sell_reason": "EOD_DISCIPLINE_1455"},
    ]
    f = tmp_path / "alerts.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(ec, "ALERTS", f)
    d = list(ec.iter_decisions())
    assert len(d) == 1
    assert d[0]["action"] == "sell"
    assert d[0]["rule"] == "EOD_DISCIPLINE_1455"


def test_iter_decisions_dedups_across_days(tmp_path, monkeypatch):
    rows = [
        {"ts": "2026-06-02", "alert": "SELL_DEFERRED", "code": "A.XSHG", "reason": "TRAILING_STOP"},
        {"ts": "2026-06-03", "alert": "SELL_DEFERRED", "code": "A.XSHG", "reason": "TRAILING_STOP"},
    ]
    f = tmp_path / "alerts.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(ec, "ALERTS", f)
    decisions = list(ec.iter_decisions())
    assert len(decisions) == 2   # same code, different days = two decisions
    assert {d["date"] for d in decisions} == {"2026-06-02", "2026-06-03"}
