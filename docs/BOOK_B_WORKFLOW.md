# Book B 统一操作流程与迭代

适用：APP 服务端仿真短线主线、同上游的 paper B，以及独立短线研究。规则权威是
[Operating Contract](OPERATING_CONTRACT.md) §1c/§2a/§4/§6/§10；本文说明如何操作、解释与验证。
Book T 是趋势系统，不参与本页的短线优劣排名。

## 一条流程，分别兑现账户结果

| 阶段 | 唯一职责 | 完成证据 |
|---|---|---|
| morning producer | 捕获全部原候选、确定性模式证据、原始 ★E，提交不可变批次 | 原 checkpoint、raw/canonical hash、run/strategy/日期 |
| KOL writer | 发布完整来源语义与观点当前性 | LiangHui 观点/评估/关系及来源验证 |
| 当前适用性判断 | 把合格观点与原冻结、当前条件、对应账户风险核对 | 原请求、明确映射、独立审核、已发布且有效 policy |
| 共同解释模块 | 确定性消费 policy，给每只冻结候选留下选择原因与限制 | `book-b-adjudication.v1` |
| APP / paper 各自执行 | 本账户整手分配、行情与风险门、委托/模型成交、账本 | APP 原计划与柜台成交；paper 独立消费 claim/result |
| 盘后与周复盘 | 对照预期、选择、订单、成交、费用与收益，登记待证假设 | 原件绑定的比较报告与 research manifest |

APP 与 paper 在原来的调用点使用 `book_b_workflow.adjudicate_book_b`。
共同解释模块不增加模型、全局等待或第二个语义 writer。各账户仍消费自己的有效 policy；
只有确实核对了两账户，才允许 `runtime=both`。APP 不等待 paper 成交。

当前 APP 的分配输入是冻结 ★E；paper 保留原有合格排名候补池，整手表达不足时可选后备。
这项适配差异写在 `allocation_adapter` 中。相同策略指纹只证明共同选择阶段相同，
不证明资金、手数、最终股票集合、价格、订单或收益相同。

## 一次判断必须能解释“不动”

`judgment.outcome` 描述消费到的正式政策：`published_no_change` / `published_changed`、
缺失/过期等降级，或 `invalid`。它不证明本次请求已经完成。

`support_attempt.outcome` 单独描述当前请求：

- `completed_no_change/changed`：作者与独立审核者都绑定原 `morning_request_sha256`，
  原 rendezvous 的有效政策 hash 一致，完成时间在原预算内。
- `reused_valid_policy`：复用之前已验证且仍有效的判断。
- `timed_out/deferred/blocked`：支持层实际结果；不能写成“模型判断不买”。
- `valid_policy_request_completion_unproved`、`not_observed`：存在可消费政策或解释，
  但本请求完成证据不足。旧格式政策仍按原时效与权限消费。
- `not_required`：原冻结为空，不虚构一次语义审核。

每只候选记录原模式状态、消费状态、★E 是否选中、选择原因、KOL 缩放/跳过和执行限制。
被选中只到分配入口；账户风险归零、行情失败、未成交及 UNKNOWN 各有后续原回执。
`morning_pipeline_status.py` 比较两端共同阶段，terminal notice 展示紧凑原因；原生产者 ready
不等于任一消费者执行成功。历史回执缺新字段时显示 unproved，不补写旧结果。

## 模式映射与完成回执

收到原冻结评审请求后，warm worker 在决策中填写 `morning_request_sha256` 和
`mode_mappings`。每项保存 `source_report_id`、`source_term`、`target_mode`、
`classification=exact|conditional|unmapped`、`conditions`、
`current_applicability=supported|uncertain|contradicted`、`reason`。

`unmapped` 的 target 为 null；conditional 必须保存条件。映射覆盖本轮实际涉及模式的
观点，空列表表示本轮没有模式映射事项，须由原覆盖复核支持。复核者在原 review 中绑定
同一请求 hash 并写 `mode_mapping_reviewed=true`。有 v2 模式跟随时，必须有同 source report、
同精确 target、当前 supported 的映射；自然语言条件仍由独立主审逐项验证。

“红盘起爆”不能靠字符串包含自动变成“标杆短线起爆”。无法证实同义或条件尚未满足就
保留 unmapped/uncertain；没有正式覆盖的 COLD 仍按默认门。新字段是来源忠实性审计，
不会新增代码、恢复 UNKNOWN 或放宽资金与交易门。

## 收益比较：选择对照必须回答同一个问题

| 对照 | 用途 | 必须保留的分母 |
|---|---|---|
| paper B / APP B | 识别准备、价格、受理、成交与退出执行差异 | 原共同批次、未执行、未成交、人工协助、独立费用/现金流 |
| Book A / B | 比较固定 next-close 与 B 退出 | 同代码/日期/价/量、双方已平仓；排除数 |
| ★KP / ★B / ★M / ★E | 检验选择精度与参与度 | 全原始选择、不可成交/缺标签、空槽、版本 |
| no-KOL / current bounded / challenger | 判断 KOL 的增量 | 同冻结、同预算和风险、全部未执行样本、费用、样本外 |

