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
        "Source-agnostic investment-claim coverage gate",
        "applies to every KOL source",
        "complete **investment-thesis inventory**",
        "an OR condition",
        "perform an independent semantic",
        "Keyword searches",
        "decision-priority ranking",
        "trade-information coverage matrix",
        "today's market diagnosis",
        "next-session playbook",
        "next-several-session base case",
        "entity-resolution inventory",
        "reader_quote",
        "Use coherent natural-language paragraphs, never tables",
    ):
        assert marker in text
    assert "market-level conclusion must lead" not in text
    assert "source-salience register" not in text


def test_kol_skill_requires_natural_reader_copy_for_every_author() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for marker in (
        "natural Chinese",
        "regardless of KOL or source adapter",
        "snake/kebab/camel tags",
        "company/product name",
        "stock/ETF ticker",
        "complete sentence",
        "not a cleanup rule tied to one author or keyword",
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


def test_kol_skill_has_one_resumable_ticket06_batch_runner() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for marker in (
        "scripts/kol_batch.py run",
        "scripts/kol_batch.py status",
        "scripts/kol_batch.py audit",
        "at least five minutes",
        "append-only batch ledger",
        "coordinator-owned durable checkpoint",
        "watched_artifacts",
        "cloud_transfer_claim",
        "large_payload_local_bytes=0",
        "low_density",
        "missing_market_data",
        "insight_path",
        "reader publication identity",
        "decision-important insight",
        "coherent compact synthesis",
        "stable 灰常亮 report link",
        "current complete",
        "content-and-manifest CAS",
        "not a synthetic publication report",
        "Ticket 07",
    ):
        assert marker in text


def test_kol_skill_has_one_ticket07_daytime_runner() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for marker in (
        "scripts/kol_daily.py run",
        "scripts/kol_daily.py status",
        "scripts/kol_daily.py audit",
        "RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=0",
        "omit `DTSTART` and `TZID`",
        "07:00 run drains overnight backlog",
        "/课程/路西法全套",
        "never reads or downloads source-video bytes",
        "content_value.status=low_density|promoted",
        "content_value.tier=report_only|alert_eligible",
        "stable URL before Book KOL-US or reminder",
        "viewpoint_triggers",
        "material fact",
        "same blocker stays silent",
    ):
        assert marker in text


def test_kol_skill_treats_multi_part_videos_as_one_logical_episode() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for marker in (
        "any number of source videos",
        "--episode-spec <path>",
        "quiescent for at least five minutes",
        "one immutable episode evidence",
        "ordered `source_parts`",
        "never reads their video bytes",
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
