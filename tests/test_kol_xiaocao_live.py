from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.kol_claim_fixture import attach_claim_contract
from xiaocao.kol.capture import (
    CaptureJobStore,
    SnifferError,
    canonical_xiaoetong_source,
)
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.xiaocao_live import (
    REQUIRED_COVERAGE_ROWS,
    XiaocaoLiveService,
    _default_sniffer_binary,
    capture_runtime_environment,
    validate_cleanup_evidence,
    validate_coverage_matrix,
    source_publication_time,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("bad", [None, "date", "future", "naive"])
def test_source_publication_time_is_separate_from_ingestion(tmp_path, bad):
    capsule = {"published_at": "2026-09-29T09:01:27+08:00",
        "source_published_at": "2026-09-23T08:44:00+08:00", "source_event_date": "2026-09-23"}
    if bad == "date": capsule["source_event_date"] = "2026-09-29"
    if bad == "future": capsule.update(source_published_at="2026-09-30T08:44:00+08:00", source_event_date="2026-09-30")
    if bad == "naive": capsule["source_published_at"] = "2026-09-23T08:44:00"
    if bad:
        with pytest.raises(EnrichmentError): source_publication_time(capsule)
    else:
        assert source_publication_time(capsule) == "2026-09-23T08:44:00+08:00"
        assert source_publication_time({"published_at": capsule["published_at"]}) == capsule["published_at"]


@pytest.mark.parametrize("detached", [True, False])
def test_capture_cleanup_preserves_other_proxy_only_with_owned_endpoint_readback(detached):
    evidence = {"process_gone": True, "api_status_unavailable": True,
        "listeners": {"2022": False, "2023": False},
        "proxy_flags": {"HTTPEnable": 0, "HTTPSEnable": 0, "ProxyAutoConfigEnable": 1, "SOCKSEnable": 0},
        "capture_proxy_detached": detached, "observed_at": "2026-09-05T15:00:00+08:00"}
    if detached:
        validate_cleanup_evidence(evidence)
    else:
        with pytest.raises(EnrichmentError):
            validate_cleanup_evidence(evidence)


@pytest.mark.parametrize("active", [False, True])
def test_backend_repair_keeps_capture_and_does_not_record_terminal_cleanup(tmp_path, monkeypatch, active):
    installed, replacement = tmp_path / "sniffer", tmp_path / "sniffer.repair"
    installed.write_bytes(b"old")
    replacement.write_bytes(b"new")
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    current = store.transition(store.arm([]), "hold", status="download_retry_claimed", download_task_id="failed")
    tasks = [{"id": "failed", "status": "error", "progress": {"downloaded": 0}}]
    if active:
        tasks.append({"id": "other", "status": "running"})
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=store.path,
        sniffer_binary=installed, sniffer_client=SimpleNamespace(tasks=lambda: tasks))
    calls = []
    pids = iter([[123], []])
    monkeypatch.setattr(service, "_sniffer_pids", lambda: next(pids))
    monkeypatch.setattr(service, "_disable_owned_capture_pac", lambda: calls.append("pac_off"))
    monkeypatch.setattr("xiaocao.kol.xiaocao_live.os.kill", lambda *a: calls.append("stop"))
    monkeypatch.setattr(service, "cleanup_snapshot", lambda: {
        "process_gone": True, "api_status_unavailable": True,
        "listeners": {"2022": False, "2023": False},
        "proxy_flags": {"HTTPEnable": 0, "HTTPSEnable": 0, "ProxyAutoConfigEnable": 0, "SOCKSEnable": 0},
        "observed_at": "2026-09-05T15:00:00+08:00"})
    monkeypatch.setattr(service, "start", lambda: {"capture_job_id": current["job_id"]})
    if active:
        with pytest.raises(EnrichmentError, match="active downloads"):
            service.restart_sniffer_for_download_repair(current["job_id"], replacement_binary=replacement)
        assert calls == [] and installed.read_bytes() == b"old"
        return
    result = service.restart_sniffer_for_download_repair(current["job_id"], replacement_binary=replacement)
    assert result["capture_job_id"] == current["job_id"]
    assert calls == ["pac_off", "stop"]
    assert installed.read_bytes() == b"new"
    assert Path(result["backup_binary"]).read_bytes() == b"old"
    assert store.latest()["status"] == "download_retry_claimed"
    assert store.latest()["job_id"] == current["job_id"]
    assert store.latest()["native_repair_armed_at"]
    assert service._event("capture_cleanup_completed", capture_job_id=current["job_id"]) is None


@pytest.mark.parametrize("invalid", [None, "active", "changed", "wrong_capture", "unfinished"])
def test_backend_install_after_exact_cleanup_never_starts_sniffer(tmp_path, monkeypatch, invalid):
    installed, replacement = tmp_path / "sniffer", tmp_path / "sniffer.repair"
    installed.write_bytes(b"old"); replacement.write_bytes(b"new")
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=tmp_path / "capture.jsonl", sniffer_binary=installed)
    job = service.capture_store.arm([])
    service.capture_store.transition(job, "downloaded", status="downloading" if invalid == "unfinished" else "downloaded")
    proof = {"capture_job_id": "other" if invalid == "wrong_capture" else job["job_id"],
        "process_gone": True, "api_status_unavailable": True,
        "listeners": {"2022": False, "2023": False},
        "proxy_flags": {"HTTPEnable": 0, "HTTPSEnable": 0, "ProxyAutoConfigEnable": 0, "SOCKSEnable": 0},
        "observed_at": "2026-09-29T08:00:00+08:00"}
    path = tmp_path / "cleanup.json"; path.write_text(json.dumps(proof))
    service._append("capture_cleanup_completed", capture_job_id=job["job_id"],
        cleanup_evidence_path=str(path), cleanup_evidence_sha256=_sha256(path))
    if invalid == "changed": path.write_text("{}")
    monkeypatch.setattr(service, "_sniffer_pids", lambda: [1] if invalid == "active" else [])
    monkeypatch.setattr(service, "cleanup_snapshot", lambda: proof)
    monkeypatch.setattr(service, "start", lambda: pytest.fail("never start for installation"))
    if invalid:
        with pytest.raises(EnrichmentError):
            service.install_sniffer_repair_after_cleanup(job["job_id"], replacement_binary=replacement)
        assert installed.read_bytes() == b"old" and replacement.exists()
    else:
        receipt = service.install_sniffer_repair_after_cleanup(job["job_id"], replacement_binary=replacement)
        assert installed.read_bytes() == b"new"
        assert Path(receipt["backup_binary"]).read_bytes() == b"old"
        assert receipt["sniffer_started"] is False


@pytest.mark.parametrize("invalid", [None, "active", "claimed", "wrong_live", "stale", "liveplay", "not_closed",
    "retained", "retained_wrong_media", "retained_wrong_source", "retained_stale"])
