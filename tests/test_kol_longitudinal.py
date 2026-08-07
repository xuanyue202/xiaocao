from __future__ import annotations

from pathlib import Path

import pytest

from tests.kol_reviewed_artifact_fixture import (
    materialize_reviewed_artifacts,
)
from xiaocao.kol.initial_import import initial_import_candidates
from xiaocao.kol.longitudinal import (
    MAINTENANCE_AS_OF,
    longitudinal_projection,
    longitudinal_update_candidates,
)
from xiaocao.kol.publication import (
    canonical_bytes,
    manifest_entries,
    record_content_sha256,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def reviewed_artifact_root(tmp_path_factory):
    return materialize_reviewed_artifacts(
        tmp_path_factory.mktemp("reviewed-kol-artifacts")
    )


def _initial(reviewed_artifact_root):
    return initial_import_candidates(
        ROOT,
        reviewed_artifact_root=reviewed_artifact_root,
    )


def _updates(reviewed_artifact_root):
    return longitudinal_update_candidates(
        ROOT,
        reviewed_artifact_root=reviewed_artifact_root,
    )


def _report(candidate):
    return next(
        record for record in candidate["records"] if record["kind"] == "report"
    )


def _candidate_by_author(candidates, author):
    return [
        candidate
        for candidate in candidates
        if _report(candidate)["payload"]["author"] == author
    ]


def test_longitudinal_review_updates_every_report_that_has_real_viewpoints(
    reviewed_artifact_root,
):
    initial = _initial(reviewed_artifact_root)
    updates = _updates(reviewed_artifact_root)

    assert len(updates) == len(initial) - 1
    assert {
        _report(candidate)["record_id"] for candidate in updates
    }.issubset({_report(candidate)["record_id"] for candidate in initial})
    for candidate in updates:
        report = _report(candidate)
        payload = report["payload"]
        assert payload["viewpoint_ids"]
        assert payload["alert_eligible"] is False
        assert (
            candidate["metadata"]["notification_claim_authorized"] is False
        )
        assert (
            candidate["metadata"]["book_kol_us_replay_authorized"] is False
        )
        assert candidate["metadata"]["large_payload_local_bytes"] == 0
        assert report["content_sha256"] == record_content_sha256(report)
        assert candidate["publish_request"]["expected_content_sha256"]
        assert candidate["publish_request"]["expected_manifest_sha256"]
        assert candidate["publish_request"]["records"] == manifest_entries(
            candidate["records"]
        )
        assert len(canonical_bytes(candidate["records"])) < 350 * 1024


def test_lucifer_includes_every_must_surface_view_and_keeps_spacex_current(
    reviewed_artifact_root,
):
    updates = _updates(reviewed_artifact_root)
    lucifer = _candidate_by_author(updates, "路西法")

    assert {
        Path(candidate["metadata"]["source_artifact"]).name
        for candidate in lucifer
    } == {
        "2025-01-09_lucifer_review.json",
        "2025-05-27_lucifer_review.json",
        "lucifer_20260705_claim_gold_v4.json",
    }
    current = next(
        candidate
        for candidate in lucifer
        if candidate["metadata"]["source_artifact"].endswith(
            "lucifer_20260705_claim_gold_v4.json"
        )
    )
    viewpoints = {
        record["payload"]["local_thesis_id"]: record["payload"]
        for record in current["records"]
        if record["kind"] == "viewpoint"
    }
    assert len(viewpoints) == 32
    assert "beite-pullback-watch" in viewpoints
    assert viewpoints["beite-pullback-watch"]["stance"].startswith(
        "作者约40元买入"
    )
    assert "macro-pessimism-information-filter" in viewpoints

    projection = longitudinal_projection(updates)["kols"]["kol-lucifer"]
    spacex = next(
        item
        for item in projection["current_viewpoints"]
        if item["subject"] == "SpaceX"
    )
    assert spacex["status"] == "current"
    assert "SPCX已上市" in spacex["basis"]
    assert projection["current_viewpoints"][0]["subject"] == "SpaceX"
    assert projection["current_viewpoints"][0]["stance"].startswith(
        "7月7日后用总资金5%以下做空"
    )


def test_xiaocao_history_is_archived_while_latest_complete_view_is_current(
    reviewed_artifact_root,
):
    updates = _updates(reviewed_artifact_root)
    projection = longitudinal_projection(updates)["kols"]["kol-xiaocao"]

    assert projection["counts"]["expired"] > 150
    assert projection["counts"]["current"] == 8
    assert projection["counts"]["uncertain"] == 2
    assert projection["relation_count"] >= 30
    assert projection["current_viewpoints"][0]["subject"] == "A股整体环境与风格"
    assert projection["current_viewpoints"][1]["subject"] == "轮动区间交易节奏"
    assert all(
        item["as_of"] == MAINTENANCE_AS_OF
        for item in projection["current_viewpoints"]
    )


def test_lv_later_views_refine_prior_technology_and_leverage_views(
    reviewed_artifact_root,
):
    updates = _updates(reviewed_artifact_root)
    relations = [
        record["payload"]
        for candidate in _candidate_by_author(updates, "吕晓彤")
        for record in candidate["records"]
        if record["kind"] == "viewpoint_relation"
    ]
    projection = longitudinal_projection(updates)["kols"]["kol-lv-xiaotong"]

    assert len(relations) == 2
    assert {row["relation_type"] for row in relations} == {"refines"}
    assert projection["counts"]["current"] == 4
    assert projection["counts"]["uncertain"] == 4
    assert projection["counts"]["expired"] >= 4
    assert projection["counts"]["invalidated"] == 0


def test_every_viewpoint_has_a_latest_explicit_evaluation(
    reviewed_artifact_root,
):
    updates = _updates(reviewed_artifact_root)
    projection = longitudinal_projection(updates)

    assert set(projection["kols"]) == {
        "kol-a-alex",
        "kol-liushao-jujiying",
        "kol-lucifer",
        "kol-lv-xiaotong",
        "kol-xiaocao",
    }
    for kol in projection["kols"].values():
        assert sum(kol["counts"].values()) == len(kol["history"])
        assert all(item["basis"] for item in kol["history"])
        assert all(item["as_of"] == MAINTENANCE_AS_OF for item in kol["history"])


def test_cross_report_relations_follow_publication_dependency_order(
    reviewed_artifact_root,
):
    updates = _updates(reviewed_artifact_root)
    published_viewpoints = set()

    for candidate in updates:
        local_viewpoints = {
            record["record_id"]
            for record in candidate["records"]
            if record["kind"] == "viewpoint"
        }
        referenceable = published_viewpoints | local_viewpoints
        for record in candidate["records"]:
            if record["kind"] != "viewpoint_relation":
                continue
            assert record["payload"]["from_viewpoint_id"] in referenceable
            assert record["payload"]["to_viewpoint_id"] in referenceable
        published_viewpoints |= local_viewpoints
