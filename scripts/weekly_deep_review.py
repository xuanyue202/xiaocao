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
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import flywheel  # noqa: E402
from xiaocao.research import protocols  # noqa: E402
from xiaocao.kol import trading_decision  # noqa: E402
from xiaocao.kol.publication import canonical_sha256  # noqa: E402
from xiaocao.live import kol_policy  # noqa: E402

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

# Fixed observation inputs, NOT new AUTO_APPLIED authority. Keep the existing
# promotion-source list and human/research/dirty-file gates unchanged.
KOL_REVIEW_INPUTS = {
    "decisions": "output/live/kol_policy/decisions/*.json",
    "context": "output/live/kol_policy/context/*.context.json",
    "requests": "output/live/kol_policy/requests/*.json",
    "source_verifications": "output/live/kol_policy/source_verifications/*.json",
    "paper_risk": "output/live/kol_policy/account_risk/risk_receipts/*.json",
    "live_risk": "output/live/kol_policy/account_risk/live_B.jsonl",
    "paper_consumption": "output/live/paper_decision_support/consumption/*.json",
    "paper_consumption_log": "output/live/paper_decision_support/consumption.jsonl",
    "live_consumption_log": "output/live/book_b_live_execution/consumption.jsonl",
    "live_morning": "output/live/book_b_live_execution/runs/*.json",
    "live_decisions": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
    "prior_reviews": "output/live/flywheel_change_ledger.jsonl",
}
_KOL_CHINA = ZoneInfo("Asia/Shanghai")
_KOL_SLOT_FIELDS = ("id", "experiment_id", "origin_review_date", "status", "objective", "falsifier",
                    "required_evidence", "owner", "rollback", "next_review", "follow_up")


def _kol_time(value: Any) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("aware evidence time required")
    return parsed


def _kol_hash_bound(row: dict, key: str, *, rfc8785: bool = False) -> None:
    unsigned = {k: v for k, v in row.items() if k != key}
    digest = canonical_sha256(unsigned) if rfc8785 else kol_policy.decision_sha256(unsigned)
    if row.get(key) != digest:
        raise ValueError("evidence hash mismatch")


def _kol_rows(data: bytes, *, jsonl: bool) -> list[dict]:
    # Use the same strict parser as the consumer audit, including duplicate
    # keys and non-finite numbers. Never silently drop a damaged ledger row.
    rows = [json.loads(line, object_pairs_hook=trading_decision._unique)
            for line in (data.splitlines() if jsonl else [data]) if line.strip()]
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("object required")
        canonical_sha256(row)
    return rows


def _kol_consumption_digest(files: dict[str, str], runtime: str) -> str:
    """Bind the inventory to audit_feedback's actual ordered file inventory."""
    base = "output/live/" + ("paper_decision_support" if runtime == "paper" else "book_b_live_execution")
    relative = {path.removeprefix(base + "/"): digest for path, digest in files.items() if path.startswith(base + "/")}
    paths = ["consumption.jsonl"] if "consumption.jsonl" in relative else []
    if runtime == "live":
        paths += sorted(p for p in relative if p.startswith("runs/"))
        if "book_b_live_decisions.jsonl" in relative:
            paths.append("book_b_live_decisions.jsonl")
    else:
        for path in sorted(p for p in relative if p.startswith("consumption/") and not p.endswith(".result.json")):
            paths.append(path)
            terminal = path.removesuffix(".json") + ".result.json"
            if terminal in relative:
                paths.append(terminal)
    return canonical_sha256([{"path": path, "sha256": relative[path]} for path in paths])


