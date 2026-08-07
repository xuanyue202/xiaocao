from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone

import pytest

from xiaocao.kol.mailbox import (
    LiangHuiMailboxClient,
    MailboxError,
    MailboxLedger,
    RemoteMailboxDrain,
)
from xiaocao.kol.enrichment_types import EnrichmentDiagnosticError


def _official_capsule() -> dict[str, object]:
    return {
        "schema_version": 2,
        "handoff_id": "a" * 64,
        "handoff_sha256": "b" * 64,
        "content_transport": "public_url_only",
        "large_payload_local_bytes": 0,
    }


def _mailbox_message(handoff_id: str) -> dict[str, object]:
    capsule = {
        **_official_capsule(),
        "handoff_id": handoff_id,
        "handoff_sha256": handoff_id,
    }
    sender_content = {
        "mailbox_id": "kol.handoff",
        "message_id": handoff_id,
        "message_type": "xiaocao.kol_handoff",
        "schema_version": 1,
        "subject": "[文章] 测试交接",
        "correlation_id": handoff_id,
        "payload": capsule,
    }
    content_sha256 = hashlib.sha256(
        json.dumps(
            sender_content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "family_id": "family-one",
        **sender_content,
        "content_sha256": content_sha256,
        "created_by": "user-one",
        "created_at": "2026-08-07T10:36:13.715Z",
        "status": "pending",
        "ack_receipt": None,
    }


def test_local_publish_requires_hash_bound_authoritative_receipt(tmp_path) -> None:
    requests: list[dict[str, object]] = []

    def exchange(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        arguments = request["arguments"]
        assert isinstance(arguments, dict)
        return {
            "operation": "send_mailbox_message",
            "outcome": "created",
            "receipt": {
                "operation": "send_mailbox_message",
                "family_id": "family-one",
                "mailbox_id": "kol.handoff",
                "message_id": "a" * 64,
                "message_type": "xiaocao.kol_handoff",
                "schema_version": 1,
                "content_sha256": arguments["content_sha256"],
                "created_by": "user-one",
                "created_at": "2026-08-07T10:36:13.715Z",
            },
        }

    ledger = MailboxLedger(tmp_path / "mailbox")
    client = LiangHuiMailboxClient(
        ledger,
        exchange=exchange,
        now=lambda: datetime(2026, 8, 7, 11, 0, tzinfo=timezone.utc),
    )

    result = client.publish_handoff(
        _official_capsule(),
        object_kind="article",
        title="测试交接",
    )

    assert result == {
        "status": "Handoff完成",
        "handoff_id": "a" * 64,
        "mailbox_outcome": "created",
        "content_sha256": (
            "237c98967c74e5793864829beb2c697cac63a985639e608f5ba9fec0c36eb911"
        ),
    }
    assert requests == [
        {
            "event": "daily_lianghui_mailbox_input_required",
            "operation": "send_mailbox_message",
            "arguments": {
                "mailbox_id": "kol.handoff",
                "message_id": "a" * 64,
                "message_type": "xiaocao.kol_handoff",
                "schema_version": 1,
                "subject": "[文章] 测试交接",
                "correlation_id": "a" * 64,
                "payload": _official_capsule(),
                "content_sha256": (
                    "237c98967c74e5793864829beb2c697cac63a985639e608f5ba9fec0c36eb911"
                ),
            },
        }
    ]
    rows = [
        json.loads(line)
        for line in (tmp_path / "mailbox" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["event"] for row in rows] == [
        "mailbox_send_attempted",
        "mailbox_send_receipted",
    ]
    assert rows[1]["handoff_id"] == "a" * 64
    assert rows[1]["receipt"]["content_sha256"] == result["content_sha256"]


def test_local_publish_reconciles_uncertain_send_before_any_retry(tmp_path) -> None:
    requests: list[dict[str, object]] = []
    sent_arguments: dict[str, object] = {}

    def exchange(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        operation = request["operation"]
        arguments = request["arguments"]
        assert isinstance(arguments, dict)
        if operation == "send_mailbox_message":
            sent_arguments.update(arguments)
            raise TimeoutError("response lost after the remote write")
        assert operation == "get_mailbox_message"
        return {
            "operation": operation,
            "message": {
                "family_id": "family-one",
                **{
                    key: sent_arguments[key]
                    for key in (
                        "mailbox_id",
                        "message_id",
                        "message_type",
                        "schema_version",
                        "subject",
                        "correlation_id",
                        "payload",
                        "content_sha256",
                    )
                },
                "created_by": "user-one",
                "created_at": "2026-08-07T10:36:13.715Z",
                "status": "pending",
                "ack_receipt": None,
            },
        }

    client = LiangHuiMailboxClient(
        MailboxLedger(tmp_path / "mailbox"),
        exchange=exchange,
    )

    with pytest.raises(TimeoutError):
        client.publish_handoff(
            _official_capsule(),
            object_kind="article",
            title="测试交接",
        )

    result = client.publish_handoff(
        _official_capsule(),
        object_kind="article",
        title="修复后的标题",
    )

    assert result["status"] == "Handoff完成"
    assert result["mailbox_outcome"] == "already_present"
    assert [request["operation"] for request in requests] == [
        "send_mailbox_message",
        "get_mailbox_message",
    ]
    assert [row["event"] for row in client.ledger.events()] == [
        "mailbox_send_attempted",
        "mailbox_send_reconciled",
    ]


def test_local_reconciliation_uses_exact_get_before_all_done(tmp_path) -> None:
    ledger = MailboxLedger(tmp_path / "mailbox")
    ledger.append(
        "mailbox_send_receipted",
        occurred_at="2026-08-07T11:00:00.000Z",
        handoff_id="a" * 64,
        object_kind="article",
        title="测试交接",
        mailbox_id="kol.handoff",
        message_id="a" * 64,
        content_sha256="c" * 64,
        outcome="created",
        receipt={
            "operation": "send_mailbox_message",
            "family_id": "family-one",
            "mailbox_id": "kol.handoff",
            "message_id": "a" * 64,
            "message_type": "xiaocao.kol_handoff",
            "schema_version": 1,
            "content_sha256": "c" * 64,
            "created_by": "user-one",
            "created_at": "2026-08-07T10:36:13.715Z",
        },
    )
    requests: list[dict[str, object]] = []

    def exchange(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        return {
            "operation": "get_mailbox_message",
            "message": {
                "family_id": "family-one",
                "mailbox_id": "kol.handoff",
                "message_id": "a" * 64,
                "message_type": "xiaocao.kol_handoff",
                "schema_version": 1,
                "payload": _official_capsule(),
                "content_sha256": "c" * 64,
                "created_by": "user-one",
                "created_at": "2026-08-07T10:36:13.715Z",
                "status": "acked",
                "ack_receipt": {
                    "operation": "ack_mailbox_message",
                    "family_id": "family-one",
                    "mailbox_id": "kol.handoff",
                    "message_id": "a" * 64,
                    "content_sha256": "c" * 64,
                    "acked_by": "user-two",
                    "acked_at": "2026-08-07T10:40:00.000Z",
                },
            },
        }

    client = LiangHuiMailboxClient(ledger, exchange=exchange)

    assert client.reconcile_local() == [{
        "object": "[文章] 测试交接",
        "status": "全部完成",
        "handoff_id": "a" * 64,
    }]
    assert requests == [{
        "event": "daily_lianghui_mailbox_input_required",
        "operation": "get_mailbox_message",
        "arguments": {
            "mailbox_id": "kol.handoff",
            "message_id": "a" * 64,
        },
    }]
    assert client.reconcile_local() == []


def test_remote_drain_attempts_each_message_once_and_requeries_for_new_work(
    tmp_path,
) -> None:
    first = _mailbox_message("a" * 64)
    second = _mailbox_message("b" * 64)
    arrived_during_run = _mailbox_message("c" * 64)
    pages = iter([
        [first, second],
        [first, arrived_during_run],
        [first],
    ])
    requests: list[dict[str, object]] = []

    def exchange(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        operation = request["operation"]
        if operation == "list_mailbox_messages":
            return {
                "operation": operation,
                "page": {
                    "items": next(pages),
                    "next_cursor": None,
                    "has_more": False,
                },
            }
        assert operation == "ack_mailbox_message"
        arguments = request["arguments"]
        assert isinstance(arguments, dict)
        return {
            "operation": operation,
            "outcome": "acked",
            "receipt": {
                "operation": operation,
                "family_id": "family-one",
                "mailbox_id": "kol.handoff",
                "message_id": arguments["message_id"],
                "content_sha256": arguments["expected_content_sha256"],
                "acked_by": "user-two",
                "acked_at": "2026-08-07T10:40:00.000Z",
            },
        }

    processed: list[str] = []

    def process(message: dict[str, object]) -> dict[str, object]:
        message_id = str(message["message_id"])
        processed.append(message_id)
        if message_id == "a" * 64:
            return {"status": "waiting", "business_complete": False}
        return {"status": "completed", "business_complete": True}

    client = LiangHuiMailboxClient(
        MailboxLedger(tmp_path / "mailbox"),
        exchange=exchange,
    )
    result = RemoteMailboxDrain(client, processor=process).run()

    assert result == {
        "status": "waiting",
        "attempted_message_ids": ["a" * 64, "b" * 64, "c" * 64],
        "acked_message_ids": ["b" * 64, "c" * 64],
        "waiting_message_ids": ["a" * 64],
        "items": [
                {
                    "object": "[文章] 测试交接",
                    "status": "等待业务完成",
                    "handoff_id": "a" * 64,
                    "category": "processor_wait",
                    "code": "waiting",
                    "stage": "business_processing",
                },
            {
                "object": "[文章] 测试交接",
                "status": "全部完成",
                "handoff_id": "b" * 64,
            },
            {
                "object": "[文章] 测试交接",
                "status": "全部完成",
                "handoff_id": "c" * 64,
            },
        ],
    }
    assert processed == ["a" * 64, "b" * 64, "c" * 64]
    assert [request["operation"] for request in requests] == [
        "list_mailbox_messages",
        "ack_mailbox_message",
        "list_mailbox_messages",
        "ack_mailbox_message",
        "list_mailbox_messages",
    ]


def test_remote_drain_reads_every_page_before_processing_the_batch(tmp_path) -> None:
    first = _mailbox_message("a" * 64)
    second = _mailbox_message("b" * 64)
    requests: list[dict[str, object]] = []
    list_count = 0

    def exchange(request: dict[str, object]) -> dict[str, object]:
        nonlocal list_count
        requests.append(request)
        operation = request["operation"]
        if operation == "list_mailbox_messages":
            list_count += 1
            arguments = request["arguments"]
            assert isinstance(arguments, dict)
            if list_count == 1:
                assert "cursor" not in arguments
                return {
                    "operation": operation,
                    "page": {
                        "items": [first],
                        "next_cursor": "page-two",
                        "has_more": True,
                    },
                }
            if list_count == 2:
                assert arguments["cursor"] == "page-two"
                return {
                    "operation": operation,
                    "page": {
                        "items": [second],
                        "next_cursor": None,
                        "has_more": False,
                    },
                }
            return {
                "operation": operation,
                "page": {"items": [], "next_cursor": None, "has_more": False},
            }
        arguments = request["arguments"]
        assert isinstance(arguments, dict)
        return {
            "operation": operation,
            "outcome": "acked",
            "receipt": {
                "operation": operation,
                "family_id": "family-one",
                "mailbox_id": "kol.handoff",
                "message_id": arguments["message_id"],
                "content_sha256": arguments["expected_content_sha256"],
                "acked_by": "user-two",
                "acked_at": "2026-08-07T10:40:00.000Z",
            },
        }

    processed: list[str] = []
    result = RemoteMailboxDrain(
        LiangHuiMailboxClient(
            MailboxLedger(tmp_path / "mailbox"),
            exchange=exchange,
        ),
        processor=lambda message: (
            processed.append(str(message["message_id"]))
            or {"business_complete": True}
        ),
    ).run()

    assert processed == ["a" * 64, "b" * 64]
    assert result["acked_message_ids"] == ["a" * 64, "b" * 64]
    assert [request["operation"] for request in requests] == [
        "list_mailbox_messages",
        "list_mailbox_messages",
        "ack_mailbox_message",
        "ack_mailbox_message",
        "list_mailbox_messages",
    ]


def test_remote_drain_deduplicates_one_message_repeated_across_pages(
    tmp_path,
) -> None:
    repeated = _mailbox_message("a" * 64)
    second = _mailbox_message("b" * 64)
    list_count = 0

    def exchange(request: dict[str, object]) -> dict[str, object]:
        nonlocal list_count
        operation = request["operation"]
        arguments = request["arguments"]
        assert isinstance(arguments, dict)
        if operation == "list_mailbox_messages":
            list_count += 1
            if list_count == 1:
                return {
                    "operation": operation,
                    "page": {
                        "items": [repeated],
                        "next_cursor": "page-two",
                        "has_more": True,
                    },
                }
            if list_count == 2:
                return {
                    "operation": operation,
                    "page": {
                        "items": [repeated, second],
                        "next_cursor": None,
                        "has_more": False,
                    },
                }
            return {
                "operation": operation,
                "page": {"items": [], "next_cursor": None, "has_more": False},
            }
        return {
            "operation": operation,
            "outcome": "acked",
            "receipt": {
                "operation": operation,
                "family_id": "family-one",
                "mailbox_id": "kol.handoff",
                "message_id": arguments["message_id"],
                "content_sha256": arguments["expected_content_sha256"],
                "acked_by": "user-two",
                "acked_at": "2026-08-07T10:40:00.000Z",
            },
        }

    processed: list[str] = []
    result = RemoteMailboxDrain(
        LiangHuiMailboxClient(
            MailboxLedger(tmp_path / "mailbox"),
            exchange=exchange,
        ),
        processor=lambda message: (
            processed.append(str(message["message_id"]))
            or {"business_complete": True}
        ),
    ).run()

    assert processed == ["a" * 64, "b" * 64]
    assert result["attempted_message_ids"] == ["a" * 64, "b" * 64]


def test_remote_drain_preserves_safe_waiting_diagnostics(tmp_path) -> None:
    message = _mailbox_message("a" * 64)
    pages = iter([[message], []])

    def exchange(request: dict[str, object]) -> dict[str, object]:
        assert request["operation"] == "list_mailbox_messages"
        return {
            "operation": "list_mailbox_messages",
            "page": {
                "items": next(pages),
                "next_cursor": None,
                "has_more": False,
            },
        }

    client = LiangHuiMailboxClient(
        MailboxLedger(tmp_path / "mailbox"),
        exchange=exchange,
    )
    result = RemoteMailboxDrain(
        client,
        processor=lambda _message: {
            "status": "waiting",
            "business_complete": False,
            "waiting_items": [{
                "category": "provider_wait",
                "code": "transcript_pending",
                "stage": "cloud_transcript",
                "reconciliation": "exact_job_pending",
                "next_poll_not_before": "2026-08-07T12:30:00.000Z",
            }],
        },
    ).run()

    assert result["items"] == [{
        "object": "[文章] 测试交接",
        "status": "等待业务完成",
        "handoff_id": "a" * 64,
        "category": "provider_wait",
        "code": "transcript_pending",
        "stage": "cloud_transcript",
        "reconciliation": "exact_job_pending",
        "next_poll_not_before": "2026-08-07T12:30:00.000Z",
    }]
    waiting_event = client.ledger.events()[-1]
    assert waiting_event["stage"] == "cloud_transcript"
    assert waiting_event["code"] == "transcript_pending"


def test_remote_drain_preserves_structured_exception_diagnostics(tmp_path) -> None:
    message = _mailbox_message("a" * 64)
    pages = iter([[message], []])

    def exchange(request: dict[str, object]) -> dict[str, object]:
        assert request["operation"] == "list_mailbox_messages"
        return {
            "operation": "list_mailbox_messages",
            "page": {
                "items": next(pages),
                "next_cursor": None,
                "has_more": False,
            },
        }

    def process(_message: dict[str, object]) -> dict[str, object]:
        raise EnrichmentDiagnosticError(
            "credential-safe diagnostic",
            category="provider_wait",
            code="transcript_pending",
            stage="cloud_transcript",
        )

    result = RemoteMailboxDrain(
        LiangHuiMailboxClient(
            MailboxLedger(tmp_path / "mailbox"),
            exchange=exchange,
        ),
        processor=process,
    ).run()

    assert result["items"][0]["category"] == "provider_wait"
    assert result["items"][0]["code"] == "transcript_pending"
    assert result["items"][0]["stage"] == "cloud_transcript"


def test_remote_repair_resume_processes_only_bound_waiting_message(
    tmp_path,
) -> None:
    target = _mailbox_message("a" * 64)
    unrelated = _mailbox_message("b" * 64)
    ledger = MailboxLedger(tmp_path / "mailbox")
    attempted = ledger.append(
        "mailbox_message_attempted",
        occurred_at="2026-08-07T10:37:00.000Z",
        handoff_id=target["message_id"],
        content_sha256=target["content_sha256"],
    )
    waiting = ledger.append(
        "mailbox_message_waiting",
        occurred_at="2026-08-07T10:37:01.000Z",
        handoff_id=target["message_id"],
        category="contract_error",
        code="mailbox_capsule_route_unsupported",
        stage="mailbox_routing",
    )
    requests: list[dict[str, object]] = []

    def exchange(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        if request["operation"] == "list_mailbox_messages":
            return {
                "operation": "list_mailbox_messages",
                "page": {
                    "items": [unrelated, target],
                    "next_cursor": None,
                    "has_more": False,
                },
            }
        arguments = request["arguments"]
        assert isinstance(arguments, dict)
        return {
            "operation": "ack_mailbox_message",
            "outcome": "acked",
            "receipt": {
                "operation": "ack_mailbox_message",
                "family_id": "family-one",
                "mailbox_id": "kol.handoff",
                "message_id": arguments["message_id"],
                "content_sha256": arguments["expected_content_sha256"],
                "acked_by": "user-two",
                "acked_at": "2026-08-07T10:40:00.000Z",
            },
        }

    processed: list[str] = []
    result = RemoteMailboxDrain(
        LiangHuiMailboxClient(ledger, exchange=exchange),
        processor=lambda message: (
            processed.append(str(message["message_id"]))
            or {"business_complete": True}
        ),
    ).run(
        only_message_id="a" * 64,
        repair_revision="c" * 40,
    )

    assert result["status"] == "completed"
    assert result["attempted_message_ids"] == ["a" * 64]
    assert result["acked_message_ids"] == ["a" * 64]
    assert processed == ["a" * 64]
    assert [request["operation"] for request in requests] == [
        "list_mailbox_messages",
        "ack_mailbox_message",
    ]
    rows = ledger.events()
    resumed = rows[-2]
    assert resumed["event"] == "mailbox_message_repair_resumed"
    assert resumed["content_sha256"] == target["content_sha256"]
    assert resumed["repair_revision"] == "c" * 40
    assert resumed["prior_waiting_event_id"] == waiting["event_id"]
    assert attempted["event_id"] != resumed["event_id"]


def test_remote_repair_resume_rejects_uncertain_side_effect(tmp_path) -> None:
    target = _mailbox_message("a" * 64)
    ledger = MailboxLedger(tmp_path / "mailbox")
    ledger.append(
        "mailbox_message_attempted",
        occurred_at="2026-08-07T10:37:00.000Z",
        handoff_id=target["message_id"],
        content_sha256=target["content_sha256"],
    )
    ledger.append(
        "mailbox_message_waiting",
        occurred_at="2026-08-07T10:37:01.000Z",
        handoff_id=target["message_id"],
        category="side_effect_uncertain",
        code="publication_result_uncertain",
        stage="publication",
    )
    client = LiangHuiMailboxClient(
        ledger,
        exchange=lambda _request: pytest.fail("must fail before MCP read"),
    )

    with pytest.raises(
        MailboxError,
        match="requires external side-effect reconciliation",
    ):
        RemoteMailboxDrain(
            client,
            processor=lambda _message: {"business_complete": True},
        ).run(
            only_message_id="a" * 64,
            repair_revision="d" * 40,
        )


def test_remote_repair_resume_revision_is_single_use(tmp_path) -> None:
    target = _mailbox_message("a" * 64)
    ledger = MailboxLedger(tmp_path / "mailbox")
    ledger.append(
        "mailbox_message_attempted",
        occurred_at="2026-08-07T10:37:00.000Z",
        handoff_id=target["message_id"],
        content_sha256=target["content_sha256"],
    )
    ledger.append(
        "mailbox_message_waiting",
        occurred_at="2026-08-07T10:37:01.000Z",
        handoff_id=target["message_id"],
        category="contract_error",
        code="mailbox_capsule_route_unsupported",
        stage="mailbox_routing",
    )
    pages = iter([[target]])

    def exchange(_request: dict[str, object]) -> dict[str, object]:
        return {
            "operation": "list_mailbox_messages",
            "page": {
                "items": next(pages),
                "next_cursor": None,
                "has_more": False,
            },
        }

    drain = RemoteMailboxDrain(
        LiangHuiMailboxClient(ledger, exchange=exchange),
        processor=lambda _message: {
            "status": "waiting",
            "business_complete": False,
        },
    )
    first = drain.run(
        only_message_id="a" * 64,
        repair_revision="e" * 40,
    )
    assert first["status"] == "waiting"

    with pytest.raises(MailboxError, match="revision was already attempted"):
        drain.run(
            only_message_id="a" * 64,
            repair_revision="e" * 40,
        )
