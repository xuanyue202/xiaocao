from __future__ import annotations

import json
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

from scripts import kol_daily
from xiaocao.kol.daily import DailyCoordinator, TransientSourceError
from xiaocao.kol.xiaocao_wechat import (
    XiaocaoWechatLiveSubscription,
    parse_xiaocao_live_messages,
)


def test_retained_capture_repair_still_discovers_new_original_entries(tmp_path):
    now = [datetime.fromisoformat("2026-10-20T16:00:00+08:00")]
    coordinator = DailyCoordinator(tmp_path / "daily", now=lambda: now[0])
    history = {
        "chat": "test-contact", "username": "exact-contact-id", "messages": [],
    }
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "subscription", contact="test-contact",
        history_reader=lambda: history,
        browser_exchange=lambda _: pytest.fail("discovery must not open native UI"),
        capture_driver=SimpleNamespace(), clock=lambda: now[0],
    )
    manifest = subscription._load()
    manifest["initialized_at"] = "2026-10-16T10:00:00+08:00"
    subscription._save(manifest)
    attempts = []

    def failed_capture():
        attempts.append("native")
        raise TransientSourceError(
            "retained input failure", category="input_error",
            code="native_window_input_unavailable", stage="native_playback_input",
        )

    first = coordinator.run([{"name": "xiaocao_wechat_live", "run": failed_capture}])
    fingerprint = first["source_results"][0]["writer_progress"]["failure_fingerprint"]
    history["messages"] = [
        "[2026-10-20 17:29] test-contact: #小程序://见势擒龙团/evening-entry",
        "[2026-10-20 08:41] test-contact: #小程序://见势擒龙团/morning-entry",
    ]
    now[0] = datetime.fromisoformat("2026-10-20T18:00:00+08:00")
    discovery_calls = []

    def discover():
        discovery_calls.append("scan")
        return subscription.discover()

    sources = [{"name": "xiaocao_wechat_live", "run": failed_capture,
                "discover": discover}]
    result = coordinator.run(sources)
    expected = {item["identity"] for item in parse_xiaocao_live_messages(history)}
    saved = subscription._load()["items"]
    assert expected <= saved.keys(), "retained repair starved original-message discovery"
    source = next(row for row in result["source_results"]
                  if row["name"] == "xiaocao_wechat_live")
    assert source["writer_progress"]["failure_fingerprint"] == fingerprint
    assert source["repair_required"] is True
    assert source["discovery"]["discovered_count"] == 2
    assert {item["identity"] for item in source["discovery"]["pending_items"]} == expected
    assert all(saved[key]["status"] == "discovered" for key in expected)
    assert attempts == ["native"]
    assert discovery_calls == ["scan"]
    state = coordinator.status()["last_sweep"]["source_states"][0]
    assert state["discovery"] == source["discovery"]
    now[0] = datetime.fromisoformat("2026-10-20T21:00:00+08:00")
    again = coordinator.run(sources)["source_results"][0]
    assert again["discovery"]["discovered_count"] == 0
    assert again["writer_progress"]["failure_fingerprint"] == fingerprint
    assert attempts == ["native"]


def test_discovery_failure_preserves_original_repair_and_other_sources(tmp_path):
    service = DailyCoordinator(tmp_path, now=lambda: datetime.fromisoformat(
        "2026-10-20T18:00:00+08:00"))

    def failed():
        raise RuntimeError("original fault")

    first = service.run([{"name": "xiaocao_wechat_live", "run": failed}])
    original = first["source_results"][0]["writer_progress"]

    def failed_discovery():
        raise TransientSourceError(
            "private input must not be exported", category="source_error",
            code="wechat_history_incomplete", stage="wechat_scan",
        )

    result = service.run([
        {"name": "xiaocao_wechat_live", "run": failed, "discover": failed_discovery},
        {"name": "wechat_official_accounts", "run": lambda: {"status": "no_update"}},
    ])
    source = next(row for row in result["source_results"]
                  if row["name"] == "xiaocao_wechat_live")
    assert source["writer_progress"] == original
    assert source["discovery"]["status"] == "failed"
    assert source["discovery"]["failure"]["code"] == "wechat_history_incomplete"
    assert next(row for row in result["source_results"]
                if row["name"] == "wechat_official_accounts")["status"] == "no_update"
    assert "private input" not in json.dumps(service.events())


