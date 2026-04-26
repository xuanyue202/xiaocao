## 背景方法论
读reference/experience/下所有的markdown，提炼小草短线底层逻辑。作为后续调优的先验经验和灵魂方向。

## 任务一句话

用 **2025-12 ~ 2026-03**（4 个月）做参数拟合训练集，**2026-04** 做held-out 测试集，对 xiaocao 策略系统的可调参数做严格的 train/test 优化。同事优化cache机制， 第一次跑 backtest 把所有数据写进 SQLite cache，之后所有分析、grid search、replay 不再发 API 请求——只读 cache， 且无副作用。

---

## 上下文

### 项目是什么

`/Users/bytedance/coding/xiaocao` 是一个基于 `reference/index-f3118026.js`（一个 A 股短线分析平台的前端 bundle）反向工程出来的 CLI。它包装了若干 `/stock/...` API、实现了一套基于"小草"短线/低吸/接力模式的策略生成器、并配套了 backtest 框架。

策略哲学全文在 `reference/experience/*.md`（7 篇直播提炼），核心：
- **道**：先判环境再选模式（regime → mode 切换）
- **法**：主线识别（连续多日 top-K 出现的方向）、大票单独排名、盈亏比 > 涨停率
- **术**：低开低位卡位、9:31-9:35 黄金窗口、短线只做弱转强套利

### 当前已落地的 B 档结构

```
xiaocao
├─ L1 regime classifier (src/xiaocao/strategy/regime.py)
│   - 输入: market_overview + 大票开盘均价
│   - 输出: bear / divergence / neutral / recovery / trend_continuing / trend_strong
│   - live `strategy run` 才有意义；backtest 因为 market_overview 是 live state 而留空
├─ L2 mainline tracker (src/xiaocao/strategy/mainline.py)
│   - 滚动 N 天 block_rank top-K 求"老面孔"
│   - 默认 N=3, K=5, min_hits=3
├─ L3 bigcap pool (src/xiaocao/strategy/bigcap.py)
│   - stock_info 按 tradableAShare 排序，top 20% 为大票
├─ L4 quality gates (在 strategy/runner.py 里)
│   - max_open_pct (默认 6.0): openPctChange ≥ cap → shadow
│   - exclude_modes: 用户硬封禁的模式 → shadow
│   - regime_gate / require_main_line / exclude_main_line: 保留为可选 hard drop
├─ L5 adaptive mode tagging (src/xiaocao/strategy/adaptive.py)
│   - **核心**: 每条信号都生成 + 评分 + 写 mode_history,
│     按 (mode, asof) 在 5/10/20 个交易日的 rolling (n, avg) 决定 active vs shadow
│   - 当前默认: n_min_by_window={5:1, 10:2, 20:3}, avg_threshold_by_window={5:-5, 10:-3, 20:-2}
│   - 4 层 fallback: Tier1 双窗口确认 → Tier2 单窗口 → Tier3 20d 兜底 → Tier4 dormant shadow
└─ 反过拟合: backtest validate 跨多窗口必须都改善才 PASS
```

### Active vs Shadow（关键设计）

**adaptive 不丢信号**。每条候选信号都：
- 生成、按"次日开盘买、收盘卖"的 1 日持仓打分
- outcome 写进 SQLite `mode_history` 表
- 通过 `adaptive_active = True/False` 标签区分

  - `adaptive_active = True` → **active**：计入用户"真实"P&L
  - `adaptive_active = False` → **shadow**：仅参考，不计入 P&L，但 outcome 仍记录

`adaptive_active` 是 **sticky False**：上游任一 gate 标 False 后下游只能 append reason，不能 re-enable。

### Validated profile

`STRATEGY_PROFILES["validated"]` 在 `src/xiaocao/strategy/runner.py`，唯一硬规则：

```python
"exclude_modes": ["接力低弱转2", "方向内绿盘低吸前3名"]
```

