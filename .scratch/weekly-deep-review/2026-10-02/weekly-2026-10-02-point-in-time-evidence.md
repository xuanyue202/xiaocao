# 先补三方案点时与费用成交证据，再评估框架和九项观测建议

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
现有固定输入不支持框架推广；本提案仅供复核证据设计，后续正式策略/永久参数变更仍须完整§10证据。本轮finalize/commit无需等待回复。

## 建议动作
保留既有三个稳定试验槽位，合并九条泛化instrumentation建议为证据设计；先定义完整未过滤候选、真实时间、身份/来源、字段/缺失语义、消费/委托/成交/费用、同资本OOS配对，再运行隔离研究。当前不改正式策略、参数、资金或交易门。

## 证据包
```json
{
  "attribution": "从固定action log与内容寻址88文件、研究manifest和KOL库存独立核验；旧PASS、A/B退出配对和中性包不足以归因KOL增益。",
  "baseline_vs_variant": "no-KOL/current/challenger全为insufficient_evidence；仅保留设计，不编零收益或PASS。",
  "change_scope": "PROPOSAL_ONLY research design；运行事故只读汇总修复走独立lane。",
  "evidence_artifact": "/Users/xuanyue202/Documents/project/xiaocao/output/live/weekly_plan_2026-10-02_inputs/9ed5036c7f8cac2c0b2cf277c1e6e644933db7684234531faf1d308b79638785.manifest.json",
  "overfit_check": "先预注册同freeze/资本/整手/时点/流动性/T+1/费用/风险/退出的OOS，按作者事件和日期聚类，剔除单赢家并覆盖失败样本。",
  "problem_observed": "固定比较为空；旧三个试验没有run；九个自动工具候选缺可实施点时输入/消费者/缺失语义；候选假设库及paper消费输入无效。",
  "rollback": "本轮未启动试验；保留原策略与原证据。后续隔离研究按各稳定slot的rollback执行。"
}
```
