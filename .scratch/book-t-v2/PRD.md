# Book T v2：多源主题研判与 ETF/趋势股表达

Status: design-confirmed

## Problem Statement

现行 Book T 从大类排名取成分股，再用静态关键词把候选分成 `aligned / neutral / external`。它实际上没有消费小草的当前趋势研判，也不能从 Python 数据层发现真实 ETF；吕晓彤“马车”仅通过一条作者专属、别名专属的 shadow 匹配路径附着在股票候选上。账户的 slot 还是证券数量，因此同一主题的 ETF 与个股会被误当成两笔独立风险。满仓时，当前流程甚至会在形成当天完整主题判断前提前返回。

这会产生四个根本问题：KOL 观点被压缩成作者或关键词权重；短期马车与长期观点没有一致的时效边界；“看对主题”和“选对表达工具”被混成同一步；ETF 加入后，交易制度、整手、结算和主题集中度无法被现有股票假设安全承接。

Book T v2 要解决的不是“给马车加分”，而是建立一个 paper-only 的主题级趋势配置系统：Agent 负责把多源观点转成证据绑定、可复核的主题判断；确定性脊柱负责资格、标的解析、组合约束、成交、退出与账本。KOL 可以提出或强化主题，但不能绕过市场事实和研究门直接授权买入。

## Goals

1. 把 Book T 的基本风险单位从证券槽位改为最多三个主题槽位，总预算仍为独立 T 账户的 30%，允许留现金。
2. 让小草、马车和其他 KOL 以不同角色进入同一主题研判，而不是等权投票或作者特判。
3. 在每个合格主题内，按可解释规则选择 ETF、核心趋势股或两者组合表达。
4. 每个交易日对全部主题和全部现有持仓重判，满仓也不能跳过判断。
5. 保留现有 paper ledger、T+1、专有行情、宽回撤、流动性阻卖、成对换仓与原子提交脊柱。
6. 先做无业务权威的 v2 shadow，与现行 Book T 同输入比较；通过研究消费门和人工门后原地升级，不创建第二本趋势账或第二个 writer。

## Non-goals

- 不启用真实资金，不增加 broker submit 路径，也不改变 Book B。
- 不把任一 KOL 变成交易授权者，不把观点数量或作者知名度当作收益证据。
- 不用大模型计算成交价、手数、止损、账户余额或直接写账本。
- 不从中文标题、证据摘录或别名做猜测式 ticker 映射；无法解析即保持 `unresolved`。
- 不因马车满一个月自动卖出；其到期只撤销马车这一项支持，并触发主题重评。
- 不补跑历史业务 slot，不让 v1 与 v2 同时修改正式 Book T 账本。

## Confirmed Investment Design

### 1. Sources have roles, not votes

- **小草**：判断市场阶段、趋势风格、节奏和仓位推进条件。日内或交易日判断每天重新评估。
- **吕晓彤马车**：提供高优先级的短期主题池。默认有效上限为发布后约一个月；新马车替代、观点失效、证伪条件触发或市场趋势破坏时可提前退出支持窗口。
- **其他 KOL**：提供确认、冲突、证伪、新主题和具体催化。按观点自己的 horizon 管理；缺少 horizon 的观点快速衰减，不能无限续期。
- **市场事实**：决定趋势是否仍成立、标的是否可交易、表达是否有效，是最终资格边界。

冲突不是投票。例如“马车仍看 AI、小草认为当前节奏不适合新开仓”应表达为“方向仍有效、时点等待”，而不是把两票平均成一个分数。经核验的重大反例可使主题进入 `conflicted` 或 `invalidated`。

### 2. Theme eligibility precedes instrument choice

主题状态只有：

- `eligible`：方向、时点和市场验证允许进入组合竞争。
- `wait`：方向可保留，但时点、数据或确认不足，不开新仓。
- `conflicted`：关键证据互相冲突，等待消解；不得用高分补偿。
- `invalidated`：主题论点或市场结构已经失效。