def test_native_observation_repair_retains_unbound_capture_without_acceptance(tmp_path, monkeypatch, invalid):
    installed, replacement = tmp_path / "sniffer", tmp_path / "sniffer.repair"
    installed.write_bytes(b"old")
    replacement.write_bytes(b"new")
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    current = store.transition(store.arm([]), "clock", created_at="2026-09-05T15:00:00+08:00")
    if invalid == "claimed":
        current = store.transition(current, "claimed", source_job_id="existing")
    resource = "https://encrypt-k-vod.xet.tech/content/playlist_eof.m3u8"
    candidate = {"id": "native", "live_id": "l_target", "captured": "2026-09-05 15:01:00",
        "media_type": "m3u8", "url": resource + "?sign=private", "source_url": resource + "?sign=private",
        "source_path": "/content/playlist_eof.m3u8"}
    previous_observation = None
    if invalid and invalid.startswith("retained"):
        previous_observation = {"candidate_id":"original", "captured_at":"2026-09-05T15:00:30+08:00",
            "source_identity_observed":"xiaoetong:appdemo:l_target",
            "media_resource_sha256":hashlib.sha256(resource.encode()).hexdigest(),
            "source_accepted":False, "playback_window_closed":True}
        if invalid == "retained_wrong_media":
            previous_observation["media_resource_sha256"] = "0" * 64
        if invalid == "retained_wrong_source":
            previous_observation["source_identity_observed"] = "xiaoetong:appother:l_target"
        if invalid == "retained_stale":
            candidate["captured"] = "2026-09-05 15:00:40"
        current = store.transition(current, "retained", native_unbound_media=previous_observation,
            native_repair_armed_at="2026-09-05T15:00:45+08:00")
    if invalid == "wrong_live":
        candidate["live_id"] = "l_other"
    if invalid == "stale":
        candidate["captured"] = "2026-09-05 14:59:00"
    if invalid == "liveplay":
        candidate.update(url=resource.replace("playlist_eof", "liveplay"),
            source_url=resource.replace("playlist_eof", "liveplay"), source_path="/content/liveplay.m3u8")
    tasks = [{"id": "other", "status": "running"}] if invalid == "active" else []
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=store.path, sniffer_binary=installed,
        sniffer_client=SimpleNamespace(tasks=lambda: tasks, candidates=lambda: [candidate]))
    calls = []
    pids = iter([[123], []])
    monkeypatch.setattr(service, "_sniffer_pids", lambda: next(pids))
    monkeypatch.setattr(service, "_disable_owned_capture_pac", lambda: calls.append("pac_off"))
    monkeypatch.setattr("xiaocao.kol.xiaocao_live.os.kill", lambda *a: calls.append("stop"))
    monkeypatch.setattr(service, "cleanup_snapshot", lambda: {
        "process_gone": True, "api_status_unavailable": True, "listeners": {"2022": False, "2023": False},
        "proxy_flags": {"HTTPEnable": 0, "HTTPSEnable": 0, "ProxyAutoConfigEnable": 0, "SOCKSEnable": 0},
        "observed_at": "2026-09-05T15:00:00+08:00"})
    monkeypatch.setattr(service, "start", lambda: {"capture_job_id": current["job_id"]})
    kwargs = dict(replacement_binary=replacement, candidate_id="native", source_identity="xiaoetong:appdemo:l_target",
        playback_window_closed=invalid != "not_closed")
    if invalid and invalid != "retained":
        with pytest.raises(EnrichmentError):
            service.restart_sniffer_for_native_observation_repair(current["job_id"], **kwargs)
        assert calls == [] and store.latest() == current and installed.read_bytes() == b"old"
        return
    result = service.restart_sniffer_for_native_observation_repair(current["job_id"], **kwargs)
    retained = store.latest()
    assert result["capture_job_id"] == retained["job_id"] == current["job_id"]
    assert retained["status"] == "awaiting_capture" and not retained.get("expected_source")
    assert not retained.get("candidate") and not retained.get("download_task_id")
    assert retained["native_unbound_media"]["media_resource_sha256"] == hashlib.sha256(resource.encode()).hexdigest()
    if previous_observation:
        assert retained["native_unbound_media"] == previous_observation
    assert retained["native_repair_armed_at"] and "private" not in store.path.read_text()
    assert calls == ["pac_off", "stop"] and installed.read_bytes() == b"new"
    assert service._event("capture_cleanup_completed", capture_job_id=current["job_id"]) is None


