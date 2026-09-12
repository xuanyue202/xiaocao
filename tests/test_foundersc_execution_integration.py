"""Real Python execution/store/adapter chain with a controllable native service."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_foundersc_native_broker import FakeNative, _adapter, _plan
from xiaocao.live.safety import ENV_LIVE_ENABLED, ENV_SIGNING_KEY, make_authorization
from xiaocao.live.trading_execution import (
    BookBOwnershipEvidence, ExecutionState, ExecutionStore, TradingExecution,
)


@pytest.fixture
def chain(tmp_path):
    now = datetime.now(timezone.utc)
    plan = replace(_plan(), created_at=now, trade_date=now.astimezone(timezone(timedelta(hours=8))).date().isoformat(),
                   recovery_deadline=now + timedelta(minutes=5), price_rule="explicit-test-limit",
                   code="512010.XSHG")
    signing = "local-test-key"
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(make_authorization(
        scope="test", max_notional=2000, signing_key=signing,
        expires_at=(now + timedelta(hours=1)).isoformat(), issued_at=now.isoformat(),
    )))
    def engine(native):
        return TradingExecution(
            store=ExecutionStore(tmp_path / "events.jsonl"), broker=_adapter(native),
            ledger=BookBOwnershipEvidence(tmp_path / "ownership.jsonl"),
            safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing},
            auth_path=auth, audit_path=tmp_path / "audit.jsonl", now=lambda: now,
            notifier=lambda *_args: None,
        )
    return plan, engine


@pytest.mark.parametrize("lost", [None, "submit", "cancel"])
def test_restart_after_native_response_loss_never_repeats_effect(chain, lost):
    class Native(FakeNative):
        def submit_prepared_order(self, **kwargs):
            result = super().submit_prepared_order(**kwargs)
            if lost == "submit":
                raise TimeoutError("response lost after service accepted")
            return result

        def cancel_order(self, **kwargs):
            result = super().cancel_order(**kwargs)
            if lost == "cancel":
                self.lose_cancel_reads = True
                raise TimeoutError("response lost after service cancelled")
            return result

        def read_query(self, **kwargs):
            if getattr(self, "lose_cancel_reads", False):
                raise TimeoutError("queries also unavailable until reconnect")
            return super().read_query(**kwargs)

    plan, engine = chain
    native = Native()
    first = engine(native).execute(plan)
    assert first.state == (ExecutionState.UNKNOWN if lost == "submit" else ExecutionState.ACKNOWLEDGED), first.reason
    resumed = engine(native).execute(plan)
    assert resumed.state == ExecutionState.ACKNOWLEDGED
    assert native.submit_calls == 1 and native.prepare_calls == 1
    cancelled = engine(native).cancel(plan)
    if lost == "cancel":
        assert cancelled.state == ExecutionState.UNKNOWN
        native.lose_cancel_reads = False
        cancelled = engine(native).cancel(plan)
    assert cancelled.state == ExecutionState.CANCELLED
    before = (native.submit_calls, native.cancel_calls, len(native.query_calls))
    for _ in range(3):
        assert engine(native).execute(plan).state == ExecutionState.CANCELLED
        assert engine(native).cancel(plan).state == ExecutionState.CANCELLED
    assert before == (native.submit_calls, native.cancel_calls, len(native.query_calls))
    assert native.submit_calls == native.cancel_calls == 1


@pytest.mark.parametrize("field,value", [
    ("trade_account_fingerprint", "999******000"), ("screen_locked", True),
    ("accessibility_trusted", False), ("app_running", False),
])
def test_broken_native_readiness_never_reaches_order_fields(chain, field, value):
    plan, engine = chain
    native = FakeNative(**{field: value})
    receipt = engine(native).execute(plan)
    assert receipt.state in {ExecutionState.REJECTED, ExecutionState.VALIDATED}
    assert receipt.submit_claim_id is None and receipt.broker_order_id is None
    assert native.prepare_calls == native.submit_calls == native.cancel_calls == 0
