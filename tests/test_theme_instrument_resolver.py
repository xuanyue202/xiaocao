from __future__ import annotations

import pytest

from xiaocao.strategy.theme_instrument_resolver import (
    ThemeInstrumentResolverError,
    ThemeInstrumentUniverse,
    resolve_theme_instruments,
)
from xiaocao.strategy.trend_snapshot import build_trend_snapshot


AS_OF = "2026-08-16T08:00:00Z"


def _snapshot(*themes: dict) -> object:
    return build_trend_snapshot(
        AS_OF,
        generated_at="2026-08-16T08:01:00Z",
        agent_draft={"themes": list(themes)},
    )


def _theme(theme_id: str, display_name: str) -> dict:
    return {
        "theme_id": theme_id,
        "display_name": display_name,
        "direction": "bullish",
        "confidence": 0.8,
        "eligibility": "wait",
    }


def _catalog() -> dict:
    return {
        "version": "catalog-2026-08-16",
        "theme_registry": {
            "version": "theme-registry-2026-08-16",
            "changes": [
                {
                    "change_id": "theme-change-1",
                    "kind": "add_alias",
                    "theme_id": "theme-ai",
                    "reason": "reviewed canonical alias",
                }
            ],
            "themes": [
                {
                    "theme_id": "theme-ai",
                    "display_name": "人工智能",
                    "aliases": [
                        {
                            "alias": "AI",
                            "approved": True,
                            "change_id": "theme-change-1",
                        }
                    ],
                }
            ],
        },
        "blocks": [
            {
                "block_code": "BK-AI",
                "name": "人工智能",
                "theme_ids": ["theme-ai"],
                "constituents": ["000001.XSHE", "300001.XSHE"],
                "provenance": {
                    "source": "xiaocao-block-api",
                    "version": "block-2026-08-16",
                    "evidence_id": "block-evidence-ai",
                },
            }
        ],
        "etfs": [
            {
                "code": "159001.XSHE",
                "name": "人工智能ETF",
                "theme_ids": ["theme-ai"],
                "tracking_block_codes": ["BK-AI"],
                "instrument_type": "etf",
                "lot_size": 100,
                "settlement_cycle": "T+1",
                "market_data_contract": {
                    "status": "verified",
                    "source": "p-xcapi",
                    "version": "quote-v1",
                    "realtime": {"status": "verified"},
                    "minute": {"status": "verified", "price_field": "trade"},
                    "daily": {"status": "verified"},
                    "fill": {"status": "verified"},
                },
                "liquidity": {"turnover_20d": 120000000},
                "trend": {"quality": "supportive"},
                "expression_role": "broad_etf",
                "provenance": {
                    "source": "etf-catalog",
                    "version": "etf-2026-08-16",
                    "evidence_id": "etf-evidence-ai",
                },
            }
        ],
        "stocks": [
            {
                "code": "000001.XSHE",
                "name": "人工智能核心股",
                "theme_ids": ["theme-ai"],
                "block_codes": ["BK-AI"],
                "instrument_type": "equity",
                "lot_size": 100,
                "settlement_cycle": "T+1",
                "market_data_contract": {"status": "verified"},
                "liquidity": {"turnover_20d": 80000000},
                "trend": {"quality": "strong"},
                "relative_strength": 0.92,
                "expression_role": "core_trend_stock",
                "provenance": {
                    "source": "trend-stock-catalog",
                    "version": "stock-2026-08-16",
                    "evidence_id": "stock-evidence-ai",
                },
            },
            {
                "code": "300001.XSHE",
                "name": "人工智能趋势股",
                "theme_ids": ["theme-ai"],
                "block_codes": ["BK-AI"],
                "instrument_type": "equity",
                "lot_size": 100,
                "settlement_cycle": "T+1",
                "market_data_contract": {"status": "verified"},
                "liquidity": {"turnover_20d": 60000000},
                "trend": {"quality": "supportive"},
                "relative_strength": 0.84,
                "expression_role": "core_trend_stock",
                "provenance": {
                    "source": "trend-stock-catalog",
                    "version": "stock-2026-08-16",
                    "evidence_id": "stock-evidence-ai-2",
                },
            },
        ],
    }


def test_resolver_maps_theme_to_block_etf_and_multiple_stocks_with_provenance():
    universe = resolve_theme_instruments(
        _snapshot(_theme("raw-ai", "AI")),
        _catalog(),
    )

    payload = universe.to_dict()
    theme = payload["themes"][0]
    instruments = theme["instruments"]

    assert theme["theme_id"] == "theme-ai"
    assert theme["resolution_status"] == "resolved"
    assert {row["code"] for row in instruments} == {
        "159001.XSHE",
        "000001.XSHE",
        "300001.XSHE",
    }
    assert {row["instrument_type"] for row in instruments} == {"etf", "equity"}
    assert {row["expression_role"] for row in instruments} == {
        "broad_etf",
        "core_trend_stock",
    }
    assert next(row for row in instruments if row["instrument_type"] == "etf")["instrument_status"] == "eligible"
    assert all(row["mapping_evidence"] for row in instruments)
    assert all(
        edge["source"] and edge["source_version"]
        for row in instruments
        for edge in row["mapping_evidence"]
    )
    assert payload["snapshot_sha256"] == universe.snapshot_sha256
    assert payload["binding_receipt"]["universe_sha256"] == universe.universe_sha256


