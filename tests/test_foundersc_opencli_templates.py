from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEMPLATE_ROOT = ROOT / "opencli" / "clis" / "foundersc-quant"
COMMANDS = (
    "login",
    "probe",
    "prepare",
    "submit",
    "reconcile",
    "recover",
    "environment",
)


def _source(name: str) -> str:
    return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")


def test_package_limit_route_is_exposed_only_through_trusted_ui_commands():
    common = _source("common.mjs")
    prepare = _source("prepare.js")
    submit = _source("submit.js")

    assert "#/home/packageDeal/create?type=security" in common
    assert "#/home/packageDeal" in common
    assert "package-limit" in prepare
    assert "siteSession: 'persistent'" in prepare
    assert "name: 'submit'" in submit
    assert "route !== 'package-limit'" in submit
    assert "strategy: Strategy.UI" in submit
    assert "siteSession: 'persistent'" in submit
    assert "fetch(" not in submit


def test_package_limit_prepare_reads_back_then_cancels_an_empty_form():
    source = _source("prepare.js")

    for marker in (
        "function packageLimitScript(input)",
        'input[name="stockCode"]',
        'select#delegateDirection',
        'select#priceMode',
        'input#basicPrice[name="basicPrice"]',
        'input#quantity[name="quantity"]',
        "指定价格",
        "package_limit_field_readback_mismatch",
        "package_limit_form_not_closed",
        "page_cleared_after_readback",
        "openPackageLimitSecurityDialog(page)",
        "closePackageLimitSecurityDialog(page)",
        ".al-modal-positive-button",
        ".al-modal-cancel-button",
    ):
        assert marker in source
    assert "numericEqual" in source
    assert "package-limit-confirm" not in source


def test_package_limit_submit_is_single_shot_and_receipt_gated():
    source = _source("submit.js")

    for argument in (
        "route",
        "expected-environment",
        "logical-account-id",
        "expected-fund-account-fingerprint",
        "claim-id",
        "strategy-name",
        "code",
        "side",
        "price",
        "quantity",
    ):
        assert f"name: '{argument}'" in source
    for marker in (
        "environmentGate(state, input.expectedEnvironment)",
        "fund_account_fingerprint !== input.expectedFundAccountFingerprint",
        "strategyName.length > 8",
        "exact_strategy_name_match_count",
        "unique_dom_proven",
        "numeric_readback_proven",
        "readDraftWithWait",
        "strategyNameModalScript",
        "package-limit-name-confirm",
        "risk_checkbox_checked",
        '.risk-agreement-link input[type="checkbox"]',
        'input[type="checkbox"][id=',
        "installInterceptor('/qt/packageTask/')",
        "waitForCapture",
        "getInterceptedRequests",
        "确定提交委托？",
        "preEntrust",
        "strategy_id",
        "order_id",
        "orderIdFrom",
        "entrust",
        "non_trading_time",
        "submitted: null",
        "reconcile_required: true",
        "retry_allowed: false",
    ):
        assert marker in source
    assert source.count("package-limit-submit-order") == 2
    assert source.count("package-limit-server-confirm") == 2
    assert "task_id: input.claimId" in source
    assert "started: false" in source
    assert "Boolean(orderIdFrom(entrustReceipt))" in source
    assert "order_id: stableOrderId" in source
    assert "submitted: true" in source
    for forbidden in ("fetch(", "page.fetchJson", "XMLHttpRequest", "$http"):
        assert forbidden not in source


def test_probe_proves_package_surface_but_keeps_receipt_mapping_pending():
    source = _source("probe.js")

    assert "name: 'route'" in source
    assert "kwargs.route || 'package-limit'" in source
    assert "normalizeProbeRoute" in source
    assert "input.route === 'package-limit'" in source
    assert "PACKAGE_ROUTE_SCRIPT" in source
    assert "ROUTES.packageCreate" in source
    assert "carryEnvironmentProof" in source
    assert "submit: packageLimit && routeProven" in source
    assert "receipt_mapping: false" in source
    assert "submit_capability: packageLimit && routeProven" in source
    for route in ("manual-limit", "opening-auction", "timed-order"):
        assert route in source


def test_reconcile_requires_one_exact_account_query_order_mapping():
    source = _source("reconcile.js")

    for argument in ("code", "side", "quantity", "price", "date", "order-id"):
        assert f"name: '{argument}'" in source
    assert "function mapExactOrderReceipt" in source
    assert "carryEnvironmentProof" in source
    assert "exact_order_match_count" in source
    assert "exact_deal_match_count" in source
    assert "receipt_mapping: mapping.receiptMapping" in source
    assert "mapping.exactOrderMatchCount === 1" in source
    assert "ambiguous_or_missing_exact_order" in source


def test_foundersc_template_registry_is_versioned_with_one_scoped_write_command():
    assert _source("common.mjs").count("TEMPLATE_VERSION = 7") == 1
    for command in COMMANDS:
        source = _source(f"{command}.js")
        assert "site: SITE" in source
        assert f"name: '{command}'" in source
        assert "./common.mjs" in source
        assert "submitted: false" in _source("common.mjs")
    assert (TEMPLATE_ROOT / "submit.js").exists()
    assert "access: 'write'" in _source("submit.js")
    assert "route !== 'package-limit'" in _source("submit.js")


