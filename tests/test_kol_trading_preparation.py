
import pytest

from xiaocao.kol.publication import canonical_sha256
from xiaocao.kol.trading_preparation import preparation_status, publish_preparation


def inputs():
    context = {"reports": [{"report_id": "a"}],
               "report_index": [{"report_id": "a", "content_sha256": "hash"}],
               "coverage": {"registered_longitudinal_complete": False}}
    context["context_sha256"] = canonical_sha256(context)
    notes = {"schema_version": "kol-source-preparation.v1", "authority": 0,
             "context_sha256": context["context_sha256"], "analyst_agent_id": "analyst",
             "coverage_limits": "Historical sources incomplete; current facts still required.",
             "sources": [{"report_id": "a", "analysis": "Claim", "conditions": "Conditional",
                          "counterevidence": "Disagreement", "time_scope": "Next session"}]}
    review = {"notes_sha256": canonical_sha256(notes), "status": "approved",
              "reviewer_agent_id": "parent", "reviewed_at": "2026-09-14T01:00:00Z",
              "source_fidelity": True, "conditions_preserved": True, "counterevidence_checked": True}
    return context, notes, review


def test_source_pack_reuses_unchanged_evidence_but_never_grants_current_authority(tmp_path):
    context, notes, review = inputs()
    first = publish_preparation(tmp_path, context, notes, review)
    assert publish_preparation(tmp_path, context, notes, review) == first
    status = preparation_status(tmp_path, context)
    assert status["status"] == "prepared"
    assert status["authority"] == 0 and status["current_applicability_review_required"]
    assert len(list((tmp_path / "output/live/kol_policy/preparations").glob("*.json"))) == 1
    context["report_index"][0]["content_sha256"] = "changed"
    assert preparation_status(tmp_path, context)["status"] == "source_analysis_required"


@pytest.mark.parametrize("change", ["self_review", "missing_source", "changed_notes", "trading_authority"])
def test_invalid_handoffs_cannot_publish(tmp_path, change):
    context, notes, review = inputs()
    if change == "self_review": review["reviewer_agent_id"] = "analyst"
    if change == "missing_source":
        notes["sources"] = []
        review["notes_sha256"] = canonical_sha256(notes)
    if change == "changed_notes": notes["sources"][0]["conditions"] = "Unconditional"
    if change == "trading_authority": notes["authority"] = 1
    with pytest.raises(ValueError):
        publish_preparation(tmp_path, context, notes, review)


def test_changed_evaluation_invalidates_prepared_analysis(tmp_path):
    context, notes, review = inputs()
    publish_preparation(tmp_path, context, notes, review)
    context["evaluations"] = [{"record_id": "evaluation", "content_sha256": "new"}]
    assert preparation_status(tmp_path, context)["status"] == "source_analysis_required"


def test_missing_cached_history_requires_revalidation_not_reanalysis(tmp_path):
    from copy import deepcopy
    context, notes, review = inputs()
    context["report_index"].append({"report_id": "history", "content_sha256": "old"})
    context["evaluations"] = [{"record_id": "old-eval", "content_sha256": "eval", "report_id": "history"}]
    context["context_sha256"] = canonical_sha256({k: v for k, v in context.items() if k != "context_sha256"})
    notes["context_sha256"] = context["context_sha256"]
    review["notes_sha256"] = canonical_sha256(notes)
    packet = publish_preparation(tmp_path, context, notes, review)
    expired = deepcopy(context)
    expired["report_index"][1]["longitudinal_loaded"] = False
    expired["report_index"][1]["content_sha256"] = None
    expired["evaluations"] = []
    status = preparation_status(tmp_path, expired)
    assert status["status"] == "source_revalidation_required"
    assert status["reusable_path"] == packet["path"]
    assert status["current_applicability_review_required"] is True
