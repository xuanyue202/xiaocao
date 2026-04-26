"""Probe whether intraday endpoints support historical playback.

Background: Phase C plan said "盘中 cache 0 命中，无法向后回测，必须从今日起捕获"。
But that assumed the 7 intraday endpoints are all real-time only. catalog.py +
client.py inspection found that several DO have a date / trade_date / paramTime
parameter; the question is whether the API HONORS them or silently returns
今日 data (the kline-anchor bug from report §6 副产品 #2 showed at least one
case of silent ignore).

This script calls each candidate endpoint twice:
  1. with no date / today
  2. with last-week's trade date (we use 2026-04-21)

If response[2] != response[1] AND response[2]'s data is for the requested past
date, the endpoint supports historical playback → we can backtest intraday signals
directly against last week's data instead of waiting 1 month.

Tested endpoints:
  ✓ xiao_cao_environment_minute_line  — has trade_date param
  ✓ xiao_cao_environment_second_line_v2  — has date param
  ✓ xiao_cao_environment_second_line_selection  — has date param
  ✓ stock_call_auction  — has tradeDate param
  ✓ get_technical_index_history  — has tradeDate + freq=1min
  ? second_line / second_line_detail_info  — NO date param (likely realtime only)
  ? minute_line  — NO date param (likely today-only)
  ? each_trade  — has count, NO date (likely "last N from now")

Usage:
  python3 scripts/probe_intraday_history.py
  (requires live API credentials; uses default config)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

# Past trade date — pick a known A-share trading day from last week.
PAST_DATE = "2026-04-22"  # Wed (within cache range, definitely a trade day)
TEST_STOCK = "002347.XSHE"  # arbitrary; just need valid code
TEST_INDEX_CODE = "9A0001"  # 小草环境指数 default


def _shape(obj) -> str:
    if isinstance(obj, list):
        return f"list n={len(obj)}" + (
            f", first.keys={list(obj[0].keys())[:8]}" if obj and isinstance(obj[0], dict) else ""
        )
    if isinstance(obj, dict):
        return f"dict keys={list(obj.keys())[:8]}"
    return f"{type(obj).__name__}"


def _sample_dates(obj) -> set:
    """Pull every distinct tradeDate / date string out of the response."""
    out: set = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("tradeDate", "date", "tradeTime") and isinstance(v, (str, int)):
                    out.add(str(v)[:10])
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return out


def probe(name: str, fn, **kwargs) -> dict:
    """Call fn(**kwargs); capture response shape + any embedded date strings."""
    try:
        result = fn(**kwargs)
    except Exception as e:
        return {"name": name, "error": f"{type(e).__name__}: {e}"}
    return {
        "name": name,
        "shape": _shape(result),
        "dates": sorted(_sample_dates(result))[:10],
        "len_json": len(json.dumps(result, ensure_ascii=False)) if result else 0,
    }


def compare(today_result: dict, past_result: dict, past_date: str) -> str:
    if today_result.get("error") or past_result.get("error"):
        return f"ERROR today={today_result.get('error', '')}, past={past_result.get('error', '')}"
    today_dates = set(today_result.get("dates") or [])
    past_dates = set(past_result.get("dates") or [])
    if past_date in past_dates and past_date not in today_dates:
        return f"✅ supports history: past response has {past_date}, today response doesn't"
    if past_dates == today_dates:
        return "❌ ignored date param: today and past responses have same dates"
    return f"⚠ inconclusive: today_dates={list(today_dates)[:3]}, past_dates={list(past_dates)[:3]}"


def main() -> None:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    client = XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=cache,
    )

    probes = []

    # 1. xiao_cao_environment_minute_line
    today_a = probe(
        "env_minute_line(today)", client.xiao_cao_environment_minute_line,
        code=TEST_INDEX_CODE,
    )
    past_a = probe(
        f"env_minute_line(past={PAST_DATE})", client.xiao_cao_environment_minute_line,
        code=TEST_INDEX_CODE, trade_date=PAST_DATE,
    )
    probes.append(("xiao_cao_environment_minute_line", today_a, past_a))

    # 2. xiao_cao_environment_second_line_v2
    today_b = probe(
        "env_second_line_v2(today)", client.xiao_cao_environment_second_line_v2,
        date="",
    )
    past_b = probe(
        f"env_second_line_v2(past={PAST_DATE})", client.xiao_cao_environment_second_line_v2,
        date=PAST_DATE,
    )
    probes.append(("xiao_cao_environment_second_line_v2", today_b, past_b))

    # 3. xiao_cao_environment_second_line_selection
    today_c = probe(
        "env_second_line_selection(today)", client.xiao_cao_environment_second_line_selection,
        date="",
    )
    past_c = probe(
        f"env_second_line_selection(past={PAST_DATE})", client.xiao_cao_environment_second_line_selection,
        date=PAST_DATE,
    )
    probes.append(("xiao_cao_environment_second_line_selection", today_c, past_c))

    # 4. stock_call_auction
    today_d = probe(
        "stock_call_auction(today)", client.stock_call_auction,
        code=TEST_STOCK, date="",
    )
    past_d = probe(
        f"stock_call_auction(past={PAST_DATE})", client.stock_call_auction,
        code=TEST_STOCK, date=PAST_DATE,
    )
    probes.append(("stock_call_auction", today_d, past_d))

    # 5. get_technical_index_history with freq=1min — designed for historical
    today_e = probe(
        "tech_index_history(today, 1min)", client.get_technical_index_history,
        stock_id=TEST_STOCK, freq="1min", count=240,
    )
    past_e = probe(
        f"tech_index_history(past={PAST_DATE}, 1min)", client.get_technical_index_history,
        stock_id=TEST_STOCK, freq="1min", count=240, trade_date=PAST_DATE,
    )
    probes.append(("get_technical_index_history(1min)", today_e, past_e))

    # 6. minute_line — has no date param, but check anyway as control
    today_f = probe(
        "minute_line(today)", client.minute_line, code=TEST_STOCK, freq="1min",
    )
    past_f = {"name": "minute_line(past)", "error": "no date param available", "shape": "—", "dates": []}
    probes.append(("minute_line", today_f, past_f))

    # 7. second_line — control: no date param
    today_g = probe("second_line(today)", client.second_line, codes=TEST_STOCK)
    past_g = {"name": "second_line(past)", "error": "no codes-with-date support", "shape": "—", "dates": []}
    probes.append(("second_line", today_g, past_g))

    # 8. each_trade — control: no date param
    today_h = probe("each_trade(today)", client.each_trade, code=TEST_STOCK, count=20)
    past_h = {"name": "each_trade(past)", "error": "no date param available", "shape": "—", "dates": []}
    probes.append(("each_trade", today_h, past_h))

    # Render results
    print(f"\nProbe target: {TEST_STOCK} (and {TEST_INDEX_CODE} for env), past_date={PAST_DATE}")
    print("=" * 80)
    for endpoint, today_r, past_r in probes:
        print(f"\n## {endpoint}")
        print(f"  today: {today_r}")
        print(f"  past:  {past_r}")
        print(f"  verdict: {compare(today_r, past_r, PAST_DATE)}")


if __name__ == "__main__":
    main()
