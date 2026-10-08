"""Local execution evidence for the daily shell; no business actions of its own.

The supervisor retains an immutable shell copy and observes its exit. Command
records describe process outcomes, never infer an order/fill from stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xiaocao.live import run_flow

CORRELATION_KEYS = {'plan_id', 'plan_hash', 'order_id', 'broker_order_id', 'decision_id',
                    'decision_sha256', 'report_id', 'source_id', 'source_fingerprint',
                    'projection_sha256', 'request_id'}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def redact(text: str) -> str:
    return run_flow.redact_text(text)



class StreamRedactor:
    """Handle split JSON credential values and private-key blocks in streams."""
    def __init__(self) -> None:
        self.pending_value = False
        self.private_key = False

    def line(self, text: str) -> str:
        if '-----BEGIN ' in text and 'PRIVATE KEY-----' in text:
            self.private_key = True
        if self.private_key:
            if '-----END ' in text and 'PRIVATE KEY-----' in text:
                self.private_key = False
            return '[redacted]\n'
        if self.pending_value:
            self.pending_value = False
            return '[redacted]\n'
        self.pending_value = bool(re.search(
            r"(?:password|passwd|token|secret|authorization|api[_-]?key|cookie|credential)"
            r"[\s\"']*[:=]\s*$", text, re.I))
        return redact(text)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def source_manifest(root: Path) -> dict[str, str]:
    """Hash source/config names only; private/runtime files and env are excluded."""
    paths = {root / 'scripts/auto_daily.sh', root / 'pyproject.toml',
             root / 'docs/OPERATING_CONTRACT.md'}
    for name in ('scripts', 'src/xiaocao', 'kronos_screen/scripts'):
        folder = root / name
        if folder.exists():
            paths.update(p for p in folder.rglob('*') if p.suffix in {'.py', '.sh', '.swift'})
    return {str(p.relative_to(root)): sha256(p) for p in sorted(paths)
            if p.is_file() and not p.is_symlink()}


def source_changes(root: Path, baseline: dict[str, str]) -> list[str]:
    current = source_manifest(root)
    return sorted(key for key in baseline.keys() | current.keys()
                  if baseline.get(key) != current.get(key))


def input_identity(args: list[str], root: Path, *, digest_only: bool = False) -> dict[str, Any]:
    """Digest explicitly supplied files, and retain only known linkage fields."""
    inputs: dict[str, str] = {}
    correlations: dict[str, list[str]] = {}
    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in CORRELATION_KEYS and isinstance(item, (str, int)):
                    # Do not capture arbitrary payloads, account numbers or secrets.
                    correlations.setdefault(key, []).append(redact(str(item))[:200])
                elif isinstance(item, (dict, list)):
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    for index, arg in enumerate(args):
        # Flags that may carry secrets never contribute values or paths.
        if index and re.search(r'password|token|secret|auth|key|cookie|credential', args[index - 1], re.I):
            continue
        if arg.startswith('-'):
            continue
        path = Path(arg)
        if not path.is_absolute():
            path = root / path
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
            if not resolved.is_file() or resolved.is_symlink():
                continue
            key = str(resolved.relative_to(root))
            if re.search(r'password|token|secret|credential|xiaocao\.ya?ml', key, re.I):
                continue
            inputs[key] = sha256(resolved)
            if not digest_only and resolved.suffix == '.json' and resolved.stat().st_size <= 2_000_000:
                collect(json.loads(resolved.read_text(encoding='utf-8')))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return {'input_hashes': inputs, 'correlation': {k: sorted(set(v)) for k, v in correlations.items()}}



def operational_inputs(root: Path, market_date: str) -> dict[str, Any]:
    """Bind selected implicit daily inputs without copying payloads or secrets."""
    paths = [f'output/live/recommend_{market_date}.md',
             f'output/live/intelligence_review_queue_{market_date}.json',
             f'output/live/book_b_live_freeze_{market_date}.jsonl',
             f'output/live/book_t_v2_shadow_input_{market_date}.json',
             'output/live/positions.jsonl', 'output/live/paper_trades.jsonl']
    identity = input_identity(paths, root)
    # Canonical account files are digest-only inputs, never parsed log/summary
    # projections or sources of order/decision correlation.
    accounts = input_identity(['output/live/paper_account.json', 'output/live/paper_account_A.json',
                               'output/live/paper_account_T.json'], root, digest_only=True)
    identity['input_hashes'].update(accounts['input_hashes'])
    return identity


def append_event(path: Path, row: dict[str, Any]) -> None:
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def stream_process(args: list[str], *, cwd: Path, env: dict[str, str], output_path: Path | None = None) -> int:
    """Forward sanitized streams; detailed output is retained separately."""
    with output_path.open('a', encoding='utf-8') if output_path else open(os.devnull, 'w') as evidence:
        process = None
        pending_signals: list[int] = []
        previous_handlers: dict[int, Any] = {}
        def forward_signal(signum: int, frame: Any) -> None:
            if process is None:
                pending_signals.append(signum)
                return
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[signum] = signal.signal(signum, forward_signal)
        try:
            # Install before spawn: a fast child can become runnable before
            # Popen returns, so a stop at that boundary must not orphan it.
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, errors='replace', start_new_session=True)
        except BaseException:
            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)
            raise
        for signum in pending_signals:
            forward_signal(signum, None)
        lock = threading.Lock()
        def forward(source: Any, target: Any) -> None:
            redactor = StreamRedactor()
            for line in source:
                clean = redactor.line(line)
                with lock:
                    evidence.write(clean)
                    evidence.flush()
                    try:
                        target.write(clean)
                        target.flush()
                    except BrokenPipeError:
                        pass
            source.close()
        threads = [threading.Thread(target=forward, args=(process.stdout, sys.stdout)),
                   threading.Thread(target=forward, args=(process.stderr, sys.stderr))]
        for thread in threads:
            thread.start()
        try:
            result = process.wait()
            for thread in threads:
                thread.join()
        finally:
            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)
    return 128 - result if result < 0 else result


def business_environment(env: dict[str, str], root: Path) -> dict[str, str]:
    """Observer imports its frozen package; business imports the complete source."""
    clean = dict(env)
    helper = Path(env['XIAOCAO_DAILY_HELPER']).resolve() if env.get('XIAOCAO_DAILY_HELPER') else None
    paths = [str(root / 'src')]
    seen = {(root / 'src').resolve()}
    for entry in env.get('PYTHONPATH', '').split(os.pathsep):
        if not entry:
            continue
        path = Path(entry)
        resolved = (path if path.is_absolute() else root / path).resolve()
        if helper is not None and (resolved == helper or helper in resolved.parents):
            continue
        if resolved not in seen:
            paths.append(str(resolved))
            seen.add(resolved)
    clean['PYTHONPATH'] = os.pathsep.join(paths)
    return clean


def command(args: list[str]) -> int:
    run_dir = Path(os.environ['XIAOCAO_DAILY_RUN_DIR'])
    root = Path(os.environ['XIAOCAO_ROOT'])
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    events_path = run_dir / 'events.jsonl'
    existing = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    stage = redact(os.environ.get('XIAOCAO_DAILY_STAGE', 'startup'))
    identity = operational_inputs(root, manifest['market_date'])
    explicit = input_identity(args, root)
    identity['input_hashes'].update(explicit['input_hashes'])
    for key, values in explicit['correlation'].items():
        identity['correlation'][key] = sorted(set(identity['correlation'].get(key, []) + values))
    program = args[1] if args and args[0] == '-m' and len(args) > 1 else (args[0] if args else 'missing')
    # Script names/modules are public source identity; never persist command argv.
    program = program if re.fullmatch(r'[\w./-]+', program) else 'unrecognized'
    attempt = 1 + sum(e.get('stage') == stage and e.get('program') == program and
                      e.get('input_hashes') == identity['input_hashes'] and e.get('type') == 'command_started'
                      for e in existing)
    command_id = f"{manifest['run_id']}:{len(existing) + 1}"
    base = {'schema_version': 1, 'run_id': manifest['run_id'], 'command_id': command_id,
            'stage': stage, 'program': program, 'attempt': attempt, **identity}
    changed = source_changes(root, manifest['source_hashes'])
    if changed:
        append_event(events_path, {**base, 'type': 'command_finished', 'ts': now(),
                     'status': 'failed', 'exit_code': 78, 'reason': 'source_changed', 'changed_sources': changed})
        print(f'runtime command refused: source_changed run_id={manifest["run_id"]}', file=sys.stderr)
        return 78
    append_event(events_path, {**base, 'type': 'command_started', 'ts': now(), 'status': 'running'})
    output = run_dir / 'commands' / f'{len(existing) + 1}.log'
    output.parent.mkdir(exist_ok=True)
    try:
        result = stream_process([os.environ['XIAOCAO_DAILY_PYTHON'], *args], cwd=root,
                                env=business_environment(dict(os.environ), root), output_path=output)
        reason = 'process_exit' if result else 'completed'
    except OSError as exc:
        result, reason = 127, f'process_start_{type(exc).__name__}'
    append_event(events_path, {**base, 'type': 'command_finished', 'ts': now(),
                 'status': 'failed' if result else 'succeeded', 'exit_code': result, 'reason': reason,
                 'evidence_path': str(output), 'evidence_sha256': sha256(output) if output.exists() else None})
    return result


def launch(script: Path, root: Path, args: list[str]) -> int:
    market_date = (os.environ.get('XIAOCAO_BOOK_T_V2_REHEARSAL_DATE')
                   if os.environ.get('XIAOCAO_BOOK_T_V2_RUN_MODE') == 'rehearsal' else None) or datetime.now().strftime('%Y-%m-%d')
    if args[:1] == ['eod']:
        # Imported only in the launcher: the frozen command observer does not
        # load business modules from the mutable checkout.
        from xiaocao.live.eod_automation_gate import EodGateRejected, claim_eod_slot
        try:
            claim_eod_slot(root, 'paper', market_date)
        except EodGateRejected as exc:
            print(json.dumps(exc.payload, sort_keys=True), file=sys.stderr)
            return 2
    return _launch(script, root, args, market_date)


def _launch(script: Path, root: Path, args: list[str], market_date: str) -> int:
    run_id = f'{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:12]}'
    run_dir = root / 'output/live/auto/runs' / run_id
    run_dir.mkdir(parents=True, mode=0o700)
    stable_script = run_dir / 'auto_daily.sh'
    source = script.read_bytes()
    stable_script.write_bytes(source)
    stable_script.chmod(0o400)
    hashes = source_manifest(root)
    automation = args[0] if args else 'unknown'
    # Freeze the observer as well: future Python source edits cannot break or
    # bypass the command boundary that checks the original source manifest.
    helper_root = run_dir / 'observer'
    helper_package = helper_root / 'xiaocao/live'
    helper_package.mkdir(parents=True)
    for init in (helper_root / 'xiaocao/__init__.py', helper_package / '__init__.py'):
        init.write_text('', encoding='utf-8')
    for name, original in (('runtime_evidence.py', Path(__file__)), ('run_flow.py', Path(run_flow.__file__))):
        (helper_package / name).write_bytes(original.read_bytes())
        (helper_package / name).chmod(0o400)
    manifest = {'schema_version': 1, 'run_id': run_id, 'automation': automation,
                'market_date': market_date, 'started_at': now(), 'source_hashes': hashes,
                'source_manifest_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
                'shell_sha256': hashlib.sha256(source).hexdigest(),
                'initial_inputs': operational_inputs(root, market_date), 'python_version': sys.version.split()[0],
                'observer_hashes': {p.name: sha256(p) for p in helper_package.glob('*.py')},
                'automation_id': os.environ.get('CODEX_AUTOMATION_ID'), 'thread_id': os.environ.get('CODEX_THREAD_ID')}
    # The exact contract/config source digest and interpreter version are in the manifest.
    write_json(run_dir / 'manifest.json', manifest)
    events_path = run_dir / 'events.jsonl'
    events_path.touch()
    log_path = run_dir / 'shell.log'
    env = {**os.environ, 'XIAOCAO_ROOT': str(root), 'XIAOCAO_DAILY_SNAPSHOT': str(stable_script),
           'XIAOCAO_DAILY_RUN_DIR': str(run_dir), 'XIAOCAO_DAILY_RUN_ID': run_id,
           'XIAOCAO_DAILY_PYTHON': str(root / '.venv/bin/python'),
           'XIAOCAO_DAILY_HELPER': str(helper_root), 'XIAOCAO_DAILY_LOG': str(log_path)}
    process_exit = 127
    failure_reason = 'process_start_failed'
    try:
        process_exit = stream_process(['bash', str(stable_script), *args], cwd=root, env=env,
                                      output_path=run_dir / 'console.log')
        failure_reason = 'process_signal' if process_exit in (130, 143) else ('process_exit' if process_exit else 'completed')
    except OSError as exc:
        failure_reason = f'process_start_{type(exc).__name__}'
    changed = source_changes(root, hashes)
    # Finalization is observational; an earlier nonzero shell exit is never overwritten.
    context_exit: int | None = None
    if not changed and log_path.exists() and (root / 'scripts/build_context_pack.py').exists():
        try:
            context_exit = stream_process([str(root / '.venv/bin/python'), 'scripts/build_context_pack.py',
                                           '--date', market_date, '--phase', automation],
                                          cwd=root, env=business_environment(env, root), output_path=run_dir / 'finalization.log')
        except OSError:
            context_exit = 127
    finalization_error: str | None = None
    rows: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    try:
        rows = [json.loads(line) for line in events_path.read_text().splitlines()]
        parsed = run_flow.events_from_log(automation=automation, market_date=market_date, log_path=log_path)
        required = {'scripts/live_recommend.py', 'kronos_screen/scripts/paper_record.py',
                    'kronos_screen/scripts/eod_capture.py', 'kronos_screen/scripts/forward_eval.py',
                    'scripts/live_monitor.py', 'kronos_screen/scripts/settle_book_a.py',
                    'kronos_screen/scripts/settle_book_t.py',
                    'scripts/weekly_deep_review.py'}
        command_events = []
        for row in rows:
            if row['type'] != 'command_finished':
                continue
            failed = row['exit_code'] != 0
            critical = row['reason'] == 'source_changed' or row['program'] in required
            detail = {**row, 'layer': 'deterministic' if critical else 'supporting'}
            command_events.append(run_flow.event(
                automation=automation, market_date=market_date, step=row['stage'],
                status='failed' if failed else 'succeeded',
                message=f"{row['program']}: {row['reason']} exit={row['exit_code']}",
                ts=row['ts'], detail=detail))
        events = parsed + command_events
        health = run_flow.supporting_health_from_live(live_dir=root / 'output/live', market_date=market_date)
        if context_exit:
            health['status'] = 'degraded'
            health.setdefault('issues', []).append({'surface': 'finalization', 'detail': f'context_pack exit={context_exit}'})
        snapshot = run_flow.build_snapshot(automation=automation, market_date=market_date,
                         events=events, exit_code=process_exit or (78 if changed else 0), supporting_health=health)
    except Exception as exc:
        # Formatting/enrichment must never erase the already observed process
        # outcome or raw evidence. Error class only; exception text may be private.
        finalization_error = type(exc).__name__
        snapshot = {'schema_version': 1, 'automation': automation, 'market_date': market_date,
                    'generated_at': now(), 'exit_code': process_exit or (78 if changed else 0),
                    'status': 'failed' if process_exit or changed else 'degraded',
                    'deterministic_status': 'failed' if process_exit or changed else 'succeeded',
                    'steps': parsed, 'supporting_health': {'status': 'degraded', 'issues': [
                        {'surface': 'finalization', 'detail': finalization_error}]}}
    snapshot.update(run_id=run_id, process_exit_code=process_exit,
                    terminal_reason='source_changed' if changed else failure_reason,
                    source_integrity={'status': 'changed' if changed else 'unchanged', 'changed_sources': changed},
                    finalization={'context_pack_exit_code': context_exit, 'snapshot_error': finalization_error},
                    evidence={'manifest_path': str(run_dir / 'manifest.json'), 'events_path': str(events_path), 'events_sha256': sha256(events_path),
                              'log_path': str(log_path), 'console_path': str(run_dir / 'console.log')})
    write_json(run_dir / 'terminal.json', snapshot)
    try:
        run_flow.write_snapshot(root / f'output/live/run_flow_{market_date}_{automation}.json', snapshot)
        run_flow.upsert_snapshot_event(root / 'output/live/run_flow.jsonl', snapshot, snapshot_path=run_dir / 'terminal.json')
        if log_path.exists():
            # Legacy daily view is a projection; unique run evidence is never rewritten.
            legacy = root / f'output/live/auto/{market_date}_{automation}.log'
            legacy.write_text(log_path.read_text(encoding='utf-8'), encoding='utf-8')
    except OSError as exc:
        snapshot['status'] = 'degraded' if snapshot['status'] != 'failed' else 'failed'
        snapshot['finalization']['projection_error'] = type(exc).__name__
        write_json(run_dir / 'terminal.json', snapshot)
    print(f"runtime terminal run_id={run_id} status={snapshot['status']} process_exit={process_exit} receipt={run_dir / 'terminal.json'}")
    return process_exit or (78 if changed else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='action', required=True)
    launch_parser = subparsers.add_parser('launch')
    launch_parser.add_argument('--script', type=Path, required=True)
    launch_parser.add_argument('--root', type=Path, required=True)
    launch_parser.add_argument('args', nargs=argparse.REMAINDER)
    subparsers.add_parser('command').add_argument('args', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    args = options.args[1:] if options.args[:1] == ['--'] else options.args
    if options.action == 'command':
        return command(args)
    if options.script is None or options.root is None:
        parser.error('launch requires --script and --root')
    return launch(options.script.resolve(), options.root.resolve(), args)


if __name__ == '__main__':
    raise SystemExit(main())
