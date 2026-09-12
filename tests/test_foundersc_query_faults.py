"""Malformed APP grids cannot become usable positions, orders or fills."""
from datetime import datetime

import pytest

from tests.test_foundersc_native_broker import FakeNative, _adapter, OBSERVED_AT
from xiaocao.live.foundersc_native_ax import FounderscNativeAXError
from xiaocao.live.foundersc_native_broker import _decimal


@pytest.mark.parametrize("table,field,value", [
    ("positions", "证券代码", "12345"), ("positions", "证券数量", "100.5"),
    ("positions", "可卖数量", "-1"), ("positions", "当前价", "-1"),
    ("positions", "最新市值", "NaN"), ("positions", "证券数量", ""),
    ("orders", "委托编号", "6O00002"), ("orders", "委托数量", "0"),
    ("orders", "成交数量", "101"), ("orders", "成交数量", "-1"),
    ("orders", "委托价格", "-1"), ("orders", "状态说明", ""),
    ("orders", "买卖标志", "买八"), ("orders", "证券代码", "1234567"),
    ("trades", "成交数量", "0"), ("trades", "成交数量", "40.5"),
    ("trades", "成交价格", "0"), ("trades", "成交编号", "bad"),
    ("trades", "委托编号", ""), ("trades", "买卖标志", "未知"),
])
def test_bad_grid_never_produces_account_snapshot(table, field, value):
    native = FakeNative()
    native.trades = [{"证券代码": "515120", "买卖标志": "买入", "成交数量": "40",
                      "成交价格": "0.646", "成交编号": "700001", "委托编号": "6000002"}]
    getattr(native, table)[0][field] = value
    with pytest.raises(FounderscNativeAXError, match="NATIVE_QUERY"):
        _adapter(native).read_live_account_snapshot(
            trade_date="2026-08-30", expected_fund_account_fingerprint="123******890",
            now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
        )
    assert native.prepare_calls == native.submit_calls == native.cancel_calls == 0


@pytest.mark.parametrize("text", ["12,34.56", "1.23,45", "1,,000.00", "1.2.3,40", "12x", "1e3"])
def test_malformed_numeric_grouping_is_not_silently_changed(text):
    with pytest.raises(FounderscNativeAXError, match="MALFORMED"):
        _decimal(text, field="TOTAL_ASSETS")


@pytest.mark.parametrize("text,expected", [
    ("1,234.56", "1234.56"), ("1.234,56", "1234.56"),
    ("17,3900", "17.3900"), ("1,234,567", "1234567"),
    ("1,234,56", "1234.56"), ("0,123", "0.123"),
])
def test_observed_locale_formats_remain_supported(text, expected):
    from decimal import Decimal
    assert _decimal(text, field="TOTAL_ASSETS") == Decimal(expected)


@pytest.mark.parametrize("fault", ["non_row", "fractional_count"])
def test_grid_cannot_hide_rows_or_truncate_its_row_count(fault):
    class Native(FakeNative):
        def read_query(self, **kwargs):
            result = super().read_query(**kwargs)
            if kwargs["kind"] == "positions":
                grid = result.payload["query_readback"]
                if fault == "non_row":
                    grid["rows"] = [*grid["rows"], None]
                else:
                    grid["row_count"] = len(grid["rows"]) + 0.5
            return result
    native = Native()
    with pytest.raises(FounderscNativeAXError, match="NATIVE_QUERY"):
        _adapter(native).read_live_account_snapshot(
            trade_date="2026-08-30", expected_fund_account_fingerprint="123******890",
            now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
        )
    assert native.prepare_calls == native.submit_calls == native.cancel_calls == 0


@pytest.mark.parametrize('glyph,price,traded,allowed', [
    ('O', '0.000', False, True), ('OO', '0.000', False, False),
    ('O', '1.000', False, False), ('O', '0.000', True, False),
])
def test_isolated_zero_ocr_alias_requires_zero_price_and_independent_zero_trades(glyph, price, traded, allowed):
    class Native(FakeNative):
        def read_query(self, **kwargs):
            result = super().read_query(**kwargs)
            if kwargs['kind'] == 'today-orders':
                q = result.payload['query_readback']
                q.update(parsing_proven=False, critical_confidence_proven=False,
                         headers=list(q['rows'][0]), low_confidence_critical_headers=['成交数量'])
            return result
    native = Native()
    native.orders[0].update({'成交数量': glyph, '成交价格': price})
    if traded:
        native.trades = [{'证券代码':'515120','买卖标志':'买入','成交数量':'1',
                          '成交价格':'0.646','成交编号':'1234','委托编号':'6000002'}]
    adapter = _adapter(native)
    def read():
        return adapter.read_live_account_snapshot(trade_date='2026-08-30',
            expected_fund_account_fingerprint='123******890',
            now=datetime.fromisoformat(OBSERVED_AT.replace('Z','+00:00')))
    if allowed:
        assert read()['tables']['today-orders']['rows'][0]['成交数量'] == '0'
        assert native.query_calls.count('today-orders') == 2
    else:
        with pytest.raises(FounderscNativeAXError):
            read()
