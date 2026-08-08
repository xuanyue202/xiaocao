from __future__ import annotations

from datetime import datetime

import pytest

from xiaocao.kol.writer_progress import (
    ConvergenceLedger,
    FailureFingerprint,
    ProgressContractError,
    project_source_outcome,
    WriterProgress,
)


FAILURE_REVISION = "a" * 40
REPAIR_REVISION = "b" * 40


def _fingerprint() -> FailureFingerprint:
    return FailureFingerprint(
        adapter="lv_text_image",
        category="identity_error",
        code="blocked_download_frame_missing",
        stage="browser_download_recovery",
        failure_revision=FAILURE_REVISION,
        provider_contract_version="baidu_netdisk_download_v1",
    )


def _claim_summary() -> dict[str, int]:
    return {
        "claim_count": 1,
        "receipt_count": 0,
        "uncertain_effect_count": 0,
    }


def _progress_rows() -> dict[str, WriterProgress]:
    fingerprint = _fingerprint()
    return {
        "continue": WriterProgress.continue_(
            item_identity="item-1",
            completed_stage="discovery",
            next_stage="download",
            claim_receipt_summary={
                "claim_count": 0,
                "receipt_count": 0,
                "uncertain_effect_count": 0,
            },
        ),
        "structured_input": WriterProgress.structured_input(
            item_identity="item-1",
            stage="semantic_input",
            request_kind="daily_analysis_input_required",
            request_id="request-1",
            request_schema_version=1,
            immutable_bindings={"evidence_sha256": "c" * 64},
            response_field="bundle_path",
            claim_receipt_summary=_claim_summary(),
        ),
        "wait_until": WriterProgress.wait_until(
            item_identity="item-1",
            category="provider_wait",
            code="transcript_processing",
            stage="cloud_enrichment",
            deadline="2026-08-08T12:30:00+08:00",
            attempt_budget={"attempted": 1, "maximum": 3},
            claim_receipt_summary=_claim_summary(),
        ),
        "repair_required": WriterProgress.repair_required(
            item_identity="item-1",
            fingerprint=fingerprint,
            repair_revision=None,
            affected_set_digest="d" * 64,
            claim_receipt_summary=_claim_summary(),
            targeted_test_profile="kol_lv_download_recovery",
            narrow_resume_surface="lv_text_image:item-1",
            retryability="retryable",
        ),
        "reconcile_required": WriterProgress.reconcile_required(
            item_identity="item-1",
            stage="publication_reconciliation",
            effect_kind="gray_report",
            claim_identity="claim-1",
            readback_operation="get_gray_report",
            claim_receipt_summary=_claim_summary(),
        ),
        "user_action_required": WriterProgress.user_action_required(
            item_identity="item-1",
            stage="provider_authentication",
            action="complete provider login",
            blocker_identity="provider-login",
            dedup_key="provider-login-item-1",
            claim_receipt_summary=_claim_summary(),
        ),
        "terminal": WriterProgress.terminal(
            item_identity="item-1",
            stage="mailbox_ack",
            content_terminal="promoted",
            gray_report_terminal="published",
            reminder_terminal="delivered",
            book_terminal="no_trade",
            knowledge_terminal="reusable_knowledge",
            ack_status="acked",
            new_external_effect_count=2,
            claim_receipt_summary={
                "claim_count": 2,
                "receipt_count": 2,
                "uncertain_effect_count": 0,
            },
        ),
    }


def test_writer_progress_has_exactly_seven_statuses_and_one_next_action_each():
    rows = _progress_rows()

    assert set(rows) == {
        "continue",
        "structured_input",
        "wait_until",
        "repair_required",
        "reconcile_required",
        "user_action_required",
        "terminal",
    }
    assert {name: row.next_action for name, row in rows.items()} == {
        "continue": "continue_in_process",
        "structured_input": "await_structured_input",
        "wait_until": "resume_after_deadline",
        "repair_required": "validate_repair_then_narrow_resume",
        "reconcile_required": "perform_authoritative_readback",
        "user_action_required": "await_user_action",
        "terminal": "stop",
    }
    for row in rows.values():
        assert WriterProgress.from_dict(row.to_dict()) == row


def test_writer_progress_rejects_missing_required_field_and_illegal_transition():
    repair = _progress_rows()["repair_required"]
    invalid = repair.to_dict()
    invalid.pop("targeted_test_profile")

    with pytest.raises(ProgressContractError, match="targeted_test_profile"):
        WriterProgress.from_dict(invalid)

    terminal = _progress_rows()["terminal"]
    with pytest.raises(ProgressContractError, match="matching repair closure"):
        repair.validate_transition_to(terminal)

    repair.validate_transition_to(
        terminal,
        evidence={
            "event": "repair_closed",
            "failure_fingerprint": repair.failure_fingerprint,
            "repair_revision": REPAIR_REVISION,
        },
    )


def test_failure_fingerprint_is_stable_and_contains_only_safe_contract_fields():
    first = _fingerprint()
    second = _fingerprint()

    assert first.digest == second.digest
    assert first.to_dict() == {
        "adapter": "lv_text_image",
        "category": "identity_error",
        "code": "blocked_download_frame_missing",
        "stage": "browser_download_recovery",
        "failure_revision": FAILURE_REVISION,
        "provider_contract_version": "baidu_netdisk_download_v1",
        "digest": first.digest,
    }
    serialized = str(first.to_dict())
    assert "https://" not in serialized
    assert "/Users/" not in serialized
    assert "课程" not in serialized

    unsafe = first.to_dict()
    unsafe["source_url"] = "https://provider.invalid/private"
    with pytest.raises(ProgressContractError, match="unsupported field"):
        FailureFingerprint.from_dict(unsafe)


