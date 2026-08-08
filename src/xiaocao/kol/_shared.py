"""Shared persistence and evidence primitives for KOL intelligence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class DecisionError(ValueError):
    """The proposed judgment cannot be tied safely to its evidence."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_iso(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DecisionError(f"{field} must include a timezone")
    return parsed


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical(row) + "\n")


def append_integrity_jsonl(
    path: Path,
    row: dict[str, Any],
    *,
    max_line_bytes: int,
    label: str,
    error_factory: Callable[[str], Exception],
) -> dict[str, Any]:
    """Append and fsync one hash-bound JSONL row under the caller's lock."""

    value = dict(row)
    value["event_id"] = hashlib.sha256(
        canonical(value).encode("utf-8")
    ).hexdigest()
    payload = (canonical(value) + "\n").encode("utf-8")
    if len(payload) > max_line_bytes:
        raise error_factory(f"{label} event exceeds limit")
    blocked = {signal.SIGINT, signal.SIGTERM}
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise error_factory(f"{label} append made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    return value


def read_integrity_jsonl(
    path: Path,
    *,
    max_line_bytes: int,
    label: str,
    error_factory: Callable[[str], Exception],
) -> list[dict[str, Any]]:
    """Read fail-closed hash-bound JSONL rows."""

    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise error_factory(f"{label} cannot be read") from exc
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > max_line_bytes:
            raise error_factory(f"{label} line {number} exceeds limit")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise error_factory(f"{label} line {number} is invalid") from exc
        event_id = str(row.get("event_id") or "")
        unsigned = dict(row)
        unsigned.pop("event_id", None)
        expected = hashlib.sha256(
            canonical(unsigned).encode("utf-8")
        ).hexdigest()
        if event_id != expected:
            raise error_factory(
                f"{label} line {number} failed integrity validation"
            )
        rows.append(row)
    return rows


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


@dataclass(frozen=True)
class TranscriptDocument:
    path: Path
    text: str
    sha256: str

    @property
    def text_length(self) -> int:
        return len(self.text)

    def contains(self, quote: str) -> bool:
        compact_text = re.sub(r"\s+", "", self.text)
        compact_quote = re.sub(r"\s+", "", str(quote))
        return bool(compact_quote) and compact_quote in compact_text

    @classmethod
    def load(cls, path: Path | str) -> "TranscriptDocument":
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise DecisionError(f"evidence file not found: {source}")
        raw = source.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DecisionError(
                "transcript must be UTF-8 text/Markdown; convert Word files first"
            ) from exc
        return cls(path=source, text=text, sha256=hashlib.sha256(raw).hexdigest())
