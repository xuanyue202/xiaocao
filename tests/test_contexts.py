"""Direct unit tests for the extracted decision-context builders
(src/xiaocao/live/contexts.py). These feed the composite exit score and were
only covered indirectly before the extraction.
"""
from __future__ import annotations

import json

from xiaocao.live import contexts


def test_load_signal_snapshot_map_keeps_latest_per_key(tmp_path):
    p = tmp_path / "snaps.jsonl"
    p.write_text("\n".join([
        json.dumps({"date": "2026-06-19", "code": "A", "captured_at": "t1", "p_score": 0.1}),
        json.dumps({"date": "2026-06-19", "code": "A", "captured_at": "t2", "p_score": 0.9}),  # newer wins
        json.dumps({"date": "2026-06-19", "code": "B", "captured_at": "t1"}),
        "not json",
        json.dumps({"code": "", "date": ""}),  # skipped
    ]) + "\n", encoding="utf-8")
    m = contexts.load_signal_snapshot_map(p)
    assert set(m) == {("2026-06-19", "A", "B"), ("2026-06-19", "B", "B")}
    assert m[("2026-06-19", "A", "B")]["p_score"] == 0.9  # latest captured_at


def test_load_signal_snapshot_map_keeps_books_separate(tmp_path):
    p = tmp_path / "snaps.jsonl"
    p.write_text("\n".join([
        json.dumps({"date": "2026-06-19", "book": "B", "code": "A", "captured_at": "t1", "p_score": 0.1}),
        json.dumps({"date": "2026-06-19", "book": "T", "code": "A", "captured_at": "t1", "p_score": 9.9}),
    ]) + "\n", encoding="utf-8")
    m = contexts.load_signal_snapshot_map(p)
    assert m[("2026-06-19", "A", "B")]["p_score"] == 0.1
    assert m[("2026-06-19", "A", "T")]["p_score"] == 9.9


def test_load_signal_snapshot_map_missing_file(tmp_path):
    assert contexts.load_signal_snapshot_map(tmp_path / "none.jsonl") == {}


def test_kronos_context_combines_p_k_and_star_flags():
    snap = {("2026-06-19", "A", "B"): {"p_score": 3.0, "k_score": 3.0, "vb_star": True}}
    pos = {"book": "B", "code": "A", "entry_date": "2026-06-19"}
    ctx = contexts.kronos_context(pos, snap)
    # 0.6*clamp(1.0) + 0.2*clamp(1.0) + 0.2 (vb_star) = 1.0, clamped
    assert ctx["score"] == 1.0 and ctx["vb_star"] is True and ctx["p_score"] == 3.0


def test_kronos_context_falls_back_to_position_fields_and_kp_star():
    pos = {"code": "A", "entry_date": "2026-06-19", "p_score": 1.5, "kp_star": True}
    ctx = contexts.kronos_context(pos, {})  # no snapshot -> use position fields
    assert ctx["kp_star"] is True and ctx["vb_star"] is False
    assert ctx["score"] == round(0.6 * 0.5 + 0.1, 4)  # 0.6*clamp(0.5) + 0.1 (kp_star)


def test_kronos_context_neutral_when_no_scores():
    ctx = contexts.kronos_context({"code": "A", "entry_date": "2026-06-19"}, {})
    assert ctx["score"] == 0.0 and ctx["p_score"] is None and ctx["k_score"] is None


def test_stock_sentiment_context_blends_external_and_proxy():
    ctx = contexts.stock_sentiment_context(
        "A", smallgrass={"score": 0.5, "source": "smallgrass_proxy"},
        sentiment_map={"A": {"score": 1.0}},
    )
    assert ctx["score"] == round(0.7 * 1.0 + 0.3 * 0.5, 4) and ctx["source"] == "external+smallgrass"


def test_stock_sentiment_context_proxy_only_when_no_external():
    ctx = contexts.stock_sentiment_context(
        "A", smallgrass={"score": -0.3, "source": "smallgrass_proxy"}, sentiment_map={},
    )
    assert ctx["external_score"] is None and ctx["source"] == "smallgrass_proxy"
    assert ctx["proxy_score"] == -0.3
