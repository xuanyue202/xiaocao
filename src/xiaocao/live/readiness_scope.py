"""Explain business scope without granting an order or changing a risk receipt."""
from __future__ import annotations


def account_readiness(account: dict | None, risk: dict | None) -> dict:
    account, risk = account or {}, risk or {}
    accounting = account.get('accounting') or {}
    lots = account.get('lots')
    reasons = risk.get('reasons') or []
    proof_gap = any(str(reason).startswith(('LIVE_RISK_ACCOUNTING_', 'LIVE_RISK_LATEST_SETTLEMENT_',
                    'SETTLED_HISTORY_STALE', 'LIVE_RISK_RECONCILED_CURRENT_NAV_')) for reason in reasons)
    return {'authority': 'explanation_only',
        'risk_cap': {'status': risk.get('status', 'unproved'),
                     'deploy_factor': risk.get('deploy_factor'),
                     'pause_latched': risk.get('pause_latched'),
                     'basis': 'current_proof_gap' if proof_gap else 'original_risk_receipt'},
        'new_buy_admission': 'requires_current_account_policy_quote_and_order_guards',
        'protective_exit': ('not_exercised_no_owned_lots' if lots == [] else
                            'independent_per_lot_sell_guards' if lots is not None else 'unproved'),
        'accounting': {'status': accounting.get('status', 'unproved'),
                       'fee_status': accounting.get('fee_status', 'unproved'),
                       'final_pnl_proven': accounting.get('cumulative_pnl') is not None
                           and accounting.get('cash_integrity_proven') is True
                           and accounting.get('actual_fees_complete') is True},
        'risk_receipt_unchanged': True}
