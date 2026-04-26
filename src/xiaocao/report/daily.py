from __future__ import annotations

from collections import Counter
from typing import Any


def build_daily_report(
    date: str,
    signals: list[dict[str, Any]],
    block_rank: list[dict[str, Any]] | None = None,
    category_rank: list[dict[str, Any]] | None = None,
    blockScore: Any | None = None,
    dynamicIndex: list[dict[str, Any]] | None = None,
    environment: Any | None = None,
    purpose: str = "盘前参考 / 盘后复盘",
    title: str | None = None,
    previous_date: str | None = None,
    previousSignals: list[dict[str, Any]] | None = None,
    performance: list[dict[str, Any]] | None = None,
    marketOverview: Any | None = None,
    topBlockDetails: list[dict[str, Any]] | None = None,
    candidateTechnical: dict[str, Any] | None = None,
    weekStats: dict[str, Any] | None = None,
) -> str:
    lines = [title or f"## {date} 小草模式日报", ""]
    name_map = _build_name_map(block_rank or [], category_rank or [], _rows(blockScore), dynamicIndex or [])
    lines.extend(_summary(signals, purpose, previous_date))
    lines.append("")
    lines.extend(_market_overview_section(marketOverview))
    lines.append("")
    lines.extend(_rank_section("### 强方向", block_rank or [], name_map, "blockCode"))
    lines.append("")
    lines.extend(_top_block_details_section(topBlockDetails or [], name_map))
    lines.append("")
    lines.extend(_rank_section("### 强方向大类", category_rank or [], name_map, "categoryCode"))
    lines.append("")
    lines.extend(_score_section(_rows(blockScore), name_map))
    lines.append("")
    lines.extend(_dynamic_section(dynamicIndex or [], name_map))
    lines.append("")
    lines.extend(_environment_section(environment))
    lines.append("")
    lines.extend(_week_stats_section(weekStats))
    lines.append("")
    if previousSignals is not None or performance is not None:
        lines.extend(_performance_section(previous_date, previousSignals or [], performance or []))
        lines.append("")
    lines.append("### 模式结果")
    lines.append("")
    lines.append(_signals_table(signals))
    lines.append("")
    lines.extend(_candidate_technical_section(candidateTechnical or {}, signals))
    return "\n".join(lines)


def _summary(signals: list[dict[str, Any]], purpose: str, previous_date: str | None = None) -> list[str]:
    lines = ["### 摘要", "", f"- 报告定位：{purpose}", "- 数据口径：按指定交易日聚合小草指数、方向、评分、环境与策略信号"]
    if previous_date:
        lines.append(f"- 对照交易日：{previous_date}")
    if not signals:
        return lines + ["- 信号数量：0"]
    counts = Counter(row.get("mode") or "未命名" for row in signals)
    lines.extend([f"- 信号数量：{len(signals)}", f"- 覆盖模式：{len(counts)}"])
    lines.extend(f"- {mode}：{count}" for mode, count in counts.most_common())
    return lines


def _performance_section(
    previous_date: str | None,
    previous_signals: list[dict[str, Any]],
    performance: list[dict[str, Any]],
) -> list[str]:
    title = f"### 昨日信号表现（{previous_date or '上一交易日'}开盘 -> 当前交易日收盘）"
    lines = [title, ""]
    if not previous_signals:
        return lines + ["_上一交易日没有策略信号_"]
    if not performance:
        return lines + ["_暂无可计算收益率，可能是本地数据源或 K 线数据未返回对应日期_"]
    returns = [_num(row.get("收益率%")) for row in performance if row.get("收益率%") not in (None, "")]
    if returns:
        win_rate = sum(1 for item in returns if item > 0) / len(returns) * 100
        avg_return = sum(returns) / len(returns)
        lines.extend([f"- 可计算股票数：{len(returns)}", f"- 平均收益率：{avg_return:.2f}%", f"- 正收益占比：{win_rate:.1f}%", ""])
    lines.append(_markdown_table(performance))
    return lines


def _rank_section(title: str, rows: list[dict[str, Any]], name_map: dict[str, str], code_field: str) -> list[str]:
    lines = [title, ""]
    ranked_rows = [row for row in rows if _num(row.get("num")) != 0]
    top_rows = sorted(ranked_rows, key=lambda row: _num(row.get("num")), reverse=True)[:5]
    if not top_rows:
        return lines + ["_当前模型无非零强度方向_"]
    table_rows = [
        {
            "排名": index,
            "代码": _code(row, code_field),
            "名称": _name(row, name_map, code_field),
            "强度": _fmt(row.get("num")),
            "变化": _fmt(row.get("numChange")),
            "前涨幅%": _fmt(row.get("prePctChangeRate")),
            "股票数": row.get("stockCount"),
        }
        for index, row in enumerate(top_rows, start=1)
    ]
    return lines + [_markdown_table(table_rows)]


