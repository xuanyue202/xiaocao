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

const TEMPLATE_NAME = `${SITE}/probe`;

function normalizedInput(kwargs) {
    try {
        return {
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
                        reconcile_required: gate.reconcile_required,
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
            return asSingleReceipt(baseReceipt(
                TEMPLATE_NAME,
                ROUTES.assets,
                input.expectedEnvironment,
                state,
                {
                    status: state.account_binding === 'proven' ? 'ready' : 'unknown',
                    status_reason: state.account_binding === 'proven'
                        ? null
                        : 'account_fingerprint_not_proven',
                    logical_account_id: input.logicalAccountId,
                    reconcile_required: state.account_binding !== 'proven',
                    locator_proof: {
                        environment_container: 'div.switcher___KVAWw',
                        environment_container_count: state.switcher_count,
                        mock_label_matches: state.mock_label_matches,
                        live_label_matches: state.live_label_matches,
                        mock_action_matches: state.mock_action_matches,
                        live_action_matches: state.live_action_matches,
                        expected_environment_readback: true,
                    },
                    capabilities: {
                        submit: false,
                        probe: true,
                        prepare: true,
                        reconcile: true,
                        recover: true,
                        account_binding: state.account_binding === 'proven',
                        receipt_mapping: false,
                        cancellation: false,
                    },
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
