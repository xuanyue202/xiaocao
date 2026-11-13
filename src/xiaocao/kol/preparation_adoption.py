"""Bind shared source reasoning to a Paper owner, without adopting APP policy."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from . import opening_preparation as prep
from .publication import canonical_sha256
from .trading_decision import read_json
from xiaocao.runner_recovery import _hash


def adoption(preparation_path: Path, current_input_path: Path, *, now: datetime,
             judgment_mode: str | None = None) -> dict:
    prepared = prep.read_preparation(preparation_path, now=now)
    current, projection = prep._inputs(current_input_path)
    source = prepared['binding']
    consumer = current['binding']
    paper = consumer.get('automation_id') == 'xiaocao-daily-morning-execution'
    live = consumer.get('automation_id') == 'xiaocao-book-b-live-morning'
    rolling = prepared.get('schema_version') == 'kol-opening-preparation.v2'
    from xiaocao.live.morning_support import preparation_timing, CURRENT_CONDITIONAL
    timing = preparation_timing(prep.aware(prepared['accepted_at']), consumer['trade_date'],
                                mode=judgment_mode) if rolling else 'prepared_on_time'
    if paper:
        from xiaocao.live.paper_morning_kol import owner_binding
        if owner_binding(current_input_path.parent, consumer['trade_date']) != consumer:
            raise ValueError('KOL_PREPARATION_ADOPTION_OWNER_MISMATCH')
    elif (not live or not rolling or consumer.get('automation_id') != os.environ.get('CODEX_AUTOMATION_ID')
            or consumer.get('owner_thread_id') != os.environ.get('CODEX_THREAD_ID')
            or consumer.get('runner_pid') != os.getpid()):
        raise ValueError('KOL_PREPARATION_ADOPTION_OWNER_MISMATCH')
    if ((not rolling and (source.get('automation_id') != 'xiaocao-book-b-live-morning'
                         or not paper or source['trade_date'] != consumer['trade_date']))
            or (rolling and source.get('automation_id') != 'xiaocao-kol-hourly-low-bandwidth-operation')
            or (paper and not consumer.get('run_id'))
            or now.astimezone(prep.TZ).date().isoformat() != consumer['trade_date']
            or prep.aware(projection['as_of']) > now
            or prep.aware(projection['as_of']) < prep.aware(prepared['accepted_at'])
            or [r['sha256'] for r in prepared['rules']] != [r['sha256'] for r in current['rules']]):
        raise ValueError('KOL_PREPARATION_ADOPTION_BINDING_INVALID')
    if not rolling and (prepared['source_fingerprint'] != current['source_fingerprint']
            or prep.viewpoint_units(prep.read_projection(prepared['projection'])) != prep.viewpoint_units(projection)):
        raise ValueError('KOL_PREPARATION_ADOPTION_SOURCE_CHANGED')
    value = {'schema_version': 'kol-preparation-adoption.v1', 'authority': 0,
        'binding': consumer, 'source_binding': source,
        'preparation_path': str(preparation_path.resolve()),
        'preparation_sha256': prepared['preparation_sha256'],
        'current_input_path': str(current_input_path.resolve()), 'current_input_sha256': _hash(current),
        'source_fingerprint': current['source_fingerprint'], 'adopted_at': now.isoformat(),
        'scope': 'conditional_source_reasoning_only', 'policy_adoption': 'not_performed'}
    if judgment_mode == CURRENT_CONDITIONAL:
        value.update(schema_version='kol-preparation-adoption.v2', judgment_mode=judgment_mode,
                     preparation_timing=timing)
    return {**value, 'adoption_sha256': canonical_sha256(value)}


def read_adoption(path: Path, preparation_path: Path, current_input_path: Path, *, now: datetime) -> dict:
    if path.is_symlink():
        raise ValueError('KOL_PREPARATION_ADOPTION_SYMLINK')
    value = read_json(path)
    if (value.get('adoption_sha256') != canonical_sha256(
            {k: v for k, v in value.items() if k != 'adoption_sha256'})
            or now < prep.aware(value['adopted_at'])
            or value != adoption(preparation_path, current_input_path, now=prep.aware(value['adopted_at']),
                                 judgment_mode=value.get('judgment_mode'))):
        raise ValueError('KOL_PREPARATION_ADOPTION_ALTERED')
    prep.read_preparation(preparation_path, now=now)
    return value
