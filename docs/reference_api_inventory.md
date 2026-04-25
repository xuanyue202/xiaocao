# Reference API Inventory

本文基于以下两个来源整理：

- `reference/index-f3118026.js` 中实际出现的 `/stock/...` 请求路径与部分返回映射逻辑
- `src/xiaocao/api/client.py` 当前已经封装的方法

目标不是“宣称官方文档”，而是把目前能从前端 bundle 和现有 Python 代码里观察到的接口信息收敛成一份更完整的清单，便于后续继续补封装、补类型、补文档。

## 结论摘要

- `reference/index-f3118026.js` 中一共出现了 `52` 个 `/stock/...` 端点。
- 当前 `XiaocaoClient` 已封装其中 `15` 个。
- 还有 `37` 个端点只在 reference bundle 中出现，尚未进入 Python 客户端。
- 已封装接口里，`用途` 和 `参数` 已经基本清楚；真正缺的是 `result` 内字段说明和“不同 shape 的兼容策略”。
- 参数层面的补充已单独整理到 `docs/api_parameter_catalog.md`，重点覆盖 `sort_v2` 的 `sortKey -> sortId`、`get_code_list_v2 groups`、`model`、`indexType` 等关键枚举。
- 未封装接口里，优先级最高的是：
  - 板块详情与板块 K 线：`/stock/xiao_cao_block_detail`、`/stock/xiao_cao_block_date_kline`
  - 环境增强数据：`/stock/xiao_cao_environment_minute_line`、`/stock/xiao_cao_environment_second_line_selection`
  - 指标类接口：`/stock/get_technical_index`、`/stock/get_technical_index_history`
  - 元数据/观察池类接口：`/stock/stock_info`、`/stock/get_stock_mark`、`/stock/add_stock_mark`、`/stock/del_stock_mark`

## 当前封装覆盖

| Python 方法 | 接口 | 用途 | 参数 | 预期返回 |
|---|---|---|---|---|
| `get_code_list_v2()` | `/stock/focus_xiao_cao_index/get_code_list_v2` | 拉股票池分组 | `groups`、`date`、`hpqbState`、`lpdxState` | 顶层 `result` 常见为对象，实际股票列表在 `result.data` |
| `get_xiao_cao_index_v2()` | `/stock/xiao_cao_index_v2` | 拉一批股票的小草指数/标签/方向归属 | `stockCodes`、`date`、`hpqbState`、`lpdxState` | `result` 多为 `code -> object` 映射；bundle 会转成列表并补 `stockId/stockCode/marketCode` |
| `sort_v2()` | `/stock/sort_v2` | 对给定股票集合按指标排序 | `queryType`、`sortId`、`sortType`、`type`、`hpqbState`、`lpdxState`、`stockIds` | `result` 直接返回排序结果列表或对象，前端基本透传 |
| `get_industry_block_rank()` | `/stock/xiao_cao_industry_block_rank` | 行业/方向排行 | `date`、`model` | `result` 多为列表；条目含 `blockCode`、`blockName`、`num`、`numChange`、`trendScore` 等 |
| `get_block_category_rank_v3()` | `/stock/xiao_cao_block_category_rank_v3` | 大类/分类排行 | `date`、`model` | `result` 可能是列表，也可能嵌在 `localCategoryRankList`、`globalCategoryRankList`、`data` |
| `get_block_score()` | `/stock/xiao_cao_block_score` | 板块强度评分 | `date` | `result` 在 bundle 中被当成列表消费，常见字段与板块分数、涨跌变化、跟踪状态有关 |
| `get_xiao_cao_dynamic_index()` | `/stock/xiao_cao_dynamic_index` | 动态方向指数 | `tradeDate`、`indexType` | `result` 可能是列表或对象；条目含 `categoryCode`、`blockCode`、`score`、`scoreChange` 等 |
| `get_trade_cal()` | `/stock/trade_cal` | 交易日历 | `exchange`、`isOpen`、`startDate`、`endDate` | 常见为列表；条目至少含 `calDate`、`isOpen` |
| `next_trade_cal()` | `/stock/next_trade_cal` | 下一交易日/下一个开市日 | `exchange`、`isOpen`、`startDate`、`endDate` | 既可能返回列表/对象，也可能直接返回 `YYYYMMDD` 字符串 |
| `get_code_by_xiao_cao_block()` | `/stock/get_code_by_xiao_cao_block` | 按方向/行业/分类/模式反查股票池 | `blockCodeList`、`industryBlockCodeList`、`categoryCodeList`、`exponentCodeList`、`excIndustryCodeList`、`patternCodeList`、`tradeDate`、`blockTypeList`、`stockIds`、`aiStockIds`、`blockIsAll` | `result` 形状待进一步实测，前端多用作“方向内选股” |
| `second_line()` | `/stock/second_line` | 股票/指数秒级分时 | `code` | `result` 多为列表；前端会映射为 OHLC、盘口五档、成交量额、时间戳等明细 |
| `second_line_detail_info()` | `/stock/second_line_detail_info` | 多代码分时详情摘要 | `codes` | `result` 多为对象映射；前端转成列表并补 `stockId/stockCode/marketCode` |
| `xiao_cao_environment_second_line_v2()` | `/stock/xiao_cao_environment_second_line_v2` | 小草环境分时 v2 | `code`、`date`、`codeType`、`isFoolMode` | `result` 多为列表；前端把市场代码补成 `XCHJZS`，并统一为时间序列 |
| `minute_line()` | `/stock/minute_line` | 分钟线 | `adj`、`freq`、`code` | `result` 多为列表；条目含 `tradeDate`、`tradeTime`、`open/high/low/close`、`vol`、`amt` |
| `date_kline()` | `/stock/date_kline` | 日/周/月等 K 线 | `count`、`code`、`freq`、`adj`、`codeType`、`paramTime` | `result` 多为列表；条目含 `tradeDate`、OHLC、`pctChangeRate`、`turnoverRate`、量额等 |
| `stock_call_auction()` | `/stock/stock_call_auction` | 个股集合竞价 | `code`、`tradeDate` | `result` 多为列表；前端会计算 `preClose`，并暴露竞价量额、未匹配量、涨跌幅等 |

