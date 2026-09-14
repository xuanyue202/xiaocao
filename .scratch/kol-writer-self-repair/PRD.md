# KOL writer 首次正确构建、当前任务自修复与七日稳定收敛

Status: ready-for-agent

## Problem Statement

小时 KOL writer 已能在唯一远端写节点上接收轻量 handoff，并以 append-only 状态和 exact-once receipts 推进转录、语义分析、灰常亮发布、企微提醒、Book KOL-US、知识效果和 mailbox ack。但连续真实运行表明，它仍是“遇到一个坑、修一个坑”的事件级恢复，而不是能够证明同根因不再复发的系统级收敛。2026-08-07 的恢复暴露出三个语义链路耦合缺口：语义 bundle 没有 canonical builder，Ticket 03 的前置 validator 与 daily publication 的完整规范化不是同一个消费门，错误与 resume 也没有共享同一份稳定合约。

当时一个覆盖 129 个 segment、6 个 thesis 的 bundle 通过了早期检查，却携带后段不接受的 `longitudinal_projection.status="candidate"`。Bundle 还曾以旧结构为种子，存在 stale/duplicate market validation 污染风险。失败随后被 Netdisk 与 mailbox 包装成泛化异常，安全但可操作的精确原因丢失。Agent 只能增加诊断轮次、手填 repair revision，并在 exact resume 时分页扫描完整 pending mailbox。

2026-08-08 07:00 的另一次真实运行证明问题不只在 semantic/mailbox。Python 前 peer gate 用固定参数进行了两次 `list_threads` 和三次 `read_thread`，经历悬挂 readback 与一次 `Codex app-server is not available`，约四分半后才完成权威排重；它最终正确排除了一个列表快照为 active、实际 readback 已 idle 的候选，并且 writer 只运行一次，所以没有 exact-once 事故，但控制面尚未达到稳定、快速、可度量的收敛。

同一轮 writer 随后在 `/课程/路西法全套` 的 `lv_text_image` 小媒体适配器上，把 16 个历史图片版本全部记录为 `blocked_download_frame_missing`、`retryable=true`，最终 sweep 正常退出为 `status=completed, health=waiting`。`subscription_video` 是 `no_update`，远端 source-video bytes 为 0；因此这不是“禁止下载源视频”的正常结果，而是小媒体下载恢复契约缺陷被逐条降级成普通等待。将这 16 个旧版本隔离出队列可以停止无效工作，但不能替代对未来新图片仍可能命中的下载能力缺陷进行修复。

这条业务项最终通过修代码后继续原 mailbox claim 而全部完成，证明 exact-once 禁止重复业务效果，但不禁止修复后继续。它也证明 `Handoff完成`、provider wait、transcript ready 和进程 `status=completed` 都不是业务完成；只有报告或合法 low-density terminal、提醒合法终态、Book 合法终态、适用知识效果和 exact mailbox ack 全部具有 durable receipts，才能报告 `全部完成`。

用户需要 writer 在一次进程和当前 Agent 任务内尽可能完成“peer gate → 取件/来源扫描 → 语义输入 → 全量校验 → 灰常亮/提醒/Book/知识效果 → durable receipts → ack”。可恢复的代码、schema、环境、provider UI 合约和控制面问题必须由 Agent 做 5 Why、修复、回归和 exact resume；只有登录、短信、验证码、授权、用户独有事实，或无法通过权威 readback 核对的外部效果才能要求用户操作。整个改进不能削弱投资主张覆盖、唯一 writer、paper-only、发布顺序或 exact-once。交付目标不是一次测试通过，而是上线后连续七日证明内部故障在当前任务闭环、同根因不再以普通 waiting 复发、无需用户反复催促，writer 才算真正“跑顺”。

## Solution

先在所有来源 adapter、semantic、mailbox 和业务 terminal 之上建立统一的 `WriterProgress` 收敛合约。每个具体步骤仍由现有深模块拥有，orchestrator 只消费有限状态、精确 identity、credential-safe failure fingerprint 和唯一合法下一步。`retryability` 只描述技术上能否再次尝试，另以 `ownership=agent|provider|user|reconciliation` 决定谁负责推进；代码、schema、环境、provider DOM/下载契约和 task-service handler 故障永远不能因为 `retryable=true` 而失去当前任务所有权。

失败按 adapter、category、code、stage、失败 revision 与 provider-contract version 生成稳定 fingerprint，并在 append-only convergence ledger 中累计 same-sweep、consecutive-slot、first/last-seen 和 repair receipt。已知确定性内部错误在一次 bounded reconciliation 后直接成为 `repair_required`；普通 transport/provider timeout 可以进入带 deadline 与 attempt budget 的 `wait_until`，但预算耗尽或同 fingerprint 再次出现时必须升级。`repair_required` 会停止同一缺陷继续扇出到剩余 item，由当前 Agent 诊断、增加回归、修复、验证、提交/推送并沿原 claim 做窄续跑；它不是一个等待下个小时自行消失的终态。

