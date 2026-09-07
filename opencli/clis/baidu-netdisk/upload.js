import { cli, Strategy } from '@jackwener/opencli/registry';
import { execFileSync } from 'node:child_process';
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
    visibility: document.visibilityState, url: location.href,
    x: screenX, y: screenY, w: outerWidth, h: outerHeight
  })`));
  if (state?.visibility !== 'hidden') return;
  if (process.platform !== 'darwin' || ![state.x, state.y, state.w, state.h].every(Number.isFinite)) {
    throw new CommandExecutionError('Hidden uploader requires exact Edge window restoration');
  }
  // Native window activation only: no navigation, reload, profile changes,
  // webpage scripting, or file chooser. Geometry + full URL must match once.
  const script = `on run argv
    set expectedBounds to {(item 1 of argv as integer), (item 2 of argv as integer), (item 3 of argv as integer), (item 4 of argv as integer)}
    set expectedURL to item 5 of argv
    tell application "Microsoft Edge"
      set candidates to {}
      repeat with w in windows
        if bounds of w is expectedBounds then
          repeat with i from 1 to count of tabs of w
            if URL of tab i of w is expectedURL then set end of candidates to {(id of w as integer), i, (id of tab i of w as text)}
          end repeat
        end if
      end repeat
      if count of candidates is not 1 then error "Exact uploader window is missing or ambiguous"
      set chosen to item 1 of candidates
      set w to window id (item 1 of chosen)
      set tabIndex to item 2 of chosen
      if (id of tab tabIndex of w as text) is not item 3 of chosen then error "Uploader tab changed"
      if URL of tab tabIndex of w is not expectedURL then error "Uploader URL changed"
      set active tab index of w to tabIndex
      set index of w to 1
      activate
    end tell
    return "foreground_requested"
  end run`;
  await uploadStage(input, 'foreground', async () => {
    try {
      execFileSync('/usr/bin/osascript', ['-e', script,
        String(Math.round(state.x)), String(Math.round(state.y)),
        String(Math.round(state.x + state.w)), String(Math.round(state.y + state.h)), state.url,
      ], {encoding: 'utf8', timeout: 10000});
    } catch {
      throw new CommandExecutionError('Exact Edge uploader window restoration failed; no file attached');
    }
  });
  // Visibility alone is insufficient: background pages can still be healthy.
  // Prove the task queue actually resumed before issuing network/file work.
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
          .map(node => ({className: node.parentElement?.className || '', text: node.parentElement?.parentElement?.innerText?.slice(0, 500) || ''})),
        transferQueue: (() => {
          const panels = [...document.querySelectorAll('.uploader-list')];
          const panel = panels.length === 1 ? panels[0] : null;
          const rows = panel ? [...panel.querySelectorAll('.file-list')] : [];
          return {
            complete: !!panel && panel.clientHeight > 0
              && panel.scrollHeight <= panel.clientHeight + 2
              && (panel.innerText || '').includes('仅展示本次上传任务'),
            rowCount: rows.length,
            successfulCount: rows.filter(node => node.classList.contains('status-success')).length,
            targetCount: rows.filter(node => (node.textContent || '').includes(target)).length,
          };
        })(),
      },
    };
  })()`));
  if (!inspection || typeof inspection !== 'object') {
    throw new CommandExecutionError('Baidu Netdisk returned a malformed folder inspection');
  }
  if (inspection.authenticated !== true) {
    throw new AuthRequiredError('Baidu Netdisk login is required before upload');
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
    const inspection = await inspectTarget(page, input, {retainPage: kwargs['inspect-only'] === true});
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
