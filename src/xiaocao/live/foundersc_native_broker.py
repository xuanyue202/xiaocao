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
                str(payload.get("status") or "") == "query_read"
                and self._account_bound(payload)
                and readback.get("capture_proven") is True
                and readback.get("parsing_proven") is True
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
                    try:
                        self._validate_rows(kind, rows)
                    except FounderscNativeAXError as exc:
                        last_error = str(exc)
                    else:
                        return {
                            **readback,
                            "rows": rows,
                            "targeted_reread_used": attempt == 1,
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
            elif kind == "today-orders":
                _code(row.get("证券代码"))
                _side(row.get("买卖标志"))
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
            elif kind == "today-trades":
                _code(row.get("证券代码"))
                _side(row.get("买卖标志"))
                if _decimal(row.get("成交价格"), field="TRADE_PRICE") <= 0:
                    raise FounderscNativeAXError("NATIVE_QUERY_TRADE_PRICE_INVALID")
                if _integer(row.get("成交数量"), field="TRADE_QUANTITY") <= 0:
                    raise FounderscNativeAXError("NATIVE_QUERY_TRADE_QUANTITY_INVALID")
                for field in ("成交编号", "委托编号"):
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
            self._query("today-orders")
            self._query("today-trades")
            self._query("funds")
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
                    "native_funds": True,
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
    ) -> BrokerReceipt:
        return BrokerReceipt(
            status=BrokerStatus.REJECTED,
            requested_shares=requested_shares,
            remaining_shares=requested_shares,
            account_binding="proven",
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
        try:
            orders = self._order_snapshot()
            matches = self._matching_orders(plan, orders["rows"], shares)
            if matches:
                return self._safe_rejection(
                    plan,
                    "NATIVE_PREEXISTING_EXACT_ORDER_BLOCKS_SUBMIT",
                    requested_shares=shares,
                    field_readback={"baseline_exact_order_match_count": len(matches)},
                )
            baseline_ids = {
                str(row["委托编号"]).strip() for row in orders["rows"]
            }
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
            )
        readback, matched = self._native_order_readback(plan, payload, shares)
        if str(payload.get("status") or "") != "prepared" or not matched:
            return self._safe_rejection(
                plan,
                "NATIVE_PREPARE_FIELD_READBACK_MISMATCH",
                requested_shares=shares,
                field_readback=readback,
            )
        self._prepared[plan.plan_id] = {
            "plan_hash": plan.plan_hash,
            "shares": shares,
            "baseline_order_ids": sorted(baseline_ids),
            "baseline_observed_at": orders.get("observed_at"),
        }
        return BrokerReceipt(
            status=BrokerStatus.PREPARED,
            requested_shares=shares,
            remaining_shares=shares,
            order_price=plan.limit_price,
            account_binding="proven",
            locator_proof={
                "baseline_order_ids": sorted(baseline_ids),
                "baseline_order_count": len(baseline_ids),
                "baseline_observed_at": orders.get("observed_at"),
                "comparison": "code+side+price+quantity+new_order_id",
            },
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
        trade_matches = [
            row for row in trades["rows"]
            if str(row.get("委托编号") or "").strip() == order_id
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
            locator_proof=last.locator_proof if last else {},
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
        try:
            current = self._reconcile_rows(
                plan,
                requested_shares=shares,
                expected_order_id=order_id,
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
        try:
            cancel_clicked = bool(
                str(payload.get("status") or "")
                    in {"cancel_clicked", "cancel_confirmed"}
                and cancel_readback.get("selection_proven") is True
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
            cancel_clicked = False

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
                        "field_readback": {
                            **last.field_readback,
                            **cancel_readback,
                            "cancel_clicked": cancel_clicked,
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
            locator_proof=last.locator_proof if last else current.locator_proof,
            template_name="foundersc-native-ax",
            reason=(
                "NATIVE_CANCEL_CLICKED_READBACK_UNPROVEN"
                if cancel_clicked else
                f"NATIVE_CANCEL_OUTCOME_UNKNOWN:{click_error or 'UNPROVEN'}"
            ),
            error_code="NATIVE_CANCEL_OUTCOME_UNKNOWN_NO_RETRY",
            conclusive=False,
            retry_allowed=False,
            echoed=self._echo(plan, shares),
            field_readback={
                **(last.field_readback if last else current.field_readback),
                **cancel_readback,
                "cancel_clicked": cancel_clicked or None,
            },
        )

    def recover(self, plan: TradePlan, previous: dict[str, Any]) -> BrokerReceipt:
        """Recover an unknown submit only from its durable pre-submit delta."""
        shares = int(previous.get("requested_shares") or plan.shares)
        claim_id = str(previous.get("submit_claim_id") or "").strip()
        locator = previous.get("locator_proof")
        locator = dict(locator) if isinstance(locator, dict) else {}
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
                template_name="foundersc-native-ax",
                reason=f"NATIVE_RECOVERY_READBACK_FAILED:{type(exc).__name__}",
                error_code="NATIVE_RECOVERY_READBACK_FAILED_NO_RETRY",
                conclusive=False,
                retry_allowed=False,
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
        required = {"资产", "股票市值", "可用"}
        if not required.issubset(summary):
            raise FounderscNativeAXError("LIVE_ALLOCATION_SUMMARY_UNPROVEN")
        total_assets = _decimal(summary["资产"], field="TOTAL_ASSETS")
        securities = _decimal(summary["股票市值"], field="SECURITIES_VALUE")
        available = _decimal(summary["可用"], field="AVAILABLE_CASH")
        if total_assets <= 0 or securities < 0 or available < 0:
            raise FounderscNativeAXError("LIVE_ALLOCATION_VALUES_INVALID")
        if abs((available + securities) - total_assets) > Decimal("0.10"):
            raise FounderscNativeAXError("LIVE_ALLOCATION_ASSET_EQUATION_FAILED")
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
            "可用资金": float(available),
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
