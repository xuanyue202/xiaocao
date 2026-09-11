# 建立无 KOL 配对基线

- mode: PROPOSAL_ONLY
- source: output/live/weekly_plan_2026-09-11.json#kol_system_review
- requires_confirmation: True

## 为什么需要你看
固定证据缺少经济反事实与完整结算，不能 AUTO_APPLIED，也不能用本周亏损或消费次数证明 KOL 有效/无效。

## 建议动作
确认后由隔离研究 runner 建立逐账户、逐 legal event 的 no-KOL/current 配对账；先补齐被判无效的 10 个 paper consumption 文件及缺失日志。

## 证据包
```json
{
  "attribution": "18 个发布包中 17 个中性，唯一暂停新增风险在 9 月 11 日 14:21 才发布；现有账户变化同时受到资格、市场、资金、T+1、native prepare 和确定性退出门影响，无法把净值差归因于 KOL。",
  "baseline_vs_variant": "同一不可变 freeze、同信息集、同整手与资金/退出/费用约束下比较 no-KOL 与实际 current；只有完整逐笔合法消费与结算链才计算增量。",
  "change_scope": "proposal only；只设计隔离研究账，不改正式策略、freeze、账户、资本、安全或调度。",
  "evidence_artifact": "output/live/weekly_plan_2026-09-11.json#kol_system_review；output/live/kol_policy/analysis/weekly-2026-09-11-astra-analysis.json",
  "overfit_check": "预注册 OOS、等风险、多重比较、来源/模式/日期聚类与最低样本；剔除最大赢家后复核，1/4/12 周未形成独立样本前不宣称稳定。",
  "problem_observed": "缺同 freeze、同资本、费后可成交的 no-KOL/current 配对，无法区分信息增量与少用资金、入口资格或执行门。",
  "rollback": "未启动即无运行副作用；若另获研究门批准，仅撤销隔离实验的明确版本化变更并保留失败/恢复证据。"
}
```
