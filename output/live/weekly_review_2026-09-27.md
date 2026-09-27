# 小草每周深度复盘 2026-09-27

## 先看结论

- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个；另有 1 条本地工作区提醒，见下一节。
- APP 执行故障复核：未结计划 1，阻断检查点 6，缺失 EOD 0，缺失结算日 3，缺失日复盘 1；逐项核对卖价/买盘/成交窗口及后续买入影响，不能只归为外部状态。
  - 未结 `book-b:2026-09-18:000572.XSHE:SELL:087c4339d890`：unknown / NATIVE_HISTORICAL_STATUS_UNPROVEN；委托 6007019；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=cc009a580503c8aae33288dfa7eec5e60c9c9ea38002a3b5a830857f1172885d）
  - 缺失结算：2026-09-21, 2026-09-22, 2026-09-23
  - 缺失日复盘：2026-09-23
- 整体框架复盘（有证据引用的分析，非收益认证）：暂时保留§2a有界 KOL 判断和全部确定性交易/账户门，但把框架收益命题列为未证实，并优先修复归因证据与点时覆盖的研究设计。1周窗口（9月21至27日）有30个来源上下文快照，却无新发布 KOL 决策；live 早盘9月21/22/23日依次受 native 解锁未证、历史 SELL 6007019 未决和同日 freeze 未证阻断，旧9月18日中性包的引用不是新成交。4周与12周的可用 KOL 资料实际相同：37个已发布决策集中9月6至18日，pause 多为临时且有空候选、过期或晚于早盘的限制，不能证明减少尾部，也不能证明过滤造成可成交上涨损失。纸盘与APP服务端仿真须分别核对；风险标记和 NORMAL 状态不是结算收益，现有窗口 return、归因、执行漏损和错失机会 PnL 均未知。挑战者保留为 authority=0 的入口/模式研究，先建点时完整机会集和相同风险费用配对；不自动改变 freeze、资格、资本、退出或§10 永久参数。三个9月11日起的旧试验截至本次固定库存仍无可核验实际运行，继续跟进，不能把本次复核计为试验完成。
- 结论证据：`output/live/kol_policy/context/fe0debd1eedc3d81990634afd79cb9ea36f13cd87cbeab994cbb5031aad88d58.context.json`（sha256=814bbdc6a1271f110082d908260848b9101c548638ec0e0ce804850ad7ca174a）；`output/live/kol_policy/context/fa08e7dc48a7c79ed54c8f11b3478b4ae5afce911d0a5f2f1942519a3f000b35.context.json`（sha256=31044d77b373da1d675c07c5c31bab5575474cc3ef831408037abb28cfb35040）；`output/live/kol_policy/decisions/kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1.json`（sha256=2b1344f9c406f1f7643ef0bc9cb95e14ea2ebe4f54335fe0ccbedd69b2d9d5a3）；`output/live/kol_policy/decisions/kol-b-live-opening-20260916-pause-adds-329fb25c-v1.json`（sha256=88f4078d1d712a69a8ba52d8c0cf3ff89d66bd29bb85bdb12364a244e58799e5）；`output/live/kol_policy/decisions/kol-b-paper-20260916-morning-pause-astra-v1.json`（sha256=0b1552c2b5b3ed1fb98b77b25f89efa6d8298abcbf9730752f47b95209323d13）；`output/live/kol_policy/decisions/kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1.json`（sha256=31402b91fc41850b048f6ca9956943455c753347c3307e1af458576604aad295）；`output/live/book_b_live_execution/runs/2026-09-16.json`（sha256=be86198021aad0181ec89ccc7f8c02d4b2f378ae3c4f4611dec12a15647965e3）；`output/live/book_b_live_execution/runs/2026-09-17.json`（sha256=e09c1c65486cbb07457c16de481a7cdc70cd46bb34ebc5c1ae5d31340e8e184c）；`output/live/book_b_live_execution/runs/2026-09-18.json`（sha256=a9f4ce03131458160f94ac6920e2f3edfd7c989027515998737c288e73d43989）；`output/live/book_b_live_execution/runs/2026-09-21.json`（sha256=f570a06a088e740d1844ed553b6e3373deca5e354800ea1ea33005ec8c0674a9）；`output/live/book_b_live_execution/runs/2026-09-22.json`（sha256=0612889a545718b5432ec8a087ac32ae6fa0b34d2c9cef11d7fc2a18d100e3a0）；`output/live/book_b_live_execution/runs/2026-09-23.json`（sha256=05a53b630ad838746ac5af432f0ce0b1e2ec890af66f2afa2633c94a15cbc787）；`output/live/book_b_live_execution/book_b_live_decisions.jsonl`（sha256=4a0edd7d2d72b3488378637d88daf31b45234a618960d0a404829d1cf34e1c17）；`output/live/kol_policy/account_risk/live_B.jsonl`（sha256=605f9621120cdb88691eb21eade9fb246c0750fbd0302f3b559b285dbf46f3c1）；`output/live/kol_policy/account_risk/risk_receipts/150a165a0fbcf09f30b0fd4ffaa43a894d89d6fecea6087229881ef6707db5a8.json`（sha256=2b8184ec6b7ccccfc4190dd62b33011d429408113484ac36263f2c609ca4ed62）；`output/live/flywheel_change_ledger.jsonl`（sha256=d67ab9b2eca16498ff7409d59616eda10c84fb9590c9608de9df4059ec37f7f4）
- 待核证据：1/4/12周分别缺同口径首尾结算 NAV、资金流和逐日资本占用；12周标称窗口早于9月6日KOL政策样本，4/12周可用资料相同，不能推断12周效应。；缺 live 委托/成交/费用与 KOL 精确消费的全链对账；6007019 SELL 状态未决，不能假定零成交或终态；缺可量化执行损耗。；paper_consumption 及 consumption.jsonl 固定输入为 missing/invalid，纸盘买入和份额变化须与正式纸盘账本、费用及结算重新绑定，不能只采信决策 rationale 或容器计数。；缺 no-KOL/current/challenger 同 freeze、同合法时点、同整手/资金/费用/退出的反事实，故避免损失、错失上涨、过度过滤和相对收益均未知。；缺模型请求、开始、完成与失败的完整时钟；decision.as_of 至 reviewed_at 不等于模型耗时，29条 live 消费记录缺消费时钟，窗口1周 latency 无观测。；registry_only 只证明已登记作者；9月23日183个索引的报告正文均未载入、远端全量发现不可证，部分历史语义状态仅为当时评估；同源回填和相关叙事需去重，未核验盘后消息不得变仓位事实。；缺上期三个试验的隔离运行、失败、OOS及回滚回执；9月25日计划复核已逾期。
- 比较框架：无 KOL 基线 / 现行有界 KOL / 挑战者；分别检查入口过滤、模式和资金利用率。
- 纸实逐账户分开；1/4/12 周重叠窗口不是独立样本。小样本不宣称因果胜率或稳定收益，不自动推广实盘。
- 旧试验跟进：3 项需先复核（历史状态仅为报告声明），再决定本周最多三个槽位；不自动启动。

