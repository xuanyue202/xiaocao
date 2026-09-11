# 隔离检验上游候选挑战者

- mode: PROPOSAL_ONLY
- source: output/live/weekly_plan_2026-09-11.json#kol_system_review
- requires_confirmation: True

## 为什么需要你看
候选完整性、模式映射和可成交前向轨迹都不完整，挑战者只能先作为需确认的研究设计，不能自动推广到 paper 或 live。

## 建议动作
确认后预登记点时完整机会集和精确模式映射，建立 authority=0 challenger；保持 production freeze、最多三槽/同模式一只及所有资本安全门不变。

## 证据包
```json
{
  "attribution": "9 月 9/10 的单一 COLD 模式不能证明上游全模式和候选完整；但冻结内双 alpha 为负、历史广度禁低吸失败和晚到赢家也反对凭直觉放宽。",
  "baseline_vs_variant": "在同本金、同整手/费用、同合法时点、流动性/T+1/退出约束和完整失败样本下，对比 no-KOL、current 与 authority=0 challenger 的机会覆盖和风险调整结果。",
  "change_scope": "proposal only；挑战者只存在隔离研究队列，不进入生产 freeze，不新增 live 候选，不改变 v2 的小草本人/同日精确 mode-follow 边界。",
  "evidence_artifact": "output/live/weekly_plan_2026-09-11.json#kol_system_review.competing_explanations；output/live/kol_policy/analysis/weekly-2026-09-11-astra-analysis.json",
  "overfit_check": "预注册竞价、固定 9:31 与盘中模式，不扫最佳秒点或事后阈值；包含 COLD 反证、全部失败样本并做 OOS、宽邻域、最大贡献模式剔除。",
  "problem_observed": "只在已入选票上缩量无法检验入口过滤与模式集合的局部最优，但现有赢家举例、BJSE 和模糊模式名也不足以授权扩大生产候选。",
  "rollback": "本周未启动且 authority=0；若另经研究门批准，停用隔离研究读取不得触及正式账户、freeze、参数、资本 key，并保留反证和失败记录。"
}
```
