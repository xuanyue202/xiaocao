#!/usr/bin/env python3
"""Read-only authentication/transport probe; never produces a candidate freeze."""
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from xiaocao.api.client import XiaocaoClient
from xiaocao.api.preflight import core_preflight
from xiaocao.config import load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today")
    args = parser.parse_args()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    date = now.date().isoformat() if args.date == "today" else args.date
    settings = load_settings(None)
    client = XiaocaoClient(base_url=settings.base_url, timeout=8, retries=0, cache=None)
    receipt = core_preflight(client, date, settings.block_model)
    receipt.update(observed_at=now.isoformat(), requested_date=date)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 2 if receipt["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
