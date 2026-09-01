from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.live.trading_execution import (
    BrokerCapability,
    BrokerReceipt,
    BrokerStatus,
    ExecutionReceipt,
    ExecutionState,
    InMemoryExecutionStore,
    TradePlan,
    TradingAccountLedger,
    TradingExecution,
    TradingTakeoverStore,
    trade_plan_from_frozen_row,
)
from xiaocao.live.safety import ENV_LIVE_ENABLED, ENV_SIGNING_KEY, make_authorization


def _plan(
    *,
    environment: str = "mock",
    guard: str = "ok",
    shares: int = 200,
    basket: float = 10.10,
    deadline: datetime | None = None,
) -> TradePlan:
    return TradePlan(
        plan_id="plan-001",
        strategy_run_id="run-2026-08-15",
        snapshot_ref="signal_snapshots.jsonl#row-1",
        strategy_sha="abc123",
        trade_date="2026-08-15",
        book="B",
        logical_account_id="primary",
        environment=environment,
        code="000001.XSHE",
        name="测试标的",
        side="BUY",
        shares=shares,
        limit_price=10.05,
        basket_price=basket,
        market_guard_status=guard,
        created_at=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        recovery_deadline=deadline or datetime.now(timezone.utc) + timedelta(minutes=15),
        allocation_proof_hash="test-allocation-proof",
    )


class FakeBroker:
    def __init__(self, *, submit: list[BrokerReceipt] | None = None, reconcile: list[BrokerReceipt] | None = None):
        self.capability = BrokerCapability(
            ready=True,
            environment="mock",
            logical_account_id="primary",
            supports_submit=True,
            supports_reconcile=True,
            supports_cancel=True,
            account_binding="proven",
        )
        self.submit_results = list(
            submit
            or [
                BrokerReceipt(
                    status=BrokerStatus.ACCEPTED,
                    order_id="o-1",
                    strategy_id="s-1",
                    receipt_mapping=True,
                    account_binding="proven",
                )
            ]
        )
        self.reconcile_results = list(reconcile or [BrokerReceipt(status=BrokerStatus.FILLED, order_id="o-1", filled_shares=200)])
        self.probe_calls = 0
        self.prepare_calls = 0
        self.submit_calls = 0
        self.reconcile_calls = 0
        self.cancel_calls = 0
        self.claim_ids: list[str] = []

    def probe(self, plan: TradePlan) -> BrokerCapability:
        self.probe_calls += 1
        return replace(self.capability, environment=plan.environment)

    def prepare(self, plan: TradePlan, *, requested_shares: int | None = None) -> BrokerReceipt:
        self.prepare_calls += 1
        shares = int(requested_shares or plan.shares)
        return BrokerReceipt(
            status=BrokerStatus.PREPARED,
            order_id="o-1",
            echoed={"code": plan.code, "side": plan.side, "shares": shares, "limit_price": plan.limit_price},
        )

    def submit(self, plan: TradePlan, claim_id: str, *, requested_shares: int | None = None) -> BrokerReceipt:
        self.submit_calls += 1
        self.claim_ids.append(claim_id)
        if not self.submit_results:
            return BrokerReceipt(
                status=BrokerStatus.ACCEPTED,
                order_id="o-1",
                strategy_id="s-1",
                receipt_mapping=True,
                account_binding="proven",
            )
        return self.submit_results.pop(0)

    def reconcile(self, plan: TradePlan, previous: dict) -> BrokerReceipt:
        self.reconcile_calls += 1
        if not self.reconcile_results:
            return BrokerReceipt(status=BrokerStatus.UNKNOWN, reason="no test receipt", conclusive=False)
        return self.reconcile_results.pop(0)

    def cancel(self, plan: TradePlan, previous: dict) -> BrokerReceipt:
        self.cancel_calls += 1
        return BrokerReceipt(
            status=BrokerStatus.CANCELLED,
            order_id=str(previous.get("broker_order_id") or "o-1"),
            strategy_id=str(previous.get("broker_strategy_id") or "s-1"),
            receipt_mapping=True,
            requested_shares=plan.shares,
            remaining_shares=plan.shares,
            account_binding="proven",
            conclusive=True,
            retry_allowed=False,
            reason="cancelled_for_test",
        )

    def recover(self, plan: TradePlan, previous: dict) -> BrokerReceipt:
        return BrokerReceipt(
            status=BrokerStatus.UNKNOWN,
            reason=str(previous.get("reason") or "recover unknown"),
            conclusive=False,
        )


def test_mock_order_claims_and_reconciles_to_filled(tmp_path: Path) -> None:
    broker = FakeBroker()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(store=store, now=lambda: datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc))

    first = engine.execute(_plan(), broker)
    assert first.state == ExecutionState.ACKNOWLEDGED
    assert first.next_action == "reconcile"
    assert broker.submit_calls == 1

    final = engine.execute(_plan(), broker)
    assert final.state == ExecutionState.FILLED
    assert final.filled_shares == 200
    assert broker.submit_calls == 1
    assert broker.reconcile_calls == 1


def test_cancel_is_one_shot_and_persists_terminal_receipt(tmp_path: Path) -> None:
    broker = FakeBroker()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(
        store=store,
        now=lambda: datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
    )
    plan = _plan()

    submitted = engine.execute(plan, broker)
    assert submitted.state == ExecutionState.ACKNOWLEDGED

    cancelled = engine.cancel(plan, broker)
    assert cancelled.state == ExecutionState.CANCELLED
    assert cancelled.broker_order_id == "o-1"
    assert cancelled.cancel_claim_id
    assert cancelled.cancel_chain_uncertain is False
    assert broker.cancel_calls == 1
    assert [row["kind"] for row in store.events(plan.plan_id)][-2:] == [
        "cancel_claimed",
        "cancel_receipt",
    ]

    same = engine.cancel(plan, broker)
    assert same.state == ExecutionState.CANCELLED
    assert broker.cancel_calls == 1


