"""One original morning batch, atomic publication and exact-byte local repair.

The immutable producer checkpoint owns expectations. Consumers never derive a
new expected hash from a broken display file, select candidates, or trade here.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from xiaocao.utils.atomic_files import atomic_write
from .trading_runner import frozen_rows_digest


SCHEMA = "morning-bundle.v1"
# Deployment is after Sep30's terminal morning. Historical evidence and
# exact-plan reconciliation through Sep30 retain their original format.
BUNDLE_REQUIRED_FROM = "2026-10-01"


def bundle_required(date: str) -> bool:
    _valid_date(date)
    return date >= BUNDLE_REQUIRED_FROM


def has_bundle_evidence(live_dir: Path, date: str) -> bool:
    """An orphan original checkpoint also forbids legacy fallback."""
    return ((live_dir / f"morning_bundle_commit_{date}.json").exists()
        or (live_dir / f"morning_bundle_ready_{date}.json").exists()
        or any((live_dir / "morning_bundles" / date).glob("*/checkpoint.json")))


def _valid_date(date: str) -> None:
    if datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d") != date:
        raise ValueError("MORNING_BUNDLE_DATE_INVALID")


def _bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_rows(raw: bytes, date: str) -> list[dict]:
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) or str(row.get("date") or row.get("trade_date") or "")[:10] != date for row in rows):
        raise ValueError("MORNING_BUNDLE_SNAPSHOT_DATE_INVALID")
    return rows


def validate_components(date: str, snapshot: bytes, report: bytes, queue: bytes) -> dict:
    """Read each component once and bind ordered canonical and raw hashes."""
    body = json.loads(queue)
    if not isinstance(body, dict):
        raise ValueError("queue_invalid")
    if body.get("market_date") != date:
        raise ValueError("queue_market_date_mismatch")
    status = body.get("status")
    counts = body.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("queue_invalid")
    count = counts.get("selected_items")
    if type(count) is not int or count < 0 or status not in {"ready", "empty"}:
        raise ValueError("queue_not_frozen")
    if (status == "ready") != (count > 0):
        raise ValueError("queue_status_count_mismatch")
    if body.get("schema_version") == 2 and (not isinstance(body.get("items"), list) or len(body["items"]) != count):
        raise ValueError("queue_status_count_mismatch")
    binding = body.get("freeze_binding")
    if not isinstance(binding, dict):
        raise ValueError("queue_freeze_binding_missing")
    if not report or binding.get("report_sha256") != _sha(report):
        raise ValueError("queue_report_binding_mismatch")
    rows = snapshot_rows(snapshot, date)
    if body.get("purpose") == "execution_identity_manifest_support_review_separate":
        expected = [{k: row.get(k) for k in ("code", "book", "mode", "mode_exec_star", "mode_trade_eligible")} for row in rows]
        if body.get("schema_version") != 2 or body.get("items") != expected:
            raise ValueError("MORNING_BUNDLE_MANIFEST_IDENTITY_MISMATCH")
    canonical = frozen_rows_digest(rows)
    if (type(binding.get("snapshot_row_count")) is not int
            or binding["snapshot_row_count"] != len(rows)
            or binding.get("snapshot_sha256") != canonical
            or not str(binding.get("strategy_run_id") or "").strip()
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(binding.get("strategy_sha") or "")) is None):
        raise ValueError("queue_snapshot_binding_mismatch")
    return {"market_date": date, "strategy_run_id": binding["strategy_run_id"],
        "strategy_sha": binding["strategy_sha"], "snapshot_sha256": canonical,
        "snapshot_raw_sha256": _sha(snapshot), "snapshot_row_count": len(rows),
        "report_sha256": _sha(report), "queue_sha256": _sha(queue),
        "queue_status": status, "selected_items": count}


def publish_bundle(live_dir: Path, date: str, *, snapshot: bytes, report: bytes,
                   queue: dict, capture: dict, on_stage=None) -> dict:
    """Commit complete original bytes before publishing any consumer readiness."""
    live_dir = Path(live_dir)
    _valid_date(date)
    if (os.environ.get("CODEX_AUTOMATION_ID") != "xiaocao-daily-morning"
            or not str(os.environ.get("CODEX_THREAD_ID") or "").strip()):
        raise ValueError("MORNING_BUNDLE_PRODUCER_IDENTITY_REQUIRED")
    queue_raw = _bytes(queue)
    binding = validate_components(date, snapshot, report, queue_raw)
    if capture.get("status") != "captured" or capture.get("market_date") != date:
        raise ValueError("MORNING_BUNDLE_CAPTURE_UNPROVEN")
    if capture.get("snapshot_sha256") != binding["snapshot_sha256"]:
        raise ValueError("MORNING_BUNDLE_CAPTURE_MISMATCH")
    run_key = _sha(binding["strategy_run_id"].encode())
    root = live_dir / "morning_bundles" / date / run_key
    checkpoint = {"schema_version": SCHEMA, "binding": binding, "capture": capture,
        "producer": {"automation_id": os.environ.get("CODEX_AUTOMATION_ID"),
            "thread_id": os.environ.get("CODEX_THREAD_ID"),
            "identity_proof": "runtime_identity_scheduler_token_unavailable"},
        "artifacts": {"snapshot": base64.b64encode(snapshot).decode(),
            "report": base64.b64encode(report).decode(), "queue": base64.b64encode(queue_raw).decode()}}
    raw = _bytes(checkpoint)
    # Single original commitment: a second batch cannot replace its identity.
    with _lock(live_dir / "morning_bundles" / date / "publish.lock"):
        commit_path = live_dir / f"morning_bundle_commit_{date}.json"
        if commit_path.exists():
            committed, _ = _checkpoint(live_dir, date)
            if (committed["producer"]["thread_id"] != os.environ.get("CODEX_THREAD_ID")):
                raise ValueError("MORNING_BUNDLE_ORIGINAL_PRODUCER_THREAD_CONFLICT")
            if committed["binding"] != binding:
                raise ValueError("MORNING_BUNDLE_SECOND_BATCH_CONFLICT")
            return acquire_bundle(live_dir, date, repair=True)
        orphans = list((live_dir / "morning_bundles" / date).glob("*/checkpoint.json"))
        if orphans and (len(orphans) != 1 or orphans[0] != root / "checkpoint.json"
                or orphans[0].read_bytes() != raw):
            raise ValueError("MORNING_BUNDLE_ORPHAN_ORIGINAL_CONFLICT")
        atomic_write(root / "checkpoint.json", raw, immutable=True)
        if on_stage:
            on_stage("checkpoint_written")
        atomic_write(commit_path, _bytes({"schema_version": SCHEMA,
            "market_date": date, "checkpoint_path": str((root / "checkpoint.json").resolve()),
            "checkpoint_sha256": _sha(raw)}), immutable=True)
        if on_stage:
            on_stage("checkpoint_committed")
        return _materialize(live_dir, date, checkpoint, _sha(raw), root / "original", on_stage=on_stage)


class _lock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+")
        deadline = time.monotonic() + 10.0
        while True:
            try:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self.stream.close()
                    raise TimeoutError("MORNING_BUNDLE_REPAIR_LOCK_TIMEOUT")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def __exit__(self, *_):
        self.stream.close()


def _checkpoint(live_dir: Path, date: str) -> tuple[dict, str]:
    commit = json.loads((live_dir / f"morning_bundle_commit_{date}.json").read_bytes())
    path = Path(commit["checkpoint_path"])
    expected_root = (live_dir / "morning_bundles" / date).resolve()
    if commit.get("market_date") != date or not path.resolve().is_relative_to(expected_root) or path.is_symlink():
        raise ValueError("MORNING_BUNDLE_COMMIT_BINDING_INVALID")
    raw = path.read_bytes()
    if commit["checkpoint_sha256"] != _sha(raw):
        raise ValueError("MORNING_BUNDLE_ORIGINAL_CHECKPOINT_UNPROVEN")
    return _decode_checkpoint(raw, date), _sha(raw)


def _decode_checkpoint(raw: bytes, date: str) -> dict:
    checkpoint = json.loads(raw)
    artifacts = {k: base64.b64decode(v, validate=True) for k, v in checkpoint["artifacts"].items()}
    binding = validate_components(date, artifacts["snapshot"], artifacts["report"], artifacts["queue"])
    capture = checkpoint["capture"]
    if (checkpoint.get("schema_version") != SCHEMA or binding != checkpoint["binding"]
            or capture.get("status") != "captured" or capture.get("market_date") != date
            or capture.get("snapshot_sha256") != binding["snapshot_sha256"]):
        raise ValueError("MORNING_BUNDLE_CHECKPOINT_BINDING_INVALID")
    if "raw_capture_base64" in capture:
        original = base64.b64decode(capture["raw_capture_base64"], validate=True)
        if (capture.get("raw_capture_sha256") != _sha(original)
                or _economic_rows(snapshot_rows(original, date)) != _economic_rows(snapshot_rows(artifacts["snapshot"], date))):
            raise ValueError("MORNING_BUNDLE_RAW_CAPTURE_BINDING_INVALID")
    producer = checkpoint.get("producer")
    if (not isinstance(producer, dict) or producer.get("automation_id") != "xiaocao-daily-morning"
            or not str(producer.get("thread_id") or "").strip()):
        raise ValueError("MORNING_BUNDLE_CHECKPOINT_PRODUCER_INVALID")
    return checkpoint


def _materialize(live_dir, date, checkpoint, checkpoint_sha, directory, *, on_stage=None):
    paths = {}
    for kind, suffix in (("snapshot", ".jsonl"), ("report", ".md"), ("queue", ".json")):
        path = directory / (kind + suffix)
        atomic_write(path, base64.b64decode(checkpoint["artifacts"][kind], validate=True), immutable=True)
        paths[kind] = str(path.resolve())
        if on_stage:
            on_stage(kind + "_committed")
    ready = {"schema_version": SCHEMA, **checkpoint["binding"], "paths": paths,
        "checkpoint_sha256": checkpoint_sha, "published_at": _stamp(),
        "bundle_live_dir": str(Path(live_dir).resolve())}
    atomic_write(live_dir / f"morning_bundle_ready_{date}.json", _bytes(ready))
    if on_stage:
        on_stage("ready_committed")
    return _ready_result(ready)


def publish_captured_batch(live_dir: Path, date: str, *, snapshot: bytes,
                           strategy_sha: str, source_readiness: dict, timing: dict,
                           raw_capture: bytes | None = None) -> dict:
    """Publish execution evidence before optional report/news enrichment.

    The queue in this package binds execution identity. The separate derived
    intelligence queue still carries reviews and cannot change this batch.
    """
    if (os.environ.get("CODEX_AUTOMATION_ID") != "xiaocao-daily-morning"
            or not str(os.environ.get("CODEX_THREAD_ID") or "").strip()):
        raise ValueError("MORNING_BUNDLE_PRODUCER_IDENTITY_REQUIRED")
    rows = snapshot_rows(snapshot, date)
    raw_capture = snapshot if raw_capture is None else raw_capture
    if _economic_rows(snapshot_rows(raw_capture, date)) != _economic_rows(rows):
        raise ValueError("MORNING_BUNDLE_CAPTURE_ECONOMIC_MUTATION")
    canonical = frozen_rows_digest(rows)
    if not rows and source_readiness.get("completeness") != "observed_responses":
        raise ValueError("MORNING_BUNDLE_EMPTY_CAPTURE_UNPROVEN")
    report = (f"# {date} original execution batch\n"
        f"capture_count={len(rows)} eligible_count={sum(bool(r.get('mode_exec_star')) for r in rows)}\n"
        "supporting_health=pending_derived_intelligence; current veto and KOL review remain required\n").encode()
    items = [{k: r.get(k) for k in ("code", "book", "mode", "mode_exec_star", "mode_trade_eligible")} for r in rows]
    queue = {"schema_version": 2, "market_date": date, "status": "ready" if rows else "empty",
        "counts": {"selected_items": len(rows)}, "items": items,
        "purpose": "execution_identity_manifest_support_review_separate",
        "freeze_binding": {"strategy_run_id": f"morning-freeze:{date}:{canonical[:16]}",
            "strategy_sha": strategy_sha, "snapshot_sha256": canonical,
            "snapshot_row_count": len(rows), "report_sha256": _sha(report)}}
    return publish_bundle(live_dir, date, snapshot=snapshot, report=report, queue=queue,
        capture={"status": "captured", "market_date": date, "snapshot_sha256": canonical,
            "raw_capture_base64": base64.b64encode(raw_capture).decode(),
            "raw_capture_sha256": _sha(raw_capture), "execution_derivation": "cached_intelligence_fields_only",
            "ordered_candidates": [{k: r.get(k) for k in ("code", "mode", "book", "mode_exec_star", "mode_trade_eligible")} for r in rows],
            "source_readiness": source_readiness, "captured_at": _stamp(), "timing": timing})


def _ready_result(ready):
    return {"status": "ready", "reason": "dated_frozen_evidence_ready",
        **{k: v for k, v in ready.items() if k not in {"paths", "schema_version"}},
        "snapshot_path": ready["paths"]["snapshot"], "report": ready["paths"]["report"],
        "queue": ready["paths"]["queue"]}


def _verify_ready(live_dir, date, checkpoint, checkpoint_sha):
    ready = json.loads((live_dir / f"morning_bundle_ready_{date}.json").read_bytes())
    if (ready.get("schema_version") != SCHEMA or ready.get("checkpoint_sha256") != checkpoint_sha
            or any(ready.get(k) != v for k, v in checkpoint["binding"].items())):
        raise ValueError("MORNING_BUNDLE_READY_BINDING_INVALID")
    raws = {}
    root = (live_dir / "morning_bundles" / date).resolve()
    if set(ready["paths"]) != {"snapshot", "report", "queue"}:
        raise ValueError("MORNING_BUNDLE_PATH_UNPROVEN")
    for kind, name in ready["paths"].items():
        path = Path(name)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("MORNING_BUNDLE_PATH_UNPROVEN")
        raws[kind] = path.read_bytes()
        if raws[kind] != base64.b64decode(checkpoint["artifacts"][kind], validate=True):
            raise ValueError("MORNING_BUNDLE_ARTIFACT_CONFLICT")
    validate_components(date, raws["snapshot"], raws["report"], raws["queue"])
    return _ready_result(ready)


def acquire_bundle(live_dir: Path, date: str, *, repair: bool = True) -> dict:
    """Revalidate the original commitment; recover files under one repair claim."""
    live_dir = Path(live_dir)
    _valid_date(date)
    try:
        checkpoint, checkpoint_sha = _checkpoint(live_dir, date)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        request = {"status": "repair_required", "reason": "MORNING_BUNDLE_ORIGINAL_UNPROVEN",
            "detail": str(exc), "market_date": date}
        orphans = list((live_dir / "morning_bundles" / date).glob("*/checkpoint.json"))
        if not (live_dir / f"morning_bundle_commit_{date}.json").exists() and len(orphans) == 1:
            try:
                orphan_raw = orphans[0].read_bytes()
            except OSError as orphan_error:
                request["detail"] = "orphan_checkpoint_unreadable:" + type(orphan_error).__name__
            else:
                request.update(reason="MORNING_BUNDLE_ORPHAN_ORIGINAL_OWNER_REQUIRED",
                    orphan_checkpoint_path=str(orphans[0].resolve()),
                    orphan_checkpoint_sha256=_sha(orphan_raw))
        fingerprint = _sha(_bytes(request))
        path = live_dir / "morning_bundles" / date / "repairs" / fingerprint / "request.json"
        atomic_write(path, _bytes(request), immutable=True)
        return {**request, "request_path": str(path)}
    try:
        return _verify_ready(live_dir, date, checkpoint, checkpoint_sha)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fingerprint = _sha(_bytes({"checkpoint_sha256": checkpoint_sha, "failure": type(exc).__name__ + ":" + str(exc)}))
    repair_root = live_dir / "morning_bundles" / date / "repairs" / fingerprint
    request_path = repair_root / "request.json"
    request = {"schema_version": SCHEMA, "market_date": date, "checkpoint_sha256": checkpoint_sha,
        "failure_fingerprint": fingerprint, "status": "repair_required"}
    atomic_write(request_path, _bytes(request), immutable=True)
    if not repair:
        return {**request, "request_path": str(request_path)}
    try:
        return _repair_checkpoint(live_dir, date, checkpoint, checkpoint_sha, repair_root, request)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {**request, "request_path": str(request_path),
            "reason": "MORNING_BUNDLE_LOCAL_REPAIR_FAILED", "failure_category": type(exc).__name__}


def _repair_checkpoint(live_dir, date, checkpoint, checkpoint_sha, repair_root, request):
    with _lock(live_dir / "morning_bundles" / date / "repair.lock"):
        try:
            return _verify_ready(live_dir, date, checkpoint, checkpoint_sha)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        claim = repair_root / "claim.json"
        if not claim.exists():
            atomic_write(claim, _bytes({**request, "claimed_at": _stamp(),
                "owner_thread_id": os.environ.get("CODEX_THREAD_ID"), "pid": os.getpid()}), immutable=True)
        # Preserve any conflicting published content before creating a new copy.
        ready_path = live_dir / f"morning_bundle_ready_{date}.json"
        if ready_path.exists():
            raw = ready_path.read_bytes()
            atomic_write(repair_root / ("conflict-ready-" + _sha(raw) + ".json"), raw, immutable=True)
            try:
                prior = json.loads(raw)
                root = (live_dir / "morning_bundles" / date).resolve()
                for kind, name in (prior.get("paths") or {}).items():
                    path = Path(name)
                    if (kind in {"snapshot", "report", "queue"} and not path.is_symlink()
                            and path.resolve().is_relative_to(root) and path.is_file()):
                        content = path.read_bytes()
                        atomic_write(repair_root / f"conflict-{kind}-{_sha(content)}", content, immutable=True)
            except (OSError, ValueError, TypeError):
                pass
        result = _materialize(live_dir, date, checkpoint, checkpoint_sha, repair_root / "restored")
        receipt = {**request, "status": "recovered", "completed_at": _stamp(),
            "claim_path": str(claim), "result": result, "actions": "restore_exact_original_bytes"}
        receipt_path = repair_root / "receipt.json"
        if not receipt_path.exists():
            atomic_write(receipt_path, _bytes(receipt), immutable=True)
        return {**result, "repair_receipt_path": str(receipt_path)}


def recover_request(request_path: Path, live_dir: Path) -> dict:
    """Resume the exact request without selecting, fetching or trading."""
    path = Path(request_path)
    request = json.loads(path.read_bytes())
    date = str(request["market_date"])
    _valid_date(date)
    root = (Path(live_dir) / "morning_bundles" / date / "repairs").resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root) or path.name != "request.json":
        raise ValueError("MORNING_BUNDLE_RECOVERY_REQUEST_UNPROVEN")
    if request.get("reason") == "MORNING_BUNDLE_ORPHAN_ORIGINAL_OWNER_REQUIRED":
        # Consumers cannot mint a commitment. Only the original runtime owner
        # can complete this interrupted publication from its exact checkpoint.
        checkpoint_path = Path(request["orphan_checkpoint_path"])
        original_root = (Path(live_dir) / "morning_bundles" / date).resolve()
        if checkpoint_path.is_symlink() or not checkpoint_path.resolve().is_relative_to(original_root):
            raise ValueError("MORNING_BUNDLE_ORPHAN_PATH_UNPROVEN")
        raw = checkpoint_path.read_bytes()
        if _sha(raw) != request["orphan_checkpoint_sha256"]:
            raise ValueError("MORNING_BUNDLE_ORPHAN_CHANGED")
        checkpoint = _decode_checkpoint(raw, date)
        if (os.environ.get("CODEX_AUTOMATION_ID") != checkpoint["producer"]["automation_id"]
                or os.environ.get("CODEX_THREAD_ID") != checkpoint["producer"]["thread_id"]):
            raise ValueError("MORNING_BUNDLE_ORPHAN_ORIGINAL_OWNER_REQUIRED")
        with _lock(original_root / "publish.lock"):
            commit_path = Path(live_dir) / f"morning_bundle_commit_{date}.json"
            atomic_write(commit_path, _bytes({"schema_version": SCHEMA, "market_date": date,
                "checkpoint_path": str(checkpoint_path.resolve()), "checkpoint_sha256": _sha(raw)}), immutable=True)
    checkpoint, sha = _checkpoint(Path(live_dir), date)
    if request.get("checkpoint_sha256") not in {None, sha}:
        raise ValueError("MORNING_BUNDLE_RECOVERY_CHECKPOINT_MISMATCH")
    return acquire_bundle(Path(live_dir), date)


def publish_support(live_dir: Path, date: str, rows: list[dict]) -> None:
    """Bind derived intelligence to original identities; never replace economics."""
    checkpoint, sha = _checkpoint(live_dir, date)
    if (os.environ.get("CODEX_AUTOMATION_ID") != "xiaocao-daily-morning"
            or os.environ.get("CODEX_THREAD_ID") != checkpoint["producer"]["thread_id"]):
        raise ValueError("MORNING_BUNDLE_ORIGINAL_PRODUCER_THREAD_CONFLICT")
    original = snapshot_rows(base64.b64decode(checkpoint["artifacts"]["snapshot"], validate=True), date)
    by_identity = {(r.get("code"), r.get("book", "B"), r.get("mode")): r for r in rows
        if r.get("date") == date and r.get("is_live") is True}
    derived = []
    for row in original:
        current = by_identity.get((row.get("code"), row.get("book", "B"), row.get("mode")))
        if current is None:
            raise ValueError("MORNING_BUNDLE_SUPPORT_COVERAGE_UNPROVEN")
        derived.append({"code": row["code"], "book": row.get("book", "B"), "mode": row.get("mode"),
            "fields": {k: v for k, v in current.items() if _support_field(k)}})
    body = {"schema_version": "morning-bundle-support.v1", "market_date": date,
        "checkpoint_sha256": sha, "snapshot_sha256": checkpoint["binding"]["snapshot_sha256"],
        "rows": derived, "status": "completed"}
    atomic_write(live_dir / f"morning_bundle_support_{date}.json",
        _bytes({**body, "support_sha256": _sha(_bytes(body))}), immutable=True)


def _support_field(key: str) -> bool:
    return key.startswith(("stock_sentiment_", "ai_intelligence_", "intelligence_", "agent_")) or key in {"veto_flags", "score_source", "ai_hard_veto", "ai_hard_veto_event_types", "ai_hard_veto_reason"}


def _economic_rows(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if not _support_field(k)} for row in rows]


def apply_support(live_dir: Path, date: str, receipt: dict, rows: list[dict]) -> list[dict]:
    support = json.loads((live_dir / f"morning_bundle_support_{date}.json").read_bytes())
    body = {k: v for k, v in support.items() if k != "support_sha256"}
    if (support.get("support_sha256") != _sha(_bytes(body)) or support.get("status") != "completed"
            or support.get("market_date") != date or support.get("snapshot_sha256") != receipt["snapshot_sha256"]
            or support.get("checkpoint_sha256") != receipt["checkpoint_sha256"]):
        raise ValueError("MORNING_BUNDLE_SUPPORT_BINDING_INVALID")
    identities = [(r.get("code"), r.get("book", "B"), r.get("mode")) for r in rows]
    derived = {(r.get("code"), r.get("book"), r.get("mode")): r for r in support["rows"]}
    if (len(derived) != len(support["rows"]) or len(set(identities)) != len(identities)
            or set(derived) != set(identities)):
        raise ValueError("MORNING_BUNDLE_SUPPORT_IDENTITY_INVALID")
    if any(not _support_field(k) for r in support["rows"] for k in r["fields"]):
        raise ValueError("MORNING_BUNDLE_SUPPORT_ECONOMIC_MUTATION")
    merged = []
    for row, identity in zip(rows, identities):
        current = {**row, **derived[identity]["fields"]}
        # A newer support record is not a withdrawal of an earlier proven
        # event. Union flags; the existing typed validity policy handles expiry.
        flags = {}
        for source in (row, derived[identity]["fields"]):
            raw_flags = source.get("veto_flags", source.get("intelligence_veto_flags", []))
            if isinstance(raw_flags, str):
                raw_flags = json.loads(raw_flags)
            if not isinstance(raw_flags, list) or any(not isinstance(flag, dict) for flag in raw_flags):
                raise ValueError("MORNING_BUNDLE_SUPPORT_VETO_INVALID")
            for flag in raw_flags:
                flags[_sha(_bytes(flag))] = flag
        current["veto_flags"] = list(flags.values())
        merged.append(current)
    return merged


def resolve_receipt(receipt: dict, date: str, *, live_dir: Path) -> dict:
    """Adopt an exact recovery copy without changing original batch identity."""
    if not has_bundle_evidence(live_dir, date):
        if bundle_required(date):
            raise ValueError("MORNING_BUNDLE_ORIGINAL_REQUIRED")
        return receipt
    result = acquire_bundle(live_dir, date)
    keys = ("market_date", "strategy_run_id", "strategy_sha", "snapshot_sha256",
        "snapshot_raw_sha256", "snapshot_row_count", "report_sha256", "queue_sha256",
        "queue_status", "selected_items", "checkpoint_sha256")
    if result.get("status") != "ready" or any(receipt.get(k) != result.get(k) for k in keys):
        raise ValueError("MORNING_BUNDLE_CONSUMER_PROVENANCE_INVALID")
    return result


def read_consumed_rows(receipt: dict, date: str, *, live_dir: Path | None = None) -> list[dict]:
    """Pin one read to the consumer receipt, never reopen another source."""
    root = Path(live_dir or receipt["bundle_live_dir"])
    receipt = resolve_receipt(receipt, date, live_dir=root)
    commit = root / f"morning_bundle_commit_{date}.json"
    if commit.exists():
        checkpoint, sha = _checkpoint(root, date)
        if (receipt.get("checkpoint_sha256") != sha
                or any(receipt.get(k) != v for k, v in checkpoint["binding"].items())):
            raise ValueError("MORNING_BUNDLE_CONSUMER_PROVENANCE_INVALID")
        original = base64.b64decode(checkpoint["artifacts"]["snapshot"], validate=True)
        try:
            raw = Path(receipt["snapshot_path"]).read_bytes()
            if raw != original:
                raise ValueError("MORNING_BUNDLE_ARTIFACT_CONFLICT")
        except (OSError, ValueError):
            recovered = acquire_bundle(root, date)
            if recovered.get("status") != "ready" or recovered.get("checkpoint_sha256") != sha:
                raise ValueError("MORNING_BUNDLE_ORIGINAL_UNPROVEN")
            raw = Path(recovered["snapshot_path"]).read_bytes()
            if raw != original:
                raise ValueError("MORNING_BUNDLE_ARTIFACT_CONFLICT")
    else:
        path = root / f"book_b_live_freeze_{date}.jsonl"
        if Path(receipt["snapshot_path"]).resolve() != path.resolve():
            raise ValueError("MORNING_BUNDLE_CONSUMER_PROVENANCE_INVALID")
        raw = path.read_bytes()
        binding = validate_components(date, raw,
            (root / f"recommend_{date}.md").read_bytes(),
            (root / f"intelligence_review_queue_{date}.json").read_bytes())
        if any(receipt.get(k) != v for k, v in binding.items()):
            raise ValueError("MORNING_BUNDLE_CONSUMER_PROVENANCE_INVALID")
    rows = snapshot_rows(raw, date)
    if (receipt.get("market_date") != date or receipt.get("snapshot_raw_sha256") != _sha(raw)
            or receipt.get("snapshot_sha256") != frozen_rows_digest(rows)
            or receipt.get("snapshot_row_count") != len(rows)
            or not receipt.get("strategy_run_id")
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(receipt.get("strategy_sha") or "")) is None):
        raise ValueError("MORNING_BUNDLE_CONSUMPTION_BINDING_INVALID")
    return rows
