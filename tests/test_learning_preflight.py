from __future__ import annotations

import json

import scripts.learning_preflight as lp


def test_latest_reconstructed_date_normalizes_compact_dates(tmp_path, monkeypatch):
    path = tmp_path / "daily_reconstructed.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({"code": "A", "date": "20260621"}),
            json.dumps({"code": "B", "date": "2026-06-22"}),
        ]) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(lp, "RECONSTRUCTED_DAILY", path)

    assert lp._latest_reconstructed_date() == "2026-06-22"