## APP 执行故障：证据、五问与修复状态

- **唯一在办修复负责人：本次 weekly deep review 任务。** 原日收盘修复任务已中断；本次只提交确定性的同持仓跨日 SELL 栅栏。原单 `6007019` 仍由精确只读对账处理，且没有周度券商写操作或过期检查点补跑。
- **首个失败事实：**9月18日 14:55:27，海马 `000572.XSHE` 卖出 1,800 股，限价 4.31、订单 `6007019` 已受理，精确日成交和成交表均为 0；14:56/14:57 之后价格走到 4.30/4.29，约剩 4 分半钟。缺当时最优买价、队列和可成交量，不能把限价与零成交直接判成唯一原因。三个 APP 自有 lot 只生成一个收盘判断，另外两个未获同轮完整评估。
- **重复与影响：**9月21、22、23日各自的收盘和 EOD 均因该单 `UNKNOWN` 阻断，共六个检查点，三日 APP 结算缺失。9月23日 14:43 的独立 HARD_STOP `6005091` 对同 lot 卖出 1,800 股，订单/成交/持仓精确证据证明 4.01 成交；它不能证明旧单已终结，也不能把两单合并。9月23日早盘另有 dated freeze 未证明，不能把无新增买入全归因于旧单。最后可核 APP 结算仍是9月17日，现金 13,035.97、NAV 29,410.33、三个自有 lot；随后可用本金、净值、错失上涨与费用无法量化。纸面 Book B/T 的结算与 APP 分开。
- **五问：** (1) 为什么未成交？收盘发单偏晚、4.31 在后续下跌中缺少可成交证明；当时买盘未知。(2) 为什么持续阻断？`已报`/零观察成交缺唯一终态，不能重试或结算。(3) 为什么范围扩大？旧全局 guard 曾挡其他 lot 出口、新 BUY 和 EOD。(4) 为什么修过后又有同 lot 新单？范围收窄后缺跨日同自有 lot 未决 SELL 栅栏。(5) 为什么前次复盘未识别？把 `reconcile_only` 当全问题，代码通过测试与自然生产验证混写，缺跨日重复不变量回归。
- **修复分层：** `e39a3ee` 改卖价使用 bid、收盘提前 14:45 并缩小旧单 guard；`2e14135` 补全所有 lot 决策；这两次已有代码和测试证据，但自然生产仍受旧单未决阻断，不能宣称完整验证。本次 `ae02340` 增加同自有 lot 跨日未决 SELL 栅栏、校验耐久 intent，67 项策略/安全测试通过，实际事件/intent 状态的只读调用返回旧 open plan；**下个合法交易检查点仍需自然生产回读**。外部订单终态保持 `UNKNOWN / reconcile_only`。
- **任务与回执核查：**
  - 9月18日首个失败收盘：任务 `/Users/xuanyue202/.codex/sessions/2026/09/18/rollout-2026-09-18T14-51-23-01a0b348-bc48-7cd3-9335-e493fdcaae45.jsonl` (sha256=a013d8883720f44d360284c38980cfdd5fca9e042d31796d3791a2c34d4df40b)；归档 `output/live/book_b_live_execution/runs/intraday/archive/2026-09-18-closing-20260918T145500360559+0800-48722.json` (sha256=343fcd427df2f55d712a9bd4e2ce84687fbded85daea826b633aa4ae3297fc1c)。
  - 9月18日首个失败 EOD：任务 `/Users/xuanyue202/.codex/sessions/2026/09/18/rollout-2026-09-18T15-11-23-01a0b35b-0bfc-7610-8ecc-6adb00b502ce.jsonl` (sha256=0e140d5031a290914169835c17c5387798fe2264b752318511c81a49fd9aeca4)；归档 `output/live/book_b_live_execution/runs/intraday/archive/2026-09-18-eod-20260918T151622896372+0800-55353.json` (sha256=82760efec3ea21fc9182c45812d13c67f131ea42b62abc60e5ad19282f9b9deb)。
  - 9月23日最新受影响收盘：任务 `/Users/xuanyue202/.codex/sessions/2026/09/23/rollout-2026-09-23T14-41-19-01a0ccff-5104-74a0-9432-be06f32def47.jsonl` (sha256=f727267d164a9cb1cbc7b0a9b0e071e37b5c33a31a520aa50949d03aff5d4694)；归档 `output/live/book_b_live_execution/runs/intraday/archive/2026-09-23-closing-20260923T144500237448+0800-8100.json` (sha256=dc04c365a5ae0edab2672b55c203155990e21b17c88f1d7b67fc3f3b16ba52b5)。
  - 9月23日最新受影响 EOD：任务 `/Users/xuanyue202/.codex/sessions/2026/09/23/rollout-2026-09-23T15-10-34-01a0cd1a-1923-7300-bec9-0b383f495b80.jsonl` (sha256=22a2163b34b8d8829ef4ea8c8fa5351a0147dd729fe92d6a3a91b9d3d11a87d1)；归档 `output/live/book_b_live_execution/runs/intraday/archive/2026-09-23-eod-20260923T153943361913+0800-19100.json` (sha256=ba3f08fbe8662ebf415a56177e501709c49cf7317bf5458de430959653c15254)。
