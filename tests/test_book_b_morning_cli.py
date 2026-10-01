"""Morning/recovery entrypoints bind one account and one durable plan."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from xiaocao.live.book_b_live_morning import BookBLiveMorningReceipt


@pytest.fixture(autouse=True)
def isolate_morning_notices(monkeypatch):
    """Mocked APP dispatch must never send real historical notifications."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    cli = importlib.import_module("scripts.book_b_live_morning")
    monkeypatch.setenv("CODEX_AUTOMATION_ID", cli.AUTOMATION_ID)
    monkeypatch.setenv("CODEX_THREAD_ID", "scheduled-owner")
    class Notices:
        def __init__(self, *args, **kwargs):
            pass
        def publish(self, *args, **kwargs):
            pass
        def arm_golden_window(self):
            pass
        def close(self):
            return []
    monkeypatch.setattr(cli, "MorningNotifications", Notices)
    monkeypatch.setattr(cli, "_morning_calendar_check", lambda day: {
        "status": "trading_day", "trade_date": day, "latest_trading_date": day})


@pytest.mark.app_simulation
@pytest.mark.parametrize("calendar_status,expected_code,reason", [
    ("non_trading_day", 0, "NON_TRADING_DAY"),
    ("unproven", 2, "MORNING_CALENDAR_UNPROVEN"),
])
def test_calendar_stops_before_app_notices_or_order_recovery(
    tmp_path, monkeypatch, capsys, calendar_status, expected_code, reason,
):
    cli = importlib.import_module("scripts.book_b_live_morning")
    monkeypatch.setattr(cli, "_morning_calendar_check", lambda day: {
        "status": calendar_status, "trade_date": day, "latest_trading_date": "2026-09-30"})
    monkeypatch.setattr(cli, "MorningNotifications", lambda *a, **k: pytest.fail("holiday notification"))
    monkeypatch.setattr(cli, "_run", lambda *a, **k: pytest.fail("holiday APP execution"))
    assert cli.main(["--date", "2026-10-01", "--state-dir", str(tmp_path)]) == expected_code
    result = json.loads(capsys.readouterr().out)
    assert result["reason"] == reason
    assert json.loads(Path(result["receipt_path"]).read_text())["calendar"]["status"] == calendar_status


def test_recovery_rejects_foreign_automation_before_lock_or_notices(monkeypatch, capsys):
    cli = importlib.import_module("scripts.book_b_live_morning")
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "remote-writer")
    monkeypatch.setattr(cli, "automation_run", lambda *a, **k: pytest.fail("foreign task took runner lock"))
    monkeypatch.setattr(cli, "MorningNotifications", lambda *a, **k: pytest.fail("foreign task queued a notice"))

    assert cli.main(["--date", "2026-09-30", "--resume-plan-id", "same-plan",
                     "--recovery-action", "reconcile"]) == 2
    result = json.loads(capsys.readouterr().out.strip())
    assert result["status"] == "blocked"
    assert result["reason"] == "AUTOMATION_ENTRYPOINT_ID_MISMATCH"


@pytest.mark.parametrize("missing", ["CODEX_AUTOMATION_ID", "CODEX_THREAD_ID"])
def test_morning_rejects_unbound_task_before_lock_or_notices(monkeypatch, capsys, missing):
    cli = importlib.import_module("scripts.book_b_live_morning")
    monkeypatch.delenv(missing)
    monkeypatch.setattr(cli, "automation_run", lambda *a, **k: pytest.fail("unbound task took runner lock"))
    monkeypatch.setattr(cli, "MorningNotifications", lambda *a, **k: pytest.fail("unbound task queued a notice"))

    assert cli.main(["--date", "2026-09-30"]) == 2
    result = json.loads(capsys.readouterr().out.strip())
    assert result["reason"] == "AUTOMATION_RUNTIME_IDENTITY_UNPROVEN"


