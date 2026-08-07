from __future__ import annotations

import hashlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import kol_daily as kol_daily_script
from scripts.kol_daily import (
    _classified_source,
    _latest_lv_video_goal,
    _lv_publication_context,
    _video_publication_context,
    DailyRuntime,
    SemanticInputUnavailable,
)
from xiaocao.kol.daily import (
    build_initial_projection_candidate,
    build_triggered_evaluation_candidate,
    DailyCoordinator,
    DailyError,
    DailyPublicationContext,
    DailyPublicationPipeline,
    initial_projection_terminal,
    TransientSourceError,
    triggered_evaluation_terminal,
    UserActionBlocker,
    VIEWPOINT_EVALUATION_STATUSES,
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


@pytest.mark.parametrize(
    "handoff_parts",
    [
        ("wechat_subscription", "items", "kol-wechat-current", "handoffs"),
        ("imported_handoffs",),
    ],
)
def test_xiaocao_runtime_imports_portable_handoff_before_status(
    tmp_path,
    monkeypatch,
    handoff_parts,
):
    handoff_dir = tmp_path / "xiaocao"
    for part in handoff_parts:
        handoff_dir /= part
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


def test_xiaocao_runtime_upgrades_only_latest_decided_publication(tmp_path, monkeypatch):
    xiaocao_output = tmp_path / "xiaocao"
    handoff_dir = xiaocao_output / "imported_handoffs"
    handoff_dir.mkdir(parents=True)
    job_id = "kol-netdisk-current"
    handoff = {
        "schema_version": 1,
        "handoff_id": "a" * 64,
        "capture_job_id": "kol-current",
        "netdisk_job_id": job_id,
        "published_at": "2026-08-06T16:00:00+08:00",
        "large_payload_local_bytes": 0,
    }
    handoff["handoff_sha256"] = _canonical_sha256(handoff)
    (handoff_dir / "kol-current.json").write_text(
        json.dumps(handoff),
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text('{"items": []}', encoding="utf-8")
    prior_result = tmp_path / "prior-result.json"
    prior_result.write_text(
        '{"status": "completed", "items": [{}]}',
        encoding="utf-8",
    )
    upgraded_result = tmp_path / "upgraded-result.json"
    upgraded_result.write_text(
        json.dumps({
            "status": "completed",
            "items": [{
                "daily_terminal": {
                    "kind": "source_event",
                    "gray_report": {"status": "published"},
                },
            }],
        }),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    class FakeNetdisk:
        def status(self, requested_job_id):
            assert requested_job_id == job_id
            return {
                "status": "decided",
                "decision_result_path": str(prior_result),
                "decision_bundle_path": str(bundle),
                "decision_bundle_sha256": hashlib.sha256(
                    bundle.read_bytes()
                ).hexdigest(),
                "transcript_sha256": "b" * 64,
            }

        def decide(self, requested_job_id, **kwargs):
            assert requested_job_id == job_id
            calls.append(kwargs)
            return {"decision_result_path": str(upgraded_result)}

    class FakeService:
        def __init__(self, *_args, **_kwargs):
            self.netdisk = FakeNetdisk()

    monkeypatch.setattr(kol_daily_script, "XiaocaoLiveService", FakeService)
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        xiaocao_output_dir=xiaocao_output,
        decision_output_dir=tmp_path / "decisions",
        enrichment_session="xiaocao-lv-subscription",
        opencli_profile=None,
    )
    pipeline = object()
    runtime._pipeline = lambda _context: pipeline

    result = runtime.xiaocao()

    assert result["status"] == "completed"
    assert result["events"][0]["gray_report"]["status"] == "published"
    assert len(calls) == 1
    assert calls[0]["pipeline"] is pipeline
    assert calls[0]["reconcile_daily_terminal"] is True


def test_daily_runtime_runs_xiaocao_wechat_subscription(tmp_path, monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeHistoryReader:
        def __init__(self, contact, *, executable, limit):
            calls.append(("reader", (contact, executable, limit)))

        def __call__(self):
            return {"messages": []}

    class FakeCaptureDriver:
        def __init__(self, output_dir, *, decision_output):
            calls.append(("capture", (output_dir, decision_output)))

    class FakeSubscription:
        def __init__(
            self,
            output_dir,
            *,
            history_reader,
            browser_exchange,
            capture_driver,
            contact,
            password,
        ):
            assert callable(history_reader)
            assert callable(browser_exchange)
            assert isinstance(capture_driver, FakeCaptureDriver)
            calls.append(("subscription", (output_dir, contact, password)))

        def run_once(self, *, opencli_session, opencli_profile=None):
            calls.append(("run", (opencli_session, opencli_profile)))
            return {"status": "no_update"}

    monkeypatch.setattr(
        kol_daily_script, "WechatCliHistoryReader", FakeHistoryReader
    )
    monkeypatch.setattr(
        kol_daily_script, "XiaocaoLiveCaptureDriver", FakeCaptureDriver
    )
    monkeypatch.setattr(
        kol_daily_script, "XiaocaoWechatLiveSubscription", FakeSubscription
    )
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        xiaocao_wechat_output_dir=tmp_path / "wechat",
        xiaocao_wechat_contact="福利官小花四-刘丹",
        xiaocao_live_password="666",
        wechat_cli=tmp_path / "wechat-cli",
        wechat_history_limit=80,
        decision_output_dir=tmp_path / "decisions",
        enrichment_session="xiaocao-lv-subscription",
        opencli_profile=None,
    )

    assert runtime.xiaocao_wechat() == {"status": "no_update"}
    assert calls == [
        (
            "reader",
            (
                "福利官小花四-刘丹",
                tmp_path / "wechat-cli",
                80,
            ),
        ),
        ("capture", (tmp_path / "wechat", tmp_path / "decisions")),
        (
            "subscription",
            (tmp_path / "wechat", "福利官小花四-刘丹", "666"),
        ),
        ("run", ("xiaocao-lv-subscription", None)),
    ]


def test_capture_local_cli_runs_live_and_official_account_sources(
    tmp_path,
    monkeypatch,
):
    observed: dict[str, object] = {}

    class FakeCoordinator:
        def __init__(self, output_dir):
            observed["output_dir"] = output_dir

        def run(self, sources, *, blocker_sender):
            observed["source_names"] = [source["name"] for source in sources]
            observed["priorities"] = [source["priority"] for source in sources]
            observed["results"] = [source["run"]() for source in sources]
            assert callable(blocker_sender)
            return {"status": "completed", "silent": True}

    def capture(self):
        assert not hasattr(self, "client")
        return {"status": "no_update"}

    monkeypatch.setattr(kol_daily_script, "DailyCoordinator", FakeCoordinator)
    monkeypatch.setattr(DailyRuntime, "xiaocao_wechat", capture)
    monkeypatch.setattr(DailyRuntime, "wechat_official_local", capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kol_daily.py",
            "capture-local",
            "--output-dir",
            str(tmp_path / "daily"),
        ],
    )

    assert kol_daily_script.main() == 0
    assert observed == {
        "output_dir": tmp_path / "daily",
        "source_names": [
            "xiaocao_wechat_live",
            "wechat_official_accounts",
        ],
        "priorities": [10, 20],
        "results": [
            {"status": "no_update"},
            {"status": "no_update"},
        ],
    }


def test_capture_local_cli_follows_exact_cloud_handoff_in_same_process(
    tmp_path,
    monkeypatch,
):
    observed: dict[str, object] = {"coordinator_runs": 0, "follow_calls": []}

    class FakeCoordinator:
        def __init__(self, output_dir):
            assert output_dir == tmp_path / "daily"

        def run(self, sources, *, blocker_sender):
            observed["coordinator_runs"] = int(observed["coordinator_runs"]) + 1
            assert [source["name"] for source in sources] == [
                "xiaocao_wechat_live",
                "wechat_official_accounts",
            ]
            assert callable(blocker_sender)
            return {
                "status": "completed",
                "silent": True,
                "source_results": [{
                    "name": "xiaocao_wechat_live",
                    "status": "waiting",
                    "waiting_items": [{
                        "identity": "kol-wechat-current",
                        "capture_job_id": "kol-capture-current",
                        "status": "upload_claimed",
                        "stage": "cloud_handoff",
                    }],
                }, {
                    "name": "wechat_official_accounts",
                    "status": "no_update",
                }],
            }

    follow_results = iter([
        {
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [{
                "identity": "kol-wechat-current",
                "capture_job_id": "kol-capture-current",
                "status": "upload_claimed",
                "stage": "cloud_handoff",
            }],
        },
        {
            "status": "no_update",
            "handoff_dispatched": True,
            "identity": "kol-wechat-current",
            "capture_job_id": "kol-capture-current",
        },
    ])

    def follow(self, identity, capture_job_id):
        observed["follow_calls"].append((identity, capture_job_id))
        return next(follow_results)

    monkeypatch.setattr(kol_daily_script, "DailyCoordinator", FakeCoordinator)
    monkeypatch.setattr(
        DailyRuntime,
        "xiaocao_cloud_handoff",
        follow,
        raising=False,
    )
    monkeypatch.setattr(
        kol_daily_script,
        "_cloud_handoff_sleep",
        lambda seconds: observed.setdefault("sleeps", []).append(seconds),
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kol_daily.py",
            "capture-local",
            "--output-dir",
            str(tmp_path / "daily"),
        ],
    )

    assert kol_daily_script.main() == 0
    assert observed["coordinator_runs"] == 1
    assert observed["follow_calls"] == [
        ("kol-wechat-current", "kol-capture-current"),
        ("kol-wechat-current", "kol-capture-current"),
    ]
    assert observed["sleeps"] == [30]


