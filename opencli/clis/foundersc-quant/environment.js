import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError } from '@jackwener/opencli/errors';
import {
    RECEIPT_COLUMNS,
    ROUTES,
    SITE,
    asSingleReceipt,
    baseReceipt,
    navigate,
    normalizeEnvironment,
    normalizeLogicalAccountId,
    pageScript,
    readEnvironment,
    unknownReceipt,
} from './common.mjs';

const TEMPLATE_NAME = `${SITE}/environment`;
const TARGET_ATTRIBUTE = 'data-opencli-foundersc-environment-target';

function parseInput(kwargs) {
    try {
        const expectedCurrentRaw = String(kwargs['expected-current'] || 'any')
            .trim().toLowerCase();
        return {
            target: normalizeEnvironment(kwargs.target),
            expectedCurrent: expectedCurrentRaw === 'any'
                ? null
                : normalizeEnvironment(expectedCurrentRaw),
            logicalAccountId: normalizeLogicalAccountId(
                kwargs['logical-account-id'] || 'primary'
            ),
        };
    } catch (error) {
        throw new ArgumentError(error.message);
    }
}

function switchTargetScript(target) {
    const actionText = target === 'live'
        ? '点击切换至实盘'
        : '点击切换至模拟盘';
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const switchers = [...document.querySelectorAll('div.switcher___KVAWw')]
            .filter(visible);
        const switcher = switchers.length === 1 ? switchers[0] : null;
        const actions = exactLeaves(switcher, ${JSON.stringify(actionText)});
        if (switcher && actions.length === 1) {
            actions[0].setAttribute(attribute, 'switch-environment');
        }
        return {
            route_available: switchers.length === 1 && actions.length === 1,
            reason: switchers.length === 1 && actions.length === 1
                ? null
                : 'environment_switch_control_not_unique',
            environment_container_count: switchers.length,
            switch_action_count: actions.length,
            target_environment: ${JSON.stringify(target)},
        };
    `, {async: true});
}

const WAIT_SCRIPT = pageScript(String.raw`
    await waitForPage(100);
    return true;
`, {async: true});

function receipt(state, input, overrides = {}) {
    return asSingleReceipt(baseReceipt(
        TEMPLATE_NAME,
        state.route || ROUTES.assets,
        input.target,
        state,
        {
            logical_account_id: input.logicalAccountId,
            submitted: false,
            saved: false,
            started: false,
            cancelled: false,
            submit_capability: false,
            ready_for_submit: false,
            ...overrides,
        }
    ));
}

cli({
    site: SITE,
    name: 'environment',
    description: 'Switch the Founder mock/live environment and verify exact readback without trading',
    access: 'write',
    domain: 'quant.foundersc.com',
    strategy: Strategy.UI,
    browser: true,
    siteSession: 'persistent',
    defaultWindowMode: 'foreground',
    navigateBefore: false,
    args: [
        {name: 'target', required: true, help: 'Target mock or live environment'},
        {name: 'expected-current', default: 'any', help: 'Expected current mock/live or any'},
        {name: 'logical-account-id', default: 'primary', help: 'Caller logical account id'},
    ],
    columns: RECEIPT_COLUMNS,
    func: async (page, kwargs) => {
        const input = parseInput(kwargs);
        let state;
        try {
            await navigate(page, ROUTES.assets);
            state = await readEnvironment(page);
            if (state.auth_state !== 'authenticated' || state.environment === 'unknown') {
                return receipt(state, input, {
                    status: state.auth_state === 'login_required'
                        ? 'auth_required'
                        : 'unknown',
                    status_reason: state.auth_state === 'login_required'
                        ? 'foundersc_login_required'
                        : 'environment_not_uniquely_identified',
                    field_readback: {
                        from_environment: state.environment,
                        to_environment: state.environment,
                        changed: false,
                    },
                    reconcile_required: true,
                    locator_proof: {},
                    capabilities: {submit: false, environment_switch: false},
                });
            }
            if (input.expectedCurrent && state.environment !== input.expectedCurrent) {
                return receipt(state, input, {
                    status: 'environment_mismatch',
                    status_reason: 'current_environment_does_not_match_expected_current',
                    field_readback: {
                        from_environment: state.environment,
                        to_environment: state.environment,
                        changed: false,
                    },
                    reconcile_required: true,
                    locator_proof: {
                        expected_current: input.expectedCurrent,
                        observed_current: state.environment,
                    },
                    capabilities: {submit: false, environment_switch: false},
                });
            }
            const fromEnvironment = state.environment;
            if (fromEnvironment === input.target) {
                return receipt(state, input, {
                    status: 'environment_ready',
                    status_reason: 'already_in_target_environment',
                    field_readback: {
                        from_environment: fromEnvironment,
                        to_environment: state.environment,
                        changed: false,
                    },
                    reconcile_required: state.account_binding !== 'proven',
                    locator_proof: {switch_action_count: 0, readback_match: true},
                    capabilities: {submit: false, environment_switch: true},
                });
            }
            const target = await page.evaluate(switchTargetScript(input.target));
            if (target?.route_available !== true) {
                return receipt(state, input, {
                    status: 'capability_gap',
                    status_reason: target?.reason || 'environment_switch_control_not_unique',
                    field_readback: {
                        from_environment: fromEnvironment,
                        to_environment: state.environment,
                        changed: false,
                    },
                    reconcile_required: true,
                    locator_proof: target || {},
                    capabilities: {submit: false, environment_switch: false},
                });
            }
            await page.click(`[${TARGET_ATTRIBUTE}="switch-environment"]`);
            let finalState = state;
            for (let attempt = 0; attempt < 30; attempt += 1) {
                await page.evaluate(WAIT_SCRIPT);
                finalState = await readEnvironment(page);
                if (finalState.environment === input.target) break;
            }
            const readbackMatch = finalState.environment === input.target;
            return receipt(finalState, input, {
                status: readbackMatch ? 'environment_switched' : 'unknown',
                status_reason: readbackMatch
                    ? 'environment_switch_readback_completed'
                    : 'environment_switch_readback_mismatch',
                field_readback: {
                    from_environment: fromEnvironment,
                    to_environment: finalState.environment,
                    changed: readbackMatch,
                },
                reconcile_required: true,
                locator_proof: {...target, readback_match: readbackMatch},
                capabilities: {
                    submit: false,
                    environment_switch: readbackMatch,
                },
            });
        } catch (error) {
            return asSingleReceipt(unknownReceipt(
                TEMPLATE_NAME,
                ROUTES.assets,
                input.target,
                state,
                error,
                {
                    logical_account_id: input.logicalAccountId,
                    field_readback: {},
                    capabilities: {submit: false, environment_switch: false},
                }
            ));
        }
    },
});
