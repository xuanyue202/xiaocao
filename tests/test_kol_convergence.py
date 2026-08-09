from datetime import datetime, timedelta, timezone

import pytest

from xiaocao.kol.writer_progress import (
    ConvergenceLedger,
    ProgressContractError,
    RolloutReadback,
    build_convergence_report,
    build_stability_acceptance_report,
)


REVISION = "a" * 40
FINGERPRINT = "b" * 64


def _rollout_readback() -> dict:
    return RolloutReadback(
        automation_id="automation-1",
        writer_task_id="task-1",
        target_revision=REVISION,
        active_writer_count=1,
        duplicate_automation_count=0,
        automation_owner="automation-1",
        automation_readback=True,
        worktree_protected=True,
        dependencies_ready=True,
        private_config_ready=True,
        restored_state_ready=True,
    ).to_dict()


def _stable_window_events() -> tuple[list[dict], list[dict]]:
    start = datetime.fromisoformat("2026-08-01T07:00:00+08:00")
    daily = []
    for day in range(5):
        for hour in range(6):
            daily.append({
                "event": "sweep_completed",
                "slot": (start + timedelta(days=day, hours=hour)).isoformat(
                    timespec="seconds"
                ),
                "health": "healthy",
                "sweep_elapsed_ms": 120_000,
                "source_states": [{"name": "lv", "status": "no_update"}],
                "coordinator_source_video_bytes": 0,
            })
    for day in range(5, 8):
        for hour in range(7, 14):
            daily.append({
                "event": "sweep_completed",
                "slot": datetime(
                    2026, 8, day + 1, hour, tzinfo=timezone(timedelta(hours=8))
                ).isoformat(timespec="seconds"),
                "health": "healthy",
                "sweep_elapsed_ms": 120_000,
                "source_states": [{"name": "lv", "status": "no_update"}],
                "coordinator_source_video_bytes": 0,
            })
    convergence = [
        {
            "event": "rollout_readback",
            "slot": start.isoformat(timespec="seconds"),
            "stability_window_start": start.isoformat(timespec="seconds"),
            "readback": _rollout_readback(),
            "baseline": {"failure_fingerprints": 0},
        },
    ]
    convergence.extend({
        "event": "peer_gate_observed",
        "slot": (start + timedelta(hours=index)).isoformat(
            timespec="seconds"
        ),
        "elapsed_ms": 1_000 if index < 18 else 2_000,
    } for index in range(20))
    convergence.extend({
        "event": "duplicate_effect_audit",
        "slot": row["slot"],
        "duplicate_count": 0,
    } for row in daily)
    return daily, convergence


def test_stability_acceptance_waits_for_authoritative_rollout_before_observing():
    report = build_stability_acceptance_report(
        [],
        [],
        as_of="2026-08-09T12:00:00+08:00",
    )

    assert report["status"] == "pending_observation"
    assert report["rollout"]["status"] == "not_recorded"
    assert report["window"]["scheduled_slots"] == 0
    assert report["blockers"] == [{
        "code": "rollout_readback_missing",
        "owner": "agent",
    }]


def test_stability_acceptance_requires_all_hard_gates_before_passing():
    daily, convergence = _stable_window_events()

    report = build_stability_acceptance_report(
        daily,
        convergence,
        as_of="2026-08-08T23:00:00+08:00",
    )

    assert report["status"] == "passed"
    assert report["window"] == {
        "start": "2026-08-01T07:00:00+08:00",
        "as_of": "2026-08-08T23:00:00+08:00",
        "elapsed_days": 7.6666666667,
        "scheduled_slots": 51,
        "observed_days": 8,
        "missing_observation_dates": [],
        "required_days": 7,
        "required_scheduled_slots": 50,
        "last_three_days_scheduled_slots": 21,
        "required_last_three_days": 3,
        "required_last_twenty_slots": 20,
    }
    assert report["latency"]["peer_gate"]["p95_ms"] == 2_000
    assert report["latency"]["clean_sweep"]["p95_ms"] == 120_000
    assert report["fingerprints"] == {
        "observed": 0,
        "closed": 0,
        "open": [],
        "same_root_recurrence": 0,
        "recent_same_root_recurrence": 0,
    }


