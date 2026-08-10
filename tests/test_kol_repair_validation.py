from __future__ import annotations

from subprocess import CompletedProcess

import pytest

from xiaocao.kol.writer_progress import (
    ProgressContractError,
    RepairValidationLedger,
    RepairValidationService,
)


FAILURE_REVISION = "a" * 40
REPAIR_REVISION = "b" * 40


def _context() -> dict[str, str]:
    return {
        "message_id": "c" * 64,
        "content_sha256": "d" * 64,
        "failure_fingerprint": "e" * 64,
        "failure_revision": FAILURE_REVISION,
        "category": "contract_error",
        "code": "mailbox_capsule_route_unsupported",
        "stage": "mailbox_routing",
        "targeted_test_profile": "kol_mailbox_exact_resume",
    }


@pytest.mark.parametrize(
    ("implementation_path", "regression_path"),
    [
        ("src/xiaocao/kol/mailbox.py", "tests/test_kol_mailbox.py"),
        (
            "src/xiaocao/kol/semantic_bundle.py",
            "tests/test_kol_semantic_bundle.py",
        ),
    ],
)
def test_repair_validation_runs_repo_owned_profile_and_persists_matching_receipt(
    tmp_path,
    implementation_path: str,
    regression_path: str,
) -> None:
    git_calls: list[tuple[str, ...]] = []

    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        git_calls.append(command)
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == (
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            REPAIR_REVISION,
        ):
            return CompletedProcess(
                command,
                0,
                f"{implementation_path}\n{regression_path}\n",
                "",
            )
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(
                command,
                0,
                f"Repair exact mailbox resume\n\nRepair-Fingerprint: {'e' * 64}\n",
                "",
            )
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    def tests(command: tuple[str, ...]) -> CompletedProcess[str]:
        assert command == (
            ".venv/bin/python",
            "-m",
            "pytest",
            "tests/test_kol_mailbox.py",
            "tests/test_kol_semantic_bundle.py",
            "-q",
        )
        return CompletedProcess(command, 0, "42 passed\n", "")

    ledger = RepairValidationLedger(tmp_path / "repair-validation.jsonl")
    service = RepairValidationService(
        tmp_path,
        ledger=ledger,
        git_runner=git,
        test_runner=tests,
        now=lambda: "2026-08-08T09:00:00+08:00",
    )

    receipt = service.validate(_context(), repair_revision=REPAIR_REVISION)

    assert receipt.message_id == "c" * 64
    assert receipt.failure_revision == FAILURE_REVISION
    assert receipt.repair_revision == REPAIR_REVISION
    assert receipt.target_branch == "main"
    assert receipt.test_status == "passed"
    assert receipt.test_result_sha256
    assert ledger.find_matching(_context(), repair_revision=REPAIR_REVISION) == receipt
    assert ("branch", "--show-current") in git_calls
    assert ("merge-base", "--is-ancestor", FAILURE_REVISION, REPAIR_REVISION) in git_calls


@pytest.mark.parametrize(
    ("code", "declared_profile"),
    [
        ("provider_download_filtered", "kol_lv_download_recovery"),
        (
            "provider_download_link_errno_2",
            "kol_lv_text_image_provider_download_link",
        ),
    ],
)
def test_repair_validation_accepts_exact_lv_download_recovery_profile(
    tmp_path,
    code,
    declared_profile,
) -> None:
    context = {
        "adapter": "lv_text_image",
        "message_id": "1" * 64,
        "content_sha256": "2" * 64,
        "failure_fingerprint": "3" * 64,
        "failure_revision": FAILURE_REVISION,
        "category": "provider_error",
        "code": code,
        "stage": "provider_download_link",
        "targeted_test_profile": declared_profile,
    }

    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command[:2] == ("diff-tree", "--no-commit-id"):
            return CompletedProcess(
                command,
                0,
                (
                    "src/xiaocao/kol/lv_subscription.py\n"
                    "tests/test_kol_lv_subscription.py\n"
                ),
                "",
            )
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(
                command,
                0,
                f"Repair Lv download\n\nRepair-Fingerprint: {'3' * 64}\n",
                "",
            )
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    expected_command = (
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_writer_progress.py",
        "tests/test_kol_repair_validation.py",
        "-q",
        "-k",
        (
            "reviewed_historical_small_items_retire or "
            "new_image_claim_uses_single_frontend_intercept or "
            "newer_repair_lifecycle_supersedes_old_fingerprint or "
            "repair_validation_accepts_exact_lv_download_recovery_profile"
        ),
    )
    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: CompletedProcess(
            command,
            0 if command == expected_command else 1,
            "2 passed\n",
            "",
        ),
        now=lambda: "2026-08-09T14:00:00+08:00",
    )

    receipt = service.validate(context, repair_revision=REPAIR_REVISION)

    assert receipt.targeted_test_profile == "kol_lv_download_recovery"
    assert receipt.failure_fingerprint == "3" * 64


