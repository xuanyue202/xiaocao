"""Saved market credentials recover once without prompting a human."""
import json
from unittest.mock import Mock

import pytest

from xiaocao.api import auth
from xiaocao.api.errors import ApiAuthError


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(auth.sys, "platform", "darwin")
    monkeypatch.setattr(auth, "_login_state_directory", lambda: tmp_path)
    monkeypatch.setattr(auth, "_rejected_session_hash", "")
    monkeypatch.delenv(auth.TOKEN_ENV, raising=False)
    auth.invalidate_token_cache()
    yield
    auth.invalidate_token_cache()


def test_two_recovery_owners_fetch_and_submit_one_challenge(monkeypatch, tmp_path):
    import multiprocessing
    import time
    token = tmp_path / "fixture-token"
    token.write_text("expired")
    calls = tmp_path / "calls"
    monkeypatch.setattr(auth, "read_keychain_token", token.read_text)
    monkeypatch.setattr(auth, "_store_keychain_secret", lambda *a: None)
    monkeypatch.setattr(auth, "store_market_token", token.write_text)
    def login(*a, **k):
        with calls.open("a") as stream:
            stream.write("login\n")
        time.sleep(.1)
        return "rotated"
    monkeypatch.setattr(auth, "login_with_credentials", login)
    context = multiprocessing.get_context("fork")
    start, results = context.Event(), context.Queue()
    def worker():
        start.wait(3)
        with auth.captcha_recovery_owner("expired") as owned:
            if owned:
                with calls.open("a") as stream:
                    stream.write("challenge\n")
                auth.configure_credentials("fixture-user", "fixture-password", captcha_code="AB12")
            results.put(owned)
    workers = [context.Process(target=worker) for _ in range(2)]
    try:
        for process in workers:
            process.start()
        start.set()
        assert sorted(results.get(timeout=5) for _ in workers) == [False, True]
        for process in workers:
            process.join(5)
            assert process.exitcode == 0
        assert calls.read_text().splitlines() == ["challenge", "login"]
    finally:
        for process in workers:
            if process.is_alive():
                process.terminate()
                process.join(5)
        results.close()


def test_rejected_login_cools_before_another_challenge(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "read_keychain_token", lambda: "expired")
    login = Mock(side_effect=ApiAuthError("MARKET_LOGIN_REQUIRES_USER"))
    monkeypatch.setattr(auth, "login_with_credentials", login)
    with pytest.raises(ApiAuthError, match="MARKET_LOGIN_REQUIRES_USER"):
        with auth.captcha_recovery_owner("expired"):
            auth.configure_credentials("user", "password", captcha_code="AB12")
    with pytest.raises(ApiAuthError, match="MARKET_LOGIN_REQUIRES_USER"):
        with auth.captcha_recovery_owner("expired"):
            pytest.fail("must not fetch another challenge")
    assert login.call_count == 1
    state = (tmp_path / "last-attempt.json").read_text()
    assert json.loads(state)["status"] == "rejected"
    assert "password" not in state and "AB12" not in state


def test_explicit_challenge_rejection_is_typed_without_server_text(monkeypatch):
    response = Mock()
    response.json.return_value = {"code": 9001, "msg": "验证码错误 private-server-detail"}
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: response)
    with pytest.raises(ApiAuthError) as error:
        auth.login_with_credentials("user", "password", captcha_code="AB12")
    assert error.value.failure_category == "MARKET_CAPTCHA_REJECTED"
    assert "private-server-detail" not in str(error.value)


def test_rejected_token_is_not_resent_until_keychain_rotates(monkeypatch):
    token = ["expired"]
    monkeypatch.setattr(auth, "read_keychain_token", lambda: token[0])
    monkeypatch.setattr(auth, "read_credentials", lambda: ("user", "password"))
    with pytest.raises(ApiAuthError):
        auth.renew_market_token("expired")
    with pytest.raises(ApiAuthError, match="MARKET_LOGIN_CAPTCHA_REQUIRED"):
        auth.load_market_token()
    token[0] = "rotated"
    assert auth.load_market_token() == "rotated"
    assert auth.load_market_token() == "rotated"


@pytest.mark.parametrize("category", ["MARKET_PASSWORD_REJECTED", "MARKET_ACCOUNT_LOCKED", "MARKET_LOGIN_TRANSPORT_FAILED"])
def test_rejected_or_uncertain_login_does_not_retry_after_time_alone(monkeypatch, tmp_path, category):
    token = ["expired"]
    monkeypatch.setattr(auth, "read_keychain_token", lambda: token[0])
    login = Mock(side_effect=ApiAuthError(category))
    monkeypatch.setattr(auth, "login_with_credentials", login)
    with pytest.raises(ApiAuthError, match=category):
        with auth.captcha_recovery_owner("expired"):
            auth.configure_credentials("user", "password", captcha_code="AB12")
    monkeypatch.setattr(auth.time, "time", lambda: 10**12)
    with pytest.raises(ApiAuthError, match=category):
        with auth.captcha_recovery_owner("expired"):
            pytest.fail("time cannot erase an uncertain password action")
    assert login.call_count == 1
    token[0] = "externally-proved-new-session"
    with auth.captcha_recovery_owner("expired") as owner:
        assert owner is False


@pytest.mark.parametrize("message,category", [
    ("验证码错误 用户名或密码错误", "MARKET_PASSWORD_REJECTED"),
    ("验证码错误 账户已锁定", "MARKET_ACCOUNT_LOCKED"),
])
def test_mixed_rejection_never_retries_password(monkeypatch, message, category):
    response = Mock()
    response.json.return_value = {"code": 9001, "msg": message}
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: response)
    with pytest.raises(ApiAuthError) as error:
        auth.login_with_credentials("user", "password", captcha_code="AB12")
    assert error.value.failure_category == category


def test_exact_legacy_success_state_does_not_block_new_challenge(monkeypatch, tmp_path):
    (tmp_path / "last-attempt.json").write_text(json.dumps({"attempted_at": 1000.0}))
    monkeypatch.setattr(auth, "read_keychain_token", lambda: "expired")
    with auth.captcha_recovery_owner("expired") as owner:
        assert owner is True
