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

ACTION_LOG = ROOT / "reference" / "experience" / "distill_action_log.jsonl"
CHANGE_LEDGER = ROOT / "output" / "live" / "flywheel_change_ledger.jsonl"
WEEKLY_DIR = ROOT / "output" / "live"
SCRATCH_DIR = ROOT / ".scratch" / "weekly-deep-review"

MODE_AUTO = "AUTO_APPLIED"
MODE_PROPOSAL = "PROPOSAL_ONLY"
MODE_NONE = "NO_ACTION_REQUIRED"
MODES = {MODE_AUTO, MODE_PROPOSAL, MODE_NONE}

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
        or source == "kronos_screen/HYPOTHESES.jsonl"
    )


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
            title="PASS verdict pending strategy consumption",
            source="scripts/flywheel_selfcheck.py",
            reason=f"Strategy flywheel is blocked by pending PASS verdict(s): {', '.join(pending)}.",
            recommended_action="Confirm or implement the paper/simulation strategy mapping for the PASS evidence; do not leave it hidden in the ledger.",
            evidence=_evidence_bundle(
                problem=f"PASS pending with no actuator: {', '.join(pending)}",
                attribution="flywheel_selfcheck derives pending PASS from the verdict ledger; the gap is ② evidence not reaching ③ strategy updates.",
                artifact="kronos_screen/HYPOTHESES.jsonl + scripts/flywheel_selfcheck.py",
                baseline="Current behavior leaves PASS evidence visible but unapplied.",
                overfit="No automatic strategy change is inferred here; implementation still needs a concrete mapping and validation.",
                scope="paper/simulation strategy proposal",
            ),
        ))

    for row in action_rows:
        todo = row.get("instrumentation_todo")
        if _is_nullish(todo):
            continue
        pid = f"instrumentation-{row.get('date')}-{_slug(str(todo))}"
        proposals.append(_proposal(
            pid=pid,
            title=f"Instrumentation todo from {row.get('file')}",
            source="reference/experience/distill_action_log.jsonl",
            reason=str(todo),
            recommended_action="Create or implement the observability/tooling change after confirming it is still needed.",
            evidence=_evidence_bundle(
                problem=f"Distillation exposed instrumentation gap: {todo}",
                attribution="The gap was explicitly routed through action_summary.instrumentation_todo, not inferred ad hoc.",
                artifact=f"reference/experience/distilled/{row.get('file')}",
                baseline="Without the tool/schema/report field, future review cannot attribute the same observation cleanly.",
                overfit="Non-return tooling change; still requires explicit evidence and human confirmation unless it is in the fixed input plan.",
                scope="workflow/instrumentation proposal",
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
        "mode_recommendation": MODE_PROPOSAL if proposals else MODE_NONE,
        "rules": {
            "outside_fixed_inputs": "proposal_only_requires_user_confirmation",
            "auto_apply_requires": "complete evidence_bundle + fixed input source + validation + clean target files",
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
            "## Reason",
            p["reason"],
            "",
            "## Recommended Action",
            p["recommended_action"],
            "",
            "## Evidence Bundle",
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
    lines = [
        f"# Xiaocao Weekly Deep Review {plan['date']}",
        "",
        f"## Mode",
        mode,
        "",
        "## Human Attention",
    ]
    if plan.get("proposals"):
        for p in plan["proposals"]:
            lines.append(f"- NEEDS_CONFIRMATION `{p['id']}`: {p['title']}")
    if blocked_dirty:
        max_blocked = 20
        for p in blocked_dirty[:max_blocked]:
            lines.append(f"- BLOCKED_BY_DIRTY_FILE `{p}`")
        if len(blocked_dirty) > max_blocked:
            lines.append(f"- BLOCKED_BY_DIRTY_FILE ... and {len(blocked_dirty) - max_blocked} more pre-existing dirty allowed path(s)")
    pending = strategy.get("pending_pass_verdicts") or []
    if pending:
        lines.append(f"- PASS pending: {', '.join(pending)}")
    if not plan.get("proposals") and not blocked_dirty and not pending:
        lines.append("- none")
    lines += [
        "",
        "## Auto Applied Changes",
    ]
    if mode == MODE_AUTO:
        for c in plan.get("auto_apply_candidates", []):
            lines.append(f"- `{c.get('id')}` {c.get('title')}: {c.get('recommended_change')}")
        lines.append("")
        lines.append("Changed/staged files:")
        lines.extend([f"- {p}" for p in staged_files] or ["- none detected"])
    else:
        lines.append("- none")
    lines += [
        "",
        "## Evidence Summary",
        f"- fixed inputs: {', '.join(plan.get('fixed_inputs', []))}",
        f"- proposals: {len(plan.get('proposals', []))}",
        f"- auto_apply_candidates: {len(plan.get('auto_apply_candidates', []))}",
        "",
        "## Validation",
    ]
    lines.extend(f"- {v}" for v in _validation_lines(validation))
    lines += [
        "",
        "## Rollback",
        "- After commit: `git revert <commit>`",
        "",
        "## Flywheel Health",
        f"- spinning: {fw.get('spinning')}",
        f"- strategy: {strategy.get('status')} pending={strategy.get('pending_pass_verdicts')}",
        f"- knowledge: candidates {knowledge.get('candidates_total')} / tested {knowledge.get('candidates_tested')} / retired {knowledge.get('candidates_retired')} / oldest {knowledge.get('oldest_untested')}",
        "",
        "## Proposal Issues",
    ]
    lines.extend(f"- {p}" for p in created_issues) if created_issues else lines.append("- none")
    lines += [
        "",
        "## Details",
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