def test_capture_wechat_official_cli_runs_only_local_official_account_source(
    tmp_path,
    monkeypatch,
    capsys,
):
    observed: dict[str, object] = {}

    def capture(self):
        assert not hasattr(self, "client")
        observed["args"] = self.args
        return {"status": "completed", "dispatched": 2}

    monkeypatch.setattr(DailyRuntime, "wechat_official_local", capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kol_daily.py",
            "capture-wechat-official",
            "--output-dir",
            str(tmp_path / "daily"),
        ],
    )

    assert kol_daily_script.main() == 0
    assert observed["args"].output_dir == tmp_path / "daily"
    assert json.loads(capsys.readouterr().out) == {
        "status": "completed",
        "dispatched": 2,
    }


def test_capture_xiaocao_handoff_cli_runs_only_read_only_handoff_recovery(
    tmp_path,
    monkeypatch,
    capsys,
):
    observed: dict[str, object] = {}

    def recover(self):
        assert not hasattr(self, "client")
        observed["args"] = self.args
        return {"status": "no_update", "handoff_dispatched": True}

    monkeypatch.setattr(DailyRuntime, "xiaocao_handoff_local", recover)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kol_daily.py",
            "capture-xiaocao-handoff",
            "--output-dir",
            str(tmp_path / "daily"),
        ],
    )

    assert kol_daily_script.main() == 0
    assert observed["args"].output_dir == tmp_path / "daily"
    assert json.loads(capsys.readouterr().out) == {
        "status": "no_update",
        "handoff_dispatched": True,
    }


