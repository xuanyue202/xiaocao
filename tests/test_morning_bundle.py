from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from xiaocao.live.morning_bundle import (
    acquire_bundle, publish_bundle, publish_captured_batch, read_consumed_rows,
    recover_request, validate_components,
    publish_support, apply_support, resolve_receipt,
)
from xiaocao.live.trading_runner import frozen_rows_digest


DATE = "2026-09-30"


@pytest.fixture(autouse=True)
def producer_identity(monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-morning")
    monkeypatch.setenv("CODEX_THREAD_ID", "original-producer")


def original():
    rows = [{"date": DATE, "book": "B", "code": "000020.XSHE", "mode": "test",
        "is_live": True, "mode_exec_star": True, "mode_trade_eligible": True,
        "open": 13.71, "basket_price": 13.98}]
    snapshot = (json.dumps(rows[0]) + "\n").encode()
    report = b"# Original report\n"
    sha = frozen_rows_digest(rows)
    queue = {"schema_version": 2, "market_date": DATE, "status": "empty",
        "counts": {"selected_items": 0}, "items": [],
        "freeze_binding": {"strategy_run_id": "original-run", "strategy_sha": "a" * 40,
            "snapshot_sha256": sha, "snapshot_row_count": 1,
            "report_sha256": hashlib.sha256(report).hexdigest()}}
    capture = {"status": "captured", "market_date": DATE, "snapshot_sha256": sha}
    return snapshot, report, queue, capture


def publish(root, on_stage=None):
    snapshot, report, queue, capture = original()
    return publish_bundle(root, DATE, snapshot=snapshot, report=report,
        queue=queue, capture=capture, on_stage=on_stage)


@pytest.mark.parametrize("stage", ["checkpoint_committed", "snapshot_committed",
    "report_committed", "queue_committed", "ready_committed"])
def test_crash_at_each_publication_boundary_recovers_original(tmp_path, stage):
    def crash(value):
        if value == stage:
            raise OSError("injected producer crash")
    with pytest.raises(OSError):
        publish(tmp_path, crash)
    result = acquire_bundle(tmp_path, DATE)
    assert result["status"] == "ready"
    assert Path(result["snapshot_path"]).read_bytes() == original()[0]
    assert read_consumed_rows(result, DATE)[0]["code"] == "000020.XSHE"
    assert len(list(tmp_path.rglob("claim.json"))) == (0 if stage == "ready_committed" else 1)


@pytest.mark.parametrize("kind", ["snapshot", "report", "queue", "ready"])
@pytest.mark.parametrize("fault", ["missing", "half_written", "wrong_date"])
def test_conflicts_and_missing_files_restore_new_copy_without_overwriting(tmp_path, kind, fault):
    result = publish(tmp_path)
    path = (tmp_path / f"morning_bundle_ready_{DATE}.json" if kind == "ready"
        else Path(result[{"snapshot": "snapshot_path", "report": "report", "queue": "queue"}[kind]]))
    content = b'{"date":"2026-09-29"}' if fault == "wrong_date" else b'{"half":'
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(content)
    fixed = acquire_bundle(tmp_path, DATE)
    assert fixed["status"] == "ready"
    assert Path(fixed["snapshot_path"]).read_bytes() == original()[0]
    if kind != "ready" and fault != "missing":
        assert path.read_bytes() == content
    assert len(list(tmp_path.rglob("claim.json"))) == 1
    assert len(list(tmp_path.rglob("receipt.json"))) == 1


def test_two_consumers_share_one_repair_claim(tmp_path):
    result = publish(tmp_path)
    Path(result["snapshot_path"]).unlink()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: acquire_bundle(tmp_path, DATE), range(2)))
    assert {r["snapshot_path"] for r in results} == {results[0]["snapshot_path"]}
    assert all(r["snapshot_sha256"] == result["snapshot_sha256"] for r in results)
    assert len(list(tmp_path.rglob("claim.json"))) == 1


