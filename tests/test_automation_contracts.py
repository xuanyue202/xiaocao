"""Check deployment wiring; prose and model preferences are reviewed as text.

These offline checks do not run an automation or contact a trading service.
Trading behavior is covered by the execution, lifecycle and safety suites.
"""
from __future__ import annotations

import tomllib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _automation(name: str) -> dict:
    path = ROOT / ".codex" / "automations" / name / "automation.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_market_schedules_keep_distinct_ids_and_china_wall_clock() -> None:
    expected = {
        "xiaocao-daily-morning": ("9", "18"),
        "xiaocao-daily-morning-execution": ("9", "10"),
        "xiaocao-book-b-live-morning": ("8", "53"),
        "xiaocao-intraday-monitor": ("9", "35,45,55"),
        "xiaocao-intraday-monitor-05": ("10,13", "25,55"),
        "xiaocao-intraday-risk-precheck-1425": ("14", "18"),
        "xiaocao-intraday-monitor-1455": ("14", "38"),
        "xiaocao-daily-eod": ("15", "3"),
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


@pytest.mark.parametrize(('app_exit', 'paper_exit'), [(0, 0), (2, 0), (0, 3), (2, 3)])
def test_closing_dispatches_native_once_before_paper_work(tmp_path, app_exit, paper_exit) -> None:
    prompt = _automation("xiaocao-intraday-monitor-1455")["prompt"]
    entry = "scripts/book_b_live_closing_startup.sh"
    assert entry in prompt
    launcher = tmp_path / entry
    launcher.parent.mkdir()
    launcher.write_bytes((ROOT / entry).read_bytes())
    executable = tmp_path / '.venv/bin/python'
    executable.parent.mkdir(parents=True)
    executable.write_text(f'''#!{sys.executable}
import json, os, sys
with open(os.environ['CALLS_PATH'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if 'scripts/book_b_live_intraday.py' in sys.argv:
    sys.exit(int(os.environ['APP_EXIT']))
if 'scripts/live_monitor.py' in sys.argv:
    sys.exit(int(os.environ['PAPER_EXIT']))
''')
    executable.chmod(0o700)
    # Reference reads are not the behavior under test and must not read the
    # operator's actual Automation memory from this isolated shell harness.
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    for name in ('sed', 'rg'):
        script = fake_bin / name
        script.write_text('#!/bin/sh\nexit 0\n')
        script.chmod(0o700)
    calls = tmp_path / 'calls.jsonl'
    env = {**os.environ, 'PATH': str(fake_bin) + os.pathsep + os.defpath,
        'CODEX_AUTOMATION_ID': 'xiaocao-intraday-monitor-1455', 'CODEX_THREAD_ID': 'test-owner',
        'CALLS_PATH': str(calls), 'APP_EXIT': str(app_exit), 'PAPER_EXIT': str(paper_exit)}
    result = subprocess.run(['bash', str(launcher)], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=10)
    assert result.returncode == (app_exit or paper_exit), result.stderr
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        ['-m', 'xiaocao.live.closing_startup'],
        ['scripts/book_b_live_intraday.py', '--date', 'today', '--phase', 'closing', '--execute-sells'],
        ['scripts/live_monitor.py', '--execute-sells'],
        ['scripts/research_book_b_forward.py', '--phase', 'monitor', '--checkpoint-phase', 'closing'],
    ]


def test_nonsemantic_daytime_tasks_cannot_start_kol_publication() -> None:
    for name in (
        "xiaocao-intraday-monitor",
        "xiaocao-intraday-risk-precheck-1425",
        "xiaocao-intraday-monitor-1455",
        "xiaocao-daily-eod",
    ):
        prompt = _automation(name)["prompt"]
        assert "delegate only semantic judgment" not in prompt
        assert "kol_trading_decision.py publish" not in prompt


def test_remote_writer_routes_to_its_identity_gated_entrypoint() -> None:
    remote = _automation("xiaocao-kol-hourly-remote-writer")
    commands = [shlex.split(command) for command in re.findall(r'`([^`]+)`', remote['prompt'])
                if 'scripts/kol_automation_slot_gate.py' in command]
    assert len(commands) == 1
    command = commands[0]
    assert f"CODEX_AUTOMATION_ID={remote['id']}" in command
    assert command[command.index('--automation-id') + 1] == remote['id']
    assert command[command.index('--') + 1:] == ['.venv/bin/python', 'scripts/kol_daily.py', 'run']
    assert (ROOT / 'scripts/kol_automation_slot_gate.py').is_file()
    assert (ROOT / 'scripts/kol_daily.py').is_file()


def test_kol_writers_stay_on_separate_hosts_and_schedules() -> None:
    local = _automation("xiaocao-kol-hourly")
    remote = _automation("xiaocao-kol-hourly-remote-writer")
    assert local["id"] != remote["id"]
    assert local["target"] != remote["target"]
    assert local["cwds"] == ["/Users/bytedance/coding/xiaocao"]
    assert remote["cwds"] == ["/Users/xuanyue202/Documents/project/xiaocao"]
    assert local["rrule"].endswith(";BYMINUTE=0,20,40")
    # Hour selections are reviewed scheduling preferences. The deployment test
    # protects China wall-clock syntax and the separate writer, not an old hour.
    assert 'DTSTART' not in remote['rrule'] and 'TZID' not in remote['rrule']
    parts = dict(part.split('=', 1) for part in remote['rrule'].removeprefix('RRULE:').split(';'))
    assert parts['FREQ'] == 'DAILY'
    assert all(0 <= int(hour) < 24 for hour in parts['BYHOUR'].split(','))
    assert all(0 <= int(minute) < 60 for minute in parts['BYMINUTE'].split(','))
