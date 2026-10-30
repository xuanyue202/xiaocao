"""Bound inherited BUY effects without changing their order or accounting state.

Only a fresh account-bound observation and immutable intent/event prefixes may
admit independent new risk. Historical UNKNOWN remains reconcile-only. Cash
holds reduce spending capacity, never create a loss, NAV asset or funding flow.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from pathlib import Path

from .book_b_capital import digest, number, policy
from .book_b_live_lifecycle import load_execution_intents, read_execution_plan, open_execution_plan_ids
from .trading_execution import ExecutionReceipt, ExecutionState, ExecutionStore, TERMINAL_STATES
from xiaocao.utils.atomic_files import atomic_write

_EFFECT_STATES = {ExecutionState.CLAIMED, ExecutionState.UNKNOWN, ExecutionState.SUBMITTED,
                  ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL, ExecutionState.RECONCILING}
_CENT = Decimal('.01')


def prior_day_buy_ids(root: Path, *, trade_date: str) -> tuple[str, ...]:
    intents = load_execution_intents(Path(root))
    ids = open_execution_plan_ids(Path(root))
    if any(plan_id not in intents for plan_id in ids):
        raise ValueError('LIVE_INHERITED_BUY_INTENT_MISSING')
    store = ExecutionStore(Path(root) / 'events.jsonl')
    return tuple(p for p in ids if intents[p].get('side') == 'BUY'
                 and str(intents[p].get('trade_date') or '') < trade_date
                 and (receipt := store.current(p)) is not None and receipt.state in _EFFECT_STATES)


def query_codes(root: Path, *, trade_date: str) -> set[str]:
    """Potential owned shares need current marks, without adopting manual lots."""
    intents = load_execution_intents(Path(root))
    return {str(intents[p]['code']) for p in prior_day_buy_ids(root, trade_date=trade_date)}


def _calculate(root: Path, snapshot: dict, *, event_heads: dict | None = None, ownership_head: str | None = None) -> dict:
    from .book_b_accounting import replay_owned
    from .book_b_live_morning import _event_chain_proven, _uncertain_execution_plan_ids
    from .buy_preflight import validate_buy_preflight
    from .book_b_live_lifecycle import _broker_decimal, _broker_integer, _normalize_code
    from .foundersc_native_broker import _decimal, _integer, _side

    observed = datetime.fromisoformat(snapshot['observed_at'])
    validate_buy_preflight(snapshot, snapshot['trade_date'], observed)
    if event_heads is None and _uncertain_execution_plan_ids(root, trade_date=snapshot['trade_date'],
            asof=observed, defer_prior_day_sells=True, defer_prior_day_buys=True):
        raise ValueError('LIVE_INHERITED_BUY_CURRENT_EXECUTION_UNPROVEN')
    cfg = policy(root)
    if cfg is None or cfg['fund_account_binding_sha256'] != snapshot['fund_account_binding_sha256']:
        raise ValueError('LIVE_INHERITED_BUY_CAPITAL_BINDING_UNPROVEN')
    intents, store, book = load_execution_intents(root), ExecutionStore(root / 'events.jsonl'), replay_owned(root)
    rows_prefix = book.rows
    source_head = book.head
    if event_heads is not None:
        if ownership_head not in book.cash_by_head:
            raise ValueError('LIVE_INHERITED_BUY_OWNERSHIP_PREFIX_UNPROVEN')
        rows_prefix = []
        for row in book.rows if ownership_head is not None else []:
            rows_prefix.append(row)
            if row['event_hash'] == ownership_head:
                break
        source_head = ownership_head
    ids = tuple(event_heads) if event_heads is not None else prior_day_buy_ids(root, trade_date=snapshot['trade_date'])
    positions = snapshot['positions']
    required = {str(intents[p]['code']).split('.')[0] for p in ids}
    if not required <= set(positions.get('scoped_codes', [])):
        raise ValueError('LIVE_INHERITED_BUY_POSITION_SCOPE_UNPROVEN')
    rows = {}
    for row in positions['rows']:
        code = _normalize_code(row.get('证券代码'))
        if code in rows:
            raise ValueError('LIVE_INHERITED_BUY_POSITION_DUPLICATE')
        rows[code] = row
    cash = number(snapshot['available_cash'])
    # The same capture's gross cash includes freezes. Use it only as a lower
    # bound on the cash pool; min(available, gross - commitments) avoids charging
    # an already reflected hold twice. If absent, available is a safe lower bound.
    raw_balance = positions['summary_values'].get('余额')
    gross = cash
    try:
        candidate = _broker_decimal(raw_balance, reason='LIVE_INHERITED_BUY_CASH_BALANCE_UNPROVEN')
        if candidate >= cash:
            gross = candidate
    except (ValueError, InvalidOperation):
        pass  # Optional audit balance must not defeat a proved cash lower bound.
    commitments, exposure, entries = Decimal(0), Decimal(0), []
    for plan_id in ids:
        raw = intents[plan_id]
        plan = read_execution_plan(raw)
        if plan.side != 'BUY' or plan.trade_date >= snapshot['trade_date']:
            raise ValueError('LIVE_INHERITED_BUY_NOT_PRIOR_DAY')
        events = store.events(plan_id)
        if event_heads is not None:
            ref = event_heads[plan_id]
            events = events[:ref['sequence']]
            if not events or events[-1]['event_hash'] != ref['event_hash']:
                raise ValueError('LIVE_INHERITED_BUY_EVENT_PREFIX_UNPROVEN')
        if not events or not _event_chain_proven(plan_id, events):
            raise ValueError('LIVE_INHERITED_BUY_EVENT_CHAIN_UNPROVEN')
        receipt = ExecutionReceipt.from_dict(events[-1]['receipt'])
        if receipt.plan_hash != plan.plan_hash or any(e.get('plan_hash') != plan.plan_hash for e in events):
            raise ValueError('LIVE_INHERITED_BUY_PLAN_BINDING_UNPROVEN')
        if receipt.state not in _EFFECT_STATES:
            raise ValueError('LIVE_INHERITED_BUY_EFFECT_STATE_UNPROVEN')
        if receipt.account_binding != 'proven' or not (receipt.submit_claim_id or receipt.broker_order_id):
            raise ValueError('LIVE_INHERITED_BUY_ACCOUNT_UNPROVEN')
        explicit_binding = receipt.locator_proof.get('fund_account_binding_sha256')
        if explicit_binding is not None and explicit_binding != snapshot['fund_account_binding_sha256']:
            raise ValueError('LIVE_INHERITED_BUY_ACCOUNT_MISMATCH')
        if (type(plan.shares) is not int or plan.shares <= 0
                or number(plan.limit_price) <= 0):
            raise ValueError('LIVE_INHERITED_BUY_AMOUNT_UNPROVEN')
        proved = sum(int(r['shares']) for r in rows_prefix if r['plan_id'] == plan_id and r['side'] == 'BUY')
        remaining = plan.shares - proved
        if not 0 <= remaining <= plan.shares:
            raise ValueError('LIVE_INHERITED_BUY_FILL_BOUND_UNPROVEN')
        price = number(plan.limit_price)
        claims = {}
        claim_orders = {}
        for event in events:
            seen = ExecutionReceipt.from_dict(event['receipt'])
            if seen.submit_claim_id:
                if any(claim != seen.submit_claim_id and prior.state not in TERMINAL_STATES
                        for claim, prior in claims.items()):
                    raise ValueError('LIVE_INHERITED_BUY_MULTIPLE_UNRESOLVED_CLAIMS')
                claims[seen.submit_claim_id] = seen
                if seen.broker_order_id:
                    orders = claim_orders.setdefault(seen.submit_claim_id, set())
                    orders.add(seen.broker_order_id)
                    if len(orders) > 1:
                        raise ValueError('LIVE_INHERITED_BUY_ORDER_IDENTITY_CHANGED')
            if seen.state not in _EFFECT_STATES:
                continue
            native = seen.locator_proof.get('native_order_readback') or {}
            try:
                native_quantity = (_integer(native['quantity'], field='ORDER_QUANTITY')
                    if native.get('quantity') is not None else None)
                native_price = (_decimal(native['price'], field='ORDER_PRICE')
                    if native.get('price') is not None else None)
                native_side = _side(native['side']) if native.get('side') not in (None, '') else None
            except RuntimeError as exc:
                raise ValueError('LIVE_INHERITED_BUY_EFFECT_BOUND_CONTRADICTED') from exc
            contradiction = (
                seen.order_price is not None and number(seen.order_price) > price
                or not 0 <= seen.remaining_shares <= plan.shares
                or native.get('code') not in (None, '') and _normalize_code(native['code']) != plan.code.split('.')[0]
                or native_side is not None and native_side != 'BUY'
                or native_quantity is not None and not 0 < native_quantity <= plan.shares
                or native_price is not None and not 0 < native_price <= price
                or native.get('field_mapping_proven') is False
            )
            if contradiction or seen.locator_proof.get('terminal_identity_mismatch'):
                raise ValueError('LIVE_INHERITED_BUY_EFFECT_BOUND_CONTRADICTED')
        row = rows.get(plan.code.split('.')[0])
        mark = price
        if row is not None:
            shares = _broker_integer(row.get('证券数量'), reason='LIVE_INHERITED_BUY_POSITION_UNPROVEN')
            if shares > 0:
                mark = _broker_decimal(row.get('当前价'), reason='LIVE_INHERITED_BUY_MARK_UNPROVEN')
                if mark <= 0:
                    raise ValueError('LIVE_INHERITED_BUY_MARK_UNPROVEN')
        cost = (Decimal(remaining) * price * Decimal('1.0001')).quantize(_CENT, rounding=ROUND_CEILING)
        risk_exposure = (Decimal(remaining) * max(price, mark)).quantize(_CENT, rounding=ROUND_CEILING)
        commitments += cost
        exposure += risk_exposure
        entries.append({'plan_id': plan_id, 'plan_hash': plan.plan_hash, 'code': plan.code,
            'event_head': {'sequence': events[-1]['sequence'], 'event_hash': events[-1]['event_hash']},
            'service_state': receipt.state.value, 'submit_claim_id': receipt.submit_claim_id,
            'proved_filled_shares': proved, 'possible_remaining_shares': remaining,
            'cash_commitment_upper_bound': str(cost), 'exposure_upper_bound': str(risk_exposure)})
    result = {'schema_version': 'inherited-buy-isolation.v1', 'scope': 'independent_new_buy',
        'trade_date': snapshot['trade_date'], 'observed_at': snapshot['observed_at'],
        'fund_account_binding_sha256': snapshot['fund_account_binding_sha256'],
        'capital_policy_sha256': cfg['policy_sha256'], 'broker_snapshot_sha256': snapshot['snapshot_sha256'],
        'ownership_head_sha256': source_head, 'plan_bounds': entries,
        'broker_available_cash': str(cash), 'gross_cash_lower_bound': str(gross),
        'cash_commitment_upper_bound': str(commitments), 'potential_exposure_upper_bound': str(exposure),
        'new_buy_cash_limit': str(max(Decimal(0), min(cash, gross - commitments))),
        'same_code_buy_fences': sorted({entry['code'] for entry in entries}),
        'accounting_finality': 'pending', 'order_replay_allowed': False}
    return result


def prove(root: Path, snapshot: dict, *, now: datetime) -> dict | None:
    from .buy_preflight import validate_buy_preflight
    validate_buy_preflight(snapshot, snapshot['trade_date'], now)
    root = Path(root)
    if not prior_day_buy_ids(root, trade_date=snapshot['trade_date']):
        return None
    try:
        result = _calculate(root, snapshot)
    except (KeyError, TypeError, AttributeError, InvalidOperation) as exc:
        raise ValueError('LIVE_INHERITED_BUY_EFFECT_BOUND_UNPROVEN') from exc
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    path = root / 'inherited_buy_evidence' / (snapshot['snapshot_sha256'] + '.json')
    atomic_write(path, payload, immutable=True)
    result['snapshot_path'] = str(path.resolve())
    result['snapshot_file_sha256'] = hashlib.sha256(payload).hexdigest()
    result['isolation_sha256'] = digest(result)
    return result


def verify(root: Path, proof: dict, *, current: bool = True, now: datetime | None = None) -> dict:
    """Verify original prefixes for archived caps; current admission also checks heads."""
    try:
        return _verify(root, proof, current=current, now=now)
    except (KeyError, TypeError, AttributeError, InvalidOperation) as exc:
        raise ValueError('LIVE_INHERITED_BUY_PROOF_INVALID') from exc


def _verify(root: Path, proof: dict, *, current: bool, now: datetime | None) -> dict:
    root = Path(root)
    body = {k: v for k, v in proof.items() if k != 'isolation_sha256'}
    if digest(body) != proof.get('isolation_sha256'):
        raise ValueError('LIVE_INHERITED_BUY_PROOF_HASH_MISMATCH')
    path = Path(proof['snapshot_path'])
    expected = (root / 'inherited_buy_evidence' / (proof['broker_snapshot_sha256'] + '.json')).resolve()
    if path.is_symlink() or path.resolve() != expected:
        raise ValueError('LIVE_INHERITED_BUY_SNAPSHOT_PATH_UNPROVEN')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != proof['snapshot_file_sha256']:
        raise ValueError('LIVE_INHERITED_BUY_SNAPSHOT_HASH_MISMATCH')
    if now is not None:
        from .buy_preflight import validate_buy_preflight
        validate_buy_preflight(json.loads(raw), proof['trade_date'], now)
    heads = {entry['plan_id']: entry['event_head'] for entry in proof['plan_bounds']}
    rebuilt = _calculate(root, json.loads(raw), event_heads=None if current else heads, ownership_head=proof['ownership_head_sha256'])
    rebuilt.update(snapshot_path=str(path.resolve()), snapshot_file_sha256=proof['snapshot_file_sha256'])
    if rebuilt != body:
        raise ValueError('LIVE_INHERITED_BUY_PROOF_SOURCE_CHANGED')
    return proof
