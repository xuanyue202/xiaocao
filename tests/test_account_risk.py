from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from itertools import permutations

import pytest

from xiaocao.live.account_risk import (
    NAV_BASIS,
    AccountRiskReceipt,
    NavObservation,
    evaluate_account_risk,
)


ASOF = datetime.fromisoformat("2026-09-06T10:00:00+08:00")


def observation(nav=30_000, day="2026-09-04", **changes):
    return replace(NavObservation(
        date=day, nav=nav, account_id="live:B", initial_capital=30_000,
        external_flow_total=0, nav_basis=NAV_BASIS, status="settled",
        observed_at=f"{day}T15:10:00+08:00", evidence_digest="a" * 64,
    ), **changes)


def current(nav=30_000, **changes):
    return observation(nav, "2026-09-06", status="reconciled",
                       observed_at="2026-09-06T10:00:00+08:00", **changes)


def evaluate(history=None, **changes) -> AccountRiskReceipt:
    kwargs = dict(asof=ASOF, account_id="live:B", initial_capital=30_000,
                  expected_settlement_date="2026-09-04")
    kwargs.update(changes)
    return evaluate_account_risk([observation()] if history is None else history, **kwargs)


def assert_blocked(receipt, reason=None):
    assert receipt.status == "BLOCKED"
    assert receipt.deploy_factor == 0
    assert receipt.review_required
    assert receipt.nav is None
    assert receipt.drawdown_pct is None
    if reason:
        assert reason in receipt.reasons
    json.dumps(receipt.as_dict(), allow_nan=False)


@pytest.mark.parametrize("account_id", ["live:B", "paper:B"])
def test_normal_growth_on_explicit_independent_account(account_id):
    result = evaluate([observation(31_000, account_id=account_id)], account_id=account_id)
    assert (result.nav, result.high_water_mark, result.drawdown_pct) == (31_000, 31_000, 0)
    assert result.status == "NORMAL"
    assert result.deploy_factor == 1
    assert not result.review_required


@pytest.mark.parametrize("nav,status,factor", [
    (27_000.01, "NORMAL", 1), (27_000, "REDUCED", 0.5),
    (26_999.99, "REDUCED", 0.5), (24_000.01, "REDUCED", 0.5),
    (24_000, "PAUSED", 0), (23_999.99, "PAUSED", 0),
])
def test_inclusive_pilot_boundaries_without_float_rounding(nav, status, factor):
    result = evaluate(current_nav=current(nav))
    assert (result.status, result.deploy_factor) == (status, factor)
    assert result.high_water_mark == 30_000
    assert result.drawdown_pct == pytest.approx((30_000 - nav) / 30_000 * 100)
    assert result.review_required == (status == "PAUSED")


def test_threshold_uses_lifetime_peak_not_seed_or_first_input():
    history = [observation(36_000, "2026-09-03"), observation(32_400)]
    result = evaluate(history)
    assert result.high_water_mark == 36_000
    assert result.drawdown_pct == 10
    assert result.deploy_factor == 0.5


def test_later_growth_does_not_retroactively_pause_earlier_nav():
    history = [observation(30_000, "2026-09-03"), observation(40_000)]
    first = evaluate(history)
    again = evaluate(history, previous_receipt=first)
    assert again.status == "NORMAL"
    assert not again.pause_latched


def test_historical_pause_survives_rebound_to_a_new_high():
    history = [observation(24_000, "2026-09-03"), observation(40_000)]
    result = evaluate(history)
    assert result.drawdown_pct == 0
    assert result.high_water_mark == 40_000
    assert result.status == "PAUSED"
    assert result.pause_latched and result.review_required


def test_intraday_pause_survives_invalid_readback_and_rebound():
    paused = evaluate(current_nav=current(24_000))
    blocked = evaluate(current_nav=current(float("nan")), previous_receipt=paused)
    assert_blocked(blocked)
    assert blocked.pause_latched
    recovered = evaluate(current_nav=current(33_000), previous_receipt=blocked)
    assert recovered.status == "PAUSED"
    assert recovered.high_water_mark == 33_000
    assert recovered.drawdown_pct == 0


