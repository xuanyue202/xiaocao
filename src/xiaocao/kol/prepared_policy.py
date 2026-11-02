"""Instantiate already reviewed conditional semantics, returning an unapproved draft.

No semantic classification, review approval, policy-store write or execution.
New evidence/unresolved prose requires the existing bounded worker branch.
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from time import perf_counter

from .publication import canonical_sha256
from .selection import conditions_hold, SelectionError
from xiaocao.live import kol_policy

_EFFECT_FIELDS = {'buy_scale','skip_codes','exit_codes','rationale','invalidation_conditions',
                  'xiaocao_mode_overrides','mode_mappings'}
_TEMPLATE_FIELDS = _EFFECT_FIELDS | {'source_report_ids','request_conditions','unresolved_semantic_conditions'}
_FACT_FIELDS = {'account_risk_status', 'account_deploy_factor'}


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise SelectionError(reason)


def validate_template(template: dict, reports: dict[str, dict]) -> None:
    _require(isinstance(template,dict) and set(template)-{'defer_if_no_effect'}==_TEMPLATE_FIELDS,
             'PREPARED_POLICY_TEMPLATE_INVALID')
    _require('defer_if_no_effect' not in template or type(template['defer_if_no_effect']) is bool,
             'PREPARED_POLICY_DEFER_FLAG_INVALID')
    scale = template['buy_scale']
    _require(type(scale) in (int,float) and 0<=scale<=1, 'PREPARED_POLICY_SCALE_INVALID')
    for name in ('skip_codes','exit_codes'):
        codes=template[name]
        _require(isinstance(codes,list) and len(codes)==len(set(codes))
                 and all(kol_policy._valid_code(code,'B') for code in codes), 'PREPARED_POLICY_CODES_INVALID')
    _require(isinstance(template['rationale'],str) and bool(template['rationale'].strip())
             and isinstance(template['invalidation_conditions'],list) and bool(template['invalidation_conditions'])
             and all(isinstance(v,str) and v.strip() for v in template['invalidation_conditions']),
             'PREPARED_POLICY_REASON_REQUIRED')
    ids=template['source_report_ids']
    _require(isinstance(ids,list) and bool(ids) and len(ids)==len(set(ids)) and set(ids)<=reports.keys(),
             'PREPARED_POLICY_SOURCE_REQUIRED')
    _require(isinstance(template['xiaocao_mode_overrides'],list) and isinstance(template['mode_mappings'],list)
             and isinstance(template['unresolved_semantic_conditions'],list), 'PREPARED_POLICY_LIST_REQUIRED')
    conditions=template['request_conditions']
    _require(isinstance(conditions,list), 'PREPARED_POLICY_CONDITIONS_REQUIRED')
    for condition in conditions:
        _require(isinstance(condition,dict) and set(condition)=={'field','op','value','evidence_ref'}
                 and condition['field'] in _FACT_FIELDS and isinstance(condition['evidence_ref'],str)
                 and bool(condition['evidence_ref'].strip()), 'PREPARED_POLICY_CONDITION_INVALID')
        op,value=condition['op'],condition['value']
        _require(op in {'eq','in','lt','lte','gt','gte'}, 'PREPARED_POLICY_OPERATOR_INVALID')
        values=value if op=='in' and isinstance(value,list) else [value]
        _require(op!='in' or isinstance(value,list) and bool(value), 'PREPARED_POLICY_VALUE_INVALID')
        _require(all(type(v) in (str,int,float,bool) and (type(v) not in (int,float) or math.isfinite(v))
                     for v in values) and (op in {'eq','in'} or type(value) in (int,float)),
                 'PREPARED_POLICY_VALUE_INVALID')


def _bound_template(prepared: dict, packet: dict, request: dict, now: datetime) -> tuple:
    from .opening_preparation import aware
    template = prepared['draft'].get('policy_template')
    _require(template is not None and prepared['review'].get('policy_template_reviewed') is True,
             'PREPARED_POLICY_NOT_REVIEWED')
    reports={r['report_id']:r for r in prepared['context']['reports']}
    validate_template(template,reports)
    _require(packet['preparation_sha256']==prepared['preparation_sha256']
             and packet['source_fingerprint']==prepared['source_fingerprint']
             and all(not packet['delta'].get(name) for name in ('added','changed','removed')),
             'PREPARED_POLICY_SOURCE_DELTA_REQUIRES_WORKER')
    unsigned={k:v for k,v in request.items() if k not in {'request_id','request_sha256'}}
    _require(request.get('request_sha256')==kol_policy.decision_sha256(unsigned), 'PREPARED_POLICY_REQUEST_HASH_INVALID')
    packet_facts={k:v for k,v in unsigned.items() if k not in {'kol_inputs','dispatch_budget'}}
    _require(packet['request_facts_sha256']==canonical_sha256(packet_facts)
             and packet['packet_sha256']==canonical_sha256({k:v for k,v in packet.items() if k!='packet_sha256'}),
             'PREPARED_POLICY_PACKET_BINDING_INVALID')
    cutoff=aware(packet['cutoff'])
    _require(now.utcoffset() is not None and aware(request['requested_at'])<=now<cutoff
             and now<aware(prepared['draft']['valid_until']), 'PREPARED_POLICY_ORIGINAL_DEADLINE')
    binding={k:request.get('freeze',{}).get(k) for k in kol_policy.SELECTION_BINDING_FIELDS}
    _require(binding['snapshot_sha256']==request.get('freeze_sha256')
             and binding['market_date']==prepared['binding']['trade_date']==request['trade_date'],
             'PREPARED_POLICY_FREEZE_BINDING_INVALID')
    risk=request.get('account_risk') or {}
    facts={'account_risk_status':risk.get('status'),'account_deploy_factor':risk.get('deploy_factor')}
    _require(conditions_hold(facts,template['request_conditions']), 'PREPARED_POLICY_CURRENT_CONDITION_UNPROVEN')
    preferences=prepared['draft'].get('selection_preferences',[])
    _require(packet.get('selection_preferences',[])==preferences, 'PREPARED_POLICY_PREFERENCE_DELTA')
    ids=set(template['source_report_ids'])
    _require(all(p['source_report_id'] in ids for p in preferences)
             and all(p.get('source_report_id') in ids for p in template['xiaocao_mode_overrides']),
             'PREPARED_POLICY_EFFECT_SOURCE_NOT_CITED')
    return template,reports,binding,preferences


def defer_no_effect(prepared: dict, packet: dict, request: dict, *, now: datetime) -> dict:
    """Skip optional inference only under a separately reviewed baseline fallback.

    Existing valid policy and every deterministic trading gate still apply.
    This never declares a completed neutral judgment or grants policy authority.
    """
    template,_,binding,preferences = _bound_template(prepared,packet,request,now)
    _require(template.get('defer_if_no_effect') is True
             and prepared['review'].get('deferred_overlay_reviewed') is True,
             'PREPARED_DEFER_NOT_REVIEWED')
    _require(template['buy_scale']==1 and not template['skip_codes'] and not template['exit_codes']
             and not template['xiaocao_mode_overrides'], 'PREPARED_DEFER_RISK_EFFECT_PRESENT')
    from .selection import select_candidates
    selection = select_candidates(request['candidates'],preferences,trade_date=request['trade_date'],
                                  freeze_sha256=binding['snapshot_sha256'])
    _require(not any(p['status']=='applied' for p in selection.receipt['preferences']),
             'PREPARED_DEFER_SELECTION_EFFECT_PRESENT')
    value={'schema_version':'kol-prepared-deferred-overlay.v1','authority':0,'status':'deferred',
        'reason':'NO_EXECUTABLE_PREPARED_KOL_EFFECT','request_sha256':request['request_sha256'],
        'preparation_sha256':prepared['preparation_sha256'],'source_fingerprint':prepared['source_fingerprint'],
        'known_unresolved_conditions':template['unresolved_semantic_conditions'],
        'observed_at':now.isoformat(),'fallback':'original_baseline_under_current_policy',
        'semantic_review_completed':False,'model_dispatch':'not_performed','publication':'not_performed'}
    return {**value,'sha256':canonical_sha256(value)}


def materialize(prepared: dict, packet: dict, request: dict, *, now: datetime) -> dict:
    """Caller supplies already validated immutable inputs and the actual clock."""
    from .opening_preparation import aware
    from .trading_decision import _source
    started = perf_counter()
    template,reports,binding,preferences = _bound_template(prepared,packet,request,now)
    _require(not template['unresolved_semantic_conditions'], 'PREPARED_POLICY_SEMANTIC_REVIEW_NEEDED')
    ids=set(template['source_report_ids'])
    until=min(aware(prepared['draft']['valid_until']),aware(prepared['binding']['trade_date']+'T11:30:00+08:00'))
    draft={'schema_version':kol_policy.SELECTION_SCHEMA_VERSION,
        'decision_id':'prepared-'+request['request_sha256'][:24], 'agent_id':prepared['worker_id'],
        'book':'B','runtime':request['runtime'],'as_of':now.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
        'valid_until':until.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
        **copy.deepcopy({key:template[key] for key in _EFFECT_FIELDS}),
        'source_refs':[_source(reports[rid]) for rid in sorted(ids)],
        'selection_preferences':copy.deepcopy(preferences),'selection_binding':binding,
        'morning_request_sha256':request['request_sha256'],
        'prepared_semantics_sha256':prepared['preparation_sha256'],
        'current_checks':[{'claim':'Reviewed preparation unchanged; explicit current request predicates hold.',
            'observed_at':aware(request['requested_at']).astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
            'evidence_ref':'request-sha256:'+request['request_sha256'],
            'verdict':'supports'}]}
    return {'schema_version':'kol-prepared-policy-draft.v1','authority':0,'status':'independent_review_required',
        'request_sha256':request['request_sha256'],'decision':draft,
        'context_sha256':prepared['context']['context_sha256'],
        'source_coverage':{'cited_report_count':len(ids),
            'registered_report_count':len(prepared['context'].get('report_index',[]))},
        'review':'not_performed','source_verification':'not_performed','publication':'not_performed',
        'elapsed_seconds':perf_counter()-started}
