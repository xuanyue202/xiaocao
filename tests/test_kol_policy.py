from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.live import kol_policy as policy


NOW = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
CODE = "600519.XSHG"
OTHER = "000001.XSHE"


def iso(when: datetime) -> str:
    return when.isoformat()


def make_decision(identifier: str = "decision-1", *, as_of: datetime = NOW,
                  book: str = "B", runtime: str = "live", scale: float = 0.5) -> dict:
    return {
        "schema_version": "kol-trading-decision.v1", "decision_id": identifier,
        "agent_id": "full-source-reader", "book": book, "runtime": runtime,
        "as_of": iso(as_of), "valid_until": iso(as_of + timedelta(hours=2)),
        "source_refs": [{
            "report_id": "report-1", "content_sha256": "a" * 64, "author_id": "xiaocao",
            "source_published_at": iso(as_of - timedelta(days=2)),
            "received_at": iso(as_of - timedelta(minutes=1)),
        }, {
            "report_id": "report-2", "content_sha256": "b" * 64, "author_id": "environment-author",
            "source_published_at": iso(as_of - timedelta(hours=1)),
            "received_at": iso(as_of - timedelta(minutes=1)),
        }],
        "buy_scale": scale, "skip_codes": [], "exit_codes": [],
        "rationale": "Full-source short-term judgment with contextual theme evidence.",
        "invalidation_conditions": ["Reassess if the observed liquidity deteriorates."],
        "current_checks": [{
            "claim": "Current evidence supports the bounded judgment.",
            "observed_at": iso(as_of - timedelta(minutes=2)),
            "evidence_ref": "quote-readback:20260906T015800Z", "verdict": "supports",
        }],
    }


def make_review(decision: dict, **changes) -> dict:
    return {
        "decision_sha256": policy.decision_sha256(decision), "status": "approved",
        "reviewer_agent_id": "independent-main-reviewer", "reviewed_at": decision["as_of"],
        "coverage_complete": True, "source_fidelity": True,
        "applicability_checked": True, "counterevidence_checked": True, **changes,
    }


def publish(root: Path, decision: dict, now: datetime = NOW) -> dict:
    return policy.publish_decision(root, decision, make_review(decision), now)


def load(root: Path, now: datetime = NOW, book: str = "B", runtime: str = "live") -> dict:
    return policy.load_decision(root, book, runtime, now)


def assert_inert(snapshot: dict, status: str, scale: float) -> None:
    assert snapshot["status"] == status
    assert snapshot["buy_scale"] == scale
    assert snapshot["exit_codes"] == []
    assert policy.buy_adjustment(snapshot, CODE)["scale"] == scale
    assert policy.buy_adjustment(snapshot, CODE)["skip"] is (scale == 0)
    assert policy.exit_adjustment(snapshot, CODE)["triggered"] is False


def test_publish_load_and_exact_adjustments(tmp_path: Path) -> None:
    decision = make_decision()
    decision.update(skip_codes=[CODE], exit_codes=[OTHER])
    original = copy.deepcopy(decision)
    receipt = publish(tmp_path, decision)
    snapshot = load(tmp_path)
    assert receipt["status"] == "published"
    assert snapshot["status"] == "validated"
    assert snapshot["record"]["decision"] == original == decision
    assert snapshot["record"]["review"] == make_review(decision)
    assert snapshot["record"]["receipt"] == receipt
    assert snapshot["decision_sha256"] == receipt["decision_sha256"]
    assert policy.buy_adjustment(snapshot, CODE) == {
        "scale": 0, "skip": True, "reason": "KOL_DISCRETIONARY_SKIP", "decision_id": "decision-1",
    }
    assert policy.buy_adjustment(snapshot, OTHER)["scale"] == 0.5
    assert policy.exit_adjustment(snapshot, OTHER) == {
        "triggered": True, "reason": "KOL_DISCRETIONARY_EXIT", "decision_id": "decision-1",
    }
    assert policy.exit_adjustment(snapshot, CODE)["triggered"] is False
    assert policy.exit_adjustment(snapshot, "000001.XSHG")["triggered"] is False
    assert policy.buy_adjustment(snapshot, "600519.XSHE")["skip"] is False
    assert sorted(path.name for path in tmp_path.iterdir()) == [".lock", "decision-1.json"]


