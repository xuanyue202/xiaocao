"""Reviewed KOL viewpoint history and currentness maintenance.

LiangHui is the household record and reader surface.  Xiaocao remains the
analysis owner: it selects report-bound viewpoints, appends explicit
currentness evaluations and relationships, and republishes an exact manifest
under compare-and-swap.  Historical maintenance never authorizes a household
notification or a Book replay.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .initial_import import initial_import_candidates
from .publication import (
    PublicationError,
    build_append_only_publication_update,
    build_record,
    evaluation_id,
    relation_id,
    stable_claim,
    viewpoint_id,
)


MAINTENANCE_CREATED_AT = "2026-07-26T11:52:13.000Z"
MAINTENANCE_AS_OF = "2026-07-26T11:52:13.000Z"
MAINTENANCE_CONTRACT_VERSION = "kol-longitudinal-review-v1"

READER_POSTURE_STYLES = {
    "scenario_analysis": "情景分析与条件验证",
    "risk_appetite_and_expectation_validation": "风险偏好与预期验证",
}
READER_INTERNAL_ACTION_LABELS = {
    "active": "具备模式资格",
    "cold": "尚不具备模式资格",
    "no_trade": "暂无可执行交易",
    "executable_count": "可执行候选数量",
}

LUCIFER_UNCERTAIN = {
    "sanhua-governance-risk",
    "strong-dollar-us-regime",
    "korea-capital-flight-risk",
    "crypto-trump-conditional",
    "elnino-commodity-risk",
    "memory-orders-vs-moat",
    "harmonic-drive-herd-risk",
    "unitree-policy-benchmark",
    "dreame-financing-risk",
    "geopolitical-war-risk",
    "account-cash-tax-scrutiny",
    "offshore-legal-structure",
    "macro-pessimism-information-filter",
}
XIAOCAO_UNCERTAIN = {
    "eight-session-2021-analogy",
    "changxin-not-sector-only-drain",
}
LV_VIDEO_CURRENT = {
    "lv-20260720-etf-versus-stock",
    "lv-20260720-remove-leverage",
}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"invalid reviewed viewpoint source: {path}") from exc
    if not isinstance(value, dict):
        raise PublicationError(f"reviewed viewpoint source is not an object: {path}")
    return value


def _safe_text(value: Any, *, maximum: int = 8_000) -> str:
    text = str(value or "").replace("<", "＜").replace(">", "＞").strip()
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


def _reader_text(value: Any, *, maximum: int = 8_000) -> str:
    text = _safe_text(value, maximum=maximum)
    for token, replacement in READER_INTERNAL_ACTION_LABELS.items():
        text = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
            replacement,
            text,
            flags=re.IGNORECASE,
        )
    return text


def _local_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _report(candidate: dict[str, Any]) -> dict[str, Any]:
    reports = [
        record for record in candidate["records"] if record["kind"] == "report"
    ]
    if len(reports) != 1:
        raise PublicationError("viewpoint maintenance needs exactly one report")
    return reports[0]


def _existing_viewpoints(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(record["payload"]["local_thesis_id"]): record
        for record in candidate["records"]
        if record["kind"] == "viewpoint"
    }


def _legacy_stance(row: dict[str, Any]) -> str:
    stance = _reader_text(row.get("stance"))
    if stance:
        return stance
    strength = _reader_text(row.get("strength"))
    note = _reader_text(row.get("note"))
    return "；".join(value for value in (strength, note) if value)


def _reader_posture_style(value: Any) -> str:
    style = _reader_text(value)
    return READER_POSTURE_STYLES.get(style, style)


def _legacy_evaluation(
    source_name: str,
    *,
    subject: str,
) -> dict[str, Any]:
    if source_name == "2026-07-13_lv_xiaotong_review.json":
        if subject in {"跨市场科技配置与去杠杆", "人工智能"}:
            return {
                "status": "current",
                "basis": (
                    "原始期限覆盖未来一个季度至数年，且7月20日后续直播继续确认"
                    "非杠杆科技配置和卸掉倍数产品；当前表示观点仍在适用期，"
                    "不代表系统认可任意价格买入。"
                ),
                "confidence": "medium",
                "uncertainties": ["具体工具、估值和入场条件仍需逐项复核"],
            }
        return {
            "status": "uncertain",
            "basis": (
                "原始期限仍可能覆盖当前，但存储、通信/光模块或设备资本开支"
                "缺少截至本次维护时的最新价格和基本面复核，因此保留为待确认。"
            ),
            "confidence": "medium",
            "uncertainties": ["需要最新价格、盈利预期或资本开支证据"],
        }
    return {
        "status": "expired",
        "basis": (
            "该观点服务于当次交易日或随后数日的市场结构；同一KOL之后已有"
            "新的真实发布事件重新判断环境，因此退出当前区但永久保留在历史时间线。"
        ),
        "confidence": "high",
        "uncertainties": [],
    }


def _legacy_specs(
    root: Path,
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    source_artifact = str(candidate["metadata"].get("source_artifact") or "")
    if not source_artifact.startswith("reference/experience/distilled/"):
        return []
    source_path = root / source_artifact
    value = _json(source_path)
    report = _report(candidate)
    payload = report["payload"]
    author = str(payload["author"])
    source_name = source_path.name
    posture = value.get("posture") if isinstance(value.get("posture"), dict) else {}
    regime = (
        value.get("regime_call")
        if isinstance(value.get("regime_call"), dict)
        else {}
    )
    horizon = _reader_text(regime.get("horizon")) or "当次发布事件及随后数日"
    dominant = _reader_posture_style(posture.get("dominant_style"))
    risk = _reader_text(posture.get("risk"))
    stance = "；".join(value for value in (dominant, risk) if value)
    specs: list[dict[str, Any]] = []
    if stance:
        subject = (
            "跨市场科技配置与去杠杆"
            if author == "吕晓彤"
            else "A股市场环境与总体策略"
        )
        local_thesis_id = "legacy-market-posture"
        specs.append(
            {
                "local_thesis_id": local_thesis_id,
                "subject": subject,
                "stance": stance,
                "horizon": horizon,
                "attribution": author,
                "role": "market_or_sector_view",
                "reasoning": _safe_text(value.get("summary")),
                "triggers": [],
                "falsifiers": (
                    [_reader_text(row) for row in regime.get("what_would_falsify", [])]
                    if isinstance(regime.get("what_would_falsify"), list)
                    else [_reader_text(regime.get("what_would_falsify"))]
                    if regime.get("what_would_falsify")
                    else []
                ),
                "evidence_refs": [
                    {
                        "claim_id": local_thesis_id,
                        "source_section": "reviewed_distill.posture",
                        "excerpt": stance,
                    }
                ],
                "evaluation": _legacy_evaluation(
                    source_name,
                    subject=subject,
                ),
            }
        )
    directions = value.get("directions")
    if isinstance(directions, list):
        for row in directions:
            if not isinstance(row, dict):
                continue
            subject = _safe_text(row.get("name"), maximum=500)
            direction_stance = _legacy_stance(row)
            if not subject or not direction_stance:
                continue
            local_thesis_id = _local_id("legacy-direction", subject)
            specs.append(
                {
                    "local_thesis_id": local_thesis_id,
                    "subject": subject,
                    "stance": direction_stance,
                    "horizon": horizon,
                    "attribution": author,
                    "role": "primary_recommendation",
                    "reasoning": _safe_text(value.get("summary")),
                    "triggers": [],
                    "falsifiers": [],
                    "evidence_refs": [
                        {
                            "claim_id": local_thesis_id,
                            "source_section": "reviewed_distill.directions",
                            "excerpt": direction_stance,
                        }
                    ],
                    "evaluation": _legacy_evaluation(
                        source_name,
                        subject=subject,
                    ),
                }
            )
    return specs


def _gold_evidence_refs(thesis: dict[str, Any]) -> list[dict[str, str]]:
    claim_ids = [
        str(value)
        for value in thesis.get("claim_ids", [])
        if str(value).strip()
    ]
    refs: list[dict[str, str]] = []
    for index, value in enumerate(thesis.get("evidence_refs", [])):
        if not isinstance(value, dict):
            continue
        quotes = value.get("quotes")
        excerpt = (
            _safe_text(quotes[0], maximum=2_000)
            if isinstance(quotes, list) and quotes
            else ""
        )
        segment_id = str(value.get("segment_id") or "").strip()
        if not excerpt or not segment_id:
            continue
        refs.append(
            {
                "claim_id": (
                    claim_ids[min(index, len(claim_ids) - 1)]
                    if claim_ids
                    else str(thesis["thesis_id"])
                ),
                "segment_id": segment_id,
                "excerpt": excerpt,
            }
        )
    if not refs:
        raise PublicationError(
            f"reviewed thesis lacks evidence: {thesis.get('thesis_id')}"
        )
    return refs


def _gold_evaluation(author: str, thesis_id: str) -> dict[str, Any]:
    if author == "路西法":
        if thesis_id in LUCIFER_UNCERTAIN:
            return {
                "status": "uncertain",
                "basis": (
                    "观点的原始适用期尚未明确结束，但其宏观、公司治理、产业、"
                    "地缘或法律事实没有在本次维护中完成足够的新证据复核；保留"
                    "为待确认，不因没有反例自动列为当前。"
                ),
                "confidence": "medium",
                "uncertainties": ["需要最新市场、公司披露或持牌专业意见复核"],
            }
        if thesis_id == "spacex-short-after-july-7":
            return {
                "status": "current",
                "basis": (
                    "7月7日时间触发已经发生，作者给出的中期期限仍覆盖"
                    "2026-07-26；系统已核对SPCX已上市、纳指100纳入和7月24日"
                    "价格。当前仅表示该KOL观点仍在适用窗口，不构成追空或执行授权。"
                ),
                "confidence": "high",
                "uncertainties": ["作者没有给出精确入场价，且现金纸面Book不支持做空"],
                "evidence": [
                    {
                        "as_of": "2026-07-24",
                        "excerpt": "SPCX已上市并于7月7日前纳入纳指100；7月24日价格115.07美元。",
                    }
                ],
            }
        return {
            "status": "current",
            "basis": (
                "该观点发布不足一个月，且作者给出的明确期限或条件仍覆盖"
                "2026-07-26；状态表示来源观点仍处适用窗口，不代表系统认定"
                "观点正确，也不授权任何真实交易或资本安排。"
            ),
            "confidence": "medium",
            "uncertainties": ["具体价格、触发条件和最新事实仍需在行动前复核"],
        }
    if author == "小草":
        if thesis_id in XIAOCAO_UNCERTAIN:
            return {
                "status": "uncertain",
                "basis": (
                    "该判断仍在原始观察窗口内，但它依赖历史类比或尚未发生的"
                    "资金分流，当前证据不足以把条件性推演列为已确认。"
                ),
                "confidence": "medium",
                "uncertainties": ["需要后续真实盘面确认"],
            }
        return {
            "status": "current",
            "basis": (
                "7月24日发布后尚无新的A股交易日，原始当前阶段、短期轮动或"
                "持续适用期限仍覆盖2026-07-26；状态只表示小草观点仍在当前"
                "决策窗口，不替用户执行交易。"
            ),
            "confidence": "high",
            "uncertainties": [],
        }
    if thesis_id in LV_VIDEO_CURRENT:
        return {
            "status": "current",
            "basis": (
                "去杠杆和非杠杆科技配置属于跨日风险控制原则，原始未来数月"
                "至长期期限仍覆盖2026-07-26。"
            ),
            "confidence": "high",
            "uncertainties": [],
        }
    return {
        "status": "uncertain",
        "basis": (
            "原始条件可能仍有效，但缺少当前价格、估值与明确入场触发复核，"
            "不能因为没有出现反例就自动列为当前。"
        ),
        "confidence": "medium",
        "uncertainties": ["需要当前价格、估值和触发条件复核"],
    }


def _gold_specs(
    root: Path,
    candidate: dict[str, Any],
    *,
    reviewed_artifact_root: Path,
) -> list[dict[str, Any]]:
    source_artifact = str(candidate["metadata"].get("source_artifact") or "")
    if not source_artifact.endswith(
        (
            "lucifer_20260705_claim_gold_v4.json",
            "xiaocao_20260724_claim_gold_v1.json",
        )
    ):
        return []
    value = _json(reviewed_artifact_root / source_artifact)
    item = value.get("item") or {}
    author = str(item.get("author") or "")
    inventory = item.get("investment_thesis_inventory") or {}
    theses = inventory.get("theses") if isinstance(inventory, dict) else None
    if not isinstance(theses, list):
        return []
    specs = []
    for thesis in theses:
        if (
            not isinstance(thesis, dict)
            or thesis.get("decision_relevance") != "must_surface"
        ):
            continue
        thesis_id = str(thesis.get("thesis_id") or "").strip()
        if not thesis_id:
            raise PublicationError("reviewed gold thesis lacks identity")
        specs.append(
            {
                "local_thesis_id": thesis_id,
                "subject": _safe_text(thesis.get("subject"), maximum=500),
                "stance": _safe_text(thesis.get("stance"), maximum=1_000),
                "horizon": _safe_text(thesis.get("horizon"), maximum=500),
                "attribution": _safe_text(
                    thesis.get("attribution") or author,
                    maximum=500,
                ),
                "role": _safe_text(thesis.get("role"), maximum=500),
                "reasoning": "",
                "triggers": [],
                "falsifiers": [],
                "uncertainties": [],
                "evidence_refs": _gold_evidence_refs(thesis),
                "evaluation": _gold_evaluation(author, thesis_id),
            }
        )
    return specs


def _viewpoint_record(
    report: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    report_payload = report["payload"]
    refs = spec["evidence_refs"]
    viewpoint_id_value = viewpoint_id(
        report["record_id"],
        spec["local_thesis_id"],
        refs,
    )
    payload = {
        "viewpoint_id": viewpoint_id_value,
        "report_id": report["record_id"],
        "kol_id": report_payload["kol_id"],
        "local_thesis_id": spec["local_thesis_id"],
        "subject": spec["subject"],
        "stance": spec["stance"],
        "source_published_at": report_payload["source_published_at"],
        "evidence_refs": refs,
    }
    for field in (
        "horizon",
        "attribution",
        "role",
        "reasoning",
        "triggers",
        "falsifiers",
        "uncertainties",
    ):
        value = spec.get(field)
        if value not in (None, "", []):
            payload[field] = value
    publication_id = report["source_binding"]["publication_id"]
    return build_record(
        kind="viewpoint",
        record_id_value=viewpoint_id_value,
        idempotency_key=stable_claim(
            "put",
            publication_id,
            "longitudinal-viewpoint-v1",
            viewpoint_id_value,
        ),
        created_at=MAINTENANCE_CREATED_AT,
        source_binding=report["source_binding"],
        payload=payload,
    )


def _evaluation_record(
    viewpoint: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    viewpoint_id_value = str(viewpoint["record_id"])
    evaluation_id_value = evaluation_id(
        viewpoint_id_value,
        MAINTENANCE_AS_OF,
        MAINTENANCE_AS_OF,
    )
    payload = {
        "evaluation_id": evaluation_id_value,
        "viewpoint_id": viewpoint_id_value,
        "status": evaluation["status"],
        "as_of": MAINTENANCE_AS_OF,
        "evaluated_at": MAINTENANCE_AS_OF,
        "basis": evaluation["basis"],
        "confidence": evaluation.get("confidence", "medium"),
        "uncertainties": evaluation.get("uncertainties", []),
    }
    if evaluation.get("evidence"):
        payload["evidence"] = evaluation["evidence"]
    publication_id = viewpoint["source_binding"]["publication_id"]
    return build_record(
        kind="viewpoint_evaluation",
        record_id_value=evaluation_id_value,
        idempotency_key=stable_claim(
            "put",
            publication_id,
            "longitudinal-evaluation-v1",
            evaluation_id_value,
        ),
        created_at=MAINTENANCE_CREATED_AT,
        source_binding=viewpoint["source_binding"],
        payload=payload,
    )


def _relation_record(
    *,
    source_binding: dict[str, Any],
    from_viewpoint_id: str,
    to_viewpoint_id: str,
    relation_type: str,
    reason: str,
) -> dict[str, Any]:
    relation_id_value = relation_id(
        from_viewpoint_id,
        to_viewpoint_id,
        relation_type,
        MAINTENANCE_AS_OF,
    )
    publication_id = str(source_binding["publication_id"])
    return build_record(
        kind="viewpoint_relation",
        record_id_value=relation_id_value,
        idempotency_key=stable_claim(
            "put",
            publication_id,
            "longitudinal-relation-v1",
            relation_id_value,
        ),
        created_at=MAINTENANCE_CREATED_AT,
        source_binding=source_binding,
        payload={
            "relation_id": relation_id_value,
            "from_viewpoint_id": from_viewpoint_id,
            "to_viewpoint_id": to_viewpoint_id,
            "relation_type": relation_type,
            "asserted_at": MAINTENANCE_AS_OF,
            "reason": reason,
        },
    )


def _build_working_set(
    root: Path,
    *,
    reviewed_artifact_root: Path,
) -> list[dict[str, Any]]:
    working: list[dict[str, Any]] = []
    for original in initial_import_candidates(
        root,
        reviewed_artifact_root=reviewed_artifact_root,
    ):
        report = _report(original)
        specs = _legacy_specs(root, original) or _gold_specs(
            root,
            original,
            reviewed_artifact_root=reviewed_artifact_root,
        )
        existing = _existing_viewpoints(original)
        viewpoints = list(existing.values())
        evaluations: list[dict[str, Any]] = []
        for spec in specs:
            local_thesis_id = str(spec["local_thesis_id"])
            viewpoint = existing.get(local_thesis_id)
            if viewpoint is None:
                viewpoint = _viewpoint_record(report, spec)
                viewpoints.append(viewpoint)
            evaluations.append(_evaluation_record(viewpoint, spec["evaluation"]))
        if not specs and existing:
            author = str(report["payload"]["author"])
            for local_thesis_id, viewpoint in existing.items():
                evaluations.append(
                    _evaluation_record(
                        viewpoint,
                        _gold_evaluation(author, local_thesis_id),
                    )
                )
        if not specs and not existing:
            continue
        working.append(
            {
                "original": original,
                "report": report,
                "viewpoints": viewpoints,
                "new_evaluations": evaluations,
                "relations": [],
                "spec_by_local_id": {
                    str(spec["local_thesis_id"]): spec for spec in specs
                },
            }
        )
    return working


def _add_relations(working: list[dict[str, Any]]) -> None:
    xiaocao_market: list[tuple[str, str, dict[str, Any]]] = []
    for row in working:
        report = row["report"]
        payload = report["payload"]
        source_artifact = str(
            row["original"]["metadata"].get("source_artifact") or ""
        )
        if payload["author"] != "小草":
            continue
        market = next(
            (
                viewpoint
                for viewpoint in row["viewpoints"]
                if viewpoint["payload"]["local_thesis_id"]
                in {"legacy-market-posture", "broad-decline-low-level-rotation"}
            ),
            None,
        )
        if market:
            xiaocao_market.append(
                (
                    str(payload["source_published_at"]),
                    source_artifact,
                    row,
                )
            )
    xiaocao_market.sort(key=lambda value: (value[0], value[1]))
    previous: dict[str, Any] | None = None
    for _, _, row in xiaocao_market:
        current = next(
            viewpoint
            for viewpoint in row["viewpoints"]
            if viewpoint["payload"]["local_thesis_id"]
            in {"legacy-market-posture", "broad-decline-low-level-rotation"}
        )
        if previous is not None:
            row["relations"].append(
                _relation_record(
                    source_binding=current["source_binding"],
                    from_viewpoint_id=current["record_id"],
                    to_viewpoint_id=previous["record_id"],
                    relation_type="replaces",
                    reason=(
                        "后续真实发布事件重新判断A股环境与总体策略；旧观点保留"
                        "在历史时间线，不由新观点静默覆盖。"
                    ),
                )
            )
        previous = current

    lv_legacy: dict[str, dict[str, Any]] = {}
    lv_video_row: dict[str, Any] | None = None
    for row in working:
        report = row["report"]
        if report["payload"]["author"] != "吕晓彤":
            continue
        source_name = Path(
            str(row["original"]["metadata"].get("source_artifact") or "")
        ).name
        for viewpoint in row["viewpoints"]:
            local_id = str(viewpoint["payload"]["local_thesis_id"])
            subject = str(viewpoint["payload"]["subject"])
            if (
                source_name == "2026-07-13_lv_xiaotong_review.json"
                and local_id == "legacy-market-posture"
            ):
                lv_legacy["market"] = viewpoint
            elif (
                source_name == "2026-07-13_lv_xiaotong_review.json"
                and subject == "人工智能"
            ):
                lv_legacy["ai"] = viewpoint
            elif local_id.startswith("lv-20260720-"):
                lv_video_row = row
    if lv_video_row and {"market", "ai"} <= set(lv_legacy):
        later = {
            viewpoint["payload"]["local_thesis_id"]: viewpoint
            for viewpoint in lv_video_row["viewpoints"]
        }
        lv_video_row["relations"].extend(
            [
                _relation_record(
                    source_binding=later[
                        "lv-20260720-remove-leverage"
                    ]["source_binding"],
                    from_viewpoint_id=later[
                        "lv-20260720-remove-leverage"
                    ]["record_id"],
                    to_viewpoint_id=lv_legacy["market"]["record_id"],
                    relation_type="refines",
                    reason=(
                        "7月20日把7月13日的科技去杠杆总原则细化为立即卸掉"
                        "倍数产品，同时保留非杠杆方向暴露。"
                    ),
                ),
                _relation_record(
                    source_binding=later[
                        "lv-20260720-etf-versus-stock"
                    ]["source_binding"],
                    from_viewpoint_id=later[
                        "lv-20260720-etf-versus-stock"
                    ]["record_id"],
                    to_viewpoint_id=lv_legacy["ai"]["record_id"],
                    relation_type="refines",
                    reason=(
                        "7月20日进一步说明长期科技/AI暴露可用非杠杆ETF或"
                        "有明确逻辑的个股表达。"
                    ),
                ),
            ]
        )

    for row in working:
        if row["report"]["payload"]["author"] != "路西法":
            continue
        by_local = {
            viewpoint["payload"]["local_thesis_id"]: viewpoint
            for viewpoint in row["viewpoints"]
        }
        pairs = (
            (
                "gold-near-term-rebound",
                "gold-tactical-trim",
                "黄金短线反弹与下半年逢高减仓属于不同期限，可以并存。",
            ),
            (
                "physical-ai-energy-etf",
                "ai-bubble-winter-window",
                "物理AI长期主线与冬季至明春的估值风险属于不同期限，可以并存。",
            ),
        )
        for from_local, to_local, reason in pairs:
            if from_local in by_local and to_local in by_local:
                row["relations"].append(
                    _relation_record(
                        source_binding=by_local[from_local]["source_binding"],
                        from_viewpoint_id=by_local[from_local]["record_id"],
                        to_viewpoint_id=by_local[to_local]["record_id"],
                        relation_type="coexists",
                        reason=reason,
                    )
                )


def longitudinal_update_candidates(
    root: Path | str,
    *,
    reviewed_artifact_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Build exact CAS updates for the reviewed initial production corpus."""

    project = Path(root).expanduser().resolve()
    reviewed = (
        project
        if reviewed_artifact_root is None
        else Path(reviewed_artifact_root).expanduser().resolve()
    )
    working = _build_working_set(
        project,
        reviewed_artifact_root=reviewed,
    )
    _add_relations(working)
    results: list[dict[str, Any]] = []
    for row in working:
        original = row["original"]
        old_report = row["report"]
        viewpoint_ids = [
            str(viewpoint["record_id"]) for viewpoint in row["viewpoints"]
        ]
        old_non_report = [
            record
            for record in original["records"]
            if record["kind"] != "report"
        ]
        existing_keys = {
            (
                str(record["kind"]),
                str(record["record_id"]),
                str(record["content_sha256"]),
            )
            for record in old_non_report
        }
        additions = [
            record
            for record in (
                row["viewpoints"]
                + row["new_evaluations"]
                + row["relations"]
            )
            if (
                str(record["kind"]),
                str(record["record_id"]),
                str(record["content_sha256"]),
            )
            not in existing_keys
        ]
        records, publish = build_append_only_publication_update(
            current_records=original["records"],
            additions=additions,
            viewpoint_ids=viewpoint_ids,
            created_at=MAINTENANCE_CREATED_AT,
            revision=MAINTENANCE_CONTRACT_VERSION,
            reason=(
                "补齐受审历史观点时间线并显式重评当前性；不创建提醒、不重放Book"
            ),
        )
        results.append(
            {
                "publication_key": (
                    "longitudinal-v1:" + str(original["publication_key"])
                ),
                "records": records,
                "publish_request": publish,
                "metadata": {
                    "historical": True,
                    "notification_claim_authorized": False,
                    "book_kol_us_replay_authorized": False,
                    "large_payload_local_bytes": 0,
                    "source_publication_key": original["publication_key"],
                    "source_artifact": original["metadata"].get(
                        "source_artifact"
                    ),
                    "viewpoint_count": len(row["viewpoints"]),
                    "evaluation_count": len(
                        [
                            record
                            for record in records
                            if record["kind"] == "viewpoint_evaluation"
                        ]
                    ),
                    "relation_count": len(
                        [
                            record
                            for record in records
                            if record["kind"] == "viewpoint_relation"
                        ]
                    ),
                },
            }
        )
    return sorted(
        results,
        key=lambda candidate: (
            str(_report(candidate)["payload"]["source_published_at"]),
            str(candidate["metadata"].get("source_artifact") or ""),
            str(candidate["publication_key"]),
        ),
    )


