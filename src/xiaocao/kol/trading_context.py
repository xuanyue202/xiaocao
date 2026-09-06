"""Read published KOL evidence; produce no judgments or business side effects.

Discovery is a local, explicit PublicationLedger registry, never remote search.
All registered manifests are read or reused from verified, dated cache (within a
global read budget) so an old report's long-lived viewpoint cannot disappear
behind a latest-N or author-name filter.
Only report *bodies in the returned context* use latest-N selection. Unselected
reports remain indexed and can be selected with report_ids on a subsequent call.

Cache files are disposable, canonical-hash-bound projections. received_at is the
first verified observation by this consumer on this machine, never a publication
timestamp copied from a writer's ledger. Losing that cache loses that observation
proof; rebuilding starts a new observation, which cannot backfill a past as_of.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import queue
import tempfile
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit

from .household import LiangHuiMcpClient
from .publication import (
    KOL_RECORD_KINDS,
    PublicationLedger,
    PublicationTransport,
    canonical_bytes,
    canonical_sha256,
    manifest_entries,
    read_published_publication,
    report_id as stable_report_id,
)


ROOT = Path(__file__).resolve().parents[3]
CACHE_RELATIVE_PATH = Path("output/live/kol_policy/context")
# These are named production entry points, not a recursive events.jsonl scan.
PRODUCTION_LEDGER_PATHS = (
    "output/live/kol_daily/publications/events.jsonl",
    "output/live/kol_xiaocao_live/publications/events.jsonl",
    "output/live/kol_lianghui_initial/events.jsonl",
    "output/live/kol_lianghui_initial_v2/events.jsonl",
    "output/live/kol_lianghui_initial_v3/events.jsonl",
    "output/live/kol_lianghui_longitudinal_v1/events.jsonl",
    "output/live/kol_lianghui_xiaocao_20260727/events.jsonl",
    "output/live/kol_reader_copy_20260726/events.jsonl",
)
EVALUATION_STATES = {"current", "expired", "invalidated", "uncertain"}


class TradingContextError(ValueError):
    """Credential-free, machine-readable failure code."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: str | datetime) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise TradingContextError("invalid_timestamp") from None


def _iso(value: datetime) -> str:
    return _timestamp(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _evaluation_as_of(value: str) -> datetime:
    # Older production evaluations use a calendar day. Only this field allows it.
    if isinstance(value, str) and len(value) == 10:
        value += "T00:00:00+08:00"
    return _timestamp(value)


def _public_url(value: Any) -> str:
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username or
                url.password or url.query or url.fragment):
            raise ValueError
        return value
    except (TypeError, ValueError):
        raise TradingContextError("invalid_public_report_url") from None


