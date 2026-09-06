from __future__ import annotations

import fcntl
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from xiaocao.live import kol_policy


spec = importlib.util.spec_from_file_location("kol_trading_tick", Path(__file__).resolve().parents[1] / "scripts/kol_trading_tick.py")
tick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tick)
NOW = datetime.fromisoformat("2026-09-07T10:00:00+08:00")


def at(hhmm, day="2026-09-07"):
    return datetime.fromisoformat(f"{day}T{hhmm}:00+08:00")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def publication(root, identifier="report-1", event="publication_receipt", state="published", relative=None, when=None):
    path = root / (relative or tick.PRODUCTION_LEDGER_PATHS[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"schema_version": 1, "publication_key": identifier, "event": event,
           "occurred_at": (when or NOW - timedelta(minutes=1)).isoformat(),
           "receipt": {"recordState": state, "recordId": identifier,
                       "contentSha256": "a" * 64, "manifestSha256": "b" * 64}}
    row["event_id"] = tick._digest(row)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    return path


def positions(root, **changes):
    row = {"book": "B", "code": "600519.XSHG", "shares": 100, "exit_date": None, "exit_price": None, **changes}
    path = root / "output/live/positions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def policy(root, *, runtime="paper", identifier="decision-1", when=NOW):
    when = when.astimezone(tick.timezone.utc)
    decision = {
        "schema_version": "kol-trading-decision.v1", "decision_id": identifier,
        "agent_id": "reader", "book": "B", "runtime": runtime,
        "as_of": when.isoformat(), "valid_until": (when + timedelta(hours=2)).isoformat(),
        "source_refs": [{"report_id": "report-1", "content_sha256": "a" * 64, "author_id": "xiaocao",
                         "source_published_at": (when - timedelta(hours=1)).isoformat(),
                         "received_at": (when - timedelta(minutes=1)).isoformat()}],
        "buy_scale": 1.0, "skip_codes": [], "exit_codes": [], "rationale": "Reviewed context.",
        "invalidation_conditions": ["Reassess current evidence."],
        "current_checks": [{"claim": "Bounded current fact.", "observed_at": when.isoformat(),
                            "evidence_ref": "fixture:current", "verdict": "supports"}],
    }
    review = {"decision_sha256": kol_policy.decision_sha256(decision), "status": "approved",
              "reviewer_agent_id": "reviewer", "reviewed_at": when.isoformat(),
              "coverage_complete": True, "source_fidelity": True, "applicability_checked": True,
              "counterevidence_checked": True}
    # Assemble the already-published local fixture; never invoke a business writer.
    receipt = {"status": "published", "decision_id": identifier,
               "decision_sha256": kol_policy.decision_sha256(decision),
               "review_sha256": kol_policy.decision_sha256(review), "book": "B", "runtime": runtime,
               "published_at": when.isoformat()}
    record = {"schema_version": "kol-trading-decision-record.v1", "decision": decision,
              "review": review, "receipt": receipt}
    record["record_sha256"] = kol_policy.decision_sha256(record)
    store = root / "output/live/kol_policy/decisions"
    write_json(store / f"{identifier}.json", record)
    (store / ".lock").touch()
    return store


def finish(root, claim, outcome="completed", now=NOW):
    return tick.ack(root, token=claim["token"], outcome=outcome, now=now)


@pytest.mark.parametrize("hhmm", ["10:25", "10:55", "13:25", "13:55"])
def test_original_sparse_slots_always_request_regular_monitor(tmp_path, hhmm):
    claim = tick.poll(tmp_path, now=at(hhmm))
    assert claim["status"] == "run"
    assert claim["regular_monitor"] and not claim["need_semantic_review"]
    assert finish(tmp_path, claim, now=at(hhmm))["status"] == "no_op"
    assert tick.poll(tmp_path, now=at(hhmm))["status"] == "no_op"


@pytest.mark.parametrize("hhmm", ["09:40", "11:25", "13:00", "14:50"])
def test_candidate_session_boundaries_do_not_prove_open_exchange(tmp_path, hhmm):
    publication(tmp_path)
    # The gate does no exchange/holiday-calendar query; consumer owns that gate.
    claim = tick.poll(tmp_path, now=at(hhmm, "2026-09-08"))
    assert claim["status"] == "run" and claim["need_semantic_review"]
    assert not claim["regular_monitor"]


@pytest.mark.parametrize("hhmm,day", [("09:29", "2026-09-07"), ("09:30", "2026-09-07"),
    ("11:30", "2026-09-07"), ("11:31", "2026-09-07"),
    ("12:30", "2026-09-07"), ("14:51", "2026-09-07"), ("14:55", "2026-09-07"),
    ("10:25", "2026-09-05"), ("10:25", "2026-09-06")])
def test_outside_candidates_never_reads_production_inputs(tmp_path, monkeypatch, hhmm, day):
    monkeypatch.setattr(tick, "publication_fingerprint", lambda *a: pytest.fail("out-of-window read"))
    assert tick.poll(tmp_path, now=at(hhmm, day))["status"] == "no_op"


def test_empty_extra_tick_is_local_no_op_and_creates_no_claim(tmp_path):
    result = tick.poll(tmp_path, now=NOW)
    assert result["status"] == "no_op"
    assert not result["need_semantic_review"] and not result["regular_monitor"]
    assert not (tmp_path / tick.STATE_RELATIVE_PATH / "state.json").exists()


def test_raw_prepared_and_test_registry_never_trigger_semantic_work(tmp_path):
    publication(tmp_path, event="publication_prepared")
    publication(tmp_path, state="draft")
    publication(tmp_path, relative="output/live/test_registry/publications/events.jsonl")
    publication(tmp_path, relative="output/live/kol_daily/captures/events.jsonl")
    assert tick.poll(tmp_path, now=NOW)["status"] == "no_op"


@pytest.mark.parametrize("outcome", ["completed", "degraded"])
def test_publication_cursor_advances_only_on_matching_terminal_ack(tmp_path, outcome):
    publication(tmp_path)
    claim = tick.poll(tmp_path, now=NOW)
    assert claim["status"] == "run"
    assert finish(tmp_path, {"token": "f" * 64})["status"] == "reconcile_required"
    assert tick.poll(tmp_path, now=NOW + timedelta(days=100))["token"] == claim["token"]
    assert finish(tmp_path, claim, outcome)["status"] == "no_op"
    assert finish(tmp_path, claim, outcome)["reason"] == "ALREADY_ACKNOWLEDGED"
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=5))["status"] == "no_op"


