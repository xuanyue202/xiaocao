from __future__ import annotations

import io
import json
from base64 import urlsafe_b64encode

import pytest

from xiaocao.kol.capture import (
    CaptureJobStore,
    InvalidSourcePage,
    SnifferClient,
    bind_recorded_media_url,
    canonical_xiaoetong_source,
    resolve_xiaoetong_h5_page,
    resolve_candidate,
)
from xiaocao.kol.capture import InvalidCheckpoint


class _Response:
    def __init__(self, value):
        self.body = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


def test_arm_then_detects_only_unseen_live_id(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    armed = store.arm([{"id": "old-a", "live_id": "live-old"}])

    assert store.detect_capture(armed, [{"id": "old-b", "live_id": "live-old"}]) is None

    detected = store.detect_capture(
        armed,
        [
            {"id": "old-b", "live_id": "live-old"},
            {"id": "new", "live_id": "live-new", "captured": "2026-07-19 12:00:00"},
        ],
    )
    assert detected is not None
    assert detected["status"] == "captured"
    assert detected["candidate_key"] == "live:live-new"
    assert "url" not in detected["candidate"]
    assert store.latest(armed["job_id"])["event"] == "capture_detected"


def test_arm_persists_sniffer_status(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    armed = store.arm([], sniffer_status={"proxy_port": 2023, "running": True})

    assert armed["sniffer_status"]["running"] is True
    assert store.latest(armed["job_id"])["sniffer_status"]["proxy_port"] == 2023


def test_xiaoetong_source_identity_strips_share_and_signed_state():
    source = canonical_xiaoetong_source(
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/alive/"
        "l_6a6c475be4b0694c5bf2605b?share_user_id=private&share_type=5"
    )

    assert source == {
        "source_kind": "xiaoetong",
        "source_host": "appsnm3rlcp3566.h5.xiaoeknow.com",
        "source_app_id": "appsnm3rlcp3566",
        "source_resource_id": "l_6a6c475be4b0694c5bf2605b",
        "source_identity": (
            "xiaoetong:appsnm3rlcp3566:l_6a6c475be4b0694c5bf2605b"
        ),
    }
    assert "share_user_id" not in json.dumps(source)
    assert "url" not in json.dumps(source).lower()


def test_xiaoetong_recorded_video_source_identity_is_stable():
    source = canonical_xiaoetong_source(
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/"
        "v_6a7db774e4b0694c5bfa7583?share_user_id=private&share_type=5"
    )

    assert source == {
        "source_kind": "xiaoetong",
        "source_host": "appsnm3rlcp3566.h5.xiaoeknow.com",
        "source_app_id": "appsnm3rlcp3566",
        "source_resource_id": "v_6a7db774e4b0694c5bfa7583",
        "source_identity": (
            "xiaoetong:appsnm3rlcp3566:v_6a7db774e4b0694c5bfa7583"
        ),
    }


def test_xiaoetong_mp_wrapper_resolves_bound_h5_page():
    params = urlsafe_b64encode(json.dumps({
        "app_id": "appsnm3rlcp3566",
        "resource_id": "l_6a699f8ce4b0694c5bf12013",
        "h5_url": (
            "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/alive/"
            "l_6a699f8ce4b0694c5bf12013?share_user_id=private&share_type=5"
        ),
    }).encode()).decode().rstrip("=")
    wrapper = (
        "https://appsnm3rlcp3566.mp.xiaoeknow.com/"
        f"?app_id=appsnm3rlcp3566&params={params}"
    )

    assert resolve_xiaoetong_h5_page(wrapper) == (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/alive/"
        "l_6a699f8ce4b0694c5bf12013"
    )
    assert canonical_xiaoetong_source(
        resolve_xiaoetong_h5_page(wrapper)
    )["source_identity"] == (
        "xiaoetong:appsnm3rlcp3566:l_6a699f8ce4b0694c5bf12013"
    )


def test_xiaoetong_mp_wrapper_rejects_cross_app_h5_page():
    params = urlsafe_b64encode(json.dumps({
        "app_id": "appsnm3rlcp3566",
        "resource_id": "l_target",
        "h5_url": "https://attacker.h5.xiaoeknow.com/v2/course/alive/l_target",
    }).encode()).decode().rstrip("=")

    try:
        resolve_xiaoetong_h5_page(
            "https://appsnm3rlcp3566.mp.xiaoeknow.com/"
            f"?app_id=appsnm3rlcp3566&params={params}"
        )
    except InvalidSourcePage:
        pass
    else:
        raise AssertionError("cross-app Xiaoetong wrapper was accepted")


def test_xiaoetong_source_identity_rejects_untrusted_page():
    for page_url in (
        "https://example.test/v4/course/alive/l_123",
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/not-a-course/l_123",
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/l_123",
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/alive/v_123",
        "javascript:alert(1)",
    ):
        try:
            canonical_xiaoetong_source(page_url)
        except InvalidSourcePage:
            pass
        else:
            raise AssertionError(f"untrusted source page accepted: {page_url}")


def test_arm_binds_expected_xiaoetong_source_and_filters_other_candidates(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    source = canonical_xiaoetong_source(
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/alive/l_target"
    )
    armed = store.arm([], expected_source=source, source_job_id="source-1")

    assert armed["expected_source"] == source
    assert armed["source_job_id"] == "source-1"
    assert store.detect_capture(
        armed,
        [{"id": "other", "live_id": "l_other", "captured": "2026-08-03 10:00:00"}],
    ) is None
    detected = store.detect_capture(
        armed,
        [{"id": "target", "live_id": "l_target", "captured": "2026-08-03 10:01:00"}],
    )
    assert detected is not None
    assert detected["candidate_key"] == "live:l_target"
    assert "http" not in (tmp_path / "jobs.jsonl").read_text(encoding="utf-8")


def test_recorded_video_capture_uses_file_binding_not_stale_live_context(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    source = canonical_xiaoetong_source(
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/"
        "v_6a7db774e4b0694c5bfa7583"
    )
    old = {
        "id": "candidate-before-arm",
        "live_id": "l_stale_context",
        "url": (
            "https://encrypt-k-vod.xet.tech/vod/"
            "773e679a5001834815942190711/drm/v.f421220.m3u8"
        ),
    }
    armed = store.arm(
        [old],
        expected_source=source,
        expected_media_file_id="5001834815942190711",
    )

    detected = store.detect_capture(
        armed,
        [
            old,
            {
                "id": "candidate-other-video",
                "live_id": "l_stale_context",
                "url": (
                    "https://encrypt-k-vod.xet.tech/vod/"
                    "773e679a5001834815000000000/drm/v.f421220.m3u8"
                ),
            },
            {
                "id": "candidate-bound-video",
                "live_id": "l_stale_context",
                "url": (
                    "https://encrypt-k-vod.xet.tech/vod/"
                    "773e679a5001834815942190711/drm/v.f421220.m3u8"
                    "?sign=fresh"
                ),
            },
        ],
    )

    assert detected is not None
    assert detected["candidate"]["id"] == "candidate-bound-video"
    assert detected["candidate_key"] == "id:candidate-bound-video"
    persisted = (tmp_path / "jobs.jsonl").read_text(encoding="utf-8")
    assert "sign=fresh" not in persisted


def test_recorded_media_url_rehydrates_only_exact_signed_path():
    candidate = {
        "id": "candidate-bound-video",
        "media_type": "m3u8",
        "url": (
            "https://encrypt-k-vod.xet.tech/vod/"
            "773e679a5001834815942190711/drm/v.f421220.m3u8"
        ),
    }
    signed = candidate["url"] + "?sign=fresh&t=expires&us=user"

    assert bind_recorded_media_url(
        candidate,
        signed,
        media_file_id="5001834815942190711",
    )["url"] == signed
    with pytest.raises(InvalidSourcePage):
        bind_recorded_media_url(
            candidate,
            candidate["url"],
            media_file_id="5001834815942190711",
        )


def test_recorded_candidate_rehydrates_by_file_when_ephemeral_id_rotates():
    current = {
        "candidate_key": "id:expired-candidate",
        "expected_source": {
            "source_resource_id": "v_6a7db774e4b0694c5bfa7583",
        },
        "expected_media_file_id": "5001834815942190711",
    }
    refreshed = {
        "id": "fresh-candidate",
        "media_type": "m3u8",
        "url": (
            "https://encrypt-k-vod.xet.tech/vod/"
            "773e679a5001834815942190711/drm/v.f421220.m3u8"
        ),
    }

    assert resolve_candidate(current, [refreshed]) == refreshed


def test_sniffer_arms_xiaoetong_source_job_without_persisting_response_url():
    seen = {}

    def opener(request, timeout):
        seen["path"] = request.full_url
        seen["payload"] = json.loads(request.data)
        return _Response({
            "code": 0,
            "data": {
                "id": "source-1",
                "status": "awaiting_playback",
                "live_id": "l_target",
                "page_url": "https://example.test/?share_user_id=private",
            },
        })

    client = SnifferClient(opener=opener)
    job = client.arm_xiaoetong_source(
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/alive/l_target"
    )

    assert seen["path"].endswith("/api/elive/source-jobs")
    assert seen["payload"]["compress"] is True
    assert job == {
        "id": "source-1",
        "status": "awaiting_playback",
        "live_id": "l_target",
    }


def test_sniffer_reads_safe_xiaoetong_source_job_status():
    seen = {}

    def opener(request, timeout):
        seen["path"] = request.full_url
        return _Response({
            "code": 0,
            "data": {
                "id": "source-1",
                "status": "task_created",
                "live_id": "l_target",
                "candidate_id": "candidate-1",
                "task_id": "task-1",
                "canonical_page": "https://example.test/safe",
                "playlist_url": "https://example.test/live.m3u8?sign=secret",
            },
        })

    client = SnifferClient(opener=opener)
    job = client.xiaoetong_source_job("source-1")

    assert seen["path"].endswith("/api/elive/source-jobs/source-1")
    assert job == {
        "id": "source-1",
        "status": "task_created",
        "live_id": "l_target",
        "candidate_id": "candidate-1",
        "task_id": "task-1",
    }
    assert "sign" not in json.dumps(job)


def test_sniffer_allows_large_candidate_listing_more_time():
    seen = {}

    def opener(request, timeout):
        seen["path"] = request.full_url
        seen["timeout"] = timeout
        return _Response({
            "code": 0,
            "data": {"list": [{"id": "candidate-1"}]},
        })

    client = SnifferClient(timeout=2.0, opener=opener)

    assert client.candidates() == [{"id": "candidate-1"}]
    assert seen["path"].endswith("/api/elive/live/candidates?all=1")
    assert seen["timeout"] == 15.0


def test_sniffer_retries_xiaoetong_source_job_without_media_credentials():
    seen = {}

    def opener(request, timeout):
        seen["path"] = request.full_url
        seen["method"] = request.method
        return _Response({
            "code": 0,
            "data": {
                "id": "source-1",
                "status": "task_created",
                "live_id": "l_target",
                "candidate_id": "candidate-fresh",
                "task_id": "task-fresh",
                "playlist_url": "https://example.test/live.m3u8?sign=secret",
            },
        })

    job = SnifferClient(opener=opener).retry_xiaoetong_source_job("source-1")

    assert seen["path"].endswith("/api/elive/source-jobs/source-1/retry")
    assert seen["method"] == "POST"
    assert job == {
        "id": "source-1",
        "status": "task_created",
        "live_id": "l_target",
        "candidate_id": "candidate-fresh",
        "task_id": "task-fresh",
    }
    assert "sign" not in json.dumps(job)


def test_sniffer_download_payload_keeps_evidence_metadata():
    seen = {}

    def opener(request, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return _Response({"code": 0, "data": {"id": "task-1"}})

    client = SnifferClient(opener=opener)
    task_id = client.start_download(
        {
            "id": "candidate-1",
            "live_id": "live-1",
            "url": "https://example.test/video.m3u8",
            "filename": "new.mp4",
            "media_type": "m3u8",
        }
    )

    assert task_id == "task-1"
    payload = json.loads(seen["request"].data)
    assert payload["extra"]["type"] == "live_capture"
    assert payload["extra"]["compress"] == "true"
    assert payload["extra"]["live_id"] == "live-1"
    assert payload["filename"] == "new.mp4"


def test_sniffer_can_force_retry_through_same_live_capture_path():
    seen = {}

    def opener(request, timeout):
        seen["payload"] = json.loads(request.data)
        return _Response({"code": 0, "data": {"id": "retry-1"}})

    client = SnifferClient(opener=opener)
    client.start_download(
        {"url": "https://example.test/video.m3u8", "filename": "new.mp4"},
        force=True,
    )

    assert seen["payload"]["force"] is True
    assert seen["payload"]["extra"]["type"] == "live_capture"
    assert seen["payload"]["extra"]["compress"] == "true"


def test_reconcile_download_appends_terminal_transition(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    armed = store.arm([])
    downloading = store.transition(
        armed, "download_started", status="downloading", download_task_id="task-7"
    )
    done = store.reconcile_download(
        downloading,
        [
            {
                "id": "task-7",
                "status": "done",
                "name": "sample.mp4",
                "meta": {"opts": {"path": "/tmp/downloads"}},
            }
        ],
    )

    assert done is not None
    assert done["status"] == "downloaded"
    assert done["event"] == "download_completed"
    assert done["media_path"] == "/tmp/downloads/sample.mp4"


def test_capture_ledger_never_persists_signed_url_or_raw_task(tmp_path):
    path = tmp_path / "jobs.jsonl"
    store = CaptureJobStore(path)
    armed = store.arm([])
    detected = store.detect_capture(
        armed,
        [{
            "id": "candidate",
            "live_id": "live-1",
            "filename": "sample.mp4",
            "url": "https://example.test/stream.m3u8?sign=secret",
        }],
    )
    assert detected is not None
    downloading = store.transition(
        detected,
        "download_started",
        status="downloading",
        download_task_id="task-1",
    )
    store.reconcile_download(
        downloading,
        [{
            "id": "task-1",
            "status": "done",
            "name": "sample-compressed.mp4",
            "meta": {
                "opts": {"path": "/tmp/downloads"},
                "req": {
                    "url": "https://example.test/stream.m3u8?sign=secret",
                    "headers": {"Cookie": "secret"},
                    "labels": {
                        "live_id": "live-1",
                        "compress": "true",
                        "compress_inline": "true",
                        "type": "live_capture",
                    },
                },
            },
        }],
    )

    text = path.read_text(encoding="utf-8")
    assert "sign=secret" not in text
    assert "Cookie" not in text
    assert '"url"' not in text
    assert "compress_inline" in text


def test_sanitize_legacy_ledger_removes_signed_query_in_place(tmp_path):
    path = tmp_path / "jobs.jsonl"
    path.write_text(
        json.dumps({
            "job_id": "kol-old",
            "event": "download_completed",
            "status": "downloaded",
            "candidate": {
                "id": "candidate",
                "live_id": "live-1",
                "url": "https://example.test/live.m3u8?sign=secret",
            },
            "download_task": {
                "id": "task-1",
                "status": "done",
                "meta": {
                    "opts": {"path": "/tmp", "name": "sample-compressed.mp4"},
                    "req": {
                        "url": "https://example.test/live.m3u8?sign=secret",
                        "labels": {
                            "type": "live_capture",
                            "compress": "true",
                        },
                    },
                },
            },
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = CaptureJobStore(path).sanitize_ledger()

    assert result == {"events": 1, "changed": 1}
    text = path.read_text(encoding="utf-8")
    assert "sign=secret" not in text
    assert "live_capture" in text


def test_resolve_candidate_rehydrates_url_only_in_memory(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    armed = store.arm([])
    raw = {
        "id": "candidate",
        "live_id": "live-1",
        "url": "https://example.test/live.m3u8?sign=secret",
    }
    detected = store.detect_capture(armed, [raw])

    assert detected is not None
    assert resolve_candidate(detected, [raw]) == raw


def test_resolve_candidate_prefers_latest_fresh_url_for_same_live_id(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    armed = store.arm([])
    old = {
        "id": "candidate-old",
        "live_id": "live-1",
        "captured": "2026-08-04 11:07:09",
        "url": "https://example.test/playlist.m3u8",
    }
    fresh = {
        "id": "candidate-fresh",
        "live_id": "live-1",
        "captured": "2026-08-04 11:25:17",
        "url": "https://example.test/playlist.m3u8?sign=fresh",
    }
    detected = store.detect_capture(armed, [old, fresh])

    assert detected is not None
    assert resolve_candidate(detected, [old, fresh]) == fresh


def test_checkpoint_records_async_boundary_and_rejects_unknown_status(tmp_path):
    store = CaptureJobStore(tmp_path / "jobs.jsonl")
    armed = store.arm([])
    uploading = store.checkpoint(
        armed,
        status="uploading",
        artifact_path="baidu://ai-notes/session-1",
    )

    assert uploading["event"] == "checkpoint_uploading"
    assert uploading["artifact_path"] == "baidu://ai-notes/session-1"

    try:
        store.checkpoint(uploading, status="mystery")
    except InvalidCheckpoint:
        pass
    else:
        raise AssertionError("unknown checkpoint status must fail")
