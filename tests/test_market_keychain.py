from types import SimpleNamespace

import pytest

from xiaocao.api import auth
from xiaocao.api.client import XiaocaoClient


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv(auth.TOKEN_ENV, raising=False)
    monkeypatch.setattr(auth.sys, "platform", "darwin")
    auth.invalidate_token_cache()
    yield
    auth.invalidate_token_cache()


def test_keychain_reads_cached_then_invalidated_and_environment_overrides(monkeypatch):
    reads = []
    monkeypatch.setattr(auth, "read_keychain_token", lambda: reads.append(1) or f"secret-{len(reads)}")
    assert auth.load_market_token() == auth.load_market_token() == "secret-1"
    auth.invalidate_token_cache()
    assert auth.load_market_token() == "secret-2"
    monkeypatch.setenv(auth.TOKEN_ENV, "explicit")
    assert auth.load_market_token() == "explicit"
    monkeypatch.setenv(auth.TOKEN_ENV, "")
    assert auth.load_market_token() == ""
    assert len(reads) == 2


def test_storage_uses_pipe_not_argv_or_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(auth.subprocess, "run", lambda argv, **kw: calls.append((argv, kw)) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(auth, "read_keychain_token", lambda: "secret-fixture")
    auth.store_market_token("secret-fixture")
    argv, kw = calls[0]
    assert "secret-fixture" not in str(argv)
    assert "env" not in kw
    assert kw["input"] == b"secret-fixture\n"
    assert kw["capture_output"]


def test_failed_read_returns_no_secret(monkeypatch):
    monkeypatch.setattr(auth.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=44, stdout=b""))
    assert auth.read_keychain_token() == ""


def test_auth_rejection_reloads_replaced_keychain_on_next_call(monkeypatch):
    from xiaocao.api.errors import ApiAuthError
    tokens = iter(["old-fixture", "new-fixture"])
    monkeypatch.setattr(auth, "read_keychain_token", lambda: next(tokens))
    calls = []
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def json(self): return {"code": 990502 if len(calls) == 1 else 8200, "result": []}
    def post(*a, **kw):
        calls.append(kw["headers"]["token"])
        assert kw["allow_redirects"] is False
        return Response()
    c = XiaocaoClient(retries=3)
    monkeypatch.setattr(c._session, "post", post)
    with pytest.raises(ApiAuthError):
        c.get_industry_block_rank("2026-09-14", 0)
    assert calls == ["old-fixture"]
    assert c.get_industry_block_rank("2026-09-14", 0) == []
    assert calls == ["old-fixture", "new-fixture"]


@pytest.mark.parametrize("url", ["https://unrelated.example", "http://p-xcapi.kjap1.cn", "https://p-xcapi.kjap1.cn.evil.example"])
def test_custom_or_insecure_hosts_never_read_keychain(monkeypatch, url):
    def forbidden():
        pytest.fail("credential read for an unapproved host")
    monkeypatch.setattr(auth, "load_market_token", forbidden)
    client = XiaocaoClient(base_url=url, retries=0)
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def json(self): return {"code": 8200, "result": []}
    def post(*a, **kw):
        assert "token" not in kw.get("headers", {})
        return Response()
    monkeypatch.setattr(client._session, "post", post)
    assert client.get_industry_block_rank("2026-09-14", 0) == []
