"""Record the day's ★B (live K->P + auction) picks as paper positions so
live_monitor.py can track them under the v5 rule. Idempotent per (date, code).

Fill model (realistic, not worst-case): a paper limit order at
L = min(open x (1 + limit premium), basket_price). After the opening window
settles, fill at min(window VWAP, L); if the window never trades through L the
pick is SKIPPED (audited in output/live/paper_skips.jsonl). basket_price is the
abandon bound only — never the fill assumption (the old behaviour booked every
fill at the +2% chase cap, costing ~1.9%/trade of fictitious slippage).
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
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from xiaocao.api.client import XiaocaoClient  # noqa: E402
from quality_governor import annotate_quality_governor, ensure_quality_fields  # noqa: E402

SNAP = Path("output/live/signal_snapshots.jsonl")
POS = Path("output/live/positions.jsonl")
ACCOUNT = Path("output/live/paper_account.json")
ACCOUNT_A = Path("output/live/paper_account_A.json")
TRADES = Path("output/live/paper_trades.jsonl")
SKIPS = Path("output/live/paper_skips.jsonl")
QUALITY_AUDIT = Path("output/live/quality_governor_audit.jsonl")
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001
DEFAULT_DEPLOY_RATIO = 0.5
DEFAULT_MAX_TOTAL_EXPOSURE_RATIO = 0.67
A_SHARE_TZ = ZoneInfo("Asia/Shanghai")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_account(initial_capital: float, fee_rate: float, path: Path = ACCOUNT) -> dict:
    if path.exists():
        with path.open(encoding="utf-8") as f:
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


def _save_account(account: dict, path: Path = ACCOUNT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    account["updated_at"] = _now_iso()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def _append_trade(record: dict) -> None:
    TRADES.parent.mkdir(parents=True, exist_ok=True)
    with TRADES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _append_skip(record: dict) -> None:
    SKIPS.parent.mkdir(parents=True, exist_ok=True)
    with SKIPS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _append_quality_audit(records: list[dict]) -> None:
    if not records:
        return
    if all(str(r.get("quality_governor_mode") or "off") == "off" for r in records):
        return
    QUALITY_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with QUALITY_AUDIT.open("a", encoding="utf-8") as f:
        for record in records:
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


def _fill_window_stats(
    client: XiaocaoClient,
    code: str,
    date_iso: str,
    *,
    start_hhmm: str,
    end_hhmm: str,
) -> dict | None:
    """VWAP / low / high of the opening fill window from 1-min bars.
    VWAP is the realistic small-order fill; window high systematically
    overstates the cost (it was the prior fill assumption)."""
    try:
        rows = client.minute_line(
            code,
            "1min",
            "bfq",
            trade_date=date_iso.replace("-", ""),
            count=241,
        )
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    start_key = _minute_key(start_hhmm)
    end_key = _minute_key(end_hhmm)
    amt = vol = 0.0
    closes: list[float] = []
    lo: float | None = None
    hi: float | None = None
    last_time: str | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        trade_time = _minute_key(row.get("tradeTime"))
        if not trade_time or trade_time < start_key or trade_time > end_key:
            continue
        c = _num(row.get("close")) or _num(row.get("trade"))
        h = _num(row.get("high")) or c
        l = _num(row.get("low")) or c
        if not c or c <= 0:
            continue
        closes.append(c)
        if h and h > 0:
            hi = h if hi is None else max(hi, h)
        if l and l > 0:
            lo = l if lo is None else min(lo, l)
        a, v = _num(row.get("amt")), _num(row.get("vol"))
        if a and v and a > 0 and v > 0:
            amt += a
            vol += v
        last_time = trade_time
    if not closes:
        return None
    vwap = amt / vol if vol > 0 else sum(closes) / len(closes)
    return {"vwap": vwap, "low": lo, "high": hi, "time": last_time}


def _fill_price_from_window(
    record: dict,
    *,
    window: dict | None,
    limit_premium_pct: float,
) -> tuple[float | None, str, str | None, dict]:
    """Realistic paper fill: a limit order at L = min(open x (1+premium), basket).
    - window low > L  -> limit never reached -> SKIP (price None).
    - else fill at min(window VWAP, L)  (limit fills at L or better).
    - no window data  -> fall back to L anchored on open (never the basket cap).
    basket remains only the abandon bound, NOT the fill assumption."""
    basket_px = _num(record.get("basket_price"))
    open_px = _num(record.get("open"))
    metadata: dict[str, object] = {}
    limit_px: float | None = None
    if open_px and open_px > 0:
        limit_px = open_px * (1 + limit_premium_pct / 100)
        if basket_px and basket_px > 0:
            limit_px = min(limit_px, basket_px)
        metadata["fill_limit_price"] = round(limit_px, 4)
        metadata["fill_limit_premium_pct"] = limit_premium_pct
    if window:
        if window.get("high"):
            metadata["fill_window_high"] = round(float(window["high"]), 4)
        if window.get("low"):
            metadata["fill_window_low"] = round(float(window["low"]), 4)
        metadata["fill_window_vwap"] = round(float(window["vwap"]), 4)
        if window.get("time"):
            metadata["fill_window_time"] = window["time"]
        if limit_px is None:
            return float(window["vwap"]), "opening_window_vwap", None, metadata
        lo = _num(window.get("low"))
        if lo is not None and lo > limit_px:
            metadata["skip_reason"] = "LIMIT_NOT_REACHED"
            return None, "skipped_limit_not_reached", record.get("basket_rule"), metadata
        return (
            min(float(window["vwap"]), limit_px),
            "opening_window_vwap_capped_by_limit",
            record.get("basket_rule"),
            metadata,
        )
    if limit_px is not None:
        metadata["fill_fallback"] = "limit_no_window_data"
        return limit_px, "limit_fallback", record.get("basket_rule"), metadata
    if basket_px is not None and basket_px > 0:
        metadata["fill_fallback"] = "basket_no_window_no_open"
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
    limit_premium_pct: float,
) -> tuple[list[dict], list[dict]]:
    """Returns (fillable, skipped). Skipped picks (limit never reached) are
    surfaced for audit, never silently dropped."""
    out: list[dict] = []
    skipped: list[dict] = []
    for record in picks:
        code = str(record.get("code") or "")
        window = _fill_window_stats(
            client,
            code,
            date_iso,
            start_hhmm=start_hhmm,
            end_hhmm=end_hhmm,
        )
        price, basis, basket_rule, metadata = _fill_price_from_window(
            record,
            window=window,
            limit_premium_pct=limit_premium_pct,
        )
        enriched = dict(record)
        enriched["_paper_fill"] = {
            "price": price,
            "basis": basis,
            "basket_rule": basket_rule,
            **metadata,
        }
        if price is None and metadata.get("skip_reason"):
            skipped.append(enriched)
        else:
            out.append(enriched)
    return out, skipped


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


def _filter_affordable_fixed_slot(
    picks: list[dict],
    target_notional: float,
    cash: float,
    fee_rate: float,
) -> list[dict]:
    """Affordability check for quality-governor ON.

    The target_notional is derived from the original slot count. We do not
    reallocate cash from filtered weak slots into the remaining names.
    """
    out: list[dict] = []
    for record in picks:
        px, _, _ = _fill_price(record)
        if not px:
            continue
        min_lot_cost = _board_lot_cost(float(px), fee_rate)
        if min_lot_cost <= min(target_notional, cash):
            out.append(record)
    return out


def _quality_governor_buyable(
    picks: list[dict],
    mode: str,
) -> tuple[list[dict], list[dict], int]:
    annotated = [annotate_quality_governor(p, mode) for p in picks]
    slot_count = len(annotated)
    if mode == "on":
        active = [p for p in annotated if float(p.get("quality_slot_weight") or 0.0) > 0.0]
    else:
        active = list(annotated)
    return annotated, active, slot_count


def _quality_audit_records(
    *,
    date_iso: str,
    pick: str,
    mode: str,
    candidates: list[dict],
    actual_buy_codes: set[str],
    slot_count: int,
    deployable_cash: float,
    target_notional: float,
) -> list[dict]:
    rows: list[dict] = []
    for r in candidates:
        code = str(r.get("code") or "")
        rows.append({
            "ts": _now_iso(),
            "date": date_iso,
            "source": f"auto:{pick}",
            "quality_governor_mode": mode,
            "code": code,
            "name": r.get("name"),
            "mode": r.get("mode"),
            "primary_score": r.get("primary_score"),
            "primary_score_label": r.get("primary_score_label"),
            "p_score": r.get("p_score"),
            "quality_tag": r.get("quality_tag"),
            "shadow_action": r.get("quality_governor_action"),
            "shadow_reason": r.get("quality_governor_reason"),
            "quality_slot_weight": r.get("quality_slot_weight"),
            "actual_action": "BUY" if code in actual_buy_codes else "CASH_SLOT",
            "slot_count": slot_count,
            "deployable_cash": round(deployable_cash, 2),
            "target_notional": round(target_notional, 2),
            "slot_cash_sizing": True,
            "no_reallocation_from_filtered_slots": mode == "on",
        })
    return rows


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
    ap.add_argument("--limit-premium-pct", type=float, default=0.5,
                    help="paper limit order premium over the 9:25 open reference, in %%; "
                         "fill = min(window VWAP, open x (1+premium)) or SKIP if the "
                         "window never trades through the limit; default 0.5")
    ap.add_argument("--fill-settle-seconds", type=int, default=5,
                    help="seconds after the next minute to wait before reading the end bar")
    ap.add_argument("--no-wait-fill-window", action="store_true",
                    help="do not wait for the opening fill window to complete")
    ap.add_argument("--no-book-a", action="store_true",
                    help="skip the book-A (validated open->next-close reference) recording")
    ap.add_argument("--quality-governor", choices=["off", "shadow", "on"], default="off",
                    help="quality governor mode: off=ignore, shadow=audit only, "
                         "on=leave weak-primary slots in cash without reallocating")
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
        ensure_quality_fields(r) for r in day_live
        if str(r.get("captured_at") or "") == latest_capture and r.get(a.pick)
    ]
    if not picks:
        print(f"{a.date}: no live {a.pick} picks to paper-record (is_live snapshot required)"); return
    account = _load_account(a.initial_capital, a.fee_rate)
    fee_rate = float(account.get("fee_rate", a.fee_rate))
    if not a.no_book_a:
        _record_book_a(picks, a, fee_rate)
    existing = set()
    open_codes = set()
    existing_auto_for_date = 0
    if POS.exists():
        for l in open(POS, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("book", "B") != "B":
                    continue  # book A entries never block / get blocked by book B
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
        annotate_quality_governor(r, a.quality_governor) for r in picks
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
    buyable, skipped = _attach_fill_prices(
        client,
        buyable,
        a.date,
        start_hhmm=a.fill_window_start,
        end_hhmm=a.fill_window_end,
        limit_premium_pct=a.limit_premium_pct,
    )
    for r in skipped:
        meta = r.get("_paper_fill") or {}
        print(
            f"{a.date}: SKIP {r.get('code')} {r.get('name')} — "
            f"{meta.get('skip_reason')} (limit {meta.get('fill_limit_price')}, "
            f"window low {meta.get('fill_window_low')})"
        )
        _append_skip({
            "ts": _now_iso(), "date": a.date, "code": r.get("code"),
            "name": r.get("name"), "source": f"auto:{a.pick}",
            "reason": meta.get("skip_reason"),
            "limit_price": meta.get("fill_limit_price"),
            "window_low": meta.get("fill_window_low"),
            "window_vwap": meta.get("fill_window_vwap"),
            "basket_price": r.get("basket_price"), "open": r.get("open"),
            "primary_score": r.get("primary_score"),
            "p_score": r.get("p_score"),
            "quality_tag": r.get("quality_tag"),
            "quality_governor_mode": a.quality_governor,
        })
    if not buyable:
        print(f"{a.date}: all {a.pick} picks skipped (limit not reached)")
        return
    cash = float(account.get("cash", 0.0))
    deploy_ratio = float(a.deploy_ratio)
    if not (0 < deploy_ratio <= 1):
        raise SystemExit("--deploy-ratio must be in (0, 1]")
    ks_factor, ks_reason = _kill_switch_factor()
    print(f"{a.date}: kill-switch — {ks_reason} (deploy factor {ks_factor:.1f})")
    if ks_factor <= 0:
        print(f"{a.date}: book B buys PAUSED by kill-switch; data capture & book A continue")
        return
    deploy_ratio = deploy_ratio * ks_factor
    max_total_exposure_ratio = float(a.max_total_exposure_ratio)
    if not (0 < max_total_exposure_ratio <= 1):
        raise SystemExit("--max-total-exposure-ratio must be in (0, 1]")
    current_open_cost = 0.0
    for l in _load_positions_from_file(POS):
        if l.get("book", "B") == "B" and l.get("status", "open") == "open":
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
    quality_candidates, quality_buyable, quality_slot_count = _quality_governor_buyable(
        buyable,
        a.quality_governor,
    )
    if a.quality_governor == "on" and not quality_buyable:
        target_notional = deployable_cash / max(quality_slot_count, 1)
        _append_quality_audit(_quality_audit_records(
            date_iso=a.date,
            pick=a.pick,
            mode=a.quality_governor,
            candidates=quality_candidates,
            actual_buy_codes=set(),
            slot_count=quality_slot_count,
            deployable_cash=deployable_cash,
            target_notional=target_notional,
        ))
        print(f"{a.date}: quality-governor ON left all {a.pick} slots in cash")
        return
    if a.notional is not None:
        eligible_buyable = list(quality_buyable)
        target_notional = a.notional
    elif a.quality_governor == "on":
        target_notional = deployable_cash / max(quality_slot_count, 1)
        eligible_buyable = _filter_affordable_fixed_slot(
            quality_buyable,
            target_notional,
            cash,
            fee_rate,
        )
    else:
        eligible_buyable, target_notional = _filter_affordable_equal_weight(
            quality_buyable, deployable_cash, cash, fee_rate
        )
    _append_quality_audit(_quality_audit_records(
        date_iso=a.date,
        pick=a.pick,
        mode=a.quality_governor,
        candidates=quality_candidates,
        actual_buy_codes={str(r.get("code") or "") for r in eligible_buyable},
        slot_count=quality_slot_count,
        deployable_cash=deployable_cash,
        target_notional=target_notional,
    ))
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
                "book": "B",
                "code": r["code"], "name": r.get("name", ""), "entry_date": a.date,
                "entry_price": round(px, 3), "profile": a.profile, "shares": shares,
                "mode": r.get("mode"), "flags": r.get("flags"),
                "xcjw": r.get("xcjw"), "cjs": r.get("cjs"), "jsjl": r.get("jsjl"),
                "primary_score": r.get("primary_score"),
                "primary_score_label": r.get("primary_score_label"),
                "rank_score": r.get("rank_score"),
                "mode_confidence": r.get("mode_confidence"),
                "p_score": r.get("p_score"),
                "quality_tag": r.get("quality_tag"),
                "quality_governor_mode": a.quality_governor,
                "quality_governor_action": r.get("quality_governor_action"),
                "quality_governor_reason": r.get("quality_governor_reason"),
                "quality_slot_weight": r.get("quality_slot_weight"),
                "gross_notional": gross_notional, "entry_fee": entry_fee,
                "entry_cash_out": entry_cash_out,
                "entry_price_basis": fill_basis,
                "fill_window_start": a.fill_window_start,
                "fill_window_end": a.fill_window_end,
                "fill_window_high": fill_meta.get("fill_window_high"),
                "fill_window_low": fill_meta.get("fill_window_low"),
                "fill_window_vwap": fill_meta.get("fill_window_vwap"),
                "fill_limit_price": fill_meta.get("fill_limit_price"),
                "fill_window_time": fill_meta.get("fill_window_time"),
                "fill_fallback": fill_meta.get("fill_fallback"),
                "basket_price": round(float(r["basket_price"]), 3) if r.get("basket_price") else None,
                "basket_rule": basket_rule,
                "initial_capital": round(float(account.get("initial_capital", a.initial_capital)), 2),
                "fee_rate": fee_rate,
                "allocation_rule": (
                    f"rolling_cash_equal_weight_{deploy_ratio:.0%}"
                    f"_cap_{max_total_exposure_ratio:.0%}"
                    f"_quality_{a.quality_governor}"
                ),
                "status": "open", "source": f"auto:{a.pick}",
            }, ensure_ascii=False) + "\n")
            _append_trade({
                "ts": _now_iso(), "date": a.date, "side": "BUY", "code": r["code"],
                "name": r.get("name", ""), "price": round(px, 3), "shares": shares,
                "gross_notional": gross_notional, "fee": entry_fee,
                "cash_after": cash, "source": f"auto:{a.pick}", "price_basis": fill_basis,
                "primary_score": r.get("primary_score"),
                "p_score": r.get("p_score"),
                "quality_tag": r.get("quality_tag"),
                "quality_governor_mode": a.quality_governor,
                "fill_window_start": a.fill_window_start,
                "fill_window_end": a.fill_window_end,
                "fill_window_high": fill_meta.get("fill_window_high"),
                "fill_window_vwap": fill_meta.get("fill_window_vwap"),
                "fill_limit_price": fill_meta.get("fill_limit_price"),
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
        f"target_notional={target_notional:.2f}/position, "
        f"quality_governor={a.quality_governor})"
    )


def _kill_switch_factor() -> tuple[float, str]:
    """Deploy throttle from book A (the validated reference policy): when even
    the no-stop next-close book is bleeding, the tape is bad — cut book B's
    deploy. Sensor stays alive: book A keeps recording regardless (it is
    virtual), only book B buying is throttled.
      last 5 exit-days cum return < -5%  -> factor 0   (pause B buys)
      last 5 exit-days cum return < -3%  -> factor 0.5 (halve deploy)
    Backtested index/regime gates all failed train+test consistency
    (backtest_deploy_gate.py), so performance of the validated book is the
    only deploy control."""
    closed = [
        p for p in _load_positions_from_file(POS)
        if p.get("book") == "A" and p.get("status") == "closed"
        and p.get("exit_date") and p.get("entry_cash_out")
    ]
    if not closed:
        return 1.0, "book A has no closed trades yet"
    exit_days = sorted({p["exit_date"] for p in closed})[-5:]
    window = [p for p in closed if p["exit_date"] in exit_days]
    cash_out = sum(float(p["entry_cash_out"]) for p in window)
    pnl = sum(float(p.get("realized_pnl") or 0.0) for p in window)
    cum = pnl / cash_out * 100 if cash_out > 0 else 0.0
    desc = f"book A last {len(exit_days)} exit-day(s) cum {cum:+.2f}%"
    if cum < -5.0:
        return 0.0, f"KILL-SWITCH PAUSE: {desc} < -5%"
    if cum < -3.0:
        return 0.5, f"KILL-SWITCH HALVE: {desc} < -3%"
    return 1.0, desc


def _record_book_a(picks: list[dict], a, fee_rate: float) -> None:
    """Book A = the VALIDATED reference policy: buy at the open reference,
    sell at next close, no stop. Pure accounting book (settled by
    settle_book_a.py at eod) — never monitored or stop-managed. Lets the
    forward record answer directly whether the stop layer (book B) helps or
    hurts vs the only backtested exit."""
    account = _load_account(a.initial_capital, fee_rate, path=ACCOUNT_A)
    existing = set()
    open_codes = set()
    for r in _load_positions_from_file(POS):
        if r.get("book", "B") != "A":
            continue
        existing.add((r.get("entry_date"), r.get("code")))
        if r.get("status", "open") == "open":
            open_codes.add(r.get("code"))
    buyable = []
    for r in picks:
        if (a.date, r.get("code")) in existing or r.get("code") in open_codes:
            continue
        if not _num(r.get("open")):
            continue
        buyable.append(r)
    if not buyable:
        print(f"{a.date}: book A — no new buyable picks")
        return
    cash = float(account.get("cash", 0.0))
    deployable = cash * float(a.deploy_ratio)
    target = deployable / len(buyable)
    n = 0
    with POS.open("a", encoding="utf-8") as fh:
        for r in buyable:
            px = float(_num(r.get("open")))
            shares = int((min(target, cash) / (px * (1 + fee_rate))) / 100) * 100
            if shares < 100:
                continue
            gross = round(shares * px, 2)
            fee = round(gross * fee_rate, 2)
            cash_out = round(gross + fee, 2)
            if cash_out > cash + 1e-6:
                continue
            cash = round(cash - cash_out, 2)
            fh.write(json.dumps({
                "book": "A",
                "code": r["code"], "name": r.get("name", ""), "entry_date": a.date,
                "entry_price": round(px, 3), "profile": "v5_nextclose", "shares": shares,
                "mode": r.get("mode"),
                "gross_notional": gross, "entry_fee": fee, "entry_cash_out": cash_out,
                "entry_price_basis": "open_reference",
                "fee_rate": fee_rate,
                "initial_capital": round(float(account.get("initial_capital", a.initial_capital)), 2),
                "status": "open", "source": f"auto:{a.pick}:bookA",
            }, ensure_ascii=False) + "\n")
            _append_trade({
                "ts": _now_iso(), "date": a.date, "side": "BUY", "book": "A",
                "code": r["code"], "name": r.get("name", ""), "price": round(px, 3),
                "shares": shares, "gross_notional": gross, "fee": fee,
                "cash_after": cash, "source": f"auto:{a.pick}:bookA",
                "price_basis": "open_reference",
            })
            n += 1
    if n:
        account["cash"] = cash
        account["fee_rate"] = fee_rate
        account["last_buy_date"] = a.date
        _save_account(account, path=ACCOUNT_A)
    print(f"{a.date}: book A recorded {n} position(s) at open reference (cash_A={cash:.2f})")


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
