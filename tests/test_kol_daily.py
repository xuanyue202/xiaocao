from __future__ import annotations

import hashlib
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from scripts import kol_daily as kol_daily_script
from scripts.kol_daily import (
    _classified_source,
    _latest_lv_video_goal,
    _video_publication_context,
    DailyRuntime,
)
from xiaocao.kol.daily import (
    build_triggered_evaluation_candidate,
    DailyCoordinator,
    DailyError,
    DailyPublicationContext,
    DailyPublicationPipeline,
    TransientSourceError,
    triggered_evaluation_terminal,
    UserActionBlocker,
)
from xiaocao.kol.enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
)
from xiaocao.kol.household import LiangHuiMcpError
from xiaocao.kol.publication import (
    PublicationLedger,
    build_record,
    publication_id_for_source,
    report_id,
    viewpoint_id,
)


class Clock:
    def __init__(self, value: str):
        self.value = datetime.fromisoformat(value)

    def __call__(self) -> datetime:
        return self.value


def _canonical_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def test_xiaocao_runtime_imports_portable_handoff_before_status(
    tmp_path,
    monkeypatch,
):
    handoff_dir = tmp_path / "xiaocao" / "handoffs"
    handoff_dir.mkdir(parents=True)
    media_sha256 = "a" * 64
    handoff_id = "b" * 64
    job_id = f"kol-netdisk-{media_sha256[:16]}"
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
        "cloud_reference": "baidu:/课程/自己的课/小草/target-compressed.mp4",
        "provider": "baidu_consumer_page",
        "large_payload_local_bytes": 0,
        "published_at": "2026-08-01T19:45:00+08:00",
        "netdisk_job_snapshot": snapshot,
        "netdisk_job_snapshot_sha256": _canonical_sha256(snapshot),
    }
    capsule["handoff_sha256"] = _canonical_sha256(capsule)
    (handoff_dir / "kol-capture-test.json").write_text(
        json.dumps(capsule, ensure_ascii=False),
        encoding="utf-8",
    )
    calls: list[str] = []

    class FakeNetdisk:
        def status(self, requested_job_id):
            assert requested_job_id == job_id
            assert calls == ["import"]
            return {"status": "decided", "job_id": job_id}

    class FakeService:
        def __init__(self, *_args, **_kwargs):
            self.netdisk = FakeNetdisk()

        def import_handoff_capsule(self, value):
            assert value == capsule
            calls.append("import")
            return {"status": "video_ready", "job_id": job_id}

    monkeypatch.setattr(kol_daily_script, "XiaocaoLiveService", FakeService)
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        xiaocao_output_dir=tmp_path / "xiaocao",
        decision_output_dir=tmp_path / "decisions",
        enrichment_session="xiaocao-lv-subscription",
        opencli_profile=None,
    )

    assert runtime.xiaocao() == {"status": "no_update"}
    assert calls == ["import"]


def test_daily_runner_is_silent_outside_beijing_daytime_window(tmp_path):
    calls: list[str] = []
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T06:59:00+08:00"),
    )

    result = service.run(
        [{"name": "lv", "priority": 10, "run": lambda: calls.append("lv")}]
    )

    assert result == {
        "status": "outside_window",
        "silent": True,
        "beijing_time": "2026-07-27T06:59:00+08:00",
    }
    assert calls == []
    assert not service.events_path.exists()


def test_daily_runner_records_one_short_lived_no_update_sweep(tmp_path):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T07:00:00+08:00"),
    )

    result = service.run(
        [
            {
                "name": "lv",
                "priority": 10,
                "run": lambda: {"status": "no_update"},
            },
            {
                "name": "lucifer",
                "priority": 20,
                "run": lambda: {"status": "no_update"},
            },
        ]
    )

    assert result["status"] == "completed"
    assert result["silent"] is True
    assert result["source_results"] == [
        {"name": "lv", "status": "no_update"},
        {"name": "lucifer", "status": "no_update"},
    ]
    assert service.status()["last_sweep"]["status"] == "completed"
    assert service.status()["last_sweep"]["health"] == "healthy"
    assert service.status()["last_sweep"]["source_states"] == [
        {"name": "lv", "status": "no_update"},
        {"name": "lucifer", "status": "no_update"},
    ]
    assert service.audit()["coordinator_source_video_bytes"] == 0


