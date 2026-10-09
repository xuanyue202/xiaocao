"""Committed entry evidence must reach the APP Book B exit monitor."""
import json
from dataclasses import replace

import pytest

from xiaocao.live.book_b_live_intraday import load_monitor_contexts
from xiaocao.live.book_b_live_lifecycle import BookBLiveOwnedLot
from xiaocao.live.morning_bundle import publish_captured_batch
from xiaocao.live.trading_runner import frozen_rows_digest

pytestmark = pytest.mark.app_simulation
DATE = "2026-10-09"


def entry(root, monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-morning")
    monkeypatch.setenv("CODEX_THREAD_ID", "original-producer")
    row = {"date": DATE, "book": "B", "code": "000710.XSHE",
           "mode": "N字低吸", "profile": "xiaocao", "is_live": True,
           "mode_exec_star": True}
    bundle = publish_captured_batch(root, DATE,
        snapshot=(json.dumps(row) + "\n").encode(), strategy_sha="a" * 40,
        source_readiness={}, timing={})
    reference = f"{root}/morning_bundle_commit_{DATE}.json:{DATE}:sha256:{bundle['snapshot_sha256']}:000710.XSHE"
    lot = BookBLiveOwnedLot("assisted-buy", "000710.XSHE", "贝瑞基因", DATE,
        9.95, 2600, 0, 10.01, 26026, 26023.4, .0001, .0001, reference, {})
    return row, bundle, lot


def test_committed_entry_ignores_empty_legacy_projection(tmp_path, monkeypatch):
    _, _, lot = entry(tmp_path, monkeypatch)
    (tmp_path / f"book_b_live_freeze_{DATE}.jsonl").write_bytes(b"")
    assert load_monitor_contexts(tmp_path, [lot])[lot.owned_lot_id] == {
        "mode": "N字低吸", "profile": "xiaocao"}


def test_broken_commitment_never_falls_back_to_legacy(tmp_path, monkeypatch):
    row, _, lot = entry(tmp_path, monkeypatch)
    (tmp_path / f"book_b_live_freeze_{DATE}.jsonl").write_text(json.dumps(row) + "\n")
    (tmp_path / f"morning_bundle_commit_{DATE}.json").write_text("{}")
    with pytest.raises(ValueError):
        load_monitor_contexts(tmp_path, [lot])


def test_pre_bundle_lot_retains_original_hashed_legacy(tmp_path):
    legacy_date = "2026-09-30"
    row = {"date": legacy_date, "book": "B", "code": "000710.XSHE", "mode": "N字低吸"}
    path = tmp_path / f"book_b_live_freeze_{legacy_date}.jsonl"
    path.write_text(json.dumps(row) + "\n")
    ref = f"{path}:{legacy_date}:sha256:{frozen_rows_digest([row])}:000710.XSHE"
    lot = BookBLiveOwnedLot("legacy-buy", "000710.XSHE", "贝瑞基因", legacy_date,
        9.95, 2600, 0, 10.01, 26026, 26023.4, .0001, .0001, ref, {})
    assert load_monitor_contexts(tmp_path, [lot])[lot.owned_lot_id]["mode"] == "N字低吸"
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        load_monitor_contexts(tmp_path, [replace(lot, snapshot_ref=ref.replace(frozen_rows_digest([row]), "0" * 64))])


def test_post_cutover_lot_rejects_missing_commitment(tmp_path):
    row = {"date": DATE, "book": "B", "code": "000710.XSHE", "mode": "N字低吸"}
    path = tmp_path / f"book_b_live_freeze_{DATE}.jsonl"
    path.write_text(json.dumps(row) + "\n")
    ref = f"{path}:{DATE}:sha256:{frozen_rows_digest([row])}:000710.XSHE"
    lot = BookBLiveOwnedLot("legacy-buy", "000710.XSHE", "贝瑞基因", DATE,
        9.95, 2600, 0, 10.01, 26026, 26023.4, .0001, .0001, ref, {})
    with pytest.raises(ValueError, match="COMMITMENT_MISSING"):
        load_monitor_contexts(tmp_path, [lot])
