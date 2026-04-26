from __future__ import annotations

import inspect

import pytest

from xiaocao.api import catalog
from xiaocao.api.catalog import (
    ENDPOINTS,
    EndpointSpec,
    INDICATORS_BACKEND,
    INDICATORS_FRONTEND_ONLY,
    KLINE_ADJUSTMENTS,
    KLINE_FREQS,
    resolve_indicator,
)
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.errors import ApiSchemaError


VALID_BODY_STYLES = {"params", "raw"}
VALID_BASES = {"XC", "PZ"}
VALID_STATUSES = {"stable", "experimental", "planned"}


def test_every_endpoint_has_valid_enum_fields():
    for name, spec in ENDPOINTS.items():
        assert spec.body_style in VALID_BODY_STYLES, name
        assert spec.base in VALID_BASES, name
        assert spec.status in VALID_STATUSES, name
        assert isinstance(spec.auth_required, bool), name


def test_raw_body_endpoints_are_exactly_the_technical_ones():
    raw = {name for name, spec in ENDPOINTS.items() if spec.body_style == "raw"}
    assert raw == {"get_technical_index", "get_technical_index_history"}


def test_all_endpoints_currently_stable():
    # No experimental/planned endpoints right now. When one is added, replace
    # this check with a positive assertion (e.g. ENDPOINTS[name].status == "experimental").
    non_stable = {name for name, spec in ENDPOINTS.items() if spec.status != "stable"}
    assert non_stable == set()


def test_every_endpoint_has_cli_command_and_client_method():
    for name, spec in ENDPOINTS.items():
        assert spec.cli_command, f"{name} missing cli_command"
        assert spec.client_method, f"{name} missing client_method"
        assert spec.source_evidence, f"{name} missing source_evidence"


def test_client_method_names_exist_on_client():
    client_attrs = {n for n, _ in inspect.getmembers(XiaocaoClient, predicate=inspect.isfunction)}
    for name, spec in ENDPOINTS.items():
        assert spec.client_method in client_attrs, (
            f"{name}.client_method={spec.client_method!r} not found on XiaocaoClient"
        )


def test_as_row_field_set_matches_dataclass():
    spec = next(iter(ENDPOINTS.values()))
    row_keys = set(spec.as_row().keys())
    field_names = {f.name for f in spec.__dataclass_fields__.values()}
    assert row_keys == field_names


def test_indicators_backend_set():
    assert set(INDICATORS_BACKEND) == {
        "smallGrass", "vol", "amt", "macd", "rsi", "kdj", "boll"
    }


def test_indicators_frontend_only_set():
    assert set(INDICATORS_FRONTEND_ONLY) == {
        "smallGrassTrend", "klinesma", "mike"
    }


def test_resolve_indicator_accepts_backend_values():
    for name in INDICATORS_BACKEND:
        assert resolve_indicator(name) == name


def test_resolve_indicator_rejects_frontend_values():
    for name in INDICATORS_FRONTEND_ONLY:
        with pytest.raises(ApiSchemaError, match="rendered locally"):
            resolve_indicator(name)


def test_resolve_indicator_rejects_unknown():
    with pytest.raises(ApiSchemaError, match="Unknown indicator"):
        resolve_indicator("nonsense")


def test_kline_freqs_complete():
    assert set(KLINE_FREQS) == {"5min", "15min", "30min", "60min", "D", "W", "M", "Q", "Y"}


def test_kline_adjustments_complete():
    assert set(KLINE_ADJUSTMENTS) == {"qfq", "bfq"}
