from __future__ import annotations

import json

import pytest

from xiaocao.kol.household import LiangHuiMcpError
from xiaocao.kol.publication import (
    PublicationLedger,
    PublicationError,
    build_append_only_publication_update,
    build_publish_request,
    build_record,
    canonical_bytes,
    canonical_sha256,
    evaluation_id,
    manifest_entries,
    manifest_sha256,
    publication_id_for_source,
    relation_id,
    read_published_publication,
    report_id,
    stable_claim,
    viewpoint_id,
    publication_thesis_id,
    _rebind_short_theses,
)


PUBLICATION_ID = "youtube:channel-42:live-2026-07-26"
REPORT_ID = "kr_yrig6moiwytxfdahs44c5sa3qvda3pjgprcdehigqti72p3m2gxq"
INITIAL_CONTENT_SHA256 = (
    "98634db75f90efe0ad838780074a7f6a6c8364d73d5fc7c93843769e3be7272a"
)
INITIAL_MANIFEST_SHA256 = (
    "a077cd76862bb60660f18cf87bb470e387241887fc9b94c61e22c9395623812b"
)


def _initial_report():
    source_binding = {
        "publication_id": PUBLICATION_ID,
        "publication_version": "episode-v3",
        "evidence_sha256": "a" * 64,
        "decision_result_sha256": "b" * 64,
        "extraction_contract_version": "kol-intelligence-v1",
    }
    return build_record(
        kind="report",
        record_id_value=REPORT_ID,
        idempotency_key="put-contract-report-v1",
        created_at="2026-07-26T08:00:00.000Z",
        source_binding=source_binding,
        payload={
            "report_id": REPORT_ID,
            "report_kind": "publication_event",
            "kol_id": "kol-lucifer",
            "author": "路西法",
            "source": "订阅直播",
            "title": "利率与科技股估值",
            "summary": "等待赔率改善，不把单次反弹视为趋势确认。",
            "source_published_at": "2026-07-26T07:30:00.000Z",
            "media_types": ["video"],
            "source_parts": [
                {
                    "identity": "provider-video-1",
                    "version": "cloud-v3",
                    "order": 1,
                    "size": 0,
                    "evidence_sha256": "c" * 64,
                },
                {
                    "identity": "provider-video-2",
                    "version": "cloud-v3",
                    "order": 2,
                    "size": 0,
                    "evidence_sha256": "d" * 64,
                },
            ],
            "report_format": "markdown",
            "report_body": "# 核心判断\n\n当前更适合等待估值和利率条件改善。",
            "viewpoint_ids": [],
            "alert_eligible": False,
            "alert_reason": "historical_notification_reconciled",
            "reader_insight": {
                "status": "useful",
                "reason": "内容仍有长期参考价值",
            },
        },
    )


def test_cross_language_contract_ids_content_and_manifest_are_frozen():
    report = _initial_report()
    assert report_id(PUBLICATION_ID) == REPORT_ID
    assert canonical_bytes(
        {
            "z": "中文",
            "a": [1, True, None],
        }
    ) == b'{"a":[1,true,null],"z":"\xe4\xb8\xad\xe6\x96\x87"}'
    assert report["content_sha256"] == INITIAL_CONTENT_SHA256
    request = build_publish_request(
        [report],
        idempotency_key="publish-contract-v1",
        reason="首次发布",
    )
    assert request["manifest_sha256"] == INITIAL_MANIFEST_SHA256
    assert manifest_sha256(request["records"]) == INITIAL_MANIFEST_SHA256


def test_publication_record_requires_created_at_in_utc_z():
    report = _initial_report()

    with pytest.raises(PublicationError, match="UTC ISO-8601 ending in Z"):
        build_record(
            kind="report",
            record_id_value=REPORT_ID,
            idempotency_key="put-non-utc-created-at",
            created_at="2026-08-03T14:00:00+08:00",
            source_binding=report["source_binding"],
            payload=report["payload"],
        )


@pytest.mark.parametrize("author", ["吕晓彤", "路西法", "小草"])
def test_male_kol_report_rejects_feminine_author_pronoun(author):
    payload = dict(_initial_report()["payload"])
    payload.update(
        {
            "author": author,
            "summary": f"{author}认为科技仍有机会，她会等待条件确认。",
        }
    )

    with pytest.raises(
        Exception,
        match=f"{author}.*他.*她",
    ):
        build_record(
            kind="report",
            record_id_value=REPORT_ID,
            idempotency_key="put-wrong-author-pronoun",
            created_at="2026-07-26T08:00:00.000Z",
            source_binding=_initial_report()["source_binding"],
            payload=payload,
        )


