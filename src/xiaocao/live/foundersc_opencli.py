"""Founder Securities OpenCLI adapter for the broker-neutral Book B seam.

The browser templates deliberately expose only ``probe``, ``prepare``,
``reconcile`` and ``recover`` today.  This adapter keeps that boundary honest:
it consumes one sanitized JSON receipt, never parses DOM text, and its
``submit`` method is an explicit no-route guard rather than a hidden fallback.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .trading_execution import (
    BrokerAdapter,
    BrokerCapability,
    BrokerReceipt,
    BrokerStatus,
    TradePlan,
    _safe_evidence,
)


Runner = Callable[..., Any]


class OpenCLIAdapterError(RuntimeError):
    """A command or receipt failed before any broker-side submit action."""


def _bare_code(value: object) -> str:
    return str(value or "").strip().split(".", 1)[0]


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _one_receipt(stdout: object) -> dict[str, Any]:
    """Parse the template's strict one-row JSON output.

    OpenCLI may print a short diagnostic before the formatted row.  We accept
    only the final non-empty line and still require it to be exactly one JSON
    object (or a one-element JSON array); arbitrary text is never interpreted
    as a successful broker result.
    """
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    if not lines:
        raise OpenCLIAdapterError("OPENCLI_EMPTY_RECEIPT")
    try:
        payload = json.loads(lines[-1])
    except (TypeError, json.JSONDecodeError) as exc:
        raise OpenCLIAdapterError("OPENCLI_INVALID_RECEIPT") from exc
    if isinstance(payload, list):
        if len(payload) != 1 or not isinstance(payload[0], dict):
            raise OpenCLIAdapterError("OPENCLI_RECEIPT_CARDINALITY")
        return dict(payload[0])
    if not isinstance(payload, dict):
        raise OpenCLIAdapterError("OPENCLI_RECEIPT_SHAPE")
    return dict(payload)


class FounderscQuantOpenCLIAdapter(BrokerAdapter):
    """Read-only Founder template adapter with a permanent submit fail-closed."""

    def __init__(
        self,
        *,
        profile: str | None = None,
        opencli_command: tuple[str, ...] | None = None,
        runner: Runner = subprocess.run,
        timeout_seconds: int = 30,
        route: str = "manual-limit",
    ) -> None:
        if profile is not None and not profile.strip():
            raise ValueError("profile must be non-empty when supplied")
        if route not in {"manual-limit", "opening-auction", "timed-order"}:
            raise ValueError("unsupported Founder preparation route")
        self.profile = profile
        installed = shutil.which("opencli")
        self.opencli_command = tuple(opencli_command or ((installed,) if installed else (
            "npx", "--yes", "@jackwener/opencli@1.8.6"
        )))
        self.runner = runner
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.route = route

    def _command(self, operation: str, args: list[str]) -> list[str]:
        return [
            *self.opencli_command,
            *(("--profile", self.profile) if self.profile else ()),
            "foundersc-quant",
            operation,
            *args,
            "-f",
            "json",
        ]

    def _run(self, operation: str, args: list[str]) -> dict[str, Any]:
        command = self._command(operation, args)
        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenCLIAdapterError("OPENCLI_TIMEOUT") from exc
        except OSError as exc:
            raise OpenCLIAdapterError(f"OPENCLI_START_FAILED:{type(exc).__name__}") from exc
        if int(getattr(result, "returncode", 1)) != 0:
            raise OpenCLIAdapterError("OPENCLI_COMMAND_FAILED")
        return _one_receipt(getattr(result, "stdout", ""))

    @staticmethod
    def _plan_args(plan: TradePlan) -> list[str]:
        return [
            "--expected-environment",
            plan.environment,
            "--logical-account-id",
            plan.logical_account_id,
        ]

    def probe(self, plan: TradePlan) -> BrokerCapability:
        try:
            row = self._run("probe", self._plan_args(plan))
        except OpenCLIAdapterError as exc:
            return BrokerCapability(
                ready=False,
                environment=plan.environment,
                logical_account_id=plan.logical_account_id,
                supports_submit=False,
                supports_reconcile=False,
                reason=str(exc),
            )
        capability = BrokerCapability.from_template(row)
        # A malformed template receipt must never be treated as a binding for
        # the requested plan simply because it omitted identity fields.
        if not capability.environment or not capability.logical_account_id:
            return BrokerCapability(
                ready=False,
                environment=capability.environment or "unknown",
                logical_account_id=capability.logical_account_id,
                supports_submit=False,
                supports_reconcile=capability.supports_reconcile,
                reason="OPENCLI_BINDING_FIELDS_MISSING",
                locator_proof=capability.locator_proof,
                capabilities=capability.capabilities,
                template_name=capability.template_name,
                template_version=capability.template_version,
            )
        return capability

    def prepare(self, plan: TradePlan, *, requested_shares: int | None = None) -> BrokerReceipt:
        shares = int(requested_shares or plan.shares)
        args = [
            "--route",
            self.route,
            *self._plan_args(plan),
            "--code",
            _bare_code(plan.code),
            "--side",
            plan.side.lower(),
            "--quantity",
            str(shares),
            "--price",
            f"{plan.limit_price:.6f}".rstrip("0").rstrip("."),
        ]
        try:
            row = self._run("prepare", args)
        except OpenCLIAdapterError as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason=str(exc),
                error_code=str(exc).split(":", 1)[0],
                conclusive=False,
            )
        return self._receipt_from_row(plan, row, stage="prepare", requested_shares=shares)

    def submit(
        self,
        plan: TradePlan,
        claim_id: str,
        *,
        requested_shares: int | None = None,
    ) -> BrokerReceipt:
        # There is intentionally no `foundersc-quant submit` command yet.  Do
        # not turn a template capability gap into a direct browser click.
        return BrokerReceipt(
            status=BrokerStatus.REJECTED,
            reason="NO_ROUTE_PROVEN",
            error_code="NO_ROUTE_PROVEN",
            conclusive=True,
            field_readback={"submitted": False, "claim_id": claim_id},
        )

    def reconcile(self, plan: TradePlan, previous: dict[str, Any]) -> BrokerReceipt:
        args = [
            "--scope",
            "all",
            *self._plan_args(plan),
        ]
        try:
            row = self._run("reconcile", args)
        except OpenCLIAdapterError as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason=str(exc),
                error_code=str(exc).split(":", 1)[0],
                conclusive=False,
            )
        return self._receipt_from_row(plan, row, stage="reconcile")

    def recover(self, plan: TradePlan, error: str) -> BrokerReceipt:
        args = [
            "--route",
            "assets",
            *self._plan_args(plan),
        ]
        try:
            row = self._run("recover", args)
        except OpenCLIAdapterError as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason=f"{error};{exc}",
                error_code=str(exc).split(":", 1)[0],
                conclusive=False,
            )
        receipt = self._receipt_from_row(plan, row, stage="recover")
        if receipt.status == BrokerStatus.UNKNOWN and not receipt.reason:
            return BrokerReceipt(
                **{**receipt.__dict__, "reason": error},
            )
        return receipt

    @classmethod
    def _receipt_from_row(
        cls,
        plan: TradePlan,
        row: dict[str, Any],
        *,
        stage: str,
        requested_shares: int | None = None,
    ) -> BrokerReceipt:
        raw_status = str(row.get("status") or "unknown").strip().lower()
        reason = str(row.get("status_reason") or row.get("reason") or "")
        error_code = row.get("error_code")
        capabilities = row.get("capabilities")
        capabilities = dict(capabilities) if isinstance(capabilities, dict) else {}
        receipt_mapping = bool(row.get("receipt_mapping", capabilities.get("receipt_mapping")))
        if raw_status in {"unknown", "auth_required", "capability_gap"}:
            status: str | BrokerStatus = BrokerStatus.UNKNOWN
            conclusive = False
        elif raw_status == "environment_mismatch":
            status = BrokerStatus.REJECTED
            conclusive = True
        elif stage == "prepare" and raw_status in {"prepared_readback", "prepared"}:
            status = BrokerStatus.PREPARED
            conclusive = True
        elif stage == "reconcile" and raw_status in {"reconciled", "ready", "recovered"}:
            # A page readback without a stable order/deal mapping is an
            # observation, not proof of a fill or a terminal order state.
            if not receipt_mapping or not row.get("order_id"):
                status = BrokerStatus.UNKNOWN
                conclusive = False
                reason = reason or "BROKER_RECEIPT_MAPPING_UNPROVEN"
            else:
                status = BrokerStatus.UNKNOWN
                conclusive = False
        else:
            status = raw_status
            conclusive = not bool(row.get("reconcile_required"))

        field_readback = row.get("field_readback")
        field_readback = dict(field_readback) if isinstance(field_readback, dict) else {}
        locator_proof = row.get("locator_proof")
        locator_proof = dict(locator_proof) if isinstance(locator_proof, dict) else {}
        echoed: dict[str, Any] = {}
        if stage == "prepare":
            echoed_code = field_readback.get("code") or field_readback.get("stock_code")
            echoed_side = field_readback.get("side") or field_readback.get("requested_side")
            echoed_shares = field_readback.get("quantity") or field_readback.get("shares")
            echoed_price = field_readback.get("price") or field_readback.get("limit_price")
            if echoed_code not in (None, ""):
                echoed["code"] = plan.code if _bare_code(echoed_code) == _bare_code(plan.code) else echoed_code
            if echoed_side not in (None, ""):
                echoed["side"] = (
                    "BUY" if str(echoed_side).strip().lower() in {"buy", "买入"}
                    else "SELL" if str(echoed_side).strip().lower() in {"sell", "卖出"}
                    else echoed_side
                )
            if echoed_shares not in (None, ""):
                echoed["shares"] = _optional_int(echoed_shares)
            if echoed_price not in (None, ""):
                echoed["limit_price"] = _optional_float(echoed_price)

        return BrokerReceipt(
            status=status,
            order_id=str(row.get("order_id") or "") or None,
            strategy_id=str(row.get("strategy_id") or row.get("task_id") or "") or None,
            requested_shares=_optional_int(row.get("requested_shares")) or requested_shares,
            filled_shares=_optional_int(row.get("filled_shares")) or 0,
            remaining_shares=_optional_int(row.get("remaining_shares")),
            order_price=_optional_float(row.get("order_price")),
            fill_price=_optional_float(row.get("fill_price")),
            latest_price=_optional_float(row.get("latest_price")),
            active=row.get("active") if isinstance(row.get("active"), bool) else None,
            retry_allowed=row.get("retry_allowed") if isinstance(row.get("retry_allowed"), bool) else None,
            market_guard_status=row.get("market_guard_status"),
            market_guard_observed_at=_parse_datetime(
                row.get("market_guard_observed_at") or row.get("market_observed_at")
            ),
            market_guard_down_price=_optional_float(
                row.get("market_guard_down_price")
                if row.get("market_guard_down_price") not in (None, "")
                else row.get("down_price") or row.get("downPrice")
            ),
            template_name=str(row.get("template_name") or "foundersc-quant") or None,
            template_version=str(row.get("template_version") or "") or None,
            account_binding=str(row.get("account_binding") or "") or None,
            locator_proof=_safe_evidence(locator_proof),
            reason=reason,
            error_code=str(error_code) if error_code not in (None, "") else None,
            observed_at=_parse_datetime(row.get("observed_at") or row.get("market_observed_at")),
            submitted_at=_parse_datetime(row.get("submitted_at")),
            cancelled_at=_parse_datetime(row.get("cancelled_at")),
            conclusive=conclusive,
            echoed=echoed,
            field_readback=field_readback,
        )


__all__ = ["FounderscQuantOpenCLIAdapter", "OpenCLIAdapterError"]
