# Xiaocao CLI

`xiaocao` 是一个围绕“小草 API”的命令行工具。它既覆盖小草指数、板块方向、个股模式和日报复盘，也把 API 里的个股行情、指数行情、分钟线、历史 K 线、交易日历等通用市场数据能力暴露出来。它支持直接调用线上 API，也支持读取仓库里的本地历史 CSV 数据，适合日常看盘、自动化选股、生成日报、拉取行情数据和做接口契约测试。

## 安装与运行

推荐直接从源码运行：

```bash
PYTHONPATH=src python3 -m xiaocao --help
```

如果你的 `pip` 版本较新，也可以安装成命令：

```bash
python3 -m pip install -e .
xiaocao --help
```

老版本 `pip` 如果不支持 editable install，可以继续使用 `PYTHONPATH=src python3 -m xiaocao ...`。

## 全局参数

这些参数可以放在子命令前面或后面：

```bash
--config xiaocao.yaml
--base-url https://p-xcapi.kjap1.cn
--timeout 10
--retries 3
--format table|json|csv|markdown
--output output/file.csv
```

日期参数一般使用 `YYYY-MM-DD`，部分命令支持：

```bash
--date today
--date latest
--date previous
```

输出格式建议：

- `table`：人工在终端查看
- `json`：给脚本、Agent、自动化流程使用
- `csv`：落盘后用表格工具分析
- `markdown`：日报和文档

## 完整用法速查

下面先给完整命令地图，后面再展开典型场景和细节说明。

### 交易日历

```bash
xiaocao calendar latest --date today
xiaocao calendar latest --date 2026-04-25
xiaocao calendar latest --date today --source local
xiaocao calendar trade-days --start 2026-04-01 --end 2026-04-25 --format json
xiaocao calendar next --date 2026-04-24
```

### 通用行情：个股 / 指数 / 大盘

`quote` 是面向通用行情数据的一等入口。股票代码和指数代码都可以传，例如 `300750.XSHE`、`000001.XSHG`、`399001.XSHE`。

```bash
# 实时行情详情，默认调用 second_line_detail_info
xiaocao quote realtime --codes 000001.XSHG,399001.XSHE,300750.XSHE --format table

# 原始分时线，调用 second_line
xiaocao quote realtime --codes 000001.XSHG,399001.XSHE --raw-line --format json

# 个股或指数分钟线
xiaocao quote minute --code 300750.XSHE --freq 1min --adj bfq --format json

# 个股或指数历史 K 线；freq 可用于日线、周线、月线等 API 支持的周期
xiaocao quote history --code 000001.XSHG --count 60 --freq D --adj qfq --format csv --output output/sh_index.csv
xiaocao quote history --code 300750.XSHE --count 120 --freq D --adj qfq --format table
xiaocao quote history --codes 300750.XSHE,000001.XSHG --count 20 --freq D --adj qfq --format csv --output output/batch_kline.csv

# 集合竞价
xiaocao quote auction --code 300750.XSHE --date latest --format json
```

### 小草股票池、排序和个股指数

```bash
# 股票池：jieli/lianban 接力，jingwang 竞王，hpqb/qibao 红盘起爆，dixi 低吸
xiaocao data pool --date latest --group dixi --format json
xiaocao data pool --source local --date 2024-10-25 --group dixi

# 在股票池或自定义股票列表中排序；优先用 sort-key，不必记裸数字
xiaocao data sort --date latest --from-pool dixi --sort-key xiaocaoCJS --format table
xiaocao data sort --date latest --from-pool dixi --sort-key directionCjs --sort desc --format table
xiaocao data sort --date latest --stock-file stocks.json --sort-key xiaocaoXCJW --format csv --output output/sorted.csv

# 个股小草指数
xiaocao index stock --date latest --codes 688807.XSHG,301050.XSHE --format json
xiaocao index stock --date latest --from-pool dixi --format csv --output output/dixi_index.csv

# 小草动态指数
xiaocao index dynamic --date latest --index-name jinglong --format table
xiaocao index industry-dynamic --date latest --index-name jinglong --format table
```

### 板块、方向和环境

```bash
xiaocao block rank --date latest --rank-model focus --format table
xiaocao block category-rank --date latest --rank-model full --format table
xiaocao block score --date latest --format json
xiaocao block stocks --date latest --block-code 980338.ZHBK --format json
xiaocao block stocks --date latest --category-code 000028.BKDL --format json
xiaocao block detail --date latest --code T08.ZHBK --format json
xiaocao block kline --code T08.ZHBK --count 60 --format table

xiaocao market overview --format json
xiaocao market stock-info --format csv --output output/stock_info.csv
xiaocao market environment --date latest --format json
xiaocao market environment --date latest --codes 9A0001,9A0002,9B0001 --format table
xiaocao market env-selection --date latest --format json
xiaocao market week-stats --format json
```

### 兼容行情入口

`market` 下保留了原始 API 语义更明显的兼容入口；新脚本优先使用 `quote` 查询普通行情，使用 `market environment` 查询小草环境分时。