def _kol_item(kind: str, row: dict, reference: dict) -> dict:
    item = {"kind": kind, "evidence": reference}
    if kind == "prior_reviews":
        state = row["kol_review_state"]
        _kol_hash_bound(state, "state_sha256", rfc8785=True)
        if state.get("schema_version") != 1 or state.get("date") != row["date"]:
            raise ValueError("weekly review date/schema mismatch")
        slots = state["experiment_slots"]
        if not isinstance(slots, list) or len(slots) > 3 or any(not isinstance(s, dict) for s in slots):
            raise ValueError("weekly review slots invalid")
        day = dt.date.fromisoformat(row["date"])
        item.update(observed_date=day.isoformat(), state_sha256=state["state_sha256"],
                    experiment_slots=slots, analysis=state.get("analysis", {}), authority="review_only")
    elif kind == "decisions":
        kol_policy._validate_record(row)
        decision, review = row["decision"], row["review"]
        item.update(book=decision["book"], runtime=decision["runtime"],
                    observed_at=row["receipt"]["published_at"], decision_id=decision["decision_id"],
                    decision_sha256=row["receipt"]["decision_sha256"],
                    source_refs=decision["source_refs"], agent_id=decision["agent_id"],
                    source_observation_latency_seconds=[(_kol_time(s["received_at"]) - _kol_time(s["source_published_at"])).total_seconds()
                                                        for s in decision["source_refs"]],
                    reviewer_agent_id=review["reviewer_agent_id"],
                    review_latency_seconds=(_kol_time(review["reviewed_at"]) - _kol_time(decision["as_of"])).total_seconds(),
                    publication_latency_seconds=(_kol_time(row["receipt"]["published_at"]) - _kol_time(review["reviewed_at"])).total_seconds())
    elif kind == "context":
        _kol_hash_bound(row, "context_sha256", rfc8785=True)
        if row.get("source") != "lianghui_published_registry" or not isinstance(row.get("coverage"), dict):
            raise ValueError("context schema missing")
        item.update(observed_at=row["as_of"], coverage=row["coverage"],
                    context_sha256=row["context_sha256"],
                    relation_types=dict(Counter(r.get("record", {}).get("payload", {}).get("relation_type", "unknown")
                                                for r in row.get("relations", []))),
                    report_count=len(row.get("report_index", [])),
                    unloaded_report_ids=row.get("unloaded_report_ids", []))
    elif kind in ("requests", "source_verifications"):
        _kol_hash_bound(row, "record_sha256", rfc8785=True)
        payload = row["payload"]
        item.update(observed_at=row["recorded_at"], book=payload.get("book"), runtime=payload.get("runtime"),
                    decision_id=payload.get("decision_id"), decision_sha256=payload.get("decision_sha256"),
                    context_sha256=payload.get("context_sha256", payload.get("context", {}).get("context_sha256")),
                    phase=payload.get("phase"))
    elif kind in ("paper_risk", "live_risk"):
        if kind == "paper_risk":
            _kol_hash_bound(row, "receipt_sha256")
            receipt = row
        else:
            _kol_hash_bound(row, "event_hash")
            receipt = row["receipt"]
        runtime = "paper" if kind == "paper_risk" else "live"
        if receipt.get("account_id") != f"{runtime}:B":
            raise ValueError("account identity mismatch")
        nav = receipt.get("nav")
        if nav is not None and (isinstance(nav, bool) or not isinstance(nav, (int, float))
                                or not math.isfinite(nav) or nav <= 0):
            raise ValueError("invalid NAV")
        nav_time = receipt.get("nav_observed_at")
        age = (_kol_time(receipt["asof"]) - _kol_time(nav_time)).total_seconds() if nav_time else None
        nav_usable = (nav is not None and receipt["status"] in ("NORMAL", "REDUCED", "PAUSED")
                      and age is not None and 0 <= age <= 300
                      and _kol_time(nav_time).astimezone(_KOL_CHINA).date()
                      == _kol_time(receipt["asof"]).astimezone(_KOL_CHINA).date())
        item.update(book="B", runtime=runtime, observed_at=receipt["asof"], nav=nav,
                    nav_observed_at=nav_time, nav_evidence_usable=nav_usable,
                    risk_status=receipt["status"], history_basis=receipt.get("history_basis", "missing"),
                    evidence_digest=receipt["evidence_digest"])
    elif kind == "paper_consumption":
        _kol_hash_bound(row, "receipt_sha256")
        if row.get("book") != "B" or row.get("runtime") != "paper":
            raise ValueError("paper consumption scope mismatch")
        if row.get("schema_version") not in ("paper-policy-result.v1", "paper-policy-consumption.v1"):
            raise ValueError("paper consumption schema missing")
        terminal = row.get("schema_version") == "paper-policy-result.v1"
        if terminal:
            # Terminal is meaningful only when bound to its exact durable claim.
            result_path = Path(reference["absolute_path"])
            claim_path = result_path.with_name(result_path.name.removesuffix(".result.json") + ".json")
            claim = trading_decision.read_json(claim_path)
            _kol_hash_bound(claim, "receipt_sha256")
            if row.get("consumption_sha256") != claim["receipt_sha256"]:
                raise ValueError("paper terminal binding mismatch")
        else:
            claim = row
        observed = claim["kol_decision"]["evaluated_at"]
        item.update(book="B", runtime="paper", observed_at=observed,
                    timestamp_basis="policy_evaluated_at; terminal clock not recorded",
                    decision_id=claim["kol_decision"].get("decision_id"),
                    decision_sha256=claim["kol_decision"].get("decision_sha256"),
                    policy_status=claim["kol_decision"]["status"], terminal=terminal,
                    execution_status=row["status"], slots=[] if terminal else claim["slots"],
                    buy_count=row.get("buy_count") if terminal else None,
                    execution_verification="paper_receipt_only_not_broker")
    elif kind.endswith("consumption_log"):
        if row.get("runtime") != kind.split("_")[0] or row.get("book") not in ("B", "T", "KOL-US"):
            raise ValueError("consumption scope mismatch")
        item.update(book=row["book"], runtime=row["runtime"], observed_at=row["consumed_at"],
                    decision_id=row["decision_id"], decision_sha256=row.get("decision_sha256"),
                    execution_status=row.get("execution_status"),
                    adjustment=row.get("adjustment", {}), execution_verification="not_performed")
    elif kind == "live_decisions":
        _kol_hash_bound(row, "event_hash")
        if row.get("environment") != "live" or "kol_decision_id" not in row:
            raise ValueError("legacy or unscoped live decision")
        item.update(book="B", runtime="live", observed_at=row["recorded_at"],
                    decision_id=row["kol_decision_id"], decision_sha256=row.get("kol_decision_sha256"),
                    execution_status=row.get("action"), execution_verification="not_performed")
    else:
        # Native run receipts are inventory evidence, not broker-fill proofs.
        day = dt.date.fromisoformat(row["trade_date"])
        item.update(book="B", runtime="live", observed_date=day.isoformat(),
                    execution_verification="not_performed", execution_status=row.get("status"),
                    timestamp_basis="run_trade_date_not_consumption_clock",
                    policy_consumptions=row.get("policy_consumptions"))
    if "observed_at" in item:
        item["observed_date"] = _kol_time(item["observed_at"]).astimezone(_KOL_CHINA).date().isoformat()
    item["evidence"].pop("absolute_path", None)
    return item


