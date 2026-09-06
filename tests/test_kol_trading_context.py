"""Small redacted publication fixtures; no live MCP or business writer."""

from __future__ import annotations

import copy
import importlib.util
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.kol import trading_context as tc
from xiaocao.kol.publication import (
    canonical_bytes,
    canonical_sha256,
    manifest_entries,
    manifest_sha256,
    record_content_sha256,
    report_id,
)


OBSERVED = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
CREATED = "2026-09-05T01:00:00Z"


class Clock:
    def __init__(self):
        self.now = OBSERVED

    def __call__(self):
        return self.now


def envelope(kind, rid, binding, payload, created_at=CREATED):
    record = {
        "schema_version": 1, "kind": kind, "record_id": rid,
        "idempotency_key": "redacted-fixture-" + rid,
        "created_at": created_at, "source_binding": binding, "payload": payload,
    }
    record["content_sha256"] = record_content_sha256(record)
    return record


def publication(author="甲作者", day=5, *, viewpoints=2):
    identity = f"redacted:{author}:{day}"
    rid = report_id(identity)
    binding = {"publication_id": identity, "publication_version": "fixture-v1",
               "evidence_sha256": "a" * 64, "decision_result_sha256": "b" * 64}
    source_time = f"2026-09-{day:02}T00:00:00Z"
    records = []
    ids = [f"vp-{rid}-{i}" for i in range(viewpoints)]
    report = envelope("report", rid, binding, {
        "report_id": rid, "report_kind": "publication_event", "kol_id": "kol-" + author,
        "author": author, "source": "脱敏已发布正文", "title": f"{author}观点记录",
        "summary": "这段摘要不能代替正文。", "source_published_at": source_time,
        "report_body": "# 完整正文\n\n第一段条件与证据。\n\n最后一段保留反例及不确定性。",
        "viewpoint_ids": ids,
    })
    records.append(report)
    for i, vid in enumerate(ids):
        records.append(envelope("viewpoint", vid, binding, {
            "viewpoint_id": vid, "report_id": rid, "kol_id": "kol-" + author,
            "subject": "跨周期行业观点", "stance": "观点的完整条件和边界。",
            "source_published_at": source_time, "horizon": "直到明确反证出现",
            "falsifiers": ["前提发生变化"], "evidence_refs": [{"excerpt": "完整来源论述"}],
        }))
        for n, status in enumerate(["current", "expired"] if i == 0 else ["current"]):
            eid = f"ve-{vid}-{n}"
            evaluation_time = f"2026-09-05T0{n + 1}:00:00Z"
            records.append(envelope("viewpoint_evaluation", eid, binding, {
                "evaluation_id": eid, "viewpoint_id": vid, "status": status,
                "as_of": evaluation_time, "evaluated_at": evaluation_time,
                "basis": "完整评估依据", "uncertainties": ["证据仍有边界"],
            }))
    if len(ids) > 1:
        relation_id = "vr-" + rid
        records.append(envelope("viewpoint_relation", relation_id, binding, {
            "relation_id": relation_id, "from_viewpoint_id": ids[1],
            "to_viewpoint_id": ids[0], "relation_type": "refines",
            "asserted_at": CREATED, "reason": "保留前提并补充边界。",
        }))
    return records


def register(root, publications, path="output/live/kol_daily/publications/events.jsonl"):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for records in publications:
        report = records[0]
        rid = report["record_id"]
        request = {"schema_version": 1, "idempotency_key": "redacted-publish-" + rid,
                   "report_id": rid, "report_content_sha256": report["content_sha256"],
                   "records": manifest_entries(records), "manifest_sha256": manifest_sha256(manifest_entries(records))}
        artifact = {"records": records, "publish_request": request, "metadata": {}}
        events = [
            {"event": "publication_prepared", "artifact": artifact, "artifact_sha256": canonical_sha256(artifact)},
            {"event": "publication_receipt", "receipt": {
                "recordId": rid, "contentSha256": report["content_sha256"],
                "manifestSha256": request["manifest_sha256"], "recordState": "published",
                "detailUrl": f"https://example.test/kol-reports/{rid}",
            }},
        ]
        for event in events:
            row = {"schema_version": 1, "publication_key": rid,
                   "occurred_at": "2026-09-05T03:00:00Z", **event}
            rows.append({**row, "event_id": canonical_sha256(row)})
    target.write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in rows))
    return target