@pytest.mark.parametrize("scale", [0, 0.1, 0.5, 1])
def test_scale_never_enlarges_an_eligible_buy(tmp_path: Path, scale: float) -> None:
    publish(tmp_path, make_decision(scale=scale))
    adjustment = policy.buy_adjustment(load(tmp_path), CODE)
    assert adjustment["scale"] == scale
    assert adjustment["skip"] is (scale == 0)


def test_prose_and_author_counts_cannot_generate_or_expand_actions(tmp_path: Path) -> None:
    decision = make_decision(scale=1)
    decision["rationale"] = f"买入 {CODE}，立即卖出 {OTHER}，清仓。"
    decision["current_checks"][0]["claim"] = f"Sell {CODE}, buy {OTHER}, bullish bearish risk."
    decision["source_refs"] += [
        {**decision["source_refs"][1], "report_id": f"context-{index}"} for index in range(8)
    ]
    publish(tmp_path, decision)
    snapshot = load(tmp_path)
    assert snapshot["skip_codes"] == snapshot["exit_codes"] == []
    assert policy.buy_adjustment(snapshot, CODE)["scale"] == 1
    assert policy.exit_adjustment(snapshot, OTHER)["triggered"] is False


def test_missing_and_empty_store_are_neutral_without_writes(tmp_path: Path) -> None:
    assert_inert(load(tmp_path / "missing"), "no_decision", 1)
    assert_inert(load(tmp_path), "no_decision", 1)
    assert list(tmp_path.iterdir()) == []


def test_latest_expired_decision_does_not_resurrect_older_one(tmp_path: Path) -> None:
    older = make_decision("old", as_of=NOW - timedelta(minutes=10), scale=0)
    older["valid_until"] = iso(NOW + timedelta(hours=10))
    older["exit_codes"] = [CODE]
    newer = make_decision("new")
    newer["valid_until"] = iso(NOW + timedelta(minutes=1))
    publish(tmp_path, older)
    publish(tmp_path, newer)
    assert load(tmp_path)["decision_id"] == "new"
    expired = load(tmp_path, NOW + timedelta(minutes=1))
    assert_inert(expired, "expired", 1)
    assert expired["decision_id"] == "new"


def test_retry_after_expiry_returns_original_receipt_without_extending_ttl(tmp_path: Path) -> None:
    decision = make_decision()
    receipt = publish(tmp_path, decision)
    path = tmp_path / "decision-1.json"
    before = path.read_bytes(), path.stat().st_mtime_ns
    reordered = dict(reversed(list(decision.items())))
    assert publish(tmp_path, reordered, NOW + timedelta(days=1)) == receipt
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert_inert(load(tmp_path, NOW + timedelta(days=1)), "expired", 1)


@pytest.mark.parametrize("change", ["decision", "review", "scope", "expiry"])
def test_id_conflicts_do_not_overwrite_original(tmp_path: Path, change: str) -> None:
    decision = make_decision()
    publish(tmp_path, decision)
    before = (tmp_path / "decision-1.json").read_bytes()
    if change == "decision":
        decision["buy_scale"] = 0
    elif change == "scope":
        decision.update(book="T", runtime="paper")
    elif change == "expiry":
        decision["valid_until"] = iso(NOW + timedelta(hours=3))
    review = make_review(decision)
    if change == "review":
        review["reviewer_agent_id"] = "different-reviewer"
    with pytest.raises(policy.KolPolicyError, match="DECISION_ID_CONFLICT"):
        policy.publish_decision(tmp_path, decision, review, NOW)
    assert (tmp_path / "decision-1.json").read_bytes() == before


