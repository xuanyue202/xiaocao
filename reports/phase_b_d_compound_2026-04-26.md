# Phase B (multi-day exit) + Phase D (intraday entry-timing) compound — 2026-04-26

**TL;DR**：

1. **Phase B 5d max_dd 2%** 是清楚的 ship-now winner（+88% sum vs 1d baseline，4/4 子月份改善，T+1 兼容）—— 不改入场，只换出场规则
2. **Phase D `confirmation_935`** 是可选的 9:35 加仓入场模式：实测 STRONG（drawdown ≤ 1.5%）子集 9:35 close 入场单笔 EV +1.3%~+3.3%。低于 9:30 open 同子集，但正期望可作独立加仓单位
3. **真正的盈亏分水岭是 STRONG vs RETRACED 这条 axis**——在 9:30 open 入场前提下，STRONG 子集 1d 平均 +4.54%（vs RETRACED +1.56%）；5d_dd2 下 +7.77%（vs +4.18%）。可作 T+1 持仓的诊断信号（次日止损校准 / 加仓信心）

---

## 1. 完整 8mo (TRAIN+TEST) 实测矩阵

每行 73 active trades from validated_v3 baseline，已 backfill 全程 1min K：

| Entry | Exit | n | avg | win | sum |
|---|---|---|---|---|---|
| 9:30 open | 1d next_close | 73 | +3.40% | 56.2% | +248.1% |
| 9:30 open | 5d max_dd 2% | 73 | **+6.39%** | 56.2% | **+466.6%** |
| 9:30 open + STRONG filter (drawdown≤1.5%) | 1d next_close | 45 | +4.54% | 66.7% | +204.3% |
| 9:30 open + STRONG filter | 5d max_dd 2% | 45 | **+7.77%** | 68.9% | +349.7% |
| 9:35 close (STRONG only) | 1d next_close | 45 | +1.30% | 57.8% | +58.5% |
| 9:35 close (STRONG only) | 5d max_dd 2% | 45 | +3.27% | 42.2% | +147.2% |

**关键观察**：

- **同样 STRONG 子集 9:30 open 入场 vs 9:35 close 入场**：1d 帧 +4.54% vs +1.30%（Δ -3.24pp），5d_dd2 +7.77% vs +3.27%（Δ -4.50pp）。9:35 入场损失了 morning surge 溢价
- **5d_dd2 在所有变体下都比 1d 强**：4 个对比中 avg 涨幅 +1.99~+2.99pp。Phase B 是稳定 win
- **STRONG filter 在 9:30 open 入场下贡献 +1.14pp avg / +10.5pp win（1d）**，在 5d_dd2 下 +1.38pp / +12.7pp。但只有 45/73 = 62% 通过率，sum 反而降（因 n 减少）

---

## 2. STRONG vs RETRACED 含义 vs 0419 SOP

| 子集 | drawdown@9:35 vs 9:30-9:35 max | 占比 | 1d avg | 5d_dd2 avg | SOP 解读 |
|---|---|---|---|---|---|
| STRONG | ≤ 1.5% | 45/73 = 62% | +4.54% | +7.77% | 9:35 仍贴近高点 = 强势继续 |
| RETRACED | > 1.5% | 28/73 = 38% | +1.56% | +4.18% | 已回撤 = 动量减弱 |

0419 line 580 "如果冲高，等回调; 如果回调后排名仍靠前，可以分批" 在多日持仓 SOP 上说**等回调入场**。但实测 1d / 5d 帧上 **回调反而是 weak signal**——这又是报告 §4 的 "1-day backtest 里 trend continuation 胜过 mean reversion" 现象。

诊断：**0419 SOP 是为 LIVE 多周持仓 + 当日全市场全样本筛选**设计的；它的"等回调"逻辑在「已经过 EOD 高分筛选 + 1-5 日 backtest 持仓」universe 上**反预测**。

---

## 3. 实操路径建议

### 3.1 立即可上线（需用户拍板 ship）

**default 升级**: `validated_v3 + hold_days=5 + exit_rule=max_dd + max_dd_pct=2`
- 不改 9:25 集合竞价 → 9:30 open 入场
- 改成多日 trailing stop（peak 回撤 2% 触发止盈/止损）
- T+1 完全兼容
- 实测 4/4 子月份改善，sum +88%

CLI:
```
xiaocao backtest run --start 2025-12-01 --end 2026-04-30 \
  --warmup-start 2025-09-01 --workers 6 --kline-count 200 \
  --profile validated_v3 \
  --hold-days 5 --exit-rule max_dd --max-dd-pct 2
```

