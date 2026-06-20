# 小草复利飞轮（The Compounding Flywheels）

**以终为始**：xiaocao 的终态是**三个相互喂养的复利飞轮**——钱、经验、本事各自滚雪球，串成一个大环。`scripts/flywheel_selfcheck.py` 随时报告三个飞轮的诚实健康度（① 资金 / ② 能力 自动转；③ 策略 = 人工门）。

```
   ┌─────────────────────────────────────────────────────────────┐
   ▼                                                             │
 ①资金飞轮 ──产出 标注数据+决策日志──▶ ②能力飞轮                   │
 (钱滚钱)                              (经验滚经验)                │
   ▲                                      │ 产出"验证过的 edge"     │
   │                                      ▼                       │
   └──③更强策略回喂更高收益── ③策略飞轮 ◀──(②→③ 当前断点)─────────┘
                            (本事变强 · 人工门)
```

- **① 资金飞轮**（钱滚钱）：每天交易，赚的钱进账户，次日用更新后的本金继续买。✅ **闭环真的在转。**
- **② 能力飞轮**（经验滚经验）：每天把"信号→真实次日结果"存进 `training_rows.parquet`，纪律护栏判定有效/假象，裁决入 `HYPOTHESES.jsonl`；`already_refuted` 让 runner 跳过死方向。✅ **测量端自动转**（裁决说真话——真实数据上 K→P 为 REJECTED）。
- **③ 策略飞轮**（本事变强）：某假设通过纪律（PASS）→ 改参（`params.py` 唯一入口，冻结约束）/重训 → 明天更强 → 回喂 ①。🟡 **actuator 腿是有意的人工门，尚未自动闭环**；当前无 PASS 可喂（K→P 被 REJECTED），所以**正确地停着**。若未来出现 PASS 却无 actuator，自检会转 🔴 `blocked`。
- **三环耦合**：① 产出数据喂 ②，② 产出验证过的 edge 喂 ③，③ 产出更强策略回喂 ①。**当前断点在 ②→③**（无验证过的 edge + actuator 未接线）；大环 `fully_closed=False` 是诚实状态，不是 bug。

> 设计纪律：actuator 自动化是**有意推迟**的——自动改参会违反 [train+test 双改善] 纪律。先做"PASS→参数提案→人 confirm→受 guard 写回"的半自动，保留人在环。

## ① 资金复利（money compounds）

| 时点 | 步骤 | 实现 |
|---|---|---|
| 9:25 morning | recommend + ★/★B + 集合竞价快照 + paper-record(成交=min(VWAP,L)) | `auto_daily.sh morning` → `live_recommend.py`, `paper_record.py` |
| 盘中 | staged exit：盘中仅 HARD_STOP(dd≥8%)，其余诊断递延 14:55；每轮写决策日志；卖点→飞书 | `live_monitor.py` → `live/exit_policy.py`, `live/journal.py`, `live/notify.py` |
| 15:05 eod | settle book A(验证口径) / decompose PnL / **status 摘要→飞书** / pipeline 健康检查 | `auto_daily.sh eod` → `settle_book_a.py`, `decompose_pnl.py`, `status.py`, `continuous_optimize.py` |

复利的护栏：**双钥匙资金安全边界**（`live/safety.py`，paper→real 需两把钥匙，agent 无法自签）、**book A vs book B** 双账本（实盘止损口径 vs 验证 next-close 口径，差值即"止损层是否帮倒忙"）、**kill-switch**（book A 近5出场日 <-3% 减半 / <-5% 停买，sensor 永不停）。一切口径见 `docs/OPERATING_CONTRACT.md`。

## ② 能力复利（the system gets smarter）

每个 eod，`forward_eval` 把当日信号 join 真实次日收盘，累积进 `training_rows.parquet`（标注数据只增）。每周（或按需）`auto_daily.sh optimize`：

