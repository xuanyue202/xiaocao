import {spawnSync} from 'node:child_process';

import {cli, Strategy} from '@jackwener/opencli/registry';
import {
    RECEIPT_COLUMNS,
    ROUTES,
    SITE,
    asSingleReceipt,
    baseReceipt,
    navigateFresh,
    pageScript,
    readEnvironment,
    unknownReceipt,
} from './common.mjs';

const TEMPLATE_NAME = `${SITE}/login`;
const LOGIN_SERVICE = 'xiaocao.foundersc.quant.login';
const SECURITY_COMMAND = '/usr/bin/security';
const TARGET_ATTRIBUTE = 'data-opencli-foundersc-login-target';

const LOGIN_DISCOVERY_SCRIPT = pageScript(String.raw`
    const phoneInputs = [...document.querySelectorAll(
        'input[placeholder="请输入手机号码"]'
    )].filter(visible);
    const passwordInputs = [...document.querySelectorAll(
        'input[placeholder="请输入量化平台密码"]'
    )].filter(visible);
    const loginButtons = [...document.querySelectorAll('button')]
        .filter(visible)
        .filter((node) => (node.innerText || node.textContent || '').trim()
            === '登录模拟盘');
    document.querySelectorAll('[${TARGET_ATTRIBUTE}]').forEach((node) => (
        node.removeAttribute('${TARGET_ATTRIBUTE}')
    ));
    const button = loginButtons.length === 1 ? loginButtons[0] : null;
    if (button) {
        button.setAttribute(
            '${TARGET_ATTRIBUTE}',
            passwordInputs.length === 0 ? 'reveal-password' : 'submit-login'
        );
    }
    return {
        phone_input_count: phoneInputs.length,
        password_input_count: passwordInputs.length,
        login_button_count: loginButtons.length,
        password_reveal_required: passwordInputs.length === 0,
    };
`);

const LOGIN_STATUS_SCRIPT = pageScript(String.raw`
    const body = sanitize(document.body?.innerText || '');
    return {
        observed_route: location.hash || '',
        password_error: /密码.{0,12}(错误|不正确|有误)/.test(body),
        captcha_required: /验证码|滑块|人机验证/.test(body),
        sms_required: /短信.{0,8}(验证|验证码)|手机验证码/.test(body),
        account_locked: /账号.{0,12}(锁定|冻结)|尝试次数/.test(body),
        network_error: /网络.{0,12}(错误|异常|失败)|请求失败/.test(body),
    };
`);

function loginFillScript(account, secret) {
    const loginAccount = JSON.stringify(account);
    const loginSecret = JSON.stringify(secret);
    return pageScript(String.raw`
        const phoneInputs = [...document.querySelectorAll(
            'input[placeholder="请输入手机号码"]'
        )].filter(visible);
        const passwordInputs = [...document.querySelectorAll(
            'input[placeholder="请输入量化平台密码"]'
        )].filter(visible);
        const loginButtons = [...document.querySelectorAll('button')]
            .filter(visible)
            .filter((node) => (node.innerText || node.textContent || '').trim()
                === '登录模拟盘');
        document.querySelectorAll('[${TARGET_ATTRIBUTE}]').forEach((node) => (
            node.removeAttribute('${TARGET_ATTRIBUTE}')
        ));
        if (phoneInputs.length !== 1
                || passwordInputs.length !== 1
                || loginButtons.length !== 1) {
            return {
                ready: false,
                phone_input_count: phoneInputs.length,
                password_input_count: passwordInputs.length,
                login_button_count: loginButtons.length,
            };
        }
        setValue(phoneInputs[0], ${loginAccount});
        setValue(passwordInputs[0], ${loginSecret});
        const phoneMatch = phoneInputs[0].value === ${loginAccount};
        const passwordMatch = passwordInputs[0].value === ${loginSecret};
        const loginButtonDisabled = disabled(loginButtons[0]);
        if (phoneMatch && passwordMatch && !loginButtonDisabled) {
            loginButtons[0].setAttribute(
                '${TARGET_ATTRIBUTE}',
                'submit-login'
            );
        }
        return {
            ready: phoneMatch && passwordMatch && !loginButtonDisabled,
            phone_input_count: 1,
            password_input_count: 1,
            login_button_count: 1,
            phone_binding_match: phoneMatch,
            password_secret_present: passwordMatch,
            login_button_disabled: loginButtonDisabled,
        };
    `);
}

