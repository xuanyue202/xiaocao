# 定义资金流与广度投影契约

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
工具缺口真实存在，但缺少点时来源/provenance、字段及缺失值契约、明确消费方、验收夹具和基线量化；本周不能 AUTO_APPLIED。

## 建议动作
确认后先预登记只读契约与最小样例：逐字段来源及点时语义、缺失处理、输出消费者、基线误差/工时、验收夹具、维护所有者与撤回路径。

## 证据包
```json
{
  "attribution": "action_summary 只给出了工具缺口名称，未给出点时数据来源、字段语义、消费方或可复现误差基线，不能据此推断唯一安全实现。",
  "baseline_vs_variant": "先记录人工拼接 recommend、signal、positions、cohorts 的时间与错误基线，再用同一冻结输入比较只读投影的字段完整性、可追溯性和维护成本。",
  "change_scope": "proposal only；只设计只读投影契约，不改变策略、参数、候选、买卖、账户、资金、安全门或调度。",
  "evidence_artifact": "reference/experience/distilled/2026-09-15_a_alex_review.json；reference/experience/distill_action_log.jsonl",
  "overfit_check": "预先锁定来源、字段、缺失值语义、消费方、样例和验收夹具；禁止按单周结果反向选择字段或阈值。",
  "problem_observed": "需要重建资金流、广度、板块强弱、订单、收益和现金流表，但现有证据包尚不足以形成可执行变更。",
  "rollback": "未启动即无运行副作用；若另获确认，仅撤销隔离投影及其消费接线，并保留原始数据与失败样例。"
}
```