def test_daily_status_preserves_specific_video_waiting_stage(tmp_path):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T10:00:00+08:00"),
    )
    waiting_item = {
        "identity": "latest",
        "version_key": "version-2",
        "name": "底层逻辑7月29日.mp4",
        "author": "吕晓彤",
        "status": "waiting_cloud_transfer_receipt",
        "stage": "cloud_transfer_confirmation",
        "trigger_attempt": 2,
        "next_poll_not_before": "2026-07-27T10:30:00+08:00",
        "reconciliation_status": "exact_private_copy_absent",
    }

    result = service.run([
        {
            "name": "subscription_video",
            "priority": 20,
            "run": lambda: {
                "status": "waiting",
                "waiting_count": 1,
                "waiting_items": [waiting_item],
            },
        }
    ])

    assert result["health"] == "waiting"
    assert result["source_results"][0]["waiting_items"] == [waiting_item]
    assert service.status()["last_sweep"]["source_states"] == [{
        "name": "subscription_video",
        "status": "waiting",
        "waiting_count": 1,
        "waiting_items": [waiting_item],
    }]


def _low_density_event() -> dict:
    return {
        "kind": "source_event",
        "event_id": "lv-image-20260727",
        "author": "吕晓彤",
        "content_value": {
            "status": "low_density",
            "reason": "只有无作者归属的群聊情绪，没有投资决策主张。",
        },
        "gray_report": {"status": "not_created"},
        "alert": {"status": "not_created"},
        "book_kol_us": {
            "status": "no_trade",
            "book": "KOL-US",
            "paper_only": True,
            "reason": "没有可执行且可归属的美股主张。",
        },
        "coordinator_source_video_bytes": 0,
    }


def _promoted_event(*, event_id: str, tier: str) -> dict:
    report_url = f"https://reader.example/kol/{event_id}"
    alert = (
        {
            "status": "delivered",
            "receipt": f"wecom://{event_id}",
            "all_recipients": True,
            "stable_report_url": report_url,
            "stable_link_count": 1,
            "terminal_order": 2,
        }
        if tier == "alert_eligible"
        else {
            "status": "not_eligible",
            "reason": "历史方法论复核，没有当前行动触发。",
            "terminal_order": 2,
        }
    )
    return {
        "kind": "source_event",
        "event_id": event_id,
        "author": "小草",
        "content_value": {
            "status": "promoted",
            "tier": tier,
            "reason": "存在可归属且影响投资决策的完整判断。",
        },
        "gray_report": {
            "status": "published",
            "detail_url": report_url,
            "receipt": f"lianghui://{event_id}",
            "terminal_order": 1,
        },
        "alert": alert,
        "book_kol_us": {
            "status": "no_trade",
            "book": "KOL-US",
            "paper_only": True,
            "reason": "本场只讨论 A 股。",
            "terminal_order": 3,
        },
        "coordinator_source_video_bytes": 0,
    }


def test_content_value_routes_low_report_only_and_alert_event_independently(
    tmp_path,
):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T08:00:00+08:00"),
    )
    events = [
        _low_density_event(),
        _promoted_event(event_id="xiaocao-report-only", tier="report_only"),
        _promoted_event(event_id="xiaocao-alert", tier="alert_eligible"),
    ]

    result = service.run(
        [{
            "name": "accepted-sources",
            "priority": 10,
            "run": lambda: {"status": "completed", "events": events},
        }]
    )
    audit = service.audit()

    assert result["silent"] is False
    assert audit["content_value_counts"] == {
        "low_density": 1,
        "promoted": 2,
    }
    assert audit["promoted_tier_counts"] == {
        "alert_eligible": 1,
        "report_only": 1,
    }
    assert audit["gray_report_count"] == 2
    assert audit["reminder_count"] == 1
    assert audit["book_trade_count"] == 0
    assert audit["event_ids"] == [
        "lv-image-20260727",
        "xiaocao-report-only",
        "xiaocao-alert",
    ]


def test_promoted_event_fails_closed_when_book_precedes_gray_report(tmp_path):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T09:00:00+08:00"),
    )
    event = _promoted_event(event_id="wrong-order", tier="alert_eligible")
    event["book_kol_us"]["terminal_order"] = 0

    with pytest.raises(DailyError, match="gray report must precede"):
        service.run(
            [{
                "name": "source",
                "run": lambda: {"status": "completed", "events": [event]},
            }]
        )


class _Book:
    account = {"book": "KOL-US", "paper_only": True}


