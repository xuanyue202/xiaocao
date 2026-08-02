#!/usr/bin/env python3
"""Read-only historical acceptance replay for one paper-trading day.

This command does not reconstruct a second trading strategy.  It replays the
recorded Book-B decision features through the production ``decide_sell_action``
function, then reconciles the results with the append-only decision journal and
paper trade ledger.  The source files are opened read-only and the optional
receipt must live outside the production live directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from xiaocao.live import accounts, paper_exit
from xiaocao.live.exit_policy import decide_sell_action


SOURCE_FILES = (
    "signal_snapshots.jsonl",
    "alerts.jsonl",
    "decision_journal.jsonl",
    "paper_trades.jsonl",
)
POLICY_ALERTS = {"SELL_TRIGGERED", "SELL_DEFERRED"}
REQUIRED_POLICY_FIELDS = {
    "alert",
    "code",
    "composite_score",
    "dd_pct",
    "dd_threshold_pct",
    "decision_phase",
    "deferred_sell_reason",
    "entry_date",
    "hard_dd_threshold_pct",
    "hold_days",
    "latest_price",
    "latest_time",
    "peak",
    "profile",
    "sell_reason",
    "strong_hold_reason",
    "t1_blocked",
    "triggered",
    "ai_event_risk_exit",
}


class ReplayError(RuntimeError):
    """The frozen evidence cannot prove a safe historical replay."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ReplayError(f"missing source file: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ReplayError(f"invalid JSONL {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ReplayError(f"expected object at {path}:{line_number}")
            rows.append(value)
    return rows


def _row_date(row: dict[str, Any]) -> str:
    for key in ("date", "market_date", "ts", "latest_time"):
        value = str(row.get(key) or "")
        if len(value) >= 10:
            return value[:10]
    return ""


def _decision_time(alert: dict[str, Any]) -> datetime:
    raw = str(alert.get("latest_time") or alert.get("ts") or "")
    if len(raw) < 19:
        raise ReplayError(
            f"missing decision timestamp for {alert.get('code')} {alert.get('alert')}"
        )
    try:
        return datetime.fromisoformat(raw[:19].replace(" ", "T"))
    except ValueError as exc:
        raise ReplayError(f"invalid decision timestamp: {raw}") from exc


def _recorded_decision(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "triggered": bool(alert.get("triggered")),
        "sell_reason": alert.get("sell_reason"),
        "deferred_sell_reason": alert.get("deferred_sell_reason"),
        "decision_phase": alert.get("decision_phase"),
    }


def _number(alert: dict[str, Any], field: str) -> float:
    try:
        return float(alert[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplayError(f"invalid policy input {field} for {alert.get('code')}") from exc


def _replay_decision(alert: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_POLICY_FIELDS - alert.keys())
    if missing:
        raise ReplayError(
            f"incomplete policy input for {alert.get('code')}: missing {', '.join(missing)}"
        )
    if alert.get("ai_event_risk_exit"):
        event_missing = sorted(
            {"ai_event_risk_event_types", "ai_event_risk_reason"} - alert.keys()
        )
        if event_missing:
            raise ReplayError(
                f"incomplete event-risk input for {alert.get('code')}: "
                f"missing {', '.join(event_missing)}"
            )
    if alert.get("strong_hold_reason"):
        raise ReplayError(
            "historical policy replay requires raw realtime detail when a strong-hold "
            f"override exists: {alert.get('code')}"
        )
    event_risk = {
        "triggered": bool(alert.get("ai_event_risk_exit")),
        "event_types": alert.get("ai_event_risk_event_types") or [],
        "reason": alert.get("ai_event_risk_reason") or "",
    }
    decision = decide_sell_action(
        {
            "profile": alert.get("profile"),
            "mode": alert.get("mode"),
            "flags": alert.get("flags"),
            "xcjw": alert.get("xcjw"),
            "jsjl": alert.get("jsjl"),
        },
        # Trigger/deferred rows record that no strong-hold override applied.
        # Raw realtime fields were not persisted historically, so an empty
        # detail is the only non-invented replay input for these decisions.
        detail={},
        latest_price=_number(alert, "latest_price"),
        peak=_number(alert, "peak"),
        dd_pct=_number(alert, "dd_pct"),
        dd_threshold=_number(alert, "dd_threshold_pct"),
        t1_blocked=bool(alert.get("t1_blocked")),
        hold_days=int(_number(alert, "hold_days")),
        signal_score=_number(alert, "composite_score"),
        event_risk=event_risk,
        hard_dd_threshold=_number(alert, "hard_dd_threshold_pct"),
        now=_decision_time(alert),
    )
    return {
        "triggered": bool(decision.get("triggered")),
        "sell_reason": decision.get("sell_reason"),
        "deferred_sell_reason": decision.get("deferred_sell_reason"),
        "decision_phase": decision.get("decision_phase"),
    }


def _journal_has_decision(
    journal_rows: list[dict[str, Any]],
    *,
    date: str,
    alert: dict[str, Any],
) -> bool:
    expected = _recorded_decision(alert)
    for row in journal_rows:
        if _row_date(row) != date:
            continue
        deterministic = row.get("deterministic")
        if not isinstance(deterministic, dict) or deterministic.get("book", "B") != "B":
            continue
        positions = deterministic.get("positions") or []
        for position in positions:
            if not isinstance(position, dict) or position.get("code") != alert.get("code"):
                continue
            observed = {
                "triggered": bool(position.get("sell_reason")),
                "sell_reason": position.get("sell_reason"),
                "deferred_sell_reason": position.get("deferred_sell_reason"),
                "decision_phase": position.get("decision_phase"),
            }
            if observed == expected:
                return True
    return False


def _signal_summary(rows: list[dict[str, Any]], date: str) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if _row_date(row) == date
        and row.get("book", "B") == "B"
        and bool(row.get("is_live", True))
    ]
    states = Counter(str(row.get("mode_state") or "UNKNOWN") for row in candidates)
    return {
        "candidate_count": len(candidates),
        "codes": sorted(str(row.get("code") or "") for row in candidates),
        "executable_count": sum(bool(row.get("mode_exec_star")) for row in candidates),
        "mode_states": dict(sorted(states.items())),
    }


def _validate_trades(
    *,
    date: str,
    alerts: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    triggered = [row for row in alerts if bool(row.get("triggered"))]
    sell_trades = [
        row
        for row in trades
        if _row_date(row) == date
        and row.get("book", "B") == "B"
        and str(row.get("side") or "").upper() == "SELL"
    ]
    alert_keys = [
        (str(row.get("code") or ""), str(row.get("sell_reason") or ""))
        for row in triggered
    ]
    trade_keys = [
        (str(row.get("code") or ""), str(row.get("reason") or ""))
        for row in sell_trades
    ]
    if len(set(alert_keys)) != len(alert_keys):
        raise ReplayError("duplicate triggered sell decision in alerts ledger")
    if len(set(trade_keys)) != len(trade_keys):
        raise ReplayError("duplicate Book-B sell trade in paper ledger")
    if set(alert_keys) != set(trade_keys):
        raise ReplayError(
            f"triggered/trade mismatch: alerts={sorted(alert_keys)} trades={sorted(trade_keys)}"
        )

    by_key = {key: row for key, row in zip(trade_keys, sell_trades)}
    for key, alert in zip(alert_keys, triggered):
        trade = by_key[key]
        if abs(float(trade.get("price") or 0.0) - float(alert.get("latest_price") or 0.0)) > 1e-9:
            raise ReplayError(f"sell price mismatch for {key[0]}")
        trade_time = str(trade.get("ts") or "")
        if len(trade_time) < 19:
            raise ReplayError(f"missing trade timestamp for {key[0]}")
        if datetime.fromisoformat(trade_time[:19]) < _decision_time(alert):
            raise ReplayError(f"trade precedes decision for {key[0]}")
    return {"count": len(sell_trades), "exactly_once": True}


def replay_day(live_dir: Path, date: str) -> dict[str, Any]:
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise ReplayError(f"invalid --date: {date}") from exc

    paths = {name: live_dir / name for name in SOURCE_FILES}
    source_hashes = {name: _sha256(path) for name, path in paths.items() if path.is_file()}
    if len(source_hashes) != len(paths):
        missing = sorted(name for name, path in paths.items() if not path.is_file())
        raise ReplayError(f"missing source files: {', '.join(missing)}")

    signals = _load_jsonl(paths["signal_snapshots.jsonl"])
    alert_rows = _load_jsonl(paths["alerts.jsonl"])
    journal_rows = _load_jsonl(paths["decision_journal.jsonl"])
    trades = _load_jsonl(paths["paper_trades.jsonl"])
    alerts = [
        row
        for row in alert_rows
        if _row_date(row) == date
        and row.get("book", "B") == "B"
        and row.get("alert") in POLICY_ALERTS
    ]

    replayed: list[dict[str, Any]] = []
    for alert in alerts:
        recorded = _recorded_decision(alert)
        observed = _replay_decision(alert)
        if observed != recorded:
            raise ReplayError(
                f"policy drift for {alert.get('code')} {alert.get('alert')}: "
                f"recorded={recorded} replayed={observed}"
            )
        if not _journal_has_decision(journal_rows, date=date, alert=alert):
            raise ReplayError(
                f"decision journal mismatch for {alert.get('code')} {alert.get('alert')}"
            )
        replayed.append(observed)

    trade_summary = _validate_trades(
        date=date,
        alerts=alerts,
        trades=trades,
    )
    source_hashes_after = {name: _sha256(path) for name, path in paths.items()}
    if source_hashes_after != source_hashes:
        raise ReplayError("source ledger mutation detected during replay")

    return {
        "schema_version": 1,
        "date": date,
        "verdict": "PASS",
        "basis": "frozen_recorded_features_replayed_through_production_exit_policy",
        "source_hashes": source_hashes,
        "signals": _signal_summary(signals, date),
        "book_b": {
            "policy_replay": {
                "deferred_count": sum(bool(row.get("deferred_sell_reason")) for row in replayed),
                "matched_count": len(replayed),
                "triggered_count": sum(bool(row.get("triggered")) for row in replayed),
            },
            "sell_trades": trade_summary,
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReplayError(f"missing source file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ReplayError(f"invalid JSON source: {path}") from exc
    if not isinstance(value, dict):
        raise ReplayError(f"expected JSON object: {path}")
    return value


def _trade_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("code") or ""),
        str(row.get("reason") or row.get("sell_reason") or ""),
    )


def _ledger_hashes(sandbox_dir: Path) -> dict[str, str]:
    names = ("positions.jsonl", "paper_account.json", "paper_trades.jsonl")
    return {name: _sha256(sandbox_dir / name) for name in names}


def _execute_sandbox_twice(
    *,
    live_dir: Path,
    sandbox_dir: Path,
    date: str,
) -> dict[str, Any]:
    if sandbox_dir.exists() and any(sandbox_dir.iterdir()):
        raise ReplayError(f"sandbox directory must be absent or empty: {sandbox_dir}")
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    source_positions_path = live_dir / "positions.jsonl"
    source_account_path = live_dir / "paper_account.json"
    source_alerts_path = live_dir / "alerts.jsonl"
    source_trades_path = live_dir / "paper_trades.jsonl"
    guarded_source_paths = (
        source_positions_path,
        source_account_path,
        source_alerts_path,
        source_trades_path,
    )
    missing_sources = [str(path) for path in guarded_source_paths if not path.is_file()]
    if missing_sources:
        raise ReplayError(f"missing sandbox source files: {', '.join(missing_sources)}")
    source_hashes_before = {path.name: _sha256(path) for path in guarded_source_paths}
    source_positions = _load_jsonl(source_positions_path)
    source_account = _load_json(source_account_path)
    source_alerts = _load_jsonl(source_alerts_path)
    source_trades = _load_jsonl(source_trades_path)

    triggered = [
        row
        for row in source_alerts
        if _row_date(row) == date
        and row.get("book", "B") == "B"
        and row.get("alert") == "SELL_TRIGGERED"
        and bool(row.get("triggered"))
    ]
    if not triggered:
        raise ReplayError(f"no Book-B triggered sells to execute for {date}")
    target_keys = {_trade_key(row) for row in triggered}
    if len(target_keys) != len(triggered):
        raise ReplayError("duplicate triggered sell decision in sandbox source")
    later_book_b_trades = [
        row
        for row in source_trades
        if row.get("book", "B") == "B" and _row_date(row) > date
    ]
    if later_book_b_trades:
        raise ReplayError(
            "cannot reconstruct historical account after later Book-B trades; "
            "use an authoritative dated snapshot"
        )
    target_trades = [
        row
        for row in source_trades
        if _row_date(row) == date
        and row.get("book", "B") == "B"
        and str(row.get("side") or "").upper() == "SELL"
        and _trade_key(row) in target_keys
    ]
    if len(target_trades) != len(triggered):
        raise ReplayError("sandbox source does not have one final trade per trigger")
    source_trade_by_key = {_trade_key(row): row for row in target_trades}

    exit_fields = {
        "exit_date",
        "exit_price",
        "exit_fee",
        "exit_cash_in",
        "realized_pnl",
        "exit_reason",
    }
    seeded_positions: list[dict[str, Any]] = []
    reopened_keys: set[tuple[str, str]] = set()
    for source_position in source_positions:
        position = dict(source_position)
        key = (str(position.get("code") or ""), str(position.get("exit_reason") or ""))
        if (
            position.get("book", "B") == "B"
            and str(position.get("exit_date") or "") == date
            and key in target_keys
        ):
            position["status"] = "open"
            for field in exit_fields:
                position.pop(field, None)
            reopened_keys.add(key)
        seeded_positions.append(position)
    if reopened_keys != target_keys:
        raise ReplayError(
            f"sandbox position reconstruction mismatch: expected={sorted(target_keys)} "
            f"reopened={sorted(reopened_keys)}"
        )

    seeded_account = dict(source_account)
    try:
        seeded_account["cash"] = round(
            float(source_account.get("cash", 0.0))
            - sum(float(row["gross_notional"]) - float(row["fee"]) for row in target_trades),
            2,
        )
        seeded_account["realized_pnl"] = round(
            float(source_account.get("realized_pnl", 0.0))
            - sum(float(row["realized_pnl"]) for row in target_trades),
            2,
        )
        seeded_account["total_fees"] = round(
            float(source_account.get("total_fees", 0.0))
            - sum(float(row["fee"]) for row in target_trades),
            2,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplayError("incomplete source trade/account fields for sandbox rollback") from exc
    seeded_account.pop("last_sell_date", None)
    seeded_account.pop("updated_at", None)
    seeded_trades = [
        row
        for row in source_trades
        if not (
            _row_date(row) == date
            and row.get("book", "B") == "B"
            and str(row.get("side") or "").upper() == "SELL"
            and _trade_key(row) in target_keys
        )
    ]

    sandbox_positions = sandbox_dir / "positions.jsonl"
    sandbox_account = sandbox_dir / "paper_account.json"
    sandbox_trades = sandbox_dir / "paper_trades.jsonl"
    sandbox_alerts = sandbox_dir / "alerts.jsonl"
    sandbox_positions.write_bytes(accounts.encode_jsonl(seeded_positions))
    sandbox_account.write_bytes(accounts.encode_json(seeded_account))
    sandbox_trades.write_bytes(accounts.encode_jsonl(seeded_trades))
    sandbox_alerts.write_bytes(source_alerts_path.read_bytes())

    def _timestamp(alert: dict[str, Any]) -> str:
        return str(source_trade_by_key[_trade_key(alert)].get("ts") or "")

    execution_args = {
        "book": "B",
        "live_dir": sandbox_dir,
        "positions_path": sandbox_positions,
        "account_path": sandbox_account,
        "trades_path": sandbox_trades,
        "alerts_path": sandbox_alerts,
        "initial_capital": float(source_account.get("initial_capital", 100000.0)),
        "default_fee_rate": float(source_account.get("fee_rate", 0.0001)),
        "trade_date": date,
        "detail_provider": lambda _code: {},
        "timestamp_provider": _timestamp,
    }
    first_closed, first_blocked = paper_exit.execute_simulated_sells(
        triggered,
        **execution_args,
    )
    first_hashes = _ledger_hashes(sandbox_dir)
    second_closed, second_blocked = paper_exit.execute_simulated_sells(
        triggered,
        **execution_args,
    )
    second_hashes = _ledger_hashes(sandbox_dir)

    final_positions = _load_jsonl(sandbox_positions)
    final_account = _load_json(sandbox_account)
    final_trades = _load_jsonl(sandbox_trades)
    target_final_positions = {
        (str(row.get("code") or ""), str(row.get("exit_reason") or "")): row
        for row in final_positions
        if row.get("book", "B") == "B"
        and str(row.get("exit_date") or "") == date
        and (str(row.get("code") or ""), str(row.get("exit_reason") or "")) in target_keys
    }
    source_target_positions = {
        (str(row.get("code") or ""), str(row.get("exit_reason") or "")): row
        for row in source_positions
        if row.get("book", "B") == "B"
        and str(row.get("exit_date") or "") == date
        and (str(row.get("code") or ""), str(row.get("exit_reason") or "")) in target_keys
    }
    final_target_trades = {
        _trade_key(row): row
        for row in final_trades
        if _row_date(row) == date
        and row.get("book", "B") == "B"
        and str(row.get("side") or "").upper() == "SELL"
        and _trade_key(row) in target_keys
    }
    account_fields = (
        "initial_capital",
        "cash",
        "fee_rate",
        "realized_pnl",
        "total_fees",
        "last_sell_date",
    )
    source_final_state_matched = (
        target_final_positions == source_target_positions
        and final_target_trades == source_trade_by_key
        and all(final_account.get(field) == source_account.get(field) for field in account_fields)
    )
    if first_closed != len(triggered) or first_blocked:
        raise ReplayError(
            f"sandbox first run mismatch: closed={first_closed} blocked={first_blocked}"
        )
    if second_closed or second_blocked or first_hashes != second_hashes:
        raise ReplayError(
            "sandbox second run was not exactly-once: "
            f"closed={second_closed} blocked={second_blocked}"
        )
    if not source_final_state_matched:
        raise ReplayError("sandbox final ledger does not match authoritative final state")
    if (sandbox_dir / ".ledger_txn" / "pending.json").exists():
        raise ReplayError("sandbox ledger transaction was not fully committed")
    source_hashes_after = {path.name: _sha256(path) for path in guarded_source_paths}
    if source_hashes_after != source_hashes_before:
        raise ReplayError("authoritative source mutation detected during sandbox execution")
    return {
        "first_run_closed": first_closed,
        "first_run_blocked": first_blocked,
        "second_run_closed": second_closed,
        "second_run_blocked": second_blocked,
        "second_run_state_unchanged": first_hashes == second_hashes,
        "source_state_unchanged": source_hashes_after == source_hashes_before,
        "source_final_state_matched": source_final_state_matched,
    }


def _write_receipt(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="historical trading day, YYYY-MM-DD")
    parser.add_argument("--live-dir", type=Path, default=Path("output/live"))
    parser.add_argument("--output", type=Path, help="optional deterministic receipt outside live-dir")
    parser.add_argument(
        "--execute-sandbox-twice",
        action="store_true",
        help="reconstruct the pre-exit ledger in an isolated directory and execute twice",
    )
    parser.add_argument("--sandbox-dir", type=Path, help="empty, non-production sandbox directory")
    args = parser.parse_args()

    try:
        live_dir = args.live_dir.resolve()
        if args.output and args.output.resolve().is_relative_to(live_dir):
            raise ReplayError("--output must be outside the production live-dir")
        if bool(args.execute_sandbox_twice) != bool(args.sandbox_dir):
            raise ReplayError(
                "--execute-sandbox-twice and --sandbox-dir must be provided together"
            )
        sandbox_dir = args.sandbox_dir.resolve() if args.sandbox_dir else None
        if sandbox_dir and sandbox_dir.is_relative_to(live_dir):
            raise ReplayError("--sandbox-dir must be outside the production live-dir")
        if args.output and sandbox_dir and args.output.resolve().is_relative_to(sandbox_dir):
            raise ReplayError("--output must be outside the sandbox ledger directory")
        result = replay_day(live_dir, args.date)
        if sandbox_dir:
            result["sandbox_execution"] = _execute_sandbox_twice(
                live_dir=live_dir,
                sandbox_dir=sandbox_dir,
                date=args.date,
            )
        if args.output:
            _write_receipt(args.output.resolve(), result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ReplayError as exc:
        print(f"paper-day replay failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
