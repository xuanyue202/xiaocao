"""Record the day's ★B (live K->P + auction) picks as paper positions so
live_monitor.py can track them under the v5 rule. Idempotent per (date, code).

Fill model (realistic, not worst-case): a paper limit order at
L = min(open x (1 + limit premium), basket_price). After the opening window
settles, fill at min(window VWAP, L) if the window trades through L. If the
initial low limit is not filled or would be rejected as too far from the tape,
paper_record checks the latest opening-window price as the real-time retry
proxy; when that price is still within the basket abandon bound, it buys at
that real-time price and audits the retry. basket_price is the abandon bound
only — never the fill assumption (the old behaviour booked every fill at the
+2% chase cap, costing ~1.9%/trade of fictitious slippage).
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
from xiaocao.live import accounts  # noqa: E402
from xiaocao.strategy.params import (  # noqa: E402
    TREND_BUDGET_RATIO,
    TREND_REBALANCE_R,
    TREND_TOP_M,
    TREND_TRAIL_DD,
)
from xiaocao.strategy.trend_rules import classify_trend_alignment, generate_trend_picks  # noqa: E402
from quality_governor import annotate_quality_governor, ensure_quality_fields  # noqa: E402

SNAP = Path("output/live/signal_snapshots.jsonl")
POS = Path("output/live/positions.jsonl")
ACCOUNT = Path("output/live/paper_account.json")
ACCOUNT_A = Path("output/live/paper_account_A.json")
ACCOUNT_T = Path("output/live/paper_account_T.json")
TRADES = Path("output/live/paper_trades.jsonl")
SKIPS = Path("output/live/paper_skips.jsonl")
QUALITY_AUDIT = Path("output/live/quality_governor_audit.jsonl")
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001
DEFAULT_DEPLOY_RATIO = 0.5
DEFAULT_MAX_TOTAL_EXPOSURE_RATIO = 0.67
DEFAULT_TREND_MAX_EXPOSURE_RATIO = 1.0
A_SHARE_TZ = ZoneInfo("Asia/Shanghai")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Account/position I/O is the shared real-money SSOT in xiaocao.live.accounts
# (also used by live_monitor); these thin wrappers bind it to this script's paths.
def _load_account(initial_capital: float, fee_rate: float, path: Path = ACCOUNT) -> dict:
    return accounts.load_account(path, initial_capital, fee_rate)


def _save_account(account: dict, path: Path = ACCOUNT) -> None:
    accounts.save_account(account, path)


def _append_trade(record: dict) -> None:
    accounts.append_jsonl(record, TRADES)


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
    return {"vwap": vwap, "low": lo, "high": hi, "last": closes[-1], "time": last_time}


def _fill_price_from_window(
    record: dict,
    *,
    window: dict | None,
    limit_premium_pct: float,
) -> tuple[float | None, str, str | None, dict]:
    """Realistic paper fill with an order-status retry.

    First submit a limit order at L = min(open x (1+premium), basket).
    - window low <= L -> fill at min(window VWAP, L) (limit fills at L or better).
    - window low > L  -> initial limit did not fill / may be blocked. Check the
      latest window price as a real-time retry proxy; if it is still <= basket,
      buy at that real-time price, otherwise SKIP.
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
        if window.get("last"):
            metadata["fill_window_last"] = round(float(window["last"]), 4)
        if window.get("time"):
            metadata["fill_window_time"] = window["time"]
        if limit_px is None:
            return float(window["vwap"]), "opening_window_vwap", None, metadata
        lo = _num(window.get("low"))
        if lo is not None and lo > limit_px:
            realtime_px = _num(window.get("last"))
            metadata["initial_fill_blocked"] = True
            metadata["initial_fill_block_reason"] = "LIMIT_NOT_REACHED"
            if realtime_px is not None and basket_px is not None and basket_px > 0 and realtime_px <= basket_px:
                metadata["fill_retry"] = True
                metadata["fill_retry_reason"] = "LIMIT_NOT_REACHED_REALTIME_WITHIN_BASKET"
                metadata["fill_retry_price"] = round(realtime_px, 4)
                return (
                    realtime_px,
                    "retry_realtime_after_limit_reject",
                    record.get("basket_rule"),
                    metadata,
                )
            metadata["skip_reason"] = "LIMIT_NOT_REACHED"
            if realtime_px is None:
                metadata["skip_detail"] = "NO_REALTIME_RETRY_PRICE"
            elif basket_px is None or basket_px <= 0:
                metadata["skip_detail"] = "NO_BASKET_RETRY_BOUND"
            else:
                metadata["skip_detail"] = "REALTIME_ABOVE_BASKET"
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
    ap.add_argument("--pick", choices=["vb_star", "kp_star", "mode_star"], default="vb_star",
                    help="which variant to paper-trade "
                         "(vb_star=★B live set, kp_star=★ baseline, mode_star=★M shadow variant)")
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
                         "fill = min(window VWAP, open x (1+premium)) when touched; "
                         "if not touched, retry at latest window price while <= basket; "
                         "default 0.5")
    ap.add_argument("--fill-settle-seconds", type=int, default=5,
                    help="seconds after the next minute to wait before reading the end bar")
    ap.add_argument("--no-wait-fill-window", action="store_true",
                    help="do not wait for the opening fill window to complete")
    ap.add_argument("--no-book-a", action="store_true",
                    help="skip the book-A (validated open->next-close reference) recording")
    ap.add_argument("--quality-governor", choices=["off", "shadow", "on"], default="off",
                    help="quality governor mode: off=ignore, shadow=audit only, "
                         "on=leave weak-primary slots in cash without reallocating")
    ap.add_argument("--trend-only", action="store_true",
                    help="record Book T trend paper positions only; skips Book B/A")
    ap.add_argument("--trend-budget-ratio", type=float, default=TREND_BUDGET_RATIO,
                    help="Book T paper account initial capital as a ratio of --initial-capital")
    ap.add_argument("--trend-max-positions", type=int, default=TREND_TOP_M,
                    help="target number of Book T positions")
    ap.add_argument("--trend-max-total-exposure-ratio", type=float, default=DEFAULT_TREND_MAX_EXPOSURE_RATIO,
                    help="Book T open gross exposure cap / Book T initial capital")
    a = ap.parse_args()
    _parse_hhmm(a.fill_window_start)
    _parse_hhmm(a.fill_window_end)
    _validate_fill_window(a.fill_window_start, a.fill_window_end)
    if a.trend_only:
        if not a.no_wait_fill_window:
            _wait_until_fill_window_complete(a.date, a.fill_window_end, a.fill_settle_seconds)
        client = XiaocaoClient()
        _record_book_t(client, a)
        return
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
            f"window low {meta.get('fill_window_low')}, "
            f"realtime {meta.get('fill_window_last')}, "
            f"detail {meta.get('skip_detail')})"
        )
        _append_skip({
            "ts": _now_iso(), "date": a.date, "code": r.get("code"),
            "name": r.get("name"), "source": f"auto:{a.pick}",
            "reason": meta.get("skip_reason"),
            "detail": meta.get("skip_detail"),
            "limit_price": meta.get("fill_limit_price"),
            "window_low": meta.get("fill_window_low"),
            "window_vwap": meta.get("fill_window_vwap"),
            "window_last": meta.get("fill_window_last"),
            "basket_price": r.get("basket_price"), "open": r.get("open"),
            "primary_score": r.get("primary_score"),
            "p_score": r.get("p_score"),
            "quality_tag": r.get("quality_tag"),
            "quality_governor_mode": a.quality_governor,
        })
    if not buyable:
        print(f"{a.date}: all {a.pick} picks skipped (limit not reached and retry not suitable)")
        return
    if not a.no_book_a:
        _record_book_a(buyable, a, fee_rate)
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
                "fill_window_last": fill_meta.get("fill_window_last"),
                "fill_limit_price": fill_meta.get("fill_limit_price"),
                "fill_window_time": fill_meta.get("fill_window_time"),
                "initial_fill_blocked": fill_meta.get("initial_fill_blocked"),
                "initial_fill_block_reason": fill_meta.get("initial_fill_block_reason"),
                "fill_retry": fill_meta.get("fill_retry"),
                "fill_retry_reason": fill_meta.get("fill_retry_reason"),
                "fill_retry_price": fill_meta.get("fill_retry_price"),
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
                "fill_window_last": fill_meta.get("fill_window_last"),
                "fill_limit_price": fill_meta.get("fill_limit_price"),
                "initial_fill_blocked": fill_meta.get("initial_fill_blocked"),
                "initial_fill_block_reason": fill_meta.get("initial_fill_block_reason"),
                "fill_retry": fill_meta.get("fill_retry"),
                "fill_retry_reason": fill_meta.get("fill_retry_reason"),
                "fill_retry_price": fill_meta.get("fill_retry_price"),
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


