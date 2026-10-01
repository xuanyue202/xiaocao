from __future__ import annotations

import json

import scripts.reconcile_paper_account as recon


def test_rebuild_account_from_book_b_positions():
    account = {"initial_capital": 100000.0, "cash": 10.0, "realized_pnl": 1.0, "fee_rate": 0.0001}
    positions = [
        valid_position(status="closed", realized_pnl=-100.0, entry_fee=1.0, exit_price=9.012, exit_fee=1.2, exit_cash_in=900.0, exit_date="2026-06-02"),
        valid_position(code="600001.XSHG", entry_price=199.98, gross_notional=19998, entry_cash_out=20000.0, entry_fee=2.0),
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
        "code": "600000.XSHG", "entry_date": "2026-06-01", "shares": 100,
        "entry_price": 99.99, "gross_notional": 9999,
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


def valid_position(**changes):
    row = {"book": "B", "code": "600000.XSHG", "entry_date": "2026-06-01",
           "shares": 100, "status": "open", "entry_price": 9.99, "gross_notional": 999,
           "entry_cash_out": 1000.0, "entry_fee": 1.0}
    return {**row, **changes}


def valid_account(**changes):
    return {"initial_capital": 100000.0, "cash": 1.0, "realized_pnl": 0.0, **changes}


def test_rebuild_rejects_unproved_or_unsafe_accounting():
    import pytest
    bad_inputs = [
        ([valid_position()], {}),
        ([valid_position()], valid_account(initial_capital=True)),
        ([valid_position()], valid_account(initial_capital=float("nan"))),
        ([valid_position()], valid_account(cash="bad")),
        ([valid_position(entry_cash_out=float("inf"))], valid_account()),
        ([valid_position(entry_fee=True)], valid_account()),
        ([valid_position(entry_price=True)], valid_account()),
        ([valid_position(exit_price=float("inf"))], valid_account()),
        ([valid_position(entry_cash_out=-1)], valid_account()),
        ([valid_position(), valid_position()], valid_account()),
        ([valid_position(book=None)], valid_account()),
        ([valid_position(status="partial")], valid_account()),
        ([valid_position()], valid_account(initial_capital=1)),
        ([valid_position(status="closed", realized_pnl=100, exit_fee=1,
                         exit_cash_in=1000)], valid_account()),
    ]
    for positions, account in bad_inputs:
        with pytest.raises(ValueError):
            recon.rebuild_account(positions, account)


def test_cli_invalid_evidence_never_mutates_files(tmp_path, monkeypatch):
    positions = tmp_path / "positions.jsonl"
    account = tmp_path / "paper_account.json"
    cases = [(None, valid_account()), ("bad\n", valid_account()),
             ("[]\n", valid_account()), (json.dumps(valid_position()) + "\nbad\n", valid_account()),
             (json.dumps(valid_position()) + "\n", None),
             (json.dumps(valid_position()) + "\n", "bad"),
             (json.dumps(valid_position()) + "\n", [])]
    for lines, acct in cases:
        positions.unlink(missing_ok=True)
        account.unlink(missing_ok=True)
        if lines is not None:
            positions.write_text(lines)
        if acct is not None:
            account.write_text(json.dumps(acct) if acct != "bad" else "bad")
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file() and p.name != "paper_ledger.lock"}
        monkeypatch.setattr("sys.argv", ["reconcile", "--positions", str(positions),
                                       "--account", str(account), "--write"])
        assert recon.main() == 2
        assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file() and p.name != "paper_ledger.lock"} == before


def test_dry_run_does_not_recover_or_create_lock_and_write_is_idempotent(tmp_path, monkeypatch):
    positions = tmp_path / "positions.jsonl"
    account = tmp_path / "paper_account.json"
    positions.write_text(json.dumps(valid_position()) + "\n")
    account.write_text(json.dumps(valid_account()))
    pending = tmp_path / ".ledger_txn" / "pending.json"
    pending.parent.mkdir()
    pending.write_text('{"unresolved": true}')
    argv = ["reconcile", "--positions", str(positions), "--account", str(account)]
    monkeypatch.setattr("sys.argv", argv)
    assert recon.main() == 2
    assert pending.read_text() == '{"unresolved": true}'
    assert not (tmp_path / "paper_ledger.lock").exists()
    pending.unlink()
    assert recon.main() == 0
    assert not (tmp_path / "paper_ledger.lock").exists()
    monkeypatch.setattr("sys.argv", argv + ["--write"])
    assert recon.main() == 0
    result = account.read_bytes()
    assert json.loads(result)["reconcile_evidence"]["positions_sha256"]
    assert recon.main() == 0
    assert account.read_bytes() == result


