# 小草每周深度复盘 2026-10-02

## 先看结论

- 本周学到：来源叙事须用当日触发和反证核对；本周中性KOL与重叠4/12周样本不能证明收益，三个旧实验均未运行。
- 已沉淀：三个稳定实验明确证伪与点时证据；修复周度休市/违规结算漏报、周报暂存/提交边界及逐文件账本清单，未改变策略或资金。
- 重点看：两个未决SELL与下一合法日验证；九项泛化工具建议合为取证提案，缺点时、费用、成交及OOS证据，暂不能自动推广。
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个；另有 1 条本地工作区提醒，见下一节。
- APP 执行故障复核：未结计划 2，阻断检查点 3，缺失 EOD 0，缺失结算日 3，缺失日复盘 0；逐项核对卖价/买盘/成交窗口及后续买入影响，不能只归为外部状态。
  - 未结 `book-b:2026-09-18:000572.XSHE:SELL:087c4339d890`：unknown / NATIVE_HISTORICAL_STATUS_UNPROVEN；委托 6007019；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=12ba128fadf78258c1dd117dcb48c48064e865f67cde0c156eb0964689778ad2）
  - 未结 `book-b:2026-09-30:301382.XSHE:SELL:9c1cb5e059e5`：unknown / NATIVE_HISTORICAL_EXACT_ORDER_NOT_UNIQUE；委托 6004811；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=12ba128fadf78258c1dd117dcb48c48064e865f67cde0c156eb0964689778ad2）
  - 缺失结算：2026-09-28, 2026-09-29, 2026-09-30
  - 原结算不可采纳 `2026-09-28`：ORIGINAL_EOD_NONTERMINAL_EXECUTION；原件保留，未决计划 book-b:2026-09-18:000572.XSHE:SELL:087c4339d890
  - 日历证明休市，无应结算义务：2026-10-01, 2026-10-02
- 执行事故复核：两条旧SELL分别UNKNOWN；09-28原结算不可采纳，09-29/30缺结算；10-01/02休市免应结算。独立后来filled不能关闭旧单，full-read和未实现sellable-only分开。
- 当前修复负责人：xiaocao-weekly-deep-review / 01a0fc99-7f2d-7502-b994-2e5a9491f3a7；验收边界：下一自然weekly验证汇总；下一合法交易日验证稳定paper EOD与fresh APP post-close/strict settlement；外部精确终态、sell-only端口及其E2E仍未证明。
- 完整订单、任务轨迹、5 Why 与修复证据：[执行复核](/Users/xuanyue202/Documents/project/xiaocao/docs/reviews/2026-10-02-weekly-execution-review.md)。
- 整体框架复盘（有证据引用的分析，非收益认证）：保留§2a有界判断的来源忠实、独立审核、时效及交易硬门，细化点时取证；仅在authority=0隔离研究中挑战原★E/模式入口，不改正式策略、资金或退出。1周(9/26–10/2)交易观测只到9/30，10/1–2休市；9/29–30六个已审live/paper稀疏包均中性（buy_scale=1、skip/exit为空、无v2模式跟随），无证据证明它们创造或损失收益。9/29当日上涨宽度反证直接外推9/28普跌，财富值2000边界、匿名公司及个股退出条件仍缺精确当下触发；这是审阅反证，非避免损失的可量化收益。live:B与paper:B的风险观测（1周16/24条）缺同口径首尾结算、资本流和完整实际费用，不能计算归因收益、回撤或资金效率。9/30 APP dated statement 的较晚观测为marked NAV 53,372.04、净投入54,462.04、已实现-846.21、未实现-236.39，现金未分类差额-7.40、累计PnL为N/A、退出费仅按计划估计0.36；旧mark不得充作10/2结算。纸盘1周B入场cohort 4笔、已闭3笔，A/B同入口退出仅2对，B-A均值约-0.031个百分点；4周9对约-0.162个百分点，12周37对约+0.527个百分点，窗口重叠、闭仓选择和旧成交窗口时效缺口使之只可描述退出，绝非KOL alpha。纸盘费是模型费，APP真实费、执行漏损、错失上涨、现金时间积分均未闭合；低仓位还可能来自入口/模式、风险与结算、整手或订单障碍，不能单因果归KOL。4周与12周KOL库存同为9月以来43包及418份context；7–8月没有完整KOL决策覆盖，12周不是独立长期验证。10/2 context虽有215份登记report、185个current观点，但正文未载、远端全量发现不可用，含同源关系/回填，不是185个独立即时信号；9/30之后无已发布新决策。现有请求/审核/发布时间不能分解模型耗时，消费引用也不闭合到成交。三个稳定实验ID在本周无可核验的点时配对run、反证或回滚；固定option_comparison为空，旧研究REJECTED与缺费用成交链不能转成新PASS。no-KOL、现行bounded和预注册入口/模式challenger均证据不足。下次用同freeze、同本金/风险、合法时点、整手、流动性、T+1、费用和退出构建OOS配对，同时量化净收益、回撤左尾、现金时间积分、漏损与错失上涨，按作者事件/日期聚类并剔除单一赢家。休市且缺下次开盘当下事实，本周审阅不生成交易decision。
- 结论证据：`output/live/flywheel_change_ledger.jsonl`（sha256=5b04451dc97b27757ae73f96ecfbf1a2f53c73232a30d9e7534cf074bd51660a）；`output/live/book_b_live_execution/book_b_live_decisions.jsonl`（sha256=cb647858fa6df80f1e796da538523c133687c05795b899dbf8b7d30791553350）；`output/live/kol_policy/account_risk/live_B.jsonl`（sha256=7890c87f88054fafed6fd4449dcf90f103d5707d679ffaad0a00f93ac9584fa0）；`output/live/book_b_live_execution/runs/2026-09-29.json`（sha256=4e19aa97f4feb7aeb064b524b55742dd1019e8d2d4f3e475dc8b3b5311f095cb）；`output/live/book_b_live_execution/runs/2026-09-30.json`（sha256=51f81171e752a14bd01986a4879a61d6001607c8563f60b531fc205d182f9269）；`output/live/kol_policy/decisions/kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1.json`（sha256=2b1344f9c406f1f7643ef0bc9cb95e14ea2ebe4f54335fe0ccbedd69b2d9d5a3）；`output/live/kol_policy/decisions/kol-b-paper-20260916-morning-pause-astra-v1.json`（sha256=0b1552c2b5b3ed1fb98b77b25f89efa6d8298abcbf9730752f47b95209323d13）；`output/live/kol_policy/decisions/kol-b-live-sparse-20260929-1025-neutral-7f33dfd2-v1.json`（sha256=23304a2c7d3863144976289ad2156af9bf4c7d110637c0accb06bac6248b9fd3）；`output/live/kol_policy/decisions/kol-b-live-sparse-20260929-1325-neutral-8156af63-v1.json`（sha256=05fbbd5aa16354ed2f481da3aeab952e097e570478bfb98b0f5073619c6cf5a4）；`output/live/kol_policy/decisions/kol-b-live-sparse-20260930-1025-neutral-4f559e49-v1.json`（sha256=a0bb81a0f0b6c3a3408c973d9730854c6a1192cffcaa0ae12551f8a07ccdab6e）；`output/live/kol_policy/decisions/kol-b-paper-sparse-20260930-1025-neutral-4f559e49-v1.json`（sha256=b9738643602a9f80ed2d0b348a0172c03b70055a3b6f60d59a0b794a17b2a0f1）；`output/live/kol_policy/context/ad67ab2a53ef79f636cf319d552fd6930c23f0a40b2fb8336286f242f3505059.context.json`（sha256=5cf9a446bd89948795405db0de08958835dbb4cc94f714681b3b355c1b368d47）；`output/live/kol_policy/context/295f3e9c726a363871e36f2563405243c93d103c243945343d09d3c33e7b65fc.context.json`（sha256=2cfc809cbc115d3fb257b1a61c26b0d7b7d3f3e9014a0f6c403300132af0ca49）
- 待核证据：1/4/12周同口径首尾NAV、应结算日、资本划拨链及APP实际费用；10/2不能复用9/30标记；同freeze的三方案点时可成交配对及入口前后完整队列、拒绝理由、整手/报价/流动性/T+1/退出、费用、风险暴露、OOS与失败样本；固定比较为空；paper consumption缺失/28文件不可解析、live独立consumption日志缺失；需来源→审核→首次合法消费→原plan→订单成交结算；UNKNOWN保留未决；9/30未分类现金-7.40与未决订单、旧结算的独立归因，不能折成KOL PnL或机会成本；远端未登记来源完整发现、被引报告正文点时回读、观点关系/作者事件去重及分类回填时序；模型请求开始/完成、审核、发布、到期、第一合法动作时钟；现有时长不足以诊断系统性模型迟延；10/1–2休市且缺下次交易日新鲜行情、账户、可卖量和freeze，不产生未来开盘判断；reference/experience/xiaocao_hypotheses.jsonl固定捕获字节状态invalid（多行非JSON）；不能把该候选假设库当作可解析研究输入
- 比较框架：无 KOL 基线 / 现行有界 KOL / 挑战者；分别检查入口过滤、模式和资金利用率。
- 纸实逐账户分开；1/4/12 周重叠窗口不是独立样本。小样本不宣称因果胜率或稳定收益，不自动推广实盘。
- 旧试验跟进：3 项需先复核（历史状态仅为报告声明），再决定本周最多三个槽位；不自动启动。

## 数据证据与方案比较

- 输入清单 sha256=`9ed5036c7f8cac2c0b2cf277c1e6e644933db7684234531faf1d308b79638785`；捕获 88 个文件；缺失模式 2 项。
- 结论只约束已保存样本，不自动升级策略；配对 A/B 出场差不解释为 KOL 选股 alpha。

| 比较 / 方案 | 结论 | 样本 | 净收益均值 | 成本均值 | OOS | 判断/执行秒 |
|---|---|---:|---:|---:|---|---|
| 未提供 / baseline_no_kol | 证据不足 | N/A | N/A | N/A | N/A | N/A/N/A |
| 未提供 / current_bounded | 证据不足 | N/A | N/A | N/A | N/A | N/A/N/A |
| 未提供 / kol_challenger | 证据不足 | N/A | N/A | N/A | N/A | N/A/N/A |

### 已记录假设与研究运行

- `A_kp_star`：历史记录 REJECTED（2026-10-02T20:32:09）；本次复核 证据不足；n_days=78，train/test=0.839962/0.736789。
- `B_vb_star`：历史记录 REJECTED（2026-08-28T15:25:16）；本次复核 证据不足；n_days=60，train/test=0.196744/2.214262。
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

- 12w：独立入场 87，记录窗口标签 87（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- 1w：独立入场 9，记录窗口标签 9（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- 4w：独立入场 26，记录窗口标签 26（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- APP 已保存会计观测 5 份；资金划拨不计利润，缺完整净值/现金流/实际费用时不计算账户收益。
- 会计观测 2026-09-29T07:46:17.739000+00:00：净投入 54462.04，标记净值 53704.28，累计盈亏 -757.76，已实现/浮动 -1329.59/571.83；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-09-29T07:46:17.739000+00:00：净投入 54462.04，标记净值 53704.28，累计盈亏 -757.76，已实现/浮动 -1329.59/571.83；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-09-29T07:46:17.739000+00:00：净投入 54462.04，标记净值 53704.28，累计盈亏 -757.76，已实现/浮动 -1329.59/571.83；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-09-30T07:22:21.651000+00:00：净投入 54462.04，标记净值 53372.04，累计盈亏 N/A，已实现/浮动 -846.21/-236.39；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-09-30T06:51:01.818000+00:00：净投入 54462.04，标记净值 53398.04，累计盈亏 N/A，已实现/浮动 -846.21/-210.39；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。

生产纸盘观察截至 2026-10-02；最新原记录日期 2026-09-30，相距 2 个自然日。
有效仓 204、未知仓 17、坏记录 0、未成熟仓 4；旧日期/naive 时钟缺时区与可用时点证明。
Book A：有效/闭仓 90/90；有效子集模型买费 178.26，卖费 181.57，闭仓现金净变动 32622.24。
Book B：有效/闭仓 103/102；有效子集模型买费 205.69，卖费 205.93，闭仓现金净变动 33529.65。
Book T：有效/闭仓 11/8；有效子集模型买费 10.03，卖费 7.02，闭仓现金净变动 -1010.90。
同进场 A/B 闭仓配对 50，B−A均值 0.5720 pp；有效分组排除 54（开放 1、未匹配 15、进场不一致 38）；另有未知仓 17。
12w 进场窗口 2026-07-11–2026-10-02：有效 87；最新数据在窗口前=False。
1w 进场窗口 2026-09-26–2026-10-02：有效 9；最新数据在窗口前=False。
4w 进场窗口 2026-09-05–2026-10-02：有效 26；最新数据在窗口前=False。
以上仅为原始现金事实的描述性观察，非组合NAV、APP成交或KOL增益；闭仓选择偏差与未成熟删失仍在。

### 下一步探索（提案，未运行）

- `weekly-evidence-2026-10-02-paired-options`：冻结同一候选、预算与 OOS 分割，比较无 KOL / 有界 KOL / 挑战者；证伪：费用后改善不能在 OOS 保留，或只由单周/单赢家/缩仓解释；负责人 weekly research owner；复核 2026-10-09；回滚 retain current strategy; remove only isolated research experiment artifacts。
- `weekly-evidence-2026-10-02-proxy-fill`：量化缺分钟窗口及实时重试代理对纸面结论的敏感度；证伪：剔除代理后样本不足或优势消失，则不能称为已确认可执行改善；负责人 weekly research owner；复核 2026-10-09；回滚 retain current strategy; remove only isolated research experiment artifacts。
- `weekly-evidence-2026-10-02-cashflow-time`：分账户验证资金划拨、费用与延迟对收益的影响；证伪：无法闭合净投入/净值/费用或缺自然运行时刻，则不认定收益或速度提升；负责人 weekly research owner；复核 2026-10-09；回滚 retain current strategy; remove only isolated research experiment artifacts。

## 需要你看/确认的事项

- **需要确认** `weekly-2026-10-02-point-in-time-evidence`：先补三方案点时与费用成交证据，再评估框架和九项观测建议
- **本地工作区提醒，不是策略判断**：有 3 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl, src/xiaocao/live/app_test_window.py, tests/test_app_preopen_grant.py。

## 这批转录给我的启发
- **2026-09-29 盘前大师班直播（含盘中跟踪）（2026-09-29_xiaocao_morning_kol356848c22a78.json）**
  启发：小草把短线交易拆成环境、模式、时点和退出四层：先等9:25后的竞价结果，再在连板环境尚可时按既定模式处理二板以上接力；昨日涨停而次日低开属于不及预期，但退出细节按对象区分，三羊马示例是先减半、反抽再处理，博通集成示例是直接退出。趋势股可在走势流畅时保留半仓或三分之一仓位沿五日线跟随。房地产观点来自万科等中军及短线标的的盘面表现，并延伸为国庆节前可能出现政策利好的主观预期；实际发言日期和年份未证实，现有市场证据只核验2026年交易日历，…
  姿态：proposal_only：房地产观点的来源期限写作国庆节前，但实际发言日期和年份未证实；当前交易日历、行情和政策不足以确认其仍在有效期，不自动更新现行姿态。
  打法：proposal_only：保留不及预期退出、早段时点边界、五日线部分留仓和模式优先于板块猜测四类方法候选，未经研究与人审不晋级。
  待验证：six_authority_0_candidates：形成六条可证伪候选；已与XH-091、XH-121、XH-137、XH-175及裁决账本中的XH-011比较，未发现完全同义重复，尚未研究验证或入库。
  命中审计：完整读取并绑定60个稳定段；所有盘面、证券、政策与收益主张均保持来源归属，广告段未进入投资结论。
  工具缺口：先证实实际发言日期与年份，再补齐本场9:20、9:25、9:30:20、9:30:45、9:31和9:33等观测点的竞价与盘中快照、候选首次出现时间、分数、初始涨幅、可成交价、退出、费用、本地推荐和正式房地产政策公告。
- **2026-09-29 处理日2026-09-29：真实发言日未核实的国庆节前大师班复盘（2026-09-29_xiaocao_review_kol02051c71f196.json）**
  启发：小草在一场真实日期未核实的节前直播中，把发言时行情判断为指数偏弱但短线情绪尚未退潮的轮动期，并提出相对周一修复、周二分歧、周三再修复的路径。可复用内容是环境与模式匹配、评分与反馈门控、按对象拆分的退出条件、环境分层卖出和差环境允许空仓。轮动仓位原句“你就两周三滚动”不能可靠还原为股票只数或仓位成数。所有内容均为authority=0候选，不更新当前姿态、参数或交易。
  姿态：none；真实发言日与当前行情未核实，且现行姿态证据已过期，本次不写入确定性当前姿态。
  打法：candidate_only；研究对象化退出、环境分层、看一做二和空仓权，不自动修改规则。
  待验证：proposed_4_authority_0_candidates；退潮识别延迟、环境分层退出、节前效应和差环境空仓，均完成既有XH邻近去重说明。
  命中审计：逐字稿SHA-256为2079d6e3e70672b7e0bf363c538fff6aae83e8816c2b533d9577a3ee3b68aedd；93个稳定段已逐段复核。
  工具缺口：保存可靠发言时间、逐日环境标签、模式评分、完整候选、实际入出场、不可成交、成本、容量、左尾和纪律违约；单独统计国庆前最后三个交易日。
- **2026-09-30 节前大师班直播（2026-09-30_xiaocao_morning.json）**
  启发：小草把节前退潮与空仓环境下的短线决策拆成三层：先用高开广度、量能和环境状态约束仓位；再在下跌低吸、倒接力、紫薇和红盘起爆之间按环境选择；最后用低涨幅与高分排名筛选盘中候选。他明确说严格低于六个百分点的阈值来自感觉、尚无数据，并提出用自动监控替代人工盯盘。直播排名与收益未获独立验证则是系统核验限制。全部内容仅形成 authority=0 的研究候选。
  姿态：candidate_only：来源可作为小草阶段性姿态候选，但具体盘中窗口已过，下一交易日前需重新核验。
  打法：proposal_only：高开广度分层、六个百分点涨幅边界、模式排序和高分监控均需研究与人审。
  待验证：six_authority_0_candidates：三条复用XH-137、XH-154、XH-138的exact claim并补充本场细化，另形成三条可证伪候选；全部未验证、未入库。
  命中审计：完整读取并绑定39个稳定段；证券身份仅采用绑定盘后事实，直播排名、分数、历史收益和卖点保持未核验。
  工具缺口：冻结9:25高开家数、环境状态、候选排名与分数、当时涨幅、发现延迟、可成交价格、退出、费用和账户回执，做前瞻对照。
