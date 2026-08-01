"""Source-neutral KOL transcript judgment orchestration."""

from __future__ import annotations

import hashlib
import json
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .author_profiles import AuthorIdentityError, validate_author_pronouns
from ._shared import (
    DecisionError,
    TranscriptDocument,
    append_jsonl as _append_jsonl,
    atomic_write_json as _atomic_write_json,
    canonical as _canonical,
    now_iso as _now_iso,
    parse_iso as _parse_iso,
    read_jsonl as _read_jsonl,
)
from .book import BookKolUs
from .claim_coverage import validate_claim_coverage
from .delivery import WechatDelivery
from .rendering import (
    reader_cross_source as _reader_cross_source,
    reader_market_facts as _reader_market_facts,
    reader_message_title,
    render_household_item_message,
    render_household_message,
)


MARKET_STATUSES = {"support", "qualify", "conflict", "invalidate"}
HOUSEHOLD_ACTIONS = {"buy", "add", "hold", "reduce", "sell", "wait"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}


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
            theses = (
                (item.get("investment_thesis_inventory") or {}).get("theses")
                or []
            )
            has_must_surface = any(
                isinstance(thesis, dict)
                and thesis.get("decision_relevance") == "must_surface"
                for thesis in theses
            )
            if not item.get("claims") or (
                not item.get("actionable_signals")
                and not has_must_surface
            ):
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

    def _validate_market_outlook(self, item: dict[str, Any]) -> None:
        outlook = item.get("market_outlook") or {}
        if not outlook:
            return
        claim_ids = {claim.get("claim_id") for claim in item.get("claims") or []}
        linked = outlook.get("claim_ids") or []
        if not linked or not set(linked).issubset(claim_ids):
            raise DecisionError("market outlook claim_ids are invalid")
        for field in ("scope", "current_phase", "base_case", "horizon"):
            if not str(outlook.get(field) or "").strip():
                raise DecisionError(f"market outlook requires {field}")
        if outlook.get("confidence") not in CONFIDENCE_LEVELS:
            raise DecisionError("market outlook confidence is invalid")
        for field in ("strategy", "turning_points", "falsifiers"):
            values = outlook.get(field)
            if not isinstance(values, list) or not values:
                raise DecisionError(f"market outlook requires {field}")
            if any(
                not isinstance(value, str) or not value.strip()
                for value in values
            ):
                raise DecisionError(f"market outlook {field} values must be nonblank text")
        self._validate_market_validation(
            outlook.get("current_validation") or {},
            field="market_outlook.current_validation",
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
        validate_claim_coverage(
            item,
            evidence_text=document.text,
            evidence_sha256=document.sha256,
        )
        self._validate_actionable_signals(item)
        self._validate_market_outlook(item)
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
        if synthesis.get("reader_render_mode") == "kol_context_corrected":
            claims_by_id = {
                str(claim.get("claim_id")): claim
                for claim in item.get("claims") or []
            }
            reader_quote_ids = synthesis.get("reader_quote_ids")
            normalized_reader_quote_ids = [
                str(claim_id)
                for claim_id in reader_quote_ids
            ] if isinstance(reader_quote_ids, list) else []
            if (
                not isinstance(reader_quote_ids, list)
                or not reader_quote_ids
                or len(normalized_reader_quote_ids)
                != len(set(normalized_reader_quote_ids))
                or any(
                    claim_id not in claims_by_id
                    for claim_id in normalized_reader_quote_ids
                )
            ):
                raise DecisionError(
                    "context-corrected KOL output requires unique valid reader_quote_ids"
                )
            if any(
                not str(
                    claims_by_id[claim_id].get("reader_quote") or ""
                ).strip()
                for claim_id in normalized_reader_quote_ids
            ):
                raise DecisionError(
                    "context-corrected KOL output requires every reader_quote"
                )
            analysis_points = synthesis.get("analysis_points")
            if (
                not isinstance(analysis_points, list)
                or not analysis_points
                or any(
                    not isinstance(value, str) or not value.strip()
                    for value in analysis_points
                )
                or not str(synthesis.get("system_check") or "").strip()
                or not str(synthesis.get("system_advice") or "").strip()
            ):
                raise DecisionError(
                    "context-corrected KOL output requires analysis, check, and advice"
                )
        if item.get("decision_status") == "no_actionable_signal":
            insight = item.get("reader_insight") or {}
            if insight.get("status") not in {"useful", "none"}:
                raise DecisionError(
                    "no_actionable_signal requires reader_insight useful or none"
                )
            if insight["status"] == "useful" and any(
                not str(insight.get(field) or "").strip()
                for field in ("summary", "boundary")
            ):
                raise DecisionError(
                    "useful reader_insight requires summary and boundary"
                )
            if insight["status"] == "none" and not str(
                insight.get("reason") or ""
            ).strip():
                raise DecisionError("empty reader_insight requires a reason")
        try:
            validate_author_pronouns(
                item["author"],
                reader_message_title(item),
                field="household title",
            )
            validate_author_pronouns(
                item["author"],
                render_household_item_message(item),
                field="household message",
            )
            publication = item.get("publication") or {}
            for field in ("summary", "remaining_summary", "report_body"):
                validate_author_pronouns(
                    item["author"],
                    publication.get(field),
                    field=f"publication.{field}",
                )
        except AuthorIdentityError as exc:
            raise DecisionError(str(exc)) from exc
        return document

    def _validate_cross_source(self, bundle: dict[str, Any]) -> dict[str, Any]:
        claim_authors = {
            claim["claim_id"]: item["author"]
            for item in bundle.get("items") or []
            for claim in item.get("claims") or []
        }
        cross = bundle.get("cross_source") or {}
        enriched: dict[str, Any] = {"agreements": [], "conflicts": []}
        for relation_type in ("agreements", "conflicts"):
            for relation in cross.get(relation_type) or []:
                if not relation.get("topic") or not relation.get("judgment"):
                    raise DecisionError("cross-source relation requires topic and judgment")
                linked = relation.get("claim_ids") or []
                if len(linked) < 2 or not set(linked).issubset(claim_authors):
                    raise DecisionError("cross-source relation has invalid claim_ids")
                authors = list(
                    dict.fromkeys(claim_authors[claim_id] for claim_id in linked)
                )
                if len(authors) < 2:
                    raise DecisionError(
                        "cross-source relation requires claims from distinct authors"
                    )
                enriched[relation_type].append({**relation, "authors": authors})
        return {**enriched, "method": "evidence_weighted_judgment"}

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
        claims: list[dict[str, Any]],
        actionable_signals: list[dict[str, Any]],
        market_outlook: dict[str, Any],
        synthesis: dict[str, Any],
        household_recommendation: dict[str, Any],
        cross_source: dict[str, Any],
        reader_insight: dict[str, Any] | None = None,
        reader_briefing: dict[str, Any] | None = None,
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
        visible_market_outlook: dict[str, Any] = {}
        if market_outlook:
            claim_quotes = {
                claim.get("claim_id"): claim.get("reader_quote") or claim.get("quote")
                for claim in claims
            }
            visible_market_outlook = {
                field: market_outlook.get(field)
                for field in (
                    "scope",
                    "current_phase",
                    "base_case",
                    "strategy",
                    "turning_points",
                    "horizon",
                    "confidence",
                    "falsifiers",
                )
            }
            visible_market_outlook["author_quotes"] = [
                claim_quotes[claim_id]
                for claim_id in market_outlook.get("claim_ids") or []
            ]
            validation = market_outlook.get("current_validation") or {}
            visible_market_outlook["current_validation"] = {
                "status": validation.get("status"),
                "as_of": validation.get("as_of"),
                "summary": validation.get("summary"),
                "facts": _reader_market_facts(validation),
            }
        visible_synthesis = {
            field: synthesis.get(field)
            for field in (
                "summary",
                "reader_render_mode",
                "reader_quote_ids",
                "analysis_points",
                "system_check",
                "system_advice",
            )
            if synthesis.get(field) is not None
        }
        if synthesis.get("reader_render_mode") == "kol_context_corrected":
            claims_by_id = {
                str(claim.get("claim_id")): claim
                for claim in claims
            }
            visible_synthesis["reader_quotes"] = [
                {
                    "claim_id": str(claim_id),
                    "text": claims_by_id[str(claim_id)].get("reader_quote"),
                }
                for claim_id in synthesis.get("reader_quote_ids") or []
            ]
        payload = {
            "author": author,
            "title": title,
            "actionable_signals": normalized_signals,
            "market_outlook": visible_market_outlook,
            "synthesis": visible_synthesis,
            "cross_source": cross_source,
        }
        if reader_insight:
            payload["reader_insight"] = {
                field: reader_insight.get(field)
                for field in ("status", "summary", "boundary", "reason")
                if reader_insight.get(field) is not None
            }
        if reader_briefing:
            payload["reader_briefing"] = reader_briefing
        return payload

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
                paper_identity = self.book.resolve_identity(
                    document.sha256, item["book_kol_us"]
                )
                if paper_identity in existing_book_keys:
                    continue
                planned_book.route(
                    item["book_kol_us"],
                    idempotency_key=paper_identity,
                    evidence=str(document.path),
                    evidence_context={
                        "evidence_sha256": document.sha256,
                        "paper_intent_sha256": self.book.intent_fingerprint(
                            item["book_kol_us"]
                        ),
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
            paper_identity = self.book.resolve_identity(
                document.sha256, item["book_kol_us"]
            )
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
                claims=item["claims"],
                actionable_signals=contextual_signals,
                market_outlook=item.get("market_outlook") or {},
                synthesis=item["synthesis"],
                household_recommendation=contextual_advice,
                cross_source=_reader_cross_source(item, cross_source),
                reader_insight=item.get("reader_insight"),
                reader_briefing=item.get("reader_briefing"),
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
                        claims=row.get("kol_claims") or [],
                        actionable_signals=row.get("actionable_signals") or [],
                        market_outlook=row.get("market_outlook") or {},
                        synthesis=row.get("system_synthesis") or {},
                        household_recommendation=row.get("household_recommendation") or {},
                        cross_source=row.get("cross_source_judgments") or {
                            "agreements": [],
                            "conflicts": [],
                        },
                        reader_insight=row.get("reader_insight"),
                        reader_briefing=row.get("reader_briefing"),
                    ) == notification_payload
                ),
                None,
            )
            identity = str(
                (equivalent_prior or {}).get("idempotency_key") or desired_identity
            )
            replay = identity in known_notifications
            insight = item.get("reader_insight") or {}
            content_value = item.get("content_value") or {}
            report_only = (
                content_value.get("status") == "promoted"
                and content_value.get("tier") == "report_only"
                and bool(
                    str(
                        content_value.get("no_alert_reason")
                        or content_value.get("reason")
                        or ""
                    ).strip()
                )
            )
            notification_suppressed = report_only or (
                item.get("decision_status") == "no_actionable_signal"
                and insight.get("status") == "none"
            )
            suppression_reason = (
                str(
                    content_value.get("no_alert_reason")
                    or content_value.get("reason")
                )
                if report_only
                else str(insight.get("reason"))
            )
            message = {
                "idempotency_key": identity,
                "channel": "wechat",
                "status": "suppressed" if notification_suppressed else "pending",
                "reason": (
                    suppression_reason
                    if notification_suppressed
                    else None
                ),
                "author": item["author"],
                "title": item["title"],
                "evidence": str(document.path),
                "evidence_sha256": document.sha256,
                "notification_revision": item.get("notification_revision"),
                "kol_claims": item["claims"],
                "actionable_signals": contextual_signals,
                "market_outlook": item.get("market_outlook") or {},
                "system_synthesis": item["synthesis"],
                "market_validation": item["market_validation"],
                "cross_source_judgments": _reader_cross_source(item, cross_source),
                "household_recommendation": contextual_advice,
                "decision_status": item.get("decision_status"),
                "decision_reason": item.get("decision_reason"),
                "reader_insight": item.get("reader_insight"),
                "reader_briefing": item.get("reader_briefing"),
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
                    "paper_intent_sha256": self.book.intent_fingerprint(
                        item["book_kol_us"]
                    ),
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
        """Validate evidence and intent without creating advice or paper decisions."""
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
        return WechatDelivery(
            events_path=self.events_path,
            outbox_path=self.outbox_path,
            lock_path=self.wechat_delivery_lock_path,
        ).record(idempotency_key, receipt)

    def deliver_wechat(
        self,
        result: dict[str, Any],
        *,
        sender: Callable[[str, str], dict[str, str]],
    ) -> dict[str, Any]:
        return WechatDelivery(
            events_path=self.events_path,
            outbox_path=self.outbox_path,
            lock_path=self.wechat_delivery_lock_path,
        ).deliver(result, sender=sender)


def load_bundle(path: Path | str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DecisionError("decision bundle must be a JSON object")
    return value