```bash
xiaocao market second-line --codes 000001.XSHG,399001.XSHE --format json
xiaocao market second-line-detail --codes 000001.XSHG,399001.XSHE --format table
xiaocao market minute-line --code 603520.XSHG --freq 1min --adj bfq --format json
xiaocao market kline --code 000001.XSHG --count 60 --freq D --adj qfq --format table
xiaocao market auction --code 688808.XSHG --date latest --format json
xiaocao market each-trade --code 300750.XSHE --count 20 --format table
xiaocao market env-minute --code 9A0001.XCHJZS --date latest --format json
xiaocao market technical --history --param code=300750.XSHE --param freq=D --format json
xiaocao market technical --param code=300750.XSHE --format json
```

### 策略和报告

```bash
xiaocao strategy run --date latest --source api --format table
xiaocao strategy run --date latest --modes jieli,dixi --sort-key xiaocaoCJS --format csv --output output/signals.csv
xiaocao strategy run --source local --date 2024-10-25 --format table

xiaocao report premarket --date latest --source api --output reports/premarket/latest.md
xiaocao report afterclose --date latest --source api --output reports/afterclose/latest.md
xiaocao report daily --date latest --source api --format json --output output/daily.json
```

### 配置与调试

```bash
xiaocao config show --format json
xiaocao catalog list --format table
xiaocao catalog describe sort_v2 --format json
xiaocao catalog sort-keys --format table
xiaocao catalog groups --format table
xiaocao catalog rank-models --format table
xiaocao catalog index-types --format table
xiaocao catalog freqs --format table
xiaocao catalog adjs --format table
xiaocao catalog indicators --format table
PYTHONPATH=src python3 -m pytest tests/e2e -q
```

`catalog` 子命令仅做参数速查，不发请求。需要发请求请用对应业务子命令（`market`/`block`/`indicator` 等）。

## 典型使用场景与调用流

这个 CLI 不是只为了把 API 包一层，而是为了覆盖几个高频工作流：盘前准备、盘中查询、盘后复盘、历史回放和自动化监控。

### 场景一：盘前准备

目标：开盘前快速知道今天重点看哪些方向、哪些模式信号、市场环境有没有风险。

推荐调用流：

```bash
# 1. 找最近一个已完成交易日
xiaocao calendar latest --date today

# 2. 生成盘前参考报告
xiaocao report premarket --date latest --source api --output reports/premarket/latest.md

# 3. 如果只想看候选信号
xiaocao strategy run --date latest --source api --format table

# 4. 如果想导出给表格工具
xiaocao strategy run --date latest --source api --format csv --output output/premarket_signals.csv
```

设计思路：

- `premarket` 用最近已完成交易日的数据，不假设当日数据已经完整。
- 报告里的强方向用于开盘前建立观察框架。
- 策略结果用于形成候选池，而不是直接给买卖指令。

### 场景二：盘中快速查询

目标：盘中临时查看某个方向、股票池、行情分时或环境状态。

推荐调用流：

```bash
# 看当前低吸池
xiaocao data pool --date latest --group dixi --format table

# 看某批股票的小草指数
xiaocao index stock --date latest --codes 688807.XSHG,301050.XSHE --format table

# 看方向内股票
xiaocao block stocks --date latest --category-code 000031.BKDL --format json

# 看指数/股票分时详情
xiaocao quote realtime --codes 000001.XSHG,399001.XSHE,300750.XSHE --format table

# 看指数/股票历史 K 线
xiaocao quote history --code 000001.XSHG --count 60 --freq D --format table
xiaocao quote history --codes 300750.XSHE,000001.XSHG --count 20 --freq D --format csv --output output/batch_kline.csv

# 看小草环境分时
xiaocao market environment --date latest --format table
```

设计思路：

- 盘中查询尽量使用 `table` 或 `json`，便于快速读或接到其他工具。
- `block stocks` 适合从“方向”反查股票池。
- `environment` 更偏市场状态，不直接替代策略信号。

### 场景三：盘后复盘

目标：收盘后复盘当天方向、环境、策略信号，并检查上一交易日选出的股票表现。

推荐调用流：

```bash
# 生成盘后复盘
xiaocao report afterclose --date latest --source api --output reports/afterclose/latest.md

# 输出结构化 JSON，给自动化汇总或 Agent 使用
xiaocao report afterclose --date latest --source api --format json --output output/afterclose.json
```

盘后复盘会额外做一件事：

```text
找到前一个交易日 -> 运行前一交易日策略 -> 获取日 K -> 计算 前一交易日开盘 到 当前交易日收盘 的收益率
```

设计思路：

- 当天的策略信号告诉你“今天出现了什么”。
- 上一交易日信号表现告诉你“昨天选出来的东西今天兑现得怎么样”。
- 这个收益率是复盘口径，不是实盘成交回测；它默认用前一交易日开盘价和当前交易日收盘价做统一衡量。

### 场景四：历史回放和本地调试

目标：不用打线上 API，直接用仓库里的历史 CSV 验证策略输出。

推荐调用流：

```bash
# 看本地某天的低吸池
xiaocao data pool --source local --date 2024-10-25 --group dixi

# 跑本地策略
xiaocao strategy run --source local --date 2024-10-25 --format table

# 生成本地日报
xiaocao report daily --source local --date 2024-10-25 --output output/daily_2024-10-25.md
```

设计思路：

- `--source local` 适合回归测试、离线调试、策略迁移验证。
- 本地数据没有所有线上接口，因此日报里的部分实时板块、环境信息会缺失或不展示。

### 场景五：自动化和 Agent 调用

目标：让脚本、定时任务或 Agent 稳定消费结果。

推荐调用流：

