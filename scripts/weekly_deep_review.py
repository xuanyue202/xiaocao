#!/usr/bin/env python3
"""Weekly Xiaocao deep review automation.

This is the audit/commit harness for the fast exploration flywheel. It does not
hard-code a strategy change. Instead it:

  * builds a plan from fixed, local inputs;
  * turns weak or out-of-input-list findings into explicit proposals;
  * lets the Codex agent implement only evidence-backed AUTO_APPLY items;
  * finalizes with a weekly report, append-only change ledger, allowlist staging,
    and an optional current-branch commit.

The deterministic spine, account history, raw caches, and live authorization files
are never edited here. Real code changes are made by the agent between --plan and
--finalize, then this harness checks the dirty-file boundary and records evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import flywheel  # noqa: E402
from xiaocao.research import protocols  # noqa: E402

ACTION_LOG = ROOT / "reference" / "experience" / "distill_action_log.jsonl"
CHANGE_LEDGER = ROOT / "output" / "live" / "flywheel_change_ledger.jsonl"
WEEKLY_DIR = ROOT / "output" / "live"
SCRATCH_DIR = ROOT / ".scratch" / "weekly-deep-review"

MODE_AUTO = "AUTO_APPLIED"
MODE_PROPOSAL = "PROPOSAL_ONLY"
MODE_NONE = "NO_ACTION_REQUIRED"
MODES = {MODE_AUTO, MODE_PROPOSAL, MODE_NONE}
MODE_LABELS = {
    MODE_AUTO: "已按证据自动落地",
    MODE_PROPOSAL: "只给提案，等你确认",
    MODE_NONE: "本周无需动作",
}

NULLISH = {"", "none", "no_change", "not_applicable", "no_issue_created", "[]", "{}"}
REQUIRED_EVIDENCE_FIELDS = {
    "problem_observed",
    "attribution",
    "evidence_artifact",
    "baseline_vs_variant",
    "overfit_check",
    "change_scope",
    "rollback",
}
REQUIRED_AUTO_APPLY_FIELDS = {"id", "title", "source", "recommended_change", "evidence_bundle"}
FIXED_INPUTS = [
    "scripts/flywheel_selfcheck.py",
    "scripts/flywheel_sweep.py --json --top 30",
    "reference/experience/distill_action_log.jsonl",
    "kronos_screen/HYPOTHESES.jsonl",
    "output/research/*",
    "output/live/pnl_decompose.csv",
    "output/research/paper_vs_market_*.md",
    "output/live/posture_calibration.jsonl",
    "output/live/exit_calibration.jsonl",
    "reference/experience/research_protocols.yaml",
    "output/research/runs/*/manifest.json",
    "git status --porcelain",
]


def _today() -> dt.date:
    return dt.date.today()


def _jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src" if not env.get("PYTHONPATH") else f"src:{env['PYTHONPATH']}"
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, check=check)


def _git_status() -> list[str]:
    cp = _run(["git", "status", "--porcelain"])
    if cp.returncode != 0:
        return [f"!! git status failed: {cp.stderr.strip()}"]
    return [line for line in cp.stdout.splitlines() if line.strip()]


def _status_path(line: str) -> str:
    # porcelain v1: XY SP path, or XY SP old -> new. Keep the destination path.
    p = line[3:] if len(line) > 3 else line
    if " -> " in p:
        p = p.split(" -> ", 1)[1]
    return p.strip().strip('"')


def _dirty_paths(lines: list[str]) -> set[str]:
    return {_status_path(line) for line in lines if line and not line.startswith("!! ")}


def _load_sweep_json() -> dict:
    cp = _run([sys.executable, "scripts/flywheel_sweep.py", "--json", "--top", "30"])
    if cp.returncode != 0:
        return {"error": cp.stderr.strip() or cp.stdout.strip(), "scoreboard": {}, "pass_evidence": [], "queue": []}
    try:
        return json.loads(cp.stdout)
    except json.JSONDecodeError:
        return {"error": cp.stdout[-1000:], "scoreboard": {}, "pass_evidence": [], "queue": []}


def _recent_action_rows(end: dt.date, *, days: int = 7) -> list[dict]:
    start = end - dt.timedelta(days=days - 1)
    rows = []
    for r in _jsonl(ACTION_LOG):
        try:
            d = dt.date.fromisoformat(str(r.get("date")))
        except ValueError:
            continue
        if start <= d <= end:
            rows.append(r)
    return rows


def _is_nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)):
        return not value
    return str(value).strip().lower() in NULLISH


def _is_meaningful_summary(value: Any) -> bool:
    if _is_nullish(value):
        return False
    return not str(value).strip().lower().startswith("legacy_backfill:")


def _is_resolved_instrumentation(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith(("implemented:", "已实现", "done:"))


def _distilled_path(file_name: str | None) -> Path | None:
    if not file_name:
        return None
    path = ROOT / "reference" / "experience" / "distilled" / str(file_name)
    return path if path.exists() else None


def _load_distilled(file_name: str | None) -> dict:
    path = _distilled_path(file_name)
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _clip(s: Any, *, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _report_action_rows(plan: dict, *, limit: int = 4) -> list[dict]:
    rows = [
        r for r in plan.get("recent_action_summary", [])
        if any(_is_meaningful_summary(r.get(k)) for k in (
            "posture_update", "playbook_update", "hypothesis_update",
            "audit_evidence", "instrumentation_todo",
        ))
    ]
    return rows[-limit:]


def _render_transcript_insights(plan: dict) -> list[str]:
    rows = _report_action_rows(plan)
    if not rows:
        return ["- 本周没有新的高信号转录启发。"]
    out: list[str] = []
    for row in rows:
        distilled = _load_distilled(row.get("file"))
        label = f"{row.get('date')} {row.get('kind') or ''}".strip()
        if row.get("file"):
            label += f"（{row.get('file')}）"
        out.append(f"- **{label}**")
        summary = distilled.get("summary")
        if summary:
            out.append(f"  启发：{_clip(summary, limit=220)}")
        if _is_meaningful_summary(row.get("posture_update")):
            out.append(f"  姿态：{_clip(row.get('posture_update'))}")
        if _is_meaningful_summary(row.get("playbook_update")):
            out.append(f"  打法：{_clip(row.get('playbook_update'))}")
        if _is_meaningful_summary(row.get("hypothesis_update")):
            out.append(f"  待验证：{_clip(row.get('hypothesis_update'))}")
        if _is_meaningful_summary(row.get("audit_evidence")):
            out.append(f"  命中审计：{_clip(row.get('audit_evidence'))}")
        if _is_meaningful_summary(row.get("instrumentation_todo")):
            out.append(f"  工具缺口：{_clip(row.get('instrumentation_todo'))}")
    return out


def _render_knowledge_changes(plan: dict) -> list[str]:
    rows = _report_action_rows(plan)
    if not rows:
        return ["- 没有新的知识层变更。"]
    buckets = [
        ("posture_update", "姿态先验"),
        ("playbook_update", "Playbook/纪律"),
        ("hypothesis_update", "候选假设"),
        ("audit_evidence", "命中审计"),
        ("instrumentation_todo", "工具/流程提案"),
    ]
    out: list[str] = []
    for key, label in buckets:
        items = [
            f"{r.get('date')} {r.get('file')}: {_clip(r.get(key), limit=190)}"
            for r in rows
            if _is_meaningful_summary(r.get(key))
        ]
        if items:
            out.append(f"- **{label}**")
            out.extend(f"  - {item}" for item in items)
    return out or ["- 没有新的知识层变更。"]


def _human_proposal_line(p: dict) -> str:
    pid = str(p.get("id", "proposal"))
    if pid.startswith("pass-pending-"):
        pending_ids = re.findall(r"xh-\d+", pid, flags=re.IGNORECASE)
        pending = ", ".join(x.upper() for x in pending_ids) or pid.removeprefix("pass-pending-").upper()
        return (
            f"- **确认策略映射方案**：{pending} 已经通过研究/纪律口径，但这次固定输入里还缺"
            "明确的落地映射、不过拟合说明或回滚方案。证据链补齐后可以自动落地；现在先写成提案，避免想当然改策略。"
        )
    if pid.startswith("instrumentation-"):
        reason = str(p.get("reason") or "").removeprefix("提案：").strip()
        return (
            f"- **补流程工具**：{_clip(reason, limit=180)} "
            "这是只读观测工具，不改策略/参数/成交/账户；以后这类固定输入里的工具缺口默认直接优化。"
        )
    return f"- **需要确认** `{pid}`：{_clip(p.get('title') or p.get('reason'), limit=180)}"


def _render_needs_review(plan: dict, blocked_dirty: list[str]) -> list[str]:
    out = [_human_proposal_line(p) for p in plan.get("proposals", [])]
    pending = plan.get("flywheel", {}).get("strategy_flywheel", {}).get("pending_pass_verdicts") or []
    if pending and not any(str(p.get("id", "")).startswith("pass-pending-") for p in plan.get("proposals", [])):
        out.append(
            f"- **确认策略映射方案**：{', '.join(pending)} 已 PASS，但本次 plan 没有给出"
            "可直接落地的代码映射/不过拟合/回滚方案。"
        )
    if blocked_dirty:
        sample = ", ".join(blocked_dirty[:5])
        more = f"；另有 {len(blocked_dirty) - 5} 个" if len(blocked_dirty) > 5 else ""
        out.append(
            f"- **本地工作区提醒，不是策略判断**：有 {len(blocked_dirty)} 个本来就 dirty 的可改路径，"
            f"本周自动化不会碰它们。样例：{sample}{more}。"
        )
    return out or ["- 没有需要你确认的事项。"]


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s.strip()).strip("-").lower()
    return s[:80] or "proposal"


def _evidence_bundle(
    *,
    problem: str,
    attribution: str,
    artifact: str,
    baseline: str,
    overfit: str,
    scope: str,
    rollback: str = "git revert <commit>",
) -> dict:
    return {
        "problem_observed": problem,
        "attribution": attribution,
        "evidence_artifact": artifact,
        "baseline_vs_variant": baseline,
        "overfit_check": overfit,
        "change_scope": scope,
        "rollback": rollback,
    }


def _source_is_fixed(source: str) -> bool:
    source = str(source or "")
    if source in FIXED_INPUTS:
        return True
    return (
        source.startswith("output/research/")
        or source == "output/live/pnl_decompose.csv"
        or source == "output/live/posture_calibration.jsonl"
        or source == "output/live/exit_calibration.jsonl"
        or source == "reference/experience/distill_action_log.jsonl"
        or source == "reference/experience/research_protocols.yaml"
        or source == "kronos_screen/HYPOTHESES.jsonl"
    )


def _repo_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _protocol_registry_path() -> Path:
    return ROOT / "reference" / "experience" / "research_protocols.yaml"


def _nested_get(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _candidate_requires_research_protocol(candidate: dict[str, Any]) -> bool:
    change_type = str(candidate.get("change_type", "")).lower()
    strategy_types = {"strategy", "paper_strategy", "simulation_strategy", "research_strategy", "strategy_return"}
    tooling_types = {"tooling", "instrumentation", "observability", "report_quality", "reporting", "research_tooling"}
    if change_type in strategy_types:
        return True
    if change_type in tooling_types:
        return False
    source = str(candidate.get("source", ""))
    if source == "kronos_screen/HYPOTHESES.jsonl":
        return True
    if source.startswith("output/research/runs/") and source.endswith("/manifest.json"):
        return True
    return source.startswith("output/research/") and not change_type


def _manifest_artifact_path(artifact: str, manifest: dict[str, Any], manifest_path: Path) -> Path:
    if Path(artifact).name == manifest_path.name:
        return manifest_path
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    for key in (artifact, Path(artifact).stem, Path(artifact).name):
        value = artifacts.get(key)
        if value:
            p = Path(str(value))
            if p.is_absolute():
                return p
            return ROOT / p if len(p.parts) > 1 else manifest_path.parent / p
    return manifest_path.parent / artifact


def _research_protocol_errors(candidate: dict[str, Any]) -> list[str]:
    if not _candidate_requires_research_protocol(candidate):
        return []
    errors: list[str] = []
    protocol_id = str(candidate.get("protocol_id") or "")
    manifest_value = str(candidate.get("research_manifest") or "")
    if not protocol_id:
        errors.append("strategy auto_apply_candidate requires protocol_id")
    if not manifest_value:
        errors.append("strategy auto_apply_candidate requires research_manifest")
    if errors:
        return errors

    try:
        protocol = protocols.find_protocol(protocol_id, path=_protocol_registry_path())
    except (FileNotFoundError, OSError) as exc:
        return [f"strategy protocol registry unavailable: {exc}"]
    if protocol is None:
        errors.append(f"unknown strategy protocol_id: {protocol_id}")
        return errors

    manifest_path = _repo_path(manifest_value)
    if not manifest_path.exists():
        return [f"research_manifest does not exist: {manifest_value}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"research_manifest is not valid JSON: {manifest_value}: {exc}"]

    if manifest.get("protocol_id") != protocol_id:
        errors.append(
            f"research_manifest protocol_id mismatch: candidate={protocol_id} manifest={manifest.get('protocol_id')}"
        )
    verdict_status = str(_nested_get(manifest, "verdict.status") or "").upper()
    if verdict_status != "PASS":
        errors.append(
            f"research_manifest verdict must be PASS for strategy AUTO_APPLIED: {verdict_status or 'missing'}"
        )
    for field in protocol.get("required_manifest_fields", []):
        if _is_nullish(_nested_get(manifest, str(field))):
            errors.append(f"research_manifest missing/empty required field for {protocol_id}: {field}")
    for artifact in protocol.get("required_artifacts", []):
        artifact_name = str(artifact)
        artifact_path = _manifest_artifact_path(artifact_name, manifest, manifest_path)
        if not artifact_path.exists():
            errors.append(
                f"research_manifest missing required artifact for {protocol_id}: "
                f"{artifact_name} ({_display_path(artifact_path)})"
            )
    return errors


def _evidence_errors(bundle: Any) -> list[str]:
    if not isinstance(bundle, dict):
        return ["evidence_bundle must be a dict"]
    missing = sorted(k for k in REQUIRED_EVIDENCE_FIELDS if _is_nullish(bundle.get(k)))
    return [f"evidence_bundle missing/empty keys: {missing}"] if missing else []


def _auto_apply_errors(candidate: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["auto_apply_candidate must be a dict"]
    missing = sorted(k for k in REQUIRED_AUTO_APPLY_FIELDS if _is_nullish(candidate.get(k)))
    if missing:
        errors.append(f"auto_apply_candidate missing/empty keys: {missing}")
    errors.extend(_evidence_errors(candidate.get("evidence_bundle")))
    source = str(candidate.get("source", ""))
    if source and not _source_is_fixed(source):
        errors.append(f"auto_apply_candidate source is outside fixed inputs: {source}")
    errors.extend(_research_protocol_errors(candidate))
    return errors


def _load_auto_apply_candidates(paths: list[Path] | None) -> list[dict]:
    out: list[dict] = []
    for path in paths or []:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        try:
            data = json.loads(text)
            if isinstance(data, list):
                out.extend(data)
            else:
                out.append(data)
            continue
        except json.JSONDecodeError:
            pass
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            out.append(json.loads(s))
    return out


def _proposal(
    *,
    pid: str,
    title: str,
    reason: str,
    evidence: dict,
    recommended_action: str,
    source: str,
    requires_confirmation: bool = True,
) -> dict:
    return {
        "id": pid,
        "title": title,
        "source": source,
        "reason": reason,
        "requires_confirmation": requires_confirmation,
        "recommended_action": recommended_action,
        "evidence_bundle": evidence,
    }


def _auto_apply_candidate(
    *,
    cid: str,
    title: str,
    source: str,
    recommended_change: str,
    evidence: dict,
) -> dict:
    return {
        "id": cid,
        "title": title,
        "source": source,
        "recommended_change": recommended_change,
        "evidence_bundle": evidence,
    }


def build_plan(*, as_of: dt.date | None = None, output: Path | None = None) -> dict:
    as_of = as_of or _today()
    pre_dirty = _git_status()
    fw = flywheel.check_flywheel(root=ROOT, env={})
    sweep = _load_sweep_json()
    action_rows = _recent_action_rows(as_of)

    proposals: list[dict] = []
    auto_apply_candidates: list[dict] = []

    pending = fw.get("strategy_flywheel", {}).get("pending_pass_verdicts") or []
    if pending:
        proposals.append(_proposal(
            pid="pass-pending-" + "-".join(str(x).lower() for x in pending),
            title=f"{', '.join(pending)} 已 PASS，但还没有进入策略消费",
            source="scripts/flywheel_selfcheck.py",
            reason=f"策略飞轮发现已 PASS 但未消费的证据：{', '.join(pending)}。",
            recommended_action="补齐明确落地映射、不过拟合证据和回滚方案；齐了就按固定输入走 AUTO_APPLIED，否则维持提案。",
            evidence=_evidence_bundle(
                problem=f"已 PASS 但没有进入策略消费：{', '.join(pending)}",
                attribution="flywheel_selfcheck 从 verdict ledger 读到 PASS；缺口是 ② 证据没有进入 ③ 策略更新。",
                artifact="kronos_screen/HYPOTHESES.jsonl + scripts/flywheel_selfcheck.py",
                baseline="当前行为只是把 PASS 证据暴露出来，没有应用到纸面/模拟策略。",
                overfit="PASS 本身不等于任意改代码；自动落地需要明确映射、不过拟合说明和可回滚方案。",
                scope="纸面/模拟策略提案",
            ),
        ))

    for row in action_rows:
        todo = row.get("instrumentation_todo")
        if _is_nullish(todo) or _is_resolved_instrumentation(todo):
            continue
        pid = f"instrumentation-{row.get('date')}-{_slug(str(todo))}"
        auto_apply_candidates.append(_auto_apply_candidate(
            cid=pid,
            title=f"补命中审计投影工具：{row.get('file')}",
            source="reference/experience/distill_action_log.jsonl",
            recommended_change="实现只读观测/投影工具；不改变策略、参数、买卖、账户或资金。",
            evidence=_evidence_bundle(
                problem=f"转录解读暴露了工具缺口：{todo}",
                attribution="这个缺口来自 action_summary.instrumentation_todo 的显式路由，不是临时脑补。",
                artifact=f"reference/experience/distilled/{row.get('file')}",
                baseline="没有这个工具/字段时，后续命中审计仍要手动拼 recommend、signal、positions、cohorts。",
                overfit="这是只读观测工具，不改变收益路径；负作用限于维护成本/报告噪音，可用测试和报告样例约束。",
                scope="流程/观测工具自动优化",
            ),
        ))

    plan = {
        "date": as_of.isoformat(),
        "week_start": (as_of - dt.timedelta(days=6)).isoformat(),
        "week_end": as_of.isoformat(),
        "fixed_inputs": FIXED_INPUTS,
        "pre_existing_dirty": pre_dirty,
        "flywheel": fw,
        "sweep": sweep,
        "recent_action_summary": action_rows,
        "auto_apply_candidates": auto_apply_candidates,
        "proposals": proposals,
        "mode_recommendation": MODE_PROPOSAL if proposals else (MODE_AUTO if auto_apply_candidates else MODE_NONE),
        "rules": {
            "outside_fixed_inputs": "proposal_only_requires_user_confirmation",
            "auto_apply_requires": (
                "complete evidence_bundle + fixed input source + validation + clean target files; "
                "strategy/research consumption also requires protocol_id + research_manifest"
            ),
            "instrumentation_todo": "auto_apply_when_read_only_and_from_fixed_action_log; no user confirmation required",
            "dirty_file_boundary": "pre-existing dirty files are not auto-edited; emit NEEDS_HUMAN_CONFIRMATION",
        },
    }
    if output is None:
        output = WEEKLY_DIR / f"weekly_plan_{as_of.isoformat()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"weekly plan: wrote {_display_path(output)} ({len(proposals)} proposal(s), "
          f"{len(auto_apply_candidates)} auto-apply candidate(s))")
    return plan


def _write_proposal_issues(plan: dict) -> list[str]:
    created: list[str] = []
    if not plan.get("proposals"):
        return created
    day_dir = SCRATCH_DIR / str(plan["date"])
    day_dir.mkdir(parents=True, exist_ok=True)
    for p in plan["proposals"]:
        path = day_dir / f"{_slug(p['id'])}.md"
        body = [
            f"# {p['title']}",
            "",
            f"- mode: PROPOSAL_ONLY",
            f"- source: {p['source']}",
            f"- requires_confirmation: {p['requires_confirmation']}",
            "",
            "## 为什么需要你看",
            p["reason"],
            "",
            "## 建议动作",
            p["recommended_action"],
            "",
            "## 证据包",
            "```json",
            json.dumps(p["evidence_bundle"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        path.write_text("\n".join(body), encoding="utf-8")
        created.append(str(path.relative_to(ROOT)))
    return created


def _allowed_path(path: str, *, date_s: str) -> bool:
    allowed_prefixes = (
        "scripts/", "src/", "tests/", "docs/", ".codex/", "reference/experience/",
        "kronos_screen/", ".scratch/weekly-deep-review/",
    )
    if path.startswith(allowed_prefixes):
        return True
    if path == f"output/live/weekly_review_{date_s}.md":
        return True
    if path == "output/live/flywheel_change_ledger.jsonl":
        return True
    return False


def _validation_lines(validation: list[str]) -> list[str]:
    return validation or ["not_run"]


def _validation_failed(validation: list[str]) -> bool:
    return any(re.search(r"\b(fail|failed|error)\b", line, re.IGNORECASE) for line in validation)


def _render_report(plan: dict, *, mode: str, validation: list[str], created_issues: list[str],
                   staged_files: list[str], blocked_dirty: list[str]) -> str:
    fw = plan.get("flywheel", {})
    knowledge = fw.get("knowledge", {})
    strategy = fw.get("strategy_flywheel", {})
    human_mode = MODE_LABELS.get(mode, mode)
    decision_count = len(plan.get("proposals", []))
    reminder = "；另有 1 条本地工作区提醒" if blocked_dirty else ""
    lines = [
        f"# 小草每周深度复盘 {plan['date']}",
        "",
        "## 先看结论",
        f"- 本周模式：{human_mode}（`{mode}`）。",
        f"- 自动改策略代码：{'有，见下方「已自动落地」' if mode == MODE_AUTO else '没有。没有完整证据链时只产出提案/审计，不想当然改策略。'}",
        f"- 需要你确认的事项：{decision_count} 个{reminder}，见下一节。",
        "",
        "## 需要你看/确认的事项",
    ]
    lines.extend(_render_needs_review(plan, blocked_dirty))
    lines += [
        "",
        "## 这批转录给我的启发",
    ]
    lines.extend(_render_transcript_insights(plan))
    lines += [
        "",
        "## 已经改进/沉淀到哪里",
    ]
    lines.extend(_render_knowledge_changes(plan))
    lines += [
        "",
        "## 已自动落地的代码/配置变更",
    ]
    if mode == MODE_AUTO:
        for c in plan.get("auto_apply_candidates", []):
            lines.append(f"- `{c.get('id')}` {c.get('title')}: {c.get('recommended_change')}")
        lines.append("")
        lines.append("本次纳入提交/暂存的文件：")
        lines.extend([f"- {p}" for p in staged_files] or ["- none detected"])
    else:
        lines.append("- none")
    lines += [
        "",
        "## 证据来源",
        f"- 固定输入清单：{', '.join(plan.get('fixed_inputs', []))}",
        f"- 提案数量：{len(plan.get('proposals', []))}",
        f"- 自动落地候选数量：{len(plan.get('auto_apply_candidates', []))}",
        "",
        "## 验证",
    ]
    lines.extend(f"- {v}" for v in _validation_lines(validation))
    lines += [
        "",
        "## 回滚",
        "- 如果本周有提交：`git revert <commit>`",
        "",
        "## 飞轮健康度",
        f"- 总体在转：{fw.get('spinning')}",
        f"- 策略飞轮：{strategy.get('status')}；待处理 PASS={strategy.get('pending_pass_verdicts')}",
        f"- 知识飞轮：候选 {knowledge.get('candidates_total')} / 已测 {knowledge.get('candidates_tested')} / 已退役 {knowledge.get('candidates_retired')} / 最老未测 {knowledge.get('oldest_untested')}",
        "",
        "## 提案文件",
    ]
    lines.extend(f"- {p}" for p in created_issues) if created_issues else lines.append("- none")
    lines += [
        "",
        "## 机器审计明细",
        "```json",
        json.dumps({
            "scoreboard": plan.get("sweep", {}).get("scoreboard", {}),
            "pass_evidence": plan.get("sweep", {}).get("pass_evidence", []),
            "pre_existing_dirty_count": len(plan.get("pre_existing_dirty", [])),
            "pre_existing_dirty_sample": plan.get("pre_existing_dirty", [])[:20],
        }, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def _append_ledger(plan: dict, *, mode: str, report_path: str, validation: list[str],
                   files_changed: list[str], created_issues: list[str]) -> None:
    CHANGE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    evidence = [p["evidence_bundle"] for p in plan.get("proposals", [])]
    evidence.extend(c.get("evidence_bundle") for c in plan.get("auto_apply_candidates", [])
                    if c.get("evidence_bundle"))
    rec = {
        "date": plan["date"],
        "mode": mode,
        "commit": "SELF_COMMIT",
        "evidence_bundle": evidence,
        "files_changed": files_changed,
        "validation": validation,
        "weekly_report": report_path,
        "proposal_issues": created_issues,
    }
    with CHANGE_LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def _stage_and_commit(*, plan: dict, mode: str, validation: list[str], report_path: Path,
                      created_issues: list[str], allow_commit: bool) -> str | None:
    current = _git_status()
    pre_dirty = _dirty_paths(plan.get("pre_existing_dirty", []))
    current_dirty = _dirty_paths(current)
    generated = {str(report_path.relative_to(ROOT)), str(CHANGE_LEDGER.relative_to(ROOT)), *created_issues}
    candidates = sorted(p for p in current_dirty if _allowed_path(p, date_s=plan["date"]))
    blocked_dirty = sorted((set(candidates) - generated) & pre_dirty)
    if blocked_dirty and mode == MODE_AUTO:
        raise SystemExit("AUTO_APPLIED blocked by pre-existing dirty file(s): " + ", ".join(blocked_dirty))
    stage_files = sorted((set(candidates) - set(blocked_dirty)) | generated)
    if mode == MODE_NONE:
        return None
    if not stage_files:
        print("weekly finalize: no allowed files to stage; skip commit")
        return None
    if not allow_commit:
        print("weekly finalize: commit disabled by --no-commit; skip staging")
        return None
    _run(["git", "add", "--", *stage_files], check=True)
    verb = "apply" if mode == MODE_AUTO else "propose"
    msg = [
        f"weekly: {verb} xiaocao flywheel updates {plan['date']}",
        "",
        mode,
        "",
        f"Weekly report: {report_path.relative_to(ROOT)}",
        "Validation:",
        *[f"- {v}" for v in _validation_lines(validation)],
        "",
        "Rollback: git revert <commit>",
    ]
    _run(["git", "commit", "-m", "\n".join(msg)], check=True)
    sha = _run(["git", "rev-parse", "--short", "HEAD"], check=True).stdout.strip()
    print(f"weekly finalize: committed {sha}")
    return sha


def finalize_plan(*, plan_path: Path, mode: str | None, validation: list[str],
                  auto_apply_candidate_paths: list[Path] | None = None,
                  allow_commit: bool) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    extra_candidates = _load_auto_apply_candidates(auto_apply_candidate_paths)
    if extra_candidates:
        plan.setdefault("auto_apply_candidates", []).extend(extra_candidates)
    if mode is None:
        if plan.get("auto_apply_candidates"):
            mode = MODE_AUTO
        else:
            mode = plan.get("mode_recommendation") or (MODE_PROPOSAL if plan.get("proposals") else MODE_NONE)
    if mode not in MODES:
        raise SystemExit(f"invalid mode {mode!r}; expected one of {sorted(MODES)}")
    if mode == MODE_AUTO:
        if not plan.get("auto_apply_candidates"):
            raise SystemExit("AUTO_APPLIED requires explicit auto_apply_candidates in the weekly plan")
        if not validation:
            raise SystemExit("AUTO_APPLIED requires validation evidence")
        if _validation_failed(validation):
            raise SystemExit("AUTO_APPLIED validation contains failure/error marker")
        errors: list[str] = []
        for i, c in enumerate(plan.get("auto_apply_candidates", [])):
            errors.extend(f"auto_apply_candidates[{i}]: {e}" for e in _auto_apply_errors(c))
        if errors:
            raise SystemExit("AUTO_APPLIED candidate validation failed:\n" + "\n".join(errors))

    created_issues = _write_proposal_issues(plan)
    report = WEEKLY_DIR / f"weekly_review_{plan['date']}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    current = _git_status()
    pre_dirty = _dirty_paths(plan.get("pre_existing_dirty", []))
    current_dirty = _dirty_paths(current)
    generated = {str(report.relative_to(ROOT)), str(CHANGE_LEDGER.relative_to(ROOT)), *created_issues}
    allowed_now = sorted(p for p in current_dirty if _allowed_path(p, date_s=plan["date"]))
    blocked_dirty = sorted((set(allowed_now) - generated) & pre_dirty)
    files_changed = sorted((set(allowed_now) - set(blocked_dirty)) | generated)
    report.write_text(_render_report(plan, mode=mode, validation=validation,
                                     created_issues=created_issues,
                                     staged_files=files_changed,
                                     blocked_dirty=blocked_dirty),
                      encoding="utf-8")
    _append_ledger(plan, mode=mode, report_path=str(report.relative_to(ROOT)),
                   validation=validation, files_changed=files_changed,
                   created_issues=created_issues)
    sha = _stage_and_commit(plan=plan, mode=mode, validation=validation, report_path=report,
                            created_issues=created_issues, allow_commit=allow_commit)
    return {
        "mode": mode,
        "report": str(report.relative_to(ROOT)),
        "ledger": str(CHANGE_LEDGER.relative_to(ROOT)),
        "issues": created_issues,
        "commit": sha,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="build the fixed-input weekly plan")
    mode.add_argument("--finalize", metavar="PLAN", help="write report/ledger/issues and stage/commit allowed files")
    ap.add_argument("--date", help="review date, YYYY-MM-DD (default: today)")
    ap.add_argument("--output", help="plan output path for --plan")
    ap.add_argument("--mode", choices=sorted(MODES), help="final report mode; inferred when omitted")
    ap.add_argument("--validation", action="append", default=[],
                    help="validation command/result line for finalize; repeatable")
    ap.add_argument("--auto-apply-candidate", action="append", default=[],
                    help="JSON/JSONL evidence-backed auto-apply candidate to merge during finalize")
    ap.add_argument("--no-commit", action="store_true", help="write report/ledger/issues only; do not stage or commit")
    a = ap.parse_args()

    as_of = dt.date.fromisoformat(a.date) if a.date else _today()
    if a.plan:
        build_plan(as_of=as_of, output=Path(a.output) if a.output else None)
        return 0
    result = finalize_plan(plan_path=Path(a.finalize), mode=a.mode,
                           auto_apply_candidate_paths=[Path(p) for p in a.auto_apply_candidate],
                           validation=a.validation, allow_commit=not a.no_commit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
