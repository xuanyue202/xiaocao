from __future__ import annotations

import json
import hashlib
from types import SimpleNamespace
from base64 import urlsafe_b64encode
from datetime import datetime
from urllib.parse import quote

import pytest

from xiaocao.kol.enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
)
from xiaocao.kol.capture import CaptureJobStore
from xiaocao.kol.xiaocao_wechat import (
    XiaocaoLiveCaptureDriver,
    XiaocaoWechatLiveSubscription,
    XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
    parse_xiaocao_live_messages,
)
from xiaocao.kol.writer_progress import normalize_source_result


CONTACT = "福利官小花四-刘丹（执业编号:A0380125080026）"
USERNAME = "25984984262321238@openim"


def _history(*messages: str) -> dict:
    return {
        "chat": CONTACT,
        "username": USERNAME,
        "is_group": False,
        "count": len(messages),
        "messages": list(messages),
        "failures": None,
    }


def test_wechat_history_extracts_only_xiaocao_live_links():
    payload = _history(
        "[2026-08-03 21:17] 福利官小花四: 2026/08/03文字复盘总结：https://example.com/not-live",
        "[2026-08-04 08:29] 福利官小花四: 9点20草神直播地址（密码666）：https://yv9lc.xetslk.com/sl/4EKPYp",
        "[2026-08-04 17:02] 福利官小花四: 草神重磅直播：https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/alive/l_6a708838e4b0694c5bf42e55?share_user_id=private",
    )

    items = parse_xiaocao_live_messages(payload)

    assert [item["published_at"] for item in items] == [
        "2026-08-04T08:29:00+08:00",
        "2026-08-04T17:02:00+08:00",
    ]
    assert [item["source_url"] for item in items] == [
        "https://yv9lc.xetslk.com/sl/4EKPYp",
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/alive/l_6a708838e4b0694c5bf42e55",
    ]
    assert all(item["contact_username"] == USERNAME for item in items)
    assert all("message" not in item for item in items)


def test_wechat_history_accepts_xiaoetong_link_without_message_keywords():
    payload = _history(
        "[2026-08-06 16:48] 福利官小花四: 今晚见："
        "https://yv9lc.xetslk.com/sl/3qV2x"
    )

    items = parse_xiaocao_live_messages(payload)

    assert len(items) == 1
    assert items[0]["published_at"] == "2026-08-06T16:48:00+08:00"
    assert items[0]["source_url"] == "https://yv9lc.xetslk.com/sl/3qV2x"


def test_wechat_history_accepts_h5_xeknow_short_live_links():
    payload = _history(
        "[2026-08-14 16:53] 福利官小花四: 17:30草神重磅直播："
        "https://9ozbz.h5.xeknow.com/sl/2AjX90"
    )

    items = parse_xiaocao_live_messages(payload)

    assert len(items) == 1
    assert items[0]["published_at"] == "2026-08-14T16:53:00+08:00"
    assert items[0]["source_url"] == "https://9ozbz.h5.xeknow.com/sl/2AjX90"


def test_wechat_history_accepts_native_goose_live_mini_program_entries():
    payload = _history(
        "[2026-09-04 08:37] 福利官小花四: 9点20草神直播地址（密码666）："
        "#小程序://鹅直播/WDUa9A1nxlXZoSz"
    )

    items = parse_xiaocao_live_messages(payload)

    assert len(items) == 1
    assert items[0]["published_at"] == "2026-09-04T08:37:00+08:00"
    assert items[0]["entry_kind"] == "wechat_mini_program"
    assert items[0]["mini_program_name"] == "鹅直播"
    assert items[0]["mini_program_token"] == "WDUa9A1nxlXZoSz"
    assert "source_url" not in items[0]
    assert "message" not in items[0]


class _CaptureDriver:
    def __init__(self):
        self.arms: list[tuple[str, str | None, str | None]] = []
        self.advances = 0
        self.capture_checks = 0
        self.native_bindings = []
        self.playback_preparations = []
        self.media_urls: list[str | None] = []
        self.needs_media_url = False
        self.capture_check_result = {
            "event": "capture_pending",
            "status": "awaiting_capture",
            "capture_job_id": "kol-capture-current",
            "source_job_status": "awaiting_playback",
        }
        self.next_result = {
            "event": "xiaocao_live_pending",
            "status": "downloading",
            "capture_job_id": "kol-capture-current",
            "next": "rerun",
        }

    def arm(
        self,
        identity: str,
        page_url: str | None,
        *,
        media_file_id: str | None = None,
    ) -> dict:
        self.arms.append((identity, page_url, media_file_id))
        return {"capture_job_id": "kol-capture-current"}

    def bind_mini_program_capture(self, identity, capture_job_id, **binding):
        self.native_bindings.append((identity, capture_job_id, binding))
        return {"status": "captured"}

    def prepare_playback(self, identity, capture_job_id):
        self.playback_preparations.append((identity, capture_job_id))
        return {"capture_job_id": capture_job_id, "status": "awaiting_capture"}

    def advance(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None,
        recorded_media_url: str | None = None,
    ) -> dict:
        self.media_urls.append(recorded_media_url)
        assert identity
        assert capture_job_id == "kol-capture-current"
        assert opencli_session == "xiaocao-lv-subscription"
        assert opencli_profile is None
        self.advances += 1
        return dict(self.next_result)

    def advance_capture(
        self,
        identity: str,
        capture_job_id: str,
        *,
        recorded_media_url: str | None = None,
    ) -> dict:
        del recorded_media_url
        assert identity
        assert capture_job_id == "kol-capture-current"
        self.capture_checks += 1
        return dict(self.capture_check_result)

    def needs_recorded_media_url(
        self,
        identity: str,
        capture_job_id: str,
    ) -> bool:
        assert identity
        assert capture_job_id == "kol-capture-current"
        return self.needs_media_url

    def published_handoff(
        self,
        identity: str,
        capture_job_id: str,
    ) -> dict | None:
        del identity, capture_job_id
        return None