def test_cross_language_longitudinal_ids_are_frozen():
    first_refs = [
        {
            "claim_id": "claim-7",
            "excerpt": "等待估值回落",
            "segment_id": "segment-3",
        }
    ]
    first = viewpoint_id(REPORT_ID, "thesis-growth", first_refs)
    second = viewpoint_id(
        REPORT_ID,
        "thesis-rates",
        [
            {
                "claim_id": "claim-9",
                "excerpt": "若利率回落可逐步观察",
                "segment_id": "segment-5",
            }
        ],
    )
    assert first == "vp_wbis3lqnnjyxu4h7iub7gdkivauczffg4s7mu4dojmauew4ra55q"
    assert second == "vp_4a365owrcqmi4bm5uw5g2h62d5mokkuowxcazhqanaqx6lmschzq"
    assert evaluation_id(
        first,
        "2026-07-26T08:20:00.000Z",
        "2026-07-26T08:25:00.000Z",
    ) == "ve_3ficfnqvx63zhggf66w5mfvxbbtaxzfrkyviljne4e5a5oqfhguq"
    assert relation_id(
        second,
        first,
        "refines",
        "2026-07-26T08:26:00.000Z",
    ) == "vr_tjwp6oyt2qoe47lwjqvg5ubjlrhlp32q7q6jsophup27274yldoa"


def _viewpoint(report):
    refs = [
        {
            "claim_id": "claim-7",
            "segment_id": "segment-3",
            "excerpt": "等待估值回落",
        }
    ]
    record_id_value = viewpoint_id(
        report["record_id"],
        "thesis-growth",
        refs,
    )
    return build_record(
        kind="viewpoint",
        record_id_value=record_id_value,
        idempotency_key="put-viewpoint-v1",
        created_at="2026-07-26T08:20:00.000Z",
        source_binding=report["source_binding"],
        payload={
            "viewpoint_id": record_id_value,
            "report_id": report["record_id"],
            "kol_id": report["payload"]["kol_id"],
            "local_thesis_id": "thesis-growth",
            "subject": "科技股估值",
            "stance": "等待估值回落后再观察",
            "source_published_at": report["payload"]["source_published_at"],
            "evidence_refs": refs,
        },
    )


def test_append_only_update_preserves_report_and_uses_double_cas():
    current = _initial_report()
    viewpoint = _viewpoint(current)

    records, publish = build_append_only_publication_update(
        current_records=[current],
        additions=[viewpoint],
        viewpoint_ids=[viewpoint["record_id"]],
        created_at="2026-07-26T08:25:00.000Z",
        revision="review-v1",
        reason="补充长期观点",
    )
    report = next(record for record in records if record["kind"] == "report")

    assert report["record_id"] == current["record_id"]
    assert report["payload"]["report_body"] == current["payload"]["report_body"]
    assert report["payload"]["alert_eligible"] is False
    assert report["expected_content_sha256"] == current["content_sha256"]
    assert report["payload"]["viewpoint_ids"] == [viewpoint["record_id"]]
    assert publish["expected_content_sha256"] == current["content_sha256"]
    assert publish["expected_manifest_sha256"] == INITIAL_MANIFEST_SHA256
    assert publish["records"] == manifest_entries(records)


def test_append_only_update_can_correct_reader_copy_without_stable_field_change():
    current = _initial_report()

    records, publish = build_append_only_publication_update(
        current_records=[current],
        additions=[],
        viewpoint_ids=[],
        created_at="2026-07-26T08:25:00.000Z",
        revision="reader-copy-v1",
        reason="纠正读者文案",
        report_payload_updates={
            "title": "利率变化与科技股估值",
            "summary": "等待估值和利率条件改善，不把一次反弹当成趋势确认。",
            "report_body": "# 核心判断\n\n等待估值和利率条件改善。",
        },
    )
    report = records[0]

    assert report["record_id"] == current["record_id"]
    assert report["payload"]["kol_id"] == current["payload"]["kol_id"]
    assert report["payload"]["title"] == "利率变化与科技股估值"
    assert report["expected_content_sha256"] == current["content_sha256"]
    assert publish["expected_content_sha256"] == current["content_sha256"]
    assert publish["expected_manifest_sha256"] == INITIAL_MANIFEST_SHA256