```bash
# JSON 输出，适合机器消费
xiaocao report afterclose --date latest --source api --format json --output output/afterclose.json

# CSV 输出，适合表格和批处理
xiaocao strategy run --date latest --source api --format csv --output output/signals.csv

# Live API 契约测试，尽早发现接口 breaking change
PYTHONPATH=src python3 -m pytest tests/e2e -q
```

设计思路：

- 自动化优先使用 `json`，字段结构更稳定。
- 报告类命令适合产出综合上下文。
- 单一资源查询命令适合按需拉取 API 数据。
- e2e 测试会动态选择最近交易日，适合作为接口健康检查。

## 交易日历

```bash
xiaocao calendar latest --date today
xiaocao calendar latest --date 2026-04-25
xiaocao calendar trade-days --start 2026-04-01 --end 2026-04-25 --format json
xiaocao calendar next --date 2026-04-24
```

## 股票池与排序

股票池分组：

- `jieli` / `lianban`：接力
- `jingwang`：竞王
- `hpqb` / `qibao`：红盘起爆
- `dixi`：低吸

```bash
xiaocao data pool --date latest --group dixi --format json
xiaocao data pool --date 2026-04-24 --group jingwang --format csv --output output/jingwang.csv
xiaocao data sort --date latest --from-pool dixi --sort-key xiaocaoCJS --format table
xiaocao data sort --date latest --from-pool dixi --sort-key directionCjs --sort desc --format table
xiaocao data sort --date latest --stock-file stocks.json --sort-key xiaocaoXCJW --format csv --output output/sorted.csv
```

`--source local` 可读取本地 `results/*_detail.csv`：

```bash
xiaocao data pool --source local --date 2024-10-25 --group dixi
```

排序参数优先使用 `--sort-key`。可通过下面命令查看完整映射：

```bash
xiaocao catalog sort-keys --format table
```

`--sort-id` 仍保留，用于兼容旧脚本。本地排序当前支持常用映射：

- `37 -> jsjl` / `44 -> jsjlTest`
- `38 -> xcjw` / `48 -> xcjwV2`
- `39 -> jssb` / `45 -> jssbTest`
- `40 -> cjs` / `46 -> cjsTest`
- `41 -> dwcjs`
- `47 -> directionCjs` / `54 -> directionCjsV2`
- `55 -> cgykValue`
- `56 -> htykValue`
- `57 -> minuteCgykValue`
- `58 -> minuteHtykValue`
- `59 -> atraderate30d`
- `60 -> atraderate10d`

## 小草指数

个股小草指数：

```bash
xiaocao index stock --date latest --codes 688807.XSHG,301050.XSHE --format json
xiaocao index stock --date latest --from-pool dixi --format csv --output output/dixi_index.csv
```

小草动态指数：

```bash
xiaocao index dynamic --date latest --index-name jinglong --format table
xiaocao index dynamic --date 2026-04-24 --index-name jinglong --format json
xiaocao index industry-dynamic --date latest --index-name jinglong --format table
```

## 板块与方向

```bash
xiaocao block rank --date latest --rank-model focus --format table
xiaocao block category-rank --date latest --rank-model full --format table
xiaocao block score --date latest --format json
xiaocao block stocks --date latest --block-code 980338.ZHBK --format json
xiaocao block stocks --date latest --category-code 000028.BKDL --format json
xiaocao block detail --date latest --code T08.ZHBK --format json
xiaocao block kline --code T08.ZHBK --count 60 --format table
```

`model` 口径目前没有官方枚举文档。CLI 优先使用 `--rank-model full|focus|full_alias_2|full_alias_3`；`--model` 仍保留为底层数字透传。当前约定是：报告展示使用 `full`，策略加持默认使用 `focus`。更详细的推理和证据见 [docs/api_models.md](docs/api_models.md)。

## 通用行情

`quote` 适合查询个股、指数和大盘行情。指数代码示例：上证指数 `000001.XSHG`，深证成指 `399001.XSHE`，创业板指 `399006.XSHE`。

```bash
xiaocao quote realtime --codes 000001.XSHG,399001.XSHE,399006.XSHE --format table
xiaocao quote realtime --codes 000001.XSHG,399001.XSHE --raw-line --format json
xiaocao quote minute --code 603520.XSHG --freq 1min --adj bfq --format json
xiaocao quote history --code 000001.XSHG --count 60 --freq D --adj qfq --format table
xiaocao quote history --code 300422.XSHE --count 120 --freq D --adj qfq --format csv --output output/300422_kline.csv
xiaocao quote history --codes 300750.XSHE,000001.XSHG --count 20 --freq D --adj qfq --format csv --output output/batch_kline.csv
xiaocao quote auction --code 688808.XSHG --date latest --format json
```

`quote history` 底层调用 `date_kline`，因此股票和指数可以共用同一个入口。`--count` 控制返回条数，`--freq` 和 `--adj` 传给 API 原始参数。`--codes` 支持一次传入多个代码；由于当前 `date_kline` API 本身是单代码接口，CLI 会并发拉取并合并输出。

## 行情与环境兼容入口

`market` 保留更贴近原始 API 名称的入口，也提供小草环境分时：