def test_repair_validation_accepts_subscription_private_listing_profile(
    tmp_path,
) -> None:
    context = {
        "adapter": "subscription_video",
        "message_id": "4" * 64,
        "content_sha256": "5" * 64,
        "failure_fingerprint": "6" * 64,
        "failure_revision": FAILURE_REVISION,
        "category": "incomplete_scan",
        "code": "private_listing_incomplete",
        "stage": "private_listing_validation",
        "targeted_test_profile": (
            "kol_subscription_video_private_listing_validation"
        ),
    }

    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == (
            "rev-parse",
            "--verify",
            "origin/main^{commit}",
        ):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command[:2] == ("diff-tree", "--no-commit-id"):
            return CompletedProcess(
                command,
                0,
                (
                    "src/xiaocao/kol/subscription_video.py\n"
                    "tests/test_kol_subscription_video.py\n"
                ),
                "",
            )
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(
                command,
                0,
                (
                    "Repair private listing\n\n"
                    f"Repair-Fingerprint: {'6' * 64}\n"
                ),
                "",
            )
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    expected_command = (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_subscription_video.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_repair_validation.py",
        "-q",
        "-k",
        (
            "private_scan_allows_slow_directory_settlement or "
            "private_scan_classifies_directory_failure or "
            "source_cli_narrow_runner_supports_subscription_video or "
            "repair_validation_accepts_subscription_private_listing_profile"
        ),
    )
    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: CompletedProcess(
            command,
            0 if command == expected_command else 1,
            "5 passed\n",
            "",
        ),
        now=lambda: "2026-08-09T17:50:00+08:00",
    )

    receipt = service.validate(context, repair_revision=REPAIR_REVISION)

    assert receipt.targeted_test_profile == (
        "kol_subscription_video_private_listing_validation"
    )
    assert receipt.failure_fingerprint == "6" * 64


@pytest.mark.parametrize(
    "failure_code",
    ["opencli_command_failed", "opencli_cdp_timeout", "opencli_timeout"],
)
def test_repair_validation_accepts_subscription_video_browser_eval_profile(
    tmp_path,
    failure_code,
) -> None:
    context = {
        "adapter": "subscription_video",
        "message_id": "a" * 64,
        "content_sha256": "b" * 64,
        "failure_fingerprint": "c" * 64,
        "failure_revision": FAILURE_REVISION,
        "category": "transport_error",
        "code": failure_code,
        "stage": "browser_eval",
        "targeted_test_profile": "kol_subscription_video_browser_eval",
    }

    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command[:2] == ("diff-tree", "--no-commit-id"):
            return CompletedProcess(
                command,
                0,
                (
                    "src/xiaocao/kol/subscription_video.py\n"
                    "src/xiaocao/kol/writer_progress.py\n"
                    "tests/test_kol_subscription_video.py\n"
                    "tests/test_kol_repair_validation.py\n"
                    "tests/test_kol_writer_progress.py\n"
                ),
                "",
            )
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(
                command,
                0,
                (
                    "Chunk private listing eval\n\n"
                    f"Repair-Fingerprint: {'c' * 64}\n"
                ),
                "",
            )
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    expected_command = (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_subscription_video.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "private_scan_chunks_recursive_eval_below_opencli_deadline or "
            "opencli_json_classifies_cdp_timeout or "
            "narrow_source_failure_keeps_seven_state_contract or "
            "source_repair_validation_accepts_pending_resume or "
            "repair_validation_accepts_subscription_video_browser_eval_profile or "
            "repair_closure_accepts_subscription_video_browser_eval_profile or "
            "repair_closure_refreshes_pending_resume or "
            "repair_resume_persists_following_repair"
        ),
    )
    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: CompletedProcess(
            command,
            0 if command == expected_command else 1,
            "4 passed\n",
            "",
        ),
        now=lambda: "2026-08-09T22:45:00+08:00",
    )

    receipt = service.validate(context, repair_revision=REPAIR_REVISION)

    assert receipt.targeted_test_profile == (
        "kol_subscription_video_browser_eval"
    )
    assert receipt.failure_fingerprint == "c" * 64


