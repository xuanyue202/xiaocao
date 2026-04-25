# Xiaocao CLI 产品与技术设计文档

## 1. 背景与目标

当前 `xiaocao` 项目是一个围绕“小草指数 / 板块方向 / 个股模式”的 Python 脚本集合，主要功能包括：

- 从小草相关 API 获取股票池、个股指标、板块方向、动态指数、环境数据
- 将历史数据保存为 CSV / JSON
- 基于固定规则筛选接力、低吸、断板、方向加持等模式
- 输出每日推荐结果 CSV

随着接口升级、功能扩展和日常使用需求增加，当前脚本式结构已经不适合长期维护。新的目标是将项目重构为一个可维护、可扩展、可自动化调用的 CLI 工具。

设计目标：

1. 修复和升级现有功能
2. 统一 CLI 命令、参数、输出和错误处理
3. 支持更多模式、数据源和输出格式
4. 适配新版 API
5. 为后续报告生成、定时任务和 Agent 调用打基础

---

## 2. 当前项目功能与问题梳理

### 2.1 当前文件职责

| 文件 | 当前职责 | 建议 |
|---|---|---|
| `xiaocao_api.py` | 旧版线上 API 封装 | 重构为新版 API client |
| `xiaocao_file.py` | 从本地 CSV / JSON 读取历史数据 | 保留，改造成 LocalDataSource |
| `stock_recommend.py` | 核心选股策略 | 保留业务逻辑，拆成 strategy 模块 |
| `today_gogogo.py` | 当日自动运行入口 | 废弃为脚本入口，迁移为 CLI 命令 |
| `stock_details.py` | 批量拉取个股详情 | 改造成 `xiaocao data fetch-details` |
| `stock_industry_block.py` | 批量拉取行业板块排名 | 改造成 CLI 子命令 |
| `stock_block_category_v2.py` | 拉取板块分类排名 | 升级到 v3 |
| `stock_dynamic_index.py` | 拉取动态指数 | 保留并封装 |
| `stock_env.py` | 拉取环境分时数据 | 升级到环境分时 v2 |
| `*_process.py` | JSON 展平处理 | 改造成 transform 模块 |
| `stocks.json` | 股票代码列表 | 保留为本地数据资产，可由 API 更新 |

### 2.2 当前主要问题

1. **接口失效**
   - `/stock/sort` 已返回 404
   - `/stock/xiao_cao_index` 已返回 404
   - `/stock/xiao_cao_block_category_rank_v2` 已返回 404
   - `/stock/focus_xiao_cao_index/get_code_list` 旧接口已不可直接使用

2. **接口封装耦合业务**
   - API 请求、重试、字段处理和策略逻辑混杂
   - 不利于切换数据源或升级接口

3. **策略规则硬编码**
   - 模式规则写死在 `stock_recommend.py`
   - 后续新增模式需要改代码
   - 表格里的部分模式未完整实现

4. **输出格式单一**
   - 当前主要输出 CSV
   - 不支持 table、json、markdown、报告等格式

5. **缺少 CLI 规范**
   - 无统一命令入口
   - 无统一日期参数
   - 无统一日志、错误码、配置文件

6. **历史数据与实时数据边界不清**
   - 有在线 API，也有本地 CSV 数据源
   - 但调用方式靠手动切换模块，不够清晰

---

## 3. 新版 API 总览

### 3.1 API 域名

新版接口主要使用：

```text
https://p-xcapi.kjap1.cn
```

部分 v2 接口在旧域名也可用：

```text
https://p-xcapi.topxlc.com
```

建议统一配置为：

```yaml
api:
  base_url: https://p-xcapi.kjap1.cn
```

---

## 4. API 适配文档

### 4.1 小草指数 v2

```text
POST /stock/xiao_cao_index_v2
```

用途：

获取一批股票在指定日期的小草指数、竞王、低吸、红盘、接力、形态标签、板块归属等综合指标。

可能替代旧接口：

```text
/stock/xiao_cao_index
```

推测依据：

- 路径增加 `_v2`
- 请求参数仍包含 `stockCodes` 和 `date`
- 新增 `hpqbState`、`lpdxState`
- 旧接口已 404

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `stockCodes` | string | 股票代码列表，逗号分隔 |
| `date` | string | 交易日期，格式 `YYYY-MM-DD` |
| `hpqbState` | number | 红盘起爆相关过滤状态，业务含义待确认 |
| `lpdxState` | number | 绿盘低吸相关过滤状态，业务含义待确认 |

返回结构：

返回结构待补充。

建议封装方法：

```python
get_xiao_cao_index_v2(date, stock_codes, hpqb_state=0, lpdx_state=0)
```

---

### 4.2 小草动态指数

```text
POST /stock/xiao_cao_dynamic_index
```

用途：

