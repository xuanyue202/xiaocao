"""Human-readable household rendering for KOL intelligence."""

from __future__ import annotations

import re
from typing import Any


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


def reader_message_title(item: dict[str, Any]) -> str:
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
    lines = [f"先说结论：{item['synthesis']['summary']}"]
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
        causal_parts = [*fundamentals, *trading]
        if causal_parts:
            lines.append(f"为什么会传导：{' → '.join(causal_parts)}")
        if events:
            lines.append(f"现在市场怎么验证：{validation.get('summary')}")
        signal_context = signal.get("context_assessment") or {}
        held_text = _reader_context_text(signal)
        funding_plan = signal.get("funding_plan") or signal_context.get("funding_plan")
        action = signal.get("action")
        needs_execution_text = signal_context.get("held") or action not in {
            "sell",
            "reduce",
            "hold",
        }
        execution_text = signal["execution"] if needs_execution_text else ""
        lines.append(f"对你意味着什么：{held_text}{execution_text}")
        if funding_plan:
            lines.append(f"资金怎么安排：{funding_plan}")
        lines.extend(
            [
                f"{_reader_timing_label(signal.get('action'))}：{signal['trigger']}",
                "什么情况需要重新评估："
                + "；".join(str(value) for value in signal["falsifiers"]),
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
            lines.extend(["", f"{label}{attribution}：{relation['judgment']}"])
    lines.extend(
        [
            "",
            f"信息来源：{item['author']}｜{item['title']}",
            "这只是决策信息，不会替你执行真实交易。",
        ]
    )
    return "\n".join(lines)


def render_household_message(result: dict[str, Any]) -> str:
    blocks = [
        render_household_item_message(item, result.get("cross_source") or {})
        for item in result.get("items") or []
    ]
    return "\n\n---\n\n".join(blocks) + "\n"
