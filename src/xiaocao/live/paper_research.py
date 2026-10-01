"""Strict, read-only evidence primitives for paper accounting research."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def number(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError(f"{label}: missing or invalid number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}: invalid number") from None
    if not result.is_finite() or not math.isfinite(float(result)):
        raise ValueError(f"{label}: non-finite number")
    return result


def money(value: Any, label: str, *, nonnegative: bool = False) -> Decimal:
    result = number(value, label)
    try:
        exact_cents = result == result.quantize(Decimal("0.01"))
    except InvalidOperation:
        exact_cents = False
    if not exact_cents:
        raise ValueError(f"{label}: amount is not exact cents")
    if nonnegative and result < 0:
        raise ValueError(f"{label}: negative amount")
    return result


def day(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("date must be ISO YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("date must be ISO YYYY-MM-DD")
    return value


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise ValueError(f"{path}:{line_no}: invalid JSON") from None
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        rows.append(row)
    return rows


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()
