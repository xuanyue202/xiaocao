"""One precommitted 09:45 relay replacement, observed under the existing research owner."""

from __future__ import annotations
from datetime import datetime
import json
import math
from pathlib import Path

from research_forward_quotes import at, collect, wait_until
from research_relay_cycle import encode, sha, stock_guard
from xiaocao.research.pool_observation import read_receipt
from xiaocao.research.entry_clock import COSTS, enter, new_accounts, settle
from xiaocao.utils.atomic_files import atomic_write

PROTOCOL = dict(
    id="sealed-relay-successor-v1",
    capital_yuan=100000,
    cash_interest=0,
    ranking="natural 09:32 relay pool sort37; jsjl>0, xcjw>=300, permitted non-ST shares",
    decision="if first eligible trades at upper limit with standing bid and no ask at 09:45, choose first tradable in order within 1.016 x 09:30",
    execution="09:46 exact point, one common slot, at most 1/6 NAV; first tradable T+1 close",
    costs=COSTS,
    authority=0,
)


def ranked(book, day):
    path = book / "pool_observations" / day / "0932.json"
    receipt, error = read_receipt(path, day, "0932", None)
    if error:
        raise ValueError(error)
    rank = receipt["relay_ranking"]
    members = receipt["current"]["jieli"]
    rows = rank["stocks"]
    order = rank["ordered_codes"]
    if (
        members["status"] != "observed"
        or rank["status"] not in ("observed", "missing_scores")
        or rank["requested_day"] != day
        or rank["sort_id"] != 37
        or set(order) != set(members["codes"])
        or len(order) != len(set(order))
        or [r["code"] for r in rows] != order
    ):
        raise ValueError("relay_rank_or_score_gap")
    reads = rank["reads"]
    if [r["kind"] for r in reads] != ["sort:37"] + ["stock_index"] * (
        (len(order) + 79) // 80
    ):
        raise ValueError("relay_read_sequence")
    prev = at(day, "0932")
    for r in reads:
        start, end = (
            datetime.fromisoformat(r[k]) for k in ("started_at", "completed_at")
        )
        if not prev <= start <= end < at(day, "0933"):
            raise ValueError("relay_rank_time")
        prev = end
    return rows, sha(path.read_bytes())


def choose(rows, quote):
    trace = []
    for r in rows:
        c = r["code"]
        if (
            c.startswith(("688", "689"))
            or c.endswith(".BJSE")
            or (r.get("jsjl") is not None and r["jsjl"] <= 0)
            or (r.get("xcjw") is not None and r["xcjw"] < 300)
        ):
            continue
        if r.get("isPreSt") not in (0, 1) or not r.get("codeName"):
            raise ValueError("relay_ST_identity_unknown")
        if r["isPreSt"] or "ST" in r["codeName"].upper():
            continue
        if r.get("jsjl") is None or r.get("xcjw") is None:
            raise ValueError("earlier_relay_score_unknown")
        q = quote(c)
        sealed = (
            q["trade"] == q["up"]
            and q["buyPrice1"] == q["up"]
            and q["buyVol1"] > 0
            and q["sellVol1"] == 0
            and q["sellPrice1"] == 0
        )
        cap = min(q["up"], round(q["open"] * 1.016, 6))
        trace.append(dict(code=c, cap=cap, score=r["xcjw"], **q))
        if len(trace) == 1 and not sealed:
            return "first_not_sealed", None, trace
        if (
            not sealed
            and q["allowed"]
            and q["down"] < q["trade"] <= cap
            and q["vol"] > 0
            and 0 < q["sellPrice1"] <= cap
            and q["sellVol1"] >= 100
        ):
            return "selected", trace[-1], trace
    return "no_replacement", None, trace


