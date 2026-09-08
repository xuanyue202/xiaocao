"""Consume user-approved, independently reviewed KOL judgments; never trade.

``root`` is a dedicated store directory, not the repository root. Each immutable
<decision_id>.json contains the decision, separate review and publication receipt.
No index is needed: selection uses (as_of, specific-runtime-first, decision_id).
Older arrivals are retained for audit but cannot replace newer judgments. The
latest applicable judgment expiring never resurrects an older judgment.

Agents own full-source reading, author/time-horizon weighting, applicability and
independent semantic review. This module does not call a model, classify prose,
verify remote report bytes, require research PASS, or inspect accounts. The CLI
must read back authoritative reports and verify source hashes before publishing.
Review assertions and hashes are auditable data, NOT unforgeable authorization.
Eligibility, capital, lots, liquidity and broker safety remain separate gates.

Review uses reviewer_agent_id and reviewed_at (UTC ISO). A contradicting check is
material by default; live/both requires resolved=true and resolution_reason for
material contradictions. Every current check must be at most 15 minutes old both
at decision.as_of and at consumption; otherwise load returns needs_refresh with
neutral adjustments and the original decision_id for Agent reassessment. Source
publication and receipt times are separate required facts, never inferred from
one another (they may genuinely coincide). Optional annotations are hash-bound;
source_refs accepts only its five documented fields to avoid apparent validation
of unsupported source-verification claims.

Call load_decision with a fresh clock at each action boundary. Its result is a
point-in-time snapshot; the pure adjustment helpers neither refresh nor extend
it. They only narrow an already eligible candidate or request an exit for the
exact supplied code. An exit request is neither permission nor an execution.
Natural-language invalidation_conditions require Agent reassessment; validating
their structure does not establish whether those conditions have occurred.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = "kol-trading-decision.v1"
MODE_OVERRIDE_SCHEMA_VERSION = "kol-trading-decision.v2"
_SUPPORTED_SCHEMA_VERSIONS = {SCHEMA_VERSION, MODE_OVERRIDE_SCHEMA_VERSION}
_RECORD_VERSION = "kol-trading-decision-record.v1"
_SOURCE_FIELDS = {
    "report_id", "content_sha256", "author_id", "source_published_at", "received_at",
}
_REVIEW_FLAGS = (
    "coverage_complete", "source_fidelity", "applicability_checked", "counterevidence_checked",
)
_UTC_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{64}")
_CN_CODE = re.compile(r"[0-9]{6}\.(?:XSHG|XSHE|BJSE)")
_US_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*")


class KolPolicyError(ValueError):
    """Invalid judgment, immutable-ID conflict, or failed durable publication."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise KolPolicyError(reason)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _json_value(value: object) -> None:
    if isinstance(value, dict):
        _require(all(isinstance(key, str) for key in value), "NON_STRING_JSON_KEY")
        for item in value.values():
            _json_value(item)
    elif isinstance(value, list):
        for item in value:
            _json_value(item)
    elif isinstance(value, float):
        _require(math.isfinite(value), "NON_FINITE_NUMBER")
    else:
        _require(value is None or type(value) in (str, int, bool), "NON_JSON_VALUE")


def _canonical(value: object) -> bytes:
    _json_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def decision_sha256(decision: dict) -> str:
    """SHA-256 of the ENTIRE UTF-8, sorted-key, compact, finite JSON decision."""
    return hashlib.sha256(_canonical(decision)).hexdigest()


def _time(value: object) -> datetime:
    _require(isinstance(value, str) and _UTC_ISO.fullmatch(value) is not None, "UTC_ISO_REQUIRED")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KolPolicyError("INVALID_TIMESTAMP") from exc


def _clock(now: datetime) -> datetime:
    _require(isinstance(now, datetime) and now.utcoffset() is not None, "AWARE_CLOCK_REQUIRED")
    return now.astimezone(timezone.utc)


def _scope(book: str, runtime: str, *, stored: bool = False) -> None:
    _require(book in ("B", "T", "KOL-US"), "INVALID_BOOK")
    _require(runtime in (("live", "paper", "both") if stored else ("live", "paper")),
             "INVALID_RUNTIME")
    _require(book == "B" or runtime == "paper", "NON_B_BOOK_IS_PAPER_ONLY")


