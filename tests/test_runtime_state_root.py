import json
from pathlib import Path

import pytest

from xiaocao.live.runtime_snapshot import freeze_runtime, operational_root
from xiaocao.kol.trading_context import TradingContextError, build_trading_context


def snapshot(root):
    run = root / 'output/live/auto/runs/original'
    run.mkdir(parents=True)
    runtime = freeze_runtime(root, run/'runtime', {})
    (run/'manifest.json').write_text(json.dumps({'deployment_root':str(root),
        'execution_root':str(runtime), 'run_id':'original'}))
    return runtime


def test_manifest_bound_shared_output_reaches_real_cache_guard(tmp_path):
    runtime = snapshot(tmp_path)
    with pytest.raises(TradingContextError, match='cache_directory_symlink_forbidden'):
        build_trading_context(repo_root=runtime, read_report_ids=[])
    assert operational_root(runtime) == tmp_path
    # The real builder passes its directory guard after canonical binding.
    result = build_trading_context(repo_root=operational_root(runtime), read_report_ids=[])
    assert result['context_sha256']


@pytest.mark.parametrize('fault', ['manifest', 'target', 'nested_cache'])
def test_foreign_or_changed_shared_mount_is_not_whitelisted(tmp_path, fault):
    runtime = snapshot(tmp_path)
    other = tmp_path/'other';other.mkdir()
    if fault == 'manifest':
        (runtime.parent/'manifest.json').write_text('{}')
    elif fault == 'target':
        (runtime/'output').unlink();(runtime/'output').symlink_to(other)
    else:
        cache = tmp_path/'output/live/kol_policy/context';cache.parent.mkdir(parents=True)
        cache.symlink_to(other)
        with pytest.raises(TradingContextError, match='symlink_forbidden'):
            build_trading_context(repo_root=operational_root(runtime), read_report_ids=[])
        return
    with pytest.raises(ValueError, match='RUNTIME_SHARED_STATE_BINDING_INVALID'):
        operational_root(runtime)