- **2026-09-30 2026-09-30小草国庆前大师班晚间复盘（2026-09-30_xiaocao_review.json）**
  启发：可复用内容是：空仓环境不做模式切换；若交易者已经绕开这条规则且仍在赚钱，只把第一次亏损作为这条越规执行链的停止点，不能外推为正常模式亏一笔即停；广泛高开且易高开低走时，低吸和倒接力的赔率下降，盘中起爆及下跌、超跌方向相对优先；早盘高分必须绑定观察秒点与当时涨幅，阈值会随时间快速变化，现有100分、200分等口述值尚未测试；尾盘只研究轮动下跌、热门板块回撤而龙头抗跌的窄条件；快速涨停是否开板决定退出分支。以上均为authority=0候…
  姿态：none；来源的节后基准只进入待重验观点，不更新确定性当前姿态。
  打法：candidate_only；保留空仓模式边界、时间涨幅双门槛、尾盘四条件和封板/开板退出分支。
  待验证：XH-190 exact reproduction；XH-192 one material refinement；新增2个authority=0候选。
  命中审计：完整逐字稿SHA-256为a8b86d5c75fca65f2574861bc4e4a95ee3539664e2a499dbd95b19f3dbedd86b；189个稳定段逐段复核。运行时审计仅保留不构成逐秒命中或本地成交复现的边界结论。
  工具缺口：保存逐秒未过滤评分、算法版本、当时涨幅、首次发现、可成交价、退出、失败样本、开盘广度、环境标签与规则内外状态。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-09-29 2026-09-29_xiaocao_morning_kol356848c22a78.json: proposal_only：房地产观点的来源期限写作国庆节前，但实际发言日期和年份未证实；当前交易日历、行情和政策不足以确认其仍在有效期，不自动更新现行姿态。
  - 2026-09-29 2026-09-29_xiaocao_review_kol02051c71f196.json: none；真实发言日与当前行情未核实，且现行姿态证据已过期，本次不写入确定性当前姿态。
  - 2026-09-30 2026-09-30_xiaocao_morning.json: candidate_only：来源可作为小草阶段性姿态候选，但具体盘中窗口已过，下一交易日前需重新核验。
  - 2026-09-30 2026-09-30_xiaocao_review.json: none；来源的节后基准只进入待重验观点，不更新确定性当前姿态。
- **Playbook/纪律**
  - 2026-09-29 2026-09-29_xiaocao_morning_kol356848c22a78.json: proposal_only：保留不及预期退出、早段时点边界、五日线部分留仓和模式优先于板块猜测四类方法候选，未经研究与人审不晋级。
  - 2026-09-29 2026-09-29_xiaocao_review_kol02051c71f196.json: candidate_only；研究对象化退出、环境分层、看一做二和空仓权，不自动修改规则。
  - 2026-09-30 2026-09-30_xiaocao_morning.json: proposal_only：高开广度分层、六个百分点涨幅边界、模式排序和高分监控均需研究与人审。
  - 2026-09-30 2026-09-30_xiaocao_review.json: candidate_only；保留空仓模式边界、时间涨幅双门槛、尾盘四条件和封板/开板退出分支。
- **候选假设**
  - 2026-09-29 2026-09-29_xiaocao_morning_kol356848c22a78.json: six_authority_0_candidates：形成六条可证伪候选；已与XH-091、XH-121、XH-137、XH-175及裁决账本中的XH-011比较，未发现完全同义重复，尚未研究验证或入库。
  - 2026-09-29 2026-09-29_xiaocao_review_kol02051c71f196.json: proposed_4_authority_0_candidates；退潮识别延迟、环境分层退出、节前效应和差环境空仓，均完成既有XH邻近去重说明。
  - 2026-09-30 2026-09-30_xiaocao_morning.json: six_authority_0_candidates：三条复用XH-137、XH-154、XH-138的exact claim并补充本场细化，另形成三条可证伪候选；全部未验证、未入库。
  - 2026-09-30 2026-09-30_xiaocao_review.json: XH-190 exact reproduction；XH-192 one material refinement；新增2个authority=0候选。
- **命中审计**
  - 2026-09-29 2026-09-29_xiaocao_morning_kol356848c22a78.json: 完整读取并绑定60个稳定段；所有盘面、证券、政策与收益主张均保持来源归属，广告段未进入投资结论。
  - 2026-09-29 2026-09-29_xiaocao_review_kol02051c71f196.json: 逐字稿SHA-256为2079d6e3e70672b7e0bf363c538fff6aae83e8816c2b533d9577a3ee3b68aedd；93个稳定段已逐段复核。
  - 2026-09-30 2026-09-30_xiaocao_morning.json: 完整读取并绑定39个稳定段；证券身份仅采用绑定盘后事实，直播排名、分数、历史收益和卖点保持未核验。
  - 2026-09-30 2026-09-30_xiaocao_review.json: 完整逐字稿SHA-256为a8b86d5c75fca65f2574861bc4e4a95ee3539664e2a499dbd95b19f3dbedd86b；189个稳定段逐段复核。运行时审计仅保留不构成逐秒命中或本地成交复现的边界结论。
- **工具/流程提案**
  - 2026-09-29 2026-09-29_xiaocao_morning_kol356848c22a78.json: 先证实实际发言日期与年份，再补齐本场9:20、9:25、9:30:20、9:30:45、9:31和9:33等观测点的竞价与盘中快照、候选首次出现时间、分数、初始涨幅、可成交价、退出、费用、本地推荐和正式房地产政策公告。
  - 2026-09-29 2026-09-29_xiaocao_review_kol02051c71f196.json: 保存可靠发言时间、逐日环境标签、模式评分、完整候选、实际入出场、不可成交、成本、容量、左尾和纪律违约；单独统计国庆前最后三个交易日。
  - 2026-09-30 2026-09-30_xiaocao_morning.json: 冻结9:25高开家数、环境状态、候选排名与分数、当时涨幅、发现延迟、可成交价格、退出、费用和账户回执，做前瞻对照。
  - 2026-09-30 2026-09-30_xiaocao_review.json: 保存逐秒未过滤评分、算法版本、当时涨幅、首次发现、可成交价、退出、失败样本、开盘广度、环境标签与规则内外状态。

## 上期试验与失败跟进（先于新增试验，未记录不等于完成）

- `weekly-2026-09-11-baseline_no_kol`：逐 Book/runtime 重建同日冻结、同整手/风险预算/退出约束的 no-KOL 与现行叠加配对路径；先量化是否存在真实可执行的 KOL 增量，再比较费后收益、左尾、回撤、暴露和现金时间积分。
  - 历史状态：needs_evidence_and_design；本周复核状态：reviewed；原复核日：2026-10-02。
  - 跟进结论（报告声明）：9月16日 live 早盘旧 pause 已过期并回基线，9月17日同样过期且价格门跳过一只；9月21至23日 live 早盘分别受 native 解锁、历史 SELL 未决和 dated freeze 证据阻断，均无可归给 KOL 的新买决策。纸盘已有风险标记，但固定库存的 paper consumption 源缺失，不能用纸盘成交计数推出叠加收益。上期截至9月18日的配对账试验在本库存仍无运行/回滚回执；旧试验继续，原来9月25日复核已逾期。
  - 回滚：本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-27；state sha256=fd2b685b39f31e88f623bace5fc0ee9dfeecfd2b6c18c06a68f6edb335a389b3。
- `weekly-2026-09-11-current_bounded`：检验已审阅的有界暂停和中性判断是否在第一合法动作前被消费，并以同风险暴露、同费用反事实衡量减少损失与错失上涨；把来源、模型、审阅、发布、过期和执行延迟分开。
  - 历史状态：needs_evidence_and_design；本周复核状态：reviewed；原复核日：2026-10-02。
  - 跟进结论（报告声明）：9月15日有界 pause 的审核说明当时 freeze 两行均 COLD/非★E，未产生增量订单；9月16日纸盘包明确在两笔基线买入之后发布，live 早盘旧包过期且 rendezvous 超时。9月18日中性包承认八行均 COLD/UNKNOWN。9月21至23日虽有新登记语义，但无新已发布交易判断，旧9月18日包的引用已过期。固定清单没有模型起止遥测、完整 paper consumption 或费用/成交配对，不能把临时暂停称作尾部收益；上期试验未见可核验运行或回滚，须细化时钟与归因。
  - 回滚：本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-27；state sha256=fd2b685b39f31e88f623bace5fc0ee9dfeecfd2b6c18c06a68f6edb335a389b3。
- `weekly-2026-09-11-kol_challenger`：在 authority=0 隔离研究队列预先定义竞价、9:31 与盘中机会集，检验原入口和模式筛选是否遗漏合法、可成交且有风险调整价值的候选；与 no-KOL 和有界叠加作同本金配对。
  - 历史状态：needs_evidence_and_design；本周复核状态：reviewed；原复核日：2026-10-02。
  - 跟进结论（报告声明）：9月23日登记上下文有183个报告索引但正文全未载入；118条带 current 状态的观点包含回填/同源重复，不能视作118个独立即时信号。小草9月19日谈早盘低吸窗口、评分不保证与退潮限制，刘少9月21日撤回节前减仓又缺消息名称及期限；这构成需点时核验的竞争假设，不是扩大 Book B 入口的授权。固定清单没有入口外完整候选、成交反事实或 OOS；上期挑战者仍未运行，维持 authority=0 研究设计。
  - 回滚：本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-27；state sha256=fd2b685b39f31e88f623bace5fc0ee9dfeecfd2b6c18c06a68f6edb335a389b3。

## 整体框架试验槽位（待取证与设计，不是合格变更候选）

- 目标：分开live:B与paper:B，在同日不可变freeze、同本金风险、整手、合法时点与退出下配对no-KOL和现行overlay；预注册OOS，测费后收益、左尾/回撤、暴露、现金时间积分及可成交错失上涨。
  - 证伪条件：若多日期/独立来源事件的点时费后配对显示KOL改善净收益或左尾，剔除单一赢家且同风险暴露后仍成立，则推翻基线足以解释账户结果；缺证据不判定。
  - 必要证据：每日完整freeze、资格和模式；消费、intent/claim、实际订单/成交/费用、T+1、报价；UNKNOWN保持未决；同本金/风险/整手/时点/退出no-KOL与current配对，完整结算NAV、资本流、现金时间积分、漏损与错失上涨；预注册OOS、失败样本、作者事件/模式/市场阶段聚类、单一赢家剔除与成本敏感性；分开1/4/12周实际覆盖
  - 回滚：本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。
  - 本次跟进（报告声明）：旧账本截至9/27仅登记设计；本轮固定option_comparison为空，没有新的no-KOL/current点时配对run或回滚回执。9/29–30中性包和风险读数仅证实覆盖/观测，APP结算及纸盘消费链仍缺，不能确认收益增量或实验完成。
  - 负责人：xiaocao weekly research maintainer；隔离执行仍需既有研究门指定；下次复核：2026-10-09。
- 目标：检验有界pause/中性包是否在第一合法动作前被消费并改变原计划；分解来源、模型、审核、发布、过期和native/订单迟延，配对量化避免损失与错失上涨。
  - 证伪条件：若多数pause没有当时合法新增风险机会、发布晚于动作或到期，或费后错失收益/执行漏损抵消左尾改善，则不支持叠加增益；中性包计数不算收益。
  - 必要证据：source published/received、请求及模型开始/完成、独立审核、发布、到期、第一合法消费、原plan/订单/成交/结算全时钟；逐pause的freeze资格、账户现金/风险、报价、流动性、整手、T+1；仅合法机会计机会成本；live/paper分开核实际费用、净避免损失/错失上涨、现金时间积分和左尾；按作者事件去重并保存反证
  - 回滚：本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。
  - 本次跟进（报告声明）：9/15–16旧pause未见本轮新增收益归因或实验run；9/29–30六包中性且无跳过、退出或模式跟随。9/29宽度反证旧日普跌直接外推，但没有合法消费至成交的配对链，不能登记为避免损失。财富值/匿名代码触发仍未证，未见回滚。
  - 负责人：xiaocao weekly research maintainer；lineage补证由原生产/消费owner协作；下次复核：2026-10-09。
- 目标：authority=0隔离研究预注册竞价、9:31和有限盘中截面，检验★E/模式入口遗漏合法可成交候选，并与no-KOL/current同本金、风险、费用和退出OOS配对。
  - 证伪条件：若完整点时队列在整手、费用、流动性、T+1、退出及OOS约束后不能同时改善机会覆盖与风险调整结果，或优势来自事后补榜/回填/同源重复/单一赢家，则拒绝；缺数据不判PASS。
  - 必要证据：入口前后完整候选、每条拒绝理由、模式/评分版本和当时可见时间；区分COLD、UNKNOWN、BJSE与真正入口外研究行；预注册合法截面与同本金/风险/费用/整手/流动性/T+1/退出三方案点时回放，含失败、现金时间积分、净收益和左尾；作者/事件/关系去重及来源冲突复核；current标签、未载入正文和旧REJECTED研究不得升级
  - 回滚：本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。
  - 本次跟进（报告声明）：10/2 context有215份report索引、185个current观点但正文未载、远端全量发现不可用；它们不是独立即时信号。固定清单缺完整入口外点时队列和三方案OOS；旧研究manifest不是本挑战者运行。未见本轮运行或回滚。
  - 负责人：xiaocao weekly research maintainer；入口完整性研究仅走独立研究门；下次复核：2026-10-09。

