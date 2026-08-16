from __future__ import annotations

import pytest

from xiaocao.kol.publication import (
    build_publish_request,
    build_record,
    relation_id,
    report_id,
    viewpoint_id,
)
from xiaocao.strategy.trend_snapshot import (
    PublicationBindingError,
    TrendSnapshotError,
    build_trend_snapshot,
)


AS_OF = "2026-08-16T08:00:00Z"
GENERATED_AT = "2026-08-16T08:01:00Z"


def _source(
    *,
    source_key: str,
    kol_id: str,
    theme_id: str = "theme-ai",
    published_at: str = "2026-08-01T02:00:00Z",
    evaluated_at: str = "2026-08-16T02:00:00Z",
    evaluation_status: str = "current",
    horizon: list[str] | None = None,
    evaluation_review_not_after: str | None = None,
    subject: str = "人工智能趋势",
    report_title: str = "当前趋势判断",
    viewpoint_kol_id: str | None = None,
    evaluation_payload_id: str | None = None,
    receipt_record_id: str | None = None,
    receipt_manifest_sha256: str | None = None,
    publication_state: str = "published",
    binding_suffix: str | None = None,
) -> dict:
    suffix = binding_suffix or source_key
    publication = f"source:{suffix}"
    source_binding = {
        "publication_id": publication,
        "publication_version": f"{suffix}-v1",
        "evidence_sha256": suffix.ljust(64, "e"),
        "decision_result_sha256": suffix.ljust(64, "d"),
        "extraction_contract_version": "kol-intelligence-v1",
    }
    rid = report_id(publication)
    refs = [{"claim_id": f"claim-{source_key}", "excerpt": "趋势与估值条件"}]
    vid = viewpoint_id(rid, f"{source_key}-thesis", refs)
    report = build_record(
        kind="report",
        record_id_value=rid,
        idempotency_key=f"put-report-{source_key}",
        created_at=published_at,
        source_binding=source_binding,
        payload={
            "report_id": rid,
            "report_kind": "publication_event",
            "kol_id": kol_id,
            "author": (
                "小草"
                if kol_id == "kol-xiaocao"
                else "吕晓彤"
                if kol_id == "kol-lv-xiaotong"
                else "其他作者"
            ),
            "source": "研究报告",
            "title": report_title,
            "summary": "当前观点与市场条件需要绑定复核。",
            "source_published_at": published_at,
            "media_types": ["text"],
            "report_format": "markdown",
            "report_body": "# 核心判断\n\n当前观点与市场条件需要绑定复核。",
            "viewpoint_ids": [vid],
            "alert_eligible": False,
            "alert_reason": "shadow_snapshot_only",
        },
    )
    viewpoint_payload = {
        "viewpoint_id": vid,
        "report_id": rid,
        "kol_id": viewpoint_kol_id if viewpoint_kol_id is not None else kol_id,
        "local_thesis_id": f"{source_key}-thesis",
        "subject": subject,
        "stance": "保持方向并等待市场条件确认。",
        "source_published_at": published_at,
        "evidence_refs": refs,
    }
    if horizon is not None:
        viewpoint_payload["horizon"] = horizon
    viewpoint = build_record(
        kind="viewpoint",
        record_id_value=vid,
        idempotency_key=f"put-viewpoint-{source_key}",
        created_at=published_at,
        source_binding=source_binding,
        payload=viewpoint_payload,
    )
    evaluation_payload = {
        "evaluation_id": evaluation_payload_id or f"evaluation-{source_key}-{evaluation_status}",
        "viewpoint_id": vid,
        "status": evaluation_status,
        "as_of": evaluated_at,
        "evaluated_at": evaluated_at,
        "basis": "根据当前市场事实复核该观点。",
    }
    if evaluation_review_not_after is not None:
        evaluation_payload["review_not_after"] = evaluation_review_not_after
    evaluation = build_record(
        kind="viewpoint_evaluation",
        record_id_value=f"evaluation-{source_key}-{evaluation_status}",
        idempotency_key=f"put-evaluation-{source_key}-{evaluation_status}",
        created_at=evaluated_at,
        source_binding=source_binding,
        payload=evaluation_payload,
    )
    records = [report, viewpoint, evaluation]
    request = build_publish_request(
        records,
        idempotency_key=f"publish-{source_key}",
        reason="Book T v2 snapshot input",
    )
    return {
        "source_key": source_key,
        "theme_ids": [theme_id],
        "artifact": {"records": records, "publish_request": request},
        "publish_receipt": {
            "recordState": publication_state,
            "manifestSha256": receipt_manifest_sha256 or request["manifest_sha256"],
            "recordId": receipt_record_id or rid,
            "serverTime": evaluated_at,
        },
    }


