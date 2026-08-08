from datetime import datetime, timezone

import pytest

from xiaocao.kol.writer_progress import (
    ProgressContractError,
    RolloutReadback,
    build_convergence_report,
)


REVISION = "a" * 40
FINGERPRINT = "b" * 64


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