## 已自动落地的代码/配置变更
- none
- 独立运行事故修复（不属策略 AUTO_APPLIED）：修正日历证明、违规原结算和缺EOD识别；finalizer只暂存确切生成工件、commit --only保留原index、逐文件清单与旧dirty目录子文件保护；隔离Git验证未/已暂存私人runtime与旧目录WIP均不入commit；回滚：git revert本轮scoped commit，仅回退报告/暂存逻辑；不更改原账户、订单、snapshot或结算。

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- KOL 固定复盘输入（仅观察，不增加自动落地权限）：output/live/kol_policy/context/*.context.json, output/live/kol_policy/decisions/*.json, output/live/book_b_live_execution/consumption.jsonl, output/live/book_b_live_execution/book_b_live_decisions.jsonl, output/live/book_b_live_execution/runs/*.json, output/live/kol_policy/account_risk/live_B.jsonl, output/live/paper_decision_support/consumption/*.json, output/live/paper_decision_support/consumption.jsonl, output/live/kol_policy/account_risk/risk_receipts/*.json, output/live/flywheel_change_ledger.jsonl, output/live/kol_policy/requests/*.json, output/live/kol_policy/source_verifications/*.json
- APP 执行固定复盘输入（仅观察，不增加策略自动落地权限）：output/live/daily_execution_review_*.md, output/live/book_b_live_execution/events.jsonl, output/live/book_b_live_execution/runs/intraday/archive/*.json, output/live/book_b_live_execution/settlements/*.json, output/live/book_b_live_execution/capital_policy.json, output/live/book_b_live_execution/capital_flows.jsonl, output/live/book_b_live_execution/accounting_reports/*.json
- 提案数量：1
- 自动落地候选数量：0

## 验证
- Focused offline weekly regression: 116 passed in 2.28s; includes generated proposal tree/ledger equality, legacy dirty-directory descendants and staged-private preservation
- Independent Standards and Spec review against 83772dba: PASS; zero unresolved findings; staged-private regression and original failed-turn evidence verified
- Fixed-input 88 snapshots, 824 unique KOL files and 13 semantic refs: PASS; execution repair refs 20 verified; append-only task trace capture prefix preserved
- scripts/data_doctor.py: OK (weekly_doctor_2026-10-02.log)
- scripts/strategy_protocols.py --check: PASS (3 protocols)
- bash -n scripts/auto_daily.sh and git diff --check: PASS
- Post-finalize artifact correction: only this dated row files_changed and report refreshed; one weekly command, one finalize, one dated ledger row retained

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 195 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-10-02/weekly-2026-10-02-point-in-time-evidence.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 110,
    "candidate_assertions": 274,
    "candidate_to_tested": 0.05,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 195,
    "candidates_untested": 185,
    "dedup_ratio": 0.71,
    "instrumentation_todos": 78,
    "median_recurrence": 1,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 631,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 110
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 10,
  "pre_existing_dirty_sample": [
    " M kronos_screen/HYPOTHESES.jsonl",
    " M src/xiaocao/live/app_test_window.py",
    "?? .scratch/book-b-morning-20260916-review/",
    "?? .scratch/kol-classification-backfill-20260921.py",
    "?? .scratch/kol-netdisk-e51919c15179ed8d-content-audit.json",
    "?? .scratch/morning-handoff-resilience/",
    "?? output/audit/",
    "?? output/automation_audit/",
    "?? output/deployment/",
    "?? tests/test_app_preopen_grant.py"
  ],
  "kol_system_review_status": "completed",
  "kol_inventory_sha256": "425ab84073bb3c5588cd4c4093c34a307b9b61962e4fa4b92c6dab3611910780",
  "kol_audit_feedback": {
    "consumption": {
      "live": {
        "book_counts": {
          "B": 160
        },
        "consumption_container_count": 139,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 7,
          "kol-b-live-opening-20260916-pause-adds-329fb25c-v1": 1,
          "kol-b-live-sparse-20260916-1025-pause-7878186a-v1": 1,
          "kol-b-live-sparse-20260916-1325-neutral-3510a357-v1": 25,
          "kol-b-live-sparse-20260917-1025-neutral-d4b2fe7f-v1": 6,
          "kol-b-live-sparse-20260917-1325-neutral-b4cc5ae7-v1": 21,
          "kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1": 36,
          "kol-b-live-sparse-20260929-1025-neutral-7f33dfd2-v1": 4,
          "kol-b-live-sparse-20260929-1325-neutral-8156af63-v1": 17,
          "kol-b-live-sparse-20260930-1025-neutral-4f559e49-v1": 10,
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
        "evidence_sha256": "7dae250e8a67b028284d23f81a69d49d3f007fa42e428047b7c840c79bc21424",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 122,
        "legacy_file_count": 11,
        "missing_consumption_clock_count": 38,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 0,
        "paper_terminal_status_counts": {},
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 122,
        "record_count": 160,
        "reported_execution_status_counts": {},
        "skip_record_count": 1,
        "source_file_count": 29,
        "status": "read",
        "unbound_decision_reference_count": 117
      },
      "paper": {
        "book_counts": {
          "B": 14
        },
        "consumption_container_count": 14,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 1,
          "kol-b-paper-sparse-20260916-1325-neutral-3510a357-v1": 1,
          "kol-b-paper-sparse-20260917-1325-neutral-b4cc5ae7-v1": 1,
          "kol-b-paper-sparse-20260918-1325-neutral-3ae43f5a-v1": 4,
          "kol-b-paper-sparse-20260929-1325-neutral-8156af63-v1": 1,
          "kol-b-precheck-20260908-1428-astra-neutral-v1": 1,
          "kol-b-sparse-20260907-1430-astra-neutral-v1": 1,
          "kol-b-sparse-20260909-1325-astra-neutral-38a3f375-v1": 1,
          "kol-b-sparse-20260910-1055-astra-neutral-12b5dc0e-v1": 1,
          "kol-b-sparse-20260914-1325-pause-adds-5903d480-v1": 1,
          "kol-xiaocao-sunday-pilot-20260906-reviewed-v2": 1
        },
        "evidence_sha256": "870b2c4188370129e1113d920cacda2a142641f4a74c1ed3823edf9ff1b93f5a",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 14,
        "legacy_file_count": 0,
        "missing_consumption_clock_count": 14,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 13,
        "paper_terminal_status_counts": {
          "bought": 8,
          "no_buy": 6
        },
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 14,
        "record_count": 14,
        "reported_execution_status_counts": {},
        "skip_record_count": 6,
        "source_file_count": 28,
        "status": "read",
        "unbound_decision_reference_count": 14
      }
    },
    "execution_verification": "not_performed",
    "profit_attribution": "not_established",
    "published_decision_count": 43,
    "status": "audited"
  },
  "kol_audit_snapshot_binding": {
    "live": "matched",
    "paper": "matched"
  },
  "kol_experiment_slots": [
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-baseline_no_kol",
      "falsifier": "若多日期/独立来源事件的点时费后配对显示KOL改善净收益或左尾，剔除单一赢家且同风险暴露后仍成立，则推翻基线足以解释账户结果；缺证据不判定。",
      "follow_up": {
        "conclusion": "旧账本截至9/27仅登记设计；本轮固定option_comparison为空，没有新的no-KOL/current点时配对run或回滚回执。9/29–30中性包和风险读数仅证实覆盖/观测，APP结算及纸盘消费链仍缺，不能确认收益增量或实验完成。",
        "disposition": "continue",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "5b04451dc97b27757ae73f96ecfbf1a2f53c73232a30d9e7534cf074bd51660a"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260929-1025-neutral-7f33dfd2-v1.json",
            "sha256": "23304a2c7d3863144976289ad2156af9bf4c7d110637c0accb06bac6248b9fd3"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260930-1025-neutral-4f559e49-v1.json",
            "sha256": "a0bb81a0f0b6c3a3408c973d9730854c6a1192cffcaa0ae12551f8a07ccdab6e"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-paper-sparse-20260930-1025-neutral-4f559e49-v1.json",
            "sha256": "b9738643602a9f80ed2d0b348a0172c03b70055a3b6f60d59a0b794a17b2a0f1"
          },
          {
            "path": "output/live/kol_policy/account_risk/live_B.jsonl",
            "sha256": "7890c87f88054fafed6fd4449dcf90f103d5707d679ffaad0a00f93ac9584fa0"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "cb647858fa6df80f1e796da538523c133687c05795b899dbf8b7d30791553350"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "baseline_no_kol",
      "next_review": "2026-10-09",
      "objective": "分开live:B与paper:B，在同日不可变freeze、同本金风险、整手、合法时点与退出下配对no-KOL和现行overlay；预注册OOS，测费后收益、左尾/回撤、暴露、现金时间积分及可成交错失上涨。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly research maintainer；隔离执行仍需既有研究门指定",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "5b04451dc97b27757ae73f96ecfbf1a2f53c73232a30d9e7534cf074bd51660a"
      },
      "required_evidence": [
        "每日完整freeze、资格和模式；消费、intent/claim、实际订单/成交/费用、T+1、报价；UNKNOWN保持未决",
        "同本金/风险/整手/时点/退出no-KOL与current配对，完整结算NAV、资本流、现金时间积分、漏损与错失上涨",
        "预注册OOS、失败样本、作者事件/模式/市场阶段聚类、单一赢家剔除与成本敏感性；分开1/4/12周实际覆盖"
      ],
      "rollback": "本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。",
      "status": "needs_evidence_and_design"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-current_bounded",
      "falsifier": "若多数pause没有当时合法新增风险机会、发布晚于动作或到期，或费后错失收益/执行漏损抵消左尾改善，则不支持叠加增益；中性包计数不算收益。",
      "follow_up": {
        "conclusion": "9/15–16旧pause未见本轮新增收益归因或实验run；9/29–30六包中性且无跳过、退出或模式跟随。9/29宽度反证旧日普跌直接外推，但没有合法消费至成交的配对链，不能登记为避免损失。财富值/匿名代码触发仍未证，未见回滚。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "5b04451dc97b27757ae73f96ecfbf1a2f53c73232a30d9e7534cf074bd51660a"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1.json",
            "sha256": "2b1344f9c406f1f7643ef0bc9cb95e14ea2ebe4f54335fe0ccbedd69b2d9d5a3"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-paper-20260916-morning-pause-astra-v1.json",
            "sha256": "0b1552c2b5b3ed1fb98b77b25f89efa6d8298abcbf9730752f47b95209323d13"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260929-1025-neutral-7f33dfd2-v1.json",
            "sha256": "23304a2c7d3863144976289ad2156af9bf4c7d110637c0accb06bac6248b9fd3"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260929-1325-neutral-8156af63-v1.json",
            "sha256": "05fbbd5aa16354ed2f481da3aeab952e097e570478bfb98b0f5073619c6cf5a4"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260930-1025-neutral-4f559e49-v1.json",
            "sha256": "a0bb81a0f0b6c3a3408c973d9730854c6a1192cffcaa0ae12551f8a07ccdab6e"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-paper-sparse-20260930-1025-neutral-4f559e49-v1.json",
            "sha256": "b9738643602a9f80ed2d0b348a0172c03b70055a3b6f60d59a0b794a17b2a0f1"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "cb647858fa6df80f1e796da538523c133687c05795b899dbf8b7d30791553350"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "current_bounded",
      "next_review": "2026-10-09",
      "objective": "检验有界pause/中性包是否在第一合法动作前被消费并改变原计划；分解来源、模型、审核、发布、过期和native/订单迟延，配对量化避免损失与错失上涨。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly research maintainer；lineage补证由原生产/消费owner协作",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "5b04451dc97b27757ae73f96ecfbf1a2f53c73232a30d9e7534cf074bd51660a"
      },
      "required_evidence": [
        "source published/received、请求及模型开始/完成、独立审核、发布、到期、第一合法消费、原plan/订单/成交/结算全时钟",
        "逐pause的freeze资格、账户现金/风险、报价、流动性、整手、T+1；仅合法机会计机会成本",
        "live/paper分开核实际费用、净避免损失/错失上涨、现金时间积分和左尾；按作者事件去重并保存反证"
      ],
      "rollback": "本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。",
      "status": "needs_evidence_and_design"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-kol_challenger",
      "falsifier": "若完整点时队列在整手、费用、流动性、T+1、退出及OOS约束后不能同时改善机会覆盖与风险调整结果，或优势来自事后补榜/回填/同源重复/单一赢家，则拒绝；缺数据不判PASS。",
      "follow_up": {
        "conclusion": "10/2 context有215份report索引、185个current观点但正文未载、远端全量发现不可用；它们不是独立即时信号。固定清单缺完整入口外点时队列和三方案OOS；旧研究manifest不是本挑战者运行。未见本轮运行或回滚。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "5b04451dc97b27757ae73f96ecfbf1a2f53c73232a30d9e7534cf074bd51660a"
          },
          {
            "path": "output/live/kol_policy/context/ad67ab2a53ef79f636cf319d552fd6930c23f0a40b2fb8336286f242f3505059.context.json",
            "sha256": "5cf9a446bd89948795405db0de08958835dbb4cc94f714681b3b355c1b368d47"
          },
          {
            "path": "output/live/kol_policy/context/295f3e9c726a363871e36f2563405243c93d103c243945343d09d3c33e7b65fc.context.json",
            "sha256": "2cfc809cbc115d3fb257b1a61c26b0d7b7d3f3e9014a0f6c403300132af0ca49"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260929-1325-neutral-8156af63-v1.json",
            "sha256": "05fbbd5aa16354ed2f481da3aeab952e097e570478bfb98b0f5073619c6cf5a4"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260930-1025-neutral-4f559e49-v1.json",
            "sha256": "a0bb81a0f0b6c3a3408c973d9730854c6a1192cffcaa0ae12551f8a07ccdab6e"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "kol_challenger",
      "next_review": "2026-10-09",
      "objective": "authority=0隔离研究预注册竞价、9:31和有限盘中截面，检验★E/模式入口遗漏合法可成交候选，并与no-KOL/current同本金、风险、费用和退出OOS配对。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly research maintainer；入口完整性研究仅走独立研究门",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "5b04451dc97b27757ae73f96ecfbf1a2f53c73232a30d9e7534cf074bd51660a"
      },
      "required_evidence": [
        "入口前后完整候选、每条拒绝理由、模式/评分版本和当时可见时间；区分COLD、UNKNOWN、BJSE与真正入口外研究行",
        "预注册合法截面与同本金/风险/费用/整手/流动性/T+1/退出三方案点时回放，含失败、现金时间积分、净收益和左尾",
        "作者/事件/关系去重及来源冲突复核；current标签、未载入正文和旧REJECTED研究不得升级"
      ],
      "rollback": "本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。",
      "status": "needs_evidence_and_design"
    }
  ],
  "data_evidence_review": {
    "accounting_observations": [
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/189f1f5f0f67564a9e27214fb7b28800dce60f3cd661e5bab906571e96b01ff1.json",
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-09-29T07:46:17.739000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c.json",
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-09-29T07:46:17.739000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/5fdccb94720cb27ec705c46da02f69429616cfe21964e2d3ef23bec01f2cd006.json",
          "sha256": "59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-09-29T07:46:17.739000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/8e58602dce0e24050d28f4157476691f5c89b4477d1075bf54d86cd588ac738b.json",
          "sha256": "2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-09-30T07:22:21.651000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/c41cf727e4ea97810027c561a03a355118fa2ae5c94a372a4a792e70c8bd5467.json",
          "sha256": "fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-09-30T06:51:01.818000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      }
    ],
    "as_of": "2026-10-02",
    "authority": "research_observer_only",
    "exploration_proposals": [
      {
        "auto_apply_eligible": false,
        "experiment_id": "weekly-evidence-2026-10-02-paired-options",
        "falsifier": "费用后改善不能在 OOS 保留，或只由单周/单赢家/缩仓解释",
        "next_review": "2026-10-09",
        "objective": "冻结同一候选、预算与 OOS 分割，比较无 KOL / 有界 KOL / 挑战者",
        "owner": "weekly research owner",
        "required_evidence": [
          "expected_sample_ids",
          "frozen_candidates_sha256",
          "selection/outcome clocks",
          "three-option net costs"
        ],
        "rollback": "retain current strategy; remove only isolated research experiment artifacts",
        "status": "proposed_not_run"
      },
      {
        "auto_apply_eligible": false,
        "experiment_id": "weekly-evidence-2026-10-02-proxy-fill",
        "falsifier": "剔除代理后样本不足或优势消失，则不能称为已确认可执行改善",
        "next_review": "2026-10-09",
        "objective": "量化缺分钟窗口及实时重试代理对纸面结论的敏感度",
        "owner": "weekly research owner",
        "required_evidence": [
          "saved fill basis/fallback",
          "same-cohort confirmed-window sensitivity",
          "missing-window counts"
        ],
        "rollback": "retain current strategy; remove only isolated research experiment artifacts",
        "status": "proposed_not_run"
      },
      {
        "auto_apply_eligible": false,
        "experiment_id": "weekly-evidence-2026-10-02-cashflow-time",
        "falsifier": "无法闭合净投入/净值/费用或缺自然运行时刻，则不认定收益或速度提升",
        "next_review": "2026-10-09",
        "objective": "分账户验证资金划拨、费用与延迟对收益的影响",
        "owner": "weekly research owner",
        "required_evidence": [
          "dated accounting statements",
          "capital flow chain",
          "source/decision/order/fill timestamps"
        ],
        "rollback": "retain current strategy; remove only isolated research experiment artifacts",
        "status": "proposed_not_run"
      }
    ],
    "hypotheses": [
      {
        "claim": "K->P top picks (variant A) beats take-all",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "A_kp_star",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 78,
          "n_trades": 222,
          "p": 0.074914,
          "per_trade_spread": 0.787911,
          "test_edge": 0.736789,
          "train_edge": 0.839962
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-10-02T20:32:09",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "K->P + auction tiebreak (variant B) beats take-all",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "B_vb_star",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 60,
          "n_trades": 172,
          "p": 0.038279,
          "per_trade_spread": 1.240692,
          "test_edge": 2.214262,
          "train_edge": 0.196744
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-08-28T15:25:16",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "出场层非-4602主因:逐笔配对 exit_timing 中性(+0.10%),真漏点=entry追高(+1.2~1.7%/笔)+负选股alpha;-4602 headline是book A/B不配对(book A仅覆盖~6/15+)的伪差",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "XH-016",
        "metrics": {
          "effective_alpha": 0.025,
          "n_days": 12,
          "n_trades": 44,
          "p": 0.920587,
          "per_trade_spread": 0.101864,
          "test_edge": 0.899037,
          "train_edge": -1.164235
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-06-21T22:52:29",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "机械2%trailing杀趋势龙头卖飞:REJECTED-前提不成立(系统零趋势龙头持仓,全短线低吸mode);所持仓上trailing vs next-close=-0.26%/笔,不显著",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "XH-001",
        "metrics": {
          "effective_alpha": 0.025,
          "n_days": 11,
          "n_trades": 30,
          "p": 0.746217,
          "per_trade_spread": -0.255967,
          "test_edge": 0.634824,
          "train_edge": -1.420846
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-06-21T22:52:29",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "坏regime(bear+div)禁低吸mode:REJECTED-全年mode_history(1587笔/104天)skip比take亏-1.15%/笔(p=0.0003反向);低吸即便坏regime也正期望(bear~平-0.02%,div+1.99%),低胜率右偏,lever是抓右尾非按regime禁用",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "XH-011",
        "metrics": {
          "effective_alpha": 0.0125,
          "n_days": 104,
          "n_trades": 1587,
          "p": 0.000262,
          "per_trade_spread": -1.149909,
          "test_edge": -0.824224,
          "train_edge": -1.520804
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-06-21T23:16:47",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "连续N天广度恶化(死盘)窗口应空仓低吸 — primary abs(N=2,positive_ratio<0.40)",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "XH-017",
        "metrics": {
          "effective_alpha": 0.00625,
          "n_days": 258,
          "n_trades": 3827,
          "p": 0.002957,
          "per_trade_spread": -0.32006,
          "test_edge": -0.361687,
          "train_edge": -0.263952
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-06-22T09:43:51",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "趋势龙头选股是lever — momentum-leader proxy(top-10 by 60d momentum, liquid top-30%, 5d hold) beats market",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "XH-013",
        "metrics": {
          "effective_alpha": 0.008333333333333333,
          "n_days": 195,
          "n_trades": 195,
          "p": 0.039811,
          "per_trade_spread": -0.893363,
          "test_edge": -1.913247,
          "train_edge": 0.137035
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-06-22T09:51:40",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "趋势主线选股(小草实际信号:轮动频率主线,非龙头非动量)beats 平均题材/广义参与",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "XH-013b",
        "metrics": {
          "effective_alpha": 0.002777777777777778,
          "n_days": 31,
          "n_trades": 31,
          "p": 0.247396,
          "per_trade_spread": -0.158757,
          "test_edge": -0.193822,
          "train_edge": -0.121354
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-06-22T10:47:08",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "趋势尾声的短线起爆样本来自 raw qibao rank top10 + 电子/20cm + 开幅可控红盘非涨停，而不是严格高 jssb emitted qibao",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "XH-037",
        "metrics": {
          "effective_alpha": 0.0071428571428571435,
          "n_days": 114,
          "n_trades": 164,
          "p": 0.0,
          "per_trade_spread": 3.970832,
          "test_edge": 4.266669,
          "train_edge": 3.682124
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-06-30T21:31:08",
        "recorded_verdict": "PASS",
        "rejected_by": [],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "K survivors + mode-rotation rank (variant C) beats take-all",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "C_mode_rotation_k_survivors",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 29,
          "n_trades": 83,
          "p": 0.011414,
          "per_trade_spread": 2.048145,
          "test_edge": 0.657456,
          "train_edge": 3.472752
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-08-14T15:26:12",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "raw-qibao benchmark paper-promoted modes (variant D) beat take-all",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "D_qibao_benchmark_paper_promoted",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 11,
          "n_trades": 56,
          "p": 0.119046,
          "per_trade_spread": -1.382789,
          "test_edge": -3.010903,
          "train_edge": 0.245325
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-17T15:29:18",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "Book T trend config trend_L60_R20_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "T_trend_L60_R20_M3",
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
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "compounded_alpha_positive",
          "per_hold_alpha_positive",
          "walk_forward_consistent",
          "significant",
          "survives_non_bull"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "Book T trend config trend_L60_R30_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "T_trend_L60_R30_M3",
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
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "compounded_alpha_positive",
          "per_hold_alpha_positive",
          "walk_forward_consistent",
          "significant",
          "survives_non_bull"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "Book T trend config trend_L60_R40_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "T_trend_L60_R40_M3",
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
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "Book T trend config trend_L60_R60_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "T_trend_L60_R60_M3",
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
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "Book T trend config trend_L20_R20_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "T_trend_L20_R20_M3",
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
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "Book T trend config rotation_L60_R30_M3_W20_K5 beats average-theme beta under compounded return / drawdown / turnover guards",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "T_rotation_L60_R30_M3_W20_K5",
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
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-03T15:42:46",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "N字低吸灰区机制指标确认组跑赢中证1000",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "aux_gray_n_fixed",
        "metrics": {
          "effective_alpha": 0.008333333333333333,
          "n_days": 9,
          "n_trades": 9,
          "p": 0.560284,
          "per_trade_spread": -1.356032,
          "test_edge": -2.259637,
          "train_edge": -0.226526
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-10T20:17:02",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "接力低弱转1灰区机制指标确认组跑赢中证1000",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "aux_gray_relay1_fixed",
        "metrics": {
          "effective_alpha": 0.008333333333333333,
          "n_days": 25,
          "n_trades": 25,
          "p": 0.851966,
          "per_trade_spread": -0.243076,
          "test_edge": -1.135733,
          "train_edge": 0.723968
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-07-10T20:17:09",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "agent-reviewed AI intelligence short-factor bullish picks (variant E) beat take-all",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f"
        },
        "hypothesis_id": "E_ai_intelligence_short_factor",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 13,
          "n_trades": 25,
          "p": 0.311072,
          "per_trade_spread": 1.055139,
          "test_edge": -0.660393,
          "train_edge": 2.403057
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-08-14T15:26:12",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      }
    ],
    "input_manifest": {
      "files": [
        {
          "first_date": "2026-06-20",
          "last_date": "2026-10-02",
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "record_count": 38,
          "sha256": "6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f",
          "size_bytes": 26045,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/6914ec58bd66f56377bb17072c0b99fdf1bad91aff0867c0bbf3cf9ac61c583f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/189f1f5f0f67564a9e27214fb7b28800dce60f3cd661e5bab906571e96b01ff1.json",
          "record_count": 1,
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "size_bytes": 1972,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c.json",
          "record_count": 1,
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "size_bytes": 1972,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/5fdccb94720cb27ec705c46da02f69429616cfe21964e2d3ef23bec01f2cd006.json",
          "record_count": 1,
          "sha256": "59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b",
          "size_bytes": 2013,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/8e58602dce0e24050d28f4157476691f5c89b4477d1075bf54d86cd588ac738b.json",
          "record_count": 1,
          "sha256": "2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955",
          "size_bytes": 1939,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/c41cf727e4ea97810027c561a03a355118fa2ae5c94a372a4a792e70c8bd5467.json",
          "record_count": 1,
          "sha256": "fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf",
          "size_bytes": 1939,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/capital_flows.jsonl",
          "record_count": 1,
          "sha256": "25d2c184575a2821c38d27e0a2c7d563de2d327042f3683ef94b98f45aa635c5",
          "size_bytes": 868,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/25d2c184575a2821c38d27e0a2c7d563de2d327042f3683ef94b98f45aa635c5",
          "status": "captured"
        },
        {
          "first_date": "2026-06-08",
          "last_date": "2026-06-08",
          "path": "output/live/exit_calibration.jsonl",
          "record_count": 1,
          "sha256": "dde16689d347d08cc3196e8dd9d7c450cc60f9f99f4d7f7ad381a94041df5752",
          "size_bytes": 280,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/dde16689d347d08cc3196e8dd9d7c450cc60f9f99f4d7f7ad381a94041df5752",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-09-30",
          "path": "output/live/paper_holdings_snapshots.jsonl",
          "record_count": 773,
          "sha256": "68989977fd0e46d272d8b6066598bb3d4b577e072a9a739211d6332ac20ad2d4",
          "size_bytes": 1013194,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/68989977fd0e46d272d8b6066598bb3d4b577e072a9a739211d6332ac20ad2d4",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-09-30",
          "path": "output/live/paper_trades.jsonl",
          "record_count": 438,
          "sha256": "7a77cdd43cedc145bc8a5beef3405bb202c52fd5f94a4ec82f568478bb6254c2",
          "size_bytes": 227441,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/7a77cdd43cedc145bc8a5beef3405bb202c52fd5f94a4ec82f568478bb6254c2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/pnl_decompose.csv",
          "record_count": null,
          "sha256": "f642a76d82a7dbccc981a0b78f03f19dba278b207cfbb8e3fcb825701fe3af7b",
          "size_bytes": 20315,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/f642a76d82a7dbccc981a0b78f03f19dba278b207cfbb8e3fcb825701fe3af7b",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-09-29",
          "path": "output/live/positions.jsonl",
          "record_count": 221,
          "sha256": "b45115d2ed9e8072f13675f4158f41eaa28c8b12953188ae954f0870ac990a60",
          "size_bytes": 315355,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b45115d2ed9e8072f13675f4158f41eaa28c8b12953188ae954f0870ac990a60",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-09-30",
          "path": "output/live/signal_snapshots.jsonl",
          "record_count": 853,
          "sha256": "bc94632a8b9f6c3b5f653af47ec8814df1be74f349db8367c2dca3b5b2d52244",
          "size_bytes": 3583754,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/bc94632a8b9f6c3b5f653af47ec8814df1be74f349db8367c2dca3b5b2d52244",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-06-30.md",
          "record_count": null,
          "sha256": "d66495a808d06d9371daa6287838dba3f0af165c10a8638a1d59c612cde2581d",
          "size_bytes": 1552,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/d66495a808d06d9371daa6287838dba3f0af165c10a8638a1d59c612cde2581d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-01.md",
          "record_count": null,
          "sha256": "76377baf3480cd9615e67e6260571418cf9247dc54b0960d5047bb2dfd9de9e9",
          "size_bytes": 1568,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/76377baf3480cd9615e67e6260571418cf9247dc54b0960d5047bb2dfd9de9e9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-02.md",
          "record_count": null,
          "sha256": "62c8ecff2e5ae8a5105609809a5b8d3601871c12cb0dc6366338b2b8c7eb7baa",
          "size_bytes": 1614,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/62c8ecff2e5ae8a5105609809a5b8d3601871c12cb0dc6366338b2b8c7eb7baa",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-03.md",
          "record_count": null,
          "sha256": "8b7fd10f1634b4d5051ba707e6af2e43945caf33e4df326bdfaa4a5f02ed1f39",
          "size_bytes": 1596,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/8b7fd10f1634b4d5051ba707e6af2e43945caf33e4df326bdfaa4a5f02ed1f39",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-06.md",
          "record_count": null,
          "sha256": "3eb2487514a15f0a342f3fc765af57f8ed76a12cf87215e68765c50a36892535",
          "size_bytes": 1657,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/3eb2487514a15f0a342f3fc765af57f8ed76a12cf87215e68765c50a36892535",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-07.md",
          "record_count": null,
          "sha256": "4703555ba1d1feb2cc352471ec20b9e05a476a7936bfa04574c02e14a89cc0f3",
          "size_bytes": 1659,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/4703555ba1d1feb2cc352471ec20b9e05a476a7936bfa04574c02e14a89cc0f3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-08.md",
          "record_count": null,
          "sha256": "3051c61877741e55750cb64a5e2b7ad3dd9484bae16e8bf3b95732143a3811df",
          "size_bytes": 1659,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/3051c61877741e55750cb64a5e2b7ad3dd9484bae16e8bf3b95732143a3811df",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-09.md",
          "record_count": null,
          "sha256": "421025f3d2671c0474f92c901e40c8fd06e08ce7dbdd575d2366f64fdcd812d8",
          "size_bytes": 1664,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/421025f3d2671c0474f92c901e40c8fd06e08ce7dbdd575d2366f64fdcd812d8",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-10.md",
          "record_count": null,
          "sha256": "e3d03874c764b96a280a787198db36b9e3e6b6121bc300d3ebc646cfe420977c",
          "size_bytes": 1665,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/e3d03874c764b96a280a787198db36b9e3e6b6121bc300d3ebc646cfe420977c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-13.md",
          "record_count": null,
          "sha256": "538ced43d020a0f4f15a001c7b02c53197e266d9e4198d69c7a36a99a740b912",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/538ced43d020a0f4f15a001c7b02c53197e266d9e4198d69c7a36a99a740b912",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-14.md",
          "record_count": null,
          "sha256": "bb90bce70c12c7c856b678a7d348e8873a069a8d01bbf23f78b55e03e1aba3e0",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/bb90bce70c12c7c856b678a7d348e8873a069a8d01bbf23f78b55e03e1aba3e0",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-15.md",
          "record_count": null,
          "sha256": "c550da9aa03924d953236ff4bede78eb6deaf513acee7b1a8f45f7cf0bcff321",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/c550da9aa03924d953236ff4bede78eb6deaf513acee7b1a8f45f7cf0bcff321",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-16.md",
          "record_count": null,
          "sha256": "07051d8db157280a82ef0503d5371f40ea13af11f9b184b45c5f84e78edd1b9b",
          "size_bytes": 1679,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/07051d8db157280a82ef0503d5371f40ea13af11f9b184b45c5f84e78edd1b9b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-17.md",
          "record_count": null,
          "sha256": "b8a8a7b5fd7347609c36e1a391fc8436ead0109413d4fcc6f89335e2263209ff",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b8a8a7b5fd7347609c36e1a391fc8436ead0109413d4fcc6f89335e2263209ff",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-20.md",
          "record_count": null,
          "sha256": "4ac67aaf14c874122ef6ff4e39c824a257d6e0d020e147ca13ce435941278c0e",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/4ac67aaf14c874122ef6ff4e39c824a257d6e0d020e147ca13ce435941278c0e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-21.md",
          "record_count": null,
          "sha256": "4da8cefa13f79332520f76ef1c5e6327461fb6d1688bcc4c570f3b3716b7c3fc",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/4da8cefa13f79332520f76ef1c5e6327461fb6d1688bcc4c570f3b3716b7c3fc",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-22.md",
          "record_count": null,
          "sha256": "c62603355e0b8b6c81f052efb1f046653e5d510cfd5a4433df7693d800a44a3d",
          "size_bytes": 1739,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/c62603355e0b8b6c81f052efb1f046653e5d510cfd5a4433df7693d800a44a3d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-23.md",
          "record_count": null,
          "sha256": "2866883e99c0cb09ce15a8faa7c9e2033e62f39eac4ea1e0dfe65b45185ea22f",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/2866883e99c0cb09ce15a8faa7c9e2033e62f39eac4ea1e0dfe65b45185ea22f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-24.md",
          "record_count": null,
          "sha256": "7749911678871915752439e978e352fd3b98839b688edee103bcc9bd7f0799df",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/7749911678871915752439e978e352fd3b98839b688edee103bcc9bd7f0799df",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-27.md",
          "record_count": null,
          "sha256": "b45de707bceb56128e29d06aed080e6171e2bb30021d3bb7af753f967a1b9c01",
          "size_bytes": 1736,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b45de707bceb56128e29d06aed080e6171e2bb30021d3bb7af753f967a1b9c01",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-28.md",
          "record_count": null,
          "sha256": "9e5aa5387abc464a2580cd1fbfc4fbb1aefb82b218346017dcfcb58388a97958",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/9e5aa5387abc464a2580cd1fbfc4fbb1aefb82b218346017dcfcb58388a97958",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-03.md",
          "record_count": null,
          "sha256": "9adbe52713711ccb666619155fe2aa13ddc6e41df810009a1044a1ddcb89bc53",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/9adbe52713711ccb666619155fe2aa13ddc6e41df810009a1044a1ddcb89bc53",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-04.md",
          "record_count": null,
          "sha256": "7d2ab40b988a0b312d10f40e1ea0077e40f4c8b0a4f20ca2910ad47f88d27e93",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/7d2ab40b988a0b312d10f40e1ea0077e40f4c8b0a4f20ca2910ad47f88d27e93",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-05.md",
          "record_count": null,
          "sha256": "8521076f2100e1b245fcf8d9357d714189ae0674bf64799255d3fbc4f4868c5b",
          "size_bytes": 1735,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/8521076f2100e1b245fcf8d9357d714189ae0674bf64799255d3fbc4f4868c5b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-06.md",
          "record_count": null,
          "sha256": "b29ce0f1708a8e129abf56a6fb5b609bc0c86e2a92c783df44de0431dc5cc23e",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b29ce0f1708a8e129abf56a6fb5b609bc0c86e2a92c783df44de0431dc5cc23e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-07.md",
          "record_count": null,
          "sha256": "ca9f909330795b6ef3b26ee23401dcb91f765bc7116c1c1c4b8c15dbe164f819",
          "size_bytes": 1736,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/ca9f909330795b6ef3b26ee23401dcb91f765bc7116c1c1c4b8c15dbe164f819",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-10.md",
          "record_count": null,
          "sha256": "d3552e00c3426d4779bc070975fa057b483add73b711f8f148c06265c0da13f4",
          "size_bytes": 1734,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/d3552e00c3426d4779bc070975fa057b483add73b711f8f148c06265c0da13f4",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-11.md",
          "record_count": null,
          "sha256": "9d4dde9cbc13f56d74a031f88f4e32c3f04bcde74467bcf2cc0b9113ee028954",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/9d4dde9cbc13f56d74a031f88f4e32c3f04bcde74467bcf2cc0b9113ee028954",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-12.md",
          "record_count": null,
          "sha256": "4e127d3e802b60465f31ca597fd6d36cef2d3a110df76eed26d5bf18a4c2d898",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/4e127d3e802b60465f31ca597fd6d36cef2d3a110df76eed26d5bf18a4c2d898",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-13.md",
          "record_count": null,
          "sha256": "785f1fd8a42083c24e15569f8d649bbc863c2c79ed502063bfa84fb92c8bb314",
          "size_bytes": 1733,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/785f1fd8a42083c24e15569f8d649bbc863c2c79ed502063bfa84fb92c8bb314",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-14.md",
          "record_count": null,
          "sha256": "41bfd6060c4f806377bfef8564f5487791644b659f053ea59bb66d1f164a1c0d",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/41bfd6060c4f806377bfef8564f5487791644b659f053ea59bb66d1f164a1c0d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-17.md",
          "record_count": null,
          "sha256": "a00c328cbf60a8f2f7a67623d4f81b042c5173220eadc9088ee781c5b1dada9e",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/a00c328cbf60a8f2f7a67623d4f81b042c5173220eadc9088ee781c5b1dada9e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-18.md",
          "record_count": null,
          "sha256": "fa09c513b7ad5606602270053cc80955d596db6ef18d5f867375b1ebb74c8c14",
          "size_bytes": 1735,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/fa09c513b7ad5606602270053cc80955d596db6ef18d5f867375b1ebb74c8c14",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-19.md",
          "record_count": null,
          "sha256": "d761791ad07a44e1ee8a56552eadd3891bd46fb43d2a3c05c54bc0537ec22c57",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/d761791ad07a44e1ee8a56552eadd3891bd46fb43d2a3c05c54bc0537ec22c57",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-20.md",
          "record_count": null,
          "sha256": "83b3ac332aceb925c6070f86112ec846b588a2bba476077fd3c38eabd80c7d39",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/83b3ac332aceb925c6070f86112ec846b588a2bba476077fd3c38eabd80c7d39",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-21.md",
          "record_count": null,
          "sha256": "d0300b91b7b4cfb54b8ac244b9443fe8f83dbb95145d7f8c37ade984e7239507",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/d0300b91b7b4cfb54b8ac244b9443fe8f83dbb95145d7f8c37ade984e7239507",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-24.md",
          "record_count": null,
          "sha256": "3b7682800bdd7ebf3abbee95afcd69fa7b3f7f877c81bc57d31d41bf1b030757",
          "size_bytes": 1742,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/3b7682800bdd7ebf3abbee95afcd69fa7b3f7f877c81bc57d31d41bf1b030757",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-25.md",
          "record_count": null,
          "sha256": "42cf42b3f69e1fbcea63ecc62a3764ac22130040694580f77590a88defecfa23",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/42cf42b3f69e1fbcea63ecc62a3764ac22130040694580f77590a88defecfa23",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-26.md",
          "record_count": null,
          "sha256": "43c56977508352616008101248ec0de5db86bec7b44b1642ffddd18ab79a6d94",
          "size_bytes": 1742,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/43c56977508352616008101248ec0de5db86bec7b44b1642ffddd18ab79a6d94",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-27.md",
          "record_count": null,
          "sha256": "4ac4cc4d1ae290c25b3e72a06f6b9fd080ae8170c277b8555fff137ed7cba91d",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/4ac4cc4d1ae290c25b3e72a06f6b9fd080ae8170c277b8555fff137ed7cba91d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-28.md",
          "record_count": null,
          "sha256": "e75e0b270ec136fc3b5ed584c1f28e8d4a75f357e27b47446c8eb1510dd09b87",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/e75e0b270ec136fc3b5ed584c1f28e8d4a75f357e27b47446c8eb1510dd09b87",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-31.md",
          "record_count": null,
          "sha256": "d885d323aea5ca5bfb0a19684dc9accbc7a9bdf0f40496fe6bd5effb861ffeed",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/d885d323aea5ca5bfb0a19684dc9accbc7a9bdf0f40496fe6bd5effb861ffeed",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-01.md",
          "record_count": null,
          "sha256": "be16f20dfb2cc264c4c9f85a6061c4494c844207baa88b38f973585eb8ac3929",
          "size_bytes": 1746,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/be16f20dfb2cc264c4c9f85a6061c4494c844207baa88b38f973585eb8ac3929",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-02.md",
          "record_count": null,
          "sha256": "b264718c16a877e0a3096b2bdc7a691cc98e2ee1e86faa2895953cac3f36d654",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b264718c16a877e0a3096b2bdc7a691cc98e2ee1e86faa2895953cac3f36d654",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-03.md",
          "record_count": null,
          "sha256": "5a7888361cb36d477417bffa84b93667f6f53560b25952315783cd33bc6a0f57",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/5a7888361cb36d477417bffa84b93667f6f53560b25952315783cd33bc6a0f57",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-04.md",
          "record_count": null,
          "sha256": "40d23f8116a46650265df67c651d3a30068a2ad39e68ceedfa15cf41aafd3355",
          "size_bytes": 1747,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/40d23f8116a46650265df67c651d3a30068a2ad39e68ceedfa15cf41aafd3355",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-07.md",
          "record_count": null,
          "sha256": "30e67efe07a50b6a6b54855929ad6af0cae64ed61b55dc9e3fa9516c6cb5eb6b",
          "size_bytes": 1748,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/30e67efe07a50b6a6b54855929ad6af0cae64ed61b55dc9e3fa9516c6cb5eb6b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-08.md",
          "record_count": null,
          "sha256": "f3e7eb1beb00104123dcc5adb7a158a35fc36f62a03915c5abdf68236945c60d",
          "size_bytes": 1747,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/f3e7eb1beb00104123dcc5adb7a158a35fc36f62a03915c5abdf68236945c60d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-09.md",
          "record_count": null,
          "sha256": "d4a354c8d1d8dc3ee309bdda62e1917259f98fbfb87acfa632c40282919c9fba",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/d4a354c8d1d8dc3ee309bdda62e1917259f98fbfb87acfa632c40282919c9fba",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-10.md",
          "record_count": null,
          "sha256": "ba52216859c03481296bb4d943ae343d4ecf60950cc796fcfddd1fd96ba8ce2f",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/ba52216859c03481296bb4d943ae343d4ecf60950cc796fcfddd1fd96ba8ce2f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-11.md",
          "record_count": null,
          "sha256": "b62ebb513190a36b5ad236cefb684f89f1fa4daaa2efb341ea5847debeafd74f",
          "size_bytes": 1749,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b62ebb513190a36b5ad236cefb684f89f1fa4daaa2efb341ea5847debeafd74f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-14.md",
          "record_count": null,
          "sha256": "2cebfd0ce5a4c1feee5e74c512cae5b189ef8f5bc400c2df5a7773d87757a14f",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/2cebfd0ce5a4c1feee5e74c512cae5b189ef8f5bc400c2df5a7773d87757a14f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-15.md",
          "record_count": null,
          "sha256": "5c00b8d24449edb06f7c273a057bf3e72358ad12df4e2cfe1a0a8714295cc90e",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/5c00b8d24449edb06f7c273a057bf3e72358ad12df4e2cfe1a0a8714295cc90e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-16.md",
          "record_count": null,
          "sha256": "b6fffa71d0e90842edd6d27766f15763197c84a89fe99b49c997f88ce89a6543",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b6fffa71d0e90842edd6d27766f15763197c84a89fe99b49c997f88ce89a6543",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-17.md",
          "record_count": null,
          "sha256": "f03f5d55a814d36ff930fdfcd8eb166072040fdf787645c943bcb5ab3a13cfbb",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/f03f5d55a814d36ff930fdfcd8eb166072040fdf787645c943bcb5ab3a13cfbb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-18.md",
          "record_count": null,
          "sha256": "100944791fa4121500ef1442f8d2fdfb7369f47eb4e265a2858c5c7bd0b2f823",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/100944791fa4121500ef1442f8d2fdfb7369f47eb4e265a2858c5c7bd0b2f823",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-21.md",
          "record_count": null,
          "sha256": "c6534dd010ec90470584b1963a9ffd8a1f01dd307b2e04087d84645abfa02fc5",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/c6534dd010ec90470584b1963a9ffd8a1f01dd307b2e04087d84645abfa02fc5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-22.md",
          "record_count": null,
          "sha256": "d5c7aefdadb805987efbb686277d16fb2f7e819fb0d6ac1a1d40deed0a6aff6e",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/d5c7aefdadb805987efbb686277d16fb2f7e819fb0d6ac1a1d40deed0a6aff6e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-23.md",
          "record_count": null,
          "sha256": "ef3b24b1ae89cdab8bff3e376b250cbd18737f0cbe212b30cf947d01a205d502",
          "size_bytes": 1746,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/ef3b24b1ae89cdab8bff3e376b250cbd18737f0cbe212b30cf947d01a205d502",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-28.md",
          "record_count": null,
          "sha256": "657596725f41f76d5e7422e75ccf82682476e58ad5da9b1cd52d4363bb2b3126",
          "size_bytes": 1751,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/657596725f41f76d5e7422e75ccf82682476e58ad5da9b1cd52d4363bb2b3126",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-29.md",
          "record_count": null,
          "sha256": "36ceb388f9f11b63ad7fea64a2224a114a2164c9fdf5d2c478095f1cb039add2",
          "size_bytes": 1748,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/36ceb388f9f11b63ad7fea64a2224a114a2164c9fdf5d2c478095f1cb039add2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-30.md",
          "record_count": null,
          "sha256": "3c8361e19dd4bd0070e6e77135d9a374ccd52657c472e6b7b0226c8165e5ad23",
          "size_bytes": 1751,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/3c8361e19dd4bd0070e6e77135d9a374ccd52657c472e6b7b0226c8165e5ad23",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-11_2026-07-09.md",
          "record_count": null,
          "sha256": "0cd141c22a2e3efa16b2c72f824cc9e3178ff826f85d52d96dbba6c5a5815e7f",
          "size_bytes": 1457,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/0cd141c22a2e3efa16b2c72f824cc9e3178ff826f85d52d96dbba6c5a5815e7f",
          "status": "captured"
        },
        {
          "first_date": "2026-07-10",
          "last_date": "2026-07-10",
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/manifest.json",
          "record_count": 1,
          "sha256": "b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6",
          "size_bytes": 4174,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6",
          "status": "captured"
        },
        {
          "first_date": "2026-03-19",
          "last_date": "2026-05-19",
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/trades.jsonl",
          "record_count": 9,
          "sha256": "8ae058057e8b9ee1ae52369d32cc0fa96b9575a01a71b4d50b0624eca709de9a",
          "size_bytes": 1638,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/8ae058057e8b9ee1ae52369d32cc0fa96b9575a01a71b4d50b0624eca709de9a",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/verdict.json",
          "record_count": 1,
          "sha256": "eec84c380b4696c652657886dfed8008a9b773df8cf89b72031bc7c13d0687fc",
          "size_bytes": 1799,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/eec84c380b4696c652657886dfed8008a9b773df8cf89b72031bc7c13d0687fc",
          "status": "captured"
        },
        {
          "first_date": "2026-07-10",
          "last_date": "2026-07-10",
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/manifest.json",
          "record_count": 1,
          "sha256": "f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381",
          "size_bytes": 4224,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381",
          "status": "captured"
        },
        {
          "first_date": "2026-03-02",
          "last_date": "2026-06-26",
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/trades.jsonl",
          "record_count": 25,
          "sha256": "58719f1fb223330affcec1287d4abf641d8f536500293025dbd5afc6c73d16be",
          "size_bytes": 4553,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/58719f1fb223330affcec1287d4abf641d8f536500293025dbd5afc6c73d16be",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/verdict.json",
          "record_count": 1,
          "sha256": "a7bd2ff9aae1dd62e6579dd0fd7eeb420be2d3c4ddd59ac96c93861aa1fd5ecf",
          "size_bytes": 1766,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/a7bd2ff9aae1dd62e6579dd0fd7eeb420be2d3c4ddd59ac96c93861aa1fd5ecf",
          "status": "captured"
        },
        {
          "first_date": "2026-08-07",
          "last_date": "2026-08-07",
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/manifest.json",
          "record_count": 1,
          "sha256": "82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26",
          "size_bytes": 2535,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26",
          "status": "captured"
        },
        {
          "first_date": "2026-07-01",
          "last_date": "2026-08-06",
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/trades.jsonl",
          "record_count": 69,
          "sha256": "5b445e7cd3a3c3b53db9d58a9333456a151f102d52e735086087c0a59caf83d5",
          "size_bytes": 6000,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/5b445e7cd3a3c3b53db9d58a9333456a151f102d52e735086087c0a59caf83d5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/verdict.json",
          "record_count": 1,
          "sha256": "c3e5e74bff341b76cb2c36abcf929e89253c270678cac61ce7ad4e9946b293ec",
          "size_bytes": 1728,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/c3e5e74bff341b76cb2c36abcf929e89253c270678cac61ce7ad4e9946b293ec",
          "status": "captured"
        },
        {
          "first_date": "2025-01-09",
          "last_date": "2026-09-30",
          "path": "reference/experience/distill_action_log.jsonl",
          "record_count": 110,
          "sha256": "16529725eb2cd529d586a74eaac989ecf47ffe0d3a5cc0b8e2d9ac445ec1ba47",
          "size_bytes": 99945,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/16529725eb2cd529d586a74eaac989ecf47ffe0d3a5cc0b8e2d9ac445ec1ba47",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "reference/experience/research_protocols.yaml",
          "record_count": null,
          "sha256": "0f7c4d1d75174a005dabefe0a03a908ad101a5dcb5b630446b12bf8f8cde7da7",
          "size_bytes": 7262,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/0f7c4d1d75174a005dabefe0a03a908ad101a5dcb5b630446b12bf8f8cde7da7",
          "status": "captured"
        },
        {
          "error": "Expecting value: line 1 column 1 (char 0)",
          "first_date": null,
          "last_date": null,
          "path": "reference/experience/xiaocao_hypotheses.jsonl",
          "record_count": null,
          "sha256": "8b5b0a10a3b55dfc473bd67fce942256b3cae1450e2346d45d5cdfd388a08ddc",
          "size_bytes": 236243,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/8b5b0a10a3b55dfc473bd67fce942256b3cae1450e2346d45d5cdfd388a08ddc",
          "status": "invalid"
        }
      ],
      "missing_patterns": [
        "output/research/weekly_comparison*.json",
        "output/live/posture_calibration.jsonl"
      ],
      "schema_version": 1,
      "sha256": "9ed5036c7f8cac2c0b2cf277c1e6e644933db7684234531faf1d308b79638785",
      "source_semantics": "captured bytes; mtime is never an observation time"
    },
    "limitations": [
      "saved observations are not independent broker/source verification",
      "A/B identical-entry exit difference is descriptive exit evidence, never KOL selection alpha",
      "overlapping 1/4/12-week windows are not independent OOS samples",
      "cash movements are not profit; absent accounting and actual fees remain unknown"
    ],
    "missing_evidence": [
      "reference/experience/xiaocao_hypotheses.jsonl",
      "saved_three_option_paired_comparison_missing"
    ],
    "option_comparison": {
      "comparisons": [],
      "options": [
        {
          "conclusion": "insufficient_evidence",
          "mean_net_ret": null,
          "missing_evidence": [
            "saved_three_option_paired_comparison_missing"
          ],
          "option": "baseline_no_kol"
        },
        {
          "conclusion": "insufficient_evidence",
          "mean_net_ret": null,
          "missing_evidence": [
            "saved_three_option_paired_comparison_missing"
          ],
          "option": "current_bounded"
        },
        {
          "conclusion": "insufficient_evidence",
          "mean_net_ret": null,
          "missing_evidence": [
            "saved_three_option_paired_comparison_missing"
          ],
          "option": "kol_challenger"
        }
      ]
    },
    "paper_fill_audit": {
      "count_semantics": "unique book/code/entry_date/shares/price entries; positions and BUY duplicates merged",
      "invalid_identity_count": 0,
      "limitations": [
        "reported_window is a saved label without original window/hash/clock verification",
        "all legacy labels remain excluded from executable confirmation; comparison originals are verified separately",
        "paper audit is not a no-KOL counterfactual or an alpha estimate"
      ],
      "windows": {
        "12w": {
          "by_book": {
            "A": {
              "reported_window": 38
            },
            "B": {
              "reported_window": 43
            },
            "T": {
              "reported_window": 6
            }
          },
          "confirmed_window_count": 0,
          "end": "2026-10-02",
          "entry_count": 87,
          "excluded_from_confirmed_count": 87,
          "fallback_count": 0,
          "fallback_proportion": 0.0,
          "proxy_count": 0,
          "proxy_proportion": 0.0,
          "reported_window_count": 87,
          "start": "2026-07-11",
          "unknown_count": 0
        },
        "1w": {
          "by_book": {
            "A": {
              "reported_window": 3
            },
            "B": {
              "reported_window": 4
            },
            "T": {
              "reported_window": 2
            }
          },
          "confirmed_window_count": 0,
          "end": "2026-10-02",
          "entry_count": 9,
          "excluded_from_confirmed_count": 9,
          "fallback_count": 0,
          "fallback_proportion": 0.0,
          "proxy_count": 0,
          "proxy_proportion": 0.0,
          "reported_window_count": 9,
          "start": "2026-09-26",
          "unknown_count": 0
        },
        "4w": {
          "by_book": {
            "A": {
              "reported_window": 10
            },
            "B": {
              "reported_window": 13
            },
            "T": {
              "reported_window": 3
            }
          },
          "confirmed_window_count": 0,
          "end": "2026-10-02",
          "entry_count": 26,
          "excluded_from_confirmed_count": 26,
          "fallback_count": 0,
          "fallback_proportion": 0.0,
          "proxy_count": 0,
          "proxy_proportion": 0.0,
          "reported_window_count": 26,
          "start": "2026-09-05",
          "unknown_count": 0
        }
      }
    },
    "production_observations": {
      "as_of": "2026-10-02",
      "audit": [
        {
          "book": "B",
          "buy_trade_line": 1,
          "code": "000509.XSHE",
          "entry_date": "2026-06-01",
          "historical_repair_annotation": {
            "_rederive_note": "basket 5.08 -> window-vwap fill 4.98 (minute-reconstructed 2026-06-22); Δrealized +320.04"
          },
          "line": 1,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 2,
          "code": "603032.XSHG",
          "entry_date": "2026-06-01",
          "historical_repair_annotation": {
            "_rederive_note": "basket 25.73 -> window-vwap fill 25.3561 (minute-reconstructed 2026-06-22); Δrealized +224.33"
          },
          "line": 2,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 3,
          "code": "000636.XSHE",
          "entry_date": "2026-06-01",
          "historical_repair_annotation": {
            "_rederive_note": "basket 49.96 -> window-vwap fill 49.2249 (minute-reconstructed 2026-06-22); Δrealized +220.55"
          },
          "line": 3,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 4,
          "code": "002457.XSHE",
          "entry_date": "2026-06-02",
          "historical_repair_annotation": {
            "_rederive_note": "basket 12.638 -> window-vwap fill 12.39 (minute-reconstructed 2026-06-22); Δrealized +123.91"
          },
          "line": 4,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 5,
          "code": "000608.XSHE",
          "entry_date": "2026-06-02",
          "historical_repair_annotation": {
            "_rederive_note": "basket 5.029 -> window-vwap fill 4.8953 (minute-reconstructed 2026-06-22); Δrealized +173.30"
          },
          "line": 5,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 6,
          "code": "605277.XSHG",
          "entry_date": "2026-06-02",
          "historical_repair_annotation": {
            "_rederive_note": "basket 25.806 -> window-vwap fill 24.5676 (minute-reconstructed 2026-06-22); Δrealized +247.71"
          },
          "line": 6,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 10,
          "code": "002995.XSHE",
          "entry_date": "2026-06-03",
          "historical_repair_annotation": {
            "_rederive_note": "basket 25.072 -> window-vwap fill 24.7029 (minute-reconstructed 2026-06-22); Δrealized +184.36"
          },
          "line": 7,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 11,
          "code": "600797.XSHG",
          "entry_date": "2026-06-03",
          "historical_repair_annotation": {
            "_rederive_note": "basket 8.037 -> window-vwap fill 7.8743 (minute-reconstructed 2026-06-22); Δrealized +276.28"
          },
          "line": 8,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 12,
          "code": "920190.BJSE",
          "entry_date": "2026-06-03",
          "historical_repair_annotation": {
            "_rederive_note": "basket 34.167 -> window-vwap fill 33.6263 (minute-reconstructed 2026-06-22); Δrealized +216.18"
          },
          "line": 9,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 16,
          "code": "002951.XSHE",
          "entry_date": "2026-06-04",
          "historical_repair_annotation": {
            "_rederive_note": "basket 21.838 -> window-vwap fill 21.517 (minute-reconstructed 2026-06-22); Δrealized +128.47"
          },
          "line": 10,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 17,
          "code": "000881.XSHE",
          "entry_date": "2026-06-04",
          "historical_repair_annotation": {
            "_rederive_note": "basket 8.263 -> window-vwap fill 8.0867 (minute-reconstructed 2026-06-22); Δrealized +176.12"
          },
          "line": 11,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 18,
          "code": "000601.XSHE",
          "entry_date": "2026-06-04",
          "historical_repair_annotation": {
            "_rederive_note": "basket 9.027 -> window-vwap fill 8.8425 (minute-reconstructed 2026-06-22); Δrealized +184.52"
          },
          "line": 12,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 22,
          "code": "300516.XSHE",
          "entry_date": "2026-06-05",
          "historical_repair_annotation": {
            "_rederive_note": "basket 42.636 -> window-vwap fill 41.927 (minute-reconstructed 2026-06-22); Δrealized +141.81"
          },
          "line": 13,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 23,
          "code": "300197.XSHE",
          "entry_date": "2026-06-05",
          "historical_repair_annotation": {
            "_rederive_note": "basket 2.754 -> window-vwap fill 2.6865 (minute-reconstructed 2026-06-22); Δrealized +290.27"
          },
          "line": 14,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 24,
          "code": "600121.XSHG",
          "entry_date": "2026-06-05",
          "historical_repair_annotation": {
            "_rederive_note": "basket 5.753 -> window-vwap fill 5.5654 (minute-reconstructed 2026-06-22); Δrealized +374.84"
          },
          "line": 15,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 27,
          "code": "600255.XSHG",
          "entry_date": "2026-06-08",
          "historical_repair_annotation": {
            "_rederive_note": "basket 4.437 -> window-vwap fill 4.364 (minute-reconstructed 2026-06-22); Δrealized +138.71"
          },
          "line": 16,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 28,
          "code": "600439.XSHG",
          "entry_date": "2026-06-08",
          "historical_repair_annotation": {
            "_rederive_note": "basket 2.693 -> window-vwap fill 2.6458 (minute-reconstructed 2026-06-22); Δrealized +150.41"
          },
          "line": 17,
          "reason": "trade_fee_mismatch",
          "repair_link_status": "unverified_original_to_rederived_link",
          "source": "output/live/positions.jsonl",
          "state": "unknown"
        },
        {
          "book": "B",
          "buy_trade_line": 32,
          "code": "002747.XSHE",
          "entry_date": "2026-06-09",
          "line": 18,
          "maturity": "closed",
          "sell_trade_line": 41,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 33,
          "code": "920088.BJSE",
          "entry_date": "2026-06-09",
          "line": 19,
          "maturity": "closed",
          "sell_trade_line": 42,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 34,
          "code": "920961.BJSE",
          "entry_date": "2026-06-09",
          "line": 20,
          "maturity": "closed",
          "sell_trade_line": 43,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 38,
          "code": "000670.XSHE",
          "entry_date": "2026-06-10",
          "line": 21,
          "maturity": "closed",
          "sell_trade_line": 47,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 39,
          "code": "603859.XSHG",
          "entry_date": "2026-06-10",
          "line": 22,
          "maturity": "closed",
          "sell_trade_line": 49,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 40,
          "code": "002613.XSHE",
          "entry_date": "2026-06-10",
          "line": 23,
          "maturity": "closed",
          "sell_trade_line": 48,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 44,
          "code": "002362.XSHE",
          "entry_date": "2026-06-11",
          "line": 24,
          "maturity": "closed",
          "sell_trade_line": 53,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 45,
          "code": "001696.XSHE",
          "entry_date": "2026-06-11",
          "line": 25,
          "maturity": "closed",
          "sell_trade_line": 54,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 46,
          "code": "603330.XSHG",
          "entry_date": "2026-06-11",
          "line": 26,
          "maturity": "closed",
          "sell_trade_line": 55,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 50,
          "code": "300264.XSHE",
          "entry_date": "2026-06-12",
          "line": 27,
          "maturity": "closed",
          "sell_trade_line": 65,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 51,
          "code": "603886.XSHG",
          "entry_date": "2026-06-12",
          "line": 28,
          "maturity": "closed",
          "sell_trade_line": 66,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 52,
          "code": "600703.XSHG",
          "entry_date": "2026-06-12",
          "line": 29,
          "maturity": "closed",
          "sell_trade_line": 88,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 56,
          "code": "300264.XSHE",
          "entry_date": "2026-06-12",
          "line": 30,
          "maturity": "closed",
          "sell_trade_line": 67,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 57,
          "code": "603886.XSHG",
          "entry_date": "2026-06-12",
          "line": 31,
          "maturity": "closed",
          "sell_trade_line": 68,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 58,
          "code": "600703.XSHG",
          "entry_date": "2026-06-12",
          "line": 32,
          "maturity": "closed",
          "sell_trade_line": 69,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 59,
          "code": "300894.XSHE",
          "entry_date": "2026-06-15",
          "line": 33,
          "maturity": "closed",
          "sell_trade_line": 79,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 60,
          "code": "002490.XSHE",
          "entry_date": "2026-06-15",
          "line": 34,
          "maturity": "closed",
          "sell_trade_line": 80,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 61,
          "code": "000759.XSHE",
          "entry_date": "2026-06-15",
          "line": 35,
          "maturity": "closed",
          "sell_trade_line": 81,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 62,
          "code": "300894.XSHE",
          "entry_date": "2026-06-15",
          "line": 36,
          "maturity": "closed",
          "sell_trade_line": 76,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 63,
          "code": "002490.XSHE",
          "entry_date": "2026-06-15",
          "line": 37,
          "maturity": "closed",
          "sell_trade_line": 77,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 64,
          "code": "000759.XSHE",
          "entry_date": "2026-06-15",
          "line": 38,
          "maturity": "closed",
          "sell_trade_line": 78,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 70,
          "code": "603065.XSHG",
          "entry_date": "2026-06-16",
          "line": 39,
          "maturity": "closed",
          "sell_trade_line": 99,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 71,
          "code": "300377.XSHE",
          "entry_date": "2026-06-16",
          "line": 40,
          "maturity": "closed",
          "sell_trade_line": 100,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 72,
          "code": "600067.XSHG",
          "entry_date": "2026-06-16",
          "line": 41,
          "maturity": "closed",
          "sell_trade_line": 101,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 73,
          "code": "603065.XSHG",
          "entry_date": "2026-06-16",
          "line": 42,
          "maturity": "closed",
          "sell_trade_line": 89,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 74,
          "code": "300377.XSHE",
          "entry_date": "2026-06-16",
          "line": 43,
          "maturity": "closed",
          "sell_trade_line": 90,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 75,
          "code": "600067.XSHG",
          "entry_date": "2026-06-16",
          "line": 44,
          "maturity": "closed",
          "sell_trade_line": 91,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 82,
          "code": "300726.XSHE",
          "entry_date": "2026-06-17",
          "line": 45,
          "maturity": "closed",
          "sell_trade_line": 107,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 83,
          "code": "002263.XSHE",
          "entry_date": "2026-06-17",
          "line": 46,
          "maturity": "closed",
          "sell_trade_line": 108,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 84,
          "code": "600460.XSHG",
          "entry_date": "2026-06-17",
          "line": 47,
          "maturity": "closed",
          "sell_trade_line": 109,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 85,
          "code": "300726.XSHE",
          "entry_date": "2026-06-17",
          "line": 48,
          "maturity": "closed",
          "sell_trade_line": 96,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 86,
          "code": "002263.XSHE",
          "entry_date": "2026-06-17",
          "line": 49,
          "maturity": "closed",
          "sell_trade_line": 97,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 87,
          "code": "600460.XSHG",
          "entry_date": "2026-06-17",
          "line": 50,
          "maturity": "closed",
          "sell_trade_line": 98,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 92,
          "code": "300522.XSHE",
          "entry_date": "2026-06-18",
          "line": 51,
          "maturity": "closed",
          "sell_trade_line": 119,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 93,
          "code": "300411.XSHE",
          "entry_date": "2026-06-18",
          "line": 52,
          "maturity": "closed",
          "sell_trade_line": 120,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 94,
          "code": "300522.XSHE",
          "entry_date": "2026-06-18",
          "line": 53,
          "maturity": "closed",
          "sell_trade_line": 116,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 95,
          "code": "300411.XSHE",
          "entry_date": "2026-06-18",
          "line": 54,
          "maturity": "closed",
          "sell_trade_line": 106,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 102,
          "code": "001282.XSHE",
          "entry_date": "2026-06-22",
          "line": 55,
          "maturity": "closed",
          "sell_trade_line": 128,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 103,
          "code": "000679.XSHE",
          "entry_date": "2026-06-22",
          "line": 56,
          "maturity": "closed",
          "sell_trade_line": 129,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 104,
          "code": "001282.XSHE",
          "entry_date": "2026-06-22",
          "line": 57,
          "maturity": "closed",
          "sell_trade_line": 117,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 105,
          "code": "000679.XSHE",
          "entry_date": "2026-06-22",
          "line": 58,
          "maturity": "closed",
          "sell_trade_line": 118,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 110,
          "code": "300319.XSHE",
          "entry_date": "2026-06-23",
          "line": 59,
          "maturity": "closed",
          "sell_trade_line": 130,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 111,
          "code": "002579.XSHE",
          "entry_date": "2026-06-23",
          "line": 60,
          "maturity": "closed",
          "sell_trade_line": 131,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 112,
          "code": "600545.XSHG",
          "entry_date": "2026-06-23",
          "line": 61,
          "maturity": "closed",
          "sell_trade_line": 132,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 113,
          "code": "300319.XSHE",
          "entry_date": "2026-06-23",
          "line": 62,
          "maturity": "closed",
          "sell_trade_line": 127,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 114,
          "code": "002579.XSHE",
          "entry_date": "2026-06-23",
          "line": 63,
          "maturity": "closed",
          "sell_trade_line": 126,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 115,
          "code": "600545.XSHG",
          "entry_date": "2026-06-23",
          "line": 64,
          "maturity": "closed",
          "sell_trade_line": 125,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 121,
          "code": "920790.BJSE",
          "entry_date": "2026-06-24",
          "line": 65,
          "maturity": "closed",
          "sell_trade_line": 141,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 122,
          "code": "000545.XSHE",
          "entry_date": "2026-06-24",
          "line": 66,
          "maturity": "closed",
          "sell_trade_line": 142,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 123,
          "code": "920790.BJSE",
          "entry_date": "2026-06-24",
          "line": 67,
          "maturity": "closed",
          "sell_trade_line": 139,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 124,
          "code": "000545.XSHE",
          "entry_date": "2026-06-24",
          "line": 68,
          "maturity": "closed",
          "sell_trade_line": 140,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 133,
          "code": "002549.XSHE",
          "entry_date": "2026-06-25",
          "line": 69,
          "maturity": "closed",
          "sell_trade_line": 148,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 134,
          "code": "600488.XSHG",
          "entry_date": "2026-06-25",
          "line": 70,
          "maturity": "closed",
          "sell_trade_line": 149,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 135,
          "code": "603757.XSHG",
          "entry_date": "2026-06-25",
          "line": 71,
          "maturity": "closed",
          "sell_trade_line": 150,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 136,
          "code": "002549.XSHE",
          "entry_date": "2026-06-25",
          "line": 72,
          "maturity": "closed",
          "sell_trade_line": 146,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 137,
          "code": "600488.XSHG",
          "entry_date": "2026-06-25",
          "line": 73,
          "maturity": "closed",
          "sell_trade_line": 145,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 138,
          "code": "603757.XSHG",
          "entry_date": "2026-06-25",
          "line": 74,
          "maturity": "closed",
          "sell_trade_line": 147,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 143,
          "code": "002141.XSHE",
          "entry_date": "2026-06-26",
          "line": 75,
          "maturity": "closed",
          "sell_trade_line": 158,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 144,
          "code": "002141.XSHE",
          "entry_date": "2026-06-26",
          "line": 76,
          "maturity": "closed",
          "sell_trade_line": 157,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 151,
          "code": "002579.XSHE",
          "entry_date": "2026-06-29",
          "line": 77,
          "maturity": "closed",
          "sell_trade_line": 165,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 152,
          "code": "000818.XSHE",
          "entry_date": "2026-06-29",
          "line": 78,
          "maturity": "closed",
          "sell_trade_line": 166,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 153,
          "code": "603661.XSHG",
          "entry_date": "2026-06-29",
          "line": 79,
          "maturity": "closed",
          "sell_trade_line": 167,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 154,
          "code": "002579.XSHE",
          "entry_date": "2026-06-29",
          "line": 80,
          "maturity": "closed",
          "sell_trade_line": 163,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 155,
          "code": "000818.XSHE",
          "entry_date": "2026-06-29",
          "line": 81,
          "maturity": "closed",
          "sell_trade_line": 172,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 156,
          "code": "603661.XSHG",
          "entry_date": "2026-06-29",
          "line": 82,
          "maturity": "closed",
          "sell_trade_line": 164,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 159,
          "code": "603687.XSHG",
          "entry_date": "2026-06-30",
          "line": 83,
          "maturity": "closed",
          "sell_trade_line": 175,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 160,
          "code": "002962.XSHE",
          "entry_date": "2026-06-30",
          "line": 84,
          "maturity": "closed",
          "sell_trade_line": 176,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 161,
          "code": "603687.XSHG",
          "entry_date": "2026-06-30",
          "line": 85,
          "maturity": "closed",
          "sell_trade_line": 173,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 162,
          "code": "002962.XSHE",
          "entry_date": "2026-06-30",
          "line": 86,
          "maturity": "closed",
          "sell_trade_line": 174,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 168,
          "code": "301051.XSHE",
          "entry_date": "2026-07-01",
          "line": 87,
          "maturity": "closed",
          "sell_trade_line": 188,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 169,
          "code": "002866.XSHE",
          "entry_date": "2026-07-01",
          "line": 88,
          "maturity": "closed",
          "sell_trade_line": 189,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 170,
          "code": "301051.XSHE",
          "entry_date": "2026-07-01",
          "line": 89,
          "maturity": "closed",
          "sell_trade_line": 186,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 171,
          "code": "002866.XSHE",
          "entry_date": "2026-07-01",
          "line": 90,
          "maturity": "closed",
          "sell_trade_line": 187,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 177,
          "code": "000100.XSHE",
          "entry_date": "2026-07-02",
          "line": 91,
          "maturity": "closed",
          "sell_trade_line": 199,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 178,
          "code": "002208.XSHE",
          "entry_date": "2026-07-02",
          "line": 92,
          "maturity": "closed",
          "sell_trade_line": 200,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 179,
          "code": "300980.XSHE",
          "entry_date": "2026-07-02",
          "line": 93,
          "maturity": "closed",
          "sell_trade_line": 201,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 180,
          "code": "000100.XSHE",
          "entry_date": "2026-07-02",
          "line": 94,
          "maturity": "closed",
          "sell_trade_line": 196,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 181,
          "code": "002208.XSHE",
          "entry_date": "2026-07-02",
          "line": 95,
          "maturity": "closed",
          "sell_trade_line": 197,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 182,
          "code": "300980.XSHE",
          "entry_date": "2026-07-02",
          "line": 96,
          "maturity": "closed",
          "sell_trade_line": 198,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 183,
          "code": "003816.XSHE",
          "entry_date": "2026-07-02",
          "line": 97,
          "maturity": "closed",
          "sell_trade_line": 426,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 184,
          "code": "601288.XSHG",
          "entry_date": "2026-07-02",
          "line": 98,
          "maturity": "closed",
          "sell_trade_line": 208,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 185,
          "code": "000725.XSHE",
          "entry_date": "2026-07-02",
          "line": 99,
          "maturity": "closed",
          "sell_trade_line": 213,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 190,
          "code": "300651.XSHE",
          "entry_date": "2026-07-03",
          "line": 100,
          "maturity": "closed",
          "sell_trade_line": 214,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 191,
          "code": "002326.XSHE",
          "entry_date": "2026-07-03",
          "line": 101,
          "maturity": "closed",
          "sell_trade_line": 215,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 192,
          "code": "300853.XSHE",
          "entry_date": "2026-07-03",
          "line": 102,
          "maturity": "closed",
          "sell_trade_line": 216,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 193,
          "code": "300651.XSHE",
          "entry_date": "2026-07-03",
          "line": 103,
          "maturity": "closed",
          "sell_trade_line": 212,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 194,
          "code": "002326.XSHE",
          "entry_date": "2026-07-03",
          "line": 104,
          "maturity": "closed",
          "sell_trade_line": 210,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 195,
          "code": "300853.XSHE",
          "entry_date": "2026-07-03",
          "line": 105,
          "maturity": "closed",
          "sell_trade_line": 211,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 202,
          "code": "002458.XSHE",
          "entry_date": "2026-07-06",
          "line": 106,
          "maturity": "closed",
          "sell_trade_line": 225,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 203,
          "code": "002826.XSHE",
          "entry_date": "2026-07-06",
          "line": 107,
          "maturity": "closed",
          "sell_trade_line": 226,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 204,
          "code": "301379.XSHE",
          "entry_date": "2026-07-06",
          "line": 108,
          "maturity": "closed",
          "sell_trade_line": 227,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 205,
          "code": "002458.XSHE",
          "entry_date": "2026-07-06",
          "line": 109,
          "maturity": "closed",
          "sell_trade_line": 223,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 206,
          "code": "002826.XSHE",
          "entry_date": "2026-07-06",
          "line": 110,
          "maturity": "closed",
          "sell_trade_line": 224,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 207,
          "code": "301379.XSHE",
          "entry_date": "2026-07-06",
          "line": 111,
          "maturity": "closed",
          "sell_trade_line": 222,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 209,
          "code": "601728.XSHG",
          "entry_date": "2026-07-06",
          "line": 112,
          "maturity": "closed",
          "sell_trade_line": 431,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 217,
          "code": "688103.XSHG",
          "entry_date": "2026-07-07",
          "line": 113,
          "maturity": "closed",
          "sell_trade_line": 236,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 218,
          "code": "002457.XSHE",
          "entry_date": "2026-07-07",
          "line": 114,
          "maturity": "closed",
          "sell_trade_line": 237,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 219,
          "code": "688103.XSHG",
          "entry_date": "2026-07-07",
          "line": 115,
          "maturity": "closed",
          "sell_trade_line": 234,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 220,
          "code": "002457.XSHE",
          "entry_date": "2026-07-07",
          "line": 116,
          "maturity": "closed",
          "sell_trade_line": 235,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 221,
          "code": "000725.XSHE",
          "entry_date": "2026-07-07",
          "historical_repair_annotation": {
            "ledger_repair_id": "book_t_blocked_2026-07-13_000725.XSHE_2026-07-07"
          },
          "line": 117,
          "maturity": "closed",
          "sell_trade_line": 272,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 228,
          "code": "002607.XSHE",
          "entry_date": "2026-07-08",
          "line": 118,
          "maturity": "closed",
          "sell_trade_line": 246,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 229,
          "code": "002137.XSHE",
          "entry_date": "2026-07-08",
          "line": 119,
          "maturity": "closed",
          "sell_trade_line": 247,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 230,
          "code": "002584.XSHE",
          "entry_date": "2026-07-08",
          "line": 120,
          "maturity": "closed",
          "sell_trade_line": 248,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 231,
          "code": "002607.XSHE",
          "entry_date": "2026-07-08",
          "line": 121,
          "maturity": "closed",
          "sell_trade_line": 244,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 232,
          "code": "002137.XSHE",
          "entry_date": "2026-07-08",
          "line": 122,
          "maturity": "closed",
          "sell_trade_line": 245,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 233,
          "code": "002584.XSHE",
          "entry_date": "2026-07-08",
          "line": 123,
          "maturity": "closed",
          "sell_trade_line": 243,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 238,
          "code": "002520.XSHE",
          "entry_date": "2026-07-09",
          "line": 124,
          "maturity": "closed",
          "sell_trade_line": 257,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 239,
          "code": "600793.XSHG",
          "entry_date": "2026-07-09",
          "line": 125,
          "maturity": "closed",
          "sell_trade_line": 258,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 240,
          "code": "688103.XSHG",
          "entry_date": "2026-07-09",
          "line": 126,
          "maturity": "closed",
          "sell_trade_line": 259,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 241,
          "code": "002520.XSHE",
          "entry_date": "2026-07-09",
          "line": 127,
          "maturity": "closed",
          "sell_trade_line": 255,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 242,
          "code": "600793.XSHG",
          "entry_date": "2026-07-09",
          "line": 128,
          "maturity": "closed",
          "sell_trade_line": 256,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 249,
          "code": "600094.XSHG",
          "entry_date": "2026-07-10",
          "line": 129,
          "maturity": "closed",
          "sell_trade_line": 266,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 250,
          "code": "600288.XSHG",
          "entry_date": "2026-07-10",
          "line": 130,
          "maturity": "closed",
          "sell_trade_line": 267,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 251,
          "code": "003020.XSHE",
          "entry_date": "2026-07-10",
          "line": 131,
          "maturity": "closed",
          "sell_trade_line": 268,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 252,
          "code": "600094.XSHG",
          "entry_date": "2026-07-10",
          "line": 132,
          "maturity": "closed",
          "sell_trade_line": 264,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 253,
          "code": "600288.XSHG",
          "entry_date": "2026-07-10",
          "line": 133,
          "maturity": "closed",
          "sell_trade_line": 265,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 254,
          "code": "003020.XSHE",
          "entry_date": "2026-07-10",
          "line": 134,
          "maturity": "closed",
          "sell_trade_line": 270,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 260,
          "code": "603928.XSHG",
          "entry_date": "2026-07-13",
          "line": 135,
          "maturity": "closed",
          "sell_trade_line": 273,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 261,
          "code": "688106.XSHG",
          "entry_date": "2026-07-13",
          "line": 136,
          "maturity": "closed",
          "sell_trade_line": 274,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 262,
          "code": "603928.XSHG",
          "entry_date": "2026-07-13",
          "line": 137,
          "maturity": "closed",
          "sell_trade_line": 269,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 263,
          "code": "688106.XSHG",
          "entry_date": "2026-07-13",
          "line": 138,
          "maturity": "closed",
          "sell_trade_line": 271,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 275,
          "code": "000725.XSHE",
          "entry_date": "2026-07-15",
          "line": 139,
          "maturity": "closed",
          "sell_trade_line": 280,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 276,
          "code": "300937.XSHE",
          "entry_date": "2026-07-16",
          "line": 140,
          "maturity": "closed",
          "sell_trade_line": 285,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 277,
          "code": "002558.XSHE",
          "entry_date": "2026-07-16",
          "line": 141,
          "maturity": "closed",
          "sell_trade_line": 286,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 278,
          "code": "300937.XSHE",
          "entry_date": "2026-07-16",
          "line": 142,
          "maturity": "closed",
          "sell_trade_line": 283,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 279,
          "code": "002558.XSHE",
          "entry_date": "2026-07-16",
          "line": 143,
          "maturity": "closed",
          "sell_trade_line": 284,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 281,
          "code": "000725.XSHE",
          "entry_date": "2026-07-17",
          "line": 144,
          "maturity": "closed",
          "sell_trade_line": 314,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 282,
          "code": "300665.XSHE",
          "entry_date": "2026-07-17",
          "line": 145,
          "maturity": "closed",
          "sell_trade_line": 287,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 288,
          "code": "300577.XSHE",
          "entry_date": "2026-07-21",
          "line": 146,
          "maturity": "closed",
          "sell_trade_line": 297,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 289,
          "code": "300577.XSHE",
          "entry_date": "2026-07-21",
          "line": 147,
          "maturity": "closed",
          "sell_trade_line": 296,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 290,
          "code": "300534.XSHE",
          "entry_date": "2026-07-22",
          "line": 148,
          "maturity": "closed",
          "sell_trade_line": 303,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 291,
          "code": "600227.XSHG",
          "entry_date": "2026-07-22",
          "line": 149,
          "maturity": "closed",
          "sell_trade_line": 304,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 292,
          "code": "000938.XSHE",
          "entry_date": "2026-07-22",
          "line": 150,
          "maturity": "closed",
          "sell_trade_line": 305,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 293,
          "code": "300534.XSHE",
          "entry_date": "2026-07-22",
          "line": 151,
          "maturity": "closed",
          "sell_trade_line": 301,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 294,
          "code": "600227.XSHG",
          "entry_date": "2026-07-22",
          "line": 152,
          "maturity": "closed",
          "sell_trade_line": 302,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 295,
          "code": "000938.XSHE",
          "entry_date": "2026-07-22",
          "line": 153,
          "maturity": "closed",
          "sell_trade_line": 300,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 298,
          "code": "603123.XSHG",
          "entry_date": "2026-07-23",
          "line": 154,
          "maturity": "closed",
          "sell_trade_line": 309,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 299,
          "code": "603123.XSHG",
          "entry_date": "2026-07-23",
          "line": 155,
          "maturity": "closed",
          "sell_trade_line": 308,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 306,
          "code": "002173.XSHE",
          "entry_date": "2026-07-24",
          "line": 156,
          "maturity": "closed",
          "sell_trade_line": 312,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 307,
          "code": "002173.XSHE",
          "entry_date": "2026-07-24",
          "line": 157,
          "maturity": "closed",
          "sell_trade_line": 321,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 310,
          "code": "300214.XSHE",
          "entry_date": "2026-07-27",
          "line": 158,
          "maturity": "closed",
          "sell_trade_line": 315,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 311,
          "code": "300214.XSHE",
          "entry_date": "2026-07-27",
          "line": 159,
          "maturity": "closed",
          "sell_trade_line": 313,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 316,
          "code": "603580.XSHG",
          "entry_date": "2026-07-29",
          "line": 160,
          "maturity": "closed",
          "sell_trade_line": 328,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 317,
          "code": "300331.XSHE",
          "entry_date": "2026-07-29",
          "line": 161,
          "maturity": "closed",
          "sell_trade_line": 329,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 318,
          "code": "603580.XSHG",
          "entry_date": "2026-07-29",
          "line": 162,
          "maturity": "closed",
          "sell_trade_line": 327,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 319,
          "code": "300331.XSHE",
          "entry_date": "2026-07-29",
          "line": 163,
          "maturity": "closed",
          "sell_trade_line": 326,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 320,
          "code": "000725.XSHE",
          "entry_date": "2026-07-29",
          "line": 164,
          "maturity": "closed",
          "sell_trade_line": 388,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 322,
          "code": "002279.XSHE",
          "entry_date": "2026-07-30",
          "line": 165,
          "maturity": "closed",
          "sell_trade_line": 332,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 323,
          "code": "002173.XSHE",
          "entry_date": "2026-07-30",
          "line": 166,
          "maturity": "closed",
          "sell_trade_line": 333,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 324,
          "code": "002279.XSHE",
          "entry_date": "2026-07-30",
          "line": 167,
          "maturity": "closed",
          "sell_trade_line": 331,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 325,
          "code": "002173.XSHE",
          "entry_date": "2026-07-30",
          "line": 168,
          "maturity": "closed",
          "sell_trade_line": 330,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 334,
          "code": "600712.XSHG",
          "entry_date": "2026-08-06",
          "line": 169,
          "maturity": "closed",
          "sell_trade_line": 340,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 335,
          "code": "603106.XSHG",
          "entry_date": "2026-08-06",
          "line": 170,
          "maturity": "closed",
          "sell_trade_line": 341,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 336,
          "code": "600712.XSHG",
          "entry_date": "2026-08-06",
          "line": 171,
          "maturity": "closed",
          "sell_trade_line": 339,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 337,
          "code": "603106.XSHG",
          "entry_date": "2026-08-06",
          "line": 172,
          "maturity": "closed",
          "sell_trade_line": 342,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 338,
          "code": "600611.XSHG",
          "entry_date": "2026-08-07",
          "line": 173,
          "maturity": "closed",
          "sell_trade_line": 343,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 344,
          "code": "002580.XSHE",
          "entry_date": "2026-08-11",
          "line": 174,
          "maturity": "closed",
          "sell_trade_line": 352,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 345,
          "code": "002762.XSHE",
          "entry_date": "2026-08-11",
          "line": 175,
          "maturity": "closed",
          "sell_trade_line": 353,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 346,
          "code": "002792.XSHE",
          "entry_date": "2026-08-11",
          "line": 176,
          "maturity": "closed",
          "sell_trade_line": 354,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 347,
          "code": "002580.XSHE",
          "entry_date": "2026-08-11",
          "line": 177,
          "maturity": "closed",
          "sell_trade_line": 350,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 348,
          "code": "002762.XSHE",
          "entry_date": "2026-08-11",
          "line": 178,
          "maturity": "closed",
          "sell_trade_line": 351,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 349,
          "code": "002792.XSHE",
          "entry_date": "2026-08-11",
          "line": 179,
          "maturity": "closed",
          "sell_trade_line": 355,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 356,
          "code": "002229.XSHE",
          "entry_date": "2026-08-14",
          "line": 180,
          "maturity": "closed",
          "sell_trade_line": 364,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 357,
          "code": "002396.XSHE",
          "entry_date": "2026-08-14",
          "line": 181,
          "maturity": "closed",
          "sell_trade_line": 365,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 358,
          "code": "300426.XSHE",
          "entry_date": "2026-08-14",
          "line": 182,
          "maturity": "closed",
          "sell_trade_line": 366,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 359,
          "code": "002229.XSHE",
          "entry_date": "2026-08-14",
          "line": 183,
          "maturity": "closed",
          "sell_trade_line": 367,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 360,
          "code": "002396.XSHE",
          "entry_date": "2026-08-14",
          "line": 184,
          "maturity": "closed",
          "sell_trade_line": 362,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 361,
          "code": "300426.XSHE",
          "entry_date": "2026-08-14",
          "line": 185,
          "maturity": "closed",
          "sell_trade_line": 363,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 368,
          "code": "002742.XSHE",
          "entry_date": "2026-08-25",
          "line": 186,
          "maturity": "closed",
          "sell_trade_line": 374,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 369,
          "code": "002742.XSHE",
          "entry_date": "2026-08-25",
          "line": 187,
          "maturity": "closed",
          "sell_trade_line": 381,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 370,
          "code": "000523.XSHE",
          "entry_date": "2026-08-26",
          "line": 188,
          "maturity": "closed",
          "sell_trade_line": 377,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 371,
          "code": "002963.XSHE",
          "entry_date": "2026-08-26",
          "line": 189,
          "maturity": "closed",
          "sell_trade_line": 378,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 372,
          "code": "000523.XSHE",
          "entry_date": "2026-08-26",
          "line": 190,
          "maturity": "closed",
          "sell_trade_line": 376,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 373,
          "code": "002963.XSHE",
          "entry_date": "2026-08-26",
          "line": 191,
          "maturity": "closed",
          "sell_trade_line": 375,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 379,
          "code": "001309.XSHE",
          "entry_date": "2026-08-28",
          "line": 192,
          "maturity": "closed",
          "sell_trade_line": 383,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 380,
          "code": "001309.XSHE",
          "entry_date": "2026-08-28",
          "line": 193,
          "maturity": "closed",
          "sell_trade_line": 382,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 384,
          "code": "002349.XSHE",
          "entry_date": "2026-09-01",
          "line": 194,
          "maturity": "closed",
          "sell_trade_line": 387,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 385,
          "code": "002349.XSHE",
          "entry_date": "2026-09-01",
          "line": 195,
          "maturity": "closed",
          "sell_trade_line": 386,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 389,
          "code": "600059.XSHG",
          "entry_date": "2026-09-07",
          "line": 196,
          "maturity": "closed",
          "sell_trade_line": 393,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 390,
          "code": "600059.XSHG",
          "entry_date": "2026-09-07",
          "line": 197,
          "maturity": "closed",
          "sell_trade_line": 394,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 391,
          "code": "000725.XSHE",
          "entry_date": "2026-09-07",
          "line": 198,
          "maturity": "immature",
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 392,
          "code": "600371.XSHG",
          "entry_date": "2026-09-08",
          "line": 199,
          "maturity": "closed",
          "sell_trade_line": 395,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 396,
          "code": "001299.XSHE",
          "entry_date": "2026-09-11",
          "line": 200,
          "maturity": "closed",
          "sell_trade_line": 398,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 397,
          "code": "001299.XSHE",
          "entry_date": "2026-09-11",
          "line": 201,
          "maturity": "closed",
          "sell_trade_line": 399,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 400,
          "code": "002522.XSHE",
          "entry_date": "2026-09-16",
          "line": 202,
          "maturity": "closed",
          "sell_trade_line": 409,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 401,
          "code": "000572.XSHE",
          "entry_date": "2026-09-16",
          "line": 203,
          "maturity": "closed",
          "sell_trade_line": 410,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 402,
          "code": "002522.XSHE",
          "entry_date": "2026-09-16",
          "line": 204,
          "maturity": "closed",
          "sell_trade_line": 411,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 403,
          "code": "000572.XSHE",
          "entry_date": "2026-09-16",
          "line": 205,
          "maturity": "closed",
          "sell_trade_line": 412,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 404,
          "code": "002212.XSHE",
          "entry_date": "2026-09-17",
          "line": 206,
          "maturity": "closed",
          "sell_trade_line": 414,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 405,
          "code": "001209.XSHE",
          "entry_date": "2026-09-17",
          "line": 207,
          "maturity": "closed",
          "sell_trade_line": 413,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 406,
          "code": "002585.XSHE",
          "entry_date": "2026-09-17",
          "line": 208,
          "maturity": "closed",
          "sell_trade_line": 415,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 407,
          "code": "002212.XSHE",
          "entry_date": "2026-09-17",
          "line": 209,
          "maturity": "closed",
          "sell_trade_line": 416,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 408,
          "code": "001209.XSHE",
          "entry_date": "2026-09-17",
          "line": 210,
          "maturity": "closed",
          "sell_trade_line": 417,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 418,
          "code": "301520.XSHE",
          "entry_date": "2026-09-21",
          "line": 211,
          "maturity": "closed",
          "sell_trade_line": 420,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 419,
          "code": "301520.XSHE",
          "entry_date": "2026-09-21",
          "line": 212,
          "maturity": "closed",
          "sell_trade_line": 421,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 422,
          "code": "600371.XSHG",
          "entry_date": "2026-09-28",
          "line": 213,
          "maturity": "closed",
          "sell_trade_line": 433,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 423,
          "code": "301560.XSHE",
          "entry_date": "2026-09-28",
          "line": 214,
          "maturity": "immature",
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 424,
          "code": "600371.XSHG",
          "entry_date": "2026-09-28",
          "line": 215,
          "maturity": "closed",
          "sell_trade_line": 434,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 425,
          "code": "301560.XSHE",
          "entry_date": "2026-09-28",
          "line": 216,
          "maturity": "closed",
          "sell_trade_line": 435,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 427,
          "code": "600050.XSHG",
          "entry_date": "2026-09-28",
          "line": 217,
          "maturity": "immature",
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 428,
          "code": "603042.XSHG",
          "entry_date": "2026-09-29",
          "line": 218,
          "maturity": "closed",
          "sell_trade_line": 436,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 429,
          "code": "301382.XSHE",
          "entry_date": "2026-09-29",
          "line": 219,
          "maturity": "closed",
          "sell_trade_line": 437,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 430,
          "code": "603042.XSHG",
          "entry_date": "2026-09-29",
          "line": 220,
          "maturity": "closed",
          "sell_trade_line": 438,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 432,
          "code": "601868.XSHG",
          "entry_date": "2026-09-29",
          "line": 221,
          "maturity": "immature",
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "line": 7,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 8,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 9,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 13,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 14,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 15,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 19,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 20,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 21,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 25,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 26,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 29,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 30,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 31,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 35,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 36,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        },
        {
          "line": 37,
          "reason": "unmatched_trade",
          "source": "output/live/paper_trades.jsonl",
          "state": "unknown"
        }
      ],
      "books": {
        "A": {
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
          "closed_cash_net_change": 32622.24,
          "closed_lots": 90,
          "entry_fee": 178.26,
          "exit_fee": 181.57,
          "mean_closed_lot_return_pct": 1.061778847913888,
          "open_lots": 0,
          "valid_lots": 90
        },
        "B": {
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
          "closed_cash_net_change": 33529.65,
          "closed_lots": 102,
          "entry_fee": 205.69,
          "exit_fee": 205.93,
          "mean_closed_lot_return_pct": 0.9283914677825688,
          "open_lots": 1,
          "valid_lots": 103
        },
        "T": {
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
          "closed_cash_net_change": -1010.9,
          "closed_lots": 8,
          "entry_fee": 10.03,
          "exit_fee": 7.02,
          "mean_closed_lot_return_pct": -1.769757470510693,
          "open_lots": 3,
          "valid_lots": 11
        }
      },
      "counts": {
        "bad": 0,
        "closed": 200,
        "future": 0,
        "immature": 4,
        "unknown": 17,
        "unknown_trades": 17,
        "valid": 204
      },
      "fill_basis_counts": {
        "basket": 9,
        "open_reference": 21,
        "opening_window_capped_by_basket": 3,
        "opening_window_vwap_capped_by_limit": 171
      },
      "latest_record_date": "2026-09-30",
      "limitations": [
        "Legacy date/naive clocks lack verified availability time and timezone; no intraday timeliness proof.",
        "Modeled paper fees and cash changes are not actual broker fees, executable alpha or portfolio NAV.",
        "A/B identical-entry closed-lot comparison has selection/censoring bias and is not KOL alpha.",
        "No no-KOL/current/challenger strategy runs inferred; no source truth repaired."
      ],
      "paired_exit_comparison": {
        "censored": 1,
        "eligible": 50,
        "entry_mismatch": 38,
        "excluded": 54,
        "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
        "mean_b_minus_a_pp": 0.5720159131454873,
        "open": 1,
        "pairs": [
          {
            "b_minus_a_pp": 0.0,
            "code": "000523.XSHE",
            "entry_date": "2026-08-26"
          },
          {
            "b_minus_a_pp": 0.24807928612712257,
            "code": "000572.XSHE",
            "entry_date": "2026-09-16"
          },
          {
            "b_minus_a_pp": -1.5509156635710475,
            "code": "000938.XSHE",
            "entry_date": "2026-07-22"
          },
          {
            "b_minus_a_pp": -1.82404613140212,
            "code": "001209.XSHE",
            "entry_date": "2026-09-17"
          },
          {
            "b_minus_a_pp": 0.08242960162084592,
            "code": "001299.XSHE",
            "entry_date": "2026-09-11"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "001309.XSHE",
            "entry_date": "2026-08-28"
          },
          {
            "b_minus_a_pp": -0.5123225573939615,
            "code": "002137.XSHE",
            "entry_date": "2026-07-08"
          },
          {
            "b_minus_a_pp": 1.751625371332378,
            "code": "002173.XSHE",
            "entry_date": "2026-07-24"
          },
          {
            "b_minus_a_pp": -1.2365183278445877,
            "code": "002173.XSHE",
            "entry_date": "2026-07-30"
          },
          {
            "b_minus_a_pp": -0.9844584286803967,
            "code": "002208.XSHE",
            "entry_date": "2026-07-02"
          },
          {
            "b_minus_a_pp": -0.14696094252215317,
            "code": "002212.XSHE",
            "entry_date": "2026-09-17"
          },
          {
            "b_minus_a_pp": -8.602677385065107,
            "code": "002229.XSHE",
            "entry_date": "2026-08-14"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "002279.XSHE",
            "entry_date": "2026-07-30"
          },
          {
            "b_minus_a_pp": 5.75942828777017,
            "code": "002326.XSHE",
            "entry_date": "2026-07-03"
          },
          {
            "b_minus_a_pp": -0.26665064535341554,
            "code": "002349.XSHE",
            "entry_date": "2026-09-01"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "002396.XSHE",
            "entry_date": "2026-08-14"
          },
          {
            "b_minus_a_pp": -0.22109443588215297,
            "code": "002458.XSHE",
            "entry_date": "2026-07-06"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "002522.XSHE",
            "entry_date": "2026-09-16"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "002558.XSHE",
            "entry_date": "2026-07-16"
          },
          {
            "b_minus_a_pp": -5.516801801150414,
            "code": "002579.XSHE",
            "entry_date": "2026-06-29"
          },
          {
            "b_minus_a_pp": 0.04635166078000575,
            "code": "002580.XSHE",
            "entry_date": "2026-08-11"
          },
          {
            "b_minus_a_pp": 12.996525663526631,
            "code": "002742.XSHE",
            "entry_date": "2026-08-25"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "002762.XSHE",
            "entry_date": "2026-08-11"
          },
          {
            "b_minus_a_pp": 4.609103507726937,
            "code": "002792.XSHE",
            "entry_date": "2026-08-11"
          },
          {
            "b_minus_a_pp": 0.05590136762695899,
            "code": "002826.XSHE",
            "entry_date": "2026-07-06"
          },
          {
            "b_minus_a_pp": 3.407598948203156,
            "code": "002963.XSHE",
            "entry_date": "2026-08-26"
          },
          {
            "b_minus_a_pp": 1.1277474837153636,
            "code": "300214.XSHE",
            "entry_date": "2026-07-27"
          },
          {
            "b_minus_a_pp": 2.6429541602216338,
            "code": "300331.XSHE",
            "entry_date": "2026-07-29"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "300426.XSHE",
            "entry_date": "2026-08-14"
          },
          {
            "b_minus_a_pp": -0.07686636781954571,
            "code": "300534.XSHE",
            "entry_date": "2026-07-22"
          },
          {
            "b_minus_a_pp": 6.963784496980651,
            "code": "300577.XSHE",
            "entry_date": "2026-07-21"
          },
          {
            "b_minus_a_pp": -0.10429660248815681,
            "code": "300651.XSHE",
            "entry_date": "2026-07-03"
          },
          {
            "b_minus_a_pp": 9.868310587867784,
            "code": "300853.XSHE",
            "entry_date": "2026-07-03"
          },
          {
            "b_minus_a_pp": 1.8019177668840358,
            "code": "300937.XSHE",
            "entry_date": "2026-07-16"
          },
          {
            "b_minus_a_pp": -0.0612596203128733,
            "code": "300980.XSHE",
            "entry_date": "2026-07-02"
          },
          {
            "b_minus_a_pp": 0.6301697126370086,
            "code": "301379.XSHE",
            "entry_date": "2026-07-06"
          },
          {
            "b_minus_a_pp": 0.3539085728812919,
            "code": "301520.XSHE",
            "entry_date": "2026-09-21"
          },
          {
            "b_minus_a_pp": -0.10687346784138903,
            "code": "600059.XSHG",
            "entry_date": "2026-09-07"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "600227.XSHG",
            "entry_date": "2026-07-22"
          },
          {
            "b_minus_a_pp": 0.06620993154995071,
            "code": "600371.XSHG",
            "entry_date": "2026-09-28"
          },
          {
            "b_minus_a_pp": 0.5426480408438968,
            "code": "600712.XSHG",
            "entry_date": "2026-08-06"
          },
          {
            "b_minus_a_pp": -0.12871204274502723,
            "code": "603042.XSHG",
            "entry_date": "2026-09-29"
          },
          {
            "b_minus_a_pp": -3.578254252091518,
            "code": "603106.XSHG",
            "entry_date": "2026-08-06"
          },
          {
            "b_minus_a_pp": 0.11240013532151873,
            "code": "603123.XSHG",
            "entry_date": "2026-07-23"
          },
          {
            "b_minus_a_pp": 0.0,
            "code": "603580.XSHG",
            "entry_date": "2026-07-29"
          },
          {
            "b_minus_a_pp": 1.2402978575498722,
            "code": "603661.XSHG",
            "entry_date": "2026-06-29"
          },
          {
            "b_minus_a_pp": 0.10943777709987154,
            "code": "603757.XSHG",
            "entry_date": "2026-06-25"
          },
          {
            "b_minus_a_pp": 0.4119457543105079,
            "code": "603928.XSHG",
            "entry_date": "2026-07-13"
          },
          {
            "b_minus_a_pp": -1.1489290087455097,
            "code": "688103.XSHG",
            "entry_date": "2026-07-07"
          },
          {
            "b_minus_a_pp": -0.1603426343938514,
            "code": "688106.XSHG",
            "entry_date": "2026-07-13"
          }
        ],
        "unknown_lots": 17,
        "unmatched": 15
      },
      "sources": [
        {
          "latest_record_date": "2026-09-30",
          "parsed_records": 221,
          "path": "output/live/positions.jsonl",
          "sha256": "b45115d2ed9e8072f13675f4158f41eaa28c8b12953188ae954f0870ac990a60",
          "status": "captured"
        },
        {
          "latest_record_date": "2026-09-30",
          "parsed_records": 438,
          "path": "output/live/paper_trades.jsonl",
          "sha256": "7a77cdd43cedc145bc8a5beef3405bb202c52fd5f94a4ec82f568478bb6254c2",
          "status": "captured"
        }
      ],
      "staleness_calendar_days": 2,
      "timeliness_proven": false,
      "windows": {
        "12w": {
          "books": {
            "A": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": 35139.04,
              "closed_lots": 38,
              "entry_fee": 118.19,
              "exit_fee": 121.74,
              "mean_closed_lot_return_pct": 2.6199854015333788,
              "open_lots": 0,
              "valid_lots": 38
            },
            "B": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": 31662.17,
              "closed_lots": 42,
              "entry_fee": 140.58,
              "exit_fee": 140.57,
              "mean_closed_lot_return_pct": 1.9326390942861074,
              "open_lots": 1,
              "valid_lots": 43
            },
            "T": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": -1842.13,
              "closed_lots": 3,
              "entry_fee": 5.21,
              "exit_fee": 2.13,
              "mean_closed_lot_return_pct": -7.414706214012722,
              "open_lots": 3,
              "valid_lots": 6
            }
          },
          "end": "2026-10-02",
          "latest_data_before_window": false,
          "paired_exit_comparison": {
            "censored": 1,
            "eligible": 37,
            "entry_mismatch": 0,
            "excluded": 6,
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
            "mean_b_minus_a_pp": 0.5266597978750314,
            "open": 1,
            "pairs": [
              {
                "b_minus_a_pp": 0.0,
                "code": "000523.XSHE",
                "entry_date": "2026-08-26"
              },
              {
                "b_minus_a_pp": 0.24807928612712257,
                "code": "000572.XSHE",
                "entry_date": "2026-09-16"
              },
              {
                "b_minus_a_pp": -1.5509156635710475,
                "code": "000938.XSHE",
                "entry_date": "2026-07-22"
              },
              {
                "b_minus_a_pp": -1.82404613140212,
                "code": "001209.XSHE",
                "entry_date": "2026-09-17"
              },
              {
                "b_minus_a_pp": 0.08242960162084592,
                "code": "001299.XSHE",
                "entry_date": "2026-09-11"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "001309.XSHE",
                "entry_date": "2026-08-28"
              },
              {
                "b_minus_a_pp": 1.751625371332378,
                "code": "002173.XSHE",
                "entry_date": "2026-07-24"
              },
              {
                "b_minus_a_pp": -1.2365183278445877,
                "code": "002173.XSHE",
                "entry_date": "2026-07-30"
              },
              {
                "b_minus_a_pp": -0.14696094252215317,
                "code": "002212.XSHE",
                "entry_date": "2026-09-17"
              },
              {
                "b_minus_a_pp": -8.602677385065107,
                "code": "002229.XSHE",
                "entry_date": "2026-08-14"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "002279.XSHE",
                "entry_date": "2026-07-30"
              },
              {
                "b_minus_a_pp": -0.26665064535341554,
                "code": "002349.XSHE",
                "entry_date": "2026-09-01"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "002396.XSHE",
                "entry_date": "2026-08-14"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "002522.XSHE",
                "entry_date": "2026-09-16"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "002558.XSHE",
                "entry_date": "2026-07-16"
              },
              {
                "b_minus_a_pp": 0.04635166078000575,
                "code": "002580.XSHE",
                "entry_date": "2026-08-11"
              },
              {
                "b_minus_a_pp": 12.996525663526631,
                "code": "002742.XSHE",
                "entry_date": "2026-08-25"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "002762.XSHE",
                "entry_date": "2026-08-11"
              },
              {
                "b_minus_a_pp": 4.609103507726937,
                "code": "002792.XSHE",
                "entry_date": "2026-08-11"
              },
              {
                "b_minus_a_pp": 3.407598948203156,
                "code": "002963.XSHE",
                "entry_date": "2026-08-26"
              },
              {
                "b_minus_a_pp": 1.1277474837153636,
                "code": "300214.XSHE",
                "entry_date": "2026-07-27"
              },
              {
                "b_minus_a_pp": 2.6429541602216338,
                "code": "300331.XSHE",
                "entry_date": "2026-07-29"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "300426.XSHE",
                "entry_date": "2026-08-14"
              },
              {
                "b_minus_a_pp": -0.07686636781954571,
                "code": "300534.XSHE",
                "entry_date": "2026-07-22"
              },
              {
                "b_minus_a_pp": 6.963784496980651,
                "code": "300577.XSHE",
                "entry_date": "2026-07-21"
              },
              {
                "b_minus_a_pp": 1.8019177668840358,
                "code": "300937.XSHE",
                "entry_date": "2026-07-16"
              },
              {
                "b_minus_a_pp": 0.3539085728812919,
                "code": "301520.XSHE",
                "entry_date": "2026-09-21"
              },
              {
                "b_minus_a_pp": -0.10687346784138903,
                "code": "600059.XSHG",
                "entry_date": "2026-09-07"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "600227.XSHG",
                "entry_date": "2026-07-22"
              },
              {
                "b_minus_a_pp": 0.06620993154995071,
                "code": "600371.XSHG",
                "entry_date": "2026-09-28"
              },
              {
                "b_minus_a_pp": 0.5426480408438968,
                "code": "600712.XSHG",
                "entry_date": "2026-08-06"
              },
              {
                "b_minus_a_pp": -0.12871204274502723,
                "code": "603042.XSHG",
                "entry_date": "2026-09-29"
              },
              {
                "b_minus_a_pp": -3.578254252091518,
                "code": "603106.XSHG",
                "entry_date": "2026-08-06"
              },
              {
                "b_minus_a_pp": 0.11240013532151873,
                "code": "603123.XSHG",
                "entry_date": "2026-07-23"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "603580.XSHG",
                "entry_date": "2026-07-29"
              },
              {
                "b_minus_a_pp": 0.4119457543105079,
                "code": "603928.XSHG",
                "entry_date": "2026-07-13"
              },
              {
                "b_minus_a_pp": -0.1603426343938514,
                "code": "688106.XSHG",
                "entry_date": "2026-07-13"
              }
            ],
            "unknown_lots": 0,
            "unmatched": 5
          },
          "start": "2026-07-11",
          "status": "observed",
          "valid_lots": 87
        },
        "1w": {
          "books": {
            "A": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": 2289.71,
              "closed_lots": 3,
              "entry_fee": 9.82,
              "exit_fee": 10.05,
              "mean_closed_lot_return_pct": 2.469304689373567,
              "open_lots": 0,
              "valid_lots": 3
            },
            "B": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": -4315.25,
              "closed_lots": 3,
              "entry_fee": 13.27,
              "exit_fee": 9.61,
              "mean_closed_lot_return_pct": -4.2241404244940775,
              "open_lots": 1,
              "valid_lots": 4
            },
            "T": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": null,
              "closed_lots": 0,
              "entry_fee": 2.22,
              "exit_fee": null,
              "mean_closed_lot_return_pct": null,
              "open_lots": 2,
              "valid_lots": 2
            }
          },
          "end": "2026-10-02",
          "latest_data_before_window": false,
          "paired_exit_comparison": {
            "censored": 1,
            "eligible": 2,
            "entry_mismatch": 0,
            "excluded": 2,
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
            "mean_b_minus_a_pp": -0.03125105559753826,
            "open": 1,
            "pairs": [
              {
                "b_minus_a_pp": 0.06620993154995071,
                "code": "600371.XSHG",
                "entry_date": "2026-09-28"
              },
              {
                "b_minus_a_pp": -0.12871204274502723,
                "code": "603042.XSHG",
                "entry_date": "2026-09-29"
              }
            ],
            "unknown_lots": 0,
            "unmatched": 1
          },
          "start": "2026-09-26",
          "status": "observed",
          "valid_lots": 9
        },
        "4w": {
          "books": {
            "A": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": 3324.29,
              "closed_lots": 10,
              "entry_fee": 39.33,
              "exit_fee": 39.66,
              "mean_closed_lot_return_pct": 1.1548350213671728,
              "open_lots": 0,
              "valid_lots": 10
            },
            "B": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": -4074.25,
              "closed_lots": 12,
              "entry_fee": 51.54,
              "exit_fee": 47.92,
              "mean_closed_lot_return_pct": -1.0400737308083536,
              "open_lots": 1,
              "valid_lots": 13
            },
            "T": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": null,
              "closed_lots": 0,
              "entry_fee": 2.9,
              "exit_fee": null,
              "mean_closed_lot_return_pct": null,
              "open_lots": 3,
              "valid_lots": 3
            }
          },
          "end": "2026-10-02",
          "latest_data_before_window": false,
          "paired_exit_comparison": {
            "censored": 1,
            "eligible": 9,
            "entry_mismatch": 0,
            "excluded": 4,
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
            "mean_b_minus_a_pp": -0.16177391025905313,
            "open": 1,
            "pairs": [
              {
                "b_minus_a_pp": 0.24807928612712257,
                "code": "000572.XSHE",
                "entry_date": "2026-09-16"
              },
              {
                "b_minus_a_pp": -1.82404613140212,
                "code": "001209.XSHE",
                "entry_date": "2026-09-17"
              },
              {
                "b_minus_a_pp": 0.08242960162084592,
                "code": "001299.XSHE",
                "entry_date": "2026-09-11"
              },
              {
                "b_minus_a_pp": -0.14696094252215317,
                "code": "002212.XSHE",
                "entry_date": "2026-09-17"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "002522.XSHE",
                "entry_date": "2026-09-16"
              },
              {
                "b_minus_a_pp": 0.3539085728812919,
                "code": "301520.XSHE",
                "entry_date": "2026-09-21"
              },
              {
                "b_minus_a_pp": -0.10687346784138903,
                "code": "600059.XSHG",
                "entry_date": "2026-09-07"
              },
              {
                "b_minus_a_pp": 0.06620993154995071,
                "code": "600371.XSHG",
                "entry_date": "2026-09-28"
              },
              {
                "b_minus_a_pp": -0.12871204274502723,
                "code": "603042.XSHG",
                "entry_date": "2026-09-29"
              }
            ],
            "unknown_lots": 0,
            "unmatched": 3
          },
          "start": "2026-09-05",
          "status": "observed",
          "valid_lots": 26
        }
      }
    },
    "promotion": {
      "auto_promote": false,
      "changes_strategy": false,
      "writes_verdict_ledger": false
    },
    "research_runs": [
      {
        "conclusion": "insufficient_evidence",
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
        "hypothesis_id": "aux_gray_n_fixed",
        "missing_evidence": [
          "paired_cost_fill_chronology_comparison_missing"
        ],
        "n_days": 9,
        "n_rows": 9,
        "observed_date": "2026-07-10",
        "parameters": {
          "alpha": 0.05,
          "cache_only": true,
          "min_days": 8,
          "n_tried": 6
        },
        "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/manifest.json",
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
        "recorded_verdict": "REJECTED",
        "scope": "recorded_run_not_a_new_research_verdict",
        "sha256": "b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6"
      },
      {
        "conclusion": "insufficient_evidence",
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
        "hypothesis_id": "aux_gray_relay1_fixed",
        "missing_evidence": [
          "paired_cost_fill_chronology_comparison_missing"
        ],
        "n_days": 25,
        "n_rows": 25,
        "observed_date": "2026-07-10",
        "parameters": {
          "alpha": 0.05,
          "cache_only": true,
          "min_days": 8,
          "n_tried": 6
        },
        "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/manifest.json",
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
        "recorded_verdict": "REJECTED",
        "scope": "recorded_run_not_a_new_research_verdict",
        "sha256": "f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381"
      },
      {
        "conclusion": "insufficient_evidence",
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
        "hypothesis_id": "C_mode_rotation_k_survivors",
        "missing_evidence": [
          "paired_cost_fill_chronology_comparison_missing"
        ],
        "n_days": 24,
        "n_rows": 69,
        "observed_date": "2026-08-07",
        "parameters": {
          "alpha": 0.05,
          "cache_only": true,
          "min_days": 8,
          "n_tried": 20
        },
        "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/manifest.json",
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
        "recorded_verdict": "REJECTED",
        "scope": "recorded_run_not_a_new_research_verdict",
        "sha256": "82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26"
      }
    ],
    "schema_version": 1,
    "snapshot_manifest_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/9ed5036c7f8cac2c0b2cf277c1e6e644933db7684234531faf1d308b79638785.manifest.json",
    "status": "insufficient_evidence"
  }
}
```
