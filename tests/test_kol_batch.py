from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import xiaocao.kol.batch as batch_module
from xiaocao.kol.batch import BatchCoordinator, BatchError


NOW = datetime.fromisoformat("2026-07-25T21:00:00+08:00")


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _xiaocao_receipt(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "ticket03.json",
        {
            "ticket": "03-xiaocao-live-to-decisions",
            "status": "completed",
            "capture": {
                "capture_job_id": "kol-real-live",
                "media_sha256": "a" * 64,
            },
            "cloud_handoff": {
                "handoff_sha256": "b" * 64,
                "coordinator_large_payload_local_bytes": 0,
            },
            "enrichment": {
                "transcript_sha256": "c" * 64,
                "decision_result_sha256": "7" * 64,
                "market_first": True,
                "source_system_and_market_validation_separated": True,
                "seven_row_trade_information_matrix_complete": True,
            },
            "household_output": {
                "status": "delivered",
                "notification_idempotency_key": "d" * 64,
                "advisory_only": True,
                "utf8_chunk_limit_bytes": 2048,
                "utf8_chunk_sizes_bytes": [1024, 512],
                "lossless_reassembly_verified": True,
            },
            "book_kol_us_output": {
                "paper_only": True,
                "status": "no_trade",
                "reason": "No eligible US-listed instrument.",
                "idempotency_key": "e" * 64,
            },
            "side_effect_counts": {
                "rerun_external_side_effects": 0,
            },
        },
    )


def _image_receipt(
    tmp_path: Path,
    *,
    identity: str = "lv-real-image",
    version: str = "image-version",
    stem: str = "image",
) -> Path:
    coverage = {
        row: {"status": "absent", "reason": "fixture"}
        for row in (
            "todays_market_diagnosis",
            "next_session_playbook",
            "next_several_session_base_case",
            "style_market_cap_regime",
            "market_board_sector_hierarchy",
            "position_risk_budget",
            "named_asset_inventory",
        )
    }
    bundle_path = _write_json(
        tmp_path / f"{stem}-bundle.json",
        {
            "items": [{
                "claims": [],
                "decision_status": "no_actionable_signal",
                "knowledge_status": "no_reusable_knowledge",
                "market_outlook": {
                    "scope": "market",
                    "current_validation": {"status": "invalidate"},
                },
                "synthesis": {"summary": "No signal."},
                "trade_information_coverage": coverage,
            }],
        },
    )
    result_path = _write_json(
        tmp_path / f"{stem}-result.json",
        {
            "status": "completed",
            "items": [{
                "decision_status": "no_actionable_signal",
                "evidence_sha256": "8" * 64,
                "knowledge_status": "no_reusable_knowledge",
                "book_kol_us": {
                    "book": "KOL-US",
                    "paper_only": True,
                    "status": "no_trade",
                    "reason": "Unattributed fragment.",
                    "idempotency_key": "1" * 64,
                },
            }],
        },
    )
    import hashlib

    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    result_sha256 = hashlib.sha256(result_path.read_bytes()).hexdigest()
    return _write_json(
        tmp_path / f"{stem}-state.json",
        {
            "event": "subscription_decisions_completed",
            "status": "decided",
            "identity": identity,
            "version_key": version,
            "decision_bundle_path": str(bundle_path),
            "decision_bundle_sha256": bundle_sha256,
            "decision_result_path": str(result_path),
            "decision_result_sha256": result_sha256,
            "household_notification": {
                "status": "delivered",
                "idempotency_key": "f" * 64,
            },
            "book_kol_us": {
                "paper_only": True,
                "status": "no_trade",
                "reason": "Unattributed fragment.",
                "idempotency_key": "1" * 64,
            },
        },
    )


def _video_receipt(
    tmp_path: Path,
    *,
    source_identity: str = "lv-real-video",
    version_identity: str = "video-version",
    source_parts: list[dict] | None = None,
    stem: str = "ticket05",
) -> Path:
    logical_content = None
    if source_parts:
        logical_content = {
            "kind": "multi_part_episode",
            "part_count": len(source_parts),
            "analyzed_once": True,
            "household_terminal_once": True,
            "book_terminal_once": True,
            "components": source_parts,
        }
    return _write_json(
        tmp_path / f"{stem}.json",
        {
            "ticket": "05-subscription-video-to-decisions",
            "status": "completed",
            "samples": [{
                "stable_identity_sha256": source_identity,
                "version_key": version_identity,
                **(
                    {"logical_content": logical_content}
                    if logical_content is not None
                    else {}
                ),
                "cloud_transfer": {
                    "status": "completed",
                    "claim_before_trigger": True,
                    "receipt_after_completion": True,
                    "large_payload_local_bytes": 0,
                },
                "enrichment": {
                    "large_payload_local_bytes": 0,
                    "transcript_sha256": "2" * 64,
                },
                "decision_contract_audit": {
                    "decision_status": "actionable_signal",
                    "knowledge_status": "no_reusable_knowledge",
                    "market_first": True,
                    "all_named_assets_resolved_or_explicitly_unresolved": True,
                    "xiaocao_cross_view": {},
                    "coverage_rows": [
                        "todays_market_diagnosis",
                        "next_session_playbook",
                        "next_several_session_base_case",
                        "style_market_cap_regime",
                        "market_board_sector_hierarchy",
                        "position_risk_budget",
                        "named_asset_inventory",
                    ],
                    "household": {
                        "status": "delivered",
                        "receipt_persisted": True,
                    },
                    "book_kol_us": {
                        "paper_only": True,
                        "status": "no_trade",
                        "reason": "No current US trigger.",
                    },
                    "decision_result_sha256": "3" * 64,
                },
            }],
        },
    )


