# 第一性原理交易复盘：2025-09 → 2026-03 (TRAIN)

**样本**：125 笔 trades 跨 8 个 modes（2025-12-01 ~ 2026-03-31，warmup Sep25-Nov25 给 mode_history 喂数据）
**口径**：1 日持仓 (signal day open → next day close)
**生成日期**：2026-04-26

---

## 0. 宏观环境警示（必须先说）

⚠️ **2026-03 ~ 2026-04 期间美伊战争对全球股市冲击巨大**。任何对这两个月信号 avg
做"模型有效"判断都要打折——可能是 macro tailwind 或避险流入而不是模型 edge。

具体到我们的 TRAIN 数据:
- **2026-03**: 36 trades / +4.08% / 67% win — **TRAIN 内最好的月份**。但这恰好是
  地缘政治高峰期开端。中国股市可能因为 (a) 资金避险流入 (b) 国防 / 能源板块直接
  受益 而表现强于模型本身的 edge
- 不能把 March 的强势纯归功于策略；应该说"策略在地缘政治抬升的市场环境里没拉胯"

下面的所有 finding 都已在分析时考虑：
- 跨 4 个月一致出现的模式 → 强信号
- 只在 March 出现的模式 → 弱化处理（可能是 macro artifact）

---

## 1. Cohort 总览

| | n | avg ret |
|---|---|---|
| Winners (>+1%) | 66 (53%) | **+9.19%** |
| Losers (<-1%) | 46 (37%) | -6.13% |
| Washes (±1%) | 13 (10%) | ~0 |

期望盈亏比: avg_win / avg_loss = 9.19 / 6.13 ≈ **1.5**。胜率 53% × 1.5 = 0.80
盈亏比单位 → 净 +0.5 单位 → 整体正预期。这是一个**可工业化的 setup**，不是侥幸。

---

## 2. 各模式排名（按 avg 排序）

| Mode | n | avg | win% | best | worst | 评价 |
|---|---|---|---|---|---|---|
| **首红断低吸** | 21 | **+5.26%** | **71%** | +21.9 | -3.9 | ⭐ 最佳 |
| 红断低吸 | 5 | +5.02% | 60% | +14.2 | -3.3 | 强但 n 太小 |
| **接力低弱转1** | 31 | +3.41% | 52% | +39.4 | -17.6 | 双极性，需筛选 |
| N字低吸 | 16 | +2.50% | 50% | +12.7 | -7.8 | 中性 |
| 方向内绿盘低吸前3名 | 23 | +2.45% | 61% | +25.6 | -12.1 | 已被 validated 排除 |
| 接力低弱转2 | 11 | +0.41% | 36% | +14.0 | -8.7 | 已被 validated 排除 ✓ |
| **绿断低吸** | 17 | **-0.54%** | **35%** | +22.7 | -9.7 | ⚠ 真的差 |
| 红盘起爆主攻 | 1 | -7.0% | 0% | -7.0 | -7.0 | 样本不足 |

**5 个 finding 值得行动**：

### Finding A: 首红断低吸 是金牌模式 — 强化
- 21 笔 / 71% win / +5.26% avg / worst -3.9%（无大亏）
- 跨所有 score quartile 都正向 (+2.65%, +5.98%, +6.13%, +6.11%) — 不挑分数
- **建议**: 不动它（已经是默认 active）；下次设计 ensemble 加权时给它更高权重

### Finding B: 接力低弱转1 是双极性 — 需要 score 筛选
- xcjw 四分位非线性分布：Q1 +2.77 / Q2 -0.28 / Q3 -0.99 / **Q4 +9.51% / 70% win**
- 高分 (xcjw≥410) 是核心利润来源，中段 (282-402) 反而是亏损区
- 这是为什么早期 per-mode threshold 调到 400 看似有用但 cross-window 不稳——
  问题不在阈值高低，是中段本身不可靠
- **建议**: state-fitness 框架已经处理（state 强匹配 → 阈值放宽 → 高分时仍 active；
  state 弱匹配 + 中段 → 自然被 mode_history 滚动负向 trip 掉）。无需额外 hard cutoff

