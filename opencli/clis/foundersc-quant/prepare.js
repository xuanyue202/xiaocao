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
    navigateFresh,
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
const PREPARE_TARGET_ATTRIBUTE = 'data-opencli-foundersc-prepare-target';
const PREPARE_WAIT_SCRIPT = pageScript(String.raw`
    await waitForPage(100);
    return true;
`, {async: true});

function timedOrderTriggerScript() {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(PREPARE_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const outer = [...document.querySelectorAll('div.new-condition-strategy')]
            .filter(visible);
        const triggers = outer.length === 1
            ? [...outer[0].querySelectorAll('.new-condition-strategy-title')]
                    .filter(visible)
            : [];
        if (outer.length === 1 && triggers.length === 1) {
            triggers[0].setAttribute(attribute, 'timed-trigger');
        }
        return {
            route_available: outer.length === 1 && triggers.length === 1,
            reason: outer.length === 1 && triggers.length === 1
                ? null
                : 'timed_order_trigger_locator_not_unique',
            strategy_container_count: outer.length,
            strategy_trigger_count: triggers.length,
        };
    `, {async: true});
}

function timedOrderMenuScript() {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(PREPARE_TARGET_ATTRIBUTE)};
        let menuRoots = [];
        let menuMatches = [];
        const outer = [...document.querySelectorAll('div.new-condition-strategy')]
            .filter(visible);
        for (let attempt = 0; attempt < 20 && outer.length === 1; attempt += 1) {
            await waitForPage(100);
            menuRoots = [
                ...outer[0].querySelectorAll('.new-condition-strategy-dropDown'),
            ].filter(visible);
            menuMatches = menuRoots.length === 1
                ? exactLeaves(menuRoots[0], '定时单')
                : [];
            if (menuRoots.length === 1 && menuMatches.length === 1) break;
        }
        if (menuRoots.length === 1 && menuMatches.length === 1) {
            menuMatches[0].setAttribute(attribute, 'timed-menu');
        }
        return {
            route_available: outer.length === 1
                && menuRoots.length === 1 && menuMatches.length === 1,
            reason: outer.length === 1
                    && menuRoots.length === 1 && menuMatches.length === 1
                ? null
                : 'timed_order_menu_locator_not_unique',
            strategy_container_count: outer.length,
            menu_count: menuRoots.length,
            timed_order_matches: menuMatches.length,
        };
    `, {async: true});
}

