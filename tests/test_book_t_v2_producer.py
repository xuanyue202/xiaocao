from __future__ import annotations

import hashlib
import json

import pytest

from xiaocao.kol.publication import canonical_sha256
from xiaocao.research.book_t_shadow import evaluate_book_t_shadow, run_book_t_shadow
from xiaocao.research.book_t_v2_producer import (
    BookTV2ProducerError,
    prepare_book_t_v2_shadow_day,
    record_book_t_v2_daily_mark,
    _control_fill_rows,
)


def test_control_uses_proved_gross_when_display_price_is_rounded():
    receipt = {"daily_semantics": {"selection": {"selected_codes": ["601868.XSHG"],
        "actions": [{"code": "601868.XSHG", "kind": "trade", "side": "BUY",
            "price": 2.368, "shares": 4800, "notional": 11367.81, "fee": 1.14}]}}}
    _, fills = _control_fill_rows(receipt, date_iso="2026-09-29", market_hash="a" * 64, catalog={})
    fill = fills[0]
    assert fill["display_fill_price"] == 2.368
    assert fill["fill_price"] * fill["shares"] == pytest.approx(11367.81)
    assert fill["notional"] == 11367.81 and fill["fee"] == 1.14
    receipt["daily_semantics"]["selection"]["actions"][0]["notional"] = 99999
    with pytest.raises(BookTV2ProducerError, match="DISPLAY_PRICE_GROSS_MISMATCH"):
        _control_fill_rows(receipt, date_iso="2026-09-29", market_hash="a" * 64, catalog={})


def _receipt(root, date_iso: str) -> None:
    live = root / "output" / "live"
    live.mkdir(parents=True)
    files = {
        "positions": live / "positions.jsonl",
        "account": live / "paper_account_T.json",
        "trades": live / "paper_trades.jsonl",
    }
    files["positions"].write_text("", encoding="utf-8")
    files["account"].write_text('{"cash": 30000, "initial_capital": 30000, "fee_rate": 0.0001}\n', encoding="utf-8")
    files["trades"].write_text("", encoding="utf-8")
    semantics = {
        "as_of": date_iso,
        "book": "T",
        "selection": {"as_of": date_iso, "selected_codes": [], "actions": []},
        "actions": [],
        "trade_count": 0,
        "skip_count": 0,
        "position_transition_count": 0,
    }
    body = {
        "consumer": "book_t_v1_control",
        "producer": "kronos_screen/scripts/paper_record.py",
        "mode": "trend-only",
        "book": "T",
        "as_of": date_iso,
        "artifact_paths": {
            "positions": "output/live/positions.jsonl",
            "account": "output/live/paper_account_T.json",
            "trades": "output/live/paper_trades.jsonl",
        },
        "artifact_hashes": {
            key: hashlib.sha256(path.read_bytes()).hexdigest()
            for key, path in files.items()
        },
        "daily_semantics": semantics,
        "daily_semantics_sha256": canonical_sha256(semantics),
    }
    (live / f"book_t_v1_control_receipt_{date_iso}.json").write_text(
        json.dumps({**body, "receipt_sha256": canonical_sha256(body)}, sort_keys=True),
        encoding="utf-8",
    )


def test_producer_builds_pending_shadow_input_from_injected_source_adapters(tmp_path) -> None:
    date_iso = "2026-08-21"
    _receipt(tmp_path, date_iso)
    capsule = {
        "publications": [],
        "agent_draft": {
            "themes": [],
            "status": "pending_observation",
            "reason": "no dated structured judgment in rehearsal",
        },
        "market_validation": {},
        "catalog": {
            "version": "catalog-rehearsal",
            "theme_registry": {"version": "registry-rehearsal", "themes": [], "changes": []},
            "blocks": [],
            "etfs": [],
            "stocks": [],
        },
        "portfolio": {
            "as_of": date_iso,
            "account_equity": 30000,
            "account": {"initial_capital": 30000, "cash": 30000},
            "positions": [],
            "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0},
        },
        "market_input": {
            "market_date": date_iso,
            "is_trading_day": True,
            "trading_day_index": 42,
            "quotes": {},
            "liquidity": {},
            "source": "isolated_rehearsal_capsule",
        },
    }

    result = prepare_book_t_v2_shadow_day(
        tmp_path,
        date_iso,
        run_mode="rehearsal",
        capsule=capsule,
    )
    frozen = json.loads(result["input"].read_text(encoding="utf-8"))
    run = run_book_t_shadow(frozen)
    evaluation = evaluate_book_t_shadow([run])

    assert frozen["input_sha256"]
    assert frozen["bindings"]["snapshot"]["snapshot_sha256"]
    assert frozen["bindings"]["universe"]["universe_sha256"]
    assert frozen["bindings"]["selection_plan"]["selection_plan_sha256"]
    assert frozen["bindings"]["portfolio"]["account_equity"] == 30000
    assert frozen["evidence_lifecycle"]["outcome_status"] == "not_applicable"
    assert run["engineering"]["engineering_day_valid"] is True
    assert run["engineering"]["outcome_matured"] is False
    assert evaluation["status"] == "pending_observation"
    assert evaluation["sample"]["real_trading_days"] == 0
    assert evaluation["sample"]["rehearsal_days_excluded"] == 1
    assert "engineering_burn_in" in evaluation["pending_reasons"]

    mark = record_book_t_v2_daily_mark(tmp_path, date_iso, marks=[])
    assert mark["stage_counts"]["daily_mark"] == 1
    assert mark["outcome_matured"] == 0
    from scripts.book_t_shadow import _load_event_frozen_days, _load_lifecycle_events
    from xiaocao.research.book_t_shadow import BookTShadowError
    events = _load_lifecycle_events(tmp_path)
    assert _load_event_frozen_days(events, through=date_iso, root=tmp_path) == [frozen]
    bad = json.loads(json.dumps(frozen))
    bad["assumptions"]["budget_ratio"] = 0.9
    result["input"].write_text(json.dumps(bad))
    with pytest.raises(BookTShadowError, match="input_sha256"):
        _load_event_frozen_days(events, through=date_iso, root=tmp_path)
    result["input"].unlink()
    with pytest.raises(BookTShadowError, match="cannot read JSON"):
        _load_event_frozen_days(events, through=date_iso, root=tmp_path)


