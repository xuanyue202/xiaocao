from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .errors import ApiSchemaError


BodyStyle = Literal["params", "raw"]
BaseHost = Literal["XC", "PZ"]
EndpointStatus = Literal["stable", "experimental", "planned"]


@dataclass(frozen=True)
class NamedValue:
    key: str
    value: int
    label: str
    description: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "label": self.label,
            "description": self.description,
        }


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    path: str
    purpose: str
    params: str
    returns: str
    body_style: BodyStyle = "params"
    base: BaseHost = "XC"
    auth_required: bool = True
    status: EndpointStatus = "stable"
    source_evidence: str = ""
    cli_command: str = ""
    client_method: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "purpose": self.purpose,
            "params": self.params,
            "returns": self.returns,
            "body_style": self.body_style,
            "base": self.base,
            "auth_required": self.auth_required,
            "status": self.status,
            "source_evidence": self.source_evidence,
            "cli_command": self.cli_command,
            "client_method": self.client_method,
        }


STOCK_GROUPS: dict[str, NamedValue] = {
    "jieli": NamedValue("jieli", 0, "连板接力", "alias of xiaocaoJSJL"),
    "lianban": NamedValue("lianban", 0, "连板接力", "legacy alias"),
    "jsjl": NamedValue("jsjl", 0, "连板接力", "short alias"),
    "xiaocaoJSJL": NamedValue("xiaocaoJSJL", 0, "小草连板接力"),
    "jingwang": NamedValue("jingwang", 1, "竞王", "alias of xiaocaoXCJW"),
    "xcjw": NamedValue("xcjw", 1, "竞王", "short alias"),
    "xiaocaoXCJW": NamedValue("xiaocaoXCJW", 1, "小草竞王"),
    "hpqb": NamedValue("hpqb", 2, "红盘起爆", "alias of xiaocaoJSSB"),
    "qibao": NamedValue("qibao", 2, "红盘起爆", "legacy alias"),
    "jssb": NamedValue("jssb", 2, "红盘起爆", "short alias"),
    "xiaocaoJSSB": NamedValue("xiaocaoJSSB", 2, "小草红盘起爆"),
    "dixi": NamedValue("dixi", 3, "绿盘低吸", "alias of xiaocaoCJS"),
    "cjs": NamedValue("cjs", 3, "绿盘低吸", "short alias"),
    "xiaocaoCJS": NamedValue("xiaocaoCJS", 3, "小草绿盘低吸"),
    "dwcjs": NamedValue("dwcjs", 4, "低位绿盘低吸"),
    "xiaocaoDWCJS": NamedValue("xiaocaoDWCJS", 4, "低位绿盘低吸"),
    "jsjl_test": NamedValue("jsjl_test", 30, "连板接力-专享"),
    "jssb_test": NamedValue("jssb_test", 31, "红盘起爆-专享"),
    "cjs_test": NamedValue("cjs_test", 32, "绿盘低吸-专享"),
}


