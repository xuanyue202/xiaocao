from __future__ import annotations

import io
import json

from xiaocao.kol.capture import (
    CaptureJobStore,
    SnifferClient,
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
