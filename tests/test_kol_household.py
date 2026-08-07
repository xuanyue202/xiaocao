from __future__ import annotations

import json
from pathlib import Path

import pytest

from xiaocao.kol.decisions import DecisionError
from xiaocao.kol.household import (
    LiangHuiMcpClient,
    default_lianghui_mcp_config,
)


class _Response:
    def __init__(self, value):
        self.body = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


def test_lianghui_context_is_fetched_fresh_from_three_read_only_surfaces():
    calls = []

    def opener(request, timeout):
        payload = json.loads(request.data)
        calls.append((payload["method"], payload["params"]))
        if payload["method"] == "resources/read":
            value = {"familyId": "family-real"}
            result = {"contents": [{"text": json.dumps(value)}]}
        elif payload["params"]["name"] == "get_portfolio_decision_view":
            value = {"totalAssets": 100, "cashAvailable": 20}
            result = {"content": [{"text": json.dumps(value)}]}
        else:
            value = {"items": [{"assetId": "asset-1", "currentAmount": 100}]}
            result = {"content": [{"text": json.dumps(value)}]}
        return _Response({"jsonrpc": "2.0", "id": 1, "result": result})

    client = LiangHuiMcpClient(
        "https://example.test/mcp", {"X-Phone-Number": "secret"}, opener=opener
    )
    first = client.load_context()
    second = client.load_context()

    assert first["family_id"] == "family-real"
    assert first["positions"][0]["assetId"] == "asset-1"
    assert first["decision_view"]["cashAvailable"] == 20
    assert len(calls) == 6
    assert second is not first
    assert all(call[0] in {"resources/read", "tools/call"} for call in calls)


def test_lianghui_client_reuses_private_project_codex_config(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[mcp_servers.lianghui]
url = "https://example.test/mcp"
http_headers = { X-Phone-Number = "phone", X-Password = "password" }
enabled = true
""".strip(),
        encoding="utf-8",
    )
    config_path.chmod(0o600)

    client = LiangHuiMcpClient.from_config(config_path)

    assert client.url == "https://example.test/mcp"
    assert client.headers == {
        "X-Phone-Number": "phone",
        "X-Password": "password",
    }


def test_lianghui_client_rejects_world_readable_credentials(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[mcp_servers.lianghui]
url = "https://example.test/mcp"
http_headers = { X-Phone-Number = "phone", X-Password = "password" }
enabled = true
""".strip(),
        encoding="utf-8",
    )
    config_path.chmod(0o644)

    with pytest.raises(DecisionError, match="mode 0600"):
        LiangHuiMcpClient.from_config(config_path)


def test_lianghui_client_defaults_to_user_global_codex_config(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("LIANGHUI_MCP_CONFIG", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_lianghui_mcp_config() == (
        Path(tmp_path) / ".codex" / "config.toml"
    )


def test_lianghui_client_honors_explicit_config_environment(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "private" / "lianghui.toml"
    monkeypatch.setenv("LIANGHUI_MCP_CONFIG", str(config_path))

    assert default_lianghui_mcp_config() == config_path


def test_lianghui_client_prefers_structured_tool_result():
    def opener(request, timeout):
        payload = json.loads(request.data)
        assert payload["params"]["name"] == "get_kol_write_status"
        return _Response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "structuredContent": {
                        "recordState": "published",
                        "recordId": "kr_example",
                    },
                    "content": [{"text": "not-json"}],
                },
            }
        )

    client = LiangHuiMcpClient(
        "https://example.test/mcp",
        {"X-Phone-Number": "secret"},
        opener=opener,
    )

    assert client.call_tool(
        "get_kol_write_status",
        {"idempotency_key": "claim"},
    ) == {
        "recordState": "published",
        "recordId": "kr_example",
    }


def test_lianghui_client_lists_live_tools():
    def opener(request, timeout):
        payload = json.loads(request.data)
        assert payload["method"] == "tools/list"
        return _Response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {
                            "name": "publish_kol_report",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                },
            }
        )

    client = LiangHuiMcpClient(
        "https://example.test/mcp",
        {"X-Phone-Number": "secret"},
        opener=opener,
    )

    assert [tool["name"] for tool in client.list_tools()] == [
        "publish_kol_report"
    ]