def test_ack_binds_claimed_fingerprint_not_newer_publications(tmp_path):
    publication(tmp_path)
    first = tick.poll(tmp_path, now=NOW)
    publication(tmp_path, "report-2")
    finish(tmp_path, first)
    second = tick.poll(tmp_path, now=NOW + timedelta(minutes=5))
    assert second["status"] == "run"
    assert second["fingerprint"] != first["fingerprint"]
    assert finish(tmp_path, first)["reason"] == "ALREADY_ACKNOWLEDGED"
    assert tick.poll(tmp_path, now=NOW)["token"] == second["token"]


def test_stale_policy_requires_same_runtime_explicit_open_positions_and_ack(tmp_path):
    policy(tmp_path)
    finish(tmp_path, tick.poll(tmp_path, now=NOW))
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=20))["status"] == "no_op"
    positions(tmp_path)
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=15))["status"] == "no_op"
    claim = tick.poll(tmp_path, now=NOW + timedelta(minutes=20))
    assert claim["status"] == "run" and claim["need_semantic_review"]
    assert not claim["regular_monitor"]
    finish(tmp_path, claim, "degraded", NOW + timedelta(minutes=20))
    regular = tick.poll(tmp_path, now=NOW + timedelta(minutes=25))
    assert regular["regular_monitor"] and not regular["need_semantic_review"]