def _book_t_position_cost(row: dict) -> float:
    cost = _num(row.get("gross_notional"))
    if cost is not None and cost > 0:
        return cost
    cash_out = _num(row.get("entry_cash_out"))
    return float(cash_out or 0.0)


def _book_t_entry_before_today(row: dict, date_iso: str) -> bool:
    entry_date = str(row.get("entry_date") or "")[:10]
    return bool(entry_date and entry_date < str(date_iso)[:10])


def _mark_book_t_switch_context(row: dict, *, fee_rate: float) -> dict[str, str]:
    alignment = classify_trend_alignment(
        code=str(row.get("code") or ""),
        name=str(row.get("name") or ""),
        category_name=str(row.get("category_name") or ""),
        category_code=str(row.get("category_code") or ""),
    )
    row["trend_alignment"] = alignment["trend_alignment"]
    row["trend_alignment_reason"] = alignment["trend_alignment_reason"]
    row["trend_switch_policy"] = "hold_exposure; paired_morning_switch_when_replacement_ready"
    row["trend_switch_est_roundtrip_fee_bps"] = round(fee_rate * 2 * 10000, 2)
    return alignment


def _book_t_switch_exit_plan(
    client: XiaocaoClient,
    row: dict,
    *,
    date_iso: str,
    start_hhmm: str,
    end_hhmm: str,
    account: dict,
) -> dict | None:
    code = str(row.get("code") or "")
    shares = int(row.get("shares") or 0)
    if not code or shares <= 0:
        return None
    window = _fill_window_stats(
        client,
        code,
        date_iso,
        start_hhmm=start_hhmm,
        end_hhmm=end_hhmm,
    )
    if not window:
        return None
    exit_price = _num(window.get("vwap"))
    if exit_price is None or exit_price <= 0:
        return None
    fee_rate = float(row.get("fee_rate") or account.get("fee_rate", DEFAULT_FEE_RATE))
    gross = round(float(exit_price) * shares, 2)
    exit_fee = round(gross * fee_rate, 2)
    cash_in = round(gross - exit_fee, 2)
    entry_cash_out = _num(row.get("entry_cash_out"))
    if entry_cash_out is None:
        entry_cash_out = round(
            float(row.get("gross_notional") or 0.0) + float(row.get("entry_fee") or 0.0),
            2,
        )
    realized = round(cash_in - float(entry_cash_out or 0.0), 2)
    return {
        "position": row,
        "exit_price": float(exit_price),
        "gross": gross,
        "exit_fee": exit_fee,
        "cash_in": cash_in,
        "realized_pnl": realized,
        "open_cost": _book_t_position_cost(row),
        "fill_window_start": start_hhmm,
        "fill_window_end": end_hhmm,
        "fill_window_vwap": round(float(exit_price), 4),
        "fill_window_low": round(float(window["low"]), 4) if window.get("low") else None,
        "fill_window_high": round(float(window["high"]), 4) if window.get("high") else None,
        "fill_window_last": round(float(window["last"]), 4) if window.get("last") else None,
        "fill_window_time": window.get("time"),
    }


