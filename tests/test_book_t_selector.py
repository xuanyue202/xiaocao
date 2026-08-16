from __future__ import annotations

import copy

import pytest

from xiaocao.kol.publication import canonical_sha256
from xiaocao.strategy.book_t_selector import (
    BookTSelectionPlan,
    select_book_t,
)
from xiaocao.strategy.theme_instrument_resolver import ThemeInstrumentUniverse
from xiaocao.strategy.trend_snapshot import TrendJudgmentSnapshot


AS_OF = "2026-08-16T08:00:00Z"
AS_OF_DATE = AS_OF[:10]


def _snapshot(*theme_specs: dict) -> TrendJudgmentSnapshot:
    body = {
        "schema_version": 1,
        "as_of": AS_OF,
        "generated_at": "2026-08-16T08:01:00Z",
        "agent_judgment_version": "selector-test-v1",
        "input_summary_sha256": "input-summary",
        "themes": [
            {
                "theme_id": spec["theme_id"],
                "display_name": spec.get("display_name", spec["theme_id"]),
                "direction": spec.get("direction", "bullish"),
                "confidence": spec.get("confidence", 0.8),
                "eligibility": spec.get("eligibility", "eligible"),
                "eligibility_reason": spec.get("eligibility_reason", "market_supported"),
                "review_not_after": "2026-08-17T08:00:00Z",
                "source_evidence": spec.get("source_evidence", [{"source_key": "xiaocao"}]),
                "market_validation": spec.get(
                    "market_validation",
                    {"status": "support", "trend_strength": spec.get("theme_score", 0.8)},
                ),
            }
            for spec in theme_specs
        ],
        "binding_receipt": {
            "schema_version": 1,
            "status": "validated",
            "input_summary_sha256": "input-summary",
            "validated_at": "2026-08-16T08:01:00Z",
            "source_count": 1,
        },
    }
    snapshot_sha = canonical_sha256(body)
    return TrendJudgmentSnapshot.from_payload(
        {
            **body,
            "snapshot_sha256": snapshot_sha,
            "binding_receipt": {**body["binding_receipt"], "snapshot_sha256": snapshot_sha},
        }
    )


def _instrument(
    theme_id: str,
    code: str,
    *,
    instrument_type: str = "equity",
    expression_role: str = "core_trend_stock",
    breadth_score: float | None = None,
    leader_clarity: float | None = None,
    relative_strength: float = 0.85,
    turnover_20d: float = 100_000_000,
    trend_quality: str = "strong",
    instrument_status: str = "eligible",
    buy_fee_rate: float = 0.0001,
    sell_fee_rate: float = 0.0001,
    risk_contribution: float | None = None,
    catalog_trade_date: str = AS_OF_DATE,
) -> dict:
    market_contract = {"status": "verified"}
    row = {
        "code": code,
        "name": code,
        "instrument_type": instrument_type,
        "theme_id": theme_id,
        "mapping_status": "resolved",
        "mapping_evidence": [{"edge_type": "theme_to_instrument", "source": "fixture"}],
        "provenance": [{"edge_type": "theme_to_instrument", "source": "fixture"}],
        "lot_size": 100,
        "settlement_cycle": "T+1",
        "market_data_contract": market_contract,
        "liquidity": {"status": "liquid", "turnover_20d": turnover_20d},
        "trend": {"quality": trend_quality},
        "relative_strength": relative_strength,
        "expression_role": expression_role,
        "instrument_status": instrument_status,
        "tradability_status": instrument_status,
        "non_tradable_reasons": [] if instrument_status == "eligible" else ["contract_unknown"],
        "ineligible_reasons": [] if instrument_status == "eligible" else ["contract_unknown"],
    }
    if breadth_score is not None:
        row["breadth_score"] = breadth_score
    if leader_clarity is not None:
        row["leader_clarity"] = leader_clarity
    if risk_contribution is not None:
        row["risk_contribution"] = risk_contribution
    if instrument_type == "etf":
        row.update(
            {
                "buy_fee_rate": buy_fee_rate,
                "sell_fee_rate": sell_fee_rate,
                "catalog_trade_date": catalog_trade_date,
                "market_status": "active",
                "liquidity_status": "liquid",
                "market_data_contract": {
                    "status": "verified",
                    "source": "p-xcapi",
                    "realtime": {"status": "verified"},
                    "minute": {"status": "verified", "price_field": "trade"},
                    "daily": {"status": "verified"},
                    "fill": {"status": "verified"},
                },
            }
        )
    return row


