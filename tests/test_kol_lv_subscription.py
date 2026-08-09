from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.kol_claim_fixture import attach_claim_contract
import xiaocao.kol.lv_subscription as lv_subscription
from xiaocao.kol.decisions import DecisionPipeline
from xiaocao.kol.enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
)
from xiaocao.kol.lv_subscription import LvSubscriptionService


NOW = datetime.fromisoformat("2026-07-25T10:00:00+08:00")


def _representative_subscription_entries() -> list[dict]:
    return [
        {
            "provider_file_id": "image-12",
            "path": "/彤商学院防断更新zk7897897/7月25日/12.png",
            "name": "12.png",
            "is_dir": False,
            "size": 286_912,
            "modified_at": 1_784_944_800,
        },
        {
            "provider_file_id": "text-daily",
            "path": "/彤商学院防断更新zk7897897/7月25日/盘后.txt",
            "name": "盘后.txt",
            "is_dir": False,
            "size": 8_192,
            "modified_at": 1_784_945_400,
        },
        {
            "provider_file_id": "video-daily",
            "path": "/彤商学院防断更新zk7897897/7月25日/7月25日.mp4",
            "name": "7月25日.mp4",
            "is_dir": False,
            "size": 800_000_000,
            "modified_at": 1_784_945_600,
        },
    ]


def _capture_browser_download(
    service: LvSubscriptionService,
    identity: str,
    path: Path,
) -> dict:
    claim = service.claim_browser_download(identity)
    return service.complete_browser_download(
        identity,
        path,
        claim_id=claim["claim_id"],
    )


def test_ticket_records_sanitized_iab_policy_failure_and_opencli_bootstrap():
    ticket = (
        Path(__file__).parents[1]
        / ".scratch"
        / "kol-intelligence-mvp"
        / "issues"
        / "04-lv-text-image-to-decisions.md"
    ).read_text(encoding="utf-8")

    assert "browser_security_policy_denied" in ticket
    assert "built-in browser" in ticket
    assert "Microsoft Edge" in ticket
    assert "Google Chrome" in ticket
    assert "OpenCLI Browser Bridge" in ticket
    assert "OpenCLI" in ticket
    assert "attach that exact tab" not in ticket
    assert "https://pan.baidu.com/s/" not in ticket


