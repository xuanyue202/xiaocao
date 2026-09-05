from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from xiaocao.kol.book import BookKolUs
from xiaocao.kol.enrichment import EnrichmentError
from xiaocao.kol.enrichment_types import EnrichmentDiagnosticError, validate_decision_completion
from xiaocao.kol.netdisk_enrichment import (
    NetdiskEnrichmentService,
    _normalize_ordered_transcript_segments,
)


NOW = datetime.fromisoformat("2026-07-20T09:00:00+08:00")


def test_template_file_chooser_timeout_preserves_pre_attachment_diagnostic():
    result = SimpleNamespace(returncode=1, stdout="", stderr=(
        "Page.fileChooserOpened not received within 5s — the input may not have opened a file chooser"
    ))
    with pytest.raises(EnrichmentDiagnosticError) as caught:
        NetdiskEnrichmentService._validate_opencli_upload_template_receipt(
            result, target_name="video.mp4", directory="/课程/自己的课/小草", claim_id="job-12345678"
        )
    assert caught.value.diagnostic_code == "file_chooser_not_opened"
    assert caught.value.diagnostic_stage == "upload_before_attachment"


def test_pre_attachment_repair_reuses_claim_once_and_rejects_unknown_effect(tmp_path, monkeypatch):
    video = tmp_path / "video-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(tmp_path / "out", runner=_runner, now=lambda: NOW,
                                       use_opencli_upload_template=True)
    job = service.prepare(video)
    current = {**job, "event": "netdisk_upload_failed", "status": "upload_claimed",
               "reason": "browser_command_failed"}
    service.store.append(current)
    with pytest.raises(EnrichmentError, match="pre-attachment"):
        service.resume_pre_attachment_upload(job["job_id"], session="site:baidu-netdisk")
    service.store.append({**current, "reason": "file_chooser_not_opened",
                          "failure_stage": "upload_before_attachment"})
    monkeypatch.setattr(service, "_inspect_opencli_target", lambda **kwargs: {
        "exact_count": 0, "observed_at": NOW})
    submitted = []
    def submit(job_id, **kwargs):
        latest = service.store.latest(job_id)
        assert latest["event"] == "netdisk_upload_repair_claimed"
        submitted.append(job_id)
        return latest
    monkeypatch.setattr(service, "_submit_opencli_upload", submit)
    result = service.resume_pre_attachment_upload(job["job_id"], session="site:baidu-netdisk")
    assert result["upload_repair_attempts"] == 1
    assert submitted == [job["job_id"]]
    with pytest.raises(EnrichmentError, match="pre-attachment"):
        service.resume_pre_attachment_upload(job["job_id"], session="site:baidu-netdisk")


def test_file_access_repair_requires_user_restore_and_is_consumed_once(tmp_path, monkeypatch):
    video = tmp_path / "video-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(tmp_path / "out", runner=_runner, now=lambda: NOW,
                                       use_opencli_upload_template=True)
    job = service.prepare(video)
    service.store.append({**job, "event": "netdisk_upload_failed", "status": "upload_claimed",
                          "reason": "file_access_denied", "upload_repair_attempts": 1})
    with pytest.raises(EnrichmentError, match="pre-attachment"):
        service.resume_pre_attachment_upload(job["job_id"], session="site:baidu-netdisk")
    monkeypatch.setattr(service, "_inspect_opencli_target", lambda **kwargs: {
        "exact_count": 0, "observed_at": NOW})
    monkeypatch.setattr(service, "_submit_opencli_upload", lambda job_id, **kwargs: service.store.latest(job_id))
    result = service.resume_pre_attachment_upload(job["job_id"], session="site:baidu-netdisk",
                                                  file_access_restored=True)
    assert result["upload_repair_attempts"] == 2
    assert result["file_access_repair_claimed_at"]
    service.store.append({**result, "event": "netdisk_upload_failed", "reason": "file_access_denied"})
    with pytest.raises(EnrichmentError, match="pre-attachment"):
        service.resume_pre_attachment_upload(job["job_id"], session="site:baidu-netdisk",
                                              file_access_restored=True)


@pytest.mark.parametrize("failure", [None, "cloud_present", "queue_incomplete", "queued", "attached", "receipt", "no_control", "wrong_job", "not_authorized"])
def test_reconciled_upload_requires_complete_negative_proof_and_claims_once(tmp_path, monkeypatch, failure):
    video = tmp_path / "video-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(tmp_path / "out", runner=_runner, now=lambda: NOW,
                                       use_opencli_upload_template=True)
    job = service.prepare(video)
    service.store.append({**job, "event": "netdisk_upload_failed", "status": "upload_claimed",
                          "reason": "browser_command_failed", "updated_at": (NOW - timedelta(minutes=10)).isoformat()})
    queue = {"complete": True, "targetCount": 0, "successfulCount": 1}
    surface = {"transferQueue": queue, "targetInTransferUi": False, "targetUiRows": [],
               "receiptMatchesTarget": False, "inputs": [{"targetAttached": False}]}
    row = {"status": "ready_to_upload", "directory": service.netdisk_directory,
           "targetName": video.name, "claimId": job["job_id"], "uploaded": False,
           "exactCountBefore": 0, "surfaceState": surface}
    if failure == "cloud_present": row["exactCountBefore"] = 1
    if failure == "queue_incomplete": queue["complete"] = False
    if failure == "queued": queue["targetCount"] = 1
    if failure == "attached": surface["inputs"][0]["targetAttached"] = True
    if failure == "receipt": surface["receiptMatchesTarget"] = True
    if failure == "no_control": queue["successfulCount"] = 0
    if failure == "wrong_job": row["claimId"] = "different-job"
    def inspect(**kwargs):
        assert kwargs["inspect_only"] is True
        return SimpleNamespace(returncode=0, stdout=json.dumps([row]), stderr="")
    monkeypatch.setattr(service, "_opencli_upload_template_process", inspect)
    submissions = []
    def submit(job_id, **kwargs):
        state = service.store.latest(job_id)
        assert state["event"] == "netdisk_upload_repair_claimed"
        assert state["upload_reconciliation_proof"] == row
        submissions.append(job_id)
        return state
    monkeypatch.setattr(service, "_submit_opencli_upload", submit)
    if failure:
        with pytest.raises(EnrichmentError):
            service.resume_reconciled_failed_upload(job["job_id"], session="site:baidu-netdisk",
                                                     repair_authorized=failure != "not_authorized")
        assert submissions == []
        return
    service.resume_reconciled_failed_upload(job["job_id"], session="site:baidu-netdisk", repair_authorized=True)
    assert submissions == [job["job_id"]]
    with pytest.raises(EnrichmentError):
        service.resume_reconciled_failed_upload(job["job_id"], session="site:baidu-netdisk", repair_authorized=True)


def _runner(command, **_kwargs):
    if command[0] == "ffprobe":
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"format": {"duration": "2192.547945"}}),
            stderr="",
        )
    raise AssertionError(command)


def _opencli_capture_runner(
    video_name: str,
    *,
    virtualized: bool = False,
    profile: str | None = None,
    command_log: list[list[str]] | None = None,
):
    transcript = (
        "开头明确说市场连续下跌后可能修复，但仓位必须很轻。\n\n"
        + "中段讨论信通电子、德明利和市场成交量，强调触发与风险。" * 20
        + "\n\n结尾明确说商业航天没有企稳信号，当前不参与。"
    )
    segments = [
        {"index": index, "paragraph_index": index, "text": text}
        for index, text in enumerate(transcript.split("\n\n"))
    ]

    def runner(command, **kwargs):
        if command_log is not None:
            command_log.append(list(command))
        if command[0] == "ffprobe":
            return _runner(command, **kwargs)
        prefix = ["opencli"]
        if profile:
            prefix.extend(["--profile", profile])
        prefix.extend(["browser", "ticket02-test"])
        if command[: len(prefix)] != prefix:
            raise AssertionError(command)
        tail = command[len(prefix):]
        if tail[:1] == ["open"]:
            payload = {"url": command[len(prefix) + 1], "page": "page-1"}
        elif tail[:1] == ["eval"] and "const guardKey = '__xiaocaoNetdiskPauseGuardV1'" in tail[1]:
            payload = {
                "target_bound": True,
                "video_count": 1,
                "playing_before_pause": 1,
                "all_video_paused": True,
                "pause_guard_installed": True,
            }
        elif tail[:1] == ["eval"] and "current_url: location.href" in tail[1]:
            payload = {
                "current_url": "https://pan.baidu.com/pfile/video?path="
                + quote(f"/课程/自己的课/小草/{video_name}")
            }
        elif len(tail) == 2 and tail[0] == "eval" and "url: location.href" in tail[1]:
            assert "ad_overlays_dismissed" in tail[1]
            assert "location.reload" not in tail[1]
            assert "await new Promise" in tail[1]
            assert "document.contains(overlay) && visible(overlay)" in tail[1]
            assert "scroller.scrollTop = 0" in tail[1]
            assert "getAttribute('data-index')" in tail[1]
            payload = {
                "url": (
                    "https://pan.baidu.com/pfile/video?path="
                    + quote(f"/课程/自己的课/小草/{video_name}")
                ),
                "target_bound": True,
                "active": {"matches": 1, "text": "文稿"},
                "transcript": {"text": transcript, "segments": segments},
                "playback": {
                    "video_count": 1,
                    "all_video_paused": True,
                    "pause_guard_installed": True,
                },
                "render": {
                    "list_matches": 1,
                    "scroll_top": 0,
                    "client_height": 555,
                    "scroll_height": 3997,
                    "paragraph_count": len(segments),
                    "sentence_count": len(segments),
                    "segment_count": len(segments),
                    "segment_terminal_index": segments[-1]["index"],
                    "list_text_chars": len(transcript.strip()),
                    "sentence_text_chars": sum(
                        len(row["text"]) for row in segments
                    ),
                    "first_node_in_dom": True,
                    "last_node_in_dom": True,
                    "first_node_at_viewport_start": True,
                    "first_node_near_list_start": True,
                    "last_node_below_viewport": True,
                    "last_node_near_list_end": True,
                    "virtual_or_loading_markers": (
                        ["virtual-list"] if virtualized else []
                    ),
                    "has_load_more": False,
                },
            }
        elif tail[:2] == ["tab", "close"] and tail[2:] == ["page-1"]:
            payload = {"closed": "page-1"}
        elif tail[:2] == ["tab", "list"]:
            payload = []
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    return runner


def _evidence(video_name: str, visible_state: str) -> dict:
    markers = {
        "上传完成，目标视频行可见": "video_present",
        "目标视频已存在于 /课程/自己的课/小草": "video_present",
        "目标视频已存在": "video_present",
        "文稿生成中": "transcript_generating",
        "文稿 已生成": "transcript_ready",
        "AI笔记生成中": "ai_note_generating",
        "AI笔记 已生成": "ai_note_ready",
    }
    marker = markers.get(visible_state)
    if marker is None and visible_state.startswith("文稿生成中"):
        marker = "transcript_generating"
    snapshot_text = f"{video_name}\n{visible_state}"
    player_markers = {
        "transcript_generating",
        "transcript_ready",
        "ai_note_generating",
        "ai_note_ready",
    }
    page_url = (
        "https://pan.baidu.com/pfile/video?path="
        + quote(f"/课程/自己的课/小草/{video_name}")
        if marker in player_markers
        else "https://pan.baidu.com/disk/main#/index?category=all"
    )
    return {
        "page_url": page_url,
        "target_name": video_name,
        "visible_state": marker or visible_state,
        "snapshot_text": snapshot_text,
        "target_region_text": snapshot_text,
        "snapshot_sha256": hashlib.sha256(snapshot_text.encode()).hexdigest(),
        "observed_at": NOW.isoformat(),
    }


def _prepare(tmp_path: Path) -> tuple[NetdiskEnrichmentService, Path, dict]:
    video = tmp_path / "20260717 盘前大师班直播(7月17日)-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out", runner=_runner, now=lambda: NOW
    )
    return service, video, service.prepare(video)