def test_append_only_update_can_promote_a_misclassified_live_alert():
    current = _initial_report()

    records, publish = build_append_only_publication_update(
        current_records=[current],
        additions=[],
        viewpoint_ids=[],
        created_at="2026-07-26T08:25:00.000Z",
        revision="alert-eligibility-correction-v1",
        reason="纠正实时投资情报提醒资格",
        report_payload_updates={
            "alert_eligible": True,
            "alert_reason": "permissive_live_investment_content_gate",
        },
    )
    report = records[0]

    assert report["record_id"] == current["record_id"]
    assert report["payload"]["alert_eligible"] is True
    assert report["payload"]["alert_reason"] == (
        "permissive_live_investment_content_gate"
    )
    assert report["expected_content_sha256"] == current["content_sha256"]
    assert publish["expected_content_sha256"] == current["content_sha256"]
    assert publish["expected_manifest_sha256"] == INITIAL_MANIFEST_SHA256


@pytest.mark.parametrize(
    "updates",
    [
        {"alert_eligible": True},
        {"alert_reason": "permissive_live_investment_content_gate"},
        {"alert_eligible": False, "alert_reason": "historical"},
        {"alert_eligible": True, "alert_reason": "ad_hoc_override"},
    ],
)
def test_alert_eligibility_correction_fails_closed(updates):
    with pytest.raises(PublicationError, match="alert eligibility|canonical live"):
        build_append_only_publication_update(
            current_records=[_initial_report()],
            additions=[],
            viewpoint_ids=[],
            created_at="2026-07-26T08:25:00.000Z",
            revision="bad-alert-correction",
            reason="非法更改提醒资格",
            report_payload_updates=updates,
        )


def test_reader_copy_gate_is_source_neutral_and_allows_only_formal_ascii_subjects():
    report = _initial_report()
    common = {
        "viewpoint_id": "vp-reader-copy",
        "report_id": report["record_id"],
        "kol_id": "kol-any-author",
        "local_thesis_id": "reader-copy-test",
        "source_published_at": report["payload"]["source_published_at"],
        "evidence_refs": [
            {
                "claim_id": "claim-reader-copy",
                "segment_id": "segment-reader-copy",
                "excerpt": "来源证据",
            }
        ],
    }

    for subject, stance in (
        ("non-leveraged-tech-etf、individual-tech-equities", "继续观察"),
        ("任意行业", "hold-with-conditions"),
        ("another_machine_tag", "降低风险暴露"),
    ):
        with pytest.raises(
            Exception,
            match="machine token|natural Chinese",
        ):
            build_record(
                kind="viewpoint",
                record_id_value="vp-reader-copy",
                idempotency_key="put-reader-copy",
                created_at="2026-07-26T08:20:00.000Z",
                source_binding=report["source_binding"],
                payload={
                    **common,
                    "subject": subject,
                    "stance": stance,
                },
            )

    for subject, stance in (
        ("SpaceX", "等待明确时间和仓位条件后再评估。"),
        ("苹果（AAPL）", "等待价格与估值形成安全边际后再观察。"),
        ("非杠杆科技ETF", "保留长期方向，但不使用杠杆产品。"),
    ):
        record = build_record(
            kind="viewpoint",
            record_id_value="vp-reader-copy",
            idempotency_key="put-reader-copy",
            created_at="2026-07-26T08:20:00.000Z",
            source_binding=report["source_binding"],
            payload={
                **common,
                "subject": subject,
                "stance": stance,
            },
        )
        assert record["content_sha256"]


def test_report_reader_copy_rejects_transport_titles_and_internal_actions():
    report = _initial_report()

    with pytest.raises(Exception, match="reader title|transport filename"):
        build_record(
            kind="report",
            record_id_value=report["record_id"],
            idempotency_key="put-raw-title",
            created_at=report["created_at"],
            source_binding=report["source_binding"],
            payload={
                **report["payload"],
                "title": "20260802 大师班专场-compressed.mp4",
            },
        )

    with pytest.raises(Exception, match="internal action label"):
        build_record(
            kind="report",
            record_id_value=report["record_id"],
            idempotency_key="put-internal-actions",
            created_at=report["created_at"],
            source_binding=report["source_binding"],
            payload={
                **report["payload"],
                "report_body": "# 系统结论\n\n家庭动作 wait；Book KOL-US 为 no_trade。",
            },
        )


