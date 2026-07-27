from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pandas")  # capture_signals pulls pandas transitively; skip (not error) if absent

from kronos_screen.scripts.capture_signals import _replace_day_rows, capture  # noqa: E402


class FakeAuctionClient:
    """stock_call_auction returning a configurable 9:25 snapshot per code."""

    def __init__(self, rows_by_code: dict[str, dict]):
        self.rows_by_code = rows_by_code

    def stock_call_auction(self, code: str, date_iso: str):
        row = self.rows_by_code.get(code)
        return [row] if row else []


def _auction_row(pct: float, buy_residual: float, vol: float = 1000.0) -> dict:
    return {
        "tradeTimestamp": "092500",
        "tradeDate": "20260612",
        "pctChangeRate": pct,
        "vol": vol,
        "buyVol2": buy_residual * vol,
        "sellVol2": 0.0,
        "trade": 10.0,
        "tradeStatus": "T",
    }


def _cand(code: str, p_score: float, kp_star: bool, *, mode: str = "绿断低吸", rank_score: float = 47.0) -> dict:
    return {
        "code": code, "name": code[:6], "mode": mode,
        "xcjw": 200.0, "cjs": 0.0, "jsjl": 0.0,
        "rank_score": rank_score, "mode_confidence": 55.0,
        "p_score": p_score, "k_score": 0.5,
        "kp_keep": True, "kp_rank": 0, "kp_star": kp_star,
        "mode_state": "ACTIVE", "mode_trade_eligible": True,
        "open": 10.0,
    }


def test_forced_contrast_swaps_auction_worst_pick(tmp_path: Path) -> None:
    # A picks: c1, c2, c3 (by P). c3 has the worst auction quality; c4 (non-A)
    # has better auction quality -> B = {c1, c2, c4}.
    cands = [
        _cand("C1.XSHE", 3.0, True),
        _cand("C2.XSHE", 2.0, True),
        _cand("C3.XSHE", 1.0, True),
        _cand("C4.XSHE", 0.5, False),
    ]
    client = FakeAuctionClient({
        "C1.XSHE": _auction_row(pct=-1.0, buy_residual=0.8),
        "C2.XSHE": _auction_row(pct=-2.0, buy_residual=0.6),
        "C3.XSHE": _auction_row(pct=-9.0, buy_residual=0.01),
        "C4.XSHE": _auction_row(pct=-0.5, buy_residual=0.9),
    })
    out = tmp_path / "snap.jsonl"
    capture(cands, client, "2026-06-12", is_live=True, top_n=3, out=out)

    b_codes = {c["code"] for c in cands if c["vb_star"]}
    assert b_codes == {"C1.XSHE", "C2.XSHE", "C4.XSHE"}
    a_codes = {c["code"] for c in cands if c["kp_star"]}
    assert a_codes != b_codes  # forced contrast achieved
    assert all(c.get("vb_swap") for c in cands if c.get("kp_keep"))


def test_no_swap_when_replacement_auction_is_worse(tmp_path: Path) -> None:
    cands = [
        _cand("C1.XSHE", 3.0, True),
        _cand("C2.XSHE", 2.0, True),
        _cand("C3.XSHE", 1.0, True),
        _cand("C4.XSHE", 0.5, False),
    ]
    client = FakeAuctionClient({
        "C1.XSHE": _auction_row(pct=-1.0, buy_residual=0.8),
        "C2.XSHE": _auction_row(pct=-2.0, buy_residual=0.6),
        "C3.XSHE": _auction_row(pct=-3.0, buy_residual=0.5),
        "C4.XSHE": _auction_row(pct=-9.0, buy_residual=0.01),  # worst auction
    })
    out = tmp_path / "snap.jsonl"
    capture(cands, client, "2026-06-12", is_live=True, top_n=3, out=out)

    b_codes = {c["code"] for c in cands if c["vb_star"]}
    assert b_codes == {"C1.XSHE", "C2.XSHE", "C3.XSHE"}  # B == A, no forced swap
    assert not any(c.get("vb_swap") for c in cands)


