"""New-BUY buying power and owned-lot marks, separate from account settlement.

No inferred total assets, unrelated order lifecycle or broker write. Full order,
trade and mixed-account reconciliation remains mandatory after submission.
"""
from datetime import datetime
import hashlib
import json
import math
import re
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .book_b_live_lifecycle import (
    BOOK_B_LIVE_INITIAL_CAPITAL,
    BookBLiveAccountState, BookBLiveOwnedLot, load_latest_book_b_live_settlement,
    _broker_decimal, _broker_integer, _normalize_code,
)


def _capsule_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def validate_buy_preflight(snapshot: dict, trade_date: str, now: datetime) -> dict:
    try:
        return _validate_buy_preflight(snapshot, trade_date, now)
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("BUY_PREFLIGHT_PROOF_INVALID") from exc


def _validate_buy_preflight(snapshot: dict, trade_date: str, now: datetime) -> dict:
    from .foundersc_native_broker import _decimal
    body = {k: v for k, v in snapshot.items() if k != 'snapshot_sha256'}
    snapshot_sha256 = _capsule_sha256(body)
    observed = datetime.fromisoformat(snapshot['observed_at'])
    if (snapshot_sha256 != snapshot.get('snapshot_sha256')
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
        'broker_receipt': receipt, 'broker_receipt_sha256': _capsule_sha256(receipt),
    }
    from .book_b_capital import SOURCE
    if basis.source == SOURCE:
        # Carry the exact funding head; verification/recovery never revalues
        # this immutable allocation using a later capital movement.
        result['capital_flow_head_sha256'] = basis.capital_flow_head_sha256
        if basis.accounting_report is not None:
            result['accounting'] = basis.accounting_report
    result['allocation_capsule_sha256'] = _capsule_sha256(result)
    return result


def _replay_owned_book(state_dir: Path) -> tuple[Decimal, dict[str, dict], str | None]:
    """Replay proved Book-B fills without requiring a terminal old order."""
    from .book_b_accounting import replay_owned
    book = replay_owned(state_dir)
    cash, lots, head = book.cash.quantize(Decimal('0.01')), book.lots, book.head
    from .book_b_capital import policy
    if cash < Decimal('-0.10') and policy(state_dir) is None:
        raise ValueError('BUY_PREFLIGHT_SUBACCOUNT_CASH_NEGATIVE')
    return cash, lots, head


def current_owned_book_b_codes(state_dir: Path) -> set[str]:
    """Codes whose proven Book-B shares must be present in scoped APP reads."""
    _, lots, _ = _replay_owned_book(Path(state_dir))
    return {str(lot['code']) for lot in lots.values() if lot['shares'] > 0}