def test_previous_intraday_high_is_not_reset_to_settled_high():
    high = evaluate(current_nav=current(40_000))
    result = evaluate(current_nav=current(36_000), previous_receipt=high)
    assert result.high_water_mark == 40_000
    assert result.deploy_factor == 0.5


def test_older_settlement_cannot_undo_more_recent_intraday_mark():
    reduced = evaluate(current_nav=current(27_000))
    blocked = evaluate(previous_receipt=reduced)
    assert_blocked(blocked, "NAV_OBSERVATION_REGRESSION")
    assert blocked.nav_observed_at == reduced.nav_observed_at
    assert_blocked(evaluate(previous_receipt=blocked), "NAV_OBSERVATION_REGRESSION")


def test_prior_intraday_peak_binds_later_settlement_even_after_rebound():
    high = evaluate(
        [observation(day="2026-09-02")],
        asof=datetime.fromisoformat("2026-09-03T10:00:00+08:00"),
        expected_settlement_date="2026-09-02",
        current_nav=observation(40_000, "2026-09-03", status="reconciled",
                                observed_at="2026-09-03T10:00:00+08:00"),
    )
    result = evaluate(
        [observation(day="2026-09-02"), observation(32_000, "2026-09-03"), observation(50_000)],
        previous_receipt=high,
    )
    assert result.status == "PAUSED"
    assert result.high_water_mark == 50_000
    assert result.drawdown_pct == 0


def test_bad_readback_does_not_erase_prior_intraday_high():
    high = evaluate(current_nav=current(40_000))
    blocked = evaluate(current_nav=current(float("nan")), previous_receipt=high)
    result = evaluate(current_nav=current(36_000), previous_receipt=blocked)
    assert result.high_water_mark == 40_000
    assert result.deploy_factor == 0.5


def test_hash_and_receipt_are_order_independent_including_conflicts():
    history = [observation(30_000, "2026-09-02"), observation(34_000, "2026-09-03"),
               observation(32_000)]
    for rows in (history, history + [observation(31_000)]):
        receipts = [evaluate(order) for order in permutations(rows)]
        assert all(receipt == receipts[0] for receipt in receipts)
    assert_blocked(evaluate(history + [observation(31_000)]), "DUPLICATE_DATE_CONFLICT")


def test_exact_duplicate_is_idempotent_but_source_hash_is_bound():
    original = evaluate()
    assert evaluate([observation(), observation()]) == original
    changed = evaluate([observation(evidence_digest="b" * 64)])
    assert changed.evidence_digest != original.evidence_digest
    assert changed.deploy_factor == original.deploy_factor


def test_same_day_current_and_settlement_conflict_blocks():
    assert_blocked(evaluate(
        [observation()], asof=datetime.fromisoformat("2026-09-04T15:12:00+08:00"),
        current_nav=observation(31_000, status="reconciled"),
    ), "DUPLICATE_DATE_CONFLICT")


@pytest.mark.parametrize("nav", [float("nan"), float("inf"), -float("inf"), 0, -1, True, "30000", None])
@pytest.mark.parametrize("where", ["history", "current"])
def test_invalid_nav_fails_closed_and_remains_json_safe(nav, where):
    result = evaluate([observation(nav)]) if where == "history" else evaluate(current_nav=current(nav))
    assert_blocked(result)


@pytest.mark.parametrize("capital", [float("nan"), float("inf"), 0, -1, True, "30000", None])
def test_invalid_initial_capital_fails_closed(capital):
    assert_blocked(evaluate(initial_capital=capital), "INITIAL_CAPITAL_INVALID")


@pytest.mark.parametrize("account_id", ["paper:B", "live:T", "B", "live:primary", "", None])
def test_paper_or_wrong_identity_cannot_protect_live(account_id):
    assert_blocked(evaluate([observation(account_id=account_id)]), "ACCOUNT_ID_MISMATCH")
    assert_blocked(evaluate(current_nav=current(account_id=account_id)), "ACCOUNT_ID_MISMATCH")


@pytest.mark.parametrize("account_id", ["B", "paper:A", "live:T", "broker:total", None])
def test_invalid_requested_identity_blocks(account_id):
    assert_blocked(evaluate(account_id=account_id), "ACCOUNT_ID_INVALID")