def test_mode_star_ranks_k_survivors_by_mode_aware_rank_score(tmp_path: Path) -> None:
    cands = [
        _cand("C1.XSHE", 3.0, True, mode="首红断低吸", rank_score=40.0),
        _cand("C2.XSHE", 2.0, True, mode="首红断低吸", rank_score=90.0),
        _cand("C3.XSHE", 1.0, True, mode="首红断低吸", rank_score=80.0),
        _cand("C4.XSHE", 0.5, False, mode="N字低吸", rank_score=70.0),
    ]
    client = FakeAuctionClient({
        "C1.XSHE": _auction_row(pct=-1.0, buy_residual=0.8),
        "C2.XSHE": _auction_row(pct=-2.0, buy_residual=0.6),
        "C3.XSHE": _auction_row(pct=-3.0, buy_residual=0.5),
        "C4.XSHE": _auction_row(pct=-4.0, buy_residual=0.4),
    })
    out = tmp_path / "snap.jsonl"

    capture(cands, client, "2026-06-12", is_live=True, top_n=3, out=out)

    m_codes = {c["code"] for c in cands if c["mode_star"]}
    assert m_codes == {"C2.XSHE", "C3.XSHE", "C4.XSHE"}
    ranks = {c["code"]: c["mode_rank"] for c in cands if c["mode_star"]}
    assert ranks == {"C2.XSHE": 1, "C3.XSHE": 2, "C4.XSHE": 3}


def test_mode_exec_applies_mode_permission_before_soft_rank(tmp_path: Path) -> None:
    cands = [
        _cand("COLD.XSHE", 9.0, True, mode="首红断低吸", rank_score=999.0),
        _cand("A1.XSHE", 3.0, True, mode="接力低弱转1", rank_score=90.0),
        _cand("A2.XSHE", 2.0, True, mode="接力低弱转1", rank_score=80.0),
        _cand("A3.XSHE", 1.0, True, mode="接力低弱转1", rank_score=70.0),
    ]
    cands[0].update({"mode_state": "COLD", "mode_trade_eligible": False})
    client = FakeAuctionClient({row["code"]: _auction_row(-1.0, 0.5) for row in cands})

    capture(cands, client, "2026-06-12", is_live=True, top_n=3, out=tmp_path / "snap.jsonl")

    selected = {row["code"] for row in cands if row["mode_exec_star"]}
    assert selected == {"A1.XSHE"}
    assert cands[0]["mode_exec_star"] is False


def test_replace_day_rows_is_idempotent_per_day(tmp_path: Path) -> None:
    out = tmp_path / "snap.jsonl"
    old = [json.dumps({"date": "2026-06-11", "is_live": True, "code": "X"}),
           json.dumps({"date": "2026-06-12", "is_live": True, "code": "STALE"})]
    out.write_text("\n".join(old) + "\n", encoding="utf-8")

    new = [json.dumps({"date": "2026-06-12", "is_live": True, "code": "FRESH"})]
    _replace_day_rows(out, "2026-06-12", True, new)

    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    codes = {(r["date"], r["code"]) for r in rows}
    assert ("2026-06-12", "STALE") not in codes
    assert ("2026-06-12", "FRESH") in codes
    assert ("2026-06-11", "X") in codes  # other days untouched


def test_capture_rewrite_replaces_same_day_duplicates(tmp_path: Path) -> None:
    out = tmp_path / "snap.jsonl"
    client = FakeAuctionClient({"C1.XSHE": _auction_row(pct=-1.0, buy_residual=0.5)})
    for _ in range(3):  # re-running the same morning must not accumulate rows
        cands = [_cand("C1.XSHE", 1.0, True)]
        capture(cands, client, "2026-06-12", is_live=True, top_n=3, out=out)

    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["book"] == "B"