def _registry(root: Path, ledger_paths: Sequence[Path | str]) -> tuple[dict, list, list]:
    paths = {root / name: False for name in PRODUCTION_LEDGER_PATHS}
    for value in ledger_paths:
        path = Path(value).expanduser()
        path = path if path.is_absolute() else root / path
        if path.name != "events.jsonl":
            raise TradingContextError("ledger_must_be_events_jsonl")
        paths[path.resolve()] = True
    reports: dict[str, dict] = {}
    issues: list[dict] = []
    ledgers: list[dict] = []
    for path, explicit in sorted(paths.items()):
        if not path.is_file():
            ledgers.append({"path": str(path), "status": "absent"})
            if explicit:
                issues.append({"code": "registered_ledger_missing", "ledger": str(path)})
            continue
        try:
            # events()/status() take a writer lock and create .lock. Use the
            # existing integrity-checked reader without mutating a writer dir.
            events = PublicationLedger(path.parent)._events_unlocked()
            prepared: dict[str, dict] = {}
            local: dict[str, dict] = {}
            for event in events:
                key = event.get("publication_key")
                if event.get("event") == "publication_prepared":
                    artifact = event["artifact"]
                    if canonical_sha256(artifact) != event["artifact_sha256"]:
                        raise TradingContextError("registry_artifact_invalid")
                    prepared[key] = artifact
                elif event.get("event") == "publication_receipt":
                    receipt = event["receipt"]
                    if receipt.get("recordState") not in {"published", "superseded"}:
                        continue
                    artifact = prepared[key]
                    request = artifact["publish_request"]
                    rid = request["report_id"]
                    if (receipt.get("recordId") != rid or
                            receipt.get("contentSha256") != request["report_content_sha256"] or
                            receipt.get("manifestSha256") != request["manifest_sha256"]):
                        raise TradingContextError("registry_receipt_mismatch")
                    report = next(r for r in artifact["records"] if r["kind"] == "report")
                    payload = report["payload"]
                    if report["record_id"] != rid or not payload["author"] or not payload["kol_id"]:
                        raise TradingContextError("registry_identity_invalid")
                    published = _timestamp(payload["source_published_at"])
                    local[rid] = {
                        "report_id": rid, "author": payload["author"],
                        "kol_id": payload["kol_id"],
                        "publication_id": report["source_binding"]["publication_id"],
                        "source_published_at": _iso(published),
                        "registry_observed_at": _iso(_timestamp(event["occurred_at"])),
                        "estimated_record_reads": len(artifact["records"]),
                        "author_aliases": sorted({payload["author"], *local.get(rid, {}).get("author_aliases", [])}),
                        "url": _public_url(receipt["detailUrl"]),
                    }
            for rid, row in local.items():
                prior = reports.get(rid)
                if prior and any(prior[k] != row[k] for k in ("kol_id", "publication_id", "url")):
                    raise TradingContextError("registry_identity_conflict")
            for rid, row in local.items():
                prior = reports.get(rid)
                aliases = sorted(set(row["author_aliases"]) | set((prior or {}).get("author_aliases", [])))
                if not prior or row["registry_observed_at"] > prior["registry_observed_at"]:
                    reports[rid] = row
                reports[rid]["author_aliases"] = aliases
            ledgers.append({"path": str(path), "status": "verified", "report_count": len(local)})
        except Exception:
            # Never expose raw ledger rows or exception text (may include secrets).
            issues.append({"code": "registered_ledger_invalid", "ledger": str(path)})
            ledgers.append({"path": str(path), "status": "invalid"})
    return reports, issues, ledgers


class ReadOnlyPublicationTransport:
    """Only get_kol_record; bounded attempts, per-call wait and whole-run budget.

    A timed-out injected transport cannot hold up the caller or process exit:
    calls run on daemon threads. The production client also has its own socket
    timeout. No background completion writes a cache or any business ledger.
    """

    def __init__(self, client: PublicationTransport | None, *, timeout_seconds: float,
                 retries: int, max_read_calls: int, total_timeout_seconds: float):
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.remaining_calls = max_read_calls
        self.deadline = time.monotonic() + total_timeout_seconds

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name != "get_kol_record" or arguments.get("kind") not in KOL_RECORD_KINDS:
            raise TradingContextError("read_only_tool_required")
        failure = "remote_read_failed"
        for _ in range(self.retries + 1):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0 or self.remaining_calls <= 0:
                raise TradingContextError("remote_read_budget_exhausted")
            self.remaining_calls -= 1
            result: queue.Queue = queue.Queue(maxsize=1)

            def invoke(result_queue=result):
                try:
                    if self.client is None:
                        self.client = LiangHuiMcpClient.from_config()
                    result_queue.put((True, self.client.call_tool(name, arguments)))
                except Exception:
                    result_queue.put((False, None))

            threading.Thread(target=invoke, daemon=True).start()
            try:
                ok, value = result.get(timeout=min(self.timeout_seconds, remaining))
                if ok:
                    if not isinstance(value, dict):
                        raise TradingContextError("remote_read_invalid")
                    return value
                failure = "remote_read_failed"
            except queue.Empty:
                failure = "remote_read_timeout"
        raise TradingContextError(failure)


class _SnapshotTransport:
    """Replay cached envelopes through the same canonical manifest verifier."""

    def __init__(self, publication: dict):
        self.publication = publication

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        if name != "get_kol_record":
            raise TradingContextError("read_only_tool_required")
        publication = self.publication
        if arguments["kind"] == "report" and "content_sha256" not in arguments:
            return {**publication["report"], "state": "published",
                    "manifest": manifest_entries(publication["records"]),
                    "manifest_sha256": publication["manifest_sha256"],
                    "published_at": publication["published_at"],
                    "updated_at": publication["updated_at"]}
        return next(record for record in publication["records"] if all(
            record[field] == arguments[field] for field in ("kind", "record_id", "content_sha256")
        ))


