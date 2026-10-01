from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def isolated_daily(tmp_path: Path, *, mutate: bool = False, tail: str = '', context_exit: int = 0):
    (tmp_path / 'scripts').mkdir()
    script = tmp_path / 'scripts/auto_daily.sh'
    script.write_text((REPO / 'scripts/auto_daily.sh').read_text() + tail)
    (tmp_path / 'scripts/build_context_pack.py').write_text('fixture')
    (tmp_path / '.venv/bin').mkdir(parents=True)
    stub = tmp_path / '.venv/bin/python'
    stub.write_text(f'''#!/usr/bin/env bash
if [ "$1" = "-m" ] && [ "$2" = "xiaocao.live.runtime_evidence" ]; then
  PYTHONPATH="${{XIAOCAO_DAILY_HELPER:+$XIAOCAO_DAILY_HELPER:}}{REPO / 'src'}" exec "{PYTHON}" "$@"
fi
if [ "$1" = "-m" ] && [ "$2" = "xiaocao" ]; then
  if [ "${{MUTATE_SOURCE:-0}}" = 1 ]; then printf '\\nif true; then\\n' >> "$XIAOCAO_ROOT/scripts/auto_daily.sh"; fi
  date +%F
  exit 0
fi
if [ "$1" = "scripts/build_context_pack.py" ]; then exit {context_exit}; fi
exit 0
''')
    stub.chmod(0o755)
    env = {**os.environ, 'XIAOCAO_ROOT': str(tmp_path), 'PYTHONPATH': str(REPO / 'src'),
           'MUTATE_SOURCE': str(int(mutate)), 'PYTHONDONTWRITEBYTECODE': '1'}
    completed = subprocess.run(['bash', str(script), 'eod'], cwd=tmp_path,
                               env=env, capture_output=True, text=True, timeout=20)
    receipts = list((tmp_path / 'output/live/auto/runs').glob('*/terminal.json'))
    return completed, [json.loads(path.read_text()) for path in receipts]


def test_running_shell_is_not_corrupted_by_source_mutation(tmp_path: Path) -> None:
    completed, receipts = isolated_daily(tmp_path, mutate=True)
    assert 'unexpected end of file' not in completed.stderr
    assert len(receipts) == 1
    assert receipts[0]['source_integrity']['status'] == 'changed'
    assert receipts[0]['status'] == 'failed'


def test_terminal_receipt_uses_late_process_exit_over_done_message(tmp_path: Path) -> None:
    completed, receipts = isolated_daily(tmp_path, tail='\nexit 7\n')
    assert completed.returncode == 7
    assert len(receipts) == 1
    assert receipts[0]['process_exit_code'] == 7
    assert receipts[0]['status'] == 'failed'
    assert any(event['message'] == 'eod done' for event in receipts[0]['steps'])


def test_finalizer_failure_preserves_stage_evidence(tmp_path: Path) -> None:
    completed, receipts = isolated_daily(tmp_path, context_exit=9)
    assert completed.returncode == 0
    assert len(receipts) == 1
    assert receipts[0]['process_exit_code'] == 0
    assert receipts[0]['finalization']['context_pack_exit_code'] == 9
    assert receipts[0]['status'] == 'degraded'
    assert Path(receipts[0]['evidence']['events_path']).is_file()


def test_repeated_events_compact_without_hiding_failure_or_order_change() -> None:
    from xiaocao.live import run_flow
    base = run_flow.event(automation='eod', market_date='2026-09-30', step='reconcile', status='info',
                          detail={'type': 'command_finished', 'reason': 'completed', 'exit_code': 0,
                                  'input_hashes': {'intent.json': 'aaa'}, 'correlation': {'order_id': ['one']}})
    events = [base, {**base, 'ts': 'later'}, {**base, 'status': 'failed'},
              {**base, 'detail': {**base['detail'], 'reason': 'unknown'}},
              {**base, 'detail': {**base['detail'], 'correlation': {'order_id': ['two']}}}]
    compact = run_flow.aggregate_events(events)
    assert len(compact) == 4
    assert compact[0]['repeat_count'] == 2
    assert compact[1]['status'] == 'failed'
    assert compact[-1]['detail']['correlation'] == {'order_id': ['two']}


