import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const scenario = process.argv[2];
const target = 'course-compressed.mp4';
const input = {targetName: target, directory: '/课程/自己的课/小草', claimId: 'kol-netdisk-test12345'};
const continueOnly = scenario.startsWith('continue_');
let phase = scenario === 'paused_initial' || continueOnly ? 'paused' : 'uploading';
if (scenario === 'continue_error') phase = 'error';
let clock = 0;
let clicks = 0;
let attaches = 0;
let navigations = 0;
const width = () => scenario === 'progress' || scenario === 'continue_progress' || (clicks === (continueOnly ? 1 : 2) && phase === 'uploading') ? '1%' : '0%';
const node = title => ({
  attrs: {}, title,
  getBoundingClientRect: () => ({width: 20, height: 20}),
  setAttribute(key, value) { this.attrs[key] = value; },
  removeAttribute(key) { delete this.attrs[key]; },
});
const name = node(target);
const action = node('');
Object.defineProperty(action, 'title', {get: () => phase === 'uploading' ? '暂停' : phase === 'paused' ? '继续上传' : '开始'});
const cancel = node('取消');
const duplicate = node('暂停');
const all = () => scenario === 'ambiguous' ? [name, action, duplicate, cancel] : [name, action, cancel];
const row = {
  get innerText() { return target + '\n712M\n' + (width() === '0%' ? '0B/s' : '50KB/s'); },
  classList: {contains(value) {
    return value === (phase === 'uploading' ? 'status-uploading' : phase === 'paused' ? 'status-pause' : 'status-error');
  }},
  querySelectorAll(selector) {
    if (selector === '[title]') return all();
    if (selector === '[style]') return [{style: {width: width()}}];
    if (selector === '[data-xiaocao-transfer-recovery]') return all().filter(n => n.attrs['data-xiaocao-transfer-recovery']);
    throw Error('Unexpected DOM selector ' + selector);
  },
};
const panel = {
  clientHeight: 100, scrollHeight: scenario === 'incomplete' ? 1000 : 100,
  get innerText() { return '仅展示本次上传任务\n' + row.innerText; },
  querySelectorAll: selector => selector === '.file-list' ? [row] : [],
};
const dom = vm.createContext({
  document: {querySelectorAll: selector => selector === '.uploader-list' ? [panel] : []},
  location: {href: 'https://pan.baidu.com/disk/main#/index?path=' + encodeURIComponent(scenario === 'wrong_folder' ? '/other' : input.directory)},
  URL, URLSearchParams,
  getComputedStyle: () => ({display: 'block', visibility: 'visible', opacity: '1'}),
});
const page = {
  evaluate: async source => vm.runInContext(source, dom),
  click: async selector => {
    clicks += 1;
    assert.equal(selector, '[data-xiaocao-transfer-recovery="' + input.claimId + '"]');
    assert.equal(all().filter(n => n.attrs['data-xiaocao-transfer-recovery'] === input.claimId).length, 1);
    if (scenario === 'denied') throw Error('Native input denied');
    if (continueOnly) phase = 'uploading';
    else if (clicks === 1) phase = scenario === 'error_after_pause' ? 'error' : 'paused';
    else phase = 'uploading';
  },
  uploadFiles: async () => { attaches += 1; throw Error('Must not attach'); },
  goto: async () => { navigations += 1; throw Error('Must not navigate'); },
};
const text = fs.readFileSync('opencli/clis/baidu-netdisk/upload.js', 'utf8');
const start = text.indexOf('async function recoverStalledTransfer');
const end = text.indexOf('\ncli({', start);
assert(start >= 0 && end > start);
const context = vm.createContext({
  CommandExecutionError: Error,
  uploadStage: async (_input, _stage, fn) => fn(),
  Date: {now: () => { clock += 1000; return clock; }},
  setTimeout: callback => callback(),
});
vm.runInContext(text.slice(start, end), context);
const inspection = {surfaceState: {transferQueue: {complete: true, rowCount: 1, targetCount: 1, successfulCount: 0},
  targetUiRows: [{rowClassName: continueOnly ? 'status-pause file-list' : 'status-uploading file-list', progressWidths: ['0%'], rowText: target + '\n712M\n0B/s'}]}};
let receipt;
let failure;
try { receipt = await context.recoverStalledTransfer(page, input, inspection, {continueOnly}); }
catch (error) { failure = error.message; }
if (scenario === 'success' || scenario === 'continue_success') {
  assert.equal(failure, undefined);
  assert.equal(receipt[0].status, 'existing_upload_resumed');
  assert.equal(clicks, continueOnly ? 1 : 2);
} else {
  assert(failure, 'Unsafe scenario must refuse recovery');
  assert.equal(clicks, ['denied', 'error_after_pause'].includes(scenario) ? 1 : 0);
}
assert.equal(attaches, 0);
assert.equal(navigations, 0);
console.log(JSON.stringify({scenario, clicks, attaches, navigations, failure, receipt}));
