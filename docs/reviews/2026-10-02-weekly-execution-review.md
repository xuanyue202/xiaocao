# 2026-10-02 周度执行证据复核

本轮周复盘的唯一业务入口于 20:32:08 返回 `hour_acquired`，原 PTY 66441 保留到 20:33:11 退出 0；没有第二次 weekly、生产器、交易检查点或 APP 动作。Automation ID 为 `xiaocao-weekly-deep-review`，原 Thread ID 为 `01a0fc99-7f2d-7502-b994-2e5a9491f3a7`，与原 manifest 一致。主链 succeeded，支持层因 posture 2026-07-03 过期而 degraded；平台没有可信 signed scheduler run token，环境绑定不能冒充密码学身份认证。

本周范围为 09-26 至 10-02，实际交易观测截至 09-30。当前 active repair owner 恰为本周任务 `xiaocao-weekly-deep-review / 01a0fc99-7f2d-7502-b994-2e5a9491f3a7`，负责此处的证据汇总修复和验收记录。既有 EOD/晨间/部署修复的作者及已完成结果保留；没有向另一任务发送指令、建立第二个账户写者或重放过期检查点。部署任务“部署小草修复并验收”的本次工具读回为 idle，不能再写为 active。

## 未决订单与窗口损失

| 精确订单 | 原提交与报价 | 当前可证明结果 | 当前影响 |
|---|---|---|---|
| 6007019，09-18 000572 SELL | 14:55:27，1800@4.31；当时 bid/队列缺证；距 14:57 约93秒 | 原事件 seq108 UNKNOWN，`NATIVE_HISTORICAL_STATUS_UNPROVEN`，已报、原成交0；当前持仓0不能证明原单终态 | 原单 reconcile_only；严格 EOD 和风险结算缺口保留，同股新 BUY 不得据零持仓放行 |
| 6004811，09-30 301382 SELL | 14:45:03 bid36.82、量22000；limit36.81；14:45:30 ACK，至14:57约11分30秒 | seq12 UNKNOWN，`NATIVE_HISTORICAL_EXACT_ORDER_NOT_UNIQUE`；10-01历史精确行0、成交0、持仓100；09-30当日精确行已报、0/100 | 剩余100股、旧单只精确对账；下一合法日要重读当前可卖/T+1/自有批次，不能沿旧claim补发 |

原 plan/hash：6007019 为 `book-b:2026-09-18:000572.XSHE:SELL:087c4339d890` / `655db71af12a810890d52018f3be520a838df9f303c279e9aec9e3c07db7571a`；6004811 为 `book-b:2026-09-30:301382.XSHE:SELL:9c1cb5e059e5` / `9e53b96a86360c3ae90a507a14701cdd17f608e5b2d28fb6a2b36126bcd3c401`。本轮重新验证事件/intent链，未修改原件。

09-18缓存逐分钟 trade：14:55 4.31、14:56 4.30、14:57–59 4.29、收盘4.31；09-30 301382 14:46 trade36.63、收盘36.33。它们支持“原限价随后失去竞争力”的解释，不能证明提交点队列、撮合、服务端处理或唯一未成交原因。没有原始bid时不能补造bid。ACK和zero fill不提供撤换单权限。

09-23 独立 plan `book-b:2026-09-23:000572.XSHE:SELL:087c4339d890` 的新订单 **6005091** 已由自有成交链证明1800股@4.01，限价4.00、对应独立claim/plan hash、后来持仓清零。它反驳“跨日同lot必须全局硬挡”的旧结论，但不关闭6007019。09-28洪兴200股订单6006397在14:45:48已filled；09-30两lot均有决策2/2，603042的6004842独立filled500@16.63。full-read路径的提前窗口、bid定价和独立lot覆盖已有这些自然样本；它们不能证明所有行情下成交，也不能证明降级路径。

