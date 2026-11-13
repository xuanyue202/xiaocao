"""Explanation never relaxes original economic admission or final accounting proof."""
import copy
from xiaocao.live.readiness_scope import account_readiness


def test_proof_gap_retains_risk_and_independent_exit_scope():
    risk = {'status':'BLOCKED', 'deploy_factor':0, 'pause_latched':False,
            'reasons':['LIVE_RISK_ACCOUNTING_CASH_RESERVE_RECONCILIATION_REQUIRED']}
    original = copy.deepcopy(risk)
    result = account_readiness({'lots':[], 'accounting':{'cumulative_pnl':1,
            'cash_integrity_proven':True, 'actual_fees_complete':False}}, risk)
    assert result['risk_cap']['status']=='BLOCKED'
    assert result['risk_cap']['basis']=='current_proof_gap'
    assert result['protective_exit']=='not_exercised_no_owned_lots'
    assert result['accounting']['final_pnl_proven'] is False
    assert risk == original