def test_browser_listing_discovers_text_and_image_then_same_poll_is_quiet(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)

    first = service.observe_browser_listing(_representative_subscription_entries())
    second = service.observe_browser_listing(_representative_subscription_entries())

    assert [row["media_type"] for row in first["updates"]] == ["image", "text"]
    assert first["observed_count"] == 3
    assert first["excluded_count"] == 1
    assert first["cursor"]
    assert second is None

    events = (tmp_path / "out" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 1
    assert json.loads(events[0])["event"] == "subscription_updates_discovered"

    persisted = (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    assert "subscription_share_url" not in persisted
    assert "subscription_share_code" not in persisted
    assert "7月25日.mp4" in persisted


def test_bootstrap_baselines_history_and_keeps_only_latest_supported_versions(
    tmp_path,
):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    entries = _representative_subscription_entries()
    older_image = {
        **entries[0],
        "provider_file_id": "older-image",
        "path": "/彤商学院防断更新zk7897897/7月2日/older.png",
        "name": "older.png",
        "modified_at": entries[0]["modified_at"] - 86_400,
    }

    discovered = service.observe_browser_listing([older_image, *entries])

    assert discovered["bootstrap_baseline_count"] == 1
    assert [row["name"] for row in discovered["updates"]] == [
        "12.png",
        "盘后.txt",
    ]
    assert [row["name"] for row in service.pending_items()] == [
        "12.png",
        "盘后.txt",
    ]
    manifest = json.loads(
        (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["bootstrap"] == {
        "policy": "latest_version_per_supported_media_type",
        "completed_at": NOW.isoformat(timespec="seconds"),
        "baseline_only_count": 1,
        "work_eligible_count": 2,
    }


def test_isolated_item_failure_does_not_change_existing_claim(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    service.observe_browser_listing(_representative_subscription_entries())
    item = service.pending_items()[0]
    claim = service.claim_browser_download(item["identity"])
    claim_path = (
        tmp_path
        / "out"
        / "artifacts"
        / item["version_key"]
        / "browser_download_claim.json"
    )
    before = claim_path.read_bytes()

    recorded = service.record_item_failure(
        item["identity"],
        failure={
            "category": "timeout",
            "code": "opencli_timeout",
            "stage": "browser_command",
        },
        retryable=True,
    )

    assert claim_path.read_bytes() == before
    assert recorded["claim_status"] == claim["status"] == "claimed"
    assert recorded["external_business_effects_replayed"] is False
    assert service.pending_items()[0]["identity"] == item["identity"]


def test_reviewed_historical_small_items_retire_without_fabricating_completion_and_new_version_reopens(
    tmp_path,
):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    entries = _representative_subscription_entries()
    service.observe_browser_listing(entries)
    target = service.pending_items()[0]
    claim_path = (
        tmp_path
        / "out"
        / "artifacts"
        / target["version_key"]
        / "browser_download_claim.json"
    )
    service.claim_browser_download(target["identity"])
    claim_before = claim_path.read_bytes()

    migration = service.retire_historical_versions(
        [{
            "identity": target["identity"],
            "version_key": target["version_key"],
        }],
        cutoff_modified_at=target["modified_at"],
    )

    retired = json.loads(
        service.manifest_path.read_text(encoding="utf-8")
    )["items"][target["identity"]]
    assert migration["status"] == "completed"
    assert migration["retired_count"] == 1
    assert migration["claims_and_receipts_preserved"] is True
    assert migration["completed_version_keys_written"] == 0
    assert retired["work_eligible"] is False
    assert retired["pause_reason"] == "historical_backlog_retired"
    assert retired.get("completed_version_key") is None
    assert claim_path.read_bytes() == claim_before
    assert target["identity"] not in {
        row["identity"] for row in service.pending_items()
    }

    newer = [
        {
            **row,
            "modified_at": row["modified_at"] + 60,
        }
        if row["provider_file_id"] == entries[0]["provider_file_id"]
        else row
        for row in entries
    ]
    service.observe_browser_listing(newer)
    reopened = json.loads(
        service.manifest_path.read_text(encoding="utf-8")
    )["items"][target["identity"]]
    assert reopened["version_key"] != target["version_key"]
    assert reopened["work_eligible"] is True
    assert "pause_reason" not in reopened


def test_disappearing_item_keeps_identity_and_only_a_new_version_is_rediscovered(
    tmp_path,
):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    image = _representative_subscription_entries()[0]

    first = service.observe_browser_listing([image])
    absent = service.observe_browser_listing([])
    reappeared = service.observe_browser_listing([image])
    changed_image = {**image, "modified_at": image["modified_at"] + 60}
    changed = service.observe_browser_listing([changed_image])

    assert len(first["updates"]) == 1
    assert absent is None
    assert reappeared is None
    assert len(changed["updates"]) == 1
    assert changed["updates"][0]["identity"] == first["updates"][0]["identity"]
    assert (
        changed["updates"][0]["version_key"]
        != first["updates"][0]["version_key"]
    )

    manifest = json.loads(
        (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["items"]) == 1
    assert next(iter(manifest["items"].values()))["present"] is True


def test_browser_listing_rejects_missing_provider_modification_time(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    invalid = {**_representative_subscription_entries()[0], "modified_at": 0}

    with pytest.raises(EnrichmentError, match="modification time"):
        service.observe_browser_listing([invalid])

    assert not (tmp_path / "out" / "manifest.json").exists()


def test_private_config_drives_one_browser_listing_path_without_persisting_credentials(
    tmp_path,
):
    private_url = "https://pan.baidu.com/s/private-share-token"
    private_code = "a1b2"
    commands: list[list[str]] = []
    listing_calls = 0

    def browser_runner(command, **_kwargs):
        nonlocal listing_calls
        commands.append(command)
        assert command[:5] == [
            "opencli",
            "--profile",
            "work",
            "browser",
            "ticket04",
        ]
        tail = command[5:]
        if tail[:1] == ["open"]:
            payload = {"url": private_url, "page": "page-1"}
        elif tail[:1] == ["eval"] and "authorization_required" in tail[1]:
            listing_calls += 1
            payload = (
                {"status": "authorization_required"}
                if listing_calls == 1
                else {
                    "status": "ok",
                    "complete_scan": True,
                    "entries": _representative_subscription_entries(),
                }
            )
        elif tail[:1] == ["eval"] and "share_code" in tail[1]:
            payload = {"status": "authorization_submitted"}
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url=private_url,
        share_code=private_code,
    )

    result = service.poll_opencli(session="ticket04", profile="work")

    assert result["observed_count"] == 3
    assert listing_calls == 2
    assert commands[0][:4] == ["opencli", "--profile", "work", "browser"]
    assert commands[0][4:7] == [
        "ticket04",
        "open",
        f"{private_url}?pwd={private_code}",
    ]
    assert "/share/list" in commands[1][-1]
    assert "performance.getEntriesByType('resource')" in commands[1][-1]
    assert "parsed.searchParams.has('shorturl')" in commands[1][-1]
    assert "parsed.searchParams.has('sekey')" in commands[1][-1]
    assert "parsed.searchParams.set('dir', String(dir))" in commands[1][-1]
    assert "String(item.isdir) === '1'" in commands[1][-1]
    assert "new URLSearchParams({" not in commands[1][-1]
    assert "expectedPath" in commands[1][-1]
    assert "/s/private-share-token" in commands[1][-1]

    durable = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "out").glob("*.json*")
    )
    assert private_url not in durable
    assert private_code not in durable


def test_authorized_share_url_preserves_the_root_hash_route():
    assert lv_subscription._authorized_share_url(
        "https://pan.baidu.com/s/private-share-token#list/path=%2F",
        "a1b2",
    ) == (
        "https://pan.baidu.com/s/private-share-token"
        "?pwd=a1b2#list/path=%2F"
    )


def test_browser_listing_recurses_without_parent_mtime_pruning_in_bounded_batches():
    script = lv_subscription._browser_listing_script(
        "/s/private-share-token"
    )

    assert "pendingDirs.push(path)" in script
    assert "const maxConcurrentDirectories = 4;" in script
    assert (
        "const batch = pendingDirs.splice(0, maxConcurrentDirectories);"
        in script
    )
    assert "await Promise.all(batch.map(async dir =>" in script
    assert "const controller = new AbortController();" in script
    assert "share_list_timeout" in script
    assert ".includes('已失效')" not in script
    assert "exact_visible_terminal" in script
    assert "provider_errno" in script
    assert "json_error_position" in script
    assert "item.server_mtime" not in script[
        script.index("if (isDir && !seenDirs.has(path))") :
        script.index("const maxDirectories")
    ]


@pytest.mark.parametrize(
    "initial_status",
    ["share_list_invalid_json", "share_list_timeout"],
)
def test_listing_recovers_once_after_transient_full_scan_failure(
    tmp_path,
    initial_status,
):
    listing_calls = 0
    open_calls = 0

    def browser_runner(command, **_kwargs):
        nonlocal listing_calls, open_calls
        tail = command[3:]
        if tail[:1] == ["open"]:
            open_calls += 1
            payload = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            listing_calls += 1
            payload = (
                {"status": initial_status, "entries": []}
                if listing_calls == 1
                else {
                    "status": "ok",
                    "complete_scan": True,
                    "entries": _representative_subscription_entries(),
                }
            )
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        sleep=lambda _seconds: None,
    )

    listing = service._read_opencli_listing(session="ticket04")

    assert listing["complete_scan"] is True
    assert listing["recovery"]["attempts"] == 2
    assert listing["recovery"]["initial_failure"] == {
        "category": (
            "timeout" if initial_status == "share_list_timeout" else "incomplete_scan"
        ),
        "code": initial_status,
        "stage": "listing_validation",
    }
    assert listing_calls == 2
    assert open_calls == 2


def test_cursor_advances_only_after_complete_listing(tmp_path):
    calls = 0

    def browser_runner(command, **_kwargs):
        nonlocal calls
        tail = command[3:]
        if tail[:1] == ["open"]:
            payload = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"]:
            calls += 1
            payload = {"status": "share_list_invalid_json", "entries": []}
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        sleep=lambda _seconds: None,
    )

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service.poll_opencli(session="ticket04")

    assert captured.value.diagnostic_code == "share_list_invalid_json"
    assert calls == 2
    assert not service.manifest_path.exists()


def _pdf_entry(*, size: int = 4096) -> dict:
    return {
        "provider_file_id": "pdf-report",
        "path": "/彤商学院/报告/大摩拆解.pdf",
        "name": "大摩拆解.pdf",
        "is_dir": False,
        "size": size,
        "modified_at": int(NOW.timestamp()),
    }


def _captured_pdf(service: LvSubscriptionService, tmp_path: Path) -> tuple[str, Path]:
    update = service.observe_browser_listing([_pdf_entry()])["updates"][0]
    downloaded = tmp_path / "大摩拆解.pdf"
    payload = b"%PDF-1.7\n" + b"x" * (_pdf_entry()["size"] - 9)
    downloaded.write_bytes(payload)
    _capture_browser_download(service, update["identity"], downloaded)
    return update["identity"], downloaded


def test_transferred_artifact_paths_rebase_to_hash_bound_local_files(tmp_path):
    entry = _representative_subscription_entries()[0]
    payload = b"\x89PNG\r\n" + b"x" * (entry["size"] - 6)
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    update = service.observe_browser_listing([entry])["updates"][0]
    downloaded = tmp_path / entry["name"]
    downloaded.write_bytes(payload)
    _capture_browser_download(service, update["identity"], downloaded)
    ingest = service.ingest_browser_download(
        update["identity"],
        ocr_runner=lambda _path: {
            "engine": "test-local",
            "lines": [{
                "text": "迁移后的图片证据仍由原始哈希绑定。",
                "confidence": 0.99,
                "bounding_box": [0.1, 0.1, 0.8, 0.1],
            }],
        },
    )
    request = service.prepare_analysis_request(ingest)
    artifact_dir = Path(ingest["evidence_path"]).parent
    receipt_path = artifact_dir / "browser_download_receipt.json"
    ingest_path = artifact_dir / "ingest_result.json"
    request_path = Path(request["request_path"])
    remote_root = Path("/Users/bytedance/coding/xiaocao/output/live")

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["immutable_path"] = str(remote_root / Path(receipt["immutable_path"]).name)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    persisted_ingest = json.loads(ingest_path.read_text(encoding="utf-8"))
    for key in ("original_path", "evidence_path", "ocr_path"):
        persisted_ingest[key] = str(
            remote_root / Path(persisted_ingest[key]).name
        )
    ingest_path.write_text(json.dumps(persisted_ingest), encoding="utf-8")
    persisted_request = json.loads(request_path.read_text(encoding="utf-8"))
    persisted_request["evidence_path"] = str(remote_root / "evidence.txt")
    persisted_request["original_evidence_path"] = str(
        remote_root / "browser_original.png"
    )
    persisted_request["ocr_path"] = str(remote_root / "ocr.json")
    request_path.write_text(json.dumps(persisted_request), encoding="utf-8")

    completed = service._completed_browser_receipt(
        service._manifest_item(update["identity"])
    )
    replayed_ingest = service.ingest_browser_download(update["identity"])
    replayed_request = service.prepare_analysis_request(replayed_ingest)

    assert Path(completed["immutable_path"]).parent == artifact_dir
    assert Path(replayed_ingest["original_path"]).parent == artifact_dir
    assert Path(replayed_ingest["evidence_path"]).parent == artifact_dir
    assert Path(replayed_ingest["ocr_path"]).parent == artifact_dir
    assert Path(replayed_request["evidence_path"]).parent == artifact_dir
    assert Path(replayed_request["original_evidence_path"]).parent == artifact_dir
    assert Path(replayed_request["ocr_path"]).parent == artifact_dir


def test_small_pdf_is_discovered_hashed_and_text_extracted(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    identity, downloaded = _captured_pdf(service, tmp_path)

    ingest = service.ingest_browser_download(
        identity,
        pdf_text_extractor=lambda _path: {
            "engine": "test-local",
            "pages": [{
                "page": 1,
                "text": "大摩拆解报告包含足够长度的原生文本提取内容。",
                "has_visuals": False,
            }],
        },
        pdf_renderer=lambda *_args: (_ for _ in ()).throw(
            AssertionError("text-only PDF must not render")
        ),
    )

    assert ingest["media_type"] == "pdf"
    assert ingest["original_sha256"] == hashlib.sha256(
        downloaded.read_bytes()
    ).hexdigest()
    assert ingest["pdf_page_count"] == 1
    assert ingest["pdf_visual_pages"] == []
    coverage = json.loads(Path(ingest["pdf_coverage_path"]).read_text())
    assert coverage["pages"][0]["coverage_status"] == "covered"
    assert service.pending_items()[0]["stage"] == "ingested"


def test_scanned_pdf_renders_and_records_page_ocr_coverage(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    identity, _downloaded = _captured_pdf(service, tmp_path)

    def renderer(_pdf, output_dir, pages):
        assert pages == [1]
        output_dir.mkdir(parents=True)
        rendered = output_dir / "page-0001-1.png"
        rendered.write_bytes(b"png-page")
        return {1: rendered}

    ingest = service.ingest_browser_download(
        identity,
        pdf_text_extractor=lambda _path: {
            "engine": "test-local",
            "pages": [{"page": 1, "text": "", "has_visuals": True}],
        },
        pdf_renderer=renderer,
        ocr_runner=lambda _path: {
            "engine": "test-ocr",
            "lines": [{
                "text": "扫描页中的大摩拆解结论",
                "confidence": 0.99,
                "bounding_box": [0, 0, 1, 1],
            }],
        },
    )

    assert ingest["pdf_visual_pages"] == [1]
    coverage = json.loads(Path(ingest["pdf_coverage_path"]).read_text())
    page = coverage["pages"][0]
    assert page["coverage_status"] == "covered"
    assert len(page["rendered_sha256"]) == 64
    assert len(page["ocr_sha256"]) == 64


def test_pdf_replay_does_not_repeat_ingest_or_analysis_request(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    identity, _downloaded = _captured_pdf(service, tmp_path)
    extractor_calls = 0

    def extractor(_path):
        nonlocal extractor_calls
        extractor_calls += 1
        return {
            "engine": "test-local",
            "pages": [{
                "page": 1,
                "text": "重复执行仍然复用相同的不可变 PDF 文本证据。",
                "has_visuals": False,
            }],
        }

    first = service.ingest_browser_download(identity, pdf_text_extractor=extractor)
    second = service.ingest_browser_download(identity, pdf_text_extractor=extractor)
    first_request = service.prepare_analysis_request(first)
    second_request = service.prepare_analysis_request(second)

    assert extractor_calls == 1
    assert second["idempotent_replay"] is True
    assert second_request["idempotent_replay"] is True
    assert first_request["evidence_sha256"] == second_request["evidence_sha256"]


def test_unknown_and_oversized_pdf_fail_closed(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    oversized = _pdf_entry(size=50 * 1024 * 1024 + 1)

    assert service.observe_browser_listing([oversized]) is None
    assert service.pending_items() == []
    manifest_item = next(iter(service.status()["items"].values()))
    assert manifest_item["pause_reason"] == (
        "pdf_size_outside_small_file_boundary"
    )
    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service.claim_browser_download(manifest_item["identity"])
    assert captured.value.diagnostic_code == (
        "pdf_size_outside_small_file_boundary"
    )

    invalid_service = LvSubscriptionService(
        tmp_path / "invalid", now=lambda: NOW
    )
    invalid_identity, downloaded = _captured_pdf(invalid_service, tmp_path / "invalid")
    downloaded.write_bytes(b"not-a-pdf" + b"x" * (4096 - 9))
    receipt = Path(
        invalid_service._completed_browser_receipt(
            invalid_service._manifest_item(invalid_identity)
        )["immutable_path"]
    )
    receipt.write_bytes(downloaded.read_bytes())
    receipt_path = receipt.parent / "browser_download_receipt.json"
    value = json.loads(receipt_path.read_text())
    value["sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(value))
    with pytest.raises(EnrichmentDiagnosticError) as invalid:
        invalid_service.ingest_browser_download(invalid_identity)
    assert invalid.value.diagnostic_code == "pdf_invalid"


def test_metadata_sufficient_companion_skips_pdf_download_and_side_effects(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    base_time = int(NOW.timestamp())
    video = {
        "provider_file_id": "video-aug-3",
        "path": "/彤商学院/直播回放/2026年8月/8月3日 (1).mp4",
        "name": "8月3日 (1).mp4",
        "is_dir": False,
        "size": 5_508_885_608,
        "modified_at": base_time,
    }
    pdf = {
        "provider_file_id": "summary-aug-3",
        "path": "/彤商学院/直播回放/2026年8月/8月3日会员直播gpt总结.pdf",
        "name": "8月3日会员直播gpt总结.pdf",
        "is_dir": False,
        "size": 317_268,
        "modified_at": base_time + 3600,
    }
    update = service.observe_browser_listing([video, pdf])["updates"][0]
    transcript = tmp_path / "video-transcript.txt"
    transcript.write_text("完整逐字稿证据", encoding="utf-8")
    normalized_video = LvSubscriptionService._normalize_entry(video)
    transcript_sha = hashlib.sha256(transcript.read_bytes()).hexdigest()
    proof = service.metadata_companion_proof(
        update["identity"],
        complete_video_transcripts=[{
            **normalized_video,
            "provider_identity_sha256": normalized_video["identity"],
            "transcript_complete": True,
            "transcript_path": str(transcript),
            "transcript_sha256": transcript_sha,
        }],
    )

    assert proof is not None
    state = service.record_metadata_companion_suppression(
        update["identity"],
        proof=proof,
    )

    assert state["route"] == "companion_suppressed"
    assert state["acquisition_skipped"] is True
    assert state["business_effects"] == {
        "report": "not_created",
        "notification": "not_created",
        "book_kol_us": "not_created",
    }
    artifact_dir = service.output_dir / "artifacts" / update["version_key"]
    assert not (artifact_dir / "browser_download_claim.json").exists()
    assert not (artifact_dir / "browser_download_receipt.json").exists()
    assert not (artifact_dir / "ingest_result.json").exists()
    assert not (artifact_dir / "analysis_request.json").exists()
    assert service.pending_items() == []


def test_ambiguous_pdf_relation_creates_only_one_download_claim(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    report = _pdf_entry()
    update = service.observe_browser_listing([report])["updates"][0]

    assert service.metadata_companion_proof(
        update["identity"],
        complete_video_transcripts=[],
    ) is None
    first = service.claim_browser_download(update["identity"])
    second = service.claim_browser_download(update["identity"])

    assert first["claim_id"] == second["claim_id"]
    assert second["idempotent_replay"] is True
    claims = [
        json.loads(line)
        for line in service.events_path.read_text(encoding="utf-8").splitlines()
        if "subscription_browser_download_claimed" in line
    ]
    assert len(claims) == 1


def test_private_config_accepts_only_the_observed_root_hash_route(tmp_path):
    service = LvSubscriptionService(
        tmp_path / "out",
        share_url=(
            "https://pan.baidu.com/s/private-share-token"
            "#list/path=%2F"
        ),
        share_code="a1b2",
    )
    service._validate_private_config()

    wrong_route = LvSubscriptionService(
        tmp_path / "wrong",
        share_url=(
            "https://pan.baidu.com/s/private-share-token"
            "#list/path=%2Fother"
        ),
        share_code="a1b2",
    )
    with pytest.raises(EnrichmentError, match="share URL is invalid"):
        wrong_route._validate_private_config()


def test_opencli_download_claims_before_one_browser_trigger_and_replays(tmp_path):
    private_url = "https://pan.baidu.com/s/private-share-token"
    private_code = "a1b2"
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nbrowser-downloaded-real-shape")
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "123456789012345"
    entry["size"] = downloaded.stat().st_size
    commands: list[list[str]] = []
    download_operations: list[str] = []
    trigger_calls = 0
    wait_calls = 0

    def browser_runner(command, **_kwargs):
        nonlocal trigger_calls, wait_calls
        commands.append(command)
        tail = command[3:]
        if tail[:1] == ["open"]:
            payload = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            payload = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:1] == ["eval"] and "ticket04_provider_direct_link" in tail[1]:
            payload = {"status": "unsupported"}
        elif tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            claim_path = (
                tmp_path
                / "out"
                / "artifacts"
                / LvSubscriptionService._normalize_entry(entry)["version_key"]
                / "browser_download_claim.json"
            )
            assert json.loads(claim_path.read_text(encoding="utf-8"))[
                "status"
            ] == "claimed"
            payload = {
                "status": "download_confirmation_ready",
                "name": entry["name"],
            }
        elif tail[:1] == ["click"]:
            download_operations.append("trigger")
            trigger_calls += 1
            payload = {"clicked": True, "matches_n": 1}
        elif tail[:2] == ["wait", "download"]:
            download_operations.append("wait")
            wait_calls += 1
            payload = {
                "downloaded": True,
                "filename": str(downloaded),
                "state": "complete",
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url=private_url,
        share_code=private_code,
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]

    first = service.download_opencli(
        update["identity"],
        session="ticket04",
    )
    second = service.download_opencli(
        update["identity"],
        session="ticket04",
    )

    assert first["status"] == "completed"
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert trigger_calls == 1
    assert wait_calls == 1
    assert download_operations == ["trigger", "wait"]
    wait_index = next(
        index
        for index, command in enumerate(commands)
        if command[3:5] == ["wait", "download"]
    )
    trigger_index = next(
        index
        for index, command in enumerate(commands)
        if command[3:4] == ["eval"]
        and "ticket04_exact_ui_download" in command[4]
    )
    assert trigger_index < wait_index
    assert any(
        any("ticket04_exact_ui_download" in part for part in command)
        for command in commands
    )

    durable = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "out").rglob("*.json*")
    )
    assert private_url not in durable
    assert private_code not in durable


def test_provider_row_selection_does_not_treat_js_item_active_as_selected():
    script = lv_subscription._browser_download_script(
        expected_share_path="/s/private-share-token",
        expected_item_path="/彤商学院/报告/大摩拆解.pdf",
        expected_name="大摩拆解.pdf",
    )

    assert "!row.classList.contains('JS-item-active')" in script
    assert (
        "rows.filter(row => row.classList.contains('JS-item-active'))"
        not in script
    )
    assert "downloadControls[0].click()" not in script
    assert "data-xiaocao-download-open" in script


def test_download_control_uses_native_click_and_preserves_client_only_status(
    tmp_path,
):
    operations = []

    def runner(command, **_kwargs):
        tail = command[3:]
        if tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            payload = {"status": "download_control_ready"}
            operations.append("select")
        elif tail[:1] == ["click"]:
            payload = {"clicked": True, "matches_n": 1}
            operations.append("native_click")
        elif tail[:1] == ["eval"] and "ticket04_download_confirmation_readback" in tail[1]:
            payload = {"status": "provider_web_download_client_only"}
            operations.append("readback")
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        runner=runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
    )
    result = service._prepare_opencli_download_confirmation(
        {
            "path": "/彤商学院/报告/大摩拆解.pdf",
            "name": "大摩拆解.pdf",
        },
        session="ticket04",
        profile=None,
    )

    assert result["status"] == "provider_web_download_client_only"
    assert operations == ["select", "native_click", "readback"]


def test_owner_download_selection_binds_exact_fsid_name_and_checkbox_state():
    script = lv_subscription._owner_download_link_script(
        expected_provider_file_id="512980618612681",
        expected_name="大摩拆解.pdf",
        expected_size=768188,
    )

    assert "[data-id], [data-fsid]" in script
    assert "expectedProviderFileId" in script
    assert "rowName(row)" in script
    assert "aria-selected" in script
    assert "aria-checked" in script
    assert "selectedRows.length !== 1" in script
    assert "JS-item-active" not in script


def test_replayed_download_claim_reconciles_without_retriggering_browser(tmp_path):
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "123456789012345"
    trigger_calls = 0
    wait_calls = 0

    def browser_runner(command, **_kwargs):
        nonlocal trigger_calls, wait_calls
        tail = command[3:]
        if tail[:1] == ["open"]:
            payload = {"url": "redacted", "page": "page-1"}
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )
        if tail[:1] == ["eval"] and "/share/list" in tail[1]:
            payload = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )
        if tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            trigger_calls += 1
            raise AssertionError("a replayed claim must never retrigger download")
        if tail[:1] == ["eval"] and "blocked_download_frame_probe" in tail[1]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "status": "other_browser_error",
                    "error_code": "",
                }),
                stderr="",
            )
        if tail[:2] == ["wait", "download"]:
            wait_calls += 1
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps({"error": {"code": "download_not_seen"}}),
                stderr="",
            )
        if tail[:1] == ["eval"] and "blocked_download_frame_probe" in tail[1]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "status": "other_browser_error",
                    "error_code": "",
                }),
                stderr="",
            )
        raise AssertionError(command)

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        download_policy_configurer=lambda *_args: {
            "configured": True,
            "method": "Page.setDownloadBehavior",
            "command_ack": True,
        },
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]
    service.claim_browser_download(update["identity"])

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service.download_opencli(
            update["identity"],
            session="ticket04",
        )

    assert captured.value.diagnostic_category == "uncertain_state"
    assert captured.value.diagnostic_code == "download_not_seen"
    assert captured.value.diagnostic_stage == "browser_wait"
    assert captured.value.diagnostic_exit_code == 1
    assert trigger_calls == 0
    assert wait_calls == 1


