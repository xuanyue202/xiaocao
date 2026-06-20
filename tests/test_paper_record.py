from __future__ import annotations

from kronos_screen.scripts.paper_record import (
    _attach_fill_prices,
    _fill_price,
    _fill_price_from_window,
    _fill_window_stats,
    _filter_affordable_fixed_slot,
    _quality_governor_buyable,
    _validate_fill_window,
)
from kronos_screen.scripts.quality_governor import ensure_quality_fields


class FakeClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def minute_line(self, code: str, freq: str, adj: str, *, trade_date: str, count: int):
        return self.rows


def test_fill_uses_window_vwap_when_below_limit() -> None:
    price, basis, basket_rule, meta = _fill_price_from_window(
        {"basket_price": 10.391, "basket_rule": "entry+2.1%", "open": 10.18},
        window={"vwap": 10.20, "low": 10.10, "high": 10.28, "time": "0931"},
        limit_premium_pct=0.5,
    )

    assert price == 10.20
    assert basis == "opening_window_vwap_capped_by_limit"
    assert basket_rule == "entry+2.1%"
    assert meta["fill_window_vwap"] == 10.20
    # limit = open * 1.005 = 10.2309 (basket above it does not matter)
    assert abs(meta["fill_limit_price"] - 10.2309) < 1e-6


def test_fill_caps_at_limit_when_vwap_trades_above() -> None:
    price, basis, _, meta = _fill_price_from_window(
        {"basket_price": 10.391, "basket_rule": "entry+2.1%", "open": 10.18},
        window={"vwap": 10.30, "low": 10.15, "high": 10.5, "time": "0931"},
        limit_premium_pct=0.5,
    )

    # vwap 10.30 > limit 10.2309, but window low 10.15 reached the limit -> fill at limit
    assert abs(price - 10.2309) < 1e-6
    assert basis == "opening_window_vwap_capped_by_limit"


def test_fill_skipped_when_window_never_reaches_limit() -> None:
    price, basis, _, meta = _fill_price_from_window(
        {"basket_price": 10.391, "basket_rule": "entry+2.1%", "open": 10.18},
        window={"vwap": 10.35, "low": 10.30, "high": 10.5, "time": "0931"},
        limit_premium_pct=0.5,
    )

    assert price is None
    assert basis == "skipped_limit_not_reached"
    assert meta["skip_reason"] == "LIMIT_NOT_REACHED"


def test_fill_limit_is_bounded_by_basket() -> None:
    price, _, _, meta = _fill_price_from_window(
        {"basket_price": 10.20, "basket_rule": "entry+0.2%", "open": 10.18},
        window={"vwap": 10.30, "low": 10.10, "high": 10.5, "time": "0931"},
        limit_premium_pct=0.5,
    )

    # limit = min(10.18 * 1.005, basket 10.20) = 10.20
    assert price == 10.20
    assert meta["fill_limit_price"] == 10.20


def test_fill_window_stats_uses_only_configured_opening_minutes() -> None:
    client = FakeClient([
        {"tradeTime": "0929", "close": 11.0, "high": 11.0, "low": 11.0, "amt": 1100.0, "vol": 100},
        {"tradeTime": "0930", "close": 10.1, "high": 10.2, "low": 10.0, "amt": 1010.0, "vol": 100},
        {"tradeTime": "0931", "close": 10.28, "high": 10.3, "low": 10.2, "amt": 3084.0, "vol": 300},
        {"tradeTime": "0932", "close": 10.9, "high": 10.9, "low": 10.9, "amt": 1090.0, "vol": 100},
    ])

    stats = _fill_window_stats(
        client,
        "000670.XSHE",
        "2026-06-10",
        start_hhmm="0930",
        end_hhmm="0931",
    )

    assert stats is not None
    assert abs(stats["vwap"] - (1010.0 + 3084.0) / 400) < 1e-9
    assert stats["low"] == 10.0
    assert stats["high"] == 10.3
    assert stats["time"] == "0931"


def test_attach_fill_prices_splits_fillable_and_skipped() -> None:
    client = FakeClient([
        {"tradeTime": "0930", "close": 5.08, "high": 5.08, "low": 5.07, "amt": 508.0, "vol": 100},
        {"tradeTime": "0931", "close": 5.09, "high": 5.11, "low": 5.08, "amt": 509.0, "vol": 100},
    ])

    fillable, skipped = _attach_fill_prices(
        client,
        [{"code": "002613.XSHE", "basket_price": 5.212, "basket_rule": "entry+2.0%", "open": 5.11}],
        "2026-06-10",
        start_hhmm="0930",
        end_hhmm="0931",
        limit_premium_pct=0.5,
    )

    assert not skipped
    [record] = fillable
    price, basis, basket_rule = _fill_price(record)
    # vwap = 1017/200 = 5.085, below limit 5.11*1.005 -> fill at vwap
    assert abs(price - 5.085) < 1e-9
    assert basis == "opening_window_vwap_capped_by_limit"
    assert basket_rule == "entry+2.0%"