def test_process_wechat_official_cli_runs_only_the_remote_inbox(
    tmp_path,
    monkeypatch,
    capsys,
):
    observed: dict[str, object] = {}

    class FakeRuntime:
        def __init__(self, args):
            observed["args"] = args

        @staticmethod
        def wechat_official():
            observed["called"] = True
            return {"status": "completed", "events": [{"event_id": "article"}]}

    monkeypatch.setattr(kol_daily_script, "DailyRuntime", FakeRuntime)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kol_daily.py",
            "process-wechat-official",
            "--output-dir",
            str(tmp_path / "daily"),
        ],
    )

    assert kol_daily_script.main() == 0
    assert observed["called"] is True
    assert json.loads(capsys.readouterr().out) == {
        "status": "completed",
        "events": [{"event_id": "article"}],
    }


def test_process_xiaocao_handoff_cli_runs_only_remote_post_handoff(
    tmp_path,
    monkeypatch,
    capsys,
):
    observed: dict[str, object] = {}

    class FakeRuntime:
        def __init__(self, args):
            observed["args"] = args

        @staticmethod
        def xiaocao():
            observed["called"] = True
            return {"status": "completed", "events": [{"event_id": "video"}]}

    monkeypatch.setattr(kol_daily_script, "DailyRuntime", FakeRuntime)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kol_daily.py",
            "process-xiaocao-handoff",
            "--output-dir",
            str(tmp_path / "daily"),
        ],
    )

    assert kol_daily_script.main() == 0
    assert observed["called"] is True
    assert json.loads(capsys.readouterr().out) == {
        "status": "completed",
        "events": [{"event_id": "video"}],
    }


def test_daily_runtime_runs_wechat_official_account_subscription(
    tmp_path,
    monkeypatch,
):
    calls: list[tuple[str, object]] = []

    class FakeReader:
        def __init__(self, publishers, *, executable, within):
            calls.append(("reader", (publishers, executable, within)))

        def __call__(self):
            return {"updates": [], "failures": []}

    class FakeSubscription:
        def __init__(
            self,
            output_dir,
            *,
            reader,
            handoff_exchange,
            publishers,
        ):
            assert isinstance(reader, FakeReader)
            assert callable(handoff_exchange)
            calls.append(("subscription", (output_dir, publishers)))

        def run_once(self):
            calls.append(("run", None))
            return {"status": "no_update"}

    monkeypatch.setattr(
        kol_daily_script,
        "WechatCliOfficialAccountReader",
        FakeReader,
    )
    monkeypatch.setattr(
        kol_daily_script,
        "OfficialAccountSubscription",
        FakeSubscription,
    )
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        wechat_official_publishers=("刘少狙击营", "A也叫艾利克斯"),
        wechat_official_output_dir=tmp_path / "official",
        wechat_official_within="48h",
        wechat_cli=tmp_path / "wechat-cli",
    )

    assert runtime.wechat_official_local() == {"status": "no_update"}
    assert calls == [
        (
            "reader",
            (
                ("刘少狙击营", "A也叫艾利克斯"),
                tmp_path / "wechat-cli",
                "48h",
            ),
        ),
        (
            "subscription",
            (
                tmp_path / "official",
                ("刘少狙击营", "A也叫艾利克斯"),
            ),
        ),
        ("run", None),
    ]


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


def test_durable_report_only_terminal_has_zero_book_effect(tmp_path):
    service = DailyCoordinator(
        tmp_path / "daily",
        now=Clock("2026-07-27T08:00:00+08:00"),
    )
    event = _promoted_event(event_id="lv-durable-report", tier="report_only")
    event["claim_semantic_routing"] = {
        "content_product": "underlying_logic",
        "current_decision_claim_ids": [],
        "durable_knowledge_claim_ids": ["lv-method"],
    }
    event["book_kol_us"] = {
        "status": "not_created",
        "book": "KOL-US",
        "paper_only": True,
        "reason": "durable-only knowledge creates no Book entry",
        "terminal_order": 3,
    }

    result = service.run(
        [{
            "name": "lv-durable",
            "priority": 10,
            "run": lambda: {"status": "completed", "events": [event]},
        }]
    )
    audit = service.audit()

    assert result["health"] == "healthy"
    assert audit["gray_report_count"] == 1
    assert audit["reminder_count"] == 0
    assert audit["book_trade_count"] == 0


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
        self.claimed_content_sha256 = None

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

    def deliver_wechat(self, result, *, sender, message_builder=None):
        self.order.append("alert")
        assert message_builder is not None
        title, body = message_builder(
            result["items"][0],
            result["cross_source"],
        )
        self.claimed_content_sha256 = hashlib.sha256(
            f"{title}\n{body}".encode()
        ).hexdigest()[:16]
        response = sender(title, body)
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
            "longitudinal_projection": {
                "status": "none",
                "reason": "本测试只验证事件报告与提醒顺序，不建立长期观点。",
                "viewpoints": [],
            },
        }]
    }


def _projection_bundle() -> dict:
    bundle = _publication_bundle(tier="report_only")
    item = bundle["items"][0]
    item["claims"] = [{
        "claim_id": "light-position-boundary",
        "quote": "轮动仍乱，趋势与断板都只用轻仓。",
    }]
    item["longitudinal_projection"] = {
        "status": "promoted",
        "reason": "轻仓纪律有明确适用环境、期限和失效条件，可以持续复核。",
        "evaluated_at": "2026-07-27T10:05:00+08:00",
        "viewpoints": [{
            "local_thesis_id": "light-position-boundary",
            "subject": "弱轮动环境下的仓位边界",
            "stance": "市场轮动混乱时，趋势与断板机会都只适合轻仓试错。",
            "horizon": "当日及随后几个交易日",
            "reasoning": "方向持续性不足时，先控制单次错误对账户的影响。",
            "role": "仓位与风险控制",
            "triggers": ["市场仍缺少持续领涨方向时继续轻仓。"],
            "falsifiers": ["主线形成并出现连续放量承接时重新评估仓位。"],
            "uncertainties": ["需要后续盘面确认主线是否真正形成。"],
            "evidence_refs": [{
                "claim_id": "light-position-boundary",
                "excerpt": "轮动仍乱，趋势与断板都只用轻仓。",
            }],
            "evaluation": {
                "status": "uncertain",
                "basis": "观点来源明确，但随后数日的盘面持续性尚未验证。",
                "confidence": "中等",
                "uncertainties": ["缺少下一交易日的量价确认。"],
                "evidence": [
                    "/Users/example/output/live/paper_holdings.json"
                ],
            },
        }],
    }
    return bundle


