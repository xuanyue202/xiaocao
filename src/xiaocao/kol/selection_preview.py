"""Producer recommendation preview from accepted preparation, never trading policy."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from time import perf_counter

from . import opening_preparation as preparation
from .publication import canonical_sha256
from .selection import select_candidates, selection_diff


def register_preparation(input_path: Path, path: Path, prepared: dict) -> None:
    """Register accepted full source coverage under its original APP owner."""
    binding = prepared['binding']
    if (binding.get('automation_id') != 'xiaocao-book-b-live-morning'
            or os.environ.get('CODEX_AUTOMATION_ID') != binding['automation_id']
            or os.environ.get('CODEX_THREAD_ID') != binding.get('owner_thread_id')):
        raise ValueError('KOL_PREPARATION_PREVIEW_OWNER_MISMATCH')
    if input_path != Path(prepared['input_path']).resolve():
        raise ValueError('KOL_PREPARATION_PREVIEW_INPUT_MISMATCH')
    # Rules are exact repository-relative paths already verified by acceptance.
    root = Path(prepared['rules'][0]['path']).parents[1]
    directory = root / 'output/live/kol_selection_preparations' / binding['trade_date']
    preparation.write_artifact(directory, {
        'schema_version': 'kol-selection-preparation-reference.v1', 'authority': 0,
        'binding': binding, 'preparation_path': str(path.resolve()),
        'preparation_sha256': prepared['preparation_sha256']}, '.json')


def current_source_fingerprint(root: Path, now: datetime, trade_date: str) -> str:
    from .trading_context import build_trading_context, write_trading_projection
    context = build_trading_context(repo_root=root, read_report_ids=[], include_report_bodies=False,
        as_of=now, history_fresh_through=trade_date + 'T11:30:00+08:00')
    summary = write_trading_projection(context, repo_root=root)
    return preparation.read_projection(summary)['source_fingerprint']


def registered_preparation(root: Path, trade_date: str, *, now: datetime) -> tuple[Path, dict] | None:
    """Read an accepted source brief without waiting for its APP owner."""
    from .rolling_preparation import registered
    rolling = registered(root, now=now)
    if rolling is not None:
        return rolling
    accepted = []
    for path in sorted((root / 'output/live/kol_selection_preparations' / trade_date).glob('*.json')):
        if path.is_symlink():
            raise ValueError('PREPARATION_REFERENCE_SYMLINK')
        reference = json.loads(path.read_bytes())
        if path.name != canonical_sha256(reference) + '.json' or reference.get('authority') != 0:
            raise ValueError('PREPARATION_REFERENCE_HASH_MISMATCH')
        source_path = Path(reference['preparation_path'])
        prepared = preparation.read_preparation(source_path, now=now)
        if (reference.get('binding') != prepared['binding']
                or reference.get('preparation_sha256') != prepared['preparation_sha256']
                or prepared['binding'].get('automation_id') != 'xiaocao-book-b-live-morning'
                or prepared['binding'].get('trade_date') != trade_date):
            raise ValueError('PREPARATION_REFERENCE_BINDING_MISMATCH')
        accepted.append((source_path, prepared))
    if len(accepted) > 1:
        raise ValueError('PREPARATION_REFERENCE_AMBIGUOUS')
    return accepted[0] if accepted else None


def preview(rows: list[dict], freeze: dict, *, root: Path, now: datetime,
            fingerprint_reader=current_source_fingerprint) -> dict:
    """Read local immutable evidence once; missing/stale support preserves baseline."""
    started = perf_counter()
    baseline = [r['code'] for r in rows if r.get('mode_exec_star') is True]
    result = {'schema_version': 'kol-recommendation-preview.v1', 'authority': 0,
        'trade_date': freeze['market_date'], 'freeze': freeze, 'observed_at': now.isoformat(),
        'baseline_codes': baseline, 'selected_codes': baseline,
        'policy_adoption': 'not_performed', 'status': 'baseline', 'reason': 'PREPARATION_UNAVAILABLE'}
    try:
        accepted = registered_preparation(root, freeze['market_date'], now=now)
        if accepted:
            _, prepared = accepted
            preferences = prepared['draft'].get('selection_preferences', [])
            rolling = prepared.get('schema_version') == 'kol-opening-preparation.v2'
            if rolling:
                result.update(preparation_sha256=prepared['preparation_sha256'],
                    source_synthesis=prepared['draft']['synthesis'],
                    source_coverage_limits=prepared['draft']['source_coverage_limits'],
                    unresolved_semantic_conditions=prepared['draft'].get('policy_template', {}).get(
                        'unresolved_semantic_conditions', []),
                    current_applicability='not_completed',
                    current_source_head='not_checked')
            executable = any(item['applicability']=='supported' for item in preferences)
            from .prepared_policy import preview_risk
            risk = preview_risk(prepared, trade_date=freeze['market_date'], now=now) if rolling else None
            if (preferences and (executable or not rolling)) or risk is not None:
                if rolling:
                    from .rolling_preparation import validate_current_sources
                    validate_current_sources(prepared, now=now)
                if fingerprint_reader(root, now, freeze['market_date']) != prepared['source_fingerprint']:
                    raise ValueError('PREPARATION_SOURCE_CHANGED')
                selection = select_candidates(rows, preferences, trade_date=freeze['market_date'],
                    freeze_sha256=freeze['snapshot_sha256'])
                result.update(status='prepared_preview', reason='REVIEWED_PREPARATION_RECOMMENDATION_ONLY',
                    selected_codes=selection.receipt['selected_codes'], selection=selection.receipt,
                    preparation_sha256=prepared['preparation_sha256'],
                    source_fingerprint=prepared['source_fingerprint'])
                if rolling:
                    result['current_source_head'] = 'fingerprint_matched'
                if risk is not None:
                    adjusted = [dict(row) for row in selection.rows]
                    for row in adjusted:
                        weight = row.get('mode_exec_target_weight') or 0
                        row['mode_exec_target_weight'] = (0 if row.get('code') in risk['skip_codes']
                                                          else weight * risk['buy_scale'])
                    result.update(candidate_codes=selection.receipt['selected_codes'],
                        selected_codes=[row['code'] for row in adjusted if row.get('mode_exec_star') is True
                                        and row['mode_exec_target_weight'] > 0],
                        risk_adjustment=risk, portfolio_diff=selection_diff(rows, adjusted),
                        current_applicability='explicit_prepared_conditions_satisfied')
            else:
                result['reason'] = ('CURRENT_APPLICABILITY_REVIEW_REQUIRED' if rolling and
                    result['unresolved_semantic_conditions'] else 'PREPARATION_NO_SELECTION_PREFERENCE')
                if rolling:
                    # Complete observable unchanged comparison; this is not
                    # source revalidation or a completed neutral judgment.
                    result['selection'] = select_candidates(rows, [], trade_date=freeze['market_date'],
                        freeze_sha256=freeze['snapshot_sha256']).receipt
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status='degraded', reason=str(exc))
    result['elapsed_seconds'] = round(perf_counter() - started, 6)
    result['receipt_sha256'] = canonical_sha256(result)
    return result


def render(value: dict) -> str:
    baseline = ', '.join(value['baseline_codes']) or '空'
    selected = ', '.join(value['selected_codes']) or '空'
    synthesis = ''
    if value.get('source_synthesis'):
        synthesis = '\n小草跨日判断（当前适用性另行核验）：\n\n' + '\n'.join(
            '- ' + item['judgment'] + ' 条件：' + item['conditions']
            for item in value['source_synthesis']) + '\n\n'
    if value.get('risk_adjustment'):
        synthesis += '当下条件下的新增仓位系数：' + str(value['risk_adjustment']['buy_scale']) + '。'
        synthesis += value['risk_adjustment']['rationale'] + '\n\n'
    return (f"\n## KOL 候选偏好（推荐预览）\n\n"
        f"状态：{value['status']}；原因：{value['reason']}。\n\n"
        f"冻结基线：{baseline}。\n\nKOL 推荐：{selected}。\n\n"
        + synthesis + f"本地处理 {value['elapsed_seconds']:.3f}s；回执 `{value['receipt_sha256']}`。"
        "正式 APP/Paper 采纳以各自当前账户、行情及独立复核的批次政策为准。\n")


def read_recommendation(live_dir: Path, date: str, bundle: dict) -> dict:
    """Observe the original producer's exact preview, separately from adoption."""
    try:
        pointer = live_dir / f'morning_kol_recommendation_{date}.json'
        reference = json.loads(pointer.read_bytes())
        path = Path(reference['path'])
        if pointer.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(
                (live_dir/'kol_recommendations'/date).resolve()):
            raise ValueError('PREVIEW_REFERENCE_PATH_INVALID')
        value = json.loads(path.read_bytes())
        claimed = value['receipt_sha256']
        if (claimed != canonical_sha256({k:v for k,v in value.items() if k!='receipt_sha256'})
                or claimed != reference['receipt_sha256'] or value.get('authority') != 0
                or value.get('trade_date') != date or bundle.get('status') != 'ready'
                or any(value['freeze'].get(key) != bundle.get(key) for key in
                       ('snapshot_sha256','checkpoint_sha256','strategy_run_id','strategy_sha'))):
            raise ValueError('PREVIEW_ORIGINAL_BINDING_UNPROVEN')
        return {key:value.get(key) for key in ('status','reason','authority','receipt_sha256',
            'baseline_codes','selected_codes','elapsed_seconds','preparation_sha256','policy_adoption')}
    except (OSError,ValueError,KeyError,TypeError):
        return {'status':'unproved','authority':0,'policy_adoption':'not_performed'}
