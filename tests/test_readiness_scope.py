"""Explanation never relaxes original economic admission or final accounting proof."""
import copy
import pytest

pytestmark = pytest.mark.app_simulation
from xiaocao.live.readiness_scope import account_readiness


def test_proof_gap_retains_risk_and_independent_exit_scope():
    risk = {'status':'BLOCKED', 'deploy_factor':0, 'pause_latched':False,
            'reasons':['LIVE_RISK_ACCOUNTING_CASH_RESERVE_RECONCILIATION_REQUIRED']}
    original = copy.deepcopy(risk)
    result = account_readiness({'lots':[], 'accounting':{'cumulative_pnl':1,
            'cash_integrity_proven':True, 'fee_status':'actual_fees_pending'}}, risk)
    assert result['risk_cap']['status']=='BLOCKED'
    assert result['risk_cap']['basis']=='current_proof_gap'
    assert result['protective_exit']=='not_exercised_no_owned_lots'
    assert result['accounting']['final_pnl_proven'] is False
    assert risk == original


@pytest.mark.parametrize('status, fees, expected', [
    ('reconciled','actual_fees_complete',True),
    ('reconciled','actual_fees_pending',False),
    ('cash_reserve_reconciliation_required','actual_fees_complete',False),
])
def test_final_pnl_requires_canonical_reconciled_fee_and_cash_proof(status, fees, expected):
    account = {'accounting':{'status':status, 'fee_status':fees,
                            'cumulative_pnl':1.0, 'cash_integrity_proven':True}}
    assert account_readiness(account,{})['accounting']['final_pnl_proven'] is expected
