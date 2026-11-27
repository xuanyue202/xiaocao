# 2026-11-27 周度执行、因果与下一窗口复核

本周新增的有效观察是：APP 独立新买入已成交，Paper 同候选被自身性能暂停，T 影子时效再次失败后恢复一次按时接收，研究写盘曾因容量耗尽丢失一个窗口。它们分别解释执行能力、风险政策和研究样本完整性，不能合成 KOL 收益或下周就绪证明。

原 Automation `xiaocao-weekly-deep-review`、Thread `01a21cff-4c10-7b42-8a78-a5bcf9897242`；首命令唯一 retained PTY45284，20:33:53取得小时锁，原 run `20261127T123353-5836f2e55629` 于20:41:49终态。process0、确定性成功、历史姿态支持降级，源码未变。原计划120,797,502字节、SHA256 `57dd76aa3597d2a8b9cefcd892817405a6cb0f118490d0eec669d432e4f00104`，原样保存在 `output/research/weekly_audit_20261127/original-plan.json`。978项冻结输入及2339个不同KOL/执行引用核hash通过；字节完整不认证因果。本轮无第二weekly、APP查询/订单、历史回放或自动参数晋级。

## 当前交易、保护与会计

| 日期 | APP原业务 | 证据边界 |
|---|---|---|
| 11-23 | 1候选全COLD，0计划 | 真实资格无动作，旧UNKNOWN未全局拦截 |
| 11-24 | 4候选全COLD，其中2科创权限排除，0计划 | 资格和权限分别记录 |
| 11-25 | 9候选全COLD，其中3科创权限排除，0计划 | 不为样本恢复COLD |
| 11-26 | 8候选，300753 ACTIVE；BUY1800@17.08/6000087全成 | 唯一claim、原intent及同订单成交证明；其余7 COLD |
| 11-27 | 9候选全COLD，其中1科创权限排除；0新计划 | 原300753仍自有1800，不能把0新单误成空仓 |

26日原计划hash `4bb410f510030dd0fb1febf55ab0dc488d3ba2d5a31a45fe69c6b58739691ba0`、submit claim `book-b:2026-11-26:300753.XSHE:BUY:1:ea4ff4fd504543ff829fcda14351a805`。原native成功提示09:26:38.949证明柜台ACK；09:30:04原同单回读证明1800股、均价17.08、remaining0，两个时点不互代、不冒充撮合时间。提交前限价17.08、原市场门最新价17.00/跌停12.74，经济字段未后改；只读回执不能被模型成交替代。

26日九保护checkpoint均覆盖该lot，T+1可卖0；14:45价格15.44、暂计净收益率-9.62%仍为t1_blocked，不是漏卖。27日可卖1800，九checkpoint逐lot评估；早间软trailing延期且未触硬退出，14:25价格17.14无新SELL，14:45价格17.26、LIMIT_UP_DAY强持有，无新SELL intent。是否可以在早间卖出由原策略/当时事实决定，后续反弹不能证明先前一定正确；周末无回放卖点。

Paper 26日同ACTIVE候选被原Book A性能kill-switch factor0暂停，Paper账户风险REDUCED/.5是另一门。补充只读funded state原26日morning事件 `33a3f2e6530dcc6d2b2805d4deb8cf3222b1859c60443e6d4aa1774341a0de71` 的inputs.performance_factor=0.0，四variant均选中300753后为POLICY_OR_RISK_ZERO/effective_deploy_factor0，无模型订单。补充原state保存于 `output/research/weekly_audit_20261127/supplemental-funded-state.json`，原文件SHA `c1827d0b996fcc1b4c39ffe007ef009351012a31c856030592c0fbda63adf13e`；它不是固定AUTO输入，未据此改动策略。此日差异的直接原因是性能因子，不能泛化成账户权限或成交滑点。APP当日开放敞口、模型空仓，缺少同风险政策配对，既不证明KOL避损，也不授权移除性能传感器。

