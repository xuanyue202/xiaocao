from __future__ import annotations

from typing import Any

import pytest

from xiaocao.strategy.rules import check_qibao, pick_big_ones
from xiaocao.strategy.runner import (
    STRATEGY_PROFILES,
    _dedupe_signals,
    _filter_open_pct,
    run_strategy,
)


def test_check_qibao_emits_main_attack_when_score_high_and_red_under_4pct() -> None:
    details = [
        {  # main attack candidate: jssb high, pct in (0, 4]
            "code": "001.XSHE", "jssb": 250, "isLimitUp": 0,
            "entityPctChangeRate": 2.5,
        },
        {  # below floor — break early
            "code": "002.XSHE", "jssb": 50, "isLimitUp": 0,
            "entityPctChangeRate": 1.0,
        },
    ]
    out = check_qibao(details, [], [], "2026-04-25")
    assert [s["mode"] for s in out] == ["红盘起爆主攻"]


def test_check_qibao_skips_already_limit_up_and_negative_pct() -> None:
    details = [
        {"code": "001", "jssb": 300, "isLimitUp": 1, "entityPctChangeRate": 9.99},
        {"code": "002", "jssb": 300, "isLimitUp": 0, "entityPctChangeRate": -1.0},
        {"code": "003", "jssb": 300, "isLimitUp": 0, "entityPctChangeRate": 9.6},
    ]
    out = check_qibao(details, [], [], "2026-04-25")
    assert out == []  # all three filtered (limit-up / red below 0 / >= 9.5%)


def test_check_qibao_direction_variant_with_lower_score() -> None:
    # jssb between QUALIFIED/1.3 (115.4) and STRONG/1.3 (153.8); with direction
    # support, only the secondary 方向红盘起爆 fires. Tighter pct cap (≤ 3).
    picked_block = [{"blockCode": "BK001", "blockName": "AI", "num": 100, "r": 0}]
    details = [
        {
            "code": "001.XSHE",
            "jssb": 130, "isLimitUp": 0,
            "entityPctChangeRate": 1.5,
            "blockCodeList": ["BK001"],
        },
        {  # same jssb, but no direction → no signal
            "code": "002.XSHE",
            "jssb": 130, "isLimitUp": 0,
            "entityPctChangeRate": 1.5,
        },
    ]
    out = check_qibao(details, picked_block, [], "2026-04-25")
    assert [(s["mode"], s["code"]) for s in out] == [("方向红盘起爆", "001.XSHE")]


def test_pick_big_ones_skips_none_entries() -> None:
    # Some upstream endpoints return list values that include None gaps when
    # the response was a dict whose values include nulls. The picker must not
    # crash on those. (Regression: 2026-04-26 5-month backtest hit AttributeError
    # because category_rank had None entries.)
    items = [None, {"num": 100}, None, {"num": 95}, None]
    out = pick_big_ones(items, upper_num=3)
    assert [item["num"] for item in out] == [100, 95]


def test_strategy_open_pct_high_marked_shadow_not_dropped() -> None:
    rows = [
        {"code": "keep-missing"},
        {"code": "keep-low", "openPctChange": 5.99},
        {"code": "shadow-six", "openPctChange": 6.0},
        {"code": "shadow-high", "openPctChange": 8.5},
    ]
    out = _filter_open_pct(rows)
    # All rows preserved, including high opens — they're now shadow.
    assert [row["code"] for row in out] == [
        "keep-missing", "keep-low", "shadow-six", "shadow-high",
    ]
    by_code = {r["code"]: r for r in out}
    # Low / missing rows are not touched.
    assert "adaptive_active" not in by_code["keep-missing"]
    assert "adaptive_active" not in by_code["keep-low"]
    # High-open rows are marked shadow with a reason.
    assert by_code["shadow-six"]["adaptive_active"] is False
    assert "openPctChange" in by_code["shadow-six"]["adaptive_reason"]
    assert by_code["shadow-high"]["adaptive_active"] is False