### Finding C: 绿断低吸 是隐性亏钱模式 — 考虑排除
- 17 笔 / 35% win / -0.54% avg / sum -9.2%
- 现在 validated 没排除它（只排了 接力2 + 方向内绿盘）
- 但样本量 17 vs 阈值要求 (n≥10 AND avg≤-1%): avg = -0.54 略好于 -1，**不严格符合
  排除标准**
- 跨子月份: 它在 Mar 是 +14.0 的大赢家拉高 avg，去掉 March 的 macro shock 它的
  其他月份 avg 是负的（要求看具体月份分解才能确认）
- **建议**: 留作下一轮 monitoring；如果 Apr-May 数据继续负 avg → 加入 exclude_modes

### Finding D: 红盘起爆主攻 样本不足，无法判断
- 1 笔，刚加入的新模式
- 也许设计的精度问题：jssb >= STRONG_JW=200 + pctChange ∈ (0,4]，可能太严格几乎不触发
- **建议**: 跑 6 个月看是否有足够信号；如果还是 < 5 笔 / 月，放宽精度（jssb>=150 或 pct cap 6）

### Finding E: 接力低弱转2 排除决定 valid
- 11 笔 / 36% win / +0.41% avg
- xcjw 高分反而最差: Q4 (≥215) 全部 0% win, avg -4.80%
- **决定**: 保持 exclude，符合 validated profile

---

## 3. Score-Quartile 分析（per mode）

| Mode (score field) | Q1 (low) | Q2 | Q3 | Q4 (high) |
|---|---|---|---|---|
| 接力低弱转1 (xcjw) | +2.77/57% | -0.28/29% | -0.99/43% | **+9.51/70%** |
| 接力低弱转2 (xcjw) | +3.40/50% | +7.08/50% | +3.79/100% | **-4.80/0%** ⚠ inverse! |
| 首红断低吸 (cjs) | +2.65/80% | +5.98/80% | +6.13/60% | +6.11/67% |
| 绿断低吸 (cjs) | -4.23/25% | +4.21/50% | -2.14/25% | -0.10/40% |
| 方向内绿盘 (cjs) | -3.19/20% | +11.28/100% | +2.30/60% | +0.54/62% |
| N字低吸 (cjs) | +1.90/50% | +5.61/75% | +0.40/25% | +2.10/50% |

**两个反直觉但显著的模式**：

1. **接力低弱转2 inverse xcjw**: 越高分越差 — 高 xcjw 在该模式下意味着"高竞王 +
   高开"组合，这正是 0410 / 0419 警告的"高开追涨"陷阱。已排除 → 不需要额外动作。

2. **方向内绿盘 Q1 (cjs<28) 显著差**: -3.19% / 20% win — 这是低分股票的"硬上"。
   已排除 → 不需要额外动作。

---

## 4. State-Axis 信号强度（最重要的发现）

```
axis                low (n=41)    mid (n=41)    high (n=43)
reward              +1.00%        +4.82%        +2.02%       ← 中段最佳
risk                +2.56%        +3.77%        +1.55%       ← risk-off 反而稍好
continuity          -1.61%        +3.35%        +5.92%       ← 强单调正向 ⭐
duan_ban_recovery   -0.17%        -0.39%        +8.11%       ← 强阈值正向 ⭐
```

**Finding F: continuity 是最强的 state 预测器** (low → -1.61% / high → +5.92%)
- 主线稳定 = 资金集中 = 我们的 rebound + continuation 模式都受益
- 我的 MODE_PROFILE 已经在大部分模式上设了 wants_continuity=high or any
- 不需要改

**Finding G: duan_ban_recovery 是阈值类信号 (>0.55)，不是连续**
- 只有 high 段 (n=43) 给 +8.11%；low + mid 都接近 0
- 我的精度 0.45 阈值 (`_duan_ban_recovery_ok`) 设得偏低 — 真正的活跃水线在 0.55
- **建议**: 把 precondition 从 0.45 提到 0.55 — 避免在边缘情况勉强 active

