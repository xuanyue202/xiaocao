from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".codex" / "skills" / "kol-intelligence"
SKILL_MD = SKILL_DIR / "SKILL.md"
FULL_CONTRACT_MD = SKILL_DIR / "references" / "full-contract.md"
HOURLY_LOCAL_CAPTURE_MD = (
    SKILL_DIR / "references" / "hourly-local-capture.md"
)
HOURLY_REMOTE_WRITER_MD = (
    SKILL_DIR / "references" / "hourly-remote-writer.md"
)
XIAOCAO_CAPTURE_START_MD = (
    SKILL_DIR / "references" / "xiaocao-capture-start.md"
)


def test_kol_skill_is_the_single_conditional_entrypoint() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    assert not (ROOT / ".codex" / "skills" / "xiaocao-distill" / "SKILL.md").exists()
    assert "decision_status=actionable_signal" in text
    assert "decision_status=no_actionable_signal" in text
    assert "knowledge_status=reusable_knowledge" in text
    assert "knowledge_status=no_reusable_knowledge" in text
    assert "Do not make the user invoke another skill" in text
    assert "holdings as context, not a search boundary" in text


def test_kol_skill_routes_xiaocao_recap_to_live_replay_capture_first() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for marker in (
        "小草复盘",
        "live-replay capture",
        "inspect the current Ticket 03 job",
        "录入直播回放",
        "复盘已有报告",
        "keep that route fixed",
    ):
        assert marker in text


def test_kol_skill_has_a_bounded_under_ten_second_capture_ready_path() -> None:
    entrypoint = SKILL_MD.read_text(encoding="utf-8")

    assert XIAOCAO_CAPTURE_START_MD.is_file()
    fast_start = XIAOCAO_CAPTURE_START_MD.read_text(encoding="utf-8")
    flattened_entrypoint = " ".join(entrypoint.split())
    flattened_fast_start = " ".join(fast_start.split())

    assert len(fast_start.encode("utf-8")) < 6_000
    assert "xiaocao-capture-start.md" in entrypoint
    assert "within 10 seconds" in flattened_entrypoint
    assert "Do not read `full-contract.md` before Ready" in flattened_entrypoint
    for marker in (
        "scripts/kol_xiaocao_live.py run",
        "capture_armed",
        "Do not inspect Git",
        "Do not contact the remote writer",
        "not a long-lived daemon",
        "cancel-wait",
        "ports 2022/2023",
        "proxy",
    ):
        assert marker in flattened_fast_start


def test_kol_skill_handoffs_use_machine_read_full_git_sha() -> None:
    text = FULL_CONTRACT_MD.read_text(encoding="utf-8")

    assert "git rev-parse HEAD" in text
    assert "never expand a short SHA manually" in text
    assert "receiver must reject a mismatch" in text


def test_kol_skill_requires_complete_trade_information_coverage() -> None:
    text = FULL_CONTRACT_MD.read_text(encoding="utf-8")

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
    text = FULL_CONTRACT_MD.read_text(encoding="utf-8")

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


def test_kol_skill_preserves_session_identity_and_fact_check_boundaries() -> None:
    text = " ".join(FULL_CONTRACT_MD.read_text(encoding="utf-8").split())

    for marker in (
        "reader-facing date, session label, and episode label",
        "immutable source identity",
        "must not silently change an attributable label",
        "use neutral wording",
        "same-report content-and-manifest CAS correction",
        "UTC ISO-8601 timestamp ending in `Z`",
        "distinguish external confirmation from source consistency",
        "do not turn internal transcript consistency into a fact check",
        "fact-validation depth as limited",
        "stop before publication",
        "self-hashed market-validation request",
        "endpoint, parameters, trade date, selected rows, as-of time, and limitations",
        "supported, conflicting, or unresolved",
    ):
        assert marker in text


def test_kol_skill_cross_node_handoffs_are_self_contained_and_resumable() -> None:
    text = " ".join(FULL_CONTRACT_MD.read_text(encoding="utf-8").split())

    for marker in (
        "complete credential-free request JSON",
        "not only a remote filesystem path",
        "complete receipt JSON",
        "one control-plane coordinator",
        "item_id",
        "prerequisite_sha",
        "completed_gate",
        "next_gate",
        "never authorize a second Relay call, publication, or Book action",
        "handler error never authorizes redispatch",
    ):
        assert marker in text


def test_kol_skill_reuses_one_ticket04_listing_only_within_one_runner() -> None:
    text = " ".join(
        FULL_CONTRACT_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "one complete in-memory listing",
        "instead of rescanning",
        "never crosses a runner boundary",
        "exact identity, version, name, size, and browser target",
        "must never retrigger it",
    ):
        assert marker in text


def test_kol_skill_has_one_resumable_ticket05_cloud_video_runner() -> None:
    text = FULL_CONTRACT_MD.read_text(encoding="utf-8")

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


def test_hourly_semantic_stdin_eof_is_fail_resumable() -> None:
    text = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "Keep stdin open",
        "waiting_semantic_input",
        "preserving the original request, evidence SHA, and item claim",
        "reuses that exact request/evidence",
        "skips completed acquisition/transcript work",
        "never replays publication, notification, or Book effects",
        "Stop that adapter before later backlog items",
    ):
        assert marker in text


def test_hourly_small_download_is_unattended_and_prompt_is_internal() -> None:
    text = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "Page.setDownloadBehavior",
        "controlled inbox",
        "exact provider id/name/size/identity/version",
        "no user blocker or WeChat",
        "never edit ordinary Chrome",
        "global extension",
        "Only auth, SMS, CAPTCHA",
        "second UI trigger",
    ):
        assert marker in text


def test_kol_skill_has_one_resumable_ticket06_batch_runner() -> None:
    text = FULL_CONTRACT_MD.read_text(encoding="utf-8")

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
    text = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )

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
    text = FULL_CONTRACT_MD.read_text(encoding="utf-8")

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


def test_kol_skill_defers_the_full_contract_on_hourly_no_update_runs() -> None:
    entrypoint = SKILL_MD.read_text(encoding="utf-8")
    local = HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8")
    hourly = HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8")
    full = FULL_CONTRACT_MD.read_text(encoding="utf-8")
    entrypoint_flat = " ".join(entrypoint.split())
    hourly_flat = " ".join(hourly.split())

    assert len(entrypoint.encode("utf-8")) < 5_000
    assert len(local.encode("utf-8")) < 8_000
    assert len(hourly.encode("utf-8")) < 8_000
    assert len(full.encode("utf-8")) > 35_000
    assert (
        "Do not read the full contract before starting the runner"
        in entrypoint_flat
    )
    assert "Do not read `full-contract.md` unless the" in hourly_flat
    assert "daily_analysis_input_required" in entrypoint
    assert "daily_analysis_input_required" in hourly
    assert "Read `full-contract.md` completely before analysis" in hourly_flat
    assert "verify its current SHA-256 against the request" in hourly_flat


def test_hourly_local_and_remote_machine_contracts_stay_separate() -> None:
    entrypoint = SKILL_MD.read_text(encoding="utf-8")
    local = HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8")
    remote = HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8")

    assert "hourly-operation.md" not in entrypoint
    assert "scripts/kol_daily.py capture-local" in local
    assert "scripts/kol_daily.py run" not in local
    assert "daily_browser_input_required" in local
    assert "scripts/kol_daily.py run" in remote
    assert "daily_browser_input_required" not in remote
    assert "never scans the local WeChat contact" in remote


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
