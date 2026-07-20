from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from xiaocao.kol.enrichment import EnrichmentError
from xiaocao.kol.enrichment_types import validate_decision_completion
from xiaocao.kol.netdisk_enrichment import NetdiskEnrichmentService


NOW = datetime.fromisoformat("2026-07-20T09:00:00+08:00")


def _runner(command, **_kwargs):
    if command[0] == "ffprobe":
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"format": {"duration": "2192.547945"}}),
            stderr="",
        )
    if command[0] == "textutil":
        text = (
            "开头明确说今天不要追高，先等待。"
            + "中间讨论机器人产业链与北特科技，数字目标是四十。" * 20
            + "结尾再次强调若成交量不放大就不交易。"
        )
        return SimpleNamespace(returncode=0, stdout=text, stderr="")
    raise AssertionError(command)


def _opencli_capture_runner(
    video_name: str,
    *,
    virtualized: bool = False,
):
    transcript = (
        "开头明确说市场连续下跌后可能修复，但仓位必须很轻。\n\n"
        + "中段讨论信通电子、德明利和市场成交量，强调触发与风险。" * 20
        + "\n\n结尾明确说商业航天没有企稳信号，当前不参与。"
    )

    def runner(command, **kwargs):
        if command[0] == "ffprobe":
            return _runner(command, **kwargs)
        if command[:3] != ["opencli", "browser", "ticket02-test"]:
            raise AssertionError(command)
        tail = command[3:]
        if len(tail) == 2 and tail[0] == "eval" and "url: location.href" in tail[1]:
            payload = {
                "url": (
                    "https://pan.baidu.com/pfile/video?path="
                    f"%2F%E8%AF%BE%E7%A8%8B%2F{video_name}"
                ),
                "active": {"matches": 1, "text": "文稿"},
                "transcript": {"text": transcript},
                "render": {
                    "list_matches": 1,
                    "scroll_top": 0,
                    "client_height": 555,
                    "scroll_height": 3997,
                    "paragraph_count": 8,
                    "sentence_count": 80,
                    "list_text_chars": len(transcript.strip()),
                    "sentence_text_chars": len(transcript.replace("\n", "")),
                    "last_node_in_dom": True,
                    "last_node_below_viewport": True,
                    "virtual_or_loading_markers": (
                        ["virtual-list"] if virtualized else []
                    ),
                    "has_load_more": False,
                },
            }
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
        "文稿 已导出": "transcript_exported",
        "同名文稿已在当前网盘目录中可见": "cloud_document_present",
        "同名文稿可见": "cloud_document_present",
        "同名文稿下载已开始": "download_started",
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
        "transcript_exported",
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


def _liveness_evidence(*, observed_at: datetime = NOW) -> dict:
    snapshot_text = "百度网盘 /课程/自己的课/小草 文件列表"
    return {
        "page_url": "https://pan.baidu.com/disk/main#/index?category=all",
        "snapshot_text": snapshot_text,
        "snapshot_sha256": hashlib.sha256(snapshot_text.encode()).hexdigest(),
        "observed_at": observed_at.isoformat(),
    }