def test_cancel_prefers_dedicated_cancel_probe_over_submit_probe(
    tmp_path: Path,
) -> None:
    class CancelAwareBroker(FakeBroker):
        def __init__(self):
            super().__init__()
            self.cancel_probe_calls = 0

        def probe_cancel(
            self,
            plan: TradePlan,
            previous: dict,
        ) -> BrokerCapability:
            self.cancel_probe_calls += 1
            assert previous["broker_order_id"] == "o-1"
            return replace(
                self.capability,
                environment=plan.environment,
                supports_submit=False,
                supports_reconcile=True,
                supports_cancel=True,
            )

    broker = CancelAwareBroker()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(
        store=store,
        now=lambda: datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
    )
    plan = _plan()
    assert engine.execute(plan, broker).state == ExecutionState.ACKNOWLEDGED
    submit_probe_calls = broker.probe_calls

    cancelled = engine.cancel(plan, broker)

    assert cancelled.state == ExecutionState.CANCELLED
    assert broker.cancel_probe_calls == 1
    assert broker.probe_calls == submit_probe_calls


def test_unknown_cancel_claim_reconciles_without_replaying_cancel(
    tmp_path: Path,
) -> None:
    class LostCancelResponseBroker(FakeBroker):
        def cancel(self, plan: TradePlan, previous: dict) -> BrokerReceipt:
            self.cancel_calls += 1
            assert previous["cancel_claim_id"]
            raise TimeoutError("response lost after cancel click")

    broker = LostCancelResponseBroker(
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.CANCELLED,
                order_id="o-1",
                strategy_id="s-1",
                receipt_mapping=True,
                account_binding="proven",
                conclusive=True,
                retry_allowed=False,
            )
        ]
    )
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(
        store=store,
        now=lambda: datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
    )
    plan = _plan()
    assert engine.execute(plan, broker).state == ExecutionState.ACKNOWLEDGED

    unknown = engine.cancel(plan, broker)
    assert unknown.state == ExecutionState.UNKNOWN
    assert unknown.cancel_claim_id
    assert unknown.cancel_chain_uncertain is True
    assert broker.cancel_calls == 1

    recovered = engine.cancel(plan, broker)
    assert recovered.state == ExecutionState.CANCELLED
    assert recovered.cancel_claim_id == unknown.cancel_claim_id
    assert recovered.cancel_chain_uncertain is False
    assert broker.cancel_calls == 1
    assert broker.reconcile_calls == 1


def test_complete_submit_baseline_is_not_truncated_in_durable_receipt(
    tmp_path: Path,
) -> None:
    plan = _plan()
    baseline = [str(6_000_000 + index) for index in range(200)]
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    store.append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.CLAIMED,
            submit_chain_uncertain=True,
            submit_claim_id="claim-complete-baseline",
            remaining_shares=plan.shares,
            locator_proof={
                "baseline_order_ids": baseline,
                "baseline_order_count": len(baseline),
            },
        ),
        kind="durable_claim",
    )

    current = store.current(plan.plan_id)
    assert current is not None
    assert current.locator_proof["baseline_order_ids"] == baseline
    assert current.locator_proof["baseline_order_count"] == len(baseline)


def test_unknown_after_submit_never_replays_submit(tmp_path: Path) -> None:
    class UncertainBroker(FakeBroker):
        def submit(self, plan: TradePlan, claim_id: str, *, requested_shares: int | None = None) -> BrokerReceipt:
            self.submit_calls += 1
            raise TimeoutError("response lost after click")

    broker = UncertainBroker(reconcile=[BrokerReceipt(status=BrokerStatus.FILLED, order_id="o-1", filled_shares=200)])
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    messages: list[tuple[str, str]] = []
    engine = TradingExecution(
        store=store,
        now=lambda: datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
        notifier=lambda title, body: messages.append((title, body)),
    )

    unknown = engine.execute(_plan(), broker)
    assert unknown.state == ExecutionState.UNKNOWN
    assert unknown.next_action == "reconcile_only"
    assert broker.submit_calls == 1
    assert len(messages) == 1
    assert "000001.XSHE" in messages[0][1]
    assert "10.05" in messages[0][1]
    assert "200" in messages[0][1]

    final = engine.execute(_plan(), broker)
    assert final.state == ExecutionState.FILLED
    assert broker.submit_calls == 1
    assert broker.reconcile_calls == 1
    assert len(messages) == 1


def test_durable_claim_after_process_stop_reconciles_without_replaying_submit(
    tmp_path: Path,
) -> None:
    plan = _plan()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    store.append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.CLAIMED,
            attempt=1,
            remaining_shares=plan.shares,
            next_action="submit_once",
        ),
        kind="durable_claim",
        details={"claim_id": "claim-before-process-stop"},
    )
    broker = FakeBroker(
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.FILLED,
                order_id="o-1",
                strategy_id="s-1",
                filled_shares=plan.shares,
            )
        ]
    )
    engine = TradingExecution(store=store)

    receipt = engine.execute(plan, broker)

    assert receipt.state == ExecutionState.FILLED
    assert receipt.submit_chain_uncertain is True
    assert broker.submit_calls == 0
    assert broker.reconcile_calls == 1


