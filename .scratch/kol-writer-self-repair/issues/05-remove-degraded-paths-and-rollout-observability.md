# 05 — 删除旧退化路径并上线稳定性观测

**What to build:** 在首次正确完成和精确修复路径均可用后，迁移剩余 writer 行为、删除无 owner 的 generic waiting 退化通道，并交付能回答“是否真的越来越顺”的每日 convergence 报告；随后以唯一 writer、正确 revision 和权威 Automation readback 完成首个生产 rollout，启动七日稳定窗口。

**Blocked by:** 04 — 让失败内容修复后精确续跑

**Status:** ready-for-agent

- [ ] 所有来源、semantic、mailbox、publication 和 maintenance 路径只产生统一进度结果；legacy projection 与已知 diagnostic 的 generic waiting fallback 被删除。
- [ ] 内部确定性故障不能返回无限 `wait_until` 或 `user_action_required`；provider deadline、auth/CAPTCHA 和 unreconciled effects 仍保持各自合法状态。
- [ ] Repo runtime、writer skill、Automation prompt contract、CLI output 和测试 fixture 对七种进度、exact get、repair receipt 与 completion semantics 保持一致。
- [ ] 指标至少覆盖 failure fingerprints、repair required/closed、repair 后 same-root recurrence、generic waits、内部故障用户依赖、peer-gate attempts/latency、runner starts、side-effect reconciliation 和 duplicate-effect audit。
- [ ] 每日 convergence report 只输出 credential-safe 聚合和稳定 code，明确 scheduled/clean/business slots 与排除项，不允许手工删除失败 slot。
- [ ] 冻结的 deterministic corpus、targeted suites、完整 KOL suite、compile、whitespace 和 exact-once regressions 全部通过；现有 PTY、routing、terminal replay、provider deadline 与 active-peer no-op 不回退。
- [ ] 生产 rollout 前 read back 唯一 writer、目标 revision、工作树保护、依赖/私有配置/恢复状态和权威 Automation ownership；禁止 active-active、重复 Automation 或用镜像配置冒充启用状态。
- [ ] 首个生产 rollout 成功后记录稳定窗口起点和基线摘要，开始累计七个自然日且至少 50 个 scheduled slots；不补跑历史业务。
