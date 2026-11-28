from datetime import timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_entry_clock as runner
from xiaocao.research.entry_clock import COSTS, cash_effect, new_accounts, settle


DAY = "2026-11-30"
NEXT = "2026-12-01"
CODE = "600519.XSHG"


class Clock:
    def __init__(self, day, minute):
        self.value = runner.at(day, minute)

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += timedelta(seconds=seconds)


class Quotes:
    def __init__(self, missing=()):
        self.missing = missing

    def minute_line(self, code, trade_date, count):
        return [
            dict(
                code=code, tradeDate=trade_date, tradeTime=t, trade=price, vol=1_000_000
            )
            for t, price in (
                ("0931", 10.15),
                ("0945", 10.05),
                ("0946", 10.00),
                ("1500", 10.50),
            )
            if t not in self.missing
        ]

    def second_line_detail_info(self, code):
        return {
            code: dict(
                code=code,
                tradeStatus="T",
                tradeDate="20261201",
                tradeTimestamp="15:01:57:000",
                downPrice=9,
                buyVol1=10000,
            )
        }


def exercise(family, missing=(), start="0929"):
    state = dict(activated_at=DAY + "T09:17:00+08:00", accounts=new_accounts(), days={})
    quote = Quotes(missing)
    clock = Clock(DAY, start)
    row = dict(
        code=CODE,
        mode="test",
        mode_state="ACTIVE",
        open=10,
        up_price=11,
        down_price=9,
        basket_price=10.4,
        mode_exec_rank=1,
    )
    universe = {"selected": [], "cold": [], "frozen_count": 1}
    universe[family] = [row]
    runner.morning(
        state,
        DAY,
        "2026-11-27",
        quote,
        lambda: None,
        clock.now,
        clock.sleep,
        lambda *_: {"universe": universe},
    )
    return state, quote, clock


def test_original_pair_two_independent_accounts_and_t1():
    state, q, clock = exercise("selected")
    a = state["accounts"]
    early = a["selected_0931/normal"]
    late = a["selected_0946/normal"]
    assert early["lots"][0]["shares"] == late["lots"][0]["shares"]
    assert early["cash"] < late["cash"] and a["cash/normal"]["cash"] == 10_000_000
    runner.morning(state, DAY, "2026-11-27", q, lambda: None, clock.now, clock.sleep)
    assert early["buys"] == 1
    for day in (DAY, NEXT, NEXT):
        clock = Clock(day, "1517")
        runner.eod(state, day, q, lambda: None, clock.now, clock.sleep)
        if day == DAY:
            assert early["lots"] and early["realized"] == 0
    assert not early["lots"] and 0 < early["realized"] < late["realized"]
    assert early["cash"] == 10_000_000 + early["realized"]
    assert runner.report(state)["mature_opportunity_days"]["selected"]["dates"] == [DAY]


def test_cold_breadth_uses_separate_minute_and_complete_universe():
    good, _, _ = exercise("cold")
    p = good["days"][DAY]["phases"]
    assert (
        p["0945"]["decision"]["qualifies"]
        and not p["0931"]["effects"]["selected_0931/normal"]
    )
    assert p["0946"]["effects"]["cold_0946/normal"][0]["price"] == 10.01
    gap, _, _ = exercise("cold", ("0945",))
    assert gap["days"][DAY]["phases"]["0945"]["status"] == "gap"
    assert gap["accounts"]["cold_0946/normal"]["buys"] == 0


def test_late_original_cannot_admit_single_side_of_pair():
    state, _, _ = exercise("selected", start="0932")
    assert state["days"][DAY]["phases"]["0931"]["status"] == "gap"
    assert state["accounts"]["selected_0946/normal"]["buys"] == 0
    cold, _, _ = exercise("cold", start="0932")
    assert cold["accounts"]["cold_0946/normal"]["buys"] == 1


def test_partial_exit_and_missing_price_keep_cost_basis():
    state, _, _ = exercise("cold")
    a = state["accounts"]["cold_0946/normal"]
    lot = a["lots"][0].copy()
    guard = {CODE: {"down": 9, "bid_shares": 0}}
    settle(a, NEXT, {CODE: {"trade": 9, "vol": 90000}}, guard, COSTS["normal"])
    assert a["lots"] == [lot]
    settle(a, NEXT, {}, guard, COSTS["normal"])
    assert a["nav"] is None and a["lots"] == [lot]
    day = "2026-12-02"
    effect = settle(
        a, day, {CODE: {"trade": 10.52, "vol": 15000}}, guard, COSTS["normal"]
    )[0]
    assert (
        effect["shares"] == 100
        and a["lots"][0]["basis"] + effect["basis"] == lot["basis"]
    )
    assert a["realized"] == cash_effect(100, 10.52, False)[0] - effect["basis"]


def test_unknown_price_invalidates_only_the_affected_comparison():
    state, q, clock = exercise("selected", ("0931",))
    for day in (DAY, NEXT):
        clock = Clock(day, "1517")
        runner.eod(state, day, q, lambda: None, clock.now, clock.sleep)
    result = runner.report(state)
    assert result["returns_at_last_mark"]["normal"]["0946_less_0931_yuan"] is None
    assert result["mature_opportunity_days"]["selected"]["days"] == 0
    assert result["first_unpriced_path_event"]["selected_0931/normal"] == [DAY, "0931"]


def test_missing_0945_does_not_measure_cold_cash_as_a_tie():
    state, _, _ = exercise("cold", ("0945",))
    r = runner.report(state)
    assert r["returns_at_last_mark"]["normal"]["cold_less_cash_yuan"] is None
    assert r["returns_at_last_mark"]["normal"]["0946_less_0931_yuan"] == 0


def test_late_batch_cannot_apply_timely_partial_point():
    state = dict(activated_at=DAY, accounts=new_accounts(), days={})
    clock = Clock(DAY, "0929")
    rows = [
        dict(
            code=c,
            mode=m,
            mode_state="ACTIVE",
            open=10,
            up_price=11,
            down_price=9,
            basket_price=10.4,
            mode_exec_rank=i,
        )
        for i, (c, m) in enumerate(((CODE, "a"), ("000001.XSHE", "b")), 1)
    ]

    class Partial(Quotes):
        def minute_line(self, code, trade_date, count):
            return (
                []
                if code == "000001.XSHE"
                else super().minute_line(code, trade_date, count)
            )

    runner.morning(
        state,
        DAY,
        "2026-11-27",
        Partial(),
        lambda: None,
        clock.now,
        clock.sleep,
        lambda *_: {"universe": {"selected": rows, "cold": [], "frozen_count": 2}},
    )
    event = state["days"][DAY]["phases"]["0931"]
    assert (
        CODE in event["points"] and event["gaps"][CODE] == "batch_closed_after_deadline"
    )
    assert state["accounts"]["selected_0931/normal"]["buys"] == 0


def test_missing_whole_session_does_not_advance_mark():
    state, q, _ = exercise("cold")
    clock = Clock(DAY, "1517")
    runner.eod(state, DAY, q, lambda: None, clock.now, clock.sleep)
    state["days"][NEXT] = {
        "phases": {
            x: {"status": "gap", "reason": "missed"} for x in (*runner.PHASES, "1500")
        }
    }
    report = runner.report(state)
    assert report["last_marked_date"] == DAY
    assert report["returns_at_last_mark"]["normal"]["cold_less_cash_yuan"] is None
