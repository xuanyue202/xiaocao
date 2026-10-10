from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from xiaocao.kol.publication import canonical_sha256
from xiaocao.strategy.book_t_budget import budget_contract, constrain_shadow_fills, validate_control_budget
from xiaocao.research.book_t_budget_repair import create_budget_repair, resolve_budget_input, partition_repair_events, REPAIR_ROOT
from xiaocao.research.book_t_shadow import BookTShadowError, bind_book_t_shadow_input, evaluate_book_t_shadow, run_book_t_shadow
from xiaocao.research.book_t_v2_producer import prepare_book_t_v2_shadow_day
from xiaocao.research.book_t_v2_lifecycle import build_initial_lifecycle, build_daily_mark_event, append_events
from scripts.book_t_v2_soak import _load_inputs, evaluate_daily_stability_soak, evaluate_engineering_burn_in
from scripts.book_t_shadow import _load_event_frozen_days, _merge_days
from tests.test_book_t_v2_producer import _receipt
from xiaocao.strategy.book_t_selector import _finalize_plan
from tests.test_book_t_selector import _snapshot, _universe, _instrument, select_book_t


def _paired_case():
    portfolio = {"book": "T", "account": {"initial_capital": 30000, "cash": 166.66},
                 "account_equity": 27473.17, "positions": [
                     {"code": "601728.XSHG", "shares": 1800, "gross_notional": 9756.70},
                     {"code": "000725.XSHE", "shares": 1200, "gross_notional": 6785.19},
                     {"code": "600050.XSHG", "shares": 2600, "gross_notional": 10764.62}]}
    buy = {"kind": "trade", "side": "BUY", "code": "600050.XSHG", "shares": 2600,
           "notional": 10764.62, "fee": 1.08, "event_sha256": "buy-exact"}
    sell = {"kind": "trade", "side": "SELL", "code": "003816.XSHE", "shares": 2500,
            "notional": 10520.43, "fee": 1.05}
    receipt = {"daily_semantics": {"actions": [buy, sell,
        {"kind": "position_transition", "status": "open", "code": buy["code"], "shares": 2600, "notional": 10764.62},
        {"kind": "position_transition", "status": "closed", "code": sell["code"], "shares": 2500, "notional": 9667.49}]}}
    for index, action in enumerate(receipt["daily_semantics"]["actions"]):
        action.setdefault("event_sha256", f"event-{index}")
    fills = [{**buy, "status": "filled", "fill_id": "v1-control-buy-exact"}]
    return portfolio, receipt, fills


def test_real_t_capital_and_paired_switch_are_not_sliced_twice():
    portfolio, receipt, fills = _paired_case()
    budget = budget_contract(portfolio)
    assert budget["initial_capital"] == 30000
    assert budget["target_budget"] == 27473.17
    assert budget["exposure_cap"] == 30000
    assert fills[0]["notional"] > portfolio["account_equity"] * .3
    validate_control_budget(portfolio, receipt, fills)
    assert fills[0]["notional"] == 10764.62


@pytest.mark.parametrize("fault", ["missing_transition", "cash", "exposure", "slots", "fill_amount", "unproved_sell"])
def test_control_budget_rejects_unproved_cash_cost_slot_and_receipt(fault):
    portfolio, receipt, fills = _paired_case()
    if fault == "missing_transition":
        receipt["daily_semantics"]["actions"].pop()
    elif fault == "cash":
        portfolio["account"]["cash"] = -1
    elif fault == "exposure":
        portfolio["account"]["initial_capital"] = 20000
    elif fault == "slots":
        portfolio["positions"].append({"code": "extra", "shares": 100, "gross_notional": 1})
        portfolio["account_equity"] += 1
    elif fault == "fill_amount":
        fills[0]["notional"] += 1
    else:
        receipt["daily_semantics"]["actions"][1]["notional"] += 10000
    with pytest.raises(ValueError):
        validate_control_budget(portfolio, receipt, fills)


