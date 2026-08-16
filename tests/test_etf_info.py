from __future__ import annotations

from typing import Any

from xiaocao.api.cache import SQLiteCache, should_persist
from xiaocao.api.client import XiaocaoClient


class _StubClient(XiaocaoClient):
    def __init__(self, result: Any):
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.cache = None

    def post(self, path: str, params: dict[str, Any]) -> Any:  # type: ignore[override]
        self.calls.append((path, params))
        return self.result


def test_etf_info_uses_trade_date_and_keeps_catalog_provenance() -> None:
    client = _StubClient({
        "list": [{
            "code": "510300.XSHG",
            "stockCode": "510300",
            "stockName": "沪深300ETF",
            "tradeDate": "20260814",
            "statusType": 1,
        }],
    })

    rows = client.etf_info("2026-08-14")

    assert client.calls == [
        ("/stock/etf_info", {"tradeDate": "20260814"}),
    ]
    assert rows[0]["code"] == "510300.XSHG"
    assert rows[0]["instrument_type"] == "etf"
    assert rows[0]["catalog_trade_date"] == "2026-08-14"
    assert rows[0]["provenance"] == {
        "source": "xiaocao_api",
        "endpoint": "/stock/etf_info",
        "trade_date": "2026-08-14",
    }


def test_etf_info_current_date_is_explicit_for_cache_key(monkeypatch) -> None:
    client = _StubClient([])
    monkeypatch.setattr("xiaocao.api.client.today_str", lambda: "2026-08-16")

    client.etf_info()

    assert client.calls == [
        ("/stock/etf_info", {"tradeDate": "20260816"}),
    ]


def test_etf_catalog_is_cacheable_by_trade_date(tmp_path) -> None:
    cache = SQLiteCache(tmp_path / "cache.db")
    client = XiaocaoClient(cache=cache)
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_do_post(path: str, payload: dict[str, Any]):
        calls.append((path, payload))
        return [{"code": "510300.XSHG", "tradeDate": "20260814"}]

    client._do_post = fake_do_post  # type: ignore[assignment]

    first = client.etf_info("2026-08-14")
    second = client.etf_info("2026-08-14")

    assert first == second
    assert len(calls) == 1
    assert should_persist(
        "/stock/etf_info",
        {"params": {"tradeDate": "20260814"}},
        "2026-08-16",
    ) is True