def test_capture_runtime_preserves_environment_and_adds_installed_tools(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("XIAOCAO_ENV_TEST", "preserved")
    environment = capture_runtime_environment()
    assert environment["PATH"].startswith("/usr/bin:/bin")
    assert environment["XIAOCAO_ENV_TEST"] == "preserved"
    for directory in ("/opt/homebrew/bin", "/usr/local/bin"):
        if Path(directory).is_dir():
            assert directory in environment["PATH"].split(os.pathsep)
    assert os.environ["PATH"] == "/usr/bin:/bin"


@pytest.mark.parametrize("url,expected_writes", [
    ("http://127.0.0.1:2023/proxy.pac", 1),
    ("http://127.0.0.1:33331/commands/pac", 0),
])
def test_capture_cleanup_disables_only_owned_pac(tmp_path, url, expected_writes):
    writes = []

    def runner(command, **kwargs):
        if command == ["scutil", "--proxy"]:
            return SimpleNamespace(stdout=f"ProxyAutoConfigEnable : 1\nProxyAutoConfigURLString : {url}\n")
        if command == ["networksetup", "-listallnetworkservices"]:
            return SimpleNamespace(stdout="An asterisk denotes disabled services\nWi-Fi\nOther\n")
        if command[:2] == ["networksetup", "-getautoproxyurl"]:
            configured = url if command[2] == "Wi-Fi" else "https://unrelated.example/pac"
            enabled = "No" if writes and command[2] == "Wi-Fi" else "Yes"
            return SimpleNamespace(stdout=f"URL: {configured}\nEnabled: {enabled}\n")
        writes.append(command)
        assert command == ["networksetup", "-setautoproxystate", "Wi-Fi", "off"]
        return SimpleNamespace(stdout="")

    service = XiaocaoLiveService(tmp_path / "live", runner=runner)
    service._disable_owned_capture_pac()
    assert len(writes) == expected_writes


@pytest.mark.parametrize("service_prefix", ["", "*"])
def test_capture_cleanup_checks_inactive_network_services(tmp_path, service_prefix):
    writes = []

    def runner(command, **kwargs):
        if command == ["scutil", "--proxy"]:
            return SimpleNamespace(stdout="ProxyAutoConfigEnable : 0\n")
        if command == ["networksetup", "-listallnetworkservices"]:
            return SimpleNamespace(stdout=f"An asterisk denotes disabled services\n{service_prefix}Wi-Fi\nUSB LAN\n")
        if command[:2] == ["networksetup", "-getautoproxyurl"]:
            url = "http://127.0.0.1:2023/proxy.pac" if command[2] == "Wi-Fi" else "http://vpn.example/pac"
            enabled = "No" if writes and command[2] == "Wi-Fi" else "Yes"
            return SimpleNamespace(stdout=f"URL: {url}\nEnabled: {enabled}\n")
        writes.append(command)
        return SimpleNamespace(stdout="")

    XiaocaoLiveService(tmp_path / "live", runner=runner)._disable_owned_capture_pac()
    assert writes == [["networksetup", "-setautoproxystate", "Wi-Fi", "off"]]


def test_capture_pac_noop_write_cannot_prove_cleanup(tmp_path):
    def runner(command, **kwargs):
        if command == ["networksetup", "-listallnetworkservices"]:
            return SimpleNamespace(stdout="An asterisk denotes disabled services\nWi-Fi\n")
        if command[:2] == ["networksetup", "-getautoproxyurl"]:
            return SimpleNamespace(stdout="URL: http://127.0.0.1:2023/proxy.pac\nEnabled: Yes\n")
        return SimpleNamespace(stdout="")

    with pytest.raises(EnrichmentError, match="detachment was not verified"):
        XiaocaoLiveService(tmp_path / "live", runner=runner)._disable_owned_capture_pac()


def test_sniffer_singleton_excludes_only_exact_proxy_guard(tmp_path):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    service = XiaocaoLiveService(
        tmp_path / "live", sniffer_binary=binary,
        runner=lambda *args, **kwargs: SimpleNamespace(stdout=(
            f"101 {binary} --xiaoetong-only\n"
            f"102 {binary} __proxy-guard\n"
            f"103 {binary} --xiaoetong-only --unexpected\n"
        )),
    )
    assert service._sniffer_pids() == [101, 103]


@pytest.mark.parametrize("same_executable", [True, False])
def test_sniffer_manual_relative_launch_requires_actual_executable_identity(
    tmp_path, monkeypatch, same_executable,
):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    actual = binary if same_executable else tmp_path / "other" / binary.name
    monkeypatch.setattr(
        "xiaocao.kol.xiaocao_live._process_executable_path",
        lambda pid: str(actual), raising=False,
    )
    service = XiaocaoLiveService(
        tmp_path / "live", sniffer_binary=binary,
        runner=lambda *args, **kwargs: SimpleNamespace(stdout=(
            "101 ./wx_video_download_macos_arm64 --xiaoetong-only\n"
            "102 ./wx_video_download_macos_arm64 __proxy-guard\n"
        )),
    )
    assert service._sniffer_pids() == ([101] if same_executable else [])


def test_default_sniffer_binary_follows_active_checkout(tmp_path):
    repo_root = tmp_path / "coding" / "xiaocao"

    assert _default_sniffer_binary(repo_root) == (
        tmp_path
        / "coding"
        / "wx_channels_download"
        / "wx_video_download_macos_arm64"
    )


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _canonical_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


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


def test_recorded_capture_contract_accepts_file_bound_candidate(tmp_path):
    ledger = tmp_path / "capture.jsonl"
    store = CaptureJobStore(ledger)
    source = canonical_xiaoetong_source(
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/"
        "v_6a7db774e4b0694c5bfa7583"
    )
    armed = store.arm(
        [],
        expected_source=source,
        expected_media_file_id="5001834815942190711",
    )
    candidate = {
        "id": "vod-capture",
        "live_id": "l_stale",
        "media_type": "m3u8",
        "url": (
            "https://encrypt-k-vod.xet.tech/vod/"
            "773e679a5001834815942190711/drm/v.f421220.m3u8"
        ),
    }
    detected = store.detect_capture(armed, [candidate])
    downloaded = store.transition(
        detected,
        "download_completed",
        status="downloaded",
        download_task={
            "meta": {"labels": {
                "live_id": "l_stale",
                "type": "live_capture",
                "compress": "true",
                "compress_inline": "true",
            }}
        },
    )

    identity = XiaocaoLiveService._capture_contract(downloaded)

    assert identity["capture_id"] == "vod-capture"
    assert identity["live_id"] == "l_stale"


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

    assert first["status"] == "completed"
    assert first["completion_basis"] == "deterministic_receipts"
    assert first["next"] == "none"
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


def test_remote_import_accepts_one_portable_job_capsule_idempotently(tmp_path):
    media_sha256 = "a" * 64
    job_id = "kol-netdisk-aaaaaaaaaaaaaaaa"
    handoff_id = "b" * 64
    snapshot = {
        "schema_version": 1,
        "status": "video_ready",
        "provider": "baidu_consumer_page",
        "job_id": job_id,
        "netdisk_directory": "/课程/自己的课/小草",
        "netdisk_path": "/课程/自己的课/小草/target-compressed.mp4",
        "video_basename": "target-compressed.mp4",
        "video_sha256": media_sha256,
        "video_sha256_kind": "content_sha256",
        "video_size_bytes": 123456,
        "video_duration_seconds": 1800.5,
        "source_mode": "cloud_handoff",
        "large_payload_local_bytes": 0,
        "handoff_id": handoff_id,
    }
    capsule = {
        "schema_version": 2,
        "source": "xiaocao",
        "author": "小草",
        "handoff_id": handoff_id,
        "capture_job_id": "kol-capture-test",
        "live_id": "live-test",
        "captured_at": "2026-08-01T19:30:00+08:00",
        "media_basename": "target-compressed.mp4",
        "media_sha256": media_sha256,
        "media_size_bytes": 123456,
        "media_duration_seconds": 1800.5,
        "netdisk_job_id": job_id,
        "cloud_reference": (
            "baidu:/课程/自己的课/小草/target-compressed.mp4"
        ),
        "provider": "baidu_consumer_page",
        "large_payload_local_bytes": 0,
        "published_at": "2026-08-01T19:45:00+08:00",
        "netdisk_job_snapshot": snapshot,
        "netdisk_job_snapshot_sha256": _canonical_sha256(snapshot),
    }
    capsule["handoff_sha256"] = _canonical_sha256(capsule)
    service = XiaocaoLiveService(
        tmp_path / "remote-live",
        netdisk_output=tmp_path / "remote-netdisk",
    )

    first = service.import_handoff_capsule(capsule)
    second = service.import_handoff_capsule(capsule)

    assert first["status"] == "video_ready"
    assert first["handoff_id"] == handoff_id
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    rows = service.netdisk.store.read()
    assert len(rows) == 1
    assert rows[0]["event"] == "netdisk_remote_handoff_imported"
    assert rows[0]["browser_control_blocked"] is True
    assert "video_path" not in rows[0]
    assert "media_path" not in rows[0]
    assert "browser_evidence" not in rows[0]


def test_publication_reconciliation_derives_legal_no_alert_bundle(tmp_path):
    source = _write_json(tmp_path / "bundle.json", {
        "items": [{
            "content_value": {
                "status": "promoted",
                "tier": "alert_eligible",
                "alert_basis": ["market_posture"],
                "reason": "有当前市场与仓位边界。",
            },
        }],
    })
    artifact_dir = tmp_path / "artifacts" / "job"
    result = _write_json(artifact_dir / "decision_result.json", {
        "status": "completed",
        "items": [{}],
    })
    service = XiaocaoLiveService(tmp_path / "live")

    derived = service._publication_reconciliation_bundle(
        source,
        state={
            "decision_result_path": str(result),
            "household_notification": {
                "status": "delivered",
                "idempotency_key": "a" * 64,
            },
        },
    )

    original = json.loads(source.read_text(encoding="utf-8"))
    reconciled = json.loads(derived.read_text(encoding="utf-8"))
    content = reconciled["items"][0]["content_value"]
    assert original["items"][0]["content_value"]["tier"] == "alert_eligible"
    assert content["tier"] == "report_only"
    assert "alert_basis" not in content
    assert "禁止补发" in content["no_alert_reason"]
    assert reconciled["items"][0]["notification_revision"].startswith(
        "post-handoff-publication-reconciliation-v1-"
    )
    assert reconciled["post_handoff_publication_reconciliation"] == {
        "schema_version": 1,
        "source_bundle_sha256": _sha256(source),
        "prior_notification_idempotency_key": "a" * 64,
        "policy": "publish_report_without_duplicate_reminder",
    }


def test_imported_decided_handoff_reconciles_missing_daily_terminal(
    tmp_path,
    monkeypatch,
):
    requested = _write_json(tmp_path / "bundle.json", {"items": [{}]})
    derived = _write_json(tmp_path / "derived.json", {"items": [{}]})
    prior_result = _write_json(tmp_path / "decision_result.json", {
        "status": "completed",
        "items": [{}],
    })
    revised_result = _write_json(tmp_path / "decision_result.revised.json", {
        "status": "completed",
        "items": [{"daily_terminal": {}}],
    })
    state = {
        "status": "decided",
        "job_id": "job-1",
        "transcript_path": str(tmp_path / "transcript.txt"),
        "transcript_sha256": "b" * 64,
        "decision_bundle_path": str(requested),
        "decision_bundle_sha256": _sha256(requested),
        "decision_result_path": str(prior_result),
        "decision_result_sha256": _sha256(prior_result),
    }
    calls = []

    class Netdisk:
        store = SimpleNamespace(read=lambda: [])

        @staticmethod
        def status(job_id):
            assert job_id == "job-1"
            return dict(state)

        @staticmethod
        def decide(job_id, **kwargs):
            calls.append((job_id, kwargs))
            return {
                **state,
                "decision_bundle_path": str(derived),
                "decision_bundle_sha256": _sha256(derived),
                "decision_result_path": str(revised_result),
                "decision_result_sha256": _sha256(revised_result),
            }

    service = XiaocaoLiveService(
        tmp_path / "live",
        netdisk_service=Netdisk(),
    )
    sentinel_pipeline = object()
    monkeypatch.setattr(
        "xiaocao.kol.xiaocao_live.validate_decision_bundle",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        service,
        "_publication_reconciliation_bundle",
        lambda *_args, **_kwargs: derived,
    )
    monkeypatch.setattr(
        service,
        "_daily_publication_pipeline",
        lambda *_args, **_kwargs: sentinel_pipeline,
    )
    monkeypatch.setattr(
        service,
        "_audit_imported_acceptance",
        lambda *_args, **_kwargs: {"status": "completed", "next": "none"},
    )

    terminal = service._advance_imported_handoff(
        {
            "capture_job_id": "capture-1",
            "netdisk_job_id": "job-1",
            "handoff_id": "c" * 64,
            "media_sha256": "d" * 64,
            "live_id": "live-1",
        },
        opencli_session="session",
        opencli_profile=None,
        audit_path=None,
        bundle_path=requested,
        sender=lambda *_args: {"wecom": "ok"},
    )

    assert terminal == {"status": "completed", "next": "none"}
    assert len(calls) == 1
    assert calls[0][0] == "job-1"
    assert calls[0][1]["bundle_path"] == derived
    assert calls[0][1]["pipeline"] is sentinel_pipeline
    assert calls[0][1]["reconcile_daily_terminal"] is True


@pytest.mark.parametrize("media_day", ["20260723", "20260724"])
def test_publish_handoff_includes_portable_cloud_ready_ledger_snapshot(tmp_path, media_day):
    media_sha256 = "c" * 64
    job_id = f"kol-netdisk-{media_sha256[:16]}"
    service = XiaocaoLiveService(tmp_path / "local-live")
    capture = service.capture_store.arm([])
    service.capture_store.transition(capture, "source_publication_bound",
        source_published_at="2026-07-23T17:07:00+08:00", source_event_date="2026-07-23",
        source_subscription_id="original-subscription", source_message_sha256="a" * 64)
    if media_day == "20260724":
        with pytest.raises(EnrichmentError, match="native video date conflicts"):
            service._publish_handoff(capture_job_id=capture["job_id"],
                media={"live_id":"live-test", "captured_at":"2026-08-01T19:30:00+08:00",
                    "media_basename":f"{media_day} target-compressed.mp4", "media_sha256":media_sha256,
                    "media_size_bytes":123456, "media_duration_seconds":1800.5},
                netdisk={"job_id":job_id})
        return
    published = service._publish_handoff(
        capture_job_id=capture["job_id"],
        media={
            "live_id": "live-test",
            "captured_at": "2026-08-01T19:30:00+08:00",
            "media_basename": f"{media_day} target-compressed.mp4",
            "media_sha256": media_sha256,
            "media_size_bytes": 123456,
            "media_duration_seconds": 1800.5,
            "media_path": "/private/local/target-compressed.mp4",
        },
        netdisk={
            "status": "video_ready",
            "provider": "baidu_consumer_page",
            "job_id": job_id,
            "netdisk_directory": "/课程/自己的课/小草",
            "netdisk_path": "/课程/自己的课/小草/target-compressed.mp4",
            "video_basename": "target-compressed.mp4",
            "video_path": "/private/local/target-compressed.mp4",
            "video_sha256": media_sha256,
            "video_sha256_kind": "content_sha256",
            "video_size_bytes": 123456,
            "video_duration_seconds": 1800.5,
            "browser_evidence": {"session": "local-secret"},
        },
    )

    capsule = json.loads(Path(published["handoff_path"]).read_text())
    assert capsule["schema_version"] == 2
    assert capsule["source_published_at"] == "2026-07-23T17:07:00+08:00"
    assert capsule["source_event_date"] == "2026-07-23"
    assert capsule["published_at"] != capsule["source_published_at"]
    assert capsule["handoff_id"] == published["handoff_claim_idempotency_key"]
    assert capsule["handoff_sha256"] == _canonical_sha256({
        key: value
        for key, value in capsule.items()
        if key != "handoff_sha256"
    })
    snapshot = capsule["netdisk_job_snapshot"]
    assert capsule["netdisk_job_snapshot_sha256"] == _canonical_sha256(snapshot)
    assert snapshot["status"] == "video_ready"
    assert snapshot["source_mode"] == "cloud_handoff"
    assert snapshot["handoff_id"] == capsule["handoff_id"]
    assert snapshot["large_payload_local_bytes"] == 0
    serialized = json.dumps(capsule, ensure_ascii=False)
    assert "/private/local" not in serialized
    assert "browser_evidence" not in serialized
    remote = XiaocaoLiveService(
        tmp_path / "remote-live",
        netdisk_output=tmp_path / "remote-netdisk",
    )
    assert remote.import_handoff_capsule(capsule)["status"] == "video_ready"


def test_remote_audit_accepts_decided_portable_handoff_without_capture_state(
    tmp_path,
):
    transcript = tmp_path / "complete.txt"
    quote = "半导体继续最强才考虑"
    transcript.write_text(quote * 200, encoding="utf-8")
    transcript_sha = _sha256(transcript)
    media_sha256 = "a" * 64
    handoff_id = "b" * 64
    job_id = f"kol-netdisk-{media_sha256[:16]}"
    bundle_item = {
        "decision_status": "actionable_signal",
        "knowledge_status": "reusable_knowledge",
        "knowledge_reason": "来源包含可证伪的风格与仓位方法。",
        "evidence_path": str(transcript),
        "evidence_sha256": transcript_sha,
        "claims": [{
            "claim_id": "xiaocao-semiconductor",
            "quote": quote,
            "reader_quote": "只有半导体继续保持最强时才考虑参与。",
        }],
        "trade_information_coverage": _coverage(quote),
        "market_outlook": {"summary": "市场结论优先。"},
        "book_kol_us": {
            "decision": "no_trade",
            "reason": "没有明确美国上市标的和有效交易触发。",
        },
    }
    attach_claim_contract(bundle_item, transcript)
    bundle = _write_json(tmp_path / "bundle.json", {"items": [bundle_item]})
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
    snapshot = {
        "schema_version": 1,
        "status": "video_ready",
        "provider": "baidu_consumer_page",
        "job_id": job_id,
        "netdisk_directory": "/课程/自己的课/小草",
        "netdisk_path": "/课程/自己的课/小草/target-compressed.mp4",
        "video_basename": "target-compressed.mp4",
        "video_sha256": media_sha256,
        "video_sha256_kind": "content_sha256",
        "video_size_bytes": 123456,
        "video_duration_seconds": 1800.5,
        "source_mode": "cloud_handoff",
        "large_payload_local_bytes": 0,
        "handoff_id": handoff_id,
    }
    capsule = {
        "schema_version": 2,
        "source": "xiaocao",
        "author": "小草",
        "handoff_id": handoff_id,
        "capture_job_id": "kol-capture-test",
        "live_id": "live-test",
        "captured_at": "2026-08-01T19:30:00+08:00",
        "media_basename": "target-compressed.mp4",
        "media_sha256": media_sha256,
        "media_size_bytes": 123456,
        "media_duration_seconds": 1800.5,
        "netdisk_job_id": job_id,
        "cloud_reference": (
            "baidu:/课程/自己的课/小草/target-compressed.mp4"
        ),
        "provider": "baidu_consumer_page",
        "large_payload_local_bytes": 0,
        "published_at": "2026-08-01T19:45:00+08:00",
        "netdisk_job_snapshot": snapshot,
        "netdisk_job_snapshot_sha256": _canonical_sha256(snapshot),
    }
    capsule["handoff_sha256"] = _canonical_sha256(capsule)
    state = {
        **snapshot,
        "status": "decided",
        "transcript_path": str(transcript),
        "transcript_sha256": transcript_sha,
        "transcript_character_count": len(transcript.read_text(encoding="utf-8")),
        "audit_sha256": "c" * 64,
        "ai_note_template_no": 1,
        "ai_note_triggered_at": "2026-08-01T20:00:00+08:00",
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
            "idempotency_key": "d" * 64,
        },
    }
    netdisk_events = [
        {"job_id": job_id, "event": "netdisk_remote_handoff_imported"},
        {"job_id": job_id, "event": "netdisk_transcript_requested"},
        {"job_id": job_id, "event": "netdisk_ai_note_triggered"},
        {"job_id": job_id, "event": "netdisk_decisions_completed"},
    ]
    decision_output = tmp_path / "decisions"
    _append_jsonl(decision_output / "events.jsonl", {
        "event": "notification_transport_content_alias_validated",
        "idempotency_key": "e" * 64,
    })
    _append_jsonl(decision_output / "events.jsonl", {
        "event": "notification_delivered",
        "idempotency_key": "e" * 64,
    })
    _append_jsonl(decision_output / "book_kol_us" / "decisions.jsonl", {
        "idempotency_key": "d" * 64,
        "book": "KOL-US",
        "paper_only": True,
        "status": "no_trade",
        "reason": "没有明确美国上市标的和有效交易触发。",
    })
    service = XiaocaoLiveService(
        tmp_path / "remote-live",
        netdisk_output=tmp_path / "remote-netdisk",
        decision_output=decision_output,
    )
    service.import_handoff_capsule(capsule)
    for row in netdisk_events[1:]:
        service.netdisk.store.append({**snapshot, **row})
    service.netdisk.store.append(state)

    first = service.advance(
        "kol-capture-test",
        opencli_session="remote-session",
        sender=lambda *_args: pytest.fail("decided replay must not resend"),
    )
    second = service.audit_acceptance("kol-capture-test")
    acceptance = json.loads(
        Path(first["acceptance_evidence_path"]).read_text(encoding="utf-8")
    )

    assert first["status"] == "completed"
    assert first["completion_basis"] == "deterministic_receipts"
    assert first["next"] == "none"
    assert first["new_external_side_effect_count"] == 0
    assert second["idempotent_replay"] is True
    assert acceptance["scope"] == "post_handoff"
    assert acceptance["status"] == "completed"
    assert acceptance["completion_basis"] == "deterministic_receipts"
    assert acceptance["upstream_attestation"]["handoff_id"] == handoff_id
    assert acceptance["side_effect_counts"] == {
        "handoff_import": 1,
        "transcript_request": 1,
        "ai_note_request": 1,
        "household_notification": 1,
        "book_kol_us": 1,
    }
    assert not (tmp_path / "capture.jsonl").exists()


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

    assert first["status"] == "completed"
    assert first["completion_basis"] == "deterministic_receipts"
    assert first["next"] == "none"
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
    assert receipt["status"] == "completed"
    assert receipt["completion_basis"] == "deterministic_receipts"
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


