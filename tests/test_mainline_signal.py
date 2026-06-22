from __future__ import annotations

from xiaocao.strategy import mainline_signal as ms


def _panel():
    # 3 concepts over 4 days. A trends up hardest, C is flat/down.
    days = ["d1", "d2", "d3", "d4"]
    ret = {
        "d1": {"A": 0.0, "B": 0.0, "C": 0.0},
        "d2": {"A": 2.0, "B": 1.0, "C": -1.0},
        "d3": {"A": 3.0, "B": 0.0, "C": -2.0},
        "d4": {"A": 1.0, "B": 1.0, "C": 0.0},
    }
    num = {  # A ranks top most days
        "d1": {"A": 10, "B": 5, "C": 1},
        "d2": {"A": 12, "B": 4, "C": 1},
        "d3": {"A": 11, "B": 6, "C": 2},
        "d4": {"A": 9, "B": 7, "C": 3},
    }
    return {"num": num, "ret": ret, "name": {"A": "AA", "B": "BB", "C": "CC"}, "days": days}


def test_cum_return_compounds_window():
    p = _panel()
    # (i0, i1] = days d2,d3 for A: (1.02 * 1.03 - 1) * 100
    got = ms.cum_return(p["ret"], p["days"], "A", 0, 2)
    assert abs(got - ((1.02 * 1.03) - 1) * 100) < 1e-9


def test_cum_return_none_on_bad_window_or_missing():
    p = _panel()
    assert ms.cum_return(p["ret"], p["days"], "A", 2, 2) is None  # i0 not < i1
    assert ms.cum_return(p["ret"], p["days"], "Z", 0, 2) is None  # missing concept


def test_trailing_strength_picks_strongest():
    p = _panel()
    a = ms.trailing_strength(p["ret"], p["days"], "A", 3, 3)
    c = ms.trailing_strength(p["ret"], p["days"], "C", 3, 3)
    assert a is not None and c is not None and a > c


def test_select_by_trend_strength_orders_by_trailing():
    p = _panel()
    picks = ms.select_by_trend_strength(p, 3, L=3, M=2)
    assert picks[0] == "A"  # strongest trailing trend
    assert set(picks) == {"A", "B"}  # top-2, C excluded


def test_select_by_trend_strength_empty_when_no_history():
    p = _panel()
    assert ms.select_by_trend_strength(p, 1, L=3, M=2) == []  # i < L


def test_rotation_frequency_counts_top_k_persistence():
    p = _panel()
    freq = ms.rotation_frequency(p["num"], p["days"], 3, W=4, K=1)
    assert freq["A"] == 1.0  # A is top-1 on all 4 days
    assert "C" not in freq  # never top-1


def test_select_by_rotation_freq_prefers_persistent():
    p = _panel()
    picks = ms.select_by_rotation_freq(p, 3, W=4, K=2, M=1)
    assert picks == ["A"]