class _DelegatePipeline:
    def __init__(self, order: list[str]):
        self.book = _Book()
        self.order = order

    def process(self, bundle):
        self.order.append("book")
        item = dict(bundle["items"][0])
        item["notification"] = {
            "idempotency_key": "notify-event",
            "status": "pending",
        }
        item["book_kol_us"] = {
            "status": "no_trade",
            "book": "KOL-US",
            "paper_only": True,
            "reason": "本场只讨论 A 股。",
        }
        return {
            "status": "completed",
            "items": [item],
            "cross_source": {"agreements": [], "conflicts": []},
        }

    def deliver_wechat(self, result, *, sender):
        self.order.append("alert")
        response = sender("legacy", "legacy")
        assert response == {"wecom": "ok"}
        result["items"][0]["notification"].update(
            {"status": "delivered", "receipt": "wecom://notify-event"}
        )
        return {"status": "delivered"}


class _PublicationClient:
    def __init__(self, order: list[str]):
        self.order = order
        self.receipts: dict[str, dict] = {}

    def call_tool(self, name, arguments):
        if name == "get_kol_write_status":
            receipt = self.receipts.get(arguments["idempotency_key"])
            if receipt is None:
                raise LiangHuiMcpError("missing", code="NOT_FOUND")
            return receipt
        if name == "put_kol_record":
            receipt = {
                "recordState": "staged",
                "idempotencyKey": arguments["idempotency_key"],
            }
            self.receipts[arguments["idempotency_key"]] = receipt
            return receipt
        if name == "publish_kol_report":
            self.order.append("gray")
            receipt = {
                "recordState": "published",
                "idempotencyKey": arguments["idempotency_key"],
                "detailUrl": "https://reader.example/kol/report-first",
            }
            self.receipts[arguments["idempotency_key"]] = receipt
            return receipt
        raise AssertionError(name)


def _publication_bundle(tier: str = "alert_eligible") -> dict:
    return {
        "items": [{
            "author": "小草",
            "title": "早盘轮动与仓位边界",
            "published_at": "2026-07-27T09:30:00+08:00",
            "evidence_sha256": "a" * 64,
            "content_value": {
                "status": "promoted",
                "tier": tier,
                "reason": "含当前市场姿态与仓位边界。",
                "alert_basis": ["market_posture", "position_boundary"],
            },
            "reader_insight": {
                "status": "useful",
                "summary": "轮动仍乱，趋势与断板都只用轻仓。",
                "boundary": "盘中判断需由价格与承接继续验证。",
            },
            "publication": {
                "summary": "轮动仍乱，趋势与断板都只用轻仓。",
                "report_body": (
                    "# 核心判断\n\n轮动仍乱，趋势与断板都只用轻仓。\n\n"
                    "## 风险边界\n\n盘中判断需由价格与承接继续验证。"
                ),
                "remaining_summary": "不机械按钟点交易，优先观察流动性与强弱。",
            },
        }]
    }


def test_publication_pipeline_publishes_before_book_and_one_link_reminder(
    tmp_path,
):
    order: list[str] = []
    sent: list[tuple[str, str]] = []
    pipeline = DailyPublicationPipeline(
        _DelegatePipeline(order),
        ledger=PublicationLedger(tmp_path / "publication"),
        client=_PublicationClient(order),
        context=DailyPublicationContext(
            adapter="xiaocao_live",
            source_identity="live-20260727-am",
            publication_version="transcript-v1",
            kol_id="kol-xiaocao",
            source="小草直播",
            source_published_at="2026-07-27T09:30:00+08:00",
            media_types=("video",),
            source_parts=({
                "identity": "handoff-1",
                "version": "transcript-v1",
                "order": 1,
                "size": 0,
                "evidence_sha256": "a" * 64,
            },),
        ),
    )

    bundle = _publication_bundle()
    bundle["items"][0]["title"] = (
        "20260802 大师班专场(晚18：00开播)-compressed.mp4"
    )
    bundle["items"][0]["reader_title"] = (
        "8月2日大师班专场：弱轮动下的周一剧本与10%试错纪律"
    )
    result = pipeline.process(bundle)
    delivery = pipeline.deliver_wechat(
        result,
        sender=lambda title, body: (
            sent.append((title, body)) or {"wecom": "ok"}
        ),
    )

    assert order == ["gray", "book", "alert"]
    assert delivery["status"] == "delivered"
    assert len(sent) == 1
    assert sent[0][0] == (
        "投资情报｜小草：8月2日大师班专场："
        "弱轮动下的周一剧本与10%试错纪律"
    )
    assert sent[0][1].count("https://") == 1
    assert sent[0][1].endswith(
        "https://reader.example/kol/report-first"
    )
    terminal = result["items"][0]["daily_terminal"]
    assert terminal["source_binding"] == {
        "source_identity": "live-20260727-am",
        "publication_version": "transcript-v1",
    }
    assert terminal["gray_report"]["terminal_order"] == 1
    assert terminal["book_kol_us"]["terminal_order"] == 2
    assert terminal["alert"]["terminal_order"] == 3
    publication_key = publication_id_for_source(
        adapter="xiaocao_live",
        source_identity="live-20260727-am",
    )
    prepared = pipeline.ledger.status(publication_key)
    assert prepared["artifact"]["records"][0]["payload"]["title"] == (
        "8月2日大师班专场：弱轮动下的周一剧本与10%试错纪律"
    )
    assert prepared["artifact"]["records"][0]["created_at"] == (
        "2026-07-27T01:30:00Z"
    )