def test_replayed_claim_reconciles_exact_native_save_history_without_click(tmp_path):
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    chrome_profile_dir = tmp_path / "Default"
    chrome_profile_dir.mkdir()
    downloaded = downloads_dir / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nnative-save-receipt")
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "123456789012345"
    entry["size"] = downloaded.stat().st_size
    commands = []

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=lambda command, **_kwargs: commands.append(command),
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        downloads_dir=downloads_dir,
        chrome_profile_dir=chrome_profile_dir,
    )
    update = service.observe_browser_listing([entry])["updates"][0]
    claim = service.claim_browser_download(update["identity"])
    service._opencli_listing = (
        "ticket04",
        None,
        {"status": "ok", "complete_scan": True, "entries": [entry]},
    )
    history = sqlite3.connect(chrome_profile_dir / "History")
    history.execute(
        """CREATE TABLE downloads (
          id INTEGER PRIMARY KEY,
          target_path TEXT,
          current_path TEXT,
          received_bytes INTEGER,
          total_bytes INTEGER,
          state INTEGER,
          interrupt_reason INTEGER,
          start_time INTEGER,
          end_time INTEGER
        )"""
    )
    chrome_epoch_us = 11_644_473_600 * 1_000_000
    claimed_us = int(datetime.fromisoformat(claim["claimed_at"]).timestamp() * 1_000_000)
    history.execute(
        "INSERT INTO downloads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            str(downloaded),
            str(downloaded),
            downloaded.stat().st_size,
            downloaded.stat().st_size,
            1,
            0,
            chrome_epoch_us + claimed_us + 1_000_000,
            chrome_epoch_us + claimed_us + 2_000_000,
        ),
    )
    history.commit()
    history.close()

    result = service.download_opencli(update["identity"], session="ticket04")

    assert result["status"] == "completed"
    assert result["sha256"] == hashlib.sha256(downloaded.read_bytes()).hexdigest()
    assert commands == []


class _FakeNativeSaveProcess:
    def __init__(self, first, final, *, completed_path=None, payload=b""):
        self.stdout = SimpleNamespace(
            readline=lambda: json.dumps(first) + "\n"
        )
        self.stderr = SimpleNamespace()
        self._final = final
        self._completed_path = completed_path
        self._payload = payload

    def communicate(self, timeout):
        assert timeout <= 35
        if self._completed_path is not None:
            self._completed_path.write_bytes(self._payload)
        return json.dumps(self._final) + "\n", ""

    def poll(self):
        return 0


def _native_save_service(tmp_path, monkeypatch, first, final, *, payload=b""):
    entry = _pdf_entry(size=len(payload) if payload else 768_188)
    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"clicked": True, "matches_n": 1}),
            stderr="",
        ),
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
    )
    update = service.observe_browser_listing([entry])["updates"][0]
    claim = service.claim_browser_download(update["identity"])
    item = service._manifest_item(update["identity"])
    destination = (
        service.download_inbox / item["version_key"] / item["name"]
    )

    def fake_popen(command, **_kwargs):
        assert command[-3:] == (
            item["name"],
            str(destination.resolve()),
            str(item["size"]),
        )
        return _FakeNativeSaveProcess(
            first,
            final,
            completed_path=(
                destination
                if final.get("status") == "completed"
                else None
            ),
            payload=payload,
        )

    monkeypatch.setattr(lv_subscription.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        lv_subscription.select,
        "select",
        lambda *_args, **_kwargs: ([object()], [], []),
    )
    monkeypatch.setattr(
        service,
        "_chrome_history_download_completed",
        lambda *_args, **_kwargs: True,
    )
    return service, item, claim


def test_automated_native_save_authorized_exact_pdf_completes(tmp_path, monkeypatch):
    payload = b"%PDF-" + b"x" * 4096
    service, item, claim = _native_save_service(
        tmp_path,
        monkeypatch,
        {"status": "ready", "accessibility_trusted": True},
        {"status": "completed", "actual_size": len(payload)},
        payload=payload,
    )

    result = service._automated_native_save_download(
        item,
        claim,
        session="ticket04",
        profile=None,
        confirmation_prepared=True,
    )

    assert result["acquisition_transport"] == "automated_native_save"
    assert result["actual_size"] == len(payload)
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()


def test_automated_native_save_untrusted_is_permission_diagnostic(
    tmp_path, monkeypatch
):
    service, item, claim = _native_save_service(
        tmp_path,
        monkeypatch,
        {"status": "accessibility_not_trusted", "accessibility_trusted": False},
        {},
    )

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service._automated_native_save_download(
            item,
            claim,
            session="ticket04",
            profile=None,
            confirmation_prepared=True,
        )

    assert captured.value.diagnostic_category == "permission_error"
    assert captured.value.diagnostic_code == "macos_accessibility_permission_required"
    assert captured.value.diagnostic_stage == "native_save_automation"


def test_automated_native_save_filename_mismatch_fails_closed(
    tmp_path, monkeypatch
):
    service, item, claim = _native_save_service(
        tmp_path,
        monkeypatch,
        {"status": "ready", "accessibility_trusted": True},
        {"status": "save_sheet_filename_mismatch"},
    )

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service._automated_native_save_download(
            item,
            claim,
            session="ticket04",
            profile=None,
            confirmation_prepared=True,
        )

    assert captured.value.diagnostic_category == "identity_error"
    assert captured.value.diagnostic_code == "save_sheet_filename_mismatch"
    assert not (
        service.download_inbox / item["version_key"] / item["name"]
    ).exists()


