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
HOURLY_LOCAL_NATIVE_CAPTURE_MD = (
    SKILL_DIR / "references" / "hourly-local-native-capture.md"
)
HOURLY_REMOTE_WRITER_MD = (
    SKILL_DIR / "references" / "hourly-remote-writer.md"
)
VIDEO_PLAYER_SAFETY_MD = (
    SKILL_DIR / "references" / "video-player-safety.md"
)
OPENCLI_EDGE_RECOVERY_MD = (
    SKILL_DIR / "references" / "opencli-edge-recovery.md"
)
REMOTE_WRITER_LEASE_MD = (
    SKILL_DIR / "references" / "remote-writer-lease.md"
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
    assert "conflicts from first principles without asking by default" in text
    assert "preserve a reversible snapshot and unrelated WIP" in text
    assert "irreducibly incompatible" in text


def test_kol_skill_owns_safe_self_repair_before_user_escalation() -> None:
    entrypoint = " ".join(SKILL_MD.read_text(encoding="utf-8").split())
    hourly = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )
    full = " ".join(FULL_CONTRACT_MD.read_text(encoding="utf-8").split())

    for marker in (
        "Repair before escalating",
        "without waiting for the user to request a retrospective",
        "repair_required",
        "commit and normally push",
        "never run the same hourly command twice",
    ):
        assert marker in entrypoint
    for marker in (
        "work for the current Agent, not a user blocker",
        "same stdin",
        "repair_required=true",
        "writer_progress.next_action",
        "matching repair closure",
        "narrow_resume_surface",
        "repository defect is never by itself `user_action_required`",
        "raw `waiting` result without an immutable provider",
        "convergence-report",
        "rollout-readback",
    ):
        assert marker in hourly
    for marker in (
        "Agent-owned self-repair",
        "add a regression",
        "must not send a user-action notification",
        "preserve the original job",
    ):
        assert marker in full


def test_kol_local_capture_owns_bounded_native_activation_and_rechecks() -> None:
    local = " ".join(
        HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8").split()
    )
    native = " ".join(
        HOURLY_LOCAL_NATIVE_CAPTURE_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "native WeChat mini-program",
        "20 分钟",
        "wechat_client_login_required",
        "keep the same identity/job",
        "one deduplicated user action even from `resume-source-repair`",
    ):
        assert marker in local
    for marker in (
        "activate_xiaoetong_mini_program",
        "Agent owns the native WeChat UI",
        "read state back after each semantic action",
        "no evidence for a magic safe interval",
        "Do not use coordinates, hooks, injection, webhooks, storage/cookie",
        "at most one activation attempt per scheduled boundary",
        "Retain only `app_id`, `pro_id`, `type`, `alive_mode`, stripping share IDs",
        "SMS/OTP, CAPTCHA, consent, or shows an explicit protection screen",
        "return `wechat_client_login_required` and stop",
        "Never return signed URLs, cookies, keys, or request headers",
    ):
        assert marker in native


def test_hourly_local_native_details_are_mandatory_at_the_relevant_stage() -> None:
    local = HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8")
    target = HOURLY_LOCAL_NATIVE_CAPTURE_MD.name
    routes = [
        " ".join(paragraph.split())
        for paragraph in local.split("\n\n")
        if f"]({target})" in paragraph
    ]

    assert HOURLY_LOCAL_NATIVE_CAPTURE_MD.is_file()
    assert len(routes) == 1
    route = routes[0]
    for marker in (
        "Before native launch resolution",
        "`resolve_xiaoetong_page`",
        "`activate_xiaoetong_mini_program`",
        "continuation/acceptance of an existing native capture",
        f"read [{target}]({target}) completely",
        "mandatory for resumed jobs",
        "No-update discovery needs only this entry reference",
    ):
        assert marker in route
    for detail in ("launch_resolver_command", "playlist_eof.m3u8", "view=capture"):
        assert detail not in local
        assert detail in HOURLY_LOCAL_NATIVE_CAPTURE_MD.read_text(encoding="utf-8")