def _universe(
    snapshot: TrendJudgmentSnapshot,
    theme_specs: list[dict],
    instruments: list[dict],
) -> ThemeInstrumentUniverse:
    themes = []
    for spec in theme_specs:
        theme_instruments = [
            copy.deepcopy(row)
            for row in instruments
            if row["theme_id"] == spec["theme_id"]
        ]
        themes.append(
            {
                "theme_id": spec["theme_id"],
                "display_name": spec.get("display_name", spec["theme_id"]),
                "snapshot_display_name": spec.get("display_name", spec["theme_id"]),
                "snapshot_eligibility": spec.get("eligibility", "eligible"),
                "resolution_status": spec.get("resolution_status", "resolved"),
                "matched_by": "theme_id",
                "mapping_evidence": [{"edge_type": "theme_identity", "source": "fixture"}],
                "instruments": theme_instruments,
            }
        )
    body = {
        "schema_version": 1,
        "resolver_version": "selector-test-resolver-v1",
        "snapshot_sha256": snapshot.snapshot_sha256,
        "catalog_sha256": "catalog-sha",
        "catalog_version": "catalog-v1",
        "registry_version": "registry-v1",
        "theme_registry": {"version": "registry-v1", "themes": []},
        "themes": sorted(themes, key=lambda row: row["theme_id"]),
        "instruments": sorted(
            (copy.deepcopy(row) for row in instruments),
            key=lambda row: (row["theme_id"], row["code"], row["instrument_type"]),
        ),
        "unresolved": [],
        "binding_receipt": {
            "status": "validated",
            "snapshot_sha256": snapshot.snapshot_sha256,
            "catalog_sha256": "catalog-sha",
            "catalog_version": "catalog-v1",
            "resolver_version": "selector-test-resolver-v1",
        },
    }
    universe_sha = canonical_sha256(body)
    return ThemeInstrumentUniverse.from_payload(
        {
            **body,
            "universe_sha256": universe_sha,
            "binding_receipt": {**body["binding_receipt"], "universe_sha256": universe_sha},
        }
    )


def _portfolio(*, positions: list[dict] | None = None, history: object = None) -> dict:
    value = {
        "account_equity": 100_000,
        "positions": positions or [],
    }
    if history is not None:
        value["evaluation_history"] = history
    return value


def _selected(plan: BookTSelectionPlan) -> list[dict]:
    return plan.to_dict()["selected_themes"]


def test_selects_at_most_three_theme_slots_and_caps_budget_at_thirty_percent():
    specs = [
        {"theme_id": "theme-a", "theme_score": 0.95},
        {"theme_id": "theme-b", "theme_score": 0.90},
        {"theme_id": "theme-c", "theme_score": 0.85},
        {"theme_id": "theme-d", "theme_score": 0.80},
    ]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [
            _instrument(spec["theme_id"], f"{index:06d}.XSHE", relative_strength=spec["theme_score"])
            for index, spec in enumerate(specs, 1)
        ],
    )

    plan = select_book_t(_portfolio(), snapshot, universe)
    payload = plan.to_dict()

    assert payload["plan_status"] == "ready"
    assert len(_selected(plan)) == 3
    assert payload["budget"]["max_theme_slots"] == 3
    assert payload["budget"]["target_ratio_total"] == pytest.approx(0.30)
    assert sum(row["target_ratio"] for row in _selected(plan)) == pytest.approx(0.30)
    assert all(row["target_ratio"] == pytest.approx(0.10) for row in _selected(plan))
    assert payload["budget"]["target_notional_total"] == pytest.approx(30_000)
    assert {row["theme_id"] for row in payload["unselected_candidates"]} == {"theme-d"}


