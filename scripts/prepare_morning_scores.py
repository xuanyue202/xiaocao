#!/usr/bin/env python3
"""Prewake historical K/P preparation; no today-source capture or book writes."""
import argparse
import hashlib
import importlib.util
import json
import math
from datetime import datetime
from pathlib import Path

from xiaocao.api.client import XiaocaoClient
from xiaocao.api.cache import SQLiteCache
from xiaocao.config import load_settings
from xiaocao.live.morning_score_cache import model_fingerprint, previous_codes, save_scores, load_scores

ROOT = Path(__file__).resolve().parents[1]


class HistoricalInputs:
    def __init__(self, client, day, deadline):
        self.client, self.day, self.deadline = client, day, deadline
        self.hashes, self.dates = [], []

    def check(self):
        if datetime.now(self.deadline.tzinfo) >= self.deadline:
            raise TimeoutError("MORNING_SCORE_PREPARATION_DEADLINE")

    def date_kline(self, code, **kwargs):
        self.check()
        rows = self.client.date_kline(code, **kwargs)
        filtered = []
        for row in rows:
            day = str(row["tradeDate"])
            if len(day) == 8 and day.isdigit(): day = day[:4]+"-"+day[4:6]+"-"+day[6:]
            datetime.fromisoformat(day)
            if day < self.day:
                filtered.append({**row, "tradeDate": day}); self.dates.append(day)
        self.hashes.append(hashlib.sha256(json.dumps(filtered, sort_keys=True).encode()).hexdigest())
        return filtered

    def minute_line(self, code, *, trade_date, count):
        self.check()
        if trade_date >= self.day:
            raise ValueError("MORNING_SCORE_FUTURE_INPUT")
        rows = self.client.minute_line(code, trade_date=trade_date, count=count)
        expected = trade_date.replace("-", "")
        for row in rows:
            dates = [row[key] for key in ("tradeDate", "trade_date", "date") if row.get(key) is not None]
            for key in ("datetime", "timestamp", "time", "tradeTime"):
                value = row.get(key)
                if isinstance(value, str) and len(value) >= 10 and value[:4].isdigit() and value[4] == "-":
                    dates.append(value)
            # Time-only bars are bound by this exact historical request; all
            # explicit response dates must independently agree with it.
            for value in dates:
                observed = str(value).replace("-", "")[:8]
                datetime.strptime(observed, "%Y%m%d")
                if observed != expected:
                    raise ValueError("MORNING_SCORE_RESPONSE_DATE_MISMATCH")
        self.dates.append(trade_date)
        self.hashes.append(hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest())
        return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--deadline", required=True)
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.deadline)
    if deadline.utcoffset() is None:
        raise ValueError("MORNING_SCORE_AWARE_DEADLINE_REQUIRED")
    if load_scores(ROOT, args.date):
        print('{"status":"prepared_cache_reused"}')
        return
    codes = previous_codes(ROOT / "output/live", args.date)
    if not codes:
        print('{"status":"no_prior_original"}')
        return
    fingerprint = model_fingerprint(ROOT)
    settings = load_settings(None)
    client = HistoricalInputs(XiaocaoClient(base_url=settings.base_url, timeout=min(settings.timeout, 8),
        retries=0, cache=SQLiteCache(ROOT / "output/.cache/xiaocao.db"), minimum_request_interval=.5), args.date, deadline)
    path = ROOT / "kronos_screen/scripts/secondary_screen.py"
    spec = importlib.util.spec_from_file_location("prepared_secondary_screen", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    candidates = [{"code": code} for code in codes]
    module.score(candidates, client, args.date, cache_path=ROOT / "output/.cache/xiaocao.db")
    client.check()
    if not client.dates:
        raise ValueError("MORNING_SCORE_HISTORICAL_INPUT_REQUIRED")
    def finite(value): return float(value) if value is not None and math.isfinite(float(value)) else None
    result = save_scores(ROOT, args.date,
        {r["code"]: {key: finite(r.get(key)) for key in ("k_score", "p_score")} for r in candidates},
        fingerprint=fingerprint, input_max_date=max(client.dates), input_hashes=client.hashes,
        completed_at=datetime.now(deadline.tzinfo).isoformat())
    print(json.dumps({"status": "prepared", "covered": len(candidates), "sha256": result["sha256"]}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "degraded", "error_type": type(exc).__name__}))
        raise SystemExit(1)
