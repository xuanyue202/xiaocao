from __future__ import annotations

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_kol_policy import NOW, make_decision, make_review
from xiaocao.live import kol_policy
from xiaocao.live.book_b_workflow import adjudicate_book_b, summarize_adjudication
from xiaocao.live.trading_runner import frozen_rows_digest
from xiaocao.research.shortline_comparison import record_selection_experiments

pytestmark = pytest.mark.app_simulation


def test_final_plan_compares_economic_stages_without_claiming_equal_fills():
    from xiaocao.live.book_b_workflow import final_plan_receipt, compare_final_plans
    rows = [row(state="ACTIVE")]
    decision = adjudicate_book_b(rows, {"status":"absent","book":"B","runtime":"live"}, freeze=freeze(rows), runtime="live").receipt
    order = {"code":"000001.XSHE", "shares":100, "limit_price":10.}
    app = final_plan_receipt(decision, {"available_cash":10000}, [order])
    model = final_plan_receipt(decision, {"available_cash":10000}, [order], execution_model="paper_model")
    result = compare_final_plans(app, model)
    assert result["first_divergence"] == "execution_model"
    assert result["same_order_economics"] and result["fill_or_return_equivalence"] == "not_established"
    different_cash = final_plan_receipt(decision, {"available_cash":1000}, [order])
    assert compare_final_plans(app,different_cash)["first_divergence"] == "account_allocation"
    model["orders"][0]["shares"] = 200
    with pytest.raises(ValueError,match="HASH_MISMATCH"):
        compare_final_plans(app,model)


def row(code="000001.XSHE", state="COLD", **extra):
    return {"date": NOW.date().isoformat(), "code": code, "book": "B", "is_live": True,
            "mode": "标杆短线起爆", "mode_state": state, "mode_exec_score": 10,
            "mode_exec_star": state == "ACTIVE", "mode_trade_eligible": state == "ACTIVE",
            "kp_star": True, "vb_star": False, "mode_star": True, **extra}


def freeze(rows):
    return {"market_date": NOW.date().isoformat(), "strategy_run_id": "original",
            "strategy_sha": "a" * 40, "snapshot_sha256": frozen_rows_digest(rows),
            "snapshot_raw_sha256": "b" * 64, "snapshot_row_count": len(rows),
            "checkpoint_sha256": "c" * 64}


def published(tmp_path, *, override=False, request=None, runtime="live"):
    decision = make_decision(scale=1, runtime=runtime)
    if override:
        decision["schema_version"] = "kol-trading-decision.v2"
        decision["source_refs"][0]["author_id"] = "kol-xiaocao"
        decision["xiaocao_mode_overrides"] = [{"mode": "标杆短线起爆",
            "source_report_id": "report-1", "source_quote": "当下条件满足，跟随该起爆模式。",
            "scope": "frozen_candidates_only"}]
    if request:
        decision.update(morning_request_sha256=request, mode_mappings=[])
    review = make_review(decision)
    if request:
        review.update(morning_request_sha256=request, mode_mapping_reviewed=True)
    kol_policy.publish_decision(tmp_path, decision, review, NOW)
    return kol_policy.load_decision(tmp_path, "B", "live" if runtime == "both" else runtime, NOW)


def test_missing_expired_and_corrupt_are_not_completed_neutral(tmp_path):
    rows = [row()]
    neutral = published(tmp_path)
    actual = adjudicate_book_b(rows, neutral, freeze=freeze(rows), runtime="live").receipt
    assert actual["judgment"]["outcome"] == "published_no_change"
    assert actual["support_attempt"]["outcome"] == "not_observed"
    assert actual["strategy_codes"] == []
    assert actual["rows"][0]["selection_reason"] == "COLD_DEFAULT_GATE"
    expired = kol_policy.load_decision(tmp_path, "B", "live", NOW + timedelta(hours=3))
    missing = kol_policy.load_decision(tmp_path / "missing", "B", "live", NOW)
    corrupt = copy.deepcopy(neutral)
    corrupt["buy_scale"] = 0.1
    for policy in (expired, missing, corrupt):
        result = adjudicate_book_b(rows, policy, freeze=freeze(rows), runtime="live").receipt
        assert not result["judgment"]["outcome"].startswith("published")
        assert result["support_attempt"]["outcome"] != "completed_no_change"
    assert adjudicate_book_b([row(state="ACTIVE")], corrupt, freeze=freeze(rows), runtime="live").receipt["rows"][0]["kol_skip"]


