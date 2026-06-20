"""Settle book A — the validated reference policy (buy open[D], sell close[D+1],
no stop). Pure accounting: closes any open book-A position whose next-day close
is available, then prints A vs B running comparison. Run from auto_daily.sh eod.
Idempotent.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.config.settings import load_settings  # noqa: E402
from xiaocao.api.client import XiaocaoClient        # noqa: E402
from xiaocao.api.cache import SQLiteCache           # noqa: E402

POS = Path("output/live/positions.jsonl")
ACCOUNT_A = Path("output/live/paper_account_A.json")
ACCOUNT_B = Path("output/live/paper_account.json")
TRADES = Path("output/live/paper_trades.jsonl")


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    a = ap.parse_args()
    if not POS.exists():
        print("no positions file"); return
    lines = [l.rstrip("\n") for l in POS.open(encoding="utf-8") if l.strip()]
    positions = [json.loads(l) for l in lines]
    todo = [p for p in positions
            if p.get("book") == "A" and p.get("status", "open") == "open"]
    if not todo:
        print("book A: nothing to settle")
        _print_comparison(positions)
        return

    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                        cache=SQLiteCache(a.cache))
    account = json.loads(ACCOUNT_A.read_text(encoding="utf-8")) if ACCOUNT_A.exists() else None
    if account is None:
        print("book A: no account file yet"); return

    settled = 0
    for p in todo:
        code, d0 = p["code"], p["entry_date"]
        try:
            kl = cli.date_kline(code, count=60, freq="D", adj="bfq")
        except Exception:
            continue
        ser = {r["tradeDate"]: r for r in kl if isinstance(r, dict) and r.get("tradeDate")} \
            if isinstance(kl, list) else {}
        dts = sorted(ser)
        if d0 not in dts:
            continue
        i = dts.index(d0)
        if i + 1 >= len(dts):
            continue  # next close not available yet
        d1 = dts[i + 1]
        close1 = _f(ser[d1].get("close"))
        if not close1:
            continue
        shares = int(p.get("shares") or 0)
        fee_rate = float(p.get("fee_rate") or account.get("fee_rate", 0.0001))
        gross = round(close1 * shares, 2)
        exit_fee = round(gross * fee_rate, 2)
        cash_in = round(gross - exit_fee, 2)
        entry_cash_out = float(p.get("entry_cash_out") or 0.0)
        realized = round(cash_in - entry_cash_out, 2)
        p.update({
            "status": "closed", "exit_date": d1, "exit_price": close1,
            "exit_fee": exit_fee, "exit_cash_in": cash_in,
            "realized_pnl": realized, "exit_reason": "NEXT_CLOSE",
        })
        account["cash"] = round(float(account.get("cash", 0.0)) + cash_in, 2)
        account["realized_pnl"] = round(float(account.get("realized_pnl", 0.0)) + realized, 2)
        account["total_fees"] = round(float(account.get("total_fees", 0.0)) + exit_fee, 2)
        with TRADES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": _now_iso(), "date": d1, "side": "SELL", "book": "A",
                "code": code, "name": p.get("name", ""), "price": close1,
                "shares": shares, "gross_notional": gross, "fee": exit_fee,
                "cash_after": account["cash"], "realized_pnl": realized,
                "reason": "NEXT_CLOSE",
            }, ensure_ascii=False, sort_keys=True) + "\n")
        settled += 1

    if settled:
        account["updated_at"] = _now_iso()
        tmp = ACCOUNT_A.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(account, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(ACCOUNT_A)
        tmp2 = POS.with_suffix(".jsonl.tmp")
        with tmp2.open("w", encoding="utf-8") as f:
            for p in positions:
                f.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
        tmp2.replace(POS)
    print(f"book A: settled {settled} position(s) at next close")
    _print_comparison(positions)


def _print_comparison(positions: list[dict]) -> None:
    def stats(book):
        closed = [p for p in positions
                  if p.get("book", "B") == book and p.get("status") == "closed"
                  and p.get("realized_pnl") is not None]
        if not closed:
            return None
        pnl = sum(float(p["realized_pnl"]) for p in closed)
        wins = sum(1 for p in closed if float(p["realized_pnl"]) > 0)
        rets = [float(p["realized_pnl"]) / float(p.get("entry_cash_out") or 1) * 100
                for p in closed if p.get("entry_cash_out")]
        avg = sum(rets) / len(rets) if rets else 0.0
        return {"n": len(closed), "pnl": pnl, "win": wins, "avg": avg}
    sa, sb = stats("A"), stats("B")
    print("\n-- book A (validated next-close, no stop) vs book B (live stop policy) --")
    for label, st in (("A", sa), ("B", sb)):
        if st:
            print(f"  book {label}: n={st['n']:>3}  pnl {st['pnl']:+,.0f}  "
                  f"win {st['win']}/{st['n']}  avg {st['avg']:+.2f}%/trade")
        else:
            print(f"  book {label}: no closed trades yet")
    accs = []
    for label, path in (("A", ACCOUNT_A), ("B", ACCOUNT_B)):
        if path.exists():
            acct = json.loads(path.read_text(encoding="utf-8"))
            accs.append(f"  account {label}: cash={acct.get('cash', 0):,.2f} "
                        f"realized={acct.get('realized_pnl', 0):+,.2f}")
    print("\n".join(accs))


if __name__ == "__main__":
    main()
