from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from xiaocao.live.foundersc_native_ax import FounderscNativeAXError, NativeAXReceipt
from xiaocao.live.foundersc_native_broker import (
    FounderscNativeAXBrokerAdapter,
    _decimal,
    _integer,
)
from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account
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


def test_native_numeric_normalization_distinguishes_decimal_comma_and_grouping(
) -> None:
    assert _decimal("17,3900", field="ORDER_PRICE") == Decimal("17.3900")
    assert _decimal("54,528.94", field="TOTAL_ASSETS") == Decimal("54528.94")
    assert _decimal("54.528,94", field="TOTAL_ASSETS") == Decimal("54528.94")
    assert _integer("1,100", field="ORDER_QUANTITY") == 1100
    assert _integer("800,00", field="ORDER_QUANTITY") == 800


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


class TransientAccountInvariantNative(FakeNative):
    def __init__(self):
        super().__init__()
        self.transient_position_reads = 0

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        receipt = super().read_query(kind=kind, **kwargs)
        if kind == "positions" and self.transient_position_reads == 0:
            self.transient_position_reads += 1
            receipt.payload["query_readback"]["summary_values"]["余额"] = "0.01"
        return receipt


class StickyQuerySurfaceNative(FakeNative):
    """Positions OCR stays unproven until read-only navigation resets the surface."""

    def __init__(self):
        super().__init__()
        self.surface = "query_only"
        self.query_surface_needs_reset = True

    def open_order_surface(self, *, side: str, **kwargs) -> NativeAXReceipt:
        receipt = super().open_order_surface(side=side, **kwargs)
        self.query_surface_needs_reset = False
        return receipt

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind == "positions" and self.query_surface_needs_reset:
            self.query_calls.append(kind)
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


class MidSnapshotTradeLockNative(StickyQuerySurfaceNative):
    """The normal five-minute trade lock appears after snapshot reading starts."""

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        receipt = super().read_query(kind=kind, **kwargs)
        if kind == "positions" and self.query_surface_needs_reset:
            self.surface = "authentication_required"
        return receipt

    def open_order_surface(self, *, side: str, **kwargs) -> NativeAXReceipt:
        if self.surface == "authentication_required":
            return self._receipt(status="order_surface_authentication_required")
        return super().open_order_surface(side=side, **kwargs)


class UnprovenSurfaceResetNative(FakeNative):
    """A reset OCR miss must not discard the remaining whole-snapshot read."""

    def __init__(self):
        super().__init__()
        self.surface = "query_only"
        self.position_reads = 0

    def open_order_surface(self, *, side: str, **kwargs) -> NativeAXReceipt:
        return self._receipt(status="order_navigation_capture_unproven")

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind == "positions":
            self.position_reads += 1
            if self.position_reads <= 2:
                self.query_calls.append(kind)
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


class PopupOrderIdBeforeTableRefreshNative(FakeNative):
    """Broker confirms one order id before the today-orders grid refreshes."""

    def submit_prepared_order(self, **kwargs) -> NativeAXReceipt:
        assert kwargs["explicitly_enabled"] is True
        self.submit_calls += 1
        return self._receipt(
            status="submit_confirmed",
            action={
                "attempted": True,
                "succeeded": True,
                "requires_user_input": False,
                "confirm_pressed": True,
                "confirmation_mode": "focused_dialog_button",
                "unlock_path_proven": False,
            },
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
            result_readback={
                "kind": "submit",
                "status": "submit_result_acknowledged",
                "broker_order_id": "6000099",
                "message_matched": True,
                "acknowledgment_pressed": True,
                "acknowledgment_mode": "focused_dialog_button",
                "observed_at": OBSERVED_AT,
            },
        )


class DelayedPopupOrderNative(PopupOrderIdBeforeTableRefreshNative):
    def __init__(self):
        super().__init__()
        self.post_submit_order_reads = 0

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind == "today-orders" and self.submit_calls:
            self.post_submit_order_reads += 1
            if self.post_submit_order_reads == 3:
                self.orders.append(
                    {
                        "证券代码": "000001",
                        "证券名称": "测试标的",
                        "委托时间": "93018",
                        "买卖标志": "买入",
                        "委托类别": "委托",
                        "状态说明": "已报",
                        "委托价格": "10,0000",
                        "委托数量": "100",
                        "委托编号": "6000099",
                        "成交价格": "0.000",
                        "成交数量": "",
                        "报价方式": "买卖",
                        "股东代码": "A***",
                        "备注": "",
                    }
                )
        return super().read_query(kind=kind, **kwargs)


