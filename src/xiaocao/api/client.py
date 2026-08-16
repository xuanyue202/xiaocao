from __future__ import annotations

import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
import requests

from .catalog import (
    resolve_dynamic_index_type,
    resolve_group,
    resolve_rank_model,
    resolve_sort_direction,
    resolve_sort_id,
    resolve_sort_target_type,
)
from .errors import ApiError, ApiNotFoundError, ApiSchemaError
from .normalizers import (
    as_list as _as_list,
    as_list_of_dicts as _as_list_of_dicts,
    normalize_api_date as _normalize_api_date,
    normalize_etf_info_rows as _normalize_etf_info_rows,
    normalize_kline_rows as _normalize_kline_rows,
    normalize_minute_line_rows as _normalize_minute_line_rows,
    normalize_technical_rows as _normalize_technical_rows,
    percent as _percent,
    split_code as _split_code,
    technical_payload as _technical_payload,
)
from xiaocao.utils.dates import compact_date, today_str


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
    cache: Any | None = None  # optional SQLiteCache instance
    pool_size: int = 128  # HTTP connection pool size for concurrent workers

    def __post_init__(self) -> None:
        # Use a Session with adapter-level connection pooling so concurrent
        # workers reuse keep-alive sockets instead of opening fresh TCP
        # connections per call. Without this, observed CLOSE_WAIT pile-up
        # (>300 zombie sockets) and ~10x slower throughput on long backtests.
        # pool_size large enough for max concurrency (workers × per-day fan-out)
        # so connections never overflow the pool and get discarded mid-flight.
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self.pool_size,
            pool_maxsize=self.pool_size,
            pool_block=True,  # block waiting for free conn instead of opening new
            max_retries=0,  # we do retries ourselves below
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._session.headers.update(DEFAULT_HEADERS)
        self._rate_limit_lock = threading.Lock()
        self._last_rate_limited_request: dict[str, float] = {}

    def post(self, path: str, params: dict[str, Any]) -> Any:
        return self._post_json(path, {"params": params})

    def post_raw(self, path: str, payload: dict[str, Any]) -> Any:
        return self._post_json(path, payload)

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        if self.cache is not None:
            cached = self.cache.get(path, payload)
            if cached is not None:
                return cached
        self._respect_endpoint_rate_limit(path)
        result = self._do_post(path, payload)
        if self.cache is not None:
            try:
                self.cache.put(path, payload, result)
            except Exception:
                pass  # cache failures must never break the call
        return result

    def _respect_endpoint_rate_limit(self, path: str) -> None:
        """Throttle only endpoints whose cache policy declares an interval."""
        from .cache import ENDPOINT_POLICY

        interval = float(ENDPOINT_POLICY.get(path, {}).get("min_interval", 0.0) or 0.0)
        if interval <= 0:
            return
        lock = getattr(self, "_rate_limit_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._rate_limit_lock = lock
        last_requests = getattr(self, "_last_rate_limited_request", None)
        if last_requests is None:
            last_requests = {}
            self._last_rate_limited_request = last_requests
        with lock:
            now = time.monotonic()
            last = last_requests.get(path)
            wait_for = interval - (now - last) if last is not None else 0.0
            if wait_for > 0:
                time.sleep(wait_for)
            last_requests[path] = time.monotonic()

    def _do_post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                # Context manager ensures response is closed even on exceptions,
                # preventing CLOSE_WAIT socket pile-up in concurrent workloads.
                with self._session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                ) as response:
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
                "groups": str(resolve_group(group)),
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
        sort_id: int | str,
        query_type: int = 1,
        sort_type: int | str | bool = 1,
        type_: int | str = 0,
        date: str | None = None,
        hpqb_state: int = 0,
        lpdx_state: int = 0,
    ) -> list[Any]:
        params = {
            "queryType": query_type,
            "sortId": resolve_sort_id(sort_id),
            "sortType": resolve_sort_direction(sort_type),
            "type": resolve_sort_target_type(type_),
            "hpqbState": hpqb_state,
            "lpdxState": lpdx_state,
            "stockIds": list(stock_ids),
        }
        if date:
            params["date"] = date
        return self.post(
            "/stock/sort_v2",
            params,
        )

    def sort_v2_by_key(
        self,
        stock_ids: Iterable[str],
        sort_key: str,
        descending: bool = True,
        target_type: int | str = "stock",
        date: str | None = None,
        hpqb_state: int = 0,
        lpdx_state: int = 0,
    ) -> list[Any]:
        return self.sort_v2(
            stock_ids,
            sort_id=sort_key,
            sort_type=descending,
            type_=target_type,
            date=date,
            hpqb_state=hpqb_state,
            lpdx_state=lpdx_state,
        )

    def get_industry_block_rank(self, date: str, model: int | str = RANK_MODEL_FOCUS) -> list[dict[str, Any]]:
        """Return industry/block rank rows.

        Observed model meanings:
        - 0: full continuous rank, suitable for report display.
        - 1: sparse focus/selected rank, suitable for strategy boosts.
        - 2/3: currently behave like model 0, likely aliases or reserved variants.
        """
        result = self.post("/stock/xiao_cao_industry_block_rank", {"date": date, "model": resolve_rank_model(model)})
        return result if isinstance(result, list) else list(result.values())

    def get_block_category_rank_v3(self, date: str, model: int | str = RANK_MODEL_FULL) -> list[dict[str, Any]]:
        """Return category rank rows.

        Observed model meanings mirror industry/block rank:
        - 0: full continuous rank.
        - 1: focus/normalized subset.
        - 2/3: currently behave like model 0, likely aliases or reserved variants.
        """
        result = self.post("/stock/xiao_cao_block_category_rank_v3", {"date": date, "model": resolve_rank_model(model)})
        if isinstance(result, dict):
            for key in ("localCategoryRankList", "globalCategoryRankList", "data"):
                if isinstance(result.get(key), list):
                    return result[key]
            return [value for value in result.values() if isinstance(value, dict)]
        return result

    def get_block_score(self, date: str) -> Any:
        return self.post("/stock/xiao_cao_block_score", {"date": date})

    def stock_info(self) -> list[dict[str, Any]]:
        result = self.post("/stock/stock_info", {})
        rows = _as_list(result)
        output = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            status_type = row.get("statusType")
            block_type = row.get("blockType")
            if status_type not in {1, 99} and not isinstance(block_type, int):
                continue
            stock_code, market_code = _split_code(row.get("code"))
            output.append(
                {
                    "stockId": row.get("code"),
                    "stockCode": stock_code,
                    "marketCode": market_code,
                    "stockName": row.get("codeName"),
                    "la": str(row.get("la") or "").replace(" ", ""),
                    "ipoDate": row.get("ipoDate"),
                    "tsc": row.get("tsc"),
                    "roe": _percent(row.get("roe")),
                    "tradableAShare": row.get("tradableAShare"),
                    "pne": row.get("pne"),
                    "eps": row.get("eps"),
                    "mainBusiness": row.get("mainBusiness"),
                    "type": 99 if isinstance(block_type, int) else row.get("secType", 5 if status_type == 99 else 1),
                    "subType": block_type,
                }
            )
        return output

    def etf_info(self, trade_date: str | None = None) -> list[dict[str, Any]]:
        """Return the proprietary ETF catalog for one explicit trade date.

        A current date is put on the wire even when the caller omits it. This
        prevents a SQLite cache key from serving yesterday's catalog after the
        day rolls over, while preserving the endpoint's trade-date semantics.
        """
        requested_date = compact_date(trade_date or today_str())
        result = self.post("/stock/etf_info", {"tradeDate": requested_date})
        return _normalize_etf_info_rows(result, trade_date=requested_date)

    def market_overview(self) -> Any:
        return self.post("/stock/market_overview", {})

    def get_xiao_cao_dynamic_index(self, date: str, index_type: int | str = 0) -> list[dict[str, Any]]:
        result = self.post("/stock/xiao_cao_dynamic_index", {"tradeDate": date, "indexType": resolve_dynamic_index_type(index_type)})
        return _as_list_of_dicts(result, "xiao_cao_dynamic_index")

    def get_xiao_cao_industry_block_dynamic_index(self, date: str, index_type: int | str = 0) -> list[dict[str, Any]]:
        result = self.post(
            "/stock/xiao_cao_industry_block_dynamic_index",
            {"tradeDate": date, "indexType": resolve_dynamic_index_type(index_type)},
        )
        return _as_list_of_dicts(result, "xiao_cao_industry_block_dynamic_index")

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

    def each_trade(self, code: str, count: int | None = None, code_type: int = 0, is_less: int = 0, **params: Any) -> list[dict[str, Any]]:
        payload = {"code": code, "codeType": code_type, "isLess": is_less, **params}
        if count is not None:
            payload["count"] = count
        rows = _as_list(self.post("/stock/each_trade", payload))
        output = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            stock_code, market_code = _split_code(row.get("code"))
            output.append(
                {
                    "stockId": row.get("code"),
                    "stockCode": stock_code,
                    "marketCode": market_code,
                    "stockName": row.get("codeName", ""),
                    "trade": row.get("trade"),
                    "vol": row.get("oneVol"),
                    "amt": row.get("oneAmt"),
                    "flag": "buy" if row.get("bsFlag") == 1 else "sell",
                    "tradeDate": row.get("tradeDate"),
                    "tradeTime": row.get("tradeTime"),
                    "timestamp": row.get("timestamp"),
                }
            )
        return output

    def xiao_cao_block_detail(self, code: str, trade_date: str) -> dict[str, Any]:
        result = self.post("/stock/xiao_cao_block_detail", {"code": code, "tradeDate": trade_date})
        if not isinstance(result, dict):
            raise ApiSchemaError("Unexpected xiao_cao_block_detail response shape")
        stock_code, market_code = _split_code(result.get("code"))
        return {
            "code": result.get("code"),
            "stockCode": stock_code,
            "marketCode": market_code,
            "name": result.get("name"),
            "tradeDate": result.get("tradeDate"),
            "shortLineScore": result.get("shortLineScore"),
            "trendScore": result.get("trendScore"),
            "blockType": result.get("blockType"),
            "open": result.get("open"),
            "high": result.get("high"),
            "low": result.get("low"),
            "close": result.get("close"),
            "preClose": result.get("preClose"),
            "pctChangeRate": _percent(result.get("pctChangeRate")),
            "pctChange": result.get("pctChange"),
            "vol": result.get("vol"),
            "amt": result.get("amt"),
            "position": result.get("position"),
            "rank": result.get("rank"),
            "stockType": result.get("stockType"),
            "blockScoreList": result.get("blockScoreList"),
            "trade": result.get("trade"),
            "turnoverRate": result.get("turnoverRate") or 0,
        }

    def xiao_cao_block_date_kline(
        self,
        code: str,
        count: int = 120,
        freq: str = "D",
        adj: str = "bfq",
        code_type: int | str = 0,
        param_time: str = "",
    ) -> list[dict[str, Any]]:
        result = self.post(
            "/stock/xiao_cao_block_date_kline",
            {
                "count": count,
                "code": code.replace(".ZXBK", ".ZHBK"),
                "freq": freq,
                "adj": adj,
                "codeType": code_type,
                "paramTime": param_time,
            },
        )
        return _normalize_kline_rows(result, freq=freq, adj=adj)

    def xiao_cao_environment_minute_line(
        self,
        code: str,
        trade_date: str | None = None,
        adj: str = "bfq",
        freq: str = "1min",
        **params: Any,
    ) -> list[dict[str, Any]]:
        payload = {"code": code.replace(".XCHJZS", ""), "adj": adj, "freq": freq, **params}
        if trade_date:
            payload["tradeDate"] = compact_date(trade_date)
        result = self.post("/stock/xiao_cao_environment_minute_line", payload)
        return _normalize_minute_line_rows(result, market_code="XCHJZS")

    def xiao_cao_environment_second_line_selection(self, date: str) -> list[dict[str, Any]]:
        rows = _as_list(self.post("/stock/xiao_cao_environment_second_line_selection", {"date": date}))
        output = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            trade_timestamp = str(row.get("tradeTimestamp") or "")
            output.append(
                {
                    "stockId": f"{row.get('code')}.XCHJZS",
                    "stockCode": row.get("code"),
                    "marketCode": "XCHJZS",
                    "stockName": row.get("codeName"),
                    "renderId": f"{row.get('code')}.XCHJZS:{row.get('codeType')}",
                    "trade": row.get("trade"),
                    "pctChangeRate": _percent(row.get("pctChangeRate")),
                    "pctChange": row.get("pctChange"),
                    "riseRate": row.get("riseRate"),
                    "amt": row.get("amt"),
                    "turnoverRate": _percent(row.get("turnoverRatio")),
                    "amplitude": row.get("amplitude"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "open": row.get("open"),
                    "preClose": row.get("preClose"),
                    "shortLineScore": row.get("shortLineScore"),
                    "trendScore": row.get("trendScore"),
                    "position": row.get("position"),
                    "vol": row.get("vol"),
                    "tradeStatus": row.get("tradeStatus"),
                    "volRatio": row.get("volRatio"),
                    "close": row.get("close"),
                    "tradeDate": date,
                    "tradeTime": trade_timestamp,
                    "codeType": row.get("codeType"),
                    "stockCount": row.get("stockCount") or 0,
                }
            )
        return output

    def xiao_cao_week_stats(self) -> dict[str, list[dict[str, Any]]]:
        result = self.post("/stock/xiao_cao_week_stats", {})
        if not isinstance(result, dict):
            raise ApiSchemaError("Unexpected xiao_cao_week_stats response shape")

        def convert(rows: Any) -> list[dict[str, Any]]:
            output = []
            for row in _as_list(rows):
                if not isinstance(row, dict):
                    continue
                stock_code, market_code = _split_code(row.get("code"))
                output.append(
                    {
                        "stockId": row.get("code"),
                        "stockCode": stock_code,
                        "marketCode": market_code,
                        "stockName": row.get("codeName"),
                        "maxPctChangeRate": _percent(row.get("maxPctChangeRate")),
                        "holdDays": row.get("holdDays"),
                        "holdDate": row.get("ctime"),
                    }
                )
            return output

        return {
            "jsjl": convert(result.get("jsjlWeekState")),
            "xcjw": convert(result.get("xcjwWeekState")),
            "jssb": convert(result.get("jssbWeekState")),
            "cjs": convert(result.get("cjsWeekState")),
        }

    def get_technical_index(
        self,
        stock_ids: Iterable[str] | str | None = None,
        indicator: str = "smallGrass",
        **params: Any,
    ) -> list[dict[str, Any]]:
        payload = _technical_payload(stock_ids, indicator, **params)
        result = self.post_raw("/stock/get_technical_index", payload)
        return _normalize_technical_rows(result, minute=False)

    def get_technical_index_history(
        self,
        stock_id: str | None = None,
        freq: str = "D",
        indicator: str = "smallGrass",
        count: int = 200,
        adj: str = "qfq",
        trade_date: str | None = None,
        **params: Any,
    ) -> list[dict[str, Any]]:
        payload = {
            "freq": freq,
            "adj": adj,
            "count": count,
            "indicators": indicator,
            **params,
        }
        if stock_id:
            payload["code"] = stock_id
        if trade_date:
            payload["tradeDate"] = compact_date(trade_date)
        result = self.post_raw("/stock/get_technical_index_history", payload)
        return _normalize_technical_rows(result, minute="min" in freq)

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

    def minute_line(
        self,
        code: str,
        freq: str = "1min",
        adj: str = "bfq",
        trade_date: str | None = None,
        count: int | None = None,
        code_type: int = 0,
    ) -> Any:
        """Per-stock 1-min K-line. Supports HISTORICAL playback when both
        `trade_date` (any past day) AND `count` are passed; without them the
        backend silently returns today's data only.

        Per JS bundle wrapper K0 (~9835): defaults adj=bfq freq=1min; tradeDate
        is formatted as YYYYMMDD before send. If `code` contains ".XCHJZS" the
        wrapper routes to /stock/xiao_cao_environment_minute_line and strips
        the suffix; we mirror that here so callers get the same routing.

        Empirically (probed 2026-04-26):
          - count=241 + tradeDate=YYYYMMDD returns the full 9:30-15:00 day's
            1-min data for ANY past trading day → history WORKS
          - omitting count returns today's data regardless of trade_date
            (backend default 'live' mode)
        """
        is_env = ".XCHJZS" in code
        path = "/stock/xiao_cao_environment_minute_line" if is_env else "/stock/minute_line"
        clean_code = code.replace(".XCHJZS", "") if is_env else code
        payload: dict[str, Any] = {"adj": adj, "freq": freq, "code": clean_code,
                                    "codeType": code_type}
        if trade_date:
            payload["tradeDate"] = compact_date(trade_date)
        if count is not None:
            payload["count"] = count
        return self.post(path, payload)

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