@pytest.mark.parametrize(
    ("filter_date", "expected_state"),
    [
        ("2026-08-15", ExecutionState.REJECTED),
        ("2026-08-14", ExecutionState.UNKNOWN),
    ],
)
def test_live_prior_day_absence_reconcile_never_submits_and_requires_exact_dates(
    tmp_path: Path,
    filter_date: str,
    expected_state: ExecutionState,
) -> None:
    plan = _plan(environment="live")
    broker = FakeBroker(
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.REJECTED,
                reason="prior_day_broker_absence_proven",
                absence_proof=True,
                conclusive=True,
                account_binding="proven",
                filled_shares=0,
                locator_proof={
                    "exact_order_match_count": 0,
                    "exact_deal_match_count": 0,
                    "target_holding_shares": 0,
                    "historical_order_date_filter": {
                        "start": filter_date,
                        "end": filter_date,
                        "applied": True,
                    },
                    "historical_deal_date_filter": {
                        "start": filter_date,
                        "end": filter_date,
                        "applied": True,
                    },
                },
                field_readback={
                    "submitted": False,
                    "saved": False,
                    "started": False,
                },
            )
        ]
    )
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    store.append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.UNKNOWN,
            reason="server_confirmation_not_proven",
            filled_shares=0,
            remaining_shares=plan.shares,
            next_action="reconcile_only",
            submit_chain_uncertain=True,
        ),
        kind="submit_receipt_unproven",
    )
    engine = TradingExecution(store=store, notifier=lambda _title, _body: "ok")

    reconciled = engine.execute(plan, broker)
    repeated = engine.execute(plan, broker)

    assert reconciled.state == repeated.state == expected_state
    assert broker.submit_calls == 0
    assert broker.reconcile_calls == (1 if expected_state == ExecutionState.REJECTED else 2)
    if expected_state == ExecutionState.REJECTED:
        assert reconciled.absence_proof is True
        assert reconciled.reason == "prior_day_broker_absence_proven"
    else:
        assert reconciled.reason == "LIVE_RECONCILE_RECEIPT_UNPROVEN"


def test_live_order_is_denied_before_adapter_side_effect_without_two_keys(tmp_path: Path) -> None:
    broker = FakeBroker()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(
        store=store,
        safety_env={},
        auth_path=tmp_path / "missing-auth.json",
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
    )

    receipt = engine.execute(replace(_plan(environment="live")), broker)
    assert receipt.state == ExecutionState.REJECTED
    assert receipt.reason.startswith("SAFETY_DENIED")
    assert broker.probe_calls == 0
    assert broker.prepare_calls == 0
    assert broker.submit_calls == 0


def test_live_order_resumed_at_submit_window_rechecks_two_keys(tmp_path: Path) -> None:
    before = datetime(2026, 8, 24, 1, 20, tzinfo=timezone.utc)
    submit_at = datetime(2026, 8, 24, 1, 30, tzinfo=timezone.utc)
    clock = [before]
    broker = FakeBroker()
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={},
        auth_path=tmp_path / "missing-auth.json",
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: clock[0],
    )
    plan = replace(
        _plan(
            environment="live",
            deadline=submit_at + timedelta(minutes=15),
        ),
        submit_not_before=submit_at,
    )

    waiting = engine.execute(plan, broker)
    assert waiting.state == ExecutionState.VALIDATED
    assert waiting.reason == "SUBMIT_NOT_BEFORE"
    assert broker.probe_calls == 0

    clock[0] = submit_at
    denied = engine.execute(plan, broker)

    assert denied.state == ExecutionState.REJECTED
    assert denied.reason.startswith("SAFETY_DENIED")
    assert broker.submit_calls == 0


def test_live_switch_can_be_rehearsed_with_fake_adapter_but_never_without_gate(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker()
    broker.capability = replace(
        broker.capability,
        account_binding="bound",
        manual_position_shares=0,
        capabilities={"receipt_mapping": True},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )

    receipt = engine.execute(
        replace(
            _plan(
                environment="live",
                deadline=now + timedelta(minutes=15),
            )
        ),
        broker,
    )

    assert receipt.state == ExecutionState.ACKNOWLEDGED
    assert broker.probe_calls == 1
    assert broker.submit_calls == 1


def test_live_order_loads_capital_keys_at_submit_time_from_runtime_provider(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 24, 1, 30, tzinfo=timezone.utc)
    signing_key = "test-runtime-key"
    auth = make_authorization(
        scope="book-b-live-morning",
        max_notional=15_000.0,
        signing_key=signing_key,
        sides=["BUY"],
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(hours=1)).isoformat(),
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    calls: list[str] = []

    def safety_env_provider() -> dict[str, str]:
        calls.append("read")
        return {
            ENV_LIVE_ENABLED: "true",
            ENV_SIGNING_KEY: signing_key,
        }

    broker = FakeBroker()
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env_provider=safety_env_provider,
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )

    receipt = engine.execute(
        _plan(environment="live", deadline=now + timedelta(minutes=15)),
        broker,
    )

    assert receipt.state == ExecutionState.ACKNOWLEDGED
    assert calls == ["read", "read"]


def test_first_live_submit_can_prove_receipt_mapping_when_probe_is_pending(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker()
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )

    receipt = engine.execute(
        _plan(environment="live", deadline=now + timedelta(minutes=15)),
        broker,
    )

    assert receipt.state == ExecutionState.ACKNOWLEDGED
    assert broker.submit_calls == 1


def test_live_route_without_reconcile_capability_is_rejected_before_submit(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker()
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        supports_reconcile=False,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )

    receipt = engine.execute(
        _plan(environment="live", deadline=now + timedelta(minutes=15)),
        broker,
    )

    assert receipt.state == ExecutionState.REJECTED
    assert receipt.reason == "BROKER_RECONCILE_UNPROVEN"
    assert broker.submit_calls == 0


