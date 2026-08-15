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

const TEMPLATE_NAME = `${SITE}/recover`;

const ROUTE_ALIASES = Object.freeze({
  assets: ROUTES.assets,
  orders: ROUTES.query,
  combo: ROUTES.combo,
  condition: ROUTES.conditionActive,
  auction: ROUTES.auction,
  manual: ROUTES.manual,
});

function parseInput(kwargs) {
  try {
    const routeName = String(kwargs.route || 'assets').trim();
    if (!Object.prototype.hasOwnProperty.call(ROUTE_ALIASES, routeName)) {
      throw new Error('--route must be assets, orders, combo, condition, auction or manual');
    }
    return {
      routeName,
      route: ROUTE_ALIASES[routeName],
      expectedEnvironment: normalizeEnvironment(kwargs['expected-environment'] || 'mock'),
      logicalAccountId: normalizeLogicalAccountId(
        kwargs['logical-account-id'] || 'primary'
      ),
    };
  } catch (error) {
    throw new ArgumentError(error.message);
  }
}

function routeReached(routeName, expectedRoute, observedRoute) {
  const observed = String(observedRoute || '').trim();
  if (!observed) return false;
  const variants = [
    observed,
    (() => {
      try {
        return decodeURIComponent(observed);
      } catch (_error) {
        return observed;
      }
    })(),
  ];
  const expectedVariants = [
    expectedRoute,
    (() => {
      try {
        return decodeURIComponent(expectedRoute);
      } catch (_error) {
        return expectedRoute;
      }
    })(),
  ];
  if (routeName === 'manual') {
    return variants.some((value) => value.startsWith(ROUTES.manual));
  }
  return variants.some((value) => expectedVariants.some((expected) => (
    value === expected
      || value.startsWith(`${expected}?`)
      || value.startsWith(`${expected}&`)
  )));
}

const HEALTH_SCRIPT = String.raw`(() => {
  const body = (document.body?.innerText || '').trim();
  const sanitized = body.replace(/\b1\d{10}\b/g, (phone) => (
    phone.slice(0, 3) + '******' + phone.slice(-3)
  ));
  return {
    ready_state: document.readyState,
    body_chars: body.length,
    title: document.title || '',
    route: location.hash || '',
    body_sample: sanitized.slice(0, 1200),
  };
})()`;

cli({
  site: SITE,
  name: 'recover',
  description: 'Recover one safe Founder Securities read-only route and return page health',
  access: 'read',
  domain: 'quant.foundersc.com',
  strategy: Strategy.UI,
  browser: true,
  siteSession: 'persistent',
  defaultWindowMode: 'foreground',
  navigateBefore: false,
  args: [
    {name: 'route', default: 'assets', help: 'assets, orders, combo, condition, auction or manual'},
    {name: 'expected-environment', default: 'mock', help: 'Expected mock or live environment'},
    {name: 'logical-account-id', default: 'primary', help: 'Caller logical account id'},
  ],
  columns: RECEIPT_COLUMNS,
  func: async (page, kwargs) => {
    const input = parseInput(kwargs);
    let state;
    try {
      await navigate(page, input.route);
      state = await readEnvironment(page);
      const gate = environmentGate(state, input.expectedEnvironment);
      if (gate) {
        return asSingleReceipt(baseReceipt(
          TEMPLATE_NAME,
          input.route,
          input.expectedEnvironment,
          state,
          {
            status: gate.status,
            status_reason: gate.reason,
            logical_account_id: input.logicalAccountId,
            reconcile_required: gate.reconcile_required,
          }
        ));
      }
      const health = await page.evaluate(HEALTH_SCRIPT);
      const pageHealthy = health?.ready_state === 'complete'
        && Number(health.body_chars || 0) > 0;
      const route_reached = routeReached(
        input.routeName,
        input.route,
        health?.route || state.route
      );
      const healthy = pageHealthy && route_reached;
      const observedRoute = health?.route || state.route || input.route;
      return asSingleReceipt(baseReceipt(
        TEMPLATE_NAME,
        observedRoute,
        input.expectedEnvironment,
        state,
        {
          status: healthy ? 'recovered' : 'unknown',
          status_reason: !pageHealthy
            ? 'page_shell_not_ready'
            : route_reached
              ? 'safe_route_readback_completed'
              : 'route_not_reached',
          logical_account_id: input.logicalAccountId,
          reconcile_required: !healthy,
          field_readback: {
            health,
            environment: state.environment,
            route_reached,
          },
          locator_proof: {
            environment_container: 'div.switcher___KVAWw',
            environment_container_count: state.switcher_count,
            route_name: input.routeName,
            expected_route: input.route,
            observed_route: observedRoute,
            route_reached,
          },
          capabilities: {
            submit: false,
            recover: healthy,
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
        input.route,
        input.expectedEnvironment,
        state,
        'recover',
        error,
        {logical_account_id: input.logicalAccountId}
      ));
    }
  },
});