def _valid_code(code: object, book: str) -> bool:
    return isinstance(code, str) and bool((_US_CODE if book == "KOL-US" else _CN_CODE).fullmatch(code))


def _validate_pair(decision: dict, review: dict) -> tuple[datetime, datetime, datetime]:
    _require(isinstance(decision, dict) and isinstance(review, dict), "DECISION_AND_REVIEW_REQUIRED")
    _canonical(decision)
    _canonical(review)
    schema_version = decision.get("schema_version")
    _require(schema_version in _SUPPORTED_SCHEMA_VERSIONS, "INVALID_SCHEMA")
    identifier = decision.get("decision_id")
    _require(isinstance(identifier, str) and _ID.fullmatch(identifier) is not None, "INVALID_DECISION_ID")
    _require(_text(decision.get("agent_id")), "AUTHOR_AGENT_REQUIRED")
    _scope(decision.get("book"), decision.get("runtime"), stored=True)
    as_of, until = _time(decision.get("as_of")), _time(decision.get("valid_until"))
    _require(timedelta(0) < until - as_of <= timedelta(hours=24), "INVALID_LIFETIME")
    scale = decision.get("buy_scale")
    _require(type(scale) in (int, float) and 0 <= scale <= 1, "INVALID_BUY_SCALE")
    for name in ("skip_codes", "exit_codes"):
        codes = decision.get(name)
        _require(isinstance(codes, list), "EXACT_CODE_LIST_REQUIRED")
        _require(all(_valid_code(code, decision["book"]) for code in codes), "INVALID_EXACT_CODE")
        _require(len(codes) == len(set(codes)), "DUPLICATE_CODE")
    _require(_text(decision.get("rationale")), "RATIONALE_REQUIRED")
    conditions = decision.get("invalidation_conditions")
    _require(isinstance(conditions, list) and bool(conditions) and all(map(_text, conditions)),
             "INVALIDATION_CONDITIONS_REQUIRED")

    sources = decision.get("source_refs")
    _require(isinstance(sources, list) and bool(sources), "SOURCE_REFS_REQUIRED")
    report_ids = set()
    for source in sources:
        _require(isinstance(source, dict) and set(source) == _SOURCE_FIELDS, "INVALID_SOURCE_FIELDS")
        _require(_text(source["report_id"]) and _text(source["author_id"]), "SOURCE_IDENTITY_REQUIRED")
        sha = source["content_sha256"]
        _require(isinstance(sha, str) and _SHA.fullmatch(sha) is not None, "INVALID_SOURCE_HASH")
        published, received = _time(source["source_published_at"]), _time(source["received_at"])
        _require(published <= received <= as_of, "SOURCE_TIME_ORDER")
        _require(source["report_id"] not in report_ids, "DUPLICATE_SOURCE_REPORT")
        report_ids.add(source["report_id"])

    mode_overrides = decision.get("xiaocao_mode_overrides")
    if schema_version == SCHEMA_VERSION:
        _require(mode_overrides is None, "MODE_OVERRIDE_REQUIRES_V2")
    else:
        _require(isinstance(mode_overrides, list), "MODE_OVERRIDE_LIST_REQUIRED")
        _require(len(mode_overrides) <= 3, "MODE_OVERRIDE_LIMIT")
        source_by_report = {source["report_id"]: source for source in sources}
        seen_modes: set[str] = set()
        for override in mode_overrides:
            _require(isinstance(override, dict) and set(override) == {
                "mode", "source_report_id", "source_quote", "scope",
            }, "INVALID_MODE_OVERRIDE_FIELDS")
            mode = override["mode"]
            _require(_text(mode) and len(mode) <= 128, "INVALID_MODE_OVERRIDE")
            _require(mode not in seen_modes, "DUPLICATE_MODE_OVERRIDE")
            seen_modes.add(mode)
            report_id = override["source_report_id"]
            source = source_by_report.get(report_id)
            _require(source is not None, "MODE_OVERRIDE_SOURCE_NOT_CITED")
            _require(source["author_id"] == "kol-xiaocao", "MODE_OVERRIDE_SOURCE_NOT_XIAOCAO")
            quote = override["source_quote"]
            _require(_text(quote) and len(quote) <= 2000, "MODE_OVERRIDE_QUOTE_REQUIRED")
            _require(override["scope"] == "frozen_candidates_only", "MODE_OVERRIDE_SCOPE_INVALID")

    checks = decision.get("current_checks")
    _require(isinstance(checks, list) and bool(checks), "CURRENT_CHECKS_REQUIRED")
    supported = False
    for check in checks:
        _require(isinstance(check, dict), "INVALID_CURRENT_CHECK")
        _require(_text(check.get("claim")) and _text(check.get("evidence_ref")), "CHECK_EVIDENCE_REQUIRED")
        observed = _time(check.get("observed_at"))
        _require(timedelta(0) <= as_of - observed <= timedelta(minutes=15), "STALE_OR_FUTURE_CHECK")
        verdict = check.get("verdict")
        _require(verdict in ("supports", "contradicts", "uncertain"), "INVALID_CHECK_VERDICT")
        supported = supported or verdict == "supports"
        for flag in ("material", "resolved"):
            _require(flag not in check or type(check[flag]) is bool, "INVALID_CHECK_FLAG")
        if check.get("resolved") is True:
            _require(_text(check.get("resolution_reason")), "RESOLUTION_REASON_REQUIRED")
        if verdict == "contradicts" and check.get("material", True) and decision["runtime"] != "paper":
            _require(check.get("resolved") is True and _text(check.get("resolution_reason")),
                     "UNRESOLVED_MATERIAL_CONTRADICTION")
    _require(supported, "SUPPORTING_CHECK_REQUIRED")

    _require(review.get("decision_sha256") == decision_sha256(decision), "REVIEW_HASH_MISMATCH")
    _require(review.get("status") == "approved", "INDEPENDENT_REVIEW_NOT_APPROVED")
    reviewer = review.get("reviewer_agent_id")
    _require(_text(reviewer) and reviewer != decision["agent_id"], "INDEPENDENT_REVIEWER_REQUIRED")
    _require(all(review.get(flag) is True for flag in _REVIEW_FLAGS), "REVIEW_COVERAGE_INCOMPLETE")
    reviewed_at = _time(review.get("reviewed_at"))
    _require(as_of <= reviewed_at < until, "REVIEW_TIME_ORDER")
    return as_of, until, reviewed_at


