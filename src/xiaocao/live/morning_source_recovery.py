"""Recheck only the live original producer's uncommitted source observation.

No process launch, source replacement, account access, or budget renewal. Code
repairs are deployed for a later run; this signal invalidates input caches only.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from xiaocao.utils.atomic_files import atomic_write


def _raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def _read(path):
    return json.loads(Path(path).read_bytes())


class SourceRecovery:
    def __init__(self, run_dir: Path, live_dir: Path, date: str, deadline: str | None):
        self.run_dir, self.live_dir, self.date = run_dir.resolve(), live_dir.resolve(), date
        self.manifest = _read(run_dir / "manifest.json")
        self.binding = {"automation_id": self.manifest["automation_id"],
            "thread_id": self.manifest["thread_id"], "run_id": self.manifest["run_id"],
            "market_date": date, "behavior_sha256": self.manifest["source_manifest_sha256"],
            "preparation_deadline": deadline, "runner_pid": os.getpid()}
        if (self.binding["automation_id"] != "xiaocao-daily-morning"
                or self.binding["thread_id"] != os.environ.get("CODEX_THREAD_ID")
                or self.manifest["market_date"] != date):
            raise ValueError("MORNING_SOURCE_OWNER_MISMATCH")
        self.stream = (run_dir / "source_capture.lock").open("a+")
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.state_path = run_dir / "source_capture.json"
        self.request_path = None
        self._state("active")

    def _state(self, status):
        atomic_write(self.state_path, _raw({"binding": self.binding, "status": status,
            "request_path": str(self.request_path) if self.request_path else None}))

    def waiting(self, readiness: dict) -> dict:
        root = self.run_dir / "source_dependencies"
        evidence = _raw(readiness)
        digest = hashlib.sha256(evidence).hexdigest()
        path = root / (digest + ".evidence.json")
        atomic_write(path, evidence, immutable=True)
        request = {"binding": self.binding, "recovery_kind": "original_source_recheck",
            "evidence_path": str(path), "evidence_sha256": digest,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "original_budget": "unbounded_original_wait" if self.binding["preparation_deadline"] is None else "absolute_deadline"}
        self.request_path = root / (digest + ".request.json")
        atomic_write(self.request_path, _raw(request), immutable=True)
        self._state("waiting")
        return {"request_path": str(self.request_path),
            "request_sha256": hashlib.sha256(self.request_path.read_bytes()).hexdigest(),
            "recovery_kind": "original_source_recheck"}

    def consume(self) -> bool:
        if self.request_path is None:
            return False
        signal = self.request_path.with_suffix(".signal.json")
        if not signal.exists():
            return False
        value = _read(signal)
        if value.get("request_sha256") != hashlib.sha256(self.request_path.read_bytes()).hexdigest():
            raise ValueError("MORNING_SOURCE_SIGNAL_MISMATCH")
        # Mark before acting: an interrupted cache refresh cannot reuse a signal.
        consumed = self.request_path.with_suffix(".consumed.json")
        atomic_write(consumed, _raw(value), immutable=True)
        self.request_path = None
        self._state("active")
        return True

    def close(self):
        self._state("closed")
        self.stream.close()


def signal_recheck(path: Path) -> dict:
    path = path.resolve()
    request = _read(path)
    binding = request["binding"]
    if (request.get("recovery_kind") != "original_source_recheck"
            or binding["automation_id"] != os.environ.get("CODEX_AUTOMATION_ID")
            or binding["thread_id"] != os.environ.get("CODEX_THREAD_ID")):
        raise ValueError("MORNING_SOURCE_OWNER_MISMATCH")
    run_dir = path.parent.parent
    manifest = _read(run_dir / "manifest.json")
    if path.parent != run_dir / "source_dependencies" or binding["run_id"] != run_dir.name:
        raise ValueError("MORNING_SOURCE_REQUEST_PATH_INVALID")
    if (manifest.get("automation_id") != binding["automation_id"]
            or manifest.get("thread_id") != binding["thread_id"]
            or manifest.get("market_date") != binding["market_date"]
            or manifest.get("source_manifest_sha256") != binding["behavior_sha256"]):
        raise ValueError("MORNING_SOURCE_MANIFEST_MISMATCH")
    state = _read(run_dir / "source_capture.json")
    if state != {"binding": binding, "status": "waiting", "request_path": str(path)}:
        raise ValueError("MORNING_SOURCE_NOT_WAITING")
    from xiaocao.utils.trading_session import A_SHARE_TZ
    now = datetime.now(timezone.utc)
    if now.astimezone(A_SHARE_TZ).date().isoformat() != binding["market_date"]:
        raise ValueError("MORNING_SOURCE_SESSION_EXPIRED")
    deadline = binding["preparation_deadline"]
    if deadline is not None:
        bound = datetime.fromisoformat(deadline)
        if bound.tzinfo is None or now >= bound:
            raise ValueError("MORNING_SOURCE_DEADLINE_EXPIRED")
    if (run_dir / "terminal.json").exists():
        raise ValueError("MORNING_SOURCE_ALREADY_TERMINAL")
    root = Path(manifest["execution_root"])
    from xiaocao.live.morning_bundle import has_bundle_evidence
    if has_bundle_evidence(root / "output/live", binding["market_date"]):
        raise ValueError("MORNING_SOURCE_ALREADY_COMMITTED")
    from xiaocao.live.runtime_evidence import source_changes
    if source_changes(root, manifest["source_hashes"]):
        raise ValueError("MORNING_SOURCE_BEHAVIOR_CHANGED")
    evidence = Path(request["evidence_path"])
    if (evidence.parent != path.parent or hashlib.sha256(evidence.read_bytes()).hexdigest()
            != request["evidence_sha256"]):
        raise ValueError("MORNING_SOURCE_EVIDENCE_MISMATCH")
    os.kill(binding["runner_pid"], 0)
    with (run_dir / "source_capture.lock").open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise ValueError("MORNING_SOURCE_ORIGINAL_NOT_ALIVE")
    value = {"request_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "signaled_at": now.isoformat(), "status": "recheck_signaled_not_ready"}
    # One durable claim. An uncertain signal is inspected, never replayed.
    claim = path.with_suffix(".claim.json")
    with claim.open("xb") as stream:
        stream.write(_raw(value))
        stream.flush()
        os.fsync(stream.fileno())
    atomic_write(path.with_suffix(".signal.json"), _raw(value), immutable=True)
    return value
