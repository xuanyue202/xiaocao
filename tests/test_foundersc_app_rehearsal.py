"""The manual simulation runner uses the same durable execution chain."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts import foundersc_app_rehearsal as rehearsal
from tests.test_foundersc_native_broker import FakeNative
from xiaocao.live.safety import make_authorization, ENV_LIVE_ENABLED, ENV_SIGNING_KEY


@pytest.fixture
def app(tmp_path, monkeypatch):
    class Native(FakeNative):
        def read_query(self, **kwargs):
            receipt = super().read_query(**kwargs)
            receipt.payload["query_readback"]["observed_at"] = datetime.now(timezone.utc).isoformat()
            return receipt
    native = Native()
    native.position_summary.update({"资产": "44054.60", "可用": "1000.00",
                                    "余额": "1000.00", "可取": "1000.00"})
    monkeypatch.setattr(rehearsal, "ROOT", tmp_path)
    monkeypatch.setattr(rehearsal, "FounderscNativeAXClient", lambda: native)
    monkeypatch.setattr(rehearsal, "source_digest", lambda: "source-test")
    monkeypatch.setattr(rehearsal.subprocess, "check_output", lambda *a, **k: "test-sha")
    env = {ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: "test-only-signing"}
    monkeypatch.setattr(rehearsal.KeychainCapitalRuntime, "safety_env", lambda _: env)
    auth = tmp_path / "output/live/live_authorization.json"
    auth.parent.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    auth.write_text(json.dumps(make_authorization(
        scope="test", max_notional=1000, signing_key=env[ENV_SIGNING_KEY],
        expires_at=(now + timedelta(hours=1)).isoformat(), issued_at=now.isoformat(),
    )))
    def run(action, *extra):
        monkeypatch.setattr(rehearsal.sys, "argv", ["rehearsal", action, "--run-id", "test",
            "--fingerprint", "123******890", "--acknowledge-app-server-simulation", *extra])
        return rehearsal.main()
    directory = tmp_path / "output/research/foundersc_app_rehearsal/test"
    return run, native, directory


def test_cli_prepare_submit_cancel_and_repeat_reconcile(app):
    run, native, directory = app
    assert run("snapshot") == 0
    assert run("prepare") == 0
    assert native.submit_calls == native.cancel_calls == 0
    assert run("advance") == 0
    assert native.submit_calls == native.cancel_calls == 1
    for _ in range(2):
        assert run("reconcile") == 0
        assert run("advance") == 0
    assert native.submit_calls == native.cancel_calls == 1
    assert not (directory / "ownership.jsonl").exists()
    with pytest.raises(ValueError, match="PREPARE_FORBIDDEN"):
        run("prepare")


def test_reconcile_cannot_create_an_order_and_plan_cannot_change(app):
    run, native, directory = app
    with pytest.raises(ValueError, match="INTENT_MISSING"):
        run("reconcile")
    assert run("prepare") == 0
    before = native.prepare_calls
    with pytest.raises(ValueError, match="NO_SUBMIT"):
        run("reconcile")
    with pytest.raises(ValueError, match="IMMUTABLE"):
        run("advance", "--price", "0.36")
    assert native.prepare_calls == before and native.submit_calls == 0
    payload = json.loads((directory / "intent.json").read_text())
    payload["rehearsal_budget"]["limit_price"] = 0.36
    with pytest.raises(ValueError, match="INTENT_INVALID"):
        rehearsal.read_rehearsal_plan(payload)


def test_crash_after_baseline_publication_can_resume_without_overwrite(app):
    run, native, directory = app
    assert run("prepare") == 0
    original = (directory / "baseline.json").read_bytes()
    (directory / "intent.json").unlink()  # crash fixture, never an operational repair
    assert run("advance") == 0
    assert (directory / "baseline.json").read_bytes() == original
    assert native.submit_calls == native.cancel_calls == 1


def test_atomic_evidence_never_overwrites_or_publishes_partial_json(tmp_path):
    target = tmp_path / "receipt.json"
    rehearsal.write_once(target, {"receipt": "first"})
    with pytest.raises(FileExistsError):
        rehearsal.write_once(target, {"receipt": "second"})
    assert json.loads(target.read_text()) == {"receipt": "first"}
    other = tmp_path / "invalid.json"
    with pytest.raises(ValueError):
        rehearsal.write_once(other, {"bad": float("nan")})
    assert list(tmp_path.iterdir()) == [target]
