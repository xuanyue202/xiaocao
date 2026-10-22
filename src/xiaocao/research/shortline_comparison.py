"""Isolated short-term selection experiments; never record an account or fill."""
from __future__ import annotations

import hashlib
import json
import re
import math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median

from xiaocao.utils.atomic_files import atomic_write
from xiaocao.live.book_b_workflow import summarize_adjudication
from xiaocao.live.trading_runner import frozen_rows_digest
from xiaocao.research.paper_fill_evidence import classify_paper_fill, summarize_paper_fills


SELECTORS = ("kp_star", "vb_star", "mode_star", "mode_exec_star")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def record_selection_experiments(root: Path, trade_date: str, rows: list[dict],
                                 adjudication: dict) -> dict:
    """Archive all selector choices from the consumed original freeze.

    These are full-denominator selection records, not funded paper portfolios.
    Empty selections are preserved. Eligibility/fill/account constraints are not
    retroactively invented for a research selector that lacks that authority.
    The caller has already validated the original bundle; this does not mint one.
    """
    if date.fromisoformat(trade_date).isoformat() != trade_date:
        raise ValueError("SHORTLINE_EXPERIMENT_DATE_INVALID")
    freeze = adjudication["freeze_sha256"]
    if not isinstance(freeze, str) or re.fullmatch(r"[0-9a-f]{64}", freeze) is None:
        raise ValueError("SHORTLINE_EXPERIMENT_FREEZE_REQUIRED")
    body = {k: v for k, v in adjudication.items() if k != "receipt_sha256"}
    if hashlib.sha256(_canonical(body)).hexdigest() != adjudication.get("receipt_sha256"):
        raise ValueError("SHORTLINE_EXPERIMENT_ADJUDICATION_INVALID")
    if summarize_adjudication(adjudication, runtime="paper")["status"] != "recorded":
        raise ValueError("SHORTLINE_EXPERIMENT_PAPER_RECEIPT_REQUIRED")
    if adjudication["freeze"]["market_date"] != trade_date:
        raise ValueError("SHORTLINE_EXPERIMENT_DATE_MISMATCH")
    if frozen_rows_digest(rows) != freeze or len(rows) != adjudication["freeze"]["snapshot_row_count"]:
        raise ValueError("SHORTLINE_EXPERIMENT_ORIGINAL_ROWS_MISMATCH")
    candidates = [row for row in rows if row.get("book") == "B" and row.get("is_live") is True]
    keys = [(row.get("code"), row.get("mode")) for row in candidates]
    if len(keys) != len(set(keys)) or any(not code or not mode for code, mode in keys):
        raise ValueError("SHORTLINE_EXPERIMENT_CANDIDATE_IDENTITY_INVALID")
    variants = {selector: [row["code"] for row in candidates if row.get(selector) is True]
                for selector in SELECTORS}
    variants["baseline_no_kol"] = list(adjudication["baseline_codes"])
    variants["current_bounded"] = list(adjudication["strategy_codes"])
    record = {
        "schema_version": "shortline-selection-experiments.v1", "trade_date": trade_date,
        "freeze": adjudication["freeze"],
        "freeze_sha256": freeze, "adjudication_sha256": adjudication["receipt_sha256"],
        "strategy_semantics_sha256": adjudication["strategy_semantics_sha256"],
        "runtime": "research", "authority": 0, "status": "selection_recorded_outcomes_pending",
        "variants": variants, "candidate_count": len(candidates),
        "policy": adjudication["judgment"],
        "variant_semantics": {
            "baseline_no_kol": "pre_allocation_star_selection_without_KOL",
            "current_bounded": "pre_allocation_star_selection_with_validated_mode_follow",
            "policy_scaling": "recorded_separately_not_a_funded_ablation",
        },
        "candidates": [{"code": row["code"], "mode": row["mode"],
                        "row_sha256": frozen_rows_digest([row]),
                        "captured_at": row.get("captured_at"),
                        "mode_state": row.get("mode_state"),
                        "selector_evidence": {key: row[key] if type(row.get(key)) is bool else None for key in SELECTORS},
                        "selector_fields_missing": [key for key in SELECTORS if type(row.get(key)) is not bool]}
                       for row in candidates],
        "accounting": {"portfolio_return": None, "fills": None,
                       "reason": "selection_only_cash_slots_T1_fees_and_execution_not_simulated"},
    }
    raw = _canonical(record)
    sha = hashlib.sha256(raw).hexdigest()
    path = Path(root) / "output/research/shortline_experiments" / trade_date / (sha + ".json")
    atomic_write(path, raw, immutable=True)
    return {"status": record["status"], "path": str(path.resolve()), "sha256": sha,
            "variant_counts": {key: len(value) for key, value in variants.items()}}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def compare_shortline(positions: list[dict], training: list[dict], *, start: str, end: str) -> dict:
    """Compare saved evidence with explicit cohorts; never simulate a portfolio.

    Training labels are measured in percentage points. All selectors use the
    same executable_net_ret, not the theoretical label used by older reports.
    An observation cutoff is not proof of historical point-in-time availability.
    """
    from xiaocao.live.ab_attribution import paired_exit_attribution

    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("SHORTLINE_WINDOW_INVALID")
    paired_rows = []
    modes: dict[str, list[dict]] = defaultdict(list)
    for original in positions:
        if original.get("book") not in {"A", "B"} or not start <= str(original.get("entry_date", ""))[:10] <= end:
            continue
        row = dict(original)
        if row.get("status") == "closed" and (not row.get("exit_date") or str(row["exit_date"])[:10] > end):
            row["status"] = "open"
        if row.get("status") == "closed":
            for key in ("shares", "entry_price", "entry_cash_out", "realized_pnl"):
                if _number(row.get(key)) is None:
                    raise ValueError("SHORTLINE_POSITION_ECONOMICS_INVALID")
            if any(row[key] <= 0 for key in ("shares", "entry_price", "entry_cash_out")):
                raise ValueError("SHORTLINE_POSITION_ECONOMICS_INVALID")
        paired_rows.append(row)
        if row["book"] == "B":
            modes[str(row.get("mode") or "unclassified")].append(row)
    paired = paired_exit_attribution(paired_rows)
    # The attribution function guarantees one A and one B per accepted key.
    # A pair has window labels only when both entries carry those labels.
    paired_keys = {(row["entry_date"], row["code"]) for row in paired["pairs"]}
    pair_basis = defaultdict(dict)
    for row in paired_rows:
        key = (str(row.get("entry_date"))[:10], row.get("code"))
        if key in paired_keys:
            pair_basis[key][row["book"]] = classify_paper_fill(row)
    for row in paired["pairs"]:
        basis = pair_basis[(row["entry_date"], row["code"])]
        row["entry_basis"] = {**basis, "pair": next(category for category in
            ("fallback", "proxy", "unknown", "reported_window") if category in basis.values())}
    paired["fill_evidence"] = summarize_paper_fills([row["entry_basis"]["pair"] for row in paired["pairs"]])
    paired["fill_evidence"]["by_book"] = {
        book: summarize_paper_fills([row["entry_basis"][book] for row in paired["pairs"]]) for book in ("A", "B")}
    differences = [row["b_minus_a_pp"] for row in paired["pairs"]]
    paired.update(
        median_b_minus_a_pp=median(differences) if differences else None,
        mean_without_best_pair_pp=mean(sorted(differences)[:-1]) if len(differences) > 1 else None,
        entry_day_count=len({row["entry_date"] for row in paired["pairs"]}),
        b_worse_pairs=sum(value < 0 for value in differences),
        equal_pairs=sum(value == 0 for value in differences),
    )
    mode_rows = []
    for mode, rows in sorted(modes.items()):
        closed = [row for row in rows if row.get("status") == "closed"]
        mode_rows.append({"mode": mode, "entries": len(rows), "closed": len(closed),
                          "open_or_not_closed_by_cutoff": len(rows) - len(closed),
                          "closed_fill_evidence": summarize_paper_fills([classify_paper_fill(row) for row in closed]),
                          "closed_pnl": sum(row["realized_pnl"] for row in closed),
                          "mean_closed_return_pct": mean(row["realized_pnl"] / row["entry_cash_out"] * 100
                                                         for row in closed) if closed else None})
    candidates = [row for row in training if row.get("book") == "B" and row.get("is_live") is True
                  and start <= str(row.get("date", ""))[:10] <= end]
    keys = [(str(row.get("date"))[:10], row.get("code")) for row in candidates]
    if len(keys) != len(set(keys)):
        raise ValueError("SHORTLINE_DUPLICATE_TRAINING_IDENTITY")

    def label(row: dict) -> float | None:
        if str(row.get("code") or "").endswith(".BJSE") or row.get("executable_fillable") is not True:
            return None
        return _number(row.get("executable_net_ret"))

    conditional = []
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        by_day[str(row["date"])[:10]].append(row)
    for selector in SELECTORS:
        selected = [row for row in candidates if row.get(selector) is True]
        values = [value for row in selected if (value := label(row)) is not None]
        conditional.append({"selector": selector, "selected": len(selected), "labels": len(values),
                            "selected_without_label": len(selected) - len(values),
                            "flag_unknown": sum(type(row.get(selector)) is not bool for row in candidates),
                            "mean_executable_label_pct": mean(values) if values else None})
    complete_flags = {day: rows for day, rows in by_day.items()
                      if all(type(row.get(selector)) is bool for row in rows for selector in SELECTORS)}
    complete_labels = {day: rows for day, rows in complete_flags.items()
                       if all(label(row) is not None for row in rows if any(row[key] for key in SELECTORS))}
    common = []
    for selector in SELECTORS:
        observations = []
        for day, rows in sorted(complete_labels.items()):
            selected = [row for row in rows if row[selector]]
            observations.append({"date": day, "selected": len(selected),
                                 "three_slot_measure_pct": sum(label(row) for row in selected) / 3})
        common.append({"selector": selector, "days": len(observations),
                       "active_days": sum(row["selected"] > 0 for row in observations),
                       "selected": sum(row["selected"] for row in observations),
                       "mean_three_slot_measure_pct": mean(row["three_slot_measure_pct"] for row in observations)
                           if observations else None,
                       "observations": observations})
    return {
        "schema_version": "shortline-comparison.v1", "authority": 0,
        "start": start, "end": end, "status": "descriptive_only_no_promotion",
        "paired_exit": paired, "traded_mode_cohorts": mode_rows,
        "selector_labels": conditional, "common_date_diagnostic": common,
        "coverage": {"candidate_rows": len(candidates), "signal_days": len(by_day),
                     "bjse_rows_retained_in_raw_denominator": sum(str(row.get("code") or "").endswith(".BJSE") for row in candidates),
                     "complete_flag_days": len(complete_flags), "complete_label_days": len(complete_labels),
                     "excluded_incomplete_flag_days": sorted(set(by_day) - set(complete_flags)),
                     "excluded_incomplete_label_days": sorted(set(complete_flags) - set(complete_labels)),
                     "capture_hash_rows": sum(isinstance(row.get("original_capture_sha256"), str)
                         and re.fullmatch(r"[0-9a-f]{64}", row["original_capture_sha256"]) is not None for row in candidates),
                     "fillability": dict(Counter(str(row.get("executable_fillable")) for row in candidates))},
        "portfolio_return": None, "promotion_eligible": False,
        "limitations": [
            "Book T excluded: independent trend strategy",
            "A/B paired exits are descriptive; they do not measure KOL or selector alpha",
            "entry basis counts are saved model labels; even reported_window is not independently confirmed execution",
            "mode PnL conditions on actually traded entries and their position sizes",
            "selector labels are next-close outcomes, not dynamic Book-B exits",
            "three-slot arithmetic diagnostic includes cash zeros but is not a self-financing portfolio",
            "common-date complete cases exclude missing labels and may be selection biased",
            "T+1, overlapping holdings, cash, board lots, risk caps and execution versions are not simulated",
            "legacy label availability/outcome clocks are unproved; no point-in-time or OOS certification",
            "APP realized fees, cashflows and account returns require independent reconciliation",
        ],
    }


