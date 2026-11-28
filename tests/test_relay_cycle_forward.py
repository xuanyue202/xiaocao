import copy
import datetime as dt
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_relay_cycle as run
import research_entry_clock as clock_runner
import research_forward_review as reports
from xiaocao.research.entry_clock import new_accounts
from xiaocao.research.pool_observation import encoded
from xiaocao.research.relay_cycle import INDEX, cohorts, initial
from xiaocao.research.weekly_evidence import observe_entry_cycle

DAY = "2026-11-30"
NEXT = "2026-12-01"
PREV = "2026-11-27"
TARGET, LOW, HIGH = "000889.XSHE", "002815.XSHE", "603960.XSHG"


class Clock:
    def __init__(self, day, minute):
        self.value = run.at(day, minute)

    def now(self):
        return self.value

    def sleep(self, n):
        self.value += dt.timedelta(seconds=n)


class Quotes:
    def __init__(self, clock):
        self.clock = clock

    def minute_line(self, code, trade_date, count, code_type=0):
        assert code != INDEX or code_type == 1
        change = {INDEX: -0.03, LOW: 0.02, HIGH: -0.02, TARGET: 0.01}[code]
        return [
            {
                "code": code,
                "tradeDate": trade_date,
                "tradeTime": m,
                "trade": p,
                "vol": 1_000_000,
            }
            for m, p in [
                ("0930", 10),
                ("0943", 10 * (1 + change)),
                ("0946", 10.05),
                ("1500", 11.5),
            ]
        ]

    def second_line_detail_info(self, c):
        t = self.clock.now()
        return {
            c: dict(
                code=c,
                tradeDate=t.strftime("%Y%m%d"),
                tradeTimestamp=t.strftime("%H:%M:%S") if t.hour < 15 else "15:00:00",
                tradeStatus="T",
                downPrice=9,
                upPrice=12,
                trade=10.05,
                buyVol1=500000,
            )
        }


def original(*_):
    return {
        "checkpoint": "abc",
        "universe": {"frozen_count": 1, "frozen_state_counts": {"COLD": 1}},
    }


def receipt(book):
    d = book / "pool_observations" / DAY
    d.mkdir(parents=True)
    ordered = [TARGET, LOW, HIGH]
    record = {
        "day": DAY,
        "slot": "0932",
        "opening": {"checkpoint_sha256": "abc"},
        "current": {
            g: {
                "group": g,
                "requested_day": DAY,
                "status": "observed",
                "codes": ordered,
            }
            for g in ("jieli", "dixi", "qibao")
        },
        "relay_ranking": {
            "requested_day": DAY,
            "sort_id": 37,
            "status": "observed",
            "ordered_codes": ordered,
            "reads": [
                {
                    "kind": k,
                    "started_at": run.at(DAY, "0932").isoformat(),
                    "completed_at": run.at(DAY, "0932").isoformat(),
                }
                for k in ("sort:37", "stock_index")
            ],
            "stocks": [
                {
                    "code": c,
                    "xcjw": 310 if i != 1 else 220,
                    "jsjl": 20 - i,
                    "isPreSt": 0,
                    "ylimitupdays": 1 if i < 2 else 3,
                }
                for i, c in enumerate(ordered)
            ],
        },
    }
    record["receipt_sha256"] = run.sha(encoded(record))
    f = d / "0932.json"
    f.write_bytes(encoded(record))
    return record


def test_rotation_trade_separate_from_index_and_cash_finishes_at_t1_once(tmp_path):
    receipt(tmp_path)
    state = initial(run.at(PREV, "1517").isoformat())
    clock = Clock(DAY, "0917")
    q = Quotes(clock)

    def morning():
        run.morning(
            state,
            DAY,
            PREV,
            tmp_path,
            q,
            original,
            lambda: None,
            clock.now,
            clock.sleep,
        )

    morning()
    morning()
    decision = state["days"][DAY]["decision"]
    assert decision["low"] == [LOW] and decision["high"] == [HIGH]
    assert decision["factors"]["gates"] == {
        "rank": True,
        "cash": False,
        "index": False,
        "rotation": True,
    }
    for d in (DAY, NEXT, NEXT):
        clock.value = run.at(d, "1517")
        if d == NEXT:
            state["days"].setdefault(
                d,
                {
                    "decision": {"status": "slot_occupied"},
                    "entry": {"status": "skipped"},
                },
            )
        run.closing(state, d, q, lambda: None, clock.now, clock.sleep)
        if d == DAY:
            assert (
                "paired_pnl" not in state["days"][DAY]
                and state["accounts"]["rotation/normal"]["lots"]
            )
    v = state["days"][DAY]["paired_pnl"]
    assert v["cash/normal"] == v["index/normal"] == 0
    assert 0 < v["rotation/stress"] < v["rotation/normal"] == v["rank/normal"]
    assert (
        state["accounts"]["rotation/normal"]["cash"]
        == 10_000_000 + v["rotation/normal"]
    )
    assert state["accounts"]["rotation/normal"]["buys"] == 1


