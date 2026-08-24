"""Live daily recommendation: v5 + v6 candidates + theoretical entry/stop.

Run any time after 9:25 (集合竞价 ends) to get today's recommended stocks
side-by-side under both validated_v5 (5d max_dd 2%) and validated_v6
(3d max_dd 0.5%) scoring rules.

Output: markdown table to stdout, also written to
    output/live/recommend_YYYY-MM-DD.md

The "entry" column is today's 9:30 open price (= 9:25 集合竞价 fill price).
After running this script, the user decides which to actually buy and at what
size; record the actuals into output/live/positions.jsonl so live_monitor.py
can track them.

Usage:
    python3 scripts/live_recommend.py [--date today]
    python3 scripts/live_recommend.py --date 2026-04-28  # backtest a past day
"""
from __future__ import annotations

import argparse
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
import time as _time
from datetime import date as _date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "kronos_screen" / "scripts"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.datasource.api_source import ApiDataSource  # noqa: E402
from xiaocao.live import agent_signals, intelligence, intelligence_evidence, intelligence_policy  # noqa: E402
from xiaocao.strategy import run_strategy  # noqa: E402
from xiaocao.strategy.mode_switch import (  # noqa: E402
    annotate_candidates as annotate_mode_candidates,
    confidence_map_from_decisions,
    decide_modes as decide_mode_switches,
    fast_health_fields,
    load_live_executable_evidence,
)
from xiaocao.strategy.rules import (  # noqa: E402
    RAW_QIBAO_BENCHMARK_MODE,
    RAW_QIBAO_BENCHMARK_MODES,
    RAW_QIBAO_HIGH_OPEN_MODE,
    RAW_QIBAO_LIMITLIKE_MODE,
)
from xiaocao.utils.trading_session import A_SHARE_TZ  # noqa: E402
from quality_governor import ensure_quality_fields  # noqa: E402

OUT_DIR = ROOT / "output" / "live"
TRAINING_ROWS_FILE = OUT_DIR / "training_rows.parquet"
STOCK_SENTIMENT_FILE = OUT_DIR / "stock_sentiment.json"
STOCK_SENTIMENT_HISTORY_FILE = OUT_DIR / "stock_sentiment_history.jsonl"
POSITIONS_FILE = OUT_DIR / "positions.jsonl"
WAIT_START = time(9, 20)
WAIT_TARGET = time(9, 25, 1)
DEFAULT_MAX_CANDIDATES = 3
DEFAULT_MAX_PER_MODE = 2
DEFAULT_MAX_STANDBY = 2
DEFAULT_READY_TIMEOUT_SEC = 30.0
DEFAULT_READY_POLL_SEC = 1.0
DEFAULT_READY_CONFIRM_SEC = 8.0
DEFAULT_READY_STABLE_SAMPLES = 2
STANDBY_MAX_RANK_GAP = 3.0
_ENTRY_DETAIL_CACHE: dict[tuple[str, str], dict[str, object] | None] = {}
_MISSING_ENTRY_DETAIL = object()
BASKET_POLICY = {
    "接力低弱转1": {"premium": 2.0, "min": 1.5, "max": 2.5, "cap_pct": 10.0, "exec_cap_pct": 6.0},
    "接力低弱转2": {"premium": 1.2, "min": 0.8, "max": 1.8, "cap_pct": 8.0, "exec_cap_pct": 5.5},
    "红盘起爆主攻": {"premium": 2.0, "min": 1.5, "max": 2.5, "cap_pct": 10.0, "exec_cap_pct": 6.0},
    "方向红盘起爆": {"premium": 1.8, "min": 1.2, "max": 2.3, "cap_pct": 8.0, "exec_cap_pct": 5.5},
    RAW_QIBAO_BENCHMARK_MODE: {"premium": 1.6, "min": 1.0, "max": 2.0, "cap_pct": 6.0, "exec_cap_pct": 4.5},
    RAW_QIBAO_HIGH_OPEN_MODE: {"premium": 1.4, "min": 0.8, "max": 1.8, "cap_pct": 10.0, "exec_cap_pct": 8.0},
    RAW_QIBAO_LIMITLIKE_MODE: {"premium": 1.2, "min": 0.5, "max": 1.6, "cap_pct": 20.0, "exec_cap_pct": 18.0},
    "N字低吸": {"premium": 2.0, "min": 1.5, "max": 2.3, "cap_pct": 5.0, "exec_cap_pct": 4.0},
    "绿断低吸": {"premium": 2.0, "min": 1.5, "max": 2.0, "cap_pct": 2.0, "exec_cap_pct": 2.0},
    "红断低吸": {"premium": 2.0, "min": 1.5, "max": 2.0, "cap_pct": 2.0, "exec_cap_pct": 2.0},
    "首红断低吸": {"premium": 2.0, "min": 1.5, "max": 2.0, "cap_pct": 2.0, "exec_cap_pct": 2.0},
    "全盘低位低吸": {"premium": 0.5, "min": 0.0, "max": 0.8, "cap_pct": 1.0, "exec_cap_pct": 1.0},
    "方向低位低吸": {"premium": 2.0, "min": 1.5, "max": 2.0, "cap_pct": 2.0, "exec_cap_pct": 2.0},
    "孕线低吸": {"premium": 0.5, "min": 0.0, "max": 0.8, "cap_pct": 1.0, "exec_cap_pct": 1.0},
}
DEFAULT_BASKET_POLICY = {"premium": 1.0, "min": 0.5, "max": 1.5, "cap_pct": 2.0, "exec_cap_pct": 2.0}
PROFILES = {
    "v5": {"profile": "validated_v5", "dd_pct": 2.0, "label": "5d max_dd 2% (conservative)"},
    "v6": {"profile": "validated_v6", "dd_pct": 0.5, "label": "3d max_dd 0.5% (aggressive)"},
}
SENTIMENT_HEADERS = {"user-agent": "Mozilla/5.0 xiaocao-live-recommend/0.1"}
INTELLIGENCE_EVIDENCE_TIMEOUT_SEC = 60.0
INTELLIGENCE_CACHE_TTL_SEC = 30 * 60
POSITIVE_SENTIMENT_TERMS = intelligence.POSITIVE_TERMS
NEGATIVE_SENTIMENT_TERMS = intelligence.NEGATIVE_TERMS


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    return XiaocaoClient(
        base_url=settings.base_url, timeout=settings.timeout,
        retries=settings.retries, cache=cache,
    )


