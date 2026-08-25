from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
TEMPLATE_ROOT = ROOT / "opencli" / "clis" / "foundersc-quant"
NODE_CANDIDATES = (
    shutil.which("node"),
    "/Users/xuanyue202/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
)


def _node() -> str:
    for candidate in NODE_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    pytest.skip("node is required for browser-script contract tests")


def _assets_body() -> str:
    source = (TEMPLATE_ROOT / "reconcile.js").read_text(encoding="utf-8")
    match = re.search(
        r"const ASSETS_SCRIPT = pageScript\(String\.raw`(?P<body>.*?)`, "
        r"\{async: true\}\);",
        source,
        flags=re.DOTALL,
    )
    assert match, "ASSETS_SCRIPT body must remain directly executable in the browser"
    return match.group("body")


def _order_mapping_source() -> str:
    source = (TEMPLATE_ROOT / "reconcile.js").read_text(encoding="utf-8")
    start = source.index("const ORDER_HEADERS")
    end = source.index("function collectScope", start)
    return source[start:end]


def test_exact_order_mapping_accepts_one_stable_order_and_rejects_duplicates():
    node_script = r"""
const mapping = new Function(
    `${MAPPING_SOURCE}; return mapExactOrderReceipt;`,
)();
const orderTable = {
    headers: ['代码/名称', '订单编号', '买/卖', '委托量', '委托价', '状态'],
    rows: [['510300 300ETF', 'order-123', '买入', '100', '4.22', '全部成交']],
};
const dealTable = {
    headers: ['订单编号', '成交量', '成交价'],
    rows: [['order-123', '40', '4.21'], ['order-123', '60', '4.22']],
};
const snapshot = {
    tabs: {
        '当日委托': {complete_scan: true, table: orderTable},
        '当日成交': {complete_scan: true, table: dealTable},
    },
};
const expected = {
    code: '510300', side: '买入', quantity: 100, price: 4.22,
    date: '2026-08-24', orderId: 'order-123',
};
const exact = mapping(snapshot, expected, '2026-08-24');
const duplicate = mapping({
    tabs: {
        '当日委托': {
            complete_scan: true,
            table: {...orderTable, rows: [...orderTable.rows, ...orderTable.rows]},
        },
        '当日成交': {complete_scan: true, table: dealTable},
    },
}, expected, '2026-08-24');
const missingOrderId = mapping(
    snapshot,
    {...expected, orderId: ''},
    '2026-08-24',
);
const wrongDate = mapping(snapshot, expected, '2026-08-25');
console.log(JSON.stringify({exact, duplicate, missingOrderId, wrongDate}));
""".replace("MAPPING_SOURCE", json.dumps(_order_mapping_source()))
    completed = subprocess.run(
        [_node(), "--input-type=module", "--eval", node_script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["exact"]["receiptMapping"] is True
    assert payload["exact"]["status"] == "filled"
    assert payload["exact"]["filledShares"] == 100
    assert payload["exact"]["fillPrice"] == pytest.approx(4.216)
    assert payload["duplicate"]["receiptMapping"] is False
    assert payload["duplicate"]["exactOrderMatchCount"] == 2
    assert payload["missingOrderId"]["receiptMapping"] is False
    assert payload["missingOrderId"]["statusReason"] == "broker_order_id_required"
    assert payload["wrongDate"]["receiptMapping"] is False
    assert payload["wrongDate"]["statusReason"] == "trade_date_not_current"


def test_prior_day_absence_requires_exact_history_filters_and_zero_holding():
    node_script = r"""
const mapping = new Function(
    `${MAPPING_SOURCE}; return mapExactOrderReceipt;`,
)();
const emptyOrders = {
    complete_scan: true,
    date_filter: {
        start: '2026-08-24', end: '2026-08-24', applied: true,
    },
    table: {
        headers: ['时间', '代码/名称', '买/卖', '委托量', '委托价', '状态'],
        row_count: 0,
        rows: [],
    },
};
const emptyDeals = {
    complete_scan: true,
    date_filter: {
        start: '2026-08-24', end: '2026-08-24', applied: true,
    },
    table: {
        headers: ['时间', '代码/名称', '买/卖', '成交量', '成交价', '成交金额'],
        row_count: 0,
        rows: [],
    },
};
const emptyAssets = {
    complete_scan: true,
    table: {
        headers: ['代码/名称', '持仓'],
        row_count: 1,
        rows: [['515120 创新药ETF广发', '65100']],
    },
};
const expected = {
    code: '603801', side: '买入', quantity: 800, price: 6.62,
    date: '2026-08-24', orderId: '',
};
const snapshot = {
    assets: emptyAssets,
    orders: {tabs: {'历史委托': emptyOrders, '历史成交': emptyDeals}},
};
const absent = mapping(snapshot, expected, '2026-08-25');
const wrongFilter = mapping({
    ...snapshot,
    orders: {tabs: {
        '历史委托': {
            ...emptyOrders,
            date_filter: {...emptyOrders.date_filter, start: '2026-08-18'},
        },
        '历史成交': emptyDeals,
    }},
}, expected, '2026-08-25');
const holdingPresent = mapping({
    ...snapshot,
    assets: {
        ...emptyAssets,
        table: {
            ...emptyAssets.table,
            row_count: 1,
            rows: [['603801 志邦家居', '800']],
        },
    },
}, expected, '2026-08-25');
const sameDay = mapping(snapshot, expected, '2026-08-24');
console.log(JSON.stringify({absent, wrongFilter, holdingPresent, sameDay}));
""".replace("MAPPING_SOURCE", json.dumps(_order_mapping_source()))
    completed = subprocess.run(
        [_node(), "--input-type=module", "--eval", node_script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["absent"]["status"] == "not_submitted"
    assert payload["absent"]["absenceProof"] is True
    assert payload["absent"]["statusReason"] == "prior_day_broker_absence_proven"
    assert payload["wrongFilter"]["absenceProof"] is False
    assert payload["holdingPresent"]["absenceProof"] is False
    assert payload["sameDay"]["absenceProof"] is False


def test_browser_scripts_execute_normal_and_fail_closed_readbacks(tmp_path: Path):
    common_url = (TEMPLATE_ROOT / "common.mjs").as_uri()
    prepare_path = str(TEMPLATE_ROOT / "prepare.js")
    node_script = r"""
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const common = await import(COMMON_URL);

function element(tag, text = '', attrs = {}, children = [], style = {}) {
    const node = {
        tagName: tag.toUpperCase(),
        children,
        attrs,
        style: {display: 'block', visibility: 'visible', opacity: '1', overflowY: 'visible', ...style},
        scrollHeight: 0,
        clientHeight: 0,
        scrollTop: 0,
        disabled: false,
        parentNode: null,
        getBoundingClientRect: () => ({width: 100, height: 20}),
        getAttribute: (name) => Object.prototype.hasOwnProperty.call(attrs, name)
            ? String(attrs[name]) : null,
        dispatchEvent: () => true,
        click: () => {},
    };
    for (const child of children) child.parentNode = node;
    Object.defineProperty(node, 'textContent', {
        get: () => children.length
            ? children.map((child) => child.textContent).join('')
            : text,
    });
    Object.defineProperty(node, 'innerText', {
        get: () => node.textContent,
    });
    node.classList = {
        contains: (name) => String(attrs.class || '').split(/\s+/).includes(name),
    };
    node.querySelectorAll = (selector) => {
        const selectors = selector.split(',').map((part) => part.trim()).filter(Boolean);
        const descendants = [];
        const visit = (candidate) => {
            for (const child of candidate.children) {
                descendants.push(child);
                visit(child);
            }
        };
        visit(node);
        return descendants.filter((candidate) => selectors.some((part) => {
            const simple = part.split(/\s+/).at(-1);
            if (simple === '*') return true;
            const tag = simple.match(/^[a-zA-Z][\w-]*/)?.[0];
            if (tag && candidate.tagName !== tag.toUpperCase()) return false;
            for (const classMatch of simple.matchAll(/\.([\w-]+)/g)) {
                if (!candidate.classList.contains(classMatch[1])) return false;
            }
            for (const attrMatch of simple.matchAll(
                /\[([\w-]+)(?:="([^"]*)")?\]/g
            )) {
                const actual = candidate.getAttribute(attrMatch[1]);
                if (actual === null) return false;
                if (attrMatch[2] !== undefined && actual !== attrMatch[2]) return false;
            }
            if (simple.includes(':checked') && candidate.checked !== true) return false;
            return true;
        }));
    };
    node.querySelector = (selector) => node.querySelectorAll(selector)[0] || null;
    return node;
}

function input(attrs = {}) {
    const node = element('input', '', attrs);
    node.value = '';
    node.checked = false;
    return node;
}

function select(options) {
    const node = element('select');
    node.options = options.map((text) => ({
        textContent: text,
        value: text ? `string:${text}` : '',
    }));
    node.value = '';
    Object.defineProperty(node, 'selectedOptions', {
        get: () => node.options.filter((option) => option.value === node.value),
    });
    return node;
}

function context(body, hash) {
    const document = {
        body,
        readyState: 'complete',
        title: 'Founder test page',
        querySelectorAll: (selector) => body.querySelectorAll(selector),
        querySelector: (selector) => body.querySelectorAll(selector)[0] || null,
    };
    return {
        document,
        location: {
            hash,
            href: `https://quant.foundersc.com/qtassets/dist/index.html${hash}`,
            origin: 'https://quant.foundersc.com',
            pathname: '/qtassets/dist/index.html',
        },
        getComputedStyle: (node) => node.style,
        HTMLInputElement: {prototype: {}},
        Event: class Event {
            constructor(type, options = {}) {
                this.type = type;
                this.bubbles = options.bubbles === true;
            }
        },
        setTimeout,
        clearTimeout,
        AbortController,
        performance: {
            getEntriesByType: (type) => type === 'resource'
                ? (body.resourceEntries || [])
                : [],
        },
        URL,
        Promise,
        Set,
        JSON,
        Number,
        Object,
        Array,
        String,
        Math,
        console,
    };
}

async function evaluate(script, body, hash) {
    return await vm.runInNewContext(script, context(body, hash));
}

const assetsScript = common.pageScript(ASSETS_BODY, {async: true});
const prepareSource = readFileSync(PREPARE_PATH, 'utf8');
const prepareFunctions = prepareSource.slice(
    prepareSource.indexOf('function manualLimitScript'),
    prepareSource.indexOf('function routeDetails'),
);
const prepareBuilders = new Function(
    'pageScript',
    `${prepareFunctions}; return {manualLimitScript, openingAuctionScript, timedOrderScript};`,
)(common.pageScript);
const prepareInput = {
    code: '600000',
    side: '买入',
    quantity: 100,
    price: 10,
    participation: 1,
    minute: 20,
    seconds: 0,
    strategyName: 'readback-probe',
    date: '2026-08-15',
    time: '09:30',
};
const openingScript = prepareBuilders.openingAuctionScript(prepareInput);
const timedScript = prepareBuilders.timedOrderScript(
    prepareInput,
    {dialogAlreadyOpen: true},
);
new Function(`return ${openingScript}`);
new Function(`return ${timedScript}`);
const timedMenuItem = element('span', '定时单', {}, [], {display: 'none'});
const timedMenu = element('div', '', {class: 'new-condition-strategy-dropDown'}, [
    timedMenuItem,
], {display: 'none'});
const timedTitle = element('div', '+ 新建策略', {
    class: 'new-condition-strategy-title',
});
const timedOuter = element('div', '+ 新建策略', {
    class: 'new-condition-strategy',
}, [timedTitle, timedMenu]);
let timedTitleClicks = 0;
let timedMenuClicks = 0;
const taskName = input({name: 'taskName'});
const stockCode = input({name: 'stockCode'});
const direction = input({class: 'children-absolute'});
const price = input({class: 'children-absolute'});
const quantity = input({name: 'quantity'});
const executeDate = input({class: 'al-modal-date-input', readonly: ''});
const hourSelect = select(['', '9', '10', '11', '13', '14']);
const minuteSelect = select(['', '30']);
const riskAgreement = input({type: 'checkbox'});
const cancelTimed = element('button', '取消', {type: 'button'});
const row = (label, field) => element('div', '', {class: 'al-modal-input-row'}, [
    element('label', label, {class: 'al-modal-input-label'}),
    field,
]);
const timedDialog = element('div', '', {role: 'dialog'}, [
    row('策略名称:', taskName),
    row('证券代码:', stockCode),
    row('委托方向:', direction),
    row('委托价格:', price),
    row('委托数量:', quantity),
    row('委托日期:', executeDate),
    row('委托时间:', hourSelect),
    minuteSelect,
    riskAgreement,
    cancelTimed,
]);
const timedBody = element('body', '', {}, [timedOuter]);
const sideList = element('ul', '', {}, [
    element('li', '买入'),
    element('li', '卖出'),
]);
const timedPriceList = element('ul', '', {}, [
    element('li', '现价'),
    element('li', '买一'),
    element('li', '卖一'),
    element('li', '开盘价'),
]);
direction.click = () => {
    if (!timedBody.children.includes(sideList)) timedBody.children.push(sideList);
};
price.click = () => {
    if (!timedBody.children.includes(timedPriceList)) {
        timedBody.children.push(timedPriceList);
    }
};
sideList.children[0].click = () => {
    direction.value = '买入';
    timedBody.children.splice(timedBody.children.indexOf(sideList), 1);
};
sideList.children[1].click = () => {
    direction.value = '卖出';
    timedBody.children.splice(timedBody.children.indexOf(sideList), 1);
};
const datePicker = element('div', '', {class: 'ui-datepicker'}, [
    element('span', '八月', {class: 'ui-datepicker-month'}),
    element('span', '2026', {class: 'ui-datepicker-year'}),
    element('a', '15', {
        class: 'ui-state-default',
        'data-date': '15',
        'data-month': '7',
        'data-year': '2026',
    }),
]);
executeDate.click = () => {
    if (!timedBody.children.includes(datePicker)) timedBody.children.push(datePicker);
};
datePicker.children[2].click = () => {
    executeDate.value = '2026-08-15';
    timedBody.children.splice(timedBody.children.indexOf(datePicker), 1);
};
cancelTimed.click = () => {
    timedBody.children.splice(timedBody.children.indexOf(timedDialog), 1);
};
timedTitle.click = () => {
    timedTitleClicks += 1;
    timedMenu.style.display = 'block';
    timedMenuItem.style.display = 'block';
};
timedMenuItem.click = () => {
    timedMenuClicks += 1;
    timedBody.children.push(timedDialog);
};
timedTitle.click();
timedMenuItem.click();
executeDate.value = '2026-08-15';
const timedExpandedMenu = await evaluate(
    timedScript,
    timedBody,
    '#/home/conditionStrategy/active',
);
const manualGap = await evaluate(
    prepareBuilders.manualLimitScript(prepareInput),
    element('body'),
    '#/home/orderByHand',
);
const normalTable = element('table', '', {}, [
        element('thead', '', {}, [
            element('th', '总资产'),
            element('th', '证券市值'),
            element('th', '可用资金'),
            element('th', '资金账号'),
        ]),
        element('tbody', '', {}, [
            element('tr', '', {}, [
                element('td', '100000'),
                element('td', '25000'),
                element('td', '50000'),
                element('td', '123456'),
            ]),
    ]),
]);
const normal = await evaluate(
    assetsScript,
    element('body', '', {}, [normalTable]),
    '#/home/myAccount/assets',
);
const duplicateAccountTable = element('table', '', {}, [
    element('thead', '', {}, [
        element('th', '总资产'),
        element('th', '证券市值'),
        element('th', '可用资金'),
        element('th', '资金账号'),
        element('th', '资金账号'),
    ]),
    element('tbody', '', {}, [
        element('tr', '', {}, [
            element('td', '100000'),
            element('td', '25000'),
            element('td', '50000'),
            element('td', '123456'),
            element('td', '7654321'),
        ]),
    ]),
]);
const duplicateAccounts = await evaluate(
    assetsScript,
    element('body', '', {}, [duplicateAccountTable]),
    '#/home/myAccount/assets',
);
const assetCards = element('body', '', {}, [
    element('div', '', {}, [element('span', '总资产'), element('strong', '100,000.00')]),
    element('div', '', {}, [element('span', '证券市值'), element('strong', '25,000.00')]),
    element('div', '', {}, [element('span', '可用资金'), element('strong', '70,000.00')]),
]);
const cards = await evaluate(
    assetsScript,
    assetCards,
    '#/home/myAccount/assets',
);
const outsideShortAccount = await evaluate(
    assetsScript,
    element('body', '', {}, [
        ...assetCards.children,
        element('span', '资金账号：7654321'),
    ]),
    '#/home/myAccount/assets',
);
const blank = await evaluate(
    assetsScript,
    element('body'),
    '#/home/myAccount/assets',
);
const ambiguousPagination = await evaluate(
    assetsScript,
    element('body', '', {}, [
        normalTable,
        element('div', '', {class: 'pagination'}),
    ]),
    '#/home/myAccount/assets',
);

const uniqueManual = await evaluate(
    common.MANUAL_ROUTE_DISCOVERY_SCRIPT,
    element('body', '', {}, [element('a', '详情', {
        href: '#/home/orderByHand/123/entrustDetail',
    })]),
    '#/home/myAccount/assets',
);
const ambiguousManual = await evaluate(
    common.MANUAL_ROUTE_DISCOVERY_SCRIPT,
    element('body', '', {}, [
        element('a', '一', {href: '#/home/orderByHand/123/entrustDetail'}),
        element('a', '二', {href: '#/home/orderByHand/456/entrustDetail'}),
    ]),
    '#/home/myAccount/assets',
);
const mockEnvironmentBody = element('body', '', {}, [
    element('div', '', {class: 'switcher___KVAWw'}, [
        element('span', '模拟盘交易'),
    ]),
    element('span', '资金账号：9876543210'),
]);
mockEnvironmentBody.resourceEntries = [
    {name: 'https://quant.foundersc.com/qt/user/mock/getFund'},
];
const environment = await evaluate(
    common.ENVIRONMENT_SCRIPT,
    mockEnvironmentBody,
    '#/home/myAccount/assets',
);
const staleMockBody = element('body', '', {}, [
    element('div', '', {class: 'switcher___KVAWw'}, [
        element('span', '模拟盘交易'),
    ]),
]);
staleMockBody.resourceEntries = [
    {name: 'https://quant.foundersc.com/qt/user/getFund'},
];
const staleEnvironment = await evaluate(
    common.ENVIRONMENT_SCRIPT,
    staleMockBody,
    '#/home/myAccount/assets',
);
const staleEnvironmentGate = common.environmentGate(staleEnvironment, 'mock');
const carriedEnvironment = common.carryEnvironmentProof(
    {
        ...environment,
        fund_account_fingerprint: '987******210',
        fund_account_match_count: 1,
        account_binding: 'proven',
    },
    {
        ...environment,
        route: '#/home/conditionStrategy/active',
        environment_data_namespace: 'unknown',
        environment_proof_complete: false,
    },
);
const rejectedCarry = common.carryEnvironmentProof(
    environment,
    {
        ...environment,
        environment: 'live',
        route: '#/home/conditionStrategy/active',
        environment_data_namespace: 'unknown',
        environment_proof_complete: false,
    },
);
const rejectedOppositeNamespaceCarry = common.carryEnvironmentProof(
    environment,
    {
        ...environment,
        route: '#/home/conditionStrategy/active',
        environment_data_namespace: 'live',
        environment_proof_complete: false,
    },
);
const rejectedConflictingAccountCarry = common.carryEnvironmentProof(
    {
        ...environment,
        fund_account_fingerprint: '987******210',
        fund_account_match_count: 1,
        account_binding: 'proven',
    },
    {
        ...environment,
        route: '#/home/myAccount/query',
        environment_data_namespace: 'unknown',
        environment_proof_complete: false,
        fund_account_fingerprint: '123******456',
        fund_account_match_count: 1,
        account_binding: 'proven',
    },
);
const sameAccountStaleBindingCarry = common.carryEnvironmentProof(
    {
        ...environment,
        fund_account_fingerprint: '987******210',
        fund_account_match_count: 1,
        account_binding: 'proven',
    },
    {
        ...environment,
        route: '#/home/myAccount/query',
        environment_data_namespace: 'unknown',
        environment_proof_complete: false,
        fund_account_fingerprint: '987******210',
        fund_account_match_count: 1,
        account_binding: 'not_proven',
    },
);
const missingAuthenticatedAccountGate = common.environmentGate(
    {
        ...environment,
        fund_account_match_count: 0,
    },
    'mock',
);
const accountApi = await vm.runInNewContext(
    common.FUND_ACCOUNT_SCRIPT,
    {
        ...context(element('body'), '#/home/myAccount/assets'),
        fetch: async () => ({
            ok: true,
            json: async () => ({info: {fund_id: '9876543210'}}),
        }),
    },
);
const shortAccountApi = await vm.runInNewContext(
    common.FUND_ACCOUNT_SCRIPT,
    {
        ...context(element('body'), '#/home/myAccount/assets'),
        fetch: async () => ({
            ok: true,
            json: async () => ({info: {fund_id: '123456'}}),
        }),
    },
);
const exactRoute = common.routeMatches(
    'manual',
    '#/home/orderByHand/123/entrustDetail',
    '#/home/orderByHand/123/entrustDetail',
);
const wrongRoute = common.routeMatches(
    'manual',
    '#/home/orderByHand/123/entrustDetail',
    '#/home/orderByHand/456/entrustDetail',
);
console.log(JSON.stringify({
    normal,
    duplicateAccounts,
    cards,
    outsideShortAccount,
    blank,
    ambiguousPagination,
    uniqueManual,
    ambiguousManual,
    environment,
    staleEnvironment,
    staleEnvironmentGate,
    carriedEnvironment,
    rejectedCarry,
    rejectedOppositeNamespaceCarry,
    rejectedConflictingAccountCarry,
    sameAccountStaleBindingCarry,
    missingAuthenticatedAccountGate,
    accountApi,
    shortAccountApi,
    exactRoute,
    wrongRoute,
    manualGap,
    timedExpandedMenu,
    timedTitleClicks,
    timedMenuClicks,
}));
    """
    node_script = node_script.replace("COMMON_URL", json.dumps(common_url))
    node_script = node_script.replace("PREPARE_PATH", json.dumps(prepare_path))
    node_script = node_script.replace("ASSETS_BODY", json.dumps(_assets_body(), ensure_ascii=False))
    result = subprocess.run(
        [_node(), "--input-type=module", "-e", node_script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["normal"]["surface_ready"] is True
    assert payload["normal"]["complete_scan"] is True
    assert payload["normal"]["pagination_complete"] is True
    assert payload["normal"]["allocation_summary"]["complete"] is True
    assert payload["cards"]["allocation_summary"]["complete"] is True
    assert payload["cards"]["allocation_summary"]["values"] == {
        "总资产": "100,000.00",
        "证券市值": "25,000.00",
        "可用资金": "70,000.00",
    }
    assert payload["blank"]["surface_ready"] is False
    assert payload["blank"]["complete_scan"] is False
    assert payload["ambiguousPagination"]["pagination_complete"] is False
    assert payload["ambiguousPagination"]["complete_scan"] is False
    assert payload["uniqueManual"]["route_available"] is True
    assert payload["ambiguousManual"]["route_available"] is False
    assert payload["environment"]["environment"] == "mock"
    assert payload["environment"]["environment_data_namespace"] == "mock"
    assert payload["environment"]["environment_proof_complete"] is True
    assert payload["environment"]["environment_resource_count"] == 1
    assert payload["environment"]["switcher_count"] == 1
    assert payload["environment"]["fund_account_fingerprint"] == ""
    assert payload["environment"]["fund_account_match_count"] == 0
    assert payload["staleEnvironment"]["environment"] == "mock"
    assert payload["staleEnvironment"]["environment_data_namespace"] == "live"
    assert payload["staleEnvironment"]["environment_proof_complete"] is False
    assert payload["staleEnvironmentGate"] == {
        "status": "unknown",
        "reason": "environment_ui_data_namespace_mismatch",
        "reconcile_required": True,
    }
    assert payload["carriedEnvironment"]["environment_proof_complete"] is True
    assert (
        payload["carriedEnvironment"]["environment_proof_source"]
        == "same_tab_assets_preflight"
    )
    assert payload["carriedEnvironment"]["route"] == (
        "#/home/conditionStrategy/active"
    )
    assert payload["carriedEnvironment"]["fund_account_fingerprint"] == (
        "987******210"
    )
    assert payload["carriedEnvironment"]["fund_account_match_count"] == 1
    assert payload["carriedEnvironment"]["account_binding"] == "proven"
    assert payload["rejectedCarry"]["environment_proof_complete"] is False
    assert (
        payload["rejectedOppositeNamespaceCarry"]["environment_data_namespace"]
        == "live"
    )
    assert (
        payload["rejectedOppositeNamespaceCarry"]["environment_proof_complete"]
        is False
    )
    assert payload["rejectedConflictingAccountCarry"]["fund_account_fingerprint"] == (
        "123******456"
    )
    assert payload["sameAccountStaleBindingCarry"]["account_binding"] == "proven"
    assert payload["missingAuthenticatedAccountGate"] == {
        "status": "unknown",
        "reason": "environment_authenticated_account_readback_missing",
        "reconcile_required": True,
    }
    assert payload["accountApi"] == {
        "fund_account_fingerprint": "987******210",
        "fund_account_match_count": 1,
        "fund_account_proof_source": "same_origin_getBaseInfo",
    }
    assert payload["shortAccountApi"] == {
        "fund_account_fingerprint": "",
        "fund_account_match_count": 1,
        "fund_account_proof_source": "same_origin_getBaseInfo",
    }
    assert payload["normal"]["table"]["rows"][0][-1] == "******"
    assert "123456" not in payload["normal"]["body_text"]
    assert payload["duplicateAccounts"]["table"]["rows"][0][-2:] == [
        "******",
        "******",
    ]
    assert "123456" not in payload["duplicateAccounts"]["body_text"]
    assert "7654321" not in payload["duplicateAccounts"]["body_text"]
    assert "7654321" not in payload["outsideShortAccount"]["body_text"]
    assert payload["exactRoute"] is True
    assert payload["wrongRoute"] is False
    assert payload["manualGap"]["route_available"] is False
    assert payload["manualGap"]["reason"] == "manual_limit_form_or_field_not_unique"
    assert payload["timedTitleClicks"] == 1
    assert payload["timedMenuClicks"] == 1
    assert payload["timedExpandedMenu"]["route_available"] is False
    assert (
        payload["timedExpandedMenu"]["reason"]
        == "timed_order_numeric_limit_not_supported"
    )
    assert payload["timedExpandedMenu"]["field_readback"] == {
        "available_price_types": ["现价", "买一", "卖一", "开盘价"],
        "requested_limit_price": "10",
        "submitted": False,
        "saved": False,
        "started": False,
    }
    assert payload["timedExpandedMenu"]["form_closed_after_readback"] is True


def test_login_fill_script_executes_exactly_once_and_returns_no_secret() -> None:
    common_url = (TEMPLATE_ROOT / "common.mjs").as_uri()
    login_path = str(TEMPLATE_ROOT / "login.js")
    node_script = r"""
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const common = await import(COMMON_URL);
const source = readFileSync(LOGIN_PATH, 'utf8');
const functions = source.slice(
    source.indexOf('const LOGIN_DISCOVERY_SCRIPT'),
    source.indexOf('function loginReceipt'),
);
const login = new Function(
    'pageScript',
    'TARGET_ATTRIBUTE',
    `${functions}; return {loginFillScript};`,
)(common.pageScript, 'data-opencli-foundersc-login-target');

function node(tag, text, attrs = {}) {
    return {
        tagName: tag.toUpperCase(),
        innerText: text,
        textContent: text,
        attrs: {...attrs},
        value: '',
        disabled: false,
        children: [],
        style: {display: 'block', visibility: 'visible', opacity: '1'},
        classList: {contains: () => false},
        getBoundingClientRect: () => ({width: 100, height: 20}),
        getAttribute(name) { return Object.hasOwn(this.attrs, name) ? this.attrs[name] : null; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        removeAttribute(name) { delete this.attrs[name]; },
        dispatchEvent: () => true,
    };
}

function run(passwordCount) {
    const phone = node('input', '', {placeholder: '请输入手机号码'});
    const passwords = Array.from({length: passwordCount}, () => (
        node('input', '', {placeholder: '请输入量化平台密码'})
    ));
    const button = node('button', '登录模拟盘');
    const all = [phone, ...passwords, button];
    const document = {
        body: node('body'),
        querySelectorAll(selector) {
            if (selector === 'input[placeholder="请输入手机号码"]') return [phone];
            if (selector === 'input[placeholder="请输入量化平台密码"]') return passwords;
            if (selector === 'button') return [button];
            if (selector === '[data-opencli-foundersc-login-target]') {
                return all.filter((item) => item.getAttribute(
                    'data-opencli-foundersc-login-target'
                ) !== null);
            }
            return [];
        },
    };
    const result = vm.runInNewContext(
        login.loginFillScript('13800138000', 'sensitive-password'),
        {
            document,
            getComputedStyle: (item) => item.style,
            HTMLInputElement: {prototype: {}},
            Event: class Event {},
            setTimeout,
            Promise,
            Set,
            JSON,
            Number,
            Object,
            Array,
            String,
        },
    );
    return {result, phone, passwords, button};
}

const exact = run(1);
const ambiguous = run(2);
console.log(JSON.stringify({
    exactResult: exact.result,
    exactPhoneValue: exact.phone.value,
    exactPasswordValue: exact.passwords[0].value,
    exactTarget: exact.button.getAttribute('data-opencli-foundersc-login-target'),
    ambiguousResult: ambiguous.result,
}));
"""
    node_script = node_script.replace("COMMON_URL", json.dumps(common_url))
    node_script = node_script.replace("LOGIN_PATH", json.dumps(login_path))
    result = subprocess.run(
        [_node(), "--input-type=module", "-e", node_script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["exactResult"] == {
        "ready": True,
        "phone_input_count": 1,
        "password_input_count": 1,
        "login_button_count": 1,
        "phone_binding_match": True,
        "password_secret_present": True,
        "login_button_disabled": False,
    }
    assert payload["exactPhoneValue"] == "13800138000"
    assert payload["exactPasswordValue"] == "sensitive-password"
    assert payload["exactTarget"] == "submit-login"
    assert "13800138000" not in json.dumps(payload["exactResult"])
    assert "sensitive-password" not in json.dumps(payload["exactResult"])
    assert payload["ambiguousResult"]["ready"] is False
    assert payload["ambiguousResult"]["password_input_count"] == 2
