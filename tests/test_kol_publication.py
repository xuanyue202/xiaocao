from __future__ import annotations

import json

import pytest

from xiaocao.kol.household import LiangHuiMcpError
from xiaocao.kol.publication import (
    PublicationLedger,
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
