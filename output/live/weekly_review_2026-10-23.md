# 小草每周深度复盘 2026-10-23

## 先看结论

- 本周证据要求把弱市防守、可执行的模式资格与资金参与度分开。小草的空仓优先仍保留轻仓参与和放量转强反证；多位作者的相同风险叙事不算独立成功样本。
- 原周度命令仅一次且失败，未生成原计划；本报告从125份原研究快照与有真实接续时点的KOL库存完成只读复核，原失败保持，不重跑、不回填。
- 修复等待契约误入终态库存、shell误报计划ready，以及APP失败读取未归档原始坏格三项运行取证问题；不改变E/COLD、资金、交易或结算权限。
- 研究保留原三个槽位并接到已登记M/open-limit/no-KOL资金账户。四组首日各一计划均未成交，日历只证明至10月23日；58组同入场退出配对不是KOL盈利证明。
- 本轮无需新增策略或资金批准：研究继续只读维护，永久晋级仍缺同资金、真实费用、点时可成交及样本外证据。APP最终净利润N/A；具体待核留审计。
- 本周21条知识路由已从原action-log快照恢复，引用蒸馏文件全部匹配原Git基线；笼统面板/观测建议缺字段、点时、基线和验证契约，不作自动落地候选。
- 本周模式：保留提案，证据不足不晋级（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：0 个；另有 1 条本地工作区提醒，见下一节。
- APP 执行故障复核：未结计划 2，阻断检查点 4，缺失 EOD 1，缺失结算日 4，缺失日复盘 1；逐项核对卖价/买盘/成交窗口及后续买入影响，不能只归为外部状态。
  - 未结 `book-b:2026-09-18:000572.XSHE:SELL:087c4339d890`：unknown / NATIVE_HISTORY_QUERY_CAPTURE_INCOMPLETE；委托 6007019；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=ba90b6125c797945f9747fc9f0ef3e1a3ee5736da36acc0de7a5f24712e2dfeb）
  - 未结 `book-b:2026-09-30:301382.XSHE:SELL:9c1cb5e059e5`：unknown / NATIVE_HISTORICAL_STATUS_UNPROVEN；委托 6004811；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=ba90b6125c797945f9747fc9f0ef3e1a3ee5736da36acc0de7a5f24712e2dfeb）
  - 缺失结算：2026-10-19, 2026-10-20, 2026-10-21, 2026-10-23
  - 缺失日复盘：2026-10-22
  - 缺失 EOD：2026-10-22
- 执行事故复核：原weekly失败已留证并只读接续。旧原单UNKNOWN与后来独立清仓分别成立；10月23日经济任务已自然收口，正式账务仍待现金和实际费用。10月22容量失败及坏格取证缺口分别留证。
- 当前修复负责人：xiaocao-weekly-deep-review / 01a168c1-d63c-7b40-8c8d-12afb5612db3；验收边界：下一原合法checkpoint验证诊断留证，下一原weekly验证sidecar分型与失败传播；专用sellable-only自然非零lot/新委托仍待样本。
- 完整订单、任务轨迹、5 Why 与修复证据：[执行复核](/Users/xuanyue202/Documents/project/xiaocao/docs/reviews/2026-10-23-weekly-execution-review.md)。
- 整体框架复盘（有证据引用的分析，非收益认证）：维持现行 APP Book B 的 E 资格、普通 COLD 默认门及有界 KOL 来源/独立复核/到期/执行门，下一周只做隔离、同资金、点时、费后前向证伪；本轮不晋级策略或资本权限。恢复审阅不是原周度计划成功：原命令只运行一次且构建计划失败，原飞轮、扫盘和 KOL 中间值未保存，补采库存按 10 月 23 日真实捕获时点解释。1/4/12 周重叠窗口有来源、判断、风险与部分消费观察，却无 no-KOL/现行/挑战者完整同点时资金曲线、真实费用、未成交机会及左尾归因，不能从表面净值、闭仓均值、同入场 A/B 退出或模型零收益推出 KOL 盈利。10 月 23 日小草来源的防守与低吸负分约束有明确当日适用性，13:42 才发布的零新增风险判断不能回填 09:27 已收单、09:30 才证明成交的 APP 买入；其他作者的悲观叙事与反弹可能属于相关或相反的背景，均不能当独立投票。保留空仓机会成本和原入口过筛风险为第一研究问题，同时坚持现有 COLD 门直到可成交、同风险、样本外证据足以挑战。
- 结论证据：`output/live/kol_policy/context/4a215c76ccdb2940553dcfa66438133dde90da6f1e8120338858a0cfb8c11134.context.json`（sha256=b82ccdb8369ee45e36460e482f07c7883033db62931ca9a8ba805ea5ba33c133）；`output/live/kol_policy/context/09ae049b1e7d36340f5e5d43b17249b113a78ce81f81e60731d1f7b9c8e66bf7.context.json`（sha256=96c0f616cc750937e2c44e93d823262f607f30d3ce13dbbc89c00f7607ff8b7d）；`output/live/kol_policy/context/5b89ed0a6b1488e802e64f22e742bddef8a8135adf505597f079a4b4cb27ee65.context.json`（sha256=8192511691ed80b9e8746eb976fbc31a373352c5824346e58a203593db0e3051）；`output/live/kol_policy/context/2cbb192fdcd04f6464b1499065e39699fe338e207adbbd12a2f2d3e791f79401.context.json`（sha256=92ca138f082befff145928173af367c1904802b449c03fdcafa1ed0500098912）；`output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1025-neutral-521305ed-v1.json`（sha256=e23a1f68c69129ac4e9c2e2aba39be5ba496208863776fcde341c3f205ccefb7）；`output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json`（sha256=c5fb076b6d662c7d78cb013b2bc7a7b457e18bce6f47e83478d3c8875a3941da）；`output/live/kol_policy/source_verifications/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json`（sha256=0856baf33eaf860ecc16161d04b4a86e3c037bb0a687ffd3401f7dc88fab8230）；`output/live/book_b_live_execution/book_b_live_decisions.jsonl`（sha256=fddaae1265e5ae212311517d4f04357f69bed61c01064d09f4fa86f95143fd30）；`output/live/paper_decision_support/consumption/e0016c5f95ba4b30a2f7bb1c9884bf0736220dc274649f61a272ea193a08ce1c.result.json`（sha256=21ddc939b2e0dac1ef4f698384b87c1ea1e68869079fd42e7ea24b3c7ba5cbcc）；`output/live/book_b_live_execution/runs/2026-10-23.json`（sha256=b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd）；`output/live/kol_policy/account_risk/live_B.jsonl`（sha256=0cacc3824f5503a8034590839ef411a0d9f60941144ed62b10e4fbefbde9d4b8）；`output/live/flywheel_change_ledger.jsonl`（sha256=2b40451d719bb10f5cbd23e21bfbd7cadd92a91a930f3aed9c0fca01c9c50808）
- 待核证据：原周度计划未写出；原 flywheel、sweep 和 KOL 库存中间值未持久化，恢复库存只证明恢复时点。；来源仅有已登记五位作者的本地 registry-only 覆盖；最新上下文 269 份登记报告正文未载入，远端完整发现和未登记/新版来源覆盖未证明。；逐条作者事件去重、冲突关系及完整评分表/入口外点时候选不足；10 月 23 日登记关系没有新的关系边来充当独立印证。；三方案同日 freeze、同本金、风险、整手、T+1、合法时点、费用、真实可成交性、B 出口与现金时间积分的成套 1/4/12 周 OOS 结果缺失。；APP 逐笔实际费用 33 项及 11253.45 元未分类现金未闭合，正式累计盈亏、完整结算与历史原单终态仍未知；不能将保守风险净值、预估费用或账户净流入当盈利。；KOL 模型请求开始/完成、第一合法消费、原计划到成交与费用的逐事件时钟链不全；纸盘旧消费时钟缺失，所见消费不能证明因果盈利。；前向资金实验仅证明 10 月 23 日首个自然日；四组各一计划均 no_fill，后续日历、持仓退出、费用与回撤分布尚无观察。；10 月 23 日选择记录只有三条原冻结候选，其中两条 COLD；完整入口外候选、拒绝理由、点时价格/量及可执行错失收益仍缺。
- 比较框架：无 KOL 基线 / 现行有界 KOL / 挑战者；分别检查入口过滤、模式和资金利用率。
- 纸实逐账户分开；1/4/12 周重叠窗口不是独立样本。小样本不宣称因果胜率或稳定收益，不自动推广实盘。
- 旧试验跟进：3 项需先复核（历史状态仅为报告声明），再决定本周最多三个槽位；不自动启动。

## 数据证据与方案比较

- 输入清单 sha256=`38590bf5f52c473dd1d62956104ee3754be55e4ffe0158e321ce0d82cb45cbfa`；捕获 125 个文件；缺失模式 2 项。
- 结论只约束已保存样本，不自动升级策略；配对 A/B 出场差不解释为 KOL 选股 alpha。

| 比较 / 方案 | 结论 | 样本 | 净收益均值 | 成本均值 | OOS | 判断/执行秒 |
|---|---|---:|---:|---:|---|---|
| 未提供 / baseline_no_kol | 证据不足 | N/A | N/A | N/A | N/A | N/A/N/A |
| 未提供 / current_bounded | 证据不足 | N/A | N/A | N/A | N/A | N/A/N/A |
| 未提供 / kol_challenger | 证据不足 | N/A | N/A | N/A | N/A | N/A/N/A |

### 已记录假设与研究运行

- `A_kp_star`：历史记录 REJECTED（2026-10-16T15:15:00）；本次复核 证据不足；n_days=84，train/test=1.353824/-0.086429。
- `B_vb_star`：历史记录 REJECTED（2026-10-16T15:15:00）；本次复核 证据不足；n_days=84，train/test=1.102407/0.099805。
- `XH-016`：历史记录 REJECTED（2026-06-21T22:52:29）；本次复核 证据不足；n_days=12，train/test=-1.164235/0.899037。
- `XH-001`：历史记录 REJECTED（2026-06-21T22:52:29）；本次复核 证据不足；n_days=11，train/test=-1.420846/0.634824。
- `XH-011`：历史记录 REJECTED（2026-06-21T23:16:47）；本次复核 证据不足；n_days=104，train/test=-1.520804/-0.824224。
- `XH-017`：历史记录 REJECTED（2026-06-22T09:43:51）；本次复核 证据不足；n_days=258，train/test=-0.263952/-0.361687。
- `XH-013`：历史记录 REJECTED（2026-06-22T09:51:40）；本次复核 证据不足；n_days=195，train/test=0.137035/-1.913247。
- `XH-013b`：历史记录 REJECTED（2026-06-22T10:47:08）；本次复核 证据不足；n_days=31，train/test=-0.121354/-0.193822。
- `XH-037`：历史记录 PASS（2026-06-30T21:31:08）；本次复核 证据不足；n_days=114，train/test=3.682124/4.266669。
- `C_mode_rotation_k_survivors`：历史记录 REJECTED（2026-08-14T15:26:12）；本次复核 证据不足；n_days=29，train/test=3.472752/0.657456。
- `D_qibao_benchmark_paper_promoted`：历史记录 REJECTED（2026-07-17T15:29:18）；本次复核 证据不足；n_days=11，train/test=0.245325/-3.010903。
- `T_trend_L60_R20_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_trend_L60_R30_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_trend_L60_R40_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_trend_L60_R60_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_trend_L20_R20_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_rotation_L60_R30_M3_W20_K5`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `aux_gray_n_fixed`：历史记录 REJECTED（2026-07-10T20:17:02）；本次复核 证据不足；n_days=9，train/test=-0.226526/-2.259637。
- `aux_gray_relay1_fixed`：历史记录 REJECTED（2026-07-10T20:17:09）；本次复核 证据不足；n_days=25，train/test=0.723968/-1.135733。
- `E_ai_intelligence_short_factor`：历史记录 REJECTED（2026-08-14T15:26:12）；本次复核 证据不足；n_days=13，train/test=2.403057/-0.660393。
- 研究 `output/research/runs/aux-gray-n-fixed-2026-07-10/manifest.json`：记录 REJECTED，本次 证据不足；缺口：paired_cost_fill_chronology_comparison_missing。
- 研究 `output/research/runs/aux-gray-relay1-fixed-2026-07-10/manifest.json`：记录 REJECTED，本次 证据不足；缺口：paired_cost_fill_chronology_comparison_missing。
- 研究 `output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/manifest.json`：记录 REJECTED，本次 证据不足；缺口：paired_cost_fill_chronology_comparison_missing。

### 纸面成交证据与资金口径

- 1w：独立入场 7，记录窗口标签 7（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- 4w：独立入场 28，记录窗口标签 28（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- 12w：独立入场 72，记录窗口标签 72（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- APP 已保存会计观测 23 份；资金划拨不计利润，缺完整净值/现金流/实际费用时不计算账户收益。
- 会计观测 2026-10-21T01:31:08.677000+00:00：净投入 65845.40，标记净值 68226.84，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-15T07:20:03.515000+00:00：净投入 54462.04，标记净值 56357.60，累计盈亏 N/A，已实现/浮动 1895.56/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-20T01:31:47.456000+00:00：净投入 65845.40，标记净值 67639.84，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-09-29T07:46:17.739000+00:00：净投入 54462.04，标记净值 53704.28，累计盈亏 -757.76，已实现/浮动 -1329.59/571.83；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-10-22T01:30:40.511000+00:00：净投入 65845.40，标记净值 65643.23，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-23T01:31:45.282000+00:00：净投入 65845.40，标记净值 65085.93，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-09-29T07:46:17.739000+00:00：净投入 54462.04，标记净值 53704.28，累计盈亏 -757.76，已实现/浮动 -1329.59/571.83；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-10-15T01:36:25.013000+00:00：净投入 54462.04，标记净值 56357.60，累计盈亏 N/A，已实现/浮动 1895.56/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-09-29T07:46:17.739000+00:00：净投入 54462.04，标记净值 53704.28，累计盈亏 -757.76，已实现/浮动 -1329.59/571.83；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-10-19T01:37:16.622000+00:00：净投入 65845.40，标记净值 68770.17，累计盈亏 N/A，已实现/浮动 1895.56/1029.21；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-23T07:15:26.462000+00:00：净投入 65845.40，标记净值 65085.93，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-20T07:16:23.521000+00:00：净投入 65845.40，标记净值 68623.84，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-09T06:45:04.837000+00:00：净投入 54462.04，标记净值 58415.26，累计盈亏 N/A，已实现/浮动 -1156.95/5131.10；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-09-30T07:22:21.651000+00:00：净投入 54462.04，标记净值 53372.04，累计盈亏 N/A，已实现/浮动 -846.21/-236.39；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-13T07:16:32.855000+00:00：净投入 54462.04，标记净值 59745.10，累计盈亏 N/A，已实现/浮动 5283.06/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-08T07:21:52.104000+00:00：净投入 54462.04，标记净值 53291.26，累计盈亏 N/A，已实现/浮动 -1156.95/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-16T08:03:28.059000+00:00：净投入 65845.40，标记净值 68616.17，累计盈亏 2770.77，已实现/浮动 1895.56/875.21；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-10-16T01:31:46.380000+00:00：净投入 54462.04，标记净值 55768.81，累计盈亏 N/A，已实现/浮动 1895.56/-588.79；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-09-30T06:51:01.818000+00:00：净投入 54462.04，标记净值 53398.04，累计盈亏 N/A，已实现/浮动 -846.21/-210.39；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-16T07:15:54.737000+00:00：净投入 54462.04，标记净值 57232.81，累计盈亏 N/A，已实现/浮动 1895.56/875.21；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-19T07:16:16.247000+00:00：净投入 65845.40，标记净值 68217.82，累计盈亏 N/A，已实现/浮动 2393.94/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-09T01:45:43.626000+00:00：净投入 54462.04，标记净值 53345.26，累计盈亏 N/A，已实现/浮动 -1156.95/61.10；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-21T07:16:31.258000+00:00：净投入 65845.40，标记净值 67392.23，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。

生产纸盘观察截至 2026-10-23；最新原记录日期 2026-10-23，相距 0 个自然日。
有效仓 223、未知仓 17、坏记录 0、未成熟仓 5；旧日期/naive 时钟缺时区与可用时点证明。
Book A：有效/闭仓 98/97；有效子集模型买费 219.89，卖费 216.08，闭仓现金净变动 30244.74。
Book B：有效/闭仓 113/112；有效子集模型买费 258.18，卖费 255.49，闭仓现金净变动 40710.58。
Book T：有效/闭仓 12/9；有效子集模型买费 10.69，卖费 7.68，闭仓现金净变动 -1197.43。
同进场 A/B 闭仓配对 58，B−A均值 0.6707 pp；有效分组排除 56（开放 1、未匹配 17、进场不一致 38）；另有未知仓 17。
1w 进场窗口 2026-10-17–2026-10-23：有效 7；最新数据在窗口前=False。
4w 进场窗口 2026-09-26–2026-10-23：有效 28；最新数据在窗口前=False。
12w 进场窗口 2026-08-01–2026-10-23：有效 72；最新数据在窗口前=False。
以上仅为原始现金事实的描述性观察，非组合NAV、APP成交或KOL增益；闭仓选择偏差与未成熟删失仍在。

### 短线统一流程的前向证据

- 已保存原冻结选择记录 1 日；选择记录不代表独立资金组合已运行。
- 截至 2026-10-21：严格同进场退出 57 对，B−A 均值 +0.6287pp；仅描述该样本，不自动晋级。证据 `output/research/shortline_comparisons/2026-10-21-fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2.json`。
- 截至 2026-10-23：严格同进场退出 58 对，B−A 均值 +0.6707pp；仅描述该样本，不自动晋级。证据 `output/research/shortline_comparisons/2026-10-23-c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41.json`。

### APP B 独立资金对照（模型成交）

| 账户 | 费用后模型收益 | 未决模型订单 | 估值时间 |
|---|---:|---:|---|
| app_b_control | +0.000% | 0 | 2026-10-23T15:16:22.923840+08:00 |
| mode_m | +0.000% | 0 | 2026-10-23T15:16:22.923840+08:00 |
| no_kol | +0.000% | 0 | 2026-10-23T15:16:22.923840+08:00 |
| open_limit | +0.000% | 0 | 2026-10-23T15:16:22.923840+08:00 |
- 2026-10-23 APP 与资金对照：资金分配。
模型成交和盘后时序单独标注；缺证与完整日期分母保留，晋级仍需研究门和人工决策。

## 需要你看/确认的事项

- **继续取证** `continue-registered-funded-evidence`：沿已有三个槽维护费后资金、时效和机会成本证据
- **本地工作区提醒，不是策略判断**：有 37 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl, reference/experience/transcripts/2026-10/2026-10-05_lv_xiaotong_review_514e6857.txt, reference/experience/transcripts/2026-10/2026-10-07_liushao_jujiying_article.md, reference/experience/transcripts/2026-10/2026-10-08_lv_xiaotong_review.txt, reference/experience/transcripts/2026-10/2026-10-12_a-alex_article_732d77c57bdb.md；另有 32 个。

## 这批转录给我的启发
- **2026-10-22 xiaocao_live_method_and_regime_observation（2026-10-22_xiaocao_morning_b8e96488.json）**
  启发：可复用部分是弱市中的仓位与模式治理：环境由纯空仓向局部轮动演变时仍只使用轮动级轻仓，以多模式组合分散单一模式风险；当日开盘型机会只在最初几分钟评估，09:35后不再低吸或追单；高分若主要来自ST、新股或高开标的，不把分数直接当买点。来源中的个股涨跌与模式盈亏只是当日口述盘中例子，不是系统实绩，也不能跨日重放。
  姿态：not_applied：现有姿态窗口停在2026-07-03，本来源是10月22日迟到的盘前至盘中混合材料，不更新10月23日姿态。
  打法：no_change：仅保留弱市轻仓、组合分散、当日开盘低吸时钟和分模式退出的authority=0研究候选。
  待验证：deduplicated：仅XH-276属于精确复现；XH-235只记partial_support_not_ingested，不放入hypotheses；分模式第二至第五日退出保留为唯一新候选，不自动调参。
  命中审计：已核对完整36段、10月22日系统收盘、冻结推荐九行与同日纸账；来源案例没有本地同名推荐或买入证明。
  工具缺口：no_issue_created：后续研究若获授权，再按模式、分钟与环境分层采样；本次不改系统。
- **2026-10-22 大师班复盘（2026-10-22_xiaocao_review_a55dd716.json）**
  启发：源日普跌、成交量不足且科技回撤加深时，小草要求等待放量风险释放；求稳者空仓，仍参与者把固定总仓拆为两至三份，反抽先退出，不追高开，不用杠杆。两至四周机会以出清完成为前提；35%至40%统一强平线与公开规则冲突。
  姿态：no_update：reference/experience/posture_current.json已于2026-07-03过期；单篇转写不足以替换全局姿态。
  打法：proposal_only：组合、退出、追高和去杠杆框架仍需研究与人审。
  待验证：reuse_exact_XH-276_XH-285_XH-289；XH-286与XH-042仅部分支持，不强并。
  命中审计：116个稳定段双遍覆盖；源日九行冻结逐行只读核对，eligible_count=0。
  工具缺口：补齐全市场广度、总成交额、融资余额与账户分布、源日分时、模式候选池和可成交回放。
- **2026-10-23 review（2026-10-23_a-alex_review.json）**
  启发：文章提供了一套可复用的资本密集型科技周期检查框架：把订单、交付、收入确认和回款分开，把资本开支与经营现金流、租赁和采购承诺、信用利差一起看；评估数据中心时以实际接入容量、送电日期和客户起租时间替代规划吉瓦数；评估存储和设备周期时区分价格贡献与产量贡献。所有结论均为来源启发式或待检验假设，authority=0。
  姿态：not_applied_other_author_authority_zero
  打法：candidate_only_no_change_without_research_and_human_gate
  待验证：two_recurrences_XH-228_XH-150_and_two_new_authority_zero_candidates_XH-295_XH-296
  命中审计：bound_to_complete_wechat_article_sha256_4f52bd188306b03dc608ff5d8d7d6db203680cf902bb80ec6181017af1ce1d56
  工具缺口：research_needs_company_level_cashflow_credit_grid_connection_lease_start_price_volume_and_equipment_order_panels
- **2026-10-23 大师班直播（竞价前至约10点）（2026-10-23_xiaocao_morning_3e5dde36.json）**
  启发：极端低开后的反抽若没有量能和承接，只能视为弱修复而不是风险解除；弱市里应把仓位控制放在模式选择之前，仍参与也只能轻仓组合，个股冲高或反抽优先退出。科技拥挤与融资盘风险是作者推演，现有事实只支持科技偏弱，不能确认强平已经发生。
  姿态：proposal_only：本场支持10月23日短线防守与无量反抽不追，但语义草稿不直接改写全局姿态。
  打法：proposal_only：保留弱市反抽退出、评分负分放弃和轻仓组合原则，需研究与人工门槛。
  待验证：reuse_exact_XH-176；XH-276、XH-042与XH-289仅部分支持，不强并。
  命中审计：25个稳定段双遍覆盖；来源、行情与registry文件均绑定SHA-256和大小。
  工具缺口：补齐全市场竞价广度、分时总成交额、融资余额与账户分布、作者模式评分和候选身份。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-10-22 2026-10-22_xiaocao_morning_b8e96488.json: not_applied：现有姿态窗口停在2026-07-03，本来源是10月22日迟到的盘前至盘中混合材料，不更新10月23日姿态。
  - 2026-10-22 2026-10-22_xiaocao_review_a55dd716.json: no_update：reference/experience/posture_current.json已于2026-07-03过期；单篇转写不足以替换全局姿态。
  - 2026-10-23 2026-10-23_a-alex_review.json: not_applied_other_author_authority_zero
  - 2026-10-23 2026-10-23_xiaocao_morning_3e5dde36.json: proposal_only：本场支持10月23日短线防守与无量反抽不追，但语义草稿不直接改写全局姿态。
- **Playbook/纪律**
  - 2026-10-22 2026-10-22_xiaocao_morning_b8e96488.json: no_change：仅保留弱市轻仓、组合分散、当日开盘低吸时钟和分模式退出的authority=0研究候选。
  - 2026-10-22 2026-10-22_xiaocao_review_a55dd716.json: proposal_only：组合、退出、追高和去杠杆框架仍需研究与人审。
  - 2026-10-23 2026-10-23_a-alex_review.json: candidate_only_no_change_without_research_and_human_gate
  - 2026-10-23 2026-10-23_xiaocao_morning_3e5dde36.json: proposal_only：保留弱市反抽退出、评分负分放弃和轻仓组合原则，需研究与人工门槛。
- **候选假设**
  - 2026-10-22 2026-10-22_xiaocao_morning_b8e96488.json: deduplicated：仅XH-276属于精确复现；XH-235只记partial_support_not_ingested，不放入hypotheses；分模式第二至第五日退出保留为唯一新候选，不自动调参。
  - 2026-10-22 2026-10-22_xiaocao_review_a55dd716.json: reuse_exact_XH-276_XH-285_XH-289；XH-286与XH-042仅部分支持，不强并。
  - 2026-10-23 2026-10-23_a-alex_review.json: two_recurrences_XH-228_XH-150_and_two_new_authority_zero_candidates_XH-295_XH-296
  - 2026-10-23 2026-10-23_xiaocao_morning_3e5dde36.json: reuse_exact_XH-176；XH-276、XH-042与XH-289仅部分支持，不强并。
- **命中审计**
  - 2026-10-22 2026-10-22_xiaocao_morning_b8e96488.json: 已核对完整36段、10月22日系统收盘、冻结推荐九行与同日纸账；来源案例没有本地同名推荐或买入证明。
  - 2026-10-22 2026-10-22_xiaocao_review_a55dd716.json: 116个稳定段双遍覆盖；源日九行冻结逐行只读核对，eligible_count=0。
  - 2026-10-23 2026-10-23_a-alex_review.json: bound_to_complete_wechat_article_sha256_4f52bd188306b03dc608ff5d8d7d6db203680cf902bb80ec6181017af1ce1d56
  - 2026-10-23 2026-10-23_xiaocao_morning_3e5dde36.json: 25个稳定段双遍覆盖；来源、行情与registry文件均绑定SHA-256和大小。
- **工具/流程提案**
  - 2026-10-22 2026-10-22_xiaocao_morning_b8e96488.json: no_issue_created：后续研究若获授权，再按模式、分钟与环境分层采样；本次不改系统。
  - 2026-10-22 2026-10-22_xiaocao_review_a55dd716.json: 补齐全市场广度、总成交额、融资余额与账户分布、源日分时、模式候选池和可成交回放。
  - 2026-10-23 2026-10-23_a-alex_review.json: research_needs_company_level_cashflow_credit_grid_connection_lease_start_price_volume_and_equipment_order_panels
  - 2026-10-23 2026-10-23_xiaocao_morning_3e5dde36.json: 补齐全市场竞价广度、分时总成交额、融资余额与账户分布、作者模式评分和候选身份。

## 上期试验与失败跟进（先于新增试验，未记录不等于完成）

- `weekly-2026-09-11-baseline_no_kol`：分开live:B与paper:B，在同日不可变freeze、同本金风险、整手、合法时点与退出下配对no-KOL和现行overlay；预注册OOS，测费后收益、左尾/回撤、暴露、现金时间积分及可成交错失上涨。
  - 历史状态：needs_evidence_and_design；本周复核状态：reviewed；原复核日：2026-10-23。
  - 跟进结论（报告声明）：前次仅登记设计，未发现该历史实验已运行的证据。已预登记资金挑战于10月23日首个自然日出现一单计划/未成交，与控制同为10万元现金；没有可比较利润或回撤分布。保留原编号，下周跟踪同资金多日费用/成交。
  - 回滚：本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-10-16；state sha256=a83cd242af93faa18ea50c58e919731c4f1367794573f3e3404ce271ef58ffa6。
- `weekly-2026-09-11-current_bounded`：检验有界pause/中性包是否在第一合法动作前被消费并改变原计划；分解来源、模型、审核、发布、过期和native/订单迟延，配对量化避免损失与错失上涨。
  - 历史状态：needs_evidence_and_design；本周复核状态：reviewed；原复核日：2026-10-23。
  - 跟进结论（报告声明）：前次 42 份纸盘原消费文件的只读兼容修复不等于实验运行，旧时钟仍缺。10月23日两份正式判断在 APP 买入后发布，第二份零新增风险没有已证合法新增买入分母；四资金账户首日均 no_fill。保持时效/真实消费/定价漏损拆解，不改生产 TTL 或执行门。
  - 回滚：本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-10-16；state sha256=a83cd242af93faa18ea50c58e919731c4f1367794573f3e3404ce271ef58ffa6。
- `weekly-2026-09-11-kol_challenger`：authority=0隔离研究预注册竞价、9:31和有限盘中截面，检验★E/模式入口遗漏合法可成交候选，并与no-KOL/current同本金、风险、费用和退出OOS配对。
  - 历史状态：needs_evidence_and_design；本周复核状态：reviewed；原复核日：2026-10-23。
  - 跟进结论（报告声明）：前次入口外研究仍只有设计，旧 C 模式研究为 REJECTED。10月23日冻结三候选中两条 COLD，模式参与挑战与控制同为一单计划/未成交，无法计算可追回上涨；弱市评分缺原表且 09:37 观察已过期。下周优先补完整点时队列和反证。
  - 回滚：本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-10-16；state sha256=a83cd242af93faa18ea50c58e919731c4f1367794573f3e3404ce271ef58ffa6。

## 整体框架试验槽位（待取证与设计，不是合格变更候选）

- 目标：沿原稳定编号继续检验 APP E+COLD 控制与 no-KOL 的同资金费后差异；把 paper:B 另列，只在完整点时 freeze、整手、真实合法时钟与共同 B 出口上计算收益、现金时间积分、回撤及可成交错失上涨。
  - 证伪条件：若多独立交易日的同风险、费后、可成交 OOS 显示有界 KOL 的收益或左尾改善，控制市场/模式及单一赢家后仍成立，则推翻无 KOL 足以解释表现；无成交样本不判定。
  - 必要证据：完整交易日和原计划/正式政策/消费时点绑定；APP 与模型账户独立；控制与 no-KOL 的 10 万元共同资金路径、费用、保留现金、未决、未成交与 B 出口；多日 OOS、作者事件聚类、市场阶段、现金时间积分、回撤与错失上涨的可成交反事实
  - 回滚：本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。
  - 本次跟进（报告声明）：前次仅登记设计，未发现该历史实验已运行的证据。已预登记资金挑战于10月23日首个自然日出现一单计划/未成交，与控制同为10万元现金；没有可比较利润或回撤分布。保留原编号，下周跟踪同资金多日费用/成交。
  - 负责人：xiaocao weekly research maintainer；隔离执行仍需既有研究门指定；下次复核：2026-10-30。
- 目标：沿原编号分解有界判断的来源、评价、独立复核、发布、失效、第一合法消费与 APP/纸盘原计划/成交；对 no-KOL 资金控制检验左尾与错失，借 open-limit 隔离同计划定价/未成交漏损。
  - 证伪条件：若多数保护判断晚于唯一合法机会、到期或没有可买/可卖暴露，或费后错失上涨及执行漏损抵消左尾收益，则拒绝当前叠加增益；中性包数量不能当收益。
  - 必要证据：按真实时点贯通作者发布/本地可见、评价、请求、审核、出版、有效期、首个合法消费与原 plan/hash；每一缩量/跳过/退出的冻结候选、账户、报价、成交、整手、T+1 与实际费用；缺时钟保持 unknown；同资金 no-KOL 与 current 的多日 OOS 资金曲线、尾部、闲置现金与错失上涨；open-limit 定价差异单列；纸盘 claim/terminal 原哈希及旧 schema 消费时钟只读补证，禁止回填过去交易
  - 回滚：本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。
  - 本次跟进（报告声明）：前次 42 份纸盘原消费文件的只读兼容修复不等于实验运行，旧时钟仍缺。10月23日两份正式判断在 APP 买入后发布，第二份零新增风险没有已证合法新增买入分母；四资金账户首日均 no_fill。保持时效/真实消费/定价漏损拆解，不改生产 TTL 或执行门。
  - 负责人：xiaocao weekly research maintainer；lineage补证由原生产/消费owner协作；下次复核：2026-10-30。
- 目标：沿原编号先检验 mode_star 与原 E/COLD 门在冻结内的同资金可成交参与机会；并设计隔离的竞价、09:31、有限盘中完整入口外队列，测过筛及弱市误读，生产默认维持 E+COLD。
  - 证伪条件：若冻结内 mode_m 和以后入口外挑战在多日 OOS、同本金/整手/费用/流动性/T+1/B 出口后不能同时改善机会覆盖与风险调整收益，或优势由回填、单一赢家、相关来源和标签缺失驱动，则拒绝。
  - 必要证据：冻结前后完整候选和每条拒绝理由、模式/评分版本、实际可见与观察时钟；分开 COLD、UNKNOWN 和不可交易行；已预登记 app-b-mode-m 与控制的 10 万元多日点时资金/费用/未成交/现金时间积分/回撤；原 B 出口；入口外设计需单独预注册且隔离 authority=0，完整可成交队列与多日 OOS；旧 REJECTED 不得冒称新 PASS；观点/评价/关系按作者事件去重；未载入正文与矛盾来源降级，已结束开盘口述不回填 freeze
  - 回滚：本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。
  - 本次跟进（报告声明）：前次入口外研究仍只有设计，旧 C 模式研究为 REJECTED。10月23日冻结三候选中两条 COLD，模式参与挑战与控制同为一单计划/未成交，无法计算可追回上涨；弱市评分缺原表且 09:37 观察已过期。下周优先补完整点时队列和反证。
  - 负责人：xiaocao weekly research maintainer；入口完整性研究仅走独立研究门；下次复核：2026-10-30。

