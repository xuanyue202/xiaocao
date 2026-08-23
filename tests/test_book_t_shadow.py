from __future__ import annotations

import copy
import json
from datetime import date as calendar_date, timedelta
from pathlib import Path

import pytest

from xiaocao.kol.publication import canonical_sha256
from xiaocao.research.book_t_shadow import (
    BOOK_T_SHADOW_NAMESPACE,
    BOOK_T_SHADOW_PROTOCOL_ID,
    BookTShadowError,
    bind_book_t_shadow_input,
    evaluate_book_t_shadow,
    run_book_t_shadow,
    write_book_t_shadow_artifacts,
)
from xiaocao.research.book_t_v2_lifecycle import (
    build_daily_mark_event,
    build_exit_event,
    build_initial_lifecycle,
    build_matured_outcome_event,
)
from scripts.book_t_shadow import _load_historical_days, _merge_days, runtime_check


def _hashed(body: dict, field: str) -> dict:
    return {**body, field: canonical_sha256(body)}


def _selection_plan(theme_id: str, code: str, as_of: str) -> dict:
    body = {
        "schema_version": 1,
        "as_of": as_of,
        "plan_status": "ready",
        "daily_reevaluation_complete": True,
        "new_buys_allowed": True,
        "proactive_switches_allowed": True,
        "snapshot_sha256": canonical_sha256({"snapshot": theme_id, "as_of": as_of}),
        "universe_sha256": canonical_sha256({"universe": theme_id, "as_of": as_of}),
        "portfolio_sha256": canonical_sha256({"portfolio": theme_id, "as_of": as_of}),
        "binding_receipt": {
            "status": "validated",
            "snapshot_sha256": canonical_sha256({"snapshot": theme_id, "as_of": as_of}),
            "universe_sha256": canonical_sha256({"universe": theme_id, "as_of": as_of}),
            "portfolio_sha256": canonical_sha256({"portfolio": theme_id, "as_of": as_of}),
        },
        "selected_themes": [
            {
                "theme_id": theme_id,
                "target_ratio": 0.1,
                "expression_type": "broad_etf" if code.startswith("15") else "core_stock",
                "instruments": [{"code": code, "theme_id": theme_id}],
            }
        ],
        "actions": [{"action": "open", "theme_id": theme_id, "code": code}],
        "paired_switches": [],
        "unselected_candidates": [
            {
                "theme_id": "unselected-theme",
                "first_failure_layer": "theme_eligibility",
                "reason": f"wait-{as_of}",
            }
        ],
        "budget": {"target_ratio_total": 0.1},
        "concentration": {"risk_unit": "theme_slot", "instrument_risk_merged": True},
    }
    return _hashed(body, "selection_plan_sha256")


def _market_input(date: str, theme_id: str, code: str, trading_day_index: int) -> dict:
    body = {
        "market_date": date,
        "is_trading_day": True,
        "trading_day_index": trading_day_index,
        "quotes": {code: {"open": 10.0, "last": 10.1}},
        "theme_beta": {theme_id: 1.0},
        "liquidity": {code: {"status": "verified", "source": "p-xcapi"}},
        "source": "frozen_proprietary_market_input",
    }
    return _hashed(body, "market_input_sha256")


