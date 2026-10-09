"""Exercise the production recovery CLI through durable attempt state."""
import json
from unittest.mock import Mock

import pytest
import requests

from scripts import configure_market_data_auth as setup
from xiaocao.api import auth


@pytest.fixture
def recovery(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup.sys, "argv", ["configure_market_data_auth.py", "--captcha-from-keychain"])
    monkeypatch.setattr(setup.sys, "stdin", Mock(isatty=lambda: True))
    monkeypatch.setattr(auth, "_login_state_directory", lambda: tmp_path / "state")
    secrets = {auth.SERVICE: "expired", auth.CREDENTIALS_SERVICE: json.dumps(
        {"username": "fixture-user", "password": "fixture-password"})}
    monkeypatch.setattr(auth, "_read_keychain_secret", lambda service: secrets.get(service, ""))
    monkeypatch.setattr(auth, "_store_keychain_secret", secrets.__setitem__)
    monkeypatch.setattr(setup, "agent_captcha_input", lambda _: "AB12")
    sessions = []
    outcomes = []

    def new_session():
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)

        def post(url, **kwargs):
            response = Mock()
            if url.endswith("getCaptcha"):
                response.json.return_value = {"code": 8200, "result":
                    "data:image/png;base64,iVBORw0KGgo="}
            else:
                outcome = outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                response.json.return_value = outcome
            return response

        session.post.side_effect = post
        sessions.append(session)
        return session

    monkeypatch.setattr(setup.requests, "Session", new_session)
    return secrets, sessions, outcomes, tmp_path


def accepted():
    return {"code": 8200, "result": {"token": "fresh-session"}}


def assert_redacted(capsys, root):
    captured = capsys.readouterr()
    text = captured.out + captured.err
    state = root / "state/last-attempt.json"
    if state.exists():
        text += state.read_text()
    for private in ("fixture-password", "fresh-session", "AB12", "unknown-private-detail", "private-transport-detail"):
        assert private not in text
    return captured.out


@pytest.mark.parametrize("rejections", [0, 1, 2])
def test_fresh_challenge_retries_then_saves_and_cleans(recovery, capsys, rejections):
    secrets, sessions, outcomes, root = recovery
    outcomes.extend([{"code": 9001, "msg": "验证码错误"}] * rejections + [accepted()])
    assert setup.main() == 0
    assert secrets[auth.SERVICE] == "fresh-session"
    assert len(sessions) == rejections + 1
    for session in sessions:
        assert [call.args[0].rsplit("/", 1)[-1] for call in session.post.call_args_list] == ["getCaptcha", "login"]
    assert not list((root / "output/.cache/market-captcha").glob("challenge-*"))
    assert json.loads((root / "state/last-attempt.json").read_text())["status"] == "completed"
    assert_redacted(capsys, root)


def test_three_explicit_captcha_rejections_bound_one_invocation(recovery, capsys):
    secrets, sessions, outcomes, root = recovery
    outcomes.extend([{"code": 9001, "msg": "验证码错误"}] * 3)
    assert setup.main() == 2
    assert len(sessions) == 3 and secrets[auth.SERVICE] == "expired"
    assert not list((root / "output/.cache/market-captcha").glob("challenge-*"))
    assert_redacted(capsys, root)


@pytest.mark.parametrize("outcome,category", [
    ({"code": 9001, "msg": "用户名或密码错误"}, "MARKET_PASSWORD_REJECTED"),
    ({"code": 9001, "msg": "账户已锁定"}, "MARKET_ACCOUNT_LOCKED"),
    ({"code": 9001, "msg": "unknown-private-detail"}, "MARKET_LOGIN_REJECTED_UNCLASSIFIED"),
    (requests.Timeout("private-transport-detail"), "MARKET_LOGIN_TRANSPORT_FAILED"),
    ({"code": 8200, "result": {}}, "MARKET_LOGIN_SESSION_MISSING"),
])
def test_password_or_uncertain_result_fences_next_cli(recovery, capsys, outcome, category):
    secrets, sessions, outcomes, root = recovery
    before = dict(secrets)
    outcomes.append(outcome)
    assert setup.main() == 2
    assert setup.main() == 2
    assert len(sessions) == 1 and secrets == before
    assert category in assert_redacted(capsys, root)
    assert not list((root / "output/.cache/market-captcha").glob("challenge-*"))


@pytest.mark.parametrize("service", [auth.CREDENTIALS_SERVICE, auth.SERVICE])
def test_keychain_write_failure_keeps_uncertain_attempt_fenced(recovery, monkeypatch, capsys, service):
    secrets, sessions, outcomes, root = recovery
    outcomes.append(accepted())
    def store(name, value):
        if name == service:
            raise RuntimeError("market_keychain_write_failed")
        secrets[name] = value
    monkeypatch.setattr(auth, "_store_keychain_secret", store)
    assert setup.main() == 2
    assert setup.main() == 2
    assert len(sessions) == 1
    assert json.loads((root / "state/last-attempt.json").read_text())["status"] == "attempt_claimed"
    assert_redacted(capsys, root)


def test_hidden_input_timeout_cleans_image_without_password_claim(recovery, monkeypatch, capsys):
    _, sessions, _, root = recovery
    monkeypatch.setattr(setup, "agent_captcha_input", Mock(side_effect=RuntimeError("market_agent_captcha_timeout")))
    assert setup.main() == 2
    assert sessions[0].post.call_count == 1
    assert not (root / "state/last-attempt.json").exists()
    assert not list((root / "output/.cache/market-captcha").glob("challenge-*"))
    assert_redacted(capsys, root)


def test_rotated_session_reused_before_fetch_or_password(recovery, monkeypatch, capsys):
    secrets, sessions, _, root = recovery
    def observed():
        secrets[auth.SERVICE] = "concurrently-rotated"
        return "expired"
    monkeypatch.setattr(setup, "read_keychain_token", observed)
    assert setup.main() == 0
    assert sessions == []
    assert_redacted(capsys, root)
