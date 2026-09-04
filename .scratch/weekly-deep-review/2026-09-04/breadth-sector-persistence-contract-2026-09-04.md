# 定义市场广度与板块持续性合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
广度与板块持续性可能影响 posture 或策略叙述，缺少时点和验证合同会造成未来信息与指标挑选偏差。

## 建议动作
确认最小指标集、权威数据源、板块版本、目标窗口和样本外 guard；完成合同前不接入 posture 或任何确定性路径。

## 证据包
```json
{
  "attribution": "2026-09-03 两条 action log 共同提出广度、成交量、订单、两融、现金流、利率和板块持续性跟踪，但只给出方向性标签。",
  "baseline_vs_variant": "基线是继续保留 XH-118、XH-122、XH-128 的复核记录；变体须在固定指数/行业 universe 和同一交易日截面上比较广度、量价、两融、订单/现金流与利率特征对 1/5/20 日板块持续性的样本外增量。",
  "change_scope": "市场广度与板块持续性的只读研究面板合同；authority=0，不进入 posture、模式资格、排序或资金分配。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-09-03_a_alex_review.json + reference/experience/distilled/2026-09-03_liu_shao_review.json + output/live/weekly_plan_2026-09-04.json",
  "overfit_check": "预注册 universe、复权、发布时间、特征窗口、板块分类版本和 1/5/20 日目标；滚动样本外、费用/换手与多重比较校正必须同时披露。",
  "problem_observed": "计划只列出了若干指标名，没有数据来源、发布时点、板块分类版本、目标变量、缺失值语义或可复现实验。",
  "rollback": "git revert <commit>"
}
```
