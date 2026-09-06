#!/usr/bin/env python3
"""Local KOL checkpoint gate: poll -> claimed work -> exact terminal ack.

Only production publication receipts, local Book B ownership and published KOL
decisions are read. No broker, MCP, raw capture scan, calendar query or business
writer runs here. Weekday/session slots are candidates, NOT proof of an open
exchange; every consumer must still validate its trading calendar and gates.
Extra morning work starts at 09:40 and stops before 11:30. The five-minute
slots owned by opening (09:35/09:45/09:55), precheck (14:25) and closing (14:55)
are reserved, including delayed polls within those slots. 14:50 remains a
candidate for the ordinary sparse hard-risk monitor, never a soft-close pass.
Reserved/window no-ops consume no source or decision changes. Existing native
writer locks and durable plans take priority; consumers must still acquire
their own execution fences because a local precheck is not a transferred lock.

The four original sparse slots always request the regular monitor. Other slots
wake for source or published decision changes, or a stale published decision
with explicit open positions in its own runtime. Fresh decision changes need
monitor consumption, not another semantic review. On EVERY run, the consumer
runs each existing paper/live monitor once FIRST, protecting hard exits, then
arranges any required semantic review. Newly reviewed packs are consumed by a
later tick, never by rerunning a monitor within the same claim. Each stale
decision is acknowledged once, including a degraded completion. A claim never
expires: interrupted/unknown business work requires exact reconciliation.

ack asserts the entire claimed work completed or terminally degraded; it is
not an acknowledgement of dispatch. reconcile additionally records an explicit
user/root-agent terminal confirmation and its evidence reference. These are
auditable caller assertions, not authentication or permission to trade.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.kol.publication import PublicationLedger
from xiaocao.kol.trading_context import PRODUCTION_LEDGER_PATHS
from xiaocao.live import kol_policy
from xiaocao.live.book_b_live_lifecycle import _validate_ownership_chain, open_execution_plan_ids


ROOT = Path(__file__).resolve().parents[1]
STATE_RELATIVE_PATH = Path("output/live/kol_policy/ticks")
_CHINA = ZoneInfo("Asia/Shanghai")
_REGULAR = {"10:25", "10:55", "13:25", "13:55"}
_RESERVED = {"09:35", "09:45", "09:55", "14:25", "14:55"}


class TickError(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _clock(now: datetime | None) -> datetime:
    result = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(result, datetime) or result.utcoffset() is None:
        raise TickError("AWARE_CLOCK_REQUIRED")
    return result.astimezone(timezone.utc)


def _time(value: str) -> datetime:
    return _clock(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _result(status: str, reason: str, **fields) -> dict:
    return {"status": status, "reason": reason, "need_semantic_review": False,
            "regular_monitor": False, "decision_changed": False, **fields}


def _json(path: Path) -> dict:
    if path.is_symlink():
        raise TickError("SYMLINK_INPUT")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TickError("OBJECT_REQUIRED")
    return value


def _jsonl(path: Path) -> list[dict]:
    if path.is_symlink():
        raise TickError("SYMLINK_INPUT")
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise TickError("ROW_OBJECT_REQUIRED")
    return rows


@contextmanager
def _locked(root: Path):
    directory = root / STATE_RELATIVE_PATH
    if directory.resolve() != directory:
        raise TickError("SYMLINK_STATE_DIRECTORY")
    # Persist newly created ancestors as well as the claim's final directory.
    missing = []
    path = directory
    while not path.exists():
        missing.append(path)
        path = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    for path in reversed(missing):
        _sync(path.parent)
    fd = os.open(directory / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield directory


def _sync(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save(directory: Path, state: dict) -> None:
    value = {**state, "state_sha256": _digest(state)}
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=directory)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, directory / "state.json")
    _sync(directory)


def _state(root: Path, directory: Path) -> dict:
    if any(directory.glob(".pending-*")):
        raise TickError("STATE_COMMIT_UNCERTAIN")
    path = directory / "state.json"
    if not path.exists():
        return {"schema_version": 1, "root": str(root), "claim": None, "last_ack": None,
                "cursor": {"fingerprint": _digest([]), "decision_fingerprint": _digest([]),
                           "slot": None, "expired": []}}
    value = _json(path)
    claimed = value.pop("state_sha256", None)
    if claimed != _digest(value) or value.get("root") != str(root) or value.get("schema_version") != 1:
        raise TickError("STATE_HASH_OR_ROOT_MISMATCH")
    if value["claim"] is not None:
        claim = dict(value["claim"])
        token = claim.pop("token", None)
        if token != _digest(claim) or claim["root"] != str(root):
            raise TickError("CLAIM_HASH_MISMATCH")
    return value


def publication_fingerprint(root: Path, now: datetime) -> str:
    """Fixed production allowlist; raw/prepared/notification rows do not wake work."""
    published = []
    for relative in PRODUCTION_LEDGER_PATHS:
        path = root / relative
        if path.is_symlink():
            raise TickError("SYMLINK_LEDGER")
        for event in PublicationLedger(path.parent)._events_unlocked():
            if (event.get("event") == "publication_receipt"
                    and event.get("receipt", {}).get("recordState") in ("published", "superseded")):
                if _time(event["occurred_at"]) > now:
                    raise TickError("FUTURE_PUBLICATION")
                published.append([relative, event["event_id"]])
    return _digest(sorted(published))


def _open_runtimes(root: Path) -> set[str]:
    opened = set()
    for row in _jsonl(root / "output/live/positions.jsonl"):
        shares = row.get("shares")
        if (row.get("book") == "B" and row.get("exit_date") is None
                and row.get("exit_price") is None
                and type(shares) in (int, float) and 0 < shares < float("inf")):
            opened.add("paper")
    # Read the local ownership ledger, never a broker table or mixed account.
    path = root / "output/live/book_b_live_execution/book_b_ownership_evidence.jsonl"
    rows, _ = _validate_ownership_chain(_jsonl(path))
    balances: dict[str, int] = {}
    for row in rows:
        if row.get("logical_account_id") != "primary":
            raise TickError("LIVE_OWNERSHIP_ACCOUNT_MISMATCH")
        code = row["code"]
        balances[code] = balances.get(code, 0) + int(row["shares"]) * (1 if row["side"].upper() == "BUY" else -1)
        if balances[code] < 0:
            raise TickError("LIVE_OWNERSHIP_NEGATIVE")
    if any(balances.values()):
        opened.add("live")
    return opened


def _decision_inputs(root: Path, now: datetime) -> tuple[str, list[str]]:
    runtimes = _open_runtimes(root)
    store = root / "output/live/kol_policy/decisions"
    if not store.exists():
        return _digest([]), []
    if store.is_symlink():
        raise TickError("SYMLINK_POLICY")
    if not any(store.iterdir()):
        return _digest([]), []
    expired, fingerprints = [], []
    # A held writer must not turn a cheap tick into a blocking policy read.
    with (store / ".lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        # Reuse the policy store's complete hash/review/scope validation and
        # its exact current-check TTL; no alternate judgment schema lives here.
        records = kol_policy._records(store)
        for runtime in ("paper", "live"):
            candidates = [record for record in records
                          if record["decision"]["book"] == "B"
                          and record["decision"]["runtime"] in (runtime, "both")
                          and _time(record["decision"]["as_of"]) <= now
                          and _time(record["receipt"]["published_at"]) <= now]
            if not candidates:
                continue
            record = max(candidates, key=lambda item: (
                _time(item["decision"]["as_of"]), item["decision"]["runtime"] == runtime,
                item["decision"]["decision_id"],
            ))
            snapshot = kol_policy._snapshot(record, "B", runtime, now)
            fingerprints.append([runtime, record["record_sha256"]])
            if runtime in runtimes and snapshot["status"] in ("expired", "needs_refresh"):
                expired.append(runtime + ":" + record["record_sha256"])
    return _digest(sorted(fingerprints)), expired


def _live_owner(root: Path) -> dict | None:
    """Read existing local fences only; never create locks in business stores."""
    state_root = root / "output/live/book_b_live_execution"
    account = hashlib.sha256(b"primary").hexdigest()[:24]
    paths = (state_root / "book_b_live_checkpoint.lock",
             state_root / "account_writer_locks" / f"account-{account}.lock")
    for path in paths:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            continue
        with os.fdopen(fd, "rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return _result("no_op", "LIVE_WRITER_OWNS_CHECKPOINT")
    if open_execution_plan_ids(state_root):
        return _result("reconcile_required", "EXISTING_LIVE_PLAN_REQUIRES_OWNER")
    return None


def poll(root: Path = ROOT, *, now: datetime | None = None) -> dict:
    try:
        root, current = Path(root).resolve(), _clock(now)
        with _locked(root) as directory:
            state = _state(root, directory)
            if state["claim"] is not None:
                return _result("reconcile_required", "RUNNING_CLAIM", token=state["claim"]["token"])
            local = current.astimezone(_CHINA)
            minute = local.hour * 60 + local.minute
            if local.weekday() > 4:
                return _result("no_op", "OUTSIDE_CANDIDATE_WINDOW")
            slot = local.replace(minute=local.minute // 5 * 5, second=0, microsecond=0).isoformat()
            if slot[11:16] in _RESERVED:
                return _result("no_op", "RESERVED_OWNED_SLOT")
            if not (580 <= minute < 690 or 780 <= minute <= 890):
                return _result("no_op", "OUTSIDE_CANDIDATE_WINDOW")
            cursor = state["cursor"]
            if cursor["slot"] is not None and slot <= cursor["slot"]:
                return _result("no_op", "SLOT_ALREADY_ACKNOWLEDGED")
            owner = _live_owner(root)
            if owner is not None:
                return owner
            fingerprint = publication_fingerprint(root, current)
            decision_fingerprint, stale = _decision_inputs(root, current)
            expired = sorted(set(stale) - set(cursor["expired"]))
            decision_changed = decision_fingerprint != cursor.get("decision_fingerprint", _digest([]))
            regular = slot[11:16] in _REGULAR
            semantic = fingerprint != cursor["fingerprint"] or bool(expired)
            if not regular and not semantic and not decision_changed:
                return _result("no_op", "UNCHANGED")
            claim = {"root": str(root), "nonce": uuid.uuid4().hex, "claimed_at": current.isoformat(),
                     "cadence_slot": slot, "fingerprint": fingerprint, "expired": expired,
                     "decision_fingerprint": decision_fingerprint, "decision_changed": decision_changed,
                     "need_semantic_review": semantic, "regular_monitor": regular}
            claim["token"] = _digest(claim)
            state["claim"] = claim
            _save(directory, state)
            return _result("run", "CLAIMED", **{key: claim[key] for key in (
                "token", "cadence_slot", "fingerprint", "decision_fingerprint", "decision_changed",
                "need_semantic_review", "regular_monitor")})
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _result("reconcile_required", "LOCAL_GATE_READBACK_REQUIRED")


def _finish(root: Path, token: str, outcome: str, now: datetime | None,
            confirmation: dict | None) -> dict:
    try:
        root, current = Path(root).resolve(), _clock(now)
        if outcome not in ("completed", "degraded") or not isinstance(token, str) or len(token) != 64:
            raise TickError("INVALID_ACK")
        with _locked(root) as directory:
            state = _state(root, directory)
            last = state["last_ack"]
            if last is not None and last["token"] == token:
                if last["outcome"] != outcome:
                    raise TickError("ACK_OUTCOME_CONFLICT")
                return _result("no_op", "ALREADY_ACKNOWLEDGED", token=token, outcome=outcome)
            claim = state["claim"]
            if claim is None or token != claim["token"] or current < _time(claim["claimed_at"]):
                raise TickError("EXACT_CLAIM_REQUIRED")
            state["cursor"] = {"fingerprint": claim["fingerprint"], "slot": claim["cadence_slot"],
                               "decision_fingerprint": claim.get("decision_fingerprint", state["cursor"].get("decision_fingerprint", _digest([]))),
                               "expired": sorted(set(state["cursor"]["expired"]) | set(claim["expired"]))}
            state["last_ack"] = {"token": token, "outcome": outcome, "acknowledged_at": current.isoformat(),
                                 "claim": claim, "confirmation": confirmation}
            state["claim"] = None
            _save(directory, state)
            return _result("no_op", "ACKNOWLEDGED", token=token, outcome=outcome)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _result("reconcile_required", "EXACT_TERMINAL_ACK_REQUIRED")


def ack(root: Path, *, token: str, outcome: str, now: datetime | None = None) -> dict:
    return _finish(root, token, outcome, now, None)


def reconcile(root: Path, *, token: str, outcome: str, confirmed_by: str,
              evidence_ref: str, now: datetime | None = None) -> dict:
    if confirmed_by not in ("user", "root") or not isinstance(evidence_ref, str) or not evidence_ref.strip():
        return _result("reconcile_required", "EXPLICIT_TERMINAL_CONFIRMATION_REQUIRED")
    return _finish(root, token, outcome, now, {"confirmed_by": confirmed_by, "evidence_ref": evidence_ref})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("poll", "ack", "reconcile"):
        sub = commands.add_parser(command)
        sub.add_argument("--root", type=Path, default=ROOT)
        sub.add_argument("--now", help="Aware ISO clock; tests only, requires a separate --root")
        if command != "poll":
            sub.add_argument("--token", required=True)
            sub.add_argument("--outcome", choices=("completed", "degraded"), required=True)
        if command == "reconcile":
            sub.add_argument("--confirmed-by", choices=("user", "root"), required=True)
            sub.add_argument("--evidence-ref", required=True)
    args = parser.parse_args(argv)
    try:
        if args.now is not None and args.root.resolve() == ROOT.resolve():
            raise TickError("TEST_CLOCK_REQUIRES_SEPARATE_ROOT")
        now = _time(args.now) if args.now is not None else None
        if args.command == "poll":
            result = poll(args.root, now=now)
        elif args.command == "ack":
            result = ack(args.root, token=args.token, outcome=args.outcome, now=now)
        else:
            result = reconcile(args.root, token=args.token, outcome=args.outcome, now=now,
                               confirmed_by=args.confirmed_by, evidence_ref=args.evidence_ref)
    except (ValueError, TypeError, AttributeError):
        result = _result("reconcile_required", "INVALID_CLI_CLOCK")
    print(_canonical(result).decode("utf-8"))
    return 2 if result["status"] == "reconcile_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
