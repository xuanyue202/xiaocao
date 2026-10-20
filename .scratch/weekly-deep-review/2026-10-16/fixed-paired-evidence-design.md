# 补齐三方案点时证据与观测契约

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
本周16项笼统观测提议没有完整数据/字段/生效时钟/成本/基线契约；1/4/12周无配对OOS，三个9月11日实验均未运行。不能靠框架文案、口述赢家或旧PASS自动调整策略。

## 建议动作
仅完善原baseline_no_kol/current_bounded/kol_challenger三槽的证据设计：固定同日候选、模式、首次时点、分数与涨幅，按合法报价/整手/资金/T+1/费用/退出配对；分开纸面与APP，保留错失上涨、失败和回滚，10月23日复核。未启动试验、不扩大仓位或模式权限。

## 证据包
```json
{
  "attribution": "固定action log与weekly snapshot/kol_system_review明确记录缺点时面板、缺消费时钟与无配对run；不是市场方向证明。",
  "baseline_vs_variant": "no-KOL/current/challenger尚无同样本费后OOS比较；只保留可证伪设计，收益不填0。",
  "change_scope": "authority=0研究/只读证据设计，保留三原experiment_id；现有策略、账户、freeze和订单不变。",
  "evidence_artifact": "output/live/weekly_plan_2026-10-16.json；原固定快照manifest与独立语义/主审记录。",
  "overfit_check": "预注册OOS、作者/事件聚类、失败和未成交样本、剔除单赢家与成本敏感性；小样本不作因果证明。",
  "problem_observed": "16项观测建议缺可复现三方案证据契约，纸面盈利与A/B退出差不能解释KOL增量。",
  "rollback": "本轮未启动；后续撤回隔离变体并保留原证据，文档可git revert本提交。"
}
```
