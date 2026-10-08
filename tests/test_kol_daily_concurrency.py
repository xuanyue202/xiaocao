from __future__ import annotations

import fcntl
import multiprocessing
import json
import sys
import subprocess
from datetime import datetime
from queue import Queue
from threading import Event, Thread
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import kol_daily
from xiaocao.kol import _shared
from xiaocao.kol.daily import DailyCoordinator, DailyError
from xiaocao.kol.writer_progress import ConvergenceLedger


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


def test_native_timeout_releases_source_and_continues_articles(tmp_path):
    import os
    read_fd, write_fd = os.pipe()
    calls = []
    def capture():
        kol_daily._read_native_agent_line(read_fd, timeout=0.02)
    def articles():
        calls.append("articles")
        return {"status": "no_update"}
    service = coordinator(tmp_path)
    try:
        service.run([
            {"name": "xiaocao_wechat_live", "run": capture},
            {"name": "wechat_official_accounts", "run": articles},
        ])
    finally:
        os.close(read_fd)
        os.close(write_fd)
    assert calls == ["articles"]
    with coordinator(tmp_path)._source_locked("xiaocao_wechat_live"):
        pass


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
            assert receive(status_output)["ledger_available"] is False
            status_thread.join(2)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
            thread.join(2)
    assert service.run([
        {"name": "xiaocao_wechat_live", "run": lambda: {"status": "no_update"}},
    ])["health"] == "healthy"


def test_partial_legacy_append_is_neither_read_nor_overwritten(tmp_path, monkeypatch):
    service = coordinator(tmp_path)
    entered, release = Event(), Event()
    original_write = _shared.os.write
    first_write = True

    def partial_write(descriptor, data):
        nonlocal first_write
        if first_write:
            first_write = False
            written = original_write(descriptor, data[:len(data) // 2])
            entered.set()
            assert release.wait(5)
            return written
        return original_write(descriptor, data)

    def legacy_append():
        with service.legacy_lock_path.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            return _shared.append_integrity_jsonl(
                service.events_path, {"event": "legacy_write"},
                max_line_bytes=1000, label="daily ledger", error_factory=DailyError,
            )

    monkeypatch.setattr(_shared.os, "write", partial_write)
    thread, output = start_call(legacy_append)
    try:
        assert entered.wait(2)
        partial = service.events_path.read_bytes()
        assert service.status()["code"] == "legacy_coordinator_busy"
        assert service.audit()["code"] == "legacy_coordinator_busy"
        result = service.run([
            {"name": "xiaocao_wechat_live", "run": lambda: pytest.fail("old writer active")},
        ])
        assert result["code"] == "legacy_coordinator_busy"
        assert service.events_path.read_bytes() == partial
    finally:
        release.set()
        thread.join(2)
    receive(output)
    assert [row["event"] for row in service.events()] == ["legacy_write"]


@pytest.mark.parametrize("command", ["status", "audit"])
def test_cli_legacy_busy_does_not_attempt_unavailable_ledger_read(tmp_path, monkeypatch, capsys, command):
    monkeypatch.setattr(sys, "argv", [
        "kol_daily.py", command, "--output-dir", str(tmp_path),
    ])
    with (tmp_path / ".lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        assert kol_daily.main() == 0
    assert json.loads(capsys.readouterr().out)["code"] == "legacy_coordinator_busy"
    assert not (tmp_path / "events.jsonl").exists()


def test_repair_cli_checks_source_slot_before_progress_or_callback(tmp_path, monkeypatch):
    owner = coordinator(tmp_path)

    def service_factory(path):
        service = coordinator(path)
        service.convergence.pending_resume = lambda _: pytest.fail("must check busy source first")
        return service

    monkeypatch.setattr(kol_daily, "DailyCoordinator", service_factory)
    monkeypatch.setattr(kol_daily, "_resume_source_repair_outcome", lambda *_args, **_kwargs: pytest.fail("duplicate repair"))
    monkeypatch.setattr(sys, "argv", [
        "kol_daily.py", "resume-source-repair", "--output-dir", str(tmp_path),
        "--source-adapter", "xiaocao_wechat_live", "--failure-fingerprint", "a" * 64,
    ])
    with owner._source_locked("xiaocao_wechat_live"):
        with pytest.raises(DailyError, match="source execution busy"):
            kol_daily.main()


@pytest.mark.parametrize("command,source,method", [
    ("capture-xiaocao-item", "xiaocao_wechat_live", "xiaocao_wechat"),
    ("capture-xiaocao-handoff", "xiaocao_wechat_live", "xiaocao_handoff_local"),
    ("capture-wechat-official", "wechat_official_accounts", "wechat_official_local"),
])
def test_local_continuation_cli_uses_canonical_source_slot(tmp_path, monkeypatch, command, source, method):
    owner = coordinator(tmp_path)
    monkeypatch.setattr(kol_daily.DailyRuntime, method, lambda *_args, **_kwargs: pytest.fail("duplicate continuation"))
    monkeypatch.setattr(sys, "argv", [
        "kol_daily.py", command, "--output-dir", str(tmp_path),
        "--source-identity", "original-video",
    ])
    with owner._source_locked(source):
        with pytest.raises(DailyError, match="source execution busy"):
            kol_daily.main()


def test_bound_cloud_follow_up_uses_source_slot_but_no_binding_needs_none(tmp_path):
    owner, other = coordinator(tmp_path), coordinator(tmp_path)
    runtime = SimpleNamespace(xiaocao_cloud_handoff=lambda *_args: pytest.fail("duplicate upload"))
    waiting = {"waiting_items": [{
        "identity": "original-video", "capture_job_id": "original-capture",
        "status": "upload_claimed", "stage": "cloud_handoff",
    }]}
    with owner._source_locked("xiaocao_wechat_live"):
        with pytest.raises(DailyError, match="source execution busy"):
            kol_daily._follow_cloud_handoff(runtime, waiting, coordinator=other)
        assert kol_daily._follow_cloud_handoff(runtime, {}, coordinator=other) is None


def test_busy_continuation_cli_reports_wait_instead_of_repair_failure(tmp_path):
    owner = coordinator(tmp_path)
    with owner._source_locked("xiaocao_wechat_live"):
        result = subprocess.run([
            sys.executable, str(Path(kol_daily.__file__).resolve()),
            "capture-xiaocao-item", "--output-dir", str(tmp_path),
            "--source-identity", "original-video",
        ], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    message = json.loads(result.stdout)
    assert message["status"] == "waiting"
    assert message["code"] == "source_busy"
    assert message["source"] == "xiaocao_wechat_live"


def test_convergence_reads_wait_only_for_short_ledger_write(tmp_path):
    ledger = ConvergenceLedger(tmp_path / "convergence.jsonl")
    other = ConvergenceLedger(ledger.path)
    entered, release = Event(), Event()

    def append():
        with ledger._locked():
            entered.set()
            assert release.wait(5)
            ledger._append({"event": "test_write"})

    writer, writer_output = start_call(append)
    reader_started, reader_finished = Event(), Event()

    def read():
        reader_started.set()
        rows = other.events()
        reader_finished.set()
        return rows

    try:
        assert entered.wait(2)
        reader, reader_output = start_call(read)
        assert reader_started.wait(2)
        assert not reader_finished.wait(0.1)
    finally:
        release.set()
        writer.join(2)
    receive(writer_output)
    assert [row["event"] for row in receive(reader_output)] == ["test_write"]
    reader.join(2)


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