跨 March + April 双窗口 PASS（验证记录在 `reports/strategy_validation_2026-03_2026-04.md`）。

---

## 上一轮失败：为什么需要更长训练集

之前的 grid search (`scripts/tune_adaptive.py`) 跨 1620 个 (n_min, threshold) 组合：

| 配置 | March active | April active |
|---|---|---|
| (1,2,3 \| -5,-3,-2) 当前默认 | **1 trade** | 7 / +7.03% / 71% |
| (2,1,2 \| -3,-2,-1) | **1 trade** | 5 / +7.83% / 80% |
| 全 1620 个配置 | **几乎都是 1 trade** | 5-7 between |

**结论**：March 跨所有 config 只产出 ≤ 1 个 active signal。原因是 backtest 冷启动时 mode_history 空，前 ~15 个交易日全是 Tier 4 dormant shadow。March 实际上**无法用作训练集**——所有 config 都在 March 长一样。

39 个交易日 / 31 笔 trades 也太少做严格 train/test 切分（按 0419 doc 的"真实的谎言"标准）。

### 为什么 4 个月 warmup 能解决

如果 **2025-12-01 ~ 2026-03-31** 全部跑过，到 2026-04-01 时 mode_history 已经累积 ~80 个交易日的数据。每个模式都该有足够样本，rolling 5/10/20d 窗口大部分时间 informative。Adaptive 真正在每天做实时判断，调参才有意义。

---

## 你（下一个 agent）要做的事

### 阶段 1: 数据缓存预热（一次 API 调用，永久受益）

**关键约束**：第一次 backtest 跑完后，SQLite cache (`output/.cache/xiaocao.db`) 已经包含了所有需要的历史 API 数据。后续所有分析、grid search、replay **必须**从 cache 直接读，**不再触碰网络**。如果某次分析需要新数据，先把它跑一遍 backtest 写入 cache，再分析。

```bash
# 一次性跑完整 5 个月 backtest（冷缓存，预计 3-5 分钟）
xiaocao backtest run \
  --start 2025-12-01 --end 2026-04-30 \
  --workers 6 \
  --output output/xiaocao_5month_seed
```

跑完后验证 cache 完整：
```python
from xiaocao.api.cache import SQLiteCache
c = SQLiteCache('output/.cache/xiaocao.db')
for r in c.stats():
    print(r)  # 应该看到几千行 historical=True 的记录
```

`mode_history` 也会被填上 ~5 个月的 trade outcomes。

### 阶段 2: train/test 切分

- **训练集**: 2025-12-01 ~ 2026-03-31（4 个月，约 80 个交易日）
- **测试集**: 2026-04-01 ~ 2026-04-30（hold-out，约 17 个交易日）

参数拟合**绝对不能看**测试集数据。fitting 时只用训练集 trades；测试集只在 fitting 完成后跑一次 sanity check。

### 阶段 3: 调参类别（按 ROI 排序）

下面是值得拟合的全部参数类别。按你的判断挑 1-3 个最值得做的开始（每个类别独立 train/test）：

#### A. Adaptive (n_min, avg_threshold) — **优先**

文件：`src/xiaocao/strategy/adaptive.py`

可调：
- `DEFAULT_N_MIN_BY_WINDOW`: dict[window→int]，每个窗口要求的最少 informative 样本
- `DEFAULT_AVG_THRESHOLD_BY_WINDOW`: dict[window→float]，每个窗口的 "bad" 阈值
- 是否引入 4 个或更多窗口（如 3d / 5d / 10d / 20d / 60d）
- 是否引入 win_rate 维度（不只看 avg）

当前默认: `(1,2,3 | -5,-3,-2)`，t-stat-like 推导，但只在 39 天 31 笔上验证过，欠拟合风险高。

参考脚本：`scripts/tune_adaptive.py`（基于 cache 直接读 + grid search）。

#### B. Mainline (window, topk, min_hits)

文件：`src/xiaocao/strategy/mainline.py`

