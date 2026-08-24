import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError } from '@jackwener/opencli/errors';
import {
    RECEIPT_COLUMNS,
    ROUTES,
    SITE,
    asSingleReceipt,
    baseReceipt,
    carryEnvironmentProof,
    environmentGate,
    navigate,
    navigateFresh,
    normalizeCode,
    normalizeEnvironment,
    normalizeLogicalAccountId,
    normalizeNonNegativeNumber,
    normalizePositiveInteger,
    normalizeSide,
    pageScript,
    readEnvironment,
} from './common.mjs';

const TEMPLATE_NAME = `${SITE}/submit`;
const SUBMIT_TARGET_ATTRIBUTE = 'data-opencli-foundersc-submit-target';

function parseInput(kwargs) {
    try {
        const route = String(kwargs.route || '').trim();
        if (route !== 'package-limit') {
            throw new Error('--route must be package-limit');
        }
        const strategyName = String(kwargs['strategy-name'] || '').trim();
        if (!strategyName || strategyName.length > 8
                || !/^[\p{L}\p{N}_-]+$/u.test(strategyName)) {
            throw new Error('--strategy-name must be an exact 1-8 character name');
        }
        const expectedFundAccountFingerprint = String(
            kwargs['expected-fund-account-fingerprint'] || ''
        ).trim();
        if (!/^\d{3}\*{6}\d{3}$/.test(expectedFundAccountFingerprint)) {
            throw new Error('--expected-fund-account-fingerprint must be masked');
        }
        const claimId = String(kwargs['claim-id'] || '').trim();
        if (!/^[A-Za-z0-9_.:-]{1,128}$/.test(claimId)) {
            throw new Error('--claim-id must be a bounded identifier');
        }
        const price = normalizeNonNegativeNumber(kwargs.price, '--price');
        if (price <= 0) throw new Error('--price must be greater than zero');
        const preflightOnlyRaw = String(
            kwargs['preflight-only'] ?? 'false'
        ).trim().toLowerCase();
        if (!['true', 'false'].includes(preflightOnlyRaw)) {
            throw new Error('--preflight-only must be true or false');
        }
        return {
            route,
            expectedEnvironment: normalizeEnvironment(
                kwargs['expected-environment'] || 'mock'
            ),
            logicalAccountId: normalizeLogicalAccountId(
                kwargs['logical-account-id'] || 'primary'
            ),
            expectedFundAccountFingerprint,
            claimId,
            strategyName,
            code: normalizeCode(kwargs.code),
            side: normalizeSide(kwargs.side),
            price,
            quantity: normalizePositiveInteger(kwargs.quantity, '--quantity'),
            preflightOnly: preflightOnlyRaw === 'true',
        };
    } catch (error) {
        throw new ArgumentError(error.message);
    }
}

function packageReceipt(input, state, fields = {}) {
    return baseReceipt(
        TEMPLATE_NAME,
        ROUTES.packageCreate,
        input.expectedEnvironment,
        state,
        {
            logical_account_id: input.logicalAccountId,
            task_id: input.claimId,
            retry_allowed: false,
            submit_capability: true,
            capabilities: {
                submit: true,
                submit_route: 'package-limit',
                receipt_mapping: true,
                cancellation: false,
            },
            ...fields,
        }
    );
}

function strategyListScript(strategyName) {
    return pageScript(String.raw`
        const containers = [...document.querySelectorAll('.pd-left')]
            .filter(visible);
        const scrollRoots = containers.length === 1
            ? [...containers[0].querySelectorAll('.scrollBar')].filter(visible)
            : [];
        const exactMatches = containers.length === 1
            ? exactLeaves(containers[0], ${JSON.stringify(strategyName)})
            : [];
        return {
            unique_dom_proven: containers.length === 1
                && scrollRoots.length === 1,
            exact_strategy_name_match_count: exactMatches.length,
            strategy_container_count: containers.length,
            strategy_scroll_root_count: scrollRoots.length,
        };
    `, {async: true});
}