def test_replayed_claim_recovers_exact_blocked_download_frame_once(tmp_path):
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nblocked-frame-recovery")
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "123456789012345"
    entry["size"] = downloaded.stat().st_size
    waits = 0
    opens: list[str] = []
    trigger_calls = 0

    def browser_runner(command, **_kwargs):
        nonlocal waits, trigger_calls
        session = command[2]
        tail = command[3:]
        if tail[:1] == ["open"]:
            opens.append(session)
            payload = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            payload = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            trigger_calls += 1
            raise AssertionError("recovery must not replay the provider click")
        elif tail[:1] == ["eval"] and "blocked_download_frame_probe" in tail[1]:
            payload = {
                "status": "blocked_by_client",
                "error_code": "ERR_BLOCKED_BY_CLIENT",
            }
        elif tail[:1] == ["eval"] and "blocked_download_url_probe" in tail[1]:
            payload = {
                "status": "download_url_ready",
                "download_url": (
                    "https://d.pcs.baidu.com/rest/2.0/pcs/file?signed=evidence"
                ),
                "scheme": "https:",
                "host": "d.pcs.baidu.com",
                "path": "/rest/2.0/pcs/file",
                "provider_file_id": entry["provider_file_id"],
                "name": entry["name"],
                "size": entry["size"],
            }
        elif tail[:2] == ["wait", "download"]:
            waits += 1
            if waits == 1:
                return SimpleNamespace(
                    returncode=1,
                    stdout=json.dumps({"error": {"code": "download_not_seen"}}),
                    stderr="",
                )
            payload = {
                "downloaded": True,
                "filename": str(downloaded),
                "state": "complete",
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]
    service.claim_browser_download(update["identity"])

    result = service.download_opencli(update["identity"], session="ticket04")

    assert result["status"] == "completed"
    assert trigger_calls == 0
    assert waits == 2
    assert opens == ["ticket04", "ticket04"]


def test_replayed_claim_reports_missing_blocked_download_frame_exactly(tmp_path):
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "123456789012345"
    waits = 0

    def browser_runner(command, **_kwargs):
        nonlocal waits
        tail = command[3:]
        if tail[:1] == ["open"]:
            payload = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "ticket04_provider_direct_link" in tail[1]:
            payload = {
                "status": "provider_error",
                "provider_errno": 2,
            }
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            payload = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:2] == ["wait", "download"]:
            waits += 1
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps({"error": {"code": "download_not_seen"}}),
                stderr="",
            )
        elif tail[:1] == ["eval"] and "blocked_download_frame_probe" in tail[1]:
            payload = {
                "status": "blocked_by_client",
                "error_code": "ERR_BLOCKED_BY_CLIENT",
            }
        elif tail[:1] == ["eval"] and "blocked_download_url_probe" in tail[1]:
            payload = {
                "status": "download_url_missing",
                "frame_count": 0,
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]
    service.claim_browser_download(update["identity"])

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service.download_opencli(update["identity"], session="ticket04")

    assert captured.value.diagnostic_code == "provider_download_filtered"
    assert captured.value.diagnostic_stage == "provider_download_link"
    assert waits == 1


def test_session_download_policy_ack_uses_controlled_inbox_without_profile_edit(
    tmp_path,
):
    calls = []

    def configure(session, profile, inbox):
        calls.append((session, profile, inbox))
        return {
            "configured": True,
            "method": "Page.setDownloadBehavior",
            "command_ack": True,
        }

    service = LvSubscriptionService(
        tmp_path / "out",
        download_policy_configurer=configure,
    )

    result = service.configure_opencli_download_policy(
        session="ticket04",
        profile="dedicated-context",
    )

    inbox = tmp_path / "out" / "download_inbox"
    assert calls == [("ticket04", "dedicated-context", inbox.resolve())]
    assert result == {
        "configured": True,
        "method": "Page.setDownloadBehavior",
        "command_ack": True,
        "session": "ticket04",
        "profile": "dedicated-context",
        "inbox": str(inbox.resolve()),
        "persistent_profile_mutated": False,
    }
    persisted = json.loads(
        (tmp_path / "out" / "download_policy.json").read_text(encoding="utf-8")
    )
    assert persisted == result
    assert not (tmp_path / "Default" / "Preferences").exists()


def test_existing_pdf_claim_uses_direct_page_api_without_second_ui_trigger(
    tmp_path,
):
    payload = b"%PDF-1.7\n" + b"x" * 2048
    entry = _pdf_entry(size=len(payload))
    entry["provider_file_id"] = "987654321012345"
    trigger_calls = 0
    direct_calls = []

    def browser_runner(command, **_kwargs):
        nonlocal trigger_calls
        tail = command[3:]
        if tail[:1] == ["open"]:
            result = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "ticket04_provider_direct_link" in tail[1]:
            result = {
                "status": "download_link_ready",
                "download_url": (
                    "https://d.pcs.baidu.com/rest/2.0/pcs/file?"
                    "signed=credential-redacted-from-ledger"
                ),
                "scheme": "https:",
                "host": "d.pcs.baidu.com",
                "path": "/rest/2.0/pcs/file",
                "provider_file_id": entry["provider_file_id"],
            }
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            result = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:2] == ["wait", "download"]:
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps({"error": {"code": "download_not_seen"}}),
                stderr="",
            )
        elif tail[:1] == ["eval"] and "blocked_download_frame_probe" in tail[1]:
            result = {
                "status": "blocked_by_client",
                "error_code": "ERR_BLOCKED_BY_CLIENT",
            }
        elif tail[:1] == ["eval"] and "blocked_download_url_probe" in tail[1]:
            result = {"status": "download_url_missing", "frame_count": 0}
        elif tail[:1] in (["click"],):
            trigger_calls += 1
            raise AssertionError("existing claim must not replay UI download")
        elif tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            trigger_calls += 1
            raise AssertionError("existing claim must not replay UI download")
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(result),
            stderr="",
        )

    def direct_fetch(url, destination, expected_size, media_type):
        direct_calls.append((url, destination, expected_size, media_type))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return {
            "path": str(destination),
            "actual_size": len(payload),
            "content_type": "application/pdf",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        download_policy_configurer=lambda *_args: {
            "configured": False,
            "code": "opencli_cdp_method_not_permitted",
        },
        direct_download_fetcher=direct_fetch,
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]
    claim = service.claim_browser_download(update["identity"])

    result = service.download_opencli(update["identity"], session="ticket04")

    assert claim["status"] == "claimed"
    assert result["status"] == "completed"
    assert result["acquisition_transport"] == "provider_direct_small_file"
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert trigger_calls == 0
    assert len(direct_calls) == 1
    assert direct_calls[0][1] == (
        tmp_path
        / "out"
        / "download_inbox"
        / update["version_key"]
        / "大摩拆解.pdf"
    )
    durable = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "out").rglob("*.json*")
    )
    assert "credential-redacted-from-ledger" not in durable


def test_existing_image_claim_uses_direct_page_api_without_second_ui_trigger(
    tmp_path,
):
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * 2048
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "987654321012345"
    entry["size"] = len(payload)
    trigger_calls = 0
    direct_calls = []

    def browser_runner(command, **_kwargs):
        nonlocal trigger_calls
        tail = command[3:]
        if tail[:1] == ["open"]:
            result = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "ticket04_provider_direct_link" in tail[1]:
            result = {
                "status": "download_link_ready",
                "download_url": (
                    "https://d.pcs.baidu.com/rest/2.0/pcs/file?"
                    "signed=credential-redacted-from-ledger"
                ),
                "scheme": "https:",
                "host": "d.pcs.baidu.com",
                "path": "/rest/2.0/pcs/file",
                "provider_file_id": entry["provider_file_id"],
            }
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            result = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:2] == ["wait", "download"]:
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps({"error": {"code": "download_not_seen"}}),
                stderr="",
            )
        elif tail[:1] == ["eval"] and "blocked_download_frame_probe" in tail[1]:
            result = {
                "status": "blocked_by_client",
                "error_code": "ERR_BLOCKED_BY_CLIENT",
            }
        elif tail[:1] == ["eval"] and "blocked_download_url_probe" in tail[1]:
            result = {"status": "download_url_missing", "frame_count": 0}
        elif tail[:1] in (["click"],):
            trigger_calls += 1
            raise AssertionError("existing claim must not replay UI download")
        elif tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            trigger_calls += 1
            raise AssertionError("existing claim must not replay UI download")
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(result),
            stderr="",
        )

    def direct_fetch(url, destination, expected_size, media_type):
        direct_calls.append((url, destination, expected_size, media_type))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return {
            "path": str(destination),
            "actual_size": len(payload),
            "content_type": "image/png",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        download_policy_configurer=lambda *_args: {
            "configured": False,
            "code": "opencli_cdp_method_not_permitted",
        },
        direct_download_fetcher=direct_fetch,
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]
    claim = service.claim_browser_download(update["identity"])

    result = service.download_opencli(update["identity"], session="ticket04")

    assert claim["status"] == "claimed"
    assert result["status"] == "completed"
    assert result["acquisition_transport"] == "browser_download"
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert trigger_calls == 0
    assert len(direct_calls) == 1
    assert direct_calls[0][2:] == (len(payload), "image")
    durable = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "out").rglob("*.json*")
    )
    assert "credential-redacted-from-ledger" not in durable


def test_image_recovery_provider_probe_is_versioned_opencli_template():
    source = lv_subscription._provider_direct_link_script(
        expected_share_path="/s/private-share-token",
        expected_provider_file_id="123456789012345",
        expected_item_path="/folder/12.png",
        expected_name="12.png",
        expected_size=42,
    )

    assert "baidu-netdisk/probe-download" in source
    assert "const template_version = 1" in source
    assert "__EXPECTED_" not in source
    assert "performance.getEntriesByType('resource')" in source
    assert "resourceValue(['sekey'])" in source
    assert "if (sign) query.set('sign', sign)" in source
    assert "provider_filtered" in source
    assert "部分文件违规，已被过滤" in source
    assert "expectedProviderFileId = \"123456789012345\"" in source
    assert "12.png" in source


def test_existing_pdf_claim_intercepts_one_frontend_signed_link_after_errno_2(
    tmp_path,
):
    payload = b"%PDF-1.7\n" + b"d" * 4096
    entry = _pdf_entry(size=len(payload))
    entry["provider_file_id"] = "987654321012345"
    click_calls = 0
    claim_calls = 0
    direct_calls = []

    def browser_runner(command, **_kwargs):
        nonlocal click_calls
        tail = command[3:]
        if tail[:1] == ["open"]:
            result = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "ticket04_provider_direct_link" in tail[1]:
            result = {
                "status": "provider_error",
                "provider_errno": 2,
                "http_status": 200,
            }
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            result = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:1] == ["eval"] and "ticket04_target_route_readback" in tail[1]:
            result = {"status": "target_route_ready"}
        elif tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            result = {
                "status": "download_confirmation_ready",
                "name": entry["name"],
            }
        elif tail[:1] == ["eval"] and "ticket04_signed_link_intercept_and_trigger" in tail[1]:
            click_calls += 1
            result = {
                "status": "download_link_ready",
                "download_url": (
                    "https://d.pcs.baidu.com/file/signed-evidence?"
                    "credential=must-not-persist"
                ),
                "scheme": "https:",
                "host": "d.pcs.baidu.com",
                "path": "/file/signed-evidence",
                "provider_file_id": entry["provider_file_id"],
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(result),
            stderr="",
        )

    def direct_fetch(url, destination, expected_size, media_type):
        direct_calls.append((url, destination, expected_size, media_type))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return {
            "path": str(destination),
            "actual_size": len(payload),
            "content_type": "application/pdf",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        download_policy_configurer=lambda *_args: {
            "configured": False,
            "code": "opencli_cdp_method_not_permitted",
        },
        direct_download_fetcher=direct_fetch,
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]
    original_claim = service.claim_browser_download

    def counted_claim(identity):
        nonlocal claim_calls
        claim_calls += 1
        return original_claim(identity)

    service.claim_browser_download = counted_claim
    first = service.claim_browser_download(update["identity"])

    result = service.download_opencli(update["identity"], session="ticket04")

    assert first["status"] == "claimed"
    assert result["status"] == "completed"
    assert result["acquisition_transport"] == (
        "provider_frontend_intercepted_small_file"
    )
    assert click_calls == 1
    assert claim_calls == 2
    claims = [
        json.loads(line)
        for line in service.events_path.read_text(encoding="utf-8").splitlines()
        if "subscription_browser_download_claimed" in line
    ]
    assert len(claims) == 1
    assert len(direct_calls) == 1
    durable = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "out").rglob("*.json*")
    )
    assert "credential=must-not-persist" not in durable