def test_exact_mode_follow_is_shared_without_mutating_freeze_or_restoring_unknown(tmp_path):
    rows = [row(), row("000002.XSHE", "UNKNOWN", mode_exec_score=100),
            row("830001.BJSE", mode_exec_score=200),
            row("000004.XSHE", executable_fillable=False, mode_exec_score=300),
            row("000005.XSHE", mode="红盘起爆", mode_exec_score=400)]
    original = copy.deepcopy(rows)
    published(tmp_path, override=True, runtime="both")
    # load_decision requires a concrete runtime even when the record is both.
    live = kol_policy.load_decision(tmp_path, "B", "live", NOW)
    paper = kol_policy.load_decision(tmp_path, "B", "paper", NOW)
    left = adjudicate_book_b(rows, live, freeze=freeze(rows), runtime="live")
    right = adjudicate_book_b(rows, paper, freeze=freeze(rows), runtime="paper")
    assert rows == original
    assert left.receipt["strategy_codes"] == ["000001.XSHE"] == right.receipt["strategy_codes"]
    assert left.receipt["strategy_semantics_sha256"] == right.receipt["strategy_semantics_sha256"]
    assert left.receipt["receipt_sha256"] != right.receipt["receipt_sha256"]
    assert left.rows[0]["kol_mode_original_state"] == "COLD"
    with pytest.raises(ValueError, match="SCOPE_MISMATCH"):
        adjudicate_book_b(rows, live, freeze=freeze(rows), runtime="paper")


def test_current_request_needs_both_bindings_and_timely_receipt(tmp_path):
    request = "d" * 64
    policy = published(tmp_path, request=request)
    support = {"status": "validated", "decision_sha256": policy["decision_sha256"],
               "request_sha256": request, "requested_at": NOW.isoformat(),
               "completed_at": (NOW + timedelta(seconds=5)).isoformat(),
               "entry_deadline": (NOW + timedelta(minutes=5)).isoformat(), "max_wait_seconds": 120}
    support["receipt_sha256"] = kol_policy.decision_sha256(support)
    rows = [row()]
    result = adjudicate_book_b(rows, policy, freeze=freeze(rows), runtime="live", support_receipt=support)
    assert result.receipt["support_attempt"]["outcome"] == "completed_no_change"
    for field, value in (("request_sha256", "e" * 64), ("completed_at", (NOW + timedelta(minutes=3)).isoformat())):
        changed = {**support, field: value}
        changed["receipt_sha256"] = kol_policy.decision_sha256({k: v for k, v in changed.items() if k != "receipt_sha256"})
        result = adjudicate_book_b(rows, policy, freeze=freeze(rows), runtime="live", support_receipt=changed)
        assert result.receipt["support_attempt"]["outcome"] == "valid_policy_request_completion_unproved"
    timed_out = adjudicate_book_b(rows, policy, freeze=freeze(rows), runtime="live", support_receipt={"status": "timed_out"})
    assert timed_out.receipt["support_attempt"]["outcome"] == "timed_out"
    reused = {**support, "requested_at": (NOW + timedelta(seconds=1)).isoformat()}
    reused["receipt_sha256"] = kol_policy.decision_sha256({k: v for k, v in reused.items() if k != "receipt_sha256"})
    result = adjudicate_book_b(rows, policy, freeze=freeze(rows), runtime="live", support_receipt=reused)
    assert result.receipt["support_attempt"]["outcome"] == "reused_valid_policy"


