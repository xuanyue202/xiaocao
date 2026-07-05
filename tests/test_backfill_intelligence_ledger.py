from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_backfill():
    root = Path(__file__).resolve().parent.parent
    path = root / "scripts" / "backfill_intelligence_ledger.py"
    spec = importlib.util.spec_from_file_location("backfill_intelligence_ledger_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_backfill_agent_review_never_marks_exit_composite_input(tmp_path: Path) -> None:
    mod = _load_backfill()
    live = tmp_path / "live"
    live.mkdir()
    (live / "signal_snapshots.jsonl").write_text(
        json.dumps({"date": "2026-07-01", "code": "000001.XSHE"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    changed = mod.merge_signal_snapshots(live, [{
        "date": "2026-07-01",
        "code": "000001.XSHE",
        "score_source": "agent_review",
        "agent_short_score": 0.5,
        "score": 0.5,
        "label": "偏多",
        "usage": {"exit_composite_input": True},
        "data_quality": "ok",
    }])

    row = json.loads((live / "signal_snapshots.jsonl").read_text(encoding="utf-8"))
    assert changed == 1
    assert row["stock_sentiment_exit_composite_input"] is False
