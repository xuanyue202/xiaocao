# 定义东方甄选财季基本面板合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
这些指标并非仓库现有 recommend/signal/positions/cohorts 的投影，而是新的外部公司事实源；字段和缺失值合同未确认前落地会制造伪精度。

## 建议动作
先确认东方甄选公告/年报为权威源，定义 fiscal_period/published_at/source_locator/reported_vs_derived/currency 与公司及平台基准字段，并为未披露值、重述、半年转财季和口径变化建立 fail-closed fixture；完成后再实现 research-only 面板。

## 证据包
```json
{
  "attribution": "本周固定输入提供东方甄选分析和四条 authority=0 候选，但没有把公告/年报、平台大盘与公司经营字段映射为 point-in-time 结构化数据。",
  "baseline_vs_variant": "基线是保留 XH-095 至 XH-098 为未测候选；变体必须在至少八个已发布财季上，将公司收入、GMV、订单、客单价、自营品占比、会员/App、线下单点经济与可比平台基准逐期同口径对齐。",
  "change_scope": "东方甄选基本面只读数据合同与事实面板提案；不生成证券买卖、仓位、Book 写入或策略参数。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-08-25_lv_xiaotong_review.json + output/live/weekly_plan_2026-08-28.json",
  "overfit_check": "要求保存公告发布日期和原始表格定位，区分 reported/derived/not_disclosed，冻结季节性与平台基准口径；禁止把未披露的复购、App 订单或单点经济填成零，也禁止用后来披露的信息改写历史截面。",
  "problem_observed": "计划器建议自动补公司公告/年报与后续财季面板，但固定输入没有字段词典、公告版本、平台基准、派生公式、币种/财年对齐或未披露值规则。",
  "rollback": "git revert <commit>"
}
```
