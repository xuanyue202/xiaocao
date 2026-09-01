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
            "helper_version": 8,
            "status": "trade_ready",
            "surface_state": "trade_ready",
            "app_running": True,
            "accessibility_trusted": True,
            "screen_locked": False,
            "side": "buy",
            "trade_account_fingerprint": "123******890",
            "trade_account_fingerprint_count": 1,
            "capabilities": {"prepare": True, "submit": True, "cancel": True},
        }
        self.payload.update(overrides)
        self.surface = str(self.payload["surface_state"])
        self.prepare_calls = 0
        self.submit_calls = 0
        self.cancel_calls = 0
        self.unlock_calls = 0
        self.open_cancel_calls = 0
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
        self.history_orders: list[dict[str, str]] = []
        self.history_trades: list[dict[str, str]] = []
        self.position_summary = {
            "资产": "43054.60",
            "股票市值": "43054.60",
            "可用": "0.00",
            "余额": "0.00",
            "可取": "0.00",
        }

    def _receipt(self, **values) -> NativeAXReceipt:
        return NativeAXReceipt({**self.payload, "surface_state": self.surface, **values})

    def probe(self, *, table_audit: bool = False) -> NativeAXReceipt:
        assert table_audit is True
        caps = {"prepare": self.surface == "trade_ready", "submit": self.surface == "trade_ready"}
        return self._receipt(status=self.surface, capabilities=caps)

    def unlock_from_keychain(self, *, explicitly_enabled: bool) -> NativeAXReceipt:
        assert explicitly_enabled is True
        self.unlock_calls += 1
        self.surface = "query_only"
        return self._receipt(status="unlocked")

    def open_query_surface(self, **_kwargs) -> NativeAXReceipt:
        self.surface = "query_only"
        return self._receipt(status="query_surface_opened")

    def open_cancel_surface(self, **_kwargs) -> NativeAXReceipt:
        self.open_cancel_calls += 1
        self.surface = "query_only"
        return self._receipt(
            status="cancel_surface_ready",
            capabilities={"prepare": False, "submit": False, "cancel": True},
        )

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
            "history-orders": self.history_orders,
            "history-trades": self.history_trades,
            "funds": [{"资金余额": "1000.00", "可用资金": "100.00", "总资产": "43054.60"}],
        }[kind]
        summary = dict(self.position_summary) if kind == "positions" else {}
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
            status="submit_confirmed",
            order_readback={
                "code": kwargs["code"].split(".", 1)[0],
                "side": kwargs["side"].lower(),
                "price": str(kwargs["price"]),
                "quantity": kwargs["quantity"],
                "field_mapping_proven": True,
                "submit_control_count": 1,
                "submitted": True,
                "saved": True,
                "started": True,
                "observed_at": OBSERVED_AT,
            },
        )

    def cancel_order(self, **kwargs) -> NativeAXReceipt:
        assert kwargs["explicitly_enabled"] is True
        self.cancel_calls += 1
        matches = [
            row for row in self.orders
            if row["委托编号"] == kwargs["order_id"]
        ]
        assert len(matches) == 1
        matches[0]["状态说明"] = "已撤"
        return self._receipt(
            status="cancel_confirmed",
            cancel_readback={
                "order_id": kwargs["order_id"],
                "code": kwargs["code"].split(".", 1)[0],
                "side": kwargs["side"].lower(),
                "price": str(kwargs["price"]),
                "quantity": kwargs["quantity"],
                "order_status": "未报",
                "target_match_count": 1,
                "selection_proven": True,
                "selection_proof_mode": "exact_order_tuple",
                "cancel_control_count": 1,
                "cancel_clicked": True,
                "confirmation_pressed": True,
                "confirmation_mode": "semantic_cancel_confirmation",
            },
        )

    def probe_cancel_selection(self, **kwargs) -> NativeAXReceipt:
        self.open_cancel_calls += 1
        self.surface = "query_only"
        matches = [
            row for row in self.orders
            if row["委托编号"] == kwargs["order_id"]
        ]
        assert len(matches) == 1
        row = matches[0]
        return self._receipt(
            status="cancel_selection_proven",
            cancel_readback={
                "order_id": kwargs["order_id"],
                "code": kwargs["code"].split(".", 1)[0],
                "side": kwargs["side"].lower(),
                "price": str(kwargs["price"]),
                "quantity": kwargs["quantity"],
                "order_status": row["状态说明"],
                "target_match_count": 1,
                "selection_proven": True,
                "selection_proof_mode": "exact_order_tuple",
                "cancel_control_count": 1,
                "cancel_clicked": False,
                "confirmation_pressed": False,
                "confirmation_mode": "none",
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


class LowConfidenceZeroFillNative(FakeNative):
    def __init__(self):
        super().__init__()
        self.low_headers = ["成交数量"]

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind != "today-orders":
            return super().read_query(kind=kind, **kwargs)
        self.query_calls.append(kind)
        return self._receipt(
            status="query_parse_unproven",
            query_readback={
                "kind": kind,
                "capture_proven": True,
                "parsing_proven": False,
                "critical_confidence_proven": False,
                "low_confidence_critical_headers": list(self.low_headers),
                "headers": [
                    "证券代码",
                    "委托时间",
                    "买卖标志",
                    "状态说明",
                    "委托价格",
                    "委托数量",
                    "委托编号",
                    "成交数量",
                ],
                "rows": [dict(row) for row in self.orders],
                "row_count": len(self.orders),
                "observed_at": OBSERVED_AT,
            },
        )


class BoundedBaselineStrictPostNative(LowConfidenceZeroFillNative):
    def __init__(self):
        super().__init__()
        self.order_query_reads = 0

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind != "today-orders":
            return super().read_query(kind=kind, **kwargs)
        self.order_query_reads += 1
        if self.order_query_reads <= 2:
            return LowConfidenceZeroFillNative.read_query(
                self,
                kind=kind,
                **kwargs,
            )
        return FakeNative.read_query(self, kind=kind, **kwargs)


class StrictBaselineBoundedPostNative(LowConfidenceZeroFillNative):
    def __init__(self):
        super().__init__()
        self.order_query_reads = 0

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind != "today-orders":
            return super().read_query(kind=kind, **kwargs)
        self.order_query_reads += 1
        if self.order_query_reads == 1:
            return FakeNative.read_query(self, kind=kind, **kwargs)
        return LowConfidenceZeroFillNative.read_query(
            self,
            kind=kind,
            **kwargs,
        )


class UnreconciledCancelNative(FakeNative):
    def cancel_order(self, **kwargs) -> NativeAXReceipt:
        receipt = super().cancel_order(**kwargs)
        matches = [
            row for row in self.orders
            if row["委托编号"] == kwargs["order_id"]
        ]
        assert len(matches) == 1
        matches[0]["状态说明"] = "未报"
        return receipt


class UnprovenConfirmationCancelNative(UnreconciledCancelNative):
    def cancel_order(self, **kwargs) -> NativeAXReceipt:
        receipt = super().cancel_order(**kwargs)
        receipt.payload["status"] = "cancel_confirmation_unproven"
        receipt.payload["cancel_readback"]["confirmation_pressed"] = False
        receipt.payload["cancel_readback"]["confirmation_mode"] = "none"
        return receipt


class MalformedSelectionCancelNative(UnprovenConfirmationCancelNative):
    def cancel_order(self, **kwargs) -> NativeAXReceipt:
        receipt = super().cancel_order(**kwargs)
        receipt.payload["cancel_readback"]["selection_proven"] = False
        receipt.payload["cancel_readback"]["selection_proof_mode"] = ""
        return receipt


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
    assert capability.supports_cancel is True
    assert capability.account_binding == "proven"
    assert capability.capabilities["opencli_used"] is False
    assert capability.capabilities["native_orders"] is True
    assert capability.capabilities["native_position_funds_summary"] is True
    assert capability.capabilities["native_funds_query"] is False
    assert capability.owned_position_shares == 100
    assert adapter.native.query_calls == [
        "positions",
        "today-orders",
        "today-trades",
    ]


def test_native_probe_accepts_reserved_cash_without_breaking_asset_identity() -> None:
    native = FakeNative()
    native.position_summary.update(
        {
            "资产": "43154.60",
            "余额": "100.00",
            "可用": "50.00",
            "可取": "40.00",
        }
    )

    capability = _adapter(native).probe(_plan())

    assert capability.ready is True
    assert capability.supports_submit is True
    assert capability.capabilities["native_position_funds_summary"] is True


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


def test_query_accepts_only_targeted_low_confidence_zero_fill_fallback() -> None:
    native = LowConfidenceZeroFillNative()
    native.orders[0]["成交数量"] = "0"
    adapter = _adapter(native)

    readback = adapter._query("today-orders")

    assert readback["bounded_order_readback_used"] is True
    assert readback["targeted_reread_used"] is True
    assert native.query_calls == ["today-orders", "today-orders"]


def test_low_confidence_nonzero_fill_remains_fail_closed() -> None:
    native = LowConfidenceZeroFillNative()
    native.orders[0]["成交数量"] = "10"

    with pytest.raises(FounderscNativeAXError, match="TODAY-ORDERS_UNPROVEN"):
        _adapter(native)._query("today-orders")


def test_exact_known_status_can_share_bounded_zero_fill_fallback() -> None:
    native = LowConfidenceZeroFillNative()
    native.low_headers = ["成交数量", "状态说明"]
    native.orders[0]["成交数量"] = "0"
    native.orders[0]["状态说明"] = "已撤"

    readback = _adapter(native)._query("today-orders")

    assert readback["bounded_order_readback_used"] is True
    assert set(readback["bounded_low_confidence_headers"]) == {"成交数量", "状态说明"}


def test_bounded_order_readback_is_exposed_in_reconcile_locator() -> None:
    native = LowConfidenceZeroFillNative()
    native.low_headers = ["成交数量", "状态说明"]
    native.orders[0]["成交数量"] = "0"
    native.orders[0]["状态说明"] = "已撤"
    sample = replace(
        _plan(),
        code="515120.XSHG",
        name="创新药",
        limit_price=0.646,
        basket_price=0.646,
    )

    receipt = _adapter(native)._reconcile_rows(
        sample,
        requested_shares=100,
        expected_order_id="6000002",
    )

    assert receipt.normalized_status() == BrokerStatus.CANCELLED
    assert receipt.locator_proof["order_readback_mode"] == (
        "bounded_known_status_zero_fill"
    )
    assert set(receipt.locator_proof["bounded_low_confidence_headers"]) == {
        "成交数量",
        "状态说明",
    }
    assert receipt.locator_proof["targeted_order_reread_used"] is True


def test_bounded_order_baseline_is_persisted_through_prepare_and_submit() -> None:
    native = LowConfidenceZeroFillNative()
    native.orders[0]["成交数量"] = "0"
    adapter = _adapter(native)
    plan = _plan()

    prepared = adapter.prepare(plan)
    submitted = adapter.submit(plan, "claim-bounded-baseline")

    assert prepared.normalized_status() == BrokerStatus.PREPARED
    assert prepared.locator_proof["baseline_order_readback_mode"] == (
        "bounded_known_status_zero_fill"
    )
    assert prepared.locator_proof["baseline_order_ids"] == ["6000002"]
    assert prepared.locator_proof["baseline_targeted_order_reread_used"] is True
    assert submitted.normalized_status() == BrokerStatus.ACCEPTED
    assert submitted.locator_proof["baseline_order_readback_mode"] == (
        "bounded_known_status_zero_fill"
    )
    assert submitted.locator_proof["order_readback_mode"] == (
        "bounded_known_status_zero_fill"
    )
    assert submitted.locator_proof["baseline_order_ids"] == ["6000002"]
    assert submitted.locator_proof["baseline_order_count"] == 1


@pytest.mark.parametrize(
    ("native_type", "baseline_mode", "post_mode"),
    [
        (
            BoundedBaselineStrictPostNative,
            "bounded_known_status_zero_fill",
            "strict_confidence",
        ),
        (
            StrictBaselineBoundedPostNative,
            "strict_confidence",
            "bounded_known_status_zero_fill",
        ),
    ],
)
def test_submit_keeps_baseline_and_post_readback_modes_separate(
    native_type: type[FakeNative],
    baseline_mode: str,
    post_mode: str,
) -> None:
    native = native_type()
    native.orders[0]["成交数量"] = "0"
    adapter = _adapter(native)
    plan = _plan()

    prepared = adapter.prepare(plan)
    submitted = adapter.submit(plan, "claim-phase-separated")

    assert prepared.normalized_status() == BrokerStatus.PREPARED
    assert submitted.normalized_status() == BrokerStatus.ACCEPTED
    assert submitted.locator_proof["baseline_order_readback_mode"] == baseline_mode
    assert submitted.locator_proof["order_readback_mode"] == post_mode
    assert submitted.locator_proof["baseline_order_ids"] == ["6000002"]


def test_unknown_low_confidence_status_remains_fail_closed() -> None:
    native = LowConfidenceZeroFillNative()
    native.low_headers = ["成交数量", "状态说明"]
    native.orders[0]["成交数量"] = "0"
    native.orders[0]["状态说明"] = "撤单失败"

    with pytest.raises(FounderscNativeAXError, match="TODAY-ORDERS_UNPROVEN"):
        _adapter(native)._query("today-orders")


def test_bounded_zero_fill_requires_independent_trade_crosscheck() -> None:
    native = LowConfidenceZeroFillNative()
    native.orders[0]["成交数量"] = "0"
    native.trades.append(
        {
            "证券代码": "515120",
            "证券名称": "创新药",
            "成交时间": "092001",
            "买卖标志": "买入",
            "成交价格": "0.6460",
            "成交数量": "100",
            "成交金额": "64.60",
            "成交编号": "7000001",
            "委托编号": "6000002",
        }
    )
    sample = replace(
        _plan(),
        code="515120.XSHG",
        name="创新药",
        limit_price=0.646,
        basket_price=0.646,
    )

    with pytest.raises(
        FounderscNativeAXError,
        match="ZERO_FILL_CROSSCHECK_FAILED",
    ):
        _adapter(native)._reconcile_rows(
            sample,
            requested_shares=100,
            expected_order_id="6000002",
        )


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


def test_native_prepare_persists_baseline_for_unknown_submit_recovery() -> None:
    native = FakeNative()
    adapter = _adapter(native)
    plan = _plan()

    prepared = adapter.prepare(plan)
    native.orders.append(
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托时间": "092001",
            "买卖标志": "买入",
            "委托类别": "委托",
            "状态说明": "已撤",
            "委托价格": "10.0000",
            "委托数量": "100",
            "委托编号": "6000003",
            "成交价格": "0.000",
            "成交数量": "",
            "报价方式": "买卖",
            "股东代码": "A***",
            "备注": "",
        }
    )

    recovered = adapter.recover(
        plan,
        {
            "requested_shares": 100,
            "submit_chain_uncertain": True,
            "submit_claim_id": "claim-1",
            "locator_proof": prepared.locator_proof,
        },
    )

    assert prepared.locator_proof["baseline_order_ids"] == ["6000002"]
    assert recovered.normalized_status() == BrokerStatus.CANCELLED
    assert recovered.order_id == "6000003"
    assert recovered.strategy_id == "NAX448444379404E09E"
    assert recovered.receipt_mapping is True
    assert recovered.locator_proof["baseline_order_readback_mode"] == (
        "strict_confidence"
    )
    assert recovered.locator_proof["order_readback_mode"] == "strict_confidence"
    assert recovered.locator_proof["recovery_mode"] == "durable_exact_order_delta"


def test_recovery_keeps_bounded_baseline_separate_from_strict_readback() -> None:
    native = BoundedBaselineStrictPostNative()
    native.orders[0]["成交数量"] = "0"
    adapter = _adapter(native)
    plan = _plan()
    prepared = adapter.prepare(plan)
    native.orders.append(
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托时间": "092001",
            "买卖标志": "买入",
            "委托类别": "委托",
            "状态说明": "已撤",
            "委托价格": "10.0000",
            "委托数量": "100",
            "委托编号": "6000003",
            "成交价格": "0.000",
            "成交数量": "",
            "报价方式": "买卖",
            "股东代码": "A***",
            "备注": "",
        }
    )

    recovered = adapter.recover(
        plan,
        {
            "requested_shares": 100,
            "submit_chain_uncertain": True,
            "submit_claim_id": "claim-bounded-recovery",
            "locator_proof": prepared.locator_proof,
        },
    )

    assert recovered.normalized_status() == BrokerStatus.CANCELLED
    assert recovered.locator_proof["baseline_order_readback_mode"] == (
        "bounded_known_status_zero_fill"
    )
    assert recovered.locator_proof["order_readback_mode"] == "strict_confidence"
    assert recovered.locator_proof["recovery_mode"] == "durable_exact_order_delta"


