from __future__ import annotations

import time

import pytest

from xiaocao.api.cache import (
    SQLiteCache,
    canonical_params,
    is_historical,
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


def test_sqlite_cache_round_trip(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {"date": "2020-01-01", "code": "X"}}
    assert db.get("/stock/sort_v2", payload) is None
    db.put("/stock/sort_v2", payload, {"data": [1, 2, 3]})
    assert db.get("/stock/sort_v2", payload) == {"data": [1, 2, 3]}


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


def test_sqlite_live_expires_after_ttl(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    payload = {"params": {}}
    db.put("/stock/market_overview", payload, "fresh")
    # Force fetched_at past TTL (60s for market_overview).
    import sqlite3
    with sqlite3.connect(db.path) as c:
        c.execute("UPDATE api_cache SET fetched_at = ?", (int(time.time()) - 3600,))
        c.commit()
    assert db.get("/stock/market_overview", payload) is None


def test_sqlite_clear(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    db.put("/stock/a", {"params": {}}, 1)
    db.put("/stock/b", {"params": {}}, 2)
    assert db.clear("/stock/a") == 1
    assert db.get("/stock/a", {"params": {}}) is None
    assert db.get("/stock/b", {"params": {}}) == 2
    assert db.clear() == 1
    assert db.get("/stock/b", {"params": {}}) is None


def test_sqlite_stats(tmp_path):
    db = SQLiteCache(tmp_path / "cache.db")
    db.put("/stock/sort_v2", {"params": {"date": "2020-01-01"}}, [1])
    db.put("/stock/sort_v2", {"params": {"date": "2020-01-02"}}, [2])
    db.put("/stock/market_overview", {"params": {}}, {})
    stats = {row["endpoint"]: row for row in db.stats()}
    assert stats["/stock/sort_v2"]["rows"] == 2
    assert stats["/stock/sort_v2"]["historical"] == 2
    assert stats["/stock/market_overview"]["rows"] == 1
    assert stats["/stock/market_overview"]["historical"] == 0


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