def test_expression_choice_can_combine_broad_etf_and_clear_core_stock():
    specs = [{"theme_id": "theme-ai", "theme_score": 0.9}]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [
            _instrument(
                "theme-ai",
                "159001.XSHE",
                instrument_type="etf",
                expression_role="broad_etf",
                breadth_score=0.95,
                relative_strength=0.88,
            ),
            _instrument(
                "theme-ai",
                "000001.XSHE",
                expression_role="core_trend_stock",
                leader_clarity=0.95,
                relative_strength=0.94,
            ),
        ],
    )

    selected = _selected(select_book_t(_portfolio(), snapshot, universe))[0]

    assert selected["expression"]["expression_type"] == "etf_plus_stock"
    assert {row["instrument_type"] for row in selected["expression"]["instruments"]} == {
        "etf",
        "equity",
    }
    assert sum(row["weight"] for row in selected["expression"]["instruments"]) == pytest.approx(1.0)
    assert selected["expression"]["instruments"][0]["weight"] == pytest.approx(0.5)
    assert selected["risk"]["risk_unit"] == "theme_slot"
    assert selected["expression"]["correlation_policy"] == (
        "merge_all_instruments_into_one_theme_risk_slot"
    )


def test_expression_combo_is_rejected_when_combined_risk_exceeds_one_theme_slot():
    specs = [{"theme_id": "theme-ai", "theme_score": 0.9}]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [
            _instrument(
                "theme-ai",
                "159001.XSHE",
                instrument_type="etf",
                expression_role="broad_etf",
                breadth_score=0.95,
                risk_contribution=1.0,
            ),
            _instrument(
                "theme-ai",
                "000001.XSHE",
                leader_clarity=0.95,
                relative_strength=0.94,
                risk_contribution=1.4,
            ),
        ],
    )

    selected = _selected(select_book_t(_portfolio(), snapshot, universe))[0]

    assert selected["expression"]["expression_type"] == "etf"
    assert selected["expression"]["combined_risk_ratio"] == pytest.approx(1.0)


def test_stale_etf_catalog_is_the_first_contract_failure():
    specs = [{"theme_id": "theme-ai"}]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [
            _instrument(
                "theme-ai",
                "159001.XSHE",
                instrument_type="etf",
                expression_role="broad_etf",
                catalog_trade_date="2026-08-10",
            ),
            _instrument("theme-ai", "000001.XSHE"),
        ],
    )

    payload = select_book_t(_portfolio(), snapshot, universe).to_dict()

    stale = next(row for row in payload["unselected_candidates"] if row.get("code") == "159001.XSHE")
    assert stale["first_failure_layer"] == "instrument_contract"
    assert stale["reason"] == "etf_catalog_stale"


def test_hierarchy_blocks_theme_before_expression_and_skips_bad_etf_contract():
    specs = [
        {"theme_id": "theme-wait", "eligibility": "wait", "eligibility_reason": "timing_wait"},
        {"theme_id": "theme-ai"},
    ]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [
            _instrument("theme-wait", "000001.XSHE"),
            _instrument(
                "theme-ai",
                "159999.XSHE",
                instrument_type="etf",
                expression_role="broad_etf",
                instrument_status="ineligible",
            ),
            _instrument("theme-ai", "000002.XSHE", relative_strength=0.82),
        ],
    )

    payload = select_book_t(_portfolio(), snapshot, universe).to_dict()

    selected = payload["selected_themes"]
    assert [row["theme_id"] for row in selected] == ["theme-ai"]
    wait_rejection = next(
        row for row in payload["unselected_candidates"] if row["theme_id"] == "theme-wait"
    )
    assert wait_rejection["first_failure_layer"] == "theme_eligibility"
    assert wait_rejection["reason"] == "theme_wait"
    etf_rejection = next(
        row
        for row in payload["unselected_candidates"]
        if row.get("code") == "159999.XSHE"
    )
    assert etf_rejection["first_failure_layer"] == "instrument_contract"
    assert etf_rejection["reason"] == "instrument_ineligible"


