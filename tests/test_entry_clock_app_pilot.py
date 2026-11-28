from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
import pytest
from xiaocao.live import entry_clock_pilot as pilot
from xiaocao.live import book_b_live_morning as morning
from xiaocao.live import book_b_live_lifecycle as life
from xiaocao.live import inherited_execution, live_decision_support as policy
from xiaocao.live.book_b_allocation import BookBAllocationFacts
from xiaocao.live.trading_execution import (
    ExecutionStore,
    ExecutionReceipt,
    ExecutionState,
    TradePlan,
)

pytestmark = pytest.mark.app_simulation
DAY = "2026-11-30"
T = datetime.fromisoformat(DAY + "T09:26:00+08:00")


def ordinary(code="000001.XSHE", shares=200, price=10.0):
    return TradePlan(
        plan_id=f"book-b:{DAY}:{code}:BUY",
        strategy_run_id="run",
        snapshot_ref="freeze",
        strategy_sha="sha",
        trade_date=DAY,
        book="B",
        logical_account_id="primary",
        environment="live",
        code=code,
        name="测试",
        side="BUY",
        shares=shares,
        limit_price=price,
        basket_price=price,
        market_guard_status="ok",
        created_at=T,
        recovery_deadline=T + timedelta(minutes=9),
        allocation_proof_hash="a" * 64,
    )


def split(path, plans):
    return pilot.split_before_binding(path, DAY, plans, T, cash_budget=lambda: 3000.0)


def test_split_conserves_allocation_and_binds_restart(tmp_path):
    p = ordinary()
    other = ordinary("600001.XSHG", shares=300)
    assert split(tmp_path, [p, other]) == [p, other]
    pilot.enable(tmp_path, T)
    assert split(
        tmp_path, [ordinary(shares=100), ordinary("600002.XSHG", price=31)]
    ) == [ordinary(shares=100), ordinary("600002.XSHG", price=31)]
    early, survivor = split(tmp_path, [p, other])
    assert (
        early.shares + 100 == p.shares
        and survivor == other
        and early.plan_hash != p.plan_hash
    )
    assert split(tmp_path, [p, other])[0] == early
    with pytest.raises(ValueError, match="allocation_changed"):
        split(tmp_path, [replace(p, shares=500)])
    assert not pilot.can_allocate(tmp_path, "2026-12-01")


@pytest.mark.parametrize(
    "mode", ["filled", "expired", "risk", "missing_shadow", "wait_failed", "duplicate"]
)
def test_original_after_business_one_effect_or_cash(tmp_path, monkeypatch, mode):
    p = ordinary()
    pilot.enable(tmp_path, T)
    early = split(tmp_path, [p])[0]
    config = morning.BookBLiveMorningConfig(
        DAY, tmp_path / "freeze", tmp_path / "facts", tmp_path, policy_root=tmp_path
    )
    morning.bind_durable_live_plan_intents(tmp_path, [early])
    store = ExecutionStore(tmp_path / "events.jsonl")
    primary = store.append(
        plan=early,
        receipt=ExecutionReceipt(
            early.plan_id,
            early.plan_hash,
            ExecutionState.FILLED,
            filled_shares=early.shares,
            fill_price=p.limit_price,
            broker_order_id="101",
            broker_strategy_id="native-101",
            receipt_mapping=True,
            account_binding="proven",
            submit_claim_id="a",
        ),
    )
    receipt = SimpleNamespace(
        status="completed",
        execution_receipts=[primary.as_dict()],
        review_rendezvous=None,
    )
    monkeypatch.setattr(life, "blocking_open_execution_plan_ids", lambda *a, **k: ())
    monkeypatch.setattr(life, "unresolved_prior_sell_codes", lambda *a, **k: ())
    monkeypatch.setattr(inherited_execution, "query_codes", lambda *a, **k: ())
    monkeypatch.setattr(
        morning,
        "_load_allocation",
        lambda *a, **k: BookBAllocationFacts(100000, 100000),
    )
    policy.bind_plan_audit(tmp_path, early, {"effective_deploy_factor": 1.0})
    monkeypatch.setattr(policy, "read_policy", lambda *a, **k: {})
    monkeypatch.setattr(
        policy,
        "buy_cap",
        lambda *a, **k: dict(skip=mode == "risk", effective_deploy_factor=1),
    )
    start, end = pilot.windows(DAY)
    clock = [T]

    def wait(at):
        assert at == start
        if mode == "wait_failed":
            raise RuntimeError("test")
        clock[0] = end if mode == "expired" else at

    seen = []

    def submit(child):
        assert pilot.authorized_child(child) and child.limit_price == early.limit_price
        assert (
            child.validation_error() is None and child.shares + early.shares == p.shares
        )
        seen.append(child)
        return store.append(
            plan=child,
            receipt=ExecutionReceipt(
                child.plan_id,
                child.plan_hash,
                ExecutionState.ACKNOWLEDGED,
                broker_order_id="101" if mode == "duplicate" else "102",
                submit_claim_id="b",
            ),
        )

    def shadow(doc):
        if mode == "missing_shadow":
            raise ValueError("missing_shadow")
        return "1" * 64

    callbacks = dict(
        clock=lambda: clock[0],
        wait=wait,
        shadow=shadow,
        allocation_facts=lambda: {},
        risk=lambda t: True,
        guard=lambda row: dict(
            market_guard_status="T100",
            market_guard_required=True,
            market_observed_at=clock[0].isoformat(),
            down_price=8,
            market_price=10,
        ),
        submission_scope=lambda p: nullcontext(),
        execute=submit,
    )
    result = pilot.run_assigned(config, receipt, **callbacks)
    assert result["kind"] == (
        "observed"
        if mode == "filled"
        else "reconcile_only"
        if mode == "duplicate"
        else "no_submit"
    )
    assert len(seen) == (mode in ("filled", "duplicate"))
    assert pilot.run_assigned(config, receipt, **callbacks) == result and len(seen) == (
        mode in ("filled", "duplicate")
    )
    if seen:
        assert not pilot.authorized_child(seen[0])


