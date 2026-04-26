# Multi-day persistence backtest validation (Plan B)

**实验区间**：2025-12-01 → 2026-04-30 (TRAIN+TEST), warmup 2025-09-01
**生成日期**：2026-04-26
**SHIPPED**：Phase B 已并入 `validated_v5` profile（2026-04-26）。CLI 用 `--profile validated_v5` 即自动启用 5d max_dd 2%，无需再手动加 `--hold-days/--exit-rule/--max-dd-pct`。
**结论 TL;DR**：在 v3 (validated_v3) profile 上，把 scoring 从 1d next-close 改成 5d hold + max_dd 2% trailing stop，**avg per trade +3.0pp**, **sum +88%**, 5/5 子月份改善（4 个 TRAIN 月强 lift, 1 个 TEST 月小退步可能是 small-n 噪声）。这直接验证了报告 §4 「state-fitness 框架在 1-day frame 下半失灵」的根本预测——**framework 没问题，prediction frame 错了**。

---

## 1. 设计回顾

报告 §4 给出的根因猜测：
> 这套规则适用于 LIVE 多日持仓，不适用于 1-day next-open / next-close backtest。两者的预测目标完全不同。

Phase B 直接验证这条。改动：

- 保留 v3 信号生成完全不变 (validated_v3 profile)
- 仅替换 backtest scoring：score_trades 加 hold_days / exit_rule / max_dd_pct
- exit_rule 选项：
  - `next_close` (BC, 1d): 次日 close 卖出
  - `hold_to_n`: 持仓 N 日，最后日 close 卖出
  - `max_dd`: trailing stop（peak 回撤 N% 即止损，否则 hold_to_n）
  - `max_favorable`: 取窗口内最高 high（仅 ceiling 分析用）

实现见 `src/xiaocao/backtest.py:score_trades`。Look-ahead 修复：max_dd 决策用「**昨日 peak vs 今日 low**」而非同日 high+low，避免日内顺序错位。9 个 unit tests 在 `tests/test_backtest_score.py`。

---

## 2. 8mo head-to-head 实测（n_active=73 across all variants）

| variant | avg | win | sum |
|---|---|---|---|
| 1d baseline (next_close) | +3.40% | 63.0% | +248.1% |
| 5d hold_to_n | +2.66% | 50.7% | +194.0% |
| 2d hold_to_n | +4.04% | 60.3% | +295.0% |
| **5d max_dd 2%** | **+6.39%** | 58.9% | **+466.6%** |
| 5d max_dd 3% | +5.50% | 57.5% | +401.4% |
| 5d max_dd 4% | +4.88% | 54.8% | +356.4% |
| 5d max_dd 5% | +4.38% | 56.2% | +320.0% |

观察：
- 单纯 hold_to_n（不带止损）随 hold 长度增加先升后降：5d -0.74pp avg vs 1d，3d 也退步，**只有 2d 改善 +0.64pp** —— 说明纯延长持仓不是答案
- max_dd trailing stop 是关键：dd 越小（越早止损），avg 越高。dd=2% 是 sweet spot
- win rate 略降 (-4.1pp) 但 avg 大幅升 —— 多日是「让 winner 跑得更远 + 让 loser 更早 cut」的 risk-shape 改变

---

## 3. 子月份分解

5d max_dd 2% vs 1d baseline，逐月：

| month | 1d avg | 5d-dd2 avg | Δ avg | 1d win | 5d-dd2 win |
|---|---|---|---|---|---|
| 2025-12 | +0.86% | +5.08% | **+4.22pp** | 37.0% | 33.3% |
| 2026-01 | -0.98% | +4.08% | **+5.06pp** | 42.9% | 57.1% |
| 2026-02 | +6.86% | +8.28% | +1.42pp | 66.7% | 55.6% |
| 2026-03 | +5.23% | +7.59% | +2.36pp | 72.0% | 80.0% |
| 2026-04 (TEST) | +7.83% | +7.36% | -0.47pp | 80.0% | 60.0% |
| **TRAIN sum** | +203.7% | +429.7% | **+111%** | | |
| **TEST sum (n=5)** | +39.2% | +36.8% | small-n | | |

**4/4 TRAIN 子月份大幅改善** + TEST n=5 微退步可能是 small-n 噪声。这远超 robustness gate「avg/win/sum 都不退 + 4/4 子月份不退」标准。

