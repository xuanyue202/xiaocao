"""Hash-bound daily observations and the weekly response, with no trading authority."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

AUTOMATION_ID = "xiaocao-daily-eod"
DAILY_PATTERN = "output/live/review_feedback/daily/*.json"
WEEKLY_LEDGER = "output/live/flywheel_change_ledger.jsonl"
KINDS = {"issue", "experiment", "design", "finding"}
STATUSES = {"open", "repaired", "verified", "observed", "insufficient_evidence", "accepted_deviation"}


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_ref(root: Path, path: Path) -> dict:
    path = path if path.is_absolute() else root / path
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("EOD_FEEDBACK_OUTSIDE_ROOT")
    return {"path": path.relative_to(root).as_posix(), "sha256": sha(path.read_bytes())}


def _refs(value: dict) -> list[dict]:
    return list(value["evidence"].values()) + [ref for item in value["items"] for ref in item["evidence_refs"]]


def _validate(value: dict, contents: dict[str, bytes]) -> None:
    if value.get("schema_version") != 1 or value.get("authority") != 0:
        raise ValueError("EOD_FEEDBACK_AUTHORITY_INVALID")
    if dt.date.fromisoformat(value["date"]).isoformat() != value["date"]:
        raise ValueError("EOD_FEEDBACK_DATE_INVALID")
    if value.get("automation_id") != AUTOMATION_ID or not value.get("thread_id"):
        raise ValueError("EOD_FEEDBACK_OWNER_INVALID")
    if not isinstance(value["items"], list):
        raise ValueError("EOD_FEEDBACK_ITEMS_INVALID")
    ids = set()
    for item in value["items"]:
        if (not isinstance(item.get("id"), str) or not item["id"].strip() or item["id"] in ids
                or item.get("kind") not in KINDS or item.get("status") not in STATUSES):
            raise ValueError("EOD_FEEDBACK_ITEM_INVALID")
        ids.add(item["id"])
        for field in ("summary", "owner", "next_action", "next_verification", "falsifier", "basis"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"EOD_FEEDBACK_REQUIRED:{item['id']}:{field}")
        if item["basis"] not in {"observed", "inference"} or not item.get("evidence_refs"):
            raise ValueError("EOD_FEEDBACK_EVIDENCE_REQUIRED")
        if item["kind"] == "experiment":
            count = item.get("effective_samples")
            if (type(count) is not int or count < 0 or not item.get("sample_unit")
                    or type(item.get("comparable")) is not bool):
                raise ValueError("EOD_FEEDBACK_SAMPLE_INVALID")
            if (not count or not item["comparable"]) and item["status"] != "insufficient_evidence":
                raise ValueError("EOD_FEEDBACK_INSUFFICIENT_SAMPLES")
        if item["kind"] == "design" and not item.get("acceptance"):
            raise ValueError("EOD_FEEDBACK_ACCEPTANCE_REQUIRED")
        if item["kind"] == "issue" and item["status"] == "verified":
            proof = item.get("verification", {})
            if (not re.fullmatch(r"[0-9a-f]{40}", proof.get("code_commit", ""))
                    or not proof.get("tests") or not proof.get("natural")):
                raise ValueError("EOD_FEEDBACK_NATURAL_VERIFICATION_REQUIRED")
            if any(ref not in item["evidence_refs"] for ref in proof["tests"] + proof["natural"]):
                raise ValueError("EOD_FEEDBACK_VERIFICATION_UNBOUND")
            if any(ref in proof["tests"] for ref in proof["natural"]):
                raise ValueError("EOD_FEEDBACK_VERIFICATION_NOT_INDEPENDENT")
    for ref in _refs(value):
        path = ref["path"]
        saved = value.get("snapshots", {}).get(path, ref)
        data = contents.get(saved.get("path"))
        if (Path(path).is_absolute() or ".." in Path(path).parts
                or Path(saved["path"]).is_absolute() or ".." in Path(saved["path"]).parts
                or saved.get("sha256") != ref.get("sha256")
                or data is None or sha(data) != ref.get("sha256")):
            raise ValueError(f"EOD_FEEDBACK_EVIDENCE_MISMATCH:{path}")


def record_daily(root: Path, value: dict) -> Path:
    """Publish one immutable final handoff per day; identical retries reuse bytes."""
    contents = {}
    for ref in _refs(value):
        actual = evidence_ref(root, Path(ref["path"]))
        if actual != ref:
            raise ValueError("EOD_FEEDBACK_EVIDENCE_MISMATCH")
        contents[ref["path"]] = (root / ref["path"]).read_bytes()
    _validate(value, contents)
    value = json.loads(canonical(value))
    value["snapshots"] = {}
    for name, data in contents.items():
        blob = root / "output/live/review_feedback/evidence" / sha(data)
        blob.parent.mkdir(parents=True, exist_ok=True)
        try:
            with blob.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            if blob.read_bytes() != data:
                raise ValueError("EOD_FEEDBACK_SNAPSHOT_CORRUPTED") from None
        value["snapshots"][name] = {"path": blob.relative_to(root).as_posix(), "sha256": sha(data)}
    data = canonical(value)
    path = root / "output/live/review_feedback/daily" / (value["date"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".feedback-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("EOD_FEEDBACK_DAY_ALREADY_RECORDED") from None
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def referenced_paths(data: bytes) -> list[str]:
    """Only explicit local receipt references; no semantic-source discovery."""
    value = json.loads(data)
    return [ref["path"] for ref in (value["snapshots"].values() if "snapshots" in value else _refs(value))]


def observe_feedback(contents: dict[str, bytes], *, as_of: dt.date) -> dict:
    items, errors, receipts = {}, [], []
    for path in sorted(p for p in contents if Path(p).match(DAILY_PATTERN)):
        try:
            value = json.loads(contents[path])
            day = dt.date.fromisoformat(value["date"])
            if day > as_of:
                continue
            _validate(value, contents)
            receipts.append({"path": path, "sha256": sha(contents[path])})
            for item in value["items"]:
                prior = items.get(item["id"], {})
                items[item["id"]] = dict(item, first_seen=prior.get("first_seen", value["date"]),
                    last_seen=value["date"], observations=prior.get("observations", 0) + 1,
                    daily_receipt=receipts[-1])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            errors.append({"path": path, "error": str(exc)})
    prior_responses = {}
    for line in contents.get(WEEKLY_LEDGER, b"").splitlines():
        try:
            row = json.loads(line)
            if row["date"] > as_of.isoformat():
                continue
            state = row.get("eod_feedback_state", {})
            unsigned = {k: v for k, v in state.items() if k != "sha256"}
            if state and state.get("sha256") != sha(canonical(unsigned)):
                raise ValueError("WEEKLY_FEEDBACK_STATE_HASH_INVALID")
            for response in state.get("responses", []):
                prior = prior_responses.get(response["id"])
                if prior is None or row["date"] >= prior["reviewed_at"]:
                    prior_responses[response["id"]] = dict(response, reviewed_at=row["date"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            errors.append({"path": WEEKLY_LEDGER, "error": str(exc)})
    selected = []
    for identity, item in sorted(items.items()):
        item["prior_weekly_response"] = prior_responses.get(identity)
        # Closed old repairs stay in immutable audit; unresolved items never age out.
        current_week = item["last_seen"] >= (as_of - dt.timedelta(days=6)).isoformat()
        prior = prior_responses.get(identity) or {}
        prior_closed = prior.get("disposition") == "close" and prior["reviewed_at"] >= item["last_seen"]
        if current_week or (item["status"] != "verified" and not (prior_closed and item["kind"] != "issue")):
            selected.append(item)
    return {"schema_version": 1, "authority": 0, "as_of": as_of.isoformat(),
            "status": "evidence_gap" if errors else ("review_required" if selected else "no_records"),
            "receipts": receipts, "items": selected, "errors": errors}


def weekly_response_state(plan: dict) -> dict | None:
    """Rebuild required coverage from frozen bytes, never a mutable plan summary."""
    evidence = plan.get("data_evidence_review", {})
    if plan.get("eod_feedback_contract") == 1 and not evidence.get("input_manifest"):
        raise ValueError("WEEKLY_FEEDBACK_FROZEN_INVENTORY_REQUIRED")
    if "eod_feedback" not in evidence:
        if (plan.get("eod_feedback_contract") == 1
                or evidence.get("input_manifest", {}).get("eod_feedback_contract") == 1):
            raise ValueError("WEEKLY_FEEDBACK_FROZEN_REVIEW_REQUIRED")
        return None  # Immutable pre-schema plans retain their old contract.
    contents = {row["path"]: Path(row["snapshot_path"]).read_bytes()
                for row in evidence["input_manifest"]["files"] if row.get("snapshot_path")}
    observed = observe_feedback(contents, as_of=dt.date.fromisoformat(plan["date"]))
    if observed != evidence["eod_feedback"]:
        raise ValueError("WEEKLY_FEEDBACK_FROZEN_REVIEW_MISMATCH")
    responses = plan.get("eod_feedback_responses", [])
    required = {item["id"]: item for item in observed["items"]}
    if observed["errors"] and not plan.get("eod_feedback_gap_review", "").strip():
        raise ValueError("WEEKLY_FEEDBACK_GAPS_REQUIRE_EXPLANATION")
    if (len(responses) != len(required) or {row.get("id") for row in responses} != set(required)):
        raise ValueError("WEEKLY_FEEDBACK_RESPONSE_COVERAGE_REQUIRED")
    refs = {(p, sha(data)) for p, data in contents.items()}
    for response in responses:
        if response.get("disposition") not in {"continue", "deepen", "verify", "close", "needs_evidence", "stop_proposal"}:
            raise ValueError("WEEKLY_FEEDBACK_DISPOSITION_INVALID")
        for field in ("rationale", "owner", "next_action", "next_review"):
            if not isinstance(response.get(field), str) or not response[field].strip():
                raise ValueError("WEEKLY_FEEDBACK_RESPONSE_INCOMPLETE")
        dt.date.fromisoformat(response["next_review"])
        if response["next_review"] <= plan["date"]:
            raise ValueError("WEEKLY_FEEDBACK_NEXT_REVIEW_INVALID")
        if not response.get("evidence_refs") or any((r["path"], r["sha256"]) not in refs
                                                   for r in response["evidence_refs"]):
            raise ValueError("WEEKLY_FEEDBACK_RESPONSE_EVIDENCE_UNBOUND")
        item = required[response["id"]]
        if response["disposition"] == "close" and item["kind"] == "issue" and item["status"] != "verified":
            raise ValueError("WEEKLY_FEEDBACK_REPAIR_NOT_NATURALLY_VERIFIED")
    state = {"schema_version": 1, "authority": 0, "date": plan["date"],
             "input_manifest_sha256": evidence["input_manifest"]["sha256"], "responses": responses,
             "evidence_gaps": observed["errors"], "gap_review": plan.get("eod_feedback_gap_review")}
    state["sha256"] = sha(canonical(state))
    return state


def render_feedback(observed: dict, responses: list[dict]) -> list[str]:
    lines = ["", "## 每日发现与周度处理", "",
             f"- 冻结每日交接 {len(observed.get('receipts', []))} 份；待回应 {len(observed.get('items', []))} 项；证据缺口 {len(observed.get('errors', []))} 项。"]
    replies = {row["id"]: row for row in responses}
    for item in observed.get("items", []):
        reply = replies.get(item["id"], {})
        lines.append(f"- `{item['id']}`（{item['first_seen']}–{item['last_seen']}，{item['observations']} 次）：{item['summary']}；状态 {item['status']}。"
                     f" 周度 {reply.get('disposition', '未回应')}：{reply.get('rationale', '待审')}；"
                     f"负责人 {reply.get('owner', item['owner'])}；下一步 {reply.get('next_action', item['next_action'])}；"
                     f"下次 {reply.get('next_review', item['next_verification'])}。")
    return lines