def _context(*, stance: str = "可观察并逐步推进") -> dict:
    return {
        "as_of": AS_OF,
        "observed_at": "2026-08-16T01:00:00Z",
        "stance": stance,
        "direction": "bullish",
        "evidence_ids": ["xiaocao-posture-20260816"],
    }


def _market(*, status: str = "support", current: bool = True) -> dict:
    return {
        "theme-ai": {
            "status": status,
            "as_of": AS_OF,
            "checked_at": "2026-08-16T02:30:00Z",
            "currentness": {
                "latest_available": current,
                "reason": "专有行情验证" if current else "行情验证过期",
                "checked_at": "2026-08-16T02:30:00Z",
            },
            "facts": [
                {
                    "fact_id": "market-breadth-1",
                    "metric": "trend_breadth",
                    "value": "supportive",
                    "observed_at": "2026-08-16T02:00:00Z",
                    "evidence": "market-evidence-1",
                }
            ],
        }
    }


def _draft(
    *,
    eligibility: str = "eligible",
    source_keys: list[str] | None = None,
    review_not_after: str = "2026-08-17T02:00:00Z",
    other_kol: dict | None = None,
) -> dict:
    return {
        "themes": [
            {
                "theme_id": "theme-ai",
                "display_name": "人工智能",
                "direction": "bullish",
                "confidence": 0.8,
                "effective_from": "2026-08-01T02:00:00Z",
                "review_not_after": review_not_after,
                "horizon_basis": "agent_declared_trend_review",
                "eligibility": eligibility,
                "source_keys": source_keys or ["xiaocao", "mache", "other"],
                "xiaocao_timing": {"stance": "可观察并逐步推进"},
                "other_kol": (
                    other_kol
                    if other_kol is not None
                    else (
                        {
                            "confirmations": [
                                {
                                    "source_key": "other",
                                    "summary": "方向得到独立确认。",
                                }
                            ]
                        }
                        if "other"
                        in (source_keys or ["xiaocao", "mache", "other"])
                        else {}
                    )
                ),
            }
        ]
    }


def _build(
    *,
    sources: list[dict] | None = None,
    market: dict | None = None,
    draft: dict | None = None,
    context: dict | None = None,
    as_of: str = AS_OF,
):
    return build_trend_snapshot(
        as_of,
        published_sources=sources
        or [
            _source(
                source_key="xiaocao",
                kol_id="kol-xiaocao",
                published_at="2026-08-01T02:00:00Z",
                evaluated_at="2026-08-02T02:00:00Z",
            ),
            _source(source_key="mache", kol_id="kol-lv-xiaotong"),
            _source(source_key="other", kol_id="kol-other"),
        ],
        xiaocao_context=context or _context(),
        market_validation=market or _market(),
        agent_draft=draft or _draft(),
        generated_at=GENERATED_AT,
    )


def test_build_current_snapshot_keeps_roles_independent_and_is_not_a_trade_instruction():
    snapshot = _build()
    payload = snapshot.to_dict()
    theme = payload["themes"][0]

    assert payload["schema_version"] == 1
    assert payload["agent_judgment_version"] == "book-t-v2-trend-snapshot-v1"
    assert theme["eligibility"] == "eligible"
    assert theme["direction"] == "bullish"
    assert theme["xiaocao_timing"]["status"] == "current"
    assert theme["mache_support"]["status"] == "active"
    assert theme["mache_support"]["expires_not_after"] == "2026-09-01T02:00:00Z"
    assert theme["horizon"]["review_not_after"] == theme["review_not_after"]
    assert theme["other_kol"]["confirmations"]
    assert theme["source_evidence"]
    assert theme["market_validation"]["evidence_ids"] == ["market-evidence-1"]
    assert all(row["evidence_refs"] for row in theme["source_evidence"])
    assert payload["binding_receipt"]["snapshot_sha256"] == payload["snapshot_sha256"]
    assert not {"price", "shares", "quantity", "ledger", "order"}.intersection(theme)


def test_snapshot_waits_when_market_validation_is_not_current():
    snapshot = _build(market=_market(current=False))

    theme = snapshot.to_dict()["themes"][0]

    assert theme["eligibility"] == "wait"
    assert theme["eligibility_reason"] == "market_validation_not_current"


