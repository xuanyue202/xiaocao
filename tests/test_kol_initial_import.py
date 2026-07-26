from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.kol_reviewed_artifact_fixture import (
    materialize_reviewed_artifacts,
)
from xiaocao.kol.initial_import import (
    ADVERTISEMENT_TERMS,
    initial_import_candidates,
)
from xiaocao.kol.publication import PublicationLedger, record_content_sha256


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def reviewed_artifact_root(tmp_path_factory):
    return materialize_reviewed_artifacts(
        tmp_path_factory.mktemp("reviewed-kol-artifacts")
    )


def _candidates(reviewed_artifact_root):
    return initial_import_candidates(
        ROOT,
        reviewed_artifact_root=reviewed_artifact_root,
    )


def _expected_candidate_count() -> int:
    reviewed_distills = [
        path
        for path in (ROOT / "reference/experience/distilled").glob("*.json")
        if path.name != "2026-07-05_lucifer_review.json"
    ]
    return len(reviewed_distills) + 4


def _report(candidate):
    return next(
        record for record in candidate["records"] if record["kind"] == "report"
    )


def test_initial_import_has_one_safe_report_per_reviewed_publication_event(
    reviewed_artifact_root,
):
    candidates = _candidates(reviewed_artifact_root)

    assert len(candidates) == _expected_candidate_count()
    assert len({row["publication_key"] for row in candidates}) == len(
        candidates
    )
    for candidate in candidates:
        report = _report(candidate)
        payload = report["payload"]
        assert report["content_sha256"] == record_content_sha256(report)
        assert payload["report_kind"] == "publication_event"
        assert payload["summary"].strip()
        assert payload["alert_eligible"] is False
        assert payload["alert_reason"] == "historical_initialization_no_alert"
        assert payload["reader_insight"]["status"] == "useful"
        assert candidate["metadata"]["notification_claim_authorized"] is False
        assert candidate["metadata"]["book_kol_us_replay_authorized"] is False
        assert candidate["metadata"]["large_payload_local_bytes"] == 0
        encoded = json.dumps(candidate["records"], ensure_ascii=False)
        assert "/Users/" not in encoded
        assert "http://" not in encoded
        assert "https://" not in encoded
        assert "raw_transcript" not in encoded
        assert "familyId" not in encoded
        reader_text = "\n".join(
            (payload["title"], payload["summary"], payload["report_body"])
        )
        assert all(term not in reader_text for term in ADVERTISEMENT_TERMS)
        hashes = [
            report["source_binding"]["evidence_sha256"],
            *[
                part["evidence_sha256"]
                for part in payload.get("source_parts", [])
                if "evidence_sha256" in part
            ],
        ]
        assert all(re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes)


def test_superseded_lucifer_fragments_are_not_imported_and_spacex_is_prominent(
    reviewed_artifact_root,
):
    candidates = _candidates(reviewed_artifact_root)
    lucifer = [
        row
        for row in candidates
        if _report(row)["payload"]["kol_id"] == "kol-lucifer"
    ]

    assert len(lucifer) == 1
    payload = _report(lucifer[0])["payload"]
    assert len(payload["source_parts"]) == 3
    assert "SpaceX" in payload["report_body"]
    assert "7月7日后" in payload["report_body"]
    assert "5%以下做空" in payload["report_body"]
    assert all("sha256" not in part for part in payload["source_parts"])
    assert payload["viewpoint_ids"]


def test_group_chat_image_does_not_create_fake_lv_viewpoints(
    reviewed_artifact_root,
):
    candidates = _candidates(reviewed_artifact_root)
    image = next(
        row
        for row in candidates
        if row["metadata"]["source_artifact"].endswith(
            "lv_20260723_image_claim_gold_v1.json"
        )
    )

    assert _report(image)["payload"]["viewpoint_ids"] == []
    assert "不能归属于吕晓彤" in _report(image)["payload"]["report_body"]


def test_longitudinal_currentness_is_explicit_and_conservative(
    reviewed_artifact_root,
):
    candidates = _candidates(reviewed_artifact_root)
    evaluations = [
        record["payload"]
        for candidate in candidates
        for record in candidate["records"]
        if record["kind"] == "viewpoint_evaluation"
    ]

    assert evaluations
    assert {row["status"] for row in evaluations} == {"current", "uncertain"}
    assert any(
        row["status"] == "current"
        and "杠杆工具" in row["basis"]
        for row in evaluations
    )
    assert all(row["as_of"] and row["evaluated_at"] for row in evaluations)
    assert all(row["basis"] for row in evaluations)


def test_prepare_is_offline_and_records_zero_large_payload_bytes(
    tmp_path,
    reviewed_artifact_root,
):
    candidates = _candidates(reviewed_artifact_root)
    ledger = PublicationLedger(tmp_path)

    for candidate in candidates:
        ledger.prepare(
            candidate["publication_key"],
            candidate["records"],
            candidate["publish_request"],
            metadata=candidate["metadata"],
        )

    assert len(
        [row for row in ledger.events() if row["event"] == "publication_prepared"]
    ) == len(candidates)
    assert all(
        row.get("large_payload_local_bytes", 0) == 0
        for row in ledger.events()
    )