def test_publication_pipeline_creates_initial_viewpoint_and_evaluation(
    tmp_path,
):
    order: list[str] = []
    pipeline = DailyPublicationPipeline(
        _DelegatePipeline(order),
        ledger=PublicationLedger(tmp_path / "publication"),
        client=_PublicationClient(order),
        context=DailyPublicationContext(
            adapter="xiaocao_live",
            source_identity="live-with-viewpoint",
            publication_version="transcript-v1",
            kol_id="kol-xiaocao",
            source="小草直播",
            source_published_at="2026-07-27T09:30:00+08:00",
            media_types=("video",),
            source_parts=({
                "identity": "handoff-viewpoint",
                "version": "transcript-v1",
                "order": 1,
                "size": 0,
                "evidence_sha256": "a" * 64,
            },),
        ),
    )

    result = pipeline.process(_projection_bundle())

    assert result["status"] == "completed"
    publication_key = publication_id_for_source(
        adapter="xiaocao_live",
        source_identity="live-with-viewpoint",
    )
    records = pipeline.ledger.status(publication_key)["artifact"]["records"]
    report = next(row for row in records if row["kind"] == "report")
    viewpoint = next(row for row in records if row["kind"] == "viewpoint")
    evaluation = next(
        row for row in records if row["kind"] == "viewpoint_evaluation"
    )
    assert report["payload"]["viewpoint_ids"] == [viewpoint["record_id"]]
    assert viewpoint["payload"]["local_thesis_id"] == (
        "light-position-boundary"
    )
    assert evaluation["payload"]["viewpoint_id"] == viewpoint["record_id"]
    assert evaluation["payload"]["status"] == "uncertain"
    assert "evidence" not in evaluation["payload"]
    assert evaluation["created_at"] == "2026-07-27T02:05:00Z"
    assert order == ["gray", "book"]


def test_promoted_event_requires_explicit_longitudinal_decision(tmp_path):
    bundle = _publication_bundle()
    del bundle["items"][0]["longitudinal_projection"]
    pipeline = DailyPublicationPipeline(
        _DelegatePipeline([]),
        ledger=PublicationLedger(tmp_path / "publication"),
        client=_PublicationClient([]),
        context=DailyPublicationContext(
            adapter="xiaocao_live",
            source_identity="missing-projection",
            publication_version="transcript-v1",
            kol_id="kol-xiaocao",
            source="小草直播",
            source_published_at="2026-07-27T09:30:00+08:00",
            media_types=("video",),
            source_parts=(),
        ),
    )

    with pytest.raises(DailyError, match="explicit longitudinal"):
        pipeline.process(bundle)


def test_publication_pipeline_publishes_before_book_and_one_link_reminder(
    tmp_path,
):
    order: list[str] = []
    sent: list[tuple[str, str]] = []
    delegate = _DelegatePipeline(order)
    pipeline = DailyPublicationPipeline(
        delegate,
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
    bundle["items"][0]["reader_reminder"] = {
        "title": "弱轮动下的周一剧本与10%试错纪律",
        "summary": "轮动仍乱，先观察开盘路径，条件满足也只轻仓试错。",
    }
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
        "投资情报｜小草：弱轮动下的周一剧本与10%试错纪律"
    )
    assert sent[0][1].startswith(
        "轮动仍乱，先观察开盘路径，条件满足也只轻仓试错。"
    )
    assert sent[0][1].count("https://") == 1
    assert sent[0][1].endswith(
        "https://reader.example/kol/report-first"
    )
    assert delegate.claimed_content_sha256 == hashlib.sha256(
        f"{sent[0][0]}\n{sent[0][1]}".encode()
    ).hexdigest()[:16]
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


def test_completed_publication_resumes_without_rebuilding_changed_reader_copy(
    tmp_path,
):
    order: list[str] = []
    ledger = PublicationLedger(tmp_path / "publication")
    client = _PublicationClient(order)
    context = DailyPublicationContext(
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
    )
    first = DailyPublicationPipeline(
        _DelegatePipeline(order),
        ledger=ledger,
        client=client,
        context=context,
    )
    first.process(_publication_bundle())
    assert order == ["gray", "book"]
    publication_key = publication_id_for_source(
        adapter=context.adapter,
        source_identity=context.source_identity,
    )
    original_event_count = ledger.status(publication_key)["event_count"]
    changed = _publication_bundle()
    changed["items"][0]["publication"]["report_body"] += (
        "\n\n内部旧状态 COLD"
    )
    resumed = DailyPublicationPipeline(
        _DelegatePipeline(order),
        ledger=ledger,
        client=client,
        context=context,
    )

    result = resumed.process(changed)

    assert result["status"] == "completed"
    assert order == ["gray", "book", "book"]
    assert ledger.status(publication_key)["event_count"] == original_event_count
    invalid_reminder = _publication_bundle()
    invalid_reminder["items"][0]["publication"]["remaining_summary"] = (
        "内部旧状态 COLD"
    )
    blocked = DailyPublicationPipeline(
        _DelegatePipeline(order),
        ledger=ledger,
        client=client,
        context=context,
    )
    with pytest.raises(DailyError, match="internal action label 'COLD'"):
        blocked.process(invalid_reminder)
    assert order == ["gray", "book", "book"]


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