def test_subscription_episode_child_preserves_all_source_parts(tmp_path):
    parts = [
        {
            "source_identity": f"part-{index}",
            "version_identity": f"version-{index}",
            "part_index": index,
            "part_label": str(index),
            "source_path": f"/课程/主题/复盘-{index}.mp4",
            "source_size": 100 * index,
        }
        for index in range(1, 5)
    ]
    receipt = _video_receipt(
        tmp_path,
        source_identity="episode",
        version_identity="episode-version",
        source_parts=parts,
        stem="episode-ticket05",
    )
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "episode-batch",
        [
            {
                "adapter": "subscription_video",
                "source_identity": "episode",
                "version_identity": "episode-version",
                "source_parts": parts,
                "author": "路西法",
                "media_type": "video",
                "priority": 80,
                "receipt_path": str(receipt),
            }
        ],
    )

    service.run_once("episode-batch")
    service.run_once("episode-batch")

    state = service.status("episode-batch")
    child = state["children"][0]
    assert child["status"] == "terminal"
    assert child["source_parts"] == parts
    assert child["terminal_receipt"]["source_part_count"] == 4
    assert child["terminal_receipt"]["coordinator_source_video_bytes"] == 0


def test_existing_single_video_batch_replays_with_empty_source_parts(tmp_path):
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    child_input = {
        "adapter": "subscription_video",
        "source_identity": "legacy-video",
        "version_identity": "legacy-version",
        "author": "吕晓彤",
        "media_type": "video",
        "priority": 80,
        "receipt_path": str(_video_receipt(tmp_path)),
    }
    legacy_child = service._normalize_child(child_input)
    legacy_child.pop("source_parts")
    service._append(
        "batch_created",
        batch_id="legacy-batch",
        child_count=1,
        children=[legacy_child],
        insight_required=False,
        coordinator_source_video_bytes=0,
        watched_artifacts_before=[],
    )

    replay = service.create_batch("legacy-batch", [child_input])

    assert replay["children"][0]["source_parts"] == []


def test_ready_children_progress_while_video_waits_and_restart_rebuilds_state(
    tmp_path: Path,
):
    clock = Clock(NOW)
    service = BatchCoordinator(tmp_path / "batch", now=clock)
    service.create_batch(
        "real-window",
        [
            {
                "adapter": "subscription_video",
                "source_identity": "lv-real-video",
                "version_identity": "video-version",
                "author": "吕晓彤",
                "media_type": "video",
                "priority": 90,
                "wait_for_async_receipt": True,
                "receipt_path": str(_video_receipt(tmp_path)),
            },
            {
                "adapter": "xiaocao_live",
                "source_identity": "kol-real-live",
                "version_identity": "a" * 64,
                "author": "小草",
                "media_type": "video",
                "priority": 80,
                "receipt_path": str(_xiaocao_receipt(tmp_path)),
            },
            {
                "adapter": "lv_text_image",
                "source_identity": "lv-real-image",
                "version_identity": "image-version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 40,
                "receipt_path": str(_image_receipt(tmp_path)),
            },
        ],
    )

    service.run_once("real-window")
    service.run_once("real-window")

    restarted = BatchCoordinator(tmp_path / "batch", now=clock)
    status = restarted.status("real-window")
    children = {row["adapter"]: row for row in status["children"]}

    assert children["subscription_video"]["status"] == "waiting_async"
    assert children["subscription_video"]["next_poll_not_before"] == (
        NOW + timedelta(minutes=5)
    ).isoformat()
    assert children["xiaocao_live"]["status"] == "terminal"
    assert children["lv_text_image"]["status"] == "terminal"
    assert all(row["large_payload_local_bytes"] == 0 for row in status["children"])
    assert status["append_only_event_count"] == 5


