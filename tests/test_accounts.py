"""Round-trip tests for the shared account/position I/O (src/xiaocao/live/accounts.py).

Pins the real-money state behaviour that was unified out of live_monitor and
paper_record, so a future edit can't silently change account semantics.
"""
from __future__ import annotations

import json

import pytest

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


def test_append_trade_requires_explicit_valid_book(tmp_path):
    path = tmp_path / "trades.jsonl"
    with pytest.raises(ValueError, match="explicit book"):
        accounts.append_trade({"side": "BUY"}, path)
    with pytest.raises(ValueError, match="invalid book"):
        accounts.append_trade({"side": "BUY", "book": "C"}, path)

    accounts.append_trade({"side": "BUY", "book": "B"}, path)
    assert json.loads(path.read_text())["book"] == "B"


def test_position_jsonl_line_requires_explicit_book():
    with pytest.raises(ValueError, match="explicit book"):
        accounts.position_jsonl_line({"code": "A"})
    assert json.loads(accounts.position_jsonl_line({"code": "A", "book": "B"}))["book"] == "B"


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


def test_save_positions_is_atomic(tmp_path):
    path = tmp_path / "positions.jsonl"
    accounts.save_positions([{"code": "A", "book": "B"}, {"code": "B", "book": "A"}], path)
    assert not (tmp_path / "positions.jsonl.tmp").exists()
    assert [json.loads(line)["code"] for line in path.read_text().splitlines()] == ["A", "B"]


def test_save_positions_rejects_implicit_book(tmp_path):
    with pytest.raises(ValueError, match="explicit book"):
        accounts.save_positions([{"code": "A"}], tmp_path / "positions.jsonl")


def test_ledger_lock_path_is_canonical(tmp_path):
    assert accounts.ledger_lock_path(tmp_path) == tmp_path / "paper_ledger.lock"


def test_interrupted_multi_file_commit_is_recoverable(tmp_path, monkeypatch):
    positions = tmp_path / "positions.jsonl"
    account_path = tmp_path / "paper_account.json"
    trades = tmp_path / "paper_trades.jsonl"
    positions.write_text(json.dumps({
        "book": "B", "code": "A", "status": "open",
    }) + "\n", encoding="utf-8")
    account_path.write_text(json.dumps({"cash": 1000.0}), encoding="utf-8")
    trades.write_text("", encoding="utf-8")
    original_install = accounts._install_staged_file
    calls = 0

    def fail_after_first(staged, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated crash")
        original_install(staged, target)

    monkeypatch.setattr(accounts, "_install_staged_file", fail_after_first)
    with pytest.raises(OSError, match="simulated crash"):
        accounts.commit_ledger_transaction(
            live_dir=tmp_path,
            positions=[{"book": "B", "code": "A", "status": "closed"}],
            positions_path=positions,
            account={"cash": 1100.0},
            account_path=account_path,
            new_trades=[{"book": "B", "side": "SELL", "code": "A"}],
            trades_path=trades,
        )
    assert (tmp_path / ".ledger_txn" / "pending.json").exists()

    monkeypatch.setattr(accounts, "_install_staged_file", original_install)
    assert accounts.recover_ledger_transaction(tmp_path) is True
    assert json.loads(positions.read_text())["status"] == "closed"
    assert json.loads(account_path.read_text())["cash"] == 1100.0
    assert json.loads(trades.read_text())["side"] == "SELL"
    assert not (tmp_path / ".ledger_txn" / "pending.json").exists()
