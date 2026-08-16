"""Shared paper-ledger SELL transaction used by live and historical runners."""
from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

from xiaocao.live import accounts
from xiaocao.live.exit_policy import sell_block_reason
from xiaocao.live.instrument_contract import (
    InstrumentContractError,
    contract_record_fields,
    contract_from_record,
    exit_fee_for,
    is_sellable,
    validate_sell_market_data,
)


DetailProvider = Callable[[str], dict[str, Any]]
TimestampProvider = Callable[[dict[str, Any]], str]


def _has_alert_recorded(
    alerts_path: Path,
    alert_type: str,
    *,
    code: str,
    entry_date: str,
    alert_date: str,
    reason: str,
    book: str,
) -> bool:
    if not alerts_path.exists():
        return False
    with alerts_path.open(encoding="utf-8") as handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if row.get("alert") != alert_type:
                continue
            if str(row.get("book") or "B") != book:
                continue
            if str(row.get("code") or "") != code:
                continue
            if str(row.get("entry_date") or "") != entry_date:
                continue
            if str(row.get("ts") or "")[:10] != alert_date:
                continue
            if str(row.get("reason") or row.get("sell_reason") or "") != reason:
                continue
            return True
    return False


def _record_sell_block(
    alerts_path: Path,
    alert: dict[str, Any],
    position: dict[str, Any],
    *,
    trade_date: str,
    reason: str,
    timestamp_provider: TimestampProvider,
    detail: str | None = None,
) -> None:
    if _has_alert_recorded(
        alerts_path,
        "SELL_BLOCKED",
        code=str(position.get("code") or ""),
        entry_date=str(position.get("entry_date") or ""),
        alert_date=trade_date,
        reason=reason,
        book=str(position.get("book") or "B"),
    ):
        return
    row: dict[str, Any] = {
        "ts": timestamp_provider(alert),
        "alert": "SELL_BLOCKED",
        "book": position.get("book") or "B",
        "reason": reason,
        "code": position.get("code"),
        "name": position.get("name", ""),
        "entry_date": position.get("entry_date"),
    }
    if detail:
        row["detail"] = detail
    accounts.append_jsonl(row, alerts_path)