class Reader:
    def __init__(self, publications):
        self.publications = {r[0]["record_id"]: r for r in publications}
        self.calls = []
        self.fail = False
        self.fail_authors = set()

    def call_tool(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        assert name == "get_kol_record", "A business write tool must never be called"
        if self.fail:
            raise OSError("Authorization: Bearer redacted-test-secret")
        if arguments["kind"] == "report":
            records = self.publications[arguments["record_id"]]
            if records[0]["payload"]["author"] in self.fail_authors:
                raise OSError("redacted-test-secret")
            return {**copy.deepcopy(records[0]), "state": "published",
                    "manifest": manifest_entries(records),
                    "manifest_sha256": manifest_sha256(manifest_entries(records)),
                    "published_at": CREATED, "updated_at": CREATED,
                    "Authorization": "Bearer redacted-test-secret"}
        return copy.deepcopy(next(r for rows in self.publications.values() for r in rows
                                  if all(r[k] == arguments[k] for k in ("kind", "record_id", "content_sha256"))))


def build(root, reader, clock, **kwargs):
    return tc.build_trading_context(repo_root=root, client=reader, clock=clock, **kwargs)


def codes(context):
    return {r["code"] for r in context["coverage"]["incomplete_reasons"]}


def test_complete_multi_viewpoint_evaluation_relation_and_author_coverage(tmp_path):
    items = [publication("甲作者"), publication("乙作者")]
    ledger = register(tmp_path, items)
    before = ledger.read_bytes()
    reader, clock = Reader(items), Clock()
    context = build(tmp_path, reader, clock, registered_authors=["丙作者"])
    assert len(context["reports"]) == 2
    assert len(context["viewpoints"]) == 4
    assert len(context["evaluations"]) == 6
    assert len(context["relations"]) == 2
    assert context["coverage"]["covered_authors"] == ["乙作者", "甲作者"]
    assert context["coverage"]["missing_authors"] == ["丙作者"]
    assert context["coverage"]["remote_discovery"] == "registry_only"
    assert context["coverage"]["incomplete"] is True
    for row in context["reports"]:
        original = reader.publications[row["report_id"]][0]
        assert row["report"] == original
        assert row["report_body"] == original["payload"]["report_body"]
        assert row["received_at"] == tc._iso(OBSERVED)
        assert row["received_at"] != row["source_published_at"]
    for row in context["viewpoints"] + context["evaluations"] + context["relations"]:
        assert set(("author", "source_published_at", "received_at", "report_id", "content_sha256", "url")) <= row.keys()
    assert {v["latest_status"] for v in context["viewpoints"]} == {"current", "expired"}
    assert len(context["current_viewpoint_ids"]) == 2
    assert ledger.read_bytes() == before
    assert not (ledger.parent / ".lock").exists()
    assert {name for name, _ in reader.calls} == {"get_kol_record"}


def test_all_registered_long_term_views_survive_latest_three_body_selection(tmp_path):
    items = [publication("甲作者", day) for day in range(1, 6)] + [publication("乙作者", 1)]
    register(tmp_path, items)
    reader, clock = Reader(items), Clock()
    context = build(tmp_path, reader, clock)
    assert len(context["reports"]) == 4
    assert len(context["viewpoints"]) == 12
    oldest = items[0][0]["record_id"]
    assert oldest in context["unloaded_report_ids"]
    old_index = next(r for r in context["report_index"] if r["report_id"] == oldest)
    assert old_index["longitudinal_loaded"] is True
    assert old_index["not_loaded_reason"] == "report_body_not_selected"
    assert any(v["report_id"] == oldest and v["latest_status"] == "current" for v in context["viewpoints"])
    selected = build(tmp_path, reader, clock, report_ids=[oldest])
    assert len(selected["reports"]) == 5
    assert oldest not in selected["unloaded_report_ids"]


def test_registry_is_explicit_and_extra_ledgers_extend_it(tmp_path):
    production, extra, sandbox = publication("甲作者"), publication("乙作者"), publication("沙箱作者")
    register(tmp_path, [production])
    extra_path = register(tmp_path, [extra], "output/live/approved-extra/events.jsonl")
    register(tmp_path, [sandbox], "output/live/acceptance/sandbox/publications/events.jsonl")
    reader = Reader([production, extra, sandbox])
    context = build(tmp_path, reader, Clock(), ledger_paths=[extra_path])
    assert context["coverage"]["registered_authors"] == ["乙作者", "甲作者"]
    assert sandbox[0]["record_id"] not in {args["record_id"] for _, args in reader.calls}


@pytest.mark.parametrize("corruption", ["report_hash", "record_hash", "manifest_hash", "wrong_report", "unpublished"])
def test_remote_hash_and_identity_fail_closed(tmp_path, corruption):
    item = publication()
    register(tmp_path, [item])
    base = Reader([item])

    class Corrupt:
        def call_tool(self, name, arguments):
            value = base.call_tool(name, arguments)
            if arguments["kind"] == "report":
                if corruption == "report_hash":
                    value["payload"]["report_body"] += "未被哈希绑定的文字"
                elif corruption == "manifest_hash":
                    value["manifest_sha256"] = "0" * 64
                elif corruption == "wrong_report":
                    value["record_id"] = "kr-wrong"
                    value["content_sha256"] = record_content_sha256(value)
                elif corruption == "unpublished":
                    value["state"] = "staged"
            elif corruption == "record_hash":
                value["payload"]["unexpected"] = "hash mismatch"
            return value

    context = build(tmp_path, Corrupt(), Clock())
    assert context["reports"] == context["viewpoints"] == []
    assert context["coverage"]["missing_authors"] == ["甲作者"]
    assert "publication_read_or_hash_validation_failed" in codes(context)


def test_future_as_of_rejected_before_network_and_cache(tmp_path):
    reader = Reader([])
    with pytest.raises(tc.TradingContextError, match="future_as_of_forbidden"):
        build(tmp_path, reader, Clock(), as_of=OBSERVED + timedelta(seconds=1))
    assert reader.calls == []
    assert not (tmp_path / tc.CACHE_RELATIVE_PATH).exists()


def test_historical_cutoff_cannot_backdate_first_observation(tmp_path):
    item = publication()
    register(tmp_path, [item])
    context = build(tmp_path, Reader([item]), Clock(), as_of=OBSERVED - timedelta(seconds=1))
    assert context["reports"] == []
    assert "publication_not_observed_as_of" in codes(context)


@pytest.mark.parametrize("field", ["source", "created", "evaluation", "evaluation_as_of", "relation"])
def test_future_source_and_evaluation_records_never_enter_context(tmp_path, field):
    item = publication()
    register(tmp_path, [item])
    future = "2026-09-07T00:00:00Z"
    if field == "source":
        item[0]["payload"]["source_published_at"] = future
    elif field == "created":
        item[0]["created_at"] = future
    elif field in {"evaluation", "evaluation_as_of"}:
        evaluation = next(r for r in item if r["kind"] == "viewpoint_evaluation")
        evaluation["payload"]["evaluated_at" if field == "evaluation" else "as_of"] = future
    else:
        item[-1]["payload"]["asserted_at"] = future
    for record in item:
        record["content_sha256"] = record_content_sha256(record)
    context = build(tmp_path, Reader([item]), Clock())
    assert context["reports"] == []
    assert "future_publication_forbidden" in codes(context)


def test_cache_is_idempotent_hash_bound_and_credential_free(tmp_path):
    item = publication()
    register(tmp_path, [item])
    reader, clock = Reader([item]), Clock()
    first = build(tmp_path, reader, clock)
    directory = tmp_path / tc.CACHE_RELATIVE_PATH
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.glob("*.json")}
    count = len(reader.calls)
    reader.fail = True
    second = build(tmp_path, reader, clock)
    assert second == first
    assert len(reader.calls) == count
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.glob("*.json")}
    unsigned = dict(first)
    digest = unsigned.pop("context_sha256")
    assert canonical_sha256(unsigned) == digest
    assert b"redacted-test-secret" not in b"".join(p.read_bytes() for p in directory.glob("*.json"))
    rejected = build(tmp_path, reader, clock, refresh=True)
    assert rejected["reports"] == []
    assert "redacted-test-secret" not in json.dumps(rejected)
    assert "remote_read_failed" in codes(rejected)
    retried = build(tmp_path, reader, clock)
    assert retried["reports"] == []  # A failed refresh invalidates the old TTL.
    assert "remote_read_failed" in codes(retried)
    reader.fail = False
    recovered = build(tmp_path, reader, clock)
    assert recovered["reports"][0]["received_at"] == first["reports"][0]["received_at"]


