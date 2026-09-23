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


def test_early_auth_probe_does_not_require_unpublished_opening_scores():
    from xiaocao.api.preflight import authentication_preflight
    c = client_fixture()
    c.get_xiao_cao_index_v2.return_value = None
    result = authentication_preflight(c, "2026-09-15")
    assert result["status"] == "reachable"
    assert result["source_completeness_proven"] is False
    assert c.method_calls == [("get_code_list_v2", ("2026-09-15", "jieli"), {})]


def test_early_auth_probe_preserves_auth_and_transport_failures():
    from xiaocao.api.errors import ApiError
    from xiaocao.api.preflight import authentication_preflight
    for error, reason in [(ApiAuthError("990502"), "MARKET_DATA_AUTH_REQUIRED"),
                          (ApiError("network"), "MARKET_DATA_UNAVAILABLE_OR_INVALID")]:
        c = client_fixture()
        c.get_code_list_v2.side_effect = error
        result = authentication_preflight(c, "2026-09-15")
        assert result["status"] == "blocked" and result["reason"] == reason
        assert len(c.method_calls) == 1


def test_early_auth_probe_reports_sanitized_login_failure():
    from xiaocao.api.preflight import authentication_preflight
    c = client_fixture()
    c.get_code_list_v2.side_effect = ApiAuthError(
        "MARKET_LOGIN_REQUIRES_USER",
        failure_category="MARKET_LOGIN_REQUIRES_USER",
        official_login_code=9001,
    )
    result = authentication_preflight(c, "2026-09-23")
    assert result["reason"] == "MARKET_DATA_AUTH_REQUIRED"
    assert result["checks"][0]["auth_failure_category"] == "MARKET_LOGIN_REQUIRES_USER"
    assert result["checks"][0]["official_login_code"] == 9001
