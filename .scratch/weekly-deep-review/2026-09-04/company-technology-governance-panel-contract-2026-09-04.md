# 定义公司技术与治理事实面板

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
这些主题跨越公司基本面、政策准入与治理事件，不能在缺少 point-in-time 合同和字段语义时合并成普通观测工具。

## 建议动作
确认是否建立公告优先的事实 schema，并先选一个最小主题做可复现样例；明确未披露、修订公告、公司/行业基准和事件窗口后再实现。

## 证据包
```json
{
  "attribution": "2026-08-31 与 2026-09-04 的吕晓彤复盘提出公司经营矛盾、技术主题、出口限制和融资治理核验；这些仍是 authority=0 候选。",
  "baseline_vs_variant": "基线是保留 XH-123、XH-127、XH-128、XH-129 为未测候选；变体须按公告发布日期冻结研发、订单、交付、利润、现金流、收入暴露、融资条款、质押/解禁与政策文件，并与只读叙事基线比较。",
  "change_scope": "上市公司技术主题、经营质量、市场准入与治理事件的只读事实面板合同；不产生交易、仓位、评分或参数。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-08-31_lv_xiaotong_review.json + reference/experience/distilled/2026-09-04_lv_xiaotong_review.json + output/live/weekly_plan_2026-09-04.json",
  "overfit_check": "冻结公告版本与发布日期，区分 reported/derived/not_disclosed，预注册公司 universe、事件窗口和行业基准；禁止把未披露字段当零或用后续公告改写历史。",
  "problem_observed": "一个泛化候选同时混合经营、情绪、技术、出口和治理，固定输入没有公告定位、字段口径、事件身份、版本修订、公司 universe 或验证基线。",
  "rollback": "git revert <commit>"
}
```