def test_append_only_update_rejects_silent_viewpoint_omission():
    current = _initial_report()
    viewpoint = _viewpoint(current)

    with pytest.raises(Exception, match="viewpoint_ids"):
        build_append_only_publication_update(
            current_records=[current],
            additions=[viewpoint],
            viewpoint_ids=[],
            created_at="2026-07-26T08:25:00.000Z",
            revision="review-v1",
            reason="补充长期观点",
        )


class _ReadLiangHui:
    def __init__(self, records):
        self.records = {
            (record["kind"], record["record_id"], record["content_sha256"]): record
            for record in records
        }
        self.manifest = manifest_entries(records)
        self.manifest_sha256 = manifest_sha256(self.manifest)

    def call_tool(self, name, arguments):
        assert name == "get_kol_record"
        if arguments["kind"] == "report":
            record = next(
                record
                for (kind, _, _), record in self.records.items()
                if kind == "report"
            )
            return {
                **record,
                "state": "published",
                "manifest": self.manifest,
                "manifest_sha256": self.manifest_sha256,
                "published_at": "2026-07-26T08:30:00.000Z",
                "updated_at": "2026-07-26T08:30:00.000Z",
            }
        key = (
            arguments["kind"],
            arguments["record_id"],
            arguments["content_sha256"],
        )
        return self.records[key]


def test_published_manifest_can_be_read_back_for_future_maintenance():
    report = _initial_report()
    viewpoint = _viewpoint(report)
    report, _ = build_append_only_publication_update(
        current_records=[report],
        additions=[viewpoint],
        viewpoint_ids=[viewpoint["record_id"]],
        created_at="2026-07-26T08:25:00.000Z",
        revision="review-v1",
        reason="补充长期观点",
    )
    client = _ReadLiangHui(report)

    actual = read_published_publication(client, REPORT_ID)

    assert manifest_entries(actual["records"]) == manifest_entries(report)
    assert actual["report"]["payload"] == report[0]["payload"]
    assert actual["manifest_sha256"] == manifest_sha256(
        manifest_entries(report)
    )


class _FakeLiangHui:
    def __init__(self):
        self.receipts = {}
        self.write_calls = []
        self.raise_after_first_put = True

    def call_tool(self, name, arguments):
        if name == "get_kol_write_status":
            receipt = self.receipts.get(arguments["idempotency_key"])
            if receipt is None:
                raise LiangHuiMcpError(
                    "missing",
                    code="NOT_FOUND",
                )
            return receipt
        self.write_calls.append((name, arguments))
        if name == "put_kol_record":
            receipt = {
                "operation": name,
                "idempotencyKey": arguments["idempotency_key"],
                "actor": "agent",
                "familyId": "family",
                "kind": arguments["kind"],
                "recordId": arguments["record_id"],
                "contentSha256": arguments["content_sha256"],
                "result": "created",
                "serverTime": "2026-07-26T08:30:00.000Z",
                "recordState": "staged",
            }
            self.receipts[arguments["idempotency_key"]] = receipt
            if self.raise_after_first_put:
                self.raise_after_first_put = False
                raise OSError("connection closed after durable write")
            return receipt
        receipt = {
            "operation": name,
            "idempotencyKey": arguments["idempotency_key"],
            "actor": "agent",
            "familyId": "family",
            "recordId": arguments["report_id"],
            "contentSha256": arguments["report_content_sha256"],
            "result": "created",
            "serverTime": "2026-07-26T08:31:00.000Z",
            "recordState": "published",
            "manifestSha256": arguments["manifest_sha256"],
            "detailPath": f"/kol-reports/{arguments['report_id']}",
            "detailUrl": f"https://example.test/kol-reports/{arguments['report_id']}",
        }
        self.receipts[arguments["idempotency_key"]] = receipt
        return receipt


