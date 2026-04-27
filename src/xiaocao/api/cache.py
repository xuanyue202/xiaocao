"""Persistent SQLite cache for XiaocaoClient responses.

Most `/stock/...` endpoints are deterministic for a given (path, params) tuple
once the date in question is in the past — so we can cache the response forever.
Live endpoints (no date arg, or `date == today`) cache with a short TTL.

Schema:

    api_cache (
        endpoint TEXT,
        params_hash TEXT,
        params_json TEXT,
        fetched_at INTEGER,
        historical INTEGER,
        response_json TEXT,       -- legacy/plain fallback
        response_blob BLOB,        -- gzip-compressed UTF-8 JSON
        PRIMARY KEY (endpoint, params_hash)
    )

The cache stores responses as gzip-compressed JSON blobs. Legacy rows with
plain `response_json` are still readable.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import threading
import time
from datetime import date as _date
from pathlib import Path
from typing import Any

_DEFAULT_LIVE_TTL = 30
_TODAY_PAST_DAY_PADDING = 0  # treat today as live; only strictly past dates are historical
_GZIP_LEVEL = 6


# Per-endpoint cache policy. `date_arg` names the params key that, when ≤ today,
# makes the response historical (cache forever). `live_ttl` overrides the
# default TTL for live responses.
ENDPOINT_POLICY: dict[str, dict[str, Any]] = {
    # Date-anchored, historical when date is past
    "/stock/xiao_cao_industry_block_rank": {"date_arg": "date", "live_ttl": 10},
    "/stock/xiao_cao_block_category_rank_v3": {"date_arg": "date", "live_ttl": 10},
    "/stock/xiao_cao_dynamic_index": {"date_arg": "tradeDate", "live_ttl": 10},
    "/stock/xiao_cao_industry_block_dynamic_index": {"date_arg": "tradeDate", "live_ttl": 10},
    "/stock/focus_xiao_cao_index/get_code_list_v2": {"date_arg": "date", "live_ttl": 10},
    "/stock/xiao_cao_index_v2": {"date_arg": "date", "live_ttl": 10},
    "/stock/xiao_cao_block_score": {"date_arg": "date", "live_ttl": 10},
    "/stock/xiao_cao_environment_second_line_v2": {"date_arg": "date", "live_ttl": 10},
    "/stock/xiao_cao_environment_second_line_selection": {"date_arg": "date", "live_ttl": 10},
    "/stock/xiao_cao_environment_minute_line": {"date_arg": "tradeDate", "live_ttl": 5},
    "/stock/xiao_cao_block_detail": {"date_arg": "tradeDate", "live_ttl": 10},
    "/stock/sort_v2": {"date_arg": "date", "live_ttl": 10},
    "/stock/get_code_by_xiao_cao_block": {"date_arg": "tradeDate", "live_ttl": 10},
    "/stock/stock_call_auction": {"date_arg": "tradeDate", "live_ttl": 3},
    "/stock/date_kline": {"date_arg": "paramTime", "live_ttl": 10},
    "/stock/xiao_cao_block_date_kline": {"date_arg": "paramTime", "live_ttl": 10},
    "/stock/trade_cal": {"date_arg": "endDate", "live_ttl": 3600},
    # Always live
    "/stock/market_overview": {"date_arg": None, "live_ttl": 10},
    "/stock/stock_info": {"date_arg": None, "live_ttl": 86400},
    "/stock/minute_line": {"date_arg": None, "live_ttl": 5},
    "/stock/each_trade": {"date_arg": None, "live_ttl": 3},
    "/stock/get_technical_index": {"date_arg": None, "live_ttl": 10},
    "/stock/get_technical_index_history": {"date_arg": "tradeDate", "live_ttl": 10},
    "/stock/next_trade_cal": {"date_arg": None, "live_ttl": 600},
    "/stock/second_line": {"date_arg": None, "live_ttl": 3},
    "/stock/second_line_detail_info": {"date_arg": None, "live_ttl": 3},
    "/stock/xiao_cao_week_stats": {"date_arg": None, "live_ttl": 3600},
    "/stock/xiao_cao_emotions_height": {"date_arg": None, "live_ttl": 10},
}


def canonical_params(payload: dict[str, Any]) -> str:
    """Stable JSON for cache keying. Lists ARE preserved as-is (not re-sorted)
    because list order can be semantically meaningful (e.g. stockIds order
    affects how callers consume the response). Top-level dict keys are sorted.
    """
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_date(value: str) -> str:
    s = str(value)[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def _payload_inner(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the {params: ...} envelope when present, else return payload."""
    if isinstance(payload, dict) and isinstance(payload.get("params"), dict):
        return payload["params"]
    return payload if isinstance(payload, dict) else {}


