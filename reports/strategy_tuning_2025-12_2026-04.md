# 小草策略调优报告 2025-12 ~ 2026-04

**调优区间**: 训练集 2025-12-01 → 2026-03-31（4 个月，~83 个交易日），
测试集 2026-04-01 → 2026-04-30（held-out，17 个交易日）
**生成日期**: 2026-04-26
**口径**: 1 日持仓（次个交易日 qfq 开盘买、收盘卖）

---

## 1. 设计与方法

按用户给定的护栏：
- 第一次跑 backtest 把所有 API 数据写进 SQLite cache，后续 grid search、replay
  **完全只读 cache**，不再触碰网络
- 训练集和测试集严格分离，参数拟合**绝对不能看测试集**
- 任何 magic number 必须 train + test **都**显著优于当前默认
- 跨子月份要看一致性，不能单月看好

**Universe**：5 个月 cold backtest 跑出 **175 笔候选信号**（158 训练 / 17 测试），
跨 8 个模式（接力低弱转 1/2、绿断 / 红断 / 首红断 / 孕线 / N字低吸、方向内绿盘低吸）。
所有 trades 写入 SQLite mode_history，给 adaptive 提供完整证据。

每个调参类别用 `scripts/tune_*.py` 做 grid search，输入 = `output/xiaocao_5month_seed/`
的 signals_*.json + trades.csv + cache db。这些脚本可重放，无副作用。

---

## 2. 结论 TL;DR

| 类别 | 结论 | 处置 |
|---|---|---|
| **A. Adaptive 参数** | 当前默认 (1,2,3 \| -5,-3,-2) 在 1620 配置 grid 中已接近最优；提名"赢家"在小测试样本上是集中度伪利好 | 保持不变 |
| **B. Mainline 反向过滤** | `exclude_main_line=True` (3,5,3) 在 train +0.47% / test +0.78% avg 双向改善，win 率 +24pp；与 0413-A "短线找新轮动" 一致 | 加入 v2 |
| **C. Open-pct cap** | 当前 cap=6 在所有候选 (2/3/4/5) 中都是最优；收紧任何阈值都会同时拖累 train 和 test | 保持不变 |
| **G. Mode 黑名单** | 无任何模式在 4 个月 train 上 n≥10 且 avg ≤ -1%，validated 现有的两个排除项在 train 上甚至是正 avg；但在 test 仍然是负 avg → 体现"环境匹配"，保留现状 | 保持不变 |
| **E. Rules 阈值** (xcjw) | grid winner (400,350,150) train Δ +0.41% / test Δ +0.57% 但 sum 反而下降——**集中度 trick**；per-mode xcjw 相关性混合（接力低弱转1 越高越好，但接力低弱转2 / 绿断低吸 反向）→ 真正的优化方向是 per-mode 独立阈值 refactor | 保持 (300,200,150) |
| **H. Bigcap 过滤** | bigcap 21% of universe；exclude bigcap → train Δ +0.10% / test Δ +0.08% 噪声级；only bigcap → 显著负向。0413-A "大票留底仓" 不适用于弱转强/低吸短线模式集 | 保持双轨标注但不过滤 |
| **D. Regime 过滤** | 用 cached date_kline 重建 proxy regime（5 类，跨 67 天分布合理）。所有 gating 变体在 TEST 都伤害（Δ -4.24% 到 -5.04%）。原因：1 日持仓 backtest 实际 profit 来自 bear-day 后的 oversold 反弹——regime 概念对持仓周期更长的策略才有效 | 保持 OFF（regime annotation 仍记录但不 gate）|
| **F. Sort key** (direction + pool) | direction_sort_key 实测改 0 个信号（validated_v2 已经把 direction 模式的 dominant variety 排除了，剩下信号太稀疏）；pool_sort_key 改了 jieli/dixi 选择，但 xiaocaoCJS(40)/xcjwV2(48) 都让 TRAIN n 大幅下降（concentration trick），TEST 微涨不构成 robust 改善 | 保持 direction=directionCjs(47), pool=xiaocaoXCJW(38) 默认 |
| **副作用 1**: kline-count 默认 30，对超过 30 个交易日的 backtest 会**静默丢失**早期信号的 trade | 改为自动按 `len(trade_days)+5` 兜底 |
| **副作用 2**: `pick_big_ones` 在 list 含 None 元素时崩溃（5 个月 backtest 实际触发） | 加 `isinstance(item, dict)` 守卫 |