function maskedFingerprint(account) {
    return account.length >= 8
        ? `${account.slice(0, 3)}******${account.slice(-3)}`
        : '';
}

function runSecurity(args) {
    return spawnSync(SECURITY_COMMAND, args, {
        encoding: 'utf8',
        timeout: 8000,
        maxBuffer: 16384,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
    });
}

function readLoginKeychainItem() {
    const metadata = runSecurity([
        'find-generic-password',
        '-s',
        LOGIN_SERVICE,
    ]);
    if (metadata.status !== 0 || metadata.error) {
        throw new Error('keychain_login_metadata_unavailable');
    }
    const rendered = `${metadata.stdout || ''}\n${metadata.stderr || ''}`;
    const accountMatch = /^\s*"acct"<blob>="([^"]+)"$/m.exec(rendered);
    const account = String(accountMatch?.[1] || '').trim();
    if (!/^1\d{10}$/.test(account)) {
        throw new Error('keychain_login_account_invalid');
    }
    const secretResult = runSecurity([
        'find-generic-password',
        '-w',
        '-s',
        LOGIN_SERVICE,
    ]);
    if (secretResult.status !== 0 || secretResult.error) {
        throw new Error('keychain_login_secret_unavailable');
    }
    const secret = String(secretResult.stdout || '').replace(/\r?\n$/, '');
    if (!secret || secret.length > 256) {
        throw new Error('keychain_login_secret_invalid');
    }
    return {account, secret};
}

function loginReceipt(state, fields = {}) {
    return asSingleReceipt(baseReceipt(
        TEMPLATE_NAME,
        ROUTES.assets,
        'mock',
        state,
        {
            logical_account_id: 'primary',
            submitted: false,
            saved: false,
            started: false,
            submit_capability: false,
            capabilities: {
                submit: false,
                login: false,
                account_binding: false,
                receipt_mapping: false,
                cancellation: false,
            },
            ...fields,
        }
    ));
}

