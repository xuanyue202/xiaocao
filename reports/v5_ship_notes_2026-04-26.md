# validated_v5 Ship Notes — 2026-04-26

**TL;DR**：Phase B 多日持仓 + max_dd 2% trailing stop 已合入 `validated_v5` profile。CLI 一行启用，不必再手动加 scoring flags。本文档记录实操注意事项 + 已知 caveats。

---

## 1. 启用方式

```bash
# 默认 v5 行为（无需额外 flag）：
xiaocao backtest run --start ... --end ... --warmup-start ... \
  --profile validated_v5

# 等价于（v3 + 手动 Phase B flags）：
xiaocao backtest run --start ... --end ... --warmup-start ... \
  --profile validated_v3 --hold-days 5 --exit-rule max_dd --max-dd-pct 2
```

**对实操**：你照常 9:25 集合竞价 → 9:30 fill 入场，**唯一变化是退出规则**：
- 不再次日 close 卖
- 持仓 5 日窗口内，只要从 post-entry peak HIGH 回撤 ≥ 2% 就触发 trailing stop
- 5 日窗口结束仍未触发，按当日 close 退出

T+1 完全合规（stop 检查仅作用于 buy_date+1 之后）。

---

## 2. 8mo TRAIN+TEST 实测改善

| 指标 | v3 (1d) | v5 (5d max_dd 2%) | Δ |
|---|---|---|---|
| n_active | 73 | 73 | — |
| avg | +3.40% | **+6.39%** | +2.99pp |
| win | 56.2% | 56.2% | — |
| sum | +248.1% | **+466.6%** | +88% |

**子月份分解** (v5 vs v3):

| month | v3 avg | v5 avg | Δ |
|---|---|---|---|
| 2025-12 | +0.86% | +5.08% | +4.22pp |
| 2026-01 | -0.98% | +4.08% | +5.06pp |
| 2026-02 | +6.86% | +8.28% | +1.42pp |
| 2026-03 | +5.23% | +7.59% | +2.36pp |
| 2026-04 (TEST) | +7.83% | +7.36% | -0.47pp (n=5 噪声) |

4/4 TRAIN 月份大幅改善。

---

## 3. 已知 Caveats

### 3.1 Bull-period bias
- 8mo 窗口 (Sep25-Apr26) 偏 bull
- 在 bear 周期，trailing stop 触发更频繁，效果可能折损
- **进行中**：cross-window 验证 (2025-04 → 2025-08)

### 3.2 dd=2% 不一定是真最优
完整 dd sweep 显示 dd=0.5% 反而 backtest 最高（avg +6.88%, sum +502），但有 over-fit 嫌疑（紧 stop 在 bear 期会一律 -0.5% 锁损）。dd=2% 是稳健选择，能容忍正常震荡。

### 3.3 Indicators 不再可比
v5 的 avg/win/sum 跟 v3 历史数据不能直接比。任何监控指标 / 报表都要用 v5 baseline 重算。

### 3.4 多日持仓的资金周转
v3 (1d) 的资金周转每天 1 次。v5 平均持仓 2-3 日（trailing stop 早触发），资金周转降低 ~50-60%。如果你按 turnover 算 ROI，v5 的 "per-trade ROI" 看起来比 "per-day ROI" 高得多。

### 3.5 5d 窗口 vs 实际持仓
看 trades.csv 的 `holdDays` 列：5d 是 max，trailing stop 多在前 1-3 日触发。**不要被 "5d 窗口" 字面误导**——多数 trade 实际持仓 < 3 日。

### 3.6 hold_days = 3 也基本等价
3d_dd2 实测 +6.42% / sum +468 ≈ 5d_dd2 +6.39% / sum +467。hold_days≥3 后 max_dd 已 saturate。如果你想缩短最坏情况持仓，可以手动 `--hold-days 3` 不损失 P&L。但默认 5d 给 trailing stop 更宽松环境。

---

## 4. 实操新规则（T+1 合规）

### 4.1 入场仍按你既有方式
- 9:25 集合竞价 buy
- 9:30 open fill
- 仓位你自己决定

### 4.2 持仓监控（v5 框架）
对每只持仓股，记录 entry 后的 **peak HIGH**（每日盘后看一下当日 high 是否破前高）：
- 当前价距 peak 回撤 ≥ 2% → 触发 stop，**次日**早盘卖出
- 5 个交易日内未触发 → 第 5 日 close 主动卖出

### 4.3 加 9:35 confirmation 加仓（可选）
对 STRONG（drawdown ≤ 1.5%）的持仓股，9:35 可以额外加仓：
```bash
... --entry-rule confirmation_935
```
9:35 close 加仓单笔 EV +1.30~+3.27%（低于 9:30 open 同子集，但正期望）。要求该股票预先 backfill 过 minute_line。

### 4.4 9:35 诊断信号
- drawdown ≤ 1.5%（STRONG）→ 信号确认，次日止损可放宽
- drawdown > 3%（深度回撤）→ 信号衰减，次日 stop 收紧到 -1.5%，**不加仓**

---

## 5. 监控建议

每周复盘对比：
- v5 实盘 P&L 是否符合 backtest 预期 (+6.4% per-trade avg, 56% win)
- 哪些 mode 偏离最大（per-mode 实盘 vs backtest）
- max_dd 触发次数 / 5d full-window 退出次数比

如果连续 2 周实盘明显差于预期：
1. 检查 universe 漂移（v3 候选池是否同 backtest 期类似）
2. 看是否进入 bear regime（dd=2% 在 bear 期表现需观察）
3. 考虑暂时降回 v3 (1d) 或测试 dd=3% / dd=4%

---

## 6. Rollback 路径

随时可回 v3：
```bash
... --profile validated_v3
```

或保 v5 入场但用更宽 stop：
```bash
... --profile validated_v5 --max-dd-pct 3.5
```

---

## 7. 后续工作（按优先级）

1. **cross-window 验证** (in progress, 2025-04 → 2025-08): 确认 dd=2% 不是 over-fit
2. **dd=0.5% vs 2% cross-period decision**: 等 cross-window 结果
3. **R3/R4/R5 SOP 暂不推**: 基于 R2 实证，预期边际产出低
4. **forward-capture daemon**: 5月起开始捕获 second_line / each_trade 数据为下一阶段准备