def _apply_book_t_switch_exit(plan: dict, account: dict, *, date_iso: str) -> None:
    row = plan["position"]
    row.update({
        "status": "closed",
        "exit_date": date_iso,
        "exit_price": round(float(plan["exit_price"]), 4),
        "exit_fee": plan["exit_fee"],
        "exit_cash_in": plan["cash_in"],
        "realized_pnl": plan["realized_pnl"],
        "exit_reason": "TREND_POSTURE_MISMATCH",
        "trend_switch_execution": "paired_morning_switch",
        "trend_switch_fill_basis": "opening_window_vwap",
        "trend_switch_exit_window_start": plan.get("fill_window_start"),
        "trend_switch_exit_window_end": plan.get("fill_window_end"),
        "trend_switch_exit_window_vwap": plan.get("fill_window_vwap"),
        "trend_switch_exit_window_last": plan.get("fill_window_last"),
    })
    account["cash"] = round(float(account.get("cash", 0.0)) + float(plan["cash_in"]), 2)
    account["realized_pnl"] = round(
        float(account.get("realized_pnl", 0.0)) + float(plan["realized_pnl"]),
        2,
    )
    account["total_fees"] = round(
        float(account.get("total_fees", 0.0)) + float(plan["exit_fee"]),
        2,
    )
    account["last_sell_date"] = date_iso
    _append_trade({
        "ts": _now_iso(),
        "date": date_iso,
        "side": "SELL",
        "book": "T",
        "code": row.get("code"),
        "name": row.get("name", ""),
        "price": round(float(plan["exit_price"]), 4),
        "shares": int(row.get("shares") or 0),
        "gross_notional": plan["gross"],
        "fee": plan["exit_fee"],
        "cash_after": account["cash"],
        "realized_pnl": plan["realized_pnl"],
        "reason": "TREND_POSTURE_MISMATCH",
        "source": "auto:trend_book",
        "price_basis": "opening_window_vwap",
        "trend_switch_execution": "paired_morning_switch",
        "trend_alignment": row.get("trend_alignment"),
        "trend_alignment_reason": row.get("trend_alignment_reason"),
        "trend_switch_policy": row.get("trend_switch_policy"),
        "trend_switch_est_roundtrip_fee_bps": row.get("trend_switch_est_roundtrip_fee_bps"),
        "fill_window_start": plan.get("fill_window_start"),
        "fill_window_end": plan.get("fill_window_end"),
        "fill_window_vwap": plan.get("fill_window_vwap"),
        "fill_window_last": plan.get("fill_window_last"),
    })


