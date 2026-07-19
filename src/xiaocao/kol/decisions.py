"""Source-neutral KOL transcript judgment and safe paper-routing primitives."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


MARKET_STATUSES = {"support", "qualify", "conflict", "invalidate"}
HOUSEHOLD_ACTIONS = {"buy", "add", "hold", "reduce", "sell", "wait"}
PAPER_INSTRUMENTS = {"equity", "etf"}


class DecisionError(ValueError):
    """The proposed judgment cannot be tied safely to its evidence."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_iso(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DecisionError(f"{field} must include a timezone")
    return parsed


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(row) + "\n")


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


@dataclass(frozen=True)
class TranscriptDocument:
    path: Path
    text: str
    sha256: str

    @property
    def text_length(self) -> int:
        return len(self.text)

    def contains(self, quote: str) -> bool:
        compact_text = re.sub(r"\s+", "", self.text)
        compact_quote = re.sub(r"\s+", "", str(quote))
        return bool(compact_quote) and compact_quote in compact_text

    @classmethod
    def load(cls, path: Path | str) -> "TranscriptDocument":
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise DecisionError(f"evidence file not found: {source}")
        raw = source.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DecisionError(
                "transcript must be UTF-8 text/Markdown; convert Word files first"
            ) from exc
        return cls(path=source, text=text, sha256=hashlib.sha256(raw).hexdigest())


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
        _atomic_write_json(self.account_path, self.account)

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
                for row in _read_jsonl(self.decisions_path)
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
                "created_at": _now_iso(),
            }
            _append_jsonl(self.decisions_path, decision)
            return decision
        filled = next(
            (
                row
                for row in _read_jsonl(self.trades_path)
                if row.get("event") == "trade_filled"
                and row.get("idempotency_key") == idempotency_key
            ),
            None,
        )
        if filled:
            trade = {key: value for key, value in filled.items() if key != "event"}
            _append_jsonl(self.decisions_path, trade)
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
                    "created_at": _now_iso(),
                }
                _append_jsonl(self.decisions_path, decision)
                return decision
            if notional > float(self.account["cash"]):
                raise DecisionError("Book KOL-US forbids negative cash")
            quantity = notional / price
            post_account = json.loads(_canonical(self.account))
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
            post_account = json.loads(_canonical(self.account))
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
            "created_at": _now_iso(),
        }
        intent_event = {
            "event": "trade_intent",
            "idempotency_key": idempotency_key,
            "pre_account_sha256": hashlib.sha256(_canonical(self.account).encode()).hexdigest(),
            "post_account": post_account,
            "trade": trade,
        }
        _append_jsonl(self.trades_path, intent_event)
        self.account = post_account
        self._persist()
        _append_jsonl(self.trades_path, {"event": "trade_filled", **trade})
        _append_jsonl(self.decisions_path, trade)
        return trade

    def recover(self) -> list[dict[str, Any]]:
        """Complete interrupted intents without applying their account delta twice."""
        rows = _read_jsonl(self.trades_path)
        completed = {
            row.get("idempotency_key") for row in rows if row.get("event") == "trade_filled"
        }
        recovered = []
        for row in rows:
            if row.get("event") != "trade_intent" or row.get("idempotency_key") in completed:
                continue
            current_hash = hashlib.sha256(_canonical(self.account).encode()).hexdigest()
            post_account = row.get("post_account") or {}
            post_hash = hashlib.sha256(_canonical(post_account).encode()).hexdigest()
            if current_hash == row.get("pre_account_sha256"):
                self.account = post_account
                self._persist()
            elif current_hash != post_hash:
                raise DecisionError("Book KOL-US account diverged during trade recovery")
            trade = dict(row.get("trade") or {})
            _append_jsonl(self.trades_path, {"event": "trade_filled", **trade})
            _append_jsonl(self.decisions_path, trade)
            recovered.append(trade)
        return recovered