def test_video_publication_context_uses_request_time_and_evidence_hash():
    context = _video_publication_context(
        {
            "author": "吕晓彤",
            "identity": "latest-lv-video",
            "modified_at": 1785318030,
            "size": 5_217_837_384,
            "source": "baidu_subscription_share_browser",
            "version_key": "latest-lv-version",
        },
        {
            "publication_time": "2026-07-29T00:00:00+08:00",
            "evidence_sha256": "a" * 64,
        },
    )

    assert context.source_published_at == "2026-07-29T00:00:00+08:00"
    assert context.source_parts[0]["evidence_sha256"] == "a" * 64


def test_latest_lv_video_closes_only_on_bound_report_publication(tmp_path):
    video_output = tmp_path / "videos"
    video_output.mkdir()
    (video_output / "manifest.json").write_text(
        json.dumps({
            "items": {
                "latest": {
                    "author": "吕晓彤",
                    "identity": "latest-lv-video",
                    "media_type": "video",
                    "modified_at": 200,
                    "name": "底层逻辑7月29日.mp4",
                    "present": True,
                    "version_key": "latest-lv-version",
                    "work_eligible": False,
                },
            },
        }),
        encoding="utf-8",
    )
    order: list[str] = []
    pipeline = DailyPublicationPipeline(
        _DelegatePipeline(order),
        ledger=PublicationLedger(tmp_path / "publication"),
        client=_PublicationClient(order),
        context=DailyPublicationContext(
            adapter="subscription_video",
            source_identity="latest-lv-video",
            publication_version="latest-lv-version",
            kol_id="kol-lv-xiaotong",
            source="吕晓彤订阅",
            source_published_at="2026-07-29T17:40:30+08:00",
            media_types=("video",),
            source_parts=({
                "identity": "latest-lv-video",
                "version": "latest-lv-version",
                "order": 1,
                "size": 5_217_837_384,
                "evidence_sha256": "a" * 64,
            },),
        ),
    )

    result = pipeline.process(_publication_bundle())
    pipeline.deliver_wechat(
        result,
        sender=lambda _title, _body: {"wecom": "ok"},
    )
    terminal = result["items"][0]["daily_terminal"]
    goal = _latest_lv_video_goal(
        video_output,
        [{
            "event": "source_completed",
            "slot": "2026-07-30T12:00+08:00",
            "result": {"events": [terminal]},
        }],
    )

    assert order == ["gray", "book", "alert"]
    assert goal["status"] == "succeeded"
    assert goal["success"] is True
    assert goal["stage"] == "report_published"
    assert goal["report_receipt"]
    assert goal["report_url"] == (
        "https://reader.example/kol/report-first"
    )


def test_interrupted_sweep_resumes_only_unfinished_source(tmp_path):
    clock = Clock("2026-07-27T10:00:00+08:00")
    service = DailyCoordinator(tmp_path / "daily", now=clock)
    calls = {"first": 0, "second": 0}

    def first():
        calls["first"] += 1
        return {"status": "completed", "events": [_low_density_event()]}

    def interrupted():
        calls["second"] += 1
        raise RuntimeError("forced interruption")

    with pytest.raises(RuntimeError, match="forced interruption"):
        service.run(
            [
                {"name": "first", "priority": 10, "run": first},
                {"name": "second", "priority": 20, "run": interrupted},
            ]
        )

    result = service.run(
        [
            {"name": "first", "priority": 10, "run": first},
            {
                "name": "second",
                "priority": 20,
                "run": lambda: (
                    calls.__setitem__("second", calls["second"] + 1)
                    or {"status": "no_update"}
                ),
            },
        ]
    )

    assert calls == {"first": 1, "second": 2}
    assert result["status"] == "completed"
    assert service.audit()["content_value_counts"]["low_density"] == 1
    assert service.audit()["interruption_count"] == 1