def test_legacy_confirmation_migration_is_exactly_once(tmp_path):
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

    def popen(command, **_kwargs):
        assert command == [str(binary), "--xiaoetong-only"]
        assert _kwargs["env"] == capture_runtime_environment()
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
        sleep=lambda _seconds: None,
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


def test_start_rejects_api_that_dies_before_proxy_is_stable(tmp_path):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    state = {"running": False}

    class Sniffer:
        def status(self):
            if not state["running"]:
                raise SnifferError("not running")
            return {"version": "test", "running": True}

    class Process:
        pid = 1234

    def popen(*_args, **_kwargs):
        state["running"] = True
        return Process()

    def runner(command, **_kwargs):
        if command[0] == "ps":
            stdout = f"1234 {binary}\n" if state["running"] else ""
            return SimpleNamespace(stdout=stdout)
        raise AssertionError(command)

    def sleep(_seconds):
        state["running"] = False

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=tmp_path / "capture.jsonl",
        sniffer_binary=binary,
        sniffer_client=Sniffer(),
        popen=popen,
        runner=runner,
        sleep=sleep,
    )

    with pytest.raises(EnrichmentError, match="did not become healthy"):
        service.start()

    assert not any(
        row["event"] in {"sniffer_started", "capture_armed"}
        for row in service.events()
    )


