from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

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


def test_manifest_stale_writer_preserves_other_item_download(tmp_path):
    def sub():
        return XiaocaoWechatLiveSubscription(tmp_path, history_reader=lambda: {},
            browser_exchange=lambda request: pytest.fail("no native input"),
            capture_driver=_CaptureDriver())
    first, second = sub(), sub()
    initial = first._load()
    initial["items"] = {"morning": {"identity": "morning", "status": "capture_armed"},
                        "evening": {"identity": "evening", "status": "awaiting_playback"}}
    first._save(initial)
    a, b = first._load(), second._load()
    first._transition(a, a["items"]["morning"], "playback_activated",
        capture_job_id="original", candidate_id="same", playback_window_closed=True)
    second._transition(b, b["items"]["evening"], "awaiting_playback", checked=True)
    saved = second._load()
    assert saved["items"]["morning"] == a["items"]["morning"]
    assert saved["items"]["evening"]["checked"] is True


def test_manifest_same_item_concurrent_change_fails_closed(tmp_path):
    def sub():
        return XiaocaoWechatLiveSubscription(tmp_path, history_reader=lambda: {},
            browser_exchange=lambda request: request, capture_driver=_CaptureDriver())
    first, second = sub(), sub()
    initial = first._load()
    initial["items"]["same"] = {"identity": "same", "status": "capture_armed"}
    first._save(initial)
    a, b = first._load(), second._load()
    first._transition(a, a["items"]["same"], "playback_activated", candidate_id="original")
    with pytest.raises(EnrichmentError, match="changed during continuation"):
        second._transition(b, b["items"]["same"], "playback_activated", candidate_id="other")
    assert second._load()["items"]["same"]["candidate_id"] == "original"


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


def test_wechat_history_discovers_merchant_entry_exactly_once():
    message = "[2026-09-11 16:38] 福利官小花四: https://wxmpurl.cn/OOgqnECl26c"
    items = parse_xiaocao_live_messages(_history(message, message))
    assert len(items) == 1
    assert items[0]["source_url"] == "https://wxmpurl.cn/OOgqnECl26c"
    assert items[0]["published_at"] == "2026-09-11T16:38:00+08:00"


@pytest.mark.parametrize("url", [
    "http://wxmpurl.cn/a", "https://wxmpurl.cn.evil.test/a",
    "https://u:p@wxmpurl.cn/a", "https://wxmpurl.cn/a/b",
    "https://wxmpurl.cn/a?extra=1",
])
def test_wechat_history_rejects_ambiguous_merchant_entries(url):
    assert parse_xiaocao_live_messages(_history(
        "[2026-09-11 16:38] 福利官小花四: " + url,
    )) == []


def test_wechat_history_accepts_h5_xeknow_short_live_links():
    payload = _history(
        "[2026-08-14 16:53] 福利官小花四: 17:30草神重磅直播："
        "https://9ozbz.h5.xeknow.com/sl/2AjX90"
    )

    items = parse_xiaocao_live_messages(payload)

    assert len(items) == 1
    assert items[0]["published_at"] == "2026-08-14T16:53:00+08:00"
    assert items[0]["source_url"] == "https://9ozbz.h5.xeknow.com/sl/2AjX90"


@pytest.mark.parametrize("app_name", ["鹅直播", "见势擒龙团"])
def test_wechat_history_accepts_supported_native_mini_program_entries(app_name):
    payload = _history(
        "[2026-09-04 08:37] 福利官小花四: 9点20草神直播地址（密码666）："
        f"#小程序://{app_name}/WDUa9A1nxlXZoSz"
    )

    items = parse_xiaocao_live_messages(payload)

    assert len(items) == 1
    assert items[0]["published_at"] == "2026-09-04T08:37:00+08:00"
    assert items[0]["entry_kind"] == "wechat_mini_program"
    assert items[0]["mini_program_name"] == app_name
    assert items[0]["mini_program_token"] == "WDUa9A1nxlXZoSz"
    assert "source_url" not in items[0]
    assert "message" not in items[0]


def test_wechat_history_ignores_unreviewed_native_mini_program():
    assert parse_xiaocao_live_messages(_history(
        "[2026-09-24 17:07] 福利官小花四: "
        "#小程序://其他直播/W4o8kKJeegclUZv"
    )) == []


def test_unsupported_merchant_entry_is_retained_without_arming_or_retry(tmp_path):
    history = _history("[2026-09-11 16:38] 福利官小花四: https://wxmpurl.cn/OOgqnECl26c")
    calls = []
    driver = _CaptureDriver()

    def exchange(request):
        calls.append(request)
        return {"action": request["action"], "subscription_id": request["subscription_id"],
                "page_state": "unsupported_application", "launch_allowed": False}

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path, history_reader=lambda: history, browser_exchange=exchange,
        capture_driver=driver,
        clock=lambda: datetime.fromisoformat("2026-09-12T12:00:00+08:00"),
    )
    result = subscription.run_once(opencli_session="test")
    assert result["unsupported_application"] is True
    assert driver.arms == []
    saved = subscription._load()["items"][result["identity"]]
    assert saved["status"] == "unsupported_application"
    assert saved["message_sha256"]
    subscription.run_once(opencli_session="test")
    assert len(calls) == 1


class _CaptureDriver:
    def __init__(self):
        self.arms: list[tuple[str, str | None]] = []
        self.advances = 0
        self.capture_checks = 0
        self.native_bindings = []
        self.playback_preparations = []
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
    ) -> dict:
        self.arms.append((identity, page_url))
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
    ) -> dict:
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
    ) -> dict:
        assert identity
        assert capture_job_id == "kol-capture-current"
        self.capture_checks += 1
        return dict(self.capture_check_result)

    def published_handoff(
        self,
        identity: str,
        capture_job_id: str,
    ) -> dict | None:
        del identity, capture_job_id
        return None


@pytest.mark.parametrize("previous_status", [None, "expired", "superseded", "historical_baseline"])
def test_explicit_dated_backfill_recovers_only_the_selected_original_entry(
    tmp_path, previous_status,
):
    payload = _history(
        "[2026-09-23 08:44] 小花: #小程序://见势擒龙团/7qBV0CwjiqCrkHB",
        "[2026-09-27 17:17] 小花: #小程序://见势擒龙团/YbZMTddvUAzLR2c",
    )
    original = parse_xiaocao_live_messages(payload)[0]
    driver = _CaptureDriver()
    requests = []

    def exchange(request):
        requests.append(request)
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": "wechat_mini_program",
            "page_state": "mini_program_waiting",
            "activated": False,
            "media_request_observed": False,
            "playback_window_closed": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat", history_reader=lambda: payload,
        browser_exchange=exchange, capture_driver=driver,
        clock=lambda: datetime.fromisoformat("2026-09-28T10:15:00+08:00"),
    )
    manifest = subscription._load()
    if previous_status:
        manifest["items"][original["identity"]] = {**original, "status": previous_status}
        subscription._save(manifest)

    result = subscription.run_once(
        opencli_session="test", only_identity=original["identity"],
        backfill_since="2026-09-23",
    )

    assert result["status"] == "waiting"
    assert driver.arms == [(original["identity"], None)]
    assert driver.advances == 0
    assert len(requests) == 1
    assert requests[0]["mini_program_token"] == original["mini_program_token"]
    items = subscription._load()["items"]
    assert list(items) == [original["identity"]]
    assert items[original["identity"]]["capture_job_id"] == "kol-capture-current"
    assert items[original["identity"]]["manual_backfill_since"] == "2026-09-23"


