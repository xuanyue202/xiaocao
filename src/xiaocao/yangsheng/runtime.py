"""Shared downloader lifecycle and the bounded native connection boundary."""
from __future__ import annotations
import ctypes
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from .capture import DEFAULT_ROOT, cycle, database, initialize, lifecycle_lease, sha_file, tasks
from .native import CaptureError, request, save
from . import network

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / 'wx_channels_download' / 'wx_video_download_macos_arm64'
ENABLED = DEFAULT_ROOT / 'shared-enabled.json'
SOURCE = ROOT / 'output/live/kol_daily'


@contextmanager
def native_lease():
    paths = [(SOURCE / '.lock', fcntl.LOCK_SH), (SOURCE / '.source-locks/99a61c48bff0d5317ae30e323deeb51318e2a9b8dccc61892e89efb392572911.lock', fcntl.LOCK_EX)]
    handles = []
    try:
        for path, kind in paths:
            handle = path.open('a+'); handles.append(handle)
            try: fcntl.flock(handle, kind | fcntl.LOCK_NB)
            except BlockingIOError: raise CaptureError('xiaocao_native_resource_busy') from None
        yield
    finally:
        for handle in reversed(handles): handle.close()


def executable(pid):
    lib = ctypes.CDLL('/usr/lib/libproc.dylib')
    buf = ctypes.create_string_buffer(4096)
    if lib.proc_pidpath(int(pid), buf, len(buf)) <= 0: raise CaptureError('shared_backend_pid_unverified')
    return Path(os.fsdecode(buf.value)).resolve()


def ensure_backend(api='http://127.0.0.1:2022'):
    if not ENABLED.is_file(): return {'status': 'disabled', 'code': 'shared_capture_not_deployed'}
    descriptor = json.loads(ENABLED.read_text())
    if Path(descriptor['binary']).resolve() != BACKEND.resolve() or sha_file(BACKEND) != descriptor['sha256']:
        raise CaptureError('shared_backend_binary_changed')
    try: health = request(api, '/api/shared-capture/status')
    except CaptureError:
        with native_lease():
            for port in (2022, 2023):
                with socket.socket() as sock:
                    if sock.connect_ex(('127.0.0.1', port)) == 0: raise CaptureError('shared_backend_upgrade_or_owner_required')
            from xiaocao.kol.xiaocao_live import capture_runtime_environment
            process = subprocess.Popen([str(BACKEND), '--xiaoetong-only'], cwd=BACKEND.parent,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, env=capture_runtime_environment())
            for _ in range(50):
                if process.poll() is not None: raise CaptureError('shared_backend_start_failed')
                try: health = request(api, '/api/shared-capture/status'); break
                except CaptureError: time.sleep(0.1)
            else: raise CaptureError('shared_backend_start_timeout')
    if health.get('enabled') is not True or health.get('engine') != 'gopeed' or executable(health['pid']) != BACKEND.resolve():
        raise CaptureError('shared_backend_identity_unverified')
    return health


def moments_snapshot(root):
    runtime = json.loads((Path.home() / '.wechat-cli/asr/runtime.json').read_text())
    env = dict(os.environ, PYTHONPATH=str(ROOT.parent / 'wechat-cli'))
    result = subprocess.run([runtime['python'], str(ROOT / 'scripts/kol_liuguan_moments.py'), '--state-dir', str(root)],
        capture_output=True, text=True, timeout=90, env=env)
    if result.returncode: raise CaptureError('moments_snapshot_failed')
    return json.loads(result.stdout)


def run_local(root=DEFAULT_ROOT, api='http://127.0.0.1:2022'):
    with lifecycle_lease(root):
        return _run_local(root, api)


def _run_local(root, api):
    root = Path(root)
    with database(root) as db: initialize(db)
    health = ensure_backend(api)
    if health.get('status') == 'disabled': return health
    from .artifacts import reconcile_artifacts
    from .asr import start_worker, summary
    artifacts = reconcile_artifacts(root, api)
    snapshot = None; discovery_error = None
    try: snapshot = moments_snapshot(root)
    except (OSError, ValueError, subprocess.SubprocessError, CaptureError): discovery_error = 'moments_snapshot_failed'
    try:
        value = cycle(root, api, moments_snapshot=snapshot)
    finally:
        # Accepted downloads remain consumable if the next native scan fails.
        # cycle has released its catalogue writer lock before dispatch.
        worker = start_worker(root)
    value['artifacts'] = artifacts
    value['asr_worker'] = worker
    value['asr_status'] = summary(root)
    if discovery_error:
        value['moments_error'] = discovery_error
        if value['status'] == 'scanned': value['status'] = 'degraded'
    return value


