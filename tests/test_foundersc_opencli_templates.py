from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEMPLATE_ROOT = ROOT / "opencli" / "clis" / "foundersc-quant"
COMMANDS = ("probe", "prepare", "reconcile", "recover", "environment")


def _source(name: str) -> str:
    return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")


def test_foundersc_template_registry_is_versioned_and_read_only_first_phase():
    assert _source("common.mjs").count("TEMPLATE_VERSION = 2") == 1
    for command in COMMANDS:
        source = _source(f"{command}.js")
        assert "site: SITE" in source
        assert f"name: '{command}'" in source
        assert "./common.mjs" in source
        assert "submitted: false" in _source("common.mjs")
    assert not (TEMPLATE_ROOT / "submit.js").exists()


def test_template_javascript_uses_repository_four_space_indentation():
    for name in (
        "common.mjs",
        "environment.js",
        "probe.js",
        "prepare.js",
        "reconcile.js",
        "recover.js",
    ):
        for line_number, line in enumerate(_source(name).splitlines(), start=1):
            leading = len(line) - len(line.lstrip(" "))
            assert leading % 4 == 0, f"{name}:{line_number} uses {leading} spaces"


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
        ".new-condition-strategy-title",
        ".new-condition-strategy-dropDown",
        "data-opencli-foundersc-prepare-target",
        "timed-date-open",
        "timed-date-day",
        "[role=\"dialog\"]",
        "exactLeaves(modal, '取消')",
        "exactLeaves(dialog, '取消')",
    ):
        assert marker in source
    assert "form_closed_after_readback" in source
    assert "opening_auction_field_readback_mismatch" in source
    assert "timed_order_field_readback_mismatch" in source
    assert "ready_for_submit: false" in source
    assert "await page.click" in source
    assert "PREPARE_WAIT_SCRIPT" in source
    assert "page.evaluate(PREPARE_WAIT_SCRIPT)" in source


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


def test_environment_command_only_switches_the_unique_environment_control():
    source = _source("environment.js")
    assert "data-opencli-foundersc-environment-target" in source
    assert "点击切换至实盘" in source
    assert "点击切换至模拟盘" in source
    assert "await page.click" in source
    assert "environment_switch_readback_mismatch" in source
    assert "submit_capability: false" in source
    for forbidden in ("保存", "启动", "买入", "卖出", "撤单"):
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
    assert "MANUAL_ROUTE_DISCOVERY_SCRIPT" in recover
    assert "routeMatches(" in recover
    assert "startsWith(ROUTES.manual)" not in recover


def test_reconcile_does_not_claim_complete_when_lists_are_not_fully_read():
    source = _source("reconcile.js")
    assert "pagination_present" in source
    assert "virtual_scroll" in source
    assert "reconciled_partial" in source
    assert "reconcile_complete: reconcileComplete" in source
    assert "reconcile_required: !reconcileComplete" in source
    assert "pagination_complete" in source
    assert "virtual_complete" in source
    assert "account_fingerprint_not_proven" in source


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


def test_skill_routes_foundersc_read_only_work_to_its_reference():
    skill = (ROOT / ".codex" / "skills" / "xiaocao-trading" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    reference = (ROOT / ".codex" / "skills" / "xiaocao-trading" / "references"
                 / "foundersc-opencli.md").read_text(encoding="utf-8")
    assert "references/foundersc-opencli.md" in skill
    assert "submit_capability=false" in reference
    assert "no Codex Automation" in reference