def test_corrupt_original_cannot_redefine_expected_hash(tmp_path):
    result = publish(tmp_path)
    commit_path = tmp_path / f"morning_bundle_commit_{DATE}.json"
    commit_bytes = commit_path.read_bytes()
    checkpoint = Path(json.loads(commit_bytes)["checkpoint_path"])
    checkpoint.write_bytes(b"unproved replacement")
    blocked = acquire_bundle(tmp_path, DATE)
    assert blocked["status"] == "repair_required"
    assert Path(blocked["request_path"]).exists()
    assert commit_path.read_bytes() == commit_bytes
    assert len(list(tmp_path.rglob("claim.json"))) == 0
    assert Path(result["snapshot_path"]).read_bytes() == original()[0]


def test_exact_request_recovery_and_second_batch_rejection(tmp_path):
    result = publish(tmp_path)
    Path(result["queue"]).unlink()
    request = acquire_bundle(tmp_path, DATE, repair=False)
    recovered = recover_request(Path(request["request_path"]), tmp_path)
    assert recovered["status"] == "ready"
    snapshot, report, queue, capture = original()
    queue["freeze_binding"]["strategy_run_id"] = "second-run"
    with pytest.raises(ValueError, match="SECOND_BATCH"):
        publish_bundle(tmp_path, DATE, snapshot=snapshot, report=report, queue=queue, capture=capture)


def test_use_rechecks_pinned_snapshot_and_never_reads_mutable_source(tmp_path):
    result = publish(tmp_path)
    (tmp_path / "signal_snapshots.jsonl").write_text("corrupt mutable source")
    assert len(read_consumed_rows(result, DATE)) == 1
    Path(result["snapshot_path"]).write_text("{}")
    assert len(read_consumed_rows(result, DATE)) == 1


def test_forged_consumer_receipt_cannot_change_original_batch(tmp_path):
    result = publish(tmp_path)
    forged = dict(result)
    row = {"date": DATE, "code": "600519.XSHG", "book": "B"}
    raw = (json.dumps(row) + "\n").encode()
    path = tmp_path / "forged.jsonl"
    path.write_bytes(raw)
    forged.update(snapshot_path=str(path), snapshot_raw_sha256=hashlib.sha256(raw).hexdigest(),
        snapshot_sha256=frozen_rows_digest([row]))
    with pytest.raises(ValueError, match="CONSUMER_PROVENANCE"):
        read_consumed_rows(forged, DATE, live_dir=tmp_path)


def test_false_empty_is_unproved_but_proven_zero_capture_is_ready(tmp_path):
    with pytest.raises(ValueError, match="EMPTY_CAPTURE_UNPROVEN"):
        publish_captured_batch(tmp_path, DATE, snapshot=b"", strategy_sha="b" * 40,
            source_readiness={"completeness": "unproven"}, timing={})
    result = publish_captured_batch(tmp_path, DATE, snapshot=b"", strategy_sha="b" * 40,
        source_readiness={"completeness": "observed_responses"}, timing={})
    assert result["snapshot_row_count"] == 0
    assert read_consumed_rows(result, DATE) == []


@pytest.mark.parametrize("field,value", [("strategy_sha", "unknown"), ("snapshot_row_count", 2),
    ("snapshot_sha256", "c" * 64), ("report_sha256", "d" * 64)])
def test_every_binding_is_required(field, value):
    snapshot, report, queue, _ = original()
    queue["freeze_binding"][field] = value
    with pytest.raises(ValueError):
        validate_components(DATE, snapshot, report, json.dumps(queue).encode())


