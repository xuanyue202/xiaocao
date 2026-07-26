"""Build the reviewed initial LiangHui KOL publication set.

Historical material uses the same production contract as future events.  This
module never sends Enterprise WeChat messages or executes/replays Book actions.
It renders only safe, reader-facing reports and deliberately selected
longitudinal viewpoints.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .publication import (
    PublicationError,
    build_publish_request,
    build_record,
    evaluation_id,
    publication_id_for_source,
    report_id,
    stable_claim,
    viewpoint_id,
)


INITIAL_IMPORT_CREATED_AT = "2026-07-26T10:00:00.000Z"
INITIAL_EVALUATED_AT = "2026-07-26T10:00:00.000Z"
EXTRACTION_CONTRACT_VERSION = "kol-investment-claims-v1"
ADVERTISEMENT_TERMS = (
    "促销",
    "抽奖",
    "续费",
    "报课",
    "软件销售",
    "课程销售",
    "加微信",
)
KOL_REGISTRY = {
    "小草": "kol-xiaocao",
    "吕晓彤": "kol-lv-xiaotong",
    "路西法": "kol-lucifer",
}

LUCIFER_CURRENT = set()
XIAOCAO_CURRENT = {"do-not-trade-if-uncomprehended"}
LV_CURRENT = {
    "lv-20260720-remove-leverage",
    "lv-20260720-etf-versus-stock",
}
LV_LONGITUDINAL = {
    "lv-20260720-remove-leverage",
    "lv-20260720-etf-versus-stock",
    "lv-20260720-apple-pullback",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"invalid initial import artifact: {path}") from exc
    if not isinstance(value, dict):
        raise PublicationError(f"initial import artifact is not an object: {path}")
    return value


def _utc(value: str, *, date_only: bool = False) -> str:
    text = str(value or "").strip()
    if date_only:
        text = text + "T00:00:00+08:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PublicationError(f"invalid source time: {value}") from exc
    if parsed.tzinfo is None:
        raise PublicationError(f"source time lacks timezone: {value}")
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _safe_text(value: Any) -> str:
    text = re.sub(r"<[^>\n]+>", "", str(value or ""))
    return text.replace("<", "＜").replace(">", "＞").strip()


def _without_advertisements(value: Any) -> str:
    text = _safe_text(value)
    sentences = re.split(r"(?<=[。！？；])", text)
    kept = [
        sentence
        for sentence in sentences
        if sentence.strip()
        and not any(term in sentence for term in ADVERTISEMENT_TERMS)
    ]
    return "".join(kept).strip()


def _reader_title(value: Any) -> str:
    """Remove promotion-only parentheticals from a reader-facing title."""

    title = _safe_text(value).replace("morning_live", "盘前直播")
    for opening, closing in (("(", ")"), ("（", "）")):
        title = re.sub(
            re.escape(opening)
            + r"[^"
            + re.escape(closing)
            + r"]*(?:"
            + "|".join(re.escape(term) for term in ADVERTISEMENT_TERMS)
            + r")[^"
            + re.escape(closing)
            + r"]*"
            + re.escape(closing),
            "",
            title,
        )
    return re.sub(r"\s+", " ", title).strip(" ,，;；")


def _summary(value: Any, *, maximum: int = 1900) -> str:
    text = _without_advertisements(value)
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


def _candidate(
    *,
    publication_id: str,
    publication_version: str,
    kol_id: str,
    author: str,
    source: str,
    title: str,
    summary: str,
    source_published_at: str,
    media_types: list[str],
    source_parts: list[dict[str, Any]],
    report_body: str,
    evidence_sha256: str,
    decision_result_sha256: str,
    viewpoints: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    claim_revision: str | None = None,
) -> dict[str, Any]:
    report_id_value = report_id(publication_id)
    source_binding = {
        "publication_id": publication_id,
        "publication_version": publication_version,
        "evidence_sha256": evidence_sha256,
        "decision_result_sha256": decision_result_sha256,
        "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
    }
    records: list[dict[str, Any]] = []
    viewpoint_ids: list[str] = []
    for thesis in viewpoints or []:
        refs = thesis["evidence_refs"]
        viewpoint_id_value = viewpoint_id(
            report_id_value,
            thesis["local_thesis_id"],
            refs,
        )
        viewpoint_ids.append(viewpoint_id_value)
        viewpoint_payload = {
            "viewpoint_id": viewpoint_id_value,
            "report_id": report_id_value,
            "kol_id": kol_id,
            "local_thesis_id": thesis["local_thesis_id"],
            "subject": _safe_text(thesis["subject"]),
            "stance": _safe_text(thesis["stance"]),
            "source_published_at": source_published_at,
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
            if thesis.get(field) not in (None, "", []):
                viewpoint_payload[field] = thesis[field]
        records.append(
            build_record(
                kind="viewpoint",
                record_id_value=viewpoint_id_value,
                idempotency_key=stable_claim(
                    "put",
                    publication_id,
                    "viewpoint",
                    viewpoint_id_value,
                ),
                created_at=INITIAL_IMPORT_CREATED_AT,
                source_binding=source_binding,
                payload=viewpoint_payload,
            )
        )
        status = thesis["evaluation_status"]
        evaluation_id_value = evaluation_id(
            viewpoint_id_value,
            INITIAL_EVALUATED_AT,
            INITIAL_EVALUATED_AT,
        )
        evaluation_payload = {
            "evaluation_id": evaluation_id_value,
            "viewpoint_id": viewpoint_id_value,
            "status": status,
            "as_of": INITIAL_EVALUATED_AT,
            "evaluated_at": INITIAL_EVALUATED_AT,
            "basis": thesis["evaluation_basis"],
            "confidence": thesis.get("evaluation_confidence", "medium"),
            "uncertainties": thesis.get("evaluation_uncertainties", []),
        }
        records.append(
            build_record(
                kind="viewpoint_evaluation",
                record_id_value=evaluation_id_value,
                idempotency_key=stable_claim(
                    "put",
                    publication_id,
                    "evaluation",
                    evaluation_id_value,
                ),
                created_at=INITIAL_IMPORT_CREATED_AT,
                source_binding=source_binding,
                payload=evaluation_payload,
            )
        )
    report_payload = {
        "report_id": report_id_value,
        "report_kind": "publication_event",
        "kol_id": kol_id,
        "author": author,
        "source": source,
        "title": _safe_text(title),
        "summary": _summary(summary),
        "source_published_at": source_published_at,
        "media_types": media_types,
        "source_parts": source_parts,
        "report_format": "markdown",
        "report_body": _safe_text(report_body),
        "viewpoint_ids": viewpoint_ids,
        "alert_eligible": False,
        "alert_reason": "historical_initialization_no_alert",
        "reader_insight": {
            "status": "useful",
            "reason": "已受审历史报告，供家庭检索和达人观点时间线初始化",
        },
    }
    report = build_record(
        kind="report",
        record_id_value=report_id_value,
        idempotency_key=stable_claim(
            "put",
            publication_id,
            "report",
            decision_result_sha256,
            *([claim_revision] if claim_revision else []),
        ),
        created_at=INITIAL_IMPORT_CREATED_AT,
        source_binding=source_binding,
        payload=report_payload,
    )
    records.insert(0, report)
    publish = build_publish_request(
        records,
        idempotency_key=stable_claim(
            "publish",
            publication_id,
            decision_result_sha256,
            *([claim_revision] if claim_revision else []),
        ),
        reason="受审历史 KOL 报告初始化；不创建提醒、不重放 Book",
    )
    return {
        "publication_key": publication_id,
        "records": records,
        "publish_request": publish,
        "metadata": {
            "historical": True,
            "notification_claim_authorized": False,
            "book_kol_us_replay_authorized": False,
            "large_payload_local_bytes": 0,
            **(metadata or {}),
        },
    }


def _distilled_body(
    value: dict[str, Any],
    *,
    author: str,
    title: str,
) -> str:
    lines = [
        f"# {_safe_text(author)}｜{title}",
        "",
        "## 核心判断",
        "",
        _summary(value.get("summary")),
    ]
    posture = value.get("posture")
    if isinstance(posture, dict):
        dominant = _without_advertisements(posture.get("dominant_style"))
        risk = _without_advertisements(posture.get("risk"))
        if dominant or risk:
            lines.extend(["", "## 市场与风险姿态", ""])
            if dominant:
                lines.append(dominant)
            if risk:
                lines.extend(["", f"风险边界：{risk}"])
    directions = value.get("directions")
    if isinstance(directions, list) and directions:
        lines.extend(["", "## 关注方向", ""])
        for row in directions:
            if not isinstance(row, dict):
                continue
            name = _safe_text(row.get("name"))
            stance = _without_advertisements(row.get("stance"))
            if name and stance:
                lines.append(f"- {name}：{stance}")
    action = value.get("action_summary")
    if isinstance(action, dict):
        posture_update = _without_advertisements(action.get("posture_update"))
        playbook = _without_advertisements(action.get("playbook_update"))
        if posture_update or playbook:
            lines.extend(["", "## 系统边界与可复用判断", ""])
            if posture_update:
                lines.append(posture_update)
            if playbook:
                lines.extend(["", playbook])
    lines.extend(
        [
            "",
            "## 发布说明",
            "",
            "这是既有受审分析的历史初始化。报告仅供家庭快速检索，不重新发送提醒，也不重放任何 Book KOL-US 动作。",
        ]
    )
    return "\n".join(lines)


def _legacy_transcript(
    root: Path,
    distilled_path: Path,
    value: dict[str, Any],
) -> tuple[Path, str]:
    evidence = value.get("evidence")
    if isinstance(evidence, list) and evidence:
        raw_path = str(evidence[0].get("path") or "")
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise PublicationError(
                f"reviewed source evidence is missing: {distilled_path.name}"
            )
        expected = str(evidence[0].get("sha256") or "")
        actual = _sha256_file(path)
        if expected and expected != actual:
            raise PublicationError(
                f"reviewed evidence hash changed: {distilled_path.name}"
            )
        return path, actual
    date_token = str(value.get("date") or "").replace("-", "")
    session = "盘前" if distilled_path.stem.endswith("_morning") else "大师班专场"
    matches = sorted(
        path
        for path in (root / "reference/experience/transcripts").glob(
            f"*/{date_token}*.md"
        )
        if session in path.name
    )
    if len(matches) != 1:
        raise PublicationError(
            f"legacy evidence cannot be resolved exactly: {distilled_path.name}"
        )
    return matches[0], _sha256_file(matches[0])


def _distilled_candidate(root: Path, path: Path) -> dict[str, Any]:
    value = _json(path)
    if path.name == "2026-07-05_lucifer_review.json":
        raise PublicationError("superseded Lucifer distill must not be imported")
    author = str(value.get("author") or "小草")
    kol_id = KOL_REGISTRY.get(author)
    if not kol_id:
        raise PublicationError(f"unknown historical KOL: {author}")
    transcript, evidence_sha256 = _legacy_transcript(root, path, value)
    decision_sha256 = _sha256_file(path)
    date = str(value["date"])
    session = "morning" if path.stem.endswith("_morning") else "review"
    adapter = {
        "小草": "xiaocao_legacy_transcript",
        "吕晓彤": "lv_legacy_transcript",
    }[author]
    source_identity = hashlib.sha256(
        "\0".join((author, date, session, evidence_sha256)).encode()
    ).hexdigest()
    publication_id = publication_id_for_source(
        adapter=adapter,
        source_identity=source_identity,
    )
    source_time = _utc(date, date_only=True)
    title = _reader_title(f"{date} {_safe_text(value.get('kind'))}")
    return _candidate(
        publication_id=publication_id,
        publication_version=evidence_sha256,
        kol_id=kol_id,
        author=author,
        source="历史受审文稿",
        title=title,
        summary=value.get("summary", ""),
        source_published_at=source_time,
        media_types=["text"],
        source_parts=[
            {
                "identity": source_identity,
                "version": evidence_sha256,
                "order": 1,
                "size": transcript.stat().st_size,
                "evidence_sha256": evidence_sha256,
            }
        ],
        report_body=_distilled_body(value, author=author, title=title),
        evidence_sha256=evidence_sha256,
        decision_result_sha256=decision_sha256,
        metadata={
            "source_artifact": str(path.relative_to(root)),
            "longitudinal_records": 0,
        },
    )


def _gold_evidence_refs(thesis: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    claim_ids = [
        str(value)
        for value in thesis.get("claim_ids", [])
        if str(value).strip()
    ]
    for index, value in enumerate(thesis.get("evidence_refs", [])):
        if not isinstance(value, dict):
            continue
        quotes = value.get("quotes")
        excerpt = (
            str(quotes[0]).strip()
            if isinstance(quotes, list) and quotes
            else ""
        )
        segment_id = str(value.get("segment_id") or "").strip()
        if excerpt and segment_id:
            refs.append(
                {
                    "claim_id": claim_ids[min(index, len(claim_ids) - 1)]
                    if claim_ids
                    else thesis["thesis_id"],
                    "segment_id": segment_id,
                    "excerpt": _safe_text(excerpt),
                }
            )
    if not refs:
        raise PublicationError(
            f"longitudinal thesis lacks exact evidence: {thesis.get('thesis_id')}"
        )
    return refs


def _gold_viewpoints(
    value: dict[str, Any],
    *,
    author: str,
) -> list[dict[str, Any]]:
    inventory = (value.get("item") or {}).get("investment_thesis_inventory") or {}
    theses = inventory.get("theses") if isinstance(inventory, dict) else None
    if not isinstance(theses, list):
        return []
    selected: list[dict[str, Any]] = []
    for thesis in theses:
        if not isinstance(thesis, dict):
            continue
        priority = thesis.get("priority") or {}
        if (
            thesis.get("decision_relevance") != "must_surface"
            or priority.get("potential_impact") != "high"
        ):
            continue
        local_id = str(thesis.get("thesis_id") or "")
        current = (
            local_id in XIAOCAO_CURRENT
            if author == "小草"
            else local_id in LUCIFER_CURRENT
        )
        basis = (
            "该结论是跨行情适用的停止条件，当前仍有独立风险控制价值；"
            "状态不代表系统认可任何具体买卖。"
            if current
            else "原始观点影响较大，但截至本次初始化缺少足以覆盖其触发、"
            "价格和基本面条件的最新完整复核，因此不把它自动列为当前有效。"
        )
        selected.append(
            {
                "local_thesis_id": local_id,
                "subject": thesis.get("subject"),
                "stance": thesis.get("stance"),
                "horizon": thesis.get("horizon"),
                "attribution": thesis.get("attribution") or author,
                "role": thesis.get("role"),
                "evidence_refs": _gold_evidence_refs(thesis),
                "evaluation_status": "current" if current else "uncertain",
                "evaluation_basis": basis,
                "evaluation_confidence": "high" if current else "medium",
                "evaluation_uncertainties": []
                if current
                else ["需要结合最新市场、基本面及原始触发条件重新评估"],
            }
        )
    return selected


def _gold_body(value: dict[str, Any]) -> str:
    item = value["item"]
    title = (
        (item.get("reader_briefing") or {}).get("title")
        or item.get("title")
        or "KOL 投资情报"
    )
    message = _without_advertisements(value.get("reader_message"))
    return "\n".join(
        (
            f"# {_safe_text(title)}",
            "",
            message,
            "",
            "## 发布说明",
            "",
            "这是已通过完整性审计的历史报告。报告发布不代表重新提醒，也不会重放任何 Book KOL-US 动作。",
        )
    )


def _gold_candidate(
    root: Path,
    path: Path,
    *,
    author: str,
    adapter: str,
    source_identity: str,
    publication_version: str,
    source_parts: list[dict[str, Any]],
    claim_revision: str | None = None,
    source_artifact: str | None = None,
) -> dict[str, Any]:
    value = _json(path)
    item = value["item"]
    if item.get("author") != author:
        raise PublicationError(f"gold author mismatch: {path.name}")
    evidence_sha256 = str(item.get("evidence_sha256") or "")
    if evidence_sha256 != (value.get("validation") or {}).get("evidence_sha256"):
        raise PublicationError(f"gold evidence hash mismatch: {path.name}")
    viewpoints = (
        []
        if path.name.startswith("lv_20260723_image")
        else _gold_viewpoints(value, author=author)
    )
    publication_id = publication_id_for_source(
        adapter=adapter,
        source_identity=source_identity,
    )
    briefing = item.get("reader_briefing") or {}
    paragraphs = briefing.get("paragraphs")
    first_paragraph = (
        paragraphs[0].get("text")
        if isinstance(paragraphs, list)
        and paragraphs
        and isinstance(paragraphs[0], dict)
        else value.get("reader_message")
    )
    return _candidate(
        publication_id=publication_id,
        publication_version=publication_version,
        kol_id=KOL_REGISTRY[author],
        author=author,
        source={
            "subscription_video": "订阅云端视频",
            "xiaocao_live": "小草直播",
            "lv_text_image": "订阅图片",
        }[adapter],
        title=briefing.get("title") or item.get("title"),
        summary=first_paragraph,
        source_published_at=_utc(item["published_at"]),
        media_types=["image" if "image" in path.name else "video"],
        source_parts=source_parts,
        report_body=_gold_body(value),
        evidence_sha256=evidence_sha256,
        decision_result_sha256=_sha256_file(path),
        viewpoints=viewpoints,
        metadata={
            "source_artifact": (
                source_artifact
                if source_artifact is not None
                else str(path.relative_to(root))
            ),
            "longitudinal_records": len(viewpoints),
        },
        claim_revision=claim_revision,
    )


def _lv_video_candidate(
    root: Path,
    reviewed_artifact_root: Path,
) -> dict[str, Any]:
    source_artifact = (
        "output/live/kol_subscription_videos/enrichment/"
        "051231a20050519b6514a8d566f2473e6135be3095f32abf8f22b3506ca51aac/"
        "artifacts/kol-netdisk-cloud-d5f607550bbd9dee/decision_result.json"
    )
    result_path = reviewed_artifact_root / source_artifact
    value = _json(result_path)
    item = value["items"][0]
    claims = {
        str(row["claim_id"]): row
        for row in item.get("claims", [])
        if isinstance(row, dict) and row.get("claim_id")
    }
    viewpoints = []
    for claim_id in sorted(LV_LONGITUDINAL):
        claim = claims[claim_id]
        current = claim_id in LV_CURRENT
        viewpoints.append(
            {
                "local_thesis_id": claim_id,
                "subject": "、".join(
                    str(value)
                    for value in claim.get("asset_scope", [])
                )
                or claim_id,
                "stance": claim.get("direction"),
                "horizon": claim.get("horizon"),
                "attribution": "吕晓彤",
                "role": "primary_recommendation",
                "reasoning": _safe_text(claim.get("reasoning")),
                "falsifiers": [
                    _safe_text(row) for row in claim.get("falsifiers", [])
                ],
                "evidence_refs": [
                    {
                        "claim_id": claim_id,
                        "segment_id": claim_id,
                        "excerpt": _safe_text(claim.get("quote")),
                    }
                ],
                "evaluation_status": "current" if current else "uncertain",
                "evaluation_basis": (
                    "该结论约束的是杠杆工具或 ETF/个股的结构差异，"
                    "不依赖单日涨跌，当前仍可作为风险控制原则。"
                    if current
                    else "原观点缺少当前价格、估值与明确入场条件，"
                    "不能因未出现反例而自动视为当前有效。"
                ),
                "evaluation_confidence": "high" if current else "medium",
                "evaluation_uncertainties": []
                if current
                else ["缺少当前价格、估值和入场触发复核"],
            }
        )
    market = item.get("market_outlook") or {}
    synthesis = item.get("system_synthesis") or {}
    signals = item.get("actionable_signals") or []
    lines = [
        "# 投资情报｜吕晓彤 7 月 20 日直播",
        "",
        "## KOL 关键观点",
        "",
    ]
    for claim in claims.values():
        lines.append(
            f"- {_safe_text(claim.get('quote'))}。"
            f"{_safe_text(claim.get('reasoning'))}"
        )
    lines.extend(
        [
            "",
            "## 市场与系统判断",
            "",
            _safe_text(market.get("base_case")),
            "",
            _safe_text(synthesis.get("summary")),
            "",
            "## 与家庭决策相关",
            "",
        ]
    )
    for signal in signals:
        lines.append(
            f"- {_safe_text(signal.get('execution'))}"
            f"  边界：{_safe_text(signal.get('trigger'))}"
        )
    book = item.get("book_kol_us") or {}
    lines.extend(
        [
            "",
            "## Book KOL-US",
            "",
            f"纸面结果：{_safe_text(book.get('status'))}。"
            f"{_safe_text(book.get('reason'))}",
            "",
            "## 发布说明",
            "",
            "这是既有受审分析的历史初始化，不重新发送提醒，也不重放纸面动作。",
        ]
    )
    source_identity = (
        "687cebb7eece471b7d71d6043324059d2ace729d1debe1e0fd05ec4ef3091f4a"
    )
    version = (
        "051231a20050519b6514a8d566f2473e6135be3095f32abf8f22b3506ca51aac"
    )
    evidence_sha256 = str(item["evidence_sha256"])
    reader_summary = (
        synthesis.get("summary")
        or market.get("base_case")
        or next(
            (
                claim.get("quote")
                for claim in claims.values()
                if claim.get("quote")
            ),
            None,
        )
    )
    return _candidate(
        publication_id=publication_id_for_source(
            adapter="subscription_video",
            source_identity=source_identity,
        ),
        publication_version=version,
        kol_id=KOL_REGISTRY["吕晓彤"],
        author="吕晓彤",
        source="订阅云端视频",
        title="投资情报｜吕晓彤 7 月 20 日直播",
        summary=reader_summary,
        source_published_at=_utc(item["published_at"]),
        media_types=["video"],
        source_parts=[
            {
                "identity": source_identity,
                "version": version,
                "order": 1,
                "size": 3682235122,
                "evidence_sha256": evidence_sha256,
            }
        ],
        report_body="\n".join(lines),
        evidence_sha256=evidence_sha256,
        decision_result_sha256=_sha256_file(result_path),
        viewpoints=viewpoints,
        metadata={
            "source_artifact": source_artifact,
            "longitudinal_records": len(viewpoints),
        },
        claim_revision="nonempty-reader-summary-v1",
    )


def initial_import_candidates(
    root: Path | str,
    *,
    reviewed_artifact_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    project = Path(root).expanduser().resolve()
    reviewed = (
        project
        if reviewed_artifact_root is None
        else Path(reviewed_artifact_root).expanduser().resolve()
    )
    candidates = []
    for path in sorted(
        (project / "reference/experience/distilled").glob("*.json")
    ):
        if path.name == "2026-07-05_lucifer_review.json":
            continue
        candidates.append(_distilled_candidate(project, path))

    lucifer_artifact = (
        "output/live/kol_subscription_videos/review/"
        "lucifer_20260705_claim_gold_v4.json"
    )
    candidates.append(
        _gold_candidate(
            project,
            reviewed / lucifer_artifact,
            author="路西法",
            adapter="subscription_video",
            source_identity=(
                "9fc5ed7f825ff6a3dea9ccff39ae382e521a0d777a673e6fad5a45a1c7da2b73"
            ),
            publication_version=(
                "c4ea2e58009b9d3fc193006b7fdffd8b0bb914ac7da64bb3d82dc1c8f8be265e"
            ),
            source_parts=[
                {
                    "identity": (
                        "25088415af14905aa1da82072b668db34278f21817fe868650a4efb04d4cc048"
                    ),
                    "version": (
                        "cf3c98d35feba8a6b34bdd51cbd5a21a7b71278f50a126cbc3a7a8c0d2770a2a"
                    ),
                    "order": 1,
                    "label": "一",
                    "size": 759800380,
                    "evidence_sha256": (
                        "9979e52faead7f453962ba3af7291fc7deaecb7e23f8174633ae0700710efb0b"
                    ),
                },
                {
                    "identity": (
                        "1d33d6886adccc3b8558c5886f7362d55789fcb2fcbe8f323d9d699731a47a48"
                    ),
                    "version": (
                        "aaa96795b8bc03bee3aff82a05b9fb4e8131b66d0edffb22f18c0e62dd7a37f3"
                    ),
                    "order": 2,
                    "label": "二",
                    "size": 578859389,
                    "evidence_sha256": (
                        "c482a8d29e7793e03454847f1e31c8fcf5cd7e6bd32227464dda232af155418c"
                    ),
                },
                {
                    "identity": (
                        "d972ce2110cfa389be9e688090caaebb05fb87330a6b3f847a39bf19e4ea20eb"
                    ),
                    "version": (
                        "bf3a1583dea8da417cf3afa80287ca74848dec36888db62abc119eb635c41208"
                    ),
                    "order": 3,
                    "label": "三",
                    "size": 744292790,
                    "evidence_sha256": (
                        "eb50136f8f5edc41169e0a1c5b5321ce0266c23de6c0244d7d3c02bbaace2498"
                    ),
                },
            ],
            claim_revision="source-part-evidence-fix-v1",
            source_artifact=lucifer_artifact,
        )
    )
    candidates.append(_lv_video_candidate(project, reviewed))
    lv_image_artifact = (
        "output/live/kol_lv_subscription/review/"
        "lv_20260723_image_claim_gold_v1.json"
    )
    candidates.append(
        _gold_candidate(
            project,
            reviewed / lv_image_artifact,
            author="吕晓彤",
            adapter="lv_text_image",
            source_identity=(
                "b5579f1a34e9872aaadad52514ea6564c2b034f60797cd7ac8fbbb331dc1a73a"
            ),
            publication_version=(
                "681d609740831e17b9a49e3cdd0d6b3dc08516970df0120932464b8650447e6d"
            ),
            source_parts=[
                {
                    "identity": (
                        "b5579f1a34e9872aaadad52514ea6564c2b034f60797cd7ac8fbbb331dc1a73a"
                    ),
                    "version": (
                        "681d609740831e17b9a49e3cdd0d6b3dc08516970df0120932464b8650447e6d"
                    ),
                    "order": 1,
                    "label": "17.png",
                    "size": 0,
                    "evidence_sha256": (
                        "10bf2839cb777d3f507b15db9d9b3eac9f9f17fa12e93dcd82fca11841d49f79"
                    ),
                }
            ],
            source_artifact=lv_image_artifact,
        )
    )
    xiaocao_artifact = (
        "output/live/kol_netdisk_enrichment/review/"
        "xiaocao_20260724_claim_gold_v1.json"
    )
    candidates.append(
        _gold_candidate(
            project,
            reviewed / xiaocao_artifact,
            author="小草",
            adapter="xiaocao_live",
            source_identity="kol-d141475ad2a9",
            publication_version=(
                "ac3939f5f949cf47e05b90680bca91393fd7e249e62f69f6dfbec7735f9815b2"
            ),
            source_parts=[
                {
                    "identity": "kol-d141475ad2a9",
                    "version": (
                        "ac3939f5f949cf47e05b90680bca91393fd7e249e62f69f6dfbec7735f9815b2"
                    ),
                    "order": 1,
                    "size": 208016619,
                    "evidence_sha256": (
                        "ff0556df3d35414bf33b18fa6ef1543ed210d901bda2c77c420990526092d75b"
                    ),
                }
            ],
            source_artifact=xiaocao_artifact,
        )
    )
    identities = [candidate["publication_key"] for candidate in candidates]
    if len(identities) != len(set(identities)):
        raise PublicationError("initial import contains duplicate publication events")
    return sorted(candidates, key=lambda row: row["publication_key"])
