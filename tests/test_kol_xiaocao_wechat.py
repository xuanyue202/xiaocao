from __future__ import annotations

import json
import hashlib
from base64 import urlsafe_b64encode

from xiaocao.kol.xiaocao_wechat import (
    XiaocaoLiveCaptureDriver,
    XiaocaoWechatLiveSubscription,
    parse_xiaocao_live_messages,
)


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


class _CaptureDriver:
    def __init__(self):
        self.arms: list[tuple[str, str]] = []
        self.advances = 0
        self.next_result = {
            "event": "xiaocao_live_pending",
            "status": "downloading",
            "capture_job_id": "kol-capture-current",
            "next": "rerun",
        }

    def arm(self, identity: str, page_url: str) -> dict:
        self.arms.append((identity, page_url))
        return {"capture_job_id": "kol-capture-current"}

    def advance(
        self,
        identity: str,
        capture_job_id: str,
        *,
        opencli_session: str,
        opencli_profile: str | None,
    ) -> dict:
        assert identity
        assert capture_job_id == "kol-capture-current"
        assert opencli_session == "xiaocao-lv-subscription"
        assert opencli_profile is None
        self.advances += 1
        return dict(self.next_result)


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

        def advance(self, capture_job_id, *, opencli_session, opencli_profile):
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

        def advance(self, capture_job_id, *, opencli_session, opencli_profile):
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
    )]
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    statuses = sorted(item["status"] for item in manifest["items"].values())
    assert statuses == ["historical_baseline", "playback_activated"]


def test_pending_capture_resumes_without_reopening_browser(tmp_path):
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
        assert request["action"] == "dispatch_xiaocao_handoff"
        assert request["handoff_id"] == "b" * 64
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "handoff_id": request["handoff_id"],
            "accepted": True,
            "readback_status": "accepted",
            "remote_thread_id": "remote-xiaocao-executor",
            "remote_host_id": "remote-control:registered",
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
    first = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )
    assert first["status"] == "waiting"
    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_playback",
    ]

    handoff_path = tmp_path / "handoff.json"
    capsule = {
        "schema_version": 2,
        "handoff_id": "b" * 64,
        "capture_job_id": "kol-capture-current",
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
    second = subscription.run_once(
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
        "dispatch_xiaocao_handoff",
    ]
    assert capture.advances == 2
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["status"] == "completed"
    assert item["remote_thread_id"] == "remote-xiaocao-executor"
