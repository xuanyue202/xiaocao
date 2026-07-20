"""Durable append-only job storage shared by KOL enrichment providers."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .enrichment_types import EnrichmentError


class EnrichmentJobStore:
    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"
        self.lock_dir = self.output_dir / ".locks"

    @contextmanager
    def job_lock(self, job_id: str) -> Iterator[None]:
        if not str(job_id).strip() or "/" in job_id or "\\" in job_id:
            raise EnrichmentError("invalid enrichment job id")
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.lock_dir / f"{job_id}.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield

    def read(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.events_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise EnrichmentError(
                        f"enrichment event ledger is invalid at line {line_number}"
                    ) from exc
                if not isinstance(value, dict):
                    raise EnrichmentError(
                        f"enrichment event ledger is invalid at line {line_number}"
                    )
                rows.append(value)
        return rows

    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_lock = self.lock_dir / "ledger.lock"
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        with ledger_lock.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        return row

    def latest(self, job_id: str) -> dict[str, Any]:
        row = next(
            (row for row in reversed(self.read()) if row.get("job_id") == job_id),
            None,
        )
        if row is None:
            raise EnrichmentError(f"enrichment job not found: {job_id}")
        return row

    def status(self, job_id: str | None = None) -> dict[str, Any]:
        events = self.read()
        if job_id is None:
            if not events:
                raise EnrichmentError("no video enrichment job exists")
            return {**events[-1]}
        return {**self.latest(job_id)}