def build_kol_evidence_inventory(root: Path, *, as_of: dt.date) -> dict:
    """Read fixed KOL evidence and existing audit_feedback, without any writer.

    Availability is evidence availability, not investment efficacy or complete
    account history. Audit totals cover all current files, never a week count.
    Each dated item below is independently assigned to the requested windows.
    """
    root = Path(root)
    try:
        feedback = trading_decision.audit_feedback(root, clock=lambda: dt.datetime.combine(as_of, dt.time.max, _KOL_CHINA))
    except (OSError, ValueError, TypeError):
        feedback = {"status": "missing", "reason": "audit_evidence_invalid",
                    "execution_verification": "not_performed", "profit_attribution": "not_established"}
    sources, items, observed_files = {}, [], {}
    for kind, pattern in KOL_REVIEW_INPUTS.items():
        references, errors, record_count = [], [], 0
        paths = sorted(root.glob(pattern))
        for path in paths:
            reference = {"path": path.relative_to(root).as_posix(), "absolute_path": str(path)}
            try:
                data = trading_decision._bytes(path)
                reference["sha256"] = hashlib.sha256(data).hexdigest()
                observed_files[reference["path"]] = reference["sha256"]
                rows = _kol_rows(data, jsonl=path.suffix == ".jsonl")
                if kind in ("paper_consumption", "paper_consumption_log", "live_consumption_log", "live_morning", "live_decisions"):
                    if feedback.get("status") != "audited":
                        raise ValueError("consumption audit failed")
                chain_head = None
                file_items = []
                for row in rows:
                    if kind == "prior_reviews" and "kol_review_state" not in row:
                        continue  # Legacy weekly ledger rows do not prove experiment completion.
                    if kind in ("live_risk", "live_decisions"):
                        if row.get("previous_hash") != chain_head:
                            raise ValueError("risk history chain invalid")
                        chain_head = row.get("event_hash")
                    if kind == "live_decisions" and "kol_decision_id" not in row:
                        _kol_hash_bound(row, "event_hash")
                        continue
                    file_items.append(_kol_item(kind, row, dict(reference)))
                # Reject a damaged file as a whole, never expose its valid prefix.
                items.extend(file_items)
                record_count += len(file_items)
                references.append({k: v for k, v in reference.items() if k != "absolute_path"})
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                errors.append({"path": reference["path"], "reason": "missing_or_invalid_evidence"})
        sources[kind] = {"pattern": pattern, "status": "available" if record_count else "missing",
                         "record_count": record_count or None, "files": references, "invalid_files": errors}
    snapshot_binding = {}
    for runtime in ("live", "paper"):
        matched = (feedback.get("status") == "audited"
                   and feedback.get("consumption", {}).get(runtime, {}).get("evidence_sha256")
                   == _kol_consumption_digest(observed_files, runtime))
        snapshot_binding[runtime] = "matched" if matched else "missing_or_changed"
        if not matched:
            kinds = {"paper_consumption", "paper_consumption_log"} if runtime == "paper" else {
                "live_consumption_log", "live_morning", "live_decisions"}
            items = [item for item in items if item["kind"] not in kinds]
            for kind in kinds:
                sources[kind].update(status="missing", record_count=None, reason="audit_snapshot_unbound")
    end = as_of.isoformat()
    start = (as_of - dt.timedelta(weeks=12) + dt.timedelta(days=1)).isoformat()
    selected = [item for item in items if (item["observed_date"] < end if item["kind"] == "prior_reviews"
                                           else start <= item["observed_date"] <= end)]
    return {"schema_version": 1, "authority": "review_only", "as_of": end,
            "fixed_inputs": dict(KOL_REVIEW_INPUTS), "sources": sources, "items": selected,
            "audit_feedback": feedback, "audit_feedback_scope": "all_available_records_not_window_totals",
            "audit_feedback_snapshot_binding": snapshot_binding,
            "excluded_outside_window_count": len(items) - len(selected),
            "status": "available" if selected else "missing"}


