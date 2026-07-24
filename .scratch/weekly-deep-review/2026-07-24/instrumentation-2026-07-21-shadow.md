# 为重复盘中预警补只读 shadow 回放

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: false

## 为什么本周没有自动落地

固定输入给出了完整的只读观测候选，但本周计划同时存在必须确认的策略消费提案，整体推荐模式为 `PROPOSAL_ONLY`。此外，运行前已有大量 allowlist 文件处于 dirty 状态；weekly finalizer 会对 `AUTO_APPLIED` 硬阻断。为避免覆盖或混入用户已有改动，本周只保留可审计提案；这个工具项不需要策略确认，待 clean-target 条件满足后可按同一证据候选自动落地。

## 建议动作

在干净目标文件上实现一个只读回放工具，把同方向盘中预警分为：

1. 单次预警；
2. 重复但第二次未增强；
3. 第二次分数更高且价格更低。

分别比较后续 30/60/120 分钟与 T+1 收益、最大不利变动和命中率。工具不得接真实交易接口，不得改变策略参数、买卖、账户或资金；完成后用独立 fixture 和报告样例验证，并将 action log 对应 todo 标记为 implemented。

## 证据包

```json
{
  "problem_observed": "为盘中重复预警建立 shadow 回放，比较单次、重复不增强、低价增强三组的后续收益和最大不利变动。",
  "attribution": "缺口来自 2026-07-21 action_summary.instrumentation_todo 的显式路由。",
  "evidence_artifact": "reference/experience/distilled/2026-07-21_xiaocao_review.json",
  "baseline_vs_variant": "当前需要手工拼接预警与后续价格；候选工具应输出固定分组、收益窗口和最大不利变动。",
  "overfit_check": "只读观测，不改变收益路径；以 fixture、样本覆盖和报告样例限制维护成本与报告噪音。",
  "change_scope": "流程/观测工具自动优化",
  "rollback": "git revert <commit>"
}
```
