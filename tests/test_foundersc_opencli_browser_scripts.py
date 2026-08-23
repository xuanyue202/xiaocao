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
direction.click = () => {
    if (!timedBody.children.includes(sideList)) timedBody.children.push(sideList);
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
        element('th', '可用资金'),
    ]),
    element('tbody', '', {}, [
        element('tr', '', {}, [element('td', '100000'), element('td', '50000')]),
    ]),
]);
const normal = await evaluate(
    assetsScript,
    element('body', '', {}, [normalTable]),
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
const environment = await evaluate(
    common.ENVIRONMENT_SCRIPT,
    element('body', '', {}, [element('div', '', {class: 'switcher___KVAWw'}, [
        element('span', '模拟盘交易'),
    ])]),
    '#/home/myAccount/assets',
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
    blank,
    ambiguousPagination,
    uniqueManual,
    ambiguousManual,
    environment,
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
    assert payload["blank"]["surface_ready"] is False
    assert payload["blank"]["complete_scan"] is False
    assert payload["ambiguousPagination"]["pagination_complete"] is False
    assert payload["ambiguousPagination"]["complete_scan"] is False
    assert payload["uniqueManual"]["route_available"] is True
    assert payload["ambiguousManual"]["route_available"] is False
    assert payload["environment"]["environment"] == "mock"
    assert payload["environment"]["switcher_count"] == 1
    assert payload["exactRoute"] is True
    assert payload["wrongRoute"] is False
    assert payload["manualGap"]["route_available"] is False
    assert payload["manualGap"]["reason"] == "manual_limit_form_or_field_not_unique"
    assert payload["timedTitleClicks"] == 1
    assert payload["timedMenuClicks"] == 1
    assert payload["timedExpandedMenu"]["route_available"] is True
    assert payload["timedExpandedMenu"]["field_readback"] == {
        "strategy_name": "readback-probe",
        "code": "600000",
        "side": "买入",
        "price": "10",
        "quantity": "100",
        "date": "2026-08-15",
        "hour": "9",
        "minute": "30",
        "risk_agreement_checked": False,
        "submitted": False,
        "saved": False,
        "started": False,
    }
    assert payload["timedExpandedMenu"]["form_closed_after_readback"] is True
