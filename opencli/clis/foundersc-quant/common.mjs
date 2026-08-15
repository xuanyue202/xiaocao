export const TEMPLATE_VERSION = 1;
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
    ? accountMatches[0].slice(0, 3) + '******' + accountMatches[0].slice(-3)
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
    account_binding: 'not_proven',
    logical_account_id: null,
  };
})()`;

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
  await page.goto(url, {waitUntil: 'load', settleMs: 1000});
  await page.wait({time: 1});
  return url;
}

export async function readEnvironment(page) {
  const state = await page.evaluate(ENVIRONMENT_SCRIPT);
  if (!state || typeof state !== 'object') {
    throw new Error('environment probe returned a malformed object');
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
  return [receipt];
}
