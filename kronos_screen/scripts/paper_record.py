"""Record the day's ★B (live K->P + auction) picks as paper positions so
live_monitor.py can track them under the v5 rule. Idempotent per (date, code).

For pre-open/auction decisions, paper fills should be marked at the worst-case
`basket_price` when available instead of the raw auction/open print; that better
matches a realistic "do not chase above basket" execution assumption.
Reads output/live/signal_snapshots.jsonl; appends to output/live/positions.jsonl.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

SNAP = Path("output/live/signal_snapshots.jsonl")
POS = Path("output/live/positions.jsonl")
ACCOUNT = Path("output/live/paper_account.json")
TRADES = Path("output/live/paper_trades.jsonl")
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001
DEFAULT_DEPLOY_RATIO = 0.5
DEFAULT_MAX_TOTAL_EXPOSURE_RATIO = 0.67


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_account(initial_capital: float, fee_rate: float) -> dict:
    if ACCOUNT.exists():
        with ACCOUNT.open(encoding="utf-8") as f:
            account = json.load(f)
        account.setdefault("initial_capital", initial_capital)
        account.setdefault("cash", initial_capital)
        account.setdefault("fee_rate", fee_rate)
        account.setdefault("realized_pnl", 0.0)
        account.setdefault("total_fees", 0.0)
        return account
    return {
        "initial_capital": initial_capital,
        "cash": initial_capital,
        "fee_rate": fee_rate,
        "realized_pnl": 0.0,
        "total_fees": 0.0,
        "created_at": _now_iso(),
    }


def _save_account(account: dict) -> None:
    ACCOUNT.parent.mkdir(parents=True, exist_ok=True)
    account["updated_at"] = _now_iso()
    tmp = ACCOUNT.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(ACCOUNT)


def _append_trade(record: dict) -> None:
    TRADES.parent.mkdir(parents=True, exist_ok=True)
    with TRADES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _fill_price(record: dict) -> tuple[float | None, str, str | None]:
    basket = record.get("basket_price")
    try:
        basket_px = float(basket) if basket not in (None, "") else None
    except (TypeError, ValueError):
        basket_px = None
    if basket_px and basket_px > 0:
        return basket_px, "basket", record.get("basket_rule")
    opn = record.get("open")
    try:
        open_px = float(opn) if opn not in (None, "") else None
    except (TypeError, ValueError):
        open_px = None
    return open_px, "open", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--pick", choices=["vb_star", "kp_star"], default="vb_star",
                    help="which variant to paper-trade (vb_star=★B live set, kp_star=★ baseline)")
    ap.add_argument("--initial-capital", type=float, default=DEFAULT_STARTING_CAPITAL,
                    help="initial paper account cash; only used when the account file does not exist")
    ap.add_argument("--fee-rate", type=float, default=DEFAULT_FEE_RATE,
                    help="one-way transaction fee rate, e.g. 0.0001 = 1bp")
    ap.add_argument("--notional", type=float, default=None,
                    help="optional max RMB per position; defaults to available cash / number of buyable picks")
    ap.add_argument("--deploy-ratio", type=float, default=DEFAULT_DEPLOY_RATIO,
                    help="fraction of current cash allowed to deploy on this run; default 0.5 keeps dry powder")
    ap.add_argument("--max-total-exposure-ratio", type=float, default=DEFAULT_MAX_TOTAL_EXPOSURE_RATIO,
                    help="cap total open gross exposure as a fraction of initial capital; default 0.67")
    ap.add_argument("--profile", default="v5")
    ap.add_argument("--allow-additional", action="store_true",
                    help="allow additional auto buys for the same date after an earlier paper-record")
    a = ap.parse_args()
    if not SNAP.exists():
        print("no snapshots; run live_recommend first"); return
    snaps = [json.loads(l) for l in open(SNAP, encoding="utf-8") if l.strip()]
    day_live = [r for r in snaps if r.get("date") == a.date and r.get("is_live")]
    latest_capture = max((str(r.get("captured_at") or "") for r in day_live), default="")
    picks = [
        r for r in day_live
        if str(r.get("captured_at") or "") == latest_capture and r.get(a.pick)
    ]
    if not picks:
        print(f"{a.date}: no live {a.pick} picks to paper-record (is_live snapshot required)"); return
    account = _load_account(a.initial_capital, a.fee_rate)
    fee_rate = float(account.get("fee_rate", a.fee_rate))
    existing = set()
    open_codes = set()
    existing_auto_for_date = 0
    if POS.exists():
        for l in open(POS, encoding="utf-8"):
            try:
                r = json.loads(l)
                existing.add((r.get("entry_date"), r.get("code")))
                if r.get("status", "open") == "open":
                    open_codes.add(r.get("code"))
                if r.get("entry_date") == a.date and r.get("source") == f"auto:{a.pick}":
                    existing_auto_for_date += 1
            except Exception:
                pass
    if existing_auto_for_date and not a.allow_additional:
        print(
            f"{a.date}: already paper-recorded {existing_auto_for_date} auto {a.pick} "
            "position(s); skip additional buys"
        )
        return
    buyable = [
        r for r in picks
        if (a.date, r.get("code")) not in existing
        and r.get("code") not in open_codes
        and r.get("open")
    ]
    if not buyable:
        print(
            f"{a.date}: no new buyable {a.pick} picks "
            f"(cash={float(account.get('cash', 0.0)):.2f})"
        )
        return
    cash = float(account.get("cash", 0.0))
    deploy_ratio = float(a.deploy_ratio)
    if not (0 < deploy_ratio <= 1):
        raise SystemExit("--deploy-ratio must be in (0, 1]")
    max_total_exposure_ratio = float(a.max_total_exposure_ratio)
    if not (0 < max_total_exposure_ratio <= 1):
        raise SystemExit("--max-total-exposure-ratio must be in (0, 1]")
    current_open_cost = 0.0
    for l in _load_positions_from_file(POS):
        if l.get("status", "open") == "open":
            current_open_cost += float(l.get("gross_notional") or 0.0)
    exposure_budget = max(
        0.0,
        float(account.get("initial_capital", a.initial_capital)) * max_total_exposure_ratio - current_open_cost,
    )
    deployable_cash = (
        cash if a.notional is not None
        else min(cash * deploy_ratio, exposure_budget)
    )
    if deployable_cash <= 0:
        print(
            f"{a.date}: exposure budget exhausted for {a.pick} "
            f"(cash={cash:.2f}, open_cost={current_open_cost:.2f}, "
            f"max_total_exposure_ratio={max_total_exposure_ratio:.0%})"
        )
        return
    target_notional = a.notional if a.notional is not None else deployable_cash / len(buyable)
    POS.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    run_fees = 0.0
    with POS.open("a", encoding="utf-8") as fh:
        for r in buyable:
            key = (a.date, r["code"])
            if key in existing:
                continue
            px, fill_basis, basket_rule = _fill_price(r)
            if not px:
                continue
            px = float(px)
            affordable_notional = min(target_notional, cash)
            shares = int((affordable_notional / (px * (1 + fee_rate))) / 100) * 100
            if shares < 100:
                continue
            gross_notional = round(shares * px, 2)
            entry_fee = round(gross_notional * fee_rate, 2)
            entry_cash_out = round(gross_notional + entry_fee, 2)
            if entry_cash_out > cash + 1e-6:
                continue
            cash = round(cash - entry_cash_out, 2)
            fh.write(json.dumps({
                "code": r["code"], "name": r.get("name", ""), "entry_date": a.date,
                "entry_price": round(px, 3), "profile": a.profile, "shares": shares,
                "mode": r.get("mode"), "flags": r.get("flags"),
                "xcjw": r.get("xcjw"), "cjs": r.get("cjs"), "jsjl": r.get("jsjl"),
                "gross_notional": gross_notional, "entry_fee": entry_fee,
                "entry_cash_out": entry_cash_out,
                "entry_price_basis": fill_basis,
                "basket_price": round(float(r["basket_price"]), 3) if r.get("basket_price") else None,
                "basket_rule": basket_rule,
                "initial_capital": round(float(account.get("initial_capital", a.initial_capital)), 2),
                "fee_rate": fee_rate,
                "allocation_rule": (
                    f"rolling_cash_equal_weight_{deploy_ratio:.0%}"
                    f"_cap_{max_total_exposure_ratio:.0%}"
                ),
                "status": "open", "source": f"auto:{a.pick}",
            }, ensure_ascii=False) + "\n")
            _append_trade({
                "ts": _now_iso(), "date": a.date, "side": "BUY", "code": r["code"],
                "name": r.get("name", ""), "price": round(px, 3), "shares": shares,
                "gross_notional": gross_notional, "fee": entry_fee,
                "cash_after": cash, "source": f"auto:{a.pick}", "price_basis": fill_basis,
            })
            run_fees = round(run_fees + entry_fee, 2)
            n += 1
    account["cash"] = cash
    account["fee_rate"] = fee_rate
    account["last_buy_date"] = a.date
    account["total_fees"] = round(float(account.get("total_fees", 0.0)) + run_fees, 2)
    _save_account(account)
    print(
        f"{a.date}: paper-recorded {n} {a.pick} positions -> {POS} "
        f"(rolling_cash_after={cash:.2f}, fee_rate={fee_rate:.4%}, "
        f"deploy_ratio={deploy_ratio:.0%}, exposure_budget={exposure_budget:.2f}, "
        f"target_notional={target_notional:.2f}/position)"
    )


def _load_positions_from_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


if __name__ == "__main__":
    main()