function timedOrderDateStepScript(targetDate) {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(PREPARE_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const dialogs = [...document.querySelectorAll('[role="dialog"]')]
            .filter(visible);
        const dateFields = dialogs.length === 1
            ? [...dialogs[0].querySelectorAll('input.al-modal-date-input')]
                    .filter(visible)
            : [];
        if (dialogs.length !== 1 || dateFields.length !== 1) {
            return {
                route_available: false,
                reason: 'timed_order_date_field_not_unique',
                dialog_count: dialogs.length,
                date_field_count: dateFields.length,
            };
        }
        const date = dateFields[0];
        const targetDate = ${JSON.stringify(targetDate)};
        if (date.value === targetDate) {
            return {
                route_available: true,
                reason: null,
                date_selected: true,
                action: 'complete',
            };
        }
        const datePickers = [...document.querySelectorAll('.ui-datepicker')]
            .filter(visible);
        if (datePickers.length === 0) {
            date.setAttribute(attribute, 'timed-date-open');
            return {
                route_available: true,
                reason: null,
                date_selected: false,
                action: 'timed-date-open',
            };
        }
        if (datePickers.length !== 1) {
            return {
                route_available: false,
                reason: 'timed_order_datepicker_not_unique',
                datepicker_count: datePickers.length,
            };
        }
        const [targetYear, targetMonth, targetDay] = targetDate
            .split('-').map(Number);
        const monthNames = [
            '一月', '二月', '三月', '四月', '五月', '六月',
            '七月', '八月', '九月', '十月', '十一月', '十二月',
        ];
        const datePicker = datePickers[0];
        const years = [...datePicker.querySelectorAll('.ui-datepicker-year')]
            .filter(visible);
        const months = [...datePicker.querySelectorAll('.ui-datepicker-month')]
            .filter(visible);
        const year = years.length === 1
            ? Number((years[0].textContent || '').trim())
            : 0;
        const month = months.length === 1
            ? monthNames.indexOf((months[0].textContent || '').trim()) + 1
            : 0;
        if (!year || !month) {
            return {
                route_available: false,
                reason: 'timed_order_datepicker_month_not_readable',
                year_count: years.length,
                month_count: months.length,
            };
        }
        const current = year * 12 + month;
        const target = targetYear * 12 + targetMonth;
        if (current !== target) {
            const selector = current < target
                ? '.ui-datepicker-next'
                : '.ui-datepicker-prev';
            const controls = [...datePicker.querySelectorAll(selector)]
                .filter(visible).filter((node) => !disabled(node));
            if (controls.length !== 1) {
                return {
                    route_available: false,
                    reason: 'timed_order_datepicker_navigation_not_unique',
                    navigation_count: controls.length,
                    observed_year: year,
                    observed_month: month,
                };
            }
            const action = current < target ? 'timed-date-next' : 'timed-date-prev';
            controls[0].setAttribute(attribute, action);
            return {
                route_available: true,
                reason: null,
                date_selected: false,
                action,
            };
        }
        const dayMatches = [...datePicker.querySelectorAll('a.ui-state-default')]
            .filter(visible).filter((node) => (
                (node.textContent || '').trim() === String(targetDay)
            ));
        if (dayMatches.length !== 1) {
            return {
                route_available: false,
                reason: 'timed_order_date_not_unique_or_not_selectable',
                date_matches: dayMatches.length,
            };
        }
        dayMatches[0].setAttribute(attribute, 'timed-date-day');
        return {
            route_available: true,
            reason: null,
            date_selected: false,
            action: 'timed-date-day',
        };
    `, {async: true});
}

async function openTimedOrderDialog(page, input) {
    const trigger = await page.evaluate(timedOrderTriggerScript());
    if (trigger?.route_available !== true) return trigger;
    await page.click(`[${PREPARE_TARGET_ATTRIBUTE}="timed-trigger"]`);
    const menu = await page.evaluate(timedOrderMenuScript());
    if (menu?.route_available !== true) return {...trigger, ...menu};
    await page.click(`[${PREPARE_TARGET_ATTRIBUTE}="timed-menu"]`);
    const trustedClicks = ['timed-trigger', 'timed-menu'];
    let dateStep = null;
    for (let attempt = 0; attempt < 27; attempt += 1) {
        dateStep = await page.evaluate(timedOrderDateStepScript(input.date));
        if (dateStep?.route_available !== true) {
            return {...trigger, ...menu, ...dateStep, trusted_clicks: trustedClicks};
        }
        if (dateStep.date_selected === true) break;
        await page.click(
            `[${PREPARE_TARGET_ATTRIBUTE}="${dateStep.action}"]`
        );
        trustedClicks.push(dateStep.action);
    }
    if (dateStep?.date_selected !== true) {
        return {
            ...trigger,
            ...menu,
            route_available: false,
            reason: 'timed_order_date_not_selected_within_bound',
            trusted_clicks: trustedClicks,
        };
    }
    return {
        route_available: true,
        reason: null,
        trusted_clicks: trustedClicks,
        date_selected: true,
        ...trigger,
        ...menu,
    };
}

function openingAuctionAddSecurityScript() {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(PREPARE_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const dataOptions = [...document.querySelectorAll('.pdc-data-option')]
            .filter(visible);
        const scope = dataOptions.length === 1 ? dataOptions[0] : null;
        const addMatches = exactLeaves(scope, '添加证券');
        const dataAreas = [...document.querySelectorAll('.pdc-data')]
            .filter(visible);
        const data = dataAreas.length === 1 ? dataAreas[0] : null;
        const dataEmpty = dataAreas.length === 1
            && !!data && /暂无数据/.test(data.innerText || '');
        if (dataOptions.length === 1 && addMatches.length === 1 && dataEmpty) {
            addMatches[0].setAttribute(attribute, 'opening-auction-add-security');
        }
        return {
            route_available: dataOptions.length === 1
                && addMatches.length === 1 && dataEmpty,
            reason: dataOptions.length !== 1 || addMatches.length !== 1
                ? 'opening_auction_add_security_locator_not_unique'
                : !dataEmpty
                    ? 'opening_auction_data_area_not_unique_or_not_empty'
                    : null,
            data_option_count: dataOptions.length,
            data_area_count: dataAreas.length,
            add_matches: addMatches.length,
            data_empty: dataEmpty,
        };
    `, {async: true});
}