本轮读回：截至 2026-10-21，57 对严格同进场退出中 B−A 均值 +0.6287pp，去掉最大正差后
+0.3736pp；支持保留 B 退出。988 行历史候选的 ★E 条件单笔标签较好，但共同完整日期里
只在 37/50 日有选择。固定三个名义槽的算术指标会改变排序，提示优先研究空仓机会成本。
这些标签未模拟重叠持仓/T+1/现金，不能直接复利成资金收益或证明永久晋级。
57 对样本均保存了窗口成交标签，未出现 fallback；这仍是模型标签，未经原窗口、hash 与
时钟逐笔复核。比较报告分别披露配对及各模式的窗口、fallback、重试代理和未知依据，
保留全样本描述性收益，不把有标签升级成 APP 可实现收益证明。

复算命令（无网络、无交易、先检查数据健康；只写独立研究报告与输入副本）：

```bash
PYTHONPATH=src .venv/bin/python scripts/research_shortline_comparison.py --start 2026-06-01 --end YYYY-MM-DD
```

输出 `output/research/shortline_comparisons/`，保存输入 hash、剔除日期与成熟性限制。
`--end` 是观察窗口，不是证明历史标签当时已知。APP 净收益仍以 §6 独立费用/资金核验为准。

## APP 收益改进的落地顺序

统一回执是归因与维护基础，不应被记作已经提高收益。当前证据支持以下顺序：

| 优先项 | 已观察事实 | APP 动作与验收 |
|---|---|---|
| 保留 B 退出并兑现执行 | 57 对同进场样本 B 比固定次日收盘 A 平均高 0.6287 个百分点；并非每笔占优 | 保留共用退出规则；逐次核对合法触发、提交、成交，修复当前仍复现的执行故障，不整体延迟卖出 |
| 消除可避免的未执行 | 历史 paper 独有的 8 组中，5 组准备/解锁受阻、1 组行情缺证；另 2 组是未成交与合法价格跳过 | 验收现有准备、原请求恢复及竞价报价修复；分别统计工程阻断、合法跳过、未成交。原历史利润不能称可追回利润 |
| 核查买入价格机制 | 10/14—10/21 的 6 个共同已成交组，APP 均价都等于各自委托限价，平均较 paper 模型价高 49.43bp | 先核查仿真撮合和原委托/行情时钟，区分撮合规则、限价设置、提交延迟和 paper 模型差异；没有因果证明前不调低限价、不把固定滑点写入参数 |
| 研究 COLD 与参与度 | ★E 条件标签较好，但 50 个共同完整日期中仅 37 日选中 | 先在隔离 paper 中固定资金、退出、费用、T+1 和失败处理，只改变一个研究变量；APP 继续当前默认门 |

价格验证必须保留未成交订单分母：只看已成交样本会高估低限价方案。若以后注册限价
对照，要同时衡量成交后的价格、未成交机会成本、费用后资金收益和回撤，不能只以成交率
或“买得更便宜”判优。6 组限价等于成交价是待解释现象，不证明服务端永远按限价撮合。
新价格/参与度方案依次占用现有研究实验槽，避免同时换选股、入场和退出造成归因混乱。

## 可持续的 paper 研究

原 paper B 消费时自动把原冻结的四种选择标记、无 KOL/当前有界模式选择、policy、
候选行 hash 与 checkpoint 保存到 `output/research/shortline_experiments/<date>/`。
记录失败只降级研究观测；不会延迟或阻断正式交易。空选择也保存，未知 flag 保持 null。
同内容重复写幂等；已终态日期不重跑来补数据。

这层是 **选择证据采集**。`selection_recorded_outcomes_pending` 不代表另一个资金账户
已经运行，更不代表收益已成熟。`paper_record --pick vb_star/kp_star/mode_star` 仍会写
canonical B 账户，不能用多次运行它制造隔离试验。

新资金组合实验使用独立 account/positions/trades/claim/fees/NAV 根，复用生产分配、成交、
退出规则，按 [研究协议](../reference/experience/research_protocols.yaml) 的
`shortline-book-b-v1` 登记后启动。首个挑战变量建议是 COLD 与空槽机会成本；其他条件固定。
先登记假设、样本外起点、比较族数量、资金约束、费用与失败处理，后读取未来结果。
当前代码没有自动启动这类新资金组合，也没有将选择记录升级成组合收益。

维护顺序：

1. 原晨间 owner 收齐执行回执，检查共同阶段差异；工程损耗与合法未成交分开。
2. 原 EOD owner 核对当日会计/费用，保留实际费用未知；研究标签按原 forward_eval 成熟。
3. 周复盘在原 plan 前运行一次上述比较命令（end 为真实窗口末日），再由 weekly harness
   冻结报告、输入和每日选择记录。沿现有三个实验槽跟踪，不另建一套无限增长的候选池。
4. 每槽记录 continue/refine/completed/retired/rolled_back、证据、反证与下一次检查条件。
   同时看费用后资金收益、回撤、资金利用率、尾部损失与执行损耗；成交率本身不是目标。
5. 永久变更须 §10 的点时/费用/样本外/失败样本/研究门与回滚；执行修复以受影响行为
   回归和后续自然运行证明。未证明事项保持显式状态，不靠新的说明文字变成通过。

## 发布验收

顺序为隔离实现 → 独立 Standards/Spec 评审并修复 → 合法测试时段内行为回归 →
源码/skill/Automation 一致读回 → 下一原始自然批次验收。禁止回放已终态交易日。
自然验收检查同批 hash、COLD 默认与合法覆盖、空批/零买回执、两端分配适配差异、
原计划/成交/账本及研究记录隔离。回滚使用本变更 commit 的定向 revert，保留全部历史证据。
