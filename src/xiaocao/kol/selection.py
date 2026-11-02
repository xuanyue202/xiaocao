"""Pure ordinal preferences over original Book-B rows; never data, orders or cash."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .publication import canonical_sha256
from xiaocao.strategy.mode_switch import target_weights

SECTOR_FIELDS = {'excIndustryCode', 'blockCodeList', 'blockCategoryCodeList'}
FACT_FIELDS = {'mode_state', 'open_pct_change', 'market_guard_status', 'market_price',
               'open', 'basket_price', 'is_main_line', 'is_big_cap', 'direction'}
_CODE = re.compile(r'\d{6}\.(XSHG|XSHE|BJSE)\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


class SelectionError(ValueError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise SelectionError(reason)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_preferences(preferences: list[dict]) -> None:
    _require(isinstance(preferences, list), 'SELECTION_PREFERENCES_REQUIRED')
    ids, targets = set(), set()
    for pref in preferences:
        _require(isinstance(pref, dict) and _text(pref.get('id')) and pref['id'] not in ids,
                 'SELECTION_PREFERENCE_ID_INVALID')
        ids.add(pref['id'])
        kind, target = pref.get('kind'), pref.get('target')
        _require(kind in {'mode','sector','candidate'} and isinstance(target, dict), 'SELECTION_TARGET_INVALID')
        if kind == 'mode':
            _require(set(target) == {'mode'} and _text(target['mode']), 'SELECTION_MODE_INVALID')
        elif kind == 'candidate':
            _require(set(target) == {'code','mode'} and isinstance(target['code'],str)
                     and _CODE.fullmatch(target['code']) is not None and _text(target['mode']),
                     'SELECTION_CANDIDATE_INVALID')
        else:
            _require(set(target) == {'field','code','name','mapping_ref'} and target['field'] in SECTOR_FIELDS
                     and _text(target['code']) and _text(target['name']), 'SELECTION_SECTOR_INVALID')
            ref = target['mapping_ref']
            _require(isinstance(ref,dict) and set(ref)=={'path','sha256'} and _text(ref['path'])
                     and isinstance(ref['sha256'],str) and _SHA.fullmatch(ref['sha256']) is not None,
                     'SELECTION_SECTOR_MAPPING_REQUIRED')
        identity = {k:v for k,v in target.items() if k not in {'mapping_ref','name'}}
        key = (kind, canonical_sha256(identity))
        _require(key not in targets, 'SELECTION_TARGET_CONFLICT')
        targets.add(key)
        _require(pref.get('direction') in {'prefer','deprioritize'} and
                 pref.get('applicability') in {'supported','uncertain','contradicted'}, 'SELECTION_EFFECT_INVALID')
        _require(all(_text(pref.get(k)) for k in ('source_report_id','source_quote','rationale')),
                 'SELECTION_SOURCE_REQUIRED')
        _require(isinstance(pref.get('conditions'),list), 'SELECTION_CONDITIONS_REQUIRED')
        for condition in pref['conditions']:
            _require(isinstance(condition,dict) and set(condition)=={'field','op','value','evidence_ref'}
                     and condition['field'] in FACT_FIELDS and _text(condition['evidence_ref']),
                     'SELECTION_CONDITION_INVALID')
            op, value = condition['op'], condition['value']
            _require(op in {'lt','lte','gt','gte','eq','in'}, 'SELECTION_OPERATOR_INVALID')
            values = value if op=='in' and isinstance(value,list) else [value]
            _require(op!='in' or isinstance(value,list) and bool(value), 'SELECTION_CONDITION_VALUE_INVALID')
            _require(all(type(v) in (str,int,float,bool) and (type(v) not in (int,float) or math.isfinite(v))
                         for v in values), 'SELECTION_CONDITION_VALUE_INVALID')
            _require(op in {'eq','in'} or type(value) in (int,float), 'SELECTION_NUMERIC_CONDITION_REQUIRED')


def _equal(value: object, expected: object) -> bool:
    if type(value) in (int, float) and type(expected) in (int, float):
        return math.isfinite(value) and value == expected
    return type(value) is type(expected) and value == expected


def conditions_hold(row: dict, conditions: list[dict]) -> bool:
    """Evaluate validated finite predicates; absent facts never support a rule."""
    for condition in conditions:
        value, expected, op = row.get(condition['field']), condition['value'], condition['op']
        if value is None:
            return False
        if op=='eq':
            if not _equal(value, expected):
                return False
        elif op=='in':
            if not any(_equal(value, item) for item in expected):
                return False
        else:
            if type(value) not in (int,float) or not math.isfinite(value):
                return False
            if not {'lt':value<expected,'lte':value<=expected,'gt':value>expected,'gte':value>=expected}[op]:
                return False
    return True


def _matches(row: dict, preference: dict) -> bool:
    target, kind = preference['target'], preference['kind']
    if kind=='mode':
        return row.get('mode')==target['mode']
    if kind=='candidate':
        return (row.get('code'),row.get('mode'))==(target['code'],target['mode'])
    value = row.get(target['field'])
    return target['code'] in value if isinstance(value,list) else value==target['code']


def _number(value: object, default: float = 9999) -> float:
    return float(value) if type(value) in (int,float) and math.isfinite(value) else default


@dataclass(frozen=True)
class SelectionResult:
    rows: list[dict]
    receipt: dict


def select_candidates(rows: list[dict], preferences: list[dict], *, trade_date: str,
                      freeze_sha256: str, max_slots: int = 3,
                      frozen_rows: list[dict] | None = None) -> SelectionResult:
    validate_preferences(preferences)
    _require(type(max_slots) is int, 'SELECTION_SLOT_LIMIT_INVALID')
    _require(isinstance(freeze_sha256,str) and _SHA.fullmatch(freeze_sha256) is not None,
             'SELECTION_FREEZE_BINDING_REQUIRED')
    copied = [dict(row) for row in rows]
    identities = [(r.get('code'),r.get('mode')) for r in copied]
    _require(len(identities)==len(set(identities)), 'SELECTION_DUPLICATE_CANDIDATE')
    original = rows if frozen_rows is None else frozen_rows
    facts = {(r.get('code'),r.get('mode')):r for r in original}
    _require(len(facts)==len(original) and set(identities)==set(facts), 'SELECTION_ORIGINAL_FACTS_MISMATCH')
    limit = max(0,min(3,max_slots))
    def eligible(row):
        return (row.get('date')==trade_date and row.get('book')=='B' and row.get('is_live') is True
                and isinstance(row.get('code'),str) and _CODE.fullmatch(row['code']) is not None
                and not row['code'].endswith('.BJSE') and _text(row.get('mode'))
                and row.get('mode_state') in {'ACTIVE','PROVISIONAL'} and row.get('mode_trade_eligible') is True
                and ('executable_fillable' not in row or row['executable_fillable'] is True))
    pool = [row for row in copied if eligible(row)]
    pool.sort(key=lambda r: (_number(r.get('mode_exec_candidate_rank')),
                            _number(r.get('mode_exec_rank')),-_number(r.get('mode_exec_score'),0),r['code'],r['mode']))
    inherited = [row for row in pool if row.get('mode_exec_star') is True][:limit]
    baseline = [row for row in original if eligible(row) and row.get('mode_exec_star') is True][:limit]
    matches = {pref['id']:{(r['code'],r['mode']) for r in pool if pref['applicability']=='supported'
                          and _matches(facts[(r['code'],r['mode'])],pref)
                          and conditions_hold(facts[(r['code'],r['mode'])],pref['conditions'])} for pref in preferences}
    active = [pref for pref in preferences if matches[pref['id']]]
    if active:
        def priority(row):
            key = (row['code'],row['mode'])
            return tuple((0 if key in matches[p['id']] else 1) if p['direction']=='prefer'
                         else (1 if key in matches[p['id']] else 0) for p in active)
        pool.sort(key=priority)  # Stable: ties retain the original deterministic rank.
        chosen, modes, codes = [], set(), set()
        for row in pool:
            if row['mode'] in modes or row['code'] in codes:
                continue
            chosen.append(row);modes.add(row['mode']);codes.add(row['code'])
        for row in copied:
            row.update(mode_exec_star=False,mode_exec_rank=9999,mode_exec_target_weight=0.)
        # Paper's board-lot allocator reads the entire ranked reserve pool.
        # Rank every row so an old same-mode favourite cannot jump a new pick.
        for rank,row in enumerate(pool,1):
            row['mode_exec_candidate_rank']=rank
        selected = chosen[:limit]
        for rank,(row,weight) in enumerate(zip(selected,target_weights([r['mode_state'] for r in selected])),1):
            row.update(mode_exec_star=True,mode_exec_rank=rank,mode_exec_target_weight=weight)
            row['kol_selection_preferences']=[p['id'] for p in active if (row['code'],row['mode']) in matches[p['id']]]
        order={id(row):index for index,row in enumerate(pool)}
        copied.sort(key=lambda row:order.get(id(row),len(pool)))
    else:
        selected = inherited
        selected_ids = {id(row) for row in selected}
        for row in copied:
            if not eligible(row) or (row.get('mode_exec_star') is True and id(row) not in selected_ids):
                row.update(mode_exec_star=False, mode_exec_rank=9999, mode_exec_target_weight=0.)
    receipt={'schema_version':'kol-selection-result.v1','trade_date':trade_date,'freeze_sha256':freeze_sha256,
             'candidate_pool_sha256':canonical_sha256([list(key) for key in identities]),
             'preferences_sha256':canonical_sha256(preferences),
             'baseline_codes':[r['code'] for r in baseline],'selected_codes':[r['code'] for r in selected],
             'selected_identities':[{'code':r['code'],'mode':r['mode']} for r in selected],
             'preferences':[{'id':p['id'],'kind':p['kind'],'direction':p['direction'],
                             'status':'applied' if matches[p['id']] else 'not_applicable',
                             'matched_codes':sorted({code for code,_ in matches[p['id']]})} for p in preferences],
             'diff':selection_diff(original,copied),
             'authority':'selection_only_allocation_and_execution_gates_required'}
    receipt['receipt_sha256']=canonical_sha256(receipt)
    return SelectionResult(copied,receipt)


def selection_diff(before: list[dict], after: list[dict]) -> dict:
    """Observable selection effects, without inventing fills or future returns."""
    original = {(row['code'],row['mode']):row for row in before}
    changes = []
    for row in after:
        key = (row['code'],row['mode'])
        old = original[key]
        values = lambda item: {
            'selected':item.get('mode_exec_star') is True,
            'candidate_rank':_number(item.get('mode_exec_candidate_rank')),
            'seat_rank':_number(item.get('mode_exec_rank')),
            'target_weight':_number(item.get('mode_exec_target_weight'),0.),
        }
        previous,current = values(old),values(row)
        if previous != current:
            changes.append({'code':key[0],'mode':key[1],'before':previous,'after':current})

    def exposure(rows):
        modes, sectors = {}, {}
        selected = [row for row in rows if row.get('mode_exec_star') is True]
        for row in selected:
            weight = _number(row.get('mode_exec_target_weight'),0.)
            modes[row['mode']] = modes.get(row['mode'],0.) + weight
            for field in sorted(SECTOR_FIELDS):
                codes = row.get(field,[])
                codes = codes if isinstance(codes,list) else [codes]
                for code in codes:
                    if isinstance(code,str) and code:
                        key = field+':'+code
                        sectors[key] = sectors.get(key,0.) + weight
        return {'selected_identities':[{'code':r['code'],'mode':r['mode']} for r in selected],
                'mode_target_weights':modes,'sector_membership_weights':sectors,
                'sector_weight_note':'overlapping_memberships_not_additive_portfolio_exposure'}

    old,new = exposure(before),exposure(after)
    old_keys = {(r['code'],r['mode']) for r in old['selected_identities']}
    new_keys = {(r['code'],r['mode']) for r in new['selected_identities']}
    return {'row_rank_and_seat_changes':changes,'before':old,'after':new,
            'added_seats':[{'code':code,'mode':mode} for code,mode in sorted(new_keys-old_keys)],
            'removed_seats':[{'code':code,'mode':mode} for code,mode in sorted(old_keys-new_keys)]}
