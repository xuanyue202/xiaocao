"""New-BUY buying power and owned-lot marks, separate from account settlement.

No inferred total assets, unrelated order lifecycle or broker write. Full order,
trade and mixed-account reconciliation remains mandatory after submission.
"""
from dataclasses import replace
from datetime import datetime
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.kol.publication import canonical_sha256
from .book_b_live_lifecycle import (
    BookBLiveAccountState, BookBLiveOwnedLot, load_latest_book_b_live_settlement,
    _read_jsonl_strict, _validate_execution_fill_coverage,
    _validate_ownership_chain,
)


def validate_buy_preflight(snapshot: dict, trade_date: str, now: datetime) -> dict:
    try:
        return _validate_buy_preflight(snapshot, trade_date, now)
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("BUY_PREFLIGHT_PROOF_INVALID") from exc


def _validate_buy_preflight(snapshot: dict, trade_date: str, now: datetime) -> dict:
    from .foundersc_native_broker import _decimal
    body = {k: v for k, v in snapshot.items() if k != 'snapshot_sha256'}
    observed = datetime.fromisoformat(snapshot['observed_at'])
    if (canonical_sha256(body) != snapshot.get('snapshot_sha256')
            or snapshot.get('schema_version') != 'book-b-buy-preflight.v1'
            or snapshot.get('account_binding') != 'proven'
            or snapshot.get('logical_account_id') != 'primary'
            or snapshot.get('trade_date') != trade_date
            or re.fullmatch(r'[0-9a-f]{64}', snapshot.get('fund_account_binding_sha256', '')) is None
            or snapshot.get('positions', {}).get('observed_at') != snapshot['observed_at']
            or snapshot.get('positions', {}).get('scope') != 'new_buy_preflight'
            or float(_decimal(snapshot['positions']['summary_values'].get('可用'), field='AVAILABLE_CASH')) != snapshot['available_cash']
            or observed.tzinfo is None or now.tzinfo is None
            or observed.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() != trade_date
            or not -30 <= (now - observed).total_seconds() <= 60
            or not math.isfinite(snapshot['available_cash']) or snapshot['available_cash'] < 0):
        raise ValueError('BUY_PREFLIGHT_PROOF_INVALID')
    return snapshot


def allocation_from_buy_preflight(snapshot: dict, basis, *, now: datetime) -> dict:
    validate_buy_preflight(snapshot, snapshot['trade_date'], now)
    binding = snapshot['fund_account_binding_sha256']
    receipt = {
        'status': 'allocation_reconciled', 'allocation_scope': 'buying_power',
        'trade_date': snapshot['trade_date'], 'environment': 'live',
        'logical_account_id': 'primary', 'account_binding': 'proven',
        'fund_account_binding_sha256': binding, 'observed_at': snapshot['observed_at'],
        'allocation_summary': {'complete': True, 'values': {'可用资金': snapshot['available_cash']}},
        'pretrade_snapshot': snapshot,
    }
    result = {
        'trade_date': snapshot['trade_date'], 'environment': 'live',
        'logical_account_id': 'primary', 'account_binding': 'proven',
        'fund_account_binding_sha256': binding, 'source': 'foundersc_native_app',
        'allocation_scope': 'buying_power', 'available_cash': snapshot['available_cash'],
        'settled_nav': basis.settled_nav, 'current_open_exposure': basis.current_open_exposure,
        'capital_basis_source': basis.source, 'capital_basis_receipt_sha256': basis.receipt_sha256,
        'broker_observed_at': snapshot['observed_at'],
        'broker_receipt': receipt, 'broker_receipt_sha256': canonical_sha256(receipt),
    }
    result['allocation_capsule_sha256'] = canonical_sha256(result)
    return result


def pretrade_account(state_dir: Path, snapshot: dict, *, trade_date: str, now: datetime) -> BookBLiveAccountState:
    """Mark settled Book-B lots only; cannot settle accounts or authorize exits."""
    validate_buy_preflight(snapshot, trade_date, now)
    # Every prior fill must still have durable ownership; this check touches
    # our own ledger only, not unrelated manual/test broker orders.
    events, head = _validate_ownership_chain(_read_jsonl_strict(state_dir / 'book_b_ownership_evidence.jsonl'))
    _validate_execution_fill_coverage(state_dir, events)
    from .book_b_live_morning import _uncertain_execution_plan_ids
    if _uncertain_execution_plan_ids(state_dir):
        raise ValueError('BUY_PREFLIGHT_OWNED_ORDER_RECONCILE_REQUIRED')
    settlement = load_latest_book_b_live_settlement(state_dir)
    if settlement is None:
        if events:
            raise ValueError('BUY_PREFLIGHT_SETTLEMENT_REQUIRED')
        cash, realized, old_lots = 30000.0, 0.0, []
    else:
        if settlement['ownership_head_sha256'] != head:
            raise ValueError('BUY_PREFLIGHT_OWNERSHIP_CHANGED')
        cash, realized, old_lots = settlement['cash'], settlement['realized_cash_delta'], settlement['lots']
    positions = {r['证券代码']: r for r in snapshot['positions']['rows']}
    lots = []
    totals = {}
    for row in old_lots:
        code = row['code'].split('.')[0]
        totals[code] = totals.get(code, 0) + row['shares']
    for code, shares in totals.items():
        if code not in positions or float(positions[code]['证券数量']) < shares:
            raise ValueError('BUY_PREFLIGHT_OWNED_POSITION_MISMATCH')
    remaining = {c: int(float(r['可卖数量'])) for c, r in positions.items()}
    for row in old_lots:
        lot = BookBLiveOwnedLot(**row)
        code = lot.code.split('.')[0]
        price = float(positions[code]['当前价'])
        if not math.isfinite(price) or price <= 0:
            raise ValueError('BUY_PREFLIGHT_OWNED_MARK_INVALID')
        sellable = min(lot.shares, remaining[code]) if lot.entry_date < trade_date else 0
        remaining[code] -= sellable
        lots.append(replace(lot, current_price=price, sellable_shares=sellable,
            market_value=round(price*lot.shares, 2),
            liquidation_value_after_fee=round(price*lot.shares*(1-lot.sell_fee_rate), 2)))
    exposure = round(sum(l.market_value for l in lots), 2)
    liquidation = round(sum(l.liquidation_value_after_fee for l in lots), 2)
    return BookBLiveAccountState(trade_date=trade_date, logical_account_id='primary', cash=cash,
        current_open_exposure=exposure, liquidation_value_after_fee=liquidation,
        settled_nav=round(cash+liquidation, 2), realized_cash_delta=realized,
        ownership_head_sha256=head, broker_snapshot_sha256=snapshot['snapshot_sha256'],
        broker_snapshot_observed_at=snapshot['observed_at'], lots=tuple(lots))
