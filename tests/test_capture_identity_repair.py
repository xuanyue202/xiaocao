from copy import deepcopy

import pytest

from xiaocao.kol.capture import canonical_xiaoetong_source
from xiaocao.kol.capture_identity_repair import corrected_rows


def fixture():
    old_page = "https://app123.h5.xiaoeknow.com/v2/course/alive/l_wrong"
    page = old_page.replace("l_wrong", "l_correct")
    item = dict(identity="item", capture_job_id="capture", status="capture_armed",
                source_identity="xiaoetong:app123:l_wrong")
    capture = dict(job_id="capture", source_job_id="source", status="awaiting_capture",
                   expected_source=canonical_xiaoetong_source(old_page), baseline_candidate_keys=["live:l_old"])
    job = dict(id="source", live_id="l_wrong", app_id="app123", status="awaiting_playback",
               armed_at="2026-09-08T12:00:00+08:00", baseline={"candidate_ids": ["old"]})
    candidate = dict(id="new", live_id="l_correct", captured="2026-09-08 12:01:00",
                     media_type="m3u8", url="https://vod.xet.tech/a/playlist_eof.m3u8",
                     source_url="https://app123.h5.xe-live.com/_alive/v3/get_lookback_list")
    evidence = dict(identity="item", source_identity="xiaoetong:app123:l_correct",
                    playback_surface="wechat_mini_program", media_request_observed=True,
                    playback_window_closed=True)
    return [item, capture, job, page, candidate, evidence, "2026-09-08T12:02:00+08:00"]


def test_corrects_only_identity_preserving_original_ids_baselines_and_input():
    args = fixture()
    before = deepcopy(args)
    item, capture, job = corrected_rows(*args)
    assert args == before
    assert item["capture_job_id"] == capture["job_id"] == "capture"
    assert capture["source_job_id"] == job["id"] == "source"
    assert job["armed_at"] == args[2]["armed_at"]
    assert job["baseline"] == args[2]["baseline"]
    assert capture["baseline_candidate_keys"] == args[1]["baseline_candidate_keys"]
    assert job["live_id"] == "l_correct"
    assert job["identity_correction"]["previous_source_identity"] == "xiaoetong:app123:l_wrong"


@pytest.mark.parametrize("index,key,value", [
    (0, "handoff_id", "already-published"),
    (1, "download_task_id", "already-started"), (2, "task_id", "already-started"),
    (2, "status", "playlist_detected"), (2, "error_code", "task_create_failed"),
    (4, "id", "old"), (4, "captured", "2026-09-08 11:59:00"),
    (4, "live_id", "l_other"), (4, "url", "https://vod.xet.tech/liveplay.m3u8"),
    (4, "source_url", "https://app999.h5.xe-live.com/a"),
    (5, "playback_window_closed", False), (5, "identity", "other"),
])
def test_refuses_effects_stale_candidate_other_app_or_unproved_closure(index, key, value):
    args = fixture()
    args[index][key] = value
    with pytest.raises(ValueError):
        corrected_rows(*args)