def _fill(
    market_hash: str,
    *,
    date: str,
    theme_id: str,
    code: str,
    instrument_type: str,
    expression_type: str,
    status: str = "filled",
) -> dict:
    row = {
        "as_of": date,
        "market_input_sha256": market_hash,
        "code": code,
        "fill_id": f"fill-{date}-{code}",
        "theme_id": theme_id,
        "instrument_type": instrument_type,
        "expression_type": expression_type,
        "status": status,
        "side": "BUY",
        "fill_price": 10.0 if status == "filled" else None,
        "shares": 100 if status == "filled" else 0,
        "notional": 1000.0 if status == "filled" else 0.0,
        "fee": 1.0 if status == "filled" else 0.0,
        "liquidity_status": "verified" if status == "filled" else "unavailable",
        "market_contract_status": "verified" if status == "filled" else "unknown",
        "tradability_status": "eligible" if status == "filled" else "blocked",
        "lot_size": 100,
        "settlement_cycle": "T+1",
        "market_data_source": "p-xcapi",
        "market_price_field": "trade",
        "skip_reason": None if status == "filled" else "LIMIT_NOT_REACHED",
    }
    if instrument_type == "etf" and status == "filled":
        row.update(
            {
                "instrument_contract": {
                    "code": code,
                    "instrument_type": "etf",
                    "lot_size": 100,
                    "settlement_cycle": "T+1",
                    "buy_fee_rate": 0.001,
                    "sell_fee_rate": 0.001,
                    "market_data_contract": {
                        "realtime": "verified",
                        "minute": "verified",
                        "daily": "verified",
                        "fill": "verified",
                    },
                    "provenance": {
                        "source": "xiaocao_api",
                        "trade_date": date,
                    },
                },
                "market_data_facts": {
                    "code": code,
                    "as_of": date,
                    "source": "xiaocao_api",
                    "realtime": {
                        "code": code,
                        "trade": 10.0,
                        "tradeDate": date.replace("-", ""),
                        "status": "active",
                    },
                    "minute_rows": [
                        {
                            "code": code,
                            "trade": 10.0,
                            "tradeDate": date.replace("-", ""),
                        }
                    ],
                    "daily_rows": [
                        {
                            "code": code,
                            "tradeDate": date.replace("-", ""),
                            "open": 9.9,
                            "high": 10.1,
                            "low": 9.8,
                            "close": 10.0,
                        }
                    ],
                    "liquidity": {"status": "liquid"},
                },
            }
        )
    return row


def _variant(
    *,
    date: str,
    market_hash: str,
    theme_id: str,
    code: str,
    instrument_type: str,
    expression_type: str,
    strat_ret: float,
    base_ret: float,
    source_roles: list[str],
    selection_plan: dict | None = None,
) -> dict:
    selection = selection_plan or {
        "variant": "v1_control",
        "as_of": date,
        "selected_themes": [theme_id],
        "selected_codes": [code],
        "actions": [{"action": "open", "theme_id": theme_id, "code": code}],
        "market_input_sha256": market_hash,
    }
    if selection_plan is None:
        selection = _hashed(selection, "selection_sha256")
    control_receipt = {
        "consumer": "book_t_v1_control",
        "producer": "kronos_screen/scripts/paper_record.py",
        "mode": "trend-only",
        "book": "T",
        "as_of": date,
        "artifact_paths": {
            "positions": "output/live/positions.jsonl",
            "account": "output/live/paper_account_T.json",
            "trades": "output/live/paper_trades.jsonl",
        },
        "artifact_hashes": {
            "positions": canonical_sha256({"artifact": "positions", "date": date}),
            "account": canonical_sha256({"artifact": "account", "date": date}),
            "trades": canonical_sha256({"artifact": "trades", "date": date}),
        },
    }
    control_receipt = _hashed(control_receipt, "receipt_sha256")
    return {
        "selection": selection if selection_plan is None else None,
        "selection_plan": selection_plan,
        "control_receipt": control_receipt,
        "source_roles": source_roles,
        "expected_fill_codes": [code],
        "fills": [
            _fill(
                market_hash,
                date=date,
                theme_id=theme_id,
                code=code,
                instrument_type=instrument_type,
                expression_type=expression_type,
            )
        ],
        "holds": [
            {
                "entry": date,
                "exit": date,
                "as_of": date,
                "market_input_sha256": market_hash,
                "theme_id": theme_id,
                "code": code,
                "fill_reference": f"fill-{date}-{code}",
                "instrument_type": instrument_type,
                "expression_type": expression_type,
                "strat_ret": strat_ret,
                "base_ret": base_ret,
                "regime": "bear" if date.endswith(("2", "4", "6", "8", "0")) else "trend_strong",
                "turnover": 0.2,
            }
        ],
    }


