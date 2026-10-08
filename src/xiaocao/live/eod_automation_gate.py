"""Persistent EOD task claims, separate from economic resource locks."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

AUTOMATION_ID = "xiaocao-daily-eod"


class EodGateRejected(RuntimeError):
    def __init__(self, reason: str, **evidence):
        self.payload = {"status": "blocked", "reason": reason,
                        "automation_id": AUTOMATION_ID, **evidence}
        super().__init__(reason)


def claim_eod_slot(root: Path, branch: str, trade_date: str) -> dict:
    """Claim once before business entry; crashes never permit a top-level replay."""
    actual = os.environ.get("CODEX_AUTOMATION_ID")
    thread = os.environ.get("CODEX_THREAD_ID")
    if actual != AUTOMATION_ID or not thread or not thread.strip():
        raise EodGateRejected("EOD_TASK_IDENTITY_MISMATCH", actual_automation_id=actual,
                              thread_id=thread)
    if branch not in {"paper", "app"} or date.fromisoformat(trade_date).isoformat() != trade_date:
        raise EodGateRejected("EOD_SLOT_INVALID")
    path = Path(root) / "output/live/eod_task_slots" / AUTOMATION_ID / f"{trade_date}-{branch}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = {"automation_id": AUTOMATION_ID, "thread_id": thread, "pid": os.getpid(),
             "trade_date": trade_date, "branch": branch,
             "claimed_at": datetime.now(timezone.utc).isoformat(), "claim_path": str(path)}
    # Publish fully written evidence atomically. A competing process never sees
    # half a JSON receipt, and a prior completed/failed claim is never replaced.
    descriptor, temporary = tempfile.mkstemp(prefix=".claim-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(owner, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if (existing.get("automation_id") != AUTOMATION_ID
                        or existing.get("trade_date") != trade_date
                        or existing.get("branch") != branch or not existing.get("thread_id")):
                    raise ValueError("invalid owner")
            except (OSError, ValueError, AttributeError):
                raise EodGateRejected("EOD_SLOT_OWNER_UNPROVEN", claim_path=str(path)) from None
            raise EodGateRejected("EOD_SLOT_ALREADY_CLAIMED", owner=existing, claim_path=str(path)) from None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return owner