@pytest.mark.parametrize("retained_native_repair", [False, True])
def test_dated_backfill_revalidates_reexpired_item_and_reuses_capture(tmp_path, retained_native_repair):
    payload = _history(
        "[2026-09-23 08:44] 小花: #小程序://见势擒龙团/7qBV0CwjiqCrkHB",
    )
    original = parse_xiaocao_live_messages(payload)[0]
    driver = _CaptureDriver()
    driver.can_expire_wait = lambda identity, job: not retained_native_repair and job == "kol-capture-current"
    driver.can_resume_unbound_native_repair = lambda identity, job: retained_native_repair and job == "kol-capture-current"
    history_reads = []
    requests = []

    def history():
        history_reads.append(True)
        return payload

    def exchange(request):
        requests.append(request)
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": "wechat_mini_program",
            "page_state": "mini_program_waiting",
            "activated": False,
            "media_request_observed": False,
            "playback_window_closed": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat", history_reader=history, browser_exchange=exchange,
        capture_driver=driver,
        clock=lambda: datetime.fromisoformat("2026-09-28T10:15:00+08:00"),
    )
    manifest = subscription._load()
    manifest["items"][original["identity"]] = {
        **original, "status": "expired", "capture_job_id": "kol-capture-current",
        "manual_backfill_since": "2026-09-23",
    }
    subscription._save(manifest)

    result = subscription.run_once(
        opencli_session="test", only_identity=original["identity"],
        backfill_since="2026-09-23",
    )

    assert result["status"] == "waiting"
    assert len(history_reads) == 1
    assert driver.arms == []
    assert driver.playback_preparations == [(original["identity"], "kol-capture-current")]
    assert len(requests) == 1
    assert requests[0]["mini_program_token"] == original["mini_program_token"]
    assert subscription._load()["items"][original["identity"]]["capture_job_id"] == "kol-capture-current"


@pytest.mark.parametrize("since,identity", [
    ("2026-09-24", "selected"),
    ("invalid", "selected"),
    ("2026-09-23", None),
])
def test_manual_backfill_rejects_ambiguous_or_out_of_range_requests(tmp_path, since, identity):
    payload = _history("[2026-09-23 08:44] 小花: #小程序://见势擒龙团/7qBV0CwjiqCrkHB")
    original = parse_xiaocao_live_messages(payload)[0]
    driver = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat", history_reader=lambda: payload,
        browser_exchange=lambda request: pytest.fail("invalid backfill must not launch"),
        capture_driver=driver,
        clock=lambda: datetime.fromisoformat("2026-09-28T10:15:00+08:00"),
    )
    with pytest.raises(EnrichmentError):
        subscription.run_once(
            opencli_session="test", only_identity=original["identity"] if identity else None,
            backfill_since=since,
        )
    assert driver.arms == []


@pytest.mark.parametrize("previous_authorization", [False, True])
@pytest.mark.parametrize("status,fields", [
    ("completed", {"handoff_id": "same-handoff", "capture_job_id": "same-capture"}),
    ("expired", {"candidate_id": "same-candidate", "capture_job_id": "same-capture"}),
])
def test_manual_backfill_never_resets_completed_or_bound_claims(
    tmp_path, status, fields, previous_authorization,
):
    payload = _history("[2026-09-23 08:44] 小花: #小程序://见势擒龙团/7qBV0CwjiqCrkHB")
    original = parse_xiaocao_live_messages(payload)[0]
    driver = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat", history_reader=lambda: payload,
        browser_exchange=lambda request: pytest.fail("bound work must not relaunch"),
        capture_driver=driver,
        clock=lambda: datetime.fromisoformat("2026-09-28T10:15:00+08:00"),
    )
    manifest = subscription._load()
    saved = {**original, "status": status, **fields}
    if previous_authorization:
        saved["manual_backfill_since"] = "2026-09-23"
    manifest["items"][original["identity"]] = saved
    subscription._save(manifest)
    if status == "completed":
        assert subscription.run_once(
            opencli_session="test", only_identity=original["identity"],
            backfill_since="2026-09-23",
        )["already_completed"] is True
    else:
        with pytest.raises(EnrichmentError, match="reconcile existing bound claims"):
            subscription.run_once(
                opencli_session="test", only_identity=original["identity"],
                backfill_since="2026-09-23",
            )
    assert driver.arms == []
    assert subscription._load()["items"][original["identity"]] == saved


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
    assert result["waiting_items"][0]["category"] == "provider_wait"
    assert result["waiting_items"][0]["code"] == "awaiting_playback"
    progress = normalize_source_result(
        "xiaocao_wechat_live",
        result,
        failure_revision="a" * 40,
        provider_contract_version="xiaocao_writer_v1",
    )
    assert progress.status == "wait_until"
    assert progress.next_action == "resume_after_deadline"
    assert progress.details["category"] == "provider_wait"
    assert progress.details["code"] == "awaiting_playback"


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
        ):
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
        ):
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
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "page_url": (
                    "https://appsnm3rlcp3566.h5.xiaoeknow.com/v2/course/"
                    "alive/l_6a708838e4b0694c5bf42e55?share_user_id=private"
                ),
                "page_state": "unknown",
            }
        assert request["action"] == "activate_xiaoetong_mini_program"
        assert request["password_policy"] == {
            "only_if_password_gate_visible": True,
            "password": "666",
        }
        assert "不要打开或依赖浏览器 H5 播放页" in request["instructions"]
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:appsnm3rlcp3566:l_6a708838e4b0694c5bf42e55"
            ),
            "live_id": "l_6a708838e4b0694c5bf42e55",
            "page_state": "mini_program_media_observed",
            "activated": True,
            "playback_window_closed": True,
            "password_used": True,
            "media_request_observed": True,
        }

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
        clock=lambda: datetime.fromisoformat("2026-08-04T23:00:00+08:00"),
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )

    assert result["status"] == "waiting"
    assert result["waiting_count"] == 1
    assert result["waiting_items"][0]["stage"] == "compressed_capture"
    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_mini_program",
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


