"""Exercise the scheduled Python entrypoint and its native callback wiring."""
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def entry(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    cli = importlib.import_module("scripts.book_b_live_intraday")
    calls = []
    class Keychain:
        def run(self, **kwargs):
            return dict.fromkeys(("trade_item_present", "trade_account_present",
                                  "trade_secret_readable", "trade_secret_nonempty"), True)
        def trade_account_fingerprint(self):
            return "123******890"
    class Broker:
        def ensure_login(self):
            calls.append("login")
        def read_live_account_snapshot(self, **kwargs):
            assert kwargs["expected_fund_account_fingerprint"] == "123******890"
            calls.append("snapshot")
            return {"source": "native-test"}
    def execute(plan, broker):
        calls.append("execute")
        return {"plan": plan}
    monkeypatch.setattr(cli, "FounderscKeychainPreflight", Keychain)
    monkeypatch.setattr(cli, "build_foundersc_native_execution",
                        lambda *a, **k: (SimpleNamespace(execute=execute), Broker()))
    monkeypatch.setattr(cli, "_china_now", lambda: datetime(2026, 9, 11, 15, 10, tzinfo=ZoneInfo("Asia/Shanghai")))
    monkeypatch.setattr(cli, "_git_sha", lambda: "test-sha")
    monkeypatch.setattr(cli.monitor, "_client", lambda: object())
    monkeypatch.setattr(cli.monitor, "_market_sentiment_context", lambda _: {})
    monkeypatch.setattr(cli.monitor, "_load_stock_sentiment_map", lambda _: {})
    monkeypatch.setattr(cli.monitor, "_load_signal_snapshot_map", lambda: {})
    monkeypatch.setattr(cli.monitor, "_compute_status", lambda *a, **k: {"code": "000001.XSHE"})
    monkeypatch.setattr(cli, "read_policy", lambda *a: {})
    monkeypatch.setattr(cli, "calendar_provider", lambda _: object())
    return cli, calls, tmp_path


@pytest.mark.parametrize("phase", ["opening", "sparse", "precheck", "closing", "eod"])
@pytest.mark.parametrize("execute_sells", [False, True])
def test_all_checkpoint_entrypoints_bind_the_same_native_account(entry, monkeypatch, capsys, phase, execute_sells):
    cli, calls, root = entry
    def checkpoint(**kwargs):
        assert kwargs["phase"] == phase and kwargs["execute_sells"] is execute_sells
        assert kwargs["account_snapshot_provider"]() == {"source": "native-test"}
        kwargs["account_snapshot_provider"]()
        lot = SimpleNamespace(code="000001.XSHE", name="fixture", entry_date="2026-09-10",
            entry_price=10, shares=100, buy_fee_rate=0.0001, monitor_context={}, owned_lot_id="owned")
        assert kwargs["status_provider"]([lot])[0]["owned_lot_id"] == "owned"
        if execute_sells:
            kwargs["execute"]("same-plan")
        return SimpleNamespace(as_dict=lambda: {"status": "settled" if phase == "eod" else "observed"})
    monkeypatch.setattr(cli, "run_book_b_live_intraday", checkpoint)
    args = ["--phase", phase, "--state-dir", str(root)]
    if execute_sells:
        args.append("--execute-sells")
    assert cli.main(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["route"] == "native-app" and payload["paper_ledger_used"] is False
    assert calls.count("login") == 1
    assert calls.count("execute") == int(execute_sells)
    assert json.loads(Path(payload["run_receipt_path"]).read_text()) == payload


@pytest.mark.parametrize("reason", ["BROKER_READ_FAILED", "LIVE_BOOK_B_CHECKPOINT_ALREADY_RUNNING"])
def test_failed_checkpoint_archives_error_and_preserves_running_owner(entry, monkeypatch, capsys, reason):
    cli, calls, root = entry
    latest = root / "runs/intraday/2026-09-11-opening.json"
    latest.parent.mkdir(parents=True)
    latest.write_text('{"owner":"running"}')
    def fail(**kwargs):
        raise ValueError(reason)
    monkeypatch.setattr(cli, "run_book_b_live_intraday", fail)
    assert cli.main(["--phase", "opening", "--state-dir", str(root)]) == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["reason"] == reason
    assert json.loads(Path(payload["run_receipt_path"]).read_text()) == payload
    assert json.loads(latest.read_text()) == ({"owner": "running"} if reason.endswith("ALREADY_RUNNING") else payload)
    assert calls == []
