"""Offline preparation/producer adoption; no APP adapter or engineering orders."""
import copy
import json
import pytest

from tests.test_kol_opening_preparation import case, accept, save, NOW
from tests.test_kol_selection import row, preference
from xiaocao.kol import opening_preparation as prep, selection_preview as preview
from xiaocao.runner_recovery import _hash


def prepared(case, monkeypatch):
    binding = case['inputs']['binding']
    binding.update(automation_id='xiaocao-book-b-live-morning', owner_thread_id='owner')
    save(case['path'], case['inputs'])
    case['draft'].update(input_sha256=_hash(case['inputs']), selection_preferences=[
        preference('mode', {'mode':'B'}, source_report_id='r', source_quote='source')])
    case['dispatch'].update(binding=binding, input_sha256=_hash(case['inputs']))
    case['review'].update(selection_preferences_reviewed=True,
        draft_sha256=prep.canonical_sha256(case['draft']),
        dispatch_sha256=prep.canonical_sha256(case['dispatch']))
    value = accept(case)
    path = save(case['root']/'prepared.json', value)
    monkeypatch.setenv('CODEX_AUTOMATION_ID', binding['automation_id'])
    monkeypatch.setenv('CODEX_THREAD_ID', 'owner')
    preview.register_preparation(case['path'].resolve(), path, value)
    return value


def test_accepted_preference_changes_producer_recommendation_and_preserves_freeze(case, monkeypatch):
    value = prepared(case, monkeypatch)
    rows = [row('000001.XSHE','A',1),row('000002.XSHE','B',4)]
    for item in rows: item['date']=value['binding']['trade_date']
    before=copy.deepcopy(rows)
    freeze={'market_date':value['binding']['trade_date'],'snapshot_sha256':'a'*64}
    result=preview.preview(rows,freeze,root=case['root'],now=NOW,
        fingerprint_reader=lambda *a:value['source_fingerprint'])
    assert result['status']=='prepared_preview' and result['selected_codes'][0]=='000002.XSHE'
    assert result['authority']==0 and result['policy_adoption']=='not_performed'
    assert rows==before and '000002.XSHE' in preview.render(result)


def test_changed_sources_preserve_baseline_with_explicit_degradation(case, monkeypatch):
    value=prepared(case,monkeypatch)
    rows=[{**row('000001.XSHE','A',1),'date':value['binding']['trade_date']}]
    result=preview.preview(rows,{'market_date':value['binding']['trade_date'],'snapshot_sha256':'a'*64},
        root=case['root'],now=NOW,fingerprint_reader=lambda *a:'changed')
    assert result['status']=='degraded' and result['reason']=='PREPARATION_SOURCE_CHANGED'
    assert result['selected_codes']==result['baseline_codes']==['000001.XSHE']


def test_preference_requires_source_quote_and_independent_review(case):
    case['draft']['selection_preferences']=[preference('mode',{'mode':'B'}, source_report_id='r',source_quote='source')]
    case['review']['draft_sha256']=prep.canonical_sha256(case['draft'])
    with pytest.raises(ValueError,match='SELECTION_REVIEW'):accept(case)
    case['review']['selection_preferences_reviewed']=True
    case['draft']['selection_preferences'][0]['source_quote']='invented quotation'
    case['review']['draft_sha256']=prep.canonical_sha256(case['draft'])
    with pytest.raises(ValueError,match='SOURCE_QUOTE'):accept(case)


def test_preview_missing_preparation_is_prompt_baseline_without_source_work(tmp_path):
    def forbidden(*a):raise AssertionError('no source work without accepted preferences')
    result=preview.preview([],{'market_date':'2026-10-23','snapshot_sha256':'a'*64},root=tmp_path,
        now=NOW,fingerprint_reader=forbidden)
    assert result['status']=='baseline' and result['selected_codes']==[]


def test_accept_command_registers_source_before_app_checklist_completion(case, monkeypatch):
    from scripts import kol_trading_prepare as cli
    binding = case['inputs']['binding']
    binding.update(automation_id='xiaocao-book-b-live-morning', owner_thread_id='owner')
    save(case['path'], case['inputs'])
    case['draft']['input_sha256'] = _hash(case['inputs'])
    case['dispatch'].update(binding=binding, input_sha256=_hash(case['inputs']))
    case['review'].update(draft_sha256=prep.canonical_sha256(case['draft']),
                         dispatch_sha256=prep.canonical_sha256(case['dispatch']))
    class Clock:
        @classmethod
        def now(cls, tz):
            return NOW.astimezone(tz)
    monkeypatch.setattr(cli, 'datetime', Clock)
    monkeypatch.setenv('CODEX_AUTOMATION_ID', binding['automation_id'])
    monkeypatch.setenv('CODEX_THREAD_ID', 'owner')
    arguments = ['accept', '--root', str(case['root']), '--input', str(case['path']),
                 '--output-dir', str(case['root'] / 'accepted')]
    for name in ('draft', 'dispatch', 'review', 'context'):
        arguments.extend(['--' + name, str(save(case['root'] / (name + '.json'), case[name]))])
    assert cli.main(arguments) == 0
    _, value = preview.registered_preparation(case['root'], binding['trade_date'], now=NOW)
    assert value['input_sha256'] == _hash(case['inputs'])
    assert value['authority'] == 0