def test_superseded_receipt_with_current_evaluation_remains_authoritative():
    snapshot = _build(
        sources=[
            _source(
                source_key="xiaocao",
                kol_id="kol-xiaocao",
                publication_state="superseded",
            )
        ],
        draft=_draft(source_keys=["xiaocao"]),
    )

    theme = snapshot.to_dict()["themes"][0]

    assert theme["eligibility"] == "eligible"
    assert theme["source_evidence"][0]["publication_state"] == "superseded"
    assert theme["source_evidence"][0]["current"] is True


def test_xiaocao_without_review_deadline_is_not_automatically_renewed():
    snapshot = _build(
        sources=[
            _source(
                source_key="xiaocao",
                kol_id="kol-xiaocao",
                evaluated_at="2026-08-02T02:00:00Z",
            )
        ],
        draft=_draft(source_keys=["xiaocao"], review_not_after=None),
    )

    theme = snapshot.to_dict()["themes"][0]
    source = theme["source_evidence"][0]

    assert theme["eligibility"] == "wait"
    assert source["current"] is False
    assert source["status"] == "pending"
    assert source["freshness_basis"] == (
        "current_evaluation_requires_machine_review_not_after"
    )


def test_mache_uses_earlier_evaluation_review_deadline():
    snapshot = _build(
        sources=[
            _source(
                source_key="mache",
                kol_id="kol-lv-xiaotong",
                evaluated_at="2026-08-02T02:00:00Z",
                evaluation_review_not_after="2026-08-10T02:00:00Z",
            )
        ],
        draft=_draft(source_keys=["mache"]),
    )

    theme = snapshot.to_dict()["themes"][0]
    mache = theme["mache_support"]
    source = theme["source_evidence"][0]

    assert mache["status"] == "expired"
    assert mache["expires_not_after"] == "2026-08-10T02:00:00Z"
    assert source["status"] == "expired"
    assert source["freshness_basis"] == "source_review_not_after"
    assert source["review_not_after"] == "2026-08-10T02:00:00Z"


def test_role_uses_bound_kol_identity_not_free_text():
    snapshot = _build(
        sources=[
            _source(
                source_key="other",
                kol_id="kol-other",
                subject="马车主题观察",
                report_title="马车主题观察",
            )
        ],
        draft=_draft(source_keys=["other"]),
    )

    theme = snapshot.to_dict()["themes"][0]

    assert theme["source_evidence"][0]["role"] == "other_kol"
    assert theme["mache_support"]["status"] == "none"


def test_missing_kol_identity_is_rejected():
    with pytest.raises(PublicationBindingError, match="stable KOL identity"):
        _build(
            sources=[_source(source_key="other", kol_id="")],
            draft=_draft(source_keys=["other"]),
        )


def test_mismatched_report_and_viewpoint_kol_identity_is_rejected():
    with pytest.raises(PublicationBindingError, match="KOL identity"):
        _build(
            sources=[
                _source(
                    source_key="other",
                    kol_id="kol-report",
                    viewpoint_kol_id="kol-viewpoint",
                )
            ],
            draft=_draft(source_keys=["other"]),
        )


def test_receipt_report_identity_mismatch_is_rejected():
    with pytest.raises(PublicationBindingError, match="receipt record identity"):
        _build(
            sources=[
                _source(
                    source_key="other",
                    kol_id="kol-other",
                    receipt_record_id="wrong-report-id",
                )
            ],
            draft=_draft(source_keys=["other"]),
        )


def test_receipt_manifest_hash_mismatch_is_rejected():
    with pytest.raises(PublicationBindingError, match="manifest hash mismatch"):
        _build(
            sources=[
                _source(
                    source_key="other",
                    kol_id="kol-other",
                    receipt_manifest_sha256="wrong-manifest-hash",
                )
            ],
            draft=_draft(source_keys=["other"]),
        )


def test_evaluation_envelope_identity_mismatch_is_rejected():
    with pytest.raises(PublicationBindingError, match="evaluation identity"):
        _build(
            sources=[
                _source(
                    source_key="other",
                    kol_id="kol-other",
                    evaluation_payload_id="wrong-evaluation-id",
                )
            ],
            draft=_draft(source_keys=["other"]),
        )


