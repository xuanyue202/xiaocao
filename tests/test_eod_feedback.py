from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from xiaocao.research import eod_feedback as feedback
from xiaocao.research import weekly_evidence
from xiaocao.live.eod_closeout import closeout

DAY = '2026-10-26'
OWNER = 'original-eod-thread'
ENV = {'CODEX_AUTOMATION_ID': feedback.AUTOMATION_ID, 'CODEX_THREAD_ID': OWNER}


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return feedback.evidence_ref(root, path)


def daily(root, day=DAY):
    ref = write(root, 'output/dated-fact.json', {'observed': 'accounting pending'})
    return dict(schema_version=1, authority=0, date=day,
        automation_id=feedback.AUTOMATION_ID, thread_id=OWNER,
        evidence={'fact': ref}, items=[dict(id='stable-timing-defect', kind='issue', status='repaired',
            summary='Delayed final digest', owner='daily EOD', next_action='verify original next run',
            next_verification='next legal EOD', falsifier='digest precedes APP terminal', basis='observed',
            evidence_refs=[ref])])


def captured(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in (root / 'output/live/review_feedback').rglob('*') if p.is_file()}


def test_daily_immutable_idempotent_and_snapshots_survive_source_changes(tmp_path):
    value = daily(tmp_path)
    path = feedback.record_daily(tmp_path, value)
    original = path.read_bytes()
    assert feedback.record_daily(tmp_path, value) == path
    (tmp_path / 'output/dated-fact.json').write_text('changed')
    observed = feedback.observe_feedback(captured(tmp_path), as_of=dt.date(2026, 11, 27))
    assert observed['items'][0]['id'] == 'stable-timing-defect'
    assert observed['errors'] == []
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match='MISMATCH'):
        feedback.record_daily(tmp_path, value)


def test_repeated_identity_retains_history_future_excluded_and_natural_proof_required(tmp_path):
    first = daily(tmp_path)
    feedback.record_daily(tmp_path, first)
    second = daily(tmp_path, '2026-10-27')
    feedback.record_daily(tmp_path, second)
    observed = feedback.observe_feedback(captured(tmp_path), as_of=dt.date(2026, 10, 27))
    assert len(observed['items']) == 1
    assert observed['items'][0]['observations'] == 2
    assert observed['items'][0]['first_seen'] == DAY
    assert feedback.observe_feedback(captured(tmp_path), as_of=dt.date(2026, 10, 26))['items'][0]['observations'] == 1
    third = daily(tmp_path, '2026-10-28')
    third['items'][0]['status'] = 'verified'
    with pytest.raises(ValueError, match='NATURAL_VERIFICATION'):
        feedback.record_daily(tmp_path, third)
    third['items'][0]['status'] = 'repaired'
    third['items'][0]['summary'] = 'conflicting same-day final review'
    third['date'] = DAY
    with pytest.raises(ValueError, match='DAY_ALREADY_RECORDED'):
        feedback.record_daily(tmp_path, third)


def test_zero_fill_or_incomparable_experiment_cannot_claim_success(tmp_path):
    value = daily(tmp_path)
    item = value['items'][0]
    item.update(kind='experiment', effective_samples=0, sample_unit='filled funded path', comparable=True,
                status='observed')
    with pytest.raises(ValueError, match='INSUFFICIENT_SAMPLES'):
        feedback.record_daily(tmp_path, value)
    item['status'] = 'insufficient_evidence'
    assert feedback.record_daily(tmp_path, value).is_file()


def weekly_plan(root):
    feedback.record_daily(root, daily(root))
    review = weekly_evidence.build_weekly_evidence(root, as_of=dt.date(2026, 10, 30), snapshot_dir=root / 'frozen')
    return {'date': '2026-10-30', 'data_evidence_review': review}


def response(plan):
    item = plan['data_evidence_review']['eod_feedback']['items'][0]
    return dict(id=item['id'], disposition='verify', rationale='tests do not prove deployment',
                owner='daily EOD', next_action='read next natural archive', next_review='2026-11-02',
                evidence_refs=[item['daily_receipt']])


