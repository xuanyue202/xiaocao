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


def test_lianghui_default_transport_reuses_one_requests_session(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"tools": [{"name": "get_kol_record"}]},
            }

    class Session:
        def post(self, url, *, data, headers, timeout):
            calls.append((url, json.loads(data), headers, timeout))
            return Response()

    session = Session()
    monkeypatch.setattr(
        "xiaocao.kol.household.requests.Session",
        lambda: session,
    )
    client = LiangHuiMcpClient(
        "https://example.test/mcp",
        {"X-Phone-Number": "secret"},
    )

    assert [tool["name"] for tool in client.list_tools()] == ["get_kol_record"]
    assert client.session is session
    assert len(calls) == 1


@pytest.mark.parametrize("condition", ["fresh", "old", "mismatch", "unavailable", "failed", "pending", "screenshot"])
def test_broker_household_freshness_comes_from_matching_complete_receipt(condition):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    observed = (now - timedelta(minutes=45 if condition == "old" else 2)).isoformat()
    connection_id = "lb-sg-example"
    row = {"assetId": "asset-1", "brokerConnectionId": connection_id,
           "brokerSyncReceiptId": "receipt", "positionsVersion": 3,
           "brokerObservedAt": observed, "brokerPositionStatus": "absence_pending" if condition == "pending" else "present"}
    if condition == "screenshot":
        row.update(positionObservationSource="screenshot", positionObservedAt=now.isoformat(), positionObservationId="screenshot-receipt")
    def opener(request, timeout):
        payload = json.loads(request.data)
        if payload["method"] == "tools/call":
            value = {"items": [row]} if payload["params"]["name"] == "get_portfolio_reconciliation_view" else {"totalAssets": 100}
            result = {"content": [{"text": json.dumps(value)}]}
        else:
            uri = payload["params"]["uri"]
            if uri == "user://current":
                value = {"familyId": "family-real"}
            elif "/receipts/" in uri:
                if condition == "unavailable":
                    return _Response({"error": {"message": "unavailable"}})
                value = {"status": "complete", "familyId": "family-real", "connectionId": connection_id,
                         "positionsVersion": 4 if condition == "mismatch" else 3, "brokerObservedAt": observed}
            else:
                value = {"enabled": True, "authStatus": "ready", "lastCompleteReceiptId": "receipt",
                         "positionsVersion": 3, "syncStatus": "sync_failed" if condition == "failed" else "synced"}
            result = {"contents": [{"text": json.dumps(value)}]}
        return _Response({"result": result})
    context = LiangHuiMcpClient("https://example.test/mcp", {"X-Phone-Number": "secret"}, opener=opener).load_context()
    assert context["as_of"] == context["read_at"]
    assert context["broker_positions_status"] == ("fresh" if condition == "fresh" else "degraded")
    assert context["broker_positions_observed_at"] == (None if condition in {"mismatch", "unavailable"} else observed)
    assert context["positions"] == [row]
    if condition == "screenshot":
        source = context["broker_sync_sources"][0]
        assert source["degraded_reason"] == "SCREENSHOT_OVERRIDE"
        assert source["effective_observations"][0]["receipt_id"] == "screenshot-receipt"


