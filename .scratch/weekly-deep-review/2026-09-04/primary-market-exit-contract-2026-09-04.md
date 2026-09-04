# 定义一级项目估值退出合同

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
一级项目与二级市场公司的样本单元、数据来源和退出语义不同，不能并入泛化公司面板，更不能在只有成功叙事时自动实现。

## 建议动作
确认项目主键、披露/修订规则、失败与未上市样本覆盖、估值和退出状态 schema；合同闭合后再决定是否建设只读面板。

## 证据包
```json
{
  "attribution": "2026-09-04 的 action log 新增一级项目退出核验方向；固定输入只有转录哈希与候选主张，没有项目级可审计事实链。",
  "baseline_vs_variant": "基线是保留 XH-126 为未测候选；变体须在同一项目身份和披露时点上比较完整核验资金来源、估值、可比主体、订单/现金流、上市条件、锁定期和退出安排与仅按融资热度参与的后续回报、回撤和退出成功率。",
  "change_scope": "一级项目估值与退出路径的独立只读数据/研究合同；不形成证券交易、家庭配置或 real-capital 行为。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-09-04_lv_xiaotong_review.json + output/live/weekly_plan_2026-09-04.json",
  "overfit_check": "冻结项目身份、披露日期、轮次、估值口径、可比主体和退出状态；审计幸存者偏差、未上市/失败项目覆盖与多重比较，禁止只收集成功案例。",
  "problem_observed": "计划器建议建立一级项目退出面板，但没有项目主键、轮次/币种/估值口径、披露版本、锁定期、退出状态或失败样本覆盖规则。",
  "rollback": "git revert <commit>"
}
```
