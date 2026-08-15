from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEMPLATE_ROOT = ROOT / "opencli" / "clis" / "foundersc-quant"
COMMANDS = ("probe", "prepare", "reconcile", "recover")


def _source(name: str) -> str:
    return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")


def test_foundersc_template_registry_is_versioned_and_read_only_first_phase():
    assert _source("common.mjs").count("TEMPLATE_VERSION = 1") == 1
    for command in COMMANDS:
        source = _source(f"{command}.js")
        assert "site: SITE" in source
        assert f"name: '{command}'" in source
        assert "./common.mjs" in source
        assert "submitted: false" in _source("common.mjs")
    assert not (TEMPLATE_ROOT / "submit.js").exists()


def test_common_receipt_contains_optional_broker_neutral_fields():
    source = _source("common.mjs")
    required = (
        "order_id",
        "strategy_id",
        "task_id",
        "requested_shares",
        "filled_shares",
        "remaining_shares",
        "order_price",
        "fill_price",
        "latest_price",
        "active",
        "status_reason",
        "error_code",
        "observed_at",
        "submitted_at",
        "cancelled_at",
        "retry_allowed",
        "field_readback",
    )
    for field in required:
        assert f"{field}:" in source
    assert "account_binding: 'not_proven'" in source
    assert "reconcile_required: true" in source
    assert "reconcile_complete: null" in source
    assert "submit_capability: false" in source


def test_templates_bind_environment_before_form_work():
    for command in ("probe", "prepare", "reconcile", "recover"):
        source = _source(f"{command}.js")
        assert "readEnvironment(page)" in source
        assert "environmentGate(state, input.expectedEnvironment)" in source
        assert "environment_mismatch" in _source("common.mjs")
    common = _source("common.mjs")
    assert "div.switcher___KVAWw" in common
    assert "switcher_count !== 1" in common


def test_prepare_uses_exact_route_containers_and_safe_close_controls():
    source = _source("prepare.js")
    for marker in (
        "input[placeholder=\"请输入证券代码\"]",
        "input[placeholder=\"请输入委托价格\"]",
        "input[placeholder=\"请输入委托数量\"]",
        ".pdc-data-option",
        ".al-modal-container",
        "div.new-condition-strategy",
        ".new-condition-strategy-dropDown",
        "[role=\"dialog\"]",
        "exactLeaves(modal, '取消')",
        "exactLeaves(dialog, '取消')",
    ):
        assert marker in source
    assert "form_closed_after_readback" in source
    assert "ready_for_submit: false" in source


def test_no_template_clicks_a_broker_action_or_reads_credentials():
    source = "\n".join(
        _source(name)
        for name in ("common.mjs", "probe.js", "prepare.js", "reconcile.js", "recover.js")
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


def test_unknown_page_states_require_reconciliation_and_never_retry():
    common = _source("common.mjs")
    assert "status: 'unknown'" in common
    assert "reconcile_required: true" in common
    assert "status: 'auth_required'" in common
    assert "status: 'environment_mismatch'" in common
    recover = _source("recover.js")
    assert "page_shell_not_ready" in recover
    assert "route_not_reached" in recover
    assert "reconcile_required: !healthy" in recover


def test_reconcile_does_not_claim_complete_when_lists_are_not_fully_read():
    source = _source("reconcile.js")
    assert "pagination_present" in source
    assert "virtual_scroll" in source
    assert "reconciled_partial" in source
    assert "reconcile_complete: reconcileComplete" in source
    assert "reconcile_required: !reconcileComplete" in source


def test_readme_publishes_the_broker_neutral_contract_and_no_submit_gate():
    readme = _source("README.md")
    assert "probe" in readme
    assert "prepare" in readme
    assert "reconcile" in readme
    assert "recover" in readme
    assert "not expose a `submit` command" in readme
    assert "order_id" in readme
    assert "filled_shares` and" in readme
    assert "reconcile_complete=false" in readme
    assert "account_binding" in readme
    assert "NO_ROUTE_PROVEN" in readme