@pytest.mark.parametrize("closed", [True, False, None])
@pytest.mark.parametrize("page_state", ["mini_program_media_observed", "live", "waiting_to_start", "replay_generating", "mini_program_waiting", "unknown"])
def test_wechat_mini_program_route_binds_media_to_the_exact_live_id(tmp_path, closed, page_state):
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
            "playback_cleanup": "close_course_window",
            "window_close_readback_required": True,
            "coordinate_policy": "fresh_screenshot_visible_control_only_when_ax_absent",
        }
        assert "浏览器 H5" in request["instructions"]
        assert request["launch_resolver_command"] == [
            ".venv/bin/python", "scripts/kol_xiaoetong_launch.py",
            "--source-url", request["source_url"],
            "--expected-identity", "xiaoetong:app6ums63as6516:l_6a9531fbe4b0694c35440d7e",
        ]
        assert "不重开" in request["instructions"]
        assert "只有直播结束且完整回放生成才可下载" in request["instructions"]
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:app6ums63as6516:l_6a9531fbe4b0694c35440d7e"
            ),
            "live_id": "l_6a9531fbe4b0694c35440d7e",
            "page_state": page_state,
            "activated": True,
            "playback_window_closed": closed,
            "playback_paused": True,  # A pause must not satisfy the new close gate.
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
        clock=lambda: datetime.fromisoformat("2026-08-31T23:00:00+08:00"),
    )

    if closed is not True and page_state == "mini_program_media_observed":
        with pytest.raises(EnrichmentDiagnosticError) as error:
            subscription.run_once(opencli_session="xiaocao-lv-subscription")
        assert error.value.diagnostic_code == "native_playback_window_close_unverified"
        assert capture.advances == 0
        return

    result = subscription.run_once(opencli_session="xiaocao-lv-subscription")
    assert result["status"] == "waiting"
    assert capture.advances == (1 if page_state == "mini_program_media_observed" else 0)
    assert [request["action"] for request in requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_mini_program",
    ]
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["status"] == ("playback_activated" if page_state == "mini_program_media_observed" else "awaiting_playback")
    assert item["playback_route"] == (
        XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM
    )
    assert item["playback_surface"] == (
        XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM
    )
    assert item["media_request_observed"] is True
    assert item["source_resource_id"] == "l_6a9531fbe4b0694c35440d7e"
    assert item["observed_page_state"] == page_state
    assert item["playback_window_closed"] is (closed is True)