def test_source_classifier_isolates_unavailable_semantic_input():
    runner = _classified_source(
        "subscription_video",
        lambda: (_ for _ in ()).throw(
            SemanticInputUnavailable("private input detail")
        ),
    )

    with pytest.raises(TransientSourceError) as captured:
        runner()

    assert captured.value.diagnostic() == {
        "category": "input_error",
        "code": "semantic_input_unavailable",
        "stage": "semantic_input",
        "retryable": True,
    }
    assert "private input detail" not in str(captured.value)


def test_one_lv_full_snapshot_is_reused_by_both_adapters(monkeypatch, tmp_path):
    listing = {
        "status": "ok",
        "complete_scan": True,
        "entries": [{
            "provider_file_id": "lv-one",
            "path": "/share/one.mp4",
            "name": "one.mp4",
            "is_dir": False,
            "size": 123,
            "modified_at": 1_785_000_000,
        }],
    }
    calls = {"full_scan": 0, "video_scan": 0}

    class FakeLv:
        @classmethod
        def from_config(cls, *_args, **_kwargs):
            return cls()

        def _read_opencli_listing(self, **_kwargs):
            calls["full_scan"] += 1
            return listing

        def poll_opencli(self, *, listing: dict, **_kwargs):
            assert listing is not None
            assert listing is globals_listing

        @staticmethod
        def pending_items():
            return []

    class FakeVideos:
        def __init__(self, *_args, **_kwargs):
            pass

        def scan_opencli(self, *, lv_listing: dict, **_kwargs):
            calls["video_scan"] += 1
            assert lv_listing is globals_listing

        @staticmethod
        def pending_items():
            return []

    globals_listing = listing
    monkeypatch.setattr(kol_daily_script, "LvSubscriptionService", FakeLv)
    monkeypatch.setattr(kol_daily_script, "SubscriptionVideoService", FakeVideos)
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        lv_output_dir=tmp_path / "lv",
        video_output_dir=tmp_path / "videos",
        config=tmp_path / "config.yaml",
        lv_session="lv-session",
        private_session="private-session",
        enrichment_session="enrichment-session",
        opencli_profile="profile",
    )
    runtime._lv_service = None
    runtime._lv_listing = None
    runtime._lv_listing_error = None

    assert runtime.lv() == {"status": "no_update"}
    assert runtime.videos() == {"status": "no_update"}
    assert calls == {"full_scan": 1, "video_scan": 1}


def test_lv_pending_failure_isolated_without_blocking_later_pdf(
    monkeypatch,
    tmp_path,
):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text("{}", encoding="utf-8")
    calls = []
    failures = []

    class FakeLv:
        def poll_opencli(self, **_kwargs):
            return None

        @staticmethod
        def pending_items():
            return [
                {
                    "identity": "historical-bad",
                    "version_key": "historical-version",
                    "name": "历史坏状态.pdf",
                    "path": "/报告/历史坏状态.pdf",
                    "media_type": "pdf",
                    "size": 10,
                    "modified_at": 200,
                    "stage": "downloaded",
                },
                {
                    "identity": "new-good",
                    "version_key": "new-version",
                    "name": "大摩拆解.pdf",
                    "path": "/报告/大摩拆解.pdf",
                    "media_type": "pdf",
                    "size": 20,
                    "modified_at": 100,
                    "stage": "discovered",
                },
            ]

        @staticmethod
        def metadata_companion_proof(*_args, **_kwargs):
            return None

        def download_opencli(self, identity, **_kwargs):
            calls.append(identity)
            if identity == "historical-bad":
                raise EnrichmentError(
                    "subscription browser download receipt is not evidence-bound"
                )
            return {"status": "completed"}

        @staticmethod
        def ingest_browser_download(identity):
            return {
                "identity": identity,
                "version_key": "new-version",
                "media_type": "pdf",
                "evidence_path": "/immutable/new.pdf",
            }

        @staticmethod
        def prepare_analysis_request(_ingest):
            return {"request_path": "/runtime/request.json"}

        @staticmethod
        def record_pdf_relationship(_identity, *, bundle_path):
            assert bundle_path == globals_bundle_path
            return {"route": "companion_suppressed"}

        @staticmethod
        def record_item_failure(identity, *, failure, retryable):
            failures.append((identity, failure, retryable))

    globals_bundle_path = bundle_path
    monkeypatch.setattr(
        kol_daily_script,
        "_read_agent_path",
        lambda *_args, **_kwargs: bundle_path,
    )
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        lv_output_dir=tmp_path / "lv",
        video_output_dir=tmp_path / "videos",
        lv_session="lv-session",
        opencli_profile=None,
        decision_output_dir=tmp_path / "decisions",
    )
    runtime._lv_service = FakeLv()
    runtime._lv_listing = {
        "status": "ok",
        "complete_scan": True,
        "entries": [],
    }
    runtime._lv_listing_error = None

    result = runtime.lv()

    assert calls == ["historical-bad", "new-good"]
    assert result["status"] == "waiting"
    assert result["suppressed_companion_count"] == 1
    assert result["waiting_count"] == 1
    assert failures == [(
        "historical-bad",
        {
            "category": "state_error",
            "code": "download_receipt_not_evidence_bound",
            "stage": "download_reconciliation",
        },
        False,
    )]


