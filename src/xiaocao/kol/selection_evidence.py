"""Verify source quotations and canonical sector maps before sealing preferences."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .selection import SelectionError, validate_preferences


def verify_preference_sources(preferences: list[dict], reports: dict[str, dict], *, as_of: datetime) -> None:
    validate_preferences(preferences)
    for preference in preferences:
        report = reports.get(preference['source_report_id'])
        if report is None or preference['source_quote'] not in report.get('report_body', ''):
            raise SelectionError('SELECTION_SOURCE_QUOTE_UNPROVEN')
        if preference['kind'] != 'sector':
            continue
        target = preference['target']
        reference = target['mapping_ref']
        path = Path(reference['path'])
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise SelectionError('SELECTION_SECTOR_MAP_FILE_INVALID')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['sha256']:
            raise SelectionError('SELECTION_SECTOR_MAP_HASH_MISMATCH')
        value = json.loads(raw)
        observed = datetime.fromisoformat(value['observed_at'].replace('Z', '+00:00'))
        if (value.get('schema_version') != 'kol-sector-map.v1' or observed.utcoffset() is None
                or observed > as_of or not isinstance(value.get('source_ref'), str)
                or not value['source_ref'].strip()):
            raise SelectionError('SELECTION_SECTOR_MAP_PROVENANCE_REQUIRED')
        entries = value.get('entries', [])
        matching = [entry for entry in entries if entry.get('field') == target['field']
                    and entry.get('code') == target['code']]
        if len(matching) != 1 or matching[0].get('name') != target['name']:
            raise SelectionError('SELECTION_SECTOR_MAP_AMBIGUOUS')
