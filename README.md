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

# 在股票池或自定义股票列表中排序
xiaocao data sort --date latest --from-pool dixi --sort-id 40 --format table
xiaocao data sort --date latest --stock-file stocks.json --sort-id 38 --format csv --output output/sorted.csv

# 个股小草指数
xiaocao index stock --date latest --codes 688807.XSHG,301050.XSHE --format json
xiaocao index stock --date latest --from-pool dixi --format csv --output output/dixi_index.csv

# 小草动态指数
xiaocao index dynamic --date latest --index-type 0 --format table
```

### 板块、方向和环境

```bash
xiaocao block rank --date latest --model 1 --format table
xiaocao block category-rank --date latest --model 0 --format table
xiaocao block score --date latest --format json
xiaocao block stocks --date latest --block-code 980338.ZHBK --format json
xiaocao block stocks --date latest --category-code 000028.BKDL --format json

xiaocao market environment --date latest --format json
xiaocao market environment --date latest --codes 9A0001,9A0002,9B0001 --format table
```

### 兼容行情入口

`market` 下保留了原始 API 语义更明显的兼容入口；新脚本优先使用 `quote` 查询普通行情，使用 `market environment` 查询小草环境分时。

```bash
xiaocao market second-line --codes 000001.XSHG,399001.XSHE --format json
xiaocao market second-line-detail --codes 000001.XSHG,399001.XSHE --format table
xiaocao market minute-line --code 603520.XSHG --freq 1min --adj bfq --format json
xiaocao market kline --code 000001.XSHG --count 60 --freq D --adj qfq --format table
xiaocao market auction --code 688808.XSHG --date latest --format json
```

### 策略和报告

```bash
xiaocao strategy run --date latest --source api --format table
xiaocao strategy run --date latest --modes jieli,dixi --sort-id 40 --format csv --output output/signals.csv
xiaocao strategy run --source local --date 2024-10-25 --format table

xiaocao report premarket --date latest --source api --output reports/premarket/latest.md
xiaocao report afterclose --date latest --source api --output reports/afterclose/latest.md
xiaocao report daily --date latest --source api --format json --output output/daily.json
```

### 配置与调试

```bash
xiaocao config show --format json
PYTHONPATH=src python3 -m pytest tests/e2e -q
```

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
xiaocao data sort --date latest --from-pool dixi --sort-id 40 --format table
xiaocao data sort --date latest --stock-file stocks.json --sort-id 38 --format csv --output output/sorted.csv
```

`--source local` 可读取本地 `results/*_detail.csv`：

```bash
xiaocao data pool --source local --date 2024-10-25 --group dixi
```

本地排序当前支持常用映射：

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
xiaocao index dynamic --date latest --index-type 0 --format table
xiaocao index dynamic --date 2026-04-24 --index-type 0 --format json
```

## 板块与方向

```bash
xiaocao block rank --date latest --model 1 --format table
xiaocao block category-rank --date latest --model 0 --format table
xiaocao block score --date latest --format json
xiaocao block stocks --date latest --block-code 980338.ZHBK --format json
xiaocao block stocks --date latest --category-code 000028.BKDL --format json
```

`model` 口径目前没有官方枚举文档。CLI 的当前约定是：报告展示使用 `model=0` 的全量强度排行，策略加持默认使用 `model=1` 的短线重点/精选口径。更详细的推理和证据见 [docs/api_models.md](docs/api_models.md)。

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
xiaocao market second-line-detail --codes 000001.XSHG,399001.XSHE,399006.XSHE --format table
xiaocao market minute-line --code 603520.XSHG --freq 1min --adj bfq --format json
xiaocao market kline --code 300422.XSHE --count 20 --freq D --adj qfq --format table
xiaocao market kline --codes 300750.XSHE,000001.XSHG --count 20 --freq D --adj qfq --format csv
xiaocao market auction --code 688808.XSHG --date latest --format json
xiaocao market environment --date latest --format json
xiaocao market environment --date latest --codes 9A0001,9A0002,9B0001 --format table
```

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
xiaocao strategy run --date latest --modes direction --sort-id 40
```

本地历史数据回放：

```bash
xiaocao strategy run --source local --date 2024-10-25 --format table
xiaocao strategy run --source local --date 2024-10-25 --modes direction --sort-id 40
```

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