def test_source_adapter_keeps_discovery_capability():
    discover = lambda: {"discovered_count": 1}
    adapter = kol_daily.SourceAdapter(
        name="xiaocao_wechat_live", priority=10, run=lambda: None,
        narrow_resume=lambda _: None, reconcile=lambda _: None, discover=discover,
    )
    assert adapter.coordinator_entry()["discover"] is discover


def test_local_cli_registers_metadata_only_discovery(tmp_path, monkeypatch):
    calls = []

    class Coordinator:
        def __init__(self, _path):
            pass

        def run(self, sources, **_kwargs):
            local = next(row for row in sources if row["name"] == "xiaocao_wechat_live")
            assert local["discover"]() == {"status": "scanned"}
            return {"silent": True}

    def capture(_runtime, *, discovery_only=False):
        assert discovery_only, "must not enter the ordinary capture runner"
        calls.append("metadata")
        return {"status": "scanned"}

    monkeypatch.setattr(kol_daily, "DailyCoordinator", Coordinator)
    monkeypatch.setattr(kol_daily.DailyRuntime, "xiaocao_wechat", capture)
    monkeypatch.setattr(kol_daily.DailyRuntime, "reconcile_local_mailbox", lambda _: [])
    monkeypatch.setattr(sys, "argv", ["kol_daily.py", "capture-local",
                                    "--output-dir", str(tmp_path)])
    assert kol_daily.main() == 0
    assert calls == ["metadata"]


def test_discovery_keeps_bound_media_but_expires_ungenerated_entries(tmp_path):
    history = {
        "chat": "test-contact", "username": "exact-contact-id", "messages": [
            "[2026-10-16 16:29] test-contact: #小程序://见势擒龙团/oldentry",
            "[2026-10-20 17:29] test-contact: #小程序://见势擒龙团/newentry",
        ],
    }
    old, fresh = parse_xiaocao_live_messages(history)
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path, contact="test-contact", history_reader=lambda: history,
        browser_exchange=lambda _: pytest.fail("must not activate"),
        capture_driver=SimpleNamespace(),
        clock=lambda: datetime.fromisoformat("2026-10-21T08:00:00+08:00"),
    )
    manifest = subscription._load()
    manifest["initialized_at"] = "2026-10-16T08:00:00+08:00"
    manifest["items"]["bound"] = {
        **old, "identity": "bound", "status": "awaiting_playback",
        "capture_job_id": "original-capture", "candidate_id": "original-candidate",
    }
    subscription._save(manifest)
    result = subscription.discover()
    saved = subscription._load()
    assert saved["items"][old["identity"]]["status"] == "expired"
    assert saved["items"][fresh["identity"]]["status"] == "discovered"
    assert saved["items"]["bound"] == manifest["items"]["bound"]
    assert result["expired_count"] == 1
    assert saved["last_discovery"] == result


@pytest.mark.parametrize("outside_window", [False, True])
def test_discovery_obeys_source_busy_and_runtime_window(tmp_path, outside_window):
    now = datetime.fromisoformat(
        "2026-10-21T06:00:00+08:00" if outside_window else "2026-10-21T08:00:00+08:00"
    )
    service = DailyCoordinator(tmp_path, now=lambda: now)
    source = {"name": "xiaocao_wechat_live",
              "run": lambda: pytest.fail("must not execute"),
              "discover": lambda: pytest.fail("must not discover")}
    if outside_window:
        assert service.run([source])["status"] == "outside_window"
    else:
        with service._source_slot("xiaocao_wechat_live") as busy:
            assert not busy
            other = DailyCoordinator(tmp_path, now=lambda: now)
            result = other.run([source])
            assert result["source_results"][0]["code"] == "source_busy"