def _score_section(rows: list[dict[str, Any]], name_map: dict[str, str]) -> list[str]:
    lines = ["### 板块评分", ""]
    if not rows:
        return lines + ["_No data_"]
    top_rows = sorted(rows, key=lambda row: _num(row.get("shortLineScore")), reverse=True)[:5]
    table_rows = [
        {
            "排名": row.get("rank") or index,
            "代码": _code(row, "code"),
            "名称": _name(row, name_map, "code"),
            "短线分": _fmt(row.get("shortLineScore")),
            "趋势分": _fmt(row.get("trendScore")),
            "前涨幅%": _fmt(row.get("prePctChangeRate")),
            "股票数": row.get("stockCount"),
        }
        for index, row in enumerate(top_rows, start=1)
    ]
    return lines + [_markdown_table(table_rows)]


def _dynamic_section(rows: list[dict[str, Any]], name_map: dict[str, str]) -> list[str]:
    lines = ["### 动态指数", ""]
    if not rows:
        return lines + ["_No data_"]
    top_rows = sorted(rows, key=lambda row: _num(row.get("score")), reverse=True)[:5]
    table_rows = [
        {
            "排名": index,
            "代码": _code(row, "categoryCode"),
            "名称": _name(row, name_map, "categoryCode"),
            "分数": _fmt(row.get("score")),
            "变化": _fmt(row.get("scoreChange")),
            "前值变化": _fmt(row.get("scoreChangePre")),
            "跟踪": _yes_no(row.get("isTrack")),
        }
        for index, row in enumerate(top_rows, start=1)
    ]
    return lines + [_markdown_table(table_rows)]


def _environment_section(environment: Any) -> list[str]:
    lines = ["### 环境分时", ""]
    rows = _rows(environment)
    if not rows:
        return lines + ["_No data_"]
    table_rows = []
    for index, row in enumerate(rows[:8], start=1):
        table_rows.append(
            {
                "序号": index,
                "代码": row.get("code") or row.get("indexCode") or row.get("label"),
                "名称": row.get("name") or row.get("codeName") or row.get("indexName"),
                "现值": _fmt(row.get("trade") or row.get("close")),
                "涨跌幅%": _fmt(row.get("pctChangeRate")),
                "短线分": _fmt(row.get("shortLineScore")),
                "趋势分": _fmt(row.get("trendScore")),
                "股票数": row.get("stockCount"),
            }
        )
    return lines + [_markdown_table(table_rows)]


