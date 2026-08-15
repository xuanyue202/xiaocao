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
    normalizeAuctionMinute,
    normalizeAuctionSeconds,
    normalizeCode,
    normalizeDate,
    normalizeEnvironment,
    normalizeLogicalAccountId,
    normalizeNonNegativeNumber,
    normalizeParticipation,
    normalizePositiveInteger,
    normalizeSide,
    normalizeTime,
    pageScript,
    readEnvironment,
    unknownReceipt,
} from './common.mjs';

const TEMPLATE_NAME = `${SITE}/prepare`;

function parseInput(kwargs) {
    try {
        const route = String(kwargs.route || 'manual-limit').trim();
        if (!['manual-limit', 'opening-auction', 'timed-order'].includes(route)) {
            throw new Error('--route must be manual-limit, opening-auction or timed-order');
        }
        const input = {
            route,
            expectedEnvironment: normalizeEnvironment(kwargs['expected-environment'] || 'mock'),
            logicalAccountId: normalizeLogicalAccountId(
                kwargs['logical-account-id'] || 'primary'
            ),
            code: normalizeCode(kwargs.code),
            side: normalizeSide(kwargs.side),
            quantity: normalizePositiveInteger(kwargs.quantity, '--quantity'),
            price: normalizeNonNegativeNumber(kwargs.price, '--price'),
        };
        if (input.price <= 0) throw new Error('--price must be greater than zero');
        if (route === 'opening-auction') {
            input.minute = normalizeAuctionMinute(kwargs.minute || 20);
            input.seconds = normalizeAuctionSeconds(kwargs.seconds || 0);
            input.participation = normalizeParticipation(kwargs.participation || 1);
        }
        if (route === 'timed-order') {
            input.date = normalizeDate(kwargs.date);
            input.time = normalizeTime(kwargs.time);
            input.strategyName = String(kwargs['strategy-name'] || 'OpenCLI readback probe').trim();
            if (!input.strategyName || input.strategyName.length > 64) {
                throw new Error('--strategy-name must be 1-64 characters');
            }
        }
        return input;
    } catch (error) {
        throw new ArgumentError(error.message);
    }
}

function manualLimitScript(_input) {
    return pageScript(String.raw`
        const forms = [...document.querySelectorAll('form')].filter(visible);
        const form = forms.length === 1 ? forms[0] : null;
        const codeFields = form
            ? [...form.querySelectorAll('input[placeholder="请输入证券代码"]')]
                .filter(visible)
            : [];
        const priceFields = form
            ? [...form.querySelectorAll('input[placeholder="请输入委托价格"]')]
                .filter(visible)
            : [];
        const quantityFields = form
            ? [...form.querySelectorAll('input[placeholder="请输入委托数量"]')]
                .filter(visible)
            : [];
        const result = {
            route_available: false,
            form_count: forms.length,
            code_field_count: codeFields.length,
            price_field_count: priceFields.length,
            quantity_field_count: quantityFields.length,
            side_buy_matches: exactLeaves(form, '买入').length,
            side_sell_matches: exactLeaves(form, '卖出').length,
            side_selection_safe: false,
            field_readback: {},
            form_cleared_after_readback: false,
        };
        if (forms.length !== 1 || codeFields.length !== 1
                || priceFields.length !== 1 || quantityFields.length !== 1) {
            result.reason = 'manual_limit_form_or_field_not_unique';
            return result;
        }
        // The visible 买入/卖出 controls are the final broker actions in the
        // observed page.  No non-submitting side selector has been proven, so a
        // read-only prepare must fail closed instead of claiming the requested
        // side was selected.
        result.reason = 'manual_limit_side_selection_not_safe_to_probe';
        return result;
    `, {async: true});
}