def test_cloud_handoff_wait_has_durable_poll_deadline(tmp_path):
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: {},
        browser_exchange=lambda request: request,
        capture_driver=_CaptureDriver(),
        clock=lambda: datetime.fromisoformat("2026-08-10T15:03:00+08:00"),
    )

    result = subscription._waiting(
        {
            "identity": "kol-wechat-current",
            "published_at": "2026-08-10T08:45:00+08:00",
            "capture_job_id": "kol-capture-current",
            "status": "playback_activated",
        },
        {
            "event": "xiaocao_live_upload_pending",
            "status": "upload_claimed",
        },
    )

    assert result["waiting_items"][0]["next_poll_not_before"] == (
        "2026-08-10T15:03:30+08:00"
    )
    progress = normalize_source_result(
        "xiaocao_wechat_live",
        result,
        failure_revision="a" * 40,
        provider_contract_version="xiaocao_writer_v1",
    )
    assert progress.status == "wait_until"
    assert progress.next_action == "resume_after_deadline"


def test_compressed_capture_wait_has_durable_poll_deadline(tmp_path):
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: {},
        browser_exchange=lambda request: request,
        capture_driver=_CaptureDriver(),
        clock=lambda: datetime.fromisoformat("2026-08-10T16:03:00+08:00"),
    )

    result = subscription._waiting(
        {
            "identity": "kol-wechat-current",
            "published_at": "2026-08-09T16:42:00+08:00",
            "capture_job_id": "kol-capture-current",
            "status": "playback_activated",
        },
        {
            "event": "xiaocao_live_pending",
            "status": "downloading",
        },
    )

    assert result["waiting_items"][0]["next_poll_not_before"] == (
        "2026-08-10T16:03:30+08:00"
    )
    progress = normalize_source_result(
        "xiaocao_wechat_live",
        result,
        failure_revision="a" * 40,
        provider_contract_version="xiaocao_writer_v1",
    )
    assert progress.status == "wait_until"
    assert progress.next_action == "resume_after_deadline"


@pytest.mark.parametrize(
    ("observed_at", "expected_deadline"),
    [
        (
            "2026-08-10T18:06:00+08:00",
            "2026-08-10T18:20:00+08:00",
        ),
        (
            "2026-08-10T23:06:00+08:00",
            "2026-08-11T07:00:00+08:00",
        ),
        (
            "2026-08-11T06:03:00+08:00",
            "2026-08-11T07:00:00+08:00",
        ),
    ],
)
def test_awaiting_playback_compressed_capture_wait_has_durable_poll_deadline(
    tmp_path,
    observed_at,
    expected_deadline,
):
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: {},
        browser_exchange=lambda request: request,
        capture_driver=_CaptureDriver(),
        clock=lambda: datetime.fromisoformat(observed_at),
    )

    result = subscription._waiting(
        {
            "identity": "kol-wechat-current",
            "published_at": "2026-08-10T17:06:00+08:00",
            "capture_job_id": "kol-capture-current",
            "status": "awaiting_playback",
        },
        {"status": "awaiting_playback"},
    )

    assert result["waiting_items"][0]["next_poll_not_before"] == (
        expected_deadline
    )
    progress = normalize_source_result(
        "xiaocao_wechat_live",
        result,
        failure_revision="a" * 40,
        provider_contract_version="xiaocao_writer_v1",
    )
    assert progress.status == "wait_until"
    assert progress.next_action == "resume_after_deadline"


def test_live_capture_driver_reconciles_sniffer_before_pending_advance(tmp_path):
    calls: list[object] = []

    class FakeCaptureStore:
        @staticmethod
        def latest(capture_job_id):
            assert capture_job_id == "kol-capture-current"
            return {"status": "awaiting_capture"}

    class FakeService:
        capture_store = FakeCaptureStore()

        def events(self):
            return []

        def start(self):
            calls.append("start")
            return {"capture_job_id": "kol-capture-current"}

        def advance(
            self,
            capture_job_id,
            *,
            opencli_session,
            opencli_profile,
            recorded_media_url=None,
        ):
            del recorded_media_url
            calls.append((capture_job_id, opencli_session, opencli_profile))
            return {"event": "capture_pending", "status": "awaiting_capture"}

    driver = XiaocaoLiveCaptureDriver(
        tmp_path / "wechat",
        decision_output=tmp_path / "decisions",
        netdisk_output=tmp_path / "netdisk",
        service_factory=lambda *args, **kwargs: FakeService(),
    )

    result = driver.advance(
        "kol-wechat-current",
        "kol-capture-current",
        opencli_session="xiaocao-lv-subscription",
        opencli_profile=None,
    )

    assert result["status"] == "awaiting_capture"
    assert calls == [
        "start",
        ("kol-capture-current", "xiaocao-lv-subscription", None),
    ]


def test_live_capture_driver_does_not_restart_sniffer_after_download(tmp_path):
    calls: list[object] = []

    class FakeCaptureStore:
        @staticmethod
        def latest(capture_job_id):
            assert capture_job_id == "kol-capture-current"
            return {"status": "downloaded"}

    class FakeService:
        capture_store = FakeCaptureStore()

        def events(self):
            return []

        def start(self):
            calls.append("start")

        def advance(
            self,
            capture_job_id,
            *,
            opencli_session,
            opencli_profile,
            recorded_media_url=None,
        ):
            del recorded_media_url
            calls.append((capture_job_id, opencli_session, opencli_profile))
            return {"event": "xiaocao_live_upload_pending", "status": "prepared"}

    driver = XiaocaoLiveCaptureDriver(
        tmp_path / "wechat",
        decision_output=tmp_path / "decisions",
        netdisk_output=tmp_path / "netdisk",
        service_factory=lambda *args, **kwargs: FakeService(),
    )

    result = driver.advance(
        "kol-wechat-current",
        "kol-capture-current",
        opencli_session="xiaocao-lv-subscription",
        opencli_profile=None,
    )

    assert result["status"] == "prepared"
    assert calls == [
        ("kol-capture-current", "xiaocao-lv-subscription", None),
    ]


