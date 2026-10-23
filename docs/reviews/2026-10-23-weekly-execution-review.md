# 2026-10-23 周度执行复核

本轮唯一 weekly 入口于北京时间20:35:08取得小时锁，原PTY 30129于20:37:15终止。
Automation为`xiaocao-weekly-deep-review`，原thread为`01a168c1-d63c-7b40-8c8d-12afb5612db3`；锁和supervisor manifest均绑定该身份。原shell exit0，但监督器正确记录deterministic failed：第七个命令构建计划exit1，计划文件没有生成。不得把日志中的plan ready当作完成。

本轮只有一个活跃修复owner：上述weekly任务。未重跑weekly、任何历史交易检查点或APP查询。

## 原运行失败与只读接续

`scripts/book_b_live_intraday.py`本周在archive旁新增`.wait.json`，用于持久化原120秒预算。
weekly的通配符把它当成终态回执，严格trade_date/phase检查因而抛出
`WEEKLY_EXECUTION_CHECKPOINT_INVALID`；weekly shell未检查该退出码，仍打印ready。
原始失败回执、日志、125份已保存研究输入和manifest保留不变。

接续没有再次调用`build_plan`或周度业务命令：只用原内容寻址研究输入重算观察报告，
另外捕获有真实接续时点的本地KOL只读库存。恢复审阅计划保存在
`output/research/weekly_audit_20261023/recovered-review-plan.json`，明确原计划未生成、
原flywheel/sweep及KOL中间值未持久化、无AUTO_APPLIED权限；不把新库存回填为原运行成功。

5 Why：周报不能完成←原计划未落盘←等待契约被终态glob接纳←同目录新产物没有类型分界←
旧测试只覆盖终态回执；同时shell忽略失败掩盖了错误。修复仅区分保留hash的等待契约、
对孤立等待契约报告缺终态、继续严格拒绝坏的正式回执，并让计划失败传出非零退出码。
两项隔离回归先红后绿，相关50项通过；独立Standards/Spec初审均0发现。
当前原始failed状态不修改；未来原weekly自然运行仍须证明修复已被采用。

## 旧SELL：原单状态、经济处置与机会损失分别核验

重读9月18/30原closing工具输出和精确archive、原event/intent/ownership记录；
首日morning/EOD及9月23独立退出使用此前保存的原始工具输出捕获，原session文件缺失如实保留。
本轮再次通过官方read_thread取得两份首日closing、10月22失败closing/EOD、
10月23最新morning/closing；不是只接受先前agent结论。
捕获路径和逐条工具输出在`output/research/weekly_audit_20261023/official-*.json`，
此前原始捕获在`output/research/weekly_audit_20261016/task-traces.json`。

| 原单 | 精确提交/回读 | 独立后续处置 | 当前解释 |
|---|---|---|---|
| 9月18日海马6007019 | 14:55:32 ACK，1800股，限4.31；至15:16:27仍无证明成交。原bid缺证，不能用后来的分钟价补齐。连续竞价剩约88秒，不能把集合竞价时间算作可新发普通SELL窗口。 | 9月23日另一个plan/claim的6005091成交1800@4.01、限4.00；发生于14:43 precheck，不能据此证明14:25准点。 | 原单UNKNOWN/reconcile_only；后单不替原单证明撤销、拒绝或成交。 |
| 9月30日新瀚6004811 | 14:45:37 ACK，100股，限36.81；原14:45:03买一36.82/22000股。14:48、14:50及EOD仍零证明成交。后续分钟价格下行只能支持失去市场性的可能解释，不能证明撮合/队列根因。 | 10月8日独立6001466成交100@35.59。 | 原单仍UNKNOWN；独立清仓与原单终态不同。 |

9月18日closing原account有3个lot却只有1条decision；不能接受“任务完成”作为另外两lot已评估。
9月30日2/2已评估，独立6004842成交500@16.63；本周最新closing为1/1且当日T+1。
历史全lot修复、买一低一档定价与14:45窗口前移是不同修复，均不终结旧订单。
旧`ae02340`同lot跨日硬挡被9月23独立清仓反驳，不能复装；现行独立BUY也不把旧历史查询作为全局前置。
10月23日6000059于09:27:20 ACK，09:30:04精确成交7700@4.18，反驳“旧单仍全局阻买”。

10月23日原EOD三表快照`ecd2802b…`及eod_review`024618c8…`重新证明原lot后续独立完整处置、
当前同账户相应代码无持仓/订单成交矛盾，两个历史经济任务均`economically_closed`、active_plan_ids为空。
对应4个buy/disposal ownership hash明确列在review中；原UNKNOWN、claim和同代码BUY fence保持。
这是10月21修复的自然EOD验收，不是正式结算或原单终态。

跨日5 Why：原SELL未闭环←ACK不是成交←限价后续可能失去市场性、原窗口内读回不足←
过去把原单未知与新交易/全lot/结算依赖混用←早期复盘接受exit0和总结。
定价与时段修复、独立当前可卖出口、原单终态和会计最终性必须分别验证。
现行代码有原120秒预算内只读成交观察，不自动撤换单；不再沿用上周“端口尚未实现”的结论。

