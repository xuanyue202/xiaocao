"""Bounded market-data readiness checks; no strategy or trading execution."""
from __future__ import annotations

import math
import time
from typing import Any

from .errors import ApiAuthError, ApiError


def authentication_preflight(client: Any, date: str) -> dict:
    """One authenticated read; pre-auction empty pools are not auth failures."""
    reason = None
    check = {"source": "pool:jieli", "status": "reachable"}
    try:
        rows = client.get_code_list_v2(date, "jieli")
        if not isinstance(rows, list):
            raise ValueError("invalid_rows")
        check["row_count"] = len(rows)
    except ApiAuthError:
        reason = "MARKET_DATA_AUTH_REQUIRED"
        check["api_code"] = 990502
    except (ApiError, ValueError, TypeError, KeyError):
        reason = "MARKET_DATA_UNAVAILABLE_OR_INVALID"
    if reason:
        check.update(status="blocked", reason=reason)
    return {"status": "blocked" if reason else "reachable", "reason": reason,
            "scope": "authentication", "checks": [check],
            "source_completeness_proven": False, "actions": "market_data_read_only"}


def core_preflight(client: Any, date: str, block_model: int = 1, *, pause=time.sleep) -> dict:
    checks = []
    symbol = "600519.XSHG"
    probes = [
        ("industry_rank", lambda: client.get_industry_block_rank(date, block_model)),
        ("category_rank", lambda: client.get_block_category_rank_v3(date, 0)),
        *[(f"pool:{group}", lambda g=group: client.get_code_list_v2(date, g)) for group in ("jieli", "dixi", "qibao")],
        ("stock_core", lambda: client.get_xiao_cao_index_v2(date, [symbol])),
        ("smallgrass_current", lambda: client.get_technical_index([symbol], indicator="smallGrass")),
    ]
    for name, probe in probes:
        if checks:
            pause(1)
        try:
            rows = probe()
            if not isinstance(rows, list):
                raise ValueError("invalid_rows")
            if name == "stock_core":
                if len(rows) != 1 or rows[0].get("code") != symbol:
                    raise ValueError("requested_symbol_missing")
                if not all(isinstance(rows[0].get(k), (int, float)) and math.isfinite(rows[0][k])
                           for k in ("xcjw", "jsjl", "cjs", "jssb")):
                    raise ValueError("core_scores_missing")
            if name == "smallgrass_current":
                if len(rows) != 1 or (rows[0].get("code") or rows[0].get("stockId")) != symbol:
                    raise ValueError("technical_symbol_missing")
                if not all(isinstance(rows[0].get(k), (int, float)) and math.isfinite(rows[0][k])
                           for k in ("ema", "aaaLine", "bbbLine")):
                    raise ValueError("technical_values_missing")
            checks.append({"source": name, "status": "reachable", "row_count": len(rows)})
        except ApiAuthError:
            checks.append({"source": name, "status": "blocked", "reason": "MARKET_DATA_AUTH_REQUIRED", "api_code": 990502})
            break
        except (ApiError, ValueError, TypeError, KeyError):
            checks.append({"source": name, "status": "blocked", "reason": "MARKET_DATA_UNAVAILABLE_OR_INVALID"})
            break
    failed = next((c for c in checks if c["status"] == "blocked"), None)
    return {"status": "blocked" if failed else "reachable",
            "reason": failed["reason"] if failed else None, "checks": checks,
            "source_completeness_proven": False,
            "actions": "market_data_read_only"}
