"""Evidence-shaped stock intelligence for the live loop.

This module is deliberately fetch-free. Callers may collect headlines from any
provider, but the deterministic live spine only receives normalized evidence,
authority, quality, and usage flags.
"""
from __future__ import annotations

import html
from collections import Counter
from datetime import datetime
from typing import Any

POSITIVE_TERMS = (
    "涨停", "连板", "大涨", "增持", "回购", "中标", "订单", "预增", "扭亏",
    "增长", "盈利", "签约", "突破", "获批", "龙头", "景气", "合作",
)
NEGATIVE_TERMS = (
    "跌停", "减持", "问询", "处罚", "下滑", "亏损", "风险", "终止", "诉讼",
    "异常波动", "监管", "解禁", "退市", "违约", "澄清", "下修",
)
MARKET_TERMS = ("A股", "沪指", "深成指", "创业板", "北交所", "市场", "板块", "题材")

DEFAULT_USAGE = {
    "report": True,
    "training_shadow": True,
    "buy_ranking": False,
    "paper_buy": False,
    # AI/agent review is shadow/evidence until a separately-audited rule consumes
    # it. Do not let ordinary short-score sentiment leak into Book-B exits.
    "exit_composite_input": False,
}


def sanitize_headline(text: str) -> str:
    cleaned = html.unescape(text or "").strip()
    if " - " in cleaned:
        cleaned = cleaned.split(" - ", 1)[0].strip()
    return " ".join(cleaned.split())


def headline_sentiment_score(headlines: list[dict[str, Any]]) -> float:
    if not headlines:
        return 0.0
    pos = 0
    neg = 0
    for item in headlines:
        title = str(item.get("title") or "")
        pos += sum(1 for term in POSITIVE_TERMS if term in title)
        neg += sum(1 for term in NEGATIVE_TERMS if term in title)
    raw = (pos - neg) / max(1.0, len(headlines) * 2.0)
    return max(-1.0, min(1.0, raw))


def headline_sentiment_label(score: float) -> str:
    if score >= 0.2:
        return "偏多"
    if score <= -0.2:
        return "偏空"
    return "中性"


def headline_sentiment_summary(headlines: list[dict[str, Any]], score: float) -> str:
    if not headlines:
        return "未检索到近期公开新闻标题。"
    lead = sanitize_headline(str(headlines[0].get("title") or ""))
    label = headline_sentiment_label(score)
    if label == "偏多":
        prefix = "近期公开标题偏多"
    elif label == "偏空":
        prefix = "近期公开标题偏空"
    else:
        prefix = "近期公开标题偏中性"
    if lead:
        return f"{prefix}，最新聚焦“{lead}”。"
    return f"{prefix}。"


def classify_relevance(
    title: str,
    *,
    code: str,
    name: str,
    sector_terms: list[str] | tuple[str, ...] = (),
) -> str:
    symbol = str(code).split(".", 1)[0]
    clean_title = sanitize_headline(title)
    clean_name = str(name or "").strip()
    if (clean_name and clean_name in clean_title) or (symbol and symbol in clean_title):
        return "direct_company_news"
    if any(term and term in clean_title for term in sector_terms):
        return "sector_related_news"
    if any(term in clean_title for term in MARKET_TERMS):
        return "macro_market_news"
    return "unclassified_news"


