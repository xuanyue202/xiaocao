# 定义美元利率公司传导研究合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
宏观利率到公司利润与估值的映射本身就是待证伪假设，不是无判断的报表字段；没有研究协议和 manifest 时不能自动落地。

## 建议动作
先登记 research-only protocol，定义官方利率/公司公告来源、company_id/period/published_at/currency_exposure/hedge/margin/orders/earnings_revision/valuation schema、传导时滞和基准；生成 point-in-time fixture 与 manifest 后再跑受保护研究。

## 证据包
```json
{
  "attribution": "来源 action_summary 明确标为 research_candidate_only；固定输入没有美元利率、公司币种暴露、套保、利润率、订单、盈利修正和估值的统一 point-in-time 面板。",
  "baseline_vs_variant": "基线是保留 XH-099 为未测候选；变体必须预注册公司 universe、利率冲击、传导时滞和基准，比较美元成本/套保/毛利率/订单/盈利修正/估值是否存在稳定先后关系。",
  "change_scope": "美元利率到海外收入制造企业的 research-only 数据与协议映射；不形成板块方向、证券交易或资金动作。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-08-27_liu_shao_review.json + output/live/weekly_plan_2026-08-28.json",
  "overfit_check": "要求至少八个 point-in-time 财季、固定公司与行业基准、币种和套保披露、预注册时滞、双向 walk-forward 和多重比较校正；单次降息预期或事后行业赢家不得成为特征。",
  "problem_observed": "计划器把宏观传导研究候选归为普通观测工具，但缺少公司级中间变量、发布日期、因果时序、样本 universe、协议 manifest 和可审计数据源。",
  "rollback": "git revert <commit>"
}
```
