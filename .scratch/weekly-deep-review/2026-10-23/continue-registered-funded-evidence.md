# 沿已有三个槽维护费后资金、时效和机会成本证据

- mode: PROPOSAL_ONLY
- source: output/research/app_b_forward/performance.json
- requires_confirmation: False

## 为什么需要你看
首个自然日四组均未成交；缺完整同点时OOS及实际费用，不能晋级策略。

## 建议动作
继续既有前向账户和原三框架槽位，10月30日复核。当前无需用户作新的资金或策略决定；未来晋级必须满足原证据门。

## 证据包
```json
{
  "problem_observed": "no-KOL/当前/挑战者尚无完整费后可成交资金比较",
  "attribution": "原固定研究快照与独立Sol/主审共同核对",
  "evidence_artifact": "原snapshot manifest、app_b_forward/protocol/performance/app_lifecycle、短线对照报告",
  "baseline_vs_variant": "APP默认E/COLD保持；四组各100000模型元、首日一计划/no_fill，不能排序",
  "overfit_check": "继续多日OOS并保留空槽、缺标签、不可成交、费用与版本；日收益不当逐笔样本",
  "change_scope": "已登记authority=0研究维护，无策略或资本推广",
  "rollback": "git revert <commit>"
}
```