def _kol_evidence_cell(rows: list[dict], *, missing: list[str], **observations) -> dict:
    return {"status": "available" if rows else "missing", "record_count": len(rows) if rows else None,
            "available": [row["evidence"] for row in rows], "missing": missing, **observations}


def _kol_prior_experiments(inventory: dict, *, as_of: dt.date) -> dict:
    """Retain unresolved experiments even beyond 12 weeks; no launch/closure inference."""
    latest = {}
    prior = sorted((r for r in inventory["items"] if r["kind"] == "prior_reviews"), key=lambda r: r["observed_date"])
    for row in prior:
        for slot in row["experiment_slots"]:
            identifier = slot.get("experiment_id") or f"weekly-{row['observed_date']}-{slot.get('id', 'missing')}"
            experiment = {key: slot[key] for key in _KOL_SLOT_FIELDS if key in slot}
            experiment.update(experiment_id=identifier,
                              origin_review_date=slot.get("origin_review_date", row["observed_date"]))
            follow_up = experiment.get("follow_up") or {}
            refs = follow_up.get("evidence_refs") if isinstance(follow_up, dict) else None
            complete_refs = (isinstance(refs, list) and bool(refs) and all(
                isinstance(ref, dict) and isinstance(ref.get("path"), str) and bool(ref["path"].strip())
                and isinstance(ref.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])
                for ref in refs))
            # These are reported findings, not verification of a run, profit or promotion.
            reported_closed = (isinstance(follow_up, dict) and follow_up.get("status") == "reviewed"
                               and follow_up.get("disposition") in ("completed", "retired", "rolled_back")
                               and not _is_nullish(follow_up.get("conclusion"))
                               and complete_refs)
            latest[identifier] = {"experiment": experiment, "source": row["evidence"],
                                  "source_review_date": row["observed_date"], "state_sha256": row["state_sha256"],
                                  "reported_closed": bool(reported_closed), "outcome_verification": "not_performed",
                                  "current_review_status": "pending_review",
                                  "missing_fields": [key for key in ("rollback", "next_review", "owner") if _is_nullish(slot.get(key))]}
    items = sorted(latest.values(), key=lambda r: (r["experiment"].get("next_review") or "", r["experiment"]["experiment_id"]))
    for row in items:
        try:
            row["next_review_due"] = dt.date.fromisoformat(row["experiment"]["next_review"]) <= as_of
        except (KeyError, TypeError, ValueError):
            row["next_review_due"] = None
    return {"status": "available" if items else "missing", "items": items,
            "history_scope": "all dated prior finalized reviews; unresolved work is not dropped after 12 weeks",
            "authority": "review_only", "automatic_launch": False,
            "missing": ["逐项复核上期试验的实际运行/反证/失败/回滚证据；未记录不等于完成。"]}


def _kol_review_state(plan: dict) -> dict | None:
    """Compact durable projection; never embed previous inventories recursively."""
    review = plan.get("kol_system_review")
    if not review:
        return None  # Original plans and their promotion gates remain compatible.
    slots = review.get("experiment_slots")
    if not isinstance(slots, list) or len(slots) > 3:
        raise SystemExit("KOL weekly review requires at most three experiment_slots")
    for slot in slots:
        if not isinstance(slot, dict) or any(_is_nullish(slot.get(key)) for key in (
                "id", "objective", "falsifier", "required_evidence", "owner", "rollback", "next_review")):
            raise SystemExit("KOL weekly experiment requires objective/falsifier/evidence/owner/rollback/next_review")
    identifiers = [slot.get("experiment_id") or slot["id"] for slot in slots]
    if len(set(identifiers)) != len(identifiers):
        raise SystemExit("KOL weekly experiment identities must be unique")
    state = {"schema_version": 1, "date": plan["date"], "authority": "review_only", "automatic_launch": False,
             "experiment_slots": [{key: slot[key] for key in _KOL_SLOT_FIELDS if key in slot} for slot in slots],
             "analysis": review.get("analysis", {})}
    return {**state, "state_sha256": canonical_sha256(state)}


