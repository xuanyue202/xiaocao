from __future__ import annotations

import time
from datetime import date

import pytest

from xiaocao.api.cache import (
    SQLiteCache,
    canonical_params,
    default_archive_path,
    is_historical,
    iter_cached_responses,
    should_persist,
)


def test_canonical_params_stable_across_key_order():
    a = {"params": {"date": "2026-04-25", "stockIds": ["A", "B"]}}
    b = {"params": {"stockIds": ["A", "B"], "date": "2026-04-25"}}
    assert canonical_params(a) == canonical_params(b)


def test_canonical_params_distinguishes_list_order():
    # Different list ordering MUST produce different keys (semantic).
    a = canonical_params({"params": {"stockIds": ["A", "B"]}})
    b = canonical_params({"params": {"stockIds": ["B", "A"]}})
    assert a != b


def test_is_historical_recognizes_past_date():
    payload = {"params": {"date": "2020-01-01"}}
    assert is_historical("/stock/sort_v2", payload, today_iso="2026-04-25") is True


def test_is_historical_today_is_live():
    payload = {"params": {"date": "2026-04-25"}}
    assert is_historical("/stock/sort_v2", payload, today_iso="2026-04-25") is False


def test_is_historical_unknown_endpoint_is_live():
    payload = {"params": {"date": "2020-01-01"}}
    assert is_historical("/stock/no_policy_endpoint", payload, today_iso="2026-04-25") is False


def test_should_persist_skips_volatile_realtime_rows():
    assert should_persist("/stock/second_line", {"params": {"code": "000001.XSHE"}}, "2026-04-25") is False
    assert should_persist("/stock/market_overview", {"params": {}}, "2026-04-25") is False


def test_should_persist_keeps_slow_metadata_rows():
    assert should_persist("/stock/stock_info", {"params": {}}, "2026-04-25") is True
    assert should_persist("/stock/xiao_cao_week_stats", {"params": {}}, "2026-04-25") is True


def test_minute_line_history_requires_trade_date_and_count():
    today = "2026-04-25"
    with_date_only = {"params": {"code": "000001.XSHE", "tradeDate": "20200101"}}
    with_date_and_count = {"params": {"code": "000001.XSHE", "tradeDate": "20200101", "count": 241}}
    assert is_historical("/stock/minute_line", with_date_only, today) is False
    assert is_historical("/stock/minute_line", with_date_and_count, today) is True


def test_sqlite_cache_round_trip(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"date": "2020-01-01", "code": "X"}}
    assert db.get("/stock/sort_v2", payload) is None
    db.put("/stock/sort_v2", payload, {"data": [1, 2, 3]})
    assert db.get("/stock/sort_v2", payload) == {"data": [1, 2, 3]}


def test_sqlite_cache_stores_compressed_blob(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"date": "2020-01-01", "code": "X"}}
    db.put("/stock/sort_v2", payload, {"data": ["same"] * 100})

    import sqlite3
    with sqlite3.connect(db.path) as c:
        response_json, response_blob = c.execute(
            "SELECT response_json, response_blob FROM api_cache"
        ).fetchone()
    assert response_json == ""
    assert isinstance(response_blob, bytes)
    assert db.get("/stock/sort_v2", payload) == {"data": ["same"] * 100}