## 本周缺运行与解析失败

watch记录10月19/20/21历史EOD阻断及相应缺结算，10月22有closing而缺EOD/日复盘，
10月23完成observed/accounting_pending但无正式结算。最新可消费结算仍9月17日；
9月28旧问题结算不能被后来清仓追认。没有补跑或补写历史结算。

官方10月22 EOD task `01a16267-a82a-79b3-8196-b9746beb61c1`终态failed，
`Selected model is at capacity`；原shell命令exit−1、286058ms、未产生业务slot/supervisor archive。
同日closing task `01a16253-f8cc-74e3-91ea-1b29b90d83f4`也因容量错误失败，
但其原launcher已在14:45:00.319进入APP并exit2：三次读取耗尽，
`NATIVE_QUERY_ORDER_FILLED_QUANTITY_MALFORMED`。因此两条链不能统称没有启动或调度迟到。
平台内部容量根因和可信scheduler dispatch token未提供；不调查用户自有网络修复。

10月22日开盘6001284于09:36:31收单，1200股限13.04，原行情13.05、规则best_bid_minus_tick；
原09:37/09:46/09:55回读仍ACK/零成交，14:25:05才观察FILLED1200@13.04。
14:25是本地观察时刻，不能冒称实际撮合时刻。6001953另单成交500@30.188。
14:25自有lot已空，14:45坏格发生时不证明还有未卖数量，更不能虚构可追回损失。
原失败archive没有坏格/三表原件，尚不能区分OCR、源行变化与解析原因；
10月23完整读取正常只是后来通过，不能声称永久根因已修复。

本轮定位到可独立修复的取证出口：broker已保留账户绑定后的脱敏readback与行，
CLI异常分支却只归档错误字符串。现在把这些已有材料写到独立`read_failures`目录，
blocked回执只带路径和SHA-256，stdout/stderr不打印坏格；文件标记`diagnostic_only`，
不成为有效snapshot，不改原错误、重试或资金/结算权限。磁盘取证失败另记错误类型，
不覆盖原业务失败。两项新隔离回归先红后绿，intraday CLI相关30项通过。
此修复保留未来复现材料，不能补造10月22原始坏格，也不宣称解析根因已解决。

5 Why：10月22无EOD←原turn容量失败且命令中断←未到业务slot←平台容量错误←
服务内部原因未知；有原terminal/slot才能推翻缺运行判断。
解析故障←成交数量未证←原始坏格未存←采集与解析原因不能区分←缺复现原件；
保持严格数量门，不以关键词归一或放宽置信度修复未知根因。

## 本周端口验收分层

统一生命周期实现`b2868a98`已合入当前main，完整账户与classified sellable_only均已实现。
10月22日17:16:51真实只读验收账户绑定proven、orders2、sellable_only、cash/NAV=null，
owned_lot_count=0；离线5190项通过。当前源文件与验收范围核对，不重建所谓缺失端口。
10月23原各监控有非零新lot，但均T+1，没有新SELL；因此专用降级口的自然非零可卖/新委托
验收仍未发生。全账户自然成交、零lot只读验收、离线链测试不能互相替代。
下一原合法运行重新观察，不发试单或重放过去时点。

六个既有Automation通过API追加读取指引并逐个view，运行模型、推理档、调度、
状态、项目和目录与修改前逐字段一致；仓库镜像同步。技能同步故障证据等级与
weekly失败接续边界。没有新调度或额外业务写者。

## 会计、风险及下次运行

按10月23日15:15:26.462的原SQLite观测：APP标记NAV65085.93、净投入65845.40、
预计退出费3.27、退出费后65082.66；未分类现金11253.45、33笔实际费用待核，
最终已实现/浮动/累计PnL均N/A。原计划费率暂估−1295.25/+535.78只作估计。
资金head `5f2b9da1…`、journal `1a9d59f7…`、observation `ba299fe4…`均绑定原报告。
当前风险NAV下界29557.908167不能当作最终收益，原高点/暂停不重置。
5 Why：正式封账未写←现金及逐笔费用门未过←未分类和原生费用缺证←现有collector未提供←
接收接口不能生成外部来源。不可从现金差额反推本金或费用。
独立下一晨BUY使用当时新鲜可用现金、owned marks、资金与风险门；不能复用本报告数值。
paper A/B/T与APP及四个研究账户分别保留。本轮只读修复没有改变策略、资金权限、安全门或订单。

## 关键原件

- [原weekly终态](/Users/xuanyue202/Documents/project/xiaocao/output/live/auto/runs/20261023T123508-0eb56f647b9f/terminal.json)
- [修正后只读watch](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261023/execution-watch.json)
- [首末任务工具输出](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261023/official-first-latest-turns.json)
- [失败scheduled turn](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261023/official-failed-turns.json)
- [原EOD](/Users/xuanyue202/Documents/project/xiaocao/output/live/book_b_live_execution/runs/intraday/archive/2026-10-23-eod-20261023T151522401184+0800-5982.json)
- [本周部署只读验收](/Users/xuanyue202/Documents/project/xiaocao/output/deployment/app-b-unified-lifecycle-20261022/native-readonly-acceptance.json)