def test_missing_theme_source_binding_does_not_attach_every_published_source():
    draft = _draft(other_kol={})
    draft["themes"][0].pop("source_keys")

    snapshot = _build(
        draft=draft,
        sources=[
            _source(source_key="xiaocao", kol_id="kol-xiaocao", theme_id=""),
            _source(source_key="mache", kol_id="kol-lv-xiaotong", theme_id=""),
            _source(source_key="other", kol_id="kol-other", theme_id=""),
        ],
    )
    theme = snapshot.to_dict()["themes"][0]

    assert theme["source_evidence"] == []
    assert theme["eligibility"] == "wait"
    assert theme["eligibility_reason"] == "no_current_bound_source"


def test_conflict_is_explicit_and_does_not_average_into_a_bullish_vote():
    snapshot = _build(draft=_draft(eligibility="conflicted"))

    theme = snapshot.to_dict()["themes"][0]

    assert theme["eligibility"] == "conflicted"
    assert theme["direction"] == "bullish"
    assert theme["confidence"] == 0.8


def test_conflicted_evaluation_is_preserved_as_theme_conflict():
    snapshot = _build(
        sources=[
            _source(
                source_key="other",
                kol_id="kol-other",
                evaluation_status="conflicted",
            )
        ],
        draft=_draft(source_keys=["other"], eligibility="eligible"),
    )

    theme = snapshot.to_dict()["themes"][0]

    assert theme["eligibility"] == "conflicted"
    assert theme["eligibility_reason"] == "bound_source_conflict"
    assert theme["source_evidence"][0]["status"] == "conflicted"
    assert theme["source_evidence"][0]["current"] is False


def test_market_invalidation_is_a_hard_theme_state():
    snapshot = _build(market=_market(status="invalidate"))

    theme = snapshot.to_dict()["themes"][0]

    assert theme["eligibility"] == "invalidated"
    assert theme["eligibility_reason"] == "market_validation_invalidated"


def test_invalidated_current_viewpoint_does_not_remain_a_theme_support():
    snapshot = _build(
        sources=[
            _source(
                source_key="mache",
                kol_id="kol-lv-xiaotong",
                evaluation_status="invalidated",
            )
        ],
        draft=_draft(source_keys=["mache"]),
    )

    theme = snapshot.to_dict()["themes"][0]

    assert theme["eligibility"] == "invalidated"
    assert theme["eligibility_reason"] == "all_bound_sources_invalidated"


def test_expired_mache_support_is_removed_without_forcing_a_sell():
    snapshot = _build(
        sources=[
            _source(
                source_key="xiaocao",
                kol_id="kol-xiaocao",
                theme_id="theme-ai",
                published_at="2026-08-01T02:00:00Z",
            ),
            _source(
                source_key="mache",
                kol_id="kol-lv-xiaotong",
                published_at="2026-07-01T02:00:00Z",
                evaluated_at="2026-08-16T02:00:00Z",
            ),
        ],
        draft=_draft(source_keys=["xiaocao", "mache"]),
        as_of=AS_OF,
    )

    theme = snapshot.to_dict()["themes"][0]

    assert theme["mache_support"]["status"] == "expired"
    assert theme["eligibility"] == "eligible"
    assert "sell" not in str(theme).lower()