def test_start_with_xiaoetong_page_arms_bound_source_job_without_query_state(
    tmp_path,
):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    state = {"running": False}
    calls = []

    class Sniffer:
        def status(self):
            if not state["running"]:
                raise SnifferError("not running")
            return {"version": "test", "running": True}

        @staticmethod
        def candidates():
            calls.append("baseline")
            return [{"live_id": "l_old"}]

        @staticmethod
        def arm_xiaoetong_source(_page_url):
            calls.append("source_job")
            return {
                "id": "source-1",
                "status": "awaiting_playback",
                "live_id": "l_target",
            }

    class Process:
        pid = 1234

    def popen(*_args, **_kwargs):
        state["running"] = True
        return Process()

    def runner(command, **_kwargs):
        if command[0] == "ps":
            stdout = f"1234 {binary}\n" if state["running"] else ""
            return SimpleNamespace(stdout=stdout)
        raise AssertionError(command)

    ledger = tmp_path / "capture.jsonl"
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_binary=binary,
        sniffer_client=Sniffer(),
        popen=popen,
        runner=runner,
        sleep=lambda _seconds: None,
    )
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/alive/l_target"
        "?share_user_id=private&share_type=5"
    )

    result = service.start(page_url=page_url)
    capture = CaptureJobStore(ledger).latest(result["capture_job_id"])

    assert result["source_job_id"] == "source-1"
    assert calls == ["baseline", "source_job"]
    assert result["source_identity"] == "xiaoetong:appsnm3rlcp3566:l_target"
    assert result["prompt"].startswith("请在已登录浏览器刷新或播放这个小鹅通页面")
    assert capture is not None
    assert capture["source_job_id"] == "source-1"
    assert capture["expected_source"]["source_resource_id"] == "l_target"
    persisted = ledger.read_text(encoding="utf-8") + service.events_path.read_text(
        encoding="utf-8"
    )
    assert "share_user_id" not in persisted
    assert page_url not in persisted


def test_start_with_recorded_video_page_arms_file_bound_capture_without_source_job(
    tmp_path,
):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    calls = []

    class Sniffer:
        @staticmethod
        def status():
            return {"version": "test", "running": True}

        @staticmethod
        def candidates():
            calls.append("baseline")
            return [{"id": "candidate-old", "live_id": "l_stale"}]

        @staticmethod
        def arm_xiaoetong_source(_page_url):
            raise AssertionError("recorded video must not use live source jobs")

    def runner(command, **_kwargs):
        if command[0] == "ps":
            return SimpleNamespace(stdout=f"1234 {binary}\n")
        raise AssertionError(command)

    ledger = tmp_path / "capture.jsonl"
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_binary=binary,
        sniffer_client=Sniffer(),
        runner=runner,
        sleep=lambda _seconds: None,
    )
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/"
        "v_6a7db774e4b0694c5bfa7583"
    )

    result = service.start(
        page_url=page_url,
        media_file_id="5001834815942190711",
    )
    capture = CaptureJobStore(ledger).latest(result["capture_job_id"])

    assert calls == ["baseline"]
    assert "source_job_id" not in result
    assert result["source_identity"] == (
        "xiaoetong:appsnm3rlcp3566:v_6a7db774e4b0694c5bfa7583"
    )
    assert capture is not None
    assert capture["expected_media_file_id"] == "5001834815942190711"