def longitudinal_projection(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the Agent-owned current/history projection for audit."""

    by_kol: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        report = _report(candidate)
        payload = report["payload"]
        kol_id = str(payload["kol_id"])
        kol = by_kol.setdefault(
            kol_id,
            {
                "kol_id": kol_id,
                "author": payload["author"],
                "viewpoints": {},
                "evaluations": {},
                "relation_count": 0,
            },
        )
        for record in candidate["records"]:
            if record["kind"] == "viewpoint":
                kol["viewpoints"][record["record_id"]] = record["payload"]
            elif record["kind"] == "viewpoint_evaluation":
                evaluation = record["payload"]
                viewpoint_id_value = str(evaluation["viewpoint_id"])
                prior = kol["evaluations"].get(viewpoint_id_value)
                if prior is None or str(evaluation["evaluated_at"]) > str(
                    prior["evaluated_at"]
                ):
                    kol["evaluations"][viewpoint_id_value] = evaluation
            elif record["kind"] == "viewpoint_relation":
                kol["relation_count"] += 1
    output = {}
    for kol_id, kol in sorted(by_kol.items()):
        counts = {
            "current": 0,
            "uncertain": 0,
            "expired": 0,
            "invalidated": 0,
        }
        current = []
        history = []
        for viewpoint_id_value, viewpoint in kol["viewpoints"].items():
            evaluation = kol["evaluations"].get(viewpoint_id_value)
            if evaluation is None:
                raise PublicationError(
                    f"viewpoint lacks currentness evaluation: {viewpoint_id_value}"
                )
            status = str(evaluation["status"])
            counts[status] += 1
            item = {
                "viewpoint_id": viewpoint_id_value,
                "source_published_at": viewpoint["source_published_at"],
                "subject": viewpoint["subject"],
                "stance": viewpoint["stance"],
                "horizon": viewpoint.get("horizon"),
                "status": status,
                "as_of": evaluation["as_of"],
                "basis": evaluation["basis"],
                "confidence": evaluation.get("confidence"),
                "uncertainties": evaluation.get("uncertainties", []),
            }
            history.append(item)
            if status in {"current", "uncertain"}:
                current.append(item)
        current.sort(
            key=lambda item: (
                str(item["source_published_at"]),
                item["status"] == "current",
            ),
            reverse=True,
        )
        history.sort(
            key=lambda item: (
                str(item["source_published_at"]),
                str(item["viewpoint_id"]),
            ),
            reverse=True,
        )
        output[kol_id] = {
            "kol_id": kol_id,
            "author": kol["author"],
            "counts": counts,
            "current_viewpoints": current,
            "history": history,
            "relation_count": kol["relation_count"],
            "as_of": MAINTENANCE_AS_OF,
        }
    return {
        "contract_version": MAINTENANCE_CONTRACT_VERSION,
        "as_of": MAINTENANCE_AS_OF,
        "kols": output,
        "notification_claims_created": 0,
        "book_kol_us_replays": 0,
        "large_payload_local_bytes": 0,
    }