KOL 可以把黄金、创新药等现行静态词表外主题提入候选，但只有经过标准主题解析、市场趋势验证、交易制度和组合约束后才可能成为 `eligible`。

### 3. ETF and stocks are expressions of one theme risk

- 主题宽泛、扩散度高、个股胜负难判断时优先 ETF。
- 存在清晰龙头，且相对强度、流动性、趋势完整性和成交可表达性均更好时选核心股。
- 只有 ETF 提供广度、个股提供可信超额表达且两者合计风险不超过一个主题槽时，才采用 ETF + 个股。
- 同一主题内多证券合并计量风险，不因证券数量增加主题预算。
- ETF 必须先有经 contract test 验证的 `instrument_type`、`lot_size`、`settlement_cycle`、行情与成交边界；元数据缺失时 fail closed。

### 4. Portfolio selection is hierarchical

不建立一个可相互补偿的总权重。选择顺序固定为：

1. 证据绑定、数据完整性和新鲜度；
2. 主题趋势资格；
3. KOL 的确认、冲突、提议或证伪角色；
4. ETF 与趋势股的表达质量；
5. 组合分散、流动性、换手成本和现有持仓适配。

任一上层硬门失败，不能靠下层高分恢复。通过同一层级的候选才使用确定性 tie-breaker 排序。

### 5. Daily reevaluation and switching

每天先形成完整主题研判，再评估现有主题和新候选。现有持仓可被 `hold / risk_exit / replace / wait`，不能因 `potential_slots <= 0` 跳过当日重判。

- 趋势破坏或经验证的观点失效可以触发退出。
- 普通名次波动不换仓。
- 挑战主题必须在连续两个有效评估中显著优于现有主题，且优势覆盖预计双边费用、流动性差异和风险变化，才形成 paired-switch 意图。
- 无可成交替代时保留现有趋势仓，除非独立风险退出规则已经触发。
- 马车到期只触发重新评估；若其他证据和市场趋势仍支持，主题可以继续持有。

## Deep Module Interfaces

### `build_trend_snapshot(as_of) -> TrendJudgmentSnapshot`

输入只包含已发布并经权威 receipt 绑定的 KOL 观点/评估、当前小草知识上下文、市场验证证据和明确 `as_of`。输出是冻结且可哈希的 Agent 判断 capsule。

每个主题至少包含：

- `theme_id`、`display_name`、`direction`、`confidence`；
- `effective_from`、`review_not_after`、`horizon_basis`；
- `xiaocao_timing` 与证据 ID；
- `mache_support`、`published_at`、`expires_not_after`、替代/失效关系；
- 其他 KOL 的 `confirmations / conflicts / falsifiers / proposals`；
- `market_validation`；
- `eligibility = eligible | wait | conflicted | invalidated`；
- 精确的 publication/viewpoint/evaluation/evidence identities；
- snapshot schema、输入摘要 hash、生成时间与 agent judgment version。

模块不解析成交、不生成手数、不修改账本。无法证明 publication 当前终态、horizon 或 evidence binding 时，相关证据不得升级主题资格。

### `resolve_theme_instruments(snapshot, catalog) -> ThemeInstrumentUniverse`

该模块把来源表述先映射到标准 `theme_id`，再连接小草 block/category、ETF catalog 和股票成分股。它输出每个主题下的 instrument candidates 及完整 provenance。

每个 instrument 至少包含：`code`、`name`、`instrument_type`、`theme_id`、`mapping_evidence`、`lot_size`、`settlement_cycle`、行情 contract 状态、流动性、趋势质量、相对强度、表达角色和不可交易原因。任何模糊映射、缺 ETF 交易制度或缺权威行情 contract 的项目保持 `unresolved / ineligible`，不做字符串猜测。

### `select_book_t(portfolio, snapshot, universe) -> BookTSelectionPlan`

