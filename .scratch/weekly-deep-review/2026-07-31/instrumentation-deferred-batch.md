# 本周只读 instrumentation 候选延后落地

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: false

## 为什么本周没有自动落地

固定输入给出了 5 个 evidence-backed 的只读观测候选，但本周计划同时存在必须确认的策略消费提案，整体推荐模式是 `PROPOSAL_ONLY`。运行前还有 34 个 allowlist 路径处于 dirty 状态；weekly finalizer 会对 `AUTO_APPLIED` 硬阻断。为避免把用户已有 KOL/蒸馏工作混进周度提交，本周只保留可审计提案，不改策略、参数、买卖、账户或资金。

这些工具候选没有被否决，也不需要策略确认。待工作区满足 clean-target 条件，并为每个候选确定独立输出 schema、fixture 和报告样例后，可按原 evidence bundle 自动落地。

## 候选与建议动作

1. `instrumentation-2026-07-26-proposal`：回放同涨同跌/跷跷板窗口内的相对强弱，比较未大涨抗跌大票与已大涨补跌大票；证据为 `reference/experience/distilled/2026-07-26_xiaocao_review.json`。
2. `instrumentation-2026-07-27-etf`：回放固定钟点、指数转折和标的信号，并建立同主题 ETF 流动性/滑点对照；证据为 `reference/experience/distilled/2026-07-27_xiaocao_morning.json`。
3. `instrumentation-2026-07-29-qqq-tqqq`：跟踪 QQQ/TQQQ 路径差、长鑫产能与海外存储毛利率，以及科技恐慌窗口中的宽基和单股永久损失率；证据为 `reference/experience/distilled/2026-07-29_lv_xiaotong_review.json`。
4. `instrumentation-2026-07-29-proposal`：回放普涨但无主线日的追涨质量，并按一手占净值比例研究小账户组合左尾；证据为 `reference/experience/distilled/2026-07-29_xiaocao_review.json`。
5. `instrumentation-2026-07-30-proposal`：回放无入围日的空仓与强选最高分，并研究情绪风向标连续承接对后续短线模式胜率的领先性；证据为 `reference/experience/distilled/2026-07-30_xiaocao_morning.json`。

## 共同验收边界

- 只读、cache-first，不接真实交易接口，不写账户、成交或安全状态。
- 每个候选使用独立 fixture，固定输入、分组、时间窗和缺失数据语义。
- 输出必须带样本覆盖、基线/变体、最大不利变动或执行损耗等对应指标，不能把缺失当零。
- 完成后以 focused pytest 和报告样例验证，并在 action log 中记录实际实现位置。

## 回滚

`git revert <commit>`
