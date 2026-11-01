"""Acceptance observes the original business; it cannot manufacture adoption."""
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from xiaocao.automation_run import automation_run, runner_identity
from xiaocao.runner_recovery import _hash
from xiaocao.live.incident_dispositions import consume
from xiaocao.live.morning_acceptance import record_repair_acceptance, read_repair_acceptance
from xiaocao.live.morning_checklist import MorningChecklist

pytestmark = pytest.mark.app_simulation
DAY = '2026-11-02'
AUTOMATION = 'xiaocao-book-b-live-morning'


@contextmanager
def original(tmp_path, monkeypatch, *, engineering=False, stage='execution'):
    monkeypatch.setenv('CODEX_AUTOMATION_ID', AUTOMATION)
    monkeypatch.setenv('CODEX_THREAD_ID', 'original-test-owner')
    monkeypatch.setattr('xiaocao.live.app_test_window.app_test_context_active', lambda: engineering)
    monkeypatch.setattr('xiaocao.live.morning_acceptance.app_test_context_active', lambda: engineering)
    root = tmp_path / 'book_b_live_execution'
    root.mkdir()
    with automation_run(AUTOMATION, DAY, root=tmp_path / 'locks'):
        identity = runner_identity(AUTOMATION, 'scripts/book_b_live_morning.py')
        deadline = DAY + 'T09:35:00+08:00'
        binding = {**identity, 'trade_date': DAY, 'preparation_deadline': deadline}
        checklist = MorningChecklist.create(root / 'runs/checklists', binding)
        from datetime import datetime
        checklist.record('account_risk', 'passed', evidence={'allocation_capsule_sha256': 'a' * 64},
                         observed_at=datetime.fromisoformat(DAY + 'T09:25:00+08:00'))
        run_id = DAY + '-original'
        consumption = consume(root, trade_date=DAY, run_id=run_id,
                              now=datetime.fromisoformat(DAY + 'T09:00:00+08:00'))
        receipt = {'run_id': run_id, 'trade_date': DAY, 'state_path': str(root.resolve()),
            'runner_identity': identity, 'preparation_deadline': deadline,
            'checklist_path': str(checklist.path), 'inherited_incidents': consumption,
            'deferred_prior_day_buy_plan_ids': ['historical-unknown'], 'execution_receipts': [],
            'stage_times': {stage: DAY + 'T09:25:00+08:00'},
            'status': 'no_action' if stage == 'execution' else 'blocked',
            'reason': 'RISK_OR_SELECTION_ZERO' if stage == 'execution' else 'CURRENT_DEPENDENCY'}
        path = root / 'runs/history' / (run_id + '.json')
        path.parent.mkdir()
        path.write_text(json.dumps(receipt))
        yield root, path, receipt, checklist


def test_original_lock_and_immutable_observations_prove_actual_consumer_path(tmp_path, monkeypatch):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        before = path.read_bytes()
        ref = record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        assert ref['natural_run_observed'] and ref['incident_consumption'] == 'observed'
        assert ref['independent_admission'] == 'current_admission_reached'
        assert record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt)) == ref
        accepted = read_repair_acceptance(root, path)
        facts = accepted['facts']
        assert accepted['status'] == 'observed'
        assert facts['business_status'] == receipt['status'] and facts['business_reason'] == receipt['reason']
        assert facts['admission_authority'] == 'none' and facts['broker_actions'] == 0
        assert facts['execution_states'] == [] and not (root / 'events.jsonl').exists()
        assert path.read_bytes() == before


def test_engineering_execution_never_becomes_natural_acceptance(tmp_path, monkeypatch):
    with original(tmp_path, monkeypatch, engineering=True) as (root, path, receipt, _):
        result = record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        assert result['natural_run_observed'] is False
        assert result['incident_consumption'] == 'unproved'


def test_environment_identity_without_the_held_original_lock_cannot_record_acceptance(tmp_path, monkeypatch):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        pass
    with pytest.raises(ValueError, match='ORIGINAL_OWNER_REQUIRED'):
        record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
    assert not (root / 'runs/repair_acceptance').exists()


@pytest.mark.parametrize('fault', ['consumption-hash', 'consumption-other-run', 'consumption-other-owner', 'account-observation'])
def test_bad_supporting_evidence_never_accepts_a_branch(tmp_path, monkeypatch, fault):
    with original(tmp_path, monkeypatch) as (root, path, receipt, checklist):
        if fault.startswith('consumption'):
            ref = receipt['inherited_incidents']
            evidence = Path(ref['path'])
            body = json.loads(evidence.read_text())
            if fault == 'consumption-other-run':
                body['run_id'] = DAY + '-another'
            elif fault == 'consumption-other-owner':
                body['dated_lock_owner']['thread_id'] = 'another-owner'
            else:
                body['accepted_handoff'] = False
            evidence.write_text(json.dumps(body))
            if fault != 'consumption-hash':
                import hashlib
                ref['sha256'] = hashlib.sha256(evidence.read_bytes()).hexdigest()
                path.write_text(json.dumps(receipt))
        else:
            observation = Path(checklist.read()['items']['account_risk']['observation_path'])
            observation.write_text('{}')
        result = record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        if fault.startswith('consumption'):
            assert result['incident_consumption'] == 'unproved'
        else:
            assert result['independent_admission'] == 'not_reached_or_unproved'


def test_early_block_and_unexercised_cases_keep_the_actual_business_result(tmp_path, monkeypatch):
    with original(tmp_path, monkeypatch, stage='preflight') as (root, path, receipt, _):
        ref = record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        assert ref['independent_admission'] == 'not_reached_or_unproved'
        assert read_repair_acceptance(root, path)['facts']['business_reason'] == 'CURRENT_DEPENDENCY'