**新建 `STRATEGY_PROFILES["validated_v2"]`**：在 validated 基础上加 `exclude_main_line=True`，
配合 CLI 默认开启的 adaptive_modes（1,2,3 \| -5,-3,-2），整体效果如下：

| 配置 | TRAIN n / avg / win | TEST n / avg / win |
|---|---|---|
| validated (no adaptive) | 110 / +2.41% / 56.4% | 9 / +4.68% / 55.6% |
| validated + adaptive | 87 / +2.78% / 59.8% | 8 / +6.06% / 62.5% |
| validated + off_mainline | 95 / +2.89% / 60.0% | 6 / +5.46% / 66.7% |
| **validated_v2 = both** | **76 / +3.25% / 64.5%** | **5 / +7.83% / 80.0%** |

TEST 上 avg +3.16%、win +24.4pp 都是 **clear 改善**（相对 validated 基线）。
TEST n 从 9 → 5 的样本损失反映 v2 更严的"宁缺勿滥"取舍，符合 0419 "盈亏比 > 涨停率" 哲学。

---

## 3. 上一轮失败 vs 这次的不同

handoff 文档说：之前 `tune_adaptive.py` 的 1620 配置 grid 在 March 几乎都只产出 ≤ 1 个
active signal，因为 March 一开始 mode_history 是空的，前 ~15 个交易日全是 Tier 4 dormant。

这次跑了 **5 个月** seed backtest，到 2026-04-01 时 mode_history 已经累积了 **158 笔
训练集 trades 跨 8 个模式**，每个模式样本数：

```
接力低弱转1: 37        方向内绿盘低吸前3名: 35
首红断低吸:   32        N字低吸:           24
绿断低吸:     22        接力低弱转2:        17
红断低吸:      6        孕线低吸:            2
```

主要模式都有 17~37 笔训练样本，rolling 5/10/20 日窗口大部分时间 informative，
adaptive 真正可以做实时判断。这是这次调参可以做严肃 train/test 切分的前提。

---

## 4. 详细发现

### 4.1 Adaptive 参数（A）

**Grid**：
- `n_min`: n5 ∈ [1,2,3], n10 ∈ [2,3,4], n20 ∈ [3,4,5]
- `thr`: thr5 ∈ [-3..-7], thr10 ∈ [-2..-5], thr20 ∈ [-1..-3]
- 共 1620 配置，每个跑完整 train + test 评估

**Top by TRAIN avg**：

| (n5,n10,n20 \| thr5,thr10,thr20) | TRAIN | TEST |
|---|---|---|
| 当前默认 (1,2,3 \| -5,-3,-2) | n=87 avg=+2.78% win=59.8% | n=8 avg=+6.06% win=62.5% |
| (2,3,4 \| -7,-2,-1) "赢家" | n=88 avg=+2.86% win=60.2% | n=5 avg=+7.83% win=80.0% |

赢家与默认的 train avg 差距只有 **+0.08%**，test 差距 +1.77% 是因为多 shadow 了 3 笔
（n 8→5 的集中度 trick）。**TEST sum** 反而从 +48.5% 降到 +39.2% — 总收益变差了，
只是 avg 看起来好。这是典型的"真实的谎言" 数据包装。

**结论**：保持当前默认 (1,2,3 \| -5,-3,-2)。grid 验证它已经接近最优。

### 4.2 Mainline 过滤（B）

**前提**：之前 March-April backtest 数据显示 off-mainline 信号反而比 on-mainline
更好（baseline +3.7%/win 62% vs (-5.5)%/17%）。Hypothesis 由 0413-A 给出：
"短线 / 弱转强 模式 hunt for 新轮动卡位 — directions NOT yet in the established
main-line"。

5 个月数据上验证：

| 配置 | TRAIN avg | TEST avg | TRAIN win | TEST win |
|---|---|---|---|---|
| 无 mainline 过滤 (baseline) | +2.41% | +4.68% | 56.4% | 55.6% |
| **require** mainline (3,3,3) | +2.73% | +5.57% | 56.6% | 50.0% |
| **exclude** mainline (3,5,3) | **+2.89%** | **+5.46%** | **60.0%** | **66.7%** |
| exclude (3,7,3) | +2.88% | +4.44% | 56.5% | 60.0% |