def test_stability_acceptance_fails_on_duplicate_effect_and_repaired_recurrence():
    daily, convergence = _stable_window_events()
    daily.append({
        "event": "duplicate_effect_audit",
        "slot": "2026-08-07T12:00:00+08:00",
        "duplicate_count": 1,
        "duplicate_effect_counts": {"publication": 1},
    })
    convergence.extend([
        {
            "event": "failure_observed",
            "slot": "2026-08-02T07:00:00+08:00",
            "failure_fingerprint": FINGERPRINT,
            "ownership": "agent",
        },
        {
            "event": "repair_closed",
            "slot": "2026-08-02T08:00:00+08:00",
            "failure_fingerprint": FINGERPRINT,
            "repair_receipt": {"failure_fingerprint": FINGERPRINT},
        },
        {
            "event": "failure_observed",
            "slot": "2026-08-07T12:00:00+08:00",
            "failure_fingerprint": FINGERPRINT,
            "ownership": "agent",
        },
    ])

    report = build_stability_acceptance_report(
        daily,
        convergence,
        as_of="2026-08-08T23:00:00+08:00",
    )

    assert report["status"] == "failed"
    assert {blocker["code"] for blocker in report["blockers"]} == {
        "duplicate_effects_detected",
        "duplicate_effect_audit_mismatch",
        "fingerprint_closure_incomplete",
        "repair_after_same_root_recurrence",
    }
    recurrence = next(
        blocker for blocker in report["blockers"]
        if blocker["code"] == "repair_after_same_root_recurrence"
    )
    assert recurrence["fingerprint"] == FINGERPRINT
    assert report["next_verification_window"]["kind"] == "new_rollout"


def test_stability_acceptance_reports_latency_failure_and_open_owner():
    daily, convergence = _stable_window_events()
    for row in daily:
        row["sweep_elapsed_ms"] = 300_001
    convergence[1]["elapsed_ms"] = 60_001
    convergence[2]["elapsed_ms"] = 60_001
    convergence.append({
        "event": "failure_observed",
        "slot": "2026-08-07T12:00:00+08:00",
        "failure_fingerprint": FINGERPRINT,
        "ownership": "agent",
    })

    report = build_stability_acceptance_report(
        daily,
        convergence,
        as_of="2026-08-08T23:00:00+08:00",
    )

    assert report["status"] == "failed"
    assert report["latency"]["peer_gate"]["status"] == "failed"
    assert report["latency"]["clean_sweep"]["status"] == "failed"
    assert report["fingerprints"]["open"] == [FINGERPRINT]
    assert any(
        blocker["code"] == "fingerprint_closure_incomplete"
        and blocker["owner"] == "agent"
        for blocker in report["blockers"]
    )


def test_stability_acceptance_does_not_fill_an_empty_observation_date():
    daily, convergence = _stable_window_events()
    daily = [
        row for row in daily
        if not str(row.get("slot", "")).startswith("2026-08-03")
    ]
    for hour in range(14, 20):
        daily.append({
            "event": "sweep_completed",
            "slot": f"2026-08-08T{hour:02d}:00:00+08:00",
            "health": "healthy",
            "sweep_elapsed_ms": 120_000,
            "source_states": [{"name": "lv", "status": "no_update"}],
            "coordinator_source_video_bytes": 0,
        })

    report = build_stability_acceptance_report(
        daily,
        convergence,
        as_of="2026-08-08T23:00:00+08:00",
    )

    assert report["status"] == "pending_observation"
    assert report["window"]["scheduled_slots"] == 51
    assert report["window"]["missing_observation_dates"] == ["2026-08-03"]
    assert any(
        blocker["code"] == "observation_days_discontinuous"
        for blocker in report["blockers"]
    )


def test_stability_acceptance_fails_closed_on_active_peer_and_p0_safety():
    daily, convergence = _stable_window_events()
    convergence.extend([
        {
            "event": "peer_gate_observed",
            "slot": "2026-08-07T12:00:00+08:00",
            "elapsed_ms": 1_000,
            "gate_result": "no_op",
        },
        {
            "event": "safety_incident",
            "slot": "2026-08-07T12:00:00+08:00",
            "severity": "P0",
        },
    ])

    report = build_stability_acceptance_report(
        daily,
        convergence,
        as_of="2026-08-08T23:00:00+08:00",
    )

    assert report["status"] == "failed"
    assert report["safety"]["active_active"] == 1
    assert report["safety"]["p0_safety_incidents"] == 1
    assert {
        blocker["code"] for blocker in report["blockers"]
    } >= {"active_active_detected", "p0_safety_incident"}


