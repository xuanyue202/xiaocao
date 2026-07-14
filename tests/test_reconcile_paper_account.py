from __future__ import annotations

import json

import scripts.reconcile_paper_account as recon


def test_rebuild_account_from_book_b_positions():
    account = {"initial_capital": 100000.0, "cash": 10.0, "realized_pnl": 1.0, "fee_rate": 0.0001}
    positions = [
        {"book": "B", "status": "closed", "realized_pnl": -100.0, "entry_fee": 1.0, "exit_fee": 1.2},
        {"book": "B", "status": "open", "entry_cash_out": 20000.0, "entry_fee": 2.0},
        {"book": "A", "status": "closed", "realized_pnl": 999.0, "entry_fee": 9.0, "exit_fee": 9.0},
    ]

    rebuilt, summary = recon.rebuild_account(positions, account)

    assert rebuilt["cash"] == 79900.0
    assert rebuilt["realized_pnl"] == -100.0
    assert rebuilt["total_fees"] == 4.2
    assert summary["cash_delta"] == 79890.0


def test_write_reconcile_uses_recoverable_ledger_path(tmp_path, monkeypatch):
    positions = tmp_path / "positions.jsonl"
    account = tmp_path / "paper_account.json"
    positions.write_text(json.dumps({
        "book": "B", "status": "open", "entry_cash_out": 10000.0, "entry_fee": 1.0,
    }) + "\n", encoding="utf-8")
    account.write_text(json.dumps({
        "initial_capital": 100000.0, "cash": 1.0, "realized_pnl": 0.0,
    }), encoding="utf-8")
    monkeypatch.setattr("sys.argv", [
        "reconcile_paper_account.py", "--positions", str(positions),
        "--account", str(account), "--write",
    ])

    assert recon.main() == 0

    assert json.loads(account.read_text())["cash"] == 90000.0
    assert not (tmp_path / ".ledger_txn" / "pending.json").exists()