@pytest.mark.parametrize("action", [None, "preflight_repair", "resume", "reconcile", "close", "capital_unavailable"])
def test_morning_entry_dispatches_without_reproducing_recovery_candidates(tmp_path, monkeypatch, capsys, action):
    repair = action == "preflight_repair"
    action = None if repair else action
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    cli = importlib.import_module("scripts.book_b_live_morning")
    calls = []
    if repair:
        from xiaocao.runner_recovery import DependencyRecovery, signal_recheck
        def create_recovery(**kwargs):
            kwargs["sleep"] = lambda _: signal_recheck(Path(wait.requests[-1]["request_path"]))
            wait = DependencyRecovery(**kwargs)
            return wait
        monkeypatch.setattr(cli, "DependencyRecovery", create_recovery)
    def account_call(name, **kwargs):
        calls.append(name)
        if repair and name == "login" and calls.count("login") == 1:
            raise RuntimeError("NATIVE_AX_ACCOUNT_SURFACE_NOT_READY")
        if "expected_fund_account_fingerprint" in kwargs:
            assert kwargs["expected_fund_account_fingerprint"] == "123******890"
        return {"status": "ready"}
    broker = SimpleNamespace(
        ensure_login=lambda: account_call("login"),
        ensure_native_ready=lambda **kw: account_call("ready", **kw),
        ensure_environment=lambda **kw: account_call("environment", **kw),
        read_live_allocation_facts=lambda **kw: account_call("allocation", **kw),
        read_live_account_snapshot=lambda **kw: account_call("snapshot", **kw),
        read_buy_preflight_snapshot=lambda **kw: {"trade_date": "2026-09-11"},
        prepare_readonly=lambda plan, **kw: account_call("prepare", **kw),
        submission_batch=lambda: None,
    )
    execution = SimpleNamespace(execute=lambda plan, bound: account_call("execute"))
    monkeypatch.setattr(cli, "KeychainCapitalRuntime", lambda: SimpleNamespace(
        preflight=lambda: {"status": "blocked" if action == "capital_unavailable" else "ready"},
        safety_env=lambda: {}))
    monkeypatch.setattr(cli, "FounderscKeychainPreflight", lambda: SimpleNamespace(
        run=lambda **_: dict.fromkeys(("trade_item_present", "trade_account_present",
                                      "trade_secret_readable", "trade_secret_nonempty"), True),
        trade_account_fingerprint=lambda: "123******890"))
    monkeypatch.setattr(cli, "build_foundersc_native_execution", lambda *a, **k: (execution, broker))
    monkeypatch.setattr(cli, "load_settings", lambda _: SimpleNamespace(base_url="unused", timeout=1, retries=0))
    monkeypatch.setattr(cli, "XiaocaoClient", lambda **_: object())
    monkeypatch.setattr(cli, "calendar_provider", lambda _: object())
    monkeypatch.setattr(cli, "reconcile_prior_day_canary_unknowns", lambda *a, **k: ())
    from xiaocao.live import buy_preflight
    monkeypatch.setattr(buy_preflight, "pretrade_account", lambda *a, **k: object())
    monkeypatch.setattr(buy_preflight, "allocation_from_buy_preflight", lambda *a, **k: account_call("allocation"))
    monkeypatch.setattr(cli, "load_book_b_live_capital_basis", lambda *a, **k: SimpleNamespace(
        settled_nav=30000, current_open_exposure=0, source="fixture", receipt_sha256="hash"))
    monkeypatch.setattr(cli, "_fresh_market_guard", lambda *a: {"status": "ok"})
    monkeypatch.setattr(cli, "_wait_for_submit_window", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_review_rendezvous", lambda *a, **k: {"status": "reviewed"})
    def freeze(**kwargs):
        assert (0 < kwargs["timeout_sec"] <= 2100) if action is None else kwargs["timeout_sec"] == 0
        kwargs["heartbeat"]()
        return {}
    monkeypatch.setattr(cli, "wait_for_morning_freeze", freeze)
    monkeypatch.setattr(cli, "write_book_b_live_morning_receipt", lambda *a: calls.append("receipt"))
    def core(config, **kwargs):
        if action is not None:
            assert kwargs["plan_id"] == "same-plan" and kwargs["action"] == action
        if action == "close":
            assert not calls and "preflight" not in kwargs
        elif action == "reconcile":
            kwargs["account_snapshot_provider"]()
            kwargs["execute"]("same-plan")
        else:
            kwargs["preflight"]()
            kwargs["read_allocation_facts"]()
            kwargs["account_snapshot_provider"]()
            kwargs["wait_for_dated_freeze"]()
            kwargs["refresh_market_guard"]({})
            if kwargs["prepare_only"] is not None:
                kwargs["prepare_only"]("same-plan")
            kwargs["execute"]("same-plan")
            assert kwargs["restore_environment"]()["status"] == "native_environment_restore_not_applicable"
        return BookBLiveMorningReceipt(config.trade_date, "no_action", "fixture", 0, (), (),
            str(config.freeze_path), str(config.allocation_facts_path), str(config.state_dir))
    monkeypatch.setattr(cli, "run_book_b_live_morning", core if action is None else lambda *a, **k: pytest.fail("new producer during recovery"))
    monkeypatch.setattr(cli, "run_book_b_live_recovery", core)
    args = ["--date", "2026-09-11", "--state-dir", str(tmp_path)]
    if action in {"resume", "reconcile", "close"}:
        args += ["--resume-plan-id", "same-plan", "--recovery-action", action]
    assert cli.main(args) == (2 if action == "capital_unavailable" else 0)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    result = lines[-1]
    if repair:
        assert calls.count("login") == 2 and calls.count("execute") == 1
        assert [line.get("event") for line in lines[:-1]] == ["dependency_recovery_wait", "dependency_recovered"]
        assert result["runner_identity"]["automation_id"] == "xiaocao-book-b-live-morning"
    if action == "capital_unavailable":
        assert result["reason"] == "LIVE_CAPITAL_RUNTIME_NOT_READY" and not calls
    elif action != "close":
        assert calls.count("prepare") == (1 if action == "resume" else 0)
        assert calls.count("execute") == calls.count("receipt") == 1
