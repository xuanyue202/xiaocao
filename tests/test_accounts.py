"""Round-trip tests for the shared account/position I/O (src/xiaocao/live/accounts.py).

Pins the real-money state behaviour that was unified out of live_monitor and
paper_record, so a future edit can't silently change account semantics.
"""
from __future__ import annotations

import json

from xiaocao.live import accounts


def test_load_account_fresh_defaults(tmp_path):
    a = accounts.load_account(tmp_path / "acct.json", initial_capital=100000.0, fee_rate=0.0001)
    assert a["cash"] == 100000.0 and a["initial_capital"] == 100000.0
    assert a["fee_rate"] == 0.0001 and a["realized_pnl"] == 0.0 and a["total_fees"] == 0.0
    assert "created_at" in a


def test_load_account_existing_keeps_values_and_fills_missing(tmp_path):
    p = tmp_path / "acct.json"
    p.write_text(json.dumps({"cash": 55000.0, "realized_pnl": -4191.0}), encoding="utf-8")
    a = accounts.load_account(p, initial_capital=100000.0, fee_rate=0.0001)
    assert a["cash"] == 55000.0 and a["realized_pnl"] == -4191.0     # kept
    assert a["initial_capital"] == 100000.0 and a["total_fees"] == 0.0  # filled


def test_save_account_atomic_roundtrip(tmp_path):
    p = tmp_path / "acct.json"
    accounts.save_account({"cash": 1.0}, p)
    assert not (tmp_path / "acct.json.tmp").exists()   # tmp replaced
    saved = json.loads(p.read_text())
    assert saved["cash"] == 1.0 and "updated_at" in saved


def test_append_jsonl(tmp_path):
    p = tmp_path / "trades.jsonl"
    accounts.append_jsonl({"side": "BUY"}, p)
    accounts.append_jsonl({"side": "SELL"}, p)
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert [r["side"] for r in rows] == ["BUY", "SELL"]


def test_load_positions_skips_blank_comment_and_malformed(tmp_path):
    p = tmp_path / "positions.jsonl"
    p.write_text(
        "\n".join([
            json.dumps({"code": "A", "book": "B"}),
            "# a comment line",
            "",
            "{not json}",
            json.dumps({"code": "B", "book": "A"}),
        ]) + "\n",
        encoding="utf-8",
    )
    rows = accounts.load_positions(p)
    assert [r["code"] for r in rows] == ["A", "B"]


def test_position_key():
    assert accounts.position_key({"entry_date": "2026-06-19", "code": "A"}) == ("2026-06-19", "A")
    assert accounts.position_key({}) == ("", "")
