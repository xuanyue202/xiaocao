from __future__ import annotations

from xiaocao.strategy.runner import _filter_open_pct


def test_strategy_filters_open_pct_change_below_six() -> None:
    rows = [
        {"code": "keep-missing"},
        {"code": "keep-low", "openPctChange": 5.99},
        {"code": "drop-six", "openPctChange": 6.0},
        {"code": "drop-high", "openPctChange": 8.5},
    ]

    assert [row["code"] for row in _filter_open_pct(rows)] == ["keep-missing", "keep-low"]