def test_sqlite_cache_reads_legacy_plain_response_json(tmp_path):
    import json
    import sqlite3

    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"date": "2020-01-01"}}
    params_json = canonical_params(payload)
    params_hash = db._hash(params_json)
    with sqlite3.connect(db.path) as c:
        c.execute(
            """
            INSERT INTO api_cache
              (endpoint, params_hash, params_json, fetched_at, historical, response_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("/stock/sort_v2", params_hash, params_json, 0, 1, json.dumps({"legacy": True})),
        )
        c.commit()

    assert db.get("/stock/sort_v2", payload) == {"legacy": True}


def test_iter_cached_responses_handles_plain_and_compressed_rows(tmp_path):
    import json
    import sqlite3

    db = SQLiteCache(tmp_path / "cache.db")
    db.put("/stock/sort_v2", {"params": {"date": "2020-01-01"}}, {"new": 1})

    with sqlite3.connect(db.path) as c:
        c.execute(
            """
            INSERT INTO api_cache
              (endpoint, params_hash, params_json, fetched_at, historical, response_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("/stock/sort_v2", "legacy", "{}", 0, 1, json.dumps({"old": 2})),
        )
        c.commit()

    rows = list(iter_cached_responses(db.path, "/stock/sort_v2"))
    assert {"new": 1} in rows
    assert {"old": 2} in rows


def test_sqlite_historical_never_expires(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"date": "2020-01-01"}}
    db.put("/stock/sort_v2", payload, "old")
    # Forge an ancient fetched_at by direct SQL.
    import sqlite3
    with sqlite3.connect(db.path) as c:
        c.execute("UPDATE api_cache SET fetched_at = 0")
        c.commit()
    assert db.get("/stock/sort_v2", payload) == "old"


def test_sqlite_realtime_rows_are_not_persisted(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"code": "000001.XSHE"}}
    db.put("/stock/second_line", payload, "fresh")

    import sqlite3
    with sqlite3.connect(db.path) as c:
        (rows,) = c.execute("SELECT COUNT(*) FROM api_cache").fetchone()
    assert rows == 0
    assert db.get("/stock/second_line", payload) is None


def test_sqlite_slow_metadata_still_expires_by_ttl(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {}}
    db.put("/stock/xiao_cao_week_stats", payload, {"fresh": True})

    import sqlite3
    with sqlite3.connect(db.path) as c:
        c.execute("UPDATE api_cache SET fetched_at = ?", (int(time.time()) - 7200,))
        c.commit()
    assert db.get("/stock/xiao_cao_week_stats", payload) is None


def test_sqlite_today_date_anchored_rows_are_not_persisted(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"date": date.today().isoformat(), "model": 1}}
    db.put("/stock/xiao_cao_industry_block_rank", payload, [{"num": 1}])

    import sqlite3
    with sqlite3.connect(db.path) as c:
        (rows,) = c.execute("SELECT COUNT(*) FROM api_cache").fetchone()
    assert rows == 0
    assert db.get("/stock/xiao_cao_industry_block_rank", payload) is None


def test_sqlite_does_not_cache_empty_live_responses(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"date": date.today().isoformat()}}
    db.put("/stock/xiao_cao_industry_block_rank", payload, [])
    db.put(
        "/stock/xiao_cao_block_category_rank_v3",
        payload,
        {
            "localNum": None,
            "globalNum": None,
            "localCategoryRankList": None,
            "globalCategoryRankList": None,
        },
    )
    assert db.get("/stock/xiao_cao_industry_block_rank", payload) is None
    assert db.get("/stock/xiao_cao_block_category_rank_v3", payload) is None


