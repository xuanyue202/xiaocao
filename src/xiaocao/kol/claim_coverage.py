"""Source-agnostic investment-claim extraction and coverage contracts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ._shared import DecisionError


CONTRACT_VERSION = "kol-investment-claims-v1"
IMPORTANCE_BASES = {
    "explicit_recommendation",
    "portfolio_or_risk_guidance",
    "market_or_sector_view",
    "material_impact_thesis",
}
MENTION_ROLES = {
    "primary_recommendation",
    "alternative_instrument",
    "risk_warning",
    "supporting_rationale",
    "historical_example",
    "analogy",
    "quoted_view",
    "unrelated_mention",
}
AUDIT_ONLY_ROLES = {
    "historical_example",
    "analogy",
    "quoted_view",
    "unrelated_mention",
}
AUDIT_DISPOSITIONS = {
    "investment_content",
    "non_investment_content",
    "advertisement",
}
FACT_CHECK_STATUSES = {
    "support",
    "conflict",
    "unverified",
    "not_needed",
}
PRIORITY_LEVELS = {"low", "medium", "high"}
USER_RELEVANCE_LEVELS = {"unknown", "indirect", "direct"}
_SENTENCE_BOUNDARY = re.compile(r".+?(?:[。！？!?；;\n]+|$)", re.DOTALL)
_MARKDOWN_TABLE_SEPARATOR = re.compile(
    r"(?m)^\s*\|?(?:\s*:?-{3,}:?\s*\|){2,}\s*$"
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_segments(
    text: str,
    *,
    evidence_sha256: str,
    target_chars: int = 1200,
) -> list[dict[str, Any]]:
    """Split complete evidence structurally without deciding importance."""
    if target_chars < 200:
        raise ValueError("target_chars must be at least 200")
    spans: list[tuple[int, int]] = []
    pending_start: int | None = None
    pending_end: int | None = None
    for match in _SENTENCE_BOUNDARY.finditer(text):
        hard_boundary = "\n" in match.group(0)
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start >= end:
            continue
        if pending_start is None:
            pending_start, pending_end = start, end
            if hard_boundary:
                spans.append((pending_start, pending_end))
                pending_start, pending_end = None, None
            continue
        assert pending_end is not None
        if end - pending_start <= target_chars:
            pending_end = end
            if hard_boundary:
                spans.append((pending_start, pending_end))
                pending_start, pending_end = None, None
            continue
        spans.append((pending_start, pending_end))
        pending_start, pending_end = start, end
        if hard_boundary:
            spans.append((pending_start, pending_end))
            pending_start, pending_end = None, None
    if pending_start is not None and pending_end is not None:
        spans.append((pending_start, pending_end))

    normalized: list[tuple[int, int]] = []
    for start, end in spans:
        cursor = start
        while end - cursor > target_chars * 2:
            cut = cursor + target_chars
            normalized.append((cursor, cut))
            cursor = cut
        normalized.append((cursor, end))

    segments = []
    for index, (start, end) in enumerate(normalized, start=1):
        segment_text = text[start:end]
        segment_sha256 = _sha256_text(segment_text)
        segment_id = _sha256_text(
            f"{CONTRACT_VERSION}\n{evidence_sha256}\n"
            f"{start}:{end}\n{segment_sha256}"
        )
        segments.append(
            {
                "segment_id": segment_id,
                "index": index,
                "start": start,
                "end": end,
                "char_count": len(segment_text),
                "sha256": segment_sha256,
            }
        )
    return segments


def build_claim_extraction_request(
    evidence_path: Path | str,
    *,
    evidence_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the same semantic extraction request for every KOL source."""
    path = Path(evidence_path).expanduser().resolve()
    if not path.is_file():
        raise DecisionError("KOL claim extraction evidence is missing")
    actual_sha256 = _sha256_file(path)
    if evidence_sha256 and evidence_sha256 != actual_sha256:
        raise DecisionError("KOL claim extraction evidence hash changed")
    text = path.read_text(encoding="utf-8")
    segments = evidence_segments(text, evidence_sha256=actual_sha256)
    return {
        "contract_version": CONTRACT_VERSION,
        "evidence_path": str(path),
        "evidence_sha256": actual_sha256,
        "goal": (
            "让用户快速看清来源中所有具体投资建议和可能显著影响"
            "资产选择、方向、仓位、时点、持有期限或风险控制的信息。"
        ),
        "mandatory_order": [
            "first_pass_complete_investment_thesis_inventory",
            "second_pass_independent_full_evidence_coverage_audit",
            "fact_and_background_supplement",
            "reader_briefing",
            "household_and_book_routing",
        ],
        "must_surface_if_any": sorted(IMPORTANCE_BASES),
        "mention_roles": sorted(MENTION_ROLES),
        "rules": [
            (
                "具体建议和潜在重大影响是并列的或条件；不得要求对象、"
                "方向、时间、仓位和风险同时齐全。"
            ),
            (
                "条件性、低置信、尚未核实或与系统判断冲突只能成为"
                "标签，不能删除已达到任一必达门槛的来源主张。"
            ),
            (
                "纯广告和推广直接排除；历史案例、类比、引用观点和"
                "无关提及保留角色，重大角色歧义按不确定内容展示。"
            ),
            (
                "相同对象、方向、期限和条件的论点可以跨段聚合；"
                "不同方向、期限或条件不得合并。"
            ),
            (
                "用户持仓只影响排序和关联说明，不限制提取范围。"
            ),
            (
                "关键词、资产名称、动作词组合和单次摘要均不能充当"
                "完整性证明。"
            ),
            (
                "读者输出使用逻辑通顺的自然语言，不使用表格；系统"
                "只补充关键背景、事实、冲突或疑点。"
            ),
        ],
        "coverage_audit": {
            "review_mode": "independent_semantic_reread",
            "required_segment_ids": [
                segment["segment_id"] for segment in segments
            ],
            "allowed_dispositions": sorted(AUDIT_DISPOSITIONS),
            "pass_condition": (
                "every segment reviewed exactly once; every investment "
                "segment links a thesis; missing, merge, and role findings empty"
            ),
        },
        "required_output_schema": {
            "investment_thesis_inventory": {
                "contract_version": CONTRACT_VERSION,
                "evidence_sha256": actual_sha256,
                "theses": [
                    {
                        "thesis_id": "stable semantic identity",
                        "role": "one mention_roles value",
                        "decision_relevance": "must_surface or audit_only",
                        "importance_basis": (
                            "one or more must_surface_if_any values; "
                            "empty only for audit_only"
                        ),
                        "claim_ids": (
                            "one or more evidence-bound claim ids for "
                            "must_surface"
                        ),
                        "subject": (
                            "自然中文的资产、主题、市场或资本风险名称；"
                            "只有正式公司/产品名和股票或ETF代码可保留英文"
                        ),
                        "stance": (
                            "忠实、完整、自然中文的观点结论及条件；"
                            "不得输出内部枚举或英文标签"
                        ),
                        "horizon": "自然中文的来源期限，或明确写原文未提供",
                        "attribution": "说话人、被引用方或自然中文的归属歧义",
                        "evidence_refs": [
                            {
                                "segment_id": "one supplied segment id",
                                "quotes": ["exact source quote"],
                            }
                        ],
                        "priority": {
                            "rank": "contiguous integer for must_surface",
                            "urgency": "low, medium, or high",
                            "potential_impact": "low, medium, or high",
                            "specificity": "low, medium, or high",
                            "user_relevance": "unknown, indirect, or direct",
                            "reason": "自然中文的决策优先级理由",
                        },
                    }
                ],
            },
            "investment_thesis_coverage_audit": {
                "contract_version": CONTRACT_VERSION,
                "evidence_sha256": actual_sha256,
                "review_mode": "independent_semantic_reread",
                "status": "passed only after findings are resolved",
                "findings": {
                    "missing_theses": [],
                    "incorrect_merges": [],
                    "role_errors": [],
                },
                "segment_reviews": [
                    {
                        "segment_id": "every supplied segment exactly once",
                        "disposition": "one allowed disposition",
                        "thesis_ids": (
                            "linked theses for investment_content; empty otherwise"
                        ),
                        "reason": "semantic classification reason",
                    }
                ],
            },
            "investment_thesis_fact_checks": [
                {
                    "thesis_id": "every must_surface thesis exactly once",
                    "status": "support, conflict, unverified, or not_needed",
                    "summary": "only the critical fact or uncertainty note",
                    "reader_visible": (
                        "true when the fact materially helps or conflicts"
                    ),
                }
            ],
            "reader_briefing": {
                "format": "wecom_narrative_v1",
                "title": "简短、自然中文的决策优先级标题",
                "thesis_order": (
                    "all must_surface thesis ids in exact priority order"
                ),
                "paragraphs": [
                    {
                        "kind": "kol or system",
                        "thesis_ids": (
                            "sequential thesis ids covered by this paragraph"
                        ),
                        "text": "coherent natural-language prose, never a table",
                    }
                ],
            },
        },
        "segments": segments,
    }


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_nonblank(value: Any, *, field: str) -> str:
    if not _nonblank(value):
        raise DecisionError(f"{field} must be nonblank")
    return str(value).strip()