def test_producer_rejects_control_artifact_changed_after_receipt(tmp_path) -> None:
    date_iso = "2026-08-21"
    _receipt(tmp_path, date_iso)
    (tmp_path / "output/live/positions.jsonl").write_text("changed\n", encoding="utf-8")

    with pytest.raises(BookTV2ProducerError, match="artifact changed"):
        prepare_book_t_v2_shadow_day(
            tmp_path,
            date_iso,
            run_mode="rehearsal",
            capsule={
                "catalog": {"version": "test", "theme_registry": {}, "blocks": [], "etfs": [], "stocks": []},
                "portfolio": {"account_equity": 30000,
            "account": {"initial_capital": 30000, "cash": 30000}, "positions": []},
                "market_input": {"market_date": date_iso, "is_trading_day": True, "trading_day_index": 1},
                "publications": [],
                "agent_draft": {"themes": []},
            },
        )


def test_multiview_publication_keeps_complete_manifest_per_identity(tmp_path, monkeypatch):
    from xiaocao.research.book_t_v2_producer import _load_publications
    from xiaocao.kol.publication import PublicationLedger
    import copy
    from tests.test_trend_snapshot import _source
    from xiaocao.kol.publication import record_content_sha256, build_publish_request
    original = _source(source_key="multi", kol_id="kol-lv-xiaotong")
    artifact = original["artifact"]
    first = artifact["records"][1]
    second = copy.deepcopy(first)
    second["record_id"] = "v2"
    second["payload"]["viewpoint_id"] = "v2"
    second["content_sha256"] = record_content_sha256(second)
    artifact["records"].append(second)
    evaluation = copy.deepcopy(artifact["records"][2])
    evaluation["record_id"] = "eval-v2"
    evaluation["payload"]["evaluation_id"] = "eval-v2"
    evaluation["payload"]["viewpoint_id"] = "v2"
    evaluation["content_sha256"] = record_content_sha256(evaluation)
    artifact["records"].append(evaluation)
    report = artifact["records"][0]
    report["payload"]["viewpoint_ids"].append("v2")
    report["content_sha256"] = record_content_sha256(report)
    request = build_publish_request(artifact["records"], idempotency_key="multiview", reason="test")
    artifact["publish_request"] = request
    state = {**original, "completed": True}
    state["publish_receipt"]["manifestSha256"] = request["manifest_sha256"]
    monkeypatch.setattr(PublicationLedger, "status_snapshot", lambda self: {"p": state})
    sources, errors = _load_publications(tmp_path)
    assert not errors
    assert {r["viewpoint_id"] for r in sources} == {first["record_id"], "v2"}
    assert all(r["artifact"] == artifact and r["publish_receipt"] == state["publish_receipt"] for r in sources)


def test_control_immutable_snapshot_survives_unrelated_book_write(tmp_path):
    from xiaocao.research.book_t_v2_producer import _load_receipt, _load_portfolio
    day = '2026-10-19'
    _receipt(tmp_path, day)
    receipt_path = tmp_path/f'output/live/book_t_v1_control_receipt_{day}.json'
    receipt = json.loads(receipt_path.read_text())
    snapshots = {}
    for key, relative in receipt['artifact_paths'].items():
        source = tmp_path/relative
        path = tmp_path/'output/live/book_t_v1_control_artifacts'/day/(receipt['artifact_hashes'][key]+source.suffix)
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source.read_bytes())
        snapshots[key] = str(path.relative_to(tmp_path))
    receipt['artifact_snapshots'] = snapshots
    receipt.pop('receipt_sha256');receipt['receipt_sha256'] = canonical_sha256(receipt)
    receipt_path.write_text(json.dumps(receipt))
    (tmp_path/'output/live/positions.jsonl').write_text('{"book":"B","code":"000001.XSHE"}\n')
    assert _load_receipt(tmp_path,day) == receipt
    assert _load_portfolio(tmp_path,receipt)['positions'] == []
    (tmp_path/snapshots['positions']).write_text('corrupt')
    with pytest.raises(BookTV2ProducerError,match='changed after receipt'):
        _load_receipt(tmp_path,day)