class DecisionPipeline:
    def __init__(
        self,
        output_dir: Path | str,
        *,
        household_context_loader: Callable[[], dict[str, Any]] | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.events_path = self.output_dir / "events.jsonl"
        self.outbox_path = self.output_dir / "household_outbox.jsonl"
        self.wechat_delivery_lock_path = self.output_dir / ".wechat_delivery.lock"
        self.book = BookKolUs(self.output_dir / "book_kol_us")
        self.household_context_loader = household_context_loader

    def _failures(self, bundle: dict[str, Any]) -> list[str]:
        failures = []
        provider = bundle.get("household_context_provider") or {}
        if provider.get("type") != "lianghui_mcp" or self.household_context_loader is None:
            failures.append("missing_household_context")
        for item in bundle.get("items") or []:
            if not (item.get("market_validation") or {}).get("facts"):
                failures.append("missing_market_data")
            if (item.get("book_kol_us") or {}).get("ticker_ambiguous"):
                failures.append("ambiguous_ticker_mapping")
            if not item.get("claims") or not item.get("actionable_signals"):
                failures.append("low_density_content")
        return list(dict.fromkeys(failures))

    def _load_household_context(self) -> tuple[dict[str, Any], str]:
        try:
            context = self.household_context_loader() if self.household_context_loader else None
            raw = _canonical(context).encode()
        except Exception as exc:
            if isinstance(exc, DecisionError):
                raise
            raise DecisionError("household context provider failed") from exc
        if not isinstance(context, dict) or any(
            not context.get(field) for field in ("family_id", "as_of", "source_reference")
        ):
            raise DecisionError(
                "household context requires family_id, as_of, and source_reference"
            )
        if not isinstance(context.get("positions"), list):
            raise DecisionError("household context positions must be a list")
        _parse_iso(context["as_of"], field="household context as_of")
        return context, hashlib.sha256(raw).hexdigest()

    def _validate_market_validation(
        self,
        validation: dict[str, Any],
        *,
        field: str,
    ) -> None:
        if validation.get("status") not in MARKET_STATUSES:
            raise DecisionError(f"{field} status is invalid")
        if not validation.get("as_of") or not validation.get("summary"):
            raise DecisionError(f"{field} requires as_of and summary")
        _parse_iso(validation["as_of"], field=f"{field}.as_of")
        currentness = validation.get("currentness") or {}
        if (
            currentness.get("latest_available") is not True
            or not currentness.get("reason")
            or not currentness.get("checked_at")
        ):
            raise DecisionError(
                f"{field} currentness requires latest_available, reason, and checked_at"
            )
        checked_at = _parse_iso(
            currentness["checked_at"], field=f"{field}.currentness.checked_at"
        )
        processing_age = datetime.now(timezone.utc) - checked_at.astimezone(timezone.utc)
        if processing_age.total_seconds() < -300 or processing_age.total_seconds() > 24 * 60 * 60:
            raise DecisionError(f"{field} currentness check is not from processing time")
        facts = validation.get("facts")
        if not isinstance(facts, list) or not facts:
            raise DecisionError(f"{field} facts must be a non-empty list")
        for fact in facts:
            if not isinstance(fact, dict) or any(
                not fact.get(required)
                for required in ("metric", "value", "observed_at", "evidence")
            ):
                raise DecisionError(
                    "each market fact requires metric, value, observed_at, and evidence"
                )
            observed_at = _parse_iso(
                fact["observed_at"], field=f"{field} market fact observed_at"
            )
            age = checked_at.astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)
            if age.total_seconds() < 0:
                raise DecisionError(f"{field} market fact is future-dated at validation time")

    def _validate_actionable_signals(self, item: dict[str, Any]) -> None:
        claim_ids = {claim.get("claim_id") for claim in item.get("claims") or []}
        for signal in item.get("actionable_signals") or []:
            signal_id = str(signal.get("signal_id") or "<unknown>")
            if signal.get("action") not in HOUSEHOLD_ACTIONS:
                raise DecisionError(f"actionable signal action is invalid: {signal_id}")
            linked = signal.get("claim_ids") or []
            if not linked or not set(linked).issubset(claim_ids):
                raise DecisionError(f"actionable signal claim_ids are invalid: {signal_id}")
            assets = signal.get("assets")
            if not isinstance(assets, list) or not assets:
                raise DecisionError(f"actionable signal assets are required: {signal_id}")
            for asset in assets:
                if (
                    not isinstance(asset, dict)
                    or not asset.get("name")
                    or not asset.get("market")
                    or not (asset.get("ticker") or asset.get("theme"))
                ):
                    raise DecisionError(
                        f"actionable signal assets require name, market, and ticker or theme: {signal_id}"
                    )
            for required in (
                "horizon", "execution", "trigger", "confidence", "falsifiers"
            ):
                if not signal.get(required):
                    raise DecisionError(
                        f"actionable signal requires {required}: {signal_id}"
                    )
            rationale = signal.get("rationale")
            rationale_keys = ("news_or_event", "fundamental", "trading")
            if not isinstance(rationale, dict) or any(
                not isinstance(rationale.get(key), list) for key in rationale_keys
            ):
                raise DecisionError(
                    f"actionable signal rationale requires three typed lists: {signal_id}"
                )
            if not any(rationale[key] for key in rationale_keys):
                raise DecisionError(f"actionable signal rationale is empty: {signal_id}")
            self._validate_market_validation(
                signal.get("current_validation") or {},
                field=f"actionable_signals[{signal_id}].current_validation",
            )

    def _validate_item(self, item: dict[str, Any]) -> TranscriptDocument:
        required = ("source", "author", "title", "published_at", "captured_at", "evidence_path")
        missing = [name for name in required if not str(item.get(name) or "").strip()]
        if missing:
            raise DecisionError(f"missing source metadata: {', '.join(missing)}")
        document = TranscriptDocument.load(item["evidence_path"])
        for claim in item.get("claims") or []:
            fields = (
                "claim_id", "quote", "reasoning", "asset_scope", "direction",
                "horizon", "confidence", "falsifiers",
            )
            if any(not claim.get(field) for field in fields):
                raise DecisionError(f"claim has missing fields: {claim.get('claim_id', '<unknown>')}")
            if not document.contains(claim["quote"]):
                raise DecisionError(f"quote not found in evidence: {claim['claim_id']}")
        self._validate_actionable_signals(item)
        self._validate_market_validation(
            item.get("market_validation") or {}, field="market_validation"
        )
        recommendation = item.get("household_recommendation") or {}
        if recommendation.get("action") not in HOUSEHOLD_ACTIONS:
            raise DecisionError("household action is invalid")
        for field in ("evidence", "confidence", "horizon", "falsifier"):
            if not recommendation.get(field):
                raise DecisionError(f"household recommendation requires {field}")
        synthesis = item.get("synthesis") or {}
        if not synthesis.get("summary") or not synthesis.get("confidence"):
            raise DecisionError("system synthesis must be explicit")
        return document

    def _validate_cross_source(self, bundle: dict[str, Any]) -> dict[str, Any]:
        claim_ids = {
            claim["claim_id"]
            for item in bundle.get("items") or []
            for claim in item.get("claims") or []
        }
        cross = bundle.get("cross_source") or {}
        for relation in [*(cross.get("agreements") or []), *(cross.get("conflicts") or [])]:
            if not relation.get("topic") or not relation.get("judgment"):
                raise DecisionError("cross-source relation requires topic and judgment")
            linked = relation.get("claim_ids") or []
            if len(linked) < 2 or not set(linked).issubset(claim_ids):
                raise DecisionError("cross-source relation has invalid claim_ids")
        return {**cross, "method": "evidence_weighted_judgment"}

    def _contextualize_household_recommendation(
        self,
        recommendation: dict[str, Any],
        actionable_signals: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        decision_view = context.get("decision_view") or {}
        positions = [
            {
                "asset_name": row.get("assetName"),
                "asset_code": row.get("assetCode"),
                "asset_type": row.get("assetType"),
                "currency": row.get("currency"),
                "current_amount": row.get("currentAmount"),
                "cost_confidence": row.get("costConfidence"),
            }
            for row in context.get("positions") or []
        ]
        def positions_for(codes: set[str]) -> list[dict[str, Any]]:
            return [
                row for row in positions
                if str(row.get("asset_code") or "").upper() in codes
            ]

        relevant_codes = {
            str(value).upper() for value in recommendation.get("relevant_asset_codes") or []
        }
        contextual_signals = []
        for original in actionable_signals:
            signal = deepcopy(original)
            signal_codes = {
                str(value).upper() for value in signal.get("relevant_asset_codes") or []
            }
            matched = positions_for(signal_codes)
            signal["context_assessment"] = {
                "held": bool(matched),
                "relevant_positions": matched,
                "candidate_universe_constrained_by_holdings": False,
                "funding_plan": signal.get("funding_plan"),
            }
            contextual_signals.append(signal)
            relevant_codes.update(signal_codes)
        relevant_positions = positions_for(relevant_codes)
        excesses = list(decision_view.get("bucketExcesses") or [])
        result = dict(recommendation)
        gate = recommendation.get("avoid_add_if_bucket_excess")
        gate_triggered = bool(gate and gate in excesses)
        if result.get("action") in {"buy", "add"} and gate_triggered:
            result["context_constraint"] = (
                f"fresh household context shows {gate} above its target range"
            )
        assessment = {
            "read_at": context["as_of"],
            "cash_available_cny": decision_view.get("cashAvailable"),
            "bucket_shortfalls": decision_view.get("bucketShortfalls") or [],
            "bucket_excesses": excesses,
            "relevant_positions": relevant_positions,
            "gate_triggered": gate_triggered,
            "candidate_universe_constrained_by_holdings": False,
        }
        return result, contextual_signals, assessment

    @staticmethod
    def _notification_payload(
        *,
        author: Any,
        title: Any,
        actionable_signals: list[dict[str, Any]],
        synthesis: dict[str, Any],
        household_recommendation: dict[str, Any],
    ) -> dict[str, Any]:
        """Return only semantics that can change the reader-facing message.

        The full household snapshot remains in the audit outbox, but volatile
        amounts and internal gates must not create a new notification identity
        when the human-readable advice is unchanged.
        """
        del household_recommendation
        normalized_signals = []
        for signal in actionable_signals:
            rationale = signal.get("rationale") or {}
            validation = signal.get("current_validation") or {}
            context = signal.get("context_assessment") or {}
            normalized_signals.append(
                {
                    "action": signal.get("action"),
                    "assets": [
                        {
                            "name": asset.get("name"),
                            "ticker": asset.get("ticker"),
                        }
                        for asset in signal.get("assets") or []
                    ],
                    "execution": signal.get("execution"),
                    "trigger": signal.get("trigger"),
                    "falsifiers": signal.get("falsifiers") or [],
                    "rationale": {
                        "news_or_event": rationale.get("news_or_event") or [],
                        "fundamental": rationale.get("fundamental") or [],
                        "trading": rationale.get("trading") or [],
                    },
                    "current_validation": {
                        "summary": validation.get("summary"),
                    },
                    "funding_plan": signal.get("funding_plan")
                    or context.get("funding_plan"),
                    "held": bool(context.get("held")),
                }
            )
        return {
            "author": author,
            "title": title,
            "actionable_signals": normalized_signals,
            "synthesis": {"summary": synthesis.get("summary")},
        }

    @staticmethod
    def _notification_identity(
        evidence_sha256: str,
        *,
        revision: Any,
        payload: dict[str, Any],
    ) -> str:
        advisory = {"revision": revision, **payload}
        return hashlib.sha256(
            f"{evidence_sha256}\n{_canonical(advisory)}".encode()
        ).hexdigest()

    def process(self, bundle: dict[str, Any]) -> dict[str, Any]:
        failures = self._failures(bundle)
        if failures:
            result = {"status": "failed", "failures": failures, "processed_at": _now_iso()}
            _append_jsonl(self.events_path, {"event": "processing_failed", **result})
            return result
        household_context, household_context_sha256 = self._load_household_context()
        cross_source = self._validate_cross_source(bundle)
        validated = []
        for item in bundle.get("items") or []:
            document = self._validate_item(item)
            self.book.validate(item.get("book_kol_us") or {})
            validated.append((item, document))
        self.book.recover()
        existing_book_keys = {
            row.get("idempotency_key") for row in _read_jsonl(self.book.decisions_path)
        }
        with tempfile.TemporaryDirectory(prefix="kol-book-plan-") as temporary:
            planned_book = BookKolUs(Path(temporary))
            planned_book.account = deepcopy(self.book.account)
            for item, document in validated:
                if document.sha256 in existing_book_keys:
                    continue
                planned_book.route(
                    item["book_kol_us"],
                    idempotency_key=document.sha256,
                    evidence=str(document.path),
                    evidence_context={
                        "evidence_sha256": document.sha256,
                        "claim_ids": [claim["claim_id"] for claim in item["claims"]],
                        "market_validation": item["market_validation"],
                    },
                )
        outbox_rows = _read_jsonl(self.outbox_path)
        known_notifications = {row.get("idempotency_key") for row in outbox_rows}
        delivered_notifications = {
            row.get("idempotency_key"): row
            for row in _read_jsonl(self.events_path)
            if row.get("event") == "notification_delivered"
        }
        results = []
        for item, document in validated:
            paper_identity = document.sha256
            contextual_advice, contextual_signals, context_assessment = (
                self._contextualize_household_recommendation(
                    item["household_recommendation"],
                    item["actionable_signals"],
                    household_context,
                )
            )
            notification_payload = self._notification_payload(
                author=item["author"],
                title=item["title"],
                actionable_signals=contextual_signals,
                synthesis=item["synthesis"],
                household_recommendation=contextual_advice,
            )
            desired_identity = self._notification_identity(
                document.sha256,
                revision=item.get("notification_revision"),
                payload=notification_payload,
            )
            equivalent_prior = next(
                (
                    row for row in outbox_rows
                    if row.get("evidence_sha256") == document.sha256
                    and row.get("notification_revision") == item.get("notification_revision")
                    and self._notification_payload(
                        author=row.get("author"),
                        title=row.get("title"),
                        actionable_signals=row.get("actionable_signals") or [],
                        synthesis=row.get("system_synthesis") or {},
                        household_recommendation=row.get("household_recommendation") or {},
                    ) == notification_payload
                ),
                None,
            )
            identity = str(
                (equivalent_prior or {}).get("idempotency_key") or desired_identity
            )
            replay = identity in known_notifications
            message = {
                "idempotency_key": identity,
                "channel": "wechat",
                "status": "pending",
                "author": item["author"],
                "title": item["title"],
                "evidence": str(document.path),
                "evidence_sha256": document.sha256,
                "notification_revision": item.get("notification_revision"),
                "kol_claims": item["claims"],
                "actionable_signals": contextual_signals,
                "system_synthesis": item["synthesis"],
                "market_validation": item["market_validation"],
                "household_recommendation": contextual_advice,
                "household_context_assessment": context_assessment,
                "household_context": {
                    "family_id": household_context["family_id"],
                    "as_of": household_context["as_of"],
                    "source_reference": household_context["source_reference"],
                    "sha256": household_context_sha256,
                },
                "created_at": _now_iso(),
            }
            if identity in delivered_notifications:
                delivery = delivered_notifications[identity]
                message.update(
                    {
                        "status": "delivered",
                        "receipt": delivery["receipt"],
                        "delivered_at": delivery["delivered_at"],
                    }
                )
            if not replay:
                _append_jsonl(self.outbox_path, message)
                outbox_rows.append(message)
                known_notifications.add(identity)
            paper = self.book.route(
                item["book_kol_us"],
                idempotency_key=paper_identity,
                evidence=str(document.path),
                evidence_context={
                    "evidence_sha256": document.sha256,
                    "claim_ids": [claim["claim_id"] for claim in item["claims"]],
                    "market_validation": item["market_validation"],
                },
            )
            result_item = {
                **item,
                "actionable_signals": contextual_signals,
                "household_recommendation": contextual_advice,
                "household_context_assessment": context_assessment,
                "evidence_sha256": document.sha256,
                "processed_at": _now_iso(),
                "notification": message,
                "book_kol_us": paper,
                "idempotent_replay": replay,
            }
            results.append(result_item)
            _append_jsonl(
                self.events_path,
                {"event": "analysis_completed", "idempotency_key": identity, "result": result_item},
            )
        return {
            "status": "completed",
            "processed_at": _now_iso(),
            "items": results,
            "cross_source": cross_source,
        }

    def preflight(self, bundle: dict[str, Any]) -> dict[str, Any]:
        """Validate real evidence and routing intent without producing side effects."""
        failures = [
            failure for failure in self._failures(bundle) if failure != "missing_household_context"
        ]
        if failures:
            return {"status": "failed", "failures": failures}
        self._validate_cross_source(bundle)
        evidence = []
        for item in bundle.get("items") or []:
            document = self._validate_item(item)
            self.book.validate(item.get("book_kol_us") or {})
            evidence.append(
                {
                    "author": item["author"],
                    "path": str(document.path),
                    "sha256": document.sha256,
                    "claims": len(item["claims"]),
                }
            )
        if self.household_context_loader is None:
            result = {
                "status": "waiting_for_household_context",
                "evidence": evidence,
            }
        else:
            self._load_household_context()
            result = {"status": "ready", "evidence": evidence}
        _atomic_write_json(self.output_dir / "latest_preflight.json", result)
        _append_jsonl(self.events_path, {"event": "preflight_completed", **result})
        return result

    def record_delivery(self, idempotency_key: str, receipt: str) -> dict[str, Any]:
        if not str(receipt).strip():
            raise DecisionError("notification delivery receipt must not be blank")
        matching = next(
            (
                row
                for row in _read_jsonl(self.outbox_path)
                if row.get("idempotency_key") == idempotency_key
            ),
            None,
        )
        if matching is None:
            raise DecisionError("notification idempotency key not found")
        prior = next(
            (
                row
                for row in _read_jsonl(self.events_path)
                if row.get("event") == "notification_delivered"
                and row.get("idempotency_key") == idempotency_key
            ),
            None,
        )
        if prior:
            return {**prior, "idempotent_replay": True}
        event = {
            "event": "notification_delivered",
            "idempotency_key": idempotency_key,
            "channel": "wechat",
            "status": "delivered",
            "receipt": receipt,
            "delivered_at": _now_iso(),
        }
        _append_jsonl(self.events_path, event)
        return event

    def deliver_wechat(
        self,
        result: dict[str, Any],
        *,
        sender: Callable[[str, str], dict[str, str]],
    ) -> dict[str, Any]:
        """Deliver each pending item through Xiaocao's configured WeCom relay.

        Successful items are recorded immediately, so a later failure or rerun
        sends only the still-pending items.
        """
        deliveries: list[dict[str, Any]] = []
        skipped: list[str] = []
        cross_source = result.get("cross_source") or {}
        self.wechat_delivery_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.wechat_delivery_lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            events = _read_jsonl(self.events_path)
            delivered = {
                row.get("idempotency_key"): row
                for row in events
                if row.get("event") == "notification_delivered"
            }
            last_send_state: dict[str, dict[str, Any]] = {}
            for row in events:
                if row.get("event") in {
                    "notification_send_claimed",
                    "notification_send_uncertain",
                    "notification_delivered",
                }:
                    last_send_state[str(row.get("idempotency_key"))] = row
            for item in result.get("items") or []:
                notification = item.get("notification") or {}
                identity = str(notification.get("idempotency_key") or "").strip()
                if not identity:
                    raise DecisionError("notification idempotency key is missing")
                prior = delivered.get(identity)
                if prior:
                    notification.update(
                        {
                            "status": "delivered",
                            "receipt": prior["receipt"],
                            "delivered_at": prior["delivered_at"],
                        }
                    )
                    skipped.append(identity)
                    continue
                previous_state = last_send_state.get(identity) or {}
                if previous_state.get("event") in {
                    "notification_send_claimed",
                    "notification_send_uncertain",
                }:
                    raise DecisionError(
                        "WeChat delivery state is uncertain; reconcile the prior relay call "
                        f"before resending {identity}"
                    )

                title = _reader_message_title(item)
                body = render_household_item_message(item, cross_source)
                content_sha = hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()[:16]
                claim_event = {
                    "event": "notification_send_claimed",
                    "idempotency_key": identity,
                    "channel": "wechat",
                    "content_sha256": content_sha,
                    "claimed_at": _now_iso(),
                }
                _append_jsonl(self.events_path, claim_event)
                last_send_state[identity] = claim_event
                try:
                    response = sender(title, body)
                except Exception as exc:
                    raise DecisionError(
                        f"WeChat delivery outcome is uncertain for {item['author']}"
                    ) from exc
                status = response.get("wecom") if isinstance(response, dict) else None
                if status != "ok":
                    uncertain_event = {
                        "event": "notification_send_uncertain",
                        "idempotency_key": identity,
                        "channel": "wechat",
                        "status": status or "relay not configured",
                        "recorded_at": _now_iso(),
                    }
                    _append_jsonl(self.events_path, uncertain_event)
                    last_send_state[identity] = uncertain_event
                    raise DecisionError(
                        f"WeChat delivery failed for {item['author']}: "
                        f"{status or 'relay not configured'}"
                    )
                receipt = f"wecom-relay://ok/{identity}/{content_sha}"
                event = self.record_delivery(identity, receipt)
                notification.update(
                    {
                        "status": "delivered",
                        "receipt": event["receipt"],
                        "delivered_at": event["delivered_at"],
                    }
                )
                delivered[identity] = event
                last_send_state[identity] = event
                deliveries.append(event)
        return {
            "status": "delivered" if deliveries else "already_delivered",
            "deliveries": deliveries,
            "skipped": skipped,
        }


def load_bundle(path: Path | str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DecisionError("decision bundle must be a JSON object")
    return value


_ACTION_LABELS = {
    "buy": "买入",
    "add": "加仓",
    "hold": "持有",
    "reduce": "减仓",
    "sell": "卖出",
    "wait": "等待",
}
_MARKET_LABELS = {
    "support": "支持",
    "qualify": "限定支持",
    "conflict": "冲突",
    "invalidate": "失效",
}
_BUCKET_LABELS = {
    "foundation": "基石",
    "compound": "复利",
    "breakthrough": "突破",
    "trial": "试验",
}


def _reader_asset_label(signal: dict[str, Any]) -> str:
    labels = []
    for asset in signal.get("assets") or []:
        name = str(asset.get("name") or "未命名机会").strip()
        code = str(asset.get("ticker") or "").strip()
        code = re.sub(r"\.(XSHG|XSHE|BJSE)$", "", code)
        labels.append(f"{name}（{code}）" if code else name)
    return " / ".join(labels)


def _reader_signal_heading(signal: dict[str, Any]) -> str:
    prefix = {
        "buy": "机会",
        "add": "可以加仓",
        "hold": "继续持有",
        "reduce": "现在处理",
        "sell": "现在处理",
        "wait": "暂不参与",
    }.get(str(signal.get("action")), "关注")
    return f"【{prefix}：{_reader_asset_label(signal)}】"


def _reader_context_text(signal: dict[str, Any]) -> str:
    context = signal.get("context_assessment") or {}
    if context.get("held"):
        return "你现在持有相关仓位。"
    action = signal.get("action")
    if action in {"buy", "add"}:
        return "你现在没有这项持仓，但它仍然可以是新的机会。"
    if action in {"sell", "reduce"}:
        return "你现在没有这项持仓，因此不需要处理。"
    return "你现在没有这项持仓，先放在观察名单。"


def _reader_timing_label(action: Any) -> str:
    return {
        "buy": "什么时候考虑买",
        "add": "什么时候考虑加仓",
        "sell": "什么时候处理",
        "reduce": "什么时候处理",
        "hold": "接下来观察什么",
        "wait": "什么时候重新考虑",
    }.get(str(action), "什么时候行动")


def _reader_message_title(item: dict[str, Any]) -> str:
    names: list[str] = []
    for signal in item.get("actionable_signals") or []:
        for asset in signal.get("assets") or []:
            name = str(asset.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
    topic = "、".join(names[:3])
    if len(names) > 3:
        topic += "等"
    return f"投资情报｜{item['author']}" + (f"：{topic}" if topic else "")


def render_household_item_message(
    item: dict[str, Any],
    cross_source: dict[str, Any] | None = None,
) -> str:
    """Render human-readable market intelligence; internal gates stay internal."""
    lines = [
        f"先说结论：{item['synthesis']['summary']}",
    ]
    for signal in item.get("actionable_signals") or []:
        lines.extend(["", _reader_signal_heading(signal)])
        rationale = signal.get("rationale") or {}
        events = [str(value) for value in rationale.get("news_or_event") or []]
        fundamentals = [str(value) for value in rationale.get("fundamental") or []]
        trading = [str(value) for value in rationale.get("trading") or []]
        validation = signal.get("current_validation") or {}
        lines.append(
            "发生了什么："
            + ("；".join(events) if events else str(validation.get("summary")))
        )
        causal_parts = [
            *fundamentals,
            *trading,
        ]
        if causal_parts:
            lines.append(f"为什么会传导：{' → '.join(causal_parts)}")
        if events:
            lines.append(f"现在市场怎么验证：{validation.get('summary')}")
        signal_context = signal.get("context_assessment") or {}
        held_text = _reader_context_text(signal)
        funding_plan = signal.get("funding_plan") or signal_context.get("funding_plan")
        lines.append(f"对你意味着什么：{held_text}{signal['execution']}")
        if funding_plan:
            lines.append(f"资金怎么安排：{funding_plan}")
        lines.extend([
            f"{_reader_timing_label(signal.get('action'))}：{signal['trigger']}",
            f"什么情况需要重新评估：{'；'.join(str(value) for value in signal['falsifiers'])}",
        ])
    lines.extend(["", f"信息来源：{item['author']}｜{item['title']}", "这只是决策信息，不会替你执行真实交易。"])
    return "\n".join(lines)


def render_household_message(result: dict[str, Any]) -> str:
    blocks = [
        render_household_item_message(item, result.get("cross_source") or {})
        for item in result.get("items") or []
    ]
    return "\n\n---\n\n".join(blocks) + "\n"