def test_expired_cache_requires_refresh_and_failure_is_not_no_new_viewpoint(tmp_path):
    item = publication()
    register(tmp_path, [item])
    reader, clock = Reader([item]), Clock()
    build(tmp_path, reader, clock)
    clock.now += timedelta(minutes=10)
    reader.fail = True
    context = build(tmp_path, reader, clock)
    assert context["reports"] == []
    assert context["coverage"]["registered_longitudinal_complete"] is False
    assert context["coverage"]["missing_authors"] == ["甲作者"]
    assert "remote_read_failed" in codes(context)


def test_corrupt_cache_rebuild_does_not_restore_old_first_observed_time(tmp_path):
    item = publication()
    register(tmp_path, [item])
    reader, clock = Reader([item]), Clock()
    build(tmp_path, reader, clock)
    cached = next((tmp_path / tc.CACHE_RELATIVE_PATH).glob("*.cache.json"))
    cached.write_text("{broken", encoding="utf-8")
    clock.now += timedelta(minutes=1)
    context = build(tmp_path, reader, clock)
    assert "cache_invalid_rebuild_required" in codes(context)
    assert context["reports"][0]["received_at"] == tc._iso(clock.now)


def test_corrected_current_hash_is_reverified_and_observation_times_are_distinct(tmp_path):
    item = publication()
    register(tmp_path, [item])
    reader, clock = Reader([item]), Clock()
    initial = build(tmp_path, reader, clock)
    clock.now += timedelta(minutes=1)
    item[0]["payload"]["report_body"] += "\n\n更正后的完整补充。"
    item[0]["content_sha256"] = record_content_sha256(item[0])
    revised = build(tmp_path, reader, clock, refresh=True)
    before, after = initial["reports"][0], revised["reports"][0]
    assert after["content_sha256"] != before["content_sha256"]
    assert after["received_at"] == before["received_at"]
    assert after["version_received_at"] == tc._iso(clock.now)
    historical = build(tmp_path, reader, clock, as_of=OBSERVED)
    assert historical["reports"] == []