def is_historical(endpoint: str, payload: dict[str, Any], today_iso: str) -> bool:
    """Whether the response is anchored to a past date and can be cached forever."""
    policy = ENDPOINT_POLICY.get(endpoint, {})
    date_arg = policy.get("date_arg")
    inner = _payload_inner(payload)
    keys: tuple[str, ...]
    if date_arg:
        keys = (date_arg,)
    else:
        # No declared date arg → endpoint is live (e.g. market_overview).
        return False
    for k in keys:
        v = inner.get(k)
        if not isinstance(v, str) or len(v) < 8:
            continue
        normalized = _normalize_date(v)
        if normalized < today_iso:
            return True
    return False


def encode_cached_response(response: Any) -> bytes:
    response_json = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    return gzip.compress(response_json.encode("utf-8"), compresslevel=_GZIP_LEVEL, mtime=0)


def decode_cached_response(response_blob: bytes | None, response_json: str | None) -> Any:
    if response_blob:
        raw = gzip.decompress(response_blob).decode("utf-8")
        return json.loads(raw)
    if response_json:
        return json.loads(response_json)
    raise ValueError("Cached response row has neither response_blob nor response_json")


def is_empty_response(response: Any) -> bool:
    """True for backend "not populated yet" shapes that should not poison live cache."""
    if response is None:
        return True
    if isinstance(response, list):
        return len(response) == 0
    if isinstance(response, dict):
        if not response:
            return True
        return all(is_empty_response(value) for value in response.values())
    return False


def _api_cache_columns(conn: sqlite3.Connection) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute("PRAGMA table_info(api_cache)").fetchall()}
    except sqlite3.Error:
        return set()


def iter_cached_responses(
    cache_path: str | Path,
    endpoint: str,
    *,
    include_params: bool = False,
) -> Any:
    """Yield decoded cached responses for an endpoint.

    This is the compatibility boundary for callers that used to select
    `response_json` directly. It reads both new gzip BLOB rows and legacy
    plain-text rows.
    """
    with sqlite3.connect(str(cache_path)) as conn:
        columns = _api_cache_columns(conn)
        if "response_blob" in columns:
            select = "params_json, response_blob, response_json" if include_params else "response_blob, response_json"
        else:
            select = "params_json, NULL, response_json" if include_params else "NULL, response_json"
        rows = conn.execute(
            f"SELECT {select} FROM api_cache WHERE endpoint=?",
            (endpoint,),
        ).fetchall()
    for row in rows:
        if include_params:
            params_json, response_blob, response_json = row
            yield params_json, decode_cached_response(response_blob, response_json)
        else:
            response_blob, response_json = row
            yield decode_cached_response(response_blob, response_json)


