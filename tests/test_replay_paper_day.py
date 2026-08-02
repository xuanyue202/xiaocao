from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "replay_paper_day.py"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(live_dir: Path, *, duplicate_trade: bool = False) -> dict[str, Path]:
    live_dir.mkdir()
    signals = live_dir / "signal_snapshots.jsonl"
    alerts = live_dir / "alerts.jsonl"
    journal = live_dir / "decision_journal.jsonl"
    trades = live_dir / "paper_trades.jsonl"
    positions = live_dir / "positions.jsonl"
    account = live_dir / "paper_account.json"

    _write_jsonl(
        signals,
        [
            {
                "date": "2026-07-31",
                "book": "B",
                "code": code,
                "name": name,
                "is_live": True,
                "mode_state": "COLD",
                "mode_exec_star": False,
                "mode_exec_target_weight": 0.0,
            }
            for code, name in [
                ("300206.XSHE", "理邦仪器"),
                ("301295.XSHE", "美硕科技"),
                ("301117.XSHE", "佳缘科技"),
            ]
        ],
    )
    _write_jsonl(
        alerts,
        [
            {
                "ts": "2026-07-31",
                "latest_time": "2026-07-31 09:36:48:000",
                "alert": "SELL_TRIGGERED",
                "book": "B",
                "code": "002173.XSHE",
                "name": "创新医疗",
                "entry_date": "2026-07-30",
                "profile": "v5",
                "latest_price": 19.29,
                "peak": 20.214,
                "dd_pct": 4.5711,
                "dd_threshold_pct": 2.0,
                "hard_dd_threshold_pct": 8.0,
                "hold_days": 1,
                "t1_blocked": False,
                "composite_score": 0.2476,
                "ai_event_risk_exit": True,
                "ai_event_risk_event_types": ["concept_hype_denial"],
                "ai_event_risk_reason": "题材兑现度不足",
                "triggered": True,
                "sell_reason": "AI_EVENT_RISK_EXIT",
                "deferred_sell_reason": None,
                "decision_phase": "event_risk",
                "strong_hold_reason": None,
            },
            {
                "ts": "2026-07-31T13:27:29",
                "latest_time": "2026-07-31 13:27:27:000",
                "alert": "SELL_DEFERRED",
                "book": "B",
                "code": "002279.XSHE",
                "name": "久其软件",
                "entry_date": "2026-07-30",
                "profile": "v5",
                "latest_price": 6.94,
                "peak": 7.1,
                "dd_pct": 2.2535,
                "dd_threshold_pct": 2.0,
                "hard_dd_threshold_pct": 8.0,
                "hold_days": 1,
                "t1_blocked": False,
                "composite_score": 0.2467,
                "ai_event_risk_exit": False,
                "triggered": False,
                "sell_reason": None,
                "deferred_sell_reason": "TRAILING_STOP",
                "decision_phase": "midday_reassessment",
                "strong_hold_reason": None,
            },
            {
                "ts": "2026-07-31",
                "latest_time": "2026-07-31 14:57:30:000",
                "alert": "SELL_TRIGGERED",
                "book": "B",
                "code": "002279.XSHE",
                "name": "久其软件",
                "entry_date": "2026-07-30",
                "profile": "v5",
                "latest_price": 6.9,
                "peak": 7.1,
                "dd_pct": 2.8169,
                "dd_threshold_pct": 2.0,
                "hard_dd_threshold_pct": 8.0,
                "hold_days": 1,
                "t1_blocked": False,
                "composite_score": 0.2184,
                "ai_event_risk_exit": False,
                "triggered": True,
                "sell_reason": "TRAILING_STOP",
                "deferred_sell_reason": None,
                "decision_phase": "eod_discipline",
                "strong_hold_reason": None,
            },
        ],
    )
    _write_jsonl(
        journal,
        [
            {
                "market_date": "2026-07-31",
                "ts": "2026-07-31T09:36:53",
                "automation": "live_monitor",
                "deterministic": {
                    "book": "B",
                    "positions": [
                        {
                            "code": "002173.XSHE",
                            "decision_phase": "event_risk",
                            "sell_reason": "AI_EVENT_RISK_EXIT",
                            "deferred_sell_reason": None,
                        }
                    ],
                },
            },
            {
                "market_date": "2026-07-31",
                "ts": "2026-07-31T13:27:29",
                "automation": "live_monitor",
                "deterministic": {
                    "book": "B",
                    "positions": [
                        {
                            "code": "002279.XSHE",
                            "decision_phase": "midday_reassessment",
                            "sell_reason": None,
                            "deferred_sell_reason": "TRAILING_STOP",
                        }
                    ],
                },
            },
            {
                "market_date": "2026-07-31",
                "ts": "2026-07-31T14:57:35",
                "automation": "live_monitor",
                "deterministic": {
                    "book": "B",
                    "positions": [
                        {
                            "code": "002279.XSHE",
                            "decision_phase": "eod_discipline",
                            "sell_reason": "TRAILING_STOP",
                            "deferred_sell_reason": None,
                        }
                    ],
                },
            },
        ],
    )
    trade_rows = [
        {
            "ts": "2026-07-31T09:36:53",
            "date": "2026-07-31",
            "book": "B",
            "side": "SELL",
            "code": "002173.XSHE",
            "name": "创新医疗",
            "price": 19.29,
            "shares": 1300,
            "gross_notional": 25077.0,
            "fee": 2.51,
            "cash_after": 75074.49,
            "realized_pnl": -1206.34,
            "reason": "AI_EVENT_RISK_EXIT",
        },
        {
            "ts": "2026-07-31T14:57:35",
            "date": "2026-07-31",
            "book": "B",
            "side": "SELL",
            "code": "002279.XSHE",
            "name": "久其软件",
            "price": 6.9,
            "shares": 4100,
            "gross_notional": 28290.0,
            "fee": 2.83,
            "cash_after": 103361.66,
            "realized_pnl": 1212.16,
            "reason": "TRAILING_STOP",
        },
    ]
    if duplicate_trade:
        trade_rows.append(dict(trade_rows[-1]))
    _write_jsonl(trades, trade_rows)
    _write_jsonl(
        positions,
        [
            {
                "book": "B",
                "status": "closed",
                "code": "002173.XSHE",
                "name": "创新医疗",
                "entry_date": "2026-07-30",
                "entry_price": 20.214,
                "entry_cash_out": 26280.83,
                "shares": 1300,
                "fee_rate": 0.0001,
                "exit_date": "2026-07-31",
                "exit_price": 19.29,
                "exit_fee": 2.51,
                "exit_cash_in": 25074.49,
                "realized_pnl": -1206.34,
                "exit_reason": "AI_EVENT_RISK_EXIT",
            },
            {
                "book": "B",
                "status": "closed",
                "code": "002279.XSHE",
                "name": "久其软件",
                "entry_date": "2026-07-30",
                "entry_price": 6.603,
                "entry_cash_out": 27075.01,
                "shares": 4100,
                "fee_rate": 0.0001,
                "exit_date": "2026-07-31",
                "exit_price": 6.9,
                "exit_fee": 2.83,
                "exit_cash_in": 28287.17,
                "realized_pnl": 1212.16,
                "exit_reason": "TRAILING_STOP",
            },
        ],
    )
    account.write_text(
        json.dumps(
            {
                "initial_capital": 100000.0,
                "cash": 103361.66,
                "fee_rate": 0.0001,
                "realized_pnl": 1005.82,
                "total_fees": 10.68,
                "last_sell_date": "2026-07-31",
                "updated_at": "2026-07-31T14:57:35",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        p.name: p
        for p in (signals, alerts, journal, trades, positions, account)
    }


def _run(
    live_dir: Path,
    receipt: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--date",
            "2026-07-31",
            "--live-dir",
            str(live_dir),
            "--output",
            str(receipt),
            *extra_args,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_replays_previous_trading_day_without_mutating_ledgers(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    source_paths = _fixture(live_dir)
    before = {name: _sha256(path) for name, path in source_paths.items()}
    receipt = tmp_path / "receipt.json"

    first = _run(live_dir, receipt)

    assert first.returncode == 0, first.stderr
    result = json.loads(receipt.read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS"
    assert result["date"] == "2026-07-31"
    assert result["signals"] == {
        "candidate_count": 3,
        "codes": ["300206.XSHE", "301117.XSHE", "301295.XSHE"],
        "executable_count": 0,
        "mode_states": {"COLD": 3},
    }
    assert result["book_b"]["policy_replay"] == {
        "deferred_count": 1,
        "matched_count": 3,
        "triggered_count": 2,
    }
    assert result["book_b"]["sell_trades"] == {
        "count": 2,
        "exactly_once": True,
    }
    assert before == {name: _sha256(path) for name, path in source_paths.items()}

    first_receipt_hash = _sha256(receipt)
    second = _run(live_dir, receipt)
    assert second.returncode == 0, second.stderr
    assert _sha256(receipt) == first_receipt_hash
    assert before == {name: _sha256(path) for name, path in source_paths.items()}


def test_cli_fails_closed_on_duplicate_sell_trade(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _fixture(live_dir, duplicate_trade=True)

    completed = _run(live_dir, tmp_path / "receipt.json")

    assert completed.returncode == 2
    assert "duplicate" in completed.stderr.lower()


def test_cli_fails_closed_when_recorded_policy_input_is_incomplete(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    paths = _fixture(live_dir)
    alert_rows = [
        json.loads(line)
        for line in paths["alerts.jsonl"].read_text(encoding="utf-8").splitlines()
    ]
    del alert_rows[0]["dd_threshold_pct"]
    _write_jsonl(paths["alerts.jsonl"], alert_rows)

    completed = _run(live_dir, tmp_path / "receipt.json")

    assert completed.returncode == 2
    assert "incomplete" in completed.stderr.lower()


def test_cli_executes_historical_sells_twice_in_isolated_ledger(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    source_paths = _fixture(live_dir)
    source_before = {name: _sha256(path) for name, path in source_paths.items()}
    sandbox_dir = tmp_path / "paper-sandbox"
    receipt = tmp_path / "sandbox-receipt.json"

    completed = _run(
        live_dir,
        receipt,
        "--execute-sandbox-twice",
        "--sandbox-dir",
        str(sandbox_dir),
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(receipt.read_text(encoding="utf-8"))
    assert result["sandbox_execution"] == {
        "first_run_closed": 2,
        "first_run_blocked": 0,
        "second_run_closed": 0,
        "second_run_blocked": 0,
        "second_run_state_unchanged": True,
        "source_state_unchanged": True,
        "source_final_state_matched": True,
    }
    sandbox_trades = [
        json.loads(line)
        for line in (sandbox_dir / "paper_trades.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [
        (row["code"], row["reason"])
        for row in sandbox_trades
        if row.get("date") == "2026-07-31" and row.get("book") == "B"
    ] == [
        ("002173.XSHE", "AI_EVENT_RISK_EXIT"),
        ("002279.XSHE", "TRAILING_STOP"),
    ]
    assert source_before == {name: _sha256(path) for name, path in source_paths.items()}
