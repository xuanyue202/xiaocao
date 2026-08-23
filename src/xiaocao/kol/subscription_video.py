"""Resumable cloud-only video intake for KOL Ticket 05."""

from __future__ import annotations

import fcntl
import functools
import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse

from ._shared import DecisionError
from .claim_coverage import (
    build_claim_extraction_request,
    validate_claim_coverage,
)
from .author_profiles import semantic_author_profile
from .enrichment_types import EnrichmentDiagnosticError, EnrichmentError
from .episodes import assemble_video_units
from .lv_subscription import LvSubscriptionService
from .netdisk_enrichment import NetdiskEnrichmentService
from .rendering import reader_message_title, render_household_item_message
from .runtime_paths import resolve_repo_owned_path
from .semantic_bundle import read_validated_bundle, validate_receipt_bindings


LV_SOURCE = "baidu_subscription_share_browser"
LUCIFER_SOURCE = "baidu_private_folder"
LV_AUTHOR = "吕晓彤"
LUCIFER_AUTHOR = "路西法"
LUCIFER_ROOT = "/课程/路西法全套"
LV_DESTINATION_PARENT = "/课程/自己的课"
LV_DESTINATION_DIRECTORY = "/课程/自己的课/吕晓彤"
LV_TRANSFER_CONFIRMATION_WINDOW = timedelta(minutes=30)
LV_TRANSFER_MAX_TRIGGER_ATTEMPTS = 2
VIDEO_SUFFIXES = {".avi", ".flv", ".m4v", ".mkv", ".mov", ".mp4"}
MAX_EPISODE_SPEC_BYTES = 16 * 1024 * 1024
MAX_EPISODE_REVIEW_SPEC_BYTES = 2 * 1024 * 1024
MAX_EPISODE_TRANSCRIPT_BYTES = 8 * 1024 * 1024
EPISODE_TRANSCRIPT_SUFFIXES = {".md", ".txt"}
DECISION_STATUSES = {"actionable_signal", "no_actionable_signal"}
KNOWLEDGE_STATUSES = {"reusable_knowledge", "no_reusable_knowledge"}
REQUIRED_COVERAGE_ROWS = {
    "todays_market_diagnosis",
    "next_session_playbook",
    "next_several_session_base_case",
    "style_market_cap_regime",
    "market_board_sector_hierarchy",
    "position_risk_budget",
    "named_asset_inventory",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPENCLI_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_PRIVATE_DIRECTORY_EVAL_PROCESS_TIMEOUT_SECONDS = 120
_DISCOVERY_HOT_WINDOW = timedelta(days=14)
_DISCOVERY_HOT_ROOT_LIMIT = 3
_DISCOVERY_COLD_ROOTS_PER_HOUR = 1


def _private_directory_url_matches(value: Any, directory: str) -> bool:
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.netloc != "pan.baidu.com"
        or parsed.path != "/disk/main"
    ):
        return False
    _route, separator, query = parsed.fragment.partition("?")
    if not separator:
        return False
    return parse_qs(query).get("path") == [directory]


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _remote_activity_at(row: dict[str, Any]) -> int:
    """Return the provider-side activity time used for discovery eligibility."""
    try:
        modified_at = int(row.get("modified_at") or 0)
        uploaded_at = int(row.get("uploaded_at") or 0)
    except (TypeError, ValueError) as exc:
        raise EnrichmentError("Ticket 05 remote time metadata is invalid") from exc
    if modified_at < 0 or uploaded_at < 0:
        raise EnrichmentError("Ticket 05 remote time metadata is invalid")
    return max(modified_at, uploaded_at)


