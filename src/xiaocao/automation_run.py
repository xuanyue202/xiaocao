"""Task-local runner deduplication, separate from resource/ledger locks."""
from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


@contextmanager
def automation_run(automation_id: str, slot: str, *, root: Path):
    for value in (automation_id, slot):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value):
            raise ValueError("AUTOMATION_LOCK_ID_INVALID")
    path = Path(root) / automation_id / f"{slot}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            try:
                owner = json.load(handle)
            except ValueError:
                owner = {"status": "unproven"}
            yield {"status": "busy", "automation_id": automation_id, "owner": owner}
            return
        owner = {"automation_id": automation_id, "pid": os.getpid(),
                 "thread_id": os.environ.get("CODEX_THREAD_ID"),
                 "slot": slot, "acquired_at": datetime.now(timezone.utc).isoformat()}
        handle.seek(0)
        handle.truncate()
        json.dump(owner, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield {"status": "acquired", **owner}
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
