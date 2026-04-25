from __future__ import annotations

import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
import requests

from .errors import ApiError, ApiNotFoundError, ApiSchemaError
from xiaocao.utils.dates import compact_date


DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://www.topxlc.com",
    "referer": "https://www.topxlc.com/",
    "user-agent": "Mozilla/5.0 xiaocao-cli/0.1",
}

# API model constants. These names are inferred from live API observations, not
# official enum docs. See docs/api_models.md for the evidence log.
RANK_MODEL_FULL = 0
RANK_MODEL_FOCUS = 1
RANK_MODEL_FULL_ALIAS_2 = 2
RANK_MODEL_FULL_ALIAS_3 = 3


@dataclass
class XiaocaoClient:
    base_url: str = "https://p-xcapi.kjap1.cn"
    timeout: float = 10
    retries: int = 3
    backoff: float = 0.4

    def post(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        payload = {"params": params}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=DEFAULT_HEADERS,
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code == 404:
                    raise ApiNotFoundError(f"API endpoint not found: {path}")
                response.raise_for_status()
                body = response.json()
                code = body.get("code")
                if code is not None and code != 8200:
                    message = body.get("msg") or body.get("errmsg") or body
                    raise ApiError(f"API returned code={code}: {message}")
                if "result" not in body:
                    raise ApiSchemaError(f"Missing result in API response for {path}")
                return body["result"]
            except (requests.RequestException, ValueError, ApiError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.backoff * (attempt + 1))
        if isinstance(last_error, ApiError):
            raise last_error
        raise ApiError(f"Request failed for {path}: {last_error}")

    def get_code_list_v2(
        self,
        date: str,
        group: int | str,
        hpqb_state: int = 0,
        lpdx_state: int = 0,
    ) -> list[str]:
        result = self.post(
            "/stock/focus_xiao_cao_index/get_code_list_v2",
            {
                "groups": str(group),
                "date": date,
                "hpqbState": hpqb_state,
                "lpdxState": lpdx_state,
            },
        )
        if isinstance(result, dict):
            return list(result.get("data") or [])
        if isinstance(result, list):
            return result
        raise ApiSchemaError("Unexpected get_code_list_v2 response shape")

    def get_xiao_cao_index_v2(
        self,
        date: str,
        stock_codes: Iterable[str] | str,
        hpqb_state: int = 0,
        lpdx_state: int = 0,
    ) -> list[dict[str, Any]]:
        codes = ",".join(stock_codes) if not isinstance(stock_codes, str) else stock_codes
        result = self.post(
            "/stock/xiao_cao_index_v2",
            {
                "stockCodes": codes,
                "date": date,
                "hpqbState": hpqb_state,
                "lpdxState": lpdx_state,
            },
        )
        if isinstance(result, dict):
            return [{**value, "code": key} if isinstance(value, dict) and "code" not in value else value for key, value in result.items()]
        if isinstance(result, list):
            return result
        raise ApiSchemaError("Unexpected xiao_cao_index_v2 response shape")

    def sort_v2(
        self,
        stock_ids: Iterable[str],
        sort_id: int,
        query_type: int = 1,
        sort_type: int = 1,
        type_: int = 0,
        hpqb_state: int = 0,
        lpdx_state: int = 0,
    ) -> list[Any]:
        return self.post(
            "/stock/sort_v2",
            {
                "queryType": query_type,
                "sortId": sort_id,
                "sortType": sort_type,
                "type": type_,
                "hpqbState": hpqb_state,
                "lpdxState": lpdx_state,
                "stockIds": list(stock_ids),
            },
        )

    def get_industry_block_rank(self, date: str, model: int = RANK_MODEL_FOCUS) -> list[dict[str, Any]]:
        """Return industry/block rank rows.

        Observed model meanings:
        - 0: full continuous rank, suitable for report display.
        - 1: sparse focus/selected rank, suitable for strategy boosts.
        - 2/3: currently behave like model 0, likely aliases or reserved variants.
        """
        result = self.post("/stock/xiao_cao_industry_block_rank", {"date": date, "model": model})
        return result if isinstance(result, list) else list(result.values())

    def get_block_category_rank_v3(self, date: str, model: int = RANK_MODEL_FULL) -> list[dict[str, Any]]:
        """Return category rank rows.

        Observed model meanings mirror industry/block rank:
        - 0: full continuous rank.
        - 1: focus/normalized subset.
        - 2/3: currently behave like model 0, likely aliases or reserved variants.
        """
        result = self.post("/stock/xiao_cao_block_category_rank_v3", {"date": date, "model": model})
        if isinstance(result, dict):
            for key in ("localCategoryRankList", "globalCategoryRankList", "data"):
                if isinstance(result.get(key), list):
                    return result[key]
            return list(result.values())
        return result

    def get_block_score(self, date: str) -> Any:
        return self.post("/stock/xiao_cao_block_score", {"date": date})

    def get_xiao_cao_dynamic_index(self, date: str, index_type: int = 0) -> list[dict[str, Any]]:
        result = self.post("/stock/xiao_cao_dynamic_index", {"tradeDate": date, "indexType": index_type})
        return _as_list_of_dicts(result, "xiao_cao_dynamic_index")

    def get_trade_cal(
        self,
        start: str,
        end: str,
        exchange: str = "SSE",
        is_open: int = 1,
    ) -> list[dict[str, Any]]:
        result = self.post(
            "/stock/trade_cal",
            {
                "exchange": exchange,
                "isOpen": is_open,
                "startDate": compact_date(start),
                "endDate": compact_date(end),
            },
        )
        return result if isinstance(result, list) else list(result.values())

    def next_trade_cal(
        self,
        start: str,
        end: str,
        exchange: str = "SSE",
        is_open: int = 1,
    ) -> list[dict[str, Any]]:
        result = self.post(
            "/stock/next_trade_cal",
            {
                "exchange": exchange,
                "isOpen": is_open,
                "startDate": compact_date(start),
                "endDate": compact_date(end),
            },
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return list(result.values())
        if isinstance(result, str):
            return [{"date": _normalize_api_date(result)}]
        raise ApiSchemaError(f"Unexpected next_trade_cal response shape: {type(result).__name__}")

    def get_code_by_xiao_cao_block(self, date: str, **filters: str | int) -> Any:
        params = {
            "blockCodeList": "",
            "industryBlockCodeList": "",
            "categoryCodeList": "",
            "exponentCodeList": "",
            "excIndustryCodeList": "",
            "patternCodeList": "",
            "tradeDate": date,
            "blockTypeList": "",
            "stockIds": "",
            "aiStockIds": "",
            "blockIsAll": 0,
        }
        params.update(filters)
        return self.post("/stock/get_code_by_xiao_cao_block", params)

    def second_line(self, codes: str) -> Any:
        return self.post("/stock/second_line", {"code": codes})

    def second_line_detail_info(self, codes: str) -> Any:
        return self.post("/stock/second_line_detail_info", {"codes": codes})

    def xiao_cao_environment_second_line_v2(
        self,
        date: str,
        code: str = "9A0001,9A0002,9A0003,9B0001,9B0002,9B0003,9C0001,9A0004,9B0004,9A0005,9B0005,9C0002",
        code_type: int = 0,
        is_fool_mode: int = 0,
    ) -> Any:
        return self.post(
            "/stock/xiao_cao_environment_second_line_v2",
            {
                "code": code,
                "date": date,
                "codeType": code_type,
                "isFoolMode": is_fool_mode,
            },
        )

    def minute_line(self, code: str, freq: str = "1min", adj: str = "bfq") -> Any:
        return self.post("/stock/minute_line", {"adj": adj, "freq": freq, "code": code})

    def date_kline(
        self,
        code: str,
        count: int = 20,
        freq: str = "D",
        adj: str = "qfq",
        code_type: str = "0",
        param_time: str = "",
    ) -> Any:
        return self.post(
            "/stock/date_kline",
            {
                "count": count,
                "code": code,
                "freq": freq,
                "adj": adj,
                "codeType": code_type,
                "paramTime": param_time,
            },
        )

    def date_kline_many(
        self,
        codes: Iterable[str],
        count: int = 20,
        freq: str = "D",
        adj: str = "qfq",
        code_type: str = "0",
        param_time: str = "",
        max_workers: int = 8,
    ) -> dict[str, Any]:
        code_list = [code for code in codes if code]
        if not code_list:
            return {}
        workers = max(1, min(max_workers, len(code_list)))
        output: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self.date_kline,
                    code,
                    count=count,
                    freq=freq,
                    adj=adj,
                    code_type=code_type,
                    param_time=param_time,
                ): code
                for code in code_list
            }
            for future in as_completed(futures):
                code = futures[future]
                output[code] = future.result()
        return {code: output[code] for code in code_list if code in output}

    def stock_call_auction(self, code: str, date: str) -> Any:
        return self.post("/stock/stock_call_auction", {"code": code, "tradeDate": compact_date(date)})


def _normalize_api_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _as_list_of_dicts(result: Any, context: str) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "list", "rows", "result"):
            if isinstance(result.get(key), list):
                return result[key]
        return [value for value in result.values() if isinstance(value, dict)]
    raise ApiSchemaError(f"Unexpected {context} response shape: {type(result).__name__}")