def test_weekly_frozen_handoff_requires_each_response_and_round_trips(tmp_path):
    plan = weekly_plan(tmp_path)
    assert weekly_evidence.verify_snapshots(plan['data_evidence_review']) == []
    with pytest.raises(ValueError, match='COVERAGE'):
        feedback.weekly_response_state(plan)
    plan['eod_feedback_responses'] = [response(plan)]
    state = feedback.weekly_response_state(plan)
    # Both the live source and daily handoff can change after inventory freeze.
    (tmp_path / 'output/dated-fact.json').write_text('changed')
    (tmp_path / 'output/live/review_feedback/daily/2026-10-26.json').write_text('{}')
    assert feedback.weekly_response_state(plan) == state
    contents = captured(tmp_path)
    daily_path = 'output/live/review_feedback/daily/2026-10-26.json'
    frozen = next(r for r in plan['data_evidence_review']['input_manifest']['files'] if r['path'] == daily_path)
    contents[daily_path] = Path(frozen['snapshot_path']).read_bytes()
    contents[feedback.WEEKLY_LEDGER] = feedback.canonical({'date': '2026-10-30', 'eod_feedback_state': state})
    observed = feedback.observe_feedback(contents, as_of=dt.date(2026, 11, 6))
    assert observed['items'][0]['prior_weekly_response']['owner'] == 'daily EOD'
    plan['eod_feedback_responses'][0]['disposition'] = 'close'
    with pytest.raises(ValueError, match='NOT_NATURALLY_VERIFIED'):
        feedback.weekly_response_state(plan)


def test_weekly_cannot_omit_observations_or_use_live_uncaptured_proof(tmp_path):
    plan = weekly_plan(tmp_path)
    plan['eod_feedback_responses'] = [response(plan)]
    plan['data_evidence_review']['eod_feedback']['items'] = []
    with pytest.raises(ValueError, match='FROZEN_REVIEW_MISMATCH'):
        feedback.weekly_response_state(plan)
    plan = weekly_plan(tmp_path)
    plan['eod_feedback_responses'] = [response(plan)]
    plan['eod_feedback_responses'][0]['evidence_refs'] = [{'path': 'absent', 'sha256': 'unbound'}]
    with pytest.raises(ValueError, match='EVIDENCE_UNBOUND'):
        feedback.weekly_response_state(plan)


def original_closeout(root):
    value = daily(root)
    account = {'receipt_sha256': 'a' * 64, 'cumulative_pnl': None, 'fee_status': 'pending',
               'valuation_status': 'dated_observation'}
    identity = dict(automation_id=feedback.AUTOMATION_ID, thread_id=OWNER, trade_date=DAY)
    facts = {
        'paper_terminal': ('output/auto/original/terminal.json', dict(automation='eod', market_date=DAY,
            process_exit_code=0, terminal_reason='completed', deterministic_status='succeeded', run_id='original')),
        'paper_manifest': ('output/auto/original/manifest.json', dict(identity, run_id='original', market_date=DAY)),
        'app_eod': ('output/app/archive/original.json', dict(phase='eod', trade_date=DAY, status='observed',
            automation_identity=identity, account={'accounting': account}, reason='ACCOUNTING_PENDING')),
        'statement': ('output/accounting/statement.json', dict(schema_version='book-b-statement.v2', source_observation=account)),
        'research': ('output/audit/research.log', dict(authority=0, phase='eod', status='observed')),
        'feedback': ('output/audit/feedback.log', dict(status='audited')),
        'daily_review': ('output/audit/review.md', {'reviewed': True}),
    }
    value['evidence'] = {role: write(root, name, data) for role, (name, data) in facts.items()}
    from xiaocao.live.eod_post_business import COMMANDS
    value['evidence']['statement_stdout'] = write(root, 'output/audit/statement.log',
        {'report_path': str(root / value['evidence']['statement']['path'])})
    for step, command in COMMANDS.items():
        stdout = value['evidence']['statement_stdout' if step == 'statement' else step]
        value['evidence'][step + '_terminal'] = write(root, 'output/audit/' + step + '-terminal.json',
            dict(schema_version=1, automation_id=feedback.AUTOMATION_ID, thread_id=OWNER,
                 date=DAY, step=step, command=command, started_at=DAY + 'T15:16:00+08:00',
                 finished_at=DAY + 'T15:17:00+08:00', exit_code=0, stdout=stdout))
    value['reviewed_at'] = DAY + 'T15:18:00+08:00'
    return value, account


