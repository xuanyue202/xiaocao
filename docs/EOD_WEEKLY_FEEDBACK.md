# EOD → Weekly 复盘交接

EOD 的价值是证明当天执行、账本和学习证据是否可信，修复可独立处理的确定性故障，并留下可验收的下一步。Weekly 负责跨日归纳原因、评判实验和设计、集中优化。二者都不能用报告增长代替策略收益证明。

## 每日收尾

原 paper EOD、APP EOD 保留既有原始入口并等待终态。之后 statement、funded research EOD、KOL feedback 的三个规范命令分别由以下入口启动一次、等待并保留真实 exit/身份/时钟/输出哈希回执（不要再直接重复启动子命令）：

```bash
CODEX_AUTOMATION_ID=xiaocao-daily-eod PYTHONPATH=src .venv/bin/python scripts/eod_post_business.py --step statement
CODEX_AUTOMATION_ID=xiaocao-daily-eod PYTHONPATH=src .venv/bin/python scripts/eod_post_business.py --step research
CODEX_AUTOMATION_ID=xiaocao-daily-eod PYTHONPATH=src .venv/bin/python scripts/eod_post_business.py --step feedback
```

每步 claim 按精确 Automation ID/日期/step 持久保存。失败、受中断或缺 terminal 都不允许替代进程重跑；stdout JSON 与诊断流分开保留。完成执行复盘与必要修复。纸面 shell 不再提前推最终消息。先运行只读上下文：

```bash
PYTHONPATH=src .venv/bin/python scripts/eod_closeout.py --context --date YYYY-MM-DD
```

根据原始回执制作 `output/live/eod_feedback_review_<date>.json`，按 `src/xiaocao/research/eod_feedback.py` 校验字段。顶层为 `schema_version=1, authority=0, date, automation_id=xiaocao-daily-eod, thread_id, reviewed_at`，保留初始 scheduler 的线程身份；reviewed_at 为带时区的真实复盘结束时间，晚于三个 post-business 终态。

`evidence` 为角色到 `{path, sha256}` 的映射，path 相对当前仓库：

- `paper_terminal` 与 `paper_manifest`：同一原始 supervisor archive。
- `app_eod`：本 owner 本日原始 APP EOD archive。
- `statement`：已执行一次的 statement 的原 report_path。
- `research`、`feedback`：已终止原命令的原 JSON stdout 文件，不再运行报告。
- `statement_terminal`、`research_terminal`、`feedback_terminal`：上方三个入口返回的原 terminal_path；`statement_stdout` 为 statement 终态绑定的 stdout 文件。诊断流也加入具名引用。date/owner/exit/argv/stdout 必须逐项匹配。
- `daily_review`：已完成的 dated 执行复盘。可增加原件角色。

每个 `items[]` 必须有稳定 `id`、`kind`（issue/experiment/design/finding）、`status`、`summary`、`owner`、`next_action`、`next_verification`、`falsifier`、`basis`（observed/inference）和 `evidence_refs[]`。相同原因跨日沿用 id，变化的证据和影响写进新日记录，不以时钟重新命名问题。

- issue 的 `repaired` 只表示代码已修。`verified` 另需 `verification.code_commit`（完整 SHA）、`tests[]` 和 `natural[]`，后两者必须属于该项 evidence_refs。审核实际行为，文件存在不代表验收通过。外部订单/费用缺口可以保留 open，不要求伪造代码修复。
- experiment 必须写 `effective_samples`、`sample_unit` 和 `comparable`；零有效样本或不可比时 status 必须为 insufficient_evidence。沿用已有预注册 ID；不把每日净值行当独立交易，不从 APP/paper 差异推断 KOL alpha。
- design 必须写 `acceptance`，仅跟进已登记设计的有限、可证伪标准。偏离记录 observed/inference、合理解释或待修原因；不扫描任意聊天、不扩大当日语义工作。
- finding 记录有用但尚未晋级的结论、适用范围与反证。

验证完成后，同一 EOD owner 运行一次：

```bash
CODEX_AUTOMATION_ID=xiaocao-daily-eod PYTHONPATH=src .venv/bin/python scripts/eod_closeout.py --review output/live/eod_feedback_review_YYYY-MM-DD.json --push-wecom
```

入口只读原件和 SQLite 已保存观测，验证日期、owner、两分支终态及 statement/digest 的同一 observation。失败前不发送。它冻结交接及所引原件字节到 `output/live/review_feedback/`，每日期一份不可改写；最终摘要按 APP 模拟 B、纸面 B、T 顺序，沿用现有 outbox 和共享 durable delivery claim。现金/实际费用未闭合仍为最终盈亏 N/A。

research 原命令 exit=0 的 `not_started`（尚无 funded morning、报告已保存）或 `NON_TRADING_DAY` 是合法无动作终态。保留确切 research_status，不把它们当成已产生模型成交/有效样本，也不因此阻断已完成 EOD 的交接；未知或失败结果仍阻断。

若原业务失败、无合法同日证据或收尾无法通过，保留本地失败证据、当前缺口和下一负责人；不得回放业务来补报告。记录成功不等于发送成功，检查 delivery。不确定送达只走 exact-claim reconciliation；安全重试仍用 trading_change_notice，不重跑 closeout/status 造新消息。`--review` 不带 --push-wecom 用于明确不发送的本地验收。

旧运行缺少新增 post-business 终态回执时，只能按原工具输出做标明 legacy_read_only_handoff 的本地交接；不能补造终态、回放子命令或以此发送新版收尾。首次完整验收等待下一个合法原始运行。

## 周度必回应与回流

`weekly_evidence` 在原有内容寻址 inventory 中冻结每日记录及它们的原件副本，产出 `data_evidence_review.eod_feedback`。未完成事项不因超过七天/十二周消失；已验证旧修复保留审计，不反复占用处理列表。缺失/损坏记录显示 evidence_gap，旧日期不会被重建。

周度状态另保存每项对应的原 daily receipt 引用。原件丢失或损坏时，未决回复仍保留 id、负责人和下一步，明确显示 evidence_gap；必须回应并说明缺证，不能以空清单或 close 消掉义务。存续账本只能证明这些跟进义务，不能重建缺失原件的类别、历史事实或验证状态。

Weekly 在 `eod_feedback_responses[]` 逐项写 `id, disposition, rationale, owner, next_action, next_review, evidence_refs`。disposition 为 continue/deepen/verify/close/needs_evidence/stop_proposal；next_review 必须晚于本次日期，证据引用必须来自冻结 inventory。跨日集中分析共因、预防测试、有效实验样本、设计偏离的收益/成本与可证伪解释；读原始失败与最近运行，不能只抄每日结论。若存在输入错误，另写 `eod_feedback_gap_review` 说明具体缺口。

finalizer 在写报告/ledger 前重建冻结输入并强制完整回应。未经自然验证的 issue 不能 close。策略实验的 stop_proposal 是研究建议，执行与晋级仍受原协议和 §10 限制。回复写入现有 `flywheel_change_ledger.jsonl.eod_feedback_state`，带 manifest hash 与状态 hash；下一 EOD 的 --context 回读该回复及负责人。此交接没有加入策略 AUTO_APPLIED 的固定输入白名单，也不关闭 UNKNOWN、结算或费用任务。

自然验收：下一合法 EOD 应证明摘要晚于全部原始业务终态且产生每日交接；下一原始 Weekly 应证明读取这些交接、逐项回应、ledger 回流。配置成功和测试通过均不替代这两次自然运行。
