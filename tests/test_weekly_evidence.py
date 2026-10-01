from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import pytest

from xiaocao.research.weekly_evidence import build_weekly_evidence, verify_snapshots

AS_OF = dt.date(2026, 9, 18)


def write(root: Path, relative: str, value, *, jsonl=False):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in value) if jsonl else json.dumps(value))
    return path


def attach_source_facts(root, row):
    identity = {field: row[field] for field in ('sample_id', 'option', 'code', 'book', 'runtime', 'day')}
    prefix = f"output/research/inputs/{row['sample_id']}_{row['option']}"
    def save(kind, fields):
        observed = row['selection_as_of'] if kind == 'decision' else row['outcome_as_of']
        path = write(root, prefix+'_'+kind+'.json', dict(schema_version=f'weekly-{kind}-facts.v1',
            observed_at=observed, **identity, **fields))
        return dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    entry_price, shares = 10, 1500
    exit_price = entry_price*(1+row['gross_ret'])
    entry_gross, exit_gross = entry_price*shares, exit_price*shares
    entry_clock = row['day']+'T09:30:00+08:00'
    decision = save('decision', dict(frozen_candidates_sha256=row['frozen_candidates_sha256'],
        selected_at=row['selection_as_of'], requested_at=row['day']+'T09:24:48+08:00',
        capital_base=row['capital_base'], net_cash_flow=0, shares=shares, limit_price=10.01))
    market = save('market', dict(entry=dict(code=row['code'], observed_at=entry_clock,
        source='xiaocao_proprietary', trade_status='trading', volume=10000, low=9.98, high=10.02, vwap=entry_price),
        exit=dict(code=row['code'], observed_at=row['outcome_as_of'], source='xiaocao_proprietary',
                  trade_status='trading', volume=10000, trade=exit_price)))
    execution = save('execution', dict(decision_sha256=decision['sha256'], market_sha256=market['sha256'],
        entry=dict(code=row['code'], side='BUY', status='filled', price=entry_price, shares=shares,
            filled_at=entry_clock, observed_at=entry_clock, submitted_at=row['day']+'T09:29:57+08:00',
            fill_basis=row['fill_basis']),
        exit=dict(code=row['code'], side='SELL', status='filled', price=exit_price, shares=shares,
            filled_at=row['outcome_as_of'], observed_at=row['outcome_as_of'], fill_basis='paper_exit_proprietary_quote')))
    fees = save('fees', dict(execution_sha256=execution['sha256'], fee_basis='paper_model_rate',
        entry_fee=entry_gross*.0001, exit_fee=exit_gross*.0001, entry_fee_rate=.0001, exit_fee_rate=.0001))
    row.update(source_refs=dict(decision=decision, market=market, execution=execution, fees=fees),
        cost_ret=(entry_gross+exit_gross)*.0001/entry_gross,
        net_ret=row['gross_ret']-(entry_gross+exit_gross)*.0001/entry_gross,
        turnover=(entry_gross+exit_gross)/(2*row['capital_base']))


