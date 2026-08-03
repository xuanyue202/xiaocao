from __future__ import annotations

import json
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from xiaocao.kol.decisions import DecisionError, DecisionPipeline


def _result() -> dict:
    item = {
        "author": "小草",
        "title": "真实文稿",
        "claims": [{"claim_id": "claim-1", "reasoning": "等待放量后再行动。"}],
        "actionable_signals": [{
            "signal_id": "signal-1",
            "claim_ids": ["claim-1"],
            "action": "sell",
            "assets": [{"name": "三倍做多纳指", "market": "US", "ticker": "TQQQ"}],
            "relevant_asset_codes": ["TQQQ"],
            "horizon": "下一个交易日",
            "execution": "卖出 TQQQ；如需保留 AI 暴露，改用非杠杆 ETF。",
            "trigger": "当前即执行。",
            "confidence": "high",
            "falsifiers": ["家庭账户已无 TQQQ"],
            "rationale": {
                "news_or_event": ["KOL 明确要求卸掉杠杆。"],
                "fundamental": ["长期 AI 方向不需要账户杠杆表达。"],
                "trading": ["三倍 ETF 会放大回撤并产生路径损耗。"],
            },
            "current_validation": {
                "status": "support",
                "summary": "TQQQ 跌幅显著高于 QQQ。",
            },
        }],
        "market_validation": {"status": "support", "summary": "当前市场仍支持防守。"},
        "synthesis": {"summary": "不提前抄底。"},
        "household_recommendation": {
            "action": "wait",
            "confidence": "high",
            "horizon": "下一交易周",
            "falsifier": "放量止跌并形成主线。",
        },
        "household_context_assessment": {
            "cash_available_cny": 600_000,
            "bucket_excesses": ["breakthrough"],
            "relevant_positions": [{"asset_name": "科技ETF"}],
        },
        "book_kol_us": {"status": "no_trade", "reason": "没有明确美股映射。"},
        "notification": {
            "idempotency_key": "evidence-1",
            "status": "pending",
        },
    }
    return {
        "status": "completed",
        "items": [item],
        "cross_source": {
            "agreements": [],
            "conflicts": [{
                "topic": "entry-timing",
                "claim_ids": ["claim-1", "claim-2"],
                "authors": ["小草", "吕晓彤"],
                "judgment": "长期方向不覆盖短线风控。",
            }],
        },
    }


