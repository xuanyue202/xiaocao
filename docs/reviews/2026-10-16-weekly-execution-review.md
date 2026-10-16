# 2026-10-16 周度执行证据复核

本轮范围为10月10日至16日。唯一 weekly 命令在20:28:55取得小时门，原PTY 25427保留到20:30:29退出0；run为 `20261016T122855-08ee58870d32`。Automation精确为 `xiaocao-weekly-deep-review`，Thread为 `01a144af-a782-7090-8337-1a623f74f26a`，原lock与manifest一致。主链成功，posture有效期停在7月3日，支持层降级。没有第二次weekly、交易检查点、APP查询或订单动作；平台签名scheduler token仍不可得。

本轮唯一活跃修复负责人为上述weekly任务，负责下述只读取证修复、证据缺口与后续验收记录。10月15/16日EOD的代码修复已有独立提交；任务当前已结束，不能继续写作活跃修复者。原订单/账户writer和claim不转移，也没有向其他任务发送业务指令。

## 未决订单、原窗口与当前影响

| 原订单 | 原始价格/窗口 | 10月16日原EOD精确证据 | 当前边界 |
|---|---|---|---|
| 6007019，9月18日000572 SELL 1,800 | 限4.31，14:55:27收单，连续竞价剩约93秒；原bid/队列不足 | 15:15:47历史订单2行完整；15:15:51空成交表的异步响应/分页完整性未证 | UNKNOWN / reconcile_only；不能宣称全生命周期零成交或已撤 |
| 6004811，9月30日301382 SELL 100 | 限36.81，14:45:30收单；当时bid36.82、量22,000，连续竞价剩约11分30秒 | 15:15:35/39历史订单4行、成交1行均完整；目标仍已报/0，唯一成交属于另一单，目标持仓0 | UNKNOWN / reconcile_only；零持仓和其他委托成交不能关闭原claim |

两原plan/hash分别是 `book-b:2026-09-18:000572.XSHE:SELL:087c4339d890` / `655db71af12a810890d52018f3be520a838df9f303c279e9aec9e3c07db7571a`，以及 `book-b:2026-09-30:301382.XSHE:SELL:9c1cb5e059e5` / `9e53b96a86360c3ae90a507a14701cdd17f608e5b2d28fb6a2b36126bcd3c401`。原事件、意图、ownership与历史结算均保留。

9月30日原分钟证据的trade为14:45 36.84、14:46 36.63、14:50 36.59、收盘36.33。限价随后失去市场性是合理解释，缺少撮合/队列证据，不能当作唯一原因或撤换单授权。9月18日原bid未取得；过去归档中的4.30/4.29后续分钟价也不能补成提交时bid。

9月18日原closing账户有3个lot，仅1条decision，不能追认另两lot已评估。9月30日2/2有decision，另一单6004842确切FILLED 500@16.63，证明当时独立lot可继续。本周10月12日两份贝瑞基因lot均评估并分别FILLED（6005170/6005182）；10月16日closing为2/2 T+1，不能把不卖理解为漏评。

9月23日实际是14:43的precheck：独立新日期同lot SELL 6005091，1,800股@4.01、限4.00、独立plan/claim及后续持仓证明，反驳旧 `ae02340` 跨日同lot硬挡。`f7e1bdb` 的当前可卖分支与旧6007019身份分开，不能退回全局硬挡。该样本也不证明14:25准点，不能关闭旧订单。

10月16日原morning明确延期两笔旧SELL历史查询，独立BUY 6000056/6000057于09:27:19/22收单，09:30:04/08证明FILLED，分别建新1,100@8.15、龙江6,100@3.09。因此“旧单今天全局阻买”被实际成交反驳；缺结算仍严格保留，同代码BUY等原门不解除。

## 逐日缺口、失败任务与修复分层

原watch有3个EOD阻断日（10月13/15/16）和3个相应缺结算日；10月12/14另缺EOD，也无结算及日复盘，不能用前述三个日期代表全周完整覆盖。更早结算缺口继续保留，最近可采纳正式结算为9月17日；9月28日原件仍因原非终态EOD证据被排除。没有历史补结算。

