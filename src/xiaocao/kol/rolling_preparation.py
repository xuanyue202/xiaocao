"""Shared pre-market reasoning over published semantics, with no account authority."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path

from . import opening_preparation as prep
from .publication import canonical_sha256
from .trading_decision import read_json

SCHEMA = 'kol-opening-preparation.v2'
OWNER = 'xiaocao-kol-hourly-low-bandwidth-operation'
DIRECTORY = 'output/live/kol_rolling_preparations'
CATALOG = ('src/xiaocao/strategy/rules.py', 'src/xiaocao/strategy/params.py')
INSTRUCTIONS = ('.codex/skills/xiaocao-trading/references/kol-rolling-preparation.md',
                '.codex/skills/xiaocao-trading/references/kol-preopen-program.md')


def input_payload(summary: dict, *, binding: dict, repo_root: Path,
                  intended_use_at: str | None = None) -> dict:
    """The timeline is provenance, never a name/keyword-based trading filter."""
    if binding.get('automation_id') != OWNER:
        raise ValueError('KOL_PREPARATION_ROLLING_OWNER_REQUIRED')
    value = prep.input_payload(summary, binding=binding, repo_root=repo_root)
    projection = prep.read_projection(summary)
    timeline = {}
    for row in projection['active_viewpoints']:
        if row.get('kol_id') == 'kol-xiaocao':
            key = (row['source_published_at'], row['report_id'])
            timeline.setdefault(key, []).append(row['record_id'])
    value.update(preparation_kind='rolling', source_cutoff=projection['as_of'],
        xiaocao_timeline=[{'source_published_at': clock, 'report_id': rid,
                          'viewpoint_ids': sorted(ids)}
                         for (clock, rid), ids in sorted(timeline.items())],
        decision_catalog=[{'path': str((repo_root / relative).resolve()),
            'sha256': hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()}
            for relative in CATALOG],
        instruction_refs=[{'path': str((repo_root / relative).resolve()),
            'sha256': hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()}
            for relative in INSTRUCTIONS],
        instruction='Synthesize Xiaocao chronology, continuity, revisions and conflicts before market data. '
                    'Cover every eligible published viewpoint; resolve canonical mappings before opening. '
                    'Keep current-market conditions explicit and unknown. Derived reasoning only; authority=0.')
    if intended_use_at is not None:
        readiness = source_readiness(projection, through=prep.aware(intended_use_at))
        value.update(intended_use_at=intended_use_at, source_readiness=readiness)
    return value


def source_readiness(projection: dict, *, through: datetime) -> dict:
    """Forecast original validity before dispatch; never renew or drop a source."""
    evaluations = {row['evaluation']['viewpoint_id']: row['evaluation']
                   for row in projection.get('latest_evaluations', [])}
    expired, missing, expiries = [], [], []
    for row in projection['active_viewpoints']:
        identifier = row['record_id']
        expiry = evaluations.get(identifier, {}).get('trading_applicability', {}).get('valid_until')
        if expiry is None:
            missing.append(identifier)
            continue
        stamp = prep.aware(expiry)
        expiries.append(stamp)
        if stamp <= through:
            expired.append(identifier)
    return {'status': 'ready' if not expired and not missing else 'blocked',
        'fresh_through': through.isoformat(), 'eligible_count': len(projection['active_viewpoints']),
        'earliest_original_expiry': min(expiries).isoformat() if expiries else None,
        'expired_before_use_count': len(expired), 'expired_before_use': sorted(expired),
        'missing_expiry': sorted(missing), 'authority': 0}


def validate_inputs(inputs: dict, projection: dict) -> None:
    if (inputs['binding'].get('automation_id') != OWNER
            or inputs.get('source_cutoff') != projection['as_of']):
        raise ValueError('KOL_PREPARATION_ROLLING_SOURCE_INVALID')
    expected = input_payload(inputs['projection'], binding=inputs['binding'],
                             repo_root=Path(inputs['rules'][0]['path']).parents[1],
                             intended_use_at=inputs.get('intended_use_at'))
    if inputs != expected:
        raise ValueError('KOL_PREPARATION_ROLLING_INPUT_ALTERED')
    if inputs.get('source_readiness', {}).get('status') == 'blocked':
        raise ValueError('KOL_PREPARATION_SOURCE_EXPIRES_BEFORE_USE')
    cutoff = prep.aware(inputs['source_cutoff'])
    if any(prep.aware(row['source_published_at']) > cutoff for row in projection['active_viewpoints']):
        raise ValueError('KOL_PREPARATION_ROLLING_FUTURE_SOURCE')
    if any(prep.aware(row['evaluation']['evaluated_at']) > cutoff
           for row in projection.get('latest_evaluations', [])):
        raise ValueError('KOL_PREPARATION_ROLLING_FUTURE_EVALUATION')


def validate_synthesis(draft: dict, inputs: dict, projection: dict, now: datetime) -> set[str]:
    prepared, until = prep.aware(draft['prepared_at']), prep.aware(draft['valid_until'])
    if not (prep.aware(inputs['source_cutoff']) <= prepared <= now < until <= prepared + timedelta(hours=24)):
        raise ValueError('KOL_PREPARATION_ROLLING_TIME_INVALID')
    if inputs.get('intended_use_at') and until <= prep.aware(inputs['intended_use_at']):
        raise ValueError('KOL_PREPARATION_BRIEF_EXPIRES_BEFORE_USE')
    rows = {row['record_id']: row for row in projection['active_viewpoints']}
    required = {identifier for group in inputs['xiaocao_timeline'] for identifier in group['viewpoint_ids']}
    synthesis = draft.get('synthesis')
    if not isinstance(synthesis, list) or (required and not synthesis):
        raise ValueError('KOL_PREPARATION_ROLLING_SYNTHESIS_REQUIRED')
    if (not isinstance(draft.get('source_coverage_limits'), list) or not draft['source_coverage_limits']
            or any(not isinstance(item, str) or not item.strip() for item in draft['source_coverage_limits'])):
        raise ValueError('KOL_PREPARATION_ROLLING_COVERAGE_LIMITS_REQUIRED')
    covered, reports, identifiers = set(), set(), set()
    for item in synthesis:
        sources = item.get('viewpoint_ids')
        if (not isinstance(item.get('id'), str) or not item['id'].strip() or item['id'] in identifiers
                or not isinstance(sources, list) or not sources or len(sources) != len(set(sources))
                or not set(sources) <= rows.keys()
                or any(not isinstance(item.get(key), str) or not item[key].strip() for key in
                       ('judgment', 'evolution', 'conditions', 'invalidations', 'counterevidence'))):
            raise ValueError('KOL_PREPARATION_ROLLING_SYNTHESIS_INVALID')
        identifiers.add(item['id'])
        covered.update(sources)
        reports.update(rows[identifier]['report_id'] for identifier in sources)
    if not required <= covered:
        raise ValueError('KOL_PREPARATION_ROLLING_XIAOCAO_COVERAGE_INCOMPLETE')
    return reports


def validate_current_sources(prepared: dict, *, now: datetime) -> None:
    """Unchanged source hashes do not renew a viewpoint's original expiry."""
    projection = prep.read_projection(prepared['projection'])
    active = {row['record_id'] for row in projection['active_viewpoints']}
    evaluations = {row['evaluation']['viewpoint_id']: row['evaluation']
                   for row in projection.get('latest_evaluations', [])}
    if any(identifier not in evaluations or prep.aware(evaluations[identifier]
            ['trading_applicability']['valid_until']) <= now for identifier in active):
        raise ValueError('KOL_PREPARATION_ROLLING_SOURCE_EXPIRED')


