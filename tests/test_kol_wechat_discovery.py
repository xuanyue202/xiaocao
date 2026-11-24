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


def test_keycap_numbered_history_link_is_bound_to_same_message():
    from xiaocao.kol.replay_catalog import ReplayCatalogConfig, ReplayCatalogError, verify_catalogue_binding

    history = {"chat": "test-contact", "username": "exact-contact-id", "messages": [
        "[2026-11-23 09:17] test-contact: 1⃣课程：#小程序://见势擒龙团/abc12345\n"
        "2️⃣历史直播回放点击链接学习：https://yv9lc.xetslk.com/s/4uRHyc"
    ]}
    items = parse_xiaocao_live_messages(history)
    mini = next(item for item in items if item.get("entry_kind") == "wechat_mini_program")
    link = next(item for item in items if item.get("source_url"))
    assert link["recorded_navigation_marker"] is True
    assert link["message_sha256"] == mini["message_sha256"]
    config = ReplayCatalogConfig('appTest123', 'course_Example123', 'OldToken',
        navigation_source_url='https://yv9lc.xetslk.com/s/4uRHyc')
    verify_catalogue_binding(config, mini, items)
    with pytest.raises(ReplayCatalogError, match='original_catalog_binding_invalid'):
        verify_catalogue_binding(config, mini, [mini, link, {**mini, 'identity': 'kol-wechat-' + 'f' * 24}])


def test_preopen_anchor_requires_exact_original_session_announcement():
    message = ("[2026-11-23 09:17] test-contact: ⏰企业微信app课程已发送，09：20和草神一起看\n\n"
               "1⃣盘前早盘+晚盘【密码666】：#小程序://见势擒龙团/abc12345\n"
               "2️⃣历史直播回放点击链接学习：https://yv9lc.xetslk.com/s/4uRHyc")
    def mini(text):
        history = {'chat':'test-contact', 'username':'exact-contact-id', 'messages':[text]}
        return next(x for x in parse_xiaocao_live_messages(history) if x.get('entry_kind') == 'wechat_mini_program')
    assert mini(message)['recorded_preopen_start_at'] == '2026-11-23T09:20:00+08:00'
    for changed in (message.replace('盘前早盘+晚盘', '课程回放'),
                    message.replace('09：20', '08：20'),
                    message + '\n#小程序://见势擒龙团/another123',
                    message + '\n1⃣盘前早盘+晚盘【密码666】：duplicate',
                    message.replace('企业微信app课程已发送', '明天课程')):
        assert 'recorded_preopen_start_at' not in mini(changed)


def test_exact_original_history_is_bounded_complete_and_never_transcribes(tmp_path):
    from xiaocao.kol.enrichment_types import EnrichmentError
    from xiaocao.kol.xiaocao_wechat import WechatCliHistoryReader
    executable = tmp_path/'wechat-cli'; executable.touch()
    calls = []
    def runner(command, **kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(stdout=json.dumps({'chat':'contact','messages':['one'],
                                                  'count':1,'limit':80,'offset':0,'failures':[]}))
    reader = WechatCliHistoryReader('contact', executable=executable, runner=runner)
    assert reader.read_original('2026-11-23T09:17:00+08:00')['count'] == 1
    command, options = calls[0]
    assert command[command.index('--voice')+1] == 'off'
    assert command[command.index('--start-time')+1] == '2026-11-23 09:16:00'
    assert command[command.index('--end-time')+1] == '2026-11-23 09:18:00'
    assert options['timeout'] == 60
    def truncated(command, **kwargs):
        return SimpleNamespace(stdout=json.dumps({'chat':'contact','messages':['x']*80,
                                                  'count':80,'limit':80,'offset':0}))
    with pytest.raises(EnrichmentError, match='window is incomplete'):
        WechatCliHistoryReader('contact',executable=executable,runner=truncated).read_original('2026-11-23T09:17:00+08:00')


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
