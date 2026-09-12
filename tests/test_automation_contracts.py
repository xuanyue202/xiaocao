"""Check deployment wiring; prose and model preferences are reviewed as text.

These offline checks do not run an automation or contact a trading service.
Trading behavior is covered by the execution, lifecycle and safety suites.
"""
from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _automation(name: str) -> dict:
    path = ROOT / ".codex" / "automations" / name / "automation.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_market_schedules_keep_distinct_ids_and_china_wall_clock() -> None:
    expected = {
        "xiaocao-daily-morning": ("9", "23"),
        "xiaocao-daily-morning-execution": ("9", "25"),
        "xiaocao-book-b-live-morning": ("9", "15"),
        "xiaocao-intraday-monitor": ("9", "35,45,55"),
        "xiaocao-intraday-monitor-05": ("10,13", "25,55"),
        "xiaocao-intraday-risk-precheck-1425": ("14", "25"),
        "xiaocao-intraday-monitor-1455": ("14", "55"),
        "xiaocao-daily-eod": ("15", "10"),
        "xiaocao-weekly-deep-review": ("20", "30"),
    }
    ids = []
    for name, (hour, minute) in expected.items():
        automation = _automation(name)
        ids.append(automation["id"])
        rrule = automation["rrule"]
        assert "DTSTART" not in rrule and "TZID" not in rrule
        parts = dict(part.split("=", 1) for part in rrule.removeprefix("RRULE:").split(";"))
        assert parts["BYHOUR"] == hour
        assert parts["BYMINUTE"] == minute
    assert len(ids) == len(set(ids))


def test_morning_tasks_route_to_separate_entrypoints() -> None:
    prerecommend = _automation("xiaocao-daily-morning")["prompt"]
    paper = _automation("xiaocao-daily-morning-execution")["prompt"]
    native = _automation("xiaocao-book-b-live-morning")["prompt"]
    assert "morning-prerecommend" in prerecommend
    assert "morning-execute" in paper
    assert "scripts/book_b_live_morning.py --date today --route native-app" in native
    assert "book_b_live_morning.py" not in paper


def test_closing_dispatches_native_once_before_paper_work() -> None:
    prompt = _automation("xiaocao-intraday-monitor-1455")["prompt"]
    startup_command = "bash scripts/book_b_live_closing_startup.sh"
    paper_command = "scripts/live_monitor.py --execute-sells"
    assert prompt.index(startup_command) < prompt.index(paper_command)
    startup = (ROOT / "scripts/book_b_live_closing_startup.sh").read_text()
    live_command = "scripts/book_b_live_intraday.py --date today --phase closing --execute-sells"
    assert startup.count(live_command) == 1
    before_live = startup.split(live_command, 1)[0]
    for unrelated_work in ("live_monitor.py", "data_doctor.py", "git status", "kol_trading_decision.py"):
        assert unrelated_work not in before_live


def test_paper_execution_stage_does_not_regenerate_recommendations() -> None:
    script = (ROOT / "scripts/auto_daily.sh").read_text()
    execute_branch = script.split("morning-execute)", 1)[1].split(";;", 1)[0]
    assert "wait_for_morning_freeze.py" in execute_branch
    assert "live_recommend.py" not in execute_branch


def test_kol_writers_stay_on_separate_hosts_and_schedules() -> None:
    local = _automation("xiaocao-kol-hourly")
    remote = _automation("xiaocao-kol-hourly-remote-writer")
    assert local["id"] != remote["id"]
    assert local["target"] != remote["target"]
    assert local["cwds"] == ["/Users/bytedance/coding/xiaocao"]
    assert remote["cwds"] == ["/Users/xuanyue202/Documents/project/xiaocao"]
    assert local["rrule"].endswith(";BYMINUTE=0,20,40")
    assert remote["rrule"] == "RRULE:FREQ=DAILY;BYHOUR=8,10,12,14,17,18,22;BYMINUTE=30"