def test_first_poll_baselines_history_and_arms_only_latest_live(tmp_path):
    payload = _history(
        "[2026-08-03 17:00] 福利官小花四: 草神直播：https://yv9lc.xetslk.com/sl/old001",
        "[2026-08-04 08:29] 福利官小花四: 9点20草神直播地址（密码666）：https://yv9lc.xetslk.com/sl/4EKPYp",
    )
    browser_requests: list[dict] = []

    def browser_exchange(request: dict) -> dict:
        browser_requests.append(request)
        if request["action"] == "resolve_xiaoetong_page":
            params = urlsafe_b64encode(json.dumps({
                "apparid": "appsnm3rlcp3566",
                "resource_id": "l_6a708838e4b0694c5bf42e55",
                "h5_url": (
                    "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/"
                    "alive/l_6a708838e4b0694c5bf42e55?share_user_id=private"
                ),
            }).encode()).decode().rstrip("=")
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": (
                    "https://appsnm3rlcp3566.mp.xiaoeknow.com/"
                    f"?app_id=appsnm3rlcp3566&params={params}"
                ),
                "page_state": "password_required",
            }
        assert request["action"] == "activate_xiaoetong_playback"
        assert request["password_policy"] == {
            "only_if_password_gate_visible": True,
            "password": "666",
        }
        assert "page-level control" in request["instructions"]
        assert "video.muted=true" in request["instructions"]
        assert "video.volume=0" in request["instructions"]
        assert "Runtime.evaluate" in request["instructions"]
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": request["page_url"],
            "activated": True,
            "password_used": True,
        }

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )

    assert result["status"] == "waiting"
    assert result["waiting_count"] == 1
    assert result["waiting_items"][0]["stage"] == "compressed_capture"
    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_playback",
    ]
    assert capture.arms == [(
        result["waiting_items"][0]["identity"],
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/alive/"
        "l_6a708838e4b0694c5bf42e55",
        None,
    )]
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    statuses = sorted(item["status"] for item in manifest["items"].values())
    assert statuses == ["historical_baseline", "playback_activated"]


@pytest.mark.parametrize("returned_id", ["same-capture", "different-capture"])
def test_native_playback_restores_only_the_existing_capture(tmp_path, returned_id):
    starts = []
    def start():
        starts.append(True)
        return {"capture_job_id": returned_id, "status": "awaiting_capture"}
    service = SimpleNamespace(
        capture_store=SimpleNamespace(latest=lambda job_id: {"status": "awaiting_capture"}),
        start=start,
    )
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    if returned_id == "different-capture":
        with pytest.raises(EnrichmentError, match="different capture"):
            driver.prepare_playback("source", "same-capture")
    else:
        assert driver.prepare_playback("source", "same-capture")["capture_job_id"] == returned_id
    assert starts == [True]


def test_wechat_mini_program_route_binds_media_to_the_exact_live_id(tmp_path):
    page_url = (
        "https://app6ums63as6516.h5.xiaoeknow.com/v2/course/alive/"
        "l_6a9531fbe4b0694c35440d7e"
    )
    payload = _history(
        "[2026-08-31 16:54] 福利官小花四: 盘前大师班：" + page_url,
    )
    requests: list[dict] = []
    capture = _CaptureDriver()

    def browser_exchange(request: dict) -> dict:
        requests.append(request)
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "page_state": "unknown",
            }
        assert request["action"] == "activate_xiaoetong_mini_program"
        assert capture.playback_preparations == [(request["subscription_id"], "kol-capture-current")]
        assert request["playback_surface"] == (
            XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM
        )
        assert request["operator"] == "agent"
        assert request["user_action_required"] is False
        assert request["ui_policy"] == {
            "app_bundle_id": "com.tencent.xinWeChat",
            "surface": "visible_foreground_ui",
            "action_mode": "one_action_then_state_readback",
            "max_activation_attempts": 1,
        }
        assert "浏览器 H5" in request["instructions"]
        assert request["launch_resolver_command"] == [
            ".venv/bin/python", "scripts/kol_xiaoetong_launch.py",
            "--source-url", request["source_url"],
            "--expected-identity", "xiaoetong:app6ums63as6516:l_6a9531fbe4b0694c35440d7e",
        ]
        assert "不重开" in request["instructions"]
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:app6ums63as6516:l_6a9531fbe4b0694c35440d7e"
            ),
            "live_id": "l_6a9531fbe4b0694c35440d7e",
            "page_state": "mini_program_media_observed",
            "activated": True,
            "media_request_observed": True,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        playback_route=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )

    assert result["status"] == "waiting"
    assert capture.advances == 1
    assert [request["action"] for request in requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_mini_program",
    ]
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["status"] == "playback_activated"
    assert item["playback_route"] == (
        XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM
    )
    assert item["playback_surface"] == (
        XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM
    )
    assert item["media_request_observed"] is True


def test_native_mini_program_entry_is_armed_before_ui_and_binds_observed_live(
    tmp_path,
):
    payload = _history(
        "[2026-09-04 08:37] 福利官小花四: 9点20草神直播地址（密码666）："
        "#小程序://鹅直播/WDUa9A1nxlXZoSz"
    )
    requests: list[dict] = []
    capture = _CaptureDriver()

    def browser_exchange(request: dict) -> dict:
        requests.append(request)
        assert request["action"] == "activate_xiaoetong_mini_program"
        assert request["mini_program_name"] == "鹅直播"
        assert request["mini_program_token"] == "WDUa9A1nxlXZoSz"
        assert "source_url" not in request
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:app6ums63as6516:l_6a99d00de4b0694c3546aaaa"
            ),
            "live_id": "l_6a99d00de4b0694c3546aaaa",
            "candidate_id": "candidate-new-live",
            "page_state": "mini_program_media_observed",
            "activated": True,
            "media_request_observed": True,
            "password_used": True,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
        playback_route=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )

    assert result["status"] == "waiting"
    assert capture.arms == [(
        result["waiting_items"][0]["identity"],
        None,
        None,
    )]
    assert capture.advances == 1
    assert [request["action"] for request in requests] == [
        "activate_xiaoetong_mini_program",
    ]
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["status"] == "playback_activated"
    assert item["source_identity"] == (
        "xiaoetong:app6ums63as6516:l_6a99d00de4b0694c3546aaaa"
    )
    assert item["candidate_id"] == "candidate-new-live"
    assert capture.native_bindings == [(
        item["identity"], "kol-capture-current", {
            "source_identity": item["source_identity"],
            "candidate_id": "candidate-new-live",
        },
    )]