def test_user_blocker_notifies_once_until_state_changes(tmp_path):
    clock = Clock("2026-07-27T11:00:00+08:00")
    service = DailyCoordinator(tmp_path / "daily", now=clock)
    notices: list[tuple[str, str]] = []

    def blocked():
        raise UserActionBlocker(
            "lv-share-login",
            "请重新登录百度网盘并保持已授权分享页可访问。",
        )

    for hour in (11, 12):
        clock.value = datetime.fromisoformat(
            f"2026-07-27T{hour:02d}:00:00+08:00"
        )
        result = service.run(
            [{"name": "lv", "run": blocked}],
            blocker_sender=lambda title, body: notices.append((title, body)),
        )
        assert result["silent"] is True

    clock.value = datetime.fromisoformat("2026-07-27T13:00:00+08:00")

    def changed():
        raise UserActionBlocker(
            "lv-share-expired",
            "请更新吕晓彤唯一分享链接和提取码。",
        )

    service.run(
        [{"name": "lv", "run": changed}],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )
    clock.value = datetime.fromisoformat("2026-07-27T14:00:00+08:00")
    service.run([{"name": "lv", "run": lambda: {"status": "no_update"}}])
    clock.value = datetime.fromisoformat("2026-07-27T15:00:00+08:00")
    service.run(
        [{"name": "lv", "run": changed}],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )

    assert len(notices) == 3
    assert notices[0][1] == "请重新登录百度网盘并保持已授权分享页可访问。"
    assert notices[1][1] == "请更新吕晓彤唯一分享链接和提取码。"
    assert notices[2][1] == "请更新吕晓彤唯一分享链接和提取码。"
    assert service.audit()["operational_reminder_count"] == 3


def test_transient_source_failure_is_structured_and_does_not_notify(tmp_path):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T14:00:00+08:00"),
    )
    notices = []

    result = service.run(
        [{
            "name": "lucifer",
            "run": lambda: (_ for _ in ()).throw(
                TransientSourceError(
                    "provider temporarily unavailable",
                    category="timeout",
                    code="opencli_timeout",
                    stage="browser_eval",
                )
            ),
        }],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )

    assert result["silent"] is False
    assert result["health"] == "degraded"
    assert result["source_results"] == [{
        "name": "lucifer",
        "status": "waiting",
        "retryable": True,
        "failure": {
            "category": "timeout",
            "code": "opencli_timeout",
            "stage": "browser_eval",
            "retryable": True,
        },
    }]
    assert notices == []
    status = service.status()
    assert status["status"] == "degraded"
    assert status["last_sweep"]["health"] == "degraded"
    audit = service.audit()
    assert audit["status"] == "degraded"
    assert audit["safety_status"] == "accepted"
    assert audit["operational_status"] == "degraded"
    assert audit["latest_failures"] == [{
        "source": "lucifer",
        "category": "timeout",
        "code": "opencli_timeout",
        "stage": "browser_eval",
        "retryable": True,
    }]
    assert audit["transient_failure_count"] == 1
    assert "provider temporarily unavailable" not in (
        service.events_path.read_text(encoding="utf-8")
    )

    calls = 0

    def recovered():
        nonlocal calls
        calls += 1
        return {"status": "no_update"}

    service.run([{"name": "lucifer", "run": recovered}])
    assert calls == 1
    assert service.status()["status"] == "ready"
    assert service.status()["last_sweep"]["health"] == "healthy"


def test_source_classifier_preserves_safe_timeout_diagnostic():
    runner = _classified_source(
        "lv_text_image",
        lambda: (_ for _ in ()).throw(
            EnrichmentDiagnosticError(
                "private provider details must not enter the ledger",
                category="timeout",
                code="opencli_timeout",
                stage="browser_eval",
            )
        ),
    )

    with pytest.raises(TransientSourceError) as captured:
        runner()

    assert captured.value.diagnostic() == {
        "category": "timeout",
        "code": "opencli_timeout",
        "stage": "browser_eval",
        "retryable": True,
    }


def test_source_classifier_promotes_provider_transfer_rejection_to_blocker():
    runner = _classified_source(
        "subscription_video",
        lambda: (_ for _ in ()).throw(
            EnrichmentError(
                "Lv cloud transfer was rejected by provider"
            )
        ),
    )

    with pytest.raises(UserActionBlocker) as captured:
        runner()

    assert captured.value.blocker_key == (
        "lv-cloud-transfer-provider-rejected"
    )
    assert "/课程/自己的课/吕晓彤" in captured.value.action


