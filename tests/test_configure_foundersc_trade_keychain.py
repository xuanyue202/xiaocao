from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "configure_foundersc_trade_keychain.py"
    )
    spec = importlib.util.spec_from_file_location(
        "configure_foundersc_trade_keychain_for_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _InteractiveInput:
    def isatty(self) -> bool:
        return True


class _NonInteractiveInput:
    def isatty(self) -> bool:
        return False


def test_configuration_refuses_noninteractive_input(monkeypatch) -> None:
    module = _load_script()
    monkeypatch.setattr(module.sys, "stdin", _NonInteractiveInput())

    with pytest.raises(SystemExit, match="interactive terminal required"):
        module.main()


def test_configuration_refuses_existing_account_mismatch(monkeypatch) -> None:
    module = _load_script()
    monkeypatch.setattr(module.sys, "stdin", _InteractiveInput())
    monkeypatch.setattr(module, "_existing_account", lambda: (True, "1234567890"))
    monkeypatch.setattr("builtins.input", lambda _: "configure-trade-password")
    monkeypatch.setattr(module.getpass, "getpass", lambda _: "1111111111")
    stored: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "_store", lambda account, secret: stored.append((account, secret)))

    with pytest.raises(SystemExit, match="differs from the existing fixed item"):
        module.main()

    assert stored == []


def test_configuration_uses_hidden_inputs_and_emits_no_raw_values(
    monkeypatch,
    capsys,
) -> None:
    module = _load_script()
    account = "1234567890"
    secret = "test-secret"
    hidden_inputs = iter([account, secret, secret])
    stored: list[tuple[str, str]] = []

    class _Preflight:
        def run(self, **_kwargs):
            return {
                "trade_item_present": True,
                "trade_account_present": True,
                "trade_account_length": len(account),
                "trade_secret_readable": True,
                "trade_secret_nonempty": True,
            }

    monkeypatch.setattr(module.sys, "stdin", _InteractiveInput())
    monkeypatch.setattr(module, "_existing_account", lambda: (False, ""))
    monkeypatch.setattr("builtins.input", lambda _: "configure-trade-password")
    monkeypatch.setattr(module.getpass, "getpass", lambda _: next(hidden_inputs))
    monkeypatch.setattr(module, "_store", lambda acct, value: stored.append((acct, value)))
    monkeypatch.setattr(module, "FounderscKeychainPreflight", _Preflight)

    assert module.main() == 0
    output = capsys.readouterr().out

    assert stored == [(account, secret)]
    assert account not in output
    assert secret not in output
    assert "trade account length: 10" in output