def test_live_submit_without_receipt_mapping_becomes_unknown_and_is_not_replayed(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.ACCEPTED,
                order_id="o-1",
                strategy_id="s-1",
                receipt_mapping=False,
                account_binding="proven",
            )
        ],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason="order mapping still unavailable",
                conclusive=False,
            )
        ],
    )
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )
    plan = _plan(environment="live", deadline=now + timedelta(minutes=15))

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)

    assert first.state == second.state == ExecutionState.UNKNOWN
    assert first.reason == "LIVE_SUBMIT_RECEIPT_UNPROVEN"
    assert first.next_action == "reconcile_only"
    assert broker.submit_calls == 1
    assert broker.reconcile_calls == 1


def test_unknown_live_submit_recovers_from_durable_claim_without_replay(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")

    class RecoveringBroker(FakeBroker):
        def __init__(self) -> None:
            super().__init__(
                submit=[
                    BrokerReceipt(
                        status=BrokerStatus.UNKNOWN,
                        account_binding="proven",
                        reason="submit response unknown",
                        conclusive=False,
                    )
                ]
            )
            self.recover_calls = 0

        def prepare(
            self,
            plan: TradePlan,
            *,
            requested_shares: int | None = None,
        ) -> BrokerReceipt:
            receipt = super().prepare(plan, requested_shares=requested_shares)
            return replace(
                receipt,
                order_id=None,
                locator_proof={
                    "baseline_order_ids": ["old-1"],
                    "baseline_observed_at": now.isoformat(),
                },
            )

        def recover(self, plan: TradePlan, previous: dict) -> BrokerReceipt:
            self.recover_calls += 1
            assert previous["submit_chain_uncertain"] is True
            assert previous["submit_claim_id"]
            assert previous["locator_proof"]["baseline_order_ids"] == ["old-1"]
            return BrokerReceipt(
                status=BrokerStatus.CANCELLED,
                order_id="o-recovered",
                strategy_id="s-recovered",
                receipt_mapping=True,
                account_binding="proven",
                requested_shares=plan.shares,
                remaining_shares=plan.shares,
                conclusive=True,
                reason="recovered exact delta",
            )

    broker = RecoveringBroker()
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )
    plan = _plan(environment="live", deadline=now + timedelta(minutes=15))

    unknown = engine.execute(plan, broker)
    recovered = engine.execute(plan, broker)

    assert unknown.state == ExecutionState.UNKNOWN
    assert unknown.submit_claim_id
    assert recovered.state == ExecutionState.CANCELLED
    assert recovered.broker_order_id == "o-recovered"
    assert recovered.broker_strategy_id == "s-recovered"
    assert recovered.submit_chain_uncertain is True
    assert broker.submit_calls == 1
    assert broker.recover_calls == 1
    assert broker.reconcile_calls == 0


def test_uncertain_live_submit_cannot_retry_after_partial_reconcile(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.ACCEPTED,
                order_id="o-1",
                strategy_id="s-1",
                receipt_mapping=False,
                account_binding="proven",
            )
        ],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-1",
                strategy_id="s-1",
                receipt_mapping=True,
                account_binding="proven",
                filled_shares=100,
                remaining_shares=100,
                latest_price=10.05,
                active=False,
                retry_allowed=True,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-1",
                strategy_id="s-1",
                receipt_mapping=True,
                account_binding="proven",
                filled_shares=100,
                remaining_shares=100,
                latest_price=10.05,
                active=False,
                retry_allowed=True,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
        ],
    )
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )
    plan = _plan(environment="live", deadline=now + timedelta(minutes=15))

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)
    third = engine.execute(plan, broker)

    assert first.state == ExecutionState.UNKNOWN
    assert second.state == third.state == ExecutionState.PARTIAL
    assert second.reason == third.reason == "UNCERTAIN_SUBMIT_NO_RETRY"
    assert broker.submit_calls == 1
    assert broker.reconcile_calls == 2


def test_live_reconcile_without_strategy_id_remains_unknown(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.ACCEPTED,
                order_id="o-1",
                receipt_mapping=False,
                account_binding="proven",
            )
        ],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.FILLED,
                order_id="o-1",
                receipt_mapping=True,
                account_binding="proven",
                filled_shares=200,
            )
        ],
    )
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )
    plan = _plan(environment="live", deadline=now + timedelta(minutes=15))

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)

    assert first.state == second.state == ExecutionState.UNKNOWN
    assert second.reason == "LIVE_RECONCILE_RECEIPT_UNPROVEN"
    assert broker.submit_calls == 1


def test_live_reconcile_cannot_bind_a_new_order_to_a_stale_strategy(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.ACCEPTED,
                order_id="o-1",
                strategy_id="s-1",
                receipt_mapping=False,
                account_binding="proven",
            )
        ],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.FILLED,
                order_id="o-2",
                receipt_mapping=True,
                account_binding="proven",
                filled_shares=200,
            )
        ],
    )
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )
    plan = _plan(environment="live", deadline=now + timedelta(minutes=15))

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)

    assert first.state == second.state == ExecutionState.UNKNOWN
    assert second.reason == "LIVE_RECONCILE_RECEIPT_UNPROVEN"
    assert second.broker_order_id == "o-2"
    assert broker.submit_calls == 1


def test_live_reconcile_can_discover_order_id_from_the_claimed_strategy(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.ACCEPTED,
                strategy_id="s-1",
                receipt_mapping=False,
                account_binding="proven",
            )
        ],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.ACCEPTED,
                order_id="o-1",
                receipt_mapping=True,
                account_binding="proven",
                filled_shares=0,
            )
        ],
    )
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )
    plan = _plan(environment="live", deadline=now + timedelta(minutes=15))

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)

    assert first.state == ExecutionState.UNKNOWN
    assert second.state == ExecutionState.ACKNOWLEDGED
    assert second.broker_order_id == "o-1"
    assert second.broker_strategy_id == "s-1"
    assert broker.submit_calls == 1