获取小草动态指数数据，可能包含板块大类、板块、指数分数、变化值、跟踪状态等。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `tradeDate` | string | 交易日期，格式 `YYYY-MM-DD` |
| `indexType` | number | 指数类型，枚举含义待确认 |

返回字段旧代码中已观察到：

| 字段 | 含义 |
|---|---|
| `categoryCode` | 板块大类代码 |
| `blockCode` | 板块代码 |
| `score` | 指数分数 |
| `scoreChangePre` | 相对前值变化 |
| `scoreChange` | 分数变化 |
| `dataType` | 数据类型 |
| `isTrack` | 是否跟踪 |
| `isPpp` | 业务标记，含义待确认 |
| `industryType` | 行业类型 |

---

### 4.3 小草行业板块排名

```text
POST /stock/xiao_cao_industry_block_rank
```

用途：

获取指定日期的行业 / 题材方向排名。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `date` | string | 日期，格式 `YYYY-MM-DD` |
| `model` | number | 排名模型，枚举含义待确认 |

已知返回字段：

| 字段 | 含义 |
|---|---|
| `tradeDate` | 交易日期 |
| `blockCode` | 板块代码 |
| `blockName` | 板块名称 |
| `dataType` | 数据类型 |
| `industryType` | 行业类型 |
| `num` | 排名分数 / 强度值 |
| `directionNum` | 方向数量，含义待确认 |
| `numChange` | 强度变化 |
| `prePctChangeRate` | 前一阶段涨跌幅 |
| `isTrack` | 是否跟踪 |
| `isPpp` | 业务标记 |
| `trendScore` | 趋势分，旧接口新增字段 |

---

### 4.4 小草板块评分

```text
POST /stock/xiao_cao_block_score
```

用途：

获取指定日期的小草板块评分。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `date` | string | 日期，格式 `YYYY-MM-DD` |

返回结构：

返回结构待补充。

可能用途：

- 替代或补充行业板块排名
- 用于方向强度、板块筛选、方向加持评分

---

### 4.5 下一交易日历

```text
POST /stock/next_trade_cal
```

用途：

获取指定交易所和日期范围内的下一个交易日信息。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `exchange` | string | 交易所，例如 `SSE` |
| `isOpen` | number | 是否开市，通常 `1` 表示交易日 |
| `startDate` | string | 开始日期，格式 `YYYYMMDD` |
| `endDate` | string | 结束日期，格式 `YYYYMMDD` |

建议用途：

- CLI 默认日期推断
- 周末 / 节假日自动回退到最近交易日
- 定时任务判断是否执行

---

### 4.6 小草板块分类排名 v3

```text
POST /stock/xiao_cao_block_category_rank_v3
```

用途：

获取板块分类排名，替代旧版 v2。

替代旧接口：

```text
/stock/xiao_cao_block_category_rank_v2
```

推测依据：

- 路径升级为 `_v3`
- 旧 v2 接口已 404
- 请求参数仍然为 `date` 和 `model`

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `date` | string | 日期，格式 `YYYY-MM-DD` |
| `model` | number | 模型类型，枚举含义待确认 |

返回结构：

返回结构待补充。

---

### 4.7 排序接口 v2

```text
POST /stock/sort_v2
```

用途：

对指定股票集合按某种指标排序。

替代旧接口：

```text
/stock/sort
```

推测依据：

- 路径升级为 `_v2`
- 旧接口已 404
- 请求参数保留 `queryType`、`sortId`、`sortType`、`type`
- 新增 `stockIds`、`hpqbState`、`lpdxState`

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `queryType` | number | 查询类型，枚举待确认 |
| `sortId` | number | 排序字段 ID，枚举待确认 |
| `sortType` | number | 排序方向，可能 `1` 为降序，待确认 |
| `type` | number | 股票范围 / 类型，枚举待确认 |
| `hpqbState` | number | 红盘起爆过滤状态，待确认 |
| `lpdxState` | number | 绿盘低吸过滤状态，待确认 |
| `stockIds` | list[string] | 待排序股票代码列表 |

建议用途：

- 替代当前 `get_sorted_code_list`
- 支持在指定股票池内排序
- 支持低吸排名、竞王排名、红盘起爆排名

---

### 4.8 秒级 / 分时线数据

```text
POST /stock/second_line
```

用途：

获取指数或股票的秒级 / 分时线数据。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `code` | string | 股票或指数代码，多个用逗号分隔 |

返回结构：

返回结构待补充。

---

### 4.9 秒级 / 分时线详情信息

```text
POST /stock/second_line_detail_info
```

用途：

获取多个指数 / 板块 / 股票的分时详情信息。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `codes` | string | 多个代码，逗号分隔 |

返回结构：

返回结构待补充。

可能关系：

- `/second_line` 偏时间序列
- `/second_line_detail_info` 偏当前详情 / 汇总信息

---

### 4.10 分钟线数据