### 3.2 可选加仓模式（独立 trade unit）

`entry_rule=confirmation_935` —— 9:35 close 加仓 STRONG 子集
- 与 9:25 集合竞价头寸**独立**，不互相影响
- 你实际操作仓位灵活分配
- EV 正但低于 9:30 open，所以适合「资金有余裕」的加仓场景

CLI:
```
xiaocao backtest run [...同上] \
  --entry-rule confirmation_935 \
  --intraday-dd-threshold 1.5
```

### 3.3 T+1 持仓诊断信号（不上 backtest，纯实操参考）

对每只 9:25 集合竞价已买入的股票，9:35 看 drawdown：

| 9:35 状态 | 实操动作 |
|---|---|
| drawdown ≤ 1.5% (STRONG) | 信号确认，次日止损可放宽到 -3% / -4%；可考虑加仓 |
| 1.5% < drawdown ≤ 3% (轻微回撤) | 持有但谨慎，次日止损 -2% |
| drawdown > 3% (深度回撤) | 信号衰减，次日止损 -1.5%，**不加仓** |

这套规则源于 Phase D 实测 STRONG 1d avg +4.54% vs RETRACED +1.56%。深度回撤的次日表现更差。

---

## 4. 实现细节

### 4.1 已 ship 的代码

`src/xiaocao/backtest.py:score_trades`:
- 加 `entry_rule` ∈ `{open, confirmation_935}`
- 加 `intraday_minute_data` (cached minute_line) + `intraday_dd_threshold` 参数
- BC: default `entry_rule="open"` 等同 v3.3 行为

`src/xiaocao/strategy/intraday_entry.py`：新模块
- `load_minute_cache(path)`: 从 SQLite cache 加载 minute_line（仅带 count param 的真历史）
- `compute_intraday_axes(records)`: 输出 6 个 axis：open_pct / pct_at_935 / max_window / drawdown_from_peak / entry_price / still_strong
- `passes_filter(axes, name, threshold)`: 入口过滤函数，支持 `still_strong` / `weak_open` / `pct_controlled` 三种

`src/xiaocao/api/client.py:minute_line`：
- 加 `trade_date / count / code_type` 参数（之前漏 count → silent today）
- 自动 routing：`.XCHJZS` 后缀 → `xiao_cao_environment_minute_line`，剥后缀

`src/xiaocao/cli.py` `backtest run`：
- `--hold-days N` `--exit-rule {next_close|hold_to_n|max_dd|max_favorable}` `--max-dd-pct X` (Phase B)
- `--entry-rule {open|confirmation_935}` `--intraday-dd-threshold X` (Phase D)

### 4.2 测试

185 passed (was 142 → +43 new tests over this session)：
- 9 backtest_score tests (B + D)
- 7 momentum/limitup state tests
- 6 v3.4 candidate regime tests
- 7 explain layer tests
- 4 minute_line wrapper tests
- ... + others

### 4.3 backfill 脚本

`scripts/backfill_intraday_minute.py`:
- 从 `output/<run>/trades.csv` 读 (date, code) → 拉 minute_line
- 11.6s 拉 73 active trades；9.3s 拉 138 全部 trades
- 写入 SQLite cache，下次重跑读 cache 不发 API

---

## 5. 未尽事项

- May-Jun 2026 cross-window 验证（等数据）—— 5d_dd2 dd 阈值 2% 是这个窗口的最优；新窗口可能不同
- 把 backfill 扩到 v3 candidate POOL（不只 active trades），让 confirmation_935 可在生产 mode 跑
- Per-mode multi-day 偏好（哪些 mode 最适合 5d_dd2，哪些更适合 1d）—— 可能进一步优化
- Phase C R3/R4/R5 SOP 同 R2 流程做 sub-axis discovery

---

## 6. 给未来自己的话

这一轮验证了**两个独立的 framework 上限突破**：
1. Phase B：把 prediction frame 从 1d 升级到 5d + trailing stop，捕到 trend continuation 的多日 tail
2. Phase D：minute-level entry-timing axis（drawdown_from_peak）正交于 EOD 筛选，提供独立 alpha

但同时验证了**两个 SOP 误判**：
1. v3.4 framework 升级（A8）—— DBR drop + momentum/limitup bonus axes 是 wash
2. 0419 9-step 弱转强 SOP combo —— 在 backtest universe 上 anti-predictive

第一性原理 + 数据驱动校准是唯一的安全网。**下次想到任何「按 SOP 应该这样」的想法，先回到这份报告看实证证据。**