def _day(
    index: int,
    *,
    single_theme: bool = False,
    single_source: bool = False,
    instrument_type: str | None = None,
) -> dict:
    date = (calendar_date(2026, 1, 1) + timedelta(days=index)).isoformat()
    theme_id = "theme-ai" if single_theme or index % 2 == 0 else "theme-chip"
    code = "159001.XSHE" if (instrument_type == "etf" or (instrument_type is None and index % 2 == 0)) else "000001.XSHE"
    instrument = "etf" if code.startswith("159") else "equity"
    expression = "broad_etf" if instrument == "etf" else "core_trend_stock"
    market = _market_input(date, theme_id, code, index)
    roles = ["xiaocao"] if single_source else ["xiaocao", "mache", "other_kol"]
    shadow_plan = _selection_plan(theme_id, code, date)
    return {
        "schema_version": 1,
        "namespace": "book_t_v2_shadow_input",
        "as_of": f"{date}T08:00:00Z",
        "market_input": market,
        "assumptions": {
            "budget_ratio": 0.30,
            "fee_rate": 0.001,
            "fill_model": "opening_window_vwap_capped_by_limit",
            "liquidity_model": "proprietary_current_facts",
            "settlement_model": "instrument_contract",
        },
        "control": _variant(
            date=date,
            market_hash=market["market_input_sha256"],
            theme_id=theme_id,
            code=code,
            instrument_type=instrument,
            expression_type=expression,
            strat_ret=1.0,
            base_ret=0.4,
            source_roles=roles,
        ),
        "shadow": _variant(
            date=date,
            market_hash=market["market_input_sha256"],
            theme_id=theme_id,
            code=code,
            instrument_type=instrument,
            expression_type=expression,
            strat_ret=1.2 + (index % 3) * 0.15,
            base_ret=0.4,
            source_roles=roles,
            selection_plan=shadow_plan,
        ),
    }


def _bound_day(index: int, **kwargs) -> dict:
    return bind_book_t_shadow_input(_day(index, **kwargs))


def _bound_lifecycle_day(index: int) -> dict:
    value = _day(index)
    date = (calendar_date(2026, 1, 1) + timedelta(days=index)).isoformat()
    code = value["shadow"]["fills"][0]["code"]
    semantics = {
        "as_of": date,
        "book": "T",
        "selection": {"as_of": date, "selected_codes": [code], "actions": [{"code": code, "kind": "trade", "side": "BUY"}]},
        "actions": [{"code": code, "kind": "trade", "side": "BUY"}],
        "trade_count": 1,
        "skip_count": 0,
        "position_transition_count": 0,
    }
    receipt = dict(value["control"]["control_receipt"])
    receipt["daily_semantics"] = semantics
    receipt["daily_semantics_sha256"] = canonical_sha256(semantics)
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    value["control"]["control_receipt"] = receipt
    value["control"]["daily_semantics_sha256"] = receipt["daily_semantics_sha256"]
    value["control"]["holds"] = []
    value["shadow"]["holds"] = []
    plan = value["shadow"]["selection_plan"]
    value["evidence_lifecycle"] = build_initial_lifecycle(
        decision_id=f"book-t-v2:{date}:real",
        as_of=date,
        observed_at=f"{date}T08:00:00Z",
        trading_day_index=index,
        run_mode="real",
        snapshot_sha256=plan["snapshot_sha256"],
        universe_sha256=plan["universe_sha256"],
        selection_plan_sha256=plan["selection_plan_sha256"],
        portfolio_sha256=plan["portfolio_sha256"],
        control_receipt_sha256=receipt["receipt_sha256"],
        fills=value["shadow"]["fills"],
        daily_reevaluation_complete=True,
    )
    return bind_book_t_shadow_input(value)


def test_shadow_run_is_hash_bound_and_never_mutates_formal_ledger() -> None:
    frozen = _bound_day(1)

    first = run_book_t_shadow(frozen)
    second = run_book_t_shadow(copy.deepcopy(frozen))

    assert first == second
    assert first["namespace"] == BOOK_T_SHADOW_NAMESPACE
    assert first["input_sha256"] == frozen["input_sha256"]
    assert first["market_input_sha256"] == frozen["market_input"]["market_input_sha256"]
    assert first["comparison"]["same_market_input"] is True
    assert first["engineering"]["formal_ledger_mutations"] == {
        "positions": 0,
        "account": 0,
        "trades": 0,
    }
    assert first["engineering"]["valid_theme_decision"] is True
    assert first["shadow"]["fills"][0]["market_input_sha256"] == first["market_input_sha256"]