- **晚启动归因：**9月22日 15:12 计划任务先在 Codex backend 以 HTTP 403 失败，后续业务 shell 15:45 才启动；单凭 shell 时间不能证明调度器迟到。用户已说明周四、周五网络问题在修复，本次不另行追查网络。失败任务 `/Users/xuanyue202/.codex/sessions/2026/09/22/rollout-2026-09-22T15-12-16-01a0c7f5-4ab0-7060-be48-9a8662706219.jsonl` (sha256=5b1e8b78c58316249e58ed608dd4b18a04ba8bd2a6742cb72a04547a3a1d0f0d)。

## 需要你看/确认的事项

- **需要确认** `weekly-2026-09-27-kol-paired-evidence-contract`：先建立 KOL 三框架点时配对与完整账户证据契约
- **本地工作区提醒，不是策略判断**：有 3 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl, src/xiaocao/live/app_test_window.py, tests/test_app_preopen_grant.py。

## 这批转录给我的启发
- 本周没有新的高信号转录启发。

## 已经改进/沉淀到哪里
- 没有新的知识层变更。

## 上期试验与失败跟进（先于新增试验，未记录不等于完成）

- `weekly-2026-09-11-baseline_no_kol`：验证本周及后续经济结果主要由既有 ★E、模式、资金与执行门解释，还是 KOL 确有超出少用资金的增量；建立可复放、同信息集、同风险暴露的 no-KOL/current 配对账。
  - 历史状态：needs_evidence_and_design；本周待复核；原复核日：2026-09-25。
  - 跟进结论（报告声明）：已逐项复核 2026-09-11 未启动槽位。本周早盘多次过期 neutral fallback、无可执行 ★E 或 freeze/价格约束支持‘结果首先由既有资格与执行解释’这一竞争解释；但缺配对反事实、完整费用/现金占用和结算，既不能判 no-KOL 胜出，也不能判 KOL 有超额。本次仅完成证据复核，实验仍未运行。
  - 回滚：本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-18；state sha256=e69df29b4c56ae65be585db7780aaa5843a10e233a04a6eb5a67fce8dfd07843。