function openingAuctionScript(input) {
    return pageScript(String.raw`
        const visibleSelects = (root) => [...root.querySelectorAll('select')]
            .filter(visible);
        const selectWithOptions = (root, wanted) => visibleSelects(root).filter((select) => {
            const options = [...select.options].map((option) => (
                (option.textContent || '').trim()
            ));
            return wanted.every((text) => options.includes(text));
        });
        const dataOptions = [...document.querySelectorAll('.pdc-data-option')]
            .filter(visible);
        const scope = dataOptions.length === 1 ? dataOptions[0] : null;
        const addMatches = exactLeaves(scope, '添加证券');
        const dataAreas = [...document.querySelectorAll('.pdc-data')]
            .filter(visible);
        const data = dataAreas.length === 1 ? dataAreas[0] : null;
        if (dataOptions.length !== 1 || addMatches.length !== 1) {
            return {
                route_available: false,
                reason: 'opening_auction_add_security_locator_not_unique',
                data_option_count: dataOptions.length,
                add_matches: addMatches.length,
                field_readback: {},
            };
        }
        if (dataAreas.length !== 1 || !data || !/暂无数据/.test(data.innerText || '')) {
            return {
                route_available: false,
                reason: 'opening_auction_data_area_not_unique_or_not_empty',
                data_area_count: dataAreas.length,
                add_matches: 1,
                field_readback: {},
            };
        }
        addMatches[0].click();
        const modals = [...document.querySelectorAll('.al-modal-container')]
            .filter(visible);
        const modal = modals.length === 1 ? modals[0] : null;
        const result = {
            route_available: false,
            data_option_count: dataOptions.length,
            data_area_count: dataAreas.length,
            modal_count: modals.length,
            code_field_count: 0,
            quantity_field_count: 0,
            participation_field_count: 0,
            field_readback: {},
            form_closed_after_readback: false,
        };
        if (!modal) {
            result.reason = 'opening_auction_security_modal_not_unique';
            return result;
        }
        const form = [...modal.querySelectorAll('form')].filter(visible);
        const codeFields = [...modal.querySelectorAll('input[name="stockCode"]')]
            .filter(visible);
        const quantityFields = [...modal.querySelectorAll(
            'input[placeholder="请输入目标数量"]'
        )].filter(visible);
        const participationFields = [...modal.querySelectorAll(
            'input[name="mPercentage"]'
        )].filter(visible);
        result.form_count = form.length;
        result.code_field_count = codeFields.length;
        result.quantity_field_count = quantityFields.length;
        result.participation_field_count = participationFields.length;
        const cancel = exactLeaves(modal, '取消');
        const close = () => {
            if (cancel.length === 1) cancel[0].click();
            result.form_closed_after_readback = document.querySelectorAll(
                '.al-modal-container'
            ).length === 0;
        };
        if (form.length !== 1 || codeFields.length !== 1
                || quantityFields.length !== 1 || participationFields.length !== 1) {
            result.reason = 'opening_auction_field_not_unique';
            close();
            return result;
        }
        const sideSelects = selectWithOptions(modal, ['买入', '卖出']);
        const minuteSelects = selectWithOptions(modal, ['20', '21', '22', '23', '24']);
        const limitFlagSelects = selectWithOptions(modal, [
            '涨停能卖跌停能买', '涨停不卖跌停不买'
        ]);
        const secondsFields = [
            ...modal.querySelectorAll('input[name="triggerTimeSecond"]'),
            ...modal.querySelectorAll('input[name="seconds"]'),
        ].filter(visible);
        const limitPriceFields = [...modal.querySelectorAll(
            'input[placeholder="默认为0, 表示不限价"]'
        )].filter(visible);
        result.side_select_count = sideSelects.length;
        result.minute_select_count = minuteSelects.length;
        result.limit_flag_select_count = limitFlagSelects.length;
        result.seconds_field_count = secondsFields.length;
        result.limit_price_field_count = limitPriceFields.length;
        if (sideSelects.length !== 1 || minuteSelects.length !== 1
                || limitFlagSelects.length !== 1 || secondsFields.length !== 1
                || limitPriceFields.length !== 1) {
            result.reason = 'opening_auction_execution_field_not_unique';
            close();
            return result;
        }
        const code = codeFields[0];
        const quantity = quantityFields[0];
        const participation = participationFields[0];
        const seconds = secondsFields[0];
        const limitPrice = limitPriceFields[0];
        setValue(code, ${JSON.stringify(input.code)});
        setValue(quantity, ${JSON.stringify(String(input.quantity))});
        setValue(participation, ${JSON.stringify(String(input.participation))});
        setValue(seconds, ${JSON.stringify(String(input.seconds))});
        setValue(limitPrice, ${JSON.stringify(String(input.price))});
        setSelect(sideSelects[0], ${JSON.stringify(input.side)});
        setSelect(minuteSelects[0], ${JSON.stringify(String(input.minute))});
        const fieldReadback = {
            code: code.value,
            side: sideSelects[0].selectedOptions[0]?.textContent?.trim() || '',
            quantity: quantity.value,
            participation: participation.value,
            minute: minuteSelects[0].selectedOptions[0]?.textContent?.trim() || '',
            seconds: seconds.value,
            limit_price: limitPrice.value,
            submitted: false,
            saved: false,
            started: false,
        };
        const numericEqual = (actual, expected) => Number.isFinite(Number(actual))
            && Number(actual) === Number(expected);
        const readbackMismatches = {};
        if (fieldReadback.code !== ${JSON.stringify(input.code)}) {
            readbackMismatches.code = fieldReadback.code;
        }
        if (fieldReadback.side !== ${JSON.stringify(input.side)}) {
            readbackMismatches.side = fieldReadback.side;
        }
        if (!numericEqual(fieldReadback.quantity, ${JSON.stringify(input.quantity)})) {
            readbackMismatches.quantity = fieldReadback.quantity;
        }
        if (!numericEqual(fieldReadback.participation, ${JSON.stringify(input.participation)})) {
            readbackMismatches.participation = fieldReadback.participation;
        }
        if (fieldReadback.minute !== ${JSON.stringify(String(input.minute))}) {
            readbackMismatches.minute = fieldReadback.minute;
        }
        if (!numericEqual(fieldReadback.seconds, ${JSON.stringify(input.seconds)})) {
            readbackMismatches.seconds = fieldReadback.seconds;
        }
        if (!numericEqual(fieldReadback.limit_price, ${JSON.stringify(input.price)})) {
            readbackMismatches.limit_price = fieldReadback.limit_price;
        }
        result.field_readback = fieldReadback;
        result.readback_mismatches = readbackMismatches;
        result.readback_match = Object.keys(readbackMismatches).length === 0;
        result.route_available = result.readback_match;
        if (!result.readback_match) {
            result.reason = 'opening_auction_field_readback_mismatch';
        }
        close();
        return result;
    `, {async: true});
}

