from __future__ import annotations

from xiaocao.live.buy_guards import (
    LIMIT_DOWN_BUY_BLOCKED,
    LIMIT_DOWN_CHECK_UNAVAILABLE,
    evaluate_buy_market_guard,
)


def test_limit_down_price_blocks_even_when_status_is_generic_trading() -> None:
    allowed, reason, evidence = evaluate_buy_market_guard(
        {
            "market_guard_required": True,
            "trade_status": "T",
            "down_price": 10.13,
            "market_price": 10.13,
            "market_observed_at": "09:29:59",
        }
    )
    assert allowed is False
    assert reason == LIMIT_DOWN_BUY_BLOCKED
    assert evidence["down_price"] == 10.13


def test_authoritative_trading_facts_allow_buy_above_down_price() -> None:
    allowed, reason, _ = evaluate_buy_market_guard(
        {
            "market_guard_required": True,
            "trade_status": "T",
            "down_price": 10.13,
            "market_price": 10.20,
            "market_observed_at": "09:29:59",
        }
    )
    assert allowed is True
    assert reason is None


def test_missing_live_facts_fail_closed() -> None:
    allowed, reason, _ = evaluate_buy_market_guard({"market_guard_required": True})
    assert allowed is False
    assert reason == LIMIT_DOWN_CHECK_UNAVAILABLE


def test_live_facts_without_observation_timestamp_fail_closed() -> None:
    allowed, reason, _ = evaluate_buy_market_guard(
        {
            "market_guard_required": True,
            "trade_status": "T",
            "down_price": 10.13,
            "market_price": 10.20,
        }
    )
    assert allowed is False
    assert reason == LIMIT_DOWN_CHECK_UNAVAILABLE


def test_live_facts_with_malformed_dated_observation_fail_closed() -> None:
    allowed, reason, _ = evaluate_buy_market_guard(
        {
            "date": "2026-08-15",
            "market_guard_required": True,
            "trade_status": "T",
            "down_price": 10.13,
            "market_price": 10.20,
            "market_observed_at": "not-a-timestamp",
        }
    )
    assert allowed is False
    assert reason == LIMIT_DOWN_CHECK_UNAVAILABLE


def test_historical_rows_keep_existing_paper_behavior_without_live_guard() -> None:
    allowed, reason, _ = evaluate_buy_market_guard({})
    assert allowed is True
    assert reason is None