def test_matured_events_feed_metrics_only_after_explicit_lifecycle_events() -> None:
    frozen = _bound_lifecycle_day(1)
    run = run_book_t_shadow(frozen)
    before = evaluate_book_t_shadow([run])
    lifecycle = frozen["evidence_lifecycle"]
    date = frozen["as_of"][:10]
    code = frozen["shadow"]["fills"][0]["code"]
    daily_mark = build_daily_mark_event(
        lifecycle,
        observed_at=f"{date}T09:00:00Z",
        marks=[{"as_of": date, "code": code, "price": 10.2}],
    )
    exit_event = build_exit_event(
        lifecycle,
        observed_at="2026-01-03T07:10:00Z",
        exits=[{"as_of": "2026-01-03", "code": code, "exit_price": 10.5}],
    )
    matured = build_matured_outcome_event(
        lifecycle,
        observed_at="2026-01-04T07:10:00Z",
        outcomes=[
            {
                "as_of": "2026-01-04",
                "code": code,
                "strat_ret": 5.0,
                "base_ret": 3.0,
            }
        ],
    )
    after = evaluate_book_t_shadow(
        [run],
        lifecycle_events=[daily_mark, exit_event, matured],
    )

    assert before["sample"]["outcome_pending"] == 1
    assert before["sample"]["valid_theme_decisions"] == 0
    assert after["sample"]["outcome_pending"] == 0
    assert after["sample"]["outcome_matured"] == 1
    assert after["sample"]["valid_theme_decisions"] == 1


def test_shadow_run_fails_closed_on_mixed_market_input() -> None:
    frozen = _bound_day(1)
    frozen["shadow"]["fills"][0]["market_input_sha256"] = "wrong-market"
    unsigned = dict(frozen)
    unsigned.pop("input_sha256", None)
    frozen["input_sha256"] = canonical_sha256(unsigned)

    with pytest.raises(BookTShadowError, match="market_input_sha256"):
        run_book_t_shadow(frozen)


def test_research_evaluation_replays_the_frozen_input() -> None:
    run = run_book_t_shadow(_bound_day(1))
    run.pop("frozen_input")

    with pytest.raises(BookTShadowError, match="frozen_input"):
        evaluate_book_t_shadow([run])


def test_research_floors_cannot_be_lowered() -> None:
    with pytest.raises(BookTShadowError, match="protocol minimum"):
        evaluate_book_t_shadow([], min_burn_in_days=0)


def test_blocked_shadow_fill_is_not_a_valid_decision_or_return_path() -> None:
    def blocked_day(index: int) -> dict:
        day = _day(index)
        day["shadow"]["fills"][0]["status"] = "blocked"
        day["shadow"]["fills"][0]["skip_reason"] = "MARKET_CONTRACT_UNVERIFIED"
        return bind_book_t_shadow_input(day)

    result = evaluate_book_t_shadow([run_book_t_shadow(blocked_day(i)) for i in range(60)])

    assert result["status"] == "REJECTED"
    assert result["sample"]["valid_theme_decisions"] == 0
    assert "strategy_sample_floor" in result["pending_reasons"]


def test_input_component_dates_are_bound_to_the_root_day() -> None:
    day = _day(1)
    day["shadow"]["fills"][0]["as_of"] = "2026-02-01"

    with pytest.raises(BookTShadowError, match="does not match frozen day"):
        bind_book_t_shadow_input(day)


def test_shadow_research_stays_pending_until_burn_in_and_strategy_floor() -> None:
    runs = [run_book_t_shadow(_bound_day(i)) for i in range(3)]

    result = evaluate_book_t_shadow(runs)

    assert result["status"] == "pending_observation"
    assert "engineering_burn_in" in result["pending_reasons"]
    assert "strategy_sample_floor" in result["pending_reasons"]
    assert result["sample"]["trading_days"] == 3
    assert result["sample"]["valid_theme_decisions"] == 3
    assert result["shadow_verdict"]["verdict"] in {"PASS", "REJECTED"}


def test_shadow_research_pass_requires_diverse_evidence_and_not_one_winner() -> None:
    runs = [run_book_t_shadow(_bound_day(i)) for i in range(60)]

    result = evaluate_book_t_shadow(runs, min_burn_in_days=20, min_strategy_days=60)

    assert result["status"] == "PASS", result["rejected_reasons"]
    assert result["sample"]["valid_theme_decisions"] == 60
    assert result["coverage"]["unique_themes"] == 2
    assert result["coverage"]["source_roles"] == 3
    assert result["coverage"]["instrument_types"] == 2
    assert result["coverage"]["etf_contract_exclusion_rate"] == 0.0
    assert result["coverage"]["winner_alpha_share"] < 0.5
    assert result["metrics"]["shadow"]["left_tail"]["min"] > 0

    single_theme = evaluate_book_t_shadow(
        [run_book_t_shadow(_bound_day(i, single_theme=True)) for i in range(60)],
        min_burn_in_days=20,
        min_strategy_days=60,
    )
    assert single_theme["status"] == "REJECTED"
    assert "single_theme" in single_theme["rejected_reasons"]


