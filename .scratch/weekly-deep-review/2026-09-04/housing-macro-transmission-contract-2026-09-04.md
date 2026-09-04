# 定义住房与宏观科技传导合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
固定输入只有转录主张与证据哈希，没有定义可审计数据源、时点语义和研究 guard；直接实现会把 authority=0 叙事固化成隐含真值。

## 建议动作
确认是否先定义住房与科技传导的独立 schema、来源优先级、发布日期/修订规则、缺失值语义和样本外验证合同；确认前只保留候选。

## 证据包
```json
{
  "attribution": "2026-08-31 与 2026-09-01 的 action log 把住房企稳、房地产政策和科技叙事传导列为 authority=0 研究方向；固定输入没有可消费的时点数据合同。",
  "baseline_vs_variant": "基线是保留 XH-100、XH-118、XH-121 为未测候选；变体须在同一发布日期截面比较融资成本、租金回报、库存/成交、政策节点与科技订单/盈利中间变量对后续结果的增量解释力。",
  "change_scope": "住房与宏观科技传导的只读 point-in-time 数据合同提案；不改变策略、参数、Book、账户、成交或安全。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-08-31_liu_shao_review.json + reference/experience/distilled/2026-09-01_liu_shao_review.json + output/live/weekly_plan_2026-09-04.json",
  "overfit_check": "预注册字段、发布日期、滞后窗口、城市/行业 universe、缺失值语义和基准；使用滚动样本外与多重比较校正，禁止以事后政策效果或赢家回填历史截面。",
  "problem_observed": "计划器把住房融资—租金—供需和科技主线中间变量泛化成一个可自动实现的投影工具，但没有字段词典、来源版本、时序、样本单元、缺失值规则或可复现基线。",
  "rollback": "git revert <commit>"
}
```