def test_native_unknown_recovery_without_durable_baseline_fails_closed() -> None:
    adapter = _adapter()

    recovered = adapter.recover(
        _plan(),
        {
            "requested_shares": 100,
            "submit_chain_uncertain": True,
            "submit_claim_id": "claim-1",
            "locator_proof": {},
        },
    )

    assert recovered.normalized_status() == BrokerStatus.UNKNOWN
    assert recovered.conclusive is False
    assert recovered.reason == "NATIVE_RECOVERY_DURABLE_CONTEXT_UNPROVEN"


def test_native_unknown_recovery_accepts_a_proven_empty_baseline() -> None:
    native = FakeNative()
    native.orders = []
    adapter = _adapter(native)
    plan = _plan()

    prepared = adapter.prepare(plan)
    native.orders.append(
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托时间": "092001",
            "买卖标志": "买入",
            "委托类别": "委托",
            "状态说明": "未报",
            "委托价格": "10.0000",
            "委托数量": "100",
            "委托编号": "6000003",
            "成交价格": "0.000",
            "成交数量": "",
            "报价方式": "买卖",
            "股东代码": "A***",
            "备注": "",
        }
    )

    recovered = adapter.recover(
        plan,
        {
            "requested_shares": 100,
            "submit_chain_uncertain": True,
            "submit_claim_id": "claim-empty-baseline",
            "locator_proof": prepared.locator_proof,
        },
    )

    assert prepared.locator_proof["baseline_order_ids"] == []
    assert prepared.locator_proof["baseline_order_count"] == 0
    assert recovered.normalized_status() == BrokerStatus.ACCEPTED
    assert recovered.order_id == "6000003"
    assert recovered.receipt_mapping is True


