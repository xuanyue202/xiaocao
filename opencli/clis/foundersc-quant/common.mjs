export const TEMPLATE_VERSION = 3;
export const SITE = 'foundersc-quant';
export const DEFAULT_BASE_URL = (
    'https://quant.foundersc.com/qtassets/dist/index.html'
);

export const ROUTES = Object.freeze({
    assets: '#/home/myAccount/assets',
    query: '#/home/myAccount/query',
    conditionActive: '#/home/conditionStrategy/active',
    combo: '#/home/combAlgorithm',
    manual: '#/home/orderByHand',
    auction: '#/home/combAlgorithm/create?type=%E7%9B%98%E5%89%8D%E9%9B%86%E5%90%88%E7%AB%9E%E4%BB%B7',
});

export const RECEIPT_COLUMNS = Object.freeze([
    'template_name',
    'template_version',
    'status',
    'environment',
    'expected_environment',
    'logical_account_id',
    'account_binding',
    'login_account_fingerprint',
    'fund_account_fingerprint',
    'route',
    'order_id',
    'strategy_id',
    'task_id',
    'requested_shares',
    'filled_shares',
    'remaining_shares',
    'order_price',
    'fill_price',
    'latest_price',
    'active',
    'status_reason',
    'error_code',
    'observed_at',
    'submitted_at',
    'cancelled_at',
    'retry_allowed',
    'field_readback',
    'submitted',
    'saved',
    'started',
    'cancelled',
    'reconcile_required',
    'reconcile_complete',
    'locator_proof',
    'capabilities',
    'failure_type',
    'ready_for_submit',
    'form_closed',
    'submit_capability',
]);

export const ENVIRONMENT_SCRIPT = String.raw`(() => {
    const visible = (node) => {
        if (!node) return false;
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return rect.width > 0 && rect.height > 0
            && style.display !== 'none'
            && style.visibility !== 'hidden'
            && Number(style.opacity) !== 0;
    };
    const exactLeafCount = (root, text) => {
        if (!root) return 0;
        return [...root.querySelectorAll('*')].filter((node) => (
            node.children.length === 0
            && visible(node)
            && (node.textContent || '').trim() === text
        )).length;
    };
    const accountFingerprint = (account) => {
        if (account.length < 8) return '';
        return account.slice(0, 3) + '******' + account.slice(-3);
    };
    const body = (document.body?.innerText || '').trim();
    const switchers = [...document.querySelectorAll('div.switcher___KVAWw')];
    const switcher = switchers.length === 1 ? switchers[0] : null;
    const mockLabelMatches = exactLeafCount(switcher, '模拟盘交易');
    const liveLabelMatches = exactLeafCount(switcher, '实盘交易');
    const mockActionMatches = exactLeafCount(switcher, '点击切换至实盘');
    const liveActionMatches = exactLeafCount(switcher, '点击切换至模拟盘');
    const environment = mockLabelMatches === 1 && liveLabelMatches === 0
        ? 'mock'
        : liveLabelMatches === 1 && mockLabelMatches === 0
            ? 'live'
            : 'unknown';
    const accountMatches = [...body.matchAll(/\b1\d{10}\b/g)]
        .map((match) => match[0]);
    const maskedAccount = accountMatches.length > 0
        ? accountFingerprint(accountMatches[0])
        : '';
    const authState = environment !== 'unknown'
        ? 'authenticated'
        : /登录|资金账号|手机登录/.test(body)
            ? 'login_required'
            : 'unknown';
    return {
        environment,
        auth_state: authState,
        route: location.hash || '',
        switcher_count: switchers.length,
        mock_label_matches: mockLabelMatches,
        live_label_matches: liveLabelMatches,
        mock_action_matches: mockActionMatches,
        live_action_matches: liveActionMatches,
        login_account_fingerprint: maskedAccount,
        fund_account_fingerprint: '',
        fund_account_match_count: 0,
        fund_account_proof_source: '',
        account_binding: 'not_proven',
        logical_account_id: null,
    };
})()`;