def test_resolver_keeps_multiple_etf_expressions_in_one_theme():
    catalog = _catalog()
    catalog["etfs"].append(
        {
            **catalog["etfs"][0],
            "code": "159002.XSHE",
            "name": "人工智能宽基ETF",
            "provenance": {
                "source": "etf-catalog",
                "version": "etf-2026-08-16",
                "evidence_id": "etf-evidence-ai-2",
            },
        }
    )

    theme = resolve_theme_instruments(
        _snapshot(_theme("theme-ai", "人工智能")),
        catalog,
    ).to_dict()["themes"][0]

    assert {
        row["code"] for row in theme["instruments"] if row["instrument_type"] == "etf"
    } == {"159001.XSHE", "159002.XSHE"}


def test_resolver_is_deterministic_when_catalog_order_and_display_names_change():
    catalog = _catalog()
    first = resolve_theme_instruments(_snapshot(_theme("theme-ai", "人工智能")), catalog)

    reordered = {
        **catalog,
        "blocks": list(reversed(catalog["blocks"])),
        "etfs": list(reversed(catalog["etfs"])),
        "stocks": list(reversed(catalog["stocks"])),
    }
    reordered["stocks"][0] = {
        **reordered["stocks"][0],
        "name": "展示名变化不影响主题身份",
    }
    second = resolve_theme_instruments(_snapshot(_theme("theme-ai", "展示名变化")), reordered)

    assert first.to_dict()["themes"][0]["theme_id"] == "theme-ai"
    assert second.to_dict()["themes"][0]["theme_id"] == "theme-ai"
    assert first.to_dict()["themes"][0]["resolution_status"] == "resolved"
    assert second.to_dict()["themes"][0]["resolution_status"] == "resolved"
    assert [row["code"] for row in first.to_dict()["themes"][0]["instruments"]] == [
        row["code"] for row in second.to_dict()["themes"][0]["instruments"]
    ]


def test_one_stock_can_be_expressed_under_two_themes_without_merging_theme_risk():
    catalog = _catalog()
    catalog["theme_registry"]["themes"].append(
        {
            "theme_id": "theme-semiconductor",
            "display_name": "半导体",
            "aliases": ["芯片"],
        }
    )
    catalog["blocks"].append(
        {
            "block_code": "BK-SEMIS",
            "name": "半导体",
            "theme_ids": ["theme-semiconductor"],
            "constituents": ["000001.XSHE"],
            "provenance": {
                "source": "xiaocao-block-api",
                "version": "block-2026-08-16",
                "evidence_id": "block-evidence-semis",
            },
        }
    )
    catalog["stocks"][0] = {
        **catalog["stocks"][0],
        "theme_ids": ["theme-ai", "theme-semiconductor"],
        "block_codes": ["BK-AI", "BK-SEMIS"],
    }

    universe = resolve_theme_instruments(
        _snapshot(_theme("theme-ai", "人工智能"), _theme("theme-semiconductor", "半导体")),
        catalog,
    ).to_dict()

    by_theme = {
        theme["theme_id"]: {row["code"] for row in theme["instruments"]}
        for theme in universe["themes"]
    }
    assert "000001.XSHE" in by_theme["theme-ai"]
    assert "000001.XSHE" in by_theme["theme-semiconductor"]
    shared = [row for row in universe["instruments"] if row["code"] == "000001.XSHE"]
    assert {row["theme_id"] for row in shared} == {"theme-ai", "theme-semiconductor"}


def test_ambiguous_and_unknown_theme_expressions_remain_unresolved():
    catalog = _catalog()
    catalog["theme_registry"]["themes"].append(
        {
            "theme_id": "theme-semiconductor",
            "display_name": "半导体",
            "aliases": [
                {"alias": "科技", "approved": True, "change_id": "theme-change-2"}
            ],
        }
    )
    catalog["theme_registry"]["changes"].append(
        {
            "change_id": "theme-change-2",
            "kind": "add_alias",
            "theme_id": "theme-semiconductor",
            "reason": "reviewed ambiguous test alias",
        }
    )
    catalog["theme_registry"]["themes"][0]["aliases"].append(
        {"alias": "科技", "approved": True, "change_id": "theme-change-1"}
    )

    universe = resolve_theme_instruments(
        _snapshot(_theme("raw-tech", "科技"), _theme("raw-unknown", "未知主题")),
        catalog,
    ).to_dict()

    by_input = {theme["input_theme_id"]: theme for theme in universe["themes"]}
    assert by_input["raw-tech"]["resolution_status"] == "unresolved"
    assert by_input["raw-tech"]["reason"] == "ambiguous_theme_alias"
    assert by_input["raw-tech"]["instruments"] == []
    assert by_input["raw-unknown"]["reason"] == "unknown_theme"
    assert {row["kind"] for row in universe["unresolved"]} == {"theme"}