class DelayedRecoveryOrderNative(FakeNative):
    """A restarted process sees the claimed order only after grid refresh."""

    def __init__(self):
        super().__init__()
        self.recovery_order_reads = 0

    def read_query(self, *, kind: str, **kwargs) -> NativeAXReceipt:
        if kind == "today-orders":
            self.recovery_order_reads += 1
            if self.recovery_order_reads == 3:
                self.orders.append(
                    {
                        "证券代码": "000001",
                        "证券名称": "测试标的",
                        "委托时间": "93018",
                        "买卖标志": "买入",
                        "委托类别": "委托",
                        "状态说明": "已报",
                        "委托价格": "10,0000",
                        "委托数量": "100",
                        "委托编号": "6000099",
                        "成交价格": "0.000",
                        "成交数量": "",
                        "报价方式": "买卖",
                        "股东代码": "A***",
                        "备注": "",
                    }
                )
        return super().read_query(kind=kind, **kwargs)


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
        snapshot_read_delays=(0.0,),
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


def test_submit_unknown_retains_popup_order_id_and_native_action_evidence() -> None:
    native = PopupOrderIdBeforeTableRefreshNative()
    adapter = _adapter(native)

    prepared = adapter.prepare(_plan())
    submitted = adapter.submit(_plan(), "claim-popup-order-id")

    assert prepared.normalized_status() == BrokerStatus.PREPARED
    assert submitted.normalized_status() == BrokerStatus.UNKNOWN
    assert submitted.receipt_mapping is False
    assert submitted.order_id == "6000099"
    assert submitted.field_readback["native_helper_status"] == "submit_confirmed"
    assert submitted.field_readback["native_action"]["confirm_pressed"] is True
    assert (
        submitted.field_readback["native_result_readback"]["broker_order_id"]
        == "6000099"
    )
    assert submitted.locator_proof["native_helper_status"] == "submit_confirmed"
    assert submitted.locator_proof["native_action"]["confirm_pressed"] is True
    assert (
        submitted.locator_proof["native_result_readback"]["broker_order_id"]
        == "6000099"
    )
    assert native.submit_calls == 1


def test_unknown_submit_recovery_accepts_founder_decimal_comma_price() -> None:
    native = FakeNative()
    native.orders = [
        {
            "证券代码": "603029",
            "证券名称": "天鹅股份",
            "委托时间": "93018",
            "买卖标志": "买入",
            "委托类别": "委托",
            "状态说明": "已成",
            "委托价格": "17,3900",
            "委托数量": "800",
            "委托编号": "6000356",
            "成交价格": "17.060",
            "成交数量": "800",
            "报价方式": "买卖",
            "股东代码": "A***",
            "备注": "",
        }
    ]
    native.trades = [
        {
            "证券代码": "603029",
            "证券名称": "天鹅股份",
            "成交时间": "93042",
            "买卖标志": "买入",
            "成交价格": "17.060",
            "成交数量": "800.00",
            "成交金额": "13648.00",
            "成交编号": "1560943",
            "委托编号": "6000356",
            "股东代码": "A***",
            "成交类型": "买卖",
            "状态说明": "成交",
        }
    ]
    plan = replace(
        _plan(),
        plan_id="book-b:2026-09-02:603029.XSHG:BUY",
        trade_date="2026-09-02",
        code="603029.XSHG",
        name="天鹅股份",
        shares=800,
        limit_price=17.39,
        basket_price=17.6683,
    )

    recovered = _adapter(native).recover(
        plan,
        {
            "requested_shares": 800,
            "submit_chain_uncertain": True,
            "submit_claim_id": "claim-603029",
            "locator_proof": {
                "baseline_order_ids": [],
                "baseline_order_count": 0,
                "baseline_observed_at": OBSERVED_AT,
                "baseline_order_readback_mode": "strict_confidence",
            },
        },
    )

    assert recovered.normalized_status() == BrokerStatus.FILLED
    assert recovered.order_id == "6000356"
    assert recovered.filled_shares == 800
    assert recovered.fill_price == 17.06
    assert recovered.receipt_mapping is True
    assert recovered.locator_proof["recovery_mode"] == (
        "durable_exact_order_delta"
    )


def test_submit_self_heals_delayed_order_grid_without_second_submit() -> None:
    native = DelayedPopupOrderNative()
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0, 0.0, 0.0),
    )

    prepared = adapter.prepare(_plan())
    submitted = adapter.submit(_plan(), "claim-delayed-order-grid")

    assert prepared.normalized_status() == BrokerStatus.PREPARED
    assert submitted.normalized_status() == BrokerStatus.ACCEPTED
    assert submitted.order_id == "6000099"
    assert submitted.receipt_mapping is True
    assert submitted.locator_proof["observed_order_row_count"] == 2
    assert submitted.locator_proof["exact_order_match_count"] == 1
    assert native.submit_calls == 1
    assert native.post_submit_order_reads == 3


