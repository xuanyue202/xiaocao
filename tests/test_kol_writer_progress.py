from __future__ import annotations

from datetime import datetime

import pytest

from xiaocao.kol.writer_progress import (
    ConvergenceLedger,
    FailureFingerprint,
    ProgressContractError,
    RepairValidationLedger,
    RepairValidationReceipt,
    normalize_source_result,
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


def _repair_receipt(
    progress: WriterProgress,
    *,
    profile: str = "kol_lv_download_recovery",
) -> RepairValidationReceipt:
    failure = progress.failure
    return RepairValidationReceipt.create(
        message_id="c" * 64,
        content_sha256="d" * 64,
        failure_fingerprint=progress.failure_fingerprint,
        failure_revision=failure["failure_revision"],
        failure_code=failure["code"],
        failure_stage=failure["stage"],
        repair_revision=REPAIR_REVISION,
        target_branch="main",
        target_branch_revision=REPAIR_REVISION,
        targeted_test_profile=profile,
        test_command_digest="e" * 64,
        test_result_sha256="f" * 64,
        validated_at="2026-08-08T08:40:00+08:00",
    )


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

    validation = RepairValidationLedger(tmp_path / "repair-validation.jsonl")
    receipt = validation.append(_repair_receipt(progress))
    ledger.close_repair(
        progress.failure_fingerprint,
        repair_receipt=receipt,
        validation_ledger=validation,
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


def test_newer_repair_lifecycle_supersedes_old_fingerprint_on_same_surface(
    tmp_path,
):
    clock_values = iter(
        [
            datetime.fromisoformat("2026-08-08T07:30:00+08:00"),
            datetime.fromisoformat("2026-08-08T07:31:00+08:00"),
            datetime.fromisoformat("2026-08-08T07:32:00+08:00"),
        ]
    )
    ledger = ConvergenceLedger(
        tmp_path / "convergence.jsonl",
        now=lambda: next(clock_values),
    )
    older = _progress_rows()["repair_required"]
    newer = WriterProgress.repair_required(
        item_identity=older.item_identity,
        fingerprint=FailureFingerprint(
            adapter="lv_text_image",
            category="provider_error",
            code="provider_download_filtered",
            stage="provider_download_link",
            failure_revision=FAILURE_REVISION,
            provider_contract_version="baidu_netdisk_download_v1",
        ),
        repair_revision=None,
        affected_set_digest="e" * 64,
        claim_receipt_summary=_claim_summary(),
        targeted_test_profile="kol_lv_download_recovery",
        narrow_resume_surface="lv_text_image:item-1",
        retryability="not_retryable",
    )
    ledger.record(older, slot="2026-08-08T07:00+08:00")
    ledger.record(newer, slot="2026-08-08T07:00+08:00")
    validation = RepairValidationLedger(tmp_path / "repair-validation.jsonl")
    receipt = validation.append(_repair_receipt(newer))
    ledger.close_repair(
        newer.failure_fingerprint,
        repair_receipt=receipt,
        validation_ledger=validation,
        slot="2026-08-08T07:00+08:00",
    )

    assert ledger.active_progress("lv_text_image") is None
    pending = ledger.pending_resume("lv_text_image")
    assert pending is not None
    assert pending[0] == newer


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
                    "effect_kind": "gray_report",
                    "claim_identity": "gray-report-claim-1",
                    "readback_operation": "read_gray_report_receipt",
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
    progress = normalize_source_result(
        "lv_text_image",
        outcome,
        failure_revision=FAILURE_REVISION,
        provider_contract_version="xiaocao_writer_v1",
    )

    assert progress.status == expected_status
    assert WriterProgress.from_dict(progress.to_dict()) == progress


def test_projected_repair_resumes_only_the_exact_waiting_item():
    progress = normalize_source_result(
        "wechat_official_accounts",
        {
            "status": "waiting",
            "repair_required": True,
            "waiting_items": [{
                "identity": "article-1",
                "version_key": "version-1",
                "stage": "evidence_materialization",
                "failure": {
                    "category": "schema_error",
                    "code": "image_notes_invalid",
                    "stage": "evidence_materialization",
                },
            }],
        },
        failure_revision=FAILURE_REVISION,
        provider_contract_version="xiaocao_writer_v1",
    )

    assert progress.details["narrow_resume_surface"] == (
        "wechat_official_accounts:article-1"
    )


def test_uncertain_effect_without_exact_claim_binding_is_agent_repair():
    progress = normalize_source_result(
        "subscription_video",
        {
            "status": "waiting",
            "waiting_items": [{
                "identity": "video-1",
                "version_key": "version-1",
                "stage": "cloud_transfer_reconciliation",
                "failure": {
                    "category": "uncertain_state",
                    "code": "transfer_receipt_uncertain",
                    "stage": "cloud_transfer_reconciliation",
                },
            }],
        },
        failure_revision=FAILURE_REVISION,
        provider_contract_version="xiaocao_writer_v1",
    )

    assert progress.status == "repair_required"
    assert progress.failure["category"] == "control_plane_handler_error"
    assert progress.failure["code"] == (
        "uncertain_effect_lacks_readback_binding"
    )


def test_source_wait_without_durable_deadline_becomes_repair_required():
    progress = normalize_source_result(
        "lv_text_image",
        {
            "status": "waiting",
            "waiting_items": [{
                "identity": "item-1",
                "stage": "source_run",
            }],
        },
        failure_revision=FAILURE_REVISION,
        provider_contract_version="xiaocao_writer_v1",
    )

    assert progress.status == "repair_required"
    assert progress.failure["category"] == "internal_state_error"
    assert progress.failure["code"] == "progress_deadline_missing"
    assert progress.ownership == "agent"


def test_repair_closure_must_match_required_test_profile(tmp_path):
    progress = _progress_rows()["repair_required"]
    ledger = ConvergenceLedger(
        tmp_path / "convergence.jsonl",
        now=lambda: datetime.fromisoformat("2026-08-08T07:30:00+08:00"),
    )
    ledger.record(progress, slot="2026-08-08T07:00+08:00")

    validation = RepairValidationLedger(tmp_path / "repair-validation.jsonl")
    receipt = validation.append(
        _repair_receipt(progress, profile="unrelated_profile")
    )
    with pytest.raises(ProgressContractError, match="test profile does not match"):
        ledger.close_repair(
            progress.failure_fingerprint,
            repair_receipt=receipt,
            validation_ledger=validation,
            slot="2026-08-08T07:00+08:00",
        )


@pytest.mark.parametrize("adapter", ["lv_text_image", "subscription_video"])
def test_repair_closure_accepts_shared_lv_listing_browser_eval_profile(
    tmp_path,
    adapter,
):
    progress = WriterProgress.repair_required(
        item_identity=f"{adapter}:source",
        fingerprint=FailureFingerprint(
            adapter=adapter,
            category="transport_error",
            code="detached_mid_command",
            stage="browser_eval",
            failure_revision=FAILURE_REVISION,
            provider_contract_version="xiaocao_writer_v1",
        ),
        repair_revision=None,
        affected_set_digest="d" * 64,
        claim_receipt_summary={
            "claim_count": 0,
            "receipt_count": 0,
            "uncertain_effect_count": 0,
        },
        targeted_test_profile=f"kol_{adapter}_browser_eval",
        narrow_resume_surface=f"{adapter}:source",
        retryability="retryable",
    )
    ledger = ConvergenceLedger(
        tmp_path / "convergence.jsonl",
        now=lambda: datetime.fromisoformat("2026-08-09T19:50:00+08:00"),
    )
    ledger.record(progress, slot="2026-08-09T19:00+08:00")
    validation = RepairValidationLedger(tmp_path / "repair-validation.jsonl")
    receipt = validation.append(_repair_receipt(
        progress,
        profile="kol_shared_lv_listing_browser_eval",
    ))

    closure = ledger.close_repair(
        progress.failure_fingerprint,
        repair_receipt=receipt,
        validation_ledger=validation,
        slot="2026-08-09T19:00+08:00",
    )

    assert closure["event"] == "repair_closed"
    assert closure["repair_receipt"]["targeted_test_profile"] == (
        "kol_shared_lv_listing_browser_eval"
    )


@pytest.mark.parametrize(
    "failure_code",
    ["opencli_command_failed", "opencli_cdp_timeout", "opencli_timeout"],
)
def test_repair_closure_accepts_subscription_video_browser_eval_profile(
    tmp_path,
    failure_code,
):
    progress = WriterProgress.repair_required(
        item_identity="subscription_video:source",
        fingerprint=FailureFingerprint(
            adapter="subscription_video",
            category="transport_error",
            code=failure_code,
            stage="browser_eval",
            failure_revision=FAILURE_REVISION,
            provider_contract_version="xiaocao_writer_v1",
        ),
        repair_revision=None,
        affected_set_digest="e" * 64,
        claim_receipt_summary={
            "claim_count": 0,
            "receipt_count": 0,
            "uncertain_effect_count": 0,
        },
        targeted_test_profile="kol_subscription_video_browser_eval",
        narrow_resume_surface="subscription_video:source",
        retryability="retryable",
    )
    ledger = ConvergenceLedger(
        tmp_path / "convergence.jsonl",
        now=lambda: datetime.fromisoformat("2026-08-09T22:50:00+08:00"),
    )
    ledger.record(progress, slot="2026-08-09T22:00+08:00")
    validation = RepairValidationLedger(tmp_path / "repair-validation.jsonl")
    receipt = validation.append(_repair_receipt(
        progress,
        profile="kol_subscription_video_browser_eval",
    ))

    closure = ledger.close_repair(
        progress.failure_fingerprint,
        repair_receipt=receipt,
        validation_ledger=validation,
        slot="2026-08-09T22:00+08:00",
    )

    assert closure["event"] == "repair_closed"


def test_repair_closure_rejects_unpersisted_receipt(tmp_path):
    progress = _progress_rows()["repair_required"]
    ledger = ConvergenceLedger(tmp_path / "convergence.jsonl")
    ledger.record(progress, slot="2026-08-08T07:00+08:00")
    validation = RepairValidationLedger(tmp_path / "repair-validation.jsonl")

    with pytest.raises(ProgressContractError, match="validation ledger"):
        ledger.close_repair(
            progress.failure_fingerprint,
            repair_receipt=_repair_receipt(progress),
            validation_ledger=validation,
            slot="2026-08-08T07:00+08:00",
        )
