"""An old unnumbered claim reads its original date, without another action."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.test_foundersc_native_broker import FakeNative, _adapter, _plan, OBSERVED_AT
from xiaocao.live.trading_execution import BrokerStatus

pytestmark = pytest.mark.app_simulation


def previous():
    return {'submit_claim_id':'original-claim','submit_chain_uncertain':True,
        'requested_shares':100,'locator_proof':{'baseline_order_ids':[],
            'baseline_order_count':0,'baseline_observed_at':OBSERVED_AT}}


def test_unmapped_old_claim_uses_original_history_not_today_delta():
    native=FakeNative()
    native.orders=[]
    native.trades=[]
    native.history_orders=[{'证券代码':'000001','委托日期':'20260830',
        '买卖标志':'买入','委托类别':'委托','状态说明':'废单','委托价格':'10.00',
        '委托数量':'100','委托编号':'1234567','成交数量':'0','成交价格':'0'}]
    native.history_trades=[]
    receipt=_adapter(native).recover(_plan(),previous())
    assert receipt.normalized_status()==BrokerStatus.REJECTED,receipt.reason
    assert receipt.order_id=='1234567' and receipt.receipt_mapping
    assert receipt.strategy_id is not None
    assert native.query_calls==['history-orders','history-trades','positions']
    assert native.submit_calls==native.cancel_calls==native.unlock_calls==0


def test_complete_empty_history_is_an_observation_not_a_fabricated_rejection():
    native=FakeNative()
    native.history_orders=[];native.history_trades=[]
    receipt=_adapter(native).recover(_plan(),previous())
    assert receipt.normalized_status()==BrokerStatus.UNKNOWN and not receipt.retry_allowed
    assert 'history-orders' in native.query_calls
    assert receipt.locator_proof['history_query_complete'] is True
    assert receipt.order_id is None and not receipt.receipt_mapping
    assert native.submit_calls==native.cancel_calls==native.unlock_calls==0


def history_order(order_id):
    return {'证券代码':'000001','委托日期':'20260830', '买卖标志':'买入',
        '委托类别':'委托','状态说明':'废单','委托价格':'10.00',
        '委托数量':'100','委托编号':order_id,'成交数量':'0','成交价格':'0'}


@pytest.mark.parametrize('new_ids,expected', [([], None), (['1234568'], '1234568'),
    (['1234568','1234569'], None)])
def test_original_baseline_is_removed_before_historical_delta_uniqueness(new_ids, expected):
    native=FakeNative()
    native.history_orders=[history_order(order_id) for order_id in ['1234567',*new_ids]]
    native.history_trades=[]
    old=previous()
    old['locator_proof'].update(baseline_order_ids=['1234567'],baseline_order_count=1)
    receipt=_adapter(native).recover(_plan(),old)
    assert receipt.order_id==expected
    assert bool(receipt.receipt_mapping)==bool(expected)
    assert receipt.normalized_status()==(BrokerStatus.REJECTED if expected else BrokerStatus.UNKNOWN)
    assert native.submit_calls==native.cancel_calls==native.unlock_calls==0


def test_old_claim_never_uses_or_acknowledges_a_current_server_notice():
    native=FakeNative()
    native.history_orders=[];native.history_trades=[]
    def forbidden(**kwargs):
        pytest.fail('current notice cannot prove a prior-date unknown submit')
    native.read_submit_rejection=forbidden
    receipt=_adapter(native).recover(_plan(),previous())
    assert receipt.normalized_status()==BrokerStatus.UNKNOWN


def test_original_day_routing_uses_china_date_when_injected_clock_is_utc():
    native=FakeNative()
    native.history_orders=[history_order('1234567')];native.history_trades=[]
    adapter=_adapter(native)
    adapter._clock=lambda: datetime(2026,8,30,17,tzinfo=ZoneInfo('UTC'))
    receipt=adapter.recover(_plan(),previous())
    assert receipt.order_id=='1234567'
    assert native.query_calls[:2]==['history-orders','history-trades']


def test_a_different_day_baseline_cannot_rebind_an_old_claim():
    native=FakeNative();old=previous()
    old['locator_proof']['baseline_observed_at']='2026-08-31T01:20:00+00:00'
    receipt=_adapter(native).recover(_plan(),old)
    assert receipt.normalized_status()==BrokerStatus.UNKNOWN
    assert receipt.reason=='NATIVE_RECOVERY_DURABLE_CONTEXT_UNPROVEN'
    assert native.query_calls==[]