def test_later_archive_change_invalidates_acceptance_without_rewriting_either(tmp_path, monkeypatch):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        ref = record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        audit = Path(ref['path']).read_bytes()
        receipt['reason'] = 'different-original-result'
        path.write_text(json.dumps(receipt))
        assert read_repair_acceptance(root, path)['status'] == 'unproved'
        assert Path(ref['path']).read_bytes() == audit


@pytest.mark.parametrize('fault', ['environment', 'exact-plan-recovery'])
def test_changed_identity_or_exact_plan_recovery_cannot_claim_fresh_adoption(tmp_path, monkeypatch, fault):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        if fault == 'environment':
            monkeypatch.setenv('CODEX_THREAD_ID', 'another-thread')
        else:
            receipt['recovery_of'] = 'old-exact-plan'
            path.write_text(json.dumps(receipt))
        with pytest.raises(ValueError, match='ORIGINAL_OWNER_REQUIRED'):
            record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))


@pytest.mark.parametrize('stamp', ['not-a-time', '2026-11-01T09:25:00+08:00', '2026-11-02T09:25:00'])
def test_undated_or_other_day_stage_does_not_prove_current_admission(tmp_path, monkeypatch, stamp):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        receipt['stage_times']['execution'] = stamp
        path.write_text(json.dumps(receipt))
        assert record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))['independent_admission'] == 'not_reached_or_unproved'


def test_no_deferred_incident_is_an_unexercised_case_not_an_isolation_pass(tmp_path, monkeypatch):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        receipt['deferred_prior_day_buy_plan_ids'] = []
        path.write_text(json.dumps(receipt))
        assert record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))['independent_admission'] == 'not_exercised'


def test_real_pipeline_reads_only_acceptance_bound_to_its_original_archive(tmp_path, monkeypatch):
    from xiaocao.live.morning_pipeline import pipeline_status
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        terminal = pipeline_status(root.parent, DAY)['app'][0]['terminal_receipts'][0]
        assert terminal['repair_acceptance']['status'] == 'observed'
        assert terminal['status'] == receipt['status']
        receipt['reason'] = 'changed-source'
        path.write_text(json.dumps(receipt))
        terminal = pipeline_status(root.parent, DAY)['app'][0]['terminal_receipts'][0]
        assert terminal['repair_acceptance']['status'] == 'unproved'
        assert terminal['reason'] == 'changed-source'


def test_archive_changed_before_first_audit_cannot_replace_the_original_business_seal(tmp_path, monkeypatch):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        changed = {**receipt, 'status': 'completed', 'reason': 'changed-before-audit'}
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match='SEALED_RECEIPT_CHANGED'):
            record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))


@pytest.mark.parametrize('source', ['consumption', 'account', 'disposition'])
@pytest.mark.parametrize('change', ['delete', 'modify'])
def test_readback_revalidates_the_recorded_immutable_supporting_sources(tmp_path, monkeypatch, source, change):
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        ref = record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        audit = json.loads(Path(ref['path']).read_text())
        key = 'current_account_observation' if source == 'account' else 'incident_consumption'
        evidence = Path(audit[key]['evidence']['path'])
        if source == 'disposition':
            evidence = Path(json.loads(evidence.read_text())['current_ref']['path'])
        if change == 'delete':
            evidence.unlink()
        else:
            evidence.write_text('{}')
        assert read_repair_acceptance(root, path)['status'] == 'unproved'


def test_later_checklist_observation_does_not_replace_the_bound_original_source(tmp_path, monkeypatch):
    from datetime import datetime
    with original(tmp_path, monkeypatch) as (root, path, receipt, checklist):
        ref = record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        original_facts = json.loads(Path(ref['path']).read_text())['current_account_observation']
        checklist.record('account_risk', 'degraded', evidence={'new': 'later-check'},
                         observed_at=datetime.fromisoformat(DAY + 'T09:34:00+08:00'))
        readback = read_repair_acceptance(root, path)
        assert readback['status'] == 'observed'
        assert readback['facts']['current_account_observation'] == original_facts


def test_missing_audit_module_cannot_hide_the_pipeline_business_receipt(tmp_path, monkeypatch):
    import builtins
    from xiaocao.live.morning_pipeline import pipeline_status
    with original(tmp_path, monkeypatch) as (root, path, receipt, _):
        record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        original_import = builtins.__import__
        def missing_audit(name, *args, **kwargs):
            if name.endswith('morning_acceptance'):
                raise ModuleNotFoundError('audit absent')
            return original_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, '__import__', missing_audit)
        terminal = pipeline_status(root.parent, DAY)['app'][0]['terminal_receipts'][0]
        assert terminal['status'] == receipt['status'] and terminal['reason'] == receipt['reason']
        assert terminal['repair_acceptance']['status'] == 'unproved'


def test_missing_mutable_checklist_cannot_hide_the_sealed_business_and_original_audit(tmp_path, monkeypatch):
    from xiaocao.live.morning_pipeline import pipeline_status
    with original(tmp_path, monkeypatch) as (root, path, receipt, checklist):
        record_repair_acceptance(root, path, original_receipt_sha256=_hash(receipt))
        checklist.path.unlink()
        pipeline = pipeline_status(root.parent, DAY)
        assert len(pipeline['app']) == 1
        terminal = pipeline['app'][0]['terminal_receipts'][0]
        assert terminal['status'] == receipt['status'] and terminal['reason'] == receipt['reason']
        assert terminal['repair_acceptance']['status'] == 'observed'