def _validate_evidence_refs(
    thesis: dict[str, Any],
    *,
    segments_by_id: dict[str, dict[str, Any]],
    text: str,
) -> set[str]:
    refs = thesis.get("evidence_refs")
    thesis_id = str(thesis.get("thesis_id") or "<unknown>")
    if not isinstance(refs, list) or not refs:
        raise DecisionError(
            f"investment thesis requires evidence_refs: {thesis_id}"
        )
    linked_segments: set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            raise DecisionError(
                f"investment thesis evidence ref is invalid: {thesis_id}"
            )
        segment_id = str(ref.get("segment_id") or "")
        segment = segments_by_id.get(segment_id)
        if segment is None:
            raise DecisionError(
                f"investment thesis uses an unknown evidence segment: {thesis_id}"
            )
        quotes = ref.get("quotes")
        if (
            not isinstance(quotes, list)
            or not quotes
            or any(not _nonblank(quote) for quote in quotes)
        ):
            raise DecisionError(
                f"investment thesis evidence quotes are invalid: {thesis_id}"
            )
        segment_text = text[int(segment["start"]):int(segment["end"])]
        if any(str(quote) not in segment_text for quote in quotes):
            raise DecisionError(
                f"investment thesis quote is outside its segment: {thesis_id}"
            )
        linked_segments.add(segment_id)
    return linked_segments


