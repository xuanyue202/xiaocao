"""Auction readiness regressions; no APP adapter or business effects."""
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import scripts.live_recommend as recommend
from xiaocao.utils.business_clock import wait_for_business_time
from xiaocao.utils.trading_session import A_SHARE_TZ


def test_early_wake_waits_bounded_chunks_until_auction():
    current = [datetime(2026, 10, 9, 9, 15, tzinfo=A_SHARE_TZ)]
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        current[0] += timedelta(seconds=seconds)
    wait_for_business_time("2026-10-09", time(9, 25, 1), now=lambda: current[0], sleep=sleep)
    assert current[0].time() == time(9, 25, 1)
    assert max(sleeps) <= 60
    assert recommend._seconds_until_recommendation_start(
        "2026-10-09", datetime(2026, 10, 9, 9, 19, 31, tzinfo=A_SHARE_TZ)) == 330


def test_stable_signals_retry_until_every_price_ready(monkeypatch):
    elapsed = [0.0]
    attempts = []
    source = SimpleNamespace(readiness={})
    monkeypatch.setattr(recommend, "_today_iso", lambda: "2026-10-09")
    monkeypatch.setattr(recommend._time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(recommend._time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    def strategy(*a, **k):
        attempts.append(elapsed[0])
        source.readiness = {"sources": [{"source": "stock_index", "status": "populated"}]}
        return [{"code": "A", "mode": "test"}, {"code": "B", "mode": "test"}]
    monkeypatch.setattr(recommend, "run_strategy", strategy)
    missing = lambda rows: [] if elapsed[0] >= 40 else ["B"]
    rows, active = recommend._run_strategy_when_ready("2026-10-09", source,
        timeout_sec=-1, poll_sec=2, confirm_sec=0, price_probe=missing)
    assert len(rows) == len(active) == 2
    assert elapsed[0] == 40
    assert all(b - a == 2 for a, b in zip(attempts, attempts[1:]))
    assert source.readiness["price_enrichment"]["status"] == "complete"


def test_missing_source_never_released_as_stable_candidates(monkeypatch):
    source = SimpleNamespace(readiness={})
    elapsed = [0.0]
    monkeypatch.setattr(recommend, "_today_iso", lambda: "2026-10-09")
    monkeypatch.setattr(recommend._time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(recommend._time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    def strategy(*a, **k):
        source.readiness = {"sources": [{"source": "pool", "status":
            "empty_unconfirmed" if elapsed[0] < 6 else "populated"}]}
        return [{"code": "A", "mode": "test"}]
    monkeypatch.setattr(recommend, "run_strategy", strategy)
    recommend._run_strategy_when_ready("2026-10-09", source, timeout_sec=-1,
        poll_sec=2, confirm_sec=0, price_probe=lambda _: [])
    assert elapsed[0] == 6


def test_context_pack_failure_observation_does_not_create_freeze(tmp_path):
    from xiaocao.live.context_pack import build_context_pack
    pack = build_context_pack(live_dir=tmp_path, market_date="2026-10-09")
    assert pack["intelligence_review_queue"]["status"] == "missing"
    assert not (tmp_path / "book_b_live_freeze_2026-10-09.jsonl").exists()


def test_review_from_other_batch_cannot_release_paper_rendezvous(tmp_path):
    import json
    from scripts.wait_for_agent_reviews import review_progress
    queue, history = tmp_path / "queue.json", tmp_path / "history.jsonl"
    binding = {"snapshot_sha256": "a" * 64, "checkpoint_sha256": "b" * 64, "strategy_sha": "c" * 40}
    queue.write_text(json.dumps({"market_date": "2026-10-09", "status": "ready",
        "freeze_binding": binding, "items": [{"code": "A"}]}))
    history.write_text(json.dumps({"date": "2026-10-09", "code": "A", "score_source": "agent_review",
        "evidence_freeze_ref": "other-batch"}) + "\n")
    result = review_progress(queue, history, expected_date="2026-10-09", expected_binding=binding)
    assert result["pending"] == 1 and result["reviewed"] == 0
    history.write_text(history.read_text().replace("other-batch", f"morning-bundle:{'b' * 64}:{'a' * 64}"))
    assert review_progress(queue, history, expected_date="2026-10-09", expected_binding=binding)["reviewed"] == 1


def test_market_token_recovery_keeps_original_capture_waiting(monkeypatch, capsys):
    from xiaocao.api.errors import ApiAuthError
    source, elapsed = SimpleNamespace(readiness={}), [0.0]
    monkeypatch.setattr(recommend, "_today_iso", lambda: "2026-10-09")
    monkeypatch.setattr(recommend._time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(recommend._time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    def strategy(*a, **k):
        if elapsed[0] < 6:
            raise ApiAuthError("MARKET_LOGIN_CAPTCHA_REQUIRED")
        source.readiness = {"sources": [{"source": "pool", "status": "populated"}]}
        return [{"code": "A", "mode": "test"}]
    monkeypatch.setattr(recommend, "run_strategy", strategy)
    rows, _ = recommend._run_strategy_when_ready("2026-10-09", source, timeout_sec=-1,
        poll_sec=2, confirm_sec=0, stable_samples=1, price_probe=lambda _: [])
    assert rows[0]["code"] == "A" and elapsed[0] == 6
    assert capsys.readouterr().err.count("market_dependency_recovery_wait") == 1


def test_explicit_stale_source_date_is_rejected():
    import pytest
    from xiaocao.datasource.api_source import ApiDataSource
    from xiaocao.api.errors import ApiSchemaError
    source = ApiDataSource(SimpleNamespace(get_industry_block_rank=lambda *a: [{"tradeDate": "20261008"}]))
    source.begin_observation(1)
    with pytest.raises(ApiSchemaError, match="MORNING_SOURCE_DATE_MISMATCH"):
        source.get_industry_block_rank("2026-10-09")


def test_old_source_date_waits_in_original_capture_until_today_arrives(monkeypatch):
    from xiaocao.datasource.api_source import ApiDataSource
    elapsed = [0.0]
    calls = []
    def fetch(*args):
        calls.append(elapsed[0])
        return [{"tradeDate": "20261008" if elapsed[0] < 6 else "20261009"}]
    source = ApiDataSource(SimpleNamespace(get_industry_block_rank=fetch))
    monkeypatch.setattr(recommend, "_today_iso", lambda: "2026-10-09")
    monkeypatch.setattr(recommend._time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(recommend._time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    def strategy(date, source, **kwargs):
        source.get_industry_block_rank(date)
        return [{"code": "A", "mode": "test"}]
    monkeypatch.setattr(recommend, "run_strategy", strategy)
    rows, _ = recommend._run_strategy_when_ready("2026-10-09", source,
        timeout_sec=-1, poll_sec=2, confirm_sec=0, stable_samples=1, price_probe=lambda _: [])
    assert calls == [0, 2, 4, 6]
    assert rows[0]["code"] == "A"
    assert source.readiness["sources"][0]["status"] == "populated"


def test_real_schema_failure_still_stops_capture_without_retry(monkeypatch):
    import pytest
    from xiaocao.api.errors import ApiSchemaError
    from xiaocao.datasource.api_source import ApiDataSource
    def fetch(*args):
        raise ApiSchemaError("invalid response shape")
    source = ApiDataSource(SimpleNamespace(get_industry_block_rank=fetch))
    monkeypatch.setattr(recommend, "_today_iso", lambda: "2026-10-09")
    monkeypatch.setattr(recommend._time, "sleep", lambda _: pytest.fail("schema damage must not retry"))
    monkeypatch.setattr(recommend, "run_strategy", lambda date, source, **kwargs:
                        source.get_industry_block_rank(date))
    with pytest.raises(ApiSchemaError, match="invalid response shape"):
        recommend._run_strategy_when_ready("2026-10-09", source,
            timeout_sec=-1, poll_sec=2, price_probe=lambda _: [])


def test_ranking_subset_keeps_unranked_universe_visible_without_blocking():
    from xiaocao.datasource.api_source import ApiDataSource
    source = ApiDataSource(SimpleNamespace(sort_v2=lambda *a, **k: ["A"]))
    source.begin_observation(1)
    source.sort_codes("2026-10-09", ["A", "B"])
    assert source.readiness["sources"][0]["status"] == "populated"
    assert source.readiness["sources"][0]["unranked_codes"] == ["B"]


def test_global_ranking_without_any_requested_member_stays_unready():
    from xiaocao.datasource.api_source import ApiDataSource
    source = ApiDataSource(SimpleNamespace(sort_v2=lambda *a, **k: ["outside-pool"]))
    source.begin_observation(1)
    source.sort_codes("2026-10-09", ["A", "B"])
    assert source.readiness["sources"][0]["status"] == "partial"
    assert source.readiness["sources"][0]["unranked_codes"] == ["A", "B"]


def test_selected_stock_index_missing_a_code_still_blocks_capture():
    from xiaocao.datasource.api_source import ApiDataSource
    source = ApiDataSource(SimpleNamespace(get_xiao_cao_index_v2=lambda *a: [{"code": "A"}]))
    source.begin_observation(1)
    source.get_stock_index("2026-10-09", ["A", "B"])
    assert source.readiness["sources"][0]["status"] == "partial"
    assert source.readiness["sources"][0]["missing_codes"] == ["B"]


def test_health_does_not_count_a_review_from_another_original(tmp_path):
    import json
    from xiaocao.live.run_flow import supporting_health_from_live
    (tmp_path / "morning_bundle_commit_2026-10-09.json").write_text("{}")
    (tmp_path / "intelligence_review_queue_2026-10-09.json").write_text(json.dumps({
        "market_date": "2026-10-09", "items": [{"code": "A", "evidence_freeze_ref": "this-original"}]}))
    (tmp_path / "stock_sentiment_history.jsonl").write_text(json.dumps({
        "date": "2026-10-09", "code": "A", "score_source": "agent_review", "evidence_freeze_ref": "other-original"}) + "\n")
    result = supporting_health_from_live(live_dir=tmp_path, market_date="2026-10-09")
    assert result["agent_review"] == {"selected": 1, "reviewed": 0, "pending": 1}


def test_empty_regenerated_queue_retains_completed_batch_health(tmp_path):
    import json
    from xiaocao.live.run_flow import supporting_health_from_live
    (tmp_path / "morning_bundle_commit_2026-10-09.json").write_text("{}")
    (tmp_path / "intelligence_review_queue_2026-10-09.json").write_text(json.dumps({
        "market_date": "2026-10-09", "items": [], "evidence_freeze_ref": "this-original"}))
    (tmp_path / "stock_sentiment_history.jsonl").write_text(json.dumps({
        "date": "2026-10-09", "code": "A", "score_source": "agent_review", "evidence_freeze_ref": "this-original"}) + "\n")
    result = supporting_health_from_live(live_dir=tmp_path, market_date="2026-10-09")
    assert result["agent_review"] == {"selected": 0, "reviewed": 1, "pending": 0}


def test_nonfinite_or_negative_quote_is_not_a_ready_entry(monkeypatch):
    monkeypatch.setattr(recommend, "_today_iso", lambda: "2026-10-09")
    for price in (float("nan"), float("inf"), -1):
        client = SimpleNamespace(
            second_line_detail_info=lambda code: {code: {"code": code, "tradeDate": "2026-10-09", "open": price}},
            date_kline=lambda *a, **k: [], stock_call_auction=lambda *a: [])
        assert recommend._entry_price(client, "A", "2026-10-09")[0] is None
