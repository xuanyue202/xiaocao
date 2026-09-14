"""Exercise the public shell with isolated command receipts, never real ledgers."""
import os
import subprocess
from pathlib import Path

import pytest

from xiaocao.live import run_flow

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('failure', ['freeze', 'book_b', 'book_t', 'none', 'calendar'])
def test_morning_books_keep_independent_results(tmp_path, failure):
    python = tmp_path / '.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
with Path('calls.txt').open('a') as f:
    f.write(' '.join(args) + '\\n')
if args[:3] == ['-m', 'xiaocao', 'calendar']:
    import datetime
    if os.environ['FAIL_STAGE'] == 'calendar':
        print('calendar unavailable')
        sys.exit(1)
    print(datetime.date.today().isoformat())
if args[0].endswith('wait_for_morning_freeze.py') and os.environ['FAIL_STAGE'] == 'freeze':
    print('report_missing')
    sys.exit(1)
if args[0].endswith('paper_record.py') and '--trend-only' not in args and os.environ['FAIL_STAGE'] == 'book_b':
    sys.exit(1)
if args[0].endswith('paper_record.py') and '--trend-only' in args and os.environ['FAIL_STAGE'] == 'book_t':
    sys.exit(1)
''')
    python.chmod(0o755)
    env = {**os.environ, 'XIAOCAO_ROOT': str(tmp_path), 'FAIL_STAGE': failure}
    completed = subprocess.run(['bash', str(ROOT / 'scripts/auto_daily.sh'), 'morning-execute'], env=env, capture_output=True, text=True, timeout=10)
    calls = (tmp_path / 'calls.txt').read_text().splitlines()
    log = next((tmp_path / 'output/live/auto').glob('*_morning-execute.log'))
    events = run_flow.events_from_log(automation='morning-execute', market_date='2026-09-14', log_path=log)
    snapshot = run_flow.build_snapshot(automation='morning-execute', market_date='2026-09-14', events=events, exit_code=completed.returncode)
    assert snapshot['deterministic_status'] == ('succeeded' if failure == 'none' else 'failed')
    assert (completed.returncode != 0) == (failure != 'none')
    if failure == 'calendar':
        assert not any('paper_record.py' in c for c in calls)
        return
    assert sum('paper_record.py' in c and '--trend-only' in c for c in calls) == 1
    assert not any('live_recommend.py' in c for c in calls)
    if failure == 'freeze':
        assert not any('wait_for_agent_reviews.py' in c or ('paper_record.py' in c and '--trend-only' not in c) for c in calls)

    if failure == 'book_t':
        assert not any('book_t_v2_daily.py' in c for c in calls)