**Finding H: reward 中段比高段好** — 反直觉
- 高 reward = 全市场都在动 = "everyone is already in" → 跟随成本高
- 这与 0419 "好行情做主动票" 不矛盾——他指的是 risk-on 不是 reward-on
- 我的 MODE_PROFILE 大多 wants_reward=high — **可能需要调整 to "mid"**

---

## 5. Open-pct 分布（验证 0419 直觉）

| open_pct bucket | n | avg | win% |
|---|---|---|---|
| ≤ 0 (低开/平开) | 82 | **+2.72%** | 56% | ⭐ 最稳定 |
| (0, 2) | 16 | **+0.85%** | **38%** | ⚠ 弱区 |
| ≥ 4 | 12 | +6.39% | 58% | n 太少难判断 |

**Finding I: open_pct ∈ (0, 2) 是 dead zone**
- 0419 说 "0-2% 最舒服" 是从买入体验角度（卡住低位）
- 但**1-day 收益**显示这个区段反而最差 — 38% win
- 解读：略微红盘但不是低开 = 已经被算法或散户抢跑了一步，我们做不出 edge
- 真正稳的是 ≤ 0（充分低开）或 ≥ 4（强势确认）

**建议**: 不引入硬过滤（n=16 太少，单月 macro 影响大）。但下次设计 score modulation
时可以**针对 open_pct ∈ (0,2) 略微抬高分数门槛**。

---

## 6. 大票 vs 小票

| | n | avg | win% |
|---|---|---|---|
| big-cap | 27 | +1.23% | 52% |
| small-cap | 98 | **+2.99%** | 53% |

**Finding J: 小票优势稳定**（与之前 5-month 数据一致）
- 已经做过 H 类 bigcap_filter 测试 — 排除 big-cap 没 robust 改善
- 我们的 universe 由 弱转强 / 低吸 短线模式生成，本就更适合小票
- 不动

---

## 7. 月度模式 — 警惕 macro 干扰

| 月份 | n | avg | win% | 说明 |
|---|---|---|---|---|
| 2025-12 | 46 | +1.34% | 48% | 最大样本月，避险/方向不明，普通 |
| 2026-01 | 27 | +2.02% | 41% | 信号变少（春节季节性？），胜率最低 |
| 2026-02 | 16 | +3.92% | 56% | 春节后修复 |
| **2026-03** | 36 | **+4.08%** | **67%** | **可能含美伊地缘政治助推** |

⚠ **2026-03 这个月的强势可能不全归功于策略**。如果 March 的真实 contribution 砍半
（去 macro），整体 TRAIN avg 会从 +2.61% 掉到 ~+2.0%，仍然是正预期但没现在漂亮。

**建议**: 等 6 月以后再用 Mar 当作 robust evidence；近期决策只看跨月一致信号。

---

## 8. 综合 Pattern：值得强化 vs 警惕的 setup

### ⭐ Reinforce-able patterns (跨多个月 + 多个模式 一致正向)

| pattern | n | win% | avg | 来源 |
|---|---|---|---|---|
| state.continuity ≥ 0.6 | 54 | 48% | +2.98% | Finding F |
| state.duan_ban_recovery ≥ 0.55 | 43 | — | +8.11% | Finding G |
| 首红断低吸 + 任何 state | 21 | 71% | +5.26% | Finding A |
| 接力低弱转1 + xcjw ≥ 400 | ~11 | 70% | +9.51% | Finding B |
| open_pct ≤ 0 | 82 | 56% | +2.72% | Finding I |

### ⚠ Anti-patterns (跨多个 setup 一致负向)

| pattern | n | win% | avg |
|---|---|---|---|
| state.continuity < 0.4 | 41 | — | -1.61% |
| 接力低弱转1 + open ≥ 5% + cont < 0.4 | ~5 | 0% | -10 to -17% |
| 接力低弱转2 + xcjw ≥ 215 | ~5 | 0% | -4.80% |
| 绿断低吸 + cjs < 21 | 4 | 25% | -4.23% |
| open_pct ∈ (0, 2) | 16 | 38% | +0.85% |

