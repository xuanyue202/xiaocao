import { cli, Strategy } from '@jackwener/opencli/registry';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import {
  ArgumentError,
  AuthRequiredError,
  CommandExecutionError,
} from '@jackwener/opencli/errors';

const DEFAULT_DIRECTORY = '/课程/自己的课/小草';
const UPLOAD_INPUT = 'input[type="file"][title="点击选择文件"][accept="*/*"]';

// Credential-free, claim-bound progress survives CLI/runtime failures. Never
// infer a pre-attachment failure after attach.begin has appeared.
async function uploadStage(input, stage, action) {
  const emit = phase => process.stderr.write(JSON.stringify({
    kind: 'xiaocao_upload_stage', claimId: input.claimId, stage, phase,
  }) + '\n');
  emit('begin');
  const result = await action();
  emit('end');
  return result;
}

async function restoreUploaderWindow(page, input) {
  const state = await uploadStage(input, 'page_state', () => page.evaluate(`({
    visibility: document.visibilityState, url: location.href
  })`));
  if (state?.visibility !== 'hidden') return;
  if (process.platform !== 'darwin') {
    throw new CommandExecutionError('Hidden uploader requires exact Edge window restoration');
  }
  // The retained Bridge page is the identity. Geometry can be stale and two
  // native tabs can share both URL and bounds. A temporary title binds only
  // this page to its native tab; restore it even if foregrounding fails.
  const marker = `Xiaocao uploader ${randomUUID()}`;
  const originalTitle = await page.evaluate(`(() => {
    const original = document.title;
    document.title = ${JSON.stringify(marker)};
    return original;
  })()`);
  const script = `on run argv
    set expectedURL to item 1 of argv
    set expectedTitle to item 2 of argv
    tell application "Microsoft Edge"
      set candidates to {}
      repeat with w in windows
        repeat with i from 1 to count of tabs of w
          if URL of tab i of w is expectedURL and title of tab i of w is expectedTitle then
            set end of candidates to {(id of w as integer), i, (id of tab i of w as text)}
          end if
        end repeat
      end repeat
      if count of candidates is not 1 then error "Exact marked uploader tab is missing or ambiguous"
      set chosen to item 1 of candidates
      set w to window id (item 1 of chosen)
      set tabIndex to item 2 of chosen
      if (id of tab tabIndex of w as text) is not item 3 of chosen then error "Uploader tab changed"
      if URL of tab tabIndex of w is not expectedURL then error "Uploader URL changed"
      if title of tab tabIndex of w is not expectedTitle then error "Uploader title binding changed"
      set active tab index of w to tabIndex
      set index of w to 1
      activate
    end tell
    return "foreground_requested"
  end run`;
  try {
    await uploadStage(input, 'foreground', async () => {
      try {
        execFileSync('/usr/bin/osascript', ['-e', script, state.url, marker],
          {encoding: 'utf8', timeout: 10000});
      } catch {
        throw new CommandExecutionError('Exact Edge uploader window restoration failed; no file attached');
      }
    });
  } finally {
    await page.evaluate(`(() => {
      if (document.title === ${JSON.stringify(marker)}) document.title = ${JSON.stringify(originalTitle)};
    })()`);
  }
  const heartbeat = await uploadStage(input, 'event_loop', () => page.evaluate(
    'new Promise(resolve => setTimeout(() => resolve({responsive:true}), 100))'
  ));
  if (heartbeat?.responsive !== true) {
    throw new CommandExecutionError('Uploader event loop recovery was not verified');
  }
}

function basename(value) {
  return String(value || '').split(/[\\/]/).filter(Boolean).at(-1) || '';
}