class _ExpiredClaimLiangHui(_FakeLiangHui):
    def __init__(self, original_claim):
        super().__init__()
        self.raise_after_first_put = False
        self.receipts[original_claim] = {
            "operation": "put_kol_record",
            "idempotencyKey": original_claim,
            "actor": "agent",
            "familyId": "family",
            "kind": "report",
            "recordId": REPORT_ID,
            "contentSha256": INITIAL_CONTENT_SHA256,
            "result": "created",
            "serverTime": "2026-07-25T08:30:00.000Z",
            "recordState": "expired_or_missing",
        }


def test_uncertain_write_is_reconciled_and_completed_replay_has_no_side_effect(
    tmp_path,
):
    report = _initial_report()
    request = build_publish_request(
        [report],
        idempotency_key="publish-contract-v1",
        reason="首次发布",
    )
    ledger = PublicationLedger(tmp_path)
    ledger.prepare(
        "lucifer-20260705",
        [report],
        request,
        metadata={"historical": True, "external_side_effect_replay": False},
    )
    client = _FakeLiangHui()

    with pytest.raises(OSError):
        ledger.run("lucifer-20260705", client)
    recovered = ledger.run("lucifer-20260705", client)
    writes_after_recovery = list(client.write_calls)
    replay = ledger.run("lucifer-20260705", client)

    assert recovered["completed"] is True
    assert replay["completed"] is True
    assert client.write_calls == writes_after_recovery
    assert [name for name, _ in client.write_calls] == [
        "put_kol_record",
        "publish_kol_report",
    ]
    events = ledger.events()
    assert any(row["event"] == "record_call_uncertain" for row in events)
    assert any(
        row["event"] == "record_receipt" and row["reconciled"]
        for row in events
    )
    assert all(row.get("large_payload_local_bytes", 0) == 0 for row in events)


def test_expired_staging_receipt_renews_with_new_claim_and_same_artifact(
    tmp_path,
):
    report = _initial_report()
    request = build_publish_request(
        [report],
        idempotency_key="publish-contract-v1",
        reason="首次发布",
    )
    ledger = PublicationLedger(tmp_path)
    ledger.prepare("event-expired", [report], request)
    client = _ExpiredClaimLiangHui(report["idempotency_key"])

    completed = ledger.run("event-expired", client)

    assert completed["completed"] is True
    put_request = next(
        arguments
        for name, arguments in client.write_calls
        if name == "put_kol_record"
    )
    assert put_request["idempotency_key"] != report["idempotency_key"]
    assert put_request["content_sha256"] == report["content_sha256"]
    assert put_request["created_at"] == report["created_at"]
    assert put_request["payload"] == report["payload"]


def test_source_publication_identity_excludes_batch_and_version():
    identity = publication_id_for_source(
        adapter="subscription_video",
        source_identity="event-7-5",
    )
    assert identity == "xiaocao:subscription_video:event-7-5"
    assert report_id(identity) == report_id(identity)
    assert "batch" not in identity
    assert stable_claim("put", identity, "v3") == stable_claim(
        "put", identity, "v3"
    )


def test_prepared_artifact_cannot_change_under_same_event_identity(tmp_path):
    report = _initial_report()
    request = build_publish_request(
        [report],
        idempotency_key="publish-contract-v1",
        reason="首次发布",
    )
    ledger = PublicationLedger(tmp_path)
    ledger.prepare("event-1", [report], request)
    changed = json.loads(json.dumps(report))
    changed["payload"]["summary"] = "changed"
    changed["content_sha256"] = canonical_sha256(
        {
            key: changed[key]
            for key in (
                "schema_version",
                "kind",
                "record_id",
                "created_at",
                "source_binding",
                "payload",
            )
        }
    )
    changed_request = build_publish_request(
        [changed],
        idempotency_key="publish-contract-v2",
        reason="纠错",
    )
    with pytest.raises(Exception, match="stable key"):
        ledger.prepare("event-1", [changed], changed_request)