def test_status_classifies_legacy_retryable_failure_as_degraded(tmp_path):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T14:00:00+08:00"),
    )
    service.output_dir.mkdir(parents=True)
    service._append("sweep_started", slot="2026-07-27T14:00+08:00")
    service._append(
        "source_retryable_failure",
        slot="2026-07-27T14:00+08:00",
        source="lv_text_image",
        error_type="TransientSourceError",
    )
    service._append(
        "source_completed",
        slot="2026-07-27T14:00+08:00",
        source="lv_text_image",
        result={"status": "waiting", "retryable": True},
        coordinator_source_video_bytes=0,
    )
    service._append(
        "sweep_completed",
        slot="2026-07-27T14:00+08:00",
        status="completed",
        source_count=1,
        coordinator_source_video_bytes=0,
    )

    status = service.status()

    assert status["status"] == "degraded"
    assert status["last_sweep"]["source_states"][0]["failure"]["code"] == (
        "legacy_unclassified_failure"
    )


def test_latest_lv_video_goal_requires_matching_version_and_report_receipt(
    tmp_path,
):
    video_output = tmp_path / "videos"
    video_output.mkdir()
    (video_output / "manifest.json").write_text(
        json.dumps({
            "items": {
                "latest": {
                    "author": "吕晓彤",
                    "identity": "latest",
                    "media_type": "video",
                    "modified_at": 200,
                    "name": "底层逻辑7月29日.mp4",
                    "present": True,
                    "version_key": "version-2",
                    "work_eligible": True,
                },
                "older": {
                    "author": "吕晓彤",
                    "identity": "older",
                    "media_type": "video",
                    "modified_at": 100,
                    "name": "7月20日.mp4",
                    "present": True,
                    "version_key": "version-1",
                    "work_eligible": False,
                },
            },
        }),
        encoding="utf-8",
    )

    pending = _latest_lv_video_goal(video_output, [])

    assert pending == {
        "status": "pending",
        "success": False,
        "stage": "source_acquisition",
        "identity": "latest",
        "version_key": "version-2",
        "name": "底层逻辑7月29日.mp4",
        "modified_at": 200,
    }

    (video_output / "claims").mkdir()
    (video_output / "claims" / "lv_transfer_version-2.json").write_text(
        json.dumps({
            "status": "waiting_cloud_transfer_receipt",
            "source_identity": "latest",
            "source_version_key": "version-2",
            "trigger_attempt": 2,
            "triggered_at": "2026-07-30T09:41:06+08:00",
            "next_poll_not_before": "2026-07-30T10:11:06+08:00",
            "reconciliation_status": "exact_private_copy_absent",
        }),
        encoding="utf-8",
    )

    processing = _latest_lv_video_goal(video_output, [])

    assert processing["status"] == "processing"
    assert processing["stage"] == "cloud_transfer_confirmation"
    assert processing["transfer_status"] == (
        "waiting_cloud_transfer_receipt"
    )
    assert processing["trigger_attempt"] == 2
    assert processing["next_poll_not_before"] == (
        "2026-07-30T10:11:06+08:00"
    )

    (video_output / "claims" / "lv_transfer_version-2.json").write_text(
        json.dumps({
            "status": "blocked",
            "stage": "cloud_transfer_confirmation",
            "source_identity": "latest",
            "source_version_key": "version-2",
            "trigger_attempt": 2,
            "blocker_key": "lv-cloud-transfer-not-materialized",
            "failure_reason": (
                "two confirmed transfer attempts produced no exact private copy"
            ),
            "reconciliation_status": (
                "exact_private_copy_absent_after_bounded_retry"
            ),
            "blocked_at": "2026-07-30T10:11:17+08:00",
        }),
        encoding="utf-8",
    )

    blocked = _latest_lv_video_goal(video_output, [])

    assert blocked["status"] == "blocked"
    assert blocked["success"] is False
    assert blocked["user_action_required"] is True
    assert blocked["blocker_key"] == (
        "lv-cloud-transfer-not-materialized"
    )
    assert blocked["reconciliation_status"] == (
        "exact_private_copy_absent_after_bounded_retry"
    )

    succeeded = _latest_lv_video_goal(
        video_output,
        [{
            "event": "source_completed",
            "slot": "2026-07-30T07:00+08:00",
            "result": {
                "events": [{
                    "kind": "source_event",
                    "event_id": "latest",
                    "source_binding": {
                        "source_identity": "latest",
                        "publication_version": "version-2",
                    },
                    "gray_report": {
                        "status": "published",
                        "receipt": "receipt-1",
                        "detail_url": "https://report.example/latest",
                    },
                }],
            },
        }],
    )

    assert succeeded["status"] == "succeeded"
    assert succeeded["success"] is True
    assert succeeded["analysis_status"] == "completed"
    assert succeeded["report_status"] == "published"
    assert succeeded["report_receipt"] == "receipt-1"
    assert succeeded["report_url"] == "https://report.example/latest"


