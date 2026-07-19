"""Shared persistence and evidence primitives for KOL intelligence."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
