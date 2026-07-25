from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".codex" / "skills" / "kol-intelligence"
SKILL_MD = SKILL_DIR / "SKILL.md"


def test_kol_skill_is_the_single_conditional_entrypoint() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    assert not (ROOT / ".codex" / "skills" / "xiaocao-distill" / "SKILL.md").exists()
    assert "decision_status=actionable_signal" in text
    assert "decision_status=no_actionable_signal" in text
    assert "knowledge_status=reusable_knowledge" in text
    assert "knowledge_status=no_reusable_knowledge" in text
    assert "Do not make the user invoke another skill" in text
    assert "holdings as context, not a search boundary" in text


def test_kol_skill_requires_complete_trade_information_coverage() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for marker in (
        "trade-information coverage matrix",
        "today's market diagnosis",
        "next-session playbook",
        "next-several-session base case",
        "entity-resolution inventory",
        "reader_quote",
        "market-level conclusion must lead",
    ):
        assert marker in text


def test_kol_skill_has_one_resumable_ticket05_cloud_video_runner() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for marker in (
        "scripts/kol_subscription_videos.py run",
        "/课程/路西法全套",
        "cloud-to-cloud",
        "large_payload_local_bytes=0",
        "subscription_video_analysis_input_required",
        "A no-update run prints nothing",
        "same-author, same-title transcript",
    ):
        assert marker in text


def test_kol_skill_local_markdown_links_resolve() -> None:
    markdown_files = [SKILL_MD, *SKILL_DIR.joinpath("references").glob("*.md")]

    for source in markdown_files:
        text = source.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+\.md)\)", text):
            assert (source.parent / target).resolve().is_file(), (
                f"broken Markdown link in {source}: {target}"
            )


def test_durable_branch_preserves_authority_and_provenance_boundaries() -> None:
    text = (SKILL_DIR / "references" / "durable-knowledge.md").read_text(
        encoding="utf-8"
    )

    for marker in (
        "authority=0",
        "author",
        "source",
        "evidence",
        "--feedback",
        "--validate",
        "--ingest",
        "--refresh-action-log",
        "do not rewrite the Xiaocao global A-share",
        "display name to `亮灰`",
    ):
        assert marker in text
