from __future__ import annotations

import json

from xiaocao.kol.household import LiangHuiMcpClient


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
