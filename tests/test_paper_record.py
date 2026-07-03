from __future__ import annotations

import json
from argparse import Namespace

from kronos_screen.scripts.paper_record import (
    _attach_fill_prices,
    _fill_price,
    _fill_price_from_window,
    _fill_window_stats,
    _filter_affordable_fixed_slot,
    _quality_governor_buyable,
    _record_book_t,
    _record_book_a,
    _validate_fill_window,
)
from kronos_screen.scripts.quality_governor import ensure_quality_fields


class FakeClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def minute_line(self, code: str, freq: str, adj: str, *, trade_date: str, count: int):
        return self.rows


class FakeBookTClient(FakeClient):
    def stock_info(self):
        return [
            {"code": "600BIG.XSHG", "codeName": "大票B", "statusType": 1, "tradableAShare": 10_000},
        ]

    def get_block_category_rank_v3(self, date, model=0):
        return [{"categoryCode": "C1.BKDL", "name": "主线", "num": 200, "trendScore": 188}]

    def get_code_by_xiao_cao_block(self, date, **filters):
        return ["600BIG.XSHG"]

    def second_line_detail_info(self, codes):
        return {
            "600BIG.XSHG": {
                "code": "600BIG.XSHG",
                "codeName": "大票B",
                "open": 10.0,
                "preClose": 9.9,
                "pctChangeRate": 1.0,
            }
        }


class FakeBookTSwitchClient(FakeClient):
    def stock_info(self):
        return [
            {"code": "601288.XSHG", "codeName": "农业银行", "statusType": 1, "tradableAShare": 300_000},
            {"code": "000725.XSHE", "codeName": "京东方Ａ", "statusType": 1, "tradableAShare": 90_000},
        ]

    def get_block_category_rank_v3(self, date, model=0):
        return [
            {"categoryCode": "BANK.BKDL", "name": "业绩股权类", "num": 200, "trendScore": 200},
            {"categoryCode": "ELEC.BKDL", "name": "行业电子", "num": 180, "trendScore": 180},
        ]

    def get_code_by_xiao_cao_block(self, date, **filters):
        code = filters.get("categoryCodeList")
        if code == "BANK.BKDL":
            return ["601288.XSHG"]
        if code == "ELEC.BKDL":
            return ["000725.XSHE"]
        return []

    def second_line_detail_info(self, codes):
        return {
            "000725.XSHE": {
                "code": "000725.XSHE",
                "codeName": "京东方Ａ",
                "open": 10.0,
                "preClose": 9.9,
                "pctChangeRate": 1.0,
            }
        }

    def minute_line(self, code: str, freq: str, adj: str, *, trade_date: str, count: int):
        px = 5.0 if code == "601288.XSHG" else 10.0
        return [
            {"tradeTime": "0930", "close": px, "high": px, "low": px, "amt": px * 100, "vol": 100},
            {"tradeTime": "0931", "close": px, "high": px, "low": px, "amt": px * 100, "vol": 100},
        ]


class FakeBookTNoReplacementClient(FakeBookTSwitchClient):
    def stock_info(self):
        return [
            {"code": "601288.XSHG", "codeName": "农业银行", "statusType": 1, "tradableAShare": 300_000},
        ]

    def get_block_category_rank_v3(self, date, model=0):
        return [
            {"categoryCode": "BANK.BKDL", "name": "业绩股权类", "num": 200, "trendScore": 200},
        ]

    def get_code_by_xiao_cao_block(self, date, **filters):
        if filters.get("categoryCodeList") == "BANK.BKDL":
            return ["601288.XSHG"]
        return []

    def second_line_detail_info(self, codes):
        return {}


def _patch_book_t_paths(tmp_path, monkeypatch):
    import kronos_screen.scripts.paper_record as pr

    pos = tmp_path / "positions.jsonl"
    account_t = tmp_path / "paper_account_T.json"
    trades = tmp_path / "paper_trades.jsonl"
    skips = tmp_path / "paper_skips.jsonl"
    monkeypatch.setattr(pr, "POS", pos)
    monkeypatch.setattr(pr, "ACCOUNT_T", account_t)
    monkeypatch.setattr(pr, "TRADES", trades)
    monkeypatch.setattr(pr, "SKIPS", skips)
    return pos, account_t, trades


