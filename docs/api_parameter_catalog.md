# API Parameter Catalog

本文专门补“参数层”的信息，重点回答三类问题：

1. 某个接口的枚举参数到底有哪些值
2. 这些值在前端 `reference/index-f3118026.js` 里对应什么业务含义
3. 如果现在从 Python / curl 调用，参数应该怎么填

说明：

- 本文基于 `reference/index-f3118026.js` 的前端映射逻辑整理，不是官方协议文档。
- 对能直接从 bundle 中看到的内容，标记为“前端实锤”。
- 对只能从字段名推断的内容，会显式写“按命名推断”。

## 1. `sort_v2` 参数字典

接口：

```text
POST /stock/sort_v2
```

前端调用链里，这个接口是“给一组股票按某个字段排序”的统一入口。

### 1.1 请求参数

| 参数 | 类型 | 前端口径 | 如何填写 |
|---|---|---|---|
| `queryType` | number | 前端默认固定传 `1` | 当前建议固定填 `1` |
| `sortId` | number | 真正发给后端的排序字段 ID | 如果你手里是 `sortKey`，先查下面映射表再填 |
| `sortType` | number | 前端把 `"desc"` 转成 `1`，其他转成 `0` | 降序填 `1`，升序填 `0` |
| `type` | number | 前端观察到 `stock -> 0`，`block -> 1` | 排股票填 `0`，排板块填 `1` |
| `date` | string | 前端会把 `YYYYMMDD` 转成 `YYYY-MM-DD` | 直接填 `YYYY-MM-DD` 最稳妥 |
| `hpqbState` | number | 前端实锤存在 `0/1` 两档 | 默认 `0`；放宽红盘起爆筛选时用 `1` |
| `lpdxState` | number | 前端实锤存在 `0/1` 两档 | 默认 `0`；放宽绿盘低吸筛选时用 `1` |
| `stockIds` | list[string] | 待排序股票集合 | 传股票代码数组，如 `["300750.XSHE","603520.XSHG"]` |

### 1.2 `sortType` 的前端转换

前端 bundle 中有明确转换：

```text
sortType === "desc" -> 1
otherwise            -> 0
```

所以 raw API 建议直接记成：

- `1`: 降序
- `0`: 升序

### 1.3 `type` 的前端转换

前端排序 hook 里能直接看到：

```text
block -> 1
stock -> 0
```

所以：

- 排股票列表：`type=0`
- 排板块列表：`type=1`

### 1.4 `sortKey -> sortId` 完整映射

这是前端 `vd()` 转换函数里的完整列表，属于“前端实锤”。

#### 基础行情类

| sortKey | sortId | 含义 | 说明 |
|---|---:|---|---|
| `tradeRate5d` | 4 | 5日涨幅 | 前端表头可见 |
| `tradeRate10d` | 5 | 10日涨幅 | 前端表头可见 |
| `tradeRate20d` | 6 | 20日涨幅 | 按命名推断，和 5/10 日口径一致 |
| `pctChangeRate` | 7 | 涨幅 | 前端表头可见 |
| `trade` | 8 | 最新价 / 现价 | 前端同时出现“现价”“最新价”两种中文标题 |
| `pctChange` | 9 | 涨跌 | 前端表头可见 |
| `agencynetbAmt` | 3 | 主力净额 | 前端表头可见 |
| `agencynetbVol` | 10 | 主力净量 | 前端表头可见 |
| `volRate` | 11 | 量比 | 前端表头可见 |
| `riseRate` | 12 | 涨速 | 前端表头可见 |
| `circulationMarketValue` | 14 | 流通市值 | 按字段名和前端字段消费推断 |
| `vol` | 16 | 成交量 | 常规行情字段 |
| `turnoverRate` | 17 | 换手率 | 前端表头可见 |
| `amplitude` | 18 | 振幅 | 前端表头可见 |
| `peRate` | 19 | 市盈(动) | 前端表头可见 |
| `high` | 20 | 最高 | 前端表头可见 |
| `low` | 21 | 最低 | 前端表头可见 |
| `open` | 22 | 开盘 | 前端表头可见 |
| `preClose` | 23 | 昨收 | 前端表头可见 |
| `volOut` | 24 | 外盘 | 按字段名推断，与 `volIn` 成对 |
| `volIn` | 25 | 内盘 | 前端表头可见 |
| `upNum` | 27 | 涨家数 | 前端表头可见 |
| `amt` | 26 | 成交额 | 前端表头可见 |
| `downNum` | 28 | 跌家数 | 前端表头可见 |
| `limitUpNum` | 29 | 涨停家数 | 前端表头可见 |
| `allBuyAmt` | 30 | 总买额 / 委买额 | 仅字段名可见，中文名按命名推断 |
| `allBuySellAmt` | 31 | 买卖差额 / 净流入 | 前端曾出现“净流入”标题，语义接近 |
| `allBuySellAmt5d` | 32 | 5日买卖差额 / 5日净流入 | 按命名推断 |
| `openPctChangeRate` | 33 | 开幅 | 前端导出表头可见 |
| `entityPctChangeRate` | 34 | 当日盈亏 | 前端导出表头可见 |
| `preLimitUpDays` | 35 | 昨日连板 | 前端导出表头可见 |
| `limitUpDays` | 36 | 今日连板 | 前端导出表头可见 |

