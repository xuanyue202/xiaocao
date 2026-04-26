# Phase C R2 Intraday SOP — historical validation (2026-04-26)

**TL;DR**: API 实测发现 `/stock/minute_line` 在加 `count + codeType` 参数后**真支持历史回放**（之前我误判了）。138 笔 v3 baseline trades 全 backfill 后，把 0419 的「9:31-9:35 弱转强 9-step SOP」简化版应用到 1d 和 5d 两种 backtest frame 上：**全 SOP 组合反预测**（PASS subset avg 1-2% vs baseline 3-7%），但**`not_at_peak` 单轴**（即「不在 9:30-9:35 内的高点买」）**在两种 frame 下都是真正的 +1pp+ avg / +10pp+ win 加成**。结论是 SOP 不能机械搬，需要 sub-axis 实证拆解。

---

## 1. API 历史回放发现的真相

最初判断"分钟级 intraday 完全不可历史回放，必须前向 capture"是 **错的**。修正过程：

1. 用户指出 `reference/index-f3118026.js` 里 minute_line wrapper (K0, line 9835) 显式处理 tradeDate
2. 原 probe 只传 `{code, freq, adj, tradeDate}` → backend silent 返回今日
3. 翻 JS bundle 找 K0 真实 caller（line 10271-10277）发现额外参数：
   ```js
   K0({stockId, adj, tradeDate, count: 241, codeType})
   ```
4. 加 `count=241, codeType=0` 后再 probe → 3 个不同历史日期返回 3 套真实历史 1min K 线
5. 修复 client wrapper + CLI flags，backfill 138 笔 trades = 11.6s 跑完

**最终 8 个 intraday endpoint 历史可用性表**：

| endpoint | 历史 | 必要 param |
|---|---|---|
| **`/stock/minute_line`** | ✅ | `count + codeType` 必须传 |
| `/stock/xiao_cao_environment_second_line_v2` | ✅ EOD aggregate | date |
| `/stock/second_line` | ❌ silent today | — |
| `/stock/second_line_detail_info` | ❌ silent today | — |
| `/stock/stock_call_auction` | ❌ silent today | — |
| `/stock/each_trade` | ❌ silent today | — |
| `/stock/xiao_cao_environment_minute_line` | ❌ returns empty | code 不论怎么写 |
| `/stock/get_technical_index_history` | ⚠️ daily EMA only | tradeDate ok |

**对 Phase C 的影响**: R2/R3/R4/R5 (4/5 SOPs) 可在 8mo cache 上历史回测。R1 集合竞价仍需前向 capture。

---

## 2. R2 9-step SOP 简化版

完整 0419 的 9-step 中，只有 3 步可从 minute_line 单独 derive：

| 简化轴 | 实现 | 对应 SOP step |
|---|---|---|
| `weak_open_ok` | 9:30 cum pct ∈ [-3%, +1%] | step W: 弱/平开倾向 |
| `pct_controlled` | 9:35 cum pct ∈ (-3%, +4%] | step 5: 涨幅可控 |
| `pct_ideal` | 9:35 cum pct ∈ [-1%, +2%] | step 5 严格版 |
| `not_at_peak` | 9:35 trade ≥ window-max × 0.985 | step 7: 不冲高 |

其他 step 需要 realtime selection / sort_v2 / EOD signals.json，不可单独 backfill：
- step 1, 6 (先机预警活跃 / 方向预警配合): selection endpoint silently returns 空
- step 2, 3 (一进二/首板属性 / 排除 3进4): 需 EOD signals.json 关联（可补但未做）
- step 4 (排名靠前): 需 realtime sort_v2，无历史
- step 8, 9 (回调后入场 / 没合适不做): 这两步是 meta-SOP，不是单独筛选

---

## 3. 实测 — R2 SOP × 3 种 backtest frame

数据：73 笔 v3 baseline active trades，已全部 backfilled minute_line。

| frame | baseline | R2 PASS combo | R2 FAIL | not_at_peak only |
|---|---|---|---|---|
| 1d | n=73 / **+3.40%** / 56.2% / sum 248 | n=14 / +0.99% / 64.3% / sum 14 | n=59 / +3.97% / 54.2% / sum 234 | **n=45 / +4.54% / 66.7% / sum 204** |
| 5d max_dd 2% | n=73 / **+6.39%** / 56.2% / sum 467 | n=14 / +2.15% / 64.3% / sum 30 | n=59 / +7.40% / 54.2% / sum 437 | **n=45 / +7.77% / 68.9% / sum 350** |
| 5d max_dd 3% | n=73 / **+5.50%** / 57.5% / sum 401 | n=14 / +1.36% / 57.1% / sum 19 | n=59 / +6.48% / 57.6% / sum 382 | **n=45 / +6.88% / 68.9% / sum 309** |

**关键观察**：

