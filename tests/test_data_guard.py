from __future__ import annotations

from xiaocao.research import data_guard as dg


def test_data_valid_floor_catches_zero_padding():
    # 2023 all-zero (the concept-returns trap), real data from 2024
    recs = ([{"day": f"2023-01-{i:02d}", "ret": 0.0} for i in range(1, 6)]
            + [{"day": f"2024-05-{i:02d}", "ret": 1.5} for i in range(13, 18)])
    f = dg.data_valid_floor(recs, "ret")
    assert f["coverage_is_data"] is False
    assert f["valid_range"][0].startswith("2024-05")
    assert f["span"][0].startswith("2023-01")
    assert f["n_zero_or_null"] == 5


def test_data_valid_floor_clean_data():
    recs = [{"day": f"2025-01-{i:02d}", "ret": 0.3 * i} for i in range(1, 6)]
    f = dg.data_valid_floor(recs, "ret")
    assert f["coverage_is_data"] is True
    assert f["n_zero_or_null"] == 0


def test_trailing_excludes_current_by_default():
    vals = [10, 20, 30, 40, 50]
    assert dg.trailing(vals, 3, 2) == [20, 30]          # i-2, i-1 (not i)
    assert dg.trailing(vals, 3, 2, include_current=True) == [30, 40]
    assert dg.trailing(vals, 0, 5) == []                 # nothing before index 0
    assert dg.trailing(vals, 2, 10) == [10, 20]          # clamps at 0


def test_looks_like_realized_pnl_flags_right_skew():
    # mode_history-like: mean positive, median negative
    pnl = [-2, -1, -3, -1, -2, -1, 66, -2, -1, 30, -1, -2]
    r = dg.looks_like_realized_pnl(pnl)
    assert r["suspect_realized_pnl"] is True
    assert r["mean"] > 0 and r["median"] < 0


def test_looks_like_realized_pnl_clean_price_series():
    px = [0.5, -0.3, 0.4, -0.2, 0.6, -0.1, 0.3, -0.4, 0.2, 0.1]
    assert dg.looks_like_realized_pnl(px)["suspect_realized_pnl"] is False


def test_staleness():
    recs = [{"day": "2026-05-29", "v": 1}]
    assert dg.staleness(recs, "2026-06-22", max_lag_days=10)["stale"] is True
    assert dg.staleness(recs, "2026-06-02", max_lag_days=10)["stale"] is False


def test_audit_fail_closed_on_zero_padding_and_stale():
    recs = ([{"day": f"2023-01-{i:02d}", "ret": 0.0} for i in range(1, 9)]
            + [{"day": f"2024-05-{i:02d}", "ret": 1.0} for i in range(13, 16)])
    rep = dg.audit(recs, "ret")
    assert rep["ok"] is False                # >10% zero dates => critical
    assert any("data-valid range" in w for w in rep["warnings"])


def test_audit_clean_passes():
    recs = [{"day": f"2025-0{m}-01", "ret": 0.5} for m in range(1, 6)]
    rep = dg.audit(recs, "ret", today="2025-05-05", max_lag_days=40)
    assert rep["ok"] is True
    assert rep["warnings"] == []