@pytest.mark.parametrize("basis", ["broker_total_assets", "gross_market_equity", "", None])
def test_mixed_assets_and_valuation_basis_mismatch_block(basis):
    assert_blocked(evaluate([observation(nav_basis=basis)]), "NAV_BASIS_MISMATCH")
    assert_blocked(evaluate(current_nav=current(nav_basis=basis)), "NAV_BASIS_MISMATCH")


@pytest.mark.parametrize("flows", [10_000, -1, float("nan"), None, True])
def test_added_capital_or_unknown_flows_never_masquerade_as_profit(flows):
    assert_blocked(evaluate(current_nav=current(40_000, external_flow_total=flows)))
    assert_blocked(evaluate([observation(40_000, external_flow_total=flows)]))


def test_offsetting_deposit_and_withdrawal_still_requires_review():
    assert_blocked(evaluate(current_nav=current(external_flow_total=20_000)),
                   "EXTERNAL_FLOW_REVIEW_REQUIRED")


def test_no_automatic_principal_change_or_hwm_reset():
    assert_blocked(evaluate([observation(initial_capital=40_000)]), "INITIAL_CAPITAL_MISMATCH")
    prior = evaluate()
    assert_blocked(evaluate([observation(initial_capital=40_000)], initial_capital=40_000,
                           previous_receipt=prior), "PREVIOUS_RECEIPT_INVALID")


def test_initial_capital_is_required_and_never_inferred_from_other_assets():
    with pytest.raises(TypeError, match="initial_capital"):
        evaluate_account_risk([observation()], asof=ASOF, account_id="live:B",
                              expected_settlement_date="2026-09-04")
    assert_blocked(evaluate(initial_capital=130_000), "INITIAL_CAPITAL_MISMATCH")


def test_current_mark_cannot_substitute_for_missing_or_stale_settlement():
    assert_blocked(evaluate([], current_nav=current()), "SETTLED_HISTORY_REQUIRED")
    assert_blocked(evaluate([observation(day="2026-09-03")], current_nav=current()),
                   "SETTLED_HISTORY_STALE_OR_UNEXPECTED")


def test_weekend_and_holiday_freshness_uses_explicit_calendar_requirement():
    assert evaluate().status == "NORMAL"
    assert evaluate([observation(day="2026-09-01")],
                    expected_settlement_date="2026-09-01").status == "NORMAL"


@pytest.mark.parametrize("age,status", [(0, "NORMAL"), (300, "NORMAL"), (301, "BLOCKED"), (-1, "BLOCKED")])
def test_current_mark_freshness_boundary(age, status):
    mark = replace(current(), observed_at=(ASOF - timedelta(seconds=age)).isoformat())
    assert evaluate(current_nav=mark).status == status


@pytest.mark.parametrize("changes,reason", [
    ({"date": "2026-09-07", "observed_at": "2026-09-07T15:10:00+08:00"}, "FUTURE_EVIDENCE"),
    ({"date": "20260904"}, "OBSERVATION_INVALID"),
    ({"observed_at": "2026-09-04T15:10:00"}, "OBSERVATION_INVALID"),
    ({"observed_at": "2026-09-03T15:10:00+08:00"}, "OBSERVATION_DATE_MISMATCH"),
    ({"observed_at": "2026-09-04T14:59:59+08:00"}, "HISTORY_NOT_SETTLED"),
    ({"status": "reconciled"}, "HISTORY_NOT_SETTLED"),
    ({"evidence_digest": "not-a-sha256"}, "SOURCE_DIGEST_INVALID"),
])
def test_invalid_historical_time_settlement_or_provenance(changes, reason):
    assert_blocked(evaluate([observation(**changes)]), reason)


def test_current_must_be_reconciled_same_day_even_with_recent_timestamp():
    assert_blocked(evaluate(current_nav=replace(current(), status="settled")),
                   "CURRENT_NAV_NOT_RECONCILED")
    just_after_midnight = datetime.fromisoformat("2026-09-06T00:01:00+08:00")
    prior_day = replace(current(), date="2026-09-05", observed_at="2026-09-05T23:59:00+08:00")
    assert_blocked(evaluate(asof=just_after_midnight, current_nav=prior_day), "CURRENT_NAV_STALE")


@pytest.mark.parametrize("asof", [ASOF.replace(tzinfo=None), "2026-09-06", None])
def test_asof_requires_explicit_timezone(asof):
    assert_blocked(evaluate(asof=asof), "ASOF_INVALID")