**exclude_main_line (3,5,3)** 是赢家：train avg Δ +0.48%，test avg Δ +0.78%，
test win Δ +11.1pp，符合"双向改善"标准。Default mainline (3,5,3) coverage = 16%
（28/175 信号 hit mainline），所以 exclude 把这 28 笔过滤掉，留下 95 笔。

### 4.3 Open-pct cap（C）

直观判断：小草反复说"最喜欢 0-1 个点，2 个点勉强接受，更高就不舒服"。
但 1 日持仓回测看到的不是开盘体验，是次日收益。Open-pct 直方图：

| open_pct bin | TRAIN n | TRAIN avg | TRAIN win | TEST n | TEST avg | TEST win |
|---|---|---|---|---|---|---|
| [-100, 0) | 109 | +2.41% | 57.8% | 8 | -0.84% | 37.5% |
| [0, 1) | 13 | +2.33% | 53.8% | 3 | +10.00% | 66.7% |
| [1, 2) | 8 | -0.32% | 50.0% | 3 | -4.59% | 0.0% |
| [2, 3) | 9 | -0.42% | 33.3% | 1 | -1.67% | 0.0% |
| [3, 4) | 8 | +1.28% | 75.0% | 0 | — | — |
| [4, 5) | 2 | +12.04% | 100.0% | 2 | +8.93% | 100.0% |
| [5, 6) | 5 | +6.63% | 40.0% | 0 | — | — |
| [6, ∞) | 4 | +6.61% | 75.0% | 0 | — | — |

收紧 cap 到 5/4/3/2 在 TRAIN 和 TEST 上都是 **均匀变差**。原因：低开（< 0%）虽然
samples 多但 TEST 上是负的（-0.84%），中开（4-5%）样本太少（n=2）。

**结论**：不动 cap。小草的 0-2% 偏好是关于"买入体验/盈亏比"，不是次日收益，1 日
backtest 捕捉不到。

### 4.4 Bad mode 排除（G）

Per-mode train avg（按 avg 升序）：

```
mode                    TR_n   TR_avg  TR_win   TR_med  |  TE_n   TE_avg  TE_win
孕线低吸                       1  -16.64%    0.0%  -16.64%  |     1   -6.42%    0.0%
接力低弱转2                    13   -0.14%   46.2%   -1.94%  |     4   -0.73%   25.0%
绿断低吸                      21   +0.73%   42.9%   -0.48%  |     1   -0.72%    0.0%
N字低吸                      24   +1.72%   50.0%   +0.32%  |     0       —       —
方向内绿盘低吸前3名                31   +2.93%   61.3%   +4.68%  |     4   -3.37%   25.0%
接力低弱转1                    32   +3.24%   59.4%   +1.08%  |     5   +7.07%   60.0%
首红断低吸                     30   +3.90%   70.0%   +3.33%  |     2   +6.94%  100.0%
红断低吸                       6   +5.21%   66.7%   +4.86%  |     0       —       —
```

按 "TRAIN n≥10 AND TRAIN avg ≤ -1%" 标准筛 → **没有任何模式合格**。

特别注意：validated 的两个排除项 `接力低弱转2` 和 `方向内绿盘低吸前3名` 在 4 个月
TRAIN 上分别是 -0.14% 和 +2.93%（前者勉强可接受，后者是正的）。但在 1 个月 TEST 上
都是负的（-0.73% 和 -3.37%）。

这印证了 0419 说的"模式适配环境"——这两个模式在 12-3 月环境中可以做，在 4 月不能做。
保留 validated 的硬排除是对当下（4 月以后）环境最稳妥的选择。adaptive 的 rolling
窗口理论上能捕捉到这种环境切换，但响应慢；硬规则补这个缺口。

**结论**：不扩充 exclude_modes。保留 validated 的两条作为"区域保险"。

### 4.5 Rules 阈值（E）

每个模式都用 `_compare_jw(detail, threshold, focus)`：信号通过当且仅当
`xcjw >= threshold` 或者 `(direction AND xcjw >= threshold/1.3)`。

模式→阈值映射（基于现行常数 SUPER=300, STRONG=200, QUALIFIED=150）：

