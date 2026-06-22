"""Tests for the flywheel self-check (src/xiaocao/live/flywheel.py) and the
strategy-blocked escalation (scripts/flywheel_selfcheck.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from xiaocao.live import flywheel

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import flywheel_selfcheck as fsc  # noqa: E402


def _wire_repo(tmp_path, *, with_optimize=True, with_data=True):
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    steps = "morning)\n  ;;\neod)\n  ;;\n" + ("optimize)\n  ;;\n" if with_optimize else "")
    (tmp_path / "scripts" / "auto_daily.sh").write_text(f"case $STEP in\n{steps}esac\n", encoding="utf-8")
    live = tmp_path / "output" / "live"
    live.mkdir(parents=True, exist_ok=True)
    (live / "decision_journal.jsonl").write_text(json.dumps({"automation": "live_monitor"}) + "\n", encoding="utf-8")
    (live / "paper_account.json").write_text("{}", encoding="utf-8")
    (live / "paper_account_A.json").write_text("{}", encoding="utf-8")
    (tmp_path / "kronos_screen").mkdir(parents=True, exist_ok=True)
    (tmp_path / "kronos_screen" / "HYPOTHESES.jsonl").write_text(json.dumps({"id": "x", "verdict": "REJECTED"}) + "\n", encoding="utf-8")
    if with_data:
        # pandas/pyarrow are an OPTIONAL extra (training_rows is a metric, not load-bearing —
        # _parquet_rows degrades to 0/None without it). Write the fixture parquet only when
        # available so the 6 tests that DON'T assert on training_rows still run pandas-free;
        # the one test that does asserts via pytest.importorskip.
        try:
            import pandas as pd
            pd.DataFrame([{"date": "2026-06-01", "net_realized_ret": 1.0}]).to_parquet(live / "training_rows.parquet")
        except ImportError:
            pass
    return tmp_path


def test_fully_wired_repo_is_spinning(tmp_path):
    pytest.importorskip("pandas")  # this test asserts training_rows == 1, which needs the parquet
    root = _wire_repo(tmp_path)
    # no live authorization + env without the live flag -> paper-only holds.
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["spinning"] is True
    assert r["capital_flywheel"]["safety_paper_only"] is True
    assert r["capital_flywheel"]["automation_complete"] is True
    assert r["capability_flywheel"]["optimize_step_wired"] is True
    assert r["capability_flywheel"]["training_rows"] == 1


def test_three_flywheels_and_rings_reported(tmp_path):
    root = _wire_repo(tmp_path)
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["capital_flywheel"]["status"] == "spinning"
    assert r["capability_flywheel"]["status"] == "wired"
    # ③ actuator is a human gate; with no PASS pending it idles "open" (by design),
    # NOT closed — and the big three-ring loop is honestly reported as not closed.
    assert r["strategy_flywheel"]["status"] == "open"
    assert r["strategy_flywheel"]["actuator_wired"] is False
    assert isinstance(r["strategy_flywheel"]["params_frozen"], bool)
    assert r["rings"]["fully_closed"] is False
    assert r["rings"]["strategy_to_capital"] is False


def test_strategy_blocked_when_pass_pending_without_actuator(tmp_path):
    # A validated edge (latest verdict PASS) with no actuator wired is a REAL gap,
    # not a by-design idle — strategy goes 🔴 blocked and a STRATEGY warning fires.
    root = _wire_repo(tmp_path)
    (root / "kronos_screen" / "HYPOTHESES.jsonl").write_text(
        json.dumps({"id": "edge1", "verdict": "PASS"}) + "\n", encoding="utf-8")
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["strategy_flywheel"]["status"] == "blocked"
    assert r["strategy_flywheel"]["pending_pass_verdicts"] == ["edge1"]
    assert r["rings"]["capability_to_strategy"] is True
    assert any("STRATEGY" in w for w in r["warnings"])
    # the operational loops still turn -> spinning (and the exit code) is unaffected
    assert r["spinning"] is True


def test_superseded_pass_is_not_pending(tmp_path):
    # latest-verdict-wins: a PASS later superseded by a REJECTED is not pending.
    root = _wire_repo(tmp_path)
    (root / "kronos_screen" / "HYPOTHESES.jsonl").write_text(
        json.dumps({"id": "edge1", "verdict": "PASS"}) + "\n"
        + json.dumps({"id": "edge1", "verdict": "REJECTED"}) + "\n", encoding="utf-8")
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["strategy_flywheel"]["pending_pass_verdicts"] == []
    assert r["strategy_flywheel"]["status"] == "open"


def test_blocked_escalation_pushes_wecom_with_runbook(tmp_path):
    # When ③ is blocked, eod's `--notify-blocked` must escalate to a human with the
    # do-NOT-auto-change-params runbook, naming the pending hypothesis.
    calls = []

    def poster(url, payload, *, headers=None, verify=True):
        calls.append(payload)
        return 200, '{"ok":true}'

    report = {"strategy_flywheel": {"status": "blocked", "pending_pass_verdicts": ["edge1"]}}
    res = fsc.maybe_escalate_blocked(
        report,
        {
            "XIAOCAO_WECOM_RELAY_URL": "https://clawsg/send",
            "XIAOCAO_WECOM_RELAY_TOKEN": "tok",
            "XIAOCAO_WECOM_USER_ID": "Chen",
        },
        poster=poster,
    )
    assert res["wecom"] == "ok"
    text = calls[0]["text"]
    assert "edge1" in text and "不得自动改参" in text and "params.py" in text


def test_no_escalation_when_strategy_open_or_closed():
    for st in ("open", "closed"):
        report = {"strategy_flywheel": {"status": st, "pending_pass_verdicts": []}}
        assert fsc.maybe_escalate_blocked(report, {"XIAOCAO_WECOM_RELAY_URL": "https://clawsg/send"}) is None


def test_missing_optimize_step_is_not_spinning(tmp_path):
    root = _wire_repo(tmp_path, with_optimize=False)
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["spinning"] is False
    assert any("capability flywheel not wired" in w for w in r["warnings"])


def test_liveness_warns_on_stale_journal(tmp_path):
    # Wiring intact but the loop silently stopped: a stale journal must surface a
    # LIVENESS warning even though spinning stays true.
    root = _wire_repo(tmp_path)
    (root / "output" / "live" / "decision_journal.jsonl").write_text(
        json.dumps({"automation": "live_monitor", "market_date": "2020-01-01"}) + "\n", encoding="utf-8")
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["capital_flywheel"]["last_journal_date"] == "2020-01-01"
    assert any("LIVENESS" in w for w in r["warnings"])


def test_unblocked_real_capital_is_critical(tmp_path):
    # Simulate a (mis)configuration where the real-capital path would NOT be
    # blocked: a valid two-key setup. The self-check must flag it as critical.
    from xiaocao.live import safety
    root = _wire_repo(tmp_path)
    auth = root / "auth.json"
    key = "k"
    obj = safety.make_authorization(scope="t", max_notional=1e9, signing_key=key,
                                    expires_at="2099-01-01T00:00:00+00:00")
    auth.write_text(json.dumps(obj), encoding="utf-8")
    env = {safety.ENV_LIVE_ENABLED: "true", safety.ENV_SIGNING_KEY: key}
    r = flywheel.check_flywheel(root=root, env=env, auth_path=auth)
    assert r["capital_flywheel"]["safety_paper_only"] is False
    assert r["spinning"] is False
    assert any("CRITICAL" in w for w in r["warnings"])