```bash
xiaocao market second-line --codes 000001.XSHG,399001.XSHE,399006.XSHE --format json
xiaocao market overview --format json
xiaocao market stock-info --format csv --output output/stock_info.csv
xiaocao market env-selection --date latest --format json
xiaocao market week-stats --format json
xiaocao market each-trade --code 300750.XSHE --count 20 --format table
xiaocao market env-minute --code 9A0001.XCHJZS --date latest --format json
xiaocao market technical --history --param code=300750.XSHE --param freq=D --format json
xiaocao market technical --param code=300750.XSHE --format json
xiaocao market second-line-detail --codes 000001.XSHG,399001.XSHE,399006.XSHE --format table
xiaocao market minute-line --code 603520.XSHG --freq 1min --adj bfq --format json
xiaocao market kline --code 300422.XSHE --count 20 --freq D --adj qfq --format table
xiaocao market kline --codes 300750.XSHE,000001.XSHG --count 20 --freq D --adj qfq --format csv
xiaocao market auction --code 688808.XSHG --date latest --format json
xiaocao market environment --date latest --format json
xiaocao market environment --date latest --codes 9A0001,9A0002,9B0001 --format table
```

## 小草技术指标

`indicator` 子命令封装 `/stock/get_technical_index` 与 `/stock/get_technical_index_history`。这两个接口和大多数 `/stock/...` API 不一样：前端 POST 的是 raw body，不包 `{params: ...}`。CLI 和 `XiaocaoClient` 已按这个口径处理。

`smallgrass` preset 直接给 `indicators=smallGrass`：

```bash
xiaocao indicator smallgrass current --code 300750.XSHE --format json
xiaocao indicator smallgrass current --codes 300750.XSHE,000001.XSHG --format json
xiaocao indicator smallgrass history --code 300750.XSHE --freq D --count 120 --format json
xiaocao indicator smallgrass history --code 300750.XSHE --freq 5min --count 240 --format json
```

`query` 子命令允许指定 backend 接受的其它 indicator：

```bash
xiaocao indicator query current --code 300750.XSHE --indicator macd --format json
xiaocao indicator query history --code 300750.XSHE --indicator boll --freq D --format json
```

backend 接受的 indicators（来自 `reference/index-f3118026.js` 的 `Zd` 数组）：`smallGrass / vol / amt / macd / rsi / kdj / boll`。前端图表本地渲染但 backend **不接受**的：`smallGrassTrend / klinesma / mike` —— 用 `indicator query --indicator klinesma` 会被 argparse 直接拒绝。

参数：

| 参数 | 适用 | 默认 | 含义 |
|---|---|---|---|
| `--code` | 当前、历史 | 必填（历史） | 股票/指数代码 |
| `--codes` | 当前 | — | 逗号分隔多个代码 |
| `--freq` | 历史 | `D` | `D/W/M/Q/Y/5min/15min/30min/60min` |
| `--adj` | 历史 | freq 推导 | `qfq`（min 周期）/`bfq`（其它），来自 JS `K0` 默认 |
| `--count` | 历史 | `200` | 返回条数 |
| `--trade-date` | 历史 | — | 上翻加载更多时使用 |
| `--indicator` | `query` 必填 | — | 见上方 backend 列表 |

旧的 `market technical --history --param code=...` 兼容入口保留，作为低层透传调试路径。

## 策略运行

默认运行当前已迁移的接力、断板、低吸、方向内低吸等策略。策略信号统一过滤 `openPctChange < 6`，避免开盘涨幅过高的候选：

```bash
xiaocao strategy run --date latest --source api --format table
xiaocao strategy run --date latest --source api --format csv --output output/result.csv
```

只跑某类模式：

```bash
xiaocao strategy run --date latest --modes jieli
xiaocao strategy run --date latest --modes dixi
xiaocao strategy run --date latest --modes direction --sort-key directionCjs
```

本地历史数据回放：

```bash
xiaocao strategy run --source local --date 2024-10-25 --format table
xiaocao strategy run --source local --date 2024-10-25 --modes direction --sort-key xiaocaoCJS
```

方向内排序与每方向上限：

```bash
xiaocao strategy run --date latest --modes direction \
  --direction-sort-key directionCjs \
  --max-per-direction 5

xiaocao strategy run --date latest --profile default
```

- `--direction-sort-key`：方向内候选股排序口径，默认 `directionCjs`（id 47），更贴近前端"方向内绿盘低吸"语义。可改成 `directionCjsV2` / `xiaocaoCJS` / `xcjwV2` 等。
- `--pool-sort-key`：接力 / 低吸两个池子的预排序口径，默认沿用历史的 `38 (xiaocaoXCJW)`。
- `--max-per-direction`：每个方向最多保留多少候选，默认 10。
- `--exclude-modes`：逗号分隔的模式名，跳过这些模式（如 `接力低弱转2`）。
- `--profile`：把上面这些参数打包成预设。当前推荐 `validated_v5`（多日持仓 max_dd 2%）。完整列表见下面「已经验证通过的 profile」段。

报告子命令也接受 `--top-blocks`（强方向详情拉取数量，默认 5）和 `--no-extras`（跳过 market_overview / 方向详情 / 技术指标拉取，加速本地调试）。

策略输出每个 `(date, code)` 只发一条信号；如果同一标的同时命中多个模式，主模式留在 `mode` 字段，其它模式记录在 `dropped_modes` 里。

## 回测

`xiaocao backtest run` 用现有策略对历史区间复跑，按"信号当日 qfq 开盘买、次个交易日 qfq 收盘卖"的 1 日持仓口径打分。产出：每日 `signals_<date>.json` + 收尾 `trades.csv` + 聚合 `summary.json`（含 `overall_signal_level`、`overall_stock_day_level`、`mode_summary`）。

