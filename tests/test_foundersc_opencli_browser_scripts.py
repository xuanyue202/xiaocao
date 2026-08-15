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
            return true;
        }));
    };
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
const timedScript = prepareBuilders.timedOrderScript(prepareInput);
new Function(`return ${openingScript}`);
new Function(`return ${timedScript}`);
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
console.log(JSON.stringify({normal, blank, ambiguousPagination, uniqueManual, ambiguousManual, environment, exactRoute, wrongRoute, manualGap}));
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
