from __future__ import annotations

import json
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("strategy_hit_audit", ROOT / "scripts" / "strategy_hit_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_strategy_hit_audit_projects_signal_buy_and_cohort(tmp_path):
    _append_jsonl(tmp_path / "output" / "live" / "signal_snapshots.jsonl", [{
        "date": "2026-07-01",
        "code": "301051.XSHE",
        "name": "信濠光电",
        "mode": "标杆短线起爆",
        "vb_star": True,
        "vb_rank": 1,
        "kp_star": True,
        "kp_rank": 1,
        "quality_tag": "normal",
        "primary_score": 156.0,
        "qibaoBenchmarkKind": "raw_top10_elec20_open_le6_red_notlimit",
        "reason": "raw qibao rank前10",
    }])
    _append_jsonl(tmp_path / "output" / "live" / "paper_trades.jsonl", [{
        "date": "2026-07-01",
        "book": "B",
        "side": "BUY",
        "code": "301051.XSHE",
        "name": "信濠光电",
        "shares": 900,
        "price": 19.593,
    }])
    _append_jsonl(tmp_path / "output" / "cohorts" / "cohort_snapshots.jsonl", [{
        "date": "2026-07-01",
        "code": "300720.XSHE",
        "name": "海川智能",
        "cohort_id": "qibao_raw_top10_elec20_limitlike_watch",
        "layer": "watchlist",
        "authority": 0,
        "note": "authority=0 watchlist",
    }])

    rows = audit.build_projection(date="2026-07-01", root=tmp_path)

    by_code = {r["code"]: r for r in rows}
    assert by_code["301051.XSHE"]["classification"] == "本地正式买入"
    assert by_code["301051.XSHE"]["book_b_buy"] == "yes"
    assert by_code["301051.XSHE"]["signal_tier"] == "★B1/★KP1"
    assert by_code["300720.XSHE"]["classification"] == "研究队列-观察"
    assert by_code["300720.XSHE"]["cohort_authority"] == "0"
    md = audit.render_markdown(rows, date="2026-07-01")
    assert "策略命中审计" in md and "信濠光电" in md and "海川智能" in md
