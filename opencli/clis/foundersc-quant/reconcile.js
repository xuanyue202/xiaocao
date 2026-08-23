import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError } from '@jackwener/opencli/errors';
import {
    RECEIPT_COLUMNS,
    ROUTES,
    SITE,
    MANUAL_ROUTE_DISCOVERY_SCRIPT,
    asSingleReceipt,
    baseReceipt,
    environmentGate,
    navigate,
    normalizeEnvironment,
    normalizeLogicalAccountId,
    pageScript,
    readEnvironment,
    unknownReceipt,
} from './common.mjs';

const TEMPLATE_NAME = `${SITE}/reconcile`;

function parseInput(kwargs) {
    try {
        const scope = String(kwargs.scope || 'all').trim();
        if (!['assets', 'orders', 'strategies', 'all'].includes(scope)) {
            throw new Error('--scope must be assets, orders, strategies or all');
        }
        return {
            scope,
            expectedEnvironment: normalizeEnvironment(kwargs['expected-environment'] || 'mock'),
            logicalAccountId: normalizeLogicalAccountId(
                kwargs['logical-account-id'] || 'primary'
            ),
        };
    } catch (error) {
        throw new ArgumentError(error.message);
    }
}

const ASSETS_SCRIPT = pageScript(String.raw`
        const root = document.body;
        const route = location.hash || '';
        const tableSnapshot = (scope) => {
                const tables = [...scope.querySelectorAll('table')].filter(visible);
                const headers = [...new Set(tables.flatMap((table) => (
                        [...table.querySelectorAll('thead th')].map((cell) => (
                                (cell.innerText || '').trim()
                        )).filter(Boolean)
                )))];
                const rows = tables.flatMap((table) => (
                        [...table.querySelectorAll('tbody tr')].filter(visible).map((row) => (
                                sanitizeTableRow(table, row)
                        ))
                ));
                return {
                        table_count: tables.length,
                        headers,
                        rows,
                        row_count: rows.length,
                };
        };
        const pageScan = await scanTablePages(root, () => tableSnapshot(root));
        const table = mergeTablePages(pageScan.pages);
        const allocationLabels = ['总资产', '证券市值', '可用资金'];
        const numericText = (value) => /^[-+]?\s*(?:¥|￥)?\s*\d[\d,]*(?:\.\d+)?$/
                .test(String(value || '').trim());
        const cardValues = {};
        let cardsComplete = true;
        for (const label of allocationLabels) {
                const labels = exactLeaves(root, label);
                if (labels.length !== 1) {
                        cardsComplete = false;
                        break;
                }
                let container = labels[0].parentNode;
                let value = '';
                for (let depth = 0; container && depth < 4; depth += 1) {
                        const leaves = [container, ...container.querySelectorAll('*')]
                                .filter((node) => node.children.length === 0 && visible(node));
                        const numbers = [...new Set(leaves
                                .map((node) => (node.innerText || node.textContent || '').trim())
                                .filter((text) => text !== label && numericText(text)))];
                        if (numbers.length === 1) {
                                value = numbers[0];
                                break;
                        }
                        container = container.parentNode;
                }
                if (!value) {
                        cardsComplete = false;
                        break;
                }
                cardValues[label] = value;
        }
        const tableValues = {};
        const tableComplete = table.rows.length === 1
                && allocationLabels.every((label) => (
                        table.headers.filter((header) => header === label).length === 1
                ));
        if (tableComplete) {
                for (const label of allocationLabels) {
                        tableValues[label] = table.rows[0][table.headers.indexOf(label)];
                }
        }
        const summaryCandidates = [];
        if (cardsComplete) summaryCandidates.push(cardValues);
        if (tableComplete) summaryCandidates.push(tableValues);
        const uniqueSummaries = [...new Map(summaryCandidates.map((values) => (
                [JSON.stringify(values), values]
        ))).values()];
        const allocationSummary = {
                complete: uniqueSummaries.length === 1,
                source_count: summaryCandidates.length,
                unique_source_count: uniqueSummaries.length,
                values: uniqueSummaries.length === 1 ? uniqueSummaries[0] : {},
        };
        const bodyTextPresent = (root?.innerText || '').trim().length > 0;
        const assetLabelMatches = [
                '总资产',
                '证券市值',
                '可用资金',
                '可取资金',
                '持仓',
        ].filter((label) => exactLeaves(root, label).length === 1).length;
        const pageReady = document.readyState === 'complete';
        const routeMatch = route === '#/home/myAccount/assets'
                || route.startsWith('#/home/myAccount/assets?');
        const surfaceReady = pageReady && bodyTextPresent
                && (assetLabelMatches >= 2
                        || (pageScan.pages[0]?.table_count === 1 && table.headers.length > 0));
        return {
                route,
                route_match: routeMatch,
                page_ready: pageReady,
                body_text: '',
                asset_label_matches: assetLabelMatches,
                table,
                allocation_summary: allocationSummary,
                surface_ready: surfaceReady,
                pagination_present: pageScan.pagination_present,
                pagination_complete: pageScan.pagination_complete,
                page_count: pageScan.page_count,
                complete_scan: routeMatch && surfaceReady
                        && pageScan.pagination_complete,
                stable_keys: {
                        order_id: null,
                        strategy_id: null,
                        task_id: null,
                },
                freshness: 'page_readback_only',
        };
`, {async: true});