def test_start_rejects_recorded_video_without_media_file_binding(tmp_path):
    service = XiaocaoLiveService(tmp_path / "live")

    with pytest.raises(EnrichmentError, match="recorded media file binding"):
        service.start(
            page_url=(
                "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/"
                "v_6a7db774e4b0694c5bfa7583"
            )
        )


def test_start_classifies_sniffer_candidate_baseline_failure(tmp_path):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")

    class Sniffer:
        @staticmethod
        def status():
            return {"version": "test", "running": True}

        @staticmethod
        def candidates():
            raise SnifferError("candidate baseline timed out")

    def runner(command, **_kwargs):
        if command[0] == "ps":
            return SimpleNamespace(stdout=f"1234 {binary}\n")
        raise AssertionError(command)

    service = XiaocaoLiveService(
        tmp_path / "live",
        sniffer_binary=binary,
        sniffer_client=Sniffer(),
        runner=runner,
    )

    with pytest.raises(EnrichmentError, match="baseline is unavailable"):
        service.start()


def test_advance_xiaoetong_source_reuses_auto_created_download_task(tmp_path):
    ledger = tmp_path / "capture.jsonl"
    source = {
        "source_kind": "xiaoetong",
        "source_host": "appsnm3rlcp3566.h5.xiaoeknow.com",
        "source_app_id": "appsnm3rlcp3566",
        "source_resource_id": "l_target",
        "source_identity": "xiaoetong:appsnm3rlcp3566:l_target",
    }
    store = CaptureJobStore(ledger)
    armed = store.arm(
        [{"id": "candidate-before-arm", "live_id": "l_target"}],
        expected_source=source,
        source_job_id="source-1",
    )
    calls = {"create": 0, "source": 0}

    class Sniffer:
        @staticmethod
        def xiaoetong_source_job(job_id):
            assert job_id == "source-1"
            calls["source"] += 1
            return {
                "id": "source-1",
                "status": "task_created",
                "live_id": "l_target",
                "candidate_id": "candidate-1",
                "task_id": "task-1",
            }

        @staticmethod
        def candidates():
            return [{
                "id": "candidate-1",
                "live_id": "l_target",
                "filename": "target.mp4",
                "media_type": "m3u8",
                "captured": "2026-08-04 11:25:17",
                "url": "https://example.test/live.m3u8?sign=secret",
            }]

        @staticmethod
        def tasks():
            return [{
                "id": "task-1",
                "status": "running",
                "meta": {"req": {"labels": {
                    "live_id": "l_target",
                    "type": "live_capture",
                    "compress": "true",
                }}},
            }]

        @staticmethod
        def start_download(*_args, **_kwargs):
            calls["create"] += 1
            return "duplicate-task"

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_client=Sniffer(),
    )

    result = service.advance_capture(armed["job_id"])

    assert result["status"] == "downloading"
    assert result["download_task_id"] == "task-1"
    assert calls == {"create": 0, "source": 1}


def test_advance_recovers_completed_source_task_after_candidate_is_retired(tmp_path):
    ledger = tmp_path / "capture.jsonl"
    source = {
        "source_kind": "xiaoetong",
        "source_host": "appsnm3rlcp3566.h5.xiaoeknow.com",
        "source_app_id": "appsnm3rlcp3566",
        "source_resource_id": "l_target",
        "source_identity": "xiaoetong:appsnm3rlcp3566:l_target",
    }
    armed = CaptureJobStore(ledger).arm(
        [],
        expected_source=source,
        source_job_id="source-1",
    )

    class Sniffer:
        @staticmethod
        def xiaoetong_source_job(_job_id):
            return {
                "id": "source-1",
                "status": "task_created",
                "live_id": "l_target",
                "candidate_id": "candidate-retired",
                "task_id": "task-1",
            }

        @staticmethod
        def candidates():
            raise AssertionError("exact completed task must bypass candidate scan")

        @staticmethod
        def tasks():
            return [{
                "id": "task-1",
                "status": "done",
                "meta": {
                    "opts": {"name": "target-compressed.mp4", "path": "/tmp"},
                    "req": {"labels": {
                        "capture_id": "candidate-retired",
                        "live_id": "l_target",
                        "media_type": "m3u8",
                        "source_job_id": "source-1",
                        "type": "live_capture",
                        "compress": "true",
                    }},
                },
            }]

        @staticmethod
        def start_download(*_args, **_kwargs):
            raise AssertionError("must reuse the exact completed source task")

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_client=Sniffer(),
    )

    result = service.advance_capture(armed["job_id"])

    assert result["status"] == "downloaded"
    assert result["download_task_id"] == "task-1"
    assert result["media_path"] == "/tmp/target-compressed.mp4"


def test_advance_surfaces_awaiting_playback_for_hourly_page_recheck(tmp_path):
    ledger = tmp_path / "capture.jsonl"
    source = {
        "source_kind": "xiaoetong",
        "source_host": "appsnm3rlcp3566.h5.xiaoeknow.com",
        "source_app_id": "appsnm3rlcp3566",
        "source_resource_id": "l_target",
        "source_identity": "xiaoetong:appsnm3rlcp3566:l_target",
    }
    armed = CaptureJobStore(ledger).arm(
        [],
        expected_source=source,
        source_job_id="source-1",
    )

    class Sniffer:
        @staticmethod
        def xiaoetong_source_job(job_id):
            assert job_id == "source-1"
            return {
                "id": "source-1",
                "status": "awaiting_playback",
                "live_id": "l_target",
            }

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_client=Sniffer(),
    )

    result = service.advance(
        armed["job_id"],
        opencli_session="xiaocao-lv-subscription",
    )

    assert result == {
        "event": "xiaocao_live_pending",
        "status": "awaiting_capture",
        "capture_job_id": armed["job_id"],
        "source_job_status": "awaiting_playback",
        "next": "rerun",
    }


def test_advance_xiaoetong_source_retries_orphaned_restored_task_with_fresh_candidate(
    tmp_path,
):
    ledger = tmp_path / "capture.jsonl"
    source = {
        "source_kind": "xiaoetong",
        "source_host": "appsnm3rlcp3566.h5.xiaoeknow.com",
        "source_app_id": "appsnm3rlcp3566",
        "source_resource_id": "l_target",
        "source_identity": "xiaoetong:appsnm3rlcp3566:l_target",
    }
    store = CaptureJobStore(ledger)
    armed = store.arm(
        [{"id": "candidate-before-arm", "live_id": "l_target"}],
        expected_source=source,
        source_job_id="source-1",
    )
    retries: list[str] = []

    class Sniffer:
        @staticmethod
        def xiaoetong_source_job(_job_id):
            return {
                "id": "source-1",
                "status": "task_created",
                "live_id": "l_target",
                "candidate_id": "candidate-no-longer-resolvable",
                "task_id": "task-restored-error",
            }

        @staticmethod
        def retry_xiaoetong_source_job(job_id):
            assert job_id == "source-1"
            retries.append(job_id)
            return {
                "id": "source-1",
                "status": "task_created",
                "live_id": "l_target",
                "candidate_id": "candidate-fresh",
                "task_id": "task-retry-fresh",
            }

        @staticmethod
        def candidates():
            return [{
                "id": "candidate-fresh",
                "live_id": "l_target",
                "filename": "target.mp4",
                "media_type": "m3u8",
                "captured": "2026-08-04 11:25:17",
                "url": "https://example.test/live.m3u8?sign=fresh",
            }]

        @staticmethod
        def tasks():
            return ([{
                    "id": "task-retry-fresh",
                    "status": "running",
                    "meta": {"req": {"labels": {
                        "live_id": "l_target",
                        "type": "live_capture",
                        "compress": "true",
                    }}},
                }] if retries else [])

        @staticmethod
        def start_download(candidate, *, force=False):
            raise AssertionError((candidate, force))

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_client=Sniffer(),
    )

    result = service.advance_capture(armed["job_id"])

    assert result["status"] == "downloading"
    assert result["download_task_id"] == "task-retry-fresh"
    assert retries == ["source-1"]


