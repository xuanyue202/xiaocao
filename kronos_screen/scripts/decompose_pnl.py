"""Per-trade PnL attribution for the paper book, against the VALIDATED
counterfactual (buy at open[D], sell at close[D+1], no stop).

Exact log-space decomposition per closed trade:
    log(exit/entry) = log(close1/open0)        pick_alpha   (what the screen was validated on)
                    - log(entry/open0)         entry_slippage (chase above open; positive = cost)
                    + log(exit/close1)         exit_timing  (stop/discipline deviation from next close)
Reconciles sum of money PnL vs account realized_pnl. Buckets by auction gap
(auc_pct) to expose the deep-water 低吸 tail. Run daily from auto_daily.sh eod.

Uses bfq klines so prices match actual traded prices.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.config.settings import load_settings  # noqa: E402
from xiaocao.api.client import XiaocaoClient        # noqa: E402
from xiaocao.api.cache import SQLiteCache           # noqa: E402

POS = Path("output/live/positions.jsonl")
SNAP = Path("output/live/signal_snapshots.jsonl")
ACCOUNT = Path("output/live/paper_account.json")
OUT_CSV = Path("output/live/pnl_decompose.csv")
RECONSTRUCTED_DAILY = Path("output/live/daily_reconstructed.jsonl")


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _normal_date(value) -> str | None:
    s = str(value or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if len(s) >= 10:
        return s[:10]
    return None


def _load_reconstructed_daily(path: Path = RECONSTRUCTED_DAILY) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for row in _load_jsonl(path):
        code = row.get("code")
        d = _normal_date(row.get("date"))
        if not code or not d:
            continue
        out.setdefault(str(code), {})[d] = {
            "tradeDate": d,
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "source": row.get("source", "minute_reconstructed"),
        }
    return out


def _kline_map(cli, code: str, reconstructed: dict[str, dict[str, dict]]) -> dict[str, dict]:
    try:
        kl = cli.date_kline(code, count=400, freq="D", adj="bfq")
    except Exception:
        kl = []
    if not isinstance(kl, list):
        kl = []
    ser = {
        _normal_date(r.get("tradeDate")): r
        for r in kl
        if isinstance(r, dict) and _normal_date(r.get("tradeDate"))
    }
    ser.update(reconstructed.get(str(code), {}))
    return ser


def decompose(
    positions: list[dict],
    cli,
    *,
    book: str = "B",
    fee_rate_fallback: float = 0.0001,
) -> tuple[list[dict], list[dict]]:
    """Returns (rows, pending). pending = closed trades whose close[D+1] bar is
    not final yet (or kline gap) — reported, never silently dropped."""
    rows, pending = [], []
    kl_cache: dict[str, dict[str, dict]] = {}
    reconstructed = _load_reconstructed_daily()
    for p in positions:
        if p.get("status") != "closed":
            continue
        if book and p.get("book", "B") != book:
            continue
        code = p.get("code")
        d0, d1x = p.get("entry_date"), p.get("exit_date")
        entry, exitp = _f(p.get("entry_price")), _f(p.get("exit_price"))
        shares = _f(p.get("shares")) or 0
        if not (code and d0 and entry and exitp and shares):
            pending.append(p)
            continue
        if code not in kl_cache:
            kl_cache[code] = _kline_map(cli, code, reconstructed)
        ser = kl_cache[code]
        dts = sorted(ser)
        if d0 not in dts:
            pending.append(p)
            continue
        i = dts.index(d0)
        open0 = _f(ser[d0].get("open"))
        close1 = _f(ser[dts[i + 1]].get("close")) if i + 1 < len(dts) else None
        if not (open0 and close1):
            pending.append(p)
            continue
        # % view (log space, exactly additive): realized = alpha - slippage + timing
        pick_alpha = math.log(close1 / open0) * 100
        entry_slip = math.log(entry / open0) * 100          # positive = paid above open
        exit_timing = math.log(exitp / close1) * 100         # negative = sold below next close
        realized_log = math.log(exitp / entry) * 100
        # money view (price differences x shares, exactly additive):
        # (exit-entry) = (close1-open0) - (entry-open0) + (exit-close1)
        m_alpha = (close1 - open0) * shares
        m_slip = (entry - open0) * shares
        m_timing = (exitp - close1) * shares
        fees = (_f(p.get("entry_fee")) or 0) + (_f(p.get("exit_fee")) or 0)
        notional = _f(p.get("gross_notional")) or entry * shares
        rows.append({
            "entry_date": d0, "exit_date": d1x, "code": code, "name": p.get("name"),
            "mode": p.get("mode"), "exit_reason": p.get("exit_reason"),
            "shares": int(shares), "notional": round(notional, 2),
            "open0": open0, "entry": entry, "close1": close1, "exit": exitp,
            "pick_alpha_pct": round(pick_alpha, 3),
            "entry_slippage_pct": round(entry_slip, 3),
            "exit_timing_pct": round(exit_timing, 3),
            "realized_pct": round(realized_log, 3),
            "m_pick_alpha": round(m_alpha, 2),
            "m_entry_slippage": round(m_slip, 2),
            "m_exit_timing": round(m_timing, 2),
            "fees": round(fees, 2),
            "realized_pnl": _f(p.get("realized_pnl")),
        })
    return rows, pending


def _summarize(rows: list[dict], pending: list[dict], *, book: str) -> None:
    n = len(rows)
    if not n:
        print("no closed trades to decompose")
        return
    def s(key):
        return sum(r[key] for r in rows)
    def avg(key):
        return s(key) / n
    pnl = s("realized_pnl")
    fees = s("fees")
    print(f"book {book}: closed trades decomposed: {n}   win: {sum(1 for r in rows if (r['realized_pnl'] or 0) > 0)}/{n}")
    if pending:
        pend_pnl = sum(_f(p.get("realized_pnl")) or 0 for p in pending)
        names = ", ".join(f"{p.get('name')}({p.get('exit_date')})" for p in pending)
        print(f"pending (close[D+1] not final yet): {len(pending)}  pnl {pend_pnl:+,.0f}  [{names}]")
    print(f"sum realized_pnl (decomposed): {pnl:+,.0f}  (fees {fees:,.0f})")
    print("\n-- per-trade averages (log %, vs validated open[D]->close[D+1]) --")
    print(f"  pick_alpha     : {avg('pick_alpha_pct'):+.2f}%   (screen quality at validated exits)")
    print(f"  entry_slippage : {avg('entry_slippage_pct'):+.2f}%   (paid above open; cost when +)")
    print(f"  exit_timing    : {avg('exit_timing_pct'):+.2f}%   (vs next close; cost when -)")
    print(f"  realized       : {avg('realized_pct'):+.2f}%   (= alpha - slippage + timing)")
    print("\n-- money attribution (exact, price-diff x shares) --")
    print(f"  pick_alpha     : {s('m_pick_alpha'):+,.0f}")
    print(f"  entry_slippage : {-s('m_entry_slippage'):+,.0f}")
    print(f"  exit_timing    : {s('m_exit_timing'):+,.0f}")
    print(f"  fees           : {-fees:+,.0f}")
    total = s('m_pick_alpha') - s('m_entry_slippage') + s('m_exit_timing') - fees
    # tolerance: entry/exit prices are stored rounded to 3 decimals -> ~0.5 RMB/trade
    flag = "OK" if abs(total - pnl) < max(1.0, 0.5 * n) else f"MISMATCH d={total-pnl:+.2f}"
    print(f"  total          : {total:+,.0f}   vs booked {pnl:+,.0f}  [{flag}]")
    if ACCOUNT.exists():
        acct = json.loads(ACCOUNT.read_text(encoding="utf-8"))
        booked = acct.get("realized_pnl")
        if booked is not None:
            pend_pnl = sum(_f(p.get("realized_pnl")) or 0 for p in pending)
            flag2 = "OK" if abs(booked - (pnl + pend_pnl)) < 1.0 else "MISMATCH"
            print(f"  account realized_pnl: {booked:+,.2f} = decomposed {pnl:+,.0f} + pending {pend_pnl:+,.0f}  [{flag2}]")


def _auction_buckets(rows: list[dict]) -> None:
    snaps = _load_jsonl(SNAP)
    auc = {(r.get("date"), r.get("code")): _f(r.get("auc_pct")) for r in snaps if r.get("is_live")}
    def bucket(v):
        if v is None: return "n/a"
        if v < -8: return "<-8%"
        if v < -4: return "-8..-4%"
        if v < 0: return "-4..0%"
        return ">=0%"
    agg: dict[str, list[float]] = {}
    for r in rows:
        b = bucket(auc.get((r["entry_date"], r["code"])))
        agg.setdefault(b, []).append(r["realized_pct"])
    print("\n-- realized % by auction gap (auc_pct at 9:25) --")
    for b in ("<-8%", "-8..-4%", "-4..0%", ">=0%", "n/a"):
        if b in agg:
            v = agg[b]
            wins = sum(1 for x in v if x > 0)
            print(f"  {b:>8}: n={len(v):>2}  avg {sum(v)/len(v):+.2f}%  win {wins}/{len(v)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--csv", default=str(OUT_CSV))
    ap.add_argument("--book", default="B", choices=["A", "B", "all"], help="position book to decompose")
    a = ap.parse_args()
    positions = _load_jsonl(POS)
    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                        cache=SQLiteCache(a.cache))
    book = "" if a.book == "all" else a.book
    rows, pending = decompose(positions, cli, book=book)
    _summarize(rows, pending, book=a.book)
    _auction_buckets(rows)
    if rows:
        import csv
        out = Path(a.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nper-trade table -> {out}")


if __name__ == "__main__":
    main()
