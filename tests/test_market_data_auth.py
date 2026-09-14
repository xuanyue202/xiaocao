import pytest

from xiaocao.api.client import XiaocaoClient
from xiaocao.api.errors import ApiAuthError


class Response:
    status_code = 200

    def __init__(self, code):
        self.code = code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def json(self):
        return {"code": self.code, "msg": "登录已失效，请重新登录", "result": []}


def test_expired_auth_is_not_retried_or_cached(monkeypatch):
    client = XiaocaoClient(retries=3)
    calls = []
    monkeypatch.setattr(client._session, "post", lambda *a, **kw: calls.append(kw) or Response(990502))
    with pytest.raises(ApiAuthError, match="990502"):
        client.get_industry_block_rank("2026-09-14", 0)
    assert len(calls) == 1


def test_configured_token_is_read_at_request_boundary(monkeypatch):
    client = XiaocaoClient(retries=0)
    seen = []
    def post(*args, **kwargs):
        assert kwargs.get("allow_redirects") is False
        seen.append(kwargs.get("headers", {}).get("token"))
        return Response(8200)
    monkeypatch.setattr(client._session, "post", post)
    monkeypatch.setenv("XIAOCAO_API_TOKEN", "first-fixture")
    client.get_industry_block_rank("2026-09-14", 0)
    monkeypatch.setenv("XIAOCAO_API_TOKEN", "rotated-fixture")
    client.get_industry_block_rank("2026-09-14", 0)
    assert seen == ["first-fixture", "rotated-fixture"]
    assert "fixture" not in repr(client)


def test_ambient_token_is_not_sent_to_another_host(monkeypatch):
    monkeypatch.setenv("XIAOCAO_API_TOKEN", "private-fixture")
    client = XiaocaoClient(base_url="https://unrelated.example", retries=0)
    seen = []
    monkeypatch.setattr(client._session, "post", lambda *a, **kw: seen.append(kw) or Response(8200))
    client.get_industry_block_rank("2026-09-14", 0)
    assert not seen[0].get("headers", {}).get("token")
