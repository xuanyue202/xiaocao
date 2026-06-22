"""Tests for the calibration distill bridge (xiaocao.research.calibration_distill):
flag systematically-wrong groups over a min-n floor, and stage candidates idempotently."""
from __future__ import annotations

import json

from xiaocao.research import calibration_distill as cd


def _scored(pairs):
    """pairs: list of (key, right) -> scored records with that group key + outcome."""
    return [{"grp": k, "right": r} for k, r in pairs]


def test_flagged_returns_only_wrong_groups_over_min_n():
    scored = _scored(
        [("bad", False)] * 7 + [("bad", True)] * 1          # 1/8 = 12% over n=8  -> flagged
        + [("good", True)] * 9 + [("good", False)] * 1      # 9/10 = 90%          -> not
        + [("small", False)] * 3                            # 0/3 but n<8         -> not
    )
    flags = cd.flagged(scored, key=lambda s: s["grp"], min_n=8)
    keys = {f["key"] for f in flags}
    assert keys == {"bad"}
    bad = flags[0]
    assert bad["hit"] == 1 and bad["n"] == 8 and bad["rate"] == 0.125


def test_flagged_skips_none_key_and_open_windows():
    scored = (_scored([("x", False)] * 10)
              + [{"grp": "x", "right": None}]      # open window — ignored
              + [{"grp": None, "right": False}] * 10)  # key None — skipped
    flags = cd.flagged(scored, key=lambda s: s["grp"], min_n=8)
    assert [f["key"] for f in flags] == ["x"]
    assert flags[0]["n"] == 10   # the None-right record did not inflate n


def test_flagged_threshold_boundary():
    # exactly 45% is NOT flagged (< 0.45 is the bar)
    scored = _scored([("e", True)] * 9 + [("e", False)] * 11)  # 9/20 = 0.45
    assert cd.flagged(scored, key=lambda s: s["grp"], min_n=8) == []
    scored2 = _scored([("e", True)] * 8 + [("e", False)] * 12)  # 8/20 = 0.40
    assert len(cd.flagged(scored2, key=lambda s: s["grp"], min_n=8)) == 1


def test_stage_is_idempotent(tmp_path):
    path = tmp_path / "calibration_candidates.jsonl"
    c1 = {"cand_key": "exit:sell:TRAILING_STOP", "claim": "..."}
    c2 = {"cand_key": "posture:defensive", "claim": "..."}
    assert cd.stage(path, [c1, c2]) == 2
    assert cd.stage(path, [c1, c2]) == 0          # already present -> no dup
    assert cd.stage(path, [c1, {"cand_key": "exit:hold:NEAR_LIMIT_UP"}]) == 1
    keys = [json.loads(l)["cand_key"] for l in path.read_text().splitlines() if l.strip()]
    assert keys == ["exit:sell:TRAILING_STOP", "posture:defensive", "exit:hold:NEAR_LIMIT_UP"]


def test_stage_handles_comment_lines(tmp_path):
    path = tmp_path / "calibration_candidates.jsonl"
    path.write_text("# header comment\n", encoding="utf-8")
    assert cd.stage(path, [{"cand_key": "k1"}]) == 1
    assert cd.stage(path, [{"cand_key": "k1"}]) == 0