@pytest.mark.parametrize("changes", [{"book": "T"}, {"book": None}, {"shares": 0},
    {"exit_date": "2026-09-07"}, {"exit_price": 10}, {"shares": float("nan")}])
def test_non_open_or_non_b_positions_do_not_wake_stale_review(tmp_path, changes):
    policy(tmp_path)
    finish(tmp_path, tick.poll(tmp_path, now=NOW))
    positions(tmp_path, **changes)
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=20))["status"] == "no_op"


def test_paper_positions_do_not_wake_live_only_decision(tmp_path):
    policy(tmp_path, runtime="live")
    finish(tmp_path, tick.poll(tmp_path, now=NOW))
    positions(tmp_path)
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=20))["status"] == "no_op"


def test_nonblocking_claim_fence_allows_only_one_dispatch(tmp_path):
    publication(tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: tick.poll(tmp_path, now=NOW), range(6)))
    assert sum(row["status"] == "run" for row in results) == 1
    assert all(row["status"] in ("run", "reconcile_required") for row in results)


def test_held_policy_writer_is_nonblocking(tmp_path):
    store = policy(tmp_path)
    positions(tmp_path)
    with (store / ".lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert tick.poll(tmp_path, now=NOW + timedelta(minutes=20))["status"] == "reconcile_required"


def test_reconcile_requires_explicit_exact_terminal_confirmation(tmp_path):
    publication(tmp_path)
    claim = tick.poll(tmp_path, now=NOW)
    assert tick.reconcile(tmp_path, token=claim["token"], outcome="completed", confirmed_by="timer",
                          evidence_ref="TTL expired", now=NOW)["status"] == "reconcile_required"
    assert tick.reconcile(tmp_path, token=claim["token"], outcome="completed", confirmed_by="root",
                          evidence_ref="", now=NOW)["status"] == "reconcile_required"
    assert tick.reconcile(tmp_path, token=claim["token"], outcome="degraded", confirmed_by="user",
                          evidence_ref="reviewed-terminal-receipt:123", now=NOW)["status"] == "no_op"
    state = json.loads((tmp_path / tick.STATE_RELATIVE_PATH / "state.json").read_text())
    assert state["last_ack"]["confirmation"]["confirmed_by"] == "user"


def test_tampered_claim_cannot_be_acknowledged_even_if_outer_hash_recomputed(tmp_path):
    publication(tmp_path)
    claim = tick.poll(tmp_path, now=NOW)
    path = tmp_path / tick.STATE_RELATIVE_PATH / "state.json"
    state = json.loads(path.read_text())
    state.pop("state_sha256")
    state["claim"]["cadence_slot"] = "2026-09-07T13:00:00+08:00"
    write_json(path, {**state, "state_sha256": tick._digest(state)})
    assert finish(tmp_path, claim)["status"] == "reconcile_required"


def test_cli_compact_json_and_test_clock_scope(tmp_path, capsys):
    assert tick.main(["poll", "--root", str(tmp_path), "--now", NOW.isoformat()]) == 0
    output = capsys.readouterr().out
    assert output.count("\n") == 1 and json.loads(output)["status"] == "no_op"
    assert tick.main(["poll", "--now", NOW.isoformat()]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "reconcile_required"
    assert tick.main(["poll", "--root", str(tmp_path), "--now", "2026-09-07T10:00:00"]) == 2


def test_sparse_monitor_and_publication_review_share_one_claim(tmp_path):
    publication(tmp_path)
    claim = tick.poll(tmp_path, now=at("10:25"))
    assert claim["status"] == "run"
    assert claim["regular_monitor"] and claim["need_semantic_review"]
    state = json.loads((tmp_path / tick.STATE_RELATIVE_PATH / "state.json").read_text())
    persisted = dict(state["claim"])
    token = persisted.pop("token")
    assert token == claim["token"] == tick._digest(persisted)


def test_claim_commit_followed_by_crash_is_not_replayed(tmp_path, monkeypatch):
    publication(tmp_path)
    save = tick._save

    def save_then_crash(*args):
        save(*args)
        raise OSError("injected crash after durable claim")

    monkeypatch.setattr(tick, "_save", save_then_crash)
    assert tick.poll(tmp_path, now=NOW)["status"] == "reconcile_required"
    monkeypatch.setattr(tick, "_save", save)
    result = tick.poll(tmp_path, now=NOW + timedelta(days=90))
    assert result["reason"] == "RUNNING_CLAIM"
    assert result["token"]


def test_pending_state_commit_never_creates_another_claim(tmp_path):
    publication(tmp_path)
    directory = tmp_path / tick.STATE_RELATIVE_PATH
    directory.mkdir(parents=True)
    (directory / ".pending-crash").write_text("partial")
    assert tick.poll(tmp_path, now=NOW)["status"] == "reconcile_required"
    assert not (directory / "state.json").exists()


def test_nonterminal_or_conflicting_ack_does_not_advance_cursor(tmp_path):
    publication(tmp_path)
    claim = tick.poll(tmp_path, now=NOW)
    path = tmp_path / tick.STATE_RELATIVE_PATH / "state.json"
    before = path.read_bytes()
    for outcome in ("running", "dispatched", "failed", "unknown"):
        assert finish(tmp_path, claim, outcome)["status"] == "reconcile_required"
        assert path.read_bytes() == before
    finish(tmp_path, claim)
    before = path.read_bytes()
    assert finish(tmp_path, claim, "degraded")["status"] == "reconcile_required"
    assert path.read_bytes() == before


def test_prepared_append_after_ack_does_not_change_publication_cursor(tmp_path):
    publication(tmp_path)
    finish(tmp_path, tick.poll(tmp_path, now=NOW))
    publication(tmp_path, "raw-new-item", event="publication_prepared")
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=5))["status"] == "no_op"