def test_selector_preserves_original_cap_when_t_equity_grows():
    spec = {"theme_id": "theme-a", "theme_score": .9}
    snapshot = _snapshot(spec)
    universe = _universe(snapshot, [spec], [_instrument("theme-a", "000001.XSHE")])
    portfolio = {"account_equity": 40000, "account": {"initial_capital": 30000, "cash": 40000},
                 "max_total_exposure_ratio": .8, "positions": []}
    plan = select_book_t(portfolio, snapshot, universe).to_dict()
    assert plan["budget"]["budget_notional"] == 24000
    assert plan["selected_themes"][0]["target_notional"] == 24000


@pytest.mark.parametrize("fault", ["target", "cash_fee", "held", "cap", "slots"])
def test_shadow_readback_is_blocked_instead_of_resized(fault):
    portfolio = {"account_equity": 30000, "account": {"initial_capital": 30000, "cash": 30000}, "positions": []}
    plan = {"selected_themes": [{"theme_id": "a", "target_notional": 30000,
                                "expression": {"instruments": [{"code": "new"}]}}]}
    row = {"code": "new", "theme_id": "a", "status": "filled", "notional": 10000, "fee": 1, "shares": 1000}
    if fault == "target":
        plan["selected_themes"][0]["target_notional"] = 9000
    elif fault == "cash_fee":
        portfolio["account"]["cash"] = portfolio["account_equity"] = 10000
    elif fault == "held":
        portfolio["positions"] = [{"code": "new", "gross_notional": 10000}]
        portfolio["account"]["cash"] = 20000
    elif fault == "cap":
        portfolio["max_total_exposure_ratio"] = .3
    else:
        portfolio["positions"] = [{"code": f"old{i}", "gross_notional": 100} for i in range(3)]
        portfolio["account"]["cash"] = 29700
    before = copy.deepcopy(row)
    result = constrain_shadow_fills(plan, portfolio, [row])
    assert row == before
    assert result[0]["status"] == "blocked"
    assert result[0]["unused_control_readback"] == before
    assert "notional" not in result[0]


def _legacy(root: Path):
    day = "2026-08-21"
    _receipt(root, day)
    capsule = {"publications": [], "agent_draft": {"themes": []}, "market_validation": {},
        "catalog": {"version": "test", "theme_registry": {"version": "test", "themes": [], "changes": []},
                    "stocks": [], "etfs": [], "blocks": []},
        "portfolio": {"book": "T", "account_equity": 30000, "account": {"initial_capital": 30000, "cash": 30000}, "positions": []},
        "market_input": {"market_date": day, "is_trading_day": True, "trading_day_index": 42}}
    result = prepare_book_t_v2_shadow_day(root, day, run_mode="rehearsal", capsule=capsule)
    value = json.loads(result["input"].read_text())
    value["assumptions"].pop("budget_contract")
    value["assumptions"]["budget_ratio"] = .3
    plan = value["shadow"]["selection_plan"]
    plan["budget"].update(budget_ratio=.3, budget_notional=9000)
    plan = _finalize_plan(plan).to_dict()
    value["shadow"]["selection_plan"] = plan
    value["bindings"]["selection_plan"] = plan
    value["evidence_lifecycle"] = build_initial_lifecycle(
        decision_id=f"book-t-v2:{day}:{plan['selection_plan_sha256'][:16]}", as_of=day, observed_at=value["as_of"],
        trading_day_index=42, run_mode="real", snapshot_sha256=plan["snapshot_sha256"], universe_sha256=plan["universe_sha256"],
        selection_plan_sha256=plan["selection_plan_sha256"], portfolio_sha256=plan["portfolio_sha256"],
        control_receipt_sha256=value["control"]["control_receipt"]["receipt_sha256"], fills=[], daily_reevaluation_complete=True)
    value = bind_book_t_shadow_input(value)
    result["input"].write_text(json.dumps(value))
    event = build_daily_mark_event(value["evidence_lifecycle"],
                                   observed_at=f"{day}T15:00:00+08:00", marks=[])
    event_path = root / "output/research/book_t_v2_shadow/evidence_events.jsonl"
    append_events(event_path, [event])
    return result["input"], value, event_path, event


