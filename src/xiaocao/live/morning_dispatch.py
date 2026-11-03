"""Assemble a warm-worker handoff; never dispatch a model or authorize policy."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from xiaocao.kol.opening_preparation import aware, canonical_sha256
from xiaocao.utils.atomic_files import atomic_write
from .morning_observability import review_brief


def write_warm_dispatch(request: dict, request_path: Path, *, now: datetime) -> Path | None:
    inputs = request.get('kol_inputs') or {}
    packet_path = inputs.get('packet_path')
    worker = inputs.get('warm_worker')
    if not packet_path:
        return None
    packet = json.loads(Path(packet_path).read_bytes())
    shared = packet.get('preparation_adoption')
    if not worker and not shared:
        return None
    cutoff = aware(request['review_wait_until'])
    if now.utcoffset() is None or not aware(request['requested_at']) <= now < cutoff:
        raise ValueError('MORNING_DISPATCH_ORIGINAL_CUTOFF')
    original_facts = {k:v for k,v in request.items()
                      if k not in {'kol_inputs', 'dispatch_budget', 'request_id', 'request_sha256'}}
    if (packet.get('packet_sha256') != inputs.get('packet_sha256')
            or packet.get('packet_sha256') != canonical_sha256({k:v for k,v in packet.items() if k!='packet_sha256'})
            or (not shared and packet.get('worker_id') != worker) or packet.get('cutoff') != request['review_wait_until']
            or packet.get('request_facts_sha256') != canonical_sha256(original_facts)):
        raise ValueError('MORNING_DISPATCH_PACKET_BINDING_MISMATCH')
    if shared:
        from xiaocao.kol.preparation_adoption import read_adoption
        adopted = read_adoption(Path(shared['path']), Path(packet['preparation_path']),
                                Path(packet['current_input_path']), now=now)
        if (worker is not None or request.get('runtime') != 'paper'
                or adopted['adoption_sha256'] != shared.get('sha256')
                or adopted['binding'] != request.get('binding')):
            raise ValueError('MORNING_DISPATCH_ADOPTION_BINDING_MISMATCH')
    path = request_path.with_suffix('.dispatch.json')
    identifier = request['request_sha256']
    # Ordinary COLD remains gated; the reviewed source-bound v2 exception is
    # intentional. A blanket COLD ban would contradict the consuming policy.
    message = (
        f'原冻结评审现已就绪。立即读取这一个由原runner装配的authority=0交接文件：{path.resolve()}。'
        f'原请求{identifier}，截止{cutoff.isoformat()}；只复核相关已准备结论、全部delta与当前账户/风险事实。'
        '复用未变化准备，不重扫完整来源。引用必须精确核验，正式决策仍须父级独立复核后在原截止前发布。'
        '预算不足就保留明确降级；不回填。普通COLD门保留，仅已验证v2小草显式模式跟随可恢复COLD；'
        'UNKNOWN模式及账户、行情、资金、风险和精确一次门不变。这个文件不是实际dispatch或政策采用证明。'
    )
    value = {'schema_version':'morning-warm-dispatch.v1','authority':0,
        'request_sha256':identifier,'request_path':str(request_path.resolve()),
        'prepared_at':now.isoformat(),'cutoff':cutoff.isoformat(),
        'remaining_seconds_at_assembly':(cutoff-now).total_seconds(),
        'brief':review_brief(request),'packet':packet,
        'tool_arguments':{'target':worker,'message':message},
        'actual_dispatch':'not_observed','publication':'not_observed'}
    try:
        from xiaocao.kol.opening_preparation import read_preparation, write_artifact
        from xiaocao.kol.prepared_policy import materialize, defer_no_effect
        prepared = read_preparation(Path(packet['preparation_path']), now=now)
        try:
            deferred = defer_no_effect(prepared,packet,request,now=now)
        except ValueError:
            deferred = None
        if deferred is not None:
            value.update(next_action='continue_original_baseline_deferred', deferred_overlay=deferred)
        else:
            candidate = materialize(prepared,packet,request,now=now)
            context_path = write_artifact(request_path.parent,prepared['context'],'.publication-context.json')
            decision_path = write_artifact(request_path.parent,candidate['decision'],'.decision.json')
            from .kol_policy import decision_sha256
            candidate.update(context_path=str(context_path),decision_path=str(decision_path),
                decision_sha256=decision_sha256(candidate['decision']))
            candidate_path = write_artifact(request_path.parent,candidate,'.prepared-policy.json')
            value.update(next_action='independently_review_prepared_draft',
                prepared_policy_path=str(candidate_path), prepared_policy_sha256=canonical_sha256(candidate))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        value.update(next_action='dispatch_warm_worker', prepared_policy_unavailable=type(exc).__name__+':'+str(exc))
        if shared:
            # Source reasoning is reusable; an APP child is not addressable
            # from a different Paper thread. Only current applicability is new.
            value.update(next_action='dispatch_current_worker', tool_arguments={
                'task_name': 'paper_kol_current_' + identifier[:12],
                'model': 'gpt-6-sol', 'reasoning_effort': 'xhigh', 'fork_turns': 'none',
                'message': message + '共享准备已完成全量来源阅读；只处理本Paper请求当前适用性及delta，不重做完整来源准备。'})
    value['sha256'] = canonical_sha256(value)
    atomic_write(path,json.dumps(value,ensure_ascii=False,sort_keys=True).encode(),immutable=True)
    return path


def read_deferred_overlay(path: Path, request_sha256: str) -> dict | None:
    """Validate the exact generated supporting directive before skipping a wait."""
    if path.is_symlink():
        raise ValueError('MORNING_DISPATCH_DEFER_PATH_INVALID')
    value=json.loads(path.read_bytes())
    if (value.get('sha256')!=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
            or value.get('request_sha256')!=request_sha256):
        raise ValueError('MORNING_DISPATCH_DEFER_HASH_INVALID')
    if value.get('next_action')!='continue_original_baseline_deferred':
        return None
    deferred=value['deferred_overlay']
    if (deferred.get('sha256')!=canonical_sha256({k:v for k,v in deferred.items() if k!='sha256'})
            or deferred.get('request_sha256')!=request_sha256 or deferred.get('authority')!=0
            or deferred.get('status')!='deferred' or deferred.get('semantic_review_completed') is not False):
        raise ValueError('MORNING_DISPATCH_DEFER_BINDING_INVALID')
    return deferred
