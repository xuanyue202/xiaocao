from __future__ import annotations

import json

from scripts import refresh_daily_cache as refresh


def _jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_universe_always_includes_indices_and_uses_requested_date(tmp_path) -> None:
    _jsonl(tmp_path / "positions.jsonl", [
        {"status": "open", "code": "OPEN.XSHE"},
        {"status": "closed", "code": "CLOSED.XSHE"},
    ])
    _jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-07-10", "code": "TARGET.XSHE"},
        {"date": "2026-07-14", "code": "TODAY.XSHE"},
    ])

    codes = refresh._universe("20260710", live_dir=tmp_path)

    assert set(refresh.MARKET_INDEX_CODES).issubset(codes)
    assert {"OPEN.XSHE", "TARGET.XSHE"}.issubset(codes)
    assert "TODAY.XSHE" not in codes and "CLOSED.XSHE" not in codes