def test_append_only_idempotent_repair_and_public_history_consumers(tmp_path):
    path, original, events_path, event = _legacy(tmp_path)
    paths = [path, events_path, tmp_path / "output/live/paper_account_T.json", tmp_path / "output/live/positions.jsonl",
             tmp_path / "output/live/paper_trades.jsonl", tmp_path / "output/live/book_t_v1_control_receipt_2026-08-21.json"]
    before = {p: p.read_bytes() for p in paths}
    corrected = create_budget_repair(tmp_path, path)
    directory = tmp_path / REPAIR_ROOT / original["input_sha256"]
    manifests = {p: p.read_bytes() for p in directory.iterdir()}
    assert create_budget_repair(tmp_path, path) == corrected
    assert all(p.read_bytes() == data for p, data in before.items())
    assert all(p.read_bytes() == data for p, data in manifests.items())
    assert corrected["control"] == original["control"]
    assert corrected["evidence_lifecycle"]["decision_id"] != original["evidence_lifecycle"]["decision_id"]
    assert corrected["evidence_lifecycle"]["run_mode"] == "rehearsal"
    assert corrected["assumptions"]["budget_contract"]["initial_capital"] == 30000
    assert resolve_budget_input(tmp_path, original) == corrected
    assert _load_event_frozen_days([event], through="2026-08-21", root=tmp_path) == [corrected]
    assert _merge_days([corrected, corrected]) == [corrected]
    selected, retained = partition_repair_events([corrected], [event])
    assert selected == [] and retained == [event]
    runs = [run_book_t_shadow(corrected)]
    evaluation = evaluate_book_t_shadow(runs, lifecycle_events=selected)
    assert evaluation["sample"]["real_trading_days"] == 0
    assert evaluation["sample"]["valid_theme_decisions"] == 0
    assert evaluation["sample"]["budget_replay_days_excluded"] == 1
    inputs = _load_inputs(tmp_path)  # No original manifest: repaired failed days are valid replay inputs.
    assert inputs == [corrected]
    for verdict in (evaluate_daily_stability_soak(inputs), evaluate_engineering_burn_in(inputs)):
        assert verdict["status"] == "pending" and verdict["real_trading_days"] == 0
        assert verdict["budget_replay_days_excluded"] == 1


@pytest.mark.parametrize("fault", ["source_bytes", "derived_bytes", "resealed_manifest", "natural_provenance"])
def test_repair_rejects_corruption_or_claimed_natural_acceptance(tmp_path, fault):
    path, original, _, _ = _legacy(tmp_path)
    corrected = create_budget_repair(tmp_path, path)
    directory = tmp_path / REPAIR_ROOT / original["input_sha256"]
    if fault == "source_bytes":
        path.write_text(path.read_text() + "\n")
    elif fault == "derived_bytes":
        target = directory / "frozen_input.json"
        target.write_text(target.read_text() + "\n")
    elif fault == "resealed_manifest":
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["reference"]["original_input_sha256"] = "f" * 64
        manifest.pop("manifest_sha256")
        manifest["manifest_sha256"] = canonical_sha256(manifest)
        manifest_path.write_text(json.dumps(manifest))
    else:
        corrected["evidence_lifecycle"]["run_mode"] = "real"
        with pytest.raises(BookTShadowError):
            run_book_t_shadow(bind_book_t_shadow_input(corrected))
        return
    with pytest.raises(BookTShadowError):
        resolve_budget_input(tmp_path, original)


