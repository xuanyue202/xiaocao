# Per-mode multi-day exit tune (Plan B follow-up)

- Source: `output/xiaocao_8mo_v3_baseline/signals_*.json` re-scored under each variant
- Entry uniformly = 9:30 open (T+1 compatible, validated_v3 baseline)
- v5 ship default = `5d_dd2` (5d hold + max_dd 2%)

## Global (all modes combined)

| variant | n | avg | win | sum |
|---|---|---|---|---|
| 1d_baseline | 73 | 3.399% | 56.2% | 248.1% |
| 2d_hold_to_n | 73 | 4.037% | 52.1% | 294.7% |
| 3d_hold_to_n | 73 | 2.66% | 49.3% | 194.2% |
| 5d_hold_to_n | 73 | 1.648% | 34.2% | 120.3% |
| 3d_dd2 | 73 | 6.417% | 56.2% | 468.5% |
| 3d_dd3 | 73 | 5.556% | 57.5% | 405.6% |
| 5d_dd2  ← v5 default | 73 | 6.392% | 56.2% | 466.6% |
| 5d_dd3 | 73 | 5.499% | 57.5% | 401.4% |
| 5d_dd4 | 73 | 4.883% | 54.8% | 356.4% |
| 7d_dd2 | 73 | 6.392% | 56.2% | 466.6% |
| 7d_dd3 | 73 | 5.499% | 57.5% | 401.4% |
| 10d_dd3 | 73 | 5.499% | 57.5% | 401.4% |

## Per-mode best variant (sorted by trade count)

| mode | n | best variant (by avg) | avg | win | v5(5d_dd2) avg | Δ avg |
|---|---|---|---|---|---|---|
| 接力低弱转1 | 29 | 3d_dd2 | +7.32% | 48.3% | +7.23% | +0.10pp |
| 首红断低吸 | 21 | 3d_dd2 | +7.64% | 76.2% | +7.64% | +0.00pp |
| N字低吸 | 13 | 5d_dd2 | +5.52% | 53.8% | +5.52% | +0.00pp |
| 绿断低吸 | 10 | 3d_dd2 | +2.48% | 40.0% | +2.48% | +0.00pp |

## Per-mode full matrix (avg returns by variant)

| mode | 1d_baseline | 2d_hold_to_n | 3d_hold_to_n | 5d_hold_to_n | 3d_dd2 | 3d_dd3 | 5d_dd2 | 5d_dd3 | 5d_dd4 | 7d_dd2 | 7d_dd3 | 10d_dd3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 接力低弱转1| +3.56% (n=29)| +3.64% (n=29)| +3.15% (n=29)| +3.35% (n=29)| +7.32% (n=29)| +6.48% (n=29)| +7.23% (n=29)| +6.34% (n=29)| +5.75% (n=29)| +7.23% (n=29)| +6.34% (n=29)| +6.34% (n=29) |
| 首红断低吸| +5.69% (n=21)| +6.72% (n=21)| +4.99% (n=21)| +3.45% (n=21)| +7.64% (n=21)| +6.71% (n=21)| +7.64% (n=21)| +6.71% (n=21)| +6.34% (n=21)| +7.64% (n=21)| +6.71% (n=21)| +6.71% (n=21) |
| N字低吸| +2.61% (n=13)| +5.45% (n=13)| +3.41% (n=13)| -0.61% (n=13)| +5.45% (n=13)| +4.82% (n=13)| +5.52% (n=13)| +4.79% (n=13)| +4.07% (n=13)| +5.52% (n=13)| +4.79% (n=13)| +4.79% (n=13) |
| 绿断低吸| -0.85% (n=10)| -2.28% (n=10)| -4.62% (n=10)| -4.15% (n=10)| +2.48% (n=10)| +1.43% (n=10)| +2.48% (n=10)| +1.43% (n=10)| +0.39% (n=10)| +2.48% (n=10)| +1.43% (n=10)| +1.43% (n=10) |

## Decision framework

- If a mode's best variant is `5d_dd2` → ship v5 default applies
- If best avg differs by ≥ 0.5pp AND n ≥ 8 → consider per-mode override
- If best is hold_to_n variants (no max_dd) → that mode benefits from no trailing stop
- If n < 5 → keep v5 default; insufficient sample for per-mode tune

## 关键发现 (2026-04-26)

**1. Per-mode override 不必要**：4 个 mode（≥10 trades）全部 best variant 是 dd=2% 系列；Δ 全 ≤ 0.10pp 噪声级。v5 一刀切 `5d_dd2` 已等同 per-mode 最优。

**2. hold_days≥3 后 max_dd 已 saturate**：3d_dd2 ≈ 5d_dd2 ≈ 7d_dd2 = 10d_dd2。Trailing stop 几乎都在前 3 日触发，多日持仓边际归零。可以把 v5 收到 3d 减少最坏情况持仓时间，收益 ~0.03pp 不值得动 default。

**3. `hold_to_n` 系列（无 max_dd）全部劣于 dd 系列**：3d_hold_to_n / 5d_hold_to_n 反而比 1d 还差。Trailing stop 是 Phase B 的真正 alpha 来源，单纯延长持仓不够。

**4. dd 阈值 sweep — dd=0.5% 反而是 backtest-optimal 但有 over-fit 风险**：

| dd_pct | avg | win | sum |
|---|---|---|---|
| 0.5 | **+6.88%** | 47.9% | **+502.1%** |
| 1.0 | +6.62% | 52.1% | +483.4% |
| 1.5 | +6.65% | 53.4% | +485.6% |
| 2.0 | +6.42% | 56.2% | +468.5% (v5 ship) |
| 2.5 | +5.97% | 57.5% | +435.8% |

dd=0.5% 比 dd=2.0% 多 +0.46pp avg / +33pp sum。但有显著 bull-period 嫌疑：
- 这个 8mo 窗口 (Sep25-Apr26) bull-leaning
- dd=0.5% 在 bear 期 = 「次日低点必触发 = -0.5% 锁损」（noise > 0.5%）
- dd=2.0% 容忍正常震荡，跨 regime 更稳

**ship 决定**：v5 维持 dd=2.0%。等 cross-window (2025-04 → 2025-08) 验证后再决定是否调成 0.5%（如果 cross-window 也偏好 0.5% → 真信号；否则就是 over-fit）。