async function openOpeningAuctionSecurityDialog(page) {
    const target = await page.evaluate(openingAuctionAddSecurityScript());
    if (target?.route_available !== true) return target;
    await page.click(
        `[${PREPARE_TARGET_ATTRIBUTE}="opening-auction-add-security"]`
    );
    return {
        ...target,
        trusted_clicks: ['opening-auction-add-security'],
    };
}

function openingAuctionCancelScript() {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(PREPARE_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const modals = [...document.querySelectorAll('.al-modal-container')]
            .filter(visible);
        if (modals.length === 0) {
            return {
                route_available: true,
                reason: null,
                form_closed: true,
                modal_count: 0,
                cancel_count: 0,
            };
        }
        const cancel = modals.length === 1
            ? exactLeaves(modals[0], '取消')
            : [];
        if (modals.length === 1 && cancel.length === 1) {
            cancel[0].setAttribute(attribute, 'opening-auction-cancel');
        }
        return {
            route_available: modals.length === 1 && cancel.length === 1,
            reason: modals.length === 1 && cancel.length === 1
                ? null
                : 'opening_auction_cancel_not_unique',
            form_closed: false,
            modal_count: modals.length,
            cancel_count: cancel.length,
        };
    `, {async: true});
}

async function closeOpeningAuctionSecurityDialog(page) {
    let proof = await page.evaluate(openingAuctionCancelScript());
    if (proof?.form_closed === true) return proof;
    if (proof?.route_available !== true) return proof;
    await page.click(
        `[${PREPARE_TARGET_ATTRIBUTE}="opening-auction-cancel"]`
    );
    for (let attempt = 0; attempt < 20; attempt += 1) {
        await page.evaluate(PREPARE_WAIT_SCRIPT);
        proof = await page.evaluate(openingAuctionCancelScript());
        if (proof?.form_closed === true) break;
    }
    return proof;
}

function packageLimitAddSecurityScript() {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(PREPARE_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const dataOptions = [...document.querySelectorAll('.pdc-data-option')]
            .filter(visible);
        const scope = dataOptions.length === 1 ? dataOptions[0] : null;
        const addMatches = exactLeaves(scope, '添加证券');
        const dataAreas = [...document.querySelectorAll('.pdc-data')]
            .filter(visible);
        const dataEmpty = dataAreas.length === 1
            && /暂无数据/.test(dataAreas[0].innerText || '');
        if (dataOptions.length === 1 && addMatches.length === 1 && dataEmpty) {
            addMatches[0].setAttribute(attribute, 'package-limit-add-security');
        }
        return {
            route_available: dataOptions.length === 1
                && addMatches.length === 1 && dataEmpty,
            reason: dataOptions.length !== 1 || addMatches.length !== 1
                ? 'package_limit_add_security_locator_not_unique'
                : !dataEmpty
                    ? 'package_limit_page_not_empty'
                    : null,
            data_option_count: dataOptions.length,
            data_area_count: dataAreas.length,
            add_matches: addMatches.length,
            page_empty_before_readback: dataEmpty,
        };
    `, {async: true});
}

async function openPackageLimitSecurityDialog(page) {
    const target = await page.evaluate(packageLimitAddSecurityScript());
    if (target?.route_available !== true) return target;
    await page.click(
        `[${PREPARE_TARGET_ATTRIBUTE}="package-limit-add-security"]`
    );
    return {
        ...target,
        trusted_clicks: ['package-limit-add-security'],
    };
}

function packageLimitCancelScript() {
    return pageScript(String.raw`
        const attribute = ${JSON.stringify(PREPARE_TARGET_ATTRIBUTE)};
        for (const node of document.querySelectorAll('[' + attribute + ']')) {
            node.removeAttribute(attribute);
        }
        const modals = [...document.querySelectorAll('.al-modal-container')]
            .filter(visible);
        const dataAreas = [...document.querySelectorAll('.pdc-data')]
            .filter(visible);
        const pageCleared = dataAreas.length === 1
            && /暂无数据/.test(dataAreas[0].innerText || '');
        if (modals.length === 0) {
            return {
                route_available: pageCleared,
                reason: pageCleared ? null : 'package_limit_page_not_cleared',
                form_closed: true,
                page_cleared_after_readback: pageCleared,
                modal_count: 0,
                cancel_count: 0,
            };
        }
        const cancel = modals.length === 1
            ? [...modals[0].querySelectorAll('.al-modal-cancel-button')]
                .filter(visible).filter((node) => (
                    (node.textContent || '').trim() === '取消'
                ))
            : [];
        if (modals.length === 1 && cancel.length === 1) {
            cancel[0].setAttribute(attribute, 'package-limit-cancel');
        }
        return {
            route_available: modals.length === 1 && cancel.length === 1,
            reason: modals.length === 1 && cancel.length === 1
                ? null
                : 'package_limit_cancel_locator_not_unique',
            form_closed: false,
            page_cleared_after_readback: false,
            modal_count: modals.length,
            cancel_count: cancel.length,
        };
    `, {async: true});
}

