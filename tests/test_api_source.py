from __future__ import annotations

from xiaocao.datasource.api_source import ApiDataSource


def test_live_universe_excludes_directory_orphans_with_proof():
    from types import SimpleNamespace

    reads = []
    client = SimpleNamespace(
        stock_info=lambda **kwargs: reads.append(kwargs) or [{"stockId": "A.XSHE"}],
        get_code_list_v2=lambda *args: ["A.XSHE", "301139.XSHE"],
        get_code_by_xiao_cao_block=lambda *args, **kwargs: ["301139.XSHE", "A.XSHE"],
        get_xiao_cao_index_v2=lambda day, codes, *args: [{"code": c} for c in codes],
    )
    source = ApiDataSource(client, resolve_security_universe=True)
    source.begin_observation(1)
    assert source.get_pool("2026-10-19", "qibao") == ["A.XSHE"]
    assert source.get_direction_codes("2026-10-19") == ["A.XSHE"]
    assert reads == [{"use_cache": False, "strict": True}]
    pool = next(r for r in source.observations if r["source"] == "pool:qibao")
    directory = next(r for r in source.observations if r["source"] == "security_directory")
    assert pool["raw_code_count"] == 2 and pool["admitted_code_count"] == 1
    assert pool["excluded_codes"] == ["301139.XSHE"]
    assert pool["exclusion_reason"] == "NOT_IN_SECURITY_DIRECTORY"
    assert pool["security_directory_sha256"] == directory["response_sha256"]
    assert source.get_stock_index("2026-10-19", ["A.XSHE"]) == [{"code": "A.XSHE"}]


def test_directory_failure_never_becomes_a_blanket_exclusion():
    import pytest
    from types import SimpleNamespace
    from xiaocao.api.errors import ApiSourceNotReadyError, ApiSchemaError

    for rows, error in [([], ApiSourceNotReadyError), ([{"stockId": None}], ApiSchemaError)]:
        source = ApiDataSource(SimpleNamespace(stock_info=lambda **kwargs: rows),
                               resolve_security_universe=True)
        source.begin_observation(1)
        with pytest.raises(error):
            source.get_pool("2026-10-19", "qibao")
        assert source.observations[-1]["status"] == "error"


def test_directory_admitted_missing_detail_still_blocks():
    from types import SimpleNamespace

    source = ApiDataSource(SimpleNamespace(
        stock_info=lambda **kwargs: [{"stockId": "A.XSHE"}, {"stockId": "B.XSHE"}],
        get_code_list_v2=lambda *args: ["A.XSHE", "B.XSHE"],
        get_xiao_cao_index_v2=lambda *args: [{"code": "A.XSHE"}],
    ), resolve_security_universe=True)
    source.begin_observation(1)
    codes = source.get_pool("2026-10-19", "qibao")
    source.get_stock_index("2026-10-19", codes)
    assert source.observations[-1]["status"] == "partial"
    assert source.observations[-1]["missing_codes"] == ["B.XSHE"]


