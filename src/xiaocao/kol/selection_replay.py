"""Local data-ready to recommendation replay; no current source or trading writes."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .publication import canonical_sha256
from .selection import select_candidates
from .selection_preview import render
from xiaocao.live.trading_runner import frozen_rows_digest
from xiaocao.utils.atomic_files import atomic_write


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * probability) - 1)] if ordered else 0.


def _exercise_preference(rows: list[dict]) -> list[dict]:
    """Synthetic mechanics probe, explicitly distinct from an author judgment."""
    pool = [row for row in rows if row.get('mode_state') in {'ACTIVE', 'PROVISIONAL'}
            and row.get('mode_trade_eligible') is True and not str(row.get('code')).endswith('.BJSE')
            and row.get('executable_fillable', True) is True]
    if not pool:
        return []
    target = pool[-1]
    return [{'id':'engineering-reserve-probe','kind':'candidate',
        'target':{'code':target['code'],'mode':target['mode']},'direction':'prefer',
        'source_report_id':'synthetic-mechanics-only', 'source_quote':'not a KOL judgment',
        'rationale':'Exercise the last eligible candidate without granting policy authority.',
        'applicability':'supported','conditions':[]}]


def replay(bundle_root: Path, output_dir: Path, *, repeats: int = 30,
           analysis: dict | None = None, p95_budget_ms: float = 100.,
           replay_raw_strategy: bool = False, trade_date: str | None = None) -> dict:
    if type(repeats) is not int or not 1 <= repeats <= 1000 or not 0 < p95_budget_ms < 60_000:
        raise ValueError('REPLAY_BUDGET_INVALID')
    source_root, destination = bundle_root.resolve(), output_dir.resolve()
    if destination == source_root or destination.is_relative_to(source_root):
        raise ValueError('REPLAY_OUTPUT_MUST_BE_ISOLATED')
    destination.mkdir(parents=True, exist_ok=True)
    cases, totals, phases = [], [], {}
    snapshots = sorted(source_root.glob('*/*/original/snapshot.jsonl'))
    if trade_date is not None:
        if datetime.strptime(trade_date,'%Y-%m-%d').date().isoformat()!=trade_date:
            raise ValueError('REPLAY_TRADE_DATE_INVALID')
        snapshots = [path for path in snapshots if path.parents[2].name==trade_date]
    if not snapshots:
        raise ValueError('REPLAY_IMMUTABLE_BUNDLES_REQUIRED')
    for snapshot in snapshots:
        original_raw = snapshot.read_bytes()
        checkpoint_path = snapshot.parent.parent / 'checkpoint.json'
        raw_checkpoint = checkpoint_path.read_bytes()
        checkpoint = json.loads(raw_checkpoint)
        freeze = {**checkpoint['binding'], 'checkpoint_sha256':hashlib.sha256(raw_checkpoint).hexdigest()}
        if (freeze['snapshot_raw_sha256'] != hashlib.sha256(original_raw).hexdigest()
                or checkpoint_path.parent.name != hashlib.sha256(freeze['strategy_run_id'].encode()).hexdigest()):
            raise ValueError('REPLAY_ORIGINAL_RAW_OR_CHECKPOINT_MISMATCH')
        initial_rows = [json.loads(line) for line in original_raw.splitlines() if line.strip()]
        if (frozen_rows_digest(initial_rows) != freeze['snapshot_sha256']
                or len(initial_rows) != freeze['snapshot_row_count']):
            raise ValueError('REPLAY_ORIGINAL_CANONICAL_MISMATCH')
        scenarios = [('baseline', []) , ('synthetic_mechanics', _exercise_preference(initial_rows))]
        analysis_date = (analysis or {}).get('trade_date') or str((analysis or {}).get('simulated_market_as_of',''))[:10]
        if analysis and analysis_date == freeze['market_date']:
            if analysis.get('authority') != 0 or analysis.get('replay_only') is not True:
                raise ValueError('REPLAY_ANALYSIS_AUTHORITY_INVALID')
            scenarios.append(('offline_semantic_replay', analysis['preferences']))
        for label, preferences in scenarios:
            per_case = []
            last_receipt = None
            for _ in range(repeats):
                started = previous = perf_counter()
                raw = snapshot.read_bytes()
                rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
                timings = {'read_decode_ms':(perf_counter()-previous)*1000}
                raw_replay = {'status':'not_requested'}
                if replay_raw_strategy:
                    previous = perf_counter()
                    from .replay_inputs import raw_strategy
                    rows,raw_replay=raw_strategy(checkpoint,rows)
                    timings['raw_strategy_ms']=(perf_counter()-previous)*1000
                previous = perf_counter()
                if frozen_rows_digest([json.loads(line) for line in raw.splitlines() if line.strip()]) != freeze['snapshot_sha256']:
                    raise ValueError('REPLAY_INPUT_CHANGED')
                timings['validate_ms'] = (perf_counter()-previous)*1000
                previous = perf_counter()
                selection = select_candidates(rows, preferences, trade_date=freeze['market_date'],
                                               freeze_sha256=freeze['snapshot_sha256'])
                timings['select_ms'] = (perf_counter()-previous)*1000
                selected = [r for r in selection.rows if r.get('mode_exec_star') is True]
                keys = {(r['code'],r['mode']) for r in rows}
                if (len(selected)>3 or len({r['mode'] for r in selected})!=len(selected)
                        or len({r['code'] for r in selected})!=len(selected)
                        or any((r['code'],r['mode']) not in keys for r in selected)
                        or any(r.get('mode_state') not in {'ACTIVE','PROVISIONAL'} or r.get('mode_trade_eligible') is not True
                               or r['code'].endswith('.BJSE') or r.get('executable_fillable',True) is not True for r in selected)):
                    raise ValueError('REPLAY_SELECTION_INVARIANT_VIOLATION')
                previous = perf_counter()
                preview = {'status':label,'reason':'offline_replay_only','baseline_codes':selection.receipt['baseline_codes'],
                    'selected_codes':selection.receipt['selected_codes'],'elapsed_seconds':perf_counter()-started,
                    'receipt_sha256':selection.receipt['receipt_sha256']}
                markdown = render(preview)
                timings['render_ms'] = (perf_counter()-previous)*1000
                previous = perf_counter()
                atomic_write(destination/'recommendation.md', markdown.encode())
                atomic_write(destination/'selection.json', json.dumps(selection.receipt,ensure_ascii=False).encode())
                timings['write_ms'] = (perf_counter()-previous)*1000
                total = (perf_counter()-started)*1000
                per_case.append(total)
                totals.append(total)
                for name,value in timings.items():
                    phases.setdefault(name,[]).append(value)
                last_receipt = selection.receipt
            if snapshot.read_bytes() != original_raw:
                raise ValueError('REPLAY_MUTATED_ORIGINAL')
            cases.append({'snapshot':str(snapshot),'trade_date':freeze['market_date'],'rows':len(initial_rows),
                'scenario':label,'preferences':len(preferences),'selection':last_receipt,
                'raw_strategy':raw_replay,
                'p50_ms':_percentile(per_case,.5),'p95_ms':_percentile(per_case,.95),
                'predictive_quality':'unproved_no_contemporaneous_v3_policy_or_completed_holdout',
                'execution_and_fees':'not_simulated_no_fill_or_pnl_claim'})
    report = {'schema_version':'kol-selection-offline-replay.v1','authority':0,
        'observed_at':datetime.now(timezone.utc).isoformat(),'bundle_count':len(snapshots),
        'repeats':repeats,'recommendations':len(totals),'originals_unchanged':True,
        'selection_invariants':'passed','p50_ms':_percentile(totals,.5),'p95_ms':_percentile(totals,.95),
        'p95_budget_ms':p95_budget_ms,'performance_passed':_percentile(totals,.95)<=p95_budget_ms,
        'phase_p95_ms':{name:_percentile(values,.95) for name,values in phases.items()},
        'measurement_scope':('archived_raw_API_to_strategy_with_recorded_prewake_features_to_recommendation'
            if replay_raw_strategy else 'local_immutable_data_ready_to_durable_recommendation'),
        'not_measured':['new_source_capture','model_preparation','current_remote_source_heads','formal_policy_review','broker_execution'],
        'analysis_sha256':canonical_sha256(analysis) if analysis else None,'cases':cases}
    report['receipt_sha256'] = canonical_sha256(report)
    atomic_write(destination/'replay.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
    return report