const QUERY_SCRIPT = pageScript(String.raw`
        const readTable = (root) => {
                const tables = [...root.querySelectorAll('table')].filter(visible);
                const headers = [...new Set(tables.flatMap((table) => (
                        [...table.querySelectorAll('thead th')].map((cell) => (
                                (cell.innerText || '').trim()
                        )).filter(Boolean)
                )))];
                const rows = tables.flatMap((table) => (
                        [...table.querySelectorAll('tbody tr')].filter(visible).map((row) => (
                                sanitizeTableRow(table, row)
                        ))
                ));
                return {
                        table_count: tables.length,
                        headers,
                        rows,
                        row_count: rows.length,
                };
        };
        const container = document.querySelector('.ma-q-table-container');
        const result = {
                route: location.hash || '',
                route_match: location.hash === '#/home/myAccount/query'
                        || location.hash.startsWith('#/home/myAccount/query?'),
                container_count: document.querySelectorAll('.ma-q-table-container').length,
                tabs: {},
                status_filter: '',
                strategy_filter: '',
                complete_scan: false,
                stable_keys: {
                        order_id: null,
                        strategy_id: null,
                        task_id: null,
                },
        };
        if (!container || result.container_count !== 1) {
                result.reason = 'account_query_container_not_unique';
                return result;
        }
        const status = [...container.querySelectorAll('select')].find((select) => (
                visible(select) && [...select.options].some((option) => (
                        (option.textContent || '').trim() === '全部'
                ))
        ));
        result.status_filter = status?.value || '';
        const tabs = [...container.querySelectorAll('li.gs-tab-line')]
                .filter(visible);
        for (const label of ['当日委托', '当日成交', '历史委托', '历史成交']) {
                const matches = tabs.filter((tab) => exactLeaves(tab, label).length > 0);
                if (matches.length !== 1) {
                        result.tabs[label] = {
                                status: 'not_proven',
                                locator_count: matches.length,
                                complete_scan: false,
                        };
                        continue;
                }
                matches[0].click();
                await waitForPage(100);
                const scan = await scanTablePages(container, () => readTable(container));
                const firstPage = scan.pages[0] || {table_count: 0, headers: []};
                result.tabs[label] = {
                        status: 'read',
                        locator_count: 1,
                        table: mergeTablePages(scan.pages),
                        table_count: firstPage.table_count,
                        surface_ready: firstPage.table_count === 1
                                && firstPage.headers.length > 0,
                        pagination_present: scan.pagination_present,
                        pagination_complete: scan.pagination_complete,
                        page_count: scan.page_count,
                        complete_scan: firstPage.table_count === 1
                                && firstPage.headers.length > 0
                                && scan.pagination_complete,
                };
        }
        result.body_text = '';
        const tabResults = Object.values(result.tabs);
        result.complete_scan = result.route_match
                && tabResults.length === 4
                && tabResults.every((tab) => tab.complete_scan === true);
        return result;
`, {async: true});