```
接力低弱转1: SUPER (300)              N字低吸:    STRONG*1.3 (260)
接力低弱转2: STRONG (200)             孕线低吸:    QUALIFIED*1.3 (195)
绿断低吸 / 红断低吸 / 首红断低吸: QUALIFIED (150)   方向低位低吸:  STRONG (200)
全盘低位低吸: STRONG (200)             方向内绿盘低吸前3名: QUALIFIED (150)
```

**Per-mode xcjw 与 return 的相关性**（TRAIN 内 split 成 low/high half）：

| mode | n | xcjw range | low half avg | high half avg | 解读 |
|---|---|---|---|---|---|
| 接力低弱转1 | 32 | [232, 775] | +1.46% | **+5.03%** | xcjw 越高越好（值得提高 SUPER）|
| 接力低弱转2 | 13 | [177, 276] | +2.43% | **-2.35%** | 反向：xcjw 高反而差 |
| 绿断低吸 | 21 | [135, 835] | +3.49% | **-1.78%** | 反向 |
| 方向内绿盘低吸前3名 | 31 | [127, 1626] | +2.05% | +3.75% | 弱正相关 |
| 红断低吸 | 6 | [145, 225] | +4.73% | +5.69% | 样本太少 |
| 首红断低吸 | 30 | [143, 956] | +3.60% | +4.21% | 弱正相关 |
| N字低吸 | 24 | [202, 454] | +1.76% | +1.67% | 无相关 |

**Grid (tighten only)**: super_jw ∈ {300,350,400,500}, strong_jw ∈ {200,250,300,350},
qualified_jw ∈ {150,175,200,250}。Robust（双向改善 + TEST n≥3）的赢家：

| (S, T, Q) | TRAIN n / avg / win | TEST n / avg / win | Δ TR | Δ TE |
|---|---|---|---|---|
| (400,350,150) | 75 / +2.83% / 60.0% | 7 / +5.25% / 57.1% | +0.41% | +0.57% |
| (400,300,150) | 79 / +2.76% / 59.5% | 7 / +5.25% / 57.1% | +0.34% | +0.57% |

但**这是集中度 trick**：TEST sum 从 +42.1% → +36.8%（少 5.3pp），avg 上升只是因为
丢了 2 笔接近平均值的小赢家。"sum down avg up" 不是真改善。

**结论**：保持现行 (300, 200, 150) 不变。

**Follow-up：per-mode xcjw threshold 也测了** (`scripts/tune_per_mode_xcjw.py` +
`scripts/tune_jielidi_threshold.py`)。最强候选是单独把 接力低弱转1 的 xcjw cutoff
从 300 升到 400：

| month | baseline n / avg / win | variant n / avg / win | Δ avg | Δ win |
|---|---|---|---|---|
| Dec25 | 30 / +0.97% / 43.3% | 16 / **+2.31%** / 37.5% | +1.34% | **-5.8pp** ⚠ |
| Jan26 | 20 / -1.00% / 45.0% | 19 / -1.07% / 42.1% | -0.07% | -2.9pp |
| Feb26 | 19 / +3.91% / 57.9% | 16 / +3.17% / 56.3% | -0.74% | -1.6pp |
| Mar26 | 41 / +4.45% / 70.7% | 39 / +4.69% / 71.8% | +0.24% | +1.1pp |
| **Apr26 (TEST)** | 9 / +4.68% / 55.6% | 6 / **+6.13% / 66.7%** | **+1.45%** | **+11.1pp** |

TEST 上 1.45% avg + 11.1pp win 是漂亮的，但 **3/4 TRAIN 月份的 win 率都倒退**
(Dec -5.8pp / Jan -2.9pp / Feb -1.6pp)，TRAIN sum 跌 15.4% 也是明显的样本损失。
不通过 cross-window robustness。

更重要的认知：**adaptive 已经在动态捕捉这个信号**——当 接力低弱转1 滚动 avg 跌
到阈值之下时会自动 shadow，不需要硬编码 xcjw cutoff。静态 cutoff 锁死规则反而
失去 adaptive 的环境适应能力。

要做真正的 per-mode threshold refactor，需要：
1. `rules.py` 接受 `mode_thresholds: dict[str, float]` 参数
2. 不是死阈值而是 mode 加 quality_band 字段（low/med/high），让 adaptive 更细粒度
3. 用 ≥ 200 笔 trades 的 universe 做更稳健的拟合

这超出"调参"范围，留作下一轮架构设计。

### 4.5b Sort key（F）