def test_completed_replay_resolves_migrated_paths_without_side_effects(tmp_path):
    repo = tmp_path / "new-checkout"
    output = (
        repo
        / "output"
        / "live"
        / "kol_subscription_videos"
        / "enrichment"
        / "version"
    )
    service = NetdiskEnrichmentService(
        output,
        runner=_runner,
        now=lambda: NOW,
    )
    artifact_dir = output / "artifacts" / "job-1"
    artifact_dir.mkdir(parents=True)
    transcript = artifact_dir / "transcript.txt"
    transcript.write_text("immutable transcript\n", encoding="utf-8")
    decision_result = artifact_dir / "decision_result.json"
    decision_result.write_text('{"status":"completed"}\n', encoding="utf-8")
    historical_prefix = (
        "/Users/old/repo/output/live/kol_subscription_videos/"
        "enrichment/version/artifacts/job-1"
    )
    bundle = output / "decision_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "items": [
                    {"evidence_path": f"{historical_prefix}/transcript.txt"}
                ]
            }
        ),
        encoding="utf-8",
    )
    service.store.append(
        {
            "job_id": "job-1",
            "status": "decided",
            "transcript_path": f"{historical_prefix}/transcript.txt",
            "transcript_sha256": hashlib.sha256(
                transcript.read_bytes()
            ).hexdigest(),
            "decision_bundle_path": (
                "/Users/old/repo/output/live/kol_subscription_videos/"
                "enrichment/version/decision_bundle.json"
            ),
            "decision_bundle_sha256": hashlib.sha256(
                bundle.read_bytes()
            ).hexdigest(),
            "decision_result_path": (
                f"{historical_prefix}/decision_result.json"
            ),
            "decision_result_sha256": hashlib.sha256(
                decision_result.read_bytes()
            ).hexdigest(),
        }
    )

    class FailPipeline:
        def process(self, _bundle):
            raise AssertionError("completed replay must not process again")

        def deliver_wechat(self, _result, *, sender):
            raise AssertionError("completed replay must not notify again")

    replay = service.decide(
        "job-1",
        bundle_path=bundle,
        decision_output_dir=repo / "output" / "live" / "kol_intelligence",
        sender=lambda *_args: (_ for _ in ()).throw(
            AssertionError("completed replay must not call sender")
        ),
        pipeline=FailPipeline(),
    )

    assert replay["idempotent_replay"] is True
    assert replay["transcript_path"] == str(transcript)
    assert replay["decision_result_path"] == str(decision_result)
    assert len(service.store.read()) == 1


def test_decided_same_bundle_can_reconcile_missing_daily_terminal(tmp_path):
    output = tmp_path / "netdisk"
    decisions = tmp_path / "decisions"
    service = NetdiskEnrichmentService(output, runner=_runner, now=lambda: NOW)
    transcript = tmp_path / "complete.txt"
    transcript.write_text("完整历史文稿" * 200, encoding="utf-8")
    transcript_sha = hashlib.sha256(transcript.read_bytes()).hexdigest()
    book_intent = {
        "decision": "no_trade",
        "reason": "历史 A 股内容没有当前美股触发。",
    }
    book = BookKolUs(decisions / "book_kol_us")
    book_key = book.resolve_identity(transcript_sha, book_intent)
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps({
            "items": [{
                "evidence_path": str(transcript),
                "book_kol_us": book_intent,
            }],
        }),
        encoding="utf-8",
    )
    bundle_sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    prior_result = tmp_path / "decision_result.json"
    prior_result.write_text(
        json.dumps({"status": "completed", "items": [{}]}),
        encoding="utf-8",
    )
    service.store.append({
        "job_id": "job-1",
        "status": "decided",
        "transcript_path": str(transcript),
        "transcript_sha256": transcript_sha,
        "decision_bundle_path": str(bundle),
        "decision_bundle_sha256": bundle_sha,
        "decision_result_path": str(prior_result),
        "decision_result_sha256": hashlib.sha256(
            prior_result.read_bytes()
        ).hexdigest(),
        "book_kol_us": {
            "book": "KOL-US",
            "paper_only": True,
            "status": "no_trade",
            "reason": book_intent["reason"],
            "idempotency_key": book_key,
        },
    })

    class PublicationPipeline:
        def process(self, _bundle):
            return {
                "status": "completed",
                "items": [{
                    "content_value": {
                        "status": "promoted",
                        "tier": "report_only",
                        "no_alert_reason": "历史报告不补发提醒。",
                    },
                    "notification": {
                        "status": "suppressed",
                        "reason": "历史报告不补发提醒。",
                        "idempotency_key": "e" * 64,
                    },
                    "book_kol_us": {
                        "book": "KOL-US",
                        "paper_only": True,
                        "status": "no_trade",
                        "reason": book_intent["reason"],
                        "idempotency_key": book_key,
                    },
                    "daily_terminal": {
                        "gray_report": {
                            "status": "published",
                            "detail_url": "https://example.test/report",
                            "receipt": "publish-receipt",
                        },
                        "alert": {
                            "status": "not_eligible",
                            "reason": "历史报告不补发提醒。",
                        },
                    },
                }],
            }

        def deliver_wechat(self, _result, *, sender):
            return {"status": "legally_not_eligible"}

    reconciled = service.decide(
        "job-1",
        bundle_path=bundle,
        decision_output_dir=decisions,
        sender=lambda *_args: pytest.fail("suppressed reminder must not send"),
        pipeline=PublicationPipeline(),
        reconcile_daily_terminal=True,
    )

    assert reconciled["idempotent_replay"] is False
    assert reconciled["household_notification"]["status"] == "suppressed"
    assert reconciled["household_notification"]["reason"] == (
        "历史报告不补发提醒。"
    )
    result = json.loads(
        Path(reconciled["decision_result_path"]).read_text(encoding="utf-8")
    )
    assert result["items"][0]["daily_terminal"]["gray_report"]["status"] == (
        "published"
    )


def _liveness_evidence(*, observed_at: datetime = NOW) -> dict:
    snapshot_text = "百度网盘 /课程/自己的课/小草 文件列表"
    return {
        "page_url": "https://pan.baidu.com/disk/main#/index?category=all",
        "snapshot_text": snapshot_text,
        "snapshot_sha256": hashlib.sha256(snapshot_text.encode()).hexdigest(),
        "observed_at": observed_at.isoformat(),
    }


def _opencli_upload_runner(
    events_path: Path,
    video_name: str,
    *,
    opencli_command: tuple[str, ...] = ("opencli",),
    snapshot_paths: list[Path] | None = None,
    upload_error: str | None = None,
):
    target_present = False

    def runner(command, **kwargs):
        nonlocal target_present
        if command[0] == "ffprobe":
            return _runner(command, **kwargs)
        prefix = [*opencli_command, "--profile", "work", "browser"]
        if command[: len(prefix)] != prefix:
            raise AssertionError(command)
        assert command[len(prefix)] == "ticket02-upload"
        tail = command[len(prefix) + 1:]
        if tail[:1] == ["open"]:
            payload = {"url": tail[1], "page": "page-1"}
        elif tail[:1] == ["eval"] and "current_url: location.href" in tail[1]:
            payload = {
                "current_url": "https://pan.baidu.com/pfile/video?path="
                + quote(f"/课程/自己的课/小草/{video_name}")
            }
        elif tail[:1] == ["eval"] and "/api/list" in tail[1]:
            assert "maxPages = 100" in tail[1]
            assert "page += 1" in tail[1]
            assert "complete_scan" in tail[1]
            assert ".nd-operate-guidance" in tail[1]
            assert 'img[alt="close"]' in tail[1]
            assert "getBoundingClientRect" in tail[1]
            assert ".click()" in tail[1]
            assert "clientX" not in tail[1]
            assert "clientY" not in tail[1]
            payload = {
                "page_url": "https://pan.baidu.com/disk/main",
                "errno": 0,
                "complete_scan": True,
                "folder_bound": True,
                "exact_count": 1 if target_present else 0,
                "target_name": video_name,
                "ad_overlays_dismissed": 1,
            }
        elif tail[:1] == ["eval"] and "data-xiaocao-upload-marker" in tail[1]:
            assert "stopImmediatePropagation" in tail[1]
            assert "capture: true" in tail[1]
            assert "addEventListener('input'" in tail[1]
            assert "addEventListener('change'" in tail[1]
            assert "hashchange" in tail[1]
            payload = {"marked": True, "matches": 1}
        elif tail[:1] == ["eval"] and "folder_bound" in tail[1]:
            payload = {"folder_bound": True}
        elif tail[:1] == ["upload"]:
            ledger = events_path.read_text(encoding="utf-8")
            assert "netdisk_upload_claimed" in ledger
            assert kwargs["timeout"] == 300
            assert kwargs["env"]["OPENCLI_BROWSER_COMMAND_TIMEOUT"] == "290"
            assert "data-xiaocao-upload-marker" in tail[1]
            snapshot_path = Path(tail[2])
            assert snapshot_path.name == video_name
            assert snapshot_path.read_bytes() == b"real-video"
            if snapshot_paths is not None:
                snapshot_paths.append(snapshot_path)
            if upload_error is not None:
                return SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr=upload_error,
                )
            target_present = True
            payload = {
                "uploaded": True,
                "files": [str(snapshot_path)],
                "file_names": [video_name],
            }
        else:
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    return runner


def test_opencli_step_claims_before_cdp_upload_and_waits_for_cloud_proof(
    tmp_path,
):
    video = tmp_path / "20260720 upload-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    events_path = tmp_path / "out" / "events.jsonl"
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_upload_runner(events_path, video.name),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)

    submitted = service.advance_opencli(
        prepared["job_id"],
        session="ticket02-upload",
        profile="work",
    )

    assert submitted["event"] == "netdisk_upload_started"
    assert submitted["status"] == "upload_claimed"
    assert submitted["upload_transport"] == "opencli_cdp"
    assert "127.0.0.1" not in json.dumps(submitted)
    assert [json.loads(line)["event"] for line in events_path.read_text().splitlines()] == [
        "netdisk_video_prepared",
        "netdisk_browser_liveness_ready",
        "netdisk_upload_claimed",
        "netdisk_upload_started",
    ]

    ready = service.advance_opencli(
        prepared["job_id"],
        session="ticket02-upload",
        profile="work",
    )

    assert ready["event"] == "netdisk_video_ready"
    assert ready["status"] == "video_ready"
    assert ready["source_mode"] == "uploaded"


def test_opencli_template_upload_reuses_site_session_and_validates_receipt(
    tmp_path,
):
    video = tmp_path / "20260720 template-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    output_dir = tmp_path / "out"
    target_present = False
    commands: list[list[str]] = []

    def runner(command, **kwargs):
        nonlocal target_present
        commands.append(command)
        if command[0] == "ffprobe":
            return _runner(command, **kwargs)
        browser_prefix = [
            "opencli",
            "--profile",
            "work",
            "browser",
            "site:baidu-netdisk",
        ]
        if command[: len(browser_prefix)] == browser_prefix:
            tail = command[len(browser_prefix):]
            if tail[:1] == ["open"]:
                payload = {"url": tail[1], "page": "page-1"}
            elif tail[:1] == ["eval"] and "/api/list" in tail[1]:
                payload = {
                    "page_url": "https://pan.baidu.com/disk/main",
                    "errno": 0,
                    "complete_scan": True,
                    "folder_bound": True,
                    "exact_count": 1 if target_present else 0,
                    "target_name": video.name,
                    "target_index": 0 if target_present else -1,
                }
            elif tail[:1] == ["eval"] and "folder_bound" in tail[1]:
                payload = {"folder_bound": True}
            else:
                raise AssertionError(command)
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload, ensure_ascii=False),
                stderr="",
            )
        adapter_prefix = [
            "opencli",
            "--profile",
            "work",
            "baidu-netdisk",
            "upload",
        ]
        if command[: len(adapter_prefix)] != adapter_prefix:
            raise AssertionError(command)
        assert "netdisk_upload_claimed" in (
            output_dir / "events.jsonl"
        ).read_text(encoding="utf-8")
        assert command[command.index("--file") + 1] == str(video.resolve())
        assert command[command.index("--target-name") + 1] == video.name
        claim_id = command[command.index("--claim-id") + 1]
        assert claim_id.startswith("kol-netdisk-")
        assert kwargs["timeout"] == 300
        assert kwargs["env"]["OPENCLI_BROWSER_COMMAND_TIMEOUT"] == "290"
        target_present = True
        payload = [{
            "status": "upload_submitted",
            "directory": "/课程/自己的课/小草",
            "targetName": video.name,
            "exactCountBefore": 0,
            "uploaded": True,
            "uploadTarget": (
                f'input[data-opencli-baidu-upload-claim="{claim_id}"]'
            ),
            "claimId": claim_id,
            "url": "https://pan.baidu.com/disk/main",
        }]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    service = NetdiskEnrichmentService(
        output_dir,
        runner=runner,
        now=lambda: NOW,
        opencli_command=("opencli",),
        use_opencli_upload_template=True,
    )
    prepared = service.prepare(video)

    submitted = service.advance_opencli(
        prepared["job_id"],
        session="site:baidu-netdisk",
        profile="work",
    )

    assert submitted["event"] == "netdisk_upload_started"
    assert submitted["upload_transport"] == "opencli_template"
    assert any(command[3:5] == ["baidu-netdisk", "upload"] for command in commands)

    ready = service.advance_opencli(
        prepared["job_id"],
        session="site:baidu-netdisk",
        profile="work",
    )
    assert ready["status"] == "video_ready"
    assert ready["source_mode"] == "uploaded"


