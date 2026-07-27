"""Frozen evidence and scoring scaffolding for AI intelligence factors.

The cache is allowed to grow over time; the daily freeze is the immutable as-of
view used by agent scoring and forward evaluation. This prevents an EOD score
from accidentally seeing news that was unavailable at the morning decision time.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from xiaocao.live import intelligence

SHORT_DECAY = {
    "fresh_window_days": 3,
    "half_life_days": 2,
    "max_age_days": 14,
}
TREND_DECAY = {
    "fresh_window_days": 14,
    "half_life_days": 30,
    "max_age_days": 180,
}
HARD_VETO_DECAY = {
    "short_max_age_days": 30,
    "trend_max_age_days": 90,
    "ongoing_never_expires": True,
}

HARD_VETO_TAXONOMY: dict[str, tuple[str, ...]] = {
    "regulatory_listing": (
        "delisting_risk",
        "st_or_star",
        "regulatory_investigation",
        "major_regulatory_penalty",
        "exchange_public_censure",
        "ipo_or_refinancing_blocked",
    ),
    "financial_integrity": (
        "audit_opinion_adverse",
        "financial_fraud",
        "earnings_restated_down",
        "going_concern_risk",
        "debt_default",
        "liquidity_crisis",
    ),
    "legal_credit": (
        "dishonesty_enforcement",
        "restricted_high_consumption",
        "major_lawsuit_loss",
        "asset_freeze",
        "criminal_case",
    ),
    "ownership_stability": (
        "controller_forced_sell",
        "control_right_dispute",
        "pledge_liquidation_risk",
        "large_shareholder_dump",
        "lockup_expiry_shock",
    ),
    "business_break": (
        "major_contract_terminated",
        "key_customer_loss",
        "license_or_qualification_lost",
        "production_halt",
        "core_asset_disposal_distress",
        "supply_chain_blocked",
    ),
    "safety_social": (
        "major_safety_accident",
        "major_quality_incident",
        "data_security_or_privacy_case",
        "public_opinion_crisis",
    ),
    "abnormal_trading": (
        "abnormal_volatility_clarification_negative",
        "concept_hype_denial",
        "price_manipulation_risk",
        "suspension_or_resume_uncertainty",
    ),
}
HARD_VETO_EVENT_TYPES = {
    event_type
    for events in HARD_VETO_TAXONOMY.values()
    for event_type in events
}


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        return None


def _asof_dt(value: str | None = None) -> datetime:
    parsed = _parse_dt(value)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc)


def age_days(published_at: object, *, asof: str | None = None) -> float | None:
    published = _parse_dt(published_at)
    if published is None:
        return None
    delta = _asof_dt(asof) - published
    return max(0.0, delta.total_seconds() / 86400.0)


def decay_weight(
    age: float | None,
    *,
    fresh_window_days: int,
    half_life_days: int,
    max_age_days: int,
) -> float:
    if age is None:
        return 0.0
    if age > max_age_days:
        return 0.0
    if age <= fresh_window_days:
        return 1.0
    return round(0.5 ** ((age - fresh_window_days) / max(1, half_life_days)), 4)


def _candidate_context(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "code", "name", "mode", "rank_score", "primary_score", "primary_score_label",
        "quality_tag", "k_score", "p_score", "kp_star", "vb_star", "vb_rank",
        "mode_star", "mode_rank", "mode_exec_star", "mode_exec_rank",
        "mode_exec_score", "mode_exec_rank_score", "mode_exec_mode_confidence",
        "mode_exec_target_weight", "mode_state",
        "mode_state_window", "mode_return_raw", "mode_alpha_pool", "mode_alpha_pool_lcb80",
        "mode_alpha_market", "mode_alpha_market_lcb80", "mode_evidence_weighting",
        "mode_fast_health", "mode_fast_authority", "mode_fast_days", "mode_fast_signals",
        "mode_fast_alpha_pool", "mode_fast_alpha_market",
        "open", "open_pct_change", "auc_pct",
        "auc_residual_imb", "basket_price", "basket_rule", "qibaoBenchmarkKind",
        "qibaoBenchmarkLayer", "rawQibaoRank", "qibaoRankScore", "reason",
    )
    return {key: candidate.get(key) for key in keys if key in candidate}


def evidence_key(*, code: str, source: str, title: str, link: str, published_at: str) -> str:
    return intelligence.sanitize_headline("|".join([code, source, title, link, published_at]))


def freeze_rows_from_records(
    *,
    records: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    market_date: str,
    phase: str,
    universe: str,
    evidence_asof: str | None = None,
    max_items: int = 5,
) -> list[dict[str, Any]]:
    asof = evidence_asof or datetime.now(timezone.utc).isoformat(timespec="seconds")
    candidate_by_code = {str(c.get("code") or ""): c for c in candidates if c.get("code")}
    rows: list[dict[str, Any]] = []
    for record in records:
        code = str(record.get("code") or "")
        if not code:
            continue
        source = str(record.get("source") or "")
        evidence = record.get("evidence") if isinstance(record.get("evidence"), list) else []
        normalized_items: list[dict[str, Any]] = []
        for idx, item in enumerate(evidence[:max_items], 1):
            title = intelligence.sanitize_headline(str(item.get("title") or ""))
            if not title:
                continue
            published_at = str(item.get("published_at") or "")
            age = age_days(published_at, asof=asof)
            normalized_items.append({
                "evidence_id": f"ev{idx}",
                "cache_key": evidence_key(
                    code=code,
                    source=source,
                    title=title,
                    link=str(item.get("link") or ""),
                    published_at=published_at,
                ),
                "title": title,
                "link": str(item.get("link") or ""),
                "published_at": published_at,
                "source": source,
                "relevance": str(item.get("relevance") or "unclassified_news"),
                "age_days": None if age is None else round(age, 4),
                "short_decay_weight": decay_weight(age, **SHORT_DECAY),
                "trend_decay_weight": decay_weight(age, **TREND_DECAY),
            })
        rows.append({
            "schema_version": 1,
            "date": str(market_date)[:10],
            "phase": phase,
            "universe": universe,
            "code": code,
            "name": record.get("name", ""),
            "captured_at": asof,
            "evidence_asof": asof,
            "evidence_state": record.get("evidence_state") or record.get("data_quality") or "unknown",
            "data_quality": record.get("data_quality") or "unknown",
            "source": source,
            "source_url": record.get("source_url", ""),
            "candidate_context": _candidate_context(candidate_by_code.get(code, {})),
            "evidence": normalized_items,
            "evidence_count": len(normalized_items),
            "decay_config": {
                "short": SHORT_DECAY,
                "trend": TREND_DECAY,
                "hard_veto": HARD_VETO_DECAY,
            },
            "hard_veto_taxonomy_version": 1,
            "hard_veto_event_types": sorted(HARD_VETO_EVENT_TYPES),
        })
    return rows


def upsert_cache(path: Path, freeze_rows: list[dict[str, Any]]) -> None:
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = str(row.get("cache_key") or "")
            if key:
                existing[key] = row
    for freeze in freeze_rows:
        for item in freeze.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("cache_key") or "")
            if not key:
                continue
            existing[key] = {
                "schema_version": 1,
                "cache_key": key,
                "code": freeze.get("code"),
                "name": freeze.get("name"),
                "source": item.get("source"),
                "title": item.get("title"),
                "link": item.get("link"),
                "published_at": item.get("published_at"),
                "first_seen_at": existing.get(key, {}).get("first_seen_at") or freeze.get("captured_at"),
                "last_seen_at": freeze.get("captured_at"),
                "relevance": item.get("relevance"),
            }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for key in sorted(existing):
            fh.write(json.dumps(existing[key], ensure_ascii=False, default=str) + "\n")


def upsert_daily_freeze(path: Path, freeze_rows: list[dict[str, Any]]) -> None:
    if not freeze_rows:
        return
    incoming_keys = {
        (row.get("date"), row.get("phase"), row.get("universe"), row.get("code"))
        for row in freeze_rows
    }
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (row.get("date"), row.get("phase"), row.get("universe"), row.get("code"))
            if key not in incoming_keys:
                rows.append(row)
    rows.extend(freeze_rows)
    rows.sort(key=lambda r: (str(r.get("date") or ""), str(r.get("phase") or ""), str(r.get("universe") or ""), str(r.get("code") or "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def append_latency_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def write_freeze_artifacts(
    *,
    live_dir: Path,
    records: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    market_date: str,
    phase: str,
    universe: str,
    evidence_asof: str | None = None,
    elapsed_ms: int | None = None,
) -> list[dict[str, Any]]:
    freeze_rows = freeze_rows_from_records(
        records=records,
        candidates=candidates,
        market_date=market_date,
        phase=phase,
        universe=universe,
        evidence_asof=evidence_asof,
    )
    upsert_cache(live_dir / "intelligence_evidence_cache.jsonl", freeze_rows)
    upsert_daily_freeze(live_dir / f"intelligence_evidence_{market_date}.jsonl", freeze_rows)
    append_latency_event(live_dir / "intelligence_latency.jsonl", {
        "schema_version": 1,
        "date": str(market_date)[:10],
        "phase": phase,
        "universe": universe,
        "event": "evidence_freeze",
        "n_records": len(records),
        "n_candidates": len(candidates),
        "n_with_evidence": sum(1 for row in freeze_rows if int(row.get("evidence_count") or 0) > 0),
        "elapsed_ms": elapsed_ms,
        "target_ms": 20_000,
        "warn_ms": 30_000,
        "hard_timeout_ms": 60_000,
        "status": "timeout" if elapsed_ms is not None and elapsed_ms > 60_000 else "ok",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return freeze_rows


def hard_veto_schema() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "taxonomy": HARD_VETO_TAXONOMY,
        "allowed_event_types": sorted(HARD_VETO_EVENT_TYPES),
        "required_fields": [
            "event_type",
            "severity",
            "evidence_id",
            "reason",
            "event_scope",
            "confidence",
        ],
    }
