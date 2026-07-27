from __future__ import annotations

import json
from pathlib import Path

from xiaocao.live import intelligence_evidence


def test_decay_weight_respects_fresh_window_and_max_age() -> None:
    assert intelligence_evidence.decay_weight(
        2,
        fresh_window_days=3,
        half_life_days=2,
        max_age_days=14,
    ) == 1.0
    assert intelligence_evidence.decay_weight(
        5,
        fresh_window_days=3,
        half_life_days=2,
        max_age_days=14,
    ) == 0.5
    assert intelligence_evidence.decay_weight(
        15,
        fresh_window_days=3,
        half_life_days=2,
        max_age_days=14,
    ) == 0.0


def test_freeze_rows_shape_evidence_without_future_fetch() -> None:
    rows = intelligence_evidence.freeze_rows_from_records(
        records=[{
            "date": "2026-07-01",
            "code": "000001.XSHE",
            "name": "平安银行",
            "source": "google_news_rss",
            "source_url": "https://example.com/rss",
            "data_quality": "ok",
            "evidence_state": "available",
            "evidence": [{
                "title": "平安银行被列失信执行相关风险",
                "link": "https://example.com/a",
                "published_at": "2026-06-30T09:30:00+08:00",
                "relevance": "direct_company_news",
            }],
        }],
        candidates=[{
            "code": "000001.XSHE",
            "name": "平安银行",
            "mode": "首红断低吸",
            "rank_score": 88.0,
            "vb_star": True,
            "mode_exec_star": True,
            "mode_state": "ACTIVE",
            "mode_alpha_pool_lcb80": 1.25,
        }],
        market_date="2026-07-01",
        phase="morning_freeze",
        universe="candidates",
        evidence_asof="2026-07-01T09:30:00+08:00",
    )

    assert rows[0]["phase"] == "morning_freeze"
    assert rows[0]["candidate_context"]["rank_score"] == 88.0
    assert rows[0]["candidate_context"]["mode_exec_star"] is True
    assert rows[0]["candidate_context"]["mode_state"] == "ACTIVE"
    assert rows[0]["evidence"][0]["evidence_id"] == "ev1"
    assert rows[0]["evidence"][0]["short_decay_weight"] == 1.0
    assert "dishonesty_enforcement" in rows[0]["hard_veto_event_types"]


def test_write_freeze_artifacts_updates_cache_freeze_and_latency(tmp_path: Path) -> None:
    live = tmp_path / "live"
    freeze = intelligence_evidence.write_freeze_artifacts(
        live_dir=live,
        records=[{
            "date": "2026-07-01",
            "code": "000001.XSHE",
            "name": "平安银行",
            "source": "unit",
            "data_quality": "ok",
            "evidence": [{"title": "平安银行公告", "published_at": "2026-07-01T01:00:00+00:00"}],
        }],
        candidates=[{"code": "000001.XSHE", "name": "平安银行"}],
        market_date="2026-07-01",
        phase="morning_freeze",
        universe="candidates",
        evidence_asof="2026-07-01T02:00:00+00:00",
        elapsed_ms=1234,
    )

    assert len(freeze) == 1
    assert (live / "intelligence_evidence_cache.jsonl").exists()
    assert (live / "intelligence_evidence_2026-07-01.jsonl").exists()
    latency = json.loads((live / "intelligence_latency.jsonl").read_text(encoding="utf-8").strip())
    assert latency["event"] == "evidence_freeze"
    assert latency["elapsed_ms"] == 1234