def test_opencli_template_rejects_wrong_receipt_identity():
    result = SimpleNamespace(
        returncode=0,
        stdout=json.dumps([{
            "status": "upload_submitted",
            "directory": "/wrong",
            "targetName": "video.mp4",
            "exactCountBefore": 0,
            "uploaded": True,
            "uploadTarget": "input[data-opencli-baidu-upload-claim]",
            "claimId": "netdisk-12345678",
            "url": "https://pan.baidu.com/disk/main",
        }]),
        stderr="",
    )

    with pytest.raises(EnrichmentError, match="identity mismatch"):
        NetdiskEnrichmentService._validate_opencli_upload_template_receipt(
            result,
            target_name="video.mp4",
            directory="/课程/自己的课/小草",
            claim_id="netdisk-12345678",
        )


def test_short_opencli_dom_commands_keep_the_cli_default_timeout(tmp_path):
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=lambda _command, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True}),
            stderr="",
            runner_kwargs=kwargs,
        ),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )

    result = service._opencli_process(
        "ticket02-dom",
        "eval",
        "({ok: true})",
        profile="work",
        timeout_seconds=10,
    )

    assert "env" not in result.runner_kwargs


def test_npx_runtime_upload_keeps_the_verified_source_path_available(tmp_path):
    video = tmp_path / "20260720 npx-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    snapshots: list[Path] = []
    opencli_command = ("npx", "--yes", "@jackwener/opencli@1.8.6")
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_upload_runner(
            tmp_path / "out" / "events.jsonl",
            video.name,
            opencli_command=opencli_command,
            snapshot_paths=snapshots,
        ),
        now=lambda: NOW,
        opencli_command=opencli_command,
    )
    prepared = service.prepare(video)

    submitted = service.advance_opencli(
        prepared["job_id"],
        session="ticket02-upload",
        profile="work",
    )

    assert submitted["status"] == "upload_claimed"
    assert submitted["upload_transport"] == "opencli_cdp"
    assert len(snapshots) == 1
    assert snapshots[0] == video.resolve()
    assert snapshots[0].exists() is True


def test_upload_claim_replay_only_reconciles_and_never_resubmits(tmp_path):
    video = tmp_path / "20260720 replay-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    commands = []
    base_runner = _opencli_upload_runner(
        tmp_path / "out" / "events.jsonl",
        video.name,
    )

    def runner(command, **kwargs):
        commands.append(command)
        return base_runner(command, **kwargs)

    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=runner,
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)
    service.record_browser_liveness(
        prepared["job_id"],
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.claim_browser_action(prepared["job_id"], action="upload")

    replay = service.advance_opencli(
        prepared["job_id"],
        session="ticket02-upload",
        profile="work",
    )

    assert replay["status"] == "upload_claimed"
    assert replay["side_effect_uncertain"] is True
    assert all("upload" not in command[5:] for command in commands)
    assert all(
        not (len(command) > 6 and "DataTransfer" in command[6])
        for command in commands
    )


def test_upload_rejects_source_changed_after_prepare_before_any_submission(tmp_path):
    video = tmp_path / "20260720 immutable-source-compressed.mp4"
    video.write_bytes(b"real-video")
    upload_attempted = False

    def runner(command, **kwargs):
        nonlocal upload_attempted
        if command[0] == "ffprobe":
            return _runner(command, **kwargs)
        tail = command[5:]
        if tail[:1] == ["open"]:
            payload = {"url": command[6], "page": "page-1"}
        elif tail[:1] == ["eval"] and "/api/list" in tail[1]:
            video.write_bytes(b"changed-source")
            payload = {
                "page_url": "https://pan.baidu.com/disk/main",
                "errno": 0,
                "complete_scan": True,
                "folder_bound": True,
                "exact_count": 0,
                "target_name": video.name,
                "target_index": -1,
            }
        elif tail[:1] == ["eval"] and "folder_bound" in tail[1]:
            payload = {"folder_bound": True}
        else:
            upload_attempted = True
            raise AssertionError(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=runner,
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)

    with pytest.raises(EnrichmentError, match="source changed"):
        service.advance_opencli(
            prepared["job_id"],
            session="ticket02-immutable",
            profile="work",
        )

    assert upload_attempted is False
    assert service.status(prepared["job_id"])["status"] == "upload_claimed"


def test_cdp_upload_records_actionable_file_access_permission_failure(tmp_path):
    video = tmp_path / "20260720 permission-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    output_dir = tmp_path / "out"
    service = NetdiskEnrichmentService(
        output_dir,
        runner=_opencli_upload_runner(
            output_dir / "events.jsonl",
            video.name,
            upload_error="Not allowed",
        ),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)

    with pytest.raises(EnrichmentError, match="Allow access to file URLs"):
        service.advance_opencli(
            prepared["job_id"],
            session="ticket02-upload",
            profile="work",
        )

    latest = service.status(prepared["job_id"])
    assert latest["event"] == "netdisk_upload_failed"
    assert latest["status"] == "upload_claimed"
    assert latest["failure_stage"] == "opencli_cdp"
    assert latest["reason"] == "file_access_denied"
    assert "Not allowed" not in json.dumps(latest)


def test_cdp_upload_records_sanitized_opencli_command_failure(tmp_path):
    video = tmp_path / "20260720 command-failure-compressed.mp4"
    video.write_bytes(b"real-video")
    output_dir = tmp_path / "out"
    service = NetdiskEnrichmentService(
        output_dir,
        runner=_opencli_upload_runner(
            output_dir / "events.jsonl",
            video.name,
            upload_error="simulated browser failure",
        ),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)

    with pytest.raises(EnrichmentError, match="OpenCLI file upload failed"):
        service.advance_opencli(
            prepared["job_id"],
            session="ticket02-upload",
            profile="work",
        )

    events = [
        json.loads(line)
        for line in (output_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["event"] == "netdisk_upload_failed"
    assert events[-1]["status"] == "upload_claimed"
    assert events[-1]["failure_stage"] == "opencli_cdp"
    assert events[-1]["reason"] == "browser_command_failed"
    assert "simulated browser failure" not in json.dumps(events)
    assert "netdisk_upload_started" not in [row["event"] for row in events]


def _opencli_transcript_runner(
    video_name: str,
    *,
    transcript_states: list[dict] | None = None,
):
    transcript_probe_count = 0
    probe_states = transcript_states or [
        {
            "transcript_state": "generating",
            "active_tab": "文稿",
            "content_chars": 0,
            "export_available": False,
            "target_bound": True,
        },
        {
            "transcript_state": "ready",
            "active_tab": "文稿",
            "content_chars": 1842,
            "export_available": True,
            "target_bound": True,
        },
    ]

    def runner(command, **kwargs):
        nonlocal transcript_probe_count
        if command[0] == "ffprobe":
            return _runner(command, **kwargs)
        if command[:4] != ["opencli", "--profile", "work", "browser"]:
            raise AssertionError(command)
        tail = command[5:]
        if tail[:1] == ["open"]:
            payload = {"url": command[6], "page": "page-1"}
        elif tail[:1] == ["eval"] and "const guardKey = '__xiaocaoNetdiskPauseGuardV1'" in tail[1]:
            payload = {
                "target_bound": True,
                "video_count": 1,
                "playing_before_pause": 0,
                "all_video_paused": True,
                "pause_guard_installed": True,
            }
        elif tail[:1] == ["eval"] and "current_url: location.href" in tail[1]:
            payload = {
                "current_url": "https://pan.baidu.com/pfile/video?path="
                + quote(f"/课程/自己的课/小草/{video_name}")
            }
        elif tail[:1] == ["eval"] and "/api/list" in tail[1]:
            payload = {
                "page_url": "https://pan.baidu.com/disk/main",
                "errno": 0,
                "complete_scan": True,
                "folder_bound": True,
                "exact_count": 1,
                "target_name": video_name,
            }
        elif tail[:1] == ["eval"] and "scheduled" in tail[1]:
            payload = {"scheduled": True, "tab": "文稿", "matches": 1}
        elif tail[:1] == ["eval"] and "expected_tab" in tail[1]:
            payload = {
                "active_tab": "文稿",
                "expected_tab": "文稿",
                "target_bound": True,
                "video_count": 1,
                "all_video_paused": True,
                "pause_guard_installed": True,
            }
        elif tail[:1] == ["eval"] and "transcript_state" in tail[1]:
            transcript_probe_count += 1
            payload = probe_states[
                min(transcript_probe_count - 1, len(probe_states) - 1)
            ]
        else:
            raise AssertionError(command)
        if tail[:1] == ["eval"] and "baidu-netdisk/probe-transcript" in tail[1]:
            payload = {
                "template_name": "baidu-netdisk/probe-transcript",
                "template_version": 1,
                **payload,
            }
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    return runner


def test_opencli_step_submits_then_polls_transcript_without_reclicking_generation(
    tmp_path,
):
    video = tmp_path / "20260720 transcript-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    clock = [NOW]
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_transcript_runner(video.name),
        now=lambda: clock[0],
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)
    ready = service.advance_opencli(
        prepared["job_id"], session="ticket02-transcript", profile="work"
    )

    requested = service.advance_opencli(
        prepared["job_id"], session="ticket02-transcript", profile="work"
    )

    assert ready["status"] == "video_ready"
    assert requested["event"] == "netdisk_transcript_requested"
    assert requested["status"] == "transcript_requested"
    assert requested["next_poll_not_before"] == (
        NOW + timedelta(minutes=1)
    ).isoformat(timespec="microseconds")
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "out" / "events.jsonl").read_text().splitlines()
    ]
    assert events[-2:] == [
        "netdisk_transcript_claimed",
        "netdisk_transcript_requested",
    ]

    clock[0] = NOW + timedelta(minutes=6)
    completed = service.advance_opencli(
        prepared["job_id"], session="ticket02-transcript", profile="work"
    )

    assert completed["event"] == "netdisk_transcript_ready"
    assert completed["status"] == "transcript_ready"


def test_transcript_claim_replay_never_repeats_generation_interaction(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.claim_browser_action(job_id, action="transcript")
    service.runner = _opencli_transcript_runner(video.name)
    service.opencli_command = ("opencli",)
    replay = service.advance_opencli(
        job_id,
        session="ticket02-transcript",
        profile="work",
    )

    assert replay["status"] == "transcript_requested"
    assert replay["next_poll_not_before"] == (
        NOW + timedelta(minutes=1)
    ).isoformat(timespec="microseconds")
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "out" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert events.count("netdisk_transcript_claimed") == 1
    assert events[-1] == "netdisk_transcript_requested"


def test_transcript_claim_replay_stays_uncertain_when_readback_is_missing(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.claim_browser_action(job_id, action="transcript")
    service.runner = _opencli_transcript_runner(
        video.name,
        transcript_states=[
            {
                "transcript_state": "missing",
                "active_tab": "文稿",
                "content_chars": 0,
                "export_available": False,
                "target_bound": True,
            }
        ],
    )
    service.opencli_command = ("opencli",)

    replay = service.advance_opencli(
        job_id,
        session="ticket02-transcript",
        profile="work",
    )

    assert replay["status"] == "transcript_claimed"
    assert replay["pending"] is True
    assert replay["side_effect_uncertain"] is True
    assert replay["idempotent_replay"] is True
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "out" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert events.count("netdisk_transcript_claimed") == 1
    assert "netdisk_transcript_requested" not in events


def test_transcript_claim_replay_never_repeats_generation_interaction_after_browser_rebind(
    tmp_path,
):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.claim_browser_action(job_id, action="transcript")

    base_runner = _opencli_transcript_runner(video.name)
    open_failures = 3
    bind_calls = 0
    commands: list[list[str]] = []

    def runner(command, **kwargs):
        nonlocal open_failures, bind_calls
        commands.append(command)
        tail = command[5:]
        if tail[:1] == ["bind"]:
            bind_calls += 1
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"session": "ticket02-transcript"}),
                stderr="",
            )
        if tail[:1] == ["open"] and open_failures:
            open_failures -= 1
            raise subprocess.TimeoutExpired(
                command,
                kwargs.get("timeout", 30),
            )
        return base_runner(command, **kwargs)

    service.runner = runner
    service.opencli_command = ("opencli",)
    replay = service.advance_opencli(
        job_id,
        session="ticket02-transcript",
        profile="work",
    )

    assert replay["status"] == "transcript_requested"
    assert bind_calls == 1
    bind_index = next(
        index for index, command in enumerate(commands)
        if command[5:6] == ["bind"]
    )
    assert commands[bind_index + 1][5:6] == ["open"]
    assert not any(command[5:6] == ["click"] for command in commands)


