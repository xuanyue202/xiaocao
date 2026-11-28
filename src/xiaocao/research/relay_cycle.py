"""Predeclared forward relay attribution on the marginal slot of an all-COLD day."""

from __future__ import annotations

from statistics import median

from xiaocao.live.book_b_live_morning import app_buy_permission_reason
from xiaocao.research.entry_clock import COSTS, PROTOCOL as CLOCK, new_accounts

ARMS = ("cash", "rank", "index", "rotation")
INDEX = "000300.XSHG"
PROTOCOL = {
    "id": "relay-cycle-forward-v1",
    "authority": 0,
    "cash_cents": CLOCK["initial_cents_per_arm"],
    "costs": COSTS,
    "arms": list(ARMS),
    "sample": "original Book B nonempty and all COLD; unoccupied common slot",
    "candidate": "first permitted non-pre-ST prior one-board stock in natural 09:32 sort37 with jsjl>0 and xcjw>=300",
    "peers": "first up to three other permitted non-pre-ST stocks per group in same ranking; yesterday 1 board vs >=2",
    "measure": "natural 09:30 to 09:43 price-point returns, median per peer group; CSI300 index measured identically",
    "gates": "rank always; index if index>0; rotation if low>0 and low>high; cash always holds",
    "entry": "09:46 next point, 1/6 starting capital maximum, 100-share lots, cap 1.016 times 09:30 point and actual upper limit",
    "exit": "first tradable T+1 close, actual limit guards, partial fills remain; one shared opportunity until every arm flat",
    "review": "20 matured opportunities diagnostic; first 40 matured opportunities fixed evaluation; at least 8 nonzero net difference days vs each active control and 3 positive-rotation episodes; positive early/late and ex-best stress net differences vs cash/rank/index, no greater drawdown than rank; protocol manifest plus section 10 before APP pilot",
    "n_tried": 5,
}


def initial(stamp):
    accounts = {
        f"{arm}/{cost}": new_accounts()[f"cash/{cost}"]
        for arm in ARMS
        for cost in COSTS
    }
    return dict(activated_at=stamp, protocol=PROTOCOL, accounts=accounts, days={})


def cohorts(ranking):
    if ranking.get("status") != "observed":
        return {"status": "gap", "reason": "relay_rank_" + str(ranking.get("status"))}
    rows = ranking["stocks"]
    if [r["code"] for r in rows] != ranking["ordered_codes"]:
        return {"status": "gap", "reason": "rank_members_mismatch"}
    permitted = [
        r
        for r in rows
        if not app_buy_permission_reason(r["code"]) and not r["code"].endswith(".BJSE")
    ]
    for r in permitted:
        height = r.get("ylimitupdays")
        if (
            type(height) not in (int, float)
            or height < 0
            or int(height) != height
            or r.get("isPreSt") not in (0, 1)
        ):
            return {
                "status": "gap",
                "reason": "peer_classification_missing",
                "code": r["code"],
            }
    peers = [r for r in permitted if r["isPreSt"] == 0]
    low = [r for r in peers if r["ylimitupdays"] == 1]
    first = next((r for r in low if r["jsjl"] > 0 and r["xcjw"] >= 300), None)
    if not first:
        return {"status": "no_candidate"}
    code = first["code"]
    low_codes = [r["code"] for r in low if r["code"] != code][:3]
    high_codes = [r["code"] for r in peers if r["ylimitupdays"] >= 2][:3]
    return dict(
        status="ready" if low_codes and high_codes else "no_peer_group",
        candidate=code,
        low=low_codes,
        high=high_codes,
    )


def measure(plan, quotes):
    moves = {c: q["0943"] / q["0930"] - 1 for c, q in quotes.items()}
    low = median(moves[c] for c in plan["low"])
    high = median(moves[c] for c in plan["high"])
    index = moves[INDEX]
    return dict(
        index_return=index,
        high_return=high,
        low_return=low,
        gates={
            "cash": False,
            "rank": True,
            "index": index > 0,
            "rotation": low > 0 and low > high,
        },
    )


def review(state):
    """A closed opportunity contains actual model debits, fees and all exit proceeds."""
    days = state["days"]
    rows = [(d, v) for d, v in sorted(days.items()) if v.get("paired_pnl") is not None]
    verdict_rows = rows[:40]
    gaps = [
        d
        for d, v in sorted(days.items())
        if v.get("decision", {}).get("status") == "gap"
        or v.get("entry", {}).get("status") == "gap"
        or v.get("close", {}).get("gaps")
    ]
    funded_gaps = []
    for day, record in sorted(days.items()):
        close_gaps = record.get("close", {}).get("gaps", {})
        # A missed session close matters economically if a funded lot spanned it.
        exposed = (
            any(
                entry <= day <= (row.get("matured_on") or day)
                and any(row.get("entry", {}).get("fills", {}).values())
                for entry, row in days.items()
            )
            if "session" in close_gaps
            else False
        )
        if (
            record.get("entry", {}).get("status") == "gap"
            and record.get("decision", {}).get("status") == "ready"
            or set(close_gaps) - {"session"}
            or exposed
        ):
            funded_gaps.append(day)
    accounts = {}
    for name, a in state["accounts"].items():
        peak = PROTOCOL["cash_cents"]
        dd = 0
        for _, v in sorted(days.items()):
            nav = v.get("close", {}).get("nav", {}).get(name)
            if nav is not None:
                peak = max(peak, nav)
                dd = max(dd, 1 - nav / peak)
        accounts[name] = dict(
            net_yuan=None
            if a["nav"] is None
            else (a["nav"] - PROTOCOL["cash_cents"]) / 100,
            observed_drawdown_pct=100 * dd,
            buys=a["buys"],
            fees_yuan=a["fees"] / 100,
            open_lots=len(a["lots"]),
        )
    # Count separated spells in eligible opportunities; adjacent positive days are one episode.
    signs = [v["decision"]["factors"]["gates"]["rotation"] for _, v in verdict_rows]
    episodes = sum(
        active and (i == 0 or not signs[i - 1]) for i, active in enumerate(signs)
    )
    phase = (
        "collecting"
        if len(rows) < 20
        else "interim_review"
        if len(rows) < 40
        else "fixed_sample_review"
    )
    return dict(
        protocol=PROTOCOL["id"],
        authority=0,
        stage=phase,
        matured=len(rows),
        mature_dates=[d for d, _ in rows],
        first_40=[d for d, _ in verdict_rows],
        funded_gaps=funded_gaps,
        episodes=episodes,
        accounts=accounts,
        gaps=gaps,
        sessions=len(days),
        dispositions={
            k: sum(v.get("decision", {}).get("status") == k for v in days.values())
            for k in (
                "ready",
                "not_all_cold",
                "slot_occupied",
                "market_veto",
                "no_candidate",
                "no_peer_group",
                "gap",
            )
        },
        actual_orders=0,
    )