async function closePackageLimitSecurityDialog(page) {
    let proof = await page.evaluate(packageLimitCancelScript());
    if (proof?.form_closed === true) return proof;
    if (proof?.route_available !== true) return proof;
    await page.click(
        `[${PREPARE_TARGET_ATTRIBUTE}="package-limit-cancel"]`
    );
    for (let attempt = 0; attempt < 20; attempt += 1) {
        await page.evaluate(PREPARE_WAIT_SCRIPT);
        proof = await page.evaluate(packageLimitCancelScript());
        if (proof?.form_closed === true) break;
    }
    return proof;
}

function parseInput(kwargs) {
    try {
        const route = String(kwargs.route || 'manual-limit').trim();
        if (![
            'manual-limit',
            'opening-auction',
            'package-limit',
            'timed-order',
        ].includes(route)) {
            throw new Error(
                '--route must be manual-limit, opening-auction, package-limit or timed-order'
            );
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

function packageLimitScript(input) {
    return pageScript(String.raw`
        let modals = [];
        for (let attempt = 0; attempt < 20; attempt += 1) {
            await waitForPage(100);
            modals = [...document.querySelectorAll('.al-modal-container')]
                .filter(visible);
            if (modals.length === 1) break;
        }
        const modal = modals.length === 1 ? modals[0] : null;
        const result = {
            route_available: false,
            modal_count: modals.length,
            field_readback: {},
            form_closed_after_readback: false,
            page_cleared_after_readback: false,
        };
        if (!modal || exactLeaves(modal, '添加证券').length !== 1) {
            result.reason = 'package_limit_security_modal_not_unique';
            return result;
        }
        const forms = [...modal.querySelectorAll('form')].filter(visible);
        const codeFields = [...modal.querySelectorAll(
            'input[name="stockCode"]'
        )].filter(visible);
        const sideFields = [...modal.querySelectorAll(
            'select#delegateDirection'
        )].filter(visible);
        const priceModeFields = [...modal.querySelectorAll(
            'select#priceMode'
        )].filter(visible);
        const priceFields = [...modal.querySelectorAll(
            'input#basicPrice[name="basicPrice"]'
        )].filter(visible);
        const quantityFields = [...modal.querySelectorAll(
            'input#quantity[name="quantity"]'
        )].filter(visible);
        const confirmButtons = [...modal.querySelectorAll(
            '.al-modal-positive-button'
        )].filter(visible).filter((node) => (
            (node.textContent || '').trim() === '确定'
        ));
        const cancelButtons = [...modal.querySelectorAll(
            '.al-modal-cancel-button'
        )].filter(visible).filter((node) => (
            (node.textContent || '').trim() === '取消'
        ));
        result.form_count = forms.length;
        result.code_field_count = codeFields.length;
        result.side_field_count = sideFields.length;
        result.price_mode_field_count = priceModeFields.length;
        result.price_field_count = priceFields.length;
        result.quantity_field_count = quantityFields.length;
        result.confirm_button_count = confirmButtons.length;
        result.cancel_button_count = cancelButtons.length;
        if (forms.length !== 1 || codeFields.length !== 1
                || sideFields.length !== 1 || priceModeFields.length !== 1
                || priceFields.length !== 1 || quantityFields.length !== 1
                || confirmButtons.length !== 1 || cancelButtons.length !== 1) {
            result.reason = 'package_limit_field_not_unique';
            return result;
        }
        const selectExactText = (select, wanted) => {
            const matches = [...select.options].filter((option) => (
                (option.textContent || '').trim() === wanted
            ));
            if (matches.length !== 1) return false;
            setSelect(select, matches[0].value);
            return true;
        };
        const code = codeFields[0];
        setValue(code, ${JSON.stringify(input.code)});
        await waitForPage(1000);
        const stableSide = [...modal.querySelectorAll(
            'select#delegateDirection'
        )].filter(visible);
        const stableMode = [...modal.querySelectorAll(
            'select#priceMode'
        )].filter(visible);
        if (stableSide.length !== 1 || stableMode.length !== 1) {
            result.reason = 'package_limit_field_not_stable';
            return result;
        }
        if (!selectExactText(stableSide[0], ${JSON.stringify(input.side)})) {
            result.reason = 'package_limit_side_option_not_unique';
            return result;
        }
        if (!selectExactText(stableMode[0], '指定价格')) {
            result.reason = 'package_limit_price_mode_not_unique';
            return result;
        }
        await waitForPage(200);
        const stablePrice = [...modal.querySelectorAll(
            'input#basicPrice[name="basicPrice"]'
        )].filter(visible);
        const stableQuantity = [...modal.querySelectorAll(
            'input#quantity[name="quantity"]'
        )].filter(visible);
        if (stablePrice.length !== 1 || stableQuantity.length !== 1) {
            result.reason = 'package_limit_field_not_stable';
            return result;
        }
        setValue(stablePrice[0], ${JSON.stringify(String(input.price))});
        setValue(stableQuantity[0], ${JSON.stringify(String(input.quantity))});
        await waitForPage(200);
        const readCode = [...modal.querySelectorAll('input[name="stockCode"]')]
            .filter(visible);
        const readSide = [...modal.querySelectorAll('select#delegateDirection')]
            .filter(visible);
        const readMode = [...modal.querySelectorAll('select#priceMode')]
            .filter(visible);
        const readPrice = [...modal.querySelectorAll(
            'input#basicPrice[name="basicPrice"]'
        )].filter(visible);
        const readQuantity = [...modal.querySelectorAll(
            'input#quantity[name="quantity"]'
        )].filter(visible);
        if ([readCode, readSide, readMode, readPrice, readQuantity]
                .some((nodes) => nodes.length !== 1)) {
            result.reason = 'package_limit_field_not_stable';
            return result;
        }
        const fieldReadback = {
            code: readCode[0].value,
            side: readSide[0].selectedOptions[0]?.textContent?.trim() || '',
            price_mode:
                readMode[0].selectedOptions[0]?.textContent?.trim() || '',
            price: readPrice[0].value,
            quantity: readQuantity[0].value,
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
        if (fieldReadback.price_mode !== '指定价格') {
            readbackMismatches.price_mode = fieldReadback.price_mode;
        }
        if (!numericEqual(fieldReadback.price, ${JSON.stringify(input.price)})) {
            readbackMismatches.price = fieldReadback.price;
        }
        if (!numericEqual(
            fieldReadback.quantity,
            ${JSON.stringify(input.quantity)}
        )) {
            readbackMismatches.quantity = fieldReadback.quantity;
        }
        result.field_readback = fieldReadback;
        result.readback_mismatches = readbackMismatches;
        result.readback_match = Object.keys(readbackMismatches).length === 0;
        result.route_available = result.readback_match;
        if (!result.readback_match) {
            result.reason = 'package_limit_field_readback_mismatch';
        }
        return result;
    `, {async: true});
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

function openingAuctionScript(input, {dialogAlreadyOpen = false} = {}) {
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
        const dataAreas = [...document.querySelectorAll('.pdc-data')]
            .filter(visible);
        if (!${JSON.stringify(dialogAlreadyOpen)}) {
            return {
                route_available: false,
                reason: 'opening_auction_trusted_dialog_open_required',
                field_readback: {},
            };
        }
        let modals = [];
        for (let attempt = 0; attempt < 20; attempt += 1) {
            await waitForPage(100);
            modals = [...document.querySelectorAll('.al-modal-container')]
                .filter(visible);
            if (modals.length === 1) break;
        }
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
            'input[name="max_percentage"], input[name="mPercentage"]'
        )].filter(visible);
        result.form_count = form.length;
        result.code_field_count = codeFields.length;
        result.quantity_field_count = quantityFields.length;
        result.participation_field_count = participationFields.length;
        const cancel = exactLeaves(modal, '取消');
        const close = () => {
            result.form_closed_after_readback = false;
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
        const secondsFields = [...modal.querySelectorAll(
            'input[name="triggerTimeSecond"], input[name="seconds"], '
            + 'input[ng-model="vm.triggerTimeSecond"]'
        )].filter(visible);
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
        const setSelectText = (select, wanted) => {
            const matches = [...select.options].filter((option) => (
                (option.textContent || '').trim() === String(wanted)
            ));
            if (matches.length !== 1) return false;
            select.value = matches[0].value;
            select.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        };
        if (!setSelectText(sideSelects[0], ${JSON.stringify(input.side)})) {
            result.reason = 'opening_auction_side_option_not_unique';
            close();
            return result;
        }
        if (!setSelectText(minuteSelects[0], ${JSON.stringify(String(input.minute))})) {
            result.reason = 'opening_auction_minute_option_not_unique';
            close();
            return result;
        }
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

function timedOrderScript(input, {dialogAlreadyOpen = false} = {}) {
    const [hour, minute] = input.time.split(':').map(Number);
    return pageScript(String.raw`
        if (!${JSON.stringify(dialogAlreadyOpen)}) {
            return {
                route_available: false,
                reason: 'timed_order_trusted_dialog_open_required',
                field_readback: {},
            };
        }
        let dialogs = [];
        for (let attempt = 0; attempt < 20; attempt += 1) {
            await waitForPage(100);
            dialogs = [...document.querySelectorAll('[role="dialog"]')]
                .filter(visible);
            if (dialogs.length === 1) break;
        }
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
        const inputRows = [...dialog.querySelectorAll('.al-modal-input-row')]
            .filter(visible);
        const rowByLabel = (label) => inputRows.filter((row) => (
            exactLeaves(row, label).filter((node) => node.tagName === 'LABEL')
                .length === 1
        ));
        const directionRows = rowByLabel('委托方向:');
        const priceRows = rowByLabel('委托价格:');
        const visibleInputs = (row) => row
            ? [...row.querySelectorAll('input')].filter(visible)
            : [];
        const directionFields = directionRows.length === 1
            ? visibleInputs(directionRows[0])
            : [];
        const priceFields = priceRows.length === 1
            ? visibleInputs(priceRows[0])
            : [];
        const taskName = uniqueField(['input[name="taskName"]']);
        const code = uniqueField(['input[name="stockCode"]']);
        const quantity = uniqueField(['input[name="quantity"]']);
        const date = uniqueField(['input.al-modal-date-input']);
        const direction = directionFields.length === 1 ? directionFields[0] : null;
        const price = priceFields.length === 1 ? priceFields[0] : null;
        const selects = [...dialog.querySelectorAll('select')].filter(visible);
        const optionSelect = (wanted) => selects.filter((select) => {
            const options = [...select.options].map((option) => (
                (option.textContent || '').trim()
            ));
            return wanted.every((text) => options.includes(text));
        });
        const hourSelects = optionSelect(['9', '10', '11', '13', '14']);
        const cancel = exactLeaves(dialog, '取消');
        const close = async () => {
            if (cancel.length === 1) cancel[0].click();
            for (let attempt = 0; attempt < 20; attempt += 1) {
                await waitForPage(100);
                const remainingDialogs = [
                    ...document.querySelectorAll('[role="dialog"]'),
                ].filter(visible);
                if (remainingDialogs.length === 0) break;
            }
            result.form_closed_after_readback = [
                ...document.querySelectorAll('[role="dialog"]'),
            ].filter(visible).length === 0;
        };
        result.locator_counts = {
            task_name: taskName ? 1 : 0,
            code: code ? 1 : 0,
            quantity: quantity ? 1 : 0,
            date: date ? 1 : 0,
            price: price ? 1 : 0,
            direction_row: directionRows.length,
            direction_input: directionFields.length,
            price_row: priceRows.length,
            price_input: priceFields.length,
            hour_select: hourSelects.length,
            native_select: selects.length,
            cancel: cancel.length,
        };
        if (!taskName || !code || !quantity || !date || !price
                || !direction || hourSelects.length !== 1
                || selects.length !== 2 || cancel.length !== 1) {
            result.reason = 'timed_order_field_not_unique';
            await close();
            return result;
        }
        setValue(taskName, ${JSON.stringify(input.strategyName)});
        setValue(code, ${JSON.stringify(input.code)});
        setValue(quantity, ${JSON.stringify(String(input.quantity))});
        direction.click();
        let sideMatches = [];
        for (let attempt = 0; attempt < 20; attempt += 1) {
            await waitForPage(100);
            sideMatches = exactLeaves(document.body, ${JSON.stringify(input.side)})
                .filter((node) => node.tagName === 'LI');
            if (sideMatches.length === 1) break;
        }
        if (sideMatches.length !== 1) {
            result.reason = 'timed_order_side_option_not_unique';
            result.locator_counts.side_option = sideMatches.length;
            await close();
            return result;
        }
        sideMatches[0].click();
        await waitForPage(100);
        if (direction.value !== ${JSON.stringify(input.side)}) {
            result.reason = 'timed_order_side_readback_mismatch';
            await close();
            return result;
        }
        price.click();
        const knownPriceTypes = [
            '现价', '买一', '买二', '买三', '买四', '买五',
            '卖一', '卖二', '卖三', '卖四', '卖五',
            '涨停价', '跌停价', '开盘价', '昨收价', '最高价', '最低价',
        ];
        let availablePriceTypes = [];
        let numericPriceMatches = [];
        for (let attempt = 0; attempt < 20; attempt += 1) {
            await waitForPage(100);
            availablePriceTypes = knownPriceTypes.filter((text) => (
                exactLeaves(document.body, text)
                    .filter((node) => node.tagName === 'LI').length === 1
            ));
            numericPriceMatches = exactLeaves(
                document.body,
                ${JSON.stringify(String(input.price))}
            ).filter((node) => node.tagName === 'LI');
            if (availablePriceTypes.length > 0 || numericPriceMatches.length > 0) {
                break;
            }
        }
        result.locator_counts.price_type_options = availablePriceTypes.length;
        result.locator_counts.numeric_price_options = numericPriceMatches.length;
        if (numericPriceMatches.length !== 1) {
            result.reason = 'timed_order_numeric_limit_not_supported';
            result.field_readback = {
                available_price_types: availablePriceTypes,
                requested_limit_price: ${JSON.stringify(String(input.price))},
                submitted: false,
                saved: false,
                started: false,
            };
            await close();
            return result;
        }
        numericPriceMatches[0].click();
        await waitForPage(100);
        if (price.value !== ${JSON.stringify(String(input.price))}) {
            result.reason = 'timed_order_price_readback_mismatch';
            await close();
            return result;
        }
        if (date.value !== ${JSON.stringify(input.date)}) {
            result.reason = 'timed_order_date_readback_mismatch';
            await close();
            return result;
        }
        const setSelectText = (select, wanted) => {
            const matches = [...select.options].filter((option) => (
                (option.textContent || '').trim() === String(wanted)
            ));
            if (matches.length !== 1) return false;
            select.value = matches[0].value;
            select.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        };
        if (!setSelectText(hourSelects[0], ${JSON.stringify(String(hour))})) {
            result.reason = 'timed_order_hour_option_not_unique';
            await close();
            return result;
        }
        let minuteSelects = [];
        for (let attempt = 0; attempt < 20; attempt += 1) {
            await waitForPage(100);
            minuteSelects = [...dialog.querySelectorAll('select')].filter(visible)
                .filter((select) => [...select.options].some((option) => (
                    (option.textContent || '').trim() === String(${minute})
                )));
            if (minuteSelects.length === 1) break;
        }
        if (minuteSelects.length !== 1) {
            result.reason = 'timed_order_minute_select_changed_or_not_unique';
            await close();
            return result;
        }
        if (!setSelectText(minuteSelects[0], ${JSON.stringify(String(minute))})) {
            result.reason = 'timed_order_minute_option_not_unique';
            await close();
            return result;
        }
        const fieldReadback = {
            strategy_name: taskName.value,
            code: code.value,
            side: direction.value,
            price: price.value,
            price_semantics: 'numeric_limit',
            numeric_price_option_count: numericPriceMatches.length,
            quantity: quantity.value,
            date: date.value,
            hour: hourSelects[0].selectedOptions[0]?.textContent?.trim() || '',
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
        await close();
        return result;
    `, {async: true});
}

function routeDetails(input) {
    if (input.route === 'manual-limit') {
        return {route: ROUTES.manual, script: manualLimitScript(input)};
    }
    if (input.route === 'opening-auction') {
        return {
            route: ROUTES.auction,
            script: openingAuctionScript(input, {dialogAlreadyOpen: true}),
        };
    }
    if (input.route === 'package-limit') {
        return {
            route: ROUTES.packageCreate,
            script: packageLimitScript(input),
        };
    }
    return {
        route: ROUTES.conditionActive,
        script: timedOrderScript(input, {dialogAlreadyOpen: true}),
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
            help: 'manual-limit, opening-auction, package-limit or timed-order',
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
            await navigateFresh(page, ROUTES.assets);
            const preflightState = await readEnvironment(page);
            const preflightGate = environmentGate(
                preflightState,
                input.expectedEnvironment
            );
            if (preflightGate) {
                return asSingleReceipt(baseReceipt(
                    TEMPLATE_NAME,
                    details.route,
                    input.expectedEnvironment,
                    preflightState,
                    {
                        status: preflightGate.status,
                        status_reason: preflightGate.reason,
                        logical_account_id: input.logicalAccountId,
                        reconcile_required: preflightGate.reconcile_required,
                        field_readback: {},
                        locator_proof: {
                            environment_preflight_route: ROUTES.assets,
                            environment_proof_complete:
                                preflightState.environment_proof_complete === true,
                            environment_data_namespace:
                                preflightState.environment_data_namespace || 'unknown',
                        },
                    }
                ));
            }
            await navigate(page, details.route);
            const routeState = await readEnvironment(page);
            state = carryEnvironmentProof(preflightState, routeState);
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
            let trustedInteraction = null;
            if (input.route === 'opening-auction') {
                trustedInteraction = await openOpeningAuctionSecurityDialog(page);
            } else if (input.route === 'package-limit') {
                trustedInteraction = await openPackageLimitSecurityDialog(page);
            } else if (input.route === 'timed-order') {
                trustedInteraction = await openTimedOrderDialog(page, input);
            }
            if (trustedInteraction && trustedInteraction.route_available !== true) {
                return asSingleReceipt(baseReceipt(
                    TEMPLATE_NAME,
                    details.route,
                    input.expectedEnvironment,
                    state,
                    {
                        status: 'capability_gap',
                        status_reason: trustedInteraction?.reason
                            || 'trusted_prepare_dialog_open_failed',
                        logical_account_id: input.logicalAccountId,
                        field_readback: {},
                        locator_proof: trustedInteraction || {},
                        reconcile_required: true,
                        form_closed: false,
                        ready_for_submit: false,
                    }
                ));
            }
            let result;
            let postInteraction = null;
            try {
                result = await page.evaluate(details.script);
            } finally {
                if (input.route === 'opening-auction') {
                    try {
                        postInteraction = await closeOpeningAuctionSecurityDialog(page);
                    } catch (closeError) {
                        postInteraction = {
                            route_available: false,
                            form_closed: false,
                            reason: `opening_auction_close_failed:${closeError.name || 'Error'}`,
                        };
                    }
                } else if (input.route === 'package-limit') {
                    try {
                        postInteraction = await closePackageLimitSecurityDialog(page);
                    } catch (closeError) {
                        postInteraction = {
                            route_available: false,
                            form_closed: false,
                            page_cleared_after_readback: false,
                            reason: `package_limit_close_failed:${closeError.name || 'Error'}`,
                        };
                    }
                }
            }
            if (!result || typeof result !== 'object') {
                throw new Error('prepare form returned a malformed object');
            }
            if (input.route === 'opening-auction') {
                result.form_closed_after_readback = postInteraction?.form_closed === true;
                result.close_proof = postInteraction || {};
                if (!result.form_closed_after_readback) {
                    result.route_available = false;
                    result.reason = result.reason || 'opening_auction_form_not_closed';
                }
            } else if (input.route === 'package-limit') {
                result.form_closed_after_readback = postInteraction?.form_closed === true;
                result.page_cleared_after_readback =
                    postInteraction?.page_cleared_after_readback === true;
                result.close_proof = postInteraction || {};
                if (!result.form_closed_after_readback) {
                    result.route_available = false;
                    result.reason = result.reason || 'package_limit_form_not_closed';
                } else if (!result.page_cleared_after_readback) {
                    result.route_available = false;
                    result.reason = result.reason || 'package_limit_page_not_cleared';
                }
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
                    locator_proof: trustedInteraction
                        ? {...trustedInteraction, form: result}
                        : result,
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
