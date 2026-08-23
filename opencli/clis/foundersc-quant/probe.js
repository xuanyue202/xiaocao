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
    normalizeEnvironment,
    normalizeLogicalAccountId,
    pageScript,
    readEnvironment,
    unknownReceipt,
} from './common.mjs';

const TEMPLATE_NAME = `${SITE}/probe`;

const PACKAGE_ROUTE_SCRIPT = pageScript(String.raw`
    const route = location.hash || '';
    const options = [...document.querySelectorAll('.pdc-data-option')]
        .filter(visible);
    const add = options.length === 1
        ? exactLeaves(options[0], '添加证券')
        : [];
    const data = [...document.querySelectorAll('.pdc-data')].filter(visible);
    const empty = data.length === 1 && /暂无数据/.test(data[0].innerText || '');
    return {
        route_match: route === '#/home/packageDeal/create?type=security',
        option_container_count: options.length,
        add_security_count: add.length,
        data_container_count: data.length,
        page_empty: empty,
        unique_dom_proven: options.length === 1
            && add.length === 1
            && data.length === 1
            && empty,
    };
`, {async: true});

function normalizeProbeRoute(value) {
    const route = String(value || '').trim();
    if (![
        'package-limit',
        'manual-limit',
        'opening-auction',
        'timed-order',
    ].includes(route)) {
        throw new Error(
            '--route must be package-limit, manual-limit, opening-auction or timed-order'
        );
    }
    return route;
}

function normalizedInput(kwargs) {
    try {
        return {
            route: normalizeProbeRoute(kwargs.route || 'package-limit'),
            expectedEnvironment: normalizeEnvironment(kwargs['expected-environment'] || 'mock'),
            logicalAccountId: normalizeLogicalAccountId(
                kwargs['logical-account-id'] || 'primary'
            ),
        };
    } catch (error) {
        throw new ArgumentError(error.message);
    }
}

cli({
    site: SITE,
    name: 'probe',
    description: 'Read the Founder Securities session, environment and account binding capability',
    access: 'read',
    domain: 'quant.foundersc.com',
    strategy: Strategy.UI,
    browser: true,
    siteSession: 'persistent',
    defaultWindowMode: 'foreground',
    navigateBefore: false,
    args: [
        {
            name: 'route',
            default: 'package-limit',
            help: 'Route capability to probe; defaults to the only submit-capable route',
        },
        {
            name: 'expected-environment',
            default: 'mock',
            help: 'Expected page environment: mock or live; no environment switch is performed',
        },
        {
            name: 'logical-account-id',
            default: 'primary',
            help: 'Caller logical account id; the page binding is independently read back',
        },
    ],
    columns: RECEIPT_COLUMNS,
    func: async (page, kwargs) => {
        const input = normalizedInput(kwargs);
        const packageLimit = input.route === 'package-limit';
        let state;
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
                        submit_capability: false,
                        reconcile_required: gate.reconcile_required,
                        capabilities: {
                            submit: false,
                            receipt_mapping: false,
                            submit_route: null,
                        },
                        locator_proof: {
                            environment_container: 'div.switcher___KVAWw',
                            environment_container_count: state.switcher_count,
                            mock_label_matches: state.mock_label_matches,
                            live_label_matches: state.live_label_matches,
                            expected_environment_readback: false,
                        },
                        field_readback: {
                            environment: state.environment,
                            login_account_fingerprint: state.login_account_fingerprint || null,
                            route: state.route,
                        },
                    }
                ));
            }
            let packageRoute = null;
            if (packageLimit) {
                const assetsState = state;
                await navigate(page, ROUTES.packageCreate);
                state = carryEnvironmentProof(
                    assetsState,
                    await readEnvironment(page),
                );
                const packageGate = environmentGate(
                    state,
                    input.expectedEnvironment,
                );
                if (packageGate) {
                    return asSingleReceipt(baseReceipt(
                        TEMPLATE_NAME,
                        ROUTES.packageCreate,
                        input.expectedEnvironment,
                        state,
                        {
                            status: packageGate.status,
                            status_reason: packageGate.reason,
                            logical_account_id: input.logicalAccountId,
                            submit_capability: false,
                            reconcile_required: packageGate.reconcile_required,
                            capabilities: {
                                submit: false,
                                receipt_mapping: false,
                                submit_route: null,
                            },
                        }
                    ));
                }
                packageRoute = await page.evaluate(PACKAGE_ROUTE_SCRIPT);
            }
            const routeProven = !packageLimit
                || packageRoute?.unique_dom_proven === true;
            const bindingProven = state.fund_account_match_count === 1
                && /^\d{3}\*{6}\d{3}$/.test(
                    String(state.fund_account_fingerprint || '')
                );
            const ready = bindingProven && routeProven;
            return asSingleReceipt(baseReceipt(
                TEMPLATE_NAME,
                packageLimit ? ROUTES.packageCreate : ROUTES.assets,
                input.expectedEnvironment,
                state,
                {
                    status: ready ? 'ready' : 'unknown',
                    status_reason: !bindingProven
                        ? 'account_fingerprint_not_proven'
                        : !routeProven
                            ? 'package_submit_route_not_proven'
                            : null,
                    logical_account_id: input.logicalAccountId,
                    reconcile_required: !ready,
                    locator_proof: {
                        environment_container: 'div.switcher___KVAWw',
                        environment_container_count: state.switcher_count,
                        mock_label_matches: state.mock_label_matches,
                        live_label_matches: state.live_label_matches,
                        mock_action_matches: state.mock_action_matches,
                        live_action_matches: state.live_action_matches,
                        expected_environment_readback: true,
                        package_route: packageRoute,
                    },
                    capabilities: {
                        submit: packageLimit && routeProven,
                        probe: true,
                        prepare: true,
                        reconcile: true,
                        recover: true,
                        account_binding: bindingProven,
                        receipt_mapping: false,
                        submit_route: packageLimit && routeProven
                            ? 'package-limit'
                            : null,
                        cancellation: false,
                    },
                    submit_capability: packageLimit && routeProven,
                    field_readback: {
                        environment: state.environment,
                        login_account_fingerprint: state.login_account_fingerprint || null,
                        route: state.route,
                    },
                }
            ));
        } catch (error) {
            return asSingleReceipt(unknownReceipt(
                TEMPLATE_NAME,
                ROUTES.assets,
                input.expectedEnvironment,
                state,
                'probe',
                error,
                {logical_account_id: input.logicalAccountId}
            ));
        }
    },
});