def test_secret_redaction_keeps_context_and_hashes(tmp_path: Path) -> None:
    from xiaocao.live.runtime_evidence import input_identity, redact
    text = 'password=hunter2 token="secret-token" Authorization: Bearer hidden https://u:pw@example.org'
    clean = redact(text)
    assert all(value not in clean for value in ('hunter2', 'secret-token', 'hidden', 'u:pw'))
    capsule = tmp_path / 'intent.json'
    capsule.write_text(json.dumps({'plan_id': 'plan-one', 'order_id': 'order-two',
                                   'password': 'never-record', 'arbitrary': 'private'}))
    identity = input_identity(['script.py', '--input', str(capsule)], tmp_path)
    assert identity['correlation'] == {'plan_id': ['plan-one'], 'order_id': ['order-two']}
    assert identity['input_hashes']['intent.json']
    assert 'never-record' not in json.dumps(identity)


def test_run_flow_index_preserves_same_day_distinct_runs(tmp_path: Path) -> None:
    from xiaocao.live import run_flow
    path = tmp_path / 'flows.jsonl'
    for run_id, status in [('one', 'failed'), ('two', 'succeeded')]:
        snapshot = {'run_id': run_id, 'market_date': '2026-09-30', 'automation': 'eod', 'status': status}
        run_flow.upsert_snapshot_event(path, snapshot, snapshot_path=tmp_path / run_id)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(row['run_id'], row['status']) for row in rows] == [('one', 'failed'), ('two', 'succeeded')]


def test_snapshot_enrichment_error_still_retains_actual_exit(tmp_path: Path, monkeypatch) -> None:
    from xiaocao.live import runtime_evidence
    script = tmp_path / 'auto_daily.sh'
    script.write_text('echo "[2026-09-30 15:20:00] eod done" | tee "$XIAOCAO_DAILY_LOG"\nexit 7\n')
    def fail(**kwargs):
        raise RuntimeError('token=credential-that-must-not-be-retained')
    monkeypatch.setattr(runtime_evidence.run_flow, 'build_snapshot', fail)
    assert runtime_evidence.launch(script, tmp_path, ['eod']) == 7
    receipt = json.loads(next((tmp_path / 'output/live/auto/runs').glob('*/terminal.json')).read_text())
    assert receipt['process_exit_code'] == 7
    assert receipt['status'] == 'failed'
    assert receipt['finalization']['snapshot_error'] == 'RuntimeError'
    assert receipt['steps'][0]['message'] == 'eod done'
    assert 'credential-that-must-not-be-retained' not in json.dumps(receipt)


