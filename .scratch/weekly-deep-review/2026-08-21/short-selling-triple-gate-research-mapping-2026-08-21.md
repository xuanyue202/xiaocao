# 补齐跨市场做空三重门槛研究契约

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
固定输入允许证据完整的只读工具自动落地，但 XH-092 目前只是研究方向。没有 point-in-time 数据契约和协议时实现代码会把私人公司估值、事后可借券性或任意阈值混入结果，无法形成可审计证据。

## 建议动作
先定义 research-only 契约：限定公开可交易且可验证借券/反向工具的市场与标的；绑定带发布日期和 provenance 的公开估值源；预注册方向、严重高估、持续下跌阈值及持有期；定义含借券费、滑点和止损的 baseline/variant 输出 schema；加入无前视、拒绝私人公司估值的 fixture，并登记独立 research protocol/manifest。映射完整后再走工具类 AUTO_APPLIED。

## 证据包
```json
{
  "attribution": "本周固定输入只提供 XH-092 的三重条件主张与待比较指标；仓库现有事实源和已登记协议都没有覆盖跨市场可借券标的与 point-in-time 公开估值。",
  "baseline_vs_variant": "基线是保留 authority=0 的可证伪候选；变体必须预先登记单日弱势基线、方向/估值/持续性阈值、持有期、成本和借券约束，并输出同样本后续收益、最大回撤、止损率与持续性误判率。",
  "change_scope": "跨市场做空只读研究契约与数据映射提案；不建立空头敞口，不改变 Book B/T、账户、成交、安全或真实资金行为。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + reference/experience/distilled/2026-08-20_lv_xiaotong_review.json + output/live/weekly_plan_2026-08-21.json",
  "overfit_check": "要求 point-in-time 标的与估值、预注册阈值和持有期、独立 train/test 与多重比较校正；私人公司估值和事后可交易性回填必须被 fixture 明确拒绝。",
  "problem_observed": "计划器把跨市场做空三重门槛回测泛化成可自动实现的只读投影，但候选缺少可交易空头 universe、借券事实、已核验估值源、阈值、执行成本、输出 schema 和适用研究协议。",
  "rollback": "git revert <commit>"
}
```