def _validate_reader_briefing(
    item: dict[str, Any],
    *,
    must_surface: dict[str, dict[str, Any]],
) -> None:
    briefing = item.get("reader_briefing")
    if not must_surface:
        if briefing is not None and not isinstance(briefing, dict):
            raise DecisionError("reader_briefing must be an object")
        return
    if not isinstance(briefing, dict):
        raise DecisionError(
            "must-surface investment theses require reader_briefing"
        )
    if briefing.get("format") != "wecom_narrative_v1":
        raise DecisionError("reader_briefing format is invalid")
    _require_nonblank(briefing.get("title"), field="reader_briefing.title")
    ordered = briefing.get("thesis_order")
    if not isinstance(ordered, list):
        raise DecisionError("reader_briefing thesis_order must be a list")
    ordered_ids = [str(value) for value in ordered]
    expected_order = [
        thesis_id
        for thesis_id, _ in sorted(
            must_surface.items(),
            key=lambda row: int(row[1]["priority"]["rank"]),
        )
    ]
    if ordered_ids != expected_order:
        raise DecisionError(
            "reader_briefing must follow decision priority without omissions"
        )
    paragraphs = briefing.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        raise DecisionError("reader_briefing paragraphs are required")
    surfaced: list[str] = []
    must_ids = set(must_surface)
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            raise DecisionError("reader_briefing paragraph is invalid")
        kind = paragraph.get("kind")
        if kind not in {"kol", "system"}:
            raise DecisionError("reader_briefing paragraph kind is invalid")
        paragraph_text = _require_nonblank(
            paragraph.get("text"),
            field="reader_briefing paragraph text",
        )
        if _MARKDOWN_TABLE_SEPARATOR.search(paragraph_text):
            raise DecisionError("reader_briefing must not contain a table")
        thesis_ids = [str(value) for value in paragraph.get("thesis_ids") or []]
        if not set(thesis_ids).issubset(must_ids):
            raise DecisionError(
                "reader_briefing paragraph references an unknown thesis"
            )
        if kind == "kol":
            if not thesis_ids:
                raise DecisionError(
                    "reader_briefing KOL paragraph requires thesis_ids"
                )
            surfaced.extend(thesis_ids)
    if surfaced != ordered_ids or len(surfaced) != len(set(surfaced)):
        raise DecisionError(
            "every must-surface thesis must appear once in KOL reader prose"
        )