def test_corrupt_ledger_fails_closed_without_a_work_claim(tmp_path):
    path = publication(tmp_path)
    path.write_text(path.read_text().replace('"published"', '"superseded"'))
    assert tick.poll(tmp_path, now=NOW)["status"] == "reconcile_required"
    assert not (tmp_path / tick.STATE_RELATIVE_PATH / "state.json").exists()


def live_positions(root, closed=False):
    rows = []
    for index, side in enumerate(["BUY", "SELL"] if closed else ["BUY"]):
        row = {"evidence_kind": "book_b_ownership", "kind": "fill_observed", "book": "B",
               "environment": "live", "logical_account_id": "primary", "code": "600519.XSHG",
               "side": side, "shares": 100, "fill_price": 10, "plan_id": f"plan-{index}",
               "plan_hash": "a" * 64, "cumulative_filled_shares": 100,
               "fill_notional": 1_000, "cumulative_fill_notional": 1_000,
               "source_execution_event_id": f"execution-{index}",
               "previous_hash": rows[-1]["event_hash"] if rows else None}
        row["event_hash"] = tick._digest(row)
        rows.append(row)
    path = root / "output/live/book_b_live_execution/book_b_ownership_evidence.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.mark.parametrize("closed,status", [(False, "run"), (True, "no_op")])
def test_live_owned_open_positions_can_wake_live_policy_without_broker_read(tmp_path, closed, status):
    policy(tmp_path, runtime="live")
    finish(tmp_path, tick.poll(tmp_path, now=NOW))
    live_positions(tmp_path, closed)
    result = tick.poll(tmp_path, now=NOW + timedelta(minutes=20))
    assert result["status"] == status
    assert result["need_semantic_review"] == (not closed)


def test_newer_fresh_decision_does_not_resurrect_old_expired_decision(tmp_path):
    positions(tmp_path)
    policy(tmp_path)
    policy(tmp_path, identifier="decision-2", when=NOW + timedelta(minutes=20))
    result = tick.poll(tmp_path, now=NOW + timedelta(minutes=20))
    assert result["status"] == "run" and result["decision_changed"]
    assert not result["need_semantic_review"]


