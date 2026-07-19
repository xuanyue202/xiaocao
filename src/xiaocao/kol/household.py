"""Fresh household-context adapters for KOL decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from .decisions import DecisionError


DEFAULT_LIANGHUI_MCP_CONFIG = Path("/Users/bytedance/Downloads/LiangHuiProject/.mcp.json")


class LiangHuiMcpClient:
    """Read current family/portfolio facts without persisting MCP credentials."""

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
    def from_config(cls, path: Path | str = DEFAULT_LIANGHUI_MCP_CONFIG) -> "LiangHuiMcpClient":
        config_path = Path(path).expanduser().resolve()
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            server = config["mcpServers"]["lianghui"]
            url = str(server["url"])
            headers = {str(key): str(value) for key, value in server.get("headers", {}).items()}
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
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
            message = payload["error"].get("message", "unknown MCP error")
            raise DecisionError(f"亮灰 MCP rejected request: {message}")
        return payload.get("result")

    def _tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        try:
            return json.loads(result["content"][0]["text"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise DecisionError(f"亮灰 MCP returned invalid tool result: {name}") from exc

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