cli({
    site: SITE,
    name: 'login',
    description: 'Authenticate the persistent Founder session using the fixed macOS Keychain item',
    access: 'write',
    domain: 'quant.foundersc.com',
    strategy: Strategy.UI,
    browser: true,
    siteSession: 'persistent',
    defaultWindowMode: 'foreground',
    navigateBefore: false,
    args: [],
    columns: RECEIPT_COLUMNS,
    func: async (page) => {
        let state;
        let fingerprint = '';
        try {
            await navigateFresh(page, ROUTES.assets);
            state = await readEnvironment(page);
            const safeMockSession = state?.auth_state === 'authenticated'
                && state?.environment === 'mock'
                && state?.environment_data_namespace === 'mock'
                && state?.environment_proof_complete === true
                && state?.fund_account_match_count === 1;
            if (safeMockSession) {
                return loginReceipt(state, {
                    status: 'login_authenticated',
                    status_reason: 'persistent_session_already_authenticated',
                    reconcile_required: true,
                    field_readback: {
                        authenticated: true,
                        password_secret_present: false,
                    },
                    capabilities: {
                        submit: false,
                        login: true,
                        account_binding: false,
                        receipt_mapping: false,
                        cancellation: false,
                    },
                });
            }
            if (state?.auth_state === 'authenticated') {
                return loginReceipt(state, {
                    status: 'unknown',
                    status_reason: 'login_authenticated_safe_mock_unproven',
                    reconcile_required: true,
                    field_readback: {
                        authenticated: true,
                        environment: state?.environment || 'unknown',
                    },
                });
            }
            if (state?.auth_state !== 'login_required') {
                return loginReceipt(state, {
                    status: 'unknown',
                    status_reason: 'login_page_not_proven',
                    reconcile_required: true,
                });
            }

            let keychain;
            try {
                keychain = readLoginKeychainItem();
            } catch (_error) {
                return loginReceipt(state, {
                    status: 'auth_required',
                    status_reason: 'keychain_login_unavailable',
                    reconcile_required: false,
                });
            }
            fingerprint = maskedFingerprint(keychain.account);
            let discovery = await page.evaluate(LOGIN_DISCOVERY_SCRIPT);
            if (discovery?.password_reveal_required === true
                    && discovery?.login_button_count === 1) {
                await page.click(
                    `[${TARGET_ATTRIBUTE}="reveal-password"]`
                );
                for (let attempt = 0; attempt < 10; attempt += 1) {
                    await page.wait({time: 0.5});
                    discovery = await page.evaluate(LOGIN_DISCOVERY_SCRIPT);
                    if (discovery?.password_input_count === 1) break;
                }
            }
            if (discovery?.phone_input_count !== 1
                    || discovery?.password_input_count !== 1
                    || discovery?.login_button_count !== 1) {
                keychain.secret = '';
                return loginReceipt(state, {
                    status: 'auth_required',
                    status_reason: 'login_controls_not_unique',
                    login_account_fingerprint: fingerprint,
                    reconcile_required: false,
                    locator_proof: discovery || {},
                });
            }
            const account = keychain.account;
            let secret = keychain.secret;
            const filled = await page.evaluate(loginFillScript(account, secret));
            secret = '';
            keychain.secret = '';
            if (filled?.ready !== true) {
                return loginReceipt(state, {
                    status: 'auth_required',
                    status_reason: 'login_field_readback_mismatch',
                    login_account_fingerprint: fingerprint,
                    reconcile_required: false,
                    locator_proof: filled || {},
                });
            }
            await page.click(`[${TARGET_ATTRIBUTE}="submit-login"]`);
            await page.wait({time: 1});
            const finalState = await readEnvironment(page);
            const authenticated = finalState?.auth_state === 'authenticated'
                && finalState?.environment === 'mock'
                && finalState?.environment_data_namespace === 'mock'
                && finalState?.environment_proof_complete === true
                && finalState?.fund_account_match_count === 1;
            const loginStatus = await page.evaluate(LOGIN_STATUS_SCRIPT);
            return loginReceipt(finalState, {
                status: authenticated ? 'login_authenticated' : 'auth_required',
                status_reason: authenticated
                    ? 'login_authenticated_readback_completed'
                    : 'login_readback_not_authenticated',
                login_account_fingerprint: fingerprint,
                reconcile_required: authenticated,
                field_readback: {
                    authenticated,
                    phone_binding_match: filled.phone_binding_match === true,
                    password_secret_present: filled.password_secret_present === true,
                    login_button_disabled: filled.login_button_disabled === true,
                    environment: finalState?.environment || 'unknown',
                    observed_route: loginStatus?.observed_route || '',
                    password_error: loginStatus?.password_error === true,
                    captcha_required: loginStatus?.captcha_required === true,
                    sms_required: loginStatus?.sms_required === true,
                    account_locked: loginStatus?.account_locked === true,
                    network_error: loginStatus?.network_error === true,
                },
                locator_proof: {
                    phone_input_count: filled.phone_input_count,
                    password_input_count: filled.password_input_count,
                    login_button_count: filled.login_button_count,
                    authenticated_readback: authenticated,
                },
                capabilities: {
                    submit: false,
                    login: authenticated,
                    account_binding: false,
                    receipt_mapping: false,
                    cancellation: false,
                },
            });
        } catch (error) {
            return asSingleReceipt(unknownReceipt(
                TEMPLATE_NAME,
                ROUTES.assets,
                'mock',
                state,
                'login',
                error,
                {
                    logical_account_id: 'primary',
                    login_account_fingerprint: fingerprint,
                    field_readback: {},
                    submitted: false,
                    saved: false,
                    started: false,
                    submit_capability: false,
                }
            ));
        }
    },
});