def test_state_directory_symlink_does_not_write_outside_tick_store(tmp_path):
    other = tmp_path / "unrelated"
    other.mkdir()
    link = tmp_path / tick.STATE_RELATIVE_PATH
    link.parent.mkdir(parents=True)
    link.symlink_to(other, target_is_directory=True)
    assert tick.poll(tmp_path, now=NOW)["status"] == "reconcile_required"
    assert not list(other.iterdir())


@pytest.mark.parametrize("runtime", ["paper", "live", "both"])
def test_new_fresh_decision_wakes_next_tick_without_another_semantic_review(tmp_path, runtime):
    policy(tmp_path, runtime=runtime)
    claim = tick.poll(tmp_path, now=NOW)
    assert claim["status"] == "run" and claim["decision_changed"]
    assert not claim["need_semantic_review"] and not claim["regular_monitor"]
    finish(tmp_path, claim)
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=5))["status"] == "no_op"


def test_review_completed_during_source_claim_is_consumed_by_later_tick(tmp_path):
    publication(tmp_path)
    source_claim = tick.poll(tmp_path, now=NOW)
    assert source_claim["need_semantic_review"] and not source_claim["decision_changed"]
    policy(tmp_path, when=NOW + timedelta(minutes=1))
    finish(tmp_path, source_claim, now=NOW + timedelta(minutes=2))
    # No second monitor within the first claim's cadence slot.
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=3))["status"] == "no_op"
    consumer_claim = tick.poll(tmp_path, now=NOW + timedelta(minutes=5))
    assert consumer_claim["status"] == "run" and consumer_claim["decision_changed"]
    assert consumer_claim["fingerprint"] == source_claim["fingerprint"]
    assert consumer_claim["decision_fingerprint"] != source_claim["decision_fingerprint"]
    assert not consumer_claim["need_semantic_review"]


def test_ack_freezes_both_fingerprints_when_sources_and_decisions_arrive_during_work(tmp_path):
    publication(tmp_path)
    policy(tmp_path)
    first = tick.poll(tmp_path, now=NOW)
    publication(tmp_path, "report-2")
    policy(tmp_path, identifier="decision-2", when=NOW + timedelta(minutes=1))
    finish(tmp_path, first, "degraded", NOW + timedelta(minutes=2))
    state = json.loads((tmp_path / tick.STATE_RELATIVE_PATH / "state.json").read_text())
    assert state["cursor"]["fingerprint"] == first["fingerprint"]
    assert state["cursor"]["decision_fingerprint"] == first["decision_fingerprint"]
    second = tick.poll(tmp_path, now=NOW + timedelta(minutes=5))
    assert second["status"] == "run" and second["decision_changed"] and second["need_semantic_review"]
    assert second["fingerprint"] != first["fingerprint"]
    assert second["decision_fingerprint"] != first["decision_fingerprint"]
    finish(tmp_path, second, now=NOW + timedelta(minutes=5))
    assert tick.poll(tmp_path, now=NOW + timedelta(minutes=10))["status"] == "no_op"


@pytest.mark.parametrize("hhmm", ["09:35", "09:39", "09:45", "09:49", "09:55", "09:59",
                                  "14:25", "14:29", "14:55", "14:59"])
def test_reserved_owned_slots_never_read_sources_or_decisions(tmp_path, monkeypatch, hhmm):
    monkeypatch.setattr(tick, "publication_fingerprint", lambda *a: pytest.fail("reserved source read"))
    monkeypatch.setattr(tick, "_decision_inputs", lambda *a: pytest.fail("reserved decision read"))
    result = tick.poll(tmp_path, now=at(hhmm))
    assert (result["status"], result["reason"]) == ("no_op", "RESERVED_OWNED_SLOT")
    assert not result["regular_monitor"] and not result["need_semantic_review"]
    assert not (tmp_path / tick.STATE_RELATIVE_PATH / "state.json").exists()