def _book_t_args(*, target_positions: int = 1) -> Namespace:
    return Namespace(
        date="2026-07-03",
        initial_capital=100000.0,
        fee_rate=0.0001,
        trend_budget_ratio=0.3,
        trend_max_positions=target_positions,
        trend_max_total_exposure_ratio=1.0,
        fill_window_start="0930",
        fill_window_end="0931",
        limit_premium_pct=0.5,
        allow_additional=False,
    )


def _bank_position() -> dict:
    return {
        "book": "T",
        "code": "601288.XSHG",
        "name": "农业银行",
        "entry_date": "2026-07-02",
        "entry_price": 5.0,
        "shares": 2000,
        "gross_notional": 10000.0,
        "entry_fee": 1.0,
        "entry_cash_out": 10001.0,
        "fee_rate": 0.0001,
        "category_name": "业绩股权类",
        "status": "open",
        "source": "auto:trend_book",
    }


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


def test_fill_retries_at_realtime_when_window_never_reaches_limit_but_still_suitable() -> None:
    price, basis, _, meta = _fill_price_from_window(
        {"basket_price": 10.391, "basket_rule": "entry+2.1%", "open": 10.18},
        window={"vwap": 10.35, "low": 10.30, "high": 10.5, "last": 10.35, "time": "0931"},
        limit_premium_pct=0.5,
    )

    assert price == 10.35
    assert basis == "retry_realtime_after_limit_reject"
    assert meta["initial_fill_block_reason"] == "LIMIT_NOT_REACHED"
    assert meta["fill_retry"] is True
    assert meta["fill_retry_reason"] == "LIMIT_NOT_REACHED_REALTIME_WITHIN_BASKET"
    assert meta["fill_retry_price"] == 10.35


def test_fill_skips_when_realtime_retry_would_exceed_basket() -> None:
    price, basis, _, meta = _fill_price_from_window(
        {"basket_price": 10.32, "basket_rule": "entry+1.4%", "open": 10.18},
        window={"vwap": 10.35, "low": 10.30, "high": 10.5, "last": 10.35, "time": "0931"},
        limit_premium_pct=0.5,
    )

    assert price is None
    assert basis == "skipped_limit_not_reached"
    assert meta["skip_reason"] == "LIMIT_NOT_REACHED"
    assert meta["skip_detail"] == "REALTIME_ABOVE_BASKET"


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
    assert stats["last"] == 10.28
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
    assert record["_paper_fill"]["skip_detail"] == "REALTIME_ABOVE_BASKET"


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


def test_raw_qibao_benchmark_quality_uses_rank_score() -> None:
    for mode in ("标杆短线起爆", "高开标杆起爆", "强攻标杆起爆"):
        row = ensure_quality_fields({
            "code": "688001.XSHG",
            "mode": mode,
            "jssb": 5.0,
            "qibaoRankScore": 228.0,
        })

        assert row["primary_score"] == 228.0
        assert row["primary_score_label"] == "qibaoRankScore"
        assert row["quality_tag"] == "normal"


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


def test_book_a_uses_book_b_aligned_fill_price(tmp_path, monkeypatch) -> None:
    import json
    from argparse import Namespace
    import kronos_screen.scripts.paper_record as pr

    pos = tmp_path / "positions.jsonl"
    account_a = tmp_path / "paper_account_A.json"
    trades = tmp_path / "paper_trades.jsonl"
    pos.write_text("", encoding="utf-8")
    monkeypatch.setattr(pr, "POS", pos)
    monkeypatch.setattr(pr, "ACCOUNT_A", account_a)
    monkeypatch.setattr(pr, "TRADES", trades)

    args = Namespace(
        date="2026-06-24",
        pick="vb_star",
        initial_capital=100000.0,
        deploy_ratio=0.5,
        fill_window_start="0930",
        fill_window_end="0931",
    )
    picks = [{
        "code": "000001.XSHE",
        "name": "平安银行",
        "mode": "首红断低吸",
        "open": 10.0,
        "basket_price": 10.2,
        "basket_rule": "entry+2.0%",
        "_paper_fill": {
            "price": 10.05,
            "basis": "opening_window_vwap_capped_by_limit",
            "fill_window_vwap": 10.05,
            "fill_limit_price": 10.05,
            "fill_window_last": 10.06,
        },
    }]

    _record_book_a(picks, args, fee_rate=0.0001)

    [row] = [json.loads(line) for line in pos.read_text(encoding="utf-8").splitlines()]
    assert row["book"] == "A"
    assert row["entry_price"] == 10.05
    assert row["entry_price_basis"] == "opening_window_vwap_capped_by_limit"
    assert row["fill_limit_price"] == 10.05
    assert row["fill_window_last"] == 10.06


