from xiaocao.automation_run import automation_run


def test_only_same_automation_slot_is_busy(tmp_path):
    with automation_run("remote-writer", "2026-09-28", root=tmp_path) as writer:
        with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as morning:
            assert writer["status"] == morning["status"] == "acquired"
            with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as duplicate:
                assert duplicate["status"] == "busy"
                assert duplicate["owner"]["automation_id"] == "book-b-morning"
    with automation_run("book-b-morning", "2026-09-28", root=tmp_path) as next_run:
        assert next_run["status"] == "acquired"