def evidence_items(
    headlines: list[dict[str, Any]],
    *,
    code: str,
    name: str,
    sector_terms: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in headlines:
        title = sanitize_headline(str(item.get("title") or ""))
        if not title:
            continue
        matched_positive = [term for term in POSITIVE_TERMS if term in title]
        matched_negative = [term for term in NEGATIVE_TERMS if term in title]
        evidence.append({
            "title": title,
            "link": str(item.get("link") or ""),
            "published_at": str(item.get("published_at") or ""),
            "relevance": classify_relevance(title, code=code, name=name, sector_terms=sector_terms),
            "matched_positive_terms": matched_positive,
            "matched_negative_terms": matched_negative,
        })
    return evidence


def _quality(headlines: list[dict[str, Any]], error: str | None) -> str:
    if error:
        return "fetch_failed"
    if headlines:
        return "ok"
    return "empty"


def _parse_score(value: Any, default: float = 0.0) -> float:
    try:
        return max(-1.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _has_value(value: Any) -> bool:
    return value not in (None, "")


def build_stock_intelligence_record(
    *,
    date: str,
    code: str,
    name: str,
    source: str,
    source_url: str,
    headlines: list[dict[str, Any]],
    fetched_at: str | None = None,
    error: str | None = None,
    sector_terms: list[str] | tuple[str, ...] = (),
    usage: dict[str, bool] | None = None,
) -> dict[str, Any]:
    clean_headlines = [
        {**item, "title": sanitize_headline(str(item.get("title") or ""))}
        for item in headlines
        if sanitize_headline(str(item.get("title") or ""))
    ]
    keyword_score = round(headline_sentiment_score(clean_headlines), 4)
    evidence = evidence_items(clean_headlines, code=code, name=name, sector_terms=sector_terms)
    relevance_counts = dict(Counter(str(item.get("relevance") or "unknown") for item in evidence))
    data_quality = _quality(clean_headlines, error)
    merged_usage = dict(DEFAULT_USAGE)
    if usage:
        merged_usage.update({str(k): bool(v) for k, v in usage.items()})
    evidence_summary = "未检索到近期公开新闻标题。"
    if clean_headlines:
        evidence_summary = f"核心标题：“{clean_headlines[0].get('title', '')}”。"
    return {
        "schema_version": 2,
        "date": str(date)[:10],
        "code": code,
        "name": name,
        "source": source,
        "source_url": source_url,
        "fetched_at": fetched_at or datetime.now().isoformat(timespec="seconds"),
        "headlines": clean_headlines,
        "evidence": evidence,
        "relevance_counts": relevance_counts,
        "keyword_score": keyword_score,
        "keyword_label": headline_sentiment_label(keyword_score),
        "keyword_summary": headline_sentiment_summary(clean_headlines, keyword_score),
        "agent_score": None,
        "agent_short_score": None,
        "agent_trend_score": None,
        "sentiment_score": 0.0,
        "score": 0.0,
        "score_source": "pending_agent_review",
        "label": "待研判",
        "summary": evidence_summary,
        "data_quality": data_quality,
        "evidence_state": "available" if data_quality == "ok" else data_quality,
        "authority": 0,
        "decision_used": False,
        "usage": merged_usage,
        "error": error or "",
    }


def apply_agent_review(record: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    has_short = any(_has_value(review.get(k)) for k in ("short_score", "agent_score", "score"))
    has_trend = _has_value(review.get("trend_score"))
    trend_score_raw = review.get("trend_score")
    trend_score = None if not has_trend else _parse_score(trend_score_raw)
    confidence = _parse_score(review.get("confidence", 0.0))
    if has_short:
        short_score = _parse_score(review.get("short_score", review.get("agent_score", review.get("score", 0.0))))
        label = str(review.get("label") or headline_sentiment_label(short_score))
        summary = str(review.get("summary") or review.get("thesis") or "")
        if not summary:
            summary = f"agent 短线研判{label}，short_score={short_score:+.2f}。"
        out.update({
            "agent_score": short_score,
            "agent_short_score": short_score,
            "sentiment_score": short_score,
            "score": short_score,
            "score_source": "agent_review",
            "short_score_source": "agent_review",
            "label": label,
            "summary": summary,
            "agent_short_confidence": confidence,
            "agent_thesis": str(review.get("thesis") or summary),
            "agent_evidence_for": list(review.get("evidence_for") or []),
            "agent_evidence_against": list(review.get("evidence_against") or []),
            "agent_risks": list(review.get("risks") or []),
            "agent_action_bias": str(review.get("action_bias") or ""),
            "agent_horizon": str(review.get("horizon") or "short"),
            "agent_reviewed_at": str(review.get("reviewed_at") or datetime.now().isoformat(timespec="seconds")),
            "agent_reviewer": str(review.get("reviewer") or "codex_agent"),
        })
        if isinstance(review.get("veto_flags"), list):
            out["veto_flags"] = list(review.get("veto_flags") or [])
        if _has_value(review.get("score_elapsed_ms")):
            out["agent_score_elapsed_ms"] = int(float(review.get("score_elapsed_ms") or 0))
        if _has_value(review.get("scorer_mode")):
            out["agent_scorer_mode"] = str(review.get("scorer_mode") or "")
        if _has_value(review.get("evidence_freeze_ref")):
            out["evidence_freeze_ref"] = str(review.get("evidence_freeze_ref") or "")
    if has_trend:
        trend_summary = str(review.get("trend_summary") or review.get("summary") or review.get("thesis") or "")
        out.update({
            "agent_trend_score": trend_score,
            "trend_score_source": "agent_review",
            "trend_label": str(review.get("trend_label") or headline_sentiment_label(trend_score or 0.0)),
            "trend_summary": trend_summary,
            "trend_thesis": str(review.get("thesis") or trend_summary),
            "agent_trend_confidence": confidence,
            "agent_trend_evidence_for": list(review.get("evidence_for") or []),
            "agent_trend_evidence_against": list(review.get("evidence_against") or []),
            "agent_trend_risks": list(review.get("risks") or []),
            "agent_trend_reviewed_at": str(review.get("reviewed_at") or datetime.now().isoformat(timespec="seconds")),
            "agent_trend_reviewer": str(review.get("reviewer") or "codex_agent"),
        })
    return out


def normalize_stock_intelligence_record(
    record: dict[str, Any],
    *,
    date: str,
    code: str,
    name: str,
    source: str = "google_news_rss",
) -> dict[str, Any]:
    out = dict(record)
    headlines = out.get("headlines") if isinstance(out.get("headlines"), list) else []
    legacy_score = _parse_score(out.get("score", out.get("sentiment_score", headline_sentiment_score(headlines))))
    error = str(out.get("error") or "")
    normalized = build_stock_intelligence_record(
        date=str(out.get("date") or date)[:10],
        code=str(out.get("code") or code),
        name=str(out.get("name") or name),
        source=str(out.get("source") or source),
        source_url=str(out.get("source_url") or ""),
        headlines=headlines,
        fetched_at=str(out.get("fetched_at") or "") or None,
        error=error or None,
        usage=out.get("usage") if isinstance(out.get("usage"), dict) else None,
    )
    normalized.update(out)
    normalized["schema_version"] = 2
    normalized["keyword_score"] = _parse_score(out.get("keyword_score", legacy_score))
    normalized["keyword_label"] = str(out.get("keyword_label") or headline_sentiment_label(normalized["keyword_score"]))
    normalized["keyword_summary"] = str(out.get("keyword_summary") or headline_sentiment_summary(headlines, normalized["keyword_score"]))
    has_short_review = str(out.get("score_source") or "") == "agent_review" and _has_value(out.get("agent_short_score", out.get("score")))
    has_trend_review = _has_value(out.get("agent_trend_score"))
    if has_short_review:
        normalized["sentiment_score"] = _parse_score(out.get("agent_short_score", out.get("score", out.get("sentiment_score", 0.0))))
        normalized["score"] = normalized["sentiment_score"]
        normalized["agent_score"] = normalized["sentiment_score"]
        normalized["agent_short_score"] = normalized["sentiment_score"]
        normalized["score_source"] = "agent_review"
        normalized["short_score_source"] = str(out.get("short_score_source") or "agent_review")
        normalized["label"] = str(out.get("label") or headline_sentiment_label(normalized["score"]))
        normalized["summary"] = str(out.get("summary") or "")
    else:
        normalized["sentiment_score"] = 0.0
        normalized["score"] = 0.0
        normalized["agent_score"] = None
        normalized["agent_short_score"] = None
        normalized["score_source"] = "pending_agent_review"
        normalized["label"] = "待研判"
        normalized["summary"] = str(out.get("summary") or normalized.get("summary") or "标题证据已记录，等待 agent 结构化研判。")
    if has_trend_review:
        normalized["agent_trend_score"] = _parse_score(out.get("agent_trend_score"))
        normalized["trend_score_source"] = str(out.get("trend_score_source") or "agent_review")
        normalized["trend_label"] = str(out.get("trend_label") or headline_sentiment_label(normalized["agent_trend_score"]))
        normalized["trend_summary"] = str(out.get("trend_summary") or "")
    normalized["data_quality"] = str(out.get("data_quality") or _quality(headlines, error or None))
    normalized["evidence_state"] = str(out.get("evidence_state") or ("available" if headlines else normalized["data_quality"]))
    normalized["authority"] = int(out.get("authority", 0) or 0)
    normalized["decision_used"] = bool(out.get("decision_used", False))
    usage = dict(DEFAULT_USAGE)
    if isinstance(out.get("usage"), dict):
        usage.update({str(k): bool(v) for k, v in out["usage"].items()})
    normalized["usage"] = usage
    if not normalized.get("evidence"):
        normalized["evidence"] = evidence_items(headlines, code=code, name=name)
    if not normalized.get("relevance_counts"):
        normalized["relevance_counts"] = dict(Counter(str(item.get("relevance") or "unknown") for item in normalized["evidence"]))
    return normalized


def short_shadow_rank_map(
    records: list[dict[str, Any]],
    *,
    threshold: float = 0.2,
) -> dict[str, dict[str, Any]]:
    """Rank bullish short-intelligence records for the E shadow A/B variant.

    This is not an official Book-B buy rule. It makes the bullish intelligence
    claim falsifiable by tagging eligible rows so forward_eval can score them.
    """
    eligible: list[dict[str, Any]] = []
    for row in records:
        code = str(row.get("code") or "")
        if not code:
            continue
        if str(row.get("score_source") or "") != "agent_review":
            continue
        try:
            score = float(row.get("agent_short_score", row.get("score", row.get("sentiment_score", 0.0))) or 0.0)
        except (TypeError, ValueError):
            continue
        quality = str(row.get("data_quality") or "legacy")
        if score >= threshold and quality in {"ok", "legacy"}:
            eligible.append(row)
    eligible.sort(key=lambda r: (
        -float(r.get("agent_short_score", r.get("score", r.get("sentiment_score", 0.0))) or 0.0),
        int(float(r.get("target_rank") or 9999)),
        str(r.get("code") or ""),
    ))
    out: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(eligible, 1):
        code = str(row.get("code") or "")
        out[code] = {
            "ai_intelligence_short_star": True,
            "ai_intelligence_short_rank": rank,
            "ai_intelligence_short_score": round(float(row.get("agent_short_score", row.get("score", row.get("sentiment_score", 0.0))) or 0.0), 4),
            "ai_intelligence_short_threshold": threshold,
            "ai_intelligence_short_surface": "shadow_ab",
            # Back-compat for existing training rows and local notebooks. New code
            # should consume ai_intelligence_short_*.
            "intelligence_long_star": True,
            "intelligence_long_rank": rank,
            "intelligence_long_score": round(float(row.get("agent_short_score", row.get("score", row.get("sentiment_score", 0.0))) or 0.0), 4),
            "intelligence_long_threshold": threshold,
            "intelligence_long_surface": "shadow_ab",
        }
    return out


def long_shadow_rank_map(
    records: list[dict[str, Any]],
    *,
    threshold: float = 0.2,
) -> dict[str, dict[str, Any]]:
    """Deprecated compatibility wrapper for the old short-factor name."""
    return short_shadow_rank_map(records, threshold=threshold)