def test_book_t_records_independent_trend_account(tmp_path, monkeypatch) -> None:
    import json
    from argparse import Namespace
    import kronos_screen.scripts.paper_record as pr

    pos = tmp_path / "positions.jsonl"
    account_t = tmp_path / "paper_account_T.json"
    trades = tmp_path / "paper_trades.jsonl"
    skips = tmp_path / "paper_skips.jsonl"
    monkeypatch.setattr(pr, "POS", pos)
    monkeypatch.setattr(pr, "ACCOUNT_T", account_t)
    monkeypatch.setattr(pr, "TRADES", trades)
    monkeypatch.setattr(pr, "SKIPS", skips)

    args = Namespace(
        date="2026-07-01",
        initial_capital=100000.0,
        fee_rate=0.0001,
        trend_budget_ratio=0.3,
        trend_max_positions=3,
        trend_max_total_exposure_ratio=1.0,
        fill_window_start="0930",
        fill_window_end="0931",
        limit_premium_pct=0.5,
        allow_additional=False,
    )
    client = FakeBookTClient([
        {"tradeTime": "0930", "close": 10.0, "high": 10.02, "low": 9.98, "amt": 1000.0, "vol": 100},
        {"tradeTime": "0931", "close": 10.0, "high": 10.03, "low": 9.99, "amt": 1000.0, "vol": 100},
    ])

    _record_book_t(client, args)

    [row] = [json.loads(line) for line in pos.read_text(encoding="utf-8").splitlines()]
    assert row["book"] == "T"
    assert row["source"] == "auto:trend_book"
    assert row["category_code"] == "C1.BKDL"
    assert row["entry_price_basis"] == "opening_window_vwap_capped_by_limit"
    assert row["trend_alignment"] == "neutral"
    assert "兜底" in row["trend_alignment_reason"]
    assert row["shares"] == 900
    account = json.loads(account_t.read_text(encoding="utf-8"))
    assert account["initial_capital"] == 30000.0
    [trade] = [json.loads(line) for line in trades.read_text(encoding="utf-8").splitlines()]
    assert trade["book"] == "T" and trade["side"] == "BUY"
    assert trade["trend_alignment"] == "neutral"


def test_book_t_switches_external_position_only_with_paired_replacement(tmp_path, monkeypatch) -> None:
    pos, account_t, trades = _patch_book_t_paths(tmp_path, monkeypatch)
    pos.write_text(json.dumps(_bank_position(), ensure_ascii=False) + "\n", encoding="utf-8")
    account_t.write_text(json.dumps({
        "initial_capital": 30000.0,
        "cash": 19999.0,
        "fee_rate": 0.0001,
        "realized_pnl": 0.0,
        "total_fees": 1.0,
    }), encoding="utf-8")

    _record_book_t(FakeBookTSwitchClient([]), _book_t_args(target_positions=1))

    rows = [json.loads(line) for line in pos.read_text(encoding="utf-8").splitlines()]
    old, new = rows
    assert old["code"] == "601288.XSHG"
    assert old["status"] == "closed"
    assert old["exit_reason"] == "TREND_POSTURE_MISMATCH"
    assert old["trend_switch_execution"] == "paired_morning_switch"
    assert new["code"] == "000725.XSHE"
    assert new["status"] == "open"
    assert new["trend_alignment"] == "aligned"
    assert new["trend_switch_execution"] == "paired_morning_replacement"

    trade_rows = [json.loads(line) for line in trades.read_text(encoding="utf-8").splitlines()]
    assert [(r["side"], r["code"]) for r in trade_rows] == [
        ("SELL", "601288.XSHG"),
        ("BUY", "000725.XSHE"),
    ]
    account = json.loads(account_t.read_text(encoding="utf-8"))
    assert round(account["cash"], 2) == 995.10
    assert account["realized_pnl"] == -2.0
    assert account["total_fees"] == 4.9