function addSecurityTargetScript() {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(SUBMIT_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const options = [...document.querySelectorAll('.pdc-data-option')]
            .filter(visible);
        const add = options.length === 1
            ? exactLeaves(options[0], '添加证券')
            : [];
        const data = [...document.querySelectorAll('.pdc-data')].filter(visible);
        const empty = data.length === 1
            && /暂无数据/.test(data[0].innerText || '');
        if (options.length === 1 && add.length === 1 && empty) {
            add[0].setAttribute(attribute, 'package-limit-add-security');
        }
        return {
            unique_dom_proven: options.length === 1
                && add.length === 1 && data.length === 1,
            page_empty: empty,
            add_match_count: add.length,
        };
    `, {async: true});
}

function addSecurityModalScript(input) {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(SUBMIT_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const modals = [...document.querySelectorAll('.al-modal-container')]
            .filter(visible);
        const modal = modals.length === 1 ? modals[0] : null;
        const result = {
            unique_dom_proven: false,
            numeric_readback_proven: false,
            modal_count: modals.length,
            field_readback: {},
        };
        if (!modal) return result;
        const fields = {
            code: [...modal.querySelectorAll('input[name="stockCode"]')]
                .filter(visible),
            side: [...modal.querySelectorAll('select#delegateDirection')]
                .filter(visible),
            priceMode: [...modal.querySelectorAll('select#priceMode')]
                .filter(visible),
            price: [...modal.querySelectorAll(
                'input#basicPrice[name="basicPrice"]'
            )].filter(visible),
            quantity: [...modal.querySelectorAll(
                'input#quantity[name="quantity"]'
            )].filter(visible),
            confirm: [...modal.querySelectorAll('.al-modal-positive-button')]
                .filter(visible).filter((node) => (
                    (node.textContent || '').trim() === '确定'
                )),
            cancel: [...modal.querySelectorAll('.al-modal-cancel-button')]
                .filter(visible).filter((node) => (
                    (node.textContent || '').trim() === '取消'
                )),
        };
        if (!Object.values(fields).every((nodes) => nodes.length === 1)) {
            return result;
        }
        const selectExactText = (select, wanted) => {
            const matches = [...select.options].filter((option) => (
                (option.textContent || '').trim() === wanted
            ));
            if (matches.length !== 1) return false;
            setSelect(select, matches[0].value);
            return true;
        };
        setValue(fields.code[0], ${JSON.stringify(input.code)});
        await waitForPage(1000);
        const stableSide = [...modal.querySelectorAll('select#delegateDirection')]
            .filter(visible);
        const stableMode = [...modal.querySelectorAll('select#priceMode')]
            .filter(visible);
        if (stableSide.length !== 1 || stableMode.length !== 1) return result;
        const sideSet = selectExactText(
            stableSide[0],
            ${JSON.stringify(input.side)}
        );
        const modeSet = selectExactText(stableMode[0], '指定价格');
        await waitForPage(200);
        const stablePrice = [...modal.querySelectorAll(
            'input#basicPrice[name="basicPrice"]'
        )].filter(visible);
        const stableQuantity = [...modal.querySelectorAll(
            'input#quantity[name="quantity"]'
        )].filter(visible);
        if (stablePrice.length !== 1 || stableQuantity.length !== 1) return result;
        setValue(stablePrice[0], ${JSON.stringify(String(input.price))});
        setValue(stableQuantity[0], ${JSON.stringify(String(input.quantity))});
        await waitForPage(200);
        const readFields = {
            code: [...modal.querySelectorAll('input[name="stockCode"]')]
                .filter(visible),
            side: [...modal.querySelectorAll('select#delegateDirection')]
                .filter(visible),
            priceMode: [...modal.querySelectorAll('select#priceMode')]
                .filter(visible),
            price: [...modal.querySelectorAll(
                'input#basicPrice[name="basicPrice"]'
            )].filter(visible),
            quantity: [...modal.querySelectorAll(
                'input#quantity[name="quantity"]'
            )].filter(visible),
            confirm: [...modal.querySelectorAll('.al-modal-positive-button')]
                .filter(visible).filter((node) => (
                    (node.textContent || '').trim() === '确定'
                )),
        };
        if (!Object.values(readFields).every((nodes) => nodes.length === 1)) {
            return result;
        }
        const readback = {
            code: readFields.code[0].value,
            side: readFields.side[0].selectedOptions[0]?.textContent?.trim() || '',
            price_mode:
                readFields.priceMode[0].selectedOptions[0]?.textContent?.trim() || '',
            price: readFields.price[0].value,
            quantity: readFields.quantity[0].value,
        };
        const numericEqual = (actual, expected) => Number.isFinite(Number(actual))
            && Number(actual) === Number(expected);
        const numericReadback = numericEqual(
            readback.price,
            ${JSON.stringify(input.price)}
        ) && numericEqual(
            readback.quantity,
            ${JSON.stringify(input.quantity)}
        );
        const exactReadback = readback.code === ${JSON.stringify(input.code)}
            && readback.side === ${JSON.stringify(input.side)}
            && readback.price_mode === '指定价格';
        const ready = sideSet && modeSet && numericReadback && exactReadback
            && !disabled(readFields.confirm[0]);
        if (ready) {
            readFields.confirm[0].setAttribute(
                attribute,
                'package-limit-add-confirm'
            );
        }
        result.unique_dom_proven = true;
        result.numeric_readback_proven = numericReadback;
        result.exact_readback_proven = exactReadback;
        result.confirm_enabled = !disabled(readFields.confirm[0]);
        result.field_readback = readback;
        return result;
    `, {async: true});
}