def _kol_execution_chain(items: list[dict], decisions: list[dict]) -> dict:
    links = []
    for decision in decisions:
        identifier, digest = decision["decision_id"], decision["decision_sha256"]
        proofs = [r for r in items if r["kind"] == "source_verifications"
                  and r.get("decision_id") == identifier and r.get("decision_sha256") == digest]
        contexts = [r for r in items if r["kind"] == "context"
                    and any(r["context_sha256"] == p["context_sha256"] for p in proofs)]
        runtimes = ("live", "paper") if decision["runtime"] == "both" else (decision["runtime"],)
        for runtime in runtimes:
            scoped = [r for r in items if r.get("book") == decision["book"] and r.get("runtime") == runtime]
            consumes = [r for r in scoped if r["kind"] not in ("decisions", "requests", "source_verifications")
                        and ((r.get("decision_id") == identifier and r.get("decision_sha256") == digest)
                             or any(c.get("decision_id") == identifier and c.get("decision_sha256") == digest
                                    for c in (r.get("policy_consumptions") or [])))]
            requests = [r for r in scoped if r["kind"] == "requests"
                        and any(r.get("context_sha256") == p["context_sha256"] for p in proofs)]
            missing_clocks = any(r["kind"] == "live_morning" and any(
                c.get("decision_id") == identifier and not c.get("consumed_at")
                for c in (r.get("policy_consumptions") or [])) for r in consumes)
            links.append({"account_id": f"{runtime}:{decision['book']}", "decision_id": identifier,
                          "decision_sha256": digest, "decision": decision["evidence"],
                          "source_verifications": [r["evidence"] for r in proofs],
                          "context": [r["evidence"] for r in contexts],
                          "same_context_requests_not_proven_model_runs": [r["evidence"] for r in requests],
                          "consumption": [r["evidence"] for r in consumes],
                          "missing": ([] if proofs else ["来源复核绑定"]) + ([] if contexts else ["对应 context"])
                                     + ([] if consumes else ["本 runtime 的 hash-bound 消费"])
                                     + (["精确消费时钟；run.trade_date 仅供日期分组"] if missing_clocks else [])
                                     + ["成交/费用对账及模型请求的精确关联"],
                          "execution_verification": "not_performed", "profit_attribution": "not_established"})
    return {"status": "available" if links else "missing", "links": links,
            "missing": ["没有完整链时，不把发布、消费或状态声明当作真实成交。"]}


