from unittest.mock import Mock

from xiaocao.api.errors import ApiAuthError
from xiaocao.api.preflight import core_preflight


def client_fixture():
    c = Mock()
    c.get_industry_block_rank.return_value = []
    c.get_block_category_rank_v3.return_value = []
    c.get_code_list_v2.return_value = []
    c.get_xiao_cao_index_v2.return_value = [{"code": "600519.XSHG", "xcjw": 0, "jsjl": 0, "cjs": 0, "jssb": 0}]
    c.get_technical_index.return_value = [{"code": "600519.XSHG", "ema": 1, "aaaLine": 2, "bbbLine": 3}]
    return c


def test_preflight_checks_core_even_when_pools_are_empty():
    c = client_fixture()
    r = core_preflight(c, "2026-09-14", pause=lambda _: None)
    assert r["status"] == "reachable" and len(r["checks"]) == 7
    assert r["source_completeness_proven"] is False
    assert c.get_code_list_v2.call_count == 3


def test_preflight_stops_on_auth_rejection():
    c = client_fixture()
    c.get_industry_block_rank.side_effect = ApiAuthError("990502")
    r = core_preflight(c, "2026-09-14", pause=lambda _: None)
    assert r["reason"] == "MARKET_DATA_AUTH_REQUIRED"
    c.get_code_list_v2.assert_not_called()


def test_preflight_rejects_missing_core_values():
    c = client_fixture()
    c.get_xiao_cao_index_v2.return_value[0]["xcjw"] = None
    r = core_preflight(c, "2026-09-14", pause=lambda _: None)
    assert r["status"] == "blocked"
    assert r["checks"][-1]["source"] == "stock_core"