def render_comparison(report: dict) -> str:
    pair = report["paired_exit"]
    number = lambda value: "N/A" if value is None else f"{value:+.4f}"
    lines = [f"# 短线对照：{report['start']}—{report['end']}", "",
             "描述性研究；Book T 不纳入。下面的单笔标签和三槽指标均不是组合收益率。", "",
             f"严格同进场 A/B 已平仓 {pair['eligible_pairs']} 对，{pair['entry_day_count']} 个入场日；"
             f"B−A 平均 {number(pair['mean_b_minus_a_pp'])}pp，中位数 {number(pair['median_b_minus_a_pp'])}pp。",
             f"B 更好/更差/相同：{pair['b_better_pairs']}/{pair['b_worse_pairs']}/{pair['equal_pairs']}；"
             f"去掉最大正差后均值 {number(pair['mean_without_best_pair_pp'])}pp。", "",
             "| 选择器 | 原选中 | 可成交标签 | 缺标签 | 单笔标签均值% |", "|---|---:|---:|---:|---:|"]
    for row in report["selector_labels"]:
        lines.append(f"| {row['selector']} | {row['selected']} | {row['labels']} | {row['selected_without_label']} | {number(row['mean_executable_label_pct'])} |")
    lines += ["", "共同日期、固定三个名义槽的算术诊断（空槽为现金；不复利、不代表可实现组合）：", "",
              "| 选择器 | 完整日期 | 有选择日 | 三槽指标均值% |", "|---|---:|---:|---:|"]
    for row in report["common_date_diagnostic"]:
        lines.append(f"| {row['selector']} | {row['days']} | {row['active_days']} | {number(row['mean_three_slot_measure_pct'])} |")
    lines += ["", "成交依据覆盖（仅保存的模型标签，窗口标签也未经原窗口/hash/时钟复核）：", "",
              "| 样本 | 数量 | 窗口标签 | fallback | 重试/代理 | 未知 | 代理含 fallback 占比% |", "|---|---:|---:|---:|---:|---:|---:|"]
    evidence = [("A/B 配对", pair["fill_evidence"])] + [
        ("B 已平仓：" + row["mode"], row["closed_fill_evidence"]) for row in report["traded_mode_cohorts"]]
    for name, item in evidence:
        counts = item["counts"]
        share = item["proxy_including_fallback_proportion"]
        lines.append(f"| {name} | {item['count']} | {counts['reported_window']} | {counts['fallback']} | {counts['proxy']} | {counts['unknown']} | {number(share * 100 if share is not None else None)} |")
    lines += ["", "配对按较弱依据归类：任一方 fallback/代理则分别归类；否则任一方未知则为未知。"]
    lines += ["", "局限与未证明事项：", "", *["- " + value for value in report["limitations"]]]
    return "\n".join(lines) + "\n"


