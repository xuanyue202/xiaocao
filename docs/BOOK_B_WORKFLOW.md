# APP Book B 统一操作流程

适用 APP 服务端仿真短线、原 Paper B 和独立前向研究。规则权威为
[Operating Contract](OPERATING_CONTRACT.md) §1c/§2a/§4/§6/§10。
Book T 保持趋势体系，不参与短线排名。

## 已采纳的依据与边界

2026-10-22 的完整比较截止 10-21。57 组同进场已平仓 A/B 配对，在统一资金回放中
A 为 +11.4389%、B 为 +19.0082%；完成样本偏差仍在，支持保留 B 退出而非宣称最优。
48 个具备严格 D+1 证据的共同信号日，E / M 资金路径为 +14.1879% / +11.9634%；
扩大到退出日期未证明的旧标签会翻转排序，因此 APP 保留 E 和普通 COLD 默认门。
共同成交路径的差异同时涉及买价和退出日期，不能只看单笔均值或把差额当可追回利润。

APP 继续现有 E、B 分阶段退出、动态资金、10%/20% 损失预算和原单纪律。
M、open 限价、no-KOL 只占三个独立研究槽；这次工程升级没有晋级这些策略。

## 从原始批次到实际结果

| 阶段 | 职责 | 完成证据 |
|---|---|---|
| morning producer | 完整原候选、模式事实、不可变批次 | 日期、原 checkpoint、raw/canonical hash、策略 SHA |
| KOL writer 与当下判断 | 唯一来源语义；当前适用性及独立复核 | 原请求、精确映射、有效 policy |
| 共同裁决 | 解释原门与 KOL 效应 | `book-b-adjudication.v1` 每只候选的原因 |
| 最终计划 | 共同整手分配与政策上限 | `book-b-final-plan.v1` 资金事实、候选、计划经济字段 |
| APP 执行 | 账户/行情/原单门，串行提交、准确终态 | intent、claim、柜台号、成交增量、未决状态 |
| 会计与研究 | lot、费用、资金流、同频估值、分歧 | 原账链和独立资金账户，实际与模型结果分栏 |

`book_b_workflow` 解释策略，`book_b_allocation.allocate_policy_rows` 负责同一分配规则。
`compare_final_plans` 首先比较来源，再比较规则、政策/选择、资金输入、执行模型和最终
订单经济字段。日常报告会用原 owner 的 runs/history 中已验 hash 的 APP final_plan 与同日 app_b_control
逐一比较，并把首处分歧送入 weekly evidence。旧回执缺 final_plan 时记录缺证，不重建。
相同选择 hash 不能代替相同手数、成交或收益。APP 的 final_plan 是
归因证据，实际执行权限继续由原 guards 和 durable claim 决定。

原 Paper A/B/T 及 A 性能传感器保留历史和现行写者。原 Paper B 的较宽候选池作为旧流程
对照；新的 `app_b_control` 使用 APP 分配器。两者不能混称同一 Paper B 账户。

## 当前判断与“不动”的解释

有效中性政策、复用有效政策、当前请求已完成、支持超时/缺失/风险免等分别记录。
当前请求完成要求 decision/review 同时绑定原 `morning_request_sha256`，且原预算内
完成。`mode_mappings` 保存原词、精确目标、exact/conditional/unmapped、条件和当前
适用性，独立审核绑定 `mode_mapping_reviewed`。普通 COLD 不因关键词或模式别名解除；
合法 v2 模式跟随仍只消费原有授权接口，UNKNOWN 不恢复。

候选被选中后，政策缩放、账户风险、已有持仓/预留、整手、行情和订单门仍可能拒绝。
没有 final_plan 的旧回执保持未证明；不补写过去的决策或重放已完成交易日。

## SELL 闭环

完整账户读失败，只对已分类的只读证据错误尝试独立 `sellable_only`：同账户/同日/
60 秒内、完整结构及关键格置信度、自有成交链、当前数量/可卖数量、lot 与 T+1。
身份或日期不符保持阻断。投影不提供现金、估值、NAV 或结算；BUY/EOD 继续原完整门。
提交前再次检查当前可卖数量、全部当日委托 ID 和目标 tuple，原意图、报价、双钥匙及
claim 保持。资金读取失败不会冒充“已核验资金”。

原 intraday checkpoint 在原 120 秒总预算与 14:57 较早截止内，完成串行交接后调用
`reconcile_existing` 读取已 claim 的原单，等待期间释放 APP/账户锁。预算在 APP 准备前
持久化；不因回读重置。ACK/PARTIAL/UNKNOWN 是 pending；已成交/撤销/拒绝才有对应
终态。进度文件和最终回执分别保存。后续 lot 失败也须保留此前订单，禁止用第二个 runner
重报。截止未证明保留原单、部分成交和 UNKNOWN；正式结算仍严格。