def test_native_cancel_uses_exact_order_id_once_and_reconciles() -> None:
    native = FakeNative()
    adapter = _adapter(native)
    plan = _plan()
    adapter.prepare(plan)
    submitted = adapter.submit(plan, "claim-1")

    cancelled = adapter.cancel(
        plan,
        {
            "broker_order_id": submitted.order_id,
            "broker_strategy_id": submitted.strategy_id,
            "requested_shares": 100,
        },
    )

    assert cancelled.normalized_status() == BrokerStatus.CANCELLED
    assert cancelled.order_id == "6000003"
    assert cancelled.filled_shares == 0
    assert cancelled.retry_allowed is False
    assert cancelled.field_readback["cancel_clicked"] is True
    assert cancelled.locator_proof["cancel_clicked"] is True
    assert cancelled.locator_proof["cancel_click_proven"] is True
    assert cancelled.locator_proof["cancel_helper_status"] == "cancel_confirmed"
    assert (
        cancelled.locator_proof["cancel_selection_proof_mode"]
        == "exact_order_tuple"
    )
    assert native.cancel_calls == 1

    idempotent = adapter.cancel(
        plan,
        {
            "broker_order_id": submitted.order_id,
            "broker_strategy_id": submitted.strategy_id,
            "requested_shares": 100,
        },
    )
    assert idempotent.normalized_status() == BrokerStatus.CANCELLED
    assert native.cancel_calls == 1