def test_reconcile_exact_cents_and_closed_cash_conservation():
    import pytest
    lot = valid_position(status="closed", exit_date="2026-06-02", exit_cash_in=1001.01,
                         exit_fee=0.01, exit_price=10.0102, realized_pnl=1.01,
                         entry_fee=0.01, gross_notional=999.99, entry_price=9.9999)
    rebuilt, _ = recon.rebuild_account([lot], valid_account())
    assert rebuilt["cash"] == 100001.01
    assert rebuilt["total_fees"] == 0.02
    for value in ("1e1000", "1e50", "1.001", False):
        with pytest.raises(ValueError):
            recon.rebuild_account([valid_position(entry_cash_out=value)], valid_account())


def test_write_reconcile_rejects_sources_outside_shared_ledger_lock(tmp_path, monkeypatch):
    positions = tmp_path / "other" / "positions.jsonl"
    positions.parent.mkdir()
    positions.write_text(json.dumps(valid_position()) + "\n")
    account = tmp_path / "paper_account.json"
    account.write_text(json.dumps(valid_account()))
    before = account.read_bytes()
    monkeypatch.setattr("sys.argv", ["reconcile", "--positions", str(positions), "--account", str(account), "--write"])
    assert recon.main() == 2
    assert account.read_bytes() == before


def test_rebuild_rejects_contradictory_price_quantity_cash_without_mutating_input():
    import copy
    import pytest
    bad_lots = [
        valid_position(entry_price=10, gross_notional=10000, entry_fee=1, entry_cash_out=10001),
        valid_position(status="closed", entry_price=9.99, gross_notional=999,
                       exit_price=10, exit_fee=1, exit_cash_in=9999,
                       realized_pnl=8999, exit_date="2026-06-02"),
        valid_position(original_shares=200, remaining_shares=100, entry_price=10,
                       gross_notional=2000, entry_fee=1, entry_cash_out=2001),
    ]
    for lot in bad_lots:
        account = valid_account(cash=98999.90)
        before = copy.deepcopy((lot, account))
        with pytest.raises(ValueError):
            recon.rebuild_account([lot], account)
        assert (lot, account) == before


def test_rebuild_refuses_missing_economic_price_evidence():
    import pytest
    lot = valid_position()
    lot.pop("entry_price", None)
    with pytest.raises(ValueError):
        recon.rebuild_account([lot], valid_account())
    lot = valid_position(status="closed", exit_date="2026-06-02", exit_cash_in=1001.01,
                         exit_fee=0.01, realized_pnl=1.01)
    lot.pop("exit_price", None)
    with pytest.raises(ValueError):
        recon.rebuild_account([lot], valid_account())


def test_rebuild_preserves_producer_price_rounding_and_original_shares_after_full_clear():
    # Original production semantics: entry gross from 10.123456, stored price
    # 10.123; exit gross from 10.234567, stored price 10.2346. All 1000 shares
    # remain on the closed row. This is not a remaining-inventory projection.
    lot = valid_position(shares=1000, entry_price=10.123, gross_notional=10123.46,
                         entry_fee=1.01, entry_cash_out=10124.47)
    rebuilt, _ = recon.rebuild_account([lot], valid_account())
    assert rebuilt["cash"] == 89875.53
    lot.update(status="closed", exit_date="2026-06-02", exit_price=10.2346,
               exit_cash_in=10233.55, exit_fee=1.02, realized_pnl=109.08)
    rebuilt, _ = recon.rebuild_account([lot], valid_account())
    assert rebuilt["cash"] == 100109.08
    assert rebuilt["realized_pnl"] == 109.08
    assert lot["shares"] == 1000


def test_rebuild_accepts_actual_filled_quantity_but_rejects_unproved_partial_sale():
    import pytest
    # An incomplete BUY fill may be less than the planned request; shares and
    # money still describe the actual filled lot. Planned size is not inventory.
    lot = valid_position(planned_shares=200)
    rebuilt, _ = recon.rebuild_account([lot], valid_account())
    assert rebuilt["cash"] == 99000
    for changes in ({"remaining_shares": 50}, {"realized_pnl": 100},
                    {"exit_fee": 1}, {"partial_exits": []}):
        with pytest.raises(ValueError):
            recon.rebuild_account([valid_position(**changes)], valid_account())