该模块是确定性选择边界。它先评估现有主题，再选择最多三个主题槽位及其表达，输出：

- 保留、等待、新开、风险退出和成对替换意图；
- 每个主题的 ETF/股票/组合表达及槽内目标比例；
- 主题级预算、集中度、预计换手和费用；
- 两次评估的 challenger hysteresis 证据；
- 所有未选择候选的第一失败层级与原因；
- 输入 snapshot/universe/portfolio hashes。

Selection plan 不是 fill receipt。现有 paper execution 与 ledger writer 仍负责 T+1、开盘窗口、100 股或 instrument-specific lot、专有行情、资金、流动性和 exactly-once 提交。

## Failure Semantics

| Failure | Existing holdings | New buys | Proactive switches |
|---|---|---|---|
| Snapshot 缺失、过期或绑定失败 | 继续确定性风险管理 | 暂停 | 暂停 |
| KOL publication ledger 不可权威回读 | 继续确定性风险管理 | 暂停 | 暂停 |
| Theme mapping unresolved | 不影响其他已解析主题 | 该主题暂停 | 该主题暂停 |
| ETF metadata/行情 contract 未验证 | 股票表达可独立评估 | ETF 不合格 | 不切入 ETF |
| Market data/流动性不可用 | 按现行 fail-safe 保持/阻卖 | 暂停 | 暂停 |

不得静默回退到现行静态 `aligned / neutral / external` 策略。数据恢复后以同一日绑定重新生成计划，不重放不确定成交。

## Delivery Plan

### Phase 0 — Freeze contracts and control

- 冻结现行 Book T 作为 control，保留当前账本唯一 writer。
- 给 v2 定义独立、不可与正式 ledger 混淆的 snapshot、universe、selection-plan 和 simulated-fill artifacts。
- 建立现行 v1 fixtures，覆盖满仓早退、马车命中、paired switch、阻卖和行情缺失。

### Phase 1 — Judgment snapshot

- 从权威 publication status/readback 构建多 KOL current evidence view。
- 增加机器可判的 `effective_from / review_not_after / timing_status`，不在确定性代码解析中文 horizon。
- 建立 Agent 结构化输入、schema、binding receipt、freshness 和 conflict contract tests。

### Phase 2 — Theme and ETF resolution

- 为 Python client/cache 增加 ETF catalog 的 cache-first、限流封装与 contract tests。
- 建立标准主题 registry 和可审计 mapping；KOL 自然语言只能经受控 resolver 进入。
- 为所有可成交 instrument 加 `instrument_type / lot_size / settlement_cycle`，验证 ETF realtime、minute、daily/settlement 和 fill semantics。

### Phase 3 — Theme selection engine

- 将候选生成前置于 slot 计算，支持满仓每日重判。
- 实现层级资格、主题级集中度、ETF/股表达选择、组合预算和两次评估 hysteresis。
- 复用现有 paired-switch、T+1、blocked-sell、宽回撤和 ledger transaction seam，但 shadow 阶段只写模拟计划。

### Phase 4 — Shadow runner and research evidence

- v1 control 与 v2 shadow 使用同一冻结 market input；v2 不写正式 positions/account/trades。
- 记录主题决策、未选原因、模拟 fill、持有路径、ETF/股表达、换手和相对主题 beta。
- 将 protocol 登记到 `reference/experience/research_protocols.yaml`，通过 `trend_guards`/`trend_optimize` 生成 manifest 和 verdict。

### Phase 5 — Promotion and in-place cutover

- 工程 burn-in 通过后继续积累策略样本，直到满足策略验收地板。
- 只有研究消费门 PASS、人工审核和运行契约变更同时完成，才允许 v2 替换正式候选选择器。
- 切换时保持原 Book T 账户和唯一 writer；不补历史交易，不创建 Book T2。
- 首次权威运行 readback 通过后，删除/废弃作者专属 `kol_reference.py` 接入和 v1 静态方向逻辑。