def test_async_poll_starts_after_five_minutes_and_backs_off_only_pending_child(
    tmp_path: Path,
):
    clock = Clock(NOW)
    service = BatchCoordinator(tmp_path / "batch", now=clock)
    late_receipt = tmp_path / "late-ticket05.json"
    service.create_batch(
        "backoff-window",
        [
            {
                "adapter": "subscription_video",
                "source_identity": "lv-real-video",
                "version_identity": "video-version",
                "author": "吕晓彤",
                "media_type": "video",
                "priority": 90,
                "wait_for_async_receipt": True,
                "receipt_path": str(late_receipt),
            },
            {
                "adapter": "lv_text_image",
                "source_identity": "lv-real-image",
                "version_identity": "image-version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 40,
                "receipt_path": str(_image_receipt(tmp_path)),
            },
        ],
    )
    service.run_once("backoff-window")
    service.run_once("backoff-window")
    completed_event_count = service.status("backoff-window")[
        "append_only_event_count"
    ]

    clock.value = NOW + timedelta(minutes=4, seconds=59)
    service.run_once("backoff-window")
    assert (
        service.status("backoff-window")["append_only_event_count"]
        == completed_event_count
    )

    clock.value = NOW + timedelta(minutes=5)
    service.run_once("backoff-window")
    service.run_once("backoff-window")
    waiting = next(
        row
        for row in service.status("backoff-window")["children"]
        if row["adapter"] == "subscription_video"
    )
    assert waiting["status"] == "waiting_async"
    assert waiting["retry_count"] == 1
    assert waiting["failure_reason"] == "async_receipt_not_ready"
    assert waiting["next_poll_not_before"] == (
        NOW + timedelta(minutes=15)
    ).isoformat()

    clock.value = NOW + timedelta(minutes=14, seconds=59)
    service.run_once("backoff-window")
    assert service.status("backoff-window")["children"][0]["status"] != "polling"

    late_receipt.write_bytes(_video_receipt(tmp_path).read_bytes())
    clock.value = NOW + timedelta(minutes=15)
    service.run_once("backoff-window")
    service.run_once("backoff-window")

    final = service.status("backoff-window")
    assert final["status"] == "completed"
    image_terminal_events = [
        event
        for event in service.events()
        if (
            event.get("event") == "child_terminal"
            and event.get("child_id")
            == next(
                row["child_id"]
                for row in final["children"]
                if row["adapter"] == "lv_text_image"
            )
        )
    ]
    assert len(image_terminal_events) == 1
    poll_times = [
        datetime.fromisoformat(event["occurred_at"])
        for event in service.events()
        if event.get("event") == "child_async_poll_claimed"
    ]
    assert poll_times == [
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=15),
    ]


def test_explicit_exception_classes_pause_or_terminate_without_side_effects(
    tmp_path: Path,
):
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    expected = {
        "low_density": "terminal",
        "duplicate": "terminal",
        "unauthorized": "paused",
        "missing_evidence": "paused",
        "missing_market_data": "paused",
    }
    children = []
    for index, reason in enumerate(expected):
        children.append(
            {
                "adapter": "lv_text_image",
                "source_identity": f"source-{index}",
                "version_identity": f"version-{index}",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 10,
                "disposition_reason": reason,
                "receipt_path": str(tmp_path / f"unused-{index}.json"),
            }
        )
    service.create_batch("exception-window", children)
    before = service.status("exception-window")["append_only_event_count"]

    service.run_once("exception-window")

    status = service.status("exception-window")
    assert status["append_only_event_count"] == before
    assert {
        row["failure_reason"]: row["status"] for row in status["children"]
    } == expected
    assert all(
        (
            (
                row["terminal_receipt"]["disposition"]
                == row["failure_reason"]
                and row["terminal_receipt"]["household"]["status"]
                == "suppressed"
                and row["terminal_receipt"]["book_kol_us"]["status"]
                == "no_trade"
            )
            if row["status"] == "terminal"
            else row["terminal_receipt"] is None
        )
        for row in status["children"]
    )


def test_aging_makes_old_low_priority_child_visible_ahead_of_new_urgent_work(
    tmp_path: Path,
):
    clock = Clock(NOW)
    service = BatchCoordinator(tmp_path / "batch", now=clock)
    service.create_batch(
        "fair-window",
        [{
            "adapter": "lv_text_image",
            "source_identity": "old-low",
            "version_identity": "old-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 0,
            "receipt_path": str(
                _image_receipt(
                    tmp_path,
                    identity="old-low",
                    version="old-version",
                    stem="old",
                )
            ),
        }],
    )
    clock.value = NOW + timedelta(hours=10)
    service.submit_child(
        "fair-window",
        {
            "adapter": "lv_text_image",
            "source_identity": "new-urgent",
            "version_identity": "new-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 100,
            "receipt_path": str(
                _image_receipt(
                    tmp_path,
                    identity="new-urgent",
                    version="new-version",
                    stem="new",
                )
            ),
        },
    )

    before = service.status("fair-window")
    assert [row["source_identity"] for row in before["children"]] == [
        "old-low",
        "new-urgent",
    ]
    assert before["children"][0]["effective_priority"] == 120
    assert before["children"][1]["effective_priority"] == 100

    service.run_once("fair-window", max_children=1)

    after = {
        row["source_identity"]: row
        for row in service.status("fair-window")["children"]
    }
    assert after["old-low"]["status"] == "reconciling"
    assert after["new-urgent"]["status"] == "registered"


