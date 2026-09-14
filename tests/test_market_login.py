from unittest.mock import Mock

import pytest

from xiaocao.api import auth
from xiaocao.api.errors import ApiAuthError


@pytest.fixture(autouse=True)
def isolate_platform(monkeypatch):
    monkeypatch.setattr(auth.sys, "platform", "darwin")


def test_official_password_encoding_matches_frontend_vector():
    assert auth.encode_login_field("fixture-password") == "QraiA9zGXt3WRpDmw3aRI/6f8zXQ/qKfkKKzs0jyJBw="


def test_login_uses_official_host_and_encrypted_body(monkeypatch):
    response = Mock()
    response.json.return_value = {"code": 8200, "result": {"token": "new-session"}}
    post = Mock(return_value=response)
    monkeypatch.setattr(auth.requests, "post", post)
    assert auth.login_with_credentials("13800000000", "fixture-password") == "new-session"
    args, kwargs = post.call_args
    assert args[0] == "https://p-xcapi.topxlc.com/user/v2/login"
    assert kwargs["allow_redirects"] is False
    assert kwargs["json"]["params"]["passwd"] != "fixture-password"
    assert kwargs["json"]["params"]["loginId"] != "13800000000"


def test_challenge_does_not_return_token_or_expose_server_text(monkeypatch):
    response = Mock()
    response.json.return_value = {"code": 9001, "msg": "fixture-password", "result": None}
    monkeypatch.setattr(auth.requests, "post", Mock(return_value=response))
    with pytest.raises(ApiAuthError) as error:
        auth.login_with_credentials("13800000000", "fixture-password")
    assert "fixture-password" not in str(error.value)
    assert "MARKET_LOGIN_REQUIRES_USER" in str(error.value)


def test_renewal_reuses_other_process_rotation(monkeypatch, tmp_path):
    monkeypatch.delenv(auth.TOKEN_ENV, raising=False)
    monkeypatch.setattr(auth, "_login_state_directory", lambda: tmp_path)
    monkeypatch.setattr(auth, "read_keychain_token", lambda: "already-rotated")
    login = Mock()
    monkeypatch.setattr(auth, "login_with_credentials", login)
    assert auth.renew_market_token("expired") == "already-rotated"
    login.assert_not_called()


def test_failed_login_is_cooled_down_without_overwriting_session(monkeypatch, tmp_path):
    monkeypatch.delenv(auth.TOKEN_ENV, raising=False)
    monkeypatch.setattr(auth, "_login_state_directory", lambda: tmp_path)
    monkeypatch.setattr(auth, "read_keychain_token", lambda: "expired")
    monkeypatch.setattr(auth, "read_credentials", lambda: ("13800000000", "fixture-password"))
    login = Mock(side_effect=ApiAuthError("MARKET_LOGIN_REQUIRES_USER"))
    store = Mock()
    monkeypatch.setattr(auth, "login_with_credentials", login)
    monkeypatch.setattr(auth, "store_market_token", store)
    for _ in range(2):
        with pytest.raises(ApiAuthError):
            auth.renew_market_token("expired")
    assert login.call_count == 1
    store.assert_not_called()


def test_client_replays_read_only_once_after_login(monkeypatch):
    from xiaocao.api.client import XiaocaoClient
    tokens = iter(["old", "new"])
    monkeypatch.setattr(auth, "load_market_token", lambda: next(tokens))
    renew = Mock(return_value="new")
    monkeypatch.setattr(auth, "renew_market_token", renew)
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"code": 990502}
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    client = XiaocaoClient(retries=3)
    post = Mock(return_value=response)
    monkeypatch.setattr(client._session, "post", post)
    with pytest.raises(ApiAuthError):
        client.get_industry_block_rank("2026-09-14", 0)
    assert post.call_count == 2
    renew.assert_called_once_with("old")


def test_provisioning_does_not_save_bad_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "_login_state_directory", lambda: tmp_path)
    monkeypatch.setattr(auth, "login_with_credentials", Mock(side_effect=ApiAuthError("MARKET_LOGIN_REQUIRES_USER")))
    store = Mock()
    monkeypatch.setattr(auth, "_store_keychain_secret", store)
    with pytest.raises(ApiAuthError):
        auth.configure_credentials("13800000000", "fixture-password")
    store.assert_not_called()


def test_concurrent_processes_login_once_and_share_new_session(monkeypatch, tmp_path):
    import multiprocessing
    import time

    monkeypatch.delenv(auth.TOKEN_ENV, raising=False)
    monkeypatch.setattr(auth, "_login_state_directory", lambda: tmp_path)
    session = tmp_path / "fixture-session"
    session.write_text("expired")
    calls = tmp_path / "fixture-login-count"
    monkeypatch.setattr(auth, "read_keychain_token", session.read_text)
    monkeypatch.setattr(auth, "read_credentials", lambda: ("fixture-user", "fixture-password"))
    monkeypatch.setattr(auth, "store_market_token", session.write_text)

    def login(*_):
        with calls.open("a") as stream:
            stream.write("login\n")
        time.sleep(0.2)
        return "rotated"

    monkeypatch.setattr(auth, "login_with_credentials", login)
    context = multiprocessing.get_context("fork")
    start = context.Event()
    results = context.Queue()

    def worker():
        start.wait(3)
        results.put(auth.renew_market_token("expired"))

    workers = [context.Process(target=worker) for _ in range(2)]
    try:
        for process in workers:
            process.start()
        start.set()
        assert [results.get(timeout=5) for _ in workers] == ["rotated", "rotated"]
        for process in workers:
            process.join(5)
            assert process.exitcode == 0
        assert calls.read_text().splitlines() == ["login"]
    finally:
        for process in workers:
            if process.is_alive():
                process.terminate()
                process.join(5)
        results.close()
