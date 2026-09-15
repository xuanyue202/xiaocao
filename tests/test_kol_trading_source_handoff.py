import copy
import json
from pathlib import Path

import pytest

from xiaocao.kol.publication import canonical_sha256
from xiaocao.kol.trading_preparation import publish_preparation
from xiaocao.kol.trading_source_handoff import complete_source_handoff


def fixture(root):
    state = {"completed": True, "publication_key": "source-a", "publish_receipt": {"receipt": "ok"},
             "artifact": {"records": [{"kind": "report", "record_id": "a", "content_sha256": "body"}],
                          "publish_request": {"manifest_sha256": "manifest"}}}
    context = {"reports": [{"report_id": "a", "content_sha256": "body", "manifest_sha256": "manifest"}],
               "report_index": [{"report_id": "a", "content_sha256": "body"}],
               "coverage": {"registered_longitudinal_complete": True}}
    context["context_sha256"] = canonical_sha256(context)
    context_path = root / "context.json"
    context_path.write_text(json.dumps(context))
    notes = {"schema_version": "kol-source-preparation.v1", "authority": 0,
             "context_sha256": context["context_sha256"], "analyst_agent_id": "analyst",
             "coverage_limits": "Current facts still require review.",
             "sources": [{"report_id": "a", "analysis": "Claim", "conditions": "Conditional",
                          "counterevidence": "Disagreement", "time_scope": "Next session"}]}
    review = {"notes_sha256": canonical_sha256(notes), "status": "approved",
              "reviewer_agent_id": "parent", "reviewed_at": "2026-09-15T01:00:00Z",
              "source_fidelity": True, "conditions_preserved": True, "counterevidence_checked": True}
    packet = publish_preparation(root, context, notes, review)
    response = {"context_path": str(context_path), "preparation_path": packet["path"]}
    return state, context, response


def test_handoff_retries_only_pending_review_and_reuses_exact_receipt(tmp_path):
    state, context, response = fixture(tmp_path)
    calls = []
    def build(**kwargs):
        calls.append("read")
        assert kwargs["read_report_ids"] == ["a"]
        return context
    kwargs = dict(build_context=build, summarize_context=lambda *_a, **_k: {},
                  read_response=lambda request: None)
    with pytest.raises(ValueError, match="response_required"):
        complete_source_handoff(tmp_path, state, **kwargs)
    assert len(list((tmp_path / "output/live/kol_policy/handoffs").glob("*.request.json"))) == 1
    assert not list((tmp_path / "output/live/kol_policy/handoffs").glob("*.receipt.json"))
    kwargs["read_response"] = lambda request: response
    first = complete_source_handoff(tmp_path, state, **kwargs)
    calls.clear()
    kwargs["read_response"] = lambda *_: pytest.fail("completed handoff asked for another review")
    assert complete_source_handoff(tmp_path, state, **kwargs) == first
    assert calls == []
    assert first["authority"] == 0


@pytest.mark.parametrize("change", ["wrong_report", "corrupt_packet", "wrong_manifest", "wrong_receipt"])
def test_handoff_rejects_unbound_response_or_corrupt_readback(tmp_path, change):
    state, context, response = fixture(tmp_path)
    kwargs = dict(build_context=lambda **_: context, summarize_context=lambda *_a, **_k: {},
                  read_response=lambda _: response)
    if change == "wrong_receipt":
        complete_source_handoff(tmp_path, state, **kwargs)
        p = next((tmp_path / "output/live/kol_policy/handoffs").glob("*.receipt.json"))
        d = json.loads(p.read_text()); d["packet_sha256"] = "changed"; p.write_text(json.dumps(d))
    elif change == "corrupt_packet":
        p = Path(response["preparation_path"])
        d = json.loads(p.read_text()); d["notes"]["sources"][0]["analysis"] = "changed"; p.write_text(json.dumps(d))
    else:
        state = copy.deepcopy(state)
        if change == "wrong_report": state["artifact"]["records"][0]["content_sha256"] = "different"
        else: state["artifact"]["publish_request"]["manifest_sha256"] = "different"
    with pytest.raises(ValueError):
        complete_source_handoff(tmp_path, state, **kwargs)


def test_real_context_reader_publish_and_handoff_receipt(tmp_path):
    from tests.test_kol_trading_context import publication, register, Reader, Clock
    from xiaocao.kol.trading_context import build_trading_context, summarize_context
    items = [publication()]
    ledger = register(tmp_path, items)
    ledger_before = ledger.read_bytes()
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    state = {"completed": True, "publication_key": events[0]["publication_key"],
             "artifact": events[0]["artifact"], "publish_receipt": events[1]["receipt"]}
    reader, clock = Reader(items), Clock()
    def respond(request):
        context_path = Path(request["context"]["context_path"])
        context = json.loads(context_path.read_text())
        notes = {"schema_version": "kol-source-preparation.v1", "authority": 0,
                 "context_sha256": context["context_sha256"], "analyst_agent_id": "fixture-analyst",
                 "coverage_limits": "Fixture only, no current applicability.",
                 "sources": [{"report_id": r["report_id"], "analysis": "Claim",
                              "conditions": "Conditional", "counterevidence": "Counter",
                              "time_scope": "Dated source"} for r in context["reports"]]}
        review = {"notes_sha256": canonical_sha256(notes), "status": "approved",
                  "reviewer_agent_id": "fixture-parent", "reviewed_at": clock().isoformat(),
                  "source_fidelity": True, "conditions_preserved": True, "counterevidence_checked": True}
        packet = publish_preparation(tmp_path, context, notes, review)
        return {"context_path": str(context_path), "preparation_path": packet["path"]}
    receipt = complete_source_handoff(
        tmp_path, state, build_context=lambda **kwargs: build_trading_context(client=reader, clock=clock, **kwargs),
        summarize_context=summarize_context, read_response=respond,
    )
    assert receipt["status"] == "prepared" and receipt["registered_longitudinal_complete"]
    assert all(name == "get_kol_record" for name, _ in reader.calls)
    assert ledger.read_bytes() == ledger_before


def test_pending_handoff_survives_interruption_without_discovering_history(tmp_path):
    from xiaocao.kol.trading_source_handoff import pending_source_handoffs
    state, context, response = fixture(tmp_path)
    assert pending_source_handoffs(tmp_path) == []
    kwargs = dict(build_context=lambda **_: context, summarize_context=lambda *_a, **_k: {},
                  read_response=lambda _: None)
    with pytest.raises(ValueError):
        complete_source_handoff(tmp_path, state, **kwargs)
    assert pending_source_handoffs(tmp_path) == [state["publication_key"]]
    kwargs["read_response"] = lambda _: response
    complete_source_handoff(tmp_path, state, **kwargs)
    assert pending_source_handoffs(tmp_path) == []


def test_already_prepared_semantics_need_no_second_analyst(tmp_path):
    state, context, _ = fixture(tmp_path)
    cached = tmp_path / 'output/live/kol_policy/context' / (context['context_sha256'] + '.context.json')
    cached.parent.mkdir(parents=True)
    cached.write_text(json.dumps(context))
    result = complete_source_handoff(
        tmp_path, state, build_context=lambda **_: context,
        summarize_context=lambda *_a, **_k: {},
        read_response=lambda _: pytest.fail('unchanged reviewed source was reanalyzed'),
    )
    assert result['status'] == 'prepared'