const MANUAL_ORDERS_SCRIPT = pageScript(String.raw`
        const readTable = (root) => {
                const tables = [...root.querySelectorAll('table')].filter(visible);
                const relevantTables = tables.filter((table) => (
                        /代码|委托|成交|状态/.test(table.innerText || '')
                ));
                const table = relevantTables.length === 1 ? relevantTables[0] : null;
                if (!table) {
                        return {
                                table_count: tables.length,
                                relevant_table_count: relevantTables.length,
                                headers: [],
                                rows: [],
                                row_count: 0,
                        };
                }
                const headers = [...table.querySelectorAll('thead th')]
                        .map((cell) => (cell.innerText || '').trim()).filter(Boolean);
                const rows = [...table.querySelectorAll('tbody tr')]
                        .filter(visible)
                        .map((row) => sanitizeTableRow(table, row));
                return {
                        table_count: tables.length,
                        relevant_table_count: relevantTables.length,
                        headers,
                        rows,
                        row_count: rows.length,
                };
        };
        const scan = await scanTablePages(document.body, () => readTable(document.body));
        const firstPage = scan.pages[0] || {
                table_count: 0,
                relevant_table_count: 0,
                headers: [],
        };
        const withdrawControls = [...document.querySelectorAll('a.gs-tab-withdraw')]
                .filter(visible);
        const tabs = {};
        for (const label of ['当日委托', '当日成交', '历史委托', '历史成交']) {
                const matches = exactLeaves(document.body, label);
                tabs[label] = {
                        locator_count: matches.length,
                        status: matches.length === 1 ? 'read' : 'not_proven',
                };
        }
        const route = location.hash || '';
        const routeMatch = /^#\/home\/orderByHand\/[^/]+\/entrustDetail(?:[/?]|$)/
                .test(route);
        return {
                route,
                route_match: routeMatch,
                table_count: firstPage.table_count,
                relevant_table_count: firstPage.relevant_table_count,
                table: mergeTablePages(scan.pages),
                tabs,
                withdraw_control_count: withdrawControls.length,
                withdraw_control_present: withdrawControls.length === 1,
                can_withdraw: null,
                pagination_present: scan.pagination_present,
                pagination_complete: scan.pagination_complete,
                page_count: scan.page_count,
                complete_scan: document.readyState === 'complete'
                        && routeMatch
                        && firstPage.relevant_table_count === 1
                        && firstPage.headers.length > 0
                        && scan.pagination_complete,
                body_text: '',
                stable_keys: {
                        order_id: null,
                        strategy_id: null,
                        task_id: null,
                },
        };
`, {async: true});

const COMBO_SCRIPT = pageScript(String.raw`
        const body = sanitize((document.body?.innerText || '').trim());
        const dataBodies = [...document.querySelectorAll('pd-data-body')]
                .filter(visible);
        const dataBody = dataBodies.length === 1 ? dataBodies[0] : null;
        const scan = dataBody
                ? await scanVirtualList(dataBody, () => (
                        [...dataBody.querySelectorAll('tr,[role="row"],.al-table-row')]
                                .filter(visible)
                                .map((row) => sanitize((row.innerText || '').trim()))
                ))
                : {
                        rows: [],
                        virtual_present: false,
                        virtual_complete: false,
                        scroll_root_count: 0,
                };
        const route = location.hash || '';
        const routeMatch = route === '#/home/combAlgorithm'
                || route.startsWith('#/home/combAlgorithm?');
        return {
                route,
                route_match: routeMatch,
                list_container_count: dataBodies.length,
                virtual_scroll: scan.virtual_present,
                virtual_complete: scan.virtual_complete,
                scroll_root_count: scan.scroll_root_count,
                pagination_present: false,
                pagination_complete: true,
                complete_scan: document.readyState === 'complete'
                        && routeMatch
                        && dataBodies.length === 1
                        && scan.virtual_complete,
                rows: scan.rows,
                row_count: scan.rows.length,
                body_text: '',
                stable_keys: {
                        strategy_id: null,
                        task_id: null,
                        order_id: null,
                },
        };
`, {async: true});