class SQLiteCache:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    endpoint TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    fetched_at INTEGER NOT NULL,
                    historical INTEGER NOT NULL,
                    response_json TEXT,
                    response_blob BLOB,
                    PRIMARY KEY (endpoint, params_hash)
                )
                """
            )
            columns = _api_cache_columns(conn)
            if "response_blob" not in columns:
                conn.execute("ALTER TABLE api_cache ADD COLUMN response_blob BLOB")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_endpoint ON api_cache(endpoint)")
            # Per-trade outcomes for adaptive mode gating. (mode, trade_date,
            # code) is the key — same code may appear on different dates.
            # `trade_date` is the buyDate (ISO YYYY-MM-DD).
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mode_history (
                    mode TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    code TEXT NOT NULL,
                    return_pct REAL NOT NULL,
                    PRIMARY KEY (mode, trade_date, code)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mode_date ON mode_history(mode, trade_date)")
            conn.commit()

    @staticmethod
    def _hash(params_json: str) -> str:
        return hashlib.sha256(params_json.encode("utf-8")).hexdigest()

    def get(self, endpoint: str, payload: dict[str, Any]) -> Any | None:
        params_json = canonical_params(payload)
        params_hash = self._hash(params_json)
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT response_blob, response_json, fetched_at, historical FROM api_cache "
                "WHERE endpoint=? AND params_hash=?",
                (endpoint, params_hash),
            ).fetchone()
        if row is None:
            return None
        response_blob, response_json, fetched_at, historical = row
        response = decode_cached_response(response_blob, response_json)
        if historical:
            return response
        policy = ENDPOINT_POLICY.get(endpoint, {})
        ttl = int(policy.get("live_ttl", _DEFAULT_LIVE_TTL))
        if time.time() - fetched_at < ttl:
            return response
        return None

    def put(self, endpoint: str, payload: dict[str, Any], response: Any) -> None:
        params_json = canonical_params(payload)
        params_hash = self._hash(params_json)
        today_iso = _date.today().isoformat()
        hist = 1 if is_historical(endpoint, payload, today_iso) else 0
        if not hist and is_empty_response(response):
            return
        response_blob = encode_cached_response(response)
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO api_cache
                  (endpoint, params_hash, params_json, fetched_at, historical, response_json, response_blob)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    endpoint,
                    params_hash,
                    params_json,
                    int(time.time()),
                    hist,
                    "",
                    response_blob,
                ),
            )
            conn.commit()

    def clear(self, endpoint: str | None = None) -> int:
        with self._lock, sqlite3.connect(self.path) as conn:
            if endpoint:
                cur = conn.execute("DELETE FROM api_cache WHERE endpoint=?", (endpoint,))
            else:
                cur = conn.execute("DELETE FROM api_cache")
            conn.commit()
            return cur.rowcount

    # ---------- mode_history (adaptive gate inputs) ------------------------

    def record_trades(self, trades: list[dict[str, Any]]) -> int:
        """Persist closed-trade outcomes. Idempotent on (mode, trade_date, code)."""
        if not trades:
            return 0
        rows = []
        for t in trades:
            mode = t.get("mode") or t.get("Mode")
            trade_date = t.get("buyDate") or t.get("tradeDate") or t.get("date")
            code = t.get("code") or t.get("stockCode")
            ret = t.get("returnPct")
            if mode is None or trade_date is None or code is None or ret is None:
                continue
            rows.append((str(mode), str(trade_date)[:10], str(code), float(ret)))
        if not rows:
            return 0
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO mode_history(mode, trade_date, code, return_pct) VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    def mode_window_stats(
        self,
        mode: str,
        asof_iso: str,
        window_days: int,
        trade_days: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return n + avg of return_pct for `mode` over the last `window_days`
        days strictly BEFORE `asof_iso`.

        When `trade_days` is provided, the window counts TRADING days using
        that ordered list. When omitted, falls back to calendar-day counting.

        Trading-day mode is preferred for adaptive gating since 小草 thinks in
        trading-day rhythms (3/5/10/20) — calendar days under-count due to
        weekends + holidays.
        """
        from datetime import date as _date, timedelta as _td

        asof = asof_iso[:10]
        if trade_days is not None:
            try:
                idx = trade_days.index(asof)
            except ValueError:
                # asof not in calendar; treat as "after the last trading day"
                idx = len(trade_days)
            lower_idx = max(0, idx - window_days)
            lower = trade_days[lower_idx] if lower_idx < len(trade_days) else asof
        else:
            try:
                lower = (_date.fromisoformat(asof) - _td(days=window_days)).isoformat()
            except ValueError:
                return {"n": 0, "avg": 0.0}
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*), COALESCE(AVG(return_pct), 0)
                FROM mode_history
                WHERE mode = ? AND trade_date >= ? AND trade_date < ?
                """,
                (mode, lower, asof),
            ).fetchone()
        return {"n": int(row[0] or 0), "avg": float(row[1] or 0.0)}

    def has_seed_evidence(
        self,
        asof_iso: str,
        trade_days: list[str] | None = None,
        window_days: int = 20,
        n_min: int = 3,
    ) -> bool:
        """True if at least one mode has >= n_min trades in the trailing window
        before `asof_iso`. Used to decide whether adaptive gating has enough
        prior data to function (vs. cascading Tier 4 lockouts on cold start).
        """
        from datetime import date as _date, timedelta as _td

        asof = asof_iso[:10]
        if trade_days is not None:
            try:
                idx = trade_days.index(asof)
            except ValueError:
                idx = len(trade_days)
            lower_idx = max(0, idx - window_days)
            lower = trade_days[lower_idx] if lower_idx < len(trade_days) else asof
        else:
            try:
                lower = (_date.fromisoformat(asof) - _td(days=window_days)).isoformat()
            except ValueError:
                return False
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                """
                SELECT MAX(c) FROM (
                    SELECT COUNT(*) AS c FROM mode_history
                    WHERE trade_date >= ? AND trade_date < ?
                    GROUP BY mode
                )
                """,
                (lower, asof),
            ).fetchone()
        return bool(row and row[0] is not None and row[0] >= n_min)

    def clear_mode_history(
        self,
        mode: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> int:
        clauses = []
        params: list[Any] = []
        if mode:
            clauses.append("mode=?")
            params.append(mode)
        if date_start:
            clauses.append("trade_date >= ?")
            params.append(date_start)
        if date_end:
            clauses.append("trade_date < ?")
            params.append(date_end)
        sql = "DELETE FROM mode_history" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        with self._lock, sqlite3.connect(self.path) as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount

    def stats(self) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT endpoint, COUNT(*), SUM(historical) FROM api_cache GROUP BY endpoint"
            ).fetchall()
        return [
            {"endpoint": r[0], "rows": int(r[1]), "historical": int(r[2] or 0)}
            for r in rows
        ]