def test_lv_native_save_prompt_stays_internal_and_does_not_request_user(tmp_path):
    failures = []

    class FakeLv:
        def poll_opencli(self, **_kwargs):
            return None

        @staticmethod
        def pending_items():
            return [{
                "identity": "e" * 64,
                "version_key": "v" * 64,
                "name": "大摩拆解.pdf",
                "path": "/报告/大摩拆解.pdf",
                "media_type": "pdf",
                "size": 768188,
                "modified_at": 1785774466,
                "stage": "download_claimed",
            }]

        @staticmethod
        def metadata_companion_proof(*_args, **_kwargs):
            return None

        @staticmethod
        def download_opencli(*_args, **_kwargs):
            raise EnrichmentDiagnosticError(
                "native save prompt",
                category="local_recovery",
                code="download_prompt_internal_recovery",
                stage="browser_download_prompt",
            )

        @staticmethod
        def record_item_failure(identity, *, failure, retryable):
            failures.append((identity, failure, retryable))

    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        lv_session="lv-session",
        opencli_profile=None,
    )
    runtime._lv_service = FakeLv()
    runtime._lv_listing = {
        "status": "ok",
        "complete_scan": True,
        "entries": [],
    }
    runtime._lv_listing_error = None
    runtime._complete_lv_video_transcripts = lambda: []

    result = runtime.lv()

    assert result["status"] == "waiting"
    assert failures == [(
        "e" * 64,
        {
            "category": "local_recovery",
            "code": "download_prompt_internal_recovery",
            "stage": "browser_download_prompt",
        },
        True,
    )]


def test_video_history_failure_isolated_after_latest_lv_priority(
    monkeypatch,
    tmp_path,
):
    calls = []
    failures = []
    latest_lv = {
        "identity": "latest-lv",
        "version_key": "latest-version",
        "name": "8月3日 (1).mp4",
        "path": "/share/8月3日 (1).mp4",
        "source": "baidu_subscription_share_browser",
        "modified_at": 200,
        "version_first_seen_at": "2026-08-04T07:00:00+08:00",
    }
    historical = {
        "identity": "historical-lucifer",
        "version_key": "historical-version",
        "name": "第一段.mp4",
        "path": "/private/第一段.mp4",
        "source": "baidu_private_folder",
        "modified_at": 100,
        "version_first_seen_at": "2026-07-28T12:00:00+08:00",
    }

    class FakeVideos:
        def __init__(self, *_args, **_kwargs):
            pass

        def scan_opencli(self, **_kwargs):
            return None

        @staticmethod
        def pending_items():
            return [historical, latest_lv]

        @staticmethod
        def advance_item(item, **_kwargs):
            calls.append(item["identity"])
            if item["identity"] == "historical-lucifer":
                raise EnrichmentError("OpenCLI browser command timed out")
            return {
                "status": "waiting_cloud_transfer_receipt",
                "stage": "source_acquisition",
                "next_poll_not_before": "2026-08-04T13:10:00+08:00",
            }

        @staticmethod
        def record_item_failure(item, *, failure, retryable):
            failures.append((item["identity"], failure, retryable))

    monkeypatch.setattr(kol_daily_script, "SubscriptionVideoService", FakeVideos)
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        video_output_dir=tmp_path / "videos",
        config=tmp_path / "config.yaml",
        lv_session="lv-session",
        private_session="private-session",
        enrichment_session="enrichment-session",
        opencli_profile=None,
    )
    runtime._lv_listing = {
        "status": "ok",
        "complete_scan": True,
        "entries": [],
    }
    runtime._lv_listing_error = None

    result = runtime.videos()

    assert calls == ["latest-lv", "historical-lucifer"]
    assert result["status"] == "waiting"
    assert result["waiting_count"] == 2
    assert failures == [(
        "historical-lucifer",
        {
            "category": "timeout",
            "code": "opencli_timeout",
            "stage": "browser_command",
        },
        True,
    )]