def test_attach_fill_prices_skips_when_limit_not_reached() -> None:
    client = FakeClient([
        {"tradeTime": "0930", "close": 5.30, "high": 5.32, "low": 5.28, "amt": 530.0, "vol": 100},
        {"tradeTime": "0931", "close": 5.31, "high": 5.33, "low": 5.29, "amt": 531.0, "vol": 100},
    ])

    fillable, skipped = _attach_fill_prices(
        client,
        [{"code": "002613.XSHE", "basket_price": 5.212, "basket_rule": "entry+2.0%", "open": 5.11}],
        "2026-06-10",
        start_hhmm="0930",
        end_hhmm="0931",
        limit_premium_pct=0.5,
    )

    assert not fillable
    [record] = skipped
    assert record["_paper_fill"]["skip_reason"] == "LIMIT_NOT_REACHED"


def test_old_snapshot_quality_fields_are_recomputed() -> None:
    row = ensure_quality_fields({
        "code": "300001.XSHE",
        "mode": "绿断低吸",
        "xcjw": 100.0,
        "cjs": 50.0,
        "p_score": -2.2,
    })

    assert row["primary_score"] == 140.0
    assert row["primary_score_label"] == "xcjw+0.8*cjs"
    assert row["quality_tag"] == "weak_primary+p_tail_warning"
    assert row["quality_fields_fallback"] is True


def test_quality_governor_modes_preserve_slots() -> None:
    picks = [
        {"code": "A.XSHE", "mode": "绿断低吸", "xcjw": 200.0, "cjs": 0.0, "p_score": 0.0},
        {"code": "B.XSHE", "mode": "绿断低吸", "xcjw": 100.0, "cjs": 0.0, "p_score": 0.0},
    ]

    shadow_all, shadow_active, shadow_slots = _quality_governor_buyable(picks, "shadow")
    on_all, on_active, on_slots = _quality_governor_buyable(picks, "on")

    assert len(shadow_all) == 2
    assert len(shadow_active) == 2
    assert shadow_slots == 2
    assert len(on_all) == 2
    assert [p["code"] for p in on_active] == ["A.XSHE"]
    assert on_slots == 2


def test_fixed_slot_filter_does_not_reallocate_cash() -> None:
    # One lot costs about 600 RMB. With target_notional fixed at 500, the pick is
    # unaffordable even though total cash is 1000; filtered slots stay in cash.
    eligible = _filter_affordable_fixed_slot(
        [{"code": "A.XSHE", "basket_price": 6.0}],
        target_notional=500.0,
        cash=1000.0,
        fee_rate=0.0,
    )

    assert eligible == []


def _book_a_closed(exit_date: str, cash_out: float, pnl: float) -> dict:
    return {
        "book": "A", "status": "closed", "exit_date": exit_date,
        "entry_cash_out": cash_out, "realized_pnl": pnl,
        "code": "X.XSHE", "entry_date": exit_date,
    }


def test_kill_switch_inactive_without_book_a_history(tmp_path, monkeypatch) -> None:
    import json
    import kronos_screen.scripts.paper_record as pr
    pos = tmp_path / "positions.jsonl"
    pos.write_text("", encoding="utf-8")
    monkeypatch.setattr(pr, "POS", pos)

    factor, reason = pr._kill_switch_factor()
    assert factor == 1.0
    assert "no closed trades" in reason


def test_kill_switch_pauses_on_deep_book_a_drawdown(tmp_path, monkeypatch) -> None:
    import json
    import kronos_screen.scripts.paper_record as pr
    pos = tmp_path / "positions.jsonl"
    rows = [_book_a_closed(f"2026-06-0{i}", 10000.0, -120.0 - 60 * i) for i in range(1, 6)]
    pos.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(pr, "POS", pos)

    # cum = sum(pnl)/sum(cash_out) = (-180-240-300-360-420)/50000 = -3.0%... make deeper
    rows = [_book_a_closed(f"2026-06-0{i}", 10000.0, -600.0) for i in range(1, 6)]
    pos.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    factor, reason = pr._kill_switch_factor()
    assert factor == 0.0  # -6% < -5% -> pause
    assert "PAUSE" in reason


def test_kill_switch_halves_on_moderate_book_a_drawdown(tmp_path, monkeypatch) -> None:
    import json
    import kronos_screen.scripts.paper_record as pr
    pos = tmp_path / "positions.jsonl"
    rows = [_book_a_closed(f"2026-06-0{i}", 10000.0, -400.0) for i in range(1, 6)]
    pos.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(pr, "POS", pos)

    factor, reason = pr._kill_switch_factor()
    assert factor == 0.5  # -4% in (-5%, -3%] -> halve
    assert "HALVE" in reason


def test_validate_fill_window_rejects_reversed_window() -> None:
    try:
        _validate_fill_window("0931", "0930")
    except ValueError as exc:
        assert "fill-window-end" in str(exc)
    else:
        raise AssertionError("expected reversed fill window to fail")