对当前路西法小媒体积压同时做两条互不替代的处理。第一条是 eligibility migration：仅把审阅确认的历史 identity/version 标为 `work_eligible=false` 和 `pause_reason=historical_backlog_retired`，记录 cutoff/source-watermark 与集合摘要，保留所有 claim/receipt，不写 `completed_version_key`；内容生成新 version 后按正常 watermark 重新评估。第二条是 capability repair：修复并回归 `blocked_download_frame_missing` 的同 session、同 target、无重复 click 下载恢复，使一个未来 eligible 小媒体不会因旧 DOM/iframe 假设退化为普通等待。开发测试使用 fake DOM/transport，不下载真实小媒体或源视频。

Python 前 peer gate 保持在 Automation/control-plane，不增加 Python 锁、lease、heartbeat、fencing 或 stale takeover。它获得明确的阶段、attempt/elapsed 指标和 bounded retry budget：列表快照只用于发现候选，精确 `read_thread` 才能证明当前 task 或 peer；超时、app-server/handler 错误都保持业务副作用关闭并进入当前任务 `repair_required`。权威 readback 恢复后继续同一 gate；真实 peer 正确 no-op，陈旧 active 快照不能阻止唯一 writer，任何恢复序列最多启动一次 runner。

在结构化 semantic input 与所有业务消费者之间建立一个深模块 seam。该模块对普通调用者只暴露一个主 interface：`build_validated_bundle(request, semantic_draft) -> ValidatedBundleReceipt`。另保留 `validate_existing_bundle(request, existing_bundle)`，但只允许 legacy migration、已有 claim reconciliation 和只读 audit 使用，不能成为新事件的 builder。

`request` 提供本次 message/handoff、immutable transcript、已有 claim-extraction contract、当前 market evidence 和已审阅作者/来源元数据。`semantic_draft` 只表达 Agent 从当前 evidence 得出的 thesis、覆盖判断、读者文案、current-decision、knowledge 和 Book 判断，并引用 request 已给出的 segment identity；它不能填写 evidence identity、schema/hash、业务 idempotency key、第二套 segment ID 或两份 market projection。模块内部完成 canonicalization、共享枚举、cross-field projection、完整 validation、artifact hash 和 typed errors，调用者不再学习接近完整 bundle 的嵌套实现。

成功结果先以原子写持久化 `ValidatedBundleReceipt`，再允许任何 publication prepare 或 side-effect claim。Receipt 绑定 message/content SHA、handoff/media identity、transcript SHA、claim-extraction contract version、market-evidence SHA、canonical bundle SHA、bundle schema version 和 validator version。Resume 只有在全部绑定完全相同时复用 receipt 和 bundle；receipt 之前崩溃的语义尝试记录为 abandoned attempt，不能伪称“已读取一次”。

Bundle SHA 只证明 artifact integrity，绝不作为 publication、reminder、Book 或 ack 的业务 identity。任何已经开始或完成的 v1 item 继续使用其持久化 source/message identity 和 idempotency keys；v2 builder 只能更换待验证 artifact，不能派生第二套外部效果 identity。新 v2 item 仍通过既有业务 identity constructors 建立 claims，schema/validator version 与 bundle SHA 不进入业务 key。

Exact resume 正式扩展 writer 的 mailbox port：普通 drain 继续使用 list，已知 message 的 `resume-mailbox` 必须使用 `get_mailbox_message(message_id, expected_content_sha256)`，不得以全量 list 兜底。该操作同步进入 writer skill、Automation prompt、client adapter 与 fake adapter tests；若 exact get 不可用，状态是 control-plane `repair_required`，且不读取其他 pending message、不推进业务。

Code/contract resume 不再把 `HEAD` 本身当作修复证明。仓库提供一个 repair-validation interface：它读取原 durable wait，解析当前完整 commit，按 error category/stage 运行仓库拥有的 targeted test profile，并在测试、lineage 与目标分支 readback 通过后原子写 `RepairValidationReceipt`。Receipt 绑定 message/content SHA、原 error code/stage、failure revision、repair revision、测试 profile/结果 hash。`resume-mailbox` 自动解析 `HEAD` 并自动发现完全匹配的 receipt；provider deadline wait 继续沿用现有同 revision 到期续跑规则，不要求虚构代码修复。

Runner 的每一步统一返回 `continue | structured_input | wait_until | repair_required | reconcile_required | user_action_required | terminal`。原进程自动消费 `continue`；其余结果各有固定必需字段和唯一合法下一步。指标仅记录 Python runner 可观测的 stdin/stdout bytes、structured requests、stage time、resume/list/get/reconciliation counts、semantic attempts、validated-artifact reuse、failure fingerprints 与 repair closure；控制面另记录 credential-safe gate attempts/elapsed/result，不声称掌握 Codex 侧所有工具输出或真实 token。