def test_video_semantic_eof_waits_and_next_run_reuses_persisted_request(
    monkeypatch,
    tmp_path,
):
    video_output = tmp_path / "videos"
    evidence = tmp_path / "transcript.txt"
    evidence.write_text("完整逐字稿证据", encoding="utf-8")
    evidence_sha256 = hashlib.sha256(evidence.read_bytes()).hexdigest()
    version_key = "v" * 64
    identity = "i" * 64
    request_path = video_output / "artifacts" / version_key / "analysis_request.json"
    item = {
        "identity": identity,
        "version_key": version_key,
        "name": "8月3日 (1).mp4",
        "path": "/直播回放/2026年8月/8月3日 (1).mp4",
        "source": "baidu_subscription_share_browser",
        "author": "吕晓彤",
        "media_type": "video",
        "size": 5_508_885_608,
        "modified_at": 1_785_772_456,
        "version_first_seen_at": "2026-08-04T07:00:00+08:00",
    }
    historical_item = {
        **item,
        "identity": "h" * 64,
        "version_key": "w" * 64,
        "name": "historical.mp4",
        "path": "/historical.mp4",
        "source": "baidu_private_folder",
        "author": "路西法",
        "modified_at": 1_748_323_280,
    }
    advance_calls = []
    decision_calls = []
    pending_calls = 0

    def analysis_request():
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request = {
            "event": "subscription_video_analysis_input_required",
            "source": item["source"],
            "author": item["author"],
            "title": item["name"],
            "publication_time": "2026-08-03T00:00:00+08:00",
            "source_identity": identity,
            "source_version_key": version_key,
            "evidence_path": str(evidence.resolve()),
            "evidence_sha256": evidence_sha256,
            "transcript_path": str(evidence.resolve()),
            "transcript_sha256": evidence_sha256,
            "analysis_request_path": str(request_path.resolve()),
        }
        request_path.write_text(json.dumps(request), encoding="utf-8")
        return request

    class FakeVideos:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def scan_opencli(**_kwargs):
            return None

        @staticmethod
        def pending_items():
            nonlocal pending_calls
            pending_calls += 1
            if pending_calls == 1:
                return [item, historical_item]
            return [item]

        @staticmethod
        def advance_item(requested, **_kwargs):
            advance_calls.append(requested["identity"])
            return analysis_request()

        @staticmethod
        def decide_item(requested, *, bundle_path, **_kwargs):
            decision_calls.append((requested["identity"], Path(bundle_path)))
            result_path = tmp_path / "decision-result.json"
            result_path.write_text(json.dumps({
                "items": [{
                    "daily_terminal": {
                        "kind": "source_event",
                        "event_id": identity,
                    },
                }],
            }), encoding="utf-8")
            return {"decision_result_path": str(result_path)}

    monkeypatch.setattr(kol_daily_script, "SubscriptionVideoService", FakeVideos)
    runtime = DailyRuntime.__new__(DailyRuntime)
    runtime.args = SimpleNamespace(
        video_output_dir=video_output,
        config=tmp_path / "config.yaml",
        decision_output_dir=tmp_path / "decisions",
        lv_session="lv-session",
        private_session="private-session",
        enrichment_session="enrichment-session",
        opencli_profile=None,
    )
    runtime._lv_listing = {
        "status": "ok",
        "complete_scan": True,
        "entries": [],
    }
    runtime._lv_listing_error = None
    runtime._pipeline = lambda _context: object()

    monkeypatch.setattr(kol_daily_script.sys, "stdin", io.StringIO(""))
    first = runtime.videos()

    assert first["status"] == "waiting"
    assert first["waiting_count"] == 1
    assert first["waiting_items"] == [{
        "identity": identity,
        "version_key": version_key,
        "name": item["name"],
        "author": item["author"],
        "status": "waiting_semantic_input",
        "stage": "waiting_semantic_input",
        "analysis_request_path": str(request_path.resolve()),
        "evidence_path": str(evidence.resolve()),
        "evidence_sha256": evidence_sha256,
        "semantic_request_preserved": True,
        "external_business_effects_replayed": False,
    }]
    assert advance_calls == [identity]
    assert decision_calls == []

    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        kol_daily_script.sys,
        "stdin",
        io.StringIO(json.dumps({"bundle_path": str(bundle)}) + "\n"),
    )
    second = runtime.videos()

    assert second["status"] == "completed"
    assert advance_calls == [identity]
    assert decision_calls == [(identity, bundle.resolve())]


def test_pdf_companion_publication_context_merges_explicit_source_parts(tmp_path):
    original = tmp_path / "report.pdf"
    original.write_bytes(b"%PDF-evidence")
    ingest = {
        "identity": "pdf-identity",
        "version_key": "pdf-version",
        "original_path": str(original),
        "evidence_sha256": "a" * 64,
        "media_type": "pdf",
        "published_at": "2026-08-04T03:22:06+08:00",
    }
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({
        "items": [{
            "episode_relationship": {
                "document_role": "video_summary",
                "primary_source_status": "complete",
                "semantic_comparison": {
                    "substantive_new_points": True,
                },
                "related_source_part": {
                    "identity": "video-identity",
                    "version_key": "video-version",
                    "size": 5_508_885_608,
                    "media_type": "video",
                    "transcript_sha256": "b" * 64,
                },
            },
        }],
    }))

    context = _lv_publication_context(ingest, bundle_path)

    assert context.source_identity not in {"pdf-identity", "video-identity"}
    assert context.media_types == ("pdf", "video")
    assert [row["identity"] for row in context.source_parts] == [
        "pdf-identity",
        "video-identity",
    ]
    assert [row["evidence_sha256"] for row in context.source_parts] == [
        "a" * 64,
        "b" * 64,
    ]


def test_consecutive_same_failure_requests_internal_repair_without_notifying(tmp_path):
    clock = Clock("2026-07-27T14:00:00+08:00")
    service = DailyCoordinator(tmp_path / "daily", now=clock)
    notices = []
    attempts = 0

    def failing():
        nonlocal attempts
        attempts += 1
        raise TransientSourceError(
            "private details must not be persisted",
            category="timeout",
            code="share_list_timeout",
            stage="listing_validation",
        )

    first = service.run(
        [{"name": "lv_text_image", "run": failing}],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )
    clock.value = datetime.fromisoformat("2026-07-27T15:00:00+08:00")
    second = service.run(
        [{"name": "lv_text_image", "run": failing}],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )
    clock.value = datetime.fromisoformat("2026-07-27T16:00:00+08:00")
    third = service.run(
        [{"name": "lv_text_image", "run": failing}],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )

    assert first["health"] == "degraded"
    assert second["health"] == "degraded"
    assert third["health"] == "degraded"
    assert attempts == 3
    assert notices == []
    assert second["source_results"][0]["consecutive_failure_count"] == 2
    assert second["source_results"][0]["repair_required"] is True
    assert second["source_results"][0]["user_action_required"] is False
    assert third["source_results"][0]["repair_required"] is True
    audit = service.audit()
    assert audit["operational_status"] == "degraded"
    assert audit["operational_reminder_count"] == 0
    assert audit["repair_required_count"] == 2
    assert audit["latest_repairs"][0]["source"] == "lv_text_image"
    events = service.events()
    exhausted = [
        row for row in events if row["event"] == "source_recovery_exhausted"
    ]
    assert len(exhausted) == 2
    assert all(
        row["external_business_effects_replayed"] is False
        for row in exhausted
    )