def test_book_t_switch_candidate_consumes_replacement_before_empty_slot(tmp_path, monkeypatch) -> None:
    pos, account_t, trades = _patch_book_t_paths(tmp_path, monkeypatch)
    existing_aligned = {
        "book": "T",
        "code": "003816.XSHE",
        "name": "中国广核",
        "entry_date": "2026-07-02",
        "entry_price": 4.0,
        "shares": 2000,
        "gross_notional": 8000.0,
        "entry_fee": 0.8,
        "entry_cash_out": 8000.8,
        "fee_rate": 0.0001,
        "category_name": "行业电子",
        "status": "open",
        "source": "auto:trend_book",
    }
    pos.write_text(
        json.dumps(_bank_position(), ensure_ascii=False) + "\n"
        + json.dumps(existing_aligned, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    account_t.write_text(json.dumps({
        "initial_capital": 30000.0,
        "cash": 11998.2,
        "fee_rate": 0.0001,
        "realized_pnl": 0.0,
        "total_fees": 1.8,
    }), encoding="utf-8")

    _record_book_t(FakeBookTSwitchClient([]), _book_t_args(target_positions=3))

    rows = [json.loads(line) for line in pos.read_text(encoding="utf-8").splitlines()]
    old_bank, old_aligned, replacement = rows
    assert old_bank["status"] == "closed"
    assert old_bank["exit_reason"] == "TREND_POSTURE_MISMATCH"
    assert old_aligned["status"] == "open"
    assert replacement["code"] == "000725.XSHE"
    assert replacement["trend_switch_execution"] == "paired_morning_replacement"
    assert [(r["side"], r["code"]) for r in [
        json.loads(line) for line in trades.read_text(encoding="utf-8").splitlines()
    ]] == [
        ("SELL", "601288.XSHG"),
        ("BUY", "000725.XSHE"),
    ]


def test_book_t_rebalance_due_switches_only_with_paired_replacement(tmp_path, monkeypatch) -> None:
    pos, account_t, trades = _patch_book_t_paths(tmp_path, monkeypatch)
    due = {
        "book": "T",
        "code": "003816.XSHE",
        "name": "中国广核",
        "entry_date": "2026-07-02",
        "entry_price": 4.0,
        "shares": 2000,
        "gross_notional": 8000.0,
        "entry_fee": 0.8,
        "entry_cash_out": 8000.8,
        "fee_rate": 0.0001,
        "category_name": "行业电子",
        "trend_rebalance_days": 1,
        "status": "open",
        "source": "auto:trend_book",
    }
    pos.write_text(json.dumps(due, ensure_ascii=False) + "\n", encoding="utf-8")
    account_t.write_text(json.dumps({
        "initial_capital": 30000.0,
        "cash": 21999.2,
        "fee_rate": 0.0001,
        "realized_pnl": 0.0,
        "total_fees": 0.8,
    }), encoding="utf-8")

    _record_book_t(FakeBookTSwitchClient([]), _book_t_args(target_positions=1))

    old, new = [json.loads(line) for line in pos.read_text(encoding="utf-8").splitlines()]
    assert old["status"] == "closed"
    assert old["exit_reason"] == "TREND_REBALANCE_R"
    assert old["trend_switch_execution"] == "paired_morning_switch"
    assert new["code"] == "000725.XSHE"
    assert new["trend_switch_execution"] == "paired_morning_replacement"


def test_book_t_keeps_external_position_when_no_replacement_exists(tmp_path, monkeypatch) -> None:
    pos, account_t, trades = _patch_book_t_paths(tmp_path, monkeypatch)
    pos.write_text(json.dumps(_bank_position(), ensure_ascii=False) + "\n", encoding="utf-8")
    account_t.write_text(json.dumps({
        "initial_capital": 30000.0,
        "cash": 19999.0,
        "fee_rate": 0.0001,
        "realized_pnl": 0.0,
        "total_fees": 1.0,
    }), encoding="utf-8")

    _record_book_t(FakeBookTNoReplacementClient([]), _book_t_args(target_positions=1))

    [row] = [json.loads(line) for line in pos.read_text(encoding="utf-8").splitlines()]
    assert row["code"] == "601288.XSHG"
    assert row["status"] == "open"
    assert not trades.exists()
    account = json.loads(account_t.read_text(encoding="utf-8"))
    assert account["cash"] == 19999.0
    assert account["realized_pnl"] == 0.0


def test_validate_fill_window_rejects_reversed_window() -> None:
    try:
        _validate_fill_window("0931", "0930")
    except ValueError as exc:
        assert "fill-window-end" in str(exc)
    else:
        raise AssertionError("expected reversed fill window to fail")