def _opencli_ai_note_runner(
    video_name: str,
    *,
    note_states: list[dict] | None = None,
    submission_payload: dict | None = None,
):
    note_probe_count = 0
    probe_states = note_states or [
        {
            "ai_note_state": "missing",
            "active_tab": "笔记",
            "content_chars": 0,
            "template": "",
            "target_bound": True,
        },
        {
            "ai_note_state": "generating",
            "active_tab": "笔记",
            "content_chars": 0,
            "template": "文稿笔记",
            "target_bound": True,
        },
        {
            "ai_note_state": "ready",
            "active_tab": "笔记",
            "content_chars": 918,
            "template": "文稿笔记",
            "target_bound": True,
        },
    ]

    def runner(command, **kwargs):
        nonlocal note_probe_count
        if command[0] == "ffprobe":
            return _runner(command, **kwargs)
        if command[:4] != ["opencli", "--profile", "work", "browser"]:
            raise AssertionError(command)
        tail = command[5:]
        if tail[:1] == ["open"]:
            payload = {"url": command[6], "page": "page-1"}
        elif tail[:1] == ["eval"] and "const guardKey = '__xiaocaoNetdiskPauseGuardV1'" in tail[1]:
            payload = {
                "target_bound": True,
                "video_count": 1,
                "playing_before_pause": 0,
                "all_video_paused": True,
                "pause_guard_installed": True,
            }
        elif tail[:1] == ["eval"] and "current_url: location.href" in tail[1]:
            payload = {
                "current_url": "https://pan.baidu.com/pfile/video?path="
                + quote(f"/课程/自己的课/小草/{video_name}")
            }
        elif tail[:2] == ["wait", "selector"]:
            return SimpleNamespace(returncode=0, stdout="Waited", stderr="")
        elif tail[:1] == ["eval"] and "previewTemplate" in tail[1]:
            payload = {
                "scheduled": True,
                "template_no": 1,
                "target_bound": True,
                "modal_ready": True,
                "template_matches": 1,
                "template_selected": "文稿笔记",
                "button_matches": 1,
                "click_dispatched": False,
            }
        elif (
            tail[:1] == ["eval"]
            and "baidu-netdisk/submit-ai-note" in tail[1]
        ):
            payload = submission_payload or {
                "submitted": True,
                "template_no": 1,
                "target_bound": True,
                "button_matches": 1,
                "click_dispatched": True,
                "modal_visible": False,
                "confirmed_state": "generating",
                "content_chars": 42,
            }
        elif tail[:1] == ["eval"] and "genNoteByTpl" in tail[1]:
            payload = {"submitted": True, "template_no": 1}
        elif tail[:1] == ["eval"] and "ai_note_state" in tail[1]:
            note_probe_count += 1
            payload = probe_states[min(note_probe_count - 1, len(probe_states) - 1)]
        elif tail[:1] == ["eval"] and "scheduled" in tail[1]:
            payload = {"scheduled": True, "tab": "笔记", "matches": 1}
        elif tail[:1] == ["eval"] and "expected_tab" in tail[1]:
            payload = {
                "active_tab": "笔记",
                "expected_tab": "笔记",
                "target_bound": True,
                "video_count": 1,
                "all_video_paused": True,
                "pause_guard_installed": True,
            }
        else:
            raise AssertionError(command)
        if tail[:1] == ["eval"]:
            for template_name in (
                "probe-ai-note",
                "prepare-ai-note",
                "submit-ai-note",
            ):
                marker = f"baidu-netdisk/{template_name}"
                if marker in tail[1]:
                    payload = {
                        "template_name": marker,
                        "template_version": 1,
                        **payload,
                    }
                    break
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    return runner


def test_opencli_step_tracks_ai_note_as_independent_template_job(tmp_path):
    video = tmp_path / "20260720 ai-note-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    clock = [NOW]
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_ai_note_runner(video.name),
        now=lambda: clock[0],
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)
    job_id = prepared["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )

    triggered = service.advance_opencli(
        job_id, session="ticket02-ai-note", profile="work"
    )

    assert triggered["event"] == "netdisk_ai_note_triggered"
    assert triggered["status"] == "ai_note_requested"
    assert triggered["ai_note_template"] == "文稿笔记"
    assert triggered["ai_note_template_no"] == 1
    assert triggered["ai_note_completion_required"] is False
    assert triggered["ai_note_submission_proof"] == {
        "control_text": "生成该笔记",
        "click_dispatched": True,
        "modal_visible": False,
        "confirmed_state": "generating",
        "content_chars": 42,
        "reconciled_after_claim": False,
    }
    assert triggered["browser_evidence"]["page_url"] == (
        "https://pan.baidu.com/pfile/video"
    )
    assert "snapshot_text" not in triggered["browser_evidence"]


def test_ai_note_submission_clicks_real_modal_button_and_confirms_transition(
    tmp_path,
):
    video = tmp_path / "20260720 ai-note-final-click-compressed.mp4"
    video.write_bytes(b"real-video")
    commands = []
    base_runner = _opencli_ai_note_runner(video.name)

    def runner(command, **kwargs):
        commands.append(command)
        return base_runner(command, **kwargs)

    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=runner,
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )

    triggered = service.advance_opencli(
        job_id, session="ticket02-ai-note-click", profile="work"
    )

    eval_scripts = [
        command[6]
        for command in commands
        if len(command) > 6 and command[5] == "eval"
    ]
    assert not any("genNoteByTpl" in script for script in eval_scripts)
    assert any(
        "tplModal" in script
        and "contentDocument" in script
        and "生成该笔记" in script
        and ".click()" in script
        and "modal_visible" in script
        for script in eval_scripts
    )
    assert any("以下为AI生成的" in script for script in eval_scripts)
    assert triggered["browser_evidence"]["visible_state"] == "ai_note_generating"


def test_ai_note_submission_dispatch_does_not_wait_for_modal_transition(
    tmp_path,
):
    video = tmp_path / "20260720 ai-note-stuck-modal-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_ai_note_runner(
            video.name,
            submission_payload={
                "submitted": False,
                "template_no": 1,
                "target_bound": True,
                "button_matches": 1,
                "click_dispatched": True,
                "modal_visible": True,
                "confirmed_state": "generating",
                "content_chars": 42,
            },
        ),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )

    triggered = service.advance_opencli(
        job_id, session="ticket02-ai-note-stuck", profile="work"
    )

    assert triggered["status"] == "ai_note_requested"
    assert triggered["event"] == "netdisk_ai_note_triggered"
    assert triggered["ai_note_completion_required"] is False
    assert triggered["ai_note_submission_proof"]["click_dispatched"] is True
    assert triggered["ai_note_submission_proof"]["confirmed_state"] == (
        "dispatched"
    )


def test_ai_note_postclick_zero_recovery_submits_once_after_exact_zero_proof(
    tmp_path,
):
    video = tmp_path / "20260720 ai-note-postclick-zero-compressed.mp4"
    video.write_bytes(b"real-video")
    clock = [NOW]
    commands = []
    base_runner = _opencli_ai_note_runner(
        video.name,
        note_states=[{
            "ai_note_state": "missing",
            "active_tab": "笔记",
            "content_chars": 76,
            "template": "",
            "target_bound": True,
        }],
    )

    def runner(command, **kwargs):
        commands.append(command)
        return base_runner(command, **kwargs)

    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=runner,
        now=lambda: clock[0],
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    original = service.claim_browser_action(job_id, action="ai_note")
    clock[0] = NOW + timedelta(minutes=6)

    recovered = service.recover_ai_note_postclick_zero(
        job_id,
        session="ticket02-ai-note-zero",
        profile="work",
        operator_confirmed_no_click=True,
    )

    assert recovered["event"] == "netdisk_ai_note_triggered"
    assert recovered["status"] == "ai_note_requested"
    assert recovered["ai_note_trigger_attempt"] == 2
    assert recovered["ai_note_retry_of"] == original["claimed_at"]
    assert recovered["ai_note_recovery_kind"] == "stale_claim_exact_zero_effect"
    assert recovered["ai_note_operator_confirmed_no_click"] is True
    submit_scripts = [
        command[6]
        for command in commands
        if len(command) > 6
        and command[5] == "eval"
        and "baidu-netdisk/submit-ai-note" in command[6]
    ]
    assert len(submit_scripts) == 1


def test_ai_note_postclick_zero_recovery_rejects_recent_claim(tmp_path):
    video = tmp_path / "20260720 ai-note-postclick-recent-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_ai_note_runner(
            video.name,
            note_states=[{
                "ai_note_state": "missing",
                "active_tab": "笔记",
                "content_chars": 76,
                "template": "",
                "target_bound": True,
            }],
        ),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    service.claim_browser_action(job_id, action="ai_note")

    with pytest.raises(EnrichmentError, match="not old enough"):
        service.recover_ai_note_postclick_zero(
            job_id,
            session="ticket02-ai-note-recent",
            profile="work",
            operator_confirmed_no_click=True,
        )

    assert service.status(job_id)["ai_note_trigger_attempt"] == 1


def test_ai_note_pretrigger_failure_is_persisted_and_retried_once(tmp_path):
    video = tmp_path / "20260720 ai-note-pretrigger-retry-compressed.mp4"
    video.write_bytes(b"real-video")
    submit_calls = 0
    missing = {
        "ai_note_state": "missing",
        "active_tab": "笔记",
        "content_chars": 76,
        "template": "文稿笔记",
        "export_available": True,
        "target_bound": True,
    }
    base_runner = _opencli_ai_note_runner(
        video.name,
        note_states=[missing, missing],
    )

    def runner(command, **kwargs):
        nonlocal submit_calls
        if (
            len(command) > 6
            and command[5] == "eval"
            and "baidu-netdisk/submit-ai-note" in command[6]
        ):
            submit_calls += 1
            payload = (
                {
                    "submitted": False,
                    "template_no": 1,
                    "target_bound": True,
                    "button_matches": 0,
                    "click_dispatched": False,
                }
                if submit_calls == 1
                else {
                    "submitted": True,
                    "template_no": 1,
                    "target_bound": True,
                    "button_matches": 1,
                    "click_dispatched": True,
                    "modal_visible": False,
                    "confirmed_state": "generating",
                    "content_chars": 76,
                }
            )
            payload = {
                "template_name": "baidu-netdisk/submit-ai-note",
                "template_version": 1,
                **payload,
            }
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload, ensure_ascii=False),
                stderr="",
            )
        return base_runner(command, **kwargs)

    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=runner,
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )

    with pytest.raises(EnrichmentError, match="template submission failed"):
        service.advance_opencli(
            job_id,
            session="ticket02-ai-note-pretrigger",
            profile="work",
        )

    failed = service.status(job_id)
    assert failed["event"] == "netdisk_ai_note_pretrigger_failed"
    assert failed["status"] == "ai_note_pretrigger_failed"
    assert failed["ai_note_trigger_attempt"] == 1
    assert failed["ai_note_pretrigger_proof"] == {
        "button_matches": 0,
        "click_dispatched": False,
        "template_no": 1,
        "target_bound": True,
    }

    recovered = service.advance_opencli(
        job_id,
        session="ticket02-ai-note-pretrigger",
        profile="work",
    )

    assert recovered["event"] == "netdisk_ai_note_triggered"
    assert recovered["status"] == "ai_note_requested"
    assert recovered["ai_note_trigger_attempt"] == 2
    assert recovered["ai_note_retry_of"] == failed["claimed_at"]
    assert submit_calls == 2


