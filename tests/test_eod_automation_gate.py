"""EOD task slots prevent duplicate business work across completed processes."""
import importlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def identity(monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-eod")
    monkeypatch.setenv("CODEX_THREAD_ID", "first-owner")


def test_slot_survives_owner_exit_and_branches_are_independent(tmp_path, monkeypatch, identity):
    from xiaocao.live.eod_automation_gate import claim_eod_slot, EodGateRejected
    first = claim_eod_slot(tmp_path, "paper", "2026-10-06")
    monkeypatch.setenv("CODEX_THREAD_ID", "later-owner")
    with pytest.raises(EodGateRejected) as rejected:
        claim_eod_slot(tmp_path, "paper", "2026-10-06")
    assert rejected.value.payload["owner"] == first
    assert json.loads(Path(first["claim_path"]).read_text()) == first
    assert claim_eod_slot(tmp_path, "app", "2026-10-06")["thread_id"] == "later-owner"
    assert claim_eod_slot(tmp_path, "paper", "2026-10-07")["trade_date"] == "2026-10-07"


@pytest.mark.parametrize("automation_id,thread", [("wrong", "owner"), ("", "owner"), ("xiaocao-daily-eod", "")])
def test_identity_rejects_before_any_claim(tmp_path, monkeypatch, automation_id, thread):
    from xiaocao.live.eod_automation_gate import claim_eod_slot, EodGateRejected
    monkeypatch.setenv("CODEX_AUTOMATION_ID", automation_id)
    monkeypatch.setenv("CODEX_THREAD_ID", thread)
    with pytest.raises(EodGateRejected):
        claim_eod_slot(tmp_path, "paper", "2026-10-06")
    assert list(tmp_path.iterdir()) == []


def test_paper_duplicate_cannot_spawn_or_overwrite_latest(tmp_path, monkeypatch, identity):
    from xiaocao.live import runtime_evidence
    script = tmp_path / "daily.sh"
    script.write_text("echo noop\n")
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return 0
    monkeypatch.setattr(runtime_evidence, "stream_process", run)
    assert runtime_evidence.launch(script, tmp_path, ["eod"]) == 0
    latest = next((tmp_path / "output/live").glob("run_flow_*_eod.json"))
    original = latest.read_bytes()
    monkeypatch.setenv("CODEX_THREAD_ID", "second-owner")
    assert runtime_evidence.launch(script, tmp_path, ["eod"]) == 2
    assert len(calls) == 1
    assert latest.read_bytes() == original
    assert len(list((tmp_path / "output/live/auto/runs").iterdir())) == 1


@pytest.mark.app_simulation
def test_app_holiday_owner_and_duplicate_before_client(tmp_path, monkeypatch, capsys, identity):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    cli = importlib.import_module("scripts.book_b_live_intraday")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "_china_now", lambda: datetime(2026, 10, 6, 18, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    calls = []
    monkeypatch.setattr(cli.monitor, "_client", lambda: calls.append("client"))
    monkeypatch.setattr(cli, "calendar_provider", lambda _: lambda clock: ["2026-09-30"])
    args = ["--date", "today", "--phase", "eod", "--state-dir", str(tmp_path / "state")]
    assert cli.main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["automation_identity"]["automation_id"] == "xiaocao-daily-eod"
    latest = tmp_path / "state/runs/intraday/2026-10-06-eod.json"
    original = latest.read_bytes()
    monkeypatch.setenv("CODEX_THREAD_ID", "second-owner")
    assert cli.main(args) == 2
    second = json.loads(capsys.readouterr().err)
    assert second["owner"]["thread_id"] == "first-owner"
    assert calls == ["client"]
    assert latest.read_bytes() == original


@pytest.mark.app_simulation
def test_app_wrong_identity_never_reaches_client(tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    cli = importlib.import_module("scripts.book_b_live_intraday")
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "another-task")
    monkeypatch.setenv("CODEX_THREAD_ID", "owner")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.monitor, "_client", lambda: pytest.fail("wrong owner reached market/native dependencies"))
    assert cli.main(["--phase", "eod", "--state-dir", str(tmp_path / "state")]) == 2
    assert json.loads(capsys.readouterr().err)["reason"] == "EOD_TASK_IDENTITY_MISMATCH"
    assert list(tmp_path.iterdir()) == []


def test_concurrent_claims_publish_exactly_one_complete_owner(tmp_path, identity):
    from concurrent.futures import ThreadPoolExecutor
    from xiaocao.live.eod_automation_gate import claim_eod_slot, EodGateRejected
    def claim(_):
        try:
            return {"owner": claim_eod_slot(tmp_path, "paper", "2026-10-06")}
        except EodGateRejected as exc:
            return exc.payload
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, range(2)))
    assert sum("reason" not in r for r in results) == 1
    blocked = next(r for r in results if "reason" in r)
    assert blocked["reason"] == "EOD_SLOT_ALREADY_CLAIMED"
    assert blocked["owner"] == next(r["owner"] for r in results if "reason" not in r)


def test_damaged_claim_is_not_reclaimed(tmp_path, identity):
    from xiaocao.live.eod_automation_gate import claim_eod_slot, EodGateRejected
    owner = claim_eod_slot(tmp_path, "app", "2026-10-06")
    claim = Path(owner["claim_path"])
    claim.write_text("broken")
    with pytest.raises(EodGateRejected) as rejected:
        claim_eod_slot(tmp_path, "app", "2026-10-06")
    assert rejected.value.payload["reason"] == "EOD_SLOT_OWNER_UNPROVEN"
    assert claim.read_text() == "broken"


def test_failed_paper_shell_keeps_claim_and_cannot_be_restarted(tmp_path, monkeypatch, identity):
    from xiaocao.live import runtime_evidence
    script = tmp_path / "daily.sh"
    script.write_text("exit 7\n")
    calls = []
    monkeypatch.setattr(runtime_evidence, "stream_process", lambda *a, **k: calls.append(a) or 7)
    assert runtime_evidence.launch(script, tmp_path, ["eod"]) == 7
    assert runtime_evidence.launch(script, tmp_path, ["eod"]) == 2
    assert len(calls) == 1
