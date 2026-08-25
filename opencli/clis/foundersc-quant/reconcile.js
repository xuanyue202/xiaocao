import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError } from '@jackwener/opencli/errors';
import {
    RECEIPT_COLUMNS,
    ROUTES,
    SITE,
    MANUAL_ROUTE_DISCOVERY_SCRIPT,
    asSingleReceipt,
    baseReceipt,
    carryEnvironmentProof,
    environmentGate,
    navigate,
    normalizeCode,
    normalizeDate,
    normalizeEnvironment,
    normalizeLogicalAccountId,
    normalizeNonNegativeNumber,
    normalizePositiveInteger,
    normalizeSide,
    pageScript,
    readEnvironment,
    unknownReceipt,
} from './common.mjs';

const TEMPLATE_NAME = `${SITE}/reconcile`;

function parseInput(kwargs) {
    try {
        const scope = String(kwargs.scope || 'all').trim();
        if (!['assets', 'orders', 'strategies', 'settlement', 'all'].includes(scope)) {
            throw new Error(
                '--scope must be assets, orders, strategies, settlement or all'
            );
        }
        const rawMatch = {
            code: String(kwargs.code || '').trim(),
            side: String(kwargs.side || '').trim(),
            quantity: String(kwargs.quantity || '').trim(),
            price: String(kwargs.price || '').trim(),
            date: String(kwargs.date || '').trim(),
            orderId: String(kwargs['order-id'] || '').trim(),
        };
        const matchRequested = Object.values(rawMatch).some(Boolean);
        if (matchRequested && (!rawMatch.code || !rawMatch.side
                || !rawMatch.quantity || !rawMatch.price || !rawMatch.date)) {
            throw new Error(
                '--code, --side, --quantity, --price and --date are required together'
            );
        }
        if (rawMatch.orderId
                && !/^[A-Za-z0-9_.:-]{1,64}$/.test(rawMatch.orderId)) {
            throw new Error('--order-id must be a bounded broker identifier');
        }
        const orderMatch = matchRequested ? {
            code: normalizeCode(rawMatch.code),
            side: normalizeSide(rawMatch.side),
            quantity: normalizePositiveInteger(rawMatch.quantity, '--quantity'),
            price: normalizeNonNegativeNumber(rawMatch.price, '--price'),
            date: normalizeDate(rawMatch.date),
            orderId: rawMatch.orderId,
        } : null;
        if (orderMatch && orderMatch.price <= 0) {
            throw new Error('--price must be greater than zero');
        }
        return {
            scope,
            expectedEnvironment: normalizeEnvironment(kwargs['expected-environment'] || 'mock'),
            logicalAccountId: normalizeLogicalAccountId(
                kwargs['logical-account-id'] || 'primary'
            ),
            orderMatch,
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

function queryScript(requestedDate = '', historicalOnly = false) {
    const dateLiteral = JSON.stringify(String(requestedDate || ''));
    const historicalLiteral = historicalOnly ? 'true' : 'false';
    return pageScript(String.raw`
        const targetDate = __XIAOCAO_TARGET_DATE__;
        const historicalOnly = __XIAOCAO_HISTORICAL_ONLY__;
        const readTable = (root, structural = false, emptyRoot = root) => {
                const tables = [...root.querySelectorAll('table')]
                        .filter((table) => structural || visible(table));
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
                        empty_state_count: exactLeaves(emptyRoot, '暂无数据').length,
                };
        };
        let container = document.querySelector('.ma-q-table-container');
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
        const requestedLabels = historicalOnly
                ? ['历史委托', '历史成交']
                : ['当日委托', '当日成交', '历史委托', '历史成交'];
        for (const label of requestedLabels) {
                const matches = exactLeaves(container, label);
                if (matches.length !== 1) {
                        result.tabs[label] = {
                                status: 'not_proven',
                                locator_count: matches.length,
                                complete_scan: false,
                        };
                        continue;
                }
                matches[0].click();
                await waitForPage(300);
                const refreshedContainers = document.querySelectorAll(
                        '.ma-q-table-container'
                );
                if (refreshedContainers.length !== 1) {
                        result.tabs[label] = {
                                status: 'not_proven',
                                locator_count: matches.length,
                                reason: 'account_query_container_changed',
                                complete_scan: false,
                        };
                        continue;
                }
                container = refreshedContainers[0];
                let dateFilter = null;
                if (label.startsWith('历史')) {
                        const dateInputs = [...container.querySelectorAll('input[type="text"]')]
                                .filter(visible)
                                .filter((input) => /^\d{4}-\d{2}-\d{2}$/.test(
                                        String(input.value || '').trim()
                                ));
                        const queryControls = exactLeaves(container, '查询');
                        if (targetDate && dateInputs.length === 2
                                && queryControls.length === 1) {
                                setValue(dateInputs[0], targetDate);
                                setValue(dateInputs[1], targetDate);
                                queryControls[0].click();
                                await waitForPage(1000);
                                const queriedContainers = document.querySelectorAll(
                                        '.ma-q-table-container'
                                );
                                if (queriedContainers.length === 1) {
                                        container = queriedContainers[0];
                                }
                        }
                        dateFilter = {
                                input_count: dateInputs.length,
                                query_control_count: queryControls.length,
                                start: dateInputs.length === 2
                                        ? String(dateInputs[0].value || '').trim() : '',
                                end: dateInputs.length === 2
                                        ? String(dateInputs[1].value || '').trim() : '',
                                applied: dateInputs.length === 2
                                        && queryControls.length === 1
                                        && (!targetDate || (
                                                String(dateInputs[0].value || '').trim()
                                                        === targetDate
                                                && String(dateInputs[1].value || '').trim()
                                                        === targetDate
                                        )),
                        };
                }
                let tableRoot = container;
                let structuralTable = false;
                if (label.startsWith('历史')) {
                        const refreshedDateInputs = [
                                ...container.querySelectorAll('input[type="text"]'),
                        ].filter(visible).filter((input) => /^\d{4}-\d{2}-\d{2}$/
                                .test(String(input.value || '').trim()));
                        const roots = [];
                        for (const input of refreshedDateInputs) {
                                let candidate = input.parentNode;
                                for (let depth = 0; candidate && depth < 5; depth += 1) {
                                        const dates = [
                                                ...candidate.querySelectorAll('input[type="text"]'),
                                        ].filter(visible).filter((node) => /^\d{4}-\d{2}-\d{2}$/
                                                .test(String(node.value || '').trim()));
                                        const queries = exactLeaves(candidate, '查询');
                                        const tables = [...candidate.querySelectorAll('table')]
                                                .filter((table) => tableHeaders(table).length > 0);
                                        if (dates.length === 2 && queries.length === 1
                                                && tables.length === 1) {
                                                roots.push(candidate);
                                                break;
                                        }
                                        candidate = candidate.parentNode;
                                }
                        }
                        const uniqueRoots = [...new Set(roots)];
                        if (uniqueRoots.length === 1) {
                                tableRoot = uniqueRoots[0];
                                structuralTable = true;
                        }
                }
                const scan = await scanTablePages(
                        tableRoot,
                        () => readTable(tableRoot, structuralTable, container)
                );
                const firstPage = scan.pages[0] || {table_count: 0, headers: []};
                const terminalReadback = Number(firstPage.row_count || 0) > 0
                        || firstPage.empty_state_count === 1;
                const filterComplete = !label.startsWith('历史')
                        || dateFilter?.applied === true;
                result.tabs[label] = {
                        status: 'read',
                        locator_count: 1,
                        table: mergeTablePages(scan.pages),
                        table_count: firstPage.table_count,
                        surface_ready: firstPage.table_count === 1
                                && firstPage.headers.length > 0
                                && terminalReadback,
                        empty_state_count: firstPage.empty_state_count,
                        terminal_readback: terminalReadback,
                        date_filter: dateFilter,
                        pagination_present: scan.pagination_present,
                        pagination_complete: scan.pagination_complete,
                        page_count: scan.page_count,
                        complete_scan: firstPage.table_count === 1
                                && firstPage.headers.length > 0
                                && terminalReadback
                                && filterComplete
                                && scan.pagination_complete,
                };
        }
        result.body_text = '';
        const tabResults = Object.values(result.tabs);
        result.complete_scan = result.route_match
                && tabResults.length === requestedLabels.length
                && tabResults.every((tab) => tab.complete_scan === true);
        return result;
`, {async: true})
        .replace('__XIAOCAO_TARGET_DATE__', dateLiteral)
        .replace('__XIAOCAO_HISTORICAL_ONLY__', historicalLiteral);
}

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

const ORDER_HEADERS = Object.freeze({
    code: ['代码/名称', '证券代码', '代码'],
    side: ['买/卖', '买卖方向', '委托方向', '方向'],
    quantity: ['委托量', '委托数量', '数量'],
    price: ['委托价', '委托价格', '价格'],
    status: ['状态', '委托状态'],
    orderId: ['订单编号', '委托编号', '合同编号', '申报编号'],
    filled: ['成交量', '已成量', '成交数量'],
});

const DEAL_HEADERS = Object.freeze({
    orderId: ORDER_HEADERS.orderId,
    code: ORDER_HEADERS.code,
    side: ORDER_HEADERS.side,
    quantity: ['成交量', '成交数量', '数量'],
    price: ['成交价', '成交价格', '价格'],
});

function tableCell(table, row, aliases) {
    const headers = Array.isArray(table?.headers) ? table.headers : [];
    const indexes = headers
        .map((header, index) => aliases.includes(String(header || '').trim()) ? index : -1)
        .filter((index) => index >= 0);
    if (indexes.length !== 1 || !Array.isArray(row)) return null;
    return row[indexes[0]] ?? null;
}

function numericCell(value) {
    const normalized = String(value ?? '')
        .replace(/[\s,，￥¥股元]/g, '')
        .trim();
    if (!/^[-+]?\d+(?:\.\d+)?$/.test(normalized)) return null;
    const number = Number(normalized);
    return Number.isFinite(number) ? number : null;
}

function codeCell(value) {
    const match = /(?:^|\D)(\d{6})(?:\D|$)/.exec(String(value || ''));
    return match ? match[1] : '';
}

function brokerStatus(value) {
    const status = String(value || '').replace(/\s+/g, '');
    if (/全部成交|已成交|已成$|成交$/.test(status)) return 'filled';
    if (/部分成交|部成/.test(status)) return 'partial';
    if (/已撤|部撤|撤单/.test(status)) return 'cancelled';
    if (/拒绝|废单|无效/.test(status)) return 'rejected';
    if (/已报|未成|待报|已提交|已受理|已确认/.test(status)) return 'accepted';
    return 'unknown';
}

function chinaTradeDate() {
    const parts = Object.fromEntries(
        new Intl.DateTimeFormat('en-US', {
            timeZone: 'Asia/Shanghai',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
        }).formatToParts(new Date())
            .filter((part) => ['year', 'month', 'day'].includes(part.type))
            .map((part) => [part.type, part.value])
    );
    return `${parts.year}-${parts.month}-${parts.day}`;
}

function mapExactOrderReceipt(querySnapshot, expected, observedTradeDate) {
    const empty = {
        status: 'unknown',
        statusReason: 'ambiguous_or_missing_exact_order',
        orderId: null,
        exactOrderMatchCount: 0,
        exactDealMatchCount: 0,
        requestedShares: expected?.quantity || null,
        filledShares: 0,
        remainingShares: expected?.quantity || null,
        orderPrice: expected?.price || null,
        fillPrice: null,
        active: null,
        receiptMapping: false,
        absenceProof: false,
    };
    const combinedSnapshot = querySnapshot?.orders
        ? querySnapshot
        : {orders: querySnapshot, assets: null};
    const ordersSnapshot = combinedSnapshot.orders;
    if (expected?.date < observedTradeDate && !expected?.orderId) {
        const orderTab = ordersSnapshot?.tabs?.['历史委托'];
        const dealTab = ordersSnapshot?.tabs?.['历史成交'];
        const orderTable = orderTab?.table;
        const dealTable = dealTab?.table;
        const assets = combinedSnapshot.assets;
        const assetTable = assets?.table;
        const exactFilter = (tab) => tab?.date_filter?.applied === true
            && tab.date_filter.start === expected.date
            && tab.date_filter.end === expected.date;
        const tablesComplete = orderTab?.complete_scan === true
            && dealTab?.complete_scan === true
            && assets?.complete_scan === true
            && exactFilter(orderTab)
            && exactFilter(dealTab)
            && Array.isArray(orderTable?.headers)
            && Array.isArray(orderTable?.rows)
            && Number(orderTable?.row_count) === orderTable.rows.length
            && Array.isArray(dealTable?.headers)
            && Array.isArray(dealTable?.rows)
            && Number(dealTable?.row_count) === dealTable.rows.length
            && Array.isArray(assetTable?.headers)
            && Array.isArray(assetTable?.rows)
            && Number(assetTable?.row_count) === assetTable.rows.length;
        if (!tablesComplete) {
            return {...empty, statusReason: 'prior_day_absence_scan_incomplete'};
        }
        const relatedOrders = orderTable.rows.filter((row) => (
            codeCell(tableCell(orderTable, row, ORDER_HEADERS.code)) === expected.code
            && String(tableCell(orderTable, row, ORDER_HEADERS.side) || '').trim()
                === expected.side
        ));
        const relatedDeals = dealTable.rows.filter((row) => (
            codeCell(tableCell(dealTable, row, DEAL_HEADERS.code)) === expected.code
            && String(tableCell(dealTable, row, DEAL_HEADERS.side) || '').trim()
                === expected.side
        ));
        const codeIndexes = assetTable.headers
            .map((header, index) => String(header || '').trim() === '代码/名称'
                ? index : -1)
            .filter((index) => index >= 0);
        const holdingIndexes = assetTable.headers
            .map((header, index) => String(header || '').trim() === '持仓'
                ? index : -1)
            .filter((index) => index >= 0);
        if (codeIndexes.length !== 1 || holdingIndexes.length !== 1) {
            return {...empty, statusReason: 'prior_day_holding_scan_incomplete'};
        }
        const targetHoldings = [];
        for (const row of assetTable.rows) {
            if (!Array.isArray(row)
                    || row.length <= Math.max(codeIndexes[0], holdingIndexes[0])) {
                return {...empty, statusReason: 'prior_day_holding_scan_incomplete'};
            }
            const observedCode = codeCell(row[codeIndexes[0]]);
            if (!observedCode) {
                return {...empty, statusReason: 'prior_day_holding_scan_incomplete'};
            }
            if (observedCode === expected.code) {
                const shares = numericCell(row[holdingIndexes[0]]);
                if (shares === null || shares < 0) {
                    return {...empty, statusReason: 'prior_day_holding_scan_incomplete'};
                }
                targetHoldings.push(shares);
            }
        }
        const targetHoldingShares = targetHoldings.length === 0
            ? 0
            : targetHoldings.length === 1 ? targetHoldings[0] : null;
        const absenceProof = relatedOrders.length === 0
            && relatedDeals.length === 0
            && targetHoldingShares === 0;
        return {
            ...empty,
            status: absenceProof ? 'not_submitted' : 'unknown',
            statusReason: absenceProof
                ? 'prior_day_broker_absence_proven'
                : 'prior_day_related_activity_or_holding_present',
            exactOrderMatchCount: relatedOrders.length,
            exactDealMatchCount: relatedDeals.length,
            targetHoldingShares,
            active: absenceProof ? false : null,
            absenceProof,
        };
    }
    if (!expected?.orderId) {
        return {...empty, statusReason: 'broker_order_id_required'};
    }
    if (expected.date !== observedTradeDate) {
        return {...empty, statusReason: 'trade_date_not_current'};
    }
    const orderTab = ordersSnapshot?.tabs?.['当日委托'];
    const dealTab = ordersSnapshot?.tabs?.['当日成交'];
    const orderTable = orderTab?.table;
    const dealTable = dealTab?.table;
    if (orderTab?.complete_scan !== true
            || dealTab?.complete_scan !== true
            || !Array.isArray(orderTable?.rows)
            || !Array.isArray(dealTable?.rows)) {
        return empty;
    }
    const exactOrders = orderTable.rows.filter((row) => {
        const observedCode = codeCell(tableCell(orderTable, row, ORDER_HEADERS.code));
        const observedSide = String(
            tableCell(orderTable, row, ORDER_HEADERS.side) || ''
        ).trim();
        const observedQuantity = numericCell(
            tableCell(orderTable, row, ORDER_HEADERS.quantity)
        );
        const observedPrice = numericCell(
            tableCell(orderTable, row, ORDER_HEADERS.price)
        );
        const observedOrderId = String(
            tableCell(orderTable, row, ORDER_HEADERS.orderId) || ''
        ).trim();
        return observedCode === expected.code
            && observedSide === expected.side
            && observedQuantity === expected.quantity
            && observedPrice !== null
            && Math.abs(observedPrice - expected.price) < 0.000001
            && observedOrderId === expected.orderId;
    });
    if (exactOrders.length !== 1) {
        return {...empty, exactOrderMatchCount: exactOrders.length};
    }
    const orderRow = exactOrders[0];
    const orderId = String(
        tableCell(orderTable, orderRow, ORDER_HEADERS.orderId) || ''
    ).trim();
    if (!orderId) {
        return {...empty, exactOrderMatchCount: 1};
    }
    const status = brokerStatus(tableCell(orderTable, orderRow, ORDER_HEADERS.status));
    const exactDeals = dealTable.rows.filter((row) => (
        String(tableCell(dealTable, row, DEAL_HEADERS.orderId) || '').trim() === orderId
    ));
    const dealLegs = exactDeals.map((row) => ({
        quantity: numericCell(tableCell(dealTable, row, DEAL_HEADERS.quantity)),
        price: numericCell(tableCell(dealTable, row, DEAL_HEADERS.price)),
    }));
    const dealLegsComplete = dealLegs.every((leg) => (
        leg.quantity !== null && leg.quantity > 0 && leg.price !== null
    ));
    const dealFilledShares = dealLegsComplete
        ? dealLegs.reduce((total, leg) => total + leg.quantity, 0)
        : null;
    const orderFilledShares = numericCell(
        tableCell(orderTable, orderRow, ORDER_HEADERS.filled)
    );
    const filledShares = dealFilledShares !== null
        ? dealFilledShares
        : orderFilledShares ?? 0;
    const fillPrice = dealLegsComplete && filledShares > 0
        ? dealLegs.reduce((total, leg) => total + leg.quantity * leg.price, 0)
            / filledShares
        : null;
    const fillProofComplete = !['filled', 'partial'].includes(status)
        || (exactDeals.length > 0 && dealLegsComplete && filledShares > 0);
    const mapping = {exactOrderMatchCount: exactOrders.length};
    const receiptMapping = mapping.exactOrderMatchCount === 1
        && status !== 'unknown'
        && fillProofComplete
        && filledShares <= expected.quantity;
    return {
        status: receiptMapping ? status : 'unknown',
        statusReason: receiptMapping
            ? 'exact_account_query_order_mapped'
            : 'order_status_or_fill_mapping_unproven',
        orderId,
        exactOrderMatchCount: 1,
        exactDealMatchCount: exactDeals.length,
        requestedShares: expected.quantity,
        filledShares,
        remainingShares: Math.max(0, expected.quantity - filledShares),
        orderPrice: expected.price,
        fillPrice,
        active: receiptMapping ? ['accepted', 'partial'].includes(status) : null,
        receiptMapping,
    };
}

function collectScope(scope) {
    return {
        assets: scope === 'assets' || scope === 'settlement' || scope === 'all',
        orders: scope === 'orders' || scope === 'settlement' || scope === 'all',
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
        {name: 'code', help: 'Expected six-digit security code'},
        {name: 'side', help: 'Expected buy or sell side'},
        {name: 'quantity', help: 'Expected order quantity'},
        {name: 'price', help: 'Expected numeric limit price'},
        {name: 'date', help: 'Expected trade date in YYYY-MM-DD'},
        {name: 'order-id', help: 'Previously claimed broker order id'},
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
                await navigate(page, ROUTES.query);
                const historicalOnly = Boolean(
                    input.orderMatch
                    && !input.orderMatch.orderId
                    && input.orderMatch.date < chinaTradeDate()
                );
                snapshots.orders = await page.evaluate(queryScript(
                    input.orderMatch?.date || '',
                    historicalOnly,
                ));
                if (!input.orderMatch) {
                    const manualRoute = await page.evaluate(MANUAL_ROUTE_DISCOVERY_SCRIPT);
                    snapshots.manual_route_discovery = {
                        route_available: manualRoute?.route_available === true,
                        link_count: Number(manualRoute?.link_count || 0),
                        unique_route_count: Number(manualRoute?.unique_route_count || 0),
                    };
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
            }
            if (scopes.strategies) {
                await navigate(page, ROUTES.combo);
                snapshots.combo = await page.evaluate(COMBO_SCRIPT);
                await navigate(page, ROUTES.conditionActive);
                snapshots.condition = await page.evaluate(CONDITION_SCRIPT);
            }
            const finalState = carryEnvironmentProof(
                state,
                await readEnvironment(page),
            );
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
            const mapping = mapExactOrderReceipt(
                snapshots,
                input.orderMatch,
                chinaTradeDate(),
            );
            const mappingRequested = input.orderMatch !== null;
            const reconcileComplete = accountBindingProven
                && pageScansComplete
                && (!mappingRequested
                    || mapping.receiptMapping
                    || mapping.absenceProof);
            return asSingleReceipt(baseReceipt(
                TEMPLATE_NAME,
                finalState.route || ROUTES.assets,
                input.expectedEnvironment,
                finalState,
                {
                    status: mappingRequested
                        ? mapping.status
                        : reconcileComplete ? 'reconciled' : 'reconciled_partial',
                    status_reason: !accountBindingProven
                        ? 'account_fingerprint_not_proven'
                        : mappingRequested
                            ? mapping.statusReason
                        : reconcileComplete
                            ? 'page_readback_completed'
                            : 'page_readback_incomplete_or_route_unproven',
                    logical_account_id: input.logicalAccountId,
                    reconcile_required: !reconcileComplete,
                    reconcile_complete: reconcileComplete,
                    absence_proof: mappingRequested ? mapping.absenceProof : false,
                    order_id: mappingRequested ? mapping.orderId : null,
                    requested_shares: mappingRequested ? mapping.requestedShares : null,
                    filled_shares: mappingRequested ? mapping.filledShares : null,
                    remaining_shares: mappingRequested ? mapping.remainingShares : null,
                    order_price: mappingRequested ? mapping.orderPrice : null,
                    fill_price: mappingRequested ? mapping.fillPrice : null,
                    active: mappingRequested ? mapping.active : null,
                    submitted: mapping.absenceProof ? false : null,
                    saved: mapping.absenceProof ? false : null,
                    started: mapping.absenceProof ? false : null,
                    field_readback: snapshots,
                    locator_proof: {
                        assets_route: scopes.assets ? ROUTES.assets : null,
                        orders_route: scopes.orders ? ROUTES.query : null,
                        manual_entrust_route: scopes.orders
                            ? snapshots.manual_route_discovery
                            : null,
                        exact_order_match_count: mappingRequested
                            ? mapping.exactOrderMatchCount
                            : null,
                        exact_deal_match_count: mappingRequested
                            ? mapping.exactDealMatchCount
                            : null,
                        target_holding_shares: mappingRequested
                            ? mapping.targetHoldingShares ?? null
                            : null,
                        historical_order_date_filter: mappingRequested
                            ? snapshots.orders?.tabs?.['历史委托']?.date_filter ?? null
                            : null,
                        historical_deal_date_filter: mappingRequested
                            ? snapshots.orders?.tabs?.['历史成交']?.date_filter ?? null
                            : null,
                        combo_route: scopes.strategies ? ROUTES.combo : null,
                        condition_route: scopes.strategies ? ROUTES.conditionActive : null,
                    },
                    capabilities: {
                        submit: false,
                        reconcile: true,
                        account_binding: accountBindingProven,
                        receipt_mapping: mapping.receiptMapping,
                        absence_proof: mapping.absenceProof,
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