def pretrade_account(state_dir: Path, snapshot: dict, *, trade_date: str, now: datetime,
                     sync_capital: bool = True, historical_capital: bool = False,
                     capital_flow_head: str | None = None,
                     capital_policy_id: str | None = None) -> BookBLiveAccountState:
    """Mark current proved Book-B lots; preserve old orders for reconciliation."""
    validate_buy_preflight(snapshot, trade_date, now)
    state_dir = Path(state_dir)
    cash, owned, head = _replay_owned_book(state_dir)
    from .book_b_live_morning import _uncertain_execution_plan_ids
    if _uncertain_execution_plan_ids(state_dir, trade_date=trade_date, asof=now):
        raise ValueError('BUY_PREFLIGHT_OWNED_ORDER_RECONCILE_REQUIRED')
    settlement = load_latest_book_b_live_settlement(state_dir)
    if settlement is None and owned:
        raise ValueError('BUY_PREFLIGHT_SETTLEMENT_REQUIRED')
    contexts = {str(lot['owned_lot_id']): dict(lot.get('monitor_context') or {})
                for lot in (settlement or {}).get('lots', [])}
    positions = {}
    for row in snapshot['positions']['rows']:
        code = _normalize_code(row.get('证券代码'))
        if code in positions:
            raise ValueError('BUY_PREFLIGHT_OWNED_POSITION_DUPLICATE')
        positions[code] = row
    lots = []
    totals = {}
    for row in owned.values():
        if row['shares'] <= 0:
            continue
        code = _normalize_code(row['code'])
        totals[code] = totals.get(code, 0) + row['shares']
    for code, shares in totals.items():
        if code not in positions or _broker_integer(positions[code]['证券数量'],
                reason='BUY_PREFLIGHT_OWNED_POSITION_INVALID') < shares:
            raise ValueError('BUY_PREFLIGHT_OWNED_POSITION_MISMATCH')
    remaining = {c: _broker_integer(r['可卖数量'],
        reason='BUY_PREFLIGHT_OWNED_SELLABLE_INVALID') for c, r in positions.items()}
    for lot_id, row in sorted(owned.items(), key=lambda item: (item[1]['entry_date'], item[0])):
        if row['shares'] <= 0:
            continue
        code = _normalize_code(row['code'])
        price = float(_broker_decimal(positions[code]['当前价'],
            reason='BUY_PREFLIGHT_OWNED_MARK_INVALID'))
        if not math.isfinite(price) or price <= 0:
            raise ValueError('BUY_PREFLIGHT_OWNED_MARK_INVALID')
        sellable = min(row['shares'], remaining[code]) if row['entry_date'] < trade_date else 0
        remaining[code] -= sellable
        lots.append(BookBLiveOwnedLot(
            owned_lot_id=lot_id, code=row['code'], name=row['name'],
            entry_date=row['entry_date'], entry_price=round(float(row['cost'] / row['shares']), 6),
            shares=row['shares'], sellable_shares=sellable, current_price=price,
            market_value=round(price * row['shares'], 2),
            liquidation_value_after_fee=round(price * row['shares'] * (1-float(row['fee_rate'])), 2),
            buy_fee_rate=float(row['fee_rate']), sell_fee_rate=float(row['fee_rate']),
            snapshot_ref=row['snapshot_ref'], monitor_context=contexts.get(lot_id, {})))
    exposure = round(sum(l.market_value for l in lots), 2)
    liquidation = round(sum(l.liquidation_value_after_fee for l in lots), 2)
    from .book_b_capital import allocate_cash
    cash, funding = allocate_cash(state_dir, base_cash=cash, liquidation=liquidation,
        ownership_head=head, snapshot=snapshot, sync=sync_capital,
        replay_flow_head=capital_flow_head, historical=historical_capital)
    if capital_policy_id is not None:
        from .book_b_capital import POLICY, policy
        if capital_policy_id != POLICY or policy(state_dir) is None:
            raise ValueError('BUY_PREFLIGHT_CAPITAL_POLICY_UNPROVEN')
        funding['capital_policy_id'] = POLICY
    if cash < Decimal('-0.10'):
        raise ValueError('BUY_PREFLIGHT_SUBACCOUNT_CASH_NEGATIVE')
    from .book_b_accounting import observe_account
    accounting = (observe_account(state_dir, cash=cash, market_value=exposure,
        liquidation_value=liquidation, snapshot=snapshot, capital_state=funding)
        if sync_capital else None)
    return BookBLiveAccountState(trade_date=trade_date, logical_account_id='primary', cash=float(cash),
        current_open_exposure=exposure, liquidation_value_after_fee=liquidation,
        settled_nav=round(float(cash)+liquidation, 2),
        realized_cash_delta=round(float(cash)-funding['net_external_flow_total']-BOOK_B_LIVE_INITIAL_CAPITAL, 2),
        ownership_head_sha256=head, broker_snapshot_sha256=snapshot['snapshot_sha256'],
        broker_snapshot_observed_at=snapshot['observed_at'], lots=tuple(lots), accounting=accounting, **funding)