@pytest.mark.parametrize("app_name,app_id", [
    ("鹅直播", "app6ums63as6516"),
    ("见势擒龙团", "appsnm3rlcp3566"),
])
def test_native_mini_program_entry_is_armed_before_ui_and_binds_observed_live(
    tmp_path, app_name, app_id,
):
    payload = _history(
        "[2026-09-04 08:37] 福利官小花四: 9点20草神直播地址（密码666）："
        f"#小程序://{app_name}/WDUa9A1nxlXZoSz"
    )
    requests: list[dict] = []
    capture = _CaptureDriver()

    def browser_exchange(request: dict) -> dict:
        requests.append(request)
        assert request["action"] == "activate_xiaoetong_mini_program"
        assert request["mini_program_name"] == app_name
        assert request["mini_program_token"] == "WDUa9A1nxlXZoSz"
        assert "source_url" not in request
        assert "launch_resolver_command" not in request
        if app_name == "见势擒龙团":
            assert Path(request["native_entry_reference"]).is_file()
            assert request["native_bridge_config_path"] == (
                "output/live/kol_xiaocao_live/native_share_bridge.json"
            )
        else:
            assert "native_entry_reference" not in request
            assert "native_bridge_config_path" not in request
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                f"xiaoetong:{app_id}:l_6a99d00de4b0694c3546aaaa"
            ),
            "live_id": "l_6a99d00de4b0694c3546aaaa",
            "candidate_id": "candidate-new-live",
            "page_state": "mini_program_media_observed",
            "activated": True,
            "playback_window_closed": True,
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
        clock=lambda: datetime.fromisoformat("2026-09-04T23:00:00+08:00"),
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )

    assert result["status"] == "waiting"
    assert capture.arms == [(
        result["waiting_items"][0]["identity"],
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
        f"xiaoetong:{app_id}:l_6a99d00de4b0694c3546aaaa"
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


@pytest.mark.parametrize("invalid", [
    None, "no_anchor", "other_app", "other_live", "other_media", "other_host",
    "other_endpoint", "reporting_query", "old_anchor", "future_anchor",
    "stale_capture", "live_stream", "indirect_request", "conflicting_anchor",
])
def test_native_direct_manifest_requires_exact_merchant_lineage(tmp_path, invalid):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    armed = store.arm([])
    armed = store.transition(armed, "test_clock", created_at="2026-09-05T15:00:00+08:00")
    resource = "https://encrypt-k-vod.xet.tech/content/replay/playlist_eof.m3u8"
    candidate = {
        "id": "fresh-request", "live_id": "l_target",
        "captured": "2026-09-05 15:02:00", "media_type": "m3u8",
        "source_url": resource + "?ticket=fresh-private",
        "source_path": "/content/replay/playlist_eof.m3u8",
        "url": resource + "?ticket=fresh-private",
    }
    anchor = {
        "id": "metadata-anchor", "live_id": "l_target",
        "captured": "2026-09-05 15:01:00", "media_type": "m3u8",
        "source_url": "https://appdemo.h5.xe-live.com/_alive/v3/get_lookback_list",
        "source_path": "/_alive/v3/get_lookback_list",
        "json_path": "data[0].line_sharpness[0].url",
        "url": resource + "?ticket=old-private",
    }
    observations = [candidate, anchor]
    if invalid == "no_anchor":
        observations = [candidate]
    elif invalid == "other_app":
        anchor["source_url"] = anchor["source_url"].replace("appdemo", "appother")
    elif invalid == "other_live":
        anchor["live_id"] = "l_other"
    elif invalid == "other_media":
        anchor["url"] = anchor["url"].replace("/replay/", "/another/")
    elif invalid == "other_host":
        anchor["url"] = anchor["url"].replace("encrypt-k-vod", "another-vod")
    elif invalid == "other_endpoint":
        anchor["source_url"] = anchor["source_url"].replace("get_lookback_list", "get_warm_up_video")
        anchor["source_path"] = "/_alive/v3/get_warm_up_video"
    elif invalid == "reporting_query":
        anchor["json_path"] = "query.params[play_url]"
    elif invalid == "old_anchor":
        anchor["captured"] = "2026-09-05 14:59:00"
    elif invalid == "future_anchor":
        anchor["captured"] = "2026-09-05 15:03:00"
    elif invalid == "stale_capture":
        candidate["captured"] = "2026-09-05 14:59:00"
    elif invalid == "live_stream":
        candidate["url"] = candidate["source_url"] = resource.replace("playlist_eof", "liveplay")
        candidate["source_path"] = "/content/replay/liveplay.m3u8"
    elif invalid == "indirect_request":
        candidate["source_path"] = "/report"
    elif invalid == "conflicting_anchor":
        observations.append({**anchor, "id": "conflict", "live_id": "l_other"})
    service = SimpleNamespace(
        capture_store=store,
        sniffer=SimpleNamespace(candidates=lambda: observations),
    )
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    kwargs = dict(source_identity="xiaoetong:appdemo:l_target", candidate_id="fresh-request")
    if invalid:
        with pytest.raises(EnrichmentError):
            driver.bind_mini_program_capture("item", armed["job_id"], **kwargs)
        assert store.latest()["status"] == "awaiting_capture"
        return
    result = driver.bind_mini_program_capture("item", armed["job_id"], **kwargs)
    assert result["job_id"] == armed["job_id"]
    assert result["status"] == "captured"
    assert result["candidate"]["id"] == "fresh-request"
    assert result["native_media_lineage"] == {
        "method": "direct_manifest_with_merchant_lookback",
        "media_resource_sha256": hashlib.sha256(resource.encode()).hexdigest(),
        "metadata_anchors": [{
            "candidate_id": "metadata-anchor", "source_host": "appdemo.h5.xe-live.com",
            "source_path": "/_alive/v3/get_lookback_list",
            "json_path": "data[0].line_sharpness[0].url",
        }],
    }
    assert driver.bind_mini_program_capture("item", armed["job_id"], **kwargs) == result
    assert "private" not in store.path.read_text()


@pytest.mark.parametrize("host,valid", [
    ("appdemo.h5.xiaoe-live.com", True),
    ("appdemo.h5.xetsdkspace.com", True),
    ("appdemo.mp.xetsdkspace.com", False),
    ("appdemo.h5.xetsdkspace.com.evil.test", False),
])
def test_native_lineage_accepts_documented_sdk_merchants_only(tmp_path, host, valid):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    armed = store.transition(store.arm([]), "test_clock", created_at="2026-09-05T15:00:00+08:00")
    resource = "https://encrypt-k-vod.xet.tech/content/playlist_eof.m3u8"
    candidate = {"id": "native", "live_id": "l_target", "captured": "2026-09-05 15:02:00",
                 "media_type": "m3u8", "url": resource, "source_url": resource,
                 "source_path": "/content/playlist_eof.m3u8"}
    anchor = {"id": "merchant", "live_id": "l_target", "captured": "2026-09-05 15:01:00",
              "media_type": "m3u8", "url": resource,
              "source_url": f"https://{host}/_alive/v3/get_lookback_list",
              "source_path": "/_alive/v3/get_lookback_list",
              "json_path": "data[0].line_sharpness[0].url"}
    service = SimpleNamespace(capture_store=store, sniffer=SimpleNamespace(candidates=lambda: [candidate, anchor]))
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    if not valid:
        with pytest.raises(EnrichmentError):
            driver.bind_mini_program_capture("item", armed["job_id"],
                source_identity="xiaoetong:appdemo:l_target", candidate_id="native")
        assert store.latest()["status"] == "awaiting_capture"
    else:
        bound = driver.bind_mini_program_capture("item", armed["job_id"],
            source_identity="xiaoetong:appdemo:l_target", candidate_id="native")
        assert bound["native_media_lineage"]["metadata_anchors"][0]["source_host"] == host
        assert bound["job_id"] == armed["job_id"]


@pytest.mark.parametrize("invalid", [None, "missing_base", "old_base", "other_app", "other_live", "other_media",
    "review_id", "other_host", "unapproved_field", "outside_root", "provider_error"])
def test_native_v2_binding_reopens_actual_merchant_response_without_global_context(tmp_path, invalid):
    from datetime import datetime
    from xiaocao.kol.xiaocao_wechat import _native_direct_media_lineage

    root = tmp_path / "elive_live_debug"
    (root / "json").mkdir(parents=True)
    resource = "https://encrypt-k-vod.xet.tech/vod/playlist_eof.m3u8"
    candidate = {"id":"native", "url":resource+"?sign=private", "media_type":"m3u8", "live_id":"l_target",
        "source_url":"https://xet.kj1team.cn/_alive/v2/get_lookback_url",
        "source_path":"/_alive/v2/get_lookback_url", "json_path":"data.miniAliveVideoUrl"}
    base = {"code":0,"data":{"alive_info":{"app_id":"appsnm3rlcp3566","alive_id":"l_target"}}}
    replay = {"code":0,"data":{"aliveReviewUrl":"/l_target.m3u8","miniAliveVideoUrl":resource+"?sign=private"}}
    if invalid == "other_app": base["data"]["alive_info"]["app_id"] = "appother"
    if invalid == "other_live": base["data"]["alive_info"]["alive_id"] = "l_other"
    if invalid == "other_media": replay["data"]["miniAliveVideoUrl"] = resource.replace("vod/", "different/")
    if invalid == "review_id": replay["data"]["aliveReviewUrl"] = "/l_other.m3u8"
    if invalid == "provider_error": replay["code"] = 401
    if invalid == "other_host": candidate["source_url"] = candidate["source_url"].replace("xet.kj1team.cn", "xet.kj1team.cn.evil.test")
    if invalid == "unapproved_field": candidate["json_path"] = "data.warmupUrl"
    events = []
    for name, path, payload, at in [("base", "/_alive/v3/base_info", base, "2026-09-05T15:01:00.5+08:00"),
        ("replay", "/_alive/v2/get_lookback_url", replay, "2026-09-05T15:01:01.5+08:00")]:
        file = root / "json" / f"{name}.json"
        if invalid == "outside_root": file = tmp_path / f"{name}.json"
        file.write_text(json.dumps(payload))
        if invalid == "missing_base" and name == "base": continue
        if invalid == "old_base" and name == "base": at = "2026-09-05T14:59:59+08:00"
        events.append({"kind":"response.body","url":"https://xet.kj1team.cn"+path,"at":at,"status":200,"file":str(file)})
    (root / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    kwargs = dict(app_id="appsnm3rlcp3566",live_id="l_target",debug_root=root,
        armed_at=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
        captured_at=datetime.fromisoformat("2026-09-05T15:01:01+08:00"))
    if invalid:
        with pytest.raises(EnrichmentError): _native_direct_media_lineage(candidate, [], **kwargs)
    else:
        result = _native_direct_media_lineage(candidate, [], **kwargs)
        assert result["method"] == "native_v2_merchant_response"
        assert result["media_resource_sha256"] == hashlib.sha256(resource.encode()).hexdigest()
        assert len(result["metadata_anchors"][0]["response_sha256"]) == 64
        assert "private" not in json.dumps(result)


@pytest.mark.parametrize("invalid", [None, "cached_probe", "signed_probe", "no_end", "not_vod", "live", "old", "wrong_resource", "outside"])
def test_native_numeric_playlist_requires_singleton_ended_vod_receipt(tmp_path, invalid, monkeypatch):
    from datetime import datetime
    from xiaocao.kol.xiaocao_wechat import _native_direct_media_lineage, _native_v2_merchant_lineage
    root = tmp_path / "elive_live_debug"
    (root / "json").mkdir(parents=True)
    (root / "m3u8").mkdir()
    resource = "https://live-ex-speed.xiaoeknow.com/5060_recording.m3u8"
    candidate = {"id": "native", "url": resource, "media_type": "m3u8", "live_id": "l_target",
        "source_url": "https://xet.kj1team.cn/_alive/v2/get_lookback_url",
        "source_path": "/_alive/v2/get_lookback_url", "json_path": "data.miniAliveVideoUrl"}
    base = {"code": 0, "data": {"alive_info": {"app_id": "appsnm3rlcp3566", "alive_id": "l_target", "alive_state": 3}}}
    if invalid == "live": base["data"]["alive_info"]["alive_state"] = 1
    replay = {"code": 0, "data": {"aliveReviewUrl": "/l_target.m3u8", "miniAliveVideoUrl": resource}}
    if invalid == "signed_probe": replay["data"]["miniAliveVideoUrl"] += "?sign=private"
    events = []
    for name, body, path, at in [("base", base, "/_alive/v3/base_info", "2026-09-05T15:01:00+08:00"),
            ("replay", replay, "/_alive/v2/get_lookback_url", "2026-09-05T15:01:01+08:00")]:
        file = root / "json" / (name + ".json")
        file.write_text(json.dumps(body))
        events.append({"kind": "response.body", "status": 200, "url": "https://xet.kj1team.cn" + path,
                       "at": at, "file": str(file)})
    body = "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:120,\nsegment.ts\n#EXT-X-ENDLIST\n\n"
    if invalid == "no_end": body = body.replace("#EXT-X-ENDLIST\n", "")
    if invalid == "not_vod": body = body.replace("VOD", "EVENT")
    file = (tmp_path if invalid == "outside" else root / "m3u8") / "recording.m3u8"
    file.write_text(body)
    if invalid in {"cached_probe", "signed_probe"}: file.write_text("")
    events.append({"kind": "response.body", "status": 200,
        "url": resource + (".other" if invalid == "wrong_resource" else ""), "file": str(file),
        "at": "2026-09-05T14:59:00+08:00" if invalid == "old" else "2026-09-05T15:01:03+08:00"})
    (root / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    kwargs = dict(app_id="appsnm3rlcp3566", live_id="l_target", debug_root=root,
        armed_at=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
        captured_at=datetime.fromisoformat("2026-09-05T15:01:01+08:00"))
    calls = []
    def probe(argv, **kw):
        calls.append(argv)
        assert "-k" not in argv and "--insecure" not in argv and argv[-1] == resource
        file.write_text(body)
        return SimpleNamespace(returncode=0, stdout=body.encode())
    monkeypatch.setattr("xiaocao.kol.xiaocao_wechat.subprocess.run", probe)
    if invalid in {"cached_probe", "signed_probe"}:
        if invalid == "signed_probe":
            with pytest.raises(EnrichmentError): _native_v2_merchant_lineage(candidate, public_probe=True, **kwargs)
            assert not calls
        else:
            assert _native_v2_merchant_lineage(candidate, public_probe=True, **kwargs)["finite_playlist"]["ended"]
            assert len(calls) == 1
        return
    if invalid:
        with pytest.raises(EnrichmentError): _native_direct_media_lineage(candidate, [], **kwargs)
    else:
        result = _native_direct_media_lineage(candidate, [], **kwargs)
        assert result["finite_playlist"]["ended"] is True
        assert result["finite_playlist"]["duration_seconds"] == 120


@pytest.mark.parametrize("invalid", [None, "missing_anchor", "changed_source", "changed_media", "stale"])
def test_unbound_native_repair_still_requires_exact_original_identity_and_lineage(tmp_path, invalid):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    resource = "https://encrypt-k-vod.xet.tech/content/playlist_eof.m3u8"
    armed = store.transition(store.arm([]), "unaccepted_observation",
        created_at="2026-09-05T14:00:00+08:00", native_repair_armed_at="2026-09-05T15:00:00+08:00",
        native_unbound_media={"media_resource_sha256": hashlib.sha256(resource.encode()).hexdigest(),
            "source_identity_observed": "xiaoetong:appdemo:l_target", "source_accepted": False})
    candidate = {"id": "renewed", "live_id": "l_target", "captured": "2026-09-05 15:02:00",
        "media_type": "m3u8", "url": resource, "source_url": resource, "source_path": "/content/playlist_eof.m3u8"}
    anchor = {"id": "anchor", "live_id": "l_target", "captured": "2026-09-05 15:01:00",
        "media_type": "m3u8", "url": resource,
        "source_url": "https://appdemo.h5.xetsdkspace.com/_alive/v3/get_lookback_list",
        "source_path": "/_alive/v3/get_lookback_list", "json_path": "data[0].line_sharpness[0].url"}
    source_identity = "xiaoetong:appdemo:l_target"
    if invalid == "changed_source":
        source_identity = "xiaoetong:appother:l_target"
        anchor["source_url"] = anchor["source_url"].replace("appdemo", "appother")
    if invalid == "changed_media":
        for key in ("url", "source_url", "source_path"):
            candidate[key] = candidate[key].replace("/content/", "/other/")
        anchor["url"] = candidate["url"]
    if invalid == "stale":
        candidate["captured"] = "2026-09-05 14:30:00"
    observations = [candidate] if invalid == "missing_anchor" else [candidate, anchor]
    service = SimpleNamespace(capture_store=store, sniffer=SimpleNamespace(candidates=lambda: observations))
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    assert not driver.can_expire_wait("item", armed["job_id"])
    if invalid:
        with pytest.raises(EnrichmentError):
            driver.bind_mini_program_capture("item", armed["job_id"], source_identity=source_identity, candidate_id="renewed")
        assert store.latest() == armed
    else:
        bound = driver.bind_mini_program_capture("item", armed["job_id"], source_identity=source_identity, candidate_id="renewed")
        assert bound["job_id"] == armed["job_id"] and bound["status"] == "captured"
        assert bound["native_media_lineage"]["metadata_anchors"][0]["candidate_id"] == "anchor"


@pytest.mark.parametrize("invalid", [
    None, "different_media", "old_request", "uncertain_task", "restored_pause",
    "unclaimed_pause", "different_paused_task", "partial_paused_task",
    "cached_lineage", "cached_missing_anchor", "cached_wrong_anchor",
])
def test_native_repair_retains_capture_and_only_renews_same_failed_media(tmp_path, invalid):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    armed = store.arm([])
    resource = "https://encrypt-k-vod.xet.tech/content/playlist_eof.m3u8"
    held = store.transition(
        armed, "repair_hold", status="download_retry_claimed",
        expected_source={"source_identity": "xiaoetong:appdemo:l_target"},
        candidate={"id": "old", "live_id": "l_target"}, candidate_key="live:l_target",
        download_task_id="failed", native_repair_armed_at="2026-09-05T15:00:00+08:00",
        native_media_lineage={"media_resource_sha256": hashlib.sha256(resource.encode()).hexdigest()},
    )
    candidate = {"id": "fresh", "live_id": "l_target", "media_type": "m3u8",
                 "captured": "2026-09-05 15:02:00", "url": resource,
                 "source_url": resource, "source_path": "/content/playlist_eof.m3u8"}
    if invalid == "different_media":
        candidate.update(url=resource.replace("content", "other"), source_url=resource.replace("content", "other"), source_path="/other/playlist_eof.m3u8")
    if invalid == "old_request":
        candidate["captured"] = "2026-09-05 14:59:00"
    anchor = {"id": "metadata", "live_id": "l_target", "media_type": "m3u8",
              "captured": "2026-09-05 15:01:00", "url": candidate["url"],
              "source_url": "https://appdemo.h5.xe-live.com/_alive/v3/get_lookback_list",
              "source_path": "/_alive/v3/get_lookback_list", "json_path": "data[0].line_sharpness[0].url"}
    if invalid and invalid.startswith("cached_"):
        anchor["captured"] = "2026-09-05 14:30:00"
        held = store.transition(
            held, "prior_native_binding", created_at="2026-09-05T14:00:00+08:00",
            candidate={**candidate, "id": "old", "captured": "2026-09-05 14:31:00"},
            native_media_lineage={
                "method": "direct_manifest_with_merchant_lookback",
                "media_resource_sha256": hashlib.sha256(resource.encode()).hexdigest(),
                "metadata_anchors": [{
                    "candidate_id": "missing" if invalid == "cached_missing_anchor" else "metadata",
                    "source_host": "appother.h5.xe-live.com" if invalid == "cached_wrong_anchor" else "appdemo.h5.xe-live.com",
                    "source_path": anchor["source_path"], "json_path": anchor["json_path"],
                }],
            },
        )
    task = {"id": "failed", "status": "error", "progress": {"downloaded": 0},
            "meta": {"req": {"labels": {"capture_id": "old", "live_id": "l_target"}}}}
    if invalid == "uncertain_task":
        task["progress"]["downloaded"] = 1
    if invalid in {"restored_pause", "unclaimed_pause", "different_paused_task", "partial_paused_task"}:
        task["status"] = "pause"
        if invalid != "unclaimed_pause":
            held = store.transition(
                held, "native_backend_repaired",
                repair_task_id="other" if invalid == "different_paused_task" else "failed",
                repaired_binary_sha256="a" * 64,
            )
        if invalid == "partial_paused_task":
            task["progress"]["downloaded"] = 1
    observations = [candidate, anchor]
    if invalid and invalid.startswith("cached_"):
        observations.append({**candidate, "id": "old", "captured": "2026-09-05 14:31:00"})
    service = SimpleNamespace(capture_store=store, sniffer=SimpleNamespace(
        candidates=lambda: observations, tasks=lambda: [task]))
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    if invalid not in {None, "restored_pause", "cached_lineage"}:
        with pytest.raises(EnrichmentError):
            driver.refresh_failed_native_capture("item", held["job_id"], candidate_id="fresh")
        assert store.latest() == held
        return
    result = driver.refresh_failed_native_capture("item", held["job_id"], candidate_id="fresh")
    assert result["job_id"] == held["job_id"]
    assert result["download_task_id"] == "failed"
    assert result["previous_candidate_id"] == "old"
    assert result["candidate"]["id"] == "fresh"
    assert result["status"] == "download_failed"


@pytest.mark.parametrize("repaired", [False, True])
def test_native_repair_wait_cannot_auto_bind_historical_candidates(tmp_path, repaired):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    capture = store.arm([])
    if repaired:
        capture = store.transition(capture, "repair_wait", native_repair_armed_at="2026-09-05T15:00:00+08:00")
    starts = []
    service = SimpleNamespace(capture_store=store, start=lambda: starts.append(True))
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    assert driver.advance_capture("item", capture["job_id"]) == {
        "status": "awaiting_capture", "capture_job_id": capture["job_id"]}
    assert starts == [True]
    assert store.latest() == capture


@pytest.mark.parametrize("claim", [None, "source_job_id", "download_task_id", "expected_source", "native_unbound_media"])
def test_native_playback_reconciles_only_unaccepted_global_observation(tmp_path, claim):
    store = CaptureJobStore(tmp_path / "capture.jsonl")
    original = store.arm([{"id": "baseline"}])
    captured = store.transition(original, "capture_detected", status="captured",
        candidate={"id": "another-course", "live_id": "l_other"},
        candidate_key="live:l_other", **({claim: "retained-claim"} if claim else {}))
    (tmp_path / "manifest.json").write_text(json.dumps({"items": {"item": {
        "entry_kind": "wechat_mini_program", "status": "awaiting_playback",
        "capture_job_id": original["job_id"], "media_request_observed": False,
    }}}))
    service = SimpleNamespace(capture_store=store, start=lambda: {
        "capture_job_id": original["job_id"], "status": store.latest()["status"]})
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **kw: service)
    if claim:
        with pytest.raises(EnrichmentError, match="existing awaiting capture"):
            driver.prepare_playback("item", original["job_id"])
        assert store.latest() == captured
    else:
        assert driver.prepare_playback("item", original["job_id"])["status"] == "awaiting_capture"
        restored = store.latest()
        assert restored["job_id"] == original["job_id"]
        assert restored["baseline_candidate_keys"] == original["baseline_candidate_keys"]
        assert restored["candidate"] is None
        assert restored["rejected_global_candidate"] == captured["candidate"]


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
            "playback_window_closed": True,
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
        clock=lambda: datetime.fromisoformat("2026-08-31T23:00:00+08:00"),
    )

    with pytest.raises(
        EnrichmentError,
        match="WeChat mini-program playback binding is invalid",
    ):
        subscription.run_once(opencli_session="xiaocao-lv-subscription")
    assert capture.advances == 0


def test_transcribed_resolver_identity_is_rejected_before_arming(tmp_path):
    capture = _CaptureDriver()
    page = "https://app123.h5.xiaoeknow.com/v2/course/alive/l_wrong"
    def exchange(request):
        command = request["launch_resolver_command"]
        assert command[command.index("--subscription-id") + 1] == "item"
        assert "browser_response unchanged" in request["instructions"]
        return {"action": request["action"],
            "subscription_id": request["subscription_id"], "page_url": page,
            "page_state": "unknown", "source_identity": "xiaoetong:app123:l_correct",
            "live_id": "l_correct"}
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path, history_reader=lambda: {}, capture_driver=capture, contact=CONTACT,
        browser_exchange=exchange)
    with pytest.raises(EnrichmentError, match="resolver response identity"):
        subscription._resolve_page({}, {"identity": "item", "source_url": "https://x.xet.tech/s/a"})
    assert capture.arms == []


def test_h5_playback_state_is_rejected_before_arming(tmp_path):
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
            }
        raise AssertionError("H5 resolution must stop before native activation")

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
        clock=lambda: datetime.fromisoformat("2026-08-13T23:00:00+08:00"),
    )

    with pytest.raises(
        EnrichmentError,
        match="Xiaocao H5 resolution returned a playback state",
    ):
        subscription.run_once(opencli_session="xiaocao-lv-subscription")

    assert capture.arms == []