function timedOrderScript(input) {
    const [hour, minute] = input.time.split(':').map(Number);
    return pageScript(String.raw`
        const outer = [...document.querySelectorAll('div.new-condition-strategy')]
            .filter(visible);
        const menuRoots = outer.length === 1
            ? [...outer[0].querySelectorAll('.new-condition-strategy-dropDown')]
                    .filter(visible)
            : [];
        const menuMatches = menuRoots.length === 1
            ? exactLeaves(menuRoots[0], '定时单')
            : [];
        if (outer.length !== 1 || menuRoots.length !== 1 || menuMatches.length !== 1) {
            return {
                route_available: false,
                reason: 'timed_order_menu_locator_not_unique',
                strategy_container_count: outer.length,
                menu_count: menuRoots.length,
                timed_order_matches: menuMatches.length,
                field_readback: {},
            };
        }
        menuMatches[0].click();
        const dialogs = [...document.querySelectorAll('[role="dialog"]')]
            .filter(visible);
        const dialog = dialogs.length === 1 ? dialogs[0] : null;
        const result = {
            route_available: false,
            dialog_count: dialogs.length,
            field_readback: {},
            form_closed_after_readback: false,
        };
        if (!dialog) {
            result.reason = 'timed_order_dialog_not_unique';
            return result;
        }
        const uniqueField = (selectors) => {
            const nodes = selectors.flatMap((selector) => (
                [...dialog.querySelectorAll(selector)].filter(visible)
            ));
            return nodes.length === 1 ? nodes[0] : null;
        };
        const taskName = uniqueField(['input[name="taskName"]']);
        const code = uniqueField(['input[name="stockCode"]']);
        const quantity = uniqueField(['input[name="quantity"]']);
        const date = uniqueField([
            'input[name="executeDate"]',
            'input[type="date"]',
        ]);
        const price = uniqueField([
            'input[name="entrustPrice"]',
            'input[name="price"]',
        ]);
        const selects = [...dialog.querySelectorAll('select')].filter(visible);
        const optionSelect = (wanted) => selects.filter((select) => {
            const options = [...select.options].map((option) => (
                (option.textContent || '').trim()
            ));
            return wanted.every((text) => options.includes(text));
        });
        const sideSelects = optionSelect(['买入', '卖出']);
        const hourSelects = optionSelect(['9', '10', '11', '13', '14']);
        let minuteSelects = selects.filter((select) => (
            [...select.options].some((option) => (option.textContent || '').trim() === String(${minute}))
        ));
        const cancel = exactLeaves(dialog, '取消');
        const close = () => {
            if (cancel.length === 1) cancel[0].click();
            result.form_closed_after_readback = document.querySelectorAll(
                '[role="dialog"]'
            ).length === 0;
        };
        result.locator_counts = {
            task_name: taskName ? 1 : 0,
            code: code ? 1 : 0,
            quantity: quantity ? 1 : 0,
            date: date ? 1 : 0,
            price: price ? 1 : 0,
            side_select: sideSelects.length,
            hour_select: hourSelects.length,
            minute_select: minuteSelects.length,
            cancel: cancel.length,
        };
        if (!taskName || !code || !quantity || !date || !price
                || sideSelects.length !== 1 || hourSelects.length !== 1
                || minuteSelects.length !== 1 || cancel.length !== 1) {
            result.reason = 'timed_order_field_not_unique';
            close();
            return result;
        }
        setValue(taskName, ${JSON.stringify(input.strategyName)});
        setValue(code, ${JSON.stringify(input.code)});
        setValue(quantity, ${JSON.stringify(String(input.quantity))});
        setValue(date, ${JSON.stringify(input.date)});
        setValue(price, ${JSON.stringify(String(input.price))});
        setSelect(sideSelects[0], ${JSON.stringify(input.side)});
        setSelect(hourSelects[0], ${JSON.stringify(String(hour))});
        minuteSelects = [...dialog.querySelectorAll('select')].filter(visible)
            .filter((select) => [...select.options].some((option) => (
                (option.textContent || '').trim() === String(${minute})
            )));
        if (minuteSelects.length !== 1) {
            result.reason = 'timed_order_minute_select_changed_or_not_unique';
            close();
            return result;
        }
        setSelect(minuteSelects[0], ${JSON.stringify(String(minute))});
        const fieldReadback = {
            strategy_name: taskName.value,
            code: code.value,
            side: sideSelects[0].selectedOptions[0]?.textContent?.trim() || '',
            price: price.value,
            quantity: quantity.value,
            date: date.value,
            hour: hourSelects[0].value,
            minute: minuteSelects[0].selectedOptions[0]?.textContent?.trim() || '',
            risk_agreement_checked: !!dialog.querySelector(
                'input[type="checkbox"]:checked'
            ),
            submitted: false,
            saved: false,
            started: false,
        };
        const numericEqual = (actual, expected) => Number.isFinite(Number(actual))
            && Number(actual) === Number(expected);
        const readbackMismatches = {};
        if (fieldReadback.strategy_name !== ${JSON.stringify(input.strategyName)}) {
            readbackMismatches.strategy_name = fieldReadback.strategy_name;
        }
        if (fieldReadback.code !== ${JSON.stringify(input.code)}) {
            readbackMismatches.code = fieldReadback.code;
        }
        if (fieldReadback.side !== ${JSON.stringify(input.side)}) {
            readbackMismatches.side = fieldReadback.side;
        }
        if (!numericEqual(fieldReadback.price, ${JSON.stringify(input.price)})) {
            readbackMismatches.price = fieldReadback.price;
        }
        if (!numericEqual(fieldReadback.quantity, ${JSON.stringify(input.quantity)})) {
            readbackMismatches.quantity = fieldReadback.quantity;
        }
        if (fieldReadback.date !== ${JSON.stringify(input.date)}) {
            readbackMismatches.date = fieldReadback.date;
        }
        if (fieldReadback.hour !== ${JSON.stringify(String(hour))}) {
            readbackMismatches.hour = fieldReadback.hour;
        }
        if (fieldReadback.minute !== ${JSON.stringify(String(minute))}) {
            readbackMismatches.minute = fieldReadback.minute;
        }
        result.field_readback = fieldReadback;
        result.readback_mismatches = readbackMismatches;
        result.readback_match = Object.keys(readbackMismatches).length === 0;
        result.route_available = result.readback_match;
        if (!result.readback_match) {
            result.reason = 'timed_order_field_readback_mismatch';
        }
        close();
        return result;
    `, {async: true});
}

