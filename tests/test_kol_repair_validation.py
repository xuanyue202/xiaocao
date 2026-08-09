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


def test_repair_validation_runs_repo_owned_profile_and_persists_matching_receipt(
    tmp_path,
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
                "src/xiaocao/kol/mailbox.py\ntests/test_kol_mailbox.py\n",
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
        assert command == ("pytest", "tests/test_kol_mailbox.py", "-q")
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