export const FUND_ACCOUNT_SCRIPT = String.raw`(async () => {
    const empty = {
        fund_account_fingerprint: '',
        fund_account_match_count: 0,
        fund_account_proof_source: '',
    };
    const accountFingerprint = (account) => {
        if (account.length < 8) return '';
        return account.slice(0, 3) + '******' + account.slice(-3);
    };
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    try {
        const response = await fetch('/qt/user/getBaseInfo', {
            credentials: 'same-origin',
            signal: controller.signal,
        });
        if (!response.ok) return empty;
        const payload = await response.json();
        const info = payload && typeof payload.info === 'object'
            ? payload.info
            : {};
        const accounts = [info.fund_id, info.fundId]
            .map((value) => String(value || '').trim())
            .filter((value) => /^\d{6,20}$/.test(value));
        const uniqueAccounts = [...new Set(accounts)];
        if (uniqueAccounts.length !== 1) return empty;
        const account = uniqueAccounts[0];
        return {
            fund_account_fingerprint: accountFingerprint(account),
            fund_account_match_count: 1,
            fund_account_proof_source: 'same_origin_getBaseInfo',
        };
    } catch {
        return empty;
    } finally {
        clearTimeout(timeoutId);
    }
})()`;

export const PAGE_HELPERS = String.raw`
    const visible = (node) => {
        if (!node) return false;
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return rect.width > 0 && rect.height > 0
            && style.display !== 'none'
            && style.visibility !== 'hidden'
            && Number(style.opacity) !== 0;
    };
    const exactLeaves = (root, text) => root
        ? [...root.querySelectorAll('*')].filter((node) => (
            node.children.length === 0
            && visible(node)
            && (node.textContent || '').trim() === text
        ))
        : [];
    const maskAccount = (account) => account.length < 8
        ? '******'
        : account.slice(0, 3) + '******' + account.slice(-3);
    const tableHeaders = (table) => (
        [...table.querySelectorAll('thead th')]
            .map((cell) => (cell.innerText || cell.textContent || '').trim())
    );
    const fundAccountColumnIndexes = (table) => tableHeaders(table)
        .map((header, index) => header === '资金账号' ? index : -1)
        .filter((index) => index >= 0);
    const tableFundAccounts = [...document.querySelectorAll('table')]
        .flatMap((table) => {
            const indexes = fundAccountColumnIndexes(table);
            if (indexes.length !== 1) return [];
            return [...table.querySelectorAll('tbody tr')]
                .flatMap((row) => {
                    const cells = [...row.querySelectorAll('th,td')];
                    const account = String(
                        cells[indexes[0]]?.innerText
                            || cells[indexes[0]]?.textContent
                            || ''
                    ).trim();
                    return /^\d{6,20}$/.test(account) ? [account] : [];
                });
        });
    const knownFundAccounts = [...new Set(tableFundAccounts)];
    const sanitize = (value) => {
        let sanitized = String(value || '');
        for (const account of knownFundAccounts) {
            sanitized = sanitized.split(account).join(maskAccount(account));
        }
        return sanitized.replace(/\b\d{8,20}\b/g, maskAccount);
    };
    const sanitizeTableRow = (table, row) => {
        const indexes = fundAccountColumnIndexes(table);
        const cells = [...row.querySelectorAll('th,td')];
        return cells.map((cell, index) => {
            const value = (cell.innerText || cell.textContent || '').trim();
            if (indexes.includes(index)
                    && /^\d{6,20}$/.test(value)) {
                return maskAccount(value);
            }
            return sanitize(value);
        });
    };
    const paginationSelectors = [
        '.ant-pagination',
        '.el-pagination',
        '.pagination',
    ];
    const paginationState = (root) => {
        const paginationRoots = paginationSelectors.flatMap((selector) => (
            [...root.querySelectorAll(selector)].filter(visible)
        ));
        const controls = [...root.querySelectorAll(
            '[aria-label="下一页"], [aria-label="Next Page"], '
            + '[title="下一页"], [title="Next Page"], button, a'
        )].filter(visible);
        const nextControls = controls.filter((node) => {
            const label = (node.getAttribute('aria-label') || '').trim();
            const title = (node.getAttribute('title') || '').trim();
            const text = (node.innerText || node.textContent || '').trim();
            return label === '下一页' || label === 'Next Page'
                || title === '下一页' || title === 'Next Page'
                || text === '下一页' || text === 'Next Page';
        });
        return {
            root_count: paginationRoots.length,
            next_count: nextControls.length,
            next: nextControls.length === 1 ? nextControls[0] : null,
            present: paginationRoots.length > 0 || nextControls.length > 0,
        };
    };
    const disabled = (node) => node?.disabled === true
        || node?.getAttribute('disabled') !== null
        || node?.getAttribute('aria-disabled') === 'true'
        || node?.classList?.contains('disabled') === true;
    const waitForPage = (milliseconds) => new Promise((resolve) => (
        setTimeout(resolve, milliseconds)
    ));
    const mergeTablePages = (pages) => {
        const headers = [...new Set(pages.flatMap((page) => (
            page.headers || []
        )))];
        const rows = pages.flatMap((page) => page.rows || []);
        return {headers, rows, row_count: rows.length};
    };
    const scanTablePages = async (root, readPage) => {
        const pages = [];
        const signatures = new Set();
        let pagination_present = false;
        let pagination_complete = true;
        let page_count = 0;
        for (; page_count < 100; page_count += 1) {
            const page = readPage();
            pages.push(page);
            const signature = JSON.stringify(page);
            if (signatures.has(signature)) {
                pagination_complete = false;
                break;
            }
            signatures.add(signature);
            const state = paginationState(root);
            pagination_present = pagination_present || state.present;
            if (!state.present) break;
            if (state.root_count !== 1 || state.next_count !== 1) {
                pagination_complete = false;
                break;
            }
            if (disabled(state.next)) break;
            state.next.click();
            await waitForPage(100);
        }
        if (page_count >= 100) pagination_complete = false;
        return {
            pages,
            page_count: pages.length,
            pagination_present,
            pagination_complete,
        };
    };
    const scanVirtualList = async (root, readRows) => {
        const candidates = [root, ...root.querySelectorAll('*')]
            .filter(visible)
            .filter((node) => {
                const style = getComputedStyle(node);
                return ['auto', 'scroll'].includes(style.overflowY)
                    && Number(node.scrollHeight) > Number(node.clientHeight);
            });
        if (candidates.length === 0) {
            return {
                rows: readRows(),
                virtual_present: false,
                virtual_complete: true,
                scroll_root_count: 0,
            };
        }
        if (candidates.length !== 1) {
            return {
                rows: readRows(),
                virtual_present: true,
                virtual_complete: false,
                scroll_root_count: candidates.length,
            };
        }
        const scrollRoot = candidates[0];
        const rows = [];
        const seenRows = new Set();
        for (let step = 0; step < 100; step += 1) {
            for (const row of readRows()) {
                if (!seenRows.has(row)) {
                    seenRows.add(row);
                    rows.push(row);
                }
            }
            const scrollHeight = Number(scrollRoot.scrollHeight);
            const clientHeight = Number(scrollRoot.clientHeight);
            const maximum = scrollHeight - clientHeight;
            const before = Number(scrollRoot.scrollTop || 0);
            if (!Number.isFinite(maximum) || maximum <= 0) {
                return {
                    rows,
                    virtual_present: true,
                    virtual_complete: false,
                    scroll_root_count: 1,
                };
            }
            if (before >= maximum - 1) {
                return {
                    rows,
                    virtual_present: true,
                    virtual_complete: true,
                    scroll_root_count: 1,
                };
            }
            scrollRoot.scrollTop = Math.min(
                maximum,
                before + Math.max(1, clientHeight)
            );
            await waitForPage(50);
            if (Number(scrollRoot.scrollTop || 0) <= before) break;
        }
        return {
            rows,
            virtual_present: true,
            virtual_complete: false,
            scroll_root_count: 1,
        };
    };
    const setValue = (node, value) => {
        const setter = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype,
            'value'
        )?.set;
        if (setter) setter.call(node, String(value));
        else node.value = String(value);
        node.dispatchEvent(new Event('input', {bubbles: true}));
        node.dispatchEvent(new Event('change', {bubbles: true}));
    };
    const setSelect = (node, value) => {
        node.value = String(value);
        node.dispatchEvent(new Event('change', {bubbles: true}));
    };
`;