def test_persisted_web_recorded_video_is_rejected_before_arming(tmp_path):
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
        }

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        output,
        history_reader=lambda: pytest.fail("narrow resume must not rescan WeChat"),
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
        clock=lambda: datetime.fromisoformat("2026-08-13T23:00:00+08:00"),
    )

    with pytest.raises(
        EnrichmentError,
        match="supports only Xiaoetong live mini-program entries",
    ):
        subscription.run_once(
            opencli_session="xiaocao-lv-subscription",
            only_identity=identity,
        )

    assert requests == []
    assert capture.arms == []


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
                "page_state": "unknown",
            }
        return {
            "action": request["action"],
            "subscription_id": request["subscription_id"],
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:appsnm3rlcp3566:"
                + (
                    "l_new_preview"
                    if request["source_url"].endswith("/new002")
                    else "l_old_preview"
                )
            ),
            "live_id": (
                "l_new_preview"
                if request["source_url"].endswith("/new002")
                else "l_old_preview"
            ),
            "page_state": "mini_program_media_observed",
            "activated": True,
            "playback_window_closed": True,
            "password_used": False,
            "media_request_observed": True,
        }

    capture = _CaptureDriver()
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload[0],
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
        clock=lambda: datetime.fromisoformat("2026-08-05T23:00:00+08:00"),
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
    assert manifest["items"][morning_identity]["status"] == "discovered"
    assert "superseded_by" not in manifest["items"][morning_identity]

    # Recover the legacy persisted state only through explicit same-item resume.
    manifest["items"][morning_identity]["status"] = "superseded"
    subscription._save(manifest)
    subscription.run_once(
        opencli_session="xiaocao-lv-subscription", only_identity=morning_identity,
    )
    assert capture.arms[-1][0] == morning_identity
    restored = subscription._load()["items"][morning_identity]
    assert restored["backfill_reason"] == "explicit_item_resume"


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