def test_hourly_local_native_launch_preserves_readiness_and_verified_identity() -> None:
    native = " ".join(
        HOURLY_LOCAL_NATIVE_CAPTURE_MD.read_text(encoding="utf-8").split()
    )
    local = " ".join(HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8").split())

    for marker in (
        "Before every native activation prompt, the driver restores and checks",
        "a historical armed receipt is not current process health",
        "Verify/apply the bounded capture PAC only after that health check",
        "preserve inherited PATH precedence and append installed Homebrew CLI directories",
        "Run the emitted `launch_resolver_command` with `PYTHONPATH=src`",
        "ignores the page's mock branch",
        "`weixin://dl/business/?t=...` ticket embeds that exact replay",
        "Do not invent tickets, app IDs or page paths",
        "armed and `/proxy.pac` is healthy and applied, execute `launch_command` once",
        "If the target mini-program is already open, reuse it",
        "Regenerate the merchant ticket only for that one activation",
        "Once the exact course is visible, do not resolve again",
        "focus the visible course-password input, enter `666` once",
        "then press Play once and Pause once",
        "No hooks, WeChat re-signing, hidden debugging, CDP/DOM evaluation",
        "If the resolver cannot prove a ticket, use the original visible message entry",
        "A launch plan is not playback, download or upload acceptance",
    ):
        assert marker in native
    for marker in (
        "must not be used as a download fallback",
        "Use `--xiaoetong-only`",
        "Keep WeChat login/security domains DIRECT and disable the PAC when stopping",
        "keep the Automation PAUSED and run offline checks only until explicit confirmation",
    ):
        assert marker in local


def test_hourly_local_native_continuation_requires_bound_media_and_cleaned_audit() -> None:
    native = " ".join(
        HOURLY_LOCAL_NATIVE_CAPTURE_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "`view=capture`: fresh observed IDs/times only",
        "they cannot bind a source",
        "observed candidate ID, app ID, live ID and post-arm time before downloading",
        "`media_request_observed=true` only when the singleton "
        "`wx_channels_download` sniffer saw the target request",
        "`liveplay` request alone is not a finite replay",
        "only the newly observed candidate bound to the exact `live_id` and finite playlist",
        "same `type=live_capture`, `compress=true` task",
        "validates the resulting `-compressed.mp4`",
        "An H5 identity anchor can never be reported as download success",
        "exact-source media observation -> original compressed download -> "
        "media validation -> detach only the capture PAC and stop the sniffer -> "
        "original Netdisk upload -> hash-bound mailbox handoff -> "
        "authoritative end-to-end readback",
        "Do not insert a new permanent stop after native playback",
        "persisted, exact candidate/source/task receipt and rechecks local media hashes",
        "must not restart or query the cleaned sniffer merely to pass audit",
        "A mismatched saved task fails closed",
    ):
        assert marker in native


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
        "Agent opens the target",
        "do not ask the user",
        "event-based waits",
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


def test_kol_skill_treats_lv_macheng_as_the_current_cycle_core_pool() -> None:
    text = " ".join(FULL_CONTRACT_MD.read_text(encoding="utf-8").split())

    for marker in (
        "吕晓彤“马车”周期推荐池",
        "current-cycle core recommendation pool",
        "stable user-provided author/product fact",
        "Every ETF, stock, or theme",
        "role `primary_recommendation`",
        "does not demote it to a generic watchlist",
        "priority research and screening universe",
        "longitudinal_projection.status=promoted",
        "latest current `马车` viewpoint",
        "appends an `expired` evaluation",
        "with `replaces`",
        "partial add/remove amendment uses `refines`",
        "additions, removals, and unchanged members",
        "current direction choice",
        "is `alert_eligible`",
        "creates no reminder or Book replay",
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


def test_kol_skill_requires_paused_and_closed_baidu_transcript_players() -> None:
    hourly = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )
    full = " ".join(FULL_CONTRACT_MD.read_text(encoding="utf-8").split())
    safety = " ".join(
        VIDEO_PLAYER_SAFETY_MD.read_text(encoding="utf-8").split()
    )

    for text in (hourly, full, safety):
        assert "pause guard" in text
        assert "paused" in text
        assert "close" in text
        assert "repair_required" in text
    assert "吕晓彤" in full
    assert "小草" in full
    assert "muting is not a substitute for pausing" in full
    assert "do not keep the page open" in full
    for marker in (
        "video.paused=true",
        "DOM completeness",
        "SHA-256",
        "page ID",
        "tab list",
        "Do not continue to analysis",
    ):
        assert marker in safety


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
        "exact provider identity",
        "Save prompt is not a user blocker",
        "never edit the ordinary Microsoft Edge profile",
        "global extension",
        "Only auth, SMS, CAPTCHA",
        "second trigger",
    ):
        assert marker in text