```text
POST /stock/minute_line
```

用途：

获取股票分钟 K 线。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `adj` | string | 复权方式，例如 `bfq` 不复权 |
| `freq` | string | 周期，例如 `1min` |
| `code` | string | 股票代码 |

返回结构：

返回结构待补充。

---

### 4.11 日 K 线数据

```text
POST /stock/date_kline
```

用途：

获取股票日 K 线。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `count` | number | 返回 K 线数量 |
| `code` | string | 股票代码 |
| `freq` | string | 周期，例如 `D` |
| `adj` | string | 复权方式，例如 `qfq` 前复权 |
| `codeType` | string | 代码类型，枚举待确认 |
| `paramTime` | string | 查询时间参数，空字符串表示默认 |

返回结构：

返回结构待补充。

---

### 4.12 小草环境秒级 / 分时线 v2

```text
POST /stock/xiao_cao_environment_second_line_v2
```

用途：

获取小草环境分时线数据。

替代旧接口：

```text
/stock/xiao_cao_environment_second_line
```

推测依据：

- 路径升级为 `_v2`
- 代码列表从 7 个扩展到 12 个
- 新增 `codeType`、`isFoolMode`

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `code` | string | 环境指标代码列表 |
| `date` | string | 日期，格式 `YYYY-MM-DD` |
| `codeType` | number | 代码类型，枚举待确认 |
| `isFoolMode` | number | 简化模式 / 傻瓜模式，业务含义待确认 |

---

### 4.13 交易日历

```text
POST /stock/trade_cal
```

用途：

获取交易日历。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `exchange` | string | 交易所，例如 `SSE` |
| `isOpen` | number | 是否开市 |
| `startDate` | string | 开始日期，格式 `YYYYMMDD` |
| `endDate` | string | 结束日期，格式 `YYYYMMDD` |

建议用途：

- 判断是否交易日
- 自动选择最近交易日
- 补全历史任务日期列表

---

### 4.14 根据小草板块获取股票代码

```text
POST /stock/get_code_by_xiao_cao_block
```

用途：

根据板块、行业、分类、指数、模式等条件获取股票代码集合。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `blockCodeList` | string | 小草板块代码列表 |
| `industryBlockCodeList` | string | 行业板块代码列表 |
| `categoryCodeList` | string | 板块分类代码列表 |
| `exponentCodeList` | string | 指数代码列表 |
| `excIndustryCodeList` | string | 排除行业代码列表 |
| `patternCodeList` | string | 模式代码列表 |
| `tradeDate` | string | 交易日期，格式 `YYYY-MM-DD` |
| `blockTypeList` | string | 板块类型列表 |
| `stockIds` | string | 指定股票范围 |
| `aiStockIds` | string | AI 股票池范围，业务含义待确认 |
| `blockIsAll` | number | 板块条件是否全匹配，业务含义待确认 |

建议用途：

- 方向内选股
- 板块内股票池构建
- 支持模式表里的“方向低位低吸”
- 支持更复杂的组合过滤

---

### 4.15 个股集合竞价数据

```text
POST /stock/stock_call_auction
```

用途：

获取个股集合竞价数据。

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `code` | string | 股票代码 |
| `tradeDate` | string | 交易日期，格式 `YYYYMMDD` |

返回结构：

返回结构待补充。

建议用途：

- 接力模式开盘竞价判断
- 高开幅度、竞价强度、竞价成交量等扩展指标

---

### 4.16 股票池接口 v2

```text
POST /stock/focus_xiao_cao_index/get_code_list_v2
```

用途：

获取不同分组的股票池。

替代旧接口：

```text
/stock/focus_xiao_cao_index/get_code_list
```

已实测：

- `groups=0`：接力
- `groups=1`：竞王
- `groups=2`：红盘 / 起爆
- `groups=3`：低吸

请求参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `groups` | string | 股票池分组 |
| `date` | string | 日期，格式 `YYYY-MM-DD` |
| `hpqbState` | number | 红盘起爆过滤状态，待确认 |
| `lpdxState` | number | 绿盘低吸过滤状态，待确认 |

已知返回结构：

```json
{
  "code": 8200,
  "result": {
    "visibility": 1,
    "data": ["688807.XSHG"]
  }
}
```

## curl samples

## API Curl Samples:
### 1. 小草指数 v2