def test_late_old_judgment_is_audited_without_replacing_newer(tmp_path: Path) -> None:
    publish(tmp_path, make_decision("new", scale=0.1))
    publish(tmp_path, make_decision("late-old", as_of=NOW - timedelta(minutes=5), scale=1),
            NOW + timedelta(minutes=1))
    assert (tmp_path / "late-old.json").exists()
    snapshot = load(tmp_path, NOW + timedelta(minutes=2))
    assert snapshot["decision_id"] == "new"
    assert policy.buy_adjustment(snapshot, CODE)["scale"] == 0.1


@pytest.mark.parametrize("reverse", [False, True])
def test_runtime_ties_are_specific_then_stable_id_independent_of_arrival(tmp_path: Path, reverse: bool) -> None:
    decisions = [make_decision("z-both", runtime="both", scale=0.2),
                 make_decision("a-live", scale=0.4), make_decision("b-live", scale=0.6)]
    for decision in reversed(decisions) if reverse else decisions:
        publish(tmp_path, decision)
    assert load(tmp_path)["decision_id"] == "b-live"
    assert load(tmp_path, runtime="paper")["decision_id"] == "z-both"
    publish(tmp_path, make_decision("new-both", as_of=NOW + timedelta(minutes=1), runtime="both"),
            NOW + timedelta(minutes=1))
    assert load(tmp_path, NOW + timedelta(minutes=1))["decision_id"] == "new-both"


def test_valid_scopes_are_isolated(tmp_path: Path) -> None:
    decisions = [make_decision("b-live", scale=0.1), make_decision("b-paper", runtime="paper", scale=0.2),
                 make_decision("t-paper", book="T", runtime="paper", scale=0.3),
                 make_decision("us-paper", book="KOL-US", runtime="paper", scale=0.4)]
    decisions[-1].update(skip_codes=["AAPL"], exit_codes=["BRK.B"])
    for decision in decisions:
        publish(tmp_path, decision)
    for decision in decisions:
        snapshot = load(tmp_path, book=decision["book"], runtime=decision["runtime"])
        assert snapshot["decision_id"] == decision["decision_id"]
    us = load(tmp_path, book="KOL-US", runtime="paper")
    assert policy.buy_adjustment(us, "AAPL")["skip"] is True
    assert policy.exit_adjustment(us, "BRK.B")["triggered"] is True
    assert policy.exit_adjustment(us, "BRK-B")["triggered"] is False


def test_no_cross_runtime_fallback(tmp_path: Path) -> None:
    publish(tmp_path, make_decision(runtime="paper"))
    assert_inert(load(tmp_path), "no_decision", 1)
    assert_inert(load(tmp_path, book="T", runtime="paper"), "no_decision", 1)


def test_historical_load_checks_publication_time_as_well_as_decision_time(tmp_path: Path) -> None:
    decision = make_decision()
    decision["exit_codes"] = [CODE]
    publish(tmp_path, decision, NOW + timedelta(minutes=10))
    assert_inert(load(tmp_path, NOW - timedelta(minutes=1)), "no_decision", 1)
    assert_inert(load(tmp_path, NOW + timedelta(minutes=9)), "no_decision", 1)
    assert load(tmp_path, NOW + timedelta(minutes=10))["status"] == "validated"
    future = make_decision("future", as_of=NOW + timedelta(minutes=20), scale=0)
    publish(tmp_path, future, NOW + timedelta(minutes=20))
    assert load(tmp_path, NOW + timedelta(minutes=15))["decision_id"] == "decision-1"


