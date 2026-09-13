from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEMPLATE_ROOT = ROOT / "opencli" / "clis" / "foundersc-quant"

def _source(name: str) -> str:
    return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")


def test_no_template_clicks_a_broker_action_or_reads_credentials():
    source = "\n".join(
        _source(name)
        for name in (
            "common.mjs",
            "probe.js",
            "prepare.js",
            "reconcile.js",
            "recover.js",
            "environment.js",
        )
    )
    dangerous_click = re.compile(
        r"(?:买入|卖出|保存|启动|确定|全部撤单)[^\n]*\.click\(|\.click\([^\n]*(?:买入|卖出|保存|启动|确定|全部撤单)"
    )
    assert dangerous_click.search(source) is None
    for forbidden in (
        "document.cookie",
        "localStorage",
        "sessionStorage",
        "PASSWORD",
        "PassGuard",
        "pwdSetSk",
        "checkTradePassword",
    ):
        assert forbidden not in source
    assert r"\b\d{8,20}\b" in source


def test_login_reads_only_the_fixed_keychain_item_and_redacts_process_output():
    source = _source("login.js")

    assert "xiaocao.foundersc.quant.login" in source
    assert "spawnSync" in source
    assert "find-generic-password" in source
    assert "'-w'" in source
    assert "timeout: 8000" in source
    assert "maxBuffer: 16384" in source
    assert "access: 'write'" in source
    assert "password_secret_present" in source
    assert "login_account_fingerprint" in source
    assert "password_value" not in source
    assert "account_value" not in source
    assert "console.log" not in source
    assert "process.argv" not in source
    assert "kwargs.password" not in source
    assert "kwargs.account" not in source
    for forbidden in ("保存", "启动", "买入", "卖出", "撤单"):
        assert forbidden not in source