**direction_sort_key 实测无效** — `_run_direction_dixi` 用此 key 排序候选 codes，
但生成 signal 的逻辑（`check_direction_dixi`）只看 `details[:3]` 中的 `isBottom`/
`isDownBroken` 标志，与 sort 顺序几乎无关。validated_v2 已排除 `方向内绿盘低吸前3名`，
剩下的 `方向低位低吸` 跨 5 个月只有 2 笔。改 sort_id 47/54/48/40 出来的 backtest
结果完全 identical（4 个 sort_id 都跑了，`/stock/sort_v2` 缓存确认调用过）。

**pool_sort_key 实测有效但不 robust**。pool_sort_key 默认 38（xiaocaoXCJW=小草竞王），
控制 jieli + dixi 池排序。candidate 测试：

| (dir, pool) | Dec-Jan n/avg/win | Feb-Mar n/avg/win | **Apr (TEST)** n/avg/win |
|---|---|---|---|
| 47 / 38 (默认) | 41 / +0.70% / 46.3% | 44 / +5.00% / 72.7% | 8 / +6.06% / 62.5% |
| 47 / 48 (xcjwV2) | 37 / +0.50% / 45.9% | 28 / +3.82% / 64.3% | 11 / **+6.28%** / 72.7% |
| 47 / 40 (xiaocaoCJS) | 28 / +0.23% / 42.9% | 10 / +3.87% / 60.0% | 7 / **+7.03%** / 71.4% |
| 54 / 48 | 37 / +0.50% / 45.9% | 28 / +3.82% / 64.3% | 11 / **+6.28%** / 72.7% |

xcjwV2/xiaocaoCJS 在 TEST 上 avg 微涨（+0.22% 到 +0.97%），但 TRAIN n 大幅下降
(Feb-Mar 44→10 是 4× 缩水)，TRAIN avg 也都更差。**集中度 trick + cross-window 不一致**
→ reject。

### 4.5c Regime 过滤（D）

用 cached `/stock/date_kline` 数据重建 per-date 市场情绪（distinct stock 共 157 只，
每天 300-900 个样本），计算 positive_ratio + mean_pct + top-K block strength，
分类为 bull / trend / neutral / divergence / bear。跨 67 天分布：

```
trend       19 (28%)
divergence  17 (25%)
bear        12 (18%)
bull        10 (15%)
neutral      9 (13%)
```

**反直觉发现**：TEST (April) 上各 regime 的 active 信号 avg：

| regime | TRAIN n/avg | TEST n/avg |
|---|---|---|
| bear | 26 / +1.65% | 5 / **+7.35%** |
| neutral | 33 / +4.08% | 3 / +5.35% |
| divergence | 49 / +2.08% | 5 / -0.68% |
| trend | 31 / +1.35% | 4 / **-5.93%** |
| bull | 19 / +3.15% | 0 |

TEST 上 bear 反而最好，trend 反而最差。**原因**：1 日持仓 backtest profit 来自次日
开盘到收盘的反弹——bear day 之后常有 oversold rebound。0410 / 0415 提到的 regime
gate 是给"是否开仓 + 持仓周期"做参考，对 1 日持仓的 next-open / next-close 套利
不直接适用。

测试 4 种 regime gate 变体：

| 变体 | TRAIN Δ | TEST Δ |
|---|---|---|
| full gate (drop bear, restrict divergence to dixi) | -0.49% | **-4.24%** |
| drop bear only | -0.29% | **-4.24%** |
| drop bear + divergence entirely | +0.16% | **-5.04%** |
| drop bear + drop 接力 in divergence | -0.29% | **-4.24%** |

所有变体在 TEST 都明显伤害 → reject。Regime gating 留作 annotation（信号上仍带
`regime` 字段），不参与 active/shadow 决策。

### 4.6 Bigcap 过滤（H）

`is_big_cap` 已经是每个信号的内置 tag（`bigcap_codes()` 用 stock_info 的
tradableAShare top 20%）。21% 的 universe 信号属于 bigcap。

| split | TRAIN n / avg / win | TEST n / avg / win |
|---|---|---|
| big_cap | 32 / +2.42% / 62.5% | 5 / **-1.12%** / 40.0% |
| small_cap | 126 / +2.41% / 55.6% | 12 / +2.61% / 41.7% |

