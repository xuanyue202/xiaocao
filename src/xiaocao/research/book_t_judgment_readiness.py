"""Original post-business research input request; no trading or source effects."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from xiaocao.kol.publication import canonical_sha256
from xiaocao.utils.atomic_files import atomic_write


class JudgmentInputRequired(ValueError):
    pass


def _candidate(path: Path, *, request: dict | None, day: str,
               clock: datetime) -> tuple[dict, bytes] | None:
    if not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or not isinstance(value.get('themes'), list):
        return None
    # Existing nonempty preloaded drafts retain their normal binder validation.
    # A requested reply and every empty-theme result require explicit review.
    if request is None and value['themes']:
        return value, raw
    review = value.get('readiness_review') or {}
    if not isinstance(review,dict) or not isinstance(review.get('reviewed_at'),str):
        return None
    try:
        reviewed = datetime.fromisoformat(review['reviewed_at'].replace('Z','+00:00'))
    except (KeyError, TypeError, ValueError):
        return None
    if (review.get('status') != 'reviewed' or not review.get('reviewer_id')
            or review.get('trade_date') != day or reviewed.utcoffset() is None
            or reviewed > clock or reviewed.astimezone(timezone(timedelta(hours=8))).date().isoformat() != day
            or review.get('draft_sha256') != canonical_sha256({k:v for k,v in value.items() if k!='readiness_review'})
            or not isinstance(review.get('reason'), str) or not review['reason'].strip()):
        return None
    if not value['themes'] and (value.get('status') != 'no_supported_theme'
            or not isinstance(value.get('reason'),str) or not value['reason'].strip()):
        return None
    if request is not None and (review.get('request_sha256') != request['request_sha256']
            or review['reviewer_id'] != request['binding']['CODEX_THREAD_ID']
            or reviewed < datetime.fromisoformat(request['requested_at'])):
        return None
    return value, raw


def _accept(root: Path, owner_key: str, day: str, candidate: tuple[dict, bytes],
            *, request: dict | None, accepted_at: datetime) -> dict:
    draft, raw = candidate
    value = {'schema_version':'book-t-judgment-admission.v1', 'trade_date':day,
        'authority':'research_only', 'status':'received_snapshot_only', 'accepted_at':accepted_at.isoformat(),
        'request_sha256':request['request_sha256'] if request else None,
        'deadline':request['deadline'] if request else None,
        'draft':draft, 'draft_sha256':hashlib.sha256(raw).hexdigest()}
    value['receipt_sha256'] = canonical_sha256(value)
    path = root/'output/live/book_t_v2_judgment_requests'/day/(owner_key+'.'+value['receipt_sha256']+'.accepted.json')
    atomic_write(path,json.dumps(value,sort_keys=True).encode(),immutable=True)
    return {**value,'receipt_path':str(path)}


def await_judgment(root: Path, day: str, *, wait_seconds: float = 0,
                   emit: Callable[[dict], None] | None = None,
                   now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                   sleep: Callable[[float], None] = time.sleep) -> dict:
    """Admit exact reviewed bytes within one original owner-bound deadline."""
    if not math.isfinite(wait_seconds) or wait_seconds < 0:
        raise JudgmentInputRequired('BOOK_T_JUDGMENT_WAIT_INVALID')
    draft = root / f'output/live/book_t_v2_judgment_draft_{day}.json'
    binding = {key: os.environ.get(key) for key in
               ('CODEX_AUTOMATION_ID', 'CODEX_THREAD_ID', 'XIAOCAO_DAILY_RUN_ID')}
    owner_key = canonical_sha256({'day': day, 'binding': binding})
    path = root / 'output/live/book_t_v2_judgment_requests' / day / (owner_key+'.json')
    if wait_seconds > 0 and (binding['CODEX_AUTOMATION_ID'] != 'xiaocao-daily-morning-execution'
                             or not binding['CODEX_THREAD_ID'] or not binding['XIAOCAO_DAILY_RUN_ID']):
        raise JudgmentInputRequired('BOOK_T_JUDGMENT_OWNER_REQUIRED')
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise JudgmentInputRequired('BOOK_T_JUDGMENT_REQUEST_SYMLINK')
        request = json.loads(path.read_bytes())
        unsigned = {key:value for key,value in request.items() if key!='request_sha256'}
        if (request.get('request_sha256') != canonical_sha256(unsigned)
                or request.get('binding') != binding or request.get('trade_date') != day):
            raise JudgmentInputRequired('BOOK_T_JUDGMENT_REQUEST_BINDING_INVALID')
    else:
        candidate = _candidate(draft,request=None,day=day,clock=now())
        if candidate is not None:
            return _accept(root,owner_key,day,candidate,request=None,accepted_at=now())
        started = now()
        request = {'schema_version':'book-t-judgment-input-request.v1', 'trade_date':day,
            'binding':binding, 'authority':'research_only', 'requested_at':started.isoformat(),
            'deadline':(started+timedelta(seconds=min(120,wait_seconds))).isoformat(),
            'draft_path':str(draft), 'source_ledger':str(root/'output/live/kol_daily/publications'),
            'theme_registry':str(root/'reference/experience/book_t_v2_theme_registry.json'),
            'reply_review_fields':['status=reviewed','reviewer_id=original thread','trade_date',
                'request_sha256','draft_sha256=canonical draft without readiness_review','reviewed_at','reason'],
            'next_action':'original_owner_review_dated_theme_input_after_formal_business'}
        request['request_sha256'] = canonical_sha256(request)
        atomic_write(path,json.dumps(request,sort_keys=True).encode(),immutable=True)
    if emit:
        emit({'event':'book_t_v2_judgment_required', 'trade_date':day,
              'status':'research_input_required', 'reason':'BOOK_T_DATED_JUDGMENT_MISSING',
              'request_path':str(path), 'request_sha256':request['request_sha256']})
    deadline = datetime.fromisoformat(request['deadline'])
    while now() < deadline:
        candidate = _candidate(draft,request=request,day=day,clock=now())
        accepted_at = now()  # Reading/parsing time also consumes the original budget.
        if candidate is not None and accepted_at < deadline:
            admitted = _accept(root,owner_key,day,candidate,request=request,accepted_at=accepted_at)
            if now() < deadline:
                return admitted
            break
        sleep(min(.5,max(0,(deadline-now()).total_seconds())))
    raise JudgmentInputRequired('BOOK_T_DATED_JUDGMENT_MISSING:'+str(path))
