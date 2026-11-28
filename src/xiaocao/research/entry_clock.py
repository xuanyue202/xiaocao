"""Prospective, isolated Book B entry-clock experiment. Amounts in integer cents."""

from __future__ import annotations

from collections import Counter
import math
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from xiaocao.live.book_b_live_morning import (
    _app_permitted_rows,
    app_buy_permission_reason,
)
from xiaocao.live.buy_guards import evaluate_buy_market_guard
from xiaocao.strategy.mode_switch import (
    plan_board_lot_orders,
    select_executable_candidates,
)

ARMS = ("cash", "cold_0946", "selected_0931", "selected_0946")
COSTS = {
    "normal": {"buy_bp": 5, "sell_bp": 0, "volume_fraction": 0.01},
    "stress": {"buy_bp": 20, "sell_bp": 20, "volume_fraction": 0.0025},
}
PROTOCOL = {
    "version": "entry-clock-forward-v1",
    "authority": 0,
    "arms": list(ARMS),
    "review_at_days": [20, 40],
    "review_rule": "paired matured opportunity days per family; compare normal and stress net NAV, drawdown and best-day exclusion; no automatic action",
    "initial_cents_per_arm": 10_000_000,
    "fee_rate": 0.0001,
    "costs": COSTS,
    "cold_condition": "all original Book B rows COLD; strict majority of permitted guarded names above frozen open at 09:45",
    "cold_rank": "one original top-ranked permission-eligible name, one sixth NAV, one concurrent lot, no reseat",
    "selected": "neutral original star-E after APP permissions; shared frozen names; independently funded 50% batch",
    "buy": "exact next scheduled minute trade plus adverse slippage, capped by basket, 100-share lots",
    "exit": "next trading session close point, or next observed tradable close for remainder; same cost model, no-bid guard",
}