def test_0930_source_and_decision_changes_wait_for_0940_without_ack(tmp_path):
    publication(tmp_path, when=at("09:29"))
    policy(tmp_path, when=at("09:29"))
    for clock in ("09:30", "09:34", "09:35", "09:39"):
        assert tick.poll(tmp_path, now=at(clock))["status"] == "no_op"
        assert not (tmp_path / tick.STATE_RELATIVE_PATH / "state.json").exists()
    claim = tick.poll(tmp_path, now=at("09:40"))
    assert claim["status"] == "run" and claim["decision_changed"] and claim["need_semantic_review"]


def test_precheck_reserved_slot_preserves_both_acknowledged_cursors(tmp_path):
    publication(tmp_path)
    policy(tmp_path)
    finish(tmp_path, tick.poll(tmp_path, now=NOW))
    publication(tmp_path, "report-2", when=at("14:24"))
    policy(tmp_path, identifier="decision-2", when=at("14:24"))
    path = tmp_path / tick.STATE_RELATIVE_PATH / "state.json"
    before = path.read_bytes()
    assert tick.poll(tmp_path, now=at("14:25"))["reason"] == "RESERVED_OWNED_SLOT"
    assert path.read_bytes() == before
    claim = tick.poll(tmp_path, now=at("14:30"))
    assert claim["status"] == "run" and claim["decision_changed"] and claim["need_semantic_review"]


def test_1130_defers_work_until_afternoon_without_consuming_source(tmp_path):
    publication(tmp_path)
    assert tick.poll(tmp_path, now=at("11:30"))["status"] == "no_op"
    assert not (tmp_path / tick.STATE_RELATIVE_PATH / "state.json").exists()
    assert tick.poll(tmp_path, now=at("13:00"))["status"] == "run"


@pytest.mark.parametrize("hhmm", ["09:30", "09:35", "09:45", "09:55", "11:30", "14:25", "14:55"])
def test_existing_tick_claim_is_never_hidden_by_reserved_or_window_noop(tmp_path, hhmm):
    publication(tmp_path, when=at("09:29"))
    claim = tick.poll(tmp_path, now=at("09:40"))
    result = tick.poll(tmp_path, now=at(hhmm, "2026-09-08"))
    assert result["status"] == "reconcile_required" and result["token"] == claim["token"]


@pytest.mark.parametrize("kind", ["checkpoint", "account"])
def test_existing_live_writer_gets_priority_without_consuming_changes(tmp_path, kind):
    publication(tmp_path, when=at("09:29"))
    state_root = tmp_path / "output/live/book_b_live_execution"
    account = tick.hashlib.sha256(b"primary").hexdigest()[:24]
    path = (state_root / "book_b_live_checkpoint.lock" if kind == "checkpoint"
            else state_root / "account_writer_locks" / f"account-{account}.lock")
    path.parent.mkdir(parents=True)
    with path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = tick.poll(tmp_path, now=at("09:40"))
        assert (result["status"], result["reason"]) == ("no_op", "LIVE_WRITER_OWNS_CHECKPOINT")
        assert not (tmp_path / tick.STATE_RELATIVE_PATH / "state.json").exists()
    assert tick.poll(tmp_path, now=at("09:50"))["status"] == "run"


def test_unresolved_morning_plan_does_not_start_a_tick_writer_after_time_passes(tmp_path):
    publication(tmp_path)
    path = tmp_path / "output/live/book_b_live_execution/events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"plan_id": "book-b:morning:BUY", "state": "claimed"}) + "\n")
    for now in (NOW, NOW + timedelta(days=1)):
        result = tick.poll(tmp_path, now=now)
        assert (result["status"], result["reason"]) == ("reconcile_required", "EXISTING_LIVE_PLAN_REQUIRES_OWNER")
    assert not (tmp_path / tick.STATE_RELATIVE_PATH / "state.json").exists()
