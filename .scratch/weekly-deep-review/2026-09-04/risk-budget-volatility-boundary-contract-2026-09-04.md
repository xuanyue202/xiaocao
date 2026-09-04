# 定义风险预算与波动边界合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
该方向最接近退出与资金纪律；没有冻结定义和配对研究前，自动实现容易越过研究层并暗改行为。

## 建议动作
确认是否先把家庭风险预算与策略退出完全隔离，定义 research-only 事件 schema、最大损失/流动性字段和配对基线；确认前不得接入 Book。

## 证据包
```json
{
  "attribution": "2026-09-01、09-02 与 09-04 的 action log 分别提出波动边界、亏损预算/回撤入场和家庭复杂产品条款，但没有共同样本与可执行定义。",
  "baseline_vs_variant": "基线是保留 XH-121、XH-124、XH-125、XH-130 为 authority=0 候选；变体须在同资产同入场的冻结事件上比较预设损失预算/回撤边界与追涨或临时反向操作的收益、最大不利变动、被动止损、流动性和成本。",
  "change_scope": "家庭风险预算、波动资产边界与复杂产品条款的 research-only 合同；不触碰 Book B/T 退出、账户、成交、安全或真实家庭资产。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-09-01_liu_shao_review.json + reference/experience/distilled/2026-09-02_a_alex_review.json + reference/experience/distilled/2026-09-04_lv_xiaotong_review.json + output/live/weekly_plan_2026-09-04.json",
  "overfit_check": "边界必须在事件前冻结；按资产类型分层，显式纳入费用、汇率、保证金、流动性和不可交易性；使用 walk-forward 与多重比较校正，家庭口述仓位不得成为训练标签。",
  "problem_observed": "计划器将风险预算、回撤入场、波动边界和复杂工具混成只读工具，却没有最大损失定义、事件前冻结、资产分层、交易成本、流动性或配对基线。",
  "rollback": "git revert <commit>"
}
```