```bash

curl 'https://p-xcapi.kjap1.cn/stock/xiao_cao_index_v2' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"stockCodes":"688808.XSHG,300422.XSHE,300283.XSHE,300613.XSHE,688633.XSHG,688268.XSHG,301077.XSHE,300721.XSHE,300489.XSHE,688141.XSHG,688807.XSHG,300390.XSHE,688347.XSHG,301003.XSHE,300434.XSHE,301307.XSHE,300965.XSHE,688101.XSHG,000889.XSHE,600726.XSHG,002795.XSHE,600537.XSHG,002999.XSHE,603318.XSHG,000925.XSHE,002313.XSHE,002406.XSHE,301510.XSHE,688629.XSHG,603680.XSHG,000906.XSHE,300057.XSHE,600826.XSHG,603390.XSHG,600152.XSHG,603520.XSHG,000973.XSHE,002176.XSHE,002290.XSHE,603365.XSHG,002812.XSHE,002810.XSHE,603016.XSHG,603937.XSHG","date":"2026-04-24","hpqbState":0,"lpdxState":0}}'

```

### 2. 小草动态指数

```bash

curl 'https://p-xcapi.kjap1.cn/stock/xiao_cao_dynamic_index' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"tradeDate":"2026-04-24","indexType":0}}'

```

### 3. 小草行业板块排名

```bash

curl 'https://p-xcapi.kjap1.cn/stock/xiao_cao_industry_block_rank' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"date":"2026-04-24","model":1}}'

```

### 4. 小草板块评分

```bash

curl 'https://p-xcapi.kjap1.cn/stock/xiao_cao_block_score' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"date":"2026-04-24"}}'

```

### 5. 下一交易日历

```bash

curl 'https://p-xcapi.kjap1.cn/stock/next_trade_cal' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"exchange":"SSE","isOpen":1,"startDate":"20240903","endDate":"20260425"}}'

```

### 6. 小草板块分类排名 v3

```bash

curl 'https://p-xcapi.kjap1.cn/stock/xiao_cao_block_category_rank_v3' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"date":"2026-04-24","model":0}}'

```

### 7. 排序接口 v2

```bash

curl 'https://p-xcapi.kjap1.cn/stock/sort_v2' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"queryType":1,"sortId":8,"sortType":1,"type":0,"hpqbState":0,"lpdxState":0,"stockIds":["000001.XSHG","000002.XSHG","000003.XSHG","...","899601.BJSE"]}}'

```

说明：`sort_v2` 的 `stockIds` 原始列表较长，报告分析时重点分析参数结构即可，不需要逐个解释所有股票代码。

### 8. 秒级 / 分时线数据

```bash

curl 'https://p-xcapi.kjap1.cn/stock/second_line' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"code":"000001.XSHG,399001.XSHE,399006.XSHE"}}'

```

### 9. 秒级 / 分时线详情信息

```bash

curl 'https://p-xcapi.kjap1.cn/stock/second_line_detail_info' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"codes":"399704.XSHE,399638.XSHE,399669.XSHE,399310.XSHE,399377.XSHE,399703.XSHE,399385.XSHE,000993.XSHG,399324.XSHE,000148.XSHG,399276.XSHE,399688.XSHE,000112.XSHG,399368.XSHE,000991.XSHG,000138.XSHG,000146.XSHG,399617.XSHE,000856.XSHG,000102.XSHG,399852.XSHE,000852.XSHG,399354.XSHE,000814.XSHG,399344.XSHE,399550.XSHE,399905.XSHE,000905.XSHG,399373.XSHE,399394.XSHE,399399.XSHE,000802.XSHG,399552.XSHE,399360.XSHE,399813.XSHE,399701.XSHE,000933.XSHG,399933.XSHE,000051.XSHG,399403.XSHE,399379.XSHE,399645.XSHE,000145.XSHG,000115.XSHG,399362.XSHE,399103.XSHE,399005.XSHE,000067.XSHG,399750.XSHE,399004.XSHE"}}'

```

### 10. 分钟线数据

```bash

curl 'https://p-xcapi.kjap1.cn/stock/minute_line' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"adj":"bfq","freq":"1min","code":"603520.XSHG"}}'

```

### 11. 日 K 线数据

```bash

curl 'https://p-xcapi.kjap1.cn/stock/date_kline' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"count":2,"code":"300422.XSHE","freq":"D","adj":"qfq","codeType":"0","paramTime":""}}'

```

### 12. 小草环境秒级 / 分时线 v2

```bash

curl 'https://p-xcapi.kjap1.cn/stock/xiao_cao_environment_second_line_v2' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"code":"9A0001,9A0002,9A0003,9B0001,9B0002,9B0003,9C0001,9A0004,9B0004,9A0005,9B0005,9C0002","date":"2026-04-24","codeType":0,"isFoolMode":0}}'

```

### 13. 交易日历

```bash

curl 'https://p-xcapi.kjap1.cn/stock/trade_cal' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"exchange":"SSE","isOpen":1,"startDate":"20240903","endDate":"20260425"}}'

```

### 14. 根据小草板块获取股票代码

```bash

curl 'https://p-xcapi.kjap1.cn/stock/get_code_by_xiao_cao_block' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"blockCodeList":"","industryBlockCodeList":"","categoryCodeList":"","exponentCodeList":"","excIndustryCodeList":"","patternCodeList":"","tradeDate":"2026-04-24","blockTypeList":"","stockIds":"","aiStockIds":"","blockIsAll":0}}'

```