def test_capture_rewrite_is_book_scoped(tmp_path: Path) -> None:
    out = tmp_path / "snap.jsonl"
    old = [
        json.dumps({"date": "2026-06-12", "book": "T", "is_live": True, "code": "TREND"}),
        json.dumps({"date": "2026-06-12", "book": "B", "is_live": True, "code": "STALE"}),
    ]
    out.write_text("\n".join(old) + "\n", encoding="utf-8")
    new = [json.dumps({"date": "2026-06-12", "book": "B", "is_live": True, "code": "FRESH"})]

    _replace_day_rows(out, "2026-06-12", True, new, book="B")

    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    keys = {(r["book"], r["code"]) for r in rows}
    assert ("T", "TREND") in keys
    assert ("B", "STALE") not in keys
    assert ("B", "FRESH") in keys


def test_capture_snapshot_includes_quality_fields(tmp_path: Path) -> None:
    out = tmp_path / "snap.jsonl"
    client = FakeAuctionClient({"C1.XSHE": _auction_row(pct=-1.0, buy_residual=0.5)})
    cands = [_cand("C1.XSHE", 1.0, True)]

    capture(cands, client, "2026-06-12", is_live=True, top_n=3, out=out)

    [row] = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert row["primary_score"] == 200.0
    assert row["primary_score_label"] == "xcjw+0.8*cjs"
    assert row["rank_score"] == 47.0
    assert row["mode_confidence"] == 55.0
    assert row["quality_tag"] == "normal"
    assert row["mode_star"] is True
    assert row["mode_rank"] == 1
    assert row["mode_score"] == 47.0
    assert row["mode_exec_star"] is True
    assert row["mode_state"] == "ACTIVE"
    assert row["mode_exec_rank_score"] == pytest.approx(row["rank_score"])
    assert row["mode_exec_target_weight"] == pytest.approx(0.50)


def test_capture_snapshot_preserves_qibao_benchmark_fields(tmp_path: Path) -> None:
    out = tmp_path / "snap.jsonl"
    client = FakeAuctionClient({"C1.XSHE": _auction_row(pct=7.0, buy_residual=0.5)})
    c = _cand("C1.XSHE", 1.0, True, mode="高开标杆起爆")
    c.update({
        "rawQibaoRank": 2,
        "qibaoRankScore": 228.0,
        "qibaoBenchmarkKind": "raw_top10_elec20_high_open_6_10",
        "qibaoBenchmarkLayer": "paper_buy",
        "industryElectronic": True,
        "board20": True,
    })

    capture([c], client, "2026-06-12", is_live=True, top_n=3, out=out)

    [row] = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert row["rawQibaoRank"] == 2
    assert row["qibaoRankScore"] == 228.0
    assert row["qibaoBenchmarkKind"] == "raw_top10_elec20_high_open_6_10"
    assert row["qibaoBenchmarkLayer"] == "paper_buy"
    assert row["industryElectronic"] is True
    assert row["board20"] is True


def test_capture_snapshot_preserves_trend_context_fields(tmp_path: Path) -> None:
    out = tmp_path / "snap.jsonl"
    client = FakeAuctionClient({"C1.XSHE": _auction_row(pct=1.0, buy_residual=0.5)})
    c = _cand("C1.XSHE", 1.0, True)
    c.update({
        "is_main_line": True,
        "is_big_cap": True,
        "direction": True,
        "direction_rank": 0,
        "category_rank": 1,
        "regime": "trend_continuing",
        "macro_focus_score": 100.0,
        "macro_focus_reason": "block r0",
        "open_risk_penalty": 0.0,
        "reason": "trend context fixture",
        "excIndustryCode": "T08.ZHBK",
        "blockCodeList": "B1",
        "blockCategoryCodeList": "C1",
    })

    capture([c], client, "2026-06-12", is_live=True, top_n=3, out=out)

    [row] = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert row["is_main_line"] is True
    assert row["is_big_cap"] is True
    assert row["direction"] is True
    assert row["direction_rank"] == 0
    assert row["category_rank"] == 1
    assert row["regime"] == "trend_continuing"
    assert row["macro_focus_score"] == 100.0
    assert row["macro_focus_reason"] == "block r0"
    assert row["reason"] == "trend context fixture"
