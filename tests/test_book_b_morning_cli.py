"""Morning/recovery entrypoints bind one account and one durable plan."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from xiaocao.live.book_b_live_morning import BookBLiveMorningReceipt


@pytest.mark.parametrize("action", [None, "resume", "reconcile", "close", "capital_unavailable"])
def test_morning_entry_dispatches_without_reproducing_recovery_candidates(tmp_path, monkeypatch, capsys, action):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    cli = importlib.import_module("scripts.book_b_live_morning")
    calls = []
    def account_call(name, **kwargs):
        calls.append(name)
        if "expected_fund_account_fingerprint" in kwargs:
            assert kwargs["expected_fund_account_fingerprint"] == "123******890"
        return {"status": "ready"}
    broker = SimpleNamespace(
        ensure_login=lambda: account_call("login"),
        ensure_native_ready=lambda **kw: account_call("ready", **kw),
        ensure_environment=lambda **kw: account_call("environment", **kw),
        read_live_allocation_facts=lambda **kw: account_call("allocation", **kw),
        read_live_account_snapshot=lambda **kw: account_call("snapshot", **kw),
        prepare_readonly=lambda plan, **kw: account_call("prepare", **kw),
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
    monkeypatch.setattr(cli, "load_book_b_live_capital_basis", lambda _: SimpleNamespace(
        settled_nav=30000, current_open_exposure=0, source="fixture", receipt_sha256="hash"))
    monkeypatch.setattr(cli, "_fresh_market_guard", lambda *a: {"status": "ok"})
    monkeypatch.setattr(cli, "_wait_for_submit_window", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_review_rendezvous", lambda *a, **k: {"status": "reviewed"})
    def freeze(**kwargs):
        assert kwargs["timeout_sec"] == (900 if action is None else 0)
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
    result = json.loads(capsys.readouterr().out)
    if action == "capital_unavailable":
        assert result["reason"] == "LIVE_CAPITAL_RUNTIME_NOT_READY" and not calls
    elif action != "close":
        assert calls.count("prepare") == (0 if action == "reconcile" else 1)
        assert calls.count("execute") == calls.count("receipt") == 1