def _validate_record(record: dict) -> None:
    _require(isinstance(record, dict) and set(record) == {
        "schema_version", "decision", "review", "receipt", "record_sha256",
    }, "INVALID_RECORD")
    _require(record["schema_version"] == _RECORD_VERSION, "INVALID_RECORD_SCHEMA")
    unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
    _require(record["record_sha256"] == decision_sha256(unsigned), "RECORD_HASH_MISMATCH")
    decision, review, receipt = record["decision"], record["review"], record["receipt"]
    _, until, reviewed_at = _validate_pair(decision, review)
    _require(isinstance(receipt, dict) and set(receipt) == {
        "status", "decision_id", "decision_sha256", "review_sha256", "book", "runtime", "published_at",
    }, "INVALID_RECEIPT")
    _require(receipt["status"] == "published" and all(
        receipt[key] == decision[key] for key in ("decision_id", "book", "runtime")
    ), "RECEIPT_IDENTITY_MISMATCH")
    _require(receipt["decision_sha256"] == decision_sha256(decision)
             and receipt["review_sha256"] == decision_sha256(review), "RECEIPT_HASH_MISMATCH")
    _require(reviewed_at <= _time(receipt["published_at"]) < until, "PUBLICATION_TIME_ORDER")


@contextmanager
def _lock(root: Path, *, write: bool) -> Iterator[None]:
    _require(not root.is_symlink() and root.is_dir(), "INVALID_STORE_DIRECTORY")
    flags = os.O_RDWR | os.O_CREAT if write else os.O_RDONLY
    fd = os.open(root / ".lock", flags | os.O_NOFOLLOW, 0o600)
    try:
        _require(stat.S_ISREG(os.fstat(fd).st_mode), "INVALID_STORE_LOCK")
        fcntl.flock(fd, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        yield
    finally:
        os.close(fd)


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _records(root: Path) -> list[dict]:
    records = []
    for path in sorted(root.iterdir()):
        if path.name == ".lock":
            continue
        _require(not path.name.startswith(".pending-"), "INCOMPLETE_AUDIT_PUBLICATION")
        _require(path.suffix == ".json" and not path.is_symlink() and path.is_file(), "UNEXPECTED_STORE_ENTRY")
        record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        _validate_record(record)
        _require(path.name == record["decision"]["decision_id"] + ".json", "RECORD_FILENAME_MISMATCH")
        records.append(record)
    return records


def _sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _make_store(root: Path) -> None:
    missing = []
    directory = root
    while not directory.exists():
        missing.append(directory)
        directory = directory.parent
    root.mkdir(parents=True, exist_ok=True)
    # fsync of a record's directory alone does not persist that directory's
    # own new entry in its parent. Cover every newly created ancestor as well.
    for directory in reversed(missing):
        _sync_directory(directory.parent)


def _persist(root: Path, record: dict) -> None:
    # The record IS the audit. Keep the pending file on any failure so consumers
    # fail closed, even if a complete final link was made before fsync failed.
    fd, pending_name = tempfile.mkstemp(prefix=".pending-", dir=root)
    pending = Path(pending_name)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(record) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.link(pending, root / (record["decision"]["decision_id"] + ".json"))
    _sync_directory(root)
    # The final record is durable before readers may see a clean directory.
    # A crash resurrecting this temporary entry can only block consumption.
    pending.unlink()


def publish_decision(root: Path, decision: dict, review: dict, now: datetime) -> dict:
    """Validate and durably append; exact retries return the original receipt.

    Failures raise KolPolicyError. A leftover .pending-* is an audit failure
    requiring reconciliation, never permission to retry with a different ID.
    """
    try:
        now = _clock(now)
        # Detach caller-owned objects before validation and acquiring the lock.
        decision, review = json.loads(_canonical(decision)), json.loads(_canonical(review))
        as_of, until, reviewed_at = _validate_pair(decision, review)
        _require(as_of <= now and reviewed_at <= now, "FUTURE_DECISION_OR_REVIEW")
        root = Path(root)
        _make_store(root)
        with _lock(root, write=True):
            for existing in _records(root):
                if existing["decision"]["decision_id"] == decision["decision_id"]:
                    _require(_canonical(existing["decision"]) == _canonical(decision)
                             and _canonical(existing["review"]) == _canonical(review), "DECISION_ID_CONFLICT")
                    _require(_time(existing["receipt"]["published_at"]) <= now, "FUTURE_PUBLICATION")
                    return existing["receipt"]
            _require(now < until, "EXPIRED_DECISION")
            receipt = {
                "status": "published", "decision_id": decision["decision_id"],
                "decision_sha256": decision_sha256(decision), "review_sha256": decision_sha256(review),
                "book": decision["book"], "runtime": decision["runtime"], "published_at": now.isoformat(),
            }
            record = {"schema_version": _RECORD_VERSION, "decision": decision, "review": review, "receipt": receipt}
            record["record_sha256"] = decision_sha256(record)
            _persist(root, record)
            return receipt
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        if isinstance(exc, KolPolicyError):
            raise
        raise KolPolicyError("PUBLICATION_FAILED: " + str(exc)) from exc


def _state(status: str, book: str, runtime: str, reason: str, *, decision_id: str | None = None) -> dict:
    return {
        "status": status, "book": book, "runtime": runtime, "reason": reason,
        "decision_id": decision_id, "buy_scale": 0.0 if status == "blocked" else 1.0,
        "skip_codes": [], "exit_codes": [], "xiaocao_mode_overrides": [],
    }


def _snapshot(record: dict, book: str, runtime: str, now: datetime) -> dict:
    decision = record["decision"]
    _require(decision["book"] == book and decision["runtime"] in (runtime, "both"), "SCOPE_MISMATCH")
    _require(_time(record["receipt"]["published_at"]) <= now, "FUTURE_PUBLICATION")
    _require(_time(decision["as_of"]) <= now, "FUTURE_DECISION")
    if now >= _time(decision["valid_until"]):
        return _state("expired", book, runtime, "KOL_POLICY_EXPIRED", decision_id=decision["decision_id"])
    oldest_check = min(_time(check["observed_at"]) for check in decision["current_checks"])
    if now - oldest_check > timedelta(minutes=15):
        return _state("needs_refresh", book, runtime, "KOL_POLICY_NEEDS_REFRESH",
                      decision_id=decision["decision_id"])
    result = _state("validated", book, runtime, "KOL_POLICY_VALIDATED", decision_id=decision["decision_id"])
    result.update({key: decision[key] for key in ("buy_scale", "skip_codes", "exit_codes")})
    result["xiaocao_mode_overrides"] = list(decision.get("xiaocao_mode_overrides") or [])
    result.update(record=record, evaluated_at=now.isoformat(), decision_sha256=record["receipt"]["decision_sha256"])
    return result


def load_decision(root: Path, book: str, runtime: str, now: datetime) -> dict:
    """Read a scoped point-in-time snapshot. Any corrupt store entry blocks buys.

    An untrusted file cannot reliably identify its book, so store corruption is
    conservatively store-wide. Valid judgments remain isolated by book/runtime.
    A query must name one runtime (live or paper), never both.
    """
    try:
        now = _clock(now)
        _scope(book, runtime)
        root = Path(root)
        if not root.exists() and not root.is_symlink():
            return _state("no_decision", book, runtime, "KOL_POLICY_NO_DECISION")
        if root.is_dir() and not root.is_symlink() and not list(root.iterdir()):
            return _state("no_decision", book, runtime, "KOL_POLICY_NO_DECISION")
        with _lock(root, write=False):
            records = _records(root)
        candidates = [record for record in records if record["decision"]["book"] == book
                      and record["decision"]["runtime"] in (runtime, "both")
                      and _time(record["decision"]["as_of"]) <= now
                      and _time(record["receipt"]["published_at"]) <= now]
        if not candidates:
            return _state("no_decision", book, runtime, "KOL_POLICY_NO_DECISION")
        latest = max(candidates, key=lambda record: (
            _time(record["decision"]["as_of"]), record["decision"]["runtime"] == runtime,
            record["decision"]["decision_id"],
        ))
        return _snapshot(latest, book, runtime, now)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        return _state("blocked", book, runtime, "KOL_POLICY_BLOCKED: " + str(exc))


def _consumable_snapshot(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict):
        return _state("blocked", "", "", "KOL_POLICY_INVALID_SNAPSHOT")
    if snapshot.get("status") in ("no_decision", "neutral", "expired", "needs_refresh", "blocked"):
        return _state(snapshot["status"], snapshot.get("book"), snapshot.get("runtime"),
                      snapshot.get("reason", "KOL_POLICY_NEUTRAL"), decision_id=snapshot.get("decision_id"))
    try:
        _require(snapshot.get("status") == "validated", "VALIDATED_SNAPSHOT_REQUIRED")
        record = snapshot.get("record")
        _validate_record(record)
        _scope(snapshot.get("book"), snapshot.get("runtime"))
        expected = _snapshot(record, snapshot["book"], snapshot["runtime"], _time(snapshot.get("evaluated_at")))
        _require(_canonical(snapshot) == _canonical(expected), "SNAPSHOT_MISMATCH")
        return expected
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        return _state("blocked", snapshot.get("book"), snapshot.get("runtime"), "KOL_POLICY_BLOCKED: " + str(exc))


def _consumable(snapshot: dict, code: str) -> dict:
    expected = _consumable_snapshot(snapshot)
    if expected["status"] != "validated":
        return expected
    try:
        _require(_valid_code(code, expected["book"]), "INVALID_EXACT_CODE")
        return expected
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        return _state("blocked", expected.get("book"), expected.get("runtime"),
                      "KOL_POLICY_BLOCKED: " + str(exc))


def prioritize_xiaocao_modes(rows: list[dict], snapshot: dict, *, max_slots: int = 3) -> list[dict]:
    """Apply an explicit Xiaocao mode follow before the normal mode rotation.

    The function only derives a consumer view of already frozen live Book-B
    candidates.  It cannot add a code, restore UNKNOWN/missing evidence, make a
    BJSE name eligible, or bypass an explicit fillability block.  The immutable
    source row remains available through the ``kol_mode_original_*`` fields.
    """
    copied = [dict(row) for row in rows]
    decision = _consumable_snapshot(snapshot)
    overrides = decision.get("xiaocao_mode_overrides") if decision.get("status") == "validated" else []
    if not overrides:
        return copied
    limit = max(0, min(3, int(max_slots)))

    def number(value: object, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if math.isfinite(parsed) else default

    def frozen_candidate(row: dict) -> bool:
        return (
            row.get("book") == "B"
            and row.get("is_live") is True
            and str(row.get("mode_state") or "") != "UNKNOWN"
            and not str(row.get("code") or "").endswith(".BJSE")
            and ("executable_fillable" not in row or row.get("executable_fillable") is True)
        )

    selected: list[dict] = []
    selected_codes: set[str] = set()
    selected_modes: set[str] = set()
    for priority, override in enumerate(overrides, 1):
        mode = override["mode"]
        candidates = [row for row in copied if frozen_candidate(row) and row.get("mode") == mode]
        candidates.sort(key=lambda row: (
            -number(row.get("mode_exec_score")),
            -number(row.get("mode_exec_rank_score") or row.get("rank_score")),
            str(row.get("code") or ""),
        ))
        if not candidates:
            continue
        row = candidates[0]
        code = str(row.get("code") or "")
        if not _valid_code(code, "B") or code in selected_codes or mode in selected_modes:
            continue
        row.update({
            "kol_mode_original_state": row.get("mode_state"),
            "kol_mode_original_trade_eligible": row.get("mode_trade_eligible"),
            "kol_mode_original_exec_star": row.get("mode_exec_star"),
            "kol_mode_override": {
                "priority": priority,
                "decision_id": decision["decision_id"],
                "decision_sha256": decision.get("decision_sha256"),
                **override,
            },
            "mode_state": "ACTIVE",
            "mode_trade_eligible": True,
        })
        selected.append(row)
        selected_codes.add(code)
        selected_modes.add(mode)

    baseline = [row for row in copied if frozen_candidate(row) and row.get("mode_trade_eligible") is True]
    baseline.sort(key=lambda row: (
        0 if row.get("mode_exec_star") is True else 1,
        int(number(row.get("mode_exec_rank"), 9999)),
        int(number(row.get("mode_exec_candidate_rank"), 9999)),
        -number(row.get("mode_exec_score")),
        str(row.get("code") or ""),
    ))
    ordered_pool = selected + [row for row in baseline if str(row.get("code") or "") not in selected_codes]
    for row in copied:
        row.update(mode_exec_star=False, mode_exec_rank=9999, mode_exec_target_weight=0.0)
    selected = []
    selected_codes.clear()
    selected_modes.clear()
    ranked_pool: list[dict] = []
    for row in ordered_pool:
        code, mode = str(row.get("code") or ""), str(row.get("mode") or "")
        if code in selected_codes or not mode or mode in selected_modes:
            continue
        ranked_pool.append(row)
        selected_codes.add(code)
        selected_modes.add(mode)
    for rank, row in enumerate(ranked_pool, 1):
        row["mode_exec_candidate_rank"] = rank
    selected = ranked_pool[:limit]
    if selected:
        from xiaocao.strategy.mode_switch import target_weights

        weights = target_weights([str(row.get("mode_state") or "UNKNOWN") for row in selected])
        for rank, (row, weight) in enumerate(zip(selected, weights), 1):
            row.update(mode_exec_star=True, mode_exec_rank=rank,
                       mode_exec_candidate_rank=rank, mode_exec_target_weight=weight)
    ranked_ids = {id(row) for row in ranked_pool}
    return ranked_pool + [row for row in copied if id(row) not in ranked_ids]


def buy_adjustment(decision: dict, code: str) -> dict:
    """Bound scaling to [0, 1]; do not create or qualify a buy candidate."""
    snapshot = _consumable(decision, code)
    skip = snapshot["status"] == "blocked" or code in snapshot["skip_codes"] or snapshot["buy_scale"] == 0
    return {"scale": 0.0 if skip else snapshot["buy_scale"], "skip": skip,
            "reason": "KOL_DISCRETIONARY_SKIP" if code in snapshot["skip_codes"] else snapshot["reason"],
            "decision_id": snapshot["decision_id"]}


def exit_adjustment(decision: dict, code: str) -> dict:
    """Return only a KOL_DISCRETIONARY_EXIT request for the exact code."""
    snapshot = _consumable(decision, code)
    triggered = snapshot["status"] == "validated" and code in snapshot["exit_codes"]
    return {"triggered": triggered, "reason": "KOL_DISCRETIONARY_EXIT" if triggered else snapshot["reason"],
            "decision_id": snapshot["decision_id"]}