@pytest.mark.parametrize("needs_close_readback", [False, True])
def test_existing_source_task_is_reconciled_before_another_wechat_ui_attempt(
    tmp_path, needs_close_readback,
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
                    "media_request_observed": needs_close_readback,
                    "playback_paused": False,
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

    requests = []

    def close_readback(request: dict) -> dict:
        assert needs_close_readback, "completed source must bypass new playback"
        assert request["check_reason"] == "captured_window_cleanup"
        assert "launch_resolver_command" not in request
        requests.append(request)
        return {
            "action": request["action"],
            "subscription_id": identity,
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": "xiaoetong:app6ums63as6516:l_target",
            "live_id": "l_target",
            "page_state": "mini_program_media_observed",
            "activated": True,
            "media_request_observed": True,
            "playback_window_closed": True,
        }

    subscription = XiaocaoWechatLiveSubscription(
        output_dir,
        history_reader=lambda: {},
        browser_exchange=close_readback,
        capture_driver=capture,
        contact=CONTACT,
        playback_route=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
        clock=lambda: datetime.fromisoformat("2026-09-05T23:00:00+08:00"),
    )

    result = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
        only_identity=identity,
    )

    assert result["status"] == "waiting"
    assert result["waiting_items"][0]["stage"] == "compressed_capture"
    assert capture.capture_checks == 1
    assert capture.advances == 1
    assert capture.playback_preparations == []
    assert len(requests) == int(needs_close_readback)