def _owner_ready(item, *, transfer_performed):
    destination = (
        f"/xiaocao/lv_subscription/{item['version_key']}/{item['name']}"
    )
    return {
        "status": "owner_ready",
        "exact_match_count": 1,
        "transfer_performed": transfer_performed,
        "owner_provider_file_id": "512980618612681",
        "owner_path": destination,
        "name": item["name"],
        "size": item["size"],
        "modified_at": int(NOW.timestamp()),
        "directory_receipts": [],
    }


def test_owner_cloud_zero_match_transfers_once_and_streams_with_httponly_cookie(
    tmp_path,
):
    payload = b"%PDF-1.7\n" + b"o" * 4096
    entry = _pdf_entry(size=len(payload))
    entry["provider_file_id"] = "162571713959724"
    transfer_calls = []
    link_calls = []
    fetch_calls = []
    secret_url = (
        "https://d.pcs.baidu.com/file/owner-evidence?"
        "signed=must-never-persist"
    )
    secret_cookie = "httponly-cookie-must-never-persist"

    def owner_cloud(item, claim, session, profile):
        transfer_calls.append((
            item["provider_file_id"],
            claim["parent_acquisition_claim_id"],
            session,
            profile,
        ))
        return _owner_ready(item, transfer_performed=True)

    def owner_link(item, owner, session, profile):
        link_calls.append((owner["owner_provider_file_id"], session, profile))
        return {
            "status": "download_link_ready",
            "download_url": secret_url,
            "provider_file_id": owner["owner_provider_file_id"],
            "name": item["name"],
            "size": item["size"],
        }

    def owner_fetch(url, cookies, destination, expected_size):
        fetch_calls.append((url, [dict(row) for row in cookies], expected_size))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return {
            "path": str(destination),
            "actual_size": len(payload),
            "content_type": "application/pdf",
            "http_status": 200,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        download_policy_configurer=lambda *_args: {
            "configured": False,
            "code": "opencli_cdp_method_not_permitted",
        },
        owner_cloud_operator=owner_cloud,
        owner_download_link_reader=owner_link,
        opencli_cookie_reader=lambda *_args: [{
            "name": "BDUSS",
            "value": secret_cookie,
            "domain": ".baidu.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
        }],
        owner_download_fetcher=owner_fetch,
    )
    update = service.observe_browser_listing([entry])["updates"][0]
    service._opencli_listing = (
        "ticket04",
        None,
        {"status": "ok", "complete_scan": True, "entries": [entry]},
    )
    claim = service.claim_browser_download(update["identity"])
    service._provider_direct_download = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        EnrichmentDiagnosticError(
            "share direct unavailable",
            category="provider_error",
            code="provider_download_link_errno_2",
            stage="provider_download_link",
        )
    )
    service._provider_frontend_intercepted_download = (
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            EnrichmentDiagnosticError(
                "provider requires desktop client",
                category="provider_error",
                code="provider_web_download_client_only",
                stage="provider_download_link",
            )
        )
    )

    first = service.download_opencli(update["identity"], session="ticket04")
    second = service.download_opencli(update["identity"], session="ticket04")

    assert first["status"] == "completed"
    assert first["acquisition_transport"] == "owner_cloud_opencli_cookie_stream"
    assert first["claim_id"] == claim["claim_id"]
    assert first["sha256"] == hashlib.sha256(payload).hexdigest()
    assert second["idempotent_replay"] is True
    assert len(transfer_calls) == 1
    assert transfer_calls[0][1] == claim["claim_id"]
    assert len(link_calls) == 1
    assert len(fetch_calls) == 1
    assert fetch_calls[0][0] == secret_url
    assert fetch_calls[0][1][0]["httpOnly"] is True
    claims = [
        json.loads(line)
        for line in service.events_path.read_text(encoding="utf-8").splitlines()
        if "subscription_browser_download_claimed" in line
    ]
    assert len(claims) == 1
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "out").rglob("*.json*")
    )
    assert "must-never-persist" not in persisted
    assert "BDUSS" not in persisted


def test_default_owner_stream_keeps_signed_url_and_httponly_cookie_in_process(
    tmp_path, monkeypatch
):
    payload = b"%PDF-1.7\n" + b"s" * 1024
    entry = _pdf_entry(size=len(payload))
    entry["provider_file_id"] = "162571713959724"
    service = LvSubscriptionService(
        tmp_path / "out",
        opencli_command=("opencli",),
    )
    service._opencli_json = lambda *_args, **_kwargs: {"status": "opened"}
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    opencli = fake_bin / "opencli"
    node = fake_bin / "node"
    opencli.write_text("", encoding="utf-8")
    node.write_text("", encoding="utf-8")
    page_module = fake_bin / "browser" / "page.js"
    page_module.parent.mkdir()
    page_module.write_text("", encoding="utf-8")

    def which(name):
        return str(opencli if name == "opencli" else node if name == "node" else "")

    def run(command, **_kwargs):
        assert "Network.getAllCookies" in command[3]
        assert "httpOnly" in command[3]
        request = json.loads(command[-1])
        assert "signed=" not in command[-1]
        assert "BDUSS" not in command[-1]
        destination = Path(request["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "status": "completed",
                "path": str(destination),
                "actual_size": len(payload),
                "content_type": "application/pdf",
                "http_status": 200,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }),
            stderr="",
        )

    monkeypatch.setattr(lv_subscription.shutil, "which", which)
    monkeypatch.setattr(lv_subscription.subprocess, "run", run)
    item = {
        "identity": "a" * 64,
        "version_key": "b" * 64,
        "provider_file_id": entry["provider_file_id"],
        "path": entry["path"],
        "name": entry["name"],
        "size": entry["size"],
        "media_type": "pdf",
    }
    owner = _owner_ready(item, transfer_performed=False)
    destination = service.download_inbox / item["version_key"] / item["name"]

    receipt = service._default_owner_authenticated_streamer(
        item, owner, "ticket04", None, destination
    )

    assert receipt["status"] == "completed"
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()


def test_owner_cloud_one_exact_match_is_idempotent_without_transfer(tmp_path):
    entry = _pdf_entry()
    entry["provider_file_id"] = "162571713959724"
    calls = 0

    def owner_cloud(item, _claim, _session, _profile):
        nonlocal calls
        calls += 1
        return _owner_ready(item, transfer_performed=False)

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        owner_cloud_operator=owner_cloud,
    )
    update = service.observe_browser_listing([entry])["updates"][0]
    parent = service.claim_browser_download(update["identity"])
    item = {
        **service._manifest_item(update["identity"]),
        "provider_file_id": entry["provider_file_id"],
    }

    first = service._owner_cloud_transfer(
        item, parent, session="ticket04", profile=None
    )
    second = service._owner_cloud_transfer(
        item, parent, session="ticket04", profile=None
    )

    assert first["transfer_performed"] is False
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert calls == 1


def test_owner_cloud_duplicate_exact_matches_fail_closed(tmp_path):
    entry = _pdf_entry()
    entry["provider_file_id"] = "162571713959724"
    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        owner_cloud_operator=lambda *_args: {
            "status": "owner_duplicate_matches",
            "exact_match_count": 2,
        },
    )
    update = service.observe_browser_listing([entry])["updates"][0]
    parent = service.claim_browser_download(update["identity"])
    item = {
        **service._manifest_item(update["identity"]),
        "provider_file_id": entry["provider_file_id"],
    }

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service._owner_cloud_transfer(
            item, parent, session="ticket04", profile=None
        )

    assert captured.value.diagnostic_category == "identity_error"
    assert captured.value.diagnostic_code == "owner_cloud_duplicate_matches"
    assert captured.value.diagnostic_stage == "owner_cloud_transfer"


def test_owner_cloud_fallback_rejects_video_before_any_transfer(tmp_path):
    calls = 0

    def owner_cloud(*_args):
        nonlocal calls
        calls += 1
        return {}

    service = LvSubscriptionService(
        tmp_path / "out",
        owner_cloud_operator=owner_cloud,
    )
    item = {
        "identity": "a" * 64,
        "version_key": "b" * 64,
        "provider_file_id": "162571713959724",
        "path": "/video.mp4",
        "name": "video.mp4",
        "size": 4096,
        "media_type": "video",
    }
    claim = {"claim_id": "c" * 64}

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service._owner_cloud_transfer(
            item, claim, session="ticket04", profile=None
        )

    assert captured.value.diagnostic_code == "owner_cloud_media_not_allowed"
    assert calls == 0


@pytest.mark.parametrize(
    ("provider_status", "category", "code", "stage"),
    [
        (
            "auth_required",
            "authentication_error",
            "provider_authentication_required",
            "browser_download_authorization",
        ),
        (
            "captcha_required",
            "authentication_error",
            "provider_captcha_required",
            "browser_download_authorization",
        ),
        (
            "provider_error",
            "provider_error",
            "provider_download_link_errno_2",
            "provider_download_link",
        ),
    ],
)
def test_direct_pdf_api_preserves_auth_captcha_and_provider_diagnostics(
    tmp_path,
    provider_status,
    category,
    code,
    stage,
):
    service = LvSubscriptionService(tmp_path / "out")
    service._opencli_json = lambda *_args, **_kwargs: {
        "status": provider_status,
        "provider_errno": 0 if provider_status != "provider_error" else 2,
    }
    item = {
        "identity": "a" * 64,
        "version_key": "b" * 64,
        "provider_file_id": "987654321012345",
        "path": "/彤商学院/报告/大摩拆解.pdf",
        "name": "大摩拆解.pdf",
        "size": 4096,
        "media_type": "pdf",
    }

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service._provider_direct_download(
            item,
            session="ticket04",
            profile="dedicated-context",
        )

    assert captured.value.diagnostic_category == category
    assert captured.value.diagnostic_code == code
    assert captured.value.diagnostic_stage == stage


def test_direct_image_api_maps_provider_errno_2_to_filtered_media(tmp_path):
    service = LvSubscriptionService(tmp_path / "out")
    service._opencli_json = lambda *_args, **_kwargs: {
        "status": "provider_error",
        "provider_errno": 2,
    }
    item = {
        "identity": "a" * 64,
        "version_key": "b" * 64,
        "provider_file_id": "987654321012345",
        "path": "/彤商学院/图片/170057.png",
        "name": "170057.png",
        "size": 4096,
        "media_type": "image",
    }

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service._provider_direct_download(
            item,
            session="ticket04",
            profile="dedicated-context",
        )

    assert captured.value.diagnostic_category == "provider_error"
    assert captured.value.diagnostic_code == "provider_download_filtered"
    assert captured.value.diagnostic_stage == "provider_download_link"