function draftReadbackScript(input) {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(SUBMIT_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const prices = [...document.querySelectorAll('input#input-inline-0')]
            .filter(visible);
        const quantities = [...document.querySelectorAll('input#quantity-0')]
            .filter(visible);
        const securityCheckboxes = [...document.querySelectorAll(
            ${JSON.stringify(`input[type="checkbox"][id="${input.code}"]`)}
        )];
        const security = securityCheckboxes.length === 1
            ? securityCheckboxes[0] : null;
        const codeNameLeaves = [...document.querySelectorAll('*')]
            .filter((node) => node.children.length === 0 && visible(node))
            .filter((node) => (
                (node.textContent || '').trim().startsWith(
                    ${JSON.stringify(`${input.code} `)}
                )
            ));
        const risk = [...document.querySelectorAll(
            '.risk-agreement-link input[type="checkbox"]'
        )].filter((node) => !disabled(node));
        const orderButtons = [...document.querySelectorAll('button')]
            .filter(visible).filter((node) => (
                (node.textContent || '').trim() === '下单'
            ));
        const numericEqual = (actual, expected) => Number.isFinite(Number(actual))
            && Number(actual) === Number(expected);
        const numericReadback = prices.length === 1 && quantities.length === 1
            && numericEqual(prices[0].value, ${JSON.stringify(input.price)})
            && numericEqual(quantities[0].value, ${JSON.stringify(input.quantity)});
        const uniqueDom = prices.length === 1
            && quantities.length === 1 && securityCheckboxes.length === 1
            && codeNameLeaves.length === 1 && risk.length === 1
            && orderButtons.length === 1;
        if (securityCheckboxes.length === 1 && !security.checked) {
            security.setAttribute(attribute, 'package-limit-security-checkbox');
        }
        if (risk.length === 1 && !risk[0].checked) {
            risk[0].setAttribute(attribute, 'package-limit-risk-checkbox');
        }
        const riskChecked = risk.length === 1 && risk[0].checked;
        const securityChecked = securityCheckboxes.length === 1
            && security.checked;
        if (uniqueDom && numericReadback
                && riskChecked && securityChecked) {
            orderButtons[0].setAttribute(
                attribute,
                'package-limit-submit-order'
            );
        }
        return {
            unique_dom_proven: uniqueDom,
            exact_strategy_name_match_count: null,
            numeric_readback_proven: numericReadback,
            risk_checkbox_checked: riskChecked,
            security_checkbox_checked: securityChecked,
            risk_checkbox_count: risk.length,
            order_button_count: orderButtons.length,
            field_readback: {
                strategy_name: null,
                code: codeNameLeaves.length === 1
                    ? ${JSON.stringify(input.code)} : null,
                side: ${JSON.stringify(input.side)},
                price: prices.length === 1 ? prices[0].value : null,
                quantity: quantities.length === 1 ? quantities[0].value : null,
            },
        };
    `, {async: true});
}

function serverConfirmationScript(input) {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(SUBMIT_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const models = [...document.querySelectorAll('.order-model')]
            .filter(visible);
        const model = models.length === 1 ? models[0] : null;
        const titleMatches = model ? exactLeaves(model, '确定提交委托？') : [];
        const tableRows = model
            ? [...model.querySelectorAll('tbody tr')].filter(visible)
            : [];
        // The current official PackageDealCreateOrderModel template renders
        // entrust rows as ul.scroll > li rather than a table. Accept only
        // that exact account-bound model shape or the legacy table shape, and
        // still require one combined row so an unrelated list can never satisfy
        // the confirmation proof.
        const listRows = model
            ? [...model.querySelectorAll(
                '.pdc-data-model-body .pd-data-title ul.scroll > li'
            )].filter(visible)
            : [];
        const rows = [...tableRows, ...listRows];
        const submits = model
            ? [...model.querySelectorAll(
                'button.al-modal-positive-button[type="submit"]'
            )].filter(visible)
                .filter((node) => (node.textContent || '').trim() === '提交')
            : [];
        const cells = rows.length === 1
            ? [...rows[0].querySelectorAll('td, span')].filter(visible)
                .map((node) => (node.textContent || '').trim())
            : [];
        const numericEqual = (actual, expected) => Number.isFinite(Number(actual))
            && Number(actual) === Number(expected);
        const codeReadback = cells.some((value) => (
            value === ${JSON.stringify(input.code)}
            || value.startsWith(${JSON.stringify(`${input.code} `)})
        ));
        const sideReadback = cells.includes(${JSON.stringify(input.side)});
        const priceReadback = cells.some((value) => numericEqual(
            value,
            ${JSON.stringify(input.price)}
        ));
        const quantityReadback = cells.some((value) => numericEqual(
            value,
            ${JSON.stringify(input.quantity)}
        ));
        const uniqueDom = models.length === 1 && titleMatches.length === 1
            && rows.length === 1 && submits.length === 1;
        const numericReadback = priceReadback && quantityReadback;
        const ready = uniqueDom && codeReadback && sideReadback
            && numericReadback && !disabled(submits[0]);
        if (ready) {
            submits[0].setAttribute(
                attribute,
                'package-limit-server-confirm'
            );
        }
        return {
            server_confirmation_proven: ready,
            unique_dom_proven: uniqueDom,
            numeric_readback_proven: numericReadback,
            code_readback_proven: codeReadback,
            side_readback_proven: sideReadback,
            confirmation_row_count: rows.length,
            confirmation_table_row_count: tableRows.length,
            confirmation_list_row_count: listRows.length,
            confirmation_submit_count: submits.length,
        };
    `, {async: true});
}