def test_audit_proves_real_restart_receipt_reconciliation_and_zero_video_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    clock = Clock(NOW)
    watched = tmp_path / "side-effects.jsonl"
    watched.write_text('{"existing":true}\n', encoding="utf-8")
    service = BatchCoordinator(tmp_path / "batch", now=clock)
    service.create_batch(
        "acceptance-window",
        [
            {
                "adapter": "subscription_video",
                "source_identity": "lv-real-video",
                "version_identity": "video-version",
                "author": "吕晓彤",
                "media_type": "video",
                "priority": 90,
                "wait_for_async_receipt": True,
                "receipt_path": str(_video_receipt(tmp_path)),
            },
            {
                "adapter": "xiaocao_live",
                "source_identity": "kol-real-live",
                "version_identity": "a" * 64,
                "author": "小草",
                "media_type": "video",
                "priority": 80,
                "receipt_path": str(_xiaocao_receipt(tmp_path)),
            },
            {
                "adapter": "lv_text_image",
                "source_identity": "lv-real-image",
                "version_identity": "image-version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 40,
                "receipt_path": str(_image_receipt(tmp_path)),
            },
        ],
        watched_artifacts=[{
            "path": str(watched),
            "roles": sorted({
                "cloud_transfer_claim",
                "cloud_transfer_receipt",
                "transcript_generation",
                "ai_note_submission",
                "household_notification",
                "book_kol_us_action",
            }),
        }],
    )
    monkeypatch.setattr(batch_module.os, "getpid", lambda: 101)
    service.record_runner_started("acceptance-window")
    service.run_once("acceptance-window")
    service.run_once("acceptance-window")
    service.record_interruption(
        "acceptance-window",
        reason="signal_15",
    )

    clock.value = NOW + timedelta(minutes=5)
    restarted = BatchCoordinator(tmp_path / "batch", now=clock)
    monkeypatch.setattr(batch_module.os, "getpid", lambda: 202)
    restarted.record_runner_started("acceptance-window")
    restarted.run_once("acceptance-window")
    restarted.run_once("acceptance-window")
    restarted.record_runner_completed("acceptance-window")
    before_replay = restarted.status("acceptance-window")[
        "append_only_event_count"
    ]
    restarted.run_once("acceptance-window")
    assert (
        restarted.status("acceptance-window")["append_only_event_count"]
        == before_replay
    )

    audit = restarted.audit("acceptance-window")

    assert audit["status"] == "accepted"
    assert audit["requirements"] == {
        "two_real_videos_and_one_text_or_image": True,
        "broadband_handoff_and_subscription_combined": True,
        "waiting_child_did_not_block_ready_children": True,
        "first_poll_not_before_five_minutes": True,
        "explicit_backoff": True,
        "real_process_interruption_and_restart": True,
        "unfinished_child_at_interruption": True,
        "independent_household_and_book_terminals": True,
        "completed_children_not_replayed": True,
        "watched_side_effect_artifacts_unchanged": True,
        "required_side_effect_watchers_present": True,
        "coordinator_source_video_bytes_zero": True,
        "batch_insight_delivered": True,
    }
    assert audit["runner_start_count"] == 2
    assert audit["interruption_count"] == 1
    assert audit["terminal_receipt_count"] == 3
    assert audit["new_external_side_effect_count"] == 0
    assert audit["coordinator_source_video_bytes"] == 0
    image = next(
        row for row in audit["children"] if row["adapter"] == "lv_text_image"
    )
    assert image["terminal_receipt"]["evidence_sha256"] == "8" * 64
    assert len(image["terminal_receipt"]["decision_result_sha256"]) == 64