## 已封装接口的返回字段补充

下面的字段不是“完整协议”，而是从 bundle 的消费逻辑里能稳定看出来的高频字段。

### `/stock/xiao_cao_index_v2`

前端会把 `result` 中每个对象转成统一股票对象，能观察到的字段包括：

- 标识类：`code`、`codeName`
- 行情类：`trade`、`pctChangeRate`
- 方向归属：`jsjlBlock`、`jssbBlock`、`cjsBlock`
- 小草评分/标签类：`xcjw`、`jssb`、`openPctChangeRate`、`entityPctChangeRate`、`endPctChangeRate`
- 盘口/模式标签类：`ddhb`、`dn`、`ln`、`dx`
- 排名因子类：
  - `xczpqb`、`xczpqbpmssfd`、`xczpqbpfbhdx`
  - `dzjzpqb`、`dzjzpqbpmssfd`、`dzjzpqbpfbhdx`
  - `xcpzqb`、`xcpzqbpmssfd`、`xcpzqbpfbhdx`
  - `dzjpzqb`、`dzjpzqbpmssfd`、`dzjpzqbpfbhdx`

结论：

- Python 侧目前只做了“对象映射转列表”，还没有把这些字段的语义系统化。
- 如果继续补封装，优先值得做的是把常用字段拆成 `TypedDict` 或 dataclass。

### `/stock/second_line`

前端把每一条分时数据映射成统一 K 线/分时点对象，已观察到字段：

- 标识：`code`、`codeName`
- 时间：`tradeDate`、`tradeTimestamp`
- 行情：`trade`、`open`、`high`、`low`、`close`、`preClose`
- 涨跌：`pctChange`、`pctChangeRate`
- 成交：`vol`、`amt`、`volIn`、`volOut`
- 盘口：`buyPrice1..5`、`buyVol1..5`、`sellPrice1..5`、`sellVol1..5`
- 扩展：`turnoverRatio`、`volRatio`、`peRate`、`tradeStatus`

结论：

- `client.py` 当前直接透传 `result`，对上层来说还不够友好。
- 如果要补行情模块，建议增加一个“标准化 quote line” 变换层。

### `/stock/second_line_detail_info`

前端会把对象映射改成列表，字段集中在“当前快照”：

- 标识：`code`、`codeName`
- 行情：`preClose`、`open`、`high`、`low`、`close`、`trade`
- 成交：`vol`、`amt`、`volIn`、`volOut`
- 时间：`tradeDate`、`tradeTimestamp`
- 可能还包含盘口、涨跌幅、状态类字段

### `/stock/stock_call_auction`

前端消费时至少使用了这些字段：

- `code`、`codeName`
- `tradeDate`、`tradeTimestamp`
- `trade`
- `pctChange`
- `pctChangeRate`
- `buyVol2`、`sellVol2`

并额外计算：

- `preClose = trade - pctChange`
- `unTradeVol` 一类的竞价未匹配量语义

### `/stock/date_kline` 与 `/stock/minute_line`