def test_native_cancel_probe_leaves_exact_active_order_on_cancel_surface() -> None:
    native = FakeNative()
    adapter = _adapter(native)
    plan = _plan()
    adapter.prepare(plan)
    submitted = adapter.submit(plan, "claim-1")
    previous = {
        "broker_order_id": submitted.order_id,
        "broker_strategy_id": submitted.strategy_id,
        "requested_shares": 100,
    }
    order_surface_calls = native.open_order_calls

    capability = adapter.probe_cancel(plan, previous)
    cancelled = adapter.cancel(plan, previous)

    assert capability.ready is True
    assert capability.supports_submit is False
    assert capability.supports_cancel is True
    assert native.open_order_calls == order_surface_calls
    assert native.open_cancel_calls == 1
    assert native.cancel_calls == 1
    assert cancelled.normalized_status() == BrokerStatus.CANCELLED


def test_native_cancel_probe_allows_one_unlock_recovery() -> None:
    native = FakeNative(
        status="authentication_required",
        surface_state="authentication_required",
    )
    native.orders = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托时间": "095624",
            "买卖标志": "买入",
            "委托类别": "委托",
            "状态说明": "已报",
            "委托价格": "10.0000",
            "委托数量": "100",
            "委托编号": "6005551",
            "成交价格": "0.000",
            "成交数量": "",
            "报价方式": "买卖",
            "股东代码": "A***",
            "备注": "",
        }
    ]
    adapter = _adapter(native)

    capability = adapter.probe_cancel(
        _plan(),
        {"broker_order_id": "6005551", "requested_shares": 100},
    )

    assert capability.ready is True
    assert capability.supports_cancel is True
    assert native.unlock_calls == 1


