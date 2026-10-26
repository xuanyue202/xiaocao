from __future__ import annotations

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kronos_screen.scripts.paper_record import _attach_fill_prices
from tests.test_paper_kol_integration import runtime, rows  # noqa: F401
from xiaocao.live.paper_entry_cost import CONSERVATIVE_COST_BASIS, verified_first_minute_high


CODE = "000001.XSHE"
DATE = "2026-09-06"
NOW = datetime(2026, 9, 6, 10, tzinfo=ZoneInfo("Asia/Shanghai"))


def bar(**changes):
    return {"code": CODE, "tradeDate": "20260906", "tradeTime": "0931",
            "tradeMinutes": 1, "freq": "1min", "open": 10.0, "high": 10.20,
            "low": 9.98, "close": 10.05, "trade": 10.05,
            "amt": 1000.0, "vol": 100, **changes}


def validate(bars, **changes):
    args = {"code": CODE, "trade_date": DATE, "start_hhmm": "0930",
            "end_hhmm": "0931", "observed_at": NOW, **changes}
    return verified_first_minute_high(
        {"source": "xiaocao_api", "raw_minute_rows": bars}, **args)


def test_plausible_bar_keeps_evidence_but_does_not_prove_source_interval():
    first = bar()
    price, proof = validate([bar(tradeTime="0930", high=99), first, bar(tradeTime="0932", high=99)])
    assert price is None
    assert proof["raw_bar"] == first and proof["status"] == "unproven"
    assert proof["reason"] == "FIRST_MINUTE_SOURCE_INTERVAL_UNPROVEN"
    raw = json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert proof["raw_bar_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.parametrize("changes", [
    {"high": None}, {"high": 0}, {"high": True}, {"high": float("nan")},
    {"high": float("inf")}, {"low": None}, {"open": None}, {"close": None},
    {"high": 9.9}, {"low": 10.1}, {"vol": 0}, {"trade": 11.0},
    {"code": "600000.XSHG"}, {"code": None}, {"tradeDate": "20260905"},
    {"tradeTime": "0932"}, {"freq": None}, {"freq": "D"},
    {"tradeMinutes": 0}, {"tradeMinutes": True},
])
def test_missing_or_wrong_raw_evidence_never_becomes_a_cost(changes):
    price, proof = validate([bar(**changes)])
    assert price is None and proof["status"] == "unproven"
    json.dumps(proof, allow_nan=False)


def test_duplicate_future_and_custom_window_are_not_first_minute_proof():
    assert validate([bar(), bar()])[0] is None
    assert validate([bar()], observed_at=NOW.replace(hour=9, minute=31))[0] is None
    assert validate([bar()], end_hhmm="0932")[0] is None
    assert validate([bar()], observed_at=NOW.replace(tzinfo=None))[0] is None


class Client:
    def __init__(self, **changes):
        self.changes = changes

    def minute_line(self, code, freq, adj, *, trade_date, count):
        return [bar(code=code, **self.changes)]


@pytest.fixture
def verified_cost_input(monkeypatch):
    """Exercise cost/ledger plumbing, NOT provider acceptance or market proof."""
    from kronos_screen.scripts import paper_record

    def supplied_cost(window, **kwargs):
        _, evidence = verified_first_minute_high(window, **kwargs)
        if evidence.get("reason") != "FIRST_MINUTE_SOURCE_INTERVAL_UNPROVEN":
            return None, evidence
        return 10.20, {**evidence, "status": "verified", "source": "test_only_cost_input"}

    monkeypatch.setattr(paper_record, "verified_first_minute_high", supplied_cost)


def attach(*, conservative=True, client=None, **record_changes):
    record = {"code": CODE, "open": 10.0, "basket_price": 10.10, **record_changes}
    return _attach_fill_prices(client or Client(), [record], DATE,
                               start_hhmm="0930", end_hhmm="0931",
                               limit_premium_pct=0.5, conservative_entry=conservative)


