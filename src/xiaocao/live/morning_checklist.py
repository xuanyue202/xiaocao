"""Original-owner audit checklist; evidence never grants trading authority."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .bounded_readback import file_lock

from xiaocao.runner_recovery import _hash, _write

ITEMS = {
    "identity_calendar": ("启动", "hard"),
    "capital_credentials": ("09:00", "hard"),
    "app_ready": ("09:00", "hard"),
    "market_auth": ("09:00", "hard"),
    "transport": ("09:00", "support"),
    "kol_projection": ("09:00–09:20", "support"),
    "kol_inputs_loaded": ("09:00–09:20", "support"),
    "app_boundary": ("09:24", "hard"),
    "original_bundle": ("冻结后", "hard"),
    "kol_fingerprint": ("冻结后", "support"),
    "account_risk": ("冻结后", "hard"),
    "kol_decision": ("冻结后", "support"),
    "orders": ("提交/对账", "hard"),
    "accounting_history": ("事后", "post_business"),
    "delivery": ("事后", "support"),
}
STATUSES = {"pending", "passed", "recovered", "degraded", "blocked", "not_applicable"}


class MorningChecklist:
    def __init__(self, path: Path, binding: dict):
        self.path, self.binding = Path(path).resolve(), dict(binding)

    @classmethod
    def create(cls, root: Path, binding: dict, *, nonblocking: bool = False):
        if not binding.get("owner_thread_id") or not binding.get("trade_date"):
            raise ValueError("MORNING_CHECKLIST_OWNER_REQUIRED")
        checklist = cls(root / (_hash(binding) + ".json"), binding)
        checklist.path.parent.mkdir(parents=True, exist_ok=True)
        with checklist.path.with_suffix(".lock").open("a+") as lock:
            file_lock(lock.fileno(), wait=not nonblocking)
            if checklist.path.exists():
                checklist.read()
            else:
                _write(checklist.path, {"schema_version": 1, "binding": binding,
                    "items": {key: {"phase": phase, "kind": kind, "status": "pending",
                                      "observed_at": None, "valid_until": None,
                                      "evidence": None, "reason": None}
                              for key, (phase, kind) in ITEMS.items()}})
        return checklist

    @classmethod
    def owned(cls, path: Path, *, post_business: bool = False):
        payload = json.loads(Path(path).read_text())
        binding = payload["binding"]
        if (binding.get("owner_thread_id") != os.environ.get("CODEX_THREAD_ID")
                or binding.get("automation_id") != os.environ.get("CODEX_AUTOMATION_ID")
                or not binding.get("owner_thread_id")):
            raise ValueError("MORNING_CHECKLIST_OWNER_MISMATCH")
        if not post_business:
            os.kill(binding["runner_pid"], 0)
            if datetime.now(timezone.utc) >= datetime.fromisoformat(binding["preparation_deadline"]):
                raise ValueError("MORNING_CHECKLIST_ORIGINAL_DEADLINE_EXPIRED")
        return cls(path, binding)

    def read(self, *, now: datetime | None = None) -> dict:
        payload = json.loads(self.path.read_text())
        if payload.get("binding") != self.binding:
            raise ValueError("MORNING_CHECKLIST_BINDING_MISMATCH")
        if now is not None:
            for item in payload["items"].values():
                if (item["status"] in {"passed", "recovered"} and item.get("valid_until")
                        and now >= datetime.fromisoformat(item["valid_until"])):
                    item["status"] = "stale"
        return payload

    def record(self, item: str, status: str, *, evidence=None, reason=None,
               observed_at: datetime | None = None, valid_until: datetime | None = None,
               nonblocking: bool = False):
        if item not in ITEMS or status not in STATUSES:
            raise ValueError("MORNING_CHECKLIST_ITEM_STATUS_INVALID")
        clock = observed_at or datetime.now(timezone.utc)
        if clock.utcoffset() is None or (valid_until is not None and
                (valid_until.utcoffset() is None or valid_until <= clock)):
            raise ValueError("MORNING_CHECKLIST_VALIDITY_INVALID")
        if status in {"passed", "recovered"} and not evidence:
            raise ValueError("MORNING_CHECKLIST_EVIDENCE_REQUIRED")
        with self.path.with_suffix(".lock").open("a+") as lock:
            file_lock(lock.fileno(), wait=not nonblocking)
            payload = self.read()
            entry = payload["items"][item]
            if entry.get("first_observed_at") is None and evidence:
                entry["first_observed_at"] = clock.isoformat()
                entry["first_evidence"] = evidence
            snapshot = {"binding": self.binding, "item": item, "status": status,
                        "observed_at": clock.isoformat(), "valid_until": valid_until.isoformat() if valid_until else None,
                        "evidence": evidence, "reason": reason}
            evidence_path = self.path.parent / "observations" / (_hash(snapshot) + ".json")
            if not evidence_path.exists():
                _write(evidence_path, snapshot)
            entry.update(status=status, evidence=evidence, reason=reason, observation_path=str(evidence_path),
                observed_at=clock.isoformat(), valid_until=valid_until.isoformat() if valid_until else None)
            _write(self.path, payload)