def test_ai_note_pretrigger_retry_stops_after_two_unsubmitted_attempts(tmp_path):
    video = tmp_path / "20260720 ai-note-pretrigger-exhausted-compressed.mp4"
    video.write_bytes(b"real-video")
    submit_calls = 0
    missing = {
        "ai_note_state": "missing",
        "active_tab": "笔记",
        "content_chars": 76,
        "template": "文稿笔记",
        "export_available": True,
        "target_bound": True,
    }
    base_runner = _opencli_ai_note_runner(
        video.name,
        note_states=[missing, missing],
        submission_payload={
            "submitted": False,
            "template_no": 1,
            "target_bound": True,
            "button_matches": 0,
            "click_dispatched": False,
        },
    )

    def runner(command, **kwargs):
        nonlocal submit_calls
        if (
            len(command) > 6
            and command[5] == "eval"
            and "baidu-netdisk/submit-ai-note" in command[6]
        ):
            submit_calls += 1
        return base_runner(command, **kwargs)

    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=runner,
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )

    for _ in range(2):
        with pytest.raises(EnrichmentError, match="template submission failed"):
            service.advance_opencli(
                job_id,
                session="ticket02-ai-note-pretrigger",
                profile="work",
            )

    exhausted = service.advance_opencli(
        job_id,
        session="ticket02-ai-note-pretrigger",
        profile="work",
    )

    assert exhausted["status"] == "ai_note_pretrigger_failed"
    assert exhausted["ai_note_trigger_attempt"] == 2
    assert exhausted["retry_exhausted"] is True
    assert exhausted["idempotent_replay"] is True
    assert submit_calls == 2


def test_reconcile_legacy_ai_note_pretrigger_failure_requires_exact_cli_evidence(
    tmp_path,
):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    claim = service.claim_browser_action(job_id, action="ai_note")
    evidence = {
        "schema_version": 1,
        "job_id": job_id,
        "action": "ai_note",
        "claimed_at": claim["claimed_at"],
        "command": (
            "PYTHONPATH=src .venv/bin/python scripts/kol_netdisk_video.py "
            f"advance-opencli --job-id {job_id} "
            "--opencli-session ticket02-ai-note --opencli-profile work"
        ),
        "exit_code": 2,
        "error": "Netdisk AI-note template submission failed",
        "click_dispatched": False,
        "source_thread_id": "019fbd59-e55c-7582-8bf9-cb6eee578157",
        "source_turn_id": "019fc31b-516b-7642-9488-77a963a71ee1",
        "observed_at": NOW.isoformat(),
    }

    recovered = service.reconcile_ai_note_pretrigger_failure(
        job_id,
        evidence=evidence,
    )
    replay = service.reconcile_ai_note_pretrigger_failure(
        job_id,
        evidence=evidence,
    )

    assert recovered["event"] == "netdisk_ai_note_pretrigger_failed"
    assert recovered["status"] == "ai_note_pretrigger_failed"
    assert recovered["ai_note_trigger_attempt"] == 1
    assert recovered["reconciled_legacy_pretrigger"] is True
    assert recovered["ai_note_pretrigger_evidence_sha256"] == hashlib.sha256(
        (json.dumps(evidence, ensure_ascii=False, sort_keys=True) + "\n").encode()
    ).hexdigest()
    assert replay["idempotent_replay"] is True


def test_ai_note_claim_replay_captures_transcript_without_repeating_submission(
    tmp_path,
):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    service.claim_browser_action(job_id, action="ai_note")
    commands = []
    base_runner = _opencli_capture_runner(video.name)

    def reconcile_runner(command, **kwargs):
        commands.append(command)
        return base_runner(command, **kwargs)

    service.runner = reconcile_runner
    service.opencli_command = ("opencli",)
    replay = service.advance_opencli(
        job_id,
        session="ticket02-test",
    )

    assert replay["event"] == "netdisk_transcript_dom_captured"
    assert replay["status"] == "transcript_captured"
    assert replay["ai_note_completion_required"] is False
    assert replay["ai_note_submission_status"] == "claimed_non_gating"
    eval_scripts = [
        command[6]
        for command in commands
        if len(command) > 6 and command[5] == "eval"
    ]
    assert not any("baidu-netdisk/probe-ai-note" in script for script in eval_scripts)
    assert not any("previewTemplate" in script for script in eval_scripts)
    assert not any(
        "baidu-netdisk/submit-ai-note" in script
        for script in eval_scripts
    )


def test_ai_note_claim_replay_never_reads_ai_note_completion_state(
    tmp_path,
):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    service.claim_browser_action(job_id, action="ai_note")
    commands = []
    base_runner = _opencli_capture_runner(video.name)

    def reconcile_runner(command, **kwargs):
        commands.append(command)
        return base_runner(command, **kwargs)

    service.runner = reconcile_runner
    service.opencli_command = ("opencli",)
    replay = service.advance_opencli(
        job_id,
        session="ticket02-test",
    )

    assert replay["status"] == "transcript_captured"
    assert replay["ai_note_submission_status"] == "claimed_non_gating"
    eval_scripts = [
        command[6]
        for command in commands
        if len(command) > 6 and command[5] == "eval"
    ]
    assert not any("baidu-netdisk/probe-ai-note" in script for script in eval_scripts)
    assert not any("previewTemplate" in script for script in eval_scripts)
    assert not any(
        "baidu-netdisk/submit-ai-note" in script
        for script in eval_scripts
    )