class _FakeSource:
    """Records every sort_codes invocation so tests can assert sort_id usage."""

    def __init__(self, codes_per_direction: dict[Any, list[str]] | None = None) -> None:
        self.sort_calls: list[tuple[str, list[str], Any]] = []
        self.codes_per_direction = codes_per_direction or {}

    def get_industry_block_rank(self, date: str, model: int) -> list[dict[str, Any]]:
        return [
            {"blockCode": "BK001", "blockName": "新能源", "num": 100, "value": 100},
            {"blockCode": "BK002", "blockName": "AI", "num": 80, "value": 80},
        ]

    def get_block_category_rank(self, date: str, model: int) -> list[dict[str, Any]]:
        return []

    def get_pool(self, date: str, group: str) -> list[str]:
        return []

    def get_stock_index(self, date: str, codes: list[str]) -> list[dict[str, Any]]:
        return []

    def sort_codes(self, date: str, codes: list[str], sort_id: Any, **_: Any) -> list[str]:
        self.sort_calls.append((date, list(codes), sort_id))
        return list(codes)

    def get_direction_codes(self, date: str, block_code: str | None = None, category_code: str | None = None) -> list[str]:
        return self.codes_per_direction.get(block_code or category_code, [])


def test_direction_sort_uses_direction_cjs_by_default() -> None:
    source = _FakeSource({"BK001": ["A", "B"], "BK002": ["C"]})

    run_strategy("2026-04-25", source, modes={"direction"})

    direction_sort_ids = [call[2] for call in source.sort_calls]
    assert "directionCjs" in direction_sort_ids


def test_max_per_direction_caps_codes_per_direction() -> None:
    captured: list[list[str]] = []

    class _CappedSource(_FakeSource):
        def get_stock_index(self, date: str, codes: list[str]) -> list[dict[str, Any]]:
            captured.append(list(codes))
            return []

    source = _CappedSource({"BK001": ["A", "B", "C", "D", "E", "F"], "BK002": ["X", "Y", "Z"]})

    run_strategy("2026-04-25", source, modes={"direction"}, max_per_direction=2)

    assert all(len(group) <= 2 for group in captured)


def test_pool_sort_key_overrides_default_38() -> None:
    source = _FakeSource()

    run_strategy("2026-04-25", source, modes={"jieli", "dixi"}, pool_sort_key="xiaocaoCJS")

    pool_sort_ids = [call[2] for call in source.sort_calls]
    assert pool_sort_ids and all(sid == "xiaocaoCJS" for sid in pool_sort_ids)


def test_profile_default_resolves_to_direction_cjs() -> None:
    preset = STRATEGY_PROFILES["default"]
    assert preset["direction_sort_key"] == "directionCjs"


def test_profile_validated_v2_includes_off_main_line_and_excludes_two_modes() -> None:
    preset = STRATEGY_PROFILES["validated_v2"]
    assert preset["exclude_main_line"] is True
    assert set(preset["exclude_modes"]) == {"接力低弱转2", "方向内绿盘低吸前3名"}


def test_profile_validated_v3_present_and_inherits_v2_structure() -> None:
    preset = STRATEGY_PROFILES["validated_v3"]
    # v3 = v2 structurally; the v3 magic happens in adaptive when state is
    # available, NOT in the profile dict itself.
    assert preset["exclude_main_line"] is True
    assert set(preset["exclude_modes"]) == {"接力低弱转2", "方向内绿盘低吸前3名"}


def test_state_for_date_returns_neutral_when_cache_lacks_klines(tmp_path) -> None:
    from xiaocao.api.cache import SQLiteCache
    from xiaocao.strategy.runner import _state_for_date

    cache = SQLiteCache(tmp_path / "empty.db")
    state = _state_for_date("2026-04-25", cache)
    # Empty cache → neutral state
    assert state is not None
    assert state.reward == 0.5 and state.risk == 0.5


def test_profile_unknown_raises() -> None:
    source = _FakeSource()
    with pytest.raises(ValueError, match="Unknown strategy profile"):
        run_strategy("2026-04-25", source, profile="nonexistent")


def test_dedupe_collapses_same_date_code_across_modes() -> None:
    rows = [
        {"date": "2026-03-10", "code": "001339.XSHE", "mode": "接力低弱转1", "score": 1},
        {"date": "2026-03-10", "code": "001339.XSHE", "mode": "接力低弱转2", "score": 2},
        {"date": "2026-03-10", "code": "002667.XSHE", "mode": "接力低弱转2", "score": 3},
    ]
    out = _dedupe_signals(rows)
    assert len(out) == 2  # 001339.XSHE collapsed, 002667 stays
    by_code = {r["code"]: r for r in out}
    kept = by_code["001339.XSHE"]
    assert kept["mode"] == "接力低弱转1"  # first wins
    assert kept["dropped_modes"] == ["接力低弱转2"]
    assert kept["score"] == 1  # first occurrence's other fields preserved
    assert "dropped_modes" not in by_code["002667.XSHE"]  # no duplicates -> field absent