#### 小草核心模型类

| sortKey | sortId | 含义 | 说明 |
|---|---:|---|---|
| `xiaocaoJSJL` | 37 | 小草连板接力 | 前端下拉选项实锤 |
| `xiaocaoXCJW` | 38 | 小草竞王 | 前端下拉选项实锤 |
| `xiaocaoJSSB` | 39 | 小草红盘起爆 | 前端下拉选项实锤 |
| `xiaocaoCJS` | 40 | 小草绿盘低吸 | 前端下拉选项实锤 |
| `xiaocaoDWCJS` | 41 | 低位绿盘低吸 | 前端导出表头可见 |
| `jsjlTest` | 44 | 连板接力-专享 | 前端下拉选项实锤 |
| `jssbTest` | 45 | 红盘起爆-专享 | 前端下拉选项实锤 |
| `cjsTest` | 46 | 绿盘低吸-专享 | 前端下拉选项实锤 |

#### 方向 / 板块扩展类

| sortKey | sortId | 含义 | 说明 |
|---|---:|---|---|
| `directionCjs` | 47 | 方向绿盘低吸 | 前端曾直接出现该中文标题 |
| `xcjwV2` | 48 | 小草竞王 V2 | 按命名推断，前端字段实锤 |
| `jssbV2` | 49 | 红盘起爆 V2 | 按命名推断，前端字段实锤 |
| `cjsV2` | 50 | 绿盘低吸 V2 | 按命名推断，前端字段实锤 |
| `jsjlBlock` | 51 | 板块连板接力 | 按命名推断 |
| `jssbBlock` | 52 | 板块红盘起爆 | 按命名推断 |
| `cjsBlock` | 53 | 板块绿盘低吸 | 按命名推断 |
| `directionCjsV2` | 54 | 方向绿盘低吸 V2 | 按命名推断，前端字段实锤 |

#### 盘中收益 / 形态扩展类

| sortKey | sortId | 含义 | 说明 |
|---|---:|---|---|
| `cgyk` | 55 | 下杀相关盈亏指标 | 前端 tooltip 文案可见“下杀” |
| `htyk` | 56 | 回调相关盈亏指标 | 前端 tooltip 文案可见“回调” |
| `minuteCgyk` | 57 | 分钟级下杀相关指标 | 按字段名推断 |
| `minuteHtyk` | 58 | 分钟级回调相关指标 | 按字段名推断 |
| `atraderate30d` | 59 | 30日涨幅或同类长周期收益率 | 字段名实锤，中文名按命名推断 |
| `atraderate10d` | 60 | 10日涨幅或同类短周期收益率 | 字段名实锤，中文名按命名推断 |

### 1.5 默认行为与边界

- 前端如果 `sortKey` 为空，不会发排序请求，而是保留原有顺序。
- 前端收到 `sort_v2` 的返回后，还会再次过滤，只保留原始 `stockIds` 里出现的代码。
- 因此 `sort_v2` 更像“对现有股票池重新排序”，不是“返回一个新股票池”。

### 1.6 推荐调用方式

#### 方式一：直接按 `sortId` 调 raw API

例如按“小草竞王”降序排序：

```bash
curl 'https://p-xcapi.kjap1.cn/stock/sort_v2' \
  -X POST \
  -H 'content-type: application/json' \
  --data-raw '{
    "params": {
      "queryType": 1,
      "sortId": 38,
      "sortType": 1,
      "type": 0,
      "date": "2026-04-24",
      "hpqbState": 0,
      "lpdxState": 0,
      "stockIds": ["300750.XSHE", "603520.XSHG", "688008.XSHG"]
    }
  }'
```

#### 方式二：在当前 Python 客户端里手动把 `sortKey` 转成 `sortId`