def _save_positions_to_file(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def _record_book_t(client: XiaocaoClient, a) -> None:
    """Record Book T trend paper positions.

    Book T is separate from Book B: same positions.jsonl, different `book`,
    account file, source, and exit profile. Same-code B/T overlap is allowed.
    """
    trend_ratio = float(a.trend_budget_ratio)
    if not (0 < trend_ratio <= 1):
        raise SystemExit("--trend-budget-ratio must be in (0, 1]")
    target_positions = max(1, int(a.trend_max_positions))
    max_exposure = float(a.trend_max_total_exposure_ratio)
    if not (0 < max_exposure <= 1):
        raise SystemExit("--trend-max-total-exposure-ratio must be in (0, 1]")

    trend_initial_capital = round(float(a.initial_capital) * trend_ratio, 2)
    account = _load_account(trend_initial_capital, a.fee_rate, path=ACCOUNT_T)
    fee_rate = float(account.get("fee_rate", a.fee_rate))

    positions = _load_positions_from_file(POS)
    existing: set[tuple[str, str]] = set()
    open_codes: set[str] = set()
    open_count = 0
    current_open_cost = 0.0
    existing_auto_for_date = 0
    switch_candidates: list[dict] = []
    for row in positions:
        if row.get("book") != "T":
            continue
        existing.add((str(row.get("entry_date") or ""), str(row.get("code") or "")))
        if row.get("status", "open") == "open":
            open_count += 1
            if row.get("code"):
                open_codes.add(str(row.get("code")))
            current_open_cost += _book_t_position_cost(row)
            alignment = _mark_book_t_switch_context(row, fee_rate=fee_rate)
            if (
                alignment["trend_alignment"] == "external"
                and _book_t_entry_before_today(row, a.date)
            ):
                switch_candidates.append(row)
        if row.get("entry_date") == a.date and row.get("source") == "auto:trend_book":
            existing_auto_for_date += 1

    if existing_auto_for_date and not a.allow_additional:
        print(
            f"{a.date}: book T already paper-recorded {existing_auto_for_date} trend position(s); "
            "skip additional buys"
        )
        return

    switch_exit_plans: list[dict] = []
    for row in switch_candidates:
        plan = _book_t_switch_exit_plan(
            client,
            row,
            date_iso=a.date,
            start_hhmm=a.fill_window_start,
            end_hhmm=a.fill_window_end,
            account=account,
        )
        if plan is not None:
            switch_exit_plans.append(plan)

    empty_slots = max(0, target_positions - open_count)
    available_slots = empty_slots + len(switch_exit_plans)
    if available_slots <= 0:
        print(
            f"{a.date}: book T already has {open_count}/{target_positions} open position(s); "
            "no new buys; paired switches wait for a sellable old row and a replacement"
        )
        return

    picks = generate_trend_picks(
        client,
        a.date,
        max_positions=target_positions + len(open_codes) + len(switch_exit_plans),
    )
    candidate_pool = [
        r for r in picks
        if (a.date, str(r.get("code") or "")) not in existing
        and str(r.get("code") or "") not in open_codes
        and r.get("open")
    ][: max(available_slots * 3, available_slots)]
    if not candidate_pool:
        print(f"{a.date}: book T — no new trend candidates after book-scoped duplicate checks")
        return

    buyable, skipped = _attach_fill_prices(
        client,
        candidate_pool,
        a.date,
        start_hhmm=a.fill_window_start,
        end_hhmm=a.fill_window_end,
        limit_premium_pct=a.limit_premium_pct,
    )
    for r in skipped:
        meta = r.get("_paper_fill") or {}
        print(
            f"{a.date}: book T SKIP {r.get('code')} {r.get('name')} — "
            f"{meta.get('skip_reason')} (limit {meta.get('fill_limit_price')}, "
            f"window low {meta.get('fill_window_low')}, realtime {meta.get('fill_window_last')})"
        )
        _append_skip({
            "ts": _now_iso(), "date": a.date, "book": "T", "code": r.get("code"),
            "name": r.get("name"), "source": "auto:trend_book",
            "reason": meta.get("skip_reason"),
            "detail": meta.get("skip_detail"),
            "limit_price": meta.get("fill_limit_price"),
            "window_low": meta.get("fill_window_low"),
            "window_vwap": meta.get("fill_window_vwap"),
            "window_last": meta.get("fill_window_last"),
            "basket_price": r.get("basket_price"), "open": r.get("open"),
            "category_code": r.get("category_code"),
            "category_rank": r.get("category_rank"),
        })
    buyable = buyable[:available_slots]
    if not buyable:
        if switch_candidates:
            print(
                f"{a.date}: book T holds {len(switch_candidates)} posture-mismatch candidate(s); "
                "no paired replacement filled, so exposure is kept"
            )
        else:
            print(f"{a.date}: book T all candidates skipped by opening fill model")
        return

    cash = float(account.get("cash", 0.0))
    planned_switch_count = min(
        len(switch_exit_plans),
        max(0, len(buyable) - empty_slots),
    )
    selected_switches = switch_exit_plans[:planned_switch_count]
    switch_cash_in = sum(float(p["cash_in"]) for p in selected_switches)
    switched_open_cost = sum(float(p["open_cost"]) for p in selected_switches)
    plan_cash = round(cash + switch_cash_in, 2)
    plan_open_cost = max(0.0, current_open_cost - switched_open_cost)
    exposure_budget = max(
        0.0,
        float(account.get("initial_capital", trend_initial_capital)) * max_exposure - plan_open_cost,
    )
    slot_notional = min(plan_cash, exposure_budget) / max(available_slots, 1)
    if slot_notional <= 0:
        print(
            f"{a.date}: book T exposure budget exhausted "
            f"(cash_T={cash:.2f}, open_cost_T={current_open_cost:.2f}, "
            f"switch_ready={planned_switch_count})"
        )
        return

    POS.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    run_fees = 0.0
    new_rows: list[dict] = []
    new_trades: list[dict] = []
    cash = plan_cash
    for r in buyable:
        if n >= len(buyable):
            break
        px, fill_basis, basket_rule = _fill_price(r)
        if not px:
            continue
        px = float(px)
        fill_meta = r.get("_paper_fill") if isinstance(r.get("_paper_fill"), dict) else {}
        shares = int((min(slot_notional, cash) / (px * (1 + fee_rate))) / 100) * 100
        if shares < 100:
            continue
        gross_notional = round(shares * px, 2)
        entry_fee = round(gross_notional * fee_rate, 2)
        entry_cash_out = round(gross_notional + entry_fee, 2)
        if entry_cash_out > cash + 1e-6:
            continue
        cash = round(cash - entry_cash_out, 2)
        row = {
            "book": "T",
            "code": r["code"],
            "name": r.get("name", ""),
            "entry_date": a.date,
            "entry_price": round(px, 3),
            "profile": "trend",
            "shares": shares,
            "mode": r.get("mode"),
            "is_main_line": r.get("is_main_line"),
            "is_big_cap": r.get("is_big_cap"),
            "category_code": r.get("category_code"),
            "category_name": r.get("category_name"),
            "category_rank": r.get("category_rank"),
            "category_score": r.get("category_score"),
            "trend_score": r.get("trend_score"),
            "trend_num": r.get("trend_num"),
            "trend_lookback_days": r.get("trend_lookback_days"),
            "trend_rebalance_days": r.get("trend_rebalance_days", TREND_REBALANCE_R),
            "trend_trail_dd_pct": r.get("trend_trail_dd_pct", TREND_TRAIL_DD),
            "tradableAShare": r.get("tradableAShare"),
            "trend_alignment": r.get("trend_alignment"),
            "trend_alignment_reason": r.get("trend_alignment_reason"),
            "trend_switch_policy": r.get("trend_switch_policy"),
            "trend_switch_execution": (
                "paired_morning_replacement" if n < planned_switch_count else None
            ),
            "gross_notional": gross_notional,
            "entry_fee": entry_fee,
            "entry_cash_out": entry_cash_out,
            "entry_price_basis": fill_basis,
            "fill_window_start": a.fill_window_start,
            "fill_window_end": a.fill_window_end,
            "fill_window_high": fill_meta.get("fill_window_high"),
            "fill_window_low": fill_meta.get("fill_window_low"),
            "fill_window_vwap": fill_meta.get("fill_window_vwap"),
            "fill_window_last": fill_meta.get("fill_window_last"),
            "fill_limit_price": fill_meta.get("fill_limit_price"),
            "fill_window_time": fill_meta.get("fill_window_time"),
            "initial_fill_blocked": fill_meta.get("initial_fill_blocked"),
            "initial_fill_block_reason": fill_meta.get("initial_fill_block_reason"),
            "fill_retry": fill_meta.get("fill_retry"),
            "fill_retry_reason": fill_meta.get("fill_retry_reason"),
            "fill_retry_price": fill_meta.get("fill_retry_price"),
            "fill_fallback": fill_meta.get("fill_fallback"),
            "basket_price": round(float(r["basket_price"]), 3) if r.get("basket_price") else None,
            "basket_rule": basket_rule,
            "initial_capital": round(float(account.get("initial_capital", trend_initial_capital)), 2),
            "fee_rate": fee_rate,
            "allocation_rule": (
                f"book_t_trend_budget_{trend_ratio:.0%}"
                f"_slots_{target_positions}"
                f"_cap_{max_exposure:.0%}"
            ),
            "status": "open",
            "source": "auto:trend_book",
            "reason": r.get("reason"),
        }
        new_rows.append(row)
        new_trades.append({
            "ts": _now_iso(), "date": a.date, "side": "BUY", "book": "T",
            "code": r["code"], "name": r.get("name", ""),
            "price": round(px, 3), "shares": shares,
            "gross_notional": gross_notional, "fee": entry_fee,
            "cash_after": cash, "source": "auto:trend_book",
            "price_basis": fill_basis,
            "category_code": r.get("category_code"),
            "category_rank": r.get("category_rank"),
            "trend_score": r.get("trend_score"),
            "trend_alignment": r.get("trend_alignment"),
            "trend_alignment_reason": r.get("trend_alignment_reason"),
            "trend_switch_policy": r.get("trend_switch_policy"),
            "trend_switch_execution": (
                "paired_morning_replacement" if n < planned_switch_count else None
            ),
            "fill_window_start": a.fill_window_start,
            "fill_window_end": a.fill_window_end,
            "fill_window_vwap": fill_meta.get("fill_window_vwap"),
            "fill_window_last": fill_meta.get("fill_window_last"),
            "fill_limit_price": fill_meta.get("fill_limit_price"),
        })
        run_fees = round(run_fees + entry_fee, 2)
        n += 1

    actual_switch_count = min(planned_switch_count, n)
    selected_switches = selected_switches[:actual_switch_count]
    if actual_switch_count < planned_switch_count:
        # Rewind the unused switch proceeds before mutating account/positions.
        unused = switch_exit_plans[actual_switch_count:planned_switch_count]
        cash = round(cash - sum(float(p["cash_in"]) for p in unused), 2)

    if n == 0:
        print(
            f"{a.date}: book T no positions recorded after fill/sizing checks "
            f"(cash_T={cash:.2f}, slot_notional={slot_notional:.2f})"
        )
        return
    for plan in selected_switches:
        _apply_book_t_switch_exit(plan, account, date_iso=a.date)
    for trade in new_trades:
        _append_trade(trade)
    account["cash"] = cash
    account["fee_rate"] = fee_rate
    account["last_buy_date"] = a.date
    account["total_fees"] = round(float(account.get("total_fees", 0.0)) + run_fees, 2)
    _save_account(account, path=ACCOUNT_T)
    if selected_switches:
        _save_positions_to_file(POS, positions + new_rows)
    else:
        with POS.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(
        f"{a.date}: book T paper-recorded {n} trend position(s), "
        f"paired_switches={len(selected_switches)} -> {POS} "
        f"(cash_T_after={cash:.2f}, initial_T={float(account.get('initial_capital', trend_initial_capital)):.2f}, "
        f"slot_notional={slot_notional:.2f}, trail_dd={TREND_TRAIL_DD:.1f}%, "
        f"rebalance_days={TREND_REBALANCE_R})"
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
    """Book A = the reference exit policy: same fillable picks and same paper
    entry price as book B, then sell at next close with no stop. Pure accounting
    book (settled by settle_book_a.py at eod) — never monitored or stop-managed.
    Keeping the entry fill aligned prevents the A/B spread from mixing entry
    slippage into the exit-policy comparison."""
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
        if not _fill_price(r)[0]:
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
            px, fill_basis, basket_rule = _fill_price(r)
            if not px:
                continue
            fill_meta = r.get("_paper_fill") if isinstance(r.get("_paper_fill"), dict) else {}
            px = float(px)
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
                "entry_price_basis": fill_basis,
                "fill_window_start": a.fill_window_start,
                "fill_window_end": a.fill_window_end,
                "fill_window_high": fill_meta.get("fill_window_high"),
                "fill_window_low": fill_meta.get("fill_window_low"),
                "fill_window_vwap": fill_meta.get("fill_window_vwap"),
                "fill_window_last": fill_meta.get("fill_window_last"),
                "fill_limit_price": fill_meta.get("fill_limit_price"),
                "fill_window_time": fill_meta.get("fill_window_time"),
                "initial_fill_blocked": fill_meta.get("initial_fill_blocked"),
                "initial_fill_block_reason": fill_meta.get("initial_fill_block_reason"),
                "fill_retry": fill_meta.get("fill_retry"),
                "fill_retry_reason": fill_meta.get("fill_retry_reason"),
                "fill_retry_price": fill_meta.get("fill_retry_price"),
                "fill_fallback": fill_meta.get("fill_fallback"),
                "basket_price": round(float(r["basket_price"]), 3) if r.get("basket_price") else None,
                "basket_rule": basket_rule,
                "fee_rate": fee_rate,
                "initial_capital": round(float(account.get("initial_capital", a.initial_capital)), 2),
                "status": "open", "source": f"auto:{a.pick}:bookA",
            }, ensure_ascii=False) + "\n")
            _append_trade({
                "ts": _now_iso(), "date": a.date, "side": "BUY", "book": "A",
                "code": r["code"], "name": r.get("name", ""), "price": round(px, 3),
                "shares": shares, "gross_notional": gross, "fee": fee,
                "cash_after": cash, "source": f"auto:{a.pick}:bookA",
                "price_basis": fill_basis,
                "fill_window_start": a.fill_window_start,
                "fill_window_end": a.fill_window_end,
                "fill_window_high": fill_meta.get("fill_window_high"),
                "fill_window_vwap": fill_meta.get("fill_window_vwap"),
                "fill_window_last": fill_meta.get("fill_window_last"),
                "fill_limit_price": fill_meta.get("fill_limit_price"),
                "initial_fill_blocked": fill_meta.get("initial_fill_blocked"),
                "initial_fill_block_reason": fill_meta.get("initial_fill_block_reason"),
                "fill_retry": fill_meta.get("fill_retry"),
                "fill_retry_reason": fill_meta.get("fill_retry_reason"),
                "fill_retry_price": fill_meta.get("fill_retry_price"),
            })
            n += 1
    if n:
        account["cash"] = cash
        account["fee_rate"] = fee_rate
        account["last_buy_date"] = a.date
        _save_account(account, path=ACCOUNT_A)
    print(f"{a.date}: book A recorded {n} position(s) at book-B-aligned entry fill (cash_A={cash:.2f})")


def _load_positions_from_file(path: Path) -> list[dict]:
    return accounts.load_positions(path)


if __name__ == "__main__":
    main()