### 15. 个股集合竞价数据

```bash

curl 'https://p-xcapi.kjap1.cn/stock/stock_call_auction' \

  -X POST \

  -H 'content-type: application/json' \

  --data-raw '{"params":{"code":"688808.XSHG","tradeDate":"20260424"}}'
```

---

## 5. 新增接口判断

### 5.1 明确新增能力

| 接口 | 新增能力 |
|---|---|
| `/stock/xiao_cao_block_score` | 板块评分能力 |
| `/stock/next_trade_cal` | 下一交易日判断 |
| `/stock/trade_cal` | 交易日历 |
| `/stock/get_code_by_xiao_cao_block` | 根据板块 / 分类 / 模式反查股票池 |
| `/stock/stock_call_auction` | 集合竞价数据 |
| `/stock/second_line` | 通用分时线 |
| `/stock/second_line_detail_info` | 分时详情 |
| `/stock/minute_line` | 分钟 K 线 |
| `/stock/date_kline` | 日 K 线 |

### 5.2 原有接口升级版

| 新接口 | 原接口 | 判断 |
|---|---|---|
| `/stock/xiao_cao_index_v2` | `/stock/xiao_cao_index` | 明显升级 |
| `/stock/sort_v2` | `/stock/sort` | 明显升级 |
| `/stock/xiao_cao_block_category_rank_v3` | `/stock/xiao_cao_block_category_rank_v2` | 明显升级 |
| `/stock/xiao_cao_environment_second_line_v2` | `/stock/xiao_cao_environment_second_line` | 明显升级 |
| `/stock/focus_xiao_cao_index/get_code_list_v2` | `/stock/focus_xiao_cao_index/get_code_list` | 明显升级 |

---

## 6. 缺失能力与待补充文档

### 6.1 返回字段说明缺失

需要补充每个接口的：

- 返回顶层结构
- `code` / `msg` / `errcode` / `errmsg` 含义
- `result` 内字段说明
- 空数据返回结构
- 非交易日返回结构
- 历史日期超范围返回结构

### 6.2 参数枚举缺失

重点需要确认：

| 参数 | 待确认内容 |
|---|---|
| `model` | 模型枚举 |
| `indexType` | 指数类型枚举 |
| `sortId` | 排序字段枚举 |
| `sortType` | 升序 / 降序定义 |
| `queryType` | 查询类型 |
| `type` | 股票范围 / 市场类型 |
| `hpqbState` | 红盘起爆状态 |
| `lpdxState` | 绿盘低吸状态 |
| `isFoolMode` | 简化模式含义 |
| `blockIsAll` | 板块匹配方式 |
| `codeType` | 代码类型 |

### 6.3 日期格式不统一

当前存在两种格式：

```text
YYYY-MM-DD   例如 2026-04-24
YYYYMMDD     例如 20260424
```

CLI 内部建议统一使用：

```text
YYYY-MM-DD
```

API adapter 层负责转换。

### 6.4 代码格式需要规范

需要区分：

| 类型 | 示例 |
|---|---|
| 沪市股票 | `688808.XSHG` |
| 深市股票 | `300422.XSHE` |
| 北交所 | `899601.BJSE` |
| 指数 | `000001.XSHG`、`399001.XSHE` |
| 小草环境代码 | `9A0001`、`9B0001`、`9C0001` |
| 小草板块代码 | 待接口样例补充 |
| 板块分类代码 | 待接口样例补充 |

---

## 7. CLI 产品设计

### 7.1 命令总览

建议 CLI 名称：

```bash
xiaocao
```

一级命令：

```bash
xiaocao data        数据获取
xiaocao index       小草指数
xiaocao block       板块与方向
xiaocao market      行情数据
xiaocao calendar    交易日历
xiaocao strategy    策略筛选
xiaocao report      报告生成
xiaocao config      配置管理
```

---

## 8. 推荐命令设计

### 8.1 查看交易日

```bash
xiaocao calendar trade-days --start 2026-04-01 --end 2026-04-25
xiaocao calendar latest --date 2026-04-25
xiaocao calendar next --date 2026-04-24
```

### 8.2 获取股票池

```bash
xiaocao data pool --date 2026-04-24 --group dixi
xiaocao data pool --date 2026-04-24 --group jingwang --format csv
```

参数映射：

| CLI 参数 | API 参数 |
|---|---|
| `--group jieli` | `groups=0` |
| `--group jingwang` | `groups=1` |
| `--group hpqb` | `groups=2` |
| `--group dixi` | `groups=3` |

### 8.3 获取小草指数

```bash
xiaocao index stock --date 2026-04-24 --codes 300422.XSHE,688808.XSHG
xiaocao index stock --date 2026-04-24 --from-pool dixi
```