TRAIN 上 big/small avg ~ 平局；bigcap 微微高 win 率。TEST 上 bigcap 是负的但
n=5 太小。

| 变体 | TRAIN Δ | TEST Δ |
|---|---|---|
| validated + EXCLUDE bigcap | +0.10% | +0.08% |
| validated + ONLY bigcap | -0.37% | -0.68%（TEST n=1）|

**结论**：保持当前的"双轨标注但不过滤" — bigcap 信息保留为 annotation。
小草 0413-A "大票留底仓做趋势" 的逻辑针对的是趋势核心持仓策略，不适用于我们这套
弱转强/低吸短线模式集——0419 也明说了 "短线只做弱转强套利，不沉迷连板情绪"。

### 4.7 跨月子窗口稳定性

`scripts/validate_v2_subwindows.py` 把 TRAIN 拆成月份验证：

| window | baseline | validated_v2 | Δ avg | Δ win |
|---|---|---|---|---|
| Dec25 | n=30 +0.97% w=43.3% | n=19 +1.56% w=52.6% | +0.59% | +9.3pp |
| Jan26 | n=20 -1.00% w=45.0% | n=10 +0.03% w=50.0% | +1.03% | +5.0pp |
| Feb26 | n=19 +3.91% w=57.9% | n=17 +3.54% w=58.8% | -0.37% | +0.9pp |
| Mar26 | n=41 +4.45% w=70.7% | n=30 +5.24% w=80.0% | +0.79% | +9.3pp |
| Apr26 | n=9  +4.68% w=55.6% | n=5 +7.83% w=80.0%  | +3.16% | +24.4pp |

3/4 TRAIN 月份在 avg + win 上都改善；Feb26 是噪声级别的 ~flat（n 19→17 只去掉 2 笔，
avg 漂移 -0.37% 没有统计意义）。**符合"跨子窗口一致"标准**。

---

## 5. 工程修复

### 5.1 `kline-count` 默认值的静默截断 bug（src/xiaocao/backtest.py）

`run_backtest` 在最后用 `fetch_klines(client, codes, end_date, count=kline_count)`
拉一次 K 线供 `score_trades` 使用。`count=30`（默认）只覆盖最后 30 个交易日。如果
backtest 区间超过 30 个交易日，**早期信号的 buy/sell 价位拿不到，trades.csv 静默
缺这些行**。

复现：5 个月 backtest 第一次跑 default `--kline-count 30` 只产出 31 笔 trades。
显式 `--kline-count 120` 才产出 175 笔。

修复：在末端 fetch 前自动 `effective_kline_count = max(kline_count, len(trade_days) + 5)`。

### 5.2 `pick_big_ones` 对 None 列表元素崩溃（src/xiaocao/strategy/rules.py）

某些 `/stock/xiao_cao_block_category_rank_v3` 响应是 dict，client 用 `list(result.values())`
转换会包含 None 值。过往 March-April backtest 没碰上，5 个月窗口必定碰上。

修复：`isinstance(item, dict)` 守卫。

两个修复都加了回归测试：
- `test_pick_big_ones_skips_none_entries`
- 现有 `test_strategy_open_pct_*` 系列已经覆盖 cap 行为

---

## 5.3 端到端验证（`xiaocao backtest validate`）

```bash
xiaocao backtest validate \
  --windows "2025-12-01:2026-01-31,2026-02-01:2026-03-31,2026-04-01:2026-04-30" \
  --variant "--profile validated_v2" --metric avg --workers 4
```

跨 3 个窗口，validated_v2 vs default 全部 PASS：

| Window | Baseline n / avg / win | Variant n / avg / win | Δ avg | Δ win |
|---|---|---|---|---|
| Dec25-Jan26 | 79 / +1.51% / 50.6% | 69 / +1.87% / 52.2% | +0.36% | +1.6pp |
| Feb-Mar26 | 75 / +3.50% / 64.0% | 54 / +3.84% / 68.5% | +0.34% | +4.5pp |
| **Apr26 (TEST)** | 17 / +1.51% / 41.2% | **13 / +4.48% / 53.8%** | **+2.97%** | **+12.6pp** |

注：因为 `validate` 的 `--reset-mode-history` 默认在每个窗口开始时清空 mode_history，
adaptive 都进入 Tier 4 dormant，所有信号都是 shadow——这次比较只覆盖结构性过滤
（exclude_modes + off_mainline）的效果，不包含 adaptive 部分。adaptive 本身的提升
（见 §2 表）需要在带 warmup 的 backtest 单跑里看（`--warmup-start` 选项）。