function routeDetails(input) {
    if (input.route === 'manual-limit') {
        return {route: ROUTES.manual, script: manualLimitScript(input)};
    }
    if (input.route === 'opening-auction') {
        return {route: ROUTES.auction, script: openingAuctionScript(input)};
    }
    return {
        route: ROUTES.conditionActive,
        script: timedOrderScript(input),
    };
}

cli({
    site: SITE,
    name: 'prepare',
    description: 'Fill and read back one Founder Securities form without saving, starting or submitting it',
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
            default: 'manual-limit',
            help: 'manual-limit, opening-auction or timed-order',
        },
        {name: 'expected-environment', default: 'mock', help: 'Expected mock or live environment'},
        {name: 'logical-account-id', default: 'primary', help: 'Caller logical account id'},
        {name: 'code', required: true, help: 'Six-digit security code'},
        {name: 'side', required: true, help: 'buy or sell; manual-limit is read back but never clicked'},
        {name: 'quantity', required: true, help: 'Positive share quantity'},
        {name: 'price', required: true, help: 'Positive fixed price for safe field readback'},
        {name: 'minute', default: '20', help: 'Opening auction minute 20-24'},
        {name: 'seconds', default: '0', help: 'Opening auction second 0-59'},
        {name: 'participation', default: '1', help: 'Opening auction participation percentage 0-30'},
        {name: 'date', help: 'Timed order date YYYY-MM-DD'},
        {name: 'time', help: 'Timed order time HH:MM'},
        {name: 'strategy-name', help: 'Temporary timed-order name used only before cancellation'},
    ],
    columns: RECEIPT_COLUMNS,
    func: async (page, kwargs) => {
        const input = parseInput(kwargs);
        const details = routeDetails(input);
        let state;
        try {
            await navigate(page, details.route);
            state = await readEnvironment(page);
            const gate = environmentGate(state, input.expectedEnvironment);
            if (gate) {
                return asSingleReceipt(baseReceipt(
                    TEMPLATE_NAME,
                    details.route,
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
            const result = await page.evaluate(details.script);
            if (!result || typeof result !== 'object') {
                throw new Error('prepare form returned a malformed object');
            }
            const readbackPrice = result.field_readback?.price
                ?? result.field_readback?.limit_price;
            const formReadbackProven = result.route_available === true;
            const accountBindingProven = state.account_binding === 'proven';
            const prepareReady = formReadbackProven && accountBindingProven;
            const receipt = baseReceipt(
                TEMPLATE_NAME,
                details.route,
                input.expectedEnvironment,
                state,
                {
                    status: !formReadbackProven
                        ? 'capability_gap'
                        : prepareReady
                            ? 'prepared_readback'
                            : 'unknown',
                    status_reason: result.reason || (!accountBindingProven
                        ? 'account_fingerprint_not_proven'
                        : prepareReady
                            ? 'form_readback_completed_without_submit'
                            : 'required_form_locator_not_proven'),
                    logical_account_id: input.logicalAccountId,
                    requested_shares: result.field_readback?.quantity
                        ? Number(result.field_readback.quantity)
                        : null,
                    order_price: readbackPrice === undefined || readbackPrice === ''
                        ? null
                        : Number(readbackPrice),
                    field_readback: result.field_readback || {},
                    locator_proof: result,
                    reconcile_required: !prepareReady,
                    form_closed: result.form_closed_after_readback === true,
                    ready_for_submit: false,
                    capabilities: {
                        submit: false,
                        prepare: prepareReady,
                        form_readback: formReadbackProven,
                        account_binding: accountBindingProven,
                        receipt_mapping: false,
                        cancellation: false,
                    },
                }
            );
            return asSingleReceipt(receipt);
        } catch (error) {
            return asSingleReceipt(unknownReceipt(
                TEMPLATE_NAME,
                details.route,
                input.expectedEnvironment,
                state,
                'prepare',
                error,
                {logical_account_id: input.logicalAccountId}
            ));
        }
    },
});
