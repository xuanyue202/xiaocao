from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("weekly_deep_review", ROOT / "scripts" / "weekly_deep_review.py")
wdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wdr)


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(wdr, "ROOT", tmp_path)
    monkeypatch.setattr(wdr, "ACTION_LOG", tmp_path / "reference" / "experience" / "distill_action_log.jsonl")
    monkeypatch.setattr(wdr, "CHANGE_LEDGER", tmp_path / "output" / "live" / "flywheel_change_ledger.jsonl")
    monkeypatch.setattr(wdr, "WEEKLY_DIR", tmp_path / "output" / "live")
    monkeypatch.setattr(wdr, "SCRATCH_DIR", tmp_path / ".scratch" / "weekly-deep-review")


def _fake_flywheel():
    return {
        "spinning": True,
        "strategy_flywheel": {"status": "blocked", "pending_pass_verdicts": ["XH-037"]},
        "knowledge": {
            "candidates_total": 39,
            "candidates_tested": 10,
            "candidates_retired": 5,
            "oldest_untested": "2026-06-01",
        },
        "warnings": [],
    }


def _write_protocol_registry(root: Path):
    path = root / "reference" / "experience" / "research_protocols.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
schema_version: 1
protocols:
  - id: shortline-book-b-v1
    name: Shortline test protocol
    scope: Test strategy changes
    strategy_kernel: []
    allowed_change_surfaces: []
    forbidden_change_surfaces: []
    sample_policy: {}
    required_manifest_fields:
      - schema_version
      - protocol_id
      - hypothesis_id
      - inputs.trades_sha256
      - artifacts.trades
      - artifacts.verdict
      - verdict.status
      - git.commit
      - git.dirty
    required_artifacts:
      - manifest.json
      - trades.jsonl
      - verdict.json
    promotion_boundary: {}
    rollback: git revert <commit>
