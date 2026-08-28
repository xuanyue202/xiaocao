# 定义量化管理人容量衰减面板合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
直接实现会迫使工具自行选择数据商、容量代理、产品身份、基准、费用和缺失值语义；这些选择会决定结论，已超出只读展示层。

## 建议动作
先确认公开或已授权的 point-in-time 数据源，并登记 manager_id/product_id/as_of/published_at/AUM/capacity_proxy/turnover/cost/net_nav/benchmark/currency schema、缺失即不可评分规则和滚动样本外协议；合同通过后再实现只读面板。

## 证据包
```json
{
  "attribution": "本周固定输入只给出量化管理人容量衰减的 authority=0 主张和转录哈希，没有提供可消费的数据合同或已经登记的研究协议。",
  "baseline_vs_variant": "基线是保留 XH-093 为未测候选；变体必须在同一管理人/产品身份和 point-in-time 截面上比较容量利用率分组的后续 3/6/12 个月扣费超额、最大回撤、换手、冲击成本和压力期相关性。",
  "change_scope": "量化管理人容量衰减的只读数据与研究合同提案；不改变任何 Book、账户、成交、安全或资金行为。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-08-22_lv_xiaotong_review.json + output/live/weekly_plan_2026-08-28.json",
  "overfit_check": "要求冻结管理人/产品身份、发布日期、AUM 与容量代理定义、费用和基准；预注册 3/6/12 月窗口，使用滚动样本外、幸存者偏差审计和多重比较校正，禁止用事后规模或净值回填。",
  "problem_observed": "计划器把量化产品评估方向泛化成可自动实现的只读面板，但固定输入没有 point-in-time AUM、容量定义、经审计净值、费用、换手/冲击成本、基准与产品身份映射。",
  "rollback": "git revert <commit>"
}
```