def test_cli_run_and_status_resume_the_same_append_only_batch(tmp_path: Path):
    output = tmp_path / "batch"
    spec = _write_json(
        tmp_path / "spec.json",
        {
            "batch_id": "cli-window",
            "children": [{
                "adapter": "lv_text_image",
                "source_identity": "lv-real-image",
                "version_identity": "image-version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 40,
                "receipt_path": str(_image_receipt(tmp_path)),
            }],
            "watched_artifacts": [],
        },
    )
    script = Path(__file__).parents[1] / "scripts" / "kol_batch.py"
    environment = {**os.environ, "PYTHONPATH": "src"}
    command = [
        sys.executable,
        str(script),
        "run",
        "--spec",
        str(spec),
        "--output-dir",
        str(output),
        "--once",
    ]

    first = subprocess.run(
        command,
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        command,
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    status = subprocess.run(
        [
            sys.executable,
            str(script),
            "status",
            "--batch-id",
            "cli-window",
            "--output-dir",
            str(output),
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert status.returncode == 0
    assert json.loads(status.stdout)["status"] == "completed"
    assert json.loads(status.stdout)["children"][0]["status"] == "terminal"


def test_source_video_paths_are_rejected_before_coordinator_reads_bytes(
    tmp_path: Path,
):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"must-not-be-read")
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    child = {
        "adapter": "subscription_video",
        "source_identity": "video-source",
        "version_identity": "video-version",
        "author": "吕晓彤",
        "media_type": "video",
        "priority": 90,
        "receipt_path": str(video),
    }

    with pytest.raises(BatchError, match="JSON receipt"):
        service.create_batch("video-receipt", [child])

    child["receipt_path"] = str(_video_receipt(tmp_path))
    with pytest.raises(BatchError, match="watched artifact"):
        service.create_batch(
            "video-watch",
            [child],
            watched_artifacts=[{
                "path": str(video),
                "roles": ["transcript_generation"],
            }],
        )


def test_ticket04_decision_result_must_be_small_json_before_hashing(
    tmp_path: Path,
):
    receipt_path = _image_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    video = tmp_path / "forged-result.mp4"
    video.write_bytes(b"must-not-be-read")
    receipt["decision_result_path"] = str(video)
    receipt["decision_result_sha256"] = "0" * 64
    _write_json(receipt_path, receipt)
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "forged-result",
        [{
            "adapter": "lv_text_image",
            "source_identity": "lv-real-image",
            "version_identity": "image-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 40,
            "receipt_path": str(receipt_path),
        }],
    )

    service.run_once("forged-result")
    service.run_once("forged-result")

    paused = service.status("forged-result")["children"][0]
    pause_event = next(
        row
        for row in service.events()
        if row.get("event") == "child_paused"
    )
    assert paused["status"] == "paused"
    assert paused["failure_reason"] == "missing_evidence"
    assert "decision result must be a small JSON file" in pause_event[
        "failure_detail"
    ]


@pytest.mark.parametrize(
    ("adapter", "media_type"),
    [
        ("xiaocao_live", "image"),
        ("lv_text_image", "video"),
        ("subscription_video", "text"),
    ],
)
def test_adapter_cannot_forge_media_type_for_acceptance_counts(
    tmp_path: Path,
    adapter: str,
    media_type: str,
):
    service = BatchCoordinator(tmp_path / adapter, now=Clock(NOW))
    with pytest.raises(BatchError, match="media_type"):
        service.create_batch(
            "forged-media",
            [{
                "adapter": adapter,
                "source_identity": "source",
                "version_identity": "version",
                "author": "author",
                "media_type": media_type,
                "priority": 50,
                "receipt_path": str(tmp_path / "receipt.json"),
            }],
        )


def test_filled_book_terminal_requires_durable_kol_us_receipt(
    tmp_path: Path,
):
    receipt_path = _image_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["book_kol_us"] = {
        "paper_only": True,
        "status": "filled",
    }
    result_path = Path(receipt["decision_result_path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["items"][0]["book_kol_us"] = {
        "paper_only": True,
        "status": "filled",
    }
    _write_json(result_path, result)
    import hashlib

    receipt["decision_result_sha256"] = hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest()
    _write_json(receipt_path, receipt)
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "unsafe-fill",
        [{
            "adapter": "lv_text_image",
            "source_identity": "lv-real-image",
            "version_identity": "image-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 40,
            "receipt_path": str(receipt_path),
        }],
    )

    service.run_once("unsafe-fill")
    service.run_once("unsafe-fill")

    state = service.status("unsafe-fill")
    assert state["children"][0]["status"] == "paused"
    pause = next(
        row
        for row in service.events()
        if row.get("event") == "child_paused"
    )
    assert "durable KOL-US fill receipt" in pause["failure_detail"]


def test_ticket04_existing_runner_fill_schema_reconciles_to_terminal(
    tmp_path: Path,
):
    receipt_path = _image_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    state_fill = {
        "book": "KOL-US",
        "paper_only": True,
        "status": "filled",
        "ticker": "QQQ",
        "side": "buy",
        "idempotency_key": "4" * 64,
    }
    receipt["book_kol_us"] = state_fill
    result_path = Path(receipt["decision_result_path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["items"][0]["book_kol_us"] = {
        **state_fill,
        "quantity": 2.5,
        "price": 500.0,
    }
    _write_json(result_path, result)
    import hashlib

    receipt["decision_result_sha256"] = hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest()
    _write_json(receipt_path, receipt)
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "valid-fill",
        [{
            "adapter": "lv_text_image",
            "source_identity": "lv-real-image",
            "version_identity": "image-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 40,
            "receipt_path": str(receipt_path),
        }],
    )

    service.run_once("valid-fill")
    service.run_once("valid-fill")

    terminal = service.status("valid-fill")["children"][0]
    assert terminal["status"] == "terminal"
    assert terminal["terminal_receipt"]["book_kol_us"] == {
        "book": "KOL-US",
        "idempotency_key": "4" * 64,
        "paper_only": True,
        "price": 500.0,
        "quantity": 2.5,
        "reason": "",
        "side": "buy",
        "status": "filled",
        "ticker": "QQQ",
    }


def test_ticket03_metadata_handoff_hash_is_required_and_preserved(
    tmp_path: Path,
):
    receipt_path = _xiaocao_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["cloud_handoff"]["handoff_sha256"] = ""
    _write_json(receipt_path, receipt)
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "missing-handoff",
        [{
            "adapter": "xiaocao_live",
            "source_identity": "kol-real-live",
            "version_identity": "a" * 64,
            "author": "小草",
            "media_type": "video",
            "priority": 80,
            "receipt_path": str(receipt_path),
        }],
    )

    service.run_once("missing-handoff")
    service.run_once("missing-handoff")

    assert service.status("missing-handoff")["children"][0]["status"] == "paused"


def test_ledger_append_retries_short_writes_without_losing_event_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    real_write = os.write

    def short_write(descriptor: int, payload: bytes | memoryview) -> int:
        return real_write(descriptor, payload[:7])

    monkeypatch.setattr(batch_module.os, "write", short_write)
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "short-write",
        [{
            "adapter": "lv_text_image",
            "source_identity": "classified",
            "version_identity": "version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 1,
            "disposition_reason": "low_density",
            "receipt_path": str(tmp_path / "unused.json"),
        }],
    )

    events = service.events()
    assert [row["event"] for row in events] == ["batch_created"]
    assert all(len(row["event_id"]) == 64 for row in events)