def test_directory_refresh_can_admit_a_previously_excluded_code():
    from types import SimpleNamespace
    from datetime import datetime, timedelta, timezone

    directory = [[{"stockId": "A.XSHE"}]]
    source = ApiDataSource(SimpleNamespace(
        stock_info=lambda **kwargs: directory[0],
        get_code_list_v2=lambda *args: ["A.XSHE", "B.XSHE"],
    ), resolve_security_universe=True)
    source.begin_observation(1)
    assert source.get_pool("2026-10-19", "qibao") == ["A.XSHE"]
    for _, record, _ in source._validated.values():
        if record["source"] == "security_directory":
            record["observed_at"] = (datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat()
    directory[0] = [{"stockId": "A.XSHE"}, {"stockId": "B.XSHE"}]
    source.begin_observation(2, retry_missing=True)
    assert source.get_pool("2026-10-19", "qibao") == ["A.XSHE", "B.XSHE"]
    assert source.observations[-1]["excluded_codes"] == []
    assert source.revalidate_observation(3)
    assert source.observations[-1]["excluded_codes"] == []


def test_live_directory_read_bypasses_cached_catalog(monkeypatch):
    from xiaocao.api.client import XiaocaoClient

    client = XiaocaoClient(base_url="https://example.invalid")
    monkeypatch.setattr(client, "post", lambda *args: [{"code": "OLD.XSHE", "statusType": 1}])
    reads = []
    monkeypatch.setattr(client, "_do_post", lambda *args:
        reads.append(args) or [{"code": "NEW.XSHE", "statusType": 1}])
    assert client.stock_info()[0]["stockId"] == "OLD.XSHE"
    assert client.stock_info(use_cache=False)[0]["stockId"] == "NEW.XSHE"
    assert reads == [("/stock/stock_info", {"params": {}})]


def test_strict_directory_rejects_malformed_raw_rows_before_normalization(monkeypatch):
    import pytest
    from xiaocao.api.client import XiaocaoClient
    from xiaocao.api.errors import ApiSchemaError

    client = XiaocaoClient(base_url="https://example.invalid")
    responses = [
        [{"code": "000001.XSHE", "statusType": 1}, 42],
        [{"code": ".", "statusType": 1}],
        [{"code": "000001.XSHE", "statusType": "1"}],
    ]
    for response in responses:
        monkeypatch.setattr(client, "_do_post", lambda *args: response)
        source = ApiDataSource(client, resolve_security_universe=True)
        source.begin_observation(1)
        with pytest.raises(ApiSchemaError, match="DIRECTORY_INVALID"):
            source.get_pool("2026-10-19", "qibao")
        assert source.observations[-1]["status"] == "error"


def test_all_orphan_pool_keeps_raw_proof_without_sorting_global_market():
    from types import SimpleNamespace

    source = ApiDataSource(SimpleNamespace(
        stock_info=lambda **kwargs: [{"stockId": "A.XSHE"}],
        get_code_list_v2=lambda *args: ["301139.XSHE"],
    ), resolve_security_universe=True)
    source.begin_observation(1)
    codes = source.get_pool("2026-10-19", "qibao")
    assert codes == source.sort_codes("2026-10-19", codes) == []
    assert source.observations[-1]["status"] == "populated"
    assert source.observations[-1]["excluded_codes"] == ["301139.XSHE"]


def test_historical_source_keeps_codes_outside_current_directory():
    from types import SimpleNamespace

    source = ApiDataSource(SimpleNamespace(get_code_list_v2=lambda *args: ["301139.XSHE"]))
    source.begin_observation(1)
    assert source.get_pool("2026-05-07", "qibao") == ["301139.XSHE"]


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


def test_retry_missing_bypasses_cached_empty_without_refetching_valid_requests(tmp_path, monkeypatch):
    from xiaocao.api.client import XiaocaoClient
    from xiaocao.api.cache import SQLiteCache
    client = XiaocaoClient(base_url='https://example.invalid', cache=SQLiteCache(tmp_path/'cache.db'))
    calls = []
    def upstream(path, payload):
        calls.append((path, payload))
        return [] if len(calls) == 1 else ['000001.XSHE']
    monkeypatch.setattr(client, '_do_post', upstream)
    monkeypatch.chdir(tmp_path)
    source = ApiDataSource(client)
    source.begin_observation(1)
    assert source.get_direction_codes('2026-10-29') == []
    source.begin_observation(2, retry_missing=True)
    assert source.get_direction_codes('2026-10-29') == ['000001.XSHE']
    assert len(calls) == 2
    source.begin_observation(3, retry_missing=True)
    assert source.get_direction_codes('2026-10-29') == ['000001.XSHE']
    assert len(calls) == 2


def test_old_day_successful_http_response_retries_exact_key_uncached(tmp_path,monkeypatch):
    from xiaocao.api.client import XiaocaoClient
    from xiaocao.api.cache import SQLiteCache
    from xiaocao.api.errors import ApiSourceNotReadyError
    import pytest
    client=XiaocaoClient(cache=SQLiteCache(tmp_path/'cache.sqlite3'))
    calls=[]
    def post(path,payload):
        calls.append(path)
        return [{'code':'000001.XSHE','tradeDate':'20261028' if len(calls)==1 else '20261029'}]
    monkeypatch.setattr(client,'_do_post',post)
    source=ApiDataSource(client)
    source.begin_observation(1)
    fetch=lambda:client.post('/stock/test-source',{'date':'20261029'})
    with pytest.raises(ApiSourceNotReadyError):source._observe('fixture','2026-10-29',fetch)
    source.begin_observation(2,retry_missing=True)
    assert source._observe('fixture','2026-10-29',fetch)[0]['tradeDate']=='20261029'
    assert len(calls)==2
