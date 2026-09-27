# 先建立 KOL 三框架点时配对与完整账户证据契约

- mode: PROPOSAL_ONLY
- source: output/live/flywheel_change_ledger.jsonl
- requires_confirmation: True

## 为什么需要你看
本周 KOL 新发布决策为 0，四周与十二周可用政策样本重合；37 个既有决策无完整同冻结、同资本、同费用的执行/结算链。上期三个试验仍无可核验运行，不能把暂停或现金拖累认作收益。

## 建议动作
按现有三个稳定试验 ID 先定义隔离、只读的点时机会集和 no-KOL/current/challenger 配对口径；补齐 live/paper 分账、成交/费用/结算、消费时钟和缺测标记，经研究门与负责人确认后才运行。2026-10-02 复核证据与反证。保持§2a有界叠加及所有资本/执行门。

## 证据包
```json
{
  "attribution": "来源、模型、风险门、freeze、券商状态和账户结算尚未做点时全链归因；不能把无买单归给 KOL。",
  "baseline_vs_variant": "同一冻结候选、合法时点、本金、整手、费用和退出条件下比较 no-KOL、现行有界叠加、authority=0 挑战者。",
  "change_scope": "仅研究设计提案；不启动策略、资本、杠杆或券商交易变更。",
  "evidence_artifact": "output/live/weekly_plan_2026-09-27.json#kol_system_review; output/live/flywheel_change_ledger.jsonl; output/live/book_b_live_execution/events.jsonl",
  "overfit_check": "预注册 OOS、按交易日/独立来源聚类、包含失败样本及单一赢家剔除；4/12周重叠不当独立样本。",
  "problem_observed": "无法估算 KOL 增量收益、错失上涨、资金占用、回撤或执行漏损；三个旧试验无运行回执。",
  "rollback": "若获准启动隔离研究，保留预注册版本与失败回执，撤销具体研究实现；正式交易配置不变。"
}
```