def bootstrap(window_id, pid, api='http://127.0.0.1:2022', root=DEFAULT_ROOT):
    url = urlsplit(api)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path or url.query or url.port not in (2022, 23222):
        raise CaptureError('invalid_shared_bootstrap_api')
    root = Path(root); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    owned_url = api + '/liuguan/proxy.pac'
    health = request(api, '/api/shared-capture/status')
    if health.get('enabled') is not True: raise CaptureError('shared_backend_not_enabled')
    with lifecycle_lease(root), native_lease():
        before = network.snapshot()
        if any('Enabled: No' not in value for value in before.values()): raise CaptureError('existing_active_proxy_preserved')
        receipt = root / 'pac-restoration.json'
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        guard = subprocess.Popen([sys.executable, '-m', 'xiaocao.yangsheng.network', '--receipt', str(receipt)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, start_new_session=True, env=env)
        guard.stdin.write(json.dumps({'before': before, 'owned_url': owned_url}) + '\n'); guard.stdin.flush()
        if guard.stdout.readline().strip() != 'armed': raise CaptureError('pac_guard_not_armed')
        try:
            network.command('-setautoproxyurl', 'Wi-Fi', owned_url); network.command('-setautoproxystate', 'Wi-Fi', 'on')
            if network.fields(network.command('-getautoproxyurl', 'Wi-Fi')) != {'URL': owned_url, 'Enabled': 'Yes'}:
                raise CaptureError('native_pac_readback_failed')
            focused = subprocess.run(['swift', str(ROOT / 'scripts/kol_liuguan_window.swift'), str(window_id), str(pid), '0.74', '0.028', '--focus'],
                capture_output=True, timeout=20)
            if focused.returncode: raise CaptureError('native_window_identity_changed')
            script = f'''tell application "System Events"
 tell first application process whose unix id is {int(pid)}
  if frontmost is not true then error "target not frontmost"
  if enabled of menu item "刷新" of menu 1 of menu bar item "文件" of menu bar 1 is not true then error "refresh unavailable"
  click menu item "刷新" of menu 1 of menu bar item "文件" of menu bar 1
 end tell
end tell'''
            refreshed = subprocess.run(['osascript', '-e', script], capture_output=True, timeout=10)
            if refreshed.returncode: raise CaptureError('native_refresh_unverified')
            for _ in range(30):
                health = request(api, '/api/shared-capture/status')
                if health.get('channels_available') is True: break
                time.sleep(0.5)
            else: raise CaptureError('native_socket_not_connected')
        finally:
            guard.stdin.close(); guard.wait(timeout=65)
            restored = network.restore(before, owned_url)
            if not restored['restored']: raise CaptureError('native_pac_restore_not_verified')
        result = {'status': 'connected', 'api': api, 'window_id': window_id, 'pid': pid, 'pac_restored': True}
        save(root / 'native-entry.json', {**result, 'observed_at': time.time(), 'hint_only': True})
        return result


@contextmanager
def shared_shutdown_lease(api='http://127.0.0.1:2022', root=DEFAULT_ROOT):
    """Exclude page users/creates until the owner has finished guarded cleanup.

    Do not detach or query the backend before the caller validates its current
    capture owner and any existing strict cleanup receipt.
    """
    if not ENABLED.is_file():
        yield None
        return
    with lifecycle_lease(root, closing=True):
        yield None


def drain_for_xiaocao_cleanup(api='http://127.0.0.1:2022'):
    # Called only inside shared_shutdown_lease after owner preflight and detach.
    if not ENABLED.is_file(): return None
    from .artifacts import drain_before_shutdown
    from xiaocao.kol.enrichment_types import EnrichmentError
    try: return drain_before_shutdown(DEFAULT_ROOT, api)
    except CaptureError as error: raise EnrichmentError(str(error)) from None


def finish(root=DEFAULT_ROOT, api='http://127.0.0.1:2022'):
    if not ENABLED.is_file(): return {'status': 'disabled'}
    from .artifacts import drain_before_shutdown
    from xiaocao.kol.xiaocao_live import XiaocaoLiveService, validate_cleanup_evidence
    service = XiaocaoLiveService()
    with lifecycle_lease(root, closing=True):
        try: health = request(api, '/api/shared-capture/status')
        except CaptureError:
            # API failure alone cannot establish that the process is gone.
            cleanup = service.cleanup_snapshot()
            validate_cleanup_evidence(cleanup)
            from .asr import start_worker
            return {'status': 'already_closed', 'cleanup': cleanup, 'asr_worker': start_worker(root)}
        if health.get('enabled') is not True or executable(health['pid']) != BACKEND.resolve():
            raise CaptureError('shared_backend_identity_unverified')
        with native_lease():
            # Both native entry users have released before detaching the PAC.
            service._disable_owned_capture_pac()
            proof = drain_before_shutdown(root, api)
            current = request(api, '/api/shared-capture/status')
            if (current['pid'] != health['pid'] or current.get('post_processing_active') != []
                    or any(t.get('status') in ('running', 'ready', 'wait') for t in tasks(api))):
                raise CaptureError('shared_backend_still_owned')
            os.kill(health['pid'], signal.SIGINT)
            for _ in range(100):
                try: os.kill(health['pid'], 0)
                except ProcessLookupError: break
                time.sleep(0.1)
            cleanup = service.cleanup_snapshot(); validate_cleanup_evidence(cleanup)
    from .asr import start_worker
    return {'status': 'closed', 'artifacts': proof, 'cleanup': cleanup, 'asr_worker': start_worker(root)}