def test_closeout_waits_for_originals_then_records_without_settlement_or_extra_send(tmp_path):
    value, account = original_closeout(tmp_path)
    sent = []
    result = closeout(tmp_path, value, env=ENV,
        build_digest=lambda **kw: {'book_b_app': account, 'market_date': DAY},
        push_digest=lambda d: sent.append(d) or {'delivery': 'delivered'})
    assert sent[0]['book_b_app']['cumulative_pnl'] is None
    assert result['delivery']['delivery'] == 'delivered'
    assert Path(result['daily_feedback']).is_file()
    assert not list(tmp_path.rglob('*settlement*'))


@pytest.mark.parametrize('fault', ['identity', 'paper', 'app', 'statement', 'hash', 'latest_observation', 'feedback'])
def test_closeout_blocks_before_record_or_send_on_missing_terminal_or_changed_evidence(tmp_path, fault):
    value, account = original_closeout(tmp_path)
    env = dict(ENV)
    digest = {'book_b_app': account}
    if fault == 'identity':
        env['CODEX_THREAD_ID'] = 'another-owner'
    elif fault == 'hash':
        (tmp_path / value['evidence']['app_eod']['path']).write_text('{}')
    elif fault == 'latest_observation':
        digest['book_b_app'] = {'receipt_sha256': 'another-snapshot'}
    else:
        role = {'paper': 'paper_terminal', 'app': 'app_eod', 'statement': 'statement', 'feedback': 'feedback'}[fault]
        name = value['evidence'][role]['path']
        data = json.loads((tmp_path / name).read_bytes())
        if fault == 'paper': data.pop('process_exit_code')
        elif fault == 'app': data['automation_identity']['thread_id'] = 'another-owner'
        elif fault == 'statement': data['source_observation'] = {'receipt_sha256': 'old'}
        else: data['status'] = 'started'
        value['evidence'][role] = write(tmp_path, name, data)
    with pytest.raises(ValueError):
        closeout(tmp_path, value, env=env, build_digest=lambda **kw: digest,
            push_digest=lambda d: pytest.fail('must not send'))
    assert not (tmp_path / 'output/live/review_feedback/daily').exists()


def test_failed_paper_keeps_daily_evidence_and_blocks_success_digest(tmp_path):
    value, account = original_closeout(tmp_path)
    role = value['evidence']['paper_terminal']['path']
    terminal = json.loads((tmp_path / role).read_bytes())
    terminal['process_exit_code'] = 1
    value['evidence']['paper_terminal'] = write(tmp_path, role, terminal)
    result = closeout(tmp_path, value, env=ENV, build_digest=lambda **kw: {'book_b_app': account},
                      push_digest=lambda d: pytest.fail('must not send a failed paper EOD as normal'))
    assert result['delivery'] == {'delivery': 'blocked', 'reason': 'PAPER_EOD_FAILED'}
    assert Path(result['daily_feedback']).is_file()


def test_new_weekly_contract_cannot_drop_handoff_and_finalizer_writes_no_partial_result(tmp_path, monkeypatch):
    from scripts import weekly_deep_review as weekly
    plan = weekly_plan(tmp_path)
    monkeypatch.setattr(weekly, 'WEEKLY_DIR', tmp_path / 'output/live')
    monkeypatch.setattr(weekly, 'CHANGE_LEDGER', tmp_path / feedback.WEEKLY_LEDGER)
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='RESPONSE_COVERAGE'):
        weekly.finalize_plan(plan_path=path, mode=weekly.MODE_NONE, validation=[], allow_commit=False)
    assert not weekly.CHANGE_LEDGER.exists()
    assert not (weekly.WEEKLY_DIR / 'weekly_review_2026-10-30.md').exists()
    del plan['data_evidence_review']['eod_feedback']
    with pytest.raises(ValueError, match='FROZEN_REVIEW_REQUIRED'):
        feedback.weekly_response_state(plan)
    plan['eod_feedback_contract'] = 1
    del plan['data_evidence_review']
    with pytest.raises(ValueError, match='FROZEN_INVENTORY_REQUIRED'):
        feedback.weekly_response_state(plan)
    plan['data_evidence_review'] = {'status': 'truncated'}
    with pytest.raises(ValueError, match='FROZEN_INVENTORY_REQUIRED'):
        feedback.weekly_response_state(plan)
    plan['data_evidence_review'] = {'input_manifest': {'files': []}}
    with pytest.raises(ValueError, match='FROZEN_REVIEW_REQUIRED'):
        feedback.weekly_response_state(plan)


