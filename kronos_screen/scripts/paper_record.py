"""Record the day's ★B (live K->P + auction) picks as paper positions so
live_monitor.py can track them under the v5 rule. Idempotent per (date, code).

For pre-open/auction decisions, `basket_price` is a limit cap, not an automatic
fill. The paper fill waits for the first opening minutes, then uses the best
reachable print inside that window capped by `basket_price`.
Reads output/live/signal_snapshots.jsonl; appends to output/live/positions.jsonl.
"""
from __future__ import annotations
import argparse, json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.client import XiaocaoClient  # noqa: E402

SNAP = Path("output/live/signal_snapshots.jsonl")
POS = Path("output/live/positions.jsonl")
ACCOUNT = Path("output/live/paper_account.json")
TRADES = Path("output/live/paper_trades.jsonl")
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001
DEFAULT_DEPLOY_RATIO = 0.5
DEFAULT_MAX_TOTAL_EXPOSURE_RATIO = 0.67
A_SHARE_TZ = ZoneInfo("Asia/Shanghai")


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


def _num(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_hhmm(value: str) -> tuple[int, int]:
    text = str(value).strip().replace(":", "")
    if len(text) < 4 or not text[:4].isdigit():
        raise ValueError(f"invalid HHMM time: {value!r}")
    hour = int(text[:2])
    minute = int(text[2:4])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid HHMM time: {value!r}")
    return hour, minute


def _validate_fill_window(start_hhmm: str, end_hhmm: str) -> None:
    if _minute_key(end_hhmm) < _minute_key(start_hhmm):
        raise ValueError("--fill-window-end must be >= --fill-window-start")


def _minute_key(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:4]


def _wait_until_fill_window_complete(date_iso: str, end_hhmm: str, settle_seconds: int) -> None:
    today = datetime.now(A_SHARE_TZ).date().isoformat()
    if date_iso != today:
        return
    hour, minute = _parse_hhmm(end_hhmm)
    target = datetime.fromisoformat(date_iso).replace(
        hour=hour, minute=minute, second=0, microsecond=0, tzinfo=A_SHARE_TZ
    )
    target = target + timedelta(minutes=1, seconds=max(0, settle_seconds))
    now = datetime.now(A_SHARE_TZ)
    if now < target:
        wait_seconds = (target - now).total_seconds()
        print(
            f"{date_iso}: waiting {wait_seconds:.0f}s for opening fill window "
            f"through {end_hhmm} to settle"
        )
        time.sleep(wait_seconds)


def _fill_window_high(
    client: XiaocaoClient,
    code: str,
    date_iso: str,
    *,
    start_hhmm: str,
    end_hhmm: str,
) -> tuple[float | None, str | None]:
    try:
        rows = client.minute_line(
            code,
            "1min",
            "bfq",
            trade_date=date_iso.replace("-", ""),
            count=241,
        )
    except Exception:
        return None, None
    if not isinstance(rows, list):
        return None, None
    start_key = _minute_key(start_hhmm)
    end_key = _minute_key(end_hhmm)
    best: float | None = None
    best_time: str | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        trade_time = _minute_key(row.get("tradeTime"))
        if not trade_time or trade_time < start_key or trade_time > end_key:
            continue
        price = _num(row.get("high"))
        if price is None or price <= 0:
            price = _num(row.get("trade"))
        if price is None or price <= 0:
            continue
        if best is None or price > best:
            best = price
            best_time = trade_time
    return best, best_time


def _fill_price_from_window(
    record: dict,
    *,
    window_high: float | None,
    window_time: str | None,
) -> tuple[float | None, str, str | None, dict]:
    basket_px = _num(record.get("basket_price"))
    open_px = _num(record.get("open"))
    metadata: dict[str, object] = {}
    if window_high is not None and window_high > 0:
        metadata["fill_window_high"] = round(window_high, 4)
        if window_time:
            metadata["fill_window_time"] = window_time
        if basket_px is not None and basket_px > 0:
            return (
                min(window_high, basket_px),
                "opening_window_capped_by_basket",
                record.get("basket_rule"),
                metadata,
            )
        return window_high, "opening_window_high", None, metadata
    if basket_px is not None and basket_px > 0:
        metadata["fill_fallback"] = "basket_no_window_data"
        return basket_px, "basket_fallback", record.get("basket_rule"), metadata
    return open_px, "open_fallback", None, metadata


def _fill_price(record: dict) -> tuple[float | None, str, str | None]:
    precomputed = record.get("_paper_fill")
    if isinstance(precomputed, dict):
        return (
            _num(precomputed.get("price")),
            str(precomputed.get("basis") or "opening_window_capped_by_basket"),
            precomputed.get("basket_rule"),
        )
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


def _attach_fill_prices(
    client: XiaocaoClient,
    picks: list[dict],
    date_iso: str,
    *,
    start_hhmm: str,
    end_hhmm: str,
) -> list[dict]:
    out: list[dict] = []
    for record in picks:
        code = str(record.get("code") or "")
        window_high, window_time = _fill_window_high(
            client,
            code,
            date_iso,
            start_hhmm=start_hhmm,
            end_hhmm=end_hhmm,
        )
        price, basis, basket_rule, metadata = _fill_price_from_window(
            record,
            window_high=window_high,
            window_time=window_time,
        )
        enriched = dict(record)
        enriched["_paper_fill"] = {
            "price": price,
            "basis": basis,
            "basket_rule": basket_rule,
            **metadata,
        }
        out.append(enriched)
    return out


def _board_lot_cost(price: float, fee_rate: float) -> float:
    gross_notional = 100.0 * price
    entry_fee = round(gross_notional * fee_rate, 2)
    return round(gross_notional + entry_fee, 2)


def _filter_affordable_equal_weight(
    picks: list[dict],
    deployable_cash: float,
    cash: float,
    fee_rate: float,
) -> tuple[list[dict], float]:
    remaining = list(picks)
    while remaining:
        target_notional = deployable_cash / len(remaining)
        filtered: list[dict] = []
        for record in remaining:
            px, _, _ = _fill_price(record)
            if not px:
                continue
            min_lot_cost = _board_lot_cost(float(px), fee_rate)
            if min_lot_cost <= min(target_notional, cash):
                filtered.append(record)
        if len(filtered) == len(remaining):
            return filtered, target_notional
        remaining = filtered
    return [], 0.0


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
    ap.add_argument("--fill-window-start", default="0930",
                    help="opening execution window start, HHMM; default 0930")
    ap.add_argument("--fill-window-end", default="0931",
                    help="opening execution window end, HHMM; default 0931")
    ap.add_argument("--fill-settle-seconds", type=int, default=5,
                    help="seconds after the next minute to wait before reading the end bar")
    ap.add_argument("--no-wait-fill-window", action="store_true",
                    help="do not wait for the opening fill window to complete")
    a = ap.parse_args()
    _parse_hhmm(a.fill_window_start)
    _parse_hhmm(a.fill_window_end)
    _validate_fill_window(a.fill_window_start, a.fill_window_end)
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
    if not a.no_wait_fill_window:
        _wait_until_fill_window_complete(a.date, a.fill_window_end, a.fill_settle_seconds)
    client = XiaocaoClient()
    buyable = _attach_fill_prices(
        client,
        buyable,
        a.date,
        start_hhmm=a.fill_window_start,
        end_hhmm=a.fill_window_end,
    )
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
    if a.notional is not None:
        eligible_buyable = list(buyable)
        target_notional = a.notional
    else:
        eligible_buyable, target_notional = _filter_affordable_equal_weight(
            buyable, deployable_cash, cash, fee_rate
        )
    if not eligible_buyable or target_notional <= 0:
        print(
            f"{a.date}: no affordable {a.pick} picks after board-lot filter "
            f"(cash={cash:.2f}, deployable={deployable_cash:.2f})"
        )
        return
    POS.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    run_fees = 0.0
    with POS.open("a", encoding="utf-8") as fh:
        for r in eligible_buyable:
            key = (a.date, r["code"])
            if key in existing:
                continue
            px, fill_basis, basket_rule = _fill_price(r)
            if not px:
                continue
            fill_meta = r.get("_paper_fill") if isinstance(r.get("_paper_fill"), dict) else {}
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
                "fill_window_start": a.fill_window_start,
                "fill_window_end": a.fill_window_end,
                "fill_window_high": fill_meta.get("fill_window_high"),
                "fill_window_time": fill_meta.get("fill_window_time"),
                "fill_fallback": fill_meta.get("fill_fallback"),
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
                "fill_window_start": a.fill_window_start,
                "fill_window_end": a.fill_window_end,
                "fill_window_high": fill_meta.get("fill_window_high"),
            })
            run_fees = round(run_fees + entry_fee, 2)
            n += 1
    if n == 0:
        print(
            f"{a.date}: no {a.pick} positions recorded after fill/sizing checks "
            f"(cash={cash:.2f}, target_notional={target_notional:.2f})"
        )
        return
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
