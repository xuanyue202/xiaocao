# 06 — 完成七日稳定验收

**What to build:** 用首个 rollout 后的权威运行账本和每日 convergence 报告判断 writer 是否真正“跑顺”；只有安全硬门槛、已知故障关闭、修复后不复发和时延目标同时有足够样本证据时，才给出通过结论，否则保持 ticket 打开并返回精确未收敛 fingerprint。

**Blocked by:** 05 — 删除旧退化路径并上线稳定性观测；以及首个 rollout 后七个自然日的外部观察时间

**Status:** ready-for-agent

- [ ] 观察窗口覆盖连续七个自然日和至少 50 个实际 scheduled writer slots，排除项均有稳定 code、数量和可核对原因。
- [ ] 整个窗口 active-active、重复 publication/reminder/Book/knowledge/ack、远端 source-video bytes 和内部故障 user action 均为零。
- [ ] 全部已知 failure fingerprint 已有 matching closure；没有已知 diagnostic 被降为无 owner 的 generic waiting，也没有无 open repair ownership 的跨-slot recurrence。
- [ ] 最后连续三日且至少 20 个 scheduled slots 没有 repair closure 后的同根因复发。
- [ ] Peer gate P95 不超过 60 秒，clean/no-update sweep P95 不超过 5 分钟；不能通过跳过权威 readback或减少安全验证达标。
- [ ] 新出现的内部 fault 在当前任务取得 owner、形成 repair receipt 并关闭；P0 安全事故或 repair 后同根因复发会使本次验收失败，而不是从报告中排除。
- [ ] 最终验收报告能从 runtime ledger 独立重算 scheduled slots、fingerprint/repair/closure、latency 和 duplicate-effect audit，且不包含私有内容或凭证。
- [ ] 只有全部标准满足时才报告稳定窗口通过；未满足时列出精确 blocker、owner 和下一验证窗口，不宣称“基本稳定”或完成。