def test_missing_original_or_late_observation_never_backfills(tmp_path):
    rec = receipt(tmp_path)
    rank = rec["relay_ranking"]
    rank["stocks"][1].pop("ylimitupdays")
    assert cohorts(rank)["status"] == "gap"
    state = initial(run.at(PREV, "1517").isoformat())
    clock = Clock(DAY, "0947")
    run.morning(
        state,
        DAY,
        PREV,
        tmp_path,
        Quotes(clock),
        original,
        lambda: None,
        clock.now,
        clock.sleep,
    )
    assert state["days"][DAY]["entry"]["status"] == "gap"
    assert all(not a["lots"] for a in state["accounts"].values())
    assert (
        run.relay_plan(tmp_path, DAY, PREV, {"checkpoint": "other"})["status"] == "gap"
    )


def test_fixed_promotion_packet_is_guarded_immutable_and_weekly_bound(tmp_path):
    book = tmp_path / "output/research/entry_clock_forward"
    state = initial("2026-01-01T09:17:00+08:00")
    old = {
        "activated_at": state["activated_at"],
        "accounts": new_accounts(),
        "days": {},
    }
    report = clock_runner.report(old)
    capital = 10_000_000
    for i in range(40):
        day = (dt.date(2026, 1, 2) + dt.timedelta(days=i)).isoformat()
        rotate = i % 2 == 0
        gates = {"rotation": rotate, "cash": False, "index": not rotate, "rank": True}
        effects = {}
        pnl = {}
        nav = {}
        fills = {}
        for n, a in state["accounts"].items():
            bought = gates[n.split("/")[0]] and i != 17
            effects[n] = [{"status": "model_buy", "basis": 100000}] if bought else []
            fills[n] = 100 if bought else 0
            pnl[n] = (500 + i if rotate else -600 - i) if bought else 0
            a["nav"] += pnl[n]
            a["cash"] = a["nav"]
            a["buys"] += int(bought)
            nav[n] = a["nav"]
        state["days"][day] = {
            "decision": {
                "status": "ready",
                "candidate": TARGET,
                "factors": {"gates": gates},
            },
            "entry": {"status": "observed", "fills": fills, "effects": effects},
            "close": {"gaps": {}, "nav": nav},
            "paired_pnl": pnl,
        }
    result = reports.publish_review(book, day, old, report, state, publish=True)
    item = result["studies"]["relay"]
    assert (
        item["stage"] == "app_pilot_review_due"
        and item["fixed_decision"]["blockers"] == []
    )
    assert all(
        r["status"] == "PASS" for r in item["fixed_decision"]["manifests"].values()
    )
    assert reports.publish_review(book, day, old, report, state, publish=True) == result
    run.store(
        book / "registration.json",
        {"protocol": state["protocol"], "activated_at": state["activated_at"]},
    )
    content = {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in (tmp_path / "output").rglob("*.json*")
    }
    assert (
        observe_entry_cycle(content, dt.date.fromisoformat(day))["status"] == "observed"
    )
    assert (
        observe_entry_cycle(content, dt.date(2025, 12, 31))["status"] == "not_observed"
    )
    from xiaocao.research.weekly_evidence import _capture

    end = dt.date.fromisoformat(day)
    manifest, captured = _capture(tmp_path, tmp_path / "fixed_snapshot", end)
    assert (
        observe_entry_cycle(captured, end)["studies"]["relay"]["weekly_action"]
        == "app_pilot_review_due"
    )
    later_day = end + dt.timedelta(days=1)
    assert later_day.weekday() < 5
    assert (
        observe_entry_cycle(captured, later_day)["studies"]["relay"]["weekly_action"]
        == "reconcile_missing_current_session"
    )
    captured[
        "output/research/entry_clock_forward/closed_sessions/"
        + later_day.isoformat()
        + ".json"
    ] = run.encode(
        dict(
            day=later_day.isoformat(),
            exchange="SSE",
            last_open=day,
            closed_rows=[dict(isOpen=0, calDate=later_day.strftime("%Y%m%d"))],
        )
    )
    assert observe_entry_cycle(captured, later_day)["through_review_date"]
    digest_path = next(path for path in captured if path.endswith("/trades.jsonl"))
    captured[digest_path] += b" "
    assert observe_entry_cycle(captured, end)["status"] == "invalid"
    content[
        "output/research/entry_clock_forward/evidence/"
        + result["source_hashes"]["cycle"]
        + ".json"
    ] = b"{}"
    assert (
        observe_entry_cycle(content, dt.date.fromisoformat(day))["status"] == "invalid"
    )

    assert item["comparisons"]["stress/rank"]["opportunity_days"] == 40
    assert item["comparisons"]["stress/rank"]["funded_days"] == 39
    frozen = (book / "milestones/relay-40.json").read_bytes()
    before = reports.publish_review(book, day, old, report, state)["studies"]["relay"]
    assert before["stage"] == "app_pilot_review_due"
    end = dt.date.fromisoformat(day)
    for i in range(1, 21):
        day = (end + dt.timedelta(days=i)).isoformat()
        # Reversing the cash-flow sign after the fixed sample must change the current review.

        bad = copy.deepcopy(state["days"]["2026-01-02"])
        bad["paired_pnl"].update({"rotation/normal": -3000, "rotation/stress": -3000})
        state["days"][day] = bad
    later = reports.publish_review(book, day, old, report, state, publish=True)[
        "studies"
    ]["relay"]
    assert later["stage"] == "pause_pilot_review"
    assert later["recent_20"]["stress/cash"]["net_yuan"] == -600
    assert (
        later["subsequent_days"] == 20
        and later["fixed_decision"] == item["fixed_decision"]
    )
    assert frozen == (book / "milestones/relay-40.json").read_bytes()