def test_new_image_claim_uses_single_frontend_intercept_when_provider_filters_direct_api(
    tmp_path,
):
    payload = b"\x89PNG\r\n\x1a\n" + b"i" * 1024
    entry = {
        **_representative_subscription_entries()[0],
        "size": len(payload),
    }
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    update = service.observe_browser_listing([entry])["updates"][0]
    service._opencli_listing = (
        "ticket04",
        None,
        {"status": "ok", "complete_scan": True, "entries": [entry]},
    )
    direct_calls = 0
    frontend_calls = 0

    def filtered(*_args, **_kwargs):
        nonlocal direct_calls
        direct_calls += 1
        raise EnrichmentDiagnosticError(
            "provider filtered the direct image link",
            category="provider_error",
            code="provider_download_filtered",
            stage="provider_download_link",
        )

    def frontend(item, **_kwargs):
        nonlocal frontend_calls
        frontend_calls += 1
        destination = (
            service.download_inbox
            / item["version_key"]
            / item["name"]
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return {
            "path": str(destination),
            "actual_size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_type": "image/png",
            "acquisition_transport": (
                "provider_frontend_intercepted_small_file"
            ),
        }

    service._provider_direct_download = filtered
    service._provider_frontend_intercepted_download = frontend
    service._prepare_opencli_download_confirmation = lambda *_args, **_kwargs: (
        pytest.fail("image recovery must not dispatch a separate first click")
    )

    result = service.download_opencli(update["identity"], session="ticket04")

    assert result["status"] == "completed"
    assert result["acquisition_transport"] == (
        "provider_frontend_intercepted_small_file"
    )
    assert direct_calls == 1
    assert frontend_calls == 1


def test_one_poll_listing_is_reused_for_all_claim_reconciliations(tmp_path):
    entries = [
        {
            **_representative_subscription_entries()[index - 1],
            "provider_file_id": f"image-{index}",
        }
        for index in (1, 2)
    ]
    listing_calls = 0
    wait_calls = 0

    def browser_runner(command, **_kwargs):
        nonlocal listing_calls, wait_calls
        tail = command[3:]
        if tail[:1] == ["open"]:
            payload = {"url": "redacted", "page": "page-1"}
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )
        if tail[:1] == ["eval"] and "/share/list" in tail[1]:
            listing_calls += 1
            payload = {
                "status": "ok",
                "complete_scan": True,
                "entries": entries,
            }
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )
        if tail[:2] == ["wait", "download"]:
            wait_calls += 1
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps({"error": {"code": "download_not_seen"}}),
                stderr="",
            )
        if tail[:1] == ["eval"] and "blocked_download_frame_probe" in tail[1]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "status": "other_browser_error",
                    "error_code": "",
                }),
                stderr="",
            )
        raise AssertionError(command)

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
        download_policy_configurer=lambda *_args: {
            "configured": True,
            "method": "Page.setDownloadBehavior",
            "command_ack": True,
        },
    )
    updates = service.poll_opencli(session="ticket04")["updates"]
    for update in updates:
        service.claim_browser_download(update["identity"])

    for update in updates:
        with pytest.raises(EnrichmentError):
            service.download_opencli(
                update["identity"],
                session="ticket04",
            )

    assert listing_calls == 1
    assert wait_calls == 2


def test_expired_share_is_a_structured_user_blocker(tmp_path):
    def browser_runner(command, **_kwargs):
        tail = command[3:]
        payload = (
            {"url": "redacted", "page": "page-1"}
            if tail[:1] == ["open"]
            else {"status": "share_expired", "entries": []}
        )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
    )

    with pytest.raises(EnrichmentError, match="share is expired"):
        service.poll_opencli(session="ticket04")

    assert not (tmp_path / "out" / "manifest.json").exists()


def test_listing_eval_timeout_exposes_safe_operation_diagnostic(tmp_path):
    def browser_runner(command, **_kwargs):
        if command[3:4] == ["open"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"url": "redacted", "page": "page-1"}),
                stderr="",
            )
        raise subprocess.TimeoutExpired(command, 120)

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
    )

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        service.poll_opencli(session="ticket04")

    assert str(captured.value) == "subscription browser command timed out"
    assert captured.value.diagnostic_category == "timeout"
    assert captured.value.diagnostic_code == "opencli_timeout"
    assert captured.value.diagnostic_stage == "browser_eval"
    assert not (tmp_path / "out" / "manifest.json").exists()


def test_explicit_pretrigger_browser_failure_can_resume_safely(tmp_path):
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nbrowser-downloaded-real-shape")
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "123456789012345"
    entry["size"] = downloaded.stat().st_size
    trigger_attempts = 0

    def browser_runner(command, **_kwargs):
        nonlocal trigger_attempts
        tail = command[3:]
        if tail[:1] == ["open"]:
            payload = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            payload = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:1] == ["eval"] and "ticket04_provider_direct_link" in tail[1]:
            payload = {"status": "unsupported"}
        elif tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            trigger_attempts += 1
            payload = (
                {"status": "download_control_ambiguous"}
                if trigger_attempts == 1
                else {
                    "status": "download_confirmation_ready",
                    "name": entry["name"],
                }
            )
        elif tail[:1] == ["click"]:
            payload = {"clicked": True, "matches_n": 1}
        elif tail[:2] == ["wait", "download"]:
            payload = {
                "downloaded": True,
                "filename": str(downloaded),
                "state": "complete",
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "out",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url="https://pan.baidu.com/s/private-share-token",
        share_code="a1b2",
    )
    update = service.poll_opencli(session="ticket04")["updates"][0]

    with pytest.raises(EnrichmentError, match="was not triggered"):
        service.download_opencli(
            update["identity"],
            session="ticket04",
        )

    claim_path = next(
        (tmp_path / "out").rglob("browser_download_claim.json")
    )
    failed = json.loads(claim_path.read_text(encoding="utf-8"))
    assert failed["status"] == "failed_before_trigger"
    assert failed["failure_reason"] == "download_control_ambiguous"

    completed = service.download_opencli(
        update["identity"],
        session="ticket04",
    )

    assert completed["status"] == "completed"
    assert trigger_attempts == 2
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["attempt"] == 2


