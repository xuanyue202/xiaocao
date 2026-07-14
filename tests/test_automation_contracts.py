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
    assert "BYMINUTE=25" in precheck["rrule"]
    assert "never wait for 14:55" in precheck["prompt"]
    assert "BYMINUTE=55" in closing["rrule"] or "T065500" in closing["rrule"]
    assert "BYMINUTE=25,55" not in closing["rrule"]
    assert "do not wait" in closing["prompt"]


def test_morning_automation_is_the_agent_review_producer() -> None:
    morning = _automation("xiaocao-daily-morning")
    assert "bounded agent-review rendezvous" in morning["prompt"]
    assert "agent_intelligence_review.py" in morning["prompt"]
    assert "never use keyword scoring" in morning["prompt"]