交付分为代码验收与七日生产稳定窗口两个 gate。代码合并只证明 deterministic fixtures、targeted regressions、完整 KOL suite 和 exact-once crash matrix 通过；首个生产 rollout 即开始七个连续自然日（至少 50 个实际 scheduled writer slots）的收敛验收，目标是在该窗口内关闭全部已知 fingerprint，并在最后连续三日/至少 20 slots 无修复后同根因复发。整个窗口的硬门槛是零 active-active、零重复外部效果、零 source-video bytes、零内部故障请求用户、零已知 fingerprint 退化为无 owner 的 generic waiting。窗口内允许出现新的内部 fault，但必须在当前任务取得 owner、形成 repair receipt 并关闭；P0 安全事故或修复后同根因复发使本次验收失败，重新 rollout 后再计。认证/CAPTCHA、用户主动停用、外部 provider 明确 deadline 和正常 no-op 不伪装成内部稳定性失败，但必须独立计数。

## User Stories

1. As a KOL 用户, I want 新内容在一个 writer 任务内尽可能走到全部业务终态, so that 我不需要逐轮催促系统继续。
2. As a KOL 用户, I want `Handoff完成` 与 `全部完成` 始终明确区分, so that 消息送达不会被误报为报告、提醒、Book、知识和 ack 均已完成。
3. As a KOL 用户, I want 可恢复的内部错误由当前 Agent 修好后继续原 claim, so that 普通代码或 schema 缺陷不会转嫁给我。
4. As a KOL 用户, I want 已完成事件的 publication、reminder、Book 和 ack 永不重放, so that 修复与 schema 升级不会制造重复效果。
5. As a 家庭组合成员, I want 灰常亮完整报告仍先于适用提醒和 Book KOL-US, so that 简短入口不会替代权威读者内容。
6. As a Book KOL-US 研究者, I want repair resume 保持既有 paper-only identity, so that 新 bundle artifact 不会产生第二次模拟动作或进入真实资金路径。
7. As a sole writer 运营者, I want 每个新 bundle 只来自当前 request、transcript 和 market evidence, so that 旧 bundle 的过期字段不会污染新事件。
8. As a sole writer 运营者, I want 所有消费者使用同一个完整 validator, so that bundle 不会“前面通过、后面失败”。
9. As a sole writer 运营者, I want 既有 segment identity 算法成为唯一实现, so that builder 不会生成第二套 evidence references。
10. As a sole writer 运营者, I want validated artifact 在任何 claim 前原子持久化, so that 崩溃恢复可以安全复用并准确统计语义读取。
11. As a repair Agent, I want typed category/code/stage 从产生点无损到 mailbox readback, so that 我能直接定位问题且不泄漏凭证或任意 exception 文本。
12. As a repair Agent, I want exact resume 只读取已知 message, so that 修一个 item 不会扫描或推进无关积压。
13. As a repair Agent, I want code resume 同时验证 commit lineage 和 targeted test receipt, so that 无关 commit 不会被误当作有效修复。
14. As a repair Agent, I want runner 返回有限且明确的下一步状态, so that 自动推进、等待、核对和用户动作没有临场解释空间。
15. As an auditor, I want bundle artifact identity 与外部业务 identity 分离, so that v1/v2 migration 可以证明零重复效果。
16. As an auditor, I want 每个最终 ack 能追到完整 receipt 链, so that `全部完成` 可以独立核验。
17. As a system maintainer, I want runner 指标绑定 message 与 transcript identity, so that 性能改善、abandoned attempt 和 replay reuse 可以量化。
18. As a future KOL adapter maintainer, I want 复用同一 semantic module interface, so that 来源差异只影响证据取得而不改变语义与发布门。
19. As a KOL 用户, I want 连续七日看到 writer 无需我催促即可闭环内部故障, so that “修好了”有运行证据而不是一次性口头结论。
20. As a KOL 用户, I want 禁止源视频与允许小媒体证据下载明确分开, so that 合规边界不会掩盖真实下载缺陷。
21. As a repair Agent, I want retryability 与 failure ownership 分开, so that `retryable=true` 不会把代码或 provider UI 合约缺陷丢给下一轮。
22. As a repair Agent, I want 同一 failure fingerprint 自动累计并升级, so that 16 个同根因 item 不会被当成 16 个普通等待。
23. As a sole writer 运营者, I want peer gate 在 readback 抖动后仍以权威状态收敛且最多启动一次 runner, so that 陈旧 active 快照既不制造重复 writer 也不永久阻塞业务。
24. As a sole writer 运营者, I want 历史版本退休与下载能力修复各有独立 receipt, so that 清空积压不会被误报成修复了未来新材料。
25. As an auditor, I want 每个 repair_required 有 fingerprint、owner、revision、tests 和 closure receipt, so that 同根因复发可以自动判定为回归。
26. As a maintainer, I want 七日 soak 具有最小样本量、排除项和重置规则, so that “跑顺”是可验收的 SLO。

