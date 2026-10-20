"""Budget facts for the already allocated, independent Book T sleeve."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

BOOK_T_BUDGET_MODEL = "independent-t-sleeve-v1"


def number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Book T budget {field} is missing or invalid") from exc
    if not math.isfinite(result):
        raise ValueError(f"Book T budget {field} is not finite")
    return result


def position_cost(row: Mapping[str, Any]) -> float:
    # Same cost convention as v1 _book_t_position_cost.
    value = row.get("gross_notional")
    if value is None or number(value, "gross_notional") <= 0:
        value = row.get("entry_cash_out")
    cost = number(value, "position cost")
    if cost <= 0:
        raise ValueError("Book T budget position cost must be positive")
    return cost


def exposure_ratio(portfolio: Mapping[str, Any]) -> float:
    explicit = portfolio.get("max_total_exposure_ratio")
    rules = set()
    for row in portfolio.get("positions", []):
        match = re.search(r"_cap_([0-9.]+)%", str(row.get("allocation_rule") or ""))
        if match:
            rules.add(float(match.group(1)) / 100)
    if len(rules) > 1:
        raise ValueError("Book T budget conflicting frozen exposure caps")
    ratio = number(explicit if explicit is not None else next(iter(rules), 1.0), "exposure ratio")
    if not 0 < ratio <= 1 or (rules and ratio not in rules):
        raise ValueError("Book T budget exposure cap mismatch or out of range")
    return ratio


def target_ratio(portfolio: Mapping[str, Any], equity: float) -> float:
    account = portfolio.get("account")
    # The standalone selector also accepts minimal isolated T portfolios.
    # Production/replay requires complete account facts via budget_contract.
    initial = number(account.get("initial_capital"), "initial capital") if isinstance(account, Mapping) else equity
    if equity <= 0 or initial <= 0:
        raise ValueError("Book T budget capital must be positive")
    return min(equity, initial * exposure_ratio(portfolio)) / equity


def budget_contract(portfolio: Mapping[str, Any]) -> dict[str, Any]:
    if portfolio.get("book", "T") != "T":
        raise ValueError("Book T budget portfolio is not T")
    account = portfolio.get("account")
    if not isinstance(account, Mapping):
        raise ValueError("Book T budget independent account is required")
    initial = number(account.get("initial_capital"), "initial capital")
    cash = number(account.get("cash"), "cash")
    equity = number(portfolio.get("account_equity"), "account equity")
    rows = portfolio.get("positions")
    if not isinstance(rows, list):
        raise ValueError("Book T budget positions are required")
    codes = [str(row.get("code") or "") for row in rows]
    if any(not code for code in codes) or len(set(codes)) != len(codes):
        raise ValueError("Book T budget positions have missing or duplicate identity")
    if any(row.get("book", "T") != "T" or row.get("status", "open") != "open" for row in rows):
        raise ValueError("Book T budget positions must be open T lots")
    cost = sum(position_cost(row) for row in rows)
    if initial <= 0 or cash < 0 or equity <= 0 or abs(equity - cash - cost) > .02:
        raise ValueError("Book T budget account economics mismatch")
    cap_ratio = exposure_ratio(portfolio)
    cap = round(initial * cap_ratio, 2)
    if cost > cap + .02 or len(rows) > 3:
        raise ValueError("Book T budget held exposure or slots exceed original cap")
    return {"model": BOOK_T_BUDGET_MODEL, "initial_capital": initial,
            "account_equity": equity, "max_total_exposure_ratio": cap_ratio,
            "exposure_cap": cap, "held_cost": round(cost, 2),
            "available_cash": cash, "occupied_slots": len(rows), "max_slots": 3,
            "target_budget": round(min(equity, cap), 2),
            "target_ratio": target_ratio(portfolio, equity)}


def validate_control_budget(portfolio: Mapping[str, Any], receipt: Mapping[str, Any],
                            fills: list[Mapping[str, Any]]) -> None:
    """Reverse exact receipt transitions to prove v1's paired cash/cost budget.

    The production adapter freezes the portfolio AFTER the v1 writer. Only
    paired trade + position-transition readback may release old cost/slots.
    """
    budget = budget_contract(portfolio)
    actions = receipt["daily_semantics"]["actions"]
    if not isinstance(actions, list) or any(not isinstance(row, Mapping) for row in actions):
        raise ValueError("Book T control actions are invalid")
    for row in actions:
        if row.get("kind") not in {"trade", "position_transition"}:
            continue
        if not row.get("code") or not row.get("event_sha256"):
            raise ValueError("Book T control action identity is missing")
        if number(row.get("notional"), "action notional") <= 0 or number(row.get("shares"), "action shares") <= 0:
            raise ValueError("Book T control action amounts must be positive")
        if row.get("kind") == "trade":
            if row.get("side") not in {"BUY", "SELL"} or number(row.get("fee"), "action fee") < 0:
                raise ValueError("Book T control trade side or fee is invalid")
        elif row.get("status") not in {"open", "closed"}:
            raise ValueError("Book T control transition status is invalid")
    trades = [row for row in actions if row.get("kind") == "trade"]
    buys = [row for row in trades if row.get("side") == "BUY"]
    sells = [row for row in trades if row.get("side") == "SELL"]
    transitions = [row for row in actions if row.get("kind") == "position_transition"]
    positions = {row["code"]: row for row in portfolio["positions"]}
    released = 0.0
    for trade in buys + sells:
        side = trade["side"]
        matched = [row for row in transitions if row.get("code") == trade.get("code")
                   and row.get("status") == ("open" if side == "BUY" else "closed")
                   and row.get("shares") == trade.get("shares")]
        if len(matched) != 1:
            raise ValueError("Book T control trade lacks exact position transition")
        if side == "SELL":
            if trade["code"] in positions:
                raise ValueError("Book T control closed lot remains in post-control portfolio")
            released += number(matched[0].get("notional"), "released cost")
        else:
            position = positions.get(trade["code"])
            if position is None or position.get("shares") != trade.get("shares") or abs(
                    position_cost(position) - number(trade.get("notional"), "buy gross")) > .02:
                raise ValueError("Book T control BUY does not bind post-control lot")
    filled = [row for row in fills if row.get("status") == "filled"]
    if len(filled) != len(buys):
        raise ValueError("Book T control fills do not match receipt BUY count")
    for trade in buys:
        matched = [row for row in filled if row.get("fill_id") == "v1-control-" + str(trade.get("event_sha256"))]
        if len(matched) != 1 or any(abs(number(matched[0].get(key), key) - number(trade.get(key), key)) > .02
                                   for key in ("notional", "fee", "shares")):
            raise ValueError("Book T control fill economics do not match exact receipt")
    gross = sum(number(row.get("notional"), "buy gross") for row in buys)
    out = sum(number(row.get("notional"), "buy gross") + number(row.get("fee"), "buy fee") for row in buys)
    cash_in = sum(number(row.get("notional"), "sell gross") - number(row.get("fee"), "sell fee") for row in sells)
    pre_cash = budget["available_cash"] + out - cash_in
    pre_cost = budget["held_cost"] - gross + released
    pre_slots = budget["occupied_slots"] - len(buys) + len(sells)
    if pre_cash < -.02 or pre_cost < -.02 or pre_cost > budget["exposure_cap"] + .02 or not 0 <= pre_slots <= 3:
        raise ValueError("Book T control pre-trade budget cannot be proved")
    if out > pre_cash + cash_in + .02 or gross > budget["exposure_cap"] - (pre_cost - released) + .02:
        raise ValueError("Book T control paired execution exceeds cash or exposure")


def constrain_shadow_fills(plan: Mapping[str, Any], portfolio: Mapping[str, Any],
                           fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep canonical readbacks intact, or explicitly block unfunded fills."""
    budget = budget_contract(portfolio)
    remaining_cash = budget["available_cash"]
    remaining_cap = budget["exposure_cap"] - budget["held_cost"]
    slots = budget["max_slots"] - budget["occupied_slots"]
    held = {row["code"] for row in portfolio["positions"]}
    targets = {}
    for theme in plan.get("selected_themes", []):
        instruments = theme.get("instruments") or theme.get("expression", {}).get("instruments", [])
        for instrument in instruments:
            targets[instrument["code"]] = (number(theme.get("target_notional"), "theme target"),
                                           number(instrument.get("target_notional", theme.get("target_notional")), "instrument target"))
    spent_by_theme: dict[str, float] = {}
    result = []
    for raw in fills:
        row = dict(raw)
        if row.get("status") == "filled":
            gross = number(row.get("notional"), "shadow gross")
            out = gross + number(row.get("fee"), "shadow fee")
            theme = str(row.get("theme_id") or "")
            reason = None
            if row["code"] in held:
                reason = "V2_POST_CONTROL_LOT_ALREADY_HELD"
            elif spent_by_theme.get(theme, 0) + gross > targets.get(row["code"], (0, 0))[0] + .02 or gross > targets.get(row["code"], (0, 0))[1] + .02:
                reason = "V2_CANONICAL_FILL_EXCEEDS_THEME_TARGET"
            elif out > remaining_cash + .02 or gross > remaining_cap + .02 or slots <= 0:
                reason = "V2_CASH_EXPOSURE_OR_SLOT_UNPROVEN"
            if reason:
                row.update(status="blocked", skip_reason=reason,
                           unused_control_readback=dict(raw))
                for key in ("notional", "shares", "fee", "fill_price"):
                    row.pop(key, None)
            else:
                remaining_cash -= out
                remaining_cap -= gross
                slots -= 1
                spent_by_theme[theme] = spent_by_theme.get(theme, 0) + gross
        result.append(row)
    return result
