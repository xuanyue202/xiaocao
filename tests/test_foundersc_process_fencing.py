"""Real OS processes contend for the execution lock; no APP is opened."""
import multiprocessing
from pathlib import Path

from xiaocao.live.trading_execution import account_writer_lock


def _hold_account(lock_root, attempting, acquired, release):
    attempting.set()
    with account_writer_lock(Path(lock_root), "primary"):
        acquired.set()
        if not release.wait(timeout=10):
            raise TimeoutError("test owner was not released")


def test_other_process_waits_and_recovers_after_owner_crash(tmp_path):
    context = multiprocessing.get_context("spawn")
    events = [(context.Event(), context.Event(), context.Event()) for _ in range(2)]
    processes = [context.Process(target=_hold_account, args=(str(tmp_path), *row))
                 for row in events]
    try:
        processes[0].start()
        assert events[0][1].wait(timeout=5)
        processes[1].start()
        assert events[1][0].wait(timeout=5)
        assert not events[1][1].wait(timeout=0.1)
        # An interrupted owner cannot strand the next run behind a stale lock file.
        processes[0].terminate()
        processes[0].join(timeout=5)
        assert not processes[0].is_alive()
        assert events[1][1].wait(timeout=5)
        events[1][2].set()
        processes[1].join(timeout=5)
        assert processes[1].exitcode == 0
    finally:
        # A killed process may leave multiprocessing.Event's own condition
        # locked. Cleanup must not touch its IPC primitives after termination.
        for process in processes:
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