SORT_V2_FIELDS: dict[str, NamedValue] = {
    "agencynetbAmt": NamedValue("agencynetbAmt", 3, "主力净额"),
    "tradeRate5d": NamedValue("tradeRate5d", 4, "5日涨幅"),
    "tradeRate10d": NamedValue("tradeRate10d", 5, "10日涨幅"),
    "tradeRate20d": NamedValue("tradeRate20d", 6, "20日涨幅"),
    "pctChangeRate": NamedValue("pctChangeRate", 7, "涨幅"),
    "trade": NamedValue("trade", 8, "最新价 / 现价"),
    "pctChange": NamedValue("pctChange", 9, "涨跌"),
    "agencynetbVol": NamedValue("agencynetbVol", 10, "主力净量"),
    "volRate": NamedValue("volRate", 11, "量比"),
    "riseRate": NamedValue("riseRate", 12, "涨速"),
    "circulationMarketValue": NamedValue("circulationMarketValue", 14, "流通市值"),
    "vol": NamedValue("vol", 16, "成交量"),
    "turnoverRate": NamedValue("turnoverRate", 17, "换手率"),
    "amplitude": NamedValue("amplitude", 18, "振幅"),
    "peRate": NamedValue("peRate", 19, "市盈(动)"),
    "high": NamedValue("high", 20, "最高"),
    "low": NamedValue("low", 21, "最低"),
    "open": NamedValue("open", 22, "开盘"),
    "preClose": NamedValue("preClose", 23, "昨收"),
    "volOut": NamedValue("volOut", 24, "外盘"),
    "volIn": NamedValue("volIn", 25, "内盘"),
    "amt": NamedValue("amt", 26, "成交额"),
    "upNum": NamedValue("upNum", 27, "涨家数"),
    "downNum": NamedValue("downNum", 28, "跌家数"),
    "limitUpNum": NamedValue("limitUpNum", 29, "涨停家数"),
    "allBuyAmt": NamedValue("allBuyAmt", 30, "总买额 / 委买额"),
    "allBuySellAmt": NamedValue("allBuySellAmt", 31, "买卖差额 / 净流入"),
    "allBuySellAmt5d": NamedValue("allBuySellAmt5d", 32, "5日买卖差额 / 5日净流入"),
    "openPctChangeRate": NamedValue("openPctChangeRate", 33, "开幅"),
    "entityPctChangeRate": NamedValue("entityPctChangeRate", 34, "当日盈亏"),
    "preLimitUpDays": NamedValue("preLimitUpDays", 35, "昨日连板"),
    "limitUpDays": NamedValue("limitUpDays", 36, "今日连板"),
    "xiaocaoJSJL": NamedValue("xiaocaoJSJL", 37, "小草连板接力"),
    "xiaocaoXCJW": NamedValue("xiaocaoXCJW", 38, "小草竞王"),
    "xiaocaoJSSB": NamedValue("xiaocaoJSSB", 39, "小草红盘起爆"),
    "xiaocaoCJS": NamedValue("xiaocaoCJS", 40, "小草绿盘低吸"),
    "xiaocaoDWCJS": NamedValue("xiaocaoDWCJS", 41, "低位绿盘低吸"),
    "jsjlTest": NamedValue("jsjlTest", 44, "连板接力-专享"),
    "jssbTest": NamedValue("jssbTest", 45, "红盘起爆-专享"),
    "cjsTest": NamedValue("cjsTest", 46, "绿盘低吸-专享"),
    "directionCjs": NamedValue("directionCjs", 47, "方向绿盘低吸"),
    "xcjwV2": NamedValue("xcjwV2", 48, "小草竞王 V2"),
    "jssbV2": NamedValue("jssbV2", 49, "红盘起爆 V2"),
    "cjsV2": NamedValue("cjsV2", 50, "绿盘低吸 V2"),
    "jsjlBlock": NamedValue("jsjlBlock", 51, "板块连板接力"),
    "jssbBlock": NamedValue("jssbBlock", 52, "板块红盘起爆"),
    "cjsBlock": NamedValue("cjsBlock", 53, "板块绿盘低吸"),
    "directionCjsV2": NamedValue("directionCjsV2", 54, "方向绿盘低吸 V2"),
    "cgyk": NamedValue("cgyk", 55, "下杀相关盈亏指标"),
    "htyk": NamedValue("htyk", 56, "回调相关盈亏指标"),
    "minuteCgyk": NamedValue("minuteCgyk", 57, "分钟级下杀相关指标"),
    "minuteHtyk": NamedValue("minuteHtyk", 58, "分钟级回调相关指标"),
    "atraderate30d": NamedValue("atraderate30d", 59, "30日涨幅/长周期收益率"),
    "atraderate10d": NamedValue("atraderate10d", 60, "10日涨幅/短周期收益率"),
}

SORT_V2_ALIASES = {
    "jsjl": "xiaocaoJSJL",
    "jieli": "xiaocaoJSJL",
    "lianban": "xiaocaoJSJL",
    "xcjw": "xiaocaoXCJW",
    "jingwang": "xiaocaoXCJW",
    "jssb": "xiaocaoJSSB",
    "hpqb": "xiaocaoJSSB",
    "qibao": "xiaocaoJSSB",
    "cjs": "xiaocaoCJS",
    "dixi": "xiaocaoCJS",
    "dwcjs": "xiaocaoDWCJS",
}

SORT_DIRECTIONS = {
    "desc": NamedValue("desc", 1, "降序"),
    "asc": NamedValue("asc", 0, "升序"),
}

SORT_TARGET_TYPES = {
    "stock": NamedValue("stock", 0, "股票排序"),
    "block": NamedValue("block", 1, "板块排序"),
}