@pytest.mark.parametrize("adapter", ["lv_text_image", "subscription_video"])
def test_repair_validation_accepts_shared_lv_listing_browser_eval_profile(
    tmp_path,
    adapter,
) -> None:
    context = {
        "adapter": adapter,
        "message_id": "7" * 64,
        "content_sha256": "8" * 64,
        "failure_fingerprint": "9" * 64,
        "failure_revision": FAILURE_REVISION,
        "category": "transport_error",
        "code": "detached_mid_command",
        "stage": "browser_eval",
        "targeted_test_profile": f"kol_{adapter}_browser_eval",
    }

    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command[:2] == ("diff-tree", "--no-commit-id"):
            return CompletedProcess(
                command,
                0,
                (
                    "src/xiaocao/kol/lv_subscription.py\n"
                    "tests/test_kol_lv_subscription.py\n"
                ),
                "",
            )
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(
                command,
                0,
                (
                    "Repair shared listing eval\n\n"
                    f"Repair-Fingerprint: {'9' * 64}\n"
                ),
                "",
            )
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    expected_command = (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "listing_recovers_once_after_detached_read_only_eval or "
            "repair_validation_accepts_shared_lv_listing_browser_eval_profile or "
            "repair_closure_accepts_shared_lv_listing_browser_eval_profile"
        ),
    )
    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: CompletedProcess(
            command,
            0 if command == expected_command else 1,
            "3 passed\n",
            "",
        ),
        now=lambda: "2026-08-09T19:45:00+08:00",
    )

    receipt = service.validate(context, repair_revision=REPAIR_REVISION)

    assert receipt.targeted_test_profile == (
        "kol_shared_lv_listing_browser_eval"
    )
    assert receipt.failure_fingerprint == "9" * 64


@pytest.mark.parametrize("adapter", ["lv_text_image", "subscription_video"])
def test_repair_validation_accepts_shared_lv_listing_validation_profile(
    tmp_path,
    adapter,
) -> None:
    context = {
        "adapter": adapter,
        "message_id": "1" * 64,
        "content_sha256": "2" * 64,
        "failure_fingerprint": "3" * 64,
        "failure_revision": FAILURE_REVISION,
        "category": "incomplete_scan",
        "code": "share_metadata_missing",
        "stage": "listing_validation",
        "targeted_test_profile": f"kol_{adapter}_listing_validation",
    }

    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command[:2] == ("diff-tree", "--no-commit-id"):
            return CompletedProcess(
                command,
                0,
                (
                    "src/xiaocao/kol/lv_subscription.py\n"
                    "tests/test_kol_lv_subscription.py\n"
                ),
                "",
            )
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(
                command,
                0,
                (
                    "Repair shared listing validation\n\n"
                    f"Repair-Fingerprint: {'3' * 64}\n"
                ),
                "",
            )
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    expected_command = (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "browser_listing_recurses_without_parent_mtime_pruning_in_bounded_batches or "
            "repair_validation_accepts_shared_lv_listing_validation_profile or "
            "repair_closure_accepts_shared_lv_listing_validation_profile"
        ),
    )
    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: CompletedProcess(
            command,
            0 if command == expected_command else 1,
            "5 passed\n",
            "",
        ),
        now=lambda: "2026-08-10T11:45:00+08:00",
    )

    receipt = service.validate(context, repair_revision=REPAIR_REVISION)

    assert receipt.targeted_test_profile == "kol_shared_lv_listing_validation"
    assert receipt.failure_fingerprint == "3" * 64