## Implementation Decisions

- 本 feature 改变唯一远端 writer 的控制面门禁收敛、来源 adapter failure ownership、小媒体 eligibility/capability repair、post-handoff 语义构建、校验、artifact receipt、typed diagnostics、exact resume、自动推进、输出、度量与七日 soak。来源视频捕获/字节传输、调度归属、灰常亮产品语义和交易策略语义保持不变。
- `WriterProgress` 是所有 adapter 与业务阶段的最高业务 seam。它至少绑定 item/message identity、stage、status、ownership、retryability、failure fingerprint、attempt budget、deadline/next action 和既有 claim/receipt 摘要；调用者不能从 exception 文本或 `status=completed` 推断下一步。
- Failure fingerprint 只使用 credential-safe canonical fields：adapter、category、code、stage、failure revision 与 provider-contract version。文件名、标题、URL、cookie、私有 query 和任意 exception 文本不进入 fingerprint。Ledger 记录 first/last seen、same-sweep count、consecutive scheduled slots、current owner、repair receipt 与 closure。
- 已知 code/schema/environment/provider-contract/control-plane handler 错误属于 `ownership=agent`。确定性 code 在 bounded reconciliation 后直接返回 `repair_required`；transport/provider timeout 只有在明确 attempt budget 与 timezone-aware deadline 内才可 `wait_until`。预算耗尽、同 identity 次轮复发或同 fingerprint 在一个 sweep 扇出到多个 item 时升级并停止继续扇出。
- `repair_required` 必须含 failure fingerprint、受影响 identity/version 集合摘要、原 claim/receipt 状态、failure revision、targeted test profile 和合法窄 resume surface。它不能被 sweep 聚合器降级为 `health=waiting` 后遗忘；当前 Agent task 保持 owner 直到 matching RepairValidationReceipt 与 exact continuation/closure。
- 路西法历史小媒体 retirement 是显式 migration，不是 terminal success。仅对审阅集合写 `work_eligible=false`、`pause_reason=historical_backlog_retired`、source watermark/cutoff、identity-version digest 和 migration receipt；保留 claim/receipt，不写完成状态，新 version 重新按正常 eligibility 评估。
- `blocked_download_frame_missing` capability repair 必须保留同 session/同 provider target/不重放 click 的 exact-once 约束；frame/DOM 不匹配时先做 bounded read-only rebinding，无法恢复则进入 agent-owned repair，不逐个扫描剩余同类 item。修复必须覆盖 future eligible image/PDF，不以当前历史集合被 retirement 作为通过证据。
- Peer gate 固定参数和当前 task 排除规则继续复用，但不再视为完整收敛。控制面阶段固定为 discover candidates → identify current task → authoritative peer readback → pass/no-op/repair；列表 active 只是候选，readback idle/completed 是权威。每次 gate 记录 attempts、elapsed、failure code 和 terminal result，且任何重试序列的 runner start count ≤ 1。
- 深模块的主 interface 固定为 `build_validated_bundle(request, semantic_draft) -> ValidatedBundleReceipt`。Canonicalization、枚举、cross-field 投影、hash、完整 validator、原子 artifact 写入和 typed errors 都属于 implementation，不能泄漏给调用者。
- `validate_existing_bundle` 是第二个、受限 interface，只用于 v1 pending reconciliation、v1 completed read-only audit 和显式 legacy migration。新 v2 事件调用它属于契约错误；它不得创建或修改业务 claims。
- `request` 是模块拥有的 typed value，至少包含 message/content SHA、handoff/media identity、transcript path/SHA、claim-extraction request、market-evidence receipt 及作者/来源元数据。所有 identity 和 evidence bindings 由 runner 构造，Agent 不能在 `semantic_draft` 覆盖。
- `semantic_draft` 只承载 Agent 判断：完整 thesis inventory、独立 coverage audit、entity resolution、reader copy、content value、current-decision、longitudinal decision、knowledge routing 和 Book intent。它通过 request 中已有的 segment IDs 引用 evidence，不能携带 prior bundle、业务 keys、schema version、hash 或独立填写兼容 market projections。
- Builder 调用并校验现有 claim-extraction segment 算法。Evidence segment ID 继续由 extraction contract version、evidence SHA、offset 和 segment SHA 唯一生成；builder 不实现第二套。Thesis/claim semantic IDs 可以在模块内部 canonicalize，但必须保留对既有 segment IDs 的双向覆盖关系。
- 允许的 decision、knowledge、content、longitudinal 和 evaluation 状态集中在 semantic module implementation。完整 preflight 顺序固定为：request/handoff identity → evidence path/SHA → claim inventory/coverage → reader/content routing → canonical market validation → longitudinal projection → publication copy → knowledge branch → Book intent → canonical artifact。
- `market_validation` 与 `market_outlook.current_validation` 从同一个 canonical market object 投影。`semantic_draft` 只提供一次事实判断；不一致的 legacy 输入在 `validate_existing_bundle` 中以稳定 typed error 失败。
- `ValidatedBundleReceipt` 在任何 publication prepare、side-effect claim、灰常亮写、提醒、Book、知识写入或 ack 前原子落盘。它至少绑定 message/content SHA、handoff/media identity、transcript SHA、extraction contract version、market-evidence SHA、bundle path/SHA、bundle schema version 和 validator version，并带自身 canonical hash。
- Resume 只有在 receipt 自身 hash 有效、bundle artifact 仍匹配且所有 request bindings 完全相同时直接复用。Receipt 缺失、损坏或 binding 改变时重新进入 semantic build；receipt 前中断记录 `semantic_attempt_abandoned`，receipt 后复用记录 `validated_bundle_reused`。
- “每 transcript SHA 只读一次”定义为：同一 message/content、transcript、extraction contract 和 market-evidence binding 的成功 validated artifact 只完整读取一次。Receipt 前崩溃可以产生新的 attempt，但必须单独计数，不能被隐藏为一次成功读取。
- Artifact integrity 与 business idempotency 完全分离。Bundle SHA、schema version、validator version 和字段排序不得进入 publication、reminder、Book 或 ack identity，除非某个既有业务 contract 本来就以精确 reader-copy hash 作为自身 identity；即使如此也只使用该业务字段的 hash，不使用整个 bundle SHA。
- v1 pending migration：保留所有已持久化 claim/idempotency keys；先读取原 claims/receipts，再用 `validate_existing_bundle` 或新 builder 修复 artifact；后续效果只能沿原 identity 继续。任何 identity 无法对齐都进入 `reconcile_required`。
- v1 completed migration：authoritative receipts 直接终止业务恢复，禁止 rebuild、republish、resend、Book replay 或 re-ack；schema validation只能作只读 audit，且不得写新业务事件。
- v2 new item：通过新 builder 创建 validated receipt；外部 claims 继续由既有 source/message identity constructors 产生。新 schema 不能创建第二套 publication-event、recipient、Book 或 ack identity 算法。
- Mailbox port 正式增加 `get_mailbox_message(message_id, expected_content_sha256)`。Full drain 只用 list；exact resume 只用 get。Writer skill、Automation prompt、production adapter、in-memory adapter 和 contract tests 必须同批更新。Get 不可用或返回 changed/missing/acked target 时 fail closed，不以 full list 兜底。
- `resume-mailbox` 的 `repair_revision` 变为可选并默认解析当前完整 `HEAD`，但 HEAD 只提供便捷输入。Code/contract wait 必须存在完全匹配的 `RepairValidationReceipt`；无关 commit、未推送 commit、lineage 回退、错误 target 或失败测试都不能授权 resume。
- Repair-validation interface 读取原 durable wait，根据 category/stage 选择仓库拥有的 targeted test profile并亲自运行；调用者不能声明“测试已通过”。成功 receipt 绑定 message/content SHA、原 error code/stage、failure revision、resolved repair revision、目标分支 readback、test profile、command/result hash 和生成时间，并以原子写完成。
- Provider `wait_until` 不需要 repair receipt。它继续使用现有规则：同 revision 仅在 durable、timezone-aware `next_poll_not_before` 已到期时续跑；deadline 前不 poll，不创建新 revision。
- Progress interface 只能返回七种结果：
  - `continue`：必须含 item identity、completed stage 和 next stage；只允许无新输入、无未来 deadline、无未核对副作用的单调幂等 transition，原进程立即继续。
  - `structured_input`：必须含 request kind/id、schema version、immutable bindings、response field；runner 在同一 stdin 等待一行结构化 artifact reference。
  - `wait_until`：必须含 credential-safe category/code/stage 和 timezone-aware deadline；deadline 前不得继续该 item。
  - `repair_required`：必须含 `ownership=agent`、failure fingerprint、failure/repair revision、affected-set digest、claim/receipt summary、targeted test profile 和 narrow resume surface；在 matching repair receipt 前不得变回普通 wait 或 terminal。
  - `reconcile_required`：必须含 effect kind、claim/idempotency identity、权威 readback operation 和禁止 retry 标志；只有 reconciliation 结果能决定下一 transition。
  - `user_action_required`：必须含真正 user-only 的 action、blocker identity 和 dedup key；内部 code/schema/tool/control-plane fault 不得进入此状态。
  - `terminal`：必须含 content terminal、灰常亮 terminal、提醒 terminal、Book terminal、适用 knowledge terminal、ack status 和 new external effect count。