def _signals_table(signals: list[dict[str, Any]]) -> str:
    rows = [
        {
            "日期": row.get("date"),
            "模式": row.get("mode"),
            "代码": row.get("code"),
            "名称": row.get("name"),
            "竞王": _fmt(row.get("xcjw")),
            "低吸": _fmt(row.get("cjs")),
            "接力": _fmt(row.get("jsjl")),
            "红盘": _fmt(row.get("jssb")),
            "当日%": _fmt(row.get("pctChange")),
            "开盘%": _fmt(row.get("openPctChange")),
            "方向": "是" if row.get("direction") else "否",
            "方向排名": row.get("directionRank"),
            "大类排名": row.get("categoryRank"),
            "原因": row.get("reason"),
        }
        for row in signals
    ]
    return _markdown_table(rows)


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("data", "list", "rows", "result"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
        return [row for row in value.values() if isinstance(row, dict)]
    return []


def _build_name_map(*groups: list[dict[str, Any]]) -> dict[str, str]:
    name_map: dict[str, str] = {}
    for rows in groups:
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = _code(row, "code")
            name = row.get("name") or row.get("blockName") or row.get("categoryName") or row.get("codeName")
            if code and name:
                name_map[str(code)] = str(name)
            for nested_key in ("blockRankList", "blockScoreList", "blockDynamicIndexList"):
                for nested in row.get(nested_key) or []:
                    if isinstance(nested, dict):
                        nested_code = _code(nested, "code")
                        nested_name = nested.get("name") or nested.get("blockName") or nested.get("categoryName")
                        if nested_code and nested_name:
                            name_map[str(nested_code)] = str(nested_name)
    return name_map


def _code(row: dict[str, Any], preferred_key: str) -> Any:
    return row.get(preferred_key) or row.get("code") or row.get("blockCode") or row.get("categoryCode")


def _name(row: dict[str, Any], name_map: dict[str, str], code_field: str) -> str:
    code = _code(row, code_field)
    return str(row.get("name") or row.get("blockName") or row.get("categoryName") or row.get("codeName") or name_map.get(str(code), ""))


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_No data_"
    headers = [key for key in rows[0].keys() if any(_present(row.get(key)) for row in rows)]
    if not headers:
        return "_No data_"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(row.get(header)) for header in headers) + " |")
    return "\n".join(lines)


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ")


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _yes_no(value: Any) -> str:
    if value is None:
        return ""
    return "是" if str(value) in {"1", "true", "True"} else "否"


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _market_overview_section(overview: Any) -> list[str]:
    lines = ["### 市场概览", ""]
    if overview is None:
        return lines + ["_未拉取（local source 或 --no-extras）_"]
    if isinstance(overview, dict):
        # Surface the most informative scalar fields if present.
        rows = []
        for key in (
            "marketHeat", "marketScore", "marketTrend",
            "positiveCount", "negativeCount", "neutralCount",
            "limitUpCount", "limitDownCount",
            "totalAmt", "totalVol",
        ):
            if key in overview and _present(overview[key]):
                rows.append({"字段": key, "值": _fmt(overview[key])})
        if rows:
            return lines + [_markdown_table(rows)]
        # Fallback: render whatever scalar keys exist.
        flat = [
            {"字段": k, "值": _fmt(v)}
            for k, v in overview.items()
            if not isinstance(v, (list, dict)) and _present(v)
        ]
        if flat:
            return lines + [_markdown_table(flat[:12])]
    return lines + ["_No data_"]


def _top_block_details_section(details: list[dict[str, Any]], name_map: dict[str, str]) -> list[str]:
    lines = ["### 强方向详情", ""]
    if not details:
        return lines + ["_未拉取（local source 或 --no-extras）_"]
    table_rows = []
    for index, row in enumerate(details, start=1):
        if not isinstance(row, dict):
            continue
        code = _code(row, "code")
        table_rows.append({
            "序号": index,
            "代码": code,
            "名称": _name(row, name_map, "code"),
            "短线分": _fmt(row.get("shortLineScore")),
            "趋势分": _fmt(row.get("trendScore")),
            "排名": row.get("rank"),
            "位置": _fmt(row.get("position")),
            "类型": row.get("blockType"),
            "涨跌幅%": _fmt(row.get("pctChangeRate")),
        })
    if not table_rows:
        return lines + ["_No data_"]
    return lines + [_markdown_table(table_rows)]


def _candidate_technical_section(
    technical: dict[str, Any],
    signals: list[dict[str, Any]],
) -> list[str]:
    lines = ["### 候选股 smallGrass 技术指标", ""]
    if not technical:
        return lines + ["_未拉取（local source 或 --no-extras）_"]
    code_to_name = {}
    for sig in signals:
        if isinstance(sig, dict):
            code = sig.get("code")
            if code:
                code_to_name[str(code)] = sig.get("name") or ""
    table_rows = []
    for code, payload in technical.items():
        rows = _rows(payload)
        latest = rows[-1] if rows else (payload if isinstance(payload, dict) else None)
        if not isinstance(latest, dict):
            continue
        table_rows.append({
            "代码": code,
            "名称": code_to_name.get(str(code), latest.get("codeName", "")),
            "ema": _fmt(latest.get("ema")),
            "aaaLine": _fmt(latest.get("aaaLine")),
            "bbbLine": _fmt(latest.get("bbbLine")),
            "trade": _fmt(latest.get("trade")),
            "tradeDate": latest.get("tradeDate"),
        })
    if not table_rows:
        return lines + ["_拉取到的指标数据为空_"]
    return lines + [_markdown_table(table_rows)]


def _week_stats_section(week_stats: Any) -> list[str]:
    lines = ["### 本周模式持仓"]
    if not week_stats:
        return []  # Skip the section entirely when not available — avoid clutter.
    if not isinstance(week_stats, dict):
        return []
    counts = {key: len(value or []) for key, value in week_stats.items() if isinstance(value, list)}
    if not any(counts.values()):
        return []
    lines.append("")
    table_rows = [{"模式": mode, "在持数": count} for mode, count in counts.items()]
    return lines + [_markdown_table(table_rows)]
