# 补齐 KOL 时钟与成交链

- mode: PROPOSAL_ONLY
- source: output/live/weekly_plan_2026-09-11.json#kol_system_review
- requires_confirmation: True

## 为什么需要你看
固定输入仅能证明部分发布与消费容器，不能证明实际订单、成交、费用或完整决策延迟，属于需确认的跨管线取证设计。

## 建议动作
确认后补齐不可变 source→request→model→review→publish→next legal consume→intent→fill/fee 时钟，并逐次标记重叠 T+1/无候选/prepare 阻断。

## 证据包
```json
{
  "attribution": "名义检查点、来源发生/接收、模型、review、publish 与消费时点混杂；9 月 11 日 pause 在 14:21 发布，不能追认上午开仓或 13:55 检查点，review_latency 也不是端到端延迟。",
  "baseline_vs_variant": "现行有界边界保持不变，只比较完整时钟/lineage 前后可核实的合法消费覆盖、等待成本、错失上涨和避免下跌；不以发布数量或 no-action 率为成功。",
  "change_scope": "proposal only；只设计只读时钟与 lineage 观测，不更改语义 TTL、发布门、独立审核、freeze 绑定或交易权限。",
  "evidence_artifact": "output/live/weekly_plan_2026-09-11.json#kol_system_review.inventory；output/live/kol_policy/analysis/weekly-2026-09-11-astra-analysis.json",
  "overfit_check": "预先区分管线迟延、语义不可执行和确定性执行门；复核 9 月 7 日窗口误判与 9 月 11 日两个时点，不为缩短统计发明阈值。",
  "problem_observed": "缺 source occurrence 到 broker/fill 的统一全链时钟，无法判断价值损失来自晚到、晚审、过期、无合法动作还是执行阻断。",
  "rollback": "本周未修改调度或运行逻辑；若另行授权遥测，实现前锁定恢复点，撤回时不放松任何来源、review、freeze 或资本门。"
}
```
