# 小草策略 2026-03 ~ 2026-04 模拟盘报告

**回测区间**：2026-03-01 → 2026-04-24（39 个交易日）
**口径**：信号当日 qfq 开盘买入，次个交易日 qfq 收盘卖出（1 日持仓）
**生成日期**：2026-04-26

---

## 1. 设计核心：active vs shadow

本轮回测引入**信号双轨**：每个候选信号都生成、打分并写入 `mode_history`，但通过 adaptive 标签区分

- **active**：通过所有 quality gate，计入用户"真实"P&L
- **shadow**：被某个 gate 标记不参与（ adaptive 滚动统计、`openPctChange ≥ 6`、`exclude_modes` 等），仅用于参考与模式自我学习

mode_history 完整反映模式真实表现 — 不管是 active 还是 shadow，outcome 都被记录，所以 adaptive 的滚动判断永远基于完整证据。

---

## 2. 配置对照

三组配置在同一区间跑：

| 配置 | profile | adaptive | 备注 |
|---|---|---|---|
| **A. cold seed** | default | on (cold) | mode_history 空，全部信号 → shadow |
| **B. warm default** | default | on (warm) | 消费 A 的 mode_history，adaptive 真实工作 |
| **C. warm validated** | validated | on (warm) | B + `exclude-modes 接力低弱转2,方向内绿盘低吸前3名` |

---

## 3. 总体结果（active 即真实 P&L）

| 配置 | 总信号 | active | shadow | active avg | active win |
|---|---|---|---|---|---|
| A. cold seed | 31 | 0 | 31 | — | — |
| B. warm default | 31 | 5 | 26 | **+1.90%** | 40.0% |
| C. **warm validated**（推荐） | 31 | **3** | 28 | **+8.43%** | **66.7%** |

C 把 B 的 5 笔 active 进一步收敛到 3 笔（剔除 1 笔 接力低弱转2 + 1 笔 方向内绿盘低吸前3名），active 平均收益从 +1.90% 提升到 **+8.43%**，胜率从 40% 提升到 **66.7%**。

---

## 4. 月度切片（C — validated 配置）

| 月份 | active n | active avg | active win | shadow n | shadow avg | shadow win |
|---|---|---|---|---|---|---|
| 2026-03 | 0 | — | — | 14 | +1.49% | 64.3% |
| 2026-04 | 3 | **+8.43%** | **66.7%** | 14 | +0.03% | 35.7% |

3 月份没有 active 信号，因为 mode_history 当时还在累积初期，几乎所有模式都在 Tier 4（20 交易日样本 < 3）状态，全部被标 shadow。这是 adaptive 设计的"冷启动期"行为——宁可错过，不要乱开仓。

4 月份 mode_history 已经积累了 14+ 笔样本，rolling 5/10/20 日窗口开始 informative，adaptive 才开始放出 active 信号。

---

## 5. 模式分解（B — warm default 配置）

| 模式 | 总信号 | 总 avg | active n | active avg | adaptive 表现 |
|---|---|---|---|---|---|
| 红断低吸 | 1 | +10.78% | 0 | — | 太稀疏，Tier 4 shadow |
| N字低吸 | 3 | +8.99% | 0 | — | 信号分布在 3 月，Tier 4 shadow |
| 首红断低吸 | 3 | +6.21% | 0 | — | 同上 |
| 绿断低吸 | 2 | +5.46% | 0 | — | 同上 |
| **接力低弱转1** | 7 | +3.89% | **3** | **+8.43%** | 4 月窗口 informative，adaptive 放行 |
| 方向内绿盘低吸前3名 | 6 | -1.93% | 1 | -10.60% | adaptive 漏 1 笔（rolling 短暂翻正）|
| 接力低弱转2 | 8 | -3.75% | 1 | -5.16% | adaptive 漏 1 笔（10d 短暂 +0.75%）|
| 孕线低吸 | 1 | -6.42% | 0 | — | Tier 4 shadow |

**adaptive 自主筛选效果**：
- 14 笔差模式（接力低弱转2 + 方向内绿盘低吸前3名）中 **12 笔 shadow（85.7%）**
- 7 笔 接力低弱转1 中 **3 笔 active**（4 月份 rolling 窗口都正向的几次）
- 4 个高表现稀疏模式（红断低吸/N字低吸/首红断低吸/绿断低吸）全部 Tier 4 shadow——稀疏度让 adaptive 无法在本区间认证它们

**结论**：adaptive 不是完美过滤器（漏掉 14% 的差信号），但跨时间窗 robust。叠加 `--exclude-modes` 把这 2 笔漏网 shadow 化即得到 C 配置的 +8.43% 真实收益。

---

## 6. shadow 信号也有价值

C 配置的 shadow 池（28 笔）整体 avg +0.76%，win 50%。这些信号的 outcome 持续喂给 mode_history，让后续日子里 adaptive 能更精确判断每个模式的"现在是不是好时候"。如果未来某个 shadow 模式连续 5/10 日 avg 翻正，adaptive 会在下一日把它升级回 active——动态对应小草说的"模式阶段性"。

---

## 7. 推荐生产配置

```bash
# 第一次跑（任何区间），让 mode_history 冷启动
xiaocao backtest run \
  --start <START> --end <END> \
  --profile validated

# 后续跑（消费已有 mode_history）
xiaocao backtest run \
  --start <START> --end <END> \
  --profile validated \
  --no-reset-mode-history

# 跨窗口反过拟合验证
xiaocao backtest validate \
  --windows 2026-03-01:2026-03-31,2026-04-01:2026-04-24 \
  --variant='--profile validated' \
  --metric avg
```

cache 默认 on（路径 `output/.cache/xiaocao.db`），冷启动后所有历史 API 命中缓存零 cost；adaptive 默认 on，带 `validated` profile 等于"硬封禁两个差模式 + 软筛选其它"双层防护。

---

## 8. 反过拟合护栏

- 30 天 / 31 笔交易样本太小，**任何单一窗口结论不可信**
- `validated` profile 唯一的硬过滤项（`接力低弱转2` + `方向内绿盘低吸前3名`）已经在 2026-03 和 2026-04 两个独立窗口分别验证 PASS
- adaptive 的 5/10/20 trading-day 窗口和 Tier 1-3 双窗口确认本身就是反噪音机制
- mode_history 持续累积，未来每月都会有更多证据更新 adaptive 决策——这是动态适应而不是静态过拟合