def test_awaiting_playback_rechecks_the_bound_page_each_hour_until_playable(
    tmp_path,
):
    payload = _history(
        "[2026-08-05 08:32] 福利官小花四: 草神直播："
        "https://yv9lc.xetslk.com/sl/4EKPYp",
    )
    browser_requests: list[dict] = []
    activation_states = iter([
        ("mini_program_waiting", False),
        ("mini_program_waiting", False),
        ("mini_program_media_observed", True),
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
                "page_state": "unknown",
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
            "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
            "source_identity": (
                "xiaoetong:appsnm3rlcp3566:l_6a708838e4b0694c5bf42e55"
            ),
            "live_id": "l_6a708838e4b0694c5bf42e55",
            "page_state": page_state,
            "activated": activated,
            "playback_window_closed": activated,
            "password_used": False,
            "media_request_observed": activated,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=capture,
        contact=CONTACT,
        password="666",
        clock=lambda: datetime.fromisoformat("2026-08-05T23:00:00+08:00"),
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
        "activate_xiaoetong_mini_program",
        "activate_xiaoetong_mini_program",
        "activate_xiaoetong_mini_program",
    ]
    assert [
        request.get("check_reason")
        for request in browser_requests
        if request["action"] == "activate_xiaoetong_mini_program"
    ] == ["initial", "awaiting_playback", "awaiting_playback"]
    assert capture.advances == 1
    manifest = json.loads(
        (tmp_path / "wechat" / "manifest.json").read_text(encoding="utf-8")
    )
    item = next(iter(manifest["items"].values()))
    assert item["status"] == "playback_activated"
    assert item["observed_page_state"] == "mini_program_media_observed"


def test_web_playback_route_is_rejected_at_construction(tmp_path):
    with pytest.raises(ValueError, match="web playback is sunset"):
        XiaocaoWechatLiveSubscription(
            tmp_path / "wechat",
            history_reader=lambda: _history(),
            browser_exchange=lambda request: request,
            capture_driver=_CaptureDriver(),
            contact=CONTACT,
            playback_route="xiaoetong_h5",
        )


@pytest.mark.parametrize(
    "page_state, diagnostic_stage",
    [
        ("wechat_client_login_required", "wechat_client_authorization"),
        ("mini_program_consent_required", "mini_program_consent"),
    ],
)
def test_wechat_mini_program_authorization_keeps_login_and_consent_distinct(
    tmp_path, page_state, diagnostic_stage,
):
    page_url = (
        "https://app6ums63as6516.h5.xiaoeknow.com/v4/course/alive/"
        "l_6a75cf66e4b0694c5bf6d228"
    )
    payload = _history(
        "[2026-08-09 16:42] 福利官小花四: 草神直播：" + page_url,
    )
    recovered = False

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
            "page_state": "mini_program_media_observed" if recovered else page_state,
            "activated": recovered,
            "media_request_observed": recovered,
            "playback_window_closed": recovered,
            "password_used": False,
        }

    subscription = XiaocaoWechatLiveSubscription(
        tmp_path / "wechat",
        history_reader=lambda: payload,
        browser_exchange=browser_exchange,
        capture_driver=_CaptureDriver(),
        contact=CONTACT,
        playback_route=XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
        clock=lambda: datetime.fromisoformat("2026-08-09T23:00:00+08:00"),
    )

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        subscription.run_once(opencli_session="xiaocao-lv-subscription")

    assert captured.value.diagnostic_code == page_state
    assert captured.value.diagnostic_stage == diagnostic_stage
    item = next(iter(subscription._load()["items"].values()))
    assert item["status"] == "awaiting_playback"
    assert item["observed_page_state"] == page_state
    assert item["capture_job_id"]
    assert item["activated"] is False
    assert item["user_action_required"] is True
    original_capture_id = item["capture_job_id"]

    recovered = True
    subscription.run_once(opencli_session="xiaocao-lv-subscription")
    resumed = subscription._load()["items"][item["identity"]]
    assert resumed["capture_job_id"] == original_capture_id
    assert resumed["status"] == "playback_activated"
    assert resumed["observed_page_state"] == "mini_program_media_observed"
    assert resumed["activated"] is True
    assert resumed["user_action_required"] is False


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
                "page_state": "unknown",
            }
        if request["action"] == "activate_xiaoetong_mini_program":
            return {
                "action": request["action"],
                "subscription_id": request["subscription_id"],
                "playback_surface": XIAOCAO_PLAYBACK_ROUTE_WECHAT_MINI_PROGRAM,
                "source_identity": (
                    "xiaoetong:appsnm3rlcp3566:l_6a708838e4b0694c5bf42e55"
                ),
                "live_id": "l_6a708838e4b0694c5bf42e55",
                "page_state": "mini_program_media_observed",
                "activated": True,
                "playback_window_closed": True,
                "media_request_observed": True,
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
        clock=lambda: datetime.fromisoformat("2026-08-04T23:00:00+08:00"),
    )
    first = subscription.run_once(
        opencli_session="xiaocao-lv-subscription",
    )
    assert first["status"] == "waiting"
    assert [request["action"] for request in browser_requests] == [
        "resolve_xiaoetong_page",
        "activate_xiaoetong_mini_program",
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
        "activate_xiaoetong_mini_program",
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


def test_live_driver_preserves_original_message_date_before_advance(tmp_path):
    from xiaocao.kol.xiaocao_live import XiaocaoLiveService
    original_time = "2026-09-23T17:07:00+08:00"
    root = tmp_path / "wechat"
    service = XiaocaoLiveService(root / "item", capture_ledger=root / "capture.jsonl")
    capture = service.capture_store.arm([])
    manifest = {"items": {"original": {"capture_job_id": capture["job_id"],
        "published_at": original_time, "message_sha256": "a" * 64}}}
    (root / "manifest.json").write_text(json.dumps(manifest))
    observed = []
    service.start = lambda: None
    service.advance = lambda *a, **k: observed.append(service.capture_store.latest(capture["job_id"])) or {}
    driver = XiaocaoLiveCaptureDriver(root, service_factory=lambda *a, **k: service)
    driver.advance("original", capture["job_id"], opencli_session="existing", opencli_profile=None)
    assert observed[0]["source_published_at"] == original_time
    assert observed[0]["source_event_date"] == "2026-09-23"
    assert observed[0]["source_message_sha256"] == "a" * 64
    manifest["items"]["original"]["published_at"] = "2026-09-29T17:07:00+08:00"
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(EnrichmentError, match="publication evidence changed"):
        driver.advance("original", capture["job_id"], opencli_session="existing", opencli_profile=None)
    assert len(observed) == 1


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
        clock=lambda: datetime.fromisoformat("2026-08-06T23:00:00+08:00"),
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


@pytest.mark.parametrize("age_hours,eligible,expected", [(71, True, False), (72, True, True), (96, False, False)])
def test_expiry_preserves_recent_and_claimed_waits(tmp_path, age_hours, eligible, expected):
    from datetime import timedelta
    now = datetime.fromisoformat("2026-09-08T15:00:00+08:00")
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path, history_reader=lambda: {}, browser_exchange=lambda r: r,
        capture_driver=SimpleNamespace(can_expire_wait=lambda identity, job: eligible),
        clock=lambda: now,
    )
    item = {"identity": "old", "published_at": (now-timedelta(hours=age_hours)).isoformat(),
            "status": "awaiting_playback", "capture_job_id": "same-job"}
    manifest = {"schema_version": 1, "items": {"old": item}}
    assert subscription.expire_stale_waits(manifest) == (["old"] if expected else [])
    assert manifest["items"]["old"]["capture_job_id"] == "same-job"
    if expected:
        assert subscription._next_pending(manifest) is None
        assert subscription.expire_stale_waits(manifest) == []