`app_lifecycle.json` 将原 freeze 引用、计划、报价、限价、柜台号、fill、lot、资金与
费用观测连起来。时长标作本地观察时长，不冒称交易所撮合延迟。明确 user-assisted lot
单列；有自动执行链也不据此排除未记录的人工帮助。最终费用或现金归属不完整时，
确认利润为未知，估费收益另列。

## 独立前向资金实验

预登记协议 `app-b-forward-funded-v1` 及机器定义 `book_b_forward.PROTOCOL` 固定一个
10 万元基准和三个同资金、费用、风险、B 退出的挑战：

| 账户 | 唯一挑战 |
|---|---|
| app_b_control | APP E 筛选、共同分配和当前 live policy 的控制组 |
| mode_m | 显式 mode_star 参与度；继续当前模式资格、COLD/UNKNOWN 门 |
| open_limit | 数量保持共同分配，限价改为 min(open,basket)，检验价格与未成交成本 |
| no_kol | 关闭当前 KOL 增量，保留其余确定性门 |

全部状态在 `output/research/app_b_forward/`，一个锁内原子提交四账户状态及来源事件。
首次未来原始 morning 才建立计划；重复同日调用只读已消费结果，过迟输入记录不回填。
独立账户始终不调用 APP，不修改 canonical paper，不获取新的交易权限。

研究在原业务完成后运行，因此与 APP 的开盘执行时刻可能不同。该时序差异在协议、计划
和收益报告中明示；这不是同一时刻可实现收益的证明。每个模型订单登记实际创建时钟后，
才使用下一个完整五分钟窗口。只有完整分钟覆盖、时间/代码绑定、价格及成交量单位可核验
才模拟撮合：达到限价且最多使用窗口内满足价格条件成交量的 1%，按限价计费成交；剩余
数量仅在模型内到期。未知窗口保留资金/数量预留，不填入确定成交或确定净值。
这些是事先固定的模型假设，不能推断 APP 会成交、会部分成交或会自动撤单。

限价挑战同时保留全部计划、pending、零成交、未知、部分成交、费用、持仓和资本占用。
未决数为 pending + unknown；缺少 morning 的交易日与缺少 EOD 的交易日分别显示。净值使用
当前可核验价格；同日正式收盘价可用于 EOD。缺日保持缺日，观察点回撤不称完整日频回撤。
KOL 到期按真实消费时点降级；原计划与来源字节保留，不能用后来的政策重写前一计划。
行情按共同裁决后的四组候选并集获取，包含合法模式跟随新增的冻结候选；采集期间政策变更或到期必须明确拒绝这次未覆盖采样。研究事件使用原 supervisor 固定的源码版本，部署目录后续更新不能改写版本归因。

报告时点与已证日历截止分开。已有日历证明的日期按本次报告时点检查缺 morning/EOD；最后日历观测之后的尾段标为未证明，不因刷新报告时间就声称覆盖完整，也不凭周几补出交易日。

## 原任务的运行顺序

- morning execution：原 B/T 业务都结束后，shell 调 `research_book_b_forward.py --phase morning`。
- 14:25 与 14:45：原启动器在 paper/APP 都返回后调 `--phase monitor --checkpoint-phase precheck|closing`。普通 opening/sparse
  原 owner 在其两端业务完成后携带原 `--checkpoint-phase opening|sparse` 调用一次。晚到不改变阶段；仅 closing 允许软退出。无 tick 权限或控制层 no-op 的任务不运行研究分支，已完成的合法业务 no_action 仍推进独立模型账户。
- EOD：原 paper shell、APP EOD 和 statement 均结束后，由同一个 EOD owner 调用 `--phase eod` 一次，同时推进模型并刷新报告；研究采样不排在 APP 对账之前。
- weekly：原 shell 先刷新 report，weekly evidence 固定协议、资金报告、APP 生命周期的精确字节。

独立研究失败只标研究降级，保留原业务退出码；不延迟原 SELL 交接，不把研究 ready 当业务完成。
研究订单后续通过原登记窗口核验，不能靠重复 canonical paper_record 获取另一策略的成交。

## 维护、晋级与验收

每周沿三个固定 experiment_id 跟踪继续、反证、修订或退役，先处理既有实验再新增。
完整费用后资金收益是目标，同时看回撤、资金利用、尾部损失、未成交与未知分母。
APP 撮合规律仍须实际原单和 contemporaneous quote 验证，不能从模型或六组样本推断。

有收益结论前须核对完整机会日期、点时、资金约束、费用、样本外和成本敏感性。
`research_run.py` 的逐笔护栏与完整资金账户证据各自满足；组合日收益不能冒充逐笔样本。
永久晋级继续 §10 人工门，不由周报或累计收益排名自动启用。

工程验收区分代码/离线隔离测试、真实 APP 只读端口验证、未来原单自然终态、未来资金收益。
后两项不能由测试或说明替代。回滚定向 revert 源码 commit，保留原订单、协议、输入、研究
账户和会计历史；已有模型账户协议不兼容时拒绝继续，另行登记新实验而非覆盖旧状态。