""".strip() + "\n",
        encoding="utf-8",
    )
    return path


def _write_research_manifest(root: Path, *, write_artifacts: bool = True):
    path = root / "output" / "research" / "runs" / "demo" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    verdict_path = path.parent / "verdict.json"
    trades_path = path.parent / "trades.jsonl"
    path.write_text(json.dumps({
        "schema_version": 1,
        "protocol_id": "shortline-book-b-v1",
        "hypothesis_id": "XH-037",
        "inputs": {"trades_sha256": "a" * 64},
        "artifacts": {"trades": str(trades_path), "verdict": str(verdict_path)},
        "verdict": {"status": "PASS"},
        "diagnostics": {"coverage": {"pick_alpha": 10}},
        "git": {"commit": "abc123", "dirty": True},
    }, ensure_ascii=False), encoding="utf-8")
    if write_artifacts:
        trades_path.write_text('{"day":"2026-07-01","strat_ret":0.02,"base_ret":0.01}\n', encoding="utf-8")
        verdict_path.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    return path


def test_build_plan_routes_pass_pending_and_instrumentation_todo(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    wdr.ACTION_LOG.parent.mkdir(parents=True)
    wdr.ACTION_LOG.write_text(json.dumps({
        "date": "2026-07-02",
        "kind": "盘后复盘",
        "file": "2026-07-02_review.json",
        "routing": ["instrumentation"],
        "instrumentation_todo": "record first alert +1m path",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(wdr.flywheel, "check_flywheel", lambda **_: _fake_flywheel())
    monkeypatch.setattr(wdr, "_load_sweep_json", lambda: {"scoreboard": {}, "pass_evidence": ["XH-037"], "queue": []})
    monkeypatch.setattr(wdr, "_git_status", lambda: [" M docs/existing.md"])

    plan = wdr.build_plan(as_of=dt.date(2026, 7, 2), output=tmp_path / "plan.json")

    assert plan["mode_recommendation"] == wdr.MODE_PROPOSAL
    ids = {p["id"] for p in plan["proposals"]}
    assert "pass-pending-xh-037" in ids
    auto_ids = {c["id"] for c in plan["auto_apply_candidates"]}
    assert any(i.startswith("instrumentation-2026-07-02") for i in auto_ids)
    assert plan["rules"]["outside_fixed_inputs"] == "proposal_only_requires_user_confirmation"
    assert plan["rules"]["instrumentation_todo"].startswith("auto_apply")


def test_build_plan_skips_resolved_instrumentation_todo(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    wdr.ACTION_LOG.parent.mkdir(parents=True)
    wdr.ACTION_LOG.write_text(json.dumps({
        "date": "2026-07-02",
        "kind": "盘后复盘",
        "file": "2026-07-02_review.json",
        "routing": ["instrumentation"],
        "instrumentation_todo": "implemented: scripts/strategy_hit_audit.py",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    done_fw = _fake_flywheel()
    done_fw["strategy_flywheel"] = {"status": "open", "pending_pass_verdicts": []}
    monkeypatch.setattr(wdr.flywheel, "check_flywheel", lambda **_: done_fw)
    monkeypatch.setattr(wdr, "_load_sweep_json", lambda: {"scoreboard": {}, "pass_evidence": [], "queue": []})
    monkeypatch.setattr(wdr, "_git_status", lambda: [])

    plan = wdr.build_plan(as_of=dt.date(2026, 7, 2), output=tmp_path / "plan.json")

    assert plan["mode_recommendation"] == wdr.MODE_NONE
    assert plan["proposals"] == []
    assert plan["auto_apply_candidates"] == []


def test_finalize_writes_report_ledger_and_proposal_issue(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(wdr, "_stage_and_commit", lambda **_: None)
    plan = {
        "date": "2026-07-02",
        "fixed_inputs": wdr.FIXED_INPUTS,
        "pre_existing_dirty": [],
        "flywheel": _fake_flywheel(),
        "sweep": {"scoreboard": {}, "pass_evidence": ["XH-037"]},
        "recent_action_summary": [{
            "date": "2026-07-01",
            "kind": "盘后复盘",
            "file": "2026-07-01_review.json",
            "posture_update": "确认趋势主线尾声高低切，修复偏减仓。",
            "playbook_update": "高低切要按阶段区分。",
            "hypothesis_update": "新增大涨次日不接 vs 回调低吸候选。",
            "audit_evidence": "信濠光电是真正重合样本。",
            "instrumentation_todo": "补命中审计投影工具。",
        }],
        "auto_apply_candidates": [],
        "proposals": [{
            "id": "pass-pending-xh-037",
            "title": "PASS verdict pending strategy consumption",
            "source": "scripts/flywheel_selfcheck.py",
            "reason": "PASS pending",
            "requires_confirmation": True,
            "recommended_action": "confirm mapping",
            "evidence_bundle": wdr._evidence_bundle(
                problem="PASS pending",
                attribution="ledger says PASS",
                artifact="kronos_screen/HYPOTHESES.jsonl",
                baseline="unapplied",
                overfit="already guarded",
                scope="paper strategy",
            ),
        }],
        "mode_recommendation": wdr.MODE_PROPOSAL,
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    result = wdr.finalize_plan(plan_path=plan_path, mode=None,
                               validation=["bash -n scripts/auto_daily.sh: PASS"],
                               allow_commit=False)

    report = tmp_path / result["report"]
    ledger = tmp_path / result["ledger"]
    text = report.read_text(encoding="utf-8")
    assert report.exists() and "PROPOSAL_ONLY" in text
    assert "## 需要你看/确认的事项" in text
    assert "## 这批转录给我的启发" in text
    assert "确认趋势主线尾声高低切" in text
    assert "信濠光电是真正重合样本" in text
    assert "## 已经改进/沉淀到哪里" in text
    assert "Human Attention" not in text
    assert "NEEDS_CONFIRMATION" not in text
    assert result["issues"] == [".scratch/weekly-deep-review/2026-07-02/pass-pending-xh-037.md"]
    assert (tmp_path / result["issues"][0]).exists()
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows[-1]["mode"] == wdr.MODE_PROPOSAL
    assert rows[-1]["weekly_report"] == "output/live/weekly_review_2026-07-02.md"


def test_finalize_ledger_excludes_pre_existing_dirty_allowed_files(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(wdr, "_stage_and_commit", lambda **_: None)
    monkeypatch.setattr(wdr, "_git_status", lambda: [
        " M scripts/pre_existing_dirty.py",
        "?? output/live/weekly_review_2026-07-02.md",
        "?? output/live/flywheel_change_ledger.jsonl",
    ])
    plan = {
        "date": "2026-07-02",
        "fixed_inputs": wdr.FIXED_INPUTS,
        "pre_existing_dirty": [" M scripts/pre_existing_dirty.py"],
        "flywheel": _fake_flywheel(),
        "sweep": {},
        "auto_apply_candidates": [],
        "proposals": [],
        "mode_recommendation": wdr.MODE_NONE,
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    result = wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_PROPOSAL,
                               validation=[], allow_commit=False)

    rows = [json.loads(l) for l in (tmp_path / result["ledger"]).read_text(encoding="utf-8").splitlines()]
    assert "scripts/pre_existing_dirty.py" not in rows[-1]["files_changed"]
    assert rows[-1]["files_changed"] == [
        "output/live/flywheel_change_ledger.jsonl",
        "output/live/weekly_review_2026-07-02.md",
    ]
    report = (tmp_path / result["report"]).read_text(encoding="utf-8")
    assert "本地工作区提醒，不是策略判断" in report
    assert "scripts/pre_existing_dirty.py" in report
    assert "BLOCKED_BY_DIRTY_FILE" not in report


def test_no_commit_skips_staging(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(wdr, "_git_status", lambda: ["?? output/live/weekly_review_2026-07-02.md"])

    def fake_run(cmd, *, check=False):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(wdr, "_run", fake_run)
    report = tmp_path / "output" / "live" / "weekly_review_2026-07-02.md"
    report.parent.mkdir(parents=True)
    report.write_text("report", encoding="utf-8")

    sha = wdr._stage_and_commit(
        plan={"date": "2026-07-02", "pre_existing_dirty": []},
        mode=wdr.MODE_PROPOSAL,
        validation=[],
        report_path=report,
        created_issues=[],
        allow_commit=False,
    )

    assert sha is None
    assert not any(cmd[:2] == ["git", "add"] for cmd in calls)
    assert not any(cmd[:2] == ["git", "commit"] for cmd in calls)


def test_allowed_commit_paths_are_narrow():
    assert wdr._allowed_path("scripts/weekly_deep_review.py", date_s="2026-07-02")
    assert wdr._allowed_path("output/live/weekly_review_2026-07-02.md", date_s="2026-07-02")
    assert wdr._allowed_path("output/live/flywheel_change_ledger.jsonl", date_s="2026-07-02")
    assert not wdr._allowed_path("output/live/paper_account.json", date_s="2026-07-02")
    assert not wdr._allowed_path("output/.cache/xiaocao.db", date_s="2026-07-02")


def test_auto_applied_finalize_requires_candidate_and_validation(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    plan = {
        "date": "2026-07-02",
        "fixed_inputs": wdr.FIXED_INPUTS,
        "pre_existing_dirty": [],
        "flywheel": _fake_flywheel(),
        "sweep": {},
        "auto_apply_candidates": [],
        "proposals": [],
        "mode_recommendation": wdr.MODE_NONE,
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    try:
        wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_AUTO,
                          validation=["pytest: PASS"], allow_commit=False)
    except SystemExit as e:
        assert "auto_apply_candidates" in str(e)
    else:
        raise AssertionError("AUTO_APPLIED without auto_apply_candidates should fail")

    plan["auto_apply_candidates"] = [{"id": "x", "evidence_bundle": {}}]
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    try:
        wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_AUTO,
                          validation=[], allow_commit=False)
    except SystemExit as e:
        assert "validation" in str(e)
    else:
        raise AssertionError("AUTO_APPLIED without validation should fail")

    try:
        wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_AUTO,
                          validation=["pytest: PASS"], allow_commit=False)
    except SystemExit as e:
        assert "candidate validation failed" in str(e)
    else:
        raise AssertionError("AUTO_APPLIED with incomplete evidence should fail")


def test_strategy_auto_applied_requires_protocol_and_manifest(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    plan = {
        "date": "2026-07-02",
        "fixed_inputs": wdr.FIXED_INPUTS,
        "pre_existing_dirty": [],
        "flywheel": _fake_flywheel(),
        "sweep": {},
        "auto_apply_candidates": [{
            "id": "auto-qibao-rule",
            "title": "Apply qibao paper-only rule",
            "source": "kronos_screen/HYPOTHESES.jsonl",
            "recommended_change": "Enable paper-only emitted mode backed by XH-037 PASS.",
            "evidence_bundle": wdr._evidence_bundle(
                problem="XH-037 PASS remains unapplied",
                attribution="Verdict ledger contains PASS and fixed-input weekly plan selected it.",
                artifact="kronos_screen/HYPOTHESES.jsonl",
                baseline="Current strategy does not consume the passed qibao evidence.",
                overfit="research_run PASS with multiple-comparison correction.",
                scope="paper/simulation strategy code",
            ),
        }],
        "proposals": [],
        "mode_recommendation": wdr.MODE_AUTO,
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    try:
        wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_AUTO,
                          validation=["pytest: PASS"], allow_commit=False)
    except SystemExit as e:
        text = str(e)
        assert "protocol_id" in text
        assert "research_manifest" in text
    else:
        raise AssertionError("strategy AUTO_APPLIED without protocol/manifest should fail")


def test_auto_applied_can_merge_candidate_file_and_finalize_without_commit(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    _write_protocol_registry(tmp_path)
    manifest = _write_research_manifest(tmp_path)
    monkeypatch.setattr(wdr, "_stage_and_commit", lambda **_: None)
    monkeypatch.setattr(wdr, "_git_status", lambda: [
        "?? output/live/weekly_review_2026-07-02.md",
        "?? output/live/flywheel_change_ledger.jsonl",
    ])
    plan = {
        "date": "2026-07-02",
        "fixed_inputs": wdr.FIXED_INPUTS,
        "pre_existing_dirty": [],
        "flywheel": _fake_flywheel(),
        "sweep": {},
        "auto_apply_candidates": [],
        "proposals": [],
        "mode_recommendation": wdr.MODE_NONE,
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    candidate = {
        "id": "auto-qibao-rule",
        "title": "Apply qibao paper-only rule",
        "source": "kronos_screen/HYPOTHESES.jsonl",
        "change_type": "paper_strategy",
        "protocol_id": "shortline-book-b-v1",
        "research_manifest": str(manifest.relative_to(tmp_path)),
        "recommended_change": "Enable paper-only emitted mode backed by XH-037 PASS.",
        "evidence_bundle": wdr._evidence_bundle(
            problem="XH-037 PASS remains unapplied",
            attribution="Verdict ledger contains PASS and fixed-input weekly plan selected it.",
            artifact="kronos_screen/HYPOTHESES.jsonl",
            baseline="Current strategy does not consume the passed qibao evidence.",
            overfit="research_run PASS with multiple-comparison correction; this test only validates the harness path.",
            scope="paper/simulation strategy code",
        ),
    }
    cand_path = tmp_path / "candidate.json"
    cand_path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")

    result = wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_AUTO,
                               auto_apply_candidate_paths=[cand_path],
                               validation=["pytest: PASS"],
                               allow_commit=False)

    report = (tmp_path / result["report"]).read_text(encoding="utf-8")
    assert "AUTO_APPLIED" in report
    assert "auto-qibao-rule" in report
    rows = [json.loads(l) for l in (tmp_path / result["ledger"]).read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["mode"] == wdr.MODE_AUTO
    assert rows[-1]["evidence_bundle"][0]["problem_observed"] == "XH-037 PASS remains unapplied"


def test_strategy_auto_applied_requires_manifest_artifact_files(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    _write_protocol_registry(tmp_path)
    manifest = _write_research_manifest(tmp_path, write_artifacts=False)
    plan = {
        "date": "2026-07-02",
        "fixed_inputs": wdr.FIXED_INPUTS,
        "pre_existing_dirty": [],
        "flywheel": _fake_flywheel(),
        "sweep": {},
        "auto_apply_candidates": [{
            "id": "auto-qibao-rule",
            "title": "Apply qibao paper-only rule",
            "source": "kronos_screen/HYPOTHESES.jsonl",
            "change_type": "paper_strategy",
            "protocol_id": "shortline-book-b-v1",
            "research_manifest": str(manifest.relative_to(tmp_path)),
            "recommended_change": "Enable paper-only emitted mode backed by XH-037 PASS.",
            "evidence_bundle": wdr._evidence_bundle(
                problem="XH-037 PASS remains unapplied",
                attribution="Verdict ledger contains PASS and fixed-input weekly plan selected it.",
                artifact="kronos_screen/HYPOTHESES.jsonl",
                baseline="Current strategy does not consume the passed qibao evidence.",
                overfit="research_run PASS with multiple-comparison correction.",
                scope="paper/simulation strategy code",
            ),
        }],
        "proposals": [],
        "mode_recommendation": wdr.MODE_AUTO,
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    try:
        wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_AUTO,
                          validation=["pytest: PASS"], allow_commit=False)
    except SystemExit as e:
        text = str(e)
        assert "missing required artifact" in text
        assert "trades.jsonl" in text
        assert "verdict.json" in text
    else:
        raise AssertionError("strategy AUTO_APPLIED with missing research artifacts should fail")


def test_report_quality_research_output_does_not_require_protocol_manifest(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(wdr, "_stage_and_commit", lambda **_: None)
    monkeypatch.setattr(wdr, "_git_status", lambda: [
        "?? output/live/weekly_review_2026-07-02.md",
        "?? output/live/flywheel_change_ledger.jsonl",
    ])
    plan = {
        "date": "2026-07-02",
        "fixed_inputs": wdr.FIXED_INPUTS,
        "pre_existing_dirty": [],
        "flywheel": _fake_flywheel(),
        "sweep": {},
        "auto_apply_candidates": [{
            "id": "paper-vs-market-format",
            "title": "Improve paper-vs-market report readability",
            "source": "output/research/paper_vs_market_2026-06-01_2026-07-02.md",
            "change_type": "report_quality",
            "recommended_change": "Add a compact index comparison line to the weekly report.",
            "evidence_bundle": wdr._evidence_bundle(
                problem="Weekly report needs a clearer passive-index comparison.",
                attribution="Fixed paper-vs-market report exposes the missing comparison line.",
                artifact="output/research/paper_vs_market_2026-06-01_2026-07-02.md",
                baseline="Readers must inspect the research report manually.",
                overfit="Read-only report formatting; no strategy parameter or fill behavior changes.",
                scope="report-quality only",
            ),
        }],
        "proposals": [],
        "mode_recommendation": wdr.MODE_AUTO,
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    result = wdr.finalize_plan(plan_path=plan_path, mode=wdr.MODE_AUTO,
                               validation=["pytest: PASS"], allow_commit=False)

    assert result["mode"] == wdr.MODE_AUTO
    rows = [json.loads(l) for l in (tmp_path / result["ledger"]).read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["evidence_bundle"][0]["problem_observed"] == "Weekly report needs a clearer passive-index comparison."