def test_native_reconcile_treats_cancel_transaction_as_zero_fill_event() -> None:
    native = FakeNative()
    native.orders = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托时间": "095624",
            "买卖标志": "买入",
            "委托类别": "委托",
            "状态说明": "已撤",
            "委托价格": "10.0000",
            "委托数量": "100",
            "委托编号": "6005551",
            "成交价格": "0.000",
            "成交数量": "",
            "报价方式": "买卖",
            "股东代码": "A***",
            "备注": "",
        }
    ]
    native.trades = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "成交时间": "103302",
            "买卖标志": "买入",
            "成交价格": "0.000",
            "成交数量": "100.00",
            "成交金额": "0.00",
            "成交编号": "",
            "委托编号": "6006576",
            "股东代码": "A***",
            "成交类型": "撤单",
            "状态说明": "成交",
        }
    ]

    receipt = _adapter(native)._reconcile_rows(
        _plan(),
        requested_shares=100,
        expected_order_id="6005551",
    )

    assert receipt.normalized_status() == BrokerStatus.CANCELLED
    assert receipt.filled_shares == 0
    assert receipt.locator_proof["trade_match_count"] == 0


def test_unknown_cancel_keeps_click_and_selection_evidence_without_retry() -> None:
    native = UnreconciledCancelNative()
    adapter = _adapter(native)
    plan = _plan()
    adapter.prepare(plan)
    submitted = adapter.submit(plan, "claim-1")

    unresolved = adapter.cancel(
        plan,
        {
            "broker_order_id": submitted.order_id,
            "broker_strategy_id": submitted.strategy_id,
            "requested_shares": 100,
        },
    )

    assert unresolved.normalized_status() == BrokerStatus.UNKNOWN
    assert unresolved.retry_allowed is False
    assert unresolved.locator_proof["cancel_clicked"] is True
    assert unresolved.locator_proof["cancel_click_proven"] is True
    assert unresolved.locator_proof["cancel_helper_status"] == "cancel_confirmed"
    assert (
        unresolved.locator_proof["cancel_selection_proof_mode"]
        == "exact_order_tuple"
    )
    assert native.cancel_calls == 1


