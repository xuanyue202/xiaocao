from __future__ import annotations

import copy

import pytest

from xiaocao.research.book_t_v2_lifecycle import (
    BookTV2EvidenceError,
    append_events,
    build_daily_mark_event,
    build_exit_event,
    build_initial_lifecycle,
    build_matured_outcome_event,
    engineering_burn_in_gate,
    lifecycle_summary,
    read_events,
)


def _lifecycle(*, mode: str = "rehearsal", index: int = 100) -> dict:
    return build_initial_lifecycle(
        decision_id=f"book-t-v2:2026-08-21:{mode}:{index}",
        as_of="2026-08-21",
        observed_at="2026-08-21T01:25:00Z",
        trading_day_index=index,
        run_mode=mode,
        snapshot_sha256="a" * 64,
        universe_sha256="b" * 64,
        selection_plan_sha256="c" * 64,
        portfolio_sha256="d" * 64,
        control_receipt_sha256="e" * 64,
        fills=[
            {
                "as_of": "2026-08-21",
                "code": "000001.XSHE",
                "status": "blocked",
                "skip_reason": "MARKET_FACT_UNAVAILABLE",
            }
        ],
        daily_reevaluation_complete=True,
    )


def test_morning_lifecycle_has_no_future_outcome_fields() -> None:
    lifecycle = _lifecycle()

    assert [event["stage"] for event in lifecycle["stages"]] == ["decision", "fill"]
    assert lifecycle["outcome_status"] == "not_applicable"
    with pytest.raises(BookTV2EvidenceError, match="future outcome"):
        build_initial_lifecycle(
            decision_id="bad",
            as_of="2026-08-21",
            observed_at="2026-08-21T01:25:00Z",
            trading_day_index=100,
            run_mode="rehearsal",
            snapshot_sha256="a" * 64,
            universe_sha256="b" * 64,
            selection_plan_sha256="c" * 64,
            portfolio_sha256="d" * 64,
            control_receipt_sha256="e" * 64,
            fills=[
                {
                    "as_of": "2026-08-21",
                    "code": "000001.XSHE",
                    "status": "filled",
                    "strat_ret": 1.0,
                }
            ],
            daily_reevaluation_complete=True,
        )


def test_daily_mark_appends_idempotently_without_maturing_outcome(tmp_path) -> None:
    lifecycle = _lifecycle()
    event = build_daily_mark_event(
        lifecycle,
        observed_at="2026-08-21T07:10:00Z",
        marks=[{"as_of": "2026-08-21", "code": "000001.XSHE", "price": 10.2, "source": "test"}],
    )
    path = tmp_path / "events.jsonl"

    first = append_events(path, [event])
    second = append_events(path, [copy.deepcopy(event)])

    assert len(first) == len(second) == 1
    assert read_events(path) == [event]
    assert lifecycle_summary([lifecycle], events=second)["outcome_pending"] == 0
    assert lifecycle_summary([lifecycle], events=second)["stage_counts"]["daily_mark"] == 1


def test_daily_mark_cannot_bind_a_future_or_prior_observation() -> None:
    lifecycle = _lifecycle()
    with pytest.raises(BookTV2EvidenceError, match="decision day"):
        build_daily_mark_event(
            lifecycle,
            observed_at="2026-08-22T07:10:00Z",
            marks=[{"as_of": "2026-08-22", "code": "000001.XSHE", "price": 10.2}],
        )
    with pytest.raises(BookTV2EvidenceError, match="precedes"):
        build_exit_event(
            lifecycle,
            observed_at="2026-08-20T07:10:00Z",
            exits=[{"as_of": "2026-08-20", "code": "000001.XSHE", "exit_price": 10.1}],
        )


def test_exit_and_matured_events_are_later_explicit_stages() -> None:
    lifecycle = _lifecycle()
    exit_event = build_exit_event(
        lifecycle,
        observed_at="2026-08-25T07:10:00Z",
        exits=[{"as_of": "2026-08-25", "code": "000001.XSHE", "exit_price": 10.5}],
    )
    matured = build_matured_outcome_event(
        lifecycle,
        observed_at="2026-08-28T07:10:00Z",
        outcomes=[
            {
                "as_of": "2026-08-28",
                "code": "000001.XSHE",
                "strat_ret": 5.0,
                "base_ret": 3.0,
            }
        ],
    )

    assert exit_event["stage"] == "exit"
    assert matured["stage"] == "matured"
    assert lifecycle_summary([lifecycle], events=[exit_event, matured])["outcome_matured"] == 1


def test_burn_in_counts_real_contiguous_days_and_excludes_rehearsal() -> None:
    rehearsal = _lifecycle(mode="rehearsal", index=1)
    real_one = _lifecycle(mode="real", index=10)
    real_two = copy.deepcopy(real_one)
    real_two["decision_id"] = "book-t-v2:2026-08-22:real:11"
    real_two["as_of"] = "2026-08-22"
    for event in real_two["stages"]:
        event["decision_id"] = real_two["decision_id"]
        event["data"]["as_of"] = "2026-08-22"
    # Re-seal the copied test row through the public validator's contract.
    # This deliberately uses the same production hash rule as a persisted row.
    from xiaocao.kol.publication import canonical_sha256

    for event in real_two["stages"]:
        event["observed_at"] = "2026-08-22T01:25:00Z"
        event.pop("event_id", None)
        event["event_id"] = canonical_sha256(event)
    real_two.pop("evidence_lifecycle_sha256", None)
    real_two["evidence_lifecycle_sha256"] = canonical_sha256(real_two)

    result = engineering_burn_in_gate([rehearsal, real_one, real_two])

    assert result["status"] == "pending"
    assert result["real_trading_days"] == 2
    assert result["rehearsal_days_excluded"] == 1
    assert result["promotion_authorized"] is False