def test_repeated_source_acquisition_stall_requests_internal_repair(tmp_path):
    clock = Clock("2026-07-27T14:00:00+08:00")
    service = DailyCoordinator(tmp_path / "daily", now=clock)
    notices = []
    calls = 0

    def waiting():
        nonlocal calls
        calls += 1
        return {
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [{
                "identity": "identity-1",
                "version_key": "version-1",
                "stage": "source_acquisition",
            }],
        }

    service.run(
        [{"name": "subscription_video", "run": waiting}],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )
    clock.value = datetime.fromisoformat("2026-07-27T15:00:00+08:00")
    result = service.run(
        [{"name": "subscription_video", "run": waiting}],
        blocker_sender=lambda title, body: notices.append((title, body)),
    )

    assert calls == 2
    assert result["health"] == "degraded"
    assert result["source_results"][0]["repair_required"] is True
    assert result["source_results"][0]["user_action_required"] is False
    assert notices == []
    stalled = [
        row
        for row in service.events()
        if row["event"] == "source_acquisition_stalled"
    ]
    assert stalled[0]["external_business_effects_replayed"] is False


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


def test_source_classifier_promotes_wechat_opencli_captcha_to_blocker():
    runner = _classified_source(
        "wechat_official_accounts",
        lambda: (_ for _ in ()).throw(
            EnrichmentDiagnosticError(
                "wechat_official_captcha_required",
                category="user_action",
                code="wechat_official_captcha_required",
                stage="wechat_official_opencli",
            )
        ),
    )

    with pytest.raises(UserActionBlocker) as captured:
        runner()

    assert captured.value.blocker_key == "wechat-official-opencli-captcha"
    assert "现有 OpenCLI Chrome 会话" in captured.value.action
    assert "循环重试" in captured.value.action


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
        created_at="2026-07-20T00:00:00Z",
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
        created_at="2026-07-20T00:00:00Z",
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


def test_initial_projection_backfills_report_only_history_without_side_effects(
    tmp_path,
):
    publication_id = publication_id_for_source(
        adapter="wechat_official_account",
        source_identity="wechat-official-existing",
    )
    report_id_value = report_id(publication_id)
    evidence_path = tmp_path / "evidence.md"
    evidence_path.write_text(
        "# 来源证据\n\n行业景气仍需订单和利润验证。\n",
        encoding="utf-8",
    )
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    source_binding = {
        "publication_id": publication_id,
        "publication_version": "article-v1",
        "evidence_sha256": evidence_sha256,
        "decision_result_sha256": "b" * 64,
        "extraction_contract_version": "kol-intelligence-v1",
    }
    report = build_record(
        kind="report",
        record_id_value=report_id_value,
        idempotency_key="put-existing-report",
        created_at="2026-08-04T08:00:00Z",
        source_binding=source_binding,
        payload={
            "report_id": report_id_value,
            "report_kind": "publication_event",
            "kol_id": "kol-example",
            "author": "示例达人",
            "source": "微信公众号",
            "title": "示例达人：行业景气判断",
            "summary": "作者认为行业景气仍需订单和利润验证。",
            "source_published_at": "2026-08-04T08:00:00Z",
            "media_types": ["text"],
            "source_parts": [],
            "report_format": "markdown",
            "report_body": "# 核心判断\n\n行业景气仍需订单和利润验证。",
            "viewpoint_ids": [],
            "alert_eligible": False,
            "alert_reason": "历史文章只归档，不补发即时提醒。",
            "reader_insight": {
                "status": "useful",
                "reason": "包含可持续复核的行业判断。",
            },
        },
    )
    request = {
        "operation": "initial_projection",
        "trigger": "user_request",
        "report_id": report_id_value,
        "evidence_path": str(evidence_path),
        "evidence_sha256": evidence_sha256,
        "claims": [{
            "claim_id": "industry-profit-check",
            "quote": "行业景气仍需订单和利润验证。",
        }],
        "longitudinal_projection": {
            "status": "promoted",
            "reason": "主张有明确对象和验证条件。",
            "evaluated_at": "2026-08-05T18:20:00+08:00",
            "viewpoints": [{
                "local_thesis_id": "industry-profit-check",
                "subject": "行业景气与利润兑现",
                "stance": "行业景气能否延续，需要订单增长和利润兑现共同确认。",
                "horizon": "未来数周至一个季度",
                "reasoning": "订单只代表需求线索，最终仍需利润质量验证。",
                "evidence_refs": [{
                    "claim_id": "industry-profit-check",
                    "excerpt": "行业景气仍需订单和利润验证。",
                }],
                "evaluation": {
                    "status": "uncertain",
                    "basis": "来源观点清晰，但尚缺后续订单与利润数据。",
                    "uncertainties": ["等待下一期经营数据。"],
                },
            }],
        },
    }

    candidate = build_initial_projection_candidate(
        {"report": report, "records": [report]},
        request,
    )
    records = candidate["records"]
    updated_report = next(row for row in records if row["kind"] == "report")
    viewpoints = [row for row in records if row["kind"] == "viewpoint"]
    evaluations = [
        row for row in records if row["kind"] == "viewpoint_evaluation"
    ]
    assert len(viewpoints) == 1
    assert len(evaluations) == 1
    assert updated_report["payload"]["viewpoint_ids"] == [
        viewpoints[0]["record_id"]
    ]
    assert candidate["publish_request"]["expected_content_sha256"] == (
        report["content_sha256"]
    )
    terminal = initial_projection_terminal(
        candidate,
        {
            "completed": True,
            "publish_receipt": {
                "recordState": "published",
                "detailUrl": "https://reader.example/kol/example",
            },
        },
    )
    assert terminal["viewpoint_count"] == 1
    assert terminal["alert"]["status"] == "not_created"
    assert terminal["book_kol_us"]["status"] == "not_created"


def test_viewpoint_maintenance_uses_lianghui_evaluation_statuses():
    assert "expired" in VIEWPOINT_EVALUATION_STATUSES
    assert "changed" not in VIEWPOINT_EVALUATION_STATUSES


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