def test_opencli_step_waits_for_semantic_tab_activation_before_probing(tmp_path):
    video = tmp_path / "20260720 tab-race-contract-compressed.mp4"
    video.write_bytes(b"real-video")
    commands = []
    base_runner = _opencli_ai_note_runner(video.name)

    def runner(command, **kwargs):
        commands.append(command)
        tail = command[5:] if len(command) > 5 else []
        if tail[:1] == ["eval"] and "expected_tab" in tail[1]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                        {
                            "active_tab": "笔记",
                            "expected_tab": "笔记",
                            "target_bound": True,
                            "video_count": 1,
                            "all_video_paused": True,
                            "pause_guard_installed": True,
                        },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        return base_runner(command, **kwargs)

    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=runner,
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)
    job_id = prepared["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )

    service.advance_opencli(job_id, session="ticket02-tab-race", profile="work")

    assert any(
        len(command) > 6
        and command[5] == "eval"
        and "expected_tab" in command[6]
        for command in commands
    )


def test_prepare_replay_returns_latest_state_instead_of_regressing(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    ready = service.record_browser_state(
        prepared["job_id"],
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在于 /课程/自己的课/小草"),
        source_mode="existing",
    )

    replay = service.prepare(video)

    assert ready["status"] == "video_ready"
    assert replay["status"] == "video_ready"
    assert replay["idempotent_replay"] is True
    assert len((tmp_path / "out" / "events.jsonl").read_text().splitlines()) == 2


def test_browser_evidence_is_sanitized_and_state_transitions_are_fail_closed(tmp_path):
    service, video, prepared = _prepare(tmp_path)

    with pytest.raises(EnrichmentError, match="transcript_claimed"):
        service.record_browser_state(
            prepared["job_id"],
            step="transcript_requested",
            evidence=_evidence(video.name, "文稿生成中"),
        )

    ready = service.record_browser_state(
        prepared["job_id"],
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    claimed = service.claim_browser_action(ready["job_id"], action="transcript")
    requested = service.record_browser_state(
        ready["job_id"],
        step="transcript_requested",
        evidence=_evidence(video.name, "文稿生成中"),
    )

    assert claimed["status"] == "transcript_claimed"
    assert requested["status"] == "transcript_requested"
    assert requested["browser_evidence"]["page_url"] == (
        "https://pan.baidu.com/pfile/video"
    )
    ledger = (tmp_path / "out" / "events.jsonl").read_text()
    assert "%2Ftarget.mp4" not in ledger


@pytest.mark.parametrize(
    ("page_url", "visible_state", "match"),
    [
        (
            "https://user:password@pan.baidu.com/disk/main",
            "文稿生成中",
            "page URL",
        ),
        (
            "https://pan.baidu.com/other",
            "文稿生成中",
            "page URL",
        ),
        (
            "https://pan.baidu.com/disk/main",
            "文稿生成中 BDUSS=must-not-persist",
            "secret material",
        ),
    ],
)
def test_browser_evidence_rejects_secret_or_wrong_page_data(
    tmp_path, page_url, visible_state, match
):
    service, video, prepared = _prepare(tmp_path)
    evidence = _evidence(video.name, visible_state)
    evidence["page_url"] = page_url

    with pytest.raises(EnrichmentError, match=match):
        service.record_browser_state(
            prepared["job_id"],
            step="video_ready",
            evidence=evidence,
            source_mode="existing",
        )

    assert "must-not-persist" not in (tmp_path / "out" / "events.jsonl").read_text()


def test_browser_evidence_binds_semantic_state_to_snapshot_content(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    service.record_browser_state(
        prepared["job_id"],
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.claim_browser_action(prepared["job_id"], action="transcript")
    evidence = _evidence(video.name, "文稿生成中")
    evidence["snapshot_text"] = f"{video.name}\nAI笔记 已生成"
    evidence["target_region_text"] = evidence["snapshot_text"]
    evidence["snapshot_sha256"] = hashlib.sha256(
        evidence["snapshot_text"].encode()
    ).hexdigest()

    with pytest.raises(EnrichmentError, match="does not prove"):
        service.record_browser_state(
            prepared["job_id"],
            step="transcript_requested",
            evidence=evidence,
        )


def test_player_and_file_list_states_require_their_real_page_paths(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    service.record_browser_state(
        prepared["job_id"],
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.claim_browser_action(prepared["job_id"], action="transcript")
    player_evidence = _evidence(video.name, "文稿生成中")
    player_evidence["page_url"] = "https://pan.baidu.com/disk/main"

    with pytest.raises(EnrichmentError, match="page URL"):
        service.record_browser_state(
            prepared["job_id"],
            step="transcript_requested",
            evidence=player_evidence,
        )

    file_list_dir = tmp_path / "file-list-path"
    file_list_dir.mkdir()
    second_service, second_video, second_prepared = _prepare(file_list_dir)
    file_list_evidence = _evidence(second_video.name, "目标视频已存在")
    file_list_evidence["page_url"] = "https://pan.baidu.com/pfile/video"
    with pytest.raises(EnrichmentError, match="page URL"):
        second_service.record_browser_state(
            second_prepared["job_id"],
            step="video_ready",
            evidence=file_list_evidence,
            source_mode="existing",
        )

    nested_file_list_evidence = _evidence(second_video.name, "目标视频已存在")
    nested_file_list_evidence["page_url"] = "https://pan.baidu.com/disk/main/anything"

    with pytest.raises(EnrichmentError, match="page URL"):
        second_service.record_browser_state(
            second_prepared["job_id"],
            step="video_ready",
            evidence=nested_file_list_evidence,
            source_mode="existing",
        )

    file_list_evidence["page_url"] = "https://pan.baidu.com/disk/main/other"
    with pytest.raises(EnrichmentError, match="page URL"):
        second_service.record_browser_state(
            second_prepared["job_id"],
            step="video_ready",
            evidence=file_list_evidence,
            source_mode="existing",
        )

    file_list_dir = tmp_path / "file-list"
    file_list_dir.mkdir()
    service, video, prepared = _prepare(file_list_dir)
    file_list_evidence = _evidence(video.name, "目标视频已存在")
    file_list_evidence["page_url"] = (
        "https://pan.baidu.com/pfile/video?path=%2Ftarget.mp4"
    )

    with pytest.raises(EnrichmentError, match="page URL"):
        service.record_browser_state(
            prepared["job_id"],
            step="video_ready",
            evidence=file_list_evidence,
            source_mode="existing",
        )


def test_existing_video_can_be_bound_from_its_exact_player_path(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    evidence = _evidence(video.name, "目标视频已存在")
    evidence["page_url"] = (
        "https://pan.baidu.com/pfile/video?path="
        + quote(f"/课程/自己的课/小草/{video.name}")
    )

    ready = service.record_browser_state(
        prepared["job_id"],
        step="video_ready",
        evidence=evidence,
        source_mode="existing",
    )

    assert ready["status"] == "video_ready"
    assert ready["browser_evidence"]["page_url"] == (
        "https://pan.baidu.com/pfile/video"
    )


def test_existing_cloud_children_reconcile_without_repeating_generation(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )

    with pytest.raises(EnrichmentError, match="transcript_requested"):
        service.record_browser_state(
            job_id,
            step="transcript_ready",
            evidence=_evidence(video.name, "文稿 已生成"),
        )

    transcript = service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    ai_note = service.record_browser_state(
        job_id,
        step="ai_note_ready",
        evidence=_evidence(video.name, "AI笔记 已生成"),
        reconcile_existing=True,
    )

    assert transcript["event"] == "netdisk_transcript_ready_reconciled"
    assert ai_note["event"] == "netdisk_ai_note_ready_reconciled"
    assert transcript["reconciled_from_status"] == "video_ready"
    assert ai_note["reconciled_from_status"] == "transcript_ready"
    ledger = (tmp_path / "out" / "events.jsonl").read_text()
    assert "transcript_claimed" not in ledger
    assert "ai_note_claimed" not in ledger


def test_opencli_existing_transcript_content_proves_ready_without_regeneration(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    evidence = _evidence(video.name, "文稿 已生成")
    snapshot_text = (
        f"{video.name}\n文稿 content_chars=3795 export_available 导出 复制"
    )
    evidence["snapshot_text"] = snapshot_text
    evidence["target_region_text"] = snapshot_text
    evidence["snapshot_sha256"] = hashlib.sha256(snapshot_text.encode()).hexdigest()

    ready = service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=evidence,
        reconcile_existing=True,
    )

    assert ready["status"] == "transcript_ready"
    assert ready["reconciled_existing"] is True
    assert "content_chars" not in json.dumps(ready)


def test_opencli_existing_ai_note_content_proves_ready_without_regeneration(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    evidence = _evidence(video.name, "AI笔记 已生成")
    snapshot_text = (
        f"{video.name}\nAI笔记 content_chars=1420 export_available note_path_bound"
    )
    evidence["snapshot_text"] = snapshot_text
    evidence["target_region_text"] = snapshot_text
    evidence["snapshot_sha256"] = hashlib.sha256(snapshot_text.encode()).hexdigest()

    ready = service.record_browser_state(
        job_id,
        step="ai_note_ready",
        evidence=evidence,
        reconcile_existing=True,
    )

    assert ready["status"] == "ai_note_ready"
    assert ready["reconciled_existing"] is True
    assert "content_chars" not in json.dumps(ready)


def _prepare_opencli_dom_capture(
    tmp_path: Path,
    *,
    virtualized: bool = False,
    with_ai_note: bool = False,
) -> tuple[NetdiskEnrichmentService, str]:
    video = tmp_path / "20260717 盘前大师班直播(7月17日)-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_capture_runner(video.name, virtualized=virtualized),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    prepared = service.prepare(video)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    if with_ai_note:
        service.record_browser_state(
            job_id,
            step="ai_note_ready",
            evidence=_evidence(video.name, "AI笔记 已生成"),
            reconcile_existing=True,
        )
    else:
        service.claim_browser_action(job_id, action="ai_note")
        service.record_browser_state(
            job_id,
            step="ai_note_requested",
            evidence=_evidence(video.name, "AI笔记生成中"),
        )
    return service, job_id


def test_opencli_dom_capture_materializes_complete_immutable_transcript(tmp_path):
    service, job_id = _prepare_opencli_dom_capture(tmp_path)

    captured = service.capture_opencli_transcript(
        job_id,
        session="ticket02-test",
    )

    transcript = Path(captured["transcript_path"])
    assert captured["event"] == "netdisk_transcript_dom_captured"
    assert captured["status"] == "transcript_captured"
    assert captured["transcript_acquisition"] == "opencli_dom"
    assert captured["dom_page_url"] == "https://pan.baidu.com/pfile/video"
    assert captured["dom_render_proof"]["scroll_top"] == 0
    assert captured["dom_render_proof"]["last_node_in_dom"] is True
    assert captured["dom_render_proof"]["last_node_below_viewport"] is True
    assert captured["dom_render_proof"]["virtual_or_loading_markers"] == []
    assert transcript.is_file()
    assert hashlib.sha256(transcript.read_bytes()).hexdigest() == captured[
        "transcript_sha256"
    ]
    ledger = (tmp_path / "out" / "events.jsonl").read_text()
    assert "开头明确说" not in ledger
    assert "access_token" not in ledger


def test_opencli_dom_capture_pauses_video_and_closes_exact_player_tab(tmp_path):
    commands: list[list[str]] = []
    video = tmp_path / "20260717 traffic-safe-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_capture_runner(video.name, command_log=commands),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    service.claim_browser_action(job_id, action="ai_note")
    service.record_browser_state(
        job_id,
        step="ai_note_requested",
        evidence=_evidence(video.name, "AI笔记生成中"),
    )

    captured = service.capture_opencli_transcript(
        job_id,
        session="ticket02-test",
    )

    assert captured["player_pause_receipt"]["all_video_paused"] is True
    assert captured["player_pause_receipt"]["pause_guard_installed"] is True
    assert captured["player_close_receipt"]["closed_page"] == "page-1"
    assert captured["player_close_receipt"]["closed_pages"] == ["page-1"]
    assert captured["player_close_receipt"]["exact_player_absent"] is True
    assert any(
        command[-2:-1] == ["eval"]
        and "__xiaocaoNetdiskPauseGuardV1" in command[-1]
        for command in commands
    )
    assert any(command[-3:] == ["tab", "close", "page-1"] for command in commands)
    assert commands[-2][-3:] == ["tab", "close", "page-1"]
    assert commands[-1][-2:] == ["tab", "list"]


def test_opencli_dom_capture_fails_closed_when_video_cannot_be_paused(tmp_path):
    service, job_id = _prepare_opencli_dom_capture(tmp_path)
    base_runner = service.runner
    commands: list[list[str]] = []

    def runner(command, **kwargs):
        commands.append(list(command))
        if (
            command[0] == "opencli"
            and command[-2:-1] == ["eval"]
            and "const guardKey = '__xiaocaoNetdiskPauseGuardV1'" in command[-1]
        ):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "target_bound": True,
                        "video_count": 1,
                        "playing_before_pause": 1,
                        "all_video_paused": False,
                        "pause_guard_installed": True,
                    }
                ),
                stderr="",
            )
        return base_runner(command, **kwargs)

    service.runner = runner

    with pytest.raises(EnrichmentError, match="not proven paused"):
        service.capture_opencli_transcript(job_id, session="ticket02-test")

    assert not any("ad_overlays_dismissed" in command[-1] for command in commands)
    assert not any(command[-3:-1] == ["tab", "close"] for command in commands)


def test_opencli_dom_capture_requires_ai_note_submission_state(tmp_path):
    video = tmp_path / "20260720 submission-gate-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_capture_runner(video.name),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )

    with pytest.raises(EnrichmentError, match="AI-note submission"):
        service.capture_opencli_transcript(job_id, session="ticket02-test")


def test_opencli_dom_capture_does_not_wait_on_uncertain_ai_note_claim(tmp_path):
    video = tmp_path / "20260720 non-gating-ai-note-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out",
        runner=_opencli_capture_runner(video.name),
        now=lambda: NOW,
        opencli_command=("opencli",),
    )
    job_id = service.prepare(video)["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
        reconcile_existing=True,
    )
    service.claim_browser_action(job_id, action="ai_note")

    captured = service.advance_opencli(
        job_id,
        session="ticket02-test",
    )

    assert captured["status"] == "transcript_captured"
    assert captured["ai_note_completion_required"] is False
    assert captured["ai_note_submission_status"] == "claimed_non_gating"


def test_opencli_capture_rejects_same_basename_in_wrong_directory_before_dom_mutation(
    tmp_path,
):
    service, job_id = _prepare_opencli_dom_capture(tmp_path)
    base_runner = service.runner
    capture_mutated = False

    def wrong_directory_runner(command, **kwargs):
        nonlocal capture_mutated
        if (
            command[0] == "opencli"
            and command[-2:-1] == ["eval"]
            and "current_url: location.href" in command[-1]
        ):
            name = service.status(job_id)["video_basename"]
            payload = {
                "current_url": "https://pan.baidu.com/pfile/video?path="
                + quote(f"/另一个目录/{name}")
            }
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload, ensure_ascii=False),
                stderr="",
            )
        if command[0] == "opencli" and "ad_overlays_dismissed" in command[-1]:
            capture_mutated = True
        return base_runner(command, **kwargs)

    service.runner = wrong_directory_runner
    with pytest.raises(EnrichmentError, match="prepared Netdisk path"):
        service.capture_opencli_transcript(job_id, session="ticket02-test")

    assert capture_mutated is False


def test_opencli_dom_capture_retries_one_transient_command_timeout(tmp_path):
    service, job_id = _prepare_opencli_dom_capture(tmp_path)
    base_runner = service.runner
    opencli_calls = 0

    def flaky_runner(command, **kwargs):
        nonlocal opencli_calls
        if command[0] == "opencli":
            opencli_calls += 1
            if opencli_calls == 1:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return base_runner(command, **kwargs)

    service.runner = flaky_runner
    captured = service.capture_opencli_transcript(
        job_id,
        session="ticket02-test",
    )

    assert captured["status"] == "transcript_captured"
    assert opencli_calls == 7


def test_opencli_dom_capture_rejects_virtualized_or_partial_render(tmp_path):
    service, job_id = _prepare_opencli_dom_capture(tmp_path, virtualized=True)

    with pytest.raises(EnrichmentError, match="fully rendered"):
        service.capture_opencli_transcript(
            job_id,
            session="ticket02-test",
        )

    status = service.status(job_id)
    assert status["event"] == "netdisk_dom_capture_failed"
    assert status["status"] == "ai_note_requested"
    assert status["reason"] == "partial_or_virtualized_transcript"

    service.runner = _opencli_capture_runner(status["video_basename"])
    recovered = service.capture_opencli_transcript(
        job_id,
        session="ticket02-test",
    )

    assert recovered["status"] == "transcript_captured"
    assert "reason" not in recovered
    assert "failure_stage" not in recovered
    assert "error_type" not in recovered


def test_ordered_transcript_segments_deduplicate_and_restore_source_order():
    first = "甲" * 90
    second = "乙" * 90
    terminal = "丙" * 90

    transcript, proof = _normalize_ordered_transcript_segments([
        {"index": 1, "paragraph_index": 0, "text": second},
        {"index": 0, "paragraph_index": 0, "text": first},
        {"index": 1, "paragraph_index": 0, "text": second},
        {"index": 2, "paragraph_index": 1, "text": terminal},
    ])

    assert transcript == first + second + "\n\n" + terminal
    assert proof["segment_first_index"] == 0
    assert proof["segment_terminal_index"] == 2
    assert proof["segment_count"] == 3
    assert proof["duplicate_segment_count"] == 1
    assert proof["ordered_by_index"] is True
    assert proof["observed_order_was_monotonic"] is False


@pytest.mark.parametrize(
    ("segments", "message"),
    (
        (
            [
                {"index": 0, "paragraph_index": 0, "text": "甲" * 90},
                {"index": 2, "paragraph_index": 1, "text": "乙" * 90},
                {"index": 3, "paragraph_index": 1, "text": "丙" * 90},
            ],
            "terminal coverage",
        ),
        (
            [
                {"index": 0, "paragraph_index": 0, "text": "甲" * 90},
                {"index": 0, "paragraph_index": 0, "text": "乙" * 90},
                {"index": 1, "paragraph_index": 1, "text": "丙" * 90},
            ],
            "conflicting duplicate",
        ),
    ),
)
def test_ordered_transcript_segments_fail_closed_on_ambiguous_coverage(
    segments,
    message,
):
    with pytest.raises(EnrichmentError, match=message):
        _normalize_ordered_transcript_segments(segments)


@pytest.mark.parametrize(
    "step",
    (
        "transcript_requested",
    ),
)
def test_reconcile_existing_rejects_non_reconcilable_states(tmp_path, step):
    service, video, prepared = _prepare(tmp_path)
    service.record_browser_state(
        prepared["job_id"],
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )

    with pytest.raises(EnrichmentError, match="cannot be reconciled"):
        service.record_browser_state(
            prepared["job_id"],
            step=step,
            evidence=_evidence(video.name, "文稿生成中"),
            reconcile_existing=True,
        )


def test_browser_evidence_rejects_unbound_snapshot_hash(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    evidence = _evidence(video.name, "目标视频已存在")
    evidence["snapshot_sha256"] = "a" * 64

    with pytest.raises(EnrichmentError, match="snapshot hash"):
        service.record_browser_state(
            prepared["job_id"],
            step="video_ready",
            evidence=evidence,
            source_mode="existing",
        )


def test_browser_evidence_rejects_target_name_embedded_in_another_row(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    evidence = _evidence(video.name, "目标视频已存在")
    evidence["target_region_text"] = f"backup-{video.name}\n目标视频已存在"
    evidence["snapshot_text"] = evidence["target_region_text"]
    evidence["snapshot_sha256"] = hashlib.sha256(
        evidence["snapshot_text"].encode()
    ).hexdigest()

    with pytest.raises(EnrichmentError, match="does not prove the target"):
        service.record_browser_state(
            prepared["job_id"],
            step="video_ready",
            evidence=evidence,
            source_mode="existing",
        )


def test_video_presence_needs_step_specific_dom_text(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    evidence = _evidence(video.name, "目标视频已存在")
    evidence["target_region_text"] = video.name
    evidence["snapshot_text"] = video.name
    evidence["snapshot_sha256"] = hashlib.sha256(video.name.encode()).hexdigest()

    with pytest.raises(EnrichmentError, match="does not prove the state"):
        service.record_browser_state(
            prepared["job_id"],
            step="video_ready",
            evidence=evidence,
            source_mode="existing",
        )


def test_dom_state_text_cannot_come_from_runtime_filename(tmp_path):
    video = tmp_path / "目标视频-row-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out", runner=_runner, now=lambda: NOW
    )
    prepared = service.prepare(video)
    evidence = _evidence(video.name, "目标视频已存在")
    evidence["target_region_text"] = video.name
    evidence["snapshot_text"] = video.name
    evidence["snapshot_sha256"] = hashlib.sha256(video.name.encode()).hexdigest()

    with pytest.raises(EnrichmentError, match="does not prove the state"):
        service.record_browser_state(
            prepared["job_id"],
            step="video_ready",
            evidence=evidence,
            source_mode="existing",
        )


def test_decision_completion_requires_explicit_no_trade_reason():
    result = {
        "status": "completed",
        "items": [{
            "notification": {"status": "delivered", "receipt": "receipt-1"},
            "book_kol_us": {
                "status": "no_trade",
                "book": "KOL-US",
                "paper_only": True,
                "reason": "  ",
            },
        }],
    }

    with pytest.raises(EnrichmentError, match="no_trade requires reason"):
        validate_decision_completion(result)


def test_decision_completion_requires_real_household_receipt():
    result = {
        "status": "completed",
        "items": [{
            "notification": {"status": "delivered"},
            "book_kol_us": {
                "status": "no_trade",
                "book": "KOL-US",
                "paper_only": True,
                "reason": "观点仅涉及 A 股。",
            },
        }],
    }

    with pytest.raises(EnrichmentError, match="receipt"):
        validate_decision_completion(result)


def test_decision_completion_rejects_non_object_provider_result():
    with pytest.raises(EnrichmentError, match="result is invalid"):
        validate_decision_completion(None)  # type: ignore[arg-type]


def test_full_browser_checkpoint_chain_reads_complete_dom_transcript(tmp_path):
    service, video, current = _prepare(tmp_path)
    job_id = current["job_id"]
    service.runner = _opencli_capture_runner(video.name)
    service.opencli_command = ("opencli",)
    service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(),
    )
    current = service.claim_browser_action(job_id, action="upload")
    current = service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "上传完成，目标视频行可见"),
        source_mode="uploaded",
    )
    current = service.claim_browser_action(job_id, action="transcript")
    current = service.record_browser_state(
        job_id,
        step="transcript_requested",
        evidence=_evidence(video.name, "文稿生成中"),
    )
    current = service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
    )
    current = service.claim_browser_action(job_id, action="ai_note")
    current = service.record_browser_state(
        job_id,
        step="ai_note_requested",
        evidence=_evidence(video.name, "AI笔记生成中"),
    )
    captured = service.advance_opencli(
        job_id,
        session="ticket02-test",
    )

    text = Path(captured["transcript_path"]).read_text(encoding="utf-8")
    assert current["status"] == "ai_note_requested"
    assert captured["status"] == "transcript_captured"
    assert captured["transcript_acquisition"] == "opencli_dom"
    assert "信通电子" in text
    assert captured["transcript_sha256"] == hashlib.sha256(
        Path(captured["transcript_path"]).read_bytes()
    ).hexdigest()

    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "video_sha256": captured["video_sha256"],
                "transcript_sha256": captured["transcript_sha256"],
                "checks": [
                        {
                            "position": "opening",
                            "excerpt": "市场连续下跌后可能修复",
                        "passed": True,
                    },
                    {
                            "position": "middle",
                            "excerpt": "信通电子、德明利和市场成交量",
                        "passed": True,
                    },
                    {
                            "position": "ending",
                            "excerpt": "商业航天没有企稳信号",
                        "passed": True,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    verified = service.verify_transcript(job_id, audit_path=audit_path)

    assert verified["status"] == "verified"
    assert verified["content_checks"] == ["ending", "middle", "opening"]

    malformed_bundle = tmp_path / "malformed-bundle.json"
    malformed_bundle.write_text('{"items":[null]}', encoding="utf-8")
    with pytest.raises(EnrichmentError, match="item must be a JSON object"):
        service.decide(
            job_id,
            bundle_path=malformed_bundle,
            decision_output_dir=tmp_path / "decisions",
            sender=lambda _title, _body: {"wecom": "ok"},
        )
    assert service.status(job_id)["failure_stage"] == "invalid_bundle_item"

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps({
            "items": [{"evidence_path": verified["transcript_path"]}],
        }),
        encoding="utf-8",
    )

    class Pipeline:
        def process(self, _bundle):
            return {
                "status": "completed",
                "items": [{
                    "notification": {
                        "status": "pending",
                        "idempotency_key": "notice-1",
                    },
                    "book_kol_us": {
                        "status": "no_trade",
                        "book": "KOL-US",
                        "paper_only": True,
                        "reason": "仅涉及 A 股。",
                    },
                }],
            }

        def deliver_wechat(self, result, *, sender):
            sender("title", "body")
            result["items"][0]["notification"].update({
                "status": "delivered",
                "receipt": "wecom-relay://ok/notice-1",
            })
            return {"status": "delivered"}

    class InvalidPipeline:
        def process(self, _bundle):
            return {"status": "completed", "items": 42}

    with pytest.raises(EnrichmentError, match="did not complete one item"):
        service.decide(
            job_id,
            bundle_path=bundle_path,
            decision_output_dir=tmp_path / "decisions",
            sender=lambda _title, _body: {"wecom": "ok"},
            pipeline=InvalidPipeline(),
        )
    assert service.status(job_id)["failure_stage"] == "process_result"

    decided = service.decide(
        job_id,
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        sender=lambda _title, _body: {"wecom": "ok"},
        pipeline=Pipeline(),
    )

    assert decided["status"] == "decided"
    assert decided["household_notification"]["status"] == "delivered"
    assert decided["book_kol_us"] == {
        "status": "no_trade",
        "book": "KOL-US",
        "paper_only": True,
        "reason": "仅涉及 A 股。",
    }


def test_decided_job_runs_one_claimed_message_revision_without_new_book_effect(
    tmp_path,
):
    service, _video, prepared = _prepare(tmp_path)
    transcript = tmp_path / "complete-transcript.txt"
    transcript.write_text("小草完整文稿" * 100, encoding="utf-8")
    transcript_sha = hashlib.sha256(transcript.read_bytes()).hexdigest()
    decision_output = tmp_path / "decisions"
    book_intent = {
        "decision": "no_trade",
        "reason": "本场仅涉及 A 股。",
    }
    book = BookKolUs(decision_output / "book_kol_us")
    book_key = book.resolve_identity(transcript_sha, book_intent)
    prior_book = book.route(
        book_intent,
        idempotency_key=book_key,
        evidence=str(transcript),
        evidence_context={
            "evidence_sha256": transcript_sha,
            "paper_intent_sha256": book.intent_fingerprint(book_intent),
        },
    )
    original_bundle = tmp_path / "bundle-v1.json"
    original_bundle.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "evidence_path": str(transcript),
                        "book_kol_us": book_intent,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    artifact_dir = (
        tmp_path / "out" / "artifacts" / str(prepared["job_id"])
    )
    assert not artifact_dir.exists()
    original_result = tmp_path / "prior-decision-result.json"
    original_result.write_text('{"status":"completed"}\n', encoding="utf-8")
    service.store.append(
        {
            **prepared,
            "event": "netdisk_decisions_completed",
            "status": "decided",
            "transcript_path": str(transcript),
            "transcript_sha256": transcript_sha,
            "decision_bundle_path": str(original_bundle),
            "decision_bundle_sha256": hashlib.sha256(
                original_bundle.read_bytes()
            ).hexdigest(),
            "decision_result_path": str(original_result),
            "decision_result_sha256": hashlib.sha256(
                original_result.read_bytes()
            ).hexdigest(),
            "household_notification": {
                "status": "delivered",
                "idempotency_key": "notice-v1",
                "receipt": "wecom-relay://ok/notice-v1",
            },
            "book_kol_us": prior_book,
        }
    )
    revision_bundle = tmp_path / "bundle-v2.json"
    revision_bundle.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "evidence_path": str(transcript),
                        "book_kol_us": book_intent,
                        "notification_revision": "v2-context-corrected",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    calls = {"process": 0, "send": 0}

    class RevisionPipeline:
        def process(self, _bundle):
            calls["process"] += 1
            return {
                "status": "completed",
                "items": [
                    {
                        "notification": {
                            "status": "pending",
                            "idempotency_key": "notice-v2",
                        },
                        "book_kol_us": {
                            **prior_book,
                            "idempotent_replay": True,
                        },
                        "idempotent_replay": False,
                    }
                ],
            }

        def deliver_wechat(self, result, *, sender):
            calls["send"] += 1
            sender("更正版", "KOL观点与系统拆解")
            result["items"][0]["notification"].update(
                {
                    "status": "delivered",
                    "receipt": "wecom-relay://ok/notice-v2",
                }
            )
            return {"status": "delivered"}

    pipeline = RevisionPipeline()
    first = service.decide(
        prepared["job_id"],
        bundle_path=revision_bundle,
        decision_output_dir=decision_output,
        sender=lambda _title, _body: {"wecom": "ok"},
        pipeline=pipeline,
    )
    replay = service.decide(
        prepared["job_id"],
        bundle_path=revision_bundle,
        decision_output_dir=decision_output,
        sender=lambda _title, _body: {"wecom": "ok"},
        pipeline=pipeline,
    )

    events = [
        row
        for row in service.store.read()
        if row.get("job_id") == prepared["job_id"]
    ]
    assert first["event"] == "netdisk_decision_revision_completed"
    assert first["new_external_side_effect_count"] == 1
    assert first["book_kol_us"]["idempotency_key"] == book_key
    assert Path(first["decision_result_path"]).name.startswith(
        "decision_result."
    )
    assert artifact_dir.is_dir()
    assert replay["idempotent_replay"] is True
    assert calls == {"process": 1, "send": 1}
    assert sum(
        row.get("event") == "netdisk_decision_revision_claimed"
        for row in events
    ) == 1
    assert sum(
        row.get("event") == "netdisk_decision_revision_completed"
        for row in events
    ) == 1
    assert len(
        (decision_output / "book_kol_us" / "decisions.jsonl")
        .read_text()
        .splitlines()
    ) == 1


def test_verification_failure_is_appended_without_audit_content(tmp_path):
    service, _video, prepared = _prepare(tmp_path)

    with pytest.raises(EnrichmentError, match="content audit not found"):
        service.verify_transcript(
            prepared["job_id"], audit_path=tmp_path / "secret-audit.json"
        )

    latest = service.status(prepared["job_id"])
    assert latest["event"] == "netdisk_content_verification_failed"
    assert latest["reason"] == "audit_not_found"
    ledger = (tmp_path / "out" / "events.jsonl").read_text()
    assert "secret-audit" not in ledger


def test_non_object_content_audit_fails_with_a_durable_event(tmp_path):
    service, job_id = _prepare_opencli_dom_capture(tmp_path)
    service.capture_opencli_transcript(job_id, session="ticket02-test")
    audit_path = tmp_path / "audit.json"
    audit_path.write_text("[]", encoding="utf-8")

    with pytest.raises(EnrichmentError, match="JSON object"):
        service.verify_transcript(job_id, audit_path=audit_path)

    latest = service.status(job_id)
    assert latest["event"] == "netdisk_content_verification_failed"
    assert latest["reason"] == "invalid_audit_shape"


def test_decision_input_failure_is_appended_without_bundle_contents(tmp_path):
    service, _video, prepared = _prepare(tmp_path)

    with pytest.raises(EnrichmentError, match="decision bundle not found"):
        service.decide(
            prepared["job_id"],
            bundle_path=tmp_path / "missing-household-bundle.json",
            decision_output_dir=tmp_path / "decisions",
            sender=lambda _title, _body: {"wecom": "ok"},
        )

    latest = service.status(prepared["job_id"])
    assert latest["event"] == "netdisk_decision_failed"
    assert latest["failure_stage"] == "bundle_not_found"
    ledger = (tmp_path / "out" / "events.jsonl").read_text()
    assert "missing-household-bundle" not in ledger


def test_claim_replay_stays_uncertain_until_real_page_evidence_arrives(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    ready = service.record_browser_state(
        prepared["job_id"],
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )

    first = service.claim_browser_action(ready["job_id"], action="transcript")
    replay = service.claim_browser_action(ready["job_id"], action="transcript")

    assert first["status"] == "transcript_claimed"
    assert replay["status"] == "transcript_claimed"
    assert replay["idempotent_replay"] is True
    assert len((tmp_path / "out" / "events.jsonl").read_text().splitlines()) == 3


def test_each_browser_policy_failure_observation_is_durable_without_advancing(tmp_path):
    service, _video, prepared = _prepare(tmp_path)

    failure = service.record_capability_failure(
        prepared["job_id"],
        surface="codex_in_app_browser",
        reason="browser_security_policy_denied",
    )
    repeated = service.record_capability_failure(
        prepared["job_id"],
        surface="codex_in_app_browser",
        reason="browser_security_policy_denied",
    )

    assert failure["event"] == "netdisk_capability_failed"
    assert failure["status"] == "prepared"
    assert repeated["idempotent_replay"] is False
    assert len((tmp_path / "out" / "events.jsonl").read_text().splitlines()) == 3


def test_browser_policy_failure_blocks_claim_until_fresh_liveness(tmp_path):
    service, _video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )

    with pytest.raises(EnrichmentError, match="fresh browser"):
        service.claim_browser_action(job_id, action="upload")

    liveness = service.record_browser_liveness(
        job_id,
        surface="codex_chrome",
        evidence=_liveness_evidence(observed_at=NOW + timedelta(seconds=1)),
    )
    claimed = service.claim_browser_action(job_id, action="upload")

    assert liveness["event"] == "netdisk_browser_liveness_ready"
    assert "snapshot_text" not in json.dumps(liveness)
    assert "#" not in liveness["browser_liveness"]["page_url"]
    assert claimed["status"] == "upload_claimed"


def test_opencli_liveness_recovers_from_codex_policy_denial(tmp_path):
    service, _video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )

    liveness = service.record_browser_liveness(
        job_id,
        surface="opencli",
        evidence=_liveness_evidence(observed_at=NOW + timedelta(seconds=1)),
    )
    claimed = service.claim_browser_action(job_id, action="upload")

    assert liveness["browser_surface"] == "opencli"
    assert liveness["browser_control_blocked"] is False
    assert claimed["status"] == "upload_claimed"


def test_remote_handoff_rechecks_exact_target_before_transcript_claim(
    tmp_path,
    monkeypatch,
):
    service = NetdiskEnrichmentService(tmp_path / "out", now=lambda: NOW)
    media_sha256 = "a" * 64
    job_id = f"kol-netdisk-{media_sha256[:16]}"
    video_basename = "target-compressed.mp4"
    service.store.append({
        "schema_version": 1,
        "event": "netdisk_remote_handoff_imported",
        "status": "video_ready",
        "provider": "baidu_consumer_page",
        "job_id": job_id,
        "netdisk_directory": "/课程/自己的课/小草",
        "netdisk_path": f"/课程/自己的课/小草/{video_basename}",
        "video_basename": video_basename,
        "video_sha256": media_sha256,
        "video_sha256_kind": "content_sha256",
        "video_size_bytes": 123456,
        "video_duration_seconds": 1800.5,
        "source_mode": "cloud_handoff",
        "large_payload_local_bytes": 0,
        "handoff_id": "b" * 64,
        "browser_control_blocked": True,
        "updated_at": (NOW - timedelta(seconds=1)).isoformat(),
    })
    calls: list[str] = []

    def inspect(**kwargs):
        assert kwargs == {
            "session": "remote-session",
            "profile": "work",
            "target_name": video_basename,
        }
        calls.append("inspect")
        return {
            "exact_count": 1,
            "target_index": 0,
            "observed_at": NOW,
        }

    def advance(job, *, session, profile):
        assert (job, session, profile) == (
            job_id,
            "remote-session",
            "work",
        )
        current = service.status(job_id)
        assert current["event"] == "netdisk_browser_liveness_ready"
        assert current["browser_control_blocked"] is False
        calls.append("advance")
        return {**current, "pending": True}

    monkeypatch.setattr(service, "_inspect_opencli_target", inspect)
    monkeypatch.setattr(service, "_advance_opencli_transcript", advance)

    result = service.advance_opencli(
        job_id,
        session="remote-session",
        profile="work",
    )

    assert result["pending"] is True
    assert calls == ["inspect", "advance"]


def test_transcript_ready_refreshes_stale_liveness_before_ai_note_claim(
    tmp_path,
    monkeypatch,
):
    service = NetdiskEnrichmentService(tmp_path / "out", now=lambda: NOW)
    media_sha256 = "c" * 64
    job_id = f"kol-netdisk-{media_sha256[:16]}"
    video_basename = "20260804-masterclass-compressed.mp4"
    service.store.append({
        "schema_version": 1,
        "event": "netdisk_transcript_ready",
        "status": "transcript_ready",
        "provider": "baidu_consumer_page",
        "job_id": job_id,
        "netdisk_directory": "/课程/自己的课/小草",
        "netdisk_path": f"/课程/自己的课/小草/{video_basename}",
        "video_basename": video_basename,
        "video_sha256": media_sha256,
        "video_sha256_kind": "content_sha256",
        "source_mode": "cloud_handoff",
        "large_payload_local_bytes": 0,
        "handoff_id": "d" * 64,
        "browser_control_blocked": False,
        "browser_evidence": {
            "observed_at": (NOW - timedelta(minutes=31)).isoformat(),
            "page_url": "https://pan.baidu.com/pfile/video",
            "snapshot_sha256": "e" * 64,
            "target_name": video_basename,
            "visible_state": "transcript_ready",
        },
        "updated_at": (NOW - timedelta(minutes=31)).isoformat(),
    })
    calls: list[str] = []

    def inspect(**kwargs):
        assert kwargs == {
            "session": "remote-session",
            "profile": "work",
            "target_name": video_basename,
        }
        calls.append("inspect")
        return {
            "exact_count": 1,
            "target_index": 0,
            "observed_at": NOW,
        }

    def advance(job, *, session, profile):
        assert (job, session, profile) == (
            job_id,
            "remote-session",
            "work",
        )
        current = service.status(job_id)
        assert current["event"] == "netdisk_browser_liveness_ready"
        claim = service.claim_browser_action(job_id, action="ai_note")
        calls.append("advance")
        return {**claim, "pending": True}

    monkeypatch.setattr(service, "_inspect_opencli_target", inspect)
    monkeypatch.setattr(service, "_advance_opencli_ai_note", advance)

    result = service.advance_opencli(
        job_id,
        session="remote-session",
        profile="work",
    )

    assert result["status"] == "ai_note_claimed"
    assert result["pending"] is True
    assert calls == ["inspect", "advance"]


def test_transcript_ready_keeps_fresh_liveness_without_folder_rescan(
    tmp_path,
    monkeypatch,
):
    service = NetdiskEnrichmentService(tmp_path / "out", now=lambda: NOW)
    media_sha256 = "f" * 64
    job_id = f"kol-netdisk-{media_sha256[:16]}"
    video_basename = "fresh-masterclass-compressed.mp4"
    service.store.append({
        "schema_version": 1,
        "event": "netdisk_transcript_ready",
        "status": "transcript_ready",
        "provider": "baidu_consumer_page",
        "job_id": job_id,
        "video_basename": video_basename,
        "video_sha256": media_sha256,
        "browser_control_blocked": False,
        "browser_evidence": {
            "observed_at": NOW.isoformat(),
            "page_url": "https://pan.baidu.com/pfile/video",
            "snapshot_sha256": "a" * 64,
            "target_name": video_basename,
            "visible_state": "transcript_ready",
        },
        "updated_at": NOW.isoformat(),
    })

    def unexpected_inspection(**_kwargs):
        raise AssertionError("fresh liveness must not rescan the folder")

    def advance(job, *, session, profile):
        assert (job, session, profile) == (
            job_id,
            "remote-session",
            None,
        )
        return {**service.status(job_id), "pending": True}

    monkeypatch.setattr(
        service,
        "_inspect_opencli_target",
        unexpected_inspection,
    )
    monkeypatch.setattr(service, "_advance_opencli_ai_note", advance)

    result = service.advance_opencli(job_id, session="remote-session")

    assert result["status"] == "transcript_ready"
    assert result["pending"] is True


def test_repeated_policy_failure_after_recovery_blocks_again(tmp_path):
    service, _video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )
    service.record_browser_liveness(
        job_id,
        surface="codex_chrome",
        evidence=_liveness_evidence(observed_at=NOW + timedelta(seconds=1)),
    )
    repeated = service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )

    assert repeated["idempotent_replay"] is False
    with pytest.raises(EnrichmentError, match="fresh browser"):
        service.claim_browser_action(job_id, action="upload")


