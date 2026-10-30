# 小草每周深度复盘 2026-10-30

## 先看结论

- 本周学到：完整机会、实际采用与费用比报告/观点数量更接近可检验增益；工程漏执行是缺样本，不能记作零收益。
- 已应用：逐项回应18个冻结EOD义务；原weekly成功区分sidecar；现有隔离/反馈修复的代码、部署与未来自然验收分开；原三槽继续。
- 暂不晋级：control与no-KOL当前同为98088.45，只有一个模型往返且缺10-28；原15条工具提示保留审计，统一转研究提案。无需重复授权，下一重点是原晨间/EOD自然验收。
- 10-30 EOD feedback原失败导致正式交接/最终摘要缺失；旧日成功不补当日证据。APP最终PnL N/A，Paper/APP/T/模型分开。
- 本周模式：保留提案，证据不足不晋级（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：0 个；另有 1 条本地工作区提醒，见下一节。
- APP 执行故障复核：未结计划 3，阻断检查点 4，缺失 EOD 0，缺失结算日 4，缺失日复盘 0；逐项核对卖价/买盘/成交窗口及后续买入影响，不能只归为外部状态。
  - 未结 `book-b:2026-09-18:000572.XSHE:SELL:087c4339d890`：unknown / NATIVE_HISTORY_QUERY_CAPTURE_INCOMPLETE；委托 6007019；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=5a84e8e5768ae657ce299d7f9275cefed86c7ff8ff5cb6fa368f0d551010b8b4）
  - 未结 `book-b:2026-09-30:301382.XSHE:SELL:9c1cb5e059e5`：unknown / NATIVE_HISTORICAL_STATUS_UNPROVEN；委托 6004811；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=5a84e8e5768ae657ce299d7f9275cefed86c7ff8ff5cb6fa368f0d551010b8b4）
  - 未结 `book-b:2026-10-29:688028.XSHG:BUY`：unknown / NATIVE_EXACT_ORDER_DELTA_NOT_UNIQUE；委托 None；证据 `output/live/book_b_live_execution/events.jsonl`（sha256=5a84e8e5768ae657ce299d7f9275cefed86c7ff8ff5cb6fa368f0d551010b8b4）
  - 缺失结算：2026-10-26, 2026-10-27, 2026-10-29, 2026-10-30

## 每日发现与周度处理

- 冻结每日交接 3 份；待回应 18 项；证据缺口 0 项。
- 上述“0”仅为已保存输入的解析/哈希错误数；10月28日无业务运行、10月30日feedback失败而无正式交接，均未闭合。watch的缺EOD计数仅比较已有archive，不含28日没有archive的漏运行。
- `app-b-actual-fees-and-unclassified-cash`（2026-10-26–2026-10-29，3 次）：当前BUY预留未证，cash_reserve_reconciliation_required/cash_difference null；34单实际费用缺失，最终盈亏N/A。；状态 open。 周度 needs_evidence：29日预留与34单实际费用缺证持续；30日原EOD仍cash_reserve_reconciliation_required，最终PnL不能由估费/差额补齐。严格会计与独立当前准入分别验收。；负责人 native fee/cash evidence owner; xiaocao-daily-eod reconciles；下一步 下一EOD以新鲜同账户现金、owned及潜在预留上界核验准入；原费用/现金owner补逐项来源，保留N/A。；下次 2026-11-06。
- `app-b-current-buy-order-identity-unproven/2026-10-29/688028.XSHG`（2026-10-29–2026-10-29，1 次）：原BUY300@93.46仍UNKNOWN，无柜台号/已证成交/预留终态；影响日间APP检查点及正式结算。；状态 open。 周度 needs_evidence：原300@93.46确认动作没有唯一柜台增量，空表不能推拒绝。30日仍UNKNOWN；权限过滤与旧单终态是两条证据链，原claim不释放。；负责人 original APP morning order evidence owner; next legal read-only reconciliation owner；下一步 原owner精确只读对账；11月2日经日历确认的晨间验证已部署隔离，以新鲜资金/敞口上界判断其他代码，绝不重报原单。；下次 2026-11-06。
- `app-b-forward-funded-v1/app_b_control`（2026-10-26–2026-10-29，3 次）：app_b_control: filled entry 1, open lots 1, model NAV 97414.52; no completed exits, missing 10-28, insufficient comparable evidence.；状态 insufficient_evidence。 周度 continue：29日原交接零平仓是当日事实；当前冻结app_b_control NAV98088.45、成交订单2、open lots0，成交订单数不是独立样本数。前三账户各一买卖往返、M零成交；缺10-28，不能由0%或单次亏盈排序晋级。；负责人 xiaocao-weekly-deep-review / existing funded research owner；下一步 沿app-b-forward-funded-v1原未来窗口保存全部计划/未成交/缺失/现金/费用，按共同冻结与相同风险做多日OOS；不把APP权限/时钟差异或Book T当KOL效应。；下次 2026-11-06。
- `app-b-forward-funded-v1/mode_m`（2026-10-26–2026-10-29，3 次）：mode_m: filled entry 0, open lots 0, model NAV 100000.0; no completed exits, missing 10-28, insufficient comparable evidence.；状态 insufficient_evidence。 周度 continue：29日原交接零平仓是当日事实；当前冻结mode_m NAV100000.00、成交订单0、open lots0，成交订单数不是独立样本数。前三账户各一买卖往返、M零成交；缺10-28，不能由0%或单次亏盈排序晋级。；负责人 xiaocao-weekly-deep-review / existing funded research owner；下一步 沿app-b-forward-funded-v1原未来窗口保存全部计划/未成交/缺失/现金/费用，按共同冻结与相同风险做多日OOS；不把APP权限/时钟差异或Book T当KOL效应。；下次 2026-11-06。
- `app-b-forward-funded-v1/no_kol`（2026-10-26–2026-10-29，3 次）：no_kol: filled entry 1, open lots 1, model NAV 97414.52; no completed exits, missing 10-28, insufficient comparable evidence.；状态 insufficient_evidence。 周度 continue：29日原交接零平仓是当日事实；当前冻结no_kol NAV98088.45、成交订单2、open lots0，成交订单数不是独立样本数。前三账户各一买卖往返、M零成交；缺10-28，不能由0%或单次亏盈排序晋级。；负责人 xiaocao-weekly-deep-review / existing funded research owner；下一步 沿app-b-forward-funded-v1原未来窗口保存全部计划/未成交/缺失/现金/费用，按共同冻结与相同风险做多日OOS；不把APP权限/时钟差异或Book T当KOL效应。；下次 2026-11-06。
- `app-b-forward-funded-v1/open_limit`（2026-10-26–2026-10-29，3 次）：open_limit: filled entry 1, open lots 1, model NAV 97506.53; no completed exits, missing 10-28, insufficient comparable evidence.；状态 insufficient_evidence。 周度 continue：29日原交接零平仓是当日事实；当前冻结open_limit NAV98180.46、成交订单2、open lots0，成交订单数不是独立样本数。前三账户各一买卖往返、M零成交；缺10-28，不能由0%或单次亏盈排序晋级。；负责人 xiaocao-weekly-deep-review / existing funded research owner；下一步 沿app-b-forward-funded-v1原未来窗口保存全部计划/未成交/缺失/现金/费用，按共同冻结与相同风险做多日OOS；不把APP权限/时钟差异或Book T当KOL效应。；下次 2026-11-06。
- `app-b-lifecycle-three-distinct-receipts`（2026-10-26–2026-10-29，3 次）：APP原计划/执行/会计分开；EOD有完整快照但当前BUY/预留/34单费用阻塞，模型不替代柜台事实。；状态 observed。 周度 continue：原计划、APP执行和会计仍分开，三类blocker没有被模型NAV替代；但30日晨间在final-plan前被全局门拦截，设计分层存在而运行可达性未验收。；负责人 xiaocao-daily-eod verifies; xiaocao-weekly-deep-review synthesizes；下一步 原晨间owner核对incident consumption、实际final plan/claim/成交，EOD独立严格结算；用同一原件贯通而不回填。；下次 2026-11-06。
- `app-b-star-market-permission-filter`（2026-10-29–2026-10-29，1 次）：primary无科创权限的BUY前置过滤缺失已修复并部署；原UNKNOWN不变，权限补位自然待验。；状态 repaired。 周度 verify：primary权限过滤代码已修；30日旧BUY前置全局门阻断，尚未自然走到权限后补位，不能以另一修复替它验收或解除原UNKNOWN。；负责人 original morning repair owner / next natural owner；下一步 下一原晨间读取app_buy_permissions和原冻结排名，验证688/689排除与合格顺位补位；普通COLD、席位和账户风险门保留。；下次 2026-11-06。
- `automation-turn-without-first-business-command`（2026-10-29–2026-10-29，1 次）：10-28原EOD仅调度userMessage、22:34 interrupted，无工具/命令、slot或handoff；原因unknown，不补跑。；状态 open。 周度 needs_evidence：10月28日原turn无业务工具/slot，仅输入及interrupted；watch不列该日不能证明假日或零收益。平台内部原因unknown，未调查用户自有网络。；负责人 Codex runtime evidence owner; Weekly evidence review；下一步 保留缺失日期与非随机漏观察；下一原EOD核验真实首命令/slot/terminal，不补跑旧日；平台根因仅凭实际平台记录取证。；下次 2026-11-06。
- `book-t-v2-contiguous-day-gap`（2026-10-29–2026-10-29，1 次）：自然证据累计7天但缺10-28，contiguous false；daily stability与20日burn-in均pending，rehearsal27排除。；状态 observed。 周度 continue：29日累计7自然日但缺28日、非连续；30日日复盘另报累计8仍缺28，rehearsal排除。累计日数不能认证连续5日或20日burn-in，且T不进入短线KOL对照。；负责人 original Book T evidence owner / Weekly；下一步 T原owner沿自然日历/原始input/control/shadow/mark核验连续性；不回填缺日、不降低原门。；下次 2026-11-06。
- `eod-final-digest-before-app-terminal`（2026-10-26–2026-10-29，3 次）：10-27独立收尾证明全部原终态/交接晚于业务、APP-first摘要已投递；本日回读hash通过。；状态 verified。 周度 continue：27日独立验收确证APP-first且晚于全部原终态；这只验收该时序修复。30日feedback失败使唯一closeout拒绝，canonical daily/最终摘要不存在，不能用旧verified关闭较新义务。；负责人 xiaocao-daily-eod；下一步 下一原EOD核对e0dbb50b已部署reader及全部终态→review→closeout→delivery；30日原失败不重放，回读本Weekly状态。；下次 2026-11-06。
- `eod-learning-backlog-needs-weekly-prioritization`（2026-10-26–2026-10-29，3 次）：309候选/10已测/299未测、posture118天陈旧，大环未闭合；新标签不等于策略改善。；状态 observed。 周度 deepen：冻结29日309/10、30日复盘321/10与旧posture说明积压，非策略改善。优先级不是再造宏观面板：先沿baseline_no_kol槽取得完整机会分母与共同资金费用/时钟配对，排除工程漏执行后才评价KOL。；负责人 xiaocao-weekly-deep-review；下一步 既有三个槽不扩容；第一优先control/no-KOL原未来窗口与独立roundtrip，接着时效/定价和M参与度。资料缺口及反证写明，研究晋级仍research_run/§10。；下次 2026-11-06。
- `eod-research-no-action-terminal`（2026-10-27–2026-10-29，2 次）：f22dfb63已接受exit0 not_started(saved reports)/NON_TRADING_DAY；今日research observed，合法无动作自然路径尚未触发。；状态 repaired。 周度 verify：代码f22dfb63接受合法not_started(saved reports)/NON_TRADING_DAY；本周原research是observed，未触发无动作自然场景，测试通过不足以关闭。；负责人 xiaocao-daily-eod / xiaocao-weekly-deep-review；下一步 首次自然合法no-action时原EOD核验真实owner/argv/exit/stdout/hash及closeout；不造场景、不重跑。；下次 2026-11-06。
- `kol-source-decision-consumer-links-unknown`（2026-10-27–2026-10-29，2 次）：feedback仅receipt/hash审计：live334/hash267/unbound281/missing clock67；paper29/hash29/unbound29/missing clock29，执行/利润归因未证。；状态 observed。 周度 needs_evidence：29日哈希审计仍有unbound和缺clock，反馈没有执行/利润验证；30日原feedback失败更不能复用昨天计数冒充今天。来源发布、正式政策与实际采用分别取证。；负责人 existing remote KOL writer / next sparse claim owner；下一步 原remote/sparse owner在真实适用机会按exact receipt/hash补链；EOD不重抽语义/发布，周度按作者事件去重并保留缺时点。；下次 2026-11-06。
- `morning-dependency-and-support-observability`（2026-10-29–2026-10-29，1 次）：c98840a3已交付缓存重试/批量取价、KOL交接绑定、通知聚合、独立Paper和原生读取修复；各适用自然场景待证。；状态 repaired。 周度 verify：c98840a3源/支持链修复已有专项证据；30日原producer与Paper部分自然通过，但APP被另一旧BUY门先挡，不能把它当所有恢复分支通过。等待预算和语义时效分别统计。；负责人 original morning repair owner / next natural owner；下一步 原晨间按真实触发分支验收缓存/报价/准备/最终dispatch/claim/通知时钟；保持09:27支持截止与原owner预算，不回放终态。；下次 2026-11-06。
- `paper-b-first-minute-high-source-acceptance`（2026-10-29–2026-10-29，1 次）：原HIGH验证器只有拒绝出口且来源故障误报正常no_buy；接受路径与source_blocked终态已修复部署，未来自然采集/记账待证。；状态 repaired。 周度 verify：29日代码接受路径待验；30日001287原HIGH20.24与1700股入账匹配，提供自然正样本；688045跨边界60.54→61.00仍source_blocked，不能泛化全采集成功。；负责人 original morning repair owner / next natural owner；下一步 下一EOD在新daily引用30日原HIGH证明，分别登记已买与缺证；保留首分钟保守成本，检验全部机会分母和采集选择偏差。；下次 2026-11-06。
- `weekly-orders-sidecar-as-terminal`（2026-10-26–2026-10-29，3 次）：实际 10-26 .orders.json 被当终态导致只读 Weekly inventory 报错；现已按进度文件处理，缺终态仍告警。；状态 repaired。 周度 verify：本次唯一原weekly计划成功，8个正式checkpoint和orders/wait明确区分，26日orders sidecar自然不再误当终态。异常孤立sidecar未触发，不制造。；负责人 xiaocao-weekly-deep-review；下一步 下一EOD将本次原run/terminal作为该修复自然证据写新handoff；原weekly失败和孤立缺终态仍保留。；下次 2026-11-06。
- `weekly-unresolved-daily-source-missing`（2026-10-27–2026-10-29，2 次）：f22dfb63已修复丢失每日原件时Weekly未决义务丢失、旧verified掩盖较新缺证；今日context无缺件，缺件自然场景未触发。；状态 repaired。 周度 verify：冻结3份daily输入errors=[]，18项义务均存续；没有自然丢失原件场景，不能宣称该反例生产已验证。28/30日无canonical交接另作真实证据缺口，旧verified不替代。；负责人 xiaocao-daily-eod / xiaocao-weekly-deep-review；下一步 保留状态与本次18项回复；下一EOD实际回读ledger，首次自然source-missing按原manifest保留id/owner/action且不得close，不人为删除原件。；下次 2026-11-06。
- 执行事故复核：旧BUY全局阻断跨日复发，8e3c998d下午已部署隔离但自然开盘未验；原生空响应完成见证仍缺。EOD feedback兼容修复e0dbb50b已部署，30日原失败/无canonical交接保留；三笔原UNKNOWN不回放。
- 当前修复负责人：原APP修复task 01a18a49-34b8-7781-a5fc-37902cae4a0f；原EOD 01a18ba0-218f-7dc1-95c1-0c582a509133；Weekly只读复核及研究跟进；验收边界：11月2日须先原日历证明；原晨间09:20前部署/事故消费/当前经济边界，09:24会话复验；原EOD验reader/post终态/交接与本Weekly回读。无试单或历史重放。
- 完整订单、任务轨迹、5 Why 与修复证据：[执行复核](/Users/xuanyue202/Documents/project/xiaocao/docs/reviews/2026-10-30-weekly-execution-review.md)。
- 整体框架复盘（有证据引用的分析，非收益认证）：保留§2a有界KOL的来源语义、当前适用性、独立审核及合法消费边界，经济增量保持未证实，并把资本参与和漏执行列为同级竞争解释。10月24—30日4个发布判断中1个buy_scale=0、3个为中性；12周49包中10个为零新增风险、39个为中性，均未给出个股skip、exit或模式覆盖。10月23日13:42的零新增风险晚于当晨买入，所见持仓T+1不可卖；10月26日零新增风险及10月27日中性判断缺当时完整新买候选/行情分母。10月29日APP原计划引用过期旧包且订单终态未证，10月30日APP晨间blocked与纸盘来源阻断不能计为KOL保护。独立10万元资金模型截至10月30日的五个已消费晨间日，app_b_control与no_kol同为2个模型成交事件、2个未成交计划、费率模型净值98088.45元（-1.91155%），因此当前样本未产生可观察KOL选择差异；mode_m仍为10万元现金、零成交，不能把避开单一模型亏损当作可推广优势。open_limit模型净值98180.46元是定价诊断，非KOL增益。10月28日晨间/EOD缺测、APP与模型分配和时钟不同、APP费用与现金归属未闭合，正式APP利润和多日完整回撤仍未知。上游门可能过筛：冻结选择记录在10月23日3行中2行COLD、10月29日19行中18行COLD、10月30日17行中15行COLD；但这些只是authority=0选择记录，尚无点时可成交、同本金费后错失上涨与多日OOS。作者观点存在重复引用及市场条件冲突；本周11条来源引用只对应5份独立报告，不能把相关叙事、发布包数量或重叠1/4/12周窗口当成独立收益样本。下一步沿原三个9月11日稳定槽做同资金完整路径、合法可成交时钟和入口外挑战，不改生产门、资金或永久参数。
- 结论证据：`output/live/flywheel_change_ledger.jsonl`（sha256=efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64）；`output/live/kol_policy/context/bdb55081db9bdd7f7bd1ec4ea78dd54a2012f4bbe339cc31baa755f620b73b12.context.json`（sha256=66583c8b9b28f17c58cee859eceff2182eeea4dc5ebb58038c9ad2041e1f2287）；`output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1025-neutral-521305ed-v1.json`（sha256=e23a1f68c69129ac4e9c2e2aba39be5ba496208863776fcde341c3f205ccefb7）；`output/live/kol_policy/decisions/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json`（sha256=c5fb076b6d662c7d78cb013b2bc7a7b457e18bce6f47e83478d3c8875a3941da）；`output/live/kol_policy/decisions/kol-b-both-sparse-20261026-1025-no-new-risk-fc7bb1f8-v1.json`（sha256=3dfc3997b60b38cc641163beca9177dcaf5a6e71c867a567ea0ab55b8c335f49）；`output/live/kol_policy/decisions/kol-b-both-sparse-20261027-1355-neutral-8435b899-v1.json`（sha256=8569e7a3201c73a81c10ccc620ec7f5505dd75d625d8f35f3a90e2f94c7c737a）；`output/live/kol_policy/source_verifications/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json`（sha256=0856baf33eaf860ecc16161d04b4a86e3c037bb0a687ffd3401f7dc88fab8230）；`output/live/book_b_live_execution/runs/2026-10-23.json`（sha256=b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd）；`output/live/book_b_live_execution/runs/2026-10-29.json`（sha256=63b7d43ee5b93366c13b5c2ae1c7a023bc1868a12d04c916423956f53bd22c09）；`output/live/book_b_live_execution/runs/2026-10-30.json`（sha256=07ded948eb846d10a007799dd82d0cd2c42b1ab5d1f445aeb51872354f9043b2）；`output/live/paper_decision_support/consumption/6d66b892a839fc792753238c1d76a5f2c95611b454ded8b20b1e07f438713139.result.json`（sha256=b634afa75f12621defd0e62c9c34367cd4c1c21e2c4b2a125a2b5d87a5addf16）；`output/live/paper_decision_support/consumption/7b8180ffc50eaa1c29b2d0295727203857a5efab9555731bdffcae702e2866f9.result.json`（sha256=ac7eb939fbea6bb8dfa529afd845c7c5b05d7b30d1007197d54c64ed954bf5d8）；`output/live/book_b_live_execution/book_b_live_decisions.jsonl`（sha256=33ce56e698bfc442eae95d441b809f64fc9bbe7a3791141a7a0f3215a7c67715）；`output/live/kol_policy/account_risk/live_B.jsonl`（sha256=d4b4150b80fc9251d21bb7d474a93d1d645de8cdd712624a4404b05b5a03d29e）
- 待核证据：多独立交易日、同冻结候选/资金/费用/风险预算的no-KOL、current、challenger点时可成交OOS及左尾和现金时间积分；五个已观测晨间日中10月28日缺测；逐次来源发布/收到、评价、独立审核、正式发布、有效期、首个合法消费、原计划、柜台成交与实际费用的完整链接；旧消费时钟与未完成请求遥测缺失；所有被COLD/UNKNOWN/权限/报价/冻结排除候选的当时可见行情、可成交量、后续可合法退出收益和错失上涨；不得用事后高点替代；APP原订单终态、资金归属与逐笔实际费用的会计证明；10月30日canonical EOD handoff未进入冻结回执，不能据其缺席推断无事故；远端完整报告发现能力仍不完备；历史未载入正文按精确ID核验，不把registered coverage等同全网完整覆盖或独立作者确认
- 比较框架：无 KOL 基线 / 现行有界 KOL / 挑战者；分别检查入口过滤、模式和资金利用率。
- 纸实逐账户分开；1/4/12 周重叠窗口不是独立样本。小样本不宣称因果胜率或稳定收益，不自动推广实盘。
- 旧试验跟进：3 项需先复核（历史状态仅为报告声明），再决定本周最多三个槽位；不自动启动。

## 数据证据与方案比较