可调：
- `mainline_window`: 滚动天数 (默认 3)
- `mainline_topk`: top-K 阈值 (默认 5)
- `mainline_min_hits`: 命中天数阈值 (默认 = window)

当前观察：在 March-April 数据里，**off-mainline 信号反而比 on-mainline 表现好**（baseline +3.7%/win 62% vs +(-5.5)%/17%），这不直觉但符合 0413-A 的"短线找新轮动而非昨日老主线"。可调：
- 把 main-line 滚动定义反过来，找 NOT 持续在 top-K 的方向
- 把 ZHBK (中信行业) 改成 BKDL (大类) 做 mainline （`excIndustryCode` vs `blockCategoryCodeList`）

#### C. Quality gate `max_open_pct`

文件：`src/xiaocao/strategy/runner.py` `MAX_OPEN_PCT_CHANGE = 6.0`

经验：
- 0419 doc："最喜欢 0-1 个点，2 个点勉强接受，更高就不舒服"
- baseline 数据：openPctChange ≥ 6 区间 win 0%、avg -9.4%（很烂）
- 但 4-6 区间反而 win 60%/+4.92%（看似好）

可调：cap 值（4? 5? 6?），或区分模式（接力类 cap=3，低吸类 cap=5）

#### D. Regime classifier 阈值

文件：`src/xiaocao/strategy/regime.py`

可调：每个 regime 的边界条件（涨多/跌多比例、limit_up/down 计数阈值）。

**注意**：`market_overview` 是 live state 不带日期，所以 backtest 里 regime 永远空。要在历史数据上调 regime，需要从其他 endpoint 反推（比如 block_rank 的 prePctChangeRate 分布、stock_info 数量等）。这是个**额外工程任务**，不是简单调参。

#### E. Strategy rules 内部阈值（最敏感）

文件：`src/xiaocao/strategy/rules.py`

```python
SUPER_JW = 300       # 超级竞王分数
STRONG_JW = 200      # 强竞王
QUALIFIED_JW = 150   # 合格竞王
```

每个 mode 的命中条件硬编码了这些阈值。基于 baseline 数据：
- xcjw ≥ 300: avg +2.59%/win 50% (n=10)
- xcjw 100-300: avg -1.23%/win 40% (n=20)

可调：把这些阈值用 train/test 拟合，可能能砍掉很多差信号。但**改这些会改变信号集本身**，不是 active/shadow 标签，所以验证时要小心：跑 backtest validate 跨多窗口确认。

#### F. `direction_sort_key` / `pool_sort_key` 选择

文件：`src/xiaocao/strategy/runner.py` `STRATEGY_PROFILES`

当前默认 direction_sort_key="directionCjs" (47)。可选：directionCjsV2 (54), xiaocaoCJS (40), xcjwV2 (48), 等。

#### G. `--exclude-modes` 列表扩充

当前 validated profile 排除了 2 个模式。可能还有其他系统性差的模式没识别——5 个月数据里也许会暴露更多。

#### H. Bigcap pool 阈值

文件：`src/xiaocao/strategy/bigcap.py`

`top_pct` 默认 0.2。可调，但首先需要看 bigcap_summary 是否反映"大票表现不一样"——目前数据上 big_cap +0.59% vs small_cap +2.33%（小票更好），所以 bigcap-aware ranking 可能用反方向（不要大票）。

---

## 工程约束（必读）

1. **零网络重复**：第一次跑 5-month backtest 之后，cache 完整。所有后续分析（grid search、replay、统计）**必须**从 SQLite 直接读：
   - API 数据：`SQLiteCache.get(endpoint, payload)` 或 raw SQL on `api_cache` 表
   - Trade 数据：raw SQL on `mode_history` 表
   - 不再调 `XiaocaoClient` 或 `run_backtest`（除非确认要新数据，且新数据会进 cache）

2. **不要破坏现有 108 tests**：所有 tuning 应通过新增模块实现，调整默认值前先跑 `pytest tests/ --ignore=tests/e2e -q`。

