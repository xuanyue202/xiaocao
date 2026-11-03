"""Bind shared source reasoning to a Paper owner, without adopting APP policy."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import opening_preparation as prep
from .publication import canonical_sha256
from .trading_decision import read_json
from xiaocao.runner_recovery import _hash


def adoption(preparation_path: Path, current_input_path: Path, *, now: datetime) -> dict:
    prepared = prep.read_preparation(preparation_path, now=now)
    current, projection = prep._inputs(current_input_path)
    source = prepared['binding']
    consumer = current['binding']
    from xiaocao.live.paper_morning_kol import owner_binding
    if owner_binding(current_input_path.parent, consumer['trade_date']) != consumer:
        raise ValueError('KOL_PREPARATION_ADOPTION_OWNER_MISMATCH')
    if (source.get('automation_id') != 'xiaocao-book-b-live-morning'
            or consumer.get('automation_id') != 'xiaocao-daily-morning-execution'
            or not consumer.get('run_id') or source['trade_date'] != consumer['trade_date']
            or now.astimezone(prep.TZ).date().isoformat() != consumer['trade_date']
            or prep.aware(projection['as_of']) > now
            or prep.aware(projection['as_of']) < prep.aware(prepared['accepted_at'])
            or [r['sha256'] for r in prepared['rules']] != [r['sha256'] for r in current['rules']]):
        raise ValueError('KOL_PREPARATION_ADOPTION_BINDING_INVALID')
    if (prepared['source_fingerprint'] != current['source_fingerprint']
            or prep.viewpoint_units(prep.read_projection(prepared['projection'])) != prep.viewpoint_units(projection)):
        raise ValueError('KOL_PREPARATION_ADOPTION_SOURCE_CHANGED')
    value = {'schema_version': 'kol-preparation-adoption.v1', 'authority': 0,
        'binding': consumer, 'source_binding': source,
        'preparation_path': str(preparation_path.resolve()),
        'preparation_sha256': prepared['preparation_sha256'],
        'current_input_path': str(current_input_path.resolve()), 'current_input_sha256': _hash(current),
        'source_fingerprint': current['source_fingerprint'], 'adopted_at': now.isoformat(),
        'scope': 'conditional_source_reasoning_only', 'policy_adoption': 'not_performed'}
    return {**value, 'adoption_sha256': canonical_sha256(value)}


def read_adoption(path: Path, preparation_path: Path, current_input_path: Path, *, now: datetime) -> dict:
    if path.is_symlink():
        raise ValueError('KOL_PREPARATION_ADOPTION_SYMLINK')
    value = read_json(path)
    if (value.get('adoption_sha256') != canonical_sha256(
            {k: v for k, v in value.items() if k != 'adoption_sha256'})
            or now < prep.aware(value['adopted_at'])
            or value != adoption(preparation_path, current_input_path, now=prep.aware(value['adopted_at']))):
        raise ValueError('KOL_PREPARATION_ADOPTION_ALTERED')
    prep.read_preparation(preparation_path, now=now)
    return value
