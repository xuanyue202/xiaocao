# 小草复利飞轮（The Compounding Flywheel）

**以终为始**：xiaocao 的终态是一个**自我维持、双重复利**的 agent-native 交易系统。两个飞轮每个交易日各转一圈，互相喂养。`scripts/flywheel_selfcheck.py` 随时验证两个飞轮都已接好、能转（🟢 SPINNING）。

```
        ┌──────────────────── 资金复利 (capital) ────────────────────┐
        │  9:25 morning        盘中 staged exit       15:05 eod        │
        │  recommend+paper ──▶ live_monitor ───────▶ settle/digest    │
        │  (safety 双钥匙)      (HARD_STOP盘中,         (book A/B,       │
        │                       其余递延14:55)          kill-switch)    │
        └───────────┬─────────────────────────────────────┬──────────┘
                    │ 每日产出: 决策日志 + 标注数据          │ 飞书日报/告警
                    ▼                                       ▼
        ┌──────────────────── 能力复利 (capability) ─────────────────┐
        │  training_rows.parquet ──▶ research guards ──▶ HYPOTHESES   │
        │  (eod forward_eval 累积)    (纪律内建,不可作弊)   ledger      │
        │                                    │ PASS 才放行               │
        │                                    ▼                          │
        │                          gated retrain ──▶ 更聪明的下一轮      │
        └────────────────────────────────────────────────────────────┘
```

## 资金复利（money compounds）

| 时点 | 步骤 | 实现 |
|---|---|---|
| 9:25 morning | recommend + ★/★B + 集合竞价快照 + paper-record(成交=min(VWAP,L)) | `auto_daily.sh morning` → `live_recommend.py`, `paper_record.py` |
| 盘中 | staged exit：盘中仅 HARD_STOP(dd≥8%)，其余诊断递延 14:55；每轮写决策日志；卖点→飞书 | `live_monitor.py` → `live/exit_policy.py`, `live/journal.py`, `live/notify.py` |
| 15:05 eod | settle book A(验证口径) / decompose PnL / **status 摘要→飞书** / pipeline 健康检查 | `auto_daily.sh eod` → `settle_book_a.py`, `decompose_pnl.py`, `status.py`, `continuous_optimize.py` |

复利的护栏：**双钥匙资金安全边界**（`live/safety.py`，paper→real 需两把钥匙，agent 无法自签）、**book A vs book B** 双账本（实盘止损口径 vs 验证 next-close 口径，差值即"止损层是否帮倒忙"）、**kill-switch**（book A 近5出场日 <-3% 减半 / <-5% 停买，sensor 永不停）。一切口径见 `docs/OPERATING_CONTRACT.md`。

## 能力复利（the system gets smarter）

每个 eod，`forward_eval` 把当日信号 join 真实次日收盘，累积进 `training_rows.parquet`（标注数据只增）。每周（或按需）`auto_daily.sh optimize`：

1. `continuous_optimize.py` 把累积数据按"每笔 pick vs 当日 take-all 均值"构造逐笔结果；
2. 过 `research/guards.py` 的**纪律护栏**：cache-only、足够交易日、**逐笔非日度等权**、walk-forward train+test、多重比较显著性——**任一不过即 REJECTED**；
3. 裁决写入 `kronos_screen/HYPOTHESES.jsonl` 知识账本（STATE.md 手写日志的可执行继任者）；`ledger.already_refuted(id)` 让 agent 跳过死方向；
4. 仅当 PASS 才考虑重训/换参（参数改动的唯一入口；受 `strategy/params.py` 冻结约束）。

**诚实性内建**：harness 拒绝把"日度等权 +254% 假象"洗成 headline——逐笔护栏会戳穿它。在当前真实数据上，flywheel 自动复现 STATE.md 的结论：K→P 二级筛选 **REJECTED**（逐笔 spread −1.2%，p=0.33，walk-forward 不一致）。飞轮说真话。

任意假设：从 cache 产出 `{day, strat_ret, base_ret}` jsonl，`research_run.py` 给出裁决并可入账本。

## 自动化节奏（Codex automations）

| 任务 | 步骤 | 中国时间 |
|---|---|---|
| morning | `auto_daily.sh morning` | 工作日 09:23 |
| 盘中监控 dense/sparse/1455 | `live_monitor.py --execute-sells` | 09:35–14:55 多档 |
| eod | `auto_daily.sh eod` | 工作日 15:10 |
| **optimize（能力飞轮）** | `auto_daily.sh optimize` | 每周（建议交易日周五 eod 后） |

## 运维与监控（一条命令看全局）

```bash
python3 scripts/flywheel_selfcheck.py          # 两个飞轮是否接好、能转 (🟢/🔴)
python3 scripts/status.py                       # book A/B 价差 + 今日决策 + 持仓 (--push-feishu)
python3 scripts/show_journal.py --date today    # 今天各 run 的结构化决策（跨上下文连续性）
python3 scripts/continuous_optimize.py          # 当前 pipeline 在纪律下的诚实裁决
```

激活飞书推送：`export XIAOCAO_FEISHU_WEBHOOK=...`（可选 `XIAOCAO_FEISHU_SECRET`）。
上真金（终局）：`XIAOCAO_LIVE_TRADING_ENABLED=true` + `scripts/authorize_live.py` 铸造签名授权（两把钥匙）。在此之前，real-capital 路径结构上被 `live/safety.py` 硬拒。