def test_replaced_viewpoint_is_not_used_as_current_support():
    old = _source(
        source_key="old-mache",
        kol_id="kol-lv-xiaotong",
        published_at="2026-07-01T02:00:00Z",
        evaluated_at="2026-08-16T02:00:00Z",
        binding_suffix="old-mache",
    )
    new = _source(
        source_key="new-mache",
        kol_id="kol-lv-xiaotong",
        published_at="2026-08-10T02:00:00Z",
        evaluated_at="2026-08-16T02:00:00Z",
        binding_suffix="new-mache",
    )
    old_viewpoint = next(
        row for row in old["artifact"]["records"] if row["kind"] == "viewpoint"
    )
    new_viewpoint = next(
        row for row in new["artifact"]["records"] if row["kind"] == "viewpoint"
    )
    binding = new["artifact"]["records"][0]["source_binding"]
    relation_payload = {
        "relation_id": relation_id(
            new_viewpoint["record_id"],
            old_viewpoint["record_id"],
            "replaces",
            "2026-08-10T02:01:00Z",
        ),
        "from_viewpoint_id": new_viewpoint["record_id"],
        "to_viewpoint_id": old_viewpoint["record_id"],
        "relation_type": "replaces",
        "asserted_at": "2026-08-10T02:01:00Z",
        "reason": "新发布替代旧主题池。",
    }
    relation = build_record(
        kind="viewpoint_relation",
        record_id_value=relation_payload["relation_id"],
        idempotency_key="put-replacement-relation",
        created_at="2026-08-10T02:01:00Z",
        source_binding=binding,
        payload=relation_payload,
    )
    new_records = [*new["artifact"]["records"], relation]
    new_request = build_publish_request(
        new_records,
        idempotency_key="publish-new-mache-with-replacement",
        reason="replacement",
    )
    new["artifact"] = {"records": new_records, "publish_request": new_request}
    new["publish_receipt"]["manifestSha256"] = new_request["manifest_sha256"]

    snapshot = _build(
        sources=[old, new],
        draft=_draft(source_keys=["old-mache", "new-mache"]),
    )
    mache = snapshot.to_dict()["themes"][0]["mache_support"]

    assert mache["status"] == "active"
    assert mache["viewpoint_ids"] == [new_viewpoint["record_id"]]
    assert old_viewpoint["record_id"] in mache["replaced_viewpoint_ids"]
    new_evidence = next(
        row for row in mache["source_evidence"] if row["source_key"] == "new-mache"
    )
    assert new_evidence["relations"] == [
        {
            "relation_id": relation_payload["relation_id"],
            "from_viewpoint_id": new_viewpoint["record_id"],
            "to_viewpoint_id": old_viewpoint["record_id"],
            "relation_type": "replaces",
            "asserted_at": "2026-08-10T02:01:00Z",
        }
    ]

    bad_relation = build_record(
        kind="viewpoint_relation",
        record_id_value=relation_payload["relation_id"],
        idempotency_key="put-replacement-relation-wrong-binding",
        created_at="2026-08-10T02:00:00Z",
        source_binding=old["artifact"]["records"][0]["source_binding"],
        payload=relation_payload,
    )
    bad_records = [*new_records[:-1], bad_relation]
    bad_request = build_publish_request(
        bad_records,
        idempotency_key="publish-new-mache-wrong-relation-binding",
        reason="replacement",
    )
    bad_source = dict(new)
    bad_source["artifact"] = {"records": bad_records, "publish_request": bad_request}
    bad_source["publish_receipt"] = {
        **new["publish_receipt"],
        "manifestSha256": bad_request["manifest_sha256"],
    }
    with pytest.raises(PublicationBindingError, match="relation source binding"):
        _build(
            sources=[old, bad_source],
            draft=_draft(source_keys=["old-mache", "new-mache"]),
        )

    unknown_relation_payload = {
        **relation_payload,
        "relation_id": relation_id(
            new_viewpoint["record_id"],
            "unbound-viewpoint",
            "replaces",
            "2026-08-10T02:02:00Z",
        ),
        "to_viewpoint_id": "unbound-viewpoint",
        "asserted_at": "2026-08-10T02:02:00Z",
    }
    unknown_relation = build_record(
        kind="viewpoint_relation",
        record_id_value=unknown_relation_payload["relation_id"],
        idempotency_key="put-replacement-relation-unbound-target",
        created_at="2026-08-10T02:02:00Z",
        source_binding=binding,
        payload=unknown_relation_payload,
    )
    unknown_records = [*new_records[:-1], unknown_relation]
    unknown_request = build_publish_request(
        unknown_records,
        idempotency_key="publish-new-mache-unbound-target",
        reason="replacement",
    )
    unknown_source = dict(new)
    unknown_source["artifact"] = {
        "records": unknown_records,
        "publish_request": unknown_request,
    }
    unknown_source["publish_receipt"] = {
        **new["publish_receipt"],
        "manifestSha256": unknown_request["manifest_sha256"],
    }
    with pytest.raises(PublicationBindingError, match="relation target viewpoint is not bound"):
        _build(
            sources=[old, unknown_source],
            draft=_draft(source_keys=["old-mache", "new-mache"]),
        )

    future_relation_payload = {
        **relation_payload,
        "relation_id": relation_id(
            new_viewpoint["record_id"],
            old_viewpoint["record_id"],
            "replaces",
            "2026-08-17T02:01:00Z",
        ),
        "asserted_at": "2026-08-17T02:01:00Z",
    }
    future_relation = build_record(
        kind="viewpoint_relation",
        record_id_value=future_relation_payload["relation_id"],
        idempotency_key="put-replacement-relation-future",
        created_at="2026-08-17T02:01:00Z",
        source_binding=binding,
        payload=future_relation_payload,
    )
    future_records = [*new_records[:-1], future_relation]
    future_request = build_publish_request(
        future_records,
        idempotency_key="publish-new-mache-future-relation",
        reason="replacement",
    )
    future_source = dict(new)
    future_source["artifact"] = {
        "records": future_records,
        "publish_request": future_request,
    }
    future_source["publish_receipt"] = {
        **new["publish_receipt"],
        "manifestSha256": future_request["manifest_sha256"],
    }
    with pytest.raises(PublicationBindingError, match="future-dated"):
        _build(
            sources=[old, future_source],
            draft=_draft(source_keys=["old-mache", "new-mache"]),
        )