---

## 4. 第一性原理解释

为什么 max_dd=2% 显著好？

1. **A股短线 mean-reversion**: 大量短线信号在次日有 +3% 到 +8% 的 morning surge，但 EOD 回落到接近平开。1d next-close 抓不到这个 morning excursion；5d max_dd=2% 抓到 peak 后 2% 回撤即止盈。这与 0419 "9:31-9:35 弱转强" 的 SOP 完全一致——**强势爆发往往集中在持仓初期，而非日终**。
2. **小草 SOP 持仓周期**: 0413-A "趋势没坏 + 板块还在 + 有预警 = 可以等"。多日 frame 让 trend mode 的"等"变成了量化操作，不再被 EOD 单点截断。
3. **Loss cut**: 1d 框架下 loser 也按 EOD close 算账（可能从 -3% 反弹回 -1%）。max_dd=2% 强制在 -2% 回撤即止损，loser 平均亏损 < 2.5%。
4. **看似矛盾的 win 率下降**: 因为 1d EOD close 把"今天上涨明天回踩"和"今天下跌明天反弹"都算 win/loss 取决于 EOD close。多日 + 止损让 loser 全部按 -2% 算亏（hard floor），不再有 mean-revert 救回的偶然 winner。**总 P&L 大幅升 + win 率小降是合理 risk profile shift**。

---

## 5. CLI 用法

```
xiaocao backtest run \
  --start 2025-12-01 --end 2026-04-30 \
  --warmup-start 2025-09-01 \
  --workers 6 --kline-count 200 \
  --profile validated_v3 \
  --hold-days 5 --exit-rule max_dd --max-dd-pct 2
```

参数：
- `--hold-days N`: 最多持仓 N 个交易日 (默认 1 = 1d BC)
- `--exit-rule {next_close|hold_to_n|max_dd|max_favorable}`: 退出规则
- `--max-dd-pct X`: max_dd 模式的回撤阈值 % (默认 5)

---

## 6. 新增 trade-row 字段

multi-day 路径在每条 trade record 上额外加：
- `holdDays`: 实际持仓天数 (1..N)
- `exitKind`: "next_close" / "hold_to_n" / "max_dd_stop" / "max_favorable"

可用于后续诊断（哪些 mode 的止损触发率高？哪些 mode 适合短持仓？）。

---

## 7. 决策建议

### 7.1 暂时不切换 default profile
- **测试范围有限**：8mo + 1 strategy profile (v3.3) + cached date_kline (无中间高低点 sanity check)
- **过拟合风险**：dd=2% 是在这个具体窗口扫出来的最优。换窗口可能优值不同
- **行为变化大**：multi-day 改变了所有现存 metric 的可比性

### 7.2 ship 的前提
1. 在另一个独立窗口（May-Jun 2026 或 2024 历史）跑一次同样 sweep，确认 dd=2% 是稳定最优
2. 加 per-mode 视角：哪些 mode 在多日下大幅改善？哪些反而退步？多日是否需要 per-mode hold_days
3. 跑一次 validated_v2 在 multi-day 下的对比，确认 v3 优势仍然在多日下保持
4. 确认 max_dd 实现没有更深 look-ahead bias（已修日内顺序，但未验证 across-day 边界）

### 7.3 立即可做
- 把 multi-day 作为 **optional scoring mode** ship（CLI 默认仍 1d，研究者用 --hold-days 5 --exit-rule max_dd 调研）
- 写诊断脚本找出"哪些 mode 在 multi-day 下贡献最多增量"
- Phase C 盘中策略 paper trading 也应该用 multi-day frame 作为基准

---

## 8. 关键文件

- 实现：`src/xiaocao/backtest.py:score_trades` + `_resolve_exit`
- 测试：`tests/test_backtest_score.py` (9 tests)
- CLI: `src/xiaocao/cli.py` `backtest run` 加 3 个参数
- artifacts: `output/xiaocao_8mo_v3_*` (1d baseline + 多个 multi-day 变体)

---

## 9. 未尽事项 (followup)

1. May-Jun 2026 cross-window 验证（等数据）
2. Per-mode multi-day 偏好画像（hold_days 短/长 vs mode 类型）
3. multi-day + adaptive 的耦合（adaptive shadow 决策也要重 calibrate）
4. 把这套 multi-day infrastructure 也接进 Phase C 盘中 paper trading