def test_sigterm_is_deferred_until_append_frame_is_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    real_write = os.write
    delivered: list[int] = []
    sent = False
    previous = signal.signal(
        signal.SIGTERM,
        lambda signum, _frame: delivered.append(signum),
    )

    def signal_during_write(
        descriptor: int,
        payload: bytes | memoryview,
    ) -> int:
        nonlocal sent
        if not sent:
            sent = True
            os.kill(os.getpid(), signal.SIGTERM)
        return real_write(descriptor, payload)

    monkeypatch.setattr(batch_module.os, "write", signal_during_write)
    try:
        service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
        service.create_batch(
            "signal-safe",
            [{
                "adapter": "lv_text_image",
                "source_identity": "classified",
                "version_identity": "version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 1,
                "disposition_reason": "low_density",
                "receipt_path": str(tmp_path / "unused.json"),
            }],
        )
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert delivered == [signal.SIGTERM]
    assert len(service.events()) == 1


def test_initial_child_registration_is_one_crash_atomic_ledger_frame(
    tmp_path: Path,
):
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "atomic-create",
        [
            {
                "adapter": "xiaocao_live",
                "source_identity": "kol-real-live",
                "version_identity": "a" * 64,
                "author": "小草",
                "media_type": "video",
                "priority": 80,
                "receipt_path": str(_xiaocao_receipt(tmp_path)),
            },
            {
                "adapter": "lv_text_image",
                "source_identity": "lv-real-image",
                "version_identity": "image-version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 40,
                "receipt_path": str(_image_receipt(tmp_path)),
            },
        ],
    )

    events = service.events()
    assert len(events) == 1
    assert events[0]["event"] == "batch_created"
    assert len(events[0]["children"]) == 2
    assert len(service.status("atomic-create")["children"]) == 2


def test_watched_artifact_is_small_before_coordinator_reads_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    watched = tmp_path / "renamed-video.jsonl"
    watched.write_bytes(b"12345")
    monkeypatch.setattr(batch_module, "MAX_JSON_RECEIPT_BYTES", 4)
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))

    with pytest.raises(BatchError, match="small-payload boundary"):
        service.create_batch(
            "large-watch",
            [{
                "adapter": "lv_text_image",
                "source_identity": "classified",
                "version_identity": "version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 1,
                "disposition_reason": "low_density",
                "receipt_path": str(tmp_path / "unused.json"),
            }],
            watched_artifacts=[{
                "path": str(watched),
                "roles": ["transcript_generation"],
            }],
        )


def test_audit_does_not_claim_side_effect_integrity_without_required_watchers(
    tmp_path: Path,
):
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "no-watchers",
        [{
            "adapter": "xiaocao_live",
            "source_identity": "kol-real-live",
            "version_identity": "a" * 64,
            "author": "小草",
            "media_type": "video",
            "priority": 80,
            "receipt_path": str(_xiaocao_receipt(tmp_path)),
        }],
    )
    service.run_once("no-watchers")
    service.run_once("no-watchers")

    audit = service.audit("no-watchers")
    assert audit["requirements"][
        "required_side_effect_watchers_present"
    ] is False
    assert audit["status"] == "incomplete"


def test_restart_audit_requires_a_distinct_process_identity(tmp_path: Path):
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "same-process",
        [{
            "adapter": "xiaocao_live",
            "source_identity": "kol-real-live",
            "version_identity": "a" * 64,
            "author": "小草",
            "media_type": "video",
            "priority": 80,
            "receipt_path": str(_xiaocao_receipt(tmp_path)),
        }],
    )
    service.record_runner_started("same-process")
    service.record_interruption(
        "same-process",
        reason="synthetic",
    )
    service.record_runner_started("same-process")
    service.run_once("same-process")
    service.run_once("same-process")

    audit = service.audit("same-process")
    assert audit["requirements"][
        "real_process_interruption_and_restart"
    ] is False


def test_dynamic_child_does_not_break_resume_with_original_batch_spec(
    tmp_path: Path,
):
    clock = Clock(NOW)
    service = BatchCoordinator(tmp_path / "batch", now=clock)
    initial = {
        "adapter": "lv_text_image",
        "source_identity": "initial",
        "version_identity": "initial-version",
        "author": "吕晓彤",
        "media_type": "image",
        "priority": 1,
        "receipt_path": str(
            _image_receipt(
                tmp_path,
                identity="initial",
                version="initial-version",
                stem="initial",
            )
        ),
    }
    service.create_batch("dynamic", [initial])
    service.submit_child(
        "dynamic",
        {
            "adapter": "lv_text_image",
            "source_identity": "later",
            "version_identity": "later-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 2,
            "receipt_path": str(
                _image_receipt(
                    tmp_path,
                    identity="later",
                    version="later-version",
                    stem="later",
                )
            ),
        },
    )

    restarted = BatchCoordinator(tmp_path / "batch", now=clock)
    state = restarted.create_batch("dynamic", [initial])
    assert {row["source_identity"] for row in state["children"]} == {
        "initial",
        "later",
    }