const CONDITION_SCRIPT = pageScript(String.raw`
        const listRoots = [
                ...document.querySelectorAll(
                        '[scroll-load-data], .scroll-load-data, .al-table-container'
                ),
        ].filter(visible);
        const listRoot = listRoots.length === 1 ? listRoots[0] : null;
        const readRows = () => listRoot
                ? [...listRoot.querySelectorAll(
                        '.al-table-row-container, tr, [role="row"]'
                )].filter(visible).map((row) => sanitize((row.innerText || '').trim()))
                : [];
        const scan = listRoot
                ? await scanVirtualList(listRoot, readRows)
                : {
                        rows: [],
                        virtual_present: false,
                        virtual_complete: false,
                        scroll_root_count: 0,
                };
        const pagination = paginationState(listRoot || document.body);
        const route = location.hash || '';
        const routeMatch = route === '#/home/conditionStrategy/active'
                || route.startsWith('#/home/conditionStrategy/active?');
        const containers = listRoot
                ? [...listRoot.querySelectorAll('.al-table-row-container')]
                        .filter(visible)
                : [];
        return {
                route,
                route_match: routeMatch,
                list_root_count: listRoots.length,
                container_count: document.querySelectorAll(
                        '.al-table-row-container'
                ).length,
                virtual_list_count: containers.length,
                virtual_scroll: scan.virtual_present,
                virtual_complete: scan.virtual_complete,
                scroll_root_count: scan.scroll_root_count,
                pagination_present: pagination.present,
                pagination_complete: !pagination.present,
                complete_scan: document.readyState === 'complete'
                        && routeMatch
                        && listRoots.length === 1
                        && scan.virtual_complete
                        && !pagination.present,
                rows: scan.rows,
                row_count: scan.rows.length,
                body_text: '',
                stable_keys: {
                        strategy_id: null,
                        task_id: null,
                        order_id: null,
                },
        };
`, {async: true});

function collectScope(scope) {
    return {
        assets: scope === 'assets' || scope === 'all',
        orders: scope === 'orders' || scope === 'all',
        strategies: scope === 'strategies' || scope === 'all',
    };
}