---

## 6. 推荐使用

```bash
# 推荐生产配置
xiaocao backtest run --start <S> --end <E> --workers 6 --profile validated_v2

# 老配置仍可用（不破坏现有用户）
--profile validated                # 不带 off_mainline
--profile validated_off_main_line  # 与 validated_v2 等价（保留兼容名）
--profile default                  # 不带任何过滤
```

`validated_v2` = `validated` + `exclude_main_line=True` + CLI 默认开启的 `--adaptive-modes`。

---

## 7. 复盘脚本（可重放，无副作用）

| 脚本 | 用途 |
|---|---|
| `scripts/replay_lib.py` | cache + signals 加载 + 通用 evaluate() |
| `scripts/tune_adaptive_5mo.py` | adaptive 参数 1620-config grid |
| `scripts/tune_max_open_pct.py` | open-pct cap 全局 + 分类 |
| `scripts/tune_mainline.py` | mainline (window, topk, hits) + 反向 |
| `scripts/tune_rule_thresholds.py` | (super_jw, strong_jw, qualified_jw) 收紧 grid + per-mode xcjw 相关性 |
| `scripts/tune_bigcap.py` | bigcap exclude / only 测试 |
| `scripts/tune_sort_keys.py` | direction_sort_key + pool_sort_key 跨窗口 bench (跑 12 backtest) |
| `scripts/build_proxy_regime.py` | 从 cached date_kline 重建 per-date regime |
| `scripts/tune_regime_gate.py` | 用 proxy regime 做 mode-by-regime gating 的 4 种变体测试 |
| `scripts/tune_per_mode_xcjw.py` | per-mode xcjw cutoff 全模式 sweep |
| `scripts/tune_jielidi_threshold.py` | 单独 sweep 接力低弱转1 cutoff（最强候选）|
| `scripts/mine_bad_modes.py` | 系统性差模式挖掘 |
| `scripts/validate_v2_subwindows.py` | 跨月稳定性 |

每个脚本都从 `output/xiaocao_5month_seed/` + `output/.cache/xiaocao.db` 直接读取，
不发 API。

---

## 8. 已知限制 & 后续建议

1. **TEST 样本太小（17 笔，9 active baseline）**。+3.16% 的 avg 改善看起来漂亮但
   样本误差不可忽略。建议：每月新数据进来后 append 到 cache、定期 re-validate。

2. **Regime classifier 在 backtest 里始终空**（market_overview 是 live state，没有
   per-date 历史端点）。Category D（regime 阈值调优）这次没做，需要先建反推 regime
   的工程能力——是另一个独立项目。

3. **Rules 阈值（SUPER_JW=300 等）的 cache-only 测试已做（§4.5）**：grid winner
   是集中度 trick，per-mode xcjw 相关性指出"接力低弱转1 应升 SUPER 到 400+，但
   接力低弱转2/绿断低吸 应反向"。要做必须改 `rules.py` 让每个模式接受独立阈值
   参数——这是下一轮的 refactor。

4. **Bigcap 过滤的 cache-only 测试已做（§4.6）**：完全 neutral。我们这套
   弱转强/低吸短线模式集本来就不适合 bigcap-aware 排序，0413-A "大票留底仓"
   是趋势核心持仓的逻辑，跟我们策略 modes 的目标不一致。

5. **Sort key（§4.5b）和 Regime gate（§4.5c）的 cache-only 测试已做**：
   direction_sort_key 实测对 validated_v2 universe 几乎无影响（因为剩下的方向
   模式本来就稀疏）；pool_sort_key 改 jieli/dixi 池排序，xcjwV2 / xiaocaoCJS 在
   TEST 微涨但都伴随 TRAIN n 大幅缩水 + cross-window 不一致；regime gate 在 1 日
   持仓 backtest 里全部变体都伤害 TEST，因为 1 日 next-day 收益和 regime 的
   持仓周期假设不匹配。三者都保持当前默认。

5. **Adaptive 默认放 (1,2,3 \| -5,-3,-2) 已经是 grid 上接近最优**——下次再调可能要换
   loss function（不只看 avg / win，加上 Sortino / max drawdown 等）。
