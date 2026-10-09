"""Keep one original process alive across a repairable dependency failure.

The caller supplies a safe dependency check, never an order action. A resume
signal requests a fresh check; it cannot certify readiness or extend the budget.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def signal_recheck(path: Path) -> dict:
    request = json.loads(path.read_text())
    binding = request["binding"]
    if request.get("status") != "waiting" or _hash(binding) != request.get("request_sha256"):
        raise ValueError("DEPENDENCY_RECOVERY_REQUEST_NOT_WAITING")
    owner = os.environ.get("CODEX_THREAD_ID")
    if binding.get("owner_thread_id") and owner != binding["owner_thread_id"]:
        raise ValueError("DEPENDENCY_RECOVERY_OWNER_MISMATCH")
    automation_id = os.environ.get("CODEX_AUTOMATION_ID")
    if automation_id and automation_id != binding.get("automation_id"):
        raise ValueError("DEPENDENCY_RECOVERY_AUTOMATION_MISMATCH")
    signal = {"request_sha256": request["request_sha256"], "sequence": request["sequence"],
              "signalled_at": datetime.now(timezone.utc).isoformat()}
    _write(path.with_suffix(".resume.json"), signal)
    return {"status": "recheck_signalled", "request_path": str(path.resolve()),
            "request_sha256": request["request_sha256"]}


class DependencyRecovery:
    def __init__(self, *, root, identity, deadline, boundary, recoverable,
                 on_event, on_failure=None, evidence=lambda: {}, failure_evidence=None,
                 automatic_retry=None,
                 clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic, sleep=time.sleep):
        self.root, self.identity = Path(root), identity
        self.deadline, self.boundary = deadline, boundary
        self.recoverable, self.on_event, self.on_failure = recoverable, on_event, on_failure
        self.evidence, self.clock, self.monotonic, self.sleep = evidence, clock, monotonic, sleep
        self.failure_evidence = failure_evidence
        self.automatic_retry = automatic_retry
        self.requests = []

    def run(self, check):
        try:
            return check()
        except (OSError, ValueError, RuntimeError) as exc:
            if not self.recoverable(exc):
                raise
            last = exc
        binding = {**self.identity, "request_id": uuid.uuid4().hex}
        path = self.root / (binding["request_id"] + ".json")
        record = {"binding": binding, "request_sha256": _hash(binding), "status": "waiting",
                  "sequence": 0, "failures": [], "request_path": str(path.resolve())}
        self.requests.append(record)
        boundary_checked = self.clock() >= self.boundary

        def failed(exc):
            code = str(exc).split(":", 1)[0]
            if not re.fullmatch(r"[A-Z0-9_]{1,100}", code):
                code = type(exc).__name__
            record["sequence"] += 1
            details = self.failure_evidence(exc) if self.failure_evidence else self.evidence()
            record["failures"].append({"code": code, "observed_at": self.clock().isoformat(),
                                        "evidence": details})
            _write(path, record)
            self.on_event({"event": "dependency_recovery_wait", **record})
            if self.on_failure:
                self.on_failure(record)

        failed(last)
        next_retry = self.monotonic() + 2.0
        signal_path = path.with_suffix(".resume.json")
        while self.monotonic() < self.deadline:
            signal = None
            if signal_path.exists():
                try:
                    signal = json.loads(signal_path.read_text())
                except (OSError, ValueError):
                    pass
            resume = bool(signal and signal.get("request_sha256") == record["request_sha256"]
                          and signal.get("sequence") == record["sequence"])
            boundary_due = not boundary_checked and self.clock() >= self.boundary
            retry_due = (self.automatic_retry is not None
                         and self.automatic_retry(record["failures"][-1])
                         and self.monotonic() >= next_retry)
            if resume or boundary_due or retry_due:
                boundary_checked = boundary_checked or boundary_due
                record["last_recheck_trigger"] = ("repair_signal" if resume else
                    "no_action_dependency_retry" if retry_due else "recovery_boundary")
                # Consume this generation before checking; stale signals never
                # cause a poll loop or repeat a dependency action.
                record["sequence"] += 1
                try:
                    result = check()
                except (OSError, ValueError, RuntimeError) as exc:
                    if not self.recoverable(exc):
                        record["status"] = "terminal"
                        _write(path, record)
                        raise
                    last = exc
                    failed(exc)
                    next_retry = self.monotonic() + 2.0
                else:
                    record.update(status="recovered", recovered_at=self.clock().isoformat())
                    _write(path, record)
                    self.on_event({"event": "dependency_recovered", **record})
                    return result
            self.sleep(min(1.0, max(0.0, self.deadline - self.monotonic())))
        record.update(status="exhausted", finished_at=self.clock().isoformat())
        _write(path, record)
        raise RuntimeError("DEPENDENCY_RECOVERY_BUDGET_EXHAUSTED:" + record["failures"][-1]["code"]) from last

    def snapshot(self):
        return {"requests": self.requests, "check_count": sum(len(r["failures"]) + (r["status"] == "recovered") for r in self.requests)}