def test_shared_navigation_is_bounded_and_edge_compatible():
    common = _source("common.mjs")

    assert "waitUntil: 'domcontentloaded'" in common
    assert "timeout: 45000" in common
    assert "for (let attempt = 0; attempt < 30; attempt += 1)" in common
    assert "stableReadCount < 5" in common
    assert "JSON.stringify([" in common
    assert "state.auth_state !== 'unknown'" in common
    assert "await page.wait({time: 1})" in common
    assert "export async function navigateFresh" in common
    assert "opencli_fresh_body_present" in common
    assert "const exactUrl = routeUrl(route)" in common
    assert "opencli_env_probe=" in common


def test_account_binding_uses_same_origin_base_info_without_returning_raw_account():
    common = _source("common.mjs")

    assert "fetch('/qt/user/getBaseInfo'" in common
    assert "credentials: 'same-origin'" in common
    assert "new AbortController()" in common
    assert "clearTimeout(timeoutId)" in common
    assert "signal: controller.signal" in common
    assert "for (let accountAttempt = 0; accountAttempt < 3; accountAttempt += 1)" in common
    assert "fund_account_fingerprint" in common
    assert "fund_account_proof_source" in common
    assert "fund_account_value" not in common
    assert "raw_fund_account" not in common
    assert "sanitizeTableRow" in common
    assert "fundAccountColumnIndexes" in common
    assert "资金账号[^0-9]" not in common


def test_common_receipt_documentation_matches_template_version_six():
    readme = _source("README.md")
    assert '"template_version": 6' in readme
    assert '"template_version": 1' not in readme


def test_template_javascript_uses_repository_four_space_indentation():
    for name in (
        "common.mjs",
        "login.js",
        "environment.js",
        "probe.js",
        "prepare.js",
        "submit.js",
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
    for command in ("probe", "prepare", "submit", "reconcile", "recover"):
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


def test_login_uses_exact_login_controls_and_requires_authenticated_readback():
    source = _source("login.js")

    for marker in (
        'input[placeholder="请输入手机号码"]',
        'input[placeholder="请输入量化平台密码"]',
        "登录模拟盘",
        "data-opencli-foundersc-login-target",
        "page.evaluate(loginFillScript(account, secret))",
        "await page.click",
        "for (let attempt = 0; attempt < 10; attempt += 1)",
        "readEnvironment(page)",
        "login_authenticated",
        "login_readback_not_authenticated",
        "login_button_disabled",
        "password_error",
        "captcha_required",
        "sms_required",
        "account_locked",
        "observed_route",
        "authentication_path",
        "initial_auth_state",
        "keychain_login_read",
        "login_form_binding_proven",
        "login_submit_click_count",
        "post_auth_readback_proven",
        "session_reuse_proven",
        "fresh_login_proven",
    ):
        assert marker in source
    assert "submitted: false" in source
    assert "saved: false" in source
    assert "started: false" in source
    assert "submit_capability: false" in source


def test_environment_command_only_switches_the_unique_environment_control():
    source = _source("environment.js")
    assert "data-opencli-foundersc-environment-target" in source
    assert "点击切换至实盘" in source
    assert "点击切换至模拟盘" in source
    assert "await page.click" in source
    assert "environment_switch_readback_mismatch" in source
    assert "environment_data_namespace" in source
    assert "environment_proof_complete" in source
    assert "environment_ui_data_namespace_mismatch" in source
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


def test_readme_publishes_the_package_limit_submit_and_fail_closed_contract():
    readme = _source("README.md")
    assert "probe" in readme
    assert "prepare" in readme
    assert "reconcile" in readme
    assert "recover" in readme
    assert "submit --route package-limit" in readme
    assert "preEntrust" in readme
    assert "save" in readme
    assert "entrust" in readme
    assert "never retries" in readme
    assert "order_id" in readme
    assert "filled_shares` and" in readme
    assert "reconcile_complete=false" in readme
    assert "account_binding" in readme
    assert "manual-limit`, `opening-auction`, and `timed-order`" in readme
    assert "Strategy-surface decision" in readme
    assert "按证券组合" in readme
    assert "TWAP_PRO" in readme


def test_skill_routes_foundersc_package_limit_work_to_its_reference():
    skill = (ROOT / ".codex" / "skills" / "xiaocao-trading" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    reference = (ROOT / ".codex" / "skills" / "xiaocao-trading" / "references"
                 / "foundersc-opencli.md").read_text(encoding="utf-8")
    assert "references/foundersc-opencli.md" in skill
    assert "UI-only `package-limit` submit route" in reference
    assert "at-most-one controlled retry" in reference
    assert "separate 09:20 Book-B live-morning" in reference
    assert "never calls or waits for the 09:25" in reference
