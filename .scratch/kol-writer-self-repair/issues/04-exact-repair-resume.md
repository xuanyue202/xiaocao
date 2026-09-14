# 04 — 让失败内容修复后精确续跑

**What to build:** 让已经失败或中断的 exact item 在修复后只沿原 message、content、claim 和业务 identity 继续：系统精确读取目标消息、验证修复 revision 与测试凭证、核对不确定副作用，并自动跨过已有 receipt，绝不通过全量 sweep 或无关 commit 重放业务。

**Blocked by:** 02 — 稳定 writer 启动与来源取证；03 — 让新内容首次处理就能正确完成

**Status:** ready-for-agent

- [ ] Exact resume 只调用一次绑定 message ID 与 expected content SHA 的 get，不调用 full pending list；missing、changed、acked 和 connector unavailable 都在 processor 前 fail closed。
- [ ] Code/contract repair 必须存在 matching `RepairValidationReceipt`，绑定原 failure fingerprint/revision、repair revision、目标 branch lineage 和仓库亲自运行的 targeted test result。
- [ ] 自动解析当前 revision 只提供便捷输入；无关 commit、未推送 commit、lineage 回退、错误 target 或失败测试不能授权 resume。
- [ ] Provider `wait_until` 继续按 durable timezone-aware deadline 在同 revision 续跑，不要求虚构代码修复；deadline 前不 poll。
- [ ] v1 pending item 保留原 claims/idempotency keys 并继续，v1 completed item产生零新业务 event，v2 new item只建立一次既有业务 claims。
- [ ] Publication、每个 recipient、Book、knowledge 和 ack 后的 crash matrix 均证明恢复时已有 receipt 不回退、每个外部 identity 最多一次、最终 ack 恰好一次。
- [ ] Uncertain effect 必须先通过原 identity 的权威 readback 进入 `reconcile_required`；没有零效果证明时禁止重试。
- [ ] 修复续跑保持当前任务 owner，只使用合法窄 resume surface；不得再次运行同 slot 的全量 writer，也不得推进其他 pending message。