def test_hourly_remote_scopes_no_mcp_to_capture() -> None:
    text = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "no-MCP capture rule",
        "repository-designated LiangHui client",
        "read-only exact-receipt reconciliation",
        "materially incompatible business outcomes",
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


def test_kol_skill_has_one_ticket07_scheduled_runner() -> None:
    text = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "scripts/kol_daily.py run",
        "scripts/kol_daily.py status",
        "scripts/kol_daily.py audit",
        "scripts/kol_daily.py convergence-report",
        "/课程/路西法全套",
        "never reads or downloads source-video bytes",
        "content_value.status=low_density|promoted",
        "content_value.tier=report_only|alert_eligible",
        "Missing independent verification",
        "no uniquely mapped instrument",
        "stable URL before Book KOL-US or reminder",
        "viewpoint_triggers",
        "material fact",
        "no concrete item is silent",
        "Report concrete waits and exceptions",
        '"image_notes_path":"<absolute-md-path>"',
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

    assert len(entrypoint.encode("utf-8")) < 7_000
    assert len(local.encode("utf-8")) < 8_000
    assert len(hourly.encode("utf-8")) < 12_000
    assert len(full.encode("utf-8")) > 35_000
    assert (
        "Do not read the full contract before starting the runner"
        in entrypoint_flat
    )
    assert "Do not read `full-contract.md` unless the" in hourly_flat
    assert "daily_analysis_input_required" in entrypoint
    assert "daily_analysis_input_required" in hourly
    assert "semantic-model-routing.md" in entrypoint
    assert "semantic-model-routing.md" in hourly
    assert "Read `full-contract.md` completely before acceptance" in hourly_flat
    assert "its current hash must match the request" in hourly_flat
    route = SKILL_DIR.joinpath("references/semantic-model-routing.md").read_text(encoding="utf-8")
    for marker in (
        "gpt-6-astra", "reasoning_effort=xhigh", "fork_context=false",
        "one Xiaocao pilot", "independently reads the full",
        "parent_source_review.json", "parent_accepted", "empty queues do not spawn",
    ):
        assert marker in route


def test_hourly_local_and_remote_machine_contracts_stay_separate() -> None:
    entrypoint = SKILL_MD.read_text(encoding="utf-8")
    local = HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8")
    remote = HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8")

    assert "hourly-operation.md" not in entrypoint
    assert "scripts/kol_daily.py capture-local" in local
    assert "scripts/kol_daily.py run" not in local
    assert "daily_browser_input_required" in local
    assert "wechat_official_accounts" in local
    assert "subscription-updates --within 48h" in local
    assert "刘少狙击营" in local
    assert "A也叫艾利克斯" in local
    assert "scripts/kol_daily.py run" in remote
    assert "scripts/kol_daily.py process-wechat-official" in remote
    assert "interactive PTY (`tty=true`)" in local
    assert "normal handoff path does not inject a" in local
    assert "scripts/kol_daily.py viewpoints" in remote
    assert "longitudinal_projection" in remote
    assert "longitudinal_projection" in FULL_CONTRACT_MD.read_text(
        encoding="utf-8"
    )
    assert "not the full article" in remote
    assert "daily_browser_input_required" not in remote
    assert "never scans the local\nWeChat contact" in remote


def test_hourly_local_handoff_uses_lianghui_mailbox_creation_readback() -> None:
    local = HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8")

    for marker in (
        "send_mailbox_message",
        "created|already_present",
        "Handoff完成",
        "get_mailbox_message",
        "全部完成",
        "same `handoff_id`",
    ):
        assert marker in local
    assert "remote-writer-lease.md" not in local
    assert "no remote task discovery" in local


