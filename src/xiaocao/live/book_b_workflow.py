"""Shared morning strategy derivation and explanation, before account allocation.

The existing policy interpreter owns bounded KOL effects. This module records
what it did, including a neutral published policy versus an unfinished review.
It does not load sources, wait for a model, allocate cash or authorize an order.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import kol_policy


def eligible_buy_rows(rows: list[dict]) -> list[dict]:
    """Consume the original APP ★E predicate; account guards remain downstream."""
    return [
        row for row in rows
        if row.get("book") == "B" and row.get("is_live") is True
        and row.get("mode_exec_star") is True and row.get("mode_trade_eligible") is True
        and ("executable_fillable" not in row or row.get("executable_fillable") is True)
    ]


@dataclass(frozen=True)
class BookBAdjudication:
    rows: list[dict]
    receipt: dict


def _review_completion(policy: dict, judgment: dict, support: dict | None) -> dict:
    """A new policy timestamp alone cannot prove this request completed.

    Author and independent reviewer may bind morning_request_sha256 in their
    existing hash-bound annotations. Legacy policy remains consumable without
    that proof, but cannot claim completion of the current request.
    """
    result = {key: (support or {}).get(key) for key in (
        "status", "reason", "request_sha256", "receipt_sha256", "waited_seconds",
    )}
    result["outcome"] = "not_observed" if not support else "unproved"
    if not support:
        return result
    if support.get("status") in {"timed_out", "deferred", "blocked", "not_required"}:
        result["outcome"] = support["status"]
        return result
    if judgment["policy_status"] != "validated" or support.get("status") != "validated":
        return result
    if support.get("decision_sha256") != judgment["decision_sha256"]:
        result["outcome"] = "policy_changed_after_wait"
        return result
    result["outcome"] = "valid_policy_request_completion_unproved"
    try:
        body = {k: v for k, v in support.items() if k != "receipt_sha256"}
        if support.get("receipt_sha256") != kol_policy.decision_sha256(body):
            return result
        record = policy["record"]
        requested = datetime.fromisoformat(support["requested_at"])
        as_of = datetime.fromisoformat(record["decision"]["as_of"].replace("Z", "+00:00"))
        if as_of < requested:
            result["outcome"] = "reused_valid_policy"
        else:
            request_sha = support["request_sha256"]
            completed = datetime.fromisoformat(support["completed_at"])
            deadline = datetime.fromisoformat(support["entry_deadline"])
            budget = float(support["max_wait_seconds"])
            bound = (re.fullmatch(r"[0-9a-f]{64}", request_sha) is not None
                     and 0 <= budget <= 120 and requested <= as_of <= completed < deadline
                     and completed <= requested + timedelta(seconds=budget)
                     and support["receipt_sha256"] == kol_policy.decision_sha256(body)
                     and all(record[part].get("morning_request_sha256") == request_sha
                             for part in ("decision", "review")))
            if bound:
                result["outcome"] = ("completed_no_change" if judgment["outcome"] == "published_no_change"
                                     else "completed_changed")
    except (KeyError, TypeError, ValueError):
        pass
    return result


def _row_explanation(row: dict, selected: bool, policy: dict) -> dict:
    # Selection and execution restrictions are separate facts. A frozen flag is
    # not proof of fillability, and a valid policy can still cap it to zero.
    if row.get("book") != "B" or row.get("is_live") is not True:
        reason = "OUTSIDE_BOOK_B_LIVE_FREEZE"
    elif row.get("kol_mode_override") and selected:
        reason = "REVIEWED_XIAOCAO_MODE_FOLLOW"
    elif selected:
        reason = "BASELINE_STAR_E"
    elif row.get("mode_state") == "COLD":
        reason = "COLD_DEFAULT_GATE"
    elif row.get("mode_state") == "UNKNOWN":
        reason = "UNKNOWN_MODE_EVIDENCE"
    elif "executable_fillable" in row and row["executable_fillable"] is not True:
        reason = "EXPLICIT_UNFILLABLE"
    else:
        reason = "NOT_SELECTED_BY_BASELINE"
    restrictions = []
    if row.get("mode_state") not in {"ACTIVE", "PROVISIONAL"}:
        restrictions.append("MODE_NOT_ACTIVE_OR_PROVISIONAL")
    if str(row.get("code") or "").endswith(".BJSE"):
        restrictions.append("BJSE_EXCLUDED")
    if "executable_fillable" in row and row["executable_fillable"] is not True:
        restrictions.append("FILLABILITY_NOT_PROVEN")
    adjustment = kol_policy.buy_adjustment(policy, row.get("code"))
    return {
        "code": row.get("code"), "mode": row.get("mode"),
        "original_mode_state": row.get("kol_mode_original_state", row.get("mode_state")),
        "consumer_mode_state": row.get("mode_state"),
        "star_selected": selected, "selection_reason": reason,
        "execution_restrictions": restrictions,
        "kol_buy_scale": adjustment["scale"], "kol_skip": adjustment["skip"],
        "mode_follow": row.get("kol_mode_override"),
    }


def explain_selection_rows(rows: list[dict], policy: dict) -> list[dict]:
    selected = {id(row) for row in eligible_buy_rows(rows)}
    return [_row_explanation(row, id(row) in selected, policy) for row in rows]


def adjudicate_book_b(rows: list[dict], policy: dict, *, freeze: dict,
                      runtime: str, support_receipt: dict | None = None) -> BookBAdjudication:
    """Derive once from validated original bundle and fresh runtime policy.

    Account-specific permission filtering belongs to the APP morning caller.
    Paper and model accounts retain their registered candidate rules.
    """
    if runtime not in {"live", "paper"}:
        raise ValueError("BOOK_B_RUNTIME_REQUIRED")
    canonical = freeze.get("snapshot_sha256")
    if not isinstance(canonical, str) or re.fullmatch(r"[0-9a-f]{64}", canonical) is None:
        raise ValueError("BOOK_B_CANONICAL_FREEZE_REQUIRED")
    judgment = kol_policy.describe_judgment(policy)
    if judgment["book"] != "B" or judgment["runtime"] != runtime:
        raise ValueError("BOOK_B_POLICY_SCOPE_MISMATCH")
    derived = kol_policy.prioritize_xiaocao_modes(rows, policy)
    selected_ids = {id(row) for row in eligible_buy_rows(derived)}
    explanations = [_row_explanation(row, id(row) in selected_ids, policy) for row in derived]
    effects = {**judgment["effect"], "skip_codes": sorted(judgment["effect"]["skip_codes"]),
               "exit_codes": sorted(judgment["effect"]["exit_codes"])}
    binding = {key: freeze.get(key) for key in (
        "market_date", "strategy_run_id", "strategy_sha", "snapshot_sha256",
        "snapshot_raw_sha256", "snapshot_row_count", "checkpoint_sha256",
    )}
    semantics = {
        "schema_version": "book-b-strategy-semantics.v1", "freeze": binding, "effects": effects,
        "rows": [{k: v for k, v in row.items() if k != "mode_follow"} for row in explanations],
    }
    modes = {row.get("mode") for row in rows}
    receipt = {
        "schema_version": "book-b-adjudication.v1", "book": "B", "runtime": runtime,
        "freeze": binding, "freeze_sha256": canonical, "judgment": judgment,
        "support_attempt": _review_completion(policy, judgment, support_receipt),
        "strategy_semantics_sha256": kol_policy.decision_sha256(semantics),
        "baseline_codes": [row.get("code") for row in eligible_buy_rows(rows)],
        "strategy_codes": [row.get("code") for row in eligible_buy_rows(derived)],
        "mode_follow_bindings": [
            {**override, "frozen_mode_present": override["mode"] in modes,
             "mapping_basis": "independently_reviewed_exact_target_no_automatic_alias"}
            for override in effects["xiaocao_mode_overrides"]
        ],
        "rows": explanations,
        "input_coverage": ("complete_frozen_batch" if len(rows) == freeze.get("snapshot_row_count")
                           else "partial_frozen_batch"),
        "allocation_adapter": ("frozen_star_e" if runtime == "live"
                               else "ranked_eligible_reserve_pool_then_board_lots"),
        "authority": "explanation_only_account_and_execution_gates_required",
    }
    receipt["receipt_sha256"] = kol_policy.decision_sha256(receipt)
    return BookBAdjudication(derived, receipt)


def summarize_adjudication(value: object, *, runtime: str) -> dict:
    """Verify stored explanation bytes, not current trading permission."""
    try:
        if not isinstance(value, dict) or value.get("schema_version") != "book-b-adjudication.v1":
            raise ValueError("missing_receipt")
        if value.get("book") != "B" or value.get("runtime") != runtime:
            raise ValueError("scope_mismatch")
        body = {k: v for k, v in value.items() if k != "receipt_sha256"}
        if kol_policy.decision_sha256(body) != value.get("receipt_sha256"):
            raise ValueError("hash_mismatch")
        return {
            "status": "recorded", "freeze_sha256": value["freeze_sha256"],
            "checkpoint_sha256": value["freeze"]["checkpoint_sha256"],
            "input_coverage": value["input_coverage"],
            "strategy_semantics_sha256": value["strategy_semantics_sha256"],
            "policy_outcome": value["judgment"]["outcome"],
            "support_outcome": value["support_attempt"]["outcome"],
            "star_candidate_count": len(value["strategy_codes"]),
            "selection_reasons": dict(Counter(row["selection_reason"] for row in value["rows"])),
            "allocation_adapter": value["allocation_adapter"],
            "app_buy_permissions": value.get("app_buy_permissions", {"profile": "legacy_unrecorded"}),
        }
    except (ValueError, KeyError, TypeError):
        return {"status": "unproved"}


RULE_PROFILE = "app-b-e-staged-v1"


def final_plan_receipt(adjudication: dict, allocation: dict | None, orders: list[dict], *,
                       policy_evidence: dict | None = None, execution_model: str = "native_app") -> dict:
    """Bind the last deterministic decision to economic orders, before execution.

    Account facts and execution models may differ across consumers. Identical
    selection semantics alone never establish identical orders or returns.
    """
    runtime = adjudication.get("runtime")
    if summarize_adjudication(adjudication, runtime=runtime)["status"] != "recorded":
        raise ValueError("BOOK_B_FINAL_PLAN_ADJUDICATION_UNPROVEN")
    planned = {row["code"]: row for row in orders}
    if len(planned) != len(orders):
        raise ValueError("BOOK_B_FINAL_PLAN_DUPLICATE_CODE")
    decisions = []
    caps = (policy_evidence or {}).get("by_code", {})
    for row in adjudication["rows"]:
        code = row["code"]
        cap = caps.get(code, {})
        reason = ("PLANNED" if code in planned else
                  "POLICY_OR_RISK_ZERO" if cap.get("skip") else
                  "ALLOCATION_OR_ACCOUNT_GUARD" if row["star_selected"] else row["selection_reason"])
        decisions.append({**row, "final_reason": reason,
                          "allocation_cap": cap, "order": planned.get(code)})
    result = {"schema_version": "book-b-final-plan.v1", "rule_profile": RULE_PROFILE,
              "freeze": adjudication["freeze"], "adjudication_sha256": adjudication["receipt_sha256"],
              "strategy_semantics_sha256": adjudication["strategy_semantics_sha256"],
              "runtime": runtime, "execution_model": execution_model,
              "app_buy_permissions": adjudication.get("app_buy_permissions", {"profile": "legacy_unrecorded"}),
              "allocation": allocation, "decisions": decisions, "orders": orders,
              "accounting_basis": "fills_and_funding_required_not_plan_profit"}
    result["receipt_sha256"] = kol_policy.decision_sha256(result)
    return result


def compare_final_plans(left: dict, right: dict) -> dict:
    """Report the first material divergence without attributing causal profit."""
    for value in (left, right):
        if value.get("receipt_sha256") != kol_policy.decision_sha256(
                {k: v for k, v in value.items() if k != "receipt_sha256"}):
            raise ValueError("BOOK_B_FINAL_PLAN_HASH_MISMATCH")
    stages = (("source", "freeze"), ("rules", "rule_profile"),
              ("policy_and_selection", "strategy_semantics_sha256"),
              ("account_permissions", "app_buy_permissions"),
              ("account_allocation", "allocation"), ("execution_model", "execution_model"))
    first = next((name for name, field in stages if left.get(field) != right.get(field)), None)
    economics = lambda value: [{k: order.get(k) for k in ("code", "shares", "limit_price")}
                               for order in value["orders"]]
    if first is None and economics(left) != economics(right):
        first = "final_order_economics"
    return {"first_divergence": first, "same_order_economics": economics(left) == economics(right),
            "left_sha256": left["receipt_sha256"], "right_sha256": right["receipt_sha256"],
            "fill_or_return_equivalence": "not_established"}