def comparison(root, *, bad_field=None, facts=True):
    rows = []
    days = []
    candidate_day = dt.date(2026, 8, 25)
    while len(days) < 16:
        if candidate_day.weekday() < 5:
            days.append(candidate_day)
        candidate_day += dt.timedelta(days=1)
    for i in range(16):
        day = days[i].isoformat()
        freeze = write(root, f'output/research/inputs/frozen_{i}.json', dict(day=day,
            sample_id=str(i), captured_at=day+'T09:23:00+08:00',
            candidates=[dict(code=code) for code in ('000001.XSHE', '000002.XSHE', '000003.XSHE')]))
        digest = hashlib.sha256(freeze.read_bytes()).hexdigest()
        for option, edge in [('baseline_no_kol', 0), ('current_bounded', .01), ('kol_challenger', -.01)]:
            cost = .0002
            net = .002 + edge + (i % 3) * .001 * (1 if edge > 0 else -1)
            outcome = dt.date.fromisoformat(day)+dt.timedelta(days=1)
            while outcome.weekday() >= 5:
                outcome += dt.timedelta(days=1)
            outcome_day = outcome.isoformat()
            code = {'baseline_no_kol': '000001.XSHE', 'current_bounded': '000002.XSHE',
                    'kol_challenger': '000003.XSHE'}[option]
            row = dict(sample_id=str(i), option=option, code=code, day=day, outcome_date=outcome_day,
                       selection_as_of=day+'T09:25:00+08:00', outcome_as_of=outcome_day+'T14:55:00+08:00',
                       frozen_candidates_sha256=digest,
                       frozen_candidates_path=freeze.relative_to(root).as_posix(), runtime='paper', book='B',
                       capital_base=30000, net_cash_flow=0, exposure=.5, turnover=.1,
                       decision_latency_seconds=12, execution_latency_seconds=3,
                       fill_basis='opening_window_vwap', return_basis='per_trade_net',
                       gross_ret=net+cost, cost_ret=cost, net_ret=net)
            if facts:
                attach_source_facts(root, row)
            rows.append(row)
    if bad_field:
        rows[-1].pop(bad_field)
    return write(root, 'output/research/weekly_comparison_demo.json', dict(
        schema_version=1, comparison_id='demo', return_unit='fraction', n_tried=2,
        expected_sample_ids=[str(i) for i in range(16)],
        split_declared_at='2026-08-24T12:00:00+08:00', train_end=days[7].isoformat(),
        test_start=days[8].isoformat(), rows=rows))


def test_empty_inputs_are_unknown_and_do_not_create_zero_returns(tmp_path):
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert report['status'] == 'insufficient_evidence'
    assert all(r['conclusion'] == 'insufficient_evidence' for r in report['option_comparison']['options'])
    assert all(r['mean_net_ret'] is None for r in report['option_comparison']['options'])
    assert report['paper_fill_audit']['windows']['1w']['fallback_proportion'] is None


def test_snapshot_replays_source_after_original_changes_and_detects_tampering(tmp_path):
    comparison(tmp_path)
    snapshot = tmp_path / 'audit'
    report = build_weekly_evidence(tmp_path, as_of=AS_OF, snapshot_dir=snapshot)
    source = tmp_path / 'output/research/weekly_comparison_demo.json'
    source.write_text('{}')
    assert verify_snapshots(report) == []
    item = next(r for r in report['input_manifest']['files'] if 'weekly_comparison' in r['path'])
    Path(item['snapshot_path']).write_text('{}')
    assert verify_snapshots(report)


def test_three_options_produce_verified_support_rejection_and_cost_time_metrics(tmp_path):
    comparison(tmp_path)
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    group = report['option_comparison']['comparisons'][0]
    options = {r['option']: r for r in group['options']}
    assert options['current_bounded']['conclusion'] == 'supported'
    assert options['kol_challenger']['conclusion'] == 'rejected'
    assert options['current_bounded']['guard_result']['walk_forward']['test_days'] == 8
    assert .0002 < options['current_bounded']['mean_cost_ret'] < .000202
    assert options['current_bounded']['mean_decision_latency_seconds'] == 12
    assert report['promotion']['auto_promote'] is False


def test_incomplete_or_future_selected_cohort_cannot_be_called_supported(tmp_path):
    path = comparison(tmp_path, bad_field='cost_ret')
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert report['option_comparison']['comparisons'][0]['conclusion'] == 'insufficient_evidence'
    data = json.loads(path.read_text())
    data['rows'][-1]['cost_ret'] = .0002
    data['rows'][-1]['selection_as_of'] = '2026-09-17T09:25:00+08:00'
    path.write_text(json.dumps(data))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert 'selection_after_signal_day' in report['option_comparison']['comparisons'][0]['missing_evidence']