def _advance_to_download_requested(
    service: NetdiskEnrichmentService, video: Path, job_id: str
) -> None:
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    for action, requested_step, ready_step, requested_text, ready_text in (
        ("transcript", "transcript_requested", "transcript_ready", "文稿生成中", "文稿 已生成"),
        ("ai_note", "ai_note_requested", "ai_note_ready", "AI笔记生成中", "AI笔记 已生成"),
    ):
        service.claim_browser_action(job_id, action=action)
        service.record_browser_state(
            job_id, step=requested_step, evidence=_evidence(video.name, requested_text)
        )
        service.record_browser_state(
            job_id, step=ready_step, evidence=_evidence(video.name, ready_text)
        )
    service.claim_browser_action(job_id, action="export")
    service.record_browser_state(
        job_id,
        step="export_ready",
        evidence=_evidence(video.name, "文稿 已导出"),
    )
    document_name = f"{video.stem}.doc"
    service.record_browser_state(
        job_id,
        step="cloud_document_ready",
        evidence=_evidence(document_name, "同名文稿已在当前网盘目录中可见"),
    )
    service.claim_browser_action(job_id, action="download")
    service.record_browser_state(
        job_id,
        step="download_requested",
        evidence=_evidence(document_name, "同名文稿下载已开始"),
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
    return service, job_id


def test_opencli_dom_capture_materializes_complete_immutable_transcript(tmp_path):
    service, job_id = _prepare_opencli_dom_capture(tmp_path)

    captured = service.capture_opencli_transcript(
        job_id,
        session="ticket02-test",
    )

    transcript = Path(captured["transcript_path"])
    assert captured["event"] == "netdisk_transcript_dom_captured"
    assert captured["status"] == "downloaded"
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


def test_legacy_export_compatibility_does_not_require_ai_note(tmp_path):
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

    claimed = service.claim_browser_action(job_id, action="export")

    assert claimed["status"] == "export_claimed"


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

    assert captured["status"] == "downloaded"
    assert opencli_calls == 2


def test_opencli_dom_capture_rejects_virtualized_or_partial_render(tmp_path):
    service, job_id = _prepare_opencli_dom_capture(tmp_path, virtualized=True)

    with pytest.raises(EnrichmentError, match="fully rendered"):
        service.capture_opencli_transcript(
            job_id,
            session="ticket02-test",
        )

    status = service.status(job_id)
    assert status["event"] == "netdisk_dom_capture_failed"
    assert status["status"] == "transcript_ready"
    assert status["reason"] == "partial_or_virtualized_transcript"

    service.runner = _opencli_capture_runner(status["video_basename"])
    recovered = service.capture_opencli_transcript(
        job_id,
        session="ticket02-test",
    )

    assert recovered["status"] == "downloaded"
    assert "reason" not in recovered
    assert "failure_stage" not in recovered
    assert "error_type" not in recovered


@pytest.mark.parametrize(
    "step",
    (
        "transcript_requested",
        "export_ready",
        "cloud_document_ready",
        "download_requested",
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


def test_full_browser_checkpoint_chain_imports_and_reads_downloaded_word(tmp_path):
    service, video, current = _prepare(tmp_path)
    job_id = current["job_id"]
    service.record_browser_liveness(
        job_id,
        surface="codex_chrome",
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
    current = service.record_browser_state(
        job_id,
        step="ai_note_ready",
        evidence=_evidence(video.name, "AI笔记 已生成"),
    )
    current = service.claim_browser_action(job_id, action="export")
    current = service.record_browser_state(
        job_id,
        step="export_ready",
        evidence=_evidence(video.name, "文稿 已导出"),
    )
    document_name = f"{video.stem}.doc"
    current = service.record_browser_state(
        job_id,
        step="cloud_document_ready",
        evidence=_evidence(document_name, "同名文稿已在当前网盘目录中可见"),
    )
    current = service.claim_browser_action(job_id, action="download")
    current = service.record_browser_state(
        job_id,
        step="download_requested",
        evidence=_evidence(document_name, "同名文稿下载已开始"),
    )
    downloaded = tmp_path / f"{video.stem}.doc"
    downloaded.write_bytes(b"word-container")
    os.utime(downloaded, (NOW.timestamp(), NOW.timestamp()))
    imported = service.import_transcript_download(job_id, downloaded)

    text = Path(imported["transcript_path"]).read_text(encoding="utf-8")
    assert current["status"] == "download_requested"
    assert imported["status"] == "downloaded"
    assert imported["download_sha256"] == hashlib.sha256(
        b"word-container"
    ).hexdigest()
    assert "北特科技" in text
    assert imported["transcript_sha256"] == hashlib.sha256(
        Path(imported["transcript_path"]).read_bytes()
    ).hexdigest()

    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "video_sha256": imported["video_sha256"],
                "transcript_sha256": imported["transcript_sha256"],
                "checks": [
                    {
                        "position": "opening",
                        "excerpt": "不要追高",
                        "passed": True,
                    },
                    {
                        "position": "middle",
                        "excerpt": "数字目标是四十",
                        "passed": True,
                    },
                    {
                        "position": "ending",
                        "excerpt": "成交量不放大就不交易",
                        "passed": True,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    verified = service.verify_download(job_id, audit_path=audit_path)

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


def test_download_is_blocked_until_exported_cloud_document_is_visible(tmp_path):
    service, video, current = _prepare(tmp_path)
    job_id = current["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    service.claim_browser_action(job_id, action="transcript")
    service.record_browser_state(
        job_id,
        step="transcript_requested",
        evidence=_evidence(video.name, "文稿生成中"),
    )
    service.record_browser_state(
        job_id,
        step="transcript_ready",
        evidence=_evidence(video.name, "文稿 已生成"),
    )

    service.claim_browser_action(job_id, action="ai_note")
    service.record_browser_state(
        job_id,
        step="ai_note_requested",
        evidence=_evidence(video.name, "AI笔记生成中"),
    )
    service.record_browser_state(
        job_id,
        step="ai_note_ready",
        evidence=_evidence(video.name, "AI笔记 已生成"),
    )

    with pytest.raises(EnrichmentError, match="cloud_document_ready"):
        service.claim_browser_action(job_id, action="download")


def test_import_is_blocked_until_real_download_was_started(tmp_path):
    service, video, current = _prepare(tmp_path)
    job_id = current["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    for action, requested_step, ready_step, requested_text, ready_text in (
        ("transcript", "transcript_requested", "transcript_ready", "文稿生成中", "文稿 已生成"),
        ("ai_note", "ai_note_requested", "ai_note_ready", "AI笔记生成中", "AI笔记 已生成"),
    ):
        service.claim_browser_action(job_id, action=action)
        service.record_browser_state(
            job_id,
            step=requested_step,
            evidence=_evidence(video.name, requested_text),
        )
        service.record_browser_state(
            job_id,
            step=ready_step,
            evidence=_evidence(video.name, ready_text),
        )
    service.claim_browser_action(job_id, action="export")
    service.record_browser_state(
        job_id,
        step="export_ready",
        evidence=_evidence(video.name, "文稿 已导出"),
    )
    document_name = f"{video.stem}.doc"
    service.record_browser_state(
        job_id,
        step="cloud_document_ready",
        evidence=_evidence(document_name, "同名文稿已在当前网盘目录中可见"),
    )
    service.claim_browser_action(job_id, action="download")
    downloaded = tmp_path / document_name
    downloaded.write_bytes(b"word-container")

    with pytest.raises(EnrichmentError, match="download_requested"):
        service.import_transcript_download(job_id, downloaded)


@pytest.mark.parametrize(
    ("filename", "mtime", "match", "reason"),
    [
        (
            "20260717 盘前大师班直播(7月17日)-compressed-old.doc",
            NOW.timestamp(),
            "exactly match",
            "basename_mismatch",
        ),
        (
            "20260717 盘前大师班直播(7月17日)-compressed.doc",
            NOW.timestamp() - 30,
            "not fresh",
            "stale_or_future_file",
        ),
    ],
)
def test_download_import_rejects_unbound_local_files(
    tmp_path, filename, mtime, match, reason
):
    service, video, prepared = _prepare(tmp_path)
    _advance_to_download_requested(service, video, prepared["job_id"])
    downloaded = tmp_path / filename
    downloaded.write_bytes(b"word-container")
    os.utime(downloaded, (mtime, mtime))

    with pytest.raises(EnrichmentError, match=match):
        service.import_transcript_download(prepared["job_id"], downloaded)

    latest = service.status(prepared["job_id"])
    assert latest["event"] == "netdisk_download_import_failed"
    assert latest["status"] == "download_requested"
    assert latest["reason"] == reason


def test_verification_failure_is_appended_without_audit_content(tmp_path):
    service, _video, prepared = _prepare(tmp_path)

    with pytest.raises(EnrichmentError, match="content audit not found"):
        service.verify_download(
            prepared["job_id"], audit_path=tmp_path / "secret-audit.json"
        )

    latest = service.status(prepared["job_id"])
    assert latest["event"] == "netdisk_content_verification_failed"
    assert latest["reason"] == "audit_not_found"
    ledger = (tmp_path / "out" / "events.jsonl").read_text()
    assert "secret-audit" not in ledger


def test_non_object_content_audit_fails_with_a_durable_event(tmp_path):
    service, video, prepared = _prepare(tmp_path)
    _advance_to_download_requested(service, video, prepared["job_id"])
    downloaded = tmp_path / f"{video.stem}.doc"
    downloaded.write_bytes(b"word-container")
    os.utime(downloaded, (NOW.timestamp(), NOW.timestamp()))
    service.import_transcript_download(prepared["job_id"], downloaded)
    audit_path = tmp_path / "audit.json"
    audit_path.write_text("[]", encoding="utf-8")

    with pytest.raises(EnrichmentError, match="JSON object"):
        service.verify_download(prepared["job_id"], audit_path=audit_path)

    latest = service.status(prepared["job_id"])
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


def test_cloud_document_evidence_requires_exact_generated_doc_name(tmp_path):
    service, video, current = _prepare(tmp_path)
    job_id = current["job_id"]
    service.record_browser_state(
        job_id,
        step="video_ready",
        evidence=_evidence(video.name, "目标视频已存在"),
        source_mode="existing",
    )
    for action, requested_step, ready_step, requested_text, ready_text in (
        ("transcript", "transcript_requested", "transcript_ready", "文稿生成中", "文稿 已生成"),
        ("ai_note", "ai_note_requested", "ai_note_ready", "AI笔记生成中", "AI笔记 已生成"),
    ):
        service.claim_browser_action(job_id, action=action)
        service.record_browser_state(
            job_id,
            step=requested_step,
            evidence=_evidence(video.name, requested_text),
        )
        service.record_browser_state(
            job_id,
            step=ready_step,
            evidence=_evidence(video.name, ready_text),
        )
    service.claim_browser_action(job_id, action="export")
    service.record_browser_state(
        job_id,
        step="export_ready",
        evidence=_evidence(video.name, "文稿 已导出"),
    )

    with pytest.raises(EnrichmentError, match="target does not match"):
        service.record_browser_state(
            job_id,
            step="cloud_document_ready",
            evidence=_evidence(f"wrong-{video.stem}.doc", "同名文稿可见"),
        )

    document_name = f"{video.stem}.doc"
    evidence = _evidence(document_name, "同名文稿可见")
    evidence["target_region_text"] = document_name
    evidence["snapshot_text"] = document_name
    evidence["snapshot_sha256"] = hashlib.sha256(document_name.encode()).hexdigest()
    with pytest.raises(EnrichmentError, match="does not prove the state"):
        service.record_browser_state(
            job_id,
            step="cloud_document_ready",
            evidence=evidence,
        )


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


def test_cloud_document_evidence_cannot_predate_current_export(tmp_path):
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
    service.record_browser_state(
        job_id,
        step="ai_note_ready",
        evidence=_evidence(video.name, "AI笔记 已生成"),
        reconcile_existing=True,
    )
    service.claim_browser_action(job_id, action="export")
    service.record_browser_state(
        job_id,
        step="export_ready",
        evidence=_evidence(video.name, "文稿 已导出"),
    )
    document_name = f"{video.stem}.doc"
    stale_document = _evidence(
        document_name, "同名文稿已在当前网盘目录中可见"
    )
    stale_document["observed_at"] = (NOW - timedelta(seconds=1)).isoformat()

    with pytest.raises(EnrichmentError, match="predecessor browser evidence"):
        service.record_browser_state(
            job_id,
            step="cloud_document_ready",
            evidence=stale_document,
        )

    assert service.status(job_id)["status"] == "export_ready"