def test_unproven_cancel_confirmation_preserves_proven_click_fact() -> None:
    native = UnprovenConfirmationCancelNative()
    adapter = _adapter(native)
    plan = _plan()
    adapter.prepare(plan)
    submitted = adapter.submit(plan, "claim-1")

    unresolved = adapter.cancel(
        plan,
        {
            "broker_order_id": submitted.order_id,
            "broker_strategy_id": submitted.strategy_id,
            "requested_shares": 100,
        },
    )

    assert unresolved.normalized_status() == BrokerStatus.UNKNOWN
    assert unresolved.retry_allowed is False
    assert unresolved.locator_proof["cancel_helper_status"] == (
        "cancel_confirmation_unproven"
    )
    assert unresolved.locator_proof["cancel_clicked"] is True
    assert unresolved.locator_proof["cancel_click_proven"] is True
    assert unresolved.locator_proof["cancel_confirmation_pressed"] is False
    assert unresolved.field_readback["cancel_clicked"] is True
    assert native.cancel_calls == 1


def test_malformed_cancel_receipt_keeps_reported_click_but_not_proof() -> None:
    native = MalformedSelectionCancelNative()
    adapter = _adapter(native)
    plan = _plan()
    adapter.prepare(plan)
    submitted = adapter.submit(plan, "claim-1")

    unresolved = adapter.cancel(
        plan,
        {
            "broker_order_id": submitted.order_id,
            "broker_strategy_id": submitted.strategy_id,
            "requested_shares": 100,
        },
    )

    assert unresolved.normalized_status() == BrokerStatus.UNKNOWN
    assert unresolved.retry_allowed is False
    assert unresolved.locator_proof["cancel_clicked"] is True
    assert unresolved.locator_proof["cancel_click_proven"] is False
    assert unresolved.field_readback["cancel_clicked"] is True
    assert native.cancel_calls == 1