@pytest.mark.parametrize(
    ("category", "code", "stage", "targeted_test_profile"),
    [
        (
            "source_error",
            "source_temporarily_unavailable",
            "source_run",
            "kol_xiaocao_wechat_live_source_run",
        ),
        (
            "internal_state_error",
            "progress_deadline_missing",
            "compressed_capture",
            "kol_xiaocao_wechat_live_compressed_capture",
        ),
        (
            "internal_state_error",
            "progress_deadline_missing",
            "cloud_handoff",
            "kol_xiaocao_wechat_live_cloud_handoff",
        ),
    ],
)
def test_repair_validation_accepts_xiaocao_wechat_source_profile(
    tmp_path,
    category,
    code,
    stage,
    targeted_test_profile,
) -> None:
    context = {
        "adapter": "xiaocao_wechat_live",
        "message_id": "7" * 64,
        "content_sha256": "8" * 64,
        "failure_fingerprint": "9" * 64,
        "failure_revision": FAILURE_REVISION,
        "category": category,
        "code": code,
        "stage": stage,
        "targeted_test_profile": targeted_test_profile,
    }

    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command[:2] == ("diff-tree", "--no-commit-id"):
            return CompletedProcess(
                command,
                0,
                (
                    "scripts/kol_daily.py\n"
                    "src/xiaocao/kol/xiaocao_wechat.py\n"
                    "src/xiaocao/kol/writer_progress.py\n"
                    "tests/test_kol_daily.py\n"
                    "tests/test_kol_repair_validation.py\n"
                    "tests/test_kol_xiaocao_wechat.py\n"
                ),
                "",
            )
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(
                command,
                0,
                (
                    "Repair Xiaocao source resume\n\n"
                    f"Repair-Fingerprint: {'9' * 64}\n"
                ),
                "",
            )
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    expected_command = (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_daily.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_xiaocao_wechat.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "source_cli_narrow_runner_supports_xiaocao_wechat_live or "
            "narrow_source_user_action_keeps_seven_state_contract or "
            "source_repair_resume_follows_bound_xiaocao_cloud_handoff or "
            "repair_validation_accepts_xiaocao_wechat_source_profile or "
            "new_source_account_login_redirect_resolves_exact_page or "
            "account_login_state_is_authoritative_when_page_url_stays_bound or "
            "cloud_handoff_wait_has_durable_poll_deadline or "
            "compressed_capture_wait_has_durable_poll_deadline or "
            "pending_cloud_handoff_resumes_exact_job_after_stale_playback_state or "
            "repair_closure_accepts_xiaocao_wechat_source_profile"
        ),
    )
    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: CompletedProcess(
            command,
            0 if command == expected_command else 1,
            "2 passed\n",
            "",
        ),
        now=lambda: "2026-08-10T09:10:00+08:00",
    )

    receipt = service.validate(context, repair_revision=REPAIR_REVISION)

    assert receipt.targeted_test_profile == "kol_xiaocao_wechat_live_source_run"
    assert receipt.failure_fingerprint == "9" * 64


def test_repair_validation_rejects_unpushed_or_failed_repair(tmp_path) -> None:
    def unpushed_git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{FAILURE_REVISION}\n", "")
        if command[:2] == ("merge-base", "--is-ancestor"):
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=unpushed_git,
        test_runner=lambda command: pytest.fail("tests must not run"),
    )

    with pytest.raises(ProgressContractError, match="not pushed"):
        service.validate(_context(), repair_revision=REPAIR_REVISION)


def test_repair_validation_rejects_unrelated_commit_before_tests(tmp_path) -> None:
    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == (
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            REPAIR_REVISION,
        ):
            return CompletedProcess(command, 0, "docs/unrelated.md\n", "")
        raise AssertionError(command)

    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: pytest.fail("tests must not run"),
    )

    with pytest.raises(ProgressContractError, match="unrelated"):
        service.validate(_context(), repair_revision=REPAIR_REVISION)


@pytest.mark.parametrize(
    ("changed_files", "message", "expected"),
    [
        (
            "src/xiaocao/kol/mailbox.py\n",
            f"Repair\n\nRepair-Fingerprint: {'e' * 64}\n",
            "targeted regression",
        ),
        (
            "src/xiaocao/kol/mailbox.py\ntests/test_kol_mailbox.py\n",
            "Repair without binding\n",
            "failure fingerprint",
        ),
    ],
)
def test_repair_validation_requires_regression_and_fingerprint_trailer(
    tmp_path,
    changed_files: str,
    message: str,
    expected: str,
) -> None:
    def git(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command == ("branch", "--show-current"):
            return CompletedProcess(command, 0, "main\n", "")
        if command == ("rev-parse", "--verify", "HEAD^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command == ("rev-parse", "--verify", "origin/main^{commit}"):
            return CompletedProcess(command, 0, f"{REPAIR_REVISION}\n", "")
        if command[:2] == ("diff-tree", "--no-commit-id"):
            return CompletedProcess(command, 0, changed_files, "")
        if command == ("show", "-s", "--format=%B", REPAIR_REVISION):
            return CompletedProcess(command, 0, message, "")
        raise AssertionError(command)

    service = RepairValidationService(
        tmp_path,
        ledger=RepairValidationLedger(tmp_path / "repair-validation.jsonl"),
        git_runner=git,
        test_runner=lambda command: pytest.fail("tests must not run"),
    )

    with pytest.raises(ProgressContractError, match=expected):
        service.validate(_context(), repair_revision=REPAIR_REVISION)
