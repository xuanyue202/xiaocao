"""Tests for strategy explain layer (Plan A7)."""
from __future__ import annotations

from xiaocao.strategy.explain import explain_rows, explain_signal
from xiaocao.strategy.state import StateVector


def _state(reward=0.5, risk=0.5, continuity=0.5, dbr=0.5, momentum=0.5, lu=0.0):
    return StateVector(
        reward=reward, risk=risk, continuity=continuity,
        duan_ban_recovery=dbr, momentum=momentum, limitup_density=lu,
    )


def test_explain_signal_includes_mode_and_state() -> None:
    row = {"code": "002347.XSHE", "mode": "绿断低吸",
           "adaptive_active": True, "adaptive_reason": "fitness +0.32"}
    out = explain_signal(row, _state(risk=0.4))
    assert "002347.XSHE" in out
    assert "绿断低吸" in out
    assert "ACTIVE" in out
    assert "risk=0.400" in out


def test_explain_signal_with_unknown_mode() -> None:
    row = {"code": "001234.XSHE", "mode": "unknown_mode",
           "adaptive_active": False}
    out = explain_signal(row, _state())
    assert "unknown_mode" in out
    assert "unknown mode" in out
    assert "SHADOW" in out


def test_explain_signal_precondition_fail_marked() -> None:
    """绿断低吸 has precondition dbr ≥ 0.55. With dbr=0.4 → PRECONDITION_FAIL."""
    row = {"code": "X.XSHE", "mode": "绿断低吸"}
    out = explain_signal(row, _state(dbr=0.4))
    assert "PRECONDITION_FAIL" in out


def test_explain_signal_axes_align_displayed() -> None:
    """Each profile axis ('reward', 'risk', 'continuity') has an align line."""
    row = {"code": "X.XSHE", "mode": "接力低弱转1"}  # all wants high
    out = explain_signal(row, _state(reward=0.7, risk=0.7, continuity=0.7))
    assert "per-axis align" in out
    assert "reward" in out
    assert "risk" in out
    assert "continuity" in out


def test_explain_rows_groups_active_vs_shadow() -> None:
    rows = [
        {"code": "A.XSHE", "mode": "绿断低吸", "adaptive_active": True},
        {"code": "B.XSHE", "mode": "绿断低吸", "adaptive_active": False},
        {"code": "C.XSHE", "mode": "绿断低吸"},  # untagged
    ]
    out = explain_rows(rows, _state(dbr=0.6), date="2026-04-23")
    assert "ACTIVE: 1" in out
    assert "SHADOW: 1" in out
    assert "UNTAGGED: 1" in out
    assert "## ACTIVE signals" in out
    assert "## SHADOW signals" in out


def test_explain_rows_state_summary_inferences() -> None:
    """High momentum + high continuity should mention bull week + main-line."""
    rows = []
    state = _state(momentum=0.85, continuity=0.7)
    out = explain_rows(rows, state, date="2026-04-23")
    assert "bull week" in out
    assert "主线延续" in out


def test_explain_rows_handles_no_state() -> None:
    """When state is None (e.g., date missing from cache), still renders."""
    rows = [{"code": "A.XSHE", "mode": "绿断低吸"}]
    out = explain_rows(rows, None, date="2026-04-23")
    assert "(unavailable)" in out