```bash
# 基础回测
xiaocao backtest run --start 2026-03-01 --end 2026-04-24

# 指定输出目录
xiaocao backtest run --start 2026-03-01 --end 2026-04-24 \
  --output output/xiaocao_backtest_2026-03-01_2026-04-24

# A/B 验证：剔除某个表现差的模式
xiaocao backtest run --start 2026-03-01 --end 2026-04-24 \
  --exclude-modes 接力低弱转2 \
  --output output/xiaocao_backtest_no_jslrz2
```

backtest 接受全部 `strategy run` 的过滤参数（`--modes`、`--sort-key`、`--direction-sort-key`、`--pool-sort-key`、`--max-per-direction`、`--exclude-modes`、`--profile`），所以同一份策略改动可以快速 A/B：跑两次同区间，对比两个 `summary.json`。

### 性能选项

`--cache` 默认开启，路径为 `output/.cache/xiaocao.db`。所有过去日期的 API 结果（block_rank / get_xiao_cao_index_v2 / sort_v2 / 历史 K 线 等）存进 SQLite；下次相同查询命中缓存直接返回。冷缓存下 39 天回测约 2 分钟（workers=6），热缓存下 0.1 秒。

```bash
# 默认就有缓存，可指定路径
xiaocao backtest run --start 2026-03-01 --end 2026-04-24

# 显式指定缓存路径
xiaocao --cache ~/.xiaocao_cache.db backtest run --start 2026-03-01 --end 2026-04-24

# 关闭缓存，每次都打 API
xiaocao --no-cache backtest run --start 2026-03-01 --end 2026-04-24

# 跨天并行（冷缓存下显著加速；adaptive_modes 会强制串行）
xiaocao backtest run --start 2026-03-01 --end 2026-04-24 --workers 6
```

### B 档结构性增强（道+法层）

每个回测信号默认会被标注 `regime`/`is_main_line`/`is_big_cap`，summary 里相应有 `regime_summary` / `mainline_summary` / `bigcap_summary` 切片。可调参数：

```bash
xiaocao backtest run --start 2026-03-01 --end 2026-04-24 \
  --mainline-window 3 --mainline-topk 5 \
  --bigcap-top-pct 0.2 \
  [--require-main-line]    # 硬过滤：只保留主线方向内的信号
  [--exclude-main-line]    # 硬过滤：只保留主线方向之外的信号（短线套利友好）
  [--regime-gate]          # 硬过滤：丢弃当前 regime 不允许的模式（live 才有 regime）
  [--max-open-pct 4]       # 覆盖默认 6.0 的开幅上限
  [--no-enrich]            # 关闭所有标注，跑 baseline 行为
```

注意：`market_overview` 接口是 live state（无历史日期参数），所以 backtest 中历史日期的 regime 留空；live `xiaocao strategy run` 才有有效 regime。

实测发现：在小草现有的"短线弱转强 / 低吸"模式集合上，**主线之外的信号反而表现更好**（baseline 数据：on-mainline avg -5.5%/win 17%，off-mainline avg +3.7%/win 62%），与 0413-A "盘中方向卡的是新轮动而非昨日老主线" 一致。所以 `--exclude-main-line` 比 `--require-main-line` 通常更适合短线模式。

### 自适应模式（Adaptive mode gating）

**关键设计**：adaptive 不丢信号。每个候选信号都会被生成、按次日开盘买/收盘卖打分、写进 mode_history。adaptive 的作用是给每条信号打 `adaptive_active = True/False` 标签：

- `adaptive_active = True` → **active**：计入用户的"真实"收益（real P&L）
- `adaptive_active = False` → **shadow**：仅作参考，不计入 P&L，但 outcome 仍记录到 mode_history

这样设计的好处：
- 没有冷启动 chicken-egg 问题（即使 mode_history 为空，所有信号照样跑、照样记录）
- adaptive 的滚动窗口反映模式的**真实**长期表现，不只是 adaptive 放行的子集
- 模式稀疏（如 8 笔 / 39 天）也够用——所有 outcome 都有记录

每个模式查自己 5/10/20 个**交易日**的滚动 (n, avg)，按下面分层规则决定下一日的 active/shadow：

| 层级 | 条件（n_min 默认 5d/10d/20d = 1/2/3） | 决策（thr 默认 5d/10d/20d = -5%/-3%/-2%）|
|---|---|---|
| Tier 1 | 5d AND 10d 都达 n_min | 双窗口都 avg ≤ thr → SHADOW；任一正向 → ACTIVE |
| Tier 2 | 5d 或 10d 单独达 n_min | 该单窗口 avg ≤ thr → SHADOW；正向 → ACTIVE |
| Tier 3 | 5d/10d 都不足，20d 达 n_min | 20d avg ≤ thr → SHADOW；正向 → ACTIVE |
| Tier 4 | 20d 也不足 | **SHADOW**（dormant 模式无证据可下注，但信号仍记录） |

> 默认 (n_min=1/2/3, thr=-5/-3/-2) 经过 5 个月 4 个月训练 / 1 个月测试集上 1620 配置 grid
> 验证为接近最优——抬高 n_min 会损失样本，降低 thr 改善有限；详见
> `reports/strategy_tuning_2025-12_2026-04.md` §4.1。

