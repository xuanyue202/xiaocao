"""Replay the APP's pre-fill principal/charge reservation, across consumers."""
from datetime import datetime
from decimal import Decimal

import pytest

from tests.test_foundersc_native_broker import FakeNative, _adapter, _plan, OBSERVED_AT
from xiaocao.live.foundersc_native_broker import pending_buy_reservation_evidence
from xiaocao.live.foundersc_native_ax import FounderscNativeAXError
from xiaocao.live.book_b_live_lifecycle import validate_broker_account_snapshot


def reserved_native(count):
    native = FakeNative()
    row = native.orders[0]
    native.orders = [{**row, '委托编号': str(7000000+i), '委托价格': str(Decimal('.36')+Decimal(i)/100)}
                     for i in range(count)]
    principal = sum(Decimal(r['委托价格'])*100 for r in native.orders)
    # Observed 100@0.36 reserved 41.02. This fixture is NOT a production fee model.
    available = Decimal(1000) - principal - Decimal('5.02')*count
    native.position_summary.update({'余额':'1000', '可用':str(available), '可取':str(available),
                                   '资产':str(Decimal('43054.60')+available)})
    return native


@pytest.mark.parametrize('count',[1,2,5])
def test_pending_orders_allow_next_probe_and_lifecycle_without_inventing_fills(count):
    native = reserved_native(count)
    adapter = _adapter(native)
    now = datetime.fromisoformat(OBSERVED_AT.replace('Z','+00:00'))
    snapshot = adapter.read_live_account_snapshot(trade_date='2026-08-30',
        expected_fund_account_fingerprint='123******890', now=now)
    assert adapter.probe(_plan()).ready
    assert snapshot['cash_reservation_evidence']['order_ids'] == [str(7000000+i) for i in range(count)]
    assert snapshot['tables']['today-trades']['rows'] == []
    validate_broker_account_snapshot(snapshot, trade_date='2026-08-30', now=now)
    assert native.prepare_calls == native.submit_calls == native.cancel_calls == 0


@pytest.mark.parametrize('change',['cancelled','rejected','unknown','sell','duplicate','principal_exceeds_cash'])
def test_unproven_reservation_cannot_excuse_cash_mismatch(change):
    native = reserved_native(1)
    if change in {'cancelled','rejected','unknown'}:
        native.orders[0]['状态说明'] = {'cancelled':'已撤','rejected':'废单','unknown':'不明'}[change]
    elif change == 'sell':
        native.orders[0]['买卖标志'] = '卖出'
    elif change == 'duplicate':
        native.orders.append(dict(native.orders[0]))
    else:
        native.orders[0]['委托价格'] = '10.0'
    assert pending_buy_reservation_evidence(native.orders, balance=Decimal(1000),
        available=Decimal(native.position_summary['可用'])) is None
    assert not _adapter(native).probe(_plan()).ready
    with pytest.raises(FounderscNativeAXError):
        _adapter(native).read_live_account_snapshot(trade_date='2026-08-30',
            expected_fund_account_fingerprint='123******890',
            now=datetime.fromisoformat(OBSERVED_AT.replace('Z','+00:00')))