- Typed error contract 至少包含 `category`、`error_code`、`stage`、`safe_reason`、`retryability` 和可选字段定位。`safe_reason` 只能来自 allowlist；原 exception 文本、URL、cookie/token、私有 query、任意秘密路径和 bundle 内容不得进入 ledger/readback/stdout。
- 每个外部 side effect 保留既有 pre-action claim 和 durable receipt。`reconcile_required` 必须先查询精确 publication、recipient、Book 或 ack identity；只有权威零效果证明才能允许原动作，已有或不确定效果不得重发。
- Ack 仍是最后一个 mailbox terminal。只有报告或合法 low-density terminal、提醒合法终态、Book 合法终态和适用知识效果都具有 exact receipts 时，才能 ack 并报告 `全部完成`。
- Runner 只记录自身可观测指标：`runner_stdout_chars`、`runner_stdin_chars`、`structured_request_count`、`stage_elapsed_ms`、`process_resume_count`、`mailbox_list_count`、`mailbox_get_count`、`side_effect_reconciliation_count`、`semantic_attempt_count`、`semantic_attempt_abandoned_count`、`validated_bundle_reuse_count` 和 `bundle_first_pass_valid`。这些指标不进入业务 hash 或决策。
- Convergence metrics 另记录 `failure_fingerprint_count`、`repair_required_count`、`repair_closed_count`、`same_root_regression_count`、`generic_wait_count`、`user_dependency_for_internal_fault_count`、`peer_gate_attempt_count`、`peer_gate_elapsed_ms` 和 `runner_start_count`。生产报告只输出聚合与安全 code，不输出私有 item 内容。
- 七日稳定窗口至少覆盖 50 个 scheduled slots，并在最后连续三日/至少 20 slots 无修复后同根因复发。硬门槛为 active-active、duplicate publication/reminder/Book/ack、source-video bytes、内部故障 user_action 和无 owner 的 same-root recurrence 全部为 0；已知 diagnostic 被降为 generic waiting 也必须为 0。性能目标为 peer gate P95 ≤ 60 秒、clean/no-update sweep P95 ≤ 5 分钟；超标进入改进项，但不能用跳过权威 readback 或减少安全验证换取。
- Before/after baseline 在实现改动前冻结为版本化、credential-free fixture corpus 与结果 JSON。Corpus 至少覆盖 20 个确定性场景，并包含一个与 129-segment/6-thesis 规模相当但不含真实私有内容的 fixture。P95 不能由单条 fixture 得出。
- `bundle_first_pass_valid >= 95%` 的分母只包含 schema 上应合法的 semantic drafts；故意非法的 negative fixtures 单独统计。Schema error 的目标是 runner 在本地 validation stage 60 秒内返回稳定安全代码，不包含 Agent 修复时间或 provider wait。
- 本地可控 transcript-ready 到 ack 目标为 median ≤ 8 分钟、P95 ≤ 15 分钟，provider waits 单独统计。CI 使用固定 corpus 比较 before/after；真实生产 P95 作为上线后前 30 个 eligible item 的观察目标，不阻塞代码合并，也不允许用单条成功样本宣称达成。
- 非必要 runner I/O 字符数相对冻结 baseline 降低至少 60%。该目标不声称覆盖 Codex 侧全部工具输出或真实 token；未来若 runtime 暴露可靠 token，再新增独立指标。
- 已落地的 PTY noncanonical/no-echo 大行读取、nested handoff routing、completed terminal replay、provider deadline resume 和 Python 前 peer gate 固定参数只增加回归，不重写、不分叉。Peer coordination 仍属于 Automation/control-plane，不在 Python 内增加锁、lease 或 takeover；本 feature 只补其 bounded convergence、权威状态序列、metrics 与故障回放验收。
- 代码交付使用小步、可回滚 commit。保留用户 WIP，不 reset、clean、自动 stash 或覆盖；验证后 fetch/reconcile 并正常 push，禁止 force-push。运行 ledgers、credentials、transcripts、bundle artifacts 和 account state 不进入 Git。