def test_capability_parser_fails_closed_without_explicit_reconcile_proof() -> None:
    base = {
        "status": "ready",
        "environment": "live",
        "logical_account_id": "primary",
        "capabilities": {"submit": True},
    }

    assert BrokerCapability.from_template(base).supports_reconcile is False
    assert BrokerCapability.from_template(
        {**base, "capabilities": {"submit": True, "reconcile": False}}
    ).supports_reconcile is False
    assert BrokerCapability.from_template(
        {**base, "capabilities": {"submit": True, "reconcile": True}}
    ).supports_reconcile is True
    assert BrokerCapability(
        ready=True,
        environment="live",
        logical_account_id="primary",
        supports_submit=True,
    ).supports_reconcile is False


def test_unproved_live_rejection_becomes_unknown(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.REJECTED,
                reason="ambiguous rejection",
                conclusive=True,
            )
        ]
    )
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )

    receipt = engine.execute(
        _plan(environment="live", deadline=now + timedelta(minutes=15)),
        broker,
    )

    assert receipt.state == ExecutionState.UNKNOWN
    assert receipt.reason == "LIVE_SUBMIT_RECEIPT_UNPROVEN"
    assert receipt.submit_chain_uncertain is True


def test_proved_no_click_live_rejection_is_terminal(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    signing_key = "test-human-key"
    auth = make_authorization(
        scope="isolated-test",
        max_notional=10000.0,
        signing_key=signing_key,
        sides=["BUY"],
        codes=["000001.XSHE"],
        issued_at=now.isoformat(),
        expires_at="2026-08-16T00:00:00+00:00",
    )
    auth_path = tmp_path / "live_authorization.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.REJECTED,
                reason="non_trading_time",
                account_binding="proven",
                conclusive=True,
                field_readback={
                    "submitted": False,
                    "saved": False,
                    "started": False,
                },
            )
        ]
    )
    broker.capability = replace(
        broker.capability,
        account_binding="proven",
        manual_position_shares=0,
        capabilities={"receipt_mapping": False},
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing_key},
        auth_path=auth_path,
        audit_path=tmp_path / "audit.jsonl",
        notifier=lambda _title, _body: "ok",
        now=lambda: now,
    )

    receipt = engine.execute(
        _plan(environment="live", deadline=now + timedelta(minutes=15)),
        broker,
    )

    assert receipt.state == ExecutionState.REJECTED
    assert receipt.reason == "non_trading_time"
    assert receipt.submit_chain_uncertain is False


@pytest.mark.parametrize("guard,reason", [("limit_down", "LIMIT_DOWN_BUY_BLOCKED"), ("unavailable", "LIMIT_DOWN_CHECK_UNAVAILABLE")])
def test_buy_market_guard_fails_closed_before_probe(tmp_path: Path, guard: str, reason: str) -> None:
    broker = FakeBroker()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(store=store)

    receipt = engine.execute(replace(_plan(guard=guard)), broker)
    assert receipt.state == ExecutionState.SKIPPED
    assert receipt.reason == reason
    assert broker.probe_calls == 0
    assert broker.submit_calls == 0


def test_buy_after_recovery_deadline_is_skipped_before_probe(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 45, tzinfo=timezone.utc)
    broker = FakeBroker()
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        now=lambda: now,
    )
    receipt = engine.execute(
        _plan(deadline=now),
        broker,
    )
    assert receipt.state == ExecutionState.SKIPPED
    assert receipt.reason == "RECOVERY_DEADLINE_REACHED"
    assert broker.probe_calls == 0


def test_live_buy_outside_continuous_auction_is_skipped_before_probe(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
    broker = FakeBroker()
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        now=lambda: now,
    )

    receipt = engine.execute(
        replace(
            _plan(
                environment="live",
                deadline=datetime(2026, 8, 15, 6, 57, tzinfo=timezone.utc),
            ),
            price_rule="min(frozen_open*1.005,basket_price)",
        ),
        broker,
    )

    assert receipt.state == ExecutionState.SKIPPED
    assert receipt.reason == "OUTSIDE_CONTINUOUS_AUCTION"
    assert broker.probe_calls == 0


def test_prepare_mismatch_is_rejected_without_submit(tmp_path: Path) -> None:
    class MismatchBroker(FakeBroker):
        def prepare(self, plan: TradePlan, *, requested_shares: int | None = None) -> BrokerReceipt:
            self.prepare_calls += 1
            return BrokerReceipt(
                status=BrokerStatus.PREPARED,
                order_id="o-1",
                echoed={"code": "000002.XSHE", "side": plan.side, "shares": plan.shares, "limit_price": plan.limit_price},
            )

    broker = MismatchBroker()
    engine = TradingExecution(store=InMemoryExecutionStore(tmp_path / "events.jsonl"))

    receipt = engine.execute(_plan(), broker)
    assert receipt.state == ExecutionState.REJECTED
    assert receipt.reason == "PREPARE_MISMATCH"
    assert broker.submit_calls == 0


def test_prepare_unknown_is_reconcile_only_and_never_submits(tmp_path: Path) -> None:
    class UnknownPrepareBroker(FakeBroker):
        def prepare(self, plan: TradePlan, *, requested_shares: int | None = None) -> BrokerReceipt:
            self.prepare_calls += 1
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason="page_transition_lost",
                conclusive=False,
            )

    broker = UnknownPrepareBroker()
    engine = TradingExecution(store=InMemoryExecutionStore(tmp_path / "events.jsonl"))

    receipt = engine.execute(_plan(), broker)
    assert receipt.state == ExecutionState.UNKNOWN
    assert receipt.next_action == "reconcile_only"
    assert broker.submit_calls == 0


