from __future__ import annotations

import json

from xiaocao.strategy.kol_reference import load_current_macheng_reference


def _record(kind: str, record_id: str, payload: dict) -> dict:
    return {"kind": kind, "record_id": record_id, "payload": payload}


def _artifact(*, evaluation_status: str, evaluated_at: str) -> dict:
    report_id = "kr-macheng"
    viewpoint_id = "vp-macheng"
    return {
        "records": [
            _record(
                "report",
                report_id,
                {
                    "kol_id": "kol-lv-xiaotong",
                    "title": "吕晓彤 8月11日马车",
                },
            ),
            _record(
                "viewpoint",
                viewpoint_id,
                {
                    "viewpoint_id": viewpoint_id,
                    "report_id": report_id,
                    "kol_id": "kol-lv-xiaotong",
                    "local_thesis_id": "lv-macheng-current-cycle-core-pool-20260811",
                    "subject": "吕晓彤当前周期的“马车”核心推荐池",
                    "source_published_at": "2026-08-11T02:08:05Z",
                    "evidence_refs": [
                        {"claim_id": "gold", "excerpt": "黄金 ETF"},
                        {"claim_id": "semi", "excerpt": "半导体设备 ETF"},
                        {"claim_id": "robot", "excerpt": "机器人 ETF"},
                        {"claim_id": "ai", "excerpt": "人工智能 ETF"},
                        {"claim_id": "drug", "excerpt": "创新药 ETF"},
                    ],
                },
            ),
            _record(
                "viewpoint_evaluation",
                f"ve-{evaluation_status}-{evaluated_at}",
                {
                    "viewpoint_id": viewpoint_id,
                    "status": evaluation_status,
                    "evaluated_at": evaluated_at,
                    "as_of": evaluated_at,
                },
            ),
        ]
    }


def _write_events(path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_loader_requires_publication_receipt_and_returns_current_members(tmp_path) -> None:
    ledger = tmp_path / "events.jsonl"
    _write_events(
        ledger,
        [
            {
                "event": "publication_prepared",
                "publication_key": "published",
                "artifact": _artifact(
                    evaluation_status="current",
                    evaluated_at="2026-08-11T09:52:56Z",
                ),
            },
            {
                "event": "publication_receipt",
                "publication_key": "published",
                "receipt": {"recordState": "published"},
            },
            {
                "event": "publication_prepared",
                "publication_key": "unpublished-newer",
                "artifact": _artifact(
                    evaluation_status="current",
                    evaluated_at="2026-08-12T09:52:56Z",
                ),
            },
        ],
    )

    reference = load_current_macheng_reference(ledger)

    assert reference["status"] == "current"
    assert reference["authority"] == "shadow_only"
    assert reference["ranking_effect"] is False
    assert reference["eligibility_effect"] is False
    assert reference["publication_key"] == "published"
    assert [row["label"] for row in reference["members"]] == [
        "黄金 ETF",
        "半导体设备 ETF",
        "机器人 ETF",
        "人工智能 ETF",
        "创新药 ETF",
    ]


def test_loader_uses_latest_published_evaluation_for_currentness(tmp_path) -> None:
    ledger = tmp_path / "events.jsonl"
    _write_events(
        ledger,
        [
            {
                "event": "publication_prepared",
                "publication_key": "current",
                "artifact": _artifact(
                    evaluation_status="current",
                    evaluated_at="2026-08-11T09:52:56Z",
                ),
            },
            {
                "event": "publication_receipt",
                "publication_key": "current",
                "receipt": {"recordState": "published"},
            },
            {
                "event": "publication_prepared",
                "publication_key": "expired",
                "artifact": _artifact(
                    evaluation_status="expired",
                    evaluated_at="2026-08-20T09:52:56Z",
                ),
            },
            {
                "event": "publication_receipt",
                "publication_key": "expired",
                "receipt": {"recordState": "superseded"},
            },
        ],
    )

    reference = load_current_macheng_reference(ledger)

    assert reference["status"] == "unavailable"
    assert reference["reason"] == "no_current_published_macheng_viewpoint"


def test_loader_missing_ledger_is_non_blocking_shadow_unavailable(tmp_path) -> None:
    reference = load_current_macheng_reference(tmp_path / "missing.jsonl")

    assert reference["status"] == "unavailable"
    assert reference["authority"] == "shadow_only"
    assert reference["members"] == []