期末APP策略cash32376.36、markedNAV63462.36、净投入65845.40；暂计已实现-2721.96、浮盈338.92，当前自有300753/1800。相对上周markedNAV63123.44的端点变化+338.92仅是暂计标记差，47单实际费用、cash reserve和五日正式结算仍缺，最终PnL N/A。SQLite50条平衡分录不补会计来源。APP/statement/digest同observation `1574eacc69ec931e9e83b703e866e14e7f82eb8a0109dc06742318c8a4edf1d0`。Paper B123393.87/0仓，A119602.77/0仓，T28491.21/3仓/cash68.06/fresh估值，各自独立。

## 遗留状态传播与当前经济范围

旧6007019 SELL、6004811 SELL和无编号688028 BUY继续UNKNOWN/reconcile_only，禁止重发原claim、保留同代码BUY门。前两SELL经济核对任务关闭与服务终态不同。五晨用原首次CLAIMED/native来源及新鲜同账户完整持仓建立submit_origin_bound v2；过期未来BUY承诺0、旧代码未归属敞口0。26新BUY为新增自然正例，27无候选并非工程漏执行。300753已成交库存不因DAY到期归零。28040.81是旧最大可能承诺的历史边界，不是每日新现金、利润或资金划拨。

原11-11 94PASS、源码/部署及本周自然采用分别核验，同版本不重复工程APP测试；这不擦掉其他延期验收。反事实：保持旧UNKNOWN、提供新鲜现金/持仓/风险和独立合法候选，26原单确实成交；若去掉同代码、坏来源、T+1或真实风险门则会误放行。历史最终性缺证不等于当前全账户永久不可用，下周仍必须取得新的范围证明。

共因链：历史最终性与未来有效期混用（observed原v1）→无当前库存仍保留大额上界（observed）→后来查询template被当作首次submit来源的风险（observed原修复）→首次CLAIMED绑定、共享数量上界及原回归（observed）→为何原预检/评审未覆盖跨日无库存与可执行独立候选，是覆盖机制推断，更深治理原因unknown。规则、代码、回归、部署、自然准入与最终会计不能合并关闭。

## T时效复发：不同机制分开

本周23/24/27按时接收，25/26为BOOK_T_DATED_JUDGMENT_MISSING/producer exit2，无accepted/当日input/consumer。27请求09:32:08.027957、原截止09:34:08.027957、accepted09:33:09.796323/received_snapshot_only，producer/consumer0，正式账零写；累计25个非连续自然日、有效主题0/REJECTED。空主题判断和完整语义质量仍需证明，不能称市场没有主题，5/20连续门及60日/50有效主题门均未获晋级。

25日原工具09:31:22.010返回无输出，下一次poll09:37:34.323，相隔372.313秒无调用；请求09:32:08和截止09:34:08落在空档。没有六分钟sleep或长工具调用证据，无法区分推理、客户端暂停、平台队列等原因。它与上周17日Paper返回到APP启动约328秒空档同属无调用观察，不是已证明同一故障。

26日09:32:11已返回事件、09:32:20读取精确request，随后多轮查接口、来源及字段到09:33:39，09:34:11已过原截止。可见定位开销不同于25日未知空档。因果链：缺按时输入（observed）→未及时观察事件或收到后继续探索（各有原trace）→控制等待时接口/有界证据未预定位（inference，竞争解释为证据复杂）→前日复盘要求未转成稳定自然验收（observed复发）→代理预算/可发现性与平台深因unknown。27及时接收只反证接口必然不能在120秒工作，不关闭复发机制或语义不足。

原Paper/T owner在控制等待时准备精确接口、字段和完整有界输入；短yield接事件，在原120秒内真实review/accept，缺证明确失败，不续预算/补空主题。原runtime owner在再次无调用长空档时保存具体客户端/平台证据；当前未见足以证明且无原owner的独立源码缺陷，不另开执行writer。

## 存储事故与缺失样本