@pytest.mark.parametrize("invalid", [None, "other_app", "stale", "live_stream"])
def test_native_candidate_binding_checks_real_sniffer_evidence(tmp_path, invalid):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    armed = store.arm([])
    armed = store.transition(armed, "test_clock", created_at="2026-09-05T15:00:00+08:00")
    candidate = {
        "id": "new-candidate",
        "live_id": "l_target",
        "captured": "2026-09-05 15:01:00",
        "media_type": "m3u8",
        "source_url": "https://appdemo.h5.xe-live.com/_alive/v3/get_lookback_list",
        "url": "https://vod.xet.tech/replay/playlist_eof.m3u8?secret=private",
    }
    if invalid == "other_app":
        candidate["source_url"] = "https://appother.h5.xe-live.com/api"
    elif invalid == "stale":
        candidate["captured"] = "2026-09-05 14:59:00"
    elif invalid == "live_stream":
        candidate["url"] = "https://vod.xet.tech/liveplay.m3u8"
    service = SimpleNamespace(
        capture_store=store,
        sniffer=SimpleNamespace(candidates=lambda: [candidate]),
    )
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    kwargs = dict(source_identity="xiaoetong:appdemo:l_target", candidate_id="new-candidate")
    if invalid:
        with pytest.raises(EnrichmentError):
            driver.bind_mini_program_capture("item", armed["job_id"], **kwargs)
        assert store.latest()["status"] == "awaiting_capture"
    else:
        result = driver.bind_mini_program_capture("item", armed["job_id"], **kwargs)
        assert result["status"] == "captured"
        assert result["expected_source"]["source_identity"] == kwargs["source_identity"]
        assert driver.bind_mini_program_capture("item", armed["job_id"], **kwargs) == result
        assert "private" not in store.path.read_text()


def test_wechat_mini_program_route_rejects_a_different_live_id(tmp_path):
    page_url = (
        "https://app6ums63as6516.h5.xiaoeknow.com/v2/course/alive/"
        "l_6a9531fbe4b0694c35440d7e"
    )
    payload = _history(
        "[2026-08-31 16:54] 福利官小花四: 盘前大师班：" + page_url,
    )
    capture = _CaptureDriver()

    def browser_exchange(request: dict) -> dict:
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "page_state": "unknown",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:app6ums63as6516:l_6a9531fbe4b0694c35440d7e"
            ),
            "live_id": "l_wrong_resource",
            "page_state": "mini_program_media_observed",
            "activated": True,
            "media_request_observed": True,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        playback_route=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
    )

    with pytest.raises(
        EnrichmentError,
        match="WeChat mini-program playback binding is invalid",
    ):
        subscription.run_once(opencli_session="xiaocao-lv-subscription")
    assert capture.advances == 0


def test_recorded_video_page_arms_bound_capture(tmp_path):
    payload = _history(
        "[2026-08-13 21:46] 福利官小花四: 8月13日大师班复盘直播："
        "https://yv9lc.xetslk.com/s/5ftVx"
    )
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/"
        "v_6a7db774e4b0694c5bfa7583"
    )

    def browser_exchange(request: dict) -> dict:
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url + "?share_user_id=private",
                "page_state": "playable",
                "media_file_id": "5001834815942190711",
            }
        if request["action"] == "resolve_xiaoetong_media_url":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "media_file_id": "5001834815942190711",
                "media_url": (
                    "https://encrypt-k-vod.xet.tech/vod/"
                    "773e679a5001834815942190711/drm/v.f421220.m3u8"
                    "?sign=fresh&t=expires&us=user"
                ),
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": page_url,
            "page_state": "playable",
            "activated": True,
            "password_used": False,
        }

    capture = _CaptureDriver()
    capture.needs_media_url = True
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )

    assert result["status"] == "waiting"
    assert capture.arms == [(
        result["waiting_items"][0]["identity"],
        page_url,
        "5001834815942190711",
    )]
    assert capture.media_urls == [
        "https://encrypt-k-vod.xet.tech/vod/"
        "773e679a5001834815942190711/drm/v.f421220.m3u8"
        "?sign=fresh&t=expires&us=user"
    ]
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["page_url"] == page_url
    assert item["source_identity"] == (
        "xiaoetong:appsnm3rlcp3566:v_6a7db774e4b0694c5bfa7583"
    )
    assert item["media_file_id"] == "5001834815942190711"


def test_existing_recorded_video_page_resolves_media_file_before_arming(tmp_path):
    output = tmp_path / "wechat"
    output.mkdir(parents=True)
    identity = "kol-wechat-recorded"
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/video/"
        "v_6a7db774e4b0694c5bfa7583"
    )
    (output / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "items": {
                identity: {
                    "identity": identity,
                    "contact": CONTACT,
                    "contact_username": USERNAME,
                    "published_at": "2026-08-13T21:46:00+08:00",
                    "source_url": "https://yv9lc.xetslk.com/s/5ftVx",
                    "page_url": page_url,
                    "source_identity": (
                        "xiaoetong:appsnm3rlcp3566:"
                        "v_6a7db774e4b0694c5bfa7583"
                    ),
                    "observed_page_state": "playable",
                    "status": "page_resolved",
                }
            },
        }),
        encoding="utf-8",
    )
    requests = []

    def browser_exchange(request: dict) -> dict:
        requests.append(request)
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": page_url,
            "page_state": "playable",
            "media_file_id": "5001834815942190711",
            "activated": request["action"] == "activate_xiaoetong_playback",
            "password_used": False,
        }

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        output,
        history_reader=lambda: pytest.fail("narrow resume must not rescan WeChat"),
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
        only_identity=identity,
    )

    assert result["status"] == "waiting"
    assert [request["action"] for request in requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_playback",
    ]
    assert capture.arms == [(identity, page_url, "5001834815942190711")]


