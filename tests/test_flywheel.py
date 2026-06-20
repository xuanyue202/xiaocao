"""Tests for the flywheel self-check (src/xiaocao/live/flywheel.py)."""
from __future__ import annotations

import json

from xiaocao.live import flywheel


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
        import pandas as pd
        pd.DataFrame([{"date": "2026-06-01", "net_realized_ret": 1.0}]).to_parquet(live / "training_rows.parquet")
    return tmp_path


def test_fully_wired_repo_is_spinning(tmp_path):
    root = _wire_repo(tmp_path)
    # no live authorization + env without the live flag -> paper-only holds.
    r = flywheel.check_flywheel(root=root, env={}, auth_path=root / "none.json")
    assert r["spinning"] is True
    assert r["capital_flywheel"]["safety_paper_only"] is True
    assert r["capital_flywheel"]["automation_complete"] is True
    assert r["capability_flywheel"]["optimize_step_wired"] is True
    assert r["capability_flywheel"]["training_rows"] == 1


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
