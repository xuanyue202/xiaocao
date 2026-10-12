"""Append a narrowly proved correction of an unqualified NAV pause.

This port never changes the original chain, settlements, financial postings or
order state. Any subsequent economic mark or changed peak requires a separate
review; it cannot be cleared by this repair.
"""
from __future__ import annotations

import fcntl
import json
import os
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .account_risk import AccountRiskReceipt, evaluate_account_risk
from .book_b_accounting import DATABASE, verify_observation
from .live_decision_support import digest
from .trading_execution import account_writer_lock


def _events(path: Path) -> list[dict]:
    if path.is_symlink():
        raise ValueError("RISK_REPAIR_CHAIN_SYMLINK")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    head = None
    for row in rows:
        body = {k: v for k, v in row.items() if k != "event_hash"}
        if body.get("previous_hash") != head or digest(body) != row.get("event_hash"):
            raise ValueError("RISK_REPAIR_CHAIN_INVALID")
        AccountRiskReceipt(**{**row["receipt"], "reasons": tuple(row["receipt"]["reasons"])})
        head = row["event_hash"]
    return rows


def repair_false_pause(state_dir: Path, path: Path, *, expected_head: str,
                       now: datetime, apply: bool = False) -> dict:
    """Require immutable accounting witnesses for every disqualified mark.

    The caller supplies the reviewed original head. A concurrent risk writer
    invalidates this request before any append. Dry-run is the default.
    """
    root, path = Path(state_dir).resolve(), Path(path).absolute()
    allowed = {root / "account_risk" / "live_B.jsonl",
               root.parent / "kol_policy" / "account_risk" / "live_B.jsonl"}
    if path not in allowed or path.resolve() != path:
        raise ValueError("RISK_REPAIR_CANONICAL_LEDGER_REQUIRED")
    if now.utcoffset() is None:
        raise ValueError("RISK_REPAIR_AWARE_TIME_REQUIRED")
    with account_writer_lock(root / "account_writer_locks", "primary"):
        with path.with_suffix(".lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            rows = _events(path)
            if rows and rows[-1].get("correction", {}).get("source_head") == expected_head:
                return {"status": "already_corrected", "event_hash": rows[-1]["event_hash"]}
            if not rows or rows[-1]["event_hash"] != expected_head:
                raise ValueError("RISK_REPAIR_HEAD_CHANGED")
            if datetime.fromisoformat(rows[-1]["receipt"]["asof"]) > now:
                raise ValueError("RISK_REPAIR_TIME_REGRESSION")
            first = next((i for i, row in enumerate(rows) if row["receipt"]["pause_latched"]), None)
            if first is None or first == 0:
                raise ValueError("RISK_REPAIR_UNPAUSED_ANCHOR_REQUIRED")
            anchor = rows[first - 1]["receipt"]
            peak = anchor["high_water_mark"]
            if peak is None or anchor["account_id"] != "live:B":
                raise ValueError("RISK_REPAIR_VALID_PEAK_REQUIRED")
            database = root / DATABASE
            if database.is_symlink():
                raise ValueError("RISK_REPAIR_DATABASE_SYMLINK")
            witnesses = []
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
                reports = [json.loads(body) for (body,) in db.execute("SELECT body FROM observations")]
                for row in rows[first:]:
                    receipt = row["receipt"]
                    if (receipt["account_id"] != "live:B" or not receipt["pause_latched"]
                            or receipt["high_water_mark"] != peak
                            or receipt["status"] not in {"PAUSED", "BLOCKED"}):
                        raise ValueError("RISK_REPAIR_SUBSEQUENT_ECONOMIC_STATE")
                    if receipt["nav"] is None:
                        if receipt["status"] != "BLOCKED" or receipt["drawdown_pct"] is not None:
                            raise ValueError("RISK_REPAIR_BLOCKED_RECEIPT_INVALID")
                        basis = row.get("capital_basis")
                        if basis is None:
                            raise ValueError("RISK_REPAIR_BLOCKED_ECONOMIC_BASIS_UNPROVEN")
                        asof = datetime.fromisoformat(receipt["asof"])
                        candidates = [report for report in reports
                            if report.get("logical_account_id") == "primary" and report.get("book") == "B"
                            and report.get("capital_flow_head_sha256") == basis.get("capital_flow_head_sha256")
                            and Decimal(report["risk_unit_factor"]) == Decimal(str(basis["unit_factor"]))
                            and Decimal(report["liquidation_nav"]) == Decimal(str(basis["raw_strategy_nav"]))
                            and datetime.fromisoformat(report["observed_at"]) <= asof]
                        if not candidates:
                            raise ValueError("RISK_REPAIR_BLOCKED_ECONOMIC_BASIS_UNPROVEN")
                        report = max(candidates, key=lambda item: datetime.fromisoformat(item["observed_at"]))
                        verify_observation(root, report)
                        lower = Decimal(report["conservative_risk_nav"])
                        if not lower.is_finite() or lower <= 0:
                            raise ValueError("RISK_REPAIR_BLOCKED_ECONOMIC_BASIS_UNPROVEN")
                        if report.get("status") in {"reconciled", "cash_discrepancy_tolerated"} and lower > Decimal(str(peak)):
                            raise ValueError("RISK_REPAIR_SUBSEQUENT_ECONOMIC_STATE")
                        if lower <= Decimal(str(peak)) * Decimal(".8"):
                            # Only the same witnessed incomplete mark may be
                            # ignored; a later complete loss remains a pause.
                            if (report.get("status") != "cash_reconciliation_required"
                                    or report.get("cash_integrity_proven") is not False
                                    or not any(all(report.get(k) == old.get(k) for k in
                                        ("capital_flow_head_sha256", "ownership_head_sha256", "liquidation_nav", "conservative_risk_nav", "cash", "cash_difference"))
                                        for old in reports if old["receipt_sha256"] in
                                            {w["observation_sha256"] for w in witnesses if w.get("kind") != "blocked_basis_verified"})):
                                raise ValueError("RISK_REPAIR_SUBSEQUENT_ECONOMIC_STATE")
                        witnesses.append({"event_hash": row["event_hash"],
                            "observation_sha256": report["receipt_sha256"], "kind": "blocked_basis_verified"})
                        continue
                    found = []
                    for report in reports:
                        if datetime.fromisoformat(report["observed_at"]) != datetime.fromisoformat(receipt["nav_observed_at"]):
                            continue
                        if (report.get("status") == "cash_reconciliation_required"
                                and report.get("cash_integrity_proven") is False
                                and report.get("logical_account_id") == "primary"
                                and report.get("book") == "B"
                                and Decimal(report["conservative_risk_nav"]) == Decimal(str(receipt["nav"]))
                                and report.get("capital_flow_head_sha256") ==
                                    (row.get("capital_basis") or {}).get("capital_flow_head_sha256")):
                            verify_observation(root, report)
                            found.append(report["receipt_sha256"])
                    if len(found) != 1:
                        raise ValueError("RISK_REPAIR_UNQUALIFIED_MARK_UNPROVEN")
                    witnesses.append({"event_hash": row["event_hash"], "observation_sha256": found[0]})
            if not witnesses:
                raise ValueError("RISK_REPAIR_MARK_WITNESSES_REQUIRED")
            previous = AccountRiskReceipt(**{**anchor, "reasons": tuple(anchor["reasons"])})
            receipt = evaluate_account_risk([], asof=now, account_id="live:B", initial_capital=30000,
                expected_settlement_date=rows[-1]["receipt"]["expected_settlement_date"], previous_receipt=previous)
            if receipt.pause_latched or receipt.high_water_mark != peak or "PREVIOUS_RECEIPT_INVALID" in receipt.reasons:
                raise ValueError("RISK_REPAIR_ANCHOR_INVALID")
            receipt = replace(receipt, reasons=tuple(sorted(set(receipt.reasons) |
                {"UNQUALIFIED_NAV_PAUSE_CORRECTED", "FRESH_QUALIFIED_NAV_REQUIRED"})))
            correction = {"schema_version": 1, "source_head": expected_head,
                "anchor_event_hash": rows[first - 1]["event_hash"], "invalid_marks": witnesses,
                "reviewed_at": now.astimezone(timezone.utc).isoformat(),
                "basis": "immutable_unreconciled_observations_cannot_prove_economic_drawdown"}
            event = {"receipt": receipt.as_dict(), "previous_hash": expected_head,
                "history_coverage": {}, "capital_basis": None, "correction": correction}
            event["event_hash"] = digest(event)
            if apply:
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            return {"status": "corrected" if apply else "reviewable", **event}
