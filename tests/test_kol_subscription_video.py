from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.kol_claim_fixture import attach_claim_contract
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.netdisk_enrichment import NetdiskEnrichmentService
from xiaocao.kol.subscription_video import (
    _CREATE_FOLDER_SCRIPT,
    _PRIVATE_SEARCH_SCRIPT,
    _TRANSFER_OUTCOME_SCRIPT,
    _TRANSFER_SCRIPT,
    LUCIFER_SOURCE,
    LV_AUTHOR,
    LV_DESTINATION_DIRECTORY,
    LV_SOURCE,
    REQUIRED_COVERAGE_ROWS,
    SubscriptionVideoService,
)


NOW = datetime.fromisoformat("2026-07-25T16:00:00+08:00")


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "xiaocao.yaml"
    path.write_text(
        """
kol_intelligence:
  lv_xiaotong:
    subscription_share_url: https://pan.baidu.com/s/private-ticket05
    subscription_share_code: a1b2
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _row(
    provider_id: str,
    path: str,
    *,
    size: int,
    modified_at: int,
    is_dir: bool = False,
) -> dict:
    return {
        "provider_file_id": provider_id,
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "is_dir": is_dir,
        "size": size,
        "modified_at": modified_at,
    }


def _service(tmp_path: Path, **kwargs) -> SubscriptionVideoService:
    return SubscriptionVideoService(
        tmp_path / "out",
        config_path=_config(tmp_path),
        now=lambda: NOW,
        opencli_command=("opencli",),
        **kwargs,
    )


def _source_rows() -> tuple[list[dict], list[dict]]:
    lv = [
        _row(
            "lv-old",
            "/share/2026年7月/7月19日.mp4",
            size=8_157_346,
            modified_at=1_784_482_071,
        ),
        _row(
            "lv-latest",
            "/share/2026年7月/7月20日.mp4",
            size=3_682_235_122,
            modified_at=1_784_560_843,
        ),
        _row(
            "lv-image",
            "/share/2026年7月/17.png",
            size=1_377_484,
            modified_at=1_784_821_267,
        ),
    ]
    lucifer = [
        _row(
            "lucifer-a",
            "/课程/路西法全套/鹿7.5/7月5日（一）.mp4",
            size=759_800_380,
            modified_at=1_784_456_551,
        ),
        _row(
            "lucifer-b",
            "/课程/路西法全套/鹿7.5/7月5日（二）.mp4",
            size=578_859_389,
            modified_at=1_784_456_551,
        ),
        _row(
            "lucifer-c",
            "/课程/路西法全套/鹿7.5/7月5日（三）.mp4",
            size=744_292_790,
            modified_at=1_784_456_551,
        ),
        _row(
            "lucifer-doc",
            "/课程/路西法全套/鹿7.5/7月5日（三）.doc",
            size=31_226,
            modified_at=1_784_456_658,
        ),
    ]
    return lv, lucifer


def test_bootstrap_selects_one_real_logical_content_unit_per_source(tmp_path):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()

    discovered = service.observe(lv, lucifer)

    assert [row["path"] for row in discovered["updates"]] == [
        "/share/2026年7月/7月20日.mp4",
        "/课程/路西法全套/鹿7.5/7月5日",
    ]
    pending = service.pending_items()
    assert {row["source"] for row in pending} == {
        LV_SOURCE,
        LUCIFER_SOURCE,
    }
    lucifer_episode = next(
        row for row in pending if row["source"] == LUCIFER_SOURCE
    )
    assert lucifer_episode["is_episode"] is True
    assert [part["part_index"] for part in lucifer_episode["parts"]] == [1, 2, 3]
    status = service.status()
    assert status["bootstrap"]["policy"] == (
        "latest_real_logical_content_per_source"
    )
    assert status["bootstrap"]["historical_logical_content_baseline_count"] == 1
    assert status["source_counts"] == {LV_SOURCE: 3, LUCIFER_SOURCE: 4}
    durable = (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    assert "private-ticket05" not in durable
    assert "a1b2" not in durable
    assert "lv-latest" not in durable


def test_same_scan_is_quiet_and_only_changed_version_becomes_new_work(tmp_path):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()
    service.observe(lv, lucifer)
    manifest = service._load_manifest()
    for item in manifest["items"].values():
        if item.get("work_eligible"):
            item["completed_version_key"] = item["version_key"]
            item["work_eligible"] = False
    for episode in manifest["episodes"].values():
        if episode.get("work_eligible"):
            episode["completed_version_key"] = episode["version_key"]
            episode["work_eligible"] = False
    from xiaocao.kol.subscription_video import _atomic_write_json

    _atomic_write_json(service.manifest_path, manifest)

    assert service.observe(lv, lucifer) is None
    assert service.pending_items() == []

    changed = [
        {**row, "modified_at": row["modified_at"] + 60}
        if row["provider_file_id"] == "lv-latest"
        else row
        for row in lv
    ]
    discovered = service.observe(changed, lucifer)

    assert len(discovered["updates"]) == 1
    assert discovered["updates"][0]["path"].endswith("/7月20日.mp4")
    assert len(service.pending_items()) == 1


def test_new_deep_video_is_detected_when_parent_directory_mtime_is_unchanged(
    tmp_path,
):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()
    parent = _row(
        "lv-july-directory",
        "/share/2026年7月",
        size=0,
        modified_at=1_784_000_000,
        is_dir=True,
    )
    service.observe([parent, *lv], lucifer)
    manifest = service._load_manifest()
    for item in manifest["items"].values():
        item["work_eligible"] = False
        if item["media_type"] == "video":
            item["completed_version_key"] = item["version_key"]
    for episode in manifest["episodes"].values():
        episode["work_eligible"] = False
        episode["completed_version_key"] = episode["version_key"]
    from xiaocao.kol.subscription_video import _atomic_write_json

    _atomic_write_json(service.manifest_path, manifest)
    new_video = _row(
        "lv-new-deep-video",
        "/share/2026年7月/7月29日/7月29日.mp4",
        size=3_000_000_000,
        modified_at=1_785_315_600,
    )

    discovered = service.observe(
        [parent, *lv, new_video],
        lucifer,
    )

    assert [row["path"] for row in discovered["updates"]] == [
        "/share/2026年7月/7月29日/7月29日.mp4"
    ]
    assert next(
        row
        for row in service.pending_items()
        if row["identity"] == discovered["updates"][0]["identity"]
    )["work_eligible"] is True


def test_episode_analysis_request_binds_all_component_evidence(tmp_path):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()
    service.observe(lv, lucifer)
    episode = next(
        item
        for item in service.pending_items()
        if item["source"] == LUCIFER_SOURCE
    )
    component_states = []
    for part in episode["parts"]:
        transcript = tmp_path / f"{part['part_index']}.txt"
        transcript.write_text(
            f"第{part['part_index']}段完整文稿。" * 200,
            encoding="utf-8",
        )
        component_states.append(
            {
                "job_id": f"part-{part['part_index']}",
                "status": "verified",
                "transcript_path": str(transcript),
                "transcript_sha256": __import__("hashlib").sha256(
                    transcript.read_bytes()
                ).hexdigest(),
                "large_payload_local_bytes": 0,
                "netdisk_directory": "/课程/路西法全套/鹿7.5",
            }
        )

    state = service._prepare_episode_evidence(episode, component_states)
    request = service._analysis_request(episode, state)

    assert request["title"] == "7月5日"
    assert request["author_profile"] == {
        "gender": "male",
        "subject_pronoun": "他",
        "possessive_pronoun": "他的",
        "generation_rule": "提及作者本人时只用“他/他的”，不得使用“她/她的”。",
    }
    assert request["source_path"] == "/课程/路西法全套/鹿7.5/7月5日"
    assert request["logical_content"]["part_count"] == 3
    assert [part["part_index"] for part in request["component_evidence"]] == [
        1,
        2,
        3,
    ]
    merged = Path(request["evidence_path"]).read_text(encoding="utf-8")
    assert merged.index("第1段完整文稿") < merged.index("第2段完整文稿")
    assert merged.index("第2段完整文稿") < merged.index("第3段完整文稿")


def test_episode_advances_all_ready_parts_when_one_part_waits(tmp_path):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()
    service.observe(lv, lucifer)
    episode = next(
        item
        for item in service.pending_items()
        if item["source"] == LUCIFER_SOURCE
    )
    episode["next_poll_not_before"] = "2026-07-25T15:59:59+08:00"
    visited = []

    def advance(part, **_kwargs):
        visited.append(part["part_index"])
        if part["part_index"] == 1:
            return {
                "status": "transcript_requested",
                "next_poll_not_before": "2026-07-25T16:05:00+08:00",
            }
        return {
            "status": "verified",
            "transcript_path": str(tmp_path / f"{part['part_index']}.txt"),
            "transcript_sha256": "a" * 64,
            "large_payload_local_bytes": 0,
        }

    service._advance_part_to_verified = advance

    state = service.advance_item(
        episode,
        lv_session="lv",
        private_session="private",
        enrichment_session="enrichment",
        profile=None,
    )

    assert visited == [1, 2, 3]
    assert state["status"] == "waiting_components"
    assert state["pending_components"][0]["part_index"] == 1
    assert state["coordinator_source_video_bytes"] == 0


def test_automatic_episode_waits_five_minutes_for_more_parts(tmp_path):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()
    service.observe(lv, lucifer)
    episode = next(
        item
        for item in service.pending_items()
        if item["source"] == LUCIFER_SOURCE
    )
    service._advance_part_to_verified = lambda *_args, **_kwargs: (
        pytest.fail("component work started before the episode settled")
    )

    state = service.advance_item(
        episode,
        lv_session="lv",
        private_session="private",
        enrichment_session="enrichment",
        profile=None,
    )

    assert state["event"] == "subscription_video_episode_settling"
    assert state["next_poll_not_before"] == "2026-07-25T16:05:00+08:00"
    assert state["completion_contract"] == "quiescent_filename_group"


def test_legacy_single_part_completion_pauses_episode_without_replay(tmp_path):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()
    service.observe(lv, lucifer)
    manifest = service._load_manifest()
    manifest.pop("episodes")
    for item in manifest["items"].values():
        item["work_eligible"] = False
        if item.get("path", "").endswith("7月5日（二）.mp4"):
            item["completed_version_key"] = item["version_key"]
    from xiaocao.kol.subscription_video import _atomic_write_json

    _atomic_write_json(service.manifest_path, manifest)

    assert service.observe(lv, lucifer) is None
    status = service.status()
    episode = next(iter(status["episodes"].values()))
    assert episode["work_eligible"] is False
    assert episode["pause_reason"] == (
        "historical_component_receipts_require_reconciliation"
    )
    assert status["episode_pauses"][0]["reason"] == (
        "historical_component_receipts_require_reconciliation"
    )
    assert all(
        row.get("episode_pause_reason")
        == "historical_component_receipts_require_reconciliation"
        for row in status["items"].values()
        if "/鹿7.5/" in row.get("path", "") and row["media_type"] == "video"
    )


def test_legacy_episode_useful_aggregate_waits_for_review_without_external_replay(
    tmp_path,
    monkeypatch,
):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()
    service.observe(lv, lucifer)
    manifest = service._load_manifest()
    manifest.pop("episodes")
    for item in manifest["items"].values():
        item["work_eligible"] = False
        if item.get("path", "").endswith("7月5日（二）.mp4"):
            item["completed_version_key"] = item["version_key"]
    from xiaocao.kol.subscription_video import _atomic_write_json

    _atomic_write_json(service.manifest_path, manifest)
    assert service.observe(lv, lucifer) is None
    episode = next(iter(service.status()["episodes"].values()))

    component_spec = {
        "episode_identity": episode["identity"],
        "episode_version_key": episode["version_key"],
        "components": [],
    }
    for part in episode["parts"]:
        transcript = tmp_path / f"part-{part['part_index']}.md"
        transcript.write_text(
            f"第{part['part_index']}段完整文稿证据。" * 500,
            encoding="utf-8",
        )
        component_spec["components"].append(
            {
                "source_identity": part["identity"],
                "version_identity": part["version_key"],
                "part_index": part["part_index"],
                "source_path": part["path"],
                "source_size": part["size"],
                "transcript_path": str(transcript),
                "transcript_sha256": __import__("hashlib").sha256(
                    transcript.read_bytes()
                ).hexdigest(),
            }
        )
    component_path = tmp_path / "components.json"
    component_path.write_text(
        json.dumps(component_spec, ensure_ascii=False),
        encoding="utf-8",
    )

    request = service.prepare_legacy_episode_review(
        episode["identity"],
        component_evidence_path=component_path,
    )
    coverage = [
        {
            "row_id": row_id,
            "conclusion": f"{row_id} 已核对",
            "evidence": [{"transcript_quote": "完整文稿证据"}],
        }
        for row_id in sorted(REQUIRED_COVERAGE_ROWS)
    ]
    episode_item = {
        "source": LUCIFER_SOURCE,
        "author": "路西法",
        "title": "路西法7月5日",
        "evidence_path": request["evidence_path"],
        "evidence_sha256": request["evidence_sha256"],
        "decision_status": "actionable_signal",
        "actionable_signals": [{"signal_id": "lucifer-episode-wait"}],
        "claims": [
            {
                "claim_id": "lucifer-aggregate-insight",
                "quote": "完整文稿证据",
                "reader_quote": "整期包含新的有效观点。",
            }
        ],
        "knowledge_status": "no_reusable_knowledge",
        "knowledge_reason": "历史分片已有材料，不重复蒸馏。",
        "coverage_matrix": coverage,
        "market_outlook": {"scope": "整体市场"},
        "synthesis": {
            "summary": "整期有值得转述的新观点。",
            "confidence": "medium",
            "reader_render_mode": "kol_context_corrected",
            "reader_quote_ids": ["lucifer-aggregate-insight"],
            "analysis_points": ["旧分片回执不等于整期没有新信息。"],
            "system_check": "只读核对，没有触发外部动作。",
            "system_advice": "先交用户审核。",
        },
        "xiaocao_cross_view": {
            "consensus": [{"topic": "risk"}],
            "conflicts": [],
            "unrelated": [],
            "duplicate_side_effect_policy": "历史分片回执只读，整期不重放。",
        },
        "book_kol_us": {
            "decision": "no_trade",
            "reason": "没有明确美股入场触发。",
        },
    }
    attach_claim_contract(episode_item, request["evidence_path"])
    bundle_path = tmp_path / "episode-bundle.json"
    bundle_path.write_text(
        json.dumps({"items": [episode_item]}, ensure_ascii=False),
        encoding="utf-8",
    )

    decisions = tmp_path / "decisions"
    decisions.mkdir()
    first_sha = component_spec["components"][0]["transcript_sha256"]
    (decisions / "household_outbox.jsonl").write_text(
        json.dumps(
            {
                "author": "路西法",
                "evidence_sha256": first_sha,
                "idempotency_key": "notice-1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (decisions / "events.jsonl").write_text(
        json.dumps(
            {
                "event": "notification_delivered",
                "status": "delivered",
                "idempotency_key": "notice-1",
                "receipt": "wecom-relay://ok/notice-1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    book_dir = decisions / "book_kol_us"
    book_dir.mkdir()
    (book_dir / "decisions.jsonl").write_text(
        json.dumps(
            {
                "book": "KOL-US",
                "paper_only": True,
                "status": "no_trade",
                "reason": "历史分片无美股动作。",
                "idempotency_key": first_sha,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    watched = [
        decisions / "household_outbox.jsonl",
        decisions / "events.jsonl",
        book_dir / "decisions.jsonl",
    ]
    before = [path.read_bytes() for path in watched]

    receipt = service.reconcile_legacy_episode_review(
        episode["identity"],
        bundle_path=bundle_path,
        decision_output_dir=decisions,
    )

    assert receipt["status"] == "awaiting_user_review"
    assert receipt["part_count"] == 3
    assert receipt["household_notification"]["status"] == "review_required"
    assert "整期包含新的有效观点" in receipt[
        "household_notification"
    ]["proposed_message"]
    assert receipt["book_kol_us_proposal"]["decision"] == "no_trade"
    assert receipt["new_external_side_effect_count"] == 0
    assert receipt["coordinator_source_video_bytes"] == 0
    assert [path.read_bytes() for path in watched] == before
    completed = service.status()["episodes"][episode["identity"]]
    assert "completed_version_key" not in completed
    assert completed["reconciliation_status"] == "awaiting_user_review"
    assert completed["pause_reason"] == (
        "useful_aggregate_insight_requires_user_review"
    )

    event_count = len(service._read_jsonl(service.events_path))
    replay = service.reconcile_legacy_episode_review(
        episode["identity"],
        bundle_path=bundle_path,
        decision_output_dir=decisions,
    )
    assert replay == receipt
    assert len(service._read_jsonl(service.events_path)) == event_count
    assert service.observe(lv, lucifer) is None
    rescanned = service.status()["episodes"][episode["identity"]]
    assert "completed_version_key" not in rescanned
    assert rescanned["reconciliation_status"] == "awaiting_user_review"
    assert rescanned["review_required_sha256"] == receipt[
        "review_required_sha256"
    ]
    assert rescanned["pause_reason"] == (
        "useful_aggregate_insight_requires_user_review"
    )
    assert [path.read_bytes() for path in watched] == before

    monkeypatch.setattr(
        service,
        "decide_item",
        lambda *_args, **_kwargs: pytest.fail(
            "historical approval must not enter the notification/Book path"
        ),
    )
    handoff = service.approve_legacy_episode_review(
        episode["identity"],
        bundle_path=bundle_path,
        decision_output_dir=decisions,
        sender=lambda _title, _body: {"wecom": "ok"},
    )
    assert handoff["status"] == "gray_publication_required"
    assert handoff["episode_identity"] == episode["identity"]
    assert handoff["notification_claim_authorized"] is False
    assert handoff["book_replay_authorized"] is False
    approval_claims = list(
        (service.output_dir / "claims").glob(
            "legacy_episode_gray_publication_handoff_*.json"
        )
    )
    assert len(approval_claims) == 1
    approval_claim = json.loads(
        approval_claims[0].read_text(encoding="utf-8")
    )
    assert approval_claim["external_side_effects_authorized"] is False
    assert approval_claim["notification_claim_authorized"] is False
    assert approval_claim["book_replay_authorized"] is False
    assert approval_claim["review_required_sha256"] == receipt[
        "review_required_sha256"
    ]
    assert [path.read_bytes() for path in watched] == before
    still_paused = service.status()["episodes"][episode["identity"]]
    assert still_paused["reconciliation_status"] == "awaiting_user_review"
    assert still_paused["pause_reason"] == (
        "useful_aggregate_insight_requires_user_review"
    )


def test_cloud_registration_uses_metadata_version_without_local_video(tmp_path):
    service = NetdiskEnrichmentService(
        tmp_path / "enrichment",
        now=lambda: NOW,
        opencli_command=("opencli",),
        netdisk_directory="/课程/路西法全套/鹿7.5",
    )

    state = service.prepare_cloud(
        netdisk_path="/课程/路西法全套/鹿7.5/7月5日（三）.mp4",
        provider_identity_sha256="a" * 64,
        size=744_292_790,
        modified_at=1_784_456_551,
        source=LUCIFER_SOURCE,
        author="路西法",
        observed_at=NOW,
    )
    replay = service.prepare_cloud(
        netdisk_path="/课程/路西法全套/鹿7.5/7月5日（三）.mp4",
        provider_identity_sha256="a" * 64,
        size=744_292_790,
        modified_at=1_784_456_551,
        source=LUCIFER_SOURCE,
        author="路西法",
        observed_at=NOW,
    )

    assert state["status"] == "video_ready"
    assert state["video_sha256_kind"] == "cloud_metadata_version"
    assert state["large_payload_local_bytes"] == 0
    assert "video_path" not in state
    assert state["browser_surface"] == "opencli"
    assert replay["idempotent_replay"] is True
    assert len(service.store.read()) == 1


def test_cloud_registration_rejects_author_or_directory_mismatch(tmp_path):
    service = NetdiskEnrichmentService(
        tmp_path / "enrichment",
        now=lambda: NOW,
        netdisk_directory="/课程/路西法全套/鹿7.5",
    )

    with pytest.raises(EnrichmentError, match="source and author"):
        service.prepare_cloud(
            netdisk_path="/课程/路西法全套/鹿7.5/video.mp4",
            provider_identity_sha256="a" * 64,
            size=1,
            modified_at=1,
            source=LUCIFER_SOURCE,
            author=LV_AUTHOR,
            observed_at=NOW,
        )
    with pytest.raises(EnrichmentError, match="outside"):
        service.prepare_cloud(
            netdisk_path="/课程/别处/video.mp4",
            provider_identity_sha256="a" * 64,
            size=1,
            modified_at=1,
            source=LUCIFER_SOURCE,
            author="路西法",
            observed_at=NOW,
        )


def test_cloud_registration_accepts_one_exact_root_child(tmp_path):
    service = NetdiskEnrichmentService(
        tmp_path / "enrichment",
        now=lambda: NOW,
        netdisk_directory="/",
    )

    state = service.prepare_cloud(
        netdisk_path="/7月20日.mp4",
        provider_identity_sha256="a" * 64,
        size=3_682_235_122,
        modified_at=1_784_969_033,
        source=LV_SOURCE,
        author=LV_AUTHOR,
        observed_at=NOW,
    )

    assert state["netdisk_directory"] == "/"
    assert state["netdisk_path"] == "/7月20日.mp4"
    assert state["large_payload_local_bytes"] == 0


def test_generated_content_audit_starts_inside_each_exact_third(tmp_path):
    service = _service(tmp_path)
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("甲" * 1001, encoding="utf-8")
    captured = {}

    class FakeEnrichment:
        def verify_transcript(self, job_id, *, audit_path):
            captured.update(json.loads(Path(audit_path).read_text(encoding="utf-8")))
            return {"job_id": job_id, "status": "verified"}

    state = {
        "job_id": "cloud-job",
        "source_version_sha256": "b" * 64,
        "video_sha256": "c" * 64,
        "transcript_path": str(transcript),
        "transcript_sha256": "d" * 64,
    }

    result = service._verify_transcript(FakeEnrichment(), state)

    assert result["status"] == "verified"
    assert [row["position"] for row in captured["checks"]] == [
        "opening",
        "middle",
        "ending",
    ]
    assert all(row["excerpt"] for row in captured["checks"])


def test_private_scan_uses_exact_vue_metadata_without_file_download(tmp_path):
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        tail = command[5:]
        if tail[:1] == ["open"]:
            payload = {"url": tail[1]}
        elif tail[:1] == ["eval"]:
            assert "row.__vue__?._props?.item" in tail[1]
            assert "/api/list" not in tail[1]
            assert "download" not in tail[1].lower()
            payload = {
                "status": "ok",
                "complete_scan": True,
                "directories_scanned": 1,
                "entries": [
                    _row(
                        "lucifer-c",
                        "/课程/路西法全套/鹿7.5/7月5日（三）.mp4",
                        size=744_292_790,
                        modified_at=1_784_456_551,
                    )
                ],
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    service = _service(tmp_path, runner=runner)

    result = service._scan_private(
        session="ticket05",
        profile="work",
        root="/课程/路西法全套/鹿7.5",
        recursive=True,
    )

    assert result["entries"][0]["size"] == 744_292_790
    assert len(commands) == 2


def test_explicit_episode_spec_maps_arbitrary_real_source_names(tmp_path):
    lv, lucifer = _source_rows()
    arbitrary = [
        _row(
            "lucifer-keynote",
            "/课程/路西法全套/活动/keynote-final.mp4",
            size=100,
            modified_at=1_784_456_551,
        ),
        _row(
            "lucifer-qa",
            "/课程/路西法全套/活动/现场问答.mp4",
            size=200,
            modified_at=1_784_456_552,
        ),
    ]
    spec = tmp_path / "episodes.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "episodes": [
                    {
                        "source": LUCIFER_SOURCE,
                        "episode_id": "launch-day",
                        "title": "新品发布日",
                        "parts": [
                            {
                                "path": arbitrary[1]["path"],
                                "index": 2,
                                "label": "Q&A",
                            },
                            {
                                "path": arbitrary[0]["path"],
                                "index": 1,
                                "label": "keynote",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _lv, updated = SubscriptionVideoService._apply_episode_spec(
        lv,
        [*lucifer, *arbitrary],
        episode_spec_path=spec,
    )
    selected = [
        row for row in updated if row.get("episode_id") == "launch-day"
    ]

    assert {row["part_index"] for row in selected} == {1, 2}
    assert {row["episode_title"] for row in selected} == {"新品发布日"}


def test_folder_creation_recovers_the_observed_baidu_inline_editor():
    assert ".wp-s-pan-list__file-name-edit" in _CREATE_FOLDER_SCRIPT
    assert "input.closest('.wp-s-pan-list__file-name-edit')" in (
        _CREATE_FOLDER_SCRIPT
    )


def test_private_search_accepts_stable_fuzzy_results_as_exact_zero_matches():
    assert "bodyText.includes('搜索：' + targetName)" in _PRIVATE_SEARCH_SCRIPT
    assert "items.length > 0 && stablePolls >= 5" in _PRIVATE_SEARCH_SCRIPT
    assert "search_settled: true" in _PRIVATE_SEARCH_SCRIPT


def test_lv_transfer_observes_provider_outcome_after_confirmation():
    assert "const beforeLines = new Set(" in _TRANSFER_SCRIPT
    assert "data-xiaocao-lv-confirm" in _TRANSFER_SCRIPT
    assert "confirms[0].click()" not in _TRANSFER_SCRIPT
    assert "cloud_transfer_rejected" in _TRANSFER_OUTCOME_SCRIPT
    assert "cloud_transfer_accepted" in _TRANSFER_OUTCOME_SCRIPT
    assert "provider_outcome: 'unobserved'" in _TRANSFER_OUTCOME_SCRIPT


def test_lv_transfer_claim_precedes_trigger_and_replay_only_reconciles(tmp_path):
    triggered = False
    native_click_calls = 0
    service = _service(tmp_path, sleep=lambda _seconds: None)
    item = service._normalize(
        _source_rows()[0][1],
        source=LV_SOURCE,
        author=LV_AUTHOR,
    )
    item.update(
        {
            "version_first_seen_at": NOW.isoformat(),
            "first_seen_at": NOW.isoformat(),
            "present": True,
            "work_eligible": True,
        }
    )

    service.ensure_lv_destination = lambda **_kwargs: {"status": "completed"}

    def direct_entries(*, directory, **_kwargs):
        if directory != LV_DESTINATION_DIRECTORY or not triggered:
            return []
        return [
            _row(
                "private-lv-copy",
                f"{LV_DESTINATION_DIRECTORY}/{item['name']}",
                size=item["size"],
                modified_at=item["modified_at"] + 10,
            )
        ]

    service._direct_private_entries = direct_entries

    def opencli(session, *args, **_kwargs):
        nonlocal triggered, native_click_calls
        if args[0] == "open":
            return {"url": "sanitized"}
        claim_path = service._claim_path(f"lv_transfer_{item['version_key']}")
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        assert claim["large_payload_local_bytes"] == 0
        if args[0] == "click":
            native_click_calls += 1
            assert claim["status"] == "native_click_claimed"
            assert args[1] == '[data-xiaocao-lv-confirm="ready"]'
            return {
                "clicked": True,
                "target": args[1],
                "matches_n": 1,
            }
        assert args[0] == "eval"
        if "destinationSegments" in args[1]:
            assert claim["status"] == "claimed"
            return {
                "status": "save_confirmation_ready",
                "confirmation_selector": (
                    '[data-xiaocao-lv-confirm="ready"]'
                ),
                "triggered": False,
            }
        assert claim["status"] == "native_click_claimed"
        triggered = True
        return {
            "status": "cloud_transfer_triggered",
            "triggered": True,
            "provider_outcome": "unobserved",
        }

    service._opencli_json = opencli

    first = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )
    second = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )

    assert first["status"] == "completed"
    assert first["target_size"] == item["size"]
    assert first["large_payload_local_bytes"] == 0
    assert second["status"] == "completed"
    assert native_click_calls == 1
    assert len(
        [
            row
            for row in service.events_path.read_text().splitlines()
            if "lv_cloud_transfer_triggered" in row
        ]
    ) == 1


def test_lv_transfer_reconciles_observed_default_root_save_without_resend(
    tmp_path,
):
    service = _service(tmp_path, sleep=lambda _seconds: None)
    item = service._normalize(
        _source_rows()[0][1],
        source=LV_SOURCE,
        author=LV_AUTHOR,
    )
    item.update(
        {
            "version_first_seen_at": NOW.isoformat(),
            "first_seen_at": NOW.isoformat(),
            "present": True,
            "work_eligible": True,
        }
    )
    service.ensure_lv_destination = lambda **_kwargs: {"status": "completed"}
    service._direct_private_entries = lambda **_kwargs: []
    root_ready = False
    trigger_calls = 0

    def search(**_kwargs):
        if not root_ready:
            return []
        return [
            _row(
                "root-copy",
                f"/{item['name']}",
                size=item["size"],
                modified_at=item["modified_at"] + 1,
            )
        ]

    service._search_private_exact = search

    def opencli(_session, *args, **_kwargs):
        nonlocal root_ready, trigger_calls
        if args[0] == "open":
            return {"url": "sanitized"}
        trigger_calls += 1
        root_ready = True
        return {"status": "save_dialog_missing", "triggered": False}

    service._opencli_json = opencli
    with pytest.raises(EnrichmentError, match="save_dialog_missing"):
        service.transfer_lv_video(
            item,
            lv_session="lv",
            private_session="private",
            profile="work",
        )

    recovered = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )
    replay = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )

    assert recovered["status"] == "completed"
    assert recovered["target_path"] == f"/{item['name']}"
    assert recovered["reconciled_default_root_save"] is True
    assert recovered["large_payload_local_bytes"] == 0
    assert replay["target_path"] == recovered["target_path"]
    assert trigger_calls == 1


def test_lv_transfer_reconciles_default_root_after_confirmed_trigger(
    tmp_path,
):
    service = _service(tmp_path, sleep=lambda _seconds: None)
    item = service._normalize(
        _source_rows()[0][1],
        source=LV_SOURCE,
        author=LV_AUTHOR,
    )
    item.update(
        {
            "version_first_seen_at": NOW.isoformat(),
            "first_seen_at": NOW.isoformat(),
            "present": True,
            "work_eligible": True,
        }
    )
    service.ensure_lv_destination = lambda **_kwargs: {"status": "completed"}
    service._direct_private_entries = lambda **_kwargs: []
    root_ready = False
    trigger_calls = 0

    def search(**_kwargs):
        if not root_ready:
            return []
        return [
            _row(
                "root-copy",
                f"/{item['name']}",
                size=item["size"],
                modified_at=item["modified_at"] + 1,
            )
        ]

    service._search_private_exact = search

    def opencli(_session, *args, **_kwargs):
        nonlocal root_ready, trigger_calls
        if args[0] == "open":
            return {"url": "sanitized"}
        trigger_calls += 1
        root_ready = True
        return {"status": "cloud_transfer_triggered", "triggered": True}

    service._opencli_json = opencli

    recovered = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )
    replay = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )

    assert recovered["status"] == "completed"
    assert recovered["target_path"] == f"/{item['name']}"
    assert recovered["reconciled_default_root_save"] is True
    assert recovered["large_payload_local_bytes"] == 0
    assert replay["target_path"] == recovered["target_path"]
    assert trigger_calls == 1


def test_lv_transfer_retries_once_after_settled_exact_absence(tmp_path):
    service = _service(tmp_path, sleep=lambda _seconds: None)
    item = service._normalize(
        _source_rows()[0][1],
        source=LV_SOURCE,
        author=LV_AUTHOR,
    )
    item.update(
        {
            "version_first_seen_at": NOW.isoformat(),
            "first_seen_at": NOW.isoformat(),
            "present": True,
            "work_eligible": True,
        }
    )
    service.ensure_lv_destination = lambda **_kwargs: {"status": "completed"}
    target_ready = False
    trigger_calls = 0

    def direct_entries(*, directory, **_kwargs):
        if directory != LV_DESTINATION_DIRECTORY or not target_ready:
            return []
        return [
            _row(
                "private-recovered-copy",
                f"{LV_DESTINATION_DIRECTORY}/{item['name']}",
                size=item["size"],
                modified_at=item["modified_at"] + 1,
            )
        ]

    service._direct_private_entries = direct_entries
    service._search_private_exact = lambda **_kwargs: []
    receipt_name = f"lv_transfer_{item['version_key']}"
    claim_path = service._claim_path(receipt_name)
    claim_path.parent.mkdir(parents=True)
    first_triggered_at = NOW - timedelta(minutes=31)
    claim_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event": "lv_transfer_claimed",
                "status": "triggered",
                "claim_id": "first-claim",
                "claimed_at": first_triggered_at.isoformat(),
                "triggered_at": first_triggered_at.isoformat(),
                "trigger_attempt": 1,
                "source_identity": item["identity"],
                "source_version_key": item["version_key"],
                "source_path": item["path"],
                "source_size": item["size"],
                "target_path": (
                    f"{LV_DESTINATION_DIRECTORY}/{item['name']}"
                ),
                "large_payload_local_bytes": 0,
            }
        ),
        encoding="utf-8",
    )

    def opencli(_session, *args, **_kwargs):
        nonlocal target_ready, trigger_calls
        if args[0] == "open":
            return {"url": "sanitized"}
        trigger_calls += 1
        target_ready = True
        return {"status": "cloud_transfer_triggered", "triggered": True}

    service._opencli_json = opencli

    recovered = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )

    assert recovered["status"] == "completed"
    assert recovered["target_size"] == item["size"]
    assert trigger_calls == 1
    assert "lv_cloud_transfer_recovery_claimed" in (
        service.events_path.read_text(encoding="utf-8")
    )


def test_lv_transfer_stops_after_bounded_reconciled_retry(tmp_path):
    service = _service(tmp_path, sleep=lambda _seconds: None)
    item = service._normalize(
        _source_rows()[0][1],
        source=LV_SOURCE,
        author=LV_AUTHOR,
    )
    item.update(
        {
            "version_first_seen_at": NOW.isoformat(),
            "first_seen_at": NOW.isoformat(),
            "present": True,
            "work_eligible": True,
        }
    )
    service.ensure_lv_destination = lambda **_kwargs: {"status": "completed"}
    service._direct_private_entries = lambda **_kwargs: []
    service._search_private_exact = lambda **_kwargs: []
    receipt_name = f"lv_transfer_{item['version_key']}"
    claim_path = service._claim_path(receipt_name)
    claim_path.parent.mkdir(parents=True)
    second_triggered_at = NOW - timedelta(minutes=31)
    claim_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event": "lv_transfer_recovery_claimed",
                "status": "triggered",
                "claim_id": "second-claim",
                "claimed_at": second_triggered_at.isoformat(),
                "triggered_at": second_triggered_at.isoformat(),
                "trigger_attempt": 2,
                "source_identity": item["identity"],
                "source_version_key": item["version_key"],
                "source_path": item["path"],
                "source_size": item["size"],
                "target_path": (
                    f"{LV_DESTINATION_DIRECTORY}/{item['name']}"
                ),
                "large_payload_local_bytes": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        EnrichmentError,
        match="did not materialize after bounded exact reconciliation",
    ):
        service.transfer_lv_video(
            item,
            lv_session="lv",
            private_session="private",
            profile="work",
        )

    blocked = json.loads(claim_path.read_text(encoding="utf-8"))
    assert blocked["status"] == "blocked"
    assert blocked["blocker_key"] == (
        "lv-cloud-transfer-not-materialized"
    )
    assert blocked["reconciliation_status"] == (
        "exact_private_copy_absent_after_bounded_retry"
    )
    assert blocked["user_action_required"] is True


def test_lv_transfer_blocker_recovers_by_read_only_target_reconciliation(
    tmp_path,
):
    service = _service(tmp_path, sleep=lambda _seconds: None)
    item = service._normalize(
        _source_rows()[0][1],
        source=LV_SOURCE,
        author=LV_AUTHOR,
    )
    item.update(
        {
            "version_first_seen_at": NOW.isoformat(),
            "first_seen_at": NOW.isoformat(),
            "present": True,
            "work_eligible": True,
        }
    )
    service.ensure_lv_destination = lambda **_kwargs: {"status": "completed"}
    service._direct_private_entries = lambda **_kwargs: [
        _row(
            "manually-saved-copy",
            f"{LV_DESTINATION_DIRECTORY}/{item['name']}",
            size=item["size"],
            modified_at=item["modified_at"] + 60,
        )
    ]
    service._opencli_json = lambda *_args, **_kwargs: pytest.fail(
        "blocked recovery must not trigger another share-side save"
    )
    receipt_name = f"lv_transfer_{item['version_key']}"
    claim_path = service._claim_path(receipt_name)
    claim_path.parent.mkdir(parents=True)
    claim_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event": "lv_cloud_transfer_blocked",
                "status": "blocked",
                "claim_id": "blocked-claim",
                "claimed_at": NOW.isoformat(),
                "triggered_at": (
                    NOW - timedelta(minutes=31)
                ).isoformat(),
                "trigger_attempt": 2,
                "source_identity": item["identity"],
                "source_version_key": item["version_key"],
                "source_path": item["path"],
                "source_size": item["size"],
                "target_path": (
                    f"{LV_DESTINATION_DIRECTORY}/{item['name']}"
                ),
                "large_payload_local_bytes": 0,
                "blocker_key": "lv-cloud-transfer-not-materialized",
                "user_action_required": True,
            }
        ),
        encoding="utf-8",
    )

    recovered = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )
    replay = service.transfer_lv_video(
        item,
        lv_session="lv",
        private_session="private",
        profile="work",
    )

    assert recovered["status"] == "completed"
    assert recovered["target_path"] == (
        f"{LV_DESTINATION_DIRECTORY}/{item['name']}"
    )
    assert recovered["target_size"] == item["size"]
    assert recovered["large_payload_local_bytes"] == 0
    assert replay["status"] == "completed"
    assert replay["idempotent_replay"] is True


def test_lv_transfer_stops_on_explicit_provider_rejection(tmp_path):
    service = _service(tmp_path, sleep=lambda _seconds: None)
    item = service._normalize(
        _source_rows()[0][1],
        source=LV_SOURCE,
        author=LV_AUTHOR,
    )
    item.update(
        {
            "version_first_seen_at": NOW.isoformat(),
            "first_seen_at": NOW.isoformat(),
            "present": True,
            "work_eligible": True,
        }
    )
    service.ensure_lv_destination = lambda **_kwargs: {"status": "completed"}
    service._direct_private_entries = lambda **_kwargs: []
    service._search_private_exact = lambda **_kwargs: []

    def opencli(_session, *args, **_kwargs):
        if args[0] == "open":
            return {"url": "sanitized"}
        return {
            "status": "cloud_transfer_rejected",
            "triggered": True,
            "provider_outcome": "rejected",
        }

    service._opencli_json = opencli

    with pytest.raises(
        EnrichmentError,
        match="Lv cloud transfer was rejected by provider",
    ):
        service.transfer_lv_video(
            item,
            lv_session="lv",
            private_session="private",
            profile="work",
        )

    claim_path = service._claim_path(f"lv_transfer_{item['version_key']}")
    blocked = json.loads(claim_path.read_text(encoding="utf-8"))
    assert blocked["status"] == "blocked"
    assert blocked["blocker_key"] == (
        "lv-cloud-transfer-provider-rejected"
    )
    assert blocked["reconciliation_status"] == "provider_rejected"


def test_semantic_duplicate_requires_receipted_household_and_paper_ledgers(
    tmp_path,
):
    service = _service(tmp_path)
    item = service._normalize(
        _row(
            "lucifer-b",
            "/课程/路西法全套/鹿7.5/7月5日（二）.mp4",
            size=578_859_389,
            modified_at=1_784_456_551,
        ),
        source=LUCIFER_SOURCE,
        author="路西法",
    )
    current = tmp_path / "current.txt"
    prior = tmp_path / "prior.md"
    body = "完整文稿证据，包含市场、仓位和点名资产。" * 300
    current.write_text(body, encoding="utf-8")
    prior.write_text("\n".join(body), encoding="utf-8")
    state = {
        "transcript_path": str(current),
        "transcript_sha256": __import__("hashlib").sha256(
            current.read_bytes()
        ).hexdigest(),
    }
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "author": "路西法",
                        "title": "路西法7月5日（二）",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    decisions = tmp_path / "decisions"
    decisions.mkdir()
    prior_sha = __import__("hashlib").sha256(prior.read_bytes()).hexdigest()
    (decisions / "household_outbox.jsonl").write_text(
        json.dumps(
            {
                "author": "路西法",
                "title": "路西法7月5日（二）",
                "evidence": str(prior),
                "evidence_sha256": prior_sha,
                "idempotency_key": "notice-1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    assert (
        service._semantic_duplicate_input(
            item,
            state,
            bundle_path=bundle,
            decision_output_dir=decisions,
        )
        is None
    )

    (decisions / "events.jsonl").write_text(
        json.dumps(
            {
                "event": "notification_delivered",
                "idempotency_key": "notice-1",
                "status": "delivered",
                "receipt": "wecom-relay://ok/notice-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    book_dir = decisions / "book_kol_us"
    book_dir.mkdir()
    (book_dir / "decisions.jsonl").write_text(
        json.dumps(
            {
                "book": "KOL-US",
                "paper_only": True,
                "status": "no_trade",
                "reason": "点名机会只在 A 股。",
                "idempotency_key": prior_sha,
                "evidence_context": {"evidence_sha256": prior_sha},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    reconciliation_path = service._semantic_duplicate_input(
        item,
        state,
        bundle_path=bundle,
        decision_output_dir=decisions,
    )

    assert reconciliation_path is not None
    reconciliation = json.loads(
        reconciliation_path.read_text(encoding="utf-8")
    )
    assert reconciliation["normalized_similarity"] == 1.0
    assert reconciliation["normalized_containment"] is True
    assert reconciliation["household_notification"]["status"] == "delivered"
    assert reconciliation["book_kol_us"]["status"] == "no_trade"


def _ticket05_analysis_bundle(
    service: SubscriptionVideoService,
    tmp_path: Path,
) -> tuple[dict, dict, Path]:
    item = service._normalize(
        _row(
            "lucifer-b",
            "/课程/路西法全套/鹿7.5/7月5日（二）.mp4",
            size=578_859_389,
            modified_at=1_784_456_551,
        ),
        source=LUCIFER_SOURCE,
        author="路西法",
    )
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("完整文稿证据。" * 500, encoding="utf-8")
    evidence_sha = __import__("hashlib").sha256(transcript.read_bytes()).hexdigest()
    state = {
        "transcript_path": str(transcript),
        "transcript_sha256": evidence_sha,
    }
    coverage = [
        {
            "row_id": row_id,
            "conclusion": f"{row_id} 已核对",
            "evidence": [{"transcript_quote": "完整文稿证据"}],
        }
        for row_id in sorted(REQUIRED_COVERAGE_ROWS)
    ]
    decision_item = {
        "source": LUCIFER_SOURCE,
        "author": "路西法",
        "title": "路西法7月5日（二）",
        "evidence_path": str(transcript),
        "evidence_sha256": evidence_sha,
        "decision_status": "actionable_signal",
        "actionable_signals": [{"signal_id": "lucifer-signal"}],
        "claims": [
            {
                "claim_id": "lucifer-signal-claim",
                "quote": "完整文稿证据",
                "reader_quote": "整期包含完整文稿证据。",
            }
        ],
        "knowledge_status": "no_reusable_knowledge",
        "knowledge_reason": "同一内容已有蒸馏，不重复写入。",
        "coverage_matrix": coverage,
        "market_outlook": {"scope": "整体市场"},
        "xiaocao_cross_view": {
            "consensus": [{"topic": "risk"}],
            "conflicts": [],
            "unrelated": [],
            "duplicate_side_effect_policy": "只复用既有回执。",
        },
        "book_kol_us": {
            "decision": "no_trade",
            "reason": "没有明确美股入场触发。",
        },
    }
    attach_claim_contract(decision_item, transcript)
    bundle = {"items": [decision_item]}
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    return item, state, bundle_path


def test_ticket05_analysis_bundle_requires_exact_branch_statuses(tmp_path):
    service = _service(tmp_path)
    item, state, bundle_path = _ticket05_analysis_bundle(service, tmp_path)

    validated = service._validate_analysis_bundle(
        item,
        state,
        bundle_path=bundle_path,
    )
    assert validated["decision_status"] == "actionable_signal"
    assert validated["knowledge_status"] == "no_reusable_knowledge"

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["items"][0].pop("decision_status")
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(EnrichmentError, match="decision_status"):
        service._validate_analysis_bundle(
            item,
            state,
            bundle_path=bundle_path,
        )


def test_ticket05_analysis_bundle_requires_cross_view_and_full_coverage(
    tmp_path,
):
    service = _service(tmp_path)
    item, state, bundle_path = _ticket05_analysis_bundle(service, tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["items"][0]["coverage_matrix"].pop()
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(EnrichmentError, match="coverage"):
        service._validate_analysis_bundle(
            item,
            state,
            bundle_path=bundle_path,
        )

    _, _, bundle_path = _ticket05_analysis_bundle(service, tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["items"][0]["xiaocao_cross_view"] = {
        "consensus": [],
        "conflicts": [],
        "unrelated": [],
        "side_effect_policy": "不重复。",
    }
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(EnrichmentError, match="cross-view"):
        service._validate_analysis_bundle(
            item,
            state,
            bundle_path=bundle_path,
        )
