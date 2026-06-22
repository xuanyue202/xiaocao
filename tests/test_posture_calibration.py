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


# --- stance axis (#4): finer than action, so a TRIM isn't mislabeled aggressive ---

def test_score_stance_directions():
    assert pc.score_stance("participate", +0.5) is True   # long, market rose
    assert pc.score_stance("participate", -0.5) is False
    assert pc.score_stance("trim", -0.5) is True           # reduced, market fell -> right
    assert pc.score_stance("trim", +0.5) is False          # reduced, market ROSE -> 减飞
    assert pc.score_stance("sit_out", 0.0) is True         # flat = avoided-loss
    assert pc.score_stance("exit", -0.2) is True
    assert pc.score_stance("neutral", +0.5) is None
    assert pc.score_stance("trim", None) is None           # forward window not closed


def test_stance_of_distinguishes_trim_from_participate():
    # the 6/22 case: trend_continuing regime BUT 减仓一半 -> stance must be 'trim', not 'participate'
    trim = {"posture": "trend_continuing", "dominant_style": "趋势大票为底仓但已减一半、不加仓",
            "risk": "今日因反向板块主动引领而减一半", "stage": "减仓段已开始"}
    assert pc.stance_of(trim) == "trim"
    # a plain trend_continuing with no reduce-language -> participate (via ACTION fallback)
    assert pc.stance_of({"posture": "trend_continuing"}) == "participate"
    # explicit stance wins; defensive/空仓 -> sit_out
    assert pc.stance_of({"stance": "exit"}) == "exit"
    assert pc.stance_of({"posture": "bear", "risk": "空仓"}) == "sit_out"
    assert pc.stance_of({"posture": "divergence"}) == "sit_out"   # defensive -> sit_out fallback


def test_trim_scored_separately_not_as_aggressive():
    # a trim day where the market then ROSE: coarse action (aggressive) would call it 'right',
    # but the finer stance (trim) correctly calls it wrong (减飞) — they must diverge.
    call = {"action": "aggressive", "stance": "trim", "fwd_ret": +0.8}
    assert pc.score_call(call["action"], call["fwd_ret"]) is True       # coarse: looks right
    assert pc.score_stance(call["stance"], call["fwd_ret"]) is False    # fine: actually 减飞