def test_settled_original_app_is_a_valid_terminal(tmp_path):
    value, account = original_closeout(tmp_path)
    name = value['evidence']['app_eod']['path']
    app = json.loads((tmp_path / name).read_bytes())
    app.update(status='settled', settlement={'status': 'settled'})
    value['evidence']['app_eod'] = write(tmp_path, name, app)
    result = closeout(tmp_path, value, env=ENV, build_digest=lambda **kw: {'book_b_app': account})
    assert result['status'] == 'recorded'
    assert result['delivery']['delivery'] == 'not_requested'


def test_new_facts_reopen_previously_closed_non_issue_beyond_week_window(tmp_path):
    first = daily(tmp_path)
    first['items'][0].update(kind='finding', status='observed')
    feedback.record_daily(tmp_path, first)
    state = dict(schema_version=1, authority=0, date='2026-10-30', responses=[dict(
        id='stable-timing-defect', disposition='close')])
    state['sha256'] = feedback.sha(feedback.canonical(state))
    contents = captured(tmp_path)
    contents[feedback.WEEKLY_LEDGER] = feedback.canonical({'date': '2026-10-30', 'eod_feedback_state': state})
    assert feedback.observe_feedback(contents, as_of=dt.date(2026, 11, 6))['items'] == []
    second = daily(tmp_path, '2026-11-02')
    second['items'][0].update(kind='finding', status='open', summary='Changed execution impact')
    feedback.record_daily(tmp_path, second)
    contents.update(captured(tmp_path))
    reopened = feedback.observe_feedback(contents, as_of=dt.date(2026, 11, 13))
    assert reopened['items'][0]['last_seen'] == '2026-11-02'


@pytest.mark.parametrize('fault', ['wrong_owner', 'prior_day', 'running', 'output', 'early_review'])
def test_closeout_post_command_terminal_is_current_owned_and_hash_bound(tmp_path, fault):
    value, account = original_closeout(tmp_path)
    role = value['evidence']['feedback_terminal']['path']
    receipt = json.loads((tmp_path / role).read_bytes())
    if fault == 'wrong_owner': receipt['thread_id'] = 'other'
    elif fault == 'prior_day': receipt['date'] = '2026-10-25'
    elif fault == 'running': receipt['exit_code'] = None
    elif fault == 'output': receipt['stdout'] = value['evidence']['research']
    else: value['reviewed_at'] = DAY + 'T15:16:30+08:00'
    value['evidence']['feedback_terminal'] = write(tmp_path, role, receipt)
    with pytest.raises(ValueError):
        closeout(tmp_path, value, env=ENV, build_digest=lambda **kw: {'book_b_app': account},
                 push_digest=lambda d: pytest.fail('must wait original post-business terminals'))


def test_post_business_captures_exact_child_exit_and_claim_survives_failure(tmp_path):
    import sys
    from xiaocao.live.eod_post_business import run_step, COMMANDS
    calls = []
    def child(args, *, cwd, env, output_path, stdout_path):
        calls.append(args)
        stdout_path.write_text('{"status":"audited"}')
        output_path.write_text('diagnostic warning\n{"status":"audited"}')
        return 7
    at = dt.datetime.fromisoformat(DAY + 'T15:17:00+08:00')
    result = run_step(tmp_path, 'feedback', env=ENV, runner=child, clock=lambda: at)
    terminal = json.loads(Path(result['terminal_path']).read_bytes())
    assert terminal['exit_code'] == 7
    assert terminal['thread_id'] == OWNER
    assert terminal['command'] == COMMANDS['feedback']
    assert calls == [[sys.executable, *COMMANDS['feedback']]]
    with pytest.raises(FileExistsError):
        run_step(tmp_path, 'feedback', env=ENV, runner=child, clock=lambda: at)
    assert len(calls) == 1
    with pytest.raises(ValueError, match='IDENTITY_OR_WINDOW'):
        run_step(tmp_path, 'research', env={**ENV, 'CODEX_AUTOMATION_ID': 'other'}, runner=child, clock=lambda: at)
    assert len(calls) == 1