def register(input_path: Path, path: Path, prepared: dict) -> None:
    binding = prepared['binding']
    if (prepared.get('schema_version') != SCHEMA or binding.get('automation_id') != OWNER
            or os.environ.get('CODEX_AUTOMATION_ID') != OWNER
            or os.environ.get('CODEX_THREAD_ID') != binding.get('owner_thread_id')
            or input_path.resolve() != Path(prepared['input_path']).resolve()):
        raise ValueError('KOL_PREPARATION_ROLLING_OWNER_MISMATCH')
    root = Path(prepared['rules'][0]['path']).parents[1]
    prep.write_artifact(root / DIRECTORY, {
        'schema_version': 'kol-rolling-preparation-reference.v1', 'authority': 0,
        'binding': binding, 'preparation_path': str(path.resolve()),
        'preparation_sha256': prepared['preparation_sha256'],
        'source_fingerprint': prepared['source_fingerprint'],
        'accepted_at': prepared['accepted_at'], 'valid_until': prepared['draft']['valid_until']}, '.json')


def registered(root: Path, *, now: datetime) -> tuple[Path, dict] | None:
    """Read the newest valid source brief; never poll or contact its writer."""
    references = []
    for path in (root / DIRECTORY).glob('*.json'):
        reference = read_json(path)
        if (path.is_symlink() or path.name != canonical_sha256(reference) + '.json'
                or reference.get('authority') != 0
                or reference.get('schema_version') != 'kol-rolling-preparation-reference.v1'):
            raise ValueError('KOL_PREPARATION_ROLLING_REFERENCE_INVALID')
        if prep.aware(reference['accepted_at']) <= now < prep.aware(reference['valid_until']):
            references.append(reference)
    if not references:
        return None
    latest = max(prep.aware(row['accepted_at']) for row in references)
    newest = [row for row in references if prep.aware(row['accepted_at']) == latest]
    if len(newest) != 1:
        raise ValueError('KOL_PREPARATION_ROLLING_REFERENCE_AMBIGUOUS')
    ref = newest[0]
    path = Path(ref['preparation_path'])
    prepared = prep.read_preparation(path, now=now)
    if (prepared.get('schema_version') != SCHEMA or ref['binding'] != prepared['binding']
            or ref['preparation_sha256'] != prepared['preparation_sha256']
            or ref['source_fingerprint'] != prepared['source_fingerprint']
            or ref['accepted_at'] != prepared['accepted_at']
            or ref['valid_until'] != prepared['draft']['valid_until']):
        raise ValueError('KOL_PREPARATION_ROLLING_REFERENCE_BINDING_INVALID')
    return path, prepared
