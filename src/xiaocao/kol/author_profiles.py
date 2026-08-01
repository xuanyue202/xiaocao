"""Stable identity facts for recurring Xiaocao KOL authors.

Names are not a reliable way to infer gender or pronouns.  Keep reviewed
author facts here and project them into semantic requests and publication
validation so an Agent prompt is not the only protection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuthorProfile:
    display_name: str
    gender: str
    subject_pronoun: str
    possessive_pronoun: str

    def semantic_payload(self) -> dict[str, str]:
        return {
            "gender": self.gender,
            "subject_pronoun": self.subject_pronoun,
            "possessive_pronoun": self.possessive_pronoun,
            "generation_rule": (
                f"提及作者本人时只用“{self.subject_pronoun}/"
                f"{self.possessive_pronoun}”，不得使用“她/她的”。"
            ),
        }


_PROFILES = {
    name: AuthorProfile(
        display_name=name,
        gender="male",
        subject_pronoun="他",
        possessive_pronoun="他的",
    )
    for name in ("吕晓彤", "路西法", "小草")
}


class AuthorIdentityError(ValueError):
    """Reader copy conflicts with a reviewed author identity fact."""


def author_profile(author: Any) -> AuthorProfile | None:
    """Return a reviewed author profile without inferring from the name."""

    return _PROFILES.get(str(author or "").strip())


def semantic_author_profile(author: Any) -> dict[str, str] | None:
    profile = author_profile(author)
    return profile.semantic_payload() if profile is not None else None


def validate_author_pronouns(
    author: Any,
    value: Any,
    *,
    field: str,
) -> None:
    """Fail closed when male-author reader copy contains bare feminine prose.

    A report may still discuss a woman, but it must name that third party
    explicitly instead of using an ambiguous bare ``她`` in an author report.
    This intentionally conservative publication rule prevents the recurring
    author from being misgendered.
    """

    profile = author_profile(author)
    if (
        profile is None
        or profile.gender != "male"
        or not isinstance(value, str)
        or "她" not in value
    ):
        return
    raise AuthorIdentityError(
        f"{profile.display_name}是男性，{field}提及作者本人必须使用"
        f"“{profile.subject_pronoun}/{profile.possessive_pronoun}”，"
        "不得使用“她/她的”；如确实指第三方女性，请写明姓名以消除歧义"
    )
