# 01 — 建立证据绑定的趋势研判快照

**What to build:** 建立 `build_trend_snapshot(as_of) -> TrendJudgmentSnapshot` 深模块，把已发布 KOL 观点、小草节奏和市场验证转成冻结、可复核的主题状态，而不是作者关键词分数。

**Blocked by:** None — can start immediately.

**Status:** implemented

- [x] 只消费权威 publication receipt 与最新 evaluation 绑定，不能从 prepared artifact、标题或 legacy status 猜当前性。
- [x] Schema 覆盖来源角色、方向、置信、horizon、`review_not_after`、马车一个月上限、提前替代/失效、market validation 和四态 eligibility。
- [x] 小草、马车、其他 KOL 的角色独立表达；冲突不做平均或多数票。
- [x] Agent draft 不能填写业务 identity、成交、仓位或账本字段；builder 负责 canonicalization、hash 和 receipt。
- [x] 旧观点没有当前市场确认时不自动续期；缺 horizon 的其他 KOL 观点快速衰减并显式标注依据。
- [x] Interface tests 覆盖 current、wait、conflicted、invalidated、过期马车、观点替代、publication binding 失败和 deterministic replay。

## Implementation

- `src/xiaocao/strategy/trend_snapshot.py` implements the hash-bound snapshot
  builder, role-specific freshness, publication/evaluation/relation bindings,
  conflict and replacement handling, and fail-closed theme eligibility.
- `tests/test_trend_snapshot.py` covers the interface states, binding failures,
  deadline cutoffs, replacement evidence, and deterministic replay.

## Comments
