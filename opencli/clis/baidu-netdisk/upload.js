import { cli, Strategy } from '@jackwener/opencli/registry';
import {
  ArgumentError,
  AuthRequiredError,
  CommandExecutionError,
} from '@jackwener/opencli/errors';

const DEFAULT_DIRECTORY = '/课程/自己的课/小草';
const UPLOAD_INPUT = 'input[type="file"][title="点击选择文件"][accept="*/*"]';

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

async function inspectTarget(page, input) {
  const folderUrl = 'https://pan.baidu.com/disk/main#/index?category=all&path='
    + encodeURIComponent(input.directory);
  await page.goto(folderUrl, { waitUntil: 'load', settleMs: 1500 });
  await page.wait({ time: 1 });
  const inspection = await page.evaluate(`(async () => {
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
    const adPattern = /广告|运营图片|限时特惠|下载客户端|开通\\s*(?:SVIP|超级会员)|SVIP\\s*(?:活动|特惠|优惠)/i;
    const overlays = [...document.querySelectorAll([
      '.nd-operate-guidance',
      '[role="dialog"]',
      '[class*="modal"]',
      '[class*="popup"]',
      '[class*="advert"]',
      '[class*="promotion"]',
      '[class*="pay-revolution"]',
      '[class*="vip-dialog"]',
    ].join(','))];
    for (const overlay of overlays) {
      const identity = [
        overlay.className || '',
        (overlay.innerText || '').trim(),
        ...[...overlay.querySelectorAll('img')].map(
          (node) => (node.getAttribute('alt') || '') + ' ' + (node.className || '')
        ),
      ].join(' ');
      if (!visible(overlay) || !adPattern.test(identity)) continue;
      const close = [...overlay.querySelectorAll(
        'button,[role="button"],[aria-label],[title],[class*="close"],img[alt="close"]'
      )].find((node) => {
        const label = [
          node.getAttribute('aria-label') || '',
          node.getAttribute('title') || '',
          node.getAttribute('alt') || '',
          node.className || '',
          (node.textContent || '').trim(),
        ].join(' ');
        return visible(node) && /关闭|close|×|^x$/i.test(label);
      });
      if (close) {
        close.click();
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      if (document.contains(overlay) && visible(overlay)) {
        overlay.style.setProperty('display', 'none', 'important');
        overlay.setAttribute('aria-hidden', 'true');
      }
    }
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
      const response = await fetch(url, {credentials: 'include'});
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
    };
  })()`);
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
    const inspection = await inspectTarget(page, input);
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
      }];
    }
    if (!page.uploadFiles) {
      throw new CommandExecutionError('OpenCLI Browser Bridge uploadFiles support is required');
    }
    const selector = await markUploadInput(page, input);
    const upload = await page.uploadFiles(selector, [input.file], {nth: 0});
    if (!upload || upload.uploaded !== true || upload.files !== 1) {
      throw new CommandExecutionError('Baidu Netdisk did not confirm exactly one uploaded file');
    }
    const uploadedNames = Array.isArray(upload.file_names) ? upload.file_names : [];
    const captured = await page.evaluate(`(() => {
      const value = window.__opencliBaiduUploadReceipt;
      delete window.__opencliBaiduUploadReceipt;
      return value || null;
    })()`);
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