def build_kol_system_review(root: Path, *, as_of: dt.date) -> dict:
    """Build the read-only Astra weekly framework-review context for the plan."""
    inventory = build_kol_evidence_inventory(root, as_of=as_of)
    windows = {}
    for weeks in (1, 4, 12):
        start = (as_of - dt.timedelta(weeks=weeks) + dt.timedelta(days=1)).isoformat()
        rows = [r for r in inventory["items"] if start <= r["observed_date"] <= as_of.isoformat()]
        accounts_review = {}
        scopes = {("B", "live"), ("B", "paper")} | {
            (r["book"], r["runtime"]) for r in rows if r.get("book") and r.get("runtime") in ("paper", "live")}
        for book, runtime in sorted(scopes):
            scoped = [r for r in rows if r.get("book") == book and r.get("runtime") == runtime]
            nav_rows = [r for r in scoped if r["kind"] in ("paper_risk", "live_risk") and r["nav_evidence_usable"]]
            consume = [r for r in scoped if r["kind"] in ("paper_consumption", "paper_consumption_log",
                                                           "live_consumption_log", "live_decisions")
                       or (r["kind"] == "live_morning" and r.get("policy_consumptions"))]
            slots = [r for r in consume if r.get("slots")]
            nav_rows.sort(key=lambda r: _kol_time(r["observed_at"]))
            accounts_review[f"{runtime}:{book}"] = {
                "account_performance": _kol_evidence_cell(nav_rows,
                    missing=["窗口首尾同口径净值、完整结算覆盖与资金流核验；启用后观测不等于历史净值曲线"],
                    observed_nav=[{"as_of": r["observed_at"], "nav_observed_at": r["nav_observed_at"],
                                   "nav": r["nav"], "history_basis": r["history_basis"], "risk_status": r["risk_status"]}
                                  for r in nav_rows], window_return_pct=None, profit_attribution="not_established"),
                "execution_loss": _kol_evidence_cell(consume,
                    missing=["同计划委托/成交/费用与时效对账，才可量化执行漏损；消费或状态声明不是成交证明"],
                    reported_status_counts=dict(Counter(str(r.get("execution_status") or "not_recorded") for r in consume)),
                    count_semantics="artifact records, not trades; paper claim and terminal counted separately",
                    loss_amount=None),
                "missed_opportunities": _kol_evidence_cell(slots,
                    missing=["同一冻结候选的 no-KOL/current/challenger 可成交反事实与退出费后路径；留现金不等于错失收益"],
                    opportunity_pnl=None),
            }
        contexts = [r for r in rows if r["kind"] == "context"]
        decisions = [r for r in rows if r["kind"] == "decisions"]
        consumed_ids = {r.get("decision_id") for r in rows if r["kind"] != "decisions"}
        consumed_ids.update(c.get("decision_id") for r in rows for c in (r.get("policy_consumptions") or []))
        chain_decisions = [r for r in inventory["items"] if r["kind"] == "decisions"
                           and (r in decisions or r["decision_id"] in consumed_ids)]
        windows[f"{weeks}w"] = {"start": start, "end": as_of.isoformat(), "accounts": accounts_review,
            "decision_execution_chain": _kol_execution_chain(inventory["items"], chain_decisions),
            "source_coverage": _kol_evidence_cell(contexts,
                missing=["未登记来源的远端完整发现，registered coverage 不能代表全部 KOL"],
                snapshots=[{"as_of": r["observed_at"], "coverage": r["coverage"],
                            "relation_types": r["relation_types"], "unloaded_report_ids": r["unloaded_report_ids"]}
                           for r in contexts]),
            "decision_review_latency": _kol_evidence_cell(decisions,
                missing=["模型请求/开始/完成遥测及未完成请求；不能将 decision.as_of 到 reviewed_at 全算模型耗时"],
                observations=[{k: r[k] for k in ("decision_id", "book", "runtime", "agent_id", "reviewer_agent_id",
                                                "source_observation_latency_seconds", "review_latency_seconds",
                                                "publication_latency_seconds")} for r in decisions]),
        }
    explanations = [
        {"id": "baseline_no_kol", "hypothesis": "账户表现主要由原 ★E 资格、模式与市场环境解释，KOL 增量可能只是少用资金。",
         "falsifier": "同一冻结样本、同等风险预算及费用后，原基线无法解释有界 KOL 的跨窗口尾部改善。",
         "required_evidence": ["无 KOL 的冻结整手基线", "同风险暴露比较", "模式/环境分层及选择偏差"]},
        {"id": "current_bounded", "hypothesis": "现行有界 KOL 减少尾部损失，但可能增加等待、过期和错失机会成本。",
         "falsifier": "可成交反事实的错失收益和执行漏损抵消尾部收益，或改善仅由单一赢家/来源/周解释。",
         "required_evidence": ["实际消费到执行链", "费用和未执行样本", "同窗口尾部与闲置现金对比"]},
        {"id": "kol_challenger", "hypothesis": "局部最优可能源于上游入口过滤或模式集合；只在已入选票上缩量无法解决框架与资本利用率问题。",
         "falsifier": "隔离挑战者在同本金、同费用、同合法成交约束和 OOS 中，不能改善机会覆盖及风险调整表现。",
         "required_evidence": ["被原入口/模式排除的 authority=0 研究队列", "no-KOL/current/challenger 配对回放", "资金利用率与尾部约束"]},
    ]
    next_review = (as_of + dt.timedelta(days=7)).isoformat()
    slots = [{"id": row["id"], "status": "needs_evidence_and_design", "objective": row["hypothesis"],
              "experiment_id": f"weekly-{as_of.isoformat()}-{row['id']}", "origin_review_date": as_of.isoformat(),
              "falsifier": row["falsifier"], "required_evidence": row["required_evidence"],
              "rollback": "未启动则保留现行基线；若另经研究门批准，仅撤销该隔离试验的明确变更并保留失败/回滚证据，不改正式账户、安全或原 kill-switch。启动前补齐精确版本/参数恢复点。",
              "follow_up": {"status": "pending", "disposition": None, "conclusion": None, "evidence_refs": []},
              "owner": "weekly Astra analysis + independent main-agent review", "next_review": next_review,
              "authority": "proposal_or_existing_research_gate", "auto_apply_eligible": False}
             for row in explanations]
    prior_follow_up = _kol_prior_experiments(inventory, as_of=as_of)
    unresolved = [row for row in prior_follow_up["items"] if not row["reported_closed"]]
    if unresolved:
        # Carry identity and original due date; do not silently restart, close,
        # reschedule or invent rollback for legacy experiments missing it.
        slots = [{**row["experiment"], "prior_review_evidence": row["source"], "follow_up_required": True,
                  "authority": "proposal_or_existing_research_gate", "auto_apply_eligible": False}
                 for row in unresolved[:3]]
    prior_follow_up["unresolved_outside_slots_count"] = max(0, len(unresolved) - 3)
    missing = ["1/4/12 周完整账户表现与可成交配对反事实", "原入口过滤、模式和资金利用率的竞争解释",
               "新旧观点冲突、遗漏来源及模型/审阅迟延的归因"]
    if any(value != "matched" for value in inventory["audit_feedback_snapshot_binding"].values()):
        missing.append("消费审计与本次固定输入未能完整绑定，需重取一致证据后复核")
    if any(source["invalid_files"] for source in inventory["sources"].values()):
        missing.append("存在损坏或不完整输入，路径见 inventory.sources.invalid_files")
    return {"schema_version": 1, "status": "pending_analysis" if inventory["status"] == "available" else "missing_evidence",
            "authority": "review_only", "inventory": inventory, "windows": windows,
            "window_semantics": "trailing 7/28/84 calendar days inclusive; overlapping, not independent samples",
            "competing_explanations": explanations, "experiment_slots": slots,
            "prior_experiment_follow_up": prior_follow_up,
            "analysis_context": {"model": "gpt-6-astra", "reasoning_effort": "xhigh",
                "objective": "从整体账户目标审视本周与4/12周表现，挑战当前框架、入口过滤、模式与资本利用率，避免逐条新闻局部优化。",
                "instructions": ["用固定输入 hash 引用区分事实、缺口和竞争解释，不能只复述新闻。",
                    "逐本逐 runtime 对照三个解释；新旧冲突须读已发布观点/评估/关系，不按关键词生成结论。",
                    "最多三个可证伪试验槽位；缺数据先提取证要求，不生成合格变更候选。",
                    "先复核 prior_experiment_follow_up 的旧试验、失败和回滚，再选择最多三个槽位；每槽保留 experiment_id、rollback、owner、next_review。不得自动启动。",
                    "跟进写入每槽 follow_up：status=reviewed、disposition=continue/refine/completed/retired/rolled_back、conclusion、evidence_refs=[{path,sha256}]；空结果不算闭环。finalize 将槽位和跟进保存到固定 weekly ledger，下周读取。",
                    "分析写入 analysis：status=completed、非空 framework_conclusion、evidence_refs=[{path,sha256}] 和 missing_evidence；引用必须来自 inventory.items。",
                    "小样本不得声称因果胜率或稳定收益；实盘策略/安全/永久参数维持提案或既有研究门。"],
                "inventory_sha256": canonical_sha256(inventory)},
            "analysis": {"status": "pending", "framework_conclusion": None,
                         "evidence_refs": [], "missing_evidence": missing},
            "limitations": ["available 仅表示可读证据，不证明完整窗口或盈利归因。",
                            "工程测试、消费次数、非配对累计 A/B 差不是收益证据；小样本不建立因果或稳定收益。"],
            "promotion": {"auto_apply_candidate": False, "live_auto_promotion": False,
                          "existing_human_dirty_research_gates": "unchanged"}}


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