def test_proxy_fill_audit_counts_unique_entries_and_excludes_unknown(tmp_path):
    rows = [dict(book='B', code=str(i), entry_date='2026-09-15', shares=100, entry_price=10,
                 entry_price_basis=basis) for i, basis in enumerate([
                     'opening_window_vwap', 'limit_fallback', 'retry_realtime_after_limit_reject', None])]
    write(tmp_path, 'output/live/positions.jsonl', rows, jsonl=True)
    # Duplicate BUY represents same entry and must not double its count.
    write(tmp_path, 'output/live/paper_trades.jsonl', [dict(book='B', code='0', date='2026-09-15',
          side='BUY', shares=100, price=10, price_basis='opening_window_vwap')], jsonl=True)
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    audit = report['paper_fill_audit']['windows']['1w']
    assert audit['entry_count'] == 4
    assert audit['fallback_count'] == 1
    assert audit['proxy_count'] == 2
    assert audit['unknown_count'] == 1
    assert audit['confirmed_window_count'] == 1
    assert audit['fallback_proportion'] == .25


def test_historical_rejection_preserved_but_no_artifacts_means_unverified(tmp_path):
    write(tmp_path, 'kronos_screen/HYPOTHESES.jsonl', [dict(id='XH-1', ts='2026-09-01T12:00:00',
        verdict='REJECTED', metrics=dict(n_days=40, test_edge=-.1)),
        dict(id='XH-1', ts='2026-09-20T12:00:00', verdict='PASS')], jsonl=True)
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    row = report['hypotheses'][0]
    assert row['recorded_verdict'] == 'REJECTED'
    assert row['conclusion'] == 'insufficient_evidence'
    assert row['scope'] == 'historical_verdict_not_this_week'
    assert row['metrics']['test_edge'] == -.1


def test_manifest_hash_mismatch_cannot_launder_pass(tmp_path):
    write(tmp_path, 'output/research/runs/demo/trades.jsonl', [dict(day='2026-09-01', strat_ret=.1, base_ret=0)], jsonl=True)
    write(tmp_path, 'output/research/runs/demo/verdict.json', dict(verdict='PASS'))
    write(tmp_path, 'output/research/runs/demo/manifest.json', dict(created_at='2026-09-16T12:00:00',
        hypothesis_id='XH-1', protocol_id='shortline-book-b-v1',
        inputs=dict(trades_sha256='0'*64, n_rows=1),
        artifacts=dict(trades='trades.jsonl', verdict='verdict.json'),
        parameters=dict(n_tried=2, cache_only=True, min_days=8), verdict=dict(status='PASS')))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert 'trades_checksum_mismatch' in report['research_runs'][0]['missing_evidence']
    assert report['research_runs'][0]['conclusion'] == 'insufficient_evidence'


def test_self_reported_freeze_hash_and_label_contaminated_selection_are_insufficient(tmp_path):
    path = comparison(tmp_path)
    data = json.loads(path.read_text())
    data['rows'][-1]['frozen_candidates_sha256'] = 'b'*64
    path.write_text(json.dumps(data))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert 'frozen_candidate_original_missing_or_checksum_mismatch' in report['option_comparison']['comparisons'][0]['missing_evidence']
    freeze_path = tmp_path / data['rows'][-1]['frozen_candidates_path']
    freeze = json.loads(freeze_path.read_text())
    freeze['candidates'][0]['executable_net_ret'] = .9
    freeze_path.write_text(json.dumps(freeze))
    for row in data['rows'][-3:]:
        row['frozen_candidates_sha256'] = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(data))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert 'outcome_fields_in_selection_freeze' in report['option_comparison']['comparisons'][0]['missing_evidence']


def test_native_statement_nested_valuation_is_retained_and_undated_is_explicit(tmp_path):
    write(tmp_path, 'output/live/book_b_live_execution/accounting_reports/daily.json', dict(
        valuation_status='dated_observation', journal=dict(journal_head_sha256='a'*64),
        valuation=dict(observed_at='2026-09-18T15:10:00+08:00', journal_head_sha256='a'*64,
                       status='unclassified_cash', cumulative_pnl=None, fee_basis='estimated_plan_rate',
                       marked_nav='31000.00', net_contributed_capital='30000.00')))
    write(tmp_path, 'output/live/book_b_live_execution/accounting_reports/missing.json', dict(valuation=None))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert len(report['accounting_observations']) == 1
    observed = report['accounting_observations'][0]
    assert observed['valuation']['marked_nav'] == '31000.00'
    assert observed['valuation']['cumulative_pnl'] is None
    assert observed['profit_attribution'] == 'not_established'
    assert any('accounting_report_undated' in missing for missing in report['missing_evidence'])