### 8.4 获取排序结果

```bash
xiaocao data sort --date 2026-04-24 --sort-id 8 --stock-file stocks.json
xiaocao data sort --date 2026-04-24 --from-pool dixi --sort-id 8 --format table
```

### 8.5 获取板块方向

```bash
xiaocao block rank --date 2026-04-24 --model 1
xiaocao block category-rank --date 2026-04-24 --model 0
xiaocao block score --date 2026-04-24
```

### 8.6 根据板块获取股票

```bash
xiaocao block stocks --date 2026-04-24 --block-code 980338.ZHBK
xiaocao block stocks --date 2026-04-24 --category-code 000028.BKDL
```

### 8.7 获取行情数据

```bash
xiaocao market second-line --codes 000001.XSHG,399001.XSHE
xiaocao market minute-line --code 603520.XSHG --freq 1min --adj bfq
xiaocao market kline --code 300422.XSHE --count 20 --freq D --adj qfq
xiaocao market auction --code 688808.XSHG --date 2026-04-24
```

### 8.8 运行策略

```bash
xiaocao strategy run --date 2026-04-24
xiaocao strategy run --date latest --modes jieli,dixi,duanban
xiaocao strategy run --date 2026-04-24 --source api --output output/result.csv
xiaocao strategy run --date 2026-04-24 --source local --data-dir results
```

### 8.9 生成报告

```bash
xiaocao report daily --date 2026-04-24 --format markdown
xiaocao report daily --date latest --output reports/2026-04-24.md
```

---

## 9. 统一参数规范

### 9.1 日期参数

CLI 统一使用：

```bash
--date 2026-04-24
```

特殊值：

```bash
--date today
--date latest
--date previous
```

内部处理：

- `today`：自然日
- `latest`：最近一个交易日
- `previous`：上一个交易日

### 9.2 输出格式

统一参数：

```bash
--format table
--format json
--format csv
--format markdown
```

默认：

- 交互终端：`table`
- 自动化调用：建议 `json`
- 数据落盘：建议 `csv`

### 9.3 通用参数

```bash
--config xiaocao.yaml
--base-url https://p-xcapi.kjap1.cn
--source api|local
--output path
--log-level info|debug|warning|error
--cache
--no-cache
--timeout 10
--retries 3
```

---

## 10. 推荐目录结构

```text
xiaocao/
  pyproject.toml
  README.md
  xiaocao.yaml.example

  src/
    xiaocao/
      __init__.py
      cli.py

      config/
        __init__.py
        settings.py

      api/
        __init__.py
        client.py
        endpoints.py
        schemas.py
        errors.py

      datasource/
        __init__.py
        api_source.py
        local_source.py
        cache.py

      domain/
        __init__.py
        models.py
        calendar.py
        stocks.py
        blocks.py
        market.py

      strategy/
        __init__.py
        base.py
        registry.py
        jieli.py
        dixi.py
        duanban.py
        direction.py

      transform/
        __init__.py
        normalize.py
        flatten.py

      output/
        __init__.py
        render.py
        table.py
        csv.py
        json.py
        markdown.py

      report/
        __init__.py
        daily.py

      utils/
        __init__.py
        dates.py
        logging.py
        retry.py

  tests/
    test_api_client.py
    test_calendar.py
    test_strategy.py
    test_output.py
    fixtures/
```

---

## 11. 模块设计

### 11.1 API Client

职责：

- 统一 POST 请求
- 统一 base_url
- 统一 timeout / retry
- 统一错误处理
- 统一响应解析

示例接口：

```python
class XiaocaoClient:
    def get_code_list_v2(self, date, group, hpqb_state=0, lpdx_state=0): ...
    def get_xiao_cao_index_v2(self, date, stock_codes, hpqb_state=0, lpdx_state=0): ...
    def sort_v2(self, stock_ids, sort_id, query_type=1, sort_type=1, type_=0): ...
    def get_industry_block_rank(self, date, model=1): ...
    def get_block_category_rank_v3(self, date, model=0): ...
    def get_block_score(self, date): ...
    def get_trade_cal(self, start, end, exchange="SSE", is_open=1): ...
```

### 11.2 DataSource

统一抽象：

```python
class DataSource:
    def get_pool(self, date, group): ...
    def get_stock_index(self, date, codes): ...
    def get_block_rank(self, date): ...
```

实现：

```python
ApiDataSource
LocalDataSource
CachedDataSource
```

好处：

- 策略不关心数据来自 API 还是本地 CSV
- 方便回测
- 方便离线调试

### 11.3 Strategy

策略接口：

```python
class Strategy:
    name: str
    def match(self, stock, context) -> list[Signal]:
        ...
```

策略上下文：

```python
class StrategyContext:
    date: str
    block_rank: list
    category_rank: list
    market_env: dict
    sorted_pools: dict
```