def _pipeline(tmp_path) -> DecisionPipeline:
    pipeline = DecisionPipeline(tmp_path / "out")
    pipeline.outbox_path.parent.mkdir(parents=True)
    pipeline.outbox_path.write_text(
        json.dumps({"idempotency_key": "evidence-1"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return pipeline


def _transport_request() -> dict:
    value = {
        "schema_version": 1,
        "notification_id": "evidence-1",
        "source_task": {
            "host_id": "remote-control:host-1",
            "thread_id": "thread-1",
        },
        "report_id": "kr_report_1",
        "stable_report_url": "https://reader.example/kol-reports/kr_report_1",
        "title": "投资情报｜小草：弱轮动下的周一剧本",
        "body": (
            "高开不追，显著低开后再验证修复。"
            "\n\n查看完整报告：https://reader.example/kol-reports/kr_report_1"
        ),
        "recipients": ["Chen", "FeiFei"],
        "missing_confirmation": {
            "kind": "recipient_missing_confirmation",
            "reference": "user-confirmed-20260803",
            "confirmed_at": "2026-08-03T00:40:00+08:00",
        },
        "original_failure": {
            "claimed_at": "2026-08-03T00:21:59+08:00",
            "recorded_at": "2026-08-03T00:22:00+08:00",
            "status": "failed recipients: Chen; FeiFei",
            "delivered_recipients": [],
        },
    }
    value["content_sha256"] = hashlib.sha256(
        f"{value['title']}\n{value['body']}".encode()
    ).hexdigest()
    value["handoff_id"] = hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return value


def test_wechat_delivery_uses_existing_relay_and_is_idempotent(tmp_path):
    pipeline = _pipeline(tmp_path)
    result = _result()
    calls = []

    def sender(title, body):
        calls.append((title, body))
        return {"wecom": "ok"}

    first = pipeline.deliver_wechat(result, sender=sender)
    second = pipeline.deliver_wechat(result, sender=sender)

    assert first["status"] == "delivered"
    assert second["status"] == "already_delivered"
    assert len(calls) == 1
    assert calls[0][0] == "投资情报｜小草：三倍做多纳指"
    assert "【现在处理：三倍做多纳指（TQQQ）】" in calls[0][1]
    assert "发生了什么：KOL 明确要求卸掉杠杆。" in calls[0][1]
    assert "为什么会传导：长期 AI 方向不需要账户杠杆表达。" in calls[0][1]
    assert "对你意味着什么：你现在没有这项持仓，因此不需要处理。" in calls[0][1]
    assert "多方不同判断" in calls[0][1]
    assert "小草、吕晓彤" in calls[0][1]
    assert "Book KOL-US" not in calls[0][1]
    assert "超配仓" not in calls[0][1]
    assert result["items"][0]["notification"]["status"] == "delivered"
    assert first["deliveries"][0]["receipt"].startswith("wecom-relay://ok/evidence-1/")


def test_transport_receipt_is_validated_before_aggregate_delivery(tmp_path):
    pipeline = _pipeline(tmp_path)
    request = _transport_request()
    with pipeline.events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "event": "notification_send_claimed",
            "idempotency_key": "evidence-1",
            "content_sha256": request["content_sha256"][:16],
        }, separators=(",", ":")) + "\n")
        handle.write(json.dumps({
            "event": "notification_send_uncertain",
            "idempotency_key": "evidence-1",
            "status": request["original_failure"]["status"],
        }, separators=(",", ":")) + "\n")
    receipt = {
        "schema_version": 1,
        "status": "delivered",
        "handoff_id": request["handoff_id"],
        "notification_id": "evidence-1",
        "report_id": "kr_report_1",
        "stable_report_url": "https://reader.example/kol-reports/kr_report_1",
        "content_sha256": request["content_sha256"],
        "recipient_receipts": {
            "Chen": {
                "receipt": (
                    f"wecom-relay://ok/{request['handoff_id']}/Chen/"
                    f"{request['content_sha256'][:16]}"
                ),
                "delivered_at": "2026-08-03T00:50:00+08:00",
            },
            "FeiFei": {
                "receipt": (
                    f"wecom-relay://ok/{request['handoff_id']}/FeiFei/"
                    f"{request['content_sha256'][:16]}"
                ),
                "delivered_at": "2026-08-03T00:50:01+08:00",
            },
        },
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    first = pipeline.record_transport_delivery(
        request,
        receipt,
        expected_recipients=("Chen", "FeiFei"),
    )
    second = pipeline.record_transport_delivery(
        request,
        receipt,
        expected_recipients=("Chen", "FeiFei"),
    )

    assert first["status"] == "delivered"
    assert second["idempotent_replay"] is True
    assert first["receipt"].endswith(receipt["receipt_sha256"])
    events = pipeline.events_path.read_text(encoding="utf-8")
    assert events.count("notification_transport_receipt_validated") == 1
    assert events.count('"event":"notification_delivered"') == 1


def test_transport_receipt_rejects_missing_recipient_or_bad_hash(tmp_path):
    pipeline = _pipeline(tmp_path)
    request = _transport_request()
    receipt = {
        "schema_version": 1,
        "status": "delivered",
        "handoff_id": "a" * 64,
        "notification_id": "evidence-1",
        "report_id": "kr_report_1",
        "stable_report_url": "https://reader.example/kol-reports/kr_report_1",
        "content_sha256": "b" * 64,
        "recipient_receipts": {
            "Chen": {
                "receipt": f"wecom-relay://ok/{'a' * 64}/Chen/{'b' * 16}",
                "delivered_at": "2026-08-03T00:50:00+08:00",
            }
        },
        "receipt_sha256": "c" * 64,
    }

    with pytest.raises(DecisionError, match="transport receipt hash"):
        pipeline.record_transport_delivery(
            request,
            receipt,
            expected_recipients=("Chen", "FeiFei"),
        )

    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256")
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(DecisionError, match="exact recipient set"):
        pipeline.record_transport_delivery(
            request,
            receipt,
            expected_recipients=("Chen", "FeiFei"),
        )


def test_transport_receipt_rejects_a_different_request_or_missing_uncertain_state(
    tmp_path,
):
    pipeline = _pipeline(tmp_path)
    request = _transport_request()
    receipt = {
        "schema_version": 1,
        "status": "delivered",
        "handoff_id": request["handoff_id"],
        "notification_id": request["notification_id"],
        "report_id": request["report_id"],
        "stable_report_url": request["stable_report_url"],
        "content_sha256": request["content_sha256"],
        "recipient_receipts": {
            recipient: {
                "receipt": (
                    f"wecom-relay://ok/{request['handoff_id']}/{recipient}/"
                    f"{request['content_sha256'][:16]}"
                ),
                "delivered_at": "2026-08-03T00:50:00+08:00",
            }
            for recipient in request["recipients"]
        },
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    with pytest.raises(DecisionError, match="prior uncertain state"):
        pipeline.record_transport_delivery(
            request,
            receipt,
            expected_recipients=("Chen", "FeiFei"),
        )

    with pipeline.events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "event": "notification_send_claimed",
            "idempotency_key": request["notification_id"],
            "content_sha256": request["content_sha256"][:16],
        }, separators=(",", ":")) + "\n")
        handle.write(json.dumps({
            "event": "notification_send_uncertain",
            "idempotency_key": request["notification_id"],
            "status": request["original_failure"]["status"],
        }, separators=(",", ":")) + "\n")
    different = dict(request)
    different["report_id"] = "kr_other"
    unsigned = dict(different)
    unsigned.pop("handoff_id")
    different["handoff_id"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    with pytest.raises(DecisionError, match="request and receipt differ"):
        pipeline.record_transport_delivery(
            different,
            receipt,
            expected_recipients=("Chen", "FeiFei"),
        )


def test_wechat_delivery_failure_is_visible_and_not_marked_delivered(tmp_path):
    pipeline = _pipeline(tmp_path)
    result = _result()
    calls = []

    def failed_sender(_title, _body):
        calls.append("called")
        return {"wecom": "http 500: failed"}

    with pytest.raises(DecisionError, match="WeChat delivery failed"):
        pipeline.deliver_wechat(result, sender=failed_sender)

    assert result["items"][0]["notification"]["status"] == "pending"
    events = pipeline.events_path.read_text(encoding="utf-8") if pipeline.events_path.exists() else ""
    assert "notification_delivered" not in events
    assert "notification_send_uncertain" in events
    with pytest.raises(DecisionError, match="state is uncertain"):
        pipeline.deliver_wechat(_result(), sender=failed_sender)
    assert calls == ["called"]


def test_concurrent_wechat_delivery_claims_each_notification_once(tmp_path):
    first_pipeline = _pipeline(tmp_path)
    second_pipeline = DecisionPipeline(tmp_path / "out")
    first_sender_entered = threading.Event()
    second_call_started = threading.Event()
    release_first = threading.Event()
    calls = []
    calls_lock = threading.Lock()

    def sender(title, body):
        with calls_lock:
            calls.append((title, body))
            call_number = len(calls)
        if call_number == 1:
            first_sender_entered.set()
            assert release_first.wait(timeout=2)
        return {"wecom": "ok"}

    def second_delivery():
        second_call_started.set()
        return second_pipeline.deliver_wechat(_result(), sender=sender)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_pipeline.deliver_wechat, _result(), sender=sender)
        assert first_sender_entered.wait(timeout=2)
        second = executor.submit(second_delivery)
        assert second_call_started.wait(timeout=2)
        release_first.set()
        first_result = first.result(timeout=2)
        second_result = second.result(timeout=2)

    assert len(calls) == 1
    assert {first_result["status"], second_result["status"]} == {
        "delivered",
        "already_delivered",
    }