- `weekly-2026-09-11-current_bounded`：检验现行有界 KOL 是否以更少尾部损失补偿等待、过期、语义歧义与错失机会；重点检验来源条件能否在第一次合法开仓前完成核实，而不是增加 post-morning 中性包数量。
  - 历史状态：needs_evidence_and_design；本周待复核；原复核日：2026-09-25。
  - 跟进结论（报告声明）：已复核旧槽，未发现实际实验运行。新增反证是四个早盘 KOL review 超时，以及 9 月 16 日 10:25 pause 在 11:01 发布、13:25 过期，而可见 APP 引用到 13:26 已为 expired；9 月 17/18 日后续有效 neutral 读取说明覆盖可改善，但不是 alpha 或尾部收益证明。
  - 回滚：本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-18；state sha256=e69df29b4c56ae65be585db7780aaa5843a10e233a04a6eb5a67fce8dfd07843。
- `weekly-2026-09-11-kol_challenger`：检验上游入口或模式集合是否造成局部最优：预登记竞价与盘中模式语义及点时完整机会集，在 authority=0 隔离队列观察正式 freeze 外候选，再比较 no-KOL/current/challenger。
  - 历史状态：needs_evidence_and_design；本周待复核；原复核日：2026-09-25。
  - 跟进结论（报告声明）：已复核旧 challenger 槽，仍只有设计与来源语义，没有候选完整面板、合法成交反事实或 OOS 结果。保留 authority=0 入口/模式覆盖挑战者，但不能称现有过滤过严已经造成可实现损失，更不能以来源点名或涨幅反推新增候选。
  - 回滚：本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-18；state sha256=e69df29b4c56ae65be585db7780aaa5843a10e233a04a6eb5a67fce8dfd07843。

## 整体框架试验槽位（待取证与设计，不是合格变更候选）

- 目标：逐 Book/runtime 重建同日冻结、同整手/风险预算/退出约束的 no-KOL 与现行叠加配对路径；先量化是否存在真实可执行的 KOL 增量，再比较费后收益、左尾、回撤、暴露和现金时间积分。
  - 证伪条件：若点时合法、费用和资金流一致的 OOS 配对显示 KOL 在多个日期/来源聚类下稳定改善净收益或左尾，且不由更少暴露或单一赢家解释，则推翻基线足以解释的命题；证据缺失不判定。
  - 必要证据：分别补齐 live 与 paper 的完整入口 freeze、意图/claim、实际消费时钟、订单与成交/拒绝、T+1、当时报价和费用；UNKNOWN 只记未决，不假定成交或零成交；以相同可用本金、整手、流动性、合法执行时点和退出路径构造 no-KOL/current 配对，过期决策与晚到来源不得事后插入；逐日结算 NAV 与资金流、敞口和现金时间积分，计算费后净收益、最大回撤/左尾、避免损失和错失上涨；按模式、市场阶段、日期及独立来源聚类；预注册 OOS、剔除单一赢家、成本敏感性和最低有效样本，分开 1/4/12 周实际覆盖；未覆盖区间不按零收益处理
  - 回滚：本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。
  - 本次跟进（报告声明）：9月16日 live 早盘旧 pause 已过期并回基线，9月17日同样过期且价格门跳过一只；9月21至23日 live 早盘分别受 native 解锁、历史 SELL 未决和 dated freeze 证据阻断，均无可归给 KOL 的新买决策。纸盘已有风险标记，但固定库存的 paper consumption 源缺失，不能用纸盘成交计数推出叠加收益。上期截至9月18日的配对账试验在本库存仍无运行/回滚回执；旧试验继续，原来9月25日复核已逾期。
  - 负责人：xiaocao weekly review maintainer（隔离研究执行须另经研究门授权）；下次复核：2026-10-02。
