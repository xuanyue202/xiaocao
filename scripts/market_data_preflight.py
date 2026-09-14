#!/usr/bin/env python3
"""Read-only authentication/transport probe; never produces a candidate freeze."""
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from xiaocao.api.client import XiaocaoClient
from xiaocao.api.errors import ApiAuthError, ApiError
from xiaocao.config import load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today")
    args = parser.parse_args()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    date = now.date().isoformat() if args.date == "today" else args.date
    settings = load_settings(None)
    client = XiaocaoClient(base_url=settings.base_url, timeout=8, retries=0, cache=None)
    receipt = {"observed_at": now.isoformat(), "requested_date": date,
               "endpoint": "/stock/xiao_cao_industry_block_rank",
               "source_completeness_proven": False, "actions": "market_data_read_only"}
    try:
        rows = client.get_industry_block_rank(date, settings.block_model)
        receipt.update(status="reachable", row_count=len(rows))
    except ApiAuthError:
        receipt.update(status="blocked", reason="MARKET_DATA_AUTH_REQUIRED", api_code=990502)
    except ApiError:
        receipt.update(status="blocked", reason="MARKET_DATA_UNAVAILABLE")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 2 if receipt["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
