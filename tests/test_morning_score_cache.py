"""No model/API calls: validate prepared historical values and ranking parity."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from xiaocao.live import morning_score_cache as cache
from scripts.prepare_morning_scores import HistoricalInputs


def record(root, monkeypatch):
    monkeypatch.setattr(cache, "model_fingerprint", lambda _: "model-1")
    return cache.save_scores(root, "2026-10-12", {"A": {"k_score": 2., "p_score": 1.},
        "B": {"k_score": 3., "p_score": 2.}, "C": {"k_score": 1., "p_score": 3.}},
        fingerprint="model-1", input_max_date="2026-10-09", input_hashes=["a"*64],
        completed_at="2026-10-12T09:20:00+08:00")


def test_prepared_scores_recompute_flags_over_current_pool(tmp_path, monkeypatch):
    saved = record(tmp_path, monkeypatch)
    assert cache.load_scores(tmp_path, "2026-10-12") == saved
    candidates = [{"code": x} for x in ("A", "B", "C")]
    health = cache.apply_scores(candidates, saved, top_n=1)
    assert health["status"] == "complete"
    assert [r["code"] for r in candidates] == ["B", "A", "C"]
    assert [r["code"] for r in candidates if r["kp_star"]] == ["B"]
    # A different current pool gets its own median, never old cached flags.
    smaller = [{"code": x} for x in ("A", "C")]
    cache.apply_scores(smaller, saved, top_n=1)
    assert [r["code"] for r in smaller if r["kp_star"]] == ["A"]


@pytest.mark.parametrize("fault", ["hash", "model", "future", "day", "shape"])
def test_invalid_preparation_is_unavailable_not_current_score(tmp_path, monkeypatch, fault):
    saved = record(tmp_path, monkeypatch)
    path = cache.cache_path(tmp_path, "2026-10-12")
    if fault == "model": monkeypatch.setattr(cache, "model_fingerprint", lambda _: "model-2")
    else:
        if fault == "hash": saved["scores"]["A"]["k_score"] = 999
        if fault == "future": saved["input_max_date"] = "2026-10-12"
        if fault == "day": saved["trade_date"] = "2026-10-13"
        if fault == "shape": saved["scores"] = []
        path.write_text(json.dumps(saved))
    assert cache.load_scores(tmp_path, "2026-10-12") == {}


def test_missing_scores_are_explicit_neutral_and_do_not_remove_candidates():
    candidates = [{"code": "A"}, {"code": "NEW"}]
    health = cache.apply_scores(candidates, {}, top_n=1)
    assert health["status"] == "degraded" and health["missing"] == 2
    assert {r["code"] for r in candidates} == {"A", "NEW"}
    assert all(r["k_score"] is None and r["kp_score_basis"] == "unavailable_neutral" for r in candidates)


def test_historical_wrapper_filters_daily_today_and_rejects_today_minutes():
    wrapper = HistoricalInputs(SimpleNamespace(date_kline=lambda *a, **k: [
        {"tradeDate": "20261009", "open": 1}, {"tradeDate": "2026-10-12", "open": 99}],
        minute_line=lambda *a, **k: []), "2026-10-12", datetime.fromisoformat("2099-10-12T09:24:45+08:00"))
    assert wrapper.date_kline("A", count=10) == [{"tradeDate": "2026-10-09", "open": 1}]
    assert max(wrapper.dates) == "2026-10-09"
    with pytest.raises(ValueError, match="FUTURE_INPUT"):
        wrapper.minute_line("A", trade_date="2026-10-12", count=241)


@pytest.mark.parametrize("response_day", ["20261012", "2026-10-13", "20261008"])
def test_history_minute_response_must_match_requested_day(response_day):
    wrapper = HistoricalInputs(SimpleNamespace(minute_line=lambda *a, **k:
        [{"tradeDate": response_day, "trade": 10}]), "2026-10-12",
        datetime.fromisoformat("2099-10-12T09:24:45+08:00"))
    with pytest.raises(ValueError, match="RESPONSE_DATE_MISMATCH"):
        wrapper.minute_line("A", trade_date="2026-10-09", count=241)
    assert wrapper.dates == [] and wrapper.hashes == []


def test_minute_full_timestamp_cannot_smuggle_today_input():
    wrapper = HistoricalInputs(SimpleNamespace(minute_line=lambda *a, **k:
        [{"timestamp": "2026-10-12T09:18:00+08:00", "trade": 10}]), "2026-10-12",
        datetime.fromisoformat("2099-10-12T09:24:45+08:00"))
    with pytest.raises(ValueError, match="RESPONSE_DATE_MISMATCH"):
        wrapper.minute_line("A", trade_date="2026-10-09", count=241)


@pytest.mark.parametrize("other", [{"timestamp": "2026-10-12T09:18:00+08:00"}, {"trade_date": "2026-10-12"}])
def test_all_minute_response_dates_must_agree(other):
    wrapper = HistoricalInputs(SimpleNamespace(minute_line=lambda *a, **k:
        [{"tradeDate": "20261009", "trade": 10, **other}]), "2026-10-12",
        datetime.fromisoformat("2099-10-12T09:24:45+08:00"))
    with pytest.raises(ValueError, match="RESPONSE_DATE_MISMATCH"):
        wrapper.minute_line("A", trade_date="2026-10-09", count=241)
