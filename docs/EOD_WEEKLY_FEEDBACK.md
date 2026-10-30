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

## 因果深度与下一交易窗口验收

按 Operating Contract §1e，复盘先回答“业务是否获得当日合法执行与有效观察”，
再分别评价策略收益、执行能力、账务可信度和学习质量。读取原 command/event、
首个失败和最新受影响运行；报告结论、状态名、退出码和测试数只帮助定位。

### 每日：把昨天的遗留变成明天可使用的处置

每项执行事故的 `items[].summary/basis/evidence_refs/next_action/next_verification`
及所引 `daily_review` 必须能回答以下问题，沿用现有 schema，不另造状态写者：

1. 原服务订单状态、已知业务限制、技术修复/部署、当前经济影响各是什么；
   用户已确认的限制与正式订单终态分别标记。修复权限过滤不冒充拒单证明，
   旧单缺终态也不自动成为下一整批的资金不足证明。
2. 下个合法窗口会调用哪些真实保护门，影响哪个账户/代码/lot/资金范围；
   哪些缺口可隔离延后，哪些是当前真实前置，未知金额如何保守界定。
3. 原 owner 在开盘前应完成什么恢复与验证；恢复入口、预算/截止和触发条件
   是否真实存在。只写“下一 owner 处理”或“等待自然验收”不算执行连续性证明。
4. 至少一条反事实挑战：保留原历史未决，但提供正确的新鲜现金/持仓/风险时，
   独立合法候选能否通过；移除真实约束会否误放行。工程故障、合理策略无动作、
   真实风险拒绝分别记账，不把未知窗口填为零收益或正常无交易。
5. 从直接触发追到机制和治理的 5 Why；每条因果边标明 observed/inference/unknown、
   原件、竞争解释和反证。第五问可以暴露未知，不能编一个“外部问题”或“测试
   不足”充数。还要问为什么预检、评审和昨天的复盘没有提前发现。

处置使用稳定问题 ID，并同时追踪根因类，避免旧 SELL 与旧 BUY、不同日期/代码
把同一“历史状态全局扩散”机制拆成互不相干的新问题。关闭的是明确的验证义务，
不是订单历史；修复状态、下一窗口就绪和正式会计最终性分别接受。

### 周度：检查机制是否真正改善系统

跨日读回上述处置及上一周回复，至少覆盖以下相互关联的视角：

- 投资/策略：合格机会、权限后替补、模式/篮子约束、组合分散与资金利用；
  未执行不能归因成策略没有机会，后来的上涨也不证明当时一定能成交。
- 金融风险/会计：当前可用资金、潜在预留/敞口、单位净值与真实暂停，
  已知限额、估计和最终 PnL 各自适用范围；检查漏计及重复扣减。
- 执行/系统：开盘关键路径、恢复耗时、异步响应绑定、故障影响范围、
  带副作用动作的唯一 claim、依赖隔离、版本采用与恢复入口。
- 数据/统计/算法：完整机会分母、受故障影响而缺失的样本、选择/幸存偏差、
  成本和时点、APP 与 paper/model 口径、有效独立样本与配对反事实。
- 产品/代理治理：用户目标是否变成可检查的完成标准、盘前处置是否可用、
  遇阻是否自主恢复、何时需要人、通知是否把状态误说成经济事实。
- 实验效率/运维：每个合法窗口的有效观察产出、工程漏执行率与重复根因、
  修复成本及自然复发。增加交易数不是单独的成功指标；不为样本伪造成交。

视角是检查线索，不是给事故硬套相同答案。每个重大结论均须有原件、因果机制、
影响和不确定性、修复/实验、owner、反证及验收窗口。区分直接触发、促成因素、
设计根因和复盘失效，不用五个相似的“为什么”替代因果链。

先完成当前执行确定性修复，再按现有最多三个策略实验槽选择最有价值的假设；
恢复工程不占用或伪装为策略 alpha 实验。策略收益/参数晋级仍受原协议与 §10。
未来行为改动须通过独立 Standards/Spec 复核，并分别记录实现、受影响验证、
部署采用和下一自然窗口结果。本文提高语义审阅要求；现有 JSON 验证器仅检查
已实现字段/引用，不声称程序能自动认证因果深度或下一窗口可交易。