def test_convergence_report_aggregates_credential_safe_operational_metrics():
    daily_events = [
        {
            "event": "runner_started",
            "slot": "2026-08-08T07:00+08:00",
        },
        {
            "event": "sweep_completed",
            "slot": "2026-08-08T07:00+08:00",
            "health": "healthy",
            "source_states": [{"name": "lv", "status": "no_update"}],
        },
        {
            "event": "sweep_completed",
            "slot": "2026-08-08T08:00+08:00",
            "health": "degraded",
            "source_states": [{
                "name": "lv",
                "status": "waiting",
                "repair_required": True,
                "failure": {
                    "category": "schema_error",
                    "code": "source_result_schema_invalid",
                    "stage": "source_result_validation",
                },
            }],
        },
        {
            "event": "duplicate_effect_audit",
            "slot": "2026-08-08T08:00+08:00",
            "duplicate_count": 0,
        },
        {
            "event": "slot_excluded",
            "slot": "2026-08-08T09:00+08:00",
            "reason": "outside_window",
        },
    ]
    convergence_events = [
        {
            "event": "failure_observed",
            "slot": "2026-08-08T08:00+08:00",
            "failure_fingerprint": FINGERPRINT,
        },
        {
            "event": "repair_closed",
            "slot": "2026-08-08T08:00+08:00",
            "failure_fingerprint": FINGERPRINT,
        },
        {
            "event": "failure_observed",
            "slot": "2026-08-08T09:00+08:00",
            "failure_fingerprint": FINGERPRINT,
        },
        {
            "event": "peer_gate_observed",
            "attempt_count": 2,
            "elapsed_ms": 17,
        },
        {
            "event": "side_effect_reconciled",
            "claim_identity": "claim-1",
            "external_business_effects_replayed": False,
        },
        {
            "event": "duplicate_effect_audit",
            "duplicate_count": 1,
        },
    ]

    report = build_convergence_report(
        daily_events,
        convergence_events,
        period_start="2026-08-08T00:00:00+08:00",
        period_end="2026-08-08T23:59:59+08:00",
    )

    assert report["period"] == {
        "start": "2026-08-08T00:00:00+08:00",
        "end": "2026-08-08T23:59:59+08:00",
    }
    assert report["slots"] == {
        "scheduled": 2,
        "clean": 1,
        "business": 0,
        "excluded": 1,
        "excluded_by_reason": {"outside_window": 1},
    }
    assert report["metrics"] == {
        "failure_fingerprints": 1,
        "repair_required": 2,
        "repair_closed": 1,
        "repair_after_same_root_recurrence": 1,
        "generic_waits": 0,
        "internal_failure_user_dependency": 0,
        "peer_gate_attempts": 2,
        "peer_gate_latency_ms": 17,
        "runner_starts": 1,
        "side_effect_reconciliations": 1,
        "duplicate_effect_audits": 2,
        "duplicate_effect_findings": 1,
    }
    assert report["stability_window"] == {
        "start": None,
        "scheduled_slots": 0,
        "required_days": 7,
        "required_scheduled_slots": 50,
        "complete": False,
    }
    assert "private" not in str(report)
    assert "https://" not in str(report)


def test_convergence_report_ignores_source_terminal_replay_audits():
    report = build_convergence_report(
        [
            {
                "event": "sweep_completed",
                "slot": "2026-08-10T07:00:00+08:00",
                "health": "healthy",
                "source_states": [],
            },
            {
                "event": "duplicate_effect_audit",
                "slot": "2026-08-10T07:00:00+08:00",
                "source": "viewpoint_maintenance",
                "audited": True,
                "duplicate_count": 3,
            },
            {
                "event": "duplicate_effect_audit",
                "slot": "2026-08-10T07:00:00+08:00",
                "duplicate_count": 0,
                "duplicate_effect_counts": {
                    "ack": 0,
                    "book": 0,
                    "knowledge": 0,
                    "publication": 0,
                    "reminder": 0,
                },
            },
        ],
        [],
        period_start="2026-08-10T00:00:00+08:00",
        period_end="2026-08-10T23:59:59+08:00",
    )

    assert report["metrics"]["duplicate_effect_audits"] == 1
    assert report["metrics"]["duplicate_effect_findings"] == 0