def test_invalid_argument_before_any_receipt_can_reprepare_same_source_binding(
    tmp_path,
):
    report = _initial_report()
    request = build_publish_request(
        [report],
        idempotency_key="publish-contract-v1",
        reason="首次发布",
    )
    ledger = PublicationLedger(tmp_path)
    ledger.prepare("event-repair", [report], request)
    record_key = ledger._record_key(report)
    ledger._append(
        "record_call_claimed",
        publication_key="event-repair",
        record_key=record_key,
        idempotency_key=report["idempotency_key"],
        request=report,
    )
    ledger._append(
        "record_call_uncertain",
        publication_key="event-repair",
        record_key=record_key,
        idempotency_key=report["idempotency_key"],
        error_type="LiangHuiMcpError",
        error_code="INVALID_ARGUMENT",
    )

    corrected = json.loads(json.dumps(report))
    corrected["created_at"] = "2026-07-26T00:00:00Z"
    corrected["payload"]["source_published_at"] = "2026-07-26T00:00:00Z"
    corrected["content_sha256"] = canonical_sha256(
        {
            key: corrected[key]
            for key in (
                "schema_version",
                "kind",
                "record_id",
                "created_at",
                "source_binding",
                "payload",
            )
        }
    )
    corrected_request = build_publish_request(
        [corrected],
        idempotency_key="publish-contract-v1",
        reason="首次发布",
    )

    ledger.prepare("event-repair", [corrected], corrected_request)

    state = ledger.status("event-repair")
    assert state["artifact"]["records"] == [corrected]
    assert len([
        row
        for row in ledger.events()
        if row["event"] == "publication_prepared"
        and row["publication_key"] == "event-repair"
    ]) == 2


def test_invalid_argument_repairs_only_unreceipted_record(tmp_path):
    report = _initial_report()
    evaluation = build_record(
        kind="viewpoint_evaluation",
        record_id_value="ve_repair",
        idempotency_key="put-evaluation-repair-v1",
        created_at="2026-07-26T08:05:00.000Z",
        source_binding=report["source_binding"],
        payload={
            "evaluation_id": "ve_repair",
            "viewpoint_id": "vp_repair",
            "status": "uncertain",
            "as_of": "2026-07-26T08:05:00.000Z",
            "evaluated_at": "2026-07-26T08:05:00.000Z",
            "basis": "等待后续验证。",
            "confidence": "medium",
            "uncertainties": [],
            "evidence": ["/Users/example/output/live/evidence.json"],
        },
    )
    records = [report, evaluation]
    request = build_publish_request(
        records,
        idempotency_key="publish-partial-repair-v1",
        reason="首次发布",
    )
    ledger = PublicationLedger(tmp_path)
    ledger.prepare("event-partial-repair", records, request)
    report_key = ledger._record_key(report)
    ledger._append(
        "record_receipt",
        publication_key="event-partial-repair",
        record_key=report_key,
        receipt={
            "idempotencyKey": report["idempotency_key"],
            "recordState": "staged",
        },
        reconciled=False,
    )
    evaluation_key = ledger._record_key(evaluation)
    ledger._append(
        "record_call_claimed",
        publication_key="event-partial-repair",
        record_key=evaluation_key,
        idempotency_key=evaluation["idempotency_key"],
        request=evaluation,
    )
    ledger._append(
        "record_call_uncertain",
        publication_key="event-partial-repair",
        record_key=evaluation_key,
        idempotency_key=evaluation["idempotency_key"],
        error_type="LiangHuiMcpError",
        error_code="INVALID_ARGUMENT",
    )

    corrected = json.loads(json.dumps(evaluation))
    del corrected["payload"]["evidence"]
    corrected["content_sha256"] = canonical_sha256(
        {
            key: corrected[key]
            for key in (
                "schema_version",
                "kind",
                "record_id",
                "created_at",
                "source_binding",
                "payload",
            )
        }
    )
    corrected_records = [report, corrected]
    corrected_request = build_publish_request(
        corrected_records,
        idempotency_key="publish-partial-repair-v1",
        reason="首次发布",
    )

    ledger.prepare(
        "event-partial-repair",
        corrected_records,
        corrected_request,
    )

    state = ledger.status("event-partial-repair")
    assert state["artifact"]["records"] == corrected_records
    assert state["record_receipts"] == {
        report_key: {
            "idempotencyKey": report["idempotency_key"],
            "recordState": "staged",
        }
    }


def test_status_snapshot_is_equivalent_and_reads_ledger_once(tmp_path, monkeypatch):
    ledger = PublicationLedger(tmp_path)
    report = _initial_report()
    request = build_publish_request([report], idempotency_key="snapshot-fixture", reason="fixture")
    for key in ("one", "two"):
        ledger.prepare(key, [report], request)
    expected = {key: ledger.status(key) for key in ("one", "two")}
    original = ledger._events_unlocked
    calls = []
    def counted():
        calls.append(True)
        return original()
    monkeypatch.setattr(ledger, "_events_unlocked", counted)
    assert ledger.status_snapshot() == expected
    assert len(calls) == 1


