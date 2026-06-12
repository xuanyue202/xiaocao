from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_live_recommend():
    root = Path(__file__).resolve().parent.parent
    path = root / "scripts" / "live_recommend.py"
    spec = importlib.util.spec_from_file_location("live_recommend_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_headline_sentiment_summary_and_label():
    mod = _load_live_recommend()
    headlines = [
        {"title": "某公司签约大单并获批新项目"},
        {"title": "主力资金净买入"},
    ]
    score = mod._headline_sentiment_score(headlines)
    assert score > 0
    assert mod._headline_sentiment_label(score) == "偏多"
    summary = mod._headline_sentiment_summary(headlines, score)
    assert "近期公开标题偏多" in summary
    assert "签约大单并获批新项目" in summary


def test_merge_sentiment_into_signal_snapshots(tmp_path: Path):
    mod = _load_live_recommend()
    mod.OUT_DIR = tmp_path
    snap = tmp_path / "signal_snapshots.jsonl"
    snap.write_text(
        json.dumps({"date": "2026-06-04", "code": "000001.XSHE", "vb_star": True}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    records = [{
        "date": "2026-06-04",
        "code": "000001.XSHE",
        "score": 0.3,
        "label": "偏多",
        "summary": "近期公开标题偏多，最新聚焦“测试标题”。",
        "source": "google_news_rss",
        "target_set": "vb_star",
    }]
    mod._merge_sentiment_into_signal_snapshots(records, "2026-06-04")
    row = json.loads(snap.read_text(encoding="utf-8").strip())
    assert row["stock_sentiment_score"] == 0.3
    assert row["stock_sentiment_label"] == "偏多"
    assert row["stock_sentiment_decision_used"] is False
    assert row["stock_sentiment_target_set"] == "vb_star"