RANK_MODELS = {
    "full": NamedValue("full", 0, "全量强度排行", "报告展示优先使用"),
    "focus": NamedValue("focus", 1, "精选/短线重点口径", "策略加持可使用"),
    "full_alias_2": NamedValue("full_alias_2", 2, "全量强度排行别名"),
    "full_alias_3": NamedValue("full_alias_3", 3, "全量强度排行别名"),
}

DYNAMIC_INDEX_TYPES = {
    "jinglong": NamedValue("jinglong", 0, "jinglong 视图口径", "front-end branch type === jinglong"),
    "default": NamedValue("default", 1, "非 jinglong 视图口径"),
}


# Backend-accepted values for the technical-index `indicators` parameter.
# Source: reference/index-f3118026.js — Zd array (~5747); the broader h6 array
# (~5746) also lists `smallGrassTrend`, `klinesma`, `mike`, but those are
# rendered locally by the frontend and are NOT accepted by the backend.
INDICATORS_BACKEND: dict[str, NamedValue] = {
    "smallGrass": NamedValue("smallGrass", 0, "小草核心指标", "ema/aaaLine/bbbLine 等小草自有线"),
    "vol": NamedValue("vol", 1, "成交量"),
    "amt": NamedValue("amt", 2, "成交额"),
    "macd": NamedValue("macd", 3, "MACD"),
    "rsi": NamedValue("rsi", 4, "RSI"),
    "kdj": NamedValue("kdj", 5, "KDJ"),
    "boll": NamedValue("boll", 6, "布林带"),
}

INDICATORS_FRONTEND_ONLY: dict[str, NamedValue] = {
    "smallGrassTrend": NamedValue("smallGrassTrend", 0, "小草趋势线", "前端本地渲染，后端不接受"),
    "klinesma": NamedValue("klinesma", 1, "K 线均线", "前端本地渲染"),
    "mike": NamedValue("mike", 2, "麦克支撑压力", "前端本地渲染"),
}

KLINE_FREQS: dict[str, NamedValue] = {
    "5min": NamedValue("5min", 0, "5 分钟"),
    "15min": NamedValue("15min", 1, "15 分钟"),
    "30min": NamedValue("30min", 2, "30 分钟"),
    "60min": NamedValue("60min", 3, "60 分钟"),
    "D": NamedValue("D", 4, "日线"),
    "W": NamedValue("W", 5, "周线"),
    "M": NamedValue("M", 6, "月线"),
    "Q": NamedValue("Q", 7, "季线"),
    "Y": NamedValue("Y", 8, "年线"),
}

KLINE_ADJUSTMENTS: dict[str, NamedValue] = {
    "qfq": NamedValue("qfq", 0, "前复权", "JS K0 默认；分钟周期常用"),
    "bfq": NamedValue("bfq", 1, "不复权", "日线及以上常用"),
}


_JS = "reference/index-f3118026.js"

