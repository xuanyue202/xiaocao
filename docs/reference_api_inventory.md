# Reference API Inventory

> Auto-generated from `src/xiaocao/api/catalog.py` by `scripts/render_inventory.py`.
> Do not hand-edit. Update `EndpointSpec` entries and rerun the script.

`xiaocao` 的端点目录由 `src/xiaocao/api/catalog.py` 里的 `ENDPOINTS` 字典维护。
每个 `EndpointSpec` 同时记录了 client 方法、CLI 命令、请求体形态、稳定度，
以及在 `reference/index-f3118026.js` 里的取证位置。下表按稳定度分组渲染。

字段含义：

- **endpoint**: 后端路径
- **client method**: `XiaocaoClient` 上的方法名
- **CLI**: 推荐的业务命令路径
- **body**: `params` 表示前端走 `{"params": ...}` 包装；`raw` 表示直接 POST 顶层对象
- **base**: `XC` 主域 / `PZ` 备域（当前所有端点都是 XC）
- **auth**: 是否需要鉴权
- **status**: `stable` / `experimental` / `planned`
- **source**: JS bundle 里取证的位置或函数名


## stable — 已封装且 live 验证可用

| endpoint | client method | CLI | body | base | auth | status | source |
|---|---|---|---|---|---|---|---|
| `date_kline` | `date_kline` | `quote history` | params | XC | yes | stable | reference/index-f3118026.js: date_kline wrapper, freq enum (~5728) |
| `each_trade` | `each_trade` | `market each-trade` | params | XC | yes | stable | reference/index-f3118026.js: each_trade wrapper |
| `etf_info` | `etf_info` | `market etf-info` | params | XC | yes | stable | reference/index-f3118026.js: etf_info wrapper (~23387), daily cache (~23433) |
| `get_code_by_xiao_cao_block` | `get_code_by_xiao_cao_block` | `block stocks` | params | XC | yes | stable | reference/index-f3118026.js: get_code_by_xiao_cao_block wrapper |
| `get_code_list_v2` | `get_code_list_v2` | `data pool` | params | XC | yes | stable | reference/index-f3118026.js: focus_xiao_cao_index pool fetch |
| `get_technical_index` | `get_technical_index` | `indicator smallgrass current` | raw | XC | yes | stable | reference/index-f3118026.js: T9 (~16850) — se.post(path, t) raw body, NOT {params: t} |
| `get_technical_index_history` | `get_technical_index_history` | `indicator smallgrass history` | raw | XC | yes | stable | reference/index-f3118026.js: _r (~17450), K0 defaults (~13220) — raw body, count=200, freq-aware adj |
| `market_overview` | `market_overview` | `market overview` | params | XC | yes | stable | reference/index-f3118026.js: market_overview wrapper |
| `minute_line` | `minute_line` | `quote minute` | params | XC | yes | stable | reference/index-f3118026.js: minute_line wrapper |
| `next_trade_cal` | `next_trade_cal` | `calendar next` | params | XC | yes | stable | reference/index-f3118026.js: next_trade_cal wrapper |
| `second_line` | `second_line` | `market second-line` | params | XC | yes | stable | reference/index-f3118026.js: second_line wrapper |
| `second_line_detail_info` | `second_line_detail_info` | `market second-line-detail` | params | XC | yes | stable | reference/index-f3118026.js: second_line_detail_info wrapper |
| `sort_v2` | `sort_v2` | `data sort` | params | XC | yes | stable | reference/index-f3118026.js: sort wrapper using sortId enum |
| `stock_call_auction` | `stock_call_auction` | `quote auction` | params | XC | yes | stable | reference/index-f3118026.js: stock_call_auction wrapper |
| `stock_info` | `stock_info` | `market stock-info` | params | XC | yes | stable | reference/index-f3118026.js: stock_info wrapper |
| `trade_cal` | `get_trade_cal` | `calendar trade-days` | params | XC | yes | stable | reference/index-f3118026.js: trade_cal wrapper |
| `xiao_cao_block_category_rank_v3` | `get_block_category_rank_v3` | `block category-rank` | params | XC | yes | stable | reference/index-f3118026.js: block category rank v3 wrapper |
| `xiao_cao_block_date_kline` | `xiao_cao_block_date_kline` | `block kline` | params | XC | yes | stable | reference/index-f3118026.js: block date_kline wrapper |
| `xiao_cao_block_detail` | `xiao_cao_block_detail` | `block detail` | params | XC | yes | stable | reference/index-f3118026.js: block detail wrapper |
| `xiao_cao_block_score` | `get_block_score` | `block score` | params | XC | yes | stable | reference/index-f3118026.js: block score wrapper |
| `xiao_cao_dynamic_index` | `get_xiao_cao_dynamic_index` | `index dynamic` | params | XC | yes | stable | reference/index-f3118026.js: dynamic index wrapper (jinglong branch) |
| `xiao_cao_environment_minute_line` | `xiao_cao_environment_minute_line` | `market env-minute` | params | XC | yes | stable | reference/index-f3118026.js: environment minute_line wrapper |
| `xiao_cao_environment_second_line_selection` | `xiao_cao_environment_second_line_selection` | `market env-selection` | params | XC | yes | stable | reference/index-f3118026.js: environment second_line selection wrapper |
| `xiao_cao_environment_second_line_v2` | `xiao_cao_environment_second_line_v2` | `market environment` | params | XC | yes | stable | reference/index-f3118026.js: environment second_line v2 wrapper |
| `xiao_cao_index_v2` | `get_xiao_cao_index_v2` | `index stock` | params | XC | yes | stable | reference/index-f3118026.js: xiao_cao_index_v2 batch wrapper |
| `xiao_cao_industry_block_dynamic_index` | `get_xiao_cao_industry_block_dynamic_index` | `index industry-dynamic` | params | XC | yes | stable | reference/index-f3118026.js: industry dynamic index wrapper |
| `xiao_cao_industry_block_rank` | `get_industry_block_rank` | `block rank` | params | XC | yes | stable | reference/index-f3118026.js: industry block rank wrapper |
| `xiao_cao_week_stats` | `xiao_cao_week_stats` | `market week-stats` | params | XC | yes | stable | reference/index-f3118026.js: week_stats wrapper |

