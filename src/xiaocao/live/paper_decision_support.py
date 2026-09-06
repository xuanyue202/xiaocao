"""Paper-B adapters for shared risk/KOL policy; never write an account or trade.

``root`` is the repository root. Call under the paper ledger lock with the
canonical account and complete positions readback. ``now`` is the actual aware
read time, never a reconstructed 09:30 clock. ``mark_provider(code)`` supplies
an already acquired proprietary quote: code, price, observed_at, source; raw
trade/tradeDate/tradeTimestamp/_source fields are supported too. Quote clocks
must be same-China-day, nonfuture and at most 300 seconds old.

Only output/live/kol_policy/account_risk and output/live/paper_decision_support
are written. Risk tracking starts at
activation, retaining the seed floor, observed peak and latched 20% pause.
It does not claim a historical equity curve or consume live settlements.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
from dataclasses import fields, replace
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from xiaocao.live import accounts, kol_policy
from xiaocao.live.account_risk import (
    NAV_BASIS, AccountRiskReceipt, NavObservation, evaluate_account_risk,
)
from xiaocao.live.instrument_contract import (
    PROPRIETARY_SOURCES, exit_fee_for, has_explicit_instrument_contract,
)

CHINA = ZoneInfo("Asia/Shanghai")
_CODE = re.compile(r"\d{6}\.(?:XSHG|XSHE|BJSE)")
_ACCOUNT_FIELDS = ("initial_capital", "cash", "realized_pnl", "fee_rate")


def support_directory(root: Path) -> Path:
    return Path(root) / "output/live/paper_decision_support"


def risk_directory(root: Path) -> Path:
    return Path(root) / "output/live/kol_policy/account_risk"


def paper_ledger_lock(root: Path):
    """Canonical paper lock for fresh whole-account reads, including post-SELL.

    Already locked callers must not acquire it again. Risk has a separate
    inner lock, so paper_record/monitor share the order ledger -> risk.
    """
    return accounts.ledger_lock(accounts.ledger_lock_path(Path(root) / "output/live"))


def read_paper_positions(path: Path) -> list[dict]:
    """Keep malformed ledger evidence visible to risk instead of dropping it."""
    try:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    except (OSError, ValueError):
        return [{"book": None, "read_error": "PAPER_POSITIONS_INVALID"}]


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(name).unlink(missing_ok=True)


def _number(value: object, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("PAPER_NUMBER_INVALID")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        raise ValueError("PAPER_NUMBER_INVALID")
    return result


def _signed(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("PAPER_NUMBER_INVALID")
    return float(value)


def _close(left: float, right: float, reason: str) -> None:
    if not math.isfinite(left) or not math.isfinite(right) or abs(left - right) > 0.011:
        raise ValueError(reason)


def _open_lots(positions: list[dict]) -> list[dict]:
    if not isinstance(positions, list):
        raise ValueError("PAPER_POSITIONS_INVALID")
    result, keys = [], set()
    for row in positions:
        if not isinstance(row, dict) or row.get("book") not in ("A", "B", "T"):
            raise ValueError("PAPER_POSITION_BOOK_REQUIRED")
        if row["book"] != "B":
            continue
        if (row.get("exit_date") is None) != (row.get("exit_price") is None):
            raise ValueError("PAPER_POSITION_EXIT_INCONSISTENT")
        if row.get("exit_date") is not None or row.get("exit_price") is not None:
            continue
        if not _CODE.fullmatch(str(row.get("code", ""))):
            raise ValueError("PAPER_POSITION_CODE_INVALID")
        key = (row.get("entry_date"), row["code"])
        if key in keys:
            raise ValueError("PAPER_POSITION_DUPLICATE")
        keys.add(key)
        shares = _number(row.get("shares"), positive=True)
        if shares != int(shares) or shares % 100:
            raise ValueError("PAPER_POSITION_SHARES_INVALID")
        gross = _number(row.get("gross_notional"), positive=True)
        # Historical entry_price is stored at 0.001 precision; the canonical
        # cash-out, gross and entry fee remain the exact accounting basis.
        entry = _number(row.get("entry_price"), positive=True)
        if abs(shares * entry - gross) > shares * 0.0005 + 0.011:
            raise ValueError("PAPER_ENTRY_GROSS_MISMATCH")
        fee = _number(row.get("entry_fee"))
        cost = _number(row.get("entry_cash_out"), positive=True)
        _close(cost, gross + fee, "PAPER_ENTRY_COST_MISMATCH")
        result.append(row)
    return result


def _quote(row: dict, code: str, now: datetime) -> dict:
    if not isinstance(row, dict) or row.get("code") != code:
        raise ValueError("PAPER_MARK_CODE_MISMATCH")
    source = row.get("source") or row.get("_source")
    if source not in PROPRIETARY_SOURCES:
        raise ValueError("PAPER_MARK_SOURCE_INVALID")
    price = _number(row.get("price", row.get("trade")), positive=True)
    raw = row.get("observed_at") or row.get("tradeTimestamp")
    day = str(row.get("tradeDate") or "")
    if len(day) == 8 and day.isdigit():
        day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    observed = None
    try:
        observed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%H:%M:%S:%f", "%H:%M:%S", "%H%M%S"):
            try:
                clock = datetime.strptime(str(raw), fmt).time()
                observed = datetime.combine(datetime.strptime(day, "%Y-%m-%d").date(), clock, CHINA)
                break
            except ValueError:
                continue
    if observed is None or observed.utcoffset() is None:
        raise ValueError("PAPER_MARK_TIMESTAMP_INVALID")
    if day and day != observed.astimezone(CHINA).date().isoformat():
        raise ValueError("PAPER_MARK_DATE_MISMATCH")
    if (observed.astimezone(CHINA).date() != now.astimezone(CHINA).date()
            or not 0 <= (now - observed).total_seconds() <= 300):
        raise ValueError("PAPER_MARK_STALE_OR_FUTURE")
    return {"code": code, "price": price, "observed_at": observed.isoformat(), "source": source}


def fetch_paper_marks(client: object, positions: list[dict]) -> dict[str, dict]:
    """Acquire one proprietary read per open B code, at <=2/sec.

    Call before evaluating risk so ``now`` follows the actual reads. The
    monitor may instead reuse quotes it already acquired during its scan.
    Cached responses still have to pass every quote date/freshness check.
    """
    marks = {}
    for index, code in enumerate(sorted({row["code"] for row in _open_lots(positions)})):
        if index:
            time.sleep(0.6)
        try:
            payload = client.second_line_detail_info(code)
            row = payload.get(code) if isinstance(payload, dict) else None
            if row is None and isinstance(payload, dict) and payload.get("code") == code:
                row = payload
            if isinstance(payload, list):
                matching = [item for item in payload if isinstance(item, dict) and item.get("code") == code]
                row = matching[0] if len(matching) == 1 else None
            if isinstance(row, dict):
                marks[code] = {**row, "code": row.get("code", code)}
                marks[code].setdefault("_source", "xiaocao_api")
        except Exception:
            # Missing evidence becomes a persisted risk block, never entry cost.
            marks[code] = {}
    return marks


def _valuation(root: Path, account: dict, positions: list[dict], now: datetime,
               mark_provider: Callable[[str], dict]) -> dict:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("PAPER_AWARE_READ_TIME_REQUIRED")
    if not isinstance(account, dict):
        raise ValueError("PAPER_ACCOUNT_INVALID")
    if (account.get("account_id", "paper:B") != "paper:B"
            or account.get("book", "B") != "B" or account.get("runtime", "paper") != "paper"):
        raise ValueError("PAPER_ACCOUNT_ID_MISMATCH")
    capital = _number(account.get("initial_capital"), positive=True)
    cash = _number(account.get("cash"))
    realized = _signed(account.get("realized_pnl"))
    fee_rate = _number(account.get("fee_rate"))
    _number(account.get("total_fees", 0.0))
    if fee_rate >= 1 or _number(account.get("external_flow_total", 0)) != 0:
        raise ValueError("PAPER_EXTERNAL_FLOW_OR_FEE_INVALID")
    lots = _open_lots(positions)
    canonical_positions = Path(root) / "output/live/positions.jsonl"
    if canonical_positions.exists():
        stored_lots = _open_lots(read_paper_positions(canonical_positions))
        def identity(rows: list[dict]) -> list[str]:
            economic_fields = ("entry_date", "code", "shares", "entry_price", "gross_notional",
                               "entry_fee", "entry_cash_out", "fee_rate", "instrument_contract",
                               "instrument_type", "buy_fee_rate", "sell_fee_rate", "lot_size",
                               "settlement_cycle")
            return sorted(_digest({key: row.get(key) for key in economic_fields}) for row in rows)
        if identity(lots) != identity(stored_lots):
            raise ValueError("PAPER_CANONICAL_POSITIONS_MISMATCH")
    canonical = Path(root) / "output/live/paper_account.json"
    if canonical.exists():
        stored = json.loads(canonical.read_text(encoding="utf-8"))
        if not isinstance(stored, dict) or any(stored.get(key) != account.get(key) for key in _ACCOUNT_FIELDS):
            raise ValueError("PAPER_CANONICAL_ACCOUNT_MISMATCH")
        if any(stored.get(key, default) != default for key, default in
               (("book", "B"), ("runtime", "paper"), ("account_id", "paper:B"))):
            raise ValueError("PAPER_ACCOUNT_ID_MISMATCH")
    elif account.get("account_id") != "paper:B" and (lots or cash != capital or realized != 0):
        raise ValueError("PAPER_CANONICAL_ACCOUNT_REQUIRED")
    # This equation independently proves cash/cost/realized consistency and
    # zero unexplained net flow. A declared external flow always blocks.
    cost = sum(float(row["entry_cash_out"]) for row in lots)
    _close(cash + cost, capital + realized, "PAPER_ACCOUNT_EQUATION_FAILED")
    marks = {code: _quote(mark_provider(code), code, now) for code in sorted({row["code"] for row in lots})}
    market_value = liquidation = 0.0
    for lot in lots:
        gross = round(float(lot["shares"]) * marks[lot["code"]]["price"], 2)
        if has_explicit_instrument_contract(lot):
            exit_fee = exit_fee_for(lot, gross)
        else:
            # Canonical legacy B equities persist their one-way fee rate.
            lot_fee = _number(lot.get("fee_rate", fee_rate))
            if lot_fee >= 1:
                raise ValueError("PAPER_FEE_INVALID")
            exit_fee = round(gross * lot_fee, 2)
        _number(exit_fee)
        market_value += gross
        liquidation += gross - exit_fee
    nav = round(cash + liquidation, 2)
    _number(nav, positive=True)
    return {"account_id": "paper:B", "cash": cash, "initial_capital": capital,
            "realized_pnl": realized, "open_entry_cash_out": round(cost, 2),
            "market_value": round(market_value, 2), "liquidation_after_exit_fee": round(liquidation, 2),
            "total_equity_after_exit_fee": nav, "observed_at": now.isoformat(),
            "account_equation_reconciled": True, "external_flow_total": 0.0,
            "marks": list(marks.values()), "open_lots_sha256": _digest(lots),
            "account_sha256": _digest({key: account[key] for key in _ACCOUNT_FIELDS})}


def _read_bound(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("PAPER_RECEIPT_INVALID")
    payload = {key: item for key, item in value.items() if key != "receipt_sha256"}
    if value.get("receipt_sha256") != _digest(payload):
        raise ValueError("PAPER_RECEIPT_HASH_MISMATCH")
    return value


def evaluate_paper_risk(root: Path, account: dict, positions: list[dict], *, now: datetime,
                        mark_provider: Callable[[str], dict]) -> dict:
    """Persist and return a hash-bound paper:B AccountRiskReceipt plus valuation.

    The receipt contains status/deploy_factor/high_water_mark/pause_latched,
    history_basis='since_activation', valuation, and receipt_sha256. Invalid
    evidence blocks new buys. A corrupt prior head is preserved for repair;
    its BLOCKED attempt is archived without resetting the prior peak/pause.
    """
    directory = risk_directory(root)
    with accounts.ledger_lock(directory / "risk.lock"):
        prior = previous = None
        errors = []
        head = directory / "risk_latest.json"
        try:
            if head.exists():
                prior = _read_bound(head)
                previous = AccountRiskReceipt(**{field.name: prior[field.name] for field in fields(AccountRiskReceipt)})
            elif (directory / "risk_receipts").exists() and any((directory / "risk_receipts").iterdir()):
                raise ValueError("PAPER_RISK_HEAD_MISSING")
        except (OSError, ValueError, KeyError, TypeError):
            errors.append("PREVIOUS_RECEIPT_INVALID")
        valuation = observation = None
        try:
            valuation = _valuation(root, account, positions, now, mark_provider)
            observation = NavObservation(
                date=now.astimezone(CHINA).date().isoformat(),
                nav=valuation["total_equity_after_exit_fee"], account_id="paper:B",
                initial_capital=valuation["initial_capital"], external_flow_total=0.0,
                nav_basis=NAV_BASIS, status="reconciled", observed_at=now.isoformat(),
                evidence_digest=_digest(valuation),
            )
        except Exception as exc:
            reason = str(exc)
            errors.append(reason if reason.startswith("PAPER_") and len(reason) < 100 else "PAPER_VALUATION_INVALID")
        capital = account.get("initial_capital") if isinstance(account, dict) else None
        try:
            _number(capital, positive=True)
        except (ValueError, OverflowError):
            # An unreadable account must not replace the known seed/peak.
            # A different finite seed still goes to the pure mismatch gate.
            capital = previous.initial_capital if previous is not None else None
        risk = evaluate_account_risk([], current_nav=None if errors else observation,
                                     asof=now, account_id="paper:B", initial_capital=capital,
                                     previous_receipt=previous, require_settled_history=False)
        if errors:
            risk = replace(risk, reasons=tuple(sorted(set(risk.reasons) | set(errors))))
        result = risk.as_dict()
        result.update(schema_version="paper-risk.v1", book="B", runtime="paper",
                      valuation=valuation, previous_receipt_sha256=prior.get("receipt_sha256") if prior else None)
        result["receipt_sha256"] = _digest(result)
        valid_head = ("PREVIOUS_RECEIPT_INVALID" not in result["reasons"]
                      and result["asof"] and result["initial_capital"] is not None)
        if valid_head:
            # Commit the peak before its archive so a crash after the first
            # replace cannot leave an observed durable peak behind the head.
            _atomic_json(head, result)
        archive = "risk_receipts" if valid_head else "blocked_attempts"
        _atomic_json(directory / archive / (result["receipt_sha256"] + ".json"), result)
        return result


def consumption_path(root: Path, date: str, pick: str) -> Path:
    # Components are hashed so CLI strings never become filesystem traversal.
    return support_directory(root) / "consumption" / (_digest([date, pick, "paper:B"]) + ".json")


def read_consumption(root: Path, date: str, pick: str) -> dict | None:
    path = consumption_path(root, date, pick)
    return _read_bound(path) if path.exists() else None


def read_consumption_result(root: Path, date: str, pick: str) -> dict | None:
    path = consumption_path(root, date, pick).with_suffix(".result.json")
    if not path.exists():
        return None
    result = _read_bound(path)
    claim = read_consumption(root, date, pick)
    if claim is None or result.get("consumption_sha256") != claim["receipt_sha256"]:
        raise ValueError("PAPER_CONSUMPTION_RESULT_BINDING_INVALID")
    return result


def write_consumption(root: Path, date: str, pick: str, payload: dict) -> dict:
    """Write once under flock, including zero-buy outcomes; never overwrite."""
    directory = support_directory(root)
    with accounts.ledger_lock(directory / "consumption.lock"):
        existing = read_consumption(root, date, pick)
        if existing is not None:
            return existing
        result = {**payload, "schema_version": "paper-policy-consumption.v1",
                  "book": "B", "runtime": "paper", "date": date, "pick": pick}
        result["receipt_sha256"] = _digest(result)
        _atomic_json(consumption_path(root, date, pick), result)
        return result


def complete_consumption(root: Path, date: str, pick: str, *, entries: list[dict]) -> dict:
    """Bind a separate immutable terminal result to the durable consumption.

    An interrupted claimed writer is not replayed. Its existing claim remains
    reviewable even when no terminal result could be written.
    """
    with accounts.ledger_lock(support_directory(root) / "consumption.lock"):
        claim = read_consumption(root, date, pick)
        if claim is None:
            raise ValueError("PAPER_CONSUMPTION_CLAIM_REQUIRED")
        path = consumption_path(root, date, pick).with_suffix(".result.json")
        if path.exists():
            return _read_bound(path)
        result = {"schema_version": "paper-policy-result.v1", "book": "B", "runtime": "paper",
                  "date": date, "pick": pick, "consumption_sha256": claim["receipt_sha256"],
                  "status": "bought" if entries else "no_buy", "buy_count": len(entries),
                  "entries": entries}
        result["receipt_sha256"] = _digest(result)
        _atomic_json(path, result)
        return result


def apply_buy_policy(baseline: list[dict], decision: dict, risk: dict, *,
                     kill_factor: float, fee_rate: float) -> tuple[list[dict], list[dict]]:
    """Cap final baseline slots by min(KOL, risk, kill, 1), exactly once.

    Baseline allocation must use target_scale=1; never refill removed slots.
    """
    risk_factor = _number(risk.get("deploy_factor"))
    cap = min(_number(kill_factor), risk_factor, 1.0)
    selected, audit = [], []
    for original in baseline:
        row = dict(original)
        adjustment = kol_policy.buy_adjustment(decision, row["code"])
        scale = min(_number(adjustment["scale"]), cap)
        baseline_shares = int(row["mode_exec_planned_shares"])
        shares = int(math.floor(baseline_shares * scale / 100)) * 100
        if adjustment["skip"]:
            shares = 0
        reason = ("PAPER_RISK_" + str(risk.get("status")) if risk_factor == 0
                  else "KILL_SWITCH_PAUSE" if kill_factor == 0
                  else adjustment["reason"] if adjustment["skip"]
                  else "POLICY_BELOW_BOARD_LOT" if shares == 0 else adjustment["reason"])
        price = _number(row["execution_price"], positive=True)
        gross = round(shares * price, 2)
        fee = round(gross * fee_rate, 2)
        metadata = {"baseline_shares": baseline_shares, "final_shares": shares,
                    "baseline_target_weight": row.get("mode_exec_target_weight"),
                    "kol_decision_id": adjustment["decision_id"], "kol_status": decision["status"],
                    "kol_reason": adjustment["reason"],
                    "kol_decision_sha256": decision.get("decision_sha256"),
                    "kol_snapshot_sha256": _digest(decision), "kol_scale": adjustment["scale"],
                    "risk_receipt_sha256": risk["receipt_sha256"], "risk_deploy_factor": risk_factor,
                    "kill_factor": kill_factor, "effective_scale": scale, "reason": reason,
                    "gross_notional": gross, "entry_fee": fee, "entry_cash_out": round(gross + fee, 2)}
        row.update(mode_exec_planned_shares=shares, mode_exec_planned_cash_out=round(gross + fee, 2),
                   paper_decision_support=metadata)
        if "mode_exec_target_weight" in row:
            row["mode_exec_target_weight"] = float(row["mode_exec_target_weight"]) * scale
        audit.append({"code": row["code"], **metadata})
        if shares >= 100:
            selected.append(row)
    return selected, audit
