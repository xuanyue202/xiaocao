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
    if not packet_path or not worker:
        return None
    cutoff = aware(request['review_wait_until'])
    if now.utcoffset() is None or not aware(request['requested_at']) <= now < cutoff:
        raise ValueError('MORNING_DISPATCH_ORIGINAL_CUTOFF')
    packet = json.loads(Path(packet_path).read_bytes())
    original_facts = {k:v for k,v in request.items()
                      if k not in {'kol_inputs', 'dispatch_budget', 'request_id', 'request_sha256'}}
    if (packet.get('packet_sha256') != inputs.get('packet_sha256')
            or packet.get('packet_sha256') != canonical_sha256({k:v for k,v in packet.items() if k!='packet_sha256'})
            or packet.get('worker_id') != worker or packet.get('cutoff') != request['review_wait_until']
            or packet.get('request_facts_sha256') != canonical_sha256(original_facts)):
        raise ValueError('MORNING_DISPATCH_PACKET_BINDING_MISMATCH')
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
    value['sha256'] = canonical_sha256(value)
    atomic_write(path,json.dumps(value,ensure_ascii=False,sort_keys=True).encode(),immutable=True)
    return path
