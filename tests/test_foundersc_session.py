"""APP contention, nesting and surviving native children, with no APP effects."""
import json
import multiprocessing
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from xiaocao.live import foundersc_session as session
from xiaocao.live.foundersc_native_ax import FounderscNativeAXClient


def test_nested_clients_share_surface_and_release_after_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "session_path", lambda: tmp_path / "app.lock")
    helper = tmp_path / "helper"
    helper.write_text("unused")
    helper.chmod(0o700)
    called = Event()
    def runner(*args, **kwargs):
        os.fstat(kwargs["pass_fds"][0])
        called.set()
        return subprocess.CompletedProcess(args, 0, json.dumps(
            {"schema_version": 2, "helper_version": 10, "status": "ok"}))
    client = FounderscNativeAXClient(helper_path=helper, runner=runner)
    with ThreadPoolExecutor(1) as pool:
        with pytest.raises(RuntimeError), session.app_session() as outer:
            with session.app_session() as inner:
                assert outer == inner
            future = pool.submit(client.probe)
            assert not called.wait(0.1)
            raise RuntimeError("interrupted before broker write")
        assert future.result(timeout=3).payload["status"] == "ok"
    assert called.is_set()


def _parent_with_native_child(lock_path, ready_path, child_path, release_path):
    session.session_path = lambda: Path(lock_path)
    with session.app_session() as descriptor:
        script = ("import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text('ready'); "
                  "\nwhile not pathlib.Path(sys.argv[2]).exists(): time.sleep(.01)")
        child = subprocess.Popen([sys.executable, "-c", script, child_path, release_path],
                                 pass_fds=(descriptor,))
        Path(ready_path).write_text(str(child.pid))
        child.wait(timeout=10)


def _session_contender(lock_path, acquired_path):
    session.session_path = lambda: Path(lock_path)
    with session.app_session():
        Path(acquired_path).write_text("acquired")


def _until_file(path, timeout=5):
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert path.exists(), path


def test_killed_python_does_not_release_surface_under_running_helper(tmp_path):
    context = multiprocessing.get_context("spawn")
    lock, ready, child, release, acquired = [tmp_path / name for name in
        ("app.lock", "parent", "child", "release", "acquired")]
    parent = context.Process(target=_parent_with_native_child,
                             args=tuple(map(str, (lock, ready, child, release))))
    contender = context.Process(target=_session_contender, args=(str(lock), str(acquired)))
    try:
        parent.start()
        _until_file(ready)
        _until_file(child)
        parent.terminate()
        parent.join(5)
        contender.start()
        time.sleep(.3)
        assert not acquired.exists(), "helper still owns the inherited session FD"
        release.touch()
        contender.join(5)
        assert contender.exitcode == 0 and acquired.exists()
    finally:
        release.touch()
        for process in (parent, contender):
            if process.pid:
                if process.is_alive():
                    process.terminate()
                process.join(5)