def test_newer_preview_is_not_starved_by_an_older_unfinished_capture(tmp_path):
    old_message = (
        "[2026-08-04 16:44] 福利官小花四: 草神直播："
        "https://yv9lc.xetslk.com/sl/old001"
    )
    missed_morning_message = (
        "[2026-08-05 08:32] 福利官小花四: 小草直播："
        "https://yv9lc.xetslk.com/sl/morning001"
    )
    new_message = (
        "[2026-08-05 16:57] 福利官小花四: 小草直播预告："
        "https://yv9lc.xetslk.com/sl/new002"
    )
    payload = [_history(old_message)]
    browser_requests: list[dict] = []

    def browser_exchange(request: dict) -> dict:
        browser_requests.append(request)
        if request["action"] == "resolve_xiaoetong_page":
            resource_id = (
                "l_new_preview"
                if request["source_url"].endswith("/new002")
                else "l_old_preview"
            )
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": (
                    "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
                    f"alive/{resource_id}"
                ),
                "page_state": "playable",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": request["page_url"],
            "page_state": "playable",
            "activated": True,
            "password_used": False,
        }

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload[0],
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
    )

    subscription.run_once(opencli_session="xiaocao-lv-subscription")
    payload[0] = _history(old_message, missed_morning_message, new_message)
    subscription.run_once(opencli_session="xiaocao-lv-subscription")

    parsed = parse_xiaocao_live_messages(payload[0])
    morning_identity = parsed[-2]["identity"]
    new_identity = parsed[-1]["identity"]
    assert capture.arms[-1][0] == new_identity
    assert any(
        request.get("subscription_id") == new_identity
        and request["action"] == "resolve_xiaoetong_page"
        for request in browser_requests
    )
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["items"][morning_identity]["status"] == "superseded"
    assert manifest["items"][morning_identity]["superseded_by"] == new_identity


def test_newest_inflight_capture_precedes_an_older_ready_handoff():
    manifest = {
        "items": {
            "older-handoff": {
                "identity": "older-handoff",
                "published_at": "2026-08-05T08:30:00+08:00",
                "status": "handoff_ready",
            },
            "current-live": {
                "identity": "current-live",
                "published_at": "2026-08-06T08:30:00+08:00",
                "status": "playback_activated",
            },
        },
    }

    selected = XiaocaoWechatLiveSubscription._next_pending(manifest)

    assert selected is not None
    assert selected["identity"] == "current-live"


def test_existing_source_task_is_reconciled_before_another_wechat_ui_attempt(
    tmp_path,
):
    identity = "kol-wechat-current"
    output_dir = tmp_path / "wechat"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "initialized_at": "2026-09-05T14:00:00+08:00",
            "updated_at": "2026-09-05T14:00:00+08:00",
            "items": {
                identity: {
                    "identity": identity,
                    "contact": CONTACT,
                    "contact_username": USERNAME,
                    "published_at": "2026-09-03T08:30:00+08:00",
                    "source_url": "https://9znl4.xet.tech/s/23pHhw",
                    "page_url": (
                        "https://app6ums63as6516.h5.xiaoeknow.com/v3/"
                        "course/alive/l_target"
                    ),
                    "source_identity": "xiaoetong:app6ums63as6516:l_target",
                    "capture_job_id": "kol-capture-current",
                    "status": "awaiting_playback",
                    "observed_page_state": "unknown",
                    "updated_at": "2026-09-05T14:00:00+08:00",
                }
            },
        }),
        encoding="utf-8",
    )
    capture = _CaptureDriver()
    capture.capture_check_result = {
        "event": "download_completed",
        "status": "downloaded",
        "capture_job_id": "kol-capture-current",
        "source_job_status": "task_created",
    }
    capture.next_result = {
        "event": "xiaocao_live_pending",
        "status": "prepared",
        "capture_job_id": "kol-capture-current",
        "next": "rerun_broadband",
    }

    def reject_browser(_request: dict) -> dict:
        raise AssertionError("a completed source task must bypass WeChat UI")

    subscription = XiaocaoWechatLiveSubscription(
        output_dir,
        history_reader=lambda: {},
        browser_exchange=reject_browser,
        capture_driver=capture,
        contact=CONTACT,
        playback_route=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
        only_identity=identity,
    )

    assert result["status"] == "waiting"
    assert result["waiting_items"][0]["stage"] == "compressed_capture"
    assert capture.capture_checks == 1
    assert capture.advances == 1


