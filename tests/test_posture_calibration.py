from __future__ import annotations

import importlib.util
from pathlib import Path

# posture_calibration is a script (scripts/), load it by path
_spec = importlib.util.spec_from_file_location(
    "posture_calibration", Path(__file__).resolve().parents[1] / "scripts" / "posture_calibration.py")
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)


def test_score_call_aggressive():
    assert pc.score_call("aggressive", +0.5) is True   # participated, market rose
    assert pc.score_call("aggressive", -0.5) is False  # participated, market fell


def test_score_call_defensive():
    assert pc.score_call("defensive", -0.5) is True    # sat out, market fell (right)
    assert pc.score_call("defensive", +0.5) is False   # sat out, market rose (wrong)
    assert pc.score_call("defensive", 0.0) is True      # flat counts as avoided-loss


def test_score_call_neutral_and_none():
    assert pc.score_call("neutral", +0.5) is None      # no directional claim
    assert pc.score_call("aggressive", None) is None   # forward window not closed


def test_forward_return_is_strictly_future():
    days = ["d0", "d1", "d2", "d3", "d4"]
    daily = {"d0": 1.0, "d1": 2.0, "d2": 3.0, "d3": 4.0, "d4": 5.0}
    # from d1, horizon 2 -> mean of d2,d3 (NOT d1 itself)
    assert pc.forward_return(days, daily, "d1", 2) == 3.5
    # not enough future days -> None
    assert pc.forward_return(days, daily, "d4", 2) is None


def test_action_map_covers_regimes():
    for reg in ("bear", "trend_strong", "neutral", "trend_continuing", "divergence"):
        assert pc.ACTION[reg] in ("aggressive", "defensive", "neutral")