export function pageScript(body, {async = false} = {}) {
    const opener = async ? '(async () => {' : '(() => {';
    return `${opener}\n${PAGE_HELPERS}\n${body}\n})()`;
}

export const MANUAL_ROUTE_DISCOVERY_SCRIPT = pageScript(String.raw`
    const routes = [...document.querySelectorAll('a[href]')]
        .filter(visible)
        .map((link) => {
            try {
                const url = new URL(link.getAttribute('href'), location.href);
                if (url.origin !== location.origin
                    || url.pathname !== location.pathname) {
                    return null;
                }
                const hash = url.hash || '';
                return /^#\/home\/orderByHand\/[^/]+\/entrustDetail(?:[/?]|$)/
                    .test(hash)
                    ? hash
                    : null;
            } catch (_error) {
                return null;
            }
        })
        .filter(Boolean);
    const uniqueRoutes = [...new Set(routes)];
    return {
        route_available: routes.length === 1 && uniqueRoutes.length === 1,
        link_count: routes.length,
        unique_route_count: uniqueRoutes.length,
        route: routes.length === 1 && uniqueRoutes.length === 1
            ? uniqueRoutes[0]
            : '',
    };
`);

function decodeRoute(value) {
    try {
        return decodeURIComponent(value);
    } catch (_error) {
        return value;
    }
}

