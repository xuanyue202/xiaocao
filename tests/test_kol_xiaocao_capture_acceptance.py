from __future__ import annotations

import hashlib
import json
from pathlib import Path

from xiaocao.kol.xiaocao_capture_acceptance import inspect_acceptance


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path, *, complete: bool) -> tuple[Path, str]:
    root = tmp_path / "wechat_subscription"
    identity = "kol-wechat-test"
    live_id = "l_test"
    media = tmp_path / "capture-compressed.mp4"
    media.write_bytes(b"validated-video")
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "items": {
                    identity: {
                        "identity": identity,
                        "status": "completed" if complete else "awaiting_playback",
                        "source_identity": f"xiaoetong:appdemo:{live_id}",
                        "capture_job_id": "kol-capture-test",
                        "playback_surface": "wechat_mini_program" if complete else "",
                        "media_request_observed": complete,
                        "observed_page_state": (
                            "mini_program_media_observed"
                            if complete
                            else "account_login_required"
                        ),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    item_dir = root / "items" / identity
    _write_jsonl(
        item_dir / "capture_jobs.jsonl",
        [
            {
                "event": "armed",
                "job_id": "kol-capture-test",
                "source_job_id": "elive-job-test",
            }
        ],
    )
    events: list[dict[str, object]] = []
    if complete:
        events = [
            {
                "event": "media_validated",
                "capture_job_id": "kol-capture-test",
                "live_id": live_id,
                "media_path": str(media),
                "media_sha256": digest,
                "updated_at": "2026-09-05T15:00:00+08:00",
            },
            {
                "event": "cloud_handoff_published",
                "capture_job_id": "kol-capture-test",
                "live_id": live_id,
            },
        ]
    _write_jsonl(item_dir / "events.jsonl", events)
    return root, identity


def _fetch(url: str) -> dict[str, object]:
    if "/api/elive/source-jobs/" in url:
        return {
            "code": 0,
            "data": {
                "id": "elive-job-test",
                "status": "task_created",
                "live_id": "l_test",
                "task_id": "task-test",
            },
        }
    return {
        "code": 0,
        "data": {"list": [{"id": "task-test", "status": "done"}]},
    }


def test_acceptance_requires_complete_native_capture_chain(tmp_path: Path) -> None:
    root, identity = _fixture(tmp_path, complete=True)

    result = inspect_acceptance(
        root,
        [identity],
        required_count=1,
        not_before="2026-09-05T14:00:00+08:00",
        fetch_json=_fetch,
        probe_media=lambda _: True,
    )

    assert result["status"] == "passed"
    assert all(result["items"][0]["checks"].values())


def test_acceptance_rejects_existing_bytes_without_ui_and_handoff(
    tmp_path: Path,
) -> None:
    root, identity = _fixture(tmp_path, complete=False)

    result = inspect_acceptance(
        root,
        [identity],
        required_count=1,
        fetch_json=_fetch,
        probe_media=lambda _: True,
    )

    assert result["status"] == "failed"
    checks = result["items"][0]["checks"]
    assert checks["wechat_mini_program_surface"] is False
    assert checks["media_request_observed"] is False
    assert checks["cloud_handoff_published"] is False


def test_native_entry_acceptance_requires_the_same_candidate_in_task_labels(tmp_path):
    root, identity = _fixture(tmp_path, complete=True)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["items"][identity].update(
        entry_kind="wechat_mini_program", candidate_id="candidate-test",
    )
    manifest_path.write_text(json.dumps(manifest))
    _write_jsonl(root / "items" / identity / "capture_jobs.jsonl", [{
        "job_id": "kol-capture-test",
        "event": "mini_program_source_bound",
        "expected_source": {"source_identity": "xiaoetong:appdemo:l_test"},
    }, {
        "job_id": "kol-capture-test",
        "event": "download_complete",
        "expected_source": {"source_identity": "xiaoetong:appdemo:l_test"},
        "candidate": {"id": "candidate-test", "live_id": "l_test"},
        "download_task_id": "task-test",
    }])
    labels = {
        "capture_id": "candidate-test", "live_id": "l_test",
        "type": "live_capture", "compress": "true",
    }

    def fetch(url):
        assert "/api/task/list" in url
        return {"code": 0, "data": {"list": [{
            "id": "task-test", "status": "done", "meta": {"labels": labels},
        }]}}

    kwargs = dict(required_count=1, fetch_json=fetch, probe_media=lambda _: True)
    assert inspect_acceptance(root, [identity], **kwargs)["status"] == "passed"
    labels["capture_id"] = "another-candidate"
    assert inspect_acceptance(root, [identity], **kwargs)["status"] == "failed"


def test_completed_capture_acceptance_uses_durable_task_after_sniffer_cleanup(tmp_path):
    root, identity = _fixture(tmp_path, complete=True)
    ledger = root / "items" / identity / "capture_jobs.jsonl"
    capture = {"job_id": "kol-capture-test", "status": "downloaded",
               "source_job_id": "elive-job-test", "source_job_status": "task_created",
               "source_task_id": "task-test", "download_task_id": "task-test",
               "expected_source": {"source_identity": "xiaoetong:appdemo:l_test"},
               "candidate": {"id": "candidate-test", "live_id": "l_test"},
               "candidate_key": "live:l_test", "baseline_candidate_keys": [],
               "download_task": {"id": "task-test", "status": "done", "meta": {"labels": {
                   "capture_id": "candidate-test", "live_id": "l_test", "type": "live_capture",
                   "compress": "true", "compress_inline": "true"}}}}
    _write_jsonl(ledger, [capture])
    def offline(url):
        raise AssertionError("completed capture must not restart or query the stopped sniffer")
    result = inspect_acceptance(root, [identity], required_count=1, fetch_json=offline,
                                probe_media=lambda _: True)
    assert result["status"] == "passed"
    assert result["items"][0]["task_evidence_origin"] == "capture_ledger"
    capture["download_task"]["meta"]["labels"]["capture_id"] = "wrong-candidate"
    _write_jsonl(ledger, [capture])
    rejected = inspect_acceptance(root, [identity], required_count=1, fetch_json=offline,
                                  probe_media=lambda _: True)
    assert rejected["status"] == "failed"
    assert rejected["items"][0]["checks"]["download_task_done"] is False
