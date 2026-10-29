import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from xiaocao.kol.video_gap_watchdog import completed_trade_days, inspect_video_gaps, notification_transition
from xiaocao.kol.xiaocao_wechat import DEFAULT_CONTACT, parse_xiaocao_live_messages

NOW = datetime.fromisoformat("2026-10-21T14:00:00+08:00")


def test_completed_days_use_exchange_calendar_and_video_day_boundary():
    rows = [{"calDate": d, "isOpen": 1} for d in ("20260930", "20261009", "20261012")]
    assert completed_trade_days(rows, datetime.fromisoformat("2026-10-12T21:00:00+08:00")) == ["2026-09-30", "2026-10-09"]
    assert completed_trade_days(rows, datetime.fromisoformat("2026-10-12T22:00:00+08:00")) == ["2026-10-09", "2026-10-12"]
    with pytest.raises(ValueError):
        completed_trade_days([{"calDate": "20261020"}], NOW)


def _fixture(root):
    history = {"chat": DEFAULT_CONTACT, "username": "exact-contact", "messages": [
        "[2026-10-19 08:00] #小程序://见势擒龙团/ExampleToken",], "failures": []}
    original, = parse_xiaocao_live_messages(history)
    item = {**original, "status": "discovered"}
    (root/"manifest.json").write_text(json.dumps({"items": {item["identity"]:item}}))
    return history, item


def test_independent_history_finds_missing_original_without_mutating_source(tmp_path):
    history, item = _fixture(tmp_path)
    manifest = tmp_path/"manifest.json"
    manifest.write_text('{"items":{}}')
    before = manifest.read_bytes()
    result = inspect_video_gaps(tmp_path, ["2026-10-19", "2026-10-20"], NOW, history)
    assert result["consecutive_no_video"] is True
    assert result["gaps"][0]["stage"] == "not_discovered"
    assert manifest.read_bytes() == before


def test_media_and_handoff_gaps_are_separate_and_user_exclusions_survive(tmp_path):
    history, item = _fixture(tmp_path)
    item.update(status="playback_activated", capture_job_id="kol-capture")
    directory = tmp_path/"items"/item["identity"]
    directory.mkdir(parents=True)
    (directory/"capture_jobs.jsonl").write_text(json.dumps({"job_id":"kol-capture","status":"downloaded","media_path":"/file.mp4"})+'\n')
    event = {"capture_job_id":"kol-capture","event":"media_validated","media_path":"/file.mp4","media_sha256":"a"*64,
             "updated_at":"2026-10-21T09:00:00+08:00"}
    (directory/"events.jsonl").write_text(json.dumps(event)+'\n')
    (tmp_path/"manifest.json").write_text(json.dumps({"items":{item["identity"]:item}}))
    result = inspect_video_gaps(tmp_path, ["2026-10-19", "2026-10-20"], NOW, history)
    assert result["source_day_media_coverage"]["2026-10-19"] == 1
    assert result["media_receipt_counts"]["2026-10-19"] == 0
    assert result["media_receipts_today"] == 1
    assert result["consecutive_no_video"] is False
    assert result["gaps"][0]["media_receipted"] is True
    assert result["gaps"][0]["handoff_recorded"] is False
    item.update(status="completed", mailbox_readback_status="created", handoff_id="b"*64,
                mailbox_message_id="b"*64, mailbox_content_sha256="c"*64)
    with (directory/"events.jsonl").open("a") as output:
        output.write(json.dumps({**event,"event":"cloud_handoff_published"})+'\n')
    (tmp_path/"manifest.json").write_text(json.dumps({"items":{item["identity"]:item}}))
    assert inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history)["gaps"] == []
    ack = {"event":"mailbox_ack_observed","handoff_id":"b"*64,"content_sha256":"c"*64,
           "receipt":{"operation":"ack_mailbox_message","mailbox_id":"kol.handoff","message_id":"b"*64,"content_sha256":"c"*64}}
    checked = inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history, acknowledgments=[ack])
    assert checked["items"][0]["remote_ack_recorded"] is True
    ack["receipt"]["content_sha256"] = "wrong"
    assert inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history,acknowledgments=[ack])["items"][0]["remote_ack_recorded"] is False
    item["manual_backfill_excluded"] = True
    (tmp_path/"manifest.json").write_text(json.dumps({"items":{item["identity"]:item}}))
    skipped = inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history)
    assert skipped["gaps"] == [] and skipped["consecutive_no_video"] is False


def test_rejected_bytes_and_changed_history_do_not_count_as_success(tmp_path):
    history, item = _fixture(tmp_path)
    item["message_sha256"] = "b"*64
    (tmp_path/"manifest.json").write_text(json.dumps({"items":{item["identity"]:item}}))
    with pytest.raises(ValueError, match="history_original_binding_changed"):
        inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history)