@pytest.mark.parametrize("condition", ["fresh", "old_cash", "future_cash", "wrong_scope", "wrong_currency", "wrong_time"])
def test_broker_cash_uses_its_own_complete_receipt_coverage(condition):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    stock_at = (now - timedelta(minutes=2)).isoformat()
    cash_at = (now + timedelta(minutes=1) if condition == "future_cash" else now - timedelta(minutes=45 if condition == "old_cash" else 1)).isoformat()
    connection_id = "lb-sg-cash"
    common = {"brokerConnectionId": connection_id, "brokerSyncReceiptId": "receipt", "positionsVersion": 3, "brokerPositionStatus": "present", "positionObservationSource": "broker_sync", "positionObservationId": "receipt"}
    rows = [dict(common, assetId="stock", brokerObservedAt=stock_at),
            dict(common, assetId="cash", brokerObservedAt=stock_at if condition == "wrong_time" else cash_at,
                 brokerSecurityKind="cash", brokerSymbol="CASH.USD", currency="USD")]
    def opener(request, timeout):
        payload = json.loads(request.data)
        if payload["method"] == "tools/call":
            value = {"items": rows} if payload["params"]["name"] == "get_portfolio_reconciliation_view" else {"valuationComplete": True}
            result = {"structuredContent": value}
        else:
            uri = payload["params"]["uri"]
            if uri == "user://current":
                value = {"familyId": "family-real"}
            elif "/receipts/" in uri:
                value = {"status": "complete", "familyId": "family-real", "connectionId": connection_id,
                         "positionsVersion": 3, "brokerObservedAt": stock_at, "cashObservedAt": cash_at,
                         "cashScope": "partial" if condition == "wrong_scope" else "complete_native_currency_balances",
                         "cashCurrencies": ["HKD"] if condition == "wrong_currency" else ["USD"]}
            else:
                value = {"enabled": True, "authStatus": "ready", "lastCompleteReceiptId": "receipt", "positionsVersion": 3, "syncStatus": "synced"}
            result = {"contents": [{"text": json.dumps(value)}]}
        return _Response({"result": result})
    context = LiangHuiMcpClient("https://example.test/mcp", {"X-Phone-Number": "secret"}, opener=opener).load_context()
    assert context["broker_positions_status"] == ("fresh" if condition == "fresh" else "degraded")
    if condition == "fresh":
        assert context["broker_positions_observed_at"] == stock_at
        assert context["broker_sync_sources"][0]["cash_observed_at"] == cash_at
    if condition in {"wrong_scope", "wrong_currency", "wrong_time"}:
        assert context["broker_positions_observed_at"] is None


@pytest.mark.parametrize("kind,condition", [(kind, condition) for kind in ("stock", "cash")
                                            for condition in ("covered", "uncovered", "nonzero", "screenshot")])
def test_complete_api_absence_is_fresh_only_with_explicit_zero_coverage(kind, condition):
    from datetime import datetime, timedelta, timezone
    observed = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    connection_id = "lb-sg-pending"
    row = {"assetId": "asset", "brokerConnectionId": connection_id,
           "brokerSyncReceiptId": "receipt", "positionsVersion": 3,
           "brokerObservedAt": observed, "brokerPositionStatus": "absence_pending",
           "positionObservationSource": "screenshot" if condition == "screenshot" else "broker_sync",
           "positionObservationId": "receipt", "positionObservedAt": observed,
           "currentAmount": 5 if condition == "nonzero" else 0, "costAmount": 0,
           "holdingQuantity": 0, "brokerSecurityKind": kind,
           "brokerSymbol": "CASH.USD" if kind == "cash" else "AAPL.US", "currency": "USD"}
    def opener(request, timeout):
        payload = json.loads(request.data)
        if payload["method"] == "tools/call":
            value = {"items": [row]} if payload["params"]["name"] == "get_portfolio_reconciliation_view" else {}
            result = {"structuredContent": value}
        else:
            uri = payload["params"]["uri"]
            if uri == "user://current":
                value = {"familyId": "family-real"}
            elif "/receipts/" in uri:
                value = {"status": "complete", "familyId": "family-real", "connectionId": connection_id,
                         "positionsVersion": 3, "brokerObservedAt": observed, "cashObservedAt": observed,
                         "scope": "complete_unfiltered_stock_positions", "cashScope": "complete_native_currency_balances",
                         "cashCurrencies": [], "pendingCashCurrencies": [] if condition == "uncovered" else ["USD"],
                         "pendingAbsenceSymbols": [] if condition == "uncovered" else ["AAPL.US"]}
            else:
                value = {"enabled": True, "authStatus": "ready", "lastCompleteReceiptId": "receipt",
                         "positionsVersion": 3, "syncStatus": "synced"}
            result = {"contents": [{"text": json.dumps(value)}]}
        return _Response({"result": result})
    result = LiangHuiMcpClient("https://example.test/mcp", {}, opener=opener).load_context()
    assert result["broker_positions_status"] == ("fresh" if condition == "covered" else "degraded")
