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
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-eod")
    monkeypatch.setenv("CODEX_THREAD_ID", "intraday-fixture")
    # These callback tests isolate identity; separate cases exercise the real pre-effect gate.
    import xiaocao.automation_run as automation_identity
    monkeypatch.setattr(automation_identity, "validate_monitor_scheduler", lambda **kwargs: None)
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
    monkeypatch.setattr(cli, "calendar_provider", lambda _: lambda clock: ["2026-09-11"])
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


@pytest.mark.app_simulation
@pytest.mark.parametrize("write_failure", [False, True])
def test_failed_checkpoint_retains_native_cells_without_snapshot_authority(entry, monkeypatch, capsys, write_failure):
    import hashlib
    from xiaocao.live.foundersc_native_ax import FounderscNativeAXError

    cli, calls, root = entry
    failed = {"native_read_error": "NATIVE_QUERY_ORDER_FILLED_QUANTITY_MALFORMED",
              "failed_native_readbacks": {"today-orders": {"observed_at": "2026-09-11T07:10:00Z"}},
              "failed_native_rows": [{"query_kind": "today-orders", "成交数量": "bad-cell"}]}
    broker = SimpleNamespace(last_query_readbacks={"today-orders": {}},
                             _failed_read_evidence=lambda exc: failed)
    monkeypatch.setattr(cli, "build_foundersc_native_execution", lambda *a, **k: (object(), broker))
    def fail(**kwargs):
        raise FounderscNativeAXError(failed["native_read_error"])
    monkeypatch.setattr(cli, "run_book_b_live_intraday", fail)
    original_write = cli._write_json_atomic
    def write(path, payload):
        if write_failure and path.parent.name == "read_failures":
            raise OSError("fixture disk failure")
        original_write(path, payload)
    monkeypatch.setattr(cli, "_write_json_atomic", write)
    assert cli.main(["--phase", "opening", "--state-dir", str(root)]) == 2
    output = capsys.readouterr().err
    payload = json.loads(output)
    assert payload["reason"] == failed["native_read_error"]
    assert "bad-cell" not in output and "broker_snapshot" not in payload
    assert calls == []
    if write_failure:
        assert payload["native_readback_evidence_error"] == "OSError"
    else:
        ref = payload["native_readback_evidence"]
        raw = Path(ref["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == ref["sha256"]
        assert json.loads(raw)["evidence"] == failed
        assert Path(ref["path"]).parent.name == "read_failures"


@pytest.mark.app_simulation
@pytest.mark.parametrize("phase", ["opening", "sparse", "precheck", "closing", "eod"])
@pytest.mark.parametrize("requested_date", ["today", "2026-09-30"])
def test_holiday_stops_before_secrets_app_and_pending_order_recovery(entry, monkeypatch, capsys, phase, requested_date):
    cli, calls, root = entry
    monkeypatch.setattr(cli, "_china_now", lambda: datetime(2026, 10, 1, 14, 45, tzinfo=ZoneInfo("Asia/Shanghai")))
    monkeypatch.setattr(cli, "calendar_provider", lambda _: lambda clock: ["2026-09-30"])
    def forbidden(*args, **kwargs):
        pytest.fail("holiday reached a native/credential/order dependency")
    monkeypatch.setattr(cli, "FounderscKeychainPreflight", forbidden)
    monkeypatch.setattr(cli, "build_foundersc_native_execution", forbidden)
    monkeypatch.setattr(cli, "run_book_b_live_intraday", forbidden)
    assert cli.main(["--date", requested_date, "--phase", phase, "--state-dir", str(root), "--execute-sells"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "no_action" and payload["reason"] == "NON_TRADING_DAY"
    assert payload["calendar"]["latest_trading_date"] == "2026-09-30"
    assert payload["calendar"]["query_date"] == "2026-10-01"
    assert json.loads(Path(payload["run_receipt_path"]).read_text()) == payload
    assert calls == []


@pytest.mark.app_simulation
@pytest.mark.parametrize("calendar_result", [[], ["2026-09-12"], None])
def test_unproved_calendar_blocks_before_secrets_or_app(entry, monkeypatch, capsys, calendar_result):
    cli, calls, root = entry
    def calendar(clock):
        if calendar_result is None:
            raise RuntimeError("provider unavailable")
        return calendar_result
    monkeypatch.setattr(cli, "calendar_provider", lambda _: calendar)
    def forbidden(*args, **kwargs):
        pytest.fail("unproved calendar reached a native/credential/order dependency")
    monkeypatch.setattr(cli, "FounderscKeychainPreflight", forbidden)
    monkeypatch.setattr(cli, "run_book_b_live_intraday", forbidden)
    assert cli.main(["--phase", "closing", "--state-dir", str(root), "--execute-sells"]) == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["reason"] == "LIVE_BOOK_B_CALENDAR_UNPROVEN"
    assert json.loads(Path(payload["run_receipt_path"]).read_text()) == payload
    assert calls == []


@pytest.mark.app_simulation
def test_eod_login_failure_notifies_from_the_durable_original_receipt(entry, monkeypatch, capsys):
    cli, calls, root = entry
    notices = []

    def failed_snapshot(**kwargs):
        raise RuntimeError("NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:client_login_required")

    def notify(path, **kwargs):
        payload = json.loads(path.read_text())
        assert payload["status"] == "blocked"
        assert payload["automation_identity"]["thread_id"] == "intraday-fixture"
        notices.append(path)

    monkeypatch.setattr(cli, "run_book_b_live_intraday", failed_snapshot)
    monkeypatch.setattr(cli, "notify_eod_blocker", notify, raising=False)
    assert cli.main(["--phase", "eod", "--state-dir", str(root)]) == 2
    payload = json.loads(capsys.readouterr().err)
    assert notices == [Path(payload["run_receipt_path"])]
    assert calls == []


@pytest.mark.app_simulation
def test_eod_archive_keeps_exact_snapshot_without_printing_broker_tables(entry, monkeypatch, capsys):
    cli, calls, root = entry
    snapshot = {"snapshot_sha256": "a" * 64,
        "tables": {kind: {"rows": [{"evidence": kind}]}
                   for kind in ("positions", "today-orders", "today-trades")},
        "funds_summary": {"available_cash": 12345.67}}
    monkeypatch.setattr(cli, "run_book_b_live_intraday", lambda **kwargs:
        SimpleNamespace(as_dict=lambda: {"status": "settled", "broker_snapshot": snapshot}))
    assert cli.main(["--phase", "eod", "--state-dir", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    archived = json.loads(Path(payload["run_receipt_path"]).read_text())
    assert archived["broker_snapshot"] == snapshot
    assert "broker_snapshot" not in payload
    assert payload["broker_snapshot_evidence"] == {
        "receipt_path": payload["run_receipt_path"], "snapshot_sha256": "a" * 64}


@pytest.mark.app_simulation
def test_sell_result_notification_follows_original_archive_and_cannot_change_result(entry, monkeypatch, capsys):
    cli, calls, root = entry
    monkeypatch.setattr(cli, "run_book_b_live_intraday", lambda **kwargs:
        SimpleNamespace(as_dict=lambda: {"status": "executed"}))
    def failed_notice(payload, **kwargs):
        archived = json.loads(Path(payload["run_receipt_path"]).read_text())
        assert archived == payload and archived["status"] == "executed"
        raise OSError("notice claim unavailable")
    monkeypatch.setattr(cli, "notify_app_sells", failed_notice)
    assert cli.main(["--phase", "closing", "--state-dir", str(root)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "executed"
    assert "notice unavailable" in output.err and calls == []


@pytest.mark.app_simulation
def test_wrong_opening_owner_is_rejected_before_calendar_or_app(tmp_path, monkeypatch, capsys):
    cli=importlib.import_module("scripts.book_b_live_intraday")
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-eod")
    monkeypatch.setattr(cli.monitor,"_client",lambda:pytest.fail("identity must precede calendar"))
    assert cli.main(["--phase","opening"])==2
    assert "AUTOMATION_ENTRYPOINT_ID_MISMATCH" in capsys.readouterr().err