@pytest.mark.parametrize("day", ["2026-09-07", "20260904", "not-a-date", None])
def test_invalid_required_settlement_date(day):
    assert_blocked(evaluate(expected_settlement_date=day), "EXPECTED_SETTLEMENT_DATE_INVALID")


@pytest.mark.parametrize("change", [
    {"account_id": "paper:B"}, {"initial_capital": 40_000}, {"high_water_mark": float("nan")},
    {"asof": "2026-09-07T10:00:00+08:00"}, {"policy_id": "other"}, {"deploy_factor": 2},
    {"nav": float("inf")}, {"drawdown_pct": float("nan")}, {"nav": -1},
    {"high_water_mark": None}, {"nav_observed_at": None}, {"evidence_digest": ""},
])
def test_prior_receipt_cannot_cross_identity_time_or_basis(change):
    assert_blocked(evaluate(previous_receipt=replace(evaluate(), **change)), "PREVIOUS_RECEIPT_INVALID")


def test_invalid_prior_chain_cannot_be_laundered_through_a_blocked_receipt():
    corrupt = replace(evaluate(current_nav=current(40_000)), high_water_mark=float("nan"))
    blocked = evaluate(previous_receipt=corrupt)
    assert_blocked(blocked, "PREVIOUS_RECEIPT_INVALID")
    assert_blocked(evaluate(current_nav=current(36_000), previous_receipt=blocked),
                   "PREVIOUS_RECEIPT_INVALID")


def test_receipt_is_immutable_serializable_and_does_not_mutate_inputs():
    history = [observation()]
    before = list(history)
    receipt = evaluate(history)
    with pytest.raises(FrozenInstanceError):
        receipt.deploy_factor = 2
    with pytest.raises(FrozenInstanceError):
        history[0].nav = 1
    payload = receipt.as_dict()
    payload["reasons"].append("mutated")
    assert history == before
    assert "mutated" not in receipt.reasons
    assert len(receipt.evidence_digest) == 64
    assert json.loads(json.dumps(receipt.as_dict(), allow_nan=False)) == receipt.as_dict()


def epoch(nav=30_000, **changes):
    kwargs = dict(account_id="paper:B", require_settled_history=False,
                  expected_settlement_date=None, current_nav=current(nav, account_id="paper:B"))
    kwargs.update(changes)
    return evaluate([], **kwargs)


@pytest.mark.parametrize("nav,peak,status,factor", [
    (31_000, 31_000, "NORMAL", 1), (30_000, 30_000, "NORMAL", 1),
    (27_000, 30_000, "REDUCED", 0.5), (24_000, 30_000, "PAUSED", 0),
])
def test_paper_epoch_starts_from_real_current_mark_without_fabricated_history(nav, peak, status, factor):
    result = epoch(nav)
    assert (result.nav, result.high_water_mark, result.status, result.deploy_factor) == (nav, peak, status, factor)
    assert result.initial_capital == 30_000
    assert result.history_basis == "since_activation"
    assert result.tracking_epoch_started_at == result.asof
    assert result.expected_settlement_date == ""
    json.dumps(result.as_dict(), allow_nan=False)


def test_paper_epoch_does_not_reset_peak_or_activation_time_on_next_day():
    first = epoch(40_000)
    next_time = ASOF + timedelta(days=1)
    mark = replace(current(36_000, account_id="paper:B"), date="2026-09-07",
                   observed_at=next_time.isoformat())
    result = epoch(previous_receipt=first, asof=next_time, current_nav=mark)
    assert (result.high_water_mark, result.drawdown_pct, result.deploy_factor) == (40_000, 10, 0.5)
    assert result.tracking_epoch_started_at == first.tracking_epoch_started_at


def test_paper_epoch_pause_survives_bad_readback_and_rebound():
    paused = epoch(24_000)
    blocked = epoch(float("nan"), previous_receipt=paused)
    assert_blocked(blocked)
    assert blocked.pause_latched
    assert blocked.tracking_epoch_started_at == paused.tracking_epoch_started_at
    recovered = epoch(33_000, previous_receipt=blocked)
    assert (recovered.status, recovered.deploy_factor, recovered.drawdown_pct) == ("PAUSED", 0, 0)
    assert recovered.review_required
    assert recovered.tracking_epoch_started_at == paused.tracking_epoch_started_at


