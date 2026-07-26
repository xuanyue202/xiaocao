from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.kol_claim_fixture import attach_claim_contract
from xiaocao.kol.capture import CaptureJobStore, SnifferError
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.xiaocao_live import (
    REQUIRED_COVERAGE_ROWS,
    XiaocaoLiveService,
    validate_cleanup_evidence,
    validate_coverage_matrix,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _coverage(quote: str) -> dict:
    rows = {}
    for name in sorted(REQUIRED_COVERAGE_ROWS):
        rows[name] = {
            "status": "present",
            "evidence_quotes": [quote],
            "reader_meaning": f"{name} 已完整核对。",
            "horizon": "当日到未来数日",
            "triggers": ["保持来源给出的确认条件"],
            "falsifiers": ["来源给出的条件失效"],
        }
    rows["named_asset_inventory"]["assets"] = [
        {
            "surface_form": "五八八七五零",
            "official_name": "汇添富上证科创板芯片ETF",
            "code": "588750",
            "market": "A-share",
            "role": "ETF alternative",
            "resolution_status": "resolved",
        }
    ]
    return rows


def _capture_fixture(tmp_path: Path) -> tuple[Path, str, Path, float]:
    ledger = tmp_path / "capture.jsonl"
    store = CaptureJobStore(ledger)
    armed = store.arm([{"live_id": "live-old"}])
    raw_candidate = {
        "id": "capture-1",
        "live_id": "live-new",
        "captured": "2026-07-21 21:25:40",
        "filename": "target.mp4",
        "title": "大师班专场",
        "url": "https://example.test/live.m3u8?sign=secret",
    }
    detected = store.detect_capture(armed, [raw_candidate])
    assert detected is not None
    downloading = store.transition(
        detected,
        "download_started",
        status="downloading",
        download_task_id="task-1",
    )
    media = tmp_path / "target-compressed.mp4"
    media.write_bytes(b"ticket-03-video")
    downloaded = store.reconcile_download(
        downloading,
        [{
            "id": "task-1",
            "status": "done",
            "name": media.name,
            "meta": {
                "opts": {"path": str(tmp_path), "name": media.name},
                "req": {
                    "url": raw_candidate["url"],
                    "labels": {
                        "capture_id": "capture-1",
                        "live_id": "live-new",
                        "type": "live_capture",
                        "compress": "true",
                        "compress_inline": "true",
                        "hls_duration_sec": "120.0",
                    },
                },
            },
            "progress": {"downloaded": media.stat().st_size},
        }],
    )
    assert downloaded is not None
    return ledger, armed["job_id"], media, 120.0


class _Netdisk:
    def __init__(self, state: dict):
        self.state = state
        self.status_calls = 0
        self.store = SimpleNamespace(
            read=lambda: [{
                "job_id": state["job_id"],
                "event": "netdisk_browser_liveness_ready",
                "updated_at": "2026-07-21T21:36:21+08:00",
            }]
        )

    def status(self, job_id: str) -> dict:
        assert job_id == self.state["job_id"]
        self.status_calls += 1
        return dict(self.state)


def _probe_runner(media: Path, duration: float):
    def run(command, **_kwargs):
        if command[0] == "ffprobe":
            assert Path(command[-1]) == media
            return SimpleNamespace(
                stdout=json.dumps({
                    "format": {
                        "duration": str(duration),
                        "size": str(media.stat().st_size),
                    }
                })
            )
        raise AssertionError(command)

    return run


def test_reconcile_real_chain_is_idempotent_and_publishes_light_handoff(tmp_path):
    ledger, capture_job_id, media, duration = _capture_fixture(tmp_path)
    transcript = tmp_path / "complete.txt"
    quote = "融资盘清干净了"
    transcript.write_text(quote + "，后续等回调。" * 200, encoding="utf-8")
    transcript_sha = _sha256(transcript)
    decision = tmp_path / "decision_result.json"
    decision.write_text('{"status":"completed"}\n', encoding="utf-8")
    state = {
        "status": "decided",
        "job_id": f"kol-netdisk-{_sha256(media)[:16]}",
        "video_sha256": _sha256(media),
        "transcript_path": str(transcript),
        "transcript_sha256": transcript_sha,
        "audit_sha256": "a" * 64,
        "decision_result_sha256": _sha256(decision),
        "household_notification": {
            "status": "delivered",
            "idempotency_key": "e" * 64,
            "receipt": "wecom-relay://ok/redacted",
        },
        "book_kol_us": {
            "book": "KOL-US",
            "paper_only": True,
            "status": "no_trade",
            "reason": "没有明确美国上市标的和有效交易触发。",
            "idempotency_key": "b" * 64,
        },
    }
    netdisk = _Netdisk(state)
    cleanup = tmp_path / "cleanup.json"
    cleanup.write_text(
        json.dumps({
            "process_gone": True,
            "listeners": {"2022": False, "2023": False},
            "api_status_unavailable": True,
            "proxy_flags": {
                "HTTPEnable": 0,
                "HTTPSEnable": 0,
                "ProxyAutoConfigEnable": 0,
                "SOCKSEnable": 0,
            },
            "observed_at": "2026-07-21T21:36:20+08:00",
        }),
        encoding="utf-8",
    )
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(
        json.dumps({
            "capture": {
                "capture_job_id": capture_job_id,
                "live_id": "live-new",
                "media_sha256": _sha256(media),
                "media_size_bytes": media.stat().st_size,
                "media_duration_seconds": duration,
            },
            "enrichment": {
                "netdisk_job_id": state["job_id"],
                "transcript_sha256": transcript_sha,
                "audit_sha256": "a" * 64,
            },
                "outputs": {
                    "decision_result_sha256": _sha256(decision),
                    "household_idempotency_key": "e" * 64,
                    "book_idempotency_key": "b" * 64,
                },
            "decision_quality": {
                "trade_information_coverage": _coverage(quote),
            },
            "side_effect_counts": {
                "capture": 1,
                "upload": 1,
                "transcript_request": 1,
                "ai_note_request": 1,
                "household_notification": 1,
                "book_kol_us": 1,
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        netdisk_service=netdisk,
        runner=_probe_runner(media, duration),
    )

    first = service.reconcile_existing(
        capture_job_id,
        cleanup_evidence_path=cleanup,
        acceptance_evidence_path=acceptance,
    )
    second = service.reconcile_existing(
        capture_job_id,
        cleanup_evidence_path=cleanup,
        acceptance_evidence_path=acceptance,
    )

    assert first["status"] == "awaiting_user_confirmation"
    assert first["new_external_side_effect_count"] == 0
    assert second["idempotent_replay"] is True
    handoff = json.loads(
        (tmp_path / "live" / "handoffs" / f"{capture_job_id}.json").read_text()
    )
    assert handoff["large_payload_local_bytes"] == 0
    assert "media_path" not in handoff
    assert len([
        row
        for row in service.events()
        if row["event"] == "xiaocao_live_acceptance_reconciled"
    ]) == 1


def test_acceptance_audit_proves_exactly_once_real_chain(tmp_path):
    ledger, capture_job_id, media, duration = _capture_fixture(tmp_path)
    transcript = tmp_path / "complete.txt"
    quote = "半导体继续最强才考虑"
    transcript.write_text(quote * 200, encoding="utf-8")
    transcript_sha = _sha256(transcript)
    bundle_item = {
        "decision_status": "actionable_signal",
        "knowledge_status": "reusable_knowledge",
        "knowledge_reason": "来源包含可证伪的风格与仓位方法。",
        "evidence_path": str(transcript),
        "evidence_sha256": transcript_sha,
        "claims": [
            {
                "claim_id": "xiaocao-semiconductor",
                "quote": quote,
                "reader_quote": "只有半导体继续保持最强时才考虑参与。",
            }
        ],
        "trade_information_coverage": _coverage(quote),
        "market_outlook": {"summary": "市场结论优先。"},
        "book_kol_us": {
            "decision": "no_trade",
            "reason": "没有明确美国上市标的和有效交易触发。",
        },
    }
    attach_claim_contract(bundle_item, transcript)
    bundle = _write_json(tmp_path / "bundle.json", {
        "items": [bundle_item]
    })
    decision_result = _write_json(tmp_path / "decision_result.json", {
        "status": "completed",
        "items": [{
            "claims": [{"quote": quote}],
            "synthesis": "系统判断与来源原话分开。",
            "market_validation": {"status": "qualify"},
            "market_outlook": {"summary": "市场结论优先。"},
            "household_recommendation": {"action": "wait"},
        }],
    })
    netdisk_job_id = f"kol-netdisk-{_sha256(media)[:16]}"
    state = {
        "status": "decided",
        "job_id": netdisk_job_id,
        "provider": "baidu_consumer_page",
        "video_sha256": _sha256(media),
        "transcript_path": str(transcript),
        "transcript_sha256": transcript_sha,
        "transcript_character_count": len(transcript.read_text(encoding="utf-8")),
        "audit_sha256": "a" * 64,
        "ai_note_template_no": 1,
        "ai_note_triggered_at": "2026-07-21T21:53:38+08:00",
        "ai_note_completion_required": False,
        "decision_bundle_path": str(bundle),
        "decision_bundle_sha256": _sha256(bundle),
        "decision_result_path": str(decision_result),
        "decision_result_sha256": _sha256(decision_result),
        "household_notification": {
            "status": "delivered",
            "idempotency_key": "e" * 64,
        },
        "book_kol_us": {
            "book": "KOL-US",
            "paper_only": True,
            "status": "no_trade",
            "reason": "没有明确美国上市标的和有效交易触发。",
            "idempotency_key": "b" * 64,
        },
    }
    netdisk_events = [
        {
            "job_id": netdisk_job_id,
            "event": "netdisk_browser_liveness_ready",
            "updated_at": "2026-07-21T21:36:21+08:00",
        },
        {"job_id": netdisk_job_id, "event": "netdisk_upload_started"},
        {"job_id": netdisk_job_id, "event": "netdisk_transcript_requested"},
        {"job_id": netdisk_job_id, "event": "netdisk_ai_note_triggered"},
        {"job_id": netdisk_job_id, "event": "netdisk_decisions_completed"},
    ]
    netdisk = _Netdisk(state)
    netdisk.store = SimpleNamespace(read=lambda: list(netdisk_events))
    decision_output = tmp_path / "decisions"
    _append_jsonl(decision_output / "events.jsonl", {
        "event": "notification_send_claimed",
        "idempotency_key": "e" * 64,
    })
    _append_jsonl(decision_output / "events.jsonl", {
        "event": "notification_delivered",
        "idempotency_key": "e" * 64,
    })
    _append_jsonl(decision_output / "book_kol_us" / "decisions.jsonl", {
        "idempotency_key": "b" * 64,
        "book": "KOL-US",
        "paper_only": True,
        "status": "no_trade",
        "reason": "没有明确美国上市标的和有效交易触发。",
    })
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        netdisk_service=netdisk,
        decision_output=decision_output,
        runner=_probe_runner(media, duration),
    )
    cleanup = _write_json(tmp_path / "cleanup.json", {
        "capture_job_id": capture_job_id,
        "process_gone": True,
        "listeners": {"2022": False, "2023": False},
        "api_status_unavailable": True,
        "proxy_flags": {
            "HTTPEnable": 0,
            "HTTPSEnable": 0,
            "ProxyAutoConfigEnable": 0,
            "SOCKSEnable": 0,
        },
        "observed_at": "2026-07-21T21:36:20+08:00",
    })
    service._append(
        "capture_cleanup_completed",
        status="cleanup_completed",
        cleanup_evidence_path=str(cleanup),
        cleanup_evidence_sha256=_sha256(cleanup),
        **json.loads(cleanup.read_text(encoding="utf-8")),
    )
    handoff_value = {
        "schema_version": 1,
        "capture_job_id": capture_job_id,
        "live_id": "live-new",
        "media_sha256": _sha256(media),
        "media_basename": media.name,
        "netdisk_job_id": netdisk_job_id,
        "large_payload_local_bytes": 0,
    }
    handoff_value["handoff_sha256"] = hashlib.sha256(
        json.dumps(
            handoff_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    handoff = _write_json(tmp_path / "handoff.json", handoff_value)
    service._append(
        "cloud_handoff_published",
        status="handoff_published",
        capture_job_id=capture_job_id,
        live_id="live-new",
        media_sha256=_sha256(media),
        netdisk_job_id=netdisk_job_id,
        handoff_path=str(handoff),
        handoff_sha256=_sha256(handoff),
        coordinator_large_payload_local_bytes=0,
    )
    service._append(
        "xiaocao_live_decided",
        status="decided",
        capture_job_id=capture_job_id,
        live_id="live-new",
        media_sha256=_sha256(media),
        netdisk_job_id=netdisk_job_id,
        transcript_sha256=transcript_sha,
        decision_result_sha256=_sha256(decision_result),
    )

    first = service.audit_acceptance(capture_job_id)
    second = service.audit_acceptance(capture_job_id)
    receipt = json.loads(
        Path(first["acceptance_evidence_path"]).read_text(encoding="utf-8")
    )

    assert first["status"] == "awaiting_user_confirmation"
    assert first["new_external_side_effect_count"] == 0
    assert second["idempotent_replay"] is True
    assert receipt["side_effect_counts"] == {
        "capture": 1,
        "upload": 1,
        "transcript_request": 1,
        "ai_note_request": 1,
        "household_notification": 1,
        "book_kol_us": 1,
    }
    assert receipt["handoff"]["coordinator_large_payload_local_bytes"] == 0

    original_acceptance_path = Path(first["acceptance_evidence_path"])
    original_acceptance_bytes = original_acceptance_path.read_bytes()
    revised_bundle = _write_json(tmp_path / "bundle-v2.json", {
        **json.loads(bundle.read_text(encoding="utf-8")),
        "notification_revision": "context-corrected-v2",
    })
    revised_result = _write_json(tmp_path / "decision-result-v2.json", {
        **json.loads(decision_result.read_text(encoding="utf-8")),
        "revision": "context-corrected-v2",
    })
    netdisk.state.update({
        "decision_bundle_path": str(revised_bundle),
        "decision_bundle_sha256": _sha256(revised_bundle),
        "decision_result_path": str(revised_result),
        "decision_result_sha256": _sha256(revised_result),
        "household_notification": {
            "status": "delivered",
            "idempotency_key": "f" * 64,
        },
    })
    netdisk_events.append({
        "job_id": netdisk_job_id,
        "event": "netdisk_decision_revision_completed",
    })
    _append_jsonl(decision_output / "events.jsonl", {
        "event": "notification_send_claimed",
        "idempotency_key": "f" * 64,
    })
    _append_jsonl(decision_output / "events.jsonl", {
        "event": "notification_delivered",
        "idempotency_key": "f" * 64,
    })

    revised = service.audit_acceptance(capture_job_id)
    revised_replay = service.audit_acceptance(capture_job_id)

    assert revised["idempotent_replay"] is False
    assert revised_replay["idempotent_replay"] is True
    assert revised["decision_result_sha256"] == _sha256(revised_result)
    assert Path(revised["acceptance_evidence_path"]) != original_acceptance_path
    assert original_acceptance_path.read_bytes() == original_acceptance_bytes


def test_confirmation_is_exactly_once(tmp_path):
    service = XiaocaoLiveService(tmp_path / "live")
    service._append(
        "xiaocao_live_acceptance_reconciled",
        status="awaiting_user_confirmation",
        capture_job_id="capture",
        live_id="live",
        media_sha256="m" * 64,
        netdisk_job_id="netdisk",
        transcript_sha256="t" * 64,
        decision_result_sha256="d" * 64,
    )

    completed = service.confirm(
        confirmation="target_live_and_decision_value_confirmed"
    )
    replay = service.confirm(
        confirmation="target_live_and_decision_value_confirmed"
    )

    assert completed["status"] == "completed"
    assert replay["idempotent_replay"] is True


def test_status_reflects_capture_ledger_while_top_level_job_is_armed(tmp_path):
    ledger, capture_job_id, media, _duration = _capture_fixture(tmp_path)
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
    )
    service._append(
        "capture_armed",
        status="awaiting_capture",
        capture_job_id=capture_job_id,
        next="user_playback",
    )

    surface = service.status()

    assert surface["status"] == "downloaded"
    assert surface["event"] == "download_completed"
    assert surface["live_id"] == "live-new"
    assert surface["media_path"] == str(media)
    assert surface["next"] == "rerun"


def test_coverage_requires_all_rows_and_evidence_bound_quotes():
    quote = "半导体继续最强才考虑"
    item = {"trade_information_coverage": _coverage(quote)}
    validate_coverage_matrix(item, evidence_text=f"开头。{quote}。结尾。")

    item["trade_information_coverage"].pop("next_session_playbook")
    with pytest.raises(EnrichmentError, match="coverage"):
        validate_coverage_matrix(item, evidence_text=quote)


def test_cleanup_evidence_is_fail_closed():
    with pytest.raises(EnrichmentError, match="cleanup"):
        validate_cleanup_evidence({
            "process_gone": True,
            "listeners": {"2022": False, "2023": False},
            "api_status_unavailable": True,
            "proxy_flags": {
                "HTTPEnable": 0,
                "HTTPSEnable": 1,
                "ProxyAutoConfigEnable": 0,
                "SOCKSEnable": 0,
            },
            "observed_at": "2026-07-21T21:36:20+08:00",
        })


def test_reconcile_rejects_netdisk_action_before_cleanup(tmp_path):
    ledger, capture_job_id, media, duration = _capture_fixture(tmp_path)
    transcript = tmp_path / "complete.txt"
    quote = "融资盘清干净了"
    transcript.write_text(quote, encoding="utf-8")
    state = {
        "status": "decided",
        "job_id": f"kol-netdisk-{_sha256(media)[:16]}",
        "video_sha256": _sha256(media),
        "transcript_path": str(transcript),
        "transcript_sha256": _sha256(transcript),
        "audit_sha256": "a" * 64,
        "decision_result_sha256": "d" * 64,
        "household_notification": {
            "status": "delivered",
            "idempotency_key": "h" * 64,
        },
        "book_kol_us": {
            "book": "KOL-US",
            "paper_only": True,
            "status": "no_trade",
            "reason": "没有明确美国上市标的和有效交易触发。",
            "idempotency_key": "b" * 64,
        },
    }
    netdisk = _Netdisk(state)
    netdisk.store = SimpleNamespace(
        read=lambda: [{
            "job_id": state["job_id"],
            "event": "netdisk_upload_claimed",
            "updated_at": "2026-07-21T21:38:04+08:00",
        }]
    )
    cleanup = tmp_path / "cleanup.json"
    cleanup.write_text(json.dumps({
        "process_gone": True,
        "listeners": {"2022": False, "2023": False},
        "api_status_unavailable": True,
        "proxy_flags": {
            "HTTPEnable": 0,
            "HTTPSEnable": 0,
            "ProxyAutoConfigEnable": 0,
            "SOCKSEnable": 0,
        },
        "observed_at": "2026-07-21T21:41:43+08:00",
    }), encoding="utf-8")
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(json.dumps({
        "capture": {
            "capture_job_id": capture_job_id,
            "live_id": "live-new",
            "media_sha256": _sha256(media),
            "media_size_bytes": media.stat().st_size,
            "media_duration_seconds": duration,
        },
        "enrichment": {
            "netdisk_job_id": state["job_id"],
            "transcript_sha256": state["transcript_sha256"],
            "audit_sha256": state["audit_sha256"],
        },
        "outputs": {
            "decision_result_sha256": state["decision_result_sha256"],
            "household_idempotency_key": "h" * 64,
            "book_idempotency_key": "b" * 64,
        },
        "decision_quality": {
            "trade_information_coverage": _coverage(quote),
        },
        "side_effect_counts": {
            "capture": 1,
            "upload": 1,
            "transcript_request": 1,
            "ai_note_request": 1,
            "household_notification": 1,
            "book_kol_us": 1,
        },
    }), encoding="utf-8")
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        netdisk_service=netdisk,
        runner=_probe_runner(media, duration),
    )

    with pytest.raises(EnrichmentError, match="before capture cleanup"):
        service.reconcile_existing(
            capture_job_id,
            cleanup_evidence_path=cleanup,
            acceptance_evidence_path=acceptance,
        )


def test_start_emits_one_prompt_after_health_and_baseline(tmp_path):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    state = {"running": False}

    class Sniffer:
        def status(self):
            if not state["running"]:
                raise SnifferError("not running")
            return {"version": "test", "running": True}

        @staticmethod
        def candidates():
            return [{"live_id": "live-old"}]

    class Process:
        pid = 1234

    def popen(*_args, **_kwargs):
        state["running"] = True
        return Process()

    def runner(command, **_kwargs):
        if command[0] == "ps":
            stdout = (
                f"1234 {binary}\n"
                if state["running"]
                else ""
            )
            return SimpleNamespace(stdout=stdout)
        raise AssertionError(command)

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=tmp_path / "capture.jsonl",
        sniffer_binary=binary,
        sniffer_client=Sniffer(),
        popen=popen,
        runner=runner,
    )

    first = service.start()
    second = service.start()
    state["running"] = False
    resumed = service.start()

    assert first["prompt"].startswith("请现在打开企业微信")
    assert first["baseline_count"] == 1
    assert second["prompt"] is None
    assert second["idempotent_replay"] is True
    assert resumed["prompt"] is None
    assert resumed["idempotent_replay"] is True
    resume_events = [
        row for row in service.events() if row["event"] == "sniffer_resumed"
    ]
    assert len(resume_events) == 1
    assert resume_events[0]["prompt_replayed"] is False
    assert len([
        row for row in service.events() if row["event"] == "capture_armed"
    ]) == 1