- 输入清单 sha256=`c687ca896e747dc2734f1e9b03be7b03f4ee401aa2f007982f6584510e5d6c7e`；捕获 214 个文件；缺失模式 2 项。
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
- `T_trend_L60_R30_M3`：历史记录 REJECTED（2026-10-30T15:15:20）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_trend_L60_R40_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_trend_L60_R60_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_trend_L20_R20_M3`：历史记录 REJECTED（2026-07-03T15:42:46）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `T_rotation_L60_R30_M3_W20_K5`：历史记录 REJECTED（2026-10-30T15:15:20）；本次复核 证据不足；n_days=N/A，train/test=N/A/N/A。
- `aux_gray_n_fixed`：历史记录 REJECTED（2026-07-10T20:17:02）；本次复核 证据不足；n_days=9，train/test=-0.226526/-2.259637。
- `aux_gray_relay1_fixed`：历史记录 REJECTED（2026-07-10T20:17:09）；本次复核 证据不足；n_days=25，train/test=0.723968/-1.135733。
- `E_ai_intelligence_short_factor`：历史记录 REJECTED（2026-10-30T15:15:10）；本次复核 证据不足；n_days=31，train/test=0.981345/-1.319659。
- 研究 `output/research/runs/aux-gray-n-fixed-2026-07-10/manifest.json`：记录 REJECTED，本次 证据不足；缺口：paired_cost_fill_chronology_comparison_missing。
- 研究 `output/research/runs/aux-gray-relay1-fixed-2026-07-10/manifest.json`：记录 REJECTED，本次 证据不足；缺口：paired_cost_fill_chronology_comparison_missing。
- 研究 `output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/manifest.json`：记录 REJECTED，本次 证据不足；缺口：paired_cost_fill_chronology_comparison_missing。

### 纸面成交证据与资金口径

- 12w：独立入场 70，记录窗口标签 70（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- 1w：独立入场 3，记录窗口标签 3（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- 4w：独立入场 22，记录窗口标签 22（原窗口待证），fallback 0（0.0%），全部代理 0，未知 0；本表标签均不进入可执行确认，对照实验原件另行验证。
- APP 已保存会计观测 30 份；资金划拨不计利润，缺完整净值/现金流/实际费用时不计算账户收益。
- 会计观测 2026-10-27T01:28:36.139000+00:00：净投入 65845.40，标记净值 65159.65，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-29T07:15:53.603000+00:00：净投入 65845.40，标记净值 65159.65，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
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
- 会计观测 2026-10-26T01:26:43.205000+00:00：净投入 65845.40，标记净值 65008.93，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-27T07:16:05.869000+00:00：净投入 65845.40，标记净值 65159.65，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-09-30T07:22:21.651000+00:00：净投入 54462.04，标记净值 53372.04，累计盈亏 N/A，已实现/浮动 -846.21/-236.39；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-13T07:16:32.855000+00:00：净投入 54462.04，标记净值 59745.10，累计盈亏 N/A，已实现/浮动 5283.06/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-08T07:21:52.104000+00:00：净投入 54462.04，标记净值 53291.26，累计盈亏 N/A，已实现/浮动 -1156.95/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-16T08:03:28.059000+00:00：净投入 65845.40，标记净值 68616.17，累计盈亏 2770.77，已实现/浮动 1895.56/875.21；费用 estimated_plan_rate，状态 reconciled（已保存观测，未认证收益）。
- 会计观测 2026-10-26T07:15:58.479000+00:00：净投入 65845.40，标记净值 65159.65，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-16T01:31:46.380000+00:00：净投入 54462.04，标记净值 55768.81，累计盈亏 N/A，已实现/浮动 1895.56/-588.79；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-09-30T06:51:01.818000+00:00：净投入 54462.04，标记净值 53398.04，累计盈亏 N/A，已实现/浮动 -846.21/-210.39；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-16T07:15:54.737000+00:00：净投入 54462.04，标记净值 57232.81，累计盈亏 N/A，已实现/浮动 1895.56/875.21；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-19T07:16:16.247000+00:00：净投入 65845.40，标记净值 68217.82，累计盈亏 N/A，已实现/浮动 2393.94/0.00；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-30T07:17:21.233000+00:00：净投入 65845.40，标记净值 65159.65，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-09T01:45:43.626000+00:00：净投入 54462.04，标记净值 53345.26，累计盈亏 N/A，已实现/浮动 -1156.95/61.10；费用 estimated_plan_rate，状态 cash_reconciliation_required（已保存观测，未认证收益）。
- 会计观测 2026-10-21T07:16:31.258000+00:00：净投入 65845.40，标记净值 67392.23，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。
- 会计观测 2026-10-26T01:28:47.784000+00:00：净投入 65845.40，标记净值 65008.93，累计盈亏 N/A，已实现/浮动 None/None；费用 unknown，状态 unknown（已保存观测，未认证收益）。

生产纸盘观察截至 2026-10-30；最新原记录日期 2026-10-30，相距 0 个自然日。
有效仓 226、未知仓 17、坏记录 0、未成熟仓 5；旧日期/naive 时钟缺时区与可用时点证明。
Book A：有效/闭仓 99/98；有效子集模型买费 223.33，卖费 223.24，闭仓现金净变动 32857.48。
Book B：有效/闭仓 114/113；有效子集模型买费 261.62，卖费 262.54，闭仓现金净变动 42168.43。
Book T：有效/闭仓 13/10；有效子集模型买费 11.26，卖费 8.25，闭仓现金净变动 -2102.73。
同进场 A/B 闭仓配对 59，B−A均值 0.6309 pp；有效分组排除 56（开放 1、未匹配 17、进场不一致 38）；另有未知仓 17。
12w 进场窗口 2026-08-08–2026-10-30：有效 70；最新数据在窗口前=False。
1w 进场窗口 2026-10-24–2026-10-30：有效 3；最新数据在窗口前=False。
4w 进场窗口 2026-10-03–2026-10-30：有效 22；最新数据在窗口前=False。
以上仅为原始现金事实的描述性观察，非组合NAV、APP成交或KOL增益；闭仓选择偏差与未成熟删失仍在。

### 短线统一流程的前向证据

- 已保存原冻结选择记录 5 日；选择记录不代表独立资金组合已运行。
- 截至 2026-10-21：严格同进场退出 57 对，B−A 均值 +0.6287pp；仅描述该样本，不自动晋级。证据 `output/research/shortline_comparisons/2026-10-21-fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2.json`。
- 截至 2026-10-23：严格同进场退出 58 对，B−A 均值 +0.6707pp；仅描述该样本，不自动晋级。证据 `output/research/shortline_comparisons/2026-10-23-c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41.json`。
- 截至 2026-10-30：严格同进场退出 59 对，B−A 均值 +0.6309pp；仅描述该样本，不自动晋级。证据 `output/research/shortline_comparisons/2026-10-30-5e3f9a5f7ad6015b2508b6563221afd438a16a809239cb2766a0c7c3ca7194a4.json`。

### APP B 独立资金对照（模型成交）

| 账户 | 费用后模型收益 | 未决模型订单 | 估值时间 |
|---|---:|---:|---|
| app_b_control | -1.912% | 0 | 2026-10-30T15:17:45.481714+08:00 |
| mode_m | +0.000% | 0 | 2026-10-30T15:17:45.481714+08:00 |
| no_kol | -1.912% | 0 | 2026-10-30T15:17:45.481714+08:00 |
| open_limit | -1.820% | 0 | 2026-10-30T15:17:45.481714+08:00 |
- 2026-10-23 APP 与资金对照：资金分配。
- 2026-10-26 APP 与资金对照：资金分配。
- 2026-10-27 APP 与资金对照：资金分配。
- 2026-10-29 APP 与资金对照：资金分配。
- 2026-10-30 APP 与资金对照：APP 最终计划缺证。
缺少原 morning 观察日：2026-10-28
缺少 EOD 估值日：2026-10-28
模型成交和盘后时序单独标注；缺证与完整日期分母保留，晋级仍需研究门和人工决策。

## 需要你看/确认的事项

- **继续取证** `weekly-2026-10-30-existing-three-slot-evidence`：沿既有三个实验补齐机会分母、费用与有效采用证据
- **本地工作区提醒，不是策略判断**：有 49 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl, reference/experience/transcripts/2026-09/2026-09-13_lv_xiaotong_review_course136_f9b629a9.txt, reference/experience/transcripts/2026-10/2026-10-05_lv_xiaotong_review_514e6857.txt, reference/experience/transcripts/2026-10/2026-10-07_liushao_jujiying_article.md, reference/experience/transcripts/2026-10/2026-10-08_lv_xiaotong_review.txt；另有 44 个。

## 这批转录给我的启发
- **2026-10-29 review（2026-10-29_lv_xiaotong_review_f45aef67_corrected.json）**
  启发：本场可复用的核心是把主营经营、非主营投资损益、资本扩张纪律和集团穿透式敞口分开：主营未恶化不等于资本配置没有风险，必要的科技投入也不等于投资回报已经得到证明，名人持仓与上市证券排名更不能替代对现金回报和整体经营结构的核验。四条边界独立的内容保留为吕晓彤来源归属下的authority=0研究候选；科技资本开支内容只构成对XH-298的部分支持，不复现该完整claim，也不新增近义候选。
  姿态：not_applied：吕晓彤是其他作者，本条不修改小草全局姿态或时间线。
  打法：no_deterministic_change：保留主营与非主营拆分、企业资本配置、领域权威和集团穿透式敞口四条authority=0候选；科技资本开支仅作为方法和对XH-298的部分支持，不形成新候选或完整recurrence。
  待验证：four_distinct_candidates_retained_xh298_partial_support_only：保留已归档的XH-315至XH-318；移除XH-298完整复现，不向其合并本来源，也不新增近义资本开支候选。
  命中审计：bound_to_complete_transcript_sha256_f45aef6795a15a9a09cdb5dadc602b96754dd37206d18cffa74264e72e97078f
  工具缺口：建立利润来源桥接、非核心投资比例、回购法律阶段、名人能力圈和集团分部风险贡献面板；资本开支只记录本来源已支持的回收问题与竞争必要性，不扩写为资金成本或融资能力结论。
- **2026-10-29 盘中大师班直播（2026-10-29_xiaocao_morning_b8833076.json）**
  启发：小草在10月29日下跌环境中主张保守，并把连板倒接力与人气股低吸组合执行；红盘起爆只看竞价涨幅较低的候选，明确回避约6%高开、优先5%以下。直播同时给出百洋股份、冰山冷热、龙溪股份及多组语音转写候选的盘中口述结果，但没有独立成交与收益证据。可复用内容是组合、追高过滤和把交易动作简化到事前模式；所有内容仅作authority=0研究素材。
  姿态：candidate_only：10月29日主跌与保守判断已过期，10月30日不能直接沿用。
  打法：proposal_only：组合、红盘起爆高开过滤和规则简化只补充既有候选，不自动修改策略。
  待验证：no_new_hypothesis：现有XH-276、XH-286、XH-218和XH-027足以承接，本场证据只做反馈。
  命中审计：完整绑定52个稳定段和证券目录；所有歧义证券、口述涨幅、成交与模式归因均保留未核实。
  工具缺口：未来研究需保存竞价排名、模式版本、总风险与权重、信号时点、可成交价格、费用、退出和市场广度。
- **2026-10-29 review（2026-10-29_xiaocao_review_859674e1.json）**
  启发：小草把弱市短线判断拆成环境切换、模式选择、入场边界和退出验证：指数与科技走弱时，资金可能暂时集中到最高位和人气股，但只有模式仍有效、开盘不过高且个股出现可验证的强弱转换时才参与；没有合适模式就空仓。该框架有可复核条件，适合保留为候选知识，不能由单场直播自动升级为策略规则。
  姿态：candidate_only_no_automatic_posture_change
  打法：no_change_without_research_and_human_gate
  待验证：one_new_authority_zero_candidate_one_existing_recurrence_two_partial_support_audits
  命中审计：source_bound_with_market_and_strategy_boundary
  工具缺口：test_highest_position_regime_and_existing_XH_220_limit_timing_with_fixed_exit_rules
- **2026-10-30 morning（2026-10-30_xiaocao_morning_2ddb29b3.json）**
  启发：小草在极弱盘面中把短线决策拆成环境、模式、组合、入场高度、持仓保护和收盘确认：高辨识度高位可能保持相对强势，但只有模式和价格条件合格时才观察；盈利保护的原声“两支票／两个点”存在冲突，不能参数化；预警只形成待确认假设。整套内容仅作为 authority=0 候选知识。
  姿态：candidate_only_no_automatic_posture_change
  打法：partial_support_for_intraday_evidence_and_fresh_mode_qualification_no_full_rewrite
  待验证：no_new_hypothesis_xh078_and_xh276_partial_support_plus_three_prior_audits
  命中审计：source_bound_with_midday_market_household_and_feedback_boundaries
  工具缺口：reuse_xh078_same_mode_top_two_equal_weight_test_no_new_candidate

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-10-29 2026-10-29_lv_xiaotong_review_f45aef67_corrected.json: not_applied：吕晓彤是其他作者，本条不修改小草全局姿态或时间线。
  - 2026-10-29 2026-10-29_xiaocao_morning_b8833076.json: candidate_only：10月29日主跌与保守判断已过期，10月30日不能直接沿用。
  - 2026-10-29 2026-10-29_xiaocao_review_859674e1.json: candidate_only_no_automatic_posture_change
  - 2026-10-30 2026-10-30_xiaocao_morning_2ddb29b3.json: candidate_only_no_automatic_posture_change
- **Playbook/纪律**
  - 2026-10-29 2026-10-29_lv_xiaotong_review_f45aef67_corrected.json: no_deterministic_change：保留主营与非主营拆分、企业资本配置、领域权威和集团穿透式敞口四条authority=0候选；科技资本开支仅作为方法和对XH-298的部分支持，不形成新候选或完整recurrence。
  - 2026-10-29 2026-10-29_xiaocao_morning_b8833076.json: proposal_only：组合、红盘起爆高开过滤和规则简化只补充既有候选，不自动修改策略。
  - 2026-10-29 2026-10-29_xiaocao_review_859674e1.json: no_change_without_research_and_human_gate
  - 2026-10-30 2026-10-30_xiaocao_morning_2ddb29b3.json: partial_support_for_intraday_evidence_and_fresh_mode_qualification_no_full_rewrite
- **候选假设**
  - 2026-10-29 2026-10-29_lv_xiaotong_review_f45aef67_corrected.json: four_distinct_candidates_retained_xh298_partial_support_only：保留已归档的XH-315至XH-318；移除XH-298完整复现，不向其合并本来源，也不新增近义资本开支候选。
  - 2026-10-29 2026-10-29_xiaocao_morning_b8833076.json: no_new_hypothesis：现有XH-276、XH-286、XH-218和XH-027足以承接，本场证据只做反馈。
  - 2026-10-29 2026-10-29_xiaocao_review_859674e1.json: one_new_authority_zero_candidate_one_existing_recurrence_two_partial_support_audits
  - 2026-10-30 2026-10-30_xiaocao_morning_2ddb29b3.json: no_new_hypothesis_xh078_and_xh276_partial_support_plus_three_prior_audits
- **命中审计**
  - 2026-10-29 2026-10-29_lv_xiaotong_review_f45aef67_corrected.json: bound_to_complete_transcript_sha256_f45aef6795a15a9a09cdb5dadc602b96754dd37206d18cffa74264e72e97078f
  - 2026-10-29 2026-10-29_xiaocao_morning_b8833076.json: 完整绑定52个稳定段和证券目录；所有歧义证券、口述涨幅、成交与模式归因均保留未核实。
  - 2026-10-29 2026-10-29_xiaocao_review_859674e1.json: source_bound_with_market_and_strategy_boundary
  - 2026-10-30 2026-10-30_xiaocao_morning_2ddb29b3.json: source_bound_with_midday_market_household_and_feedback_boundaries
- **工具/流程提案**
  - 2026-10-29 2026-10-29_lv_xiaotong_review_f45aef67_corrected.json: 建立利润来源桥接、非核心投资比例、回购法律阶段、名人能力圈和集团分部风险贡献面板；资本开支只记录本来源已支持的回收问题与竞争必要性，不扩写为资金成本或融资能力结论。
  - 2026-10-29 2026-10-29_xiaocao_morning_b8833076.json: 未来研究需保存竞价排名、模式版本、总风险与权重、信号时点、可成交价格、费用、退出和市场广度。
  - 2026-10-29 2026-10-29_xiaocao_review_859674e1.json: test_highest_position_regime_and_existing_XH_220_limit_timing_with_fixed_exit_rules
  - 2026-10-30 2026-10-30_xiaocao_morning_2ddb29b3.json: reuse_xh078_same_mode_top_two_equal_weight_test_no_new_candidate

## 上期试验与失败跟进（先于新增试验，未记录不等于完成）

- `weekly-2026-09-11-baseline_no_kol`：沿原稳定编号继续检验 APP E+COLD 控制与 no-KOL 的同资金费后差异；把 paper:B 另列，只在完整点时 freeze、整手、真实合法时钟与共同 B 出口上计算收益、现金时间积分、回撤及可成交错失上涨。
  - 历史状态：funded_first_day_observed_no_fill；本周复核状态：pending_review；原复核日：2026-10-30。
  - 跟进结论（报告声明）：前次仅登记设计，未发现该历史实验已运行的证据。已预登记资金挑战于10月23日首个自然日出现一单计划/未成交，与控制同为10万元现金；没有可比较利润或回撤分布。保留原编号，下周跟踪同资金多日费用/成交。
  - 回滚：本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-10-23；state sha256=be1479168b8830fe61f23cd363cc6fa1223dd5a3d03e79c640cc043119287350。
- `weekly-2026-09-11-current_bounded`：沿原编号分解有界判断的来源、评价、独立复核、发布、失效、第一合法消费与 APP/纸盘原计划/成交；对 no-KOL 资金控制检验左尾与错失，借 open-limit 隔离同计划定价/未成交漏损。
  - 历史状态：funded_first_day_observed_no_fill_lineage_incomplete；本周复核状态：pending_review；原复核日：2026-10-30。
  - 跟进结论（报告声明）：前次 42 份纸盘原消费文件的只读兼容修复不等于实验运行，旧时钟仍缺。10月23日两份正式判断在 APP 买入后发布，第二份零新增风险没有已证合法新增买入分母；四资金账户首日均 no_fill。保持时效/真实消费/定价漏损拆解，不改生产 TTL 或执行门。
  - 回滚：本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-10-23；state sha256=be1479168b8830fe61f23cd363cc6fa1223dd5a3d03e79c640cc043119287350。
- `weekly-2026-09-11-kol_challenger`：沿原编号先检验 mode_star 与原 E/COLD 门在冻结内的同资金可成交参与机会；并设计隔离的竞价、09:31、有限盘中完整入口外队列，测过筛及弱市误读，生产默认维持 E+COLD。
  - 历史状态：funded_first_day_observed_no_fill_broader_entry_unrun；本周复核状态：pending_review；原复核日：2026-10-30。
  - 跟进结论（报告声明）：前次入口外研究仍只有设计，旧 C 模式研究为 REJECTED。10月23日冻结三候选中两条 COLD，模式参与挑战与控制同为一单计划/未成交，无法计算可追回上涨；弱市评分缺原表且 09:37 观察已过期。下周优先补完整点时队列和反证。
  - 回滚：本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-10-23；state sha256=be1479168b8830fe61f23cd363cc6fa1223dd5a3d03e79c640cc043119287350。

## 整体框架试验槽位（待取证与设计，不是合格变更候选）

- 目标：续用9月11日稳定编号，在同一冻结、10万元、整手、费用、B分阶段退出和风险预算下比较app_b_control与no_kol完整资金路径；分别报告实际APP与模型差异、现金时间积分、开仓与左尾。
  - 证伪条件：多独立交易日的点时可成交、费后OOS若显示现行KOL相对no-KOL在同风险暴露下有稳健收益或左尾改善且非单日/单票/来源驱动，则推翻无KOL足以解释表现；若仍无政策作用或合法成交，不判因果。
  - 必要证据：冻结原件/正式政策/首个合法消费及相同资金费用模型；五个已观测日以外的多日OOS完整本金、现金、开仓、未知、未成交、B退出与左尾；保留10月28日缺测，未来原自然日补足完整观察；按作者事件和市场阶段聚类，报告资金时间积分、可成交错失上涨与费用敏感性；APP实际订单/成交/费用独立验真，不把模型收益当APP收益
  - 回滚：本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。
  - 本次跟进（报告声明）：10月30日冻结研究报告覆盖五个晨间消费日；control与no_kol两组完整模型账户均为98088.45元、-1.91155%、2个模型成交事件和2个未成交计划，差异为零。此零差异仅表示本样本KOL未改变模型经济路径，不证明无KOL长期优劣；10月28日缺测且APP利润未知。继续积累合法、费后独立日和真实作用分母。
  - 负责人：xiaocao weekly research maintainer；隔离执行仍需既有研究门指定；下次复核：2026-11-06。
- 目标：续用9月11日稳定编号，按来源—评价—请求/独立审阅—发布—有效期—首个合法消费—原计划—订单/成交逐节点量化当前叠加；每次零新增风险须有当时确有合法新增BUY的分母及可成交错失收益。
  - 证伪条件：若有界保护多次晚于唯一合法机会、无可买卖暴露或到期，且费后可成交错失上涨/执行漏损抵消左尾收益，则拒绝现有经济增量；发布或中性包计数不能作收益。
  - 必要证据：同一报告和观点的source_fingerprint、原发布时间、本地接收、冲突/关系和正式source_verification；模型请求/开始/结束、审核、发布、有效期、首个合法消费及对应候选/账户/行情时钟；每个缩量/跳过/退出的实际政策作用、原计划/柜台成交/费用及T+1、整手、现金边界；APP与paper分账；旧消费时钟只读补证和10月30日缺失EOD原回执，不回填过去交易
  - 回滚：本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。
  - 本次跟进（报告声明）：本周4包只有10月26日一包buy_scale=0，其余中性；10月23日13:42零新增风险发生在APP当晨BUY后且当日T+1不可卖。10月29日APP晨间仅见过期旧包并有原单未决，10月30日APP blocked；纸盘30日买入来源阻断也不能归因KOL。12周49包中10个全局零新增风险、39个中性，未形成个股skip/exit/模式覆盖的收益样本。继续以合法机会分母检验时效，不改TTL和执行门。
  - 负责人：xiaocao weekly research maintainer；lineage补证由原生产/消费owner协作；下次复核：2026-11-06。
- 目标：续用9月11日稳定编号，先在原冻结内对E/COLD与mode_m做同资金可成交多日挑战，再单独预登记竞价、09:31及有限盘中入口外队列；保留UNKNOWN、科创权限、独立Book T和正式执行门。
  - 证伪条件：若mode_m或入口外挑战在多独立OOS日按同本金、整手、费用、流动性、T+1和共同B退出后不能同时改善机会覆盖与风险调整收益，或优势只来自单一亏损回避、事后赢家、相关来源和缺失标签，则拒绝。
  - 必要证据：全量原冻结与入口外点时候选、每行COLD/UNKNOWN/权限/报价/填单限制及当时可见时钟；mode_m与控制的10万元多日模型资金、费用、现金时间积分、未成交、开仓、回撤和共同B退出；入口外单独authority=0预注册、严格OOS、可成交分钟窗口和错失/新增尾部双向计量；旧C-mode REJECTED与来源冲突作为先验反证；模型结果不能推APP资本/执行权限
  - 回滚：本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。
  - 本次跟进（报告声明）：冻结选择样本确有COLD空槽：10月23日2/3、29日18/19、30日15/17行COLD。mode_m研究账户在五个已消费晨间日零成交、10万元现金，而控制出现单一已闭模型亏损；这是参与度与一条路径差异，不是可推广胜率。原选择捕获无资金/成交/退出，入口外挑战仍未运行，旧C-mode裁决为REJECTED。继续隔离研究并补双向错失与尾部。
  - 负责人：xiaocao weekly research maintainer；入口完整性研究仅走独立研究门；下次复核：2026-11-06。

## 已自动落地的代码/配置变更
- none
- 独立运行事故修复（不属策略 AUTO_APPLIED）：本Weekly仅审阅产物；既有8e3c998d隔离和e0dbb50b反馈兼容修复已部署，未重跑交易/APP测试/通知，原生空响应见证与自然采用保留未决；回滚：撤回本次研究建议/定向revert本次产物commit，保留旧计划/订单/claim/会计和不可变证据；既有工程修复回滚由原owner按其原验证处理。

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- KOL 固定复盘输入（仅观察，不增加自动落地权限）：output/live/kol_policy/context/*.context.json, output/live/kol_policy/decisions/*.json, output/live/book_b_live_execution/consumption.jsonl, output/live/book_b_live_execution/book_b_live_decisions.jsonl, output/live/book_b_live_execution/runs/*.json, output/live/kol_policy/account_risk/live_B.jsonl, output/live/paper_decision_support/consumption/*.json, output/live/paper_decision_support/consumption.jsonl, output/live/kol_policy/account_risk/risk_receipts/*.json, output/live/flywheel_change_ledger.jsonl, output/live/kol_policy/requests/*.json, output/live/kol_policy/source_verifications/*.json
- APP 执行固定复盘输入（仅观察，不增加策略自动落地权限）：output/live/daily_execution_review_*.md, output/live/book_b_live_execution/events.jsonl, output/live/book_b_live_execution/runs/intraday/archive/*.json, output/live/book_b_live_execution/settlements/*.json, output/live/book_b_live_execution/capital_policy.json, output/live/book_b_live_execution/capital_flows.jsonl, output/live/book_b_live_execution/accounting_reports/*.json
- 提案数量：1
- 自动落地候选数量：0

## 验证
- 214 frozen input snapshots and 22 execution references: PASS
- 18 EOD feedback obligations and 3 stable experiment slots: PASS
- Sol xhigh synthesis and independent parent source/economic review: PASS
- data_doctor.py: critical=0 warn=0 PASS; A/B/T status readback saved
- strategy_protocols.py --check: 4 PASS; bash syntax and diff check PASS
- Report-only artifacts; source tests not required; next natural APP/EOD acceptance remains pending

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 321 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-10-30/weekly-2026-10-30-existing-three-slot-evidence.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 175,
    "candidate_assertions": 445,
    "candidate_to_tested": 0.03,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 321,
    "candidates_untested": 311,
    "dedup_ratio": 0.72,
    "instrumentation_todos": 143,
    "median_recurrence": 1,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 659,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 175
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 51566,
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
  "kol_system_review_status": "completed",
  "kol_inventory_sha256": "b40e524def43de192eec61394c49d0fb059cfe5f1cb501193bfa872df60f1299",
  "kol_audit_feedback": {
    "consumption": {
      "live": {
        "book_counts": {
          "B": 334
        },
        "consumption_container_count": 300,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 7,
          "kol-b-both-sparse-20261023-1025-neutral-521305ed-v1": 2,
          "kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1": 7,
          "kol-b-both-sparse-20261026-1025-no-new-risk-fc7bb1f8-v1": 5,
          "kol-b-both-sparse-20261027-1355-neutral-8435b899-v1": 3,
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
        "evidence_sha256": "c2afc3a0355197c79ed36794fb48889929a303e0c566c4e4114ee6232e03d0ab",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 267,
        "legacy_file_count": 11,
        "missing_consumption_clock_count": 67,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 0,
        "paper_terminal_status_counts": {},
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 267,
        "record_count": 334,
        "reported_execution_status_counts": {},
        "skip_record_count": 3,
        "source_file_count": 45,
        "status": "read",
        "unbound_decision_reference_count": 281
      },
      "paper": {
        "book_counts": {
          "B": 30
        },
        "consumption_container_count": 30,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 1,
          "kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1": 1,
          "kol-b-both-sparse-20261026-1025-no-new-risk-fc7bb1f8-v1": 1,
          "kol-b-both-sparse-20261027-1355-neutral-8435b899-v1": 2,
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
        "evidence_sha256": "bbce5e6d0ce832928a1dd95ca7084a0219ea1bbcd136bf0d1627700d6f65bda8",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 30,
        "legacy_file_count": 0,
        "missing_consumption_clock_count": 30,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 1,
        "paper_slot_count": 24,
        "paper_terminal_status_counts": {
          "bought": 16,
          "bought_source_blocked": 1,
          "no_buy": 13
        },
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 30,
        "record_count": 30,
        "reported_execution_status_counts": {},
        "skip_record_count": 13,
        "source_file_count": 60,
        "status": "read",
        "unbound_decision_reference_count": 30
      }
    },
    "execution_verification": "not_performed",
    "profit_attribution": "not_established",
    "published_decision_count": 49,
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
      "falsifier": "多独立交易日的点时可成交、费后OOS若显示现行KOL相对no-KOL在同风险暴露下有稳健收益或左尾改善且非单日/单票/来源驱动，则推翻无KOL足以解释表现；若仍无政策作用或合法成交，不判因果。",
      "follow_up": {
        "conclusion": "10月30日冻结研究报告覆盖五个晨间消费日；control与no_kol两组完整模型账户均为98088.45元、-1.91155%、2个模型成交事件和2个未成交计划，差异为零。此零差异仅表示本样本KOL未改变模型经济路径，不证明无KOL长期优劣；10月28日缺测且APP利润未知。继续积累合法、费后独立日和真实作用分母。",
        "disposition": "continue",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64"
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
            "path": "output/live/book_b_live_execution/runs/2026-10-23.json",
            "sha256": "b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-29.json",
            "sha256": "63b7d43ee5b93366c13b5c2ae1c7a023bc1868a12d04c916423956f53bd22c09"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-30.json",
            "sha256": "07ded948eb846d10a007799dd82d0cd2c42b1ab5d1f445aeb51872354f9043b2"
          },
          {
            "path": "output/live/paper_decision_support/consumption/6d66b892a839fc792753238c1d76a5f2c95611b454ded8b20b1e07f438713139.result.json",
            "sha256": "b634afa75f12621defd0e62c9c34367cd4c1c21e2c4b2a125a2b5d87a5addf16"
          },
          {
            "path": "output/live/paper_decision_support/consumption/7b8180ffc50eaa1c29b2d0295727203857a5efab9555731bdffcae702e2866f9.result.json",
            "sha256": "ac7eb939fbea6bb8dfa529afd845c7c5b05d7b30d1007197d54c64ed954bf5d8"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "baseline_no_kol",
      "next_review": "2026-11-06",
      "objective": "续用9月11日稳定编号，在同一冻结、10万元、整手、费用、B分阶段退出和风险预算下比较app_b_control与no_kol完整资金路径；分别报告实际APP与模型差异、现金时间积分、开仓与左尾。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly research maintainer；隔离执行仍需既有研究门指定",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64"
      },
      "required_evidence": [
        "冻结原件/正式政策/首个合法消费及相同资金费用模型",
        "五个已观测日以外的多日OOS完整本金、现金、开仓、未知、未成交、B退出与左尾；保留10月28日缺测，未来原自然日补足完整观察",
        "按作者事件和市场阶段聚类，报告资金时间积分、可成交错失上涨与费用敏感性",
        "APP实际订单/成交/费用独立验真，不把模型收益当APP收益"
      ],
      "rollback": "本轮未启动且生产基线不变。后续研究先锁代码/数据/参数和隔离输出版本，撤回变体并保留失败/回滚证据，不触及正式freeze、账户或安全门。",
      "status": "reviewed_evidence_insufficient"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-current_bounded",
      "falsifier": "若有界保护多次晚于唯一合法机会、无可买卖暴露或到期，且费后可成交错失上涨/执行漏损抵消左尾收益，则拒绝现有经济增量；发布或中性包计数不能作收益。",
      "follow_up": {
        "conclusion": "本周4包只有10月26日一包buy_scale=0，其余中性；10月23日13:42零新增风险发生在APP当晨BUY后且当日T+1不可卖。10月29日APP晨间仅见过期旧包并有原单未决，10月30日APP blocked；纸盘30日买入来源阻断也不能归因KOL。12周49包中10个全局零新增风险、39个中性，未形成个股skip/exit/模式覆盖的收益样本。继续以合法机会分母检验时效，不改TTL和执行门。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64"
          },
          {
            "path": "output/live/kol_policy/context/bdb55081db9bdd7f7bd1ec4ea78dd54a2012f4bbe339cc31baa755f620b73b12.context.json",
            "sha256": "66583c8b9b28f17c58cee859eceff2182eeea4dc5ebb58038c9ad2041e1f2287"
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
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261026-1025-no-new-risk-fc7bb1f8-v1.json",
            "sha256": "3dfc3997b60b38cc641163beca9177dcaf5a6e71c867a567ea0ab55b8c335f49"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261027-1355-neutral-8435b899-v1.json",
            "sha256": "8569e7a3201c73a81c10ccc620ec7f5505dd75d625d8f35f3a90e2f94c7c737a"
          },
          {
            "path": "output/live/kol_policy/source_verifications/kol-b-both-sparse-20261023-1325-no-new-risk-7002f256-v1.json",
            "sha256": "0856baf33eaf860ecc16161d04b4a86e3c037bb0a687ffd3401f7dc88fab8230"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-23.json",
            "sha256": "b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-29.json",
            "sha256": "63b7d43ee5b93366c13b5c2ae1c7a023bc1868a12d04c916423956f53bd22c09"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-30.json",
            "sha256": "07ded948eb846d10a007799dd82d0cd2c42b1ab5d1f445aeb51872354f9043b2"
          },
          {
            "path": "output/live/paper_decision_support/consumption/7b8180ffc50eaa1c29b2d0295727203857a5efab9555731bdffcae702e2866f9.result.json",
            "sha256": "ac7eb939fbea6bb8dfa529afd845c7c5b05d7b30d1007197d54c64ed954bf5d8"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "33ce56e698bfc442eae95d441b809f64fc9bbe7a3791141a7a0f3215a7c67715"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "current_bounded",
      "next_review": "2026-11-06",
      "objective": "续用9月11日稳定编号，按来源—评价—请求/独立审阅—发布—有效期—首个合法消费—原计划—订单/成交逐节点量化当前叠加；每次零新增风险须有当时确有合法新增BUY的分母及可成交错失收益。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly research maintainer；lineage补证由原生产/消费owner协作",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64"
      },
      "required_evidence": [
        "同一报告和观点的source_fingerprint、原发布时间、本地接收、冲突/关系和正式source_verification",
        "模型请求/开始/结束、审核、发布、有效期、首个合法消费及对应候选/账户/行情时钟",
        "每个缩量/跳过/退出的实际政策作用、原计划/柜台成交/费用及T+1、整手、现金边界",
        "APP与paper分账；旧消费时钟只读补证和10月30日缺失EOD原回执，不回填过去交易"
      ],
      "rollback": "本轮不改TTL、调度或执行门；后续隔离遥测须版本化，撤回时保留原事件与失败，不放松来源复核、独立审核、freeze和资金门。",
      "status": "reviewed_evidence_insufficient"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-kol_challenger",
      "falsifier": "若mode_m或入口外挑战在多独立OOS日按同本金、整手、费用、流动性、T+1和共同B退出后不能同时改善机会覆盖与风险调整收益，或优势只来自单一亏损回避、事后赢家、相关来源和缺失标签，则拒绝。",
      "follow_up": {
        "conclusion": "冻结选择样本确有COLD空槽：10月23日2/3、29日18/19、30日15/17行COLD。mode_m研究账户在五个已消费晨间日零成交、10万元现金，而控制出现单一已闭模型亏损；这是参与度与一条路径差异，不是可推广胜率。原选择捕获无资金/成交/退出，入口外挑战仍未运行，旧C-mode裁决为REJECTED。继续隔离研究并补双向错失与尾部。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64"
          },
          {
            "path": "output/live/kol_policy/context/bdb55081db9bdd7f7bd1ec4ea78dd54a2012f4bbe339cc31baa755f620b73b12.context.json",
            "sha256": "66583c8b9b28f17c58cee859eceff2182eeea4dc5ebb58038c9ad2041e1f2287"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-23.json",
            "sha256": "b94770e872e38e56cc2110ca5d1e3e70a2a056485b408ca0757b5ffa3bbf5abd"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-29.json",
            "sha256": "63b7d43ee5b93366c13b5c2ae1c7a023bc1868a12d04c916423956f53bd22c09"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-10-30.json",
            "sha256": "07ded948eb846d10a007799dd82d0cd2c42b1ab5d1f445aeb51872354f9043b2"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-both-sparse-20261027-1355-neutral-8435b899-v1.json",
            "sha256": "8569e7a3201c73a81c10ccc620ec7f5505dd75d625d8f35f3a90e2f94c7c737a"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "kol_challenger",
      "next_review": "2026-11-06",
      "objective": "续用9月11日稳定编号，先在原冻结内对E/COLD与mode_m做同资金可成交多日挑战，再单独预登记竞价、09:31及有限盘中入口外队列；保留UNKNOWN、科创权限、独立Book T和正式执行门。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly research maintainer；入口完整性研究仅走独立研究门",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64"
      },
      "required_evidence": [
        "全量原冻结与入口外点时候选、每行COLD/UNKNOWN/权限/报价/填单限制及当时可见时钟",
        "mode_m与控制的10万元多日模型资金、费用、现金时间积分、未成交、开仓、回撤和共同B退出",
        "入口外单独authority=0预注册、严格OOS、可成交分钟窗口和错失/新增尾部双向计量",
        "旧C-mode REJECTED与来源冲突作为先验反证；模型结果不能推APP资本/执行权限"
      ],
      "rollback": "本轮未启动，候选authority=0；后续研究先固定隔离输出及版本恢复点，撤回变体而保留反证，不触及正式账户、freeze、参数或资本钥匙。",
      "status": "reviewed_evidence_insufficient"
    }
  ],
  "data_evidence_review": {
    "accounting_observations": [
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/031aba0867d10d4b8fc89c8ef1f6e43ff7c84ace80ce93ebdace672706ea9b65.json",
          "sha256": "c26823b677101536b47c2a2cc454c5f4d83806cee3edce1a9ccc894d327f86ab"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-27T01:28:36.139000+00:00",
        "profit_attribution": "not_established",
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 37,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "76395.98",
            "broker_snapshot_sha256": "a7b6ff24e0947ac66f0c0cabf50257112ee02abe7ba25e15be2f2bdb6570fca5",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "65159.65",
            "cash_basis": "app_available_cash",
            "cash_difference": "11236.33",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29592.873906",
            "cumulative_pnl": null,
            "deployable_cash": "65159.65",
            "entry_count": 37,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
            "liquidation_nav": "65159.65",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-27T01:28:36.139000+00:00",
            "observed_cash": "76395.98",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "c48a8e48d1a3be4f7a1e5e2a5c7f5658ff3663a60f5e426ad4bb44a003a851bc",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "provisional_unrealized_pnl": "0.00",
            "realized_pnl": null,
            "receipt_sha256": "49c26149edd43edfb7a9a99bb83e7ddd0f778177b2cbe86448f50fcd55ccbf09",
            "remaining_cost": "0.00",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-27T01:28:36.139000+00:00",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "49c26149edd43edfb7a9a99bb83e7ddd0f778177b2cbe86448f50fcd55ccbf09",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65159.65",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-27T01:28:36.139000+00:00",
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
            },
            {
              "broker_order_id": "6004300",
              "code": "002172.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-26"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "49c26149edd43edfb7a9a99bb83e7ddd0f778177b2cbe86448f50fcd55ccbf09",
          "unrealized_pnl": null
        },
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/0cae7f97ad6550e4b21af76442ff0ce4c420bdcdad197bf1bbb2211312966a5e.json",
          "sha256": "d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-29T07:15:53.603000+00:00",
        "profit_attribution": "not_established",
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 37,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "76395.98",
            "broker_snapshot_sha256": "728da6aef2d60c348018df1ee5a735e0d0749184bef43ef6eb7b21dad8773aeb",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "65159.65",
            "cash_basis": "owned_replay_including_buy_reserve",
            "cash_difference": null,
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29592.873906",
            "cumulative_pnl": null,
            "deployable_cash": "65159.65",
            "entry_count": 37,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
            "liquidation_nav": "65159.65",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-29T07:15:53.603000+00:00",
            "observed_cash": "65159.65",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "c48a8e48d1a3be4f7a1e5e2a5c7f5658ff3663a60f5e426ad4bb44a003a851bc",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "provisional_unrealized_pnl": "0.00",
            "realized_pnl": null,
            "receipt_sha256": "dfc5c590b921062ee42d5d712cc84597a681891b93826a5f53a86d2ef5b55039",
            "remaining_cost": "0.00",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reserve_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-29T07:15:53.603000+00:00",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "dfc5c590b921062ee42d5d712cc84597a681891b93826a5f53a86d2ef5b55039",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65159.65",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-29T07:15:53.603000+00:00",
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
            },
            {
              "broker_order_id": "6004300",
              "code": "002172.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-26"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "dfc5c590b921062ee42d5d712cc84597a681891b93826a5f53a86d2ef5b55039",
          "unrealized_pnl": null
        },
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/11331e61bb9b0d825b7e70c84122e935889523a4c4e294a47fb678c5f1b0d04c.json",
          "sha256": "40fabc542a25482dc8516d32678679e56c7473c8b00336eb3fd615356dc96f8f"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-21T01:31:08.677000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/11d6809532302a8058c19b61f45652ac7c50d7ee7c58941c3f599e75b5fa8944.json",
          "sha256": "c576c3bb194a4148f83d9bfe84068140e24696dce3a16cc558f7bda46f2c4f7b"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-15T07:20:03.515000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/12a8ecd8fd2c7b21dc89e55b97e8bba49d4061e7cc525fae615650ab0d88c709.json",
          "sha256": "05aad28a8c54f6d511525d6429c19568112edfd3414e05f91b7acf3c03643758"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-20T01:31:47.456000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
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
          "path": "output/live/book_b_live_execution/accounting_reports/1c356652b0500fa5e8b6f0bc71ba013a70c9eda8d359d8c4f21b3049bc1d6ae9.json",
          "sha256": "10b9eb24cb29b0cbba07b563d76eb1d998d5bf4b27b3dd346e76a709c27e8d9d"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-22T01:30:40.511000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/1d1864f5b755f1ed207f96e0af7fda45fc41acb182855665215b33fc52b587e8.json",
          "sha256": "22a52777249e095a3a1c3306a04ce8ae80a9d8be78d275cb16e7a7b92e784a5e"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-23T01:31:45.282000+00:00",
        "profit_attribution": "not_established",
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
          "path": "output/live/book_b_live_execution/accounting_reports/4f05fc9f99271615d18abfae3db79c02c35ae82c73e1104b8c3002b3073816b3.json",
          "sha256": "fa036a5795e09cbd63d4f1edbda25fe250d4108ed858b354c0a18ef47ec3b700"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-15T01:36:25.013000+00:00",
        "profit_attribution": "not_established",
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
          "path": "output/live/book_b_live_execution/accounting_reports/67a168e1b12f574245bdd1c67168e6d180be3362c906a32f266004f211516c2b.json",
          "sha256": "0eb20d33bf944f85747c0a98e78226604b1731ef5282a30c441317c980f1bd62"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-19T01:37:16.622000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/68ee4b126230e14ff8ea8108454d2c48cd0aeb4730e764d2a485cb505c1c451d.json",
          "sha256": "fb452d42134a56cc5dd975cb1b47818fbe7e648788072935a68a0ace2534d90c"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-23T07:15:26.462000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/6d157cb173b9029ce4d64aa2d4d8e3d6c3be0934dafe45e2066b0c3d7215da6f.json",
          "sha256": "684934ec6b6cb1172e750536e468c5a9ccd0e3db21da8d38c1211964b33553f9"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-20T07:16:23.521000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/6eafa2842aa86eb253533f69921c9250d2c54e686a866d3551893b14ee73442a.json",
          "sha256": "bab487e32dff3c2339c980fd87df5034a7165f31c21981f8a7043a8d2c616af0"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-09T06:45:04.837000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/7be3c693ec969698682eff4853f9a69dbcea56130283c41ea44a7066e0ac759c.json",
          "sha256": "bb7d77165b7e1c5be0dc15182d64555c0002fff0be084f17aadefe24c3240869"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-26T01:26:43.205000+00:00",
        "profit_attribution": "not_established",
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
            "broker_available_cash": "43615.38",
            "broker_snapshot_sha256": "9083945a6776548c780d62c69e04322c96de3f67c67a45144c4e1d3b996a46f5",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "32360.93",
            "cash_basis": "app_available_cash",
            "cash_difference": "11254.45",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29522.942427",
            "cumulative_pnl": null,
            "deployable_cash": "32360.93",
            "entry_count": 36,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.26",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "1a9d59f7f8e7846ec331f9eaa86be0fc8b25d2c67a685515bbcf4ac7ae6fdbf9",
            "ledger_cash": "32360.93",
            "liquidation_nav": "65005.67",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "002172.XSHE",
                "owned_lot_id": "book-b:2026-10-23:002172.XSHE:BUY",
                "remaining_cost": "32189.22",
                "shares": 7700
              }
            ],
            "marked_nav": "65008.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-26T01:26:43.205000+00:00",
            "observed_cash": "43615.38",
            "opening_capital": "30000.00",
            "owned_market_value": "32648.00",
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
            "provisional_unrealized_pnl": "458.78",
            "realized_pnl": null,
            "receipt_sha256": "d48903567b3855e54e4406f1675ff68ba4846ab8b7922e77f899cd364a6dfa17",
            "remaining_cost": "32189.22",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65008.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-26T01:26:43.205000+00:00",
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
            "source_observation_sha256": "d48903567b3855e54e4406f1675ff68ba4846ab8b7922e77f899cd364a6dfa17",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65008.93",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-26T01:26:43.205000+00:00",
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
          "source_observation_sha256": "d48903567b3855e54e4406f1675ff68ba4846ab8b7922e77f899cd364a6dfa17",
          "unrealized_pnl": null
        },
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/81e7d54e2258fd58ae3d19f7db822a9b4b34c766d14dda522a61efd894678d6d.json",
          "sha256": "911c17076290583cddea0bd8195d27756db616238035e460462723e7c29ea9bb"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-27T07:16:05.869000+00:00",
        "profit_attribution": "not_established",
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 37,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "76395.98",
            "broker_snapshot_sha256": "4237760a41206befa74cd17bb4f150cf1eba6fca741d8ec6de31865163b11218",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "65159.65",
            "cash_basis": "app_available_cash",
            "cash_difference": "11236.33",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29592.873906",
            "cumulative_pnl": null,
            "deployable_cash": "65159.65",
            "entry_count": 37,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
            "liquidation_nav": "65159.65",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-27T07:16:05.869000+00:00",
            "observed_cash": "76395.98",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "c48a8e48d1a3be4f7a1e5e2a5c7f5658ff3663a60f5e426ad4bb44a003a851bc",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "provisional_unrealized_pnl": "0.00",
            "realized_pnl": null,
            "receipt_sha256": "488fb9e4a82ad6271eb7bd2ed45a1763d723202148293d3bc581ae903566d2d8",
            "remaining_cost": "0.00",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-27T07:16:05.869000+00:00",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "488fb9e4a82ad6271eb7bd2ed45a1763d723202148293d3bc581ae903566d2d8",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65159.65",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-27T07:16:05.869000+00:00",
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
            },
            {
              "broker_order_id": "6004300",
              "code": "002172.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-26"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "488fb9e4a82ad6271eb7bd2ed45a1763d723202148293d3bc581ae903566d2d8",
          "unrealized_pnl": null
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
          "path": "output/live/book_b_live_execution/accounting_reports/9049d8b69c2efd7c1b784f732c2e14fce068708857b77c136831085b1e6d689e.json",
          "sha256": "68225c161befdb1eb84f63b937982dbee9c61bea0dbef8edff14f28eee2669af"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-13T07:16:32.855000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/93aef1dfd2aab4d323cc7da9c469dca14ebb4b8198998423cf72fc32f7b7101f.json",
          "sha256": "6e3076b3f1ccd6823684d2624da1e0b192ce5c7c3a013a8e5aef95110a634753"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-08T07:21:52.104000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/a3a2a2b46447f33b1dffbdbbb3f0c195d3804eb22258b018dd54ae7e41af6c02.json",
          "sha256": "bef91a70ed21a02cb97a3c4356011d41aa8d7d5b65d8f6c7e1091d2ee45aaf42"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-16T08:03:28.059000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/a79b0a50694bdf081ac8130f67d753be04acb81e7a10312ad3d642eb815ab87b.json",
          "sha256": "cb8670c6a15a7d7bf65e37cf9d4f991f5cbf6adbc462e9e1e092d24bd0773359"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-26T07:15:58.479000+00:00",
        "profit_attribution": "not_established",
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 37,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "76394.98",
            "broker_snapshot_sha256": "314c3e9afc8ff40761d52cac2c348962cf0ddc75c994422a50775aaf50079dd6",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "65159.65",
            "cash_basis": "app_available_cash",
            "cash_difference": "11235.33",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29592.873906",
            "cumulative_pnl": null,
            "deployable_cash": "65159.65",
            "entry_count": 37,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
            "liquidation_nav": "65159.65",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-26T07:15:58.479000+00:00",
            "observed_cash": "76394.98",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "c48a8e48d1a3be4f7a1e5e2a5c7f5658ff3663a60f5e426ad4bb44a003a851bc",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "provisional_unrealized_pnl": "0.00",
            "realized_pnl": null,
            "receipt_sha256": "028abb0adab2b5e36b98e55d4da2e08786784f88484e88cb5f84316a18f403db",
            "remaining_cost": "0.00",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-26T07:15:58.479000+00:00",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "028abb0adab2b5e36b98e55d4da2e08786784f88484e88cb5f84316a18f403db",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65159.65",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-26T07:15:58.479000+00:00",
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
            },
            {
              "broker_order_id": "6004300",
              "code": "002172.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-26"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "028abb0adab2b5e36b98e55d4da2e08786784f88484e88cb5f84316a18f403db",
          "unrealized_pnl": null
        },
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/c17b2b3981b4fbd47af69ae11c14e817560936a6670a0a156f1e82f6ae409d85.json",
          "sha256": "8428796ec2d2b4301d8b5a553ab8e33bf21263653e66f55aafffd35a3d605cc7"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-16T01:31:46.380000+00:00",
        "profit_attribution": "not_established",
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
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/c8de32a296b2f3506e04a38dc352771851340c649e4393ab38bace8029792445.json",
          "sha256": "803b3c25aeda3474fcd2b2585631326529bdac664bf279208ec1322ab8e79390"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-16T07:15:54.737000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/cc642c97ff781a8cced7d00f31530e6c9c263088ff32e509031dfc62a6485be3.json",
          "sha256": "e2b1733a766cd6cd11b86a2b3289608d14db28f776f5fd69ea8aafec2a4ea6ac"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-19T07:16:16.247000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/e71dd52554d41a77b344d5635567bd0bf2825292ae8ccbe5802f4fe4218c0151.json",
          "sha256": "199328b7f1106fb4a2767794191e1667692c087f7a47410b3f56bf6e6f01e129"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-30T07:17:21.233000+00:00",
        "profit_attribution": "not_established",
        "report": {
          "journal": {
            "database_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting.sqlite3",
            "entry_count": 37,
            "fee_status": "actual_fees_pending",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "realized_pnl": null
          },
          "schema_version": "book-b-statement.v2",
          "source_observation": {
            "book": "B",
            "broker_available_cash": "76395.98",
            "broker_snapshot_sha256": "788c1ca00739947759e911db896c10639cd3e17e42a9a398ab6b56fd9e03552c",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "65159.65",
            "cash_basis": "owned_replay_including_buy_reserve",
            "cash_difference": null,
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29592.873906",
            "cumulative_pnl": null,
            "deployable_cash": "65159.65",
            "entry_count": 37,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "0.00",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "b75c208ef910f0d96f0a13163d2c998f40177c1ae41be86c52af25556d504d07",
            "ledger_cash": "65159.65",
            "liquidation_nav": "65159.65",
            "logical_account_id": "primary",
            "lots": [],
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-30T07:17:21.233000+00:00",
            "observed_cash": "65159.65",
            "opening_capital": "30000.00",
            "owned_market_value": "0.00",
            "ownership_head_sha256": "c48a8e48d1a3be4f7a1e5e2a5c7f5658ff3663a60f5e426ad4bb44a003a851bc",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "provisional_realized_pnl": "-685.75",
            "provisional_unrealized_pnl": "0.00",
            "realized_pnl": null,
            "receipt_sha256": "e826454ff78396b022df912416c7ccdc90a3776d1ad9893ab9b3073096d855ad",
            "remaining_cost": "0.00",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reserve_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65159.65",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-30T07:17:21.233000+00:00",
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
              },
              {
                "broker_order_id": "6004300",
                "code": "002172.XSHE",
                "side": "SELL",
                "trade_date": "2026-10-26"
              }
            ],
            "realized_pnl": null,
            "source_observation_sha256": "e826454ff78396b022df912416c7ccdc90a3776d1ad9893ab9b3073096d855ad",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65159.65",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-30T07:17:21.233000+00:00",
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
            },
            {
              "broker_order_id": "6004300",
              "code": "002172.XSHE",
              "side": "SELL",
              "trade_date": "2026-10-26"
            }
          ],
          "realized_pnl": null,
          "source_observation_sha256": "e826454ff78396b022df912416c7ccdc90a3776d1ad9893ab9b3073096d855ad",
          "unrealized_pnl": null
        },
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/e7c5a5678234879cbad0ad4448221c0a59056e9e683c7540cc3337de386fb3f4.json",
          "sha256": "e7dcf98d44bb888889dc729fb9c39bbc423e00a88d2b877c06d0766ed10a3360"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-09T01:45:43.626000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/f17924bf2ab7daeafc441e55e73387816999a3b5e07656831078b601fc63850f.json",
          "sha256": "7d01fda770c85501b36afac07431a7f2aa32c5a375f40982e84138913de184a6"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-21T07:16:31.258000+00:00",
        "profit_attribution": "not_established",
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
        "valuation_status": "dated_observation"
      },
      {
        "evidence": {
          "path": "output/live/book_b_live_execution/accounting_reports/fe0ca031299a04a0af8734a87d9028a03a7981be8b16cb1048f03d9ea06c26dd.json",
          "sha256": "a8516492ea362e95b9263db8f5d93834676dc805441ddab68e1e4482320337b4"
        },
        "missing_evidence": [
          "full dated settlement/capital-flow chain and actual-fee verification required"
        ],
        "observed_at": "2026-10-26T01:28:47.784000+00:00",
        "profit_attribution": "not_established",
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
            "broker_available_cash": "43615.38",
            "broker_snapshot_sha256": "eaadb60da06bb1bf25c770bc682a1fd30cbdfba51faeeafa84f25a36aeae260a",
            "capital_flow_head_sha256": "5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423",
            "cash": "32360.93",
            "cash_basis": "app_available_cash",
            "cash_difference": "11254.45",
            "cash_discrepancy_limit": "10.00",
            "cash_integrity_proven": false,
            "conservative_risk_nav": "29522.942427",
            "cumulative_pnl": null,
            "deployable_cash": "32360.93",
            "entry_count": 36,
            "environment": "app_server_simulation",
            "estimated_exit_fee": "3.26",
            "fee_basis": "provisional_pending_actual_fees",
            "fee_status": "actual_fees_pending",
            "fund_account_binding_sha256": "c949bbd5f21c56703a9c2dfce584f020e1147a4c8cd59472257ebdd126ec07df",
            "journal_head_sha256": "1a9d59f7f8e7846ec331f9eaa86be0fc8b25d2c67a685515bbcf4ac7ae6fdbf9",
            "ledger_cash": "32360.93",
            "liquidation_nav": "65005.67",
            "logical_account_id": "primary",
            "lots": [
              {
                "code": "002172.XSHE",
                "owned_lot_id": "book-b:2026-10-23:002172.XSHE:BUY",
                "remaining_cost": "32189.22",
                "shares": 7700
              }
            ],
            "marked_nav": "65008.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-26T01:28:47.784000+00:00",
            "observed_cash": "43615.38",
            "opening_capital": "30000.00",
            "owned_market_value": "32648.00",
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
            "provisional_unrealized_pnl": "458.78",
            "realized_pnl": null,
            "receipt_sha256": "e74a8ac85f6411a00f51fb08a6140902fd594542fdee55451c353757e577cc45",
            "remaining_cost": "32189.22",
            "risk_unit_factor": "2.201869619223247326039816083",
            "schema_version": "book-b-accounting.v1",
            "status": "cash_reconciliation_required",
            "unrealized_pnl": null
          },
          "valuation": {
            "cumulative_pnl": null,
            "fee_status": "actual_fees_pending",
            "marked_nav": "65008.93",
            "net_contributed_capital": "65845.40",
            "observed_at": "2026-10-26T01:28:47.784000+00:00",
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
            "source_observation_sha256": "e74a8ac85f6411a00f51fb08a6140902fd594542fdee55451c353757e577cc45",
            "unrealized_pnl": null
          },
          "valuation_status": "dated_observation"
        },
        "valuation": {
          "cumulative_pnl": null,
          "fee_status": "actual_fees_pending",
          "marked_nav": "65008.93",
          "net_contributed_capital": "65845.40",
          "observed_at": "2026-10-26T01:28:47.784000+00:00",
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
          "source_observation_sha256": "e74a8ac85f6411a00f51fb08a6140902fd594542fdee55451c353757e577cc45",
          "unrealized_pnl": null
        },
        "valuation_status": "dated_observation"
      }
    ],
    "app_b_forward": {
      "accounts": {
        "app_b_control": {
          "app_realized_profit": null,
          "cash": 98088.45,
          "drawdown_coverage": "incomplete",
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
            },
            "2026-10-26": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-26T15:16:18.438449+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-26T07:16:18.438449+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "12681e41649771f4afdb056f0e8d0588c73676eaadf2db9f9435bf35c2cacf4c",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-26T07:16:18.438449+00:00",
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
              "source_sha256": "a166b206b2ac347736cadeec76aa48040aa6dc5759cdaf29ad215257bd3a8f64",
              "status": "marked"
            },
            "2026-10-27": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-27T15:16:23.439397+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-27T07:16:23.439397+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "7c38e10f4e64e32d396f9a5cdc45c9c399be1b5ed62d9963599dd802fe56a105",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-27T07:16:23.439397+00:00",
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
              "source_sha256": "77fe7e4e9ebedc5d91016aab66e6b77998368ff0de9d11f7b51af0ebc610ad2b",
              "status": "marked"
            },
            "2026-10-29": {
              "cash_cents": 8130613,
              "market_value_cents": 1611000,
              "nav_cents": 9741452,
              "observed_at": "2026-10-29T15:16:21.346769+08:00",
              "portfolio_sha256": "7ef28d952111877cc06f6c803ba4f5bde2c9a0fd557e56b2cdff64e56065da88",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-29T07:16:21.346769+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 2.58548,
                "evidence_digest": "db938c67808974f557b9a822fcc55b356779239fcff93412029797530d85b173",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 97414.52,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-29T07:16:21.346769+00:00",
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
              "source_sha256": "5f45829cf786bd73ca5d6b6b4ab8b19bb89daf65a53edb8d2c0bafac8dcdd584",
              "status": "marked"
            },
            "2026-10-30": {
              "cash_cents": 9808845,
              "market_value_cents": 0,
              "nav_cents": 9808845,
              "observed_at": "2026-10-30T15:17:45.481714+08:00",
              "portfolio_sha256": "c7d6b175f2a9c1a156fb0f0cde6da674e4a787acabcd26dfbdc05c674ac94506",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-30T07:17:45.481714+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 1.91155,
                "evidence_digest": "7a0bac7fbe40d399f8c769d7f2d46e7c51e45d5dc388f4dff04fac1b63980390",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 98088.45,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-30T07:17:45.481714+00:00",
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
              "source_sha256": "92b0f1051aa3441896f668a03e5a66a9d6f4e3652cbabe24419b282921748142",
              "status": "marked"
            }
          },
          "estimated_fees": 3.55,
          "fee_status": "protocol_model_rate",
          "filled_orders": 2,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 98088.45,
          "missing_eod_dates": [
            "2026-10-28"
          ],
          "net_model_return_pct": -1.9115499999999952,
          "no_fill_orders": 2,
          "observed_eod_max_drawdown_pct": 2.5854799999999956,
          "open_lots": 0,
          "partial_expired_orders": 0,
          "pending_orders": 0,
          "planned_orders": 4,
          "realized_model_pnl": -1911.55,
          "reserved_cash": 0.0,
          "unknown_orders": 0,
          "valuation_observed_at": "2026-10-30T15:17:45.481714+08:00"
        },
        "mode_m": {
          "app_realized_profit": null,
          "cash": 100000.0,
          "drawdown_coverage": "incomplete",
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
            },
            "2026-10-26": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-26T15:16:18.438449+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-26T07:16:18.438449+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "12681e41649771f4afdb056f0e8d0588c73676eaadf2db9f9435bf35c2cacf4c",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-26T07:16:18.438449+00:00",
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
              "source_sha256": "a166b206b2ac347736cadeec76aa48040aa6dc5759cdaf29ad215257bd3a8f64",
              "status": "marked"
            },
            "2026-10-27": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-27T15:16:23.439397+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-27T07:16:23.439397+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "7c38e10f4e64e32d396f9a5cdc45c9c399be1b5ed62d9963599dd802fe56a105",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-27T07:16:23.439397+00:00",
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
              "source_sha256": "77fe7e4e9ebedc5d91016aab66e6b77998368ff0de9d11f7b51af0ebc610ad2b",
              "status": "marked"
            },
            "2026-10-29": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-29T15:16:21.346769+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-29T07:16:21.346769+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "f8e7c0cb1cb36886d4b60d2de9ef253881128fd6238abfc522a5cc09cc7cf54a",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-29T07:16:21.346769+00:00",
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
              "source_sha256": "5f45829cf786bd73ca5d6b6b4ab8b19bb89daf65a53edb8d2c0bafac8dcdd584",
              "status": "marked"
            },
            "2026-10-30": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-30T15:17:45.481714+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-30T07:17:45.481714+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "d8f44397c7ad94ae94b4622c6bdf072ea932fb27cc83cad34892217c75580a3f",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-30T07:17:45.481714+00:00",
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
              "source_sha256": "92b0f1051aa3441896f668a03e5a66a9d6f4e3652cbabe24419b282921748142",
              "status": "marked"
            }
          },
          "estimated_fees": 0.0,
          "fee_status": "protocol_model_rate",
          "filled_orders": 0,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 100000.0,
          "missing_eod_dates": [
            "2026-10-28"
          ],
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
          "valuation_observed_at": "2026-10-30T15:17:45.481714+08:00"
        },
        "no_kol": {
          "app_realized_profit": null,
          "cash": 98088.45,
          "drawdown_coverage": "incomplete",
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
            },
            "2026-10-26": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-26T15:16:18.438449+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-26T07:16:18.438449+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "12681e41649771f4afdb056f0e8d0588c73676eaadf2db9f9435bf35c2cacf4c",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-26T07:16:18.438449+00:00",
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
              "source_sha256": "a166b206b2ac347736cadeec76aa48040aa6dc5759cdaf29ad215257bd3a8f64",
              "status": "marked"
            },
            "2026-10-27": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-27T15:16:23.439397+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-27T07:16:23.439397+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "7c38e10f4e64e32d396f9a5cdc45c9c399be1b5ed62d9963599dd802fe56a105",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-27T07:16:23.439397+00:00",
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
              "source_sha256": "77fe7e4e9ebedc5d91016aab66e6b77998368ff0de9d11f7b51af0ebc610ad2b",
              "status": "marked"
            },
            "2026-10-29": {
              "cash_cents": 8130613,
              "market_value_cents": 1611000,
              "nav_cents": 9741452,
              "observed_at": "2026-10-29T15:16:21.346769+08:00",
              "portfolio_sha256": "7ef28d952111877cc06f6c803ba4f5bde2c9a0fd557e56b2cdff64e56065da88",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-29T07:16:21.346769+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 2.58548,
                "evidence_digest": "db938c67808974f557b9a822fcc55b356779239fcff93412029797530d85b173",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 97414.52,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-29T07:16:21.346769+00:00",
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
              "source_sha256": "5f45829cf786bd73ca5d6b6b4ab8b19bb89daf65a53edb8d2c0bafac8dcdd584",
              "status": "marked"
            },
            "2026-10-30": {
              "cash_cents": 9808845,
              "market_value_cents": 0,
              "nav_cents": 9808845,
              "observed_at": "2026-10-30T15:17:45.481714+08:00",
              "portfolio_sha256": "c7d6b175f2a9c1a156fb0f0cde6da674e4a787acabcd26dfbdc05c674ac94506",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-30T07:17:45.481714+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 1.91155,
                "evidence_digest": "7a0bac7fbe40d399f8c769d7f2d46e7c51e45d5dc388f4dff04fac1b63980390",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 98088.45,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-30T07:17:45.481714+00:00",
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
              "source_sha256": "92b0f1051aa3441896f668a03e5a66a9d6f4e3652cbabe24419b282921748142",
              "status": "marked"
            }
          },
          "estimated_fees": 3.55,
          "fee_status": "protocol_model_rate",
          "filled_orders": 2,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 98088.45,
          "missing_eod_dates": [
            "2026-10-28"
          ],
          "net_model_return_pct": -1.9115499999999952,
          "no_fill_orders": 2,
          "observed_eod_max_drawdown_pct": 2.5854799999999956,
          "open_lots": 0,
          "partial_expired_orders": 0,
          "pending_orders": 0,
          "planned_orders": 4,
          "realized_model_pnl": -1911.55,
          "reserved_cash": 0.0,
          "unknown_orders": 0,
          "valuation_observed_at": "2026-10-30T15:17:45.481714+08:00"
        },
        "open_limit": {
          "app_realized_profit": null,
          "cash": 98180.46,
          "drawdown_coverage": "incomplete",
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
            },
            "2026-10-26": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-26T15:16:18.438449+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-26T07:16:18.438449+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "12681e41649771f4afdb056f0e8d0588c73676eaadf2db9f9435bf35c2cacf4c",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-26T07:16:18.438449+00:00",
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
              "source_sha256": "a166b206b2ac347736cadeec76aa48040aa6dc5759cdaf29ad215257bd3a8f64",
              "status": "marked"
            },
            "2026-10-27": {
              "cash_cents": 10000000,
              "market_value_cents": 0,
              "nav_cents": 10000000,
              "observed_at": "2026-10-27T15:16:23.439397+08:00",
              "portfolio_sha256": "814664da3a9623685b96a14040d9b43d47c64d82837c3f2e607a9744fb487e04",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-27T07:16:23.439397+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 0.0,
                "evidence_digest": "7c38e10f4e64e32d396f9a5cdc45c9c399be1b5ed62d9963599dd802fe56a105",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 100000.0,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-27T07:16:23.439397+00:00",
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
              "source_sha256": "77fe7e4e9ebedc5d91016aab66e6b77998368ff0de9d11f7b51af0ebc610ad2b",
              "status": "marked"
            },
            "2026-10-29": {
              "cash_cents": 8139814,
              "market_value_cents": 1611000,
              "nav_cents": 9750653,
              "observed_at": "2026-10-29T15:16:21.346769+08:00",
              "portfolio_sha256": "033301df5d1251b098321082160308ade2e02658f53200b869c1e33f87a1a78c",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-29T07:16:21.346769+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 2.49347,
                "evidence_digest": "8804c4375e1e669ac3bc64be08651aba58fb4ccf5f57adc742728e18406cf249",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 97506.53,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-29T07:16:21.346769+00:00",
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
              "source_sha256": "5f45829cf786bd73ca5d6b6b4ab8b19bb89daf65a53edb8d2c0bafac8dcdd584",
              "status": "marked"
            },
            "2026-10-30": {
              "cash_cents": 9818046,
              "market_value_cents": 0,
              "nav_cents": 9818046,
              "observed_at": "2026-10-30T15:17:45.481714+08:00",
              "portfolio_sha256": "862163af60c3ddc7606b8281e7adf30bd78668a69f5c5202238ce7c5069e48b6",
              "reserved_cents": 0,
              "risk": {
                "account_id": "paper:B",
                "asof": "2026-10-30T07:17:45.481714+00:00",
                "capital_flow_head_sha256": null,
                "current_nav_lower_bound": null,
                "deploy_factor": 1.0,
                "drawdown_pct": 1.81954,
                "evidence_digest": "d051e35a5a798e2320965dcee4d9d9b0658f08d3b0da54e18fca8be18b624e0e",
                "expected_settlement_date": "",
                "high_water_mark": 100000.0,
                "history_basis": "since_activation",
                "initial_capital": 100000.0,
                "nav": 98180.46,
                "nav_basis": "book_b_cash_plus_liquidation_after_exit_fee",
                "nav_observed_at": "2026-10-30T07:17:45.481714+00:00",
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
              "source_sha256": "92b0f1051aa3441896f668a03e5a66a9d6f4e3652cbabe24419b282921748142",
              "status": "marked"
            }
          },
          "estimated_fees": 3.54,
          "fee_status": "protocol_model_rate",
          "filled_orders": 2,
          "manual_assistance": "not_applicable_research_model",
          "marked_nav": 98180.46,
          "missing_eod_dates": [
            "2026-10-28"
          ],
          "net_model_return_pct": -1.8195399999999973,
          "no_fill_orders": 2,
          "observed_eod_max_drawdown_pct": 2.4934699999999976,
          "open_lots": 0,
          "partial_expired_orders": 0,
          "pending_orders": 0,
          "planned_orders": 4,
          "realized_model_pnl": -1819.54,
          "reserved_cash": 0.0,
          "unknown_orders": 0,
          "valuation_observed_at": "2026-10-30T15:17:45.481714+08:00"
        }
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
        },
        {
          "app_receipt_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/runs/history/2026-10-26-545c7fa7f037.json",
          "app_receipt_sha256": "3a689e7df4f03d91985988e6309691f35c8c902982786b9ea05515e189be4b4a",
          "app_run_id": "2026-10-26-545c7fa7f037",
          "fill_or_return_equivalence": "not_established",
          "first_divergence": "account_allocation",
          "left_sha256": "1dc84e99e67756e97d3d55842290e1949a90e096f7e9dcce408d9b2030f6738f",
          "research_event_sha256": "b4e330297650f97f41d2f7a9e8e959d8516ddad33a878aa8c80fe83eedabe820",
          "right_sha256": "15c0adf464a55ef7bb8893a3673bb31c2bcc82c1b75c2d03a8f792651d89c216",
          "same_order_economics": true,
          "status": "compared",
          "trade_date": "2026-10-26"
        },
        {
          "app_receipt_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/runs/history/2026-10-27-32b776156e59.json",
          "app_receipt_sha256": "274f9592f39966623fa35ea4826b1b510155f2b7651b5e2ba794061532f18973",
          "app_run_id": "2026-10-27-32b776156e59",
          "fill_or_return_equivalence": "not_established",
          "first_divergence": "account_allocation",
          "left_sha256": "a95dc9cb8973f5dc3aa402931cb88d25f07168ddbd030de2d5e88f6a688d329c",
          "research_event_sha256": "d64cace24d592a62c17cc1bad040b7b135fd762fe8f9c4464afaf506eabc3cb2",
          "right_sha256": "e3a48398107a63a76699120bc7f809c2d766bace3bd77f598fc9da9edcd296d1",
          "same_order_economics": true,
          "status": "compared",
          "trade_date": "2026-10-27"
        },
        {
          "app_receipt_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/runs/history/2026-10-29-de3c68ac7e0c.json",
          "app_receipt_sha256": "63b7d43ee5b93366c13b5c2ae1c7a023bc1868a12d04c916423956f53bd22c09",
          "app_run_id": "2026-10-29-de3c68ac7e0c",
          "fill_or_return_equivalence": "not_established",
          "first_divergence": "account_allocation",
          "left_sha256": "665a61356051c7ffd08a8abf1d5f0617dac33cd29e901924eca4fc156297309a",
          "research_event_sha256": "3ac5df31b49dfc6c162588473386bc22275d314b31df8935f6cc7b31cdb69d69",
          "right_sha256": "13aeb0ecdce7d20310afee322658cb06f03ce03e8573c7cd3b8e05cfbac69e4d",
          "same_order_economics": false,
          "status": "compared",
          "trade_date": "2026-10-29"
        },
        {
          "control_sha256": "7080f4094cce5d2ce50882d29f10d8752d92bcc8ac8d4b68dc6098723e13907c",
          "research_event_sha256": "e8a43beb428d4b06b395bbdca18032b97c10e8aa8e26c5d4fd1e5ad7ae7d6d16",
          "status": "app_final_plan_unproved",
          "trade_date": "2026-10-30"
        }
      ],
      "authority": 0,
      "calendar_coverage": {
        "observed_through": "2026-10-30",
        "report_date": "2026-10-30",
        "status": "covered_through_report_date",
        "unproved_tail": null
      },
      "consumed_morning_days": [
        "2026-10-23",
        "2026-10-26",
        "2026-10-27",
        "2026-10-29",
        "2026-10-30"
      ],
      "missing_morning_dates": [
        "2026-10-28"
      ],
      "promotion": "PROPOSAL_ONLY",
      "source_path": "output/research/app_b_forward/performance.json",
      "source_reported_at": "2026-10-30T20:28:45.265530+08:00",
      "source_sha256": "e7928be7adb3e6516decb53fa52cead8f6701c275db13ace2a2591e09e5b3d7e",
      "status": "observed_model_accounts"
    },
    "as_of": "2026-10-30",
    "authority": "research_observer_only",
    "eod_feedback": {
      "as_of": "2026-10-30",
      "authority": 0,
      "errors": [],
      "items": [
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/live/book_b_live_execution/runs/intraday/archive/2026-10-29-eod-20261029T151531410149+0800-3750.json",
              "sha256": "6e197a64ed171c5d85e85db9ce15c6c1ce808263f60a6c1fcf8af2872e6371c0"
            },
            {
              "path": "output/live/book_b_live_execution/accounting_reports/0cae7f97ad6550e4b21af76442ff0ce4c420bdcdad197bf1bbb2211312966a5e.json",
              "sha256": "d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545"
            }
          ],
          "falsifier": "同一账户原始资金事件和全部 owned order 原生费用凭据补齐，且 journal 验证通过",
          "first_seen": "2026-10-26",
          "id": "app-b-actual-fees-and-unclassified-cash",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "逐日用新 account.accounting 检查事实变化；周度说明缺证与影响，不从余额差推费用或资金",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "owner": "native fee/cash evidence owner; xiaocao-daily-eod reconciles",
          "prior_weekly_response": null,
          "status": "open",
          "summary": "当前BUY预留未证，cash_reserve_reconciliation_required/cash_difference null；34单实际费用缺失，最终盈亏N/A。"
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/live/book_b_live_execution/runs/intraday/archive/2026-10-29-eod-20261029T151531410149+0800-3750.json",
              "sha256": "6e197a64ed171c5d85e85db9ce15c6c1ce808263f60a6c1fcf8af2872e6371c0"
            },
            {
              "path": "output/research/eod_audit_20261029/morning-app-task-trace.json",
              "sha256": "21b66aad8b093f3c807c3f14799b81c5445227931c03d4b3aea5f72aad3715c3"
            }
          ],
          "falsifier": "同账户exact order终态及完整预留证明，或新证据推翻原snapshot/当前owned事实。",
          "first_seen": "2026-10-29",
          "id": "app-b-current-buy-order-identity-unproven/2026-10-29/688028.XSHG",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "保留exact plan/hash/claim，只取精确终态与资金预留证据；不得重报或用空表推拒单。",
          "next_verification": "2026-10-30下一合法原始晨间/EOD/Weekly按各自权限验收",
          "observations": 1,
          "owner": "original APP morning order evidence owner; next legal read-only reconciliation owner",
          "prevention_test": "c98840a3 STAR new-BUY filtering, submit claim and unknown quantity proof regressions",
          "prior_weekly_response": null,
          "production_verification": "order_terminal_unproven; current EOD full snapshot read verified",
          "status": "open",
          "summary": "原BUY300@93.46仍UNKNOWN，无柜台号/已证成交/预留终态；影响日间APP检查点及正式结算。"
        },
        {
          "account_id": "app_b_control",
          "basis": "observed",
          "comparable": false,
          "completed_exit_samples": 0,
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "effective_samples": 0,
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/research/app_b_forward/performance.json",
              "sha256": "b386fcc24414589fda7a493e0c721dfb7ec4618157670dd0a07ad9fa6488fc3c"
            },
            {
              "path": "output/research/app_b_forward/state.json",
              "sha256": "9d3fab9aa4aacef062fcb5dcd922c4693324ef9b0cb0990c6a685dfd7928449e"
            },
            {
              "path": "output/live/eod_post_business/xiaocao-daily-eod/2026-10-29/research/stdout.log",
              "sha256": "2e3273634bf77def62fb71a2051279f157a9c1e33887ef4a2e56fb57b99dfc82"
            }
          ],
          "falsifier": "同协议可比的原始未来窗口/成交/费用/标记证据形成足够独立样本",
          "first_seen": "2026-10-26",
          "id": "app-b-forward-funded-v1/app_b_control",
          "kind": "experiment",
          "last_seen": "2026-10-29",
          "model_authority": 0,
          "next_action": "沿已登记路径观察未来窗口；周度核对有效样本、机会覆盖、费用与可比性，决定继续/修正/停止建议",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "open_filled_entries": 1,
          "owner": "xiaocao-weekly-deep-review / existing funded research owner",
          "prior_weekly_response": null,
          "sample_unit": "completed independent funded round-trip; open filled entries are reported separately",
          "status": "insufficient_evidence",
          "summary": "app_b_control: filled entry 1, open lots 1, model NAV 97414.52; no completed exits, missing 10-28, insufficient comparable evidence."
        },
        {
          "account_id": "mode_m",
          "basis": "observed",
          "comparable": false,
          "completed_exit_samples": 0,
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "effective_samples": 0,
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/research/app_b_forward/performance.json",
              "sha256": "b386fcc24414589fda7a493e0c721dfb7ec4618157670dd0a07ad9fa6488fc3c"
            },
            {
              "path": "output/research/app_b_forward/state.json",
              "sha256": "9d3fab9aa4aacef062fcb5dcd922c4693324ef9b0cb0990c6a685dfd7928449e"
            },
            {
              "path": "output/live/eod_post_business/xiaocao-daily-eod/2026-10-29/research/stdout.log",
              "sha256": "2e3273634bf77def62fb71a2051279f157a9c1e33887ef4a2e56fb57b99dfc82"
            }
          ],
          "falsifier": "同协议可比的原始未来窗口/成交/费用/标记证据形成足够独立样本",
          "first_seen": "2026-10-26",
          "id": "app-b-forward-funded-v1/mode_m",
          "kind": "experiment",
          "last_seen": "2026-10-29",
          "model_authority": 0,
          "next_action": "沿已登记路径观察未来窗口；周度核对有效样本、机会覆盖、费用与可比性，决定继续/修正/停止建议",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "open_filled_entries": 0,
          "owner": "xiaocao-weekly-deep-review / existing funded research owner",
          "prior_weekly_response": null,
          "sample_unit": "completed independent funded round-trip; open filled entries are reported separately",
          "status": "insufficient_evidence",
          "summary": "mode_m: filled entry 0, open lots 0, model NAV 100000.0; no completed exits, missing 10-28, insufficient comparable evidence."
        },
        {
          "account_id": "no_kol",
          "basis": "observed",
          "comparable": false,
          "completed_exit_samples": 0,
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "effective_samples": 0,
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/research/app_b_forward/performance.json",
              "sha256": "b386fcc24414589fda7a493e0c721dfb7ec4618157670dd0a07ad9fa6488fc3c"
            },
            {
              "path": "output/research/app_b_forward/state.json",
              "sha256": "9d3fab9aa4aacef062fcb5dcd922c4693324ef9b0cb0990c6a685dfd7928449e"
            },
            {
              "path": "output/live/eod_post_business/xiaocao-daily-eod/2026-10-29/research/stdout.log",
              "sha256": "2e3273634bf77def62fb71a2051279f157a9c1e33887ef4a2e56fb57b99dfc82"
            }
          ],
          "falsifier": "同协议可比的原始未来窗口/成交/费用/标记证据形成足够独立样本",
          "first_seen": "2026-10-26",
          "id": "app-b-forward-funded-v1/no_kol",
          "kind": "experiment",
          "last_seen": "2026-10-29",
          "model_authority": 0,
          "next_action": "沿已登记路径观察未来窗口；周度核对有效样本、机会覆盖、费用与可比性，决定继续/修正/停止建议",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "open_filled_entries": 1,
          "owner": "xiaocao-weekly-deep-review / existing funded research owner",
          "prior_weekly_response": null,
          "sample_unit": "completed independent funded round-trip; open filled entries are reported separately",
          "status": "insufficient_evidence",
          "summary": "no_kol: filled entry 1, open lots 1, model NAV 97414.52; no completed exits, missing 10-28, insufficient comparable evidence."
        },
        {
          "account_id": "open_limit",
          "basis": "observed",
          "comparable": false,
          "completed_exit_samples": 0,
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "effective_samples": 0,
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/research/app_b_forward/performance.json",
              "sha256": "b386fcc24414589fda7a493e0c721dfb7ec4618157670dd0a07ad9fa6488fc3c"
            },
            {
              "path": "output/research/app_b_forward/state.json",
              "sha256": "9d3fab9aa4aacef062fcb5dcd922c4693324ef9b0cb0990c6a685dfd7928449e"
            },
            {
              "path": "output/live/eod_post_business/xiaocao-daily-eod/2026-10-29/research/stdout.log",
              "sha256": "2e3273634bf77def62fb71a2051279f157a9c1e33887ef4a2e56fb57b99dfc82"
            }
          ],
          "falsifier": "同协议可比的原始未来窗口/成交/费用/标记证据形成足够独立样本",
          "first_seen": "2026-10-26",
          "id": "app-b-forward-funded-v1/open_limit",
          "kind": "experiment",
          "last_seen": "2026-10-29",
          "model_authority": 0,
          "next_action": "沿已登记路径观察未来窗口；周度核对有效样本、机会覆盖、费用与可比性，决定继续/修正/停止建议",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "open_filled_entries": 1,
          "owner": "xiaocao-weekly-deep-review / existing funded research owner",
          "prior_weekly_response": null,
          "sample_unit": "completed independent funded round-trip; open filled entries are reported separately",
          "status": "insufficient_evidence",
          "summary": "open_limit: filled entry 1, open lots 1, model NAV 97506.53; no completed exits, missing 10-28, insufficient comparable evidence."
        },
        {
          "acceptance": {
            "deviation": "none established for receipt separation; earlier summary timing repaired separately",
            "expected": "plan/execution/accounting distinct; model authority0; unknown cash/fees remain pending",
            "observed": "三表3/0/0、current BUY UNKNOWN、完整三类blockers；statement绑定同一APP观测。"
          },
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/live/book_b_live_execution/runs/intraday/archive/2026-10-29-eod-20261029T151531410149+0800-3750.json",
              "sha256": "6e197a64ed171c5d85e85db9ce15c6c1ce808263f60a6c1fcf8af2872e6371c0"
            },
            {
              "path": "output/live/book_b_live_execution/accounting_reports/0cae7f97ad6550e4b21af76442ff0ce4c420bdcdad197bf1bbb2211312966a5e.json",
              "sha256": "d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545"
            },
            {
              "path": "output/research/app_b_forward/app_lifecycle.json",
              "sha256": "53c712d13cb6ff7c4034b4bfced233077baf7cbd78576e112a8dfbd5e0ba596c"
            }
          ],
          "falsifier": "任一模型回报被当 APP 成交/利润，或缺费用仍宣称最终结算",
          "first_seen": "2026-10-26",
          "id": "app-b-lifecycle-three-distinct-receipts",
          "kind": "design",
          "last_seen": "2026-10-29",
          "next_action": "每日核对已登记有限验收；周度评价偏离的具体作用、成本及反证，保持 E/COLD/B exit 权限",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "owner": "xiaocao-daily-eod verifies; xiaocao-weekly-deep-review synthesizes",
          "prior_weekly_response": null,
          "status": "observed",
          "summary": "APP原计划/执行/会计分开；EOD有完整快照但当前BUY/预留/34单费用阻塞，模型不替代柜台事实。"
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/audit/morning-automation-review-20261029/repair.md",
              "sha256": "924ed81f44e3518d2c9f2a871d866f9da36598276a974ef444e4a236e6f4a325"
            },
            {
              "path": "output/audit/morning-login-review/final-offline.log",
              "sha256": "d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77"
            },
            {
              "path": "output/audit/morning-login-review/deployment-readback.json",
              "sha256": "df19bfd7d59c96a1f3b347f31bb594fbc6bfb85797e4f4bf5d7c95d1f87a4af6"
            }
          ],
          "falsifier": "仍生成无权限STAR新BUY或错误放宽COLD/原槽位。",
          "first_seen": "2026-10-29",
          "id": "app-b-star-market-permission-filter",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "下一原晨间核对688/689过滤、原合格排序及COLD/资金门。",
          "next_verification": "2026-10-30下一合法原始晨间/EOD/Weekly按各自权限验收",
          "observations": 1,
          "owner": "original morning repair owner / next natural owner",
          "prior_weekly_response": null,
          "production_verification": "pending applicable natural scenario; full EOD native snapshot succeeded",
          "status": "repaired",
          "summary": "primary无科创权限的BUY前置过滤缺失已修复并部署；原UNKNOWN不变，权限补位自然待验。",
          "verification": {
            "code_commit": "c98840a31c09b2aab859bc95b0104fa17b842e96",
            "natural": [],
            "tests": [
              {
                "path": "output/audit/morning-login-review/final-offline.log",
                "sha256": "d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77"
              }
            ]
          }
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/research/eod_audit_20261029/prior-eod-task-trace.json",
              "sha256": "7dc4c32606f710391ab5c23c23591a60a9c3414a04436a8db51ca0dffb524e64"
            },
            {
              "path": "output/research/eod_audit_20261029/task-trace-index.json",
              "sha256": "5537296f9c53d850837b686d48cb20f4a681362d48da8e1cd5a6533ba5a19a80"
            }
          ],
          "falsifier": "找到hash匹配10-28原业务归档，或平台诊断证明具体原因。",
          "first_seen": "2026-10-29",
          "id": "automation-turn-without-first-business-command",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "保留缺跑，核对平台dispatch/模型执行诊断；本日原进程正常终态是恢复事实。",
          "next_verification": "2026-10-30下一合法原始晨间/EOD/Weekly按各自权限验收",
          "observations": 1,
          "owner": "Codex runtime evidence owner; Weekly evidence review",
          "prior_weekly_response": null,
          "production_verification": "today first command and code gate verified; prior cause unknown",
          "status": "open",
          "summary": "10-28原EOD仅调度userMessage、22:34 interrupted，无工具/命令、slot或handoff；原因unknown，不补跑。"
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/live/auto/runs/20261029T011156-9084656d4829/agent_final_daily_stability_soak_verdict.json",
              "sha256": "b9eb8173aef125eead09d70d7d4976fa3d5e5cf835a1a8687390bead9c65d277"
            }
          ],
          "falsifier": "真实原件证明缺日并不存在，或后续连续有效证据满足原5/20门。",
          "first_seen": "2026-10-29",
          "id": "book-t-v2-contiguous-day-gap",
          "kind": "finding",
          "last_seen": "2026-10-29",
          "next_action": "原自然输入继续积累并保留缺日，不以累计天数降低连续门。",
          "next_verification": "2026-10-30下一合法原始晨间/EOD/Weekly按各自权限验收",
          "observations": 1,
          "owner": "original Book T evidence owner / Weekly",
          "prior_weekly_response": null,
          "status": "observed",
          "summary": "自然证据累计7天但缺10-28，contiguous false；daily stability与20日burn-in均pending，rehearsal27排除。"
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/research/eod_weekly_link_20261026/installed-runtime-tests.log",
              "sha256": "88f04a70122f4a994a0bc4004c90e6e7875d828dc4dd0405b8e1c4626406bb07"
            },
            {
              "path": "output/research/eod_audit_20261027/post-closeout-acceptance.json",
              "sha256": "dc74e1e4c931a555d431c6acfd668ec9ce6b1650ca4a22ff92141dc97dbe0bc4"
            }
          ],
          "falsifier": "摘要早于任一必要终态，或本日原件/owner/hash 不一致仍发送",
          "first_seen": "2026-10-26",
          "five_why": [
            "纸面 status 在 APP EOD 前发送，读到的是此前 SQLite 观测。",
            "发送入口位于原 paper shell 的中段。",
            "APP EOD 由 paper 原进程退出后的独立入口执行。",
            "原摘要没有跨 paper/APP/后置命令的统一终态验收。",
            "旧测试覆盖 durable delivery，缺少未完成 APP/后置原命令不得发送的集成场景；新回归已补。"
          ],
          "id": "eod-final-digest-before-app-terminal",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "Weekly沿冻结原件验收；本日最终投递另留独立证明",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "owner": "xiaocao-daily-eod",
          "prevention_test": "test_closeout_blocks_before_record_or_send_on_missing_terminal_or_changed_evidence; test_closeout_post_command_terminal_is_current_owned_and_hash_bound",
          "prior_weekly_response": null,
          "production_verification": "verified_2026-10-27_original_closeout_and_delivery_readback_2026-10-29",
          "status": "verified",
          "summary": "10-27独立收尾证明全部原终态/交接晚于业务、APP-first摘要已投递；本日回读hash通过。",
          "verification": {
            "code_commit": "1a63d714db7def30600b84a25f041e7bb7189f34",
            "natural": [
              {
                "path": "output/research/eod_audit_20261027/post-closeout-acceptance.json",
                "sha256": "dc74e1e4c931a555d431c6acfd668ec9ce6b1650ca4a22ff92141dc97dbe0bc4"
              }
            ],
            "tests": [
              {
                "path": "output/research/eod_weekly_link_20261026/installed-runtime-tests.log",
                "sha256": "88f04a70122f4a994a0bc4004c90e6e7875d828dc4dd0405b8e1c4626406bb07"
              }
            ]
          }
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            }
          ],
          "falsifier": "dated research_run 及下游采用证据证明覆盖、归因与实际改进，不能仅报告数量增长",
          "first_seen": "2026-10-26",
          "id": "eod-learning-backlog-needs-weekly-prioritization",
          "kind": "finding",
          "last_seen": "2026-10-29",
          "next_action": "结合冻结原件集中排一个最高价值验证任务或明确缺证原因；沿既有实验槽和 research_run/§10，不自动调参",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "owner": "xiaocao-weekly-deep-review",
          "prior_weekly_response": null,
          "status": "observed",
          "summary": "309候选/10已测/299未测、posture118天陈旧，大环未闭合；新标签不等于策略改善。"
        },
        {
          "basis": "observed",
          "code_commit": "f22dfb63ca530df99278205b093ea2600115c5fb",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            }
          ],
          "falsifier": "真实原始无动作被拒绝，或缺原每日证据仍静默丢失/关闭未决义务",
          "first_seen": "2026-10-27",
          "id": "eod-research-no-action-terminal",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "沿原自然场景核验；保留代码/测试和生产证明分离，不重跑或补造场景",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 2,
          "owner": "xiaocao-daily-eod / xiaocao-weekly-deep-review",
          "prevention_test": "canonical research no-action terminal acceptance and owner/date/hash refusal cases",
          "prior_weekly_response": null,
          "production_verification": "pending_applicable_natural_scenario",
          "status": "repaired",
          "summary": "f22dfb63已接受exit0 not_started(saved reports)/NON_TRADING_DAY；今日research observed，合法无动作自然路径尚未触发。"
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/live/eod_post_business/xiaocao-daily-eod/2026-10-29/feedback/stdout.log",
              "sha256": "4ca5308bc2953bd78893525945642f3869bbc1fefdefcdb09d1162976db521e9"
            }
          ],
          "falsifier": "同源/决定/独立复核/consumer时钟与hash完整匹配的原件",
          "first_seen": "2026-10-27",
          "id": "kol-source-decision-consumer-links-unknown",
          "kind": "finding",
          "last_seen": "2026-10-29",
          "next_action": "仅由既有语义owner按exact receipt/hash补核适用链接；EOD不重建上下文或发布",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 2,
          "owner": "existing remote KOL writer / next sparse claim owner",
          "prior_weekly_response": null,
          "status": "observed",
          "summary": "feedback仅receipt/hash审计：live334/hash267/unbound281/missing clock67；paper29/hash29/unbound29/missing clock29，执行/利润归因未证。"
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/audit/morning-automation-review-20261029/repair.md",
              "sha256": "924ed81f44e3518d2c9f2a871d866f9da36598276a974ef444e4a236e6f4a325"
            },
            {
              "path": "output/audit/morning-login-review/final-offline.log",
              "sha256": "d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77"
            },
            {
              "path": "output/audit/morning-login-review/deployment-readback.json",
              "sha256": "df19bfd7d59c96a1f3b347f31bb594fbc6bfb85797e4f4bf5d7c95d1f87a4af6"
            }
          ],
          "falsifier": "同一故障在下一自然适用调用复现，或代码错误放宽身份/时效/claim。",
          "first_seen": "2026-10-29",
          "id": "morning-dependency-and-support-observability",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "下一原owner记录冻结阶段耗时、真实dispatch/publish/adoption及同claim通知；EOD完整账户读取本日已通过。",
          "next_verification": "2026-10-30下一合法原始晨间/EOD/Weekly按各自权限验收",
          "observations": 1,
          "owner": "original morning repair owner / next natural owner",
          "prior_weekly_response": null,
          "production_verification": "pending applicable natural scenario; full EOD native snapshot succeeded",
          "status": "repaired",
          "summary": "c98840a3已交付缓存重试/批量取价、KOL交接绑定、通知聚合、独立Paper和原生读取修复；各适用自然场景待证。",
          "verification": {
            "code_commit": "c98840a31c09b2aab859bc95b0104fa17b842e96",
            "natural": [],
            "tests": [
              {
                "path": "output/audit/morning-login-review/final-offline.log",
                "sha256": "d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77"
              }
            ]
          }
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/audit/morning-automation-review-20261029/repair.md",
              "sha256": "924ed81f44e3518d2c9f2a871d866f9da36598276a974ef444e4a236e6f4a325"
            },
            {
              "path": "output/audit/morning-login-review/final-offline.log",
              "sha256": "d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77"
            },
            {
              "path": "output/audit/morning-login-review/deployment-readback.json",
              "sha256": "df19bfd7d59c96a1f3b347f31bb594fbc6bfb85797e4f4bf5d7c95d1f87a4af6"
            }
          ],
          "falsifier": "合格真实夹证被永久拒绝，或缺证仍正常成功/补记买入。",
          "first_seen": "2026-10-29",
          "id": "paper-b-first-minute-high-source-acceptance",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "读取下一原纸面collector边界quote/hash和实际B adoption；不补今日买入。",
          "next_verification": "2026-10-30下一合法原始晨间/EOD/Weekly按各自权限验收",
          "observations": 1,
          "owner": "original morning repair owner / next natural owner",
          "prior_weekly_response": null,
          "production_verification": "pending applicable natural scenario; full EOD native snapshot succeeded",
          "status": "repaired",
          "summary": "原HIGH验证器只有拒绝出口且来源故障误报正常no_buy；接受路径与source_blocked终态已修复部署，未来自然采集/记账待证。",
          "verification": {
            "code_commit": "c98840a31c09b2aab859bc95b0104fa17b842e96",
            "natural": [],
            "tests": [
              {
                "path": "output/audit/morning-login-review/final-offline.log",
                "sha256": "d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77"
              }
            ]
          }
        },
        {
          "basis": "observed",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            },
            {
              "path": "output/research/eod_weekly_link_20261026/installed-runtime-tests.log",
              "sha256": "88f04a70122f4a994a0bc4004c90e6e7875d828dc4dd0405b8e1c4626406bb07"
            }
          ],
          "falsifier": "任一订单进度文件仍触发终态 schema 错误，或孤儿进度被隐藏",
          "first_seen": "2026-10-26",
          "five_why": [
            "本次只读执行 watch 抛 WEEKLY_EXECUTION_CHECKPOINT_INVALID。",
            "glob 同时包含终态与 .orders.json 进度文件。",
            "进度 schema 不含 phase/trade_date。",
            "先前只排除了 .wait.json，未涵盖真实成交等待产生的另一种 sidecar。",
            "测试没有覆盖 .orders.json 及其孤儿终态，现以生产读取接口补齐。"
          ],
          "id": "weekly-orders-sidecar-as-terminal",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "在下次原始 weekly plan 核对全部 closing/eod 及 orders/wait sidecar",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 3,
          "owner": "xiaocao-weekly-deep-review",
          "prevention_test": "test_execution_watch_separates_wait_contract_from_terminal_receipt[.orders.json]",
          "prior_weekly_response": null,
          "production_verification": "pending_original_weekly_plan; current_read_only_watch_9_checkpoints_passed",
          "status": "repaired",
          "summary": "实际 10-26 .orders.json 被当终态导致只读 Weekly inventory 报错；现已按进度文件处理，缺终态仍告警。",
          "verification": {
            "code_commit": "1a63d714db7def30600b84a25f041e7bb7189f34",
            "natural": [],
            "tests": [
              {
                "path": "output/research/eod_weekly_link_20261026/installed-runtime-tests.log",
                "sha256": "88f04a70122f4a994a0bc4004c90e6e7875d828dc4dd0405b8e1c4626406bb07"
              }
            ]
          }
        },
        {
          "basis": "observed",
          "code_commit": "f22dfb63ca530df99278205b093ea2600115c5fb",
          "daily_receipt": {
            "path": "output/live/review_feedback/daily/2026-10-29.json",
            "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
          },
          "evidence_refs": [
            {
              "path": "output/live/daily_execution_review_2026-10-29.md",
              "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067"
            },
            {
              "path": "output/research/eod_audit_20261029/business-audit.json",
              "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35"
            }
          ],
          "falsifier": "真实原始无动作被拒绝，或缺原每日证据仍静默丢失/关闭未决义务",
          "first_seen": "2026-10-27",
          "id": "weekly-unresolved-daily-source-missing",
          "kind": "issue",
          "last_seen": "2026-10-29",
          "next_action": "沿原自然场景核验；保留代码/测试和生产证明分离，不重跑或补造场景",
          "next_verification": "2026-10-30原始Weekly及下一适用合法自然运行；不补造场景",
          "observations": 2,
          "owner": "xiaocao-daily-eod / xiaocao-weekly-deep-review",
          "prevention_test": "source-missing and older-verified/newer-missing regression cases",
          "prior_weekly_response": null,
          "production_verification": "pending_applicable_natural_scenario",
          "status": "repaired",
          "summary": "f22dfb63已修复丢失每日原件时Weekly未决义务丢失、旧verified掩盖较新缺证；今日context无缺件，缺件自然场景未触发。"
        }
      ],
      "receipts": [
        {
          "path": "output/live/review_feedback/daily/2026-10-26.json",
          "sha256": "45c01a81aa41c318d9e938552e6163c88914b83192e0e22c96e9002355ac2216"
        },
        {
          "path": "output/live/review_feedback/daily/2026-10-27.json",
          "sha256": "dc548e9e47f0b8d6954adf6513eb8c7bcafcc007736ce915b6141e7f605f971f"
        },
        {
          "path": "output/live/review_feedback/daily/2026-10-29.json",
          "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1"
        }
      ],
      "schema_version": 1,
      "status": "review_required"
    },
    "exploration_proposals": [
      {
        "auto_apply_eligible": false,
        "experiment_id": "weekly-evidence-2026-10-30-paired-options",
        "falsifier": "费用后改善不能在 OOS 保留，或只由单周/单赢家/缩仓解释",
        "next_review": "2026-11-06",
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
        "experiment_id": "weekly-evidence-2026-10-30-proxy-fill",
        "falsifier": "剔除代理后样本不足或优势消失，则不能称为已确认可执行改善",
        "next_review": "2026-11-06",
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
        "experiment_id": "weekly-evidence-2026-10-30-cashflow-time",
        "falsifier": "无法闭合净投入/净值/费用或缺自然运行时刻，则不认定收益或速度提升",
        "next_review": "2026-11-06",
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
        },
        "hypothesis_id": "A_kp_star",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 84,
          "n_trades": 236,
          "p": 0.203997,
          "per_trade_spread": 0.6398,
          "test_edge": -0.086429,
          "train_edge": 1.353824
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-10-16T15:15:00",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "K->P + auction tiebreak (variant B) beats take-all",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
        },
        "hypothesis_id": "B_vb_star",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 84,
          "n_trades": 236,
          "p": 0.246052,
          "per_trade_spread": 0.605354,
          "test_edge": 0.099805,
          "train_edge": 1.102407
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-10-16T15:15:00",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "出场层非-4602主因:逐笔配对 exit_timing 中性(+0.10%),真漏点=entry追高(+1.2~1.7%/笔)+负选股alpha;-4602 headline是book A/B不配对(book A仅覆盖~6/15+)的伪差",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
        },
        "hypothesis_id": "T_trend_L60_R30_M3",
        "metrics": {
          "compounded_alpha": 0.197323,
          "compounded_base": 50.671284,
          "compounded_strat": 50.868607,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 14.821218,
          "n_holds": 21,
          "non_bull_alpha_mean": 0.162872,
          "non_bull_holds": 14,
          "p": 0.797586,
          "per_hold_alpha_mean": 0.133851,
          "per_hold_win": 0.333333,
          "test_alpha": -7.73931,
          "train_alpha": 6.715885,
          "turnover": 0.634921
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-10-30T15:15:20",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      },
      {
        "claim": "Book T trend config trend_L60_R40_M3 beats average-theme beta under compounded return / drawdown / turnover guards",
        "conclusion": "insufficient_evidence",
        "evidence": {
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
        },
        "hypothesis_id": "T_rotation_L60_R30_M3_W20_K5",
        "metrics": {
          "compounded_alpha": -1.542943,
          "compounded_base": 46.326658,
          "compounded_strat": 44.783715,
          "effective_alpha": 0.008333333333333333,
          "max_drawdown": 16.07246,
          "n_holds": 24,
          "non_bull_alpha_mean": 0.0319,
          "non_bull_holds": 16,
          "p": 0.936407,
          "per_hold_alpha_mean": -0.015742,
          "per_hold_win": 0.375,
          "test_alpha": -4.351271,
          "train_alpha": 2.942531,
          "turnover": 0.402778
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-10-30T15:15:20",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "compounded_alpha_positive",
          "per_hold_alpha_positive",
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
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
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f"
        },
        "hypothesis_id": "E_ai_intelligence_short_factor",
        "metrics": {
          "effective_alpha": 0.0025,
          "n_days": 31,
          "n_trades": 53,
          "p": 0.956231,
          "per_trade_spread": -0.060619,
          "test_edge": -1.319659,
          "train_edge": 0.981345
        },
        "missing_evidence": [
          "immutable_run_and_full_attribution_required"
        ],
        "observed_at": "2026-10-30T15:15:10",
        "recorded_verdict": "REJECTED",
        "rejected_by": [
          "survives_per_trade_equal_weight",
          "walk_forward_consistent",
          "significant"
        ],
        "scope": "historical_verdict_not_this_week"
      }
    ],
    "input_manifest": {
      "eod_feedback_contract": 1,
      "files": [
        {
          "first_date": "2026-06-20",
          "last_date": "2026-10-30",
          "path": "kronos_screen/HYPOTHESES.jsonl",
          "record_count": 43,
          "sha256": "9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f",
          "size_bytes": 29699,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9ad2faf9d2c113669756c11260ec19f15ec353d85022f105e77c38d5f3d0934f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/031aba0867d10d4b8fc89c8ef1f6e43ff7c84ace80ce93ebdace672706ea9b65.json",
          "record_count": 1,
          "sha256": "c26823b677101536b47c2a2cc454c5f4d83806cee3edce1a9ccc894d327f86ab",
          "size_bytes": 12593,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c26823b677101536b47c2a2cc454c5f4d83806cee3edce1a9ccc894d327f86ab",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/0cae7f97ad6550e4b21af76442ff0ce4c420bdcdad197bf1bbb2211312966a5e.json",
          "record_count": 1,
          "sha256": "d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545",
          "size_bytes": 12611,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/11331e61bb9b0d825b7e70c84122e935889523a4c4e294a47fb678c5f1b0d04c.json",
          "record_count": 1,
          "sha256": "40fabc542a25482dc8516d32678679e56c7473c8b00336eb3fd615356dc96f8f",
          "size_bytes": 11475,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/40fabc542a25482dc8516d32678679e56c7473c8b00336eb3fd615356dc96f8f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/11d6809532302a8058c19b61f45652ac7c50d7ee7c58941c3f599e75b5fa8944.json",
          "record_count": 1,
          "sha256": "c576c3bb194a4148f83d9bfe84068140e24696dce3a16cc558f7bda46f2c4f7b",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c576c3bb194a4148f83d9bfe84068140e24696dce3a16cc558f7bda46f2c4f7b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/12a8ecd8fd2c7b21dc89e55b97e8bba49d4061e7cc525fae615650ab0d88c709.json",
          "record_count": 1,
          "sha256": "05aad28a8c54f6d511525d6429c19568112edfd3414e05f91b7acf3c03643758",
          "size_bytes": 10654,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/05aad28a8c54f6d511525d6429c19568112edfd3414e05f91b7acf3c03643758",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/189f1f5f0f67564a9e27214fb7b28800dce60f3cd661e5bab906571e96b01ff1.json",
          "record_count": 1,
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "size_bytes": 1972,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/1c356652b0500fa5e8b6f0bc71ba013a70c9eda8d359d8c4f21b3049bc1d6ae9.json",
          "record_count": 1,
          "sha256": "10b9eb24cb29b0cbba07b563d76eb1d998d5bf4b27b3dd346e76a709c27e8d9d",
          "size_bytes": 11665,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/10b9eb24cb29b0cbba07b563d76eb1d998d5bf4b27b3dd346e76a709c27e8d9d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/1d1864f5b755f1ed207f96e0af7fda45fc41acb182855665215b33fc52b587e8.json",
          "record_count": 1,
          "sha256": "22a52777249e095a3a1c3306a04ce8ae80a9d8be78d275cb16e7a7b92e784a5e",
          "size_bytes": 12430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/22a52777249e095a3a1c3306a04ce8ae80a9d8be78d275cb16e7a7b92e784a5e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/4eaf5f8ded7453a205179f69caff221636c5fa0768e6444f22eb35ddb95f755c.json",
          "record_count": 1,
          "sha256": "741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "size_bytes": 1972,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/741d412b7c82161a54b2450ff7ad1f91d17ff60ec5a6ba045a510a930355115c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/4f05fc9f99271615d18abfae3db79c02c35ae82c73e1104b8c3002b3073816b3.json",
          "record_count": 1,
          "sha256": "fa036a5795e09cbd63d4f1edbda25fe250d4108ed858b354c0a18ef47ec3b700",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fa036a5795e09cbd63d4f1edbda25fe250d4108ed858b354c0a18ef47ec3b700",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/5fdccb94720cb27ec705c46da02f69429616cfe21964e2d3ef23bec01f2cd006.json",
          "record_count": 1,
          "sha256": "59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b",
          "size_bytes": 2013,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/59badbd2d5314c5a81caf1cc2ed5c5f273242e251bd6e8ea1b3414f2b579998b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/67a168e1b12f574245bdd1c67168e6d180be3362c906a32f266004f211516c2b.json",
          "record_count": 1,
          "sha256": "0eb20d33bf944f85747c0a98e78226604b1731ef5282a30c441317c980f1bd62",
          "size_bytes": 2192,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/0eb20d33bf944f85747c0a98e78226604b1731ef5282a30c441317c980f1bd62",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/68ee4b126230e14ff8ea8108454d2c48cd0aeb4730e764d2a485cb505c1c451d.json",
          "record_count": 1,
          "sha256": "fb452d42134a56cc5dd975cb1b47818fbe7e648788072935a68a0ace2534d90c",
          "size_bytes": 12430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fb452d42134a56cc5dd975cb1b47818fbe7e648788072935a68a0ace2534d90c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/6d157cb173b9029ce4d64aa2d4d8e3d6c3be0934dafe45e2066b0c3d7215da6f.json",
          "record_count": 1,
          "sha256": "684934ec6b6cb1172e750536e468c5a9ccd0e3db21da8d38c1211964b33553f9",
          "size_bytes": 10653,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/684934ec6b6cb1172e750536e468c5a9ccd0e3db21da8d38c1211964b33553f9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/6eafa2842aa86eb253533f69921c9250d2c54e686a866d3551893b14ee73442a.json",
          "record_count": 1,
          "sha256": "bab487e32dff3c2339c980fd87df5034a7165f31c21981f8a7043a8d2c616af0",
          "size_bytes": 2241,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/bab487e32dff3c2339c980fd87df5034a7165f31c21981f8a7043a8d2c616af0",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/7be3c693ec969698682eff4853f9a69dbcea56130283c41ea44a7066e0ac759c.json",
          "record_count": 1,
          "sha256": "bb7d77165b7e1c5be0dc15182d64555c0002fff0be084f17aadefe24c3240869",
          "size_bytes": 12430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/bb7d77165b7e1c5be0dc15182d64555c0002fff0be084f17aadefe24c3240869",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/81e7d54e2258fd58ae3d19f7db822a9b4b34c766d14dda522a61efd894678d6d.json",
          "record_count": 1,
          "sha256": "911c17076290583cddea0bd8195d27756db616238035e460462723e7c29ea9bb",
          "size_bytes": 12593,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/911c17076290583cddea0bd8195d27756db616238035e460462723e7c29ea9bb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/8e58602dce0e24050d28f4157476691f5c89b4477d1075bf54d86cd588ac738b.json",
          "record_count": 1,
          "sha256": "2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955",
          "size_bytes": 1939,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/2a55be0cec524224316ab6f75c92cc9ebc6ce12bd583f677f97485c765683955",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/9049d8b69c2efd7c1b784f732c2e14fce068708857b77c136831085b1e6d689e.json",
          "record_count": 1,
          "sha256": "68225c161befdb1eb84f63b937982dbee9c61bea0dbef8edff14f28eee2669af",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/68225c161befdb1eb84f63b937982dbee9c61bea0dbef8edff14f28eee2669af",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/93aef1dfd2aab4d323cc7da9c469dca14ebb4b8198998423cf72fc32f7b7101f.json",
          "record_count": 1,
          "sha256": "6e3076b3f1ccd6823684d2624da1e0b192ce5c7c3a013a8e5aef95110a634753",
          "size_bytes": 1940,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/6e3076b3f1ccd6823684d2624da1e0b192ce5c7c3a013a8e5aef95110a634753",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/a3a2a2b46447f33b1dffbdbbb3f0c195d3804eb22258b018dd54ae7e41af6c02.json",
          "record_count": 1,
          "sha256": "bef91a70ed21a02cb97a3c4356011d41aa8d7d5b65d8f6c7e1091d2ee45aaf42",
          "size_bytes": 2178,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/bef91a70ed21a02cb97a3c4356011d41aa8d7d5b65d8f6c7e1091d2ee45aaf42",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/a79b0a50694bdf081ac8130f67d753be04acb81e7a10312ad3d642eb815ab87b.json",
          "record_count": 1,
          "sha256": "cb8670c6a15a7d7bf65e37cf9d4f991f5cbf6adbc462e9e1e092d24bd0773359",
          "size_bytes": 12593,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/cb8670c6a15a7d7bf65e37cf9d4f991f5cbf6adbc462e9e1e092d24bd0773359",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/c17b2b3981b4fbd47af69ae11c14e817560936a6670a0a156f1e82f6ae409d85.json",
          "record_count": 1,
          "sha256": "8428796ec2d2b4301d8b5a553ab8e33bf21263653e66f55aafffd35a3d605cc7",
          "size_bytes": 2196,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/8428796ec2d2b4301d8b5a553ab8e33bf21263653e66f55aafffd35a3d605cc7",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/c41cf727e4ea97810027c561a03a355118fa2ae5c94a372a4a792e70c8bd5467.json",
          "record_count": 1,
          "sha256": "fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf",
          "size_bytes": 1939,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fb832267cfa64cf7c2b740d9bc1190f917ab3612a9d323b001b3e012c19a3edf",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/c8de32a296b2f3506e04a38dc352771851340c649e4393ab38bace8029792445.json",
          "record_count": 1,
          "sha256": "803b3c25aeda3474fcd2b2585631326529bdac664bf279208ec1322ab8e79390",
          "size_bytes": 2195,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/803b3c25aeda3474fcd2b2585631326529bdac664bf279208ec1322ab8e79390",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/cc642c97ff781a8cced7d00f31530e6c9c263088ff32e509031dfc62a6485be3.json",
          "record_count": 1,
          "sha256": "e2b1733a766cd6cd11b86a2b3289608d14db28f776f5fd69ea8aafec2a4ea6ac",
          "size_bytes": 1938,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/e2b1733a766cd6cd11b86a2b3289608d14db28f776f5fd69ea8aafec2a4ea6ac",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/e71dd52554d41a77b344d5635567bd0bf2825292ae8ccbe5802f4fe4218c0151.json",
          "record_count": 1,
          "sha256": "199328b7f1106fb4a2767794191e1667692c087f7a47410b3f56bf6e6f01e129",
          "size_bytes": 12611,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/199328b7f1106fb4a2767794191e1667692c087f7a47410b3f56bf6e6f01e129",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/e7c5a5678234879cbad0ad4448221c0a59056e9e683c7540cc3337de386fb3f4.json",
          "record_count": 1,
          "sha256": "e7dcf98d44bb888889dc729fb9c39bbc423e00a88d2b877c06d0766ed10a3360",
          "size_bytes": 2239,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/e7dcf98d44bb888889dc729fb9c39bbc423e00a88d2b877c06d0766ed10a3360",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/f17924bf2ab7daeafc441e55e73387816999a3b5e07656831078b601fc63850f.json",
          "record_count": 1,
          "sha256": "7d01fda770c85501b36afac07431a7f2aa32c5a375f40982e84138913de184a6",
          "size_bytes": 11664,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/7d01fda770c85501b36afac07431a7f2aa32c5a375f40982e84138913de184a6",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/accounting_reports/fe0ca031299a04a0af8734a87d9028a03a7981be8b16cb1048f03d9ea06c26dd.json",
          "record_count": 1,
          "sha256": "a8516492ea362e95b9263db8f5d93834676dc805441ddab68e1e4482320337b4",
          "size_bytes": 12430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/a8516492ea362e95b9263db8f5d93834676dc805441ddab68e1e4482320337b4",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/book_b_live_execution/capital_flows.jsonl",
          "record_count": 2,
          "sha256": "8f04393ae00fb62bc5ce4b202cee094a358572f31beafe778d327861e0f5c65e",
          "size_bytes": 1956,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/8f04393ae00fb62bc5ce4b202cee094a358572f31beafe778d327861e0f5c65e",
          "status": "captured"
        },
        {
          "first_date": "2026-06-08",
          "last_date": "2026-06-08",
          "path": "output/live/exit_calibration.jsonl",
          "record_count": 1,
          "sha256": "dde16689d347d08cc3196e8dd9d7c450cc60f9f99f4d7f7ad381a94041df5752",
          "size_bytes": 280,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/dde16689d347d08cc3196e8dd9d7c450cc60f9f99f4d7f7ad381a94041df5752",
          "status": "captured"
        },
        {
          "first_date": "2026-07-03",
          "last_date": "2026-10-23",
          "path": "output/live/flywheel_change_ledger.jsonl",
          "record_count": 17,
          "sha256": "efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64",
          "size_bytes": 172620,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/efe28aeaa131605c5cc76d57b6868f6ffb4928a1a1328c7614d81f055756bb64",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-30",
          "path": "output/live/paper_holdings_snapshots.jsonl",
          "record_count": 919,
          "sha256": "9ffca697653c06ad7000d63c8da3186ed41ecf3c31cc2e2453492b48ae191076",
          "size_bytes": 1134955,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9ffca697653c06ad7000d63c8da3186ed41ecf3c31cc2e2453492b48ae191076",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-30",
          "path": "output/live/paper_trades.jsonl",
          "record_count": 481,
          "sha256": "9c13a72098dd74bf4ba50ffc34929b45f365abe15f14d35a34e726134b1ce7e2",
          "size_bytes": 297898,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9c13a72098dd74bf4ba50ffc34929b45f365abe15f14d35a34e726134b1ce7e2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/pnl_decompose.csv",
          "record_count": null,
          "sha256": "ce5843145650a5191d021b88bc2c743cb6a244c8bd7e2c111eaf8b7d6719c78d",
          "size_bytes": 22185,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ce5843145650a5191d021b88bc2c743cb6a244c8bd7e2c111eaf8b7d6719c78d",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-30",
          "path": "output/live/positions.jsonl",
          "record_count": 243,
          "sha256": "b8ade52abece828745e2cf28ded04ff1b8db57cc83fa9e52c99440c5a311a6d3",
          "size_bytes": 400193,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b8ade52abece828745e2cf28ded04ff1b8db57cc83fa9e52c99440c5a311a6d3",
          "status": "captured"
        },
        {
          "first_date": "2026-10-26",
          "last_date": "2026-10-26",
          "path": "output/live/review_feedback/daily/2026-10-26.json",
          "record_count": 1,
          "sha256": "45c01a81aa41c318d9e938552e6163c88914b83192e0e22c96e9002355ac2216",
          "size_bytes": 18277,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/45c01a81aa41c318d9e938552e6163c88914b83192e0e22c96e9002355ac2216",
          "status": "captured"
        },
        {
          "first_date": "2026-10-27",
          "last_date": "2026-10-27",
          "path": "output/live/review_feedback/daily/2026-10-27.json",
          "record_count": 1,
          "sha256": "dc548e9e47f0b8d6954adf6513eb8c7bcafcc007736ce915b6141e7f605f971f",
          "size_bytes": 48874,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/dc548e9e47f0b8d6954adf6513eb8c7bcafcc007736ce915b6141e7f605f971f",
          "status": "captured"
        },
        {
          "first_date": "2026-10-29",
          "last_date": "2026-10-29",
          "path": "output/live/review_feedback/daily/2026-10-29.json",
          "record_count": 1,
          "sha256": "c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1",
          "size_bytes": 52502,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c05412e861f3def791a535453c31fd857f8f1c9d0a58418e3b62f90e820669f1",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/0f7634bd5413ba03ef9ffef30d4c98d28098f24c36c2d43e8871363596b30fb8",
          "record_count": null,
          "sha256": "0f7634bd5413ba03ef9ffef30d4c98d28098f24c36c2d43e8871363596b30fb8",
          "size_bytes": 54669,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/0f7634bd5413ba03ef9ffef30d4c98d28098f24c36c2d43e8871363596b30fb8",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/102833149fc3e913dfbd6a077f5b11d3c41534c5cef22b773979d920f4cbfa1d",
          "record_count": null,
          "sha256": "102833149fc3e913dfbd6a077f5b11d3c41534c5cef22b773979d920f4cbfa1d",
          "size_bytes": 8502,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/102833149fc3e913dfbd6a077f5b11d3c41534c5cef22b773979d920f4cbfa1d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/14a1443b532de1c8f8c5418a5a8861b48d732ee47390fcf9213fc78cbd021057",
          "record_count": null,
          "sha256": "14a1443b532de1c8f8c5418a5a8861b48d732ee47390fcf9213fc78cbd021057",
          "size_bytes": 17333,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/14a1443b532de1c8f8c5418a5a8861b48d732ee47390fcf9213fc78cbd021057",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/17bdbca794d95eb27743221a68e93bf74338780c645d2a59859e9e1c19bd8eb5",
          "record_count": null,
          "sha256": "17bdbca794d95eb27743221a68e93bf74338780c645d2a59859e9e1c19bd8eb5",
          "size_bytes": 4286,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/17bdbca794d95eb27743221a68e93bf74338780c645d2a59859e9e1c19bd8eb5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/1bc522213d458d3cd667991a17a3b4ecd11e598d19e0f3a9d8f330108572c2d2",
          "record_count": null,
          "sha256": "1bc522213d458d3cd667991a17a3b4ecd11e598d19e0f3a9d8f330108572c2d2",
          "size_bytes": 422,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/1bc522213d458d3cd667991a17a3b4ecd11e598d19e0f3a9d8f330108572c2d2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/21b66aad8b093f3c807c3f14799b81c5445227931c03d4b3aea5f72aad3715c3",
          "record_count": null,
          "sha256": "21b66aad8b093f3c807c3f14799b81c5445227931c03d4b3aea5f72aad3715c3",
          "size_bytes": 876315,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/21b66aad8b093f3c807c3f14799b81c5445227931c03d4b3aea5f72aad3715c3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/274f9592f39966623fa35ea4826b1b510155f2b7651b5e2ba794061532f18973",
          "record_count": null,
          "sha256": "274f9592f39966623fa35ea4826b1b510155f2b7651b5e2ba794061532f18973",
          "size_bytes": 23558,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/274f9592f39966623fa35ea4826b1b510155f2b7651b5e2ba794061532f18973",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/2abf6e69803288fc7d95bc0ad038861023b83bb8731a48f7d7fea5da40fec1a5",
          "record_count": null,
          "sha256": "2abf6e69803288fc7d95bc0ad038861023b83bb8731a48f7d7fea5da40fec1a5",
          "size_bytes": 497,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/2abf6e69803288fc7d95bc0ad038861023b83bb8731a48f7d7fea5da40fec1a5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/2ba7f7b4006b66c4aac6bd747931bf7cd60a9dd0335749df1e64899beec78cae",
          "record_count": null,
          "sha256": "2ba7f7b4006b66c4aac6bd747931bf7cd60a9dd0335749df1e64899beec78cae",
          "size_bytes": 55980,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/2ba7f7b4006b66c4aac6bd747931bf7cd60a9dd0335749df1e64899beec78cae",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/2e3273634bf77def62fb71a2051279f157a9c1e33887ef4a2e56fb57b99dfc82",
          "record_count": null,
          "sha256": "2e3273634bf77def62fb71a2051279f157a9c1e33887ef4a2e56fb57b99dfc82",
          "size_bytes": 430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/2e3273634bf77def62fb71a2051279f157a9c1e33887ef4a2e56fb57b99dfc82",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/3444f8f0f270803ebb9314d9f7c611e67f6f26712128f0ace8e398740dd85ad0",
          "record_count": null,
          "sha256": "3444f8f0f270803ebb9314d9f7c611e67f6f26712128f0ace8e398740dd85ad0",
          "size_bytes": 19391,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/3444f8f0f270803ebb9314d9f7c611e67f6f26712128f0ace8e398740dd85ad0",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/3e44876bf1776fe3a2a1abbedfa54ee6c8f5693ef6b636764fbd202c0931cbf3",
          "record_count": null,
          "sha256": "3e44876bf1776fe3a2a1abbedfa54ee6c8f5693ef6b636764fbd202c0931cbf3",
          "size_bytes": 430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/3e44876bf1776fe3a2a1abbedfa54ee6c8f5693ef6b636764fbd202c0931cbf3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/3e6351535fe0c2c75efd5024534fee34e2a5d9f73f817ff91af14915992eccbb",
          "record_count": null,
          "sha256": "3e6351535fe0c2c75efd5024534fee34e2a5d9f73f817ff91af14915992eccbb",
          "size_bytes": 341,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/3e6351535fe0c2c75efd5024534fee34e2a5d9f73f817ff91af14915992eccbb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/41a1f2054a9cbcdd4fc8d2df75f7a105d36ffb6f85c6a7b24974d015a7aee462",
          "record_count": null,
          "sha256": "41a1f2054a9cbcdd4fc8d2df75f7a105d36ffb6f85c6a7b24974d015a7aee462",
          "size_bytes": 15445,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/41a1f2054a9cbcdd4fc8d2df75f7a105d36ffb6f85c6a7b24974d015a7aee462",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/43214562b0e358c7d8096381062f06c4b7096d6eee3507f68f61489f26722be8",
          "record_count": null,
          "sha256": "43214562b0e358c7d8096381062f06c4b7096d6eee3507f68f61489f26722be8",
          "size_bytes": 1992,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/43214562b0e358c7d8096381062f06c4b7096d6eee3507f68f61489f26722be8",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/4a32e65158f264211a1eda922fab3d0f1bd351d1d5f5240f6de73e1089597196",
          "record_count": null,
          "sha256": "4a32e65158f264211a1eda922fab3d0f1bd351d1d5f5240f6de73e1089597196",
          "size_bytes": 74192,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4a32e65158f264211a1eda922fab3d0f1bd351d1d5f5240f6de73e1089597196",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/4ca5308bc2953bd78893525945642f3869bbc1fefdefcdb09d1162976db521e9",
          "record_count": null,
          "sha256": "4ca5308bc2953bd78893525945642f3869bbc1fefdefcdb09d1162976db521e9",
          "size_bytes": 3576,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4ca5308bc2953bd78893525945642f3869bbc1fefdefcdb09d1162976db521e9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/4d3a9f4ba64b7a0463a67c957f70acad6b9270d88fdea4d923e236376db0bcc2",
          "record_count": null,
          "sha256": "4d3a9f4ba64b7a0463a67c957f70acad6b9270d88fdea4d923e236376db0bcc2",
          "size_bytes": 3404,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4d3a9f4ba64b7a0463a67c957f70acad6b9270d88fdea4d923e236376db0bcc2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067",
          "record_count": null,
          "sha256": "4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067",
          "size_bytes": 11690,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4f3a1531459556a844281d8d40bc07e1c99e8fc2040b31f9671b79d0f32d0067",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/538fdfd76adeaa6030a7ac288f56736626c8c7a319137a866856a041db959a4b",
          "record_count": null,
          "sha256": "538fdfd76adeaa6030a7ac288f56736626c8c7a319137a866856a041db959a4b",
          "size_bytes": 10537,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/538fdfd76adeaa6030a7ac288f56736626c8c7a319137a866856a041db959a4b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/53c712d13cb6ff7c4034b4bfced233077baf7cbd78576e112a8dfbd5e0ba596c",
          "record_count": null,
          "sha256": "53c712d13cb6ff7c4034b4bfced233077baf7cbd78576e112a8dfbd5e0ba596c",
          "size_bytes": 123789,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/53c712d13cb6ff7c4034b4bfced233077baf7cbd78576e112a8dfbd5e0ba596c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/55179e25f960e29386ca4ab8538f80193a4b49a12d3e7a8eeabd41d008407bb9",
          "record_count": null,
          "sha256": "55179e25f960e29386ca4ab8538f80193a4b49a12d3e7a8eeabd41d008407bb9",
          "size_bytes": 4278,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/55179e25f960e29386ca4ab8538f80193a4b49a12d3e7a8eeabd41d008407bb9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/5537296f9c53d850837b686d48cb20f4a681362d48da8e1cd5a6533ba5a19a80",
          "record_count": null,
          "sha256": "5537296f9c53d850837b686d48cb20f4a681362d48da8e1cd5a6533ba5a19a80",
          "size_bytes": 41060,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/5537296f9c53d850837b686d48cb20f4a681362d48da8e1cd5a6533ba5a19a80",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/6709474a2417160e5185aa8ddebfe9e7204c3b57ec619a82363e6412ace86b60",
          "record_count": null,
          "sha256": "6709474a2417160e5185aa8ddebfe9e7204c3b57ec619a82363e6412ace86b60",
          "size_bytes": 669,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/6709474a2417160e5185aa8ddebfe9e7204c3b57ec619a82363e6412ace86b60",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/6773428680ac8190f20099917176e82b3ab11a12b664db3601dc88f38db95e6c",
          "record_count": null,
          "sha256": "6773428680ac8190f20099917176e82b3ab11a12b664db3601dc88f38db95e6c",
          "size_bytes": 670,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/6773428680ac8190f20099917176e82b3ab11a12b664db3601dc88f38db95e6c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/6d3fad618d76a68e0bc156ed9a21edd0bbd6191c68c6b348e0d18c87574e68ff",
          "record_count": null,
          "sha256": "6d3fad618d76a68e0bc156ed9a21edd0bbd6191c68c6b348e0d18c87574e68ff",
          "size_bytes": 10278,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/6d3fad618d76a68e0bc156ed9a21edd0bbd6191c68c6b348e0d18c87574e68ff",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/6e197a64ed171c5d85e85db9ce15c6c1ce808263f60a6c1fcf8af2872e6371c0",
          "record_count": null,
          "sha256": "6e197a64ed171c5d85e85db9ce15c6c1ce808263f60a6c1fcf8af2872e6371c0",
          "size_bytes": 18031,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/6e197a64ed171c5d85e85db9ce15c6c1ce808263f60a6c1fcf8af2872e6371c0",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/723bd8fe61392d937dc972dba78fa3642adc2ff0b10b7467782fef0dc44bf498",
          "record_count": null,
          "sha256": "723bd8fe61392d937dc972dba78fa3642adc2ff0b10b7467782fef0dc44bf498",
          "size_bytes": 12016,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/723bd8fe61392d937dc972dba78fa3642adc2ff0b10b7467782fef0dc44bf498",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/780b81f47be8e7945efcc73d2a23712a4fa716efea376ceb94b702d2d8a07e66",
          "record_count": null,
          "sha256": "780b81f47be8e7945efcc73d2a23712a4fa716efea376ceb94b702d2d8a07e66",
          "size_bytes": 35980,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/780b81f47be8e7945efcc73d2a23712a4fa716efea376ceb94b702d2d8a07e66",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/79113426b8e5f467573c9b381eaf77dca87b6c3725227475655d58e1918f146f",
          "record_count": null,
          "sha256": "79113426b8e5f467573c9b381eaf77dca87b6c3725227475655d58e1918f146f",
          "size_bytes": 645,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/79113426b8e5f467573c9b381eaf77dca87b6c3725227475655d58e1918f146f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/7dc4c32606f710391ab5c23c23591a60a9c3414a04436a8db51ca0dffb524e64",
          "record_count": null,
          "sha256": "7dc4c32606f710391ab5c23c23591a60a9c3414a04436a8db51ca0dffb524e64",
          "size_bytes": 30692,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/7dc4c32606f710391ab5c23c23591a60a9c3414a04436a8db51ca0dffb524e64",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/82cd2a25b35dd04f88062cbdad0a976ea63f522a07b6328fbc7f8c309b96664c",
          "record_count": null,
          "sha256": "82cd2a25b35dd04f88062cbdad0a976ea63f522a07b6328fbc7f8c309b96664c",
          "size_bytes": 23517,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/82cd2a25b35dd04f88062cbdad0a976ea63f522a07b6328fbc7f8c309b96664c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/8541f8fdee638fe5ed1c8be00892153456adb6cbbd24db887ffbe9f8802a1102",
          "record_count": null,
          "sha256": "8541f8fdee638fe5ed1c8be00892153456adb6cbbd24db887ffbe9f8802a1102",
          "size_bytes": 109732,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/8541f8fdee638fe5ed1c8be00892153456adb6cbbd24db887ffbe9f8802a1102",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/88f04a70122f4a994a0bc4004c90e6e7875d828dc4dd0405b8e1c4626406bb07",
          "record_count": null,
          "sha256": "88f04a70122f4a994a0bc4004c90e6e7875d828dc4dd0405b8e1c4626406bb07",
          "size_bytes": 261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/88f04a70122f4a994a0bc4004c90e6e7875d828dc4dd0405b8e1c4626406bb07",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/8a2e3bc0d2f3dada37659a4e12a07cd7566c14d242d6445964b8f89730e520cd",
          "record_count": null,
          "sha256": "8a2e3bc0d2f3dada37659a4e12a07cd7566c14d242d6445964b8f89730e520cd",
          "size_bytes": 669,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/8a2e3bc0d2f3dada37659a4e12a07cd7566c14d242d6445964b8f89730e520cd",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/911c17076290583cddea0bd8195d27756db616238035e460462723e7c29ea9bb",
          "record_count": null,
          "sha256": "911c17076290583cddea0bd8195d27756db616238035e460462723e7c29ea9bb",
          "size_bytes": 12593,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/911c17076290583cddea0bd8195d27756db616238035e460462723e7c29ea9bb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/924ed81f44e3518d2c9f2a871d866f9da36598276a974ef444e4a236e6f4a325",
          "record_count": null,
          "sha256": "924ed81f44e3518d2c9f2a871d866f9da36598276a974ef444e4a236e6f4a325",
          "size_bytes": 4429,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/924ed81f44e3518d2c9f2a871d866f9da36598276a974ef444e4a236e6f4a325",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/9d3fab9aa4aacef062fcb5dcd922c4693324ef9b0cb0990c6a685dfd7928449e",
          "record_count": null,
          "sha256": "9d3fab9aa4aacef062fcb5dcd922c4693324ef9b0cb0990c6a685dfd7928449e",
          "size_bytes": 1466499,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9d3fab9aa4aacef062fcb5dcd922c4693324ef9b0cb0990c6a685dfd7928449e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/a0a8e0ccd7f81ed4e0ef36d8bda1a275e5159015a2a8302c71e912a380b0f7a7",
          "record_count": null,
          "sha256": "a0a8e0ccd7f81ed4e0ef36d8bda1a275e5159015a2a8302c71e912a380b0f7a7",
          "size_bytes": 677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/a0a8e0ccd7f81ed4e0ef36d8bda1a275e5159015a2a8302c71e912a380b0f7a7",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35",
          "record_count": null,
          "sha256": "a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35",
          "size_bytes": 520061,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/a41a35d949d662db3f0449f473eb5aa707c62f0b800851061564e118b1ca8f35",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/ab14772c595c5cb777979172e8a7edacb9dedc6956447aeb78c517d99b9e5749",
          "record_count": null,
          "sha256": "ab14772c595c5cb777979172e8a7edacb9dedc6956447aeb78c517d99b9e5749",
          "size_bytes": 20978,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ab14772c595c5cb777979172e8a7edacb9dedc6956447aeb78c517d99b9e5749",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/ad13f881e8005439102c3e77f62f8bc89de48b93214273bb7e613f475a41e21d",
          "record_count": null,
          "sha256": "ad13f881e8005439102c3e77f62f8bc89de48b93214273bb7e613f475a41e21d",
          "size_bytes": 759,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ad13f881e8005439102c3e77f62f8bc89de48b93214273bb7e613f475a41e21d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/b386fcc24414589fda7a493e0c721dfb7ec4618157670dd0a07ad9fa6488fc3c",
          "record_count": null,
          "sha256": "b386fcc24414589fda7a493e0c721dfb7ec4618157670dd0a07ad9fa6488fc3c",
          "size_bytes": 24945,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b386fcc24414589fda7a493e0c721dfb7ec4618157670dd0a07ad9fa6488fc3c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/b8c86a01b460b5c44dd80c18a6023ce996503ee4ac9b0c80bbe0ceb059e2da62",
          "record_count": null,
          "sha256": "b8c86a01b460b5c44dd80c18a6023ce996503ee4ac9b0c80bbe0ceb059e2da62",
          "size_bytes": 7509,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b8c86a01b460b5c44dd80c18a6023ce996503ee4ac9b0c80bbe0ceb059e2da62",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/b9eb8173aef125eead09d70d7d4976fa3d5e5cf835a1a8687390bead9c65d277",
          "record_count": null,
          "sha256": "b9eb8173aef125eead09d70d7d4976fa3d5e5cf835a1a8687390bead9c65d277",
          "size_bytes": 547,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b9eb8173aef125eead09d70d7d4976fa3d5e5cf835a1a8687390bead9c65d277",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/bbc115e157d22f5b3a15dbb25dfb8f7930699e5346418007b980b440b627b48e",
          "record_count": null,
          "sha256": "bbc115e157d22f5b3a15dbb25dfb8f7930699e5346418007b980b440b627b48e",
          "size_bytes": 670,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/bbc115e157d22f5b3a15dbb25dfb8f7930699e5346418007b980b440b627b48e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/bbff613a410fd9b283b5dd5882a2cfdc8a5c812f7bc019d3557add31bc0d67dc",
          "record_count": null,
          "sha256": "bbff613a410fd9b283b5dd5882a2cfdc8a5c812f7bc019d3557add31bc0d67dc",
          "size_bytes": 48039,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/bbff613a410fd9b283b5dd5882a2cfdc8a5c812f7bc019d3557add31bc0d67dc",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/bcccb5bcf312d42235b66f7df5dfcf08efc9dd68a9966b60419ec7c1baaf5528",
          "record_count": null,
          "sha256": "bcccb5bcf312d42235b66f7df5dfcf08efc9dd68a9966b60419ec7c1baaf5528",
          "size_bytes": 68915,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/bcccb5bcf312d42235b66f7df5dfcf08efc9dd68a9966b60419ec7c1baaf5528",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/c84fbf6a7efb55c71c36d073de17e829d6d630f262e626f5f8293f00f7459b81",
          "record_count": null,
          "sha256": "c84fbf6a7efb55c71c36d073de17e829d6d630f262e626f5f8293f00f7459b81",
          "size_bytes": 341,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c84fbf6a7efb55c71c36d073de17e829d6d630f262e626f5f8293f00f7459b81",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/cb8670c6a15a7d7bf65e37cf9d4f991f5cbf6adbc462e9e1e092d24bd0773359",
          "record_count": null,
          "sha256": "cb8670c6a15a7d7bf65e37cf9d4f991f5cbf6adbc462e9e1e092d24bd0773359",
          "size_bytes": 12593,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/cb8670c6a15a7d7bf65e37cf9d4f991f5cbf6adbc462e9e1e092d24bd0773359",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77",
          "record_count": null,
          "sha256": "d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77",
          "size_bytes": 7396,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d1f69790b561881a0eb9aace328ebcf886980e3a3b9b8400a4faa9e970b97e77",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545",
          "record_count": null,
          "sha256": "d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545",
          "size_bytes": 12611,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d244a9c51f31266f9ab7ce0607ed51dd412ef22d279f481eafe041d4a8694545",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/d2e7367f46fd9c874e11eac7c1229d3b3b1116cb3a6d1083b5e9d7024acd9ba6",
          "record_count": null,
          "sha256": "d2e7367f46fd9c874e11eac7c1229d3b3b1116cb3a6d1083b5e9d7024acd9ba6",
          "size_bytes": 797,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d2e7367f46fd9c874e11eac7c1229d3b3b1116cb3a6d1083b5e9d7024acd9ba6",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/d89c75cf77de603ab5ab0d071a2204e3b0ab90728dec12f64c1399cd12d7da6f",
          "record_count": null,
          "sha256": "d89c75cf77de603ab5ab0d071a2204e3b0ab90728dec12f64c1399cd12d7da6f",
          "size_bytes": 56206,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d89c75cf77de603ab5ab0d071a2204e3b0ab90728dec12f64c1399cd12d7da6f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/da6ddb1c60b4c165fac7adf44a1547a5abde78916e75535416095bcb7a6176aa",
          "record_count": null,
          "sha256": "da6ddb1c60b4c165fac7adf44a1547a5abde78916e75535416095bcb7a6176aa",
          "size_bytes": 19179,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/da6ddb1c60b4c165fac7adf44a1547a5abde78916e75535416095bcb7a6176aa",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/db8095132f6fb442e4a0f449a8b242180ca390cb6973a111e748606737ffc30f",
          "record_count": null,
          "sha256": "db8095132f6fb442e4a0f449a8b242180ca390cb6973a111e748606737ffc30f",
          "size_bytes": 43382,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/db8095132f6fb442e4a0f449a8b242180ca390cb6973a111e748606737ffc30f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/dc74e1e4c931a555d431c6acfd668ec9ce6b1650ca4a22ff92141dc97dbe0bc4",
          "record_count": null,
          "sha256": "dc74e1e4c931a555d431c6acfd668ec9ce6b1650ca4a22ff92141dc97dbe0bc4",
          "size_bytes": 2861,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/dc74e1e4c931a555d431c6acfd668ec9ce6b1650ca4a22ff92141dc97dbe0bc4",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/dc90b048512e5fe23e1d9a9fe8060b6333cd565f07c4dec3667742c1fd036fb9",
          "record_count": null,
          "sha256": "dc90b048512e5fe23e1d9a9fe8060b6333cd565f07c4dec3667742c1fd036fb9",
          "size_bytes": 17599,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/dc90b048512e5fe23e1d9a9fe8060b6333cd565f07c4dec3667742c1fd036fb9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/df19bfd7d59c96a1f3b347f31bb594fbc6bfb85797e4f4bf5d7c95d1f87a4af6",
          "record_count": null,
          "sha256": "df19bfd7d59c96a1f3b347f31bb594fbc6bfb85797e4f4bf5d7c95d1f87a4af6",
          "size_bytes": 1729,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/df19bfd7d59c96a1f3b347f31bb594fbc6bfb85797e4f4bf5d7c95d1f87a4af6",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/e4066c0bd80961a150b528e6bea4e166d96c80ff2cfeadaba3b270394e37f81d",
          "record_count": null,
          "sha256": "e4066c0bd80961a150b528e6bea4e166d96c80ff2cfeadaba3b270394e37f81d",
          "size_bytes": 68915,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/e4066c0bd80961a150b528e6bea4e166d96c80ff2cfeadaba3b270394e37f81d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/ebdf1cabed987faa9c02bc79fe27948ff28b1169f8ed252860ae40cfe4f0ce87",
          "record_count": null,
          "sha256": "ebdf1cabed987faa9c02bc79fe27948ff28b1169f8ed252860ae40cfe4f0ce87",
          "size_bytes": 13966,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ebdf1cabed987faa9c02bc79fe27948ff28b1169f8ed252860ae40cfe4f0ce87",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/ebe07a716a20a031ffc520e5ed6504330fa01d3ef1831d62143933a2b0679859",
          "record_count": null,
          "sha256": "ebe07a716a20a031ffc520e5ed6504330fa01d3ef1831d62143933a2b0679859",
          "size_bytes": 72074,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ebe07a716a20a031ffc520e5ed6504330fa01d3ef1831d62143933a2b0679859",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/ee05d20c49b87880a7ba5a8c4336d7a2dd79538b7745c2978b591abf4b36e133",
          "record_count": null,
          "sha256": "ee05d20c49b87880a7ba5a8c4336d7a2dd79538b7745c2978b591abf4b36e133",
          "size_bytes": 3775,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ee05d20c49b87880a7ba5a8c4336d7a2dd79538b7745c2978b591abf4b36e133",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/ee2f41d05bf52924dc18a013189ac43e8fb57b4982802ef3257def9e56d94dfb",
          "record_count": null,
          "sha256": "ee2f41d05bf52924dc18a013189ac43e8fb57b4982802ef3257def9e56d94dfb",
          "size_bytes": 3464,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ee2f41d05bf52924dc18a013189ac43e8fb57b4982802ef3257def9e56d94dfb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/f475631ed9f38eba1067c1bc2f897ff80f9ac244f1efee9647df5f3fbe03b7bb",
          "record_count": null,
          "sha256": "f475631ed9f38eba1067c1bc2f897ff80f9ac244f1efee9647df5f3fbe03b7bb",
          "size_bytes": 677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/f475631ed9f38eba1067c1bc2f897ff80f9ac244f1efee9647df5f3fbe03b7bb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/f7aa4c6c8a18c30e5962e497e8404edbc1c0b0f1eb88c92303ac2ffce788d510",
          "record_count": null,
          "sha256": "f7aa4c6c8a18c30e5962e497e8404edbc1c0b0f1eb88c92303ac2ffce788d510",
          "size_bytes": 2674,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/f7aa4c6c8a18c30e5962e497e8404edbc1c0b0f1eb88c92303ac2ffce788d510",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/live/review_feedback/evidence/fc646bcb94c78c74855bbd68dd8445b558f8e080e1d916f12ed62dfa63086ee0",
          "record_count": null,
          "sha256": "fc646bcb94c78c74855bbd68dd8445b558f8e080e1d916f12ed62dfa63086ee0",
          "size_bytes": 430,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fc646bcb94c78c74855bbd68dd8445b558f8e080e1d916f12ed62dfa63086ee0",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-30",
          "path": "output/live/signal_snapshots.jsonl",
          "record_count": 1080,
          "sha256": "80a6732972344a635f42601737aba444874c0f2cf9670f37a1de073714bca902",
          "size_bytes": 4789778,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/80a6732972344a635f42601737aba444874c0f2cf9670f37a1de073714bca902",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/app_b_forward/app_lifecycle.json",
          "record_count": 1,
          "sha256": "71bcbd1a7bb698bbe27d1f7496a1b19352d06d1d5df9a6932eec8e8e6971e6f4",
          "size_bytes": 123789,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/71bcbd1a7bb698bbe27d1f7496a1b19352d06d1d5df9a6932eec8e8e6971e6f4",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/app_b_forward/performance.json",
          "record_count": 1,
          "sha256": "e7928be7adb3e6516decb53fa52cead8f6701c275db13ace2a2591e09e5b3d7e",
          "size_bytes": 29930,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/e7928be7adb3e6516decb53fa52cead8f6701c275db13ace2a2591e09e5b3d7e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/app_b_forward/protocol.json",
          "record_count": 1,
          "sha256": "79113426b8e5f467573c9b381eaf77dca87b6c3725227475655d58e1918f146f",
          "size_bytes": 645,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/79113426b8e5f467573c9b381eaf77dca87b6c3725227475655d58e1918f146f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-06-30.md",
          "record_count": null,
          "sha256": "d66495a808d06d9371daa6287838dba3f0af165c10a8638a1d59c612cde2581d",
          "size_bytes": 1552,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d66495a808d06d9371daa6287838dba3f0af165c10a8638a1d59c612cde2581d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-01.md",
          "record_count": null,
          "sha256": "76377baf3480cd9615e67e6260571418cf9247dc54b0960d5047bb2dfd9de9e9",
          "size_bytes": 1568,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/76377baf3480cd9615e67e6260571418cf9247dc54b0960d5047bb2dfd9de9e9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-02.md",
          "record_count": null,
          "sha256": "62c8ecff2e5ae8a5105609809a5b8d3601871c12cb0dc6366338b2b8c7eb7baa",
          "size_bytes": 1614,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/62c8ecff2e5ae8a5105609809a5b8d3601871c12cb0dc6366338b2b8c7eb7baa",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-03.md",
          "record_count": null,
          "sha256": "8b7fd10f1634b4d5051ba707e6af2e43945caf33e4df326bdfaa4a5f02ed1f39",
          "size_bytes": 1596,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/8b7fd10f1634b4d5051ba707e6af2e43945caf33e4df326bdfaa4a5f02ed1f39",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-06.md",
          "record_count": null,
          "sha256": "3eb2487514a15f0a342f3fc765af57f8ed76a12cf87215e68765c50a36892535",
          "size_bytes": 1657,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/3eb2487514a15f0a342f3fc765af57f8ed76a12cf87215e68765c50a36892535",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-07.md",
          "record_count": null,
          "sha256": "4703555ba1d1feb2cc352471ec20b9e05a476a7936bfa04574c02e14a89cc0f3",
          "size_bytes": 1659,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4703555ba1d1feb2cc352471ec20b9e05a476a7936bfa04574c02e14a89cc0f3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-08.md",
          "record_count": null,
          "sha256": "3051c61877741e55750cb64a5e2b7ad3dd9484bae16e8bf3b95732143a3811df",
          "size_bytes": 1659,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/3051c61877741e55750cb64a5e2b7ad3dd9484bae16e8bf3b95732143a3811df",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-09.md",
          "record_count": null,
          "sha256": "421025f3d2671c0474f92c901e40c8fd06e08ce7dbdd575d2366f64fdcd812d8",
          "size_bytes": 1664,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/421025f3d2671c0474f92c901e40c8fd06e08ce7dbdd575d2366f64fdcd812d8",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-10.md",
          "record_count": null,
          "sha256": "e3d03874c764b96a280a787198db36b9e3e6b6121bc300d3ebc646cfe420977c",
          "size_bytes": 1665,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/e3d03874c764b96a280a787198db36b9e3e6b6121bc300d3ebc646cfe420977c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-13.md",
          "record_count": null,
          "sha256": "538ced43d020a0f4f15a001c7b02c53197e266d9e4198d69c7a36a99a740b912",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/538ced43d020a0f4f15a001c7b02c53197e266d9e4198d69c7a36a99a740b912",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-14.md",
          "record_count": null,
          "sha256": "bb90bce70c12c7c856b678a7d348e8873a069a8d01bbf23f78b55e03e1aba3e0",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/bb90bce70c12c7c856b678a7d348e8873a069a8d01bbf23f78b55e03e1aba3e0",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-15.md",
          "record_count": null,
          "sha256": "c550da9aa03924d953236ff4bede78eb6deaf513acee7b1a8f45f7cf0bcff321",
          "size_bytes": 1677,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c550da9aa03924d953236ff4bede78eb6deaf513acee7b1a8f45f7cf0bcff321",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-16.md",
          "record_count": null,
          "sha256": "07051d8db157280a82ef0503d5371f40ea13af11f9b184b45c5f84e78edd1b9b",
          "size_bytes": 1679,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/07051d8db157280a82ef0503d5371f40ea13af11f9b184b45c5f84e78edd1b9b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-17.md",
          "record_count": null,
          "sha256": "b8a8a7b5fd7347609c36e1a391fc8436ead0109413d4fcc6f89335e2263209ff",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b8a8a7b5fd7347609c36e1a391fc8436ead0109413d4fcc6f89335e2263209ff",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-20.md",
          "record_count": null,
          "sha256": "4ac67aaf14c874122ef6ff4e39c824a257d6e0d020e147ca13ce435941278c0e",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4ac67aaf14c874122ef6ff4e39c824a257d6e0d020e147ca13ce435941278c0e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-21.md",
          "record_count": null,
          "sha256": "4da8cefa13f79332520f76ef1c5e6327461fb6d1688bcc4c570f3b3716b7c3fc",
          "size_bytes": 1688,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4da8cefa13f79332520f76ef1c5e6327461fb6d1688bcc4c570f3b3716b7c3fc",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-22.md",
          "record_count": null,
          "sha256": "c62603355e0b8b6c81f052efb1f046653e5d510cfd5a4433df7693d800a44a3d",
          "size_bytes": 1739,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c62603355e0b8b6c81f052efb1f046653e5d510cfd5a4433df7693d800a44a3d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-23.md",
          "record_count": null,
          "sha256": "2866883e99c0cb09ce15a8faa7c9e2033e62f39eac4ea1e0dfe65b45185ea22f",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/2866883e99c0cb09ce15a8faa7c9e2033e62f39eac4ea1e0dfe65b45185ea22f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-24.md",
          "record_count": null,
          "sha256": "7749911678871915752439e978e352fd3b98839b688edee103bcc9bd7f0799df",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/7749911678871915752439e978e352fd3b98839b688edee103bcc9bd7f0799df",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-27.md",
          "record_count": null,
          "sha256": "b45de707bceb56128e29d06aed080e6171e2bb30021d3bb7af753f967a1b9c01",
          "size_bytes": 1736,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b45de707bceb56128e29d06aed080e6171e2bb30021d3bb7af753f967a1b9c01",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-07-28.md",
          "record_count": null,
          "sha256": "9e5aa5387abc464a2580cd1fbfc4fbb1aefb82b218346017dcfcb58388a97958",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9e5aa5387abc464a2580cd1fbfc4fbb1aefb82b218346017dcfcb58388a97958",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-03.md",
          "record_count": null,
          "sha256": "9adbe52713711ccb666619155fe2aa13ddc6e41df810009a1044a1ddcb89bc53",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9adbe52713711ccb666619155fe2aa13ddc6e41df810009a1044a1ddcb89bc53",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-04.md",
          "record_count": null,
          "sha256": "7d2ab40b988a0b312d10f40e1ea0077e40f4c8b0a4f20ca2910ad47f88d27e93",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/7d2ab40b988a0b312d10f40e1ea0077e40f4c8b0a4f20ca2910ad47f88d27e93",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-05.md",
          "record_count": null,
          "sha256": "8521076f2100e1b245fcf8d9357d714189ae0674bf64799255d3fbc4f4868c5b",
          "size_bytes": 1735,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/8521076f2100e1b245fcf8d9357d714189ae0674bf64799255d3fbc4f4868c5b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-06.md",
          "record_count": null,
          "sha256": "b29ce0f1708a8e129abf56a6fb5b609bc0c86e2a92c783df44de0431dc5cc23e",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b29ce0f1708a8e129abf56a6fb5b609bc0c86e2a92c783df44de0431dc5cc23e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-07.md",
          "record_count": null,
          "sha256": "ca9f909330795b6ef3b26ee23401dcb91f765bc7116c1c1c4b8c15dbe164f819",
          "size_bytes": 1736,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ca9f909330795b6ef3b26ee23401dcb91f765bc7116c1c1c4b8c15dbe164f819",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-10.md",
          "record_count": null,
          "sha256": "d3552e00c3426d4779bc070975fa057b483add73b711f8f148c06265c0da13f4",
          "size_bytes": 1734,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d3552e00c3426d4779bc070975fa057b483add73b711f8f148c06265c0da13f4",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-11.md",
          "record_count": null,
          "sha256": "9d4dde9cbc13f56d74a031f88f4e32c3f04bcde74467bcf2cc0b9113ee028954",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9d4dde9cbc13f56d74a031f88f4e32c3f04bcde74467bcf2cc0b9113ee028954",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-12.md",
          "record_count": null,
          "sha256": "4e127d3e802b60465f31ca597fd6d36cef2d3a110df76eed26d5bf18a4c2d898",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4e127d3e802b60465f31ca597fd6d36cef2d3a110df76eed26d5bf18a4c2d898",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-13.md",
          "record_count": null,
          "sha256": "785f1fd8a42083c24e15569f8d649bbc863c2c79ed502063bfa84fb92c8bb314",
          "size_bytes": 1733,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/785f1fd8a42083c24e15569f8d649bbc863c2c79ed502063bfa84fb92c8bb314",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-14.md",
          "record_count": null,
          "sha256": "41bfd6060c4f806377bfef8564f5487791644b659f053ea59bb66d1f164a1c0d",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/41bfd6060c4f806377bfef8564f5487791644b659f053ea59bb66d1f164a1c0d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-17.md",
          "record_count": null,
          "sha256": "a00c328cbf60a8f2f7a67623d4f81b042c5173220eadc9088ee781c5b1dada9e",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/a00c328cbf60a8f2f7a67623d4f81b042c5173220eadc9088ee781c5b1dada9e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-18.md",
          "record_count": null,
          "sha256": "fa09c513b7ad5606602270053cc80955d596db6ef18d5f867375b1ebb74c8c14",
          "size_bytes": 1735,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fa09c513b7ad5606602270053cc80955d596db6ef18d5f867375b1ebb74c8c14",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-19.md",
          "record_count": null,
          "sha256": "d761791ad07a44e1ee8a56552eadd3891bd46fb43d2a3c05c54bc0537ec22c57",
          "size_bytes": 1740,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d761791ad07a44e1ee8a56552eadd3891bd46fb43d2a3c05c54bc0537ec22c57",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-20.md",
          "record_count": null,
          "sha256": "83b3ac332aceb925c6070f86112ec846b588a2bba476077fd3c38eabd80c7d39",
          "size_bytes": 1738,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/83b3ac332aceb925c6070f86112ec846b588a2bba476077fd3c38eabd80c7d39",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-21.md",
          "record_count": null,
          "sha256": "d0300b91b7b4cfb54b8ac244b9443fe8f83dbb95145d7f8c37ade984e7239507",
          "size_bytes": 1737,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d0300b91b7b4cfb54b8ac244b9443fe8f83dbb95145d7f8c37ade984e7239507",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-24.md",
          "record_count": null,
          "sha256": "3b7682800bdd7ebf3abbee95afcd69fa7b3f7f877c81bc57d31d41bf1b030757",
          "size_bytes": 1742,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/3b7682800bdd7ebf3abbee95afcd69fa7b3f7f877c81bc57d31d41bf1b030757",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-25.md",
          "record_count": null,
          "sha256": "42cf42b3f69e1fbcea63ecc62a3764ac22130040694580f77590a88defecfa23",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/42cf42b3f69e1fbcea63ecc62a3764ac22130040694580f77590a88defecfa23",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-26.md",
          "record_count": null,
          "sha256": "43c56977508352616008101248ec0de5db86bec7b44b1642ffddd18ab79a6d94",
          "size_bytes": 1742,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/43c56977508352616008101248ec0de5db86bec7b44b1642ffddd18ab79a6d94",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-27.md",
          "record_count": null,
          "sha256": "4ac4cc4d1ae290c25b3e72a06f6b9fd080ae8170c277b8555fff137ed7cba91d",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/4ac4cc4d1ae290c25b3e72a06f6b9fd080ae8170c277b8555fff137ed7cba91d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-28.md",
          "record_count": null,
          "sha256": "e75e0b270ec136fc3b5ed584c1f28e8d4a75f357e27b47446c8eb1510dd09b87",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/e75e0b270ec136fc3b5ed584c1f28e8d4a75f357e27b47446c8eb1510dd09b87",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-08-31.md",
          "record_count": null,
          "sha256": "d885d323aea5ca5bfb0a19684dc9accbc7a9bdf0f40496fe6bd5effb861ffeed",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d885d323aea5ca5bfb0a19684dc9accbc7a9bdf0f40496fe6bd5effb861ffeed",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-01.md",
          "record_count": null,
          "sha256": "be16f20dfb2cc264c4c9f85a6061c4494c844207baa88b38f973585eb8ac3929",
          "size_bytes": 1746,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/be16f20dfb2cc264c4c9f85a6061c4494c844207baa88b38f973585eb8ac3929",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-02.md",
          "record_count": null,
          "sha256": "b264718c16a877e0a3096b2bdc7a691cc98e2ee1e86faa2895953cac3f36d654",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b264718c16a877e0a3096b2bdc7a691cc98e2ee1e86faa2895953cac3f36d654",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-03.md",
          "record_count": null,
          "sha256": "5a7888361cb36d477417bffa84b93667f6f53560b25952315783cd33bc6a0f57",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/5a7888361cb36d477417bffa84b93667f6f53560b25952315783cd33bc6a0f57",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-04.md",
          "record_count": null,
          "sha256": "40d23f8116a46650265df67c651d3a30068a2ad39e68ceedfa15cf41aafd3355",
          "size_bytes": 1747,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/40d23f8116a46650265df67c651d3a30068a2ad39e68ceedfa15cf41aafd3355",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-07.md",
          "record_count": null,
          "sha256": "30e67efe07a50b6a6b54855929ad6af0cae64ed61b55dc9e3fa9516c6cb5eb6b",
          "size_bytes": 1748,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/30e67efe07a50b6a6b54855929ad6af0cae64ed61b55dc9e3fa9516c6cb5eb6b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-08.md",
          "record_count": null,
          "sha256": "f3e7eb1beb00104123dcc5adb7a158a35fc36f62a03915c5abdf68236945c60d",
          "size_bytes": 1747,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/f3e7eb1beb00104123dcc5adb7a158a35fc36f62a03915c5abdf68236945c60d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-09.md",
          "record_count": null,
          "sha256": "d4a354c8d1d8dc3ee309bdda62e1917259f98fbfb87acfa632c40282919c9fba",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d4a354c8d1d8dc3ee309bdda62e1917259f98fbfb87acfa632c40282919c9fba",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-10.md",
          "record_count": null,
          "sha256": "ba52216859c03481296bb4d943ae343d4ecf60950cc796fcfddd1fd96ba8ce2f",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ba52216859c03481296bb4d943ae343d4ecf60950cc796fcfddd1fd96ba8ce2f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-11.md",
          "record_count": null,
          "sha256": "b62ebb513190a36b5ad236cefb684f89f1fa4daaa2efb341ea5847debeafd74f",
          "size_bytes": 1749,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b62ebb513190a36b5ad236cefb684f89f1fa4daaa2efb341ea5847debeafd74f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-14.md",
          "record_count": null,
          "sha256": "2cebfd0ce5a4c1feee5e74c512cae5b189ef8f5bc400c2df5a7773d87757a14f",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/2cebfd0ce5a4c1feee5e74c512cae5b189ef8f5bc400c2df5a7773d87757a14f",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-15.md",
          "record_count": null,
          "sha256": "5c00b8d24449edb06f7c273a057bf3e72358ad12df4e2cfe1a0a8714295cc90e",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/5c00b8d24449edb06f7c273a057bf3e72358ad12df4e2cfe1a0a8714295cc90e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-16.md",
          "record_count": null,
          "sha256": "b6fffa71d0e90842edd6d27766f15763197c84a89fe99b49c997f88ce89a6543",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b6fffa71d0e90842edd6d27766f15763197c84a89fe99b49c997f88ce89a6543",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-17.md",
          "record_count": null,
          "sha256": "f03f5d55a814d36ff930fdfcd8eb166072040fdf787645c943bcb5ab3a13cfbb",
          "size_bytes": 1744,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/f03f5d55a814d36ff930fdfcd8eb166072040fdf787645c943bcb5ab3a13cfbb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-18.md",
          "record_count": null,
          "sha256": "100944791fa4121500ef1442f8d2fdfb7369f47eb4e265a2858c5c7bd0b2f823",
          "size_bytes": 1743,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/100944791fa4121500ef1442f8d2fdfb7369f47eb4e265a2858c5c7bd0b2f823",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-21.md",
          "record_count": null,
          "sha256": "c6534dd010ec90470584b1963a9ffd8a1f01dd307b2e04087d84645abfa02fc5",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c6534dd010ec90470584b1963a9ffd8a1f01dd307b2e04087d84645abfa02fc5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-22.md",
          "record_count": null,
          "sha256": "d5c7aefdadb805987efbb686277d16fb2f7e819fb0d6ac1a1d40deed0a6aff6e",
          "size_bytes": 1745,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d5c7aefdadb805987efbb686277d16fb2f7e819fb0d6ac1a1d40deed0a6aff6e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-23.md",
          "record_count": null,
          "sha256": "ef3b24b1ae89cdab8bff3e376b250cbd18737f0cbe212b30cf947d01a205d502",
          "size_bytes": 1746,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ef3b24b1ae89cdab8bff3e376b250cbd18737f0cbe212b30cf947d01a205d502",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-28.md",
          "record_count": null,
          "sha256": "657596725f41f76d5e7422e75ccf82682476e58ad5da9b1cd52d4363bb2b3126",
          "size_bytes": 1751,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/657596725f41f76d5e7422e75ccf82682476e58ad5da9b1cd52d4363bb2b3126",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-29.md",
          "record_count": null,
          "sha256": "36ceb388f9f11b63ad7fea64a2224a114a2164c9fdf5d2c478095f1cb039add2",
          "size_bytes": 1748,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/36ceb388f9f11b63ad7fea64a2224a114a2164c9fdf5d2c478095f1cb039add2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-09-30.md",
          "record_count": null,
          "sha256": "3c8361e19dd4bd0070e6e77135d9a374ccd52657c472e6b7b0226c8165e5ad23",
          "size_bytes": 1751,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/3c8361e19dd4bd0070e6e77135d9a374ccd52657c472e6b7b0226c8165e5ad23",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-08.md",
          "record_count": null,
          "sha256": "628a3e8f82be16f816e9792801bc32e17545ba2562c7538776c4addad59465ee",
          "size_bytes": 2259,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/628a3e8f82be16f816e9792801bc32e17545ba2562c7538776c4addad59465ee",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-09.md",
          "record_count": null,
          "sha256": "131abaca24648795596989fbb9f3630085b99fed7f4e67972722efe4b252fbd7",
          "size_bytes": 2259,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/131abaca24648795596989fbb9f3630085b99fed7f4e67972722efe4b252fbd7",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-13.md",
          "record_count": null,
          "sha256": "cee994e90d06a19ebc06e3c16a1591070df3c441b21c0201d171c49e1345722c",
          "size_bytes": 2259,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/cee994e90d06a19ebc06e3c16a1591070df3c441b21c0201d171c49e1345722c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-15.md",
          "record_count": null,
          "sha256": "1beada078196a92c135bf3b63a08176d4b9491a5f3a3f01a1cd926f155520d52",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/1beada078196a92c135bf3b63a08176d4b9491a5f3a3f01a1cd926f155520d52",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-16.md",
          "record_count": null,
          "sha256": "24ea1f008aebc02b439be04de1a411f7588ce3709af775af03247a05801528c3",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/24ea1f008aebc02b439be04de1a411f7588ce3709af775af03247a05801528c3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-19.md",
          "record_count": null,
          "sha256": "2f32b26f7c13cf86a0d59c45bfb6efafd69a093ace207aa995ab85ff9880bcc2",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/2f32b26f7c13cf86a0d59c45bfb6efafd69a093ace207aa995ab85ff9880bcc2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-20.md",
          "record_count": null,
          "sha256": "ebc60df0a25c4abdf9902e5fa1291a43204fff6d428c0cf8c44af3114cc82509",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ebc60df0a25c4abdf9902e5fa1291a43204fff6d428c0cf8c44af3114cc82509",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-21.md",
          "record_count": null,
          "sha256": "c9da8922e28bc527f7ef5cc1df714cf10a1b4a9381b06440091e669c24bf149e",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c9da8922e28bc527f7ef5cc1df714cf10a1b4a9381b06440091e669c24bf149e",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-23.md",
          "record_count": null,
          "sha256": "fb278e68b703500e2b97de27dfebfe69e7ab4b32262a3b3f21af0c79309cdc64",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fb278e68b703500e2b97de27dfebfe69e7ab4b32262a3b3f21af0c79309cdc64",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-26.md",
          "record_count": null,
          "sha256": "48ce47bcf357bedd067e87c09954cbb569b18175be442e5fb55fabd5bbc31bfa",
          "size_bytes": 2261,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/48ce47bcf357bedd067e87c09954cbb569b18175be442e5fb55fabd5bbc31bfa",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-27.md",
          "record_count": null,
          "sha256": "c6b112cfd649d4ee50a7a8ff1d39f49d8b6a2198b9d3d2b0ccc7fad4219a4878",
          "size_bytes": 2263,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c6b112cfd649d4ee50a7a8ff1d39f49d8b6a2198b9d3d2b0ccc7fad4219a4878",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-29.md",
          "record_count": null,
          "sha256": "9bbcf86ec071f4b688d87f0fea09882c645fda08c52cab0445a95f927a27ce9d",
          "size_bytes": 2263,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/9bbcf86ec071f4b688d87f0fea09882c645fda08c52cab0445a95f927a27ce9d",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-01_2026-10-30.md",
          "record_count": null,
          "sha256": "60f9bb01acc1d270bb4ec09691c0630b19f0f269a3f9483db85bc966e6eece5b",
          "size_bytes": 2263,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/60f9bb01acc1d270bb4ec09691c0630b19f0f269a3f9483db85bc966e6eece5b",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/paper_vs_market_2026-06-11_2026-07-09.md",
          "record_count": null,
          "sha256": "0cd141c22a2e3efa16b2c72f824cc9e3178ff826f85d52d96dbba6c5a5815e7f",
          "size_bytes": 1457,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/0cd141c22a2e3efa16b2c72f824cc9e3178ff826f85d52d96dbba6c5a5815e7f",
          "status": "captured"
        },
        {
          "first_date": "2026-07-10",
          "last_date": "2026-07-10",
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/manifest.json",
          "record_count": 1,
          "sha256": "b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6",
          "size_bytes": 4174,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b4ce922b6180b369d2219ccaa6a817adaff1b53f3bd26193064d09fb0ae246c6",
          "status": "captured"
        },
        {
          "first_date": "2026-03-19",
          "last_date": "2026-05-19",
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/trades.jsonl",
          "record_count": 9,
          "sha256": "8ae058057e8b9ee1ae52369d32cc0fa96b9575a01a71b4d50b0624eca709de9a",
          "size_bytes": 1638,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/8ae058057e8b9ee1ae52369d32cc0fa96b9575a01a71b4d50b0624eca709de9a",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/aux-gray-n-fixed-2026-07-10/verdict.json",
          "record_count": 1,
          "sha256": "eec84c380b4696c652657886dfed8008a9b773df8cf89b72031bc7c13d0687fc",
          "size_bytes": 1799,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/eec84c380b4696c652657886dfed8008a9b773df8cf89b72031bc7c13d0687fc",
          "status": "captured"
        },
        {
          "first_date": "2026-07-10",
          "last_date": "2026-07-10",
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/manifest.json",
          "record_count": 1,
          "sha256": "f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381",
          "size_bytes": 4224,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/f6c39e341edd76790084ab5c212bd85d35fddac1bde44ebe2d7d595ce2eb0381",
          "status": "captured"
        },
        {
          "first_date": "2026-03-02",
          "last_date": "2026-06-26",
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/trades.jsonl",
          "record_count": 25,
          "sha256": "58719f1fb223330affcec1287d4abf641d8f536500293025dbd5afc6c73d16be",
          "size_bytes": 4553,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/58719f1fb223330affcec1287d4abf641d8f536500293025dbd5afc6c73d16be",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/aux-gray-relay1-fixed-2026-07-10/verdict.json",
          "record_count": 1,
          "sha256": "a7bd2ff9aae1dd62e6579dd0fd7eeb420be2d3c4ddd59ac96c93861aa1fd5ecf",
          "size_bytes": 1766,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/a7bd2ff9aae1dd62e6579dd0fd7eeb420be2d3c4ddd59ac96c93861aa1fd5ecf",
          "status": "captured"
        },
        {
          "first_date": "2026-08-07",
          "last_date": "2026-08-07",
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/manifest.json",
          "record_count": 1,
          "sha256": "82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26",
          "size_bytes": 2535,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/82c462fee30c56503c0baf626e84c1300223a6d5de53c70fb6a7d9f6f45dae26",
          "status": "captured"
        },
        {
          "first_date": "2026-07-01",
          "last_date": "2026-08-06",
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/trades.jsonl",
          "record_count": 69,
          "sha256": "5b445e7cd3a3c3b53db9d58a9333456a151f102d52e735086087c0a59caf83d5",
          "size_bytes": 6000,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/5b445e7cd3a3c3b53db9d58a9333456a151f102d52e735086087c0a59caf83d5",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/runs/c-mode-rotation-k-survivors-executable-2026-08-07/verdict.json",
          "record_count": 1,
          "sha256": "c3e5e74bff341b76cb2c36abcf929e89253c270678cac61ce7ad4e9946b293ec",
          "size_bytes": 1728,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c3e5e74bff341b76cb2c36abcf929e89253c270678cac61ce7ad4e9946b293ec",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/2026-10-21-fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2.json",
          "record_count": 1,
          "sha256": "fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2",
          "size_bytes": 59389,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/2026-10-23-c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41.json",
          "record_count": 1,
          "sha256": "c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41",
          "size_bytes": 60806,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/2026-10-30-5e3f9a5f7ad6015b2508b6563221afd438a16a809239cb2766a0c7c3ca7194a4.json",
          "record_count": 1,
          "sha256": "5e3f9a5f7ad6015b2508b6563221afd438a16a809239cb2766a0c7c3ca7194a4",
          "size_bytes": 63267,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/5e3f9a5f7ad6015b2508b6563221afd438a16a809239cb2766a0c7c3ca7194a4",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-21",
          "path": "output/research/shortline_comparisons/inputs/44486d2616f8883fa6cfcbe1a733878ca7d2bbe4d271c7723d99607b41f793c9-positions.jsonl",
          "record_count": 238,
          "sha256": "44486d2616f8883fa6cfcbe1a733878ca7d2bbe4d271c7723d99607b41f793c9",
          "size_bytes": 354771,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/44486d2616f8883fa6cfcbe1a733878ca7d2bbe4d271c7723d99607b41f793c9",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/inputs/64e3794d19403eb9b5807b40b61c388f0bc097188beed60a323d64e3fb73a564-training_rows.parquet",
          "record_count": null,
          "sha256": "64e3794d19403eb9b5807b40b61c388f0bc097188beed60a323d64e3fb73a564",
          "size_bytes": 474159,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/64e3794d19403eb9b5807b40b61c388f0bc097188beed60a323d64e3fb73a564",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-30",
          "path": "output/research/shortline_comparisons/inputs/b8ade52abece828745e2cf28ded04ff1b8db57cc83fa9e52c99440c5a311a6d3-positions.jsonl",
          "record_count": 243,
          "sha256": "b8ade52abece828745e2cf28ded04ff1b8db57cc83fa9e52c99440c5a311a6d3",
          "size_bytes": 400193,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b8ade52abece828745e2cf28ded04ff1b8db57cc83fa9e52c99440c5a311a6d3",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/inputs/b9ccb2e357d807ca13750789c5be2ff66291656fc628a338db89a64ef2299674-training_rows.parquet",
          "record_count": null,
          "sha256": "b9ccb2e357d807ca13750789c5be2ff66291656fc628a338db89a64ef2299674",
          "size_bytes": 444415,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/b9ccb2e357d807ca13750789c5be2ff66291656fc628a338db89a64ef2299674",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_comparisons/inputs/f2d411e221e7b3c78ad8180cea0ae768fc4b4f3a1265485135c646e4598dba0d-training_rows.parquet",
          "record_count": null,
          "sha256": "f2d411e221e7b3c78ad8180cea0ae768fc4b4f3a1265485135c646e4598dba0d",
          "size_bytes": 452371,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/f2d411e221e7b3c78ad8180cea0ae768fc4b4f3a1265485135c646e4598dba0d",
          "status": "captured"
        },
        {
          "first_date": "2026-06-01",
          "last_date": "2026-10-23",
          "path": "output/research/shortline_comparisons/inputs/f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997-positions.jsonl",
          "record_count": 240,
          "sha256": "f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997",
          "size_bytes": 358936,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/f7fcfbe7f748caffb7cc7b72937a72e04d9e8dce50c4ed6078fe2485f1ee8997",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_experiments/2026-10-23/fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76.json",
          "record_count": 1,
          "sha256": "fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76",
          "size_bytes": 2836,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_experiments/2026-10-26/ea41a14836601305789eaa81e95019d696bcb3d7a182cda999e5f23ab459181c.json",
          "record_count": 1,
          "sha256": "ea41a14836601305789eaa81e95019d696bcb3d7a182cda999e5f23ab459181c",
          "size_bytes": 9274,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ea41a14836601305789eaa81e95019d696bcb3d7a182cda999e5f23ab459181c",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_experiments/2026-10-27/5e733a3b3babf6fc6daee12971478d1b2f439bbbbe0bdfb5a0c4cc961f2965fb.json",
          "record_count": 1,
          "sha256": "5e733a3b3babf6fc6daee12971478d1b2f439bbbbe0bdfb5a0c4cc961f2965fb",
          "size_bytes": 3999,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/5e733a3b3babf6fc6daee12971478d1b2f439bbbbe0bdfb5a0c4cc961f2965fb",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_experiments/2026-10-29/0749f321586fe056e3785d5e4dee479650da880961e4e734fb57f3c7c5a31873.json",
          "record_count": 1,
          "sha256": "0749f321586fe056e3785d5e4dee479650da880961e4e734fb57f3c7c5a31873",
          "size_bytes": 7758,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/0749f321586fe056e3785d5e4dee479650da880961e4e734fb57f3c7c5a31873",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "output/research/shortline_experiments/2026-10-30/91f5bbd4971e13ec1fdb6fb6fa35d4c7bfd9974399bad6dac92a0503cb67cc59.json",
          "record_count": 1,
          "sha256": "91f5bbd4971e13ec1fdb6fb6fa35d4c7bfd9974399bad6dac92a0503cb67cc59",
          "size_bytes": 7123,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/91f5bbd4971e13ec1fdb6fb6fa35d4c7bfd9974399bad6dac92a0503cb67cc59",
          "status": "captured"
        },
        {
          "first_date": "2025-01-09",
          "last_date": "2026-10-30",
          "path": "reference/experience/distill_action_log.jsonl",
          "record_count": 175,
          "sha256": "d6dded43aca2a456553eff3167fba4d50ef99a4025e0a9dfc540939d4b41097a",
          "size_bytes": 180258,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/d6dded43aca2a456553eff3167fba4d50ef99a4025e0a9dfc540939d4b41097a",
          "status": "captured"
        },
        {
          "first_date": null,
          "last_date": null,
          "path": "reference/experience/research_protocols.yaml",
          "record_count": null,
          "sha256": "ade8d7644a8ad7663bc1801ffa764fc386fe6a49ea669e377fe4c615308cd587",
          "size_bytes": 9662,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/ade8d7644a8ad7663bc1801ffa764fc386fe6a49ea669e377fe4c615308cd587",
          "status": "captured"
        },
        {
          "error": "Expecting value: line 1 column 1 (char 0)",
          "first_date": null,
          "last_date": null,
          "path": "reference/experience/xiaocao_hypotheses.jsonl",
          "record_count": null,
          "sha256": "6e0994bb2f50aa314c364776aa3cb5c7d4fa1cce64cd67dbdc3ce45d662187e4",
          "size_bytes": 409419,
          "snapshot_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/6e0994bb2f50aa314c364776aa3cb5c7d4fa1cce64cd67dbdc3ce45d662187e4",
          "status": "invalid"
        }
      ],
      "missing_patterns": [
        "output/research/weekly_comparison*.json",
        "output/live/posture_calibration.jsonl"
      ],
      "schema_version": 1,
      "sha256": "c687ca896e747dc2734f1e9b03be7b03f4ee401aa2f007982f6584510e5d6c7e",
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
              "reported_window": 30
            },
            "B": {
              "reported_window": 35
            },
            "T": {
              "reported_window": 5
            }
          },
          "confirmed_window_count": 0,
          "end": "2026-10-30",
          "entry_count": 70,
          "excluded_from_confirmed_count": 70,
          "fallback_count": 0,
          "fallback_proportion": 0.0,
          "proxy_count": 0,
          "proxy_proportion": 0.0,
          "reported_window_count": 70,
          "start": "2026-08-08",
          "unknown_count": 0
        },
        "1w": {
          "by_book": {
            "A": {
              "reported_window": 1
            },
            "B": {
              "reported_window": 1
            },
            "T": {
              "reported_window": 1
            }
          },
          "confirmed_window_count": 0,
          "end": "2026-10-30",
          "entry_count": 3,
          "excluded_from_confirmed_count": 3,
          "fallback_count": 0,
          "fallback_proportion": 0.0,
          "proxy_count": 0,
          "proxy_proportion": 0.0,
          "reported_window_count": 3,
          "start": "2026-10-24",
          "unknown_count": 0
        },
        "4w": {
          "by_book": {
            "A": {
              "reported_window": 9
            },
            "B": {
              "reported_window": 11
            },
            "T": {
              "reported_window": 2
            }
          },
          "confirmed_window_count": 0,
          "end": "2026-10-30",
          "entry_count": 22,
          "excluded_from_confirmed_count": 22,
          "fallback_count": 0,
          "fallback_proportion": 0.0,
          "proxy_count": 0,
          "proxy_proportion": 0.0,
          "reported_window_count": 22,
          "start": "2026-10-03",
          "unknown_count": 0
        }
      }
    },
    "production_observations": {
      "as_of": "2026-10-30",
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
          "maturity": "closed",
          "sell_trade_line": 440,
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
          "maturity": "closed",
          "sell_trade_line": 439,
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
          "book": "B",
          "buy_trade_line": 441,
          "code": "000710.XSHE",
          "entry_date": "2026-10-09",
          "line": 222,
          "maturity": "closed",
          "sell_trade_line": 446,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 442,
          "code": "000710.XSHE",
          "entry_date": "2026-10-09",
          "line": 223,
          "maturity": "closed",
          "sell_trade_line": 448,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 443,
          "code": "000725.XSHE",
          "entry_date": "2026-10-09",
          "line": 224,
          "maturity": "closed",
          "sell_trade_line": 478,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 444,
          "code": "605366.XSHG",
          "entry_date": "2026-10-12",
          "line": 225,
          "maturity": "closed",
          "sell_trade_line": 447,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 445,
          "code": "605366.XSHG",
          "entry_date": "2026-10-12",
          "line": 226,
          "maturity": "closed",
          "sell_trade_line": 449,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 450,
          "code": "002531.XSHE",
          "entry_date": "2026-10-14",
          "line": 227,
          "maturity": "closed",
          "sell_trade_line": 453,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 451,
          "code": "002531.XSHE",
          "entry_date": "2026-10-14",
          "line": 228,
          "maturity": "closed",
          "sell_trade_line": 454,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 452,
          "code": "603188.XSHG",
          "entry_date": "2026-10-15",
          "line": 229,
          "maturity": "closed",
          "sell_trade_line": 459,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 455,
          "code": "601188.XSHG",
          "entry_date": "2026-10-16",
          "line": 230,
          "maturity": "closed",
          "sell_trade_line": 460,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 456,
          "code": "300107.XSHE",
          "entry_date": "2026-10-16",
          "line": 231,
          "maturity": "closed",
          "sell_trade_line": 461,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 457,
          "code": "601188.XSHG",
          "entry_date": "2026-10-16",
          "line": 232,
          "maturity": "closed",
          "sell_trade_line": 462,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 458,
          "code": "300107.XSHE",
          "entry_date": "2026-10-16",
          "line": 233,
          "maturity": "closed",
          "sell_trade_line": 463,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 464,
          "code": "000573.XSHE",
          "entry_date": "2026-10-20",
          "line": 234,
          "maturity": "closed",
          "sell_trade_line": 469,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 465,
          "code": "000573.XSHE",
          "entry_date": "2026-10-20",
          "line": 235,
          "maturity": "closed",
          "sell_trade_line": 470,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 466,
          "code": "301052.XSHE",
          "entry_date": "2026-10-21",
          "line": 236,
          "maturity": "closed",
          "sell_trade_line": 472,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 467,
          "code": "002889.XSHE",
          "entry_date": "2026-10-21",
          "line": 237,
          "maturity": "closed",
          "sell_trade_line": 471,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 468,
          "code": "301052.XSHE",
          "entry_date": "2026-10-21",
          "line": 238,
          "maturity": "closed",
          "sell_trade_line": 475,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 473,
          "code": "002172.XSHE",
          "entry_date": "2026-10-23",
          "line": 239,
          "maturity": "closed",
          "sell_trade_line": 476,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 474,
          "code": "002172.XSHE",
          "entry_date": "2026-10-23",
          "line": 240,
          "maturity": "closed",
          "sell_trade_line": 477,
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "T",
          "buy_trade_line": 479,
          "code": "000725.XSHE",
          "entry_date": "2026-10-29",
          "line": 241,
          "maturity": "immature",
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "B",
          "buy_trade_line": 480,
          "code": "001287.XSHE",
          "entry_date": "2026-10-30",
          "line": 242,
          "maturity": "immature",
          "source": "output/live/positions.jsonl",
          "state": "valid"
        },
        {
          "book": "A",
          "buy_trade_line": 481,
          "code": "001287.XSHE",
          "entry_date": "2026-10-30",
          "line": 243,
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
          "closed_cash_net_change": 32857.48,
          "closed_lots": 98,
          "entry_fee": 223.33,
          "exit_fee": 223.24,
          "mean_closed_lot_return_pct": 0.9624128983600602,
          "open_lots": 1,
          "valid_lots": 99
        },
        "B": {
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
          "closed_cash_net_change": 42168.43,
          "closed_lots": 113,
          "entry_fee": 261.62,
          "exit_fee": 262.54,
          "mean_closed_lot_return_pct": 0.9948833053305053,
          "open_lots": 1,
          "valid_lots": 114
        },
        "T": {
          "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
          "closed_cash_net_change": -2102.73,
          "closed_lots": 10,
          "entry_fee": 11.26,
          "exit_fee": 8.25,
          "mean_closed_lot_return_pct": -3.066369229293183,
          "open_lots": 3,
          "valid_lots": 13
        }
      },
      "counts": {
        "bad": 0,
        "closed": 221,
        "future": 0,
        "immature": 5,
        "unknown": 17,
        "unknown_trades": 17,
        "valid": 226
      },
      "fill_basis_counts": {
        "basket": 9,
        "open_reference": 21,
        "opening_window_capped_by_basket": 3,
        "opening_window_vwap_capped_by_limit": 191,
        "verified_first_minute_high_cost_v1": 2
      },
      "latest_record_date": "2026-10-30",
      "limitations": [
        "Legacy date/naive clocks lack verified availability time and timezone; no intraday timeliness proof.",
        "Modeled paper fees and cash changes are not actual broker fees, executable alpha or portfolio NAV.",
        "A/B identical-entry closed-lot comparison has selection/censoring bias and is not KOL alpha.",
        "No no-KOL/current/challenger strategy runs inferred; no source truth repaired."
      ],
      "paired_exit_comparison": {
        "censored": 1,
        "eligible": 59,
        "entry_mismatch": 38,
        "excluded": 56,
        "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
        "mean_b_minus_a_pp": 0.6309447591057925,
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
            "b_minus_a_pp": 0.0,
            "code": "000573.XSHE",
            "entry_date": "2026-10-20"
          },
          {
            "b_minus_a_pp": -0.19877187531375462,
            "code": "000710.XSHE",
            "entry_date": "2026-10-09"
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
            "b_minus_a_pp": -1.6739938049082406,
            "code": "002172.XSHE",
            "entry_date": "2026-10-23"
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
            "b_minus_a_pp": 3.4268597204119984,
            "code": "002531.XSHE",
            "entry_date": "2026-10-14"
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
            "b_minus_a_pp": 0.0,
            "code": "300107.XSHE",
            "entry_date": "2026-10-16"
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
            "b_minus_a_pp": 3.061471955958942,
            "code": "301052.XSHE",
            "entry_date": "2026-10-21"
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
            "b_minus_a_pp": 14.918268863877424,
            "code": "301560.XSHE",
            "entry_date": "2026-09-28"
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
            "b_minus_a_pp": 0.6487960736632882,
            "code": "601188.XSHG",
            "entry_date": "2026-10-16"
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
            "b_minus_a_pp": -11.557685803722265,
            "code": "605366.XSHG",
            "entry_date": "2026-10-12"
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
        "unmatched": 17
      },
      "sources": [
        {
          "latest_record_date": "2026-10-30",
          "parsed_records": 243,
          "path": "output/live/positions.jsonl",
          "sha256": "b8ade52abece828745e2cf28ded04ff1b8db57cc83fa9e52c99440c5a311a6d3",
          "status": "captured"
        },
        {
          "latest_record_date": "2026-10-30",
          "parsed_records": 481,
          "path": "output/live/paper_trades.jsonl",
          "sha256": "9c13a72098dd74bf4ba50ffc34929b45f365abe15f14d35a34e726134b1ce7e2",
          "status": "captured"
        }
      ],
      "staleness_calendar_days": 0,
      "timeliness_proven": false,
      "windows": {
        "12w": {
          "books": {
            "A": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": 27728.5,
              "closed_lots": 29,
              "entry_fee": 116.57,
              "exit_fee": 115.93,
              "mean_closed_lot_return_pct": 2.7873252844685186,
              "open_lots": 1,
              "valid_lots": 30
            },
            "B": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": 35758.8,
              "closed_lots": 34,
              "entry_fee": 139.64,
              "exit_fee": 139.83,
              "mean_closed_lot_return_pct": 2.5871460611035997,
              "open_lots": 1,
              "valid_lots": 35
            },
            "T": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": -1091.83,
              "closed_lots": 2,
              "entry_fee": 4.13,
              "exit_fee": 1.23,
              "mean_closed_lot_return_pct": -8.252816264423144,
              "open_lots": 3,
              "valid_lots": 5
            }
          },
          "end": "2026-10-30",
          "latest_data_before_window": false,
          "paired_exit_comparison": {
            "censored": 1,
            "eligible": 29,
            "entry_mismatch": 0,
            "excluded": 6,
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
            "mean_b_minus_a_pp": 0.6675597133604869,
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
                "b_minus_a_pp": 0.0,
                "code": "000573.XSHE",
                "entry_date": "2026-10-20"
              },
              {
                "b_minus_a_pp": -0.19877187531375462,
                "code": "000710.XSHE",
                "entry_date": "2026-10-09"
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
                "b_minus_a_pp": -1.6739938049082406,
                "code": "002172.XSHE",
                "entry_date": "2026-10-23"
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
                "b_minus_a_pp": 3.4268597204119984,
                "code": "002531.XSHE",
                "entry_date": "2026-10-14"
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
                "b_minus_a_pp": 0.0,
                "code": "300107.XSHE",
                "entry_date": "2026-10-16"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "300426.XSHE",
                "entry_date": "2026-08-14"
              },
              {
                "b_minus_a_pp": 3.061471955958942,
                "code": "301052.XSHE",
                "entry_date": "2026-10-21"
              },
              {
                "b_minus_a_pp": 0.3539085728812919,
                "code": "301520.XSHE",
                "entry_date": "2026-09-21"
              },
              {
                "b_minus_a_pp": 14.918268863877424,
                "code": "301560.XSHE",
                "entry_date": "2026-09-28"
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
                "b_minus_a_pp": 0.6487960736632882,
                "code": "601188.XSHG",
                "entry_date": "2026-10-16"
              },
              {
                "b_minus_a_pp": -0.12871204274502723,
                "code": "603042.XSHG",
                "entry_date": "2026-09-29"
              },
              {
                "b_minus_a_pp": -11.557685803722265,
                "code": "605366.XSHG",
                "entry_date": "2026-10-12"
              }
            ],
            "unknown_lots": 0,
            "unmatched": 5
          },
          "start": "2026-08-08",
          "status": "observed",
          "valid_lots": 70
        },
        "1w": {
          "books": {
            "A": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": null,
              "closed_lots": 0,
              "entry_fee": 3.44,
              "exit_fee": null,
              "mean_closed_lot_return_pct": null,
              "open_lots": 1,
              "valid_lots": 1
            },
            "B": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": null,
              "closed_lots": 0,
              "entry_fee": 3.44,
              "exit_fee": null,
              "mean_closed_lot_return_pct": null,
              "open_lots": 1,
              "valid_lots": 1
            },
            "T": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": null,
              "closed_lots": 0,
              "entry_fee": 0.57,
              "exit_fee": null,
              "mean_closed_lot_return_pct": null,
              "open_lots": 1,
              "valid_lots": 1
            }
          },
          "end": "2026-10-30",
          "latest_data_before_window": false,
          "paired_exit_comparison": {
            "censored": 1,
            "eligible": 0,
            "entry_mismatch": 0,
            "excluded": 1,
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
            "mean_b_minus_a_pp": null,
            "open": 1,
            "pairs": [],
            "unknown_lots": 0,
            "unmatched": 0
          },
          "start": "2026-10-24",
          "status": "observed",
          "valid_lots": 3
        },
        "4w": {
          "books": {
            "A": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": 235.24,
              "closed_lots": 8,
              "entry_fee": 45.07,
              "exit_fee": 41.67,
              "mean_closed_lot_return_pct": -0.15545403412050354,
              "open_lots": 1,
              "valid_lots": 9
            },
            "B": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": -1087.52,
              "closed_lots": 10,
              "entry_fee": 55.93,
              "exit_fee": 52.4,
              "mean_closed_lot_return_pct": -1.2324640689105943,
              "open_lots": 1,
              "valid_lots": 11
            },
            "T": {
              "basis": "recorded_modeled_cash; entry-date cohort; closed-by-as-of; not portfolio NAV",
              "closed_cash_net_change": -905.3,
              "closed_lots": 1,
              "entry_fee": 1.23,
              "exit_fee": 0.57,
              "mean_closed_lot_return_pct": -13.756832448679706,
              "open_lots": 1,
              "valid_lots": 2
            }
          },
          "end": "2026-10-30",
          "latest_data_before_window": false,
          "paired_exit_comparison": {
            "censored": 1,
            "eligible": 8,
            "entry_mismatch": 0,
            "excluded": 3,
            "interpretation": "descriptive paired exit comparison; not KOL alpha; closed-lot selection bias",
            "mean_b_minus_a_pp": -0.786665466738754,
            "open": 1,
            "pairs": [
              {
                "b_minus_a_pp": 0.0,
                "code": "000573.XSHE",
                "entry_date": "2026-10-20"
              },
              {
                "b_minus_a_pp": -0.19877187531375462,
                "code": "000710.XSHE",
                "entry_date": "2026-10-09"
              },
              {
                "b_minus_a_pp": -1.6739938049082406,
                "code": "002172.XSHE",
                "entry_date": "2026-10-23"
              },
              {
                "b_minus_a_pp": 3.4268597204119984,
                "code": "002531.XSHE",
                "entry_date": "2026-10-14"
              },
              {
                "b_minus_a_pp": 0.0,
                "code": "300107.XSHE",
                "entry_date": "2026-10-16"
              },
              {
                "b_minus_a_pp": 3.061471955958942,
                "code": "301052.XSHE",
                "entry_date": "2026-10-21"
              },
              {
                "b_minus_a_pp": 0.6487960736632882,
                "code": "601188.XSHG",
                "entry_date": "2026-10-16"
              },
              {
                "b_minus_a_pp": -11.557685803722265,
                "code": "605366.XSHG",
                "entry_date": "2026-10-12"
              }
            ],
            "unknown_lots": 0,
            "unmatched": 2
          },
          "start": "2026-10-03",
          "status": "observed",
          "valid_lots": 22
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
    "shortline_research": {
      "comparisons": [
        {
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
          "end": "2026-10-21",
          "evidence": {
            "path": "output/research/shortline_comparisons/2026-10-21-fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2.json",
            "sha256": "fbc59c05d59ece99717c56e96e808db861ed23d9caa5c21ef9b32aa8186427e2"
          },
          "observed_at": "2026-10-22T11:39:47.102458+08:00",
          "paired_exit": {
            "eligible_pairs": 57,
            "entry_day_count": 35,
            "mean_b_minus_a_pp": 0.6287414497577378,
            "median_b_minus_a_pp": 0.0
          },
          "status": "descriptive_only_no_promotion"
        },
        {
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
          "end": "2026-10-23",
          "evidence": {
            "path": "output/research/shortline_comparisons/2026-10-23-c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41.json",
            "sha256": "c27bc5d617897c4d6d2e65ca70943a2719ef0042a1a061907061b360872a4d41"
          },
          "observed_at": "2026-10-23T20:35:24.740180+08:00",
          "paired_exit": {
            "eligible_pairs": 58,
            "entry_day_count": 36,
            "mean_b_minus_a_pp": 0.670685079175,
            "median_b_minus_a_pp": 0.0
          },
          "status": "descriptive_only_no_promotion"
        },
        {
          "coverage": {
            "bjse_rows_retained_in_raw_denominator": 27,
            "candidate_rows": 1063,
            "capture_hash_rows": 178,
            "complete_flag_days": 65,
            "complete_label_days": 56,
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
              "False": 33,
              "None": 40,
              "True": 990
            },
            "signal_days": 94
          },
          "end": "2026-10-30",
          "evidence": {
            "path": "output/research/shortline_comparisons/2026-10-30-5e3f9a5f7ad6015b2508b6563221afd438a16a809239cb2766a0c7c3ca7194a4.json",
            "sha256": "5e3f9a5f7ad6015b2508b6563221afd438a16a809239cb2766a0c7c3ca7194a4"
          },
          "observed_at": "2026-10-30T20:28:46.603566+08:00",
          "paired_exit": {
            "eligible_pairs": 59,
            "entry_day_count": 37,
            "mean_b_minus_a_pp": 0.6309447591057925,
            "median_b_minus_a_pp": 0.0
          },
          "status": "descriptive_only_no_promotion"
        }
      ],
      "current_window_report_observed": true,
      "invalid": [],
      "portfolio_experiment_status": "not_established_by_selection_records",
      "promotion_eligible": false,
      "selection_days": 5,
      "selection_records": [
        {
          "date": "2026-10-23",
          "evidence": {
            "path": "output/research/shortline_experiments/2026-10-23/fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76.json",
            "sha256": "fc3bdbb217b86c695700796ce0c35ca32688480d36e660ce82eddfc1b8553b76"
          },
          "status": "selection_recorded_outcomes_pending"
        },
        {
          "date": "2026-10-26",
          "evidence": {
            "path": "output/research/shortline_experiments/2026-10-26/ea41a14836601305789eaa81e95019d696bcb3d7a182cda999e5f23ab459181c.json",
            "sha256": "ea41a14836601305789eaa81e95019d696bcb3d7a182cda999e5f23ab459181c"
          },
          "status": "selection_recorded_outcomes_pending"
        },
        {
          "date": "2026-10-27",
          "evidence": {
            "path": "output/research/shortline_experiments/2026-10-27/5e733a3b3babf6fc6daee12971478d1b2f439bbbbe0bdfb5a0c4cc961f2965fb.json",
            "sha256": "5e733a3b3babf6fc6daee12971478d1b2f439bbbbe0bdfb5a0c4cc961f2965fb"
          },
          "status": "selection_recorded_outcomes_pending"
        },
        {
          "date": "2026-10-29",
          "evidence": {
            "path": "output/research/shortline_experiments/2026-10-29/0749f321586fe056e3785d5e4dee479650da880961e4e734fb57f3c7c5a31873.json",
            "sha256": "0749f321586fe056e3785d5e4dee479650da880961e4e734fb57f3c7c5a31873"
          },
          "status": "selection_recorded_outcomes_pending"
        },
        {
          "date": "2026-10-30",
          "evidence": {
            "path": "output/research/shortline_experiments/2026-10-30/91f5bbd4971e13ec1fdb6fb6fa35d4c7bfd9974399bad6dac92a0503cb67cc59.json",
            "sha256": "91f5bbd4971e13ec1fdb6fb6fa35d4c7bfd9974399bad6dac92a0503cb67cc59"
          },
          "status": "selection_recorded_outcomes_pending"
        }
      ],
      "status": "observed"
    },
    "snapshot_manifest_path": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-30_inputs/c687ca896e747dc2734f1e9b03be7b03f4ee401aa2f007982f6584510e5d6c7e.manifest.json",
    "status": "insufficient_evidence"
  }
}
```