def test_hourly_local_capture_recovers_late_video_handoffs_without_resweep() -> None:
    local = " ".join(HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8").split())

    assert "capture-xiaocao-handoff" in local
    assert "do not rerun the full sweep" in local
    assert "cloud_handoff_published" in local
    assert "same `capture-local` process" in local
    assert "created|already_present" in local
    assert "must not end the task" in local


def test_remote_writer_guards_active_peer_and_drains_each_message_once() -> None:
    remote = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").lower().split()
    )

    for marker in (
        "same automation id",
        "current host",
        "current working directory",
        "exclude the current task",
        "active peer",
        "peer task",
        "authoritative 12-hour `updatedat` window",
        "complete all-page pagination",
        "5 why",
        "blocks business effects, not repair",
        "never defer to the next automation",
        "attempted_message_ids",
        "new eligible messages",
        "ack_mailbox_message",
        "get_mailbox_message",
        "validate-repair",
        "repairvalidationreceipt",
        "generic waits",
        "duplicate-effect audits",
        "seven-day/50-scheduled-slot",
        "全部完成",
    ):
        assert marker in remote
    assert (
        "do not add a python global lock, lease, heartbeat, fencing token, "
        "or stale takeover"
    ) in remote


def test_remote_writer_owns_reporting_and_acceptance_copy() -> None:
    remote = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").split()
    )

    for marker in (
        "`对象 | 状态 | 说明`",
        "`[视频]`",
        "`[文章]`",
        "never label `Handoff完成` as `全部完成`",
        "`--period-end <as_of>`",
        "`pending_observation` is not completion",
        "only `passed` closes Issue 06",
        "explicit new rollout",
        "never historical backfill or a second hourly writer",
    ):
        assert marker in remote


def test_kol_skill_repairs_recoverable_failures_in_the_current_task() -> None:
    skill = " ".join(SKILL_MD.read_text(encoding="utf-8").lower().split())
    remote = " ".join(
        HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8").lower().split()
    )

    for marker in (
        "minimize dependence on the user",
        "5-why",
        "first-principles diagnosis",
        "correct invalid tool arguments immediately",
        "do not defer work",
    ):
        assert marker in skill
    for marker in (
        "resume-mailbox",
        "do not defer obtainable work",
        "in this task",
        "repair_required",
    ):
        assert marker in remote


def test_full_contract_applies_five_why_to_every_recoverable_failure() -> None:
    full = " ".join(
        FULL_CONTRACT_MD.read_text(encoding="utf-8").lower().split()
    )

    for marker in (
        "minimize dependence on the user",
        "apply 5 why",
        "every recoverable code, environment, tool, provider, schema",
        "control-plane failure",
        "fail-closed blocks unsafe effects, not repair",
        "instead of deferring to the user or a later run",
    ):
        assert marker in full


def test_remote_writer_has_a_xiaocao_only_post_handoff_entrypoint() -> None:
    local = HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8")
    remote = HOURLY_REMOTE_WRITER_MD.read_text(encoding="utf-8")

    assert "scripts/kol_daily.py process-xiaocao-handoff" in remote
    assert "do not rerun the full `run` command" in remote


def test_opencli_edge_recovery_exhausts_self_repair_before_user_action() -> None:
    entrypoint = SKILL_MD.read_text(encoding="utf-8")
    recovery = OPENCLI_EDGE_RECOVERY_MD.read_text(encoding="utf-8")

    assert "opencli-edge-recovery.md" in entrypoint
    for marker in (
        "opencli daemon status",
        "opencli doctor",
        'open -a "Microsoft Edge"',
        "Restart the OpenCLI daemon at most once",
        "credentialed `/api/list`",
        "Computer Use is allowed only for the minimum Edge UI",
        "click **Keep**, enable Developer mode, and enable",
        "Without that explicit",
        "Preferences/Secure Preferences",
        "prefer **账号登录** over QR or SMS",
        "Edge's already-saved Baidu",
        "Never inspect,",
        "never duplicate",
    ):
        assert marker in recovery

    assert "Google Chrome" not in recovery


def test_hourly_local_capture_sunsets_xiaoetong_web_login() -> None:
    entrypoint = " ".join(SKILL_MD.read_text(encoding="utf-8").split())
    hourly = HOURLY_LOCAL_CAPTURE_MD.read_text(encoding="utf-8")

    assert "xiaoetong-sms-login.md" not in entrypoint
    assert "xiaoetong-sms-login.md" not in hourly
    for marker in (
        "H5 is a credential-free identity anchor",
        "semantically enter `666` if visible, Play once, Pause once",
        "never use coordinates, CDP/DOM evaluation",
    ):
        assert marker in entrypoint


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