def test_sqlite_clear(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    db.put("/stock/sort_v2", {"params": {"date": "2020-01-01"}}, 1)
    db.put("/stock/date_kline", {"params": {"paramTime": "2020-01-01"}}, 2)
    assert db.clear("/stock/sort_v2") == 1
    assert db.get("/stock/sort_v2", {"params": {"date": "2020-01-01"}}) is None
    assert db.get("/stock/date_kline", {"params": {"paramTime": "2020-01-01"}}) == 2
    assert db.clear() == 1
    assert db.get("/stock/date_kline", {"params": {"paramTime": "2020-01-01"}}) is None


def test_sqlite_stats(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    db.put("/stock/sort_v2", {"params": {"date": "2020-01-01"}}, [1])
    db.put("/stock/sort_v2", {"params": {"date": "2020-01-02"}}, [2])
    db.put("/stock/stock_info", {"params": {}}, {"ok": True})
    stats = {row["endpoint"]: row for row in db.stats()}
    assert stats["/stock/sort_v2"]["rows"] == 2
    assert stats["/stock/sort_v2"]["historical"] == 2
    assert stats["/stock/stock_info"]["rows"] == 1
    assert stats["/stock/stock_info"]["historical"] == 0


def test_cache_maintain_archives_old_large_detail_rows(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    old_payload = {"params": {"date": "2020-01-01", "stockIds": ["A"]}}
    fresh_payload = {"params": {"date": "2026-04-20", "stockIds": ["A"]}}
    small_payload = {"params": {"date": "2020-01-01", "model": 1}}
    db.put("/stock/sort_v2", old_payload, {"old": True})
    db.put("/stock/sort_v2", fresh_payload, {"fresh": True})
    db.put("/stock/xiao_cao_industry_block_rank", small_payload, {"small": True})

    result = db.maintain(hot_days=365, today_iso="2026-04-25")

    assert result["archived"] == 1
    assert result["deleted_nonpersistent"] == 0
    assert db.get("/stock/sort_v2", old_payload) == {"old": True}
    assert db.get("/stock/sort_v2", fresh_payload) == {"fresh": True}
    assert db.get("/stock/xiao_cao_industry_block_rank", small_payload) == {"small": True}
    assert default_archive_path(db.path) == db.archive_path

    import sqlite3
    with sqlite3.connect(db.path) as c:
        (hot_old_rows,) = c.execute(
            "SELECT COUNT(*) FROM api_cache WHERE endpoint='/stock/sort_v2' AND params_json=?",
            (canonical_params(old_payload),),
        ).fetchone()
    with sqlite3.connect(db.archive_path) as c:
        (archive_old_rows,) = c.execute(
            "SELECT COUNT(*) FROM api_cache WHERE endpoint='/stock/sort_v2' AND params_json=?",
            (canonical_params(old_payload),),
        ).fetchone()
    assert hot_old_rows == 0
    assert archive_old_rows == 1
    rows = list(iter_cached_responses(db.path, "/stock/sort_v2"))
    assert {"old": True} in rows
    assert {"fresh": True} in rows


def test_cache_maintain_deletes_legacy_volatile_rows(tmp_path):
    import sqlite3

    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"code": "000001.XSHE"}}
    params_json = canonical_params(payload)
    with sqlite3.connect(db.path) as c:
        c.execute(
            """
            INSERT INTO api_cache
              (endpoint, params_hash, params_json, fetched_at, historical, response_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("/stock/second_line", db._hash(params_json), params_json, 0, 0, '"old"'),
        )
        c.commit()

    result = db.maintain(dry_run=True)
    assert result["deleted_nonpersistent"] == 1
    assert db.get("/stock/second_line", payload) is None

    result = db.maintain()
    assert result["deleted_nonpersistent"] == 1
    with sqlite3.connect(db.path) as c:
        (rows,) = c.execute("SELECT COUNT(*) FROM api_cache").fetchone()
    assert rows == 0


def test_cache_maintain_keeps_slow_metadata_rows(tmp_path):
    import sqlite3

    db = SQLiteCache(tmp_path / "cache.db")
    db.put("/stock/stock_info", {"params": {}}, {"slow": True})
    result = db.maintain()
    assert result["deleted_nonpersistent"] == 0
    with sqlite3.connect(db.path) as c:
        (rows,) = c.execute("SELECT COUNT(*) FROM api_cache WHERE endpoint='/stock/stock_info'").fetchone()
    assert rows == 1


def test_client_uses_cache_when_present(tmp_path, monkeypatch):
    """End-to-end: client shouldn't re-call _do_post when the cache has the entry."""
    from xiaocao.api.client import XiaocaoClient

    cache = SQLiteCache(tmp_path / "cache.db")
    client = XiaocaoClient(cache=cache)
    calls = []

    def fake_do_post(path, payload):
        calls.append((path, payload))
        return {"some": "result"}

    client._do_post = fake_do_post  # type: ignore[assignment]

    payload = {"date": "2020-01-01"}
    out1 = client.post("/stock/sort_v2", payload)
    out2 = client.post("/stock/sort_v2", payload)
    assert out1 == out2 == {"some": "result"}
    # Only the first call hits the network; second is cache hit.
    assert len(calls) == 1