两类 K 线接口在 bundle 中被统一绘图，说明其结果至少共享下面这些字段：

- `code`
- `tradeDate`
- `tradeTime` 或可推导时间
- `open`、`high`、`low`、`close`
- `preClose`
- `pctChange`
- `pctChangeRate`
- `vol`
- `amt`
- `turnoverRate`

## Reference 中额外出现但尚未封装的端点

下面这些接口目前没有出现在 `src/xiaocao/api/client.py` 中。`参数` 与 `返回` 使用三档置信度标记：

- `高`：bundle 中能直接看到参数或明显的字段映射
- `中`：能从函数名和局部逻辑推断主要语义
- `低`：只能确认端点存在

### 1. 股票元数据与自选标记

| 接口 | 用途推断 | 观察到的参数 | 预期返回 | 置信度 |
|---|---|---|---|---|
| `/stock/stock_info` | 全量股票基础信息、状态、板块类型 | 无参数或空对象 | 列表，包含 `code`、`name`、`statusType`、`blockType` 等 | 高 |
| `/stock/get_stock_mark` | 查询股票标记 | 代码列表或过滤条件，bundle 未完全展开 | 标记列表/映射 | 中 |
| `/stock/add_stock_mark` | 新增股票标记 | 标记内容、目标股票 | 操作结果 | 中 |
| `/stock/del_stock_mark` | 删除股票标记 | 标记 id 或股票标识 | 操作结果 | 中 |
| `/stock/get_industry_stock_group` | 查询行业分组下股票 | 行业/分组条件 | 股票列表 | 中 |
| `/stock/block_category_info` | 查询板块分类信息 | 分类代码或日期 | 分类详情 | 中 |

### 2. 行情与 K 线增强

| 接口 | 用途推断 | 观察到的参数 | 预期返回 | 置信度 |
|---|---|---|---|---|
| `/stock/block_second_line` | 板块级分时 | 板块代码、日期或代码列表 | 分时列表 | 中 |
| `/stock/minute_kline` | 分钟级 K 线，可能是另一套绘图口径 | `code`、`freq`、`adj` 一类 | K 线列表 | 中 |
| `/stock/xiao_cao_block_date_kline` | 小草板块日线 | `code`、`adj`、`codeType` | 板块 K 线列表 | 高 |
| `/stock/xiao_cao_environment_date_kline` | 小草环境日线 | `code`、`adj`、`codeType` | 环境 K 线列表 | 高 |
| `/stock/xiao_cao_environment_minute_kline` | 小草环境分钟线 | `code`、`adj`、`codeType` | 环境分钟 K 线 | 高 |
| `/stock/xiao_cao_environment_minute_line` | 小草环境分钟分时 | `code`、`tradeDate`、可能带 `codeType` | 分钟分时列表 | 高 |
| `/stock/get_minute_index` | 指标分时索引或分钟指标 | 条件未知 | 指标列表 | 低 |
| `/stock/getYkDetail` | 盈亏详情 | 条件未知 | 盈亏明细 | 低 |
| `/stock/each_trade` | 逐笔成交/单笔交易 | 代码、日期、分页类参数 | 逐笔列表 | 中 |

### 3. 板块、环境与市场强度

| 接口 | 用途推断 | 观察到的参数 | 预期返回 | 置信度 |
|---|---|---|---|---|
| `/stock/xiao_cao_block_detail` | 单个板块详情 | `code`、`tradeDate` | 详情对象，含 `shortLineScore`、`trendScore`、`blockType` 等 | 高 |
| `/stock/xiao_cao_block_score_admin` | 管理视图板块评分 | `date` | 列表，字段比普通 block_score 更全 | 高 |
| `/stock/xiao_cao_block_score_admin_next` | 下一日/下一批 admin 评分 | 鉴权请求 | 列表 | 中 |
| `/stock/xiao_cao_industry_block_dynamic_index` | 行业动态指数 | `tradeDate`、`indexType` | 动态指数列表 | 高 |
| `/stock/xiao_cao_emotions_height` | 情绪高度曲线 | `bkCode`、`count=240` | 时序列表，含 `maxLimitUpDays`、`resLimitUpDays` 等 | 高 |
| `/stock/market_overview` | 市场概览 | 日期或窗口参数 | 市场总览对象 | 中 |
| `/stock/get_environment_by_custom` | 自定义环境组合查询 | 自定义代码/配置 | 环境结果 | 中 |
| `/stock/xiao_cao_environment_second_line_selection` | 环境分时精选集合 | `date` | 分时列表，前端会补 `XCHJZS` 市场后缀 | 高 |
| `/stock/xiao_cao_environment_second_line_next` | 下一期环境分时 | 鉴权请求 | 环境列表 | 中 |
| `/stock/xiao_cao_environment_second_line_toal` | 环境分时 total 口径，疑似 total 拼写错误 | `date`、`codeType` 等 | 环境列表 | 高 |
| `/stock/xiao_cao_week_stats` | 周统计 | 无参数 | 周度股票/策略统计列表 | 高 |