ENDPOINTS: dict[str, EndpointSpec] = {
    "sort_v2": EndpointSpec(
        "sort_v2",
        "/stock/sort_v2",
        "对给定股票或板块集合按前端 sortKey/sortId 排序",
        "queryType, sortId/sortKey, sortType, type, date, hpqbState, lpdxState, stockIds",
        "排序后的 code/stockId 列表或对象列表，前端会按原始 stockIds 再过滤",
        source_evidence=f"{_JS}: sort wrapper using sortId enum",
        cli_command="data sort",
        client_method="sort_v2",
    ),
    "get_code_list_v2": EndpointSpec(
        "get_code_list_v2",
        "/stock/focus_xiao_cao_index/get_code_list_v2",
        "按小草模式拉股票池",
        "groups, date, hpqbState, lpdxState",
        "result.data 或 result 列表中的股票代码",
        source_evidence=f"{_JS}: focus_xiao_cao_index pool fetch",
        cli_command="data pool",
        client_method="get_code_list_v2",
    ),
    "xiao_cao_industry_block_rank": EndpointSpec(
        "xiao_cao_industry_block_rank",
        "/stock/xiao_cao_industry_block_rank",
        "行业/方向强度排行",
        "date, model/full|focus|full_alias_2|full_alias_3",
        "方向排行列表，含 blockCode/blockName/num/trendScore 等",
        source_evidence=f"{_JS}: industry block rank wrapper",
        cli_command="block rank",
        client_method="get_industry_block_rank",
    ),
    "xiao_cao_block_category_rank_v3": EndpointSpec(
        "xiao_cao_block_category_rank_v3",
        "/stock/xiao_cao_block_category_rank_v3",
        "方向大类/分类排行",
        "date, model/full|focus|full_alias_2|full_alias_3",
        "分类排行列表或 localCategoryRankList/globalCategoryRankList/data",
        source_evidence=f"{_JS}: block category rank v3 wrapper",
        cli_command="block category-rank",
        client_method="get_block_category_rank_v3",
    ),
    "xiao_cao_dynamic_index": EndpointSpec(
        "xiao_cao_dynamic_index",
        "/stock/xiao_cao_dynamic_index",
        "动态方向指数",
        "tradeDate, indexType/jinglong|default",
        "动态指数列表，含 categoryCode/blockCode/score/scoreChange 等",
        source_evidence=f"{_JS}: dynamic index wrapper (jinglong branch)",
        cli_command="index dynamic",
        client_method="get_xiao_cao_dynamic_index",
    ),
    "xiao_cao_index_v2": EndpointSpec(
        "xiao_cao_index_v2",
        "/stock/xiao_cao_index_v2",
        "批量获取股票小草指数、模式分、方向归属和行情字段",
        "stockCodes, date, hpqbState, lpdxState",
        "code -> object 映射或列表，client 会转成列表并补 code",
        source_evidence=f"{_JS}: xiao_cao_index_v2 batch wrapper",
        cli_command="index stock",
        client_method="get_xiao_cao_index_v2",
    ),
    "xiao_cao_block_score": EndpointSpec(
        "xiao_cao_block_score",
        "/stock/xiao_cao_block_score",
        "板块强度评分",
        "date",
        "板块评分列表或对象，含强度、涨跌变化、跟踪状态等",
        source_evidence=f"{_JS}: block score wrapper",
        cli_command="block score",
        client_method="get_block_score",
    ),
    "trade_cal": EndpointSpec(
        "trade_cal",
        "/stock/trade_cal",
        "交易日历",
        "exchange, isOpen, startDate, endDate",
        "交易日列表，常见字段 calDate/isOpen",
        source_evidence=f"{_JS}: trade_cal wrapper",
        cli_command="calendar trade-days",
        client_method="get_trade_cal",
    ),
    "next_trade_cal": EndpointSpec(
        "next_trade_cal",
        "/stock/next_trade_cal",
        "下一交易日/下一个开市日",
        "exchange, isOpen, startDate, endDate",
        "列表、对象或 YYYYMMDD 字符串，client 会兼容归一",
        source_evidence=f"{_JS}: next_trade_cal wrapper",
        cli_command="calendar next",
        client_method="next_trade_cal",
    ),
    "get_code_by_xiao_cao_block": EndpointSpec(
        "get_code_by_xiao_cao_block",
        "/stock/get_code_by_xiao_cao_block",
        "按方向/行业/分类/模式反查股票池",
        "blockCodeList, industryBlockCodeList, categoryCodeList, patternCodeList, tradeDate 等",
        "股票代码列表、嵌套列表或对象，datasource 会抽取代码",
        source_evidence=f"{_JS}: get_code_by_xiao_cao_block wrapper",
        cli_command="block stocks",
        client_method="get_code_by_xiao_cao_block",
    ),
    "second_line": EndpointSpec(
        "second_line",
        "/stock/second_line",
        "股票/指数秒级分时",
        "code",
        "分时线列表，含 OHLC、盘口、成交、时间戳等",
        source_evidence=f"{_JS}: second_line wrapper",
        cli_command="market second-line",
        client_method="second_line",
    ),
    "second_line_detail_info": EndpointSpec(
        "second_line_detail_info",
        "/stock/second_line_detail_info",
        "多代码分时详情摘要",
        "codes",
        "当前快照映射或列表，含行情、成交、时间和盘口字段",
        source_evidence=f"{_JS}: second_line_detail_info wrapper",
        cli_command="market second-line-detail",
        client_method="second_line_detail_info",
    ),
    "xiao_cao_environment_second_line_v2": EndpointSpec(
        "xiao_cao_environment_second_line_v2",
        "/stock/xiao_cao_environment_second_line_v2",
        "小草环境分时 v2",
        "code, date, codeType, isFoolMode",
        "环境分时时序列表",
        source_evidence=f"{_JS}: environment second_line v2 wrapper",
        cli_command="market environment",
        client_method="xiao_cao_environment_second_line_v2",
    ),
    "minute_line": EndpointSpec(
        "minute_line",
        "/stock/minute_line",
        "股票分钟线",
        "adj, freq, code",
        "分钟 K/分时列表，含 tradeDate/tradeTime/OHLC/vol/amt",
        source_evidence=f"{_JS}: minute_line wrapper",
        cli_command="quote minute",
        client_method="minute_line",
    ),
    "date_kline": EndpointSpec(
        "date_kline",
        "/stock/date_kline",
        "股票日/周/月等 K 线",
        "count, code, freq, adj, codeType, paramTime",
        "K 线列表，含 OHLC、涨跌幅、换手率、量额等",
        source_evidence=f"{_JS}: date_kline wrapper, freq enum (~5728)",
        cli_command="quote history",
        client_method="date_kline",
    ),
    "stock_call_auction": EndpointSpec(
        "stock_call_auction",
        "/stock/stock_call_auction",
        "个股集合竞价",
        "code, tradeDate",
        "集合竞价列表，含 trade/pctChange/buyVol2/sellVol2 等",
        source_evidence=f"{_JS}: stock_call_auction wrapper",
        cli_command="quote auction",
        client_method="stock_call_auction",
    ),
    "stock_info": EndpointSpec(
        "stock_info",
        "/stock/stock_info",
        "全量股票/板块基础信息",
        "无参数或空对象",
        "列表，含 code/codeName/statusType/blockType/la 等",
        source_evidence=f"{_JS}: stock_info wrapper",
        cli_command="market stock-info",
        client_method="stock_info",
    ),
    "etf_info": EndpointSpec(
        "etf_info",
        "/stock/etf_info",
        "ETF 目录与交易日元数据",
        "tradeDate",
        "ETF 目录列表；client 保留原始字段及 trade-date provenance",
        source_evidence=f"{_JS}: etf_info wrapper (~23387), daily cache (~23433)",
        cli_command="market etf-info",
        client_method="etf_info",
    ),
    "market_overview": EndpointSpec(
        "market_overview",
        "/stock/market_overview",
        "市场概览",
        "空对象",
        "市场总览对象",
        source_evidence=f"{_JS}: market_overview wrapper",
        cli_command="market overview",
        client_method="market_overview",
    ),
    "each_trade": EndpointSpec(
        "each_trade",
        "/stock/each_trade",
        "逐笔成交",
        "code, count, codeType, isLess 等",
        "逐笔列表，前端映射 trade/oneVol/oneAmt/bsFlag/time",
        source_evidence=f"{_JS}: each_trade wrapper",
        cli_command="market each-trade",
        client_method="each_trade",
    ),
    "xiao_cao_block_detail": EndpointSpec(
        "xiao_cao_block_detail",
        "/stock/xiao_cao_block_detail",
        "单个板块详情",
        "code, tradeDate",
        "详情对象，含 shortLineScore/trendScore/blockType/position/rank/blockScoreList",
        source_evidence=f"{_JS}: block detail wrapper",
        cli_command="block detail",
        client_method="xiao_cao_block_detail",
    ),
    "xiao_cao_week_stats": EndpointSpec(
        "xiao_cao_week_stats",
        "/stock/xiao_cao_week_stats",
        "小草模式周统计",
        "空 params",
        "jsjl/xcjw/jssb/cjs 四组周状态列表",
        source_evidence=f"{_JS}: week_stats wrapper",
        cli_command="market week-stats",
        client_method="xiao_cao_week_stats",
    ),
    "xiao_cao_block_date_kline": EndpointSpec(
        "xiao_cao_block_date_kline",
        "/stock/xiao_cao_block_date_kline",
        "小草板块日/周/月 K 线",
        "count, code, freq, adj, codeType, paramTime",
        "标准化 K 线列表",
        source_evidence=f"{_JS}: block date_kline wrapper",
        cli_command="block kline",
        client_method="xiao_cao_block_date_kline",
    ),
    "xiao_cao_environment_minute_line": EndpointSpec(
        "xiao_cao_environment_minute_line",
        "/stock/xiao_cao_environment_minute_line",
        "小草环境分钟分时",
        "code, tradeDate, adj, freq",
        "标准化 1min 分时列表",
        source_evidence=f"{_JS}: environment minute_line wrapper",
        cli_command="market env-minute",
        client_method="xiao_cao_environment_minute_line",
    ),
    "xiao_cao_environment_second_line_selection": EndpointSpec(
        "xiao_cao_environment_second_line_selection",
        "/stock/xiao_cao_environment_second_line_selection",
        "小草环境分时精选集合",
        "date",
        "环境精选快照列表",
        source_evidence=f"{_JS}: environment second_line selection wrapper",
        cli_command="market env-selection",
        client_method="xiao_cao_environment_second_line_selection",
    ),
    "xiao_cao_industry_block_dynamic_index": EndpointSpec(
        "xiao_cao_industry_block_dynamic_index",
        "/stock/xiao_cao_industry_block_dynamic_index",
        "行业动态指数",
        "tradeDate, indexType/jinglong|default",
        "行业动态指数列表",
        source_evidence=f"{_JS}: industry dynamic index wrapper",
        cli_command="index industry-dynamic",
        client_method="get_xiao_cao_industry_block_dynamic_index",
    ),
    "get_technical_index": EndpointSpec(
        "get_technical_index",
        "/stock/get_technical_index",
        "技术指标当前值/分时指标",
        "code, indicators (smallGrass|vol|amt|macd|rsi|kdj|boll), freq, adj",
        "原始指标对象或列表",
        body_style="raw",
        source_evidence=f"{_JS}: T9 (~16850) — se.post(path, t) raw body, NOT {{params: t}}",
        cli_command="indicator smallgrass current",
        client_method="get_technical_index",
    ),
    "get_technical_index_history": EndpointSpec(
        "get_technical_index_history",
        "/stock/get_technical_index_history",
        "技术指标历史序列",
        "code, indicators, freq, adj, count, tradeDate",
        "原始指标历史对象或列表",
        body_style="raw",
        source_evidence=f"{_JS}: _r (~17450), K0 defaults (~13220) — raw body, count=200, freq-aware adj",
        cli_command="indicator smallgrass history",
        client_method="get_technical_index_history",
    ),
}