def cents(amount):
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def cash_effect(shares, price, buy):
    gross = cents(Decimal(shares) * Decimal(str(price)))
    fee = int(
        (Decimal(gross) * Decimal("0.0001")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return gross + fee if buy else gross - fee, fee


def new_accounts():
    return {
        f"{arm}/{cost}": {
            "cash": 10_000_000,
            "nav": 10_000_000,
            "lots": [],
            "fees": 0,
            "realized": 0,
            "buys": 0,
        }
        for arm in ARMS
        for cost in COSTS
    }


def make_universe(rows, now):
    original = [r for r in rows if r.get("is_live") is True and r.get("book") == "B"]
    if len({r["code"] for r in original}) != len(original):
        raise ValueError("duplicate frozen code")

    def allowed(r):
        return not (app_buy_permission_reason(r["code"]) or r["code"].endswith(".BJSE"))

    def guarded(r):
        return evaluate_buy_market_guard(r, now=now, require_authoritative=True)[0]

    selected = [
        r for r in original if r.get("mode_trade_eligible") and r.get("mode_exec_star")
    ]
    if any(not allowed(r) for r in selected):
        derived = _app_permitted_rows(
            original,
            {"book": "B", "runtime": "live", "status": "neutral"},
            len(selected),
        )
        selected = [
            r
            for r in derived
            if r.get("mode_exec_star") and r.get("mode_trade_eligible")
        ]
    cold = []
    if original and all(r["mode_state"] == "COLD" for r in original):
        cold = select_executable_candidates(
            [
                dict(r, mode_state="PROVISIONAL", mode_trade_eligible=True)
                for r in original
                if allowed(r) and guarded(r)
            ]
        )
        cold.sort(key=lambda r: r["mode_exec_candidate_rank"])
    fields = (
        "code",
        "mode",
        "mode_state",
        "open",
        "up_price",
        "down_price",
        "basket_price",
        "mode_exec_rank",
    )

    def compact(items):
        result = [{k: r[k] for k in fields} for r in items]
        for item in result:
            if not all(
                math.isfinite(float(item[k])) and float(item[k]) > 0
                for k in ("open", "basket_price", "up_price", "down_price")
            ):
                raise ValueError("invalid frozen price")
        return result

    return {
        "selected": compact(
            sorted(
                (r for r in selected if allowed(r) and guarded(r)),
                key=lambda r: r["mode_exec_rank"],
            )
        ),
        "cold": compact(cold),
        "frozen_count": len(original),
        "frozen_state_counts": dict(Counter(r["mode_state"] for r in original)),
        "frozen_mode_counts": dict(Counter(row["mode"] for row in original)),
    }


def plan_accounts(universe, accounts, previous_session):
    plans = {}
    for name, a in accounts.items():
        arm = name.split("/")[0]
        candidates = universe["selected"]
        if a["lots"] and (a.get("marked_on") != previous_session or a["nav"] is None):
            plans[name] = {"reason": "prior_mark_missing", "orders": []}
            continue
        if arm == "cash":
            orders = []
        elif arm == "cold_0946":
            orders = []
            if universe["cold"] and not a["lots"]:
                row = universe["cold"][0]
                budget = min(a["cash"], a["nav"] / 6)
                shares = 100 * int(budget // (row["basket_price"] * 100 * 100 * 1.0001))
                if shares:
                    orders.append(dict(row, shares=shares))
        else:
            held = {lot["code"] for lot in a["lots"]}
            rows = plan_board_lot_orders(
                [r for r in candidates if r["code"] not in held],
                nav=a["nav"] / 100,
                cash_limit=min(a["cash"] / 100, a["nav"] / 200),
                fee_rate=0.0001,
                price_key="basket_price",
            )
            orders = [dict(r, shares=r["mode_exec_planned_shares"]) for r in rows]
        plans[name] = {"orders": orders}
    return plans


def breadth(rows, points):
    missing = [r["code"] for r in rows if r["code"] not in points]
    above = sum(
        points[r["code"]]["trade"] > r["open"] for r in rows if r["code"] in points
    )
    return {
        "size": len(rows),
        "above": above,
        "missing": missing,
        "qualifies": bool(rows) and not missing and above * 2 > len(rows),
    }


def enter(a, orders, points, cost, day):
    effects = []
    for r in orders:
        code = r["code"]
        q = points.get(code)
        if not q:
            effects.append({"code": code, "status": "missing_point"})
            continue
        price = float(
            (Decimal(str(q["trade"])) * (1 + Decimal(cost["buy_bp"]) / 10000)).quantize(
                Decimal(".01"), rounding=ROUND_CEILING
            )
        )
        size = min(r["shares"], 100 * int(q["vol"] * cost["volume_fraction"] // 100))
        if (
            price > r["basket_price"]
            or q["trade"] <= r["down_price"]
            or q["trade"] >= r["up_price"]
            or price > r["up_price"]
        ):
            effects.append({"code": code, "status": "outside_limits"})
        elif size < 100:
            effects.append({"code": code, "status": "volume_below_lot"})
        else:
            debit, fee = cash_effect(size, price, True)
            if debit > a["cash"]:
                raise ValueError("shadow cash underflow")
            lot = dict(code=code, shares=size, entry=day, price=price, basis=debit)
            a["lots"].append(lot)
            a["cash"] -= debit
            a["fees"] += fee
            a["buys"] += 1
            effects.append({**lot, "status": "model_buy", "fee": fee})
    return effects


def settle(a, day, points, guards, cost):
    remaining, effects = [], []
    value, complete = 0, True
    for lot in a["lots"]:
        code, n = lot["code"], lot["shares"]
        q = points.get(code)
        guard = guards.get(code)
        if not q:
            remaining.append(lot)
            complete = False
            effects.append({"code": code, "status": "close_missing"})
            continue
        tradable = (
            guard
            and guard["down"] > 0
            and q["trade"] >= guard["down"]
            and (q["trade"] > guard["down"] + 0.001 or (guard["bid_shares"] or 0) > 0)
        )
        sold = 0
        if lot["entry"] < day and tradable:
            capacity = q["vol"] * cost["volume_fraction"]
            if q["trade"] <= guard["down"] + 0.001:
                capacity = min(capacity, guard["bid_shares"])
            sold = min(n, 100 * int(capacity // 100))
        if sold:
            sell_price = max(
                guard["down"], round(q["trade"] * (1 - cost["sell_bp"] / 10000), 2)
            )
            proceeds, fee = cash_effect(sold, sell_price, False)
            basis = (lot["basis"] * sold + n // 2) // n
            a["cash"] += proceeds
            a["realized"] += proceeds - basis
            a["fees"] += fee
            effects.append(
                dict(
                    code=code,
                    shares=sold,
                    price=sell_price,
                    basis=basis,
                    fee=fee,
                    pnl=proceeds - basis,
                    status="model_sell",
                )
            )
            lot = {**lot, "shares": n - sold, "basis": lot["basis"] - basis}
        if lot["shares"]:
            remaining.append(lot)
            value += cash_effect(lot["shares"], q["trade"], False)[0]
            status = (
                "t1"
                if lot["entry"] == day
                else "sell_guard_missing"
                if not guard
                else "liquidity_deferred"
            )
            effects.append({"code": code, "status": status, "shares": lot["shares"]})
    a.update(lots=remaining, nav=a["cash"] + value if complete else None, marked_on=day)
    return effects