@pytest.mark.parametrize("field,value", [
    ("schema_version", "v0"), ("decision_id", ""), ("decision_id", "../escape"),
    ("decision_id", "/absolute"), ("decision_id", ".hidden"), ("agent_id", ""),
    ("book", "A"), ("runtime", "unknown"), ("runtime", "LIVE"),
    ("as_of", "2026-09-06T02:00:00"), ("as_of", "2026-09-06T10:00:00+08:00"),
    ("as_of", "2026-09-31T02:00:00Z"), ("valid_until", iso(NOW)),
    ("valid_until", iso(NOW - timedelta(seconds=1))),
    ("valid_until", iso(NOW + timedelta(hours=24, microseconds=1))),
    ("buy_scale", -0.01), ("buy_scale", 1.01), ("buy_scale", float("nan")),
    ("buy_scale", float("inf")), ("buy_scale", float("-inf")),
    ("buy_scale", "0.5"), ("buy_scale", True), ("buy_scale", None),
    ("skip_codes", ["600519"]), ("skip_codes", ["*"]), ("skip_codes", ["6005*"]),
    ("skip_codes", [CODE, CODE]), ("skip_codes", [" 600519.XSHG"]),
    ("exit_codes", ["半导体"]), ("exit_codes", ["600519.xshg"]), ("exit_codes", CODE),
    ("rationale", " "), ("invalidation_conditions", []), ("invalidation_conditions", [""]),
    ("invalidation_conditions", "condition"), ("source_refs", []), ("current_checks", []),
    ("annotations", {"nested": [float("nan")]}), ("annotations", {1: "ambiguous key"}),
    ("annotations", ("not", "json")),
])
def test_invalid_decisions_are_rejected_before_writes(tmp_path: Path, field: str, value: object) -> None:
    decision = make_decision()
    review = make_review(decision)
    decision[field] = value
    # Rebind when possible so structural rejection is independent of hash drift.
    try:
        review["decision_sha256"] = policy.decision_sha256(decision)
    except policy.KolPolicyError:
        pass
    with pytest.raises(policy.KolPolicyError):
        policy.publish_decision(tmp_path, decision, review, NOW)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("field", list(make_decision()))
def test_every_core_decision_field_is_required(tmp_path: Path, field: str) -> None:
    decision = make_decision()
    del decision[field]
    review = make_review(make_decision())
    review["decision_sha256"] = policy.decision_sha256(decision)
    with pytest.raises(policy.KolPolicyError):
        policy.publish_decision(tmp_path, decision, review, NOW)


@pytest.mark.parametrize("book,runtime", [("T", "live"), ("T", "both"), ("KOL-US", "live"), ("KOL-US", "both")])
def test_only_b_can_publish_live_or_both(tmp_path: Path, book: str, runtime: str) -> None:
    with pytest.raises(policy.KolPolicyError, match="PAPER_ONLY"):
        publish(tmp_path, make_decision(book=book, runtime=runtime))


@pytest.mark.parametrize("book,runtime", [("A", "paper"), ("B", "both"), ("T", "live"), ("KOL-US", "live"), ("B", "unknown")])
def test_invalid_load_scope_blocks(tmp_path: Path, book: str, runtime: str) -> None:
    assert_inert(load(tmp_path, book=book, runtime=runtime), "blocked", 0)


@pytest.mark.parametrize("field", ["report_id", "content_sha256", "author_id", "source_published_at", "received_at"])
def test_source_fields_are_required_without_alias_or_timestamp_fallback(tmp_path: Path, field: str) -> None:
    decision = make_decision()
    del decision["source_refs"][0][field]
    with pytest.raises(policy.KolPolicyError, match="INVALID_SOURCE_FIELDS"):
        publish(tmp_path, decision)


@pytest.mark.parametrize("field,value", [
    ("report_id", ""), ("author_id", ""), ("content_sha256", "no-hash"),
    ("content_sha256", "g" * 64), ("source_published_at", "2026-09-06"),
    ("source_published_at", iso(NOW + timedelta(seconds=1))),
    ("received_at", iso(NOW + timedelta(seconds=1))),
    ("received_at", iso(NOW - timedelta(days=3))),
    ("hash_verified", True), ("source_verified", True), ("confidence", 1),
    ("source_author", "unverified-attribution"),
])
def test_source_time_identity_and_unverified_claims_are_rejected(tmp_path: Path, field: str, value: object) -> None:
    decision = make_decision()
    decision["source_refs"][0][field] = value
    with pytest.raises(policy.KolPolicyError):
        publish(tmp_path, decision)