def test_latest_lv_video_goal_rejects_report_for_stale_version(tmp_path):
    video_output = tmp_path / "videos"
    video_output.mkdir()
    (video_output / "manifest.json").write_text(
        json.dumps({
            "items": {
                "latest": {
                    "author": "吕晓彤",
                    "identity": "latest",
                    "media_type": "video",
                    "modified_at": 200,
                    "name": "底层逻辑7月29日.mp4",
                    "present": True,
                    "version_key": "version-2",
                    "work_eligible": True,
                },
            },
        }),
        encoding="utf-8",
    )
    events = [{
        "event": "source_completed",
        "slot": "2026-07-29T23:00+08:00",
        "result": {
            "events": [{
                "kind": "source_event",
                "event_id": "latest",
                "source_binding": {
                    "source_identity": "latest",
                    "publication_version": "version-1",
                },
                "gray_report": {
                    "status": "published",
                    "receipt": "old-receipt",
                    "detail_url": "https://report.example/old",
                },
            }],
        },
    }]

    result = _latest_lv_video_goal(video_output, events)

    assert result["status"] == "pending"
    assert result["success"] is False


def test_latest_lv_video_goal_recovers_from_bound_decision_result(tmp_path):
    video_output = tmp_path / "videos"
    video_output.mkdir()
    result_path = video_output / "latest-decision.json"
    result_path.write_text(
        json.dumps({
            "items": [{
                "daily_terminal": {
                    "kind": "source_event",
                    "event_id": "latest",
                    "source_binding": {
                        "source_identity": "latest",
                        "publication_version": "version-2",
                    },
                    "gray_report": {
                        "status": "published",
                        "receipt": "receipt-recovered",
                        "detail_url": "https://report.example/recovered",
                    },
                },
            }],
        }),
        encoding="utf-8",
    )
    result_sha256 = hashlib.sha256(result_path.read_bytes()).hexdigest()
    (video_output / "manifest.json").write_text(
        json.dumps({
            "items": {
                "latest": {
                    "author": "吕晓彤",
                    "identity": "latest",
                    "media_type": "video",
                    "modified_at": 200,
                    "name": "底层逻辑7月29日.mp4",
                    "present": True,
                    "version_key": "version-2",
                    "completed_version_key": "version-2",
                    "decision_result_path": str(result_path),
                    "decision_result_sha256": result_sha256,
                    "work_eligible": False,
                },
            },
        }),
        encoding="utf-8",
    )

    goal = _latest_lv_video_goal(video_output, [])

    assert goal["status"] == "succeeded"
    assert goal["success"] is True
    assert goal["report_receipt"] == "receipt-recovered"
    assert goal["report_url"] == "https://report.example/recovered"
    assert goal["coordinator_slot"] == (
        "recovered_from_decision_result"
    )


