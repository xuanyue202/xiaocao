"""Fixed local fixtures only: no production weekly runner, network or commit."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from xiaocao.kol import trading_decision
from xiaocao.kol.publication import canonical_sha256
from xiaocao.live import kol_policy, paper_decision_support as paper


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("weekly_kol_review_test", ROOT / "scripts/weekly_deep_review.py")
wdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wdr)
AS_OF = dt.date(2026, 9, 6)
NOW = dt.datetime(2026, 9, 6, 2, 0, tzinfo=dt.timezone.utc)
POLICY = Path("output/live/kol_policy")


def write(root, relative, value, *, jsonl=False):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = value if jsonl else [value]
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


def bound(row, key="receipt_sha256", *, canonical=False):
    return {**row, key: (canonical_sha256 if canonical else kol_policy.decision_sha256)(row)}


def publish(root, *, identifier="weekly-decision", runtime="both", book="B", when=NOW):
    decision = {
        "schema_version": kol_policy.SCHEMA_VERSION, "decision_id": identifier, "agent_id": "reader",
        "book": book, "runtime": runtime, "as_of": when.isoformat(),
        "valid_until": (when + dt.timedelta(hours=2)).isoformat(), "buy_scale": 0.5,
        "skip_codes": [], "exit_codes": [], "rationale": "固定样本的完整来源判断。",
        "invalidation_conditions": ["独立复核当前证据"],
        "source_refs": [{"report_id": "report-1", "content_sha256": "a" * 64, "author_id": "author-1",
                         "source_published_at": (when - dt.timedelta(hours=1)).isoformat(),
                         "received_at": (when - dt.timedelta(minutes=2)).isoformat()}],
        "current_checks": [{"claim": "当前来源已核验", "observed_at": when.isoformat(),
                            "evidence_ref": "fixture-quote", "verdict": "supports"}],
    }
    review = {"decision_sha256": kol_policy.decision_sha256(decision), "status": "approved",
              "reviewer_agent_id": "independent-reviewer", "reviewed_at": (when + dt.timedelta(seconds=10)).isoformat(),
              "coverage_complete": True, "source_fidelity": True,
              "applicability_checked": True, "counterevidence_checked": True}
    return kol_policy.publish_decision(root / POLICY / "decisions", decision, review, when + dt.timedelta(seconds=20))


def consumption(root, *, when=NOW, book="B", runtime="paper", identifier=None, digest=None):
    relative = ("output/live/paper_decision_support" if runtime == "paper"
                else "output/live/book_b_live_execution") + "/consumption.jsonl"
    row = {"book": book, "runtime": runtime, "consumed_at": when.isoformat(),
           "decision_id": identifier, "decision_sha256": digest, "execution_status": "not_submitted"}
    return write(root, relative, [bound(row, "consumption_sha256", canonical=True)], jsonl=True)


def risk(root, when, nav, *, account="paper:B", filename="risk"):
    row = {"account_id": account, "asof": when.isoformat(), "nav_observed_at": when.isoformat(), "nav": nav, "status": "NORMAL",
           "history_basis": "since_activation", "evidence_digest": "a" * 64}
    return write(root, POLICY / f"account_risk/risk_receipts/{filename}.json", bound(row))


def context(root):
    row = bound({"schema_version": 1, "source": "lianghui_published_registry", "as_of": NOW.isoformat(),
                 "coverage": {"registered_authors": ["old", "new"], "covered_authors": ["new"],
                              "missing_authors": ["old"], "remote_discovery": "registry_only", "incomplete": True,
                              "incomplete_reasons": [{"code": "conflicting_latest_evaluations"}]},
                 "relations": [{"record": {"payload": {"relation_type": "refines"}}}],
                 "report_index": [{"report_id": "report-1"}], "unloaded_report_ids": ["old-report"]},
                "context_sha256", canonical=True)
    write(root, POLICY / "context/fixed.context.json", row)
    return row


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def render(review):
    return wdr._render_report({"date": AS_OF.isoformat(), "kol_system_review": review},
                             mode=wdr.MODE_NONE, validation=[], created_issues=[], staged_files=[], blocked_dirty=[])


def test_missing_fixed_inputs_are_missing_not_zero_or_success(tmp_path):
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert review["status"] == "missing_evidence"
    assert review["inventory"]["audit_feedback"]["status"] == "audited"
    assert review["inventory"]["audit_feedback"]["consumption"]["paper"]["record_count"] is None
    assert not snapshot(tmp_path), "Read-only inventory must not initialize runtime stores"
    for window in review["windows"].values():
        for account in window["accounts"].values():
            for cell in account.values():
                assert cell["status"] == "missing" and cell["record_count"] is None
                assert cell["missing"]
            assert account["account_performance"]["window_return_pct"] is None
            assert account["execution_loss"]["loss_amount"] is None
            assert account["missed_opportunities"]["opportunity_pnl"] is None
    assert "关键证据缺失，未完成分析" in render(review)


def test_inventory_calls_actual_feedback_uses_dedicated_paths_and_is_fixed(tmp_path, monkeypatch):
    consumption(tmp_path)
    # An obsolete sibling is not silently accepted as the new decision store.
    write(tmp_path, POLICY / "old-decision.json", {"not": "a published decision"})
    calls = []
    actual = trading_decision.audit_feedback

    def spy(root, **kwargs):
        calls.append(root)
        return actual(root, **kwargs)

    monkeypatch.setattr(wdr.trading_decision, "audit_feedback", spy)
    before = snapshot(tmp_path)
    first = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert first == wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert calls == [tmp_path, tmp_path]
    assert snapshot(tmp_path) == before
    inventory = first["inventory"]
    assert inventory["sources"]["decisions"]["status"] == "missing"
    assert inventory["audit_feedback"]["consumption"]["paper"]["record_count"] == 1
    assert inventory["fixed_inputs"]["decisions"] == "output/live/kol_policy/decisions/*.json"
    assert inventory["fixed_inputs"]["live_morning"].endswith("runs/*.json")
    assert inventory["fixed_inputs"]["live_decisions"].endswith("book_b_live_decisions.jsonl")
    assert first["analysis_context"]["inventory_sha256"] == canonical_sha256(inventory)


def test_windows_account_identity_and_no_fabricated_returns(tmp_path):
    for days in (0, 6, 7, 27, 28, 83, 84):
        risk(tmp_path, NOW - dt.timedelta(days=days), 100000 - days, filename=str(days))
    risk(tmp_path, NOW, 999999, account="live:B", filename="wrong-account")
    consumption(tmp_path, book="T")
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    for name, count in (("1w", 2), ("4w", 4), ("12w", 6)):
        accounts = review["windows"][name]["accounts"]
        assert accounts["paper:B"]["account_performance"]["record_count"] == count
        assert accounts["paper:B"]["account_performance"]["window_return_pct"] is None
        assert accounts["live:B"]["account_performance"]["status"] == "missing"
        assert accounts["paper:T"]["execution_loss"]["record_count"] == 1
        assert accounts["paper:B"]["execution_loss"]["status"] == "missing"
    assert review["inventory"]["excluded_outside_window_count"] == 1
    assert review["inventory"]["sources"]["paper_risk"]["invalid_files"]


def test_actual_native_paper_claim_terminal_not_fills_or_opportunity_profit(tmp_path):
    receipt = publish(tmp_path, runtime="paper")
    now = NOW + dt.timedelta(minutes=1)
    decision = kol_policy.load_decision(tmp_path / POLICY / "decisions", "B", "paper", now)
    baseline = [{"code": "600519.XSHG", "execution_price": 10, "mode_exec_planned_shares": 1000}]
    _, slots = paper.apply_buy_policy(baseline, decision, {"deploy_factor": 1, "receipt_sha256": "b" * 64},
                                     kill_factor=1, fee_rate=0.0003)
    paper.write_consumption(tmp_path, AS_OF.isoformat(), "fixed", {"status": "claimed", "slots": slots,
                                                                 "kol_decision": decision})
    paper.complete_consumption(tmp_path, AS_OF.isoformat(), "fixed", entries=[{"code": "600519.XSHG", "shares": 500}])
    before = snapshot(tmp_path)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    feedback = review["inventory"]["audit_feedback"]["consumption"]["paper"]
    assert feedback["record_count"] == 1
    assert feedback["paper_slot_count"] == feedback["paper_scaled_slot_count"] == 1
    assert feedback["paper_terminal_status_counts"] == {"bought": 1}
    account = review["windows"]["1w"]["accounts"]["paper:B"]
    assert account["execution_loss"]["record_count"] == 2  # distinct artifacts, not two trades
    assert "not trades" in account["execution_loss"]["count_semantics"]
    assert account["missed_opportunities"]["status"] == "available"
    assert account["missed_opportunities"]["opportunity_pnl"] is None
    chain = review["windows"]["1w"]["decision_execution_chain"]["links"]
    assert chain[0]["decision_sha256"] == receipt["decision_sha256"]
    assert len(chain[0]["consumption"]) == 2
    assert chain[0]["execution_verification"] == "not_performed"
    assert snapshot(tmp_path) == before


def test_native_live_consumption_context_conflicts_and_latency_chain(tmp_path):
    receipt = publish(tmp_path)
    ctx = context(tmp_path)
    write(tmp_path, POLICY / "source_verifications/check.json", bound({
        "recorded_at": (NOW + dt.timedelta(seconds=15)).isoformat(),
        "payload": {"decision_id": receipt["decision_id"], "decision_sha256": receipt["decision_sha256"],
                    "context_sha256": ctx["context_sha256"]}}, "record_sha256", canonical=True))
    write(tmp_path, POLICY / "requests/request.json", bound({
        "recorded_at": NOW.isoformat(), "payload": {"book": "B", "runtime": "live", "phase": "morning",
                                                     "context": {"context_sha256": ctx["context_sha256"]}}},
        "record_sha256", canonical=True))
    write(tmp_path, "output/live/book_b_live_execution/runs/fixed.json", {
        "trade_date": AS_OF.isoformat(), "status": "blocked", "policy_consumptions": [{
            "decision_id": receipt["decision_id"], "decision_sha256": receipt["decision_sha256"],
            "consumed_at": (NOW + dt.timedelta(minutes=1)).isoformat(), "skip": True}]})
    ledger = bound({"environment": "live", "recorded_at": (NOW + dt.timedelta(minutes=2)).isoformat(),
                    "kol_decision_id": receipt["decision_id"], "kol_decision_sha256": receipt["decision_sha256"],
                    "kol_exit_currently_valid": True, "previous_hash": None}, "event_hash")
    write(tmp_path, "output/live/book_b_live_execution/book_b_live_decisions.jsonl", [ledger], jsonl=True)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    audit = review["inventory"]["audit_feedback"]["consumption"]["live"]
    assert audit["record_count"] == 2 and audit["exit_request_record_count"] == 1
    week = review["windows"]["1w"]
    links = {r["account_id"]: r for r in week["decision_execution_chain"]["links"]}
    assert len(links["live:B"]["consumption"]) == 2
    assert links["paper:B"]["consumption"] == []
    assert links["live:B"]["context"] and links["live:B"]["source_verifications"]
    assert links["live:B"]["same_context_requests_not_proven_model_runs"]
    assert week["decision_review_latency"]["observations"][0]["review_latency_seconds"] == 10
    assert week["decision_review_latency"]["observations"][0]["publication_latency_seconds"] == 10
    source = week["source_coverage"]["snapshots"][0]
    assert source["coverage"]["incomplete_reasons"][0]["code"] == "conflicting_latest_evaluations"
    assert source["relation_types"] == {"refines": 1} and source["unloaded_report_ids"] == ["old-report"]


@pytest.mark.parametrize("damage", ["truncated", "hash", "duplicate", "empty"])
def test_malformed_or_empty_consumption_is_not_success(tmp_path, damage):
    path = consumption(tmp_path)
    if damage == "hash":
        row = json.loads(path.read_text())
        row["consumption_sha256"] = "b" * 64
        path.write_text(json.dumps(row))
    else:
        path.write_text({"truncated": "{", "duplicate": '{"book":"B","book":"T"}', "empty": ""}[damage])
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert review["windows"]["1w"]["accounts"]["paper:B"]["execution_loss"]["status"] == "missing"
    assert review["inventory"]["sources"]["paper_consumption_log"]["status"] == "missing"
    assert review["status"] == "missing_evidence"


def test_broken_live_risk_chain_rejects_whole_file(tmp_path):
    receipt = {"account_id": "live:B", "asof": NOW.isoformat(), "nav": 200000, "status": "normal",
               "history_basis": "settled_history", "evidence_digest": "c" * 64}
    rows = [bound({"receipt": receipt, "previous_hash": None}, "event_hash"),
            bound({"receipt": receipt, "previous_hash": "wrong"}, "event_hash")]
    write(tmp_path, POLICY / "account_risk/live_B.jsonl", rows, jsonl=True)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert review["windows"]["1w"]["accounts"]["live:B"]["account_performance"]["status"] == "missing"
    assert review["inventory"]["sources"]["live_risk"]["invalid_files"]


def test_live_paper_nav_evidence_stays_separate(tmp_path):
    risk(tmp_path, NOW, 100000)
    receipt = {"account_id": "live:B", "asof": NOW.isoformat(), "nav_observed_at": NOW.isoformat(), "nav": 200000, "status": "NORMAL",
               "history_basis": "settled_history", "evidence_digest": "c" * 64}
    write(tmp_path, POLICY / "account_risk/live_B.jsonl",
          [bound({"receipt": receipt, "previous_hash": None}, "event_hash")], jsonl=True)
    accounts = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)["windows"]["1w"]["accounts"]
    assert accounts["live:B"]["account_performance"]["observed_nav"][0]["nav"] == 200000
    assert accounts["paper:B"]["account_performance"]["observed_nav"][0]["nav"] == 100000


@pytest.mark.parametrize("change", [{"status": "BLOCKED"}, {"nav_observed_at": None},
                                    {"nav_observed_at": (NOW - dt.timedelta(minutes=6)).isoformat()}])
def test_unusable_nav_receipt_is_not_account_performance(tmp_path, change):
    path = risk(tmp_path, NOW, 100000)
    row = json.loads(path.read_text())
    row.pop("receipt_sha256")
    path.write_text(json.dumps(bound({**row, **change})))
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert review["inventory"]["items"], "Keep the risk evidence, but do not treat it as valid NAV history"
    assert review["windows"]["1w"]["accounts"]["paper:B"]["account_performance"]["status"] == "missing"


def test_input_change_after_feedback_is_not_a_bound_snapshot(tmp_path, monkeypatch):
    path = consumption(tmp_path)
    actual = trading_decision.audit_feedback

    def racing_feedback(root, **kwargs):
        result = actual(root, **kwargs)
        # Simulate a concurrent append; valid JSON is not the same audit input.
        path.write_text(path.read_text() * 2)
        return result

    monkeypatch.setattr(wdr.trading_decision, "audit_feedback", racing_feedback)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert review["inventory"]["audit_feedback_snapshot_binding"]["paper"] == "missing_or_changed"
    assert review["windows"]["1w"]["accounts"]["paper:B"]["execution_loss"]["status"] == "missing"
    assert "消费审计与本次固定输入未能完整绑定" in render(review)


def test_previous_week_publication_links_to_this_week_consumption(tmp_path):
    when = dt.datetime(2026, 8, 30, 15, 59, tzinfo=dt.timezone.utc)
    receipt = publish(tmp_path, when=when)
    consumption(tmp_path, when=when + dt.timedelta(minutes=2), runtime="live",
                identifier=receipt["decision_id"], digest=receipt["decision_sha256"])
    week = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)["windows"]["1w"]
    assert week["decision_review_latency"]["status"] == "missing"  # no new publication this week
    links = {r["account_id"]: r for r in week["decision_execution_chain"]["links"]}
    assert links["live:B"]["consumption"]
    assert links["paper:B"]["consumption"] == []


def test_missing_native_consumption_clock_is_not_invented_from_run_date(tmp_path):
    receipt = publish(tmp_path, runtime="live")
    write(tmp_path, "output/live/book_b_live_execution/runs/fixed.json", {
        "trade_date": AS_OF.isoformat(), "status": "blocked", "policy_consumptions": [{
            "decision_id": receipt["decision_id"], "decision_sha256": receipt["decision_sha256"]}]})
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert review["inventory"]["audit_feedback"]["consumption"]["live"]["missing_consumption_clock_count"] == 1
    link = review["windows"]["1w"]["decision_execution_chain"]["links"][0]
    assert "精确消费时钟；run.trade_date 仅供日期分组" in link["missing"]


def test_legacy_native_run_does_not_prove_zero_consumption(tmp_path):
    write(tmp_path, "output/live/book_b_live_execution/runs/legacy.json", {
        "trade_date": AS_OF.isoformat(), "status": "filled"})
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    audit = review["inventory"]["audit_feedback"]["consumption"]["live"]
    assert audit["status"] == "not_recorded" and audit["record_count"] is None
    assert review["windows"]["1w"]["accounts"]["live:B"]["execution_loss"]["status"] == "missing"


@pytest.mark.parametrize("conclusion,refs_valid", [("", True), ("   ", True), ("None", True), ("改善已证实", False)])
def test_render_does_not_accept_empty_or_unbound_completed_analysis(tmp_path, conclusion, refs_valid):
    consumption(tmp_path)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    ref = dict(review["inventory"]["items"][0]["evidence"])
    if not refs_valid:
        ref["sha256"] = "wrong"
    review["analysis"].update(status="completed", framework_conclusion=conclusion, evidence_refs=[ref])
    text = render(review)
    assert "待 Astra 整体分析" in text
    assert "有证据引用的分析" not in text


def test_render_first_screen_conclusion_missing_evidence_and_experiment_slots(tmp_path):
    consumption(tmp_path)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    review["analysis"].update(status="completed", framework_conclusion="缩量可能降低资金利用率，收益增量尚未建立。",
                              evidence_refs=[review["inventory"]["items"][0]["evidence"]],
                              missing_evidence=["同风险预算无 KOL 配对回放"])
    text = render(review)
    first_screen = text.split("## 需要你看/确认的事项")[0]
    assert "缩量可能降低资金利用率" in first_screen and "同风险预算无 KOL 配对回放" in first_screen
    assert "小样本不宣称因果胜率或稳定收益" in first_screen
    assert text.count("- 证伪条件：") == 3
    assert "不是合格变更候选" in text


def test_plan_review_is_not_automatic_promotion_and_keeps_original_gates(tmp_path, monkeypatch):
    consumption(tmp_path)
    monkeypatch.setattr(wdr, "ROOT", tmp_path)
    monkeypatch.setattr(wdr, "ACTION_LOG", tmp_path / "action.jsonl")
    monkeypatch.setattr(wdr, "CHANGE_LEDGER", tmp_path / "output/live/flywheel_change_ledger.jsonl")
    monkeypatch.setattr(wdr, "_git_status", lambda: [" M scripts/existing.py"])
    monkeypatch.setattr(wdr.flywheel, "check_flywheel", lambda **kwargs: {
        "strategy_flywheel": {"pending_pass_verdicts": ["XH-existing"]}})
    monkeypatch.setattr(wdr, "_load_sweep_json", lambda: {})
    monkeypatch.setattr(wdr, "_run", lambda *a, **k: pytest.fail("No subprocess or commit allowed"))
    plan = wdr.build_plan(as_of=AS_OF, output=tmp_path / "plan.json")
    assert json.loads((tmp_path / "plan.json").read_text()) == plan
    assert plan["mode_recommendation"] == wdr.MODE_PROPOSAL
    assert plan["auto_apply_candidates"] == []
    assert plan["proposals"][0]["requires_confirmation"] is True
    assert plan["pre_existing_dirty"] == [" M scripts/existing.py"]
    review = plan["kol_system_review"]
    assert {r["id"] for r in review["competing_explanations"]} == {"baseline_no_kol", "current_bounded", "kol_challenger"}
    assert 1 <= len(review["experiment_slots"]) <= 3
    for slot in review["experiment_slots"]:
        assert all(slot[k] for k in ("objective", "falsifier", "required_evidence", "owner", "rollback", "next_review"))
        assert slot["auto_apply_eligible"] is False and slot["next_review"] == "2026-09-13"
    assert review["promotion"]["live_auto_promotion"] is False
    assert plan["fixed_inputs"] == wdr.FIXED_INPUTS
    for pattern in plan["fixed_review_inputs"].values():
        assert not wdr._source_is_fixed(pattern)
    errors = wdr._auto_apply_errors({"source": "output/research/runs/fixed/manifest.json", "change_type": "strategy"})
    assert "strategy auto_apply_candidate requires protocol_id" in errors
    assert "strategy auto_apply_candidate requires research_manifest" in errors
    with pytest.raises(SystemExit, match="pre-existing dirty"):
        wdr._stage_and_commit(plan=plan, mode=wdr.MODE_AUTO, validation=["pytest passed"],
                              report_path=tmp_path / "output/live/weekly_review_2026-09-06.md",
                              created_issues=[], allow_commit=False)


def patch_weekly_root(tmp_path, monkeypatch):
    monkeypatch.setattr(wdr, "ROOT", tmp_path)
    monkeypatch.setattr(wdr, "WEEKLY_DIR", tmp_path / "output/live")
    monkeypatch.setattr(wdr, "ACTION_LOG", tmp_path / "action.jsonl")
    monkeypatch.setattr(wdr, "CHANGE_LEDGER", tmp_path / "output/live/flywheel_change_ledger.jsonl")
    monkeypatch.setattr(wdr, "_git_status", lambda: [])
    monkeypatch.setattr(wdr.flywheel, "check_flywheel", lambda **kwargs: {})
    monkeypatch.setattr(wdr, "_load_sweep_json", lambda: {})
    monkeypatch.setattr(wdr, "_run", lambda *a, **k: pytest.fail("No subprocess, research launch or commit"))


def finalized_review_row(tmp_path, date, *, mutate=None):
    review = wdr.build_kol_system_review(tmp_path, as_of=date)
    if mutate:
        mutate(review)
    return {"date": date.isoformat(), "kol_review_state": wdr._kol_review_state({"date": date.isoformat(), "kol_system_review": review})}


def test_rollback_follow_up_finalize_roundtrip_into_next_week_context(tmp_path, monkeypatch):
    patch_weekly_root(tmp_path, monkeypatch)
    consumption(tmp_path)
    path = tmp_path / "output/live/weekly_plan_2026-09-06.json"
    plan = wdr.build_plan(as_of=AS_OF, output=path)
    slots = plan["kol_system_review"]["experiment_slots"]
    rollback = "只还原隔离研究的 fixture-v1 参数，保留失败证据；不动正式账户。"
    slots[0]["rollback"] = rollback
    slots[0]["follow_up"] = {"status": "reviewed", "disposition": "continue",
                              "conclusion": "本轮取证失败，未运行策略试验。",
                              "evidence_refs": [plan["kol_system_review"]["inventory"]["items"][0]["evidence"]]}
    path.write_text(json.dumps(plan, ensure_ascii=False))
    finalized = wdr.finalize_plan(plan_path=path, mode=wdr.MODE_NONE, validation=[], allow_commit=False)
    assert finalized["commit"] is None
    persisted = json.loads(wdr.CHANGE_LEDGER.read_text())["kol_review_state"]
    assert persisted["experiment_slots"][0]["rollback"] == rollback
    assert persisted["experiment_slots"][0]["follow_up"] == slots[0]["follow_up"]
    assert persisted["state_sha256"] == canonical_sha256({k: v for k, v in persisted.items() if k != "state_sha256"})
    assert persisted["automatic_launch"] is False
    assert "inventory" not in persisted and "prior_experiment_follow_up" not in persisted
    report = (tmp_path / finalized["report"]).read_text()
    assert rollback in report and "本轮取证失败，未运行策略试验。" in report
    before = snapshot(tmp_path)
    following = wdr.build_kol_system_review(tmp_path, as_of=AS_OF + dt.timedelta(days=7))
    assert snapshot(tmp_path) == before
    prior = following["prior_experiment_follow_up"]
    assert prior["status"] == "available" and len(prior["items"]) == 3
    assert all(item["next_review_due"] and item["current_review_status"] == "pending_review" for item in prior["items"])
    old = next(item for item in prior["items"] if item["experiment"]["experiment_id"] == slots[0]["experiment_id"])
    assert old["experiment"]["rollback"] == rollback
    assert old["source"]["sha256"] == hashlib.sha256(wdr.CHANGE_LEDGER.read_bytes()).hexdigest()
    assert old["outcome_verification"] == "not_performed"
    assert len(following["experiment_slots"]) == 3
    assert {slot["experiment_id"] for slot in following["experiment_slots"]} == {slot["experiment_id"] for slot in slots}
    assert all(slot["follow_up_required"] for slot in following["experiment_slots"])
    assert "上期试验与失败跟进" in render(following) and rollback in render(following)
    assert not wdr._source_is_fixed(following["inventory"]["fixed_inputs"]["prior_reviews"])


def test_old_unresolved_experiments_survive_12week_window_and_ignore_today_future(tmp_path):
    old_date = AS_OF - dt.timedelta(weeks=15)
    old = finalized_review_row(tmp_path, old_date)
    today = finalized_review_row(tmp_path, AS_OF)
    future = finalized_review_row(tmp_path, AS_OF + dt.timedelta(days=7))
    write(tmp_path, wdr.KOL_REVIEW_INPUTS["prior_reviews"], [old, today, future], jsonl=True)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    prior = review["prior_experiment_follow_up"]["items"]
    assert len(prior) == 3
    assert all(item["source_review_date"] == old_date.isoformat() for item in prior)
    assert all(item["next_review_due"] for item in prior)
    assert len(review["experiment_slots"]) == 3
    assert all(slot["origin_review_date"] == old_date.isoformat() for slot in review["experiment_slots"])


@pytest.mark.parametrize("damage", ["hash", "legacy", "truncated"])
def test_missing_or_corrupt_prior_review_never_reports_closed(tmp_path, damage):
    row = finalized_review_row(tmp_path, AS_OF - dt.timedelta(days=7))
    if damage == "hash":
        row["kol_review_state"]["state_sha256"] = "f" * 64
    elif damage == "legacy":
        row = {"date": row["date"], "mode": "NO_ACTION_REQUIRED"}
    path = write(tmp_path, wdr.KOL_REVIEW_INPUTS["prior_reviews"], [row], jsonl=True)
    if damage == "truncated":
        path.write_text("{")
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert review["prior_experiment_follow_up"]["status"] == "missing"
    assert review["prior_experiment_follow_up"]["automatic_launch"] is False
    assert "不能据此宣称全部完成" in render(review)


def test_empty_follow_up_does_not_retire_prior_and_slots_stay_bounded(tmp_path):
    def empty_completion(review):
        for slot in review["experiment_slots"]:
            slot["follow_up"] = {"status": "reviewed", "disposition": "completed", "conclusion": "", "evidence_refs": []}

    rows = [finalized_review_row(tmp_path, AS_OF - dt.timedelta(days=days), mutate=empty_completion) for days in (14, 7)]
    write(tmp_path, wdr.KOL_REVIEW_INPUTS["prior_reviews"], rows, jsonl=True)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert len(review["prior_experiment_follow_up"]["items"]) == 6
    assert not any(item["reported_closed"] for item in review["prior_experiment_follow_up"]["items"])
    assert review["prior_experiment_follow_up"]["unresolved_outside_slots_count"] == 3
    assert len(review["experiment_slots"]) == 3


def test_latest_follow_up_keeps_identity_and_reported_failure_without_launch(tmp_path):
    first_date = AS_OF - dt.timedelta(days=14)
    first = finalized_review_row(tmp_path, first_date)
    state = json.loads(json.dumps(first["kol_review_state"]))
    proof = write(tmp_path, "output/research/fixed-trial/verdict.json", {"status": "FAILED", "reason": "missing paired evidence"})
    follow_up = {"status": "reviewed", "disposition": "retired", "conclusion": "配对证据缺失，终止该隔离研究提案。",
                 "evidence_refs": [{"path": proof.relative_to(tmp_path).as_posix(), "sha256": hashlib.sha256(proof.read_bytes()).hexdigest()}]}
    state["experiment_slots"][0]["follow_up"] = follow_up
    later_date = (AS_OF - dt.timedelta(days=7)).isoformat()
    later = {"date": later_date, "kol_review_state": wdr._kol_review_state({
        "date": later_date, "kol_system_review": {"experiment_slots": state["experiment_slots"]}})}
    write(tmp_path, wdr.KOL_REVIEW_INPUTS["prior_reviews"], [first, later], jsonl=True)
    before = snapshot(tmp_path)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert snapshot(tmp_path) == before
    prior = review["prior_experiment_follow_up"]
    assert len(prior["items"]) == 3  # Same experiment identities, not six launches.
    retired = next(item for item in prior["items"] if item["reported_closed"])
    assert retired["experiment"]["follow_up"] == follow_up
    assert retired["source_review_date"] == later_date and retired["outcome_verification"] == "not_performed"
    assert len(review["experiment_slots"]) == 2
    assert all(slot["follow_up_required"] and not slot["auto_apply_eligible"] for slot in review["experiment_slots"])
    assert "终止该隔离研究提案" in render(review)


def test_legacy_missing_rollback_is_visible_not_invented(tmp_path):
    row = finalized_review_row(tmp_path, AS_OF - dt.timedelta(days=7))
    state = row["kol_review_state"]
    state["experiment_slots"][0].pop("rollback")
    state.pop("state_sha256")
    row["kol_review_state"] = bound(state, "state_sha256", canonical=True)
    write(tmp_path, wdr.KOL_REVIEW_INPUTS["prior_reviews"], [row], jsonl=True)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    assert any("rollback" in item["missing_fields"] for item in review["prior_experiment_follow_up"]["items"])
    assert any("rollback" not in slot for slot in review["experiment_slots"])
    assert "缺失，需补齐" in render(review)


@pytest.mark.parametrize("damage", ["rollback", "too_many", "duplicate_id"])
def test_finalize_requires_rollback_and_at_most_three_before_any_writes(tmp_path, monkeypatch, damage):
    patch_weekly_root(tmp_path, monkeypatch)
    review = wdr.build_kol_system_review(tmp_path, as_of=AS_OF)
    if damage == "rollback":
        review["experiment_slots"][0]["rollback"] = ""
    elif damage == "too_many":
        review["experiment_slots"].append(dict(review["experiment_slots"][0]))
    else:
        review["experiment_slots"][1]["experiment_id"] = review["experiment_slots"][0]["experiment_id"]
    path = write(tmp_path, "plan.json", {"date": AS_OF.isoformat(), "kol_system_review": review})
    before = snapshot(tmp_path)
    with pytest.raises(SystemExit, match="KOL weekly"):
        wdr.finalize_plan(plan_path=path, mode=wdr.MODE_NONE, validation=[], allow_commit=False)
    assert snapshot(tmp_path) == before