def test_policy_denial_remains_blocking_across_repeated_rejected_claims(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )

    for _ in range(2):
        with pytest.raises(EnrichmentError, match="fresh browser"):
            service.claim_browser_action(job_id, action="transcript")

    assert service.status(job_id)["browser_control_blocked"] is True


def test_liveness_before_latest_policy_denial_cannot_restore_control(tmp_path):
    service, _video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )

    with pytest.raises(EnrichmentError, match="post-date"):
        service.record_browser_liveness(
            job_id,
            surface="codex_chrome",
            evidence=_liveness_evidence(observed_at=NOW - timedelta(seconds=1)),
        )

    assert service.status(job_id)["event"] == "netdisk_capability_failed"


def test_same_repeated_denial_refreshes_causal_cutoff(tmp_path):
    video = tmp_path / "20260717 盘前大师班直播(7月17日)-compressed.mp4"
    video.write_bytes(b"real-video")
    clock = [NOW]
    service = NetdiskEnrichmentService(
        tmp_path / "out", runner=_runner, now=lambda: clock[0]
    )
    prepared = service.prepare(video)
    job_id = prepared["job_id"]
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )
    between_denials = _liveness_evidence(
        observed_at=NOW + timedelta(seconds=1)
    )
    clock[0] = NOW + timedelta(seconds=2)
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )

    with pytest.raises(EnrichmentError, match="post-date"):
        service.record_browser_liveness(
            job_id,
            surface="codex_chrome",
            evidence=between_denials,
        )

    failures = [
        row
        for row in service.store.read()
        if row.get("event") == "netdisk_capability_failed"
    ]
    assert len(failures) == 2
    assert failures[-1]["updated_at"] == (NOW + timedelta(seconds=2)).isoformat(
        timespec="microseconds"
    )


