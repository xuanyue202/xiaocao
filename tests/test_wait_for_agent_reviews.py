from __future__ import annotations

import json

import pytest

from scripts.wait_for_agent_reviews import review_progress


def _write(path, value):
    if isinstance(value, list):
        path.write_text("\n".join(json.dumps(row) for row in value) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def test_review_progress_counts_only_selected_same_day_agent_reviews(tmp_path) -> None:
    queue = tmp_path / "queue.json"
    history = tmp_path / "history.jsonl"
    _write(queue, {
        "market_date": "2026-07-14",
        "items": [{"code": "A.XSHE"}, {"code": "B.XSHE"}],
    })
    _write(history, [
        {"date": "2026-07-14", "code": "A.XSHE", "score_source": "agent_review"},
        {"date": "2026-07-14", "code": "B.XSHE", "score_source": "pending_agent_review"},
        {"date": "2026-07-13", "code": "B.XSHE", "score_source": "agent_review"},
        {"date": "2026-07-14", "code": "OTHER", "score_source": "agent_review"},
    ])

    progress = review_progress(queue, history)

    assert progress == {"selected": 2, "reviewed": 1, "pending": 1, "reviewed_codes": ["A.XSHE"]}


@pytest.mark.parametrize("content,status", [("{", "queue_invalid"),
    ("[]", "queue_invalid"), ('{"market_date":"2026-09-30","items":[1]}', "queue_invalid")])
def test_missing_or_invalid_support_queue_is_degraded_without_wait(tmp_path, monkeypatch, capsys, content, status):
    import sys
    import scripts.wait_for_agent_reviews as script
    if content is not None:
        (tmp_path / "intelligence_review_queue_2026-09-30.json").write_text(content)
    monkeypatch.setattr(script.time, "sleep", lambda *_: pytest.fail("invalid queue must not wait"))
    monkeypatch.setattr(sys, "argv", ["wait_for_agent_reviews.py", "--date", "2026-09-30", "--live-dir", str(tmp_path)])
    script.main()
    assert json.loads(capsys.readouterr().out)["status"] == status


def _run_wait(tmp_path, monkeypatch, capsys, on_sleep, *, timeout=3):
    import sys
    import scripts.wait_for_agent_reviews as script
    clock = [0.0]
    def sleep(seconds):
        clock[0] += seconds
        on_sleep(clock[0])
    monkeypatch.setattr(script.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(script.time, "sleep", sleep)
    monkeypatch.setattr(sys, "argv", ["wait_for_agent_reviews.py", "--date", "2026-10-09",
        "--live-dir", str(tmp_path), "--timeout-sec", str(timeout), "--poll-sec", "1"])
    script.main()
    return json.loads(capsys.readouterr().out), clock[0]


def test_late_queue_and_reviews_share_original_deadline(tmp_path, monkeypatch, capsys):
    def arrivals(elapsed):
        if elapsed == 1:
            _write(tmp_path / "intelligence_review_queue_2026-10-09.json", {
                "market_date": "2026-10-09", "items": [{"code": "A.XSHE"}]})
        if elapsed == 2:
            _write(tmp_path / "stock_sentiment_history.jsonl", [{
                "date": "2026-10-09", "code": "A.XSHE", "score_source": "agent_review"}])
    result, elapsed = _run_wait(tmp_path, monkeypatch, capsys, arrivals)
    assert result["status"] == "reviewed"
    assert result["selected"] == result["reviewed"] == 1
    assert elapsed == 2


def test_missing_queue_exhausts_budget_without_claiming_review(tmp_path, monkeypatch, capsys):
    result, elapsed = _run_wait(tmp_path, monkeypatch, capsys, lambda _: None)
    assert elapsed == 3
    assert result["status"] == "queue_missing"
    assert result["reviewed"] == 0


def test_late_unreviewed_queue_does_not_reset_budget(tmp_path, monkeypatch, capsys):
    def arrivals(elapsed):
        if elapsed == 2:
            _write(tmp_path / "intelligence_review_queue_2026-10-09.json", {
                "market_date": "2026-10-09", "items": [{"code": "A.XSHE"}]})
    result, elapsed = _run_wait(tmp_path, monkeypatch, capsys, arrivals)
    assert elapsed == 3
    assert result["status"] == "fallback_timeout"
    assert result["pending"] == 1


def test_wrong_date_queue_cannot_release_current_review(tmp_path, monkeypatch, capsys):
    _write(tmp_path / "intelligence_review_queue_2026-10-09.json", {
        "market_date": "2026-10-08", "items": []})
    result, elapsed = _run_wait(tmp_path, monkeypatch, capsys, lambda _: pytest.fail("invalid queue must not wait"))
    assert result["status"] == "queue_invalid"
    assert elapsed == 0


def test_completed_intelligence_still_waits_for_original_kol_support(tmp_path, monkeypatch, capsys):
    import sys
    from scripts import wait_for_agent_reviews as script
    from xiaocao.live import paper_morning_kol, morning_bundle
    queue = {"market_date":"2026-10-23","status":"empty","items":[],
             "freeze_binding":{"snapshot_sha256":"a"*64,"strategy_sha":"b"*40}}
    _write(tmp_path / "intelligence_review_queue_2026-10-23.json", queue)
    _write(tmp_path / "freeze.json", {})
    monkeypatch.setattr(morning_bundle,"resolve_receipt",lambda *a,**kw: queue["freeze_binding"])
    clock = [0.0]
    monkeypatch.setattr(script.time,"monotonic",lambda:clock[0])
    monkeypatch.setattr(script.time,"sleep",lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    class Support:
        path = tmp_path / "support.json"
        receipt = {"status":"validated"}
        def __init__(self,*a,**kw): pass
        def tick(self): return clock[0] >= 2
        def defer(self,reason): pass
    monkeypatch.setattr(paper_morning_kol,"PaperKolReview",Support)
    monkeypatch.setenv("XIAOCAO_DAILY_RUN_DIR",str(tmp_path))
    monkeypatch.setenv("XIAOCAO_ROOT",str(tmp_path))
    monkeypatch.setattr(sys,"argv",["wait_for_agent_reviews.py","--date","2026-10-23","--live-dir",str(tmp_path),
        "--timeout-sec","3","--poll-sec","1","--morning-freeze-receipt",str(tmp_path/"freeze.json"),"--kol-preparation"])
    script.main()
    assert clock[0] == 2
    assert json.loads(capsys.readouterr().out)["kol_support"]["status"] == "validated"