def _legacy_short_projection():
    report = _initial_report()
    view = _viewpoint(report)
    view['payload']['local_thesis_id'] = 't1'
    view['record_id'] = viewpoint_id(report['record_id'], 't1', view['payload']['evidence_refs'])
    view['payload']['viewpoint_id'] = view['record_id']
    view['idempotency_key'] = stable_claim('put', PUBLICATION_ID, 'initial-viewpoint-v1', view['record_id'])
    view['content_sha256'] = canonical_sha256({k: view[k] for k in ('schema_version', 'kind', 'record_id', 'created_at', 'source_binding', 'payload')})
    report['payload']['viewpoint_ids'] = [view['record_id']]
    report['content_sha256'] = canonical_sha256({k: report[k] for k in ('schema_version', 'kind', 'record_id', 'created_at', 'source_binding', 'payload')})
    eid = evaluation_id(view['record_id'], view['created_at'], view['created_at'])
    evaluation = build_record(kind='viewpoint_evaluation', record_id_value=eid,
        idempotency_key=stable_claim('put', PUBLICATION_ID, 'initial-evaluation-v1', eid),
        created_at=view['created_at'], source_binding=report['source_binding'],
        payload={'evaluation_id': eid, 'viewpoint_id': view['record_id'], 'as_of': view['created_at'],
            'evaluated_at': view['created_at'], 'status': 'uncertain', 'basis': '尚待观察'})
    records = [report, view, evaluation]
    return {'records': records, 'publish_request': build_publish_request(records,
        idempotency_key='publish-short-thesis', reason='首次发布'), 'metadata': {'viewpoint_count': 1}}


class _ShortThesisLiangHui(_FakeLiangHui):
    def __init__(self):
        super().__init__()
        self.raise_after_first_put = False
        self.records = {}
        self.rejected_calls = []

    def call_tool(self, name, arguments):
        if name == 'get_kol_record':
            record = self.records.get(arguments['record_id'])
            if record is None:
                raise LiangHuiMcpError('missing', code='NOT_FOUND')
            return record
        if name == 'put_kol_record':
            if arguments['kind'] == 'viewpoint' and len(arguments['payload']['local_thesis_id']) < 3:
                self.rejected_calls.append(arguments)
                raise LiangHuiMcpError('local_thesis_id', code='INVALID_ARGUMENT')
            if arguments['kind'] == 'report' and arguments.get('expected_content_sha256'):
                raise LiangHuiMcpError('report not published', code='CONFLICT')
            result = super().call_tool(name, arguments)
            self.records[arguments['record_id']] = {**arguments, 'state': 'staged'}
            return result
        return super().call_tool(name, arguments)


def _failed_short_projection(tmp_path):
    artifact = _legacy_short_projection()
    ledger = PublicationLedger(tmp_path)
    # Restore the pre-fix checkpoint; new builders must reject this wire ID.
    ledger._append('publication_prepared', publication_key=PUBLICATION_ID,
        artifact_sha256=canonical_sha256(artifact), artifact=artifact,
        large_payload_local_bytes=0)
    client = _ShortThesisLiangHui()
    with pytest.raises(LiangHuiMcpError, match='local_thesis_id'):
        ledger.run(PUBLICATION_ID, client)
    candidate = {'publication_key': PUBLICATION_ID, **_rebind_short_theses(artifact)}
    return ledger, client, candidate


def test_short_semantic_ids_have_stable_wire_aliases_and_raw_wire_ids_fail():
    assert publication_thesis_id('t1') == publication_thesis_id('t1')
    assert len(publication_thesis_id('t1')) >= 3
    assert publication_thesis_id('thesis-growth') == 'thesis-growth'
    old = _legacy_short_projection()['records'][1]
    with pytest.raises(PublicationError, match='local_thesis_id'):
        build_record(kind=old['kind'], record_id_value=old['record_id'],
            idempotency_key=old['idempotency_key'], created_at=old['created_at'],
            source_binding=old['source_binding'], payload=old['payload'])