```bash
# 默认开启
xiaocao backtest run --start 2026-03-01 --end 2026-04-24
#   → 输出：signal-level (全部) + active (P&L) + shadow (参考)

# 关闭：所有信号默认视为 active
xiaocao backtest run --start 2026-03-01 --end 2026-04-24 --no-adaptive-modes

# 第二次跑同一窗口要消费 mode_history（不要清空）
xiaocao backtest run --start 2026-03-01 --end 2026-04-24 --no-reset-mode-history
```

Summary JSON 里有 `overall_signal_level` / `active_signal_level` / `shadow_signal_level` 三个分组；`mode_summary` 每条带 `all` 和 `active` 两个口径。

实测在 2026-03 → 2026-04 区间：
- 第一次跑（mode_history 空）：30 信号全部 SHADOW（Tier 4），mode_history 写入 30 条
- 第二次跑（不 reset）：30 信号 → 5 ACTIVE / 25 SHADOW
  - `接力低弱转2` 14/16 SHADOW（Tier 1/3 大多 avg ≤ 0）
  - `方向内绿盘低吸前3名` 5/6 SHADOW
  - 即 adaptive 自主把这两个差模式 ~85% 屏蔽到 shadow，与手动 `--exclude-modes` 等效（不 100%，因为 rolling 窗口偶尔翻正）

**预热建议**：如果你希望第一次跑就有 ACTIVE 信号产生（而不是全 shadow），用 `--warmup-start <更早日期>` 让早期信号当 seed（warmup 段不进 summary）。前提是 warmup 段策略本身能产生信号——2026-02 在我们的数据里恰好为零，所以 Feb warmup 对这段无效。

### 跨窗口反过拟合验证

任何"看起来变好"的策略改动，单一时间窗结论不可信（30 笔交易 ≠ 大数定律）。`backtest validate` 强制要求变体在至少 2 个不重叠窗口都改善才算通过：

```bash
xiaocao backtest validate \
  --windows 2026-03-01:2026-03-31,2026-04-01:2026-04-24 \
  --variant='--exclude-modes 接力低弱转2,方向内绿盘低吸前3名' \
  --metric avg \
  --output reports/validation/exclude_two_bad
```

输出 `validation_report.json` 含每窗口的 baseline vs variant，以及全局 PASS/FAIL。变体只在一个窗口改善就 FAIL（exit code 1）。

注意 `--variant` 的值如果以 `--` 开头，必须用 `--variant=...` 等号写法（避免 argparse 把后面解析成另一个 flag）。

### 已经验证通过的 profile

| profile | 入场 | 出场 | 8mo avg | xwin avg | 推荐场景 |
|---|---|---|---|---|---|
| `default` | 9:30 open | 1d next_close | — | — | 无过滤，原始策略输出 |
| `validated` | 9:30 open | 1d next_close | — | — | 排除 接力低弱转2 + 方向内绿盘低吸前3名（March/April 双窗口验证）|
| `validated_off_main_line` | 9:30 open | 1d next_close | — | — | validated + exclude_main_line=True（旧别名）|
| `validated_v2` | 9:30 open | 1d next_close | +2.82% / 58.9% | — | legacy regime-label adaptive（保 BC）|
| `validated_v3` | 9:30 open | 1d next_close | +3.40% / 56.2% | -0.14% / 46.3% | state-aware adaptive，1d frame，bear 期赔钱 |
| **`validated_v5`** | 9:30 open | **5d max_dd 2%** | **+6.39% / 56.2%** | **+2.27% / 38.9%** | **当前推荐 ship default**。Phase B 多日持仓 + trailing stop。两个 window 都对 v3 +2.4-3.0pp avg。T+1 兼容。 |
| `validated_v6` | 9:30 open | 3d max_dd 0.5% | +6.88% / 47.9% | +3.04% / 23.2% | aggressive 选项。dd=0.5% cross-window 验证为 monotonic 最优，+0.46-0.77pp avg vs v5。**但 win rate 显著低 + 滑点未建模 → 上线前必须 paper trading 1-2 周** |
| `validated_v3_4` | 9:30 open | 1d next_close | +3.14% / 60.3% | — | EXPERIMENTAL，DBR drop + momentum/limitup bonus axes。8mo 实测对 v3 wash → REJECT，留作研究 |

**版本选择指南**：

- 第一次部署 → `validated_v5`（empirically robust 跨 bull/bear，T+1 兼容，最低实操风险）
- 已经跑了 1-2 周 v5 paper trading 验证滑点 → 可以试 `validated_v6` 加 aggressive 优化
- 想回 v3 (1d) 行为 → `--profile validated_v3`
- 中庸折中 → `--profile validated_v5 --max-dd-pct 1.0`（介于 v5 和 v6）

**`validated_v5` / `validated_v6` 关键 caveats**：

- 多日持仓改变所有指标的可比性。老 1d 数据不能直接和 v5/v6 对比
- max_dd 是 trailing stop（peak 回撤 N%），不是 fixed stop loss
- T+1 满足：stop 检查仅作用于 buy_date+1 之后
- `holdDays` 字段记录实际持仓天数（多数 trade ≤ 3 日就触发 stop）

完整对比 + cross-window 数据见 `reports/cross_window_validation_2026-04-26.md` 和 `reports/multi_day_validation_2026-04-26.md`。

---