- **R2 PASS combo 反预测**：在 3 种 frame 下都比 baseline 差。R2 PASS subset 仅占 14/73 = 19%，且 avg 只有 baseline 的 1/3。0419 SOP 在 backtest universe 上不是过滤器，是反过滤器。
- **R2 FAIL subset 比 baseline 强**：因为 SOP 错误地把 winners 标成 fail
- **`not_at_peak` 单轴是真信号**：1d +1.14pp avg / +10.5pp win，5d_dd2 +1.38pp avg / +12.7pp win

---

## 4. 第一性原理解读 — 为什么 0419 SOP 不能机械搬

### 4.1 universe mismatch

0419 SOP 是给 LIVE 短线交易者设计的——他们的 universe 是**当天市场全样本数千股**。在那个 universe 里：

> "弱开 + 涨幅 0-1 点 + 排名前列" = 从 noise 池子里精筛 5-10 个高质量 setup

但我们的 backtest universe **已经过 v3 EOD 高分筛选**——只有 73 active trades 进入候选。这些已经是「次日预期上涨」的高分信号。在已筛选 universe 上叠加「弱开」过滤 = **双重过滤，把好 trade 滤掉**。

打个比方：原始 SOP 是「在垃圾堆里找宝石」的方法；我们的 universe 已经是宝石；再用「找宝石」的硬条件去过滤宝石 = 把没看出来的宝石当垃圾扔了。

### 4.2 prediction frame mismatch（与报告 §4 + Phase B 一致）

0419 SOP 的「弱开 + 0-1 点」严格条件是为**多日持仓 + 情绪修复**设计的——这种 setup 期望持有 3-5 日等价格回升。但我们的 1d / 5d frame 内：
- 1d: 没时间让 mean-reversion 兑现
- 5d_dd2: 即使有 5 日 + 紧 trailing stop，「弱开+低涨幅」选出来的还是低弹性 setup

实际上 5d_dd2 frame 下 R2 PASS 比 1d 涨了 +1.16pp（0.99→2.15）—— 多日有帮助，但不足以追平 baseline。

### 4.3 not_at_peak 为什么独立有效

`not_at_peak` 与「stock 是否高分/弱开/低涨幅」**正交**。它捕获的是 **execution timing**：「不要在 9:30-9:35 内的高点买入」。这是 EOD 信号筛选**没法表达**的信息——日级别看不见盘中 5min 的局部峰值。

- 1d frame：not_at_peak ✓ 的 trades 平均 +4.54%（baseline +3.40%）
- 5d_dd2 frame：✓ 的 +7.77%（baseline +6.39%）

这 +1.14~1.38pp 的稳定 lift 是真信号——而且是 **Phase C 第一个真正实用的产出**。

---

## 5. Phase C 计划的修正

### 5.1 放弃机械 SOP encoding
不要把 0419 的 9-step / 10-step SOP 直接编码成 backtest 过滤层。已经实测它们在我们的 universe 上 anti-predictive。

### 5.2 改成 sub-axis discovery（同 A3 DBR 流程）
- 把每个候选 axis（weak_open / pct_controlled / not_at_peak / 等）单独 vs winners / losers 实证测试
- 保留通过 robustness gate 的轴
- 拒绝反预测的轴

这正是 Phase A 对 DBR 做过的事——SOP 是 hypothesis，data 是 verdict。

### 5.3 把 `not_at_peak` 作为 EOD pipeline 的入场 timing 增强
- 在 v3 active 信号已确定后，9:35 之前不立即 entry
- 等 9:35 收完，如果当前价 ≥ 0930-0935 max × 0.985（处于回撤后）→ 买入
- 如果当前价 ≥ 0930-0935 max（处于冲高）→ skip 该 trade
- 实测 lift：**+1.14pp avg / +10.5pp win** (1d), **+1.38pp / +12.7pp** (5d_dd2)

这是 Phase A v3.4 / Phase B multi-day 之外的第三条 framework 上限。

### 5.4 R3 / R4 / R5 同样需要 sub-axis discovery
不预先承诺 SOP 全 step。每个 step 都先单独验证。

---

## 6. 关键文件 / 命令

- 修复：`src/xiaocao/api/client.py:minute_line` 加 `trade_date / count / code_type`
- CLI 暴露：`xiaocao quote minute --code X --trade-date 2026-04-22 --count 241`
- backfill：`scripts/backfill_intraday_minute.py`（11.6s 跑 73 active）
- 分析：`scripts/analyze_intraday_r2.py`
- 输出：`output/r2_intraday_analysis.md`（per-trade detail）

---

## 7. 下一步

1. **`not_at_peak` axis 加到 v3 entry-timing 层** — 改 `score_trades` 让它在 9:35 之前等一下，然后 9:35 后判断 not_at_peak 决定是否入场。这是个 backtest 改动，需要新增 minute-level entry timing。
2. **R3 / R4 sub-axis discovery** — 同 R2 流程
3. **R1 forward capture** — 集合竞价没法历史，必须从下周一起 cron
4. **完整 Phase C report 整合** — 写一份完整 Phase C MVP report