def test_side_ocr_typo_fails_closed_instead_of_authorizing_order_match() -> None:
    native = FakeNative()
    native.orders[0]["买卖标志"] = "头入"
    adapter = _adapter(native)
    sample = replace(
        _plan(),
        code="515120.XSHG",
        name="创新药",
        limit_price=0.646,
        basket_price=0.646,
    )

    with pytest.raises(FounderscNativeAXError, match="SIDE_MALFORMED"):
        adapter._reconcile_rows(
            sample,
            requested_shares=100,
            expected_order_id="6000002",
        )


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


def test_prior_day_native_history_does_not_infer_terminal_from_accepted() -> None:
    native = FakeNative()
    native.positions = [row for row in native.positions if row["证券代码"] != "000001"]
    native.history_orders = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托日期": "20260830",
            "委托时间": "145040",
            "买卖标志": "买入",
            "委托类别": "买卖",
            "状态说明": "已报",
            "委托价格": "10.00000000",
            "委托数量": "100.00",
            "委托编号": "6001324",
            "成交价格": "0.00000000",
            "成交数量": "0.00",
        }
    ]

    receipt = _adapter(native).reconcile(
        _plan(),
        {"broker_order_id": "6001324", "requested_shares": 100},
    )

    assert receipt.normalized_status() == BrokerStatus.UNKNOWN
    assert receipt.reason == "NATIVE_HISTORICAL_STATUS_UNPROVEN"
    assert receipt.order_id == "6001324"
    assert receipt.receipt_mapping is False
    assert receipt.conclusive is False
    assert receipt.active is False
    assert receipt.filled_shares == 0
    assert receipt.locator_proof["native_order_id"] == "6001324"
    assert receipt.locator_proof["order_id_mapping"] == "exact"
    assert receipt.locator_proof["exact_order_match_count"] == 1
    assert receipt.locator_proof["exact_trade_match_count"] == 0
    assert receipt.locator_proof["target_holding_shares"] == 0
    assert native.query_calls == ["history-orders", "history-trades", "positions"]