def test_uncertain_and_expired_latest_evaluations_are_never_promoted_by_age(tmp_path):
    item = publication()
    target = next(r for r in item if r["kind"] == "viewpoint_evaluation" and r["payload"]["viewpoint_id"].endswith("-1"))
    target["payload"]["status"] = "uncertain"
    target["content_sha256"] = record_content_sha256(target)
    register(tmp_path, [item])
    clock = Clock()
    clock.now += timedelta(days=100)
    context = build(tmp_path, Reader([item]), clock)
    assert {v["latest_status"] for v in context["viewpoints"]} == {"uncertain", "expired"}
    assert context["current_viewpoint_ids"] == []


def test_relations_and_evaluations_across_registered_reports_are_preserved(tmp_path):
    older, newer = publication(day=1), publication(day=5)
    old_viewpoint = older[1]["record_id"]
    # A newer manifest may carry a later evaluation of an older report's view.
    extra = envelope("viewpoint_evaluation", "ve-cross-report", newer[0]["source_binding"], {
        "evaluation_id": "ve-cross-report", "viewpoint_id": old_viewpoint,
        "status": "uncertain", "as_of": "2026-09-05T04:00:00Z",
        "evaluated_at": "2026-09-05T04:00:00Z", "basis": "补充新证据后暂不确定。",
    })
    newer[-1]["payload"]["to_viewpoint_id"] = old_viewpoint
    newer[-1]["content_sha256"] = record_content_sha256(newer[-1])
    newer.append(extra)
    register(tmp_path, [older, newer])
    context = build(tmp_path, Reader([older, newer]), Clock(), latest_per_author=1)
    row = next(v for v in context["viewpoints"] if v["record_id"] == old_viewpoint)
    assert row["latest_status"] == "uncertain"
    assert row["latest_evaluation_ids"] == ["ve-cross-report"]
    assert len(context["evaluations"]) == 7
    assert "relation_viewpoints_not_loaded" not in codes(context)


def test_family_transport_is_lazy_reused_and_cache_never_reads_config(tmp_path, monkeypatch):
    item = publication()
    register(tmp_path, [item])
    reader, calls = Reader([item]), []

    def from_config():
        calls.append("existing-family-config-loader")
        return reader

    monkeypatch.setattr(tc.LiangHuiMcpClient, "from_config", from_config)
    first = build(tmp_path, None, Clock())
    second = build(tmp_path, None, Clock())
    assert first == second
    assert calls == ["existing-family-config-loader"]
    assert {name for name, _ in reader.calls} == {"get_kol_record"}