def validate_claim_coverage(
    item: dict[str, Any],
    *,
    evidence_text: str,
    evidence_sha256: str,
) -> dict[str, Any]:
    """Validate both semantic passes before reader or external effects."""
    expected_segments = evidence_segments(
        evidence_text,
        evidence_sha256=evidence_sha256,
    )
    segments_by_id = {
        str(segment["segment_id"]): segment
        for segment in expected_segments
    }
    inventory = item.get("investment_thesis_inventory")
    if not isinstance(inventory, dict):
        raise DecisionError("investment thesis inventory is required")
    if (
        inventory.get("contract_version") != CONTRACT_VERSION
        or inventory.get("evidence_sha256") != evidence_sha256
    ):
        raise DecisionError(
            "investment thesis inventory is not bound to current evidence"
        )
    theses = inventory.get("theses")
    if not isinstance(theses, list):
        raise DecisionError("investment thesis inventory theses must be a list")
    claim_ids = {
        str(claim.get("claim_id") or "")
        for claim in item.get("claims") or []
        if isinstance(claim, dict)
    }
    theses_by_id: dict[str, dict[str, Any]] = {}
    thesis_segments: dict[str, set[str]] = {}
    ranks: set[int] = set()
    for thesis in theses:
        if not isinstance(thesis, dict):
            raise DecisionError("investment thesis row is invalid")
        thesis_id = _require_nonblank(
            thesis.get("thesis_id"),
            field="investment thesis id",
        )
        if thesis_id in theses_by_id:
            raise DecisionError("investment thesis ids must be unique")
        role = thesis.get("role")
        if role not in MENTION_ROLES:
            raise DecisionError(
                f"investment thesis role is invalid: {thesis_id}"
            )
        relevance = thesis.get("decision_relevance")
        if relevance not in {"must_surface", "audit_only"}:
            raise DecisionError(
                f"investment thesis relevance is invalid: {thesis_id}"
            )
        importance = thesis.get("importance_basis")
        if (
            not isinstance(importance, list)
            or not set(importance).issubset(IMPORTANCE_BASES)
        ):
            raise DecisionError(
                f"investment thesis importance basis is invalid: {thesis_id}"
            )
        linked_claims = {
            str(value) for value in thesis.get("claim_ids") or []
        }
        if not linked_claims.issubset(claim_ids):
            raise DecisionError(
                f"investment thesis claim_ids are invalid: {thesis_id}"
            )
        if relevance == "must_surface":
            if not importance or not linked_claims:
                raise DecisionError(
                    f"must-surface thesis needs a basis and claim: {thesis_id}"
                )
            priority = thesis.get("priority")
            if not isinstance(priority, dict):
                raise DecisionError(
                    f"must-surface thesis priority is required: {thesis_id}"
                )
            rank = priority.get("rank")
            if (
                not isinstance(rank, int)
                or isinstance(rank, bool)
                or rank < 1
                or rank in ranks
                or priority.get("urgency") not in PRIORITY_LEVELS
                or priority.get("potential_impact") not in PRIORITY_LEVELS
                or priority.get("specificity") not in PRIORITY_LEVELS
                or priority.get("user_relevance")
                not in USER_RELEVANCE_LEVELS
                or not _nonblank(priority.get("reason"))
            ):
                raise DecisionError(
                    f"must-surface thesis priority is invalid: {thesis_id}"
                )
            ranks.add(rank)
        elif importance or role not in AUDIT_ONLY_ROLES:
            raise DecisionError(
                f"audit-only thesis has an unsafe role or importance: {thesis_id}"
            )
        for field in ("subject", "stance", "horizon", "attribution"):
            _require_nonblank(
                thesis.get(field),
                field=f"investment thesis {field}",
            )
        thesis_segments[thesis_id] = _validate_evidence_refs(
            thesis,
            segments_by_id=segments_by_id,
            text=evidence_text,
        )
        theses_by_id[thesis_id] = thesis

    audit = item.get("investment_thesis_coverage_audit")
    if not isinstance(audit, dict):
        raise DecisionError("investment thesis coverage audit is required")
    if (
        audit.get("contract_version") != CONTRACT_VERSION
        or audit.get("evidence_sha256") != evidence_sha256
        or audit.get("review_mode") != "independent_semantic_reread"
        or audit.get("status") != "passed"
    ):
        raise DecisionError(
            "investment thesis coverage audit is not a passing independent review"
        )
    findings = audit.get("findings")
    if (
        not isinstance(findings, dict)
        or set(findings)
        != {"missing_theses", "incorrect_merges", "role_errors"}
        or any(
            not isinstance(findings[field], list) or findings[field]
            for field in findings
        )
    ):
        raise DecisionError(
            "investment thesis coverage audit has unresolved findings"
        )
    reviews = audit.get("segment_reviews")
    if not isinstance(reviews, list):
        raise DecisionError(
            "investment thesis coverage audit segment reviews are required"
        )
    reviewed: dict[str, dict[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, dict):
            raise DecisionError("investment thesis segment review is invalid")
        segment_id = str(review.get("segment_id") or "")
        if segment_id not in segments_by_id or segment_id in reviewed:
            raise DecisionError(
                "investment thesis segment review identity is invalid"
            )
        disposition = review.get("disposition")
        if disposition not in AUDIT_DISPOSITIONS:
            raise DecisionError(
                "investment thesis segment disposition is invalid"
            )
        linked = {
            str(value) for value in review.get("thesis_ids") or []
        }
        if not linked.issubset(theses_by_id):
            raise DecisionError(
                "investment thesis segment review links an unknown thesis"
            )
        if disposition == "investment_content" and not linked:
            raise DecisionError(
                "investment content segment must link a thesis"
            )
        if disposition != "investment_content" and linked:
            raise DecisionError(
                "non-investment or advertisement segment cannot link a thesis"
            )
        _require_nonblank(
            review.get("reason"),
            field="investment thesis segment review reason",
        )
        reviewed[segment_id] = review
    if set(reviewed) != set(segments_by_id):
        raise DecisionError(
            "investment thesis coverage audit did not review every segment"
        )
    for thesis_id, linked_segments in thesis_segments.items():
        if any(
            reviewed[segment_id]["disposition"] != "investment_content"
            or thesis_id
            not in {
                str(value)
                for value in reviewed[segment_id].get("thesis_ids") or []
            }
            for segment_id in linked_segments
        ):
            raise DecisionError(
                f"investment thesis is not covered by the second pass: {thesis_id}"
            )

    must_surface = {
        thesis_id: thesis
        for thesis_id, thesis in theses_by_id.items()
        if thesis["decision_relevance"] == "must_surface"
    }
    expected_ranks = set(range(1, len(must_surface) + 1))
    if ranks != expected_ranks:
        raise DecisionError(
            "must-surface thesis priority ranks must be contiguous"
        )
    fact_checks = item.get("investment_thesis_fact_checks")
    if not isinstance(fact_checks, list):
        raise DecisionError("investment thesis fact checks are required")
    checked: dict[str, dict[str, Any]] = {}
    for row in fact_checks:
        if not isinstance(row, dict):
            raise DecisionError("investment thesis fact check is invalid")
        thesis_id = str(row.get("thesis_id") or "")
        if thesis_id not in must_surface or thesis_id in checked:
            raise DecisionError(
                "investment thesis fact check identity is invalid"
            )
        if row.get("status") not in FACT_CHECK_STATUSES:
            raise DecisionError(
                f"investment thesis fact check status is invalid: {thesis_id}"
            )
        _require_nonblank(
            row.get("summary"),
            field=f"investment thesis fact check summary: {thesis_id}",
        )
        if not isinstance(row.get("reader_visible"), bool):
            raise DecisionError(
                f"investment thesis fact check visibility is invalid: {thesis_id}"
            )
        if row.get("status") == "conflict" and row["reader_visible"] is not True:
            raise DecisionError(
                f"conflicting fact check must be reader-visible: {thesis_id}"
            )
        checked[thesis_id] = row
    if set(checked) != set(must_surface):
        raise DecisionError(
            "every must-surface thesis needs an independent fact-check status"
        )
    _validate_reader_briefing(item, must_surface=must_surface)
    return {
        "contract_version": CONTRACT_VERSION,
        "evidence_sha256": evidence_sha256,
        "segment_count": len(expected_segments),
        "thesis_count": len(theses_by_id),
        "must_surface_count": len(must_surface),
        "must_surface_thesis_ids": [
            thesis_id
            for thesis_id, _ in sorted(
                must_surface.items(),
                key=lambda row: int(row[1]["priority"]["rank"]),
            )
        ],
    }
