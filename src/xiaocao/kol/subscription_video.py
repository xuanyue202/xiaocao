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
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import quote, urlparse

from .enrichment_types import EnrichmentError
from .lv_subscription import LvSubscriptionService
from .netdisk_enrichment import NetdiskEnrichmentService


LV_SOURCE = "baidu_subscription_share_browser"
LUCIFER_SOURCE = "baidu_private_folder"
LV_AUTHOR = "吕晓彤"
LUCIFER_AUTHOR = "路西法"
LUCIFER_ROOT = "/课程/路西法全套"
LV_DESTINATION_PARENT = "/课程/自己的课"
LV_DESTINATION_DIRECTORY = "/课程/自己的课/吕晓彤"
VIDEO_SUFFIXES = {".avi", ".flv", ".m4v", ".mkv", ".mov", ".mp4"}
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


_PRIVATE_SCAN_SCRIPT = r"""(async () => {
  const rootDir = __ROOT_DIR__;
  const recursive = __RECURSIVE__;
  const routeFor = dir => '/index?category=all&path=' + encodeURIComponent(dir);
  const currentDir = () => {
    const hash = String(location.hash || '');
    const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
    return new URLSearchParams(query).get('path');
  };
  const readDirectory = async dir => {
    location.hash = routeFor(dir);
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      if (
        location.origin !== 'https://pan.baidu.com'
        || location.pathname !== '/disk/main'
        || currentDir() !== dir
      ) {
        await new Promise(resolve => setTimeout(resolve, 100));
        continue;
      }
      const rows = [...document.querySelectorAll('tr[data-id]')];
      const items = rows.map(row => row.__vue__?._props?.item).filter(Boolean);
      const exact = items.length === rows.length && items.every(item => {
        const path = String(item.path || '');
        const parent = path.slice(0, path.lastIndexOf('/')) || '/';
        return path.startsWith('/')
          && parent === dir;
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
            modified_at: Number(
              item.server_mtime || item.local_mtime || 0
            )
          }))
        };
      }
      if (/当前列表为空|暂无文件/.test(text)) {
        return {status: 'ok', rows: []};
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    return {status: 'private_directory_load_timeout', rows: []};
  };
  const pending = [rootDir];
  const seen = new Set();
  const entries = [];
  while (pending.length > 0) {
    if (seen.size >= 200 || entries.length >= 10000) {
      return {status: 'private_listing_bounds_exceeded', entries: []};
    }
    const dir = pending.shift();
    if (seen.has(dir)) continue;
    seen.add(dir);
    const result = await readDirectory(dir);
    if (result.status !== 'ok') {
      return {status: result.status, entries: []};
    }
    for (const item of result.rows) {
      entries.push(item);
      if (
        recursive
        && item.is_dir
        && item.path.startsWith(rootDir + '/')
      ) {
        pending.push(item.path);
      }
    }
  }
  return {
    status: 'ok',
    complete_scan: true,
    directories_scanned: seen.size,
    entries
  };
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
  while (Date.now() < deadline) {
    const rows = [...document.querySelectorAll('tr[data-id]')];
    const items = rows.map(row => row.__vue__?._props?.item).filter(Boolean);
    const matches = items.filter(item => (
      String(item.server_filename || '') === targetName
    ));
    if (matches.length > 0 || /无搜索结果|暂无/.test(
      String(document.body?.innerText || '')
    )) {
      return {
        status: 'ok',
        entries: matches.map(item => ({
          provider_file_id: String(item.fs_id || ''),
          path: String(item.path || ''),
          name: String(item.server_filename || ''),
          is_dir: item.isdir === 1 || item.isdir === true,
          size: Number(item.size || 0),
          modified_at: Number(item.server_mtime || item.local_mtime || 0)
        }))
      };
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  return {status: 'private_search_timeout', entries: []};
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
    if (!row.classList.contains('JS-item-active')) continue;
    const selection = row.querySelector('span.EOGexf');
    if (!selection) {
      return {status: 'transfer_selection_control_missing', triggered: false};
    }
    selection.click();
  }
  await new Promise(resolve => setTimeout(resolve, 200));
  const targetSelection = targets[0].querySelector('span.EOGexf');
  if (!targetSelection) {
    return {status: 'transfer_selection_control_missing', triggered: false};
  }
  targetSelection.click();
  await new Promise(resolve => setTimeout(resolve, 200));
  const selectedNames = [...document.querySelectorAll(
    '#shareqr dd.JS-item-active a.filename'
  )].map(link => String(link.getAttribute('title') || ''));
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
    const candidates = [...document.querySelectorAll(
      '.dialog-fileTreeDialog'
    )].filter(node => (
      visible(node)
      && /保存到|选择保存路径|我的网盘/.test(
        String(node.innerText || node.textContent || '')
      )
    ));
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
  confirms[0].click();
  return {status: 'cloud_transfer_triggered', triggered: true};
})()"""


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
            raise EnrichmentError("Ticket 05 browser command timed out") from exc
        if result.returncode != 0:
            raise EnrichmentError("Ticket 05 browser command failed")
        try:
            value = json.loads(str(result.stdout))
        except (TypeError, json.JSONDecodeError) as exc:
            raise EnrichmentError("Ticket 05 browser returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise EnrichmentError("Ticket 05 browser returned a non-object")
        return value

    def _scan_private(
        self,
        *,
        session: str,
        profile: str | None,
        root: str,
        recursive: bool,
    ) -> dict[str, Any]:
        url = (
            "https://pan.baidu.com/disk/main#/index?category=all&path="
            + quote(root, safe="")
        )
        self._opencli_json(
            session,
            "open",
            url,
            profile=profile,
            timeout_seconds=30,
        )
        script = (
            _PRIVATE_SCAN_SCRIPT.replace(
                "__ROOT_DIR__",
                json.dumps(root, ensure_ascii=False),
            )
            .replace("__RECURSIVE__", "true" if recursive else "false")
        )
        payload = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=180,
        )
        if (
            payload.get("status") != "ok"
            or payload.get("complete_scan") is not True
            or not isinstance(payload.get("entries"), list)
        ):
            raise EnrichmentError(
                f"private Netdisk listing failed: {payload.get('status')}"
            )
        return payload

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
            modified_at = int(row.get("modified_at") or 0)
        except (TypeError, ValueError) as exc:
            raise EnrichmentError("Ticket 05 source metadata is invalid") from exc
        is_dir = bool(row.get("is_dir"))
        if size < 0 or (not is_dir and modified_at <= 0):
            raise EnrichmentError("Ticket 05 source metadata is invalid")
        provider_hash = _sha256_text(provider_id)
        identity = _sha256_text(f"{source}\n{provider_id}")
        version_key = _sha256_text(
            f"{source}\n{provider_id}\n{path}\n{size}\n{modified_at}"
        )
        suffix = Path(name).suffix.lower()
        return {
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
            "modified_at": modified_at,
        }

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

    @_exclusive("manifest")
    def observe(
        self,
        lv_entries: list[dict[str, Any]],
        lucifer_entries: list[dict[str, Any]],
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
        current = {
            identity: {**row, "present": False}
            for identity, row in previous.items()
            if isinstance(row, dict)
        }
        updates = []
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
                ):
                    if key in prior:
                        persisted[key] = prior[key]
            else:
                persisted["work_eligible"] = (
                    not bootstrap and row["media_type"] == "video"
                )
                if row["media_type"] == "video":
                    updates.append(row)
            current[row["identity"]] = persisted

        selected: list[dict[str, Any]] = []
        if bootstrap:
            for source in (LV_SOURCE, LUCIFER_SOURCE):
                candidates = [
                    row
                    for row in normalized
                    if row["source"] == source and row["media_type"] == "video"
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
            selected_versions = {row["version_key"] for row in selected}
            for item in current.values():
                item["work_eligible"] = (
                    item.get("version_key") in selected_versions
                )
            updates = selected
            manifest["bootstrap"] = {
                "policy": "latest_real_video_per_source",
                "completed_at": observed_at,
                "selected": [
                    {
                        key: row[key]
                        for key in (
                            "author",
                            "identity",
                            "modified_at",
                            "path",
                            "size",
                            "source",
                            "version_key",
                        )
                    }
                    for row in selected
                ],
                "historical_video_baseline_count": sum(
                    row["media_type"] == "video" for row in normalized
                )
                - len(selected),
            }
        cursor = _sha256_text(
            _canonical(
                [
                    {
                        "identity": row["identity"],
                        "version_key": row["version_key"],
                    }
                    for row in normalized
                ]
            )
        )
        manifest.update(
            {
                "cursor": cursor,
                "observed_at": observed_at,
                "items": current,
                "source_counts": {
                    source: sum(row["source"] == source for row in normalized)
                    for source in (LV_SOURCE, LUCIFER_SOURCE)
                },
            }
        )
        _atomic_write_json(self.manifest_path, manifest)
        updates = [
            row
            for row in updates
            if current[row["identity"]].get("work_eligible") is True
        ]
        if not updates:
            return None
        result = {
            "event": "subscription_videos_discovered",
            "observed_at": observed_at,
            "cursor": cursor,
            "bootstrap": bootstrap,
            "updates": updates,
        }
        _append_jsonl(self.events_path, result)
        return result

    def scan_opencli(
        self,
        *,
        lv_session: str,
        private_session: str,
        profile: str | None,
    ) -> dict[str, Any] | None:
        lv_listing = self.lv._read_opencli_listing(
            session=lv_session,
            profile=profile,
        )
        lucifer_listing = self._scan_private(
            session=private_session,
            profile=profile,
            root=LUCIFER_ROOT,
            recursive=True,
        )
        return self.observe(
            lv_listing["entries"],
            lucifer_listing["entries"],
        )

    def pending_items(self) -> list[dict[str, Any]]:
        rows = [
            row
            for row in self._load_manifest()["items"].values()
            if (
                isinstance(row, dict)
                and row.get("present") is True
                and row.get("media_type") == "video"
                and row.get("work_eligible") is True
                and row.get("completed_version_key") != row.get("version_key")
            )
        ]
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
            or not isinstance(payload.get("entries"), list)
        ):
            raise EnrichmentError(
                f"private Netdisk search failed: {payload.get('status')}"
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
    ) -> dict[str, Any]:
        if item.get("source") != LV_SOURCE or item.get("author") != LV_AUTHOR:
            raise EnrichmentError("cloud transfer accepts only Lv Xiaotong items")
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
        if (
            claim.get("status") == "failed_pretrigger"
            and claim.get("reason") == "save_dialog_missing"
        ):
            root_matches = [
                row
                for row in self._search_private_exact(
                    session=private_session,
                    profile=profile,
                    target_name=item["name"],
                )
                if (
                    row.get("path") == f"/{item['name']}"
                    and row.get("name") == item["name"]
                    and int(row.get("size") or 0) == int(item["size"])
                )
            ]
            if len(root_matches) > 1:
                raise EnrichmentError(
                    "default-root Lv cloud transfer is ambiguous"
                )
            if len(root_matches) == 1:
                target = self._normalize(
                    root_matches[0],
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
                    "reconciled_default_root_save": True,
                    "completed_at": self._time().isoformat(
                        timespec="seconds"
                    ),
                }
                _atomic_write_json(receipt_path, reconciled)
                _append_jsonl(self.events_path, reconciled)
                return reconciled
        if claim.get("triggered_at"):
            return {**claim, "pending": True, "side_effect_uncertain": True}
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
            **claim,
            "status": "triggered",
            "triggered_at": self._time().isoformat(timespec="microseconds"),
        }
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
            )
            if ready.get("status") == "completed":
                return ready
        return {**triggered, "pending": True, "side_effect_uncertain": True}

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
        request = {
            "schema_version": 1,
            "event": "subscription_video_analysis_input_required",
            "source": item["source"],
            "author": item["author"],
            "title": item["name"],
            "publication_time": publication_time,
            "publication_time_precision": publication_time_precision,
            "capture_time": item["version_first_seen_at"],
            "media_type": "video",
            "source_path": item["path"],
            "source_identity": item["identity"],
            "source_version_key": item["version_key"],
            "source_size": item["size"],
            "source_modified_at": item["modified_at"],
            "evidence_path": state["transcript_path"],
            "evidence_sha256": state["transcript_sha256"],
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
            },
        }
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
        decision = rows[0]
        expected_title = f"{item['author']}{PurePosixPath(item['name']).stem}"
        evidence_path = Path(
            str(decision.get("evidence_path") or "")
        ).expanduser().resolve()
        transcript_path = Path(str(state.get("transcript_path") or "")).resolve()
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
            distillation = Path(
                str(decision.get("distillation_path") or "")
            ).expanduser()
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
        current_path = Path(str(state.get("transcript_path") or "")).resolve()
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
            prior_path = Path(str(prior.get("evidence") or "")).expanduser()
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

    def advance_item(
        self,
        item: dict[str, Any],
        *,
        lv_session: str,
        private_session: str,
        enrichment_session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        if item["source"] == LV_SOURCE:
            receipt = self.transfer_lv_video(
                item,
                lv_session=lv_session,
                private_session=private_session,
                profile=profile,
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
            if status == "verified":
                return self._analysis_request(item, state)
            if status == "decided":
                return state
            not_before = state.get("next_poll_not_before")
            if not_before:
                checkpoint = datetime.fromisoformat(str(not_before))
                wait_seconds = (
                    checkpoint.astimezone(timezone.utc)
                    - self._time().astimezone(timezone.utc)
                ).total_seconds()
                if wait_seconds > 0:
                    self.sleep(min(wait_seconds, 60))
            state = service.advance_opencli(
                state["job_id"],
                session=enrichment_session,
                profile=profile,
            )
        return {**state, "pending": True}

    @_exclusive("manifest")
    def complete_item(
        self,
        item: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = self._load_manifest()
        current = manifest["items"].get(item["identity"])
        if not isinstance(current, dict):
            raise EnrichmentError("completed Ticket 05 item disappeared")
        if current.get("version_key") != item["version_key"]:
            raise EnrichmentError("completed Ticket 05 item version changed")
        result_path = str(result.get("decision_result_path") or "")
        if not result_path or not Path(result_path).is_file():
            raise EnrichmentError("Ticket 05 decision result is missing")
        current.update(
            {
                "completed_version_key": item["version_key"],
                "work_eligible": False,
                "enrichment_job_id": result["job_id"],
                "decision_result_path": result_path,
                "decision_result_sha256": _sha256_file(Path(result_path)),
                "completed_at": self._time().isoformat(timespec="seconds"),
            }
        )
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
        }
        _append_jsonl(self.events_path, event)
        return event

    def decide_item(
        self,
        item: dict[str, Any],
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
        sender: Callable[[str, str], dict[str, str]],
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
        service = NetdiskEnrichmentService(
            enrichment_dir,
            runner=self.runner,
            now=self.now,
            opencli_command=self.opencli_command,
            netdisk_directory=str(PurePosixPath(state["netdisk_path"]).parent),
        )
        self._validate_analysis_bundle(
            item,
            state,
            bundle_path=bundle_path,
        )
        reconciliation_path = self._semantic_duplicate_input(
            item,
            state,
            bundle_path=bundle_path,
            decision_output_dir=decision_output_dir,
        )
        if reconciliation_path is not None:
            result = service.reconcile_semantic_duplicate(
                state["job_id"],
                bundle_path=bundle_path,
                reconciliation_path=reconciliation_path,
                decision_output_dir=decision_output_dir,
            )
        else:
            result = service.decide(
                state["job_id"],
                bundle_path=bundle_path,
                decision_output_dir=decision_output_dir,
                sender=sender,
            )
        self.complete_item(item, result)
        return result
