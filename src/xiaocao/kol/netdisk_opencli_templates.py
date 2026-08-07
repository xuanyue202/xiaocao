"""Versioned OpenCLI DOM templates for Baidu Netdisk video enrichment.

The durable state machine remains in :mod:`netdisk_enrichment`.  These
templates perform one bounded page operation and return credential-free JSON
proof.  Keeping the JavaScript here makes provider races and DOM edge cases
reviewable and independently testable instead of scattering them through the
stepper.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


_PLACEHOLDER = re.compile(r"__[A-Z][A-Z0-9_]*__")
NETDISK_OPENCLI_TEMPLATE_VERSION = 1


@dataclass(frozen=True)
class NetdiskOpenCliTemplate:
    name: str
    source: str
    parameters: tuple[str, ...]

    def render(self, **values: Any) -> str:
        expected = set(self.parameters)
        supplied = set(values)
        if supplied != expected:
            missing = sorted(expected - supplied)
            unknown = sorted(supplied - expected)
            raise ValueError(
                f"invalid {self.name} template parameters: "
                f"missing={missing}, unknown={unknown}"
            )
        rendered = self.source
        for name in self.parameters:
            rendered = rendered.replace(
                f"__{name.upper()}__",
                json.dumps(values[name], ensure_ascii=False),
            )
        unresolved = _PLACEHOLDER.findall(rendered)
        if unresolved:
            raise ValueError(
                f"unresolved {self.name} template placeholders: {unresolved}"
            )
        return rendered


_PROBE_TRANSCRIPT = NetdiskOpenCliTemplate(
    name="probe_transcript",
    parameters=("expected_path",),
    source=r"""(async () => {
  const template_name = 'baidu-netdisk/probe-transcript';
  const template_version = 1;
  const expectedPath = __EXPECTED_PATH__;
  const deadline = Date.now() + 20000;
  let transcript_state = 'missing';
  let active_tab = '';
  let content_chars = 0;
  let export_available = false;
  let target_bound = false;
  while (Date.now() < deadline) {
    const currentUrl = new URL(location.href);
    target_bound = currentUrl.origin === 'https://pan.baidu.com'
      && currentUrl.pathname === '/pfile/video'
      && currentUrl.searchParams.getAll('path').length === 1
      && currentUrl.searchParams.get('path') === expectedPath;
    if (!target_bound) break;
    const active = document.querySelector('.vp-tabs__header-item--active');
    const root = document.querySelector('.vp-ai-draft');
    const list = document.querySelector('.ai-draft__wrap-list');
    const text = (list?.innerText || '').trim();
    const rootText = (root?.innerText || '').trim();
    const exportNode = document.querySelector('.ai-draft__export-container');
    active_tab = (active?.textContent || '').trim();
    content_chars = text.length;
    export_available = !!exportNode;
    if (list && content_chars >= 200 && export_available) {
      transcript_state = 'ready';
    } else if (/生成中|处理中|努力生成/.test(rootText)) {
      transcript_state = 'generating';
    }
    if (transcript_state !== 'missing') break;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  return {
    template_name,
    template_version,
    transcript_state,
    active_tab,
    content_chars,
    export_available,
    target_bound
  };
})()""",
)


_PROBE_AI_NOTE = NetdiskOpenCliTemplate(
    name="probe_ai_note",
    parameters=("expected_path",),
    source=r"""(() => {
  const template_name = 'baidu-netdisk/probe-ai-note';
  const template_version = 1;
  const expectedPath = __EXPECTED_PATH__;
  const currentUrl = new URL(location.href);
  const target_bound = currentUrl.origin === 'https://pan.baidu.com'
    && currentUrl.pathname === '/pfile/video'
    && currentUrl.searchParams.getAll('path').length === 1
    && currentUrl.searchParams.get('path') === expectedPath;
  if (!target_bound) {
    return {
      template_name,
      template_version,
      ai_note_state: 'missing',
      target_bound: false
    };
  }
  const visible = node => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const active = document.querySelector('.vp-tabs__header-item--active');
  const frame = document.getElementById('noteIframe');
  const doc = frame?.contentDocument;
  const text = (doc?.body?.innerText || '').trim();
  const src = frame?.getAttribute('src') || '';
  let ai_note_state = 'missing';
  if (/生成中|正在生成|处理中/.test(text)) {
    ai_note_state = 'generating';
  } else if (
    text.length >= 200
    && (
      src.includes('action=edit')
      || /以下为AI生成的.{0,20}笔记.{0,20}内容/.test(text)
    )
  ) {
    ai_note_state = 'ready';
  }
  const modal = document.getElementById('tplModal');
  const modalDocument = modal?.contentDocument;
  const templateRows = modalDocument
    ? [...modalDocument.querySelectorAll(
        '.wp-ainoteTpl__left__list__item'
      )]
    : [];
  const selectedRows = templateRows.filter(row => (
    row.querySelector('.selected')
    && visible(row)
  ));
  const selectedTitles = selectedRows.map(row => (
    row.querySelector('.wp-ainoteTpl__left__list__item__title')
      ?.textContent || ''
  ).trim()).filter(Boolean);
  const submitButtons = modalDocument
    ? [...modalDocument.querySelectorAll('button')].filter(node => (
        visible(node)
        && !node.disabled
        && (node.textContent || '').trim() === '生成该笔记'
      ))
    : [];
  return {
    template_name,
    template_version,
    ai_note_state,
    active_tab: (active?.textContent || '').trim(),
    content_chars: text.length,
    template: /文稿笔记/.test(text) ? '文稿笔记' : '',
    export_available: /导出/.test(text),
    target_bound: true,
    modal_visible: visible(modal),
    modal_template_count: templateRows.length,
    modal_selected_templates: selectedTitles,
    modal_submit_button_matches: submitButtons.length
  };
})()""",
)


_PREPARE_AI_NOTE = NetdiskOpenCliTemplate(
    name="prepare_ai_note",
    parameters=("expected_path",),
    source=r"""(async () => {
  const template_name = 'baidu-netdisk/prepare-ai-note';
  const template_version = 1;
  const expectedPath = __EXPECTED_PATH__;
  const currentUrl = new URL(location.href);
  const target_bound = currentUrl.origin === 'https://pan.baidu.com'
    && currentUrl.pathname === '/pfile/video'
    && currentUrl.searchParams.getAll('path').length === 1
    && currentUrl.searchParams.get('path') === expectedPath;
  if (!target_bound) {
    return {
      template_name,
      template_version,
      scheduled: false,
      template_no: 1,
      target_bound: false,
      click_dispatched: false
    };
  }
  const frame = document.getElementById('noteIframe');
  if (!frame) {
    return {
      template_name,
      template_version,
      scheduled: false,
      template_no: 1,
      target_bound: true,
      note_iframe_present: false,
      click_dispatched: false
    };
  }
  const visible = node => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  window.postMessage({type: 'previewTemplate', data: {tpl_no: 1}}, '*');
  const deadline = Date.now() + 12000;
  let templateMatches = [];
  let selected = false;
  let buttonMatches = [];
  let rowClickDispatched = false;
  while (Date.now() < deadline) {
    const liveUrl = new URL(location.href);
    const stillTargetBound = liveUrl.origin === 'https://pan.baidu.com'
      && liveUrl.pathname === '/pfile/video'
      && liveUrl.searchParams.getAll('path').length === 1
      && liveUrl.searchParams.get('path') === expectedPath;
    if (!stillTargetBound) {
      return {
        template_name,
        template_version,
        scheduled: false,
        template_no: 1,
        target_bound: false,
        click_dispatched: false
      };
    }
    const modal = document.getElementById('tplModal');
    const modalDocument = modal?.contentDocument;
    const rows = modalDocument
      ? [...modalDocument.querySelectorAll(
          '.wp-ainoteTpl__left__list__item'
        )]
      : [];
    templateMatches = rows.filter(row => (
      visible(row)
      && (row.querySelector(
        '.wp-ainoteTpl__left__list__item__title'
      )?.textContent || '').trim() === '文稿笔记'
    ));
    if (templateMatches.length === 1) {
      selected = !!templateMatches[0].querySelector('.selected');
      if (!selected && !rowClickDispatched) {
        templateMatches[0].click();
        rowClickDispatched = true;
      }
    }
    buttonMatches = modalDocument
      ? [...modalDocument.querySelectorAll('button')].filter(node => (
          visible(node)
          && !node.disabled
          && (node.textContent || '').trim() === '生成该笔记'
        ))
      : [];
    if (
      visible(modal)
      && templateMatches.length === 1
      && selected
      && buttonMatches.length === 1
    ) {
      return {
        template_name,
        template_version,
        scheduled: true,
        template_no: 1,
        target_bound: true,
        modal_ready: true,
        template_matches: 1,
        template_selected: '文稿笔记',
        button_matches: 1,
        row_click_dispatched: rowClickDispatched,
        click_dispatched: false
      };
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return {
    template_name,
    template_version,
    scheduled: false,
    template_no: 1,
    target_bound: true,
    modal_ready: false,
    template_matches: templateMatches.length,
    template_selected: selected ? '文稿笔记' : '',
    button_matches: buttonMatches.length,
    row_click_dispatched: rowClickDispatched,
    click_dispatched: false
  };
})()""",
)


_SUBMIT_AI_NOTE = NetdiskOpenCliTemplate(
    name="submit_ai_note",
    parameters=("expected_path",),
    source=r"""(async () => {
  const template_name = 'baidu-netdisk/submit-ai-note';
  const template_version = 1;
  const expectedPath = __EXPECTED_PATH__;
  const currentUrl = new URL(location.href);
  const target_bound = currentUrl.origin === 'https://pan.baidu.com'
    && currentUrl.pathname === '/pfile/video'
    && currentUrl.searchParams.getAll('path').length === 1
    && currentUrl.searchParams.get('path') === expectedPath;
  if (!target_bound) {
    return {
      template_name,
      template_version,
      submitted: false,
      template_no: 1,
      target_bound: false,
      click_dispatched: false
    };
  }
  const visible = node => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const modal = document.getElementById('tplModal');
  const modalDocument = modal?.contentDocument;
  const rows = modalDocument
    ? [...modalDocument.querySelectorAll(
        '.wp-ainoteTpl__left__list__item'
      )]
    : [];
  const templateMatches = rows.filter(row => (
    visible(row)
    && (row.querySelector(
      '.wp-ainoteTpl__left__list__item__title'
    )?.textContent || '').trim() === '文稿笔记'
  ));
  const templateSelected = templateMatches.length === 1
    && !!templateMatches[0].querySelector('.selected');
  const buttonMatches = modalDocument
    ? [...modalDocument.querySelectorAll('button')].filter(node => (
        visible(node)
        && !node.disabled
        && (node.textContent || '').trim() === '生成该笔记'
      ))
    : [];
  if (
    !visible(modal)
    || templateMatches.length !== 1
    || !templateSelected
    || buttonMatches.length !== 1
  ) {
    return {
      template_name,
      template_version,
      submitted: false,
      template_no: 1,
      target_bound: true,
      modal_ready: false,
      template_matches: templateMatches.length,
      template_selected: templateSelected ? '文稿笔记' : '',
      button_matches: buttonMatches.length,
      click_dispatched: false
    };
  }
  buttonMatches[0].click();
  return {
    template_name,
    template_version,
    submitted: true,
    template_no: 1,
    target_bound: true,
    modal_ready: true,
    template_matches: 1,
    template_selected: '文稿笔记',
    button_matches: 1,
    click_dispatched: true,
    modal_visible: visible(document.getElementById('tplModal')),
    confirmed_state: 'dispatched',
    content_chars: 0
  };
})()""",
)


_TEMPLATES = {
    template.name: template
    for template in (
        _PROBE_TRANSCRIPT,
        _PROBE_AI_NOTE,
        _PREPARE_AI_NOTE,
        _SUBMIT_AI_NOTE,
    )
}


def netdisk_opencli_template_names() -> tuple[str, ...]:
    return tuple(sorted(_TEMPLATES))


def render_netdisk_opencli_template(name: str, **values: Any) -> str:
    try:
        template = _TEMPLATES[name]
    except KeyError as exc:
        raise ValueError(f"unknown Netdisk OpenCLI template: {name}") from exc
    return template.render(**values)