def test_poll_cli_prints_updates_once_then_no_update_is_silent(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    opencli = fake_bin / "opencli"
    listing = {
        "status": "ok",
        "complete_scan": True,
        "entries": _representative_subscription_entries(),
    }
    opencli.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "payload = {'url': 'redacted', 'page': 'page-1'} "
        "if 'open' in sys.argv else "
        + repr(listing)
        + "\n"
        "print(json.dumps(payload, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    opencli.chmod(0o755)
    config = tmp_path / "xiaocao.yaml"
    config.write_text(
        "kol_intelligence:\n"
        "  lv_xiaotong:\n"
        "    subscription_share_url: https://pan.baidu.com/s/test-private\n"
        "    subscription_share_code: a1b2\n",
        encoding="utf-8",
    )
    output = tmp_path / "out"
    command = [
        sys.executable,
        "scripts/kol_lv_subscription.py",
        "poll",
        "--config",
        str(config),
        "--output-dir",
        str(output),
        "--opencli-session",
        "ticket04-cli",
    ]
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": "src",
    }

    first = subprocess.run(
        command,
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        command,
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0
    assert json.loads(first.stdout)["event"] == "subscription_updates_discovered"
    assert second.returncode == 0
    assert second.stdout == ""
    assert len((output / "events.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_unclaimed_same_name_file_cannot_impersonate_browser_evidence(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nbrowser-event-bytes")
    image_entry = _representative_subscription_entries()[0]
    image_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([image_entry])["updates"][0]

    with pytest.raises(EnrichmentError, match="browser download receipt"):
        service.ingest_browser_download(update["identity"])

    claim = service.claim_browser_download(update["identity"])
    first_receipt = service.complete_browser_download(
        update["identity"],
        downloaded,
        claim_id=claim["claim_id"],
    )
    second_receipt = service.complete_browser_download(
        update["identity"],
        downloaded,
        claim_id=claim["claim_id"],
    )
    downloaded.write_bytes(b"\x89PNG\r\nsubstituted-after-browser-event")

    evidence = service.ingest_browser_download(
        update["identity"],
        ocr_runner=lambda path: {
            "engine": "macos_vision",
            "lines": [
                {
                    "text": (
                        "浏览器事件证据"
                        if path.read_bytes() == b"\x89PNG\r\nbrowser-event-bytes"
                        else "错误文件"
                    ),
                    "confidence": 0.99,
                    "bounding_box": [0.1, 0.7, 0.8, 0.1],
                }
            ],
        },
    )

    assert first_receipt["idempotent_replay"] is False
    assert second_receipt["idempotent_replay"] is True
    assert Path(evidence["evidence_path"]).read_text(encoding="utf-8") == (
        "浏览器事件证据\n"
    )


def test_image_ingest_preserves_original_surfaces_ambiguity_and_reuses_ocr(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nreal-subscription-image")
    image_entry = _representative_subscription_entries()[0]
    image_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([image_entry])["updates"][0]
    receipt = _capture_browser_download(service, update["identity"], downloaded)
    ocr_calls = 0

    def vision_ocr(path):
        nonlocal ocr_calls
        ocr_calls += 1
        assert path.read_bytes() == downloaded.read_bytes()
        return {
            "engine": "macos_vision",
            "lines": [
                {
                    "text": "下周先观察市场能否放量",
                    "confidence": 0.98,
                    "bounding_box": [0.1, 0.7, 0.8, 0.1],
                },
                {
                    "text": "疑似：纳指?仓",
                    "confidence": 0.61,
                    "bounding_box": [0.1, 0.5, 0.5, 0.1],
                },
            ],
        }

    first = service.ingest_browser_download(
        update["identity"],
        ocr_runner=vision_ocr,
    )
    second = service.ingest_browser_download(
        update["identity"],
        ocr_runner=vision_ocr,
    )

    assert first["media_type"] == "image"
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert ocr_calls == 1
    assert Path(receipt["immutable_path"]).read_bytes() == downloaded.read_bytes()
    assert Path(first["original_path"]).read_bytes() == downloaded.read_bytes()
    assert "下周先观察市场能否放量" in Path(first["evidence_path"]).read_text(
        encoding="utf-8"
    )
    assert first["ambiguities"] == [
        {
            "text": "疑似：纳指?仓",
            "confidence": 0.61,
            "bounding_box": [0.1, 0.5, 0.5, 0.1],
            "reasons": ["low_confidence", "uncertain_glyph"],
        }
    ]
    assert Path(first["ocr_path"]).is_file()


def test_overlapping_image_ingest_runs_ocr_once(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nreal-subscription-image")
    image_entry = _representative_subscription_entries()[0]
    image_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([image_entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)
    started = threading.Event()
    release = threading.Event()
    ocr_calls = 0

    def vision_ocr(_path):
        nonlocal ocr_calls
        ocr_calls += 1
        started.set()
        assert release.wait(timeout=5)
        return {
            "engine": "macos_vision",
            "lines": [
                {
                    "text": "市场先观察量能",
                    "confidence": 0.99,
                    "bounding_box": [0.1, 0.7, 0.8, 0.1],
                }
            ],
        }

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            service.ingest_browser_download,
            update["identity"],
            ocr_runner=vision_ocr,
        )
        assert started.wait(timeout=5)
        second = pool.submit(
            service.ingest_browser_download,
            update["identity"],
            ocr_runner=vision_ocr,
        )
        release.set()
        results = [first.result(timeout=5), second.result(timeout=5)]

    assert ocr_calls == 1
    assert sorted(row["idempotent_replay"] for row in results) == [False, True]


def test_native_text_bypasses_ocr_and_keeps_source_author_and_time(tmp_path):
    service = LvSubscriptionService(tmp_path / "out", now=lambda: NOW)
    downloaded = tmp_path / "盘后.txt"
    downloaded.write_text(
        "今天市场缩量，下一交易日先看成交额是否恢复。",
        encoding="utf-8",
    )
    text_entry = _representative_subscription_entries()[1]
    text_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([text_entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)

    result = service.ingest_browser_download(
        update["identity"],
        ocr_runner=lambda _path: (_ for _ in ()).throw(
            AssertionError("native text must bypass OCR")
        ),
    )

    assert result["source"] == "baidu_subscription_share_browser"
    assert result["author"] == "吕晓彤"
    assert result["media_type"] == "text"
    assert result["published_at"] == "2026-07-25T10:10:00+08:00"
    assert result["published_at_basis"] == "provider_modified_at_proxy"
    assert result["source_modified_at"] == "2026-07-25T10:10:00+08:00"
    assert result["captured_at"] == "2026-07-25T10:00:00+08:00"
    assert result["first_observed_at"] == "2026-07-25T10:00:00+08:00"
    assert result["ocr_path"] is None
    assert Path(result["evidence_path"]).read_text(encoding="utf-8") == (
        "今天市场缩量，下一交易日先看成交额是否恢复。\n"
    )


def _decision_bundle(evidence: dict) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    validation = {
        "status": "qualify",
        "as_of": checked_at,
        "summary": "最新市场事实仍要求等待成交量确认。",
        "currentness": {
            "latest_available": True,
            "checked_at": checked_at,
            "reason": "已读取处理时最新可用市场快照。",
        },
        "facts": [
            {
                "metric": "market_liquidity",
                "value": "contraction",
                "observed_at": checked_at,
                "evidence": "market-snapshot://2026-07-25",
                "reader_text": "最新市场成交仍未出现可信的持续放量。",
            }
        ],
    }
    coverage = {
        "todays_market_diagnosis": {
            "status": "present",
            "evidence_quotes": ["今天市场缩量"],
            "reader_meaning": "当下量能不足，风险偏好没有确认修复。",
            "horizon": "当下",
            "triggers": ["成交额恢复"],
            "falsifiers": ["放量后仍普跌"],
        },
        "next_session_playbook": {
            "status": "present",
            "evidence_quotes": ["下一交易日先看成交额是否恢复"],
            "reader_meaning": "下一交易日先确认量能，不追涨。",
            "horizon": "下一交易日",
            "triggers": ["开盘后量价共振"],
            "falsifiers": ["放量冲高回落"],
        },
        "next_several_session_base_case": {
            "status": "absent",
            "reason": "原文没有未来数日路径判断。",
        },
        "style_market_cap_regime": {
            "status": "absent",
            "reason": "原文没有风格或市值判断。",
        },
        "market_board_sector_hierarchy": {
            "status": "absent",
            "reason": "原文没有板块或行业层级。",
        },
        "position_risk_budget": {
            "status": "absent",
            "reason": "原文没有明确仓位区间。",
        },
        "named_asset_inventory": {
            "status": "absent",
            "reason": "原文没有点名资产。",
            "assets": [],
        },
    }
    claim_id = "lv-liquidity"
    item = {
        "source": evidence["source"],
        "author": evidence["author"],
        "title": evidence["title"],
        "published_at": evidence["published_at"],
        "published_at_basis": evidence["published_at_basis"],
        "source_modified_at": evidence["source_modified_at"],
        "captured_at": evidence["captured_at"],
        "first_observed_at": evidence["first_observed_at"],
        "media_type": evidence["media_type"],
        "evidence_path": evidence["evidence_path"],
        "original_evidence_path": evidence["original_path"],
        "decision_status": "actionable_signal",
        "claim_semantic_routing": {
            "content_product": "member_livestream",
            "current_decision_claim_ids": [claim_id],
            "durable_knowledge_claim_ids": [],
        },
        "knowledge_status": "no_reusable_knowledge",
        "knowledge_reason": "短消息只包含当下量能观察，没有可复用因果模型。",
        "trade_information_coverage": coverage,
        "claims": [
            {
                "claim_id": claim_id,
                "quote": "今天市场缩量",
                "reasoning": "量能不足时不能把短暂反弹当成趋势确认。",
                "asset_scope": ["A-share", "macro"],
                "direction": "defensive",
                "horizon": "下一交易日",
                "confidence": "medium",
                "falsifiers": ["成交额恢复且形成持续主线"],
            }
        ],
        "actionable_signals": [
            {
                "signal_id": "lv-wait-liquidity",
                "claim_ids": [claim_id],
                "action": "wait",
                "assets": [
                    {"name": "A股整体", "market": "CN", "theme": "market-wide"}
                ],
                "relevant_asset_codes": [],
                "horizon": "下一交易日",
                "execution": "量能确认前不追涨，保留现金。",
                "trigger": "成交额恢复且领涨方向扩散。",
                "confidence": "medium",
                "falsifiers": ["放量后继续普跌"],
                "rationale": {
                    "news_or_event": [],
                    "fundamental": [],
                    "trading": ["最新市场成交仍未出现可信的持续放量。"],
                },
                "current_validation": validation,
            }
        ],
        "market_outlook": {
            "scope": "A股整体",
            "claim_ids": [claim_id],
            "current_phase": "当下量能不足，风险偏好修复尚未确认。",
            "base_case": "下一交易日先观察量能；未来数日保持等待，直至量价共振。",
            "strategy": [
                "下一交易日不追涨，量能确认后再考虑提高风险暴露。",
                "未来数日若继续缩量，维持现金与低波动资产优先。",
            ],
            "turning_points": ["成交额恢复且市场宽度同步改善"],
            "horizon": "当下、下一交易日及未来数日",
            "confidence": "medium",
            "falsifiers": ["放量后仍普跌并跌破关键支撑"],
            "current_validation": validation,
        },
        "market_validation": validation,
        "synthesis": {
            "summary": "系统结合最新市场事实后保留等待建议，不把单一资产替代整体市场判断。",
            "confidence": "medium",
            "conflicts": [],
        },
        "household_recommendation": {
            "action": "wait",
            "evidence": "来源与最新市场事实均未证明量能修复。",
            "confidence": "medium",
            "horizon": "下一交易日及未来数日",
            "falsifier": "量价共振并形成持续主线。",
        },
        "book_kol_us": {
            "book": "KOL-US",
            "paper_only": True,
            "decision": "no_trade",
            "reason": "来源没有可验证的美股上市股票或 ETF 映射。",
        },
    }
    attach_claim_contract(item, evidence["evidence_path"])
    return {
        "household_context_provider": {
            "type": "lianghui_mcp",
            "fresh_read_per_run": True,
        },
        "items": [item],
        "cross_source": {"agreements": [], "conflicts": []},
    }


def _household_context() -> dict:
    return {
        "family_id": "test-family",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source_reference": "test://fresh-household",
        "positions": [],
        "decision_view": {},
    }


def test_one_runner_resumes_after_analysis_failure_without_repeating_browser_or_ocr(
    tmp_path,
):
    private_url = "https://pan.baidu.com/s/private-share-token"
    private_code = "a1b2"
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nbrowser-downloaded-real-shape")
    entry = _representative_subscription_entries()[0]
    entry["provider_file_id"] = "123456789012345"
    entry["size"] = downloaded.stat().st_size
    browser_triggers = 0
    browser_binds = 0

    def browser_runner(command, **_kwargs):
        nonlocal browser_triggers, browser_binds
        tail = command[3:]
        if tail[:1] == ["bind"]:
            browser_binds += 1
            payload = {"session": "ticket04", "bound": True}
        elif tail[:1] == ["open"]:
            payload = {"url": "redacted", "page": "page-1"}
        elif tail[:1] == ["eval"] and "/share/list" in tail[1]:
            payload = {
                "status": "ok",
                "complete_scan": True,
                "entries": [entry],
            }
        elif tail[:1] == ["eval"] and "ticket04_provider_direct_link" in tail[1]:
            payload = {"status": "unsupported"}
        elif tail[:1] == ["eval"] and "ticket04_exact_ui_download" in tail[1]:
            payload = {
                "status": "download_confirmation_ready",
                "name": entry["name"],
            }
        elif tail[:1] == ["click"]:
            browser_triggers += 1
            payload = {"clicked": True, "matches_n": 1}
        elif tail[:2] == ["wait", "download"]:
            payload = {
                "downloaded": True,
                "filename": str(downloaded),
                "state": "complete",
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    service = LvSubscriptionService(
        tmp_path / "subscription",
        now=lambda: NOW,
        runner=browser_runner,
        opencli_command=("opencli",),
        share_url=private_url,
        share_code=private_code,
    )
    pipeline = DecisionPipeline(
        tmp_path / "decisions",
        household_context_loader=_household_context,
    )
    ocr_calls = 0
    bundle_calls = 0
    sends = 0

    def ocr_runner(_path):
        nonlocal ocr_calls
        ocr_calls += 1
        return {
            "engine": "macos_vision",
            "lines": [
                {
                    "text": "今天市场缩量，下一交易日先看成交额是否恢复。",
                    "confidence": 0.99,
                    "bounding_box": [0.1, 0.7, 0.8, 0.1],
                }
            ],
        }

    def bundle_builder(evidence):
        nonlocal bundle_calls
        bundle_calls += 1
        if bundle_calls == 1:
            raise EnrichmentError("analysis temporarily unavailable")
        path = tmp_path / f"{evidence['version_key']}.json"
        path.write_text(
            json.dumps(_decision_bundle(evidence), ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def sender(_title, _body):
        nonlocal sends
        sends += 1
        return {"wecom": "ok"}

    with pytest.raises(EnrichmentError, match="analysis temporarily unavailable"):
        service.run_opencli(
            session="ticket04",
            decision_output_dir=tmp_path / "decisions",
            bundle_builder=bundle_builder,
            sender=sender,
            ocr_runner=ocr_runner,
            pipeline=pipeline,
            bootstrap_bind=True,
        )
    assert service.status()["pending"] == [
        {
            "identity": LvSubscriptionService._normalize_entry(entry)[
                "identity"
            ],
            "version_key": LvSubscriptionService._normalize_entry(entry)[
                "version_key"
            ],
            "path": entry["path"],
            "name": entry["name"],
            "media_type": "image",
            "size": entry["size"],
            "modified_at": entry["modified_at"],
            "version_first_seen_at": NOW.isoformat(timespec="seconds"),
            "stage": "analysis_requested",
        }
    ]

    completed = service.run_opencli(
        session="ticket04",
        decision_output_dir=tmp_path / "decisions",
        bundle_builder=bundle_builder,
        sender=sender,
        ocr_runner=ocr_runner,
        pipeline=pipeline,
    )
    quiet = service.run_opencli(
        session="ticket04",
        decision_output_dir=tmp_path / "decisions",
        bundle_builder=bundle_builder,
        sender=sender,
        ocr_runner=ocr_runner,
        pipeline=pipeline,
    )

    assert completed["status"] == "completed"
    assert len(completed["items"]) == 1
    assert completed["items"][0]["decision"]["status"] == "decided"
    assert quiet is None
    assert browser_binds == 1
    assert browser_triggers == 1
    assert ocr_calls == 1
    assert bundle_calls == 2
    assert sends == 1
    assert len(
        (tmp_path / "decisions" / "book_kol_us" / "decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ) == 1
    requests = list(
        (tmp_path / "subscription").rglob("analysis_request.json")
    )
    assert len(requests) == 1
    request = json.loads(requests[0].read_text(encoding="utf-8"))
    assert request["status"] == "waiting_for_analysis"
    assert set(request["required_coverage_rows"]) == {
        "todays_market_diagnosis",
        "next_session_playbook",
        "next_several_session_base_case",
        "style_market_cap_regime",
        "market_board_sector_hierarchy",
        "position_risk_budget",
        "named_asset_inventory",
    }
    assert "confidence is low" in request["reader_insight_contract"]["useful"]
    assert "suppress household delivery" in request["reader_insight_contract"]["none"]
    durable = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "subscription").rglob("*.json*")
    )
    assert private_url not in durable
    assert private_code not in durable


def test_decision_requires_full_coverage_then_delivers_and_routes_paper_once(tmp_path):
    service = LvSubscriptionService(tmp_path / "subscription", now=lambda: NOW)
    downloaded = tmp_path / "盘后.txt"
    downloaded.write_text(
        "今天市场缩量，下一交易日先看成交额是否恢复。",
        encoding="utf-8",
    )
    text_entry = _representative_subscription_entries()[1]
    text_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([text_entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)
    evidence = service.ingest_browser_download(update["identity"])
    bundle = _decision_bundle(evidence)
    bundle_path = tmp_path / "decision.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    pipeline = DecisionPipeline(
        tmp_path / "decisions",
        household_context_loader=_household_context,
    )
    sends = 0

    def sender(_title, _body):
        nonlocal sends
        sends += 1
        return {"wecom": "ok"}

    missing_reader_insight = _decision_bundle(evidence)
    missing_reader_insight["items"][0].update(
        {
            "decision_status": "no_actionable_signal",
            "decision_reason": "只有弱信号，不能形成交易动作。",
        }
    )
    invalid_insight_path = tmp_path / "invalid-insight-decision.json"
    invalid_insight_path.write_text(
        json.dumps(missing_reader_insight, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(
        EnrichmentError,
        match="reader_insight useful or none",
    ):
        service.decide(
            update["identity"],
            bundle_path=invalid_insight_path,
            decision_output_dir=tmp_path / "decisions",
            sender=sender,
            pipeline=pipeline,
        )

    missing_coverage = _decision_bundle(evidence)
    del missing_coverage["items"][0]["trade_information_coverage"][
        "position_risk_budget"
    ]
    invalid_path = tmp_path / "invalid-decision.json"
    invalid_path.write_text(
        json.dumps(missing_coverage, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(EnrichmentError, match="coverage matrix"):
        service.decide(
            update["identity"],
            bundle_path=invalid_path,
            decision_output_dir=tmp_path / "decisions",
            sender=sender,
            pipeline=pipeline,
        )

    first = service.decide(
        update["identity"],
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        sender=sender,
        pipeline=pipeline,
    )
    revised_bundle = _decision_bundle(evidence)
    revised_bundle["items"][0]["synthesis"]["summary"] = (
        "重复运行不得为同一来源版本产生第二次动作。"
    )
    revised_path = tmp_path / "revised-decision.json"
    revised_path.write_text(
        json.dumps(revised_bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    second = service.decide(
        update["identity"],
        bundle_path=revised_path,
        decision_output_dir=tmp_path / "decisions",
        sender=sender,
        pipeline=pipeline,
    )

    assert first["status"] == "decided"
    assert first["household_notification"]["status"] == "delivered"
    assert first["book_kol_us"]["status"] == "no_trade"
    assert first["book_kol_us"]["paper_only"] is True
    assert second["idempotent_replay"] is True
    assert second["decision_bundle_sha256"] == first["decision_bundle_sha256"]
    assert sends == 1
    assert len(
        (tmp_path / "decisions" / "household_outbox.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ) == 1
    assert len(
        (tmp_path / "decisions" / "book_kol_us" / "decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ) == 1

    Path(first["decision_result_path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(EnrichmentError, match="decision result changed"):
        service.decide(
            update["identity"],
            bundle_path=bundle_path,
            decision_output_dir=tmp_path / "decisions",
            sender=sender,
            pipeline=pipeline,
        )


def test_no_reader_insight_suppresses_household_but_keeps_paper_audit_once(tmp_path):
    service = LvSubscriptionService(tmp_path / "subscription", now=lambda: NOW)
    downloaded = tmp_path / "盘后.txt"
    downloaded.write_text(
        "今天市场缩量，下一交易日先看成交额是否恢复。",
        encoding="utf-8",
    )
    entry = _representative_subscription_entries()[1]
    entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)
    evidence = service.ingest_browser_download(update["identity"])
    bundle = _decision_bundle(evidence)
    bundle["items"][0].update(
        {
            "decision_status": "no_actionable_signal",
            "decision_reason": "原文没有足以传达给读者的新信息。",
            "reader_insight": {
                "status": "none",
                "reason": "没有可准确复述的新增洞察。",
            },
        }
    )
    bundle_path = tmp_path / "no-reader-insight.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    pipeline = DecisionPipeline(
        tmp_path / "decisions",
        household_context_loader=_household_context,
    )
    sends = 0

    def sender(_title, _body):
        nonlocal sends
        sends += 1
        return {"wecom": "ok"}

    first = service.decide(
        update["identity"],
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        sender=sender,
        pipeline=pipeline,
    )
    second = service.decide(
        update["identity"],
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        sender=sender,
        pipeline=pipeline,
    )

    assert first["household_notification"]["status"] == "suppressed"
    assert first["household_notification"]["reason"] == (
        "没有可准确复述的新增洞察。"
    )
    assert first["book_kol_us"]["status"] == "no_trade"
    assert second["idempotent_replay"] is True
    assert sends == 0
    outbox = [
        json.loads(line)
        for line in (tmp_path / "decisions" / "household_outbox.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(outbox) == 1
    assert outbox[0]["status"] == "suppressed"
    assert len(
        (tmp_path / "decisions" / "book_kol_us" / "decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ) == 1


def test_image_decision_requires_every_low_confidence_ocr_line_to_be_excluded_or_resolved(
    tmp_path,
):
    service = LvSubscriptionService(tmp_path / "subscription", now=lambda: NOW)
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nreal-subscription-image")
    image_entry = _representative_subscription_entries()[0]
    image_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([image_entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)
    evidence = service.ingest_browser_download(
        update["identity"],
        ocr_runner=lambda _path: {
            "engine": "macos_vision",
            "lines": [
                {
                    "text": "今天市场缩量，下一交易日先看成交额是否恢复。",
                    "confidence": 0.99,
                    "bounding_box": [0.1, 0.7, 0.8, 0.1],
                },
                {
                    "text": "疑似：纳指?仓",
                    "confidence": 0.61,
                    "bounding_box": [0.1, 0.5, 0.5, 0.1],
                },
            ],
        },
    )
    bundle = _decision_bundle(evidence)
    bundle_path = tmp_path / "image-decision.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    pipeline = DecisionPipeline(
        tmp_path / "decisions",
        household_context_loader=_household_context,
    )

    with pytest.raises(EnrichmentError, match="OCR ambiguity assessment"):
        service.decide(
            update["identity"],
            bundle_path=bundle_path,
            decision_output_dir=tmp_path / "decisions",
            sender=lambda _title, _body: {"wecom": "ok"},
            pipeline=pipeline,
        )

    bundle["items"][0]["ocr_ambiguity_assessment"] = [
        {
            "text": "疑似：纳指?仓",
            "actionable": False,
            "reason": "低置信度且无法确认，不进入资产映射或建议。",
        }
    ]
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    result = service.decide(
        update["identity"],
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        sender=lambda _title, _body: {"wecom": "ok"},
        pipeline=pipeline,
    )

    assert result["status"] == "decided"


def test_high_confidence_question_mark_is_still_an_ocr_ambiguity(tmp_path):
    service = LvSubscriptionService(tmp_path / "subscription", now=lambda: NOW)
    downloaded = tmp_path / "12.png"
    downloaded.write_bytes(b"\x89PNG\r\nreal-subscription-image")
    image_entry = _representative_subscription_entries()[0]
    image_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([image_entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)

    evidence = service.ingest_browser_download(
        update["identity"],
        ocr_runner=lambda _path: {
            "engine": "macos_vision",
            "lines": [
                {
                    "text": "纳指?仓",
                    "confidence": 0.97,
                    "bounding_box": [0.1, 0.5, 0.5, 0.1],
                }
            ],
        },
    )

    assert evidence["ambiguities"] == [
        {
            "text": "纳指?仓",
            "confidence": 0.97,
            "bounding_box": [0.1, 0.5, 0.5, 0.1],
            "reasons": ["uncertain_glyph"],
        }
    ]


def test_non_paper_book_contract_fails_before_any_side_effect(tmp_path):
    service = LvSubscriptionService(tmp_path / "subscription", now=lambda: NOW)
    downloaded = tmp_path / "盘后.txt"
    downloaded.write_text(
        "今天市场缩量，下一交易日先看成交额是否恢复。",
        encoding="utf-8",
    )
    text_entry = _representative_subscription_entries()[1]
    text_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([text_entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)
    evidence = service.ingest_browser_download(update["identity"])
    bundle = _decision_bundle(evidence)
    bundle["items"][0]["book_kol_us"]["paper_only"] = False
    bundle_path = tmp_path / "unsafe-decision.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False),
        encoding="utf-8",
    )
    pipeline = DecisionPipeline(
        tmp_path / "decisions",
        household_context_loader=_household_context,
    )
    sends = 0

    def sender(_title, _body):
        nonlocal sends
        sends += 1
        return {"wecom": "must-not-run"}

    with pytest.raises(EnrichmentError, match="paper-only contract"):
        service.decide(
            update["identity"],
            bundle_path=bundle_path,
            decision_output_dir=tmp_path / "decisions",
            sender=sender,
            pipeline=pipeline,
        )

    assert sends == 0
    assert not (tmp_path / "decisions" / "household_outbox.jsonl").exists()
    assert not (
        tmp_path / "decisions" / "book_kol_us" / "decisions.jsonl"
    ).exists()


def test_state_write_failure_recovers_without_second_delivery_or_paper_action(
    tmp_path,
    monkeypatch,
):
    service = LvSubscriptionService(tmp_path / "subscription", now=lambda: NOW)
    downloaded = tmp_path / "盘后.txt"
    downloaded.write_text(
        "今天市场缩量，下一交易日先看成交额是否恢复。",
        encoding="utf-8",
    )
    text_entry = _representative_subscription_entries()[1]
    text_entry["size"] = downloaded.stat().st_size
    update = service.observe_browser_listing([text_entry])["updates"][0]
    _capture_browser_download(service, update["identity"], downloaded)
    evidence = service.ingest_browser_download(update["identity"])
    bundle_path = tmp_path / "decision.json"
    bundle_path.write_text(
        json.dumps(_decision_bundle(evidence), ensure_ascii=False),
        encoding="utf-8",
    )
    pipeline = DecisionPipeline(
        tmp_path / "decisions",
        household_context_loader=_household_context,
    )
    sends = 0

    def sender(_title, _body):
        nonlocal sends
        sends += 1
        return {"wecom": "ok"}

    real_atomic_write = lv_subscription._atomic_write_json
    state_write_attempts = 0

    def fail_first_state_write(path, value):
        nonlocal state_write_attempts
        if Path(path).name == "decision_state.json":
            state_write_attempts += 1
            if state_write_attempts == 1:
                raise OSError("simulated state persistence failure")
        real_atomic_write(path, value)

    monkeypatch.setattr(
        lv_subscription,
        "_atomic_write_json",
        fail_first_state_write,
    )

    with pytest.raises(OSError, match="state persistence failure"):
        service.decide(
            update["identity"],
            bundle_path=bundle_path,
            decision_output_dir=tmp_path / "decisions",
            sender=sender,
            pipeline=pipeline,
        )

    result = service.decide(
        update["identity"],
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        sender=sender,
        pipeline=pipeline,
    )

    assert result["status"] == "decided"
    assert sends == 1
    assert len(
        (tmp_path / "decisions" / "book_kol_us" / "decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ) == 1
    assert len(
        (tmp_path / "decisions" / "household_outbox.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ) == 1
