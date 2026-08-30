from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from xiaocao.live.foundersc_native_ax import FounderscNativeAXError, NativeAXReceipt
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter
from xiaocao.live.trading_execution import BrokerStatus, TradePlan


OBSERVED_AT = "2026-08-30T12:39:09.550Z"


def _plan() -> TradePlan:
    now = datetime(2026, 8, 30, 1, 30, tzinfo=timezone.utc)
    return TradePlan(
        plan_id="book-b:2026-08-30:000001.XSHE:BUY",
        strategy_run_id="run-native",
        snapshot_ref="freeze.jsonl#1",
        strategy_sha="abc123",
        trade_date="2026-08-30",
        book="B",
        logical_account_id="primary",
        environment="live",
        code="000001.XSHE",
        name="测试标的",
        side="BUY",
        shares=100,
        limit_price=10.0,
        basket_price=10.1,
        market_guard_status="ok",
        created_at=now,
        recovery_deadline=now + timedelta(minutes=15),
        allocation_proof_hash="proof",
    )


class FakeNative:
    def __init__(self, **overrides):
        self.payload = {
            "schema_version": 2,
            "helper_version": 5,
            "status": "trade_ready",
            "surface_state": "trade_ready",
            "app_running": True,
            "accessibility_trusted": True,
            "screen_locked": False,
            "side": "buy",
            "trade_account_fingerprint": "123******890",
            "trade_account_fingerprint_count": 1,
            "capabilities": {"prepare": True, "submit": True},
        }
        self.payload.update(overrides)
        self.surface = str(self.payload["surface_state"])
        self.prepare_calls = 0
        self.submit_calls = 0
        self.open_order_calls = 0
        self.query_calls: list[str] = []
        self.orders = [
            {
                "证券代码": "515120",
                "证券名称": "创新药",
                "委托时间": "193629",
                "买卖标志": "买入",
                "委托类别": "委托",
                "状态说明": "未报",
                "委托价格": "0.6460",
                "委托数量": "100",
                "委托编号": "6000002",
                "成交价格": "0.000",
                "成交数量": "",
                "报价方式": "买卖",
                "股东代码": "A***",
                "备注": "",
            }
        ]
        self.positions = [
            {
                "证券代码": "515120",
                "证券名称": "创新药",
                "证券数量": "65100.00",
                "可卖数量": "65100.00",
                "参考成本价": "0.7020",
                "当前价": "0.6460",
                "最新市值": "42054.60",
            },
            {
                "证券代码": "000001",
                "证券名称": "测试标的",
                "证券数量": "100.00",
                "可卖数量": "100.00",
                "参考成本价": "9.0000",
                "当前价": "10.0000",
                "最新市值": "1000.00",
            },
        ]
        self.trades: list[dict[str, str]] = []

    def _receipt(self, **values) -> NativeAXReceipt:
        return NativeAXReceipt({**self.payload, "surface_state": self.surface, **values})

    def probe(self, *, table_audit: bool = False) -> NativeAXReceipt:
        assert table_audit is True
        caps = {"prepare": self.surface == "trade_ready", "submit": self.surface == "trade_ready"}
        return self._receipt(status=self.surface, capabilities=caps)

    def unlock_from_keychain(self, *, explicitly_enabled: bool) -> NativeAXReceipt:
        assert explicitly_enabled is True
        self.surface = "query_only"
        return self._receipt(status="unlocked")

    def open_query_surface(self, **_kwargs) -> NativeAXReceipt:
        self.surface = "query_only"
        return self._receipt(status="query_surface_opened")

    def open_order_surface(self, *, side: str, **_kwargs) -> NativeAXReceipt:
        self.open_order_calls += 1
        self.surface = "trade_ready"
        return self._receipt(
            status="order_surface_opened",
            side=side.lower(),
            capabilities={"prepare": True, "submit": True},
        )

    def read_query(self, *, kind: str, **_kwargs) -> NativeAXReceipt:
        self.query_calls.append(kind)
        rows = {
            "positions": self.positions,
            "today-orders": self.orders,
            "today-trades": self.trades,
            "funds": [{"资金余额": "1000.00", "可用资金": "100.00", "总资产": "43054.60"}],
        }[kind]
        summary = (
            {"资产": "43054.60", "股票市值": "43054.60", "可用": "0.00"}
            if kind == "positions" else {}
        )
        return self._receipt(
            status="query_read",
            query_readback={
                "kind": kind,
                "capture_proven": True,
                "parsing_proven": True,
                "empty_state_proven": not rows,
                "rows": [dict(row) for row in rows],
                "row_count": len(rows),
                "summary_values": summary,
                "observed_at": OBSERVED_AT,
            },
        )

    def prepare_order(self, **kwargs) -> NativeAXReceipt:
        self.prepare_calls += 1
        return self._receipt(
            status="prepared",
            order_readback={
                "code": kwargs["code"].split(".", 1)[0],
                "side": kwargs["side"].lower(),
                "price": str(kwargs["price"]),
                "quantity": kwargs["quantity"],
                "field_mapping_proven": True,
                "submit_control_count": 1,
                "submitted": False,
                "saved": False,
                "started": False,
                "form_cleared": kwargs.get("clear_after_readback", False),
                "observed_at": OBSERVED_AT,
            },
        )

    def submit_prepared_order(self, **kwargs) -> NativeAXReceipt:
        assert kwargs["explicitly_enabled"] is True
        self.submit_calls += 1
        self.orders.append(
            {
                "证券代码": kwargs["code"].split(".", 1)[0],
                "证券名称": "测试标的",
                "委托时间": "092001",
                "买卖标志": "买入" if kwargs["side"].upper() == "BUY" else "卖出",
                "委托类别": "委托",
                "状态说明": "未报",
                "委托价格": f"{kwargs['price']:.4f}",
                "委托数量": str(kwargs["quantity"]),
                "委托编号": "6000003",
                "成交价格": "0.000",
                "成交数量": "",
                "报价方式": "买卖",
                "股东代码": "A***",
                "备注": "",
            }
        )
        return self._receipt(
            status="submit_clicked",
            order_readback={
                "code": kwargs["code"].split(".", 1)[0],
                "side": kwargs["side"].lower(),
                "price": str(kwargs["price"]),
                "quantity": kwargs["quantity"],
                "field_mapping_proven": True,
                "submit_control_count": 1,
                "submitted": True,
                "saved": False,
                "started": True,
                "observed_at": OBSERVED_AT,
            },
        )


