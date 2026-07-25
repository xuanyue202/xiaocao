"""Human-readable household rendering for KOL intelligence."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


_CHINESE_DIGITS = str.maketrans(
    {
        "零": "0",
        "〇": "0",
        "一": "1",
        "幺": "1",
        "二": "2",
        "两": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
    }
)
_SOURCE_LABELS = {
    "baidu_netdisk_opencli_dom": "百度网盘原视频（完整文稿）",
    "local_transcript": "本地原始文稿",
}


def _reader_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?<![零〇一幺二两三四五六七八九])"
        r"[零〇一幺二两三四五六七八九]{6}"
        r"(?![零〇一幺二两三四五六七八九])",
        lambda match: match.group(0).translate(_CHINESE_DIGITS),
        text,
    )
    return re.sub(
        r"(?<!\d)(\d{6})\.(?:XSHG|XSHE|BJSE)(?![A-Z])",
        r"\1",
        text,
    )


def _reader_asset_label(signal: dict[str, Any]) -> str:
    labels = []
    for asset in signal.get("assets") or []:
        name = _reader_text(asset.get("name") or "未命名机会").strip()
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


def _reader_confidence(value: Any) -> str:
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(str(value), str(value))


def _reader_market_status(value: Any) -> str:
    return {
        "support": "支持",
        "qualify": "有条件支持",
        "conflict": "与当前市场冲突",
        "invalidate": "当前已失效",
    }.get(str(value), str(value))


def _reader_time(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(value)


def _reader_source_title(item: dict[str, Any]) -> str:
    explicit = _reader_text(item.get("reader_title")).strip()
    if explicit:
        return explicit
    title = _reader_text(item.get("title")).strip()
    title = re.sub(r"\.(?:mp4|txt|md)$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\d{8}[\s_-]*", "", title)
    title = re.sub(
        r"[\s_-]*compressed(?:_\d{8}_\d{6})?$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.replace("_", " ").strip() or "原始内容"


def _reader_source_label(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "")
    media_type = str(item.get("media_type") or "")
    if source == "baidu_subscription_share_browser":
        return (
            "百度网盘订阅视频（完整文稿）"
            if media_type == "video"
            else "百度网盘订阅图片"
        )
    if source == "baidu_private_folder":
        return (
            "百度网盘私有目录视频（完整文稿）"
            if media_type == "video"
            else "百度网盘私有目录文稿"
        )
    return _SOURCE_LABELS.get(source, "原始材料")


def reader_market_facts(validation: dict[str, Any]) -> list[str]:
    facts = []
    for fact in validation.get("facts") or []:
        text = _reader_text(fact.get("reader_text") or "").strip()
        if not text:
            continue
        facts.append(f"{text}（观察于 {_reader_time(fact.get('observed_at'))}）")
    return facts


def _render_market_outlook(
    outlook: dict[str, Any],
    claims: list[dict[str, Any]],
) -> list[str]:
    claim_by_id = {claim.get("claim_id"): claim for claim in claims}
    author_quotes = [
        "「"
        + _reader_text(
            claim_by_id[claim_id].get("reader_quote")
            or claim_by_id[claim_id].get("quote")
        )
        + "」"
        for claim_id in outlook["claim_ids"]
    ]
    quote_label = (
        "来源要点（转录已校正）"
        if any(
            claim_by_id[claim_id].get("reader_quote")
            for claim_id in outlook["claim_ids"]
        )
        else "作者原话"
    )
    validation = outlook["current_validation"]
    lines = [
        f"【大盘与整体策略：{_reader_text(outlook['scope'])}】",
        f"今天盘面判断：{_reader_text(outlook['current_phase'])}",
        "下一交易日计划："
        + "；".join(_reader_text(value) for value in outlook["strategy"]),
        f"后续几天基础情景：{_reader_text(outlook['base_case'])}",
        "最新市场验证（截至 "
        f"{_reader_time(validation['as_of'])}，"
        f"{_reader_market_status(validation['status'])}）："
        f"{_reader_text(validation['summary'])}",
        quote_label + "：" + "；".join(author_quotes),
    ]
    lines.extend(
        f"关键事实：{fact}"
        for fact in reader_market_facts(validation)
    )
    lines.extend([
        "系统关注的关键转折："
        + "；".join(_reader_text(value) for value in outlook["turning_points"]),
        f"判断周期：{_reader_text(outlook['horizon'])}"
        f"（信心：{_reader_confidence(outlook['confidence'])}）",
        "什么情况需要改判："
        + "；".join(_reader_text(value) for value in outlook["falsifiers"]),
    ])
    return lines


def reader_message_title(item: dict[str, Any]) -> str:
    if item.get("decision_status") == "no_actionable_signal":
        return f"投资情报｜{item['author']}：弱信号提醒"
    if (item.get("synthesis") or {}).get("reader_render_mode") == (
        "kol_context_corrected"
    ):
        return f"投资情报｜{item['author']}：直播观点拆解"
    market_scope = _reader_text((item.get("market_outlook") or {}).get("scope")).strip()
    if market_scope:
        return f"投资情报｜{item['author']}：{market_scope}"
    names: list[str] = []
    for signal in item.get("actionable_signals") or []:
        for asset in signal.get("assets") or []:
            name = _reader_text(asset.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
    topic = "、".join(names[:3])
    if len(names) > 3:
        topic += "等"
    return f"投资情报｜{item['author']}" + (f"：{topic}" if topic else "")


def _render_kol_context_corrected(item: dict[str, Any]) -> str:
    synthesis = item.get("synthesis") or {}
    claims = {
        str(claim.get("claim_id")): claim
        for claim in item.get("claims") or []
        if isinstance(claim, dict)
    }
    requested_ids = synthesis.get("reader_quote_ids") or list(claims)
    quote_ids = [
        str(claim_id)
        for claim_id in requested_ids
        if str(claim_id) in claims
    ]
    lines = [
        f"【KOL观点｜{_reader_text(item['author'])}｜按逐字稿上下文校正】"
    ]
    for claim_id in quote_ids:
        claim = claims[claim_id]
        quote = _reader_text(claim.get("reader_quote")).strip()
        if quote:
            lines.append(f"- {quote}")
    analysis_points = [
        _reader_text(value).strip()
        for value in synthesis.get("analysis_points") or []
        if _reader_text(value).strip()
    ]
    if analysis_points:
        lines.extend(["", "【系统拆解｜对KOL逻辑的分析】"])
        lines.extend(f"- {value}" for value in analysis_points)
    system_check = _reader_text(synthesis.get("system_check")).strip()
    system_advice = _reader_text(synthesis.get("system_advice")).strip()
    if system_check:
        lines.extend(["", "【系统核对｜仅补事实】", system_check])
    if system_advice:
        lines.extend(["", "【系统结论】", system_advice])
    source_label = _reader_source_label(item)
    lines.extend(
        [
            "",
            "信息来源："
            f"{item['author']}｜{_reader_time(item.get('published_at'))}｜"
            f"{source_label}｜{_reader_source_title(item)}",
            "这只是决策信息，不会替你执行真实交易。",
        ]
    )
    return "\n".join(lines)


def reader_cross_source(
    item: dict[str, Any],
    cross_source: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    claim_ids = {str(claim.get("claim_id")) for claim in item.get("claims") or []}
    result: dict[str, list[dict[str, Any]]] = {
        "agreements": [],
        "conflicts": [],
    }
    for relation_type in result:
        for relation in (cross_source or {}).get(relation_type) or []:
            linked = (str(value) for value in relation.get("claim_ids") or [])
            if claim_ids.intersection(linked):
                result[relation_type].append(
                    {
                        "topic": relation.get("topic"),
                        "claim_ids": relation.get("claim_ids") or [],
                        "authors": relation.get("authors") or [],
                        "judgment": relation.get("judgment"),
                    }
                )
    return result


def render_household_item_message(
    item: dict[str, Any],
    cross_source: dict[str, Any] | None = None,
) -> str:
    """Render human-readable market intelligence; internal gates stay internal."""
    if item.get("decision_status") == "no_actionable_signal":
        return _render_no_actionable_signal(item)
    if (item.get("synthesis") or {}).get("reader_render_mode") == (
        "kol_context_corrected"
    ):
        return _render_kol_context_corrected(item)
    market_outlook = item.get("market_outlook") or {}
    if market_outlook:
        lines = _render_market_outlook(market_outlook, item["claims"])
        lines.extend(["", f"本次执行结论：{_reader_text(item['synthesis']['summary'])}"])
    else:
        lines = [f"先说结论：{_reader_text(item['synthesis']['summary'])}"]
    for signal in item.get("actionable_signals") or []:
        lines.extend(["", _reader_signal_heading(signal)])
        rationale = signal.get("rationale") or {}
        events = [_reader_text(value) for value in rationale.get("news_or_event") or []]
        fundamentals = [_reader_text(value) for value in rationale.get("fundamental") or []]
        trading = [_reader_text(value) for value in rationale.get("trading") or []]
        validation = signal.get("current_validation") or {}
        lines.append(
            "发生了什么："
            + ("；".join(events) if events else _reader_text(validation.get("summary")))
        )
        causal_parts = [*fundamentals, *trading]
        if causal_parts:
            lines.append(f"为什么会传导：{' → '.join(causal_parts)}")
        if events:
            lines.append(f"现在市场怎么验证：{_reader_text(validation.get('summary'))}")
        signal_context = signal.get("context_assessment") or {}
        held_text = _reader_context_text(signal)
        funding_plan = signal.get("funding_plan") or signal_context.get("funding_plan")
        action = signal.get("action")
        needs_execution_text = signal_context.get("held") or action not in {
            "sell",
            "reduce",
            "hold",
        }
        execution_text = _reader_text(signal["execution"]) if needs_execution_text else ""
        lines.append(f"对你意味着什么：{held_text}{execution_text}")
        if funding_plan:
            lines.append(f"资金怎么安排：{_reader_text(funding_plan)}")
        lines.extend(
            [
                f"{_reader_timing_label(signal.get('action'))}："
                f"{_reader_text(signal['trigger'])}",
                "什么情况需要重新评估："
                + "；".join(_reader_text(value) for value in signal["falsifiers"]),
            ]
        )
    relevant_cross_source = reader_cross_source(item, cross_source)
    for relation_type, label in (
        ("agreements", "多方共同信号"),
        ("conflicts", "多方不同判断"),
    ):
        for relation in relevant_cross_source[relation_type]:
            authors = "、".join(str(value) for value in relation.get("authors") or [])
            attribution = f"（{authors}）" if authors else ""
            lines.extend(
                ["", f"{label}{attribution}：{_reader_text(relation['judgment'])}"]
            )
    source_label = _reader_source_label(item)
    lines.extend(
        [
            "",
            "信息来源："
            f"{item['author']}｜{_reader_time(item.get('published_at'))}｜"
            f"{source_label}｜{_reader_source_title(item)}",
            "这只是决策信息，不会替你执行真实交易。",
        ]
    )
    return "\n".join(lines)


def _render_no_actionable_signal(item: dict[str, Any]) -> str:
    insight = item.get("reader_insight") or {}
    if insight.get("status") == "none":
        return ""
    positions: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for signal in item.get("actionable_signals") or []:
        context = signal.get("context_assessment") or {}
        for position in context.get("relevant_positions") or []:
            code = str(position.get("asset_code") or "").strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            positions.append(position)

    lines = ["【注意｜弱信号】"]
    lines.append(f"洞察：{_reader_text(insight.get('summary'))}")
    if positions:
        labels = []
        for position in positions:
            name = _reader_text(position.get("asset_name") or "").strip()
            code = str(position.get("asset_code") or "").strip()
            labels.append(f"{name}（{code}）" if name else code)
        lines.append(
            f"与你有关：家庭当前持有{'、'.join(labels)}；请注意波动，"
            "是否调整由你决定。"
        )
    lines.append(
        "边界："
        + _reader_text(
            insight.get("boundary")
            or "这是低置信度信息，不自动生成买卖动作。"
        )
    )
    source_label = _reader_source_label(item)
    lines.append(
        "来源："
        f"{item['author']}订阅｜{_reader_time(item.get('published_at'))}｜"
        f"{source_label}｜{_reader_source_title(item)}"
    )
    return "\n".join(lines)


def render_household_message(result: dict[str, Any]) -> str:
    blocks = [
        render_household_item_message(item, result.get("cross_source") or {})
        for item in result.get("items") or []
    ]
    return "\n\n---\n\n".join(blocks) + "\n"
