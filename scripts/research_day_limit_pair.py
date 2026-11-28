"""Observe fixed 100-share DAY tickets on original APP plans. Market-data reads only."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math

import research_relay_walkdown as walkdown
from research_forward_quotes import at, close_guard, now, wait_until
from research_relay_cycle import encode, sha
from xiaocao.api.client import XiaocaoClient
from xiaocao.live.book_b_live_morning import (
    app_buy_permission_reason,
    read_durable_live_plan_intent,
)
from xiaocao.live import entry_clock_pilot as pilot
from xiaocao.live.morning_bundle import inspect_bundle, snapshot_rows
from xiaocao.live.trading_execution import ExecutionStore
from xiaocao.research.entry_clock import COSTS, cash_effect, enter, new_accounts, settle
from xiaocao.utils.atomic_files import atomic_write

CAPITAL = 300_000  # cents
STARTS = ("0931", "0946")
PROTOCOL = {
    "id": "app-day-limit-pair-v1",
    "authority": 0,
    "capital_cents_per_arm": CAPITAL,
    "shares": 100,
    "costs": COSTS,
    "starts": list(STARTS),
    "tif": "DAY",
    "relay_walkdown": walkdown.PROTOCOL,
    "candidate": "reserved APP split when assigned; otherwise earliest affordable original BUY visible before 09:31, tie by code",
    "entry": "first eligible minute price plus adverse slippage within original limit and volume, through close",
    "exit": "first tradable T+1 close with common occupied slot and exit capacity; no new order authority",
}
MINUTES = [
    f"{i // 60:02}{i % 60:02}"
    for start, stop in ((571, 690), (781, 900))
    for i in range(start, stop + 1)
]


def initial_accounts():
    return {
        f"{start}/{cost}": {
            **new_accounts()["cash/normal"],
            "cash": CAPITAL,
            "nav": CAPITAL,
        }
        for start in STARTS
        for cost in COSTS
    }


def register(book, stamp):
    root = book / "day_limit_pair"
    path = root / "registration.json"
    if not path.exists():
        atomic_write(
            path,
            encode({"registered_at": stamp.isoformat(), "protocol": PROTOCOL}),
            immutable=True,
        )
    if json.loads(path.read_bytes())["protocol"] != PROTOCOL:
        raise ValueError("day_pair_registration_changed")


def capture(live, day, observed):
    bundle = inspect_bundle(live, day)
    if (
        bundle["status"] != "ready"
        or datetime.fromisoformat(bundle["published_at"]) > observed
    ):
        raise ValueError("morning_freeze_unavailable")
    raw = Path(bundle["snapshot_path"]).read_bytes()
    if sha(raw) != bundle["snapshot_raw_sha256"]:
        raise ValueError("freeze_hash_changed")
    rows = {
        r["code"]: r
        for r in snapshot_rows(raw, day)
        if r.get("book") == "B" and r.get("is_live") is True
    }
    folder = live / "book_b_live_execution" / "plan_intents"
    if not folder.is_dir():
        raise ValueError("original_intent_directory_missing")
    candidates = []
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_bytes())
        obj = payload["plan"]
        if (
            obj.get("trade_date") != day
            or obj.get("plan_id") != f"book-b:{day}:{obj.get('code')}:BUY"
            or obj.get("side") != "BUY"
            or obj.get("environment") != "live"
            or obj.get("logical_account_id") != "primary"
        ):
            continue
        plan = read_durable_live_plan_intent(payload)
        if (
            plan.created_at > observed
            or plan.shares < 100
            or cash_effect(100, plan.limit_price, True)[0] > CAPITAL
        ):
            continue
        if app_buy_permission_reason(plan.code) or plan.code.endswith(".BJSE"):
            continue
        if plan.code not in rows or str(plan.strategy_run_id) != str(
            bundle["strategy_run_id"]
        ):
            raise ValueError("original_plan_freeze_mismatch")
        data = rows[plan.code]
        candidates.append(
            dict(
                code=plan.code,
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                created_at=plan.created_at.isoformat(),
                limit=min(plan.limit_price, plan.basket_price),
                down=float(data["down_price"]),
                up=float(data["up_price"]),
            )
        )
    candidates.sort(key=lambda r: (datetime.fromisoformat(r["created_at"]), r["code"]))
    assignment = pilot.load_assignment(folder.parent, day)
    if assignment:
        doc, _, early = assignment
        candidates = [
            c
            for c in candidates
            if c["plan_id"] == early.plan_id and c["plan_hash"] == early.plan_hash
        ]
        if not candidates or datetime.fromisoformat(doc["sealed_at"]) > observed:
            raise ValueError("split_not_bound_at_seal")
        candidates[0].update(assignment=doc["sha256"], child_id=doc["child_id"])
    return {
        "status": "eligible" if candidates else "no_visible_eligible_intent",
        "candidate": candidates[0] if candidates else None,
        "freeze_sha256": sha(raw),
    }


def source_points(client, code, day):
    values = {}
    for row in client.minute_line(code, trade_date=day.replace("-", ""), count=241):
        t = str(row.get("tradeTime")).zfill(4)
        if (
            row.get("code") != code
            or str(row.get("tradeDate")) != day.replace("-", "")
            or t not in MINUTES
        ):
            continue
        price, vol = float(row["trade"]), float(row["vol"])
        if (
            t in values
            or not math.isfinite(price)
            or not math.isfinite(vol)
            or price <= 0
            or vol < 0
        ):
            raise ValueError("invalid_minute:" + code + ":" + t)
        values[t] = {"trade": price, "vol": vol}
    return values


def day_fill(account, candidate, points, start, cost, day):
    if set(MINUTES) - points.keys():
        raise ValueError("incomplete_DAY_path:" + candidate["code"])
    if cash_effect(100, candidate["limit"], True)[0] > account["cash"]:
        return {"status": "insufficient_cash", "start": start}
    order = dict(
        code=candidate["code"],
        shares=100,
        basket_price=candidate["limit"],
        up_price=candidate["up"],
        down_price=candidate["down"],
    )
    for t in MINUTES:
        if t < start:
            continue
        event = enter(
            account, [order], {candidate["code"]: points[t]}, COSTS[cost], day
        )[0]
        if event["status"] == "model_buy":
            return {"start": start, "fill_minute": t, **event}
    return {"status": "expired_unfilled", "start": start}


def gap(exc):
    return {
        "status": "gap",
        "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
    }


def validated_morning(record, day, registration):
    if (
        record.get("day") != day
        or record.get("registration_sha256") != sha(encode(registration))
        or record.get("receipt_sha256")
        != sha(encode({k: v for k, v in record.items() if k != "receipt_sha256"}))
    ):
        raise ValueError("day_pair_morning_binding")
    if record["status"] == "gap" and not record.get("candidate"):
        return record
    stamp = datetime.fromisoformat(record["observed_at"])
    if (
        not at(day, "0930") <= stamp < at(day, "0931")
        or len(record.get("freeze_sha256", "")) != 64
    ):
        raise ValueError("day_pair_morning_time")
    candidate = record.get("candidate")
    if record["status"] == "no_visible_eligible_intent" and candidate is None:
        return record
    if (
        record["status"] != "eligible"
        or not candidate
        or candidate["plan_id"] != f"book-b:{day}:{candidate['code']}:BUY"
        or len(candidate["plan_hash"]) != 64
        or not at(day, "0000")
        <= datetime.fromisoformat(candidate["created_at"])
        <= stamp
        or not 0 < candidate["down"] < candidate["up"]
        or not 0 < candidate["limit"]
    ):
        raise ValueError("day_pair_candidate_binding")
    return record


def read_assigned_shadow(book, day, assignment):
    root = book / "day_limit_pair"
    raw = (root / (day + ".morning.json")).read_bytes()
    reg = json.loads((root / "registration.json").read_bytes())
    if reg["protocol"] != PROTOCOL:
        raise ValueError("split_shadow_registration_changed")
    candidate = validated_morning(json.loads(raw), day, reg).get("candidate") or {}
    if (
        candidate.get("assignment") != assignment["sha256"]
        or candidate.get("child_id") != assignment["child_id"]
        or candidate.get("plan_hash") != assignment["early"]["plan_hash"]
        or candidate.get("code") != assignment["original"]["plan"]["code"]
        or candidate.get("limit") != assignment["original"]["plan"]["limit_price"]
    ):
        raise ValueError("split_shadow_not_sealed")
    return sha(raw)


def split_cash_budget(book, state, day):
    folder = book / "day_limit_pair"
    reg = json.loads((folder / "registration.json").read_bytes())
    if reg["protocol"] != PROTOCOL:
        return 0.0
    last, _ = prior_account(folder, day, reg)
    trials = (last or {}).get("split_trials", {})
    assigned = {
        p.stem
        for p in (pilot.root(state) / "assignments").glob("*.json")
        if p.stem < day
    }
    if assigned and ((last or {}).get("split_risk") or {}).get("paused", True):
        return 0.0
    if not all(
        d in trials
        and all(not a["lots"] for a in trials[d]["arms"].values())
        and all(v["status"] != "gap" for v in trials[d]["entries"].values())
        for d in assigned
    ):
        return 0.0
    initial = CAPITAL / 100
    balances = [initial, (last or {}).get("split_risk", {}).get("nav_yuan", initial)]
    for cost in COSTS:
        balances.append(
            initial + sum(trials[d]["arms"][cost]["realized"] for d in assigned) / 100
        )
    return max(0.0, min(balances))


def actual_child(state, assigned_day, doc):
    from xiaocao.live.book_b_accounting import details
    from decimal import Decimal

    pid = doc["child_id"]
    outcome = pilot.root(state) / "dispositions" / (assigned_day + ".json")
    disposition = json.loads(outcome.read_bytes()) if outcome.exists() else {}
    if disposition and (
        disposition["assignment"] != doc["sha256"] or disposition["child_id"] != pid
    ):
        raise ValueError("split_readback_binding")
    current = ExecutionStore(state / "events.jsonl").current(pid)
    result = dict(
        child_id=pid,
        assignment=doc["sha256"],
        disposition=disposition.get("kind"),
        reason=disposition.get("reason"),
        state=current.state.value if current else None,
        order_id=current.broker_order_id if current else None,
    )
    if not current:
        return {
            **result,
            "status": "no_submit"
            if disposition.get("kind") == "no_submit"
            else "pending",
        }
    from xiaocao.live.book_b_live_morning import _plan_intent_path

    plan = read_durable_live_plan_intent(
        json.loads(_plan_intent_path(state, pid).read_bytes())
    )
    if (
        plan.plan_hash != current.plan_hash
        or plan.shares != 100
        or plan.code != doc["early"]["plan"]["code"]
        or plan.limit_price != doc["early"]["plan"]["limit_price"]
    ):
        raise ValueError("split_order_plan_mismatch")
    rows = [r for r in pilot.owned_rows(state) if r["owned_lot_id"] == pid]
    buys = [r for r in rows if r["side"] == "BUY"]
    sells = [r for r in rows if r["side"] == "SELL"]
    bought, sold = (sum(r["shares"] for r in leg) for leg in (buys, sells))
    if bought != current.filled_shares or not 0 <= sold <= bought <= 100:
        raise ValueError("split_ownership_unreconciled")
    postings = (
        [
            r
            for r in details(state)
            if r["owned_lot_id"] == pid and r["kind"] in ("BUY", "SELL")
        ]
        if rows
        else []
    )

    def valued(leg, side):
        gross = sum((Decimal(str(r["fill_notional"])) for r in leg), Decimal(0))
        selected = [r for r in postings if r["kind"] == side]
        exact = (
            {r["source_event_id"] for r in selected} == {r["event_id"] for r in leg}
            and len(leg) == len(selected)
            and all(r["actual_fee"] is not None for r in selected)
        )
        fee = (
            sum((Decimal(str(r["actual_fee"])) for r in selected), Decimal(0))
            if exact
            else None
        )
        known = {
            r["source_event_id"]: r["actual_fee"]
            for r in selected
            if r["actual_fee"] is not None
        }
        cost = sum(
            (
                Decimal(str(known[r["event_id"]]))
                if r["event_id"] in known
                else Decimal(str(r["fill_notional"])) * Decimal(".0001")
                for r in leg
            ),
            Decimal(0),
        )
        return gross, fee, cost

    buy, buyfee, buy_cost = valued(buys, "BUY")
    sell, sellfee, sell_cost = valued(sells, "SELL")
    final = (
        current.state in pilot.TERMINAL
        and not current.submit_chain_uncertain
        and not current.cancel_chain_uncertain
        and sold == bought
    )
    net = (
        sell - buy - buyfee - sellfee
        if final and None not in (buyfee, sellfee)
        else None
    )
    return {
        **result,
        "status": "closed" if final else "open_or_reconciling",
        "bought": bought,
        "sold": sold,
        "buy_gross": float(buy),
        "sell_gross": float(sell),
        "buy_cost_to_date": float(buy_cost),
        "sell_cost_to_date": float(sell_cost),
        "sell_actual_fee": float(sellfee) if sellfee is not None else None,
        "buy_actual_fee": float(buyfee) if buyfee is not None else None,
        "actual_realized_net": float(net) if net is not None else None,
        "fill_event_ids": [r["event_id"] for r in rows],
        "ownership_hashes": [r["event_hash"] for r in rows],
        "accounting_source_hashes": [r["source_sha256"] for r in postings],
    }


def observe_splits(root, live, day, prior, candidate, points, close, guards):
    state = live / "book_b_live_execution"
    trials = dict((prior or {}).get("split_trials", {}))
    assignment = pilot.load_assignment(state, day)
    if assignment:
        doc, _, _ = assignment
        good = candidate and candidate.get("assignment") == doc["sha256"]
        trial = dict(
            assignment=doc["sha256"], child_id=doc["child_id"], arms={}, entries={}
        )
        for cost in COSTS:
            account = initial_accounts()["0931/" + cost]
            try:
                if not good:
                    raise ValueError("paired_seal_missing")
                entry = day_fill(
                    account,
                    candidate,
                    points.get(candidate["code"], {}),
                    "0931",
                    cost,
                    day,
                )
            except ValueError as exc:
                entry = gap(exc)
            trial["entries"][cost] = entry
            trial["arms"][cost] = account
        trials[day] = trial
    for path in sorted((pilot.root(state) / "assignments").glob("*.json")):
        d = path.stem
        if d >= day or d in trials:
            continue
        doc, _, _ = pilot.load_assignment(state, d)
        trials[d] = dict(
            assignment=doc["sha256"],
            child_id=doc["child_id"],
            original_close_missing=True,
            arms={k: initial_accounts()["0931/" + k] for k in COSTS},
            entries={
                k: {"status": "gap", "reason": "assigned_session_close_missing"}
                for k in COSTS
            },
        )
    for trade_day, trial in trials.items():
        doc, _, _ = pilot.load_assignment(state, trade_day)
        if trial["assignment"] != doc["sha256"]:
            raise ValueError("split_observation_changed")
        for cost, account in trial["arms"].items():
            settle(account, day, close, guards, COSTS[cost])
        try:
            from xiaocao.research import split_evidence

            actual = actual_child(state, trade_day, doc)
            source = split_evidence.collect(state, doc)
            split_evidence.verify(source, actual, trade_day)
            raw = encode(source)
            trial["source_sha256"] = sha(raw)
            dest = root / "split_evidence" / (sha(raw) + ".json")
            if not dest.exists():
                atomic_write(dest, raw, immutable=True)
            if dest.read_bytes() != raw:
                raise ValueError("split_source_changed")
        except Exception as exc:
            actual = gap(exc)
        actual["code"] = doc["original"]["plan"]["code"]
        trial["actual"] = actual
        # Same confirmed quantity and common exit isolate the entry-price effect.
        trial["estimated_entry_saving_yuan"] = {}
        trial["entry_saving_yuan"] = {}
        trial["net_difference_yuan"] = {}
        for cost, entry in trial["entries"].items():
            n = actual.get("bought", 0)
            fee = actual.get("buy_actual_fee")
            trial["estimated_entry_saving_yuan"][cost] = (
                round(
                    entry["basis"] / 100
                    - cash_effect(n, actual["buy_gross"] / n, True)[0] / 100,
                    2,
                )
                if (n and entry["status"] == "model_buy" and n == entry["shares"])
                else None
            )
            trial["entry_saving_yuan"][cost] = (
                round(entry["basis"] / 100 - actual["buy_gross"] - fee, 2)
                if (
                    entry["status"] == "model_buy"
                    and n == entry["shares"]
                    and fee is not None
                )
                else None
            )
            account = trial["arms"][cost]
            actual_net = (
                0.0
                if actual["status"] == "no_submit"
                else actual.get("actual_realized_net")
            )
            trial["net_difference_yuan"][cost] = (
                round(actual_net - account["realized"] / 100, 2)
                if (
                    actual_net is not None
                    and not account["lots"]
                    and entry["status"] != "gap"
                )
                else None
            )
    return trials


def split_risk(trials, closing, prior, missing=(), day=None):
    previous = (prior or {}).get("split_risk", {})
    peak = previous.get("peak_yuan", CAPITAL / 100)
    maximum = previous.get("max_drawdown_yuan", 0)
    unvalued = {
        d: set(owners) for d, owners in previous.get("unvalued_exposures", {}).items()
    }

    def add_gap(d, owner):
        if d:
            unvalued.setdefault(d, set()).add(owner)

    for owner, trial in (prior or {}).get("split_trials", {}).items():
        actual = trial["actual"]
        if actual.get("bought", 0) > actual.get("sold", 0) or actual["status"] in (
            "pending",
            "gap",
            "open_or_reconciling",
        ):
            for d in missing:
                add_gap(d, owner)
    incomplete = False
    nav = CAPITAL / 100
    for trade_day, trial in trials.items():
        r = trial["actual"]
        if trial.get("original_close_missing") and not (
            r["status"] == "no_submit"
            or (r["status"] == "closed" and r.get("bought") == 0)
        ):
            add_gap(trade_day, trade_day)
        if r["status"] == "no_submit":
            continue
        if r["status"] not in ("closed", "open_or_reconciling"):
            add_gap(day, trade_day)
            incomplete = True
            continue
        if r["actual_realized_net"] is not None:
            nav += r["actual_realized_net"]
            continue
        held = r["bought"] - r["sold"]
        if held and r["code"] not in closing:
            add_gap(day, trade_day)
            incomplete = True
            continue
        value = held * closing[r["code"]]["trade"] if held else 0
        nav += (
            r["sell_gross"]
            + value * 0.9999
            - r["buy_gross"]
            - r["buy_cost_to_date"]
            - r["sell_cost_to_date"]
        )
    if not incomplete:
        peak = max(peak, nav)
        maximum = max(maximum, round(peak - nav, 2))
    zero = {
        owner
        for owner, trial in trials.items()
        if trial["actual"]["status"] == "no_submit"
        or trial["actual"]["status"] == "closed"
        and trial["actual"].get("bought") == 0
    }
    remaining = {
        d: sorted(owners - zero) for d, owners in unvalued.items() if owners - zero
    }
    return dict(
        nav_yuan=None if incomplete else round(nav, 2),
        peak_yuan=round(peak, 2),
        max_drawdown_yuan=maximum,
        budget_yuan=pilot.AUTH["drawdown_budget_yuan"],
        unvalued_exposures=remaining,
        missing_exposed_dates=sorted(remaining),
        paused=bool(remaining)
        or incomplete
        or maximum >= pilot.AUTH["drawdown_budget_yuan"],
        fee_basis="actual when complete; otherwise provisional 1bp per side",
    )


def prior_account(root, through, registration):
    last = None
    digest = None
    for path in sorted(root.glob("*.close.json")):
        day = path.name.removesuffix(".close.json")
        if day > through:
            continue
        raw = path.read_bytes()
        record = json.loads(raw)
        if (
            day < registration["registered_at"][:10]
            or record.get("day") != day
            or record.get("protocol") != PROTOCOL["id"]
            or record.get("registration_sha256") != sha(encode(registration))
            or record.get("prior_sha256") != digest
            or record.get("receipt_sha256")
            != sha(encode({k: v for k, v in record.items() if k != "receipt_sha256"}))
        ):
            raise ValueError("day_pair_previous_account_chain")
        last = record
        digest = sha(raw)
    return last, digest


def close_session(root, live, day, sessions, registration, morning, client):
    prior, previous_digest = prior_account(root, day, registration)
    if prior and prior["day"] == day:
        return prior
    accounts = prior["accounts"] if prior else initial_accounts()
    after = prior["day"] if prior else registration["registered_at"][:10]
    missing = [d for d in sessions if after < d < day]
    gaps = list(prior["historical_gaps"]) if prior else []
    gaps.extend(missing)
    local = []
    if morning["status"] == "gap":
        local.append(morning["reason"])
    held = {l["code"] for a in accounts.values() for l in a["lots"]}
    cand = morning.get("candidate")
    codes = sorted(held | ({cand["code"]} if cand and not held else set()))
    pilot_held = {
        lot["code"]
        for trial in (prior or {}).get("split_trials", {}).values()
        for account in trial["arms"].values()
        for lot in account["lots"]
    }
    previous_relay = dict((prior or {}).get("relay_walkdown", {}))
    previous_relay["gaps"] = list(previous_relay.get("gaps", [])) + missing
    relay_held = {
        lot["code"]
        for a in previous_relay.get("accounts", {}).values()
        for lot in a["lots"]
    }
    relay_targets = set(relay_held)
    path = root / (day + ".relay-entry.json")
    if path.exists():
        try:
            entry = json.loads(path.read_bytes())
            if entry["status"] == "selected":
                relay_targets.add(entry["decision"]["candidate"]["code"])
        except (KeyError, ValueError, TypeError):
            pass
    pilot_held.update(
        r["actual"]["code"]
        for r in (prior or {}).get("split_trials", {}).values()
        if r["actual"].get("bought", 0) > r["actual"].get("sold", 0)
    )
    prior_trials = (prior or {}).get("split_trials", {})
    state = live / "book_b_live_execution"
    for path in sorted((pilot.root(state) / "assignments").glob("*.json")):
        if path.stem > day:
            continue
        observed = prior_trials.get(path.stem, {}).get("actual") or {}
        if not observed or observed.get("status") in (
            "pending",
            "gap",
            "open_or_reconciling",
        ):
            _, original, _ = pilot.load_assignment(state, path.stem)
            pilot_held.add(original.code)
    codes = sorted(
        set(codes)
        | pilot_held
        | relay_targets
        | ({cand["code"]} if cand and cand.get("assignment") else set())
    )
    points = {}
    guards = {}
    effects = {}
    for code in codes:
        try:
            points[code] = source_points(client, code, day)
            if code in held | pilot_held | relay_held:
                guard = close_guard(client, code, day)
                mark = points[code].get("1500")
                if (
                    guard
                    and mark
                    and (
                        mark["trade"] > guard["down"] or guard["bid_shares"] is not None
                    )
                ):
                    guards[code] = guard
        except Exception as exc:
            if code in held or (cand and code == cand["code"]):
                local.append(code + "/" + gap(exc)["reason"])
    closing = {c: pts["1500"] for c, pts in points.items() if "1500" in pts}
    if any(c not in closing for c in held):
        local.append("missing_funded_mark")
    for name, account in accounts.items():
        start, cost = name.split("/")
        entry = {"status": "prior_slot_occupied" if held else morning["status"]}
        if not held and cand:
            try:
                entry = day_fill(
                    account, cand, points.get(cand["code"], {}), start, cost, day
                )
            except ValueError as exc:
                entry = gap(exc)
                local.append(entry["reason"])
        origin = {l["code"]: l["entry"] for l in account["lots"]}
        events = settle(account, day, closing, guards, COSTS[cost])
        for e in events:
            e["entry_day"] = origin[e["code"]]
            if e["status"] in ("sell_guard_missing", "close_missing"):
                local.append(e["status"] + "/" + e["code"])
        effects[name] = dict(entry=entry, close=events)
    actual = None
    if cand:
        try:
            current = ExecutionStore(
                live / "book_b_live_execution/events.jsonl"
            ).current(cand["plan_id"])
            if current and current.plan_hash == cand["plan_hash"]:
                actual = {
                    "source": "original_APP_plan",
                    "plan_hash": current.plan_hash,
                    "broker_order_id": current.broker_order_id,
                    "state": current.as_dict()["state"],
                    "filled_shares": current.filled_shares,
                    "fill_price": current.fill_price,
                }
        except Exception as exc:
            actual = gap(exc)
    splits = observe_splits(root, live, day, prior, cand, points, closing, guards)
    if local:
        gaps.append(day)
    result = dict(
        day=day,
        protocol=PROTOCOL["id"],
        authority=0,
        prior_sha256=previous_digest,
        registration_sha256=sha(encode(registration)),
        morning=morning,
        observed_points=points,
        exit_guards=guards,
        effects=effects,
        accounts=accounts,
        original_app_readback=actual,
        split_trials=splits,
        relay_walkdown=walkdown.close(root, day, previous_relay, closing, guards),
        split_risk=split_risk(splits, closing, prior, missing, day),
        session_gaps=sorted(set(local)),
        historical_gaps=sorted(set(gaps)),
        net_yuan={
            n: (a["nav"] - CAPITAL) / 100 if a["nav"] is not None else None
            for n, a in accounts.items()
        },
    )
    result["receipt_sha256"] = sha(encode(result))
    return result


def run(book, live, day, sessions, early, base_url, clock=now, sleep=None):
    import time

    sleep = sleep or time.sleep
    root = book / "day_limit_pair"
    registration = json.loads((root / "registration.json").read_bytes())
    if (
        registration["protocol"] != PROTOCOL
        or day < registration["registered_at"][:10]
        or clock().date().isoformat() != day
    ):
        raise ValueError("invalid_day_pair_registration")
    out = root / (day + (".morning.json" if early else ".close.json"))
    if not out.exists():
        if early:
            target = at(day, "0930").replace(second=50)
            wait_until(target, clock, sleep)
            try:
                if clock() >= at(day, "0931"):
                    raise ValueError("pre0931_seal_missed")
                data = capture(live, day, clock())
                sealed = clock()
                if sealed >= at(day, "0931"):
                    raise ValueError("pre0931_seal_missed")
            except Exception as exc:
                sealed = clock()
                data = gap(exc)
            data.update(
                day=day,
                observed_at=sealed.isoformat(),
                registration_sha256=sha(encode(registration)),
            )
            data["receipt_sha256"] = sha(encode(data))
        else:
            if clock() < at(day, "1500"):
                raise ValueError("day_close_not_reached")
            morning_path = root / (day + ".morning.json")
            morning = (
                validated_morning(
                    json.loads(morning_path.read_bytes()), day, registration
                )
                if morning_path.exists()
                else {"status": "gap", "reason": "missing_pre0931_receipt"}
            )
            client = XiaocaoClient(
                base_url=base_url,
                timeout=3,
                retries=0,
                cache=None,
                minimum_request_interval=0.95,
            )
            data = close_session(
                root, live, day, sessions, registration, morning, client
            )
        atomic_write(out, encode(data), immutable=True)
    record = (
        validated_morning(json.loads(out.read_bytes()), day, registration)
        if early
        else prior_account(root, day, registration)[0]
    )
    return {
        "phase": "morning" if early else "close",
        "status": record.get(
            "status", "gap" if record.get("session_gaps") else "observed"
        ),
        "receipt": str(out),
        "sha256": sha(out.read_bytes()),
        "net_yuan": record.get("net_yuan"),
        "walkdown_gaps": (record.get("relay_walkdown") or {}).get("gaps", []),
    }


def run_with_relay(book, live, day, sessions, early, base_url):
    import time

    result = run(book, live, day, sessions, early, base_url)
    if early:
        client = XiaocaoClient(
            base_url=base_url,
            timeout=3,
            retries=0,
            cache=None,
            minimum_request_interval=0.95,
        )
        study = walkdown.morning(book, day, client, now, time.sleep)
        result["relay_status"] = study["status"]
        if study["status"] == "gap":
            result["status"] = "gap"
    return result