def test_full_portfolio_is_rejudged_and_requires_two_valid_evaluations_to_switch():
    specs = [
        {"theme_id": "theme-a", "theme_score": 0.55},
        {"theme_id": "theme-b", "theme_score": 0.60},
        {"theme_id": "theme-c", "theme_score": 0.65},
        {"theme_id": "theme-d", "theme_score": 0.95},
    ]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [
            _instrument(
                spec["theme_id"],
                f"{index:06d}.XSHE",
                relative_strength=spec["theme_score"],
            )
            for index, spec in enumerate(specs, 1)
        ],
    )
    positions = [
        {
            "book": "T",
            "theme_id": theme_id,
            "code": f"{index:06d}.XSHE",
            "status": "open",
            "selection_score": score,
            "entry_date": "2026-08-01",
        }
        for index, (theme_id, score) in enumerate(
            [("theme-a", 0.55), ("theme-b", 0.60), ("theme-c", 0.65)], 1
        )
    ]

    first = select_book_t(_portfolio(positions=positions), snapshot, universe).to_dict()
    assert first["daily_reevaluation_complete"] is True
    assert len(first["selected_themes"]) == 3
    assert first["paired_switches"] == []
    assert any(
        row.get("theme_id") == "theme-d"
        and row["first_failure_layer"] == "challenger_hysteresis"
        for row in first["unselected_candidates"]
    )

    history = {
        "theme-d": [
            {
                "as_of": "2026-08-15T08:00:00Z",
                "valid": True,
                "score": 0.95,
                "incumbent_theme_id": "theme-a",
                "incumbent_score": 0.55,
            }
        ]
    }
    switched = select_book_t(
        _portfolio(positions=positions, history=history), snapshot, universe
    ).to_dict()

    assert switched["daily_reevaluation_complete"] is True
    assert len(switched["paired_switches"]) == 1
    assert switched["paired_switches"][0]["from_theme_id"] == "theme-a"
    assert switched["paired_switches"][0]["to_theme_id"] == "theme-d"
    assert any(action["action"] == "paired_switch" for action in switched["actions"])
    assert {row["theme_id"] for row in switched["selected_themes"]} == {
        "theme-b",
        "theme-c",
        "theme-d",
    }


def test_existing_portfolio_overflow_is_not_carried_past_three_theme_slots():
    specs = [
        {"theme_id": "theme-a", "theme_score": 0.90},
        {"theme_id": "theme-b", "theme_score": 0.80},
        {"theme_id": "theme-c", "theme_score": 0.70},
        {"theme_id": "theme-d", "theme_score": 0.60},
    ]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [
            _instrument(spec["theme_id"], f"{index:06d}.XSHE", relative_strength=spec["theme_score"])
            for index, spec in enumerate(specs, 1)
        ],
    )
    positions = [
        {
            "book": "T",
            "theme_id": spec["theme_id"],
            "code": f"{index:06d}.XSHE",
            "selection_score": spec["theme_score"],
        }
        for index, spec in enumerate(specs, 1)
    ]

    payload = select_book_t(_portfolio(positions=positions), snapshot, universe).to_dict()

    assert len(payload["selected_themes"]) == 3
    assert any(
        row["theme_id"] == "theme-d" and row["reason"] == "theme_slot_overflow"
        for row in payload["unselected_candidates"]
    )
    assert any(
        row["theme_id"] == "theme-d" and row["reason"] == "theme_slot_overflow"
        for row in payload["actions"]
    )