---

## 9. 落地 action items（按优先级）

### P0 (低风险高 ROI，本轮可直接做)
1. **把 `_duan_ban_recovery_ok` 阈值从 0.45 提到 0.55** — 数据显示 0.55 是真正
   有效的水线；0.45-0.55 区段 avg 接近 0
2. **首红断低吸 标记为高优先级模式** — adaptive 默认对它放宽（profile 已经用
   continuity=any，但可以更激进让它在 mid-low DBR 时也 active 如果其他评分正向）

### P1 (需要更多数据 before action)
3. **绿断低吸 monitor**：再积累 1-2 个月数据，如果 avg 仍然 < 0 → 加入 exclude_modes
4. **红盘起爆主攻 优化**：1 笔太少；放宽精度（jssb>=150）让样本起来再判断
5. **MODE_PROFILE wants_reward 重审**：reward 中段表现最好，不是 high；可能多个
   模式 wants_reward 应改为 "mid"

### P2 (需要框架级改造)
6. **open_pct ∈ (0, 2) 软过滤**：dead zone 信号略微提分数门槛 — 接续之前的
   "score modulation" 设计但 scope 改为这个 specific bucket
7. **接力低弱转1 score-aware adaptive**：xcjw≥400 vs <400 表现差异巨大；让 fitness
   除了看 state 还看 xcjw 在 mode 内部的分位

---

## 10. 与 v3.2 框架的连接

v3.2 的 state-fitness 框架已经吃到了部分上述信号：
- continuity 是 3 个 state 轴之一 ✓
- 多个 mode 的 wants_continuity = "high" ✓
- 断板 modes 用 precondition ✓

但分析提示还有进一步空间：
- duan_ban_recovery 阈值校准 (P0 #1)
- reward 偏好重审 (P1 #5)

这些都是 framework 内部的 calibration，不需要改架构。

最重要的元结论：**framework 的 axes 选对了，但具体数值需要 data-feedback 校准**。
就像小草说的 "看一个范围而不是死板的数"——但范围本身也要从数据里反推、定期校准。

---

## 11. 后续行动 (post-v3.3 实施 update 2026-04-26)

P0 (DBR 阈值 0.55) 已在 v3.3 落地。P1 项目跟进结果:

### 已尝试 + 拒绝

- **绿断低吸 wants_continuity any→low (v3.6 attempt)**: 实测 0 effect，因为
  ALL 17 个 绿断低吸 trades 的 DBR < 0.55 → precondition 短路 mode_fitness。
  详见 `scripts/diagnose_lvduan_dixi.py`。Wants_continuity 的微调被 precondition
  的硬约束完全 pre-empt
- **静态分数门槛或区段过滤** (5 项不同实验): 都被 concentration trick 击败。
  详见 framework report §7.4

### 仍然待跟进 (需要新数据，不是当前可解决)

- **绿断低吸 监控**: 17 trades / -0.54% avg / 35% win — 在 exclusion bar
  (-1%) 边缘。等 1-2 个月新数据。如果持续 -avg → 加 exclude_modes
- **红盘起爆主攻 sample**: 8 个月仅 1 trade。先调研 qibao pool 内 jssb 分布；
  可能要降 jssb 门槛 200→150 或 pct cap 4→6。但都要带数据验证不能拍脑袋
- **接力低弱转1 中段死区**: Q2-Q3 (xcjw 282-402) 14 trades / -0.5% avg / 36% win
  vs Q4 (xcjw≥410) +9.51% / 70% win。但任何静态 cutoff 实测都失败（v3.5 教训）。
  正确路径: per-mode adaptive 加权（让 fitness 看 score 分位）—— 见 framework
  report §7.3 #8

### 不要做的事 (已被拒绝)

参见 framework report §7.4 的"已拒绝清单"——下次想到任何 "filter / threshold
/ static cutoff" 想法之前先回去看，避免重复犯错。