def test_distinct_source_times_and_old_context_are_preserved_without_research_pass(tmp_path: Path) -> None:
    decision = make_decision()
    publish(tmp_path, decision)
    source = load(tmp_path)["record"]["decision"]["source_refs"][0]
    assert source["source_published_at"] != source["received_at"]
    assert source == decision["source_refs"][0]
    assert "research_verdict" not in decision


def test_source_author_is_bound_to_review_but_local_hash_is_not_remote_verification(tmp_path: Path) -> None:
    decision = make_decision()
    review = make_review(decision)
    decision["source_refs"][0]["author_id"] = "misattributed-author"
    with pytest.raises(policy.KolPolicyError, match="REVIEW_HASH_MISMATCH"):
        policy.publish_decision(tmp_path, decision, review, NOW)
    # A fully rebound review can assert false facts. Remote report readback is
    # deliberately the CLI's responsibility, not a fabricated proof here.
    publish(tmp_path, decision)
    assert "source_verified" not in load(tmp_path)


@pytest.mark.parametrize("field,value", [
    ("claim", ""), ("evidence_ref", ""), ("verdict", "unknown"), ("verdict", "uncertain"),
    ("observed_at", iso(NOW + timedelta(microseconds=1))),
    ("observed_at", iso(NOW - timedelta(minutes=15, microseconds=1))),
    ("material", "false"), ("resolved", 1), ("resolved", True),
])
def test_current_checks_require_fresh_non_uncertain_support(tmp_path: Path, field: str, value: object) -> None:
    decision = make_decision()
    decision["current_checks"][0][field] = value
    with pytest.raises(policy.KolPolicyError):
        publish(tmp_path, decision)


def test_check_freshness_and_lifetime_boundaries_are_inclusive(tmp_path: Path) -> None:
    decision = make_decision()
    decision["current_checks"][0]["observed_at"] = iso(NOW - timedelta(minutes=15))
    decision["valid_until"] = iso(NOW + timedelta(hours=24))
    publish(tmp_path, decision)
    assert load(tmp_path)["status"] == "validated"
    assert_inert(load(tmp_path, NOW + timedelta(microseconds=1)), "needs_refresh", 1)
    assert_inert(load(tmp_path, NOW + timedelta(hours=23)), "needs_refresh", 1)
    assert_inert(load(tmp_path, NOW + timedelta(hours=24)), "expired", 1)


def test_every_current_check_must_stay_fresh_at_consumption(tmp_path: Path) -> None:
    decision = make_decision()
    decision.update(buy_scale=0, skip_codes=[CODE], exit_codes=[CODE])
    decision["valid_until"] = iso(NOW + timedelta(hours=24))
    decision["current_checks"][0]["observed_at"] = iso(NOW)
    decision["current_checks"].append({
        **decision["current_checks"][0], "observed_at": iso(NOW - timedelta(minutes=14)),
        "claim": "Older contextual fact also needs to remain current.", "verdict": "uncertain",
    })
    publish(tmp_path, decision)
    boundary = load(tmp_path, NOW + timedelta(minutes=1))
    assert boundary["status"] == "validated"
    assert policy.exit_adjustment(boundary, CODE)["triggered"] is True
    stale = load(tmp_path, NOW + timedelta(minutes=1, microseconds=1))
    assert_inert(stale, "needs_refresh", 1)
    assert stale["decision_id"] == "decision-1"
    assert stale["reason"] == "KOL_POLICY_NEEDS_REFRESH"
    assert_inert(load(tmp_path, NOW + timedelta(hours=1)), "needs_refresh", 1)