- 目标：检验已审阅的有界暂停和中性判断是否在第一合法动作前被消费，并以同风险暴露、同费用反事实衡量减少损失与错失上涨；把来源、模型、审阅、发布、过期和执行延迟分开。
  - 证伪条件：若大部分 pause 没有点时合法的新风险机会、在动作之后才发布/到期，或可执行错失上涨及执行成本抵消左尾改善，则不支持叠加增益；仅增加中性包或消费引用也不支持。
  - 必要证据：逐来源记录 source occurrence/published/received 与每次 request、模型开始/完成、独立 review、published、valid_until、第一合法 consumer 及终态；核对9月15日无可执行候选 pause、9月16日纸盘基线已买和 live 早盘超时、9月17日晚于目标时点的 APP 提交；区分来源迟延、审阅迟延、native/冻结/经纪状态；逐个 pause 标记当时同日冻结候选、可用现金、资格、报价、T+1 和其他风控是否允许新增风险；只在有机会的样本计算净避免损失和机会成本；以完整订单/成交/费用与每日结算 NAV 验证实际影响，并按作者及来源事件聚类；历史相同来源的重复观点、分类回填和宏观共识不能当独立确认
  - 回滚：本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。
  - 本次跟进（报告声明）：9月15日有界 pause 的审核说明当时 freeze 两行均 COLD/非★E，未产生增量订单；9月16日纸盘包明确在两笔基线买入之后发布，live 早盘旧包过期且 rendezvous 超时。9月18日中性包承认八行均 COLD/UNKNOWN。9月21至23日虽有新登记语义，但无新已发布交易判断，旧9月18日包的引用已过期。固定清单没有模型起止遥测、完整 paper consumption 或费用/成交配对，不能把临时暂停称作尾部收益；上期试验未见可核验运行或回滚，须细化时钟与归因。
  - 负责人：xiaocao weekly review maintainer（时钟与 lineage 实现须另行确认负责人）；下次复核：2026-10-02。