def test_frozen_source_reproduces_no_submit_and_rejects_impossible_settlement(tmp_path):
    from xiaocao.research import split_evidence

    state = tmp_path
    p = ordinary()
    pilot.enable(state, T)
    early = split(state, [p])[0]
    doc, _, _ = pilot.load_assignment(state, DAY)
    morning.bind_durable_live_plan_intents(state, [early])
    exe = ExecutionStore(state / "events.jsonl")
    exe.append(
        plan=early,
        receipt=ExecutionReceipt(
            early.plan_id, early.plan_hash, ExecutionState.SKIPPED
        ),
    )
    pilot.write(
        pilot.root(state) / "dispositions" / (DAY + ".json"),
        dict(
            day=DAY,
            child_id=doc["child_id"],
            kind="no_submit",
            assignment=doc["sha256"],
            reason="cash",
        ),
    )
    packet = split_evidence.collect(state, doc)
    actual = dict(
        status="no_submit",
        assignment=doc["sha256"],
        child_id=doc["child_id"],
        disposition="no_submit",
    )
    split_evidence.verify(packet, actual, DAY)
    with pytest.raises(ValueError, match="absence"):
        split_evidence.verify(packet, {**actual, "status": "closed"}, DAY)
    packet["executions"][early.plan_id][0]["state"] = "filled"
    with pytest.raises(ValueError, match="execution"):
        split_evidence.verify(packet, actual, DAY)


def test_child_lot_projection_reopens_from_frozen_fill_and_posting_rows(
    tmp_path, monkeypatch
):
    from pathlib import Path
    from xiaocao.live.trading_execution import BookBOwnershipEvidence
    from xiaocao.live.book_b_accounting import sync_journal
    from xiaocao.research import split_evidence

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import research_day_limit_pair as pair

    state = tmp_path
    pilot.enable(state, T)
    p = ordinary()
    early = split(state, [p])[0]
    doc, _, _ = pilot.load_assignment(state, DAY)
    start, end = pilot.windows(DAY)
    child = replace(
        p,
        plan_id=doc["child_id"],
        shares=100,
        submit_not_before=start,
        recovery_deadline=end,
        created_at=start,
    )
    exe = ExecutionStore(state / "events.jsonl")
    ownership = BookBOwnershipEvidence(state / "book_b_ownership_evidence.jsonl")
    for plan, order in [(early, "parent101"), (child, "child102")]:
        morning.bind_durable_live_plan_intents(state, [plan])
        raw = exe.append(
            plan=plan,
            receipt=ExecutionReceipt(
                plan.plan_id,
                plan.plan_hash,
                ExecutionState.FILLED,
                broker_order_id=order,
                submit_claim_id=order,
                receipt_mapping=True,
                account_binding="proven",
                filled_shares=plan.shares,
                fill_price=9.80,
            ),
        )
        ownership.record(plan, raw)
    sync_journal(state)
    actual = pair.actual_child(state, DAY, doc)
    packet = split_evidence.collect(state, doc)
    split_evidence.verify(packet, actual, DAY)
    assert (
        actual["bought"] == 100
        and actual["buy_gross"] == 980
        and actual["buy_actual_fee"] is None
    )
    assert len(packet["ownership"]) == 1 and len(packet["journal"]) == 1
    packet["journal"][0]["entry"]["shares"] = 200
    with pytest.raises(ValueError, match="posting"):
        split_evidence.verify(packet, actual, DAY)