## experimental — 已封装但 live 不稳定或未验证

_(none)_

## planned — JS 中存在，尚未在 client 落地

_(none)_

## Purpose / params / returns reference

| endpoint | purpose | params | returns |
|---|---|---|---|
| `date_kline` | 股票日/周/月等 K 线 | count, code, freq, adj, codeType, paramTime | K 线列表，含 OHLC、涨跌幅、换手率、量额等 |
| `each_trade` | 逐笔成交 | code, count, codeType, isLess 等 | 逐笔列表，前端映射 trade/oneVol/oneAmt/bsFlag/time |
| `etf_info` | ETF 目录与交易日元数据 | tradeDate | ETF 目录列表；client 保留原始字段及 trade-date provenance |
| `get_code_by_xiao_cao_block` | 按方向/行业/分类/模式反查股票池 | blockCodeList, industryBlockCodeList, categoryCodeList, patternCodeList, tradeDate 等 | 股票代码列表、嵌套列表或对象，datasource 会抽取代码 |
| `get_code_list_v2` | 按小草模式拉股票池 | groups, date, hpqbState, lpdxState | result.data 或 result 列表中的股票代码 |
| `get_technical_index` | 技术指标当前值/分时指标 | code, indicators (smallGrass\|vol\|amt\|macd\|rsi\|kdj\|boll), freq, adj | 原始指标对象或列表 |
| `get_technical_index_history` | 技术指标历史序列 | code, indicators, freq, adj, count, tradeDate | 原始指标历史对象或列表 |
| `market_overview` | 市场概览 | 空对象 | 市场总览对象 |
| `minute_line` | 股票分钟线 | adj, freq, code | 分钟 K/分时列表，含 tradeDate/tradeTime/OHLC/vol/amt |
| `next_trade_cal` | 下一交易日/下一个开市日 | exchange, isOpen, startDate, endDate | 列表、对象或 YYYYMMDD 字符串，client 会兼容归一 |
| `second_line` | 股票/指数秒级分时 | code | 分时线列表，含 OHLC、盘口、成交、时间戳等 |
| `second_line_detail_info` | 多代码分时详情摘要 | codes | 当前快照映射或列表，含行情、成交、时间和盘口字段 |
| `sort_v2` | 对给定股票或板块集合按前端 sortKey/sortId 排序 | queryType, sortId/sortKey, sortType, type, date, hpqbState, lpdxState, stockIds | 排序后的 code/stockId 列表或对象列表，前端会按原始 stockIds 再过滤 |
| `stock_call_auction` | 个股集合竞价 | code, tradeDate | 集合竞价列表，含 trade/pctChange/buyVol2/sellVol2 等 |
| `stock_info` | 全量股票/板块基础信息 | 无参数或空对象 | 列表，含 code/codeName/statusType/blockType/la 等 |
| `trade_cal` | 交易日历 | exchange, isOpen, startDate, endDate | 交易日列表，常见字段 calDate/isOpen |
| `xiao_cao_block_category_rank_v3` | 方向大类/分类排行 | date, model/full\|focus\|full_alias_2\|full_alias_3 | 分类排行列表或 localCategoryRankList/globalCategoryRankList/data |
| `xiao_cao_block_date_kline` | 小草板块日/周/月 K 线 | count, code, freq, adj, codeType, paramTime | 标准化 K 线列表 |
| `xiao_cao_block_detail` | 单个板块详情 | code, tradeDate | 详情对象，含 shortLineScore/trendScore/blockType/position/rank/blockScoreList |
| `xiao_cao_block_score` | 板块强度评分 | date | 板块评分列表或对象，含强度、涨跌变化、跟踪状态等 |
| `xiao_cao_dynamic_index` | 动态方向指数 | tradeDate, indexType/jinglong\|default | 动态指数列表，含 categoryCode/blockCode/score/scoreChange 等 |
| `xiao_cao_environment_minute_line` | 小草环境分钟分时 | code, tradeDate, adj, freq | 标准化 1min 分时列表 |
| `xiao_cao_environment_second_line_selection` | 小草环境分时精选集合 | date | 环境精选快照列表 |
| `xiao_cao_environment_second_line_v2` | 小草环境分时 v2 | code, date, codeType, isFoolMode | 环境分时时序列表 |
| `xiao_cao_index_v2` | 批量获取股票小草指数、模式分、方向归属和行情字段 | stockCodes, date, hpqbState, lpdxState | code -> object 映射或列表，client 会转成列表并补 code |
| `xiao_cao_industry_block_dynamic_index` | 行业动态指数 | tradeDate, indexType/jinglong\|default | 行业动态指数列表 |
| `xiao_cao_industry_block_rank` | 行业/方向强度排行 | date, model/full\|focus\|full_alias_2\|full_alias_3 | 方向排行列表，含 blockCode/blockName/num/trendScore 等 |
| `xiao_cao_week_stats` | 小草模式周统计 | 空 params | jsjl/xcjw/jssb/cjs 四组周状态列表 |