def test_prepare_unknown_permanently_blocks_automatic_submit(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)

    class UnknownPrepareBroker(FakeBroker):
        def prepare(self, plan: TradePlan, *, requested_shares: int | None = None) -> BrokerReceipt:
            self.prepare_calls += 1
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason="page_transition_lost",
                conclusive=False,
            )

    broker = UnknownPrepareBroker(
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="unexpected-order",
                filled_shares=100,
                remaining_shares=100,
                latest_price=10.05,
                active=False,
                retry_allowed=True,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="unexpected-order",
                filled_shares=100,
                remaining_shares=100,
                latest_price=10.05,
                active=False,
                retry_allowed=True,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
        ]
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        now=lambda: now,
    )
    plan = _plan()

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)
    third = engine.execute(plan, broker)

    assert first.state == ExecutionState.UNKNOWN
    assert second.state == third.state == ExecutionState.PARTIAL
    assert second.reason == third.reason == "UNCERTAIN_SUBMIT_NO_RETRY"
    assert broker.submit_calls == 0


def test_mixed_account_manual_holding_blocks_new_buy(tmp_path: Path) -> None:
    broker = FakeBroker()
    broker.capability = replace(broker.capability, manual_position_shares=100, position_source="account_readback")
    engine = TradingExecution(store=InMemoryExecutionStore(tmp_path / "events.jsonl"))

    receipt = engine.execute(_plan(), broker)
    assert receipt.state == ExecutionState.SKIPPED
    assert receipt.reason == "MANUAL_HOLDING_CONFLICT"
    assert broker.submit_calls == 0


def test_sell_is_bounded_by_book_b_owned_and_sellable_shares(tmp_path: Path) -> None:
    broker = FakeBroker()
    broker.capability = replace(
        broker.capability,
        owned_position_shares=100,
        sellable_shares=100,
        position_source="account_readback",
    )
    plan = replace(
        _plan(), side="SELL", shares=200, basket_price=None,
        owned_lot_id="lot-1", sell_authorized=True,
        sell_reason="HARD_STOP", sell_decision_phase="risk_floor",
        sell_decision_at=datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
    )
    engine = TradingExecution(store=InMemoryExecutionStore(tmp_path / "events.jsonl"))

    receipt = engine.execute(plan, broker)
    assert receipt.state == ExecutionState.REJECTED
    assert receipt.reason == "OWNED_POSITION_BOUND"
    assert broker.submit_calls == 0


def test_sell_with_ledger_cannot_consume_unattributed_manual_shares(tmp_path: Path) -> None:
    broker = FakeBroker()
    broker.capability = replace(
        broker.capability,
        owned_position_shares=500,
        sellable_shares=500,
        position_source="account_readback",
    )
    ledger = TradingAccountLedger(tmp_path / "book_b_ledger.jsonl")
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        ledger=ledger,
    )

    receipt = engine.execute(
        replace(
            _plan(), side="SELL", shares=100, basket_price=None,
            owned_lot_id="lot-1", sell_authorized=True,
            sell_reason="HARD_STOP", sell_decision_phase="risk_floor",
            sell_decision_at=datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
        ),
        broker,
    )
    assert receipt.state == ExecutionState.SKIPPED
    assert receipt.reason == "OWNED_LEDGER_BOUND"
    assert broker.submit_calls == 0


def test_frozen_row_builder_only_materializes_existing_book_b_limit_rule() -> None:
    plan = trade_plan_from_frozen_row(
        {
            "date": "2026-08-15",
            "code": "000001.XSHE",
            "name": "测试标的",
            "open": 10.0,
            "basket_price": 10.10,
            "mode_exec_planned_shares": 300,
            "market_guard_status": "ok",
        },
        environment="mock",
        logical_account_id="primary",
        now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
    )
    assert plan.plan_id == "book-b:2026-08-15:000001.XSHE:BUY"
    assert plan.limit_price == 10.05
    assert plan.basket_price == 10.10
    assert plan.shares == 300
    assert plan.recovery_deadline.isoformat() == "2026-08-15T01:45:00+00:00"


def test_live_frozen_row_builder_keeps_afternoon_continuation_open() -> None:
    plan = trade_plan_from_frozen_row(
        {
            "date": "2026-08-15",
            "book": "B",
            "is_live": True,
            "mode_exec_star": True,
            "mode_trade_eligible": True,
            "code": "000001.XSHE",
            "name": "测试标的",
            "open": 10.0,
            "basket_price": 10.10,
            "mode_exec_planned_shares": 300,
            "market_guard_status": "T",
            "market_guard_required": True,
            "market_price": 10.0,
            "down_price": 9.0,
            "market_observed_at": "2026-08-15T14:40:00+08:00",
            "allocation_proof_hash": "proof",
        },
        environment="live",
        logical_account_id="primary",
        now=datetime(2026, 8, 15, 6, 40, tzinfo=timezone.utc),
    )

    assert plan.recovery_deadline.isoformat() == "2026-08-15T06:57:00+00:00"
    assert plan.guard_reason(
        now=datetime(2026, 8, 15, 6, 40, tzinfo=timezone.utc)
    ) is None


def test_frozen_row_builder_floors_buy_limit_to_valid_stock_tick() -> None:
    plan = trade_plan_from_frozen_row(
        {
            "date": "2026-08-24",
            "code": "601011.XSHG",
            "name": "宝泰隆",
            "open": 2.71,
            "basket_price": 2.7661,
            "mode_exec_planned_shares": 1800,
            "market_guard_status": "ok",
        },
        environment="mock",
        logical_account_id="primary",
    )

    assert plan.limit_price == 2.72
    assert plan.limit_price <= 2.71 * 1.005


