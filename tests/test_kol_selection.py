"""Pure selection interface; no broker, network, model or financial writes."""
import copy
import pytest
from xiaocao.kol.selection import select_candidates, validate_preferences, SelectionError


def row(code, mode, rank, *, state='ACTIVE', sector='T01.ZHBK'):
    return dict(code=code,mode=mode,date='2026-11-03',book='B',is_live=True,mode_state=state,
                mode_trade_eligible=state in {'ACTIVE','PROVISIONAL'},mode_exec_star=rank<=3,
                mode_exec_rank=rank,mode_exec_candidate_rank=rank,mode_exec_score=1/rank,
                excIndustryCode=sector,blockCodeList=['886100.DDBK'],open_pct_change=2.)


def preference(kind, target, **extra):
    return {'id':'p1','kind':kind,'target':target,'direction':'prefer',
            'source_report_id':'source-1','source_quote':'source words','rationale':'current source reasoning',
            'applicability':'supported','conditions':[],**extra}


def select(rows, prefs):
    return select_candidates(rows,prefs,trade_date='2026-11-03',freeze_sha256='a'*64)


def test_candidate_preferences_change_choice_without_mutating_original():
    rows=[row('000001.XSHE','A',1),row('000002.XSHE','A',4),row('000003.XSHE','B',2)]
    before=copy.deepcopy(rows)
    result=select(rows,[preference('candidate',{'code':'000002.XSHE','mode':'A'})])
    assert result.receipt['baseline_codes']==['000001.XSHE','000003.XSHE']
    assert result.receipt['selected_codes']==['000002.XSHE','000003.XSHE']
    diff=result.receipt['diff']
    assert diff['added_seats']==[{'code':'000002.XSHE','mode':'A'}]
    assert diff['removed_seats']==[{'code':'000001.XSHE','mode':'A'}]
    assert diff['row_rank_and_seat_changes'] and diff['after']['mode_target_weights']['A']>0
    assert 'excIndustryCode:T01.ZHBK' in diff['after']['sector_membership_weights']
    assert rows==before
    assert sorted((r for r in result.rows if r['mode_trade_eligible']),
                  key=lambda r:r['mode_exec_candidate_rank'])[0]['code']=='000002.XSHE'
    assert sum(r['mode_exec_target_weight'] for r in result.rows if r['mode_exec_star'])==pytest.approx(.5)


def test_mode_and_exact_sector_preferences_share_stable_selector():
    rows=[row('000001.XSHE','A',1),row('000002.XSHE','B',2,sector='T02.ZHBK'),row('000003.XSHE','C',3),row('000004.XSHE','D',4,sector='T02.ZHBK')]
    pref=preference('sector',{'field':'excIndustryCode','code':'T02.ZHBK','name':'canonical sector',
                             'mapping_ref':{'path':'/fixture/catalog.json','sha256':'b'*64}})
    assert select(rows,[pref]).receipt['selected_codes']==['000002.XSHE','000004.XSHE','000001.XSHE']
    assert select(rows,[preference('mode',{'mode':'D'})]).receipt['selected_codes'][0]=='000004.XSHE'


@pytest.mark.parametrize('damage',['COLD','UNKNOWN','unfillable','BJSE','foreign_date'])
def test_preferences_cannot_qualify_forbidden_candidates(damage):
    rows=[row('000001.XSHE','A',1),row('000002.XSHE','B',4)]
    if damage in {'COLD','UNKNOWN'}: rows[1].update(mode_state=damage,mode_trade_eligible=True)
    elif damage=='unfillable': rows[1]['executable_fillable']=False
    elif damage=='BJSE': rows[1]['code']='830001.BJSE'
    else: rows[1]['date']='2026-11-04'
    p=preference('candidate',{'code':rows[1]['code'],'mode':'B'})
    result=select(rows,[p]); assert rows[1]['code'] not in result.receipt['selected_codes']


def test_unresolved_and_unmet_conditions_have_no_selection_effect():
    rows=[row('000001.XSHE','A',1),row('000002.XSHE','B',4)]
    p=preference('mode',{'mode':'B'},conditions=[{'field':'open_pct_change','op':'lt','value':0,'evidence_ref':'source-condition'}])
    assert select(rows,[p]).receipt['selected_codes']==['000001.XSHE']
    p['conditions']=[];p['applicability']='uncertain'
    assert select(rows,[p]).receipt['selected_codes']==['000001.XSHE']


def test_conflicting_duplicate_targets_and_unsafe_predicates_are_rejected():
    p=preference('mode',{'mode':'A'})
    with pytest.raises(SelectionError):validate_preferences([p,{**p,'id':'p2','direction':'deprioritize'}])
    p['conditions']=[{'field':'__class__','op':'eq','value':'secret','evidence_ref':'x'}]
    with pytest.raises(SelectionError):validate_preferences([p])


def test_sector_mapping_hash_and_ambiguity_are_checked_before_acceptance(tmp_path):
    import hashlib
    import json
    from datetime import datetime, timezone
    from xiaocao.kol.selection_evidence import verify_preference_sources
    path=tmp_path/'map.json'
    value={'schema_version':'kol-sector-map.v1','observed_at':'2026-11-01T00:00:00Z',
        'source_ref':'immutable-catalog','entries':[{'field':'excIndustryCode','code':'T01.ZHBK','name':'sector'}]}
    path.write_text(json.dumps(value))
    p=preference('sector',{'field':'excIndustryCode','code':'T01.ZHBK','name':'sector',
        'mapping_ref':{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}})
    reports={'source-1':{'report_body':'source words'}}
    now=datetime(2026,11,2,tzinfo=timezone.utc)
    verify_preference_sources([p],reports,as_of=now)
    value['entries'].append(dict(value['entries'][0]))
    path.write_text(json.dumps(value))
    with pytest.raises(SelectionError,match='HASH_MISMATCH'):verify_preference_sources([p],reports,as_of=now)
    p['target']['mapping_ref']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(SelectionError,match='AMBIGUOUS'):verify_preference_sources([p],reports,as_of=now)