def test_invalid_short_projection_is_rejected_before_any_report_claim(tmp_path):
    old = _legacy_short_projection()
    ledger = PublicationLedger(tmp_path)
    with pytest.raises(PublicationError, match='local_thesis_id'):
        ledger.prepare(PUBLICATION_ID, old['records'], old['publish_request'], metadata=old['metadata'])
    assert ledger.events() == []


def test_short_thesis_repair_preserves_reader_source_and_replays_no_effects(tmp_path):
    ledger, client, candidate = _failed_short_projection(tmp_path)
    old = ledger.status(PUBLICATION_ID)['artifact']
    repaired = ledger.reconcile_short_thesis_repair(candidate, client)
    report = repaired['records'][0]
    assert 'expected_content_sha256' not in report
    assert report['idempotency_key'] != old['records'][0]['idempotency_key']
    assert report['source_binding'] == old['records'][0]['source_binding']
    assert report['payload']['report_body'] == old['records'][0]['payload']['report_body']
    assert repaired['records'][2]['payload']['viewpoint_id'] == repaired['records'][1]['record_id']
    ledger.prepare(PUBLICATION_ID, repaired['records'], repaired['publish_request'], metadata=repaired['metadata'])
    # Re-entry after preparation uses the same proof and the same content-addressed version.
    assert ledger.reconcile_short_thesis_repair(candidate, client) == repaired
    assert ledger.run(PUBLICATION_ID, client)['completed']
    count = len(client.write_calls)
    assert ledger.run(PUBLICATION_ID, client)['completed']
    assert len(client.write_calls) == count
    assert len(client.rejected_calls) == 1
    assert len([c for n, c in client.write_calls if n == 'publish_kol_report']) == 1
    with pytest.raises(PublicationError, match='completed'):
        ledger.reconcile_short_thesis_repair(candidate, client)


@pytest.mark.parametrize('boundary', ['reader_changed', 'published', 'rejected_exists', 'unknown_rejection', 'accepted_viewpoint'])
def test_short_thesis_repair_fails_closed_on_changed_or_uncertain_effects(tmp_path, boundary):
    ledger, client, candidate = _failed_short_projection(tmp_path)
    state = ledger.status(PUBLICATION_ID)
    old_view = state['artifact']['records'][1]
    if boundary == 'reader_changed':
        candidate['records'][0]['payload']['report_body'] += '\n改变观点'
    elif boundary == 'published':
        client.records[candidate['records'][0]['record_id']]['state'] = 'published'
    elif boundary == 'rejected_exists':
        client.records[old_view['record_id']] = {**old_view, 'state': 'immutable'}
    elif boundary == 'unknown_rejection':
        ledger._append('record_call_uncertain', publication_key=PUBLICATION_ID,
            record_key=ledger._record_key(old_view), error_code='', error_type='TimeoutError')
    else:
        ledger._append('record_receipt', publication_key=PUBLICATION_ID,
            record_key=ledger._record_key(old_view), receipt={'recordState': 'immutable'})
    count = len(client.write_calls)
    with pytest.raises(PublicationError):
        ledger.reconcile_short_thesis_repair(candidate, client)
    assert len(client.write_calls) == count


@pytest.mark.parametrize('boundary', ['accepted_viewpoint', 'unknown_effect'])
def test_short_thesis_repair_rejects_stale_proof_before_prepare(tmp_path, boundary):
    ledger, client, candidate = _failed_short_projection(tmp_path)
    repaired = ledger.reconcile_short_thesis_repair(candidate, client)
    old_view = ledger.status(PUBLICATION_ID)['artifact']['records'][1]
    if boundary == 'accepted_viewpoint':
        ledger._append('record_receipt', publication_key=PUBLICATION_ID,
            record_key=ledger._record_key(old_view), receipt={'recordState': 'immutable'})
    else:
        ledger._append('record_call_uncertain', publication_key=PUBLICATION_ID,
            record_key=ledger._record_key(old_view), error_code='', error_type='TimeoutError')
    count = len(client.write_calls)
    with pytest.raises(PublicationError, match='stale'):
        ledger.reconcile_short_thesis_repair(candidate, client)
    with pytest.raises(PublicationError, match='changed under a stable key'):
        ledger.prepare(PUBLICATION_ID, repaired['records'], repaired['publish_request'],
            metadata=repaired['metadata'])
    assert len(client.write_calls) == count