def test_deferred_original_is_retained_without_gap_and_resume_restores_monitoring(tmp_path):
    history, item = _fixture(tmp_path)
    item.update(status="awaiting_playback", capture_job_id="kol-retained",
                human_playback_deferred=True, human_playback_deferral_reason="direct_user_defer")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"items": {item["identity"]: item}}))
    before = manifest.read_bytes()
    deferred = inspect_video_gaps(tmp_path, ["2026-10-19", "2026-10-20"], NOW, history)
    assert deferred["gaps"] == []
    assert deferred["consecutive_no_video"] is False
    assert deferred["explicitly_excluded_days"] == ["2026-10-19"]
    assert deferred["items"][0]["human_playback_deferred"] is True
    assert deferred["items"][0]["capture_job_id"] == "kol-retained"
    assert deferred["items"][0]["handoff_recorded"] is False
    assert manifest.read_bytes() == before

    # A separate original still alerts while the first remains deferred.
    history["messages"].append("[2026-10-20 08:00] #小程序://见势擒龙团/AnotherToken")
    other, = [r for r in parse_xiaocao_live_messages(history) if r["identity"] != item["identity"]]
    checked = inspect_video_gaps(tmp_path, ["2026-10-19", "2026-10-20"], NOW, history)
    assert [r["identity"] for r in checked["gaps"]] == [other["identity"]]

    item["human_playback_deferred"] = False
    manifest.write_text(json.dumps({"items": {item["identity"]: item}}))
    resumed = inspect_video_gaps(tmp_path, ["2026-10-19", "2026-10-20"], NOW, history)
    assert {r["identity"] for r in resumed["gaps"]} == {item["identity"], other["identity"]}


def test_weekend_pending_original_is_not_hidden_by_trade_day_window(tmp_path):
    history, item = _fixture(tmp_path)
    item["published_at"] = "2026-10-18T16:00:00+08:00"
    (tmp_path/"manifest.json").write_text(json.dumps({"items":{item["identity"]:item}}))
    history["messages"] = []
    result = inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history,coverage_start="2026-10-17")
    assert result["gaps"][0]["published_at"].startswith("2026-10-18")


def test_old_manifest_with_new_capture_receipt_stays_in_watchdog(tmp_path):
    history, item = _fixture(tmp_path)
    item.update(published_at="2026-09-01T08:00:00+08:00", updated_at="2026-09-01T10:00:00+08:00",
                status="playback_activated", capture_job_id="kol-old")
    (tmp_path/"manifest.json").write_text(json.dumps({"items":{item["identity"]:item}}))
    directory=tmp_path/"items"/item["identity"]
    directory.mkdir(parents=True)
    (directory/"capture_jobs.jsonl").write_text(json.dumps({"job_id":"kol-old","status":"downloaded","media_path":"/old.mp4"})+'\n')
    (directory/"events.jsonl").write_text(json.dumps({"event":"media_validated","capture_job_id":"kol-old",
        "media_path":"/old.mp4","media_sha256":"a"*64,"updated_at":"2026-10-21T09:00:00+08:00"})+'\n')
    history["messages"]=[]
    result=inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history)
    assert result["media_receipts_today"]==1
    assert result["gaps"][0]["identity"]==item["identity"]


def test_old_expiry_metadata_update_does_not_revive_unbound_legacy(tmp_path):
    history, item = _fixture(tmp_path)
    item.update(published_at="2026-07-17T08:00:00+08:00",updated_at=NOW.isoformat(),status="expired")
    (tmp_path/"manifest.json").write_text(json.dumps({"items":{item["identity"]:item}}))
    history["messages"]=[]
    assert inspect_video_gaps(tmp_path,["2026-10-19","2026-10-20"],NOW,history)["gaps"]==[]


def test_notification_only_on_actionable_change_or_recovery():
    gap = {"status":"action_required","completed_trade_days":["2026-10-19","2026-10-20"],"media_receipt_counts":{},"gaps":[{"identity":"same","stage":"discovered"}]}
    first = notification_transition(gap,None)
    assert first["notify"] is True
    assert notification_transition({**gap,"observed_at":"later"},first)["notify"] is False
    progress_only = {**gap, "gaps":[{**gap["gaps"][0],"capture_progress_at":"later","last_evidence_at":"later"}]}
    assert notification_transition(progress_only,first)["notify"] is False
    recovered = notification_transition({**gap,"status":"healthy","gaps":[]},first)
    assert recovered["notify"] is True
    assert notification_transition(recovered,recovered)["notify"] is False


def test_history_pagination_uses_exact_contact_and_rejects_failed_readback():
    spec = importlib.util.spec_from_file_location("watchdog_cli", Path(__file__).parents[1]/"scripts/kol_video_gap_watchdog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls=[]
    def runner(command, **kwargs):
        calls.append(command)
        offset=int(command[command.index("--offset")+1])
        count=200 if offset==0 else 1
        return SimpleNamespace(stdout=json.dumps({"chat":DEFAULT_CONTACT,"username":"exact","messages":["row"]*count,
            "count":count,"limit":200,"offset":offset,"failures":None}))
    result=module.read_history("2026-10-19","2026-10-21",Path("wechat-cli"),runner)
    assert len(result["messages"])==201 and len(calls)==2
    assert all(command[2]==DEFAULT_CONTACT for command in calls)
    def failed(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps({"chat":DEFAULT_CONTACT,"failures":["unavailable"]}))
    with pytest.raises(ValueError, match="history_readback_incomplete"):
        module.read_history("2026-10-19","2026-10-21",Path("wechat-cli"),failed)
