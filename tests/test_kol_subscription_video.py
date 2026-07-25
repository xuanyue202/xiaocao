from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.netdisk_enrichment import NetdiskEnrichmentService
from xiaocao.kol.subscription_video import (
    _CREATE_FOLDER_SCRIPT,
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


def test_bootstrap_scans_history_but_selects_one_real_video_per_source(tmp_path):
    service = _service(tmp_path)
    lv, lucifer = _source_rows()

    discovered = service.observe(lv, lucifer)

    assert [row["path"] for row in discovered["updates"]] == [
        "/share/2026年7月/7月20日.mp4",
        "/课程/路西法全套/鹿7.5/7月5日（三）.mp4",
    ]
    assert {row["source"] for row in service.pending_items()} == {
        LV_SOURCE,
        LUCIFER_SOURCE,
    }
    status = service.status()
    assert status["bootstrap"]["policy"] == "latest_real_video_per_source"
    assert status["bootstrap"]["historical_video_baseline_count"] == 2
    assert status["source_counts"] == {LV_SOURCE: 3, LUCIFER_SOURCE: 3}
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


def test_folder_creation_recovers_the_observed_baidu_inline_editor():
    assert ".wp-s-pan-list__file-name-edit" in _CREATE_FOLDER_SCRIPT
    assert "input.closest('.wp-s-pan-list__file-name-edit')" in (
        _CREATE_FOLDER_SCRIPT
    )


def test_lv_transfer_claim_precedes_trigger_and_replay_only_reconciles(tmp_path):
    triggered = False
    transfer_calls = 0
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
        nonlocal triggered, transfer_calls
        if args[0] == "open":
            return {"url": "sanitized"}
        assert args[0] == "eval"
        transfer_calls += 1
        claim_path = service._claim_path(f"lv_transfer_{item['version_key']}")
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        assert claim["status"] == "claimed"
        assert claim["large_payload_local_bytes"] == 0
        triggered = True
        return {"status": "cloud_transfer_triggered", "triggered": True}

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
    assert transfer_calls == 1
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
    bundle = {
        "items": [
            {
                "source": LUCIFER_SOURCE,
                "author": "路西法",
                "title": "路西法7月5日（二）",
                "evidence_path": str(transcript),
                "evidence_sha256": evidence_sha,
                "decision_status": "actionable_signal",
                "actionable_signals": [{"signal_id": "lucifer-signal"}],
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
        ]
    }
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