def test_exact_read_batches_resume_only_named_sources_and_summary_keeps_bodies_on_disk(tmp_path):
    items = [publication("甲作者"), publication("乙作者")]
    register(tmp_path, items)
    reader, clock = Reader(items), Clock()
    first_id, second_id = [r[0]["record_id"] for r in items]
    first = build(tmp_path, reader, clock, read_report_ids=[first_id])
    assert first["coverage"]["missing_authors"] == ["乙作者"]
    first_calls = len(reader.calls)
    second = build(tmp_path, reader, clock, read_report_ids=[second_id], refresh=True)
    new_calls = reader.calls[first_calls:]
    assert all(args["record_id"] != first_id for _, args in new_calls)
    assert second["coverage"]["missing_authors"] == []
    count = len(reader.calls)
    cached = build(tmp_path, reader, clock, read_report_ids=[])
    assert len(reader.calls) == count
    compact = tc.summarize_context(cached, repo_root=tmp_path)
    assert Path(compact["context_path"]).is_file()
    assert "report_body" not in json.dumps(compact)
    for row in cached["reports"]:
        assert Path(row["report_body_path"]).read_text(encoding="utf-8") == row["report_body"]


def test_display_author_update_is_grouped_by_stable_kol_id(tmp_path):
    items = [publication("甲作者", 4), publication("甲作者", 5)]
    register(tmp_path, items)
    # A current remote report's name can change without changing its identity.
    items[1][0]["payload"]["author"] = "甲作者新名称"
    items[1][0]["content_sha256"] = record_content_sha256(items[1][0])
    context = build(tmp_path, Reader(items), Clock(), registered_authors=["甲作者"])
    assert len(context["reports"]) == 2
    assert context["coverage"]["registered_authors"] == ["甲作者新名称"]
    assert context["coverage"]["missing_authors"] == []
    identity = context["coverage"]["author_identities"]["kol-甲作者"]
    assert identity["aliases"] == ["甲作者", "甲作者新名称"]
    assert {r["report"]["payload"]["author"] for r in context["reports"]} == {"甲作者", "甲作者新名称"}


def test_history_has_independent_ttl_and_dated_evaluations_are_not_current_support(tmp_path):
    items = [publication("甲作者", 1), publication("甲作者", 5)]
    register(tmp_path, items)
    reader, clock = Reader(items), Clock()
    build(tmp_path, reader, clock, latest_per_author=1)
    clock.now += timedelta(minutes=10)
    reader.calls.clear()
    context = build(tmp_path, reader, clock, latest_per_author=1)
    report_reads = [a["record_id"] for _, a in reader.calls if a["kind"] == "report"]
    assert report_reads == [items[1][0]["record_id"]]
    old = next(r for r in context["report_index"] if r["report_id"] == items[0][0]["record_id"])
    assert old["verification_age_seconds"] == 600
    assert old["evidence_mode"] == "persistent_verified_history"
    old_views = [v for v in context["viewpoints"] if v["report_id"] == old["report_id"]]
    assert any(v["latest_status"] == "current" for v in old_views)
    assert not any(v["current_support_eligible"] for v in old_views)
    assert context["coverage"]["history_max_cache_age_seconds"] == 86400
    reader.calls.clear()
    build(tmp_path, reader, clock, latest_per_author=1, refresh=True)
    assert len([a for _, a in reader.calls if a["kind"] == "report"]) == 2


def test_automatic_read_budget_exceeds_old_256_cap_for_registered_manifests(tmp_path):
    items = [publication(f"脱敏作者{i}") for i in range(40)]
    register(tmp_path, items)
    reader = Reader(items)
    context = build(tmp_path, reader, Clock())
    assert len(reader.calls) == 280
    assert context["coverage"]["registered_longitudinal_complete"] is True
    assert len(context["report_index"]) == 40


def test_cache_only_keeps_dated_context_but_marks_selected_freshness_missing(tmp_path):
    item = publication()
    register(tmp_path, [item])
    reader, clock = Reader([item]), Clock()
    build(tmp_path, reader, clock)
    clock.now += timedelta(minutes=10)
    reader.calls.clear()
    context = build(tmp_path, reader, clock, read_report_ids=[])
    assert reader.calls == []
    assert context["reports"]
    assert context["coverage"]["selected_reports_fresh"] is False
    assert "selected_report_refresh_required" in codes(context)
    assert context["current_support_viewpoint_ids"] == []


