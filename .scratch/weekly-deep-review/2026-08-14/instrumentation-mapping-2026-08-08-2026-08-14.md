# 补齐本周 8 条观测缺口的可实施映射

- mode: PROPOSAL_ONLY
- source: reference/experience/distill_action_log.jsonl
- requires_confirmation: True

## 为什么需要你看
固定输入允许工具类 AUTO_APPLIED，但这 8 条只有方向性 todo；缺少逐项数据源、字段、目标和夹具时自动写代码会把未解决的研究问题误报成已落地。

## 建议动作
先按同一竖向结果补齐映射：优先选择已有生产事实源的执行纪律/命中审计项，明确 target、输入字段、输出 schema、前向时间边界、fixture 和验收命令；外部财务与供应链项继续留在研究候选层。映射完整后再走工具类 AUTO_APPLIED。

## 证据包
```json
{
  "attribution": "本周固定输入中的 8 条 instrumentation_todo 都来自 distill_action_log，但只给出研究方向或未来观测目标，没有逐项绑定现有事实源、输出 schema、目标文件与确定性夹具。",
  "baseline_vs_variant": "基线是保留 8 条可追溯工具缺口；变体必须先补齐每项 target/data-source/schema/fixture/acceptance mapping，再实施真正可验证的只读投影，不能用一个泛化 backlog 列表冒充完成。",
  "change_scope": "只读观测工具实施映射提案；不改变策略、参数、成交、账户、安全或真实资金行为。",
  "evidence_artifact": "reference/experience/distill_action_log.jsonl + output/live/weekly_plan_2026-08-14.json",
  "overfit_check": "先要求结构化事实源和确定性夹具，避免围绕单篇转录或事后赢家定制字段；未来收益类观察仍须前向留样并经过研究护栏。",
  "problem_observed": "8 条候选被计划器泛化为‘实现只读观测/投影工具’，但没有足够实施映射来证明本周落地后已真实覆盖相应缺口。",
  "rollback": "git revert <commit>"
}
```