def test_awaiting_playback_rechecks_the_bound_page_each_hour_until_playable(
    tmp_path,
):
    payload = _history(
        "[2026-08-05 08:32] 福利官小花四: 草神直播："
        "https://yv9lc.xetslk.com/sl/4EKPYp",
    )
    browser_requests: list[dict] = []
    activation_states = iter([
        ("waiting_to_start", False),
        ("replay_generating", False),
        ("playable", True),
    ])
    capture = _CaptureDriver()
    capture.next_result = {
        "event": "xiaocao_live_pending",
        "status": "awaiting_capture",
        "capture_job_id": "kol-capture-current",
        "source_job_status": "awaiting_playback",
        "next": "rerun",
    }

    def browser_exchange(request: dict) -> dict:
        browser_requests.append(request)
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": (
                    "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
                    "alive/l_6a708838e4b0694c5bf42e55"
                ),
                "page_state": "waiting_to_start",
            }
        page_state, activated = next(activation_states)
        if activated:
            capture.next_result = {
                "event": "xiaocao_live_pending",
                "status": "downloading",
                "capture_job_id": "kol-capture-current",
                "next": "rerun",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": request["page_url"],
            "page_state": page_state,
            "activated": activated,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
    )

    first = subscription.run_once(opencli_session="xiaocao-lv-subscription")
    second = subscription.run_once(opencli_session="xiaocao-lv-subscription")
    third = subscription.run_once(opencli_session="xiaocao-lv-subscription")

    assert [first["status"], second["status"], third["status"]] == [
        "waiting",
        "waiting",
        "waiting",
    ]
    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_playback",
        "activate_xiaoetong_playback",
        "activate_xiaoetong_playback",
    ]
    assert [
        request.get("check_reason")
        for request in browser_requests
        if request["action"] == "activate_xiaoetong_playback"
    ] == ["initial", "awaiting_playback", "awaiting_playback"]
    assert capture.advances == 1
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["status"] == "playback_activated"
    assert item["observed_page_state"] == "playable"


def test_xiaoetong_account_login_redirect_is_reported_explicitly(tmp_path):
    payload = _history(
        "[2026-08-09 16:42] 福利官小花四: 草神直播："
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
        "alive/l_6a75cf66e4b0694c5bf6d228",
    )
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
        "alive/l_6a75cf66e4b0694c5bf6d228"
    )

    def browser_exchange(request: dict) -> dict:
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "page_state": "unknown",
            }
        assert "account_login_required" in request["required_response"][
            "page_state"
        ]
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": (
                "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/t/free/v1/"
                "basic-platform/h5_basic/login/auth?redirect_url="
                f"{quote(page_url, safe='')}"
            ),
            "page_state": "unknown",
            "activated": False,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=_CaptureDriver(),
        contact=CONTACT,
        password="666",
    )

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        subscription.run_once(opencli_session="xiaocao-lv-subscription")
    assert captured.value.diagnostic_category == "authentication_error"
    assert captured.value.diagnostic_code == "xiaoetong_account_login_required"
    assert captured.value.diagnostic_stage == "playback_authorization"


def test_wechat_mini_program_login_state_is_fail_closed(
    tmp_path,
):
    page_url = (
        "https://app6ums63as6516.h5.xiaoeknow.com/v4/course/alive/"
        "l_6a75cf66e4b0694c5bf6d228"
    )
    payload = _history(
        "[2026-08-09 16:42] 福利官小花四: 草神直播：" + page_url,
    )

    def browser_exchange(request: dict) -> dict:
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "page_state": "unknown",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:app6ums63as6516:l_6a75cf66e4b0694c5bf6d228"
            ),
            "live_id": "l_6a75cf66e4b0694c5bf6d228",
            "page_state": "account_login_required",
            "activated": True,
            "media_request_observed": True,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=_CaptureDriver(),
        contact=CONTACT,
        playback_route=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
    )

    with pytest.raises(
        EnrichmentDiagnosticError,
        match="Xiaoetong account login is required",
    ):
        subscription.run_once(opencli_session="xiaocao-lv-subscription")


def test_xiaoetong_mp_wrapper_login_state_stays_bound(tmp_path):
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
        "alive/l_6a75cf66e4b0694c5bf6d228"
    )
    params = urlsafe_b64encode(json.dumps({
        "apparid": "appsnm3rlcp3566",
        "resource_id": "l_6a75cf66e4b0694c5bf6d228",
        "h5_url": page_url,
    }).encode()).decode().rstrip("=")
    wrapper_url = (
        "https://appsnm3rlcp3566.mp.xiaoeknow.com/"
        f"?app_id=appsnm3rlcp3566&params={params}"
    )
    payload = _history(f"[2026-08-09 16:42] 福利官小花四: 草神直播：{page_url}")

    def browser_exchange(request: dict) -> dict:
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": wrapper_url,
            "page_state": "account_login_required",
            **(
                {"activated": False, "password_used": False}
                if request["action"] == "activate_xiaoetong_playback"
                else {}
            ),
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=_CaptureDriver(),
        contact=CONTACT,
        password="666",
    )

    with pytest.raises(EnrichmentError, match="account login is required"):
        subscription.run_once(opencli_session="xiaocao-lv-subscription")


def test_xiaoetong_login_redirect_allows_bound_resource_version_rotation():
    expected_page = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/alive/"
        "l_6a8dc972e4b0694c354119f2"
    )
    redirected_page = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v3/course/alive/"
        "l_6a8dc972e4b0694c354119f2"
    )
    login_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/t/free/v1/"
        "basic-platform/h5_basic/login/auth?redirect_url="
        f"{quote(redirected_page, safe='')}"
    )

    assert XiaocaoWechatLiveSubscription._is_bound_account_login_redirect(
        login_url,
        expected_page_url=expected_page,
        expected_source_identity=(
            "xiaoetong:appsnm3rlcp3566:l_6a8dc972e4b0694c354119f2"
        ),
    )