def test_unknown_recovery_self_heals_delayed_grid_without_submit() -> None:
    native = DelayedRecoveryOrderNative()
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0, 0.0, 0.0),
    )

    recovered = adapter.recover(
        _plan(),
        {
            "requested_shares": 100,
            "submit_chain_uncertain": True,
            "submit_claim_id": "claim-delayed-recovery",
            "broker_order_id": "6000099",
            "locator_proof": {
                "baseline_order_ids": [],
                "baseline_order_count": 0,
                "baseline_observed_at": OBSERVED_AT,
                "baseline_order_readback_mode": "strict_confidence",
            },
        },
    )

    assert recovered.normalized_status() == BrokerStatus.ACCEPTED
    assert recovered.order_id == "6000099"
    assert recovered.receipt_mapping is True
    assert recovered.locator_proof["recovery_read_attempts"] == 3
    assert recovered.locator_proof["recovery_expected_order_id"] == "6000099"
    assert recovered.locator_proof["recovery_actions"] == "native_readback_only"
    assert native.recovery_order_reads == 3
    assert native.submit_calls == 0


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


def test_reconcile_exposes_exact_multi_price_trade_notional() -> None:
    native = FakeNative()
    native.orders.append(
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "委托时间": "103302",
            "买卖标志": "买入",
            "委托类别": "委托",
            "状态说明": "已成",
            "委托价格": "10.0000",
            "委托数量": "700",
            "委托编号": "6007001",
            "成交价格": "10.015714",
            "成交数量": "700",
            "报价方式": "买卖",
            "股东代码": "A***",
            "备注": "",
        }
    )
    native.trades = [
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "成交时间": "103301",
            "买卖标志": "买入",
            "成交价格": "9.99",
            "成交数量": "100",
            "成交金额": "999.00",
            "成交编号": "7007001",
            "委托编号": "6007001",
            "股东代码": "A***",
            "成交类型": "成交",
            "状态说明": "成交",
        },
        {
            "证券代码": "000001",
            "证券名称": "测试标的",
            "成交时间": "103302",
            "买卖标志": "买入",
            "成交价格": "10.02",
            "成交数量": "600",
            "成交金额": "6012.00",
            "成交编号": "7007002",
            "委托编号": "6007001",
            "股东代码": "A***",
            "成交类型": "成交",
            "状态说明": "成交",
        },
    ]

    receipt = _adapter(native)._reconcile_rows(
        replace(_plan(), shares=700),
        requested_shares=700,
        expected_order_id="6007001",
    )

    assert receipt.normalized_status() == BrokerStatus.FILLED
    assert receipt.filled_shares == 700
    assert receipt.locator_proof[
        "current_order_cumulative_fill_notional"
    ] == "7011.00"


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


def test_native_allocation_uses_cash_balance_and_hashes_all_five_fund_fields() -> None:
    native = FakeNative()
    native.position_summary.update(
        {
            "资产": "43154.60",
            "股票市值": "43054.60",
            "余额": "100.00",
            "可用": "50.00",
            "可取": "40.00",
        }
    )
    adapter = _adapter(native)
    now = datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00"))

    first = adapter.read_live_allocation_facts(
        trade_date="2026-08-30",
        settled_nav=100000,
        current_open_exposure=40000,
        capital_basis_source="initial_book_b_capital",
        expected_fund_account_fingerprint="123******890",
        now=now,
    )

    assert first["available_cash"] == 50.0
    assert first["cash_balance"] == 100.0
    assert first["withdrawable_cash"] == 40.0
    assert first["broker_receipt"]["allocation_summary"]["values"] == {
        "总资产": 43154.6,
        "证券市值": 43054.6,
        "资金余额": 100.0,
        "可用资金": 50.0,
        "可取资金": 40.0,
    }

    native.position_summary["可用"] = "45.00"
    second = adapter.read_live_allocation_facts(
        trade_date="2026-08-30",
        settled_nav=100000,
        current_open_exposure=40000,
        capital_basis_source="initial_book_b_capital",
        expected_fund_account_fingerprint="123******890",
        now=now,
    )

    assert second["broker_receipt_sha256"] != first["broker_receipt_sha256"]
    assert second["allocation_capsule_sha256"] != first["allocation_capsule_sha256"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("可用", "100.01", "AVAILABLE_EXCEEDS_BALANCE"),
        ("可取", "50.01", "WITHDRAWABLE_EXCEEDS_AVAILABLE"),
    ],
)
def test_native_allocation_rejects_invalid_cash_ordering(
    field: str,
    value: str,
    reason: str,
) -> None:
    native = FakeNative()
    native.position_summary.update(
        {
            "资产": "43154.60",
            "股票市值": "43054.60",
            "余额": "100.00",
            "可用": "50.00",
            "可取": "40.00",
            field: value,
        }
    )

    with pytest.raises(FounderscNativeAXError, match=reason):
        _adapter(native).read_live_allocation_facts(
            trade_date="2026-08-30",
            settled_nav=100000,
            current_open_exposure=40000,
            capital_basis_source="initial_book_b_capital",
            expected_fund_account_fingerprint="123******890",
            now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
        )