def test_refresh_requires_new_reviewed_judgment_and_does_not_mutate_old_one(tmp_path: Path) -> None:
    original = make_decision(scale=0)
    original["exit_codes"] = [CODE]
    receipt = publish(tmp_path, original)
    original_bytes = (tmp_path / "decision-1.json").read_bytes()
    later = NOW + timedelta(minutes=16)
    assert_inert(load(tmp_path, later), "needs_refresh", 1)
    assert publish(tmp_path, original, later) == receipt
    assert_inert(load(tmp_path, later), "needs_refresh", 1)
    refreshed = make_decision("reassessed-2", as_of=later, scale=0.3)
    publish(tmp_path, refreshed, later)
    snapshot = load(tmp_path, later)
    assert snapshot["status"] == "validated"
    assert snapshot["decision_id"] == "reassessed-2"
    assert policy.buy_adjustment(snapshot, CODE)["scale"] == 0.3
    assert policy.exit_adjustment(snapshot, CODE)["triggered"] is False
    assert (tmp_path / "decision-1.json").read_bytes() == original_bytes


@pytest.mark.parametrize("runtime", ["live", "both"])
@pytest.mark.parametrize("resolution", [{}, {"resolved": True}, {"resolved": True, "resolution_reason": " "},
                                       {"resolution_reason": "Explanation without resolved flag"}])
def test_live_material_contradictions_require_explicit_resolution(tmp_path: Path, runtime: str, resolution: dict) -> None:
    decision = make_decision(runtime=runtime)
    decision["current_checks"].append({**decision["current_checks"][0], "verdict": "contradicts", **resolution})
    with pytest.raises(policy.KolPolicyError, match="RESOLUTION|CONTRADICTION"):
        publish(tmp_path, decision)


@pytest.mark.parametrize("runtime,resolution", [
    ("live", {"material": True, "resolved": True, "resolution_reason": "Independent review explains current applicability."}),
    ("live", {"material": False}), ("paper", {}),
])
def test_reviewed_resolution_or_explicit_non_material_or_paper_is_accepted(tmp_path: Path, runtime: str, resolution: dict) -> None:
    decision = make_decision(runtime=runtime)
    decision["current_checks"].append({**decision["current_checks"][0], "verdict": "contradicts", **resolution})
    publish(tmp_path, decision)
    assert load(tmp_path, runtime=runtime)["status"] == "validated"


@pytest.mark.parametrize("review", [None, {}, [], {"status": "approved"}])
def test_missing_or_incomplete_review_is_rejected(tmp_path: Path, review: object) -> None:
    with pytest.raises(policy.KolPolicyError):
        policy.publish_decision(tmp_path, make_decision(), review, NOW)


@pytest.mark.parametrize("field,value", [
    ("status", "rejected"), ("decision_sha256", "0" * 64),
    ("reviewer_agent_id", "full-source-reader"), ("reviewer_agent_id", ""),
    ("coverage_complete", False), ("coverage_complete", 1), ("source_fidelity", False),
    ("applicability_checked", False), ("counterevidence_checked", False),
    ("reviewed_at", iso(NOW - timedelta(seconds=1))), ("reviewed_at", iso(NOW + timedelta(seconds=1))),
    ("reviewed_at", iso(NOW + timedelta(hours=2))), ("confidence", float("nan")),
])
def test_review_independence_completeness_clock_and_finite_values(tmp_path: Path, field: str, value: object) -> None:
    decision = make_decision()
    with pytest.raises(policy.KolPolicyError):
        policy.publish_decision(tmp_path, decision, make_review(decision, **{field: value}), NOW)


@pytest.mark.parametrize("field", list(make_review(make_decision())))
def test_every_review_field_is_required(tmp_path: Path, field: str) -> None:
    decision = make_decision()
    review = make_review(decision)
    del review[field]
    with pytest.raises(policy.KolPolicyError):
        policy.publish_decision(tmp_path, decision, review, NOW)


