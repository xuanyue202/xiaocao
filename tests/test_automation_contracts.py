from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _automation(name: str) -> dict:
    path = ROOT / ".codex" / "automations" / name / "automation.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_1425_precheck_and_1455_execution_are_separate_wakeups() -> None:
    precheck = _automation("xiaocao-intraday-risk-precheck-1425")
    closing = _automation("xiaocao-intraday-monitor-1455")

    assert precheck["id"] != closing["id"]
    assert "BYHOUR=14;BYMINUTE=25" in precheck["rrule"]
    assert "never wait for 14:55" in precheck["prompt"]
    assert "BYHOUR=14;BYMINUTE=55" in closing["rrule"]
    assert "BYMINUTE=25,55" not in closing["rrule"]
    assert "do not wait" in closing["prompt"]


def test_morning_automations_separate_user_visible_prerecommend_from_execution() -> None:
    prerecommend = _automation("xiaocao-daily-morning")
    execution = _automation("xiaocao-daily-morning-execution")

    assert prerecommend["id"] != execution["id"]
    assert "BYHOUR=9;BYMINUTE=23" in prerecommend["rrule"]
    assert "morning-prerecommend" in prerecommend["prompt"]
    assert "final/inbox" in prerecommend["prompt"]
    assert "before any agent review" in prerecommend["prompt"]
    assert "missing signal capture is a deterministic failure" in prerecommend["prompt"]
    assert "must not suppress ★E" in prerecommend["prompt"]
    assert "do not paper-record" in prerecommend["prompt"]

    assert "BYHOUR=9;BYMINUTE=25" in execution["rrule"]
    assert "morning-execute" in execution["prompt"]
    assert "never rerun live_recommend" in execution["prompt"]
    assert "bounded agent-review rendezvous" in execution["prompt"]
    assert "agent_intelligence_review.py" in execution["prompt"]
    assert "never use keyword scoring" in execution["prompt"]


def test_live_morning_is_a_separate_0920_fail_closed_task() -> None:
    live = _automation("xiaocao-book-b-live-morning")
    paper = _automation("xiaocao-daily-morning-execution")

    assert live["id"] != paper["id"]
    assert live["rrule"].endswith(";BYHOUR=9;BYMINUTE=20")
    assert "scripts/book_b_live_morning.py" in live["prompt"]
    assert "--route timed-order" in live["prompt"]
    assert "dated deterministic freeze" in live["prompt"]
    assert "broker-sourced allocation facts" in live["prompt"]
    assert "never run or wait for `morning-execute`" in live["prompt"]
    assert "never read or write simulated fills" in live["prompt"]
    assert "NO_ROUTE_PROVEN" in live["prompt"]
    assert "auto_daily.sh" not in live["prompt"]
    assert "book_b_live_morning.py" not in paper["prompt"]
    live_script = (ROOT / "scripts" / "book_b_live_morning.py").read_text(
        encoding="utf-8"
    )
    assert "release_foundersc_opencli_site_session(profile)" in live_script


def test_auto_daily_exposes_separate_morning_stage_commands() -> None:
    script = (ROOT / "scripts" / "auto_daily.sh").read_text(encoding="utf-8")

    assert 'BASH_SOURCE[0]' in script
    assert '$HOME/coding/xiaocao' not in script
    assert 'export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"' in script
    assert "morning-prerecommend)" in script
    assert "morning-execute)" in script
    assert "wait_for_morning_freeze.py" in script
    execute_branch = script.split("morning-execute)", 1)[1].split(";;", 1)[0]
    assert "live_recommend.py" not in execute_branch


def test_intraday_automations_use_explicit_china_market_wall_clock() -> None:
    opening = _automation("xiaocao-intraday-monitor")
    sparse = _automation("xiaocao-intraday-monitor-05")

    assert opening["rrule"] == (
        "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=35,45,55"
    )
    assert sparse["rrule"] == (
        "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=10,13;BYMINUTE=25,55"
    )


def test_all_china_market_automations_use_dtstart_free_local_wall_clock() -> None:
    expected = {
        "xiaocao-daily-morning": ("BYHOUR=9", "BYMINUTE=23"),
        "xiaocao-daily-morning-execution": ("BYHOUR=9", "BYMINUTE=25"),
        "xiaocao-book-b-live-morning": ("BYHOUR=9", "BYMINUTE=20"),
        "xiaocao-intraday-monitor": ("BYHOUR=9", "BYMINUTE=35,45,55"),
        "xiaocao-intraday-monitor-05": ("BYHOUR=10,13", "BYMINUTE=25,55"),
        "xiaocao-intraday-risk-precheck-1425": ("BYHOUR=14", "BYMINUTE=25"),
        "xiaocao-intraday-monitor-1455": ("BYHOUR=14", "BYMINUTE=55"),
        "xiaocao-daily-eod": ("BYHOUR=15", "BYMINUTE=10"),
        "xiaocao-weekly-deep-review": ("BYHOUR=20", "BYMINUTE=30"),
    }

    for name, wall_clock_parts in expected.items():
        rrule = _automation(name)["rrule"]
        assert "DTSTART" not in rrule
        assert "TZID" not in rrule
        assert all(part in rrule for part in wall_clock_parts)


def test_kol_local_automation_uses_lianghui_mailbox_without_task_injection() -> None:
    automation = _automation("xiaocao-kol-hourly")

    assert "daily_lianghui_mailbox_input_required" in automation["prompt"]
    assert "send_mailbox_message" in automation["prompt"]
    assert "get_mailbox_message" in automation["prompt"]
    assert "Handoff完成" in automation["prompt"]
    assert "Never use `send_message_to_thread`" in automation["prompt"]
    assert automation["rrule"].endswith(";BYMINUTE=0")


def test_kol_remote_writer_automation_is_a_thin_fail_closed_bootstrap() -> None:
    automation = _automation("xiaocao-kol-hourly-remote-writer")
    prompt = automation["prompt"]

    assert automation["id"] == "xiaocao-kol-hourly-low-bandwidth-operation"
    assert automation["name"] == "xiaocao KOL hourly remote writer"
    assert automation["cwds"] == [
        "/Users/xuanyue202/Documents/project/xiaocao"
    ]
    assert automation["rrule"] == (
        "RRULE:FREQ=DAILY;"
        "BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;"
        "BYMINUTE=30"
    )
    assert "DTSTART" not in automation["rrule"]
    assert "TZID" not in automation["rrule"]

    for marker in (
        "kol-intelligence",
        "references/hourly-remote-writer.md",
        "MacBook-Pro-6.local",
        "node scripts/codex_peer_gate.js",
        "读取 mailbox、status、convergence 前",
        "`pass` 才可继续",
        "`no_op` 立即结束",
        "`repair_required` 或没有有效结构化结果",
        "不得改用桌面 thread wrapper",
        "runner 签发的 exact continuation",
        "`structured_input`",
        "`writer_progress.status=terminal`",
        "`next_action=stop`",
        "claim=receipt",
        "uncertain=0",
        "5 Why",
        "exact narrow resume",
        "`对象 | 状态 | 说明`",
        "`[视频]`",
        "`[文章]`",
        "空队列静默",
    ):
        assert marker in prompt

    for implementation_detail in (
        "initialize",
        "thread/list",
        "thread/read",
        "sourceKinds",
        "useStateDbOnly",
        "video.paused=true",
        "stability-acceptance",
    ):
        assert implementation_detail not in prompt
    assert len(prompt) < 2_200