**按机会损失排序：** 第一是下一合法09:25–09:30原冻结BUY的真实前置依赖和当前保护性/14:45 SELL窗口；第二是ACK后同订单剩余量、市场变化和窗口余量的持续回读；第三是旧UNKNOWN精确终态与结算。当前 native adapter仍无自动SELL replacement/窗口内成交控制器；不能用生硬重放弥补。`sellable_only`的独立Python lifecycle/probe/pre-submit/receipt链仍未实现、未隔离端到端验收，本轮没有冒充能力或启用。其缺口独立于full-read修复；本周合法交易日没有已证明的完整快照读取失败导致保护性SELL失去机会，10-01错误休市native读取另见下文。该工程缺口继续由上述唯一owner记录，使用前必须实施、隔离验证，再取得下一合法自然运行证明。

## 跨日 5 Why 与修复分层

1. **为何退出未完成？** 两笔柜台收单缺原订单终态/成交，仍有未卖份额。后续价格下降和09-18仅93秒窗口是可解释因素；服务端队列证据缺失，不能唯一归因。
2. **为何复盘不能用“已执行”结束？** 原native handoff ACK不是FILLED；现行端口缺窗口内fill controller，收盘之后的对账不可能恢复当时机会。完整所有lot决策与订单回执必须逐单核对。
3. **为何跨日影响新风险？** 严格结算缺日与风险证据是独立门。旧同股UNKNOWN不能terminalize；新日期当前可卖可以支持独立自有SELL。09-30 BUY最初阻断实际是 `LIVE_RISK_ACCOUNTING_CASH_RESERVE_RECONCILIATION_REQUIRED` / `PROVEN_SELL_GAP_INVALID`，不能笼统归为6007019全局阻挡。原1900@13.78计划后来09:32:20才柜台ACK6001214，晚于09:30目标，最终CANCELLED/零成交；没有已完成买入。
4. **为何早先修复仍有复发？** 09-28原EOD在UNKNOWN下错误写settlement；09-30原EOD又在新快照前停止。strict settlement admission和post-close只读观察必须分别修。`d1462c7`及集成部署已修改代码/通过专项；10-02休市skip未走交易日post-close projection，不能替代自然验收。09-30 paper shell在打印done后exit2/EOF，运行中源码变动解释仍须稳定源码的完整交易日自然shell证明；后来的bash -n为0不是原进程验收。
5. **为何周度汇总还会误报闭环？** 旧watch以“文件存在”判断09-28结算，并把休市EOD无settlement直接算漏结算。当前修复复用原hash-bound EOD的非终态admission证明，保留违规原件；只有精确日历证明的EOD免应结算，同日冲突EOD与缺EOD仍报缺口。它是只读报告修复，没有扩大交易、安全或资本门。

独立窄修另包括finalizer：新周报处于ignored output，过去普通 `git add` 会在report/ledger已写后失败。现在仅对确切生成的周报、change ledger和提案force-add，其余源码仍普通allowlist暂存；`git commit --only`限定本轮选定路径，保留用户原暂存区。隔离Git测试覆盖未暂存与已暂存的私人runtime/account文件，验证它们不会进入commit，原暂存内容仍保留。提交后实际tree核对还发现porcelain汇总的新提案目录会混入账本files_changed；现逐文件枚举，旧plan的dirty目录继续保护所有子文件，隔离测试验证tree与账本完全一致。本次只修正本轮唯一账本行的文件清单，没有重跑finalize或重复append。

## 结算与会计

09-28 settlement原文件 SHA `5d29b7bdf461506c2c9c649b049ca31391106267c365b95b613ad884bb2df23b`、内容hash `4ae42b85c90e45aa2b3fea1df97a4362badd9fbba2e29b1ee766a35d88e25044` 被其原EOD同hash UNKNOWN证明排除。后来的terminal不能追认旧结算。最后可采纳结算仍09-17 NAV29,410.33；本周缺有效结算为09-28/29/30，10-01/02由精确EOD日历证明休市，无应结算义务。更早历史缺口保留，不回填。

9/30 **15:22:21.651** dated APP mark：available cash49,739.04、SQLite cash49,746.44、marked NAV53,372.04、净投入54,462.04、已实现−846.21、浮动−236.39、未分类差额−7.40、累计PnL=N/A。预计未来退出费0.36仅 `estimated_plan_rate`，liquidation NAV53,371.68、risk unit NAV29,060.580891，与marked NAV分列。有未决计划，小于10元差异不能放行。下一交易日必须重新取得当前账户、资金、owned lot、风险与行情事实；本轮没有分类资本、重置高水位/暂停或改计划。