class TransientOrderQueryNative(FakeNative):
    def __init__(self):
        super().__init__()
        self.transient_order_reads = 0

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind == "today-orders" and self.transient_order_reads == 0:
            self.transient_order_reads += 1
            return self._receipt(
                status="query_parse_unproven",
                query_readback={
                    "kind": kind,
                    "capture_proven": True,
                    "parsing_proven": False,
                    "rows": [],
                    "row_count": 0,
                    "observed_at": OBSERVED_AT,
                },
            )
        return super().read_query(kind=kind, **kwargs)


def _adapter(native: FakeNative | None = None) -> FounderscNativeAXBrokerAdapter:
    return FounderscNativeAXBrokerAdapter(
        native=native or FakeNative(),
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0,),
    )


def test_native_probe_proves_app_only_submit_and_all_readbacks() -> None:
    adapter = _adapter()

    capability = adapter.probe(_plan())

    assert capability.ready is True
    assert capability.route == "native-app"
    assert capability.supports_submit is True
    assert capability.supports_reconcile is True
    assert capability.account_binding == "proven"
    assert capability.capabilities["opencli_used"] is False
    assert capability.capabilities["native_orders"] is True
    assert capability.owned_position_shares == 100


def test_native_ready_navigates_from_wrong_order_side() -> None:
    native = FakeNative(side="sell")
    adapter = _adapter(native)

    receipt = adapter.ensure_native_ready(
        require_order_capability=True,
        side="BUY",
    )

    assert receipt["side"] == "buy"
    assert native.open_order_calls == 1


def test_query_uses_one_targeted_reread_only_after_invalid_first_parse() -> None:
    native = TransientOrderQueryNative()
    adapter = _adapter(native)

    readback = adapter._query("today-orders")

    assert readback["row_count"] == 1
    assert readback["targeted_reread_used"] is True
    assert native.transient_order_reads == 1


