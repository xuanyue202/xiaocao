# 定义波动资产边界纪律研究合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
边界纪律需要事件前参数、可交易执行和配对反事实；缺少这些要素时实现只会把事后叙述伪装成验证结果。

## 建议动作
单独定义 event_id/asset/instrument/entry_ts/boundary_set_ts/take_profit/invalidation/review_condition/hot_flow_signal/tradability/cost schema，注册适用跨资产 guard 与 manifest，并用事前冻结 fixture 验证无前视；通过后才实现只读比较。

## 证据包
```json
{
  "attribution": "来源 action_summary 将波动资产边界纪律标为 research_candidate_only；固定输入没有可复现的边界事件、热点反向操作基线、成本或跨资产统一收益样本。",
  "baseline_vs_variant": "基线是热点资金触发的频繁反向操作；变体是事前冻结止盈/失效/重新评估边界并持有。两者必须在同一资产、同一入场时点和同一可交易价格上比较 1/3/5/10 日收益、最大不利变动、换手和成本。",
  "change_scope": "波动资产边界纪律的 research-only 事件 schema 与配对研究提案；不改 Book B/T 退出、账户、成交、安全或家庭资产操作。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-08-27_liu_shao_review.json + output/live/weekly_plan_2026-08-28.json",
  "overfit_check": "要求边界在事件前冻结、同入场配对、资产级 walk-forward、成本和不可交易性纳入、资产/期限多重比较校正；作者事后止盈描述和家庭持仓不得作为训练标签。",
  "problem_observed": "同一泛化候选还混入了波动资产退出纪律，但它与宏观公司面板的样本单元、基准和 guard 完全不同，不能共用一个普通投影工具。",
  "rollback": "git revert <commit>"
}
```