3. **反过拟合护栏**：
   - 任何"调出来"的 magic number 必须在 train + test 上**都**显著优于当前默认
   - 跨 train 的 sub-window（如 12 月 vs 1 月 vs 2 月 vs 3 月）也要看一致性
   - 用 `xiaocao backtest validate --windows` 工具，metric 用 `avg`，要求 **变体在 BOTH 子窗口都改善**

4. **不要碰 production endpoints**：所有调用走 cache，`--no-cache` 不要用。

---

## 关键文件索引

| 用途 | 文件 |
|---|---|
| Adaptive 决策 | `src/xiaocao/strategy/adaptive.py` |
| 策略 runner（quality gates 集成点） | `src/xiaocao/strategy/runner.py` |
| Rule 阈值 | `src/xiaocao/strategy/rules.py` |
| Mainline / Bigcap / Regime | `src/xiaocao/strategy/{mainline,bigcap,regime}.py` |
| Backtest 引擎 | `src/xiaocao/backtest.py` |
| SQLite cache + mode_history | `src/xiaocao/api/cache.py` |
| 已有 grid search 例子 | `scripts/tune_adaptive.py` |
| Inventory 文档 | `docs/reference_api_inventory.md`（自动生成） |
| Param catalog | `docs/api_parameter_catalog.md` |
| 已有 March/April 报告 | `reports/strategy_validation_2026-03_2026-04.md` |
| 直播策略哲学 | `reference/experience/*.md`（7 篇必读） |

---

## 推荐执行顺序

1. **先把 5 个月 cache 跑出来**（一次性 API 调用）：
   ```bash
   xiaocao backtest run --start 2025-12-01 --end 2026-04-30 --workers 6 --output output/seed_5mo
   ```
   时间预估：5 分钟以内（workers=6 + 历史数据缓存）

2. **审计 cache**: 确认每个 endpoint 都有几千条 historical=True 记录，mode_history 表有 100+ 笔 trades。

3. **写 train/test split 脚本**：基于 cache 重放 December-March 全部信号 + 计算 metrics。Hold out April。

4. **优先调 A (adaptive params) 和 C (max_open_pct)**——这两个是最可能在更长训练集上"调出来"的。E (rules 阈值) 改动大但 ROI 高，留到最后。

5. **每个调好的参数都过 `backtest validate` 多窗口验证**，写报告。

6. **更新 `STRATEGY_PROFILES`**，加 `validated_v2` profile 包含调好的所有参数。

---

## 输出（你应该交付）

1. `reports/strategy_tuning_2025-12_2026-04.md`：详细描述每个调参类别的方法、grid 范围、train/test 结果、是否采纳
2. `STRATEGY_PROFILES["validated_v2"]`：拟合后的新 profile（如果 train + test 都验证通过）
3. `scripts/tune_*.py`：每个调参类别一个 script，可重放
4. 更新过的 `tests/test_*.py`：覆盖新增的逻辑
5. README 中 Adaptive 章节按新参数同步

---

## 不要做的事

- ❌ 不要重新设计 active/shadow 框架（这一层稳定了，调参基于它就行）
- ❌ 不要为了 "看起来更好" 而过拟合 single window（必须跨子窗口一致）
- ❌ 不要追求 "100% 胜率"（小样本骗人；50-65% win 在量化策略里就很好了）
- ❌ 不要碰已经 PASS 的 `validated` profile（用作 baseline 对比）
- ❌ 不要重复发 API（cache 已经够用，浪费配额是大忌）

---

## 联系

完成后向用户汇报：
- 哪些参数类别调过、结论如何
- 尽量提升默认adaptive性能，profile总会倾向于过拟合风险
- `validated_v2` 比 `validated` 在 April 测试集上提升多少（avg / win / n）
- 哪些类别尝试过但 train/test 不一致（reject）
- 任何遇到的 cache schema 或 backtest 工具问题