def test_native_prepare_submit_uses_new_unique_order_delta() -> None:
    native = FakeNative()
    adapter = _adapter(native)

    prepared = adapter.prepare(_plan())
    submitted = adapter.submit(_plan(), "claim-1")

    assert prepared.normalized_status() == BrokerStatus.PREPARED
    assert submitted.normalized_status() == BrokerStatus.ACCEPTED
    assert submitted.order_id == "6000003"
    assert submitted.receipt_mapping is True
    assert submitted.retry_allowed is False
    assert submitted.locator_proof["exact_order_match_count"] == 1
    assert submitted.locator_proof["trade_match_count"] == 0
    assert native.prepare_calls == 1
    assert native.submit_calls == 1


def test_user_manual_sample_is_exactly_reconciled_as_unfilled_accepted() -> None:
    adapter = _adapter()
    sample = replace(
        _plan(),
        plan_id="sample-515120",
        code="515120.XSHG",
        name="创新药",
        limit_price=0.646,
        basket_price=0.646,
    )

    receipt = adapter._reconcile_rows(
        sample,
        requested_shares=100,
        expected_order_id="6000002",
    )

    assert receipt.normalized_status() == BrokerStatus.ACCEPTED
    assert receipt.order_id == "6000002"
    assert receipt.filled_shares == 0
    assert receipt.field_readback["order_status"] == "未报"


def test_preexisting_exact_order_blocks_prepare_before_form_write() -> None:
    native = FakeNative()
    adapter = _adapter(native)
    sample = replace(
        _plan(),
        plan_id="sample-515120",
        code="515120.XSHG",
        name="创新药",
        limit_price=0.646,
        basket_price=0.646,
    )

    receipt = adapter.prepare(sample)

    assert receipt.normalized_status() == BrokerStatus.REJECTED
    assert receipt.reason == "NATIVE_PREEXISTING_EXACT_ORDER_BLOCKS_SUBMIT"
    assert receipt.field_readback["baseline_exact_order_match_count"] == 1
    assert native.prepare_calls == 0


def test_unknown_order_status_is_no_retry() -> None:
    native = FakeNative()
    native.orders[0]["状态说明"] = "待人工核验"
    adapter = _adapter(native)
    sample = replace(
        _plan(),
        code="515120.XSHG",
        name="创新药",
        limit_price=0.646,
        basket_price=0.646,
    )

    receipt = adapter._reconcile_rows(
        sample,
        requested_shares=100,
        expected_order_id="6000002",
    )

    assert receipt.normalized_status() == BrokerStatus.UNKNOWN
    assert receipt.conclusive is False
    assert receipt.retry_allowed is False


def test_native_account_mismatch_is_fail_closed() -> None:
    adapter = _adapter(FakeNative(trade_account_fingerprint="999******999"))

    with pytest.raises(FounderscNativeAXError, match="ACCOUNT_SURFACE_NOT_READY"):
        adapter.ensure_native_ready()


def test_native_allocation_uses_position_summary_and_equations() -> None:
    adapter = _adapter()
    now = datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00"))

    facts = adapter.read_live_allocation_facts(
        trade_date="2026-08-30",
        settled_nav=100000,
        current_open_exposure=40000,
        capital_basis_source="initial_book_b_capital",
        expected_fund_account_fingerprint="123******890",
        now=now,
    )

    assert facts["source"] == "foundersc_native_app"
    assert facts["available_cash"] == 0
    assert facts["broker_total_assets"] == 43054.6
    assert len(facts["allocation_capsule_sha256"]) == 64


def test_native_allocation_rejects_position_sum_drift() -> None:
    native = FakeNative()
    native.positions[0]["最新市值"] = "42000.00"
    adapter = _adapter(native)

    with pytest.raises(FounderscNativeAXError, match="POSITION_SUM_FAILED"):
        adapter.read_live_allocation_facts(
            trade_date="2026-08-30",
            settled_nav=100000,
            current_open_exposure=40000,
            capital_basis_source="initial_book_b_capital",
            expected_fund_account_fingerprint="123******890",
            now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
        )
