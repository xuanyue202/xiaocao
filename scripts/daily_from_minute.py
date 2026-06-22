#!/usr/bin/env python3
"""Reconstruct daily OHLC / VWAP / opening-window VWAP from /stock/minute_line.

Why this exists: the date_kline (daily OHLCV) endpoint lags ~weeks
(froze at 2026-05-29 mid-2026), but minute_line serves current data — and its
per-minute PRICE is the `trade` field (open/high/low/close come back null). So we
rebuild daily bars from `trade`. See AGENTS.md "Calling the xiaocao data API".

RATE-LIMITED + cache-first by construction: minute_line is fetched with the
SQLite cache ON (so each day persists to output/.cache/xiaocao.db and re-runs are
free), a sleep is inserted between *network* calls, and a persistent-empty
result is treated as a throttle (exponential backoff). Output JSONL is append-
idempotent: an already-reconstructed (code,date) is skipped.

Usage:
  python3 scripts/daily_from_minute.py --codes 300408.XSHE,600183.XSHG \
      --dates 20260601,20260608,20260619 --out output/research/daily_minute.jsonl
  python3 scripts/daily_from_minute.py --jobs jobs.csv   # lines: CODE,YYYYMMDD
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

OPEN_WINDOW = {"0930", "0931"}  # contract §5 fill window 09:30-09:31


def reconstruct(bars: list) -> dict | None:
    """Daily OHLC/VWAP from minute bars using the `trade` price field."""
    if not isinstance(bars, list):
        return None
    px = [(b.get("trade"), b.get("vol") or 0, str(b.get("tradeTime") or "")) for b in bars
          if isinstance(b, dict) and b.get("trade") is not None]
    if not px:
        return None
    trades = [p for p, _, _ in px]
    tot_vol = sum(v for _, v, _ in px)
    vwap = (sum(p * v for p, v, _ in px) / tot_vol) if tot_vol else None
    ow = [(p, v) for p, v, t in px if t in OPEN_WINDOW]
    ow_vol = sum(v for _, v in ow)
    ow_vwap = (sum(p * v for p, v in ow) / ow_vol) if ow_vol else (ow[0][0] if ow else px[0][0])
    return {
        "open": px[0][0], "high": max(trades), "low": min(trades), "close": px[-1][0],
        "vwap": round(vwap, 4) if vwap else None,
        "open_window_vwap": round(ow_vwap, 4) if ow_vwap else None,
        "bars": len(px),
    }


def _done_keys(out_path: Path) -> set:
    if not out_path.exists():
        return set()
    keys = set()
    for line in out_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            keys.add((r["code"], r["date"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return keys


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codes", help="comma-separated codes WITH exchange suffix (NNNNNN.XSHG/.XSHE)")
    ap.add_argument("--dates", help="comma-separated YYYYMMDD")
    ap.add_argument("--jobs", help="CSV file, one CODE,YYYYMMDD per line (overrides --codes/--dates)")
    ap.add_argument("--out", default="output/research/daily_from_minute.jsonl")
    ap.add_argument("--sleep", type=float, default=1.5, help="seconds between network calls (rate-limit)")
    ap.add_argument("--max-retries", type=int, default=5, help="backoff retries on empty (throttle)")
    ap.add_argument("--count", type=int, default=241)
    a = ap.parse_args()

    jobs: list[tuple[str, str]] = []
    if a.jobs:
        for line in Path(a.jobs).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            code, date = (x.strip() for x in line.split(",")[:2])
            jobs.append((code, date))
    else:
        codes = [c.strip() for c in (a.codes or "").split(",") if c.strip()]
        dates = [d.strip() for d in (a.dates or "").split(",") if d.strip()]
        jobs = [(c, d) for c in codes for d in dates]
    if not jobs:
        raise SystemExit("no jobs: pass --codes/--dates or --jobs")

    out_path = ROOT / a.out if not Path(a.out).is_absolute() else Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = _done_keys(out_path)

    s = load_settings(None)
    client = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                           cache=SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db"))

    ok = skipped = failed = 0
    with out_path.open("a", encoding="utf-8") as fh:
        for code, date in jobs:
            if (code, date) in done:
                skipped += 1
                continue
            daily = None
            for attempt in range(a.max_retries):
                bars = client.minute_line(code, trade_date=date, count=a.count)
                daily = reconstruct(bars)
                if daily:
                    break
                # empty => likely throttle; back off then retry
                wait = a.sleep * (2 ** attempt)
                print(f"  empty {code} {date} (attempt {attempt+1}) — backoff {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
            if daily:
                rec = {"code": code, "date": date, **daily}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                ok += 1
                print(f"  {code} {date}: O={daily['open']} C={daily['close']} "
                      f"vwap={daily['vwap']} ow_vwap={daily['open_window_vwap']} bars={daily['bars']}")
            else:
                failed += 1
                print(f"  FAILED {code} {date} (throttled/no data after {a.max_retries} retries)", file=sys.stderr)
            time.sleep(a.sleep)
    print(f"\ndone: {ok} reconstructed, {skipped} cached-skip, {failed} failed -> {out_path}")
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
