"""Fail-closed checks for reader-facing KOL copy.

The analysis pipeline may use stable English enums and machine identifiers
internally. The family reader must not see those values as titles, viewpoint
subjects, conclusions, or explanatory copy.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .author_profiles import AuthorIdentityError, validate_author_pronouns


_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_MACHINE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])[a-z0-9]+(?:[-_][a-z0-9]+)+(?![A-Za-z0-9])"
)
_FORMAL_ASCII_NAME_RE = re.compile(
    r"[A-Z][A-Za-z0-9]*(?:[ .&+'/.-][A-Za-z0-9]+)*"
)


class ReaderCopyError(ValueError):
    """Reader-visible copy is machine-oriented or not natural language."""


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReaderCopyError(f"{field} must be nonempty reader-facing text")
    return value.strip()


def _contains_cjk(value: str) -> bool:
    return bool(_CJK_RE.search(value))


def _machine_token(value: str) -> str | None:
    for match in _MACHINE_TOKEN_RE.finditer(value):
        token = match.group(0)
        if any("a" <= character <= "z" for character in token):
            return token
    return None


def _natural_chinese(
    value: Any,
    *,
    field: str,
    reject_machine_tokens: bool = True,
) -> None:
    text = _text(value, field=field)
    if not _contains_cjk(text):
        raise ReaderCopyError(
            f"{field} must use natural Chinese; English is reserved for "
            "official names and stock or ETF codes"
        )
    token = _machine_token(text) if reject_machine_tokens else None
    if token:
        raise ReaderCopyError(
            f"{field} exposes machine token {token!r}; rewrite it as "
            "reader-facing Chinese"
        )


def _subject(value: Any) -> None:
    text = _text(value, field="viewpoint.subject")
    token = _machine_token(text)
    if token:
        raise ReaderCopyError(
            f"viewpoint.subject exposes machine token {token!r}; use a "
            "Chinese topic or a formal product/company/ticker name"
        )
    if _contains_cjk(text):
        return
    if (
        len(text) <= 80
        and "、" not in text
        and "," not in text
        and "，" not in text
        and _FORMAL_ASCII_NAME_RE.fullmatch(text)
    ):
        return
    raise ReaderCopyError(
        "viewpoint.subject must be natural Chinese or one formal "
        "product/company/ticker name"
    )


def _natural_values(
    values: Any,
    *,
    field: str,
    reject_machine_tokens: bool = True,
) -> None:
    if values in (None, "", []):
        return
    rows: Iterable[Any] = values if isinstance(values, list) else [values]
    for index, value in enumerate(rows):
        _natural_chinese(
            value,
            field=f"{field}[{index}]",
            reject_machine_tokens=reject_machine_tokens,
        )


def validate_reader_payload(kind: str, payload: dict[str, Any]) -> None:
    """Validate fields that can be projected directly to a family reader."""

    if kind == "report":
        author = payload.get("author")
        for field in ("title", "summary", "report_body"):
            try:
                validate_author_pronouns(
                    author,
                    payload.get(field),
                    field=f"report.{field}",
                )
            except AuthorIdentityError as exc:
                raise ReaderCopyError(str(exc)) from exc
        _natural_chinese(payload.get("title"), field="report.title")
        _natural_chinese(
            payload.get("summary"),
            field="report.summary",
            reject_machine_tokens=False,
        )
        _natural_chinese(
            payload.get("report_body"),
            field="report.report_body",
            reject_machine_tokens=False,
        )
        return
    if kind == "viewpoint":
        _subject(payload.get("subject"))
        _natural_chinese(payload.get("stance"), field="viewpoint.stance")
        _natural_values(payload.get("horizon"), field="viewpoint.horizon")
        _natural_values(
            payload.get("reasoning"),
            field="viewpoint.reasoning",
            reject_machine_tokens=False,
        )
        _natural_values(
            payload.get("triggers"),
            field="viewpoint.triggers",
            reject_machine_tokens=False,
        )
        _natural_values(
            payload.get("falsifiers"),
            field="viewpoint.falsifiers",
            reject_machine_tokens=False,
        )
        _natural_values(
            payload.get("uncertainties"),
            field="viewpoint.uncertainties",
            reject_machine_tokens=False,
        )
        return
    if kind == "viewpoint_evaluation":
        _natural_chinese(
            payload.get("basis"),
            field="viewpoint_evaluation.basis",
        )
        _natural_values(
            payload.get("uncertainties"),
            field="viewpoint_evaluation.uncertainties",
        )
        return
    if kind == "viewpoint_relation":
        _natural_chinese(
            payload.get("reason"),
            field="viewpoint_relation.reason",
        )