策略注册：

```python
registry.register(JieliWeakToStrongStrategy())
registry.register(GreenBrokenDixiStrategy())
registry.register(RedBrokenDixiStrategy())
registry.register(DirectionLowDixiStrategy())
```

---

## 12. 现有策略升级建议

### 12.1 当前可复用策略

| 策略 | 当前状态 | 建议 |
|---|---|---|
| 接力低弱转1 | 部分可复用 | 补环境、低位、竞价条件 |
| 接力低弱转2 | 可复用 | 改名或补文档 |
| 绿断低吸 | 可复用 | 补排序口径 |
| 红断低吸 | 部分可复用 | 补“看一作二空三” |
| N 字低吸 | 可复用 | 补方向内排名 |
| 孕线低吸 | 可复用 | 标准化为独立模式 |

### 12.2 需要补齐的模式

根据模式表，当前缺失：

1. 方向低位低吸
2. 全盘低位低吸
3. 首红断低吸
4. 方向内绿盘低吸前 3 名
5. 全盘绿盘低吸前 2 名

新版 API 可帮助补齐：

| 需求 | 可用接口 |
|---|---|
| 方向内股票池 | `/stock/get_code_by_xiao_cao_block` |
| 低吸排名 | `/stock/sort_v2` |
| 个股指标 | `/stock/xiao_cao_index_v2` |
| 板块方向排名 | `/stock/xiao_cao_industry_block_rank` |
| 板块分类排名 | `/stock/xiao_cao_block_category_rank_v3` |
| 集合竞价 | `/stock/stock_call_auction` |
| 交易日判断 | `/stock/trade_cal` |

---

## 13. 核心数据流

### 13.1 每日推荐数据流

```text
输入 date
  ↓
交易日判断 latest / previous
  ↓
获取股票池 get_code_list_v2
  ↓
获取排序 sort_v2
  ↓
获取个股小草指数 xiao_cao_index_v2
  ↓
获取板块方向 industry_block_rank
  ↓
获取板块分类 category_rank_v3
  ↓
构造 StrategyContext
  ↓
运行策略 registry
  ↓
输出 table / csv / json / markdown
```

### 13.2 方向低位低吸数据流

```text
获取板块方向排名
  ↓
选择强方向
  ↓
get_code_by_xiao_cao_block 获取方向内股票
  ↓
sort_v2 按绿盘低吸排序
  ↓
xiao_cao_index_v2 获取个股指标
  ↓
筛选低位 + 竞王 > 200 + 排名前 3
```

---

## 14. 错误处理设计

### 14.1 错误类型

```python
XiaocaoError
ApiError
ApiNotFoundError
ApiAuthError
ApiRateLimitError
ApiSchemaError
NoTradeDayError
NoDataError
InvalidDateError
InvalidCodeError
StrategyError
OutputError
```

### 14.2 CLI 错误输出

默认人类可读：

```text
ERROR: 2026-04-25 is not a trading day. Latest trading day is 2026-04-24.
```

JSON 模式：

```json
{
  "ok": false,
  "error": {
    "type": "NoTradeDayError",
    "message": "2026-04-25 is not a trading day",
    "suggestedDate": "2026-04-24"
  }
}
```

### 14.3 API 错误处理

建议规则：

| 场景 | 处理 |
|---|---|
| HTTP 404 | 抛 `ApiNotFoundError` |
| HTTP 200 但 `code != 8200` | 抛 `ApiError` |
| result 为空 | 返回空数据或抛 `NoDataError`，由命令决定 |
| 非交易日 | 提示 latest trading day |
| 字段缺失 | 抛 `ApiSchemaError` 并记录原始响应 |

---

## 15. 日志设计

默认日志：

```bash
xiaocao strategy run --date latest
```

输出：

```text
[INFO] date resolved: 2026-04-24
[INFO] fetch pool: dixi, count=108
[INFO] fetch pool: jingwang, count=1176
[INFO] fetch block rank: count=17
[INFO] run strategy: green_broken_dixi, hits=5
[INFO] output: output/result_2026-04-24.csv
```

调试模式：

```bash
--log-level debug
```

记录：

- 请求 URL
- 请求参数摘要
- 耗时
- 返回 code
- 数据条数
- 不记录敏感 token

---

## 16. 配置设计

### 16.1 配置文件

默认路径：

```text
~/.xiaocao/config.yaml
./xiaocao.yaml
```

示例：

```yaml
api:
  base_url: https://p-xcapi.kjap1.cn
  timeout: 10
  retries: 3

defaults:
  exchange: SSE
  output_format: table
  data_dir: results
  output_dir: output

strategy:
  hpqb_state: 0
  lpdx_state: 0
  block_model: 1
  category_model: 0

logging:
  level: info
```

### 16.2 环境变量