export function isManualEntrustRoute(value) {
    return /^#\/home\/orderByHand\/[^/]+\/entrustDetail(?:[/?]|$)/
        .test(decodeRoute(String(value || '').trim()));
}

export function routeMatches(routeName, expectedRoute, observedRoute) {
    const observed = String(observedRoute || '').trim();
    if (!observed) return false;
    const observedVariants = [observed, decodeRoute(observed)];
    const expectedVariants = [
        expectedRoute,
        decodeRoute(expectedRoute),
    ];
    if (routeName === 'manual') {
        return isManualEntrustRoute(observed)
            && observedVariants.some((value) => expectedVariants.includes(value));
    }
    return observedVariants.some((value) => expectedVariants.some((expected) => (
        value === expected
            || value.startsWith(`${expected}?`)
            || value.startsWith(`${expected}&`)
    )));
}

export function configuredBaseUrl() {
    const configured = String(
        globalThis.process?.env?.FZZQ_QUANT_BASE_URL || ''
    ).trim();
    const raw = configured || DEFAULT_BASE_URL;
    let parsed;
    try {
        parsed = new URL(raw);
    } catch (_error) {
        return DEFAULT_BASE_URL;
    }
    if (parsed.origin !== 'https://quant.foundersc.com'
            || parsed.pathname !== '/qtassets/dist/index.html') {
        return DEFAULT_BASE_URL;
    }
    return parsed.origin + parsed.pathname;
}

export function routeUrl(route) {
    return configuredBaseUrl() + route;
}

export function normalizeEnvironment(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'mock' || normalized === 'live') return normalized;
    throw new Error('--expected-environment must be mock or live');
}

export function normalizeLogicalAccountId(value) {
    const normalized = String(value || '').trim();
    if (!/^[A-Za-z0-9_.:-]{1,64}$/.test(normalized)) {
        throw new Error('--logical-account-id must be a bounded identifier');
    }
    return normalized;
}

export function normalizeCode(value) {
    const normalized = String(value || '').trim();
    if (!/^\d{6}$/.test(normalized)) {
        throw new Error('--code must be a six-digit A-share security code');
    }
    return normalized;
}

export function normalizePositiveInteger(value, flag) {
    const normalized = String(value || '').trim();
    if (!/^\d+$/.test(normalized) || Number(normalized) <= 0) {
        throw new Error(`${flag} must be a positive integer`);
    }
    return Number(normalized);
}

export function normalizeNonNegativeNumber(value, flag) {
    const normalized = String(value ?? '').trim();
    if (!/^\d+(?:\.\d+)?$/.test(normalized)) {
        throw new Error(`${flag} must be a non-negative decimal`);
    }
    const number = Number(normalized);
    if (!Number.isFinite(number)) throw new Error(`${flag} is not finite`);
    return number;
}

export function normalizeSide(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'buy' || normalized === '买入') return '买入';
    if (normalized === 'sell' || normalized === '卖出') return '卖出';
    throw new Error('--side must be buy or sell');
}

export function normalizeDate(value) {
    const normalized = String(value || '').trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
        throw new Error('--date must use YYYY-MM-DD');
    }
    return normalized;
}

export function normalizeTime(value) {
    const normalized = String(value || '').trim();
    const match = /^(\d{1,2}):(\d{2})$/.exec(normalized);
    if (!match || Number(match[1]) > 23 || Number(match[2]) > 59) {
        throw new Error('--time must use HH:MM');
    }
    return `${String(Number(match[1])).padStart(2, '0')}:${match[2]}`;
}

export function normalizeAuctionMinute(value) {
    const minute = Number(String(value || '').trim());
    if (![20, 21, 22, 23, 24].includes(minute)) {
        throw new Error('--minute must be one of 20,21,22,23,24');
    }
    return minute;
}

export function normalizeAuctionSeconds(value) {
    const seconds = Number(String(value || '').trim());
    if (!Number.isInteger(seconds) || seconds < 0 || seconds > 59) {
        throw new Error('--seconds must be an integer from 0 to 59');
    }
    return seconds;
}

