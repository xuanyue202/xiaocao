"""New-BUY scope boundary; engineering tests obey the APP test window."""
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from xiaocao.live.foundersc_native_ax import NativeAXReceipt
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter
from tests.test_foundersc_native_broker import FakeNative, _plan

pytestmark = pytest.mark.app_simulation


class ScopedNative(FakeNative):
    def __init__(self):
        super().__init__(helper_version=11)
        self.position_summary = {'可用': '20000.00'}
        self.corrupt = None

    def read_query(self, **kwargs):
        payload = super().read_query(**kwargs).as_dict()
        r = payload['query_readback']
        r.update(structural_parsing_proven=True,
                 observed_at=datetime.now(timezone.utc).isoformat(),
                 critical_confidence_floor=0.5,
                 critical_cell_confidences=[{k: 0.99 for k in row} for row in r['rows']])
        if self.corrupt == 'structure':
            r['structural_parsing_proven'] = False
        if self.corrupt == 'code' and r['rows']:
            r['critical_cell_confidences'][0]['证券代码'] = 0.2
        if self.corrupt == 'status' and kwargs['kind'] == 'today-orders':
            r['parsing_proven'] = False
            r['critical_cell_confidences'][0]['状态说明'] = 0.1
        return NativeAXReceipt(payload)


def adapter(native):
    return FounderscNativeAXBrokerAdapter(native=native,
        expected_fund_account_fingerprint='123******890',
        scoped_buy_preflight=True, snapshot_read_delays=(0,))


def test_unrelated_orders_and_valuation_do_not_block_new_buy():
    n = ScopedNative()
    n.orders[0].update(状态说明='任意旧状态', 成交数量='未识别', 委托价格='不重要')
    n.positions[0].update(当前价='未识别', 最新市值='未识别')
    n.corrupt = 'status'
    capability = adapter(n).probe(_plan())
    assert capability.ready and capability.supports_submit
    assert n.query_calls == ['positions', 'today-orders']
    assert n.open_cancel_calls == n.submit_calls == n.cancel_calls == 0


@pytest.mark.parametrize('corrupt', ['structure', 'code'])
def test_scope_cannot_hide_ambiguous_table_or_identity(corrupt):
    n = ScopedNative(); n.corrupt = corrupt
    assert not adapter(n).probe(_plan()).ready
    assert n.submit_calls == 0


def test_duplicate_exact_tuple_still_prevents_prepare_and_submit():
    n = ScopedNative()
    plan = replace(_plan(), code='515120.XSHG', limit_price=0.646, basket_price=0.65)
    a = adapter(n)
    with a.submission_batch([plan]):
        result = a.prepare(plan)
    assert result.reason == 'NATIVE_PREEXISTING_EXACT_ORDER_BLOCKS_SUBMIT'
    assert n.prepare_calls == n.submit_calls == 0


def test_batch_baseline_covers_second_symbol_and_uses_only_two_queries():
    n = ScopedNative()
    first = _plan()
    second = replace(first, plan_id='other', code='515120.XSHG', limit_price=0.646, basket_price=0.65)
    a = adapter(n)
    with a.submission_batch([first, second]):
        assert a.prepare(second).reason == 'NATIVE_PREEXISTING_EXACT_ORDER_BLOCKS_SUBMIT'
    assert n.query_calls == ['positions', 'today-orders']
    assert n.submit_calls == n.cancel_calls == 0


def test_owned_position_and_available_cash_remain_required():
    n = ScopedNative(); n.positions[1]['当前价'] = 'bad'
    assert not adapter(n).probe(_plan()).ready
    n = ScopedNative(); n.position_summary = {'余额': '100000'}
    assert not adapter(n).probe(_plan()).ready


def test_buying_power_capsule_binds_only_spendable_cash_and_preserves_capital(tmp_path):
    from xiaocao.live.buy_preflight import allocation_from_buy_preflight, pretrade_account
    from xiaocao.live.book_b_live_morning import BookBLiveCapitalBasis, BookBLiveMorningConfig, _load_allocation
    now = datetime.now(timezone.utc)
    from zoneinfo import ZoneInfo
    day = now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    snapshot = adapter(ScopedNative()).read_buy_preflight_snapshot(trade_date=day, owned_codes=set())
    basis = BookBLiveCapitalBasis(30000, 0, 'initial_book_b_capital', None)
    payload = allocation_from_buy_preflight(snapshot, basis, now=datetime.now(timezone.utc))
    config = BookBLiveMorningConfig(day, tmp_path/'freeze', tmp_path/'allocation', tmp_path)
    facts = _load_allocation(config, payload)
    assert facts.available_cash == 20000
    assert facts.settled_nav == 30000
    account = pretrade_account(tmp_path, snapshot, trade_date=day, now=datetime.now(timezone.utc))
    assert account.cash == account.settled_nav == 30000
    assert account.lots == ()
    assert 'broker_total_assets' not in payload
    payload['available_cash'] = 50000
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        _load_allocation(config, payload)


def test_wrong_date_and_locale_numbers_keep_strict_pretrade_semantics():
    n = ScopedNative()
    n.positions[1]['当前价'] = '10,0000'
    a = adapter(n)
    assert a.probe(_plan()).ready
    assert a.last_query_readbacks['positions']['rows'][0]['当前价'] == '10.0000'
    with pytest.raises(Exception, match='DATE_MISMATCH'):
        a.read_buy_preflight_snapshot(trade_date='2000-01-01', owned_codes={'000001.XSHE'})