def execute_simulated_sells(
    triggered_alerts: list[dict[str, Any]],
    *,
    book: str,
    live_dir: Path,
    positions_path: Path,
    account_path: Path,
    trades_path: Path,
    alerts_path: Path,
    initial_capital: float,
    default_fee_rate: float,
    trade_date: str,
    detail_provider: DetailProvider,
    timestamp_provider: TimestampProvider,
) -> tuple[int, int]:
    """Commit triggered paper sells once under the canonical ledger lock.

    Every path and time dependency is explicit so the exact production writer
    can be exercised against an isolated historical ledger without monkeypatching
    globals or touching the authoritative business state.
    """
    if not triggered_alerts:
        return 0, 0
    with accounts.ledger_lock(accounts.ledger_lock_path(live_dir)):
        accounts.recover_ledger_transaction(live_dir)
        positions = accounts.load_positions(positions_path)
        account = accounts.load_account(
            account_path,
            initial_capital,
            default_fee_rate,
        )
        closed = 0
        blocked = 0
        new_trades: list[dict[str, Any]] = []
        for alert in triggered_alerts:
            for position in positions:
                if position.get("status", "open") != "open":
                    continue
                if position.get("book", "B") != book:
                    continue
                if (
                    position.get("code") != alert.get("code")
                    or position.get("entry_date") != alert.get("entry_date")
                ):
                    continue
                shares = int(position.get("shares") or alert.get("shares") or 0)
                if shares <= 0:
                    break
                contract = None
                if position.get("instrument_contract") or position.get("instrument_type"):
                    try:
                        contract = contract_from_record(position, strict=True)
                        assert contract is not None
                    except InstrumentContractError as exc:
                        blocked += 1
                        _record_sell_block(
                            alerts_path,
                            alert,
                            position,
                            trade_date=trade_date,
                            reason="INSTRUMENT_CONTRACT_UNVERIFIED",
                            detail=str(exc),
                            timestamp_provider=timestamp_provider,
                        )
                        break
                    if shares % contract.lot_size:
                        blocked += 1
                        _record_sell_block(
                            alerts_path,
                            alert,
                            position,
                            trade_date=trade_date,
                            reason="LOT_SIZE_INVALID",
                            detail=f"shares={shares} lot_size={contract.lot_size}",
                            timestamp_provider=timestamp_provider,
                        )
                        break
                    if not is_sellable(
                        contract,
                        entry_date=str(position.get("entry_date") or ""),
                        as_of=trade_date,
                    ):
                        blocked += 1
                        _record_sell_block(
                            alerts_path,
                            alert,
                            position,
                            trade_date=trade_date,
                            reason="T1_BLOCKED",
                            detail=contract.settlement_cycle,
                            timestamp_provider=timestamp_provider,
                        )
                        break
                detail = detail_provider(str(position.get("code") or ""))
                validated_detail = None
                if contract is not None and contract.instrument_type == "etf":
                    validation = validate_sell_market_data(
                        position,
                        detail,
                        as_of=trade_date,
                    )
                    if not validation.ok:
                        blocked += 1
                        _record_sell_block(
                            alerts_path,
                            alert,
                            position,
                            trade_date=trade_date,
                            reason=validation.reason,
                            detail=dict(validation.details),
                            timestamp_provider=timestamp_provider,
                        )
                        break
                    validated_detail = validation
                blocked_reason = sell_block_reason(detail)
                if blocked_reason:
                    blocked += 1
                    _record_sell_block(
                        alerts_path,
                        alert,
                        position,
                        trade_date=trade_date,
                        reason=blocked_reason,
                        timestamp_provider=timestamp_provider,
                    )
                    break
                instrument_fields: dict[str, Any] = {}
                if contract is not None:
                    instrument_fields = contract_record_fields(contract)
                exit_price = float(
                    validated_detail.price
                    if validated_detail is not None and validated_detail.price is not None
                    else alert["latest_price"]
                )
                fee_rate = float(
                    contract.sell_fee_rate
                    if contract is not None
                    else position.get("fee_rate", account.get("fee_rate", default_fee_rate))
                )
                gross_notional = round(exit_price * shares, 2)
                exit_fee = (
                    exit_fee_for(contract, gross_notional)
                    if contract is not None
                    else round(gross_notional * fee_rate, 2)
                )
                exit_cash_in = round(gross_notional - exit_fee, 2)
                entry_cash_out = float(
                    position.get("entry_cash_out")
                    or (
                        float(position["entry_price"])
                        * shares
                        * (1 + (contract.buy_fee_rate if contract is not None else fee_rate))
                    )
                )
                realized_pnl = round(exit_cash_in - entry_cash_out, 2)
                account["cash"] = round(float(account.get("cash", 0.0)) + exit_cash_in, 2)
                account["realized_pnl"] = round(
                    float(account.get("realized_pnl", 0.0)) + realized_pnl,
                    2,
                )
                account["total_fees"] = round(
                    float(account.get("total_fees", 0.0)) + exit_fee,
                    2,
                )
                account["last_sell_date"] = trade_date
                position.update(
                    {
                        "status": "closed",
                        "exit_date": trade_date,
                        "exit_price": round(exit_price, 4),
                        "exit_fee": exit_fee,
                        "exit_cash_in": exit_cash_in,
                        "realized_pnl": realized_pnl,
                        "exit_reason": str(alert.get("sell_reason") or "TRAILING_STOP"),
                        **instrument_fields,
                    }
                )
                new_trades.append(
                    {
                        "ts": timestamp_provider(alert),
                        "date": trade_date,
                        "side": "SELL",
                        "book": book,
                        "code": position.get("code"),
                        "name": position.get("name", ""),
                        "price": round(exit_price, 4),
                        "shares": shares,
                        "gross_notional": gross_notional,
                        "fee": exit_fee,
                        "cash_after": account["cash"],
                        "realized_pnl": realized_pnl,
                        "reason": str(alert.get("sell_reason") or "TRAILING_STOP"),
                        **instrument_fields,
                    }
                )
                closed += 1
                break
        if closed:
            accounts.commit_ledger_transaction(
                live_dir=live_dir,
                positions=positions,
                positions_path=positions_path,
                account=account,
                account_path=account_path,
                new_trades=new_trades,
                trades_path=trades_path,
            )
        return closed, blocked
