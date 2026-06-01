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
import json
import sys
import time as _time
from datetime import date as _date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.datasource.api_source import ApiDataSource  # noqa: E402
from xiaocao.strategy import run_strategy  # noqa: E402
from xiaocao.utils.trading_session import A_SHARE_TZ  # noqa: E402

OUT_DIR = ROOT / "output" / "live"
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
MODE_CONFIDENCE_WINDOWS = (5, 10, 20)
MODE_CONFIDENCE_WEIGHTS = {5: 0.50, 10: 0.30, 20: 0.20}
BASKET_POLICY = {
    "接力低弱转1": {"premium": 2.0, "min": 1.5, "max": 2.5, "cap_pct": 10.0, "exec_cap_pct": 6.0},
    "接力低弱转2": {"premium": 1.2, "min": 0.8, "max": 1.8, "cap_pct": 8.0, "exec_cap_pct": 5.5},
    "红盘起爆主攻": {"premium": 2.0, "min": 1.5, "max": 2.5, "cap_pct": 10.0, "exec_cap_pct": 6.0},
    "方向红盘起爆": {"premium": 1.8, "min": 1.2, "max": 2.3, "cap_pct": 8.0, "exec_cap_pct": 5.5},
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


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    return XiaocaoClient(
        base_url=settings.base_url, timeout=settings.timeout,
        retries=settings.retries, cache=cache,
    )


def _resolve_date(date_arg: str) -> str:
    if date_arg in ("today", "latest"):
        return _date.today().isoformat()
    return date_arg


def _normal_date(value: object) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _trade_days(client: XiaocaoClient, date_iso: str, lookback_days: int = 90) -> list[str]:
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


def _entry_price(client: XiaocaoClient, code: str, date_iso: str) -> tuple[float | None, str, float | None]:
    """Fetch the best available early-session entry price for `code`.

    For today's live run, 9:25 call-auction completion should already expose
    the final opening price via the realtime detail `open` field. Indicative
    auction rows before 09:25 are not a stable entry price and are ignored.
    """
    if date_iso == _today_iso():
        try:
            detail = _extract_realtime_detail_row(client.second_line_detail_info(code), code)
        except Exception:
            detail = None
        if detail:
            td = _normal_date(detail.get("tradeDate") or "")
            if td == date_iso:
                try:
                    price = float(detail.get("open") or 0) or None
                except (TypeError, ValueError):
                    price = None
                if price:
                    pre_close = _to_float(detail.get("preClose"))
                    return price, "realtime_open", pre_close

    try:
        rows = client.date_kline(code, count=10, freq="D", adj="qfq")
    except Exception:
        rows = []
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
                    return price, "open", pre_close

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
                return price, "auction", pre_close
    return None, "", None


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


def _confidence_from_window_stats(windows: dict[int, dict[str, object]]) -> dict[str, object]:
    weighted_sum = 0.0
    weight_sum = 0.0
    max_n = 0
    for window in MODE_CONFIDENCE_WINDOWS:
        stat = windows.get(window) or {}
        n = int(_num(stat.get("n")))
        avg = _num(stat.get("avg"))
        if n <= 0:
            continue
        weight = MODE_CONFIDENCE_WEIGHTS[window]
        weighted_sum += avg * weight
        weight_sum += weight
        max_n = max(max_n, n)
    if weight_sum <= 0:
        return {
            "confidence": 50.0,
            "mode_recent_avg": 0.0,
            "mode_recent_n": 0,
            "mode_confidence_reason": "no recent mode_history",
        }
    recent_avg = weighted_sum / weight_sum
    raw_confidence = 50.0 + max(-10.0, min(10.0, recent_avg)) * 4.0
    shrink = min(1.0, max_n / 8.0)
    confidence = 50.0 + (raw_confidence - 50.0) * shrink
    return {
        "confidence": round(max(0.0, min(100.0, confidence)), 2),
        "mode_recent_avg": round(recent_avg, 2),
        "mode_recent_n": max_n,
        "mode_confidence_reason": f"5/10/20d weighted avg {recent_avg:+.2f}% n={max_n}",
    }


def _mode_confidence(
    cache: SQLiteCache | None,
    modes: set[str],
    date_iso: str,
    trade_days: list[str],
) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    if cache is None:
        return out
    effective_trade_days = trade_days or None
    for mode in modes:
        windows = {
            window: cache.mode_window_stats(mode, date_iso, window, trade_days=effective_trade_days)
            for window in MODE_CONFIDENCE_WINDOWS
        }
        out[mode] = _confidence_from_window_stats(windows)
    return out


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
    rank_score = score_fit * 0.60 + confidence * 0.25 + macro_score * 0.18 - open_risk_penalty
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
    out["mode_confidence_reason"] = confidence_info.get("mode_confidence_reason", "neutral")
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
        opn, entry_source, pre_close = _entry_price(client, code, date_iso)
        if not opn:
            continue
        open_pct_change = _open_pct_from_entry(opn, pre_close, r.get("openPctChange"))
        candidates.append({
            "code": code,
            "name": r.get("name") or "",
            "mode": r.get("mode") or "",
            "xcjw": _num(r.get("xcjw")),
            "cjs": _num(r.get("cjs")),
            "jsjl": _num(r.get("jsjl")),
            "jssb": _num(r.get("jssb")),
            "open": opn,
            "pre_close": pre_close,
            "entry_source": entry_source,
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
    mode_confidence = _mode_confidence(
        cache,
        {str(c.get("mode") or "") for c in candidates if c.get("mode")},
        date_iso,
        trade_days,
    )
    for c in candidates:
        mode = str(c.get("mode") or "")
        confidence = _num(mode_confidence.get(mode, {}).get("confidence", 50.0))
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
    if not args.no_kronos:
        try:
            import importlib.util as _ilu

            def _load(modname):
                _p = ROOT / "kronos_screen" / "scripts" / f"{modname}.py"
                _spec = _ilu.spec_from_file_location(modname, _p)
                _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m)
                return _m

            _load("secondary_screen").score(candidates, client, date_iso, top_n=max(1, args.kronos_top_n))
            kp_stars = [c for c in candidates if c.get("kp_star")]
            # Capture forward signals (auction imbalance) + A/B variant B + snapshot
            try:
                _load("capture_signals").capture(
                    candidates, client, date_iso,
                    is_live=_is_today_live_run(date_iso), top_n=max(1, args.kronos_top_n))
                vb_stars = [c for c in candidates if c.get("vb_star")]
            except Exception as e:
                print(f"[signal capture skipped: {type(e).__name__}: {e}]", file=sys.stderr)
        except Exception as e:  # missing model / torch / API — degrade gracefully
            print(f"[Kronos K→P skipped: {type(e).__name__}: {e}]", file=sys.stderr)

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
    L.append("")
    L.append("## Profiles 解读")
    L.append("")
    L.append("- **v5 (5d max_dd 2%)** = 持仓 5 日，从 post-entry peak 回撤 2% 即 trailing stop")
    L.append("- **v6 (3d max_dd 0.5%)** = 持仓 3 日，回撤 0.5% 即止 (aggressive，待 paper trading 验证)")
    L.append("- **入场价** = 9:25 集合竞价撮合出的开盘价（实时明细 open 字段优先）")
    L.append("- **买入看 entry / basket**：entry 是开盘参考价，basket 是建议挂单上限，不是默认成交价")
    L.append("- **篮子估算价** = mode-specific premium + mode recent confidence，并按 mode 控制 preClose cap")
    L.append("- **保护线必须按实际成交价重算**：表中 `stop@basket` 是按最差 basket 成交的保护线参考")
    L.append("- **二级筛选** = mode-specific score + mode recent confidence + 今日聚焦板块/大类加持，open_pct 只做极端执行风险惩罚")
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
        L.append(f"## ★B 实盘推荐 = K→P + 9:25竞价不平衡 tiebreak — {_tag}")
        L.append("")
        L.append("| ★B | code | name | mode | Pscore | 竞价涨幅 | 残余买卖压差 |")
        L.append("|---|---|---|---|---:|---:|---:|")
        for c in vb_stars:
            L.append(f"| {c.get('vb_rank','')} | {c['code']} | {c.get('name','')} | {c.get('mode','')} | "
                     f"{_num(c.get('p_score')):+.3f} | {_num(c.get('auc_pct')):+.2f}% | {_num(c.get('auc_residual_imb')):+.2f} |")
        L.append("- **★B = 实盘建议集**（仅当日实时有效）：在 K→P 幸存者中以 **P 为主排序、9:25 竞价不平衡(残余买卖压差+竞价涨幅)做最终 tiebreak**(权重 0.25，不覆盖强 P 信号)。")
        L.append("- **★ = A/B 基线**（纯 K→P，无竞价）。两套每日快照入 `output/live/signal_snapshots.jsonl`；`forward_eval.py --live-only` 累积真实收益后裁决竞价 tiebreak 是否带来增益（前瞻验证，历史不可回测）。")
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