def test_frozen_row_builder_normalizes_realtime_trade_status() -> None:
    plan = trade_plan_from_frozen_row(
        {
            "date": "2026-08-15",
            "code": "000001.XSHE",
            "name": "测试标的",
            "open": 10.0,
            "basket_price": 10.10,
            "mode_exec_planned_shares": 100,
            "trade_status": "T",
        },
        environment="mock",
        logical_account_id="primary",
    )
    assert plan.market_guard_status == "ok"
    assert plan.validation_error() is None


def test_live_plan_normalizes_sse_trading_status_and_vendor_clock() -> None:
    now = datetime(2026, 8, 24, 1, 30, tzinfo=timezone.utc)
    plan = trade_plan_from_frozen_row(
        {
            "date": "2026-08-24",
            "code": "601011.XSHG",
            "name": "宝泰隆",
            "book": "B",
            "is_live": True,
            "mode_exec_star": True,
            "mode_trade_eligible": True,
            "open": 2.71,
            "basket_price": 2.7661,
            "mode_exec_planned_shares": 100,
            "market_guard_required": True,
            "trade_status": "T100",
            "market_price": 2.71,
            "down_price": 2.59,
            "market_observed_at": "09:25:00:480",
            "allocation_proof_hash": "proof",
        },
        environment="live",
        logical_account_id="primary",
        now=now,
    )

    assert plan.market_guard_status == "ok"
    assert plan.market_guard_observed_at is not None
    assert plan.market_guard_observed_at.isoformat() == "2026-08-24T09:25:00.480000+08:00"
    assert plan.guard_reason(now=now) is None


def test_live_plan_reuses_shared_limit_down_guard() -> None:
    plan = trade_plan_from_frozen_row(
        {
            "date": "2026-08-15",
            "code": "000001.XSHE",
            "name": "测试标的",
            "book": "B",
            "is_live": True,
            "mode_exec_star": True,
            "mode_trade_eligible": True,
            "executable_fillable": True,
            "open": 10.0,
            "basket_price": 10.10,
            "mode_exec_planned_shares": 100,
            "market_guard_required": True,
            "trade_status": "T",
            "market_price": 10.0,
            "down_price": 10.0,
            "market_observed_at": "2026-08-15T01:01:00+00:00",
        },
        environment="live",
        logical_account_id="primary",
        now=datetime(2026, 8, 15, 1, 1, 30, tzinfo=timezone.utc),
    )
    assert plan.guard_reason() == "LIMIT_DOWN_BUY_BLOCKED"


def test_partial_fill_retries_only_when_realtime_price_is_within_basket(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    broker = FakeBroker(
        submit=[
            BrokerReceipt(status=BrokerStatus.PARTIAL, order_id="o-1", filled_shares=100, remaining_shares=100),
            BrokerReceipt(status=BrokerStatus.FILLED, order_id="o-2", filled_shares=100),
        ],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-1",
                filled_shares=100,
                remaining_shares=100,
                latest_price=10.20,
                active=False,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-1",
                filled_shares=100,
                remaining_shares=100,
                latest_price=10.05,
                active=False,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
        ],
    )
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(store=store, now=lambda: now)

    partial = engine.execute(_plan(), broker)
    assert partial.state == ExecutionState.PARTIAL
    assert partial.next_action == "reconcile"
    assert broker.submit_calls == 1

    held = engine.execute(_plan(), broker)
    assert held.state == ExecutionState.PARTIAL
    assert held.next_action == "wait_for_basket"
    assert broker.submit_calls == 1

    final = engine.execute(_plan(), broker)
    assert final.state == ExecutionState.FILLED
    assert final.filled_shares == 200
    assert broker.submit_calls == 2


def test_partial_fill_never_submits_more_than_one_controlled_retry(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc)
    broker = FakeBroker(
        submit=[
            BrokerReceipt(status=BrokerStatus.PARTIAL, order_id="o-1", filled_shares=50),
            BrokerReceipt(status=BrokerStatus.PARTIAL, order_id="o-2", filled_shares=50),
            BrokerReceipt(status=BrokerStatus.FILLED, order_id="o-3", filled_shares=100),
        ],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-1",
                filled_shares=50,
                latest_price=10.05,
                active=False,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-2",
                filled_shares=50,
                latest_price=10.05,
                active=False,
                observed_at=now,
                field_readback={"order_terminal": True},
            ),
        ],
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        now=lambda: now,
    )
    plan = _plan()

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)
    third = engine.execute(plan, broker)

    assert first.state == second.state == third.state == ExecutionState.PARTIAL
    assert third.reason == "RETRY_LIMIT_REACHED"
    assert broker.submit_calls == 2


def test_submit_boundary_blocks_a_third_attempt_from_any_state(tmp_path: Path) -> None:
    broker = FakeBroker(
        submit=[
            BrokerReceipt(status=BrokerStatus.PREPARED),
            BrokerReceipt(status=BrokerStatus.PREPARED),
            BrokerReceipt(status=BrokerStatus.FILLED, order_id="o-3", filled_shares=200),
        ]
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl")
    )
    plan = _plan()

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)
    third = engine.execute(plan, broker)

    assert first.state == second.state == ExecutionState.PREPARED
    assert third.state == ExecutionState.REJECTED
    assert third.reason == "RETRY_LIMIT_REACHED"
    assert broker.submit_calls == 2