def test_prior_day_native_history_accepts_explicit_exact_cancel_terminal() -> None:
    native = FakeNative()
    native.positions = [
        row for row in native.positions if row["证券代码"] != "000001"
    ]
    native.history_orders = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托日期": "20260830",
            "委托时间": "145040",
            "买卖标志": "买入",
            "委托类别": "买卖",
            "状态说明": "已撤",
            "委托价格": "10.00000000",
            "委托数量": "100.00",
            "委托编号": "6001324",
            "成交价格": "0.00000000",
            "成交数量": "0.00",
        }
    ]

    receipt = _adapter(native).reconcile(
        _plan(),
        {"broker_order_id": "6001324", "requested_shares": 100},
    )

    assert receipt.normalized_status() == BrokerStatus.CANCELLED
    assert receipt.reason == "native_historical_order_and_trade_readback"
    assert receipt.receipt_mapping is True
    assert receipt.conclusive is True
    assert receipt.filled_shares == 0


def test_prior_day_native_history_rejects_cross_order_tuple_match() -> None:
    native = FakeNative()
    native.positions = [
        row for row in native.positions if row["证券代码"] != "000001"
    ]
    native.history_orders = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托日期": "20260830",
            "委托时间": "145040",
            "买卖标志": "买入",
            "委托类别": "买卖",
            "状态说明": "已报",
            "委托价格": "10.00000000",
            "委托数量": "100.00",
            "委托编号": "6001324",
            "成交价格": "0.00000000",
            "成交数量": "0.00",
        }
    ]

    receipt = _adapter(native).reconcile(
        _plan(),
        {"broker_order_id": "6009999", "requested_shares": 100},
    )

    assert receipt.normalized_status() == BrokerStatus.UNKNOWN
    assert receipt.reason == "NATIVE_HISTORICAL_ORDER_ID_MISMATCH"
    assert receipt.order_id == "6009999"
    assert receipt.receipt_mapping is False
    assert receipt.conclusive is False
    assert receipt.locator_proof["native_order_id"] == "6001324"
    assert receipt.locator_proof["order_id_mapping"] == "mismatch"


def test_prior_day_native_history_wrong_date_remains_unknown() -> None:
    native = FakeNative()
    native.positions = []
    native.history_orders = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托日期": "20260829",
            "委托时间": "145040",
            "买卖标志": "买入",
            "委托类别": "买卖",
            "状态说明": "已报",
            "委托价格": "10.00000000",
            "委托数量": "100.00",
            "委托编号": "6001324",
            "成交价格": "0.00000000",
            "成交数量": "0.00",
        }
    ]

    receipt = _adapter(native).reconcile(
        _plan(),
        {"broker_order_id": "external-order-1", "requested_shares": 100},
    )

    assert receipt.normalized_status() == BrokerStatus.UNKNOWN
    assert receipt.conclusive is False
    assert receipt.receipt_mapping is False
    assert receipt.locator_proof["exact_order_match_count"] == 0


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


def test_bounded_preexisting_order_rejection_keeps_baseline_locator() -> None:
    native = LowConfidenceZeroFillNative()
    native.orders[0]["成交数量"] = "0"
    sample = replace(
        _plan(),
        plan_id="sample-515120",
        code="515120.XSHG",
        name="创新药",
        limit_price=0.646,
        basket_price=0.646,
    )

    receipt = _adapter(native).prepare(sample)

    assert receipt.normalized_status() == BrokerStatus.REJECTED
    assert receipt.reason == "NATIVE_PREEXISTING_EXACT_ORDER_BLOCKS_SUBMIT"
    assert receipt.locator_proof["baseline_order_readback_mode"] == (
        "bounded_known_status_zero_fill"
    )
    assert receipt.locator_proof["baseline_order_ids"] == ["6000002"]
    assert receipt.locator_proof["baseline_exact_order_match_count"] == 1
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


def test_cancel_failure_text_is_not_misclassified_as_cancelled() -> None:
    native = FakeNative()
    native.orders[0]["状态说明"] = "撤单失败"
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