def test_xiaoetong_bound_provider_block_waits_for_the_same_page(tmp_path):
    payload = _history(
        "[2026-08-13 08:42] 福利官小花四: 草神直播："
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/"
        "alive/l_6a7c2ed8e4b023c0d633fabb",
    )
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/"
        "alive/l_6a7c2ed8e4b023c0d633fabb"
    )
    block_url = (
        "https://appsnm3rlcp3566.block.xiaoeeye.com/v4/course/"
        "alive/l_6a7c2ed8e4b023c0d633fabb"
    )

    def browser_exchange(request: dict) -> dict:
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "page_state": "unknown",
            }
        assert "source_temporarily_unavailable" in request[
            "required_response"
        ]["page_state"]
        assert "personal-center shell" in request["instructions"]
        assert "block.xiaoeeye.com" in request["instructions"]
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": block_url,
            "page_state": "source_temporarily_unavailable",
            "activated": False,
            "password_used": False,
        }

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
        clock=lambda: datetime.fromisoformat("2026-08-13T14:08:00+08:00"),
    )

    result = subscription.run_once(opencli_session="xiaocao-lv-subscription")

    assert result["status"] == "waiting"
    assert result["waiting_items"][0]["status"] == "awaiting_playback"
    assert result["waiting_items"][0]["next_poll_not_before"] == (
        "2026-08-13T14:20:00+08:00"
    )
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["page_url"] == page_url
    assert item["observed_page_state"] == "source_temporarily_unavailable"

    # A blocked provider page must be rechecked before touching the capture
    # job again; the source job may already have failed behind that page.
    second = subscription.run_once(opencli_session="xiaocao-lv-subscription")
    assert second["status"] == "waiting"
    assert second["waiting_items"][0]["status"] == "awaiting_playback"
    assert capture.advances == 0


def test_xiaoetong_playable_page_accepts_bound_version_rotation(tmp_path):
    payload = _history(
        "[2026-08-13 08:42] 福利官小花四: 草神直播："
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/"
        "alive/l_6a7c2ed8e4b023c0d633fabb",
    )
    original_page = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/"
        "alive/l_6a7c2ed8e4b023c0d633fabb"
    )
    rotated_page = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
        "alive/l_6a7c2ed8e4b023c0d633fabb"
    )

    def browser_exchange(request: dict) -> dict:
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": original_page,
                "page_state": "unknown",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": rotated_page,
            "page_state": "playable",
            "activated": True,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=_CaptureDriver(),
        contact=CONTACT,
        password="666",
    )

    subscription.run_once(opencli_session="xiaocao-lv-subscription")
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["page_url"] == rotated_page
    assert item["status"] == "playback_activated"


@pytest.mark.parametrize(
    "block_url",
    [
        (
            "https://anotherapp.block.xiaoeeye.com/v4/course/"
            "alive/l_6a7c2ed8e4b023c0d633fabb"
        ),
        (
            "https://appsnm3rlcp3566.block.xiaoeeye.com/v4/course/"
            "alive/l_another_resource"
        ),
    ],
)
def test_xiaoetong_unbound_provider_block_fails_closed(tmp_path, block_url):
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
        "alive/l_6a7c2ed8e4b023c0d633fabb"
    )
    payload = _history(
        "[2026-08-13 08:42] 福利官小花四: 草神直播：" + page_url,
    )

    def browser_exchange(request: dict) -> dict:
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "page_state": "unknown",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": block_url,
            "page_state": "source_temporarily_unavailable",
            "activated": False,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=_CaptureDriver(),
        contact=CONTACT,
        password="666",
    )

    with pytest.raises(
        EnrichmentError,
        match="browser provider block is not bound to the live page",
    ):
        subscription.run_once(opencli_session="xiaocao-lv-subscription")


def test_new_source_account_login_redirect_resolves_exact_page(tmp_path):
    payload = _history(
        "[2026-08-10 08:45] 福利官小花四: 草神直播："
        "https://yv9lc.xetslk.com/sl/TYpKp",
    )
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
        "alive/l_6a787961e4b0694c35385519"
    )
    login_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/t/free/v1/"
        "basic-platform/h5_basic/login/auth?redirect_url="
        f"{quote(page_url, safe='')}"
    )
    browser_requests: list[dict] = []

    def browser_exchange(request: dict) -> dict:
        browser_requests.append(request)
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": login_url,
            "page_state": "account_login_required",
            "activated": False,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=_CaptureDriver(),
        contact=CONTACT,
        password="666",
    )

    with pytest.raises(
        EnrichmentError,
        match="Xiaoetong account login is required",
    ):
        subscription.run_once(opencli_session="xiaocao-lv-subscription")

    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_playback",
    ]
    assert "account_login_required" in browser_requests[0][
        "required_response"
    ]["page_state"]
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["page_url"] == page_url
    assert item["source_identity"] == (
        "xiaoetong:appsnm3rlcp3566:l_6a787961e4b0694c35385519"
    )
    assert item["status"] == "capture_armed"
    assert item["capture_job_id"]