## Testing Decisions

- 最高业务测试 seam 是小时 writer 的 `WriterProgress`/orchestrator interface：来源 adapter、exact mailbox message、semantic module、validated receipt、fake 灰常亮/Relay/Book/knowledge adapters 和 ack 都通过这一状态边界推进；进程内推进与进程退出后的窄 resume 也通过同一 seam 验证。Python 前 peer gate 是唯一独立的控制面 seam，因为它必须在 runner 存在前完成。
- 测试只断言 interface 的可观察结果：progress result、artifact/receipt hashes、append-only events、fake adapter calls、business identities、ack、metrics 和 replay。不要断言私有 helper、内部类布局或临时变量。
- Semantic module 使用 interface-level contract tests。相同 request/draft 生成相同 canonical bundle bytes/SHA 和 receipt bindings；改变业务语义会改变 artifact SHA，改变输出目录或观测时间不会改变业务 payload。
- 首个 red test 使用 `longitudinal_projection.status="candidate"`，断言在 validated receipt、publication prepare/claim、灰常亮、提醒、Book、知识和 ack 之前返回稳定 error code。
- 第二个 red test 从底层产生 credential-safe typed failure，断言 category/code/stage 经 Netdisk、runner progress、mailbox wait/readback 完全保真，同时原 exception、URL、secret path 和 bundle body 均不出现。
- 第三个 red test 在最高 adapter seam 复放 `blocked_download_frame_missing`：同一个 bounded recovery 失败后结果必须是 agent-owned `repair_required`，而不是 `retryable waiting`；同 fingerprint 不得继续扇出到 16 个 item，现有 claim 不变且没有第二次 provider click。
- 历史 retirement 测试断言只改变审阅 identity/version 的 eligibility/pause metadata，保留 claim/receipt 且不写 `completed_version_key`；同一 version 不再 pending，新 version 仍可按 watermark 进入。Capability repair 测试独立运行，不能因 retirement 后 pending=0 而通过。
- Peer gate 使用 deterministic fake task-service 序列做控制面契约回放：第一次 list 悬挂、第二次 list 返回两个 active 候选、current readback 一次 app-server failure 后恢复、另一候选权威 idle。断言 gate 最终通过、mailbox 在通过前零调用、runner 恰好启动一次；持续失败、真实 peer、陈旧 active snapshot 分别断言 repair/no-op/pass。
- Segment identity 测试使用现有 extraction request 生成的 segment IDs，断言 builder 只验证和引用它们；第二套算法、offset/SHA 不匹配或未知 segment ID 均 fail closed。
- Validated receipt crash matrix覆盖：读取前、读取中、bundle 写后 receipt 前、receipt 原子写后、publication claim 后。Receipt 前重启产生显式 abandoned attempt；receipt 后重启复用 bundle 且 semantic full-read count 不增加。
- v1/v2 migration 必须覆盖三类：v1 pending 保留原 claims 并继续；v1 completed 零新业务 event；v2 new 正常创建一次 claims。三类都断言 bundle SHA 变化不会单独改变 publication/reminder/Book/ack identity。
- Exact mailbox tests 断言 resume 只调用一次 get 且不调用 list；missing、changed、acked、connector unavailable 均在 processor 前失败。Full drain 继续分页 list，保持 attempted-message 去重。
- Repair proof tests 覆盖：省略 revision 自动解析 HEAD、合法 matching receipt、无 receipt、receipt target/error/test hash 不匹配、失败 profile、未推送 revision、非 commit、lineage 回退和无关 commit。Provider wait 到期续跑证明不需要 repair receipt。
- Progress state 表驱动测试验证七种结果的必需字段、允许 transition 和禁止 transition；任何有 claim/uncertain effect 的 item 不能返回 `continue`，agent-owned deterministic failure 不能返回无限期 `wait_until`。
- Exact-once 测试在 publication、每个 recipient、Book、knowledge 和 ack 后分别注入中断。恢复后每个 fake external identity 最多一次，已有 receipt 不回退，最后 ack 恰好一次。
- Runner I/O 测试断言普通输出不含 transcript、完整 bundle、完整 segment list 或全历史；大于终端 canonical-buffer 的 JSON line 继续通过现有 noncanonical/no-echo stdin 读取，不能新增第二套协议。
- Regression 必须保留现有 nested cloud-handoff snapshot route、completed receipt 的空 events 兼容、provider wait deadline/same-revision 语义、active-peer no-op 和 2026-08-07 completed fixture 的零 replay。
- 所有测试使用 in-memory/fake adapters 和 deterministic clock；禁止真实 mailbox、灰常亮、企微、Book、OpenCLI、Automation 或 source-video 副作用。
- 七日稳定窗口从 credential-safe runtime ledger 生成每日 convergence report 与第七日验收报告。报告列出 scheduled/clean/business slots、gate latency、fingerprint/repair/closure、repair 后 same-root regression、generic waits、user dependencies 和 duplicate-effect audit；排除项必须带稳定 code 与数量，不能手工删除失败 slot。