def test_missing_etf_contract_metadata_is_visible_and_fail_closed():
    catalog = _catalog()
    catalog["etfs"] = [
        {
            "code": "159999.XSHE",
            "name": "制度未知ETF",
            "theme_ids": ["theme-ai"],
            "instrument_type": "etf",
            "provenance": {
                "source": "etf-catalog",
                "version": "etf-2026-08-16",
                "evidence_id": "etf-evidence-unknown-contract",
            },
        }
    ]
    catalog["stocks"] = []
    catalog["blocks"] = []

    universe = resolve_theme_instruments(
        _snapshot(_theme("theme-ai", "人工智能")),
        catalog,
    ).to_dict()

    instrument = universe["themes"][0]["instruments"][0]
    assert instrument["instrument_type"] == "etf"
    assert instrument["instrument_status"] == "ineligible"
    assert instrument["lot_size"] is None
    assert instrument["settlement_cycle"] is None
    assert {
        "etf_lot_size_unknown",
        "etf_settlement_cycle_unknown",
        "market_data_contract_unverified",
    }.issubset(instrument["non_tradable_reasons"])


def test_unreviewed_author_specific_alias_is_not_a_registry_mapping():
    catalog = _catalog()
    catalog["theme_registry"]["themes"][0]["aliases"] = [
        {
            "alias": "作者专属AI",
            "approved": True,
            "author": "someone",
        }
    ]

    universe = resolve_theme_instruments(
        _snapshot(_theme("raw-author-alias", "作者专属AI")),
        catalog,
    ).to_dict()

    theme = universe["themes"][0]
    assert theme["resolution_status"] == "unresolved"
    assert theme["reason"] == "unknown_theme"


def test_missing_mapping_provenance_makes_the_candidate_ineligible():
    catalog = _catalog()
    catalog["stocks"][0] = {key: value for key, value in catalog["stocks"][0].items() if key != "provenance"}
    catalog["etfs"] = []
    catalog["blocks"] = []

    theme = resolve_theme_instruments(
        _snapshot(_theme("theme-ai", "人工智能")),
        catalog,
    ).to_dict()["themes"][0]
    instrument = theme["instruments"][0]

    assert instrument["instrument_status"] == "ineligible"
    assert "mapping_provenance_incomplete" in instrument["non_tradable_reasons"]


def test_low_confidence_alias_and_catalog_mapping_fail_closed():
    catalog = _catalog()
    catalog["theme_registry"]["themes"][0]["aliases"] = [
        {"alias": "低置信AI", "approved": True, "confidence": 0.4}
    ]
    for stock in catalog["stocks"]:
        stock["theme_ids"] = ["theme-ai"]
        stock["mapping_confidence"] = 0.4
    catalog["etfs"] = []
    catalog["blocks"] = []

    alias_universe = resolve_theme_instruments(
        _snapshot(_theme("raw-low", "低置信AI")),
        catalog,
    ).to_dict()
    assert alias_universe["themes"][0]["resolution_status"] == "unresolved"

    direct_universe = resolve_theme_instruments(
        _snapshot(_theme("theme-ai", "人工智能")),
        catalog,
    ).to_dict()
    assert direct_universe["themes"][0]["instruments"] == []

    block_only_catalog = _catalog()
    block_only_catalog["blocks"][0]["constituents"] = []
    block_only_catalog["etfs"] = []
    for stock in block_only_catalog["stocks"]:
        stock["theme_ids"] = []
        stock["block_codes"] = ["BK-AI"]
        stock["mapping_confidence"] = 0.4
    block_only_result = resolve_theme_instruments(
        _snapshot(_theme("theme-ai", "人工智能")),
        block_only_catalog,
    ).to_dict()
    assert block_only_result["themes"][0]["instruments"] == []
    assert any(row["reason"] == "low_confidence_mapping" for row in block_only_result["unresolved"])


def test_universe_rejects_tampering_after_hash_binding():
    result = resolve_theme_instruments(
        _snapshot(_theme("theme-ai", "人工智能")),
        _catalog(),
    )
    payload = result.to_dict()
    payload["themes"][0]["display_name"] = "被篡改"

    with pytest.raises(ThemeInstrumentResolverError, match="universe hash"):
        ThemeInstrumentUniverse.from_payload(payload)