def test_repeated_reconcile_of_same_order_does_not_double_count_fill(tmp_path: Path) -> None:
    broker = FakeBroker(
        submit=[BrokerReceipt(status=BrokerStatus.PARTIAL, order_id="o-1", filled_shares=100)],
        reconcile=[
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-1",
                filled_shares=100,
                active=True,
                observed_at=datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
            ),
            BrokerReceipt(
                status=BrokerStatus.PARTIAL,
                order_id="o-1",
                filled_shares=100,
                active=True,
                observed_at=datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
            ),
        ],
    )
    engine = TradingExecution(
        store=InMemoryExecutionStore(tmp_path / "events.jsonl"),
        now=lambda: datetime(2026, 8, 15, 1, 1, tzinfo=timezone.utc),
    )

    first = engine.execute(_plan(), broker)
    second = engine.execute(_plan(), broker)
    third = engine.execute(_plan(), broker)
    assert first.filled_shares == second.filled_shares == third.filled_shares == 100
    assert third.remaining_shares == 100


def test_terminal_receipt_is_idempotent_and_event_chain_is_durable(tmp_path: Path) -> None:
    broker = FakeBroker(submit=[BrokerReceipt(status=BrokerStatus.FILLED, order_id="o-1", filled_shares=200)])
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    engine = TradingExecution(store=store)
    plan = _plan()

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)
    assert first.state == second.state == ExecutionState.FILLED
    assert broker.submit_calls == 1
    events = store.events(plan.plan_id)
    assert len(events) >= 4
    assert all(event["event_hash"] for event in events)
    assert events[0]["previous_hash"] is None
    for previous, current in zip(events, events[1:]):
        assert current["previous_hash"] == previous["event_hash"]
    restored = InMemoryExecutionStore(tmp_path / "events.jsonl").current(plan.plan_id)
    assert restored is not None
    assert restored.event_id == events[-1]["event_id"]


def test_book_b_ledger_records_proved_fill_once_and_rebuilds_ownership(tmp_path: Path) -> None:
    broker = FakeBroker(
        submit=[
            BrokerReceipt(
                status=BrokerStatus.FILLED,
                order_id="o-1",
                filled_shares=200,
                fill_price=10.03,
                order_price=10.05,
            )
        ]
    )
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    ledger = TradingAccountLedger(tmp_path / "book_b_ledger.jsonl")
    engine = TradingExecution(store=store, ledger=ledger)
    plan = _plan()

    first = engine.execute(plan, broker)
    second = engine.execute(plan, broker)
    assert first.filled_shares == second.filled_shares == 200
    assert ledger.owned_shares(logical_account_id="primary", code="000001.XSHE") == 200
    rows = [json.loads(line) for line in (tmp_path / "book_b_ledger.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["source_execution_event_id"] == first.event_id


def test_account_writer_fence_and_takeover_capsule_are_durable(tmp_path: Path) -> None:
    class UnknownBroker(FakeBroker):
        def submit(self, plan: TradePlan, claim_id: str, *, requested_shares: int | None = None) -> BrokerReceipt:
            self.submit_calls += 1
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason="response_lost",
                conclusive=False,
                template_name="test-template",
                template_version="1",
                account_binding="fingerprint:abc",
                locator_proof={"route": "manual-limit", "secret": "must-not-matter"},
            )

        def reconcile(self, plan: TradePlan, previous: dict) -> BrokerReceipt:
            self.reconcile_calls += 1
            return BrokerReceipt(status=BrokerStatus.UNKNOWN, reason="response_lost", conclusive=False)

    notifications: list[object] = []
    broker = UnknownBroker()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")

    def notify(_title: str, _body: str) -> object:
        notifications.append(object())
        return "ok" if len(notifications) > 1 else "failed"

    engine = TradingExecution(store=store, notifier=notify)
    first = engine.execute(_plan(), broker)
    second = engine.execute(_plan(), broker)
    assert first.state == second.state == ExecutionState.UNKNOWN
    assert broker.submit_calls == 1
    assert len(notifications) == 2
    takeover_path = tmp_path / "trading_takeovers.jsonl"
    capsule = json.loads(takeover_path.read_text(encoding="utf-8").splitlines()[0])
    assert capsule["safe_next_action"] == "reconcile_only"
    assert capsule["forbidden_actions"] == ["submit", "blind_retry", "create_new_plan"]
    assert capsule["receipt"]["template_name"] == "test-template"
    assert capsule["receipt"]["event_id"]
    assert "secret" not in json.dumps(capsule, ensure_ascii=False).lower()
    assert any(path.name.startswith("account-") for path in (tmp_path / "account_writer_locks").iterdir())
    assert any(row.get("status") == "delivered" for row in (
        json.loads(line) for line in (tmp_path / "trading_incidents.jsonl").read_text().splitlines()
    ))


def test_ownership_evidence_rejects_canonical_account_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="canonical account files"):
        TradingAccountLedger(tmp_path / "positions.jsonl")


def test_sell_builder_requires_monitor_authorization_and_owned_lot() -> None:
    base = {
        "date": "2026-08-15",
        "code": "000001.XSHE",
        "name": "测试标的",
        "shares": 100,
        "limit_price": 10.0,
    }
    with pytest.raises(ValueError, match="OWNED_LOT_ID_MISSING"):
        trade_plan_from_frozen_row(
            base,
            environment="mock",
            logical_account_id="primary",
            side="SELL",
        )
    authorized = trade_plan_from_frozen_row(
        {
            **base,
            "owned_lot_id": "book-b:000001:2026-08-14",
            "sell_authorized": True,
            "sell_reason": "HARD_STOP",
            "decision_phase": "risk_floor",
            "decision_at": "2026-08-15T01:01:00+00:00",
        },
        environment="mock",
        logical_account_id="primary",
        side="SELL",
    )
    assert authorized.validation_error() is None