**`validated_v2` 调优依据**（详见 `reports/strategy_tuning_2025-12_2026-04.md`）：

- 训练集：2025-12 ~ 2026-03（4 个月，158 候选 trades，跨 8 个模式）
- 测试集：2026-04（held-out，17 trades）
- 端到端 `xiaocao backtest validate` 跨 3 窗口全部 PASS（vs default 基线，结构性过滤部分）：

  | window | baseline avg/win | validated_v2 avg/win | Δ avg | Δ win |
  |---|---|---|---|---|
  | Dec25-Jan26 | +1.51% / 50.6% | +1.87% / 52.2% | +0.36% | +1.6pp |
  | Feb-Mar26 | +3.50% / 64.0% | +3.84% / 68.5% | +0.34% | +4.5pp |
  | **Apr26** | +1.51% / 41.2% | **+4.48% / 53.8%** | **+2.97%** | **+12.6pp** |

  开启 adaptive 后 active P&L 进一步收敛到 5 笔 +7.83% win 80%（4 月）。

老的 `validated`（不带 off_mainline）和 `validated_off_main_line` 仍然保留，互不破坏。

## 实盘日常工作流（v5 / v6 推荐 + 持仓监控 + 卖点提醒）

每天三步：盘前推荐 → 集合竞价/9:30 入场 → 盘中监控 → 触发卖点。

### 第一步：盘前推荐（9:25 之后 / 9:30 之前）

```bash
PYTHONPATH=src python3 scripts/live_recommend.py
# 默认 --date today。也可回测：--date 2026-04-21
```

输出：

- stdout 打印 markdown 表格（code / name / mode / 9:30 open 价 / v5 初始 stop / v6 初始 stop / open_pct / flags）
- 文件 `output/live/recommend_YYYY-MM-DD.md` 留档

每只候选股给两条价位线：v5 init stop = open × 0.98，v6 init stop = open × 0.995。这是「买入当日」的初始止损位；持仓后随 peak 上行 stop 同步抬升（trailing stop）。

实操：你看完表格决定买哪些 + 多大仓位 → 9:25 集合竞价下单 → 9:30 fill。**仓位灵活**，脚本只是给候选 + 初始 stop 参考，不强制。

### 第二步：填入持仓记录（9:30 fill 后）

每笔实际买入 append 一行到 `output/live/positions.jsonl`（一行 JSON）：

```jsonl
{"code": "002347.XSHE", "name": "泰尔股份", "entry_date": "2026-04-28", "entry_price": 8.50, "profile": "v6", "shares": 1000, "status": "open"}
```

字段：

- `profile` ∈ `{"v5", "v6"}` — 决定 trailing stop 阈值（v5=2.0%, v6=0.5%）
- `entry_date` / `entry_price` — 实际 fill 价
- `shares` — 仅作记录（脚本不用，给你自己看）
- `status` — `"open"` / `"closed"`（卖出后改 closed 跳过监控）

模板：`output/live/positions.jsonl.example`

### 第三步：盘中监控 + 卖点提醒（9:35-14:55, 每 5-10 分钟）

```bash
PYTHONPATH=src python3 scripts/live_monitor.py
```

每次跑：

1. 读 `positions.jsonl` 所有 `status="open"` 的持仓
2. 拉每只股票从 entry_date+1 到今天的 minute_line
3. 跟踪 entry 后 peak (HIGH) → 计算 current dd_from_peak
4. 若 dd ≥ profile 阈值（v5: 2.0% / v6: 0.5%）→ **触发 SELL alert**

输出：

- stdout 打印每只持仓的 entry/peak/latest/dd/ret 状态行
- 触发卖点时弹 **macOS 通知**（`Glass` 提示音）
- 写入 `output/live/alerts.jsonl` 审计日志（持续累积）

T+1 兼容：entry 当日（today == entry_date）即使 dd 触发也不会推 alert（标 `T1_blocked`）—— A 股不让同日卖。次日才正式生效。

### 自动化建议

最简：手动运行。盘前 1 次 + 盘中每 10 分钟手动一次 `live_monitor.py`。

进阶：crontab（macOS launchd）：

```cron
# 盘前推荐 — 周一到周五 9:26
26 9 * * 1-5 cd /Users/.../xiaocao && PYTHONPATH=src python3 scripts/live_recommend.py >> output/live/cron.log 2>&1

# 盘中监控 — 每 10 分钟（9:35-11:30, 13:00-14:55）
35,45,55 9 * * 1-5  cd /Users/.../xiaocao && PYTHONPATH=src python3 scripts/live_monitor.py >> output/live/cron.log 2>&1
0,10,20,30,40,50 10,11 * * 1-5  cd /Users/.../xiaocao && PYTHONPATH=src python3 scripts/live_monitor.py >> output/live/cron.log 2>&1
0,10,20,30,40,50 13 * * 1-5  cd /Users/.../xiaocao && PYTHONPATH=src python3 scripts/live_monitor.py >> output/live/cron.log 2>&1
0,10,20,30,40,50 14 * * 1-5  cd /Users/.../xiaocao && PYTHONPATH=src python3 scripts/live_monitor.py >> output/live/cron.log 2>&1
```

### v5 vs v6 选择策略（实操）

