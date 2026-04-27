"""Live daily recommendation: v5 + v6 candidates + theoretical entry/stop.

Run any time after 9:25 (集合竞价 ends) to get today's recommended stocks
side-by-side under both validated_v5 (5d max_dd 2%) and validated_v6
(3d max_dd 0.5%) scoring rules.

Output: markdown table to stdout, also written to
    output/live/recommend_YYYY-MM-DD.md

The "entry" column is today's 9:30 open price (= 9:25 集合竞价 fill price).
After running this script, the user decides which to actually buy and at what
size; record the actuals into output/live/positions.jsonl so live_monitor.py
can track them.

Usage:
    python3 scripts/live_recommend.py [--date today]
    python3 scripts/live_recommend.py --date 2026-04-28  # backtest a past day
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.datasource.api_source import ApiDataSource  # noqa: E402
from xiaocao.strategy import run_strategy  # noqa: E402

OUT_DIR = ROOT / "output" / "live"
PROFILES = {
    "v5": {"profile": "validated_v5", "dd_pct": 2.0, "label": "5d max_dd 2% (conservative)"},
    "v6": {"profile": "validated_v6", "dd_pct": 0.5, "label": "3d max_dd 0.5% (aggressive)"},
}


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    return XiaocaoClient(
        base_url=settings.base_url, timeout=settings.timeout,
        retries=settings.retries, cache=cache,
    )


def _resolve_date(date_arg: str) -> str:
    if date_arg in ("today", "latest"):
        return _date.today().isoformat()
    return date_arg


def _entry_price(client: XiaocaoClient, code: str, date_iso: str) -> tuple[float | None, str, float | None]:
    """Fetch the best available early-session entry price for `code`.

    After 9:30, daily K has today's open. Between 9:25 and 9:30, use the latest
    call-auction quote instead; the daily K row is not populated yet.
    """
    try:
        rows = client.date_kline(code, count=10, freq="D", adj="qfq")
    except Exception:
        rows = []
    if isinstance(rows, list):
        td_compact = date_iso.replace("-", "")
        for r in rows:
            if not isinstance(r, dict):
                continue
            td = str(r.get("tradeDate", ""))[:10]
            if td == date_iso or td == td_compact:
                try:
                    price = float(r.get("open") or 0) or None
                except (TypeError, ValueError):
                    price = None
                if price:
                    pre_close = _to_float(r.get("preClose"))
                    return price, "open", pre_close

    try:
        auction_rows = client.stock_call_auction(code, date_iso)
    except Exception:
        auction_rows = []
    if isinstance(auction_rows, list):
        valid_rows = [
            r for r in auction_rows
            if isinstance(r, dict) and str(r.get("tradeTimestamp") or "") >= "092500"
        ]
        for r in reversed(valid_rows or auction_rows):
            try:
                price = float(r.get("trade") or r.get("buyPrice1") or r.get("sellPrice1") or 0) or None
            except (TypeError, ValueError):
                price = None
            if price:
                pre_close = _to_float(r.get("preClose"))
                return price, "auction", pre_close
    return None, "", None


def _basket_price(entry_price: float, pre_close: float | None, premium_pct: float) -> tuple[float, str]:
    raw = entry_price * (1 + premium_pct / 100)
    if pre_close and pre_close > 0:
        cap = pre_close * 1.06
        if raw > cap:
            return cap, "openPct<=6%"
    return raw, f"entry+{premium_pct:.1f}%"


def _to_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--basket-premium-pct", type=float, default=2.0,
                        help="早盘篮子估算价 = 集合竞价/entry 价上浮百分比，默认 2%%")
    parser.add_argument("--no-stdout", action="store_true",
                        help="只写文件，不打印 stdout")
    args = parser.parse_args()

    date_iso = _resolve_date(args.date)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = _client()
    source = ApiDataSource(client, hpqb_state=0, lpdx_state=0)

    # Run both profiles. Their signal generation is IDENTICAL (same EOD logic);
    # they differ only in scoring (exit rule), so signals should be identical.
    # We run once and label each signal as "in v5" / "in v6" — they're all in
    # both. The differentiation is in the STOP price computed below.
    rows = run_strategy(date_iso, source, profile="validated_v5", adaptive_modes=False)
    actives = [r for r in rows if r.get("adaptive_active") in (True, None)]

    if not actives:
        msg = f"# {date_iso} 候选股: NONE"
        print(msg)
        (OUT_DIR / f"recommend_{date_iso}.md").write_text(msg, encoding="utf-8")
        return

    # Enrich each with open price + theoretical stops
    candidates = []
    for r in actives:
        code = r.get("code")
        if not code:
            continue
        opn, entry_source, pre_close = _entry_price(client, code, date_iso)
        if not opn:
            continue
        basket_price, basket_rule = _basket_price(opn, pre_close, args.basket_premium_pct)
        candidates.append({
            "code": code,
            "name": r.get("name") or "",
            "mode": r.get("mode") or "",
            "open": opn,
            "pre_close": pre_close,
            "entry_source": entry_source,
            "basket_price": round(basket_price, 4),
            "basket_rule": basket_rule,
            "v5_stop_initial": round(opn * (1 - 0.02), 4),  # 2% below entry as initial
            "v6_stop_initial": round(opn * (1 - 0.005), 4),  # 0.5% below entry
            "is_main_line": bool(r.get("is_main_line")),
            "is_big_cap": bool(r.get("is_big_cap")),
            "direction": bool(r.get("direction")),
            "regime": r.get("regime") or "",
            "reason": r.get("reason") or "",
            "open_pct_change": float(r.get("openPctChange") or 0),
        })

    # Render markdown
    L: list[str] = []
    L.append(f"# {date_iso} 候选股推荐 — v5 + v6")
    L.append("")
    L.append(f"- 总信号数: {len(rows)}")
    L.append(f"- Active 信号: {len(actives)}")
    L.append(f"- 已 enrich (有开盘价): {len(candidates)}")
    L.append("")
    L.append("## Profiles 解读")
    L.append("")
    L.append("- **v5 (5d max_dd 2%)** = 持仓 5 日，从 post-entry peak 回撤 2% 即 trailing stop")
    L.append("- **v6 (3d max_dd 0.5%)** = 持仓 3 日，回撤 0.5% 即止 (aggressive，待 paper trading 验证)")
    L.append("- **入场价** = 今日 9:30 open（= 9:25 集合竞价 fill）")
    L.append(f"- **篮子估算价** = min(entry × (1 + {args.basket_premium_pct:.1f}%), preClose × 1.06)，用于早盘挂单参考")
    L.append("- **stop 列** = 当前 peak = entry 时的初始 stop 价位；peak 上行后 stop 同步上抬")
    L.append("")
    L.append("## 候选清单")
    L.append("")
    L.append("| code | name | mode | entry | basket | basket rule | source | v5 init stop | v6 init stop | open_pct | flags |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in candidates:
        flags = []
        if c["direction"]: flags.append("dir")
        if c["is_main_line"]: flags.append("main")
        if c["is_big_cap"]: flags.append("big")
        flag_s = "+".join(flags) if flags else "-"
        L.append(
            f"| {c['code']} | {c['name']} | {c['mode']} | "
            f"{c['open']:.2f} | {c['basket_price']:.2f} | {c['basket_rule']} | {c['entry_source']} | "
            f"{c['v5_stop_initial']:.2f} | {c['v6_stop_initial']:.2f} | "
            f"{c['open_pct_change']:+.2f}% | {flag_s} |"
        )
    L.append("")
    L.append("## 实操建议")
    L.append("")
    L.append("1. 9:25 之前在集合竞价中下买单（按你看好的子集）")
    L.append("2. 9:30 fill 后把实际买入记录到 `output/live/positions.jsonl`：")
    L.append("```jsonl")
    for c in candidates[:2]:
        L.append(json.dumps({
            "code": c["code"], "name": c["name"],
            "entry_date": date_iso, "entry_price": c["open"],
            "basket_price": c["basket_price"],
            "basket_rule": c["basket_rule"],
            "profile": "v5",  # or v6 — depends on which stop you commit to
            "shares": 1000,
        }, ensure_ascii=False))
    L.append("```")
    L.append("3. 盘中每 5-10 分钟跑 `python3 scripts/live_monitor.py` 看止损是否触发")
    L.append("")

    md = "\n".join(L)
    (OUT_DIR / f"recommend_{date_iso}.md").write_text(md, encoding="utf-8")
    if not args.no_stdout:
        print(md)
    print(f"\n[wrote {OUT_DIR / f'recommend_{date_iso}.md'}]", file=sys.stderr)


if __name__ == "__main__":
    main()
