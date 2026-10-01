"""Pure monetary policy: integer cents, no APP fixtures, evidence IO or actions."""
import pytest

from xiaocao.live import book_b_accounting as accounting


@pytest.mark.parametrize("delta,status", [
    (0, "reconciled"), (1, "cash_discrepancy_tolerated"),
    (-1, "cash_discrepancy_tolerated"), (999, "cash_discrepancy_tolerated"),
    (-999, "cash_discrepancy_tolerated"), (1000, "cash_reconciliation_required"),
    (-1000, "cash_reconciliation_required"), (1001, "cash_reconciliation_required"),
])
def test_total_difference_boundary_and_conservative_cash(delta, status):
    result = accounting.cash_observation_policy(3000000 + delta, 3000000,
        evidence_complete=True)
    assert result == {"status": status, "difference_cents": delta,
                      "deployable_cash_cents": 3000000 + min(delta, 0)}


@pytest.mark.parametrize("delta", [-999, 1, 999])
def test_missing_integrity_proof_cannot_enable_tolerance(delta):
    result = accounting.cash_observation_policy(3000000 + delta, 3000000)
    assert result["status"] == "cash_reconciliation_required"
    assert result["difference_cents"] == delta


def test_pending_reserve_is_not_a_cash_or_profit_discrepancy():
    result = accounting.cash_observation_policy(2999999, 3000000,
        evidence_complete=True, reserve_pending=True)
    assert result["status"] == "cash_reserve_reconciliation_required"
    assert result["difference_cents"] is None


def test_repeated_small_observations_never_reset_the_replay_baseline():
    ledger = 3000000
    assert accounting.cash_observation_policy(ledger + 600, ledger,
        evidence_complete=True)["status"] == "cash_discrepancy_tolerated"
    assert accounting.cash_observation_policy(ledger + 1200, ledger,
        evidence_complete=True)["status"] == "cash_reconciliation_required"


@pytest.mark.parametrize("observed,ledger", [(1.5, 0), (True, 0), (0, "0")])
def test_only_integer_cent_values_are_accepted(observed, ledger):
    with pytest.raises(ValueError, match="CASH_CENTS_INVALID"):
        accounting.cash_observation_policy(observed, ledger, evidence_complete=True)
