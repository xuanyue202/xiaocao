"""Original post-business research input request; no trading or source effects."""
from __future__ import annotations

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


def await_judgment(root: Path, day: str, *, wait_seconds: float = 0,
                   emit: Callable[[dict], None] | None = None,
                   now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                   sleep: Callable[[float], None] = time.sleep) -> None:
    """Retain one owner-bound request/deadline, never freeze an implicit empty draft."""
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
    if path.exists():
        if path.is_symlink():
            raise JudgmentInputRequired('BOOK_T_JUDGMENT_REQUEST_SYMLINK')
        request = json.loads(path.read_bytes())
        unsigned = {key:value for key,value in request.items() if key!='request_sha256'}
        if (request.get('request_sha256') != canonical_sha256(unsigned)
                or request.get('binding') != binding or request.get('trade_date') != day):
            raise JudgmentInputRequired('BOOK_T_JUDGMENT_REQUEST_BINDING_INVALID')
    else:
        if draft.is_file() and not draft.is_symlink():
            value = json.loads(draft.read_bytes())
            if isinstance(value, dict) and isinstance(value.get('themes'), list):
                return  # The snapshot binder still validates exact source/time/theme facts.
        started = now()
        request = {'schema_version':'book-t-judgment-input-request.v1', 'trade_date':day,
            'binding':binding, 'authority':'research_only', 'requested_at':started.isoformat(),
            'deadline':(started+timedelta(seconds=min(120,max(0,wait_seconds)))).isoformat(),
            'draft_path':str(draft), 'source_ledger':str(root/'output/live/kol_daily/publications'),
            'theme_registry':str(root/'reference/experience/book_t_v2_theme_registry.json'),
            'next_action':'original_owner_review_dated_theme_input_after_formal_business'}
        request['request_sha256'] = canonical_sha256(request)
        atomic_write(path,json.dumps(request,sort_keys=True).encode(),immutable=True)
    if emit:
        emit({'event':'book_t_v2_judgment_required', 'trade_date':day,
              'status':'research_input_required', 'reason':'BOOK_T_DATED_JUDGMENT_MISSING',
              'request_path':str(path), 'request_sha256':request['request_sha256']})
    deadline = datetime.fromisoformat(request['deadline'])
    # An owner may create the exact dated draft while this original process waits.
    # Subsequent calls retain this deadline; a timeout never renews the request.
    while now() < deadline:
        if draft.is_file() and not draft.is_symlink():
            value = json.loads(draft.read_bytes())
            if isinstance(value, dict) and isinstance(value.get('themes'), list):
                return
        sleep(min(.5,max(0,(deadline-now()).total_seconds())))
    raise JudgmentInputRequired('BOOK_T_DATED_JUDGMENT_MISSING:'+str(path))
