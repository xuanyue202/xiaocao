"""Cache-only weekly evidence, with frozen bytes and conservative conclusions.

This is an observer. It never records a research verdict, promotes a strategy,
replays a trading day or imports a broker/API client. Comparison JSON is a saved
research artifact, not a new selector: all three options must cover the same
predeclared sample, budget, frozen candidates and chronological OOS split.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from xiaocao.research import guards

OPTIONS = ('baseline_no_kol', 'current_bounded', 'kol_challenger')
WINDOW_BASES = {'opening_window_vwap', 'opening_window_vwap_capped_by_limit'}
PATTERNS = (
    'kronos_screen/HYPOTHESES.jsonl',
    'reference/experience/xiaocao_hypotheses.jsonl',
    'reference/experience/research_protocols.yaml',
    'reference/experience/distill_action_log.jsonl',
    'output/research/runs/*/manifest.json',
    'output/research/runs/*/trades.jsonl',
    'output/research/runs/*/verdict.json',
    'output/research/weekly_comparison*.json',
    'output/research/paper_vs_market_*.md',
    'output/live/positions.jsonl', 'output/live/paper_trades.jsonl',
    'output/live/pnl_decompose.csv',
    'output/live/posture_calibration.jsonl', 'output/live/exit_calibration.jsonl',
    'output/live/book_b_live_execution/capital_flows.jsonl',
    'output/live/book_b_live_execution/accounting_reports/*.json',
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date(value: Any) -> str | None:
    try:
        return dt.date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _proof_time(value: Any) -> dt.datetime:
    """Comparison proof requires a real offset; legacy naive clocks stay observations."""
    result = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('explicit timezone required for point-in-time proof')
    return result


def _rows(data: bytes, path: str) -> list[dict]:
    if path.endswith('.jsonl'):
        rows = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
    else:
        value = json.loads(data)
        rows = value if isinstance(value, list) else [value]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError('records must be objects')
    return rows


def _capture(root: Path, snapshot_dir: Path | None) -> tuple[dict, dict[str, bytes]]:
    files, contents, missing = [], {}, []
    paths_to_capture = []
    for pattern in PATTERNS:
        paths = sorted(p for p in root.glob(pattern) if p.is_file())
        if not paths:
            missing.append(pattern)
        paths_to_capture.extend(paths)
    # Saved comparison/run artifacts can name inputs beyond the conventional
    # filenames. Capture only local research originals, never another checkout.
    for path in list(paths_to_capture):
        if path.name.startswith('weekly_comparison') or path.name == 'manifest.json':
            try:
                value = json.loads(path.read_bytes())
                refs = [row.get('frozen_candidates_path') for row in value.get('rows', [])]
                for row in value.get('rows', []):
                    for reference in (row.get('source_refs') or {}).values():
                        if isinstance(reference, dict):
                            refs.append(reference.get('path'))
                refs += list(value.get('artifacts', {}).values())
                for ref in refs:
                    if isinstance(ref, str) and ref.startswith('output/research/'):
                        candidate = root / ref
                        if candidate.is_file() and candidate.resolve().is_relative_to(root.resolve()):
                            paths_to_capture.append(candidate)
            except (ValueError, TypeError, AttributeError):
                pass  # Main capture records the malformed artifact below.
    for path in sorted(set(paths_to_capture)):
        relative = path.relative_to(root).as_posix()
        if relative in contents:
            continue
        # Symlinks must not silently import evidence from another workspace.
        if not path.resolve().is_relative_to(root.resolve()):
            files.append(dict(path=relative, status='invalid', error='outside_root'))
            continue
        data = path.read_bytes()
        contents[relative] = data
        item = dict(path=relative, sha256=_hash(data), size_bytes=len(data), status='captured',
                    record_count=None, first_date=None, last_date=None)
        if relative.endswith(('.json', '.jsonl')):
            try:
                rows = _rows(data, relative)
                dates = sorted(d for row in rows if (d := _date(row.get('date') or row.get('day')
                    or row.get('entry_date') or row.get('ts') or row.get('created_at'))))
                item.update(record_count=len(rows), first_date=dates[0] if dates else None,
                            last_date=dates[-1] if dates else None)
            except (ValueError, UnicodeError) as exc:
                item.update(status='invalid', error=str(exc))
        if snapshot_dir is not None:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            blob = snapshot_dir / item['sha256']
            try:
                with blob.open('xb') as stream:
                    stream.write(data)
            except FileExistsError:
                if _hash(blob.read_bytes()) != item['sha256']:
                    raise ValueError(f'content-addressed snapshot corrupted: {blob}')
            item['snapshot_path'] = str(blob.resolve())
        files.append(item)
    manifest = dict(schema_version=1, files=files, missing_patterns=missing,
                    source_semantics='captured bytes; mtime is never an observation time')
    manifest['sha256'] = _hash(_canonical(manifest))
    return manifest, contents


def verify_snapshots(report: dict) -> list[str]:
    manifest = report.get('input_manifest', {})
    errors = []
    unsigned = {key: value for key, value in manifest.items() if key != 'sha256'}
    if manifest.get('sha256') != _hash(_canonical(unsigned)):
        errors.append('input_manifest_checksum_mismatch')
    saved_manifest = report.get('snapshot_manifest_path')
    if not saved_manifest or not Path(saved_manifest).is_file():
        errors.append('snapshot_manifest_missing')
    elif Path(saved_manifest).read_bytes() != _canonical(manifest):
        errors.append('snapshot_manifest_checksum_mismatch')
    for item in manifest.get('files', []):
        path = item.get('snapshot_path')
        if not path:
            errors.append(f"snapshot_missing:{item['path']}")
        elif not Path(path).is_file() or _hash(Path(path).read_bytes()) != item.get('sha256'):
            errors.append(f"snapshot_checksum_mismatch:{item['path']}")
    return errors


def _load(contents: dict[str, bytes], path: str) -> list[dict]:
    try:
        return _rows(contents[path], path)
    except (KeyError, ValueError, UnicodeError):
        return []


def _fill_class(row: dict) -> str:
    basis = str(row.get('entry_price_basis') or row.get('price_basis') or row.get('fill_basis') or '')
    if row.get('fill_fallback') or 'fallback' in basis:
        return 'fallback'
    if basis in WINDOW_BASES:
        return 'confirmed_window'
    if 'retry' in basis or 'proxy' in basis:
        return 'proxy'
    return 'unknown'


def _fill_audit(contents: dict[str, bytes], as_of: dt.date) -> dict:
    entries: dict[tuple, list[dict]] = defaultdict(list)
    invalid = 0
    for source in ('output/live/positions.jsonl', 'output/live/paper_trades.jsonl'):
        for row in _load(contents, source):
            if source.endswith('paper_trades.jsonl') and row.get('side') != 'BUY':
                continue
            day = _date(row.get('entry_date') or row.get('date'))
            if not day or row.get('book') not in ('A', 'B', 'T'):
                invalid += 1
                continue
            if day > as_of.isoformat():
                continue
            key = (row['book'], row.get('code'), day,
                   _number(row.get('shares')), _number(row.get('entry_price') or row.get('price')))
            if key[1] is None or key[3] is None or key[4] is None:
                invalid += 1
                continue
            entries[key].append(row)
    windows = {}
    for weeks in (1, 4, 12):
        start = (as_of - dt.timedelta(weeks=weeks) + dt.timedelta(days=1)).isoformat()
        counts, books = Counter(), defaultdict(Counter)
        for key, rows in entries.items():
            if key[2] < start:
                continue
            classes = {_fill_class(row) for row in rows}
            # Missing duplicate metadata does not erase known provenance; conflicting
            # concrete metadata cannot upgrade an estimate to a confirmed window.
            category = ('fallback' if 'fallback' in classes else 'proxy' if 'proxy' in classes
                        else 'confirmed_window' if 'confirmed_window' in classes else 'unknown')
            counts[category] += 1
            books[key[0]][category] += 1
        total = sum(counts.values())
        windows[f'{weeks}w'] = dict(start=start, end=as_of.isoformat(), entry_count=total,
            fallback_count=counts['fallback'], proxy_count=counts['fallback']+counts['proxy'],
            unknown_count=counts['unknown'], confirmed_window_count=counts['confirmed_window'],
            fallback_proportion=counts['fallback']/total if total else None,
            proxy_proportion=(counts['fallback']+counts['proxy'])/total if total else None,
            excluded_from_confirmed_count=total-counts['confirmed_window'],
            by_book={book: dict(value) for book, value in sorted(books.items())})
    return dict(windows=windows, invalid_identity_count=invalid,
        count_semantics='unique book/code/entry_date/shares/price entries; positions and BUY duplicates merged',
        limitations=['confirmed_window denotes evidence-backed local simulation, never APP/broker fill',
                     'fallback, realtime retry proxy and unknown fills excluded from executable confirmation',
                     'paper audit is not a no-KOL counterfactual or an alpha estimate'])


def _comparison_source_errors(row: dict, freeze: dict, contents: dict[str, bytes], *, as_of: dt.date) -> list[str]:
    """Verify separate persisted facts, never trust the comparison's summaries.

    These explicit research-export schemas are only understood for local paper
    simulation. Native production receipts have no such adapter here; absence of
    an adapter is insufficient evidence, never inferred broker confirmation.
    """
    errors, sources = [], {}
    refs = row.get('source_refs')
    if not isinstance(refs, dict):
        refs = {}
    for kind in ('decision', 'execution', 'market', 'fees'):
        ref = refs.get(kind)
        raw = contents.get(ref.get('path')) if isinstance(ref, dict) and isinstance(ref.get('path'), str) else None
        if raw is None or _hash(raw) != ref.get('sha256'):
            errors.append(f'{kind}_original_missing_or_checksum_mismatch')
            continue
        try:
            source = json.loads(raw)
            if not isinstance(source, dict) or source.get('schema_version') != f'weekly-{kind}-facts.v1':
                errors.append(f'{kind}_source_schema_not_adapted')
                continue
            sources[kind] = source
            observed = _proof_time(source['observed_at'])
            expected_clock = row.get('selection_as_of') if kind == 'decision' else row.get('outcome_as_of')
            if observed != _proof_time(expected_clock) or observed.astimezone(ZoneInfo('Asia/Shanghai')).date() > as_of:
                errors.append(f'{kind}_source_observation_clock_unproven')
            for field in ('sample_id', 'option', 'code', 'book', 'runtime', 'day'):
                if source.get(field) != row.get(field) or source.get(field) in (None, ''):
                    errors.append(f'{kind}_source_identity_mismatch')
        except (ValueError, UnicodeError, KeyError, TypeError):
            errors.append(f'{kind}_original_invalid')
    if len({ref.get('path') for ref in refs.values() if isinstance(ref, dict)}) < 4:
        errors.append('independent_fact_originals_required')
    if len(sources) != 4:
        return errors
    if row.get('runtime') != 'paper':
        return errors + ['native_broker_source_schema_not_adapted']
    decision, execution, market, fees = (sources[kind] for kind in ('decision', 'execution', 'market', 'fees'))
    try:
        if row.get('code') not in {candidate.get('code') for candidate in freeze.get('candidates', [])}:
            errors.append('decision_code_not_in_frozen_candidates')
        if (decision.get('frozen_candidates_sha256') != row.get('frozen_candidates_sha256')
                or execution.get('decision_sha256') != refs['decision']['sha256']
                or execution.get('market_sha256') != refs['market']['sha256']
                or fees.get('execution_sha256') != refs['execution']['sha256']):
            errors.append('source_fact_chain_checksum_mismatch')
        selected = _proof_time(decision['selected_at'])
        requested = _proof_time(decision['requested_at'])
        entry, exit_fill = execution['entry'], execution['exit']
        entry_clock, exit_clock = _proof_time(entry['filled_at']), _proof_time(exit_fill['filled_at'])
        if (selected != _proof_time(row['selection_as_of']) or requested > selected
                or not selected <= _proof_time(entry['submitted_at']) <= entry_clock < exit_clock
                or exit_clock != _proof_time(row['outcome_as_of'])
                or _date(entry['filled_at']) != row['day']
                or _date(exit_fill['filled_at']) != row['outcome_date']
                or _date(exit_fill['filled_at']) > as_of.isoformat()
                or _date(entry['filled_at']) >= _date(exit_fill['filled_at'])):
            errors.append('source_decision_fill_chronology_unproven')
        if decision.get('net_cash_flow') != 0 or _number(decision.get('capital_base')) != _number(row.get('capital_base')):
            errors.append('source_budget_or_cashflow_mismatch')
        prices, quantities = [], []
        for leg, fill in (('entry', entry), ('exit', exit_fill)):
            quote = market[leg]
            price, shares = _number(fill['price']), _number(fill['shares'])
            if price is None or price <= 0 or shares is None or shares <= 0 or int(shares) != shares:
                errors.append('source_price_or_quantity_invalid')
                return errors
            if (fill.get('side') != ('BUY' if leg == 'entry' else 'SELL') or fill.get('status') != 'filled'
                    or fill.get('code') != row['code'] or quote.get('code') != row['code']
                    or quote.get('source') != 'xiaocao_proprietary' or quote.get('trade_status') != 'trading'
                    or _number(quote.get('volume')) is None or _number(quote['volume']) <= 0
                    or _proof_time(quote['observed_at']) != _proof_time(fill['filled_at'])
                    or _proof_time(fill['observed_at']) < _proof_time(fill['filled_at'])
                    or _proof_time(fill['observed_at']).astimezone(ZoneInfo('Asia/Shanghai')).date() > as_of):
                errors.append('source_fill_market_identity_or_clock_unproven')
            if leg == 'entry':
                if int(shares) % 100 or _number(decision.get('shares')) != shares:
                    errors.append('source_buy_lot_or_decision_quantity_mismatch')
                basis = fill.get('fill_basis')
                if basis not in WINDOW_BASES or basis != row.get('fill_basis') or fill.get('fill_fallback'):
                    errors.append('source_proxy_or_unknown_fill')
                low, high, vwap = (_number(quote.get(field)) for field in ('low', 'high', 'vwap'))
                limit = _number(decision.get('limit_price'))
                if None in (low, high, vwap, limit) or not 0 < low <= vwap <= high or low > limit:
                    errors.append('source_opening_window_or_limit_unproven')
                else:
                    expected = min(vwap, limit) if basis.endswith('capped_by_limit') else vwap
                    if abs(price-expected) > 1e-9 or price > limit:
                        errors.append('source_paper_fill_price_mismatch')
            elif fill.get('fill_basis') != 'paper_exit_proprietary_quote' or _number(quote.get('trade')) != price:
                errors.append('source_exit_quote_or_fill_unproven')
            prices.append(price)
            quantities.append(shares)
        if quantities[0] != quantities[1]:
            errors.append('source_roundtrip_quantity_mismatch')
        entry_gross, exit_gross = prices[0]*quantities[0], prices[1]*quantities[1]
        entry_fee, exit_fee = _number(fees.get('entry_fee')), _number(fees.get('exit_fee'))
        if fees.get('fee_basis') != 'paper_model_rate' or None in (entry_fee, exit_fee) or min(entry_fee, exit_fee) < 0:
            return errors + ['source_fee_amount_or_basis_unproven']
        for leg, gross, fee in (('entry', entry_gross, entry_fee), ('exit', exit_gross, exit_fee)):
            rate = _number(fees.get(leg+'_fee_rate'))
            if rate is None or rate < 0 or abs(gross*rate-fee) > 0.011:
                errors.append('source_fee_rate_amount_mismatch')
        capital = _number(decision.get('capital_base'))
        if capital is None or capital <= 0:
            return errors + ['source_capital_base_unproven']
        actual = dict(gross_ret=(exit_gross-entry_gross)/entry_gross,
                      cost_ret=(entry_fee+exit_fee)/entry_gross,
                      net_ret=(exit_gross-entry_gross-entry_fee-exit_fee)/entry_gross,
                      exposure=entry_gross/capital, turnover=(entry_gross+exit_gross)/(2*capital),
                      decision_latency_seconds=(selected-requested).total_seconds(),
                      execution_latency_seconds=(entry_clock-_proof_time(entry['submitted_at'])).total_seconds())
        for field, value in actual.items():
            recorded = _number(row.get(field))
            if recorded is None or abs(recorded-value) > 1e-9:
                errors.append(f'{field}_does_not_match_source_facts')
    except (KeyError, TypeError, ValueError, AttributeError, ZeroDivisionError):
        errors.append('source_fact_economics_or_clocks_incomplete')
    return errors


def _comparison(data: dict, *, as_of: dt.date, evidence: dict, contents: dict[str, bytes]) -> dict:
    errors = []
    rows = data.get('rows', [])
    expected = data.get('expected_sample_ids', [])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        rows = []
        errors.append('invalid_rows')
    if not isinstance(expected, list) or not expected or len(set(map(str, expected))) != len(expected):
        expected = []
        errors.append('expected_sample_inventory_missing_or_duplicate')
    if data.get('return_unit') != 'fraction':
        errors.append('explicit_fraction_units_required')
    n_tried = _number(data.get('n_tried'))
    if n_tried is None or n_tried < 2 or int(n_tried) != n_tried:
        errors.append('honest_multiple_comparison_count_required')
    indexed = {}
    reference = {}
    future_rows = 0
    train_end, test_start = _date(data.get('train_end')), _date(data.get('test_start'))
    if not train_end or not test_start or train_end >= test_start:
        errors.append('chronological_oos_split_missing')
    for original in rows:
        row = dict(original)
        numeric_fields = ('capital_base', 'net_cash_flow', 'exposure', 'turnover', 'gross_ret', 'cost_ret',
                          'net_ret', 'decision_latency_seconds', 'execution_latency_seconds')
        for field in numeric_fields:
            if _number(row.get(field)) is not None:
                row[field] = _number(row[field])
        day = _date(row.get('day'))
        if not day:
            errors.append('signal_date_missing')
            continue
        outcome_day = _date(row.get('outcome_date'))
        if day > as_of.isoformat() or not outcome_day or outcome_day > as_of.isoformat():
            future_rows += 1
            errors.append('future_or_unmatured_rows')
            continue
        option, sample = row.get('option'), str(row.get('sample_id'))
        if option not in OPTIONS or sample not in set(map(str, expected)):
            errors.append('unexpected_option_or_sample')
            continue
        key = (sample, option)
        if key in indexed:
            errors.append('duplicate_option_sample')
        indexed[key] = row
        try:
            selection = _proof_time(row.get('selection_as_of'))
            outcome = _proof_time(row.get('outcome_as_of'))
            declaration = _proof_time(data.get('split_declared_at'))
            if selection.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() != day:
                errors.append('selection_after_signal_day')
            if selection >= outcome or declaration >= selection:
                errors.append('selection_or_split_contaminated_by_outcome')
            if outcome.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() != outcome_day:
                errors.append('outcome_clock_date_mismatch')
        except (ValueError, TypeError):
            errors.append('point_in_time_clocks_missing')
        digest = row.get('frozen_candidates_sha256')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            errors.append('frozen_candidate_checksum_missing')
        freeze_path = row.get('frozen_candidates_path')
        freeze_data = contents.get(freeze_path) if isinstance(freeze_path, str) else None
        freeze = {}
        if freeze_data is None or _hash(freeze_data) != digest:
            errors.append('frozen_candidate_original_missing_or_checksum_mismatch')
        else:
            try:
                freeze = json.loads(freeze_data)
                if (freeze.get('day') != day or str(freeze.get('sample_id')) != sample
                        or _proof_time(freeze.get('captured_at')) > _proof_time(row.get('selection_as_of'))):
                    errors.append('frozen_candidate_identity_or_chronology_mismatch')
                if not isinstance(freeze.get('candidates'), list) or not freeze['candidates']:
                    errors.append('frozen_candidate_inventory_missing')
                # A freeze made from labels is selection contamination even if its
                # top-level clock claims to predate the outcome.
                forbidden = {'strat_ret', 'base_ret', 'net_ret', 'executable_net_ret',
                             'net_realized_ret', 'outcome_date', 'outcome_as_of'}
                if any(not isinstance(candidate, dict) or forbidden.intersection(candidate)
                       for candidate in freeze.get('candidates', [])):
                    errors.append('outcome_fields_in_selection_freeze')
            except (ValueError, TypeError, AttributeError):
                errors.append('invalid_frozen_candidate_original')
        errors.extend(_comparison_source_errors(row, freeze, contents, as_of=as_of))
        for field in ('capital_base', 'net_cash_flow', 'exposure', 'turnover', 'gross_ret', 'cost_ret',
                      'net_ret', 'decision_latency_seconds', 'execution_latency_seconds'):
            if _number(row.get(field)) is None:
                errors.append(f'{field}_missing_or_nonfinite')
        if _number(row.get('capital_base')) is not None and float(row['capital_base']) <= 0:
            errors.append('invalid_capital_base')
        if row.get('runtime') not in ('paper', 'live') or row.get('book') != 'B':
            errors.append('book_runtime_identity_missing')
        if _fill_class(row) != 'confirmed_window' and row.get('fill_basis') != 'broker_confirmed':
            errors.append('proxy_or_unknown_fill')
        if row.get('runtime') == 'live' and row.get('fill_basis') != 'broker_confirmed':
            errors.append('app_cannot_consume_paper_fill')
        if row.get('runtime') == 'paper' and row.get('fill_basis') == 'broker_confirmed':
            errors.append('paper_cannot_consume_app_fill')
        if row.get('return_basis') != 'per_trade_net' or row.get('net_cash_flow') != 0:
            errors.append('cashflow_adjusted_paired_trade_basis_required')
        if all(_number(row.get(field)) is not None for field in ('gross_ret', 'cost_ret', 'net_ret')):
            if row['cost_ret'] < 0 or abs(row['gross_ret']-row['cost_ret']-row['net_ret']) > 1e-9:
                errors.append('cost_net_identity_mismatch')
        if any(row.get(field) is not None and _number(row[field]) is not None and row[field] < 0
               for field in ('exposure', 'turnover', 'decision_latency_seconds', 'execution_latency_seconds')):
            errors.append('negative_exposure_turnover_or_latency')
        facts = (day, outcome_day, digest, row.get('capital_base'), row.get('book'), row.get('runtime'))
        if sample in reference and reference[sample] != facts:
            errors.append('paired_frozen_cohort_or_budget_mismatch')
        reference[sample] = facts
    for sample in expected:
        if any((str(sample), option) not in indexed for option in OPTIONS):
            errors.append('incomplete_three_option_coverage')
    errors = sorted(set(errors))
    options = []
    for option in OPTIONS:
        selected = [indexed[(str(s), option)] for s in expected if (str(s), option) in indexed]
        result = dict(option=option, n_samples=len(selected), conclusion='insufficient_evidence',
                      mean_net_ret=None, mean_cost_ret=None, evidence=evidence)
        if not errors and selected:
            values = [row['net_ret'] for row in selected]
            train = [row for row in selected if row['day'] <= train_end]
            test = [row for row in selected if row['day'] >= test_start]
            if len(train)+len(test) != len(selected):
                errors.append('rows_outside_train_test_split')
            result.update(mean_net_ret=sum(values)/len(values), worst_net_ret=min(values),
                mean_cost_ret=sum(row['cost_ret'] for row in selected)/len(selected),
                mean_exposure=sum(row['exposure'] for row in selected)/len(selected),
                mean_turnover=sum(row['turnover'] for row in selected)/len(selected),
                net_cash_flow=sum(row['net_cash_flow'] for row in selected),
                mean_decision_latency_seconds=sum(row['decision_latency_seconds'] for row in selected)/len(selected),
                mean_execution_latency_seconds=sum(row['execution_latency_seconds'] for row in selected)/len(selected),
                train_samples=len(train), test_samples=len(test))
            if option != OPTIONS[0]:
                paired = [dict(day=row['day'], strat_ret=row['net_ret'],
                    base_ret=indexed[(str(row['sample_id']), OPTIONS[0])]['net_ret']) for row in selected]
                # Guard's split is chronological half of independent days. The saved
                # design must match it rather than silently moving its OOS boundary.
                days = sorted({row['day'] for row in selected})
                if days[:len(days)//2] != sorted({row['day'] for row in train}):
                    errors.append('declared_split_does_not_match_guard')
                result['guard_result'] = guards.evaluate_hypothesis(paired, n_tried=int(n_tried), cache_only=True)
                result['conclusion'] = ('supported' if result['guard_result']['verdict'] == 'PASS'
                    else 'insufficient_evidence' if result['guard_result']['n_days'] < 8 else 'rejected')
            else:
                result['conclusion'] = 'baseline_observed'
        options.append(result)
    if errors:
        for result in options:
            result.update(conclusion='insufficient_evidence', mean_net_ret=None)
    return dict(comparison_id=data.get('comparison_id'), evidence=evidence,
                conclusion='insufficient_evidence' if errors else 'evaluated', options=options,
                missing_evidence=sorted(set(errors)), future_rows_excluded=future_rows,
                semantics='per-trade net fractional returns; no compounded portfolio return or causal certification')


def _research_runs(contents: dict[str, bytes], *, as_of: dt.date) -> list[dict]:
    results = []
    for path in sorted(p for p in contents if p.endswith('/manifest.json')):
        manifests = _load(contents, path)
        if not manifests:
            results.append(dict(path=path, conclusion='insufficient_evidence', missing_evidence=['invalid_manifest']))
            continue
        manifest = manifests[0]
        observed = _date(manifest.get('created_at'))
        if observed and observed > as_of.isoformat():
            continue
        errors = []
        artifact_paths = {}
        for kind, default in (('trades', 'trades.jsonl'), ('verdict', 'verdict.json')):
            named = manifest.get('artifacts', {}).get(kind, default)
            # Resolve existing recorded root-relative refs, otherwise the copied
            # artifact beside its immutable run manifest; never follow external paths.
            candidate = str(named)
            artifact_paths[kind] = candidate if candidate in contents else str(Path(path).parent / Path(candidate).name)
            if artifact_paths[kind] not in contents:
                errors.append(f'{kind}_artifact_missing')
        trades = _load(contents, artifact_paths['trades'])
        expected_hash = manifest.get('inputs', {}).get('trades_sha256')
        if expected_hash != _hash(contents.get(artifact_paths['trades'], b'')):
            errors.append('trades_checksum_mismatch')
        if manifest.get('inputs', {}).get('n_rows') != len(trades):
            errors.append('trade_count_mismatch')
        if not observed:
            errors.append('run_observation_date_missing')
        if not manifest.get('protocol_id'):
            errors.append('protocol_missing')
        params = manifest.get('parameters', {})
        if params.get('cache_only') is not True:
            errors.append('cache_only_proof_missing')
        if any(not _date(row.get('day')) or row['day'] > as_of.isoformat() for row in trades):
            errors.append('future_or_undated_trades')
        # Old run artifacts retain their recorded verdict, but returns-only rows
        # cannot certify costs, selection chronology, fills or portfolio cash flows.
        if not manifest.get('evidence', {}).get('comparison_path'):
            errors.append('paired_cost_fill_chronology_comparison_missing')
        verdicts = _load(contents, artifact_paths['verdict'])
        recorded = manifest.get('verdict', {}).get('status')
        actual = verdicts[0].get('verdict') if verdicts else None
        if actual != recorded:
            errors.append('recorded_verdict_mismatch')
        results.append(dict(path=path, sha256=_hash(contents[path]), hypothesis_id=manifest.get('hypothesis_id'),
            observed_date=observed, recorded_verdict=recorded, conclusion='insufficient_evidence',
            n_rows=len(trades), n_days=len({r.get('day') for r in trades}),
            parameters=params, diagnostics=manifest.get('diagnostics', {}),
            recorded_metrics=verdicts[0] if verdicts else {}, missing_evidence=errors,
            scope='recorded_run_not_a_new_research_verdict'))
    return results


def build_weekly_evidence(root: Path, *, as_of: dt.date, snapshot_dir: Path | None = None) -> dict:
    manifest, contents = _capture(root, snapshot_dir)
    manifest_path = None
    if snapshot_dir is not None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = snapshot_dir / (manifest['sha256'] + '.manifest.json')
        manifest_bytes = _canonical(manifest)
        try:
            with manifest_path.open('xb') as stream:
                stream.write(manifest_bytes)
        except FileExistsError:
            if manifest_path.read_bytes() != manifest_bytes:
                raise ValueError('immutable input manifest corrupted')
    refs = {item['path']: {key: item[key] for key in ('path', 'sha256') if key in item}
            for item in manifest['files']}
    comparisons = []
    for path in sorted(p for p in contents if Path(p).name.startswith('weekly_comparison') and p.endswith('.json')):
        rows = _load(contents, path)
        comparisons.append(_comparison(rows[0] if rows else {}, as_of=as_of, evidence=refs[path], contents=contents))
    hypotheses = {}
    for row in _load(contents, 'kronos_screen/HYPOTHESES.jsonl'):
        observed = _date(row.get('ts'))
        if not observed or observed > as_of.isoformat() or not row.get('id'):
            continue
        # Ledger is append-only but sort by real observation time for as-of truth.
        if row['id'] not in hypotheses or row['ts'] > hypotheses[row['id']]['observed_at']:
            hypotheses[row['id']] = dict(hypothesis_id=row['id'], claim=row.get('claim'),
                observed_at=row['ts'], recorded_verdict=row.get('verdict'), metrics=row.get('metrics', {}),
                rejected_by=row.get('rejected_by', []), conclusion='insufficient_evidence',
                evidence=refs['kronos_screen/HYPOTHESES.jsonl'],
                scope='historical_verdict_not_this_week', missing_evidence=['immutable_run_and_full_attribution_required'])
    runs = _research_runs(contents, as_of=as_of)
    empty_options = [dict(option=option, conclusion='insufficient_evidence', mean_net_ret=None,
                          missing_evidence=['saved_three_option_paired_comparison_missing']) for option in OPTIONS]
    missing = [item['path'] for item in manifest['files'] if item['status'] == 'invalid']
    if not comparisons:
        missing.append('saved_three_option_paired_comparison_missing')
    missing.extend(error for comparison in comparisons for error in comparison['missing_evidence'])
    proposals = []
    for identity, objective, falsifier, evidence in (
        ('paired-options', '冻结同一候选、预算与 OOS 分割，比较无 KOL / 有界 KOL / 挑战者',
         '费用后改善不能在 OOS 保留，或只由单周/单赢家/缩仓解释',
         ['expected_sample_ids', 'frozen_candidates_sha256', 'selection/outcome clocks', 'three-option net costs']),
        ('proxy-fill', '量化缺分钟窗口及实时重试代理对纸面结论的敏感度',
         '剔除代理后样本不足或优势消失，则不能称为已确认可执行改善',
         ['saved fill basis/fallback', 'same-cohort confirmed-window sensitivity', 'missing-window counts']),
        ('cashflow-time', '分账户验证资金划拨、费用与延迟对收益的影响',
         '无法闭合净投入/净值/费用或缺自然运行时刻，则不认定收益或速度提升',
         ['dated accounting statements', 'capital flow chain', 'source/decision/order/fill timestamps']),
    ):
        proposals.append(dict(experiment_id=f'weekly-evidence-{as_of.isoformat()}-{identity}', objective=objective,
            falsifier=falsifier, required_evidence=evidence, status='proposed_not_run', owner='weekly research owner',
            next_review=(as_of+dt.timedelta(days=7)).isoformat(),
            rollback='retain current strategy; remove only isolated research experiment artifacts',
            auto_apply_eligible=False))
    accounting = []
    for path in sorted(p for p in contents if '/accounting_reports/' in p):
        values = _load(contents, path)
        value = values[0] if values else {}
        # The native statement export nests its dated mark under valuation;
        # filename/hash and the export's current wall clock are not mark dates.
        valuation = value.get('valuation') if isinstance(value.get('valuation'), dict) else value
        observed_at = valuation.get('observed_at') or valuation.get('as_of')
        day = _date(observed_at or valuation.get('trade_date') or valuation.get('date'))
        if not day:
            missing.append(f'accounting_report_undated:{path}')
            continue
        if day > as_of.isoformat():
            continue
        accounting.append(dict(evidence=refs[path], report=value, valuation=valuation,
            observed_at=observed_at, valuation_status=value.get('valuation_status', 'not_recorded'),
            profit_attribution='not_established',
            missing_evidence=['full dated settlement/capital-flow chain and actual-fee verification required']))
    return dict(schema_version=1, as_of=as_of.isoformat(), authority='research_observer_only',
        status='evaluated' if comparisons and not missing else 'insufficient_evidence',
        input_manifest=manifest, snapshot_manifest_path=str(manifest_path.resolve()) if manifest_path else None,
        hypotheses=list(hypotheses.values()), research_runs=runs,
        option_comparison=dict(options=empty_options if not comparisons else [], comparisons=comparisons),
        paper_fill_audit=_fill_audit(contents, as_of), accounting_observations=accounting,
        missing_evidence=sorted(set(missing)), exploration_proposals=proposals,
        promotion=dict(auto_promote=False, writes_verdict_ledger=False, changes_strategy=False),
        limitations=['saved observations are not independent broker/source verification',
                     'A/B identical-entry exit difference is descriptive exit evidence, never KOL selection alpha',
                     'overlapping 1/4/12-week windows are not independent OOS samples',
                     'cash movements are not profit; absent accounting and actual fees remain unknown'])


def render_weekly_evidence(report: dict) -> list[str]:
    if not report:
        return ['- 缺少冻结研究证据；收益、成本与样本外结论未知。']
    labels = {'supported': '支持（限定已保存样本）', 'rejected': '拒绝',
              'insufficient_evidence': '证据不足', 'baseline_observed': '基线观测'}
    lines = ['## 数据证据与方案比较', '',
             f"- 输入清单 sha256=`{report['input_manifest']['sha256']}`；捕获 {len(report['input_manifest']['files'])} 个文件；缺失模式 {len(report['input_manifest']['missing_patterns'])} 项。",
             '- 结论只约束已保存样本，不自动升级策略；配对 A/B 出场差不解释为 KOL 选股 alpha。', '',
             '| 比较 / 方案 | 结论 | 样本 | 净收益均值 | 成本均值 | OOS | 判断/执行秒 |',
             '|---|---|---:|---:|---:|---|---|']
    groups = report['option_comparison']['comparisons']
    for group in groups or [dict(comparison_id='未提供', options=report['option_comparison']['options'])]:
        for option in group['options']:
            pct = lambda value: 'N/A' if value is None else f'{value*100:.3f}%'
            wf = option.get('guard_result', {}).get('walk_forward', {})
            oos = f"train={wf['train_edge']:.6f}, test={wf['test_edge']:.6f}" if wf else 'N/A'
            latency = f"{option.get('mean_decision_latency_seconds', 'N/A')}/{option.get('mean_execution_latency_seconds', 'N/A')}"
            lines.append(f"| {group['comparison_id']} / {option['option']} | {labels[option['conclusion']]} | {option.get('n_samples', 'N/A')} | {pct(option.get('mean_net_ret'))} | {pct(option.get('mean_cost_ret'))} | {oos} | {latency} |")
        if group.get('missing_evidence'):
            lines.append('- 对照缺口：'+'；'.join(group['missing_evidence']))
    lines += ['', '### 已记录假设与研究运行', '']
    if not report['hypotheses'] and not report['research_runs']:
        lines.append('- 未提供可读的假设裁决或研究运行。')
    for row in report['hypotheses']:
        metrics = row['metrics']
        lines.append(f"- `{row['hypothesis_id']}`：历史记录 {row['recorded_verdict']}（{row['observed_at']}）；本次复核 {labels[row['conclusion']]}；n_days={metrics.get('n_days', 'N/A')}，train/test={metrics.get('train_edge', 'N/A')}/{metrics.get('test_edge', 'N/A')}。")
    for row in report['research_runs']:
        lines.append(f"- 研究 `{row['path']}`：记录 {row.get('recorded_verdict', 'N/A')}，本次 {labels[row['conclusion']]}；缺口：{'；'.join(row['missing_evidence']) or '尚未完成独立归因复核'}。")
    lines += ['', '### 纸面成交证据与资金口径', '']
    for window, audit in report['paper_fill_audit']['windows'].items():
        proportion = audit['fallback_proportion']
        fraction = 'N/A' if proportion is None else f'{proportion:.1%}'
        lines.append(f"- {window}：独立入场 {audit['entry_count']}，窗口证据 {audit['confirmed_window_count']}，fallback {audit['fallback_count']}（{fraction}），全部代理 {audit['proxy_count']}，未知 {audit['unknown_count']}；代理/未知不进入已确认可执行收益。")
    lines.append(f"- APP 已保存会计观测 {len(report['accounting_observations'])} 份；资金划拨不计利润，缺完整净值/现金流/实际费用时不计算账户收益。")
    for observation in report['accounting_observations']:
        value = observation['valuation']
        lines.append(f"- 会计观测 {observation['observed_at']}：净投入 {value.get('net_contributed_capital', 'N/A')}，标记净值 {value.get('marked_nav', 'N/A')}，累计盈亏 {value.get('cumulative_pnl') if value.get('cumulative_pnl') is not None else 'N/A'}，已实现/浮动 {value.get('realized_pnl', 'N/A')}/{value.get('unrealized_pnl', 'N/A')}；费用 {value.get('fee_basis', 'unknown')}，状态 {value.get('status', 'unknown')}（已保存观测，未认证收益）。")
    lines += ['', '### 下一步探索（提案，未运行）', '']
    for proposal in report['exploration_proposals']:
        lines.append(f"- `{proposal['experiment_id']}`：{proposal['objective']}；证伪：{proposal['falsifier']}；负责人 {proposal['owner']}；复核 {proposal['next_review']}；回滚 {proposal['rollback']}。")
    return lines