26日14:45原funded研究在atomic state write发生errno28；原state/event链有效，committed closing events0、原inputs/临时写未保存。原owner仅清理可再生uv缓存并做写入probe。27closing自然成功和本周计划成功说明各自时点可写，不能补26窗口或认证长期容量。本周初始free约644MiB、小额原子写成功；持续余量仍低。

5 Why：写入无空间（observed traceback）→卷容量耗尽（observed errno28/df）→容量治理未留持续余量（inference）→之前预检/复盘未防止本次缺样（observed结果，具体覆盖unknown）→增长来源/长期容量安排unknown。权限失败竞争解释被errno28反证，没有独立atomic-write代码缺陷证据。设备存储owner释放已确认可再生空间，下一高写窗口先查容量/有界原子写；不删用户模型、账本、会话或不可变原件，不重跑缺失研究。

## 系统级学习与实验效率

完整funded路径calendar证明至11-27，25个observed morning，仍缺10-28及26closing观察；control/no-KOL89465.49、M96377.57、open_limit90171.36，分别9/2/9个完整lot往返，当前open0。模型费率/未来窗口/APP权限和性能因子差异、不完整日频回撤均须保留。66组同入场A/B约+0.514pp只是退出条件诊断，不认证KOL或新选股alpha；每日NAV行不是独立交易。

投资上保留全机会/未成交/空槽，反弹不倒造早盘可执行性；金融上分已证现金、当前库存、风险单位净值和最终费用；系统上分唯一claim、原截止与支持降级；统计上不把工程漏执行当零收益；治理上不以准备接受、报告或测试数代替正式政策作用；效率上追踪窗口产生的有效独立观察。共同目标是准确观察收益与失败，不为增加样本强制交易。

11个来源工具候选均缺具体点时字段、缺值语义、consumer/fixture及baseline契约，保留一项跟进提案；沿用baseline_no_kol/current_bounded/kol_challenger三个稳定实验ID，工程恢复不另占alpha槽。来源事实按冻结作者归属消费，本轮未刷新外部事实或重写来源语义。KOL父级独立审查与逐项反馈记录于本轮计划/ledger，不自动晋级策略。

## 下一合法窗口与证据入口

下一日期预计11-30，仍由原晨trade_cal证明，不能凭周一假定交易日。原APP唯一runner先容量核验，09:20前读30项回复/处置/部署，取得当前cash/完整owned/风险及新dated v2，09:24会话复验；300753/1800按当时可卖、T+1、市场和原策略独立保护。支持截止min(原不超过120秒、更早owner、09:27:30)，理想09:28/最迟09:30柜台收单；历史claim不回放。

source owner保留21:30/06:30原准备及07:30采集门，先核原观点能否覆盖目标09:27:30、完整语义和独立接受；缺证立即blocked/deferred，不延寿、不让早盘补综合。Paper/T执行原120秒；费用/资金owner补逐单原件。下一原EOD实际消费本次30回复、核两业务和三post终态后的摘要；本周不预证这些未来结果。

- 唯一监督器：`output/live/auto/runs/20261127T123353-5836f2e55629/{manifest,terminal}.json`。
- 新BUY原archive：`output/live/book_b_live_execution/runs/history/2026-11-26-f2cf893307a3.json`；最新晨：`2026-11-27-71f4edfa71c9.json`。
- 期末原APP：`output/live/book_b_live_execution/runs/intraday/archive/2026-11-27-eod-20261127T152426057254+0800-4635.json`。
- 冻结输入与核验：`output/research/weekly_audit_20261127/{original-plan,frozen-hash-validation,raw-original-windows}.json`；raw windows绑定6份特定原session，单项7000字符上限，截断明确留证，不声称全文取证。
- 原EOD交接：`output/live/review_feedback/daily/2026-11-27.json`及冻结manifest内23份原daily；旧缺失/失败交接不回填。11-18原local session路径缺失；远端原turn有界读回保留截断，见 `first-T-failure-remote.json`，不声称全文取证。

本轮只提交周复盘、研究提案及反馈ledger，未改变策略、执行、安全、资金或原始账务。回滚只定向revert本轮报告/提案，保留原业务证据。
