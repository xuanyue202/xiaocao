from __future__ import annotations

from xiaocao.datasource.api_source import ApiDataSource


class _OutOfOrderIndexClient:
    def get_xiao_cao_index_v2(self, date: str, codes: list[str], hpqb_state: int, lpdx_state: int):
        return [
            {"code": "C.XSHE", "xcjw": 300},
            {"code": "A.XSHE", "xcjw": 100},
            {"code": "B.XSHE", "xcjw": 200},
        ]


def test_get_stock_index_preserves_requested_code_order() -> None:
    source = ApiDataSource(_OutOfOrderIndexClient())  # type: ignore[arg-type]

    rows = source.get_stock_index("2026-05-18", ["A.XSHE", "B.XSHE", "C.XSHE"])

    assert [row["code"] for row in rows] == ["A.XSHE", "B.XSHE", "C.XSHE"]


def test_readiness_keeps_missing_and_empty_sources_explicit():
    from types import SimpleNamespace
    calls = []
    def index(*args):
        calls.append(args)
        return [{"code": "A.XSHE"}]
    source = ApiDataSource(SimpleNamespace(get_xiao_cao_index_v2=index,
        get_code_list_v2=lambda *args: []))
    source.begin_observation(1)
    assert source.get_stock_index("2026-09-11", ["A.XSHE", "B.XSHE"]) == [{"code": "A.XSHE"}]
    assert source.get_pool("2026-09-11", 1) == []
    assert source.observations[0]["status"] == "partial"
    assert source.observations[0]["missing_codes"] == ["B.XSHE"]
    assert source.observations[1]["status"] == "empty_unconfirmed"
    assert len(source.observations[0]["response_sha256"]) == 64 and len(calls) == 1


def test_readiness_records_and_propagates_provider_error():
    import pytest
    from types import SimpleNamespace
    def fail(*args):
        raise RuntimeError("provider unavailable")
    source = ApiDataSource(SimpleNamespace(get_code_list_v2=fail))
    source.begin_observation(2)
    with pytest.raises(RuntimeError):
        source.get_pool("2026-09-11", 1)
    assert source.readiness["sources"][0]["status"] == "error"
    source.begin_observation(3)
    assert source.readiness["sources"] == []
