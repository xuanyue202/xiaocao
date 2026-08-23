"""Founder Securities OpenCLI adapter for the broker-neutral Book B seam.

The browser templates expose route-aware probe/prepare/reconcile/recover
commands plus one UI-only ``package-limit`` submit command.  This adapter keeps
that boundary honest: it consumes one sanitized JSON receipt, never parses DOM
text, and rejects every unproved route or ambiguous submit receipt.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .trading_execution import (
    BrokerAdapter,
    BrokerCapability,
    BrokerReceipt,
    BrokerStatus,
    TradePlan,
    _safe_evidence,
)


Runner = Callable[..., Any]
_CONNECTED_PROFILE_PATTERN = re.compile(
    r"^\s*(?P<context>\S+)(?:\s+(?P<alias>\S+))?\s+—\s+connected\b",
    re.MULTILINE,
)
_ACCOUNT_FINGERPRINT_PATTERN = re.compile(r"\d{3}\*{6}\d{3}")


class OpenCLIAdapterError(RuntimeError):
    """A command or receipt failed before any broker-side submit action."""


def resolve_connected_opencli_profile(
    profile: str | None = None,
    *,
    opencli_command: tuple[str, ...] | None = None,
    runner: Runner = subprocess.run,
    timeout_seconds: int = 10,
    launch_edge: Callable[[], None] | None = None,
    poll_attempts: int = 10,
    poll_seconds: float = 0.5,
) -> str:
    """Resolve one Edge Browser Bridge context without exposing page data."""
    requested = str(profile or "").strip()
    installed = shutil.which("opencli")
    command = tuple(
        opencli_command
        or ((installed,) if installed else ("npx", "--yes", "@jackwener/opencli@1.8.6"))
    )
    timeout = max(1, int(timeout_seconds))

    def connected_contexts() -> list[tuple[str, bool]]:
        try:
            result = runner(
                [*command, "profile", "list"],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenCLIAdapterError("OPENCLI_PROFILE_LIST_TIMEOUT") from exc
        except OSError as exc:
            raise OpenCLIAdapterError("OPENCLI_PROFILE_LIST_FAILED") from exc
        if int(getattr(result, "returncode", 1)) != 0:
            raise OpenCLIAdapterError("OPENCLI_PROFILE_LIST_FAILED")
        output = getattr(result, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return [
            (
                str(match.group("context")),
                str(match.group("alias") or "").strip().lower() == "default",
            )
            for match in _CONNECTED_PROFILE_PATTERN.finditer(str(output))
        ]

    def is_edge(context: str) -> bool:
        try:
            result = runner(
                [
                    *command,
                    "--profile",
                    context,
                    "browser",
                    "xiaocao-edge-profile-probe",
                    "eval",
                    "navigator.userAgent",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        output = getattr(result, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return int(getattr(result, "returncode", 1)) == 0 and " Edg/" in str(output)

    def start_edge() -> None:
        if launch_edge is not None:
            launch_edge()
            return
        try:
            subprocess.run(
                ["/usr/bin/open", "-g", "-a", "Microsoft Edge"],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OpenCLIAdapterError("OPENCLI_EDGE_LAUNCH_FAILED") from exc

    attempts = max(1, int(poll_attempts))
    for attempt in range(attempts):
        contexts = connected_contexts()
        resolved: str | None = None
        if len(contexts) == 1:
            resolved = contexts[0][0]
        elif len(contexts) > 1:
            defaults = [context for context, is_default in contexts if is_default]
            if len(defaults) == 1:
                resolved = defaults[0]
            else:
                raise OpenCLIAdapterError("OPENCLI_PROFILE_AMBIGUOUS")
        if resolved is not None:
            if requested and requested != resolved:
                raise OpenCLIAdapterError("OPENCLI_EDGE_PROFILE_MISMATCH")
            if is_edge(resolved):
                return resolved
        if attempt == 0:
            start_edge()
        if attempt + 1 < attempts:
            time.sleep(max(0.0, float(poll_seconds)))
    raise OpenCLIAdapterError("OPENCLI_EDGE_PROFILE_NOT_CONNECTED")


def release_foundersc_opencli_site_session(
    profile: str,
    *,
    opencli_command: tuple[str, ...] | None = None,
    runner: Runner = subprocess.run,
    timeout_seconds: int = 10,
) -> None:
    """Release only the Founder adapter's stale Edge tab lease.

    OpenCLI's persistent adapter session keeps the authenticated Edge tab warm,
    but an interrupted browser recovery can leave that exact session leased.
    Releasing the scoped lease before the morning process starts is idempotent;
    it neither closes Edge nor reads page contents.
    """
    context = str(profile or "").strip()
    if not context:
        raise ValueError("profile must be non-empty")
    installed = shutil.which("opencli")
    command = tuple(
        opencli_command
        or ((installed,) if installed else ("npx", "--yes", "@jackwener/opencli@1.8.6"))
    )
    try:
        result = runner(
            [
                *command,
                "--profile",
                context,
                "browser",
                "site:foundersc-quant",
                "close",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1, int(timeout_seconds)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OpenCLIAdapterError("OPENCLI_SITE_SESSION_RELEASE_FAILED") from exc
    if int(getattr(result, "returncode", 1)) != 0:
        raise OpenCLIAdapterError("OPENCLI_SITE_SESSION_RELEASE_FAILED")


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


def _broker_number(value: object) -> float | None:
    raw = str(value or "").strip().replace(",", "").replace("¥", "")
    try:
        number = float(raw)
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _one_receipt(stdout: object) -> dict[str, Any]:
    """Parse the template's strict one-row JSON output.

    OpenCLI may print a short diagnostic before a compact or pretty-printed
    result.  Parse only a complete JSON suffix and still require exactly one
    object (or a one-element array); arbitrary text is never interpreted as a
    successful broker result.
    """
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    if not lines:
        raise OpenCLIAdapterError("OPENCLI_EMPTY_RECEIPT")
    payload: object | None = None
    payload_start: int | None = None
    last_error: json.JSONDecodeError | None = None
    for start in range(len(lines) - 1, -1, -1):
        if not lines[start].startswith(("{", "[")):
            continue
        try:
            payload = json.loads("\n".join(lines[start:]))
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        payload_start = start
        break
    if payload is None:
        raise OpenCLIAdapterError("OPENCLI_INVALID_RECEIPT") from last_error
    if any(line.startswith(("{", "[")) for line in lines[: payload_start or 0]):
        raise OpenCLIAdapterError("OPENCLI_RECEIPT_CARDINALITY")
    if isinstance(payload, list):
        if len(payload) != 1 or not isinstance(payload[0], dict):
            raise OpenCLIAdapterError("OPENCLI_RECEIPT_CARDINALITY")
        return dict(payload[0])
    if not isinstance(payload, dict):
        raise OpenCLIAdapterError("OPENCLI_RECEIPT_SHAPE")
    return dict(payload)


class FounderscQuantOpenCLIAdapter(BrokerAdapter):
    """Founder template adapter with one receipt-gated package-limit route."""

    def __init__(
        self,
        *,
        profile: str | None = None,
        opencli_command: tuple[str, ...] | None = None,
        runner: Runner = subprocess.run,
        timeout_seconds: int = 90,
        route: str = "manual-limit",
        expected_fund_account_fingerprint: str | None = None,
    ) -> None:
        if profile is not None and not profile.strip():
            raise ValueError("profile must be non-empty when supplied")
        if route not in {
            "package-limit",
            "manual-limit",
            "opening-auction",
            "timed-order",
        }:
            raise ValueError("unsupported Founder preparation route")
        expected_fingerprint = str(expected_fund_account_fingerprint or "").strip()
        if expected_fingerprint and not _ACCOUNT_FINGERPRINT_PATTERN.fullmatch(
            expected_fingerprint
        ):
            raise ValueError("invalid expected Founder fund-account fingerprint")
        self.profile = profile
        installed = shutil.which("opencli")
        self.opencli_command = tuple(opencli_command or ((installed,) if installed else (
            "npx", "--yes", "@jackwener/opencli@1.8.6"
        )))
        self.runner = runner
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.route = route
        self.expected_fund_account_fingerprint = expected_fingerprint

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

    def _prepare_args(self, plan: TradePlan, shares: int) -> list[str]:
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
        if self.route == "timed-order":
            args.extend(
                [
                    "--date",
                    plan.trade_date,
                    "--time",
                    "09:30",
                    "--strategy-name",
                    f"xiaocao-readback-{plan.trade_date}-{_bare_code(plan.code)}",
                ]
            )
        return args

    def ensure_environment(
        self,
        *,
        target: str,
        expected_current: str = "any",
        logical_account_id: str = "primary",
    ) -> dict[str, Any]:
        """Switch only the Founder mock/live selector and verify exact readback."""
        normalized_target = str(target or "").strip().lower()
        normalized_expected = str(expected_current or "any").strip().lower()
        if normalized_target not in {"mock", "live"}:
            raise ValueError("unsupported Founder environment target")
        if normalized_expected not in {"any", "mock", "live"}:
            raise ValueError("unsupported Founder expected environment")
        row = self._run(
            "environment",
            [
                "--target",
                normalized_target,
                "--expected-current",
                normalized_expected,
                "--logical-account-id",
                str(logical_account_id or "primary").strip(),
            ],
        )
        status = str(row.get("status") or "").strip().lower()
        environment = str(row.get("environment") or "").strip().lower()
        if status not in {"environment_ready", "environment_switched"} or environment != normalized_target:
            raise OpenCLIAdapterError(f"OPENCLI_ENVIRONMENT_NOT_READY:{status or 'unknown'}")
        if (
            row.get("environment_proof_complete") is not True
            or str(row.get("environment_data_namespace") or "").strip().lower()
            != normalized_target
        ):
            raise OpenCLIAdapterError("OPENCLI_ENVIRONMENT_PROOF_UNPROVEN")
        if row.get("fund_account_match_count") != 1:
            raise OpenCLIAdapterError("OPENCLI_ENVIRONMENT_ACCOUNT_UNPROVEN")
        if any(row.get(key) is True for key in ("submitted", "saved", "started")):
            raise OpenCLIAdapterError("OPENCLI_ENVIRONMENT_UNSAFE_SIDE_EFFECT")
        return {
            "status": status,
            "environment": environment,
            "environment_data_namespace": normalized_target,
            "environment_proof_complete": True,
            "logical_account_id": str(row.get("logical_account_id") or ""),
            "account_binding": str(row.get("account_binding") or "unknown"),
            "submitted": False,
            "saved": False,
            "started": False,
            "field_readback": _safe_evidence(row.get("field_readback") or {}),
            "capabilities": _safe_evidence(row.get("capabilities") or {}),
        }

    def ensure_login(self) -> dict[str, Any]:
        """Authenticate the persistent session and prove a safe mock baseline."""
        row = self._run("login", [])
        safe = (
            str(row.get("status") or "").strip().lower()
            == "login_authenticated"
            and str(row.get("environment") or "").strip().lower() == "mock"
            and str(row.get("environment_data_namespace") or "").strip().lower()
            == "mock"
            and row.get("environment_proof_complete") is True
            and row.get("fund_account_match_count") == 1
            and all(row.get(key) is not True for key in ("submitted", "saved", "started"))
        )
        if not safe:
            raise OpenCLIAdapterError("OPENCLI_LOGIN_SAFE_MOCK_UNPROVEN")
        return {
            "status": "login_authenticated",
            "environment": "mock",
            "environment_data_namespace": "mock",
            "environment_proof_complete": True,
            "logical_account_id": str(row.get("logical_account_id") or ""),
            "submitted": False,
            "saved": False,
            "started": False,
            "capabilities": _safe_evidence(row.get("capabilities") or {}),
        }

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
        """Read one complete, live, account-bound Founder asset snapshot."""
        account = str(logical_account_id or "").strip()
        nav = float(settled_nav)
        exposure = float(current_open_exposure)
        basis_source = str(capital_basis_source or "").strip()
        if not math.isfinite(nav) or nav <= 0:
            raise ValueError("LIVE_BOOK_B_SETTLED_NAV_INVALID")
        if not math.isfinite(exposure) or exposure < 0 or exposure > nav:
            raise ValueError("LIVE_BOOK_B_OPEN_EXPOSURE_INVALID")
        if basis_source != "initial_book_b_capital":
            raise ValueError("LIVE_BOOK_B_CAPITAL_BASIS_UNPROVEN")
        expected_fingerprint = str(expected_fund_account_fingerprint or "").strip()
        if not _ACCOUNT_FINGERPRINT_PATTERN.fullmatch(expected_fingerprint):
            raise OpenCLIAdapterError("LIVE_ALLOCATION_EXPECTED_ACCOUNT_MISSING")
        row = self._run(
            "reconcile",
            [
                "--scope",
                "assets",
                "--expected-environment",
                "live",
                "--logical-account-id",
                account,
            ],
        )
        if str(row.get("environment") or "").strip().lower() != "live":
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ENVIRONMENT_NOT_LIVE")
        if (
            row.get("environment_proof_complete") is not True
            or str(row.get("environment_data_namespace") or "").strip().lower()
            != "live"
        ):
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ENVIRONMENT_PROOF_UNPROVEN")
        if str(row.get("logical_account_id") or "").strip() != account:
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ACCOUNT_MISMATCH")
        observed_fingerprint = str(row.get("fund_account_fingerprint") or "").strip()
        if observed_fingerprint != expected_fingerprint:
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ACCOUNT_BINDING_UNPROVEN")
        status = str(row.get("status") or "").strip().lower()
        status_reason = str(row.get("status_reason") or "").strip().lower()
        if status not in {"reconciled", "reconciled_partial"} or (
            status == "reconciled_partial" and status_reason not in {
                "",
                "account_fingerprint_not_proven",
            }
        ):
            raise OpenCLIAdapterError("LIVE_ALLOCATION_RECONCILE_INCOMPLETE")
        observed_at = _parse_datetime(row.get("observed_at"))
        current = now or datetime.now(timezone.utc)
        if observed_at is None or observed_at.tzinfo is None:
            raise OpenCLIAdapterError("LIVE_ALLOCATION_OBSERVED_AT_UNPROVEN")
        if current.tzinfo is None:
            raise ValueError("LIVE_ALLOCATION_NOW_NOT_TZ_AWARE")
        if observed_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() != str(
            trade_date
        )[:10]:
            raise OpenCLIAdapterError("LIVE_ALLOCATION_OBSERVED_DATE_MISMATCH")
        age_seconds = (current.astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)).total_seconds()
        if age_seconds < -30 or age_seconds > 300:
            raise OpenCLIAdapterError("LIVE_ALLOCATION_RECEIPT_STALE")
        if any(row.get(key) is True for key in ("submitted", "saved", "started")):
            raise OpenCLIAdapterError("LIVE_ALLOCATION_UNSAFE_SIDE_EFFECT")
        readback = row.get("field_readback")
        assets = readback.get("assets") if isinstance(readback, dict) else None
        if assets is None or assets.get("complete_scan") is not True:
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ASSET_SCAN_INCOMPLETE")
        summary = assets.get("allocation_summary")
        values = summary.get("values") if isinstance(summary, dict) else None
        if not isinstance(values, dict) or summary.get("complete") is not True:
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ASSET_SUMMARY_UNPROVEN")
        required = ("总资产", "证券市值", "可用资金")
        if set(values) != set(required):
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ASSET_COLUMNS_UNPROVEN")
        parsed = {
            label: _broker_number(values[label])
            for label in required
        }
        if parsed["总资产"] is None or parsed["总资产"] <= 0 or any(
            parsed[label] is None for label in ("证券市值", "可用资金")
        ):
            raise OpenCLIAdapterError("LIVE_ALLOCATION_ASSET_VALUES_INVALID")
        binding_hash = hashlib.sha256(expected_fingerprint.encode("utf-8")).hexdigest()
        safe_receipt = {
            "template_name": str(row.get("template_name") or "foundersc-quant/reconcile"),
            "template_version": row.get("template_version"),
            "status": "allocation_reconciled",
            "trade_date": str(trade_date or "")[:10],
            "environment": "live",
            "logical_account_id": account,
            "account_binding": "proven",
            "fund_account_binding_sha256": binding_hash,
            "observed_at": observed_at.isoformat(),
            "allocation_summary": {
                "complete": True,
                "values": parsed,
            },
        }
        receipt_hash = hashlib.sha256(
            json.dumps(
                safe_receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        allocation_capsule = {
            "trade_date": str(trade_date or "")[:10],
            "environment": "live",
            "logical_account_id": account,
            "account_binding": "proven",
            "fund_account_binding_sha256": binding_hash,
            "settled_nav": nav,
            "available_cash": parsed["可用资金"],
            "current_open_exposure": exposure,
            "capital_basis_source": basis_source,
            "broker_total_assets": parsed["总资产"],
            "broker_securities_market_value": parsed["证券市值"],
            "source": "foundersc_reconcile",
            "broker_observed_at": observed_at.isoformat(),
            "broker_receipt": safe_receipt,
            "broker_receipt_sha256": receipt_hash,
        }
        allocation_capsule["allocation_capsule_sha256"] = hashlib.sha256(
            json.dumps(
                allocation_capsule,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        return allocation_capsule

    def probe(self, plan: TradePlan) -> BrokerCapability:
        try:
            row = self._run(
                "probe",
                ["--route", self.route, *self._plan_args(plan)],
            )
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
        expected = self.expected_fund_account_fingerprint
        binding_safe = (
            bool(expected)
            and str(row.get("environment") or "").strip().lower()
            == plan.environment
            and row.get("environment_proof_complete") is True
            and str(row.get("environment_data_namespace") or "").strip().lower()
            == plan.environment
            and str(row.get("logical_account_id") or "").strip()
            == plan.logical_account_id
            and row.get("fund_account_match_count") == 1
            and str(row.get("fund_account_fingerprint") or "").strip()
            == expected
        )
        if not binding_safe:
            return replace(
                capability,
                ready=False,
                supports_submit=False,
                account_binding="not_proven",
                reason="OPENCLI_BINDING_PROOF_UNPROVEN",
            )
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
        return replace(capability, account_binding="proven")

    def prepare(self, plan: TradePlan, *, requested_shares: int | None = None) -> BrokerReceipt:
        if self.route == "package-limit":
            return self.prepare_readonly(
                plan,
                expected_fund_account_fingerprint=(
                    self.expected_fund_account_fingerprint
                ),
                requested_shares=requested_shares,
            )
        shares = int(requested_shares or plan.shares)
        args = self._prepare_args(plan, shares)
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

    def prepare_readonly(
        self,
        plan: TradePlan,
        *,
        expected_fund_account_fingerprint: str,
        requested_shares: int | None = None,
    ) -> BrokerReceipt:
        """Prepare, read back and close one form with external account proof.

        The browser template cannot read Keychain.  This production-only seam
        binds its masked page account to the fingerprint obtained by the
        caller from Keychain.  This method itself always closes the form and
        never calls the separate submit command.
        """
        expected = str(expected_fund_account_fingerprint or "").strip()
        if not _ACCOUNT_FINGERPRINT_PATTERN.fullmatch(expected):
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason="LIVE_PREPARE_EXPECTED_ACCOUNT_MISSING",
                error_code="LIVE_PREPARE_EXPECTED_ACCOUNT_MISSING",
                conclusive=False,
            )
        shares = int(requested_shares or plan.shares)
        args = self._prepare_args(plan, shares)
        try:
            row = self._run("prepare", args)
        except OpenCLIAdapterError as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason=str(exc),
                error_code=str(exc).split(":", 1)[0],
                conclusive=False,
            )
        status = str(row.get("status") or "").strip().lower()
        reason = str(row.get("status_reason") or row.get("reason") or "").strip()
        capabilities = row.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        field_readback = row.get("field_readback")
        field_readback = field_readback if isinstance(field_readback, dict) else {}
        timed_price = _broker_number(field_readback.get("price"))
        timed_readback_safe = self.route != "timed-order" or (
            str(field_readback.get("strategy_name") or "")
            == f"xiaocao-readback-{plan.trade_date}-{_bare_code(plan.code)}"
            and str(field_readback.get("date") or "") == plan.trade_date
            and str(field_readback.get("hour") or "") == "9"
            and str(field_readback.get("minute") or "") == "30"
            and str(field_readback.get("price_semantics") or "")
            == "numeric_limit"
            and field_readback.get("numeric_price_option_count") == 1
            and timed_price is not None
            and math.isclose(timed_price, plan.limit_price, abs_tol=1e-6)
        )
        safe = (
            str(row.get("environment") or "").strip().lower() == plan.environment
            and row.get("environment_proof_complete") is True
            and str(row.get("environment_data_namespace") or "").strip().lower()
            == plan.environment
            and str(row.get("logical_account_id") or "").strip()
            == plan.logical_account_id
            and str(row.get("fund_account_fingerprint") or "").strip() == expected
            and status in {"prepared", "prepared_readback", "unknown"}
            and (
                status != "unknown"
                or reason == "account_fingerprint_not_proven"
            )
            and capabilities.get("form_readback") is True
            and capabilities.get("submit") is False
            and timed_readback_safe
            and row.get("ready_for_submit") is False
            and row.get("form_closed") is True
            and all(row.get(key) is False for key in ("submitted", "saved", "started"))
        )
        receipt = self._receipt_from_row(
            plan,
            row,
            stage="prepare",
            requested_shares=shares,
        )
        if not safe:
            return replace(
                receipt,
                status=BrokerStatus.UNKNOWN,
                reason=reason or "LIVE_PREPARE_READBACK_UNPROVEN",
                error_code="LIVE_PREPARE_READBACK_UNPROVEN",
                conclusive=False,
            )
        return replace(
            receipt,
            status=BrokerStatus.PREPARED,
            account_binding="proven",
            reason="form_readback_completed_without_submit",
            error_code=None,
            conclusive=True,
        )

    def submit(
        self,
        plan: TradePlan,
        claim_id: str,
        *,
        requested_shares: int | None = None,
    ) -> BrokerReceipt:
        if self.route != "package-limit":
            return BrokerReceipt(
                status=BrokerStatus.REJECTED,
                reason="NO_ROUTE_PROVEN",
                error_code="NO_ROUTE_PROVEN",
                conclusive=True,
                field_readback={"submitted": False, "claim_id": claim_id},
            )
        expected = self.expected_fund_account_fingerprint
        if not expected:
            return BrokerReceipt(
                status=BrokerStatus.REJECTED,
                reason="LIVE_SUBMIT_EXPECTED_ACCOUNT_MISSING",
                error_code="LIVE_SUBMIT_EXPECTED_ACCOUNT_MISSING",
                conclusive=True,
                field_readback={"submitted": False, "claim_id": claim_id},
            )
        shares = int(requested_shares or plan.shares)
        strategy_name = "XC" + hashlib.sha256(
            str(claim_id).encode("utf-8")
        ).hexdigest()[:6].upper()
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
            "--expected-fund-account-fingerprint",
            expected,
            "--claim-id",
            str(claim_id),
            "--strategy-name",
            strategy_name,
        ]
        try:
            row = self._run("submit", args)
        except OpenCLIAdapterError as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason=str(exc),
                error_code=str(exc).split(":", 1)[0],
                conclusive=False,
            )
        receipt = self._receipt_from_row(
            plan,
            row,
            stage="submit",
            requested_shares=shares,
        )
        capabilities = row.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        binding_safe = (
            str(row.get("environment") or "").strip().lower() == plan.environment
            and row.get("environment_proof_complete") is True
            and str(row.get("environment_data_namespace") or "").strip().lower()
            == plan.environment
            and row.get("fund_account_match_count") == 1
            and str(row.get("fund_account_fingerprint") or "").strip() == expected
            and str(row.get("logical_account_id") or "").strip()
            == plan.logical_account_id
        )
        conclusive_rejection = (
            binding_safe
            and receipt.normalized_status() == BrokerStatus.REJECTED
            and row.get("submitted") is False
            and row.get("saved") is False
            and row.get("started") is False
            and row.get("reconcile_required") is False
            and receipt.conclusive
        )
        if conclusive_rejection:
            return replace(
                receipt,
                account_binding="proven",
                error_code=None,
            )
        safe = (
            binding_safe
            and row.get("submitted") is True
            and row.get("saved") is True
            and bool(row.get("order_id"))
            and bool(row.get("strategy_id"))
            and capabilities.get("submit") is True
            and capabilities.get("receipt_mapping") is True
        )
        if not safe:
            return replace(
                receipt,
                status=BrokerStatus.UNKNOWN,
                reason=str(row.get("status_reason") or "LIVE_SUBMIT_RECEIPT_UNPROVEN"),
                error_code="LIVE_SUBMIT_RECEIPT_UNPROVEN",
                conclusive=False,
            )
        return replace(
            receipt,
            status=BrokerStatus.ACCEPTED,
            account_binding="proven",
            reason=str(row.get("status_reason") or "order_submitted"),
            error_code=None,
            conclusive=True,
        )

    def reconcile(self, plan: TradePlan, previous: dict[str, Any]) -> BrokerReceipt:
        expected_order_id = str(
            previous.get("broker_order_id") or previous.get("order_id") or ""
        ).strip()
        args = [
            "--scope",
            "orders" if self.route == "package-limit" else "all",
            *self._plan_args(plan),
            "--code",
            _bare_code(plan.code),
            "--side",
            plan.side.lower(),
            "--quantity",
            str(plan.shares),
            "--price",
            f"{plan.limit_price:.6f}".rstrip("0").rstrip("."),
            "--date",
            plan.trade_date,
        ]
        if expected_order_id:
            args.extend(["--order-id", expected_order_id])
        try:
            row = self._run("reconcile", args)
        except OpenCLIAdapterError as exc:
            return BrokerReceipt(
                status=BrokerStatus.UNKNOWN,
                reason=str(exc),
                error_code=str(exc).split(":", 1)[0],
                conclusive=False,
            )
        receipt = self._receipt_from_row(plan, row, stage="reconcile")
        if self.route != "package-limit":
            return receipt
        expected_fingerprint = self.expected_fund_account_fingerprint
        capabilities = row.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        observed_order_id = str(row.get("order_id") or "").strip()
        binding_safe = (
            bool(expected_fingerprint)
            and str(row.get("environment") or "").strip().lower()
            == plan.environment
            and row.get("environment_proof_complete") is True
            and str(row.get("environment_data_namespace") or "").strip().lower()
            == plan.environment
            and row.get("fund_account_match_count") == 1
            and str(row.get("fund_account_fingerprint") or "").strip()
            == expected_fingerprint
            and str(row.get("logical_account_id") or "").strip()
            == plan.logical_account_id
        )
        mapping_safe = (
            binding_safe
            and capabilities.get("receipt_mapping") is True
            and bool(observed_order_id)
            and (not expected_order_id or observed_order_id == expected_order_id)
            and row.get("reconcile_complete") is True
            and receipt.normalized_status() != BrokerStatus.UNKNOWN
            and receipt.conclusive
        )
        if not mapping_safe:
            return replace(
                receipt,
                status=BrokerStatus.UNKNOWN,
                account_binding="proven" if binding_safe else "not_proven",
                reason=str(
                    row.get("status_reason")
                    or row.get("reason")
                    or "LIVE_RECONCILE_RECEIPT_UNPROVEN"
                ),
                error_code="LIVE_RECONCILE_RECEIPT_UNPROVEN",
                conclusive=False,
            )
        return replace(receipt, account_binding="proven")

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
        if stage in {"prepare", "submit"}:
            for key in ("submitted", "saved", "started", "form_closed"):
                if key in row:
                    field_readback[key] = row[key]
        locator_proof = row.get("locator_proof")
        locator_proof = dict(locator_proof) if isinstance(locator_proof, dict) else {}
        echoed: dict[str, Any] = {}
        if stage in {"prepare", "submit"}:
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
            strategy_id=str(row.get("strategy_id") or "") or None,
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


__all__ = [
    "FounderscQuantOpenCLIAdapter",
    "OpenCLIAdapterError",
    "release_foundersc_opencli_site_session",
    "resolve_connected_opencli_profile",
]