@pytest.mark.parametrize("downloaded", [0, 266076208])
@pytest.mark.parametrize("provider_status", ["pause", "error"])
def test_paused_native_download_never_creates_replacement_task(tmp_path, downloaded, provider_status):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    candidate = {"id": "native", "live_id": "l_original", "filename": "original.mp4",
        "url": "https://example.test/original/playlist_eof.m3u8"}
    captured = store.detect_capture(store.arm([]), [candidate])
    downloading = store.transition(captured, "download_started", status="downloading",
        download_task_id="original-task", user_resume_required=True)
    task = {"id": "original-task", "status": provider_status, "progress": {"downloaded": downloaded}}
    calls = []
    class Sniffer:
        def tasks(self): return [task]
        def candidates(self): return [candidate]
        def start_download(self, candidate, *, force=False):
            calls.append((candidate["id"], force)); return "replacement-task"
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=store.path,
        sniffer_client=Sniffer())
    result = service.advance_capture(downloading["job_id"])
    assert calls == []
    assert result["download_task_id"] == "original-task"
    assert result["status"] == "downloading"
    assert result.get("user_resume_required") is True


def test_paused_zero_byte_source_task_returns_to_source_retry(tmp_path):
    ledger = tmp_path / "capture.jsonl"
    store = CaptureJobStore(ledger)
    armed = store.arm([], source_job_id="source-1")
    downloading = store.transition(
        armed,
        "download_started",
        status="downloading",
        download_task_id="task-paused",
    )

    class Sniffer:
        @staticmethod
        def tasks():
            return [{
                "id": "task-paused",
                "status": "pause",
                "progress": {"downloaded": 0},
            }]

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_client=Sniffer(),
    )

    result = service.advance_capture(downloading["job_id"])

    assert result["event"] == "source_retry_pending"
    assert result["status"] == "awaiting_capture"


def test_pause_during_provider_read_wins_over_download_error(tmp_path):
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=tmp_path / "capture.jsonl")
    job = service.capture_store.transition(service.capture_store.arm([]), "download_started",
        status="downloading", download_task_id="original-task")
    def tasks():
        service.capture_store.transition(job, "capture_user_pause_claimed", user_resume_required=True)
        return [{"id": "original-task", "status": "error"}]
    service.sniffer = SimpleNamespace(tasks=tasks,
        start_download=lambda *a, **k: pytest.fail("pause cannot create a replacement"))
    result = service.advance_capture(job["job_id"])
    assert result["event"] == "capture_user_pause_claimed"
    assert result["download_task_id"] == "original-task"
    assert result["user_resume_required"] is True


def test_pause_is_durable_before_provider_side_effect(tmp_path):
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=tmp_path / "capture.jsonl")
    job = service.capture_store.transition(service.capture_store.arm([]), "download_started",
        status="downloading", download_task_id="original-task")
    calls = []
    def pause(task_id):
        assert service.capture_store.latest(job["job_id"])["user_resume_required"] is True
        calls.append(task_id)
        return {"id": task_id}
    service.sniffer = SimpleNamespace(pause_task=pause,
        tasks=lambda: [{"id": "original-task", "status": "pause", "progress": {"downloaded": 123}}])
    result = service.pause_capture(job["job_id"])
    assert result["paused_task_receipt"] == {"id": "original-task", "status": "pause", "downloaded_bytes": 123}
    assert service.pause_capture(job["job_id"])["idempotent_replay"] is True
    assert calls == ["original-task"]
    with pytest.raises(EnrichmentError, match="explicit resume"):
        service.resume_interrupted_capture(job["job_id"])


@pytest.mark.parametrize("capture_pac_enabled", [False, True])
def test_cancel_wait_stops_only_the_idle_sniffer_and_restores_proxy(
    tmp_path,
    monkeypatch,
    capture_pac_enabled,
):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    ledger = tmp_path / "capture.jsonl"
    store = CaptureJobStore(ledger)
    armed = store.arm([{"live_id": "live-old"}])
    state = {"running": True, "pac_enabled": capture_pac_enabled}

    class Sniffer:
        @staticmethod
        def status():
            if not state["running"]:
                raise SnifferError("not running")
            return {"version": "test", "running": True}

        @staticmethod
        def candidates():
            return [{"live_id": "live-old"}]

    def runner(command, **_kwargs):
        if command[0] == "ps":
            stdout = f"1234 {binary}\n" if state["running"] else ""
            return SimpleNamespace(stdout=stdout)
        if command[:2] == ["scutil", "--proxy"]:
            return SimpleNamespace(
                stdout=(
                    "HTTPEnable : 0\n"
                    "HTTPSEnable : 0\n"
                    f"ProxyAutoConfigEnable : {int(state['pac_enabled'])}\n"
                    "ProxyAutoConfigURLString : http://127.0.0.1:2023/proxy.pac\n"
                    "SOCKSEnable : 0\n"
                )
            )
        if command == ["networksetup", "-listallnetworkservices"]:
            return SimpleNamespace(stdout="An asterisk denotes disabled services\nWi-Fi\n")
        if command == ["networksetup", "-getautoproxyurl", "Wi-Fi"]:
            enabled = "Yes" if state["pac_enabled"] else "No"
            return SimpleNamespace(stdout=f"URL: http://127.0.0.1:2023/proxy.pac\nEnabled: {enabled}\n")
        if command == ["networksetup", "-setautoproxystate", "Wi-Fi", "off"]:
            state["pac_enabled"] = False
            return SimpleNamespace(stdout="")
        raise AssertionError(command)

    def kill(_pid, _signal):
        assert not state["pac_enabled"], "network still points at the proxy being stopped"
        state["running"] = False

    class ClosedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def settimeout(_timeout):
            return None

        @staticmethod
        def connect_ex(_address):
            return 1

    monkeypatch.setattr("xiaocao.kol.xiaocao_live.os.kill", kill)
    monkeypatch.setattr(
        "xiaocao.kol.xiaocao_live.socket.socket",
        lambda *_args, **_kwargs: ClosedSocket(),
    )
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_binary=binary,
        sniffer_client=Sniffer(),
        runner=runner,
    )
    service._append(
        "capture_armed",
        status="awaiting_capture",
        capture_job_id=armed["job_id"],
    )

    cancelled = service.cancel_capture_wait(armed["job_id"])

    assert cancelled["event"] == "capture_wait_cancelled"
    assert cancelled["status"] == "wait_cancelled"
    assert cancelled["process_gone"] is True
    assert cancelled["proxy_flags"] == {
        "HTTPEnable": 0,
        "HTTPSEnable": 0,
        "ProxyAutoConfigEnable": 0,
        "SOCKSEnable": 0,
    }
    assert not any(
        row["event"] == "capture_cleanup_completed"
        for row in service.events()
    )