export function normalizeParticipation(value) {
    const percentage = normalizeNonNegativeNumber(value, '--participation');
    if (percentage <= 0 || percentage > 30) {
        throw new Error('--participation must be greater than 0 and at most 30');
    }
    return percentage;
}

export async function navigate(page, route) {
    const url = routeUrl(route);
    await page.goto(url, {
        waitUntil: 'domcontentloaded',
        settleMs: 1000,
        timeout: 45000,
    });
    await page.wait({time: 1});
    return url;
}

export async function readEnvironment(page) {
    let state = null;
    for (let attempt = 0; attempt < 30; attempt += 1) {
        state = await page.evaluate(ENVIRONMENT_SCRIPT);
        if (!state || typeof state !== 'object') {
            throw new Error('environment probe returned a malformed object');
        }
        if (state.environment !== 'unknown'
                || state.auth_state !== 'unknown') {
            if (state.environment !== 'unknown'
                    && state.fund_account_match_count !== 1) {
                for (let accountAttempt = 0; accountAttempt < 3; accountAttempt += 1) {
                    const account = await page.evaluate(FUND_ACCOUNT_SCRIPT);
                    if (account && typeof account === 'object') {
                        state = {...state, ...account};
                    }
                    if (state.fund_account_match_count === 1) break;
                    if (accountAttempt < 2) await page.wait({time: 0.5});
                }
            }
            return state;
        }
        await page.wait({time: 1});
    }
    return state;
}

export function environmentGate(state, expectedEnvironment) {
    if (!state || typeof state !== 'object') {
        return {
            status: 'unknown',
            reason: 'environment_probe_missing',
            reconcile_required: true,
        };
    }
    if (state.auth_state === 'login_required') {
        return {
            status: 'auth_required',
            reason: 'persistent_session_requires_user_authentication',
            reconcile_required: false,
        };
    }
    if (state.switcher_count !== 1 || state.environment === 'unknown') {
        return {
            status: 'unknown',
            reason: 'environment_locator_not_unique_or_not_readable',
            reconcile_required: true,
        };
    }
    if (state.environment !== expectedEnvironment) {
        return {
            status: 'environment_mismatch',
            reason: 'page_environment_does_not_match_plan',
            reconcile_required: false,
        };
    }
    return null;
}

export function baseReceipt(templateName, route, expectedEnvironment, state, fields = {}) {
    return {
        template_name: templateName,
        template_version: TEMPLATE_VERSION,
        status: 'unknown',
        environment: state?.environment || 'unknown',
        expected_environment: expectedEnvironment,
        logical_account_id: fields.logical_account_id || 'primary',
        account_binding: state?.account_binding || 'not_proven',
        login_account_fingerprint: state?.login_account_fingerprint || '',
        fund_account_fingerprint: state?.fund_account_fingerprint || '',
        route,
        order_id: null,
        strategy_id: null,
        task_id: null,
        requested_shares: null,
        filled_shares: null,
        remaining_shares: null,
        order_price: null,
        fill_price: null,
        latest_price: null,
        active: null,
        status_reason: null,
        error_code: null,
        observed_at: new Date().toISOString(),
        submitted_at: null,
        cancelled_at: null,
        retry_allowed: null,
        field_readback: {},
        submitted: false,
        saved: false,
        started: false,
        cancelled: false,
        reconcile_required: true,
        reconcile_complete: null,
        submit_capability: false,
        locator_proof: {},
        capabilities: {
            submit: false,
            account_binding: state?.account_binding === 'proven',
            receipt_mapping: false,
            cancellation: false,
        },
        ...fields,
    };
}

export function unknownReceipt(templateName, route, expectedEnvironment, state, stage, error, fields = {}) {
    return baseReceipt(templateName, route, expectedEnvironment, state, {
        status: 'unknown',
        status_reason: `browser_${stage}_failed`,
        failure_type: error?.name || 'Error',
        reconcile_required: true,
        ...fields,
    });
}

export function gateReceipt(templateName, route, expectedEnvironment, state, gate, fields = {}) {
    return baseReceipt(templateName, route, expectedEnvironment, state, {
        status: gate.status,
        status_reason: gate.reason,
        reconcile_required: gate.reconcile_required,
        ...fields,
    });
}

export function asSingleReceipt(receipt) {
    // OpenCLI's table renderer consumes an array of rows even when this
    // command returns exactly one broker-neutral receipt.
    return [receipt];
}
