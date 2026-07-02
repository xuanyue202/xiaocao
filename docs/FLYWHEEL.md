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

> 设计纪律（2026-07-02 快速探索期）：actuator 不再是纯冻结的人肉门。weekly deep review
> 可以在 paper/simulation/research/tooling 范围内自动应用 evidence-backed 改动并提交，但必须
> 有完整 `evidence_bundle`、固定输入来源、验证结果、dirty-file 边界和回滚说明。固定输入之外
> 或证据不足的发现只能变成 proposal，等人确认。

## ① 资金复利（money compounds）

| 时点 | 步骤 | 实现 |
|---|---|---|
| 9:25 morning | recommend + ★/★B + 集合竞价快照 + paper-record(成交=min(VWAP,L)) | `auto_daily.sh morning` → `live_recommend.py`, `paper_record.py` |
| 盘中 | staged exit：盘中仅 HARD_STOP(dd≥8%)，其余诊断递延 14:55；每轮写决策日志；卖点→WeCom relay | `live_monitor.py` → `live/exit_policy.py`, `live/journal.py`, `live/notify.py` |
| 15:05 eod | settle book A(验证口径) / decompose PnL / **status 摘要→WeCom relay** / pipeline 健康检查 | `auto_daily.sh eod` → `settle_book_a.py`, `decompose_pnl.py`, `status.py`, `continuous_optimize.py` |

复利的护栏：**双钥匙资金安全边界**（`live/safety.py`，paper→real 需两把钥匙，agent 无法自签）、**book A vs book B** 双账本（实盘止损口径 vs 验证 next-close 口径，差值即"止损层是否帮倒忙"）、**kill-switch**（book A 近5出场日 <-3% 减半 / <-5% 停买，sensor 永不停）。一切口径见 `docs/OPERATING_CONTRACT.md`。

## ② 能力复利（the system gets smarter）

每个 eod，`forward_eval` 把当日信号 join 真实次日收盘，累积进 `training_rows.parquet`（标注数据只增）。每周（或按需）`auto_daily.sh optimize`：

1. `continuous_optimize.py` 把累积数据按"每笔 pick vs 当日 take-all 均值"构造逐笔结果；
2. 过 `research/guards.py` 的**纪律护栏**：cache-only、足够交易日、**逐笔非日度等权**、walk-forward train+test、多重比较显著性——**任一不过即 REJECTED**；
3. 裁决写入 `kronos_screen/HYPOTHESES.jsonl` 知识账本（STATE.md 手写日志的可执行继任者）；`continuous_optimize` 每轮 `ledger.already_refuted(id)` 复核已证伪方向：仍**重新评估**（数据增长可能翻盘），但**裁决无变化即不重复入账**（账本是变更日志，非心跳）。

**诚实性内建**：harness 拒绝把"日度等权 +254% 假象"洗成 headline——逐笔护栏会戳穿它。在当前真实数据上，flywheel 自动复现 STATE.md 的结论：K→P 二级筛选 **REJECTED**（逐笔 spread −1.2%，p=0.33，walk-forward 不一致）。飞轮说真话。

任意假设：从 cache 产出 `{day, strat_ret, base_ret}` jsonl，`research_run.py` 给出裁决并可入账本。

### 判断先验 → 候选假设（小草蒸馏喂 ② 的入口）

小草大师班转录蒸馏出的能力层分两层，**严格区分 candidate 与 verdict**：

- **候选账本** `reference/experience/xiaocao_hypotheses.jsonl`：从转录提炼的**可证伪先验**（`status:"candidate"`），每条带 `implied_rule` / `operationalization` / `falsifiable_test`。**这是一摞未证伪的先验，不是裁决**，对脊柱权威 = 0。
- **裁决账本** `kronos_screen/HYPOTHESES.jsonl`：`research_run.py` 给出的 PASS/REJECTED **verdict**。

唯一晋级路径：**candidate → 操作化（cache-only 构造 `{day,strat_ret,base_ret}`）→ `research_run.py` 护栏（逐笔/walk-forward/train+test/多重比较）→ verdict 账本 → ③ 人工门**。回填 candidate 的 `status` 为 `tested:PASS/REJECTED` 避免重复 litigate（镜像 `ledger.already_refuted`）。

**红线**：playbook/REGIME_TIMELINE 先验只作 ① 资金飞轮的 **agent 判断输入**（morning 读现行 posture、eod 用出场纪律做异常分诊），**永不**短路 ②→③、永不进确定性脊柱；未测 candidate 对大环 `fully_closed` 贡献 = 0。一句话：**小草的话是假设源，不是 edge 源**——这正是他本人"标准+数据验证+当下适配"的元规则。

## ③ 策略复利（本事变强 · actuator，人工门）