def test_event_date_annotation_keeps_canonical_publication_date_and_hash(tmp_path):
    import hashlib

    origin = tmp_path / "redacted-transcript.txt"
    origin.write_text("脱敏的完整原始证据。", encoding="utf-8")
    item = publication()
    for r in item:
        r["source_binding"]["evidence_sha256"] = hashlib.sha256(origin.read_bytes()).hexdigest()
        r["content_sha256"] = record_content_sha256(r)
    register(tmp_path, [item])
    reader, clock = Reader([item]), Clock()
    first = build(tmp_path, reader, clock)
    record = first["reports"][0]
    tc.cache_report_event_date(report_id=record["report_id"], report_content_sha256=record["content_sha256"],
                              event_date="2026-09-04", origin_path=origin, repo_root=tmp_path)
    context = build(tmp_path, reader, clock, read_report_ids=[])
    annotated = context["reports"][0]
    assert annotated["source_event_annotation"]["source_event_date"] == "2026-09-04"
    assert annotated["source_published_at"] == record["source_published_at"]
    assert annotated["report"] == record["report"]
    assert annotated["content_sha256"] == record["content_sha256"]


def test_partial_author_failure_keeps_other_author_and_marks_missing(tmp_path):
    items = [publication("甲作者"), publication("乙作者")]
    register(tmp_path, items)
    reader = Reader(items)
    reader.fail_authors.add("甲作者")
    context = build(tmp_path, reader, Clock())
    assert context["coverage"]["covered_authors"] == ["乙作者"]
    assert context["coverage"]["missing_authors"] == ["甲作者"]


def test_transport_bounded_timeout_retries_and_no_write_tools():
    release = threading.Event()
    calls = []

    class HangingReader:
        def call_tool(self, name, arguments):
            calls.append(name)
            release.wait(2)
            return {}

    transport = tc.ReadOnlyPublicationTransport(HangingReader(), timeout_seconds=0.01,
        retries=1, max_read_calls=2, total_timeout_seconds=0.2)
    start = time.monotonic()
    try:
        with pytest.raises(tc.TradingContextError, match="remote_read_timeout"):
            transport.call_tool("get_kol_record", {"kind": "report", "record_id": "fixture"})
        assert time.monotonic() - start < 0.5
        assert calls == ["get_kol_record", "get_kol_record"]
        with pytest.raises(tc.TradingContextError, match="read_only_tool_required"):
            transport.call_tool("put_kol_record", {"kind": "report"})
        assert len(calls) == 2
    finally:
        release.set()


def test_global_budget_limits_reads_and_surfaces_incomplete_longitudinal_context(tmp_path):
    items = [publication("甲作者", 1), publication("乙作者", 1)]
    register(tmp_path, items)
    reader = Reader(items)
    context = build(tmp_path, reader, Clock(), max_read_calls=1)
    assert len(reader.calls) == 1
    assert "remote_read_budget_exhausted" in codes(context)
    assert context["coverage"]["registered_longitudinal_complete"] is False


def test_unregistered_id_never_becomes_remote_discovery(tmp_path):
    reader = Reader([])
    context = build(tmp_path, reader, Clock(), report_ids=["kr-not-registered"])
    assert reader.calls == []
    assert "report_id_not_registered" in codes(context)


def test_missing_and_invalid_ledgers_are_not_silently_empty(tmp_path):
    missing = tmp_path / "approved/events.jsonl"
    invalid = register(tmp_path, [publication()])
    invalid.write_text('{"event":"publication_receipt"}\n', encoding="utf-8")
    context = build(tmp_path, Reader([]), Clock(), ledger_paths=[missing])
    assert {"registered_ledger_missing", "registered_ledger_invalid"} <= codes(context)
    assert context["coverage"]["registered_longitudinal_complete"] is False


def test_cli_context_arguments_and_failure_output_are_credential_free(tmp_path, monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1] / "scripts/kol_trading_context.py"
    spec = importlib.util.spec_from_file_location("kol_context_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {"coverage": {"missing_authors": [], "registered_longitudinal_complete": True}}

    monkeypatch.setattr(cli, "build_trading_context", fake)
    assert cli.main(["context", "--ledger", "extra/events.jsonl", "--report-id", "kr-extra", "--author", "甲作者", "--refresh"]) == 0
    assert captured["ledger_paths"] == ["extra/events.jsonl"]
    assert captured["report_ids"] == ["kr-extra"]
    assert captured["registered_authors"] == ["甲作者"]
    assert captured["refresh"] is True
    capsys.readouterr()

    def broken(**kwargs):
        raise OSError("Authorization: Bearer redacted-test-secret")

    monkeypatch.setattr(cli, "build_trading_context", broken)
    assert cli.main(["context"]) == 2
    assert "redacted-test-secret" not in capsys.readouterr().out
