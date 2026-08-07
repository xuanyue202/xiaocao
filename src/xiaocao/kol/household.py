"""Fresh household-context adapters for KOL decisions."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

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


class LiangHuiMcpClient:
    """Use the existing authenticated family MCP without copying credentials."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str],
        *,
        opener: Callable[..., Any] = urlopen,
    ):
        self.url = url
        self.headers = dict(headers)
        self.opener = opener

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
        request = Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", **self.headers},
            method="POST",
        )
        try:
            with self.opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
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

        return self._tool(name, arguments)

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
        return {
            "family_id": family_id,
            "as_of": checked_at,
            "source_reference": (
                "lianghui-mcp://user/current+get_portfolio_decision_view"
                "+get_portfolio_reconciliation_view"
            ),
            "positions": positions,
            "decision_view": decision_view,
        }
