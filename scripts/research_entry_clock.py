"""Observe natural sessions for the two entry-clock comparisons. No dated replay CLI."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import research_relay_cycle as relay
from research_forward_review import publish_review
from research_forward_quotes import (
    CHINA,
    at,
    close_guard,
    collect,
    now,
    save,
    wait_until,
)
from xiaocao.api.client import XiaocaoClient
from xiaocao.config import load_settings
from xiaocao.research.pool_observation import observe_session
from xiaocao.live.live_decision_support import calendar_provider
from xiaocao.live.morning_bundle import inspect_bundle, snapshot_rows
from xiaocao.research.entry_clock import (
    COSTS,
    PROTOCOL,
    breadth,
    enter,
    make_universe,
    new_accounts,
    plan_accounts,
    settle,
)

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "output/research/entry_clock_forward"
PHASES = ("0931", "0945", "0946")


def frozen(day, observed):
    bundle = inspect_bundle(ROOT / "output/live", day)
    if bundle["status"] != "ready":
        return None
    raw = Path(bundle["snapshot_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != bundle["snapshot_raw_sha256"]:
        raise ValueError("snapshot changed")
    published = datetime.fromisoformat(bundle["published_at"])
    if published.astimezone(CHINA).date().isoformat() != day or published > observed:
        raise ValueError("invalid publication date")
    rows = snapshot_rows(raw, day)
    return {
        "checkpoint": bundle["checkpoint_sha256"],
        "snapshot": bundle["snapshot_raw_sha256"],
        "published_at": bundle["published_at"],
        "universe": make_universe(rows, published),
    }


def morning(
    state, day, previous, client, persist, clock=now, sleep=time.sleep, read=frozen
):
    rec = state["days"].setdefault(day, {})
    events = rec.setdefault("phases", {})
    accounts = state["accounts"]

    def bind_before(cutoff):
        if "freeze" in rec:
            return
        while clock() < cutoff:
            evidence = read(day, clock())
            observed = clock()
            if evidence and observed < cutoff:
                rec["freeze"] = {
                    **evidence,
                    "observed_at": observed.isoformat(),
                    "plans": plan_accounts(evidence["universe"], accounts, previous),
                }
                persist()
                return
            if observed < cutoff:
                sleep(min(1.5, (cutoff - observed).total_seconds()))

    wait_until(at(day, "0925"), clock, sleep)
    for minute in PHASES:
        if minute in events:
            continue
        start = at(day, minute)
        if minute in ("0931", "0945"):
            bind_before(start)
        wait_until(start, clock, sleep)
        deadline = start + timedelta(minutes=1)
        if clock() >= deadline or "freeze" not in rec:
            events[minute] = {"status": "gap", "reason": "window_or_freeze_missed"}
            persist()
            continue
        evidence = rec["freeze"]
        universe, plans = evidence["universe"], evidence["plans"]
        paired = datetime.fromisoformat(evidence["observed_at"]) < at(day, "0931")
        if minute == "0945":
            codes = [r["code"] for r in universe["cold"]]
            points, gaps = collect(client, codes, day, minute, deadline, clock, sleep)
            decision = breadth(universe["cold"], points)
            sealed = clock()
            if sealed >= deadline and decision["qualifies"]:
                decision["qualifies"] = False
                gaps["breadth"] = "decision_after_deadline"
            events[minute] = dict(
                status="gap" if gaps else "observed",
                points=points,
                gaps=gaps,
                decision=decision,
                decided_at=sealed.isoformat(),
            )
        else:
            cold_ok = (
                events.get("0945", {}).get("decision", {}).get("qualifies") is True
            )
            active = {
                n: p
                for n, p in plans.items()
                if (paired and n.startswith("selected_" + minute + "/"))
                or (minute == "0946" and cold_ok and n.startswith("cold_0946/"))
            }
            codes = [r["code"] for p in active.values() for r in p["orders"]]
            points, gaps = collect(client, codes, day, minute, deadline, clock, sleep)
            decided = clock()
            admitted = points
            if points and decided >= deadline:
                gaps.update({code: "batch_closed_after_deadline" for code in points})
                admitted = {}
            effects = {
                n: enter(
                    accounts[n], p["orders"], admitted, COSTS[n.split("/")[1]], day
                )
                for n, p in active.items()
            }
            events[minute] = dict(
                status="gap" if gaps else "observed",
                points=points,
                gaps=gaps,
                effects=effects,
                paired_plan_available=paired,
                decided_at=decided.isoformat(),
            )
        persist()


def eod(state, day, client, persist, clock=now, sleep=time.sleep):
    rec = state["days"].setdefault(day, {})
    phases = rec.setdefault("phases", {})
    if "1500" in phases:
        return
    for minute in PHASES:
        phases.setdefault(
            minute, {"status": "gap", "reason": "morning_observation_missing"}
        )
    accounts = state["accounts"]
    codes = sorted({lot["code"] for a in accounts.values() for lot in a["lots"]})
    due = sorted(
        {
            lot["code"]
            for a in accounts.values()
            for lot in a["lots"]
            if lot["entry"] < day
        }
    )
    points, gaps = collect(
        client, codes, day, "1500", clock() + timedelta(seconds=60), clock, sleep
    )
    guards = {}
    for code in due:
        try:
            guard = close_guard(client, code, day)
        except Exception:
            guard = None
        point = points.get(code)
        if (
            guard
            and point
            and (
                point["trade"] > guard["down"]
                or (point["trade"] == guard["down"] and guard["bid_shares"] is not None)
            )
        ):
            guards[code] = guard
        else:
            gaps[code + "/depth"] = "close_guard_missing"
    effects = {}
    for name, account in accounts.items():
        entries = {lot["code"]: lot["entry"] for lot in account["lots"]}
        effects[name] = settle(account, day, points, guards, COSTS[name.split("/")[1]])
        for row in effects[name]:
            row["entry_day"] = entries[row["code"]]
    phases["1500"] = dict(
        status="gap" if gaps else "observed",
        points=points,
        gaps=gaps,
        guards=guards,
        effects=effects,
        observed_at=clock().isoformat(),
    )
    rec["closing_nav_cents"] = {n: a["nav"] for n, a in accounts.items()}
    persist()


def first_unpriced_events(days, dates, family, name):
    """One unknown decision can affect every later cash-constrained position."""
    steps = ("0945", "0946") if family == "cold" else (name.split("/")[0][-4:],)
    for dt in dates:
        record = days[dt]
        phases = record["phases"]
        freeze = record.get("freeze", {})
        orders = freeze.get("plans", {}).get(name, {}).get("orders", [])
        reason = freeze.get("plans", {}).get(name, {}).get("reason")
        if reason:
            return [dt, reason]
        for step in steps:
            event = phases.get(step, {})
            if event.get("status") != "gap":
                continue
            if not freeze:
                return [dt, step]
            if not orders:
                continue
            if (
                step == "0946"
                and family == "cold"
                and phases.get("0945", {}).get("status") == "observed"
                and not phases["0945"]["decision"]["qualifies"]
            ):
                continue
            effects = event.get("effects", {}).get(name)
            if effects is None or any(
                row["status"] == "missing_point" for row in effects
            ):
                return [dt, step]
        if (
            family == "selected"
            and orders
            and datetime.fromisoformat(freeze["observed_at"]) >= at(dt, "0931")
        ):
            return [dt, "unpaired_freeze"]
        close = phases.get("1500", {})
        if close.get("status") == "gap":
            if "effects" not in close or any(
                r["status"] in ("close_missing", "sell_guard_missing")
                for r in close["effects"].get(name, [])
            ):
                return [dt, "1500"]
    return None


def report(state):
    accounts, days = state["accounts"], state["days"]
    navs = {n: a["nav"] for n, a in accounts.items()}
    metrics = {}
    for name, a in accounts.items():
        peak, worst = PROTOCOL["initial_cents_per_arm"], 0
        for _, day in sorted(days.items()):
            value = day.get("closing_nav_cents", {}).get(name)
            if value is not None:
                peak = max(peak, value)
                worst = min(worst, value / peak - 1)
        metrics[name] = {
            "net_yuan": None
            if a["nav"] is None
            else (a["nav"] - PROTOCOL["initial_cents_per_arm"]) / 100,
            "observed_drawdown_pct": round(-100 * worst, 3),
            "open_lots": len(a["lots"]),
            "marked_on": a.get("marked_on") if a["nav"] is not None else None,
            "fees_yuan": a["fees"] / 100,
            "buy_count": a["buys"],
        }
    matured = {}
    dates = sorted(days)
    unpriced = {
        n: first_unpriced_events(days, dates, n.split("_")[0], n)
        for n in accounts
        if not n.startswith("cash/")
    }
    for family, arms, needed in (
        ("cold", ("cold_0946",), ("0945", "0946")),
        ("selected", ("selected_0931", "selected_0946"), ("0931", "0946")),
    ):
        names = [arm + "/" + cost for arm in arms for cost in COSTS]
        valid = []
        for i, dt in enumerate(dates[:-1]):
            r = days[dt]
            freeze = r.get("freeze", {})
            if not freeze.get("universe", {}).get(family):
                continue
            if family == "selected" and datetime.fromisoformat(
                freeze["observed_at"]
            ) >= at(dt, "0931"):
                continue
            if any(freeze["plans"][n].get("reason") for n in names):
                continue
            if any(r["phases"].get(m, {}).get("status") != "observed" for m in needed):
                continue
            if any(
                days[t]["phases"].get("1500", {}).get("status") != "observed"
                for t in (dt, dates[i + 1])
            ):
                continue
            if any(lot["entry"] == dt for n in names for lot in accounts[n]["lots"]):
                continue
            valid.append(dt)
        matured[family] = {
            "days": len(valid),
            "dates": valid,
            "review_due": len(valid) >= PROTOCOL["review_at_days"][0],
        }

    def difference(a, b):
        return (
            round((navs[a] - navs[b]) / 100, 2)
            if navs[a] is not None
            and navs[b] is not None
            and not unpriced.get(a)
            and not unpriced.get(b)
            else None
        )

    pairs = {}
    for cost in COSTS:
        pairs[cost] = {
            "cold_less_cash_yuan": difference("cold_0946/" + cost, "cash/" + cost),
            "0946_less_0931_yuan": difference(
                "selected_0946/" + cost, "selected_0931/" + cost
            ),
        }
    return {
        "activated_at": state["activated_at"],
        "protocol": PROTOCOL["version"],
        "days": len(days),
        "selected_days": sum(
            bool(d.get("freeze", {}).get("universe", {}).get("selected"))
            for d in days.values()
        ),
        "frozen_mode_counts": {
            dt: r["freeze"]["universe"].get("frozen_mode_counts", {})
            for dt, r in sorted(days.items())[-20:]
            if "freeze" in r
        },
        "cold_days": sum(
            bool(d.get("freeze", {}).get("universe", {}).get("cold"))
            for d in days.values()
        ),
        "coverage_gaps": {
            dt: [m for m, p in d["phases"].items() if p["status"] == "gap"]
            for dt, d in days.items()
            if any(p["status"] == "gap" for p in d["phases"].values())
        },
        "last_marked_date": max(
            (
                d
                for d, r in days.items()
                if "closing_nav_cents" in r
                and all(v is not None for v in r["closing_nav_cents"].values())
            ),
            default=None,
        ),
        "returns_at_last_mark": pairs,
        "first_unpriced_path_event": {n: v for n, v in unpriced.items() if v},
        "mature_opportunity_days": matured,
        "observed_ledger_metrics": metrics,
        "accounts": {
            n: {k: a[k] for k in ("cash", "nav", "fees", "realized", "buys")}
            for n, a in accounts.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    for cmd in ("init", "run", "status"):
        commands.add_argument("--" + cmd, action="store_true")
    args = parser.parse_args()
    BOOK.mkdir(parents=True, exist_ok=True)
    path = BOOK / "state.json"
    with (BOOK / "owner.lock").open("a") as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"status":"original_shadow_owner_active"}')
            return
        if not path.exists():
            if not args.init:
                raise ValueError("prospective registration required")
            save(
                path,
                dict(
                    activated_at=now().isoformat(),
                    protocol=PROTOCOL,
                    accounts=new_accounts(),
                    days={},
                ),
            )
        state = json.loads(path.read_bytes())
        if state["protocol"] != PROTOCOL:
            raise ValueError("registered protocol mismatch")
        stamp = now()
        day = stamp.date().isoformat()
        cycle_error = None
        cycle_path = BOOK / "relay_cycle" / "state.json"
        if args.init:
            _, registered_cycle = relay.state_at(BOOK, stamp, register=True)
            registration = {
                "activated_at": registered_cycle["activated_at"],
                "protocol": registered_cycle["protocol"],
                "authority": 0,
                "owner": "xiaocao-weekly-deep-review",
            }
            relay.atomic_write(
                BOOK / "registration.json", relay.encode(registration), immutable=True
            )
        pool_samples = {}
        closed_today = False
        if args.run and stamp.weekday() < 5:
            client = XiaocaoClient(
                base_url=load_settings(None).base_url,
                cache=None,
                retries=0,
                timeout=3,
                minimum_request_interval=0.8,
            )
            sessions = calendar_provider(client)(stamp)
            for dt in sessions:
                if state["activated_at"][:10] < dt < day:
                    phases = state["days"].setdefault(dt, {}).setdefault("phases", {})
                    for m in (*PHASES, "1500"):
                        phases.setdefault(
                            m,
                            {
                                "status": "gap",
                                "reason": "scheduled_observation_missing",
                            },
                        )
            save(path, state)
            if day not in sessions:
                closed = client.get_trade_cal(day, day, "SSE", 0)
                closed_rows = [
                    r
                    for r in closed
                    if str(r.get("calDate") or r.get("tradeDate") or "").replace(
                        "-", ""
                    )
                    == day.replace("-", "")
                    and str(r.get("isOpen")).lower() in ("0", "false")
                ]
                if not closed_rows:
                    raise ValueError("current exchange calendar status unproved")
                previous = max(d for d in sessions if d < day)
                proof = {
                    "day": day,
                    "last_open": previous,
                    "exchange": "SSE",
                    "closed_rows": closed_rows,
                }
                relay.atomic_write(
                    BOOK / "closed_sessions" / (day + ".json"),
                    relay.encode(proof),
                    immutable=True,
                )
            else:
                previous = max(d for d in sessions if d < day)
                early = stamp.hour < 15
                # The price-clock participant always runs on its original thread and HTTP client.
                with ThreadPoolExecutor(max_workers=2) as pool:
                    observation = pool.submit(
                        observe_session,
                        BOOK / "pool_observations",
                        ROOT / "output/live",
                        day,
                        previous,
                        early,
                        client.base_url,
                    )
                    cycle = pool.submit(
                        relay.run,
                        BOOK,
                        day,
                        previous,
                        sessions,
                        early,
                        client.base_url,
                        frozen,
                    )
                    if early:
                        morning(state, day, previous, client, lambda: save(path, state))
                    else:
                        eod(state, day, client, lambda: save(path, state))
                    closed_today = not early
                    try:
                        cycle.result()
                    except Exception as exc:
                        cycle_error = type(exc).__name__ + ": " + str(exc)
                    try:
                        pool_samples = observation.result()
                    except Exception as exc:
                        pool_samples = {
                            "sampler": {"complete": False, "error": type(exc).__name__}
                        }
        result = report(state)
        if cycle_path.exists() and not cycle_error:
            cycle_state = json.loads(cycle_path.read_bytes())
            result["forward_review"] = publish_review(
                BOOK, day, state, result, cycle_state, publish=closed_today
            )
        else:
            result["forward_review"] = {
                "status": "gap",
                "reason": cycle_error or "relay_cycle_registration_missing",
            }
        if pool_samples:
            result["pool_observations"] = pool_samples
        print(json.dumps(result, ensure_ascii=False))
        if args.run and (
            result["forward_review"].get("status") == "gap"
            or day in result["forward_review"].get("cycle_gaps", [])
            or day in result["coverage_gaps"]
            or any(not x["complete"] for x in pool_samples.values())
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