10月12日原task于15:02:16开始，15:03:42报 `server_overloaded`；原shell于15:03:02启动、15:04:42返回−1，未到15:10业务门。10月14日原task于15:06:28–34因429重试耗尽失败，未发业务工具。10月16日原task15:03:43、paper15:04:00启动并在15:10进入业务，15:15:23退出0；APP原15:15:28进入、对账后退出2。不能把前两日缺口归为一般调度迟到，也不能靠后来的正常exit0覆盖它们。进程终止机制和精确dispatcher token仍缺证；未调查用户自有周四/周五网络修复。

本次重读最初9月18日closing/morning/EOD、9月30日新增未决单对应的closing/morning/EOD、9月23日独立退出及本周最新morning/closing/EOD的工具输出和归档。旧原始session路径在本机已不可用，使用10月2日保存的精确工具输出捕获，并通过官方read_thread重新取得9月18/30 closing及10月14失败turn；不称为本轮重读了已缺失的原始session文件。本周原始session仍可读并已保存hash。旧摘要“收盘任务完成”只说明handoff/回读结束，不证明SELL终态。

按真实交易机会和前置依赖排序：下一合法09:25–09:30 BUY与保护性/14:45 SELL优先；ACK后的剩余量和窗口内只读成交观察其次；历史终态与严格结算仍独立追踪。10月16日已自然验证竞价报价修复735db45及precheck单进程交接f1dc028；closing单进程APP→paper修复b657aab已改代码、专项通过，下一合法自然closing（预计10月19日，须日历通过）仍待验收。不能把今天旧launcher的及时运行当作新launcher已验证。

完整快照路径已有自然BUY/SELL样本；独立 `sellable_only` Python lifecycle/probe/pre-submit/receipt链及隔离端到端仍未实现。它不能越过账户绑定、登录、T+1、行情、owned-lot和claim门，也不能用于BUY/NAV/EOD。本周10月13日早间登录失败没有最小账户绑定证明，因此不能声称该降级口本可恢复那次SELL。该能力缺口与ACK后fill controller仍由本任务保留，未宣称修复、启用或自然验证；没有借旧单未知来免责，也没有新增委托/自动补单来演示。

## 跨日5 Why

1. **为什么EOD不能结算？** 两个原计划没有精确成交/撤销/拒绝终态，且两日根本缺EOD；严格门不能用当前零持仓代替原单证明。
2. **为什么原退出未闭环？** ACK只证明收单，后续价格可能使静态限价失去市场性；原端口缺SELL窗口内成交控制，服务队列原因仍未知。
3. **为什么曾影响后续机会？** 历史过宽的同lot/全局依赖与当前资金/风险门曾混在一起。9月23日独立成交和10月16日独立BUY分别反驳全局硬挡；当前仍保留同代码与不确定预留边界。
4. **为什么“代码修了”不等于解决？** 定价、覆盖、完整读取、报价年龄、任务交接、sellable-only与外部终态是不同能力。源码、测试、自然样本和原单终态必须分别验收；模型标签、后续exit0不能替代。
5. **为什么周报还可能漏审？** 原watch以EOD存在为缺日复盘检查的前提，恰好漏掉失败scheduled turn；纸面reader又把缺旧字段当成文件损坏。本轮以同字节回放和边界测试修复这两处取证缺陷，不改变交易与结算权限。

## 本轮只读修复与验证

`scripts/weekly_deep_review.py` 现对只有closing、没有EOD的日期保留缺日复盘，实际补出10月12/14。paper-policy-consumption/result v1缺少 `kol_decision.evaluated_at` 时，按原claim.date分组，既不填midnight也不借risk.asof冒充消费时钟；显式坏值/null继续拒绝，原receipt及terminal→claim hash核验继续保留。

42份原paper文件（21 claim+21 terminal）前后hash不变，原feedback文件库存digest仍匹配；现在42条可读，全部仍缺精确消费时钟。13个bought、8个no_buy只是本地terminal声明，不是APP成交或KOL收益证明。原固定plan及inventory不重建；修正投影作为hash-bound只读补充保存，原判定和原字节可复核。

