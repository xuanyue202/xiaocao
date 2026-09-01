"""Founder Securities native-app broker adapter.

The native route is deliberately App-only: local Accessibility performs the
bounded order action and local Vision OCR reads positions, funds, orders and
trades from the same account-bound Founder window.  Durable authorization and
exact-once claims remain in :mod:`trading_execution`.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from .foundersc_native_ax import FounderscNativeAXClient, FounderscNativeAXError
from .trading_execution import (
    BrokerAdapter,
    BrokerCapability,
    BrokerReceipt,
    BrokerStatus,
    TradePlan,
)


NATIVE_APP_ROUTE = "native-app"
NATIVE_ORDER_ROUTE_NOT_PROMOTED = "NATIVE_AX_ORDER_ROUTE_NOT_PROMOTED"
NATIVE_ORDER_ADAPTER_PROMOTED = True
NATIVE_HELPER_MIN_VERSION = 8
NATIVE_CANCEL_HELPER_MIN_VERSION = 8
_ACCOUNT_FINGERPRINT_PATTERN = re.compile(r"\d{3}\*{6}\d{3}")
_ORDER_WORKING_STATUSES = frozenset(
    {"未报", "待报", "正报", "已报", "未成交", "已确认", "已申报"}
)
_ORDER_CANCELLED_STATUSES = frozenset({"已撤"})
_ORDER_FILLED_STATUSES = frozenset({"已成", "全成", "全部成交"})
_ORDER_PARTIAL_STATUSES = frozenset({"部成", "部分成交", "部成待撤"})
_ORDER_REJECTED_STATUSES = frozenset(
    {"废单", "已废", "拒单", "已拒绝", "委托失败", "无效委托"}
)


def _parse_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _decimal(value: object, *, field: str, blank_zero: bool = False) -> Decimal:
    text = str(value or "").strip().replace(",", "")
    if blank_zero and not text:
        return Decimal("0")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        raise FounderscNativeAXError(f"NATIVE_QUERY_{field}_MALFORMED")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise FounderscNativeAXError(f"NATIVE_QUERY_{field}_MALFORMED") from exc
    if not parsed.is_finite():
        raise FounderscNativeAXError(f"NATIVE_QUERY_{field}_MALFORMED")
    return parsed


def _integer(value: object, *, field: str, blank_zero: bool = False) -> int:
    number = _decimal(value, field=field, blank_zero=blank_zero)
    integral = number.to_integral_value()
    if number != integral:
        raise FounderscNativeAXError(f"NATIVE_QUERY_{field}_NOT_INTEGER")
    return int(integral)


def _code(value: object) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{6}", text) is None:
        raise FounderscNativeAXError("NATIVE_QUERY_SECURITY_CODE_MALFORMED")
    return text


def _side(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"买入", "买", "BUY", "B"}:
        return "BUY"
    if text in {"卖出", "卖", "SELL", "S"}:
        return "SELL"
    raise FounderscNativeAXError("NATIVE_QUERY_SIDE_MALFORMED")


def _status(value: object) -> BrokerStatus:
    text = str(value or "").strip()
    if not text:
        raise FounderscNativeAXError("NATIVE_QUERY_ORDER_STATUS_MALFORMED")
    if text in _ORDER_CANCELLED_STATUSES:
        return BrokerStatus.CANCELLED
    if text in _ORDER_REJECTED_STATUSES:
        return BrokerStatus.REJECTED
    if text in _ORDER_FILLED_STATUSES:
        return BrokerStatus.FILLED
    if text in _ORDER_PARTIAL_STATUSES:
        return BrokerStatus.PARTIAL
    if text in _ORDER_WORKING_STATUSES:
        return BrokerStatus.ACCEPTED
    return BrokerStatus.UNKNOWN


def _is_cancel_trade_row(row: dict[str, Any]) -> bool:
    return "撤" in str(row.get("成交类型") or "").strip()


class FounderscNativeAXBrokerAdapter(BrokerAdapter):
    """Exact-account, exact-order adapter for the Founder desktop App."""

    route = NATIVE_APP_ROUTE

    def __init__(
        self,
        *,
        native: FounderscNativeAXClient,
        expected_fund_account_fingerprint: str,
        reconcile_delays: tuple[float, ...] = (0.0, 0.25, 0.75, 1.5),
    ) -> None:
        expected = str(expected_fund_account_fingerprint or "").strip()
        if _ACCOUNT_FINGERPRINT_PATTERN.fullmatch(expected) is None:
            raise ValueError("Founder fund-account fingerprint is required")
        self.native = native
        self.expected_fund_account_fingerprint = expected
        self.reconcile_delays = tuple(max(0.0, float(item)) for item in reconcile_delays)
        self._prepared: dict[str, dict[str, Any]] = {}
        self._prepared_cancels: dict[str, dict[str, Any]] = {}

    def _account_bound(self, payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("app_running") is True
            and payload.get("accessibility_trusted") is True
            and payload.get("screen_locked") is False
            and payload.get("trade_account_fingerprint_count") == 1
            and str(payload.get("trade_account_fingerprint") or "")
            == self.expected_fund_account_fingerprint
        )

    def ensure_native_ready(
        self,
        *,
        require_order_capability: bool = False,
        unlock_once: bool = False,
        side: str = "BUY",
    ) -> dict[str, Any]:
        payload = self.native.probe(table_audit=True).as_dict()
        surface = str(payload.get("surface_state") or payload.get("status") or "")
        if unlock_once and surface == "authentication_required":
            unlocked = self.native.unlock_from_keychain(explicitly_enabled=True).as_dict()
            if str(unlocked.get("status") or "") != "unlocked":
                raise FounderscNativeAXError("NATIVE_AX_UNLOCK_UNPROVEN_NO_RETRY")
            payload = self.native.probe(table_audit=True).as_dict()
            surface = str(payload.get("surface_state") or payload.get("status") or "")
        if not self._account_bound(payload) or surface not in {"trade_ready", "query_only"}:
            raise FounderscNativeAXError(
                f"NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:{surface or 'unknown'}"
            )
        expected_side = "buy" if str(side).upper() == "BUY" else "sell"
        observed_side = str(payload.get("side") or "").strip().lower()
        if require_order_capability and (
            surface != "trade_ready" or observed_side != expected_side
        ):
            payload = self.native.open_order_surface(
                side=side,
                expected_fingerprint=self.expected_fund_account_fingerprint,
            ).as_dict()
            surface = str(payload.get("surface_state") or payload.get("status") or "")
            observed_side = str(payload.get("side") or "").strip().lower()
        capabilities = payload.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        helper_version = int(payload.get("helper_version") or 0)
        prepare = capabilities.get("prepare") is True
        submit = capabilities.get("submit") is True
        if require_order_capability and not (
            self._account_bound(payload)
            and surface == "trade_ready"
            and observed_side == expected_side
            and prepare
            and submit
            and helper_version >= NATIVE_HELPER_MIN_VERSION
            and NATIVE_ORDER_ADAPTER_PROMOTED
        ):
            raise FounderscNativeAXError(NATIVE_ORDER_ROUTE_NOT_PROMOTED)
        return {
            "status": "native_trade_ready" if surface == "trade_ready" else "native_query_ready",
            "environment": "live",
            "logical_account_id": "primary",
            "account_binding": "proven",
            "route": self.route,
            "template_name": "foundersc-native-ax",
            "template_version": str(helper_version),
            "surface_state": surface,
            "side": str(payload.get("side") or "unknown"),
            "prepare_capability": prepare,
            "submit_capability": submit,
            "reconcile_capability": True,
            "submitted": False,
            "saved": False,
            "started": False,
        }

    def ensure_login(self) -> dict[str, Any]:
        """Unlock the App trading area once; the web login is not used."""
        return self.ensure_native_ready(unlock_once=True)

    def ensure_environment(
        self,
        *,
        target: str,
        expected_current: str = "any",
        logical_account_id: str = "primary",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if str(target).lower() != "live":
            raise FounderscNativeAXError("NATIVE_APP_HAS_NO_MOCK_NAMESPACE")
        if str(expected_current).lower() not in {"any", "live"}:
            raise FounderscNativeAXError("NATIVE_APP_ENVIRONMENT_EXPECTATION_MISMATCH")
        if logical_account_id != "primary":
            raise FounderscNativeAXError("NATIVE_APP_LOGICAL_ACCOUNT_MISMATCH")
        ready = self.ensure_native_ready(unlock_once=True)
        return {
            **ready,
            "status": "environment_ready",
            "environment": "live",
            "environment_proof_complete": True,
            "environment_data_namespace": "live",
        }

    def _open_query_surface(self) -> dict[str, Any]:
        self.ensure_native_ready(unlock_once=True)
        payload = self.native.open_query_surface(
            expected_fingerprint=self.expected_fund_account_fingerprint,
        ).as_dict()
        if (
            str(payload.get("status") or "")
            not in {"query_surface_opened", "query_surface_ready"}
            or str(payload.get("surface_state") or "") != "query_only"
            or not self._account_bound(payload)
        ):
            raise FounderscNativeAXError("NATIVE_QUERY_SURFACE_OPEN_UNPROVEN")
        return payload

    def _open_cancel_surface(self) -> dict[str, Any]:
        self.ensure_native_ready(unlock_once=True)
        payload = self.native.open_cancel_surface(
            expected_fingerprint=self.expected_fund_account_fingerprint,
        ).as_dict()
        capabilities = payload.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        if (
            str(payload.get("status") or "") != "cancel_surface_ready"
            or str(payload.get("surface_state") or "") != "query_only"
            or not self._account_bound(payload)
            or int(payload.get("helper_version") or 0)
                < NATIVE_CANCEL_HELPER_MIN_VERSION
            or capabilities.get("cancel") is not True
        ):
            raise FounderscNativeAXError("NATIVE_CANCEL_SURFACE_OPEN_UNPROVEN")
        return payload

    def _query(self, kind: str) -> dict[str, Any]:
        last_error = f"NATIVE_QUERY_{kind.upper()}_UNPROVEN"
        for attempt in range(2):
            payload = self.native.read_query(
                kind=kind,
                expected_fingerprint=self.expected_fund_account_fingerprint,
            ).as_dict()
            readback = payload.get("query_readback")
            readback = dict(readback) if isinstance(readback, dict) else {}
            basic_proven = bool(
                str(payload.get("status") or "")
                    in {"query_read", "query_parse_unproven"}
                and self._account_bound(payload)
                and readback.get("capture_proven") is True
                and str(readback.get("kind") or "") == kind
                and isinstance(readback.get("rows"), list)
            )
            if basic_proven:
                rows = [
                    dict(row)
                    for row in readback["rows"]
                    if isinstance(row, dict)
                ]
                if len(rows) != int(readback.get("row_count") or 0):
                    last_error = (
                        f"NATIVE_QUERY_{kind.upper()}_ROW_COUNT_MISMATCH"
                    )
                else:
                    parsing_proven = readback.get("parsing_proven") is True
                    bounded_order_readback = bool(
                        attempt == 1
                        and self._bounded_order_readback(kind, readback, rows)
                    )
                    try:
                        self._validate_rows(kind, rows)
                    except FounderscNativeAXError as exc:
                        last_error = str(exc)
                    else:
                        if not parsing_proven and not bounded_order_readback:
                            last_error = f"NATIVE_QUERY_{kind.upper()}_UNPROVEN"
                            continue
                        return {
                            **readback,
                            "rows": rows,
                            "targeted_reread_used": attempt == 1,
                            "bounded_order_readback_used": bounded_order_readback,
                            "bounded_low_confidence_headers": (
                                list(
                                    readback.get(
                                        "low_confidence_critical_headers"
                                    ) or []
                                )
                                if bounded_order_readback
                                else []
                            ),
                        }
            elif self._account_bound(payload):
                last_error = f"NATIVE_QUERY_{kind.upper()}_UNPROVEN"
            else:
                raise FounderscNativeAXError(
                    f"NATIVE_QUERY_{kind.upper()}_ACCOUNT_UNPROVEN"
                )
            if attempt == 0:
                continue
        raise FounderscNativeAXError(last_error)

    @staticmethod
    def _bounded_order_readback(
        kind: str,
        readback: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> bool:
        """Allow one narrow OCR fallback; trade rows must corroborate it later."""
        if kind != "today-orders":
            return False
        low_headers = set(readback.get("low_confidence_critical_headers") or [])
        if not low_headers or not low_headers.issubset({"成交数量", "状态说明"}):
            return False
        if readback.get("critical_confidence_proven") is not False:
            return False
        required_headers = {
            "证券代码",
            "委托时间",
            "买卖标志",
            "状态说明",
            "委托价格",
            "委托数量",
            "委托编号",
            "成交数量",
        }
        if not required_headers.issubset(set(readback.get("headers") or [])):
            return False
        for row in rows:
            filled = str(row.get("成交数量") or "").strip()
            if re.fullmatch(r"(?:0+(?:\.0+)?)?", filled) is None:
                return False
            if _status(row.get("状态说明")) not in {
                BrokerStatus.ACCEPTED,
                BrokerStatus.CANCELLED,
                BrokerStatus.REJECTED,
            }:
                return False
        return True

    @staticmethod
    def _validate_order_trade_cross_readback(
        orders: dict[str, Any],
        trades: dict[str, Any],
    ) -> None:
        if orders.get("bounded_order_readback_used") is not True:
            return
        traded_by_order: dict[str, int] = {}
        for row in trades["rows"]:
            if _is_cancel_trade_row(row):
                continue
            order_id = str(row.get("委托编号") or "").strip()
            traded_by_order[order_id] = traded_by_order.get(order_id, 0) + _integer(
                row.get("成交数量"), field="TRADE_QUANTITY"
            )
        for row in orders["rows"]:
            order_id = str(row.get("委托编号") or "").strip()
            reported = _integer(
                row.get("成交数量"),
                field="ORDER_FILLED_QUANTITY",
                blank_zero=True,
            )
            if reported != traded_by_order.get(order_id, 0):
                raise FounderscNativeAXError(
                    "NATIVE_ORDER_TRADE_ZERO_FILL_CROSSCHECK_FAILED"
                )

    @staticmethod
    def _order_readback_locator(orders: dict[str, Any]) -> dict[str, Any]:
        return {
            "order_readback_mode": (
                "bounded_known_status_zero_fill"
                if orders.get("bounded_order_readback_used") is True
                else "strict_confidence"
            ),
            "bounded_low_confidence_headers": list(
                orders.get("bounded_low_confidence_headers") or []
            ),
            "targeted_order_reread_used": bool(
                orders.get("targeted_reread_used")
            ),
        }

    @classmethod
    def _baseline_order_readback_locator(
        cls,
        orders: dict[str, Any],
    ) -> dict[str, Any]:
        current = cls._order_readback_locator(orders)
        return {f"baseline_{key}": value for key, value in current.items()}

    @staticmethod
    def _durable_baseline_locator(locator: dict[str, Any]) -> dict[str, Any]:
        keys = {
            "baseline_order_ids",
            "baseline_order_count",
            "baseline_observed_at",
            "baseline_order_readback_mode",
            "baseline_bounded_low_confidence_headers",
            "baseline_targeted_order_reread_used",
            "comparison",
        }
        return {key: locator[key] for key in keys if key in locator}

    @staticmethod
    def _validate_rows(kind: str, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if kind == "positions":
                _code(row.get("证券代码"))
                for field in ("证券数量", "可卖数量"):
                    if _integer(row.get(field), field=field) < 0:
                        raise FounderscNativeAXError(f"NATIVE_QUERY_{field}_NEGATIVE")
                for field in ("当前价", "最新市值"):
                    if _decimal(row.get(field), field=field) < 0:
                        raise FounderscNativeAXError(f"NATIVE_QUERY_{field}_NEGATIVE")
            elif kind in {"today-orders", "history-orders"}:
                _code(row.get("证券代码"))
                _side(row.get("买卖标志"))
                if kind == "history-orders" and re.fullmatch(
                    r"\d{8}", str(row.get("委托日期") or "").strip()
                ) is None:
                    raise FounderscNativeAXError(
                        "NATIVE_QUERY_ORDER_DATE_MALFORMED"
                    )
                if _decimal(row.get("委托价格"), field="ORDER_PRICE") < 0:
                    raise FounderscNativeAXError("NATIVE_QUERY_ORDER_PRICE_NEGATIVE")
                requested = _integer(row.get("委托数量"), field="ORDER_QUANTITY")
                filled = _integer(
                    row.get("成交数量"), field="ORDER_FILLED_QUANTITY", blank_zero=True
                )
                if requested <= 0 or filled < 0 or filled > requested:
                    raise FounderscNativeAXError("NATIVE_QUERY_ORDER_QUANTITY_INVALID")
                if re.fullmatch(r"\d+", str(row.get("委托编号") or "").strip()) is None:
                    raise FounderscNativeAXError("NATIVE_QUERY_ORDER_ID_MALFORMED")
                _status(row.get("状态说明"))
            elif kind in {"today-trades", "history-trades"}:
                _code(row.get("证券代码"))
                _side(row.get("买卖标志"))
                if kind == "history-trades" and re.fullmatch(
                    r"\d{8}", str(row.get("成交日期") or "").strip()
                ) is None:
                    raise FounderscNativeAXError(
                        "NATIVE_QUERY_TRADE_DATE_MALFORMED"
                    )
                if _integer(row.get("成交数量"), field="TRADE_QUANTITY") <= 0:
                    raise FounderscNativeAXError("NATIVE_QUERY_TRADE_QUANTITY_INVALID")
                if _is_cancel_trade_row(row):
                    if _decimal(row.get("成交价格"), field="TRADE_PRICE") != 0:
                        raise FounderscNativeAXError(
                            "NATIVE_QUERY_CANCEL_EVENT_PRICE_INVALID"
                        )
                    if str(row.get("成交编号") or "").strip() and re.fullmatch(
                        r"\d+", str(row.get("成交编号") or "").strip()
                    ) is None:
                        raise FounderscNativeAXError(
                            "NATIVE_QUERY_成交编号_MALFORMED"
                        )
                    fields = ("委托编号",)
                else:
                    if _decimal(row.get("成交价格"), field="TRADE_PRICE") <= 0:
                        raise FounderscNativeAXError(
                            "NATIVE_QUERY_TRADE_PRICE_INVALID"
                        )
                    fields = ("成交编号", "委托编号")
                for field in fields:
                    if re.fullmatch(r"\d+", str(row.get(field) or "").strip()) is None:
                        raise FounderscNativeAXError(f"NATIVE_QUERY_{field}_MALFORMED")
            elif kind == "funds":
                for field in ("资金余额", "可用资金", "总资产"):
                    _decimal(row.get(field), field=field)

    @staticmethod
    def _position_for(plan: TradePlan, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        bare = plan.code.split(".", 1)[0]
        matches = [row for row in rows if str(row.get("证券代码") or "") == bare]
        if len(matches) > 1:
            raise FounderscNativeAXError("NATIVE_POSITION_NOT_UNIQUE")
        return matches[0] if matches else None

    @staticmethod
    def _matching_orders(
        plan: TradePlan,
        rows: list[dict[str, Any]],
        requested_shares: int,
    ) -> list[dict[str, Any]]:
        bare = plan.code.split(".", 1)[0]
        expected_price = Decimal(str(plan.limit_price))
        return [
            row
            for row in rows
            if str(row.get("证券代码") or "") == bare
            and _side(row.get("买卖标志")) == plan.side.upper()
            and _decimal(row.get("委托价格"), field="ORDER_PRICE") == expected_price
            and _integer(row.get("委托数量"), field="ORDER_QUANTITY")
            == requested_shares
        ]

    def probe(self, plan: TradePlan) -> BrokerCapability:
        try:
            ready = self.ensure_native_ready(unlock_once=True)
            self._open_query_surface()
            positions = self._query("positions")
            orders = self._query("today-orders")
            trades = self._query("today-trades")
            self._validate_order_trade_cross_readback(orders, trades)
            summary = positions.get("summary_values")
            summary = dict(summary) if isinstance(summary, dict) else {}
            required_summary = {"资产", "股票市值", "余额", "可用", "可取"}
            if not required_summary.issubset(summary):
                raise FounderscNativeAXError("NATIVE_POSITION_FUNDS_UNPROVEN")
            total_assets = _decimal(summary["资产"], field="TOTAL_ASSETS")
            securities = _decimal(
                summary["股票市值"], field="SECURITIES_VALUE"
            )
            available = _decimal(summary["可用"], field="AVAILABLE_CASH")
            balance = _decimal(summary["余额"], field="CASH_BALANCE")
            withdrawable = _decimal(summary["可取"], field="WITHDRAWABLE_CASH")
            if (
                total_assets <= 0
                or securities < 0
                or balance < 0
                or available < 0
                or withdrawable < 0
                or withdrawable > available
                or available > balance
                or abs((balance + securities) - total_assets)
                    > Decimal("0.10")
            ):
                raise FounderscNativeAXError("NATIVE_POSITION_FUNDS_UNPROVEN")
            cancel_ready = self._open_cancel_surface()
            order_ready = self.ensure_native_ready(
                require_order_capability=True,
                unlock_once=True,
                side=plan.side,
            )
            position = self._position_for(plan, positions["rows"])
            owned = (
                _integer(position.get("证券数量"), field="POSITION_QUANTITY")
                if position else 0
            )
            sellable = (
                _integer(position.get("可卖数量"), field="SELLABLE_QUANTITY")
                if position else 0
            )
            submit = bool(
                order_ready["prepare_capability"]
                and order_ready["submit_capability"]
                and int(order_ready["template_version"]) >= NATIVE_HELPER_MIN_VERSION
                and NATIVE_ORDER_ADAPTER_PROMOTED
            )
            return BrokerCapability(
                ready=True,
                environment="live",
                logical_account_id=plan.logical_account_id,
                supports_submit=submit,
                supports_reconcile=True,
                supports_cancel=bool(
                    int(cancel_ready.get("helper_version") or 0)
                    >= NATIVE_CANCEL_HELPER_MIN_VERSION
                ),
                route=self.route,
                account_binding="proven",
                capabilities={
                    "native_prepare": True,
                    "native_submit": True,
                    "native_positions": True,
                    "native_orders": True,
                    "native_trades": True,
                    "native_position_funds_summary": True,
                    "native_funds_query": False,
                    "native_cancel": True,
                    "opencli_used": False,
                },
                reason="" if submit else NATIVE_ORDER_ROUTE_NOT_PROMOTED,
                manual_position_shares=owned,
                owned_position_shares=owned,
                sellable_shares=sellable,
                t1_blocked=bool(plan.side.upper() == "SELL" and owned > sellable),
                position_source="foundersc_native_app",
                template_name="foundersc-native-ax",
                template_version=ready["template_version"],
            )
        except Exception as exc:
            return BrokerCapability(
                ready=False,
                environment=plan.environment,
                logical_account_id=plan.logical_account_id,
                supports_submit=False,
                supports_reconcile=False,
                supports_cancel=False,
                route=self.route,
                account_binding="unproven",
                reason=f"NATIVE_APP_PROBE_FAILED:{type(exc).__name__}",
                template_name="foundersc-native-ax",
            )

    def probe_cancel(
        self,
        plan: TradePlan,
        previous: dict[str, Any],
    ) -> BrokerCapability:
        """Prove one exact cancel path without reopening order entry.

        The submit probe deliberately ends on the BUY/SELL form. It is the
        wrong precondition for cancellation and used to create the sequence
        ``cancel -> query/order form -> stop``. This dedicated probe uses the
        helper's non-cancelling exact-row selection/clear proof, leaves the App
        on the cancel surface, and caches it for the one post-claim cancel.
        """
        order_id = str(
            previous.get("broker_order_id") or previous.get("order_id") or ""
        ).strip()
        shares = int(previous.get("requested_shares") or plan.shares)
        if not order_id:
            raise FounderscNativeAXError("NATIVE_CANCEL_ORDER_ID_MISSING_NO_RETRY")
        # A cancel probe is allowed the same single unattended unlock recovery
        # as the ordinary native route. This is read-only with respect to the
        # broker order: the helper only selects and clears the exact row.
        self.ensure_native_ready(unlock_once=True)
        payload = self.native.probe_cancel_selection(
            order_id=order_id,
            code=plan.code,
            side=plan.side,
            price=plan.limit_price,
            quantity=shares,
            expected_fingerprint=self.expected_fund_account_fingerprint,
            explicitly_enabled=True,
        ).as_dict()
        readback = payload.get("cancel_readback")
        readback = dict(readback) if isinstance(readback, dict) else {}
        try:
            status = _status(readback.get("order_status"))
            exact = bool(
                str(payload.get("status") or "") == "cancel_selection_proven"
                and self._account_bound(payload)
                and int(payload.get("helper_version") or 0)
                    >= NATIVE_CANCEL_HELPER_MIN_VERSION
                and readback.get("selection_proven") is True
                and str(readback.get("selection_proof_mode") or "") in {
                    "exact_order_tuple",
                    "exact_numeric_tuple_bounded_side_suffix",
                }
                and readback.get("target_match_count") == 1
                and readback.get("cancel_control_count") == 1
                and readback.get("cancel_clicked") is False
                and str(readback.get("order_id") or "") == order_id
                and str(readback.get("code") or "")
                    == plan.code.split(".", 1)[0]
                and _side(readback.get("side")) == plan.side.upper()
                and _integer(readback.get("quantity"), field="CANCEL_QUANTITY")
                    == shares
                and _decimal(readback.get("price"), field="CANCEL_PRICE")
                    == Decimal(str(plan.limit_price))
            )
        except FounderscNativeAXError:
            exact = False
            status = BrokerStatus.UNKNOWN
        if not exact or status not in {
            BrokerStatus.ACCEPTED,
            BrokerStatus.PARTIAL,
        }:
            raise FounderscNativeAXError(
                "NATIVE_CANCEL_PREFLIGHT_STATUS_UNPROVEN"
            )
        filled = int(previous.get("filled_shares") or 0)
        current = BrokerReceipt(
            status=status,
            order_id=order_id,
            strategy_id=str(
                previous.get("broker_strategy_id")
                or previous.get("strategy_id")
                or ""
            ).strip() or None,
            receipt_mapping=True,
            requested_shares=shares,
            filled_shares=filled,
            remaining_shares=max(0, shares - filled),
            order_price=plan.limit_price,
            active=True,
            account_binding="proven",
            locator_proof={
                "cancel_preflight_target_match_count": 1,
                "cancel_preflight_selection_proof_mode": str(
                    readback.get("selection_proof_mode") or ""
                ),
                "cancel_preflight_selected_then_cleared": True,
            },
            template_name="foundersc-native-ax",
            template_version=str(payload.get("helper_version") or ""),
            reason="native_exact_cancel_row_selected_then_cleared",
            conclusive=True,
            retry_allowed=False,
            echoed=self._echo(plan, shares),
            field_readback={
                **readback,
                "cancel_clicked": False,
            },
        )
        self._prepared_cancels[plan.plan_id] = {
            "plan_hash": plan.plan_hash,
            "order_id": order_id,
            "requested_shares": shares,
            "current": current,
            "cancel_surface_ready": True,
        }
        helper_version = int(payload.get("helper_version") or 0)
        return BrokerCapability(
            ready=True,
            environment="live",
            logical_account_id=plan.logical_account_id,
            supports_submit=False,
            supports_reconcile=True,
            supports_cancel=True,
            route=self.route,
            account_binding="proven",
            capabilities={
                "native_cancel": True,
                "native_cancel_exact_order_preflight": True,
                "native_cancel_surface_ready": True,
                "opencli_used": False,
            },
            reason="",
            template_name="foundersc-native-ax",
            template_version=str(helper_version),
        )

    @staticmethod
    def _echo(plan: TradePlan, requested_shares: int) -> dict[str, Any]:
        return {
            "code": plan.code,
            "side": plan.side,
            "shares": int(requested_shares),
            "limit_price": float(plan.limit_price),
        }

    @staticmethod
    def _safe_rejection(
        plan: TradePlan,
        reason: str,
        *,
        requested_shares: int,
        field_readback: dict[str, Any] | None = None,
        locator_proof: dict[str, Any] | None = None,
    ) -> BrokerReceipt:
        return BrokerReceipt(
            status=BrokerStatus.REJECTED,
            requested_shares=requested_shares,
            remaining_shares=requested_shares,
            account_binding="proven",
            locator_proof=dict(locator_proof or {}),
            template_name="foundersc-native-ax",
            reason=reason,
            error_code=reason,
            conclusive=True,
            retry_allowed=False,
            echoed=FounderscNativeAXBrokerAdapter._echo(plan, requested_shares),
            field_readback={
                "submitted": False,
                "saved": False,
                "started": False,
                **dict(field_readback or {}),
            },
        )

    @staticmethod
    def _native_order_readback(
        plan: TradePlan,
        payload: dict[str, Any],
        requested_shares: int,
    ) -> tuple[dict[str, Any], bool]:
        readback = payload.get("order_readback")
        readback = dict(readback) if isinstance(readback, dict) else {}
        try:
            matched = bool(
                readback.get("field_mapping_proven") is True
                and readback.get("submit_control_count") == 1
                and str(readback.get("code") or "") == plan.code.split(".", 1)[0]
                and _side(readback.get("side")) == plan.side.upper()
                and _integer(readback.get("quantity"), field="PREPARED_QUANTITY")
                == requested_shares
                and _decimal(readback.get("price"), field="PREPARED_PRICE")
                == Decimal(str(plan.limit_price))
            )
        except FounderscNativeAXError:
            matched = False
        return readback, matched

    def _order_snapshot(self) -> dict[str, Any]:
        self._open_query_surface()
        return self._query("today-orders")

    def prepare(
        self,
        plan: TradePlan,
        *,
        requested_shares: int | None = None,
    ) -> BrokerReceipt:
        shares = int(requested_shares or plan.shares)
        baseline_locator: dict[str, Any] = {}
        try:
            orders = self._order_snapshot()
            if orders.get("bounded_order_readback_used") is True:
                self._open_query_surface()
                self._validate_order_trade_cross_readback(
                    orders,
                    self._query("today-trades"),
                )
            baseline_ids = sorted(
                str(row["委托编号"]).strip() for row in orders["rows"]
            )
            baseline_locator = {
                **self._baseline_order_readback_locator(orders),
                "baseline_order_ids": baseline_ids,
                "baseline_order_count": len(baseline_ids),
                "baseline_observed_at": orders.get("observed_at"),
                "comparison": "code+side+price+quantity+new_order_id",
            }
            matches = self._matching_orders(plan, orders["rows"], shares)
            if matches:
                return self._safe_rejection(
                    plan,
                    "NATIVE_PREEXISTING_EXACT_ORDER_BLOCKS_SUBMIT",
                    requested_shares=shares,
                    field_readback={"baseline_exact_order_match_count": len(matches)},
                    locator_proof={
                        **baseline_locator,
                        "baseline_exact_order_match_count": len(matches),
                    },
                )
            self.ensure_native_ready(
                require_order_capability=True,
                unlock_once=True,
                side=plan.side,
            )
            payload = self.native.prepare_order(
                code=plan.code,
                side=plan.side,
                price=plan.limit_price,
                quantity=shares,
                expected_fingerprint=self.expected_fund_account_fingerprint,
            ).as_dict()
        except Exception as exc:
            return self._safe_rejection(
                plan,
                f"NATIVE_PREPARE_FAILED:{type(exc).__name__}",
                requested_shares=shares,
                locator_proof=baseline_locator,
            )
        readback, matched = self._native_order_readback(plan, payload, shares)
        if str(payload.get("status") or "") != "prepared" or not matched:
            return self._safe_rejection(
                plan,
                "NATIVE_PREPARE_FIELD_READBACK_MISMATCH",
                requested_shares=shares,
                field_readback=readback,
                locator_proof=baseline_locator,
            )
        self._prepared[plan.plan_id] = {
            "plan_hash": plan.plan_hash,
            "shares": shares,
            "baseline_order_ids": baseline_ids,
            "baseline_observed_at": orders.get("observed_at"),
            "baseline_locator_proof": dict(baseline_locator),
        }
        return BrokerReceipt(
            status=BrokerStatus.PREPARED,
            requested_shares=shares,
            remaining_shares=shares,
            order_price=plan.limit_price,
            account_binding="proven",
            locator_proof=baseline_locator,
            template_name="foundersc-native-ax",
            template_version=str(payload.get("helper_version") or "") or None,
            reason="native_form_exact_readback_prepared",
            conclusive=True,
            retry_allowed=False,
            echoed=self._echo(plan, shares),
            field_readback={
                **readback,
                "baseline_order_count": len(baseline_ids),
                "submitted": False,
                "saved": False,
                "started": False,
            },
        )

    def prepare_readonly(
        self,
        plan: TradePlan,
        *,
        expected_fund_account_fingerprint: str,
        requested_shares: int | None = None,
    ) -> BrokerReceipt:
        if str(expected_fund_account_fingerprint or "").strip() != (
            self.expected_fund_account_fingerprint
        ):
            raise FounderscNativeAXError("NATIVE_AX_ACCOUNT_BINDING_MISMATCH")
        shares = int(requested_shares or plan.shares)
        try:
            self.ensure_native_ready(
                require_order_capability=True,
                unlock_once=True,
                side=plan.side,
            )
            payload = self.native.prepare_order(
                code=plan.code,
                side=plan.side,
                price=plan.limit_price,
                quantity=shares,
                expected_fingerprint=self.expected_fund_account_fingerprint,
                clear_after_readback=True,
            ).as_dict()
        except Exception as exc:
            return self._safe_rejection(
                plan,
                f"NATIVE_READONLY_PREPARE_FAILED:{type(exc).__name__}",
                requested_shares=shares,
            )
        readback, matched = self._native_order_readback(plan, payload, shares)
        if (
            str(payload.get("status") or "") != "prepared"
            or not matched
            or readback.get("form_cleared") is not True
        ):
            return self._safe_rejection(
                plan,
                "NATIVE_READONLY_PREPARE_UNPROVEN",
                requested_shares=shares,
                field_readback=readback,
            )
        return BrokerReceipt(
            status=BrokerStatus.PREPARED,
            requested_shares=shares,
            remaining_shares=shares,
            order_price=plan.limit_price,
            account_binding="proven",
            template_name="foundersc-native-ax",
            template_version=str(payload.get("helper_version") or "") or None,
            reason="native_form_exact_readback_cleared_without_submit",
            conclusive=True,
            retry_allowed=False,
            echoed=self._echo(plan, shares),
            field_readback={
                **readback,
                "submitted": False,
                "saved": False,
                "started": False,
            },
        )

    def _reconcile_rows(
        self,
        plan: TradePlan,
        *,
        requested_shares: int,
        baseline_order_ids: set[str] | None = None,
        expected_order_id: str | None = None,
    ) -> BrokerReceipt:
        orders = self._order_snapshot()
        matches = self._matching_orders(plan, orders["rows"], requested_shares)
        if expected_order_id:
            matches = [
                row for row in matches
                if str(row.get("委托编号") or "").strip() == expected_order_id
            ]
        elif baseline_order_ids is not None:
            matches = [
                row for row in matches
                if str(row.get("委托编号") or "").strip() not in baseline_order_ids
            ]
        locator = {
            **self._order_readback_locator(orders),
            "exact_order_match_count": len(matches),
            "baseline_order_count": (
                len(baseline_order_ids) if baseline_order_ids is not None else None
            ),
            "comparison": "code+side+price+quantity+new_order_id",
        }
        if len(matches) != 1:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                requested_shares=requested_shares,
                remaining_shares=requested_shares,
                receipt_mapping=False,
                account_binding="proven",
                locator_proof=locator,
                template_name="foundersc-native-ax",
                reason="NATIVE_EXACT_ORDER_DELTA_NOT_UNIQUE",
                error_code="NATIVE_EXACT_ORDER_DELTA_NOT_UNIQUE",
                conclusive=False,
                retry_allowed=False,
                echoed=self._echo(plan, requested_shares),
            )
        order = matches[0]
        order_id = str(order["委托编号"]).strip()
        filled = _integer(
            order.get("成交数量"), field="ORDER_FILLED_QUANTITY", blank_zero=True
        )
        normalized = _status(order.get("状态说明"))
        self._open_query_surface()
        trades = self._query("today-trades")
        self._validate_order_trade_cross_readback(orders, trades)
        trade_matches = [
            row for row in trades["rows"]
            if not _is_cancel_trade_row(row)
            and str(row.get("委托编号") or "").strip() == order_id
            and str(row.get("证券代码") or "") == plan.code.split(".", 1)[0]
            and _side(row.get("买卖标志")) == plan.side.upper()
        ]
        trade_filled = sum(
            _integer(row.get("成交数量"), field="TRADE_QUANTITY")
            for row in trade_matches
        )
        if trade_filled > requested_shares or (filled and trade_filled != filled):
            raise FounderscNativeAXError("NATIVE_ORDER_TRADE_QUANTITY_MISMATCH")
        if trade_filled:
            filled = trade_filled
            normalized = (
                BrokerStatus.FILLED
                if filled == requested_shares else BrokerStatus.PARTIAL
            )
        fill_price = None
        if trade_matches:
            amount = sum(
                _decimal(row.get("成交价格"), field="TRADE_PRICE")
                * _integer(row.get("成交数量"), field="TRADE_QUANTITY")
                for row in trade_matches
            )
            fill_price = float(amount / Decimal(filled)) if filled else None
        conclusive = normalized != BrokerStatus.UNKNOWN
        return BrokerReceipt(
            status=normalized,
            order_id=order_id,
            receipt_mapping=True,
            requested_shares=requested_shares,
            filled_shares=filled,
            remaining_shares=requested_shares - filled,
            order_price=float(_decimal(order.get("委托价格"), field="ORDER_PRICE")),
            fill_price=fill_price,
            active=normalized in {
                BrokerStatus.ACCEPTED, BrokerStatus.PARTIAL
            },
            retry_allowed=False,
            account_binding="proven",
            locator_proof={
                **locator,
                "trade_match_count": len(trade_matches),
            },
            template_name="foundersc-native-ax",
            reason=(
                "native_exact_order_delta_and_trade_readback"
                if conclusive else "NATIVE_BROKER_STATUS_UNKNOWN"
            ),
            error_code=None if conclusive else "NATIVE_BROKER_STATUS_UNKNOWN",
            observed_at=_parse_timestamp(orders.get("observed_at")),
            conclusive=conclusive,
            echoed=self._echo(plan, requested_shares),
            field_readback={
                "order_status": str(order.get("状态说明") or ""),
                "order_time": str(order.get("委托时间") or ""),
                "trade_match_count": len(trade_matches),
                "submitted": True,
                "saved": True,
                "started": True,
            },
        )

    def _reconcile_prior_day_rows(
        self,
        plan: TradePlan,
        *,
        requested_shares: int,
        expected_order_id: str,
    ) -> BrokerReceipt:
        """Close one prior-day mapped BUY only from native historical evidence.

        Founder keeps an unfilled day order's historical status as ``已报``.
        That label is not carried into a later trading day: a uniquely matched
        prior-date order, zero exact historical trades, and zero current target
        holding prove that this BUY expired unfilled.  The durable external
        order id remains the execution-ledger identity while the native entrust
        number is retained as locator evidence.
        """
        self._open_query_surface()
        orders = self._query("history-orders")
        trades = self._query("history-trades")
        positions = self._query("positions")
        compact_date = plan.trade_date.replace("-", "")
        bare = plan.code.split(".", 1)[0]
        expected_price = Decimal(str(plan.limit_price))
        order_rows = [
            row
            for row in orders["rows"]
            if str(row.get("委托日期") or "").strip() == compact_date
        ]
        trade_rows = [
            row
            for row in trades["rows"]
            if str(row.get("成交日期") or "").strip() == compact_date
        ]
        order_matches = [
            row
            for row in order_rows
            if str(row.get("证券代码") or "").strip() == bare
            and _side(row.get("买卖标志")) == plan.side.upper()
            and _decimal(row.get("委托价格"), field="ORDER_PRICE")
            == expected_price
            and _integer(row.get("委托数量"), field="ORDER_QUANTITY")
            == requested_shares
            and "撤" not in str(row.get("委托类别") or "")
        ]
        position = self._position_for(plan, positions["rows"])
        target_holding_shares = (
            _integer(position.get("证券数量"), field="POSITION_QUANTITY")
            if position else 0
        )
        locator: dict[str, Any] = {
            "comparison": "trade_date+code+side+price+quantity+non_cancel_entrust",
            "exact_order_match_count": len(order_matches),
            "exact_trade_match_count": 0,
            "target_holding_shares": target_holding_shares,
            "historical_order_row_date": plan.trade_date,
            "historical_trade_row_date": plan.trade_date,
            "historical_order_date_filter": {
                "applied": False,
                "post_capture_filtered": True,
                "mode": "adapter_post_capture_exact_row_date",
                "start": plan.trade_date,
                "end": plan.trade_date,
                "input_count": len(orders["rows"]),
                "output_count": len(order_rows),
            },
            "historical_deal_date_filter": {
                "applied": False,
                "post_capture_filtered": True,
                "mode": "adapter_post_capture_exact_row_date",
                "start": plan.trade_date,
                "end": plan.trade_date,
                "input_count": len(trades["rows"]),
                "output_count": len(trade_rows),
            },
            "historical_order_observed_at": orders.get("observed_at"),
            "historical_trade_observed_at": trades.get("observed_at"),
            "position_observed_at": positions.get("observed_at"),
        }
        if len(order_matches) != 1:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                order_id=expected_order_id,
                requested_shares=requested_shares,
                remaining_shares=requested_shares,
                receipt_mapping=False,
                account_binding="proven",
                locator_proof=locator,
                template_name="foundersc-native-ax",
                reason="NATIVE_HISTORICAL_EXACT_ORDER_NOT_UNIQUE",
                error_code="NATIVE_HISTORICAL_EXACT_ORDER_NOT_UNIQUE",
                conclusive=False,
                retry_allowed=False,
                echoed=self._echo(plan, requested_shares),
            )
        order = order_matches[0]
        native_order_id = str(order.get("委托编号") or "").strip()
        locator["native_order_id"] = native_order_id
        if native_order_id != expected_order_id:
            locator["order_id_mapping"] = "mismatch"
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                order_id=expected_order_id,
                requested_shares=requested_shares,
                remaining_shares=requested_shares,
                receipt_mapping=False,
                account_binding="proven",
                locator_proof=locator,
                template_name="foundersc-native-ax",
                reason="NATIVE_HISTORICAL_ORDER_ID_MISMATCH",
                error_code="NATIVE_HISTORICAL_ORDER_ID_MISMATCH",
                conclusive=False,
                retry_allowed=False,
                echoed=self._echo(plan, requested_shares),
            )
        locator["order_id_mapping"] = "exact"
        trade_matches = [
            row
            for row in trade_rows
            if not _is_cancel_trade_row(row)
            and str(row.get("证券代码") or "").strip() == bare
            and _side(row.get("买卖标志")) == plan.side.upper()
            and str(row.get("委托编号") or "").strip() == native_order_id
        ]
        locator.update({
            "exact_trade_match_count": len(trade_matches),
        })
        order_filled = _integer(
            order.get("成交数量"),
            field="ORDER_FILLED_QUANTITY",
            blank_zero=True,
        )
        trade_filled = sum(
            _integer(row.get("成交数量"), field="TRADE_QUANTITY")
            for row in trade_matches
        )
        if (
            trade_filled > requested_shares
            or order_filled > requested_shares
            or order_filled != trade_filled
        ):
            raise FounderscNativeAXError(
                "NATIVE_HISTORICAL_ORDER_TRADE_QUANTITY_MISMATCH"
            )
        normalized = _status(order.get("状态说明"))
        fill_price = None
        if trade_filled:
            amount = sum(
                _decimal(row.get("成交价格"), field="TRADE_PRICE")
                * _integer(row.get("成交数量"), field="TRADE_QUANTITY")
                for row in trade_matches
            )
            fill_price = float(amount / Decimal(trade_filled))
            normalized = (
                BrokerStatus.FILLED
                if trade_filled == requested_shares else BrokerStatus.PARTIAL
            )
        elif normalized == BrokerStatus.ACCEPTED:
            # A historical day-order row that still says 已报 is not a broker
            # terminal. Date/position inference must never manufacture a
            # CANCELLED state or release capital.
            normalized = BrokerStatus.UNKNOWN
        conclusive = normalized != BrokerStatus.UNKNOWN
        return BrokerReceipt(
            status=normalized,
            order_id=expected_order_id,
            receipt_mapping=conclusive,
            requested_shares=requested_shares,
            filled_shares=trade_filled,
            remaining_shares=requested_shares - trade_filled,
            order_price=float(_decimal(order.get("委托价格"), field="ORDER_PRICE")),
            fill_price=fill_price,
            active=normalized in {BrokerStatus.ACCEPTED, BrokerStatus.PARTIAL},
            retry_allowed=False,
            account_binding="proven",
            locator_proof=locator,
            template_name="foundersc-native-ax",
            reason=(
                "native_historical_order_and_trade_readback"
                if conclusive else "NATIVE_HISTORICAL_STATUS_UNPROVEN"
            ),
            error_code=None if conclusive else "NATIVE_HISTORICAL_STATUS_UNPROVEN",
            observed_at=_parse_timestamp(orders.get("observed_at")),
            conclusive=conclusive,
            echoed=self._echo(plan, requested_shares),
            field_readback={
                "native_order_id": native_order_id,
                "order_status": str(order.get("状态说明") or ""),
                "order_date": str(order.get("委托日期") or ""),
                "order_filled_shares": order_filled,
                "trade_filled_shares": trade_filled,
                "trade_match_count": len(trade_matches),
                "submitted": False,
                "saved": False,
                "started": False,
            },
        )

    def submit(
        self,
        plan: TradePlan,
        claim_id: str,
        *,
        requested_shares: int | None = None,
    ) -> BrokerReceipt:
        shares = int(requested_shares or plan.shares)
        prepared = self._prepared.pop(plan.plan_id, None)
        if (
            not isinstance(prepared, dict)
            or prepared.get("plan_hash") != plan.plan_hash
            or prepared.get("shares") != shares
            or not isinstance(prepared.get("baseline_order_ids"), list)
            or not isinstance(prepared.get("baseline_locator_proof"), dict)
        ):
            return self._safe_rejection(
                plan,
                "NATIVE_DURABLE_CLAIM_HAS_NO_MATCHING_PREPARE",
                requested_shares=shares,
            )
        try:
            payload = self.native.submit_prepared_order(
                code=plan.code,
                side=plan.side,
                price=plan.limit_price,
                quantity=shares,
                expected_fingerprint=self.expected_fund_account_fingerprint,
                explicitly_enabled=True,
            ).as_dict()
        except Exception as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                locator_proof=dict(prepared["baseline_locator_proof"]),
                template_name="foundersc-native-ax",
                reason=f"NATIVE_SUBMIT_RESPONSE_UNKNOWN:{type(exc).__name__}",
                error_code="NATIVE_SUBMIT_RESPONSE_UNKNOWN",
                conclusive=False,
                retry_allowed=False,
                echoed=self._echo(plan, shares),
            )
        readback, matched = self._native_order_readback(plan, payload, shares)
        clicked = bool(
            str(payload.get("status") or "") == "submit_confirmed"
            and matched
            and readback.get("submitted") is True
            and readback.get("saved") is True
            and readback.get("started") is True
        )
        if not clicked:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                locator_proof=dict(prepared["baseline_locator_proof"]),
                template_name="foundersc-native-ax",
                reason="NATIVE_INITIAL_SUBMIT_OUTCOME_UNPROVEN",
                error_code="NATIVE_INITIAL_SUBMIT_OUTCOME_UNPROVEN",
                conclusive=False,
                retry_allowed=False,
                echoed=self._echo(plan, shares),
                field_readback={**readback, "submitted": None, "saved": None},
            )
        last: BrokerReceipt | None = None
        for delay in self.reconcile_delays:
            if delay:
                time.sleep(delay)
            try:
                last = self._reconcile_rows(
                    plan,
                    requested_shares=shares,
                    baseline_order_ids=set(prepared["baseline_order_ids"]),
                )
            except Exception:
                continue
            if last.receipt_mapping and last.order_id and last.conclusive:
                claim_hash = hashlib.sha256(str(claim_id).encode("utf-8")).hexdigest()
                return BrokerReceipt(
                    **{
                        **last.__dict__,
                        "strategy_id": "NAX" + claim_hash[:16].upper(),
                        "reason": "native_submit_mapped_by_exact_order_delta",
                        "locator_proof": {
                            **prepared["baseline_locator_proof"],
                            **last.locator_proof,
                        },
                        "field_readback": {
                            **last.field_readback,
                            **readback,
                            "native_claim_binding_sha256": claim_hash,
                            "submitted": True,
                            "saved": True,
                            "started": True,
                        },
                    }
                )
        return BrokerReceipt(
            status=BrokerStatus.UNKNOWN,
            order_id=last.order_id if last else None,
            receipt_mapping=last.receipt_mapping if last else False,
            requested_shares=shares,
            filled_shares=last.filled_shares if last else 0,
            remaining_shares=last.remaining_shares if last else shares,
            order_price=plan.limit_price,
            account_binding="proven",
            locator_proof={
                **prepared["baseline_locator_proof"],
                **(last.locator_proof if last else {}),
            },
            template_name="foundersc-native-ax",
            reason="NATIVE_SUBMIT_CLICKED_READBACK_UNPROVEN",
            error_code="NATIVE_SUBMIT_CLICKED_READBACK_UNPROVEN",
            conclusive=False,
            retry_allowed=False,
            echoed=self._echo(plan, shares),
            field_readback={
                **(last.field_readback if last else {}),
                **readback,
                "submitted": True,
                "saved": False,
                "started": True,
            },
        )

    def reconcile(self, plan: TradePlan, previous: dict[str, Any]) -> BrokerReceipt:
        order_id = str(
            previous.get("broker_order_id") or previous.get("order_id") or ""
        ).strip()
        shares = int(previous.get("requested_shares") or plan.shares)
        if not order_id:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                template_name="foundersc-native-ax",
                reason="NATIVE_RECONCILE_ORDER_ID_MISSING_NO_RETRY",
                error_code="NATIVE_RECONCILE_ORDER_ID_MISSING_NO_RETRY",
                conclusive=False,
                retry_allowed=False,
            )
        try:
            if plan.trade_date < datetime.now(
                ZoneInfo("Asia/Shanghai")
            ).date().isoformat():
                return self._reconcile_prior_day_rows(
                    plan,
                    requested_shares=shares,
                    expected_order_id=order_id,
                )
            return self._reconcile_rows(
                plan,
                requested_shares=shares,
                expected_order_id=order_id,
            )
        except Exception as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                order_id=order_id,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                template_name="foundersc-native-ax",
                reason=f"NATIVE_RECONCILE_FAILED:{type(exc).__name__}",
                error_code="NATIVE_RECONCILE_FAILED_NO_RETRY",
                conclusive=False,
                retry_allowed=False,
            )

    def cancel(self, plan: TradePlan, previous: dict[str, Any]) -> BrokerReceipt:
        """Cancel one exact mapped order with at most one broker-side click."""
        order_id = str(
            previous.get("broker_order_id") or previous.get("order_id") or ""
        ).strip()
        shares = int(previous.get("requested_shares") or plan.shares)
        strategy_id = str(
            previous.get("broker_strategy_id") or previous.get("strategy_id") or ""
        ).strip() or None
        if not order_id:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                template_name="foundersc-native-ax",
                reason="NATIVE_CANCEL_ORDER_ID_MISSING_NO_RETRY",
                error_code="NATIVE_CANCEL_ORDER_ID_MISSING_NO_RETRY",
                conclusive=False,
                retry_allowed=False,
            )
        prepared = self._prepared_cancels.pop(plan.plan_id, None)
        prepared_matches = bool(
            isinstance(prepared, dict)
            and prepared.get("plan_hash") == plan.plan_hash
            and prepared.get("order_id") == order_id
            and prepared.get("requested_shares") == shares
            and isinstance(prepared.get("current"), BrokerReceipt)
        )
        try:
            current = (
                prepared["current"]
                if prepared_matches
                else self._reconcile_rows(
                    plan,
                    requested_shares=shares,
                    expected_order_id=order_id,
                )
            )
        except Exception as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                order_id=order_id,
                strategy_id=strategy_id,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                template_name="foundersc-native-ax",
                reason=f"NATIVE_CANCEL_PREFLIGHT_FAILED:{type(exc).__name__}",
                error_code="NATIVE_CANCEL_PREFLIGHT_FAILED_NO_RETRY",
                conclusive=False,
                retry_allowed=False,
            )
        current_status = current.normalized_status()
        if current_status in {
            BrokerStatus.CANCELLED,
            BrokerStatus.FILLED,
            BrokerStatus.REJECTED,
        }:
            return BrokerReceipt(
                **{
                    **current.__dict__,
                    "strategy_id": strategy_id,
                    "reason": "native_cancel_terminal_readback_no_click",
                }
            )
        if current_status not in {BrokerStatus.ACCEPTED, BrokerStatus.PARTIAL}:
            return BrokerReceipt(
                **{
                    **current.__dict__,
                    "status": BrokerStatus.UNKNOWN,
                    "strategy_id": strategy_id,
                    "reason": "NATIVE_CANCEL_PREFLIGHT_STATUS_UNPROVEN",
                    "error_code": "NATIVE_CANCEL_PREFLIGHT_STATUS_UNPROVEN",
                    "conclusive": False,
                    "retry_allowed": False,
                }
            )

        payload: dict[str, Any] = {}
        click_error: str | None = None
        try:
            if not (
                prepared_matches
                and prepared.get("cancel_surface_ready") is True
            ):
                self._open_cancel_surface()
            payload = self.native.cancel_order(
                order_id=order_id,
                code=plan.code,
                side=plan.side,
                price=plan.limit_price,
                quantity=shares,
                expected_fingerprint=self.expected_fund_account_fingerprint,
                explicitly_enabled=True,
            ).as_dict()
        except Exception as exc:
            click_error = type(exc).__name__
        cancel_readback = payload.get("cancel_readback")
        cancel_readback = (
            dict(cancel_readback) if isinstance(cancel_readback, dict) else {}
        )
        helper_status = str(payload.get("status") or "")
        cancel_clicked = cancel_readback.get("cancel_clicked") is True
        try:
            selection_proof_mode = str(
                cancel_readback.get("selection_proof_mode") or ""
            )
            cancel_click_proven = bool(
                cancel_clicked
                and helper_status
                    in {
                        "cancel_clicked",
                        "cancel_confirmed",
                        "cancel_confirmation_unproven",
                    }
                and cancel_readback.get("selection_proven") is True
                and selection_proof_mode in {
                    "exact_order_tuple",
                    "exact_numeric_tuple_bounded_side_suffix",
                }
                and cancel_readback.get("target_match_count") == 1
                and cancel_readback.get("cancel_control_count") == 1
                and cancel_readback.get("cancel_clicked") is True
                and str(cancel_readback.get("order_id") or "") == order_id
                and str(cancel_readback.get("code") or "")
                    == plan.code.split(".", 1)[0]
                and _side(cancel_readback.get("side")) == plan.side.upper()
                and _integer(
                    cancel_readback.get("quantity"), field="CANCEL_QUANTITY"
                ) == shares
                and _decimal(cancel_readback.get("price"), field="CANCEL_PRICE")
                    == Decimal(str(plan.limit_price))
            ) if cancel_readback else False
        except FounderscNativeAXError:
            cancel_click_proven = False
        cancel_locator_evidence = {
            "cancel_helper_status": helper_status,
            "cancel_clicked": cancel_clicked,
            "cancel_click_proven": cancel_click_proven,
            "cancel_confirmation_pressed": (
                cancel_readback.get("confirmation_pressed") is True
            ),
            "cancel_selection_proof_mode": str(
                cancel_readback.get("selection_proof_mode") or ""
            ),
        }

        last: BrokerReceipt | None = None
        for delay in self.reconcile_delays:
            if delay:
                time.sleep(delay)
            try:
                last = self._reconcile_rows(
                    plan,
                    requested_shares=shares,
                    expected_order_id=order_id,
                )
            except Exception:
                continue
            if last.normalized_status() == BrokerStatus.CANCELLED and last.conclusive:
                return BrokerReceipt(
                    **{
                        **last.__dict__,
                        "strategy_id": strategy_id,
                        "reason": "native_exact_order_cancelled_and_reconciled",
                        "locator_proof": {
                            **last.locator_proof,
                            **cancel_locator_evidence,
                        },
                        "field_readback": {
                            **last.field_readback,
                            **cancel_readback,
                            "cancel_clicked": cancel_clicked,
                            "cancel_click_proven": cancel_click_proven,
                        },
                    }
                )
            if last.normalized_status() in {
                BrokerStatus.FILLED,
                BrokerStatus.REJECTED,
            } and last.conclusive:
                return BrokerReceipt(
                    **{
                        **last.__dict__,
                        "strategy_id": strategy_id,
                        "reason": "native_cancel_raced_with_terminal_broker_state",
                        "locator_proof": {
                            **last.locator_proof,
                            **cancel_locator_evidence,
                        },
                        "field_readback": {
                            **last.field_readback,
                            **cancel_readback,
                            "cancel_clicked": cancel_clicked,
                            "cancel_click_proven": cancel_click_proven,
                        },
                    }
                )
        return BrokerReceipt(
            status=BrokerStatus.UNKNOWN,
            order_id=order_id,
            strategy_id=strategy_id,
            receipt_mapping=True,
            requested_shares=shares,
            filled_shares=last.filled_shares if last else current.filled_shares,
            remaining_shares=(
                last.remaining_shares if last else current.remaining_shares
            ),
            order_price=plan.limit_price,
            account_binding="proven",
            locator_proof={
                **(last.locator_proof if last else current.locator_proof),
                **cancel_locator_evidence,
            },
            template_name="foundersc-native-ax",
            reason=(
                "NATIVE_CANCEL_CLICKED_READBACK_UNPROVEN"
                if cancel_clicked else
                "NATIVE_CANCEL_OUTCOME_UNKNOWN:"
                f"{click_error or str(payload.get('status') or 'UNPROVEN')}"
            ),
            error_code="NATIVE_CANCEL_OUTCOME_UNKNOWN_NO_RETRY",
            conclusive=False,
            retry_allowed=False,
            echoed=self._echo(plan, shares),
            field_readback={
                **(last.field_readback if last else current.field_readback),
                **cancel_readback,
                "cancel_clicked": cancel_clicked,
                "cancel_click_proven": cancel_click_proven,
            },
        )

    def recover(self, plan: TradePlan, previous: dict[str, Any]) -> BrokerReceipt:
        """Recover an unknown submit only from its durable pre-submit delta."""
        shares = int(previous.get("requested_shares") or plan.shares)
        claim_id = str(previous.get("submit_claim_id") or "").strip()
        locator = previous.get("locator_proof")
        locator = dict(locator) if isinstance(locator, dict) else {}
        baseline_locator = self._durable_baseline_locator(locator)
        raw_baseline = locator.get("baseline_order_ids")
        baseline_ids: list[str] | None = (
            [str(item).strip() for item in raw_baseline]
            if isinstance(raw_baseline, list) else []
        )
        context_proven = bool(
            previous.get("submit_chain_uncertain") is True
            and claim_id
            and isinstance(raw_baseline, list)
            and len(baseline_ids) == len(set(baseline_ids))
            and all(re.fullmatch(r"\d{1,32}", item) for item in baseline_ids)
            and locator.get("baseline_order_count") == len(baseline_ids)
            and _parse_timestamp(locator.get("baseline_observed_at")) is not None
        )
        if not context_proven:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                locator_proof=baseline_locator,
                template_name="foundersc-native-ax",
                reason="NATIVE_RECOVERY_DURABLE_CONTEXT_UNPROVEN",
                error_code="NATIVE_RECOVERY_DURABLE_CONTEXT_UNPROVEN_NO_RETRY",
                conclusive=False,
                retry_allowed=False,
            )
        try:
            recovered = self._reconcile_rows(
                plan,
                requested_shares=shares,
                baseline_order_ids=set(baseline_ids),
            )
        except Exception as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                requested_shares=shares,
                remaining_shares=shares,
                account_binding="proven",
                locator_proof=baseline_locator,
                template_name="foundersc-native-ax",
                reason=f"NATIVE_RECOVERY_READBACK_FAILED:{type(exc).__name__}",
                error_code="NATIVE_RECOVERY_READBACK_FAILED_NO_RETRY",
                conclusive=False,
                retry_allowed=False,
            )
        recovered = BrokerReceipt(
            **{
                **recovered.__dict__,
                "locator_proof": {
                    **baseline_locator,
                    **recovered.locator_proof,
                },
            }
        )
        if not (
            recovered.receipt_mapping is True
            and recovered.order_id
            and recovered.conclusive
        ):
            return recovered
        claim_hash = hashlib.sha256(claim_id.encode("utf-8")).hexdigest()
        return BrokerReceipt(
            **{
                **recovered.__dict__,
                "strategy_id": "NAX" + claim_hash[:16].upper(),
                "reason": "native_unknown_submit_recovered_by_durable_exact_order_delta",
                "locator_proof": {
                    **recovered.locator_proof,
                    "recovery_mode": "durable_exact_order_delta",
                },
                "field_readback": {
                    **recovered.field_readback,
                    "native_claim_binding_sha256": claim_hash,
                    "submitted": True,
                    "saved": True,
                    "started": True,
                },
            }
        )

    def read_live_allocation_facts(
        self,
        *,
        trade_date: str,
        settled_nav: float,
        current_open_exposure: float,
        capital_basis_source: str,
        expected_fund_account_fingerprint: str,
        logical_account_id: str = "primary",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        nav = float(settled_nav)
        exposure = float(current_open_exposure)
        if not math.isfinite(nav) or nav <= 0:
            raise ValueError("LIVE_BOOK_B_SETTLED_NAV_INVALID")
        if not math.isfinite(exposure) or exposure < 0 or exposure > nav:
            raise ValueError("LIVE_BOOK_B_OPEN_EXPOSURE_INVALID")
        if capital_basis_source != "initial_book_b_capital":
            raise ValueError("LIVE_BOOK_B_CAPITAL_BASIS_UNPROVEN")
        if logical_account_id != "primary":
            raise FounderscNativeAXError("LIVE_ALLOCATION_ACCOUNT_MISMATCH")
        if str(expected_fund_account_fingerprint or "").strip() != (
            self.expected_fund_account_fingerprint
        ):
            raise FounderscNativeAXError("LIVE_ALLOCATION_ACCOUNT_BINDING_UNPROVEN")
        self._open_query_surface()
        positions = self._query("positions")
        summary = positions.get("summary_values")
        summary = dict(summary) if isinstance(summary, dict) else {}
        required = {"资产", "股票市值", "余额", "可用", "可取"}
        if not required.issubset(summary):
            raise FounderscNativeAXError("LIVE_ALLOCATION_SUMMARY_UNPROVEN")
        total_assets = _decimal(summary["资产"], field="TOTAL_ASSETS")
        securities = _decimal(summary["股票市值"], field="SECURITIES_VALUE")
        balance = _decimal(summary["余额"], field="CASH_BALANCE")
        available = _decimal(summary["可用"], field="AVAILABLE_CASH")
        withdrawable = _decimal(summary["可取"], field="WITHDRAWABLE_CASH")
        if (
            total_assets <= 0
            or securities < 0
            or balance < 0
            or available < 0
            or withdrawable < 0
        ):
            raise FounderscNativeAXError("LIVE_ALLOCATION_VALUES_INVALID")
        if balance + securities != total_assets:
            raise FounderscNativeAXError("LIVE_ALLOCATION_ASSET_EQUATION_FAILED")
        if available > balance:
            raise FounderscNativeAXError(
                "LIVE_ALLOCATION_AVAILABLE_EXCEEDS_BALANCE"
            )
        if withdrawable > available:
            raise FounderscNativeAXError(
                "LIVE_ALLOCATION_WITHDRAWABLE_EXCEEDS_AVAILABLE"
            )
        position_value = sum(
            _decimal(row.get("最新市值"), field="POSITION_VALUE")
            for row in positions["rows"]
        )
        if abs(position_value - securities) > Decimal("0.10"):
            raise FounderscNativeAXError("LIVE_ALLOCATION_POSITION_SUM_FAILED")
        observed_at = _parse_timestamp(positions.get("observed_at"))
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("LIVE_ALLOCATION_NOW_NOT_TZ_AWARE")
        if observed_at is None:
            raise FounderscNativeAXError("LIVE_ALLOCATION_OBSERVED_AT_UNPROVEN")
        china = ZoneInfo("Asia/Shanghai")
        if observed_at.astimezone(china).date().isoformat() != str(trade_date)[:10]:
            raise FounderscNativeAXError("LIVE_ALLOCATION_OBSERVED_DATE_MISMATCH")
        age = (current.astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)).total_seconds()
        if age < -30 or age > 300:
            raise FounderscNativeAXError("LIVE_ALLOCATION_RECEIPT_STALE")
        binding_hash = hashlib.sha256(
            self.expected_fund_account_fingerprint.encode("utf-8")
        ).hexdigest()
        values = {
            "总资产": float(total_assets),
            "证券市值": float(securities),
            "资金余额": float(balance),
            "可用资金": float(available),
            "可取资金": float(withdrawable),
        }
        safe_receipt = {
            "template_name": "foundersc-native-ax/query",
            "template_version": NATIVE_HELPER_MIN_VERSION,
            "status": "allocation_reconciled",
            "trade_date": str(trade_date)[:10],
            "environment": "live",
            "logical_account_id": logical_account_id,
            "account_binding": "proven",
            "fund_account_binding_sha256": binding_hash,
            "observed_at": observed_at.isoformat(),
            "allocation_summary": {"complete": True, "values": values},
        }
        receipt_hash = hashlib.sha256(
            json.dumps(
                safe_receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        capsule = {
            "trade_date": str(trade_date)[:10],
            "environment": "live",
            "logical_account_id": logical_account_id,
            "account_binding": "proven",
            "fund_account_binding_sha256": binding_hash,
            "settled_nav": nav,
            "available_cash": float(available),
            "cash_balance": float(balance),
            "withdrawable_cash": float(withdrawable),
            "current_open_exposure": exposure,
            "capital_basis_source": capital_basis_source,
            "broker_total_assets": float(total_assets),
            "broker_securities_market_value": float(securities),
            "source": "foundersc_native_app",
            "broker_observed_at": observed_at.isoformat(),
            "broker_receipt": safe_receipt,
            "broker_receipt_sha256": receipt_hash,
        }
        capsule["allocation_capsule_sha256"] = hashlib.sha256(
            json.dumps(
                capsule,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        return capsule


__all__ = [
    "FounderscNativeAXBrokerAdapter",
    "NATIVE_APP_ROUTE",
    "NATIVE_ORDER_ADAPTER_PROMOTED",
    "NATIVE_ORDER_ROUTE_NOT_PROMOTED",
]