② 产出一个 **PASS** 裁决时，③ 把它变成更强的策略：可能是纸面/模拟层的 emitted mode、cohort 规则、研究工具、报告字段，也可能是未来的人审核心参数/模型更新。快速探索期可以自动落地 paper/simulation/research/tooling 改动；real-capital、账户历史、安全逻辑和核心真相源仍然不能自动改。

**现状诚实**：这根 actuator 腿处在快速探索期的半自动状态。`flywheel_selfcheck.py`
仍会把 PASS 待消费但没有明确消费记录的状态报为 `blocked`；weekly deep review 是当前的消费器：
它生成固定输入 plan，Codex agent 可按完整 evidence_bundle 自动改 paper/simulation/research/tooling 代码，随后由
`weekly_deep_review.py --finalize` 写周报、ledger、allowlist stage 并 commit。`flywheel_selfcheck.py`
对 ③ 给三态：

- `open`（🟡）：无未消费 PASS 待应用；如果有已消费 PASS，会记录在 `reference/experience/applied_verdicts.jsonl`；
- `blocked`（🔴）：有 PASS 待应用但缺少消费记录或明确映射——**真实缺口**，weekly 应自动落地证据完整的纸面/模拟/工具改动；不完整则写 proposal；
- `closed`（🟢）：专用 actuator 已接线，能把合格 PASS/evidence 稳定转为受审计的改动。

因此大环 `rings.fully_closed=False` 是**诚实状态**，断点在 **②→③**（无验证过的 edge + actuator 未接线），不是 bug。

## 自动化节奏（Codex automations）

| 任务 | 步骤 | 中国时间 |
|---|---|---|
| morning | `auto_daily.sh morning` | 工作日 09:23 |
| 盘中监控 dense/sparse/1455 | `live_monitor.py --execute-sells` | 09:35–14:55 多档 |
| eod | `auto_daily.sh eod`（含数据体检 + WeCom relay 日报 + pipeline 健康检查；**周五自动 record 能力飞轮裁决入账本**） | 工作日 15:10 |
| optimize（能力飞轮，按需） | `auto_daily.sh optimize` | 手动/补跑 |

能力飞轮**无需独立调度器**：eod 每日健康检查，**周五自动 `--record`** 一条裁决入 `HYPOTHESES.jsonl`（既有 eod cron 即可驱动）。`optimize` 步骤保留作按需补跑。

## Weekly deep review（②→③ 消费器）

周五晚 20:30 中国时间运行 `xiaocao-weekly-deep-review`。它不是交易动作，而是把一周的
经验真正消费掉：

1. `auto_daily.sh weekly` 先跑短线/趋势 verdict record、`flywheel_sweep.py --top 30`、
   `distill_transcript.py --refresh-action-log`，再生成 `output/live/weekly_plan_<date>.json`。
2. Codex agent 读取 plan。只有固定输入清单内、带完整 `evidence_bundle`、可验证且目标文件非
   pre-existing dirty 的事项，才允许 `AUTO_APPLIED` 改 paper/simulation/research/tooling。
3. 固定输入之外、证据不够硬、或命中 dirty-file 的事项必须 `PROPOSAL_ONLY`，写入周报第一屏和
   `.scratch/weekly-deep-review/<date>/...md`。
4. `weekly_deep_review.py --finalize` 写 `output/live/weekly_review_<date>.md`、追加
   `output/live/flywheel_change_ledger.jsonl`、只 stage allowlist 文件并 commit 当前分支。

这让 ② 不只是“变重”，而是每周把 PASS、校准结果、action_summary、instrumentation 缺口和
研究证据消费成：自动改动、明确 proposal、或 no-action 结论。

## 运维与监控（一条命令看全局）

```bash
python3 scripts/flywheel_selfcheck.py          # 三个飞轮健康度 (① ② 自动转 / ③ 人工门 open|blocked|closed)
python3 scripts/status.py                       # book A/B 价差 + 今日决策 + 持仓 (--push-wecom)
python3 scripts/show_journal.py --date today    # 今天各 run 的结构化决策（跨上下文连续性）
python3 scripts/continuous_optimize.py          # 当前 pipeline 在纪律下的诚实裁决
```

激活 WeCom relay 推送：
`export XIAOCAO_WECOM_RELAY_URL=https://.../send`
`export XIAOCAO_WECOM_RELAY_TOKEN=...`
`export XIAOCAO_WECOM_USER_ID=...`
可选：`XIAOCAO_WECOM_ACCOUNT_ID=default`，自签证书场景设 `XIAOCAO_WECOM_INSECURE=true`。
Codex cron 推荐把这些变量写入本地未入库文件 `output/live/notify.env`；通知模块会自动读取。也可用 `XIAOCAO_NOTIFY_ENV_FILE=/path/to/notify.env` 指向其他位置。
上真金（终局）：`XIAOCAO_LIVE_TRADING_ENABLED=true` + `scripts/authorize_live.py` 铸造签名授权（两把钥匙）。在此之前，real-capital 路径结构上被 `live/safety.py` 硬拒。