def test_post_business_real_child_warning_does_not_corrupt_json_stdout(tmp_path):
    import os
    import sys
    from xiaocao.live.runtime_evidence import stream_process
    stdout = tmp_path / 'stdout.log'
    console = tmp_path / 'console.log'
    result = stream_process([sys.executable, '-c',
        'import sys; print("{\\\"status\\\":\\\"audited\\\"}"); sys.stderr.write("warning\\n")'],
        cwd=tmp_path, env=dict(os.environ), output_path=console, stdout_path=stdout)
    assert result == 0
    assert json.loads(stdout.read_text()) == {'status': 'audited'}
    assert 'warning' in console.read_text()


@pytest.mark.parametrize('missing_mode', ['absent', 'corrupt', 'legacy_state'])
def test_missing_daily_keeps_unresolved_weekly_owner_and_requires_gap_response(tmp_path, missing_mode):
    plan = weekly_plan(tmp_path)
    plan['eod_feedback_responses'] = [response(plan)]
    state = feedback.weekly_response_state(plan)
    if missing_mode == 'legacy_state':
        state.pop('reviewed_items')
        state.pop('sha256')
        state['sha256'] = feedback.sha(feedback.canonical(state))
    ledger = tmp_path / feedback.WEEKLY_LEDGER
    original_ledger = feedback.canonical({'date': '2026-10-30', 'eod_feedback_state': state}) + b'\n'
    ledger.write_bytes(original_ledger)
    daily_path = tmp_path / 'output/live/review_feedback/daily/2026-10-26.json'
    if missing_mode == 'corrupt':
        daily_path.write_text('{"incomplete":')
    else:
        daily_path.unlink()
    observed = weekly_evidence.build_weekly_evidence(tmp_path, as_of=dt.date(2026, 11, 6),
                                                    snapshot_dir=tmp_path / 'next_frozen')
    next_plan = {'date': '2026-11-06', 'eod_feedback_contract': 1, 'data_evidence_review': observed}
    review = observed['eod_feedback']
    assert review['status'] == 'evidence_gap'
    assert review['items'][0]['id'] == 'stable-timing-defect'
    assert review['items'][0]['owner'] == 'daily EOD'
    assert review['items'][0]['status'] == 'evidence_gap'
    assert ledger.read_bytes() == original_ledger
    assert weekly_evidence.verify_snapshots(observed) == []
    with pytest.raises(ValueError, match='GAPS_REQUIRE_EXPLANATION'):
        feedback.weekly_response_state(next_plan)
    next_plan['eod_feedback_gap_review'] = 'Original daily receipt missing; keep owner and recover exact evidence.'
    with pytest.raises(ValueError, match='RESPONSE_COVERAGE'):
        feedback.weekly_response_state(next_plan)
    next_plan['eod_feedback_responses'] = [dict(id='stable-timing-defect', disposition='needs_evidence',
        rationale='Do not infer original repair status from a surviving weekly response', owner='daily EOD',
        next_action='Locate original receipt or collect independent new evidence', next_review='2026-11-09',
        evidence_refs=[{'path': feedback.WEEKLY_LEDGER, 'sha256': feedback.sha(original_ledger)}])]
    assert feedback.weekly_response_state(next_plan)['evidence_gaps']
    next_plan['eod_feedback_responses'][0]['disposition'] = 'close'
    with pytest.raises(ValueError, match='ORIGINAL_ITEM_REQUIRED'):
        feedback.weekly_response_state(next_plan)