def test_page_evidence_before_latest_policy_denial_cannot_restore_control(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_capability_failure(
        job_id,
        surface="codex_chrome",
        reason="browser_security_policy_denied",
    )
    stale_video = _evidence(video.name, "目标视频已存在")
    stale_video["observed_at"] = (NOW - timedelta(seconds=1)).isoformat()

    with pytest.raises(EnrichmentError, match="post-date"):
        service.record_browser_state(
            job_id,
            step="video_ready",
            evidence=stale_video,
            source_mode="existing",
        )

    assert service.status(job_id)["browser_control_blocked"] is True


def test_transition_evidence_cannot_predate_its_claim_or_predecessor(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="codex_chrome",
        evidence=_liveness_evidence(),
    )
    service.claim_browser_action(job_id, action="upload")
    stale_video = _evidence(video.name, "上传完成，目标视频行可见")
    stale_video["observed_at"] = (NOW - timedelta(seconds=1)).isoformat()

    with pytest.raises(EnrichmentError, match="predates its upload claim"):
        service.record_browser_state(
            job_id,
            step="video_ready",
            evidence=stale_video,
            source_mode="uploaded",
        )

    assert service.status(job_id)["status"] == "upload_claimed"


def test_same_second_preclaim_evidence_is_rejected_with_microsecond_precision(
    tmp_path,
):
    claim_time = NOW + timedelta(microseconds=900_000)
    video = tmp_path / "20260717 盘前大师班直播(7月17日)-compressed.mp4"
    video.write_bytes(b"real-video")
    service = NetdiskEnrichmentService(
        tmp_path / "out", runner=_runner, now=lambda: claim_time
    )
    prepared = service.prepare(video)
    job_id = prepared["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="codex_chrome",
        evidence=_liveness_evidence(observed_at=claim_time),
    )
    service.claim_browser_action(job_id, action="upload")
    stale_video = _evidence(video.name, "上传完成，目标视频行可见")
    stale_video["observed_at"] = (
        NOW + timedelta(microseconds=100_000)
    ).isoformat(timespec="microseconds")

    with pytest.raises(EnrichmentError, match="predates its upload claim"):
        service.record_browser_state(
            job_id,
            step="video_ready",
            evidence=stale_video,
            source_mode="uploaded",
        )
