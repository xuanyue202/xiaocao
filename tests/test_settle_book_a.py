from __future__ import annotations

from kronos_screen.scripts import settle_book_a as settle


def _closed(book: str, *, pnl: float) -> dict:
    return {
        "book": book,
        "code": "X.XSHE",
        "entry_date": "2026-07-10",
        "entry_price": 10.0,
        "entry_cash_out": 1000.0,
        "shares": 100,
        "status": "closed",
        "realized_pnl": pnl,
    }


def test_comparison_leads_with_paired_metric_and_labels_raw_totals(
    monkeypatch, tmp_path, capsys,
) -> None:
    monkeypatch.setattr(settle, "ACCOUNT_A", tmp_path / "missing_a.json")
    monkeypatch.setattr(settle, "ACCOUNT_B", tmp_path / "missing_b.json")

    settle._print_comparison([_closed("A", pnl=10.0), _closed("B", pnl=20.0)])

    output = capsys.readouterr().out
    assert output.index("paired identical cohort") < output.index("raw book totals")
    assert "accounting only" in output
    assert "non-attributable" in output