def _load_stock_sentiment_map(today_iso: str) -> dict[str, dict[str, object]]:
    if not STOCK_SENTIMENT_FILE.exists():
        return {}
    try:
        payload = json.loads(STOCK_SENTIMENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    out: dict[str, dict[str, object]] = {}

    def _ingest(item: object) -> None:
        if not isinstance(item, dict):
            return
        code = str(item.get("code") or item.get("stockId") or "").strip()
        if not code:
            return
        item_date = str(item.get("date") or item.get("tradeDate") or today_iso)[:10]
        if item_date != today_iso:
            return
        out[code] = item

    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                _ingest({"code": key, **value})
    elif isinstance(payload, list):
        for item in payload:
            _ingest(item)
    return out


def _parse_ts(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _cache_record_fresh(
    record: dict[str, object],
    date_iso: str,
    *,
    now: datetime | None = None,
    ttl_sec: int = INTELLIGENCE_CACHE_TTL_SEC,
) -> bool:
    if str(record.get("date") or "")[:10] != date_iso:
        return False
    fetched = _parse_ts(record.get("fetched_at") or record.get("last_seen_at"))
    if fetched is None:
        return False
    if now is None:
        now = datetime.now(tz=fetched.tzinfo) if fetched.tzinfo else datetime.now()
    if fetched.tzinfo and now.tzinfo is None:
        now = now.replace(tzinfo=fetched.tzinfo)
    if fetched.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    age = (now - fetched).total_seconds()
    return 0 <= age <= ttl_sec


def _load_open_book_b_position_candidates(path: Path = POSITIONS_FILE) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status", "open") != "open":
                continue
            if str(row.get("book") or "B") != "B":
                continue
            code = str(row.get("code") or "")
            name = str(row.get("name") or "")
            if not code or not name:
                continue
            rows.append({
                "code": code,
                "name": name,
                "mode": row.get("mode", ""),
                "target_set": "open_position",
                "target_rank": 9999,
                "is_open_position": True,
                "position_entry_date": row.get("entry_date"),
            })
    return rows


def _merge_intelligence_universe(
    candidates: list[dict[str, object]],
    open_positions: list[dict[str, object]],
) -> list[dict[str, object]]:
    position_by_code = {str(row.get("code") or ""): row for row in open_positions if row.get("code")}
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for candidate in candidates:
        code = str(candidate.get("code") or "")
        if not code:
            continue
        merged = dict(candidate)
        if code in position_by_code:
            merged["is_open_position"] = True
            merged["position_entry_date"] = position_by_code[code].get("position_entry_date")
        out.append(merged)
        seen.add(code)
    for row in open_positions:
        code = str(row.get("code") or "")
        if code and code not in seen:
            out.append(dict(row))
            seen.add(code)
    return out


def _carry_prior_veto_flags(record: dict[str, object], previous: object) -> None:
    if not isinstance(previous, dict):
        return
    flags = previous.get("veto_flags") or previous.get("intelligence_veto_flags")
    if isinstance(flags, list) and flags:
        record["veto_flags"] = flags
        record["prior_veto_flags_carried"] = True


def _sanitize_headline(text: str) -> str:
    return intelligence.sanitize_headline(text)


def _google_news_query(name: str, code: str) -> str:
    symbol = code.split(".", 1)[0]
    return f'"{name}" {symbol} 股票'


def _fetch_google_news_headlines(name: str, code: str, max_items: int = 5) -> tuple[str, list[dict[str, str]]]:
    query = _google_news_query(name, code)
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    try:
        response = requests.get(url, timeout=6, headers=SENTIMENT_HEADERS)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except Exception as exc:
        raise RuntimeError(f"google_news_rss_failed:{type(exc).__name__}") from exc

    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = _sanitize_headline(item.findtext("title", default=""))
        link = (item.findtext("link", default="") or "").strip()
        pub_date = (item.findtext("pubDate", default="") or "").strip()
        if not title:
            continue
        items.append({"title": title, "link": link, "published_at": pub_date})
        if len(items) >= max_items:
            break
    return url, items


def _headline_sentiment_score(headlines: list[dict[str, str]]) -> float:
    return intelligence.headline_sentiment_score(headlines)


def _headline_sentiment_label(score: float) -> str:
    return intelligence.headline_sentiment_label(score)


def _headline_sentiment_summary(headlines: list[dict[str, str]], score: float) -> str:
    return intelligence.headline_sentiment_summary(headlines, score)


def _build_top_stock_sentiment(
    top_candidates: list[dict[str, object]],
    date_iso: str,
    *,
    max_workers: int = 4,
    max_seconds: float = INTELLIGENCE_EVIDENCE_TIMEOUT_SEC,
) -> list[dict[str, object]]:
    if not top_candidates:
        return []
    existing = _load_stock_sentiment_map(date_iso)
    started = _time.monotonic()
    ordered_codes: list[str] = []
    out_by_code: dict[str, dict[str, object]] = {}
    fetch_specs: list[dict[str, object]] = []
    for candidate in top_candidates:
        code = str(candidate.get("code") or "")
        name = str(candidate.get("name") or "")
        if not code or not name:
            continue
        ordered_codes.append(code)
        current = existing.get(code)
        if current and _cache_record_fresh(current, date_iso):
            record = intelligence.normalize_stock_intelligence_record(
                dict(current),
                date=date_iso,
                code=code,
                name=name,
            )
            record["evidence_capture_state"] = "cache_hit"
        else:
            fetch_specs.append({"candidate": candidate, "code": code, "name": name, "previous": current})
            continue
        record["target_set"] = str(candidate.get("target_set") or ("vb_star" if bool(candidate.get("vb_star")) else "candidate"))
        record["target_rank"] = int(_num(candidate.get("vb_rank") or candidate.get("kp_rank") or candidate.get("target_rank") or 0))
        record["mode"] = str(candidate.get("mode") or "")
        out_by_code[code] = record

    def _fetch_record(spec: dict[str, object]) -> dict[str, object]:
        code = str(spec.get("code") or "")
        name = str(spec.get("name") or "")
        candidate = spec.get("candidate") if isinstance(spec.get("candidate"), dict) else {}
        previous = spec.get("previous")
        try:
            source_url, headlines = _fetch_google_news_headlines(name, code)
            record = intelligence.build_stock_intelligence_record(
                date=date_iso,
                code=code,
                name=name,
                source="google_news_rss",
                source_url=source_url,
                headlines=headlines,
            )
            record["evidence_capture_state"] = "fetched"
        except Exception as exc:
            record = intelligence.build_stock_intelligence_record(
                date=date_iso,
                code=code,
                name=name,
                source="google_news_rss",
                source_url="",
                headlines=[],
                error=f"{type(exc).__name__}:{exc}",
            )
            record["summary"] = f"舆情抓取失败，原因={type(exc).__name__}。"
            record["evidence_capture_state"] = "fetch_failed"
        _carry_prior_veto_flags(record, previous)
        record["target_set"] = str(candidate.get("target_set") or ("vb_star" if bool(candidate.get("vb_star")) else "candidate"))
        record["target_rank"] = int(_num(candidate.get("vb_rank") or candidate.get("kp_rank") or candidate.get("rank") or candidate.get("target_rank") or 0))
        record["mode"] = str(candidate.get("mode") or "")
        return record

    if fetch_specs:
        deadline = started + max_seconds
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futures = {pool.submit(_fetch_record, spec): spec for spec in fetch_specs}
            try:
                for fut in as_completed(futures, timeout=max(0.1, deadline - _time.monotonic())):
                    record = fut.result()
                    out_by_code[str(record.get("code") or "")] = record
                    if _time.monotonic() >= deadline:
                        break
            except FuturesTimeoutError:
                pass
            for fut, spec in futures.items():
                if fut.done():
                    continue
                fut.cancel()
                code = str(spec.get("code") or "")
                name = str(spec.get("name") or "")
                candidate = spec.get("candidate") if isinstance(spec.get("candidate"), dict) else {}
                previous = spec.get("previous")
                record = intelligence.build_stock_intelligence_record(
                    date=date_iso,
                    code=code,
                    name=name,
                    source="google_news_rss",
                    source_url="",
                    headlines=[],
                    error="evidence_capture_timeout",
                )
                record["summary"] = "舆情素材抓取超时，等待后续冻结补齐。"
                record["evidence_capture_state"] = "timeout"
                _carry_prior_veto_flags(record, previous)
                record["target_set"] = "vb_star" if bool(candidate.get("vb_star")) else "candidate"
                record["target_rank"] = int(_num(candidate.get("vb_rank") or candidate.get("kp_rank") or candidate.get("rank") or 0))
                record["mode"] = str(candidate.get("mode") or "")
                out_by_code[code] = record
    return [out_by_code[code] for code in ordered_codes if code in out_by_code]


def _write_stock_sentiment_records(records: list[dict[str, object]], date_iso: str) -> None:
    if not records:
        return
    latest = _load_stock_sentiment_map(date_iso)
    for record in records:
        latest[str(record.get("code") or "")] = record
    STOCK_SENTIMENT_FILE.write_text(
        json.dumps(list(latest.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    history: dict[tuple[str, str], dict[str, object]] = {}
    if STOCK_SENTIMENT_HISTORY_FILE.exists():
        with STOCK_SENTIMENT_HISTORY_FILE.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                key = (str(row.get("date") or "")[:10], str(row.get("code") or ""))
                if key[0] and key[1]:
                    history[key] = row
    for record in records:
        key = (str(record.get("date") or "")[:10], str(record.get("code") or ""))
        if key[0] and key[1]:
            history[key] = record
    with STOCK_SENTIMENT_HISTORY_FILE.open("w", encoding="utf-8") as f:
        for key in sorted(history):
            f.write(json.dumps(history[key], ensure_ascii=False) + "\n")
    agent_signals.upsert_signals(
        OUT_DIR / "agent_signals.jsonl",
        agent_signals.signals_from_intelligence_records(records),
    )


def _merge_sentiment_into_signal_snapshots(records: list[dict[str, object]], date_iso: str) -> None:
    snap = OUT_DIR / "signal_snapshots.jsonl"
    if not records or not snap.exists():
        return
    by_code = {str(r.get("code") or ""): r for r in records if r.get("code")}
    short_by_code = intelligence.short_shadow_rank_map(records)
    lines = snap.read_text(encoding="utf-8").splitlines()
    merged: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            merged.append(line)
            continue
        if str(row.get("date") or "")[:10] == date_iso:
            row["intelligence_long_star"] = False
            row["intelligence_long_rank"] = 9999
            row["intelligence_long_score"] = None
            row["intelligence_long_threshold"] = 0.2
            row["intelligence_long_surface"] = "shadow_ab"
            row["ai_intelligence_short_star"] = False
            row["ai_intelligence_short_rank"] = 9999
            row["ai_intelligence_short_score"] = None
            row["ai_intelligence_short_threshold"] = 0.2
            row["ai_intelligence_short_surface"] = "shadow_ab"
            record = by_code.get(str(row.get("code") or ""))
            if record is not None:
                row["stock_sentiment_score"] = record.get("score")
                row["stock_sentiment_label"] = record.get("label")
                row["stock_sentiment_summary"] = record.get("summary")
                row["stock_sentiment_source"] = record.get("source")
                row["stock_sentiment_decision_used"] = bool(record.get("decision_used", False))
                row["stock_sentiment_target_set"] = record.get("target_set")
                row["stock_sentiment_data_quality"] = record.get("data_quality")
                row["stock_sentiment_evidence_state"] = record.get("evidence_state")
                row["stock_sentiment_authority"] = record.get("authority", 0)
                row["stock_sentiment_relevance_counts"] = record.get("relevance_counts") or {}
                row["score_source"] = record.get("score_source")
                row["agent_score"] = record.get("agent_score")
                row["agent_short_score"] = record.get("agent_short_score")
                row["agent_trend_score"] = record.get("agent_trend_score")
                row["veto_flags"] = record.get("veto_flags") or []
                row["intelligence_factor_score_source"] = record.get("score_source")
                row["intelligence_factor_keyword_score"] = record.get("keyword_score")
                row["intelligence_factor_agent_score"] = record.get("agent_score")
                row["intelligence_factor_short_score"] = record.get("agent_short_score")
                row["intelligence_factor_trend_score"] = record.get("agent_trend_score")
                row["intelligence_factor_trend_label"] = record.get("trend_label")
                row["intelligence_veto_flags"] = record.get("veto_flags") or []
                veto_state = intelligence_policy.hard_veto_state(record, asof=f"{date_iso}T09:30:00+08:00")
                row["ai_hard_veto"] = bool(veto_state.get("hard_veto"))
                row["ai_hard_veto_event_types"] = veto_state.get("event_types") or []
                row["ai_hard_veto_reason"] = veto_state.get("reason") or ""
                usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
                exit_composite_input = bool(usage.get("exit_composite_input", False))
                if record.get("score_source") == "agent_review":
                    exit_composite_input = False
                row["stock_sentiment_exit_composite_input"] = exit_composite_input
                row["stock_sentiment_buy_ranking_used"] = bool(usage.get("buy_ranking", False))
                short_flags = short_by_code.get(str(row.get("code") or ""))
                if short_flags:
                    row.update(short_flags)
        merged.append(json.dumps(row, ensure_ascii=False, default=str))
    snap.write_text("\n".join(merged) + ("\n" if merged else ""), encoding="utf-8")


def _resolve_date(date_arg: str) -> str:
    if date_arg in ("today", "latest"):
        return _date.today().isoformat()
    return date_arg


def _normal_date(value: object) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _trade_days(client: XiaocaoClient, date_iso: str, lookback_days: int = 220) -> list[str]:
    start = (_date.fromisoformat(date_iso) - timedelta(days=lookback_days)).isoformat()
    rows = client.get_trade_cal(start, date_iso, "SSE", 1)
    return sorted({
        _normal_date(r.get("calDate") or r.get("tradeDate") or r.get("date"))
        for r in rows
        if isinstance(r, dict) and (r.get("calDate") or r.get("tradeDate") or r.get("date"))
    })


def _seconds_until_recommendation_start(date_iso: str, now: datetime) -> float:
    now = now.astimezone(A_SHARE_TZ) if now.tzinfo else now.replace(tzinfo=A_SHARE_TZ)
    if date_iso != now.date().isoformat():
        return 0.0
    current = now.time()
    if not (WAIT_START <= current < WAIT_TARGET):
        return 0.0
    target = datetime.combine(now.date(), WAIT_TARGET, tzinfo=A_SHARE_TZ)
    return max(0.0, (target - now).total_seconds())


def _wait_for_recommendation_start(date_iso: str) -> None:
    wait_seconds = _seconds_until_recommendation_start(date_iso, datetime.now(A_SHARE_TZ))
    if wait_seconds <= 0:
        return
    print(
        f"[wait] 当前为 {date_iso} 早盘集合竞价窗口，等待 {wait_seconds:.1f}s 到 09:25:01 后开跑",
        file=sys.stderr,
    )
    _time.sleep(wait_seconds)


def _today_iso() -> str:
    return datetime.now(A_SHARE_TZ).date().isoformat()


def _is_today_live_run(date_iso: str) -> bool:
    return date_iso == _today_iso()


def _run_strategy_when_ready(
    date_iso: str,
    source: ApiDataSource,
    *,
    timeout_sec: float,
    poll_sec: float,
    confirm_sec: float = DEFAULT_READY_CONFIRM_SEC,
    stable_samples: int = DEFAULT_READY_STABLE_SAMPLES,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Run live strategy, retrying empty early-morning results.

    Around 09:25 the exchange-side auction price may be final, while Xiaocao's
    pool/index APIs can still lag by tens of seconds. An empty strategy result
    during today's live run is therefore ambiguous: it can mean either "no
    signals" or "backend not populated yet". Poll briefly before declaring NONE.
    """
    if not _is_today_live_run(date_iso) or timeout_sec <= 0:
        rows = run_strategy(date_iso, source, profile="validated_v5", adaptive_modes=False)
        actives = [r for r in rows if r.get("adaptive_active") in (True, None)]
        return rows, actives

    deadline = _time.monotonic() + max(0.0, timeout_sec)
    attempt = 0
    best_rows: list[dict[str, object]] = []
    best_actives: list[dict[str, object]] = []
    first_nonempty_at: float | None = None
    last_fingerprint: tuple[tuple[object, object, object], ...] | None = None
    stable_seen = 0
    while True:
        attempt += 1
        rows = run_strategy(date_iso, source, profile="validated_v5", adaptive_modes=False)
        actives = [r for r in rows if r.get("adaptive_active") in (True, None)]

        if len(actives) > len(best_actives) or (len(actives) == len(best_actives) and len(rows) > len(best_rows)):
            best_rows = rows
            best_actives = actives

        if actives:
            now = _time.monotonic()
            if first_nonempty_at is None:
                first_nonempty_at = now
                deadline = max(deadline, now + max(0.0, confirm_sec))
            fingerprint = tuple(sorted(
                (r.get("code"), r.get("mode"), r.get("adaptive_active"))
                for r in rows
            ))
            stable_seen = stable_seen + 1 if fingerprint == last_fingerprint else 1
            last_fingerprint = fingerprint
            if stable_seen >= max(1, stable_samples):
                return rows, actives
            remaining = deadline - now
            if remaining <= 0:
                return best_rows or rows, best_actives or actives
            sleep_sec = min(max(0.2, poll_sec), remaining)
            print(
                f"[settle] {date_iso} 第 {attempt} 次已有 {len(rows)} 个信号/"
                f"{len(actives)} 个 active，继续秒级确认稳定性；{sleep_sec:.1f}s 后重试",
                file=sys.stderr,
            )
            _time.sleep(sleep_sec)
            continue

        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            return best_rows or rows, best_actives or actives
        sleep_sec = min(max(0.2, poll_sec), remaining)
        print(
            f"[not-ready] {date_iso} 第 {attempt} 次策略结果为空，疑似 API 尚未发布；"
            f"{sleep_sec:.1f}s 后重试，最多再等 {remaining:.0f}s",
            file=sys.stderr,
        )
        _time.sleep(sleep_sec)


def _extract_realtime_detail_row(payload: object, code: str) -> dict[str, object] | None:
    if isinstance(payload, dict):
        direct = payload.get(code)
        if isinstance(direct, dict):
            return direct
        if payload.get("code") == code:
            return payload
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and row.get("code") == code:
                return row
    return None


def _open_pct_from_entry(entry_price: float, pre_close: float | None, fallback: object) -> float:
    if pre_close and pre_close > 0:
        return (entry_price / pre_close - 1.0) * 100.0
    return _num(fallback)


def _market_detail_for_date(client: XiaocaoClient, code: str, date_iso: str) -> dict[str, object] | None:
    if date_iso != _today_iso():
        return None
    try:
        detail = _extract_realtime_detail_row(client.second_line_detail_info(code), code)
    except Exception:
        return None
    if not detail:
        return None
    td = _normal_date(detail.get("tradeDate") or "")
    return detail if td == date_iso else None


def _normalize_market_observed_at(value: object, date_iso: str) -> object:
    """Bind the API's HHMMSS auction clock to the dated China session."""
    text = str(value or "").strip()
    formats = ("%H%M%S", "%H:%M:%S:%f", "%H:%M:%S")
    for clock_format in formats:
        try:
            clock = datetime.strptime(text, clock_format).time()
            parsed = datetime.combine(_date.fromisoformat(date_iso), clock)
        except ValueError:
            continue
        return parsed.replace(tzinfo=A_SHARE_TZ).isoformat()
    return value


def _entry_price_with_detail(
    client: XiaocaoClient,
    code: str,
    date_iso: str,
) -> tuple[float | None, str, float | None, dict[str, object] | None]:
    """Fetch the best available early-session entry price for `code`.

    For today's live run, 9:25 call-auction completion should already expose
    the final opening price via the realtime detail `open` field. Indicative
    auction rows before 09:25 are not a stable entry price and are ignored.
    """
    detail = _market_detail_for_date(client, code, date_iso)
    if detail:
        try:
            price = float(detail.get("open") or 0) or None
        except (TypeError, ValueError):
            price = None
        if price:
            pre_close = _to_float(detail.get("preClose"))
            return price, "realtime_open", pre_close, detail

    try:
        rows = client.date_kline(code, count=10, freq="D", adj="qfq")
    except Exception:
        rows = []
    # NOTE: a per-candidate empty/failed date_kline degrades gracefully here (we
    # fall back to other price sources). The SYSTEMIC hazard — the date_kline feed
    # going stale for everyone (it froze at 2026-05-29 for ~3 weeks, unnoticed) —
    # is NOT silently swallowed: data_health.stale_market_cache flags it every eod.
    if isinstance(rows, list):
        td_compact = date_iso.replace("-", "")
        for r in rows:
            if not isinstance(r, dict):
                continue
            td = str(r.get("tradeDate", ""))[:10]
            if td == date_iso or td == td_compact:
                try:
                    price = float(r.get("open") or 0) or None
                except (TypeError, ValueError):
                    price = None
                if price:
                    pre_close = _to_float(r.get("preClose"))
                    return price, "open", pre_close, detail

    try:
        auction_rows = client.stock_call_auction(code, date_iso)
    except Exception:
        auction_rows = []
    if isinstance(auction_rows, list):
        valid_rows = [
            r for r in auction_rows
            if isinstance(r, dict) and str(r.get("tradeTimestamp") or "") >= "092500"
        ]
        for r in reversed(valid_rows):
            try:
                price = float(r.get("trade") or r.get("buyPrice1") or r.get("sellPrice1") or 0) or None
            except (TypeError, ValueError):
                price = None
            if price:
                pre_close = _to_float(r.get("preClose"))
                return price, "auction", pre_close, detail
    return None, "", None, detail


def _entry_price(client: XiaocaoClient, code: str, date_iso: str) -> tuple[float | None, str, float | None]:
    """Compatibility wrapper used by existing callers and tests."""
    price, source, pre_close, detail = _entry_price_with_detail(client, code, date_iso)
    _ENTRY_DETAIL_CACHE[(date_iso, str(code))] = detail
    return price, source, pre_close


def _basket_params(
    mode: str,
    confidence: float = 50.0,
    override_premium_pct: float | None = None,
) -> tuple[float, float, float]:
    policy = BASKET_POLICY.get(mode, DEFAULT_BASKET_POLICY)
    cap_pct = float(policy["cap_pct"])
    exec_cap_pct = float(policy.get("exec_cap_pct", cap_pct))
    if override_premium_pct is not None:
        return max(0.0, override_premium_pct), cap_pct, exec_cap_pct

    # Confidence nudges execution tolerance, but never changes a mode's nature.
    confidence_adj = max(-0.4, min(0.4, (confidence - 50.0) / 50.0 * 0.4))
    premium = float(policy["premium"]) + confidence_adj
    premium = max(float(policy["min"]), min(float(policy["max"]), premium))
    return round(premium, 2), cap_pct, exec_cap_pct


def _price_limit_pct(code: object, name: object = "") -> float:
    code_s = str(code or "")
    name_s = str(name or "").upper()
    if name_s.startswith(("ST", "*ST")):
        return 5.0
    symbol = code_s.split(".", 1)[0]
    market = code_s.rsplit(".", 1)[-1] if "." in code_s else ""
    if market == "BJSE" or symbol.startswith(("8", "9")):
        return 30.0
    if symbol.startswith(("300", "301", "688", "689")):
        return 20.0
    return 10.0


def _scale_exec_cap_pct(base_exec_cap_pct: float, price_limit_pct: float) -> float:
    if base_exec_cap_pct <= 0:
        return 0.0
    if price_limit_pct <= 5:
        return min(base_exec_cap_pct, 3.0)
    if price_limit_pct <= 10:
        return base_exec_cap_pct
    if price_limit_pct <= 20:
        return base_exec_cap_pct + 2.0
    if price_limit_pct <= 30:
        return base_exec_cap_pct + 4.0
    return base_exec_cap_pct + 6.0


def _basket_price(
    entry_price: float,
    pre_close: float | None,
    premium_pct: float,
    cap_pct: float,
    exec_cap_pct: float | None = None,
) -> tuple[float, str]:
    raw = entry_price * (1 + premium_pct / 100)
    if pre_close and pre_close > 0:
        cap = pre_close * (1 + cap_pct / 100)
        if exec_cap_pct is not None:
            cap = min(cap, pre_close * (1 + exec_cap_pct / 100))
        executable_cap = max(entry_price, cap)
        if raw > executable_cap:
            if executable_cap <= entry_price:
                return entry_price, f"entry-only; cap<=preClose+{cap_pct:.1f}%"
            if exec_cap_pct is not None and exec_cap_pct < cap_pct:
                return executable_cap, f"exec cap preClose+{exec_cap_pct:.1f}%"
            return executable_cap, f"cap preClose+{cap_pct:.1f}%"
    return raw, f"entry+{premium_pct:.1f}%"


def _to_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _num(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _profile_stop(fill_price: float, dd_pct: float) -> float:
    return round(fill_price * (1 - dd_pct / 100.0), 4)


def _block_set(row: dict[str, object]) -> set[str]:
    out: set[str] = set()
    for key in ("excIndustryCode", "blockCodeList", "blockCategoryCodeList"):
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            out.update(part.strip() for part in value.split(",") if part.strip())
        elif isinstance(value, list):
            out.update(str(part) for part in value if part)
    return out


def _primary_score(row: dict[str, object]) -> tuple[float, str]:
    mode = str(row.get("mode") or "")
    xcjw = _num(row.get("xcjw"))
    cjs = _num(row.get("cjs"))
    jsjl = _num(row.get("jsjl"))
    jssb = _num(row.get("jssb"))
    if mode in RAW_QIBAO_BENCHMARK_MODES or row.get("qibaoBenchmarkKind"):
        return _num(row.get("qibaoRankScore")), "qibaoRankScore"
    if "起爆" in mode:
        return jssb, "jssb"
    if mode.startswith("接力"):
        return xcjw + max(jsjl, 0.0) * 0.5, "xcjw+0.5*jsjl"
    if mode in {"N字低吸", "孕线低吸"}:
        return xcjw + cjs * 0.6, "xcjw+0.6*cjs"
    return xcjw + cjs * 0.8, "xcjw+0.8*cjs"


def _focus_rank_score(rank: object) -> float:
    try:
        r = int(rank)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if r < 0:
        return 0.0
    if r == 0:
        return 100.0
    if r == 1:
        return 85.0
    if r == 2:
        return 70.0
    return 55.0


def _macro_focus_score(row: dict[str, object]) -> tuple[float, str]:
    block_score = _focus_rank_score(row.get("direction_rank"))
    category_score = _focus_rank_score(row.get("category_rank"))
    score = max(block_score, category_score)
    if score <= 0:
        return 0.0, "no focus"
    reasons: list[str] = []
    if block_score:
        reasons.append(f"block r{int(_num(row.get('direction_rank')))}")
    if category_score:
        reasons.append(f"category r{int(_num(row.get('category_rank')))}")
    return score, "+".join(reasons)


def _alpha_score_fit(primary_score: float) -> float:
    return min(140.0, primary_score / 350.0 * 100.0)


def _open_fit(mode: str, open_pct: float) -> float:
    """Score opening price shape on 0..100 for recommendation ranking."""
    if mode.startswith("接力") or "起爆" in mode:
        # Continuation modes want strength, but not a high-open chase.
        return max(0.0, 100.0 - abs(open_pct - 2.0) * 18.0)
    # Rebound / low-absorb modes prefer a controlled low open around -3%.
    if open_pct <= -8.5:
        return 20.0
    return max(0.0, 100.0 - abs(open_pct + 3.0) * 15.0)


def _open_risk_penalty(mode: str, open_pct: float) -> float:
    """Light execution-risk penalty; alpha still comes from score/confidence."""
    if mode.startswith("接力") or "起爆" in mode:
        high_penalty = max(0.0, open_pct - 3.0) * 8.0
        weak_penalty = max(0.0, -2.0 - open_pct) * 5.0
        return min(35.0, high_penalty + weak_penalty)
    deep_low_penalty = max(0.0, -7.0 - open_pct) * 8.0
    chase_penalty = max(0.0, open_pct - 1.5) * 6.0
    return min(35.0, deep_low_penalty + chase_penalty)


def _annotate_recommendation_score(
    candidate: dict[str, object],
    mode_confidence: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    mode = str(candidate.get("mode") or "")
    primary, label = _primary_score(candidate)
    score_fit = _alpha_score_fit(primary)
    open_fit = _open_fit(mode, _num(candidate.get("open_pct_change")))
    open_risk_penalty = _open_risk_penalty(mode, _num(candidate.get("open_pct_change")))
    macro_score, macro_reason = _macro_focus_score(candidate)
    confidence_info = (mode_confidence or {}).get(mode, {})
    confidence = _num(confidence_info.get("confidence")) if confidence_info else 50.0
    stock_rank_score = score_fit * 0.60 + macro_score * 0.18 - open_risk_penalty
    rank_score = stock_rank_score + confidence * 0.25
    out = dict(candidate)
    out["primary_score"] = round(primary, 2)
    out["primary_score_label"] = label
    out["open_fit"] = round(open_fit, 2)
    out["open_risk_penalty"] = round(open_risk_penalty, 2)
    out["macro_focus_score"] = round(macro_score, 2)
    out["macro_focus_reason"] = macro_reason
    out["mode_confidence"] = round(confidence, 2)
    out["mode_recent_avg"] = confidence_info.get("mode_recent_avg", 0.0)
    out["mode_recent_n"] = confidence_info.get("mode_recent_n", 0)
    out["mode_confidence_source"] = confidence_info.get("mode_confidence_source", "neutral")
    out["mode_confidence_reason"] = confidence_info.get("mode_confidence_reason", "neutral")
    out["stock_rank_score"] = round(stock_rank_score, 2)
    out["rank_score"] = round(rank_score, 2)
    return out


def _rank_candidates(
    candidates: list[dict[str, object]],
    mode_confidence: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    annotated = [_annotate_recommendation_score(c, mode_confidence) for c in candidates]
    return sorted(
        annotated,
        key=lambda c: (
            -_num(c.get("rank_score")),
            -_num(c.get("primary_score")),
            _num(c.get("open_risk_penalty")),
            str(c.get("code") or ""),
        ),
    )


def _split_ranked_candidates(
    ranked: list[dict[str, object]],
    max_candidates: int,
    max_per_mode: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if max_candidates <= 0:
        return ranked, []
    selected: list[dict[str, object]] = []
    overflow: list[dict[str, object]] = []
    by_mode: dict[str, int] = {}
    for c in ranked:
        mode = str(c.get("mode") or "")
        if len(selected) < max_candidates and by_mode.get(mode, 0) < max_per_mode:
            selected.append(c)
            by_mode[mode] = by_mode.get(mode, 0) + 1
        else:
            overflow.append(c)
    return selected, overflow


def _select_candidates(
    candidates: list[dict[str, object]],
    max_candidates: int,
    max_per_mode: int,
    mode_confidence: dict[str, dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ranked = _rank_candidates(candidates, mode_confidence)
    return _split_ranked_candidates(ranked, max_candidates, max_per_mode)


def _candidate_key(candidate: dict[str, object]) -> tuple[str, str]:
    return str(candidate.get("code") or ""), str(candidate.get("mode") or "")


def _diversifies_selected(candidate: dict[str, object], selected: list[dict[str, object]]) -> bool:
    candidate_blocks = _block_set(candidate)
    if not candidate_blocks:
        return True
    return not any(candidate_blocks & _block_set(row) for row in selected)


def _select_standby_candidates(
    ranked: list[dict[str, object]],
    selected: list[dict[str, object]],
    max_standby: int = DEFAULT_MAX_STANDBY,
    max_rank_gap: float = STANDBY_MAX_RANK_GAP,
    max_per_mode: int = DEFAULT_MAX_PER_MODE,
) -> list[dict[str, object]]:
    if not selected or max_standby <= 0:
        return []
    cutoff = _num(selected[-1].get("rank_score"))
    selected_keys = {_candidate_key(c) for c in selected}
    by_mode: dict[str, int] = {}
    for c in selected:
        mode = str(c.get("mode") or "")
        by_mode[mode] = by_mode.get(mode, 0) + 1

    standby: list[dict[str, object]] = []
    for c in ranked:
        if _candidate_key(c) in selected_keys:
            continue
        mode = str(c.get("mode") or "")
        rank_gap = cutoff - _num(c.get("rank_score"))
        if rank_gap > max_rank_gap:
            continue
        if by_mode.get(mode, 0) >= max_per_mode:
            continue
        if not _diversifies_selected(c, selected):
            continue
        row = dict(c)
        row["standby_reason"] = f"rank_gap<={max_rank_gap:.1f}; diversified"
        standby.append(row)
        by_mode[mode] = by_mode.get(mode, 0) + 1
        if len(standby) >= max_standby:
            break
    return standby


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--basket-premium-pct", type=float,
                        help="覆盖 mode-specific basket premium；不传则按 mode + confidence 动态计算")
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES,
                        help="二级筛选后输出的最大候选数；0 表示输出全部")
    parser.add_argument("--max-per-mode", type=int, default=DEFAULT_MAX_PER_MODE,
                        help="二级筛选时单个 mode 最多保留几只，默认 2")
    parser.add_argument("--max-standby", type=int, default=DEFAULT_MAX_STANDBY,
                        help="小仓候补最多输出几只；仅保留与第 N 名分差很小且不拥挤的候选")
    parser.add_argument("--ready-timeout-sec", type=float, default=DEFAULT_READY_TIMEOUT_SEC,
                        help="今天实时运行时，空信号疑似 API 未 ready 的最长等待秒数；0 表示不等待")
    parser.add_argument("--ready-poll-sec", type=float, default=DEFAULT_READY_POLL_SEC,
                        help="今天实时运行时，空信号重试间隔秒数")
    parser.add_argument("--ready-confirm-sec", type=float, default=DEFAULT_READY_CONFIRM_SEC,
                        help="今天实时运行时，首次非空后继续确认稳定性的最长秒数")
    parser.add_argument("--no-secondary-filter", action="store_true",
                        help="关闭二级筛选，输出全部 enrich 后 active 候选")
    parser.add_argument("--no-stdout", action="store_true",
                        help="只写文件，不打印 stdout")
    parser.add_argument("--no-kronos", action="store_true",
                        help="关闭 Kronos K→P 防御性再排序叠加层")
    parser.add_argument("--kronos-top-n", type=int, default=3,
                        help="K→P 流水线标记的 ★ 优先候选数，默认 3")
    args = parser.parse_args()

    _ENTRY_DETAIL_CACHE.clear()

    date_iso = _resolve_date(args.date)
    _wait_for_recommendation_start(date_iso)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = _client()
    source = ApiDataSource(client, hpqb_state=0, lpdx_state=0)
    cache = client.cache if isinstance(client.cache, SQLiteCache) else None

    # Run both profiles. Their signal generation is IDENTICAL (same EOD logic);
    # they differ only in scoring (exit rule), so signals should be identical.
    # We run once and label each signal as "in v5" / "in v6" — they're all in
    # both. The differentiation is in the STOP price computed below.
    rows, actives = _run_strategy_when_ready(
        date_iso,
        source,
        timeout_sec=max(0.0, args.ready_timeout_sec),
        poll_sec=max(1.0, args.ready_poll_sec),
        confirm_sec=max(0.0, args.ready_confirm_sec),
    )

    if not actives:
        msg = f"# {date_iso} 候选股: NONE"
        print(msg)
        (OUT_DIR / f"recommend_{date_iso}.md").write_text(msg, encoding="utf-8")
        return

    # Enrich each with open price + theoretical stops
    candidates = []
    for r in actives:
        code = r.get("code")
        if not code:
            continue
        # Keep the historical three-value seam here.  A few downstream callers
        # (and, more importantly, offline recommendation fixtures) replace
        # ``_entry_price`` directly.  The realtime detail is an optional
        # enrichment for the market guard and must not make those fixtures lose
        # their candidate solely because the detail endpoint is unavailable.
        opn, entry_source, pre_close = _entry_price(client, code, date_iso)
        cached_detail = _ENTRY_DETAIL_CACHE.pop((date_iso, str(code)), _MISSING_ENTRY_DETAIL)
        # `_entry_price` already performs the one realtime-detail read and
        # stores its result.  A missing cache means a compatibility caller
        # replaced that function; do not issue a second API request merely to
        # enrich a row (the market guard will fail closed if authoritative
        # detail was not supplied).
        market_detail = None if cached_detail is _MISSING_ENTRY_DETAIL else cached_detail
        if not opn:
            continue
        open_pct_change = _open_pct_from_entry(opn, pre_close, r.get("openPctChange"))
        market_status = str((market_detail or {}).get("tradeStatus") or "")
        candidates.append({
            "code": code,
            "name": r.get("name") or "",
            "mode": r.get("mode") or "",
            "xcjw": _num(r.get("xcjw")),
            "cjs": _num(r.get("cjs")),
            "jsjl": _num(r.get("jsjl")),
            "jssb": _num(r.get("jssb")),
            "rawQibaoRank": r.get("rawQibaoRank"),
            "qibaoRankScore": r.get("qibaoRankScore"),
            "qibaoBenchmarkKind": r.get("qibaoBenchmarkKind"),
            "qibaoBenchmarkLayer": r.get("qibaoBenchmarkLayer"),
            "industryElectronic": r.get("industryElectronic"),
            "board20": r.get("board20"),
            "open": opn,
            "pre_close": pre_close,
            "entry_source": entry_source,
            "market_guard_required": bool(_is_today_live_run(date_iso)),
            "market_guard_status": market_status or None,
            "trade_status": market_status or None,
            "market_price": (market_detail or {}).get("trade"),
            "down_price": (market_detail or {}).get("downPrice"),
            "up_price": (market_detail or {}).get("upPrice"),
            "market_observed_at": _normalize_market_observed_at(
                (market_detail or {}).get("tradeTimestamp"), date_iso
            ),
            "v5_stop_initial": _profile_stop(opn, 2.0),
            "v6_stop_initial": _profile_stop(opn, 0.5),
            "is_main_line": bool(r.get("is_main_line")),
            "is_big_cap": bool(r.get("is_big_cap")),
            "direction": bool(r.get("direction")),
            "direction_rank": r.get("directionRank", -1),
            "category_rank": r.get("categoryRank", -1),
            "regime": r.get("regime") or "",
            "reason": r.get("reason") or "",
            "open_pct_change": open_pct_change,
            "excIndustryCode": r.get("excIndustryCode") or "",
            "blockCodeList": r.get("blockCodeList") or "",
            "blockCategoryCodeList": r.get("blockCategoryCodeList") or "",
        })

    try:
        trade_days = _trade_days(client, date_iso)
    except Exception:
        trade_days = []
    executable_evidence = load_live_executable_evidence(TRAINING_ROWS_FILE)
    mode_decisions = decide_mode_switches(
        {str(c.get("mode") or "") for c in candidates if c.get("mode")},
        date_iso,
        executable_evidence,
        trade_days,
    )
    mode_confidence = confidence_map_from_decisions(mode_decisions)
    candidates = [_annotate_recommendation_score(c, mode_confidence) for c in candidates]
    candidates = annotate_mode_candidates(candidates, mode_decisions)
    for c in candidates:
        mode = str(c.get("mode") or "")
        confidence = _num(c.get("mode_confidence"))
        premium_pct, cap_pct, exec_cap_pct = _basket_params(mode, confidence, args.basket_premium_pct)
        price_limit_pct = _price_limit_pct(c.get("code"), c.get("name"))
        scaled_exec_cap_pct = _scale_exec_cap_pct(exec_cap_pct, price_limit_pct)
        basket_price, basket_rule = _basket_price(
            _num(c.get("open")),
            _to_float(c.get("pre_close")),
            premium_pct,
            cap_pct,
            scaled_exec_cap_pct,
        )
        c["basket_price"] = round(basket_price, 4)
        c["basket_rule"] = basket_rule
        c["basket_premium_pct"] = premium_pct
        c["basket_cap_pct"] = cap_pct
        c["basket_exec_cap_pct"] = scaled_exec_cap_pct
        c["price_limit_pct"] = price_limit_pct
        c["basket_slippage_pct"] = round(
            (basket_price / _num(c.get("open")) - 1.0) * 100.0
            if _num(c.get("open")) > 0 else 0.0,
            2,
        )
        c["v5_stop_at_basket"] = _profile_stop(basket_price, 2.0)
        c["v6_stop_at_basket"] = _profile_stop(basket_price, 0.5)

    # --- Kronos K→P secondary re-rank (defensive overlay; fail-safe) ---
    # Honest framing: drops the Kronos-worst half, ranks survivors by prior-day
    # intraday model; validated value is drawdown cushioning + small win-rate
    # lift (NOT a proven return engine). Never blocks the recommendation.
    kp_stars: list[dict] = []
    vb_stars: list[dict] = []
    mode_stars: list[dict] = []
    mode_exec_stars: list[dict] = []
    import importlib.util as _ilu

    def _load_screen_module(modname):
        module_path = ROOT / "kronos_screen" / "scripts" / f"{modname}.py"
        spec = _ilu.spec_from_file_location(modname, module_path)
        module = _ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    if not args.no_kronos:
        try:
            _load_screen_module("secondary_screen").score(
                candidates,
                client,
                date_iso,
                top_n=max(1, args.kronos_top_n),
            )
            kp_stars = [c for c in candidates if c.get("kp_star")]
        except Exception as e:  # missing model / torch / API — degrade gracefully
            print(f"[Kronos K→P skipped: {type(e).__name__}: {e}]", file=sys.stderr)

    # Signal capture and the shared ★E mode gate are deterministic morning
    # outputs, not part of the optional K→P overlay.  Missing K/P scores fall
    # back to neutral percentiles inside select_executable_candidates().
    try:
        _load_screen_module("capture_signals").capture(
            candidates,
            client,
            date_iso,
            is_live=_is_today_live_run(date_iso),
            top_n=max(1, args.kronos_top_n),
        )
        vb_stars = [c for c in candidates if c.get("vb_star")]
        mode_stars = [c for c in candidates if c.get("mode_star")]
        mode_exec_stars = [c for c in candidates if c.get("mode_exec_star")]
    except Exception as e:
        raise RuntimeError(
            f"required signal capture failed: {type(e).__name__}: {e}"
        ) from e

    ranked = _rank_candidates(candidates, mode_confidence)
    selected, overflow = _split_ranked_candidates(
        ranked,
        0 if args.no_secondary_filter else args.max_candidates,
        max(1, args.max_per_mode),
    )
    standby = [] if args.no_secondary_filter else _select_standby_candidates(
        ranked,
        selected,
        max(0, args.max_standby),
        STANDBY_MAX_RANK_GAP,
        max(1, args.max_per_mode),
    )
    standby_keys = {_candidate_key(c) for c in standby}
    overflow = [c for c in overflow if _candidate_key(c) not in standby_keys]
    open_position_candidates = _load_open_book_b_position_candidates()
    intelligence_universe = _merge_intelligence_universe(candidates, open_position_candidates)
    open_position_codes = {str(c.get("code") or "") for c in open_position_candidates}
    sentiment_started = _time.monotonic()
    sentiment_records = _build_top_stock_sentiment(
        intelligence_universe,
        date_iso,
        max_workers=4,
        max_seconds=INTELLIGENCE_EVIDENCE_TIMEOUT_SEC,
    )
    selected_codes = {str(c.get("code") or "") for c in selected}
    standby_codes = {str(c.get("code") or "") for c in standby}
    vb_codes = {str(c.get("code") or "") for c in vb_stars}
    mode_exec_codes = {str(c.get("code") or "") for c in mode_exec_stars}
    for record in sentiment_records:
        code = str(record.get("code") or "")
        if code in mode_exec_codes:
            record["target_set"] = "mode_exec_star"
        elif code in vb_codes:
            record["target_set"] = "vb_star"
        elif code in selected_codes:
            record["target_set"] = "selected"
        elif code in standby_codes:
            record["target_set"] = "standby"
        elif code in open_position_codes:
            record["target_set"] = "open_position"
        else:
            record["target_set"] = "candidate"
    _write_stock_sentiment_records(sentiment_records, date_iso)
    _merge_sentiment_into_signal_snapshots(sentiment_records, date_iso)
    intelligence_evidence.write_freeze_artifacts(
        live_dir=OUT_DIR,
        records=sentiment_records,
        candidates=intelligence_universe,
        market_date=date_iso,
        phase="morning_freeze",
        universe="candidates+open_positions",
        elapsed_ms=int((_time.monotonic() - sentiment_started) * 1000),
    )
    top_surface = mode_exec_stars or vb_stars or selected
    top_sentiment_codes = [str(c.get("code") or "") for c in top_surface]
    sentiment_by_code = {str(r.get("code") or ""): r for r in sentiment_records}
    top_sentiment = [sentiment_by_code[code] for code in top_sentiment_codes if code in sentiment_by_code]

    # Render markdown
    L: list[str] = []
    L.append(f"# {date_iso} 候选股推荐 — v5 + v6")
    L.append("")
    L.append(f"- 总信号数: {len(rows)}")
    L.append(f"- Active 信号: {len(actives)}")
    L.append(f"- 已 enrich (有开盘价): {len(candidates)}")
    L.append(
        f"- 二级筛选入选: {len(selected)}"
        + ("" if not standby else f" / 小仓候补: {len(standby)}")
        + ("" if not overflow else f" / 观察: {len(overflow)}")
    )
    L.append(f"- 模式资格证据: executable all-hit {len(executable_evidence)} 笔")
    L.append("")
    L.append("## 模式资格（Book B 执行权限）")
    L.append("")
    L.append("| mode | state | window | raw | pool alpha/LCB80 | market alpha/LCB80 | fast health (pool/market) | n(days/signals) | max picks |")
    L.append("|---|---|---:|---:|---:|---:|---|---:|---:|")
    for mode, decision in sorted(mode_decisions.items()):
        selected_stats = decision.windows.get(decision.selected_window or -1)
        fast = fast_health_fields(decision)
        fast_label = (
            f"{fast['mode_fast_health']} ("
            f"{_num(fast.get('mode_fast_alpha_pool')):+.2f}/"
            f"{_num(fast.get('mode_fast_alpha_market')):+.2f}pp)"
        )
        if selected_stats:
            market_mean = selected_stats.alpha_market_mean
            market_lcb = selected_stats.alpha_market_lcb80
            market_label = (
                f"{market_mean:+.2f}/{market_lcb:+.2f}pp"
                if market_mean is not None and market_lcb is not None else "-"
            )
            L.append(
                f"| {mode} | {decision.state} | {decision.selected_window or '-'} | "
                f"{selected_stats.raw_return_mean:+.2f}% | "
                f"{selected_stats.alpha_pool_mean:+.2f}/{selected_stats.alpha_pool_lcb80:+.2f}pp | "
                f"{market_label} | {fast_label} | {selected_stats.signal_days}/{selected_stats.signals} | "
                f"{decision.max_picks} |"
            )
        else:
            L.append(f"| {mode} | {decision.state} | - | - | - | - | {fast_label} | 0/0 | {decision.max_picks} |")
    L.append("- 模式证据保留 1/2/3 信号对应 25%/45%/50% 验证权重；正式 `ACTIVE` 必须同时稳健跑赢候选池和四指数。")
    L.append("- 近期双基准均值和多数日转正可直接升为 `ACTIVE`；每模式只取第一名，存在 ACTIVE 时新批次目标50%，单票可达50%。")
    L.append("- 近期双基准任一均值转负会冷却为 `PROVISIONAL`；`COLD/UNKNOWN` 只保留shadow。")
    L.append("- `fast health` 是无交易权限的早期传感器；`EARLY_WARNING/DETERIORATING` 不会自行改变模式资格。")
    L.append("")
    L.append("## Profiles 解读")
    L.append("")
    L.append("- **v5 (5d max_dd 2%)** = 持仓 5 日，从 post-entry peak 回撤 2% 即 trailing stop")
    L.append("- **v6 (3d max_dd 0.5%)** = 持仓 3 日，回撤 0.5% 即止 (aggressive，待 paper trading 验证)")
    L.append("- **入场价** = 9:25 集合竞价撮合出的开盘价（实时明细 open 字段优先）")
    L.append("- **买入看 entry / basket**：entry 是开盘参考价，basket 是建议挂单上限，不是默认成交价")
    L.append("- **篮子估算价** = mode-specific premium + 同一可执行双基准保守置信度，并按 mode 控制 preClose cap")
    L.append("- **保护线必须按实际成交价重算**：表中 `stop@basket` 是按最差 basket 成交的保护线参考")
    L.append("- **二级筛选** = 个股模式分 + 同一可执行双基准保守置信度 + 今日聚焦板块/大类加持，open_pct 只做极端执行风险惩罚")
    L.append("- **小仓候补** = 与第 N 名分差很小、且不与已入选票形成同 mode / 同板块拥挤的候选；只适合作为降仓观察")
    L.append("- **★KP = Kronos K→P 防御性叠加层**：K(Kronos日线表征)剔除当天最差半数，P(前一日分钟微结构)对幸存者排序；"
             "回测价值为**回撤缓冲+小幅胜率提升**(坏周 -2.4%→-0.7%, win37→54)，**非已证实的收益放大器**，仅作优先级参考。`KP↓`=被K判为后半。")
    L.append("")
    if kp_stars:
        L.append("## ★ Kronos K→P 优先")
        L.append("")
        L.append("| ★ | code | name | mode | Kscore | Pscore |")
        L.append("|---|---|---|---|---:|---:|")
        for c in kp_stars:
            L.append(f"| {c.get('kp_rank','')} | {c['code']} | {c.get('name','')} | {c.get('mode','')} | "
                     f"{_num(c.get('k_score')):+.3f} | {_num(c.get('p_score')):+.3f} |")
        L.append("")
    if vb_stars:
        _live = _is_today_live_run(date_iso)
        _tag = "今日实时建议" if _live else "回测占位(竞价为latest，非当日，仅验证管线)"
        L.append(f"## ★B 排名候选 + 仓位建议 = K→P + 9:25竞价不平衡 tiebreak — {_tag}")
        L.append("")
        L.append("| ★B | code | name | mode | primary | Pscore | quality_tag | 竞价涨幅 | 残余买卖压差 |")
        L.append("|---|---|---|---|---:|---:|---|---:|---:|")
        for c in vb_stars:
            q = ensure_quality_fields(c)
            L.append(f"| {c.get('vb_rank','')} | {c['code']} | {c.get('name','')} | {c.get('mode','')} | "
                     f"{_num(q.get('primary_score')):.1f} | {_num(c.get('p_score')):+.3f} | {q.get('quality_tag','normal')} | "
                     f"{_num(c.get('auc_pct')):+.2f}% | {_num(c.get('auc_residual_imb')):+.2f} |")
        L.append("- **★B 现在是保留基线**：继续前向记录 K/P+竞价表现，但默认 Book B 模拟成交改由下方 ★E 模式资格集合驱动。")
        L.append("- **quality_tag**：`normal`=primary≥150；`weak_primary`=primary<150；`p_tail_warning`=P 极弱尾部。当前仅提示/沉淀，不在推荐阶段硬过滤。")
        L.append("- **竞价 forced-contrast**：在 K 幸存者中，若非★候选竞价质量显著优于★内最弱竞价者，则换入以制造可验证 A/B 对照；否则 ★B 与 ★ 保持一致。")
        L.append("- **★ = A/B 基线**（纯 K→P，无竞价）。两套每日快照入 `output/live/signal_snapshots.jsonl`；`forward_eval.py --live-only` 累积真实收益后裁决竞价 tiebreak 是否带来增益（前瞻验证，历史不可回测）。")
        L.append("")
    if mode_exec_stars:
        L.append("## ★E Book B 模式切换可执行候选")
        L.append("")
        L.append("| ★E | code | name | mode | state | exec score | target | pool alpha/LCB80 | market alpha/LCB80 |")
        L.append("|---|---|---|---|---|---:|---:|---:|---:|")
        for c in sorted(mode_exec_stars, key=lambda row: int(_num(row.get("mode_exec_rank")) or 9999)):
            L.append(
                f"| {c.get('mode_exec_rank','')} | {c['code']} | {c.get('name','')} | "
                f"{c.get('mode','')} | {c.get('mode_state','')} | "
                f"{_num(c.get('mode_exec_score')):.3f} | "
                f"{_num(c.get('mode_exec_target_weight')):.1%} | "
                f"{_num(c.get('mode_alpha_pool')):+.2f}/"
                f"{_num(c.get('mode_alpha_pool_lcb80')):+.2f}pp | "
                f"{_num(c.get('mode_alpha_market')):+.2f}/"
                f"{_num(c.get('mode_alpha_market_lcb80')):+.2f}pp |"
            )
        L.append("- ★E 是 `模式硬门 -> rank/K/P软排序 -> 动态目标仓位` 的默认 Book B 模拟成交集合。")
        L.append("")
    else:
        L.append("## ★E Book B 模式切换可执行候选")
        L.append("")
        L.append("- NONE：当前没有通过可执行收益硬门的候选，Book B 新批次留现金。")
        L.append("")
    if mode_stars:
        L.append("## ★M K生存池内模式轮动影子候选 — forward-test only")
        L.append("")
        L.append("| ★M | code | name | mode | rank | mode_conf | primary | Pscore |")
        L.append("|---|---|---|---|---:|---:|---:|---:|")
        for c in sorted(mode_stars, key=lambda x: int(_num(x.get("mode_rank")) or 9999)):
            q = ensure_quality_fields(c)
            L.append(f"| {c.get('mode_rank','')} | {c['code']} | {c.get('name','')} | {c.get('mode','')} | "
                     f"{_num(c.get('rank_score')):.1f} | {_num(c.get('mode_confidence')):.1f} | "
                     f"{_num(q.get('primary_score')):.1f} | {_num(c.get('p_score')):+.3f} |")
        L.append("- **★M 不参与默认 Book B 买入**：它继续作为旧模式分排序影子分支；默认执行是共享状态机产生的 ★E。")
        L.append("")
    if top_sentiment:
        L.append("## Top AI 情报因子（证据化记录；agent 研判后进入做多影子 A/B）")
        L.append("")
        L.append("| 标的 | 集合 | 因子 | 分数 | 来源 | 质量 | 摘要 |")
        L.append("|---|---|---|---:|---|---|---|")
        for row in top_sentiment:
            L.append(
                f"| {row.get('code','')} {row.get('name','')} | {row.get('target_set','')} | "
                f"{row.get('label','中性')} | {_num(row.get('score')):+.2f} | "
                f"{row.get('score_source','')} | {row.get('data_quality','legacy')} | {row.get('summary','')} |"
            )
        L.append("- 以上信息沉淀到 `stock_sentiment*`、`agent_signals.jsonl` 和 `signal_snapshots.jsonl`；标题关键词只保留为 `keyword_score` 诊断，不产生做多信号。")
        L.append("- 只有 agent 结构化研判写入 `score_source=agent_review` 且 `score>=0.2` 时，才会标记 `ai_intelligence_short_star`，进入 forward_eval 做多影子 A/B；默认自动化为 `--intelligence-trade shadow`，不改 ★E。")
        L.append("- 显式 `--intelligence-trade on` 也只能在已通过资格的 ★E 内重排或移除，不能恢复 COLD/UNKNOWN、北交所或非 ★E 候选；趋势侧走 Book T / trend_guards 独立评估。")
        L.append("")
    L.append("## 候选清单")
    L.append("")
    L.append("| code | name | mode | rank | macro | conf | score | openRisk | entry | basket | slip | stop@basket(v5/v6) | open_pct | flags |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for c in selected:
        flags = []
        if c.get("kp_star"): flags.append(f"★KP{c.get('kp_rank', '')}")
        elif c.get("kp_keep") is False: flags.append("KP↓")
        if c["direction"]: flags.append("dir")
        if c["is_main_line"]: flags.append("main")
        if c["is_big_cap"]: flags.append("big")
        flag_s = "+".join(flags) if flags else "-"
        L.append(
            f"| {c['code']} | {c['name']} | {c['mode']} | "
            f"{_num(c['rank_score']):.1f} | {_num(c['macro_focus_score']):.0f} | "
            f"{_num(c['mode_confidence']):.1f} | {_num(c['primary_score']):.1f} | "
            f"{_num(c['open_risk_penalty']):.1f} | {_num(c['open']):.2f} | {_num(c['basket_price']):.2f} | "
            f"{_num(c['basket_slippage_pct']):+.2f}% | "
            f"{_num(c['v5_stop_at_basket']):.2f}/{_num(c['v6_stop_at_basket']):.2f} | "
            f"{_num(c['open_pct_change']):+.2f}% | {flag_s} |"
        )
    if standby:
        L.append("")
        L.append("## 小仓候补")
        L.append("")
        L.append("| code | name | mode | rank | macro | conf | score | entry | basket | stop@basket(v5/v6) | open_pct | reason |")
        L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for c in standby:
            L.append(
                f"| {c['code']} | {c['name']} | {c['mode']} | "
                f"{_num(c['rank_score']):.1f} | {_num(c['macro_focus_score']):.0f} | "
                f"{_num(c['mode_confidence']):.1f} | {_num(c['primary_score']):.1f} | "
                f"{_num(c['open']):.2f} | {_num(c['basket_price']):.2f} | "
                f"{_num(c['v5_stop_at_basket']):.2f}/{_num(c['v6_stop_at_basket']):.2f} | "
                f"{_num(c['open_pct_change']):+.2f}% | {c.get('standby_reason', '')} |"
            )
    if overflow:
        L.append("")
        L.append("## 观察名单")
        L.append("")
        L.append("| code | name | mode | rank | macro | conf | score | openRisk | basket | open_pct | reason |")
        L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for c in overflow:
            L.append(
                f"| {c['code']} | {c['name']} | {c['mode']} | "
                f"{_num(c['rank_score']):.1f} | {_num(c['macro_focus_score']):.0f} | "
                f"{_num(c['mode_confidence']):.1f} | {_num(c['primary_score']):.1f} | "
                f"{_num(c['open_risk_penalty']):.1f} | {_num(c['basket_price']):.2f} | "
                f"{_num(c['open_pct_change']):+.2f}% | 二级筛选未入选 |"
            )
    L.append("")
    L.append("## 实操建议")
    L.append("")
    L.append("1. 9:25 竞价撮合价确认后，看 entry / basket 和二级排序；超过 basket 不追")
    L.append("2. 成交后把**实际成交价**记录到 `output/live/positions.jsonl`；下面示例按 basket 最差成交填入，实盘请替换：")
    L.append("```jsonl")
    for c in selected[:2]:
        L.append(json.dumps({
            "code": c["code"], "name": c["name"],
            "entry_date": date_iso, "entry_price": c["basket_price"],
            "basket_price": c["basket_price"],
            "basket_rule": c["basket_rule"],
            "fill_assumption": "replace entry_price with actual fill; sample uses basket worst-case",
            "profile": "v5",  # or v6 — depends on which stop you commit to
            "shares": 1000,
        }, ensure_ascii=False))
    L.append("```")
    L.append("3. 盘中每 5-10 分钟跑 `python3 scripts/live_monitor.py` 看止损是否触发")
    L.append("")

    md = "\n".join(L)
    (OUT_DIR / f"recommend_{date_iso}.md").write_text(md, encoding="utf-8")
    if not args.no_stdout:
        print(md)
    print(f"\n[wrote {OUT_DIR / f'recommend_{date_iso}.md'}]", file=sys.stderr)


if __name__ == "__main__":
    main()