def resolve_group(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    if text in STOCK_GROUPS:
        return STOCK_GROUPS[text].value
    raise ApiSchemaError(f"Unknown stock group {value!r}. Known groups: {', '.join(sorted(STOCK_GROUPS))}")


def resolve_sort_id(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    key = SORT_V2_ALIASES.get(text, text)
    if key in SORT_V2_FIELDS:
        return SORT_V2_FIELDS[key].value
    raise ApiSchemaError(f"Unknown sort key {value!r}. Known sort keys: {', '.join(sorted(SORT_V2_FIELDS))}")


def resolve_rank_model(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    if text in RANK_MODELS:
        return RANK_MODELS[text].value
    raise ApiSchemaError(f"Unknown rank model {value!r}. Known models: {', '.join(sorted(RANK_MODELS))}")


def resolve_dynamic_index_type(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    if text in DYNAMIC_INDEX_TYPES:
        return DYNAMIC_INDEX_TYPES[text].value
    raise ApiSchemaError(f"Unknown index type {value!r}. Known types: {', '.join(sorted(DYNAMIC_INDEX_TYPES))}")


def resolve_sort_direction(value: int | str | bool) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    if text in SORT_DIRECTIONS:
        return SORT_DIRECTIONS[text].value
    raise ApiSchemaError(f"Unknown sort direction {value!r}. Known directions: {', '.join(sorted(SORT_DIRECTIONS))}")


def resolve_sort_target_type(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    if text in SORT_TARGET_TYPES:
        return SORT_TARGET_TYPES[text].value
    raise ApiSchemaError(f"Unknown sort target type {value!r}. Known types: {', '.join(sorted(SORT_TARGET_TYPES))}")


def resolve_indicator(value: str) -> str:
    """Validate that `value` is a backend-accepted indicator name."""
    if value in INDICATORS_BACKEND:
        return value
    if value in INDICATORS_FRONTEND_ONLY:
        raise ApiSchemaError(
            f"Indicator {value!r} is rendered locally by the frontend and is not accepted by the backend. "
            f"Backend-accepted indicators: {', '.join(sorted(INDICATORS_BACKEND))}"
        )
    raise ApiSchemaError(
        f"Unknown indicator {value!r}. Backend-accepted indicators: {', '.join(sorted(INDICATORS_BACKEND))}"
    )


def named_rows(values: dict[str, NamedValue]) -> list[dict[str, Any]]:
    return [item.as_row() for item in values.values()]