def test_triggered_viewpoint_evaluation_appends_without_event_side_effects(
    tmp_path,
):
    publication_id = publication_id_for_source(
        adapter="subscription_video",
        source_identity="lucifer-episode-1",
    )
    report_id_value = report_id(publication_id)
    source_binding = {
        "publication_id": publication_id,
        "publication_version": "episode-v1",
        "evidence_sha256": "a" * 64,
        "decision_result_sha256": "b" * 64,
        "extraction_contract_version": "kol-intelligence-v1",
    }
    refs = [{"claim_id": "claim-1", "excerpt": "至少保留一半现金"}]
    viewpoint_id_value = viewpoint_id(
        report_id_value,
        "cash-boundary",
        refs,
    )
    viewpoint = build_record(
        kind="viewpoint",
        record_id_value=viewpoint_id_value,
        idempotency_key="put-viewpoint",
        created_at="2026-07-20T08:00:00+08:00",
        source_binding=source_binding,
        payload={
            "viewpoint_id": viewpoint_id_value,
            "report_id": report_id_value,
            "kol_id": "kol-lucifer",
            "local_thesis_id": "cash-boundary",
            "subject": "现金仓位边界",
            "stance": "至少保留一半现金等待更好赔率",
            "source_published_at": "2026-07-20T07:30:00+08:00",
            "evidence_refs": refs,
        },
    )
    report = build_record(
        kind="report",
        record_id_value=report_id_value,
        idempotency_key="put-report",
        created_at="2026-07-20T08:00:00+08:00",
        source_binding=source_binding,
        payload={
            "report_id": report_id_value,
            "report_kind": "publication_event",
            "kol_id": "kol-lucifer",
            "author": "路西法",
            "source": "订阅直播",
            "title": "现金边界与等待赔率",
            "summary": "至少保留一半现金，等待风险资产赔率改善。",
            "source_published_at": "2026-07-20T07:30:00+08:00",
            "media_types": ["video"],
            "source_parts": [],
            "report_format": "markdown",
            "report_body": "# 核心判断\n\n至少保留一半现金。",
            "viewpoint_ids": [viewpoint_id_value],
            "alert_eligible": False,
            "alert_reason": "historical_initialization_no_alert",
            "reader_insight": {"status": "useful", "reason": "长期仓位边界"},
        },
    )

    candidate = build_triggered_evaluation_candidate(
        {
            "report": report,
            "records": [report, viewpoint],
            "content_sha256": report["content_sha256"],
        },
        {
            "trigger": "material_fact_change",
            "viewpoint_id": viewpoint_id_value,
            "status": "uncertain",
            "as_of": "2026-07-27T15:00:00+08:00",
            "evaluated_at": "2026-07-27T15:01:00+08:00",
            "basis": "新一期节目仍强调防守，但没有重申精确的一半现金比例。",
            "confidence": "medium",
            "uncertainties": ["缺少下一期完整仓位表。"],
        },
    )
    kinds = [row["kind"] for row in candidate["records"]]
    evaluation = next(
        row for row in candidate["records"]
        if row["kind"] == "viewpoint_evaluation"
        and row["record_id"] == candidate["metadata"]["evaluation_id"]
    )

    assert kinds.count("report") == 1
    assert kinds.count("viewpoint") == 1
    assert kinds.count("viewpoint_evaluation") == 1
    assert evaluation["created_at"] == "2026-07-27T07:01:00Z"
    assert evaluation["payload"]["as_of"] == "2026-07-27T07:00:00Z"
    assert evaluation["payload"]["evaluated_at"] == "2026-07-27T07:01:00Z"
    assert candidate["metadata"]["notification_claim_authorized"] is False
    assert candidate["metadata"]["book_kol_us_replay_authorized"] is False
    terminal = triggered_evaluation_terminal(
        candidate,
        {
            "completed": True,
            "publish_receipt": {
                "recordState": "published",
                "detailUrl": "https://reader.example/kol/lucifer-episode-1",
            },
        },
    )
    assert terminal["history_preserved"] is True
    assert terminal["current_projection_order_preserved"] is True
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T15:00:00+08:00"),
    )
    service.run(
        [{
            "name": "viewpoint_maintenance",
            "run": lambda: {
                "status": "completed",
                "events": [terminal],
            },
        }]
    )
    assert service.audit()["viewpoint_evaluation_count"] == 1
    assert service.audit()["reminder_count"] == 0
    assert service.audit()["book_trade_count"] == 0


def test_replayed_terminal_receipt_is_recorded_once_across_hourly_slots(
    tmp_path,
):
    clock = Clock("2026-07-27T15:00:00+08:00")
    service = DailyCoordinator(tmp_path / "daily", now=clock)
    event = {
        "kind": "viewpoint_evaluation",
        "event_id": "ve-recovered-after-receipt",
        "trigger": "due_horizon",
        "gray_publication": {
            "status": "published",
            "detail_url": "https://reader.example/kol/recovered",
        },
        "history_preserved": True,
        "current_projection_order_preserved": True,
        "alert": {"status": "not_created"},
        "book_kol_us": {"status": "not_created"},
        "coordinator_source_video_bytes": 0,
    }
    source = {
        "name": "viewpoint_maintenance",
        "run": lambda: {"status": "completed", "events": [event]},
    }

    first = service.run([source])
    clock.value = datetime.fromisoformat("2026-07-27T16:00:00+08:00")
    replay = service.run([source])

    assert first["silent"] is False
    assert replay["silent"] is True
    assert replay["source_results"] == [{
        "name": "viewpoint_maintenance",
        "status": "no_update",
        "replayed_terminal_count": 1,
    }]
    assert service.audit()["viewpoint_evaluation_count"] == 1