1. `continuous_optimize.py` 把累积数据按"每笔 pick vs 当日 take-all 均值"构造逐笔结果；
2. 过 `research/guards.py` 的**纪律护栏**：cache-only、足够交易日、**逐笔非日度等权**、walk-forward train+test、多重比较显著性——**任一不过即 REJECTED**；
3. 裁决写入 `kronos_screen/HYPOTHESES.jsonl` 知识账本（STATE.md 手写日志的可执行继任者）；`continuous_optimize` 每轮 `ledger.already_refuted(id)` 复核已证伪方向：仍**重新评估**（数据增长可能翻盘），但**裁决无变化即不重复入账**（账本是变更日志，非心跳）。

**诚实性内建**：harness 拒绝把"日度等权 +254% 假象"洗成 headline——逐笔护栏会戳穿它。在当前真实数据上，flywheel 自动复现 STATE.md 的结论：K→P 二级筛选 **REJECTED**（逐笔 spread −1.2%，p=0.33，walk-forward 不一致）。飞轮说真话。

任意假设：从 cache 产出 `{day, strat_ret, base_ret}` jsonl，`research_run.py` 给出裁决并可入账本。

## ③ 策略复利（本事变强 · actuator，人工门）

② 产出一个 **PASS** 裁决时，③ 把它变成更强的策略：改一个参数（`strategy/params.py` 是唯一改值入口，受 `frozen` 约束）或重训模型（`build_scorer.py`），明天的策略就比今天强，回喂 ① 赚更多。

**现状诚实**：这根 actuator 腿是**有意的人工门，尚未自动闭环**——自动改参会违反"train+test 双改善"纪律，所以先保留人在环。`flywheel_selfcheck.py` 对 ③ 给三态：

- `open`（🟡）：无 PASS 待应用——**当前状态**（K→P 被 REJECTED，本就无 edge 可喂，正确地停着）；
- `blocked`（🔴）：有 PASS 待应用却无 actuator（`scripts/apply_verdict.py` 不存在）——**真实缺口**，自检会告警；
- `closed`（🟢）：actuator 已接线（未来：PASS→参数提案→人 confirm→受 guard 写回）。

因此大环 `rings.fully_closed=False` 是**诚实状态**，断点在 **②→③**（无验证过的 edge + actuator 未接线），不是 bug。

## 自动化节奏（Codex automations）

| 任务 | 步骤 | 中国时间 |
|---|---|---|
| morning | `auto_daily.sh morning` | 工作日 09:23 |
| 盘中监控 dense/sparse/1455 | `live_monitor.py --execute-sells` | 09:35–14:55 多档 |
| eod | `auto_daily.sh eod`（含数据体检 + 飞书日报 + pipeline 健康检查；**周五自动 record 能力飞轮裁决入账本**） | 工作日 15:10 |
| optimize（能力飞轮，按需） | `auto_daily.sh optimize` | 手动/补跑 |

能力飞轮**无需独立调度器**：eod 每日健康检查，**周五自动 `--record`** 一条裁决入 `HYPOTHESES.jsonl`（既有 eod cron 即可驱动）。`optimize` 步骤保留作按需补跑。

## 运维与监控（一条命令看全局）

```bash
python3 scripts/flywheel_selfcheck.py          # 三个飞轮健康度 (① ② 自动转 / ③ 人工门 open|blocked|closed)
python3 scripts/status.py                       # book A/B 价差 + 今日决策 + 持仓 (--push-feishu)
python3 scripts/show_journal.py --date today    # 今天各 run 的结构化决策（跨上下文连续性）
python3 scripts/continuous_optimize.py          # 当前 pipeline 在纪律下的诚实裁决
```

激活飞书推送：`export XIAOCAO_FEISHU_WEBHOOK=...`（可选 `XIAOCAO_FEISHU_SECRET`）。
上真金（终局）：`XIAOCAO_LIVE_TRADING_ENABLED=true` + `scripts/authorize_live.py` 铸造签名授权（两把钥匙）。在此之前，real-capital 路径结构上被 `live/safety.py` 硬拒。