### 4. 技术指标与扩展分析

| 接口 | 用途推断 | 观察到的参数 | 预期返回 | 置信度 |
|---|---|---|---|---|
| `/stock/get_technical_index` | 单次技术指标计算 | 股票代码、周期、指标名一类 | 指标对象 | 中 |
| `/stock/get_technical_index_history` | 技术指标历史序列 | 股票代码、时间范围、指标名 | 指标时序 | 中 |
| `/stock/code_excra_total` | extra/excra 聚合统计 | 条件未知 | 聚合对象 | 低 |
| `/stock/excra_info` | extra/excra 详情 | 条件未知 | 详情对象 | 低 |
| `/stock/excra_branch_list` | extra/excra 分支列表 | 条件未知 | 列表 | 低 |
| `/stock/excra_branch_info` | extra/excra 分支详情 | 条件未知 | 详情对象 | 低 |

### 5. ETF、直播与系统辅助

| 接口 | 用途推断 | 观察到的参数 | 预期返回 | 置信度 |
|---|---|---|---|---|
| `/stock/etf_info` | ETF 信息 | ETF 代码或筛选条件 | ETF 列表/详情 | 中 |
| `/stock/get_xet_live_list` | 直播/事件流列表 | 分页条件 | 列表 | 中 |
| `/stock/sync_xet_live_list` | 同步直播列表 | 无参数 | 成功布尔值或同步结果 | 高 |
| `/stock/get_system_time` | 服务端系统时间 | 无参数 | 时间对象/字符串 | 中 |

## 覆盖差集

reference bundle 中出现、但当前 Python 尚未封装的端点如下：

```text
/stock/add_stock_mark
/stock/block_category_info
/stock/block_second_line
/stock/code_excra_total
/stock/del_stock_mark
/stock/each_trade
/stock/etf_info
/stock/excra_branch_info
/stock/excra_branch_list
/stock/excra_info
/stock/getYkDetail
/stock/get_environment_by_custom
/stock/get_industry_stock_group
/stock/get_minute_index
/stock/get_stock_mark
/stock/get_system_time
/stock/get_technical_index
/stock/get_technical_index_history
/stock/get_xet_live_list
/stock/market_overview
/stock/minute_kline
/stock/stock_info
/stock/sync_xet_live_list
/stock/xiao_cao_block_date_kline
/stock/xiao_cao_block_detail
/stock/xiao_cao_block_score_admin
/stock/xiao_cao_block_score_admin_next
/stock/xiao_cao_emotions_height
/stock/xiao_cao_environment_date_kline
/stock/xiao_cao_environment_minute_kline
/stock/xiao_cao_environment_minute_line
/stock/xiao_cao_environment_second_line_next
/stock/xiao_cao_environment_second_line_selection
/stock/xiao_cao_environment_second_line_toal
/stock/xiao_cao_industry_block_dynamic_index
/stock/xiao_cao_week_stats
```

## 建议的下一步封装顺序

如果目标是优先提升 CLI 的实用性，建议按下面顺序补：

1. 板块/环境行情链路
   - `/stock/xiao_cao_block_detail`
   - `/stock/xiao_cao_block_date_kline`
   - `/stock/xiao_cao_environment_minute_line`
   - `/stock/xiao_cao_environment_second_line_selection`

2. 指标与分析链路
   - `/stock/get_technical_index`
   - `/stock/get_technical_index_history`
   - `/stock/xiao_cao_industry_block_dynamic_index`
   - `/stock/xiao_cao_emotions_height`

3. 元数据与人工工作流
   - `/stock/stock_info`
   - `/stock/get_stock_mark`
   - `/stock/add_stock_mark`
   - `/stock/del_stock_mark`

## 还缺什么

这份清单已经比 `client.py` 当前注释更完整，但还不是最终版。仍然缺：

- 各接口空结果时的精确 shape
- 各枚举参数的官方或准官方含义
- 鉴权接口在无 token 场景下的错误结构
- `xiao_cao_index_v2`、`sort_v2` 的字段枚举说明
- `excra_*` 与 `xet_live_*` 这两组接口的真实业务语义

更进一步时，建议结合一次真实抓包或对 bundle 里的调用函数做拆分反混淆，再补一版字段级协议说明。
