"""Reuse complete accepted source reasoning; expose every current source delta."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from . import opening_preparation as prep
from .rolling_preparation import registered


def packet(preparation_path: Path, summary: dict, *, now: datetime) -> dict:
    prepared = prep.read_preparation(preparation_path, now=now)
    projection = prep.read_projection(summary)
    if prep.aware(projection['as_of']) > now:
        raise ValueError('KOL_PREPARATION_FUTURE_CURRENT_PROJECTION')
    previous = prep.read_projection(prepared['projection'])
    if prep.aware(projection['as_of']) < prep.aware(previous['as_of']):
        raise ValueError('KOL_PREPARATION_STALE_CURRENT_PROJECTION')
    if projection['quality']['status'] != 'ready':
        raise ValueError('KOL_PREPARATION_SOURCE_COVERAGE_DEGRADED')
    old = prep.viewpoint_units(previous)
    new = prep.viewpoint_units(projection)
    changed = {i for i in old.keys() & new.keys()
               if prep.canonical_sha256(old[i]) != prep.canonical_sha256(new[i])}
    added, removed = new.keys()-old.keys(), old.keys()-new.keys()
    invalid = changed | removed
    invalid_reports = {old[i]['viewpoint']['report_id'] for i in invalid}
    draft = prepared['draft']
    def split(rows, predicate):
        return [r for r in rows if not predicate(r)], [r for r in rows if predicate(r)]
    implications, invalidated = split(draft['implications'], lambda r: bool(set(r['viewpoint_ids']) & invalid))
    synthesis, invalid_synthesis = split(draft.get('synthesis', []), lambda r: bool(set(r['viewpoint_ids']) & invalid))
    preferences, invalid_preferences = split(draft.get('selection_preferences', []), lambda r: r['source_report_id'] in invalid_reports)
    context_path = prep.write_artifact(preparation_path.parent, prepared['context'], '.shared-context.json')
    value = {'schema_version':'kol-shared-current-packet.v1', 'authority':0,
        'observed_at':now.isoformat(), 'preparation_path':str(preparation_path.resolve()),
        'preparation_sha256':prepared['preparation_sha256'],
        'source_fingerprint':projection['source_fingerprint'], 'current_projection':summary,
        'context_path':str(context_path), 'context_sha256':prepared['context']['context_sha256'],
        'source_coverage_limits':draft.get('source_coverage_limits', []),
        'implications':implications, 'invalidated_implications':invalidated,
        'synthesis':synthesis, 'invalidated_synthesis':invalid_synthesis,
        'selection_preferences':preferences, 'invalidated_selection_preferences':invalid_preferences,
        'followup_conditions':draft.get('followup_conditions', []),
        'policy_template':draft.get('policy_template'),
        'policy_template_reusable':not (added or changed or removed),
        'coverage':{'prepared_count':len(old), 'current_count':len(new),
                    'unchanged_count':len((old.keys() & new.keys())-changed),
                    'prepared_coverage_sha256':prep.canonical_sha256(draft['coverage'])},
        'delta':{'added':sorted(added), 'changed':sorted(changed), 'removed':sorted(removed),
            'units':{i:new[i] for i in sorted(added|changed)},
            'relation_history':prep.relation_history(projection) if added or changed or removed else {}},
        'policy_adoption':'not_performed', 'current_source_verification':'not_performed'}
    return {**value, 'packet_sha256':prep.canonical_sha256(value)}


def build(root: Path, *, now: datetime) -> dict:
    from .trading_context import build_trading_context, write_trading_projection
    source = registered(root, now=now)
    if source is None:
        raise ValueError('KOL_PREPARATION_SHARED_UNAVAILABLE')
    summary = write_trading_projection(build_trading_context(repo_root=root,
        as_of=now, read_report_ids=[], include_report_bodies=False), repo_root=root)
    return packet(source[0], summary, now=now)
