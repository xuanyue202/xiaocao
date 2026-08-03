from __future__ import annotations

import pytest

from xiaocao.kol.publication import (
    build_record,
    canonical_sha256,
    evaluation_id,
    record_content_sha256,
    stable_claim,
    viewpoint_id,
)
from xiaocao.kol.reader_copy import (
    ReaderCopyError,
    validate_reader_source_identity,
)
from xiaocao.kol.reader_copy_correction import (
    CORRECTION_AS_OF,
    LV_JULY_13_ORDER,
    LV_JULY_13_REPORT_ID,
    LV_JULY_13_REPORT_COPY,
    LV_JULY_20_ORDER,
    LV_JULY_20_REPORT_ID,
    LV_JULY_20_REPORT_COPY,
    build_lv_reader_copy_correction,
)


def _source_binding(report_id_value: str):
    return {
        "publication_id": f"fixture:{report_id_value}",
        "publication_version": "fixture-v1",
        "evidence_sha256": canonical_sha256(["evidence", report_id_value]),
        "decision_result_sha256": canonical_sha256(
            ["decision", report_id_value]
        ),
        "extraction_contract_version": "kol-investment-claims-v1",
    }


def test_reader_source_identity_rejects_conflicting_session_label():
    with pytest.raises(ReaderCopyError, match="session identity"):
        validate_reader_source_identity(
            source_name="20260803 盘前大师班直播8月3日-compressed.txt",
            reader_title="8月3日盘中大师班",
            report_body="# 核心判断\n\n本期盘中大师班强调控制仓位。",
        )


def test_reader_source_identity_allows_neutral_session_copy():
    validate_reader_source_identity(
        source_name="20260803 盘前大师班直播8月3日-compressed.txt",
        reader_title="8月3日大师班",
        report_body="# 核心判断\n\n本期直播强调控制仓位。",
    )


def test_reader_source_identity_ignores_later_intraday_warning():
    validate_reader_source_identity(
        source_name="20260803 盘前大师班直播8月3日-compressed.txt",
        reader_title="8月3日盘前大师班",
        report_body=(
            "# 核心判断\n\n盘前先确定低位优先纪律。\n\n"
            "## 风险提示\n\n若盘中预警出现，应继续控制仓位。"
        ),
    )


def _raw_machine_viewpoint(
    *,
    report_id_value: str,
    local_id: str,
    subject: str,
    stance: str,
    source_binding,
):
    refs = [
        {
            "claim_id": local_id,
            "segment_id": local_id,
            "excerpt": "来源观点证据",
        }
    ]
    record_id_value = viewpoint_id(report_id_value, local_id, refs)
    payload = {
        "viewpoint_id": record_id_value,
        "report_id": report_id_value,
        "kol_id": "kol-lv-xiaotong",
        "local_thesis_id": local_id,
        "subject": subject,
        "stance": stance,
        "source_published_at": "2026-07-20T00:00:00.000Z",
        "evidence_refs": refs,
        "horizon": "未来数月至长期",
        "attribution": "吕晓彤",
        "reasoning": "保留来源判断和风险边界。",
    }
    record = {
        "schema_version": 1,
        "kind": "viewpoint",
        "record_id": record_id_value,
        "idempotency_key": stable_claim("put", local_id, "old"),
        "created_at": "2026-07-26T10:00:00.000Z",
        "source_binding": source_binding,
        "payload": payload,
    }
    record["content_sha256"] = record_content_sha256(record)
    return record