## Research Acceptance Protocol

### Engineering burn-in

至少连续 20 个交易日。它只证明实现和账本边界健康，不证明策略收益。

硬性要求：

- v2 零正式 ledger/account mutation、零真实资金效果；
- snapshot、universe、selection plan、simulated fill 全部 hash-bound 且可重放；
- 满仓日也完成全量主题重判；
- 数据缺失时新开/主动换仓 fail closed，现有持仓风险管理不断；
- ETF metadata 与行情 contract 无未知制度假设；
- 同一主题多证券集中度合并正确；
- paired-switch、T+1、阻卖和 crash replay exactly-once fixtures 全绿。

### Strategy promotion sample floor

至少 60 个交易日并且至少 50 个有效主题决策；两者必须同时满足。样本不足只能是 `pending_observation`，不能判 PASS。

有效主题决策要求：当日 snapshot、市场输入、标的 universe、选择计划和可执行模拟 fill 全部完整；单纯重复持有且没有新的主题资格/表达/替换判断不计作独立有效决策。

### Primary comparisons

v2 必须与同日、同预算、同费用和同可交易输入的 v1 control 比较：

- 复合收益；
- 最大回撤与左尾损失；
- 换手和估计交易成本；
- 主题集中度及相关性集中；
- 相对匹配主题 beta 的超额收益；
- ETF、核心股和组合表达的条件性结果；
- 非牛市窗口留存与 walk-forward 保留度。

不以胜率、单个大赢家或未扣费的收益替代主指标。剔除最好主题或最好交易日后，结论不能反转为明显劣势；结果必须披露覆盖率、不可解析率和 ETF contract 排除率。

### Promotion decision

升级所需条件：

1. 工程 burn-in 全部通过；
2. 样本地板满足；
3. `trend_guards`/协议 manifest 给出可消费 PASS，且不是由单主题、单 KOL 或单表达工具驱动；
4. v2 在收益/回撤主目标上相对 v1 有明确、扣费后、walk-forward 保留的改善，换手和集中度没有不可接受恶化；
5. 所有变更通过 Research Consumption Gate；
6. 人工门批准更新 `docs/OPERATING_CONTRACT.md`、skill/automation contract 与正式 selector；
7. 有明确 rollback 到 v1 control 的 artifact 和 readback。

任何条件不满足时继续 shadow 或判 REJECTED；不得为了上线降低地板或把 KOL 信心当作统计证据。

## Acceptance Checklist

- [ ] 三个深模块接口及 schema 通过 interface-level contract tests。
- [ ] 多 KOL 来源角色、时效、冲突和 publication binding 可审计。
- [ ] 马车一个月上限与提前替代/失效可机器判定，且到期不机械卖出。
- [ ] 未解析主题和未知 ETF 制度 fail closed。
- [ ] 主题槽位正确合并 ETF/个股共同风险，总预算不超过 T 账户 30%，最多三个主题。
- [ ] 满仓时仍每日重判全部主题与 incumbents。
- [ ] 普通名次变化不换仓；challenger 连续两次显著胜出才允许 paired-switch。
- [ ] v2 shadow 与正式 Book T 账本完全隔离，并可同输入重放。
- [ ] 20 日工程 burn-in 和 60 日/50 决策策略地板分别报告，不混为“已验证”。
- [ ] Promotion 具有 protocol manifest、PASS、人工门、契约版本和 rollback readback。
- [ ] 升级原地替换 v1，不产生第二个 Book、writer 或历史业务补跑。

## Recommended Implementation Order

`01 snapshot schema/readback → 02 theme registry/resolver → 03 ETF contract → 04 selector → 05 shadow/evaluation → 06 promotion/deprecation`。Phase 1–3 完成前不得把 v2 结果接到正式 paper ledger；任何阶段发现当前规则需变更，先更新本 PRD 和 ADR，再实现。