def observe_shortline_research(contents: dict[str, bytes], *, as_of: date) -> dict:
    """Inventory only immutable files already captured by the weekly harness."""
    comparisons, captures, invalid = [], [], []
    for path, raw in sorted(contents.items()):
        capture = path.startswith("output/research/shortline_experiments/") and path.endswith(".json")
        comparison = path.startswith("output/research/shortline_comparisons/") and path.endswith(".json")
        if not (capture or comparison):
            continue
        try:
            value = json.loads(raw)
            sha = hashlib.sha256(raw).hexdigest()
            if not Path(path).stem.endswith(sha) or value.get("authority") != 0:
                raise ValueError("content_hash_or_authority_invalid")
            day = date.fromisoformat(value["trade_date"] if capture else value["end"])
            if day > as_of:
                continue
            ref = {"path": path, "sha256": sha}
            if capture:
                if value.get("schema_version") != "shortline-selection-experiments.v1":
                    raise ValueError("capture_schema_invalid")
                captures.append({"date": day.isoformat(), "evidence": ref, "status": value["status"]})
            else:
                observed = datetime.fromisoformat(value["observed_at"])
                if observed.utcoffset() is None or observed.date() > as_of:
                    continue
                if (value.get("schema_version") != "shortline-comparison.v1"
                        or value.get("promotion_eligible") is not False or value.get("portfolio_return") is not None):
                    raise ValueError("comparison_schema_or_scope_invalid")
                inputs = value.get("inputs")
                if not isinstance(inputs, list) or len(inputs) != 2:
                    raise ValueError("comparison_inputs_missing")
                for reference in inputs:
                    original = contents.get(reference["path"])
                    if original is None or hashlib.sha256(original).hexdigest() != reference["sha256"]:
                        raise ValueError("comparison_input_hash_unproved")
                comparisons.append({"end": value["end"], "observed_at": value["observed_at"],
                    "evidence": ref, "paired_exit": {key: value["paired_exit"][key] for key in (
                        "eligible_pairs", "entry_day_count", "mean_b_minus_a_pp", "median_b_minus_a_pp")},
                    "coverage": value["coverage"], "status": "descriptive_only_no_promotion"})
        except (ValueError, KeyError, TypeError, AttributeError):
            invalid.append(path)
    return {"status": "observed" if comparisons or captures else "missing",
            "comparisons": comparisons, "selection_records": captures, "invalid": invalid,
            "current_window_report_observed": any(item["end"] == as_of.isoformat() for item in comparisons),
            "selection_days": len({item["date"] for item in captures}),
            "portfolio_experiment_status": "not_established_by_selection_records",
            "promotion_eligible": False}
