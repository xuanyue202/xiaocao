from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


SIGNAL_FIELDS = [
    "date",
    "mode",
    "code",
    "name",
    "xcjw",
    "cjs",
    "jsjl",
    "jssb",
    "pctChange",
    "openPctChange",
    "direction",
    "directionRank",
    "categoryRank",
    "reason",
]


def normalize_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], dict):
            return data
        return [{"value": item} for item in data]
    if isinstance(data, dict):
        return [data]
    return [{"value": data}]


def render_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fields = _field_order(rows)
    from io import StringIO

    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_No data_"
    fields = _field_order(rows)
    header = "| " + " | ".join(fields) + " |"
    sep = "| " + " | ".join("---" for _ in fields) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_cell(row.get(field, "")) for field in fields) + " |")
    return "\n".join([header, sep, *body])


def render_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No data"
    fields = _field_order(rows)
    widths = {
        field: min(32, max(len(field), *(len(_cell(row.get(field, ""))) for row in rows)))
        for field in fields
    }
    lines = ["  ".join(field.ljust(widths[field]) for field in fields)]
    lines.append("  ".join("-" * widths[field] for field in fields))
    for row in rows:
        lines.append("  ".join(_cell(row.get(field, ""))[: widths[field]].ljust(widths[field]) for field in fields))
    return "\n".join(lines)


def write_output(data: Any, fmt: str = "table", output: str | None = None) -> None:
    rows = normalize_rows(data)
    if fmt == "json":
        text = render_json(data)
    elif fmt == "csv":
        text = render_csv(rows)
    elif fmt == "markdown":
        text = render_markdown(rows)
    elif fmt == "table":
        text = render_table(rows)
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
        sys.stdout.write("\n")


def _field_order(rows: list[dict[str, Any]]) -> list[str]:
    keys = []
    for field in SIGNAL_FIELDS:
        if any(field in row for row in rows):
            keys.append(field)
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    return keys


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).replace("\n", " ")