- 目标：在 authority=0 隔离研究队列预先定义竞价、9:31 与盘中机会集，检验原入口和模式筛选是否遗漏合法、可成交且有风险调整价值的候选；与 no-KOL 和有界叠加作同本金配对。
  - 证伪条件：若完整点时队列在整手、手续费、流动性、T+1、退出和 OOS 约束后不能同时改善机会覆盖与风险调整结果，或优势来自事后补榜、回填评分、重复来源/单一赢家，则拒绝挑战者；缺数据不判 PASS。
  - 必要证据：冻结每日全体候选及入口前后行数、每一拒绝理由、模式/评分版本、数据可见时间、来源身份与当时环境；区分 COLD、UNKNOWN、BJSE 和真正入口外研究候选；固定竞价、9:31 和有限盘中截面，不搜索最佳秒点或事后阈值；来源示例、回看收益与分类回填只作假设，不生成生产代码；同本金、风险、费用、报价、流动性、整手及退出条件下的 no-KOL/current/challenger 点时回放，含所有失败样本、现金利用率、错失上涨、下行及 OOS；按作者/事件去重并审查小草的稳定型与爆发型模式、退潮期限制和9月21日刘少未具名利好与小草防守框架的条件冲突；未经来源及市场核验不改变任何正式入口
  - 回滚：本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。
  - 本次跟进（报告声明）：9月23日登记上下文有183个报告索引但正文全未载入；118条带 current 状态的观点包含回填/同源重复，不能视作118个独立即时信号。小草9月19日谈早盘低吸窗口、评分不保证与退潮限制，刘少9月21日撤回节前减仓又缺消息名称及期限；这构成需点时核验的竞争假设，不是扩大 Book B 入口的授权。固定清单没有入口外完整候选、成交反事实或 OOS；上期挑战者仍未运行，维持 authority=0 研究设计。
  - 负责人：xiaocao weekly review maintainer（候选完整性研究须另经研究门授权）；下次复核：2026-10-02。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- KOL 固定复盘输入（仅观察，不增加自动落地权限）：output/live/kol_policy/context/*.context.json, output/live/kol_policy/decisions/*.json, output/live/book_b_live_execution/consumption.jsonl, output/live/book_b_live_execution/book_b_live_decisions.jsonl, output/live/book_b_live_execution/runs/*.json, output/live/kol_policy/account_risk/live_B.jsonl, output/live/paper_decision_support/consumption/*.json, output/live/paper_decision_support/consumption.jsonl, output/live/kol_policy/account_risk/risk_receipts/*.json, output/live/flywheel_change_ledger.jsonl, output/live/kol_policy/requests/*.json, output/live/kol_policy/source_verifications/*.json
- APP 执行固定复盘输入（仅观察，不增加策略自动落地权限）：output/live/daily_execution_review_*.md, output/live/book_b_live_execution/events.jsonl, output/live/book_b_live_execution/runs/intraday/archive/*.json, output/live/book_b_live_execution/settlements/*.json
- 提案数量：1
- 自动落地候选数量：0

## 验证
- weekly plan semantic and fixed-inventory hash review: PASS
- tests/test_weekly_kol_review.py: 35 passed
- tests/test_book_b_live_policy.py: 67 passed
- data_doctor.py: OK
- strategy_protocols.py --check: 3 PASS
- git diff --check: PASS

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 139 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-09-27/weekly-2026-09-27-kol-paired-evidence-contract.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 85,
    "candidate_assertions": 205,
    "candidate_to_tested": 0.07,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 139,
    "candidates_untested": 129,
    "dedup_ratio": 0.68,
    "instrumentation_todos": 53,
    "median_recurrence": 1,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 626,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 85
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 7,
  "pre_existing_dirty_sample": [
    " M kronos_screen/HYPOTHESES.jsonl",
    " M src/xiaocao/live/app_test_window.py",
    " M src/xiaocao/live/book_b_live_intraday.py",
    "?? .scratch/book-b-morning-20260916-review/",
    "?? .scratch/kol-classification-backfill-20260921.py",
    "?? .scratch/kol-netdisk-e51919c15179ed8d-content-audit.json",
    "?? tests/test_app_preopen_grant.py"
  ],
  "kol_system_review_status": "completed_review",
  "kol_inventory_sha256": "480b88d24096ba32c3399f8dfbf795b513f78f4939a510272307afc63a143d2e",
  "kol_audit_feedback": {
    "consumption": {
      "live": {
        "book_counts": {
          "B": 110
        },
        "consumption_container_count": 94,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 7,
          "kol-b-live-opening-20260916-pause-adds-329fb25c-v1": 1,
          "kol-b-live-sparse-20260916-1025-pause-7878186a-v1": 1,
          "kol-b-live-sparse-20260916-1325-neutral-3510a357-v1": 25,
          "kol-b-live-sparse-20260917-1025-neutral-d4b2fe7f-v1": 6,
          "kol-b-live-sparse-20260917-1325-neutral-b4cc5ae7-v1": 21,
          "kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1": 17,
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
        "evidence_sha256": "a451c3877e1842f5c2933c4aab86247209b0515bbceb04538615971c05eb113a",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 81,
        "legacy_file_count": 11,
        "missing_consumption_clock_count": 29,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 0,
        "paper_terminal_status_counts": {},
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 81,
        "record_count": 110,
        "reported_execution_status_counts": {},
        "skip_record_count": 0,
        "source_file_count": 25,
        "status": "read",
        "unbound_decision_reference_count": 87
      },
      "paper": {
        "book_counts": {
          "B": 11
        },
        "consumption_container_count": 11,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 1,
          "kol-b-paper-sparse-20260916-1325-neutral-3510a357-v1": 1,
          "kol-b-paper-sparse-20260917-1325-neutral-b4cc5ae7-v1": 1,
          "kol-b-paper-sparse-20260918-1325-neutral-3ae43f5a-v1": 2,
          "kol-b-precheck-20260908-1428-astra-neutral-v1": 1,
          "kol-b-sparse-20260907-1430-astra-neutral-v1": 1,
          "kol-b-sparse-20260909-1325-astra-neutral-38a3f375-v1": 1,
          "kol-b-sparse-20260910-1055-astra-neutral-12b5dc0e-v1": 1,
          "kol-b-sparse-20260914-1325-pause-adds-5903d480-v1": 1,
          "kol-xiaocao-sunday-pilot-20260906-reviewed-v2": 1
        },
        "evidence_sha256": "0cb9f0018c6cb6f4444edb0f9a5885880e408ebe8c21b813ad1c1cf5f8b5b1d2",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 11,
        "legacy_file_count": 0,
        "missing_consumption_clock_count": 11,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 9,
        "paper_terminal_status_counts": {
          "bought": 6,
          "no_buy": 5
        },
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 11,
        "record_count": 11,
        "reported_execution_status_counts": {},
        "skip_record_count": 5,
        "source_file_count": 22,
        "status": "read",
        "unbound_decision_reference_count": 11
      }
    },
    "execution_verification": "not_performed",
    "profit_attribution": "not_established",
    "published_decision_count": 37,
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
      "automatic_launch": false,
      "experiment_id": "weekly-2026-09-11-baseline_no_kol",
      "falsifier": "若点时合法、费用和资金流一致的 OOS 配对显示 KOL 在多个日期/来源聚类下稳定改善净收益或左尾，且不由更少暴露或单一赢家解释，则推翻基线足以解释的命题；证据缺失不判定。",
      "follow_up": {
        "conclusion": "9月16日 live 早盘旧 pause 已过期并回基线，9月17日同样过期且价格门跳过一只；9月21至23日 live 早盘分别受 native 解锁、历史 SELL 未决和 dated freeze 证据阻断，均无可归给 KOL 的新买决策。纸盘已有风险标记，但固定库存的 paper consumption 源缺失，不能用纸盘成交计数推出叠加收益。上期截至9月18日的配对账试验在本库存仍无运行/回滚回执；旧试验继续，原来9月25日复核已逾期。",
        "disposition": "continue",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "d67ab9b2eca16498ff7409d59616eda10c84fb9590c9608de9df4059ec37f7f4"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-16.json",
            "sha256": "be86198021aad0181ec89ccc7f8c02d4b2f378ae3c4f4611dec12a15647965e3"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-17.json",
            "sha256": "e09c1c65486cbb07457c16de481a7cdc70cd46bb34ebc5c1ae5d31340e8e184c"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-21.json",
            "sha256": "f570a06a088e740d1844ed553b6e3373deca5e354800ea1ea33005ec8c0674a9"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-22.json",
            "sha256": "0612889a545718b5432ec8a087ac32ae6fa0b34d2c9cef11d7fc2a18d100e3a0"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-23.json",
            "sha256": "05a53b630ad838746ac5af432f0ce0b1e2ec890af66f2afa2633c94a15cbc787"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "4a0edd7d2d72b3488378637d88daf31b45234a618960d0a404829d1cf34e1c17"
          },
          {
            "path": "output/live/kol_policy/account_risk/live_B.jsonl",
            "sha256": "605f9621120cdb88691eb21eade9fb246c0750fbd0302f3b559b285dbf46f3c1"
          },
          {
            "path": "output/live/kol_policy/account_risk/risk_receipts/150a165a0fbcf09f30b0fd4ffaa43a894d89d6fecea6087229881ef6707db5a8.json",
            "sha256": "2b8184ec6b7ccccfc4190dd62b33011d429408113484ac36263f2c609ca4ed62"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "baseline_no_kol",
      "next_review": "2026-10-02",
      "objective": "逐 Book/runtime 重建同日冻结、同整手/风险预算/退出约束的 no-KOL 与现行叠加配对路径；先量化是否存在真实可执行的 KOL 增量，再比较费后收益、左尾、回撤、暴露和现金时间积分。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（隔离研究执行须另经研究门授权）",
      "required_evidence": [
        "分别补齐 live 与 paper 的完整入口 freeze、意图/claim、实际消费时钟、订单与成交/拒绝、T+1、当时报价和费用；UNKNOWN 只记未决，不假定成交或零成交",
        "以相同可用本金、整手、流动性、合法执行时点和退出路径构造 no-KOL/current 配对，过期决策与晚到来源不得事后插入",
        "逐日结算 NAV 与资金流、敞口和现金时间积分，计算费后净收益、最大回撤/左尾、避免损失和错失上涨；按模式、市场阶段、日期及独立来源聚类",
        "预注册 OOS、剔除单一赢家、成本敏感性和最低有效样本，分开 1/4/12 周实际覆盖；未覆盖区间不按零收益处理"
      ],
      "rollback": "本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。",
      "status": "needs_evidence_and_design"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "automatic_launch": false,
      "experiment_id": "weekly-2026-09-11-current_bounded",
      "falsifier": "若大部分 pause 没有点时合法的新风险机会、在动作之后才发布/到期，或可执行错失上涨及执行成本抵消左尾改善，则不支持叠加增益；仅增加中性包或消费引用也不支持。",
      "follow_up": {
        "conclusion": "9月15日有界 pause 的审核说明当时 freeze 两行均 COLD/非★E，未产生增量订单；9月16日纸盘包明确在两笔基线买入之后发布，live 早盘旧包过期且 rendezvous 超时。9月18日中性包承认八行均 COLD/UNKNOWN。9月21至23日虽有新登记语义，但无新已发布交易判断，旧9月18日包的引用已过期。固定清单没有模型起止遥测、完整 paper consumption 或费用/成交配对，不能把临时暂停称作尾部收益；上期试验未见可核验运行或回滚，须细化时钟与归因。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "d67ab9b2eca16498ff7409d59616eda10c84fb9590c9608de9df4059ec37f7f4"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1.json",
            "sha256": "2b1344f9c406f1f7643ef0bc9cb95e14ea2ebe4f54335fe0ccbedd69b2d9d5a3"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-opening-20260916-pause-adds-329fb25c-v1.json",
            "sha256": "88f4078d1d712a69a8ba52d8c0cf3ff89d66bd29bb85bdb12364a244e58799e5"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-paper-20260916-morning-pause-astra-v1.json",
            "sha256": "0b1552c2b5b3ed1fb98b77b25f89efa6d8298abcbf9730752f47b95209323d13"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1.json",
            "sha256": "31402b91fc41850b048f6ca9956943455c753347c3307e1af458576604aad295"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-16.json",
            "sha256": "be86198021aad0181ec89ccc7f8c02d4b2f378ae3c4f4611dec12a15647965e3"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-17.json",
            "sha256": "e09c1c65486cbb07457c16de481a7cdc70cd46bb34ebc5c1ae5d31340e8e184c"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-18.json",
            "sha256": "a9f4ce03131458160f94ac6920e2f3edfd7c989027515998737c288e73d43989"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "4a0edd7d2d72b3488378637d88daf31b45234a618960d0a404829d1cf34e1c17"
          },
          {
            "path": "output/live/kol_policy/context/fe0debd1eedc3d81990634afd79cb9ea36f13cd87cbeab994cbb5031aad88d58.context.json",
            "sha256": "814bbdc6a1271f110082d908260848b9101c548638ec0e0ce804850ad7ca174a"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "current_bounded",
      "next_review": "2026-10-02",
      "objective": "检验已审阅的有界暂停和中性判断是否在第一合法动作前被消费，并以同风险暴露、同费用反事实衡量减少损失与错失上涨；把来源、模型、审阅、发布、过期和执行延迟分开。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（时钟与 lineage 实现须另行确认负责人）",
      "required_evidence": [
        "逐来源记录 source occurrence/published/received 与每次 request、模型开始/完成、独立 review、published、valid_until、第一合法 consumer 及终态",
        "核对9月15日无可执行候选 pause、9月16日纸盘基线已买和 live 早盘超时、9月17日晚于目标时点的 APP 提交；区分来源迟延、审阅迟延、native/冻结/经纪状态",
        "逐个 pause 标记当时同日冻结候选、可用现金、资格、报价、T+1 和其他风控是否允许新增风险；只在有机会的样本计算净避免损失和机会成本",
        "以完整订单/成交/费用与每日结算 NAV 验证实际影响，并按作者及来源事件聚类；历史相同来源的重复观点、分类回填和宏观共识不能当独立确认"
      ],
      "rollback": "本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。",
      "status": "needs_evidence_and_design"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "automatic_launch": false,
      "experiment_id": "weekly-2026-09-11-kol_challenger",
      "falsifier": "若完整点时队列在整手、手续费、流动性、T+1、退出和 OOS 约束后不能同时改善机会覆盖与风险调整结果，或优势来自事后补榜、回填评分、重复来源/单一赢家，则拒绝挑战者；缺数据不判 PASS。",
      "follow_up": {
        "conclusion": "9月23日登记上下文有183个报告索引但正文全未载入；118条带 current 状态的观点包含回填/同源重复，不能视作118个独立即时信号。小草9月19日谈早盘低吸窗口、评分不保证与退潮限制，刘少9月21日撤回节前减仓又缺消息名称及期限；这构成需点时核验的竞争假设，不是扩大 Book B 入口的授权。固定清单没有入口外完整候选、成交反事实或 OOS；上期挑战者仍未运行，维持 authority=0 研究设计。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "d67ab9b2eca16498ff7409d59616eda10c84fb9590c9608de9df4059ec37f7f4"
          },
          {
            "path": "output/live/kol_policy/context/fa08e7dc48a7c79ed54c8f11b3478b4ae5afce911d0a5f2f1942519a3f000b35.context.json",
            "sha256": "31044d77b373da1d675c07c5c31bab5575474cc3ef831408037abb28cfb35040"
          },
          {
            "path": "output/live/kol_policy/context/fe0debd1eedc3d81990634afd79cb9ea36f13cd87cbeab994cbb5031aad88d58.context.json",
            "sha256": "814bbdc6a1271f110082d908260848b9101c548638ec0e0ce804850ad7ca174a"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1.json",
            "sha256": "2b1344f9c406f1f7643ef0bc9cb95e14ea2ebe4f54335fe0ccbedd69b2d9d5a3"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1.json",
            "sha256": "31402b91fc41850b048f6ca9956943455c753347c3307e1af458576604aad295"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-18.json",
            "sha256": "a9f4ce03131458160f94ac6920e2f3edfd7c989027515998737c288e73d43989"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-23.json",
            "sha256": "05a53b630ad838746ac5af432f0ce0b1e2ec890af66f2afa2633c94a15cbc787"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "kol_challenger",
      "next_review": "2026-10-02",
      "objective": "在 authority=0 隔离研究队列预先定义竞价、9:31 与盘中机会集，检验原入口和模式筛选是否遗漏合法、可成交且有风险调整价值的候选；与 no-KOL 和有界叠加作同本金配对。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（候选完整性研究须另经研究门授权）",
      "required_evidence": [
        "冻结每日全体候选及入口前后行数、每一拒绝理由、模式/评分版本、数据可见时间、来源身份与当时环境；区分 COLD、UNKNOWN、BJSE 和真正入口外研究候选",
        "固定竞价、9:31 和有限盘中截面，不搜索最佳秒点或事后阈值；来源示例、回看收益与分类回填只作假设，不生成生产代码",
        "同本金、风险、费用、报价、流动性、整手及退出条件下的 no-KOL/current/challenger 点时回放，含所有失败样本、现金利用率、错失上涨、下行及 OOS",
        "按作者/事件去重并审查小草的稳定型与爆发型模式、退潮期限制和9月21日刘少未具名利好与小草防守框架的条件冲突；未经来源及市场核验不改变任何正式入口"
      ],
      "rollback": "本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。",
      "status": "needs_evidence_and_design"
    }
  ]
}
```