当前 [client.py](file:///Users/bytedance/coding/xiaocao/src/xiaocao/api/client.py#L116-L137) 只提供：

```python
client.sort_v2(stock_ids=..., sort_id=...)
```

所以如果你想按 `sortKey` 调，需要自己先映射：

```python
SORT_V2_KEY_TO_ID = {
    "pctChangeRate": 7,
    "trade": 8,
    "xiaocaoXCJW": 38,
    "xiaocaoJSSB": 39,
    "xiaocaoCJS": 40,
    "directionCjs": 47,
}

rows = client.sort_v2(
    stock_ids=["300750.XSHE", "603520.XSHG"],
    sort_id=SORT_V2_KEY_TO_ID["xiaocaoXCJW"],
    query_type=1,
    sort_type=1,
    type_=0,
    hpqb_state=0,
    lpdx_state=0,
)
```

#### 方式三：按前端口径封装一个 `sort_key` 辅助层

如果后面要补 Python API，建议封成：

```python
def sort_by_key(
    self,
    stock_ids: list[str],
    sort_key: str,
    descending: bool = True,
    type_: int = 0,
    date: str | None = None,
    hpqb_state: int = 0,
    lpdx_state: int = 0,
):
    ...
```

这样上层就不用记 `38`、`39`、`40` 这些裸数字。

## 2. `get_code_list_v2` 参数补全

接口：

```text
POST /stock/focus_xiao_cao_index/get_code_list_v2
```

### 2.1 `groups` 的前端映射

前端 `u0()` 函数里能直接看到这些映射：

| 前端类型 | groups 值 | 含义 |
|---|---:|---|
| `xiaocaoJSJL` | 0 | 连板接力 |
| `xiaocaoXCJW` | 1 | 竞王 |
| `xiaocaoJSSB` | 2 | 红盘起爆 |
| `xiaocaoCJS` | 3 | 绿盘低吸 |
| `xiaocaoDWCJS` | 4 | 低位绿盘低吸 |
| `jsjl_test` | 30 | 连板接力-专享 |
| `jssb_test` | 31 | 红盘起爆-专享 |
| `cjs_test` | 32 | 绿盘低吸-专享 |

因此 Python / curl 直接调用时，如果你不走前端类型名，应该直接填数字字符串：

- 接力：`groups="0"`
- 竞王：`groups="1"`
- 红盘起爆：`groups="2"`
- 绿盘低吸：`groups="3"`

### 2.2 `hpqbState` / `lpdxState`

这两个参数前端会参与股票池请求和排序请求。

目前能确认的是：

- 前端内部布尔配置名是 `relaxHpqbState` / `relaxLpdxState`
- 发请求时会落成数字 `interfaceAlgorithmSwitching:{relaxHpqbState:0, relaxLpdxState:0}`
- 当前观察最可靠的用法是：
  - `0`: 默认
  - `1`: 放宽筛选

还不能仅凭 bundle 确认是否存在 `2+` 的更多档位，因此现阶段不建议随意传大于 `1` 的值。

## 3. 排名接口 `model` 参数

适用接口：

- `/stock/xiao_cao_industry_block_rank`
- `/stock/xiao_cao_block_category_rank_v3`

这个部分已经在 [api_models.md](file:///Users/bytedance/coding/xiaocao/docs/api_models.md) 中单独整理过，这里只给结论：

| model | 建议名称 | 含义 |
|---:|---|---|
| `0` | `full` | 全量强度排行 |
| `1` | `focus` | 精选 / 稀疏 / 策略口径 |
| `2` | `full_alias_2` | 当前表现近似 `0` |
| `3` | `full_alias_3` | 当前表现近似 `0` |

推荐：

- 做报告展示时优先 `model=0`
- 做策略加持或精选方向时可试 `model=1`

## 4. `xiao_cao_dynamic_index` 的 `indexType`

接口：

```text
POST /stock/xiao_cao_dynamic_index
```

前端能确认：

- 会传 `indexType`
- 有一处分支逻辑是 `type === "jinglong" ? 0 : 1`

所以目前最稳妥的说法是：

| indexType | 观察结论 |
|---:|---|
| `0` | 前端某类 `jinglong` 视图使用 |
| `1` | 非 `jinglong` 视图使用 |

这里还不能只靠 bundle 给出更强语义命名，所以不建议在 Python 侧过早写死成业务友好枚举。

## 5. 现阶段最实用的参数建议

如果你只是想把现有 Python 客户端用起来，而不是 100% 复刻前端，下面这组参数最实用：

### 5.1 排竞王

```python
rows = client.sort_v2(
    stock_ids=codes,
    sort_id=38,   # xiaocaoXCJW
    sort_type=1,  # desc
    type_=0,
    hpqb_state=0,
    lpdx_state=0,
)
```

### 5.2 排红盘起爆

```python
rows = client.sort_v2(
    stock_ids=codes,
    sort_id=39,   # xiaocaoJSSB
    sort_type=1,
    type_=0,
    hpqb_state=0,
    lpdx_state=0,
)
```

### 5.3 排绿盘低吸

```python
rows = client.sort_v2(
    stock_ids=codes,
    sort_id=40,   # xiaocaoCJS
    sort_type=1,
    type_=0,
    hpqb_state=0,
    lpdx_state=0,
)
```

### 5.4 方向内绿盘低吸

```python
rows = client.sort_v2(
    stock_ids=codes,
    sort_id=47,   # directionCjs
    sort_type=1,
    type_=0,
    hpqb_state=0,
    lpdx_state=0,
)
```

## 6. 技术指标 `indicators` 参数

来源：`reference/index-f3118026.js` 中 `Zd` 数组（~5747）。`h6`（~5746）多了三个，但只在前端图表本地渲染，不发给 backend。

### 6.1 backend 接受的 `indicators` 值

| 值 | 含义 | 备注 |
|---|---|---|
| `smallGrass` | 小草核心指标 | ema/aaaLine/bbbLine 等小草自有线，前端默认值 |
| `vol` | 成交量 | |
| `amt` | 成交额 | |
| `macd` | MACD | |
| `rsi` | RSI | |
| `kdj` | KDJ | |
| `boll` | 布林带 | |

### 6.2 前端本地渲染、backend **不接受** 的值

| 值 | 含义 |
|---|---|
| `smallGrassTrend` | 小草趋势线（前端本地计算） |
| `klinesma` | K 线均线（前端本地计算） |
| `mike` | 麦克支撑压力（前端本地计算） |

CLI 侧 `xiaocao indicator query --indicator klinesma` 会在 argparse 阶段就报错。

## 7. K 线 `freq` 与 `adj` 枚举

来源：`reference/index-f3118026.js` 的 `u6` 对象（~5728）和 `K0` 函数默认参数（~13220）。

### 7.1 `freq`

| 值 | 含义 |
|---|---|
| `5min` | 5 分钟 |
| `15min` | 15 分钟 |
| `30min` | 30 分钟 |
| `60min` | 60 分钟 |
| `D` | 日线 |
| `W` | 周线 |
| `M` | 月线 |
| `Q` | 季线 |
| `Y` | 年线 |

### 7.2 `adj`

| 值 | 含义 | 默认场景 |
|---|---|---|
| `qfq` | 前复权 | 分钟级 freq 默认 |
| `bfq` | 不复权 | 日线及以上默认 |

JS 中 `K0` 的判断逻辑等价于 `adj = "min" in freq ? "qfq" : "bfq"`。CLI 的 `_indicator_adj_default()` 也按这个口径推断。

## 8. 环境分时默认 code list

来源：`src/xiaocao/api/client.py` `xiao_cao_environment_second_line_v2` 的 `code` 默认值。

```text
9A0001, 9A0002, 9A0003, 9B0001, 9B0002, 9B0003,
9C0001, 9A0004, 9B0004, 9A0005, 9B0005, 9C0002
```

这些是小草环境指数（`.XCHJZS` 域）。前端默认就是按这一组代码请求 v2 环境分时。

## 9. 百分比 normalizer 字段

`client.py` 的 `_percent()` 把 backend 返回的"百倍"字段除以 100。下面字段确认会经过这个处理：

| 字段 | 出现位置 |
|---|---|
| `pctChangeRate` | `_normalize_kline_rows` / `_normalize_minute_line_rows` / `_normalize_technical_rows` / `xiao_cao_environment_second_line_selection` / `xiao_cao_block_detail` |
| `turnoverRate` | `_normalize_kline_rows` / `_normalize_technical_rows` / `xiao_cao_environment_second_line_selection`（来源字段名 `turnoverRatio`） |
| `roe` | `stock_info` |
| `maxPctChangeRate` | `xiao_cao_week_stats` |

注意：`pctChange`（绝对涨跌额，单位元）不进 `_percent`。

## 10. 后续建议

基于这份参数字典，Python 侧下一步最值得补的是：

1. 在 `client.py` 增加 `SORT_V2_KEY_TO_ID`
2. 新增 `sort_v2_by_key()`，直接接受 `sort_key`
3. 给 `get_code_list_v2()` 增加 groups 的语义常量
4. 把 `hpqb_state` / `lpdx_state` 从裸数字提升成更友好的布尔或枚举参数