def _validate_publication(publication: dict, index: dict) -> None:
    report = publication["report"]
    payload = report["payload"]
    if (report["record_id"] != index["report_id"] or report["kind"] != "report" or
            payload["report_id"] != index["report_id"] or
            stable_report_id(report["source_binding"]["publication_id"]) != index["report_id"] or
            report["source_binding"]["publication_id"] != index["publication_id"] or
            not isinstance(payload["author"], str) or not payload["author"].strip() or
            payload["kol_id"] != index["kol_id"]):
        raise TradingContextError("publication_identity_mismatch")
    if not isinstance(payload.get("report_body"), str) or not payload["report_body"].strip():
        raise TradingContextError("complete_report_body_required")
    _timestamp(payload["source_published_at"])
    records = publication["records"]
    identities = [(r["kind"], r["record_id"]) for r in records]
    if len(set(identities)) != len(identities) or sum(r["kind"] == "report" for r in records) != 1:
        raise TradingContextError("manifest_identity_invalid")
    viewpoints = {r["record_id"] for r in records if r["kind"] == "viewpoint"}
    if set(payload.get("viewpoint_ids", [])) != viewpoints:
        raise TradingContextError("manifest_viewpoint_coverage_invalid")
    for record in records:
        if record["kind"] not in KOL_RECORD_KINDS:
            raise TradingContextError("manifest_kind_invalid")
        _timestamp(record["created_at"])
        data = record["payload"]
        if data.get("kol_id", index["kol_id"]) != index["kol_id"]:
            raise TradingContextError("record_author_mismatch")
        if data.get("source_published_at"):
            _timestamp(data["source_published_at"])
        if record["kind"] == "viewpoint_evaluation":
            if data.get("status") not in EVALUATION_STATES or not data.get("viewpoint_id"):
                raise TradingContextError("evaluation_invalid")
            _timestamp(data["evaluated_at"])
            _evaluation_as_of(data["as_of"])
        if record["kind"] == "viewpoint_relation":
            _timestamp(data["asserted_at"])
    for field in ("published_at", "updated_at"):
        if publication.get(field):
            _timestamp(publication[field])


def _load_cache(path: Path, index: dict) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        digest = value.pop("cache_sha256")
        if canonical_sha256(value) != digest or value["schema_version"] != 1:
            raise ValueError
        publication = read_published_publication(_SnapshotTransport(value["publication"]), index["report_id"])
        if publication != value["publication"]:
            raise ValueError
        _validate_publication(publication, index)
        first = _timestamp(value["received_at"])
        version = _timestamp(value["version_received_at"])
        verified = _timestamp(value["verified_at"])
        if not first <= version <= verified:
            raise ValueError
        return value
    except Exception:
        raise TradingContextError("cache_invalid") from None


def _write_bytes(path: Path, encoded: bytes) -> None:
    if path.exists() and path.read_bytes() == encoded:
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".context-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_json(path: Path, value: dict) -> None:
    _write_bytes(path, canonical_bytes(value) + b"\n")


def _eligible(publication: dict, cache: dict, as_of: datetime) -> bool:
    times = [cache["received_at"], cache["version_received_at"],
             publication["report"]["payload"]["source_published_at"]]
    times += [publication[k] for k in ("published_at", "updated_at") if publication.get(k)]
    times += [r["created_at"] for r in publication["records"]]
    for record in publication["records"]:
        data = record["payload"]
        times += [data[k] for k in ("source_published_at", "evaluated_at", "asserted_at") if data.get(k)]
        if record["kind"] == "viewpoint_evaluation" and _evaluation_as_of(data["as_of"]) > as_of:
            return False
    return all(_timestamp(value) <= as_of for value in times)


def _project(index: dict, cache: dict) -> dict:
    publication = cache["publication"]
    report = publication["report"]
    return {
        "author": report["payload"]["author"], "kol_id": report["payload"]["kol_id"],
        "source_published_at": report["payload"]["source_published_at"],
        "received_at": cache["received_at"], "version_received_at": cache["version_received_at"],
        "verified_at": cache["verified_at"], "report_id": index["report_id"],
        "content_sha256": report["content_sha256"], "url": index["url"],
    }