def test_early_identity_failure_gets_receipt_without_business_commands(tmp_path: Path) -> None:
    isolated_daily(tmp_path)
    for old in (tmp_path / 'output/live/auto/runs').iterdir():
        shutil.rmtree(old)
    env = {**os.environ, 'XIAOCAO_ROOT': str(tmp_path), 'PYTHONPATH': str(REPO / 'src'),
           'CODEX_AUTOMATION_ID': 'wrong-owner', 'CODEX_THREAD_ID': 'fixture'}
    completed = subprocess.run(['bash', str(tmp_path / 'scripts/auto_daily.sh'), 'morning-execute'],
                               cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 2
    receipt = json.loads(next((tmp_path / 'output/live/auto/runs').glob('*/terminal.json')).read_text())
    assert receipt['process_exit_code'] == 2
    assert receipt['status'] == 'failed'
    assert Path(receipt['evidence']['events_path']).read_text() == ''
    assert receipt['finalization']['context_pack_exit_code'] is None


def test_rebuild_cannot_promote_done_after_nonzero_supervisor_exit(tmp_path: Path) -> None:
    completed, receipts = isolated_daily(tmp_path, tail='\nexit 7\n')
    receipt = receipts[0]
    rebuilt = tmp_path / 'rebuilt.json'
    result = subprocess.run([str(PYTHON), str(REPO / 'scripts/build_run_flow.py'),
        '--automation', 'eod', '--date', receipt['market_date'], '--log', receipt['evidence']['log_path'],
        '--exit-code', '0', '--output', str(rebuilt), '--live-dir', str(tmp_path / 'output/live')],
        env={**os.environ, 'PYTHONPATH': str(REPO / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(rebuilt.read_text())['process_exit_code'] == completed.returncode == 7
    assert json.loads(rebuilt.read_text())['status'] == 'failed'


def test_command_retry_identity_and_changed_input_are_retained(tmp_path: Path, monkeypatch) -> None:
    from xiaocao.live import runtime_evidence
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    runtime_evidence.write_json(run_dir / 'manifest.json', {'run_id': 'run-one', 'market_date': '2026-09-30',
                                                          'source_hashes': runtime_evidence.source_manifest(tmp_path)})
    (run_dir / 'events.jsonl').touch()
    capsule = tmp_path / 'intent.json'
    capsule.write_text(json.dumps({'plan_id': 'plan-one', 'order_id': 'order-one'}))
    monkeypatch.setenv('XIAOCAO_DAILY_RUN_DIR', str(run_dir))
    monkeypatch.setenv('XIAOCAO_ROOT', str(tmp_path))
    monkeypatch.setenv('XIAOCAO_DAILY_STAGE', 'readback')
    monkeypatch.setenv('XIAOCAO_DAILY_PYTHON', str(PYTHON))
    outcomes = iter([5, 0, 0])
    monkeypatch.setattr(runtime_evidence, 'stream_process', lambda *a, **k: next(outcomes))
    for _ in range(2):
        runtime_evidence.command(['reader.py', '--input', str(capsule)])
    capsule.write_text(json.dumps({'plan_id': 'plan-one', 'order_id': 'order-two'}))
    runtime_evidence.command(['reader.py', '--input', str(capsule)])
    finished = [json.loads(line) for line in (run_dir / 'events.jsonl').read_text().splitlines()
                if json.loads(line)['type'] == 'command_finished']
    assert [(row['attempt'], row['exit_code']) for row in finished] == [(1, 5), (2, 0), (1, 0)]
    assert finished[0]['run_id'] == finished[1]['run_id'] == 'run-one'
    assert finished[-1]['correlation']['order_id'] == ['order-two']
    assert finished[0]['input_hashes'] != finished[-1]['input_hashes']


def test_redaction_handles_spaced_values_split_json_and_private_key_lines() -> None:
    from xiaocao.live.runtime_evidence import StreamRedactor, redact
    assert 'two word secret' not in redact('password="two word secret" order_id=one')
    redactor = StreamRedactor()
    clean = ''.join(redactor.line(line) for line in [
        '"password":\n', '"split-sensitive-value",\n', 'order_id=one\n',
        '-----BEGIN PRIVATE KEY-----\n', 'key-body-abc\n', '-----END PRIVATE KEY-----\n'])
    assert 'split-sensitive-value' not in clean
    assert 'key-body-abc' not in clean
    assert 'order_id=one' in clean


def test_supervisor_sigterm_forwards_to_child_and_writes_terminal(tmp_path: Path) -> None:
    import signal
    import time
    root = tmp_path
    (root / '.venv/bin').mkdir(parents=True)
    python = root / '.venv/bin/python'
    python.symlink_to(PYTHON)
    script = root / 'daily.sh'
    script.write_text('echo $$ > child.pid\necho ready > started\nsleep 30\n')
    env = {**os.environ, 'PYTHONPATH': str(REPO / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([str(PYTHON), '-m', 'xiaocao.live.runtime_evidence', 'launch',
                                '--script', str(script), '--root', str(root), '--', 'eod'],
                               cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while not (root / 'started').exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise AssertionError('isolated shell did not start')
            time.sleep(0.01)
        child_pid = int((root / 'child.pid').read_text())
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 143, stdout + stderr
        receipt = json.loads(next((root / 'output/live/auto/runs').glob('*/terminal.json')).read_text())
        assert receipt['process_exit_code'] == 143
        assert receipt['status'] == 'failed'
        assert receipt['terminal_reason'] == 'process_signal'
        with __import__('pytest').raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