def test_morning_override_requires_supported_independent_mapping(tmp_path):
    decision = make_decision(scale=1)
    decision.update(schema_version="kol-trading-decision.v2", morning_request_sha256="d" * 64,
        mode_mappings=[], xiaocao_mode_overrides=[{"mode": "标杆短线起爆", "source_report_id": "report-1",
            "source_quote": "条件成立时跟随起爆。", "scope": "frozen_candidates_only"}])
    decision["source_refs"][0]["author_id"] = "kol-xiaocao"
    def submit():
        review = make_review(decision, morning_request_sha256="d" * 64, mode_mapping_reviewed=True)
        return kol_policy.publish_decision(tmp_path, decision, review, NOW)
    with pytest.raises(ValueError, match="MAPPING_UNPROVEN"):
        submit()
    mapping = {"source_report_id": "report-1", "source_term": "红盘起爆", "target_mode": "标杆短线起爆",
               "classification": "conditional", "conditions": ["开盘条件已由当前事实证明"],
               "current_applicability": "uncertain", "reason": "原话与冻结模式的条件逐项核对"}
    decision["mode_mappings"] = [mapping]
    with pytest.raises(ValueError, match="MAPPING_UNPROVEN"):
        submit()
    mapping["current_applicability"] = "supported"
    assert submit()["status"] == "published"


def test_capture_is_immutable_original_bound_and_not_a_funded_experiment(tmp_path):
    rows = [row(), row("000002.XSHE", "ACTIVE")]
    policy = kol_policy.load_decision(tmp_path / "none", "B", "paper", NOW)
    receipt = adjudicate_book_b(rows, policy, freeze=freeze(rows), runtime="paper").receipt
    first = record_selection_experiments(tmp_path, NOW.date().isoformat(), rows, receipt)
    assert first == record_selection_experiments(tmp_path, NOW.date().isoformat(), rows, receipt)
    record = json.loads(Path(first["path"]).read_bytes())
    assert record["accounting"]["portfolio_return"] is None and record["authority"] == 0
    assert not (tmp_path / "output/live").exists()
    with pytest.raises(ValueError, match="ORIGINAL_ROWS_MISMATCH"):
        record_selection_experiments(tmp_path, NOW.date().isoformat(), rows[:1], receipt)
    receipt["strategy_codes"] = ["999999.XSHG"]
    assert summarize_adjudication(receipt, runtime="paper")["status"] == "unproved"