def test_self_reported_comparison_without_fact_originals_is_insufficient(tmp_path):
    comparison(tmp_path, facts=False)
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    group = report['option_comparison']['comparisons'][0]
    assert group['conclusion'] == 'insufficient_evidence'
    assert all(row['conclusion'] == 'insufficient_evidence' for row in group['options'])
    assert 'decision_original_missing_or_checksum_mismatch' in group['missing_evidence']


@pytest.mark.parametrize('kind,field,value,expected', [
    ('decision', 'code', '000099.XSHE', 'decision_source_identity_mismatch'),
    ('execution', 'entry.price', 10.5, 'source_paper_fill_price_mismatch'),
    ('market', 'entry.observed_at', '2026-09-20T09:30:00+08:00', 'source_fill_market_identity_or_clock_unproven'),
    ('fees', 'entry_fee', 20, 'source_fee_rate_amount_mismatch'),
    ('fees', 'observed_at', '2026-09-20T14:55:00+08:00', 'fees_source_observation_clock_unproven'),
    ('decision', 'selected_at', '2026-09-16T09:25:00', 'source_fact_economics_or_clocks_incomplete'),
    ('market', 'entry.vwap', float('nan'), 'source_opening_window_or_limit_unproven'),
])
def test_rebound_source_hash_cannot_hide_wrong_identity_fill_future_quote_or_fee(tmp_path, kind, field, value, expected):
    path = comparison(tmp_path)
    data = json.loads(path.read_text())
    row = data['rows'][-1]
    ref = row['source_refs'][kind]
    source_path = tmp_path / ref['path']
    source = json.loads(source_path.read_text())
    target = source
    parts = field.split('.')
    for key in parts[:-1]:
        target = target[key]
    target[parts[-1]] = value
    source_path.write_text(json.dumps(source))
    ref['sha256'] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(data))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    group = report['option_comparison']['comparisons'][0]
    assert group['conclusion'] == 'insufficient_evidence'
    assert expected in group['missing_evidence']


def test_missing_or_tampered_actual_source_and_membership_cannot_pass(tmp_path):
    path = comparison(tmp_path)
    data = json.loads(path.read_text())
    row = data['rows'][-1]
    market_path = tmp_path / row['source_refs']['market']['path']
    market_path.write_text('{}')
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert 'market_original_missing_or_checksum_mismatch' in report['option_comparison']['comparisons'][0]['missing_evidence']
    market_path.unlink()
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert report['option_comparison']['comparisons'][0]['conclusion'] == 'insufficient_evidence'
    # Restore sources, then change selection membership with a self-consistent freeze digest.
    attach_source_facts(tmp_path, row)
    freeze_path = tmp_path / row['frozen_candidates_path']
    freeze = json.loads(freeze_path.read_text())
    freeze['candidates'] = [dict(code='000999.XSHE')]
    freeze_path.write_text(json.dumps(freeze))
    for option in data['rows'][-3:]:
        option['frozen_candidates_sha256'] = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
        attach_source_facts(tmp_path, option)
    path.write_text(json.dumps(data))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert 'decision_code_not_in_frozen_candidates' in report['option_comparison']['comparisons'][0]['missing_evidence']


def test_naive_comparison_clocks_are_observations_without_point_in_time_authority(tmp_path):
    path = comparison(tmp_path)
    data = json.loads(path.read_text())
    data['rows'][-1]['selection_as_of'] = '2026-09-16T09:25:00'
    path.write_text(json.dumps(data))
    report = build_weekly_evidence(tmp_path, as_of=AS_OF)
    assert 'point_in_time_clocks_missing' in report['option_comparison']['comparisons'][0]['missing_evidence']
    assert report['option_comparison']['comparisons'][0]['conclusion'] == 'insufficient_evidence'