def test_stability_acceptance_ignores_source_terminal_replay_audits():
    daily, convergence = _stable_window_events()
    daily.append({
        "event": "duplicate_effect_audit",
        "slot": "2026-08-07T12:00:00+08:00",
        "source": "viewpoint_maintenance",
        "audited": True,
        "duplicate_count": 3,
    })

    report = build_stability_acceptance_report(
        daily,
        convergence,
        as_of="2026-08-08T23:00:00+08:00",
    )

    assert report["status"] == "passed"
    assert report["safety"]["duplicate_effects"] == 0


def test_stability_window_counts_slots_only_after_rollout_readback():
    report = build_convergence_report(
        [
            {"event": "sweep_completed", "slot": "2026-08-07T23:00+08:00"},
            {"event": "sweep_completed", "slot": "2026-08-08T07:00+08:00"},
        ],
        [{
            "event": "rollout_readback",
            "slot": "2026-08-07T22:00+08:00",
            "stability_window_start": "2026-08-07T22:00:00+08:00",
            "readback": {
                "automation_id": "automation-1",
                "writer_task_id": "task-1",
                "target_revision": REVISION,
            },
            "baseline": {},
        }],
        period_start="2026-08-08T00:00:00+08:00",
        period_end="2026-08-08T23:59:59+08:00",
    )

    assert report["stability_window"]["start"] == (
        "2026-08-07T22:00:00+08:00"
    )
    assert report["stability_window"]["scheduled_slots"] == 2


def test_rollout_readback_requires_one_authoritative_writer_and_protected_wip():
    readback = RolloutReadback.from_dict({
        "schema_version": 1,
        "automation_id": "xiaocao-kol-hourly-low-bandwidth-operation",
        "writer_task_id": "task-1",
        "target_revision": REVISION,
        "active_writer_count": 1,
        "duplicate_automation_count": 0,
        "automation_owner": "xiaocao-kol-hourly-low-bandwidth-operation",
        "automation_readback": True,
        "worktree_protected": True,
        "dependencies_ready": True,
        "private_config_ready": True,
        "restored_state_ready": True,
    })

    assert readback.accepted is True
    assert readback.to_dict()["target_revision"] == REVISION

    invalid = readback.to_dict()
    invalid["active_writer_count"] = 2
    with pytest.raises(ProgressContractError, match="exactly one active writer"):
        RolloutReadback.from_dict(invalid)


def test_rollout_restart_binds_window_start_to_ledger_time(tmp_path):
    clock_values = iter([
        datetime.fromisoformat("2026-08-01T07:30:00+08:00"),
        datetime.fromisoformat("2026-08-02T07:30:00+08:00"),
    ])
    ledger = ConvergenceLedger(
        tmp_path / "convergence.jsonl",
        now=lambda: next(clock_values),
    )

    first = ledger.record_rollout_readback(
        RolloutReadback.from_dict(_rollout_readback()),
        slot="2026-08-01T07:00:00+08:00",
        baseline={"failure_fingerprints": 0},
    )
    with pytest.raises(ProgressContractError, match="already recorded"):
        ledger.record_rollout_readback(
            RolloutReadback.from_dict(_rollout_readback()),
            slot="2026-08-02T07:00:00+08:00",
            baseline={"failure_fingerprints": 0},
        )
    second = ledger.record_rollout_readback(
        RolloutReadback.from_dict(_rollout_readback()),
        slot="2026-08-02T07:00:00+08:00",
        baseline={"failure_fingerprints": 0},
        restart_after_failed_acceptance=True,
    )

    assert first["stability_window_start"] == "2026-08-01T07:30:00+08:00"
    assert second["stability_window_start"] == "2026-08-02T07:30:00+08:00"
    assert second["restart_after_failed_acceptance"] is True


def test_convergence_report_rejects_naive_period_timestamps():
    with pytest.raises(ProgressContractError, match="period_start"):
        build_convergence_report(
            [],
            [],
            period_start=datetime(2026, 8, 8, tzinfo=timezone.utc).replace(
                tzinfo=None
            ).isoformat(),
            period_end="2026-08-08T23:59:59+08:00",
        )