def test_convergence_ledger_recovers_counts_owner_and_matching_closure(tmp_path):
    clock_values = iter(
        [
            datetime.fromisoformat("2026-08-08T07:30:00+08:00"),
            datetime.fromisoformat("2026-08-08T07:31:00+08:00"),
            datetime.fromisoformat("2026-08-08T08:30:00+08:00"),
            datetime.fromisoformat("2026-08-08T08:45:00+08:00"),
        ]
    )
    path = tmp_path / "convergence.jsonl"
    progress = _progress_rows()["repair_required"]
    ledger = ConvergenceLedger(path, now=lambda: next(clock_values))

    ledger.record(progress, slot="2026-08-08T07:00+08:00")
    ledger.record(progress, slot="2026-08-08T07:00+08:00")
    ledger.record(progress, slot="2026-08-08T08:00+08:00")

    recovered = ConvergenceLedger(path).current(progress.failure_fingerprint)
    assert recovered == {
        "failure_fingerprint": progress.failure_fingerprint,
        "first_seen": "2026-08-08T07:30:00+08:00",
        "last_seen": "2026-08-08T08:30:00+08:00",
        "same_sweep_count": 1,
        "consecutive_slots": 2,
        "current_owner": "agent",
        "repair_receipt": None,
        "closure": None,
        "closed": False,
    }

    ledger.close_repair(
        progress.failure_fingerprint,
        repair_receipt={
            "receipt_id": "receipt-1",
            "failure_fingerprint": progress.failure_fingerprint,
            "repair_revision": REPAIR_REVISION,
            "targeted_test_profile": "kol_lv_download_recovery",
        },
        slot="2026-08-08T08:00+08:00",
    )

    closed = ConvergenceLedger(path).current(progress.failure_fingerprint)
    assert closed["closed"] is True
    assert closed["current_owner"] is None
    assert closed["repair_receipt"]["repair_revision"] == REPAIR_REVISION
    assert closed["closure"] == "2026-08-08T08:45:00+08:00"


def test_open_progress_restores_the_authoritative_repair_contract(tmp_path):
    progress = _progress_rows()["repair_required"]
    ledger = ConvergenceLedger(
        tmp_path / "convergence.jsonl",
        now=lambda: datetime.fromisoformat("2026-08-08T07:30:00+08:00"),
    )
    ledger.record(progress, slot="2026-08-08T07:00+08:00")

    assert ConvergenceLedger(
        tmp_path / "convergence.jsonl"
    ).active_progress("lv_text_image") == progress


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ({"status": "no_update"}, "terminal"),
        (
            {
                "status": "waiting",
                "waiting_items": [{
                    "identity": "item-1",
                    "stage": "cloud_transcript",
                    "category": "provider_wait",
                    "code": "transcript_pending",
                    "next_poll_not_before": "2026-08-08T12:30:00+08:00",
                }],
            },
            "wait_until",
        ),
        (
            {
                "status": "waiting",
                "waiting_items": [{
                    "identity": "item-1",
                    "version_key": "version-1",
                    "stage": "waiting_semantic_input",
                    "evidence_sha256": "c" * 64,
                }],
            },
            "structured_input",
        ),
        (
            {
                "status": "waiting",
                "waiting_items": [{
                    "identity": "item-1",
                    "stage": "publication_reconciliation",
                    "failure": {
                        "category": "uncertain_state",
                        "code": "publication_receipt_uncertain",
                        "stage": "publication_reconciliation",
                    },
                }],
            },
            "reconcile_required",
        ),
        (
            {
                "status": "waiting",
                "failure": {
                    "category": "schema_error",
                    "code": "bundle_schema_invalid",
                    "stage": "semantic_validation",
                },
            },
            "repair_required",
        ),
    ],
)
def test_legacy_source_results_project_through_unified_progress(
    outcome,
    expected_status,
):
    progress = project_source_outcome(
        "lv_text_image",
        outcome,
        failure_revision=FAILURE_REVISION,
        provider_contract_version="xiaocao_writer_v1",
    )

    assert progress.status == expected_status
    assert WriterProgress.from_dict(progress.to_dict()) == progress


def test_repair_closure_must_match_required_test_profile(tmp_path):
    progress = _progress_rows()["repair_required"]
    ledger = ConvergenceLedger(
        tmp_path / "convergence.jsonl",
        now=lambda: datetime.fromisoformat("2026-08-08T07:30:00+08:00"),
    )
    ledger.record(progress, slot="2026-08-08T07:00+08:00")

    with pytest.raises(ProgressContractError, match="test profile does not match"):
        ledger.close_repair(
            progress.failure_fingerprint,
            repair_receipt={
                "receipt_id": "receipt-1",
                "failure_fingerprint": progress.failure_fingerprint,
                "repair_revision": REPAIR_REVISION,
                "targeted_test_profile": "unrelated_profile",
            },
            slot="2026-08-08T07:00+08:00",
        )