cli({
    site: SITE,
    name: 'reconcile',
    description: 'Read Founder Securities assets, orders, deals and strategy surfaces without writes',
    access: 'read',
    domain: 'quant.foundersc.com',
    strategy: Strategy.UI,
    browser: true,
    siteSession: 'persistent',
    defaultWindowMode: 'foreground',
    navigateBefore: false,
    args: [
        {name: 'scope', default: 'all', help: 'assets, orders, strategies or all'},
        {name: 'expected-environment', default: 'mock', help: 'Expected mock or live environment'},
        {name: 'logical-account-id', default: 'primary', help: 'Caller logical account id'},
    ],
    columns: RECEIPT_COLUMNS,
    func: async (page, kwargs) => {
        const input = parseInput(kwargs);
        const scopes = collectScope(input.scope);
        let state;
        const snapshots = {};
        try {
            await navigate(page, ROUTES.assets);
            state = await readEnvironment(page);
            const gate = environmentGate(state, input.expectedEnvironment);
            if (gate) {
                return asSingleReceipt(baseReceipt(
                    TEMPLATE_NAME,
                    ROUTES.assets,
                    input.expectedEnvironment,
                    state,
                    {
                        status: gate.status,
                        status_reason: gate.reason,
                        logical_account_id: input.logicalAccountId,
                        reconcile_required: gate.reconcile_required,
                        field_readback: {},
                    }
                ));
            }
            if (scopes.assets) snapshots.assets = await page.evaluate(ASSETS_SCRIPT);
            if (scopes.orders) {
                const manualRoute = await page.evaluate(MANUAL_ROUTE_DISCOVERY_SCRIPT);
                snapshots.manual_route_discovery = {
                    route_available: manualRoute?.route_available === true,
                    link_count: Number(manualRoute?.link_count || 0),
                    unique_route_count: Number(manualRoute?.unique_route_count || 0),
                };
                await navigate(page, ROUTES.query);
                snapshots.orders = await page.evaluate(QUERY_SCRIPT);
                if (manualRoute?.route_available === true && manualRoute.route) {
                    await navigate(page, manualRoute.route);
                    snapshots.manual = await page.evaluate(MANUAL_ORDERS_SCRIPT);
                } else {
                    snapshots.manual = {
                        route_available: false,
                        reason: 'manual_entrust_route_not_unique',
                        complete_scan: false,
                        stable_keys: {
                            order_id: null,
                            strategy_id: null,
                            task_id: null,
                        },
                    };
                }
            }
            if (scopes.strategies) {
                await navigate(page, ROUTES.combo);
                snapshots.combo = await page.evaluate(COMBO_SCRIPT);
                await navigate(page, ROUTES.conditionActive);
                snapshots.condition = await page.evaluate(CONDITION_SCRIPT);
            }
            const finalState = await readEnvironment(page);
            if (finalState.environment !== input.expectedEnvironment
                    || finalState.switcher_count !== 1) {
                return asSingleReceipt(baseReceipt(
                    TEMPLATE_NAME,
                    finalState.route || ROUTES.assets,
                    input.expectedEnvironment,
                    finalState,
                    {
                        status: 'unknown',
                        status_reason: 'environment_changed_during_reconcile',
                        logical_account_id: input.logicalAccountId,
                        reconcile_required: true,
                        field_readback: snapshots,
                    }
                ));
            }
            const snapshotValues = Object.values(snapshots).filter((snapshot) => (
                snapshot && Object.prototype.hasOwnProperty.call(snapshot, 'complete_scan')
            ));
            const pageScansComplete = snapshotValues.length > 0
                && snapshotValues.every((snapshot) => snapshot?.complete_scan === true);
            const accountBindingProven = finalState.account_binding === 'proven';
            const reconcileComplete = accountBindingProven && pageScansComplete;
            return asSingleReceipt(baseReceipt(
                TEMPLATE_NAME,
                finalState.route || ROUTES.assets,
                input.expectedEnvironment,
                finalState,
                {
                    status: reconcileComplete ? 'reconciled' : 'reconciled_partial',
                    status_reason: !accountBindingProven
                        ? 'account_fingerprint_not_proven'
                        : reconcileComplete
                            ? 'page_readback_completed'
                            : 'page_readback_incomplete_or_route_unproven',
                    logical_account_id: input.logicalAccountId,
                    reconcile_required: !reconcileComplete,
                    reconcile_complete: reconcileComplete,
                    field_readback: snapshots,
                    locator_proof: {
                        assets_route: scopes.assets ? ROUTES.assets : null,
                        orders_route: scopes.orders ? ROUTES.query : null,
                        manual_entrust_route: scopes.orders
                            ? snapshots.manual_route_discovery
                            : null,
                        combo_route: scopes.strategies ? ROUTES.combo : null,
                        condition_route: scopes.strategies ? ROUTES.conditionActive : null,
                    },
                    capabilities: {
                        submit: false,
                        reconcile: true,
                        account_binding: accountBindingProven,
                        receipt_mapping: false,
                        cancellation: false,
                    },
                }
            ));
        } catch (error) {
            return asSingleReceipt(unknownReceipt(
                TEMPLATE_NAME,
                ROUTES.assets,
                input.expectedEnvironment,
                state,
                'reconcile',
                error,
                {
                    logical_account_id: input.logicalAccountId,
                    field_readback: snapshots,
                }
            ));
        }
    },
});