def test_distinguish_flat_and_funded_missing_mark():
    state = initial("2026-10-01T16:00:00+08:00")
    gap = {"close": {"gaps": {"session": "scheduled_close_missing"}}}
    state["days"][DAY] = gap
    assert run.review(state)["gaps"] == [DAY] and run.review(state)["funded_gaps"] == []
    state["days"][PREV] = {"entry": {"fills": {"rank/stress": 100}}}
    assert run.review(state)["funded_gaps"] == [DAY]


def test_legacy_exit_links_only_to_unique_funded_prior_lot():
    name = "selected_0931/normal"

    def entry():
        return {
            "phases": {
                "0931": {
                    "effects": {
                        name: [
                            {
                                "status": "model_buy",
                                "code": TARGET,
                                "basis": 10000,
                                "shares": 100,
                            }
                        ]
                    }
                }
            }
        }

    def exit_day():
        return {
            "phases": {
                "1500": {
                    "effects": {
                        name: [
                            {
                                "status": "model_sell",
                                "code": TARGET,
                                "pnl": 300,
                                "shares": 100,
                            }
                        ]
                    }
                }
            }
        }

    days = {DAY: entry(), NEXT: exit_day()}
    lots, gaps = reports.clock_lots({"days": days})
    assert not gaps and lots[DAY, name, TARGET]["pnl"] == 300
    days[PREV] = entry()
    assert reports.clock_lots({"days": days})[1] == {name}


def test_weekly_owner_records_disposition_only_for_current_pass():
    from weekly_deep_review import _entry_cycle_responses

    plan = {
        "data_evidence_review": {
            "entry_cycle_review": {
                "status": "observed",
                "sha256": "abc",
                "studies": {"relay": {"weekly_action": "interim_review"}},
            }
        }
    }
    with pytest.raises(SystemExit, match="needs disposition"):
        _entry_cycle_responses(plan)
    item = {
        "source_sha256": "abc",
        "disposition": "refer_bounded_pilot",
        "reason": "checked",
        "owner": "weekly",
        "next_review": NEXT,
    }
    plan["entry_cycle_responses"] = {"relay": item}
    with pytest.raises(SystemExit, match="not current"):
        _entry_cycle_responses(plan)
    plan["data_evidence_review"]["entry_cycle_review"]["studies"]["relay"]["weekly_action"] = "collecting"
    with pytest.raises(SystemExit, match="not current"):
        _entry_cycle_responses(plan)
    item["disposition"] = "continue_shadow"
    assert _entry_cycle_responses(plan) == {"relay": item}