def test_repeated_noop_plan_does_not_fill_the_decision_floor() -> None:
    def noop_day(index: int) -> dict:
        day = _day(index, single_theme=True, instrument_type="equity")
        plan = day["shadow"]["selection_plan"]
        plan["unselected_candidates"][0]["reason"] = "wait"
        plan.pop("selection_plan_sha256", None)
        if isinstance(plan.get("binding_receipt"), dict):
            plan["binding_receipt"].pop("selection_plan_sha256", None)
        return bind_book_t_shadow_input(day)

    result = evaluate_book_t_shadow(
        [run_book_t_shadow(noop_day(index)) for index in range(60)]
    )

    assert result["sample"]["valid_theme_decisions"] == 1
    assert result["status"] == "REJECTED"
    assert "strategy_sample_floor" in result["pending_reasons"]


def test_shadow_artifacts_have_research_namespace_and_manifest(tmp_path: Path) -> None:
    runs = [run_book_t_shadow(_bound_day(i)) for i in range(3)]
    evaluation = evaluate_book_t_shadow(runs)

    paths = write_book_t_shadow_artifacts(
        runs,
        evaluation,
        output_dir=tmp_path,
        run_id="20260103-book-t-v2-shadow",
        frozen_inputs=[_bound_day(i) for i in range(3)],
        git_state={"commit": "test", "dirty": False},
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["namespace"] == BOOK_T_SHADOW_NAMESPACE
    assert manifest["protocol_id"] == BOOK_T_SHADOW_PROTOCOL_ID
    assert manifest["verdict"]["status"] == "pending_observation"
    assert manifest["formal_ledger_mutations"] == {"positions": 0, "account": 0, "trades": 0}
    assert paths["report"].read_text(encoding="utf-8").startswith("# Book T v2 shadow")
    assert not (tmp_path / "positions.jsonl").exists()
    assert not (tmp_path / "paper_account_T.json").exists()


def test_shadow_consumer_accumulates_prior_isolated_inputs(tmp_path: Path) -> None:
    first = _bound_day(0)
    first_run = run_book_t_shadow(first)
    first_evaluation = evaluate_book_t_shadow([first_run])
    write_book_t_shadow_artifacts(
        [first_run],
        first_evaluation,
        output_dir=tmp_path,
        run_id="20260101-book-t-v2-shadow",
        frozen_inputs=[first],
        git_state={"commit": "test", "dirty": False},
    )

    merged = _merge_days(_load_historical_days(tmp_path) + [_bound_day(1)])

    assert len(merged) == 2
    assert [run_book_t_shadow(day)["market_date"] for day in merged] == [
        "2026-01-01",
        "2026-01-02",
    ]


def test_runtime_check_preserves_v1_control_as_tomorrows_consumer(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "kronos_screen" / "scripts").mkdir(parents=True)
    (tmp_path / "output" / "live").mkdir(parents=True)
    (tmp_path / "scripts" / "auto_daily.sh").write_text(
        "paper_record.py --trend-only\nbook_t_v2_daily.py --prepare\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "book_t_v2_daily.py").write_text(
        "# production producer\n", encoding="utf-8"
    )
    (tmp_path / "reference" / "experience").mkdir(parents=True)
    (tmp_path / "reference" / "experience" / "book_t_v2_theme_registry.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "live_monitor.py").write_text(
        'parser.add_argument("--book", choices=["B", "T"])\n', encoding="utf-8"
    )
    (tmp_path / "kronos_screen" / "scripts" / "paper_record.py").write_text(
        "--trend-only\n", encoding="utf-8"
    )
    (tmp_path / "kronos_screen" / "scripts" / "settle_book_t.py").write_text("", encoding="utf-8")
    (tmp_path / "output" / "live" / "positions.jsonl").write_text(
        '{"book":"T","status":"open","code":"000001.XSHE"}\n', encoding="utf-8"
    )
    (tmp_path / "output" / "live" / "paper_account_T.json").write_text("{}\n", encoding="utf-8")

    result = runtime_check(root=tmp_path, target_date="2026-08-18")

    assert result["status"] == "pending_observation", result
    assert result["evidence_pending"] is True
    assert result["consumer"] == "book_t_v1_control"
    assert result["v2_shadow"] == "separate_research_namespace_only"
    assert result["next_command"] == "bash scripts/auto_daily.sh morning-execute"