```bash
XIAOCAO_BASE_URL
XIAOCAO_TIMEOUT
XIAOCAO_RETRIES
XIAOCAO_CONFIG
XIAOCAO_LOG_LEVEL
```

优先级：

```text
CLI 参数 > 环境变量 > 配置文件 > 默认值
```

---

## 17. 输出格式设计

### 17.1 标准 Signal 字段

```json
{
  "date": "2026-04-24",
  "mode": "绿断低吸",
  "code": "300422.XSHE",
  "name": "示例股票",
  "xcjw": 230.5,
  "cjs": 80.2,
  "jsjl": 0,
  "jssb": 0,
  "pctChange": 3.2,
  "openPctChange": 1.1,
  "direction": true,
  "directionRank": 1,
  "categoryRank": 2,
  "reason": "绿断 + 低吸有分 + 竞王达标"
}
```

### 17.2 CSV 输出

建议字段顺序：

```text
date,mode,code,name,xcjw,cjs,jsjl,jssb,pctChange,openPctChange,direction,directionRank,categoryRank,reason
```

### 17.3 Markdown 输出

适合日报：

```markdown
## 2026-04-24 小草模式结果

| 模式 | 代码 | 名称 | 竞王 | 低吸 | 方向 | 原因 |
|---|---|---|---:|---:|---|---|
```

---

## 18. 测试策略

### 18.1 单元测试

重点测试：

- 日期格式转换
- 交易日判断
- API 响应解析
- 策略匹配规则
- 输出格式渲染

### 18.2 Fixture 测试

保存一组脱敏响应样例：

```text
tests/fixtures/
  xiao_cao_index_v2_20260424.json
  get_code_list_v2_dixi.json
  industry_block_rank.json
  category_rank_v3.json
```

### 18.3 回归测试

用旧 `results/2024-10-25_detail.csv` 验证：

- 重构前后策略命中数量是否一致
- 模式名称是否一致
- 输出字段是否兼容

### 18.4 CLI 测试

使用 `pytest` + `CliRunner`：

```bash
xiaocao strategy run --date 2026-04-24 --source local --format json
xiaocao calendar latest --date 2026-04-25
```

---

## 19. 迁移步骤

### 阶段一：接口层重构

1. 新建 `XiaocaoClient`
2. 接入新版 API：
   - `get_code_list_v2`
   - `xiao_cao_index_v2`
   - `sort_v2`
   - `industry_block_rank`
   - `block_category_rank_v3`
3. 保留旧 `xiaocao_api.py`，但标记 deprecated

### 阶段二：CLI 骨架

1. 引入 `typer` 或 `click`
2. 实现：
   - `xiaocao calendar`
   - `xiaocao data pool`
   - `xiaocao block rank`
   - `xiaocao strategy run`

### 阶段三：策略模块化

1. 拆分 `stock_recommend.py`
2. 建立 strategy registry
3. 将旧策略逐个迁移
4. 补齐模式表缺失策略

### 阶段四：输出与报告

1. 支持 table / json / csv / markdown
2. 支持日报生成
3. 支持输出路径配置

### 阶段五：本地数据与缓存

1. 迁移 `xiaocao_file.py`
2. 支持 API / local 双数据源
3. 支持 cache
4. 支持历史回测

---

## 20. 开发优先级

### P0：必须先做

1. 新版 API client
2. `get_code_list_v2`
3. `xiao_cao_index_v2`
4. `sort_v2`
5. `strategy run`
6. CSV / JSON 输出
7. 交易日判断

### P1：核心增强

1. `block_category_rank_v3`
2. `block_score`
3. `get_code_by_xiao_cao_block`
4. 方向低位低吸
5. 全盘低位低吸
6. Markdown 日报

### P2：行情增强

1. `second_line`
2. `minute_line`
3. `date_kline`
4. `stock_call_auction`
5. 接力竞价策略增强

### P3：长期扩展

1. 插件化策略
2. 批量任务
3. 定时任务
4. Agent 调用接口
5. HTML / PDF 报告
6. 可视化 dashboard

---

## 21. 总结

新版 API 已经具备将 `xiaocao` 从脚本集合升级为正式 CLI 工具的基础能力。

最重要的升级点是：

1. 用 `*_v2` / `*_v3` 接口替换已失效旧接口
2. 用 `trade_cal` 解决周末和节假日日期问题
3. 用 `sort_v2` 标准化排名逻辑
4. 用 `get_code_by_xiao_cao_block` 支持方向内选股
5. 用模块化 strategy registry 支持更多模式扩展
6. 用统一 CLI 输出支持人工查看和自动化调用

建议优先完成最小可用闭环：

```text
calendar latest
  → data pool
  → index stock
  → block rank
  → strategy run
  → csv/json output
```

完成该闭环后，再逐步补齐模式表中的完整规则和报告能力。