def _current_publication(
    report_id_value: str,
    local_ids: list[str],
):
    source_binding = _source_binding(report_id_value)
    viewpoints = []
    evaluations = []
    for index, local_id in enumerate(local_ids):
        viewpoint = _raw_machine_viewpoint(
            report_id_value=report_id_value,
            local_id=local_id,
            subject=(
                "non-leveraged-tech-etf、individual-tech-equities"
                if index == 0
                else f"机器字段{index + 1}"
            ),
            stance="hold-with-conditions" if index == 0 else "结论需要纠正。",
            source_binding=source_binding,
        )
        viewpoints.append(viewpoint)
        status = "current" if index % 2 == 0 else "uncertain"
        evaluation_id_value = evaluation_id(
            viewpoint["record_id"],
            "2026-07-26T12:00:00.000Z",
            "2026-07-26T12:00:00.000Z",
        )
        evaluations.append(
            build_record(
                kind="viewpoint_evaluation",
                record_id_value=evaluation_id_value,
                idempotency_key=stable_claim(
                    "put",
                    local_id,
                    "old-evaluation",
                ),
                created_at="2026-07-26T12:00:00.000Z",
                source_binding=source_binding,
                payload={
                    "evaluation_id": evaluation_id_value,
                    "viewpoint_id": viewpoint["record_id"],
                    "status": status,
                    "as_of": "2026-07-26T12:00:00.000Z",
                    "evaluated_at": "2026-07-26T12:00:00.000Z",
                    "basis": "原来源观点仍按明确条件持续评估。",
                    "confidence": "medium",
                    "uncertainties": ["需要继续核对市场和基本面条件"],
                },
            )
        )
    report = build_record(
        kind="report",
        record_id_value=report_id_value,
        idempotency_key=stable_claim("put", report_id_value, "old-report"),
        created_at="2026-07-26T10:00:00.000Z",
        source_binding=source_binding,
        payload={
            "report_id": report_id_value,
            "report_kind": "publication_event",
            "kol_id": "kol-lv-xiaotong",
            "author": "吕晓彤",
            "source": "受审历史来源",
            "title": "吕晓彤历史直播",
            "summary": "保留来源观点并按当前条件持续评估。",
            "source_published_at": "2026-07-20T00:00:00.000Z",
            "media_types": ["video"],
            "source_parts": [],
            "report_format": "markdown",
            "report_body": "# 历史报告\n\n保留来源观点。",
            "viewpoint_ids": [
                viewpoint["record_id"] for viewpoint in viewpoints
            ],
            "alert_eligible": False,
            "alert_reason": "historical_initialization_no_alert",
            "reader_insight": {
                "status": "useful",
                "reason": "历史报告仍有检索价值",
            },
        },
    )
    return {
        "report": report,
        "records": [report, *viewpoints, *evaluations],
    }


def test_lv_reader_copy_correction_replaces_without_erasing_history():
    first = build_lv_reader_copy_correction(
        _current_publication(LV_JULY_13_REPORT_ID, LV_JULY_13_ORDER)
    )
    first_replacements = first["metadata"]["replacements"]
    second = build_lv_reader_copy_correction(
        _current_publication(LV_JULY_20_REPORT_ID, LV_JULY_20_ORDER),
        prior_replacements=first_replacements,
    )

    for candidate, expected_count in ((first, 5), (second, 3)):
        report = next(
            record
            for record in candidate["records"]
            if record["kind"] == "report"
        )
        corrected = [
            record
            for record in candidate["records"]
            if record["kind"] == "viewpoint"
            and record["payload"]["local_thesis_id"].endswith(
                "-reader-cn-v2"
            )
        ]
        invalidations = [
            record
            for record in candidate["records"]
            if record["kind"] == "viewpoint_evaluation"
            and record["payload"]["status"] == "invalidated"
            and record["payload"]["evaluated_at"] == CORRECTION_AS_OF
        ]
        replacements = [
            record
            for record in candidate["records"]
            if record["kind"] == "viewpoint_relation"
            and record["payload"]["relation_type"] == "replaces"
        ]

        assert len(corrected) == expected_count
        assert len(invalidations) == expected_count
        assert len(replacements) == expected_count
        assert report["payload"]["viewpoint_ids"][:expected_count] == [
            record["record_id"] for record in corrected
        ]
        assert report["payload"]["alert_eligible"] is False
        assert candidate["metadata"]["notification_claims_created"] == 0
        assert candidate["metadata"]["book_kol_us_replays"] == 0

    second_report = next(
        record for record in second["records"] if record["kind"] == "report"
    )
    second_relations = [
        record["payload"]
        for record in second["records"]
        if record["kind"] == "viewpoint_relation"
    ]
    assert second_report["payload"]["title"].startswith("吕晓彤 7月20日")
    assert all(
        "hold-with-conditions" not in record["payload"]["stance"]
        for record in second["records"]
        if record["kind"] == "viewpoint"
        and record["payload"]["local_thesis_id"].endswith("-reader-cn-v2")
    )
    assert len(
        [
            relation
            for relation in second_relations
            if relation["relation_type"] == "refines"
            and relation["asserted_at"] == CORRECTION_AS_OF
        ]
    ) == 2


def test_lv_reviewed_report_copy_uses_male_pronouns():
    for report in (LV_JULY_13_REPORT_COPY, LV_JULY_20_REPORT_COPY):
        assert "她" not in report["summary"]
        assert "她" not in report["report_body"]
        assert "他" in report["report_body"]
