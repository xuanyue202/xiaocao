from __future__ import annotations

import fcntl
import multiprocessing
from datetime import datetime
from queue import Queue
from threading import Event, Thread

import pytest

from xiaocao.kol.daily import DailyCoordinator, DailyError


def coordinator(path, hour=10):
    return DailyCoordinator(
        path,
        now=lambda: datetime.fromisoformat(f"2026-10-08T{hour:02}:00:00+08:00"),
    )


def start_call(call):
    output = Queue()

    def run():
        try:
            output.put((True, call()))
        except BaseException as exc:
            output.put((False, exc))

    thread = Thread(target=run, daemon=True)
    thread.start()
    return thread, output


def receive(output):
    succeeded, value = output.get(timeout=2)
    if not succeeded:
        raise value
    return value


def child_capture(path, entered, release, output):
    def capture():
        entered.set()
        if not release.wait(15):
            raise TimeoutError("test did not release capture")
        return {"status": "no_update"}

    output.put(coordinator(path).run([
        {"name": "xiaocao_wechat_live", "run": capture},
    ]))


def test_source_exclusivity_across_processes_and_release_after_exit(tmp_path):
    context = multiprocessing.get_context("spawn")
    entered, release, output = context.Event(), context.Event(), context.Queue()
    process = context.Process(target=child_capture, args=(tmp_path, entered, release, output))
    process.start()
    service = coordinator(tmp_path, hour=11)
    try:
        assert entered.wait(5)
        thread, result_output = start_call(lambda: service.run([
            {"name": "xiaocao_wechat_live", "run": lambda: pytest.fail("duplicate capture")},
            {"name": "wechat_official_accounts", "run": lambda: {"status": "no_update"}},
        ]))
        result = receive(result_output)
        thread.join(2)
        by_name = {row["name"]: row for row in result["source_results"]}
        assert by_name["xiaocao_wechat_live"]["code"] == "source_busy"
        assert by_name["wechat_official_accounts"]["status"] == "no_update"
        assert result["silent"] is False
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(2)
    assert process.exitcode == 0
    assert output.get(timeout=2)["health"] == "healthy"
    # The same source is available again after the first process exits.
    assert service.run([
        {"name": "xiaocao_wechat_live", "run": lambda: {"status": "no_update"}},
    ])["health"] == "healthy"


@pytest.mark.parametrize("same_instance", [False, True])
def test_waiting_capture_does_not_block_status_or_articles(tmp_path, same_instance):
    service = coordinator(tmp_path)
    next_service = service if same_instance else coordinator(tmp_path, hour=11)
    entered, release = Event(), Event()
    calls = []

    def capture():
        calls.append("capture")
        entered.set()
        assert release.wait(5)
        return {"status": "no_update"}

    first_thread, first_output = start_call(lambda: service.run([
        {"name": "xiaocao_wechat_live", "run": capture},
    ]))
    try:
        assert entered.wait(2)
        status_thread, status_output = start_call(next_service.status)
        assert receive(status_output)["event_count"] >= 3
        status_thread.join(2)

        def article():
            calls.append("article")
            return {"status": "no_update"}

        other_thread, other_output = start_call(lambda: next_service.run([
            {"name": "xiaocao_wechat_live", "priority": 10, "run": capture},
            {"name": "wechat_official_accounts", "priority": 20, "run": article},
        ]))
        result = receive(other_output)
        other_thread.join(2)
        assert calls == ["capture", "article"]
        assert result["health"] == "waiting"
        assert result["source_results"][0]["code"] == "source_busy"
        assert result["source_results"][1]["status"] == "no_update"
        states = next_service.status()["last_sweep"]["source_states"]
        assert states[0]["busy"] is True
        # A skipped invocation cannot overwrite the active capture's progress.
        assert not any(
            row["source"] == "xiaocao_wechat_live"
            for row in next_service.events()
            if row["event"] == "source_progressed"
        )
    finally:
        release.set()
        first_thread.join(2)
    receive(first_output)
    assert not first_thread.is_alive()


def test_source_slot_refreshes_completed_state_before_calling_later_source(tmp_path):
    service = coordinator(tmp_path)
    entered, release = Event(), Event()
    calls = []

    def capture():
        entered.set()
        assert release.wait(5)
        return {"status": "no_update"}

    def article():
        calls.append("article")
        return {"status": "no_update"}

    sources = [
        {"name": "xiaocao_wechat_live", "priority": 10, "run": capture},
        {"name": "wechat_official_accounts", "priority": 20, "run": article},
    ]
    thread, output = start_call(lambda: service.run(sources))
    try:
        assert entered.wait(2)
        second_thread, second_output = start_call(lambda: coordinator(tmp_path).run(sources))
        receive(second_output)
        second_thread.join(2)
    finally:
        release.set()
        thread.join(2)
    result = receive(output)
    assert calls == ["article"]
    assert result["source_results"][1]["resumed"] is True


def test_legacy_writer_is_reported_without_blocking_or_overlapping(tmp_path):
    service = coordinator(tmp_path)
    legacy = tmp_path / ".lock"
    with legacy.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        thread, output = start_call(lambda: service.run([
            {"name": "xiaocao_wechat_live", "run": lambda: pytest.fail("legacy writer active")},
        ]))
        try:
            result = receive(output)
            assert result["source_results"][0]["code"] == "legacy_coordinator_busy"
            status_thread, status_output = start_call(service.status)
            assert receive(status_output)["event_count"] > 0
            status_thread.join(2)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
            thread.join(2)
    assert service.run([
        {"name": "xiaocao_wechat_live", "run": lambda: {"status": "no_update"}},
    ])["health"] == "healthy"


def test_concurrent_ledger_writes_remain_readable_and_complete(tmp_path):
    services = [coordinator(tmp_path) for _ in range(3)]
    workers = [start_call(lambda service=service, index=index: [
        service._append("test_write", worker=index, sequence=sequence)
        for sequence in range(15)
    ]) for index, service in enumerate(services)]
    for thread, output in workers:
        assert len(receive(output)) == 15
        thread.join(2)
    rows = services[0].events()
    assert len(rows) == 45
    assert len({(row["worker"], row["sequence"]) for row in rows}) == 45


def test_exact_resume_rejects_busy_source_and_releases_on_failure(tmp_path):
    service = coordinator(tmp_path)
    other = coordinator(tmp_path)
    with service._source_locked("xiaocao_wechat_live"):
        with pytest.raises(DailyError, match="source execution busy"):
            other.resume_wait({
                "name": "xiaocao_wechat_live",
                "narrow_resume": lambda _: pytest.fail("duplicate continuation"),
            }, item_identity="original-video")
    with pytest.raises(RuntimeError):
        with service._source_locked("xiaocao_wechat_live"):
            raise RuntimeError("interrupted input")
    with other._source_slot("xiaocao_wechat_live") as busy:
        assert busy is None