def test_submit_child_is_idempotent_after_completion_but_rejects_drift(
    tmp_path: Path,
):
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    child = {
        "adapter": "xiaocao_live",
        "source_identity": "kol-real-live",
        "version_identity": "a" * 64,
        "author": "小草",
        "media_type": "video",
        "priority": 80,
        "receipt_path": str(_xiaocao_receipt(tmp_path)),
    }
    service.create_batch("completed-submit", [child])
    service.run_once("completed-submit")
    service.run_once("completed-submit")
    before = service.status("completed-submit")["append_only_event_count"]

    replay = service.submit_child("completed-submit", child)

    assert replay["status"] == "completed"
    assert replay["append_only_event_count"] == before
    with pytest.raises(BatchError, match="metadata changed"):
        service.submit_child(
            "completed-submit",
            {**child, "priority": 79},
        )


@pytest.mark.parametrize(
    "adapter",
    ["xiaocao_live", "lv_text_image", "subscription_video"],
)
def test_source_receipt_contract_violations_pause_only_that_child(
    tmp_path: Path,
    adapter: str,
):
    if adapter == "xiaocao_live":
        receipt_path = _xiaocao_receipt(tmp_path)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["enrichment"]["market_first"] = False
        _write_json(receipt_path, receipt)
        child = {
            "adapter": adapter,
            "source_identity": "kol-real-live",
            "version_identity": "a" * 64,
            "author": "小草",
            "media_type": "video",
            "priority": 80,
            "receipt_path": str(receipt_path),
        }
    elif adapter == "lv_text_image":
        receipt_path = _image_receipt(tmp_path)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        bundle_path = Path(receipt["decision_bundle_path"])
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle["items"][0]["trade_information_coverage"][
            "named_asset_inventory"
        ] = None
        _write_json(bundle_path, bundle)
        import hashlib

        receipt["decision_bundle_sha256"] = hashlib.sha256(
            bundle_path.read_bytes()
        ).hexdigest()
        _write_json(receipt_path, receipt)
        child = {
            "adapter": adapter,
            "source_identity": "lv-real-image",
            "version_identity": "image-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 40,
            "receipt_path": str(receipt_path),
        }
    else:
        receipt_path = _video_receipt(tmp_path)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        del receipt["samples"][0]["cloud_transfer"]["claim_before_trigger"]
        _write_json(receipt_path, receipt)
        child = {
            "adapter": adapter,
            "source_identity": "lv-real-video",
            "version_identity": "video-version",
            "author": "吕晓彤",
            "media_type": "video",
            "priority": 90,
            "receipt_path": str(receipt_path),
        }
    service = BatchCoordinator(tmp_path / adapter, now=Clock(NOW))
    service.create_batch("broken-contract", [child])

    service.run_once("broken-contract")
    service.run_once("broken-contract")

    assert service.status("broken-contract")["children"][0]["status"] == "paused"


def test_broken_child_evidence_pauses_without_blocking_other_ready_child(
    tmp_path: Path,
):
    broken = _write_json(
        tmp_path / "broken-state.json",
        {
            "event": "subscription_decisions_completed",
            "status": "decided",
            "identity": "broken-image",
            "version_key": "broken-version",
            "decision_bundle_path": str(tmp_path / "missing-bundle.json"),
            "decision_bundle_sha256": "4" * 64,
            "decision_result_path": str(tmp_path / "missing-result.json"),
            "decision_result_sha256": "5" * 64,
            "household_notification": {
                "status": "delivered",
                "idempotency_key": "6" * 64,
            },
            "book_kol_us": {
                "paper_only": True,
                "status": "no_trade",
                "reason": "Missing evidence cannot trade.",
            },
        },
    )
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "broken-window",
        [
            {
                "adapter": "xiaocao_live",
                "source_identity": "kol-real-live",
                "version_identity": "a" * 64,
                "author": "小草",
                "media_type": "video",
                "priority": 100,
                "receipt_path": str(_xiaocao_receipt(tmp_path)),
            },
            {
                "adapter": "lv_text_image",
                "source_identity": "broken-image",
                "version_identity": "broken-version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 40,
                "receipt_path": str(broken),
            },
        ],
    )
    service.run_once("broken-window")

    service.run_once("broken-window")

    status = {
        row["source_identity"]: row
        for row in service.status("broken-window")["children"]
    }
    assert status["kol-real-live"]["status"] == "terminal"
    assert status["broken-image"]["status"] == "paused"
    assert status["broken-image"]["failure_reason"] == "missing_evidence"


def test_completed_cli_run_is_compact_and_leaves_details_to_audit(
    tmp_path: Path,
):
    output = tmp_path / "batch"
    spec = _write_json(
        tmp_path / "compact-spec.json",
        {
            "batch_id": "compact-window",
            "children": [{
                "adapter": "lv_text_image",
                "source_identity": "lv-real-image",
                "version_identity": "image-version",
                "author": "吕晓彤",
                "media_type": "image",
                "priority": 40,
                "receipt_path": str(_image_receipt(tmp_path)),
            }],
            "watched_artifacts": [],
        },
    )
    script = Path(__file__).parents[1] / "scripts" / "kol_batch.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "run",
            "--spec",
            str(spec),
            "--output-dir",
            str(output),
            "--poll-interval-seconds",
            "0.1",
        ],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert len(result.stdout.encode("utf-8")) < 2_000
    assert "receipt_path" not in result.stdout
    assert json.loads(result.stdout) == {
        "acceptance_status": "incomplete",
        "batch_id": "compact-window",
        "children": [{
            "adapter": "lv_text_image",
            "author": "吕晓彤",
            "book_kol_us": "no_trade",
            "household": "delivered",
            "media_type": "image",
            "status": "terminal",
        }],
        "coordinator_source_video_bytes": 0,
        "interruption_count": 0,
        "new_external_side_effect_count": 0,
        "status": "completed",
        "terminal_receipt_count": 1,
    }


