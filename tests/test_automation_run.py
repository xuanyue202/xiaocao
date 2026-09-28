import pytest

from xiaocao.automation_run import automation_run, current_automation_id, validate_automation_identity


def test_only_same_automation_slot_is_busy(tmp_path):
    with automation_run("remote-writer", "2026-09-28", root=tmp_path) as writer:
        assert current_automation_id() == "remote-writer"
        with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as morning:
            assert current_automation_id() == "book-b-morning"
            assert writer["status"] == morning["status"] == "acquired"
            with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as duplicate:
                assert duplicate["status"] == "busy"
                assert duplicate["owner"]["automation_id"] == "book-b-morning"
        assert current_automation_id() == "remote-writer"
    with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as next_run:
        assert next_run["status"] == "acquired"


def test_entrypoint_rejects_foreign_task_identity(monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "remote-writer")
    with pytest.raises(ValueError, match="AUTOMATION_ENTRYPOINT_ID_MISMATCH"):
        validate_automation_identity("book-b-morning", "book-b-morning")
    monkeypatch.delenv("CODEX_AUTOMATION_ID")
    with pytest.raises(ValueError, match="AUTOMATION_ENTRYPOINT_ID_MISMATCH"):
        validate_automation_identity("book-b-morning", "remote-writer")
    validate_automation_identity("book-b-morning", "book-b-morning")