def test_missing_inputs_pause_new_buys_and_switches_without_v1_fallback():
    plan = select_book_t(_portfolio(), None, None).to_dict()

    assert plan["plan_status"] == "blocked"
    assert plan["new_buys_allowed"] is False
    assert plan["proactive_switches_allowed"] is False
    assert plan["existing_risk_management_allowed"] is True
    assert plan["v1_static_fallback"] is False
    assert plan["daily_reevaluation_complete"] is False
    assert {row["first_failure_layer"] for row in plan["blocking_reasons"]} == {
        "evidence_binding"
    }


def test_missing_account_equity_keeps_existing_risk_boundary_and_emits_no_new_buy():
    specs = [{"theme_id": "theme-ai"}]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [_instrument("theme-ai", "000001.XSHE")],
    )

    plan = select_book_t({}, snapshot, universe).to_dict()

    assert plan["plan_status"] == "degraded"
    assert plan["new_buys_allowed"] is False
    assert plan["proactive_switches_allowed"] is False
    assert plan["selected_themes"] == []
    assert plan["unselected_candidates"][0]["reason"] == "account_equity_missing"


def test_snapshot_universe_binding_mismatch_blocks_selection():
    specs = [{"theme_id": "theme-ai"}]
    snapshot = _snapshot(*specs)
    other_snapshot = _snapshot({"theme_id": "theme-other"})
    universe = _universe(
        other_snapshot,
        [{"theme_id": "theme-other"}],
        [_instrument("theme-other", "000002.XSHE")],
    )

    plan = select_book_t(_portfolio(), snapshot, universe).to_dict()

    assert plan["plan_status"] == "blocked"
    assert plan["new_buys_allowed"] is False
    assert any(
        row["reason"] == "snapshot_universe_hash_mismatch"
        for row in plan["blocking_reasons"]
    )


def test_invalidated_incumbent_emits_risk_exit_but_respects_t1():
    specs = [
        {
            "theme_id": "theme-ai",
            "eligibility": "invalidated",
            "eligibility_reason": "market_validation_invalidated",
        }
    ]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [_instrument("theme-ai", "000001.XSHE")],
    )
    positions = [
        {"book": "T", "theme_id": "theme-ai", "code": "000001.XSHE", "entry_date": "2026-08-01"},
        {"book": "T", "theme_id": "theme-ai", "code": "000002.XSHE", "entry_date": AS_OF_DATE},
    ]

    actions = select_book_t(_portfolio(positions=positions), snapshot, universe).to_dict()["actions"]

    assert {row["action"] for row in actions} == {"risk_exit", "wait"}
    assert next(row for row in actions if row["action"] == "wait")["reason"] == "t1_blocked"


def test_missing_book_label_blocks_new_selection_instead_of_assuming_book_t():
    specs = [{"theme_id": "theme-ai"}]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [_instrument("theme-ai", "000001.XSHE")],
    )
    portfolio = _portfolio(
        positions=[{"theme_id": "theme-ai", "code": "000001.XSHE", "status": "open"}]
    )

    payload = select_book_t(portfolio, snapshot, universe).to_dict()

    assert payload["new_buys_allowed"] is False
    assert any(
        row["reason"] == "position_book_missing_or_invalid"
        for row in payload["blocking_reasons"]
    )


def test_selection_plan_is_hash_bound():
    specs = [{"theme_id": "theme-ai"}]
    snapshot = _snapshot(*specs)
    universe = _universe(
        snapshot,
        specs,
        [_instrument("theme-ai", "000001.XSHE")],
    )
    plan = select_book_t(_portfolio(), snapshot, universe)
    payload = plan.to_dict()
    payload["selected_themes"][0]["target_ratio"] = 0.01

    with pytest.raises(ValueError, match="selection plan hash"):
        BookTSelectionPlan.from_payload(payload)