def test_cancel_wait_preserves_a_new_candidate_seen_before_ledger_poll(
    tmp_path,
    monkeypatch,
):
    binary = tmp_path / "wx_video_download_macos_arm64"
    binary.write_bytes(b"binary")
    ledger = tmp_path / "capture.jsonl"
    store = CaptureJobStore(ledger)
    armed = store.arm([{"live_id": "live-old"}])
    state = {"killed": False}

    class Sniffer:
        @staticmethod
        def candidates():
            return [{
                "id": "capture-new",
                "live_id": "live-new",
                "captured": "2026-08-03 14:00:00",
                "filename": "morning.mp4",
                "title": "盘前大师班",
            }]

    def kill(_pid, _signal):
        state["killed"] = True

    monkeypatch.setattr("xiaocao.kol.xiaocao_live.os.kill", kill)
    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_binary=binary,
        sniffer_client=Sniffer(),
    )

    with pytest.raises(EnrichmentError, match="new capture candidate"):
        service.cancel_capture_wait(armed["job_id"])

    assert state["killed"] is False
    assert store.latest(armed["job_id"])["status"] == "captured"


@pytest.mark.parametrize("changed", [None, "capture_id", "live_id", "compress_inline", "status"])
def test_interrupted_capture_resumes_only_original_task_once(tmp_path, changed):
    calls = []
    task = {"id": "same-task", "status": "pause", "protocol": "stream", "meta": {"labels": {
        "capture_id": "same-candidate", "live_id": "l_same", "type": "live_capture",
        "compress": "true", "compress_inline": "true"}}}
    if changed == "status":
        task["status"] = "running"
    elif changed:
        task["meta"]["labels"][changed] = "other"
    class Sniffer:
        def tasks(self):
            return [task]
        def resume_task(self, task_id):
            calls.append(task_id)
            return {"id": task_id}
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=tmp_path / "capture.jsonl",
        sniffer_client=Sniffer())
    armed = service.capture_store.arm([])
    service.capture_store.transition(armed, "download_started", status="downloading",
        candidate={"id": "same-candidate", "live_id": "l_same"}, download_task_id="same-task")
    if changed:
        with pytest.raises(EnrichmentError, match="does not bind"):
            service.resume_interrupted_capture(armed["job_id"])
        assert calls == []
    else:
        result = service.resume_interrupted_capture(armed["job_id"])
        assert result["download_task_id"] == "same-task"
        assert service.resume_interrupted_capture(armed["job_id"])["idempotent_replay"] is True
        assert calls == ["same-task"]


@pytest.mark.parametrize("stale", [False, True])
def test_stalled_same_task_repair_requires_old_partial_output(tmp_path, stale):
    import os
    import time
    target = tmp_path / "same-compressed.mp4"
    target.write_bytes(b"partial")
    if stale:
        os.utime(target, (time.time() - 600, time.time() - 600))
    task = {"id": "same-task", "name": target.name, "status": "running", "protocol": "stream",
        "meta": {"opts": {"path": str(tmp_path)}, "labels": {
        "capture_id": "same-candidate", "live_id": "l_same", "type": "live_capture",
        "compress": "true", "compress_inline": "true"}}}
    calls = []
    class Sniffer:
        def tasks(self): return [task]
        def pause_task(self, task_id):
            calls.append(("pause", task_id)); task["status"] = "pause"; return {"id": task_id}
        def resume_task(self, task_id):
            calls.append(("resume", task_id)); task["status"] = "running"; return {"id": task_id}
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=tmp_path / "capture.jsonl",
        sniffer_client=Sniffer())
    armed = service.capture_store.arm([])
    service.capture_store.transition(armed, "download_started", status="downloading",
        candidate={"id": "same-candidate", "live_id": "l_same"}, download_task_id="same-task")
    if not stale:
        with pytest.raises(EnrichmentError, match="not proven stalled"):
            service.resume_interrupted_capture(armed["job_id"], stalled_media_repair=True)
        assert calls == []
    else:
        result = service.resume_interrupted_capture(armed["job_id"], stalled_media_repair=True)
        assert result["stalled_resume_claim"]["media_size_bytes"] == 7
        service.resume_interrupted_capture(armed["job_id"], stalled_media_repair=True)
        assert calls == [("pause", "same-task"), ("resume", "same-task")]


def test_reconcile_completed_capture_requires_exact_paused_compressed_task(tmp_path):
    ledger = tmp_path / "capture.jsonl"
    store = CaptureJobStore(ledger)
    armed = store.arm([{"live_id": "live-old"}])
    candidate = {
        "id": "capture-new",
        "live_id": "live-new",
        "captured": "2026-08-02 23:06:46",
        "filename": "20260802 大师班专场.mp4",
        "title": "大师班专场",
    }
    detected = store.detect_capture(armed, [candidate])
    assert detected is not None
    store.transition(
        detected,
        "download_started",
        status="downloading",
        download_task_id="task-new",
    )
    media = tmp_path / "20260802 大师班专场-compressed.mp4"
    media.write_bytes(b"compressed-video")
    task = {
        "id": "task-new",
        "status": "pause",
        "protocol": "stream",
        "name": media.name,
        "meta": {
            "opts": {"path": str(tmp_path), "name": media.name},
            "req": {
                "labels": {
                    "capture_id": "capture-new",
                    "live_id": "live-new",
                    "type": "live_capture",
                    "compress": "true",
                    "compress_inline": "true",
                    "hls_duration_sec": "120.0",
                }
            },
        },
    }

    class Sniffer:
        @staticmethod
        def tasks():
            return [task]

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_client=Sniffer(),
        runner=_probe_runner(media, 120.0),
    )

    first = service.reconcile_completed_capture(armed["job_id"])
    second = service.reconcile_completed_capture(armed["job_id"])

    assert first["status"] == "downloaded"
    assert first["event"] == "download_completed_reconciled"
    assert first["provider_status_observed"] == "pause"
    assert first["download_task"]["meta"]["labels"]["compress"] == "true"
    assert second["idempotent_replay"] is True


def test_reconcile_completed_capture_rejects_running_task(tmp_path):
    ledger, capture_job_id, _media, _duration = _capture_fixture(tmp_path)
    store = CaptureJobStore(ledger)
    current = store.latest(capture_job_id)
    assert current is not None
    current = store.transition(
        current,
        "download_progress",
        status="downloading",
    )

    class Sniffer:
        @staticmethod
        def tasks():
            task = dict(current["download_task"])
            task["status"] = "running"
            return [task]

    service = XiaocaoLiveService(
        tmp_path / "live",
        capture_ledger=ledger,
        sniffer_client=Sniffer(),
    )

    with pytest.raises(EnrichmentError, match="not durably paused"):
        service.reconcile_completed_capture(capture_job_id)


@pytest.mark.parametrize("raw_name", [None, "target.mp4", "target (1).mp4"])
def test_validate_collision_numbered_compressed_media(tmp_path, raw_name):
    ledger, job_id, media, duration = _capture_fixture(tmp_path)
    numbered = media.with_name("target-compressed (1).mp4")
    media.rename(numbered)
    store = CaptureJobStore(ledger)
    current = store.latest(job_id)
    task = current["download_task"]
    task["name"] = numbered.name
    task["meta"]["opts"]["name"] = numbered.name
    store.transition(current, "download_completed", status="downloaded",
                     media_path=str(numbered), download_task=task)
    service = XiaocaoLiveService(tmp_path / "live", capture_ledger=ledger,
                                 runner=_probe_runner(numbered, duration))
    if raw_name:
        (tmp_path / raw_name).write_bytes(b"raw")
        with pytest.raises(EnrichmentError, match="retained a raw"):
            service.validate_media(job_id)
    else:
        receipt = service.validate_media(job_id)
        assert receipt["media_sha256"] == _sha256(numbered)
        assert receipt["media_basename"] == numbered.name
