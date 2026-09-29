"""Behavioral APP capital/accounting regression; no real native actions."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from xiaocao.live.book_b_capital import POLICY, SOURCE, digest, flows, verify_account
from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account
from xiaocao.live.book_b_live_morning import load_book_b_live_capital_basis
from xiaocao.live.live_decision_support import evaluate_live_risk, load_live_nav_history
from xiaocao.live.safety import (ENV_LIVE_ENABLED, ENV_SIGNING_KEY,
    authorize_capital_action, make_authorization, sign_payload)
from tests.test_book_b_live_lifecycle import (_snapshot, _plan, _record_fill,
    _bind_plan_intent, NOW)
from tests.test_book_b_live_policy import _history, _mark

pytestmark = pytest.mark.app_simulation


def activate(root, binding="a"*64):
    body = {"policy_id": POLICY, "logical_account_id": "primary",
        "fund_account_binding_sha256": binding}
    body["policy_sha256"] = digest(body)
    (root / "capital_policy.json").write_text(json.dumps(body))


def with_cash(snapshot, cash):
    snapshot.pop("snapshot_sha256")
    market = snapshot["funds_summary"]["securities_market_value"]
    for key in ("funds_summary", "broker_summary"):
        snapshot[key].update(available_cash=cash, cash_balance=cash,
            withdrawable_cash=cash, total_assets=round(cash+market, 2),
            asset_equation_cash_field="cash_balance")
    snapshot["snapshot_sha256"] = digest(snapshot)
    return snapshot


def project(root, snapshot):
    return project_book_b_live_account(root, snapshot,
        trade_date=snapshot["trade_date"], now=datetime.fromisoformat(snapshot["observed_at"]))


def test_dynamic_nav_and_cash_replace_seed_without_changing_ratios(tmp_path):
    activate(tmp_path)
    account = project(tmp_path, with_cash(_snapshot(), 100000))
    basis = load_book_b_live_capital_basis(tmp_path,
        trade_date="2026-09-01", current_account=account)
    assert basis.source == SOURCE and basis.settled_nav == 100000
    assert account.cash == 100000 and account.net_external_flow_total == 70000
    assert verify_account(tmp_path, account.as_dict()) == Decimal("30000")
    from xiaocao.live.book_b_allocation import BookBAllocationFacts
    facts = BookBAllocationFacts(available_cash=100000, settled_nav=basis.settled_nav,
        current_open_exposure=0, deploy_factor=1)
    assert facts.cash_limit == 50000


def test_funding_and_withdrawal_create_no_profit_and_are_idempotent(tmp_path):
    activate(tmp_path)
    first = project(tmp_path, with_cash(_snapshot(), 100000))
    repeated = project(tmp_path, with_cash(_snapshot(), 100000))
    assert first == repeated and len(flows(tmp_path)) == 1
    second = project(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 40000))
    assert second.realized_cash_delta == 0
    assert second.net_external_flow_total == 10000
    assert second.external_flow_total == 130000
    assert verify_account(tmp_path, second.as_dict()) == Decimal("30000")


def test_buy_over_legacy_seed_replays_with_owned_fees(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    buy = _record_fill(tmp_path, replace(_plan(), shares=6000),
        price=10, event_id="large")
    snapshot = _snapshot(shares=6000, price=11, observed_at=NOW+timedelta(seconds=1),
        broker_fills=(("order-large", buy.code, "BUY", 6000, 10),))
    account = project(tmp_path, with_cash(snapshot, 39994))
    assert account.cash == 39994 and account.net_external_flow_total == 70000
    assert account.current_open_exposure == 66000 and len(flows(tmp_path)) == 1
    assert account.realized_cash_delta == -60006
    from xiaocao.live.buy_preflight import current_owned_book_b_codes
    assert current_owned_book_b_codes(tmp_path) == {buy.code}


def test_manual_holdings_and_open_buy_reservations_are_not_added(tmp_path):
    activate(tmp_path)
    account = project(tmp_path, with_cash(_snapshot(shares=10000, sellable=10000), 80000))
    assert account.lots == () and account.settled_nav == 80000
    _bind_plan_intent(tmp_path, _plan())  # durable unclaimed reserved BUY
    frozen = project(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 79000))
    assert frozen.cash == 80000 and len(flows(tmp_path)) == 1


def test_capital_flow_does_not_rewrite_legacy_settlements_or_reset_pause(tmp_path):
    days = _history(tmp_path)
    legacy = (tmp_path/"settlements/2026-08-28.json").read_bytes()
    original_history = load_live_nav_history(tmp_path, asof=NOW, trading_dates=days)
    before = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 23000),
        trading_dates_provider=lambda _: days)
    assert before.status == "PAUSED"
    activate(tmp_path)
    stamp = NOW+timedelta(seconds=1)
    price = (23000-9998)/(2000*.9999)
    account = project(tmp_path, with_cash(_snapshot(shares=2000, sellable=2000,
        price=price, observed_at=stamp), 79998))
    assert account.settled_nav == pytest.approx(93000)
    after = evaluate_live_risk(tmp_path, now=stamp, account=account,
        trading_dates_provider=lambda _: days)
    assert after.status == "PAUSED" and after.pause_latched
    assert after.nav == pytest.approx(23000)
    assert after.high_water_mark == before.high_water_mark
    assert load_live_nav_history(tmp_path, asof=stamp, trading_dates=days) == original_history
    assert (tmp_path/"settlements/2026-08-28.json").read_bytes() == legacy


@pytest.mark.parametrize("fault", ["account", "flow", "future", "hash"])
def test_invalid_capital_evidence_blocks(tmp_path, fault):
    activate(tmp_path)
    snapshot = with_cash(_snapshot(), 80000)
    account = project(tmp_path, snapshot)
    if fault == "account":
        snapshot.pop("snapshot_sha256")
        snapshot["fund_account_binding_sha256"] = "b"*64
        snapshot["snapshot_sha256"] = digest(snapshot)
        with pytest.raises(ValueError, match="ACCOUNT_MISMATCH"):
            project(tmp_path, snapshot)
    elif fault == "flow":
        with pytest.raises(ValueError, match="FLOW_MISMATCH"):
            verify_account(tmp_path, {**account.as_dict(), "external_flow_total": 0})
    elif fault == "future":
        with pytest.raises(ValueError, match="FUTURE_FLOW"):
            verify_account(tmp_path, {**account.as_dict(),
                "broker_snapshot_observed_at": (NOW-timedelta(seconds=1)).isoformat()})
    else:
        path = tmp_path/"capital_flows.jsonl"
        row = json.loads(path.read_text()); row["amount"] = "1"
        path.write_text(json.dumps(row)+"\n")
        with pytest.raises(ValueError, match="CHAIN_INVALID"):
            flows(tmp_path)


def signed_grant(tmp_path, dynamic=True):
    env = {ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: "test-fixture-key"}
    grant = make_authorization(scope="APP test", max_notional=30000,
        signing_key=env[ENV_SIGNING_KEY], sides=["BUY", "SELL"],
        expires_at=(NOW+timedelta(days=1)).isoformat())
    if dynamic:
        grant.update(capital_policy_id=POLICY, fund_account_binding_sha256="a"*64)
        grant["signature"] = sign_payload(grant, env[ENV_SIGNING_KEY])
    path = tmp_path/"auth.json"; path.write_text(json.dumps(grant))
    return env, path


def proof(side="BUY", **overrides):
    body = {"source": "foundersc_native_app", "logical_account_id": "primary",
        "account_binding": "proven", "fund_account_binding_sha256": "a"*64,
        "plan_hash": "c"*64, "code": "000001.XSHE", "side": side,
        "action": "submit", "notional": 50000, "shares": 5000,
        "available_cash": 60000, "fee_rate": .0001,
        "book_b_owned_shares": 5000, "sellable_shares": 5000,
        "observed_at": NOW.isoformat(), **overrides}
    body["proof_sha256"] = digest(body)
    return body


def authorize(tmp_path, p, dynamic=True):
    env, path = signed_grant(tmp_path, dynamic)
    return authorize_capital_action(kind="real_capital", side=p["side"], code=p["code"],
        notional=p["notional"], auth_path=path, audit_path=tmp_path/"audit.jsonl", env=env,
        now=NOW, capital_proof=p, plan_hash="c"*64, action=p["action"])


def test_signed_dynamic_cash_allows_over_30k_and_old_grant_stays_bounded(tmp_path):
    assert authorize(tmp_path, proof()).allowed
    assert not authorize(tmp_path, proof(), dynamic=False).allowed


@pytest.mark.parametrize("changes", [
    {"available_cash": 50000}, {"available_cash": 1000},
    {"fund_account_binding_sha256": "b"*64}, {"plan_hash": "d"*64},
    {"observed_at": (NOW-timedelta(seconds=61)).isoformat()},
    {"observed_at": (NOW+timedelta(seconds=1)).isoformat()},
    {"fee_rate": -1}, {"notional": float("nan")},
])
def test_dynamic_gate_rejects_cash_fees_binding_and_staleness(tmp_path, changes):
    p = proof(**{k:v for k,v in changes.items() if k != "notional"})
    if "notional" in changes:
        p["notional"] = changes["notional"]
    assert not authorize(tmp_path, p).allowed


def test_sell_and_exact_cancel_do_not_require_buying_cash(tmp_path):
    assert authorize(tmp_path, proof("SELL", available_cash=0)).allowed
    assert not authorize(tmp_path, proof("SELL", book_b_owned_shares=4999)).allowed
    assert not authorize(tmp_path, proof("SELL", sellable_shares=4999)).allowed
    cancel = proof(action="cancel", available_cash=0,
        order_mapping_proven=True, broker_order_id="exact-order")
    assert authorize(tmp_path, cancel).allowed
    assert not authorize(tmp_path, proof(action="cancel", available_cash=0)).allowed


def test_proved_replacement_uses_only_remaining_quantity(tmp_path):
    assert authorize(tmp_path, proof(available_cash=10002, requested_notional=10000)).allowed
    assert not authorize(tmp_path, proof(available_cash=10000, requested_notional=10000)).allowed
    assert not authorize(tmp_path, proof(requested_notional=50001)).allowed


def test_settlement_rejects_projection_before_a_new_funding_head(tmp_path):
    from xiaocao.live.book_b_live_lifecycle import write_book_b_live_settlement
    activate(tmp_path)
    first = project(tmp_path, with_cash(_snapshot(), 80000))
    project(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 90000))
    with pytest.raises(ValueError, match="SETTLEMENT_CAPITAL_CHANGED"):
        write_book_b_live_settlement(tmp_path, first, now=NOW+timedelta(minutes=10))


def test_migration_preserves_existing_scopes_expiry_and_key(tmp_path):
    from scripts.migrate_book_b_available_capital import migrate
    env, auth = signed_grant(tmp_path, dynamic=False)
    snapshot = with_cash(_snapshot(), 80000)
    state = tmp_path/"output/live/book_b_live_execution"; state.mkdir(parents=True)
    original = auth.read_text()
    preview = migrate(tmp_path, snapshot=snapshot, env=env,
        approval="user-approved", apply=False, now=NOW, auth_path=auth)
    assert preview["status"] == "preview" and auth.read_text() == original
    applied = migrate(tmp_path, snapshot=snapshot, env=env,
        approval="user-approved", apply=True, now=NOW, auth_path=auth)
    assert applied["strategy_cash"] == applied["strategy_nav"] == 80000
    assert applied["expiry_preserved"] and applied["scope_preserved"]
    migrate(tmp_path, snapshot=snapshot, env=env,
        approval="user-approved", apply=True, now=NOW, auth_path=auth)
    assert len(flows(state)) == 1 and env[ENV_SIGNING_KEY] == "test-fixture-key"