def _completed_insight_batch(
    tmp_path: Path,
) -> tuple[BatchCoordinator, dict]:
    service = BatchCoordinator(tmp_path / "batch", now=Clock(NOW))
    service.create_batch(
        "insight-window",
        [{
            "adapter": "lv_text_image",
            "source_identity": "lv-real-image",
            "version_identity": "image-version",
            "author": "吕晓彤",
            "media_type": "image",
            "priority": 40,
            "receipt_path": str(_image_receipt(tmp_path)),
        }],
        insight_required=True,
    )
    service.run_once("insight-window")
    service.run_once("insight-window")
    child = service.status("insight-window")["children"][0]
    receipt = child["terminal_receipt"]
    insight = {
        "batch_id": "insight-window",
        "title": "KOL批处理洞察",
        "body": "市场优先：等待广度修复，不追涨。家庭建议仅供参考。",
        "evidence_bindings": [{
            "adapter": child["adapter"],
            "evidence_sha256": receipt["evidence_sha256"],
            "decision_result_sha256": receipt["decision_result_sha256"],
        }],
    }
    return service, insight


def test_batch_insight_claims_before_sync_wechat_and_replay_does_not_send(
    tmp_path: Path,
):
    service, insight = _completed_insight_batch(tmp_path)
    with pytest.raises(BatchError, match="before batch insight delivery"):
        service.record_runner_completed("insight-window")
    calls: list[tuple[str, str, str]] = []

    def sender(recipient: str, title: str, body: str) -> str:
        claims = [
            row
            for row in service.events()
            if row["event"] == "batch_insight_delivery_claimed"
        ]
        assert len(claims) == len(calls) + 1
        assert recipient not in service.events_path.read_text(encoding="utf-8")
        calls.append((recipient, title, body))
        return "ok"

    first = service.publish_insight(
        "insight-window",
        insight,
        recipients=["Chen", "FeiFei", "Chen"],
        sender=sender,
    )
    replay = service.publish_insight(
        "insight-window",
        insight,
        recipients=["Chen", "FeiFei"],
        sender=sender,
    )

    assert len(calls) == 2
    assert first == {
        "status": "delivered",
        "insight_id": first["insight_id"],
        "content_sha256": first["content_sha256"],
        "message_utf8_bytes": len(
            f"{insight['title']}\n{insight['body']}".encode("utf-8")
        ),
        "chunk_count": 1,
        "recipient_count": 2,
        "recipient_receipt_count": 2,
        "new_recipient_send_count": 2,
        "new_external_side_effect_count": 1,
        "idempotent_replay": False,
    }
    assert replay == {
        **first,
        "new_recipient_send_count": 0,
        "new_external_side_effect_count": 0,
        "idempotent_replay": True,
    }
    status = service.status("insight-window")
    assert status["batch_insight"] == {
        "status": "delivered",
        "insight_id": first["insight_id"],
        "content_sha256": first["content_sha256"],
        "message_utf8_bytes": first["message_utf8_bytes"],
        "chunk_count": 1,
        "recipient_count": 2,
        "recipient_receipt_count": 2,
        "uncertain_recipient_count": 0,
    }
    audit = service.audit("insight-window")
    assert audit["batch_insight"]["status"] == "delivered"
    assert audit["requirements"]["batch_insight_delivered"] is True
    assert audit["new_external_side_effect_count"] == 1
    with pytest.raises(BatchError, match="recipient set changed"):
        service.publish_insight(
            "insight-window",
            insight,
            recipients=["Chen"],
            sender=sender,
        )


def test_uncertain_batch_insight_claim_is_never_blindly_retried(
    tmp_path: Path,
):
    service, insight = _completed_insight_batch(tmp_path)
    calls = 0

    def sender(_recipient: str, _title: str, _body: str) -> str:
        nonlocal calls
        calls += 1
        return "http 500"

    with pytest.raises(BatchError, match="not confirmed"):
        service.publish_insight(
            "insight-window",
            insight,
            recipients=["Chen"],
            sender=sender,
        )
    with pytest.raises(BatchError, match="uncertain prior"):
        service.publish_insight(
            "insight-window",
            insight,
            recipients=["Chen"],
            sender=sender,
        )

    assert calls == 1
    assert service.status("insight-window")["batch_insight"]["status"] == (
        "uncertain"
    )


def test_batch_insight_rejects_unbound_or_oversized_content(
    tmp_path: Path,
):
    service, insight = _completed_insight_batch(tmp_path)

    with pytest.raises(BatchError, match="evidence bindings"):
        service.publish_insight(
            "insight-window",
            {**insight, "evidence_bindings": []},
            recipients=["Chen"],
            sender=lambda *_args: "ok",
        )
    with pytest.raises(BatchError, match="2,048-byte"):
        service.publish_insight(
            "insight-window",
            {**insight, "body": "洞察" * 1_000},
            recipients=["Chen"],
            sender=lambda *_args: "ok",
        )