def test_foreign_producer_rejected_before_file_effects(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-book-b-live-morning")
    with pytest.raises(ValueError, match="PRODUCER_IDENTITY"):
        publish(tmp_path)
    assert not list(tmp_path.iterdir())


def test_other_thread_cannot_claim_same_published_batch(tmp_path, monkeypatch):
    publish(tmp_path)
    monkeypatch.setenv("CODEX_THREAD_ID", "old-human-followup")
    with pytest.raises(ValueError, match="PRODUCER_THREAD_CONFLICT"):
        publish(tmp_path)


def test_queue_enrichment_reads_original_and_recovery_uses_effective_path(tmp_path):
    from xiaocao.live.intelligence_review_queue import build_review_queue
    result = publish(tmp_path)
    snapshot = Path(result["snapshot_path"])
    row = read_consumed_rows(result, DATE)[0]
    row.update(ai_hard_veto=True, stock_sentiment_source="new_report")
    (tmp_path / "signal_snapshots.jsonl").write_text(json.dumps(row) + "\n")
    (tmp_path / f"recommend_{DATE}.md").write_text("New human support report")
    queue = build_review_queue(live_dir=tmp_path, market_date=DATE, strategy_sha="a" * 40)
    assert queue["freeze_binding"]["snapshot_sha256"] == result["snapshot_sha256"]
    snapshot.unlink()
    effective = resolve_receipt(result, DATE, live_dir=tmp_path)
    assert Path(effective["snapshot_path"]).is_file()
    assert effective["snapshot_path"] != result["snapshot_path"]


def test_new_valid_veto_and_stale_veto_are_preserved_for_explicit_on(tmp_path):
    from xiaocao.live.intelligence_policy import hard_veto_state
    result = publish(tmp_path)
    rows = read_consumed_rows(result, DATE)
    new_flag = {"event_type": "regulatory_investigation", "severity": "high",
        "confidence": 0.99, "event_time": DATE + "T09:26:00+08:00",
        "source_url": "fixture:proved-report"}
    rows[0]["veto_flags"] = [new_flag]
    publish_support(tmp_path, DATE, rows)
    effective = apply_support(tmp_path, DATE, result, read_consumed_rows(result, DATE))
    assert hard_veto_state(effective[0], asof=DATE + "T09:30:00+08:00")["hard_veto"]
    assert not hard_veto_state(effective[0], asof="2026-11-30T09:30:00+08:00")["hard_veto"]
    assert "veto_flags" not in read_consumed_rows(result, DATE)[0]
    assert effective[0]["open"] == 13.71


def test_explicit_on_support_cannot_change_economics_or_batch(tmp_path):
    result = publish(tmp_path)
    rows = read_consumed_rows(result, DATE)
    publish_support(tmp_path, DATE, rows)
    path = tmp_path / f"morning_bundle_support_{DATE}.json"
    support = json.loads(path.read_bytes())
    support["rows"][0]["fields"]["open"] = 999
    body = {k: v for k, v in support.items() if k != "support_sha256"}
    encoded = (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    support["support_sha256"] = hashlib.sha256(encoded).hexdigest()
    path.write_text(json.dumps(support))
    with pytest.raises(ValueError, match="ECONOMIC_MUTATION"):
        apply_support(tmp_path, DATE, result, rows)


def test_repair_lock_wait_is_bounded_and_keeps_dependency_request(tmp_path, monkeypatch):
    import xiaocao.live.morning_bundle as bundle
    result = publish(tmp_path)
    Path(result["snapshot_path"]).unlink()
    elapsed = [0.0]
    monkeypatch.setattr(bundle.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(bundle.time, "sleep", lambda n: elapsed.__setitem__(0, elapsed[0] + n))
    monkeypatch.setattr(bundle.fcntl, "flock", lambda *_: (_ for _ in ()).throw(BlockingIOError()))
    blocked = acquire_bundle(tmp_path, DATE)
    assert blocked["status"] == "repair_required"
    assert blocked["failure_category"] == "TimeoutError"
    assert elapsed[0] == pytest.approx(10.0)
    assert Path(blocked["request_path"]).exists()


def test_orphan_checkpoint_requires_original_owner_and_recovers_exact_bytes(tmp_path, monkeypatch):
    from scripts.wait_for_morning_freeze import _freeze_status
    def crash(stage):
        if stage == "checkpoint_written":
            raise OSError("crash before commitment")
    with pytest.raises(OSError):
        publish(tmp_path, crash)
    checkpoint = next(tmp_path.glob("morning_bundles/*/*/checkpoint.json"))
    before = checkpoint.read_bytes()
    result = _freeze_status(date=DATE, live_dir=tmp_path)
    assert result["status"] == "waiting"
    assert result["reason"] == "MORNING_BUNDLE_ORPHAN_ORIGINAL_OWNER_REQUIRED"
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-book-b-live-morning")
    with pytest.raises(ValueError, match="ORIGINAL_OWNER_REQUIRED"):
        recover_request(Path(result["request_path"]), tmp_path)
    assert not (tmp_path / f"morning_bundle_commit_{DATE}.json").exists()
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-morning")
    recovered = recover_request(Path(result["request_path"]), tmp_path)
    assert recovered["status"] == "ready"
    assert checkpoint.read_bytes() == before
    assert Path(recovered["snapshot_path"]).read_bytes() == original()[0]


def test_capture_original_bytes_are_preserved_with_only_support_derivation(tmp_path):
    import base64
    raw, *_ = original()
    rows = [json.loads(raw)]
    rows[0]["veto_flags"] = []
    derived = (json.dumps(rows[0], sort_keys=True) + "\n").encode()
    publish_captured_batch(tmp_path, DATE, snapshot=derived, raw_capture=raw,
        strategy_sha="a" * 40, source_readiness={"completeness": "observed_responses"}, timing={})
    commit = json.loads((tmp_path / f"morning_bundle_commit_{DATE}.json").read_bytes())
    capture = json.loads(Path(commit["checkpoint_path"]).read_bytes())["capture"]
    assert base64.b64decode(capture["raw_capture_base64"]) == raw
    assert capture["raw_capture_sha256"] == hashlib.sha256(raw).hexdigest()
    rows[0]["open"] = 99
    with pytest.raises(ValueError, match="ECONOMIC_MUTATION"):
        publish_captured_batch(tmp_path, DATE, snapshot=(json.dumps(rows[0]) + "\n").encode(),
            raw_capture=raw, strategy_sha="a" * 40, source_readiness={}, timing={})


def test_empty_support_never_withdraws_original_valid_veto_and_reordering_is_safe(tmp_path):
    from xiaocao.live.intelligence_policy import hard_veto_state
    raw, *_ = original()
    row = json.loads(raw)
    flag = {"event_type": "regulatory_investigation", "severity": "high", "confidence": .99,
        "event_time": DATE + "T09:25:00+08:00", "source_url": "fixture:original-report"}
    row["veto_flags"] = [flag]
    second = {**row, "code": "000001.XSHE", "veto_flags": []}
    raw = (json.dumps(row) + "\n" + json.dumps(second) + "\n").encode()
    result = publish_captured_batch(tmp_path, DATE, snapshot=raw, strategy_sha="a" * 40,
        source_readiness={"completeness": "observed_responses"}, timing={})
    publish_support(tmp_path, DATE, [{**row, "veto_flags": []}, second])
    reordered = list(reversed(read_consumed_rows(result, DATE)))
    effective = apply_support(tmp_path, DATE, result, reordered)
    assert [r["code"] for r in effective] == [second["code"], row["code"]]
    assert hard_veto_state(effective[1], asof=DATE + "T09:30:00+08:00")["hard_veto"]
    assert not hard_veto_state(effective[1], asof="2026-11-30T09:30:00+08:00")["hard_veto"]


def test_unreadable_orphan_preserves_repair_request_without_commit(tmp_path, monkeypatch):
    def crash(stage):
        if stage == "checkpoint_written":
            raise OSError("before commit")
    with pytest.raises(OSError):
        publish(tmp_path, crash)
    checkpoint = next(tmp_path.glob("morning_bundles/*/*/checkpoint.json"))
    read_bytes = Path.read_bytes
    def read(path):
        if path == checkpoint:
            raise PermissionError("unreadable original")
        return read_bytes(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    result = acquire_bundle(tmp_path, DATE)
    assert result["status"] == "repair_required"
    assert Path(result["request_path"]).exists()
    assert "unreadable" in result["detail"]
    assert not (tmp_path / f"morning_bundle_commit_{DATE}.json").exists()


@pytest.mark.parametrize("fault", ["code", "qualification", "order"])
def test_execution_manifest_validates_ordered_identity_and_qualification(tmp_path, fault):
    raw, *_ = original()
    row = json.loads(raw)
    second = {**row, "code": "000001.XSHE"}
    raw = (json.dumps(row) + "\n" + json.dumps(second) + "\n").encode()
    result = publish_captured_batch(tmp_path, DATE, snapshot=raw, strategy_sha="a" * 40,
        source_readiness={}, timing={})
    queue = json.loads(Path(result["queue"]).read_bytes())
    if fault == "code":
        queue["items"][0]["code"] = "600519.XSHG"
    elif fault == "qualification":
        queue["items"][0]["mode_exec_star"] = False
    else:
        queue["items"].reverse()
    with pytest.raises(ValueError, match="MANIFEST_IDENTITY"):
        validate_components(DATE, raw, Path(result["report"]).read_bytes(), json.dumps(queue).encode())