@pytest.mark.parametrize("fault", ["negative_sell", "negative_fee", "negative_release", "unknown_side", "zero_shares"])
def test_control_rejects_invalid_sell_economics(fault):
    portfolio, receipt, fills = _paired_case()
    actions = receipt["daily_semantics"]["actions"]
    if fault == "negative_sell":
        actions[1]["notional"] = -1
    elif fault == "negative_fee":
        actions[1]["fee"] = -1
    elif fault == "negative_release":
        actions[-1]["notional"] = -1
    elif fault == "unknown_side":
        actions[1]["side"] = "UNKNOWN"
    else:
        actions[1]["shares"] = 0
    with pytest.raises(ValueError):
        validate_control_budget(portfolio, receipt, fills)


def test_deleted_registration_cannot_consume_supplied_repair(tmp_path):
    path, original, _, _ = _legacy(tmp_path)
    corrected = create_budget_repair(tmp_path, path)
    directory = tmp_path / REPAIR_ROOT / original["input_sha256"]
    directory.rename(directory.with_name("quarantined"))
    with pytest.raises(BookTShadowError, match="registration is missing"):
        resolve_budget_input(tmp_path, corrected)


def test_public_consumer_resolves_old_path_after_account_has_evolved(tmp_path, monkeypatch, capsys):
    import scripts.book_t_shadow as consumer
    path, original, _, _ = _legacy(tmp_path)
    corrected = create_budget_repair(tmp_path, path)
    (tmp_path / "output/live/paper_account_T.json").write_text('{"cash": 123}')
    output = tmp_path / "output/research/book_t_v2_shadow"
    historical = output / "original-artifact"
    historical.mkdir(parents=True)
    (historical / "frozen_inputs.json").write_text(json.dumps([original]))
    (historical / "manifest.json").write_text(json.dumps({
        "namespace": "book_t_v2_shadow", "protocol_id": "trend-book-t-v2-shadow-v1",
        "inputs": {"frozen_input_sha256": canonical_sha256([original]), "n_days": 1},
        "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0}}))
    historical_bytes = {p: p.read_bytes() for p in historical.iterdir()}
    monkeypatch.setattr(consumer, "ROOT", tmp_path)
    monkeypatch.setattr(consumer, "_load_lifecycle_events", lambda: consumer.read_events(
        tmp_path / "output/research/book_t_v2_shadow/evidence_events.jsonl"))
    monkeypatch.setattr(consumer, "_verify_control_receipts", lambda days, **kw: _check_receipts(tmp_path, days, **kw))
    monkeypatch.setattr(consumer, "_load_event_frozen_days", lambda events, **kw: _recover_events(tmp_path, events, **kw))
    monkeypatch.setattr("sys.argv", ["book_t_shadow", "--input", str(path), "--output-dir", str(output),
                                     "--run-id", "budget-repair-research", "--json"])
    assert consumer.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["evaluation"]["sample"]["real_trading_days"] == 0
    assert len(result["evaluation"]["deferred_original_event_sha256"]) == 1
    assert all(p.read_bytes() == content for p, content in historical_bytes.items())
    stored = json.loads(Path(result["artifacts"]["frozen_inputs"]).read_text())
    assert stored == [corrected]


from scripts.book_t_shadow import _verify_control_receipts as _original_check, _load_event_frozen_days as _original_recover


def _check_receipts(root, days, **kwargs):
    _original_check(days, root=root, **kwargs)


def _recover_events(root, events, **kwargs):
    return _original_recover(events, root=root, **kwargs)


def test_theme_and_instrument_targets_are_both_hard_caps():
    portfolio = {"account_equity": 30000, "account": {"initial_capital": 30000, "cash": 30000}, "positions": []}
    plan = {"selected_themes": [{"theme_id": "a", "target_notional": 30000, "expression": {
        "instruments": [{"code": "small", "target_notional": 5000}, {"code": "large", "target_notional": 25000}]}}]}
    fills = [{"code": "small", "theme_id": "a", "status": "filled", "notional": 10000, "fee": 1}]
    assert constrain_shadow_fills(plan, portfolio, fills)[0]["status"] == "blocked"


def test_new_budget_natural_day_counts_while_replay_does_not(tmp_path):
    path, original, _, _ = _legacy(tmp_path)
    corrected = create_budget_repair(tmp_path, path)
    body = copy.deepcopy(corrected)
    body.pop("budget_repair")
    lifecycle = body["evidence_lifecycle"]
    plan = body["shadow"]["selection_plan"]
    body["evidence_lifecycle"] = build_initial_lifecycle(
        decision_id=lifecycle["decision_id"], as_of=lifecycle["as_of"], observed_at=body["as_of"],
        trading_day_index=42, run_mode="real", snapshot_sha256=plan["snapshot_sha256"], universe_sha256=plan["universe_sha256"],
        selection_plan_sha256=plan["selection_plan_sha256"], portfolio_sha256=plan["portfolio_sha256"],
        control_receipt_sha256=body["control"]["control_receipt"]["receipt_sha256"], fills=[], daily_reevaluation_complete=True)
    natural = bind_book_t_shadow_input(body)
    assert evaluate_daily_stability_soak([natural])["real_trading_days"] == 1
    assert evaluate_daily_stability_soak([corrected])["real_trading_days"] == 0


@pytest.mark.parametrize("fault", ["future_outcome", "future_date", "wrong_asof", "invalid_observed_at"])
def test_repair_does_not_hide_resealed_invalid_original_event(tmp_path, fault):
    path, _, event_path, event = _legacy(tmp_path)
    if fault == "future_outcome":
        event["data"]["rows"] = [{"as_of": "2026-08-21", "strat_ret": .99}]
    elif fault == "future_date":
        event["data"]["rows"] = [{"as_of": "2026-08-22"}]
    elif fault == "wrong_asof":
        event["data"]["as_of"] = "2026-08-22"
    else:
        event["observed_at"] = "invalid"
    event.pop("event_id")
    event["event_id"] = canonical_sha256(event)
    event_path.write_text(json.dumps(event) + "\n")
    with pytest.raises(BookTShadowError, match="source lifecycle event is invalid"):
        create_budget_repair(tmp_path, path)


def test_duplicate_input_hash_with_changed_payload_is_rejected(tmp_path):
    path, original, _, _ = _legacy(tmp_path)
    corrected = create_budget_repair(tmp_path, path)
    corrupt = copy.deepcopy(corrected)
    corrupt["assumptions"]["account_equity"] += 1
    with pytest.raises(BookTShadowError, match="conflicting payload"):
        _merge_days([corrected, corrupt])


def test_duplicate_json_boolean_type_does_not_bypass_frozen_hash(tmp_path):
    path, _, _, _ = _legacy(tmp_path)
    corrected = create_budget_repair(tmp_path, path)
    corrupt = copy.deepcopy(corrected)
    corrupt["schema_version"] = True
    with pytest.raises(BookTShadowError, match="conflicting payload"):
        _merge_days([corrected, corrupt])


def test_historical_duplicate_json_boolean_type_is_rejected(tmp_path):
    from scripts.book_t_shadow import _load_historical_days
    path, original, _, _ = _legacy(tmp_path)
    corrupt = copy.deepcopy(original)
    corrupt["schema_version"] = True
    for label, value in (("a", original), ("b", corrupt)):
        directory = tmp_path / "archives" / label
        directory.mkdir(parents=True)
        (directory / "frozen_inputs.json").write_text(json.dumps([value]))
        (directory / "manifest.json").write_text(json.dumps({
            "namespace": "book_t_v2_shadow", "protocol_id": "trend-book-t-v2-shadow-v1",
            "inputs": {"frozen_input_sha256": canonical_sha256([value]), "n_days": 1},
            "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0}}))
    with pytest.raises(BookTShadowError, match="missing or conflicting"):
        _load_historical_days(tmp_path / "archives")