### Acceptance Checklist

- [ ] 主 interface 只有 build-validated 与受限 legacy validation；普通调用者不能手填完整 bundle implementation。
- [ ] Builder 复用唯一 segment identity，且所有 consumers 调用同一完整 validator。
- [ ] Invalid longitudinal/market/coverage/reader/knowledge/Book draft 在任何 claim 前失败。
- [ ] Validated artifact receipt 原子、hash-bound、可在 crash 后精确复用。
- [ ] Bundle SHA 与所有外部 business identities 分离，v1 pending/completed 与 v2 new migration tests 全绿。
- [ ] Exact resume 使用 get、不使用 list；skill、Automation prompt、production/fake adapters 同步。
- [ ] Code/contract resume 同时需要 resolved revision 与 matching repair-validation receipt；provider wait 保留既有 deadline 规则。
- [ ] 七种 progress result（含 `repair_required`）均有固定字段和 transition tests，不存在 generic waiting fallback。
- [ ] `blocked_download_frame_missing` 从普通 waiting 升级为 agent-owned repair，停止同 fingerprint 扇出，并有未来 eligible 小媒体回归。
- [ ] 16 个历史版本以审计 migration 退休，claim/receipt/完成状态不被伪造，且 capability repair 独立验收。
- [ ] Peer gate 悬挂/app-server/stale-active 回放最终满足业务前 fail-closed 与 runner start count ≤ 1。
- [ ] Typed diagnostics 端到端保真且 credential-safe。
- [ ] Publication → reminder/Book/knowledge → ack 顺序与 exact-once crash matrix 全绿。
- [ ] 既有 PTY、routing、terminal replay、provider deadline 和 peer-gate 回归全绿。
- [ ] 冻结 baseline corpus 后，targeted KOL suites、完整 KOL suite、compile 与 whitespace checks 通过；指标报告不夸大 runner 之外的可观测范围。
- [ ] 首个 rollout 后七日/至少 50 slots 达到零事故硬门槛，全部已知 fingerprint 已关闭，最后连续三日/至少 20 slots 无修复后同根因复发。

