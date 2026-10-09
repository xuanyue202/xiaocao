"""Fresh household-context adapters for KOL decisions."""

from __future__ import annotations

import json
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request

import requests

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10 compatibility
    import tomli as tomllib

from .decisions import DecisionError


LIANGHUI_MCP_CONFIG_ENV = "LIANGHUI_MCP_CONFIG"


def default_lianghui_mcp_config() -> Path:
    """Resolve the user-global Codex config, with an explicit test override."""

    override = os.environ.get(LIANGHUI_MCP_CONFIG_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        return Path(codex_home).expanduser() / "config.toml"
    return Path.home() / ".codex" / "config.toml"


DEFAULT_LIANGHUI_MCP_CONFIG = default_lianghui_mcp_config()


class LiangHuiMcpError(DecisionError):
    """Structured LiangHui JSON-RPC application error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "",
        data: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.data = data or {}



def _receipt_covers_broker_absence(row: dict[str, Any], receipt: dict[str, Any]) -> bool:
    if (row.get("brokerPositionStatus") != "absence_pending"
            or row.get("positionObservationSource") != "broker_sync"
            or any(type(row.get(field)) not in {int, float} or row[field] != 0
                   for field in ("currentAmount", "costAmount"))):
        return False
    if row.get("brokerSecurityKind") == "cash":
        return (receipt.get("cashScope") == "complete_native_currency_balances"
                and row.get("currency") in receipt.get("pendingCashCurrencies", [])
                and row.get("brokerSymbol") == f"CASH.{row.get('currency')}")
    return (receipt.get("scope") == "complete_unfiltered_stock_positions"
            and row.get("brokerSymbol") in receipt.get("pendingAbsenceSymbols", [])
            and type(row.get("holdingQuantity")) in {int, float}
            and row["holdingQuantity"] == 0)

class LiangHuiMcpClient:
    """Use the existing authenticated family MCP without copying credentials."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str],
        *,
        opener: Callable[..., Any] | None = None,
    ):
        self.url = url
        self.headers = dict(headers)
        self.opener = opener
        self.session = requests.Session() if opener is None else None

    @classmethod
    def from_config(
        cls,
        path: Path | str | None = None,
    ) -> "LiangHuiMcpClient":
        config_path = Path(
            path if path is not None else default_lianghui_mcp_config()
        ).expanduser().resolve()
        try:
            mode = stat.S_IMODE(config_path.stat().st_mode)
            if mode & 0o077:
                raise DecisionError(
                    f"亮灰 MCP config must be private (mode 0600): {config_path}"
                )
            raw = config_path.read_bytes()
            if config_path.suffix.lower() == ".toml":
                config = tomllib.loads(raw.decode("utf-8"))
                server = config["mcp_servers"]["lianghui"]
                headers_value = server.get("http_headers", {})
            else:
                config = json.loads(raw.decode("utf-8"))
                server = config["mcpServers"]["lianghui"]
                headers_value = server.get("headers", {})
            if server.get("enabled") is False:
                raise DecisionError(f"亮灰 MCP is disabled: {config_path}")
            url = str(server["url"])
            headers = {
                str(key): str(value)
                for key, value in headers_value.items()
            }
            if not url.startswith("https://") or not headers:
                raise DecisionError(f"invalid 亮灰 MCP endpoint: {config_path}")
        except (
            OSError,
            KeyError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
        ) as exc:
            raise DecisionError(f"invalid 亮灰 MCP config: {config_path}") from exc
        return cls(url, headers)

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            ensure_ascii=False,
        ).encode()
        try:
            if self.opener is None:
                response = self.session.post(
                    self.url,
                    data=body,
                    headers={"Content-Type": "application/json", **self.headers},
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
            else:
                request = Request(
                    self.url,
                    data=body,
                    headers={"Content-Type": "application/json", **self.headers},
                    method="POST",
                )
                with self.opener(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            requests.RequestException,
        ) as exc:
            raise DecisionError("亮灰 MCP request failed") from exc
        if payload.get("error"):
            error = payload["error"]
            data = error.get("data") if isinstance(error, dict) else None
            message = (
                error.get("message", "unknown MCP error")
                if isinstance(error, dict)
                else "unknown MCP error"
            )
            raise LiangHuiMcpError(
                f"亮灰 MCP rejected request: {message}",
                code=str((data or {}).get("code") or ""),
                data=data if isinstance(data, dict) else {},
            )
        return payload.get("result")

    def _tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        structured = (
            result.get("structuredContent")
            if isinstance(result, dict)
            else None
        )
        if isinstance(structured, dict):
            return structured
        try:
            return json.loads(result["content"][0]["text"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise DecisionError(f"亮灰 MCP returned invalid tool result: {name}") from exc

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Public small-tool seam used by the durable publication ledger."""
        attempts = 3 if name == "get_kol_write_status" else 1
        for attempt in range(1, attempts + 1):
            try:
                return self._tool(name, arguments)
            except DecisionError as exc:
                if attempt == attempts or not isinstance(
                    exc.__cause__,
                    (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
                ):
                    raise
                time.sleep(0.5 * attempt)

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the live MCP registry for a production contract preflight."""

        result = self._rpc("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list) or not all(
            isinstance(tool, dict) and isinstance(tool.get("name"), str)
            for tool in tools
        ):
            raise DecisionError("亮灰 MCP returned invalid tools/list result")
        return tools

    def _resource(self, uri: str) -> Any:
        result = self._rpc("resources/read", {"uri": uri})
        try:
            return json.loads(result["contents"][0]["text"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise DecisionError(f"亮灰 MCP returned invalid resource: {uri}") from exc

    def load_context(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        as_of_date = checked_at[:10]
        current_user = self._resource("user://current")
        decision_view = self._tool("get_portfolio_decision_view", {"asOfDate": as_of_date})
        reconciliation = self._tool(
            "get_portfolio_reconciliation_view", {"asOfDate": as_of_date}
        )
        family_id = str(current_user.get("familyId") or "").strip()
        positions = reconciliation.get("items") if isinstance(reconciliation, dict) else None
        if not family_id or not isinstance(positions, list):
            raise DecisionError("亮灰 MCP omitted familyId or portfolio positions")
        # read_at 是本次 MCP 读取时间；券商仓位时点只来自完成回执。
        managed = [row for row in positions if row.get("brokerConnectionId")]
        broker_sources = []
        degraded = False
        for connection_id in sorted({row["brokerConnectionId"] for row in managed}):
            rows = [row for row in managed if row["brokerConnectionId"] == connection_id]
            try:
                connection = self._resource(f"finance://broker-connections/{connection_id}")
                receipt_id = connection.get("lastCompleteReceiptId")
                if not receipt_id:
                    raise DecisionError("broker complete receipt missing")
                receipt = self._resource(
                    f"finance://broker-connections/{connection_id}/receipts/{receipt_id}"
                )
                stock_observed = receipt.get("brokerObservedAt")
                observed_times = [stock_observed]
                row_times = []
                for row in rows:
                    row_observed = stock_observed
                    if row.get("brokerSecurityKind") == "cash":
                        currency = row.get("currency")
                        if (receipt.get("cashScope") != "complete_native_currency_balances"
                                or (currency not in receipt.get("cashCurrencies", [])
                                    and not _receipt_covers_broker_absence(row, receipt))
                                or row.get("brokerSymbol") != f"CASH.{currency}"):
                            raise DecisionError("broker cash coverage unproven")
                        row_observed = receipt.get("cashObservedAt")
                        observed_times.append(row_observed)
                    row_times.append(row_observed)
                parsed_times = [datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                                for value in observed_times]
                observed = min(zip(parsed_times, observed_times), key=lambda item: item[0])[1]
                ages = [(datetime.now(timezone.utc) - value).total_seconds()
                        for value in parsed_times]
                proven = (
                    receipt.get("status") == "complete"
                    and receipt.get("connectionId") == connection_id
                    and receipt.get("familyId") == family_id
                    and receipt.get("positionsVersion") == connection.get("positionsVersion")
                    and all(row.get("brokerSyncReceiptId") == receipt_id
                            and row.get("positionsVersion") == receipt.get("positionsVersion")
                            and row.get("brokerObservedAt") == row_observed
                            for row, row_observed in zip(rows, row_times))
                )
                fresh = (proven and all(0 <= age <= 1800 for age in ages) and connection.get("enabled") is True
                         and connection.get("authStatus") == "ready"
                         and connection.get("syncStatus") in {"synced", "unchanged"}
                         and all((row.get("brokerPositionStatus") == "present"
                                  or _receipt_covers_broker_absence(row, receipt))
                                 and row.get("positionObservationSource") in {None, "broker_sync"}
                                 and row.get("positionObservationId") in {None, receipt_id} for row in rows))
                source = {"connection_id": connection_id, "receipt_id": receipt_id,
                          "observed_at": observed if proven else None,
                          "status": "fresh" if fresh else "stale_or_degraded",
                          "reference": f"finance://broker-connections/{connection_id}/receipts/{receipt_id}"}
                if any(row.get("brokerSecurityKind") == "cash" for row in rows):
                    source["cash_observed_at"] = receipt.get("cashObservedAt")
                source["effective_observations"] = [
                    {"asset_id": row.get("assetId"), "source": row.get("positionObservationSource") or "broker_sync",
                     "observed_at": row.get("positionObservedAt") or row.get("brokerObservedAt"),
                     "receipt_id": row.get("positionObservationId") or row.get("brokerSyncReceiptId")}
                    for row in rows
                ]
                if any(row.get("positionObservationSource") == "screenshot" for row in rows):
                    source["degraded_reason"] = "SCREENSHOT_OVERRIDE"
                degraded = degraded or not fresh
            except (DecisionError, ValueError, TypeError, AttributeError):
                degraded = True
                source = {"connection_id": connection_id, "observed_at": None,
                          "status": "unproven", "reference": None}
            broker_sources.append(source)
        observed_values = [row["observed_at"] for row in broker_sources if row.get("observed_at")]
        broker_observed_at = min(observed_values) if broker_sources and len(observed_values) == len(broker_sources) else None
        return {
            "read_at": checked_at,
            "broker_positions_observed_at": broker_observed_at,
            "broker_positions_status": "degraded" if degraded else "fresh" if managed else "not_managed",
            "broker_sync_sources": broker_sources,
            "valuation_complete": decision_view.get("valuationComplete", not managed),
            "family_id": family_id,
            "as_of": checked_at,
            "source_reference": (
                "lianghui-mcp://user/current+get_portfolio_decision_view"
                "+get_portfolio_reconciliation_view"
            ),
            "positions": positions,
            "decision_view": decision_view,
        }