@pytest.mark.parametrize("fields", [{}, {"candidate_id": "media"}, {"source_job_id": "source"}, {"expected_source": {"id": "live"}}, {"status": "downloading"}])
def test_expiry_driver_requires_unbound_idle_ledger(tmp_path, fields):
    row = {"status": "awaiting_capture", **fields}
    driver = XiaocaoLiveCaptureDriver(tmp_path, service_factory=lambda *a, **k:
        SimpleNamespace(capture_store=SimpleNamespace(latest=lambda job: row)))
    assert driver.can_expire_wait("same", "job") is (not fields)


def test_course_preview_is_retained_without_capture_or_repeated_resolution(tmp_path):
    calls = []
    driver = _CaptureDriver()
    def exchange(request):
        calls.append(request)
        return {"action": request["action"], "subscription_id": request["subscription_id"],
                "page_state": "unknown", "page_url": "https://appsnm3rlcp3566.h5.xiaoeknow.com/p/course/ecourse/preview/course_abc?share=private"}
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path, history_reader=lambda: _history("[2026-09-15 07:00] 福利官小花四: https://yv9lc.xetslk.com/s/3KML8K"),
        browser_exchange=exchange, capture_driver=driver,
        clock=lambda: datetime.fromisoformat("2026-09-15T08:00:00+08:00"),
    )
    result = subscription.run_once(opencli_session="test")
    assert result["unsupported_resource"] is True
    assert driver.arms == []
    saved = subscription._load()["items"][result["identity"]]
    assert saved["message_sha256"]
    assert "?" not in saved["page_url"]
    assert subscription.run_once(opencli_session="test")["status"] == "no_update"
    assert subscription.run_once(opencli_session="test", only_identity=result["identity"])["already_completed"] is False
    assert len(calls) == 1


def test_exact_item_resume_accepts_a_unique_source_identity(tmp_path):
    source_identity = "xiaoetong:appsnm3rlcp3566:l_6aa79dc4e4b0694c5c09eba7"
    manifest_identity = "kol-wechat-current"
    subscription = XiaocaoWechatLiveSubscription(
        tmp_path,
        history_reader=lambda: (_ for _ in ()).throw(
            AssertionError("exact resume must not rescan WeChat")
        ),
        browser_exchange=lambda request: request,
        capture_driver=_CaptureDriver(),
        clock=lambda: datetime.fromisoformat("2026-09-19T10:30:00+08:00"),
    )
    subscription._save({
        "schema_version": 1,
        "items": {
            manifest_identity: {
                "identity": manifest_identity,
                "source_identity": source_identity,
                "published_at": "2026-09-19T08:00:00+08:00",
                "status": "completed",
            }
        },
    })

    result = subscription.run_once(
        opencli_session="test",
        only_identity=source_identity,
    )

    assert result == {
        "status": "no_update",
        "identity": manifest_identity,
        "already_completed": True,
        "unsupported_resource": False,
        "unsupported_application": False,
    }