def test_failed_first_paper_mark_does_not_claim_an_activation():
    blocked = epoch(float("nan"))
    assert_blocked(blocked)
    assert blocked.tracking_epoch_started_at is None
    valid = epoch(previous_receipt=blocked)
    assert valid.tracking_epoch_started_at == valid.asof


@pytest.mark.parametrize("mode", [True, False])
def test_live_cannot_bootstrap_without_settled_history(mode):
    assert_blocked(evaluate([], require_settled_history=mode, current_nav=current()),
                   "SETTLED_HISTORY_REQUIRED" if mode else "TRACKING_EPOCH_PAPER_ONLY")


def test_paper_default_remains_strict_and_requires_expected_settlement_date():
    assert_blocked(evaluate([], account_id="paper:B", current_nav=current(account_id="paper:B")),
                   "SETTLED_HISTORY_REQUIRED")
    assert_blocked(evaluate(expected_settlement_date=None), "EXPECTED_SETTLEMENT_DATE_INVALID")
    assert evaluate().history_basis == "settled_history"
    assert evaluate().tracking_epoch_started_at is None


@pytest.mark.parametrize("mark,reason", [
    (None, "TRACKING_EPOCH_CURRENT_NAV_REQUIRED"),
    (current(), "ACCOUNT_ID_MISMATCH"),
    (replace(current(account_id="paper:B"), status="settled"), "CURRENT_NAV_NOT_RECONCILED"),
    (replace(current(account_id="paper:B"), observed_at=(ASOF - timedelta(seconds=301)).isoformat()), "CURRENT_NAV_STALE"),
    (replace(current(account_id="paper:B"), observed_at=(ASOF + timedelta(seconds=1)).isoformat()), "FUTURE_EVIDENCE"),
    (current(account_id="paper:B", external_flow_total=1_000), "EXTERNAL_FLOW_REVIEW_REQUIRED"),
    (current(account_id="paper:B", initial_capital=40_000), "INITIAL_CAPITAL_MISMATCH"),
])
def test_paper_epoch_does_not_relax_current_evidence_validation(mark, reason):
    assert_blocked(epoch(current_nav=mark), reason)


@pytest.mark.parametrize("mode", [None, 0, 1, "false"])
def test_epoch_opt_out_requires_explicit_boolean(mode):
    assert_blocked(epoch(require_settled_history=mode), "HISTORY_REQUIREMENT_INVALID")


def test_history_mode_and_epoch_identity_are_digest_bound():
    rows = [observation(account_id="paper:B")]
    mark = current(account_id="paper:B")
    strict = evaluate(rows, account_id="paper:B", current_nav=mark)
    tracking = evaluate(rows, account_id="paper:B", current_nav=mark, require_settled_history=False)
    assert strict.deploy_factor == tracking.deploy_factor
    assert strict.evidence_digest != tracking.evidence_digest
    corrupt = replace(epoch(), tracking_epoch_started_at=(ASOF + timedelta(days=1)).isoformat())
    assert_blocked(epoch(previous_receipt=corrupt), "PREVIOUS_RECEIPT_INVALID")


def test_previous_receipt_must_use_the_same_tracking_mode_in_both_directions():
    history = [observation(account_id="paper:B")]
    strict = evaluate(history, account_id="paper:B", current_nav=current(40_000, account_id="paper:B"))
    assert_blocked(epoch(previous_receipt=strict), "PREVIOUS_RECEIPT_INVALID")
    tracking = epoch(24_000)
    assert_blocked(evaluate(history, account_id="paper:B", current_nav=current(account_id="paper:B"),
                           previous_receipt=tracking), "PREVIOUS_RECEIPT_INVALID")


def test_legacy_strict_receipt_without_epoch_fields_remains_compatible():
    payload = evaluate().as_dict()
    payload.pop("history_basis")
    payload.pop("tracking_epoch_started_at")
    payload["reasons"] = tuple(payload["reasons"])
    restored = AccountRiskReceipt(**payload)
    assert restored.history_basis == "settled_history"
    assert evaluate(previous_receipt=restored).status == "NORMAL"