def _instrumentation_candidate_id(row: dict[str, Any], todo: str) -> str:
    """Build a readable identity without collapsing non-ASCII TODOs."""
    date_s = str(row.get("date") or "unknown-date")
    file_s = str(row.get("file") or "unknown-source")
    source_slug = _slug(Path(file_s).stem)[:40]
    todo_slug = _slug(todo)[:24]
    digest = hashlib.sha256(f"{file_s}\0{todo}".encode("utf-8")).hexdigest()[:12]
    return f"instrumentation-{date_s}-{source_slug}-{todo_slug}-{digest}"


def _duplicate_plan_ids(*groups: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for rows in groups:
        for row in rows:
            identity = str(row.get("id") or "").strip()
            if not identity:
                continue
            if identity in seen:
                duplicates.add(identity)
            seen.add(identity)
    return sorted(duplicates)


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
        pid = _instrumentation_candidate_id(row, str(todo))
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

    duplicate_ids = _duplicate_plan_ids(proposals, auto_apply_candidates)
    if duplicate_ids:
        raise RuntimeError(
            "weekly plan candidate ids must be unique: "
            + ", ".join(duplicate_ids)
        )

    plan = {
        "date": as_of.isoformat(),
        "week_start": (as_of - dt.timedelta(days=6)).isoformat(),
        "week_end": as_of.isoformat(),
        "fixed_inputs": FIXED_INPUTS,
        "fixed_review_inputs": dict(KOL_REVIEW_INPUTS),
        "kol_system_review": build_kol_system_review(ROOT, as_of=as_of),
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


def _render_kol_system_review(plan: dict) -> list[str]:
    review = plan.get("kol_system_review")
    if not isinstance(review, dict) or not review:
        return ["- 整体框架复盘：缺少 KOL 系统复盘上下文，未完成高视角分析。"]
    analysis = review.get("analysis") or {}
    inventory = review.get("inventory") or {}
    known_refs = {(r["evidence"]["path"], r["evidence"]["sha256"]) for r in inventory.get("items", [])}
    refs = analysis.get("evidence_refs") or []
    conclusion = analysis.get("framework_conclusion")
    complete = (analysis.get("status") == "completed" and isinstance(conclusion, str)
                and not _is_nullish(conclusion) and bool(refs)
                and all(isinstance(r, dict) and (r.get("path"), r.get("sha256")) in known_refs for r in refs))
    if complete:
        lines = [f"- 整体框架复盘（有证据引用的分析，非收益认证）：{conclusion.strip()}"]
        lines.append("- 结论证据：" + "；".join(f"`{r['path']}`（sha256={r['sha256']}）" for r in refs))
    else:
        state = "已收集部分固定证据，待 Astra 整体分析" if inventory.get("status") == "available" else "关键证据缺失，未完成分析"
        lines = [f"- 整体框架复盘：{state}；不以空结论或消费次数认定有效。"]
    missing = analysis.get("missing_evidence") or []
    missing = [value.strip() for value in missing if isinstance(value, str) and not _is_nullish(value)]
    lines.append("- 待核证据：" + ("；".join(missing) if missing else "尚未明确证据缺口，需补充核验，不能视为无缺口。"))
    lines.append("- 比较框架：无 KOL 基线 / 现行有界 KOL / 挑战者；分别检查入口过滤、模式和资金利用率。")
    lines.append("- 纸实逐账户分开；1/4/12 周重叠窗口不是独立样本。小样本不宣称因果胜率或稳定收益，不自动推广实盘。")
    prior = review.get("prior_experiment_follow_up", {})
    if prior.get("items"):
        lines.append(f"- 旧试验跟进：{len(prior['items'])} 项需先复核（历史状态仅为报告声明），再决定本周最多三个槽位；不自动启动。")
    return lines


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
        "",
        f"- 本周模式：{human_mode}（`{mode}`）。",
        f"- 自动改策略代码：{'有，见下方「已自动落地」' if mode == MODE_AUTO else '没有。没有完整证据链时只产出提案/审计，不想当然改策略。'}",
        f"- 需要你确认的事项：{decision_count} 个{reminder}，见下一节。",
    ]
    lines.extend(_render_kol_system_review(plan))
    lines += [
        "",
        "## 需要你看/确认的事项",
        "",
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
    review = plan.get("kol_system_review") or {}
    prior = review.get("prior_experiment_follow_up", {})
    if prior:
        lines += ["", "## 上期试验与失败跟进（先于新增试验，未记录不等于完成）", ""]
        for item in prior.get("items", []):
            old = item["experiment"]
            follow_up = old.get("follow_up") or {}
            if not isinstance(follow_up, dict):
                follow_up = {}
            lines += [f"- `{old['experiment_id']}`：{old.get('objective') or '目标待补'}",
                      f"  - 历史状态：{old.get('status') or '未记录'}；本周待复核；原复核日：{old.get('next_review') or '缺失'}。",
                      f"  - 跟进结论（报告声明）：{follow_up.get('conclusion') or '未记录，不能认定已完成'}",
                      f"  - 回滚：{old.get('rollback') or '缺失，需补齐后才能关闭或进入新试验'}",
                      f"  - 固定来源：`{item['source']['path']}`；复盘日期 {item['source_review_date']}；state sha256={item['state_sha256']}。"]
        if not prior.get("items"):
            lines.append("- 缺少可读的上期结构化试验记录；不能据此宣称全部完成。")
    if review.get("experiment_slots"):
        lines += ["", "## 整体框架试验槽位（待取证与设计，不是合格变更候选）", ""]
        for slot in review["experiment_slots"][:3]:
            follow_up = slot.get("follow_up") or {}
            if not isinstance(follow_up, dict):
                follow_up = {}
            lines += [f"- 目标：{slot['objective']}", f"  - 证伪条件：{slot['falsifier']}",
                      f"  - 必要证据：{'；'.join(slot['required_evidence'])}",
                      f"  - 回滚：{slot.get('rollback') or '缺失，需补齐'}",
                      f"  - 本次跟进（报告声明）：{follow_up.get('conclusion') or '待复核，尚无完成证明'}",
                      f"  - 负责人：{slot['owner']}；下次复核：{slot['next_review']}。"]
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
        f"- KOL 固定复盘输入（仅观察，不增加自动落地权限）：{', '.join(plan.get('fixed_review_inputs', {}).values()) or 'missing'}",
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
            "kol_system_review_status": review.get("status", "missing"),
            "kol_inventory_sha256": review.get("analysis_context", {}).get("inventory_sha256"),
            "kol_audit_feedback": review.get("inventory", {}).get("audit_feedback", {}),
            "kol_audit_snapshot_binding": review.get("inventory", {}).get("audit_feedback_snapshot_binding", {}),
            "kol_experiment_slots": review.get("experiment_slots", []),
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
    kol_state = _kol_review_state(plan)
    if kol_state is not None:
        rec["kol_review_state"] = kol_state
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
    _kol_review_state(plan)  # Validate rollback/slot limit before any report or ledger writes.
    extra_candidates = _load_auto_apply_candidates(auto_apply_candidate_paths)
    if extra_candidates:
        plan.setdefault("auto_apply_candidates", []).extend(extra_candidates)
    duplicate_ids = _duplicate_plan_ids(
        plan.get("proposals", []),
        plan.get("auto_apply_candidates", []),
    )
    if duplicate_ids:
        raise SystemExit(
            "weekly plan candidate ids must be unique: "
            + ", ".join(duplicate_ids)
        )
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
