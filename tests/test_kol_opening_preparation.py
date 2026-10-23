"""Pure source preparation/delta tests: no APP, market or policy writes."""
import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from xiaocao.kol import opening_preparation as p
from xiaocao.runner_recovery import _hash

NOW = datetime.fromisoformat("2026-10-23T09:10:00+08:00")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))
    return path


def projection_file(tmp_path, rows, evaluations=None, relations=None):
    value = {"as_of": NOW.isoformat(), "authority": 0, "quality": {"status": "ready"}, "active_viewpoints": rows,
             "latest_evaluations": evaluations or [], "relations": relations or [], "related_history": []}
    value["source_fingerprint"] = p.canonical_sha256(value)
    value["projection_sha256"] = p.canonical_sha256(value)
    path = save(tmp_path / (value["projection_sha256"] + ".json"), value)
    return {"projection_path": str(path), "projection_sha256": value["projection_sha256"]}


def implication(identifier, source, kind, scope):
    return {"id": identifier, "viewpoint_ids": [source], "kind": kind, "scope": scope,
            **{k: "explicit source/analyst condition" for k in ("source_wording", "interpretation", "conditions",
               "invalidations", "counterevidence", "proposed_effect")}}


@pytest.fixture
def case(tmp_path):
    for rule in p.RULES:
        path = tmp_path / rule
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("rules")
    rows = [{"record_id": str(i), "report_id": "r", "report_content_sha256": "a" * 64} for i in range(4)]
    summary = projection_file(tmp_path, rows)
    binding = {"trade_date": "2026-10-23", "owner_thread_id": "owner", "automation_id": "paper-owner"}
    inputs = p.input_payload(summary, binding=binding, repo_root=tmp_path)
    path = save(tmp_path / "input.json", inputs)
    draft = p.draft_template(path)
    draft.update(worker_id="worker", prepared_at=NOW.isoformat(), valid_until=(NOW+timedelta(hours=2)).isoformat(),
                 implications=[implication("posture", "0", "portfolio_posture", {"kind": "all", "values": []}),
                    implication("mode", "1", "mode_focus", {"kind": "modes", "values": ["N字低吸"]}),
                    implication("counter", "2", "counterevidence", {"kind": "all", "values": []})])
    for row, ids in zip(draft["coverage"], (["posture"], ["mode"], ["counter"], [])):
        row.update(implication_ids=ids, disposition="implication" if ids else "background", reason="reviewed explicitly")
    context = {"authority": 0, "as_of": NOW.isoformat(), "reports": [{"report_id": "r", "content_sha256": "a"*64,
        "report_body": "source", "report_body_sha256": hashlib.sha256(b"source").hexdigest()}]}
    context["context_sha256"] = p.canonical_sha256(context)
    dispatch = {"worker_id": "worker", "accepted": True, "input_sha256": _hash(inputs), "binding": binding,
        "dispatched_at": (NOW-timedelta(minutes=2)).isoformat(), "tool_arguments": {
        "model": "gpt-6-sol", "reasoning_effort": "xhigh", "fork_turns": "none"}, "tool_result": {"task_name": "worker"}}
    review = {"accepted": True, "draft_sha256": p.canonical_sha256(draft), "context_sha256": context["context_sha256"],
        "dispatch_sha256": p.canonical_sha256(dispatch),
        "reviewer_id": "parent", "reviewed_at": NOW.isoformat(), "all_viewpoints_covered": True,
        "source_fidelity_checked": True, "conditions_and_counterevidence_checked": True}
    return dict(path=path, inputs=inputs, draft=draft, review=review, context=context, dispatch=dispatch, rows=rows, root=tmp_path)


def accept(case):
    return p.accept_preparation(case["path"], case["draft"], case["review"], case["dispatch"], case["context"], now=NOW)


def seal(case):
    return save(case["root"] / "prepared.json", accept(case))


def request():
    return {"trade_date": "2026-10-23", "requested_at": "2026-10-23T09:25:30+08:00",
        "review_wait_until": "2026-10-23T09:27:00+08:00", "freeze_sha256": "b"*64,
        "strategy_sha": "c"*40, "candidates": [{"code": "002172", "mode": "N字低吸"}],
        "account_risk": {"deploy_factor": 1}}


def packet(case, *, facts=None, when=None):
    return p.opening_packet(seal(case), case["path"], facts or request(), now=when or NOW.replace(minute=26))


def test_complete_preparation_preserves_coverage_and_relevant_global_risks(case):
    facts = request()
    facts["candidates"][0]["mode"] = "other"
    result = packet(case, facts=facts)
    assert result["authority"] == 0
    assert [i["id"] for i in result["implications"]] == ["posture", "counter"]
    assert result["coverage"] == {"prepared_count": 4, "current_count": 4, "unchanged_count": 4}
    assert result["delta"]["units"] == {}
    assert result["request_facts_sha256"] == p.canonical_sha256(facts)
    assert [i["id"] for i in packet(case)["implications"]] == ["posture", "mode", "counter"]


