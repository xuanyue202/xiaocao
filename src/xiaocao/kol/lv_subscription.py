"""Browser-backed Lv Xiaotong subscription intake for Ticket 04."""

from __future__ import annotations

import fcntl
import functools
import hashlib
import json
import re
import select
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from ._shared import DecisionError
from .claim_coverage import (
    build_claim_extraction_request,
    validate_claim_coverage,
)
from .author_profiles import semantic_author_profile
from .enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
    validate_decision_completion,
    validate_decision_process_result,
)
from .semantic_bundle import read_validated_bundle, validate_receipt_bindings
from .netdisk_opencli_templates import NetdiskOpenCliTemplate


IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}
TEXT_SUFFIXES = {".md", ".txt"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SMALL_MEDIA = {"image", "text", "pdf"}
MAX_SMALL_EVIDENCE_BYTES = 50 * 1024 * 1024
_DISCOVERY_HOT_WINDOW = timedelta(days=14)
_DISCOVERY_HOT_ROOT_LIMIT = 3
MAX_PDF_PAGES = 200
PDF_BOOTSTRAP_WINDOW_SECONDS = 24 * 60 * 60
MIN_NATIVE_PDF_PAGE_TEXT = 20
PDF_DOCUMENT_ROLES = {"independent_report", "video_summary", "unknown"}
PDF_PRIMARY_SOURCE_STATUSES = {
    "complete",
    "unavailable",
    "incomplete",
    "pending",
    "not_applicable",
}
LV_CONTENT_PRODUCTS = {
    "member_livestream",
    "underlying_logic",
    "hybrid",
    "unknown",
}
_OPENCLI_NAME = re.compile(r"[A-Za-z0-9_.-]{1,80}")
_OPENCLI_SCRIPT_OPERATION = re.compile(
    r"\boperation\s*=\s*['\"]([a-z][a-z0-9_]{0,63})['\"]"
)
_COVERAGE_ROWS = {
    "todays_market_diagnosis",
    "next_session_playbook",
    "next_several_session_base_case",
    "style_market_cap_regime",
    "market_board_sector_hierarchy",
    "position_risk_budget",
    "named_asset_inventory",
}
_DOWNLOAD_PRETRIGGER_FAILURES = {
    "wrong_share",
    "target_path_mismatch",
    "target_not_visible",
    "target_not_unique",
    "selection_control_missing",
    "selection_mismatch",
    "download_control_ambiguous",
    "download_confirmation_click_failed",
    "provider_file_id_invalid",
    "share_download_metadata_missing",
    "share_download_failed",
    "share_download_link_missing",
    "share_download_target_mismatch",
}
_SAFE_OPENCLI_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_OPENCLI_ERROR_CATEGORIES = {
    "download_not_seen": "uncertain_state",
    "selector_ambiguous": "interaction_error",
    "target_not_found": "interaction_error",
    "session_not_found": "session_error",
}

_DIRECT_DOWNLOAD_MEDIA = {"image", "pdf", "text"}
_DIRECT_DOWNLOAD_HOSTS = {"d.pcs.baidu.com"}
_PREVIEW_DOWNLOAD_HOST = re.compile(r"thumbnail\d*\.baidupcs\.com")
MIN_PREVIEW_SHORT_EDGE = 256
MIN_PREVIEW_LONG_EDGE = 512
_READ_ONLY_ROUTE_REBIND_ATTEMPTS = 3
_READ_ONLY_LISTING_ATTEMPTS = 3
_PROVIDER_LINK_OWNER_CLOUD_FALLBACK_CODES = {
    "detached_mid_command",
    "opencli_command_failed",
    "opencli_timeout",
}


def _valid_preview_dimensions(width: int, height: int) -> bool:
    """Accept evidence-sized landscape and portrait preview derivatives."""

    return (
        min(width, height) >= MIN_PREVIEW_SHORT_EDGE
        and max(width, height) >= MIN_PREVIEW_LONG_EDGE
    )


def _subscription_decision_pipeline_error(exc: Exception) -> EnrichmentError:
    """Preserve the safe provider boundary for household-context failures."""

    if isinstance(exc, DecisionError) and str(exc) == "亮灰 MCP request failed":
        return EnrichmentDiagnosticError(
            "household context provider is temporarily unavailable",
            category="provider_error",
            code="lianghui_mcp_request_failed",
            stage="household_context",
        )
    if isinstance(exc, EnrichmentError):
        return exc
    return EnrichmentError("subscription decision pipeline failed")


BLOCKED_DOWNLOAD_PROVIDER_CONTRACT_VERSION = "baidu_netdisk_download_v1"
_DIRECT_DOWNLOAD_PATHS = {"/rest/2.0/pcs/file"}
_DIRECT_DOWNLOAD_CONTENT_TYPES = {
    "image": {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/octet-stream",
        "application/x-download",
        "binary/octet-stream",
    },
    "pdf": {
        "application/pdf",
        "application/octet-stream",
        "application/x-download",
        "binary/octet-stream",
    },
    "text": {
        "text/plain",
        "text/markdown",
        "application/octet-stream",
        "application/x-download",
        "binary/octet-stream",
    },
}
_UI_DIRECT_DOWNLOAD_MEDIA = {"pdf", "text"}
_OWNER_CLOUD_ROOT = PurePosixPath("/xiaocao/lv_subscription")
_HISTORICAL_RETIREMENT_PATH = Path(__file__).with_name(
    "lv_historical_retirement_20260808.json"
)


def _is_supported_baidu_download_path(path: str) -> bool:
    return path.startswith("/file/") or path in _DIRECT_DOWNLOAD_PATHS


_BROWSER_LISTING_SCRIPT_TEMPLATE = r"""(async () => {
  const fail = (status, diagnostic = {}) => ({
    status,
    entries: [],
    diagnostic
  });
  const expectedPath = __EXPECTED_PATH_JSON__;
  const configuredRecursiveRoots = __RECURSIVE_ROOTS_JSON__;
  const knownRootDirectories = new Set(__KNOWN_ROOTS_JSON__);
  const discoveryRoots = new Set(__DISCOVERY_ROOTS_JSON__);
  const activeRecursiveRoots = new Set(
    Array.isArray(configuredRecursiveRoots) ? configuredRecursiveRoots : []
  );
  if (location.origin !== 'https://pan.baidu.com') {
    return fail('wrong_origin');
  }
  if (location.pathname === '/share/init') {
    return fail('authorization_required');
  }
  if (location.pathname !== expectedPath) {
    return fail('wrong_share');
  }
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const exactExpiredMessages = new Set([
    '分享已失效',
    '该分享已失效',
    '分享的文件已失效',
    '分享的文件已经被取消了',
    '分享的文件已经被删除了'
  ]);
  const terminalTexts = [...document.querySelectorAll(
    '[role="alert"], .share-error, .error-msg, .error-message, '
    + '[class*="share-error"], [class*="expire"]'
  )].filter(visible).map(node => (
    String(node.innerText || node.textContent || '')
      .replace(/\s+/g, ' ').trim()
  ));
  if (terminalTexts.some(text => exactExpiredMessages.has(text))) {
    return fail('share_expired', {basis: 'exact_visible_terminal'});
  }
  const observedListUrls = () => performance.getEntriesByType('resource')
    .map(entry => String(entry.name || ''))
    .filter(name => {
      try {
        const parsed = new URL(name);
        return parsed.origin === 'https://pan.baidu.com'
          && parsed.pathname === '/share/list';
      } catch (_error) {
        return false;
      }
    });
  let rootTemplate = observedListUrls().find(name => {
    const parsed = new URL(name);
    return parsed.searchParams.get('root') === '1'
      && parsed.searchParams.has('shorturl');
  });
  if (!rootTemplate) {
    const rootDeadline = Date.now() + 10000;
    while (Date.now() < rootDeadline && !rootTemplate) {
      await new Promise(resolve => setTimeout(resolve, 100));
      rootTemplate = observedListUrls().find(name => {
        const parsed = new URL(name);
        return parsed.searchParams.get('root') === '1'
          && parsed.searchParams.has('shorturl');
      });
    }
  }
  if (!rootTemplate) {
    return fail('share_root_template_missing');
  }
  const entries = [];
  const pendingDirs = [];
  const seenDirs = new Set();
  const appendItem = item => {
    const name = String(item.server_filename || item.filename || '');
    const path = String(item.path || ('/' + name));
    const isDir = item.isdir === 1
      || item.isdir === true
      || String(item.isdir) === '1';
    entries.push({
      provider_file_id: String(item.fs_id || item.fsid || ''),
      path,
      name,
      is_dir: isDir,
      size: Number(item.size || 0),
      uploaded_at: Number(
        item.server_ctime || item.local_ctime || item.ctime || 0
      ),
      modified_at: Number(
        item.server_mtime || item.local_mtime || item.mtime || 0
      )
    });
    const slash = path.lastIndexOf('/');
    const parent = slash > 0 ? path.slice(0, slash) : '/';
    const isDiscoveryChild = discoveryRoots.size === 0
      ? parent === '/'
      : discoveryRoots.has(parent);
    if (isDiscoveryChild && !knownRootDirectories.has(path)) {
      activeRecursiveRoots.add(path);
    }
    const shouldRecurse = configuredRecursiveRoots === null
      || discoveryRoots.has(path)
      || [...activeRecursiveRoots].some(root => (
        path === root || path.startsWith(root + '/')
      ));
    if (isDir && shouldRecurse && !seenDirs.has(path)) {
      seenDirs.add(path);
      pendingDirs.push(path);
    }
  };
  const maxDirectories = 100;
  const maxItems = 5000;
  const maxConcurrentDirectories = 4;
  const requestTimeoutMs = 10000;
  const readPages = async (template, dir) => {
    const parsed = new URL(template);
    const pageSize = Math.max(1, Number(parsed.searchParams.get('num') || 100));
    const collected = [];
    let page = 1;
    while (page <= 100) {
      parsed.searchParams.set('page', String(page));
      if (dir !== null) {
        parsed.searchParams.set('dir', String(dir));
      }
      const controller = new AbortController();
      const timeout = setTimeout(
        () => controller.abort(),
        requestTimeoutMs
      );
      let response;
      try {
        response = await fetch(parsed.toString(), {
          credentials: 'include',
          signal: controller.signal
        });
      } catch (error) {
        return {
          status: error && error.name === 'AbortError'
            ? 'share_list_timeout'
            : 'share_list_failed',
          rows: []
        };
      } finally {
        clearTimeout(timeout);
      }
      let body;
      let rawBody;
      try {
        rawBody = await response.text();
        body = JSON.parse(rawBody);
      } catch (error) {
        const match = String(error && error.message || '')
          .match(/position\s+(\d+)/i);
        return {
          status: 'share_list_invalid_json',
          rows: [],
          diagnostic: {
            http_status: Number(response.status || 0),
            content_type: String(
              response.headers.get('content-type') || ''
            ).slice(0, 96),
            body_length: String(rawBody || '').length,
            json_error_position: match ? Number(match[1]) : null
          }
        };
      }
      if (!response.ok || body.errno !== 0) {
        const providerMessage = String(
          body.errmsg || body.show_msg || body.error_msg || ''
        ).replace(/\s+/g, ' ').trim();
        const expiredMessages = new Set([
          '分享的文件已经被取消了',
          '分享的文件已经被删除了',
          '该分享已失效'
        ]);
        return {
          status: expiredMessages.has(providerMessage)
            ? 'share_expired'
            : 'share_list_failed',
          rows: [],
          diagnostic: {
            http_status: Number(response.status || 0),
            provider_errno: Number(body.errno || 0)
          }
        };
      }
      const rows = Array.isArray(body.list) ? body.list : [];
      collected.push(...rows);
      if (
        rows.length === 0
        || (body.has_more !== 1 && body.has_more !== true
          && rows.length < pageSize)
      ) {
        break;
      }
      page += 1;
    }
    return {status: 'ok', rows: collected};
  };
  const rootResult = await readPages(rootTemplate, null);
  if (rootResult.status !== 'ok') {
    return fail(rootResult.status, rootResult.diagnostic || {});
  }
  rootResult.rows.forEach(appendItem);
  let directoryTemplate = observedListUrls().find(name => {
    const parsed = new URL(name);
    return parsed.searchParams.has('dir')
      && parsed.searchParams.has('sekey')
      && parsed.searchParams.has('shareid')
      && parsed.searchParams.has('uk');
  });
  if (pendingDirs.length > 0 && !directoryTemplate) {
    location.hash = 'list/path=' + encodeURIComponent(pendingDirs[0]);
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline && !directoryTemplate) {
      await new Promise(resolve => setTimeout(resolve, 100));
      directoryTemplate = observedListUrls().find(name => {
        const parsed = new URL(name);
        return parsed.searchParams.has('dir')
          && parsed.searchParams.has('sekey')
          && parsed.searchParams.has('shareid')
          && parsed.searchParams.has('uk');
      });
    }
  }
  if (pendingDirs.length > 0 && !directoryTemplate) {
    return fail('share_directory_template_missing');
  }
  let scannedDirectories = 0;
  while (pendingDirs.length > 0) {
    if (
      scannedDirectories
        + Math.min(pendingDirs.length, maxConcurrentDirectories)
        > maxDirectories
      || entries.length > maxItems
    ) {
      return fail('listing_bounds_exceeded');
    }
    const batch = pendingDirs.splice(0, maxConcurrentDirectories);
    scannedDirectories += batch.length;
    const directoryResults = await Promise.all(batch.map(async dir => ({
      dir,
      result: await readPages(directoryTemplate, dir)
    })));
    for (const {result} of directoryResults) {
      if (result.status !== 'ok') {
        return fail(result.status, result.diagnostic || {});
      }
      result.rows.forEach(appendItem);
    }
  }
  return {
    status: 'ok',
    entries,
    complete_scan: configuredRecursiveRoots === null,
    coverage: configuredRecursiveRoots === null ? null : {
      direct_roots: ['/', ...discoveryRoots].sort(),
      recursive_roots: [...activeRecursiveRoots].sort(),
      policy: 'hourly_hot_roots_plus_rotating_cold_shard'
    },
    observed_count: entries.length
  };
})()"""


def _browser_listing_script(
    expected_path: str,
    *,
    recursive_roots: list[str] | None = None,
    known_roots: list[str] | None = None,
    discovery_roots: list[str] | None = None,
) -> str:
    return (
        _BROWSER_LISTING_SCRIPT_TEMPLATE.replace(
            "__EXPECTED_PATH_JSON__",
            json.dumps(expected_path),
        )
        .replace("__RECURSIVE_ROOTS_JSON__", json.dumps(recursive_roots))
        .replace("__KNOWN_ROOTS_JSON__", json.dumps(known_roots or []))
        .replace("__DISCOVERY_ROOTS_JSON__", json.dumps(discovery_roots or []))
    )


def _parent_path(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return parent if parent != "." else "/"


def _is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _tiered_share_roots(
    items: Mapping[str, Any], now: datetime
) -> tuple[list[str], list[str], list[str]]:
    rows = [value for value in items.values() if isinstance(value, Mapping)]
    discovery_roots: list[str] = []
    candidate_parent = "/"
    while True:
        directory_children = sorted(
            {
                str(row.get("path") or "")
                for row in rows
                if row.get("is_dir") is True
                and _parent_path(str(row.get("path") or ""))
                == candidate_parent
            }
        )
        if len(directory_children) != 1:
            break
        wrapper = directory_children[0]
        nested_directories = {
            str(row.get("path") or "")
            for row in rows
            if row.get("is_dir") is True
            and _parent_path(str(row.get("path") or "")) == wrapper
        }
        if not nested_directories:
            break
        discovery_roots.append(wrapper)
        candidate_parent = wrapper

    collection_roots = sorted(
        {
            str(row.get("path") or "")
            for row in rows
            if row.get("is_dir") is True
            and _parent_path(str(row.get("path") or "")) == candidate_parent
        }
    )
    if len(collection_roots) > 1:
        discovery_roots.extend(collection_roots)
        candidate_parents = set(collection_roots)
    else:
        candidate_parents = {candidate_parent}

    activities: dict[str, int] = {}
    known = {
        str(row.get("path") or "")
        for row in rows
        if row.get("is_dir") is True
        and _parent_path(str(row.get("path") or "")) in candidate_parents
    }
    for value in rows:
        path = str(value.get("path") or "")
        containing = [root for root in known if _is_within(path, root)]
        if not containing:
            continue
        try:
            activity = max(
                int(value.get("modified_at") or 0),
                int(value.get("uploaded_at") or 0),
            )
        except (TypeError, ValueError):
            activity = 0
        for root in containing:
            activities[root] = max(activities.get(root, 0), activity)
    ranked = sorted(
        known,
        key=lambda path: (activities.get(path, 0), path),
        reverse=True,
    )
    cutoff = int((now - _DISCOVERY_HOT_WINDOW).timestamp())
    hot = [path for path in ranked if activities.get(path, 0) >= cutoff]
    selected = list(dict.fromkeys([*hot, *ranked[:_DISCOVERY_HOT_ROOT_LIMIT]]))[
        :_DISCOVERY_HOT_ROOT_LIMIT
    ]
    cold = sorted(known.difference(selected))
    if cold:
        selected.append(cold[(int(now.timestamp()) // 3600) % len(cold)])
    return discovery_roots, sorted({*discovery_roots, *known}), selected


def _covered_by_listing(path: str, coverage: Mapping[str, Any]) -> bool:
    recursive = coverage.get("recursive_roots")
    if isinstance(recursive, list) and any(
        _is_within(path, str(root)) for root in recursive
    ):
        return True
    direct = coverage.get("direct_roots")
    return isinstance(direct, list) and _parent_path(path) in {
        str(root) for root in direct
    }


def _authorized_share_url(share_url: str, share_code: str) -> str:
    """Restore Baidu's self-contained share link without persisting it."""
    parsed = urlparse(share_url)
    return parsed._replace(query=urlencode({"pwd": share_code})).geturl()


def _browser_authorization_script(share_code: str) -> str:
    """Create one semantic browser action without logging the credential."""
    return r"""(() => {
  const share_code = %s;
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== '/share/init'
  ) {
    return {status: 'authorization_not_required'};
  }
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const inputs = [...document.querySelectorAll('input')].filter(input => {
    const semantic = [
      input.type,
      input.name,
      input.placeholder,
      input.getAttribute('aria-label')
    ].join(' ');
    return visible(input) && (
      input.type === 'password'
      || semantic.includes('提取码')
      || semantic.includes('访问码')
    );
  });
  const controls = [...document.querySelectorAll('button, [role="button"], a')]
    .filter(control => {
      const text = String(control.innerText || control.textContent || '').trim();
      return visible(control) && (
        text === '提取文件'
        || text === '查看文件'
        || text === '确定'
      );
    });
  if (inputs.length !== 1 || controls.length !== 1) {
    return {
      status: 'authorization_semantics_ambiguous',
      input_count: inputs.length,
      control_count: controls.length
    };
  }
  const input = inputs[0];
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype, 'value'
    ).set;
  setter.call(input, share_code);
  input.dispatchEvent(new Event('input', {bubbles: true}));
  input.dispatchEvent(new Event('change', {bubbles: true}));
  controls[0].click();
  return {status: 'authorization_submitted'};
})()""" % json.dumps(share_code)


_BROWSER_DOWNLOAD_SCRIPT_TEMPLATE = r"""(async () => {
  const operation = 'ticket04_exact_ui_download';
  const fail = status => ({status});
  const expectedSharePath = __EXPECTED_SHARE_PATH_JSON__;
  const expectedItemPath = __EXPECTED_ITEM_PATH_JSON__;
  const expectedName = __EXPECTED_NAME_JSON__;
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== expectedSharePath
  ) {
    return fail('wrong_share');
  }
  if (
    !expectedItemPath.startsWith('/')
    || !expectedItemPath.endsWith('/' + expectedName)
  ) {
    return fail('target_path_mismatch');
  }
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const parentPath = expectedItemPath.slice(
    0, expectedItemPath.length - expectedName.length - 1
  ) || '/';
  location.hash = 'list/path=' + encodeURIComponent(parentPath);
  const targetDeadline = Date.now() + 10000;
  let targets = [];
  while (Date.now() < targetDeadline) {
    targets = Array.from(document.querySelectorAll('#shareqr dd')).filter(row => {
      const filename = row.querySelector('a.filename');
      return filename
        && String(filename.getAttribute('title') || '') === expectedName;
    });
    if (targets.length === 1) {
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (targets.length === 0) {
    return fail('target_not_visible');
  }
  if (targets.length !== 1) {
    return fail('target_not_unique');
  }
  const rows = Array.from(document.querySelectorAll('#shareqr dd'));
  const selectedRows = () => rows.filter(
    row => !row.classList.contains('JS-item-active')
  );
  for (const row of selectedRows()) {
    const control = row.querySelector('span.EOGexf');
    if (!control) {
      return fail('selection_control_missing');
    }
    control.click();
  }
  await new Promise(resolve => setTimeout(resolve, 200));
  const targetControl = targets[0].querySelector('span.EOGexf');
  if (!targetControl) {
    return fail('selection_control_missing');
  }
  targetControl.click();
  await new Promise(resolve => setTimeout(resolve, 200));
  const selected = selectedRows();
  const selectedNames = selected.map(row => {
    const filename = row.querySelector('a.filename');
    return String(filename && filename.getAttribute('title') || '');
  });
  if (selectedNames.length !== 1 || selectedNames[0] !== expectedName) {
    return fail('selection_mismatch');
  }
  const downloadControls = Array.from(
    document.querySelectorAll('a.bottom_download_btn')
  ).filter(visible);
  if (downloadControls.length !== 1) {
    return fail('download_control_ambiguous');
  }
  downloadControls[0].setAttribute('data-xiaocao-download-open', '1');
  return {
    status: 'download_control_ready',
    name: expectedName,
    operation
  };
})()"""


_BROWSER_DOWNLOAD_CONFIRMATION_SCRIPT = r"""(async () => {
  const operation = 'ticket04_download_confirmation_readback';
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const confirmationDeadline = Date.now() + 10000;
  while (Date.now() < confirmationDeadline) {
    const normalDownloads = Array.from(
      document.querySelectorAll('a.g-button')
    ).filter(control => (
      visible(control)
      && String(control.innerText || control.textContent || '').trim()
        === '普通下载'
    ));
    if (normalDownloads.length === 1) {
      normalDownloads[0].setAttribute(
        'data-xiaocao-download-confirmation',
        '1'
      );
      return {
        status: 'download_confirmation_ready',
        operation
      };
    }
    if (normalDownloads.length > 1) {
      return fail('download_confirmation_ambiguous');
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  const clientOnly = Array.from(document.querySelectorAll('a.g-button'))
    .filter(visible)
    .some(control => /安装最新版网盘客户端/.test(
      String(control.innerText || control.textContent || '').trim()
    ));
  return {
    status: clientOnly
      ? 'provider_web_download_client_only'
      : 'download_confirmation_missing',
    operation
  };
})()"""


_FILTERED_IMAGE_PREVIEW_SCRIPT_TEMPLATE = r"""(async () => {
  const operation = 'ticket04_filtered_image_preview_readback';
  const expectedSharePath = __EXPECTED_SHARE_PATH_JSON__;
  const expectedProviderFileId = __EXPECTED_PROVIDER_FILE_ID_JSON__;
  const expectedItemPath = __EXPECTED_ITEM_PATH_JSON__;
  const expectedName = __EXPECTED_NAME_JSON__;
  const minPreviewShortEdge = __MIN_PREVIEW_SHORT_EDGE__;
  const minPreviewLongEdge = __MIN_PREVIEW_LONG_EDGE__;
  const result = (status, extra = {}) => ({status, operation, ...extra});
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== expectedSharePath
    || !/^\d+$/.test(expectedProviderFileId)
    || !expectedItemPath.endsWith('/' + expectedName)
  ) return result('preview_target_invalid');
  const parentPath = expectedItemPath.slice(
    0, expectedItemPath.length - expectedName.length - 1
  ) || '/';
  const prefix = '#list/path=';
  let currentParentPath = '';
  const routeDeadline = Date.now() + 10000;
  while (Date.now() < routeDeadline) {
    try {
      currentParentPath = location.hash.startsWith(prefix)
        ? decodeURIComponent(location.hash.slice(prefix.length)) : '';
    } catch (_error) {
      currentParentPath = '';
    }
    if (currentParentPath === parentPath) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (currentParentPath !== parentPath) {
    return result('preview_parent_mismatch');
  }
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const targetDeadline = Date.now() + 10000;
  let targets = [];
  while (Date.now() < targetDeadline) {
    targets = Array.from(document.querySelectorAll('#shareqr dd')).filter(row => {
      const filename = row.querySelector('a.filename');
      return filename
        && String(filename.getAttribute('title') || '') === expectedName;
    });
    if (targets.length === 1) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (targets.length !== 1) {
    return result(
      targets.length === 0 ? 'preview_target_missing' : 'preview_target_ambiguous'
    );
  }
  const filename = targets[0].querySelector('a.filename');
  if (!filename || !visible(filename)) return result('preview_target_not_visible');
  filename.click();
  const previewDeadline = Date.now() + 15000;
  while (Date.now() < previewDeadline) {
    const candidates = Array.from(document.querySelectorAll('img'))
      .filter(image => {
        const shortEdge = Math.min(image.naturalWidth, image.naturalHeight);
        const longEdge = Math.max(image.naturalWidth, image.naturalHeight);
        if (
          !visible(image)
          || shortEdge < minPreviewShortEdge
          || longEdge < minPreviewLongEdge
        ) {
          return false;
        }
        let url;
        try { url = new URL(String(image.currentSrc || image.src || '')); }
        catch (_error) { return false; }
        const fid = String(url.searchParams.get('fid') || '').split('-').pop();
        return /^thumbnail\d*\.baidupcs\.com$/.test(url.hostname)
          && url.pathname.startsWith('/thumbnail/')
          && fid === expectedProviderFileId;
      });
    if (candidates.length > 1) return result('preview_image_ambiguous');
    if (candidates.length === 1) {
      const image = candidates[0];
      const url = new URL(String(image.currentSrc || image.src || ''));
      return result('preview_ready', {
        download_url: url.href,
        host: url.hostname,
        path: url.pathname,
        provider_file_id: expectedProviderFileId,
        natural_width: Number(image.naturalWidth || 0),
        natural_height: Number(image.naturalHeight || 0)
      });
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return result('preview_image_missing');
})()"""


def _filtered_image_preview_script(
    *,
    expected_share_path: str,
    expected_provider_file_id: str,
    expected_item_path: str,
    expected_name: str,
) -> str:
    return (
        _FILTERED_IMAGE_PREVIEW_SCRIPT_TEMPLATE.replace(
            "__EXPECTED_SHARE_PATH_JSON__", json.dumps(expected_share_path)
        )
        .replace(
            "__EXPECTED_PROVIDER_FILE_ID_JSON__",
            json.dumps(expected_provider_file_id),
        )
        .replace("__EXPECTED_ITEM_PATH_JSON__", json.dumps(expected_item_path))
        .replace("__EXPECTED_NAME_JSON__", json.dumps(expected_name))
        .replace("__MIN_PREVIEW_SHORT_EDGE__", str(MIN_PREVIEW_SHORT_EDGE))
        .replace("__MIN_PREVIEW_LONG_EDGE__", str(MIN_PREVIEW_LONG_EDGE))
    )


def _browser_download_script(
    *,
    expected_share_path: str,
    expected_item_path: str,
    expected_name: str,
) -> str:
    return (
        _BROWSER_DOWNLOAD_SCRIPT_TEMPLATE.replace(
            "__EXPECTED_SHARE_PATH_JSON__",
            json.dumps(expected_share_path),
        )
        .replace("__EXPECTED_ITEM_PATH_JSON__", json.dumps(expected_item_path))
        .replace("__EXPECTED_NAME_JSON__", json.dumps(expected_name))
    )


_PROVIDER_DIRECT_LINK_SCRIPT_TEMPLATE = r"""(async () => {
  const template_name = 'baidu-netdisk/probe-download';
  const template_version = 1;
  const operation = 'ticket04_provider_direct_link';
  const expectedSharePath = __EXPECTED_SHARE_PATH__;
  const expectedProviderFileId = __EXPECTED_PROVIDER_FILE_ID__;
  const expectedItemPath = __EXPECTED_ITEM_PATH__;
  const expectedName = __EXPECTED_NAME__;
  const expectedSize = __EXPECTED_SIZE__;
  const result = (status, extra = {}) => ({
    status, operation, template_name, template_version, ...extra
  });
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== expectedSharePath
  ) {
    return result('wrong_share');
  }
  if (
    !expectedProviderFileId
    || !expectedItemPath.endsWith('/' + expectedName)
    || !(expectedSize > 0)
  ) {
    return result('source_identity_invalid');
  }
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const pageText = String(document.body?.innerText || '');
  const captchaVisible = [...document.querySelectorAll(
    '[class*="captcha"], [id*="captcha"], iframe[src*="captcha"]'
  )].some(visible) || /验证码|安全验证/.test(pageText);
  if (captchaVisible) {
    return result('captcha_required');
  }
  if (
    location.pathname === '/share/init'
    || /登录后|请登录|提取码|访问码/.test(pageText)
  ) {
    return result('auth_required');
  }
  const sources = [window.yunData || {}, window.locals || {}];
  const observedListUrl = performance.getEntriesByType('resource')
    .map(entry => String(entry.name || ''))
    .map(value => {
      try { return new URL(value); } catch (_error) { return null; }
    })
    .find(url => url && url.pathname === '/share/list'
      && url.searchParams.has('shareid')
      && url.searchParams.has('uk'));
  const readValue = keys => {
    for (const source of sources) {
      for (const key of keys) {
        try {
          const value = typeof source.get === 'function'
            ? source.get(key)
            : source[key];
          if (value !== undefined && value !== null && String(value)) {
            return String(value);
          }
        } catch (_error) {}
      }
    }
    return '';
  };
  const resourceValue = keys => {
    if (!observedListUrl) return '';
    for (const key of keys) {
      const value = observedListUrl.searchParams.get(key);
      if (value) return String(value);
    }
    return '';
  };
  const shareId = readValue(['shareid', 'share_id', 'SHARE_ID'])
    || resourceValue(['shareid', 'share_id']);
  const shareUk = readValue(['share_uk', 'uk', 'SHARE_UK'])
    || resourceValue(['share_uk', 'uk']);
  const sign = readValue(['sign', 'SIGN'])
    || resourceValue(['sign']);
  const timestamp = readValue(['timestamp', 'TIMESTAMP'])
    || resourceValue(['timestamp']);
  if (!shareId || !shareUk) {
    return result('share_download_metadata_missing');
  }
  const query = new URLSearchParams({
    channel: 'chunlei',
    clienttype: '0',
    web: '1',
    app_id: '250528'
  });
  if (sign) query.set('sign', sign);
  if (timestamp) query.set('timestamp', timestamp);
  const body = new URLSearchParams({
    encrypt: '0',
    product: 'share',
    uk: shareUk,
    primaryid: shareId,
    fid_list: JSON.stringify([expectedProviderFileId])
  });
  const cookie = document.cookie.split(';').map(value => value.trim())
    .find(value => value.startsWith('BDCLND='));
  const sekey = cookie
    ? decodeURIComponent(cookie.slice('BDCLND='.length))
    : resourceValue(['sekey']);
  if (sekey) {
    body.set('extra', JSON.stringify({
      sekey
    }));
  }
  let response;
  let payload;
  try {
    response = await fetch('/api/sharedownload?' + query.toString(), {
      method: 'POST',
      credentials: 'include',
      headers: {'content-type': 'application/x-www-form-urlencoded'},
      body: body.toString()
    });
    payload = await response.json();
  } catch (_error) {
    return result('provider_error', {provider_errno: null});
  }
  const message = String(
    payload?.show_msg || payload?.errmsg || payload?.error_msg || ''
  );
  if (response.status === 401 || response.status === 403 || /登录|认证/.test(message)) {
    return result('auth_required');
  }
  if (/验证码|安全验证/.test(message)) {
    return result('captcha_required');
  }
  if (!response.ok || Number(payload?.errno || 0) !== 0) {
    const providerErrno = Number(payload?.errno || 0);
    const filtered = providerErrno === 2
      && /部分文件违规，已被过滤|违规文件/.test(pageText);
    return result(filtered ? 'provider_filtered' : 'provider_error', {
      provider_errno: providerErrno,
      http_status: Number(response.status || 0)
    });
  }
  const rows = Array.isArray(payload?.list) ? payload.list : [];
  if (rows.length !== 1) {
    return result('download_link_ambiguous');
  }
  const row = rows[0] || {};
  const providerFileId = String(row.fs_id || row.fsid || expectedProviderFileId);
  if (providerFileId !== expectedProviderFileId) {
    return result('download_target_mismatch');
  }
  let link;
  try {
    link = new URL(String(row.dlink || ''));
  } catch (_error) {
    return result('download_link_missing');
  }
  return result('download_link_ready', {
    download_url: link.href,
    scheme: link.protocol,
    host: link.hostname,
    path: link.pathname,
    provider_file_id: providerFileId
  });
})()"""

_PROVIDER_DIRECT_LINK_TEMPLATE = NetdiskOpenCliTemplate(
    name="probe_download",
    source=_PROVIDER_DIRECT_LINK_SCRIPT_TEMPLATE,
    parameters=(
        "expected_share_path",
        "expected_provider_file_id",
        "expected_item_path",
        "expected_name",
        "expected_size",
    ),
)


def _provider_direct_link_script(
    *,
    expected_share_path: str,
    expected_provider_file_id: str,
    expected_item_path: str,
    expected_name: str,
    expected_size: int,
) -> str:
    return _PROVIDER_DIRECT_LINK_TEMPLATE.render(
        expected_share_path=expected_share_path,
        expected_provider_file_id=expected_provider_file_id,
        expected_item_path=expected_item_path,
        expected_name=expected_name,
        expected_size=expected_size,
    )


_OWNER_CLOUD_TRANSFER_SCRIPT_TEMPLATE = r"""(async () => {
  const operation = 'ticket04_owner_cloud_transfer';
  const expectedSharePath = __EXPECTED_SHARE_PATH_JSON__;
  const expectedProviderFileId = __EXPECTED_PROVIDER_FILE_ID_JSON__;
  const expectedName = __EXPECTED_NAME_JSON__;
  const expectedSize = __EXPECTED_SIZE_JSON__;
  const destinationDirectory = __DESTINATION_DIRECTORY_JSON__;
  const destinationPath = destinationDirectory + '/' + expectedName;
  const result = (status, extra = {}) => ({status, operation, ...extra});
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== expectedSharePath
  ) return result('wrong_share');
  if (
    !/^\d+$/.test(expectedProviderFileId)
    || !(expectedSize > 0)
    || !destinationDirectory.startsWith('/xiaocao/lv_subscription/')
    || destinationPath !== destinationDirectory + '/' + expectedName
  ) return result('source_identity_invalid');
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const pageText = String(document.body?.innerText || '');
  if ([...document.querySelectorAll(
    '[class*="captcha"], [id*="captcha"], iframe[src*="captcha"]'
  )].some(visible) || /验证码|安全验证/.test(pageText)) {
    return result('captcha_required');
  }
  const sources = [window.yunData || {}, window.locals || {}];
  const readValue = keys => {
    for (const source of sources) {
      for (const key of keys) {
        try {
          const value = typeof source.get === 'function'
            ? source.get(key) : source[key];
          if (value !== undefined && value !== null && String(value)) {
            return String(value);
          }
        } catch (_error) {}
      }
    }
    return '';
  };
  const shareId = readValue(['shareid', 'share_id', 'SHARE_ID']);
  const shareUk = readValue(['share_uk', 'uk', 'SHARE_UK']);
  const bdstoken = readValue(['bdstoken', 'BDSTOKEN']);
  if (!shareId || !shareUk || !bdstoken) return result('auth_required');
  const classify = payload => {
    const message = String(
      payload?.show_msg || payload?.errmsg || payload?.error_msg || ''
    );
    if (/验证码|安全验证/.test(message)) return 'captcha_required';
    if (/登录|认证/.test(message) || Number(payload?.errno) === -6) {
      return 'auth_required';
    }
    return 'provider_error';
  };
  const listDirectory = async path => {
    const query = new URLSearchParams({
      dir: path, order: 'name', desc: '0', showempty: '0',
      web: '1', page: '1', num: '1000', channel: 'chunlei',
      app_id: '250528', clienttype: '0'
    });
    const response = await fetch('/api/list?' + query.toString(), {
      credentials: 'include'
    });
    const payload = await response.json();
    return {response, payload};
  };
  const createDirectory = async path => {
    const query = new URLSearchParams({
      a: 'commit', channel: 'chunlei', web: '1', app_id: '250528',
      bdstoken, clienttype: '0'
    });
    const body = new URLSearchParams({
      path, isdir: '1', block_list: '[]'
    });
    const response = await fetch('/api/create?' + query.toString(), {
      method: 'POST', credentials: 'include',
      headers: {'content-type': 'application/x-www-form-urlencoded'},
      body: body.toString()
    });
    return {response, payload: await response.json()};
  };
  const directoryReceipts = [];
  let parent = '/';
  for (const component of destinationDirectory.split('/').filter(Boolean)) {
    const child = (parent === '/' ? '' : parent) + '/' + component;
    let listed;
    try { listed = await listDirectory(parent); }
    catch (_error) { return result('provider_error', {provider_errno: null}); }
    if (!listed.response.ok || Number(listed.payload?.errno || 0) !== 0) {
      return result(classify(listed.payload), {
        provider_errno: Number(listed.payload?.errno || 0)
      });
    }
    let matches = (Array.isArray(listed.payload?.list) ? listed.payload.list : [])
      .filter(row => Number(row?.isdir || 0) === 1
        && String(row?.path || '') === child);
    if (matches.length > 1) {
      return result('owner_directory_ambiguous', {path: child});
    }
    if (matches.length === 0) {
      let created;
      try { created = await createDirectory(child); }
      catch (_error) { return result('provider_error', {provider_errno: null}); }
      if (
        !created.response.ok
        || ![0, -8].includes(Number(created.payload?.errno || 0))
      ) {
        return result(classify(created.payload), {
          provider_errno: Number(created.payload?.errno || 0)
        });
      }
      listed = await listDirectory(parent);
      matches = (Array.isArray(listed.payload?.list) ? listed.payload.list : [])
        .filter(row => Number(row?.isdir || 0) === 1
          && String(row?.path || '') === child);
    }
    if (matches.length !== 1) {
      return result('owner_directory_readback_failed', {path: child});
    }
    directoryReceipts.push({
      path: child,
      provider_file_id: String(matches[0]?.fs_id || matches[0]?.fsid || ''),
      exact_count: 1
    });
    parent = child;
  }
  const exactOwnerRows = payload => (
    Array.isArray(payload?.list) ? payload.list : []
  ).filter(row => String(row?.path || '') === destinationPath
    && String(row?.server_filename || row?.name || '') === expectedName);
  let ownerListing;
  try { ownerListing = await listDirectory(destinationDirectory); }
  catch (_error) { return result('provider_error', {provider_errno: null}); }
  if (!ownerListing.response.ok
      || Number(ownerListing.payload?.errno || 0) !== 0) {
    return result(classify(ownerListing.payload), {
      provider_errno: Number(ownerListing.payload?.errno || 0)
    });
  }
  let ownerRows = exactOwnerRows(ownerListing.payload);
  if (ownerRows.length > 1) {
    return result('owner_duplicate_matches', {exact_match_count: ownerRows.length});
  }
  let transferPerformed = false;
  if (ownerRows.length === 0) {
    const query = new URLSearchParams({
      shareid: shareId, from: shareUk, ondup: 'fail', async: '1',
      channel: 'chunlei', web: '1', app_id: '250528', bdstoken,
      clienttype: '0'
    });
    const body = new URLSearchParams({
      fsidlist: JSON.stringify([expectedProviderFileId]),
      path: destinationDirectory
    });
    const cookie = document.cookie.split(';').map(value => value.trim())
      .find(value => value.startsWith('BDCLND='));
    if (cookie) body.set('sekey', decodeURIComponent(cookie.slice(7)));
    let response;
    let payload;
    try {
      response = await fetch('/share/transfer?' + query.toString(), {
        method: 'POST', credentials: 'include',
        headers: {'content-type': 'application/x-www-form-urlencoded'},
        body: body.toString()
      });
      payload = await response.json();
    } catch (_error) {
      return result('provider_error', {provider_errno: null});
    }
    if (!response.ok || Number(payload?.errno || 0) !== 0) {
      return result(classify(payload), {
        provider_errno: Number(payload?.errno || 0)
      });
    }
    transferPerformed = true;
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 300));
      ownerListing = await listDirectory(destinationDirectory);
      if (Number(ownerListing.payload?.errno || 0) !== 0) continue;
      ownerRows = exactOwnerRows(ownerListing.payload);
      if (ownerRows.length !== 0) break;
    }
  }
  if (ownerRows.length > 1) {
    return result('owner_duplicate_matches', {exact_match_count: ownerRows.length});
  }
  if (ownerRows.length !== 1) {
    return result('owner_transfer_readback_missing', {exact_match_count: 0});
  }
  const owner = ownerRows[0];
  if (Number(owner?.size || 0) !== expectedSize) {
    return result('owner_size_mismatch', {exact_match_count: 1});
  }
  return result('owner_ready', {
    exact_match_count: 1,
    transfer_performed: transferPerformed,
    owner_provider_file_id: String(owner?.fs_id || owner?.fsid || ''),
    owner_path: String(owner?.path || ''),
    name: String(owner?.server_filename || owner?.name || ''),
    size: Number(owner?.size || 0),
    modified_at: Number(owner?.server_mtime || owner?.local_mtime || 0),
    directory_receipts: directoryReceipts
  });
})()"""


def _owner_cloud_transfer_script(
    *,
    expected_share_path: str,
    expected_provider_file_id: str,
    expected_name: str,
    expected_size: int,
    destination_directory: str,
) -> str:
    return (
        _OWNER_CLOUD_TRANSFER_SCRIPT_TEMPLATE.replace(
            "__EXPECTED_SHARE_PATH_JSON__", json.dumps(expected_share_path)
        )
        .replace(
            "__EXPECTED_PROVIDER_FILE_ID_JSON__",
            json.dumps(expected_provider_file_id),
        )
        .replace("__EXPECTED_NAME_JSON__", json.dumps(expected_name))
        .replace("__EXPECTED_SIZE_JSON__", json.dumps(expected_size))
        .replace(
            "__DESTINATION_DIRECTORY_JSON__",
            json.dumps(destination_directory),
        )
    )


_OWNER_DOWNLOAD_LINK_SCRIPT_TEMPLATE = r"""(async () => {
  const operation = 'ticket04_owner_download_link';
  const expectedProviderFileId = __EXPECTED_PROVIDER_FILE_ID_JSON__;
  const expectedName = __EXPECTED_NAME_JSON__;
  const expectedSize = __EXPECTED_SIZE_JSON__;
  const result = (status, extra = {}) => ({status, operation, ...extra});
  if (location.origin !== 'https://pan.baidu.com') {
    return result('wrong_origin');
  }
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const pageText = String(document.body?.innerText || '');
  if (/验证码|安全验证/.test(pageText)) return result('captcha_required');
  if (/登录后|请登录/.test(pageText)) return result('auth_required');
  const rowFor = node => node.closest(
    'dd, tr, [role="row"], [class*="table-row"], [class*="file-item"]'
  ) || node;
  const rowName = row => {
    const values = Array.from(row.querySelectorAll('[title], [data-name]'))
      .flatMap(node => [
        String(node.getAttribute('title') || ''),
        String(node.getAttribute('data-name') || ''),
        String(node.textContent || '').trim()
      ]);
    return values.includes(expectedName);
  };
  const rowId = row => {
    const nodes = [row, ...row.querySelectorAll('[data-id], [data-fsid]')];
    return nodes.some(node => [
      String(node.getAttribute('data-id') || ''),
      String(node.getAttribute('data-fsid') || '')
    ].includes(expectedProviderFileId));
  };
  const deadline = Date.now() + 12000;
  let targets = [];
  while (Date.now() < deadline) {
    const nodes = Array.from(document.querySelectorAll(
      '[data-id], [data-fsid]'
    )).filter(node => [
      String(node.getAttribute('data-id') || ''),
      String(node.getAttribute('data-fsid') || '')
    ].includes(expectedProviderFileId));
    targets = [...new Set(nodes.map(rowFor))].filter(row => rowName(row));
    if (targets.length === 1) break;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  if (targets.length === 0) return result('owner_target_not_visible');
  if (targets.length !== 1) return result('owner_target_not_unique');
  const selectionControl = row => (
    row.querySelector('input[type="checkbox"]')
    || row.querySelector(
      '[role="checkbox"], [aria-checked], [class*="checkbox"]'
    )
  );
  const itemRow = row => [
    row, ...row.querySelectorAll('[data-id], [data-fsid]')
  ].some(node => (
    String(node.getAttribute('data-id') || '') !== ''
    || String(node.getAttribute('data-fsid') || '') !== ''
  ));
  const selected = row => {
    const control = selectionControl(row);
    return row.getAttribute('aria-selected') === 'true'
      || control?.getAttribute('aria-checked') === 'true'
      || control?.checked === true
      || row.classList.contains('selected');
  };
  const visibleRows = [...new Set(Array.from(document.querySelectorAll(
    'dd, tr, [role="row"], [class*="table-row"], [class*="file-item"]'
  )).map(rowFor))].filter(row => itemRow(row) && visible(row));
  for (const row of visibleRows.filter(row => row !== targets[0] && selected(row))) {
    const control = selectionControl(row);
    if (!control) return result('owner_selection_control_missing');
    control.click();
  }
  if (!selected(targets[0])) {
    const control = selectionControl(targets[0]);
    if (!control) return result('owner_selection_control_missing');
    control.click();
  }
  await new Promise(resolve => setTimeout(resolve, 250));
  const selectedRows = visibleRows.filter(selected);
  if (
    selectedRows.length !== 1
    || selectedRows[0] !== targets[0]
    || !rowId(targets[0])
    || !rowName(targets[0])
  ) return result('owner_selection_mismatch');
  const state = {downloadUrl: '', scheme: '', host: '', path: ''};
  const capture = candidate => {
    let link;
    try { link = new URL(String(candidate || ''), location.href); }
    catch (_error) { return false; }
    if (
      link.protocol !== 'https:'
      || link.hostname !== 'd.pcs.baidu.com'
      || !(link.pathname.startsWith('/file/')
        || link.pathname === '/rest/2.0/pcs/file')
      || !link.search
    ) return false;
    state.downloadUrl = link.href;
    state.scheme = link.protocol;
    state.host = link.hostname;
    state.path = link.pathname;
    return true;
  };
  const originalSetAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function(name, value) {
    if (
      this instanceof HTMLIFrameElement
      && String(name).toLowerCase() === 'src'
      && capture(value)
    ) return originalSetAttribute.call(this, name, 'about:blank');
    return originalSetAttribute.call(this, name, value);
  };
  const observer = new MutationObserver(records => {
    for (const record of records) {
      const frame = record.target;
      if (!(frame instanceof HTMLIFrameElement)) continue;
      const source = frame.getAttribute('src') || '';
      if (capture(source)) originalSetAttribute.call(frame, 'src', 'about:blank');
    }
  });
  observer.observe(document.documentElement, {
    subtree: true, attributes: true, attributeFilter: ['src']
  });
  const originalWindowOpen = window.open.bind(window);
  window.open = (url, ...args) => (
    capture(url) ? null : originalWindowOpen(url, ...args)
  );
  const downloadControls = Array.from(document.querySelectorAll(
    'a, button, [role="button"]'
  )).filter(control => visible(control) && (
    String(control.getAttribute('title') || '').trim() === '下载'
    || String(control.textContent || '').trim() === '下载'
  ));
  if (downloadControls.length !== 1) {
    return result('owner_download_control_ambiguous');
  }
  downloadControls[0].click();
  const captureDeadline = Date.now() + 15000;
  while (Date.now() < captureDeadline && !state.downloadUrl) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!state.downloadUrl) return result('owner_download_link_not_captured');
  return result('download_link_ready', {
    download_url: state.downloadUrl,
    provider_file_id: expectedProviderFileId,
    name: expectedName,
    size: expectedSize,
    scheme: state.scheme,
    host: state.host,
    path: state.path
  });
})()"""


def _owner_download_link_script(
    *,
    expected_provider_file_id: str,
    expected_name: str,
    expected_size: int,
) -> str:
    return (
        _OWNER_DOWNLOAD_LINK_SCRIPT_TEMPLATE.replace(
            "__EXPECTED_PROVIDER_FILE_ID_JSON__",
            json.dumps(expected_provider_file_id),
        )
        .replace("__EXPECTED_NAME_JSON__", json.dumps(expected_name))
        .replace("__EXPECTED_SIZE_JSON__", json.dumps(expected_size))
    )


_PROVIDER_FRONTEND_INTERCEPT_INSTALL_SCRIPT_TEMPLATE = r"""(async () => {
  const operation = 'ticket04_signed_link_intercept_and_trigger';
  const expectedSharePath = __EXPECTED_SHARE_PATH_JSON__;
  const expectedProviderFileId = __EXPECTED_PROVIDER_FILE_ID_JSON__;
  const expectedName = __EXPECTED_NAME_JSON__;
  const expectedSize = __EXPECTED_SIZE_JSON__;
  const result = (status, extra = {}) => ({status, operation, ...extra});
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== expectedSharePath
  ) {
    return result('wrong_share');
  }
  const visible = element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const confirmations = Array.from(document.querySelectorAll(
    "a[data-xiaocao-download-confirmation='1']"
  )).filter(visible);
  const initialDownloads = Array.from(document.querySelectorAll(
    "a[data-xiaocao-download-open='1']"
  )).filter(visible);
  if (confirmations.length > 1 || initialDownloads.length > 1) {
    return result('download_trigger_ambiguous');
  }
  const trigger = confirmations[0] || initialDownloads[0];
  if (!trigger) {
    return result('download_trigger_missing');
  }
  const stateKey = '__xiaocaoTicket04SignedLink';
  const prior = window[stateKey];
  if (prior && (
    prior.providerFileId !== expectedProviderFileId
    || prior.name !== expectedName
    || prior.size !== expectedSize
  )) {
    return result('interceptor_target_mismatch');
  }
  if (prior?.installed === true) {
    return result('interceptor_installed', {
      provider_file_id: expectedProviderFileId,
      name: expectedName,
      size: expectedSize
    });
  }
  const state = {
    installed: true,
    providerFileId: expectedProviderFileId,
    name: expectedName,
    size: expectedSize,
    downloadUrl: '',
    scheme: '',
    host: '',
    path: ''
  };
  window[stateKey] = state;
  const capture = candidate => {
    let url;
    try { url = new URL(String(candidate || ''), location.href); }
    catch (_error) { return false; }
    if (
      url.protocol !== 'https:'
      || url.hostname !== 'd.pcs.baidu.com'
      || !(url.pathname.startsWith('/file/')
        || url.pathname === '/rest/2.0/pcs/file')
      || !url.search
    ) {
      return false;
    }
    state.downloadUrl = url.href;
    state.scheme = url.protocol;
    state.host = url.hostname;
    state.path = url.pathname;
    return true;
  };
  const capturePayload = payload => {
    const rows = Array.isArray(payload?.list) ? payload.list : [];
    for (const row of rows) {
      const fileId = String(row?.fs_id || row?.fsid || '');
      if (fileId === expectedProviderFileId && capture(row?.dlink)) {
        return true;
      }
    }
    return false;
  };
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    try {
      const requestUrl = new URL(String(args[0]?.url || args[0] || ''), location.href);
      if (requestUrl.pathname === '/api/sharedownload') {
        response.clone().json().then(capturePayload).catch(() => {});
      }
    } catch (_error) {}
    return response;
  };
  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    try {
      const requestUrl = new URL(String(url || ''), location.href);
      if (requestUrl.pathname === '/api/sharedownload') {
        this.addEventListener('load', () => {
          try { capturePayload(JSON.parse(this.responseText)); }
          catch (_error) {}
        }, {once: true});
      }
    } catch (_error) {}
    return originalOpen.call(this, method, url, ...rest);
  };
  const originalWindowOpen = window.open.bind(window);
  window.open = (url, ...args) => (
    capture(url) ? null : originalWindowOpen(url, ...args)
  );
  const originalAnchorClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function(...args) {
    if (capture(this.href)) return;
    return originalAnchorClick.apply(this, args);
  };
  const originalSetAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function(name, value) {
    if (
      this instanceof HTMLIFrameElement
      && String(name).toLowerCase() === 'src'
      && capture(value)
    ) {
      return originalSetAttribute.call(this, name, 'about:blank');
    }
    return originalSetAttribute.call(this, name, value);
  };
  const descriptor = Object.getOwnPropertyDescriptor(
    HTMLIFrameElement.prototype, 'src'
  );
  if (descriptor?.get && descriptor?.set) {
    Object.defineProperty(HTMLIFrameElement.prototype, 'src', {
      configurable: descriptor.configurable,
      enumerable: descriptor.enumerable,
      get: descriptor.get,
      set(value) {
        return descriptor.set.call(this, capture(value) ? 'about:blank' : value);
      }
    });
  }
  const observer = new MutationObserver(records => {
    for (const record of records) {
      const node = record.target;
      if (!(node instanceof HTMLIFrameElement)) continue;
      const source = node.getAttribute('src') || '';
      if (capture(source)) originalSetAttribute.call(node, 'src', 'about:blank');
    }
  });
  observer.observe(document.documentElement, {
    subtree: true, attributes: true, attributeFilter: ['src']
  });
  let secondaryConfirmationTriggered = confirmations.length === 1;
  trigger.click();
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (state.downloadUrl) {
      return result('download_link_ready', {
        download_url: state.downloadUrl,
        scheme: state.scheme,
        host: state.host,
        path: state.path,
        provider_file_id: state.providerFileId
      });
    }
    if (!secondaryConfirmationTriggered) {
      const secondaryConfirmations = Array.from(document.querySelectorAll(
        'a.g-button'
      )).filter(control => (
        visible(control)
        && String(control.innerText || control.textContent || '').trim()
          === '普通下载'
      ));
      if (secondaryConfirmations.length > 1) {
        return result('download_confirmation_ambiguous');
      }
      if (secondaryConfirmations.length === 1) {
        secondaryConfirmationTriggered = true;
        secondaryConfirmations[0].click();
      }
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return result('signed_link_not_captured');
})()"""


_PROVIDER_FRONTEND_INTERCEPT_READ_SCRIPT_TEMPLATE = r"""(async () => {
  const operation = 'ticket04_signed_link_intercept_read';
  const expectedProviderFileId = __EXPECTED_PROVIDER_FILE_ID_JSON__;
  const expectedName = __EXPECTED_NAME_JSON__;
  const expectedSize = __EXPECTED_SIZE_JSON__;
  const stateKey = '__xiaocaoTicket04SignedLink';
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const state = window[stateKey];
    if (!state || state.installed !== true) {
      return {status: 'interceptor_missing', operation};
    }
    if (
      state.providerFileId !== expectedProviderFileId
      || state.name !== expectedName
      || state.size !== expectedSize
    ) {
      return {status: 'interceptor_target_mismatch', operation};
    }
    if (state.downloadUrl) {
      return {
        status: 'download_link_ready', operation,
        download_url: state.downloadUrl,
        scheme: state.scheme,
        host: state.host,
        path: state.path,
        provider_file_id: state.providerFileId
      };
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return {status: 'signed_link_not_captured', operation};
})()"""


def _provider_frontend_intercept_install_script(
    *,
    expected_share_path: str,
    expected_provider_file_id: str,
    expected_name: str,
    expected_size: int,
) -> str:
    return (
        _PROVIDER_FRONTEND_INTERCEPT_INSTALL_SCRIPT_TEMPLATE.replace(
            "__EXPECTED_SHARE_PATH_JSON__", json.dumps(expected_share_path)
        )
        .replace(
            "__EXPECTED_PROVIDER_FILE_ID_JSON__",
            json.dumps(expected_provider_file_id),
        )
        .replace("__EXPECTED_NAME_JSON__", json.dumps(expected_name))
        .replace("__EXPECTED_SIZE_JSON__", json.dumps(expected_size))
    )


def _provider_frontend_intercept_read_script(
    *,
    expected_provider_file_id: str,
    expected_name: str,
    expected_size: int,
) -> str:
    return (
        _PROVIDER_FRONTEND_INTERCEPT_READ_SCRIPT_TEMPLATE.replace(
            "__EXPECTED_PROVIDER_FILE_ID_JSON__",
            json.dumps(expected_provider_file_id),
        )
        .replace("__EXPECTED_NAME_JSON__", json.dumps(expected_name))
        .replace("__EXPECTED_SIZE_JSON__", json.dumps(expected_size))
    )


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(value) + "\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _media_type(name: str, *, is_dir: bool) -> str:
    if is_dir:
        return "directory"
    suffix = Path(name).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix in PDF_SUFFIXES:
        return "pdf"
    return "excluded"


def _exclusive(scope: str) -> Callable:
    def decorate(method: Callable) -> Callable:
        @functools.wraps(method)
        def locked(self: "LvSubscriptionService", *args: Any, **kwargs: Any) -> Any:
            suffix = scope
            if scope == "item":
                identity = str(
                    args[0] if args else kwargs.get("identity") or ""
                ).strip()
                if not re.fullmatch(r"[0-9a-f]{64}", identity):
                    raise EnrichmentError("subscription item identity is invalid")
                suffix = f"item-{identity}"
            lock_path = self.output_dir / ".locks" / f"{suffix}.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                return method(self, *args, **kwargs)

        return locked

    return decorate


class LvSubscriptionService:
    """Persist the direct-share manifest without persisting share credentials."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        now: Callable[[], datetime] | None = None,
        runner: Callable[..., Any] = subprocess.run,
        opencli_command: tuple[str, ...] | None = None,
        share_url: str | None = None,
        share_code: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        edge_route_launcher: Callable[[str], None] | None = None,
        downloads_dir: Path | str | None = None,
        edge_profile_dir: Path | str | None = None,
        download_policy_configurer: Callable[
            [str, str | None, Path], dict[str, Any]
        ]
        | None = None,
        direct_download_fetcher: Callable[
            [str, Path, int, str], dict[str, Any]
        ]
        | None = None,
        preview_fetcher: Callable[[str, Path], dict[str, Any]] | None = None,
        owner_cloud_operator: Callable[
            [dict[str, Any], dict[str, Any], str, str | None],
            dict[str, Any],
        ]
        | None = None,
        owner_download_link_reader: Callable[
            [dict[str, Any], dict[str, Any], str, str | None],
            dict[str, Any],
        ]
        | None = None,
        opencli_cookie_reader: Callable[
            [str, str | None], list[dict[str, Any]]
        ]
        | None = None,
        owner_download_fetcher: Callable[
            [str, list[dict[str, Any]], Path, int], dict[str, Any]
        ]
        | None = None,
        owner_authenticated_streamer: Callable[
            [dict[str, Any], dict[str, Any], str, str | None, Path],
            dict[str, Any],
        ]
        | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.manifest_path = self.output_dir / "manifest.json"
        self.events_path = self.output_dir / "events.jsonl"
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self.runner = runner
        installed_opencli = shutil.which("opencli")
        self.opencli_command = opencli_command or (
            (installed_opencli,)
            if installed_opencli
            else ("npx", "--yes", "@jackwener/opencli@1.8.6")
        )
        self.share_url = str(share_url or "").strip()
        self.share_code = str(share_code or "").strip()
        self.sleep = sleep
        self.edge_route_launcher = (
            edge_route_launcher or self._default_edge_route_launcher
        )
        self.downloads_dir = Path(
            downloads_dir or (Path.home() / "Downloads")
        ).expanduser().resolve()
        self.edge_profile_dir = Path(
            edge_profile_dir
            or (
                Path.home()
                / "Library/Application Support/Microsoft Edge/Default"
            )
        ).expanduser().resolve()
        self.download_inbox = (self.output_dir / "download_inbox").resolve()
        self.download_policy_path = self.output_dir / "download_policy.json"
        self.download_policy_configurer = (
            download_policy_configurer
            or self._default_download_policy_configurer
        )
        self.direct_download_fetcher = (
            direct_download_fetcher or self._default_direct_download_fetcher
        )
        self.preview_fetcher = preview_fetcher or self._default_preview_fetcher
        self.owner_cloud_operator = (
            owner_cloud_operator or self._default_owner_cloud_operator
        )
        self.owner_download_link_reader = (
            owner_download_link_reader
            or self._default_owner_download_link_reader
        )
        self.opencli_cookie_reader = (
            opencli_cookie_reader or self._default_opencli_cookie_reader
        )
        self.owner_download_fetcher = (
            owner_download_fetcher or self._default_owner_download_fetcher
        )
        self.owner_authenticated_streamer = (
            owner_authenticated_streamer
            or (
                None
                if any(
                    value is not None
                    for value in (
                        owner_download_link_reader,
                        opencli_cookie_reader,
                        owner_download_fetcher,
                    )
                )
                else self._default_owner_authenticated_streamer
            )
        )
        self._opencli_listing: tuple[
            str,
            str | None,
            dict[str, Any],
        ] | None = None

    @staticmethod
    def _default_edge_route_launcher(route: str) -> None:
        """Wake the exact Edge target before rebinding a detached session."""
        try:
            result = subprocess.run(
                ["/usr/bin/open", "-a", "Microsoft Edge", route],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EnrichmentDiagnosticError(
                "subscription Edge route recovery launch failed",
                category="local_recovery",
                code="opencli_edge_launch_failed",
                stage="browser_open",
            ) from exc
        if int(getattr(result, "returncode", 1)) != 0:
            raise EnrichmentDiagnosticError(
                "subscription Edge route recovery launch failed",
                category="local_recovery",
                code="opencli_edge_launch_failed",
                stage="browser_open",
                exit_code=int(result.returncode),
            )

    def _default_download_policy_configurer(
        self,
        session: str,
        profile: str | None,
        inbox: Path,
    ) -> dict[str, Any]:
        """Set target-scoped CDP download behavior without editing Preferences."""
        opencli_binary = shutil.which(str(self.opencli_command[0]))
        node_binary = shutil.which("node")
        if not opencli_binary or not node_binary:
            return {
                "configured": False,
                "code": "opencli_cdp_transport_unavailable",
            }
        entrypoint = Path(opencli_binary).resolve()
        page_module = entrypoint.parent / "browser" / "page.js"
        if not page_module.is_file():
            return {
                "configured": False,
                "code": "opencli_cdp_transport_unavailable",
            }
        payload = {
            "module": str(page_module),
            "session": session,
            "profile": profile,
            "inbox": str(inbox),
        }
        script = """
import {pathToFileURL} from 'node:url';
const input = JSON.parse(process.argv[1]);
const {Page} = await import(pathToFileURL(input.module).href);
const page = new Page(
  input.session, 20, input.profile || undefined, 'background'
);
try {
  const ack = await page.cdp('Page.setDownloadBehavior', {
    behavior: 'allow', downloadPath: input.inbox
  });
  console.log(JSON.stringify({
    configured: true,
    method: 'Page.setDownloadBehavior',
    command_ack: ack !== undefined
  }));
} catch (error) {
  const message = String(error && error.message || error);
  const code = message.includes('not permitted')
    ? 'opencli_cdp_method_not_permitted'
    : 'opencli_cdp_download_behavior_failed';
  console.log(JSON.stringify({configured: false, code}));
}
"""
        try:
            completed = subprocess.run(
                (node_binary, "--input-type=module", "-e", script, _canonical(payload)),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            result = json.loads(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return {
                "configured": False,
                "code": "opencli_cdp_download_behavior_failed",
            }
        if not isinstance(result, dict):
            return {
                "configured": False,
                "code": "opencli_cdp_download_behavior_failed",
            }
        return result

    def configure_opencli_download_policy(
        self,
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        """Configure and persist a credential-free target-scoped readback."""
        if not _OPENCLI_NAME.fullmatch(session) or (
            profile is not None and not _OPENCLI_NAME.fullmatch(profile)
        ):
            raise EnrichmentError("OpenCLI session or profile name is invalid")
        self.download_inbox.mkdir(parents=True, exist_ok=True)
        result = self.download_policy_configurer(
            session,
            profile,
            self.download_inbox,
        )
        if not isinstance(result, dict) or not isinstance(
            result.get("configured"), bool
        ):
            raise EnrichmentDiagnosticError(
                "OpenCLI download policy readback is invalid",
                category="local_runtime_error",
                code="download_policy_readback_invalid",
                stage="browser_download_policy",
            )
        if result["configured"] is True and (
            result.get("method") != "Page.setDownloadBehavior"
            or result.get("command_ack") is not True
        ):
            raise EnrichmentDiagnosticError(
                "OpenCLI download policy was not acknowledged",
                category="local_runtime_error",
                code="download_policy_readback_invalid",
                stage="browser_download_policy",
            )
        readback = {
            **result,
            "session": session,
            "profile": profile,
            "inbox": str(self.download_inbox),
            "persistent_profile_mutated": False,
        }
        _atomic_write_json(self.download_policy_path, readback)
        return readback

    @classmethod
    def from_config(
        cls,
        output_dir: Path | str,
        *,
        config_path: Path | str = "xiaocao.yaml",
        **kwargs: Any,
    ) -> "LvSubscriptionService":
        path = Path(config_path).expanduser().resolve()
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise EnrichmentError("private Xiaocao configuration is unavailable") from exc
        config = (
            (value.get("kol_intelligence") or {}).get("lv_xiaotong") or {}
            if isinstance(value, dict)
            else {}
        )
        if not isinstance(config, dict):
            raise EnrichmentError("Lv subscription configuration is invalid")
        return cls(
            output_dir,
            share_url=config.get("subscription_share_url"),
            share_code=config.get("subscription_share_code"),
            **kwargs,
        )

    def _time(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise EnrichmentError("subscription clock must include a timezone")
        return value

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {
                "schema_version": 1,
                "source": "baidu_subscription_share_browser",
                "author": "吕晓彤",
                "cursor": None,
                "items": {},
            }
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("subscription manifest is invalid") from exc
        if not isinstance(value, dict) or not isinstance(value.get("items"), dict):
            raise EnrichmentError("subscription manifest is invalid")
        return value

    @staticmethod
    def _reviewed_version_rows(
        value: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, str]]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise EnrichmentError(
                "subscription historical eligibility review is invalid"
            )
        normalized: dict[tuple[str, str], dict[str, str]] = {}
        for raw in value:
            if not isinstance(raw, Mapping):
                raise EnrichmentError(
                    "subscription historical eligibility review is invalid"
                )
            identity = str(raw.get("identity") or "").strip()
            version_key = str(raw.get("version_key") or "").strip()
            if not re.fullmatch(r"[0-9a-f]{64}", identity) or not re.fullmatch(
                r"[0-9a-f]{64}", version_key
            ):
                raise EnrichmentError(
                    "subscription historical eligibility review is incomplete"
                )
            normalized[(identity, version_key)] = {
                "identity": identity,
                "version_key": version_key,
            }
        if not normalized:
            raise EnrichmentError(
                "subscription historical eligibility review is empty"
            )
        return sorted(
            normalized.values(),
            key=lambda row: (row["identity"], row["version_key"]),
        )

    def _write_manifest_if_unchanged(
        self,
        expected_digest: str,
        manifest: dict[str, Any],
    ) -> bool:
        current = self._load_manifest()
        current_digest = hashlib.sha256(
            _canonical(current).encode("utf-8")
        ).hexdigest()
        if current_digest != expected_digest:
            return False
        _atomic_write_json(self.manifest_path, manifest)
        return True

    @_exclusive("manifest")
    def retire_historical_versions(
        self,
        reviewed_versions: Sequence[Mapping[str, Any]],
        *,
        cutoff_modified_at: int,
    ) -> dict[str, Any]:
        """Retire one audited historical set without fabricating completion."""

        reviewed = self._reviewed_version_rows(reviewed_versions)
        try:
            cutoff = int(cutoff_modified_at)
        except (TypeError, ValueError) as exc:
            raise EnrichmentError(
                "subscription historical eligibility cutoff is invalid"
            ) from exc
        if cutoff <= 0:
            raise EnrichmentError(
                "subscription historical eligibility cutoff is invalid"
            )
        manifest = self._load_manifest()
        manifest_digest = hashlib.sha256(
            _canonical(manifest).encode("utf-8")
        ).hexdigest()
        items = manifest["items"]
        targets: list[tuple[dict[str, Any], dict[str, str]]] = []
        for reviewed_row in reviewed:
            row = items.get(reviewed_row["identity"])
            if not isinstance(row, dict):
                raise EnrichmentError(
                    "subscription reviewed historical version is missing"
                )
            if row.get("version_key") != reviewed_row["version_key"]:
                raise EnrichmentError(
                    "subscription reviewed historical version changed"
                )
            if int(row.get("modified_at") or 0) > cutoff:
                raise EnrichmentError(
                    "subscription reviewed version is newer than eligibility cutoff"
                )
            targets.append((row, reviewed_row))

        source_watermark = {
            "cursor": str(manifest.get("cursor") or ""),
            "observed_at": str(manifest.get("observed_at") or ""),
            "max_modified_at": max(
                (
                    int(row.get("modified_at") or 0)
                    for row in items.values()
                    if isinstance(row, dict)
                ),
                default=0,
            ),
        }
        migration_id = hashlib.sha256(
            _canonical({
                "reviewed_versions": reviewed,
                "cutoff_modified_at": cutoff,
            }).encode("utf-8")
        ).hexdigest()
        prior_migrations = manifest.get("eligibility_migrations")
        if not isinstance(prior_migrations, list):
            prior_migrations = []
        for prior in prior_migrations:
            if isinstance(prior, dict) and prior.get("migration_id") == migration_id:
                return {**prior, "status": "already_completed"}

        current_manifest = self._load_manifest()
        if hashlib.sha256(
            _canonical(current_manifest).encode("utf-8")
        ).hexdigest() != manifest_digest:
            blocked = {
                "event": "subscription_historical_eligibility_migration",
                "status": "blocked",
                "code": "eligibility_migration_concurrent_writer",
                "migration_id": migration_id,
                "external_business_effects_replayed": False,
            }
            _append_jsonl(self.events_path, blocked)
            return blocked

        retired: list[dict[str, str]] = []
        for row, reviewed_row in targets:
            if row.get("completed_version_key") != row.get("version_key"):
                changed = (
                    row.get("work_eligible") is True
                    or row.get("pause_reason")
                    != "historical_backlog_retired"
                )
                row["work_eligible"] = False
                row["pause_reason"] = "historical_backlog_retired"
                if changed:
                    retired.append(dict(reviewed_row))
        migration = {
            "event": "subscription_historical_eligibility_migration",
            "status": "completed",
            "migration_id": migration_id,
            "observed_at": self._time().isoformat(timespec="seconds"),
            "source_watermark": source_watermark,
            "cutoff_modified_at": cutoff,
            "reviewed_count": len(reviewed),
            "reviewed_versions_sha256": hashlib.sha256(
                _canonical(reviewed).encode("utf-8")
            ).hexdigest(),
            "retired_count": len(retired),
            "retired_versions_sha256": hashlib.sha256(
                _canonical(retired).encode("utf-8")
            ).hexdigest(),
            "completed_version_keys_written": 0,
            "claims_and_receipts_preserved": True,
            "external_business_effects_replayed": False,
        }
        manifest["historical_eligibility_migration"] = migration
        manifest["eligibility_migrations"] = [*prior_migrations, migration]
        if not self._write_manifest_if_unchanged(manifest_digest, manifest):
            blocked = {
                "event": "subscription_historical_eligibility_migration",
                "status": "blocked",
                "code": "eligibility_migration_concurrent_writer",
                "migration_id": migration_id,
                "external_business_effects_replayed": False,
            }
            _append_jsonl(self.events_path, blocked)
            return blocked
        _append_jsonl(self.events_path, migration)
        return migration

    def retire_packaged_historical_backlog(self) -> dict[str, Any] | None:
        """Apply the reviewed 2026-08-08 migration only to unchanged versions."""

        try:
            value = json.loads(
                _HISTORICAL_RETIREMENT_PATH.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                "subscription historical eligibility package is invalid"
            ) from exc
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 1
            or not isinstance(value.get("reviewed_versions"), list)
        ):
            raise EnrichmentError(
                "subscription historical eligibility package is invalid"
            )
        manifest = self._load_manifest()
        current = manifest["items"]
        unchanged = [
            row
            for row in self._reviewed_version_rows(value["reviewed_versions"])
            if isinstance(current.get(row["identity"]), dict)
            and current[row["identity"]].get("version_key")
            == row["version_key"]
        ]
        if not unchanged:
            return None
        return self.retire_historical_versions(
            unchanged,
            cutoff_modified_at=int(value.get("cutoff_modified_at") or 0),
        )

    def status(self) -> dict[str, Any]:
        """Return the credential-free durable cursor and item states."""
        return {
            **self._load_manifest(),
            "pending": self.pending_items(),
        }

    def record_item_failure(
        self,
        identity: str,
        *,
        failure: dict[str, Any],
        retryable: bool,
    ) -> dict[str, Any]:
        """Audit one isolated item failure without changing its claim."""
        item = self._manifest_item(str(identity))
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        claim_path = artifact_dir / "browser_download_claim.json"
        claim_status = "missing"
        if claim_path.is_file():
            try:
                claim = json.loads(claim_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                claim_status = "invalid"
            else:
                claim_status = str(claim.get("status") or "unknown")
        row = {
            "event": "subscription_item_failure_isolated",
            "source": "baidu_subscription_share_browser",
            "author": "吕晓彤",
            "identity": str(item["identity"]),
            "version_key": str(item["version_key"]),
            "name": str(item["name"]),
            "media_type": str(item["media_type"]),
            "claim_status": claim_status,
            "failure": {
                "category": str(failure["category"]),
                "code": str(failure["code"]),
                "stage": str(failure["stage"]),
                "retryable": bool(retryable),
            },
            "external_business_effects_replayed": False,
            "recorded_at": self._time().isoformat(timespec="seconds"),
        }
        if failure.get("exit_code") is not None:
            row["failure"]["exit_code"] = int(failure["exit_code"])
        if str(failure.get("operation") or "").strip():
            row["failure"]["operation"] = str(failure["operation"])
        _append_jsonl(self.events_path, row)
        return row

    def _opencli_json(
        self,
        session: str,
        *args: str,
        profile: str | None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        if not _OPENCLI_NAME.fullmatch(session):
            raise EnrichmentError("OpenCLI session name is invalid")
        if profile is not None and not _OPENCLI_NAME.fullmatch(profile):
            raise EnrichmentError("OpenCLI profile name is invalid")
        operation = str(args[0] if args else "unknown").strip().lower()
        stage = {
            "bind": "browser_bind",
            "click": "browser_click",
            "eval": "browser_eval",
            "open": "browser_open",
            "wait": "browser_wait",
        }.get(operation, "browser_command")
        operation_label = operation
        for candidate in args[1:]:
            match = _OPENCLI_SCRIPT_OPERATION.search(str(candidate))
            if match is not None:
                operation_label = match.group(1)
                break
        command = [
            *self.opencli_command,
            *(["--profile", profile] if profile else []),
            "browser",
            session,
            *args,
        ]
        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            diagnostic = EnrichmentDiagnosticError(
                "subscription browser command timed out",
                category="timeout",
                code="opencli_timeout",
                stage=stage,
            )
            diagnostic.diagnostic_operation = operation_label
            raise diagnostic from exc
        if result.returncode != 0:
            error_code = "opencli_command_failed"
            try:
                error_envelope = json.loads(str(result.stdout))
            except (TypeError, json.JSONDecodeError):
                error_envelope = None
            if isinstance(error_envelope, dict):
                error = error_envelope.get("error")
                candidate = (
                    str(error.get("code") or "").strip()
                    if isinstance(error, dict)
                    else ""
                )
                if _SAFE_OPENCLI_ERROR_CODE.fullmatch(candidate):
                    error_code = candidate
            diagnostic = EnrichmentDiagnosticError(
                "subscription browser command failed",
                category=_OPENCLI_ERROR_CATEGORIES.get(
                    error_code,
                    "transport_error",
                ),
                code=error_code,
                stage=stage,
                exit_code=int(result.returncode),
            )
            diagnostic.diagnostic_operation = operation_label
            raise diagnostic
        try:
            value = json.loads(str(result.stdout))
        except (TypeError, json.JSONDecodeError) as exc:
            diagnostic = EnrichmentDiagnosticError(
                "subscription browser returned invalid JSON",
                category="protocol_error",
                code="opencli_invalid_json",
                stage=stage,
            )
            diagnostic.diagnostic_operation = operation_label
            raise diagnostic from exc
        if not isinstance(value, dict):
            diagnostic = EnrichmentDiagnosticError(
                "subscription browser returned a non-object result",
                category="protocol_error",
                code="opencli_non_object",
                stage=stage,
            )
            diagnostic.diagnostic_operation = operation_label
            raise diagnostic
        return value

    def _validate_private_config(self) -> None:
        parsed = urlparse(self.share_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "pan.baidu.com"
            or not parsed.path.startswith("/s/")
            or parsed.query
            or parsed.fragment not in {"", "list/path=%2F"}
        ):
            raise EnrichmentError("Lv subscription share URL is invalid")
        if not self.share_code:
            raise EnrichmentError("Lv subscription share code is missing")

    def bind_opencli(
        self,
        *,
        session: str,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Bind the active authorized page via the compatible browser extension."""
        result = self._opencli_json(
            session,
            "bind",
            profile=profile,
            timeout_seconds=30,
        )
        if result.get("session") != session:
            raise EnrichmentError(
                "subscription OpenCLI bootstrap did not bind the requested session"
            )
        return {
            "status": "bound",
            "session": session,
        }

    def _rebind_opencli_parent_route(
        self,
        *,
        session: str,
        profile: str | None,
        route: str,
        expected_parent_path: str | None,
        operation: str,
    ) -> None:
        """Rebind a foreground page and prove its share parent before retry."""
        route_readback_script = """(() => {
          const operation = %s;
          const expectedSharePath = %s;
          const expectedParentPath = %s;
          const prefix = '#list/path=';
          let currentParentPath = '';
          try {
            currentParentPath = location.hash.startsWith(prefix)
              ? decodeURIComponent(location.hash.slice(prefix.length))
              : '';
          } catch (_error) {}
          return {
            status: (
              location.origin === 'https://pan.baidu.com'
              && location.pathname === expectedSharePath
              && (
                expectedParentPath === null
                || currentParentPath === expectedParentPath
              )
            ) ? 'target_route_ready' : 'target_route_mismatch',
            operation
          };
        })()""" % (
            json.dumps(operation),
            json.dumps(urlparse(self.share_url).path),
            json.dumps(expected_parent_path),
        )
        retryable_codes = {
            "detached_mid_command",
            "opencli_command_failed",
            "opencli_timeout",
        }
        # Navigation, bind, and route readback are all read-only recovery
        # operations. Treat the complete sequence as the retry unit: any one
        # of its browser commands can detach while the named session is being
        # rebound, and retrying only the final eval leaves the session
        # ownership unproven. No download control is selected in this helper.
        for attempt in range(_READ_ONLY_ROUTE_REBIND_ATTEMPTS):
            try:
                # A detached route readback can leave the foreground target
                # unusable even though the named session still exists. Wake
                # the same Edge target for every bounded recovery attempt;
                # retrying bind/open on the stale target alone reproduces the
                # detach and never proves session ownership.
                self.edge_route_launcher(route)
                self._opencli_json(
                    session,
                    "open",
                    route,
                    "--window",
                    "foreground",
                    profile=profile,
                    timeout_seconds=30,
                )
                self.bind_opencli(session=session, profile=profile)
                route_readback = self._opencli_json(
                    session,
                    "eval",
                    route_readback_script,
                    profile=profile,
                    timeout_seconds=30,
                )
            except EnrichmentDiagnosticError as exc:
                if (
                    attempt + 1 < _READ_ONLY_ROUTE_REBIND_ATTEMPTS
                    and exc.diagnostic_stage
                    in {"browser_open", "browser_bind", "browser_eval"}
                    and exc.diagnostic_code in retryable_codes
                ):
                    self.sleep(1.0)
                    continue
                raise
            if route_readback.get("status") == "target_route_ready":
                return
            if attempt + 1 < _READ_ONLY_ROUTE_REBIND_ATTEMPTS:
                self.sleep(1.0)
                continue
            raise EnrichmentDiagnosticError(
                "provider frontend target route did not bind",
                category="identity_error",
                code="provider_frontend_target_route_mismatch",
                stage="browser_eval",
            )
        raise AssertionError("OpenCLI parent route recovery exhausted")

    def _read_opencli_listing(
        self,
        *,
        session: str,
        profile: str | None = None,
        exact_path: str | None = None,
    ) -> dict[str, Any]:
        """Read a planned listing with bounded read-only recovery."""
        self._validate_private_config()
        expected_path = urlparse(self.share_url).path
        authorized_share_url = _authorized_share_url(
            self.share_url,
            self.share_code,
        )
        listing_navigation_url = authorized_share_url
        target_parent: str | None = None
        if exact_path is not None:
            target_parent = str(PurePosixPath(str(exact_path)).parent)
            listing_navigation_url = urlparse(authorized_share_url)._replace(
                fragment=f"list/path={quote(target_parent, safe='')}"
            ).geturl()
        manifest = self._load_manifest()
        prior_items = manifest.get("items", {})
        now = self._time()
        full_topology_audit = (
            exact_path is None
            and (not prior_items or (now.weekday() == 0 and now.hour == 3))
        )
        discovery_roots: list[str] = []
        known_roots: list[str] = []
        recursive_roots: list[str] | None = None
        if exact_path is not None:
            target = PurePosixPath(str(exact_path))
            if not target.is_absolute() or str(target) == "/":
                raise EnrichmentError("subscription exact listing path is invalid")
            parent = target.parent
            current = PurePosixPath("/")
            for component in parent.parts[1:]:
                current /= component
                discovery_roots.append(str(current))
            known_roots = sorted(
                {
                    str(row.get("path") or "")
                    for row in prior_items.values()
                    if isinstance(row, Mapping) and row.get("is_dir") is True
                }
            )
            recursive_roots = []
        elif not full_topology_audit:
            discovery_roots, known_roots, recursive_roots = _tiered_share_roots(
                prior_items, now
            )
        listing_script = _browser_listing_script(
            expected_path,
            recursive_roots=recursive_roots,
            known_roots=known_roots,
            discovery_roots=discovery_roots,
        )

        retryable_statuses = {
            "share_list_failed",
            "share_list_invalid_json",
            "share_list_timeout",
            "share_metadata_missing",
            "share_root_template_missing",
            "share_directory_template_missing",
            "wrong_origin",
            "wrong_share",
        }
        retryable_codes = {
            # OpenCLI deliberately does not retry a detached command because
            # arbitrary browser commands may have uncertain effects.  This
            # surface is only the read-only share listing, so reopening the
            # exact share and evaluating it once more is safe and bounded.
            "detached_mid_command",
            "opencli_timeout",
            "opencli_command_failed",
            "opencli_invalid_json",
            "opencli_non_object",
        }
        recovered_from: dict[str, str] | None = None
        exact_route_bound = False
        if exact_path is not None:
            # Narrow download resumes often inherit a stale background target
            # from the failed acquisition.  Prove the exact foreground parent
            # before the first listing eval; otherwise the first detached eval
            # is indistinguishable from a new source failure.  This helper is
            # navigation/bind/readback only and never selects a download row.
            self._rebind_opencli_parent_route(
                session=session,
                profile=profile,
                route=listing_navigation_url,
                expected_parent_path=target_parent,
                operation="ticket04_exact_listing_route_readback",
            )
            exact_route_bound = True
        for attempt in range(1, _READ_ONLY_LISTING_ATTEMPTS + 1):
            try:
                if not (exact_route_bound and attempt == 1):
                    self._opencli_json(
                        session,
                        "open",
                        listing_navigation_url,
                        profile=profile,
                        timeout_seconds=30,
                    )
                listing = self._opencli_json(
                    session,
                    "eval",
                    listing_script,
                    profile=profile,
                    timeout_seconds=120,
                )
            except EnrichmentDiagnosticError as exc:
                if (
                    attempt < _READ_ONLY_LISTING_ATTEMPTS
                    and exc.diagnostic_code in retryable_codes
                ):
                    if recovered_from is None:
                        recovered_from = {
                            "category": exc.diagnostic_category,
                            "code": exc.diagnostic_code,
                            "stage": exc.diagnostic_stage,
                        }
                    needs_rebind = (
                        exc.diagnostic_stage == "browser_open"
                        and exc.diagnostic_code == "opencli_timeout"
                    ) or (
                        exc.diagnostic_stage == "browser_eval"
                        and exc.diagnostic_code
                        in {
                            "detached_mid_command",
                            "opencli_command_failed",
                            "opencli_timeout",
                        }
                    )
                    if needs_rebind:
                        try:
                            # A named OpenCLI session can survive while its
                            # former page is detached (often leaving only an
                            # about:blank background target). Re-open the same
                            # authorized share in a foreground target and
                            # prove the route before retrying the read-only
                            # listing; binding first can attach the session to
                            # that dead/background page and reproduce the same
                            # eval failure indefinitely.
                            self._rebind_opencli_parent_route(
                                session=session,
                                profile=profile,
                                route=listing_navigation_url,
                                expected_parent_path=target_parent,
                                operation="ticket04_listing_route_readback",
                            )
                        except EnrichmentError as bind_error:
                            raise exc from bind_error
                    self.sleep(1.0)
                    continue
                raise
            if listing.get("status") == "authorization_required":
                authorized = self._opencli_json(
                    session,
                    "eval",
                    _browser_authorization_script(self.share_code),
                    profile=profile,
                    timeout_seconds=30,
                )
                if authorized.get("status") != "authorization_submitted":
                    raise EnrichmentError(
                        "subscription share authorization requires user confirmation"
                    )
                self._opencli_json(
                    session,
                    "open",
                    listing_navigation_url,
                    profile=profile,
                    timeout_seconds=30,
                )
                listing = self._opencli_json(
                    session,
                    "eval",
                    listing_script,
                    profile=profile,
                    timeout_seconds=120,
                )
            if listing.get("status") == "share_expired":
                raise EnrichmentError("Lv subscription share is expired")
            if (
                listing.get("status") == "ok"
                and isinstance(listing.get("entries"), list)
                and (
                    listing.get("complete_scan") is True
                    or isinstance(listing.get("coverage"), Mapping)
                )
            ):
                if recovered_from is not None:
                    listing = {
                        **listing,
                        "recovery": {
                            "status": "recovered",
                            "attempts": attempt,
                            "initial_failure": recovered_from,
                        },
                    }
                return listing
            observed_status = str(listing.get("status") or "")
            if (
                attempt < _READ_ONLY_LISTING_ATTEMPTS
                and observed_status in retryable_statuses
            ):
                if recovered_from is None:
                    recovered_from = {
                        "category": (
                            "timeout"
                            if observed_status == "share_list_timeout"
                            else "incomplete_scan"
                        ),
                        "code": {
                            "wrong_origin": "wrong_browser_origin",
                            "wrong_share": "wrong_share_page",
                        }.get(observed_status, observed_status),
                        "stage": "listing_validation",
                    }
                self.sleep(1.0)
                continue
            break

        if listing.get("status") == "authorization_required":
            raise EnrichmentError(
                "subscription share authorization requires user confirmation"
            )
        observed_status = str(listing.get("status") or "")
        code = {
            "listing_bounds_exceeded": "listing_bounds_exceeded",
            "share_list_failed": "share_list_failed",
            "share_list_invalid_json": "share_list_invalid_json",
            "share_list_timeout": "share_list_timeout",
            "share_metadata_missing": "share_metadata_missing",
            "share_root_template_missing": "share_root_template_missing",
            "share_directory_template_missing": (
                "share_directory_template_missing"
            ),
            "wrong_origin": "wrong_browser_origin",
            "wrong_share": "wrong_share_page",
        }.get(observed_status, "listing_incomplete")
        raise EnrichmentDiagnosticError(
            "subscription browser listing is unavailable",
            category=(
                "timeout"
                if observed_status == "share_list_timeout"
                else "incomplete_scan"
            ),
            code=code,
            stage="listing_validation",
        )

    @_exclusive("poll")
    def poll_opencli(
        self,
        *,
        session: str,
        profile: str | None = None,
        listing: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Open the one configured share in a browser and record its full listing."""
        if listing is None:
            listing = self._read_opencli_listing(
                session=session,
                profile=profile,
            )
        if (
            listing.get("status") != "ok"
            or not isinstance(listing.get("entries"), list)
            or (
                listing.get("complete_scan") is not True
                and not isinstance(listing.get("coverage"), Mapping)
            )
        ):
            raise EnrichmentDiagnosticError(
                "subscription shared listing is incomplete",
                category="incomplete_scan",
                code="shared_listing_incomplete",
                stage="listing_validation",
            )
        self._opencli_listing = (session, profile, listing)
        return self.observe_browser_listing(
            listing["entries"],
            coverage=(
                listing.get("coverage")
                if listing.get("complete_scan") is not True
                else None
            ),
        )

    def _download_listing(
        self,
        *,
        session: str,
        profile: str | None,
        exact_path: str,
    ) -> dict[str, Any]:
        cached = self._opencli_listing
        if cached is not None and cached[:2] == (session, profile):
            cached_listing = cached[2]
            if cached_listing.get("complete_scan") is True or (
                isinstance(cached_listing.get("coverage"), Mapping)
                and _covered_by_listing(exact_path, cached_listing["coverage"])
            ):
                return cached_listing
        listing = self._read_opencli_listing(
            session=session,
            profile=profile,
            exact_path=exact_path,
        )
        self._opencli_listing = (session, profile, listing)
        return listing

    @staticmethod
    def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(raw.get("provider_file_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        path = str(raw.get("path") or "").strip()
        if not provider_id or not name or not path:
            raise EnrichmentError(
                "browser subscription entry requires identity, name, and path"
            )
        try:
            size = int(raw.get("size") or 0)
            modified_at = int(raw.get("modified_at") or 0)
        except (TypeError, ValueError) as exc:
            raise EnrichmentError(
                "browser subscription entry size or modified time is invalid"
            ) from exc
        is_dir = bool(raw.get("is_dir"))
        if size < 0:
            raise EnrichmentError(
                "browser subscription entry size is invalid"
            )
        if not is_dir and modified_at <= 0:
            raise EnrichmentError(
                "browser subscription entry modification time is missing"
            )
        media_type = _media_type(name, is_dir=is_dir)
        identity = hashlib.sha256(provider_id.encode("utf-8")).hexdigest()
        version_key = hashlib.sha256(
            f"{provider_id}\n{modified_at}\n{size}".encode("utf-8")
        ).hexdigest()
        return {
            "identity": identity,
            "version_key": version_key,
            "path": path,
            "name": name,
            "is_dir": is_dir,
            "media_type": media_type,
            "size": size,
            "modified_at": modified_at,
        }

    @_exclusive("manifest")
    def observe_browser_listing(
        self,
        entries: list[dict[str, Any]],
        *,
        coverage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Record a complete or explicitly covered browser listing."""
        if not isinstance(entries, list):
            raise EnrichmentError("browser subscription listing must be a list")
        observed_time = self._time()
        observed_at = observed_time.isoformat(timespec="seconds")
        normalized = [self._normalize_entry(row) for row in entries]
        if len({row["identity"] for row in normalized}) != len(normalized):
            raise EnrichmentError("browser subscription listing has duplicate identities")
        normalized.sort(key=lambda row: (row["path"], row["identity"]))

        manifest = self._load_manifest()
        previous = manifest["items"]
        bootstrap_baseline = not previous or not any(
            isinstance(value, dict) and "work_eligible" in value
            for value in previous.values()
        )
        current: dict[str, dict[str, Any]] = {}
        for key, value in previous.items():
            if not isinstance(value, dict):
                continue
            present = value.get("present") is True
            if coverage is None or _covered_by_listing(
                str(value.get("path") or ""), coverage
            ):
                present = False
            current[key] = {**value, "present": present}
        updates: list[dict[str, Any]] = []
        excluded_count = 0
        paused_count = 0
        for row in normalized:
            persisted = {**row, "last_seen_at": observed_at, "present": True}
            prior = previous.get(row["identity"])
            if isinstance(prior, dict) and prior.get("first_seen_at"):
                persisted["first_seen_at"] = prior["first_seen_at"]
            else:
                persisted["first_seen_at"] = observed_at
            if (
                isinstance(prior, dict)
                and prior.get("version_key") == row["version_key"]
                and prior.get("version_first_seen_at")
            ):
                persisted["version_first_seen_at"] = prior[
                    "version_first_seen_at"
                ]
            else:
                persisted["version_first_seen_at"] = observed_at
            same_supported_version = (
                isinstance(prior, dict)
                and prior.get("version_key") == row["version_key"]
                and prior.get("media_type") == row["media_type"]
                and "work_eligible" in prior
            )
            if same_supported_version:
                persisted["work_eligible"] = prior["work_eligible"] is True
                if prior.get("pause_reason"):
                    persisted["pause_reason"] = str(prior["pause_reason"])
            else:
                within_small_boundary = (
                    row["media_type"] != "pdf"
                    or 0 < int(row["size"]) <= MAX_SMALL_EVIDENCE_BYTES
                )
                classification_migration = (
                    isinstance(prior, dict)
                    and prior.get("version_key") == row["version_key"]
                    and prior.get("media_type") == "excluded"
                    and row["media_type"] == "pdf"
                )
                persisted["work_eligible"] = (
                    not bootstrap_baseline
                    and row["media_type"] in SUPPORTED_SMALL_MEDIA
                    and within_small_boundary
                    and (
                        not classification_migration
                        or int(row["modified_at"])
                        >= int(observed_time.timestamp())
                        - PDF_BOOTSTRAP_WINDOW_SECONDS
                    )
                )
                if row["media_type"] == "pdf" and not within_small_boundary:
                    persisted["pause_reason"] = (
                        "pdf_size_outside_small_file_boundary"
                    )
            current[row["identity"]] = persisted
            if row["media_type"] not in SUPPORTED_SMALL_MEDIA:
                if not row["is_dir"]:
                    excluded_count += 1
                continue
            if persisted.get("work_eligible") is not True:
                if row["media_type"] == "pdf" and not row["is_dir"]:
                    paused_count += 1
                continue
            if (
                not isinstance(prior, dict)
                or prior.get("version_key") != row["version_key"]
                or prior.get("media_type") != row["media_type"]
            ):
                updates.append(row)

        if coverage is not None:
            observed_identities = {row["identity"] for row in normalized}
            direct_roots = coverage.get("direct_roots")
            removed_directories = [
                row
                for identity, row in previous.items()
                if (
                    isinstance(row, dict)
                    and row.get("is_dir") is True
                    and isinstance(direct_roots, list)
                    and _parent_path(str(row.get("path") or ""))
                    in {str(root) for root in direct_roots}
                    and identity not in observed_identities
                )
            ]
            for removed in removed_directories:
                removed_path = str(removed.get("path") or "")
                for item in current.values():
                    if _is_within(str(item.get("path") or ""), removed_path):
                        item["present"] = False

        bootstrap_baseline_count = 0
        if bootstrap_baseline:
            selected: dict[str, dict[str, Any]] = {}
            for row in normalized:
                media_type = str(row["media_type"])
                if media_type not in {"image", "text"}:
                    continue
                current_best = selected.get(media_type)
                if current_best is None or (
                    int(row["modified_at"]),
                    str(row["path"]),
                    str(row["identity"]),
                ) > (
                    int(current_best["modified_at"]),
                    str(current_best["path"]),
                    str(current_best["identity"]),
                ):
                    selected[media_type] = row
            selected_versions = {
                str(row["version_key"]) for row in selected.values()
            }
            recent_pdf_versions = {
                str(row["version_key"])
                for row in normalized
                if row["media_type"] == "pdf"
                and 0 < int(row["size"]) <= MAX_SMALL_EVIDENCE_BYTES
                and int(row["modified_at"])
                >= int(observed_time.timestamp())
                - PDF_BOOTSTRAP_WINDOW_SECONDS
            }
            selected_versions.update(recent_pdf_versions)
            for item in current.values():
                if isinstance(item, dict):
                    item["work_eligible"] = (
                        item.get("version_key") in selected_versions
                    )
            updates = sorted(
                [
                    row
                    for row in normalized
                    if row["version_key"] in selected_versions
                ],
                key=lambda row: (row["media_type"], row["path"]),
            )
            bootstrap_baseline_count = sum(
                1
                for row in normalized
                if row["media_type"] in SUPPORTED_SMALL_MEDIA
                and row["version_key"] not in selected_versions
            )
            manifest["bootstrap"] = {
                "policy": "latest_version_per_supported_media_type",
                "completed_at": observed_at,
                "baseline_only_count": bootstrap_baseline_count,
                "work_eligible_count": len(selected_versions),
            }

        present_rows = sorted(
            (
                row
                for row in current.values()
                if isinstance(row, dict) and row.get("present") is True
            ),
            key=lambda row: (row["path"], row["identity"]),
        )
        cursor_payload = [
            {
                "identity": row["identity"],
                "version_key": row["version_key"],
            }
            for row in present_rows
        ]
        cursor = hashlib.sha256(_canonical(cursor_payload).encode("utf-8")).hexdigest()
        manifest.update(
            {
                "cursor": cursor,
                "observed_at": observed_at,
                "items": current,
                "discovery_coverage": (
                    dict(coverage) if coverage is not None else "complete"
                ),
            }
        )
        _atomic_write_json(self.manifest_path, manifest)
        if not updates:
            return None
        updates.sort(key=lambda row: (row["media_type"], row["path"]))
        result = {
            "event": "subscription_updates_discovered",
            "source": "baidu_subscription_share_browser",
            "author": "吕晓彤",
            "cursor": cursor,
            "observed_at": observed_at,
            "observed_count": len(normalized),
            "excluded_count": excluded_count,
            "paused_count": paused_count,
            "bootstrap_baseline_count": bootstrap_baseline_count,
            "updates": updates,
        }
        _append_jsonl(self.events_path, result)
        return result

    def _manifest_item(self, identity: str) -> dict[str, Any]:
        value = self._load_manifest().get("items", {}).get(identity)
        if not isinstance(value, dict):
            raise EnrichmentError("subscription item identity is unknown")
        if value.get("media_type") not in SUPPORTED_SMALL_MEDIA:
            raise EnrichmentError("subscription item is outside Ticket 04 media scope")
        if (
            value.get("media_type") == "pdf"
            and not 0 < int(value.get("size") or 0) <= MAX_SMALL_EVIDENCE_BYTES
        ):
            raise EnrichmentDiagnosticError(
                "subscription PDF is outside the small-file boundary",
                category="policy_error",
                code="pdf_size_outside_small_file_boundary",
                stage="pdf_acquisition",
            )
        return value

    @staticmethod
    def _validate_ocr_result(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not str(value.get("engine") or "").strip():
            raise EnrichmentError("OCR result is invalid")
        rows = value.get("lines")
        if not isinstance(rows, list) or not rows:
            raise EnrichmentError("OCR produced no text lines")
        normalized = []
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("text") or "").strip():
                raise EnrichmentError("OCR line is invalid")
            try:
                confidence = float(row.get("confidence"))
            except (TypeError, ValueError) as exc:
                raise EnrichmentError("OCR confidence is invalid") from exc
            box = row.get("bounding_box")
            if (
                not 0 <= confidence <= 1
                or not isinstance(box, list)
                or len(box) != 4
            ):
                raise EnrichmentError("OCR line geometry is invalid")
            normalized.append(
                {
                    "text": str(row["text"]).strip(),
                    "confidence": round(confidence, 6),
                    "bounding_box": [float(value) for value in box],
                }
            )
        return {"engine": str(value["engine"]).strip(), "lines": normalized}

    @staticmethod
    def _ocr_ambiguity(row: dict[str, Any]) -> dict[str, Any] | None:
        text = str(row["text"])
        reasons: list[str] = []
        if float(row["confidence"]) < 0.75:
            reasons.append("low_confidence")
        if any(marker in text for marker in ("?", "？", "�", "□")):
            reasons.append("uncertain_glyph")
        if not reasons:
            return None
        return {**row, "reasons": reasons}

    @staticmethod
    def _default_ocr_runner(path: Path) -> dict[str, Any]:
        helper = Path(__file__).resolve().parents[3] / "scripts" / "kol_vision_ocr.swift"
        if not helper.is_file():
            raise EnrichmentError("macOS Vision OCR helper is unavailable")
        try:
            result = subprocess.run(
                ("swift", str(helper), str(path)),
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EnrichmentError("macOS Vision OCR could not run") from exc
        if result.returncode != 0:
            raise EnrichmentError("macOS Vision OCR failed")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise EnrichmentError("macOS Vision OCR returned invalid JSON") from exc
        return value

    @staticmethod
    def _default_pdf_text_extractor(path: Path) -> dict[str, Any]:
        """Extract native text and visual-resource hints without online services."""
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise EnrichmentDiagnosticError(
                "local PDF text extraction dependency is unavailable",
                category="dependency_error",
                code="pdf_text_extractor_unavailable",
                stage="pdf_extraction",
            ) from exc
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                raise EnrichmentDiagnosticError(
                    "encrypted subscription PDF requires reviewed handling",
                    category="policy_error",
                    code="pdf_encrypted",
                    stage="pdf_extraction",
                )
            if not 0 < len(reader.pages) <= MAX_PDF_PAGES:
                raise EnrichmentDiagnosticError(
                    "subscription PDF page count is outside the boundary",
                    category="policy_error",
                    code="pdf_page_count_outside_boundary",
                    stage="pdf_extraction",
                )
            pages: list[dict[str, Any]] = []
            for index, page in enumerate(reader.pages, start=1):
                text = str(page.extract_text() or "").strip()
                resources = page.get("/Resources") or {}
                xobjects = resources.get("/XObject") if hasattr(resources, "get") else None
                has_visuals = False
                if xobjects:
                    try:
                        for value in xobjects.get_object().values():
                            target = value.get_object()
                            if target.get("/Subtype") == "/Image":
                                has_visuals = True
                                break
                    except (AttributeError, KeyError, TypeError, ValueError):
                        has_visuals = True
                pages.append(
                    {
                        "page": index,
                        "text": text,
                        "has_visuals": has_visuals,
                    }
                )
        except EnrichmentDiagnosticError:
            raise
        except Exception as exc:
            raise EnrichmentDiagnosticError(
                "subscription PDF could not be parsed locally",
                category="content_error",
                code="pdf_invalid",
                stage="pdf_extraction",
            ) from exc

        missing = [
            row["page"]
            for row in pages
            if len(str(row["text"]).strip()) < MIN_NATIVE_PDF_PAGE_TEXT
        ]
        if missing:
            try:
                import pdfplumber

                with pdfplumber.open(str(path)) as document:
                    if len(document.pages) != len(pages):
                        raise EnrichmentError(
                            "PDF extractors disagree on page count"
                        )
                    for page_number in missing:
                        fallback = str(
                            document.pages[page_number - 1].extract_text() or ""
                        ).strip()
                        if len(fallback) > len(pages[page_number - 1]["text"]):
                            pages[page_number - 1]["text"] = fallback
            except ImportError:
                pass
            except EnrichmentError:
                raise
            except Exception as exc:
                raise EnrichmentDiagnosticError(
                    "subscription PDF fallback extraction failed",
                    category="content_error",
                    code="pdf_fallback_extraction_failed",
                    stage="pdf_extraction",
                ) from exc
        return {"engine": "pypdf+pdfplumber", "pages": pages}

    @staticmethod
    def _default_pdf_renderer(
        path: Path,
        output_dir: Path,
        pages: list[int],
    ) -> dict[int, Path]:
        executable = shutil.which("pdftoppm")
        if executable is None:
            raise EnrichmentDiagnosticError(
                "local PDF renderer is unavailable",
                category="dependency_error",
                code="pdf_renderer_unavailable",
                stage="pdf_visual_coverage",
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        rendered: dict[int, Path] = {}
        for page_number in pages:
            prefix = output_dir / f"page-{page_number:04d}"
            try:
                result = subprocess.run(
                    (
                        executable,
                        "-f",
                        str(page_number),
                        "-l",
                        str(page_number),
                        "-r",
                        "150",
                        "-png",
                        str(path),
                        str(prefix),
                    ),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise EnrichmentDiagnosticError(
                    "subscription PDF page rendering failed",
                    category="content_error",
                    code="pdf_render_failed",
                    stage="pdf_visual_coverage",
                ) from exc
            candidates = sorted(output_dir.glob(f"{prefix.name}*.png"))
            if result.returncode != 0 or len(candidates) != 1:
                raise EnrichmentDiagnosticError(
                    "subscription PDF page rendering failed",
                    category="content_error",
                    code="pdf_render_failed",
                    stage="pdf_visual_coverage",
                )
            rendered[page_number] = candidates[0]
        return rendered

    @_exclusive("item")
    def claim_browser_download(self, identity: str) -> dict[str, Any]:
        """Persist the exact source version before any browser download click."""
        item = self._manifest_item(str(identity))
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        claim_path = artifact_dir / "browser_download_claim.json"
        receipt_path = artifact_dir / "browser_download_receipt.json"
        if claim_path.is_file():
            try:
                prior = json.loads(claim_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "subscription browser download claim is invalid"
                ) from exc
            if (
                prior.get("identity") != item["identity"]
                or prior.get("version_key") != item["version_key"]
            ):
                raise EnrichmentError(
                    "subscription browser download claim changed source version"
                )
            if prior.get("status") == "completed":
                if not receipt_path.is_file():
                    raise EnrichmentError(
                        "subscription browser download receipt is missing"
                    )
                return {**prior, "idempotent_replay": True}
            if prior.get("status") == "failed_before_trigger":
                retry = {
                    **prior,
                    "status": "claimed",
                    "attempt": int(prior.get("attempt") or 1) + 1,
                    "claimed_at": self._time().isoformat(
                        timespec="seconds"
                    ),
                    "previous_failure_reason": prior.get(
                        "failure_reason"
                    ),
                    "failure_reason": None,
                    "failed_at": None,
                    "idempotent_replay": False,
                }
                _atomic_write_json(claim_path, retry)
                _append_jsonl(
                    self.events_path,
                    {
                        key: value
                        for key, value in retry.items()
                        if key
                        not in {
                            "previous_failure_reason",
                            "failure_reason",
                            "failed_at",
                            "idempotent_replay",
                        }
                    },
                )
                return retry
            if prior.get("status") != "claimed":
                raise EnrichmentError(
                    "subscription browser download claim has invalid state"
                )
            return {**prior, "idempotent_replay": True}

        claim_id = hashlib.sha256(
            (
                "lv-browser-download\n"
                f"{item['identity']}\n{item['version_key']}"
            ).encode("utf-8")
        ).hexdigest()
        claim = {
            "event": "subscription_browser_download_claimed",
            "status": "claimed",
            "claim_id": claim_id,
            "source": "baidu_subscription_share_browser",
            "author": "吕晓彤",
            "identity": str(item["identity"]),
            "version_key": str(item["version_key"]),
            "title": str(item["name"]),
            "media_type": str(item["media_type"]),
            "expected_size": int(item.get("size") or 0),
            "attempt": 1,
            "claimed_at": self._time().isoformat(timespec="seconds"),
            "idempotent_replay": False,
        }
        _atomic_write_json(claim_path, claim)
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in claim.items()
                if key != "idempotent_replay"
            },
        )
        return claim

    @_exclusive("item")
    def _record_browser_download_pretrigger_failure(
        self,
        identity: str,
        *,
        claim_id: str,
        reason: str,
    ) -> dict[str, Any]:
        if reason not in _DOWNLOAD_PRETRIGGER_FAILURES:
            raise EnrichmentError(
                "subscription browser failure is not proven pre-trigger"
            )
        item = self._manifest_item(str(identity))
        claim_path = (
            self.output_dir
            / "artifacts"
            / str(item["version_key"])
            / "browser_download_claim.json"
        )
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                "subscription browser download claim is invalid"
            ) from exc
        if (
            claim.get("claim_id") != claim_id
            or claim.get("status") != "claimed"
        ):
            raise EnrichmentError(
                "subscription browser download failure changed claim"
            )
        failed = {
            **claim,
            "status": "failed_before_trigger",
            "failure_reason": reason,
            "failed_at": self._time().isoformat(timespec="seconds"),
        }
        _atomic_write_json(claim_path, failed)
        _append_jsonl(
            self.events_path,
            {
                "event": "subscription_browser_download_pretrigger_failed",
                "source": "baidu_subscription_share_browser",
                "author": "吕晓彤",
                "identity": str(item["identity"]),
                "version_key": str(item["version_key"]),
                "claim_id": claim_id,
                "reason": reason,
                "failed_at": failed["failed_at"],
            },
        )
        return failed

    def reconcile_filtered_image_preview(
        self,
        identity: str,
        *,
        session: str,
        profile: str | None,
        listing: dict[str, Any],
    ) -> dict[str, Any]:
        """Complete one filtered image claim from an exact read-only preview."""
        item = self._manifest_item(str(identity))
        completed = self._completed_browser_receipt(item)
        if completed is not None:
            return {**completed, "idempotent_replay": True}
        if (
            item.get("media_type") != "image"
            or listing.get("status") != "ok"
            or not isinstance(listing.get("entries"), list)
            or (
                listing.get("complete_scan") is not True
                and not (
                    isinstance(listing.get("coverage"), Mapping)
                    and _covered_by_listing(
                        str(item.get("path") or ""), listing["coverage"]
                    )
                )
            )
        ):
            raise EnrichmentDiagnosticError(
                "filtered image preview lacks a complete source listing",
                category="incomplete_scan",
                code="provider_preview_listing_invalid",
                stage="provider_preview_reconciliation",
            )
        matches: list[dict[str, Any]] = []
        for raw in listing["entries"]:
            if not isinstance(raw, dict):
                continue
            normalized = self._normalize_entry(raw)
            if (
                normalized["identity"] == item["identity"]
                and normalized["version_key"] == item["version_key"]
                and normalized["path"] == item["path"]
                and normalized["name"] == item["name"]
                and normalized["size"] == item["size"]
            ):
                matches.append(raw)
        if len(matches) != 1:
            raise EnrichmentDiagnosticError(
                "filtered image preview target is not unique",
                category="identity_error",
                code="provider_preview_target_not_unique",
                stage="provider_preview_reconciliation",
            )
        provider_file_id = str(
            matches[0].get("provider_file_id") or ""
        ).strip()
        if not provider_file_id.isdigit():
            raise EnrichmentDiagnosticError(
                "filtered image preview provider identity is invalid",
                category="identity_error",
                code="provider_preview_identity_invalid",
                stage="provider_preview_reconciliation",
            )
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        claim_path = artifact_dir / "browser_download_claim.json"
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                "filtered image preview claim is invalid"
            ) from exc
        if (
            claim.get("status") != "claimed"
            or claim.get("identity") != item["identity"]
            or claim.get("version_key") != item["version_key"]
            or claim.get("media_type") != "image"
            or int(claim.get("expected_size") or 0) != int(item["size"])
        ):
            raise EnrichmentError(
                "filtered image preview changed the acquisition claim"
            )
        parent_path = str(PurePosixPath(str(item["path"])).parent)
        route = urlparse(
            _authorized_share_url(self.share_url, self.share_code)
        )._replace(fragment=f"list/path={quote(parent_path, safe='')}").geturl()
        preview_script = _filtered_image_preview_script(
            expected_share_path=urlparse(self.share_url).path,
            expected_provider_file_id=provider_file_id,
            expected_item_path=str(item["path"]),
            expected_name=str(item["name"]),
        )
        for attempt in range(2):
            try:
                self._opencli_json(
                    session,
                    "open",
                    route,
                    profile=profile,
                    timeout_seconds=30,
                )
                preview = self._opencli_json(
                    session,
                    "eval",
                    preview_script,
                    profile=profile,
                    timeout_seconds=30,
                )
                break
            except EnrichmentDiagnosticError as exc:
                if (
                    attempt == 0
                    and exc.diagnostic_code
                    in {"opencli_timeout", "opencli_command_failed"}
                    and exc.diagnostic_stage in {"browser_open", "browser_eval"}
                ):
                    try:
                        self.bind_opencli(
                            session=session,
                            profile=profile,
                        )
                    except EnrichmentError as bind_error:
                        raise exc from bind_error
                    continue
                raise
        if preview.get("status") != "preview_ready":
            raise EnrichmentDiagnosticError(
                "provider preview did not expose exact image evidence",
                category="provider_error",
                code="provider_preview_not_ready",
                stage="provider_preview_reconciliation",
            )
        preview_url = str(preview.get("download_url") or "")
        parsed = urlparse(preview_url)
        fid_values = parse_qs(parsed.query).get("fid") or []
        fid = str(fid_values[0] if len(fid_values) == 1 else "")
        width = int(preview.get("natural_width") or 0)
        height = int(preview.get("natural_height") or 0)
        if (
            parsed.scheme != "https"
            or _PREVIEW_DOWNLOAD_HOST.fullmatch(parsed.hostname or "") is None
            or not parsed.path.startswith("/thumbnail/")
            or not parsed.query
            or fid.split("-")[-1] != provider_file_id
            or preview.get("provider_file_id") != provider_file_id
            or preview.get("host") != parsed.hostname
            or preview.get("path") != parsed.path
            or not _valid_preview_dimensions(width, height)
        ):
            raise EnrichmentDiagnosticError(
                "provider preview changed source identity",
                category="identity_error",
                code="provider_preview_binding_invalid",
                stage="provider_preview_reconciliation",
            )
        destination = (
            self.download_inbox / str(item["version_key"]) / "provider_preview.jpg"
        ).resolve()
        if destination.parent.parent != self.download_inbox:
            raise EnrichmentError("provider preview destination is invalid")
        fetched = self.preview_fetcher(preview_url, destination)
        preview.pop("download_url", None)
        path = Path(str(fetched.get("path") or "")).resolve()
        if (
            path != destination
            or not path.is_file()
            or path.stat().st_size <= 0
            or int(fetched.get("actual_size") or 0) != path.stat().st_size
            or fetched.get("content_type") != "image/jpeg"
            or fetched.get("sha256") != _sha256_file(path)
            or not path.read_bytes()[:3].startswith(b"\xff\xd8\xff")
        ):
            raise EnrichmentDiagnosticError(
                "provider preview derivative receipt is invalid",
                category="identity_error",
                code="provider_preview_receipt_invalid",
                stage="provider_preview_reconciliation",
            )
        return self.complete_browser_download(
            str(item["identity"]),
            path,
            claim_id=str(claim["claim_id"]),
            acquisition_transport="provider_preview_derivative",
            source_byte_exact=False,
            source_provider_file_id=provider_file_id,
            preview_pixel_width=width,
            preview_pixel_height=height,
        )

    @_exclusive("item")
    def complete_browser_download(
        self,
        identity: str,
        downloaded_path: Path | str,
        *,
        claim_id: str,
        acquisition_transport: str = "browser_download",
        source_byte_exact: bool = True,
        source_provider_file_id: str | None = None,
        preview_pixel_width: int | None = None,
        preview_pixel_height: int | None = None,
    ) -> dict[str, Any]:
        """Snapshot one browser download against its pre-action source claim."""
        item = self._manifest_item(str(identity))
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        claim_path = artifact_dir / "browser_download_claim.json"
        receipt_path = artifact_dir / "browser_download_receipt.json"
        if not claim_path.is_file():
            raise EnrichmentError(
                "subscription browser download requires a pre-action claim"
            )
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                "subscription browser download claim is invalid"
            ) from exc
        if (
            claim.get("claim_id") != str(claim_id)
            or claim.get("identity") != item["identity"]
            or claim.get("version_key") != item["version_key"]
        ):
            raise EnrichmentError(
                "subscription browser download claim does not match source version"
            )
        if receipt_path.is_file():
            try:
                prior = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "subscription browser download receipt is invalid"
                ) from exc
            immutable = self._artifact_bound_file(
                prior.get("immutable_path"),
                artifact_dir=artifact_dir,
                expected_sha256=prior.get("sha256"),
                error_message=(
                    "subscription browser download changed after capture"
                ),
            )
            return {
                **prior,
                "immutable_path": str(immutable),
                "idempotent_replay": True,
            }
        if claim.get("status") != "claimed":
            raise EnrichmentError(
                "subscription browser download claim is not pending"
            )

        source = Path(downloaded_path).expanduser().resolve()
        if not source.is_file():
            raise EnrichmentError("browser-downloaded subscription file is missing")
        actual_size = source.stat().st_size
        if actual_size <= 0 or actual_size > MAX_SMALL_EVIDENCE_BYTES:
            raise EnrichmentError(
                "subscription evidence size is outside the small-file boundary"
            )
        if source_byte_exact:
            if int(item.get("size") or 0) and actual_size != int(item["size"]):
                raise EnrichmentError(
                    "browser-downloaded subscription file size changed"
                )
            if source.name != item.get("name"):
                raise EnrichmentError(
                    "browser-downloaded subscription filename changed"
                )
        else:
            if (
                acquisition_transport != "provider_preview_derivative"
                or item.get("media_type") != "image"
                or source.name != "provider_preview.jpg"
                or not str(source_provider_file_id or "").isdigit()
                or not isinstance(preview_pixel_width, int)
                or not isinstance(preview_pixel_height, int)
                or not _valid_preview_dimensions(
                    preview_pixel_width,
                    preview_pixel_height,
                )
                or not source.read_bytes()[:3].startswith(b"\xff\xd8\xff")
            ):
                raise EnrichmentError(
                    "provider preview derivative is not evidence-bound"
                )

        artifact_dir.mkdir(parents=True, exist_ok=True)
        immutable = artifact_dir / (
            "browser_preview.jpg"
            if not source_byte_exact
            else f"browser_original{source.suffix.lower()}"
        )
        temporary = artifact_dir / f".{immutable.name}.partial"
        shutil.copyfile(source, temporary)
        temporary.replace(immutable)
        receipt = {
            "event": "subscription_browser_download_completed",
            "status": "completed",
            "claim_id": str(claim_id),
            "source": "baidu_subscription_share_browser",
            "author": "吕晓彤",
            "identity": str(item["identity"]),
            "version_key": str(item["version_key"]),
            "title": str(item["name"]),
            "media_type": str(item["media_type"]),
            "expected_size": int(item.get("size") or 0),
            "actual_size": actual_size,
            "acquisition_transport": acquisition_transport,
            "source_byte_exact": source_byte_exact,
            "source_provider_file_id": (
                str(source_provider_file_id)
                if not source_byte_exact
                else None
            ),
            "preview_pixel_width": (
                preview_pixel_width if not source_byte_exact else None
            ),
            "preview_pixel_height": (
                preview_pixel_height if not source_byte_exact else None
            ),
            "immutable_path": str(immutable.resolve()),
            "sha256": _sha256_file(immutable),
            "claimed_at": claim["claimed_at"],
            "completed_at": self._time().isoformat(timespec="seconds"),
            "idempotent_replay": False,
        }
        _atomic_write_json(receipt_path, receipt)
        completed_claim = {
            **claim,
            "status": "completed",
            "receipt_path": str(receipt_path.resolve()),
            "receipt_sha256": _sha256_file(receipt_path),
            "completed_at": receipt["completed_at"],
        }
        _atomic_write_json(claim_path, completed_claim)
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in receipt.items()
                if key
                not in {
                    "immutable_path",
                    "sha256",
                    "idempotent_replay",
                }
            },
        )
        return receipt

    @staticmethod
    def _artifact_bound_file(
        recorded_path: Any,
        *,
        artifact_dir: Path,
        expected_sha256: Any,
        error_message: str,
    ) -> Path:
        """Resolve a transferred artifact by exact local role and hash."""
        raw_path = str(recorded_path or "").strip()
        expected = str(expected_sha256 or "").strip()
        if not raw_path or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise EnrichmentError(error_message)
        recorded = Path(raw_path).expanduser()
        candidates = [recorded]
        if recorded.name not in {"", ".", ".."}:
            local = artifact_dir / recorded.name
            if local != recorded:
                candidates.append(local)
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if (
                resolved.is_file()
                and _sha256_file(resolved) == expected
                and (
                    candidate == recorded
                    or resolved.parent == artifact_dir.resolve()
                )
            ):
                return resolved
        raise EnrichmentError(error_message)

    def _rebased_ingest_result(
        self,
        item: dict[str, Any],
        ingest: dict[str, Any],
    ) -> dict[str, Any]:
        """Rebind transferred ingest paths without weakening their hashes."""
        if (
            ingest.get("identity") != item["identity"]
            or ingest.get("version_key") != item["version_key"]
        ):
            raise EnrichmentError("subscription ingest result is invalid")
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        rebased = dict(ingest)
        for path_key, hash_key in (
            ("original_path", "original_sha256"),
            ("evidence_path", "evidence_sha256"),
            ("ocr_path", "ocr_sha256"),
            ("pdf_coverage_path", "pdf_coverage_sha256"),
        ):
            recorded_path = ingest.get(path_key)
            expected_hash = ingest.get(hash_key)
            if not str(recorded_path or "").strip() and expected_hash is None:
                continue
            resolved = self._artifact_bound_file(
                recorded_path,
                artifact_dir=artifact_dir,
                expected_sha256=expected_hash,
                error_message=(
                    "subscription evidence changed after ingestion"
                ),
            )
            rebased[path_key] = str(resolved)
        return rebased

    def _completed_browser_receipt(
        self,
        item: dict[str, Any],
    ) -> dict[str, Any] | None:
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        receipt_path = artifact_dir / "browser_download_receipt.json"
        if not receipt_path.is_file():
            return None
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                "subscription browser download receipt is invalid"
            ) from exc
        if (
            receipt.get("status") != "completed"
            or receipt.get("identity") != item["identity"]
            or receipt.get("version_key") != item["version_key"]
        ):
            raise EnrichmentError(
                "subscription browser download receipt is not evidence-bound"
            )
        immutable = self._artifact_bound_file(
            receipt.get("immutable_path"),
            artifact_dir=artifact_dir,
            expected_sha256=receipt.get("sha256"),
            error_message=(
                "subscription browser download receipt is not evidence-bound"
            ),
        )
        return {**receipt, "immutable_path": str(immutable)}

    def _wait_opencli_download(
        self,
        item: dict[str, Any],
        *,
        session: str,
        profile: str | None,
        timeout_seconds: int,
    ) -> Path:
        waited = self._opencli_json(
            session,
            "wait",
            "download",
            str(item["name"]),
            "--timeout",
            str(timeout_seconds * 1000),
            profile=profile,
            timeout_seconds=timeout_seconds + 10,
        )
        filename = str(waited.get("filename") or "").strip()
        if (
            waited.get("downloaded") is not True
            or waited.get("state") != "complete"
            or not filename
        ):
            raise EnrichmentError(
                "subscription browser download outcome is uncertain"
            )
        return Path(filename)

    def _rebind_download_confirmation_session(
        self,
        item: dict[str, Any],
        *,
        session: str,
        profile: str | None,
        operation: str = "ticket04_download_confirmation_route_readback",
    ) -> None:
        """Rebind and read back the exact parent before a safe retry."""
        parent_path = str(PurePosixPath(str(item["path"])).parent)
        route = urlparse(
            _authorized_share_url(self.share_url, self.share_code)
        )._replace(fragment=f"list/path={quote(parent_path, safe='')}").geturl()
        self._rebind_opencli_parent_route(
            session=session,
            profile=profile,
            route=route,
            expected_parent_path=parent_path,
            operation=operation,
        )

    def _download_confirmation_eval(
        self,
        item: dict[str, Any],
        *,
        session: str,
        profile: str | None,
        script: str,
    ) -> dict[str, Any]:
        """Evaluate the pre-trigger selector with one exact-tab recovery."""
        retryable_codes = {
            "detached_mid_command",
            "opencli_command_failed",
            "opencli_timeout",
        }
        for attempt in range(2):
            try:
                return self._opencli_json(
                    session,
                    "eval",
                    script,
                    profile=profile,
                    timeout_seconds=30,
                )
            except EnrichmentDiagnosticError as exc:
                if (
                    attempt != 0
                    or exc.diagnostic_stage != "browser_eval"
                    or exc.diagnostic_code not in retryable_codes
                ):
                    raise
                try:
                    # This script only selects the exact provider row and
                    # marks its download control; it has not triggered a
                    # download, so reopening the same parent route is safe.
                    self._rebind_download_confirmation_session(
                        item,
                        session=session,
                        profile=profile,
                    )
                except EnrichmentError as bind_error:
                    raise exc from bind_error
        raise AssertionError("download confirmation eval retry exhausted")

    def _prepare_opencli_download_confirmation(
        self,
        item: dict[str, Any],
        *,
        session: str,
        profile: str | None,
        defer_trigger: bool = False,
    ) -> dict[str, Any]:
        """Select one provider row and natively open its download choice."""
        script = _browser_download_script(
            expected_share_path=urlparse(self.share_url).path,
            expected_item_path=str(item["path"]),
            expected_name=str(item["name"]),
        )
        prepared = self._download_confirmation_eval(
            item,
            session=session,
            profile=profile,
            script=script,
        )
        if prepared.get("status") in {
            "target_not_visible",
            "download_confirmation_missing",
        }:
            self.sleep(1.0)
            prepared = self._download_confirmation_eval(
                item,
                session=session,
                profile=profile,
                script=script,
            )
        if prepared.get("status") == "download_confirmation_ready":
            return prepared
        if prepared.get("status") != "download_control_ready":
            return prepared
        if defer_trigger:
            return prepared
        clicked = self._opencli_json(
            session,
            "click",
            "a[data-xiaocao-download-open='1']",
            profile=profile,
            timeout_seconds=30,
        )
        if clicked.get("clicked") is not True or clicked.get("matches_n") != 1:
            return {"status": "download_control_click_failed"}
        return self._opencli_json(
            session,
            "eval",
            _BROWSER_DOWNLOAD_CONFIRMATION_SCRIPT,
            profile=profile,
            timeout_seconds=15,
        )

    @staticmethod
    def _default_direct_download_fetcher(
        download_url: str,
        destination: Path,
        expected_size: int,
        media_type: str,
    ) -> dict[str, Any]:
        """Stream one signed small file without logging URL or credentials."""
        if media_type not in _DIRECT_DOWNLOAD_MEDIA:
            raise EnrichmentDiagnosticError(
                "provider direct download media is outside the safe boundary",
                category="policy_error",
                code="provider_direct_media_not_allowed",
                stage="provider_direct_download",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not destination.is_file() or destination.stat().st_size != expected_size:
                raise EnrichmentDiagnosticError(
                    "controlled download inbox contains a conflicting file",
                    category="identity_error",
                    code="controlled_inbox_collision",
                    stage="provider_direct_download",
                )
            return {
                "path": str(destination),
                "actual_size": destination.stat().st_size,
                "content_type": "application/octet-stream",
                "sha256": _sha256_file(destination),
            }
        request = Request(
            download_url,
            headers={
                "Accept": {
                    "image": "image/png,image/jpeg,image/webp,application/octet-stream",
                    "pdf": "application/pdf,application/octet-stream",
                    "text": "text/plain,application/octet-stream",
                }[media_type],
                "Referer": "https://pan.baidu.com/",
                "User-Agent": "Mozilla/5.0",
            },
            method="GET",
        )
        temporary = destination.with_name(f".{destination.name}.partial")
        if temporary.exists():
            raise EnrichmentDiagnosticError(
                "controlled download inbox has an unfinished transfer",
                category="uncertain_state",
                code="controlled_inbox_partial_exists",
                stage="provider_direct_download",
            )
        digest = hashlib.sha256()
        actual_size = 0
        content_type = ""
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                content_type = str(
                    response.headers.get_content_type() or ""
                ).lower()
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) != expected_size:
                    raise EnrichmentDiagnosticError(
                        "provider direct download size changed",
                        category="identity_error",
                        code="provider_download_size_mismatch",
                        stage="provider_direct_download",
                    )
                if content_type not in _DIRECT_DOWNLOAD_CONTENT_TYPES[media_type]:
                    raise EnrichmentDiagnosticError(
                        "provider direct download content type is invalid",
                        category="content_error",
                        code="provider_download_content_type_invalid",
                        stage="provider_direct_download",
                    )
                with temporary.open("xb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        actual_size += len(chunk)
                        if actual_size > expected_size:
                            raise EnrichmentDiagnosticError(
                                "provider direct download exceeded expected size",
                                category="identity_error",
                                code="provider_download_size_mismatch",
                                stage="provider_direct_download",
                            )
                        digest.update(chunk)
                        handle.write(chunk)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise EnrichmentDiagnosticError(
                    "provider authentication is required",
                    category="authentication_error",
                    code="provider_authentication_required",
                    stage="browser_download_authorization",
                ) from exc
            raise EnrichmentDiagnosticError(
                "provider direct download failed",
                category="provider_error",
                code="provider_direct_http_failed",
                stage="provider_direct_download",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise EnrichmentDiagnosticError(
                "provider direct download transport failed",
                category="transport_error",
                code="provider_direct_transport_failed",
                stage="provider_direct_download",
            ) from exc
        finally:
            if temporary.exists() and actual_size != expected_size:
                temporary.unlink()
        if actual_size != expected_size:
            raise EnrichmentDiagnosticError(
                "provider direct download size changed",
                category="identity_error",
                code="provider_download_size_mismatch",
                stage="provider_direct_download",
            )
        temporary.replace(destination)
        if media_type == "pdf" and destination.read_bytes()[:5] != b"%PDF-":
            raise EnrichmentDiagnosticError(
                "provider direct PDF signature is invalid",
                category="content_error",
                code="provider_download_content_invalid",
                stage="provider_direct_download",
            )
        if media_type == "image":
            prefix = destination.read_bytes()[:12]
            suffix = destination.suffix.lower()
            valid_signature = (
                suffix == ".png" and prefix.startswith(b"\x89PNG\r\n\x1a\n")
            ) or (
                suffix in {".jpg", ".jpeg"} and prefix.startswith(b"\xff\xd8\xff")
            ) or (
                suffix == ".webp"
                and prefix.startswith(b"RIFF")
                and prefix[8:12] == b"WEBP"
            )
            if not valid_signature:
                raise EnrichmentDiagnosticError(
                    "provider direct image signature is invalid",
                    category="content_error",
                    code="provider_download_content_invalid",
                    stage="provider_direct_download",
                )
        if media_type == "text":
            try:
                destination.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise EnrichmentDiagnosticError(
                    "provider direct text is not UTF-8",
                    category="content_error",
                    code="provider_download_content_invalid",
                    stage="provider_direct_download",
                ) from exc
        return {
            "path": str(destination),
            "actual_size": actual_size,
            "content_type": content_type,
            "sha256": digest.hexdigest(),
        }

    @staticmethod
    def _default_preview_fetcher(
        preview_url: str,
        destination: Path,
    ) -> dict[str, Any]:
        """Stream one identity-bound provider preview without logging its URL."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise EnrichmentDiagnosticError(
                "controlled preview inbox contains an unreconciled file",
                category="uncertain_state",
                code="preview_inbox_collision",
                stage="provider_preview_reconciliation",
            )
        request = Request(
            preview_url,
            headers={
                "Accept": "image/jpeg",
                "Referer": "https://pan.baidu.com/",
                "User-Agent": "Mozilla/5.0",
            },
            method="GET",
        )
        temporary = destination.with_name(f".{destination.name}.partial")
        if temporary.exists():
            raise EnrichmentDiagnosticError(
                "controlled preview inbox has an unfinished transfer",
                category="uncertain_state",
                code="preview_inbox_partial_exists",
                stage="provider_preview_reconciliation",
            )
        digest = hashlib.sha256()
        actual_size = 0
        content_type = ""
        stream_completed = False
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                content_type = str(
                    response.headers.get_content_type() or ""
                ).lower()
                if content_type != "image/jpeg":
                    raise EnrichmentDiagnosticError(
                        "provider preview content type is invalid",
                        category="content_error",
                        code="provider_preview_content_type_invalid",
                        stage="provider_preview_reconciliation",
                    )
                with temporary.open("xb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        actual_size += len(chunk)
                        if actual_size > MAX_SMALL_EVIDENCE_BYTES:
                            raise EnrichmentDiagnosticError(
                                "provider preview exceeded the evidence boundary",
                                category="content_error",
                                code="provider_preview_oversized",
                                stage="provider_preview_reconciliation",
                            )
                        digest.update(chunk)
                        handle.write(chunk)
            stream_completed = True
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise EnrichmentDiagnosticError(
                    "provider preview authentication is required",
                    category="authentication_error",
                    code="provider_authentication_required",
                    stage="browser_download_authorization",
                ) from exc
            raise EnrichmentDiagnosticError(
                "provider preview fetch failed",
                category="provider_error",
                code="provider_preview_http_failed",
                stage="provider_preview_reconciliation",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise EnrichmentDiagnosticError(
                "provider preview transport failed",
                category="transport_error",
                code="provider_preview_transport_failed",
                stage="provider_preview_reconciliation",
            ) from exc
        finally:
            if temporary.exists() and not stream_completed:
                temporary.unlink()
        if actual_size <= 0:
            raise EnrichmentDiagnosticError(
                "provider preview is empty",
                category="content_error",
                code="provider_preview_empty",
                stage="provider_preview_reconciliation",
            )
        if not temporary.read_bytes()[:3].startswith(b"\xff\xd8\xff"):
            temporary.unlink()
            raise EnrichmentDiagnosticError(
                "provider preview is not a JPEG image",
                category="content_error",
                code="provider_preview_content_invalid",
                stage="provider_preview_reconciliation",
            )
        temporary.replace(destination)
        return {
            "path": str(destination),
            "actual_size": actual_size,
            "content_type": content_type,
            "sha256": digest.hexdigest(),
        }

    def _default_owner_cloud_operator(
        self,
        item: dict[str, Any],
        _claim: dict[str, Any],
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        destination_directory = str(
            _OWNER_CLOUD_ROOT / str(item["version_key"])
        )
        return self._opencli_json(
            session,
            "eval",
            _owner_cloud_transfer_script(
                expected_share_path=urlparse(self.share_url).path,
                expected_provider_file_id=str(item["provider_file_id"]),
                expected_name=str(item["name"]),
                expected_size=int(item["size"]),
                destination_directory=destination_directory,
            ),
            profile=profile,
            timeout_seconds=45,
        )

    def _default_owner_download_link_reader(
        self,
        item: dict[str, Any],
        owner: dict[str, Any],
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        destination_directory = str(PurePosixPath(str(owner["owner_path"])).parent)
        owner_route = (
            "https://pan.baidu.com/disk/main#/index?"
            + urlencode({"category": "all", "path": destination_directory})
        )
        self._opencli_json(
            session,
            "open",
            owner_route,
            profile=profile,
            timeout_seconds=30,
        )
        return self._opencli_json(
            session,
            "eval",
            _owner_download_link_script(
                expected_provider_file_id=str(owner["owner_provider_file_id"]),
                expected_name=str(item["name"]),
                expected_size=int(item["size"]),
            ),
            profile=profile,
            timeout_seconds=30,
        )

    def _default_opencli_cookie_reader(
        self,
        session: str,
        profile: str | None,
    ) -> list[dict[str, Any]]:
        """Read target cookies through CDP; callers keep values in memory only."""
        opencli_binary = shutil.which(str(self.opencli_command[0]))
        node_binary = shutil.which("node")
        if not opencli_binary or not node_binary:
            raise EnrichmentDiagnosticError(
                "OpenCLI cookie transport is unavailable",
                category="local_runtime_error",
                code="opencli_cookie_transport_unavailable",
                stage="owner_cloud_download",
            )
        page_module = Path(opencli_binary).resolve().parent / "browser" / "page.js"
        if not page_module.is_file():
            raise EnrichmentDiagnosticError(
                "OpenCLI cookie transport is unavailable",
                category="local_runtime_error",
                code="opencli_cookie_transport_unavailable",
                stage="owner_cloud_download",
            )
        payload = {
            "module": str(page_module),
            "session": session,
            "profile": profile,
        }
        script = """
import {pathToFileURL} from 'node:url';
const input = JSON.parse(process.argv[1]);
const {Page} = await import(pathToFileURL(input.module).href);
const page = new Page(
  input.session, 20, input.profile || undefined, 'background'
);
const response = await page.cdp('Network.getAllCookies');
const cookies = (response.cookies || []).filter(row => {
  const domain = String(row.domain || '').replace(/^\\./, '');
  return domain === 'baidu.com' || domain.endsWith('.baidu.com');
}).map(row => ({
  name: String(row.name || ''),
  value: String(row.value || ''),
  domain: String(row.domain || ''),
  path: String(row.path || '/'),
  secure: row.secure === true,
  httpOnly: row.httpOnly === true
}));
console.log(JSON.stringify({cookies}));
"""
        try:
            completed = subprocess.run(
                (
                    node_binary,
                    "--input-type=module",
                    "-e",
                    script,
                    _canonical(payload),
                ),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            result = json.loads(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise EnrichmentDiagnosticError(
                "OpenCLI cookie readback failed",
                category="local_runtime_error",
                code="opencli_cookie_readback_failed",
                stage="owner_cloud_download",
            ) from exc
        cookies = result.get("cookies") if isinstance(result, dict) else None
        if completed.returncode != 0 or not isinstance(cookies, list):
            raise EnrichmentDiagnosticError(
                "OpenCLI cookie readback failed",
                category="local_runtime_error",
                code="opencli_cookie_readback_failed",
                stage="owner_cloud_download",
            )
        return cookies

    def _default_owner_authenticated_streamer(
        self,
        item: dict[str, Any],
        owner: dict[str, Any],
        session: str,
        profile: str | None,
        destination: Path,
    ) -> dict[str, Any]:
        """Resolve dlink/cookies and stream in one process without emitting them."""
        destination_directory = str(PurePosixPath(str(owner["owner_path"])).parent)
        owner_route = (
            "https://pan.baidu.com/disk/main#/index?"
            + urlencode({"category": "all", "path": destination_directory})
        )
        opencli_binary = shutil.which(str(self.opencli_command[0]))
        node_binary = shutil.which("node")
        if not opencli_binary or not node_binary:
            raise EnrichmentDiagnosticError(
                "owner authenticated stream transport is unavailable",
                category="local_runtime_error",
                code="owner_stream_transport_unavailable",
                stage="owner_cloud_download",
            )
        page_module = Path(opencli_binary).resolve().parent / "browser" / "page.js"
        if not page_module.is_file():
            raise EnrichmentDiagnosticError(
                "owner authenticated stream transport is unavailable",
                category="local_runtime_error",
                code="owner_stream_transport_unavailable",
                stage="owner_cloud_download",
            )
        payload = {
            "module": str(page_module),
            "session": session,
            "profile": profile,
            "ownerRoute": owner_route,
            "expression": _owner_download_link_script(
                expected_provider_file_id=str(owner["owner_provider_file_id"]),
                expected_name=str(item["name"]),
                expected_size=int(item["size"]),
            ),
            "destination": str(destination),
            "expectedSize": int(item["size"]),
        }
        script = r"""
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {promises as fs} from 'node:fs';

const input = JSON.parse(process.argv[1]);
const output = value => console.log(JSON.stringify(value));
const failure = code => {
  const error = new Error('owner stream failed');
  error.safeCode = code;
  throw error;
};
const digestFile = async path => {
  const data = await fs.readFile(path);
  return createHash('sha256').update(data).digest('hex');
};
const partial = input.destination.replace(/([^/]+)$/, '.$1.partial');
try {
  try {
    const existing = await fs.readFile(input.destination);
    if (
      existing.length !== input.expectedSize
      || existing.subarray(0, 5).toString() !== '%PDF-'
    ) failure('owner_download_inbox_collision');
    output({
      status: 'completed', path: input.destination,
      actual_size: existing.length, content_type: 'application/pdf',
      http_status: 200,
      sha256: createHash('sha256').update(existing).digest('hex')
    });
    process.exit(0);
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
  }
  const {Page} = await import(pathToFileURL(input.module).href);
  const page = new Page(
    input.session, 30, input.profile || undefined, 'foreground'
  );
  await page.goto(input.ownerRoute, {settleMs: 1000});
  const link = await page.evaluate(input.expression);
  if (link.status !== 'download_link_ready') {
    output({status: String(link.status || 'owner_download_link_failed')});
    process.exit(0);
  }
  const signedUrl = String(link.download_url || '');
  delete link.download_url;
  const parsed = new URL(signedUrl);
  if (
    parsed.protocol !== 'https:'
    || parsed.hostname !== 'd.pcs.baidu.com'
    || !parsed.search
  ) failure('owner_download_link_invalid');
  const cookies = (await page.getCookies({domain: 'baidu.com'})).filter(row => {
    const domain = String(row.domain || '').replace(/^\./, '');
    return domain === 'baidu.com' || domain.endsWith('.baidu.com');
  });
  if (!cookies.some(row => row.httpOnly === true)) {
    failure('owner_download_authentication_required');
  }
  const cookieHeader = cookies
    .filter(row => row.name && row.value && !/[\r\n;]/.test(row.name + row.value))
    .map(row => String(row.name) + '=' + String(row.value)).join('; ');
  if (!cookieHeader) failure('owner_download_authentication_required');
  const response = await fetch(signedUrl, {
    redirect: 'follow',
    headers: {
      accept: 'application/pdf,application/octet-stream',
      cookie: cookieHeader,
      referer: 'https://pan.baidu.com/disk/main',
      'user-agent': 'Mozilla/5.0'
    }
  });
  const finalUrl = new URL(response.url);
  const finalHostAllowed = finalUrl.hostname === 'd.pcs.baidu.com'
    || /^[a-z0-9-]+\.baidupcs\.com$/.test(finalUrl.hostname);
  if (
    response.status !== 200
    || finalUrl.protocol !== 'https:'
    || !finalHostAllowed
  ) failure('owner_download_http_invalid');
  const contentType = String(response.headers.get('content-type') || '')
    .split(';', 1)[0].trim().toLowerCase();
  if (![
    'application/pdf', 'application/octet-stream',
    'application/x-download', 'binary/octet-stream'
  ].includes(contentType)) failure('owner_download_content_type_invalid');
  const contentLength = response.headers.get('content-length');
  if (contentLength && Number(contentLength) !== input.expectedSize) {
    failure('owner_download_size_mismatch');
  }
  await fs.mkdir(input.destination.slice(0, input.destination.lastIndexOf('/')), {
    recursive: true
  });
  const handle = await fs.open(partial, 'wx');
  const hash = createHash('sha256');
  let actualSize = 0;
  try {
    const reader = response.body.getReader();
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      actualSize += value.byteLength;
      if (actualSize > input.expectedSize) failure('owner_download_size_mismatch');
      hash.update(value);
      await handle.write(value);
    }
  } finally {
    await handle.close();
  }
  if (actualSize !== input.expectedSize) failure('owner_download_size_mismatch');
  const header = Buffer.alloc(5);
  const verify = await fs.open(partial, 'r');
  try { await verify.read(header, 0, 5, 0); }
  finally { await verify.close(); }
  if (header.toString() !== '%PDF-') failure('owner_download_content_invalid');
  await fs.rename(partial, input.destination);
  output({
    status: 'completed', path: input.destination,
    actual_size: actualSize, content_type: contentType,
    http_status: response.status, sha256: hash.digest('hex')
  });
} catch (error) {
  try { await fs.unlink(partial); } catch (_error) {}
  output({status: String(error?.safeCode || 'owner_stream_failed')});
}
"""
        try:
            completed = subprocess.run(
                (
                    node_binary,
                    "--input-type=module",
                    "-e",
                    script,
                    _canonical(payload),
                ),
                capture_output=True,
                text=True,
                check=False,
                timeout=90,
            )
            result = json.loads(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise EnrichmentDiagnosticError(
                "owner authenticated stream failed",
                category="local_runtime_error",
                code="owner_stream_failed",
                stage="owner_cloud_download",
            ) from exc
        if completed.returncode != 0 or not isinstance(result, dict):
            raise EnrichmentDiagnosticError(
                "owner authenticated stream failed",
                category="local_runtime_error",
                code="owner_stream_failed",
                stage="owner_cloud_download",
            )
        status = str(result.get("status") or "")
        if status != "completed":
            category = (
                "authentication_error"
                if status in {
                    "auth_required",
                    "captcha_required",
                    "owner_download_authentication_required",
                }
                else "identity_error"
                if status in {
                    "owner_target_not_unique",
                    "owner_selection_mismatch",
                    "owner_download_link_invalid",
                    "owner_download_inbox_collision",
                    "owner_download_size_mismatch",
                }
                else "provider_error"
            )
            safe_code = (
                status
                if _SAFE_OPENCLI_ERROR_CODE.fullmatch(status)
                else "owner_stream_failed"
            )
            raise EnrichmentDiagnosticError(
                "owner authenticated stream did not complete",
                category=category,
                code=safe_code,
                stage="owner_cloud_download",
            )
        return result

    @staticmethod
    def _default_owner_download_fetcher(
        download_url: str,
        cookies: list[dict[str, Any]],
        destination: Path,
        expected_size: int,
    ) -> dict[str, Any]:
        """Stream one owner-side PDF without persisting URL or cookies."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if (
                not destination.is_file()
                or destination.stat().st_size != expected_size
                or destination.read_bytes()[:5] != b"%PDF-"
            ):
                raise EnrichmentDiagnosticError(
                    "owner download inbox contains a conflicting file",
                    category="identity_error",
                    code="owner_download_inbox_collision",
                    stage="owner_cloud_download",
                )
            return {
                "path": str(destination),
                "actual_size": expected_size,
                "content_type": "application/pdf",
                "http_status": 200,
                "sha256": _sha256_file(destination),
            }
        cookie_parts = []
        for row in cookies:
            name = str(row.get("name") or "")
            value = str(row.get("value") or "")
            if (
                not name
                or not value
                or any(character in name + value for character in "\r\n;")
            ):
                continue
            cookie_parts.append(f"{name}={value}")
        if not cookie_parts:
            raise EnrichmentDiagnosticError(
                "owner download authentication is unavailable",
                category="authentication_error",
                code="owner_download_authentication_required",
                stage="owner_cloud_download",
            )
        request = Request(
            download_url,
            headers={
                "Accept": "application/pdf,application/octet-stream",
                "Cookie": "; ".join(cookie_parts),
                "Referer": "https://pan.baidu.com/disk/main",
                "User-Agent": "Mozilla/5.0",
            },
            method="GET",
        )
        temporary = destination.with_name(f".{destination.name}.partial")
        if temporary.exists():
            raise EnrichmentDiagnosticError(
                "owner download inbox has an unfinished transfer",
                category="uncertain_state",
                code="owner_download_partial_exists",
                stage="owner_cloud_download",
            )
        digest = hashlib.sha256()
        actual_size = 0
        content_type = ""
        http_status = 0
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                http_status = int(getattr(response, "status", 0) or 0)
                final = urlparse(str(response.geturl() or ""))
                content_type = str(
                    response.headers.get_content_type() or ""
                ).lower()
                if (
                    http_status != 200
                    or final.scheme != "https"
                    or final.hostname not in _DIRECT_DOWNLOAD_HOSTS
                ):
                    raise EnrichmentDiagnosticError(
                        "owner download response is invalid",
                        category="provider_error",
                        code="owner_download_http_invalid",
                        stage="owner_cloud_download",
                    )
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) != expected_size:
                    raise EnrichmentDiagnosticError(
                        "owner download size changed",
                        category="identity_error",
                        code="owner_download_size_mismatch",
                        stage="owner_cloud_download",
                    )
                if content_type not in _DIRECT_DOWNLOAD_CONTENT_TYPES["pdf"]:
                    raise EnrichmentDiagnosticError(
                        "owner download content type is invalid",
                        category="content_error",
                        code="owner_download_content_type_invalid",
                        stage="owner_cloud_download",
                    )
                with temporary.open("xb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        actual_size += len(chunk)
                        if actual_size > expected_size:
                            raise EnrichmentDiagnosticError(
                                "owner download exceeded expected size",
                                category="identity_error",
                                code="owner_download_size_mismatch",
                                stage="owner_cloud_download",
                            )
                        digest.update(chunk)
                        handle.write(chunk)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise EnrichmentDiagnosticError(
                    "owner download authentication is required",
                    category="authentication_error",
                    code="owner_download_authentication_required",
                    stage="owner_cloud_download",
                ) from exc
            raise EnrichmentDiagnosticError(
                "owner download HTTP request failed",
                category="provider_error",
                code="owner_download_http_failed",
                stage="owner_cloud_download",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise EnrichmentDiagnosticError(
                "owner download transport failed",
                category="transport_error",
                code="owner_download_transport_failed",
                stage="owner_cloud_download",
            ) from exc
        finally:
            if temporary.exists() and actual_size != expected_size:
                temporary.unlink()
        if actual_size != expected_size:
            raise EnrichmentDiagnosticError(
                "owner download size changed",
                category="identity_error",
                code="owner_download_size_mismatch",
                stage="owner_cloud_download",
            )
        temporary.replace(destination)
        if destination.read_bytes()[:5] != b"%PDF-":
            raise EnrichmentDiagnosticError(
                "owner download PDF signature is invalid",
                category="content_error",
                code="owner_download_content_invalid",
                stage="owner_cloud_download",
            )
        return {
            "path": str(destination),
            "actual_size": actual_size,
            "content_type": content_type,
            "http_status": http_status,
            "sha256": digest.hexdigest(),
        }

    def _owner_cloud_transfer(
        self,
        item: dict[str, Any],
        claim: dict[str, Any],
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        """Create or reuse one exact owner-side copy under the parent claim."""
        if (
            item.get("media_type") != "pdf"
            or int(item.get("size") or 0) <= 0
            or int(item.get("size") or 0) > MAX_SMALL_EVIDENCE_BYTES
        ):
            raise EnrichmentDiagnosticError(
                "owner cloud fallback is limited to small PDFs",
                category="policy_error",
                code="owner_cloud_media_not_allowed",
                stage="owner_cloud_transfer",
            )
        provider_file_id = str(item.get("provider_file_id") or "")
        if not provider_file_id.isdigit():
            raise EnrichmentDiagnosticError(
                "owner cloud source identity is invalid",
                category="identity_error",
                code="owner_cloud_identity_invalid",
                stage="owner_cloud_transfer",
            )
        destination_directory = str(
            _OWNER_CLOUD_ROOT / str(item["version_key"])
        )
        destination_path = str(
            PurePosixPath(destination_directory) / str(item["name"])
        )
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        artifact_dir.mkdir(parents=True, exist_ok=True)
        claim_path = artifact_dir / "owner_cloud_transfer_claim.json"
        receipt_path = artifact_dir / "owner_cloud_transfer_receipt.json"
        binding = {
            "parent_acquisition_claim_id": str(claim["claim_id"]),
            "source_identity": str(item["identity"]),
            "source_version_key": str(item["version_key"]),
            "source_provider_file_id": provider_file_id,
            "source_name": str(item["name"]),
            "source_size": int(item["size"]),
            "destination_directory": destination_directory,
            "destination_path": destination_path,
        }
        if claim_path.is_file():
            try:
                transfer_claim = json.loads(claim_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError("owner cloud transfer claim is invalid") from exc
            if any(transfer_claim.get(key) != value for key, value in binding.items()):
                raise EnrichmentError("owner cloud transfer claim changed identity")
        else:
            transfer_claim = {
                "schema_version": 1,
                "event": "subscription_owner_cloud_transfer_claimed",
                "status": "claimed",
                "claim_id": hashlib.sha256(
                    (
                        "lv-owner-cloud-transfer\n"
                        f"{claim['claim_id']}\n{item['identity']}\n"
                        f"{item['version_key']}"
                    ).encode("utf-8")
                ).hexdigest(),
                **binding,
                "claimed_at": self._time().isoformat(timespec="seconds"),
            }
            _atomic_write_json(claim_path, transfer_claim)
        if receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError("owner cloud transfer receipt is invalid") from exc
            if (
                receipt.get("status") != "completed"
                or receipt.get("parent_acquisition_claim_id")
                != binding["parent_acquisition_claim_id"]
                or receipt.get("source_identity") != binding["source_identity"]
                or receipt.get("source_version_key")
                != binding["source_version_key"]
                or receipt.get("source_provider_file_id")
                != binding["source_provider_file_id"]
                or receipt.get("owner_path") != binding["destination_path"]
                or receipt.get("name") != binding["source_name"]
                or receipt.get("size") != binding["source_size"]
                or receipt.get("exact_match_count") != 1
                or not str(receipt.get("owner_provider_file_id") or "").isdigit()
            ):
                raise EnrichmentError("owner cloud transfer receipt is not evidence-bound")
            return {**receipt, "idempotent_replay": True}
        owner = self.owner_cloud_operator(item, transfer_claim, session, profile)
        if not isinstance(owner, dict):
            raise EnrichmentDiagnosticError(
                "owner cloud readback is invalid",
                category="provider_error",
                code="owner_cloud_readback_invalid",
                stage="owner_cloud_transfer",
            )
        status = str(owner.get("status") or "")
        if status == "auth_required":
            raise EnrichmentDiagnosticError(
                "owner cloud authentication is required",
                category="authentication_error",
                code="owner_cloud_authentication_required",
                stage="owner_cloud_transfer",
            )
        if status == "captcha_required":
            raise EnrichmentDiagnosticError(
                "owner cloud CAPTCHA is required",
                category="authentication_error",
                code="owner_cloud_captcha_required",
                stage="owner_cloud_transfer",
            )
        codes = {
            "owner_duplicate_matches": "owner_cloud_duplicate_matches",
            "owner_size_mismatch": "owner_cloud_size_mismatch",
            "owner_directory_ambiguous": "owner_cloud_directory_ambiguous",
        }
        if status != "owner_ready":
            provider_errno = owner.get("provider_errno")
            if isinstance(provider_errno, int) and not isinstance(
                provider_errno, bool
            ):
                errno_suffix = (
                    str(provider_errno)
                    if provider_errno >= 0
                    else f"neg{abs(provider_errno)}"
                )
                provider_code = f"owner_cloud_transfer_errno_{errno_suffix}"
            else:
                provider_code = "owner_cloud_transfer_failed"
            raise EnrichmentDiagnosticError(
                "owner cloud transfer did not produce one exact readback",
                category=("identity_error" if status in codes else "provider_error"),
                code=codes.get(status, provider_code),
                stage="owner_cloud_transfer",
            )
        owner_provider_file_id = str(owner.get("owner_provider_file_id") or "")
        if (
            owner.get("exact_match_count") != 1
            or not owner_provider_file_id.isdigit()
            or owner.get("owner_path") != destination_path
            or owner.get("name") != item["name"]
            or int(owner.get("size") or 0) != int(item["size"])
            or not isinstance(owner.get("transfer_performed"), bool)
        ):
            raise EnrichmentDiagnosticError(
                "owner cloud readback changed identity",
                category="identity_error",
                code="owner_cloud_readback_mismatch",
                stage="owner_cloud_transfer",
            )
        receipt = {
            "schema_version": 1,
            "event": "subscription_owner_cloud_transfer_completed",
            "status": "completed",
            "claim_id": str(transfer_claim["claim_id"]),
            **binding,
            "owner_provider_file_id": owner_provider_file_id,
            "owner_path": destination_path,
            "name": str(item["name"]),
            "size": int(item["size"]),
            "modified_at": int(owner.get("modified_at") or 0),
            "exact_match_count": 1,
            "transfer_performed": owner["transfer_performed"],
            "directory_receipts": owner.get("directory_receipts") or [],
            "completed_at": self._time().isoformat(timespec="seconds"),
        }
        _atomic_write_json(receipt_path, receipt)
        _atomic_write_json(
            claim_path,
            {
                **transfer_claim,
                "status": "completed",
                "receipt_path": str(receipt_path.resolve()),
                "receipt_sha256": _sha256_file(receipt_path),
                "completed_at": receipt["completed_at"],
            },
        )
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in receipt.items()
                if key not in {"directory_receipts"}
            },
        )
        return {**receipt, "idempotent_replay": False}

    def _owner_cloud_download(
        self,
        item: dict[str, Any],
        claim: dict[str, Any],
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        owner = self._owner_cloud_transfer(
            item,
            claim,
            session=session,
            profile=profile,
        )
        destination = (
            self.download_inbox / str(item["version_key"]) / str(item["name"])
        ).resolve()
        if destination.parent.parent != self.download_inbox:
            raise EnrichmentDiagnosticError(
                "owner download destination is invalid",
                category="identity_error",
                code="owner_download_destination_invalid",
                stage="owner_cloud_download",
            )
        if self.owner_authenticated_streamer is not None:
            fetched = self.owner_authenticated_streamer(
                item, owner, session, profile, destination
            )
        else:
            link = self.owner_download_link_reader(
                item, owner, session, profile
            )
            if not isinstance(link, dict):
                raise EnrichmentDiagnosticError(
                    "owner download link readback is invalid",
                    category="provider_error",
                    code="owner_download_link_invalid",
                    stage="owner_cloud_download",
                )
            status = str(link.get("status") or "")
            if status == "auth_required":
                raise EnrichmentDiagnosticError(
                    "owner download authentication is required",
                    category="authentication_error",
                    code="owner_download_authentication_required",
                    stage="owner_cloud_download",
                )
            if status == "captcha_required":
                raise EnrichmentDiagnosticError(
                    "owner download CAPTCHA is required",
                    category="authentication_error",
                    code="owner_download_captcha_required",
                    stage="owner_cloud_download",
                )
            download_url = str(link.get("download_url") or "")
            parsed = urlparse(download_url)
            if (
                status != "download_link_ready"
                or link.get("provider_file_id")
                != owner["owner_provider_file_id"]
                or link.get("name") != item["name"]
                or int(link.get("size") or 0) != int(item["size"])
                or parsed.scheme != "https"
                or parsed.hostname not in _DIRECT_DOWNLOAD_HOSTS
                or not parsed.query
            ):
                raise EnrichmentDiagnosticError(
                    "owner download link changed identity",
                    category="identity_error",
                    code="owner_download_link_invalid",
                    stage="owner_cloud_download",
                )
            cookies = self.opencli_cookie_reader(session, profile)
            if (
                not isinstance(cookies, list)
                or not cookies
                or not any(
                    row.get("httpOnly") is True
                    for row in cookies
                    if isinstance(row, dict)
                )
            ):
                raise EnrichmentDiagnosticError(
                    "owner download authentication is unavailable",
                    category="authentication_error",
                    code="owner_download_authentication_required",
                    stage="owner_cloud_download",
                )
            try:
                fetched = self.owner_download_fetcher(
                    download_url,
                    cookies,
                    destination,
                    int(item["size"]),
                )
            finally:
                link.pop("download_url", None)
                cookies.clear()
        path = Path(str(fetched.get("path") or "")).resolve()
        if (
            path != destination
            or not path.is_file()
            or path.stat().st_size != int(item["size"])
            or path.read_bytes()[:5] != b"%PDF-"
            or fetched.get("http_status") != 200
            or int(fetched.get("actual_size") or 0) != int(item["size"])
            or fetched.get("sha256") != _sha256_file(path)
        ):
            raise EnrichmentDiagnosticError(
                "owner download receipt is invalid",
                category="identity_error",
                code="owner_download_receipt_invalid",
                stage="download_reconciliation",
            )
        return {
            "path": str(path),
            "actual_size": path.stat().st_size,
            "sha256": str(fetched["sha256"]),
            "content_type": str(fetched.get("content_type") or ""),
            "acquisition_transport": "owner_cloud_opencli_cookie_stream",
        }

    def _provider_direct_download(
        self,
        item: dict[str, Any],
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        """Recover one claimed small item through the authenticated share API."""
        media_type = str(item.get("media_type") or "")
        provider_file_id = str(item.get("provider_file_id") or "").strip()
        if media_type not in _DIRECT_DOWNLOAD_MEDIA:
            raise EnrichmentDiagnosticError(
                "provider direct download media is outside the safe boundary",
                category="policy_error",
                code="provider_direct_media_not_allowed",
                stage="provider_direct_download",
            )
        if not provider_file_id or not provider_file_id.isdigit():
            raise EnrichmentDiagnosticError(
                "provider direct download identity is invalid",
                category="identity_error",
                code="provider_direct_identity_invalid",
                stage="provider_download_link",
            )
        link_script = _provider_direct_link_script(
            expected_share_path=urlparse(self.share_url).path,
            expected_provider_file_id=provider_file_id,
            expected_item_path=str(item["path"]),
            expected_name=str(item["name"]),
            expected_size=int(item["size"]),
        )
        # This script POSTs /api/sharedownload.  OpenCLI's detached-mid-command
        # result means the browser-side command outcome is unknown; reopening
        # the route and evaluating it again would violate at-most-once.  The
        # caller owns the idempotent owner-cloud fallback for small PDFs.
        link = self._opencli_json(
            session,
            "eval",
            link_script,
            profile=profile,
            timeout_seconds=30,
        )
        status = str(link.get("status") or "")
        if status in {"auth_required", "wrong_share"}:
            raise EnrichmentDiagnosticError(
                "provider authentication is required",
                category="authentication_error",
                code="provider_authentication_required",
                stage="browser_download_authorization",
            )
        if status == "captcha_required":
            raise EnrichmentDiagnosticError(
                "provider CAPTCHA is required",
                category="authentication_error",
                code="provider_captcha_required",
                stage="browser_download_authorization",
            )
        if status != "download_link_ready":
            provider_errno = link.get("provider_errno")
            if status == "provider_filtered":
                code = "provider_download_filtered"
            elif provider_errno == 2 and media_type == "image":
                code = "provider_download_filtered"
            elif provider_errno == 2:
                code = "provider_download_link_errno_2"
            elif status == "share_download_metadata_missing":
                code = "provider_download_metadata_missing"
            else:
                code = "provider_download_link_failed"
            raise EnrichmentDiagnosticError(
                "provider download link request failed",
                category="provider_error",
                code=code,
                stage="provider_download_link",
            )
        return self._fetch_provider_small_file(
            item,
            link,
            acquisition_transport="provider_direct_small_file",
        )

    def _provider_frontend_intercepted_download(
        self,
        item: dict[str, Any],
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        """Trigger the provider frontend once and intercept its signed link."""
        provider_file_id = str(item.get("provider_file_id") or "").strip()
        item_path = str(item["path"])
        parent_path = str(PurePosixPath(item_path).parent)
        route = urlparse(
            _authorized_share_url(self.share_url, self.share_code)
        )._replace(fragment=f"list/path={quote(parent_path, safe='')}").geturl()
        self._opencli_json(
            session,
            "open",
            route,
            profile=profile,
            timeout_seconds=30,
        )
        route_readback = self._opencli_json(
            session,
            "eval",
            """(() => {
              const operation = 'ticket04_target_route_readback';
              const expectedSharePath = %s;
              const expectedParentPath = %s;
              const prefix = '#list/path=';
              let currentParentPath = '';
              try {
                currentParentPath = location.hash.startsWith(prefix)
                  ? decodeURIComponent(location.hash.slice(prefix.length))
                  : '';
              } catch (_error) {}
              return {
                status: (
                  location.origin === 'https://pan.baidu.com'
                  && location.pathname === expectedSharePath
                  && currentParentPath === expectedParentPath
                ) ? 'target_route_ready' : 'target_route_mismatch',
                operation
              };
            })()""" % (
                json.dumps(urlparse(self.share_url).path),
                json.dumps(parent_path),
            ),
            profile=profile,
            timeout_seconds=30,
        )
        if route_readback.get("status") != "target_route_ready":
            raise EnrichmentDiagnosticError(
                "provider frontend target route did not bind",
                category="identity_error",
                code="provider_frontend_target_route_mismatch",
                stage="provider_download_link",
            )
        prepared = self._prepare_opencli_download_confirmation(
            item,
            session=session,
            profile=profile,
            defer_trigger=True,
        )
        if prepared.get("status") not in {
            "download_confirmation_ready",
            "download_control_ready",
        }:
            code = (
                "provider_web_download_client_only"
                if prepared.get("status")
                == "provider_web_download_client_only"
                else "provider_frontend_target_not_ready"
            )
            raise EnrichmentDiagnosticError(
                "provider frontend download target was not prepared",
                category="provider_error",
                code=code,
                stage="provider_download_link",
            )
        link = self._opencli_json(
            session,
            "eval",
            _provider_frontend_intercept_install_script(
                expected_share_path=urlparse(self.share_url).path,
                expected_provider_file_id=provider_file_id,
                expected_name=str(item["name"]),
                expected_size=int(item["size"]),
            ),
            profile=profile,
            timeout_seconds=20,
        )
        if link.get("status") != "download_link_ready":
            raise EnrichmentDiagnosticError(
                "provider frontend did not expose a signed download link",
                category="provider_error",
                code="provider_frontend_signed_link_not_captured",
                stage="provider_download_link",
            )
        return self._fetch_provider_small_file(
            item,
            link,
            acquisition_transport="provider_frontend_intercepted_small_file",
        )

    def _automated_native_save_download(
        self,
        item: dict[str, Any],
        claim: dict[str, Any],
        *,
        session: str,
        profile: str | None,
        confirmation_prepared: bool = False,
    ) -> dict[str, Any]:
        """Recover one exact PDF through a trusted, bounded Edge Save sheet."""
        if str(item.get("media_type") or "") != "pdf":
            raise EnrichmentDiagnosticError(
                "native Save recovery is limited to small PDFs",
                category="policy_error",
                code="native_save_media_not_allowed",
                stage="native_save_automation",
            )
        destination = (
            self.download_inbox
            / str(item["version_key"])
            / str(item["name"])
        ).resolve()
        if destination.parent.parent != self.download_inbox:
            raise EnrichmentDiagnosticError(
                "native Save destination is invalid",
                category="identity_error",
                code="native_save_destination_invalid",
                stage="native_save_automation",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise EnrichmentDiagnosticError(
                "native Save destination already exists without a receipt",
                category="uncertain_state",
                code="native_save_destination_exists",
                stage="native_save_automation",
            )

        if not confirmation_prepared:
            item_path = str(item["path"])
            parent_path = str(PurePosixPath(item_path).parent)
            route = urlparse(
                _authorized_share_url(self.share_url, self.share_code)
            )._replace(
                fragment=f"list/path={quote(parent_path, safe='')}"
            ).geturl()
            self._opencli_json(
                session,
                "open",
                route,
                profile=profile,
                timeout_seconds=30,
            )
            prepared = self._prepare_opencli_download_confirmation(
                item,
                session=session,
                profile=profile,
            )
            if prepared.get("status") != "download_confirmation_ready":
                code = (
                    "provider_web_download_client_only"
                    if prepared.get("status")
                    == "provider_web_download_client_only"
                    else "native_save_target_not_ready"
                )
                raise EnrichmentDiagnosticError(
                    "native Save target was not prepared",
                    category=(
                        "provider_error"
                        if code == "provider_web_download_client_only"
                        else "identity_error"
                    ),
                    code=code,
                    stage="native_save_automation",
                )

        helper = Path(__file__).parents[3] / "scripts/macos_edge_save_helper.swift"
        swift = shutil.which("swift")
        if not swift or not helper.is_file():
            raise EnrichmentDiagnosticError(
                "native Save helper is unavailable",
                category="local_runtime_error",
                code="native_save_helper_unavailable",
                stage="native_save_automation",
            )
        process = subprocess.Popen(
            (
                swift,
                str(helper),
                str(item["name"]),
                str(destination),
                str(int(item["size"])),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            if process.stdout is None or not select.select(
                [process.stdout], [], [], 15
            )[0]:
                raise EnrichmentDiagnosticError(
                    "native Save helper did not become ready",
                    category="local_runtime_error",
                    code="native_save_helper_not_ready",
                    stage="native_save_automation",
                )
            first = json.loads(process.stdout.readline())
            if first.get("status") == "accessibility_not_trusted":
                raise EnrichmentDiagnosticError(
                    "macOS Accessibility permission is required",
                    category="permission_error",
                    code="macos_accessibility_permission_required",
                    stage="native_save_automation",
                )
            if (
                first.get("status") != "ready"
                or first.get("accessibility_trusted") is not True
            ):
                raise EnrichmentDiagnosticError(
                    "native Save helper readiness is invalid",
                    category="local_runtime_error",
                    code="native_save_helper_not_ready",
                    stage="native_save_automation",
                )
            click_error: EnrichmentDiagnosticError | None = None
            try:
                clicked = self._opencli_json(
                    session,
                    "click",
                    "a[data-xiaocao-download-confirmation='1']",
                    profile=profile,
                    timeout_seconds=30,
                )
            except EnrichmentDiagnosticError as exc:
                click_error = exc
                clicked = {}
            if click_error is None and (
                clicked.get("clicked") is not True
                or clicked.get("matches_n") != 1
            ):
                raise EnrichmentDiagnosticError(
                    "native Save trigger was not exact",
                    category="identity_error",
                    code="native_save_trigger_not_exact",
                    stage="native_save_automation",
                )
            stdout, _stderr = process.communicate(timeout=35)
            rows = [
                json.loads(line)
                for line in stdout.splitlines()
                if line.strip()
            ]
            result = rows[-1] if rows else {}
            if result.get("status") != "completed":
                safe_code = str(result.get("status") or "native_save_failed")
                if not _SAFE_OPENCLI_ERROR_CODE.fullmatch(safe_code):
                    safe_code = "native_save_failed"
                raise EnrichmentDiagnosticError(
                    "automated native Save did not complete",
                    category=(
                        "identity_error"
                        if safe_code
                        in {
                            "save_sheet_filename_mismatch",
                            "overwrite_prompt_detected",
                            "save_destination_readback_failed",
                        }
                        else "local_runtime_error"
                    ),
                    code=safe_code,
                    stage="native_save_automation",
                )
        except (json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            raise EnrichmentDiagnosticError(
                "native Save helper response is invalid",
                category="local_runtime_error",
                code="native_save_helper_failed",
                stage="native_save_automation",
            ) from exc
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()

        if (
            not destination.is_file()
            or destination.stat().st_size != int(item["size"])
            or destination.read_bytes()[:5] != b"%PDF-"
        ):
            raise EnrichmentDiagnosticError(
                "automated native Save file is invalid",
                category="content_error",
                code="native_save_file_invalid",
                stage="download_reconciliation",
            )
        history_confirmed = False
        for _attempt in range(20):
            if self._edge_history_download_completed(
                item, claim, destination
            ):
                history_confirmed = True
                break
            self.sleep(0.25)
        if not history_confirmed:
            raise EnrichmentDiagnosticError(
                "Edge completed-download history receipt is missing",
                category="uncertain_state",
                code="native_save_history_receipt_missing",
                stage="download_reconciliation",
            )
        return {
            "path": str(destination),
            "actual_size": destination.stat().st_size,
            "sha256": _sha256_file(destination),
            "content_type": "application/pdf",
            "acquisition_transport": "automated_native_save",
        }

    def _fetch_provider_small_file(
        self,
        item: dict[str, Any],
        link: dict[str, Any],
        *,
        acquisition_transport: str,
    ) -> dict[str, Any]:
        """Validate and stream one exact provider-signed small file."""
        provider_file_id = str(item.get("provider_file_id") or "").strip()
        media_type = str(item.get("media_type") or "")
        download_url = str(link.get("download_url") or "")
        parsed = urlparse(download_url)
        path_allowed = _is_supported_baidu_download_path(parsed.path)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _DIRECT_DOWNLOAD_HOSTS
            or not path_allowed
            or not parsed.query
            or str(link.get("provider_file_id") or "") != provider_file_id
        ):
            raise EnrichmentDiagnosticError(
                "provider direct download URL is invalid",
                category="identity_error",
                code="provider_direct_url_invalid",
                stage="provider_download_link",
            )
        destination = (
            self.download_inbox
            / str(item["version_key"])
            / str(item["name"])
        ).resolve()
        if (
            destination.parent.parent != self.download_inbox
            or destination.name != str(item["name"])
        ):
            raise EnrichmentDiagnosticError(
                "provider direct download destination is invalid",
                category="identity_error",
                code="provider_direct_destination_invalid",
                stage="provider_direct_download",
            )
        fetched = self.direct_download_fetcher(
            download_url,
            destination,
            int(item["size"]),
            media_type,
        )
        path = Path(str(fetched.get("path") or "")).resolve()
        if (
            path != destination
            or not path.is_file()
            or path.stat().st_size != int(item["size"])
            or int(fetched.get("actual_size") or 0) != int(item["size"])
            or str(fetched.get("sha256") or "") != _sha256_file(path)
        ):
            raise EnrichmentDiagnosticError(
                "provider direct download receipt is invalid",
                category="identity_error",
                code="provider_direct_receipt_invalid",
                stage="download_reconciliation",
            )
        return {
            "path": str(path),
            "actual_size": path.stat().st_size,
            "sha256": str(fetched["sha256"]),
            "content_type": str(fetched.get("content_type") or ""),
            "acquisition_transport": acquisition_transport,
        }

    def _download_provider_small_file(
        self,
        item: dict[str, Any],
        claim: dict[str, Any],
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        try:
            return self._provider_direct_download(
                item,
                session=session,
                profile=profile,
            )
        except EnrichmentDiagnosticError as exc:
            if (
                str(item.get("media_type") or "") == "pdf"
                and exc.diagnostic_code
                in _PROVIDER_LINK_OWNER_CLOUD_FALLBACK_CODES
            ):
                # The source-link probe has an unknown browser-command
                # outcome, but it has not claimed a second business object.
                # Continue through the separately claimed, exact owner-cloud
                # transfer/readback path; it reconciles an existing copy
                # before performing any transfer and never replays the UI.
                return self._owner_cloud_download(
                    item,
                    claim,
                    session=session,
                    profile=profile,
                )
            if exc.diagnostic_code not in {
                "provider_download_link_errno_2",
                "provider_download_metadata_missing",
                "provider_download_filtered",
            }:
                raise
        try:
            return self._provider_frontend_intercepted_download(
                item,
                session=session,
                profile=profile,
            )
        except EnrichmentDiagnosticError as exc:
            if (
                str(item.get("media_type") or "") == "pdf"
                and exc.diagnostic_code
                in _PROVIDER_LINK_OWNER_CLOUD_FALLBACK_CODES
            ):
                # The interception script clicks the provider UI.  A detached
                # command has an unknown click outcome, so never replay it;
                # use the exact owner-cloud claim/readback path instead.
                return self._owner_cloud_download(
                    item,
                    claim,
                    session=session,
                    profile=profile,
                )
            if exc.diagnostic_code not in {
                "provider_web_download_client_only",
                "provider_frontend_signed_link_not_captured",
            }:
                raise
            if str(item.get("media_type") or "") != "pdf":
                raise
        return self._owner_cloud_download(
            item,
            claim,
            session=session,
            profile=profile,
        )

    def _reconcile_native_save_download(
        self,
        item: dict[str, Any],
        claim: dict[str, Any],
        *,
        profile: str | None,
    ) -> Path | None:
        """Bind one exact post-claim Save dialog result to Edge History."""
        if profile is not None:
            return None
        candidate = (self.downloads_dir / str(item["name"])).resolve()
        if candidate.parent != self.downloads_dir or not candidate.is_file():
            return None
        if candidate.stat().st_size != int(item.get("size") or 0):
            raise EnrichmentDiagnosticError(
                "native Save dialog file does not match provider size",
                category="identity_error",
                code="native_save_file_mismatch",
                stage="download_reconciliation",
            )
        return (
            candidate
            if self._edge_history_download_completed(item, claim, candidate)
            else None
        )

    def _edge_history_download_completed(
        self,
        item: dict[str, Any],
        claim: dict[str, Any],
        candidate: Path,
    ) -> bool:
        """Read one exact completed Edge History row after the claim."""
        history_path = self.edge_profile_dir / "History"
        if not history_path.is_file():
            return False
        try:
            claimed_at = datetime.fromisoformat(str(claim["claimed_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise EnrichmentError(
                "subscription browser download claim is invalid"
            ) from exc
        edge_epoch_us = 11_644_473_600 * 1_000_000
        claimed_edge_us = (
            edge_epoch_us + int(claimed_at.timestamp() * 1_000_000)
        )
        try:
            with tempfile.TemporaryDirectory(
                prefix="xiaocao-edge-history-"
            ) as temporary_dir:
                snapshot = Path(temporary_dir) / "History"
                shutil.copy2(history_path, snapshot)
                journal = history_path.with_name("History-journal")
                if journal.is_file():
                    shutil.copy2(
                        journal,
                        snapshot.with_name("History-journal"),
                    )
                connection = sqlite3.connect(snapshot)
                try:
                    rows = connection.execute(
                        """SELECT target_path, current_path, received_bytes,
                                  total_bytes, state, interrupt_reason,
                                  start_time, end_time
                           FROM downloads
                           WHERE target_path = ? AND current_path = ?
                             AND start_time >= ?""",
                        (
                            str(candidate),
                            str(candidate),
                            claimed_edge_us,
                        ),
                    ).fetchall()
                finally:
                    connection.close()
        except (OSError, sqlite3.Error):
            return False
        completed = [
            row
            for row in rows
            if int(row[2]) == int(item["size"])
            and int(row[3]) == int(item["size"])
            and int(row[4]) == 1
            and int(row[5]) == 0
            and int(row[6]) >= claimed_edge_us
            and int(row[7]) >= int(row[6])
        ]
        if not completed:
            return False
        if len(completed) != 1:
            raise EnrichmentDiagnosticError(
                "native Save dialog receipt is ambiguous",
                category="identity_error",
                code="native_save_receipt_ambiguous",
                stage="download_reconciliation",
            )
        return True

    def _recover_blocked_client_download(
        self,
        item: dict[str, Any],
        *,
        session: str,
        profile: str | None,
    ) -> Path | None:
        """Reuse one blocked signed URL in a top-level tab without re-clicking."""
        try:
            browser_error = self._opencli_json(
                session,
                "eval",
                """(() => {
              const operation = 'blocked_download_frame_probe';
              const text = document.body?.innerText || '';
              const match = text.match(/ERR_[A-Z_]+/);
              const errorCode = match ? match[0] : '';
              return {
                status: errorCode === 'ERR_BLOCKED_BY_CLIENT'
                  ? 'blocked_by_client'
                  : 'other_browser_error',
                error_code: errorCode,
                operation
              };
            })()""",
                "--frame",
                "0",
                profile=profile,
                timeout_seconds=15,
            )
        except EnrichmentDiagnosticError as exc:
            raise EnrichmentDiagnosticError(
                "blocked browser download reconciliation failed",
                category=exc.diagnostic_category,
                code=exc.diagnostic_code,
                stage="browser_download_recovery",
                exit_code=exc.diagnostic_exit_code,
            ) from exc
        if (
            browser_error.get("status") != "blocked_by_client"
            or browser_error.get("error_code") != "ERR_BLOCKED_BY_CLIENT"
        ):
            return None
        download_target = self._opencli_json(
            session,
            "eval",
            """(() => {
              const operation = 'blocked_download_url_probe';
              const expectedProviderFileId = %s;
              const expectedName = %s;
              const expectedSize = %s;
              const frames = Array.from(
                document.querySelectorAll('iframe[name="pcsdownloadiframe"]')
              ).filter(frame => frame.getAttribute('src'));
              if (frames.length === 0) return {
                status: 'download_url_missing', frame_count: 0, operation
              };
              if (frames.length !== 1) return {
                status: 'download_url_ambiguous',
                frame_count: frames.length,
                operation
              };
              const rowFor = node => node.closest(
                'dd, tr, [role="row"], [class*="file-item"], '
                + '[class*="table-row"]'
              ) || node;
              const rowItem = row => row?.__vue__?._props?.item
                || row?.__vue__?.item || {};
              const rowId = row => String(
                rowItem(row)?.fs_id || rowItem(row)?.fsid
                || row?.getAttribute?.('data-id')
                || row?.getAttribute?.('data-fsid') || ''
              );
              const rowName = row => String(
                rowItem(row)?.server_filename || rowItem(row)?.name
                || row?.querySelector?.('a.filename')?.getAttribute('title')
                || ''
              );
              const rowSize = row => Number(rowItem(row)?.size || 0);
              const rows = [...new Set(Array.from(document.querySelectorAll(
                '[data-id], [data-fsid]'
              )).map(rowFor))];
              const targets = rows.filter(row => (
                rowId(row) === expectedProviderFileId
                && rowName(row) === expectedName
                && rowSize(row) === expectedSize
              ));
              if (targets.length !== 1) return {
                status: targets.length === 0
                  ? 'download_target_not_bound'
                  : 'download_target_ambiguous',
                frame_count: 1,
                operation
              };
              let url;
              try {
                url = new URL(frames[0].getAttribute('src'), location.href);
              } catch (_error) {
                return {
                  status: 'download_url_unparseable',
                  frame_count: 1,
                  operation
                };
              }
              return {
                status: 'download_url_ready',
                download_url: url.href,
                scheme: url.protocol,
                host: url.hostname,
                path: url.pathname,
                provider_file_id: expectedProviderFileId,
                name: expectedName,
                size: expectedSize,
                frame_count: 1,
                operation
              };
            })()""" % (
                json.dumps(str(item.get("provider_file_id") or "")),
                json.dumps(str(item.get("name") or "")),
                json.dumps(int(item.get("size") or 0)),
            ),
            profile=profile,
            timeout_seconds=15,
        )
        status = str(download_target.get("status") or "")
        if (
            status == "download_url_missing"
            and str(item.get("media_type") or "") == "image"
        ):
            # The iframe is a transient provider surface. Rebind the exact
            # claimed image through the authenticated share API before
            # classifying the recovery as a frame failure. This path is
            # read-only with respect to the provider item and never clicks a
            # second download control.
            direct = self._provider_direct_download(
                item,
                session=session,
                profile=profile,
            )
            return Path(str(direct["path"]))
        if status != "download_url_ready":
            code = {
                "download_url_missing": "blocked_download_frame_missing",
                "download_url_ambiguous": "blocked_download_frame_ambiguous",
                "download_target_not_bound": "blocked_download_target_not_bound",
                "download_target_ambiguous": "blocked_download_target_ambiguous",
                "download_url_unparseable": "blocked_download_url_unparseable",
            }.get(status, "blocked_download_probe_invalid")
            raise EnrichmentDiagnosticError(
                "subscription blocked download URL could not be rebound",
                category="identity_error",
                code=code,
                stage="browser_download_recovery",
            )
        download_url = str(download_target.get("download_url") or "")
        parsed = urlparse(download_url)
        if (
            str(download_target.get("provider_file_id") or "")
            != str(item.get("provider_file_id") or "")
            or str(download_target.get("name") or "") != str(item["name"])
            or int(download_target.get("size") or 0) != int(item["size"])
        ):
            raise EnrichmentDiagnosticError(
                "subscription blocked download target is not evidence-bound",
                category="identity_error",
                code="blocked_download_target_not_bound",
                stage="browser_download_recovery",
            )
        if download_target.get("scheme") != "https:" or parsed.scheme != "https":
            invalid_code = "blocked_download_url_scheme_invalid"
        elif (
            download_target.get("host") not in _DIRECT_DOWNLOAD_HOSTS
            or parsed.hostname not in _DIRECT_DOWNLOAD_HOSTS
        ):
            invalid_code = "blocked_download_url_host_invalid"
        elif (
            not _is_supported_baidu_download_path(
                str(download_target.get("path") or "")
            )
            or not _is_supported_baidu_download_path(parsed.path)
        ):
            invalid_code = "blocked_download_url_path_invalid"
        else:
            invalid_code = ""
        if invalid_code:
            raise EnrichmentDiagnosticError(
                "subscription blocked download URL is invalid",
                category="identity_error",
                code=invalid_code,
                stage="browser_download_recovery",
            )

        # Keep recovery on the exact browser session that proved the blocked
        # frame and target. This is a top-level navigation, not a second
        # provider click; the bounded wait reconciles the same target receipt.
        open_error: EnrichmentError | None = None
        try:
            self._opencli_json(
                session,
                "open",
                download_url,
                profile=profile,
                timeout_seconds=30,
            )
        except EnrichmentError as exc:
            # Edge may report a navigation error after converting the URL
            # into a download. The observer receipt, not navigation status,
            # decides whether recovery completed.
            open_error = exc
        try:
            return self._wait_opencli_download(
                item,
                session=session,
                profile=profile,
                timeout_seconds=60,
            )
        except EnrichmentError as exc:
            if open_error is None:
                raise EnrichmentDiagnosticError(
                    "subscription download prompt requires internal recovery",
                    category="local_recovery",
                    code="download_prompt_internal_recovery",
                    stage="browser_download_prompt",
                ) from exc
            raise EnrichmentDiagnosticError(
                "subscription download was blocked by a browser extension",
                category="local_policy_error",
                code="download_blocked_by_extension",
                stage="browser_download_recovery",
            ) from (open_error or exc)

    def download_opencli(
        self,
        identity: str,
        *,
        session: str,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Download one claimed small item through the configured share page."""
        item = self._manifest_item(str(identity))
        completed = self._completed_browser_receipt(item)
        if completed is not None:
            return {**completed, "idempotent_replay": True}

        # A completed owner-cloud transfer is the durable, exact readback for
        # an interrupted small-PDF acquisition.  Do not make recovery depend
        # on re-evaluating the ephemeral source-share tab: the named OpenCLI
        # session may retain a stale about:blank target even though the owner
        # copy and its receipt are complete.  Revalidate the persisted parent
        # claim and owner receipt in _owner_cloud_download, then stream only
        # that exact owner-side object.
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        if (
            item.get("media_type") == "pdf"
            and (artifact_dir / "browser_download_claim.json").is_file()
            and (artifact_dir / "owner_cloud_transfer_receipt.json").is_file()
        ):
            try:
                owner_receipt = json.loads(
                    (
                        artifact_dir / "owner_cloud_transfer_receipt.json"
                    ).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "owner cloud recovery receipt is invalid"
                ) from exc
            owner_provider_file_id = str(
                owner_receipt.get("source_provider_file_id") or ""
            )
            if (
                owner_receipt.get("status") != "completed"
                or owner_receipt.get("source_identity") != item["identity"]
                or owner_receipt.get("source_version_key")
                != item["version_key"]
                or owner_receipt.get("source_name") != item["name"]
                or int(owner_receipt.get("source_size") or 0)
                != int(item["size"])
                or not owner_provider_file_id.isdigit()
            ):
                raise EnrichmentError(
                    "owner cloud recovery receipt changed source identity"
                )
            claim = self.claim_browser_download(str(identity))
            if claim.get("idempotent_replay") is not True:
                raise EnrichmentError(
                    "owner cloud recovery requires an existing acquisition claim"
                )
            direct_item = {
                **item,
                "provider_file_id": owner_provider_file_id,
            }
            direct = self._owner_cloud_download(
                direct_item,
                claim,
                session=session,
                profile=profile,
            )
            return self.complete_browser_download(
                str(item["identity"]),
                Path(str(direct["path"])),
                claim_id=str(claim["claim_id"]),
                acquisition_transport=str(direct["acquisition_transport"]),
            )

        listing = self._download_listing(
            session=session,
            profile=profile,
            exact_path=str(item["path"]),
        )
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for raw in listing["entries"]:
            if not isinstance(raw, dict):
                raise EnrichmentError(
                    "subscription browser listing contains an invalid entry"
                )
            normalized = self._normalize_entry(raw)
            if (
                normalized["identity"] == item["identity"]
                and normalized["version_key"] == item["version_key"]
            ):
                matches.append((raw, normalized))
        if len(matches) != 1:
            raise EnrichmentDiagnosticError(
                "subscription browser download target is not unique",
                category="identity_error",
                code="source_version_not_unique",
                stage="source_acquisition",
            )
        raw, normalized = matches[0]
        if (
            normalized["media_type"] not in SUPPORTED_SMALL_MEDIA
            or normalized["name"] != item["name"]
            or normalized["size"] != item["size"]
        ):
            raise EnrichmentDiagnosticError(
                "subscription browser download target changed before claim",
                category="identity_error",
                code="source_version_changed",
                stage="source_acquisition",
            )

        direct_item = {
            **item,
            "provider_file_id": str(raw.get("provider_file_id") or ""),
        }
        download_policy: dict[str, Any] | None = None
        if normalized["media_type"] in _UI_DIRECT_DOWNLOAD_MEDIA:
            download_policy = self.configure_opencli_download_policy(
                session=session,
                profile=profile,
            )

        claim = self.claim_browser_download(str(identity))
        if claim.get("idempotent_replay") is True:
            reconciled_path = self._reconcile_native_save_download(
                item,
                claim,
                profile=profile,
            )
            if reconciled_path is not None:
                return self.complete_browser_download(
                    str(item["identity"]),
                    reconciled_path,
                    claim_id=str(claim["claim_id"]),
                )
            if normalized["media_type"] in _UI_DIRECT_DOWNLOAD_MEDIA:
                if download_policy and download_policy["configured"] is True:
                    try:
                        downloaded_path = self._wait_opencli_download(
                            item,
                            session=session,
                            profile=profile,
                            timeout_seconds=5,
                        )
                    except EnrichmentDiagnosticError as exc:
                        if exc.diagnostic_code != "download_not_seen":
                            raise
                    else:
                        return self.complete_browser_download(
                            str(item["identity"]),
                            downloaded_path,
                            claim_id=str(claim["claim_id"]),
                        )
                direct = self._download_provider_small_file(
                    direct_item,
                    claim,
                    session=session,
                    profile=profile,
                )
                return self.complete_browser_download(
                    str(item["identity"]),
                    Path(str(direct["path"])),
                    claim_id=str(claim["claim_id"]),
                    acquisition_transport=str(
                        direct["acquisition_transport"]
                    ),
                )
            try:
                downloaded_path = self._wait_opencli_download(
                    item,
                    session=session,
                    profile=profile,
                    timeout_seconds=5,
                )
            except EnrichmentDiagnosticError as exc:
                if exc.diagnostic_code != "download_not_seen":
                    raise
                if normalized["media_type"] == "image":
                    try:
                        direct = self._provider_direct_download(
                            direct_item,
                            session=session,
                            profile=profile,
                        )
                    except EnrichmentDiagnosticError as direct_error:
                        if direct_error.diagnostic_code in {
                            "provider_download_filtered",
                            "provider_download_link_errno_2",
                            "provider_download_metadata_missing",
                        }:
                            return self.reconcile_filtered_image_preview(
                                str(item["identity"]),
                                session=session,
                                profile=profile,
                                listing=listing,
                            )
                        if direct_error.diagnostic_code != (
                            "provider_download_link_failed"
                        ):
                            raise
                    else:
                        return self.complete_browser_download(
                            str(item["identity"]),
                            Path(str(direct["path"])),
                            claim_id=str(claim["claim_id"]),
                            acquisition_transport=str(
                                direct["acquisition_transport"]
                            ),
                        )
                downloaded_path = self._recover_blocked_client_download(
                    direct_item,
                    session=session,
                    profile=profile,
                )
                if downloaded_path is None:
                    raise
            return self.complete_browser_download(
                str(item["identity"]),
                downloaded_path,
                claim_id=str(claim["claim_id"]),
            )

        if (
            normalized["media_type"] in _UI_DIRECT_DOWNLOAD_MEDIA
            and download_policy
            and download_policy["configured"] is False
        ):
            direct = self._download_provider_small_file(
                direct_item,
                claim,
                session=session,
                profile=profile,
            )
            return self.complete_browser_download(
                str(item["identity"]),
                Path(str(direct["path"])),
                claim_id=str(claim["claim_id"]),
                acquisition_transport=str(direct["acquisition_transport"]),
            )

        if normalized["media_type"] == "image":
            direct = None
            try:
                direct = self._provider_direct_download(
                    direct_item,
                    session=session,
                    profile=profile,
                )
            except EnrichmentDiagnosticError as exc:
                if exc.diagnostic_code == "provider_download_filtered":
                    return self.reconcile_filtered_image_preview(
                        str(item["identity"]),
                        session=session,
                        profile=profile,
                        listing=listing,
                    )
                if exc.diagnostic_code == "provider_download_link_failed":
                    pass
                elif exc.diagnostic_code not in {
                    "provider_download_link_errno_2",
                    "provider_download_metadata_missing",
                }:
                    raise
                else:
                    direct = self._provider_frontend_intercepted_download(
                        direct_item,
                        session=session,
                        profile=profile,
                    )
            else:
                return self.complete_browser_download(
                    str(item["identity"]),
                    Path(str(direct["path"])),
                    claim_id=str(claim["claim_id"]),
                    acquisition_transport=str(
                        direct["acquisition_transport"]
                    ),
                )
            if direct is not None:
                return self.complete_browser_download(
                    str(item["identity"]),
                    Path(str(direct["path"])),
                    claim_id=str(claim["claim_id"]),
                    acquisition_transport=str(
                        direct["acquisition_transport"]
                    ),
                )

        # OpenCLI serializes commands per browser session. Starting `wait`
        # first prevents the trigger eval from running until the wait times
        # out. Trigger first; the Bridge download observer also reports a
        # matching recent download, so the bounded wait can reconcile it.
        trigger = self._prepare_opencli_download_confirmation(
            item,
            session=session,
            profile=profile,
        )
        if trigger.get("status") != "download_confirmation_ready":
            reason = str(trigger.get("status") or "")
            if (
                reason == "provider_web_download_client_only"
                and normalized["media_type"] == "pdf"
            ):
                direct = self._owner_cloud_download(
                    direct_item,
                    claim,
                    session=session,
                    profile=profile,
                )
                return self.complete_browser_download(
                    str(item["identity"]),
                    Path(str(direct["path"])),
                    claim_id=str(claim["claim_id"]),
                    acquisition_transport=str(
                        direct["acquisition_transport"]
                    ),
                )
            if reason in _DOWNLOAD_PRETRIGGER_FAILURES:
                self._record_browser_download_pretrigger_failure(
                    str(identity),
                    claim_id=str(claim["claim_id"]),
                    reason=reason,
                )
            raise EnrichmentError(
                "subscription browser download was not triggered"
            )
        clicked = self._opencli_json(
            session,
            "click",
            "a[data-xiaocao-download-confirmation='1']",
            profile=profile,
            timeout_seconds=30,
        )
        if clicked.get("clicked") is not True or clicked.get("matches_n") != 1:
            self._record_browser_download_pretrigger_failure(
                str(identity),
                claim_id=str(claim["claim_id"]),
                reason="download_confirmation_click_failed",
            )
            raise EnrichmentError(
                "subscription browser download was not triggered"
            )
        try:
            downloaded_path = self._wait_opencli_download(
                item,
                session=session,
                profile=profile,
                timeout_seconds=60,
            )
        except EnrichmentDiagnosticError as exc:
            if exc.diagnostic_code != "download_not_seen":
                raise
            if normalized["media_type"] in _UI_DIRECT_DOWNLOAD_MEDIA:
                direct = self._download_provider_small_file(
                    direct_item,
                    claim,
                    session=session,
                    profile=profile,
                )
                return self.complete_browser_download(
                    str(item["identity"]),
                    Path(str(direct["path"])),
                    claim_id=str(claim["claim_id"]),
                    acquisition_transport=str(
                        direct["acquisition_transport"]
                    ),
                )
            downloaded_path = self._recover_blocked_client_download(
                direct_item,
                session=session,
                profile=profile,
            )
            if downloaded_path is None:
                raise
        return self.complete_browser_download(
            str(item["identity"]),
            downloaded_path,
            claim_id=str(claim["claim_id"]),
        )

    @_exclusive("item")
    def ingest_browser_download(
        self,
        identity: str,
        *,
        ocr_runner: Callable[[Path], dict[str, Any]] | None = None,
        pdf_text_extractor: Callable[[Path], dict[str, Any]] | None = None,
        pdf_renderer: Callable[
            [Path, Path, list[int]], dict[int, Path]
        ] | None = None,
    ) -> dict[str, Any]:
        """Ingest only an immutable file captured from a claimed browser event."""
        item = self._manifest_item(str(identity))
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        receipt = self._completed_browser_receipt(item)
        if receipt is None:
            raise EnrichmentError(
                "subscription ingestion requires a browser download receipt"
            )
        source = Path(str(receipt.get("immutable_path") or ""))
        result_path = artifact_dir / "ingest_result.json"
        if result_path.is_file():
            try:
                prior = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError("subscription ingest result is invalid") from exc
            rebased = self._rebased_ingest_result(item, prior)
            return {**rebased, "idempotent_replay": True}

        original = source
        original_sha = _sha256_file(original)

        ambiguities: list[dict[str, Any]] = []
        ocr_path: Path | None = None
        pdf_coverage_path: Path | None = None
        pdf_page_count: int | None = None
        pdf_visual_pages: list[int] = []
        if item["media_type"] == "image":
            ocr = self._validate_ocr_result(
                (ocr_runner or self._default_ocr_runner)(original)
            )
            ambiguities = [
                ambiguity
                for row in ocr["lines"]
                if (ambiguity := self._ocr_ambiguity(row)) is not None
            ]
            evidence_text = "\n".join(row["text"] for row in ocr["lines"]).strip()
            ocr_payload = {
                **ocr,
                "original_sha256": original_sha,
                "ambiguity_threshold": 0.75,
                "ambiguities": ambiguities,
            }
            ocr_path = artifact_dir / "ocr.json"
            _atomic_write_json(ocr_path, ocr_payload)
        elif item["media_type"] == "pdf":
            if not original.read_bytes()[:5].startswith(b"%PDF-"):
                raise EnrichmentDiagnosticError(
                    "subscription PDF signature is invalid",
                    category="content_error",
                    code="pdf_invalid",
                    stage="pdf_extraction",
                )
            extracted = (pdf_text_extractor or self._default_pdf_text_extractor)(
                original
            )
            pages = extracted.get("pages") if isinstance(extracted, dict) else None
            if (
                not isinstance(pages, list)
                or not 0 < len(pages) <= MAX_PDF_PAGES
            ):
                raise EnrichmentDiagnosticError(
                    "subscription PDF extraction result is invalid",
                    category="content_error",
                    code="pdf_extraction_invalid",
                    stage="pdf_extraction",
                )
            normalized_pages: list[dict[str, Any]] = []
            for expected_page, row in enumerate(pages, start=1):
                if (
                    not isinstance(row, dict)
                    or int(row.get("page") or 0) != expected_page
                ):
                    raise EnrichmentDiagnosticError(
                        "subscription PDF page coverage is invalid",
                        category="content_error",
                        code="pdf_page_coverage_invalid",
                        stage="pdf_extraction",
                    )
                text = str(row.get("text") or "").strip()
                normalized_pages.append(
                    {
                        "page": expected_page,
                        "native_text": text,
                        "has_visuals": row.get("has_visuals") is True,
                    }
                )
            pages_to_render = [
                row["page"]
                for row in normalized_pages
                if row["has_visuals"]
                or len(row["native_text"]) < MIN_NATIVE_PDF_PAGE_TEXT
            ]
            rendered = (
                (pdf_renderer or self._default_pdf_renderer)(
                    original,
                    artifact_dir / "pdf_pages",
                    pages_to_render,
                )
                if pages_to_render
                else {}
            )
            if set(rendered) != set(pages_to_render):
                raise EnrichmentDiagnosticError(
                    "subscription PDF visual coverage is incomplete",
                    category="coverage_error",
                    code="pdf_visual_coverage_incomplete",
                    stage="pdf_visual_coverage",
                )
            evidence_sections: list[str] = []
            coverage_pages: list[dict[str, Any]] = []
            for row in normalized_pages:
                page_number = int(row["page"])
                page_text = str(row["native_text"])
                page_ocr_path: Path | None = None
                ocr_text = ""
                rendered_path = rendered.get(page_number)
                if rendered_path is not None:
                    if not rendered_path.is_file():
                        raise EnrichmentDiagnosticError(
                            "subscription PDF rendered page is missing",
                            category="coverage_error",
                            code="pdf_visual_coverage_incomplete",
                            stage="pdf_visual_coverage",
                        )
                    try:
                        page_ocr = self._validate_ocr_result(
                            (ocr_runner or self._default_ocr_runner)(
                                rendered_path
                            )
                        )
                    except EnrichmentError:
                        page_ocr = {"engine": "none", "lines": []}
                    ocr_text = "\n".join(
                        str(line["text"]) for line in page_ocr["lines"]
                    ).strip()
                    page_ocr_path = (
                        artifact_dir / "pdf_pages" / f"page-{page_number:04d}-ocr.json"
                    )
                    _atomic_write_json(
                        page_ocr_path,
                        {
                            **page_ocr,
                            "page": page_number,
                            "rendered_sha256": _sha256_file(rendered_path),
                        },
                    )
                combined = "\n".join(
                    value for value in (page_text, ocr_text) if value
                ).strip()
                if not combined and rendered_path is None:
                    raise EnrichmentDiagnosticError(
                        "subscription PDF page lacks extractable coverage",
                        category="coverage_error",
                        code="pdf_page_uncovered",
                        stage="pdf_visual_coverage",
                    )
                evidence_sections.append(
                    f"## PDF page {page_number}\n\n"
                    + (combined or "[visual review required]")
                )
                coverage_pages.append(
                    {
                        "page": page_number,
                        "native_text_chars": len(page_text),
                        "ocr_text_chars": len(ocr_text),
                        "has_visuals": row["has_visuals"],
                        "rendered_path": (
                            str(rendered_path.resolve())
                            if rendered_path is not None
                            else None
                        ),
                        "rendered_sha256": (
                            _sha256_file(rendered_path)
                            if rendered_path is not None
                            else None
                        ),
                        "ocr_path": (
                            str(page_ocr_path.resolve())
                            if page_ocr_path is not None
                            else None
                        ),
                        "ocr_sha256": (
                            _sha256_file(page_ocr_path)
                            if page_ocr_path is not None
                            else None
                        ),
                        "coverage_status": (
                            "visual_review_required"
                            if rendered_path is not None and not ocr_text
                            else "covered"
                        ),
                    }
                )
            evidence_text = "\n\n".join(evidence_sections).strip()
            pdf_page_count = len(normalized_pages)
            pdf_visual_pages = pages_to_render
            pdf_coverage_path = artifact_dir / "pdf_coverage.json"
            _atomic_write_json(
                pdf_coverage_path,
                {
                    "schema_version": 1,
                    "engine": str(extracted.get("engine") or "local"),
                    "original_sha256": original_sha,
                    "page_count": pdf_page_count,
                    "pages": coverage_pages,
                },
            )
        else:
            try:
                evidence_text = original.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError as exc:
                raise EnrichmentError("native text evidence must be UTF-8") from exc
            if not evidence_text:
                raise EnrichmentError("native text evidence is empty")

        evidence_path = artifact_dir / "evidence.txt"
        temporary_evidence = artifact_dir / ".evidence.partial.txt"
        temporary_evidence.write_text(evidence_text + "\n", encoding="utf-8")
        temporary_evidence.replace(evidence_path)
        observed_at = self._time()
        source_modified_at = datetime.fromtimestamp(
            int(item["modified_at"]),
            tz=observed_at.tzinfo,
        )
        first_observed_at = str(
            item.get("version_first_seen_at")
            or item.get("first_seen_at")
            or observed_at.isoformat(timespec="seconds")
        )
        result = {
            "event": "subscription_evidence_ingested",
            "source": "baidu_subscription_share_browser",
            "author": "吕晓彤",
            "identity": str(item["identity"]),
            "version_key": str(item["version_key"]),
            "title": str(item["name"]),
            "media_type": str(item["media_type"]),
            "published_at": source_modified_at.isoformat(timespec="seconds"),
            "published_at_basis": "provider_modified_at_proxy",
            "source_modified_at": source_modified_at.isoformat(
                timespec="seconds"
            ),
            "captured_at": first_observed_at,
            "first_observed_at": first_observed_at,
            "original_path": str(original.resolve()),
            "original_sha256": original_sha,
            "acquisition_transport": str(
                receipt.get("acquisition_transport") or "browser_download"
            ),
            "source_byte_exact": receipt.get("source_byte_exact") is not False,
            "source_expected_size": int(receipt.get("expected_size") or 0),
            "acquired_size": int(receipt.get("actual_size") or 0),
            "source_provider_file_id": receipt.get("source_provider_file_id"),
            "preview_pixel_width": receipt.get("preview_pixel_width"),
            "preview_pixel_height": receipt.get("preview_pixel_height"),
            "evidence_path": str(evidence_path.resolve()),
            "evidence_sha256": _sha256_file(evidence_path),
            "ocr_path": str(ocr_path.resolve()) if ocr_path else None,
            "ocr_sha256": _sha256_file(ocr_path) if ocr_path else None,
            "pdf_coverage_path": (
                str(pdf_coverage_path.resolve()) if pdf_coverage_path else None
            ),
            "pdf_coverage_sha256": (
                _sha256_file(pdf_coverage_path) if pdf_coverage_path else None
            ),
            "pdf_page_count": pdf_page_count,
            "pdf_visual_pages": pdf_visual_pages,
            "ambiguities": ambiguities,
            "idempotent_replay": False,
        }
        _atomic_write_json(result_path, result)
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in result.items()
                if key not in {"ambiguities", "idempotent_replay"}
            },
        )
        return result

    def pending_items(self) -> list[dict[str, Any]]:
        """Return resumable current-version work that has not reached decisions."""
        pending: list[dict[str, Any]] = []
        for item in self._load_manifest().get("items", {}).values():
            if (
                not isinstance(item, dict)
                or item.get("present") is not True
                or item.get("media_type") not in SUPPORTED_SMALL_MEDIA
                or item.get("work_eligible") is not True
            ):
                continue
            artifact_dir = (
                self.output_dir / "artifacts" / str(item["version_key"])
            )
            if (artifact_dir / "decision_state.json").is_file():
                continue
            relationship_path = artifact_dir / "pdf_relationship.json"
            relationship: dict[str, Any] | None = None
            if relationship_path.is_file():
                try:
                    relationship = json.loads(
                        relationship_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    raise EnrichmentError(
                        "subscription PDF relationship state is invalid"
                    ) from exc
                if relationship.get("route") == "companion_suppressed":
                    continue
            if (
                isinstance(relationship, dict)
                and relationship.get("route") == "waiting_primary_source"
            ):
                stage = "relationship_waiting"
            elif (artifact_dir / "analysis_request.json").is_file():
                stage = "analysis_requested"
            elif (artifact_dir / "ingest_result.json").is_file():
                stage = "ingested"
            elif (artifact_dir / "browser_download_receipt.json").is_file():
                stage = "downloaded"
            elif (artifact_dir / "browser_download_claim.json").is_file():
                stage = "download_claimed"
            else:
                stage = "discovered"
            pending.append(
                {
                    key: item[key]
                    for key in (
                        "identity",
                        "version_key",
                        "path",
                        "name",
                        "media_type",
                        "size",
                        "modified_at",
                        "version_first_seen_at",
                    )
                    if item.get(key) is not None
                }
                | {"stage": stage}
            )
        pending.sort(
            key=lambda row: (
                int(row["modified_at"]),
                str(row["path"]),
                str(row["identity"]),
            )
        )
        return pending

    def _episode_relation_candidates(
        self,
        item: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Expose candidates only; semantic evidence must decide any relationship."""
        if item.get("media_type") != "pdf":
            return []
        candidates = []
        for candidate in self._load_manifest().get("items", {}).values():
            if (
                not isinstance(candidate, dict)
                or candidate.get("present") is not True
                or Path(str(candidate.get("name") or "")).suffix.lower()
                not in {".avi", ".flv", ".m4v", ".mkv", ".mov", ".mp4"}
                or abs(
                    int(candidate.get("modified_at") or 0)
                    - int(item.get("modified_at") or 0)
                )
                > PDF_BOOTSTRAP_WINDOW_SECONDS
            ):
                continue
            candidates.append(
                {
                    key: candidate[key]
                    for key in (
                        "identity",
                        "version_key",
                        "path",
                        "name",
                        "size",
                        "modified_at",
                    )
                }
            )
        candidates.sort(
            key=lambda row: (
                int(row["modified_at"]),
                str(row["path"]),
                str(row["identity"]),
            )
        )
        return candidates

    @staticmethod
    def _content_product_candidates(item: dict[str, Any]) -> list[dict[str, str]]:
        """Return non-authoritative metadata hints for semantic routing."""
        path = str(item.get("path") or "")
        candidates = []
        if "/直播回放/" in path:
            candidates.append({
                "product": "member_livestream",
                "basis": "provider_directory",
            })
        if "/报告/" in path:
            candidates.append({
                "product": "underlying_logic",
                "basis": "provider_directory",
            })
        return candidates

    def metadata_companion_proof(
        self,
        identity: str,
        *,
        complete_video_transcripts: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return a strict no-download companion proof or no conclusion."""
        item = self._manifest_item(str(identity))
        if item.get("media_type") != "pdf":
            return None
        pdf_stem = PurePosixPath(str(item["name"])).stem
        pdf_date = re.search(r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日", pdf_stem)
        summary_semantics = (
            any(marker in pdf_stem for marker in ("总结", "纪要", "要点"))
            and "直播" in pdf_stem
        )
        if pdf_date is None or not summary_semantics:
            return None
        matches = []
        for video in complete_video_transcripts:
            video_stem = PurePosixPath(str(video.get("name") or "")).stem
            video_date = re.search(
                r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日",
                video_stem,
            )
            try:
                delta = int(item["modified_at"]) - int(video["modified_at"])
            except (KeyError, TypeError, ValueError):
                continue
            transcript_path = Path(
                str(video.get("transcript_path") or "")
            ).expanduser()
            transcript_sha256 = str(
                video.get("transcript_sha256") or ""
            )
            if (
                video_date is None
                or pdf_date.groups()[1:] != video_date.groups()[1:]
                or PurePosixPath(str(item["path"])).parent
                != PurePosixPath(str(video.get("path") or "")).parent
                or not 0 <= delta <= 12 * 60 * 60
                or video.get("transcript_complete") is not True
                or not re.fullmatch(
                    r"[0-9a-f]{64}",
                    transcript_sha256,
                )
                or not transcript_path.is_file()
                or _sha256_file(transcript_path) != transcript_sha256
            ):
                continue
            matches.append((video, delta))
        if len(matches) != 1:
            return None
        video, delta = matches[0]
        return {
            "document_role": "video_summary",
            "primary_source_status": "complete",
            "related_source_part": {
                key: video[key]
                for key in (
                    "identity",
                    "version_key",
                    "provider_identity_sha256",
                    "path",
                    "name",
                    "size",
                    "modified_at",
                    "transcript_path",
                    "transcript_sha256",
                )
            }
            | {"transcript_complete": True},
            "relation_basis": {
                "same_provider_parent": True,
                "same_title_date": True,
                "summary_title_semantics": True,
                "pdf_after_video_seconds": delta,
                "complete_transcript_sha256_verified": True,
                "filename_only": False,
            },
        }

    @_exclusive("item")
    def record_metadata_companion_suppression(
        self,
        identity: str,
        *,
        proof: dict[str, Any],
    ) -> dict[str, Any]:
        """Suppress an exact companion before claim/download when proof is complete."""
        item = self._manifest_item(str(identity))
        if item.get("media_type") != "pdf":
            raise EnrichmentError(
                "metadata companion suppression requires a PDF"
            )
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        if any(
            (artifact_dir / name).exists()
            for name in (
                "browser_download_claim.json",
                "browser_download_receipt.json",
                "ingest_result.json",
                "analysis_request.json",
            )
        ):
            raise EnrichmentError(
                "metadata companion suppression must precede acquisition"
            )
        expected = self.metadata_companion_proof(
            str(identity),
            complete_video_transcripts=[
                dict(proof.get("related_source_part") or {})
            ],
        )
        if expected != proof:
            raise EnrichmentError(
                "metadata companion suppression proof is incomplete"
            )
        state_path = artifact_dir / "pdf_relationship.json"
        proof_sha256 = hashlib.sha256(
            _canonical(proof).encode("utf-8")
        ).hexdigest()
        if state_path.is_file():
            try:
                prior = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "subscription PDF relationship state is invalid"
                ) from exc
            if (
                prior.get("route") != "companion_suppressed"
                or prior.get("relationship_sha256") != proof_sha256
            ):
                raise EnrichmentError(
                    "terminal subscription PDF relationship cannot change"
                )
            return {**prior, "idempotent_replay": True}
        state = {
            "event": "subscription_pdf_companion_suppressed",
            "status": "completed",
            "route": "companion_suppressed",
            "identity": str(item["identity"]),
            "version_key": str(item["version_key"]),
            "provider_path": str(item["path"]),
            "provider_name": str(item["name"]),
            "provider_size": int(item["size"]),
            "provider_modified_at": int(item["modified_at"]),
            "relationship_sha256": proof_sha256,
            "document_role": "video_summary",
            "primary_source_status": "complete",
            "related_source_part": proof["related_source_part"],
            "relation_basis": proof["relation_basis"],
            "acquisition_skipped": True,
            "business_effects": {
                "report": "not_created",
                "notification": "not_created",
                "book_kol_us": "not_created",
                "durable_knowledge": "not_created",
            },
            "resolved_at": self._time().isoformat(timespec="seconds"),
            "idempotent_replay": False,
        }
        _atomic_write_json(state_path, state)
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in state.items()
                if key not in {"related_source_part", "idempotent_replay"}
            },
        )
        return state

    def _validated_pdf_relationship(
        self,
        ingest: dict[str, Any],
        decision_item: dict[str, Any],
        *,
        complete_video_transcripts: Sequence[Mapping[str, Any]] = (),
    ) -> tuple[dict[str, Any], str]:
        relationship = decision_item.get("episode_relationship")
        if not isinstance(relationship, dict):
            raise EnrichmentError(
                "subscription PDF episode relationship is unresolved"
            )
        role = str(relationship.get("document_role") or "")
        primary_status = str(
            relationship.get("primary_source_status") or ""
        )
        comparison = relationship.get("semantic_comparison")
        quotes = relationship.get("content_evidence_quotes")
        if (
            role not in PDF_DOCUMENT_ROLES
            or primary_status not in PDF_PRIMARY_SOURCE_STATUSES
            or not str(relationship.get("reason") or "").strip()
            or not isinstance(
                relationship.get("provider_metadata_basis"), list
            )
            or not relationship.get("provider_metadata_basis")
            or not isinstance(comparison, dict)
            or not isinstance(comparison.get("substantive_new_points"), bool)
            or not str(comparison.get("summary") or "").strip()
            or not isinstance(quotes, list)
            or not quotes
        ):
            raise EnrichmentError(
                "subscription PDF episode relationship is unresolved"
            )
        evidence_path = Path(str(ingest.get("evidence_path") or ""))
        try:
            evidence_text = evidence_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise EnrichmentError(
                "subscription PDF evidence is unavailable"
            ) from exc
        if any(
            not isinstance(quote, str)
            or not quote.strip()
            or quote not in evidence_text
            for quote in quotes
        ):
            raise EnrichmentError(
                "subscription PDF episode relationship is not evidence-bound"
            )

        related = relationship.get("related_source_part")
        candidate_key: tuple[str, str] | None = None
        if isinstance(related, dict):
            candidate_key = (
                str(related.get("identity") or ""),
                str(related.get("version_key") or ""),
            )
        candidates = {
            (str(row["identity"]), str(row["version_key"]))
            for row in self._episode_relation_candidates(
                self._manifest_item(str(ingest["identity"]))
            )
        }
        if role == "video_summary" or primary_status != "not_applicable":
            if candidate_key not in candidates:
                raise EnrichmentError(
                    "subscription PDF related source metadata is incomplete"
                )
        if primary_status == "complete":
            authoritative_matches = []
            if isinstance(related, dict):
                for video in complete_video_transcripts:
                    transcript_path = Path(
                        str(video.get("transcript_path") or "")
                    ).expanduser()
                    transcript_sha256 = str(
                        video.get("transcript_sha256") or ""
                    )
                    if (
                        str(video.get("provider_identity_sha256") or "")
                        == str(related.get("identity") or "")
                        and str(video.get("path") or "")
                        == str(related.get("path") or "")
                        and str(video.get("name") or "")
                        == str(related.get("name") or "")
                        and int(video.get("size") or 0)
                        == int(related.get("size") or 0)
                        and int(video.get("modified_at") or 0)
                        == int(related.get("modified_at") or 0)
                        and video.get("transcript_complete") is True
                        and re.fullmatch(r"[0-9a-f]{64}", transcript_sha256)
                        and transcript_path.is_file()
                        and _sha256_file(transcript_path) == transcript_sha256
                    ):
                        authoritative_matches.append(video)
            if len(authoritative_matches) == 1 and isinstance(related, dict):
                video = authoritative_matches[0]
                related = {
                    **related,
                    "transcript_complete": True,
                    "transcript_path": str(
                        Path(str(video["transcript_path"])).resolve()
                    ),
                    "transcript_sha256": str(video["transcript_sha256"]),
                    "processed_source_identity": str(video["identity"]),
                    "processed_source_version_key": str(video["version_key"]),
                }
                relationship = {
                    **relationship,
                    "related_source_part": related,
                }
            if (
                not isinstance(related, dict)
                or not re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(related.get("transcript_sha256") or ""),
                )
                or related.get("transcript_complete") is not True
            ):
                raise EnrichmentError(
                    "subscription PDF primary transcript is not proven complete"
                )
        if primary_status in {"unavailable", "incomplete"}:
            failure = relationship.get("primary_source_failure")
            if (
                not isinstance(failure, dict)
                or failure.get("receipt_reconciled") is not True
                or not str(failure.get("code") or "").strip()
                or not str(failure.get("stage") or "").strip()
            ):
                raise EnrichmentError(
                    "subscription PDF fallback lacks reconciled primary failure"
                )

        substantive_new = comparison["substantive_new_points"] is True
        if role == "independent_report":
            route = "independent"
        elif substantive_new and primary_status == "complete":
            route = "merged_event"
        elif substantive_new:
            route = "fallback"
        elif role == "video_summary" and primary_status == "complete":
            route = "companion_suppressed"
        elif primary_status in {"unavailable", "incomplete"}:
            route = "fallback"
        else:
            route = "waiting_primary_source"
        return relationship, route

    @_exclusive("item")
    def record_pdf_relationship(
        self,
        identity: str,
        *,
        bundle_path: Path | str,
        complete_video_transcripts: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Persist the primary-source routing gate before any publication effect."""
        item = self._manifest_item(str(identity))
        if item.get("media_type") != "pdf":
            raise EnrichmentError(
                "subscription relationship routing requires a PDF"
            )
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        ingest_path = artifact_dir / "ingest_result.json"
        try:
            ingest = json.loads(ingest_path.read_text(encoding="utf-8"))
            bundle_file = Path(bundle_path).expanduser().resolve()
            bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
            decision_item = bundle["items"][0]
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise EnrichmentError(
                "subscription PDF relationship bundle is invalid"
            ) from exc
        relationship, route = self._validated_pdf_relationship(
            ingest,
            decision_item,
            complete_video_transcripts=complete_video_transcripts,
        )
        relationship_sha256 = hashlib.sha256(
            _canonical(relationship).encode("utf-8")
        ).hexdigest()
        state_path = artifact_dir / "pdf_relationship.json"
        if state_path.is_file():
            try:
                prior = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "subscription PDF relationship state is invalid"
                ) from exc
            if (
                prior.get("identity") != item["identity"]
                or prior.get("version_key") != item["version_key"]
            ):
                raise EnrichmentError(
                    "subscription PDF relationship changed source version"
                )
            if prior.get("route") != "waiting_primary_source":
                if (
                    prior.get("relationship_sha256") != relationship_sha256
                    or prior.get("route") != route
                ):
                    raise EnrichmentError(
                        "terminal subscription PDF relationship cannot change"
                    )
                return {**prior, "idempotent_replay": True}
        state = {
            "event": "subscription_pdf_relationship_resolved",
            "status": (
                "completed"
                if route in {
                    "companion_suppressed",
                    "independent",
                    "fallback",
                    "merged_event",
                }
                else "waiting"
            ),
            "route": route,
            "identity": str(item["identity"]),
            "version_key": str(item["version_key"]),
            "relationship_sha256": relationship_sha256,
            "document_role": relationship["document_role"],
            "primary_source_status": relationship["primary_source_status"],
            "related_source_part": relationship.get("related_source_part"),
            "resolved_at": self._time().isoformat(timespec="seconds"),
            "business_effects": {
                "report": "not_created",
                "notification": "not_created",
                "book_kol_us": "not_created",
                "durable_knowledge": "not_created",
            },
            "idempotent_replay": False,
        }
        _atomic_write_json(state_path, state)
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in state.items()
                if key not in {"related_source_part", "idempotent_replay"}
            },
        )
        return state

    def prepare_analysis_request(
        self,
        ingest: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist the safe handoff from deterministic evidence to judgment."""
        version_key = str(ingest.get("version_key") or "")
        identity = str(ingest.get("identity") or "")
        item = self._manifest_item(identity)
        if version_key != item["version_key"]:
            raise EnrichmentError(
                "subscription analysis request changed source version"
            )
        artifact_dir = self.output_dir / "artifacts" / version_key
        request_path = artifact_dir / "analysis_request.json"
        request = {
            "schema_version": 2,
            "event": "subscription_analysis_requested",
            "status": "waiting_for_analysis",
            "source": ingest["source"],
            "author": ingest["author"],
            "author_profile": semantic_author_profile(ingest["author"]),
            "identity": identity,
            "version_key": version_key,
            "source_identity": identity,
            "source_version_key": version_key,
            "handoff_id": identity,
            "message_sha256": ingest["evidence_sha256"],
            "content_sha256": ingest["evidence_sha256"],
            "media_identity": f"not_applicable:{identity}",
            "artifact_dir": str(artifact_dir.resolve()),
            "title": ingest["title"],
            "media_type": ingest["media_type"],
            "published_at": ingest["published_at"],
            "published_at_basis": ingest["published_at_basis"],
            "source_modified_at": ingest["source_modified_at"],
            "captured_at": ingest["captured_at"],
            "first_observed_at": ingest.get("first_observed_at"),
            "evidence_path": ingest["evidence_path"],
            "evidence_sha256": ingest["evidence_sha256"],
            "original_evidence_path": ingest["original_path"],
            "original_evidence_sha256": ingest["original_sha256"],
            "acquisition_transport": ingest.get("acquisition_transport"),
            "source_byte_exact": ingest.get("source_byte_exact") is not False,
            "source_expected_size": ingest.get("source_expected_size"),
            "acquired_size": ingest.get("acquired_size"),
            "source_provider_file_id": ingest.get("source_provider_file_id"),
            "preview_pixel_width": ingest.get("preview_pixel_width"),
            "preview_pixel_height": ingest.get("preview_pixel_height"),
            "ocr_path": ingest.get("ocr_path"),
            "ocr_sha256": ingest.get("ocr_sha256"),
            "pdf_coverage_path": ingest.get("pdf_coverage_path"),
            "pdf_coverage_sha256": ingest.get("pdf_coverage_sha256"),
            "pdf_page_count": ingest.get("pdf_page_count"),
            "pdf_visual_pages": ingest.get("pdf_visual_pages") or [],
            "episode_relationship_contract": (
                {
                    "status": "requires_evidence_bound_resolution",
                    "document_roles": sorted(PDF_DOCUMENT_ROLES),
                    "primary_source_statuses": sorted(
                        PDF_PRIMARY_SOURCE_STATUSES
                    ),
                    "precedence": [
                        "complete_video_transcript",
                        "independent_report_pdf",
                        "video_summary_pdf",
                    ],
                    "rule": (
                        "Resolve provider directory, mtime/version, title/date, "
                        "PDF content, and video-transcript semantics together. "
                        "A filename alone is never sufficient. A complete "
                        "video transcript suppresses a summary PDF unless the "
                        "PDF adds substantive viewpoints or is an independent "
                        "report event."
                    ),
                    "candidates": self._episode_relation_candidates(item),
                }
                if ingest["media_type"] == "pdf"
                else None
            ),
            "ambiguities": ingest.get("ambiguities") or [],
            "required_coverage_rows": sorted(_COVERAGE_ROWS),
            "investment_claim_extraction": build_claim_extraction_request(
                ingest["evidence_path"],
                evidence_sha256=str(ingest["evidence_sha256"]),
            ),
            "reader_insight_contract": {
                "useful": (
                    "send a concise evidence-bound insight even when confidence "
                    "is low; link only genuinely relevant household positions"
                ),
                "none": (
                    "persist the reason and suppress household delivery only "
                    "when nothing useful can be accurately relayed"
                ),
            },
            "claim_semantic_routing_contract": {
                "content_products": sorted(LV_CONTENT_PRODUCTS),
                "metadata_candidates": self._content_product_candidates(item),
                "rule": (
                    "Classify claims from complete evidence, not file type or "
                    "filename. Route current-decision claims and durable-knowledge "
                    "claims independently while preserving one report per real event."
                ),
                "member_livestream": (
                    "complete transcript -> current facts -> event report -> "
                    "eligible reminder -> paper-only Book"
                ),
                "underlying_logic": (
                    "reusable causal models, methods, and case frameworks -> "
                    "report_only durable knowledge with authority=0; no alert and "
                    "reasoned no_trade when no current-decision claim exists"
                ),
                "authority_boundary": {
                    "author_class": "other_author",
                    "authority": 0,
                    "may_update_posture_current": False,
                    "may_update_regime_timeline": False,
                    "may_tune_strategy": False,
                    "promotion_requires": ["research_harness", "human_gate"],
                },
            },
            "next_checkpoint": (
                "evidence-bound reader insight, current-market judgment, "
                "household advice, and paper-only Book KOL-US intent"
            ),
            "requested_at": self._time().isoformat(timespec="seconds"),
            "request_path": str(request_path.resolve()),
            "idempotent_replay": False,
        }
        if request_path.is_file():
            try:
                prior = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "subscription analysis request is invalid"
                ) from exc
            if (
                prior.get("identity") != identity
                or prior.get("version_key") != version_key
                or prior.get("evidence_sha256")
                != ingest.get("evidence_sha256")
            ):
                raise EnrichmentError(
                    "subscription analysis request changed evidence"
                )
            expected_first_observed_at = ingest.get("first_observed_at")
            persisted_first_observed_at = prior.get("first_observed_at")
            if (
                persisted_first_observed_at is not None
                and persisted_first_observed_at != expected_first_observed_at
            ):
                raise EnrichmentError(
                    "subscription analysis request changed first_observed_at"
                )
            if (
                persisted_first_observed_at is None
                and expected_first_observed_at is not None
            ):
                prior = {
                    **prior,
                    "first_observed_at": expected_first_observed_at,
                }
                _atomic_write_json(request_path, prior)
            return {
                **prior,
                "evidence_path": ingest["evidence_path"],
                "original_evidence_path": ingest["original_path"],
                "ocr_path": ingest.get("ocr_path"),
                "pdf_coverage_path": ingest.get("pdf_coverage_path"),
                "idempotent_replay": True,
            }
        _atomic_write_json(request_path, request)
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in request.items()
                if key
                not in {
                    "ambiguities",
                    "evidence_path",
                    "original_evidence_path",
                    "ocr_path",
                    "request_path",
                    "idempotent_replay",
                }
            },
        )
        return request

    @_exclusive("run")
    def run_opencli(
        self,
        *,
        session: str,
        decision_output_dir: Path | str,
        bundle_builder: Callable[[dict[str, Any]], Path | str],
        sender: Callable[[str, str], dict[str, str]],
        profile: str | None = None,
        ocr_runner: Callable[[Path], dict[str, Any]] | None = None,
        pipeline: Any | None = None,
        bootstrap_bind: bool = False,
    ) -> dict[str, Any] | None:
        """Resume every small current item through both outputs in one runner."""
        if bootstrap_bind:
            self.bind_opencli(
                session=session,
                profile=profile,
            )
        discovery = self.poll_opencli(
            session=session,
            profile=profile,
        )
        pending = self.pending_items()
        if not pending:
            return None

        completed: list[dict[str, Any]] = []
        for row in pending:
            identity = str(row["identity"])
            download = self.download_opencli(
                identity,
                session=session,
                profile=profile,
            )
            ingest = self.ingest_browser_download(
                identity,
                ocr_runner=ocr_runner,
            )
            analysis_request = self.prepare_analysis_request(ingest)
            bundle_path = Path(
                bundle_builder(
                    {
                        **ingest,
                        "analysis_request_path": analysis_request[
                            "request_path"
                        ],
                    }
                )
            ).expanduser().resolve()
            if ingest["media_type"] == "pdf":
                relationship = self.record_pdf_relationship(
                    identity,
                    bundle_path=bundle_path,
                )
                if relationship["route"] in {
                    "companion_suppressed",
                    "waiting_primary_source",
                }:
                    completed.append(
                        {
                            "identity": identity,
                            "version_key": str(row["version_key"]),
                            "media_type": "pdf",
                            "download": {
                                "status": download["status"],
                                "idempotent_replay": download.get(
                                    "idempotent_replay", False
                                ),
                            },
                            "ingest": {
                                "status": "ingested",
                                "idempotent_replay": ingest.get(
                                    "idempotent_replay", False
                                ),
                            },
                            "relationship": relationship,
                        }
                    )
                    continue
            decision = self.decide(
                identity,
                bundle_path=bundle_path,
                decision_output_dir=decision_output_dir,
                sender=sender,
                pipeline=pipeline,
            )
            completed.append(
                {
                    "identity": identity,
                    "version_key": str(row["version_key"]),
                    "media_type": str(row["media_type"]),
                    "download": {
                        "status": download["status"],
                        "idempotent_replay": download.get(
                            "idempotent_replay",
                            False,
                        ),
                    },
                    "ingest": {
                        "status": "ingested",
                        "idempotent_replay": ingest.get(
                            "idempotent_replay",
                            False,
                        ),
                    },
                    "decision": decision,
                }
            )
        return {
            "event": "subscription_run_completed",
            "status": "completed",
            "source": "baidu_subscription_share_browser",
            "author": "吕晓彤",
            "cursor": (
                discovery.get("cursor")
                if isinstance(discovery, dict)
                else self._load_manifest().get("cursor")
            ),
            "items": completed,
            "completed_at": self._time().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _validate_coverage(
        item: dict[str, Any],
        *,
        evidence_text: str,
    ) -> None:
        coverage = item.get("trade_information_coverage")
        if not isinstance(coverage, dict) or not _COVERAGE_ROWS.issubset(coverage):
            raise EnrichmentError(
                "trade information coverage matrix is incomplete"
            )
        for name in sorted(_COVERAGE_ROWS):
            row = coverage.get(name)
            if not isinstance(row, dict) or row.get("status") not in {
                "present",
                "absent",
            }:
                raise EnrichmentError(
                    f"coverage matrix row is invalid: {name}"
                )
            if row["status"] == "absent":
                if not str(row.get("reason") or "").strip():
                    raise EnrichmentError(
                        f"coverage matrix absent row needs a reason: {name}"
                    )
                continue
            quotes = row.get("evidence_quotes")
            if (
                not isinstance(quotes, list)
                or not quotes
                or any(
                    not isinstance(quote, str)
                    or not quote.strip()
                    or quote not in evidence_text
                    for quote in quotes
                )
            ):
                raise EnrichmentError(
                    f"coverage matrix quotes are not bound to evidence: {name}"
                )
            for field in ("reader_meaning", "horizon", "triggers", "falsifiers"):
                value = row.get(field)
                if field in {"triggers", "falsifiers"}:
                    valid = (
                        isinstance(value, list)
                        and bool(value)
                        and all(
                            isinstance(entry, str) and entry.strip()
                            for entry in value
                        )
                    )
                else:
                    valid = isinstance(value, str) and bool(value.strip())
                if not valid:
                    raise EnrichmentError(
                        f"coverage matrix row needs {field}: {name}"
                    )
        inventory = coverage["named_asset_inventory"]
        assets = inventory.get("assets")
        if not isinstance(assets, list):
            raise EnrichmentError(
                "coverage matrix named asset inventory must be a list"
            )
        for asset in assets:
            if not isinstance(asset, dict) or any(
                not str(asset.get(field) or "").strip()
                for field in ("surface_form", "role", "resolution_status")
            ):
                raise EnrichmentError(
                    "coverage matrix named asset inventory row is invalid"
                )
            if asset["resolution_status"] == "resolved" and any(
                not str(asset.get(field) or "").strip()
                for field in ("official_name", "market")
            ):
                raise EnrichmentError(
                    "resolved named asset requires official name and market"
                )
            if asset["resolution_status"] != "resolved" and not str(
                asset.get("exclusion_reason") or ""
            ).strip():
                raise EnrichmentError(
                    "unresolved named asset requires an exclusion reason"
                )

    def _validate_decision_bundle(
        self,
        bundle: Any,
        *,
        ingest: dict[str, Any],
    ) -> dict[str, Any]:
        items = bundle.get("items") if isinstance(bundle, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise EnrichmentError("one subscription item requires one decision item")
        item = items[0]
        evidence_path = Path(str(ingest["evidence_path"])).resolve()
        original_path = Path(str(ingest["original_path"])).resolve()
        if Path(str(item.get("evidence_path") or "")).expanduser().resolve() != evidence_path:
            raise EnrichmentError(
                "decision bundle evidence_path must match ingested evidence"
            )
        if (
            Path(str(item.get("original_evidence_path") or ""))
            .expanduser()
            .resolve()
            != original_path
        ):
            raise EnrichmentError(
                "decision bundle must retain the original subscription evidence"
            )
        for field in (
            "source",
            "author",
            "title",
            "published_at",
            "published_at_basis",
            "source_modified_at",
            "captured_at",
            "first_observed_at",
            "media_type",
        ):
            if item.get(field) != ingest.get(field):
                raise EnrichmentError(
                    f"decision bundle source metadata mismatch: {field}"
                )
        decision_status = item.get("decision_status")
        if decision_status not in {"actionable_signal", "no_actionable_signal"}:
            raise EnrichmentError("decision_status is invalid")
        if decision_status == "no_actionable_signal" and not str(
            item.get("decision_reason") or ""
        ).strip():
            raise EnrichmentError("no_actionable_signal requires a reason")
        if decision_status == "no_actionable_signal":
            insight = item.get("reader_insight")
            if (
                not isinstance(insight, dict)
                or insight.get("status") not in {"useful", "none"}
            ):
                raise EnrichmentError(
                    "no_actionable_signal requires reader_insight useful or none"
                )
            if insight["status"] == "useful" and any(
                not str(insight.get(field) or "").strip()
                for field in ("summary", "boundary")
            ):
                raise EnrichmentError(
                    "useful reader_insight requires summary and boundary"
                )
            if insight["status"] == "none" and not str(
                insight.get("reason") or ""
            ).strip():
                raise EnrichmentError("empty reader_insight requires a reason")
        knowledge_status = item.get("knowledge_status")
        if knowledge_status not in {"reusable_knowledge", "no_reusable_knowledge"}:
            raise EnrichmentError("knowledge_status is invalid")
        if knowledge_status == "no_reusable_knowledge" and not str(
            item.get("knowledge_reason") or ""
        ).strip():
            raise EnrichmentError("no_reusable_knowledge requires a reason")
        if knowledge_status == "reusable_knowledge":
            if not str(item.get("durable_distillation_path") or "").strip():
                raise EnrichmentError(
                    "reusable_knowledge requires a durable distillation path"
                )
            if not isinstance(item.get("routed_hypothesis_ids"), list):
                raise EnrichmentError(
                    "reusable_knowledge requires routed hypothesis ids"
                )
        routing = item.get("claim_semantic_routing")
        if not isinstance(routing, dict):
            raise EnrichmentError(
                "Lv claim-semantic routing is incomplete"
            )
        product = str(routing.get("content_product") or "")
        current_claim_ids = routing.get("current_decision_claim_ids")
        durable_claim_ids = routing.get("durable_knowledge_claim_ids")
        if (
            product not in LV_CONTENT_PRODUCTS
            or not isinstance(current_claim_ids, list)
            or not isinstance(durable_claim_ids, list)
            or any(
                not isinstance(claim_id, str) or not claim_id.strip()
                for claim_id in [*current_claim_ids, *durable_claim_ids]
            )
            or len(set(current_claim_ids)) != len(current_claim_ids)
            or len(set(durable_claim_ids)) != len(durable_claim_ids)
            or set(current_claim_ids) & set(durable_claim_ids)
        ):
            raise EnrichmentError(
                "Lv claim-semantic routing is invalid"
            )
        if product == "hybrid" and (
            not current_claim_ids or not durable_claim_ids
        ):
            raise EnrichmentError(
                "hybrid Lv content needs both semantic claim branches"
            )
        if durable_claim_ids:
            authority = routing.get("durable_authority")
            if (
                authority != 0
                or routing.get("may_update_posture_current") is not False
                or routing.get("may_update_regime_timeline") is not False
                or routing.get("may_tune_strategy") is not False
                or knowledge_status != "reusable_knowledge"
            ):
                raise EnrichmentError(
                    "Lv durable knowledge exceeded its authority boundary"
                )
            distillation = Path(
                str(item.get("durable_distillation_path") or "")
            )
            if "reference/experience/distilled" not in distillation.as_posix():
                raise EnrichmentError(
                    "Lv durable knowledge needs the reviewed distillation path"
                )
        if not current_claim_ids and durable_claim_ids:
            content_value = item.get("content_value") or {}
            reader_insight = item.get("reader_insight") or {}
            paper_intent = item.get("book_kol_us") or {}
            if (
                decision_status != "no_actionable_signal"
                or reader_insight.get("status") != "useful"
                or content_value.get("status") != "promoted"
                or content_value.get("tier") != "report_only"
                or paper_intent.get("decision") != "not_applicable"
                or not str(paper_intent.get("reason") or "").strip()
            ):
                raise EnrichmentError(
                    "durable-only Lv knowledge must be report-only with no Book effect"
                )
        if not isinstance(item.get("market_outlook"), dict):
            raise EnrichmentError(
                "subscription decision requires a full-band market outlook"
            )
        paper_intent = item.get("book_kol_us")
        if (
            not isinstance(paper_intent, dict)
            or paper_intent.get("book") != "KOL-US"
            or paper_intent.get("paper_only") is not True
        ):
            raise EnrichmentError(
                "subscription Book KOL-US requires a paper-only contract"
            )
        ambiguities = ingest.get("ambiguities") or []
        if ingest.get("media_type") == "image" and ambiguities:
            assessments = item.get("ocr_ambiguity_assessment")
            if not isinstance(assessments, list) or len(assessments) != len(
                ambiguities
            ):
                raise EnrichmentError(
                    "OCR ambiguity assessment must cover every low-confidence line"
                )
            by_text = {
                str(row.get("text") or ""): row
                for row in assessments
                if isinstance(row, dict)
            }
            actionable_text = "\n".join(
                str(claim.get("reader_quote") or claim.get("quote") or "")
                for claim in item.get("claims") or []
                if isinstance(claim, dict)
            )
            for ambiguity in ambiguities:
                text = str(ambiguity.get("text") or "")
                assessment = by_text.get(text)
                if (
                    not isinstance(assessment, dict)
                    or not isinstance(assessment.get("actionable"), bool)
                    or not str(assessment.get("reason") or "").strip()
                ):
                    raise EnrichmentError(
                        "OCR ambiguity assessment is incomplete"
                    )
                if assessment["actionable"]:
                    if (
                        assessment.get("human_confirmed") is not True
                        or not str(assessment.get("resolved_text") or "").strip()
                    ):
                        raise EnrichmentError(
                            "actionable OCR ambiguity requires human confirmation"
                        )
                elif text and text in actionable_text:
                    raise EnrichmentError(
                        "excluded OCR ambiguity cannot support a claim"
                    )
        if ingest.get("media_type") == "pdf":
            coverage_path = Path(str(ingest.get("pdf_coverage_path") or ""))
            if (
                not coverage_path.is_file()
                or _sha256_file(coverage_path)
                != ingest.get("pdf_coverage_sha256")
            ):
                raise EnrichmentError(
                    "subscription PDF coverage evidence is unavailable"
                )
            try:
                pdf_coverage = json.loads(
                    coverage_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError(
                    "subscription PDF coverage evidence is invalid"
                ) from exc
            pages = pdf_coverage.get("pages")
            if (
                not isinstance(pages, list)
                or len(pages) != int(ingest.get("pdf_page_count") or 0)
            ):
                raise EnrichmentError(
                    "subscription PDF page coverage is incomplete"
                )
            visual_pages = {
                int(row["page"])
                for row in pages
                if isinstance(row, dict) and row.get("rendered_path")
            }
            assessments = item.get("pdf_page_coverage_assessment")
            if visual_pages:
                if not isinstance(assessments, list):
                    raise EnrichmentError(
                        "subscription PDF visual pages need reviewed coverage"
                    )
                assessed = {
                    int(row.get("page") or 0)
                    for row in assessments
                    if isinstance(row, dict)
                    and row.get("status") == "verified"
                    and str(row.get("summary") or "").strip()
                }
                if assessed != visual_pages:
                    raise EnrichmentError(
                        "subscription PDF visual review coverage is incomplete"
                    )
            _relationship, route = self._validated_pdf_relationship(
                ingest,
                item,
            )
            if route not in {"independent", "fallback", "merged_event"}:
                raise EnrichmentError(
                    "subscription PDF is not an independent publication item"
                )
        try:
            evidence_text = evidence_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise EnrichmentError("ingested subscription evidence is unavailable") from exc
        self._validate_coverage(item, evidence_text=evidence_text)
        try:
            validate_claim_coverage(
                item,
                evidence_text=evidence_text,
                evidence_sha256=str(ingest["evidence_sha256"]),
            )
        except DecisionError as exc:
            raise EnrichmentError(
                "subscription investment-claim coverage is incomplete"
            ) from exc
        return item

    @_exclusive("decision")
    def decide(
        self,
        identity: str,
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
        sender: Callable[[str, str], dict[str, str]],
        pipeline: Any | None = None,
    ) -> dict[str, Any]:
        """Validate one evidence-bound bundle, deliver once, and route paper-only."""
        item = self._manifest_item(str(identity))
        artifact_dir = self.output_dir / "artifacts" / str(item["version_key"])
        ingest_path = artifact_dir / "ingest_result.json"
        if not ingest_path.is_file():
            raise EnrichmentError("subscription item must be ingested before decision")
        try:
            ingest = json.loads(ingest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("subscription ingest result is invalid") from exc
        ingest = self._rebased_ingest_result(item, ingest)

        bundle_file = Path(bundle_path).expanduser().resolve()
        if not bundle_file.is_file():
            raise EnrichmentError("subscription decision bundle is missing")
        bundle_bytes = bundle_file.read_bytes()
        bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
        decision_state_path = artifact_dir / "decision_state.json"
        if decision_state_path.is_file():
            try:
                prior = json.loads(decision_state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EnrichmentError("subscription decision state is invalid") from exc
            prior_result_path = Path(
                str(prior.get("decision_result_path") or "")
            )
            if (
                not prior_result_path.is_file()
                or _sha256_file(prior_result_path)
                != prior.get("decision_result_sha256")
            ):
                raise EnrichmentError(
                    "subscription decision result changed after completion"
                )
            try:
                prior_result = json.loads(
                    prior_result_path.read_text(encoding="utf-8")
                )
                validate_decision_completion(prior_result)
            except (OSError, json.JSONDecodeError, EnrichmentError) as exc:
                raise EnrichmentError(
                    "subscription decision result changed after completion"
                ) from exc
            return {**prior, "idempotent_replay": True}
        try:
            bundle = json.loads(bundle_bytes)
        except json.JSONDecodeError as exc:
            raise EnrichmentError("subscription decision bundle is invalid JSON") from exc
        if isinstance(bundle, dict) and bundle.get("schema_version") == 2:
            receipt, bundle = read_validated_bundle(bundle_file)
            validate_receipt_bindings(
                receipt,
                {
                    "source_identity": ingest.get("identity") or item.get("identity"),
                    "source_version_key": ingest.get("version_key") or item.get("version_key"),
                    "transcript_sha256": ingest.get("evidence_sha256"),
                },
            )
        else:
            self._validate_decision_bundle(bundle, ingest=ingest)

        if pipeline is None:
            from .decisions import DecisionPipeline
            from .household import LiangHuiMcpClient

            pipeline = DecisionPipeline(
                Path(decision_output_dir),
                household_context_loader=LiangHuiMcpClient.from_config().load_context,
            )
        paper_account = getattr(getattr(pipeline, "book", None), "account", None)
        if (
            not isinstance(paper_account, dict)
            or paper_account.get("book") != "KOL-US"
            or paper_account.get("paper_only") is not True
        ):
            raise EnrichmentError(
                "subscription decision pipeline lacks a paper-only contract"
            )
        try:
            result = pipeline.process(bundle)
            validate_decision_process_result(result)
            result["wechat_delivery"] = pipeline.deliver_wechat(
                result,
                sender=sender,
            )
            notification, paper = validate_decision_completion(result)
        except Exception as exc:
            if isinstance(exc, EnrichmentError):
                raise
            raise _subscription_decision_pipeline_error(exc) from exc

        result_path = artifact_dir / "decision_result.json"
        _atomic_write_json(result_path, result)
        result_sha = _sha256_file(result_path)
        state = {
            "event": "subscription_decisions_completed",
            "status": "decided",
            "source": ingest["source"],
            "author": ingest["author"],
            "identity": ingest["identity"],
            "version_key": ingest["version_key"],
            "decision_bundle_path": str(bundle_file),
            "decision_bundle_sha256": bundle_sha,
            "decision_result_path": str(result_path.resolve()),
            "decision_result_sha256": result_sha,
            "household_notification": {
                key: notification[key]
                for key in ("idempotency_key", "status", "receipt", "reason")
                if notification.get(key) is not None
            },
            "book_kol_us": {
                key: paper[key]
                for key in (
                    "status",
                    "book",
                    "paper_only",
                    "ticker",
                    "side",
                    "reason",
                    "idempotency_key",
                )
                if paper.get(key) is not None
            },
            "completed_at": self._time().isoformat(timespec="seconds"),
            "idempotent_replay": False,
        }
        _atomic_write_json(decision_state_path, state)
        _append_jsonl(
            self.events_path,
            {
                key: value
                for key, value in state.items()
                if key != "idempotent_replay"
            },
        )
        return state