function normalizeInput(kwargs) {
  const file = String(kwargs.file || '').trim();
  const directory = String(kwargs.directory || DEFAULT_DIRECTORY).trim();
  const targetName = String(kwargs['target-name'] || '').trim();
  const claimId = String(kwargs['claim-id'] || '').trim();
  if (!file.startsWith('/')) {
    throw new ArgumentError('--file must be an absolute local path');
  }
  if (!directory.startsWith('/') || (directory !== '/' && directory.endsWith('/'))
      || directory.includes('//') || /[?#]/.test(directory)) {
    throw new ArgumentError('--directory must be one normalized absolute Netdisk path');
  }
  if (!targetName || targetName === '.' || targetName === '..' || /[\\/]/.test(targetName)) {
    throw new ArgumentError('--target-name must be one exact basename');
  }
  if (basename(file) !== targetName) {
    throw new ArgumentError('--target-name must exactly match the local file basename');
  }
  if (!/^[A-Za-z0-9_.:-]{8,128}$/.test(claimId)) {
    throw new ArgumentError('--claim-id must be the durable upload claim identifier');
  }
  return { file, directory, targetName, claimId };
}

async function inspectTarget(page, input, { retainPage = false } = {}) {
  const folderUrl = 'https://pan.baidu.com/disk/main#/index?category=all&path='
    + encodeURIComponent(input.directory);
  if (!page.tabs || !page.selectTab) {
    throw new CommandExecutionError('Exact OpenCLI site page selection is required');
  }
  // Adapter and browser-command surfaces have separate leases, even with the
  // same session name. Resolve only THIS adapter's page and preserve its queue.
  const tabs = await uploadStage(input, 'tabs', () => page.tabs());
  const targets = tabs.filter(tab => {
    try {
      const url = new URL(tab.url);
      const query = url.hash.slice(url.hash.indexOf('?') + 1);
      return url.origin === 'https://pan.baidu.com' && url.pathname === '/disk/main'
        && new URLSearchParams(query).get('path') === input.directory;
    } catch { return false; }
  });
  if (targets.length > 1) {
    throw new CommandExecutionError('Multiple exact adapter uploader pages; selection is ambiguous');
  }
  if (targets.length === 1 && targets[0].page) {
    await uploadStage(input, 'select', () => page.selectTab(targets[0].page));
  } else {
    if (retainPage) {
      throw new CommandExecutionError('Retained adapter uploader page is missing; inspection must not navigate');
    }
    await uploadStage(input, 'navigate', () => page.goto(folderUrl, { waitUntil: 'load', settleMs: 1500 }));
    const activePage = page.getActivePage?.();
    if (!activePage) throw new CommandExecutionError('Exact adapter page identity is missing');
    await uploadStage(input, 'select', () => page.selectTab(activePage));
  }
  await restoreUploaderWindow(page, input);
  const inspection = await uploadStage(input, 'folder_scan', () => page.evaluate(`(async () => {
    const dir = ${JSON.stringify(input.directory)};
    const target = ${JSON.stringify(input.targetName)};
    const currentUrl = new URL(location.href);
    const hashQuery = currentUrl.hash.includes('?')
      ? currentUrl.hash.slice(currentUrl.hash.indexOf('?') + 1)
      : '';
    const currentDir = new URLSearchParams(hashQuery).get('path');
    const folderBound = currentUrl.origin === 'https://pan.baidu.com'
      && currentUrl.pathname === '/disk/main'
      && currentDir === dir;
    if (!folderBound) {
      return {folderBound: false, authenticated: true, completeScan: false};
    }
    const visible = (node) => {
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return rect.width > 0 && rect.height > 0
        && style.display !== 'none' && style.visibility !== 'hidden'
        && Number(style.opacity) !== 0;
    };
    const pageSize = 1000;
    const maxPages = 100;
    let pageNumber = 1;
    let exactCount = 0;
    let completeScan = false;
    let errno = 0;
    while (pageNumber <= maxPages) {
      const url = '/api/list?clienttype=0&app_id=250528&web=1'
        + '&order=name&desc=1&dir=' + encodeURIComponent(dir)
        + '&num=' + pageSize + '&page=' + pageNumber;
      const response = await fetch(url, {credentials: 'include', signal: AbortSignal.timeout(15000)});
      let body;
      try {
        body = await response.json();
      } catch (_error) {
        return {folderBound: true, authenticated: false, completeScan: false};
      }
      errno = body.errno;
      if (errno !== 0) break;
      const items = Array.isArray(body.list) ? body.list : [];
      exactCount += items.filter((item) => item.server_filename === target).length;
      const hasMore = body.has_more === 1 || body.has_more === true;
      if (!hasMore && items.length < pageSize) {
        completeScan = true;
        break;
      }
      if (items.length === 0) {
        completeScan = true;
        break;
      }
      pageNumber += 1;
    }
    return {
      folderBound: true,
      authenticated: errno === 0,
      completeScan,
      exactCount,
      errno,
      url: location.origin + location.pathname,
      surfaceState: {
        visibility: document.visibilityState,
        focused: document.hasFocus(),
        userActive: navigator.userActivation?.isActive === true,
        inputs: [...document.querySelectorAll('input[type="file"]')].map(node => ({
          title: node.title, accept: node.accept, directory: node.hasAttribute('webkitdirectory'),
          visible: visible(node), disabled: node.disabled,
          targetAttached: [...(node.files || [])].some(file => file.name === target),
        })),
        receiptClaim: window.__opencliBaiduUploadReceipt?.claim || '',
        receiptMatchesTarget: (window.__opencliBaiduUploadReceipt?.fileNames || []).includes(target),
        targetInTransferUi: [...document.querySelectorAll('.uploader-list')]
          .some(node => (node.textContent || '').includes(target)),
        targetUiRows: [...document.querySelectorAll('[title], span')]
          .filter(node => node.getAttribute('title') === target || (node.children.length === 0 && node.textContent?.trim() === target))
          .map(node => {
            const row = node.closest('.file-list');
            return {
              className: node.parentElement?.className || '',
              text: node.parentElement?.parentElement?.innerText?.slice(0, 500) || '',
              rowClassName: row?.className || '',
              rowText: row?.innerText?.slice(0, 500) || '',
              rowControls: row ? [...row.querySelectorAll('[title], [aria-label], button, a')]
                .filter(element => visible(element))
                .map(element => ({
                  title: (element.getAttribute('title') || '').slice(0, 150),
                  label: (element.getAttribute('aria-label') || '').slice(0, 150),
                  text: (element.innerText || '').slice(0, 150),
                  className: String(element.className || '').slice(0, 150),
                })).slice(0, 12) : [],
              progressWidths: row ? [...row.querySelectorAll('[style]')]
                .map(element => element.style.width)
                .filter(width => /^[0-9]+(?:[.][0-9]+)?%$/.test(width)).slice(0, 10) : [],
            };
          }),
        transferQueue: (() => {
          const panels = [...document.querySelectorAll('.uploader-list')];
          const panel = panels.length === 1 ? panels[0] : null;
          const rows = panel ? [...panel.querySelectorAll('.file-list')] : [];
          return {
            panelAncestors: (() => {
              const ancestors = [];
              let node = panel;
              while (node && node !== document.body && ancestors.length < 6) {
                ancestors.push({tag: node.tagName, className: String(node.className || '').slice(0, 150)});
                node = node.parentElement;
              }
              return ancestors;
            })(),
            complete: !!panel && panel.clientHeight > 0
              && panel.scrollHeight <= panel.clientHeight + 2
              && (panel.innerText || '').includes('仅展示本次上传任务'),
            rowCount: rows.length,
            successfulCount: rows.filter(node => node.classList.contains('status-success')).length,
            targetCount: rows.filter(node => (node.textContent || '').includes(target)).length,
            controls: panel ? [...(panel.parentElement?.parentElement || panel)
              .querySelectorAll('[title], [aria-label], button, a')]
              .filter(node => visible(node) && !node.closest('.file-list'))
              .map(node => ({
                title: (node.getAttribute('title') || '').slice(0, 100),
                label: (node.getAttribute('aria-label') || '').slice(0, 100),
                text: (node.innerText || '').slice(0, 100),
                className: String(node.className || '').slice(0, 100),
              })).slice(0, 20) : [],
          };
        })(),
      },
    };
  })()`));
  if (!inspection || typeof inspection !== 'object') {
    throw new CommandExecutionError('Baidu Netdisk returned a malformed folder inspection');
  }
  if (inspection.authenticated !== true) {
    process.stderr.write(JSON.stringify({kind: 'xiaocao_upload_folder_failure',
      claimId: input.claimId, folderBound: inspection.folderBound === true,
      errno: Number.isInteger(inspection.errno) ? inspection.errno : null,
      completeScan: inspection.completeScan === true}) + '\n');
    throw new AuthRequiredError('pan.baidu.com', 'Baidu Netdisk login is required before upload');
  }
  if (inspection.folderBound !== true) {
    throw new CommandExecutionError('OpenCLI is not bound to the requested Baidu Netdisk folder');
  }
  if (inspection.completeScan !== true) {
    throw new CommandExecutionError('Baidu Netdisk inspection did not scan the complete folder');
  }
  if (!Number.isInteger(inspection.exactCount) || inspection.exactCount < 0) {
    throw new CommandExecutionError('Baidu Netdisk returned an invalid exact-name count');
  }
  if (inspection.exactCount > 1) {
    throw new CommandExecutionError('Baidu Netdisk target basename is ambiguous');
  }
  return inspection;
}

async function markUploadInput(page, input) {
  const marked = await page.evaluate(`(() => {
    const dir = ${JSON.stringify(input.directory)};
    const claim = ${JSON.stringify(input.claimId)};
    const folderBound = () => {
      const currentUrl = new URL(location.href);
      const hashQuery = currentUrl.hash.includes('?')
        ? currentUrl.hash.slice(currentUrl.hash.indexOf('?') + 1)
        : '';
      return currentUrl.origin === 'https://pan.baidu.com'
        && currentUrl.pathname === '/disk/main'
        && new URLSearchParams(hashQuery).get('path') === dir;
    };
    if (!folderBound()) return {marked: false, reason: 'wrong_folder'};
    const inputs = [...document.querySelectorAll(${JSON.stringify(UPLOAD_INPUT)})]
      .filter((node) => !node.hasAttribute('webkitdirectory'));
    if (inputs.length < 1) return {marked: false, reason: 'input_missing'};
    document.querySelectorAll('[data-opencli-baidu-upload-claim]')
      .forEach((node) => node.removeAttribute('data-opencli-baidu-upload-claim'));
    const uploadInput = inputs[0];
    uploadInput.setAttribute('data-opencli-baidu-upload-claim', claim);
    const recordReceipt = () => {
      if (!folderBound()) return;
      window.__opencliBaiduUploadReceipt = {
        claim,
        fileNames: [...(uploadInput.files || [])].map((file) => file.name || ''),
      };
    };
    uploadInput.addEventListener('input', recordReceipt, {capture: true, once: true});
    uploadInput.addEventListener('change', recordReceipt, {capture: true, once: true});
    const blockWrongFolder = (event) => {
      if (folderBound()) return;
      uploadInput.value = '';
      uploadInput.removeAttribute('data-opencli-baidu-upload-claim');
      event.stopImmediatePropagation();
    };
    uploadInput.addEventListener('input', blockWrongFolder, {capture: true, once: true});
    uploadInput.addEventListener('change', blockWrongFolder, {capture: true, once: true});
    window.addEventListener('hashchange', () => {
      uploadInput.removeAttribute('data-opencli-baidu-upload-claim');
      uploadInput.value = '';
    }, {once: true});
    return {marked: true, matches: 1};
  })()`);
  if (!marked || marked.marked !== true || marked.matches !== 1) {
    throw new CommandExecutionError('Could not bind one Baidu Netdisk upload input to the claimed folder');
  }
  return `input[data-opencli-baidu-upload-claim="${input.claimId}"]`;
}

async function activateUploadPage(page) {
  // A native click on the file-name header is harmless (sort only) and gives
  // Chromium the user activation required to open its native file chooser.
  const marked = await page.evaluate(`(() => {
    const headers = [...document.querySelectorAll('span')].filter(node => {
      const rect = node.getBoundingClientRect();
      return node.children.length === 0 && node.textContent.trim() === '文件名'
        && rect.width > 0 && rect.height > 0;
    });
    if (headers.length !== 1) return false;
    headers[0].setAttribute('data-opencli-baidu-upload-activation', 'true');
    return true;
  })()`);
  if (marked !== true || !page.click) {
    throw new CommandExecutionError('Upload activation header is not uniquely available');
  }
  await page.click('[data-opencli-baidu-upload-activation="true"]');
  const state = await page.evaluate(`(() => ({
    userActive: navigator.userActivation?.isActive === true,
    focused: document.hasFocus(), visibility: document.visibilityState,
  }))()`);
  if (state?.userActive !== true) {
    throw new CommandExecutionError('Native upload-page click did not establish user activation');
  }
  return state;
}

async function recoverStalledTransfer(page, input, inspection, {continueOnly = false} = {}) {
  const surface = inspection.surfaceState;
  const row = surface?.targetUiRows?.length === 1 ? surface.targetUiRows[0] : null;
  if (!surface?.transferQueue?.complete || surface.transferQueue.rowCount !== 1
      || surface.transferQueue.targetCount !== 1 || surface.transferQueue.successfulCount !== 0
      || !(continueOnly
        ? row?.rowClassName?.split(' ').some(value => value === 'status-pause' || value === 'status-paused')
        : row?.rowClassName?.split(' ').includes('status-uploading'))
      || !row.progressWidths?.length || !row.progressWidths.every(width => /^0(?:\.0+)?%$/.test(width))
      || !/(?:^|\n)0B\/s(?:$|\n)/.test(row.rowText || '')) {
    throw new CommandExecutionError('Same-queue recovery requires one running zero-progress target');
  }
  const controlState = async (markTitle = '') => page.evaluate(`(() => {
    const target = ${JSON.stringify(input.targetName)};
    const title = ${JSON.stringify(markTitle)};
    const claim = ${JSON.stringify(input.claimId)};
    const dir = ${JSON.stringify(input.directory)};
    const current = new URL(location.href);
    const query = current.hash.slice(current.hash.indexOf('?') + 1);
    if (current.origin !== 'https://pan.baidu.com' || current.pathname !== '/disk/main'
        || new URLSearchParams(query).get('path') !== dir) return null;
    const visible = node => {
      const rect = node.getBoundingClientRect(); const style = getComputedStyle(node);
      return rect.width > 0 && rect.height > 0 && style.display !== 'none'
        && style.visibility !== 'hidden' && Number(style.opacity) !== 0;
    };
    const panels = [...document.querySelectorAll('.uploader-list')];
    if (panels.length !== 1) return null;
    if (panels[0].clientHeight <= 0 || panels[0].scrollHeight > panels[0].clientHeight + 2
        || !(panels[0].innerText || '').includes('仅展示本次上传任务')) return null;
    const rows = [...panels[0].querySelectorAll('.file-list')];
    if (rows.length !== 1) return null;
    const row = rows[0];
    const names = [...row.querySelectorAll('[title]')].filter(node => node.title === target);
    if (names.length !== 1 || !visible(names[0])) return null;
    const controls = [...row.querySelectorAll('[title]')].filter(visible);
    const pause = controls.filter(node => node.title === '暂停');
    const resume = controls.filter(node => node.title === '继续上传' || node.title === '继续' || node.title === '开始');
    const widths = [...row.querySelectorAll('[style]')].map(node => node.style.width)
      .filter(width => /^[0-9]+(?:[.][0-9]+)?%$/.test(width));
    const zero = widths.length > 0 && widths.every(width => /^0(?:[.]0+)?%$/.test(width))
      && (row.innerText || '').split(String.fromCharCode(10)).includes('0B/s');
    const paused = row.classList.contains('status-pause') || row.classList.contains('status-paused');
    const failed = row.classList.contains('status-error') || row.classList.contains('status-failed')
      || row.classList.contains('status-success');
    if (title) {
      if (title === '暂停' && (!zero || failed)) return null;
      if (title !== '暂停' && (!paused || failed || (${JSON.stringify(continueOnly)} && !zero))) return null;
      const match = controls.filter(node => node.title === title);
      if (match.length !== 1) return null;
      row.querySelectorAll('[data-xiaocao-transfer-recovery]').forEach(node =>
        node.removeAttribute('data-xiaocao-transfer-recovery'));
      match[0].setAttribute('data-xiaocao-transfer-recovery', claim);
    }
    return {pauseCount: pause.length, resumeCount: resume.length,
      resumeTitle: resume.length === 1 ? resume[0].title : '',
      uploading: row.classList.contains('status-uploading'), paused, failed, zero, marked: !!title};
  })()`);
  const selector = `[data-xiaocao-transfer-recovery="${input.claimId}"]`;
  const waitState = async (paused) => {
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
      const state = await controlState();
      if (state && (paused
        ? state.pauseCount === 0 && state.resumeCount === 1 && !state.uploading && state.paused && !state.failed
        : state.pauseCount === 1 && state.resumeCount === 0 && state.uploading && !state.paused && !state.failed)) return state;
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    throw new CommandExecutionError('Same-queue recovery state did not match; do not repeat');
  };
  let paused;
  if (continueOnly) {
    paused = await uploadStage(input, 'repair_existing_pause_readback', () => waitState(true));
  } else {
    const pause = await controlState('暂停');
    if (!pause?.marked || pause.pauseCount !== 1 || pause.resumeCount !== 0 || !pause.uploading
        || !pause.zero || pause.paused || pause.failed) {
      throw new CommandExecutionError('Exact running upload pause control is unavailable');
    }
    await uploadStage(input, 'repair_pause', () => page.click(selector));
    paused = await uploadStage(input, 'repair_pause_readback', () => waitState(true));
  }
  const resume = await controlState(paused.resumeTitle);
  if (!resume?.marked || resume.resumeCount !== 1 || resume.pauseCount !== 0 || resume.uploading
      || !resume.paused || resume.failed || (continueOnly && !resume.zero)) {
    throw new CommandExecutionError('Exact paused upload continue control is unavailable');
  }
  await uploadStage(input, 'repair_resume', () => page.click(selector));
  await uploadStage(input, 'repair_resume_readback', () => waitState(false));
  return [{status: 'existing_upload_resumed', directory: input.directory,
    targetName: input.targetName, claimId: input.claimId, uploaded: false,
    pausedReadback: true, resumedReadback: true}];
}

cli({
  site: 'baidu-netdisk',
  name: 'upload',
  description: 'Upload one durable-claimed local file to an exact Baidu Netdisk folder with exact-name reconciliation',
  access: 'write',
  example: 'opencli baidu-netdisk upload --file /abs/video.mp4 --target-name video.mp4 --claim-id job-12345678 -f json',
  domain: 'pan.baidu.com',
  strategy: Strategy.UI,
  browser: true,
  siteSession: 'persistent',
  defaultWindowMode: 'foreground',
  navigateBefore: false,
  args: [
    { name: 'file', required: true, help: 'Absolute local file path already bound to a durable claim' },
    { name: 'directory', default: DEFAULT_DIRECTORY, help: 'Exact Baidu Netdisk destination directory' },
    { name: 'target-name', required: true, help: 'Exact destination basename; must equal the local basename' },
    { name: 'claim-id', required: true, help: 'Durable upload claim identifier from the caller ledger' },
    { name: 'inspect-only', type: 'boolean', default: false, help: 'Stop after exact folder/name inspection without attaching a file' },
    { name: 'repair-stalled', type: 'boolean', default: false, help: 'One caller-claimed pause/readback/continue of the retained stalled transfer; never attach a file' },
    { name: 'continue-stalled', type: 'boolean', default: false, help: 'Finish one caller-claimed recovery from the exact paused transfer; never pause or attach' },
    { name: 'activate-only', type: 'boolean', default: false, help: 'Check native page activation without attaching a file' },
    { name: 'timeout', type: 'int', default: 60, help: 'Transport deadline in seconds; shared with the runtime deadline' },
  ],
  columns: [
    'status',
    'directory',
    'targetName',
    'exactCountBefore',
    'uploaded',
    'uploadTarget',
    'claimId',
    'url',
  ],
  func: async (page, kwargs) => {
    const input = normalizeInput(kwargs);
    const recovery = kwargs['repair-stalled'] === true || kwargs['continue-stalled'] === true;
    if (recovery && (kwargs['inspect-only'] === true || kwargs['activate-only'] === true
        || (kwargs['repair-stalled'] === true && kwargs['continue-stalled'] === true))) {
      throw new ArgumentError('Same-queue repair cannot be combined with inspection or activation');
    }
    const inspection = await inspectTarget(page, input, {
      retainPage: kwargs['inspect-only'] === true || recovery,
    });
    if (recovery) {
      if (inspection.exactCount !== 0) {
        throw new CommandExecutionError('Cloud target already exists; do not recover its upload');
      }
      return recoverStalledTransfer(page, input, inspection, {continueOnly: kwargs['continue-stalled'] === true});
    }
    if (inspection.exactCount === 1) {
      return [{
        status: 'already_present',
        directory: input.directory,
        targetName: input.targetName,
        exactCountBefore: 1,
        uploaded: false,
        uploadTarget: '',
        claimId: input.claimId,
        url: inspection.url,
        surfaceState: inspection.surfaceState,
      }];
    }
    if (kwargs['inspect-only'] === true) {
      return [{
        status: 'ready_to_upload',
        directory: input.directory,
        targetName: input.targetName,
        exactCountBefore: 0,
        uploaded: false,
        uploadTarget: '',
        claimId: input.claimId,
        url: inspection.url,
        surfaceState: inspection.surfaceState,
      }];
    }
    if (!page.uploadFiles) {
      throw new CommandExecutionError('OpenCLI Browser Bridge uploadFiles support is required');
    }
    const selector = await uploadStage(input, 'mark_input', () => markUploadInput(page, input));
    const activation = await uploadStage(input, 'activate', () => activateUploadPage(page));
    if (kwargs['activate-only'] === true) {
      return [{status: 'activation_verified', claimId: input.claimId, uploaded: false, activation}];
    }
    const upload = await uploadStage(input, 'attach', () => page.uploadFiles(selector, [input.file], {nth: 0}));
    if (!upload || upload.uploaded !== true || upload.files !== 1) {
      throw new CommandExecutionError('Baidu Netdisk did not confirm exactly one uploaded file');
    }
    const uploadedNames = Array.isArray(upload.file_names) ? upload.file_names : [];
    const captured = await uploadStage(input, 'receipt', () => page.evaluate(`(() => {
      const value = window.__opencliBaiduUploadReceipt;
      delete window.__opencliBaiduUploadReceipt;
      return value || null;
    })()`));
    const capturedNames = Array.isArray(captured?.fileNames) ? captured.fileNames : [];
    if (upload.target !== selector || upload.matches_n !== 1
        || captured?.claim !== input.claimId
        || (!uploadedNames.includes(input.targetName)
          && !capturedNames.includes(input.targetName))) {
      throw new CommandExecutionError('Baidu Netdisk upload receipt does not match the claimed input and basename');
    }
    return [{
      status: 'upload_submitted',
      directory: input.directory,
      targetName: input.targetName,
      exactCountBefore: 0,
      uploaded: true,
      uploadTarget: upload.target,
      claimId: input.claimId,
      url: inspection.url,
    }];
  },
});