def test_native_allocation_rejects_one_cent_asset_equation_drift() -> None:
    native = FakeNative()
    native.position_summary.update(
        {
            "资产": "43154.61",
            "股票市值": "43054.60",
            "余额": "100.00",
            "可用": "50.00",
            "可取": "40.00",
        }
    )

    with pytest.raises(FounderscNativeAXError, match="ASSET_EQUATION_FAILED"):
        _adapter(native).read_live_allocation_facts(
            trade_date="2026-08-30",
            settled_nav=100000,
            current_open_exposure=40000,
            capital_basis_source="initial_book_b_capital",
            expected_fund_account_fingerprint="123******890",
            now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
        )


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


def test_native_allocation_accepts_hash_bound_rolling_book_b_nav() -> None:
    adapter = _adapter()
    facts = adapter.read_live_allocation_facts(
        trade_date="2026-08-30",
        settled_nav=30_123.45,
        current_open_exposure=1_000,
        capital_basis_source="broker_reconciled_book_b_nav",
        capital_basis_receipt_sha256="c" * 64,
        expected_fund_account_fingerprint="123******890",
        now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
    )

    assert facts["capital_basis_source"] == "broker_reconciled_book_b_nav"
    assert facts["capital_basis_receipt_sha256"] == "c" * 64


def test_native_live_account_snapshot_reads_three_tables_and_position_funds(
    tmp_path: Path,
) -> None:
    native = FakeNative()
    adapter = _adapter(native)
    now = datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00"))

    snapshot = adapter.read_live_account_snapshot(
        trade_date="2026-08-30",
        expected_fund_account_fingerprint="123******890",
        now=now,
    )

    assert snapshot["status"] == "account_snapshot_reconciled"
    assert snapshot["source"] == "foundersc_native_app"
    assert set(snapshot["tables"]) == {
        "positions", "today-orders", "today-trades"
    }
    assert snapshot["funds_summary"] == {
        "source": "positions_summary",
        "total_assets": 43054.6,
        "securities_market_value": 43054.6,
        "available_cash": 0.0,
        "cash_balance": 0.0,
        "withdrawable_cash": 0.0,
    }
    assert native.query_calls[-3:] == [
        "positions", "today-orders", "today-trades"
    ]
    payload = dict(snapshot)
    claimed = payload.pop("snapshot_sha256")
    assert claimed == hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    account = project_book_b_live_account(
        tmp_path,
        snapshot,
        trade_date="2026-08-30",
        now=now,
    )
    assert account.settled_nav == 30_000
    assert account.current_open_exposure == 0
    assert account.lots == ()


def test_native_live_account_snapshot_recovers_transient_asset_drift_read_only(
) -> None:
    native = TransientAccountInvariantNative()
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0,),
        snapshot_read_delays=(0.0, 0.0),
    )

    snapshot = adapter.read_live_account_snapshot(
        trade_date="2026-08-30",
        expected_fund_account_fingerprint="123******890",
        now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
    )

    assert snapshot["read_recovery"] == {
        "actions": "native_readback_only",
        "attempts": 2,
        "failure_codes": ["LIVE_ACCOUNT_SNAPSHOT_ASSET_EQUATION_FAILED"],
        "recovered": True,
        "surface_resets": 1,
    }
    assert native.query_calls == [
        "positions", "today-orders", "today-trades",
        "positions", "today-orders", "today-trades",
    ]
    assert native.prepare_calls == 0
    assert native.submit_calls == 0
    assert native.cancel_calls == 0
    assert native.open_order_calls == 1


