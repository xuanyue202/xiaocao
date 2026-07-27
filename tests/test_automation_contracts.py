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
    assert "do not paper-record" in prerecommend["prompt"]

    assert "BYHOUR=9;BYMINUTE=25" in execution["rrule"]
    assert "morning-execute" in execution["prompt"]
    assert "never rerun live_recommend" in execution["prompt"]
    assert "bounded agent-review rendezvous" in execution["prompt"]
    assert "agent_intelligence_review.py" in execution["prompt"]
    assert "never use keyword scoring" in execution["prompt"]


def test_auto_daily_exposes_separate_morning_stage_commands() -> None:
    script = (ROOT / "scripts" / "auto_daily.sh").read_text(encoding="utf-8")

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