@pytest.mark.parametrize('research_output', [
    {'status': 'not_started', 'authority': 0, 'reports': {'status': 'reported', 'authority': 0}},
    {'status': 'NON_TRADING_DAY', 'authority': 0},
])
def test_supported_no_action_research_terminal_does_not_block_completed_closeout(tmp_path, research_output):
    value, account = original_closeout(tmp_path)
    name = value['evidence']['research']['path']
    value['evidence']['research'] = write(tmp_path, name, research_output)
    terminal_name = value['evidence']['research_terminal']['path']
    terminal = json.loads((tmp_path / terminal_name).read_bytes())
    terminal['stdout'] = value['evidence']['research']
    value['evidence']['research_terminal'] = write(tmp_path, terminal_name, terminal)
    sent = []
    result = closeout(tmp_path, value, env=ENV, build_digest=lambda **kw: {'book_b_app': account},
                      push_digest=lambda d: sent.append(d) or {'delivery': 'delivered'})
    assert result['research_status'] == research_output['status']
    assert result['delivery']['delivery'] == 'delivered' and len(sent) == 1
    saved = json.loads(Path(result['daily_feedback']).read_bytes())
    assert saved['research_status'] == research_output['status']
    assert saved['digest']['book_b_app']['cumulative_pnl'] is None


@pytest.mark.parametrize('research_output', [
    {'status': 'not_started', 'authority': 0},
    {'status': 'already_consumed', 'authority': 0},
    {'status': 'blocked', 'phase': 'eod', 'authority': 0},
])
def test_unsupported_research_output_still_blocks_before_send(tmp_path, research_output):
    value, account = original_closeout(tmp_path)
    name = value['evidence']['research']['path']
    value['evidence']['research'] = write(tmp_path, name, research_output)
    terminal_name = value['evidence']['research_terminal']['path']
    terminal = json.loads((tmp_path / terminal_name).read_bytes())
    terminal['stdout'] = value['evidence']['research']
    value['evidence']['research_terminal'] = write(tmp_path, terminal_name, terminal)
    with pytest.raises(ValueError, match='RESEARCH_NOT_TERMINAL'):
        closeout(tmp_path, value, env=ENV, build_digest=lambda **kw: {'book_b_app': account},
                 push_digest=lambda d: pytest.fail('unknown/failed result must not send'))


def test_missing_newer_reopened_item_cannot_close_using_surviving_old_verification(tmp_path):
    first = daily(tmp_path)
    test_ref = write(tmp_path, 'output/old-tests.json', {'result': 'passed'})
    natural_ref = write(tmp_path, 'output/old-natural.json', {'observed': 'accepted'})
    first['items'][0].update(status='verified', evidence_refs=[test_ref, natural_ref],
        verification={'code_commit': 'a' * 40, 'tests': [test_ref], 'natural': [natural_ref]})
    feedback.record_daily(tmp_path, first)
    newer = daily(tmp_path, '2026-10-27')
    feedback.record_daily(tmp_path, newer)
    initial = weekly_evidence.build_weekly_evidence(tmp_path, as_of=dt.date(2026, 10, 30),
                                                   snapshot_dir=tmp_path / 'initial_frozen')
    plan = {'date': '2026-10-30', 'data_evidence_review': initial}
    plan['eod_feedback_responses'] = [response(plan)]
    state = feedback.weekly_response_state(plan)
    write(tmp_path, feedback.WEEKLY_LEDGER, {'date': '2026-10-30', 'eod_feedback_state': state})
    (tmp_path / 'output/live/review_feedback/daily/2026-10-27.json').unlink()
    latest = weekly_evidence.build_weekly_evidence(tmp_path, as_of=dt.date(2026, 11, 6),
                                                  snapshot_dir=tmp_path / 'latest_frozen')
    item = latest['eod_feedback']['items'][0]
    assert item['status'] == 'evidence_gap'
    assert item['last_proved_daily']['status'] == 'verified'
    plan = dict(date='2026-11-06', data_evidence_review=latest,
        eod_feedback_gap_review='The reopened receipt is missing; old natural proof is stale.',
        eod_feedback_responses=[dict(id=item['id'], disposition='close', rationale='old verification survives',
            owner='daily EOD', next_action='verify original missing evidence', next_review='2026-11-09',
            evidence_refs=[latest['eod_feedback']['receipts'][0]])])
    with pytest.raises(ValueError, match='ORIGINAL_ITEM_REQUIRED'):
        feedback.weekly_response_state(plan)
