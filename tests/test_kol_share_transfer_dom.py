"""Execute the production share-save DOM path, including its native submit seam."""

import json
import shutil
import subprocess

import pytest

from xiaocao.kol.subscription_video import (
    _TRANSFER_OUTCOME_SCRIPT,
    _TRANSFER_PAGE_SUBMIT_SCRIPT,
    _TRANSFER_SCRIPT,
)


_PAGE = r"""
const vm = require('vm');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let clock = 0, dialogVisible = false, selected = false;
let submitted = 0, destination = '/', marked = new Map(), clickListeners = [];
const rect = {width: 100, height: 30, left: 20, top: 20};
const node = (text, extra = {}) => ({
  innerText: text, textContent: text,
  getBoundingClientRect: () => rect,
  setAttribute: (key, value) => marked.set(`[${key}="${value}"]`, extra.self),
  getAttribute: () => null,
  querySelectorAll: () => [], querySelector: () => null,
  classList: {contains: () => false}, ...extra
});
const checkbox = node('', {
  getAttribute: key => key === 'aria-checked' ? String(selected) : null,
  click: () => {selected = !selected;}
});
const filename = node('137.mp4', {getAttribute: () => '137.mp4'});
const row = node('', {
  querySelectorAll: selector => selector === '[role="checkbox"]' ? [checkbox] : [],
  querySelector: selector => selector === 'a.filename' ? filename :
    selector === '[role="checkbox"]' ? checkbox : null,
});
const treeNode = {classList: {contains: () => true}};
const segments = ['课程', '自己的课', '吕晓彤'].map(text => node(text, {
  closest: selector => selector === '.treeview-node' ? treeNode : {click: () => {}},
}));
const pathControl = node('我的网盘', {click: () => {dialogVisible = true;}});
const submit = node('保存到网盘', {click: () => {
  if (input.mode === 'submit_dialog' && !dialogVisible) {
    dialogVisible = true; return;
  }
  submitted++;
  sandbox.window.fetch('/share/transfer', {method: 'POST', body: 'path=' + destination});
}});
submit.self = submit;
const confirm = node('确定', {click: () => {
  destination = input.mode === 'wrong_destination' ? '/wrong' : '/课程/自己的课/吕晓彤';
  dialogVisible = false;
  pathControl.innerText = '我的网盘' + destination;
  if (['submit_dialog', 'unexpected_effect'].includes(input.mode)) {
    submitted++;
    sandbox.window.fetch('/share/transfer', {method: 'POST', body: 'path=' + destination});
  }
}});
confirm.self = confirm;
// The marker must resolve to the actual node, as OpenCLI's native click does.
for (const control of [confirm, submit]) {
  control.setAttribute = (key, value) => marked.set(`[${key}="${value}"]`, control);
}
const dialog = node(input.mode === 'submit_dialog' ? '保存到\n我的网盘' : '选择保存路径\n我的网盘', {
  getBoundingClientRect: () => dialogVisible ? rect : {width: 0, height: 0},
  querySelectorAll: selector => selector === '.treeview-txt' ? segments : [confirm],
});
const document = {
  body: {innerText: ''},
  elementFromPoint: () => input.mode === 'obstructed' ? null : dialogVisible ? confirm : submit,
  addEventListener: (name, fn) => {if(name === 'click') clickListeners.push(fn);},
  querySelectorAll: selector => {
    if (marked.has(selector)) return [marked.get(selector)];
    if (selector === '#shareqr dd') return [row];
    if (selector === '.save-path') return [pathControl];
    if (selector === 'a[node-type="shareSave"].save_btn') {
      return input.mode === 'submit_dialog' ? [submit] : [];
    }
    if (selector === 'a[node-type="shareSave"].first_btn') return [submit];
    if (selector === 'a[node-type="bottomShareSave"]') {
      return input.mode === 'ambiguous_submit' ? [submit, node('保存到网盘')] : [submit];
    }
    if (selector === '.dialog-fileTreeDialog') return dialogVisible ? [dialog] : [];
    if (selector === '#share-save-dialog-title') return [];
    return [];
  },
};
const sandbox = {
  document, location: {origin: 'https://pan.baidu.com', pathname: '/s/test', href: 'https://pan.baidu.com/s/test'},
  window: {fetch: async () => ({status: 200, clone: () => ({text: async () => '{"errno":0}'})})},
  getComputedStyle: () => ({display: 'block', visibility: 'visible'}),
  Date: {now: () => clock}, setTimeout: (fn, delay) => {clock += delay; fn();},
  URL, URLSearchParams,
};
let finishOldResponse;
const response = errno => ({status: 200, clone: () => ({text: async () => JSON.stringify({errno})})});
if (input.mode === 'late_previous_response') {
  let calls = 0;
  sandbox.window.fetch = () => calls++ === 0
    ? new Promise(resolve => {finishOldResponse = resolve;})
    : Promise.resolve(response(0));
}
if (input.mode === 'stale_response') {
  const state = {installed: true, observerVersion: 2, generation: 1,
    requestSeen: true, responseSeen: true,
    records: [{http_status: 200, errno: 12}]};
  sandbox.window.__xiaocaoLvTransferNetwork = state;
  sandbox.window.fetch = async () => {
    state.requestSeen = true; state.responseSeen = true;
    state.records.push({http_status: 200, errno: 0});
    return {status: 200};
  };
}
(async () => {
  let prepared = await vm.runInNewContext(input.prepare, sandbox);
  if (input.mode === 'late_previous_response') {
    const oldRequest = sandbox.window.fetch('/share/transfer', {method:'POST'});
    prepared = await vm.runInNewContext(input.prepare, sandbox);
    finishOldResponse(response(12));
    await oldRequest;
  }
  const firstPrepared = prepared;
  let nativeClicks = 0;
  for (let step=0; step<2; step++) {
    const control = marked.get(prepared.confirmation_selector);
    if (control && input.mode !== 'lost_input') {
      nativeClicks++;
      for(const listener of clickListeners) listener({isTrusted:true, composedPath:()=>[control]});
      control.click();
    }
    await Promise.resolve(); await Promise.resolve();
    if (prepared.confirmation_role !== 'destination_selection') break;
    prepared = await vm.runInNewContext(input.submit, sandbox);
    if (prepared.status !== 'save_confirmation_ready') break;
  }
  await Promise.resolve(); await Promise.resolve();
  const outcome = await vm.runInNewContext(input.observe, sandbox);
  process.stdout.write(JSON.stringify({firstPrepared, prepared, outcome, submitted, destination, nativeClicks}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


def _run_page(mode):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the production DOM seam")
    prepare = _TRANSFER_SCRIPT
    for key, value in {
        "__SHARE_PATH__": "/s/test",
        "__SOURCE_PARENT__": "/course",
        "__TARGET_NAME__": "137.mp4",
        "__DESTINATION_SEGMENTS__": ["课程", "自己的课", "吕晓彤"],
    }.items():
        prepare = prepare.replace(key, json.dumps(value, ensure_ascii=False))
    run = subprocess.run(
        [node, "-e", _PAGE],
        input=json.dumps({"mode": mode, "prepare": prepare, "submit": _TRANSFER_PAGE_SUBMIT_SCRIPT, "observe": _TRANSFER_OUTCOME_SCRIPT}),
        text=True, capture_output=True, timeout=5, check=True,
    )
    return json.loads(run.stdout)


@pytest.mark.parametrize("mode", ["destination_picker", "submit_dialog", "stale_response", "late_previous_response"])
def test_share_save_reaches_provider_after_destination_selection(mode):
    result = _run_page(mode)
    assert result["destination"] == "/课程/自己的课/吕晓彤"
    assert result["submitted"] == 1, result
    assert result["outcome"]["provider_outcome"] == "accepted", result
    assert result["outcome"]["provider_request_observed"] is True
    assert result["outcome"]["provider_response_observed"] is True
    assert result["outcome"]["input_target_observed"] is True
    assert all(record["errno"] == 0 for record in result["outcome"]["provider_network_records"])


@pytest.mark.parametrize("mode", ["wrong_destination", "ambiguous_submit", "obstructed"])
def test_share_save_does_not_submit_to_wrong_or_ambiguous_controls(mode):
    result = _run_page(mode)
    assert result["submitted"] == 0, result
    assert result["outcome"]["provider_request_observed"] is False


def test_unexpected_provider_effect_during_path_selection_is_not_repeated():
    result = _run_page("unexpected_effect")
    assert result["submitted"] == 1, result
    assert result["outcome"]["provider_request_observed"] is True
    assert result["nativeClicks"] == 1


def test_selector_match_without_input_is_distinguishable_from_transfer():
    result = _run_page("lost_input")
    assert result["submitted"] == 0
    assert result["outcome"]["input_event_probe_installed"] is True
    assert result["outcome"]["input_target_observed"] is False
    assert result["outcome"]["provider_request_observed"] is False