def test_account_login_state_is_authoritative_when_page_url_stays_bound(
    tmp_path,
):
    payload = _history(
        "[2026-08-10 08:45] 福利官小花四: 草神直播："
        "https://yv9lc.xetslk.com/sl/TYpKp",
    )
    page_url = (
        "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
        "alive/l_6a787961e4b0694c35385519"
    )
    activation_states = iter([
        "waiting_to_start",
        "account_login_required",
    ])
    browser_requests: list[dict] = []
    capture = _CaptureDriver()
    capture.next_result = {
        "event": "xiaocao_live_pending",
        "status": "awaiting_capture",
        "capture_job_id": "kol-capture-current",
        "source_job_status": "awaiting_playback",
        "next": "rerun",
    }

    def browser_exchange(request: dict) -> dict:
        browser_requests.append(request)
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": page_url,
                "page_state": "waiting_to_start",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "page_url": page_url,
            "page_state": next(activation_states),
            "activated": False,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
    )

    assert subscription.run_once(
        opencli_session="xiaocao-lv-subscription"
    )["status"] == "waiting"
    manifest_path = tmp_path / "wechat" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_identity = next(iter(manifest["items"]))
    manifest["items"]["newer-other-item"] = {
        **manifest["items"][target_identity],
        "identity": "newer-other-item",
        "published_at": "2026-08-10T09:45:00+08:00",
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    subscription.history_reader = lambda: pytest.fail(
        "exact resume must not rescan WeChat"
    )
    with pytest.raises(
        EnrichmentError,
        match="Xiaoetong account login is required",
    ):
        subscription.run_once(
            opencli_session="xiaocao-lv-subscription",
            only_identity=target_identity,
        )
    assert browser_requests[-1]["subscription_id"] == target_identity


def test_pending_cloud_handoff_resumes_exact_job_after_stale_playback_state(
    tmp_path,
):
    payload = _history(
        "[2026-08-04 08:29] 福利官小花四: 9点20草神直播地址：https://yv9lc.xetslk.com/sl/4EKPYp",
    )
    browser_requests: list[dict] = []

    def browser_exchange(request: dict) -> dict:
        browser_requests.append(request)
        if request["action"] == "resolve_xiaoetong_page":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": (
                    "https://appsnm3rlcp3566.h5.xiaoeknow.com/v4/course/"
                    "alive/l_6a708838e4b0694c5bf42e55"
                ),
                "page_state": "playable",
            }
        if request["action"] == "activate_xiaoetong_playback":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": request["page_url"],
                "activated": True,
                "password_used": False,
            }
        raise AssertionError("mailbox handoff must not use the Browser exchange")

    mailbox_published: list[dict] = []

    def handoff_exchange(capsule, *, object_kind, title):
        mailbox_published.append(capsule)
        assert object_kind == "video"
        assert title
        return {
            "status": "Handoff完成",
            "handoff_id": capsule["handoff_id"],
            "mailbox_outcome": "created",
            "content_sha256": "f" * 64,
        }

    history_reads = 0

    def read_history():
        nonlocal history_reads
        history_reads += 1
        return payload

    capture = _CaptureDriver()
    capture.next_result = {
        "event": "xiaocao_live_upload_pending",
        "status": "upload_claimed",
        "capture_job_id": "kol-capture-current",
        "next": "rerun_broadband",
    }
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=read_history,
        browser_exchange=browser_exchange,
        handoff_exchange=handoff_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
    )
    first = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )
    assert first["status"] == "waiting"
    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_playback",
    ]

    manifest_path = tmp_path / "wechat" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_identity = first["waiting_items"][0]["identity"]
    assert manifest["items"][target_identity]["status"] == "playback_activated"
    manifest["items"][target_identity]["status"] = "awaiting_playback"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    handoff_path = tmp_path / "handoff.json"
    capsule = {
        "schema_version": 2,
        "handoff_id": "b" * 64,
        "capture_job_id": "kol-capture-current",
        "media_basename": "target-compressed.mp4",
        "media_sha256": "a" * 64,
        "large_payload_local_bytes": 0,
    }
    capsule["handoff_sha256"] = hashlib.sha256(
        json.dumps(
            capsule,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    handoff_path.write_text(json.dumps(capsule), encoding="utf-8")
    capture.next_result = {
        "event": "cloud_handoff_published",
        "status": "handoff_published",
        "capture_job_id": "kol-capture-current",
        "handoff_path": str(handoff_path),
    }
    second = subscription.continue_cloud_handoff(
        target_identity,
        "kol-capture-current",
        opencli_session="xiaocao-lv-subscription",
    )

    assert second == {
        "status": "no_update",
        "handoff_dispatched": True,
        "identity": first["waiting_items"][0]["identity"],
        "capture_job_id": "kol-capture-current",
    }
    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_playback",
    ]
    assert [capsule["handoff_id"] for capsule in mailbox_published] == ["b" * 64]
    assert capture.advances == 2
    assert history_reads == 1
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["status"] == "completed"
    assert item["mailbox_readback_status"] == "created"


def test_published_handoff_recovery_is_read_only_until_remote_dispatch(tmp_path):
    payload = _history(
        "[2026-08-06 16:48] 福利官小花四: 今晚见："
        "https://yv9lc.xetslk.com/sl/3qV2x"
    )
    parsed = parse_xiaocao_live_messages(payload)[0]
    handoff_path = tmp_path / "handoff.json"
    capsule = {
        "schema_version": 2,
        "handoff_id": "b" * 64,
        "capture_job_id": "kol-capture-current",
        "media_basename": "target-compressed.mp4",
        "media_sha256": "a" * 64,
        "large_payload_local_bytes": 0,
    }
    capsule["handoff_sha256"] = hashlib.sha256(
        json.dumps(
            capsule,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    handoff_path.write_text(json.dumps(capsule), encoding="utf-8")
    output_dir = tmp_path / "wechat"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "items": {
                parsed["identity"]: {
                    **parsed,
                    "status": "playback_activated",
                    "capture_job_id": "kol-capture-current",
                }
            },
        }),
        encoding="utf-8",
    )

    class RecoveryCapture(_CaptureDriver):
        def published_handoff(self, identity, capture_job_id):
            assert identity == parsed["identity"]
            assert capture_job_id == "kol-capture-current"
            return {
                "event": "cloud_handoff_published",
                "status": "handoff_published",
                "capture_job_id": capture_job_id,
                "handoff_path": str(handoff_path),
            }

        def advance(self, *args, **kwargs):
            raise AssertionError("recovery must not advance or replay capture")

    def exchange(capsule_value, *, object_kind, title):
        assert capsule_value == capsule
        assert object_kind == "video"
        assert title == "target-compressed"
        return {
            "status": "Handoff完成",
            "handoff_id": capsule["handoff_id"],
            "mailbox_outcome": "already_present",
            "content_sha256": "f" * 64,
        }

    subscription = XiaocaoWechatLiveSubscription(
        output_dir,
        history_reader=lambda: (_ for _ in ()).throw(
            AssertionError("recovery must not rescan WeChat")
        ),
        browser_exchange=lambda request: {},
        handoff_exchange=exchange,
        capture_driver=RecoveryCapture(),
        contact=CONTACT,
    )

    result = subscription.dispatch_published_handoff()

    assert result == {
        "status": "no_update",
        "handoff_dispatched": True,
        "identity": parsed["identity"],
        "capture_job_id": "kol-capture-current",
    }
    manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    item = manifest["items"][parsed["identity"]]
    assert item["status"] == "completed"
    assert item["mailbox_readback_status"] == "already_present"