def test_dedupe_preserves_input_order() -> None:
    rows = [
        {"date": "D", "code": "B", "mode": "x"},
        {"date": "D", "code": "A", "mode": "y"},
        {"date": "D", "code": "B", "mode": "z"},
    ]
    out = _dedupe_signals(rows)
    assert [r["code"] for r in out] == ["B", "A"]


class _ModeStubSource(_FakeSource):
    """Source that produces one direction with stubbed details to test mode-level filters."""

    def __init__(self, fake_signal_rows: list[dict[str, Any]]) -> None:
        super().__init__({"BK001": ["A", "B"]})
        self._rows = fake_signal_rows
        # Strategy-runner expects rules.check_direction_dixi to be called with details and to return rows.
        # Easiest path: monkeypatch nothing — instead let the fake source's get_stock_index
        # return our stub rows directly, and override get_industry_block_rank to provide one direction.
        self.calls = self.sort_calls

    def get_stock_index(self, date: str, codes: list[str]) -> list[dict[str, Any]]:
        return list(self._rows)


def test_annotate_signals_with_regime_mainline_bigcap(monkeypatch) -> None:
    from xiaocao.strategy import runner as runner_module

    def stub_check_direction_dixi(details, picked_block, picked_category, date, **_):
        return [
            {
                "date": date,
                "code": "300750.XSHE",
                "mode": "方向内绿盘低吸前3名",
                "openPctChange": 1.0,
                "blockCodeList": ["BK_AI", "BK_NEV"],
            },
            {
                "date": date,
                "code": "002001.XSHE",
                "mode": "方向内绿盘低吸前3名",
                "openPctChange": 1.0,
                "blockCodeList": ["BK_OTHER"],
            },
        ]

    monkeypatch.setattr(runner_module, "check_direction_dixi", stub_check_direction_dixi)
    source = _ModeStubSource(fake_signal_rows=[{"code": "X"}])

    rows = run_strategy(
        "2026-04-25",
        source,
        modes={"direction"},
        regime="trend_continuing",
        mainline_blocks={"BK_AI"},
        bigcap_codes={"300750.XSHE"},
    )
    by_code = {r["code"]: r for r in rows}

    big = by_code["300750.XSHE"]
    assert big["regime"] == "trend_continuing"
    assert big["is_main_line"] is True
    assert big["is_big_cap"] is True

    small = by_code["002001.XSHE"]
    assert small["is_main_line"] is False
    assert small["is_big_cap"] is False


def test_regime_gate_drops_modes_not_allowed(monkeypatch) -> None:
    from xiaocao.strategy import runner as runner_module

    def stub_check_direction_dixi(details, picked_block, picked_category, date, **_):
        return [
            {"date": date, "code": "A", "mode": "接力低弱转2", "openPctChange": 1.0},
            {"date": date, "code": "B", "mode": "首红断低吸", "openPctChange": 1.0},
        ]

    monkeypatch.setattr(runner_module, "check_direction_dixi", stub_check_direction_dixi)
    source = _ModeStubSource(fake_signal_rows=[{"code": "X"}])

    # In `recovery` regime: 接力低弱转2's risk-floor precondition passes (risk
    # 0.55 ≥ 0.45) but state-fitness for 接力低弱转2 is just barely; meanwhile
    # 首红断低吸's duan_ban_recovery precondition passes (recovery prototype
    # DBR=0.55 ≥ 0.55) and its alignment is solidly positive.
    # NOTE this test is brittle to prototype-value tweaks; it asserts the
    # legacy gate respects fitness-based scoring, not absolute mode names.
    rows = run_strategy(
        "2026-04-25",
        source,
        modes={"direction"},
        regime="bear",  # bear blocks both: 接力2 risk-precondition + 首红断低吸 DBR-precondition
        regime_gate=True,
    )
    # Both modes blocked under bear; verify by checking mode set is empty subset
    modes_kept = {r["mode"] for r in rows}
    assert "接力低弱转2" not in modes_kept
    # 首红断低吸 also blocked in bear: DBR precondition fails (bear DBR=0.30 < 0.55)
    assert "首红断低吸" not in modes_kept