@pytest.mark.parametrize("damage", ["omitted", "duplicate", "scope", "self_review", "draft_hash", "dispatch", "context", "expired", "future"])
def test_preparation_rejects_unproved_work(case, damage):
    if damage == "omitted": case["draft"]["coverage"].pop()
    elif damage == "duplicate": case["draft"]["coverage"].append(case["draft"]["coverage"][0])
    elif damage == "scope": case["draft"]["implications"][0]["scope"] = {"kind": "modes", "values": ["x"]}
    elif damage == "self_review": case["review"]["reviewer_id"] = "worker"
    elif damage == "draft_hash": case["draft"]["implications"][0]["conditions"] = "altered"
    elif damage == "dispatch": case["dispatch"]["tool_result"]["task_name"] = "other"
    elif damage == "context": case["context"]["reports"] = []
    elif damage == "expired": case["draft"]["valid_until"] = NOW.isoformat()
    elif damage == "future": case["draft"]["prepared_at"] = (NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError): accept(case)


def test_delta_invalidates_changed_evaluation_and_removed_sources(case):
    prepared = seal(case)
    rows = copy.deepcopy(case["rows"])
    rows.pop(1)
    rows.append({"record_id": "new", "report_id": "new-report", "report_content_sha256": "f"*64})
    summary = projection_file(case["root"], rows, [{"evaluation": {"viewpoint_id": "0", "status": "changed"}}])
    current = p.input_payload(summary, binding=case["inputs"]["binding"], repo_root=case["root"])
    path = save(case["root"] / "fresh.json", current)
    result = p.opening_packet(prepared, path, request(), now=NOW.replace(minute=26))
    assert result["delta"]["changed"] == ["0"]
    assert result["delta"]["removed"] == ["1"]
    assert result["delta"]["added"] == ["new"]
    assert {i["id"] for i in result["invalidated_implications"]} == {"posture", "mode"}
    assert [i["id"] for i in result["implications"]] == ["counter"]
    assert set(result["delta"]["units"]) == {"0", "new"}


def test_relation_change_cannot_reuse_old_interpretation(case):
    prepared = seal(case)
    summary = projection_file(case["root"], case["rows"], relations=[{"new": "counterevidence"}])
    current = p.input_payload(summary, binding=case["inputs"]["binding"], repo_root=case["root"])
    result = p.opening_packet(prepared, save(case["root"] / "fresh.json", current), request(), now=NOW.replace(minute=26))
    assert not result["implications"]
    assert len(result["delta"]["changed"]) == 4


@pytest.mark.parametrize("damage", ["rule", "projection", "sealed", "owner", "cutoff", "late", "expiry"])
def test_packet_rechecks_original_evidence_and_deadline(case, damage):
    prepared = seal(case)
    facts = request()
    when = NOW.replace(minute=26)
    if damage == "rule": (case["root"] / p.RULES[0]).write_text("changed rule")
    elif damage == "projection":
        path = Path(case["inputs"]["projection"]["projection_path"])
        value = json.loads(path.read_text()); value["active_viewpoints"].pop(); save(path, value)
    elif damage == "sealed":
        value = json.loads(prepared.read_text()); value["draft"]["implications"] = []; save(prepared, value)
    elif damage == "owner":
        value = copy.deepcopy(case["inputs"]); value["binding"]["owner_thread_id"] = "other"
        case["path"] = save(case["root"] / "other.json", value)
    elif damage == "cutoff": facts["review_wait_until"] = "2026-10-23T09:28:00+08:00"
    elif damage == "late": when = NOW.replace(minute=27)
    elif damage == "expiry": when = NOW.replace(hour=12)
    with pytest.raises(ValueError): p.opening_packet(prepared, case["path"], facts, now=when)


def test_optional_missing_scores_normalize_without_changing_execution_facts(case):
    facts = request()
    facts["candidates"][0].update(k_score=float("nan"), p_score=float("nan"), market_price=4.18)
    normalized = p.normalized_review_facts(facts)
    assert normalized["candidates"][0]["k_score"] is None
    assert normalized["candidates"][0]["market_price"] == 4.18
    assert packet(case, facts=facts)["request_facts_sha256"] == p.canonical_sha256(normalized)
    facts["candidates"][0]["market_price"] = float("nan")
    with pytest.raises(ValueError): packet(case, facts=facts)


def test_parent_review_cannot_be_reused_for_another_dispatch(case):
    case["dispatch"]["tool_arguments"]["message"] = "different accepted task"
    with pytest.raises(ValueError, match="INDEPENDENT_REVIEW"):
        accept(case)


def test_related_history_evaluation_change_is_complete_delta(case):
    prepared = seal(case)
    summary = projection_file(case["root"], case["rows"])
    projection = json.loads(Path(summary["projection_path"]).read_text())
    projection["related_history"] = [{"record_id": "history"}]
    evaluation = {"evaluation": {"viewpoint_id": "history", "uncertainties": ["changed counterevidence"]}}
    projection["latest_evaluations"] = [evaluation]
    projection["projection_sha256"] = p.canonical_sha256({k:v for k,v in projection.items() if k != "projection_sha256"})
    summary = {"projection_path": str(save(case["root"] / "new-history.json", projection)),
               "projection_sha256": projection["projection_sha256"]}
    current = p.input_payload(summary, binding=case["inputs"]["binding"], repo_root=case["root"])
    result = p.opening_packet(prepared, save(case["root"] / "fresh.json", current), request(), now=NOW.replace(minute=26))
    assert not result["implications"]
    assert result["delta"]["relation_history"]["latest_evaluations"] == [evaluation]