async function readDraftWithWait(page, input) {
    let draft = null;
    for (let attempt = 0; attempt < 20; attempt += 1) {
        draft = await page.evaluate(draftReadbackScript(input));
        if (draft?.unique_dom_proven === true
                && draft.numeric_readback_proven === true) {
            break;
        }
        await page.wait({time: 0.1});
    }
    return draft;
}

function strategyNameModalScript(input) {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(SUBMIT_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        let names = [];
        for (let attempt = 0; attempt < 20; attempt += 1) {
            names = [...document.querySelectorAll(
                'input#name[name="newName"][placeholder="请输入新名称"]'
            )].filter(visible);
            if (names.length > 0) break;
            await waitForPage(100);
        }
        if (names.length === 0) {
            return {present: false, unique_dom_proven: true};
        }
        const inputNode = names.length === 1 ? names[0] : null;
        const form = inputNode?.closest('form') || null;
        const headers = form
            ? [...form.parentElement?.querySelectorAll('.al-modal-header') || []]
                .filter(visible).filter((node) => (
                    (node.textContent || '').trim() === '名称设置'
                ))
            : [];
        const confirms = form
            ? [...form.querySelectorAll('button.al-modal-positive-button')]
                .filter(visible).filter((node) => (
                    (node.textContent || '').trim() === '确定'
                ))
            : [];
        if (!inputNode || !form || headers.length !== 1 || confirms.length !== 1) {
            return {
                present: true,
                unique_dom_proven: false,
                name_input_count: names.length,
                header_count: headers.length,
                confirm_count: confirms.length,
            };
        }
        setValue(inputNode, ${JSON.stringify(input.strategyName)});
        const exactReadback = inputNode.value === ${JSON.stringify(input.strategyName)};
        const ready = exactReadback && !disabled(confirms[0]);
        if (ready) {
            confirms[0].setAttribute(attribute, 'package-limit-name-confirm');
        }
        return {
            present: true,
            unique_dom_proven: ready,
            exact_strategy_name_match_count: exactReadback ? 1 : 0,
            confirm_enabled: !disabled(confirms[0]),
        };
    `, {async: true});
}

const TERMINAL_STATUS_SCRIPT = pageScript(String.raw`
    const body = document.body?.innerText || '';
    return {
        success: exactLeaves(document.body, '下单成功').length === 1,
        failure: exactLeaves(document.body, '下单失败').length === 1,
        non_trading_time:
            /非交易时间|休市|闭市|未开市|不在交易时间/.test(body),
    };
`, {async: true});

function responseCode(payload) {
    const code = Number(payload?.code);
    return Number.isFinite(code) ? code : null;
}

function responseText(payload) {
    try {
        return JSON.stringify(payload || {});
    } catch (_error) {
        return '';
    }
}

function classifyPreEntrustFailure(payload, requestedCode) {
    const message = String(payload?.message ?? '').trim();
    const known = {
        '无创业版权限': 'gem_permission_missing',
        '无沪市股东账号': 'shanghai_account_missing',
        '无深市股东账号': 'shenzhen_account_missing',
        '超出标的范围': 'security_scope_rejected',
    };
    let category = known[message] || 'broker_pre_entrust_rejected';
    if (/创业板/.test(message)) category = 'gem_permission_missing';
    else if (/沪市.*(账号|股东)|上海.*(账号|股东)/.test(message)) {
        category = 'shanghai_account_missing';
    } else if (/深市.*(账号|股东)|深圳.*(账号|股东)/.test(message)) {
        category = 'shenzhen_account_missing';
    } else if (/(程序化|量化|极速).*(权限|开通|报备|报告)|未开通.*(程序化|量化|极速)/
            .test(message)) {
        category = 'program_trading_permission_missing';
    } else if (/(协议|风险测评|适当性).*(未|需|请)|未.*(协议|风险测评|适当性)/
            .test(message)) {
        category = 'agreement_required';
    } else if (/(交易密码|密码控件|密码)/.test(message)) {
        category = 'trade_password_required';
    } else if (/(资金不足|余额不足|可用资金)/.test(message)) {
        category = 'insufficient_cash';
    } else if (/(标的范围|不支持交易|不可交易|证券范围)/.test(message)) {
        category = 'security_scope_rejected';
    }
    const code = String(requestedCode || '').trim();
    if (category === 'broker_pre_entrust_rejected'
            && /^\d{6}/.test(message)
            && message.slice(0, 6) === code) {
        category = 'security_validation_rejected';
    }
    return {
        category,
        response_code: responseCode(payload),
    };
}

function isNonTradingResponse(payload) {
    return /非交易时间|休市|闭市|未开市|不在交易时间/
        .test(responseText(payload));
}

function isExplicitFailure(payload) {
    const code = responseCode(payload);
    return payload?.status === 'error'
        || (code !== null && code !== 200);
}

function isExplicitSuccess(payload) {
    return responseCode(payload) === 200 && payload?.status !== 'error';
}

function strategyIdFrom(payload) {
    const value = String(payload?.info?.id ?? '').trim();
    return /^[A-Za-z0-9_.:-]{1,64}$/.test(value) ? value : '';
}

function orderIdFrom(payload) {
    const info = payload?.info && typeof payload.info === 'object'
        ? payload.info : {};
    const candidates = [
        payload?.order_id,
        payload?.orderId,
        payload?.entrust_id,
        payload?.entrustId,
        payload?.contract_id,
        payload?.contractId,
        info.order_id,
        info.orderId,
        info.entrust_id,
        info.entrustId,
        info.contract_id,
        info.contractId,
    ].map((value) => String(value ?? '').trim())
        .filter((value) => /^[A-Za-z0-9_.:-]{1,64}$/.test(value));
    const unique = [...new Set(candidates)];
    return unique.length === 1 ? unique[0] : '';
}

async function capturedResponses(page, {minimum = 1, attempts = 16} = {}) {
    const captures = [];
    try {
        await page.waitForCapture(8);
    } catch (_error) {
        // The next operation is read-only; the initiating click is never repeated.
    }
    for (let attempt = 0; attempt < attempts; attempt += 1) {
        const next = await page.getInterceptedRequests();
        if (Array.isArray(next)) captures.push(...next);
        if (captures.length >= minimum) break;
        await page.wait({time: 0.5});
    }
    return captures.filter((value) => value && typeof value === 'object');
}

async function clearLocalDraft(page) {
    try {
        await navigate(page, ROUTES.packageList);
        return true;
    } catch (_error) {
        return false;
    }
}

async function readTerminalStatus(page) {
    let terminal = null;
    for (let attempt = 0; attempt < 20; attempt += 1) {
        terminal = await page.evaluate(TERMINAL_STATUS_SCRIPT);
        if (terminal?.success || terminal?.failure
                || terminal?.non_trading_time) break;
        await page.wait({time: 0.5});
    }
    return terminal || {};
}

cli({
    site: SITE,
    name: 'submit',
    description: 'Submit one verified package-limit strategy through trusted UI controls',
    access: 'write',
    domain: 'quant.foundersc.com',
    strategy: Strategy.UI,
    browser: true,
    siteSession: 'persistent',
    defaultWindowMode: 'foreground',
    navigateBefore: false,
    args: [
        {name: 'route', required: true, help: 'package-limit only'},
        {name: 'expected-environment', default: 'mock'},
        {name: 'logical-account-id', default: 'primary'},
        {name: 'expected-fund-account-fingerprint', required: true},
        {name: 'claim-id', required: true, help: 'Bounded caller correlation id'},
        {name: 'strategy-name', required: true, help: 'Exact unique name, at most 8 characters'},
        {name: 'code', required: true},
        {name: 'side', required: true, help: 'buy or sell'},
        {name: 'price', required: true},
        {name: 'quantity', required: true},
        {name: 'preflight-only', default: 'false'},
    ],
    columns: RECEIPT_COLUMNS,
    func: async (page, kwargs) => {
        const input = parseInput(kwargs);
        let state = null;
        let finalSubmitPossible = false;
        try {
            await navigateFresh(page, ROUTES.assets);
            const preflightState = await readEnvironment(page);
            const preflightGate = environmentGate(
                preflightState,
                input.expectedEnvironment
            );
            if (preflightGate) {
                return asSingleReceipt(packageReceipt(input, preflightState, {
                    status: preflightGate.status,
                    status_reason: preflightGate.reason,
                    submitted: false,
                    reconcile_required: preflightGate.reconcile_required,
                }));
            }
            if (preflightState.fund_account_fingerprint !== input.expectedFundAccountFingerprint
                    || preflightState.fund_account_match_count !== 1) {
                return asSingleReceipt(packageReceipt(input, preflightState, {
                    status: 'account_mismatch',
                    status_reason: 'expected_account_proof_mismatch',
                    submitted: false,
                    reconcile_required: false,
                }));
            }

            await navigate(page, ROUTES.packageList);
            let routeState = await readEnvironment(page);
            state = carryEnvironmentProof(preflightState, routeState);
            const listGate = environmentGate(state, input.expectedEnvironment);
            if (listGate) {
                return asSingleReceipt(packageReceipt(input, state, {
                    status: listGate.status,
                    status_reason: listGate.reason,
                    submitted: false,
                    reconcile_required: listGate.reconcile_required,
                }));
            }
            const beforeList = await page.evaluate(
                strategyListScript(input.strategyName)
            );
            if (beforeList?.unique_dom_proven !== true
                    || beforeList.exact_strategy_name_match_count !== 0) {
                return asSingleReceipt(packageReceipt(input, state, {
                    status: beforeList?.unique_dom_proven === true
                        ? 'rejected' : 'unknown',
                    status_reason: beforeList?.exact_strategy_name_match_count > 0
                        ? 'exact_strategy_name_already_exists'
                        : 'strategy_list_dom_not_unique',
                    submitted: false,
                    reconcile_required: beforeList?.unique_dom_proven !== true,
                    locator_proof: beforeList || {},
                }));
            }

            await navigate(page, ROUTES.packageCreate);
            routeState = await readEnvironment(page);
            state = carryEnvironmentProof(preflightState, routeState);
            const createGate = environmentGate(state, input.expectedEnvironment);
            if (createGate) {
                return asSingleReceipt(packageReceipt(input, state, {
                    status: createGate.status,
                    status_reason: createGate.reason,
                    submitted: false,
                    reconcile_required: createGate.reconcile_required,
                }));
            }
            const addTarget = await page.evaluate(addSecurityTargetScript());
            if (addTarget?.unique_dom_proven !== true || !addTarget.page_empty) {
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'unknown',
                    status_reason: 'package_create_dom_not_unique_or_not_empty',
                    submitted: false,
                    reconcile_required: true,
                    locator_proof: addTarget || {},
                }));
            }
            await page.click(
                `[${SUBMIT_TARGET_ATTRIBUTE}="package-limit-add-security"]`
            );
            const modal = await page.evaluate(addSecurityModalScript(input));
            if (modal?.unique_dom_proven !== true
                    || modal.numeric_readback_proven !== true
                    || modal.exact_readback_proven !== true
                    || modal.confirm_enabled !== true) {
                await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'capability_gap',
                    status_reason: 'package_modal_readback_not_proven',
                    submitted: false,
                    reconcile_required: true,
                    field_readback: modal?.field_readback || {},
                    locator_proof: modal || {},
                }));
            }
            await page.click(
                `[${SUBMIT_TARGET_ATTRIBUTE}="package-limit-add-confirm"]`
            );
            let draft = await readDraftWithWait(page, input);
            if (draft?.unique_dom_proven !== true
                    || draft.numeric_readback_proven !== true) {
                await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'capability_gap',
                    status_reason: 'package_draft_readback_not_proven',
                    submitted: false,
                    reconcile_required: true,
                    field_readback: draft?.field_readback || {},
                    locator_proof: draft || {},
                }));
            }
            if (!draft.security_checkbox_checked) {
                await page.setChecked(
                    `[${SUBMIT_TARGET_ATTRIBUTE}="package-limit-security-checkbox"]`,
                    true
                );
            }
            if (!draft.risk_checkbox_checked) {
                await page.setChecked(
                    `[${SUBMIT_TARGET_ATTRIBUTE}="package-limit-risk-checkbox"]`,
                    true
                );
            }
            draft = await page.evaluate(draftReadbackScript(input));
            if (draft?.unique_dom_proven !== true
                    || draft.numeric_readback_proven !== true
                    || draft.security_checkbox_checked !== true
                    || draft.risk_checkbox_checked !== true) {
                await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'capability_gap',
                    status_reason: 'required_checkbox_or_draft_readback_failed',
                    submitted: false,
                    reconcile_required: true,
                    field_readback: draft?.field_readback || {},
                    locator_proof: draft || {},
                }));
            }

            await page.installInterceptor('/qt/packageTask/');
            await page.getInterceptedRequests();
            await page.click(
                `[${SUBMIT_TARGET_ATTRIBUTE}="package-limit-submit-order"]`
            );
            const naming = await page.evaluate(strategyNameModalScript(input));
            if (naming?.present === true) {
                if (naming.unique_dom_proven !== true) {
                    await clearLocalDraft(page);
                    return asSingleReceipt(packageReceipt(input, state, {
                        status: 'unknown',
                        status_reason: 'strategy_name_modal_not_proven',
                        submitted: false,
                        saved: false,
                        started: false,
                        reconcile_required: true,
                        locator_proof: naming || {},
                        field_readback: draft.field_readback,
                    }));
                }
                await page.click(
                    `[${SUBMIT_TARGET_ATTRIBUTE}="package-limit-name-confirm"]`
                );
            }
            const preEntrust = await capturedResponses(page, {
                minimum: 1,
                attempts: 8,
            });
            const preTerminal = await page.evaluate(TERMINAL_STATUS_SCRIPT);
            if (preTerminal?.non_trading_time
                    || preEntrust.some(isNonTradingResponse)) {
                const cleared = await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'rejected',
                    status_reason: 'non_trading_time',
                    submitted: false,
                    saved: false,
                    started: false,
                    reconcile_required: false,
                    form_closed: cleared,
                    field_readback: draft.field_readback,
                }));
            }
            if (preEntrust.length !== 1 || isExplicitFailure(preEntrust[0])) {
                const explicit = preEntrust.length === 1
                    && isExplicitFailure(preEntrust[0]);
                const failure = explicit
                    ? classifyPreEntrustFailure(preEntrust[0], input.code)
                    : null;
                const cleared = await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: explicit ? 'rejected' : 'unknown',
                    status_reason: explicit
                        ? 'pre_entrust_rejected'
                        : 'pre_entrust_receipt_not_unique',
                    submitted: false,
                    saved: false,
                    started: false,
                    reconcile_required: !explicit,
                    form_closed: cleared,
                    error_code: failure?.category || null,
                    field_readback: {
                        ...draft.field_readback,
                        pre_entrust_failure_category: failure?.category || null,
                        pre_entrust_response_code: failure?.response_code ?? null,
                    },
                    locator_proof: {
                        pre_entrust_failure_category: failure?.category || null,
                        pre_entrust_response_code: failure?.response_code ?? null,
                        final_submit_click_count: 0,
                    },
                }));
            }
            if (!isExplicitSuccess(preEntrust[0])) {
                await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'unknown',
                    status_reason: 'pre_entrust_receipt_unrecognized',
                    submitted: false,
                    reconcile_required: true,
                    field_readback: draft.field_readback,
                }));
            }
            if (input.preflightOnly) {
                const confirmation = await page.evaluate(
                    serverConfirmationScript(input)
                );
                const cleared = await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: confirmation?.server_confirmation_proven === true
                        ? 'prepared_readback'
                        : 'unknown',
                    status_reason:
                        confirmation?.server_confirmation_proven === true
                            ? 'pre_entrust_validated_without_submit'
                            : 'server_confirmation_not_proven_without_submit',
                    submitted: false,
                    saved: false,
                    started: false,
                    reconcile_required: false,
                    form_closed: cleared,
                    field_readback: {
                        ...draft.field_readback,
                        pre_entrust_validated: true,
                    },
                    locator_proof: {
                        ...(confirmation || {}),
                        pre_entrust_validated: true,
                        final_submit_click_count: 0,
                    },
                }));
            }
            const confirmation = await page.evaluate(
                serverConfirmationScript(input)
            );
            if (confirmation?.server_confirmation_proven !== true) {
                await clearLocalDraft(page);
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'unknown',
                    status_reason: 'server_confirmation_not_proven',
                    submitted: false,
                    reconcile_required: true,
                    locator_proof: confirmation || {},
                    field_readback: draft.field_readback,
                }));
            }

            await page.getInterceptedRequests();
            finalSubmitPossible = true;
            await page.click(
                `[${SUBMIT_TARGET_ATTRIBUTE}="package-limit-server-confirm"]`
            );
            const terminalCaptures = await capturedResponses(page, {
                minimum: 2,
                attempts: 20,
            });
            const terminal = await readTerminalStatus(page);
            const saveReceipt = terminalCaptures[0] || null;
            const entrustReceipt = terminalCaptures[1] || null;
            const stableStrategyId = strategyIdFrom(saveReceipt);
            const saveSucceeded = terminalCaptures.length === 2
                && Boolean(stableStrategyId)
                && isExplicitSuccess(saveReceipt);
            const saveFailed = terminalCaptures.length === 1
                && !stableStrategyId && isExplicitFailure(saveReceipt);
            const entrustSucceeded = saveSucceeded
                && isExplicitSuccess(entrustReceipt)
                && Boolean(orderIdFrom(entrustReceipt));
            const entrustFailed = saveSucceeded
                && isExplicitFailure(entrustReceipt);
            const stableOrderId = entrustSucceeded
                ? orderIdFrom(entrustReceipt) : '';

            await navigate(page, ROUTES.packageList);
            const afterList = await page.evaluate(
                strategyListScript(input.strategyName)
            );
            const exactStrategyUnique = afterList?.unique_dom_proven === true
                && afterList.exact_strategy_name_match_count === 1;
            if (terminal.success && saveSucceeded && entrustSucceeded
                    && exactStrategyUnique) {
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'submitted',
                    status_reason: 'save_and_entrust_receipts_confirmed',
                    strategy_id: stableStrategyId,
                    order_id: stableOrderId,
                    requested_shares: input.quantity,
                    order_price: input.price,
                    submitted_at: new Date().toISOString(),
                    submitted: true,
                    saved: true,
                    started: false,
                    reconcile_required: true,
                    field_readback: draft.field_readback,
                    locator_proof: {
                        strategy_name_modal: naming,
                        server_confirmation: confirmation,
                        exact_strategy_name_match_count: 1,
                        unique_dom_proven: true,
                    },
                }));
            }
            if (terminal.failure && saveFailed
                    && afterList?.unique_dom_proven === true
                    && afterList.exact_strategy_name_match_count === 0) {
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'rejected',
                    status_reason: 'save_rejected',
                    submitted: false,
                    saved: false,
                    started: false,
                    reconcile_required: false,
                    field_readback: draft.field_readback,
                }));
            }
            if (terminal.failure && entrustFailed && exactStrategyUnique) {
                return asSingleReceipt(packageReceipt(input, state, {
                    status: 'rejected',
                    status_reason: 'entrust_rejected_after_save_attempt',
                    strategy_id: stableStrategyId || null,
                    submitted: false,
                    saved: true,
                    started: false,
                    reconcile_required: Boolean(stableStrategyId),
                    field_readback: draft.field_readback,
                }));
            }
            return asSingleReceipt(packageReceipt(input, state, {
                status: 'unknown',
                status_reason: 'save_or_entrust_receipt_incomplete',
                strategy_id: stableStrategyId || null,
                submitted: null,
                saved: stableStrategyId ? true : null,
                started: null,
                reconcile_required: true,
                locator_proof: {
                    exact_strategy_name_match_count:
                        afterList?.exact_strategy_name_match_count ?? null,
                    unique_dom_proven: afterList?.unique_dom_proven === true,
                    terminal_success: terminal.success === true,
                    terminal_failure: terminal.failure === true,
                    save_receipt_count: saveReceipt ? 1 : 0,
                    entrust_receipt_count: entrustReceipt ? 1 : 0,
                },
                field_readback: draft.field_readback,
            }));
        } catch (error) {
            return asSingleReceipt(packageReceipt(input, state, {
                status: 'unknown',
                status_reason: finalSubmitPossible
                    ? 'submit_outcome_requires_reconciliation'
                    : 'submit_precondition_or_ui_failure',
                error_code: String(error?.name || 'Error').slice(0, 64),
                submitted: finalSubmitPossible ? null : false,
                saved: finalSubmitPossible ? null : false,
                started: finalSubmitPossible ? null : false,
                reconcile_required: true,
            }));
        }
    },
});