## Out of Scope

- 不补跑、重新分析、重新发布、重新提醒、重新写 Book、重新写知识或再次 ack 已经 `全部完成` 的 2026-08-07 事件。
- 不新增第二个 writer、Python 全局锁、lease、heartbeat、fencing、stale takeover、active-active 或自动故障转移。
- 不改变 Automation RRULE、启用状态、writer 所有权或创建重复 Automation。为 exact get 同步现有 prompt/interface 属于本 feature；调度变更不属于。
- 不重写已落地的 PTY stdin、cloud-handoff routing、provider wait/deadline、terminal replay 或 peer gate 固定参数；补 peer gate 收敛状态与回放不属于重写。
- 不改变本地微信采集、视频捕获、压缩、百度上传、大媒体传输或 remote handoff envelope 的所有权 seam。
- 不下载源视频，不使用 Computer Use 或真实 provider 副作用作为开发测试。`lv_text_image` 的小图片/PDF evidence 能力属于本 feature，但仅用 fake transport/fixture 开发验证；生产窄续跑仍受 exact claim/receipt 约束。
- 不改变投资决策主张可见性、覆盖审计、灰常亮权威读者终端、提醒资格、KOL-US paper-only、持仓建议或真实资金权限。
- 不把 durable knowledge 提升到 `authority>0`，不自动修改策略参数、posture、交易规则或研究裁决。
- 不用旧 bundle 作为新 builder 输入；legacy bundle 只进入受限 validation/reconciliation interface。
- 不声称 Python runner 能测量 Codex 侧全部工具输出或真实 token。

## Further Notes

- 2026-08-08 评审快照中，当前 checkout、`origin/main` 与交接基线一致；开始实现时必须重新 read back。当前 PRD 是用户 WIP，除非后续明确授权，不随实现外的无关文件一起提交。
- 当前运行已经具备并必须保留：精确 provider wait/deadline resume、TTY 大行输入修复、handoff routing/terminal replay 修复、正确 peer gate 参数，以及 2026-08-07 事件全部 closure。它们是回归前提，不是本 feature 待重新设计的模块。
- 2026-08-08 07:00 回放已只读验证：2 次 list、3 次 read、gate 通过后 1 次 runner；`lv_text_image` 为 16 个相同 `blocked_download_frame_missing`，`subscription_video=no_update`，source-video bytes=0，sweep health=waiting。该 fixture 是新增 control-plane 与 failure-ownership 验收的事实基线，不得补跑。
- 深模块 interface 是本次评审后的设计 SSOT。删除该模块时，canonicalization、枚举、projection、validation、receipt、hash 与 typed error 复杂度应重新散落到多个 caller；这说明模块具有足够 depth，而不是浅 wrapper。
- Correctness 优先于 95%、8/15 分钟和 60% I/O 降幅。任一性能目标都不能削弱 claim coverage、reader safety、market validation、knowledge authority、business identity migration 或 exact-once。
- 推荐实现顺序：冻结历史回放/baseline 与三个 red tests → `WriterProgress`/failure ownership/convergence ledger → 路西法 eligibility migration 与 capability repair → peer-gate failure replay/metrics → semantic module/validated receipt → v1/v2 identity migration → exact mailbox get → repair-validation receipt → compact runner I/O/metrics → 首个生产 rollout 即开始七日稳定窗口。每阶段保持可独立回滚。