## 已自动落地的代码/配置变更
- none
- 独立运行事故修复（不属策略 AUTO_APPLIED）：只读取证：wait sidecar分型及孤立缺终态、weekly错误退出、失败native cells独立归档/hash引用；技能及六个既有Automation读取指引同步；回滚：定向revert本周提交并通过Automation API移除本次追加指引，保留所有原始订单、账本、失败及研究证据。

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- KOL 固定复盘输入（仅观察，不增加自动落地权限）：output/live/kol_policy/decisions/*.json, output/live/kol_policy/context/*.context.json, output/live/kol_policy/requests/*.json, output/live/kol_policy/source_verifications/*.json, output/live/kol_policy/account_risk/risk_receipts/*.json, output/live/kol_policy/account_risk/live_B.jsonl, output/live/paper_decision_support/consumption/*.json, output/live/paper_decision_support/consumption.jsonl, output/live/book_b_live_execution/consumption.jsonl, output/live/book_b_live_execution/runs/*.json, output/live/book_b_live_execution/book_b_live_decisions.jsonl, output/live/flywheel_change_ledger.jsonl
- APP 执行固定复盘输入（仅观察，不增加策略自动落地权限）：output/live/daily_execution_review_*.md, output/live/book_b_live_execution/events.jsonl, output/live/book_b_live_execution/runs/intraday/archive/*.json, output/live/book_b_live_execution/settlements/*.json, output/live/book_b_live_execution/capital_policy.json, output/live/book_b_live_execution/capital_flows.jsonl, output/live/book_b_live_execution/accounting_reports/*.json
- 提案数量：1
- 自动落地候选数量：0

## 验证
- 181 focused isolated tests PASS
- data doctor OK; four strategy protocols PASS
- original snapshot and supplemental source hashes PASS; SQLite integrity and 36 balanced entries PASS
- six existing Automation API update/view/readback PASS; schedules and models preserved
- independent Standards and Spec review PASS; bash syntax and diff PASS

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：None
- 策略飞轮：None；待处理 PASS=None
- 知识飞轮：候选 None / 已测 None / 已退役 None / 最老未测 None

## 提案文件
- .scratch/weekly-deep-review/2026-10-23/continue-registered-funded-evidence.md

## 机器审计明细
```json
{
  "scoreboard": {},
  "pass_evidence": [],
  "pre_existing_dirty_count": 38654,
  "pre_existing_dirty_sample": [
    " M kronos_screen/HYPOTHESES.jsonl",
    " M src/xiaocao/live/app_test_window.py",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/PRD.md",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/automation-config.json",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-existing-failures.log",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source.tar",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.claude/skills",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-book-b-live-morning/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-daily-eod/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-daily-morning-execution/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-daily-morning/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-intraday-monitor-05/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-intraday-monitor-1455/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-intraday-monitor/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-intraday-risk-precheck-1425/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-kol-hourly-remote-writer/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-kol-hourly/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/automations/xiaocao-weekly-deep-review/automation.toml",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/skills/kol-intelligence/SKILL.md",
    "?? .scratch/actual-trade-fee-reconciliation-20261019/baseline-source/.codex/skills/kol-intelligence/agents/openai.yaml"
  ],
  "kol_system_review_status": "reviewed_proposal_only",
  "kol_inventory_sha256": "657d8d43829a16260a93297e667ea6d7e8f0c5bb9856efc4c7af485e81ac2946",
  "kol_audit_feedback": {
    "status": "audited",
    "published_decision_count": 45,
    "consumption": {
      "live": {
        "source_file_count": 41,
        "legacy_file_count": 11,
        "consumption_container_count": 287,
        "production_hash_bound_record_count": 258,
        "paper_slot_count": 0,
        "paper_scaled_slot_count": 0,
        "paper_zero_slot_count": 0,
        "paper_claims_without_terminal": 0,
        "paper_terminal_status_counts": {},
        "evidence_sha256": "e79a2ad904eaa3869014d3714b3d8dba87b6da26ab59782e8f4022210f987bad",
        "status": "read",
        "record_count": 322,
        "hash_bound_record_count": 258,
        "missing_consumption_clock_count": 64,
        "unbound_decision_reference_count": 274,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 7,
          "kol-b-both-sparse-20261023-1025-neutral-521305ed-v1": 2,
          "kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1": 3,
          "kol-b-live-opening-20260916-pause-adds-329fb25c-v1": 1,
          "kol-b-live-sparse-20260916-1025-pause-7878186a-v1": 1,
          "kol-b-live-sparse-20260916-1325-neutral-3510a357-v1": 25,
          "kol-b-live-sparse-20260917-1025-neutral-d4b2fe7f-v1": 6,
          "kol-b-live-sparse-20260917-1325-neutral-b4cc5ae7-v1": 21,
          "kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1": 36,
          "kol-b-live-sparse-20260929-1025-neutral-7f33dfd2-v1": 4,
          "kol-b-live-sparse-20260929-1325-neutral-8156af63-v1": 17,
          "kol-b-live-sparse-20260930-1025-neutral-4f559e49-v1": 167,
          "kol-b-precheck-20260908-1428-astra-neutral-v1": 3,
          "kol-b-sparse-20260907-1355-astra-neutral-v1": 2,
          "kol-b-sparse-20260907-1430-astra-neutral-v1": 6,
          "kol-b-sparse-20260908-0950-astra-neutral-v1": 2,
          "kol-b-sparse-20260908-1050-astra-neutral-v1": 1,
          "kol-b-sparse-20260908-1325-astra-neutral-v1": 1,
          "kol-b-sparse-20260909-1025-astra-neutral-8c835b5a-v1r1": 1,
          "kol-b-sparse-20260909-1325-astra-neutral-38a3f375-v1": 4,
          "kol-b-sparse-20260910-1055-astra-neutral-12b5dc0e-v1": 3,
          "kol-xiaocao-sunday-pilot-20260906-reviewed-v2": 9
        },
        "book_counts": {
          "B": 322
        },
        "skip_record_count": 3,
        "exit_request_record_count": 0,
        "reported_execution_status_counts": {}
      },
      "paper": {
        "source_file_count": 52,
        "legacy_file_count": 0,
        "consumption_container_count": 26,
        "production_hash_bound_record_count": 26,
        "paper_slot_count": 23,
        "paper_scaled_slot_count": 0,
        "paper_zero_slot_count": 0,
        "paper_claims_without_terminal": 0,
        "paper_terminal_status_counts": {
          "no_buy": 10,
          "bought": 16
        },
        "evidence_sha256": "9c687816f0a84cff7561e8c7421107dded8826da0f10bd4c0b05fb0ff35b735d",
        "status": "read",
        "record_count": 26,
        "hash_bound_record_count": 26,
        "missing_consumption_clock_count": 26,
        "unbound_decision_reference_count": 26,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 1,
          "kol-b-paper-sparse-20260916-1325-neutral-3510a357-v1": 1,
          "kol-b-paper-sparse-20260917-1325-neutral-b4cc5ae7-v1": 1,
          "kol-b-paper-sparse-20260918-1325-neutral-3ae43f5a-v1": 4,
          "kol-b-paper-sparse-20260929-1325-neutral-8156af63-v1": 1,
          "kol-b-paper-sparse-20260930-1025-neutral-4f559e49-v1": 12,
          "kol-b-precheck-20260908-1428-astra-neutral-v1": 1,
          "kol-b-sparse-20260907-1430-astra-neutral-v1": 1,
          "kol-b-sparse-20260909-1325-astra-neutral-38a3f375-v1": 1,
          "kol-b-sparse-20260910-1055-astra-neutral-12b5dc0e-v1": 1,
          "kol-b-sparse-20260914-1325-pause-adds-5903d480-v1": 1,
          "kol-xiaocao-sunday-pilot-20260906-reviewed-v2": 1
        },
        "book_counts": {
          "B": 26
        },
        "skip_record_count": 10,
        "exit_request_record_count": 0,
        "reported_execution_status_counts": {}
      }
    },
    "execution_verification": "not_performed",
    "profit_attribution": "not_established"
  },
  "kol_audit_snapshot_binding": {
    "live": "matched",
    "paper": "matched"
  },
  "kol_experiment_slots": [
    {
      "id": "baseline_no_kol",
      "experiment_id": "weekly-2026-09-11-baseline_no_kol",
      "origin_review_date": "2026-09-11",
      "status": "funded_first_day_observed_no_fill",
      "objective": "沿原稳定编号继续检验 APP E+COLD 控制与 no-KOL 的同资金费后差异；把 paper:B 另列，只在完整点时 freeze、整手、真实合法时钟与共同 B 出口上计算收益、现金时间积分、回撤及可成交错失上涨。",
      "falsifier": "若多独立交易日的同风险、费后、可成交 OOS 显示有界 KOL 的收益或左尾改善，控制市场/模式及单一赢家后仍成立，则推翻无 KOL 足以解释表现；无成交样本不判定。",
      "required_evidence": [
        "完整交易日和原计划/正式政策/消费时点绑定；APP 与模型账户独立",
        "控制与 no-KOL 的 10 万元共同资金路径、费用、保留现金、未决、未成交与 B 出口",
        "多日 OOS、作者事件聚类、市场阶段、现金时间积分、回撤与错失上涨的可成交反事实"
      ],
      "owner": "xiaocao weekly research maintainer；隔离执行仍需既有研究门指定",
      "rollback": "本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。",
      "next_review": "2026-10-30",
      "follow_up": {
        "status": "reviewed",
        "disposition": "continue",
        "conclusion": "前次仅登记设计，未发现该历史实验已运行的证据。已预登记资金挑战于10月23日首个自然日出现一单计划/未成交，与控制同为10万元现金；没有可比较利润或回撤分布。保留原编号，下周跟踪同资金多日费用/成交。",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "2b40451d719bb10f5cbd23e21bfbd7cadd92a91a930f3aed9c0fca01c9c50808"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1025-neutral-521305ed-v1.json",
            "sha256": "e23a1f68c69129ac4e9c2e2aba39be5ba496208863776fcde341c3f205ccefb7"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json",
            "sha256": "c5fb076b6d662c7d78cb013b2bc7a7b457e18bce6f47e83478d3c8875a3941da"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "fddaae1265e5ae212311517d4f04357f69bed61c01064d09f4fa86f95143fd30"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-23.json",
            "sha256": "b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd"
          },
          {
            "path": "output/live/kol_policy/context/4a215c76ccdb2940553dcfa66438133dde90da6f1e8120338858a0cfb8c11134.context.json",
            "sha256": "b82ccdb8369ee45e36460e482f07c7883033db62931ca9a8ba805ea5ba33c133"
          }
        ]
      },
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "2b40451d719bb10f5cbd23e21bfbd7cadd92a91a930f3aed9c0fca01c9c50808"
      },
      "follow_up_required": true,
      "authority": "PROPOSAL_ONLY",
      "auto_apply_eligible": false,
      "funded_protocol_mapping": {
        "primary": "app-b-no-kol",
        "control": "app_b_control",
        "relationship": "同一基线问题的已预登记资金挑战；不是新试验家族"
      }
    },
    {
      "id": "current_bounded",
      "experiment_id": "weekly-2026-09-11-current_bounded",
      "origin_review_date": "2026-09-11",
      "status": "funded_first_day_observed_no_fill_lineage_incomplete",
      "objective": "沿原编号分解有界判断的来源、评价、独立复核、发布、失效、第一合法消费与 APP/纸盘原计划/成交；对 no-KOL 资金控制检验左尾与错失，借 open-limit 隔离同计划定价/未成交漏损。",
      "falsifier": "若多数保护判断晚于唯一合法机会、到期或没有可买/可卖暴露，或费后错失上涨及执行漏损抵消左尾收益，则拒绝当前叠加增益；中性包数量不能当收益。",
      "required_evidence": [
        "按真实时点贯通作者发布/本地可见、评价、请求、审核、出版、有效期、首个合法消费与原 plan/hash",
        "每一缩量/跳过/退出的冻结候选、账户、报价、成交、整手、T+1 与实际费用；缺时钟保持 unknown",
        "同资金 no-KOL 与 current 的多日 OOS 资金曲线、尾部、闲置现金与错失上涨；open-limit 定价差异单列",
        "纸盘 claim/terminal 原哈希及旧 schema 消费时钟只读补证，禁止回填过去交易"
      ],
      "owner": "xiaocao weekly research maintainer；lineage补证由原生产/消费owner协作",
      "rollback": "本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。",
      "next_review": "2026-10-30",
      "follow_up": {
        "status": "reviewed",
        "disposition": "refine",
        "conclusion": "前次 42 份纸盘原消费文件的只读兼容修复不等于实验运行，旧时钟仍缺。10月23日两份正式判断在 APP 买入后发布，第二份零新增风险没有已证合法新增买入分母；四资金账户首日均 no_fill。保持时效/真实消费/定价漏损拆解，不改生产 TTL 或执行门。",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "2b40451d719bb10f5cbd23e21bfbd7cadd92a91a930f3aed9c0fca01c9c50808"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1025-neutral-521305ed-v1.json",
            "sha256": "e23a1f68c69129ac4e9c2e2aba39be5ba496208863776fcde341c3f205ccefb7"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json",
            "sha256": "c5fb076b6d662c7d78cb013b2bc7a7b457e18bce6f47e83478d3c8875a3941da"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "fddaae1265e5ae212311517d4f04357f69bed61c01064d09f4fa86f95143fd30"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-23.json",
            "sha256": "b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd"
          },
          {
            "path": "output/live/kol_policy/context/4a215c76ccdb2940553dcfa66438133dde90da6f1e8120338858a0cfb8c11134.context.json",
            "sha256": "b82ccdb8369ee45e36460e482f07c7883033db62931ca9a8ba805ea5ba33c133"
          },
          {
            "path": "output/live/paper_decision_support/consumption/e0016c5f95ba4b30a2f7bb1c9884bf0736220dc274649f61a272ea193a08ce1c.result.json",
            "sha256": "21ddc939b2e0dac1ef4f698384b87c1ea1e68869079fd42e7ea24b3c7ba5cbcc"
          }
        ]
      },
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "2b40451d719bb10f5cbd23e21bfbd7cadd92a91a930f3aed9c0fca01c9c50808"
      },
      "follow_up_required": true,
      "authority": "PROPOSAL_ONLY",
      "auto_apply_eligible": false,
      "funded_protocol_mapping": {
        "primary": "app-b-no-kol",
        "secondary_execution_diagnostic": "app-b-open-limit",
        "control": "app_b_control",
        "relationship": "KOL效果与同计划限价成交损失分层，均沿已有预登记资金账户"
      }
    },
    {
      "id": "kol_challenger",
      "experiment_id": "weekly-2026-09-11-kol_challenger",
      "origin_review_date": "2026-09-11",
      "status": "funded_first_day_observed_no_fill_broader_entry_unrun",
      "objective": "沿原编号先检验 mode_star 与原 E/COLD 门在冻结内的同资金可成交参与机会；并设计隔离的竞价、09:31、有限盘中完整入口外队列，测过筛及弱市误读，生产默认维持 E+COLD。",
      "falsifier": "若冻结内 mode_m 和以后入口外挑战在多日 OOS、同本金/整手/费用/流动性/T+1/B 出口后不能同时改善机会覆盖与风险调整收益，或优势由回填、单一赢家、相关来源和标签缺失驱动，则拒绝。",
      "required_evidence": [
        "冻结前后完整候选和每条拒绝理由、模式/评分版本、实际可见与观察时钟；分开 COLD、UNKNOWN 和不可交易行",
        "已预登记 app-b-mode-m 与控制的 10 万元多日点时资金/费用/未成交/现金时间积分/回撤；原 B 出口",
        "入口外设计需单独预注册且隔离 authority=0，完整可成交队列与多日 OOS；旧 REJECTED 不得冒称新 PASS",
        "观点/评价/关系按作者事件去重；未载入正文与矛盾来源降级，已结束开盘口述不回填 freeze"
      ],
      "owner": "xiaocao weekly research maintainer；入口完整性研究仅走独立研究门",
      "rollback": "本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。",
      "next_review": "2026-10-30",
      "follow_up": {
        "status": "reviewed",
        "disposition": "refine",
        "conclusion": "前次入口外研究仍只有设计，旧 C 模式研究为 REJECTED。10月23日冻结三候选中两条 COLD，模式参与挑战与控制同为一单计划/未成交，无法计算可追回上涨；弱市评分缺原表且 09:37 观察已过期。下周优先补完整点时队列和反证。",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "2b40451d719bb10f5cbd23e21bfbd7cadd92a91a930f3aed9c0fca01c9c50808"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1025-neutral-521305ed-v1.json",
            "sha256": "e23a1f68c69129ac4e9c2e2aba39be5ba496208863776fcde341c3f205ccefb7"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json",
            "sha256": "c5fb076b6d662c7d78cb013b2bc7a7b457e18bce6f47e83478d3c8875a3941da"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "fddaae1265e5ae212311517d4f04357f69bed61c01064d09f4fa86f95143fd30"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-23.json",
            "sha256": "b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd"
          },
          {
            "path": "output/live/kol_policy/context/4a215c76ccdb2940553dcfa66438133dde90da6f1e8120338858a0cfb8c11134.context.json",
            "sha256": "b82ccdb8369ee45e36460e482f07c7883033db62931ca9a8ba805ea5ba33c133"
          },
          {
            "path": "output/live/kol_policy/context/2cbb192fdcd04f6464b1499065e39699fe338e207adbbd12a2f2d3e791f79401.context.json",
            "sha256": "92ca138f082befff145928173af367c1904802b449c03fdcafa1ed0500098912"
          }
        ]
      },
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "2b40451d719bb10f5cbd23e21bfbd7cadd92a91a930f3aed9c0fca01c9c50808"
      },
      "follow_up_required": true,
      "authority": "PROPOSAL_ONLY",
      "auto_apply_eligible": false,
      "funded_protocol_mapping": {
        "primary": "app-b-mode-m",
        "secondary_selection_diagnostic": "output/research/shortline_experiments/2026-10-23",
        "control": "app_b_control",
        "relationship": "只用既有模式参与资金挑战；入口外候选须另走 authority=0 研究设计，不虚构已经运行"
      }
    }
  ],
  "data_evidence_review": {
    "schema_version": 1,
    "as_of": "2026-10-23",
    "authority": "research_observer_only",
    "status": "insufficient_evidence",
    "input_manifest": {
      "files": [
        {
          "first_date": "2026-06-20",
          "last_date": "2026-10-16",
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "record_count": 40,
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4",
          "size_bytes": 27177,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/11331e61bb9b0d825b7e70c84122e935889523a4c4e294a47fb678c5f1b0d04c.json",
          "record_count": 1,
          "sha256": "40fabc542a25482dc8516d32678679e56c7473c8b00336eb3fd615356dc96f8f",
          "size_bytes": 11475,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/40fabc542a25482dc8516d32678679e56c7473c8b00336eb3fd615356dc96f8f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/11d6809532302a8058c19b61f45652ac7c50d7ee7c58941c3f599e75b5fa8944.json",
          "record_count": 1,
          "sha256": "c576c3bb194a4148f83d9bfe84068140e24696dce3a16cc558f7bda46f2c4f7b",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c576c3bb194a4148f83d9bfe84068140e24696dce3a16cc558f7bda46f2c4f7b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/12a8ecd8fd2c7b21dc89e55b97e8bba49d4061e7cc525fae615650ab0d88c709.json",
          "record_count": 1,
          "sha256": "05aad28a8c54f6d511525d6429c19568112edfd3414e05f91b7acf3c03643758",
          "size_bytes": 10654,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/05aad28a8c54f6d511525d6429c19568112edfd3414e05f91b7acf3c03643758",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/189f1f5f0f67564a9e27214fb7b28800dce60f3cd661e5bab906571e96b01ff1.json",
          "record_count": 1,
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "size_bytes": 1972,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/1c356652b0500fa5e8b6f0bc71ba013a70c9eda8d359d8c4f21b3049bc1d6ae9.json",
          "record_count": 1,
          "sha256": "10b9eb24cb29b0cbba07b563d76eb1d998d5bf4b27b3dd346e76a709c27e8d9d",
          "size_bytes": 11665,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/10b9eb24cb29b0cbba07b563d76eb1d998d5bf4b27b3dd346e76a709c27e8d9d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/1d1864f5b755f1ed207f96e0af7fda45fc41acb182855665215b33fc52b587e8.json",
          "record_count": 1,
          "sha256": "22a52777249e095a3a1c3306a04ce8ae80a9d8be78d275cb16e7a7b92e784a5e",
          "size_bytes": 12430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/22a52777249e095a3a1c3306a04ce8ae80a9d8be78d275cb16e7a7b92e784a5e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c.json",
          "record_count": 1,
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "size_bytes": 1972,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/4f05fc9f99271615d18abfae3db79c02c35ae82c73e1104b8c3002b3073816b3.json",
          "record_count": 1,
          "sha256": "fa036a5795e09cbd63d4f1edbda25fe250d4108ed858b354c0a18ef47ec3b700",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/fa036a5795e09cbd63d4f1edbda25fe250d4108ed858b354c0a18ef47ec3b700",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/5fdccb94720cb27ec705c46da02f69429616cfe21964e2d3ef23bec01f2cd006.json",
          "record_count": 1,
          "sha256": "59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b",
          "size_bytes": 2013,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/67a168e1b12f574245bdd1c67168e6d180be3362c906a32f266004f211516c2b.json",
          "record_count": 1,
          "sha256": "0eb20d33bf944f85747c0a98e78226604b1731ef5282a30c441317c980f1bd62",
          "size_bytes": 2192,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/0eb20d33bf944f85747c0a98e78226604b1731ef5282a30c441317c980f1bd62",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/68ee4b126230e14ff8ea8108454d2c48cd0aeb4730e764d2a485cb505c1c451d.json",
          "record_count": 1,
          "sha256": "fb452d42134a56cc5dd975cb1b47818fbe7e648788072935a68a0ace2534d90c",
          "size_bytes": 12430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/fb452d42134a56cc5dd975cb1b47818fbe7e648788072935a68a0ace2534d90c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/6d157cb173b9029ce4d64aa2d4d8e3d6c3be0934dafe45e2066b0c3d7215da6f.json",
          "record_count": 1,
          "sha256": "684934ec6b6cb1172e750536e468c5a9ccd0e3db21da8d38c1211964b33553f9",
          "size_bytes": 10653,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/684934ec6b6cb1172e750536e468c5a9ccd0e3db21da8d38c1211964b33553f9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/6eafa2842aa86eb253533f69921c9250d2c54e686a866d3551893b14ee73442a.json",
          "record_count": 1,
          "sha256": "bab487e32dff3c2339c980fd87df5034a7165f31c21981f8a7043a8d2c616af0",
          "size_bytes": 2241,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/bab487e32dff3c2339c980fd87df5034a7165f31c21981f8a7043a8d2c616af0",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/8e58602dce0e24050d28f4157476691f5c89b4477d1075bf54d86cd588ac738b.json",
          "record_count": 1,
          "sha256": "2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955",
          "size_bytes": 1939,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/9049d8b69c2efd7c1b784f732c2e14fce068708857b77c136831085b1e6d689e.json",
          "record_count": 1,
          "sha256": "68225c161befdb1eb84f63b937982dbee9c61bea0dbef8edff14f28eee2669af",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/68225c161befdb1eb84f63b937982dbee9c61bea0dbef8edff14f28eee2669af",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/93aef1dfd2aab4d323cc7da9c469dca14ebb4b8198998423cf72fc32f7b7101f.json",
          "record_count": 1,
          "sha256": "6e3076b3f1ccd6823684d2624da1e0b192ce5c7c3a013a8e5aef95110a634753",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/6e3076b3f1ccd6823684d2624da1e0b192ce5c7c3a013a8e5aef95110a634753",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/a3a2a2b46447f33b1dffbdbbb3f0c195d3804eb22258b018dd54ae7e41af6c02.json",
          "record_count": 1,
          "sha256": "bef91a70ed21a02cb97a3c4356011d41aa8d7d5b65d8f6c7e1091d2ee45aaf42",
          "size_bytes": 2178,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/bef91a70ed21a02cb97a3c4356011d41aa8d7d5b65d8f6c7e1091d2ee45aaf42",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/c17b2b3981b4fbd47af69ae11c14e817560936a6670a0a156f1e82f6ae409d85.json",
          "record_count": 1,
          "sha256": "8428796ec2d2b4301d8b5a553ab8e33bf21263653e66f55aafffd35a3d605cc7",
          "size_bytes": 2196,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/8428796ec2d2b4301d8b5a553ab8e33bf21263653e66f55aafffd35a3d605cc7",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/c41cf727e4ea97810027c561a03a355118fa2ae5c94a372a4a792e70c8bd5467.json",
          "record_count": 1,
          "sha256": "fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf",
          "size_bytes": 1939,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/c8de32a296b2f3506e04a38dc352771851340c649e4393ab38bace8029792445.json",
          "record_count": 1,
          "sha256": "803b3c25aeda3474fcd2b2585631326529bdac664bf279208ec1322ab8e79390",
          "size_bytes": 2195,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/803b3c25aeda3474fcd2b2585631326529bdac664bf279208ec1322ab8e79390",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/cc642c97ff781a8cced7d00f31530e6c9c263088ff32e509031dfc62a6485be3.json",
          "record_count": 1,
          "sha256": "e2b1733a766cd6cd11b86a2b3289608d14db28f776f5fd69ea8aafec2a4ea6ac",
          "size_bytes": 1938,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/e2b1733a766cd6cd11b86a2b3289608d14db28f776f5fd69ea8aafec2a4ea6ac",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/e7c5a5678234879cbad0ad4448221c0a59056e9e683c7540cc3337de386fb3f4.json",
          "record_count": 1,
          "sha256": "e7dcf98d44bb888889dc729fb9c39bbc423e00a88d2b877c06d0766ed10a3360",
          "size_bytes": 2239,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/e7dcf98d44bb888889dc729fb9c39bbc423e00a88d2b877c06d0766ed10a3360",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/f17924bf2ab7daeafc441e55e73387816999a3b5e07656831078b601fc63850f.json",
          "record_count": 1,
          "sha256": "7d01fda770c85501b36afac07431a7f2aa32c5a375f40982e84138913de184a6",
          "size_bytes": 11664,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/7d01fda770c85501b36afac07431a7f2aa32c5a375f40982e84138913de184a6",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/capital_flows.jsonl",
          "record_count": 2,
          "sha256": "8f04393ae00fb62bc5ce4b202cee094a358572f31beafe778d327861e0f5c65e",
          "size_bytes": 1956,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/8f04393ae00fb62bc5ce4b202cee094a358572f31beafe778d327861e0f5c65e",
          "status": "captured"
        },
        {
          "first_date": "2026-06-08",
          "last_date": "2026-06-08",
          "path": "output/live/exit_calibration.jsonl",
          "record_count": 1,
          "sha256": "dde16689d347d08cc3196e8dd9d7c450cc60f9f99f4d7f7ad381a94041df5752",
          "size_bytes": 280,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/dde16689d347d08cc3196e8dd9d7c450cc60f9f99f4d7f7ad381a94041df5752",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-23",
          "path": "output/live/paper_holdings_snapshots.jsonl",
          "record_count": 883,
          "sha256": "0702b583ec58a58d58ebecb480139922cc6f41cf9f30106894ed1cc7d46ab2c7",
          "size_bytes": 1115871,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/0702b583ec58a58d58ebecb480139922cc6f41cf9f30106894ed1cc7d46ab2c7",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-23",
          "path": "output/live/paper_trades.jsonl",
          "record_count": 475,
          "sha256": "c2ec1eca329b4942aee258b383ff31480bf17b2cc4b8f7a87165d491f82e253a",
          "size_bytes": 258559,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c2ec1eca329b4942aee258b383ff31480bf17b2cc4b8f7a87165d491f82e253a",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/pnl_decompose.csv",
          "record_count": null,
          "sha256": "6cb228d1b83f8754dc08995ead0cdeb5d48d5675616ae105ab184e5cb2077b0b",
          "size_bytes": 22017,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/6cb228d1b83f8754dc08995ead0cdeb5d48d5675616ae105ab184e5cb2077b0b",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-23",
          "path": "output/live/positions.jsonl",
          "record_count": 240,
          "sha256": "f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997",
          "size_bytes": 358936,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-23",
          "path": "output/live/signal_snapshots.jsonl",
          "record_count": 1013,
          "sha256": "9f508639c79c23dcc478c735d608599dcb930e79697c75e9c4ea97c5fb71bc63",
          "size_bytes": 4429322,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/9f508639c79c23dcc478c735d608599dcb930e79697c75e9c4ea97c5fb71bc63",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/app_b_forward/app_lifecycle.json",
          "record_count": 1,
          "sha256": "6b09df923df667df2fcb099bca0327720c418de494332ecdc17c30df42acdb60",
          "size_bytes": 93750,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/6b09df923df667df2fcb099bca0327720c418de494332ecdc17c30df42acdb60",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/app_b_forward/performance.json",
          "record_count": 1,
          "sha256": "63c8c55919168eba748faebf67312b069fcb7f7b526400a0fdad42e3bd0fa82a",
          "size_bytes": 8541,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/63c8c55919168eba748faebf67312b069fcb7f7b526400a0fdad42e3bd0fa82a",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/app_b_forward/protocol.json",
          "record_count": 1,
          "sha256": "79113426b8e5f467573c9b381eaf77dca87b6c3725227475655d58e1918f146f",
          "size_bytes": 645,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/79113426b8e5f467573c9b381eaf77dca87b6c3725227475655d58e1918f146f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-06-30.md",
          "record_count": null,
          "sha256": "d66495a808d06d9371daa6287838dba3f0af165c10a8638a1d59c612cde2581d",
          "size_bytes": 1552,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d66495a808d06d9371daa6287838dba3f0af165c10a8638a1d59c612cde2581d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-01.md",
          "record_count": null,
          "sha256": "76377baf3480cd9615e67e6260571418cf9247dc54b0960d5047bb2dfd9de9e9",
          "size_bytes": 1568,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/76377baf3480cd9615e67e6260571418cf9247dc54b0960d5047bb2dfd9de9e9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-02.md",
          "record_count": null,
          "sha256": "62c8ecff2e5ae8a5105609809a5b8d3601871c12cb0dc6366338b2b8c7eb7baa",
          "size_bytes": 1614,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/62c8ecff2e5ae8a5105609809a5b8d3601871c12cb0dc6366338b2b8c7eb7baa",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-03.md",
          "record_count": null,
          "sha256": "8b7fd10f1634b4d5051ba707e6af2e43945caf33e4df326bdfaa4a5f02ed1f39",
          "size_bytes": 1596,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/8b7fd10f1634b4d5051ba707e6af2e43945caf33e4df326bdfaa4a5f02ed1f39",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-06.md",
          "record_count": null,
          "sha256": "3eb2487514a15f0a342f3fc765af57f8ed76a12cf87215e68765c50a36892535",
          "size_bytes": 1657,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/3eb2487514a15f0a342f3fc765af57f8ed76a12cf87215e68765c50a36892535",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-07.md",
          "record_count": null,
          "sha256": "4703555ba1d1feb2cc352471ec20b9e05a476a7936bfa04574c02e14a89cc0f3",
          "size_bytes": 1659,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/4703555ba1d1feb2cc352471ec20b9e05a476a7936bfa04574c02e14a89cc0f3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-08.md",
          "record_count": null,
          "sha256": "3051c61877741e55750cb64a5e2b7ad3dd9484bae16e8bf3b95732143a3811df",
          "size_bytes": 1659,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/3051c61877741e55750cb64a5e2b7ad3dd9484bae16e8bf3b95732143a3811df",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-09.md",
          "record_count": null,
          "sha256": "421025f3d2671c0474f92c901e40c8fd06e08ce7dbdd575d2366f64fdcd812d8",
          "size_bytes": 1664,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/421025f3d2671c0474f92c901e40c8fd06e08ce7dbdd575d2366f64fdcd812d8",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-10.md",
          "record_count": null,
          "sha256": "e3d03874c764b96a280a787198db36b9e3e6b6121bc300d3ebc646cfe420977c",
          "size_bytes": 1665,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/e3d03874c764b96a280a787198db36b9e3e6b6121bc300d3ebc646cfe420977c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-13.md",
          "record_count": null,
          "sha256": "538ced43d020a0f4f15a001c7b02c53197e266d9e4198d69c7a36a99a740b912",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/538ced43d020a0f4f15a001c7b02c53197e266d9e4198d69c7a36a99a740b912",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-14.md",
          "record_count": null,
          "sha256": "bb90bce70c12c7c856b678a7d348e8873a069a8d01bbf23f78b55e03e1aba3e0",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/bb90bce70c12c7c856b678a7d348e8873a069a8d01bbf23f78b55e03e1aba3e0",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-15.md",
          "record_count": null,
          "sha256": "c550da9aa03924d953236ff4bede78eb6deaf513acee7b1a8f45f7cf0bcff321",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c550da9aa03924d953236ff4bede78eb6deaf513acee7b1a8f45f7cf0bcff321",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-16.md",
          "record_count": null,
          "sha256": "07051d8db157280a82ef0503d5371f40ea13af11f9b184b45c5f84e78edd1b9b",
          "size_bytes": 1679,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/07051d8db157280a82ef0503d5371f40ea13af11f9b184b45c5f84e78edd1b9b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-17.md",
          "record_count": null,
          "sha256": "b8a8a7b5fd7347609c36e1a391fc8436ead0109413d4fcc6f89335e2263209ff",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b8a8a7b5fd7347609c36e1a391fc8436ead0109413d4fcc6f89335e2263209ff",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-20.md",
          "record_count": null,
          "sha256": "4ac67aaf14c874122ef6ff4e39c824a257d6e0d020e147ca13ce435941278c0e",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/4ac67aaf14c874122ef6ff4e39c824a257d6e0d020e147ca13ce435941278c0e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-21.md",
          "record_count": null,
          "sha256": "4da8cefa13f79332520f76ef1c5e6327461fb6d1688bcc4c570f3b3716b7c3fc",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/4da8cefa13f79332520f76ef1c5e6327461fb6d1688bcc4c570f3b3716b7c3fc",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-22.md",
          "record_count": null,
          "sha256": "c62603355e0b8b6c81f052efb1f046653e5d510cfd5a4433df7693d800a44a3d",
          "size_bytes": 1739,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c62603355e0b8b6c81f052efb1f046653e5d510cfd5a4433df7693d800a44a3d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-23.md",
          "record_count": null,
          "sha256": "2866883e99c0cb09ce15a8faa7c9e2033e62f39eac4ea1e0dfe65b45185ea22f",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/2866883e99c0cb09ce15a8faa7c9e2033e62f39eac4ea1e0dfe65b45185ea22f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-24.md",
          "record_count": null,
          "sha256": "7749911678871915752439e978e352fd3b98839b688edee103bcc9bd7f0799df",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/7749911678871915752439e978e352fd3b98839b688edee103bcc9bd7f0799df",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-27.md",
          "record_count": null,
          "sha256": "b45de707bceb56128e29d06aed080e6171e2bb30021d3bb7af753f967a1b9c01",
          "size_bytes": 1736,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b45de707bceb56128e29d06aed080e6171e2bb30021d3bb7af753f967a1b9c01",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-28.md",
          "record_count": null,
          "sha256": "9e5aa5387abc464a2580cd1fbfc4fbb1aefb82b218346017dcfcb58388a97958",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/9e5aa5387abc464a2580cd1fbfc4fbb1aefb82b218346017dcfcb58388a97958",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-03.md",
          "record_count": null,
          "sha256": "9adbe52713711ccb666619155fe2aa13ddc6e41df810009a1044a1ddcb89bc53",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/9adbe52713711ccb666619155fe2aa13ddc6e41df810009a1044a1ddcb89bc53",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-04.md",
          "record_count": null,
          "sha256": "7d2ab40b988a0b312d10f40e1ea0077e40f4c8b0a4f20ca2910ad47f88d27e93",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/7d2ab40b988a0b312d10f40e1ea0077e40f4c8b0a4f20ca2910ad47f88d27e93",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-05.md",
          "record_count": null,
          "sha256": "8521076f2100e1b245fcf8d9357d714189ae0674bf64799255d3fbc4f4868c5b",
          "size_bytes": 1735,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/8521076f2100e1b245fcf8d9357d714189ae0674bf64799255d3fbc4f4868c5b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-06.md",
          "record_count": null,
          "sha256": "b29ce0f1708a8e129abf56a6fb5b609bc0c86e2a92c783df44de0431dc5cc23e",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b29ce0f1708a8e129abf56a6fb5b609bc0c86e2a92c783df44de0431dc5cc23e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-07.md",
          "record_count": null,
          "sha256": "ca9f909330795b6ef3b26ee23401dcb91f765bc7116c1c1c4b8c15dbe164f819",
          "size_bytes": 1736,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/ca9f909330795b6ef3b26ee23401dcb91f765bc7116c1c1c4b8c15dbe164f819",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-10.md",
          "record_count": null,
          "sha256": "d3552e00c3426d4779bc070975fa057b483add73b711f8f148c06265c0da13f4",
          "size_bytes": 1734,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d3552e00c3426d4779bc070975fa057b483add73b711f8f148c06265c0da13f4",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-11.md",
          "record_count": null,
          "sha256": "9d4dde9cbc13f56d74a031f88f4e32c3f04bcde74467bcf2cc0b9113ee028954",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/9d4dde9cbc13f56d74a031f88f4e32c3f04bcde74467bcf2cc0b9113ee028954",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-12.md",
          "record_count": null,
          "sha256": "4e127d3e802b60465f31ca597fd6d36cef2d3a110df76eed26d5bf18a4c2d898",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/4e127d3e802b60465f31ca597fd6d36cef2d3a110df76eed26d5bf18a4c2d898",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-13.md",
          "record_count": null,
          "sha256": "785f1fd8a42083c24e15569f8d649bbc863c2c79ed502063bfa84fb92c8bb314",
          "size_bytes": 1733,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/785f1fd8a42083c24e15569f8d649bbc863c2c79ed502063bfa84fb92c8bb314",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-14.md",
          "record_count": null,
          "sha256": "41bfd6060c4f806377bfef8564f5487791644b659f053ea59bb66d1f164a1c0d",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/41bfd6060c4f806377bfef8564f5487791644b659f053ea59bb66d1f164a1c0d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-17.md",
          "record_count": null,
          "sha256": "a00c328cbf60a8f2f7a67623d4f81b042c5173220eadc9088ee781c5b1dada9e",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/a00c328cbf60a8f2f7a67623d4f81b042c5173220eadc9088ee781c5b1dada9e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-18.md",
          "record_count": null,
          "sha256": "fa09c513b7ad5606602270053cc80955d596db6ef18d5f867375b1ebb74c8c14",
          "size_bytes": 1735,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/fa09c513b7ad5606602270053cc80955d596db6ef18d5f867375b1ebb74c8c14",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-19.md",
          "record_count": null,
          "sha256": "d761791ad07a44e1ee8a56552eadd3891bd46fb43d2a3c05c54bc0537ec22c57",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d761791ad07a44e1ee8a56552eadd3891bd46fb43d2a3c05c54bc0537ec22c57",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-20.md",
          "record_count": null,
          "sha256": "83b3ac332aceb925c6070f86112ec846b588a2bba476077fd3c38eabd80c7d39",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/83b3ac332aceb925c6070f86112ec846b588a2bba476077fd3c38eabd80c7d39",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-21.md",
          "record_count": null,
          "sha256": "d0300b91b7b4cfb54b8ac244b9443fe8f83dbb95145d7f8c37ade984e7239507",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d0300b91b7b4cfb54b8ac244b9443fe8f83dbb95145d7f8c37ade984e7239507",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-24.md",
          "record_count": null,
          "sha256": "3b7682800bdd7ebf3abbee95afcd69fa7b3f7f877c81bc57d31d41bf1b030757",
          "size_bytes": 1742,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/3b7682800bdd7ebf3abbee95afcd69fa7b3f7f877c81bc57d31d41bf1b030757",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-25.md",
          "record_count": null,
          "sha256": "42cf42b3f69e1fbcea63ecc62a3764ac22130040694580f77590a88defecfa23",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/42cf42b3f69e1fbcea63ecc62a3764ac22130040694580f77590a88defecfa23",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-26.md",
          "record_count": null,
          "sha256": "43c56977508352616008101248ec0de5db86bec7b44b1642ffddd18ab79a6d94",
          "size_bytes": 1742,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/43c56977508352616008101248ec0de5db86bec7b44b1642ffddd18ab79a6d94",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-27.md",
          "record_count": null,
          "sha256": "4ac4cc4d1ae290c25b3e72a06f6b9fd080ae8170c277b8555fff137ed7cba91d",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/4ac4cc4d1ae290c25b3e72a06f6b9fd080ae8170c277b8555fff137ed7cba91d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-28.md",
          "record_count": null,
          "sha256": "e75e0b270ec136fc3b5ed584c1f28e8d4a75f357e27b47446c8eb1510dd09b87",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/e75e0b270ec136fc3b5ed584c1f28e8d4a75f357e27b47446c8eb1510dd09b87",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-31.md",
          "record_count": null,
          "sha256": "d885d323aea5ca5bfb0a19684dc9accbc7a9bdf0f40496fe6bd5effb861ffeed",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d885d323aea5ca5bfb0a19684dc9accbc7a9bdf0f40496fe6bd5effb861ffeed",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-01.md",
          "record_count": null,
          "sha256": "be16f20dfb2cc264c4c9f85a6061c4494c844207baa88b38f973585eb8ac3929",
          "size_bytes": 1746,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/be16f20dfb2cc264c4c9f85a6061c4494c844207baa88b38f973585eb8ac3929",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-02.md",
          "record_count": null,
          "sha256": "b264718c16a877e0a3096b2bdc7a691cc98e2ee1e86faa2895953cac3f36d654",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b264718c16a877e0a3096b2bdc7a691cc98e2ee1e86faa2895953cac3f36d654",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-03.md",
          "record_count": null,
          "sha256": "5a7888361cb36d477417bffa84b93667f6f53560b25952315783cd33bc6a0f57",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/5a7888361cb36d477417bffa84b93667f6f53560b25952315783cd33bc6a0f57",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-04.md",
          "record_count": null,
          "sha256": "40d23f8116a46650265df67c651d3a30068a2ad39e68ceedfa15cf41aafd3355",
          "size_bytes": 1747,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/40d23f8116a46650265df67c651d3a30068a2ad39e68ceedfa15cf41aafd3355",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-07.md",
          "record_count": null,
          "sha256": "30e67efe07a50b6a6b54855929ad6af0cae64ed61b55dc9e3fa9516c6cb5eb6b",
          "size_bytes": 1748,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/30e67efe07a50b6a6b54855929ad6af0cae64ed61b55dc9e3fa9516c6cb5eb6b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-08.md",
          "record_count": null,
          "sha256": "f3e7eb1beb00104123dcc5adb7a158a35fc36f62a03915c5abdf68236945c60d",
          "size_bytes": 1747,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/f3e7eb1beb00104123dcc5adb7a158a35fc36f62a03915c5abdf68236945c60d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-09.md",
          "record_count": null,
          "sha256": "d4a354c8d1d8dc3ee309bdda62e1917259f98fbfb87acfa632c40282919c9fba",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d4a354c8d1d8dc3ee309bdda62e1917259f98fbfb87acfa632c40282919c9fba",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-10.md",
          "record_count": null,
          "sha256": "ba52216859c03481296bb4d943ae343d4ecf60950cc796fcfddd1fd96ba8ce2f",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/ba52216859c03481296bb4d943ae343d4ecf60950cc796fcfddd1fd96ba8ce2f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-11.md",
          "record_count": null,
          "sha256": "b62ebb513190a36b5ad236cefb684f89f1fa4daaa2efb341ea5847debeafd74f",
          "size_bytes": 1749,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b62ebb513190a36b5ad236cefb684f89f1fa4daaa2efb341ea5847debeafd74f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-14.md",
          "record_count": null,
          "sha256": "2cebfd0ce5a4c1feee5e74c512cae5b189ef8f5bc400c2df5a7773d87757a14f",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/2cebfd0ce5a4c1feee5e74c512cae5b189ef8f5bc400c2df5a7773d87757a14f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-15.md",
          "record_count": null,
          "sha256": "5c00b8d24449edb06f7c273a057bf3e72358ad12df4e2cfe1a0a8714295cc90e",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/5c00b8d24449edb06f7c273a057bf3e72358ad12df4e2cfe1a0a8714295cc90e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-16.md",
          "record_count": null,
          "sha256": "b6fffa71d0e90842edd6d27766f15763197c84a89fe99b49c997f88ce89a6543",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b6fffa71d0e90842edd6d27766f15763197c84a89fe99b49c997f88ce89a6543",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-17.md",
          "record_count": null,
          "sha256": "f03f5d55a814d36ff930fdfcd8eb166072040fdf787645c943bcb5ab3a13cfbb",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/f03f5d55a814d36ff930fdfcd8eb166072040fdf787645c943bcb5ab3a13cfbb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-18.md",
          "record_count": null,
          "sha256": "100944791fa4121500ef1442f8d2fdfb7369f47eb4e265a2858c5c7bd0b2f823",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/100944791fa4121500ef1442f8d2fdfb7369f47eb4e265a2858c5c7bd0b2f823",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-21.md",
          "record_count": null,
          "sha256": "c6534dd010ec90470584b1963a9ffd8a1f01dd307b2e04087d84645abfa02fc5",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c6534dd010ec90470584b1963a9ffd8a1f01dd307b2e04087d84645abfa02fc5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-22.md",
          "record_count": null,
          "sha256": "d5c7aefdadb805987efbb686277d16fb2f7e819fb0d6ac1a1d40deed0a6aff6e",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d5c7aefdadb805987efbb686277d16fb2f7e819fb0d6ac1a1d40deed0a6aff6e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-23.md",
          "record_count": null,
          "sha256": "ef3b24b1ae89cdab8bff3e376b250cbd18737f0cbe212b30cf947d01a205d502",
          "size_bytes": 1746,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/ef3b24b1ae89cdab8bff3e376b250cbd18737f0cbe212b30cf947d01a205d502",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-28.md",
          "record_count": null,
          "sha256": "657596725f41f76d5e7422e75ccf82682476e58ad5da9b1cd52d4363bb2b3126",
          "size_bytes": 1751,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/657596725f41f76d5e7422e75ccf82682476e58ad5da9b1cd52d4363bb2b3126",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-29.md",
          "record_count": null,
          "sha256": "36ceb388f9f11b63ad7fea64a2224a114a2164c9fdf5d2c478095f1cb039add2",
          "size_bytes": 1748,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/36ceb388f9f11b63ad7fea64a2224a114a2164c9fdf5d2c478095f1cb039add2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-30.md",
          "record_count": null,
          "sha256": "3c8361e19dd4bd0070e6e77135d9a374ccd52657c472e6b7b0226c8165e5ad23",
          "size_bytes": 1751,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/3c8361e19dd4bd0070e6e77135d9a374ccd52657c472e6b7b0226c8165e5ad23",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-08.md",
          "record_count": null,
          "sha256": "628a3e8f82be16f816e9792801bc32e17545ba2562c7538776c4addad59465ee",
          "size_bytes": 2259,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/628a3e8f82be16f816e9792801bc32e17545ba2562c7538776c4addad59465ee",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-09.md",
          "record_count": null,
          "sha256": "131abaca24648795596989fbb9f3630085b99fed7f4e67972722efe4b252fbd7",
          "size_bytes": 2259,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/131abaca24648795596989fbb9f3630085b99fed7f4e67972722efe4b252fbd7",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-13.md",
          "record_count": null,
          "sha256": "cee994e90d06a19ebc06e3c16a1591070df3c441b21c0201d171c49e1345722c",
          "size_bytes": 2259,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/cee994e90d06a19ebc06e3c16a1591070df3c441b21c0201d171c49e1345722c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-15.md",
          "record_count": null,
          "sha256": "1beada078196a92c135bf3b63a08176d4b9491a5f3a3f01a1cd926f155520d52",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/1beada078196a92c135bf3b63a08176d4b9491a5f3a3f01a1cd926f155520d52",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-16.md",
          "record_count": null,
          "sha256": "24ea1f008aebc02b439be04de1a411f7588ce3709af775af03247a05801528c3",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/24ea1f008aebc02b439be04de1a411f7588ce3709af775af03247a05801528c3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-19.md",
          "record_count": null,
          "sha256": "2f32b26f7c13cf86a0d59c45bfb6efafd69a093ace207aa995ab85ff9880bcc2",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/2f32b26f7c13cf86a0d59c45bfb6efafd69a093ace207aa995ab85ff9880bcc2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-20.md",
          "record_count": null,
          "sha256": "ebc60df0a25c4abdf9902e5fa1291a43204fff6d428c0cf8c44af3114cc82509",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/ebc60df0a25c4abdf9902e5fa1291a43204fff6d428c0cf8c44af3114cc82509",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-21.md",
          "record_count": null,
          "sha256": "c9da8922e28bc527f7ef5cc1df714cf10a1b4a9381b06440091e669c24bf149e",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c9da8922e28bc527f7ef5cc1df714cf10a1b4a9381b06440091e669c24bf149e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-23.md",
          "record_count": null,
          "sha256": "fb278e68b703500e2b97de27dfebfe69e7ab4b32262a3b3f21af0c79309cdc64",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/fb278e68b703500e2b97de27dfebfe69e7ab4b32262a3b3f21af0c79309cdc64",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-11_2026-07-09.md",
          "record_count": null,
          "sha256": "0cd141c22a2e3efa16b2c72f824cc9e3178ff826f85d52d96dbba6c5a5815e7f",
          "size_bytes": 1457,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/0cd141c22a2e3efa16b2c72f824cc9e3178ff826f85d52d96dbba6c5a5815e7f",
          "status": "captured"
        },
        {
          "first_date": "2026-07-10",
          "last_date": "2026-07-10",
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/manifest.json",
          "record_count": 1,
          "sha256": "b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6",
          "size_bytes": 4174,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6",
          "status": "captured"
        },
        {
          "first_date": "2026-03-19",
          "last_date": "2026-05-19",
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/trades.jsonl",
          "record_count": 9,
          "sha256": "8ae058057e8b9ee1ae52369d32cc0fa96b9575a01a71b4d50b0624eca709de9a",
          "size_bytes": 1638,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/8ae058057e8b9ee1ae52369d32cc0fa96b9575a01a71b4d50b0624eca709de9a",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/verdict.json",
          "record_count": 1,
          "sha256": "eec84c380b4696c652657886dfed8008a9b773df8cf89b72031bc7c13d0687fc",
          "size_bytes": 1799,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/eec84c380b4696c652657886dfed8008a9b773df8cf89b72031bc7c13d0687fc",
          "status": "captured"
        },
        {
          "first_date": "2026-07-10",
          "last_date": "2026-07-10",
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/manifest.json",
          "record_count": 1,
          "sha256": "f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381",
          "size_bytes": 4224,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381",
          "status": "captured"
        },
        {
          "first_date": "2026-03-02",
          "last_date": "2026-06-26",
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/trades.jsonl",
          "record_count": 25,
          "sha256": "58719f1fb223330affcec1287d4abf641d8f536500293025dbd5afc6c73d16be",
          "size_bytes": 4553,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/58719f1fb223330affcec1287d4abf641d8f536500293025dbd5afc6c73d16be",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/verdict.json",
          "record_count": 1,
          "sha256": "a7bd2ff9aae1dd62e6579dd0fd7eeb420be2d3c4ddd59ac96c93861aa1fd5ecf",
          "size_bytes": 1766,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/a7bd2ff9aae1dd62e6579dd0fd7eeb420be2d3c4ddd59ac96c93861aa1fd5ecf",
          "status": "captured"
        },
        {
          "first_date": "2026-08-07",
          "last_date": "2026-08-07",
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/manifest.json",
          "record_count": 1,
          "sha256": "82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26",
          "size_bytes": 2535,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26",
          "status": "captured"
        },
        {
          "first_date": "2026-07-01",
          "last_date": "2026-08-06",
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/trades.jsonl",
          "record_count": 69,
          "sha256": "5b445e7cd3a3c3b53db9d58a9333456a151f102d52e735086087c0a59caf83d5",
          "size_bytes": 6000,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/5b445e7cd3a3c3b53db9d58a9333456a151f102d52e735086087c0a59caf83d5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/verdict.json",
          "record_count": 1,
          "sha256": "c3e5e74bff341b76cb2c36abcf929e89253c270678cac61ce7ad4e9946b293ec",
          "size_bytes": 1728,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c3e5e74bff341b76cb2c36abcf929e89253c270678cac61ce7ad4e9946b293ec",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/2026-10-21-fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2.json",
          "record_count": 1,
          "sha256": "fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2",
          "size_bytes": 59389,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/2026-10-23-c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41.json",
          "record_count": 1,
          "sha256": "c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41",
          "size_bytes": 60806,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-21",
          "path": "output/research/shortline_comparisons/inputs/44486d2616f8883fa6cfcbe1a733878ca7d2bbe4d271c7723d99607b41f793c9-positions.jsonl",
          "record_count": 238,
          "sha256": "44486d2616f8883fa6cfcbe1a733878ca7d2bbe4d271c7723d99607b41f793c9",
          "size_bytes": 354771,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/44486d2616f8883fa6cfcbe1a733878ca7d2bbe4d271c7723d99607b41f793c9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/inputs/b9ccb2e357d807ca13750789c5be2ff66291656fc628a338db89a64ef2299674-training_rows.parquet",
          "record_count": null,
          "sha256": "b9ccb2e357d807ca13750789c5be2ff66291656fc628a338db89a64ef2299674",
          "size_bytes": 444415,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/b9ccb2e357d807ca13750789c5be2ff66291656fc628a338db89a64ef2299674",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/inputs/f2d411e221e7b3c78ad8180cea0ae768fc4b4f3a1265485135c646e4598dba0d-training_rows.parquet",
          "record_count": null,
          "sha256": "f2d411e221e7b3c78ad8180cea0ae768fc4b4f3a1265485135c646e4598dba0d",
          "size_bytes": 452371,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/f2d411e221e7b3c78ad8180cea0ae768fc4b4f3a1265485135c646e4598dba0d",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-23",
          "path": "output/research/shortline_comparisons/inputs/f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997-positions.jsonl",
          "record_count": 240,
          "sha256": "f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997",
          "size_bytes": 358936,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_experiments/2026-10-23/fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76.json",
          "record_count": 1,
          "sha256": "fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76",
          "size_bytes": 2836,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76",
          "status": "captured"
        },
        {
          "first_date": "2025-01-09",
          "last_date": "2026-10-23",
          "path": "reference/experience/distill_action_log.jsonl",
          "record_count": 158,
          "sha256": "caaff1fcad6b5663dd01d2720db8a126e1384045605ab602add068e378d52cac",
          "size_bytes": 159877,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/caaff1fcad6b5663dd01d2720db8a126e1384045605ab602add068e378d52cac",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "reference/experience/research_protocols.yaml",
          "record_count": null,
          "sha256": "ade8d7644a8ad7663bc1801ffa764fc386fe6a49ea669e377fe4c615308cd587",
          "size_bytes": 9662,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/ade8d7644a8ad7663bc1801ffa764fc386fe6a49ea669e377fe4c615308cd587",
          "status": "captured"
        },
        {
          "error": "Expecting value: line 1 column 1 (char 0)",
          "first_date": null,
          "last_date": null,
          "path": "reference/experience/xiaocao_hypotheses.jsonl",
          "record_count": null,
          "sha256": "d01e6dbaaa3219e9048d6d874a016c0143302a36995a20dca1310f2d8193de0f",
          "size_bytes": 364225,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/d01e6dbaaa3219e9048d6d874a016c0143302a36995a20dca1310f2d8193de0f",
          "status": "invalid"
        }
      ],
      "missing_patterns": [
        "output/research/weekly_comparison*.json",
        "output/live/posture_calibration.jsonl"
      ],
      "schema_version": 1,
      "sha256": "38590bf5f52c473dd1d62956104ee3754be55e4ffe0158e321ce0d82cb45cbfa",
      "source_semantics": "captured bytes; mtime is never an observation time"
    },
    "snapshot_manifest_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-23_inputs/38590bf5f52c473dd1d62956104ee3754be55e4ffe0158e321ce0d82cb45cbfa.manifest.json",
    "hypotheses": [
      {
        "hypothesis_id": "A_kp_star",
        "claim": "K->P top picks (variant A) beats take-all",
        "observed_at": "2026-10-16T15:15:00",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 84,
          "n_trades": 236,
          "p": 0.203997,
          "per_trade_spread": 0.6398,
          "test_edge": -0.086429,
          "train_edge": 1.353824
        },
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "B_vb_star",
        "claim": "K->P + auction tiebreak (variant B) beats take-all",
        "observed_at": "2026-10-16T15:15:00",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 84,
          "n_trades": 236,
          "p": 0.246052,
          "per_trade_spread": 0.605354,
          "test_edge": 0.099805,
          "train_edge": 1.102407
        },
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "XH-016",
        "claim": "出场层非-4602主因:逐笔配对 exit_timing 中性(+0.10%),真漏点=entry追高(+1.2~1.7%/笔)+负选股alpha;-4602 headline是book A/B不配对(book A仅覆盖~6/15+)的伪差",
        "observed_at": "2026-06-21T22:52:29",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.025,
          "n_days": 12,
          "n_trades": 44,
          "p": 0.920587,
          "per_trade_spread": 0.101864,
          "test_edge": 0.899037,
          "train_edge": -1.164235
        },
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "XH-001",
        "claim": "机械2%trailing杀趋势龙头卖飞:REJECTED-前提不成立(系统零趋势龙头持仓,全短线低吸mode);所持仓上trailing vs next-close=-0.26%/笔,不显著",
        "observed_at": "2026-06-21T22:52:29",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.025,
          "n_days": 11,
          "n_trades": 30,
          "p": 0.746217,
          "per_trade_spread": -0.255967,
          "test_edge": 0.634824,
          "train_edge": -1.420846
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "XH-011",
        "claim": "坏regime(bear+div)禁低吸mode:REJECTED-全年mode_history(1587笔/104天)skip比take亏-1.15%/笔(p=0.0003反向);低吸即便坏regime也正期望(bear~平-0.02%,div+1.99%),低胜率右偏,lever是抓右尾非按regime禁用",
        "observed_at": "2026-06-21T23:16:47",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.0125,
          "n_days": 104,
          "n_trades": 1587,
          "p": 0.000262,
          "per_trade_spread": -1.149909,
          "test_edge": -0.824224,
          "train_edge": -1.520804
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "XH-017",
        "claim": "连续N天广度恶化(死盘)窗口应空仓低吸 — primary abs(N=2,positive_ratio<0.40)",
        "observed_at": "2026-06-22T09:43:51",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.00625,
          "n_days": 258,
          "n_trades": 3827,
          "p": 0.002957,
          "per_trade_spread": -0.32006,
          "test_edge": -0.361687,
          "train_edge": -0.263952
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "XH-013",
        "claim": "趋势龙头选股是lever — momentum-leader proxy(top-10 by 60d momentum, liquid top-30%, 5d hold) beats market",
        "observed_at": "2026-06-22T09:51:40",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.008333333333333333,
          "n_days": 195,
          "n_trades": 195,
          "p": 0.039811,
          "per_trade_spread": -0.893363,
          "test_edge": -1.913247,
          "train_edge": 0.137035
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "XH-013b",
        "claim": "趋势主线选股(小草实际信号:轮动频率主线,非龙头非动量)beats 平均题材/广义参与",
        "observed_at": "2026-06-22T10:47:08",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.002777777777777778,
          "n_days": 31,
          "n_trades": 31,
          "p": 0.247396,
          "per_trade_spread": -0.158757,
          "test_edge": -0.193822,
          "train_edge": -0.121354
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "XH-037",
        "claim": "趋势尾声的短线起爆样本来自 raw qibao rank top10 + 电子/20cm + 开幅可控红盘非涨停，而不是严格高 jssb emitted qibao",
        "observed_at": "2026-06-30T21:31:08",
        "recorded_verdict": "PASS",
        "metrics": {
          "effective_alpha": 0.0071428571428571435,
          "n_days": 114,
          "n_trades": 164,
          "p": 0.0,
          "per_trade_spread": 3.970832,
          "test_edge": 4.266669,
          "train_edge": 3.682124
        },
        "rejected_by": [],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "C_mode_rotation_k_survivors",
        "claim": "K survivors + mode-rotation rank (variant C) beats take-all",
        "observed_at": "2026-08-14T15:26:12",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 29,
          "n_trades": 83,
          "p": 0.011414,
          "per_trade_spread": 2.048145,
          "test_edge": 0.657456,
          "train_edge": 3.472752
        },
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "D_qibao_benchmark_paper_promoted",
        "claim": "raw-qibao benchmark paper-promoted modes (variant D) beat take-all",
        "observed_at": "2026-07-17T15:29:18",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 11,
          "n_trades": 56,
          "p": 0.119046,
          "per_trade_spread": -1.382789,
          "test_edge": -3.010903,
          "train_edge": 0.245325
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "T_trend_L60_R20_M3",
        "claim": "Book T trend config trend_L60_R20_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "compounded_alpha": -3.292254,
          "compounded_base": 61.184641,
          "compounded_strat": 57.892387,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 22.258847,
          "n_holds": 33,
          "non_bull_alpha_mean": -0.096535,
          "non_bull_holds": 25,
          "p": 0.928893,
          "per_hold_alpha_mean": -0.020961,
          "per_hold_win": 0.393939,
          "test_alpha": 2.117802,
          "train_alpha": -4.098994,
          "turnover": 0.575758
        },
        "rejected_by": [
          "compounded_alpha_positive",
          "per_hold_alpha_positive",
          "walk_forward_consistent",
          "significant",
          "survives_non_bull"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "T_trend_L60_R30_M3",
        "claim": "Book T trend config trend_L60_R30_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "compounded_alpha": -4.218181,
          "compounded_base": 54.920842,
          "compounded_strat": 50.702661,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 14.821218,
          "n_holds": 20,
          "non_bull_alpha_mean": -0.044074,
          "non_bull_holds": 13,
          "p": 0.996811,
          "per_hold_alpha_mean": -0.002114,
          "per_hold_win": 0.3,
          "test_alpha": -11.751797,
          "train_alpha": 6.715885,
          "turnover": 0.633333
        },
        "rejected_by": [
          "compounded_alpha_positive",
          "per_hold_alpha_positive",
          "walk_forward_consistent",
          "significant",
          "survives_non_bull"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "T_trend_L60_R40_M3",
        "claim": "Book T trend config trend_L60_R40_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "compounded_alpha": 28.523084,
          "compounded_base": 48.804462,
          "compounded_strat": 77.327546,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 15.0798,
          "n_holds": 15,
          "non_bull_alpha_mean": 0.772923,
          "non_bull_holds": 9,
          "p": 0.089492,
          "per_hold_alpha_mean": 1.356336,
          "per_hold_win": 0.6,
          "test_alpha": 15.732935,
          "train_alpha": 7.176939,
          "turnover": 0.511111
        },
        "rejected_by": [
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "T_trend_L60_R60_M3",
        "claim": "Book T trend config trend_L60_R60_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "compounded_alpha": 20.092998,
          "compounded_base": 72.107611,
          "compounded_strat": 92.200609,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 1.698183,
          "n_holds": 9,
          "non_bull_alpha_mean": 1.583088,
          "non_bull_holds": 5,
          "p": 0.059952,
          "per_hold_alpha_mean": 1.428619,
          "per_hold_win": 0.666667,
          "test_alpha": 9.343668,
          "train_alpha": 5.758478,
          "turnover": 0.740741
        },
        "rejected_by": [
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "T_trend_L20_R20_M3",
        "claim": "Book T trend config trend_L20_R20_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "compounded_alpha": 0.73154,
          "compounded_base": 81.266265,
          "compounded_strat": 81.997805,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 22.797492,
          "n_holds": 36,
          "non_bull_alpha_mean": 0.139325,
          "non_bull_holds": 28,
          "p": 0.783293,
          "per_hold_alpha_mean": 0.071812,
          "per_hold_win": 0.361111,
          "test_alpha": 2.441335,
          "train_alpha": -1.078833,
          "turnover": 0.685185
        },
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "T_rotation_L60_R30_M3_W20_K5",
        "claim": "Book T trend config rotation_L60_R30_M3_W20_K5 beats average-theme beta under compounded return / drawdown / turnover guards",
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "compounded_alpha": 0.245326,
          "compounded_base": 50.453679,
          "compounded_strat": 50.699005,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 16.07246,
          "n_holds": 23,
          "non_bull_alpha_mean": 0.112839,
          "non_bull_holds": 15,
          "p": 0.860593,
          "per_hold_alpha_mean": 0.034973,
          "per_hold_win": 0.391304,
          "test_alpha": -2.51548,
          "train_alpha": 2.048847,
          "turnover": 0.405797
        },
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "aux_gray_n_fixed",
        "claim": "N字低吸灰区机制指标确认组跑赢中证1000",
        "observed_at": "2026-07-10T20:17:02",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.008333333333333333,
          "n_days": 9,
          "n_trades": 9,
          "p": 0.560284,
          "per_trade_spread": -1.356032,
          "test_edge": -2.259637,
          "train_edge": -0.226526
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "aux_gray_relay1_fixed",
        "claim": "接力低弱转1灰区机制指标确认组跑赢中证1000",
        "observed_at": "2026-07-10T20:17:09",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.008333333333333333,
          "n_days": 25,
          "n_trades": 25,
          "p": 0.851966,
          "per_trade_spread": -0.243076,
          "test_edge": -1.135733,
          "train_edge": 0.723968
        },
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      },
      {
        "hypothesis_id": "E_ai_intelligence_short_factor",
        "claim": "agent-reviewed AI intelligence short-factor bullish picks (variant E) beat take-all",
        "observed_at": "2026-08-14T15:26:12",
        "recorded_verdict": "REJECTED",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 13,
          "n_trades": 25,
          "p": 0.311072,
          "per_trade_spread": 1.055139,
          "test_edge": -0.660393,
          "train_edge": 2.403057
        },
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "3b3f0d04976b2674adc87f4ddf72b664d92e5230d9c07aa7d0f8871ed54ca2e4"
        },
        "scope": "historical_verdict_not_this_week",
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ]
      }
    ],
    "research_runs": [
      {
        "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/manifest.json",
        "sha256": "b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6",
        "hypothesis_id": "aux_gray_n_fixed",
        "observed_date": "2026-07-10",
        "recorded_verdict": "REJECTED",
        "conclusion": "insufficient_evidence",
        "n_rows": 9,
        "n_days": 9,
        "parameters": {
          "alpha": 0.05,
          "cache_only": true,
          "min_days": 8,
          "n_tried": 6
        },
        "diagnostics": {
          "attribution": {},
          "concentration": {
            "code_count": 8,
            "days": 9,
            "mean_hhi": 1.0,
            "mean_max_weight": 1.0,
            "mean_positions_per_day": 1.0,
            "top_code_share": 0.2222222222222222
          },
          "coverage": {
            "code": 9,
            "entry_slippage": 0,
            "exit_timing": 0,
            "exposure": 0,
            "gross_exposure": 0,
            "net_exposure": 0,
            "pick_alpha": 0,
            "position_weight": 0,
            "turnover": 0,
            "turnover_pct": 0,
            "weight": 0
          },
          "exposure": {},
          "turnover": {}
        },
        "recorded_metrics": {
          "day_weighted": {
            "base_day_mean": -0.01732374121047073,
            "n_days": 9,
            "spread": -1.3560319566832901,
            "strat_day_mean": -1.3733556978937609
          },
          "diagnostics": {
            "attribution": {},
            "concentration": {
              "code_count": 8,
              "days": 9,
              "mean_hhi": 1.0,
              "mean_max_weight": 1.0,
              "mean_positions_per_day": 1.0,
              "top_code_share": 0.2222222222222222
            },
            "coverage": {
              "code": 9,
              "entry_slippage": 0,
              "exit_timing": 0,
              "exposure": 0,
              "gross_exposure": 0,
              "net_exposure": 0,
              "pick_alpha": 0,
              "position_weight": 0,
              "turnover": 0,
              "turnover_pct": 0,
              "weight": 0
            },
            "exposure": {},
            "turnover": {}
          },
          "guards": {
            "cache_only": true,
            "enough_days": true,
            "significant": false,
            "survives_per_trade_equal_weight": false,
            "walk_forward_consistent": false
          },
          "n_days": 9,
          "n_trades": 9,
          "per_trade": {
            "base_mean": -0.01732374121047073,
            "n": 9,
            "spread": -1.3560319566832901,
            "strat_mean": -1.3733556978937609,
            "win_base": 0.6666666666666666,
            "win_strat": 0.4444444444444444
          },
          "rejected_by": [
            "survives_per_trade_equal_weight",
            "walk_forward_consistent",
            "significant"
          ],
          "significance": {
            "alpha": 0.05,
            "df": 8,
            "effective_alpha": 0.008333333333333333,
            "n_days": 9,
            "p": 0.5602843716724684,
            "t": -0.6076252228905529
          },
          "verdict": "REJECTED",
          "walk_forward": {
            "consistent": false,
            "min_edge": 0.0,
            "retain_ratio": 0.5,
            "test_days": 5,
            "test_edge": -2.2596367589021926,
            "train_days": 4,
            "train_edge": -0.22652595390966201
          },
          "warnings": [
            "multiple comparison: 6 hypotheses tried -> effective alpha 0.0083 (raw p=0.5603)"
          ]
        },
        "missing_evidence": [
          "paired_cost_fill_chronology_comparison_missing"
        ],
        "scope": "recorded_run_not_a_new_research_verdict"
      },
      {
        "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/manifest.json",
        "sha256": "f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381",
        "hypothesis_id": "aux_gray_relay1_fixed",
        "observed_date": "2026-07-10",
        "recorded_verdict": "REJECTED",
        "conclusion": "insufficient_evidence",
        "n_rows": 25,
        "n_days": 25,
        "parameters": {
          "alpha": 0.05,
          "cache_only": true,
          "min_days": 8,
          "n_tried": 6
        },
        "diagnostics": {
          "attribution": {},
          "concentration": {
            "code_count": 25,
            "days": 25,
            "mean_hhi": 1.0,
            "mean_max_weight": 1.0,
            "mean_positions_per_day": 1.0,
            "top_code_share": 0.04
          },
          "coverage": {
            "code": 25,
            "entry_slippage": 0,
            "exit_timing": 0,
            "exposure": 0,
            "gross_exposure": 0,
            "net_exposure": 0,
            "pick_alpha": 0,
            "position_weight": 0,
            "turnover": 0,
            "turnover_pct": 0,
            "weight": 0
          },
          "exposure": {},
          "turnover": {}
        },
        "recorded_metrics": {
          "day_weighted": {
            "base_day_mean": 0.18044140618176385,
            "n_days": 25,
            "spread": -0.2430764141178075,
            "strat_day_mean": -0.06263500793604367
          },
          "diagnostics": {
            "attribution": {},
            "concentration": {
              "code_count": 25,
              "days": 25,
              "mean_hhi": 1.0,
              "mean_max_weight": 1.0,
              "mean_positions_per_day": 1.0,
              "top_code_share": 0.04
            },
            "coverage": {
              "code": 25,
              "entry_slippage": 0,
              "exit_timing": 0,
              "exposure": 0,
              "gross_exposure": 0,
              "net_exposure": 0,
              "pick_alpha": 0,
              "position_weight": 0,
              "turnover": 0,
              "turnover_pct": 0,
              "weight": 0
            },
            "exposure": {},
            "turnover": {}
          },
          "guards": {
            "cache_only": true,
            "enough_days": true,
            "significant": false,
            "survives_per_trade_equal_weight": false,
            "walk_forward_consistent": false
          },
          "n_days": 25,
          "n_trades": 25,
          "per_trade": {
            "base_mean": 0.18044140618176385,
            "n": 25,
            "spread": -0.2430764141178075,
            "strat_mean": -0.06263500793604367,
            "win_base": 0.52,
            "win_strat": 0.44
          },
          "rejected_by": [
            "survives_per_trade_equal_weight",
            "walk_forward_consistent",
            "significant"
          ],
          "significance": {
            "alpha": 0.05,
            "df": 24,
            "effective_alpha": 0.008333333333333333,
            "n_days": 25,
            "p": 0.8519658562785479,
            "t": -0.18863379439735747
          },
          "verdict": "REJECTED",
          "walk_forward": {
            "consistent": false,
            "min_edge": 0.0,
            "retain_ratio": 0.5,
            "test_days": 13,
            "test_edge": -1.1357327739653573,
            "train_days": 12,
            "train_edge": 0.723967975717038
          },
          "warnings": [
            "multiple comparison: 6 hypotheses tried -> effective alpha 0.0083 (raw p=0.8520)"
          ]
        },
        "missing_evidence": [
          "paired_cost_fill_chronology_comparison_missing"
        ],
        "scope": "recorded_run_not_a_new_research_verdict"
      },
      {
        "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/manifest.json",
        "sha256": "82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26",
        "hypothesis_id": "C_mode_rotation_k_survivors",
        "observed_date": "2026-08-07",
        "recorded_verdict": "REJECTED",
        "conclusion": "insufficient_evidence",
        "n_rows": 69,
        "n_days": 24,
        "parameters": {
          "alpha": 0.05,
          "cache_only": true,
          "min_days": 8,
          "n_tried": 20
        },
        "diagnostics": {
          "attribution": {},
          "concentration": {
            "code_count": 0,
            "days": 24,
            "mean_hhi": 0.3541666666666667,
            "mean_max_weight": 0.3541666666666667,
            "mean_positions_per_day": 2.875,
            "top_code_share": null
          },
          "coverage": {
            "code": 0,
            "entry_slippage": 0,
            "exit_timing": 0,
            "exposure": 0,
            "gross_exposure": 0,
            "net_exposure": 0,
            "pick_alpha": 0,
            "position_weight": 0,
            "turnover": 0,
            "turnover_pct": 0,
            "weight": 0
          },
          "exposure": {},
          "turnover": {}
        },
        "recorded_metrics": {
          "day_weighted": {
            "base_day_mean": -0.7478146241578102,
            "n_days": 24,
            "spread": 2.632750868976928,
            "strat_day_mean": 1.8849362448191176
          },
          "diagnostics": {
            "attribution": {},
            "concentration": {
              "code_count": 0,
              "days": 24,
              "mean_hhi": 0.3541666666666667,
              "mean_max_weight": 0.3541666666666667,
              "mean_positions_per_day": 2.875,
              "top_code_share": null
            },
            "coverage": {
              "code": 0,
              "entry_slippage": 0,
              "exit_timing": 0,
              "exposure": 0,
              "gross_exposure": 0,
              "net_exposure": 0,
              "pick_alpha": 0,
              "position_weight": 0,
              "turnover": 0,
              "turnover_pct": 0,
              "weight": 0
            },
            "exposure": {},
            "turnover": {}
          },
          "guards": {
            "cache_only": true,
            "enough_days": true,
            "significant": false,
            "survives_per_trade_equal_weight": true,
            "walk_forward_consistent": true
          },
          "n_days": 24,
          "n_trades": 69,
          "per_trade": {
            "base_mean": -0.8254001891794922,
            "n": 69,
            "spread": 2.7027947463668642,
            "strat_mean": 1.8773945571873722,
            "win_base": 0.3333333333333333,
            "win_strat": 0.5942028985507246
          },
          "rejected_by": [
            "significant"
          ],
          "significance": {
            "alpha": 0.05,
            "df": 23,
            "effective_alpha": 0.0025,
            "n_days": 24,
            "p": 0.0029941506703336273,
            "t": 3.318449146207758
          },
          "verdict": "REJECTED",
          "walk_forward": {
            "consistent": true,
            "min_edge": 0.0,
            "retain_ratio": 0.5,
            "test_days": 12,
            "test_edge": 2.194681808538497,
            "train_days": 12,
            "train_edge": 3.19639017168585
          },
          "warnings": [
            "multiple comparison: 20 hypotheses tried -> effective alpha 0.0025 (raw p=0.0030)"
          ]
        },
        "missing_evidence": [
          "paired_cost_fill_chronology_comparison_missing"
        ],
        "scope": "recorded_run_not_a_new_research_verdict"
      }
    ],
    "option_comparison": {
      "options": [
        {
          "option": "baseline_no_kol",
          "conclusion": "insufficient_evidence",
          "mean_net_ret": null,
          "missing_evidence": [
            "saved_three_option_paired_comparison_missing"
          ]
        },
        {
          "option": "current_bounded",
          "conclusion": "insufficient_evidence",
          "mean_net_ret": null,
          "missing_evidence": [
            "saved_three_option_paired_comparison_missing"
          ]
        },
        {
          "option": "kol_challenger",
          "conclusion": "insufficient_evidence",
          "mean_net_ret": null,
          "missing_evidence": [
            "saved_three_option_paired_comparison_missing"
          ]
        }
      ],
      "comparisons": []
    },
    "paper_fill_audit": {
      "windows": {
        "1w": {
          "start": "2026-10-17",
          "end": "2026-10-23",
          "entry_count": 7,
          "fallback_count": 0,
          "proxy_count": 0,
          "unknown_count": 0,
          "reported_window_count": 7,
          "confirmed_window_count": 0,
          "fallback_proportion": 0.0,
          "proxy_proportion": 0.0,
          "excluded_from_confirmed_count": 7,
          "by_book": {
            "A": {
              "reported_window": 3
            },
            "B": {
              "reported_window": 4
            }
          }
        },
        "4w": {
          "start": "2026-09-26",
          "end": "2026-10-23",
          "entry_count": 28,
          "fallback_count": 0,
          "proxy_count": 0,
          "unknown_count": 0,
          "reported_window_count": 28,
          "confirmed_window_count": 0,
          "fallback_proportion": 0.0,
          "proxy_proportion": 0.0,
          "excluded_from_confirmed_count": 28,
          "by_book": {
            "A": {
              "reported_window": 11
            },
            "B": {
              "reported_window": 14
            },
            "T": {
              "reported_window": 3
            }
          }
        },
        "12w": {
          "start": "2026-08-01",
          "end": "2026-10-23",
          "entry_count": 72,
          "fallback_count": 0,
          "proxy_count": 0,
          "unknown_count": 0,
          "reported_window_count": 72,
          "confirmed_window_count": 0,
          "fallback_proportion": 0.0,
          "proxy_proportion": 0.0,
          "excluded_from_confirmed_count": 72,
          "by_book": {
            "A": {
              "reported_window": 31
            },
            "B": {
              "reported_window": 37
            },
            "T": {
              "reported_window": 4
            }
          }
        }
      },
      "invalid_identity_count": 0,
      "count_semantics": "unique book/code/entry_date/shares/price entries; positions and BUY duplicates merged",
      "limitations": [
        "reported_window is a saved label without original window/hash/clock verification",
        "all legacy labels remain excluded from executable confirmation; comparison originals are verified separately",
        "paper audit is not a no-KOL counterfactual or an alpha estimate"
      ]
    },
    "accounting_observations": [
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/11331e61bb9b0d825b7e70c84122e935889523a4c4e294a47fb678c5f1b0d04c.json",
          "sha256": "40fabc542a25482dc8516d32678679e56c7473c8b00336eb3fd615356dc96f8f"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 32,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "b33a0b9fa17bfda225b62a565842f5fa2a1eaace64af4b02e40e8fd69cd83a30",
            "ledger_cash": "440.56",
            "net_contributed_capital": "65845.40",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              }
            ],
            "provisional_realized_pnl": "2393.94",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "410.84",
            "broker_snapshot_sha256": "5ce343875d5a52b4ab36008961c06081c2b2f977afd7adf66f2185b0cd652c70",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "410.84",
            "cash_basis": "app_available_cash",
            "cash_difference": "-29.72",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "30982.788174",
            "cumulative_pnl": null,
            "deployable_cash": "410.84",
            "entry_count": 32,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "6.78",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "b33a0b9fa17bfda225b62a565842f5fa2a1eaace64af4b02e40e8fd69cd83a30",
            "ledger_cash": "440.56",
            "liquidation_nav": "68220.06",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "000573.XSHE",
                "owned_lot_id": "book-b:2026-10-20:000573.XSHE:BUY",
                "remaining_cost": "33869.38",
                "shares": 8200
              },
              {
                "code": "301052.XSHE",
                "owned_lot_id": "book-b:2026-10-21:301052.XSHE:BUY",
                "remaining_cost": "16491.65",
                "shares": 500
              },
              {
                "code": "002889.XSHE",
                "owned_lot_id": "book-b:2026-10-21:002889.XSHE:BUY",
                "remaining_cost": "17437.75",
                "shares": 1200
              }
            ],
            "marked_nav": "68226.84",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-21T01:31:08.677000+00:00",
            "observed_cash": "410.84",
            "opening_capital": "30000.00",
            "owned_market_value": "67816.00",
            "ownership_head_sha256": "dbaf87759ba37efb6359929f883008d5ae11d3c0fe94002b1faf95b7b0361684",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              }
            ],
            "provisional_realized_pnl": "2393.94",
            "provisional_unrealized_pnl": "17.22",
            "realized_pnl": null,
            "receipt_sha256": "43371f74a011398377b842e8d033019c4a1fcab5262b2a21c5a186395153899d",
            "remaining_cost": "67798.78",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "68226.84",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-21T01:31:08.677000+00:00",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "43371f74a011398377b842e8d033019c4a1fcab5262b2a21c5a186395153899d",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "68226.84",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-21T01:31:08.677000+00:00",
          "pending_fee_orders": [
            {
              "broker_order_id": "6000356",
              "code": "603029.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-02"
            },
            {
              "broker_order_id": "6007173",
              "code": "603029.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-04"
            },
            {
              "broker_order_id": "6000331",
              "code": "600059.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-07"
            },
            {
              "broker_order_id": "6003964",
              "code": "600059.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-10"
            },
            {
              "broker_order_id": "6002204",
              "code": "000572.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-16"
            },
            {
              "broker_order_id": "6002446",
              "code": "001209.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002462",
              "code": "002585.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002181",
              "code": "002585.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6005091",
              "code": "000572.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6006397",
              "code": "001209.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-28"
            },
            {
              "broker_order_id": "6000056",
              "code": "301382.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6000057",
              "code": "603042.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6004842",
              "code": "603042.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-30"
            },
            {
              "broker_order_id": "6001466",
              "code": "301382.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-08"
            },
            {
              "broker_order_id": "6000118",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6000131",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6001129",
              "code": "605366.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005170",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005182",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6002860",
              "code": "605366.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-13"
            },
            {
              "broker_order_id": "6000110",
              "code": "002531.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-14"
            },
            {
              "broker_order_id": "6001777",
              "code": "002531.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-15"
            },
            {
              "broker_order_id": "6000056",
              "code": "300107.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6000057",
              "code": "601188.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6005007",
              "code": "300107.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6005018",
              "code": "601188.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6000065",
              "code": "000573.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-20"
            },
            {
              "broker_order_id": "6000066",
              "code": "301052.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6000068",
              "code": "002889.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "43371f74a011398377b842e8d033019c4a1fcab5262b2a21c5a186395153899d",
          "unrealized_pnl": null
        },
        "observed_at": "2026-10-21T01:31:08.677000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/11d6809532302a8058c19b61f45652ac7c50d7ee7c58941c3f599e75b5fa8944.json",
          "sha256": "c576c3bb194a4148f83d9bfe84068140e24696dce3a16cc558f7bda46f2c4f7b"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 24,
            "journal_head_sha256": "56a323b8cce27e2e8e441763c20c059cdabc209cc9d0b653bf1f2685a40a0491",
            "ledger_cash": "56357.60",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "1895.56"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "67749.36",
            "broker_snapshot_sha256": "b81d85b9fc6a57756de20771ff3b306d6263b8659e69ccc4e2da4da91e9939d8",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "56357.60",
            "cash_basis": "app_available_cash",
            "cash_difference": "11391.76",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "30686.397610",
            "cumulative_pnl": null,
            "deployable_cash": "56357.60",
            "entry_count": 24,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "56a323b8cce27e2e8e441763c20c059cdabc209cc9d0b653bf1f2685a40a0491",
            "ledger_cash": "56357.60",
            "liquidation_nav": "56357.60",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "56357.60",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-15T07:20:03.515000+00:00",
            "observed_cash": "67749.36",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "9d1b35ceeba9683eca4a6a1d9b82494c0d39e2dd3c499965a57c527e723b6db8",
            "realized_pnl": "1895.56",
            "receipt_sha256": "6ec9c4b42fe5cfd6acc496bbb8c78c412476193809e1784cb6e77336fd7a31d1",
            "remaining_cost": "0.00",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "0.00"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "67749.36",
          "broker_snapshot_sha256": "b81d85b9fc6a57756de20771ff3b306d6263b8659e69ccc4e2da4da91e9939d8",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "56357.60",
          "cash_basis": "app_available_cash",
          "cash_difference": "11391.76",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "30686.397610",
          "cumulative_pnl": null,
          "deployable_cash": "56357.60",
          "entry_count": 24,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "0.00",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "56a323b8cce27e2e8e441763c20c059cdabc209cc9d0b653bf1f2685a40a0491",
          "ledger_cash": "56357.60",
          "liquidation_nav": "56357.60",
          "logical_account_id": "primary",
          "lots": [],
          "marked_nav": "56357.60",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-15T07:20:03.515000+00:00",
          "observed_cash": "67749.36",
          "opening_capital": "30000.00",
          "owned_market_value": "0.00",
          "ownership_head_sha256": "9d1b35ceeba9683eca4a6a1d9b82494c0d39e2dd3c499965a57c527e723b6db8",
          "realized_pnl": "1895.56",
          "receipt_sha256": "6ec9c4b42fe5cfd6acc496bbb8c78c412476193809e1784cb6e77336fd7a31d1",
          "remaining_cost": "0.00",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "0.00"
        },
        "observed_at": "2026-10-15T07:20:03.515000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/12a8ecd8fd2c7b21dc89e55b97e8bba49d4061e7cc525fae615650ab0d88c709.json",
          "sha256": "05aad28a8c54f6d511525d6429c19568112edfd3414e05f91b7acf3c03643758"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 30,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "fc62a8e9f225a5bdb7a1031e003a17f71c3f931116c63c8da6940e66cd4c6d0a",
            "ledger_cash": "34369.96",
            "net_contributed_capital": "65845.40",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              }
            ],
            "provisional_realized_pnl": "2393.94",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "34347.84",
            "broker_snapshot_sha256": "59fd8323ee40639150a2b9da3913b7b2a0546be5909d92cc0b9a0598648264fb",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "34347.84",
            "cash_basis": "app_available_cash",
            "cash_difference": "-22.12",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "30717.763400",
            "cumulative_pnl": null,
            "deployable_cash": "34347.84",
            "entry_count": 30,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.33",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "fc62a8e9f225a5bdb7a1031e003a17f71c3f931116c63c8da6940e66cd4c6d0a",
            "ledger_cash": "34369.96",
            "liquidation_nav": "67636.51",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "000573.XSHE",
                "owned_lot_id": "book-b:2026-10-20:000573.XSHE:BUY",
                "remaining_cost": "33869.38",
                "shares": 8200
              }
            ],
            "marked_nav": "67639.84",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-20T01:31:47.456000+00:00",
            "observed_cash": "34347.84",
            "opening_capital": "30000.00",
            "owned_market_value": "33292.00",
            "ownership_head_sha256": "e8d9ebd37220d9d4d315e7685bbc8d232392e5c2b72a81cd095b1a73e7d59296",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              }
            ],
            "provisional_realized_pnl": "2393.94",
            "provisional_unrealized_pnl": "-577.38",
            "realized_pnl": null,
            "receipt_sha256": "ae06e99cb5f87e796298a8b434d6ac8e54c060a9fdd5dac773cf84e52fe892fc",
            "remaining_cost": "33869.38",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "67639.84",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-20T01:31:47.456000+00:00",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "ae06e99cb5f87e796298a8b434d6ac8e54c060a9fdd5dac773cf84e52fe892fc",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "67639.84",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-20T01:31:47.456000+00:00",
          "pending_fee_orders": [
            {
              "broker_order_id": "6000356",
              "code": "603029.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-02"
            },
            {
              "broker_order_id": "6007173",
              "code": "603029.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-04"
            },
            {
              "broker_order_id": "6000331",
              "code": "600059.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-07"
            },
            {
              "broker_order_id": "6003964",
              "code": "600059.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-10"
            },
            {
              "broker_order_id": "6002204",
              "code": "000572.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-16"
            },
            {
              "broker_order_id": "6002446",
              "code": "001209.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002462",
              "code": "002585.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002181",
              "code": "002585.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6005091",
              "code": "000572.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6006397",
              "code": "001209.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-28"
            },
            {
              "broker_order_id": "6000056",
              "code": "301382.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6000057",
              "code": "603042.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6004842",
              "code": "603042.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-30"
            },
            {
              "broker_order_id": "6001466",
              "code": "301382.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-08"
            },
            {
              "broker_order_id": "6000118",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6000131",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6001129",
              "code": "605366.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005170",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005182",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6002860",
              "code": "605366.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-13"
            },
            {
              "broker_order_id": "6000110",
              "code": "002531.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-14"
            },
            {
              "broker_order_id": "6001777",
              "code": "002531.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-15"
            },
            {
              "broker_order_id": "6000056",
              "code": "300107.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6000057",
              "code": "601188.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6005007",
              "code": "300107.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6005018",
              "code": "601188.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6000065",
              "code": "000573.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-20"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "ae06e99cb5f87e796298a8b434d6ac8e54c060a9fdd5dac773cf84e52fe892fc",
          "unrealized_pnl": null
        },
        "observed_at": "2026-10-20T01:31:47.456000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/189f1f5f0f67564a9e27214fb7b28800dce60f3cd661e5bab906571e96b01ff1.json",
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 14,
            "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
            "ledger_cash": "41432.28",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-1329.59"
          },
          "valuation": {
            "book": "B",
            "broker_snapshot_sha256": "74bd64f21b47f599e5f58e7313a060db3abf3f97cde754a1055e4691db8320aa",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "41432.28",
            "cash_basis": "app_available_cash",
            "cash_difference": "0.00",
            "conservative_risk_nav": "29241.010000",
            "cumulative_pnl": "-757.76",
            "entry_count": 14,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "1.23",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
            "ledger_cash": "41432.28",
            "liquidation_nav": "53703.05",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "301382.XSHE",
                "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
                "remaining_cost": "3869.39",
                "shares": 100
              },
              {
                "code": "603042.XSHG",
                "owned_lot_id": "book-b:2026-09-29:603042.XSHG:BUY",
                "remaining_cost": "7830.78",
                "shares": 500
              }
            ],
            "marked_nav": "53704.28",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-09-29T07:46:17.739000+00:00",
            "opening_capital": "30000.00",
            "owned_market_value": "12272.00",
            "ownership_head_sha256": "42dc690f35cd42e326a311a555a1c61c75a755a91d51229d6ccc3b9d93dec188",
            "realized_pnl": "-1329.59",
            "receipt_sha256": "4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c",
            "remaining_cost": "11700.17",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "reconciled",
            "unrealized_pnl": "571.83"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_snapshot_sha256": "74bd64f21b47f599e5f58e7313a060db3abf3f97cde754a1055e4691db8320aa",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "41432.28",
          "cash_basis": "app_available_cash",
          "cash_difference": "0.00",
          "conservative_risk_nav": "29241.010000",
          "cumulative_pnl": "-757.76",
          "entry_count": 14,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "1.23",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
          "ledger_cash": "41432.28",
          "liquidation_nav": "53703.05",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "301382.XSHE",
              "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
              "remaining_cost": "3869.39",
              "shares": 100
            },
            {
              "code": "603042.XSHG",
              "owned_lot_id": "book-b:2026-09-29:603042.XSHG:BUY",
              "remaining_cost": "7830.78",
              "shares": 500
            }
          ],
          "marked_nav": "53704.28",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-09-29T07:46:17.739000+00:00",
          "opening_capital": "30000.00",
          "owned_market_value": "12272.00",
          "ownership_head_sha256": "42dc690f35cd42e326a311a555a1c61c75a755a91d51229d6ccc3b9d93dec188",
          "realized_pnl": "-1329.59",
          "receipt_sha256": "4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c",
          "remaining_cost": "11700.17",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "reconciled",
          "unrealized_pnl": "571.83"
        },
        "observed_at": "2026-09-29T07:46:17.739000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/1c356652b0500fa5e8b6f0bc71ba013a70c9eda8d359d8c4f21b3049bc1d6ae9.json",
          "sha256": "10b9eb24cb29b0cbba07b563d76eb1d998d5bf4b27b3dd346e76a709c27e8d9d"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 33,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "6b2ca5650c30470359b3ab3e11040f3efe7dac106dd445c963f5837aa9e3d503",
            "ledger_cash": "33811.23",
            "net_contributed_capital": "65845.40",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              }
            ],
            "provisional_realized_pnl": "1895.23",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "45089.75",
            "broker_snapshot_sha256": "04f581e53c10f9d8ef1780ae35d3b3e6387bffee2e45070b97e24bd96d873694",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "33811.23",
            "cash_basis": "app_available_cash",
            "cash_difference": "11278.52",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29811.052129",
            "cumulative_pnl": null,
            "deployable_cash": "33811.23",
            "entry_count": 33,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.18",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "6b2ca5650c30470359b3ab3e11040f3efe7dac106dd445c963f5837aa9e3d503",
            "ledger_cash": "33811.23",
            "liquidation_nav": "65640.05",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "301052.XSHE",
                "owned_lot_id": "book-b:2026-10-21:301052.XSHE:BUY",
                "remaining_cost": "16491.65",
                "shares": 500
              },
              {
                "code": "002889.XSHE",
                "owned_lot_id": "book-b:2026-10-21:002889.XSHE:BUY",
                "remaining_cost": "17437.75",
                "shares": 1200
              }
            ],
            "marked_nav": "65643.23",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-22T01:30:40.511000+00:00",
            "observed_cash": "45089.75",
            "opening_capital": "30000.00",
            "owned_market_value": "31832.00",
            "ownership_head_sha256": "01483dffb656f3a6a1b65aa8286040b7024949cbde3d1a0d46aed526c75608c1",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              }
            ],
            "provisional_realized_pnl": "1895.23",
            "provisional_unrealized_pnl": "-2097.40",
            "realized_pnl": null,
            "receipt_sha256": "a476716acfaa949710a32b6fedde40e19641b7d78ad38f21c21a6a1d2eec5510",
            "remaining_cost": "33929.40",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65643.23",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-22T01:30:40.511000+00:00",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "a476716acfaa949710a32b6fedde40e19641b7d78ad38f21c21a6a1d2eec5510",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65643.23",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-22T01:30:40.511000+00:00",
          "pending_fee_orders": [
            {
              "broker_order_id": "6000356",
              "code": "603029.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-02"
            },
            {
              "broker_order_id": "6007173",
              "code": "603029.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-04"
            },
            {
              "broker_order_id": "6000331",
              "code": "600059.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-07"
            },
            {
              "broker_order_id": "6003964",
              "code": "600059.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-10"
            },
            {
              "broker_order_id": "6002204",
              "code": "000572.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-16"
            },
            {
              "broker_order_id": "6002446",
              "code": "001209.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002462",
              "code": "002585.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002181",
              "code": "002585.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6005091",
              "code": "000572.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6006397",
              "code": "001209.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-28"
            },
            {
              "broker_order_id": "6000056",
              "code": "301382.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6000057",
              "code": "603042.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6004842",
              "code": "603042.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-30"
            },
            {
              "broker_order_id": "6001466",
              "code": "301382.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-08"
            },
            {
              "broker_order_id": "6000118",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6000131",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6001129",
              "code": "605366.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005170",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005182",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6002860",
              "code": "605366.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-13"
            },
            {
              "broker_order_id": "6000110",
              "code": "002531.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-14"
            },
            {
              "broker_order_id": "6001777",
              "code": "002531.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-15"
            },
            {
              "broker_order_id": "6000056",
              "code": "300107.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6000057",
              "code": "601188.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6005007",
              "code": "300107.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6005018",
              "code": "601188.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6000065",
              "code": "000573.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-20"
            },
            {
              "broker_order_id": "6000066",
              "code": "301052.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6000068",
              "code": "002889.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6003685",
              "code": "000573.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-21"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "a476716acfaa949710a32b6fedde40e19641b7d78ad38f21c21a6a1d2eec5510",
          "unrealized_pnl": null
        },
        "observed_at": "2026-10-22T01:30:40.511000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/1d1864f5b755f1ed207f96e0af7fda45fc41acb182855665215b33fc52b587e8.json",
          "sha256": "22a52777249e095a3a1c3306a04ce8ae80a9d8be78d275cb16e7a7b92e784a5e"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 36,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "1a9d59f7f8e7846ec331f9eaa86be0fc8b25d2c67a685515bbcf4ac7ae6fdbf9",
            "ledger_cash": "32360.93",
            "net_contributed_capital": "65845.40",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6001953",
                "code": "301052.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6001284",
                "code": "002889.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6000059",
                "code": "002172.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-23"
              }
            ],
            "provisional_realized_pnl": "-1295.25",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "43614.38",
            "broker_snapshot_sha256": "53e84362141b240d2b597037c8b5c8ace07834565749587f33edb8a286b88ae4",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "32360.93",
            "cash_basis": "app_available_cash",
            "cash_difference": "11253.45",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29557.908167",
            "cumulative_pnl": null,
            "deployable_cash": "32360.93",
            "entry_count": 36,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.27",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "1a9d59f7f8e7846ec331f9eaa86be0fc8b25d2c67a685515bbcf4ac7ae6fdbf9",
            "ledger_cash": "32360.93",
            "liquidation_nav": "65082.66",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "002172.XSHE",
                "owned_lot_id": "book-b:2026-10-23:002172.XSHE:BUY",
                "remaining_cost": "32189.22",
                "shares": 7700
              }
            ],
            "marked_nav": "65085.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-23T01:31:45.282000+00:00",
            "observed_cash": "43614.38",
            "opening_capital": "30000.00",
            "owned_market_value": "32725.00",
            "ownership_head_sha256": "85d427e532265a7e2fb4a204c44824e395d00d53f4e5b2735fafbe8d90a14580",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6001953",
                "code": "301052.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6001284",
                "code": "002889.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6000059",
                "code": "002172.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-23"
              }
            ],
            "provisional_realized_pnl": "-1295.25",
            "provisional_unrealized_pnl": "535.78",
            "realized_pnl": null,
            "receipt_sha256": "b6fb918c67ccf8c7a4c094a45f87a253da69c875e7db78086a92d27aa7ccb779",
            "remaining_cost": "32189.22",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65085.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-23T01:31:45.282000+00:00",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6001953",
                "code": "301052.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6001284",
                "code": "002889.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6000059",
                "code": "002172.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-23"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "b6fb918c67ccf8c7a4c094a45f87a253da69c875e7db78086a92d27aa7ccb779",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65085.93",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-23T01:31:45.282000+00:00",
          "pending_fee_orders": [
            {
              "broker_order_id": "6000356",
              "code": "603029.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-02"
            },
            {
              "broker_order_id": "6007173",
              "code": "603029.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-04"
            },
            {
              "broker_order_id": "6000331",
              "code": "600059.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-07"
            },
            {
              "broker_order_id": "6003964",
              "code": "600059.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-10"
            },
            {
              "broker_order_id": "6002204",
              "code": "000572.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-16"
            },
            {
              "broker_order_id": "6002446",
              "code": "001209.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002462",
              "code": "002585.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002181",
              "code": "002585.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6005091",
              "code": "000572.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6006397",
              "code": "001209.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-28"
            },
            {
              "broker_order_id": "6000056",
              "code": "301382.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6000057",
              "code": "603042.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6004842",
              "code": "603042.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-30"
            },
            {
              "broker_order_id": "6001466",
              "code": "301382.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-08"
            },
            {
              "broker_order_id": "6000118",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6000131",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6001129",
              "code": "605366.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005170",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005182",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6002860",
              "code": "605366.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-13"
            },
            {
              "broker_order_id": "6000110",
              "code": "002531.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-14"
            },
            {
              "broker_order_id": "6001777",
              "code": "002531.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-15"
            },
            {
              "broker_order_id": "6000056",
              "code": "300107.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6000057",
              "code": "601188.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6005007",
              "code": "300107.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6005018",
              "code": "601188.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6000065",
              "code": "000573.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-20"
            },
            {
              "broker_order_id": "6000066",
              "code": "301052.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6000068",
              "code": "002889.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6003685",
              "code": "000573.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6001953",
              "code": "301052.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-22"
            },
            {
              "broker_order_id": "6001284",
              "code": "002889.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-22"
            },
            {
              "broker_order_id": "6000059",
              "code": "002172.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-23"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "b6fb918c67ccf8c7a4c094a45f87a253da69c875e7db78086a92d27aa7ccb779",
          "unrealized_pnl": null
        },
        "observed_at": "2026-10-23T01:31:45.282000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c.json",
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 14,
            "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
            "ledger_cash": "41432.28",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-1329.59"
          },
          "valuation": {
            "book": "B",
            "broker_snapshot_sha256": "74bd64f21b47f599e5f58e7313a060db3abf3f97cde754a1055e4691db8320aa",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "41432.28",
            "cash_basis": "app_available_cash",
            "cash_difference": "0.00",
            "conservative_risk_nav": "29241.010000",
            "cumulative_pnl": "-757.76",
            "entry_count": 14,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "1.23",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
            "ledger_cash": "41432.28",
            "liquidation_nav": "53703.05",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "301382.XSHE",
                "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
                "remaining_cost": "3869.39",
                "shares": 100
              },
              {
                "code": "603042.XSHG",
                "owned_lot_id": "book-b:2026-09-29:603042.XSHG:BUY",
                "remaining_cost": "7830.78",
                "shares": 500
              }
            ],
            "marked_nav": "53704.28",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-09-29T07:46:17.739000+00:00",
            "opening_capital": "30000.00",
            "owned_market_value": "12272.00",
            "ownership_head_sha256": "42dc690f35cd42e326a311a555a1c61c75a755a91d51229d6ccc3b9d93dec188",
            "realized_pnl": "-1329.59",
            "receipt_sha256": "4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c",
            "remaining_cost": "11700.17",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "reconciled",
            "unrealized_pnl": "571.83"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_snapshot_sha256": "74bd64f21b47f599e5f58e7313a060db3abf3f97cde754a1055e4691db8320aa",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "41432.28",
          "cash_basis": "app_available_cash",
          "cash_difference": "0.00",
          "conservative_risk_nav": "29241.010000",
          "cumulative_pnl": "-757.76",
          "entry_count": 14,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "1.23",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
          "ledger_cash": "41432.28",
          "liquidation_nav": "53703.05",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "301382.XSHE",
              "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
              "remaining_cost": "3869.39",
              "shares": 100
            },
            {
              "code": "603042.XSHG",
              "owned_lot_id": "book-b:2026-09-29:603042.XSHG:BUY",
              "remaining_cost": "7830.78",
              "shares": 500
            }
          ],
          "marked_nav": "53704.28",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-09-29T07:46:17.739000+00:00",
          "opening_capital": "30000.00",
          "owned_market_value": "12272.00",
          "ownership_head_sha256": "42dc690f35cd42e326a311a555a1c61c75a755a91d51229d6ccc3b9d93dec188",
          "realized_pnl": "-1329.59",
          "receipt_sha256": "4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c",
          "remaining_cost": "11700.17",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "reconciled",
          "unrealized_pnl": "571.83"
        },
        "observed_at": "2026-09-29T07:46:17.739000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/4f05fc9f99271615d18abfae3db79c02c35ae82c73e1104b8c3002b3073816b3.json",
          "sha256": "fa036a5795e09cbd63d4f1edbda25fe250d4108ed858b354c0a18ef47ec3b700"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 24,
            "journal_head_sha256": "56a323b8cce27e2e8e441763c20c059cdabc209cc9d0b653bf1f2685a40a0491",
            "ledger_cash": "56357.60",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "1895.56"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "67749.36",
            "broker_snapshot_sha256": "a858c798c58e5e92ebcbd4c515d7acfe0a72a4022bc382016409ba2f5d04da9f",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "56357.60",
            "cash_basis": "app_available_cash",
            "cash_difference": "11391.76",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "30686.397610",
            "cumulative_pnl": null,
            "deployable_cash": "56357.60",
            "entry_count": 24,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "56a323b8cce27e2e8e441763c20c059cdabc209cc9d0b653bf1f2685a40a0491",
            "ledger_cash": "56357.60",
            "liquidation_nav": "56357.60",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "56357.60",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-15T01:36:25.013000+00:00",
            "observed_cash": "67749.36",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "9d1b35ceeba9683eca4a6a1d9b82494c0d39e2dd3c499965a57c527e723b6db8",
            "realized_pnl": "1895.56",
            "receipt_sha256": "f6ca52b91bdbb301c57c413a7e45abceb4853b2cdfb23f587009c8335a8bbe51",
            "remaining_cost": "0.00",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "0.00"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "67749.36",
          "broker_snapshot_sha256": "a858c798c58e5e92ebcbd4c515d7acfe0a72a4022bc382016409ba2f5d04da9f",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "56357.60",
          "cash_basis": "app_available_cash",
          "cash_difference": "11391.76",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "30686.397610",
          "cumulative_pnl": null,
          "deployable_cash": "56357.60",
          "entry_count": 24,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "0.00",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "56a323b8cce27e2e8e441763c20c059cdabc209cc9d0b653bf1f2685a40a0491",
          "ledger_cash": "56357.60",
          "liquidation_nav": "56357.60",
          "logical_account_id": "primary",
          "lots": [],
          "marked_nav": "56357.60",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-15T01:36:25.013000+00:00",
          "observed_cash": "67749.36",
          "opening_capital": "30000.00",
          "owned_market_value": "0.00",
          "ownership_head_sha256": "9d1b35ceeba9683eca4a6a1d9b82494c0d39e2dd3c499965a57c527e723b6db8",
          "realized_pnl": "1895.56",
          "receipt_sha256": "f6ca52b91bdbb301c57c413a7e45abceb4853b2cdfb23f587009c8335a8bbe51",
          "remaining_cost": "0.00",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "0.00"
        },
        "observed_at": "2026-10-15T01:36:25.013000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/5fdccb94720cb27ec705c46da02f69429616cfe21964e2d3ef23bec01f2cd006.json",
          "sha256": "59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 14,
            "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
            "ledger_cash": "41432.28",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-1329.59"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_snapshot_sha256": "74bd64f21b47f599e5f58e7313a060db3abf3f97cde754a1055e4691db8320aa",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "41432.28",
            "cash_basis": "app_available_cash",
            "cash_difference": "0.00",
            "conservative_risk_nav": "29241.010000",
            "cumulative_pnl": "-757.76",
            "entry_count": 14,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "1.23",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
            "ledger_cash": "41432.28",
            "liquidation_nav": "53703.05",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "301382.XSHE",
                "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
                "remaining_cost": "3869.39",
                "shares": 100
              },
              {
                "code": "603042.XSHG",
                "owned_lot_id": "book-b:2026-09-29:603042.XSHG:BUY",
                "remaining_cost": "7830.78",
                "shares": 500
              }
            ],
            "marked_nav": "53704.28",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-09-29T07:46:17.739000+00:00",
            "opening_capital": "30000.00",
            "owned_market_value": "12272.00",
            "ownership_head_sha256": "42dc690f35cd42e326a311a555a1c61c75a755a91d51229d6ccc3b9d93dec188",
            "realized_pnl": "-1329.59",
            "receipt_sha256": "4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c",
            "remaining_cost": "11700.17",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "reconciled",
            "unrealized_pnl": "571.83"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_snapshot_sha256": "74bd64f21b47f599e5f58e7313a060db3abf3f97cde754a1055e4691db8320aa",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "41432.28",
          "cash_basis": "app_available_cash",
          "cash_difference": "0.00",
          "conservative_risk_nav": "29241.010000",
          "cumulative_pnl": "-757.76",
          "entry_count": 14,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "1.23",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "7205e2367218ee5245ff0f14b96954c62c05e64834c14397e09bf54a7268e516",
          "ledger_cash": "41432.28",
          "liquidation_nav": "53703.05",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "301382.XSHE",
              "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
              "remaining_cost": "3869.39",
              "shares": 100
            },
            {
              "code": "603042.XSHG",
              "owned_lot_id": "book-b:2026-09-29:603042.XSHG:BUY",
              "remaining_cost": "7830.78",
              "shares": 500
            }
          ],
          "marked_nav": "53704.28",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-09-29T07:46:17.739000+00:00",
          "opening_capital": "30000.00",
          "owned_market_value": "12272.00",
          "ownership_head_sha256": "42dc690f35cd42e326a311a555a1c61c75a755a91d51229d6ccc3b9d93dec188",
          "realized_pnl": "-1329.59",
          "receipt_sha256": "4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c",
          "remaining_cost": "11700.17",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "reconciled",
          "unrealized_pnl": "571.83"
        },
        "observed_at": "2026-09-29T07:46:17.739000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/67a168e1b12f574245bdd1c67168e6d180be3362c906a32f266004f211516c2b.json",
          "sha256": "0eb20d33bf944f85747c0a98e78226604b1731ef5282a30c441317c980f1bd62"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 27,
            "journal_head_sha256": "c58f73c96e594ebbd26ddea88baf0636fda00d8d243535f4807433dae601103b",
            "ledger_cash": "39924.17",
            "net_contributed_capital": "65845.40",
            "realized_pnl": "1895.56"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "39926.17",
            "broker_snapshot_sha256": "122e47052472dd50941a673121d6fbfa47a15f46d451d52221b22b799e19d6c0",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "39924.17",
            "cash_basis": "app_available_cash",
            "cash_difference": "2.00",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "31231.317876",
            "cumulative_pnl": null,
            "deployable_cash": "39924.17",
            "entry_count": 27,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "2.88",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "c58f73c96e594ebbd26ddea88baf0636fda00d8d243535f4807433dae601103b",
            "ledger_cash": "39924.17",
            "liquidation_nav": "68767.29",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "300107.XSHE",
                "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
                "remaining_cost": "8965.90",
                "shares": 1100
              },
              {
                "code": "601188.XSHG",
                "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
                "remaining_cost": "18850.89",
                "shares": 6100
              }
            ],
            "marked_nav": "68770.17",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-19T01:37:16.622000+00:00",
            "observed_cash": "39926.17",
            "opening_capital": "30000.00",
            "owned_market_value": "28846.00",
            "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
            "realized_pnl": "1895.56",
            "receipt_sha256": "fb3ad10a1501920cc5d25a6631a3dd1db95dc72f8e33aae146cd4660d487331b",
            "remaining_cost": "27816.79",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "1029.21"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "39926.17",
          "broker_snapshot_sha256": "122e47052472dd50941a673121d6fbfa47a15f46d451d52221b22b799e19d6c0",
          "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
          "cash": "39924.17",
          "cash_basis": "app_available_cash",
          "cash_difference": "2.00",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "31231.317876",
          "cumulative_pnl": null,
          "deployable_cash": "39924.17",
          "entry_count": 27,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "2.88",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "c58f73c96e594ebbd26ddea88baf0636fda00d8d243535f4807433dae601103b",
          "ledger_cash": "39924.17",
          "liquidation_nav": "68767.29",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "300107.XSHE",
              "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
              "remaining_cost": "8965.90",
              "shares": 1100
            },
            {
              "code": "601188.XSHG",
              "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
              "remaining_cost": "18850.89",
              "shares": 6100
            }
          ],
          "marked_nav": "68770.17",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-19T01:37:16.622000+00:00",
          "observed_cash": "39926.17",
          "opening_capital": "30000.00",
          "owned_market_value": "28846.00",
          "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
          "realized_pnl": "1895.56",
          "receipt_sha256": "fb3ad10a1501920cc5d25a6631a3dd1db95dc72f8e33aae146cd4660d487331b",
          "remaining_cost": "27816.79",
          "risk_unit_factor": "2.201869619223247326039816083",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "1029.21"
        },
        "observed_at": "2026-10-19T01:37:16.622000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/68ee4b126230e14ff8ea8108454d2c48cd0aeb4730e764d2a485cb505c1c451d.json",
          "sha256": "fb452d42134a56cc5dd975cb1b47818fbe7e648788072935a68a0ace2534d90c"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 36,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "1a9d59f7f8e7846ec331f9eaa86be0fc8b25d2c67a685515bbcf4ac7ae6fdbf9",
            "ledger_cash": "32360.93",
            "net_contributed_capital": "65845.40",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6001953",
                "code": "301052.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6001284",
                "code": "002889.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6000059",
                "code": "002172.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-23"
              }
            ],
            "provisional_realized_pnl": "-1295.25",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "43614.38",
            "broker_snapshot_sha256": "ecd2802b10012a65adce68753868dc566d5d0e8348fb57c59a2f437d34c4fad4",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "32360.93",
            "cash_basis": "app_available_cash",
            "cash_difference": "11253.45",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29557.908167",
            "cumulative_pnl": null,
            "deployable_cash": "32360.93",
            "entry_count": 36,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.27",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "1a9d59f7f8e7846ec331f9eaa86be0fc8b25d2c67a685515bbcf4ac7ae6fdbf9",
            "ledger_cash": "32360.93",
            "liquidation_nav": "65082.66",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "002172.XSHE",
                "owned_lot_id": "book-b:2026-10-23:002172.XSHE:BUY",
                "remaining_cost": "32189.22",
                "shares": 7700
              }
            ],
            "marked_nav": "65085.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-23T07:15:26.462000+00:00",
            "observed_cash": "43614.38",
            "opening_capital": "30000.00",
            "owned_market_value": "32725.00",
            "ownership_head_sha256": "85d427e532265a7e2fb4a204c44824e395d00d53f4e5b2735fafbe8d90a14580",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6001953",
                "code": "301052.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6001284",
                "code": "002889.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6000059",
                "code": "002172.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-23"
              }
            ],
            "provisional_realized_pnl": "-1295.25",
            "provisional_unrealized_pnl": "535.78",
            "realized_pnl": null,
            "receipt_sha256": "ba299fe4a918500478194c2f1c9c48f7a84a054a4f84343113c6e28bb22025a9",
            "remaining_cost": "32189.22",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65085.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-23T07:15:26.462000+00:00",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6001953",
                "code": "301052.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6001284",
                "code": "002889.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-22"
              },
              {
                "broker_order_id": "6000059",
                "code": "002172.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-23"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "ba299fe4a918500478194c2f1c9c48f7a84a054a4f84343113c6e28bb22025a9",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65085.93",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-23T07:15:26.462000+00:00",
          "pending_fee_orders": [
            {
              "broker_order_id": "6000356",
              "code": "603029.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-02"
            },
            {
              "broker_order_id": "6007173",
              "code": "603029.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-04"
            },
            {
              "broker_order_id": "6000331",
              "code": "600059.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-07"
            },
            {
              "broker_order_id": "6003964",
              "code": "600059.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-10"
            },
            {
              "broker_order_id": "6002204",
              "code": "000572.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-16"
            },
            {
              "broker_order_id": "6002446",
              "code": "001209.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002462",
              "code": "002585.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002181",
              "code": "002585.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6005091",
              "code": "000572.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6006397",
              "code": "001209.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-28"
            },
            {
              "broker_order_id": "6000056",
              "code": "301382.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6000057",
              "code": "603042.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6004842",
              "code": "603042.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-30"
            },
            {
              "broker_order_id": "6001466",
              "code": "301382.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-08"
            },
            {
              "broker_order_id": "6000118",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6000131",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6001129",
              "code": "605366.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005170",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005182",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6002860",
              "code": "605366.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-13"
            },
            {
              "broker_order_id": "6000110",
              "code": "002531.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-14"
            },
            {
              "broker_order_id": "6001777",
              "code": "002531.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-15"
            },
            {
              "broker_order_id": "6000056",
              "code": "300107.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6000057",
              "code": "601188.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6005007",
              "code": "300107.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6005018",
              "code": "601188.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6000065",
              "code": "000573.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-20"
            },
            {
              "broker_order_id": "6000066",
              "code": "301052.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6000068",
              "code": "002889.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6003685",
              "code": "000573.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6001953",
              "code": "301052.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-22"
            },
            {
              "broker_order_id": "6001284",
              "code": "002889.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-22"
            },
            {
              "broker_order_id": "6000059",
              "code": "002172.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-23"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "ba299fe4a918500478194c2f1c9c48f7a84a054a4f84343113c6e28bb22025a9",
          "unrealized_pnl": null
        },
        "observed_at": "2026-10-23T07:15:26.462000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/6d157cb173b9029ce4d64aa2d4d8e3d6c3be0934dafe45e2066b0c3d7215da6f.json",
          "sha256": "684934ec6b6cb1172e750536e468c5a9ccd0e3db21da8d38c1211964b33553f9"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 30,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "fc62a8e9f225a5bdb7a1031e003a17f71c3f931116c63c8da6940e66cd4c6d0a",
            "ledger_cash": "34369.96",
            "net_contributed_capital": "65845.40",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              }
            ],
            "provisional_realized_pnl": "2393.94",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "34347.84",
            "broker_snapshot_sha256": "90173023df18a49e5e67cbb755bfeca19ebca62416580cffc672605b1a2e7a38",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "34347.84",
            "cash_basis": "app_available_cash",
            "cash_difference": "-22.12",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "31164.610929",
            "cumulative_pnl": null,
            "deployable_cash": "34347.84",
            "entry_count": 30,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.43",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "fc62a8e9f225a5bdb7a1031e003a17f71c3f931116c63c8da6940e66cd4c6d0a",
            "ledger_cash": "34369.96",
            "liquidation_nav": "68620.41",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "000573.XSHE",
                "owned_lot_id": "book-b:2026-10-20:000573.XSHE:BUY",
                "remaining_cost": "33869.38",
                "shares": 8200
              }
            ],
            "marked_nav": "68623.84",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-20T07:16:23.521000+00:00",
            "observed_cash": "34347.84",
            "opening_capital": "30000.00",
            "owned_market_value": "34276.00",
            "ownership_head_sha256": "e8d9ebd37220d9d4d315e7685bbc8d232392e5c2b72a81cd095b1a73e7d59296",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              }
            ],
            "provisional_realized_pnl": "2393.94",
            "provisional_unrealized_pnl": "406.62",
            "realized_pnl": null,
            "receipt_sha256": "9a259ae401380d958eb213034f88aca6e9b26aa0cd445c881a710a88e916d262",
            "remaining_cost": "33869.38",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "68623.84",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-20T07:16:23.521000+00:00",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "9a259ae401380d958eb213034f88aca6e9b26aa0cd445c881a710a88e916d262",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "68623.84",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-20T07:16:23.521000+00:00",
          "pending_fee_orders": [
            {
              "broker_order_id": "6000356",
              "code": "603029.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-02"
            },
            {
              "broker_order_id": "6007173",
              "code": "603029.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-04"
            },
            {
              "broker_order_id": "6000331",
              "code": "600059.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-07"
            },
            {
              "broker_order_id": "6003964",
              "code": "600059.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-10"
            },
            {
              "broker_order_id": "6002204",
              "code": "000572.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-16"
            },
            {
              "broker_order_id": "6002446",
              "code": "001209.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002462",
              "code": "002585.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002181",
              "code": "002585.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6005091",
              "code": "000572.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6006397",
              "code": "001209.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-28"
            },
            {
              "broker_order_id": "6000056",
              "code": "301382.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6000057",
              "code": "603042.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6004842",
              "code": "603042.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-30"
            },
            {
              "broker_order_id": "6001466",
              "code": "301382.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-08"
            },
            {
              "broker_order_id": "6000118",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6000131",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6001129",
              "code": "605366.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005170",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005182",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6002860",
              "code": "605366.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-13"
            },
            {
              "broker_order_id": "6000110",
              "code": "002531.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-14"
            },
            {
              "broker_order_id": "6001777",
              "code": "002531.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-15"
            },
            {
              "broker_order_id": "6000056",
              "code": "300107.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6000057",
              "code": "601188.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6005007",
              "code": "300107.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6005018",
              "code": "601188.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6000065",
              "code": "000573.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-20"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "9a259ae401380d958eb213034f88aca6e9b26aa0cd445c881a710a88e916d262",
          "unrealized_pnl": null
        },
        "observed_at": "2026-10-20T07:16:23.521000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/6eafa2842aa86eb253533f69921c9250d2c54e686a866d3551893b14ee73442a.json",
          "sha256": "bab487e32dff3c2339c980fd87df5034a7165f31c21981f8a7043a8d2c616af0"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 18,
            "journal_head_sha256": "44859e8a73526de7f0243ee076ddd20a695b978a0e1ccaad916bd3af8eb3ad6b",
            "ledger_cash": "14366.19",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-1156.95"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "14345.26",
            "broker_snapshot_sha256": "99b923f3769b6abe462b08c79ad58ce813b2de5a6a7f8b52fe9ee28bfd3bcf0a",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "14345.26",
            "cash_basis": "app_available_cash",
            "cash_difference": "-20.93",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "31804.380737",
            "cumulative_pnl": null,
            "deployable_cash": "14345.26",
            "entry_count": 18,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "4.41",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "44859e8a73526de7f0243ee076ddd20a695b978a0e1ccaad916bd3af8eb3ad6b",
            "ledger_cash": "14366.19",
            "liquidation_nav": "58410.85",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "000710.XSHE",
                "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000118",
                "remaining_cost": "25872.59",
                "shares": 2600
              },
              {
                "code": "000710.XSHE",
                "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000131",
                "remaining_cost": "13066.31",
                "shares": 1300
              }
            ],
            "marked_nav": "58415.26",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-09T06:45:04.837000+00:00",
            "observed_cash": "14345.26",
            "opening_capital": "30000.00",
            "owned_market_value": "44070.00",
            "ownership_head_sha256": "2a28c536a6a9608757af837a2a58835fbeb1011fd816923c79dcbe29207555a3",
            "realized_pnl": "-1156.95",
            "receipt_sha256": "89ebae558c715fd4e8ffca8c024548d410cd2dd95d5dcbab3db25e682b32e49e",
            "remaining_cost": "38938.90",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "5131.10"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "14345.26",
          "broker_snapshot_sha256": "99b923f3769b6abe462b08c79ad58ce813b2de5a6a7f8b52fe9ee28bfd3bcf0a",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "14345.26",
          "cash_basis": "app_available_cash",
          "cash_difference": "-20.93",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "31804.380737",
          "cumulative_pnl": null,
          "deployable_cash": "14345.26",
          "entry_count": 18,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "4.41",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "44859e8a73526de7f0243ee076ddd20a695b978a0e1ccaad916bd3af8eb3ad6b",
          "ledger_cash": "14366.19",
          "liquidation_nav": "58410.85",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "000710.XSHE",
              "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000118",
              "remaining_cost": "25872.59",
              "shares": 2600
            },
            {
              "code": "000710.XSHE",
              "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000131",
              "remaining_cost": "13066.31",
              "shares": 1300
            }
          ],
          "marked_nav": "58415.26",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-09T06:45:04.837000+00:00",
          "observed_cash": "14345.26",
          "opening_capital": "30000.00",
          "owned_market_value": "44070.00",
          "ownership_head_sha256": "2a28c536a6a9608757af837a2a58835fbeb1011fd816923c79dcbe29207555a3",
          "realized_pnl": "-1156.95",
          "receipt_sha256": "89ebae558c715fd4e8ffca8c024548d410cd2dd95d5dcbab3db25e682b32e49e",
          "remaining_cost": "38938.90",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "5131.10"
        },
        "observed_at": "2026-10-09T06:45:04.837000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/8e58602dce0e24050d28f4157476691f5c89b4477d1075bf54d86cd588ac738b.json",
          "sha256": "2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 15,
            "journal_head_sha256": "486ab177e185e10cc1f80c917fc42b1a3e6cf993defff30d1121a33b94f70d1b",
            "ledger_cash": "49746.44",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-846.21"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "49739.04",
            "broker_snapshot_sha256": "524951dbdf36a5f40a14542ddeed7afc7b3f5fc4204601574448a9bed868e7b1",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "49739.04",
            "cash_basis": "app_available_cash",
            "cash_difference": "-7.40",
            "conservative_risk_nav": "29060.580891",
            "cumulative_pnl": null,
            "entry_count": 15,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.36",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "486ab177e185e10cc1f80c917fc42b1a3e6cf993defff30d1121a33b94f70d1b",
            "ledger_cash": "49746.44",
            "liquidation_nav": "53371.68",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "301382.XSHE",
                "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
                "remaining_cost": "3869.39",
                "shares": 100
              }
            ],
            "marked_nav": "53372.04",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-09-30T07:22:21.651000+00:00",
            "opening_capital": "30000.00",
            "owned_market_value": "3633.00",
            "ownership_head_sha256": "9d1eea6b5541c0cecfbf546ecf18bb09d5afd6be9a54ae6a48e6b0e06b2778be",
            "realized_pnl": "-846.21",
            "receipt_sha256": "ba967385b9931775dfa018cc0ef0ae2873bf950ac44a2946c34ac9895824f12b",
            "remaining_cost": "3869.39",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "-236.39"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "49739.04",
          "broker_snapshot_sha256": "524951dbdf36a5f40a14542ddeed7afc7b3f5fc4204601574448a9bed868e7b1",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "49739.04",
          "cash_basis": "app_available_cash",
          "cash_difference": "-7.40",
          "conservative_risk_nav": "29060.580891",
          "cumulative_pnl": null,
          "entry_count": 15,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "0.36",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "486ab177e185e10cc1f80c917fc42b1a3e6cf993defff30d1121a33b94f70d1b",
          "ledger_cash": "49746.44",
          "liquidation_nav": "53371.68",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "301382.XSHE",
              "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
              "remaining_cost": "3869.39",
              "shares": 100
            }
          ],
          "marked_nav": "53372.04",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-09-30T07:22:21.651000+00:00",
          "opening_capital": "30000.00",
          "owned_market_value": "3633.00",
          "ownership_head_sha256": "9d1eea6b5541c0cecfbf546ecf18bb09d5afd6be9a54ae6a48e6b0e06b2778be",
          "realized_pnl": "-846.21",
          "receipt_sha256": "ba967385b9931775dfa018cc0ef0ae2873bf950ac44a2946c34ac9895824f12b",
          "remaining_cost": "3869.39",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "-236.39"
        },
        "observed_at": "2026-09-30T07:22:21.651000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/9049d8b69c2efd7c1b784f732c2e14fce068708857b77c136831085b1e6d689e.json",
          "sha256": "68225c161befdb1eb84f63b937982dbee9c61bea0dbef8edff14f28eee2669af"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 22,
            "journal_head_sha256": "3e6e6638466827ae539a6e08ea7a14ac4e6842aef2bfe3a539b858347f4376ec",
            "ledger_cash": "59745.10",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "5283.06"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "71153.27",
            "broker_snapshot_sha256": "cee1bfe3b8e5bc9651186528f06fe1b98f6c078347c4c6a13e9ea1ee76cd17a6",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "59745.10",
            "cash_basis": "app_available_cash",
            "cash_difference": "11408.17",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "32530.872391",
            "cumulative_pnl": null,
            "deployable_cash": "59745.10",
            "entry_count": 22,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "3e6e6638466827ae539a6e08ea7a14ac4e6842aef2bfe3a539b858347f4376ec",
            "ledger_cash": "59745.10",
            "liquidation_nav": "59745.10",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "59745.10",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-13T07:16:32.855000+00:00",
            "observed_cash": "71153.27",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "e367d20532a7a2f1df02a1cc2029c89fdc8003d858faf7c90f70a029aa7e7232",
            "realized_pnl": "5283.06",
            "receipt_sha256": "12dc2b6c04535ba0d9ec7e27e8ecfe93c823b72bec612dc7c85229205edce52f",
            "remaining_cost": "0.00",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "0.00"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "71153.27",
          "broker_snapshot_sha256": "cee1bfe3b8e5bc9651186528f06fe1b98f6c078347c4c6a13e9ea1ee76cd17a6",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "59745.10",
          "cash_basis": "app_available_cash",
          "cash_difference": "11408.17",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "32530.872391",
          "cumulative_pnl": null,
          "deployable_cash": "59745.10",
          "entry_count": 22,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "0.00",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "3e6e6638466827ae539a6e08ea7a14ac4e6842aef2bfe3a539b858347f4376ec",
          "ledger_cash": "59745.10",
          "liquidation_nav": "59745.10",
          "logical_account_id": "primary",
          "lots": [],
          "marked_nav": "59745.10",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-13T07:16:32.855000+00:00",
          "observed_cash": "71153.27",
          "opening_capital": "30000.00",
          "owned_market_value": "0.00",
          "ownership_head_sha256": "e367d20532a7a2f1df02a1cc2029c89fdc8003d858faf7c90f70a029aa7e7232",
          "realized_pnl": "5283.06",
          "receipt_sha256": "12dc2b6c04535ba0d9ec7e27e8ecfe93c823b72bec612dc7c85229205edce52f",
          "remaining_cost": "0.00",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "0.00"
        },
        "observed_at": "2026-10-13T07:16:32.855000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/93aef1dfd2aab4d323cc7da9c469dca14ebb4b8198998423cf72fc32f7b7101f.json",
          "sha256": "6e3076b3f1ccd6823684d2624da1e0b192ce5c7c3a013a8e5aef95110a634753"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 16,
            "journal_head_sha256": "4eafe329d94cd0b373d6e99de9404a63ef35f2e87f845a0f9a4e53b45b18b18d",
            "ledger_cash": "53305.09",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-1156.95"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "53291.26",
            "broker_snapshot_sha256": "a35c4da5650d71708a6810a54a20b76a656e2ce5e87d694adb174cf68f51d2d6",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "53291.26",
            "cash_basis": "app_available_cash",
            "cash_difference": "-13.83",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29016.792651",
            "cumulative_pnl": null,
            "deployable_cash": "53291.26",
            "entry_count": 16,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "4eafe329d94cd0b373d6e99de9404a63ef35f2e87f845a0f9a4e53b45b18b18d",
            "ledger_cash": "53305.09",
            "liquidation_nav": "53291.26",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "53291.26",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-08T07:21:52.104000+00:00",
            "observed_cash": "53291.26",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "6a614c9d61afe2a05a400d303a6b5e38eeaa5e6c608dc845f756a09f6cce53d0",
            "realized_pnl": "-1156.95",
            "receipt_sha256": "0b1ae5173a60526228f72f961726d494ae6070b15782ab71e89e1c81b5628b20",
            "remaining_cost": "0.00",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "0.00"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "53291.26",
          "broker_snapshot_sha256": "a35c4da5650d71708a6810a54a20b76a656e2ce5e87d694adb174cf68f51d2d6",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "53291.26",
          "cash_basis": "app_available_cash",
          "cash_difference": "-13.83",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "29016.792651",
          "cumulative_pnl": null,
          "deployable_cash": "53291.26",
          "entry_count": 16,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "0.00",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "4eafe329d94cd0b373d6e99de9404a63ef35f2e87f845a0f9a4e53b45b18b18d",
          "ledger_cash": "53305.09",
          "liquidation_nav": "53291.26",
          "logical_account_id": "primary",
          "lots": [],
          "marked_nav": "53291.26",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-08T07:21:52.104000+00:00",
          "observed_cash": "53291.26",
          "opening_capital": "30000.00",
          "owned_market_value": "0.00",
          "ownership_head_sha256": "6a614c9d61afe2a05a400d303a6b5e38eeaa5e6c608dc845f756a09f6cce53d0",
          "realized_pnl": "-1156.95",
          "receipt_sha256": "0b1ae5173a60526228f72f961726d494ae6070b15782ab71e89e1c81b5628b20",
          "remaining_cost": "0.00",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "0.00"
        },
        "observed_at": "2026-10-08T07:21:52.104000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/a3a2a2b46447f33b1dffbdbbb3f0c195d3804eb22258b018dd54ae7e41af6c02.json",
          "sha256": "bef91a70ed21a02cb97a3c4356011d41aa8d7d5b65d8f6c7e1091d2ee45aaf42"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 27,
            "journal_head_sha256": "c58f73c96e594ebbd26ddea88baf0636fda00d8d243535f4807433dae601103b",
            "ledger_cash": "39924.17",
            "net_contributed_capital": "65845.40",
            "realized_pnl": "1895.56"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "39924.17",
            "broker_snapshot_sha256": "a66a87c43dfbc637d9704b3dcbc71065a03bd2b72293bc6b0f73567dda2bfdaa",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "39924.17",
            "cash_basis": "app_available_cash",
            "cash_difference": "0.00",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "31161.381855",
            "cumulative_pnl": "2770.77",
            "deployable_cash": "39924.17",
            "entry_count": 27,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "2.87",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "c58f73c96e594ebbd26ddea88baf0636fda00d8d243535f4807433dae601103b",
            "ledger_cash": "39924.17",
            "liquidation_nav": "68613.30",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "300107.XSHE",
                "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
                "remaining_cost": "8965.90",
                "shares": 1100
              },
              {
                "code": "601188.XSHG",
                "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
                "remaining_cost": "18850.89",
                "shares": 6100
              }
            ],
            "marked_nav": "68616.17",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-16T08:03:28.059000+00:00",
            "observed_cash": "39924.17",
            "opening_capital": "30000.00",
            "owned_market_value": "28692.00",
            "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
            "realized_pnl": "1895.56",
            "receipt_sha256": "2cc4f5c5c9b47b54112696459add389438d59af70a88e7fb28a06dd06d4863de",
            "remaining_cost": "27816.79",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "reconciled",
            "unrealized_pnl": "875.21"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "39924.17",
          "broker_snapshot_sha256": "a66a87c43dfbc637d9704b3dcbc71065a03bd2b72293bc6b0f73567dda2bfdaa",
          "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
          "cash": "39924.17",
          "cash_basis": "app_available_cash",
          "cash_difference": "0.00",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "31161.381855",
          "cumulative_pnl": "2770.77",
          "deployable_cash": "39924.17",
          "entry_count": 27,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "2.87",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "c58f73c96e594ebbd26ddea88baf0636fda00d8d243535f4807433dae601103b",
          "ledger_cash": "39924.17",
          "liquidation_nav": "68613.30",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "300107.XSHE",
              "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
              "remaining_cost": "8965.90",
              "shares": 1100
            },
            {
              "code": "601188.XSHG",
              "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
              "remaining_cost": "18850.89",
              "shares": 6100
            }
          ],
          "marked_nav": "68616.17",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-16T08:03:28.059000+00:00",
          "observed_cash": "39924.17",
          "opening_capital": "30000.00",
          "owned_market_value": "28692.00",
          "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
          "realized_pnl": "1895.56",
          "receipt_sha256": "2cc4f5c5c9b47b54112696459add389438d59af70a88e7fb28a06dd06d4863de",
          "remaining_cost": "27816.79",
          "risk_unit_factor": "2.201869619223247326039816083",
          "schema_version": "book-b-accounting.v1",
          "status": "reconciled",
          "unrealized_pnl": "875.21"
        },
        "observed_at": "2026-10-16T08:03:28.059000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/c17b2b3981b4fbd47af69ae11c14e817560936a6670a0a156f1e82f6ae409d85.json",
          "sha256": "8428796ec2d2b4301d8b5a553ab8e33bf21263653e66f55aafffd35a3d605cc7"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 26,
            "journal_head_sha256": "54a22b99ac0d104668cbd0818bd87b8b2970a06339078c1a5cca5c310d905315",
            "ledger_cash": "28540.81",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "1895.56"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "39924.17",
            "broker_snapshot_sha256": "0968261ad429ae9ccab37c4f50291ed068be9581427164477158659e0f5e05ff",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "28540.81",
            "cash_basis": "app_available_cash",
            "cash_difference": "11383.36",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "30364.323727",
            "cumulative_pnl": null,
            "deployable_cash": "28540.81",
            "entry_count": 26,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "2.72",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "54a22b99ac0d104668cbd0818bd87b8b2970a06339078c1a5cca5c310d905315",
            "ledger_cash": "28540.81",
            "liquidation_nav": "55766.09",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "300107.XSHE",
                "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
                "remaining_cost": "8965.90",
                "shares": 1100
              },
              {
                "code": "601188.XSHG",
                "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
                "remaining_cost": "18850.89",
                "shares": 6100
              }
            ],
            "marked_nav": "55768.81",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-16T01:31:46.380000+00:00",
            "observed_cash": "39924.17",
            "opening_capital": "30000.00",
            "owned_market_value": "27228.00",
            "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
            "realized_pnl": "1895.56",
            "receipt_sha256": "bdcd0364576c465ce9d6eb56276af1e73648dc8f317a2789e8b39e43e940f183",
            "remaining_cost": "27816.79",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "-588.79"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "39924.17",
          "broker_snapshot_sha256": "0968261ad429ae9ccab37c4f50291ed068be9581427164477158659e0f5e05ff",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "28540.81",
          "cash_basis": "app_available_cash",
          "cash_difference": "11383.36",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "30364.323727",
          "cumulative_pnl": null,
          "deployable_cash": "28540.81",
          "entry_count": 26,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "2.72",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "54a22b99ac0d104668cbd0818bd87b8b2970a06339078c1a5cca5c310d905315",
          "ledger_cash": "28540.81",
          "liquidation_nav": "55766.09",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "300107.XSHE",
              "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
              "remaining_cost": "8965.90",
              "shares": 1100
            },
            {
              "code": "601188.XSHG",
              "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
              "remaining_cost": "18850.89",
              "shares": 6100
            }
          ],
          "marked_nav": "55768.81",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-16T01:31:46.380000+00:00",
          "observed_cash": "39924.17",
          "opening_capital": "30000.00",
          "owned_market_value": "27228.00",
          "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
          "realized_pnl": "1895.56",
          "receipt_sha256": "bdcd0364576c465ce9d6eb56276af1e73648dc8f317a2789e8b39e43e940f183",
          "remaining_cost": "27816.79",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "-588.79"
        },
        "observed_at": "2026-10-16T01:31:46.380000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/c41cf727e4ea97810027c561a03a355118fa2ae5c94a372a4a792e70c8bd5467.json",
          "sha256": "fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 15,
            "journal_head_sha256": "486ab177e185e10cc1f80c917fc42b1a3e6cf993defff30d1121a33b94f70d1b",
            "ledger_cash": "49746.44",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-846.21"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "49739.04",
            "broker_snapshot_sha256": "2f0ab2610d1fe1d0b22b2243ae45986eca6b04bdd8140eeb2b7e083c47764734",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "49739.04",
            "cash_basis": "app_available_cash",
            "cash_difference": "-7.40",
            "conservative_risk_nav": "29074.732300",
            "cumulative_pnl": null,
            "entry_count": 15,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.37",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "486ab177e185e10cc1f80c917fc42b1a3e6cf993defff30d1121a33b94f70d1b",
            "ledger_cash": "49746.44",
            "liquidation_nav": "53397.67",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "301382.XSHE",
                "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
                "remaining_cost": "3869.39",
                "shares": 100
              }
            ],
            "marked_nav": "53398.04",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-09-30T06:51:01.818000+00:00",
            "opening_capital": "30000.00",
            "owned_market_value": "3659.00",
            "ownership_head_sha256": "9d1eea6b5541c0cecfbf546ecf18bb09d5afd6be9a54ae6a48e6b0e06b2778be",
            "realized_pnl": "-846.21",
            "receipt_sha256": "13b35483128080bfba00657ace82c6d9acf90c45bd5b7e6818fa76f85098b5e4",
            "remaining_cost": "3869.39",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "-210.39"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "49739.04",
          "broker_snapshot_sha256": "2f0ab2610d1fe1d0b22b2243ae45986eca6b04bdd8140eeb2b7e083c47764734",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "49739.04",
          "cash_basis": "app_available_cash",
          "cash_difference": "-7.40",
          "conservative_risk_nav": "29074.732300",
          "cumulative_pnl": null,
          "entry_count": 15,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "0.37",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "486ab177e185e10cc1f80c917fc42b1a3e6cf993defff30d1121a33b94f70d1b",
          "ledger_cash": "49746.44",
          "liquidation_nav": "53397.67",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "301382.XSHE",
              "owned_lot_id": "book-b:2026-09-29:301382.XSHE:BUY",
              "remaining_cost": "3869.39",
              "shares": 100
            }
          ],
          "marked_nav": "53398.04",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-09-30T06:51:01.818000+00:00",
          "opening_capital": "30000.00",
          "owned_market_value": "3659.00",
          "ownership_head_sha256": "9d1eea6b5541c0cecfbf546ecf18bb09d5afd6be9a54ae6a48e6b0e06b2778be",
          "realized_pnl": "-846.21",
          "receipt_sha256": "13b35483128080bfba00657ace82c6d9acf90c45bd5b7e6818fa76f85098b5e4",
          "remaining_cost": "3869.39",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "-210.39"
        },
        "observed_at": "2026-09-30T06:51:01.818000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/c8de32a296b2f3506e04a38dc352771851340c649e4393ab38bace8029792445.json",
          "sha256": "803b3c25aeda3474fcd2b2585631326529bdac664bf279208ec1322ab8e79390"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 26,
            "journal_head_sha256": "54a22b99ac0d104668cbd0818bd87b8b2970a06339078c1a5cca5c310d905315",
            "ledger_cash": "28540.81",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "1895.56"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "39924.17",
            "broker_snapshot_sha256": "9045c559807f58de8060a35bf8323b164bfe5f59318ba29d79fcdb77b64dbff9",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "28540.81",
            "cash_basis": "app_available_cash",
            "cash_difference": "11383.36",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "31161.381855",
            "cumulative_pnl": null,
            "deployable_cash": "28540.81",
            "entry_count": 26,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "2.87",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "54a22b99ac0d104668cbd0818bd87b8b2970a06339078c1a5cca5c310d905315",
            "ledger_cash": "28540.81",
            "liquidation_nav": "57229.94",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "300107.XSHE",
                "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
                "remaining_cost": "8965.90",
                "shares": 1100
              },
              {
                "code": "601188.XSHG",
                "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
                "remaining_cost": "18850.89",
                "shares": 6100
              }
            ],
            "marked_nav": "57232.81",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-16T07:15:54.737000+00:00",
            "observed_cash": "39924.17",
            "opening_capital": "30000.00",
            "owned_market_value": "28692.00",
            "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
            "realized_pnl": "1895.56",
            "receipt_sha256": "17e22b64288e46de61dbd0c9db90375d7de8232c8640cfbecdefd299bbc12001",
            "remaining_cost": "27816.79",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "875.21"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "39924.17",
          "broker_snapshot_sha256": "9045c559807f58de8060a35bf8323b164bfe5f59318ba29d79fcdb77b64dbff9",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "28540.81",
          "cash_basis": "app_available_cash",
          "cash_difference": "11383.36",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "31161.381855",
          "cumulative_pnl": null,
          "deployable_cash": "28540.81",
          "entry_count": 26,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "2.87",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "54a22b99ac0d104668cbd0818bd87b8b2970a06339078c1a5cca5c310d905315",
          "ledger_cash": "28540.81",
          "liquidation_nav": "57229.94",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "300107.XSHE",
              "owned_lot_id": "book-b:2026-10-16:300107.XSHE:BUY",
              "remaining_cost": "8965.90",
              "shares": 1100
            },
            {
              "code": "601188.XSHG",
              "owned_lot_id": "book-b:2026-10-16:601188.XSHG:BUY",
              "remaining_cost": "18850.89",
              "shares": 6100
            }
          ],
          "marked_nav": "57232.81",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-16T07:15:54.737000+00:00",
          "observed_cash": "39924.17",
          "opening_capital": "30000.00",
          "owned_market_value": "28692.00",
          "ownership_head_sha256": "cf5790750c16bdc0aa8976d31185360c6c978dae6a3756ba39ea4d539d3a8a7b",
          "realized_pnl": "1895.56",
          "receipt_sha256": "17e22b64288e46de61dbd0c9db90375d7de8232c8640cfbecdefd299bbc12001",
          "remaining_cost": "27816.79",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "875.21"
        },
        "observed_at": "2026-10-16T07:15:54.737000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/cc642c97ff781a8cced7d00f31530e6c9c263088ff32e509031dfc62a6485be3.json",
          "sha256": "e2b1733a766cd6cd11b86a2b3289608d14db28f776f5fd69ea8aafec2a4ea6ac"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 29,
            "journal_head_sha256": "0eddd59d3051f1b4f18e558a74339648ca61db6de4e097f576e283292e0d7230",
            "ledger_cash": "68239.34",
            "net_contributed_capital": "65845.40",
            "realized_pnl": "2393.94"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "68217.82",
            "broker_snapshot_sha256": "534bd9c9ec75a1aaf3c2039aa64ac5d632c9a102b5feacb7d37c732291976c4a",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "68217.82",
            "cash_basis": "app_available_cash",
            "cash_difference": "-21.52",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "30981.770857",
            "cumulative_pnl": null,
            "deployable_cash": "68217.82",
            "entry_count": 29,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "0eddd59d3051f1b4f18e558a74339648ca61db6de4e097f576e283292e0d7230",
            "ledger_cash": "68239.34",
            "liquidation_nav": "68217.82",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "68217.82",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-19T07:16:16.247000+00:00",
            "observed_cash": "68217.82",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "92d18587aa76d0e25ecba0e698ea16a5b0c184a155667d9065609e9faffebdbe",
            "realized_pnl": "2393.94",
            "receipt_sha256": "2fbb4bc6267208658e67d320916de09fb1e14e6cf04a2313d19a2baec3e5b438",
            "remaining_cost": "0.00",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "0.00"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "68217.82",
          "broker_snapshot_sha256": "534bd9c9ec75a1aaf3c2039aa64ac5d632c9a102b5feacb7d37c732291976c4a",
          "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
          "cash": "68217.82",
          "cash_basis": "app_available_cash",
          "cash_difference": "-21.52",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "30981.770857",
          "cumulative_pnl": null,
          "deployable_cash": "68217.82",
          "entry_count": 29,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "0.00",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "0eddd59d3051f1b4f18e558a74339648ca61db6de4e097f576e283292e0d7230",
          "ledger_cash": "68239.34",
          "liquidation_nav": "68217.82",
          "logical_account_id": "primary",
          "lots": [],
          "marked_nav": "68217.82",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-19T07:16:16.247000+00:00",
          "observed_cash": "68217.82",
          "opening_capital": "30000.00",
          "owned_market_value": "0.00",
          "ownership_head_sha256": "92d18587aa76d0e25ecba0e698ea16a5b0c184a155667d9065609e9faffebdbe",
          "realized_pnl": "2393.94",
          "receipt_sha256": "2fbb4bc6267208658e67d320916de09fb1e14e6cf04a2313d19a2baec3e5b438",
          "remaining_cost": "0.00",
          "risk_unit_factor": "2.201869619223247326039816083",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "0.00"
        },
        "observed_at": "2026-10-19T07:16:16.247000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/e7c5a5678234879cbad0ad4448221c0a59056e9e683c7540cc3337de386fb3f4.json",
          "sha256": "e7dcf98d44bb888889dc729fb9c39bbc423e00a88d2b877c06d0766ed10a3360"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 18,
            "journal_head_sha256": "44859e8a73526de7f0243ee076ddd20a695b978a0e1ccaad916bd3af8eb3ad6b",
            "ledger_cash": "14366.19",
            "net_contributed_capital": "54462.04",
            "realized_pnl": "-1156.95"
          },
          "schema_version": "book-b-statement.v1",
          "valuation": {
            "book": "B",
            "broker_available_cash": "14345.26",
            "broker_snapshot_sha256": "44c9eadd25ac605276b07f4651ec07f09fe3660cf5247c27870cd52b3733b669",
            "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
            "cash": "14345.26",
            "cash_basis": "app_available_cash",
            "cash_difference": "-20.93",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29044.071820",
            "cumulative_pnl": null,
            "deployable_cash": "14345.26",
            "entry_count": 18,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.90",
            "fee_basis": "estimated_plan_rate",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "44859e8a73526de7f0243ee076ddd20a695b978a0e1ccaad916bd3af8eb3ad6b",
            "ledger_cash": "14366.19",
            "liquidation_nav": "53341.36",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "000710.XSHE",
                "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000118",
                "remaining_cost": "25872.59",
                "shares": 2600
              },
              {
                "code": "000710.XSHE",
                "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000131",
                "remaining_cost": "13066.31",
                "shares": 1300
              }
            ],
            "marked_nav": "53345.26",
            "net_contributed_capital": "54462.04",
            "observed_at": "2026-10-09T01:45:43.626000+00:00",
            "observed_cash": "14345.26",
            "opening_capital": "30000.00",
            "owned_market_value": "39000.00",
            "ownership_head_sha256": "2a28c536a6a9608757af837a2a58835fbeb1011fd816923c79dcbe29207555a3",
            "realized_pnl": "-1156.95",
            "receipt_sha256": "aeef103d9971f2c7778f886e07e78fdcf8fc1b0812a1ca1bc44768557573a78f",
            "remaining_cost": "38938.90",
            "risk_unit_factor": "1.836566178801621421421489887",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": "61.10"
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "book": "B",
          "broker_available_cash": "14345.26",
          "broker_snapshot_sha256": "44c9eadd25ac605276b07f4651ec07f09fe3660cf5247c27870cd52b3733b669",
          "capital_flow_head_sha256": "059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453",
          "cash": "14345.26",
          "cash_basis": "app_available_cash",
          "cash_difference": "-20.93",
          "cash_discrepancy_limit": "10.00",
          "cash_integrity_proven": false,
          "conservative_risk_nav": "29044.071820",
          "cumulative_pnl": null,
          "deployable_cash": "14345.26",
          "entry_count": 18,
          "environment": "app_server_simulation",
          "estimated_exit_fee": "3.90",
          "fee_basis": "estimated_plan_rate",
          "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
          "journal_head_sha256": "44859e8a73526de7f0243ee076ddd20a695b978a0e1ccaad916bd3af8eb3ad6b",
          "ledger_cash": "14366.19",
          "liquidation_nav": "53341.36",
          "logical_account_id": "primary",
          "lots": [
            {
              "code": "000710.XSHE",
              "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000118",
              "remaining_cost": "25872.59",
              "shares": 2600
            },
            {
              "code": "000710.XSHE",
              "owned_lot_id": "book-b:2026-10-09:000710.XSHE:BUY:user-assisted-6000131",
              "remaining_cost": "13066.31",
              "shares": 1300
            }
          ],
          "marked_nav": "53345.26",
          "net_contributed_capital": "54462.04",
          "observed_at": "2026-10-09T01:45:43.626000+00:00",
          "observed_cash": "14345.26",
          "opening_capital": "30000.00",
          "owned_market_value": "39000.00",
          "ownership_head_sha256": "2a28c536a6a9608757af837a2a58835fbeb1011fd816923c79dcbe29207555a3",
          "realized_pnl": "-1156.95",
          "receipt_sha256": "aeef103d9971f2c7778f886e07e78fdcf8fc1b0812a1ca1bc44768557573a78f",
          "remaining_cost": "38938.90",
          "risk_unit_factor": "1.836566178801621421421489887",
          "schema_version": "book-b-accounting.v1",
          "status": "cash_reconciliation_required",
          "unrealized_pnl": "61.10"
        },
        "observed_at": "2026-10-09T01:45:43.626000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/f17924bf2ab7daeafc441e55e73387816999a3b5e07656831078b601fc63850f.json",
          "sha256": "7d01fda770c85501b36afac07431a7f2aa32c5a375f40982e84138913de184a6"
        },
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 33,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "6b2ca5650c30470359b3ab3e11040f3efe7dac106dd445c963f5837aa9e3d503",
            "ledger_cash": "33811.23",
            "net_contributed_capital": "65845.40",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              }
            ],
            "provisional_realized_pnl": "1895.23",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "45086.73",
            "broker_snapshot_sha256": "efe001198ac2e66019056907f461822db20d4ea0ee11a2da415bc013e3383449",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "33811.23",
            "cash_basis": "app_available_cash",
            "cash_difference": "11275.50",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "30605.295342",
            "cumulative_pnl": null,
            "deployable_cash": "33811.23",
            "entry_count": 33,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.36",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "6b2ca5650c30470359b3ab3e11040f3efe7dac106dd445c963f5837aa9e3d503",
            "ledger_cash": "33811.23",
            "liquidation_nav": "67388.87",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "301052.XSHE",
                "owned_lot_id": "book-b:2026-10-21:301052.XSHE:BUY",
                "remaining_cost": "16491.65",
                "shares": 500
              },
              {
                "code": "002889.XSHE",
                "owned_lot_id": "book-b:2026-10-21:002889.XSHE:BUY",
                "remaining_cost": "17437.75",
                "shares": 1200
              }
            ],
            "marked_nav": "67392.23",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-21T07:16:31.258000+00:00",
            "observed_cash": "45086.73",
            "opening_capital": "30000.00",
            "owned_market_value": "33581.00",
            "ownership_head_sha256": "01483dffb656f3a6a1b65aa8286040b7024949cbde3d1a0d46aed526c75608c1",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              }
            ],
            "provisional_realized_pnl": "1895.23",
            "provisional_unrealized_pnl": "-348.40",
            "realized_pnl": null,
            "receipt_sha256": "7f87747683ce73c9a0838c2ec733226f64771ccb0bcf493fc6f94320baaa9fbf",
            "remaining_cost": "33929.40",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "67392.23",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-21T07:16:31.258000+00:00",
            "pending_fee_orders": [
              {
                "broker_order_id": "6000356",
                "code": "603029.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-02"
              },
              {
                "broker_order_id": "6007173",
                "code": "603029.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-04"
              },
              {
                "broker_order_id": "6000331",
                "code": "600059.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-07"
              },
              {
                "broker_order_id": "6003964",
                "code": "600059.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-10"
              },
              {
                "broker_order_id": "6002204",
                "code": "000572.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-16"
              },
              {
                "broker_order_id": "6002446",
                "code": "001209.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002462",
                "code": "002585.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-17"
              },
              {
                "broker_order_id": "6002181",
                "code": "002585.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6005091",
                "code": "000572.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-23"
              },
              {
                "broker_order_id": "6006397",
                "code": "001209.XSHE",
                "side": "SELL",
                "trade_date": "2026-09-28"
              },
              {
                "broker_order_id": "6000056",
                "code": "301382.XSHE",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6000057",
                "code": "603042.XSHG",
                "side": "BUY",
                "trade_date": "2026-09-29"
              },
              {
                "broker_order_id": "6004842",
                "code": "603042.XSHG",
                "side": "SELL",
                "trade_date": "2026-09-30"
              },
              {
                "broker_order_id": "6001466",
                "code": "301382.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-08"
              },
              {
                "broker_order_id": "6000118",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6000131",
                "code": "000710.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-09"
              },
              {
                "broker_order_id": "6001129",
                "code": "605366.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005170",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6005182",
                "code": "000710.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-12"
              },
              {
                "broker_order_id": "6002860",
                "code": "605366.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-13"
              },
              {
                "broker_order_id": "6000110",
                "code": "002531.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-14"
              },
              {
                "broker_order_id": "6001777",
                "code": "002531.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-15"
              },
              {
                "broker_order_id": "6000056",
                "code": "300107.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6000057",
                "code": "601188.XSHG",
                "side": "BUY",
                "trade_date": "2026-10-16"
              },
              {
                "broker_order_id": "6005007",
                "code": "300107.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6005018",
                "code": "601188.XSHG",
                "side": "SELL",
                "trade_date": "2026-10-19"
              },
              {
                "broker_order_id": "6000065",
                "code": "000573.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-20"
              },
              {
                "broker_order_id": "6000066",
                "code": "301052.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6000068",
                "code": "002889.XSHE",
                "side": "BUY",
                "trade_date": "2026-10-21"
              },
              {
                "broker_order_id": "6003685",
                "code": "000573.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-21"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "7f87747683ce73c9a0838c2ec733226f64771ccb0bcf493fc6f94320baaa9fbf",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "67392.23",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-21T07:16:31.258000+00:00",
          "pending_fee_orders": [
            {
              "broker_order_id": "6000356",
              "code": "603029.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-02"
            },
            {
              "broker_order_id": "6007173",
              "code": "603029.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-04"
            },
            {
              "broker_order_id": "6000331",
              "code": "600059.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-07"
            },
            {
              "broker_order_id": "6003964",
              "code": "600059.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-10"
            },
            {
              "broker_order_id": "6002204",
              "code": "000572.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-16"
            },
            {
              "broker_order_id": "6002446",
              "code": "001209.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002462",
              "code": "002585.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-17"
            },
            {
              "broker_order_id": "6002181",
              "code": "002585.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6005091",
              "code": "000572.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-23"
            },
            {
              "broker_order_id": "6006397",
              "code": "001209.XSHE",
              "side": "SELL",
              "trade_date": "2026-09-28"
            },
            {
              "broker_order_id": "6000056",
              "code": "301382.XSHE",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6000057",
              "code": "603042.XSHG",
              "side": "BUY",
              "trade_date": "2026-09-29"
            },
            {
              "broker_order_id": "6004842",
              "code": "603042.XSHG",
              "side": "SELL",
              "trade_date": "2026-09-30"
            },
            {
              "broker_order_id": "6001466",
              "code": "301382.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-08"
            },
            {
              "broker_order_id": "6000118",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6000131",
              "code": "000710.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-09"
            },
            {
              "broker_order_id": "6001129",
              "code": "605366.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005170",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6005182",
              "code": "000710.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-12"
            },
            {
              "broker_order_id": "6002860",
              "code": "605366.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-13"
            },
            {
              "broker_order_id": "6000110",
              "code": "002531.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-14"
            },
            {
              "broker_order_id": "6001777",
              "code": "002531.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-15"
            },
            {
              "broker_order_id": "6000056",
              "code": "300107.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6000057",
              "code": "601188.XSHG",
              "side": "BUY",
              "trade_date": "2026-10-16"
            },
            {
              "broker_order_id": "6005007",
              "code": "300107.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6005018",
              "code": "601188.XSHG",
              "side": "SELL",
              "trade_date": "2026-10-19"
            },
            {
              "broker_order_id": "6000065",
              "code": "000573.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-20"
            },
            {
              "broker_order_id": "6000066",
              "code": "301052.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6000068",
              "code": "002889.XSHE",
              "side": "BUY",
              "trade_date": "2026-10-21"
            },
            {
              "broker_order_id": "6003685",
              "code": "000573.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-21"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "7f87747683ce73c9a0838c2ec733226f64771ccb0bcf493fc6f94320baaa9fbf",
          "unrealized_pnl": null
        },
        "observed_at": "2026-10-21T07:16:31.258000+00:00",
        "valuation_status": "dated_observation",
        "profit_attribution": "not_established",
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ]
      }
    ],
    "production_observations": {
      "as_of": "2026-10-23",
      "sources": [
        {
          "path": "output/live/positions.jsonl",
          "status": "captured",
          "sha256": "f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997",
          "parsed_records": 240,
          "latest_record_date": "2026-10-23"
        },
        {
          "path": "output/live/paper_trades.jsonl",
          "status": "captured",
          "sha256": "c2ec1eca329b4942aee258b383ff31480bf17b2cc4b8f7a87165d491f82e253a",
          "parsed_records": 475,
          "latest_record_date": "2026-10-23"
        }
      ],
      "latest_record_date": "2026-10-23",
      "staleness_calendar_days": 0,
      "counts": {
        "unknown": 17,
        "valid": 223,
        "bad": 0,
        "immature": 5,
        "closed": 218,
        "unknown_trades": 17,
        "future": 0
      },
      "books": {
        "A": {
          "valid_lots": 98,
          "closed_lots": 97,
          "open_lots": 1,
          "entry_fee": 219.89,
          "exit_fee": 216.08,
          "closed_cash_net_change": 30244.74,
          "mean_closed_lot_return_pct": 0.9332921748382244,
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
        },
        "B": {
          "valid_lots": 113,
          "closed_lots": 112,
          "open_lots": 1,
          "entry_fee": 258.18,
          "exit_fee": 255.49,
          "closed_cash_net_change": 40710.58,
          "mean_closed_lot_return_pct": 0.984898966314975,
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
        },
        "T": {
          "valid_lots": 12,
          "closed_lots": 9,
          "open_lots": 3,
          "entry_fee": 10.69,
          "exit_fee": 7.68,
          "closed_cash_net_change": -1197.43,
          "mean_closed_lot_return_pct": -1.8785399826946807,
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
        }
      },
      "windows": {
        "1w": {
          "start": "2026-10-17",
          "end": "2026-10-23",
          "valid_lots": 7,
          "status": "observed",
          "latest_data_before_window": false,
          "books": {
            "A": {
              "valid_lots": 3,
              "closed_lots": 2,
              "open_lots": 1,
              "entry_fee": 17.74,
              "exit_fee": 10.38,
              "closed_cash_net_change": -4553.06,
              "mean_closed_lot_return_pct": -5.935824364365736,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            },
            "B": {
              "valid_lots": 4,
              "closed_lots": 3,
              "open_lots": 1,
              "entry_fee": 21.2,
              "exit_fee": 13.62,
              "closed_cash_net_change": -6716.87,
              "mean_closed_lot_return_pct": -6.094502277762929,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            },
            "T": {
              "valid_lots": 0,
              "closed_lots": 0,
              "open_lots": 0,
              "entry_fee": null,
              "exit_fee": null,
              "closed_cash_net_change": null,
              "mean_closed_lot_return_pct": null,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            }
          },
          "paired_exit_comparison": {
            "eligible": 2,
            "open": 1,
            "unmatched": 1,
            "entry_mismatch": 0,
            "censored": 1,
            "unknown_lots": 0,
            "excluded": 2,
            "mean_b_minus_a_pp": 1.530735977979471,
            "pairs": [
              {
                "code": "000573.XSHE",
                "entry_date": "2026-10-20",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "301052.XSHE",
                "entry_date": "2026-10-21",
                "b_minus_a_pp": 3.061471955958942
              }
            ],
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias"
          }
        },
        "4w": {
          "start": "2026-09-26",
          "end": "2026-10-23",
          "valid_lots": 28,
          "status": "observed",
          "latest_data_before_window": false,
          "books": {
            "A": {
              "valid_lots": 11,
              "closed_lots": 10,
              "open_lots": 1,
              "entry_fee": 51.45,
              "exit_fee": 44.56,
              "closed_cash_net_change": -87.79,
              "mean_closed_lot_return_pct": 0.23771587151785303,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            },
            "B": {
              "valid_lots": 14,
              "closed_lots": 13,
              "open_lots": 1,
              "entry_fee": 65.76,
              "exit_fee": 59.17,
              "closed_cash_net_change": 2865.68,
              "mean_closed_lot_return_pct": 0.22617947999791946,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            },
            "T": {
              "valid_lots": 3,
              "closed_lots": 0,
              "open_lots": 3,
              "entry_fee": 2.88,
              "exit_fee": null,
              "closed_cash_net_change": null,
              "mean_closed_lot_return_pct": null,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            }
          },
          "paired_exit_comparison": {
            "eligible": 10,
            "open": 1,
            "unmatched": 3,
            "entry_mismatch": 0,
            "censored": 1,
            "unknown_lots": 0,
            "excluded": 4,
            "mean_b_minus_a_pp": 1.0236436823680557,
            "pairs": [
              {
                "code": "000573.XSHE",
                "entry_date": "2026-10-20",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "000710.XSHE",
                "entry_date": "2026-10-09",
                "b_minus_a_pp": -0.19877187531375462
              },
              {
                "code": "002531.XSHE",
                "entry_date": "2026-10-14",
                "b_minus_a_pp": 3.4268597204119984
              },
              {
                "code": "300107.XSHE",
                "entry_date": "2026-10-16",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "301052.XSHE",
                "entry_date": "2026-10-21",
                "b_minus_a_pp": 3.061471955958942
              },
              {
                "code": "301560.XSHE",
                "entry_date": "2026-09-28",
                "b_minus_a_pp": 14.918268863877424
              },
              {
                "code": "600371.XSHG",
                "entry_date": "2026-09-28",
                "b_minus_a_pp": 0.06620993154995071
              },
              {
                "code": "601188.XSHG",
                "entry_date": "2026-10-16",
                "b_minus_a_pp": 0.6487960736632882
              },
              {
                "code": "603042.XSHG",
                "entry_date": "2026-09-29",
                "b_minus_a_pp": -0.12871204274502723
              },
              {
                "code": "605366.XSHG",
                "entry_date": "2026-10-12",
                "b_minus_a_pp": -11.557685803722265
              }
            ],
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias"
          }
        },
        "12w": {
          "start": "2026-08-01",
          "end": "2026-10-23",
          "valid_lots": 72,
          "status": "observed",
          "latest_data_before_window": false,
          "books": {
            "A": {
              "valid_lots": 31,
              "closed_lots": 30,
              "open_lots": 1,
              "entry_fee": 118.41,
              "exit_fee": 114.06,
              "closed_cash_net_change": 25178.41,
              "mean_closed_lot_return_pct": 2.575039257868202,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            },
            "B": {
              "valid_lots": 37,
              "closed_lots": 36,
              "open_lots": 1,
              "entry_fee": 146.78,
              "exit_fee": 143.1,
              "closed_cash_net_change": 31605.34,
              "mean_closed_lot_return_pct": 2.204483226451007,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            },
            "T": {
              "valid_lots": 4,
              "closed_lots": 1,
              "open_lots": 3,
              "entry_fee": 3.56,
              "exit_fee": 0.66,
              "closed_cash_net_change": -186.53,
              "mean_closed_lot_return_pct": -2.7488000801665815,
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV"
            }
          },
          "paired_exit_comparison": {
            "eligible": 30,
            "open": 1,
            "unmatched": 6,
            "entry_mismatch": 0,
            "censored": 1,
            "unknown_lots": 0,
            "excluded": 7,
            "mean_b_minus_a_pp": 0.5999206427038246,
            "pairs": [
              {
                "code": "000523.XSHE",
                "entry_date": "2026-08-26",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "000572.XSHE",
                "entry_date": "2026-09-16",
                "b_minus_a_pp": 0.24807928612712257
              },
              {
                "code": "000573.XSHE",
                "entry_date": "2026-10-20",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "000710.XSHE",
                "entry_date": "2026-10-09",
                "b_minus_a_pp": -0.19877187531375462
              },
              {
                "code": "001209.XSHE",
                "entry_date": "2026-09-17",
                "b_minus_a_pp": -1.82404613140212
              },
              {
                "code": "001299.XSHE",
                "entry_date": "2026-09-11",
                "b_minus_a_pp": 0.08242960162084592
              },
              {
                "code": "001309.XSHE",
                "entry_date": "2026-08-28",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "002212.XSHE",
                "entry_date": "2026-09-17",
                "b_minus_a_pp": -0.14696094252215317
              },
              {
                "code": "002229.XSHE",
                "entry_date": "2026-08-14",
                "b_minus_a_pp": -8.602677385065107
              },
              {
                "code": "002349.XSHE",
                "entry_date": "2026-09-01",
                "b_minus_a_pp": -0.26665064535341554
              },
              {
                "code": "002396.XSHE",
                "entry_date": "2026-08-14",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "002522.XSHE",
                "entry_date": "2026-09-16",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "002531.XSHE",
                "entry_date": "2026-10-14",
                "b_minus_a_pp": 3.4268597204119984
              },
              {
                "code": "002580.XSHE",
                "entry_date": "2026-08-11",
                "b_minus_a_pp": 0.04635166078000575
              },
              {
                "code": "002742.XSHE",
                "entry_date": "2026-08-25",
                "b_minus_a_pp": 12.996525663526631
              },
              {
                "code": "002762.XSHE",
                "entry_date": "2026-08-11",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "002792.XSHE",
                "entry_date": "2026-08-11",
                "b_minus_a_pp": 4.609103507726937
              },
              {
                "code": "002963.XSHE",
                "entry_date": "2026-08-26",
                "b_minus_a_pp": 3.407598948203156
              },
              {
                "code": "300107.XSHE",
                "entry_date": "2026-10-16",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "300426.XSHE",
                "entry_date": "2026-08-14",
                "b_minus_a_pp": 0.0
              },
              {
                "code": "301052.XSHE",
                "entry_date": "2026-10-21",
                "b_minus_a_pp": 3.061471955958942
              },
              {
                "code": "301520.XSHE",
                "entry_date": "2026-09-21",
                "b_minus_a_pp": 0.3539085728812919
              },
              {
                "code": "301560.XSHE",
                "entry_date": "2026-09-28",
                "b_minus_a_pp": 14.918268863877424
              },
              {
                "code": "600059.XSHG",
                "entry_date": "2026-09-07",
                "b_minus_a_pp": -0.10687346784138903
              },
              {
                "code": "600371.XSHG",
                "entry_date": "2026-09-28",
                "b_minus_a_pp": 0.06620993154995071
              },
              {
                "code": "600712.XSHG",
                "entry_date": "2026-08-06",
                "b_minus_a_pp": 0.5426480408438968
              },
              {
                "code": "601188.XSHG",
                "entry_date": "2026-10-16",
                "b_minus_a_pp": 0.6487960736632882
              },
              {
                "code": "603042.XSHG",
                "entry_date": "2026-09-29",
                "b_minus_a_pp": -0.12871204274502723
              },
              {
                "code": "603106.XSHG",
                "entry_date": "2026-08-06",
                "b_minus_a_pp": -3.578254252091518
              },
              {
                "code": "605366.XSHG",
                "entry_date": "2026-10-12",
                "b_minus_a_pp": -11.557685803722265
              }
            ],
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias"
          }
        }
      },
      "paired_exit_comparison": {
        "eligible": 58,
        "open": 1,
        "unmatched": 17,
        "entry_mismatch": 38,
        "censored": 1,
        "unknown_lots": 17,
        "excluded": 56,
        "mean_b_minus_a_pp": 0.670685079175,
        "pairs": [
          {
            "code": "000523.XSHE",
            "entry_date": "2026-08-26",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "000572.XSHE",
            "entry_date": "2026-09-16",
            "b_minus_a_pp": 0.24807928612712257
          },
          {
            "code": "000573.XSHE",
            "entry_date": "2026-10-20",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "000710.XSHE",
            "entry_date": "2026-10-09",
            "b_minus_a_pp": -0.19877187531375462
          },
          {
            "code": "000938.XSHE",
            "entry_date": "2026-07-22",
            "b_minus_a_pp": -1.5509156635710475
          },
          {
            "code": "001209.XSHE",
            "entry_date": "2026-09-17",
            "b_minus_a_pp": -1.82404613140212
          },
          {
            "code": "001299.XSHE",
            "entry_date": "2026-09-11",
            "b_minus_a_pp": 0.08242960162084592
          },
          {
            "code": "001309.XSHE",
            "entry_date": "2026-08-28",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "002137.XSHE",
            "entry_date": "2026-07-08",
            "b_minus_a_pp": -0.5123225573939615
          },
          {
            "code": "002173.XSHE",
            "entry_date": "2026-07-24",
            "b_minus_a_pp": 1.751625371332378
          },
          {
            "code": "002173.XSHE",
            "entry_date": "2026-07-30",
            "b_minus_a_pp": -1.2365183278445877
          },
          {
            "code": "002208.XSHE",
            "entry_date": "2026-07-02",
            "b_minus_a_pp": -0.9844584286803967
          },
          {
            "code": "002212.XSHE",
            "entry_date": "2026-09-17",
            "b_minus_a_pp": -0.14696094252215317
          },
          {
            "code": "002229.XSHE",
            "entry_date": "2026-08-14",
            "b_minus_a_pp": -8.602677385065107
          },
          {
            "code": "002279.XSHE",
            "entry_date": "2026-07-30",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "002326.XSHE",
            "entry_date": "2026-07-03",
            "b_minus_a_pp": 5.75942828777017
          },
          {
            "code": "002349.XSHE",
            "entry_date": "2026-09-01",
            "b_minus_a_pp": -0.26665064535341554
          },
          {
            "code": "002396.XSHE",
            "entry_date": "2026-08-14",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "002458.XSHE",
            "entry_date": "2026-07-06",
            "b_minus_a_pp": -0.22109443588215297
          },
          {
            "code": "002522.XSHE",
            "entry_date": "2026-09-16",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "002531.XSHE",
            "entry_date": "2026-10-14",
            "b_minus_a_pp": 3.4268597204119984
          },
          {
            "code": "002558.XSHE",
            "entry_date": "2026-07-16",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "002579.XSHE",
            "entry_date": "2026-06-29",
            "b_minus_a_pp": -5.516801801150414
          },
          {
            "code": "002580.XSHE",
            "entry_date": "2026-08-11",
            "b_minus_a_pp": 0.04635166078000575
          },
          {
            "code": "002742.XSHE",
            "entry_date": "2026-08-25",
            "b_minus_a_pp": 12.996525663526631
          },
          {
            "code": "002762.XSHE",
            "entry_date": "2026-08-11",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "002792.XSHE",
            "entry_date": "2026-08-11",
            "b_minus_a_pp": 4.609103507726937
          },
          {
            "code": "002826.XSHE",
            "entry_date": "2026-07-06",
            "b_minus_a_pp": 0.05590136762695899
          },
          {
            "code": "002963.XSHE",
            "entry_date": "2026-08-26",
            "b_minus_a_pp": 3.407598948203156
          },
          {
            "code": "300107.XSHE",
            "entry_date": "2026-10-16",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "300214.XSHE",
            "entry_date": "2026-07-27",
            "b_minus_a_pp": 1.1277474837153636
          },
          {
            "code": "300331.XSHE",
            "entry_date": "2026-07-29",
            "b_minus_a_pp": 2.6429541602216338
          },
          {
            "code": "300426.XSHE",
            "entry_date": "2026-08-14",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "300534.XSHE",
            "entry_date": "2026-07-22",
            "b_minus_a_pp": -0.07686636781954571
          },
          {
            "code": "300577.XSHE",
            "entry_date": "2026-07-21",
            "b_minus_a_pp": 6.963784496980651
          },
          {
            "code": "300651.XSHE",
            "entry_date": "2026-07-03",
            "b_minus_a_pp": -0.10429660248815681
          },
          {
            "code": "300853.XSHE",
            "entry_date": "2026-07-03",
            "b_minus_a_pp": 9.868310587867784
          },
          {
            "code": "300937.XSHE",
            "entry_date": "2026-07-16",
            "b_minus_a_pp": 1.8019177668840358
          },
          {
            "code": "300980.XSHE",
            "entry_date": "2026-07-02",
            "b_minus_a_pp": -0.0612596203128733
          },
          {
            "code": "301052.XSHE",
            "entry_date": "2026-10-21",
            "b_minus_a_pp": 3.061471955958942
          },
          {
            "code": "301379.XSHE",
            "entry_date": "2026-07-06",
            "b_minus_a_pp": 0.6301697126370086
          },
          {
            "code": "301520.XSHE",
            "entry_date": "2026-09-21",
            "b_minus_a_pp": 0.3539085728812919
          },
          {
            "code": "301560.XSHE",
            "entry_date": "2026-09-28",
            "b_minus_a_pp": 14.918268863877424
          },
          {
            "code": "600059.XSHG",
            "entry_date": "2026-09-07",
            "b_minus_a_pp": -0.10687346784138903
          },
          {
            "code": "600227.XSHG",
            "entry_date": "2026-07-22",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "600371.XSHG",
            "entry_date": "2026-09-28",
            "b_minus_a_pp": 0.06620993154995071
          },
          {
            "code": "600712.XSHG",
            "entry_date": "2026-08-06",
            "b_minus_a_pp": 0.5426480408438968
          },
          {
            "code": "601188.XSHG",
            "entry_date": "2026-10-16",
            "b_minus_a_pp": 0.6487960736632882
          },
          {
            "code": "603042.XSHG",
            "entry_date": "2026-09-29",
            "b_minus_a_pp": -0.12871204274502723
          },
          {
            "code": "603106.XSHG",
            "entry_date": "2026-08-06",
            "b_minus_a_pp": -3.578254252091518
          },
          {
            "code": "603123.XSHG",
            "entry_date": "2026-07-23",
            "b_minus_a_pp": 0.11240013532151873
          },
          {
            "code": "603580.XSHG",
            "entry_date": "2026-07-29",
            "b_minus_a_pp": 0.0
          },
          {
            "code": "603661.XSHG",
            "entry_date": "2026-06-29",
            "b_minus_a_pp": 1.2402978575498722
          },
          {
            "code": "603757.XSHG",
            "entry_date": "2026-06-25",
            "b_minus_a_pp": 0.10943777709987154
          },
          {
            "code": "603928.XSHG",
            "entry_date": "2026-07-13",
            "b_minus_a_pp": 0.4119457543105079
          },
          {
            "code": "605366.XSHG",
            "entry_date": "2026-10-12",
            "b_minus_a_pp": -11.557685803722265
          },
          {
            "code": "688103.XSHG",
            "entry_date": "2026-07-07",
            "b_minus_a_pp": -1.1489290087455097
          },
          {
            "code": "688106.XSHG",
            "entry_date": "2026-07-13",
            "b_minus_a_pp": -0.1603426343938514
          }
        ],
        "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias"
      },
      "audit": [
        {
          "source": "output/live/positions.jsonl",
          "line": 1,
          "book": "B",
          "code": "000509.XSHE",
          "entry_date": "2026-06-01",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 5.08 -> window-vwap fill 4.98 (minute-reconstructed 2026-06-22); Δrealized +320.04"
          },
          "buy_trade_line": 1,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 2,
          "book": "B",
          "code": "603032.XSHG",
          "entry_date": "2026-06-01",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 25.73 -> window-vwap fill 25.3561 (minute-reconstructed 2026-06-22); Δrealized +224.33"
          },
          "buy_trade_line": 2,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 3,
          "book": "B",
          "code": "000636.XSHE",
          "entry_date": "2026-06-01",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 49.96 -> window-vwap fill 49.2249 (minute-reconstructed 2026-06-22); Δrealized +220.55"
          },
          "buy_trade_line": 3,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 4,
          "book": "B",
          "code": "002457.XSHE",
          "entry_date": "2026-06-02",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 12.638 -> window-vwap fill 12.39 (minute-reconstructed 2026-06-22); Δrealized +123.91"
          },
          "buy_trade_line": 4,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 5,
          "book": "B",
          "code": "000608.XSHE",
          "entry_date": "2026-06-02",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 5.029 -> window-vwap fill 4.8953 (minute-reconstructed 2026-06-22); Δrealized +173.30"
          },
          "buy_trade_line": 5,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 6,
          "book": "B",
          "code": "605277.XSHG",
          "entry_date": "2026-06-02",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 25.806 -> window-vwap fill 24.5676 (minute-reconstructed 2026-06-22); Δrealized +247.71"
          },
          "buy_trade_line": 6,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 7,
          "book": "B",
          "code": "002995.XSHE",
          "entry_date": "2026-06-03",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 25.072 -> window-vwap fill 24.7029 (minute-reconstructed 2026-06-22); Δrealized +184.36"
          },
          "buy_trade_line": 10,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 8,
          "book": "B",
          "code": "600797.XSHG",
          "entry_date": "2026-06-03",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 8.037 -> window-vwap fill 7.8743 (minute-reconstructed 2026-06-22); Δrealized +276.28"
          },
          "buy_trade_line": 11,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 9,
          "book": "B",
          "code": "920190.BJSE",
          "entry_date": "2026-06-03",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 34.167 -> window-vwap fill 33.6263 (minute-reconstructed 2026-06-22); Δrealized +216.18"
          },
          "buy_trade_line": 12,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 10,
          "book": "B",
          "code": "002951.XSHE",
          "entry_date": "2026-06-04",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 21.838 -> window-vwap fill 21.517 (minute-reconstructed 2026-06-22); Δrealized +128.47"
          },
          "buy_trade_line": 16,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 11,
          "book": "B",
          "code": "000881.XSHE",
          "entry_date": "2026-06-04",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 8.263 -> window-vwap fill 8.0867 (minute-reconstructed 2026-06-22); Δrealized +176.12"
          },
          "buy_trade_line": 17,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 12,
          "book": "B",
          "code": "000601.XSHE",
          "entry_date": "2026-06-04",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 9.027 -> window-vwap fill 8.8425 (minute-reconstructed 2026-06-22); Δrealized +184.52"
          },
          "buy_trade_line": 18,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 13,
          "book": "B",
          "code": "300516.XSHE",
          "entry_date": "2026-06-05",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 42.636 -> window-vwap fill 41.927 (minute-reconstructed 2026-06-22); Δrealized +141.81"
          },
          "buy_trade_line": 22,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 14,
          "book": "B",
          "code": "300197.XSHE",
          "entry_date": "2026-06-05",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 2.754 -> window-vwap fill 2.6865 (minute-reconstructed 2026-06-22); Δrealized +290.27"
          },
          "buy_trade_line": 23,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 15,
          "book": "B",
          "code": "600121.XSHG",
          "entry_date": "2026-06-05",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 5.753 -> window-vwap fill 5.5654 (minute-reconstructed 2026-06-22); Δrealized +374.84"
          },
          "buy_trade_line": 24,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 16,
          "book": "B",
          "code": "600255.XSHG",
          "entry_date": "2026-06-08",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 4.437 -> window-vwap fill 4.364 (minute-reconstructed 2026-06-22); Δrealized +138.71"
          },
          "buy_trade_line": 27,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 17,
          "book": "B",
          "code": "600439.XSHG",
          "entry_date": "2026-06-08",
          "state": "unknown",
          "historical_repair_annotation": {
            "_rederive_note": "basket 2.693 -> window-vwap fill 2.6458 (minute-reconstructed 2026-06-22); Δrealized +150.41"
          },
          "buy_trade_line": 28,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 18,
          "book": "B",
          "code": "002747.XSHE",
          "entry_date": "2026-06-09",
          "state": "valid",
          "buy_trade_line": 32,
          "sell_trade_line": 41,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 19,
          "book": "B",
          "code": "920088.BJSE",
          "entry_date": "2026-06-09",
          "state": "valid",
          "buy_trade_line": 33,
          "sell_trade_line": 42,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 20,
          "book": "B",
          "code": "920961.BJSE",
          "entry_date": "2026-06-09",
          "state": "valid",
          "buy_trade_line": 34,
          "sell_trade_line": 43,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 21,
          "book": "B",
          "code": "000670.XSHE",
          "entry_date": "2026-06-10",
          "state": "valid",
          "buy_trade_line": 38,
          "sell_trade_line": 47,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 22,
          "book": "B",
          "code": "603859.XSHG",
          "entry_date": "2026-06-10",
          "state": "valid",
          "buy_trade_line": 39,
          "sell_trade_line": 49,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 23,
          "book": "B",
          "code": "002613.XSHE",
          "entry_date": "2026-06-10",
          "state": "valid",
          "buy_trade_line": 40,
          "sell_trade_line": 48,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 24,
          "book": "B",
          "code": "002362.XSHE",
          "entry_date": "2026-06-11",
          "state": "valid",
          "buy_trade_line": 44,
          "sell_trade_line": 53,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 25,
          "book": "B",
          "code": "001696.XSHE",
          "entry_date": "2026-06-11",
          "state": "valid",
          "buy_trade_line": 45,
          "sell_trade_line": 54,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 26,
          "book": "B",
          "code": "603330.XSHG",
          "entry_date": "2026-06-11",
          "state": "valid",
          "buy_trade_line": 46,
          "sell_trade_line": 55,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 27,
          "book": "B",
          "code": "300264.XSHE",
          "entry_date": "2026-06-12",
          "state": "valid",
          "buy_trade_line": 50,
          "sell_trade_line": 65,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 28,
          "book": "B",
          "code": "603886.XSHG",
          "entry_date": "2026-06-12",
          "state": "valid",
          "buy_trade_line": 51,
          "sell_trade_line": 66,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 29,
          "book": "B",
          "code": "600703.XSHG",
          "entry_date": "2026-06-12",
          "state": "valid",
          "buy_trade_line": 52,
          "sell_trade_line": 88,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 30,
          "book": "A",
          "code": "300264.XSHE",
          "entry_date": "2026-06-12",
          "state": "valid",
          "buy_trade_line": 56,
          "sell_trade_line": 67,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 31,
          "book": "A",
          "code": "603886.XSHG",
          "entry_date": "2026-06-12",
          "state": "valid",
          "buy_trade_line": 57,
          "sell_trade_line": 68,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 32,
          "book": "A",
          "code": "600703.XSHG",
          "entry_date": "2026-06-12",
          "state": "valid",
          "buy_trade_line": 58,
          "sell_trade_line": 69,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 33,
          "book": "A",
          "code": "300894.XSHE",
          "entry_date": "2026-06-15",
          "state": "valid",
          "buy_trade_line": 59,
          "sell_trade_line": 79,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 34,
          "book": "A",
          "code": "002490.XSHE",
          "entry_date": "2026-06-15",
          "state": "valid",
          "buy_trade_line": 60,
          "sell_trade_line": 80,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 35,
          "book": "A",
          "code": "000759.XSHE",
          "entry_date": "2026-06-15",
          "state": "valid",
          "buy_trade_line": 61,
          "sell_trade_line": 81,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 36,
          "book": "B",
          "code": "300894.XSHE",
          "entry_date": "2026-06-15",
          "state": "valid",
          "buy_trade_line": 62,
          "sell_trade_line": 76,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 37,
          "book": "B",
          "code": "002490.XSHE",
          "entry_date": "2026-06-15",
          "state": "valid",
          "buy_trade_line": 63,
          "sell_trade_line": 77,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 38,
          "book": "B",
          "code": "000759.XSHE",
          "entry_date": "2026-06-15",
          "state": "valid",
          "buy_trade_line": 64,
          "sell_trade_line": 78,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 39,
          "book": "A",
          "code": "603065.XSHG",
          "entry_date": "2026-06-16",
          "state": "valid",
          "buy_trade_line": 70,
          "sell_trade_line": 99,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 40,
          "book": "A",
          "code": "300377.XSHE",
          "entry_date": "2026-06-16",
          "state": "valid",
          "buy_trade_line": 71,
          "sell_trade_line": 100,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 41,
          "book": "A",
          "code": "600067.XSHG",
          "entry_date": "2026-06-16",
          "state": "valid",
          "buy_trade_line": 72,
          "sell_trade_line": 101,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 42,
          "book": "B",
          "code": "603065.XSHG",
          "entry_date": "2026-06-16",
          "state": "valid",
          "buy_trade_line": 73,
          "sell_trade_line": 89,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 43,
          "book": "B",
          "code": "300377.XSHE",
          "entry_date": "2026-06-16",
          "state": "valid",
          "buy_trade_line": 74,
          "sell_trade_line": 90,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 44,
          "book": "B",
          "code": "600067.XSHG",
          "entry_date": "2026-06-16",
          "state": "valid",
          "buy_trade_line": 75,
          "sell_trade_line": 91,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 45,
          "book": "A",
          "code": "300726.XSHE",
          "entry_date": "2026-06-17",
          "state": "valid",
          "buy_trade_line": 82,
          "sell_trade_line": 107,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 46,
          "book": "A",
          "code": "002263.XSHE",
          "entry_date": "2026-06-17",
          "state": "valid",
          "buy_trade_line": 83,
          "sell_trade_line": 108,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 47,
          "book": "A",
          "code": "600460.XSHG",
          "entry_date": "2026-06-17",
          "state": "valid",
          "buy_trade_line": 84,
          "sell_trade_line": 109,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 48,
          "book": "B",
          "code": "300726.XSHE",
          "entry_date": "2026-06-17",
          "state": "valid",
          "buy_trade_line": 85,
          "sell_trade_line": 96,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 49,
          "book": "B",
          "code": "002263.XSHE",
          "entry_date": "2026-06-17",
          "state": "valid",
          "buy_trade_line": 86,
          "sell_trade_line": 97,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 50,
          "book": "B",
          "code": "600460.XSHG",
          "entry_date": "2026-06-17",
          "state": "valid",
          "buy_trade_line": 87,
          "sell_trade_line": 98,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 51,
          "book": "A",
          "code": "300522.XSHE",
          "entry_date": "2026-06-18",
          "state": "valid",
          "buy_trade_line": 92,
          "sell_trade_line": 119,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 52,
          "book": "A",
          "code": "300411.XSHE",
          "entry_date": "2026-06-18",
          "state": "valid",
          "buy_trade_line": 93,
          "sell_trade_line": 120,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 53,
          "book": "B",
          "code": "300522.XSHE",
          "entry_date": "2026-06-18",
          "state": "valid",
          "buy_trade_line": 94,
          "sell_trade_line": 116,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 54,
          "book": "B",
          "code": "300411.XSHE",
          "entry_date": "2026-06-18",
          "state": "valid",
          "buy_trade_line": 95,
          "sell_trade_line": 106,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 55,
          "book": "A",
          "code": "001282.XSHE",
          "entry_date": "2026-06-22",
          "state": "valid",
          "buy_trade_line": 102,
          "sell_trade_line": 128,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 56,
          "book": "A",
          "code": "000679.XSHE",
          "entry_date": "2026-06-22",
          "state": "valid",
          "buy_trade_line": 103,
          "sell_trade_line": 129,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 57,
          "book": "B",
          "code": "001282.XSHE",
          "entry_date": "2026-06-22",
          "state": "valid",
          "buy_trade_line": 104,
          "sell_trade_line": 117,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 58,
          "book": "B",
          "code": "000679.XSHE",
          "entry_date": "2026-06-22",
          "state": "valid",
          "buy_trade_line": 105,
          "sell_trade_line": 118,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 59,
          "book": "A",
          "code": "300319.XSHE",
          "entry_date": "2026-06-23",
          "state": "valid",
          "buy_trade_line": 110,
          "sell_trade_line": 130,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 60,
          "book": "A",
          "code": "002579.XSHE",
          "entry_date": "2026-06-23",
          "state": "valid",
          "buy_trade_line": 111,
          "sell_trade_line": 131,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 61,
          "book": "A",
          "code": "600545.XSHG",
          "entry_date": "2026-06-23",
          "state": "valid",
          "buy_trade_line": 112,
          "sell_trade_line": 132,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 62,
          "book": "B",
          "code": "300319.XSHE",
          "entry_date": "2026-06-23",
          "state": "valid",
          "buy_trade_line": 113,
          "sell_trade_line": 127,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 63,
          "book": "B",
          "code": "002579.XSHE",
          "entry_date": "2026-06-23",
          "state": "valid",
          "buy_trade_line": 114,
          "sell_trade_line": 126,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 64,
          "book": "B",
          "code": "600545.XSHG",
          "entry_date": "2026-06-23",
          "state": "valid",
          "buy_trade_line": 115,
          "sell_trade_line": 125,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 65,
          "book": "A",
          "code": "920790.BJSE",
          "entry_date": "2026-06-24",
          "state": "valid",
          "buy_trade_line": 121,
          "sell_trade_line": 141,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 66,
          "book": "A",
          "code": "000545.XSHE",
          "entry_date": "2026-06-24",
          "state": "valid",
          "buy_trade_line": 122,
          "sell_trade_line": 142,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 67,
          "book": "B",
          "code": "920790.BJSE",
          "entry_date": "2026-06-24",
          "state": "valid",
          "buy_trade_line": 123,
          "sell_trade_line": 139,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 68,
          "book": "B",
          "code": "000545.XSHE",
          "entry_date": "2026-06-24",
          "state": "valid",
          "buy_trade_line": 124,
          "sell_trade_line": 140,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 69,
          "book": "A",
          "code": "002549.XSHE",
          "entry_date": "2026-06-25",
          "state": "valid",
          "buy_trade_line": 133,
          "sell_trade_line": 148,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 70,
          "book": "A",
          "code": "600488.XSHG",
          "entry_date": "2026-06-25",
          "state": "valid",
          "buy_trade_line": 134,
          "sell_trade_line": 149,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 71,
          "book": "A",
          "code": "603757.XSHG",
          "entry_date": "2026-06-25",
          "state": "valid",
          "buy_trade_line": 135,
          "sell_trade_line": 150,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 72,
          "book": "B",
          "code": "002549.XSHE",
          "entry_date": "2026-06-25",
          "state": "valid",
          "buy_trade_line": 136,
          "sell_trade_line": 146,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 73,
          "book": "B",
          "code": "600488.XSHG",
          "entry_date": "2026-06-25",
          "state": "valid",
          "buy_trade_line": 137,
          "sell_trade_line": 145,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 74,
          "book": "B",
          "code": "603757.XSHG",
          "entry_date": "2026-06-25",
          "state": "valid",
          "buy_trade_line": 138,
          "sell_trade_line": 147,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 75,
          "book": "A",
          "code": "002141.XSHE",
          "entry_date": "2026-06-26",
          "state": "valid",
          "buy_trade_line": 143,
          "sell_trade_line": 158,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 76,
          "book": "B",
          "code": "002141.XSHE",
          "entry_date": "2026-06-26",
          "state": "valid",
          "buy_trade_line": 144,
          "sell_trade_line": 157,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 77,
          "book": "A",
          "code": "002579.XSHE",
          "entry_date": "2026-06-29",
          "state": "valid",
          "buy_trade_line": 151,
          "sell_trade_line": 165,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 78,
          "book": "A",
          "code": "000818.XSHE",
          "entry_date": "2026-06-29",
          "state": "valid",
          "buy_trade_line": 152,
          "sell_trade_line": 166,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 79,
          "book": "A",
          "code": "603661.XSHG",
          "entry_date": "2026-06-29",
          "state": "valid",
          "buy_trade_line": 153,
          "sell_trade_line": 167,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 80,
          "book": "B",
          "code": "002579.XSHE",
          "entry_date": "2026-06-29",
          "state": "valid",
          "buy_trade_line": 154,
          "sell_trade_line": 163,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 81,
          "book": "B",
          "code": "000818.XSHE",
          "entry_date": "2026-06-29",
          "state": "valid",
          "buy_trade_line": 155,
          "sell_trade_line": 172,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 82,
          "book": "B",
          "code": "603661.XSHG",
          "entry_date": "2026-06-29",
          "state": "valid",
          "buy_trade_line": 156,
          "sell_trade_line": 164,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 83,
          "book": "A",
          "code": "603687.XSHG",
          "entry_date": "2026-06-30",
          "state": "valid",
          "buy_trade_line": 159,
          "sell_trade_line": 175,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 84,
          "book": "A",
          "code": "002962.XSHE",
          "entry_date": "2026-06-30",
          "state": "valid",
          "buy_trade_line": 160,
          "sell_trade_line": 176,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 85,
          "book": "B",
          "code": "603687.XSHG",
          "entry_date": "2026-06-30",
          "state": "valid",
          "buy_trade_line": 161,
          "sell_trade_line": 173,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 86,
          "book": "B",
          "code": "002962.XSHE",
          "entry_date": "2026-06-30",
          "state": "valid",
          "buy_trade_line": 162,
          "sell_trade_line": 174,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 87,
          "book": "A",
          "code": "301051.XSHE",
          "entry_date": "2026-07-01",
          "state": "valid",
          "buy_trade_line": 168,
          "sell_trade_line": 188,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 88,
          "book": "A",
          "code": "002866.XSHE",
          "entry_date": "2026-07-01",
          "state": "valid",
          "buy_trade_line": 169,
          "sell_trade_line": 189,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 89,
          "book": "B",
          "code": "301051.XSHE",
          "entry_date": "2026-07-01",
          "state": "valid",
          "buy_trade_line": 170,
          "sell_trade_line": 186,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 90,
          "book": "B",
          "code": "002866.XSHE",
          "entry_date": "2026-07-01",
          "state": "valid",
          "buy_trade_line": 171,
          "sell_trade_line": 187,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 91,
          "book": "A",
          "code": "000100.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 177,
          "sell_trade_line": 199,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 92,
          "book": "A",
          "code": "002208.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 178,
          "sell_trade_line": 200,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 93,
          "book": "A",
          "code": "300980.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 179,
          "sell_trade_line": 201,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 94,
          "book": "B",
          "code": "000100.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 180,
          "sell_trade_line": 196,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 95,
          "book": "B",
          "code": "002208.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 181,
          "sell_trade_line": 197,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 96,
          "book": "B",
          "code": "300980.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 182,
          "sell_trade_line": 198,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 97,
          "book": "T",
          "code": "003816.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 183,
          "sell_trade_line": 426,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 98,
          "book": "T",
          "code": "601288.XSHG",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 184,
          "sell_trade_line": 208,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 99,
          "book": "T",
          "code": "000725.XSHE",
          "entry_date": "2026-07-02",
          "state": "valid",
          "buy_trade_line": 185,
          "sell_trade_line": 213,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 100,
          "book": "A",
          "code": "300651.XSHE",
          "entry_date": "2026-07-03",
          "state": "valid",
          "buy_trade_line": 190,
          "sell_trade_line": 214,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 101,
          "book": "A",
          "code": "002326.XSHE",
          "entry_date": "2026-07-03",
          "state": "valid",
          "buy_trade_line": 191,
          "sell_trade_line": 215,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 102,
          "book": "A",
          "code": "300853.XSHE",
          "entry_date": "2026-07-03",
          "state": "valid",
          "buy_trade_line": 192,
          "sell_trade_line": 216,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 103,
          "book": "B",
          "code": "300651.XSHE",
          "entry_date": "2026-07-03",
          "state": "valid",
          "buy_trade_line": 193,
          "sell_trade_line": 212,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 104,
          "book": "B",
          "code": "002326.XSHE",
          "entry_date": "2026-07-03",
          "state": "valid",
          "buy_trade_line": 194,
          "sell_trade_line": 210,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 105,
          "book": "B",
          "code": "300853.XSHE",
          "entry_date": "2026-07-03",
          "state": "valid",
          "buy_trade_line": 195,
          "sell_trade_line": 211,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 106,
          "book": "A",
          "code": "002458.XSHE",
          "entry_date": "2026-07-06",
          "state": "valid",
          "buy_trade_line": 202,
          "sell_trade_line": 225,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 107,
          "book": "A",
          "code": "002826.XSHE",
          "entry_date": "2026-07-06",
          "state": "valid",
          "buy_trade_line": 203,
          "sell_trade_line": 226,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 108,
          "book": "A",
          "code": "301379.XSHE",
          "entry_date": "2026-07-06",
          "state": "valid",
          "buy_trade_line": 204,
          "sell_trade_line": 227,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 109,
          "book": "B",
          "code": "002458.XSHE",
          "entry_date": "2026-07-06",
          "state": "valid",
          "buy_trade_line": 205,
          "sell_trade_line": 223,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 110,
          "book": "B",
          "code": "002826.XSHE",
          "entry_date": "2026-07-06",
          "state": "valid",
          "buy_trade_line": 206,
          "sell_trade_line": 224,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 111,
          "book": "B",
          "code": "301379.XSHE",
          "entry_date": "2026-07-06",
          "state": "valid",
          "buy_trade_line": 207,
          "sell_trade_line": 222,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 112,
          "book": "T",
          "code": "601728.XSHG",
          "entry_date": "2026-07-06",
          "state": "valid",
          "buy_trade_line": 209,
          "sell_trade_line": 431,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 113,
          "book": "A",
          "code": "688103.XSHG",
          "entry_date": "2026-07-07",
          "state": "valid",
          "buy_trade_line": 217,
          "sell_trade_line": 236,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 114,
          "book": "A",
          "code": "002457.XSHE",
          "entry_date": "2026-07-07",
          "state": "valid",
          "buy_trade_line": 218,
          "sell_trade_line": 237,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 115,
          "book": "B",
          "code": "688103.XSHG",
          "entry_date": "2026-07-07",
          "state": "valid",
          "buy_trade_line": 219,
          "sell_trade_line": 234,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 116,
          "book": "B",
          "code": "002457.XSHE",
          "entry_date": "2026-07-07",
          "state": "valid",
          "buy_trade_line": 220,
          "sell_trade_line": 235,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 117,
          "book": "T",
          "code": "000725.XSHE",
          "entry_date": "2026-07-07",
          "state": "valid",
          "historical_repair_annotation": {
            "ledger_repair_id": "book_t_blocked_2026-07-13_000725.XSHE_2026-07-07"
          },
          "buy_trade_line": 221,
          "sell_trade_line": 272,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 118,
          "book": "A",
          "code": "002607.XSHE",
          "entry_date": "2026-07-08",
          "state": "valid",
          "buy_trade_line": 228,
          "sell_trade_line": 246,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 119,
          "book": "A",
          "code": "002137.XSHE",
          "entry_date": "2026-07-08",
          "state": "valid",
          "buy_trade_line": 229,
          "sell_trade_line": 247,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 120,
          "book": "A",
          "code": "002584.XSHE",
          "entry_date": "2026-07-08",
          "state": "valid",
          "buy_trade_line": 230,
          "sell_trade_line": 248,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 121,
          "book": "B",
          "code": "002607.XSHE",
          "entry_date": "2026-07-08",
          "state": "valid",
          "buy_trade_line": 231,
          "sell_trade_line": 244,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 122,
          "book": "B",
          "code": "002137.XSHE",
          "entry_date": "2026-07-08",
          "state": "valid",
          "buy_trade_line": 232,
          "sell_trade_line": 245,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 123,
          "book": "B",
          "code": "002584.XSHE",
          "entry_date": "2026-07-08",
          "state": "valid",
          "buy_trade_line": 233,
          "sell_trade_line": 243,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 124,
          "book": "A",
          "code": "002520.XSHE",
          "entry_date": "2026-07-09",
          "state": "valid",
          "buy_trade_line": 238,
          "sell_trade_line": 257,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 125,
          "book": "A",
          "code": "600793.XSHG",
          "entry_date": "2026-07-09",
          "state": "valid",
          "buy_trade_line": 239,
          "sell_trade_line": 258,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 126,
          "book": "A",
          "code": "688103.XSHG",
          "entry_date": "2026-07-09",
          "state": "valid",
          "buy_trade_line": 240,
          "sell_trade_line": 259,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 127,
          "book": "B",
          "code": "002520.XSHE",
          "entry_date": "2026-07-09",
          "state": "valid",
          "buy_trade_line": 241,
          "sell_trade_line": 255,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 128,
          "book": "B",
          "code": "600793.XSHG",
          "entry_date": "2026-07-09",
          "state": "valid",
          "buy_trade_line": 242,
          "sell_trade_line": 256,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 129,
          "book": "A",
          "code": "600094.XSHG",
          "entry_date": "2026-07-10",
          "state": "valid",
          "buy_trade_line": 249,
          "sell_trade_line": 266,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 130,
          "book": "A",
          "code": "600288.XSHG",
          "entry_date": "2026-07-10",
          "state": "valid",
          "buy_trade_line": 250,
          "sell_trade_line": 267,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 131,
          "book": "A",
          "code": "003020.XSHE",
          "entry_date": "2026-07-10",
          "state": "valid",
          "buy_trade_line": 251,
          "sell_trade_line": 268,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 132,
          "book": "B",
          "code": "600094.XSHG",
          "entry_date": "2026-07-10",
          "state": "valid",
          "buy_trade_line": 252,
          "sell_trade_line": 264,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 133,
          "book": "B",
          "code": "600288.XSHG",
          "entry_date": "2026-07-10",
          "state": "valid",
          "buy_trade_line": 253,
          "sell_trade_line": 265,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 134,
          "book": "B",
          "code": "003020.XSHE",
          "entry_date": "2026-07-10",
          "state": "valid",
          "buy_trade_line": 254,
          "sell_trade_line": 270,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 135,
          "book": "A",
          "code": "603928.XSHG",
          "entry_date": "2026-07-13",
          "state": "valid",
          "buy_trade_line": 260,
          "sell_trade_line": 273,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 136,
          "book": "A",
          "code": "688106.XSHG",
          "entry_date": "2026-07-13",
          "state": "valid",
          "buy_trade_line": 261,
          "sell_trade_line": 274,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 137,
          "book": "B",
          "code": "603928.XSHG",
          "entry_date": "2026-07-13",
          "state": "valid",
          "buy_trade_line": 262,
          "sell_trade_line": 269,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 138,
          "book": "B",
          "code": "688106.XSHG",
          "entry_date": "2026-07-13",
          "state": "valid",
          "buy_trade_line": 263,
          "sell_trade_line": 271,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 139,
          "book": "T",
          "code": "000725.XSHE",
          "entry_date": "2026-07-15",
          "state": "valid",
          "buy_trade_line": 275,
          "sell_trade_line": 280,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 140,
          "book": "A",
          "code": "300937.XSHE",
          "entry_date": "2026-07-16",
          "state": "valid",
          "buy_trade_line": 276,
          "sell_trade_line": 285,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 141,
          "book": "A",
          "code": "002558.XSHE",
          "entry_date": "2026-07-16",
          "state": "valid",
          "buy_trade_line": 277,
          "sell_trade_line": 286,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 142,
          "book": "B",
          "code": "300937.XSHE",
          "entry_date": "2026-07-16",
          "state": "valid",
          "buy_trade_line": 278,
          "sell_trade_line": 283,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 143,
          "book": "B",
          "code": "002558.XSHE",
          "entry_date": "2026-07-16",
          "state": "valid",
          "buy_trade_line": 279,
          "sell_trade_line": 284,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 144,
          "book": "T",
          "code": "000725.XSHE",
          "entry_date": "2026-07-17",
          "state": "valid",
          "buy_trade_line": 281,
          "sell_trade_line": 314,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 145,
          "book": "B",
          "code": "300665.XSHE",
          "entry_date": "2026-07-17",
          "state": "valid",
          "buy_trade_line": 282,
          "sell_trade_line": 287,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 146,
          "book": "A",
          "code": "300577.XSHE",
          "entry_date": "2026-07-21",
          "state": "valid",
          "buy_trade_line": 288,
          "sell_trade_line": 297,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 147,
          "book": "B",
          "code": "300577.XSHE",
          "entry_date": "2026-07-21",
          "state": "valid",
          "buy_trade_line": 289,
          "sell_trade_line": 296,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 148,
          "book": "A",
          "code": "300534.XSHE",
          "entry_date": "2026-07-22",
          "state": "valid",
          "buy_trade_line": 290,
          "sell_trade_line": 303,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 149,
          "book": "A",
          "code": "600227.XSHG",
          "entry_date": "2026-07-22",
          "state": "valid",
          "buy_trade_line": 291,
          "sell_trade_line": 304,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 150,
          "book": "A",
          "code": "000938.XSHE",
          "entry_date": "2026-07-22",
          "state": "valid",
          "buy_trade_line": 292,
          "sell_trade_line": 305,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 151,
          "book": "B",
          "code": "300534.XSHE",
          "entry_date": "2026-07-22",
          "state": "valid",
          "buy_trade_line": 293,
          "sell_trade_line": 301,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 152,
          "book": "B",
          "code": "600227.XSHG",
          "entry_date": "2026-07-22",
          "state": "valid",
          "buy_trade_line": 294,
          "sell_trade_line": 302,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 153,
          "book": "B",
          "code": "000938.XSHE",
          "entry_date": "2026-07-22",
          "state": "valid",
          "buy_trade_line": 295,
          "sell_trade_line": 300,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 154,
          "book": "A",
          "code": "603123.XSHG",
          "entry_date": "2026-07-23",
          "state": "valid",
          "buy_trade_line": 298,
          "sell_trade_line": 309,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 155,
          "book": "B",
          "code": "603123.XSHG",
          "entry_date": "2026-07-23",
          "state": "valid",
          "buy_trade_line": 299,
          "sell_trade_line": 308,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 156,
          "book": "A",
          "code": "002173.XSHE",
          "entry_date": "2026-07-24",
          "state": "valid",
          "buy_trade_line": 306,
          "sell_trade_line": 312,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 157,
          "book": "B",
          "code": "002173.XSHE",
          "entry_date": "2026-07-24",
          "state": "valid",
          "buy_trade_line": 307,
          "sell_trade_line": 321,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 158,
          "book": "A",
          "code": "300214.XSHE",
          "entry_date": "2026-07-27",
          "state": "valid",
          "buy_trade_line": 310,
          "sell_trade_line": 315,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 159,
          "book": "B",
          "code": "300214.XSHE",
          "entry_date": "2026-07-27",
          "state": "valid",
          "buy_trade_line": 311,
          "sell_trade_line": 313,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 160,
          "book": "A",
          "code": "603580.XSHG",
          "entry_date": "2026-07-29",
          "state": "valid",
          "buy_trade_line": 316,
          "sell_trade_line": 328,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 161,
          "book": "A",
          "code": "300331.XSHE",
          "entry_date": "2026-07-29",
          "state": "valid",
          "buy_trade_line": 317,
          "sell_trade_line": 329,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 162,
          "book": "B",
          "code": "603580.XSHG",
          "entry_date": "2026-07-29",
          "state": "valid",
          "buy_trade_line": 318,
          "sell_trade_line": 327,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 163,
          "book": "B",
          "code": "300331.XSHE",
          "entry_date": "2026-07-29",
          "state": "valid",
          "buy_trade_line": 319,
          "sell_trade_line": 326,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 164,
          "book": "T",
          "code": "000725.XSHE",
          "entry_date": "2026-07-29",
          "state": "valid",
          "buy_trade_line": 320,
          "sell_trade_line": 388,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 165,
          "book": "A",
          "code": "002279.XSHE",
          "entry_date": "2026-07-30",
          "state": "valid",
          "buy_trade_line": 322,
          "sell_trade_line": 332,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 166,
          "book": "A",
          "code": "002173.XSHE",
          "entry_date": "2026-07-30",
          "state": "valid",
          "buy_trade_line": 323,
          "sell_trade_line": 333,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 167,
          "book": "B",
          "code": "002279.XSHE",
          "entry_date": "2026-07-30",
          "state": "valid",
          "buy_trade_line": 324,
          "sell_trade_line": 331,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 168,
          "book": "B",
          "code": "002173.XSHE",
          "entry_date": "2026-07-30",
          "state": "valid",
          "buy_trade_line": 325,
          "sell_trade_line": 330,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 169,
          "book": "A",
          "code": "600712.XSHG",
          "entry_date": "2026-08-06",
          "state": "valid",
          "buy_trade_line": 334,
          "sell_trade_line": 340,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 170,
          "book": "A",
          "code": "603106.XSHG",
          "entry_date": "2026-08-06",
          "state": "valid",
          "buy_trade_line": 335,
          "sell_trade_line": 341,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 171,
          "book": "B",
          "code": "600712.XSHG",
          "entry_date": "2026-08-06",
          "state": "valid",
          "buy_trade_line": 336,
          "sell_trade_line": 339,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 172,
          "book": "B",
          "code": "603106.XSHG",
          "entry_date": "2026-08-06",
          "state": "valid",
          "buy_trade_line": 337,
          "sell_trade_line": 342,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 173,
          "book": "B",
          "code": "600611.XSHG",
          "entry_date": "2026-08-07",
          "state": "valid",
          "buy_trade_line": 338,
          "sell_trade_line": 343,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 174,
          "book": "A",
          "code": "002580.XSHE",
          "entry_date": "2026-08-11",
          "state": "valid",
          "buy_trade_line": 344,
          "sell_trade_line": 352,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 175,
          "book": "A",
          "code": "002762.XSHE",
          "entry_date": "2026-08-11",
          "state": "valid",
          "buy_trade_line": 345,
          "sell_trade_line": 353,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 176,
          "book": "A",
          "code": "002792.XSHE",
          "entry_date": "2026-08-11",
          "state": "valid",
          "buy_trade_line": 346,
          "sell_trade_line": 354,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 177,
          "book": "B",
          "code": "002580.XSHE",
          "entry_date": "2026-08-11",
          "state": "valid",
          "buy_trade_line": 347,
          "sell_trade_line": 350,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 178,
          "book": "B",
          "code": "002762.XSHE",
          "entry_date": "2026-08-11",
          "state": "valid",
          "buy_trade_line": 348,
          "sell_trade_line": 351,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 179,
          "book": "B",
          "code": "002792.XSHE",
          "entry_date": "2026-08-11",
          "state": "valid",
          "buy_trade_line": 349,
          "sell_trade_line": 355,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 180,
          "book": "A",
          "code": "002229.XSHE",
          "entry_date": "2026-08-14",
          "state": "valid",
          "buy_trade_line": 356,
          "sell_trade_line": 364,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 181,
          "book": "A",
          "code": "002396.XSHE",
          "entry_date": "2026-08-14",
          "state": "valid",
          "buy_trade_line": 357,
          "sell_trade_line": 365,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 182,
          "book": "A",
          "code": "300426.XSHE",
          "entry_date": "2026-08-14",
          "state": "valid",
          "buy_trade_line": 358,
          "sell_trade_line": 366,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 183,
          "book": "B",
          "code": "002229.XSHE",
          "entry_date": "2026-08-14",
          "state": "valid",
          "buy_trade_line": 359,
          "sell_trade_line": 367,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 184,
          "book": "B",
          "code": "002396.XSHE",
          "entry_date": "2026-08-14",
          "state": "valid",
          "buy_trade_line": 360,
          "sell_trade_line": 362,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 185,
          "book": "B",
          "code": "300426.XSHE",
          "entry_date": "2026-08-14",
          "state": "valid",
          "buy_trade_line": 361,
          "sell_trade_line": 363,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 186,
          "book": "A",
          "code": "002742.XSHE",
          "entry_date": "2026-08-25",
          "state": "valid",
          "buy_trade_line": 368,
          "sell_trade_line": 374,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 187,
          "book": "B",
          "code": "002742.XSHE",
          "entry_date": "2026-08-25",
          "state": "valid",
          "buy_trade_line": 369,
          "sell_trade_line": 381,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 188,
          "book": "A",
          "code": "000523.XSHE",
          "entry_date": "2026-08-26",
          "state": "valid",
          "buy_trade_line": 370,
          "sell_trade_line": 377,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 189,
          "book": "A",
          "code": "002963.XSHE",
          "entry_date": "2026-08-26",
          "state": "valid",
          "buy_trade_line": 371,
          "sell_trade_line": 378,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 190,
          "book": "B",
          "code": "000523.XSHE",
          "entry_date": "2026-08-26",
          "state": "valid",
          "buy_trade_line": 372,
          "sell_trade_line": 376,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 191,
          "book": "B",
          "code": "002963.XSHE",
          "entry_date": "2026-08-26",
          "state": "valid",
          "buy_trade_line": 373,
          "sell_trade_line": 375,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 192,
          "book": "A",
          "code": "001309.XSHE",
          "entry_date": "2026-08-28",
          "state": "valid",
          "buy_trade_line": 379,
          "sell_trade_line": 383,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 193,
          "book": "B",
          "code": "001309.XSHE",
          "entry_date": "2026-08-28",
          "state": "valid",
          "buy_trade_line": 380,
          "sell_trade_line": 382,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 194,
          "book": "A",
          "code": "002349.XSHE",
          "entry_date": "2026-09-01",
          "state": "valid",
          "buy_trade_line": 384,
          "sell_trade_line": 387,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 195,
          "book": "B",
          "code": "002349.XSHE",
          "entry_date": "2026-09-01",
          "state": "valid",
          "buy_trade_line": 385,
          "sell_trade_line": 386,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 196,
          "book": "B",
          "code": "600059.XSHG",
          "entry_date": "2026-09-07",
          "state": "valid",
          "buy_trade_line": 389,
          "sell_trade_line": 393,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 197,
          "book": "A",
          "code": "600059.XSHG",
          "entry_date": "2026-09-07",
          "state": "valid",
          "buy_trade_line": 390,
          "sell_trade_line": 394,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 198,
          "book": "T",
          "code": "000725.XSHE",
          "entry_date": "2026-09-07",
          "state": "valid",
          "buy_trade_line": 391,
          "sell_trade_line": 440,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 199,
          "book": "B",
          "code": "600371.XSHG",
          "entry_date": "2026-09-08",
          "state": "valid",
          "buy_trade_line": 392,
          "sell_trade_line": 395,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 200,
          "book": "B",
          "code": "001299.XSHE",
          "entry_date": "2026-09-11",
          "state": "valid",
          "buy_trade_line": 396,
          "sell_trade_line": 398,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 201,
          "book": "A",
          "code": "001299.XSHE",
          "entry_date": "2026-09-11",
          "state": "valid",
          "buy_trade_line": 397,
          "sell_trade_line": 399,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 202,
          "book": "B",
          "code": "002522.XSHE",
          "entry_date": "2026-09-16",
          "state": "valid",
          "buy_trade_line": 400,
          "sell_trade_line": 409,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 203,
          "book": "B",
          "code": "000572.XSHE",
          "entry_date": "2026-09-16",
          "state": "valid",
          "buy_trade_line": 401,
          "sell_trade_line": 410,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 204,
          "book": "A",
          "code": "002522.XSHE",
          "entry_date": "2026-09-16",
          "state": "valid",
          "buy_trade_line": 402,
          "sell_trade_line": 411,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 205,
          "book": "A",
          "code": "000572.XSHE",
          "entry_date": "2026-09-16",
          "state": "valid",
          "buy_trade_line": 403,
          "sell_trade_line": 412,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 206,
          "book": "B",
          "code": "002212.XSHE",
          "entry_date": "2026-09-17",
          "state": "valid",
          "buy_trade_line": 404,
          "sell_trade_line": 414,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 207,
          "book": "B",
          "code": "001209.XSHE",
          "entry_date": "2026-09-17",
          "state": "valid",
          "buy_trade_line": 405,
          "sell_trade_line": 413,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 208,
          "book": "B",
          "code": "002585.XSHE",
          "entry_date": "2026-09-17",
          "state": "valid",
          "buy_trade_line": 406,
          "sell_trade_line": 415,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 209,
          "book": "A",
          "code": "002212.XSHE",
          "entry_date": "2026-09-17",
          "state": "valid",
          "buy_trade_line": 407,
          "sell_trade_line": 416,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 210,
          "book": "A",
          "code": "001209.XSHE",
          "entry_date": "2026-09-17",
          "state": "valid",
          "buy_trade_line": 408,
          "sell_trade_line": 417,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 211,
          "book": "B",
          "code": "301520.XSHE",
          "entry_date": "2026-09-21",
          "state": "valid",
          "buy_trade_line": 418,
          "sell_trade_line": 420,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 212,
          "book": "A",
          "code": "301520.XSHE",
          "entry_date": "2026-09-21",
          "state": "valid",
          "buy_trade_line": 419,
          "sell_trade_line": 421,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 213,
          "book": "B",
          "code": "600371.XSHG",
          "entry_date": "2026-09-28",
          "state": "valid",
          "buy_trade_line": 422,
          "sell_trade_line": 433,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 214,
          "book": "B",
          "code": "301560.XSHE",
          "entry_date": "2026-09-28",
          "state": "valid",
          "buy_trade_line": 423,
          "sell_trade_line": 439,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 215,
          "book": "A",
          "code": "600371.XSHG",
          "entry_date": "2026-09-28",
          "state": "valid",
          "buy_trade_line": 424,
          "sell_trade_line": 434,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 216,
          "book": "A",
          "code": "301560.XSHE",
          "entry_date": "2026-09-28",
          "state": "valid",
          "buy_trade_line": 425,
          "sell_trade_line": 435,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 217,
          "book": "T",
          "code": "600050.XSHG",
          "entry_date": "2026-09-28",
          "state": "valid",
          "buy_trade_line": 427,
          "maturity": "immature"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 218,
          "book": "B",
          "code": "603042.XSHG",
          "entry_date": "2026-09-29",
          "state": "valid",
          "buy_trade_line": 428,
          "sell_trade_line": 436,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 219,
          "book": "B",
          "code": "301382.XSHE",
          "entry_date": "2026-09-29",
          "state": "valid",
          "buy_trade_line": 429,
          "sell_trade_line": 437,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 220,
          "book": "A",
          "code": "603042.XSHG",
          "entry_date": "2026-09-29",
          "state": "valid",
          "buy_trade_line": 430,
          "sell_trade_line": 438,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 221,
          "book": "T",
          "code": "601868.XSHG",
          "entry_date": "2026-09-29",
          "state": "valid",
          "buy_trade_line": 432,
          "maturity": "immature"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 222,
          "book": "B",
          "code": "000710.XSHE",
          "entry_date": "2026-10-09",
          "state": "valid",
          "buy_trade_line": 441,
          "sell_trade_line": 446,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 223,
          "book": "A",
          "code": "000710.XSHE",
          "entry_date": "2026-10-09",
          "state": "valid",
          "buy_trade_line": 442,
          "sell_trade_line": 448,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 224,
          "book": "T",
          "code": "000725.XSHE",
          "entry_date": "2026-10-09",
          "state": "valid",
          "buy_trade_line": 443,
          "maturity": "immature"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 225,
          "book": "B",
          "code": "605366.XSHG",
          "entry_date": "2026-10-12",
          "state": "valid",
          "buy_trade_line": 444,
          "sell_trade_line": 447,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 226,
          "book": "A",
          "code": "605366.XSHG",
          "entry_date": "2026-10-12",
          "state": "valid",
          "buy_trade_line": 445,
          "sell_trade_line": 449,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 227,
          "book": "B",
          "code": "002531.XSHE",
          "entry_date": "2026-10-14",
          "state": "valid",
          "buy_trade_line": 450,
          "sell_trade_line": 453,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 228,
          "book": "A",
          "code": "002531.XSHE",
          "entry_date": "2026-10-14",
          "state": "valid",
          "buy_trade_line": 451,
          "sell_trade_line": 454,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 229,
          "book": "B",
          "code": "603188.XSHG",
          "entry_date": "2026-10-15",
          "state": "valid",
          "buy_trade_line": 452,
          "sell_trade_line": 459,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 230,
          "book": "B",
          "code": "601188.XSHG",
          "entry_date": "2026-10-16",
          "state": "valid",
          "buy_trade_line": 455,
          "sell_trade_line": 460,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 231,
          "book": "B",
          "code": "300107.XSHE",
          "entry_date": "2026-10-16",
          "state": "valid",
          "buy_trade_line": 456,
          "sell_trade_line": 461,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 232,
          "book": "A",
          "code": "601188.XSHG",
          "entry_date": "2026-10-16",
          "state": "valid",
          "buy_trade_line": 457,
          "sell_trade_line": 462,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 233,
          "book": "A",
          "code": "300107.XSHE",
          "entry_date": "2026-10-16",
          "state": "valid",
          "buy_trade_line": 458,
          "sell_trade_line": 463,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 234,
          "book": "B",
          "code": "000573.XSHE",
          "entry_date": "2026-10-20",
          "state": "valid",
          "buy_trade_line": 464,
          "sell_trade_line": 469,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 235,
          "book": "A",
          "code": "000573.XSHE",
          "entry_date": "2026-10-20",
          "state": "valid",
          "buy_trade_line": 465,
          "sell_trade_line": 470,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 236,
          "book": "B",
          "code": "301052.XSHE",
          "entry_date": "2026-10-21",
          "state": "valid",
          "buy_trade_line": 466,
          "sell_trade_line": 472,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 237,
          "book": "B",
          "code": "002889.XSHE",
          "entry_date": "2026-10-21",
          "state": "valid",
          "buy_trade_line": 467,
          "sell_trade_line": 471,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 238,
          "book": "A",
          "code": "301052.XSHE",
          "entry_date": "2026-10-21",
          "state": "valid",
          "buy_trade_line": 468,
          "sell_trade_line": 475,
          "maturity": "closed"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 239,
          "book": "B",
          "code": "002172.XSHE",
          "entry_date": "2026-10-23",
          "state": "valid",
          "buy_trade_line": 473,
          "maturity": "immature"
        },
        {
          "source": "output/live/positions.jsonl",
          "line": 240,
          "book": "A",
          "code": "002172.XSHE",
          "entry_date": "2026-10-23",
          "state": "valid",
          "buy_trade_line": 474,
          "maturity": "immature"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 7,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 8,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 9,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 13,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 14,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 15,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 19,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 20,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 21,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 25,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 26,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 29,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 30,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 31,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 35,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 36,
          "state": "unknown",
          "reason": "unmatched_trade"
        },
        {
          "source": "output/live/paper_trades.jsonl",
          "line": 37,
          "state": "unknown",
          "reason": "unmatched_trade"
        }
      ],
      "timeliness_proven": false,
      "fill_basis_counts": {
        "basket": 9,
        "opening_window_capped_by_basket": 3,
        "open_reference": 21,
        "opening_window_vwap_capped_by_limit": 190
      },
      "limitations": [
        "Legacy date/naive clocks lack verified availability time and timezone; no intraday timeliness proof.",
        "Modeled paper fees and cash changes are not actual broker fees, executable alpha or portfolio NAV.",
        "A/B identical-entry closed-lot comparison has selection/censoring bias and is not KOL alpha.",
        "No no-KOL/current/challenger strategy runs inferred; no source truth repaired."
      ]
    },
    "shortline_research": {
      "status": "observed",
      "comparisons": [
        {
          "end": "2026-10-21",
          "observed_at": "2026-10-22T11:39:47.102458+08:00",
          "evidence": {
            "path": "output/research/shortline_comparisons/2026-10-21-fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2.json",
            "sha256": "fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2"
          },
          "paired_exit": {
            "eligible_pairs": 57,
            "entry_day_count": 35,
            "mean_b_minus_a_pp": 0.6287414497577378,
            "median_b_minus_a_pp": 0.0
          },
          "coverage": {
            "bjse_rows_retained_in_raw_denominator": 27,
            "candidate_rows": 988,
            "capture_hash_rows": 103,
            "complete_flag_days": 59,
            "complete_label_days": 50,
            "excluded_incomplete_flag_days": [
              "2026-06-01",
              "2026-06-02",
              "2026-06-03",
              "2026-06-04",
              "2026-06-05",
              "2026-06-08",
              "2026-06-09",
              "2026-06-10",
              "2026-06-11",
              "2026-06-12",
              "2026-06-15",
              "2026-06-16",
              "2026-06-17",
              "2026-06-18",
              "2026-06-22",
              "2026-06-23",
              "2026-06-24",
              "2026-06-25",
              "2026-06-26",
              "2026-06-29",
              "2026-06-30",
              "2026-07-01",
              "2026-07-02",
              "2026-07-03",
              "2026-07-06",
              "2026-07-07",
              "2026-07-08",
              "2026-07-09",
              "2026-07-10"
            ],
            "excluded_incomplete_label_days": [
              "2026-07-14",
              "2026-07-30",
              "2026-08-11",
              "2026-08-14",
              "2026-08-24",
              "2026-09-01",
              "2026-09-02",
              "2026-09-28",
              "2026-10-19"
            ],
            "fillability": {
              "False": 35,
              "None": 37,
              "True": 916
            },
            "signal_days": 88
          },
          "status": "descriptive_only_no_promotion"
        },
        {
          "end": "2026-10-23",
          "observed_at": "2026-10-23T20:35:24.740180+08:00",
          "evidence": {
            "path": "output/research/shortline_comparisons/2026-10-23-c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41.json",
            "sha256": "c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41"
          },
          "paired_exit": {
            "eligible_pairs": 58,
            "entry_day_count": 36,
            "mean_b_minus_a_pp": 0.670685079175,
            "median_b_minus_a_pp": 0.0
          },
          "coverage": {
            "bjse_rows_retained_in_raw_denominator": 27,
            "candidate_rows": 1010,
            "capture_hash_rows": 125,
            "complete_flag_days": 61,
            "complete_label_days": 52,
            "excluded_incomplete_flag_days": [
              "2026-06-01",
              "2026-06-02",
              "2026-06-03",
              "2026-06-04",
              "2026-06-05",
              "2026-06-08",
              "2026-06-09",
              "2026-06-10",
              "2026-06-11",
              "2026-06-12",
              "2026-06-15",
              "2026-06-16",
              "2026-06-17",
              "2026-06-18",
              "2026-06-22",
              "2026-06-23",
              "2026-06-24",
              "2026-06-25",
              "2026-06-26",
              "2026-06-29",
              "2026-06-30",
              "2026-07-01",
              "2026-07-02",
              "2026-07-03",
              "2026-07-06",
              "2026-07-07",
              "2026-07-08",
              "2026-07-09",
              "2026-07-10"
            ],
            "excluded_incomplete_label_days": [
              "2026-07-14",
              "2026-07-30",
              "2026-08-11",
              "2026-08-14",
              "2026-08-24",
              "2026-09-01",
              "2026-09-02",
              "2026-09-28",
              "2026-10-19"
            ],
            "fillability": {
              "False": 31,
              "None": 43,
              "True": 936
            },
            "signal_days": 90
          },
          "status": "descriptive_only_no_promotion"
        }
      ],
      "selection_records": [
        {
          "date": "2026-10-23",
          "evidence": {
            "path": "output/research/shortline_experiments/2026-10-23/fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76.json",
            "sha256": "fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76"
          },
          "status": "selection_recorded_outcomes_pending"
        }
      ],
      "invalid": [],
      "current_window_report_observed": true,
      "selection_days": 1,
      "portfolio_experiment_status": "not_established_by_selection_records",
      "promotion_eligible": false
    },
    "app_b_forward": {
      "status": "observed_model_accounts",
      "authority": 0,
      "source_sha256": "63c8c55919168eba748faebf67312b069fcb7f7b526400a0fdad42e3bd0fa82a",
      "source_path": "output/research/app_b_forward/performance.json",
      "source_reported_at": "2026-10-23T20:35:23.256346+08:00",
      "accounts": {
        "app_b_control": {
          "app_realized_profit": null,
          "cash": 100000.0,
          "drawdown_coverage": "complete_expected_dates",
          "eod_curve": {
            "2026-10-23": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-23T15:16:22.923840+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-23T07:16:22.923840+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "5543532915c603d0567492f0c0b64268edd0b500d3e8bf0ee3f409f25b5f73cf",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-23T07:16:22.923840+00:00",
                "pause_latched": false,
                "policy_id": "book_b_pilot_drawdown_10_20_v1",
                "reasons": [
                  "WITHIN_PILOT_LOSS_BUDGET"
                ],
                "review_required": false,
                "risk_nav_basis": "cash_plus_liquidation",
                "status": "NORMAL",
                "strategy_nav": null,
                "tracking_epoch_started_at": "2026-10-23T01:34:03.159255+00:00"
              },
              "source_sha256": "15d3c81a7eda593b3db2d5349722c61c94faebc4cce963f72e73eecc2d7695a8",
              "status": "marked"
            }
          },
          "estimated_fees": 0.0,
          "fee_status": "protocol_model_rate",
          "filled_orders": 0,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 100000.0,
          "missing_eod_dates": [],
          "net_model_return_pct": 0.0,
          "no_fill_orders": 1,
          "observed_eod_max_drawdown_pct": 0.0,
          "open_lots": 0,
          "partial_expired_orders": 0,
          "pending_orders": 0,
          "planned_orders": 1,
          "realized_model_pnl": 0.0,
          "reserved_cash": 0.0,
          "unknown_orders": 0,
          "valuation_observed_at": "2026-10-23T15:16:22.923840+08:00"
        },
        "mode_m": {
          "app_realized_profit": null,
          "cash": 100000.0,
          "drawdown_coverage": "complete_expected_dates",
          "eod_curve": {
            "2026-10-23": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-23T15:16:22.923840+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-23T07:16:22.923840+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "5543532915c603d0567492f0c0b64268edd0b500d3e8bf0ee3f409f25b5f73cf",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-23T07:16:22.923840+00:00",
                "pause_latched": false,
                "policy_id": "book_b_pilot_drawdown_10_20_v1",
                "reasons": [
                  "WITHIN_PILOT_LOSS_BUDGET"
                ],
                "review_required": false,
                "risk_nav_basis": "cash_plus_liquidation",
                "status": "NORMAL",
                "strategy_nav": null,
                "tracking_epoch_started_at": "2026-10-23T01:34:03.159255+00:00"
              },
              "source_sha256": "15d3c81a7eda593b3db2d5349722c61c94faebc4cce963f72e73eecc2d7695a8",
              "status": "marked"
            }
          },
          "estimated_fees": 0.0,
          "fee_status": "protocol_model_rate",
          "filled_orders": 0,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 100000.0,
          "missing_eod_dates": [],
          "net_model_return_pct": 0.0,
          "no_fill_orders": 1,
          "observed_eod_max_drawdown_pct": 0.0,
          "open_lots": 0,
          "partial_expired_orders": 0,
          "pending_orders": 0,
          "planned_orders": 1,
          "realized_model_pnl": 0.0,
          "reserved_cash": 0.0,
          "unknown_orders": 0,
          "valuation_observed_at": "2026-10-23T15:16:22.923840+08:00"
        },
        "no_kol": {
          "app_realized_profit": null,
          "cash": 100000.0,
          "drawdown_coverage": "complete_expected_dates",
          "eod_curve": {
            "2026-10-23": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-23T15:16:22.923840+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-23T07:16:22.923840+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "5543532915c603d0567492f0c0b64268edd0b500d3e8bf0ee3f409f25b5f73cf",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-23T07:16:22.923840+00:00",
                "pause_latched": false,
                "policy_id": "book_b_pilot_drawdown_10_20_v1",
                "reasons": [
                  "WITHIN_PILOT_LOSS_BUDGET"
                ],
                "review_required": false,
                "risk_nav_basis": "cash_plus_liquidation",
                "status": "NORMAL",
                "strategy_nav": null,
                "tracking_epoch_started_at": "2026-10-23T01:34:03.159255+00:00"
              },
              "source_sha256": "15d3c81a7eda593b3db2d5349722c61c94faebc4cce963f72e73eecc2d7695a8",
              "status": "marked"
            }
          },
          "estimated_fees": 0.0,
          "fee_status": "protocol_model_rate",
          "filled_orders": 0,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 100000.0,
          "missing_eod_dates": [],
          "net_model_return_pct": 0.0,
          "no_fill_orders": 1,
          "observed_eod_max_drawdown_pct": 0.0,
          "open_lots": 0,
          "partial_expired_orders": 0,
          "pending_orders": 0,
          "planned_orders": 1,
          "realized_model_pnl": 0.0,
          "reserved_cash": 0.0,
          "unknown_orders": 0,
          "valuation_observed_at": "2026-10-23T15:16:22.923840+08:00"
        },
        "open_limit": {
          "app_realized_profit": null,
          "cash": 100000.0,
          "drawdown_coverage": "complete_expected_dates",
          "eod_curve": {
            "2026-10-23": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-23T15:16:22.923840+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-23T07:16:22.923840+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "5543532915c603d0567492f0c0b64268edd0b500d3e8bf0ee3f409f25b5f73cf",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-23T07:16:22.923840+00:00",
                "pause_latched": false,
                "policy_id": "book_b_pilot_drawdown_10_20_v1",
                "reasons": [
                  "WITHIN_PILOT_LOSS_BUDGET"
                ],
                "review_required": false,
                "risk_nav_basis": "cash_plus_liquidation",
                "status": "NORMAL",
                "strategy_nav": null,
                "tracking_epoch_started_at": "2026-10-23T01:34:03.159255+00:00"
              },
              "source_sha256": "15d3c81a7eda593b3db2d5349722c61c94faebc4cce963f72e73eecc2d7695a8",
              "status": "marked"
            }
          },
          "estimated_fees": 0.0,
          "fee_status": "protocol_model_rate",
          "filled_orders": 0,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 100000.0,
          "missing_eod_dates": [],
          "net_model_return_pct": 0.0,
          "no_fill_orders": 1,
          "observed_eod_max_drawdown_pct": 0.0,
          "open_lots": 0,
          "partial_expired_orders": 0,
          "pending_orders": 0,
          "planned_orders": 1,
          "realized_model_pnl": 0.0,
          "reserved_cash": 0.0,
          "unknown_orders": 0,
          "valuation_observed_at": "2026-10-23T15:16:22.923840+08:00"
        }
      },
      "calendar_coverage": {
        "observed_through": "2026-10-23",
        "report_date": "2026-10-23",
        "status": "covered_through_report_date",
        "unproved_tail": null
      },
      "app_plan_comparisons": [
        {
          "app_receipt_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/runs/history/2026-10-23-e686872736b5.json",
          "app_receipt_sha256": "b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd",
          "app_run_id": "2026-10-23-e686872736b5",
          "fill_or_return_equivalence": "not_established",
          "first_divergence": "account_allocation",
          "left_sha256": "019835e53387f07c6fac806bb62e42a3c83e63c7aa0d42965f2ec3aaae94e7df",
          "research_event_sha256": "1c74b02ca089aa0dc1e7a04e4376dcd59e6673bb509d8c795f762a55f036cc3b",
          "right_sha256": "955198df464af77a10a1a8e992f4a2e62ddd9f4eb75bce5ecfad958781c8034d",
          "same_order_economics": false,
          "status": "compared",
          "trade_date": "2026-10-23"
        }
      ],
      "missing_morning_dates": [],
      "consumed_morning_days": [
        "2026-10-23"
      ],
      "promotion": "PROPOSAL_ONLY"
    },
    "missing_evidence": [
      "reference/experience/xiaocao_hypotheses.jsonl",
      "saved_three_option_paired_comparison_missing"
    ],
    "exploration_proposals": [
      {
        "experiment_id": "weekly-evidence-2026-10-23-paired-options",
        "objective": "冻结同一候选、预算与 OOS 分割，比较无 KOL / 有界 KOL / 挑战者",
        "falsifier": "费用后改善不能在 OOS 保留，或只由单周/单赢家/缩仓解释",
        "required_evidence": [
          "expected_sample_ids",
          "frozen_candidates_sha256",
          "selection/outcome clocks",
          "three-option net costs"
        ],
        "status": "proposed_not_run",
        "owner": "weekly research owner",
        "next_review": "2026-10-30",
        "rollback": "retain current strategy; remove only isolated research experiment artifacts",
        "auto_apply_eligible": false
      },
      {
        "experiment_id": "weekly-evidence-2026-10-23-proxy-fill",
        "objective": "量化缺分钟窗口及实时重试代理对纸面结论的敏感度",
        "falsifier": "剔除代理后样本不足或优势消失，则不能称为已确认可执行改善",
        "required_evidence": [
          "saved fill basis/fallback",
          "same-cohort confirmed-window sensitivity",
          "missing-window counts"
        ],
        "status": "proposed_not_run",
        "owner": "weekly research owner",
        "next_review": "2026-10-30",
        "rollback": "retain current strategy; remove only isolated research experiment artifacts",
        "auto_apply_eligible": false
      },
      {
        "experiment_id": "weekly-evidence-2026-10-23-cashflow-time",
        "objective": "分账户验证资金划拨、费用与延迟对收益的影响",
        "falsifier": "无法闭合净投入/净值/费用或缺自然运行时刻，则不认定收益或速度提升",
        "required_evidence": [
          "dated accounting statements",
          "capital flow chain",
          "source/decision/order/fill timestamps"
        ],
        "status": "proposed_not_run",
        "owner": "weekly research owner",
        "next_review": "2026-10-30",
        "rollback": "retain current strategy; remove only isolated research experiment artifacts",
        "auto_apply_eligible": false
      }
    ],
    "promotion": {
      "auto_promote": false,
      "writes_verdict_ledger": false,
      "changes_strategy": false
    },
    "limitations": [
      "saved observations are not independent broker/source verification",
      "A/B identical-entry exit difference is descriptive exit evidence, never KOL selection alpha",
      "overlapping 1/4/12-week windows are not independent OOS samples",
      "cash movements are not profit; absent accounting and actual fees remain unknown"
    ]
  }
}
```