def _parent_path(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return parent if parent != "." else "/"


def _is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _tiered_discovery_roots(
    items: Mapping[str, Any],
    *,
    source: str,
    root: str,
    now: datetime,
) -> tuple[list[str], list[str]]:
    """Select bounded hot roots plus one rotating cold shard.

    The persisted complete baseline is the topology authority. Directory mtimes
    are only ranking hints; they never authorize pruning an unscanned subtree.
    """
    activities: dict[str, int] = {}
    known_roots: set[str] = set()
    prefix = root.rstrip("/") + "/" if root != "/" else "/"
    for value in items.values():
        if not isinstance(value, Mapping) or value.get("source") != source:
            continue
        path = str(value.get("path") or "")
        if not path.startswith(prefix) or path == root:
            continue
        relative = path[len(prefix) :]
        component = relative.split("/", 1)[0]
        if not component:
            continue
        top = (root.rstrip("/") + "/" + component) if root != "/" else "/" + component
        known_roots.add(top)
        try:
            activity = max(
                int(value.get("modified_at") or 0),
                int(value.get("uploaded_at") or 0),
            )
        except (TypeError, ValueError):
            activity = 0
        activities[top] = max(activities.get(top, 0), activity)

    ranked = sorted(
        known_roots,
        key=lambda path: (activities.get(path, 0), path),
        reverse=True,
    )
    cutoff = int((now - _DISCOVERY_HOT_WINDOW).timestamp())
    hot = [path for path in ranked if activities.get(path, 0) >= cutoff]
    selected = list(dict.fromkeys([*hot, *ranked[:_DISCOVERY_HOT_ROOT_LIMIT]]))[
        :_DISCOVERY_HOT_ROOT_LIMIT
    ]
    cold = sorted(known_roots.difference(selected))
    if cold:
        hour_bucket = int(now.timestamp()) // 3600
        start = hour_bucket % len(cold)
        for offset in range(min(_DISCOVERY_COLD_ROOTS_PER_HOUR, len(cold))):
            selected.append(cold[(start + offset) % len(cold)])
    return sorted(known_roots), selected


def _covered_by_listing(path: str, coverage: Mapping[str, Any]) -> bool:
    recursive_roots = coverage.get("recursive_roots")
    direct_roots = coverage.get("direct_roots")
    if isinstance(recursive_roots, list) and any(
        _is_within(path, str(root)) for root in recursive_roots
    ):
        return True
    return isinstance(direct_roots, list) and _parent_path(path) in {
        str(root) for root in direct_roots
    }


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


def _exclusive(scope: str) -> Callable:
    def decorate(method: Callable) -> Callable:
        @functools.wraps(method)
        def locked(
            self: "SubscriptionVideoService",
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            lock_path = self.output_dir / ".locks" / f"{scope}.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                return method(self, *args, **kwargs)

        return locked

    return decorate


_PRIVATE_SCAN_SCRIPT = r"""(() => {
  const dir = __DIRECTORY__;
  const routeFor = dir => '/index?category=all&path=' + encodeURIComponent(dir);
  const currentDir = () => {
    const hash = String(location.hash || '');
    const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
    return new URLSearchParams(query).get('path');
  };
  if (currentDir() !== dir) {
    location.hash = routeFor(dir);
    return {status: 'private_directory_loading', rows: []};
  }
  if (
    location.origin === 'https://pan.baidu.com'
    && location.pathname === '/login'
  ) {
    return {status: 'authentication_required', rows: []};
  }
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== '/disk/main'
  ) {
    return {status: 'wrong_path', rows: []};
  }
  const rows = [...document.querySelectorAll('tr[data-id]')];
  const items = rows.map(row => row.__vue__?._props?.item).filter(Boolean);
  const exact = items.length === rows.length && items.every(item => {
    const path = String(item.path || '');
    const parent = path.slice(0, path.lastIndexOf('/')) || '/';
    return path.startsWith('/') && parent === dir;
  });
  const text = String(document.body?.innerText || '');
  if (rows.length > 0 && exact) {
    if (rows.length >= 100) {
      return {status: 'private_directory_page_bound_exceeded', rows: []};
    }
    return {
      status: 'ok',
      rows: items.map(item => ({
        provider_file_id: String(item.fs_id || ''),
        path: String(item.path || ''),
        name: String(item.server_filename || ''),
        is_dir: item.isdir === 1 || item.isdir === true,
        size: Number(item.size || 0),
        uploaded_at: Number(item.server_ctime || item.local_ctime || 0),
        modified_at: Number(item.server_mtime || item.local_mtime || 0)
      }))
    };
  }
  if (!/正在加载中/.test(text) && /当前列表为空|暂无文件/.test(text)) {
    return {status: 'ok', rows: []};
  }
  return {status: 'private_directory_loading', rows: []};
})()"""

_PRIVATE_RELOAD_SCRIPT = r"""(() => {
  location.reload();
  return {status: 'reload_started'};
})()"""


_PRIVATE_SEARCH_SCRIPT = r"""(async () => {
  const targetName = __TARGET_NAME__;
  const visible = node => {
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const inputs = [...document.querySelectorAll('input')].filter(input => (
    visible(input) && input.placeholder === '搜索我的文件'
  ));
  if (inputs.length !== 1) {
    return {status: 'private_search_input_ambiguous', entries: []};
  }
  const input = inputs[0];
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype, 'value'
  ).set;
  setter.call(input, targetName);
  input.dispatchEvent(new Event('input', {bubbles: true}));
  input.dispatchEvent(new Event('change', {bubbles: true}));
  input.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
  }));
  input.dispatchEvent(new KeyboardEvent('keyup', {
    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
  }));
  const deadline = Date.now() + 15000;
  let stableSignature = '';
  let stablePolls = 0;
  let lastSearchActive = false;
  let lastItemCount = 0;
  let lastSearchValue = '';
  let lastHeadingSeen = false;
  while (Date.now() < deadline) {
    const rows = [...document.querySelectorAll('tr[data-id]')];
    const items = rows.map(row => row.__vue__?._props?.item).filter(Boolean);
    const matches = items.filter(item => (
      String(item.server_filename || '') === targetName
    ));
    const bodyText = String(document.body?.innerText || '');
    const hash = String(location.hash || '');
    const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
    const searchValue = new URLSearchParams(query).get('search') || '';
    const headingSeen = bodyText.includes('搜索：' + targetName);
    const searchActive = searchValue === targetName && headingSeen;
    lastSearchActive = searchActive;
    lastItemCount = items.length;
    lastSearchValue = searchValue;
    lastHeadingSeen = headingSeen;
    const signature = items.map(item => [
      String(item.fs_id || ''),
      String(item.path || ''),
      String(item.server_filename || ''),
      Number(item.size || 0)
    ].join('\u0000')).sort().join('\u0001');
    if (searchActive && signature === stableSignature) {
      stablePolls += 1;
    } else {
      stableSignature = signature;
      stablePolls = 0;
    }
    if (
      searchActive
      && (
        matches.length > 0
        || /无搜索结果|暂无/.test(bodyText)
        || (items.length > 0 && stablePolls >= 5)
      )
    ) {
      return {
        status: 'ok',
        search_settled: true,
        entries: matches.map(item => ({
          provider_file_id: String(item.fs_id || ''),
          path: String(item.path || ''),
          name: String(item.server_filename || ''),
          is_dir: item.isdir === 1 || item.isdir === true,
          size: Number(item.size || 0),
          uploaded_at: Number(
            item.server_ctime || item.local_ctime || 0
          ),
          modified_at: Number(item.server_mtime || item.local_mtime || 0)
        }))
      };
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  return {
    status: 'private_search_timeout',
    entries: [],
    search_active: lastSearchActive,
    search_value: lastSearchValue,
    search_heading_seen: lastHeadingSeen,
    item_count: lastItemCount,
    stable_polls: stablePolls
  };
})()"""


_CREATE_FOLDER_SCRIPT = r"""(async () => {
  const parent = __PARENT__;
  const folderName = __FOLDER_NAME__;
  const currentDir = () => {
    const hash = String(location.hash || '');
    const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
    return new URLSearchParams(query).get('path');
  };
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== '/disk/main'
    || currentDir() !== parent
  ) {
    return {status: 'wrong_destination_parent', triggered: false};
  }
  const visible = node => {
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const existing = [...document.querySelectorAll('tr[data-id]')].filter(row => {
    const item = row.__vue__?._props?.item;
    return item
      && (item.isdir === 1 || item.isdir === true)
      && String(item.server_filename || '') === folderName;
  });
  if (existing.length === 1) {
    return {status: 'already_exists', triggered: false};
  }
  if (existing.length > 1) {
    return {status: 'destination_folder_ambiguous', triggered: false};
  }
  let inputs = [...document.querySelectorAll('input')].filter(input => (
    visible(input)
    && input.closest('.wp-s-pan-list__file-name-edit')
  ));
  if (inputs.length === 0) {
    const controls = [...document.querySelectorAll(
      'button, a, [role="button"]'
    )].filter(node => (
      visible(node)
      && String(node.innerText || node.textContent || '').trim() === '新建文件夹'
    ));
    if (controls.length !== 1) {
      return {status: 'new_folder_control_ambiguous', triggered: false};
    }
    controls[0].click();
  }
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    inputs = [...document.querySelectorAll('input')].filter(input => {
      if (!visible(input)) return false;
      const row = input.closest('tr');
      const semantic = [
        input.placeholder,
        input.getAttribute('aria-label'),
        input.value,
        row?.innerText
      ].join(' ');
      return Boolean(input.closest('.wp-s-pan-list__file-name-edit'))
        || /新建文件夹|文件夹名称|请输入名称/.test(semantic);
    });
    if (inputs.length === 1) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (inputs.length !== 1) {
    return {status: 'new_folder_input_ambiguous', triggered: false};
  }
  const input = inputs[0];
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype, 'value'
  ).set;
  setter.call(input, folderName);
  input.dispatchEvent(new Event('input', {bubbles: true}));
  input.dispatchEvent(new Event('change', {bubbles: true}));
  input.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
  }));
  input.dispatchEvent(new KeyboardEvent('keyup', {
    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
  }));
  return {status: 'folder_create_triggered', triggered: true};
})()"""


_TRANSFER_SCRIPT = r"""(async () => {
  const expectedSharePath = __SHARE_PATH__;
  const sourceParent = __SOURCE_PARENT__;
  const targetName = __TARGET_NAME__;
  const destinationSegments = __DESTINATION_SEGMENTS__;
  if (
    location.origin !== 'https://pan.baidu.com'
    || location.pathname !== expectedSharePath
  ) {
    return {status: 'wrong_share', triggered: false};
  }
  const visible = node => {
    if (!node) return false;
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const selectionControl = row => {
    const semantic = [...row.querySelectorAll('[role="checkbox"]')].filter(
      node => (
        visible(node)
        && ['true', 'false'].includes(node.getAttribute('aria-checked'))
      )
    );
    if (semantic.length === 1) return semantic[0];
    const legacy = row.querySelector('span.EOGexf');
    return legacy ? row : null;
  };
  const rowSelected = row => {
    const control = selectionControl(row);
    if (!control) return null;
    const checked = control.getAttribute('aria-checked');
    if (checked === 'true' || checked === 'false') {
      return checked === 'true';
    }
    return row.classList.contains('JS-item-active');
  };
  location.hash = 'list/path=' + encodeURIComponent(sourceParent);
  const targetDeadline = Date.now() + 10000;
  let targets = [];
  while (Date.now() < targetDeadline) {
    targets = [...document.querySelectorAll('#shareqr dd')].filter(row => {
      const link = row.querySelector('a.filename');
      return link && String(link.getAttribute('title') || '') === targetName;
    });
    if (targets.length === 1) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (targets.length !== 1) {
    return {status: 'transfer_target_not_unique', triggered: false};
  }
  for (const row of [...document.querySelectorAll('#shareqr dd')]) {
    const selected = rowSelected(row);
    if (selected === null) {
      return {status: 'transfer_selection_control_missing', triggered: false};
    }
    if (selected) selectionControl(row).click();
  }
  await new Promise(resolve => setTimeout(resolve, 200));
  const targetSelection = selectionControl(targets[0]);
  if (!targetSelection) {
    return {status: 'transfer_selection_control_missing', triggered: false};
  }
  if (rowSelected(targets[0]) !== true) targetSelection.click();
  await new Promise(resolve => setTimeout(resolve, 200));
  const selectedNames = [...document.querySelectorAll('#shareqr dd')]
    .filter(row => rowSelected(row) === true)
    .map(row => row.querySelector('a.filename'))
    .filter(Boolean)
    .map(link => String(link.getAttribute('title') || ''));
  if (selectedNames.length !== 1 || selectedNames[0] !== targetName) {
    return {status: 'transfer_selection_mismatch', triggered: false};
  }
  const pathControls = [...document.querySelectorAll('.save-path')].filter(
    visible
  );
  if (pathControls.length !== 1) {
    return {status: 'save_path_control_ambiguous', triggered: false};
  }
  pathControls[0].click();
  const dialogDeadline = Date.now() + 10000;
  let dialog = null;
  while (Date.now() < dialogDeadline) {
    const titledDialogs = [...document.querySelectorAll(
      '#share-save-dialog-title'
    )].filter(node => (
      visible(node)
      && String(node.innerText || node.textContent || '')
        .replace(/\s+/g, ' ').trim() === '保存到'
    )).map(node => node.closest('[role="dialog"]')).filter(node => (
      visible(node)
      && node.querySelector('#fileTreeDialog[role="dialog"]')
    ));
    const legacyDialogs = [...document.querySelectorAll(
      '.dialog-fileTreeDialog'
    )].filter(node => (
      visible(node)
      && /保存到|选择保存路径|我的网盘/.test(
        String(node.innerText || node.textContent || '')
      )
    ));
    const candidates = [...new Set([...titledDialogs, ...legacyDialogs])];
    candidates.sort((left, right) => (
      left.getBoundingClientRect().width * left.getBoundingClientRect().height
      - right.getBoundingClientRect().width * right.getBoundingClientRect().height
    ));
    dialog = candidates[0] || null;
    if (dialog) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!dialog) {
    return {status: 'save_dialog_missing', triggered: false};
  }
  const exactCandidates = (container, label) => {
    const nodes = [...container.querySelectorAll('.treeview-txt')].filter(
      node => (
      visible(node)
      && String(node.innerText || node.textContent || '')
        .replace(/\s+/g, ' ').trim() === label
      )
    );
    return nodes;
  };
  for (const segment of destinationSegments) {
    const segmentDeadline = Date.now() + 10000;
    let matches = [];
    while (Date.now() < segmentDeadline) {
      matches = exactCandidates(dialog, segment);
      if (matches.length === 1) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (matches.length !== 1) {
      return {
        status: 'destination_segment_not_unique',
        segment,
        matches: matches.length,
        triggered: false
      };
    }
    const handler = matches[0].closest('.treeview-node-handler');
    if (!handler) {
      return {
        status: 'destination_segment_handler_missing',
        segment,
        triggered: false
      };
    }
    handler.click();
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  const selected = exactCandidates(
    dialog,
    destinationSegments[destinationSegments.length - 1]
  );
  if (
    selected.length !== 1
    || !selected[0].closest('.treeview-node')?.classList.contains(
      'treeview-node-on'
    )
  ) {
    return {status: 'destination_not_selected', triggered: false};
  }
  const confirmLabels = new Set(['确定']);
  const confirms = [...dialog.querySelectorAll(
    'button, a, [role="button"]'
  )].filter(node => (
    visible(node)
    && confirmLabels.has(
      String(node.innerText || node.textContent || '').trim()
    )
  ));
  if (confirms.length !== 1) {
    return {
      status: 'save_confirmation_ambiguous',
      matches: confirms.length,
      triggered: false
    };
  }
  const installNetworkObserver = () => {
    const existing = window.__xiaocaoLvTransferNetwork;
    if (existing && existing.installed === true) return existing;
    const state = {
      installed: true,
      installedAt: Date.now(),
      requestSeen: false,
      responseSeen: false,
      records: []
    };
    const pathOf = value => {
      try {
        return new URL(String(value || ''), location.href).pathname;
      } catch (_) {
        return String(value || '');
      }
    };
    const requestSummary = body => {
      if (body == null) return null;
      let text = '';
      if (typeof body === 'string') text = body;
      else if (body instanceof URLSearchParams) text = body.toString();
      return {
        kind: typeof body,
        length: text.length,
        keys: [...new Set(
          (text.match(/(?:^|&)([^=&]+)/g) || [])
            .map(value => value.replace(/^&/, '').split('=')[0])
            .filter(Boolean)
        )].slice(0, 32)
      };
    };
    const responseSummary = (status, text, error) => {
      const summary = {http_status: Number(status) || 0};
      if (error) summary.response_error = String(error).slice(0, 160);
      if (!text) return summary;
      try {
        const payload = JSON.parse(text);
        for (const key of [
          'errno', 'show_msg', 'error_msg', 'taskid', 'status',
          'task_errno', 'error_code'
        ]) {
          if (payload && Object.prototype.hasOwnProperty.call(payload, key)) {
            const value = payload[key];
            summary[key] = typeof value === 'string'
              ? value.slice(0, 240)
              : value;
          }
        }
      } catch (_) {
        summary.response_parse_error = true;
      }
      return summary;
    };
    const record = (kind, method, url, body, response) => {
      if (pathOf(url) !== '/share/transfer') return;
      state.requestSeen = true;
      const entry = {
        kind,
        method: String(method || 'GET'),
        path: '/share/transfer',
        request: requestSummary(body),
        observedAt: Date.now()
      };
      if (response) {
        Object.assign(entry, response);
        state.responseSeen = Number(response.http_status || 0) > 0;
      }
      state.records.push(entry);
      if (state.records.length > 8) state.records.shift();
    };
    if (typeof window.fetch === 'function') {
      const originalFetch = window.fetch;
      window.fetch = function(input, init) {
        const url = typeof input === 'string' ? input : input?.url;
        const method = init?.method || input?.method || 'GET';
        const body = init?.body || input?.body;
        if (pathOf(url) !== '/share/transfer') {
          return originalFetch.apply(this, arguments);
        }
        state.requestSeen = true;
        return originalFetch.apply(this, arguments).then(response => {
          let clone;
          try { clone = response.clone(); } catch (_) {
            record(
              'fetch', method, url, body,
              responseSummary(response.status, '', 'response_clone_failed')
            );
            return response;
          }
          return clone.text().catch(() => '').then(text => {
            record(
              'fetch', method, url, body,
              responseSummary(response.status, text)
            );
            return response;
          });
        }).catch(error => {
          record(
            'fetch', method, url, body,
            responseSummary(0, '', error)
          );
          throw error;
        });
      };
    }
    if (window.XMLHttpRequest) {
      const originalOpen = XMLHttpRequest.prototype.open;
      const originalSend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function(method, url) {
        this.__xiaocaoLvTransferRequest = {method, url};
        return originalOpen.apply(this, arguments);
      };
      XMLHttpRequest.prototype.send = function(body) {
        const request = this.__xiaocaoLvTransferRequest || {};
        if (pathOf(request.url) !== '/share/transfer') {
          return originalSend.apply(this, arguments);
        }
        state.requestSeen = true;
        let finished = false;
        const finish = error => {
          if (finished) return;
          finished = true;
          let text = '';
          try { text = this.responseText || ''; } catch (_) {}
          record(
            'xhr', request.method, request.url, body,
            responseSummary(this.status, text, error)
          );
        };
        this.addEventListener('loadend', () => finish(), {once: true});
        this.addEventListener('error', () => finish('network_error'), {
          once: true
        });
        this.addEventListener('abort', () => finish('aborted'), {
          once: true
        });
        try {
          return originalSend.apply(this, arguments);
        } catch (error) {
          finish(error);
          throw error;
        }
      };
    }
    window.__xiaocaoLvTransferNetwork = state;
    return state;
  };
  const beforeLines = new Set(
    String(document.body?.innerText || '')
      .split(/\n+/)
      .map(value => value.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
  );
  const network = installNetworkObserver();
  window.__xiaocaoLvTransferConfirmation = {
    beforeLines: [...beforeLines],
    preparedAt: Date.now(),
    network
  };
  confirms[0].setAttribute('data-xiaocao-lv-confirm', 'ready');
  return {
    status: 'save_confirmation_ready',
    confirmation_selector: '[data-xiaocao-lv-confirm="ready"]',
    triggered: false,
    provider_outcome: 'unobserved',
    provider_request_observed: network.requestSeen,
    provider_response_observed: network.responseSeen
  };
})()"""


_TRANSFER_OUTCOME_SCRIPT = r"""(async () => {
  const checkpoint = window.__xiaocaoLvTransferConfirmation || {};
  const network = checkpoint.network
    || window.__xiaocaoLvTransferNetwork
    || {};
  const beforeLines = new Set(checkpoint.beforeLines || []);
  const networkRecords = () => (
    Array.isArray(network.records) ? network.records.slice(-8) : []
  );
  const networkState = () => ({
    provider_request_observed: network.requestSeen === true
      || networkRecords().length > 0,
    provider_response_observed: network.responseSeen === true
      || networkRecords().some(record => (
        Number(record.http_status || 0) > 0
        || record.errno !== undefined
      )),
    provider_network_records: networkRecords()
  });
  const providerResult = () => {
    const records = networkRecords();
    for (const record of records) {
      const httpStatus = Number(record.http_status || 0);
      const errno = record.errno === undefined || record.errno === null
        ? null
        : Number(record.errno);
      const rejected = httpStatus >= 400
        || (Number.isFinite(errno) && errno !== 0);
      const accepted = httpStatus >= 200 && httpStatus < 300
        && (errno === 0 || (errno === null && !record.response_parse_error));
      const details = {
        ...networkState(),
        provider_http_status: httpStatus,
        provider_errno: Number.isFinite(errno) ? errno : undefined,
        provider_message: String(
          record.show_msg || record.error_msg || record.response_error || ''
        ).slice(0, 240),
        provider_task_id: record.taskid === undefined
          ? undefined : String(record.taskid),
        provider_observation: accepted
          ? 'response_accepted' : rejected ? 'response_rejected'
          : 'response_unclassified'
      };
      if (rejected) {
        return {
          status: 'cloud_transfer_rejected',
          triggered: true,
          provider_outcome: 'rejected',
          ...details
        };
      }
      if (accepted) {
        return {
          status: 'cloud_transfer_accepted',
          triggered: true,
          provider_outcome: 'accepted',
          ...details
        };
      }
    }
    return null;
  };
  let providerDomState = '';
  const outcomeDeadline = Date.now() + 10000;
  while (Date.now() < outcomeDeadline) {
    const observed = providerResult();
    if (observed) return observed;
    const newText = String(document.body?.innerText || '')
      .split(/\n+/)
      .map(value => value.replace(/\s+/g, ' ').trim())
      .filter(value => value && !beforeLines.has(value))
      .join('\n');
    if (
      /容量不足|空间不足|转存失败|保存失败|文件过大|已达.{0,8}上限|操作失败|禁止转存/
        .test(newText)
    ) {
      return {
        status: 'cloud_transfer_rejected',
        triggered: true,
        provider_outcome: 'rejected',
        ...networkState(),
        provider_observation: 'dom_rejected'
      };
    }
    if (/保存成功|转存成功|保存完成|已保存到/.test(newText)) {
      providerDomState = 'success_toast_without_provider_response';
    } else if (/正在转存|转存中|文件转存中/.test(newText)) {
      providerDomState = 'transfer_in_progress_without_provider_response';
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  const finalNetwork = networkState();
  const observation = finalNetwork.provider_request_observed
    ? finalNetwork.provider_response_observed
      ? 'response_unclassified' : 'response_unobserved'
    : 'request_unobserved';
  return {
    status: 'cloud_transfer_outcome_unobserved',
    triggered: true,
    provider_outcome: 'unobserved',
    ...finalNetwork,
    provider_observation: observation,
    provider_dom_state: providerDomState
  };
})()"""


_TRANSFER_DIAGNOSTIC_FIELDS = (
    "provider_request_observed",
    "provider_response_observed",
    "provider_network_records",
    "provider_http_status",
    "provider_errno",
    "provider_message",
    "provider_task_id",
    "provider_observation",
    "provider_dom_state",
)


class SubscriptionVideoService:
    """Discover and advance the two authorized Ticket 05 video sources."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        config_path: Path | str = "xiaocao.yaml",
        now: Callable[[], datetime] | None = None,
        runner: Callable[..., Any] = subprocess.run,
        opencli_command: tuple[str, ...] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.manifest_path = self.output_dir / "manifest.json"
        self.events_path = self.output_dir / "events.jsonl"
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self.runner = runner
        self.sleep = sleep
        installed = shutil.which("opencli")
        self.opencli_command = opencli_command or (
            (installed,)
            if installed
            else ("npx", "--yes", "@jackwener/opencli@1.8.6")
        )
        self.lv = LvSubscriptionService.from_config(
            self.output_dir / ".lv-readonly",
            config_path=config_path,
            now=self.now,
            runner=runner,
            opencli_command=self.opencli_command,
        )

    def _time(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise EnrichmentError("subscription video clock needs a timezone")
        return value

    def _runtime_path(self, value: Path | str) -> Path:
        return resolve_repo_owned_path(value, anchor=self.output_dir)

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
            "eval": "browser_eval",
            "open": "browser_open",
            "wait": "browser_wait",
        }.get(operation, "browser_command")
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
            raise EnrichmentDiagnosticError(
                "Ticket 05 browser command timed out",
                category="timeout",
                code="opencli_timeout",
                stage=stage,
            ) from exc
        if result.returncode != 0:
            provider_code = ""
            try:
                error_payload = json.loads(str(result.stdout or ""))
                if isinstance(error_payload, dict):
                    error_value = error_payload.get("error")
                    if isinstance(error_value, dict):
                        provider_code = str(error_value.get("code") or "")
            except (TypeError, json.JSONDecodeError):
                pass
            if provider_code == "cdp_timeout":
                raise EnrichmentDiagnosticError(
                    "Ticket 05 browser evaluation exceeded the OpenCLI CDP deadline",
                    category="timeout",
                    code="opencli_cdp_timeout",
                    stage=stage,
                )
            raise EnrichmentDiagnosticError(
                "Ticket 05 browser command failed",
                category="transport_error",
                code="opencli_command_failed",
                stage=stage,
            )
        try:
            value = json.loads(str(result.stdout))
        except (TypeError, json.JSONDecodeError) as exc:
            raise EnrichmentDiagnosticError(
                "Ticket 05 browser returned invalid JSON",
                category="protocol_error",
                code="opencli_invalid_json",
                stage=stage,
            ) from exc
        if not isinstance(value, dict):
            raise EnrichmentDiagnosticError(
                "Ticket 05 browser returned a non-object",
                category="protocol_error",
                code="opencli_non_object",
                stage=stage,
            )
        return value

    def _scan_private(
        self,
        *,
        session: str,
        profile: str | None,
        root: str,
        recursive: bool,
    ) -> dict[str, Any]:
        self._open_private_directory(
            session=session,
            profile=profile,
            directory=root,
        )
        pending = [root]
        seen: set[str] = set()
        entries: list[dict[str, Any]] = []

        while pending:
            if len(seen) >= 200 or len(entries) >= 10000:
                raise EnrichmentDiagnosticError(
                    "private Netdisk listing exceeded its safety bounds",
                    category="incomplete_scan",
                    code="private_listing_bounds_exceeded",
                    stage="private_listing_validation",
                )
            directory = pending.pop(0)
            if directory in seen:
                continue
            script = _PRIVATE_SCAN_SCRIPT.replace(
                "__DIRECTORY__",
                json.dumps(directory, ensure_ascii=False),
            )
            # Keep each CDP evaluation synchronous and short. Python owns the
            # bounded settlement window so a slow page cannot strand one
            # long-running Promise beyond OpenCLI's command deadline.
            transport_retry_used = False
            payload: dict[str, Any] = {
                "status": "private_directory_loading",
                "rows": [],
            }
            for read_attempt in range(2):
                for poll in range(31):
                    try:
                        payload = self._opencli_json(
                            session,
                            "eval",
                            script,
                            profile=profile,
                            timeout_seconds=(
                                _PRIVATE_DIRECTORY_EVAL_PROCESS_TIMEOUT_SECONDS
                            ),
                        )
                    except EnrichmentDiagnosticError as exc:
                        if (
                            not transport_retry_used
                            and exc.diagnostic_stage == "browser_eval"
                            and exc.diagnostic_code
                            in {"opencli_cdp_timeout", "opencli_timeout"}
                        ):
                            transport_retry_used = True
                            self.sleep(1)
                            continue
                        raise
                    status = str(payload.get("status") or "")
                    if status == "private_directory_loading":
                        if poll < 30:
                            self.sleep(1)
                            continue
                        payload = {
                            "status": "private_directory_load_timeout",
                            "rows": [],
                        }
                    break
                if (
                    payload.get("status")
                    != "private_directory_load_timeout"
                    or read_attempt == 1
                ):
                    break
                reload_result = self._opencli_json(
                    session,
                    "eval",
                    _PRIVATE_RELOAD_SCRIPT,
                    profile=profile,
                    timeout_seconds=30,
                )
                if reload_result.get("status") != "reload_started":
                    raise EnrichmentDiagnosticError(
                        "private Netdisk reload did not start",
                        category="protocol_error",
                        code="opencli_invalid_json",
                        stage="browser_eval",
                    )
                self.sleep(5)
            if payload.get("status") != "ok" or not isinstance(
                payload.get("rows"), list
            ):
                self._raise_private_listing_failure(payload)
            seen.add(directory)
            for item in payload["rows"]:
                if not isinstance(item, dict):
                    raise EnrichmentDiagnosticError(
                        "private Netdisk listing returned invalid metadata",
                        category="incomplete_scan",
                        code="private_listing_incomplete",
                        stage="private_listing_validation",
                    )
                entries.append(item)
                path = str(item.get("path") or "")
                if (
                    recursive
                    and bool(item.get("is_dir"))
                    and path.startswith(root + "/")
                ):
                    pending.append(path)

        return {
            "status": "ok",
            "complete_scan": True,
            "directories_scanned": len(seen),
            "entries": entries,
        }

    def _open_private_directory(
        self,
        *,
        session: str,
        profile: str | None,
        directory: str,
    ) -> None:
        url = (
            "https://pan.baidu.com/disk/main#/index?category=all&path="
            + quote(directory, safe="")
        )
        readback_script = "({status: 'ok', url: location.href})"
        last_timeout: EnrichmentDiagnosticError | None = None
        for attempt in range(2):
            try:
                opened = self._opencli_json(
                    session,
                    "open",
                    url,
                    profile=profile,
                    timeout_seconds=30,
                )
            except EnrichmentDiagnosticError as exc:
                if not (
                    exc.diagnostic_code == "opencli_timeout"
                    and exc.diagnostic_stage == "browser_open"
                ):
                    raise
                last_timeout = exc
            else:
                if _private_directory_url_matches(
                    opened.get("url"), directory
                ):
                    return

            readback = self._opencli_json(
                session,
                "eval",
                readback_script,
                profile=profile,
                timeout_seconds=30,
            )
            readback_url = str(readback.get("url") or "")
            if _private_directory_url_matches(readback_url, directory):
                return
            if urlparse(readback_url).path == "/login":
                raise EnrichmentDiagnosticError(
                    "private Netdisk browser requires authentication",
                    category="authentication",
                    code="authentication_required",
                    stage="private_listing_validation",
                )
            if attempt == 0:
                self.sleep(1)
                continue
            if last_timeout is not None:
                raise last_timeout
            raise EnrichmentDiagnosticError(
                "private Netdisk browser opened the wrong directory",
                category="wrong_target",
                code="private_wrong_directory",
                stage="private_listing_validation",
            )

    @staticmethod
    def _raise_private_listing_failure(payload: Mapping[str, Any]) -> None:
        status = str(payload.get("status") or "")
        if status == "authentication_required":
            raise EnrichmentError("OpenCLI login is required")
        code = {
            "listing_timeout": "private_listing_timeout",
            "private_directory_load_timeout": "private_directory_load_timeout",
            "wrong_origin": "private_wrong_browser_origin",
            "wrong_path": "private_wrong_directory",
            "listing_bounds_exceeded": "private_listing_bounds_exceeded",
            "private_listing_bounds_exceeded": "private_listing_bounds_exceeded",
            "private_directory_page_bound_exceeded": (
                "private_directory_page_bound_exceeded"
            ),
        }.get(status, "private_listing_incomplete")
        raise EnrichmentDiagnosticError(
            "private Netdisk listing is unavailable",
            category=(
                "timeout"
                if status in {
                    "listing_timeout",
                    "private_directory_load_timeout",
                }
                else "incomplete_scan"
            ),
            code=code,
            stage="private_listing_validation",
        )

    @staticmethod
    def _normalize(
        row: dict[str, Any],
        *,
        source: str,
        author: str,
    ) -> dict[str, Any]:
        provider_id = str(row.get("provider_file_id") or "").strip()
        path = str(row.get("path") or "").strip()
        name = str(row.get("name") or "").strip()
        if not provider_id or not path or not name or not path.endswith("/" + name):
            raise EnrichmentError("Ticket 05 source metadata is incomplete")
        try:
            size = int(row.get("size") or 0)
            uploaded_at = int(row.get("uploaded_at") or 0)
            modified_at = int(row.get("modified_at") or 0)
        except (TypeError, ValueError) as exc:
            raise EnrichmentError("Ticket 05 source metadata is invalid") from exc
        is_dir = bool(row.get("is_dir"))
        if (
            size < 0
            or uploaded_at < 0
            or (not is_dir and modified_at <= 0 and uploaded_at <= 0)
        ):
            raise EnrichmentError("Ticket 05 source metadata is invalid")
        provider_hash = _sha256_text(provider_id)
        identity = _sha256_text(f"{source}\n{provider_id}")
        version_key = _sha256_text(
            f"{source}\n{provider_id}\n{path}\n{size}\n{modified_at}"
        )
        suffix = Path(name).suffix.lower()
        normalized = {
            "identity": identity,
            "version_key": version_key,
            "provider_identity_sha256": provider_hash,
            "source": source,
            "author": author,
            "path": path,
            "name": name,
            "is_dir": is_dir,
            "media_type": (
                "directory"
                if is_dir
                else ("video" if suffix in VIDEO_SUFFIXES else "other")
            ),
            "size": size,
            "uploaded_at": uploaded_at,
            "modified_at": modified_at,
        }
        normalized["remote_activity_at"] = _remote_activity_at(normalized)
        explicit_fields = {
            "episode_id": str(row.get("episode_id") or "").strip(),
            "episode_title": str(row.get("episode_title") or "").strip(),
            "part_label": str(row.get("part_label") or "").strip(),
            "part_index": row.get("part_index"),
            "part_count": row.get("part_count"),
        }
        if any(
            value not in {None, ""}
            for value in explicit_fields.values()
        ):
            normalized.update(explicit_fields)
        return normalized

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {
                "schema_version": 1,
                "ticket": "05-subscription-video-to-decisions",
                "cursor": None,
                "items": {},
            }
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("Ticket 05 manifest is invalid") from exc
        if not isinstance(value, dict) or not isinstance(value.get("items"), dict):
            raise EnrichmentError("Ticket 05 manifest is invalid")
        return value

    @staticmethod
    def _remote_time_watermarks(
        manifest: dict[str, Any],
    ) -> tuple[dict[str, int], bool]:
        stored = manifest.get("source_remote_time_watermarks")
        if stored is not None:
            if not isinstance(stored, dict):
                raise EnrichmentError("Ticket 05 remote time watermarks are invalid")
            try:
                watermarks = {
                    source: int(stored[source])
                    for source in (LV_SOURCE, LUCIFER_SOURCE)
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise EnrichmentError(
                    "Ticket 05 remote time watermarks are invalid"
                ) from exc
            if any(value < 0 for value in watermarks.values()):
                raise EnrichmentError("Ticket 05 remote time watermarks are invalid")
            return watermarks, False

        watermarks = {LV_SOURCE: 0, LUCIFER_SOURCE: 0}
        bootstrap = manifest.get("bootstrap")
        selected = (
            bootstrap.get("selected")
            if isinstance(bootstrap, dict)
            and isinstance(bootstrap.get("selected"), list)
            else []
        )
        for row in selected:
            if not isinstance(row, dict):
                continue
            source = str(row.get("source") or "")
            if source not in watermarks:
                continue
            watermarks[source] = max(
                watermarks[source],
                _remote_activity_at(row),
            )
        previous = manifest.get("items")
        if isinstance(previous, dict):
            for row in previous.values():
                if not isinstance(row, dict) or row.get("media_type") != "video":
                    continue
                source = str(row.get("source") or "")
                if source not in watermarks or watermarks[source] > 0:
                    continue
                watermarks[source] = max(
                    watermarks[source],
                    _remote_activity_at(row),
                )
        return watermarks, bool(manifest.get("items"))

    @_exclusive("manifest")
    def migrate_legacy_remote_time_eligibility(self) -> dict[str, Any]:
        """Quarantine pre-fix historical pending rows before browser work."""
        manifest = self._load_manifest()
        watermarks, migration_required = self._remote_time_watermarks(manifest)
        if not migration_required:
            return {
                "event": "subscription_video_remote_time_migration_completed",
                "status": "already_completed",
                "quarantined_count": int(
                    (manifest.get("remote_time_migration") or {}).get(
                        "quarantined_count"
                    )
                    or 0
                ),
                "source_remote_time_watermarks": watermarks,
                "external_side_effects_replayed": False,
            }

        observed_at = self._time().isoformat(timespec="seconds")
        bootstrap = manifest.get("bootstrap")
        selected = (
            bootstrap.get("selected")
            if isinstance(bootstrap, dict)
            and isinstance(bootstrap.get("selected"), list)
            else []
        )
        bootstrap_selected = {
            str(row.get("identity") or "")
            for row in selected
            if isinstance(row, dict)
        }
        items = manifest["items"]
        episodes = (
            manifest.get("episodes")
            if isinstance(manifest.get("episodes"), dict)
            else {}
        )
        quarantined: list[dict[str, Any]] = []
        for episode in episodes.values():
            if (
                not isinstance(episode, dict)
                or episode.get("work_eligible") is not True
                or episode.get("completed_version_key")
                == episode.get("version_key")
                or episode.get("identity") in bootstrap_selected
                or _remote_activity_at(episode)
                > watermarks[str(episode.get("source") or "")]
            ):
                continue
            episode.update(
                {
                    "work_eligible": False,
                    "eligibility_pause_reason": (
                        "historical_remote_time_not_newer_than_bootstrap"
                    ),
                }
            )
            for part in episode.get("parts") or []:
                member = items.get(str(part.get("identity") or ""))
                if isinstance(member, dict):
                    member.update(
                        {
                            "work_eligible": False,
                            "eligibility_pause_reason": episode[
                                "eligibility_pause_reason"
                            ],
                        }
                    )
            quarantined.append(episode)
        for row in items.values():
            if (
                not isinstance(row, dict)
                or row.get("media_type") != "video"
                or row.get("episode_identity")
                or row.get("work_eligible") is not True
                or row.get("completed_version_key") == row.get("version_key")
                or row.get("identity") in bootstrap_selected
                or _remote_activity_at(row)
                > watermarks[str(row.get("source") or "")]
            ):
                continue
            row.update(
                {
                    "work_eligible": False,
                    "eligibility_pause_reason": (
                        "historical_remote_time_not_newer_than_bootstrap"
                    ),
                }
            )
            quarantined.append(row)
        migration = {
            "event": "subscription_video_remote_time_migration_completed",
            "status": "completed",
            "observed_at": observed_at,
            "quarantined_count": len(quarantined),
            "quarantined_versions_sha256": _sha256_text(
                _canonical(
                    sorted(
                        (
                            {
                                "identity": str(row.get("identity") or ""),
                                "version_key": str(row.get("version_key") or ""),
                            }
                            for row in quarantined
                        ),
                        key=lambda row: (row["identity"], row["version_key"]),
                    )
                )
            ),
            "source_remote_time_watermarks": watermarks,
            "external_side_effects_replayed": False,
        }
        manifest.update(
            {
                "source_remote_time_watermarks": watermarks,
                "remote_time_migration": migration,
            }
        )
        _atomic_write_json(self.manifest_path, manifest)
        _append_jsonl(self.events_path, migration)
        return migration

    @staticmethod
    def _migration_source_times(
        value: Mapping[str, Any] | int | None,
        *,
        defaults: Mapping[str, int],
        label: str,
    ) -> dict[str, int]:
        if value is None:
            result = {source: int(defaults[source]) for source in defaults}
        elif isinstance(value, Mapping):
            result = {}
            for source in defaults:
                raw = value.get(source, defaults[source])
                try:
                    result[source] = int(raw)
                except (TypeError, ValueError) as exc:
                    raise EnrichmentError(
                        f"Ticket 05 {label} is invalid"
                    ) from exc
        else:
            try:
                scalar = int(value)
            except (TypeError, ValueError) as exc:
                raise EnrichmentError(f"Ticket 05 {label} is invalid") from exc
            result = {source: scalar for source in defaults}
        if any(value < 0 for value in result.values()):
            raise EnrichmentError(f"Ticket 05 {label} is invalid")
        return result

    @staticmethod
    def _reviewed_version_rows(value: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise EnrichmentError(
                "Ticket 05 historical eligibility review is invalid"
            )
        normalized: dict[tuple[str, str], dict[str, str]] = {}
        for raw in value:
            if not isinstance(raw, Mapping):
                raise EnrichmentError(
                    "Ticket 05 historical eligibility review is invalid"
                )
            identity = str(raw.get("identity") or "").strip()
            version_key = str(raw.get("version_key") or "").strip()
            source = str(raw.get("source") or "").strip()
            if not identity or not version_key:
                raise EnrichmentError(
                    "Ticket 05 historical eligibility review is incomplete"
                )
            key = (identity, version_key)
            prior = normalized.get(key)
            if prior is not None and prior.get("source") != source:
                raise EnrichmentError(
                    "Ticket 05 historical eligibility review is ambiguous"
                )
            normalized[key] = {
                "identity": identity,
                "version_key": version_key,
                "source": source,
            }
        if not normalized:
            raise EnrichmentError(
                "Ticket 05 historical eligibility review is empty"
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
        if _sha256_text(_canonical(current)) != expected_digest:
            return False
        _atomic_write_json(self.manifest_path, manifest)
        return True

    @_exclusive("manifest")
    def retire_historical_versions(
        self,
        reviewed_versions: Sequence[Mapping[str, Any]],
        *,
        cutoff: Mapping[str, Any] | int | None = None,
        source_watermarks: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retire an audited historical set without fabricating completion.

        This is a manifest-only eligibility migration.  It deliberately has a
        compare-and-swap check immediately before the write so an uncooperative
        concurrent writer cannot be overwritten by a historical cleanup.
        Claims, receipts, and completed-version markers are never edited here.
        """

        reviewed = self._reviewed_version_rows(reviewed_versions)
        manifest = self._load_manifest()
        manifest_digest = _sha256_text(_canonical(manifest))
        observed_watermarks, _ = self._remote_time_watermarks(manifest)
        watermarks = self._migration_source_times(
            source_watermarks,
            defaults=observed_watermarks,
            label="source watermarks",
        )
        if watermarks != observed_watermarks:
            return {
                "event": "subscription_video_historical_eligibility_migration",
                "status": "blocked",
                "code": "eligibility_migration_source_watermark_changed",
                "source_watermarks": observed_watermarks,
                "external_business_effects_replayed": False,
            }
        cutoffs = self._migration_source_times(
            cutoff,
            defaults=watermarks,
            label="eligibility cutoff",
        )
        if any(cutoffs[source] > watermarks[source] for source in watermarks):
            raise EnrichmentError(
                "Ticket 05 historical eligibility cutoff exceeds source watermark"
            )

        collections = {"items": manifest["items"]}
        if isinstance(manifest.get("episodes"), dict):
            collections["episodes"] = manifest["episodes"]
        targets: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        for reviewed_row in reviewed:
            found: tuple[str, dict[str, Any]] | None = None
            for collection_name, collection in collections.items():
                candidate = collection.get(reviewed_row["identity"])
                if isinstance(candidate, dict):
                    found = (collection_name, candidate)
                    break
            if found is None:
                raise EnrichmentError(
                    "Ticket 05 reviewed historical version is missing"
                )
            collection_name, row = found
            if row.get("version_key") != reviewed_row["version_key"]:
                raise EnrichmentError(
                    "Ticket 05 reviewed historical version changed"
                )
            row_source = str(row.get("source") or "")
            if reviewed_row["source"] and reviewed_row["source"] != row_source:
                raise EnrichmentError(
                    "Ticket 05 reviewed historical source changed"
                )
            if row_source not in watermarks:
                raise EnrichmentError(
                    "Ticket 05 reviewed historical source is unsupported"
                )
            if _remote_activity_at(row) > cutoffs[row_source]:
                raise EnrichmentError(
                    "Ticket 05 reviewed version is newer than eligibility cutoff"
                )
            targets.append((collection_name, row, reviewed_row))

        migration_id = _sha256_text(
            _canonical(
                {
                    "reviewed_versions": reviewed,
                    "source_watermarks": watermarks,
                    "cutoff": cutoffs,
                }
            )
        )
        prior_migrations = manifest.get("eligibility_migrations")
        if not isinstance(prior_migrations, list):
            prior_migrations = []
        for prior in prior_migrations:
            if isinstance(prior, dict) and prior.get("migration_id") == migration_id:
                return {**prior, "status": "already_completed"}

        # A second read is the CAS boundary.  The lock protects cooperating
        # writers; the digest check also fails closed for a writer that did not
        # use this service's lock.
        current_manifest = self._load_manifest()
        if _sha256_text(_canonical(current_manifest)) != manifest_digest:
            blocked = {
                "event": "subscription_video_historical_eligibility_migration",
                "status": "blocked",
                "code": "eligibility_migration_concurrent_writer",
                "migration_id": migration_id,
                "source_watermarks": watermarks,
                "cutoff": cutoffs,
                "external_business_effects_replayed": False,
            }
            _append_jsonl(self.events_path, blocked)
            return blocked

        retired: list[dict[str, str]] = []
        for collection_name, row, reviewed_row in targets:
            if (
                row.get("work_eligible") is True
                and row.get("completed_version_key") != row.get("version_key")
            ):
                row["work_eligible"] = False
                row["eligibility_pause_reason"] = "historical_backlog_retired"
                retired.append({
                    "collection": collection_name,
                    "identity": reviewed_row["identity"],
                    "version_key": reviewed_row["version_key"],
                })

        reviewed_digest = _sha256_text(_canonical(reviewed))
        retired_digest = _sha256_text(
            _canonical(
                sorted(
                    retired,
                    key=lambda row: (
                        row["identity"],
                        row["version_key"],
                    ),
                )
            )
        )
        migration = {
            "event": "subscription_video_historical_eligibility_migration",
            "status": "completed",
            "migration_id": migration_id,
            "observed_at": self._time().isoformat(timespec="seconds"),
            "source_watermarks": watermarks,
            "cutoff": cutoffs,
            "reviewed_count": len(reviewed),
            "reviewed_versions_sha256": reviewed_digest,
            "retired_count": len(retired),
            "retired_versions_sha256": retired_digest,
            "collection_summary": {
                collection: sum(
                    row["collection"] == collection for row in retired
                )
                for collection in sorted(collections)
            },
            "completed_version_keys_written": 0,
            "claims_and_receipts_preserved": True,
            "external_business_effects_replayed": False,
        }
        manifest["source_remote_time_watermarks"] = watermarks
        manifest["historical_eligibility_migration"] = migration
        manifest["eligibility_migrations"] = [*prior_migrations, migration]
        if not self._write_manifest_if_unchanged(manifest_digest, manifest):
            blocked = {
                "event": "subscription_video_historical_eligibility_migration",
                "status": "blocked",
                "code": "eligibility_migration_concurrent_writer",
                "migration_id": migration_id,
                "source_watermarks": watermarks,
                "cutoff": cutoffs,
                "external_business_effects_replayed": False,
            }
            _append_jsonl(self.events_path, blocked)
            return blocked
        _append_jsonl(self.events_path, migration)
        return migration

    migrate_reviewed_historical_eligibility = retire_historical_versions

    @_exclusive("manifest")
    def observe(
        self,
        lv_entries: list[dict[str, Any]],
        lucifer_entries: list[dict[str, Any]],
        *,
        lv_coverage: Mapping[str, Any] | None = None,
        lucifer_coverage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        observed_at = self._time().isoformat(timespec="seconds")
        normalized = [
            *(
                self._normalize(row, source=LV_SOURCE, author=LV_AUTHOR)
                for row in lv_entries
            ),
            *(
                self._normalize(
                    row,
                    source=LUCIFER_SOURCE,
                    author=LUCIFER_AUTHOR,
                )
                for row in lucifer_entries
            ),
        ]
        if len({row["identity"] for row in normalized}) != len(normalized):
            raise EnrichmentError("Ticket 05 listing has duplicate identities")
        normalized.sort(key=lambda row: (row["source"], row["path"], row["identity"]))
        manifest = self._load_manifest()
        previous = manifest["items"]
        bootstrap = not previous
        source_watermarks, migrate_remote_times = self._remote_time_watermarks(
            manifest
        )
        bootstrap_state = manifest.get("bootstrap")
        selected_rows = (
            bootstrap_state.get("selected")
            if isinstance(bootstrap_state, dict)
            and isinstance(bootstrap_state.get("selected"), list)
            else []
        )
        bootstrap_selected = {
            str(row.get("identity") or "")
            for row in selected_rows
            if isinstance(row, dict)
        }
        coverage_by_source = {
            LV_SOURCE: lv_coverage,
            LUCIFER_SOURCE: lucifer_coverage,
        }
        current: dict[str, dict[str, Any]] = {}
        for identity, row in previous.items():
            if not isinstance(row, dict):
                continue
            coverage = coverage_by_source.get(str(row.get("source") or ""))
            present = row.get("present") is True
            if coverage is None or _covered_by_listing(
                str(row.get("path") or ""), coverage
            ):
                present = False
            current[identity] = {**row, "present": present}
        changed_identities: set[str] = set()
        eligible_changed_identities: set[str] = set()
        for row in normalized:
            prior = previous.get(row["identity"])
            persisted = {
                **row,
                "present": True,
                "last_seen_at": observed_at,
                "first_seen_at": (
                    prior.get("first_seen_at")
                    if isinstance(prior, dict) and prior.get("first_seen_at")
                    else observed_at
                ),
                "version_first_seen_at": (
                    prior.get("version_first_seen_at")
                    if (
                        isinstance(prior, dict)
                        and prior.get("version_key") == row["version_key"]
                        and prior.get("version_first_seen_at")
                    )
                    else observed_at
                ),
            }
            if (
                isinstance(prior, dict)
                and prior.get("version_key") == row["version_key"]
            ):
                for key in (
                    "work_eligible",
                    "completed_version_key",
                    "enrichment_job_id",
                    "decision_result_path",
                    "decision_result_sha256",
                    "completed_episode_version_key",
                    "episode_decision_result_path",
                    "episode_decision_result_sha256",
                    "eligibility_reason",
                    "eligibility_remote_activity_at",
                    "eligibility_watermark_before",
                    "eligibility_pause_reason",
                ):
                    if key in prior:
                        persisted[key] = prior[key]
            else:
                newer_than_watermark = (
                    row["media_type"] == "video"
                    and _remote_activity_at(row)
                    > source_watermarks[row["source"]]
                )
                persisted["work_eligible"] = not bootstrap and newer_than_watermark
                if row["media_type"] == "video":
                    changed_identities.add(row["identity"])
                    if persisted["work_eligible"]:
                        eligible_changed_identities.add(row["identity"])
                        persisted.update(
                            {
                                "eligibility_reason": (
                                    "remote_time_newer_than_watermark"
                                ),
                                "eligibility_remote_activity_at": (
                                    _remote_activity_at(row)
                                ),
                                "eligibility_watermark_before": source_watermarks[
                                    row["source"]
                                ],
                            }
                        )
                        persisted.pop("eligibility_pause_reason", None)
                    else:
                        persisted["eligibility_pause_reason"] = (
                            "remote_time_not_newer_than_watermark"
                        )
            current[row["identity"]] = persisted

        observed_identities = {row["identity"] for row in normalized}
        for source, coverage in coverage_by_source.items():
            if coverage is None:
                continue
            direct_roots = coverage.get("direct_roots")
            if not isinstance(direct_roots, list):
                continue
            removed_directories = [
                row
                for identity, row in previous.items()
                if (
                    isinstance(row, dict)
                    and row.get("source") == source
                    and row.get("is_dir") is True
                    and _parent_path(str(row.get("path") or ""))
                    in {str(root) for root in direct_roots}
                    and identity not in observed_identities
                )
            ]
            for removed in removed_directories:
                removed_path = str(removed.get("path") or "")
                for item in current.values():
                    if (
                        item.get("source") == source
                        and _is_within(str(item.get("path") or ""), removed_path)
                    ):
                        item["present"] = False

        for item in current.values():
            for key in (
                "episode_identity",
                "episode_version_key",
                "episode_part_count",
                "episode_part_index",
                "episode_pause_reason",
            ):
                item.pop(key, None)

        assembled = assemble_video_units(
            [
                row
                for row in current.values()
                if (
                    isinstance(row, dict)
                    and row.get("present") is True
                    and row.get("media_type") == "video"
                )
            ]
        )
        previous_episodes = (
            manifest.get("episodes")
            if isinstance(manifest.get("episodes"), dict)
            else {}
        )
        episodes: dict[str, dict[str, Any]] = {}
        logical_updates: list[dict[str, Any]] = []
        migration_pauses: list[dict[str, Any]] = []
        for unit in assembled["units"]:
            if unit.get("is_episode") is not True:
                if (
                    unit["identity"] in eligible_changed_identities
                    and not bootstrap
                ):
                    logical_updates.append(current[unit["identity"]])
                continue
            prior_episode = previous_episodes.get(unit["identity"])
            same_version = (
                isinstance(prior_episode, dict)
                and prior_episode.get("version_key") == unit["version_key"]
            )
            member_rows = [
                current[str(part["identity"])]
                for part in unit["parts"]
            ]
            migration_conflict = (
                not bootstrap
                and prior_episode is None
                and any(
                    member.get("completed_version_key")
                    == member.get("version_key")
                    for member in member_rows
                )
            )
            changed = any(
                str(part["identity"]) in changed_identities
                for part in unit["parts"]
            )
            eligible = (
                any(
                    str(part["identity"]) in eligible_changed_identities
                    for part in unit["parts"]
                )
                and not migration_conflict
            )
            persisted_episode = {
                **unit,
                "present": True,
                "last_seen_at": observed_at,
                "first_seen_at": (
                    prior_episode.get("first_seen_at")
                    if isinstance(prior_episode, dict)
                    and prior_episode.get("first_seen_at")
                    else unit["first_seen_at"]
                ),
                "version_first_seen_at": (
                    prior_episode.get("version_first_seen_at")
                    if same_version
                    and prior_episode.get("version_first_seen_at")
                    else unit["version_first_seen_at"]
                ),
                "work_eligible": (
                    bool(prior_episode.get("work_eligible"))
                    if same_version
                    else eligible
                ),
            }
            if same_version and prior_episode.get("next_poll_not_before"):
                persisted_episode["next_poll_not_before"] = prior_episode[
                    "next_poll_not_before"
                ]
            elif int(unit.get("settle_seconds") or 0) > 0:
                first_seen = datetime.fromisoformat(
                    str(persisted_episode["version_first_seen_at"])
                )
                persisted_episode["next_poll_not_before"] = (
                    first_seen
                    + timedelta(seconds=int(unit["settle_seconds"]))
                ).isoformat()
            if migration_conflict:
                persisted_episode["work_eligible"] = False
                persisted_episode["pause_reason"] = (
                    "historical_component_receipts_require_reconciliation"
                )
                migration_pauses.append(
                    {
                        "episode_candidate_key": unit["identity"],
                        "reason": persisted_episode["pause_reason"],
                        "source": unit["source"],
                        "author": unit["author"],
                        "paths": [
                            part["path"] for part in unit["parts"]
                        ],
                        "component_identities": [
                            part["identity"] for part in unit["parts"]
                        ],
                    }
                )
            if same_version:
                for key in (
                    "completed_version_key",
                    "enrichment_job_id",
                    "decision_result_path",
                    "decision_result_sha256",
                    "completed_at",
                    "pause_reason",
                    "reconciliation_status",
                    "review_required_path",
                    "review_required_sha256",
                    "superseded_review_only_terminal",
                    "eligibility_reason",
                    "eligibility_remote_activity_at",
                    "eligibility_watermark_before",
                    "eligibility_pause_reason",
                ):
                    if key in prior_episode:
                        persisted_episode[key] = prior_episode[key]
            elif eligible:
                persisted_episode.update(
                    {
                        "work_eligible": True,
                        "eligibility_reason": "remote_time_newer_than_watermark",
                        "eligibility_remote_activity_at": _remote_activity_at(unit),
                        "eligibility_watermark_before": source_watermarks[
                            unit["source"]
                        ],
                    }
                )
                persisted_episode.pop("eligibility_pause_reason", None)
            episodes[unit["identity"]] = persisted_episode
            for part in persisted_episode["parts"]:
                member = current[str(part["identity"])]
                member.update(
                    {
                        "episode_identity": unit["identity"],
                        "episode_version_key": unit["version_key"],
                        "episode_part_count": unit["part_count"],
                        "episode_part_index": part["part_index"],
                        "work_eligible": persisted_episode["work_eligible"],
                    }
                )
                if persisted_episode.get("pause_reason"):
                    member["episode_pause_reason"] = persisted_episode[
                        "pause_reason"
                    ]
            if persisted_episode["work_eligible"] and not same_version:
                logical_updates.append(persisted_episode)

        episode_pauses = [
            *assembled["ambiguities"],
            *migration_pauses,
        ]
        paused_identities: set[str] = set()
        for pause in episode_pauses:
            for identity in pause["component_identities"]:
                member = current.get(str(identity))
                if not isinstance(member, dict):
                    continue
                member["work_eligible"] = False
                member["episode_pause_reason"] = pause["reason"]
                paused_identities.add(str(identity))

        selected: list[dict[str, Any]] = []
        if bootstrap:
            for source in (LV_SOURCE, LUCIFER_SOURCE):
                candidates = [
                    row
                    for row in assembled["units"]
                    if row["source"] == source
                ]
                if not candidates:
                    raise EnrichmentError(
                        f"Ticket 05 has no real video candidate for {source}"
                    )
                selected.append(
                    max(
                        candidates,
                        key=lambda row: (
                            row["modified_at"],
                            row["path"],
                            row["identity"],
                        ),
                    )
                )
            for item in current.values():
                item["work_eligible"] = False
            for episode in episodes.values():
                episode["work_eligible"] = False
            for row in selected:
                if row.get("is_episode") is True:
                    episode = episodes[row["identity"]]
                    episode.update(
                        {
                            "work_eligible": True,
                            "eligibility_reason": "bootstrap_latest_remote_content",
                            "eligibility_remote_activity_at": (
                                _remote_activity_at(row)
                            ),
                            "eligibility_watermark_before": 0,
                        }
                    )
                    for part in episode["parts"]:
                        current[str(part["identity"])].update(
                            {
                                "work_eligible": True,
                                "eligibility_reason": "bootstrap_latest_remote_content",
                                "eligibility_remote_activity_at": (
                                    _remote_activity_at(part)
                                ),
                                "eligibility_watermark_before": 0,
                            }
                        )
                else:
                    current[row["identity"]].update(
                        {
                            "work_eligible": True,
                            "eligibility_reason": "bootstrap_latest_remote_content",
                            "eligibility_remote_activity_at": (
                                _remote_activity_at(row)
                            ),
                            "eligibility_watermark_before": 0,
                        }
                    )
            manifest["bootstrap"] = {
                "policy": "latest_real_logical_content_per_source",
                "completed_at": observed_at,
                "selected": [
                    {
                        "author": row["author"],
                        "identity": row["identity"],
                        "is_episode": row.get("is_episode") is True,
                        "modified_at": row["modified_at"],
                        "uploaded_at": int(row.get("uploaded_at") or 0),
                        "remote_activity_at": _remote_activity_at(row),
                        "part_count": int(row.get("part_count") or 1),
                        "path": row["path"],
                        "size": row["size"],
                        "source": row["source"],
                        "version_key": row["version_key"],
                    }
                    for row in selected
                ],
                "historical_video_baseline_count": sum(
                    row["media_type"] == "video" for row in normalized
                )
                - sum(int(row.get("part_count") or 1) for row in selected),
                "historical_logical_content_baseline_count": (
                    len(assembled["units"]) - len(selected)
                ),
            }
            logical_updates = selected
        else:
            for row in assembled["units"]:
                if (
                    row.get("is_episode") is not True
                    and row["identity"] in changed_identities
                ):
                    continue
                if row.get("is_episode") is True:
                    persisted = episodes[row["identity"]]
                    if (
                        persisted.get("work_eligible") is True
                        and persisted.get("completed_version_key")
                        != persisted.get("version_key")
                        and all(
                            str(part["identity"]) not in paused_identities
                            for part in persisted["parts"]
                        )
                        and not any(
                            update.get("identity") == persisted["identity"]
                            for update in logical_updates
                        )
                    ):
                        logical_updates.append(persisted)

        quarantined: list[dict[str, Any]] = []
        if migrate_remote_times:
            for row in current.values():
                if (
                    not isinstance(row, dict)
                    or row.get("media_type") != "video"
                    or row.get("episode_identity")
                    or row.get("completed_version_key") == row.get("version_key")
                    or row.get("work_eligible") is not True
                    or row.get("identity") in bootstrap_selected
                    or _remote_activity_at(row) > source_watermarks[row["source"]]
                ):
                    continue
                row.update(
                    {
                        "work_eligible": False,
                        "eligibility_pause_reason": (
                            "historical_remote_time_not_newer_than_bootstrap"
                        ),
                    }
                )
                quarantined.append(row)
            for episode in episodes.values():
                if (
                    episode.get("completed_version_key")
                    == episode.get("version_key")
                    or episode.get("work_eligible") is not True
                    or episode.get("identity") in bootstrap_selected
                    or _remote_activity_at(episode)
                    > source_watermarks[episode["source"]]
                ):
                    continue
                episode.update(
                    {
                        "work_eligible": False,
                        "eligibility_pause_reason": (
                            "historical_remote_time_not_newer_than_bootstrap"
                        ),
                    }
                )
                for part in episode.get("parts") or []:
                    member = current.get(str(part.get("identity") or ""))
                    if isinstance(member, dict):
                        member.update(
                            {
                                "work_eligible": False,
                                "eligibility_pause_reason": episode[
                                    "eligibility_pause_reason"
                                ],
                            }
                        )
                quarantined.append(episode)

        observed_watermarks = dict(source_watermarks)
        for row in normalized:
            if row.get("media_type") != "video":
                continue
            observed_watermarks[row["source"]] = max(
                observed_watermarks[row["source"]],
                _remote_activity_at(row),
            )
        present_rows = sorted(
            (
                row
                for row in current.values()
                if isinstance(row, dict) and row.get("present") is True
            ),
            key=lambda row: (row["source"], row["path"], row["identity"]),
        )
        cursor = _sha256_text(
            _canonical(
                [
                    {
                        "identity": row["identity"],
                        "version_key": row["version_key"],
                    }
                    for row in present_rows
                ]
            )
        )
        manifest.update(
            {
                "cursor": cursor,
                "observed_at": observed_at,
                "items": current,
                "episodes": episodes,
                "episode_pauses": episode_pauses,
                "source_remote_time_watermarks": observed_watermarks,
                "source_counts": {
                    source: sum(row["source"] == source for row in present_rows)
                    for source in (LV_SOURCE, LUCIFER_SOURCE)
                },
                "discovery_coverage": {
                    LV_SOURCE: (
                        dict(lv_coverage) if lv_coverage is not None else "complete"
                    ),
                    LUCIFER_SOURCE: (
                        dict(lucifer_coverage)
                        if lucifer_coverage is not None
                        else "complete"
                    ),
                },
            }
        )
        _atomic_write_json(self.manifest_path, manifest)
        logical_updates = [
            row
            for row in logical_updates
            if (
                episodes.get(row["identity"], current.get(row["identity"], {}))
                .get("work_eligible")
                is True
            )
        ]
        pause_digest = _sha256_text(_canonical(episode_pauses))
        if manifest.get("episode_pause_digest") != pause_digest:
            manifest["episode_pause_digest"] = pause_digest
            _atomic_write_json(self.manifest_path, manifest)
            _append_jsonl(
                self.events_path,
                {
                    "event": "subscription_video_episode_pauses_updated",
                    "observed_at": observed_at,
                    "pauses": episode_pauses,
                },
            )
        if migrate_remote_times:
            migration = {
                "event": "subscription_video_remote_time_migration_completed",
                "observed_at": observed_at,
                "quarantined_count": len(quarantined),
                "quarantined_versions_sha256": _sha256_text(
                    _canonical(
                        sorted(
                            (
                                {
                                    "identity": str(row.get("identity") or ""),
                                    "version_key": str(row.get("version_key") or ""),
                                }
                                for row in quarantined
                            ),
                            key=lambda row: (
                                row["identity"],
                                row["version_key"],
                            ),
                        )
                    )
                ),
                "source_remote_time_watermarks": observed_watermarks,
                "external_side_effects_replayed": False,
            }
            manifest["remote_time_migration"] = migration
            _atomic_write_json(self.manifest_path, manifest)
            _append_jsonl(self.events_path, migration)
        if not logical_updates:
            return None
        result = {
            "event": "subscription_videos_discovered",
            "observed_at": observed_at,
            "cursor": cursor,
            "bootstrap": bootstrap,
            "updates": logical_updates,
        }
        _append_jsonl(self.events_path, result)
        return result

    def scan_opencli(
        self,
        *,
        lv_session: str,
        private_session: str,
        profile: str | None,
        episode_spec_path: Path | str | None = None,
        lv_listing: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        self.migrate_legacy_remote_time_eligibility()
        if lv_listing is None:
            lv_listing = self.lv._read_opencli_listing(
                session=lv_session,
                profile=profile,
            )
        if (
            lv_listing.get("status") != "ok"
            or not isinstance(lv_listing.get("entries"), list)
            or (
                lv_listing.get("complete_scan") is not True
                and not isinstance(lv_listing.get("coverage"), Mapping)
            )
        ):
            raise EnrichmentDiagnosticError(
                "shared Lv listing is incomplete",
                category="incomplete_scan",
                code="shared_listing_incomplete",
                stage="listing_validation",
            )
        manifest = self._load_manifest()
        prior_items = manifest.get("items", {})
        has_lucifer_baseline = any(
            isinstance(row, Mapping) and row.get("source") == LUCIFER_SOURCE
            for row in prior_items.values()
        )
        now = self._time()
        full_topology_audit = (
            not has_lucifer_baseline
            or (now.weekday() == 0 and now.hour == 3)
        )
        lucifer_coverage: Mapping[str, Any] | None = None
        if full_topology_audit:
            lucifer_listing = self._scan_private(
                session=private_session,
                profile=profile,
                root=LUCIFER_ROOT,
                recursive=True,
            )
        else:
            root_listing = self._scan_private(
                session=private_session,
                profile=profile,
                root=LUCIFER_ROOT,
                recursive=False,
            )
            known_roots, planned_roots = _tiered_discovery_roots(
                prior_items,
                source=LUCIFER_SOURCE,
                root=LUCIFER_ROOT,
                now=now,
            )
            root_directories = sorted(
                {
                    str(row.get("path") or "")
                    for row in root_listing["entries"]
                    if isinstance(row, Mapping) and row.get("is_dir") is True
                }
            )
            new_roots = [path for path in root_directories if path not in known_roots]
            selected_roots = list(
                dict.fromkeys([*new_roots[:2], *planned_roots])
            )[:4]
            lucifer_entries = list(root_listing["entries"])
            for selected_root in selected_roots:
                listing = self._scan_private(
                    session=private_session,
                    profile=profile,
                    root=selected_root,
                    recursive=True,
                )
                lucifer_entries.extend(listing["entries"])
            lucifer_listing = {
                "status": "ok",
                "complete_scan": False,
                "entries": lucifer_entries,
            }
            lucifer_coverage = {
                "direct_roots": [LUCIFER_ROOT],
                "recursive_roots": selected_roots,
                "policy": "hourly_hot_roots_plus_rotating_cold_shard",
            }
        lv_entries = lv_listing["entries"]
        lucifer_entries = lucifer_listing["entries"]
        if episode_spec_path is not None:
            lv_entries, lucifer_entries = self._apply_episode_spec(
                lv_entries,
                lucifer_entries,
                episode_spec_path=episode_spec_path,
            )
        return self.observe(
            lv_entries,
            lucifer_entries,
            lv_coverage=(
                lv_listing.get("coverage")
                if lv_listing.get("complete_scan") is not True
                else None
            ),
            lucifer_coverage=lucifer_coverage,
        )

    @staticmethod
    def _apply_episode_spec(
        lv_entries: list[dict[str, Any]],
        lucifer_entries: list[dict[str, Any]],
        *,
        episode_spec_path: Path | str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        spec_path = Path(episode_spec_path).expanduser().resolve()
        try:
            if (
                spec_path.suffix.lower() != ".json"
                or spec_path.stat().st_size > MAX_EPISODE_SPEC_BYTES
            ):
                raise EnrichmentError(
                    "Ticket 05 episode spec must be a small JSON file"
                )
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise EnrichmentError("Ticket 05 episode spec is missing") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("Ticket 05 episode spec is invalid") from exc
        episodes = spec.get("episodes") if isinstance(spec, dict) else None
        if not isinstance(episodes, list):
            raise EnrichmentError("Ticket 05 episode spec is incomplete")
        by_source = {
            LV_SOURCE: [{**row} for row in lv_entries],
            LUCIFER_SOURCE: [{**row} for row in lucifer_entries],
        }
        indexed = {
            source: {
                str(row.get("path") or ""): row
                for row in rows
            }
            for source, rows in by_source.items()
        }
        claimed_paths: set[tuple[str, str]] = set()
        for episode in episodes:
            if not isinstance(episode, dict):
                raise EnrichmentError("Ticket 05 episode spec is invalid")
            source = str(episode.get("source") or "")
            episode_id = str(episode.get("episode_id") or "").strip()
            title = str(episode.get("title") or "").strip()
            parts = episode.get("parts")
            if (
                source not in by_source
                or not episode_id
                or not title
                or not isinstance(parts, list)
                or len(parts) < 2
            ):
                raise EnrichmentError("Ticket 05 episode spec is incomplete")
            expected_count = len(parts)
            indexes = []
            for part in parts:
                if not isinstance(part, dict):
                    raise EnrichmentError("Ticket 05 episode spec is invalid")
                path = str(part.get("path") or "").strip()
                try:
                    part_index = int(part.get("index"))
                except (TypeError, ValueError) as exc:
                    raise EnrichmentError(
                        "Ticket 05 episode spec part order is invalid"
                    ) from exc
                target = indexed[source].get(path)
                key = (source, path)
                if (
                    target is None
                    or key in claimed_paths
                    or part_index <= 0
                    or Path(str(target.get("name") or "")).suffix.lower()
                    not in VIDEO_SUFFIXES
                ):
                    raise EnrichmentError(
                        "Ticket 05 episode spec does not match one source video"
                    )
                claimed_paths.add(key)
                indexes.append(part_index)
                target.update(
                    {
                        "episode_id": episode_id,
                        "episode_title": title,
                        "part_index": part_index,
                        "part_count": expected_count,
                        "part_label": str(
                            part.get("label") or part_index
                        ),
                    }
                )
            if set(indexes) != set(range(1, expected_count + 1)):
                raise EnrichmentError(
                    "Ticket 05 episode spec parts must be contiguous and unique"
                )
        return by_source[LV_SOURCE], by_source[LUCIFER_SOURCE]

    def pending_items(self) -> list[dict[str, Any]]:
        manifest = self._load_manifest()
        rows = [
            row
            for row in (
                manifest.get("episodes", {})
                if isinstance(manifest.get("episodes"), dict)
                else {}
            ).values()
            if (
                isinstance(row, dict)
                and row.get("present") is True
                and row.get("work_eligible") is True
                and row.get("completed_version_key") != row.get("version_key")
            )
        ]
        rows.extend([
            row
            for row in manifest["items"].values()
            if (
                isinstance(row, dict)
                and row.get("present") is True
                and row.get("media_type") == "video"
                and not row.get("episode_identity")
                and not row.get("episode_pause_reason")
                and row.get("work_eligible") is True
                and row.get("completed_version_key") != row.get("version_key")
            )
        ])
        rows.sort(
            key=lambda row: (
                row["version_first_seen_at"],
                row["source"],
                row["path"],
            )
        )
        return rows

    def status(self) -> dict[str, Any]:
        return {**self._load_manifest(), "pending": self.pending_items()}

    def record_item_failure(
        self,
        item: dict[str, Any],
        *,
        failure: dict[str, str],
        retryable: bool,
    ) -> dict[str, Any]:
        """Audit one isolated item failure without replaying its claims."""
        manifest = self._load_manifest()
        collection_name = (
            "episodes" if item.get("is_episode") is True else "items"
        )
        collection = manifest.get(collection_name)
        persisted = (
            collection.get(str(item.get("identity") or ""))
            if isinstance(collection, dict)
            else None
        )
        if (
            not isinstance(persisted, dict)
            or persisted.get("version_key") != item.get("version_key")
        ):
            raise EnrichmentError(
                "Ticket 05 isolated failure changed source version"
            )
        claim_status = "missing"
        if item.get("source") == LV_SOURCE:
            claim_path = self._claim_path(f"lv_transfer_{item['version_key']}")
            if claim_path.is_file():
                try:
                    claim = json.loads(claim_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    claim_status = "invalid"
                else:
                    claim_status = str(claim.get("status") or "unknown")
        else:
            enrichment_events = (
                self.output_dir
                / "enrichment"
                / str(item["version_key"])
                / "events.jsonl"
            )
            if enrichment_events.is_file():
                try:
                    rows = [
                        json.loads(line)
                        for line in enrichment_events.read_text(
                            encoding="utf-8"
                        ).splitlines()
                        if line.strip()
                    ]
                except (OSError, json.JSONDecodeError):
                    claim_status = "invalid"
                else:
                    claim_status = str(
                        (rows[-1] if rows else {}).get("status") or "missing"
                    )
        row = {
            "schema_version": 1,
            "event": "subscription_video_item_failure_isolated",
            "identity": str(item["identity"]),
            "version_key": str(item["version_key"]),
            "name": str(item.get("name") or item.get("episode_title") or ""),
            "source": str(item["source"]),
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
        _append_jsonl(self.events_path, row)
        return row

    @staticmethod
    def _read_small_json(
        path: Path | str,
        *,
        label: str,
        max_bytes: int = MAX_EPISODE_REVIEW_SPEC_BYTES,
    ) -> tuple[Path, dict[str, Any]]:
        source = Path(path).expanduser().resolve()
        try:
            if (
                source.suffix.lower() != ".json"
                or source.stat().st_size > max_bytes
            ):
                raise EnrichmentError(f"{label} must be a small JSON file")
            value = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise EnrichmentError(f"{label} is missing") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError(f"{label} is invalid") from exc
        if not isinstance(value, dict):
            raise EnrichmentError(f"{label} must be a JSON object")
        return source, value

    @staticmethod
    def _legacy_episode(
        manifest: dict[str, Any],
        episode_identity: str,
    ) -> dict[str, Any]:
        episodes = manifest.get("episodes")
        episode = (
            episodes.get(episode_identity)
            if isinstance(episodes, dict)
            else None
        )
        if (
            not isinstance(episode, dict)
            or episode.get("is_episode") is not True
            or len(episode.get("parts") or []) < 2
        ):
            raise EnrichmentError(
                "Ticket 05 logical episode does not exist"
            )
        if (
            episode.get("completed_version_key") != episode.get("version_key")
            and episode.get("pause_reason")
            not in {
                "historical_component_receipts_require_reconciliation",
                "useful_aggregate_insight_requires_user_review",
            }
        ):
            raise EnrichmentError(
                "Ticket 05 episode is not a legacy reconciliation"
            )
        return episode

    @_exclusive("manifest")
    def prepare_legacy_episode_review(
        self,
        episode_identity: str,
        *,
        component_evidence_path: Path | str,
    ) -> dict[str, Any]:
        """Bind reviewed component transcripts and assemble one episode.

        This is a local, read-only reconciliation of historical small-document
        evidence.  It never opens or hashes the source videos and never invokes
        a household or Book KOL-US side effect.
        """

        manifest = self._load_manifest()
        episode = self._legacy_episode(manifest, episode_identity)
        spec_path, spec = self._read_small_json(
            component_evidence_path,
            label="Ticket 05 component evidence spec",
        )
        if (
            spec.get("episode_identity") != episode["identity"]
            or spec.get("episode_version_key") != episode["version_key"]
        ):
            raise EnrichmentError(
                "Ticket 05 component evidence changed episode identity"
            )
        components = spec.get("components")
        if not isinstance(components, list):
            raise EnrichmentError(
                "Ticket 05 component evidence list is missing"
            )
        expected_parts = sorted(
            episode["parts"],
            key=lambda row: int(row["part_index"]),
        )
        indexed = {
            (
                str(row.get("source_identity") or ""),
                str(row.get("version_identity") or ""),
                int(row.get("part_index") or 0),
            ): row
            for row in components
            if isinstance(row, dict)
        }
        if len(indexed) != len(components) or len(indexed) != len(expected_parts):
            raise EnrichmentError(
                "Ticket 05 component evidence is incomplete or duplicated"
            )
        component_states = []
        for part in expected_parts:
            key = (
                str(part["identity"]),
                str(part["version_key"]),
                int(part["part_index"]),
            )
            component = indexed.get(key)
            if not isinstance(component, dict):
                raise EnrichmentError(
                    "Ticket 05 component evidence changed source parts"
                )
            if (
                str(component.get("source_path") or "") != part["path"]
                or int(component.get("source_size") or 0) != int(part["size"])
            ):
                raise EnrichmentError(
                    "Ticket 05 component evidence changed source metadata"
                )
            transcript_path = Path(
                str(component.get("transcript_path") or "")
            ).expanduser().resolve()
            transcript_sha256 = str(
                component.get("transcript_sha256") or ""
            ).lower()
            try:
                acceptable_transcript = (
                    transcript_path.suffix.lower()
                    in EPISODE_TRANSCRIPT_SUFFIXES
                    and transcript_path.is_file()
                    and 0 < transcript_path.stat().st_size
                    <= MAX_EPISODE_TRANSCRIPT_BYTES
                )
            except OSError:
                acceptable_transcript = False
            if (
                not acceptable_transcript
                or not _SHA256.fullmatch(transcript_sha256)
                or _sha256_file(transcript_path) != transcript_sha256
            ):
                raise EnrichmentError(
                    "Ticket 05 component transcript is missing or changed"
                )
            component_states.append(
                {
                    "status": "verified",
                    "job_id": (
                        "legacy-component-"
                        + str(part["version_key"])[:16]
                    ),
                    "part_index": int(part["part_index"]),
                    "transcript_path": str(transcript_path),
                    "transcript_sha256": transcript_sha256,
                    "netdisk_directory": str(
                        PurePosixPath(str(part["path"])).parent
                    ),
                    "large_payload_local_bytes": 0,
                    "coordinator_source_video_bytes": 0,
                }
            )

        artifact_dir = self.output_dir / "artifacts" / episode["version_key"]
        preparation_path = artifact_dir / "legacy_episode_review_preparation.json"
        spec_sha256 = _sha256_file(spec_path)
        if preparation_path.is_file():
            prior = json.loads(preparation_path.read_text(encoding="utf-8"))
            if (
                prior.get("episode_identity") != episode["identity"]
                or prior.get("episode_version_key") != episode["version_key"]
                or prior.get("component_evidence_spec_sha256") != spec_sha256
            ):
                raise EnrichmentError(
                    "Ticket 05 legacy episode preparation changed"
                )
            request_path = Path(str(prior["analysis_request_path"]))
            if (
                not request_path.is_file()
                or _sha256_file(request_path)
                != prior.get("analysis_request_sha256")
            ):
                raise EnrichmentError(
                    "Ticket 05 legacy episode analysis request changed"
                )
            return json.loads(request_path.read_text(encoding="utf-8"))

        state = self._prepare_episode_evidence(episode, component_states)
        request = self._analysis_request(episode, state)
        request_path = Path(str(request["analysis_request_path"]))
        preparation = {
            "schema_version": 1,
            "event": "subscription_video_legacy_episode_review_prepared",
            "status": "prepared",
            "episode_identity": episode["identity"],
            "episode_version_key": episode["version_key"],
            "component_evidence_spec_path": str(spec_path),
            "component_evidence_spec_sha256": spec_sha256,
            "episode_evidence_path": state["episode_evidence_path"],
            "episode_evidence_sha256": state["episode_evidence_sha256"],
            "merged_evidence_path": state["transcript_path"],
            "merged_evidence_sha256": state["transcript_sha256"],
            "analysis_request_path": str(request_path),
            "analysis_request_sha256": _sha256_file(request_path),
            "part_count": len(expected_parts),
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
            "prepared_at": self._time().isoformat(timespec="seconds"),
        }
        _atomic_write_json(preparation_path, preparation)
        _append_jsonl(self.events_path, preparation)
        return request

    def _historical_episode_receipts(
        self,
        *,
        author: str,
        component_evidence: list[dict[str, Any]],
        decision_output_dir: Path | str,
    ) -> list[dict[str, Any]]:
        output_dir = Path(decision_output_dir).expanduser().resolve()
        outbox = self._read_jsonl(output_dir / "household_outbox.jsonl")
        events = self._read_jsonl(output_dir / "events.jsonl")
        paper_rows = self._read_jsonl(
            output_dir / "book_kol_us" / "decisions.jsonl"
        )
        delivered = {
            str(row.get("idempotency_key") or ""): row
            for row in events
            if (
                row.get("event") == "notification_delivered"
                and row.get("status") == "delivered"
                and str(row.get("receipt") or "").strip()
            )
        }
        receipts = []
        for component in component_evidence:
            evidence_sha256 = str(component["transcript_sha256"])
            household = next(
                (
                    row
                    for row in reversed(outbox)
                    if (
                        row.get("author") == author
                        and row.get("evidence_sha256") == evidence_sha256
                        and str(row.get("idempotency_key") or "") in delivered
                    )
                ),
                None,
            )
            book = next(
                (
                    row
                    for row in reversed(paper_rows)
                    if (
                        row.get("book") == "KOL-US"
                        and row.get("paper_only") is True
                        and row.get("status") in {"filled", "no_trade"}
                        and (
                            row.get("idempotency_key") == evidence_sha256
                            or (
                                row.get("evidence_context") or {}
                            ).get("evidence_sha256")
                            == evidence_sha256
                        )
                    )
                ),
                None,
            )
            receipts.append(
                {
                    "part_index": component["part_index"],
                    "source_identity": component["identity"],
                    "version_identity": component["version_key"],
                    "evidence_sha256": evidence_sha256,
                    "household": (
                        {
                            "status": "delivered",
                            "idempotency_key": household["idempotency_key"],
                            "receipt": delivered[
                                str(household["idempotency_key"])
                            ]["receipt"],
                        }
                        if isinstance(household, dict)
                        else {"status": "not_previously_delivered"}
                    ),
                    "book_kol_us": (
                        {
                            "status": book["status"],
                            "idempotency_key": str(
                                book.get("idempotency_key") or ""
                            ),
                        }
                        if isinstance(book, dict)
                        else {"status": "not_previously_recorded"}
                    ),
                }
            )
        if not any(
            row["household"]["status"] == "delivered"
            or row["book_kol_us"]["status"] in {"filled", "no_trade"}
            for row in receipts
        ):
            raise EnrichmentError(
                "Ticket 05 legacy episode has no historical receipts"
            )
        return receipts

    @_exclusive("manifest")
    def reconcile_legacy_episode_review(
        self,
        episode_identity: str,
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
    ) -> dict[str, Any]:
        """Reconcile a legacy episode without hiding new aggregate insight.

        Historical component receipts are evidence against blind replay, not
        evidence that a complete episode has nothing useful to say.  A useful
        aggregate result therefore stops at an explicit user-review gate.  It
        may later use the normal ``decide_item`` path to create one new,
        aggregate-scoped household and Book terminal after approval.
        """

        manifest = self._load_manifest()
        episode = self._legacy_episode(manifest, episode_identity)
        bundle_file = Path(bundle_path).expanduser().resolve()
        if not bundle_file.is_file():
            raise EnrichmentError(
                "Ticket 05 legacy episode decision bundle is missing"
            )
        bundle_sha256 = _sha256_file(bundle_file)
        receipt_name = (
            "legacy_episode_reconciliation_"
            + str(episode["version_key"])
        )
        receipt_path = self._receipt_path(receipt_name)
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (
                receipt.get("episode_identity") != episode["identity"]
                or receipt.get("episode_version_key") != episode["version_key"]
            ):
                raise EnrichmentError(
                    "Ticket 05 legacy episode receipt changed"
                )
            result_path = Path(
                str(receipt.get("decision_result_path") or "")
            ).expanduser().resolve()
            result_sha256 = str(
                receipt.get("decision_result_sha256") or ""
            )
            if (
                not result_path.is_file()
                or not _SHA256.fullmatch(result_sha256)
                or _sha256_file(result_path) != result_sha256
            ):
                raise EnrichmentError(
                    "Ticket 05 legacy episode result changed"
                )
            prior_result = json.loads(
                result_path.read_text(encoding="utf-8")
            )
            if (
                prior_result.get("decision_bundle_sha256")
                == bundle_sha256
            ):
                episode.update(
                    {
                        "completed_version_key": episode["version_key"],
                        "work_eligible": False,
                        "reconciliation_status": "completed_review_only",
                        "decision_result_path": str(result_path),
                        "decision_result_sha256": result_sha256,
                        "completed_at": receipt["reconciled_at"],
                    }
                )
                episode.pop("pause_reason", None)
                for part in episode["parts"]:
                    member = manifest["items"].get(str(part["identity"]))
                    if not isinstance(member, dict):
                        raise EnrichmentError(
                            "Ticket 05 legacy episode component disappeared"
                        )
                    member.update(
                        {
                            "completed_episode_version_key": episode[
                                "version_key"
                            ],
                            "episode_decision_result_path": str(result_path),
                            "episode_decision_result_sha256": result_sha256,
                            "work_eligible": False,
                        }
                    )
                    member.pop("episode_pause_reason", None)
                manifest["episode_pauses"] = [
                    row
                    for row in manifest.get("episode_pauses", [])
                    if row.get("episode_candidate_key")
                    != episode["identity"]
                ]
                _atomic_write_json(self.manifest_path, manifest)
                return receipt
            receipt_name += f"_revision_{bundle_sha256[:16]}"
            receipt_path = self._receipt_path(receipt_name)

        preparation_path = (
            self.output_dir
            / "artifacts"
            / episode["version_key"]
            / "legacy_episode_review_preparation.json"
        )
        if not preparation_path.is_file():
            raise EnrichmentError(
                "Ticket 05 legacy episode review is not prepared"
            )
        preparation = json.loads(
            preparation_path.read_text(encoding="utf-8")
        )
        enrichment_dir = self.output_dir / "enrichment" / episode["version_key"]
        state = NetdiskEnrichmentService(
            enrichment_dir,
            runner=self.runner,
            now=self.now,
            opencli_command=self.opencli_command,
            netdisk_directory=str(
                PurePosixPath(str(episode["path"])).parent
            ),
        ).status()
        decision = self._validate_analysis_bundle(
            episode,
            state,
            bundle_path=bundle_path,
        )
        historical_receipts = self._historical_episode_receipts(
            author=episode["author"],
            component_evidence=state["component_evidence"],
            decision_output_dir=decision_output_dir,
        )
        decision_dir = Path(decision_output_dir).expanduser().resolve()
        watched_paths = (
            decision_dir / "household_outbox.jsonl",
            decision_dir / "events.jsonl",
            decision_dir / "book_kol_us" / "decisions.jsonl",
        )
        before = {
            str(path): _sha256_file(path)
            for path in watched_paths
            if path.is_file()
        }
        insight = decision.get("reader_insight") or {}
        has_relayable_aggregate_insight = (
            decision["decision_status"] == "actionable_signal"
            or insight.get("status") == "useful"
        )
        if has_relayable_aggregate_insight:
            artifact_dir = (
                self.output_dir / "artifacts" / episode["version_key"]
            )
            review_path = artifact_dir / (
                "legacy_episode_review_required."
                f"{bundle_sha256[:16]}.json"
            )
            if review_path.is_file():
                review = json.loads(review_path.read_text(encoding="utf-8"))
                if (
                    review.get("episode_identity") != episode["identity"]
                    or review.get("episode_version_key")
                    != episode["version_key"]
                    or review.get("decision_bundle_sha256")
                    != bundle_sha256
                ):
                    raise EnrichmentError(
                        "Ticket 05 legacy episode review gate changed"
                    )
            else:
                review = {
                    "schema_version": 1,
                    "ticket": "05-subscription-video-to-decisions",
                    "event": (
                        "subscription_video_legacy_episode_review_required"
                    ),
                    "status": "awaiting_user_review",
                    "episode_identity": episode["identity"],
                    "episode_version_key": episode["version_key"],
                    "part_count": episode["part_count"],
                    "evidence_path": state["transcript_path"],
                    "evidence_sha256": state["transcript_sha256"],
                    "component_evidence": state["component_evidence"],
                    "decision_bundle_path": str(bundle_file),
                    "decision_bundle_sha256": bundle_sha256,
                    "decision_status": decision["decision_status"],
                    "household_notification": {
                        "status": "review_required",
                        "reason": (
                            "the complete aggregate contains accurately "
                            "relayable insight that was not covered by the "
                            "historical component receipts"
                        ),
                        "proposed_title": reader_message_title(decision),
                        "proposed_message": render_household_item_message(
                            decision
                        ),
                    },
                    "book_kol_us_proposal": decision["book_kol_us"],
                    "historical_component_receipts": historical_receipts,
                    "watched_external_ledgers_unchanged": True,
                    "new_external_side_effect_count": 0,
                    "large_payload_local_bytes": 0,
                    "coordinator_source_video_bytes": 0,
                    "review_requested_at": self._time().isoformat(
                        timespec="seconds"
                    ),
                }
                _atomic_write_json(review_path, review)
                _append_jsonl(self.events_path, review)
            review_sha256 = _sha256_file(review_path)
            prior_result_path = str(
                episode.get("decision_result_path") or ""
            )
            prior_result_sha256 = str(
                episode.get("decision_result_sha256") or ""
            )
            if prior_result_path and prior_result_sha256:
                episode["superseded_review_only_terminal"] = {
                    "decision_result_path": prior_result_path,
                    "decision_result_sha256": prior_result_sha256,
                    "reason": "aggregate insight omitted or factually wrong",
                }
            for field in (
                "completed_version_key",
                "completed_at",
                "decision_result_path",
                "decision_result_sha256",
            ):
                episode.pop(field, None)
            episode.update(
                {
                    "work_eligible": False,
                    "reconciliation_status": "awaiting_user_review",
                    "pause_reason": (
                        "useful_aggregate_insight_requires_user_review"
                    ),
                    "review_required_path": str(review_path),
                    "review_required_sha256": review_sha256,
                }
            )
            for part in episode["parts"]:
                member = manifest["items"].get(str(part["identity"]))
                if not isinstance(member, dict):
                    raise EnrichmentError(
                        "Ticket 05 legacy episode component disappeared"
                    )
                for field in (
                    "completed_episode_version_key",
                    "episode_decision_result_path",
                    "episode_decision_result_sha256",
                ):
                    member.pop(field, None)
                member.update(
                    {
                        "work_eligible": False,
                        "episode_pause_reason": (
                            "useful_aggregate_insight_requires_user_review"
                        ),
                    }
                )
            _atomic_write_json(self.manifest_path, manifest)
            after = {
                str(path): _sha256_file(path)
                for path in watched_paths
                if path.is_file()
            }
            if before != after:
                raise EnrichmentError(
                    "Ticket 05 review gate changed external ledgers"
                )
            return {
                **review,
                "review_required_path": str(review_path),
                "review_required_sha256": review_sha256,
            }

        claim = self._write_claim(
            receipt_name,
            {
                "episode_identity": episode["identity"],
                "episode_version_key": episode["version_key"],
                "evidence_sha256": state["transcript_sha256"],
                "decision_bundle_sha256": bundle_sha256,
                "historical_receipt_count": len(historical_receipts),
                "external_side_effects_authorized": False,
                "large_payload_local_bytes": 0,
                "coordinator_source_video_bytes": 0,
            },
        )
        household_key = _sha256_text(
            f"{episode['identity']}\n{episode['version_key']}\n"
            "legacy-review-suppressed"
        )
        book = decision["book_kol_us"]
        if book.get("decision") != "no_trade":
            raise EnrichmentError(
                "Ticket 05 legacy review cannot create a new paper action"
            )
        book_key = _sha256_text(
            f"{episode['identity']}\n{episode['version_key']}\n"
            "legacy-review-book-no-trade"
        )
        household_terminal = {
            "status": "suppressed",
            "reason": (
                "historical component receipts exist; the complete aggregate "
                "is exposed for explicit user review and no consolidated "
                "WeChat replay is authorized"
            ),
            "idempotency_key": household_key,
        }
        book_terminal = {
            "book": "KOL-US",
            "paper_only": True,
            "status": "no_trade",
            "reason": str(book["reason"]),
            "idempotency_key": book_key,
        }
        artifact_dir = self.output_dir / "artifacts" / episode["version_key"]
        result_path = artifact_dir / "legacy_episode_review_result.json"
        result = {
            "schema_version": 1,
            "ticket": "05-subscription-video-to-decisions",
            "event": "subscription_video_legacy_episode_review_completed",
            "status": "decided",
            "job_id": str(state["job_id"]),
            "episode_identity": episode["identity"],
            "episode_version_key": episode["version_key"],
            "title": decision["title"],
            "source": episode["source"],
            "author": episode["author"],
            "evidence_path": state["transcript_path"],
            "evidence_sha256": state["transcript_sha256"],
            "component_evidence": state["component_evidence"],
            "decision_bundle_path": str(bundle_file),
            "decision_bundle_sha256": bundle_sha256,
            "decision_status": decision["decision_status"],
            "knowledge_status": decision["knowledge_status"],
            "coverage_rows": sorted(REQUIRED_COVERAGE_ROWS),
            "market_first": True,
            "household_notification": household_terminal,
            "book_kol_us": book_terminal,
            "historical_component_receipts": historical_receipts,
            "new_external_side_effect_count": 0,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
            "user_review_status": "pending",
            "completed_at": self._time().isoformat(timespec="seconds"),
        }
        _atomic_write_json(result_path, result)
        result_sha256 = _sha256_file(result_path)
        after = {
            str(path): _sha256_file(path)
            for path in watched_paths
            if path.is_file()
        }
        if before != after:
            raise EnrichmentError(
                "Ticket 05 legacy reconciliation changed external ledgers"
            )
        receipt = {
            "schema_version": 1,
            "event": "subscription_video_legacy_episode_reconciled",
            "status": "completed",
            "claim_id": claim["claim_id"],
            "episode_identity": episode["identity"],
            "episode_version_key": episode["version_key"],
            "part_count": episode["part_count"],
            "component_evidence": state["component_evidence"],
            "episode_evidence_path": preparation["episode_evidence_path"],
            "episode_evidence_sha256": preparation[
                "episode_evidence_sha256"
            ],
            "merged_evidence_path": state["transcript_path"],
            "merged_evidence_sha256": state["transcript_sha256"],
            "decision_result_path": str(result_path),
            "decision_result_sha256": result_sha256,
            "household_notification": household_terminal,
            "book_kol_us": book_terminal,
            "historical_component_receipts": historical_receipts,
            "watched_external_ledgers_unchanged": True,
            "new_external_side_effect_count": 0,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
            "reconciled_at": self._time().isoformat(timespec="seconds"),
        }
        _atomic_write_json(receipt_path, receipt)
        _append_jsonl(self.events_path, receipt)

        episode.update(
            {
                "completed_version_key": episode["version_key"],
                "work_eligible": False,
                "reconciliation_status": "completed_review_only",
                "decision_result_path": str(result_path),
                "decision_result_sha256": result_sha256,
                "completed_at": receipt["reconciled_at"],
            }
        )
        episode.pop("pause_reason", None)
        for part in episode["parts"]:
            member = manifest["items"].get(str(part["identity"]))
            if not isinstance(member, dict):
                raise EnrichmentError(
                    "Ticket 05 legacy episode component disappeared"
                )
            member.update(
                {
                    "completed_episode_version_key": episode["version_key"],
                    "episode_decision_result_path": str(result_path),
                    "episode_decision_result_sha256": result_sha256,
                    "work_eligible": False,
                }
            )
            member.pop("episode_pause_reason", None)
        manifest["episode_pauses"] = [
            row
            for row in manifest.get("episode_pauses", [])
            if row.get("episode_candidate_key") != episode["identity"]
        ]
        _atomic_write_json(self.manifest_path, manifest)
        return receipt

    def _claim_path(self, name: str) -> Path:
        return self.output_dir / "claims" / f"{name}.json"

    def _receipt_path(self, name: str) -> Path:
        return self.output_dir / "receipts" / f"{name}.json"

    def _write_claim(
        self,
        name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        path = self._claim_path(name)
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise EnrichmentError("Ticket 05 claim is invalid")
            return value
        now = self._time().isoformat(timespec="microseconds")
        claim = {
            "schema_version": 1,
            "event": f"{name}_claimed",
            "status": "claimed",
            "claim_id": _sha256_text(f"{name}\n{now}\n{_canonical(payload)}"),
            "claimed_at": now,
            **payload,
        }
        _atomic_write_json(path, claim)
        _append_jsonl(self.events_path, claim)
        return claim

    def _record_pretrigger_failure(
        self,
        name: str,
        claim: dict[str, Any],
        reason: str,
    ) -> None:
        failed = {
            **claim,
            "status": "failed_pretrigger",
            "reason": str(reason),
            "failed_at": self._time().isoformat(timespec="seconds"),
        }
        _atomic_write_json(self._claim_path(name), failed)
        _append_jsonl(
            self.events_path,
            {
                **failed,
                "event": f"{name}_failed_pretrigger",
            },
        )

    def _record_transfer_blocker(
        self,
        receipt_name: str,
        claim: dict[str, Any],
        *,
        blocker_key: str,
        failure_reason: str,
        reconciliation_status: str,
    ) -> dict[str, Any]:
        if (
            claim.get("status") == "blocked"
            and claim.get("blocker_key") == blocker_key
        ):
            return claim
        blocked = {
            **claim,
            "event": "lv_cloud_transfer_blocked",
            "status": "blocked",
            "stage": "cloud_transfer_confirmation",
            "pending": False,
            "side_effect_uncertain": False,
            "user_action_required": True,
            "blocker_key": blocker_key,
            "failure_reason": failure_reason,
            "reconciliation_status": reconciliation_status,
            "blocked_at": self._time().isoformat(timespec="seconds"),
        }
        _atomic_write_json(self._claim_path(receipt_name), blocked)
        _append_jsonl(self.events_path, blocked)
        return blocked

    def record_lv_transfer_absence_reconciliation(
        self,
        item: dict[str, Any],
        *,
        claim_id: str,
        readback_evidence_sha256: str,
    ) -> dict[str, Any]:
        receipt_name = f"lv_transfer_{item['version_key']}"
        claim_path = self._claim_path(receipt_name)
        if not claim_path.is_file():
            raise EnrichmentError(
                "Lv cloud transfer absence reconciliation requires its claim"
            )
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EnrichmentError(
                "Lv cloud transfer claim is invalid"
            ) from exc
        if (
            claim.get("claim_id") != claim_id
            or claim.get("source_identity") != item["identity"]
            or claim.get("source_version_key") != item["version_key"]
            or claim.get("provider_outcome") != "unobserved"
        ):
            raise EnrichmentError(
                "Lv cloud transfer absence reconciliation changed binding"
            )
        if (
            claim.get("status") == "reconciled_absent"
            and claim.get("readback_evidence_sha256")
            == readback_evidence_sha256
        ):
            return claim
        reconciled = {
            **claim,
            "event": "lv_cloud_transfer_absence_reconciled",
            "status": "reconciled_absent",
            "stage": "cloud_transfer_reconciliation",
            "pending": True,
            "side_effect_uncertain": False,
            "reconciliation_status": "exact_private_copy_absent",
            "readback_evidence_sha256": readback_evidence_sha256,
            "reconciled_absent_at": self._time().isoformat(
                timespec="seconds"
            ),
            "trigger_attempt_maximum": max(
                LV_TRANSFER_MAX_TRIGGER_ATTEMPTS,
                int(claim.get("trigger_attempt") or 1) + 1,
            ),
        }
        _atomic_write_json(claim_path, reconciled)
        _append_jsonl(self.events_path, reconciled)
        return reconciled

    def _direct_private_entries(
        self,
        *,
        session: str,
        profile: str | None,
        directory: str,
    ) -> list[dict[str, Any]]:
        return self._scan_private(
            session=session,
            profile=profile,
            root=directory,
            recursive=False,
        )["entries"]

    def _search_private_exact(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> list[dict[str, Any]]:
        self._opencli_json(
            session,
            "open",
            "https://pan.baidu.com/disk/main#/index?category=all&path=%2F",
            profile=profile,
            timeout_seconds=30,
        )
        script = _PRIVATE_SEARCH_SCRIPT.replace(
            "__TARGET_NAME__",
            json.dumps(target_name, ensure_ascii=False),
        )
        payload = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=30,
        )
        if (
            payload.get("status") != "ok"
            or payload.get("search_settled") is not True
            or not isinstance(payload.get("entries"), list)
        ):
            raise EnrichmentError(
                "private Netdisk search failed: "
                f"{payload.get('status')} "
                f"(active={payload.get('search_active')}, "
                f"heading={payload.get('search_heading_seen')}, "
                f"items={payload.get('item_count')}, "
                f"stable_polls={payload.get('stable_polls')})"
            )
        return payload["entries"]

    def ensure_lv_destination(
        self,
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        receipt_path = self._receipt_path("lv_destination_folder")
        rows = self._direct_private_entries(
            session=session,
            profile=profile,
            directory=LV_DESTINATION_PARENT,
        )
        matches = [
            row
            for row in rows
            if (
                row.get("is_dir")
                and row.get("path") == LV_DESTINATION_DIRECTORY
                and row.get("name") == Path(LV_DESTINATION_DIRECTORY).name
            )
        ]
        if len(matches) > 1:
            raise EnrichmentError("Lv destination folder is ambiguous")
        if len(matches) == 1:
            receipt = {
                "schema_version": 1,
                "event": "lv_destination_folder_ready",
                "status": "completed",
                "path": LV_DESTINATION_DIRECTORY,
                "provider_identity_sha256": _sha256_text(
                    str(matches[0]["provider_file_id"])
                ),
                "completed_at": self._time().isoformat(timespec="seconds"),
            }
            if not receipt_path.is_file():
                _atomic_write_json(receipt_path, receipt)
                _append_jsonl(self.events_path, receipt)
            return receipt
        claim = self._write_claim(
            "lv_destination_folder",
            {
                "parent": LV_DESTINATION_PARENT,
                "path": LV_DESTINATION_DIRECTORY,
            },
        )
        if claim.get("triggered_at"):
            return {**claim, "pending": True, "side_effect_uncertain": True}
        if claim.get("status") == "failed_pretrigger":
            self._claim_path("lv_destination_folder").unlink()
            claim = self._write_claim(
                "lv_destination_folder",
                {
                    "parent": LV_DESTINATION_PARENT,
                    "path": LV_DESTINATION_DIRECTORY,
                    "retry_of": claim["claim_id"],
                },
            )
        script = (
            _CREATE_FOLDER_SCRIPT.replace(
                "__PARENT__",
                json.dumps(LV_DESTINATION_PARENT, ensure_ascii=False),
            ).replace(
                "__FOLDER_NAME__",
                json.dumps(Path(LV_DESTINATION_DIRECTORY).name, ensure_ascii=False),
            )
        )
        result = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=30,
        )
        if result.get("status") == "already_exists":
            return self.ensure_lv_destination(session=session, profile=profile)
        if result.get("triggered") is not True:
            self._record_pretrigger_failure(
                "lv_destination_folder",
                claim,
                str(result.get("status") or "folder_create_failed"),
            )
            raise EnrichmentError(
                f"Lv destination folder was not created: {result.get('status')}"
            )
        triggered = {
            **claim,
            "status": "triggered",
            "triggered_at": self._time().isoformat(timespec="microseconds"),
        }
        _atomic_write_json(self._claim_path("lv_destination_folder"), triggered)
        _append_jsonl(
            self.events_path,
            {**triggered, "event": "lv_destination_folder_triggered"},
        )
        for _attempt in range(10):
            self.sleep(0.5)
            ready = self.ensure_lv_destination(session=session, profile=profile)
            if ready.get("status") == "completed":
                return ready
        return {**triggered, "pending": True, "side_effect_uncertain": True}

    def transfer_lv_video(
        self,
        item: dict[str, Any],
        *,
        lv_session: str,
        private_session: str,
        profile: str | None,
        readback_only: bool = False,
        observability_repair_revision: str | None = None,
    ) -> dict[str, Any]:
        if item.get("source") != LV_SOURCE or item.get("author") != LV_AUTHOR:
            raise EnrichmentError("cloud transfer accepts only Lv Xiaotong items")
        if not readback_only:
            destination = self.ensure_lv_destination(
                session=private_session,
                profile=profile,
            )
            if destination.get("status") != "completed":
                return {**destination, "pending": True}
        target_path = f"{LV_DESTINATION_DIRECTORY}/{item['name']}"
        receipt_name = f"lv_transfer_{item['version_key']}"
        receipt_path = self._receipt_path(receipt_name)
        if receipt_path.is_file():
            try:
                prior_receipt = json.loads(
                    receipt_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError as exc:
                raise EnrichmentError(
                    "Lv cloud transfer receipt is invalid"
                ) from exc
            if (
                prior_receipt.get("status") != "completed"
                or prior_receipt.get("source_identity") != item["identity"]
                or prior_receipt.get("source_version_key")
                != item["version_key"]
                or int(prior_receipt.get("target_size") or 0)
                != int(item["size"])
                or prior_receipt.get("large_payload_local_bytes") != 0
            ):
                raise EnrichmentError(
                    "Lv cloud transfer receipt conflicts with source"
                )
            return {**prior_receipt, "idempotent_replay": True}
        target_rows = self._direct_private_entries(
            session=private_session,
            profile=profile,
            directory=LV_DESTINATION_DIRECTORY,
        )
        matches = [
            row
            for row in target_rows
            if row.get("path") == target_path and row.get("name") == item["name"]
        ]
        if len(matches) > 1:
            raise EnrichmentError("transferred Lv target is ambiguous")
        if len(matches) == 1:
            target = self._normalize(
                matches[0],
                source=LV_SOURCE,
                author=LV_AUTHOR,
            )
            if target["size"] != item["size"]:
                raise EnrichmentError("transferred Lv target size does not match source")
            receipt = {
                "schema_version": 1,
                "event": "lv_cloud_transfer_completed",
                "status": "completed",
                "source_identity": item["identity"],
                "source_version_key": item["version_key"],
                "target_path": target_path,
                "target_provider_identity_sha256": target[
                    "provider_identity_sha256"
                ],
                "target_size": target["size"],
                "target_modified_at": target["modified_at"],
                "large_payload_local_bytes": 0,
                "completed_at": self._time().isoformat(timespec="seconds"),
            }
            if not receipt_path.is_file():
                _atomic_write_json(receipt_path, receipt)
                _append_jsonl(self.events_path, receipt)
            return receipt
        if readback_only:
            claim_path = self._claim_path(receipt_name)
            if not claim_path.is_file():
                raise EnrichmentError(
                    "Lv cloud transfer readback requires its exact claim"
                )
            try:
                claim = json.loads(claim_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise EnrichmentError(
                    "Lv cloud transfer claim is invalid"
                ) from exc
            if (
                claim.get("source_identity") != item["identity"]
                or claim.get("source_version_key") != item["version_key"]
            ):
                raise EnrichmentError(
                    "Lv cloud transfer claim conflicts with source"
                )
        else:
            claim = self._write_claim(
                receipt_name,
                {
                    "source_identity": item["identity"],
                    "source_version_key": item["version_key"],
                    "source_path": item["path"],
                    "source_size": item["size"],
                    "target_path": target_path,
                    "large_payload_local_bytes": 0,
                },
            )
        reconciled_absent = False
        if claim.get("triggered_at") or (
            claim.get("status") == "failed_pretrigger"
            and claim.get("reason") == "save_dialog_missing"
        ):
            exact_matches = [
                row
                for row in self._search_private_exact(
                    session=private_session,
                    profile=profile,
                    target_name=item["name"],
                )
                if (
                    row.get("name") == item["name"]
                    and int(row.get("size") or 0) == int(item["size"])
                )
            ]
            if len(exact_matches) > 1:
                raise EnrichmentError(
                    "unexpected-path Lv cloud transfer is ambiguous"
                )
            if len(exact_matches) == 1:
                target = self._normalize(
                    exact_matches[0],
                    source=LV_SOURCE,
                    author=LV_AUTHOR,
                )
                reconciled = {
                    "schema_version": 1,
                    "event": "lv_cloud_transfer_completed",
                    "status": "completed",
                    "source_identity": item["identity"],
                    "source_version_key": item["version_key"],
                    "target_path": target["path"],
                    "intended_target_path": target_path,
                    "target_provider_identity_sha256": target[
                        "provider_identity_sha256"
                    ],
                    "target_size": target["size"],
                    "target_modified_at": target["modified_at"],
                    "large_payload_local_bytes": 0,
                    "reconciled_default_root_save": (
                        target["path"] == f"/{item['name']}"
                    ),
                    "reconciled_unexpected_path_save": (
                        target["path"] != target_path
                    ),
                    "completed_at": self._time().isoformat(
                        timespec="seconds"
                    ),
                }
                _atomic_write_json(receipt_path, reconciled)
                _append_jsonl(self.events_path, reconciled)
                return reconciled
            reconciled_absent = True
        if claim.get("triggered_at"):
            try:
                triggered_at = datetime.fromisoformat(
                    str(claim["triggered_at"])
                )
            except (TypeError, ValueError) as exc:
                raise EnrichmentError(
                    "Lv cloud transfer claim has invalid triggered_at"
                ) from exc
            now = self._time()
            retry_not_before = (
                triggered_at + LV_TRANSFER_CONFIRMATION_WINDOW
            )
            trigger_attempt = int(claim.get("trigger_attempt") or 1)
            trigger_attempt_maximum = max(
                trigger_attempt,
                int(
                    claim.get("trigger_attempt_maximum")
                    or LV_TRANSFER_MAX_TRIGGER_ATTEMPTS
                ),
            )
            if claim.get("provider_trigger_status") == "cloud_transfer_rejected":
                self._record_transfer_blocker(
                    receipt_name,
                    claim,
                    blocker_key="lv-cloud-transfer-provider-rejected",
                    failure_reason=(
                        "provider rejected the confirmed cloud transfer"
                    ),
                    reconciliation_status="provider_rejected",
                )
                raise EnrichmentError(
                    "Lv cloud transfer was rejected by provider"
                )
            if (
                not readback_only
                and claim.get("provider_outcome") == "unobserved"
                and claim.get("status")
                in {"native_click_claimed", "native_click_uncertain"}
            ):
                raise EnrichmentError(
                    "Lv cloud transfer native click outcome is uncertain"
                )
            if now < retry_not_before:
                waiting = {
                    **claim,
                    "status": "waiting_cloud_transfer_receipt",
                    "stage": "cloud_transfer_confirmation",
                    "pending": True,
                    "side_effect_uncertain": True,
                    "trigger_attempt": trigger_attempt,
                    "trigger_attempt_maximum": trigger_attempt_maximum,
                    "next_poll_not_before": retry_not_before.isoformat(
                        timespec="seconds"
                    ),
                    "reconciliation_status": (
                        "exact_private_copy_absent"
                        if reconciled_absent
                        else "pending_exact_reconciliation"
                    ),
                }
                if not readback_only:
                    _atomic_write_json(self._claim_path(receipt_name), waiting)
                return waiting
            if not reconciled_absent:
                return {
                    **claim,
                    "status": "waiting_cloud_transfer_reconciliation",
                    "stage": "cloud_transfer_confirmation",
                    "pending": True,
                    "side_effect_uncertain": True,
                    "trigger_attempt": trigger_attempt,
                }
            if readback_only:
                return {
                    **claim,
                    "status": "waiting_cloud_transfer_receipt",
                    "stage": "cloud_transfer_confirmation",
                    "pending": True,
                    "side_effect_uncertain": True,
                    "trigger_attempt": trigger_attempt,
                    "trigger_attempt_maximum": trigger_attempt_maximum,
                    "reconciliation_status": "exact_private_copy_absent",
                }
            legacy_observability_gap = (
                trigger_attempt >= LV_TRANSFER_MAX_TRIGGER_ATTEMPTS
                and claim.get("provider_outcome") == "unobserved"
                and "provider_request_observed" not in claim
                and "provider_response_observed" not in claim
            )
            observability_recovery = False
            if trigger_attempt >= trigger_attempt_maximum:
                if legacy_observability_gap:
                    if observability_repair_revision is None:
                        raise EnrichmentDiagnosticError(
                            "legacy Lv transfer attempts lack provider response evidence",
                            category="provider_contract_error",
                            code="lv_transfer_response_unobserved_legacy",
                            stage="cloud_transfer_confirmation",
                        )
                    if not re.fullmatch(
                        r"[0-9a-f]{40}", observability_repair_revision
                    ):
                        raise EnrichmentError(
                            "Lv transfer observability repair revision is invalid"
                        )
                    observability_recovery = True
                else:
                    self._record_transfer_blocker(
                        receipt_name,
                        claim,
                        blocker_key="lv-cloud-transfer-not-materialized",
                        failure_reason=(
                            "two confirmed transfer attempts produced no exact "
                            "private copy"
                        ),
                        reconciliation_status=(
                            "exact_private_copy_absent_after_bounded_retry"
                        ),
                    )
                    raise EnrichmentError(
                        "Lv cloud transfer did not materialize after bounded "
                        "exact reconciliation"
                    )
            retry_claimed_at = now.isoformat(timespec="microseconds")
            retry_claim = {
                **claim,
                "event": (
                    "lv_cloud_transfer_observability_recovery_claimed"
                    if observability_recovery
                    else "lv_cloud_transfer_recovery_claimed"
                ),
                "status": "claimed",
                "claim_id": _sha256_text(
                    f"{receipt_name}\n{retry_claimed_at}\n"
                    f"{claim['claim_id']}\n{trigger_attempt + 1}"
                ),
                "claimed_at": retry_claimed_at,
                "retry_of": claim["claim_id"],
                "trigger_attempt": trigger_attempt + 1,
                "trigger_attempt_maximum": (
                    trigger_attempt + 1
                    if observability_recovery
                    else trigger_attempt_maximum
                ),
                "prior_triggered_at": claim["triggered_at"],
                "reconciled_absent_at": now.isoformat(timespec="seconds"),
                "reconciliation_basis": (
                    "intended_directory_and_settled_private_exact_search"
                ),
                **(
                    {
                        "observability_repair_revision": (
                            observability_repair_revision
                        ),
                        "recovery_reason": (
                            "legacy_attempts_predated_provider_response_observer"
                        ),
                    }
                    if observability_recovery
                    else {}
                ),
            }
            for field in (
                "triggered_at",
                "next_poll_not_before",
                "reconciliation_status",
                "side_effect_uncertain",
                "pending",
                "provider_outcome",
                "provider_trigger_status",
                "readback_evidence_sha256",
                "blocked_at",
                "blocker_key",
                "failure_reason",
                "user_action_required",
                *_TRANSFER_DIAGNOSTIC_FIELDS,
            ):
                retry_claim.pop(field, None)
            _atomic_write_json(
                self._claim_path(receipt_name),
                retry_claim,
            )
            _append_jsonl(self.events_path, retry_claim)
            claim = retry_claim
        if claim.get("status") == "failed_pretrigger":
            self._claim_path(receipt_name).unlink()
            claim = self._write_claim(
                receipt_name,
                {
                    "source_identity": item["identity"],
                    "source_version_key": item["version_key"],
                    "source_path": item["path"],
                    "source_size": item["size"],
                    "target_path": target_path,
                    "large_payload_local_bytes": 0,
                    "retry_of": claim["claim_id"],
                },
            )
        self._opencli_json(
            lv_session,
            "open",
            self.lv.share_url,
            profile=profile,
            timeout_seconds=30,
        )
        source_parent = str(PurePosixPath(str(item["path"])).parent)
        transfer_script = (
            _TRANSFER_SCRIPT.replace(
                "__SHARE_PATH__",
                json.dumps(urlparse(self.lv.share_url).path),
            )
            .replace(
                "__SOURCE_PARENT__",
                json.dumps(source_parent, ensure_ascii=False),
            )
            .replace(
                "__TARGET_NAME__",
                json.dumps(item["name"], ensure_ascii=False),
            )
            .replace(
                "__DESTINATION_SEGMENTS__",
                json.dumps(["课程", "自己的课", "吕晓彤"], ensure_ascii=False),
            )
        )
        result = self._opencli_json(
            lv_session,
            "eval",
            transfer_script,
            profile=profile,
            timeout_seconds=60,
        )
        if result.get("status") == "transfer_target_not_unique":
            # The share UI can finish the hash navigation after the first
            # bounded read expires.  This status is pre-trigger and carries
            # no provider effect, so reopen the same bound share once before
            # classifying the source item as failed.
            self._opencli_json(
                lv_session,
                "open",
                self.lv.share_url,
                profile=profile,
                timeout_seconds=30,
            )
            result = self._opencli_json(
                lv_session,
                "eval",
                transfer_script,
                profile=profile,
                timeout_seconds=60,
            )
        action_claim = claim
        if result.get("status") == "save_confirmation_ready":
            selector = str(result.get("confirmation_selector") or "")
            expected_selector = (
                '[data-xiaocao-lv-confirm="ready"]'
            )
            if selector != expected_selector:
                self._record_pretrigger_failure(
                    receipt_name,
                    claim,
                    "save_confirmation_selector_invalid",
                )
                raise EnrichmentError(
                    "Lv cloud transfer confirmation selector is invalid"
                )
            action_claim = {
                **claim,
                "status": "native_click_claimed",
                "stage": "cloud_transfer_confirmation",
                "trigger_attempt": int(
                    claim.get("trigger_attempt") or 1
                ),
                "provider_trigger_status": "native_click_claimed",
                "provider_outcome": "unobserved",
                "native_click_selector": selector,
                "triggered_at": self._time().isoformat(
                    timespec="microseconds"
                ),
            }
            _atomic_write_json(
                self._claim_path(receipt_name),
                action_claim,
            )
            _append_jsonl(
                self.events_path,
                {
                    **action_claim,
                    "event": "lv_cloud_transfer_native_click_claimed",
                },
            )
            click_result = self._opencli_json(
                lv_session,
                "click",
                selector,
                profile=profile,
                timeout_seconds=30,
            )
            if (
                click_result.get("clicked") is not True
                or click_result.get("matches_n") != 1
            ):
                _append_jsonl(
                    self.events_path,
                    {
                        **action_claim,
                        "event": (
                            "lv_cloud_transfer_native_click_uncertain"
                        ),
                    },
                )
                raise EnrichmentError(
                    "Lv cloud transfer native click outcome is uncertain"
                )
            result = self._opencli_json(
                lv_session,
                "eval",
                _TRANSFER_OUTCOME_SCRIPT,
                profile=profile,
                timeout_seconds=30,
            )
        if result.get("triggered") is not True:
            self._record_pretrigger_failure(
                receipt_name,
                claim,
                str(result.get("status") or "cloud_transfer_failed"),
            )
            raise EnrichmentError(
                f"Lv cloud transfer was not triggered: {result.get('status')}"
            )
        triggered = {
            **action_claim,
            "status": "triggered",
            "trigger_attempt": int(
                action_claim.get("trigger_attempt") or 1
            ),
            "provider_trigger_status": str(
                result.get("status") or "cloud_transfer_triggered"
            ),
            "provider_outcome": str(
                result.get("provider_outcome") or "unobserved"
            ),
            "triggered_at": str(
                action_claim.get("triggered_at")
                or self._time().isoformat(timespec="microseconds")
            ),
        }
        for field in _TRANSFER_DIAGNOSTIC_FIELDS:
            if field in result:
                triggered[field] = result[field]
        _atomic_write_json(self._claim_path(receipt_name), triggered)
        _append_jsonl(
            self.events_path,
            {**triggered, "event": "lv_cloud_transfer_triggered"},
        )
        for _attempt in range(12):
            self.sleep(5)
            ready = self.transfer_lv_video(
                item,
                lv_session=lv_session,
                private_session=private_session,
                profile=profile,
                observability_repair_revision=(
                    observability_repair_revision
                ),
            )
            if ready.get("status") == "completed":
                return ready
            if ready.get("next_poll_not_before"):
                return ready
        return {
            **triggered,
            "status": "waiting_cloud_transfer_receipt",
            "stage": "cloud_transfer_confirmation",
            "pending": True,
            "side_effect_uncertain": True,
            "trigger_attempt_maximum": int(
                triggered.get("trigger_attempt_maximum")
                or LV_TRANSFER_MAX_TRIGGER_ATTEMPTS
            ),
        }

    def _enrichment_service(
        self,
        item: dict[str, Any],
        *,
        netdisk_path: str,
    ) -> NetdiskEnrichmentService:
        directory = str(PurePosixPath(netdisk_path).parent)
        return NetdiskEnrichmentService(
            self.output_dir / "enrichment" / item["version_key"],
            runner=self.runner,
            now=self.now,
            opencli_command=self.opencli_command,
            netdisk_directory=directory,
        )

    def _prepare_episode_evidence(
        self,
        item: dict[str, Any],
        component_states: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if item.get("is_episode") is not True or len(item.get("parts") or []) < 2:
            raise EnrichmentError(
                "Ticket 05 logical episode requires multiple source parts"
            )
        parts = sorted(
            item["parts"],
            key=lambda part: int(part["part_index"]),
        )
        if len(parts) != len(component_states):
            raise EnrichmentError(
                "Ticket 05 logical episode component evidence is incomplete"
            )
        states_by_order = {
            int(state.get("part_index") or index): state
            for index, state in enumerate(component_states, start=1)
        }
        artifact_dir = self.output_dir / "artifacts" / item["version_key"]
        artifact_dir.mkdir(parents=True, exist_ok=True)
        merged_path = artifact_dir / f"{item['episode_title']}.txt"
        component_evidence = []
        sections = []
        netdisk_directories: set[str] = set()
        for part in parts:
            part_index = int(part["part_index"])
            state = states_by_order.get(part_index)
            if not isinstance(state, dict):
                raise EnrichmentError(
                    "Ticket 05 logical episode component order is incomplete"
                )
            transcript_path = Path(
                str(state.get("transcript_path") or "")
            ).expanduser().resolve()
            transcript_sha256 = str(
                state.get("transcript_sha256") or ""
            ).lower()
            if (
                state.get("status") not in {"verified", "decided"}
                or int(state.get("large_payload_local_bytes") or 0) != 0
                or not transcript_path.is_file()
                or not _SHA256.fullmatch(transcript_sha256)
                or _sha256_file(transcript_path) != transcript_sha256
            ):
                raise EnrichmentError(
                    "Ticket 05 logical episode component is not verified"
                )
            netdisk_directory = str(
                state.get("netdisk_directory")
                or PurePosixPath(str(part["path"])).parent
            )
            netdisk_directories.add(netdisk_directory)
            component = {
                "identity": part["identity"],
                "version_key": part["version_key"],
                "part_index": part_index,
                "part_label": part["part_label"],
                "source_path": part["path"],
                "source_size": part["size"],
                "source_modified_at": part["modified_at"],
                "job_id": str(state.get("job_id") or ""),
                "status": state["status"],
                "transcript_path": str(transcript_path),
                "transcript_sha256": transcript_sha256,
                "large_payload_local_bytes": 0,
            }
            component_evidence.append(component)
            text = transcript_path.read_text(encoding="utf-8").rstrip()
            if not text:
                raise EnrichmentError(
                    "Ticket 05 logical episode component transcript is empty"
                )
            sections.append(
                "\n".join(
                    (
                        (
                            f"## 分片 {part_index}/{item['part_count']}"
                            f"｜{part['name']}"
                        ),
                        f"来源路径：{part['path']}",
                        f"证据 SHA-256：{transcript_sha256}",
                        "",
                        text,
                    )
                )
            )
        if len(netdisk_directories) != 1:
            raise EnrichmentError(
                "Ticket 05 automatic episode spans multiple source directories"
            )
        merged_bytes = ("\n\n".join(sections).rstrip() + "\n").encode("utf-8")
        temporary = merged_path.with_name(f".{merged_path.name}.partial")
        temporary.write_bytes(merged_bytes)
        temporary.replace(merged_path)
        manifest = {
            "schema_version": 1,
            "event": "subscription_video_episode_evidence_assembled",
            "episode_identity": item["identity"],
            "episode_version_key": item["version_key"],
            "episode_title": item["episode_title"],
            "grouping_method": item["grouping_method"],
            "completion_contract": item["completion_contract"],
            "part_count": item["part_count"],
            "source": item["source"],
            "author": item["author"],
            "component_evidence": component_evidence,
            "merged_evidence_path": str(merged_path),
            "merged_evidence_sha256": hashlib.sha256(merged_bytes).hexdigest(),
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
            "assembled_at": self._time().isoformat(timespec="seconds"),
        }
        manifest_path = artifact_dir / "episode_evidence.json"
        _atomic_write_json(manifest_path, manifest)
        service = NetdiskEnrichmentService(
            self.output_dir / "enrichment" / item["version_key"],
            runner=self.runner,
            now=self.now,
            opencli_command=self.opencli_command,
            netdisk_directory=next(iter(netdisk_directories)),
        )
        state = service.register_verified_composite(
            episode_identity=item["identity"],
            episode_version_key=item["version_key"],
            title=item["episode_title"],
            source=item["source"],
            author=item["author"],
            transcript_path=merged_path,
            components=component_evidence,
            observed_at=self._time(),
        )
        return {
            **state,
            "episode_evidence_path": str(manifest_path),
            "episode_evidence_sha256": _sha256_file(manifest_path),
        }

    def _analysis_request(
        self,
        item: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_dir = self.output_dir / "artifacts" / item["version_key"]
        artifact_dir.mkdir(parents=True, exist_ok=True)
        request_path = artifact_dir / "analysis_request.json"
        source_date = re.search(
            r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日",
            item["path"],
        )
        if source_date:
            year = int(source_date.group(1) or self._time().year)
            publication_time = datetime(
                year,
                int(source_date.group(2)),
                int(source_date.group(3)),
                tzinfo=self._time().tzinfo,
            ).isoformat(timespec="seconds")
            publication_time_precision = "date"
        else:
            publication_time = datetime.fromtimestamp(
                int(item["modified_at"]),
                tz=timezone.utc,
            ).astimezone().isoformat(timespec="seconds")
            publication_time_precision = "provider_modified_at"
        claim_extraction = build_claim_extraction_request(
            state["transcript_path"],
            evidence_sha256=str(state["transcript_sha256"]),
        )
        request = {
            "schema_version": 2,
            "event": "subscription_video_analysis_input_required",
            "source": item["source"],
            "author": item["author"],
            "author_profile": semantic_author_profile(item["author"]),
            "title": (
                item["episode_title"]
                if item.get("is_episode") is True
                else item["name"]
            ),
            "publication_time": publication_time,
            "published_at": publication_time,
            "publication_time_precision": publication_time_precision,
            "capture_time": item["version_first_seen_at"],
            "captured_at": item["version_first_seen_at"],
            "media_type": "video",
            "source_path": item["path"],
            "source_identity": item["identity"],
            "source_version_key": item["version_key"],
            "handoff_id": item["identity"],
            "message_sha256": state["transcript_sha256"],
            "content_sha256": state["transcript_sha256"],
            "media_identity": f"not_applicable:{item['identity']}",
            "artifact_dir": str(request_path.parent.resolve()),
            "source_size": item["size"],
            "source_modified_at": item["modified_at"],
            "evidence_path": state["transcript_path"],
            "evidence_sha256": state["transcript_sha256"],
            "investment_claim_extraction": claim_extraction,
            "required_coverage_rows": sorted(REQUIRED_COVERAGE_ROWS),
            "requirements": {
                "complete_transcript_is_decision_evidence": True,
                "market_outlook_leads_when_supported": True,
                "resolve_every_named_asset": True,
                "xiaocao_cross_view": "consensus_conflict_or_unrelated",
                "household_is_advisory": True,
                "book": "KOL-US",
                "paper_only": True,
                "no_trade_requires_reason": True,
                "source_agnostic_claim_inventory_required": True,
                "independent_full_evidence_coverage_audit_required": True,
                "must_surface_specific_or_material_claims": True,
                "reader_output": "wecom_narrative_v1",
            },
        }
        if item.get("is_episode") is True:
            request["logical_content"] = {
                "kind": "multi_part_episode",
                "episode_identity": item["identity"],
                "episode_version_key": item["version_key"],
                "episode_title": item["episode_title"],
                "grouping_method": item["grouping_method"],
                "completion_contract": item["completion_contract"],
                "part_count": item["part_count"],
                "analyze_and_deliver_once": True,
            }
            request["component_evidence"] = state["component_evidence"]
        _atomic_write_json(request_path, request)
        return {**request, "analysis_request_path": str(request_path)}

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EnrichmentError(
                    f"Ticket 05 reconciliation ledger is invalid: {path.name}"
                ) from exc
            if isinstance(row, dict):
                rows.append(row)
        return rows

    @staticmethod
    def _normalized_transcript(text: str) -> str:
        return re.sub(r"\s+", "", text)

    def _validate_analysis_bundle(
        self,
        item: dict[str, Any],
        state: dict[str, Any],
        *,
        bundle_path: Path | str,
    ) -> dict[str, Any]:
        """Fail closed before any household or paper side effect."""
        bundle_file = Path(bundle_path).expanduser().resolve()
        try:
            bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnrichmentError("Ticket 05 decision bundle is invalid") from exc
        rows = bundle.get("items") if isinstance(bundle, dict) else None
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise EnrichmentError(
                "Ticket 05 decision bundle requires exactly one item"
            )
        if isinstance(bundle, dict) and bundle.get("schema_version") == 2:
            receipt, canonical_bundle = read_validated_bundle(bundle_file)
            validate_receipt_bindings(
                receipt,
                {
                    "source_identity": item.get("identity"),
                    "source_version_key": item.get("version_key"),
                    "transcript_sha256": state.get("transcript_sha256"),
                },
            )
            canonical_item = canonical_bundle["items"][0]
            if canonical_item.get("evidence_sha256") != state.get(
                "transcript_sha256"
            ):
                raise EnrichmentError(
                    "Ticket 05 validated bundle transcript receipt does not match"
                )
            return canonical_item
        decision = rows[0]
        expected_title = f"{item['author']}{PurePosixPath(item['name']).stem}"
        evidence_path = self._runtime_path(
            str(decision.get("evidence_path") or "")
        )
        transcript_path = self._runtime_path(
            str(state.get("transcript_path") or "")
        )
        if (
            decision.get("source") != item["source"]
            or decision.get("author") != item["author"]
            or decision.get("title") != expected_title
            or evidence_path != transcript_path
            or decision.get("evidence_sha256") != state.get("transcript_sha256")
            or not transcript_path.is_file()
            or _sha256_file(transcript_path) != state.get("transcript_sha256")
        ):
            raise EnrichmentError(
                "Ticket 05 decision bundle changed source or evidence identity"
            )
        decision_status = str(decision.get("decision_status") or "")
        if decision_status not in DECISION_STATUSES:
            raise EnrichmentError(
                "Ticket 05 decision_status must be actionable_signal "
                "or no_actionable_signal"
            )
        signals = decision.get("actionable_signals") or []
        if decision_status == "actionable_signal" and not signals:
            raise EnrichmentError(
                "Ticket 05 actionable_signal requires an actionable signal"
            )
        if decision_status == "no_actionable_signal":
            insight = decision.get("reader_insight") or {}
            if insight.get("status") not in {"useful", "none"}:
                raise EnrichmentError(
                    "Ticket 05 no_actionable_signal requires reader_insight"
                )
            if insight["status"] == "useful" and any(
                not str(insight.get(field) or "").strip()
                for field in ("summary", "boundary")
            ):
                raise EnrichmentError(
                    "Ticket 05 useful reader insight is incomplete"
                )
            if insight["status"] == "none" and not str(
                insight.get("reason") or ""
            ).strip():
                raise EnrichmentError(
                    "Ticket 05 empty reader insight needs a reason"
                )
        knowledge_status = str(decision.get("knowledge_status") or "")
        if knowledge_status not in KNOWLEDGE_STATUSES:
            raise EnrichmentError(
                "Ticket 05 knowledge_status must be reusable_knowledge "
                "or no_reusable_knowledge"
            )
        if not str(decision.get("knowledge_reason") or "").strip():
            raise EnrichmentError("Ticket 05 knowledge branch needs a reason")
        if knowledge_status == "reusable_knowledge":
            distillation = self._runtime_path(
                str(decision.get("distillation_path") or "")
            )
            if not distillation.is_file():
                raise EnrichmentError(
                    "Ticket 05 reusable knowledge needs a distillation"
                )
        coverage = decision.get("coverage_matrix")
        coverage_ids = {
            row.get("row_id")
            for row in coverage or []
            if isinstance(row, dict)
        }
        if (
            not isinstance(coverage, list)
            or len(coverage) != len(REQUIRED_COVERAGE_ROWS)
            or any(not isinstance(row, dict) for row in coverage)
            or coverage_ids != REQUIRED_COVERAGE_ROWS
            or any(
                not str(row.get("conclusion") or "").strip()
                or not isinstance(row.get("evidence"), list)
                or not row["evidence"]
                for row in coverage
            )
        ):
            raise EnrichmentError(
                "Ticket 05 trade-information coverage is incomplete"
            )
        cross_view = decision.get("xiaocao_cross_view")
        relation_count = 0
        if isinstance(cross_view, dict):
            for field in ("consensus", "conflicts", "unrelated"):
                relations = cross_view.get(field)
                if not isinstance(relations, list):
                    raise EnrichmentError(
                        "Ticket 05 Xiaocao cross-view is incomplete"
                    )
                relation_count += len(relations)
        if not isinstance(cross_view, dict) or relation_count == 0:
            raise EnrichmentError(
                "Ticket 05 needs an explicit Xiaocao cross-view"
            )
        if not any(
            str(cross_view.get(field) or "").strip()
            for field in ("side_effect_policy", "duplicate_side_effect_policy")
        ):
            raise EnrichmentError(
                "Ticket 05 cross-view needs a duplicate side-effect policy"
            )
        if not isinstance(decision.get("market_outlook"), dict):
            raise EnrichmentError("Ticket 05 market outlook is required")
        paper = decision.get("book_kol_us") or {}
        if paper.get("decision") not in {"trade", "no_trade"}:
            raise EnrichmentError("Ticket 05 Book KOL-US decision is invalid")
        if paper["decision"] == "no_trade" and not str(
            paper.get("reason") or ""
        ).strip():
            raise EnrichmentError("Ticket 05 no-trade needs a reason")
        try:
            validate_claim_coverage(
                decision,
                evidence_text=transcript_path.read_text(encoding="utf-8"),
                evidence_sha256=str(state["transcript_sha256"]),
            )
        except DecisionError as exc:
            raise EnrichmentError(
                "Ticket 05 investment-claim coverage is incomplete"
            ) from exc
        return decision

    def _semantic_duplicate_input(
        self,
        item: dict[str, Any],
        state: dict[str, Any],
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
    ) -> Path | None:
        """Find a fully receipted same-author/title decision without side effects."""
        bundle_file = Path(bundle_path).expanduser().resolve()
        try:
            bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        bundle_items = bundle.get("items") if isinstance(bundle, dict) else None
        if (
            not isinstance(bundle_items, list)
            or len(bundle_items) != 1
            or not isinstance(bundle_items[0], dict)
        ):
            return None
        decision_item = bundle_items[0]
        expected_title = f"{item['author']}{PurePosixPath(item['name']).stem}"
        if (
            decision_item.get("author") != item["author"]
            or decision_item.get("title") != expected_title
        ):
            return None
        current_path = self._runtime_path(
            str(state.get("transcript_path") or "")
        )
        try:
            current_text = current_path.read_text(encoding="utf-8")
        except OSError:
            return None
        current_normalized = self._normalized_transcript(current_text)
        if len(current_normalized) < 2_000:
            return None

        output_dir = Path(decision_output_dir).expanduser().resolve()
        outbox = self._read_jsonl(output_dir / "household_outbox.jsonl")
        events = self._read_jsonl(output_dir / "events.jsonl")
        delivered = {
            str(row.get("idempotency_key")): row
            for row in events
            if row.get("event") == "notification_delivered"
            and row.get("status") == "delivered"
            and str(row.get("receipt") or "").strip()
        }
        paper_rows = self._read_jsonl(
            output_dir / "book_kol_us" / "decisions.jsonl"
        )
        for prior in reversed(outbox):
            notification_key = str(prior.get("idempotency_key") or "")
            delivery = delivered.get(notification_key)
            if (
                prior.get("author") != item["author"]
                or prior.get("title") != expected_title
                or delivery is None
            ):
                continue
            prior_path = self._runtime_path(
                str(prior.get("evidence") or "")
            )
            prior_sha = str(prior.get("evidence_sha256") or "")
            if (
                not prior_path.is_file()
                or not _SHA256.fullmatch(prior_sha)
                or _sha256_file(prior_path) != prior_sha
            ):
                continue
            prior_normalized = self._normalized_transcript(
                prior_path.read_text(encoding="utf-8")
            )
            if len(prior_normalized) < 2_000:
                continue
            similarity = SequenceMatcher(
                None,
                current_normalized,
                prior_normalized,
                autojunk=False,
            ).ratio()
            containment = (
                current_normalized in prior_normalized
                or prior_normalized in current_normalized
            )
            if similarity < 0.995 or not containment:
                continue
            paper = next(
                (
                    row
                    for row in paper_rows
                    if (
                        row.get("evidence_context") or {}
                    ).get("evidence_sha256")
                    == prior_sha
                    and row.get("book") == "KOL-US"
                    and row.get("paper_only") is True
                    and row.get("status") in {"filled", "no_trade"}
                ),
                None,
            )
            if paper is None:
                continue
            reconciliation = {
                "schema_version": 1,
                "event": "subscription_video_semantic_duplicate_input",
                "source": item["source"],
                "author": item["author"],
                "title": expected_title,
                "current_evidence_path": str(current_path),
                "current_evidence_sha256": state["transcript_sha256"],
                "current_normalized_sha256": _sha256_text(current_normalized),
                "prior_evidence_path": str(prior_path.resolve()),
                "prior_evidence_sha256": prior_sha,
                "prior_normalized_sha256": _sha256_text(prior_normalized),
                "normalized_similarity": similarity,
                "normalized_containment": True,
                "household_notification": {
                    "idempotency_key": notification_key,
                    "status": "delivered",
                    "receipt": delivery["receipt"],
                    "delivered_at": delivery.get("delivered_at"),
                },
                "book_kol_us": paper,
                "matched_at": self._time().isoformat(timespec="seconds"),
            }
            artifact_dir = self.output_dir / "artifacts" / item["version_key"]
            reconciliation_path = artifact_dir / "semantic_duplicate_input.json"
            _atomic_write_json(reconciliation_path, reconciliation)
            return reconciliation_path
        return None

    def _verify_transcript(
        self,
        service: NetdiskEnrichmentService,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        text = Path(state["transcript_path"]).read_text(encoding="utf-8")
        starts = {
            "opening": 0,
            "middle": math.ceil(len(text) / 3),
            "ending": math.ceil(len(text) * 2 / 3),
        }
        checks = []
        for position, start in starts.items():
            excerpt = text[start : min(len(text), start + 160)].strip()
            if not excerpt:
                raise EnrichmentError("captured transcript third is empty")
            checks.append(
                {
                    "position": position,
                    "excerpt": excerpt,
                    "passed": True,
                }
            )
        audit = {
            "video_sha256": state["video_sha256"],
            "transcript_sha256": state["transcript_sha256"],
            "checks": checks,
        }
        audit_path = (
            self.output_dir
            / "artifacts"
            / str(state["source_version_sha256"])
            / "content_audit_input.json"
        )
        _atomic_write_json(audit_path, audit)
        return service.verify_transcript(
            state["job_id"],
            audit_path=audit_path,
        )

    def _advance_part_to_verified(
        self,
        item: dict[str, Any],
        *,
        lv_session: str,
        private_session: str,
        enrichment_session: str,
        profile: str | None,
        observability_repair_revision: str | None = None,
    ) -> dict[str, Any]:
        if item["source"] == LV_SOURCE:
            receipt = self.transfer_lv_video(
                item,
                lv_session=lv_session,
                private_session=private_session,
                profile=profile,
                observability_repair_revision=(
                    observability_repair_revision
                ),
            )
            if receipt.get("status") != "completed":
                return {**receipt, "pending": True}
            netdisk_path = str(receipt["target_path"])
            provider_hash = str(receipt["target_provider_identity_sha256"])
            size = int(receipt["target_size"])
            modified_at = int(receipt["target_modified_at"])
        elif item["source"] == LUCIFER_SOURCE:
            netdisk_path = str(item["path"])
            provider_hash = str(item["provider_identity_sha256"])
            size = int(item["size"])
            modified_at = int(item["modified_at"])
        else:
            raise EnrichmentError("Ticket 05 source is unsupported")
        service = self._enrichment_service(item, netdisk_path=netdisk_path)
        state = service.prepare_cloud(
            netdisk_path=netdisk_path,
            provider_identity_sha256=provider_hash,
            size=size,
            modified_at=modified_at,
            source=item["source"],
            author=item["author"],
            observed_at=self._time(),
        )
        for _step in range(20):
            status = str(state.get("status") or "")
            if status == "transcript_captured":
                state = self._verify_transcript(service, state)
                continue
            if status in {"verified", "decided"}:
                return state
            not_before = state.get("next_poll_not_before")
            if not_before:
                checkpoint = datetime.fromisoformat(str(not_before))
                wait_seconds = (
                    checkpoint.astimezone(timezone.utc)
                    - self._time().astimezone(timezone.utc)
                ).total_seconds()
                if wait_seconds > 0:
                    return {
                        **state,
                        "pending": True,
                        "poll_deferred": True,
                    }
            state = service.advance_opencli(
                state["job_id"],
                session=enrichment_session,
                profile=profile,
            )
            if state.get("pending") is True:
                return state
        return {**state, "pending": True}

    def advance_item(
        self,
        item: dict[str, Any],
        *,
        lv_session: str,
        private_session: str,
        enrichment_session: str,
        profile: str | None,
        observability_repair_revision: str | None = None,
    ) -> dict[str, Any]:
        if item.get("is_episode") is not True:
            state = self._advance_part_to_verified(
                item,
                lv_session=lv_session,
                private_session=private_session,
                enrichment_session=enrichment_session,
                profile=profile,
                observability_repair_revision=(
                    observability_repair_revision
                ),
            )
            if state.get("status") == "verified":
                return self._analysis_request(item, state)
            return state

        next_poll_not_before = item.get("next_poll_not_before")
        if next_poll_not_before:
            checkpoint = datetime.fromisoformat(str(next_poll_not_before))
            if (
                self._time().astimezone(timezone.utc)
                < checkpoint.astimezone(timezone.utc)
            ):
                return {
                    "schema_version": 1,
                    "event": "subscription_video_episode_settling",
                    "status": "waiting_components",
                    "identity": item["identity"],
                    "version_key": item["version_key"],
                    "part_count": item["part_count"],
                    "completion_contract": item["completion_contract"],
                    "next_poll_not_before": checkpoint.isoformat(),
                    "large_payload_local_bytes": 0,
                    "coordinator_source_video_bytes": 0,
                    "pending": True,
                }
        component_states = []
        pending_components = []
        for part in sorted(
            item["parts"],
            key=lambda row: int(row["part_index"]),
        ):
            state = self._advance_part_to_verified(
                part,
                lv_session=lv_session,
                private_session=private_session,
                enrichment_session=enrichment_session,
                profile=profile,
                observability_repair_revision=(
                    observability_repair_revision
                ),
            )
            state = {**state, "part_index": int(part["part_index"])}
            component_states.append(state)
            if state.get("status") not in {"verified", "decided"}:
                pending_components.append(
                    {
                        "identity": part["identity"],
                        "version_key": part["version_key"],
                        "part_index": part["part_index"],
                        "part_label": part["part_label"],
                        "status": state.get("status"),
                        "next_poll_not_before": state.get(
                            "next_poll_not_before"
                        ),
                        "retry_count": int(state.get("retry_count") or 0),
                        "failure_reason": str(
                            state.get("reason")
                            or state.get("failure_stage")
                            or ""
                        ),
                    }
                )
        if pending_components:
            return {
                "schema_version": 1,
                "event": "subscription_video_episode_pending",
                "status": "waiting_components",
                "identity": item["identity"],
                "version_key": item["version_key"],
                "part_count": item["part_count"],
                "pending_components": pending_components,
                "large_payload_local_bytes": 0,
                "coordinator_source_video_bytes": 0,
                "pending": True,
            }
        state = self._prepare_episode_evidence(item, component_states)
        if state.get("status") == "decided":
            return state
        return self._analysis_request(item, state)

    @_exclusive("manifest")
    def complete_item(
        self,
        item: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = self._load_manifest()
        collection = (
            manifest.get("episodes", {})
            if item.get("is_episode") is True
            else manifest["items"]
        )
        current = collection.get(item["identity"])
        if not isinstance(current, dict):
            raise EnrichmentError("completed Ticket 05 item disappeared")
        if current.get("version_key") != item["version_key"]:
            raise EnrichmentError("completed Ticket 05 item version changed")
        result_path = str(result.get("decision_result_path") or "")
        result_file = self._runtime_path(result_path)
        if not result_path or not result_file.is_file():
            raise EnrichmentError("Ticket 05 decision result is missing")
        result_sha256 = _sha256_file(result_file)
        current_result_file = self._runtime_path(
            str(current.get("decision_result_path") or "")
        )
        if (
            current.get("completed_version_key") == item["version_key"]
            and current_result_file == result_file
            and current.get("decision_result_sha256") == result_sha256
        ):
            completed_at = str(
                current.get("completed_at")
                or result.get("completed_at")
                or result.get("updated_at")
                or ""
            ).strip()
            if not completed_at:
                completion = next(
                    (
                        row
                        for row in reversed(self._read_jsonl(self.events_path))
                        if row.get("event") == "subscription_video_completed"
                        and row.get("identity") == item["identity"]
                        and row.get("version_key") == item["version_key"]
                        and row.get("decision_result_sha256") == result_sha256
                    ),
                    None,
                )
                completed_at = str(
                    (completion or {}).get("completed_at") or ""
                ).strip()
            if not completed_at:
                raise EnrichmentError(
                    "completed Ticket 05 item has no historical completion time"
                )
            return {
                "event": "subscription_video_completed",
                "identity": item["identity"],
                "version_key": item["version_key"],
                "source": item["source"],
                "author": item["author"],
                "job_id": result["job_id"],
                "decision_result_path": str(result_file),
                "decision_result_sha256": result_sha256,
                "completed_at": completed_at,
                "is_episode": item.get("is_episode") is True,
                "part_count": int(item.get("part_count") or 1),
                "component_identities": [
                    part["identity"] for part in item.get("parts") or []
                ],
                "idempotent_replay": True,
            }
        completion = (
            {
                "completed_version_key": item["version_key"],
                "work_eligible": False,
                "enrichment_job_id": result["job_id"],
                "decision_result_path": result_path,
                "decision_result_sha256": result_sha256,
                "completed_at": self._time().isoformat(timespec="seconds"),
            }
        )
        completed_after_user_review = (
            current.get("reconciliation_status")
            == "awaiting_user_review"
        )
        current.update(completion)
        current.pop("pause_reason", None)
        current.pop("review_required_path", None)
        current.pop("review_required_sha256", None)
        if completed_after_user_review:
            current["reconciliation_status"] = (
                "completed_after_user_review"
            )
        if item.get("is_episode") is True:
            for part in current["parts"]:
                member = manifest["items"].get(str(part["identity"]))
                if not isinstance(member, dict):
                    raise EnrichmentError(
                        "completed Ticket 05 episode component disappeared"
                    )
                if member.get("version_key") != part["version_key"]:
                    raise EnrichmentError(
                        "completed Ticket 05 episode component changed"
                    )
                member.update(
                    {
                        "completed_version_key": part["version_key"],
                        "completed_episode_version_key": item["version_key"],
                        "work_eligible": False,
                        "episode_decision_result_path": result_path,
                        "episode_decision_result_sha256": completion[
                            "decision_result_sha256"
                        ],
                    }
                )
                member.pop("episode_pause_reason", None)
        _atomic_write_json(self.manifest_path, manifest)
        event = {
            "event": "subscription_video_completed",
            "identity": item["identity"],
            "version_key": item["version_key"],
            "source": item["source"],
            "author": item["author"],
            "job_id": result["job_id"],
            "decision_result_path": result_path,
            "decision_result_sha256": current["decision_result_sha256"],
            "completed_at": current["completed_at"],
            "is_episode": item.get("is_episode") is True,
            "part_count": int(item.get("part_count") or 1),
            "component_identities": [
                part["identity"] for part in item.get("parts") or []
            ],
        }
        _append_jsonl(self.events_path, event)
        return event

    def approve_legacy_episode_review(
        self,
        episode_identity: str,
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
        sender: Callable[[str, str], dict[str, str]],
    ) -> dict[str, Any]:
        """Bind the review and hand off to event-specific 灰常亮 publication.

        The former implementation delegated to ``decide_item`` and could send
        the complete report through Enterprise WeChat.  That surface is
        retired: historical approval never authorizes a notification or Book
        replay.  The exact report must be published through the durable
        LiangHui publication ledger instead.
        """

        del decision_output_dir, sender
        manifest = self._load_manifest()
        episode = self._legacy_episode(manifest, episode_identity)
        if (
            episode.get("reconciliation_status")
            != "awaiting_user_review"
            or episode.get("pause_reason")
            != "useful_aggregate_insight_requires_user_review"
        ):
            raise EnrichmentError(
                "Ticket 05 legacy episode is not awaiting user review"
            )
        review_path = Path(
            str(episode.get("review_required_path") or "")
        ).expanduser().resolve()
        review_sha256 = str(
            episode.get("review_required_sha256") or ""
        )
        if (
            not review_path.is_file()
            or not _SHA256.fullmatch(review_sha256)
            or _sha256_file(review_path) != review_sha256
        ):
            raise EnrichmentError(
                "Ticket 05 reviewed aggregate artifact is missing or changed"
            )
        review = json.loads(review_path.read_text(encoding="utf-8"))
        bundle_file = Path(bundle_path).expanduser().resolve()
        if (
            not bundle_file.is_file()
            or review.get("episode_identity") != episode["identity"]
            or review.get("episode_version_key") != episode["version_key"]
            or review.get("decision_bundle_sha256")
            != _sha256_file(bundle_file)
        ):
            raise EnrichmentError(
                "Ticket 05 approval does not match the reviewed bundle"
            )
        self._write_claim(
            (
                "legacy_episode_gray_publication_handoff_"
                + str(episode["version_key"])
                + "_"
                + str(review["decision_bundle_sha256"])[:16]
            ),
            {
                "episode_identity": episode["identity"],
                "episode_version_key": episode["version_key"],
                "review_required_path": str(review_path),
                "review_required_sha256": review_sha256,
                "decision_bundle_path": str(bundle_file),
                "decision_bundle_sha256": review[
                    "decision_bundle_sha256"
                ],
                "external_side_effects_authorized": False,
                "notification_claim_authorized": False,
                "book_replay_authorized": False,
                "authorization_scope": (
                    "one complete event-specific 灰常亮 report through the "
                    "durable publication ledger"
                ),
                "large_payload_local_bytes": 0,
                "coordinator_source_video_bytes": 0,
            },
        )
        return {
            "schema_version": 1,
            "status": "gray_publication_required",
            "episode_identity": episode["identity"],
            "episode_version_key": episode["version_key"],
            "review_required_path": str(review_path),
            "review_required_sha256": review_sha256,
            "decision_bundle_path": str(bundle_file),
            "decision_bundle_sha256": review["decision_bundle_sha256"],
            "notification_claim_authorized": False,
            "book_replay_authorized": False,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
        }

    def decide_item(
        self,
        item: dict[str, Any],
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
        sender: Callable[[str, str], dict[str, str]],
        pipeline: Any | None = None,
    ) -> dict[str, Any]:
        enrichment_dir = self.output_dir / "enrichment" / item["version_key"]
        state = NetdiskEnrichmentService(
            enrichment_dir,
            runner=self.runner,
            now=self.now,
            opencli_command=self.opencli_command,
            netdisk_directory=(
                LV_DESTINATION_DIRECTORY
                if item["source"] == LV_SOURCE
                else str(PurePosixPath(item["path"]).parent)
            ),
        ).status()
        netdisk_directory = str(
            state.get("netdisk_directory")
            or PurePosixPath(str(state.get("netdisk_path") or item["path"])).parent
        )
        service = NetdiskEnrichmentService(
            enrichment_dir,
            runner=self.runner,
            now=self.now,
            opencli_command=self.opencli_command,
            netdisk_directory=netdisk_directory,
        )
        self._validate_analysis_bundle(
            item,
            state,
            bundle_path=bundle_path,
        )
        bundle_file = Path(bundle_path).expanduser().resolve()
        exact_completed_replay = (
            state.get("status") == "decided"
            and state.get("decision_bundle_sha256")
            == _sha256_file(bundle_file)
        )
        reconciliation_path = None
        if not exact_completed_replay:
            reconciliation_path = self._semantic_duplicate_input(
                item,
                state,
                bundle_path=bundle_file,
                decision_output_dir=decision_output_dir,
            )
        if reconciliation_path is not None:
            result = service.reconcile_semantic_duplicate(
                state["job_id"],
                bundle_path=bundle_file,
                reconciliation_path=reconciliation_path,
                decision_output_dir=decision_output_dir,
            )
        else:
            result = service.decide(
                state["job_id"],
                bundle_path=bundle_file,
                decision_output_dir=decision_output_dir,
                sender=sender,
                pipeline=pipeline,
            )
        self.complete_item(item, result)
        return result