def test_conservative_cost_is_high_even_above_limit_basket_and_vwap(verified_cost_input):
    bought, skipped = attach()
    assert not skipped
    fill = bought[0]["_paper_fill"]
    assert fill["price"] == 10.20  # HIGH > basket 10.10 > limit 10.05 > VWAP 10.00
    assert fill["basis"] == CONSERVATIVE_COST_BASIS
    assert fill["fill_cost_evidence"]["status"] == "verified"
    legacy, _ = attach(conservative=False)
    assert legacy[0]["_paper_fill"]["price"] == 10.0


def test_cost_policy_preserves_eligibility_and_never_falls_back_for_missing_high(verified_cost_input):
    bought, skipped = attach(client=Client(open=10.30, low=10.30, high=10.50, close=10.40, trade=10.40))
    assert not bought and skipped[0]["_paper_fill"]["skip_reason"] == "LIMIT_NOT_REACHED"
    bought, skipped = attach(client=Client(high=None))
    assert not bought and skipped[0]["_paper_fill"]["skip_reason"] == "FIRST_MINUTE_HIGH_UNPROVEN"


def test_real_paper_writer_pairs_cost_evidence_and_preserves_exact_once(runtime, monkeypatch, verified_cost_input):
    root, live, pr, run = runtime
    monkeypatch.setattr(pr, "_attach_fill_prices", _attach_fill_prices)
    monkeypatch.setattr(pr, "XiaocaoClient", Client)
    positions, claim, terminal = run()
    assert terminal["buy_count"] == 3
    assert {r["book"] for r in positions} == {"A", "B"}
    assert all(r["entry_price"] == 10.20 and r["entry_price_basis"] == CONSERVATIVE_COST_BASIS
               and r["fill_cost_evidence"]["status"] == "verified" for r in positions)
    a, b = [[r for r in positions if r["book"] == book] for book in ("A", "B")]
    assert [(r["code"], r["shares"], r["entry_cash_out"]) for r in a] == [
        (r["code"], r["shares"], r["entry_cash_out"]) for r in b]
    assert sum(r["entry_cash_out"] for r in b) <= 50000
    trades = rows(live / "paper_trades.jsonl")
    assert all(r["price"] == 10.20 and r["fill_cost_evidence"]["raw_bar_sha256"] for r in trades)
    tracked = [live / n for n in ("positions.jsonl", "paper_trades.jsonl", "paper_account.json", "paper_account_A.json")]
    before = [p.read_bytes() for p in tracked]
    run()
    assert [p.read_bytes() for p in tracked] == before


def test_unverified_source_cannot_be_enabled_by_plausible_fields():
    bought, skipped = attach()
    assert not bought
    assert skipped[0]["_paper_fill"]["skip_detail"] == "FIRST_MINUTE_SOURCE_INTERVAL_UNPROVEN"
    bought, skipped = attach(client=Client(open=10.30, low=10.30, high=10.50, close=10.40, trade=10.40))
    assert not bought
    assert skipped[0]["_paper_fill"]["fill_eligibility_rejection"]["reason"] == "LIMIT_NOT_REACHED"


@pytest.mark.parametrize("source_changes,eligibility_reason", [
    ({"high": None}, None),
    ({"open": 10.30, "low": 10.30, "high": 10.50, "close": 10.40, "trade": 10.40},
     "LIMIT_NOT_REACHED"),
])
def test_real_paper_writer_reports_missing_high_without_ledger_mutation(
    runtime, monkeypatch, source_changes, eligibility_reason,
):
    root, live, pr, run = runtime
    monkeypatch.setattr(pr, "_attach_fill_prices", _attach_fill_prices)
    monkeypatch.setattr(pr, "XiaocaoClient", lambda: Client(**source_changes))
    before = (live / "paper_account.json").read_bytes()
    positions, claim, terminal = run()
    assert positions == [] and terminal["buy_count"] == 0
    assert (live / "paper_account.json").read_bytes() == before
    assert not (live / "paper_account_A.json").exists()
    skips = rows(live / "paper_skips.jsonl")
    assert skips and all(r["reason"] == "FIRST_MINUTE_HIGH_UNPROVEN"
                         and r["fill_cost_evidence"]["raw_bar_sha256"] for r in skips)
    if eligibility_reason:
        assert all(r["fill_eligibility_rejection"] == {
            "reason": eligibility_reason, "detail": "REALTIME_ABOVE_BASKET",
        } for r in skips)