原accounting statement的observation `ba967385b9931775dfa018cc0ef0ae2873bf950ac44a2946c34ac9895824f12b`，journal head `486ab177e185e10cc1f80c917fc42b1a3e6cf993defff30d1121a33b94f70d1b`，funding head `059a0e8699f3c7d9ce3657a59927cc6b45e0ecfd95e583e30f8d2d178b655453`，ownership head `9d1eea6b5541c0cecfbf546ecf18bb09d5afd6be9a54ae6a48e6b0e06b2778be`；JSON/CSV均独立核对。paper B历史现金98,586.03、9/30退出费后权益140,227.87；paper T历史现金68.58、9/30权益29,399.64，10/02估值已stale。两者不能作为APP资本或当前NAV。现行累计A/B退出配对n50、B−A+0.5720pp只描述退出，不是本周或KOL收益。

## 原始轨迹与独立验证

原始轨迹审计覆盖09-18最初closing/EOD/morning，09-30最新受影响closing/EOD/morning，10-02自然EOD/morning，以及09-22失败turn。09-18首closing shell为14:51:31 launcher，14:55开始是当时约定窗口，不能反推调度器晚了四分钟。09-30raw rollout首shell为14:42:54 launcher，14:45:00合法进入；task-service的命令排序与raw rollout不一致时保留冲突。独立Spec review指出初始审计链接漏收09-22 EOD原件，随后补读原rollout和task-service：Thread `01a0c7f5-4ab0-7060-be48-9a8662706219`，turn `01a0c7f5-4dbd-7a90-9966-6222964a9285` 于15:12:17–15:12:35 failed，原error为 `unexpected status 403 Forbidden`（Codex responses）；15:23:18–15:23:28后续turn也403。15:35用户“？”后才进入完成业务turn，不能把晚shell直接归为调度延迟。精确scheduler dispatch仍unavailable；未重新调查用户自有Thu/Fri网络修复。

已独立读回部署的commit/push、实际测试日志及runtime manifest，不仅相信agent最终摘要。10-02各APP checkpoint NON_TRADING_DAY证明休市前置门自然生效；不证明交易日解锁、订单或完整EOD恢复。源码、离线测试、自然运行与外部订单终态各自留证。

本轮Standards/Spec独立review：Spec发现“仅closing休市回执会隐藏缺EOD”及“普通commit夹带原暂存文件”成立，已修复并加回归；09-22 EOD来源缺口已补原件。只读snapshot、inventory与最终语义refs独立校验；data doctor OK，策略协议3项PASS，shell syntax/diff检查PASS。最终复审、测试与提交SHA记录于周报告及本次Automation memory。下一自然weekly检验watch输出；下一合法交易日原EOD owner应验证fresh post-close projection、strict blocked/settled结果和完整稳定paper shell。所有未来验收仍pending。

业务后安全通知retry：2条旧变更notice仍 `pending_reconcile / PRIOR_NOTIFICATION_DELIVERY_UNPROVEN`，IDs `6ffce45aa60b798fe420e50a516e642891d7b5d7b5bd0613437b493ea1fbcc64` 与 `e59db7e03498b9fd07a0fa351f3d4c2c23a0c479ce45b40bb3ef1740f55ed50b`。程序保留不确定claim，没有盲重发。当前修复只读汇总/暂存，不改变策略或安全门，没有新增高影响变更notice。

完整私有证据保存在运行目录，未纳入源码commit：

- [原周命令terminal](/Users/xuanyue202/Documents/project/xiaocao/output/live/auto/runs/20261002T123209-305395c391c3/terminal.json)
- [原始任务命令、输出与失败turn](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261002/task_traces.json)
- [09-22 EOD原任务服务读回](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261002/sep22_eod_task_readback.json)
- [原watch与修正对照](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261002/watch_correction.json)
- [9/30会计JSON](/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting_reports/8e58602dce0e24050d28f4157476691f5c89b4477d1075bf54d86cd588ac738b.json)
- [会计CSV](/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/accounting_reports/f1eaa96312a9d0e37b15bae61ae9da26ec97bf992d012d068fba18934509d1ac.csv)