def test_same_day_old_control_receipt_cannot_handoff_to_new_run(tmp_path,monkeypatch):
    from xiaocao.research.book_t_v2_producer import _load_receipt
    day='2026-10-19';_receipt(tmp_path,day)
    monkeypatch.setenv('XIAOCAO_DAILY_RUN_ID','new-original')
    monkeypatch.setenv('CODEX_AUTOMATION_ID','xiaocao-daily-morning-execution')
    monkeypatch.setenv('CODEX_THREAD_ID','owner')
    with pytest.raises(BookTV2ProducerError,match='not from this original writer run'):
        _load_receipt(tmp_path,day)


def test_relation_targets_load_only_exact_historical_evidence_and_missing_stays_blocked(tmp_path,monkeypatch):
    from tests.test_trend_snapshot import _source
    from xiaocao.kol.publication import PublicationLedger, build_record, build_publish_request, record_content_sha256
    from xiaocao.research.book_t_v2_producer import _load_publications
    from xiaocao.strategy.trend_snapshot import _normalize_sources, _source_status
    from datetime import datetime,timezone
    old=_source(source_key='history-old',binding_suffix='history-report',kol_id='kol-lv-xiaotong')
    new=_source(source_key='history-new',binding_suffix='history-report',kol_id='kol-lv-xiaotong')
    old['completed']=new['completed']=True
    old['publish_receipt']['serverTime']='2026-08-16T03:00:00Z'
    new['publish_receipt']['serverTime']='2026-08-16T04:00:00Z'
    origin=new['artifact']['records'][1]['record_id'];target=old['artifact']['records'][1]['record_id']
    payload={'relation_id':'relation-history','from_viewpoint_id':origin,'to_viewpoint_id':target,
        'relation_type':'replaces','asserted_at':'2026-08-16T03:59:00Z','reason':'当前观点显式替换旧观点'}
    relation=build_record(kind='viewpoint_relation',record_id_value='relation-history',idempotency_key='history-rel',
        created_at='2026-08-16T03:59:00Z',source_binding=new['artifact']['records'][1]['source_binding'],payload=payload)
    new['artifact']['records'].append(relation)
    request=build_publish_request(new['artifact']['records'],idempotency_key='history-manifest',reason='replacement')
    new['artifact']['publish_request']=request;new['publish_receipt']['manifestSha256']=request['manifest_sha256']
    monkeypatch.setattr(PublicationLedger,'status_snapshot',lambda self:{'old':old,'new':new})
    asof=datetime(2026,8,16,8,tzinfo=timezone.utc)
    sources,errors=_load_publications(tmp_path,as_of=asof)
    assert not errors and len(sources)==2
    historical=next(r for r in sources if r.get('historical_reference_only'))
    assert historical['viewpoint_id']==target
    bound=next(r for r in _normalize_sources(sources,as_of=asof) if r.viewpoint_id==target)
    assert _source_status(bound,as_of=asof,replaced_by={},theme_review_not_after=None)['current'] is False
    monkeypatch.setattr(PublicationLedger,'status_snapshot',lambda self:{'new':new})
    with pytest.raises(BookTV2ProducerError,match='HISTORICAL_RELATION_TARGET_UNPROVED'):
        _load_publications(tmp_path,as_of=asof)
    # Rehydrate the exact published envelope only into historical lookup.
    import copy
    records=copy.deepcopy(old['artifact']['records']);report=records[0]
    extra=copy.deepcopy(records[1]);extra['record_id']='uncited-old-view';extra['payload']['viewpoint_id']='uncited-old-view'
    extra['content_sha256']=record_content_sha256(extra);records.append(extra)
    report['payload']['viewpoint_ids'].append('uncited-old-view');report['content_sha256']=record_content_sha256(report)
    request=build_publish_request(records,idempotency_key='cache-proof',reason='fixture')
    report.update(state='published',manifest=request['records'],manifest_sha256=request['manifest_sha256'],updated_at='2026-08-16T03:00:00Z')
    for record in records[1:]:record['state']='immutable'
    capsule={'source':'lianghui.get_kol_record','observed_at':'2026-08-16T05:00:00Z','report':report,'records':records}
    raw=json.dumps(capsule,sort_keys=True).encode();path=tmp_path/'output/live/kol_daily/publication_readbacks'/(hashlib.sha256(raw).hexdigest()+'.json')
    path.parent.mkdir(parents=True);path.write_bytes(raw)
    repaired,_=_load_publications(tmp_path,as_of=asof)
    assert {r['viewpoint_id'] for r in repaired}=={origin,target}
    assert next(r for r in repaired if r['viewpoint_id']==target)['historical_reference_only'] is True