def test_actual_paper_no_buy_binds_canonical_batch_and_does_not_replay(tmp_path, monkeypatch):
    import sys
    from kronos_screen.scripts import paper_record as paper
    from xiaocao.live import morning_bundle, paper_decision_support

    day = "2026-10-21"
    rows = [row(date=day)]
    live = tmp_path / "output/live"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-morning")
    monkeypatch.setenv("CODEX_THREAD_ID", "fixture-producer")
    bundle = morning_bundle.publish_captured_batch(live, day,
        snapshot=(json.dumps(rows[0]) + "\n").encode(), strategy_sha="a" * 40,
        source_readiness={"completeness": "observed_responses"}, timing={})
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-morning-execution")
    monkeypatch.setattr(paper, "ROOT", tmp_path)
    monkeypatch.setattr(paper, "POS", live / "positions.jsonl")
    monkeypatch.setattr(paper, "SNAP", live / "signal_snapshots.jsonl")
    monkeypatch.setattr(paper, "_load_account", lambda *_: {})
    policy = kol_policy.load_decision(tmp_path / "none", "B", "paper", NOW)
    monkeypatch.setattr(paper, "_paper_support_context", lambda *_, **kwargs: ({"status": "NORMAL"}, policy))
    monkeypatch.setattr(sys, "argv", ["paper_record.py", "--date", day, "--pick", "mode_exec_star", "--intelligence-trade", "off"])
    args = paper._parse_args()
    paper._main_locked(args)
    claim = paper_decision_support.read_consumption(tmp_path, day, "mode_exec_star")
    explanation = claim["strategy_adjudication"]
    assert claim["snapshot_sha256"] == bundle["snapshot_raw_sha256"]
    assert explanation["freeze_sha256"] == bundle["snapshot_sha256"]
    assert explanation["rows"][0]["selection_reason"] == "COLD_DEFAULT_GATE"
    assert claim["experiment_capture"]["status"] == "selection_recorded_outcomes_pending"
    assert paper_decision_support.read_consumption_result(tmp_path, day, "mode_exec_star")["status"] == "no_buy"
    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    paper._main_locked(args)
    assert before == {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    # Observe actual paper consumption alongside a separately owned APP receipt.
    from xiaocao.live.morning_pipeline import pipeline_status
    live_policy = kol_policy.load_decision(tmp_path / "none", "B", "live", NOW)
    app_explanation = adjudicate_book_b(rows, live_policy, freeze=explanation["freeze"], runtime="live").receipt
    runs = live / "book_b_live_execution/runs"
    (runs / "checklists").mkdir(parents=True)
    (runs / "history").mkdir()
    identity = {"automation_id": "xiaocao-book-b-live-morning", "owner_thread_id": "fixture-app", "runner_pid": 123}
    (runs / "checklists/fixture.json").write_text(json.dumps({"schema_version": 1, "items": {"identity_calendar": {}, "kol_projection": {}, "orders": {}}, "binding": {**identity,
        "trade_date": day, "preparation_deadline": day + "T09:35:00+08:00"}}))
    app_receipt = {"trade_date": day, "run_id": day + "-fixture", "runner_identity": identity,
                   "status": "no_action", "strategy_adjudication": app_explanation}
    app_path = runs / "history" / (app_receipt["run_id"] + ".json")
    app_path.write_text(json.dumps(app_receipt))
    observed = pipeline_status(live, day)
    assert observed["paper_b_result"]["status"] == "no_buy"
    assert observed["book_b_strategy_comparison"][0]["status"] == "same_strategy_semantics"
    # Equal semantic hashes alone cannot substitute for the original checkpoint.
    app_explanation["freeze"]["checkpoint_sha256"] = "e" * 64
    app_explanation["receipt_sha256"] = kol_policy.decision_sha256({
        key: value for key, value in app_explanation.items() if key != "receipt_sha256"})
    app_path.write_text(json.dumps(app_receipt))
    assert pipeline_status(live, day)["book_b_strategy_comparison"][0]["status"] == "unproved"


def app_adjudication(rows, policy):
    from xiaocao.live.book_b_live_morning import apply_app_buy_permissions
    return apply_app_buy_permissions(adjudicate_book_b(rows, policy, freeze=freeze(rows), runtime="live"), rows, policy)


def test_app_star_permission_reseats_original_rank_without_restoring_cold_or_unknown(tmp_path):
    rows = [row("688028.XSHG", "ACTIVE", mode_exec_candidate_rank=1),
            row("000002.XSHE", "COLD", mode_exec_candidate_rank=2),
            row("000003.XSHE", "UNKNOWN", mode_exec_candidate_rank=3),
            row("000004.XSHE", "ACTIVE", mode_exec_star=False, mode_exec_candidate_rank=4),
            row("000005.XSHE", "ACTIVE", mode_exec_star=False, mode_exec_candidate_rank=5),
            row("000006.XSHE", "ACTIVE", mode_exec_star=False, executable_fillable=False)]
    original = copy.deepcopy(rows)
    policy = kol_policy.load_decision(tmp_path, "B", "live", NOW)
    result = app_adjudication(rows, policy)
    assert result.receipt["common_strategy_codes"] == ["688028.XSHG"]
    assert result.receipt["strategy_codes"] == ["000004.XSHE"]
    assert rows == original
    selected = [r for r in result.rows if r["mode_exec_star"]]
    assert len(selected) == 1 and selected[0]["mode_exec_target_weight"] == 0.5
    skipped = result.receipt["app_buy_permissions"]["skipped"]
    assert skipped == [{"code": "688028.XSHG", "mode": "标杆短线起爆",
                        "reason": "APP_STAR_MARKET_PERMISSION_UNAVAILABLE"}]


def test_permission_replacement_keeps_three_slots_and_one_code_per_mode(tmp_path):
    rows = [row("688028.XSHG", "ACTIVE", mode_exec_rank=1),
            row("000002.XSHE", "ACTIVE", mode="红盘起爆", mode_exec_rank=2),
            row("000003.XSHE", "ACTIVE", mode="绿断低吸", mode_exec_rank=3),
            row("000004.XSHE", "ACTIVE", mode_exec_star=False, mode_exec_candidate_rank=4),
            row("000005.XSHE", "ACTIVE", mode="另一模式", mode_exec_star=False, mode_exec_candidate_rank=5)]
    policy = kol_policy.load_decision(tmp_path, "B", "live", NOW)
    result = app_adjudication(rows, policy)
    assert result.receipt["strategy_codes"] == ["000002.XSHE", "000003.XSHE", "000004.XSHE"]
    selected = [r for r in result.rows if r["mode_exec_star"]]
    assert len({r["mode"] for r in selected}) == 3
    assert sum(r["mode_exec_target_weight"] for r in selected) == pytest.approx(.5)


def test_star_permission_is_app_only_and_model_protocol_remains_explicit(tmp_path):
    from xiaocao.research.book_b_forward import adjudicate_variant
    from xiaocao.live.book_b_workflow import final_plan_receipt, compare_final_plans
    rows = [row("688028.XSHG", "ACTIVE"), row("000002.XSHE", "COLD")]
    published(tmp_path, runtime="both")
    live = kol_policy.load_decision(tmp_path, "B", "live", NOW)
    paper = kol_policy.load_decision(tmp_path, "B", "paper", NOW)
    app = app_adjudication(rows, live)
    paper_result = adjudicate_book_b(rows, paper, freeze=freeze(rows), runtime="paper")
    _, model, _ = adjudicate_variant(rows, freeze(rows), live, "app_b_control")
    assert app.receipt["strategy_codes"] == []
    assert paper_result.receipt["strategy_codes"] == model["strategy_codes"] == ["688028.XSHG"]
    assert "app_buy_permissions" not in model
    assert adjudicate_book_b(rows, live, freeze=freeze(rows), runtime="live").receipt["strategy_codes"] == ["688028.XSHG"]
    assert app.receipt["strategy_semantics_sha256"] == model["strategy_semantics_sha256"]
    left = final_plan_receipt(app.receipt, None, [])
    right = final_plan_receipt(model, None, [])
    assert compare_final_plans(left, right)["first_divergence"] == "account_permissions"


def test_app_permission_applies_before_authorized_mode_follow(tmp_path):
    rows = [row("688028.XSHG", mode_exec_score=100), row("000002.XSHE", mode_exec_score=10)]
    policy = published(tmp_path, override=True)
    result = app_adjudication(rows, policy)
    assert result.receipt["strategy_codes"] == ["000002.XSHE"]
    assert result.rows[0]["kol_mode_override"]["mode"] == "标杆短线起爆"


def test_new_app_intent_cannot_bypass_star_filter(monkeypatch):
    from xiaocao.live import book_b_live_morning as morning
    monkeypatch.setattr(morning, "_restore_durable_plan_for_row", lambda *a, **kw: None)
    with pytest.raises(ValueError, match="APP_STAR_MARKET_PERMISSION_UNAVAILABLE"):
        morning._materialize_or_restore_plans(None, [row("688028.XSHG", "ACTIVE")],
                                              strategy_sha="a" * 40, allocation=None, now=NOW)


def test_exact_star_intent_resume_reaches_selection_without_new_buy_filter(tmp_path, monkeypatch):
    from xiaocao.live import book_b_live_morning as morning
    rows = [row("688028.XSHG", "ACTIVE")]
    binding = freeze(rows)
    monkeypatch.setattr(morning, "_assert_dated_freeze", lambda *a: binding)
    monkeypatch.setattr(morning, "_read_completed_freeze", lambda *a: rows)
    monkeypatch.setattr(morning, "_restore_durable_plan_for_row", lambda *a, **kw: object())
    actual = morning.adjudicate_book_b
    monkeypatch.setattr(morning, "apply_app_buy_permissions", lambda *a: pytest.fail("old intent must not enter new BUY filter"))
    observed = []
    def stop_after_selection(*args, **kwargs):
        result = actual(*args, **kwargs)
        observed.append(result.receipt["strategy_codes"])
        raise ValueError("STOP_AFTER_ORIGINAL_INTENT_SELECTION")
    monkeypatch.setattr(morning, "adjudicate_book_b", stop_after_selection)
    calls = []
    config = morning.BookBLiveMorningConfig(trade_date=NOW.date().isoformat(),
        freeze_path=tmp_path/"freeze.jsonl", allocation_facts_path=tmp_path/"allocation.json",
        state_dir=tmp_path/"state", resume_plan_id=f"book-b:{NOW.date().isoformat()}:688028.XSHG:BUY")
    receipt = morning.run_book_b_live_morning(config, execute=lambda p: calls.append(p), now=lambda: NOW)
    assert observed == [["688028.XSHG"]]
    assert receipt.reason == "STOP_AFTER_ORIGINAL_INTENT_SELECTION" and calls == []
