from __future__ import annotations

from datetime import datetime

import pytest

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
    assert service.audit()["coordinator_source_video_bytes"] == 0


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

    result = pipeline.process(_publication_bundle())
    delivery = pipeline.deliver_wechat(
        result,
        sender=lambda title, body: (
            sent.append((title, body)) or {"wecom": "ok"}
        ),
    )

    assert order == ["gray", "book", "alert"]
    assert delivery["status"] == "delivered"
    assert len(sent) == 1
    assert sent[0][1].count("https://") == 1
    assert sent[0][1].endswith(
        "https://reader.example/kol/report-first"
    )
    terminal = result["items"][0]["daily_terminal"]
    assert terminal["gray_report"]["terminal_order"] == 1
    assert terminal["book_kol_us"]["terminal_order"] == 2
    assert terminal["alert"]["terminal_order"] == 3


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


def test_transient_source_failure_is_silent_and_does_not_notify(tmp_path):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T14:00:00+08:00"),
    )
    notices = []

    result = service.run(
        [{
            "name": "lucifer",
            "run": lambda: (_ for _ in ()).throw(
                TransientSourceError("provider temporarily unavailable")
            ),
        }],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )

    assert result["silent"] is True
    assert notices == []
    assert service.audit()["transient_failure_count"] == 1

    calls = 0

    def recovered():
        nonlocal calls
        calls += 1
        return {"status": "no_update"}

    service.run([{"name": "lucifer", "run": recovered}])
    assert calls == 1


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
