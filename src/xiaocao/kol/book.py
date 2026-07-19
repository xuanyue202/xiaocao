"""Isolated, cash-only Book KOL-US paper ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ._shared import (
    DecisionError,
    append_jsonl,
    atomic_write_json,
    canonical,
    now_iso,
    read_jsonl,
)


PAPER_INSTRUMENTS = {"equity", "etf"}


class BookKolUs:
    """An isolated, cash-only US paper ledger."""

    def __init__(self, root: Path, *, initial_cash: float = 100_000.0):
        self.root = root
        self.account_path = root / "account.json"
        self.trades_path = root / "trades.jsonl"
        self.decisions_path = root / "decisions.jsonl"
        if self.account_path.exists():
            self.account = json.loads(self.account_path.read_text(encoding="utf-8"))
        else:
            self.account = {
                "schema_version": 1,
                "book": "KOL-US",
                "paper_only": True,
                "cash": float(initial_cash),
                "positions": {},
            }

    def _persist(self) -> None:
        atomic_write_json(self.account_path, self.account)

    @staticmethod
    def intent_fingerprint(intent: dict[str, Any]) -> str:
        return hashlib.sha256(canonical(intent).encode()).hexdigest()

    @classmethod
    def decision_identity(cls, evidence_sha256: str, intent: dict[str, Any]) -> str:
        return hashlib.sha256(
            f"{evidence_sha256}\n{cls.intent_fingerprint(intent)}".encode()
        ).hexdigest()

    @staticmethod
    def _legacy_equivalent(row: dict[str, Any], intent: dict[str, Any]) -> bool:
        if intent.get("decision") == "no_trade":
            return (
                row.get("status") == "no_trade"
                and row.get("reason") == str(intent.get("reason") or "").strip()
            )
        if row.get("status") != "filled":
            return False
        return (
            row.get("ticker") == str(intent.get("ticker") or "").strip().upper()
            and row.get("side") == intent.get("side")
            and float(row.get("target_weight") or 0)
            == float(intent.get("target_weight") or 0)
            and float(row.get("price") or 0) == float(intent.get("price") or 0)
        )

    def resolve_identity(self, evidence_sha256: str, intent: dict[str, Any]) -> str:
        """Reuse an equivalent decision, while allowing material re-decisions."""
        fingerprint = self.intent_fingerprint(intent)
        for row in read_jsonl(self.decisions_path):
            context = row.get("evidence_context") or {}
            same_evidence = (
                context.get("evidence_sha256") == evidence_sha256
                or row.get("idempotency_key") == evidence_sha256
            )
            if not same_evidence:
                continue
            if context.get("paper_intent_sha256") == fingerprint:
                return str(row["idempotency_key"])
            if row.get("idempotency_key") == evidence_sha256 and self._legacy_equivalent(
                row, intent
            ):
                return str(row["idempotency_key"])
        return self.decision_identity(evidence_sha256, intent)

    def validate(self, intent: dict[str, Any]) -> None:
        if intent.get("decision") == "no_trade":
            reason = str(intent.get("reason") or "").strip()
            if not reason:
                raise DecisionError("Book KOL-US no_trade requires reason")
            return
        if intent.get("decision") != "trade":
            raise DecisionError("Book KOL-US decision must be trade or no_trade")
        if intent.get("listing_country") != "US":
            raise DecisionError("Book KOL-US listing_country must be US")
        if intent.get("instrument_type") not in PAPER_INSTRUMENTS:
            raise DecisionError("Book KOL-US instrument_type must be equity or etf")
        if intent.get("side") not in {"buy", "sell"}:
            raise DecisionError("Book KOL-US side forbids direct shorts")
        if intent.get("uses_margin"):
            raise DecisionError("Book KOL-US forbids margin")
        ticker = str(intent.get("ticker") or "").strip().upper()
        if not ticker:
            raise DecisionError("Book KOL-US requires an unambiguous ticker")
        target_weight = float(intent.get("target_weight") or 0)
        price = float(intent.get("price") or 0)
        minimum_weight = 0 if intent.get("side") == "sell" else 0.0000001
        if not minimum_weight <= target_weight <= 1 or price <= 0:
            raise DecisionError(
                "Book KOL-US requires positive buy weight, nonnegative sell weight, and weight <= 1"
            )
        if not str(intent.get("concentration_risk") or "").strip():
            raise DecisionError("Book KOL-US trade requires concentration_risk")
        if not str(intent.get("exit_or_falsifier") or "").strip():
            raise DecisionError("Book KOL-US trade requires exit_or_falsifier")

    def route(
        self,
        intent: dict[str, Any],
        *,
        idempotency_key: str,
        evidence: str,
        evidence_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.validate(intent)
        existing_decision = next(
            (
                row
                for row in read_jsonl(self.decisions_path)
                if row.get("idempotency_key") == idempotency_key
            ),
            None,
        )
        if existing_decision:
            return {**existing_decision, "idempotent_replay": True}
        if intent.get("decision") == "no_trade":
            decision = {
                "status": "no_trade",
                "book": "KOL-US",
                "paper_only": True,
                "idempotency_key": idempotency_key,
                "reason": str(intent["reason"]).strip(),
                "evidence": evidence,
                "evidence_context": evidence_context or {},
                "created_at": now_iso(),
            }
            append_jsonl(self.decisions_path, decision)
            return {**decision, "idempotent_replay": False}
        filled = next(
            (
                row
                for row in read_jsonl(self.trades_path)
                if row.get("event") == "trade_filled"
                and row.get("idempotency_key") == idempotency_key
            ),
            None,
        )
        if filled:
            trade = {key: value for key, value in filled.items() if key != "event"}
            append_jsonl(self.decisions_path, trade)
            return {**trade, "idempotent_replay": True}
        ticker = str(intent["ticker"]).strip().upper()
        target_weight = float(intent["target_weight"])
        price = float(intent["price"])
        positions = self.account["positions"]
        held = float(positions.get(ticker, {}).get("quantity", 0))
        equity = float(self.account["cash"]) + sum(
            float(row["quantity"]) * float(row["last_price"])
            for row in positions.values()
        )
        current_notional = held * price
        desired_notional = round(equity * target_weight, 2)
        if intent["side"] == "buy":
            notional = round(max(0.0, desired_notional - current_notional), 2)
            if notional == 0:
                decision = {
                    "status": "no_trade",
                    "book": "KOL-US",
                    "paper_only": True,
                    "idempotency_key": idempotency_key,
                    "reason": "position already meets or exceeds target weight",
                    "evidence": evidence,
                    "evidence_context": evidence_context or {},
                    "concentration_risk": intent["concentration_risk"],
                    "exit_or_falsifier": intent["exit_or_falsifier"],
                    "created_at": now_iso(),
                }
                append_jsonl(self.decisions_path, decision)
                return {**decision, "idempotent_replay": False}
            if notional > float(self.account["cash"]):
                raise DecisionError("Book KOL-US forbids negative cash")
            quantity = notional / price
            post_account = json.loads(canonical(self.account))
            post_account["cash"] = round(float(post_account["cash"]) - notional, 2)
            post_account["positions"][ticker] = {
                "quantity": held + quantity,
                "last_price": price,
            }
        else:
            quantity = max(0.0, (current_notional - desired_notional) / price)
            if quantity <= 0 or quantity > held:
                raise DecisionError("Book KOL-US forbids naked or direct short selling")
            notional = round(quantity * price, 2)
            post_account = json.loads(canonical(self.account))
            post_account["cash"] = round(float(post_account["cash"]) + notional, 2)
            post_account["positions"][ticker] = {
                "quantity": held - quantity,
                "last_price": price,
            }
        trade = {
            "status": "filled",
            "paper_only": True,
            "book": "KOL-US",
            "idempotency_key": idempotency_key,
            "ticker": ticker,
            "side": intent["side"],
            "quantity": quantity,
            "price": price,
            "notional": notional,
            "target_weight": target_weight,
            "concentration_risk": intent["concentration_risk"],
            "exit_or_falsifier": intent["exit_or_falsifier"],
            "evidence": evidence,
            "evidence_context": evidence_context or {},
            "created_at": now_iso(),
        }
        intent_event = {
            "event": "trade_intent",
            "idempotency_key": idempotency_key,
            "pre_account_sha256": hashlib.sha256(canonical(self.account).encode()).hexdigest(),
            "post_account": post_account,
            "trade": trade,
        }
        append_jsonl(self.trades_path, intent_event)
        self.account = post_account
        self._persist()
        append_jsonl(self.trades_path, {"event": "trade_filled", **trade})
        append_jsonl(self.decisions_path, trade)
        return {**trade, "idempotent_replay": False}

    def recover(self) -> list[dict[str, Any]]:
        """Complete interrupted intents without applying their account delta twice."""
        rows = read_jsonl(self.trades_path)
        completed = {
            row.get("idempotency_key") for row in rows if row.get("event") == "trade_filled"
        }
        recovered = []
        for row in rows:
            if row.get("event") != "trade_intent" or row.get("idempotency_key") in completed:
                continue
            current_hash = hashlib.sha256(canonical(self.account).encode()).hexdigest()
            post_account = row.get("post_account") or {}
            post_hash = hashlib.sha256(canonical(post_account).encode()).hexdigest()
            if current_hash == row.get("pre_account_sha256"):
                self.account = post_account
                self._persist()
            elif current_hash != post_hash:
                raise DecisionError("Book KOL-US account diverged during trade recovery")
            trade = dict(row.get("trade") or {})
            append_jsonl(self.trades_path, {"event": "trade_filled", **trade})
            append_jsonl(self.decisions_path, trade)
            recovered.append(trade)
        return recovered