def build_trading_context(
    *, as_of: str | datetime | None = None,
    ledger_paths: Sequence[Path | str] = (), report_ids: Sequence[str] = (),
    read_report_ids: Sequence[str] | None = None,
    registered_authors: Sequence[str] = (), latest_per_author: int = 3,
    refresh: bool = False, max_cache_age_seconds: float = 300,
    history_max_cache_age_seconds: float = 86400,
    timeout_seconds: float = 10, retries: int = 1, max_read_calls: int | None = None,
    total_timeout_seconds: float = 120, client: PublicationTransport | None = None,
    repo_root: Path | str = ROOT, clock: Callable[[], datetime] = _now,
) -> dict[str, Any]:
    """Build/cache a credential-free, evidence-only multi-author context.

    ledger_paths extends the explicit production registry. report_ids selects
    extra bodies, but cannot bypass published-receipt registration. Optional
    registered_authors declares expected coverage, never filters other authors.
    read_report_ids limits network reads to exact registered sources for bounded
    batches/recovery; other fresh verified caches still join the full context.
    An empty list is cache-only. None retains the normal all-registry read scope.
    The automatic call budget uses only manifests needing a network read. Cached
    history is dated evidence with its own 24-hour TTL; selected/explicit reports
    use max_cache_age_seconds. refresh=True refreshes all reports, unless an
    exact read_report_ids scope is supplied.
    Before a current decision, use refresh=True with the exact read_report_ids.
    An explicit as_of cannot use a version first observed later; None records
    the actual completion time. Incomplete coverage returns data plus reasons.
    Fatal argument/cache-directory errors raise TradingContextError. Consumers
    must inspect coverage before making their separately authorized judgment.
    """
    start = _timestamp(clock())
    cutoff = _timestamp(as_of) if as_of is not None else None
    if cutoff is not None and cutoff > start:
        raise TradingContextError("future_as_of_forbidden")
    if (not isinstance(latest_per_author, int) or latest_per_author < 1 or
            not isinstance(retries, int) or not 0 <= retries <= 2 or
            (max_read_calls is not None and
             (not isinstance(max_read_calls, int) or not 1 <= max_read_calls <= 10000)) or
            not all(math.isfinite(v) and v > 0 for v in
                    (max_cache_age_seconds, history_max_cache_age_seconds,
                     timeout_seconds, total_timeout_seconds))):
        raise TradingContextError("invalid_read_limits")
    root = Path(repo_root).expanduser().resolve()
    directory = root / CACHE_RELATIVE_PATH
    if directory.resolve() != directory:
        raise TradingContextError("cache_directory_symlink_forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    # Serialise only this consumer's cache; never take a PublicationLedger lock.
    lock_path = directory / ".lock"
    if lock_path.is_symlink():
        raise TradingContextError("cache_directory_symlink_forbidden")
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise TradingContextError("context_cache_busy") from None
        return _build_locked(root, directory, cutoff, ledger_paths, report_ids, read_report_ids,
                             registered_authors, latest_per_author, refresh,
                             max_cache_age_seconds, history_max_cache_age_seconds, client, timeout_seconds,
                             retries, max_read_calls, total_timeout_seconds, clock)


def _build_locked(root, directory, cutoff, ledger_paths, report_ids, read_report_ids,
                  registered_authors, latest_per_author, refresh, max_cache_age_seconds, history_max_cache_age_seconds,
                  client, timeout_seconds, retries, max_read_calls, total_timeout_seconds, clock):
    registry, issues, ledgers = _registry(root, ledger_paths)
    read_scope = None if read_report_ids is None else set(read_report_ids)
    if not registry:
        issues.append({"code": "no_registered_publications"})
    requested = set(report_ids)
    for rid in sorted((requested | (read_scope or set())) - registry.keys()):
        issues.append({"code": "report_id_not_registered", "report_id": rid})
    by_author: dict[str, list] = defaultdict(list)
    for row in registry.values():
        by_author[row["kol_id"]].append(row)
    for rows in by_author.values():
        rows.sort(key=lambda r: (r["source_published_at"], r["report_id"]), reverse=True)
    freshness_ids = requested | {r["report_id"] for rows in by_author.values() for r in rows[:latest_per_author]}
    if read_scope is not None:
        freshness_ids |= read_scope
    # Round-robin recent events prevents one prolific author exhausting all reads.
    ordered = [rows[n] for n in range(max((len(v) for v in by_author.values()), default=0))
               for _, rows in sorted(by_author.items()) if n < len(rows)]
    prior_caches = {}
    needs_read = set()
    for index in ordered:
        rid = index["report_id"]
        cache_path = directory / (canonical_sha256(rid) + ".cache.json")
        if cache_path.is_symlink():
            raise TradingContextError("cache_file_symlink_forbidden")
        cached = None
        try:
            cached = _load_cache(cache_path, index)
        except TradingContextError:
            issues.append({"code": "cache_invalid_rebuild_required", "report_id": rid})
        now = _timestamp(clock())
        age = (now - _timestamp(cached["verified_at"])).total_seconds() if cached else None
        prior_caches[rid] = cached
        force_refresh = refresh and (read_scope is None or rid in read_scope)
        ttl = max_cache_age_seconds if rid in freshness_ids else history_max_cache_age_seconds
        if (cached and not force_refresh and not cached.get("refresh_required")
                and 0 <= age <= ttl):
            continue
        needs_read.add(rid)
    pending = needs_read if read_scope is None else needs_read & read_scope
    if max_read_calls is None:
        max_read_calls = min(10000, sum(registry[rid]["estimated_record_reads"] for rid in pending) * (retries + 1) + 16)
    transport = ReadOnlyPublicationTransport(client, timeout_seconds=timeout_seconds,
        retries=retries, max_read_calls=max_read_calls, total_timeout_seconds=total_timeout_seconds)
    caches: dict[str, dict] = {}
    failures: dict[str, str] = {}
    for index in ordered:
        rid = index["report_id"]
        cached = prior_caches[rid]
        cache_path = directory / (canonical_sha256(rid) + ".cache.json")
        if rid not in needs_read:
            caches[rid] = cached
            continue
        if read_scope is not None and rid not in read_scope:
            age = (_timestamp(clock()) - _timestamp(cached["verified_at"])).total_seconds() if cached else None
            if (cached and not cached.get("refresh_required") and
                    0 <= age <= history_max_cache_age_seconds):
                caches[rid] = cached
                if rid in freshness_ids and age > max_cache_age_seconds:
                    issues.append({"code": "selected_report_refresh_required", "report_id": rid})
                continue
            failures[rid] = "outside_exact_read_batch"
            continue
        try:
            publication = read_published_publication(transport, rid)
            _validate_publication(publication, index)
            observed = _iso(_timestamp(clock()))
            unchanged = cached and cached["publication"]["manifest_sha256"] == publication["manifest_sha256"]
            value = {
                "schema_version": 1,
                "received_at": cached["received_at"] if cached else observed,
                "version_received_at": cached["version_received_at"] if unchanged else observed,
                "verified_at": observed, "publication": publication,
            }
            if not _eligible(publication, value, _timestamp(observed)):
                raise TradingContextError("future_publication_forbidden")
            _write_json(cache_path, {**value, "cache_sha256": canonical_sha256(value)})
            caches[rid] = value
        except Exception as exc:
            code = str(exc) if isinstance(exc, TradingContextError) else "publication_read_or_hash_validation_failed"
            failures[rid] = code
            issues.append({"code": code, "report_id": rid,
                           "cache_status": "stale_or_refresh_rejected" if cached else "unavailable"})
            if cached:
                # A failed current read invalidates reuse even inside the prior
                # TTL. Keep observation provenance for a later successful read.
                invalidated = {**cached, "refresh_required": True}
                _write_json(cache_path, {**invalidated, "cache_sha256": canonical_sha256(invalidated)})
    as_of = cutoff or _timestamp(clock())
    for rid, cached in list(caches.items()):
        if not _eligible(cached["publication"], cached, as_of):
            failures[rid] = "publication_not_observed_as_of"
            issues.append({"code": failures[rid], "report_id": rid})
            del caches[rid]
    # Author/source dates are authoritative only after the current readback.
    for index in registry.values():
        if index["report_id"] in caches:
            index["source_published_at"] = _iso(_timestamp(caches[index["report_id"]]["publication"]["report"]["payload"]["source_published_at"]))
    selected = set(requested & registry.keys())
    author_identities = {}
    for rows in by_author.values():
        rows.sort(key=lambda r: (r["source_published_at"], r["report_id"]), reverse=True)
        selected.update(r["report_id"] for r in rows[:latest_per_author])
        latest = rows[0]
        canonical_author = (caches[latest["report_id"]]["publication"]["report"]["payload"]["author"]
                            if latest["report_id"] in caches else latest["author"])
        aliases = {alias for r in rows for alias in r["author_aliases"]}
        aliases.update(caches[r["report_id"]]["publication"]["report"]["payload"]["author"]
                       for r in rows if r["report_id"] in caches)
        author_identities[latest["kol_id"]] = {"author": canonical_author, "aliases": sorted(aliases)}
        for row in rows:
            row["canonical_author"] = canonical_author
    reports, report_index = [], []
    longitudinal: dict[str, list] = {"viewpoints": [], "evaluations": [], "relations": []}
    names = {"viewpoint": "viewpoints", "viewpoint_evaluation": "evaluations", "viewpoint_relation": "relations"}
    for rid, index in sorted(registry.items()):
        cache = caches.get(rid)
        row = {**index, "received_at": None, "content_sha256": None,
               "body_loaded": False, "longitudinal_loaded": False,
               "not_loaded_reason": failures.get(rid, "report_body_not_selected")}
        if cache:
            metadata = _project(index, cache)
            age = (as_of - _timestamp(cache["verified_at"])).total_seconds()
            metadata["verification_age_seconds"] = round(age, 3)
            row.update(metadata, longitudinal_loaded=True,
                       fresh_for_current_use=0 <= age <= max_cache_age_seconds,
                       evidence_mode="recent_verified_read" if 0 <= age <= max_cache_age_seconds else "persistent_verified_history")
            publication = cache["publication"]
            if rid in selected:
                body = publication["report"]["payload"]["report_body"]
                body_path = directory / (metadata["content_sha256"] + ".report.md")
                _write_bytes(body_path, body.encode("utf-8"))
                projected_report = {**metadata, "report_body": publication["report"]["payload"]["report_body"],
                                "canonical_author": index["canonical_author"], "report_body_path": str(body_path),
                                "report_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                                "report": copy.deepcopy(publication["report"]),
                                "manifest": manifest_entries(publication["records"]),
                                "manifest_sha256": publication["manifest_sha256"]}
                annotation_path = directory / (metadata["content_sha256"] + ".event.json")
                if annotation_path.is_file():
                    try:
                        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
                        unsigned = {k: v for k, v in annotation.items() if k != "annotation_sha256"}
                        if (annotation["annotation_sha256"] != canonical_sha256(unsigned) or
                                annotation["report_id"] != rid or annotation["report_content_sha256"] != metadata["content_sha256"]):
                            raise ValueError
                        projected_report["source_event_annotation"] = annotation
                    except Exception:
                        issues.append({"code": "event_annotation_invalid", "report_id": rid})
                reports.append(projected_report)
                row.update(body_loaded=True, not_loaded_reason=None)
            for record in publication["records"]:
                if record["kind"] in names:
                    longitudinal[names[record["kind"]]].append({
                        **metadata, "record_id": record["record_id"],
                        "content_sha256": record["content_sha256"],
                        "report_content_sha256": metadata["content_sha256"],
                        "source_published_at": record["payload"].get("source_published_at", metadata["source_published_at"]),
                        "record": copy.deepcopy(record),
                    })
        report_index.append(row)
    evaluations: dict[str, list] = defaultdict(list)
    known_viewpoints = {v["record_id"] for v in longitudinal["viewpoints"]}
    for row in longitudinal["evaluations"]:
        evaluations[row["record"]["payload"]["viewpoint_id"]].append(row)
        if row["record"]["payload"]["viewpoint_id"] not in known_viewpoints:
            issues.append({"code": "evaluation_viewpoint_not_loaded", "record_id": row["record_id"]})
    for row in longitudinal["relations"]:
        data = row["record"]["payload"]
        missing_targets = sorted({data["from_viewpoint_id"], data["to_viewpoint_id"]} - known_viewpoints)
        if missing_targets:
            issues.append({"code": "relation_viewpoints_not_loaded", "record_id": row["record_id"],
                           "viewpoint_ids": missing_targets})
    current_ids = []
    current_support_ids = []
    fresh_selected_ids = {rid for rid in selected if rid in caches and
                          0 <= (as_of - _timestamp(caches[rid]["verified_at"])).total_seconds() <= max_cache_age_seconds}
    for row in longitudinal["viewpoints"]:
        candidates = evaluations[row["record_id"]]
        if candidates:
            latest_time = max(_timestamp(e["record"]["payload"]["evaluated_at"]) for e in candidates)
            latest = [e for e in candidates if _timestamp(e["record"]["payload"]["evaluated_at"]) == latest_time]
            statuses = {e["record"]["payload"]["status"] for e in latest}
            status = next(iter(statuses)) if len(statuses) == 1 else "uncertain"
            row.update(latest_status=status, latest_evaluation_ids=sorted({e["record_id"] for e in latest}))
            if len(statuses) > 1:
                issues.append({"code": "conflicting_latest_evaluations", "record_id": row["record_id"]})
        else:
            row.update(latest_status="uncertain", latest_evaluation_ids=[])
            issues.append({"code": "viewpoint_evaluation_missing", "record_id": row["record_id"]})
        if row["latest_status"] == "current":
            current_ids.append(row["record_id"])
        latest_evaluations = [e for e in candidates if e["record_id"] in row["latest_evaluation_ids"]]
        row["fresh_selected_reference_report_ids"] = sorted({e["report_id"] for e in latest_evaluations} & fresh_selected_ids)
        row["current_support_eligible"] = row["latest_status"] == "current" and bool(row["fresh_selected_reference_report_ids"])
        row["status_evidence_mode"] = "fresh_selected_manifest" if row["fresh_selected_reference_report_ids"] else "dated_published_evaluation"
        if row["current_support_eligible"]:
            current_support_ids.append(row["record_id"])
    unloaded = [r["report_id"] for r in report_index if not r["body_loaded"]]
    if unloaded:
        issues.append({"code": "registered_report_bodies_not_loaded", "report_ids": unloaded})
    alias_names = {alias: identity["author"] for identity in author_identities.values() for alias in identity["aliases"]}
    authors = sorted({i["author"] for i in author_identities.values()} |
                     {alias_names.get(author, author) for author in registered_authors})
    covered = sorted(author_identities[kol_id]["author"] for kol_id, rows in by_author.items()
                     if rows[0]["report_id"] in caches)
    missing = sorted(set(authors) - set(covered))
    if missing:
        issues.append({"code": "registered_author_latest_report_missing", "authors": missing})
    context = {
        "schema_version": 1, "as_of": _iso(as_of), "authority": 0,
        "source": "lianghui_published_registry", "reports": reports,
        **longitudinal, "current_viewpoint_ids": sorted(set(current_ids)),
        "current_support_viewpoint_ids": sorted(set(current_support_ids)),
        "report_index": report_index, "unloaded_report_ids": unloaded,
        "coverage": {
            "registered_authors": authors, "covered_authors": covered, "missing_authors": missing,
            "author_identities": author_identities,
            "remote_discovery": "registry_only", "incomplete": True,
            "incomplete_reasons": [{"code": "remote_full_discovery_unavailable"}, *issues],
            "registered_longitudinal_complete": len(caches) == len(registry) and bool(registry)
                and not any(i["code"] in {"registered_ledger_missing", "registered_ledger_invalid"} for i in issues),
            "latest_per_author": latest_per_author, "registered_ledgers": ledgers,
            "history_policy": "all_registered_manifests; latest_n_and_explicit_report_bodies",
            "history_refresh_policy": "independent_history_ttl; exact_report_ids_for_current_readback; refresh_all_when_unscoped",
            "max_cache_age_seconds": max_cache_age_seconds,
            "history_max_cache_age_seconds": history_max_cache_age_seconds,
            "viewpoint_status_semantics": "latest_observed_published_evaluation; not_reevaluated_at_context_as_of",
            "fresh_selected_report_ids": sorted(fresh_selected_ids),
            "selected_reports_fresh": all(r["report_id"] in caches and
                0 <= (as_of - _timestamp(caches[r["report_id"]]["verified_at"])).total_seconds() <= max_cache_age_seconds
                for r in report_index if r["report_id"] in selected),
        },
    }
    context["context_sha256"] = canonical_sha256(context)
    _write_json(directory / (context["context_sha256"] + ".context.json"), context)
    return context


def cache_report_event_date(*, report_id: str, report_content_sha256: str,
                            event_date: str, origin_path: Path | str,
                            repo_root: Path | str = ROOT) -> dict:
    """Cache an explicitly reviewed event-date annotation, without report edits.

    This is local provenance for the consumer. The complete canonical envelope,
    its source_published_at and its content hash remain untouched.
    """
    try:
        date.fromisoformat(event_date)
    except (TypeError, ValueError):
        raise TradingContextError("invalid_event_date") from None
    root = Path(repo_root).resolve()
    registry, _, _ = _registry(root, ())
    if report_id not in registry:
        raise TradingContextError("report_id_not_registered")
    directory = root / CACHE_RELATIVE_PATH
    cached = _load_cache(directory / (canonical_sha256(report_id) + ".cache.json"), registry[report_id])
    if not cached or cached["publication"]["content_sha256"] != report_content_sha256:
        raise TradingContextError("annotation_report_hash_mismatch")
    origin = Path(origin_path).resolve()
    evidence_hash = hashlib.sha256(origin.read_bytes()).hexdigest()
    if evidence_hash != cached["publication"]["report"]["source_binding"]["evidence_sha256"]:
        raise TradingContextError("annotation_origin_hash_mismatch")
    annotation = {
        "schema_version": 1, "report_id": report_id,
        "report_content_sha256": report_content_sha256,
        "source_event_date": event_date, "basis": "explicit_user_review",
        "origin_path": str(origin), "origin_sha256": evidence_hash,
        "source_published_at_semantics": "canonical_upstream_publication_chain_field",
    }
    annotation["annotation_sha256"] = canonical_sha256(annotation)
    _write_json(directory / (report_content_sha256 + ".event.json"), annotation)
    return annotation


def summarize_context(context: dict, *, repo_root: Path | str = ROOT) -> dict:
    """Compact automation output; full bodies remain in the hashed artifact."""
    from collections import Counter

    coverage = context["coverage"]
    latest = {}
    for row in context["report_index"]:
        author = row.get("canonical_author", row["author"])
        previous = latest.get(author)
        if previous is None or _timestamp(row["source_published_at"]) > _timestamp(previous["source_published_at"]):
            latest[author] = {k: row[k] for k in ("report_id", "source_published_at", "body_loaded", "longitudinal_loaded")}
            latest[author]["same_source_timestamp_report_ids"] = [row["report_id"]]
        elif _timestamp(row["source_published_at"]) == _timestamp(previous["source_published_at"]):
            previous["same_source_timestamp_report_ids"].append(row["report_id"])
    return {
        "context_path": str(Path(repo_root).resolve() / CACHE_RELATIVE_PATH / (context["context_sha256"] + ".context.json")),
        "context_sha256": context["context_sha256"], "as_of": context["as_of"],
        "coverage": {k: v for k, v in coverage.items() if k not in {"incomplete_reasons", "registered_ledgers", "fresh_selected_report_ids"}},
        "incomplete_reason_counts": dict(Counter(r["code"] for r in coverage["incomplete_reasons"])),
        "counts": {
            **{k: len(context[k]) for k in ("reports", "report_index", "viewpoints", "evaluations", "relations", "current_viewpoint_ids", "current_support_viewpoint_ids", "unloaded_report_ids")},
            "verified_report_manifests": sum(bool(r["longitudinal_loaded"]) for r in context["report_index"]),
            "fresh_selected_reports": len(coverage["fresh_selected_report_ids"]),
        },
        "latest_by_author": latest,
    }