def test_require_main_line_drops_off_main_line(monkeypatch) -> None:
    from xiaocao.strategy import runner as runner_module

    def stub(details, picked_block, picked_category, date, **_):
        return [
            {"date": date, "code": "ON", "mode": "首红断低吸", "openPctChange": 0.5,
             "blockCodeList": ["BK_AI"]},
            {"date": date, "code": "OFF", "mode": "首红断低吸", "openPctChange": 0.5,
             "blockCodeList": ["BK_OTHER"]},
        ]

    monkeypatch.setattr(runner_module, "check_direction_dixi", stub)
    source = _ModeStubSource(fake_signal_rows=[{"code": "X"}])

    rows = run_strategy(
        "2026-04-25",
        source,
        modes={"direction"},
        mainline_blocks={"BK_AI"},
        require_main_line=True,
    )
    assert {r["code"] for r in rows} == {"ON"}


def test_max_open_pct_override_marks_shadow(monkeypatch) -> None:
    from xiaocao.strategy import runner as runner_module

    def stub(details, picked_block, picked_category, date, **_):
        return [
            {"date": date, "code": "A", "mode": "首红断低吸", "openPctChange": 1.0},
            {"date": date, "code": "B", "mode": "首红断低吸", "openPctChange": 3.5},
            {"date": date, "code": "C", "mode": "首红断低吸", "openPctChange": 5.5},
        ]

    monkeypatch.setattr(runner_module, "check_direction_dixi", stub)
    source = _ModeStubSource(fake_signal_rows=[{"code": "X"}])

    # Default cap (6.0): all three are below cap → no shadow tagging
    rows = run_strategy("2026-04-25", source, modes={"direction"})
    by_code = {r["code"]: r for r in rows}
    assert set(by_code) == {"A", "B", "C"}
    assert all("adaptive_active" not in r for r in rows)

    # Tightened cap of 3: A stays clean; B (3.5%) and C (5.5%) become shadow
    # but are NOT dropped — they remain in the output for reference / shadow P&L.
    rows = run_strategy("2026-04-25", source, modes={"direction"}, max_open_pct=3.0)
    by_code = {r["code"]: r for r in rows}
    assert set(by_code) == {"A", "B", "C"}
    assert "adaptive_active" not in by_code["A"]
    assert by_code["B"]["adaptive_active"] is False
    assert by_code["C"]["adaptive_active"] is False


def test_classify_regime_called_when_only_overview_passed(monkeypatch) -> None:
    from xiaocao.strategy import runner as runner_module

    def stub(details, picked_block, picked_category, date, **_):
        return [{"date": date, "code": "A", "mode": "首红断低吸", "openPctChange": 1.0}]

    monkeypatch.setattr(runner_module, "check_direction_dixi", stub)
    source = _ModeStubSource(fake_signal_rows=[{"code": "X"}])

    overview = {
        "positiveLevelOne": 2000, "positiveLevelTwo": 500, "positiveLevelSeven": 35,
        "negativeLevelOne": 800,
    }
    rows = run_strategy("2026-04-25", source, modes={"direction"}, market_overview=overview)
    assert rows[0]["regime"] == "trend_strong"


def test_exclude_modes_marks_shadow_not_drop(monkeypatch) -> None:
    from xiaocao.strategy import runner as runner_module

    def stub_check_direction_dixi(details, picked_block, picked_category, date, **_):
        return [
            {"date": date, "code": "X", "mode": "接力低弱转1", "openPctChange": 1.0},
            {"date": date, "code": "Y", "mode": "接力低弱转2", "openPctChange": 1.0},
        ]

    monkeypatch.setattr(runner_module, "check_direction_dixi", stub_check_direction_dixi)
    source = _ModeStubSource(fake_signal_rows=[{"code": "A"}])

    rows = run_strategy(
        "2026-04-25",
        source,
        modes={"direction"},
        exclude_modes={"接力低弱转2"},
    )
    by_code = {r["code"]: r for r in rows}
    # Both modes' signals stay in the output — excluded mode is shadow only
    assert set(by_code) == {"X", "Y"}
    assert "adaptive_active" not in by_code["X"]
    assert by_code["Y"]["adaptive_active"] is False
    assert "exclude" in by_code["Y"]["adaptive_reason"]
