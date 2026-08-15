import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError } from '@jackwener/opencli/errors';
import {
  RECEIPT_COLUMNS,
  ROUTES,
  SITE,
  asSingleReceipt,
  baseReceipt,
  environmentGate,
  navigate,
  normalizeEnvironment,
  normalizeLogicalAccountId,
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

const ASSETS_SCRIPT = String.raw`(() => {
  const visible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const sanitize = (value) => String(value || '')
    .replace(/\b1\d{10}\b/g, (phone) => (
      phone.slice(0, 3) + '******' + phone.slice(-3)
    ));
  const tableSnapshot = (root) => {
    const tables = [...root.querySelectorAll('table')].filter(visible);
    const headers = [...new Set(tables.flatMap((table) => (
      [...table.querySelectorAll('thead th')].map((cell) => (
        (cell.innerText || '').trim()
      )).filter(Boolean)
    )))];
    const rows = tables.flatMap((table) => (
      [...table.querySelectorAll('tbody tr')].filter(visible).map((row) => (
        [...row.querySelectorAll('th,td')].map((cell) => (
          sanitize((cell.innerText || '').trim())
        ))
      ))
    ));
    return {headers, rows, row_count: rows.length};
  };
  const root = document.body;
  const paginationSelectors = [
    '.ant-pagination',
    '.el-pagination',
    '.pagination',
    '[aria-label="下一页"]',
    '[aria-label="Next Page"]',
  ];
  const pagination_present = paginationSelectors.some((selector) => (
    [...root.querySelectorAll(selector)].some(visible)
  ));
  const table = tableSnapshot(root);
  return {
    route: location.hash || '',
    page_ready: document.readyState === 'complete',
    body_text: sanitize((root?.innerText || '').trim()).slice(0, 6000),
    table,
    pagination_present,
    complete_scan: !pagination_present,
    stable_keys: {
      order_id: null,
      strategy_id: null,
      task_id: null,
    },
    freshness: 'page_readback_only',
  };
})()`;

const QUERY_SCRIPT = String.raw`(async () => {
  const visible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const sanitize = (value) => String(value || '')
    .replace(/\b1\d{10}\b/g, (phone) => (
      phone.slice(0, 3) + '******' + phone.slice(-3)
    ));
  const exactLeaves = (root, text) => root
    ? [...root.querySelectorAll('*')].filter((node) => (
        node.children.length === 0 && visible(node)
        && (node.textContent || '').trim() === text
      ))
    : [];
  const readTable = (root) => {
    const tables = [...root.querySelectorAll('table')].filter(visible);
    const headers = [...new Set(tables.flatMap((table) => (
      [...table.querySelectorAll('thead th')].map((cell) => (
        (cell.innerText || '').trim()
      )).filter(Boolean)
    )))];
    const rows = tables.flatMap((table) => (
      [...table.querySelectorAll('tbody tr')].filter(visible).map((row) => (
        [...row.querySelectorAll('th,td')].map((cell) => (
          sanitize((cell.innerText || '').trim())
        ))
      ))
    ));
    return {headers, rows, row_count: rows.length};
  };
  const paginationSelectors = [
    '.ant-pagination',
    '.el-pagination',
    '.pagination',
    '[aria-label="下一页"]',
    '[aria-label="Next Page"]',
  ];
  const paginationPresent = (root) => paginationSelectors.some((selector) => (
    [...root.querySelectorAll(selector)].some(visible)
  ));
  const container = document.querySelector('.ma-q-table-container');
  const result = {
    route: location.hash || '',
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
      };
      continue;
    }
    matches[0].click();
    await new Promise((resolve) => setTimeout(resolve, 100));
    result.tabs[label] = {
      status: 'read',
      locator_count: 1,
      table: readTable(container),
      pagination_present: paginationPresent(container),
    };
  }
  result.body_text = sanitize((container.innerText || '').trim()).slice(0, 6000);
  const tabResults = Object.values(result.tabs);
  result.complete_scan = tabResults.length === 4
    && tabResults.every((tab) => (
      tab.status === 'read' && tab.pagination_present === false
    ));
  return result;
})()`;

const MANUAL_ROUTE_DISCOVERY_SCRIPT = String.raw`(() => {
  const visible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const routes = [...document.querySelectorAll('a[href]')]
    .filter(visible)
    .map((link) => {
      try {
        const url = new URL(link.getAttribute('href'), location.href);
        if (url.origin !== location.origin || url.pathname !== location.pathname) {
          return null;
        }
        const hash = url.hash || '';
        return /^#\/home\/orderByHand\/[^/]+\/entrustDetail(?:[/?]|$)/.test(hash)
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
})()`;

const MANUAL_ORDERS_SCRIPT = String.raw`(() => {
  const visible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const sanitize = (value) => String(value || '')
    .replace(/\b1\d{10}\b/g, (phone) => (
      phone.slice(0, 3) + '******' + phone.slice(-3)
    ));
  const exactLeaves = (root, text) => root
    ? [...root.querySelectorAll('*')].filter((node) => (
        node.children.length === 0 && visible(node)
        && (node.textContent || '').trim() === text
      ))
    : [];
  const tables = [...document.querySelectorAll('table')].filter(visible);
  const relevantTables = tables.filter((table) => (
    /代码|委托|成交|状态/.test(table.innerText || '')
  ));
  const readTable = (table) => {
    if (!table) return {headers: [], rows: [], row_count: 0};
    const headers = [...table.querySelectorAll('thead th')]
      .map((cell) => (cell.innerText || '').trim()).filter(Boolean);
    const rows = [...table.querySelectorAll('tbody tr')]
      .filter(visible)
      .map((row) => [...row.querySelectorAll('th,td')]
        .map((cell) => sanitize((cell.innerText || '').trim())));
    return {headers, rows, row_count: rows.length};
  };
  const paginationSelectors = [
    '.ant-pagination',
    '.el-pagination',
    '.pagination',
    '[aria-label="下一页"]',
    '[aria-label="Next Page"]',
  ];
  const pagination_present = paginationSelectors.some((selector) => (
    [...document.querySelectorAll(selector)].some(visible)
  ));
  const withdrawControls = [...document.querySelectorAll('a.gs-tab-withdraw')]
    .filter(visible);
  const tabs = {};
  for (const label of ['当日委托', '当日成交', '历史委托', '历史成交']) {
    const matches = exactLeaves(document.body, label);
    tabs[label] = {locator_count: matches.length, status: matches.length === 1 ? 'read' : 'not_proven'};
  }
  return {
    route: location.hash || '',
    table_count: tables.length,
    relevant_table_count: relevantTables.length,
    table: relevantTables.length === 1 ? readTable(relevantTables[0]) : null,
    tabs,
    withdraw_control_count: withdrawControls.length,
    withdraw_control_present: withdrawControls.length === 1,
    can_withdraw: null,
    pagination_present,
    complete_scan: relevantTables.length === 1 && !pagination_present,
    body_text: sanitize((document.body?.innerText || '').trim()).slice(0, 6000),
    stable_keys: {
      order_id: null,
      strategy_id: null,
      task_id: null,
    },
  };
})()`;

const COMBO_SCRIPT = String.raw`(() => {
  const visible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const sanitize = (value) => String(value || '')
    .replace(/\b1\d{10}\b/g, (phone) => (
      phone.slice(0, 3) + '******' + phone.slice(-3)
    ));
  const body = sanitize((document.body?.innerText || '').trim());
  const dataBody = document.querySelector('pd-data-body');
  const paginationSelectors = [
    '.ant-pagination',
    '.el-pagination',
    '.pagination',
    '[aria-label="下一页"]',
    '[aria-label="Next Page"]',
  ];
  const pagination_present = paginationSelectors.some((selector) => (
    [...document.querySelectorAll(selector)].some(visible)
  ));
  const virtual_scroll = !!dataBody
    && ['auto', 'scroll'].includes(getComputedStyle(dataBody).overflowY);
  const rows = dataBody
    ? [...dataBody.querySelectorAll('tr,[role="row"],.al-table-row')]
        .filter(visible).map((row) => sanitize((row.innerText || '').trim()))
    : [];
  return {
    route: location.hash || '',
    list_container_count: document.querySelectorAll('pd-data-body').length,
    virtual_scroll,
    pagination_present,
    complete_scan: document.querySelectorAll('pd-data-body').length === 1
      && !virtual_scroll && !pagination_present,
    rows,
    row_count: rows.length,
    body_text: body.slice(0, 6000),
    stable_keys: {
      strategy_id: null,
      task_id: null,
      order_id: null,
    },
  };
})()`;

const CONDITION_SCRIPT = String.raw`(() => {
  const visible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const sanitize = (value) => String(value || '')
    .replace(/\b1\d{10}\b/g, (phone) => (
      phone.slice(0, 3) + '******' + phone.slice(-3)
    ));
  const containers = [...document.querySelectorAll('.al-table-row-container')]
    .filter(visible);
  const container_count = document.querySelectorAll(
    '.al-table-row-container'
  ).length;
  const paginationSelectors = [
    '.ant-pagination',
    '.el-pagination',
    '.pagination',
    '[aria-label="下一页"]',
    '[aria-label="Next Page"]',
  ];
  const pagination_present = paginationSelectors.some((selector) => (
    [...document.querySelectorAll(selector)].some(visible)
  ));
  const virtual_scroll = containers.length > 0;
  const rows = containers.flatMap((container) => (
    [...container.children].filter(visible).map((row) => (
      sanitize((row.innerText || '').trim())
    ))
  ));
  return {
    route: location.hash || '',
    container_count,
    virtual_list_count: containers.length,
    virtual_scroll,
    pagination_present,
    complete_scan: container_count === 1
      && containers.length === 1
      && !virtual_scroll && !pagination_present,
    rows,
    row_count: rows.length,
    body_text: sanitize((document.body?.innerText || '').trim()).slice(0, 6000),
    stable_keys: {
      strategy_id: null,
      task_id: null,
      order_id: null,
    },
  };
})()`;

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
      const reconcileComplete = snapshotValues.length > 0
        && snapshotValues.every((snapshot) => snapshot?.complete_scan === true);
      return asSingleReceipt(baseReceipt(
        TEMPLATE_NAME,
        finalState.route || ROUTES.assets,
        input.expectedEnvironment,
        finalState,
        {
          status: reconcileComplete ? 'reconciled' : 'reconciled_partial',
          status_reason: reconcileComplete
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
            account_binding: false,
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