def morning(book, day, client, clock, sleep):
    folder = book / "day_limit_pair"

    def seal(name, cutoff, callback):
        p = folder / (day + ".relay-" + name + ".json")
        if not p.exists():
            try:
                if clock() >= cutoff:
                    raise ValueError("sampling_window_missed")
                record = callback()
                if clock() >= cutoff:
                    raise ValueError("late_response")
            except Exception as exc:
                record = dict(status="gap", reason=str(exc))
            record.update(
                day=day, observed_at=clock().isoformat(), protocol=PROTOCOL["id"]
            )
            record["sha256"] = sha(encode(record))
            atomic_write(p, encode(record), immutable=True)
        raw = p.read_bytes()
        rec = json.loads(raw)
        if (
            rec["sha256"]
            != sha(encode({k: v for k, v in rec.items() if k != "sha256"}))
            or rec["day"] != day
            or rec["protocol"] != PROTOCOL["id"]
            or rec["status"] != "gap"
            and not at(day, "0945" if name == "decision" else "0946")
            <= datetime.fromisoformat(rec["observed_at"])
            < cutoff
        ):
            raise ValueError("relay_receipt_mismatch")
        return rec

    def decision():
        rows, rank_hash = ranked(book, day)

        def quote(code):
            detail = stock_guard(
                client, code, day, clock, minute="0945", book_quotes=True
            )
            points = {}
            for r in client.minute_line(
                code, trade_date=day.replace("-", ""), count=241
            ):
                t = str(r.get("tradeTime")).zfill(4)
                if (
                    r.get("code") == code
                    and str(r.get("tradeDate")) == day.replace("-", "")
                    and t in ("0930", "0945")
                ):
                    if t in points:
                        raise ValueError("duplicate_minute")
                    points[t] = r
            opening, trade, volume = map(
                float,
                (
                    points["0930"]["trade"],
                    points["0945"]["trade"],
                    points["0945"]["vol"],
                ),
            )
            if (
                not all(math.isfinite(v) for v in (opening, trade, volume))
                or min(opening, trade) <= 0
                or volume < 0
            ):
                raise ValueError("invalid_minute")
            return dict(
                open=opening,
                trade=trade,
                vol=volume,
                down=detail["down"],
                up=detail["up"],
                allowed=detail["allowed"],
                book_at=detail["evidence"]["observed_at"],
                **{
                    k: detail[k]
                    for k in ("buyPrice1", "buyVol1", "sellPrice1", "sellVol1")
                },
            )

        status, selection, trace = choose(rows, quote)
        return dict(
            status=status, candidate=selection, trace=trace, rank_sha256=rank_hash
        )

    wait_until(at(day, "0945"), clock, sleep)
    decision_record = seal("decision", at(day, "0946"), decision)
    wait_until(at(day, "0946"), clock, sleep)

    def entry():
        current = None
        status = decision_record["status"]
        point = None
        if status == "selected":
            code = decision_record["candidate"]["code"]
            q, errors = collect(
                client, [code], day, "0946", at(day, "0947"), clock, sleep
            )
            if errors:
                raise ValueError("entry_quote_missing")
            current = stock_guard(
                client, code, day, clock, minute="0946", book_quotes=True
            )
            if (current["up"], current["down"]) != (
                decision_record["candidate"]["up"],
                decision_record["candidate"]["down"],
            ):
                raise ValueError("price_band_changed")
            if (
                current["allowed"]
                and 0 < current["sellPrice1"] <= decision_record["candidate"]["cap"]
                and current["sellVol1"] >= 100
            ):
                point = {
                    **q[code],
                    "ask_price": current["sellPrice1"],
                    "ask_shares": current["sellVol1"],
                    "book_at": current["evidence"]["observed_at"],
                }
            else:
                status = "entry_veto"
        return dict(
            status=status, decision=decision_record, point=point, market_guard=current
        )

    return seal("entry", at(day, "0947"), entry)


def close(folder, day, previous, closing, guards):
    p = folder / (day + ".relay-entry.json")
    accounts = (previous or {}).get("accounts") or {
        k: new_accounts()["cash/normal"] for k in COSTS
    }
    gaps = list((previous or {}).get("gaps", []))
    occupied = any(a["lots"] for a in accounts.values())
    try:
        raw = p.read_bytes()
        rec = json.loads(raw)
        decision = rec["decision"]
        if (
            rec["sha256"]
            != sha(encode({k: v for k, v in rec.items() if k != "sha256"}))
            or rec["day"] != day
            or rec["protocol"] != PROTOCOL["id"]
            or decision["day"] != day
            or decision["sha256"]
            != sha(encode({k: v for k, v in decision.items() if k != "sha256"}))
            or json.loads((folder / (day + ".relay-decision.json")).read_bytes())
            != decision
        ):
            raise ValueError("relay_decision_chain")
        if rec["status"] != "gap":
            _, rank_hash = ranked(folder.parent, day)
            if (
                rank_hash != decision["rank_sha256"]
                or not at(day, "0945")
                <= datetime.fromisoformat(decision["observed_at"])
                < at(day, "0946")
                or not at(day, "0946")
                <= datetime.fromisoformat(rec["observed_at"])
                < at(day, "0947")
            ):
                raise ValueError("relay_rank_or_time_changed")
        if rec["status"] == "gap":
            raise ValueError("entry_or_rank_missing")
    except (ValueError, KeyError, OSError, TypeError) as exc:
        rec = dict(status="gap", reason=str(exc))
        gaps.append(day)
    effects = {}
    for cost, a in accounts.items():
        entry = {"status": "prior_slot_occupied" if occupied else rec["status"]}
        if not occupied and rec["status"] == "selected":
            r = rec["decision"]["candidate"]
            n = (
                100 * int(min(a["cash"], a["nav"] / 6) // (r["cap"] * 10000 * 1.0001))
                if a["nav"] is not None
                else 0
            )
            point = rec["point"]
            n = min(n, 100 * int(point["ask_shares"] // 100))
            executable = {**point, "trade": max(point["trade"], point["ask_price"])}
            order = dict(
                code=r["code"],
                shares=n,
                basket_price=r["cap"],
                up_price=r["up"],
                down_price=r["down"],
            )
            entry = (
                enter(a, [order], {r["code"]: executable}, COSTS[cost], day)[0]
                if n
                else {"status": "no_funded_lot"}
            )
        exits = settle(a, day, closing, guards, COSTS[cost])
        if any(x["status"] in ("close_missing", "sell_guard_missing") for x in exits):
            gaps.append(day)
        effects[cost] = dict(entry=entry, exits=exits)
    return dict(
        protocol=PROTOCOL["id"],
        accounts=accounts,
        effects=effects,
        entry_receipt=rec,
        gaps=sorted(set(gaps)),
        net_yuan={
            k: (a["nav"] - 10000000) / 100 if a["nav"] is not None else None
            for k, a in accounts.items()
        },
    )