def test_canonical_hash_covers_annotations_and_all_decision_fields(tmp_path: Path) -> None:
    decision = make_decision()
    decision["annotations"] = {"多源阅读": ["小草", "环境作者"], "score": 0.123}
    expected = hashlib.sha256(json.dumps(decision, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert policy.decision_sha256(decision) == expected
    review = make_review(decision)
    decision["annotations"]["score"] = 0.124
    with pytest.raises(policy.KolPolicyError, match="REVIEW_HASH_MISMATCH"):
        policy.publish_decision(tmp_path, decision, review, NOW)


def test_publish_rejects_future_expired_and_naive_clocks(tmp_path: Path) -> None:
    with pytest.raises(policy.KolPolicyError, match="FUTURE"):
        publish(tmp_path, make_decision(as_of=NOW + timedelta(seconds=1)))
    with pytest.raises(policy.KolPolicyError, match="EXPIRED"):
        publish(tmp_path, make_decision(), NOW + timedelta(hours=2))
    with pytest.raises(policy.KolPolicyError, match="AWARE_CLOCK"):
        publish(tmp_path, make_decision(), NOW.replace(tzinfo=None))
    assert_inert(load(tmp_path, NOW.replace(tzinfo=None)), "blocked", 0)


def test_aware_local_clock_and_explicit_utc_z_are_accepted(tmp_path: Path) -> None:
    decision = make_decision()
    decision["as_of"] = decision["as_of"].replace("+00:00", "Z")
    publish(tmp_path, decision, NOW.astimezone(timezone(timedelta(hours=8))))
    assert load(tmp_path)["status"] == "validated"


@pytest.mark.parametrize("damage", ["json", "decision", "review", "receipt", "missing_review", "nan", "duplicates", "filename"])
def test_store_corruption_never_issues_an_exit_or_neutralizes_buy_block(tmp_path: Path, damage: str) -> None:
    decision = make_decision()
    decision["exit_codes"] = [CODE]
    publish(tmp_path, decision)
    path = tmp_path / "decision-1.json"
    record = json.loads(path.read_text())
    if damage == "json":
        path.write_text("{")
    elif damage == "duplicates":
        path.write_text('{"schema_version":"bad",' + path.read_text()[1:])
    elif damage == "filename":
        path.rename(tmp_path / "wrong.json")
    else:
        if damage == "decision":
            record["decision"]["buy_scale"] = 1
        elif damage == "review":
            record["review"]["source_fidelity"] = False
        elif damage == "receipt":
            record["receipt"]["published_at"] = iso(NOW - timedelta(days=1))
        elif damage == "nan":
            record["decision"]["buy_scale"] = float("nan")
        elif damage == "missing_review":
            del record["review"]
        path.write_text(json.dumps(record))
    assert_inert(load(tmp_path), "blocked", 0)
    assert_inert(load(tmp_path, NOW + timedelta(days=1)), "blocked", 0)
    with pytest.raises(policy.KolPolicyError):
        publish(tmp_path, make_decision("new"))


def test_malformed_unscoped_file_conservatively_blocks_store(tmp_path: Path) -> None:
    publish(tmp_path, make_decision())
    (tmp_path / "unidentifiable.json").write_text("[]")
    assert_inert(load(tmp_path), "blocked", 0)
    assert_inert(load(tmp_path, book="T", runtime="paper"), "blocked", 0)


@pytest.mark.parametrize("step", ["file_fsync", "link", "directory_fsync", "pending_unlink"])
def test_audit_failure_rejects_publication_and_blocks_consumption(tmp_path: Path, monkeypatch, step: str) -> None:
    real_fsync = policy.os.fsync
    calls = 0

    def fail_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == (1 if step == "file_fsync" else 2):
            raise OSError("injected audit failure")
        real_fsync(fd)

    def fail(*args, **kwargs):
        raise OSError("injected audit failure")

    if step in ("file_fsync", "directory_fsync"):
        monkeypatch.setattr(policy.os, "fsync", fail_fsync)
    elif step == "link":
        monkeypatch.setattr(policy.os, "link", fail)
    else:
        monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(policy.KolPolicyError, match="PUBLICATION_FAILED"):
        publish(tmp_path, make_decision())
    assert_inert(load(tmp_path), "blocked", 0)


def test_store_io_failure_blocks_load_and_rejects_publish(tmp_path: Path, monkeypatch) -> None:
    publish(tmp_path, make_decision())

    def fail(*args, **kwargs):
        raise PermissionError("no access")

    monkeypatch.setattr(policy.os, "open", fail)
    assert_inert(load(tmp_path), "blocked", 0)
    with pytest.raises(policy.KolPolicyError, match="PUBLICATION_FAILED"):
        publish(tmp_path, make_decision("second"))


def test_new_store_ancestors_are_synced_before_publication(tmp_path: Path, monkeypatch) -> None:
    real_sync = policy._sync_directory
    synced = []

    def track(directory: Path) -> None:
        synced.append(directory)
        real_sync(directory)

    monkeypatch.setattr(policy, "_sync_directory", track)
    store = tmp_path / "new-parent" / "decisions"
    publish(store, make_decision())
    assert synced == [tmp_path, store.parent, store]
    assert load(store)["status"] == "validated"


def test_new_store_parent_sync_failure_rejects_before_record_write(tmp_path: Path, monkeypatch) -> None:
    def fail(directory: Path) -> None:
        raise OSError("parent entry not durable")

    monkeypatch.setattr(policy, "_sync_directory", fail)
    store = tmp_path / "new-store"
    with pytest.raises(policy.KolPolicyError, match="PUBLICATION_FAILED"):
        publish(store, make_decision())
    assert not list(store.glob("*.json"))


@pytest.mark.parametrize("target", ["store", "lock", "record"])
def test_symlink_store_entries_fail_closed(tmp_path: Path, target: str) -> None:
    store = tmp_path / "store"
    publish(store, make_decision())
    if target == "store":
        alias = tmp_path / "alias"
        alias.symlink_to(store, target_is_directory=True)
        store = alias
    else:
        name = ".lock" if target == "lock" else "decision-1.json"
        path = store / name
        outside = tmp_path / "outside"
        path.rename(outside)
        path.symlink_to(outside)
    assert_inert(load(store), "blocked", 0)


@pytest.mark.parametrize("field,value", [
    ("buy_scale", 2), ("buy_scale", float("nan")), ("skip_codes", [CODE]),
    ("exit_codes", [CODE]), ("book", "T"), ("runtime", "paper"), ("decision_id", "forged"),
])
def test_mutated_consumption_snapshot_is_blocked(tmp_path: Path, field: str, value: object) -> None:
    publish(tmp_path, make_decision())
    snapshot = load(tmp_path)
    snapshot[field] = value
    assert policy.buy_adjustment(snapshot, CODE)["scale"] == 0
    assert policy.exit_adjustment(snapshot, CODE)["triggered"] is False


@pytest.mark.parametrize("snapshot", [None, {}, {"status": "validated"}, {"status": "unknown"}, {"buy_scale": 2}])
def test_raw_or_incomplete_snapshots_cannot_be_consumed(snapshot: object) -> None:
    assert policy.buy_adjustment(snapshot, CODE)["scale"] == 0
    assert policy.exit_adjustment(snapshot, CODE)["triggered"] is False


def test_neutral_and_blocked_snapshots_ignore_stale_exit_payloads() -> None:
    for status, scale in [("neutral", 1), ("expired", 1), ("needs_refresh", 1), ("no_decision", 1), ("blocked", 0)]:
        snapshot = {"status": status, "buy_scale": 0.2, "exit_codes": [CODE]}
        assert policy.buy_adjustment(snapshot, CODE)["scale"] == scale
        assert policy.exit_adjustment(snapshot, CODE)["triggered"] is False


def _concurrent_publish(root: str, identifier: str) -> dict:
    return publish(Path(root), make_decision(identifier))


@pytest.mark.parametrize("same_id", [True, False])
def test_process_writers_are_serialized_and_idempotent(tmp_path: Path, same_id: bool) -> None:
    ids = ["same"] * 6 if same_id else [f"decision-{index}" for index in range(6)]
    with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context("spawn")) as pool:
        receipts = list(pool.map(_concurrent_publish, [str(tmp_path)] * len(ids), ids))
    assert len(list(tmp_path.glob("*.json"))) == (1 if same_id else 6)
    if same_id:
        assert all(receipt == receipts[0] for receipt in receipts)
    assert load(tmp_path)["decision_id"] == ("same" if same_id else "decision-5")