92项weekly/固定KOL/研究证据专项通过，data_doctor OK、3项策略协议PASS、shell syntax及diff检查PASS。独立Standards/Spec复审发现显式null错误降级的问题，已修复并补边界验证；最终代码复审0遗留。最终报告复审还发现证据附录的三个自动建议与本周三个稳定实验并列，现周报仅展示已选槽位，原始未选建议保留在机器审计与独立观察报告，避免形成六项选择。无需运行APP工程试单。修复代码/测试及同字节回放已通过；下一次自然weekly输出仍需核对，不能用本轮函数回放冒充下一次调度验收。回滚为撤回本次只读修复提交，原运行和订单证据保持原样。

## 账户、资本与研究边界

原EOD15:15:54 observation的标记NAV57,232.81、净投入54,462.04、未分类现金11,383.36及PnL N/A保持当时原貌。用户随后在原EOD任务确认额外追加资金，原owner通过正式入口记入资本；本任务只导出一次既存16:03:28观测、未做新分类或APP读取。最新dated statement：现金39,924.17，marked NAV68,616.17，净投入65,845.40，已实现1,895.56、浮动875.21、累计2,770.77；预计退出费2.87，liquidation NAV68,613.30，单位化保守risk NAV31,161.381855。估计费用仍为 `estimated_plan_rate`；不是正式结算或新风险验收。

新观测 `2cc4f5c5c9b47b54112696459add389438d59af70a88e7fb28a06dd06d4863de`，journal `c58f73c96e594ebbd26ddea88baf0636fda00d8d243535f4807433dae601103b`，funding `5f2b9da1dff827418d06d24c8bea91c88021f152d7dddbeee3f0cbff0a49d423`；SQLite integrity=ok，27分录，原观测current验证通过，JSON/CSV独立hash已保存。新导出是固定计划之后的运营补充，不改变三方案固定研究证据、不把追加本金计入周收益。

paper B当前模型权益145,378.27、现金83,972.41；T新鲜权益28,956.30、现金87.19，均与APP分开。10月16日日复盘发现paper B全历史trade重放与canonical positions修复账有既存差额（cash0.33、SELL realized3,571.81）；当日现金方程和逐笔新增并未损坏。该历史映射仍缺原修复证据，不手改账本，也不把data_doctor OK扩张成全历史trade链闭合。

框架比较保留no-KOL/current/challenger三个原experiment_id，均未运行。研究快照、纸面闭lot及A/B退出配对是不同口径；本周2对A/B的B−A −4.0654pp不能推出KOL因果效果。16项笼统观测提议缺点时面板/字段/基线/OOS契约，归并到一个证据设计提案，无策略/参数/资本或正式KOL发布。

业务后变更通知安全retry仍有2条 `pending_reconcile / PRIOR_NOTIFICATION_DELIVERY_UNPROVEN`（6ffce45a…、e59db7e0…）；未盲重发。当前只读取证修复没有新增高影响APP变更通知。历史订单和晨间配送的另6项仍须各自精确核对，旧送达未知不因新通道成功而关闭。

## 决定性证据

- [原周命令终态](/Users/xuanyue202/Documents/project/xiaocao/output/live/auto/runs/20261016T122855-08ee58870d32/terminal.json)
- [原始及历史捕获的任务工具输出](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261016/task-traces.json)
- [原EOD与最新历史订单读回](/Users/xuanyue202/Documents/project/xiaocao/output/research/eod_audit_20261016/old-order-readback.json)
- [同字节watch修正](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261016/watch-correction.json)
- [42份paper兼容性复验](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261016/paper-consumption-compatibility.json)
- [16:03会计JSON/CSV和观测验证](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261016/accounting-verification.json)
- [固定输入hash核验](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261016/fixed-item-verification.json)
- [变更通知安全重试](/Users/xuanyue202/Documents/project/xiaocao/output/research/weekly_audit_20261016/change-notice-retry.json)