- **同一只股票可以两个 profile 各开一笔**：positions.jsonl 写两行 entry，`profile` 一行 `v5` 一行 `v6`，监控时分别 trigger
- **保守起步**：先全用 v5（dd=2%），等 paper trading 1-2 周（见 `scripts/paper_trade_v6.py`）验证 v6 滑点 < 0.1% 后再切 v6 或部分混用
- **混合**：一只股票如果你 9:25 集合竞价买了 1000 股记 v5，9:35 看到回撤后又加仓 500 股记 v6 — 两条 position record 独立监控独立卖点

### 实操注意

- `live_monitor.py` 每次跑会拉所有持仓的当日 minute_line（API 调用）。不要 1 分钟跑一次（频繁打 API）。**5-10 分钟一次足够**——A 股一根 1min K 线就是 1 分钟，10 秒级波动不需要追
- T+1 之外其他规则也要遵守（涨停 / ST / 临停等），脚本不感知，**自己识别这些情况手动 override**
- 卖单滑点：脚本算的 dd 是基于「过去某分钟 close」。实际下市价单 fill 价可能更差几个 tick。**v6 的 0.5% 阈值对滑点最敏感**——这正是 paper trading 要验证的（见 `scripts/paper_trade_v6.py`）
- 通知不会替你下单。你看到 alert 后**手动**去券商 app 卖

### 与 paper trading 的关系

| 工具 | 用途 |
|---|---|
| `live_recommend.py` | **每天**用。生成今日候选 + 价位 |
| `live_monitor.py` | **盘中每 5-10 分钟**用。盯持仓，触发卖点提醒 |
| `paper_trade_v6.py log` | **每天 EOD** 用。记录 v6 候选信号 + 理论 stop（不依赖你实际下单） |
| `paper_trade_v6.py replay` | **每周/两周**用。统计 v6 历史滑点（mean/median）→ 决定 v6 是否升级 default |

`paper_trade_v6.py` 与 `live_monitor.py` 互不依赖：前者纯 backtest 验证 v6 dd=0.5% 是否经得起滑点；后者是你实盘 v5/v6 持仓的盯盘。两者并行跑互不影响。

---

## 报告：盘前参考、盘后复盘、通用日报

盘前参考适合开盘前发。它使用最近一个已完成交易日的数据，整理今日需要关注的方向、环境和候选信号：

```bash
xiaocao report premarket --date latest --source api --output reports/premarket/latest.md
```

盘后复盘适合收盘后发。它除了复盘当日环境、方向和策略信号，还会自动找到前一个交易日，把“前一个交易日选出的股票”从前一交易日开盘价持有到当前交易日收盘价，计算收益率：

```bash
xiaocao report afterclose --date latest --source api --output reports/afterclose/latest.md
```

盘后复盘收益率口径：

```text
收益率 = 当前交易日收盘价 / 前一个交易日开盘价 - 1
```

例如 `--date 2026-04-24` 时，会先找到前一个交易日 `2026-04-23`，运行 `2026-04-23` 的策略信号，再用日 K 计算 `2026-04-23 开盘 -> 2026-04-24 收盘` 的表现。

通用日报仍然保留：

```bash
xiaocao report daily --date latest --source api --output reports/latest.md
```

报告包含：

- 信号摘要
- 强方向（报告展示使用 `industry_block_rank model=0` 的连续方向强度口径）
- 强方向大类
- 板块评分
- 动态指数
- 环境分时
- 盘后复盘中的上一交易日信号表现
- 模式结果表

说明：策略内部仍可通过配置里的 `strategy.block_model` 使用更严格的短线重点口径，默认是 `model=1`。这个口径经常只有少数非零方向，适合做策略加持，不适合直接当报告 Top5 展示。

`model` 口径说明见 [docs/api_models.md](docs/api_models.md)。

也可以输出结构化 JSON：

```bash
xiaocao report afterclose --date latest --source api --format json --output output/afterclose.json
```

本地日报只使用本地可用数据：

```bash
xiaocao report daily --source local --date 2024-10-25 --output output/daily_2024-10-25.md
```

## 旧脚本归档

重构前的根目录脚本已经移动到 `legacy/scripts/`，只作为历史参考保留。新的开发和日常使用都应通过 `xiaocao` CLI、`src/xiaocao` 包和 `tests/e2e` 覆盖来推进。

入口映射和维护原则见 [legacy/README.md](legacy/README.md)。

## 配置

复制配置样例：

```bash
cp xiaocao.yaml.example xiaocao.yaml
```

查看当前配置：

```bash
xiaocao config show --format json
```

配置优先级：

```text
CLI 参数 > 环境变量 > 配置文件 > 默认值
```

支持的环境变量：

- `XIAOCAO_BASE_URL`
- `XIAOCAO_TIMEOUT`
- `XIAOCAO_RETRIES`
- `XIAOCAO_CONFIG`
- `XIAOCAO_LOG_LEVEL`

## E2E 测试

Live API e2e 测试会动态选择最近 45 天里的最新交易日，覆盖所有已接入 API、Datasource、策略、日报和输出格式。它不是只测“能不能返回”，还会检查关键字段、日期格式、股票代码格式、数字字段和跨接口一致性。

安装测试依赖：

```bash
python3 -m pip install pytest
```

运行测试：

```bash
PYTHONPATH=src python3 -m pytest tests/e2e -q
```

可选测试环境变量：

- `XIAOCAO_BASE_URL`
- `XIAOCAO_TEST_TIMEOUT`
- `XIAOCAO_TEST_RETRIES`
