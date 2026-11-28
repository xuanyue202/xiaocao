"""Natural-window relay study inside the existing local research wake."""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path

from live_monitor import _detail_observed_at, _detail_trade_date
from research_forward_quotes import CHINA, at, close_guard, collect, now, wait_until
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.errors import ApiError
from xiaocao.live.buy_guards import evaluate_buy_market_guard
from xiaocao.research.entry_clock import COSTS, enter, settle
from xiaocao.research.pool_observation import read_receipt
from xiaocao.research.relay_cycle import (
    INDEX,
    PROTOCOL,
    cohorts,
    initial,
    measure,
    review,
)
from xiaocao.utils.atomic_files import atomic_write


def encode(value):
    return json.dumps(
        value,
        sort_keys=True,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def store(path, value):
    atomic_write(path, encode(value))


def state_at(book, stamp, register=False):
    path = book / "relay_cycle" / "state.json"
    if not path.exists():
        if not register:
            raise ValueError("relay_cycle_registration_missing")
        atomic_write(path, encode(initial(stamp.isoformat())), immutable=True)
    state = json.loads(path.read_bytes())
    if state["protocol"] != PROTOCOL:
        raise ValueError("relay_cycle_protocol_mismatch")
    return path, state


def relay_plan(book, day, previous, freeze):
    path = book / "pool_observations" / day / "0932.json"
    receipt, error = read_receipt(path, day, "0932", previous)
    if error:
        return dict(status="gap", reason=error)
    if receipt.get("opening", {}).get("checkpoint_sha256") != freeze["checkpoint"]:
        return dict(status="gap", reason="opening_checkpoint_mismatch")
    rank = receipt.get("relay_ranking") or {}
    if rank.get("requested_day") != day or rank.get("sort_id") != 37:
        return dict(status="gap", reason="relay_rank_identity_mismatch")
    if rank.get("status") == "observed":
        members = receipt["current"]["jieli"]
        if members["status"] != "observed" or set(members["codes"]) != set(
            rank["ordered_codes"]
        ):
            return dict(status="gap", reason="ranked_members_mismatch")
        ordered = rank["ordered_codes"]
        reads = rank["reads"]
        if len(ordered) != len(set(ordered)) or [r.get("kind") for r in reads] != [
            "sort:37"
        ] + ["stock_index"] * ((len(ordered) + 79) // 80):
            return dict(status="gap", reason="rank_read_sequence")
        prior = at(day, "0932")
        for read in reads:
            start, end = (
                datetime.fromisoformat(read[k]) for k in ("started_at", "completed_at")
            )
            if not prior <= start <= end < at(day, "0933"):
                return dict(status="gap", reason="rank_outside_window")
            prior = end
    return {
        **cohorts(rank),
        "rank_receipt": sha(path.read_bytes()),
        "checkpoint": freeze["checkpoint"],
    }


def stock_guard(client, code, day, clock, minute="0943"):
    raw = client.second_line_detail_info(code)
    if isinstance(raw, dict) and code in raw and isinstance(raw[code], dict):
        raw = {**raw[code], "code": raw[code].get("code", code)}
    rows = raw if isinstance(raw, list) else [raw]
    hits = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("code") == code
        and _detail_trade_date(r) == day
    ]
    if len(hits) != 1:
        raise ValueError("candidate_quote_identity")
    r = hits[0]
    stamp = _detail_observed_at(r, day)
    if not stamp or not at(day, minute) <= stamp <= clock():
        raise ValueError("candidate_quote_time")
    down, up = float(r["downPrice"]), float(r["upPrice"])
    if not math.isfinite(up) or not math.isfinite(down) or not 0 < down < up:
        raise ValueError("candidate_quote_bands")
    ok, reason, evidence = evaluate_buy_market_guard(
        {**r, "date": day, "market_observed_at": stamp.isoformat()},
        now=clock(),
        require_authoritative=True,
    )
    if not ok and reason != "LIMIT_DOWN_BUY_BLOCKED":
        raise ValueError(reason or "candidate_status_unknown")
    return dict(allowed=ok, reason=reason, evidence=evidence, up=up, down=down)


def points_for(client, code, day):
    rows = client.minute_line(
        code, trade_date=day.replace("-", ""), count=241, code_type=int(code == INDEX)
    )
    result = {}
    for r in rows:
        minute = str(r.get("tradeTime")).zfill(4)
        if (
            minute not in ("0930", "0943")
            or r.get("code") != code
            or str(r.get("tradeDate")).replace("-", "") != day.replace("-", "")
        ):
            continue
        if minute in result:
            raise ValueError("duplicate_minute_" + code)
        value = float(r["trade"])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("invalid_minute_" + code)
        result[minute] = value
    if len(result) != 2:
        raise ValueError("missing_minute_" + code)
    return result


def morning(
    state,
    day,
    previous,
    book,
    client,
    freeze_reader,
    persist,
    clock=now,
    sleep=time.sleep,
):
    rec = state["days"].setdefault(day, {})
    if "entry" in rec:
        return
    if "decision" not in rec:
        wait_until(at(day, "0943"), clock, sleep)
        try:
            if clock() >= at(day, "0946"):
                raise ValueError("decision_window_missed")
            if any(a["lots"] for a in state["accounts"].values()):
                decision = {"status": "slot_occupied"}
            else:
                freeze = freeze_reader(day, clock())
                if freeze is None:
                    raise ValueError("missing_original_freeze")
                counts = freeze["universe"].get("frozen_state_counts", {})
                if sum(counts.values()) != freeze["universe"]["frozen_count"]:
                    raise ValueError("incomplete_original_states")
                if not counts or set(counts) != {"COLD"}:
                    decision = {
                        "status": "not_all_cold",
                        "checkpoint": freeze["checkpoint"],
                    }
                else:
                    decision = relay_plan(book, day, previous, freeze)
            if decision["status"] == "ready":
                code = decision["candidate"]
                quotes = {}
                pending = [INDEX, *decision["high"], *decision["low"], code]
                while pending and clock() < at(day, "0945"):
                    for symbol in pending.copy():
                        if clock() >= at(day, "0945"):
                            break
                        try:
                            quotes[symbol] = points_for(client, symbol, day)
                        except (ValueError, OSError, RuntimeError, ApiError):
                            continue
                        else:
                            pending.remove(symbol)
                    if pending and clock() < at(day, "0945"):
                        sleep(min(1, (at(day, "0945") - clock()).total_seconds()))
                if pending:
                    raise ValueError("missing_factor_points:" + ",".join(pending))
                guard = stock_guard(client, code, day, clock)
                decision.update(
                    points=quotes,
                    factors=measure(decision, quotes),
                    guard=guard,
                    cap=min(guard["up"], quotes[code]["0930"] * 1.016),
                )
                if not guard["allowed"]:
                    decision["status"] = "market_veto"
            if clock() >= at(day, "0946"):
                raise ValueError("factor_response_late")
        except Exception as exc:
            decision = {
                "status": "gap",
                "reason": str(exc)
                if isinstance(exc, ValueError)
                else type(exc).__name__,
            }
        rec["decision"] = {**decision, "sealed_at": clock().isoformat()}
        persist()
    plan = rec["decision"]
    if plan["status"] != "ready":
        rec["entry"] = {"status": "gap" if plan["status"] == "gap" else "skipped"}
        persist()
        return
    wait_until(at(day, "0946"), clock, sleep)
    code = plan["candidate"]
    deadline = at(day, "0947")
    entry_guard = None
    while clock() < deadline and entry_guard is None:
        try:
            entry_guard = stock_guard(client, code, day, clock, minute="0946")
        except (ValueError, KeyError, TypeError, ApiError, OSError, RuntimeError):
            if clock() < deadline:
                sleep(min(1, (deadline - clock()).total_seconds()))
    points, gaps = collect(client, [code], day, "0946", deadline, clock, sleep)
    if (
        not entry_guard
        or gaps
        or clock() >= deadline
        or datetime.fromisoformat(plan["sealed_at"]) >= at(day, "0946")
    ):
        rec["entry"] = {
            "status": "gap",
            "reason": "entry_point_or_guard_missing_or_late",
            "code": code,
        }
    else:
        effects = {}
        fills = {}
        for name, a in state["accounts"].items():
            arm, cost = name.split("/")
            budget = min(a["cash"], PROTOCOL["cash_cents"] / 6)
            shares = 100 * int(budget // (plan["cap"] * 100 * 100 * 1.0001))
            orders = (
                [
                    dict(
                        code=code,
                        shares=shares,
                        basket_price=plan["cap"],
                        up_price=entry_guard["up"],
                        down_price=entry_guard["down"],
                    )
                ]
                if entry_guard["allowed"] and plan["factors"]["gates"][arm] and shares
                else []
            )
            effects[name] = enter(a, orders, points, COSTS[cost], day)
            fills[name] = sum(
                e["shares"] for e in effects[name] if e["status"] == "model_buy"
            )
        rec["entry"] = dict(
            status="observed",
            point=points,
            guard=entry_guard,
            effects=effects,
            fills=fills,
        )
    persist()


def closing(state, day, client, persist, clock=now, sleep=time.sleep):
    rec = state["days"].setdefault(day, {})
    if "close" in rec:
        return
    rec.setdefault("decision", {"status": "gap", "reason": "morning_missing"})
    rec.setdefault("entry", {"status": "gap", "reason": "entry_missing"})
    accounts = state["accounts"]
    codes = sorted({lot["code"] for a in accounts.values() for lot in a["lots"]})
    points, gaps = collect(
        client, codes, day, "1500", clock() + timedelta(seconds=60), clock, sleep
    )
    guards = {}
    for code in sorted(
        {
            lot["code"]
            for a in accounts.values()
            for lot in a["lots"]
            if lot["entry"] < day
        }
    ):
        try:
            guard = close_guard(client, code, day)
        except Exception:
            guard = None
        if (
            guard
            and code in points
            and (
                points[code]["trade"] > guard["down"]
                or (
                    points[code]["trade"] == guard["down"]
                    and guard["bid_shares"] is not None
                )
            )
        ):
            guards[code] = guard
        else:
            gaps[code + "/guard"] = "exit_quote_unavailable"
    effects = {}
    for name, a in accounts.items():
        entry_day = a["lots"][0]["entry"] if a["lots"] else None
        events = settle(a, day, points, guards, COSTS[name.split("/")[1]])
        for e in events:
            e["entry_day"] = entry_day
            if e["status"] == "model_sell":
                source = state["days"][entry_day].setdefault("sold_pnl", {})
                source[name] = source.get(name, 0) + e["pnl"]
        effects[name] = events
    rec["close"] = dict(
        effects=effects,
        points=points,
        guards=guards,
        gaps=gaps,
        nav={n: a["nav"] for n, a in accounts.items()},
    )
    held = {lot["entry"] for a in accounts.values() for lot in a["lots"]}
    for d, v in state["days"].items():
        entry = v.get("entry", {})
        if (
            d < day
            and d not in held
            and "paired_pnl" not in v
            and entry.get("status") == "observed"
        ):
            v["paired_pnl"] = {n: v.get("sold_pnl", {}).get(n, 0) for n in accounts}
            v["matured_on"] = day
    persist()


def run(book, live_day, previous, sessions, early, base_url, freeze_reader):
    path, state = state_at(book, now())
    for dt in sessions:
        if state["activated_at"][:10] < dt < live_day:
            row = state["days"].setdefault(dt, {})
            row.setdefault(
                "decision", {"status": "gap", "reason": "scheduled_morning_missing"}
            )
            row.setdefault(
                "entry", {"status": "gap", "reason": "scheduled_entry_missing"}
            )
            row.setdefault(
                "close", {"gaps": {"session": "scheduled_close_missing"}, "nav": {}}
            )
    persist = lambda: store(path, state)
    persist()
    client = XiaocaoClient(
        base_url=base_url,
        timeout=3,
        retries=0,
        cache=None,
        minimum_request_interval=0.95,
    )
    if early:
        morning(state, live_day, previous, book, client, freeze_reader, persist)
    else:
        closing(state, live_day, client, persist)
    return review(state)
