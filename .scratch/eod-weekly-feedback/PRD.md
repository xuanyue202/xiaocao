# EOD 与 Weekly 的证据闭环

用户 2026-10-26 授权按已讨论思路优化，并把每日修复、可用结论交给 Weekly 深度归纳与优化。

- EOD 保留原来五个业务入口的恰好一次权限；不回放今天，不引入订单或 KOL 语义工作。
- 纸面 shell 不提前推最终摘要。两分支终态、现有 statement、research EOD、feedback 与执行复盘完成后，独立只读 closeout 验证原件与身份，再通过现有 durable claim 推 APP B 盈亏在首的摘要。
- 每日结构化交接：稳定 id、事实/推断、责任人、反证条件、下一步、修复/测试/自然运行证据分开。实验记录有效样本及可比性；零成交不能被称为策略改善。新设计只登记有限可证伪验收，不自动扫描任意聊天。
- Weekly 从现有内容寻址快照读取每日交接和原始引用，保留跨周未完成项，归纳重复原因、修复教训、实验和设计偏离。每一项都必须有回应和下一负责人；结果写现有周度 ledger，供下一 EOD 回读。
- 周度反馈只提供观察/研究输入，不扩大 AUTO_APPLIED 输入白名单，不改变原研究、资金和人工晋级门槛。周度“关闭”不能替代代码、测试、自然运行证明，更不能关闭 broker UNKNOWN 或会计缺口。
- 验证覆盖：缺终态/身份不符/原件 hash 改变时不发送；每日幂等；陈旧未决项不因换周消失；周度冻结证据可复核且不能漏回应。自然生产验收保留到下一个合法原始运行。

Baseline: 4895ba02dface87949428305ed8d3932f86f51d6。原 WIP：kronos_screen/HYPOTHESES.jsonl、src/xiaocao/live/app_test_window.py 及已有未跟踪文件，均不纳入改动。

实现与验证：增加只读 closeout 和不可变每日交接；后置三个原规范命令通过持久 claim 各执行一次并记录真实子进程终态，stdout 与诊断分离；不替换原 paper/APP runner。Weekly 冻结输入、强制逐项回应并写既有 ledger 回流。实际原件诊断发现 .orders.json sidecar 被错读为终态，已修正并保留 orphan 告警。

独立 Standards/Spec 两轮发现的 settled 终态、旧关闭遮蔽新事实、后置终态绑定、截断 inventory 绕过、混合流 JSON 问题均修正，最终两轴0未决。173项相关离线测试通过；wrapper 的无 venv 后备沿技能原约定使用当前解释器。自然 EOD/Weekly 尚未发生，不声称生产验收。今天原业务已结束，只做 legacy_read_only_handoff，无回放/补造回执/重复通知。

2026-10-26 用户要求全会话复核（30394b39 至 1a63d714，仅 c9d5123c/1a63d714 的21文件，排除合并的采集改动和原 WIP）。全量独立 Standards 初审0项，Spec发现2项P2：原日交接丢失会静默丢掉周度未决义务；research 正常 exit0/not_started 被拒。已补修：周度账本绑定原 daily receipt，缺失/损坏保留 id/owner/action 和 evidence_gap，并独立保留较早已证明的事实；不可用旧 verified 关闭新缺证事项。规范 not_started（报告已保存）与 NON_TRADING_DAY 保留确切 research_status，不虚构样本/利润，不放宽原 owner/终态/hash 校验。新增隔离回归覆盖删除、损坏、旧版状态、旧已验证/新再次未决、合法无动作和未知失败结果；不触碰原始业务证据，不补跑业务、不补造终态或重发消息。自然验收仍待后续合法原始 EOD/Weekly。

补修后独立 Standards/Spec 复核均0未决；230项相关离线测试通过（含真实无害子进程流隔离与原信号行为）。两个现有 Automation 已通过 API 更新、view 和 exact prompt/settings 回读，原调度/模型/项目/状态不变。自然运行验收未发生。