def test_native_live_account_snapshot_resets_sticky_query_surface_read_only(
) -> None:
    native = StickyQuerySurfaceNative()
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0,),
        snapshot_read_delays=(0.0, 0.0),
    )

    snapshot = adapter.read_live_account_snapshot(
        trade_date="2026-08-30",
        expected_fund_account_fingerprint="123******890",
        now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
    )

    assert snapshot["read_recovery"] == {
        "actions": "native_readback_only",
        "attempts": 2,
        "failure_codes": ["NATIVE_QUERY_POSITIONS_UNPROVEN"],
        "recovered": True,
        "surface_resets": 1,
    }
    assert native.open_order_calls == 1
    assert native.query_calls == [
        "positions",
        "positions",
        "positions",
        "today-orders",
        "today-trades",
    ]
    assert native.prepare_calls == 0
    assert native.submit_calls == 0
    assert native.cancel_calls == 0


def test_native_live_account_snapshot_unlocks_once_when_trade_lock_appears_mid_read(
) -> None:
    native = MidSnapshotTradeLockNative()
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0,),
        snapshot_read_delays=(0.0, 0.0),
    )

    snapshot = adapter.read_live_account_snapshot(
        trade_date="2026-08-30",
        expected_fund_account_fingerprint="123******890",
        now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
    )

    assert snapshot["read_recovery"]["surface_resets"] == 1
    assert native.unlock_calls == 1
    assert native.open_order_calls == 1
    assert native.prepare_calls == 0
    assert native.submit_calls == 0
    assert native.cancel_calls == 0


def test_native_live_account_snapshot_keeps_read_budget_when_surface_reset_unproven(
) -> None:
    native = UnprovenSurfaceResetNative()
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0,),
        snapshot_read_delays=(0.0, 0.0),
    )

    snapshot = adapter.read_live_account_snapshot(
        trade_date="2026-08-30",
        expected_fund_account_fingerprint="123******890",
        now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
    )

    assert snapshot["read_recovery"] == {
        "actions": "native_readback_only",
        "attempts": 2,
        "failure_codes": ["NATIVE_QUERY_POSITIONS_UNPROVEN"],
        "recovered": True,
        "surface_reset_failure_codes": ["NATIVE_QUERY_RESET_SURFACE_UNPROVEN"],
    }
    assert native.query_calls == [
        "positions",
        "positions",
        "positions",
        "today-orders",
        "today-trades",
    ]
    assert native.prepare_calls == 0
    assert native.submit_calls == 0
    assert native.cancel_calls == 0


def test_native_allocation_recovers_transient_asset_drift_read_only() -> None:
    native = TransientAccountInvariantNative()
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0,),
        snapshot_read_delays=(0.0, 0.0),
    )

    facts = adapter.read_live_allocation_facts(
        trade_date="2026-08-30",
        settled_nav=30_000,
        current_open_exposure=0,
        capital_basis_source="initial_book_b_capital",
        expected_fund_account_fingerprint="123******890",
        now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
    )

    assert facts["read_recovery"] == {
        "actions": "native_readback_only",
        "attempts": 2,
        "failure_codes": ["LIVE_ALLOCATION_ASSET_EQUATION_FAILED"],
        "recovered": True,
        "surface_resets": 1,
    }
    assert native.query_calls == ["positions", "positions"]
    assert native.open_order_calls == 1
    assert native.prepare_calls == 0
    assert native.submit_calls == 0
    assert native.cancel_calls == 0


def test_native_live_account_snapshot_reports_exhausted_read_recovery() -> None:
    native = FakeNative()
    native.position_summary["余额"] = "0.01"
    adapter = FounderscNativeAXBrokerAdapter(
        native=native,
        expected_fund_account_fingerprint="123******890",
        reconcile_delays=(0.0,),
        snapshot_read_delays=(0.0, 0.0),
    )

    with pytest.raises(
        FounderscNativeAXError,
        match=(
            "LIVE_ACCOUNT_SNAPSHOT_ASSET_EQUATION_FAILED:"
            "READ_ONLY_RECOVERY_EXHAUSTED:attempts=2"
        ),
    ):
        adapter.read_live_account_snapshot(
            trade_date="2026-08-30",
            expected_fund_account_fingerprint="123******890",
            now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
        )

    assert native.query_calls == [
        "positions", "today-orders", "today-trades",
        "positions", "today-orders", "today-trades",
    ]
    assert native.submit_calls == 0


def test_native_live_account_snapshot_rejects_position_funds_asset_drift() -> None:
    native = FakeNative()
    adapter = _adapter(native)
    native.position_summary["余额"] = "0.01"

    with pytest.raises(FounderscNativeAXError, match="ASSET_EQUATION_FAILED"):
        adapter.read_live_account_snapshot(
            trade_date="2026-08-30",
            expected_fund_account_fingerprint="123******890",
            now=datetime.fromisoformat(OBSERVED_AT.replace("Z", "+00:00")),
        )