def test_publication_prepared_without_receipt_is_rejected():
    source = _source(source_key="mache", kol_id="kol-lv-xiaotong")
    source.pop("publish_receipt")

    with pytest.raises(PublicationBindingError, match="publication receipt"):
        _build(sources=[source], draft=_draft(source_keys=["mache"]))


def test_agent_draft_cannot_supply_business_or_evidence_identity():
    draft = _draft()
    draft["themes"][0]["publication_id"] = "forged-publication"

    with pytest.raises(TrendSnapshotError, match="forbidden business identity"):
        _build(draft=draft)


def test_other_kol_without_horizon_uses_explicit_rapid_decay():
    snapshot = _build(
        sources=[
            _source(
                source_key="xiaocao",
                kol_id="kol-xiaocao",
                published_at="2026-08-01T02:00:00Z",
                evaluated_at="2026-08-02T02:00:00Z",
            ),
            _source(
                source_key="other",
                kol_id="kol-other",
                horizon=None,
                published_at="2026-08-01T02:00:00Z",
                evaluated_at="2026-08-02T02:00:00Z",
            ),
        ],
        draft=_draft(source_keys=["xiaocao", "other"]),
        as_of="2026-08-03T02:00:00Z",
    )

    other = snapshot.to_dict()["themes"][0]["other_kol"]["confirmations"][0]

    assert other["current"] is False
    assert other["freshness_basis"] == "missing_horizon_rapid_decay_1d"
    assert other["status"] == "stale"


def test_other_kol_horizon_requires_machine_review_deadline():
    snapshot = _build(
        sources=[
            _source(
                source_key="other",
                kol_id="kol-other",
                horizon=["未来两周"],
            )
        ],
        draft=_draft(source_keys=["other"], review_not_after=None),
    )

    other = snapshot.to_dict()["themes"][0]["other_kol"]["confirmations"][0]

    assert other["current"] is False
    assert other["status"] == "pending"
    assert other["freshness_basis"] == "horizon_requires_machine_review_not_after"


def test_other_kol_horizon_deadline_controls_freshness_without_parsing_text():
    snapshot = _build(
        sources=[
            _source(
                source_key="other",
                kol_id="kol-other",
                horizon=["未来两周"],
                evaluated_at="2026-08-02T02:00:00Z",
                evaluation_review_not_after="2026-08-10T02:00:00Z",
            )
        ],
        draft=_draft(source_keys=["other"], review_not_after=None),
    )

    theme = snapshot.to_dict()["themes"][0]
    other = theme["other_kol"]["confirmations"][0]

    assert other["current"] is False
    assert other["status"] == "stale"
    assert other["freshness_basis"] == "source_review_not_after"
    assert other["source_evidence"]["horizon"] == ["未来两周"]
    assert other["source_evidence"]["review_not_after"] == "2026-08-10T02:00:00Z"


def test_xiaocao_horizon_requires_machine_review_deadline():
    snapshot = _build(
        sources=[
            _source(
                source_key="xiaocao",
                kol_id="kol-xiaocao",
                horizon=["当前阶段"],
            )
        ],
        draft=_draft(source_keys=["xiaocao"], review_not_after=None),
    )

    source = snapshot.to_dict()["themes"][0]["source_evidence"][0]

    assert source["role"] == "xiaocao"
    assert source["current"] is False
    assert source["status"] == "pending"
    assert source["freshness_basis"] == "horizon_requires_machine_review_not_after"


def test_snapshot_replay_is_deterministic_when_generation_time_is_bound():
    first = _build()
    second = _build()

    assert first == second
    assert hash(first) == hash(second)
    assert first.to_dict() == second.to_dict()
