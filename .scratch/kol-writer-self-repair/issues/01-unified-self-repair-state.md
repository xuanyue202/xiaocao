# 01 — 建立统一自修复状态模型

**What to build:** 让小时 KOL writer 的每个步骤都通过同一套可持久化进度合约表达“继续、等待、修复、核对、用户动作或完成”，并用一个代表性内部故障贯穿 adapter、orchestrator、账本和审计结果，证明可恢复问题始终有明确 owner，不会再被普通 waiting 吞掉。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] 统一进度合约只允许 `continue`、`structured_input`、`wait_until`、`repair_required`、`reconcile_required`、`user_action_required` 和 `terminal` 七种结果，每种结果都有固定必需字段和唯一合法下一步。
- [ ] `retryability` 与 `ownership` 独立；代码、schema、环境、provider contract 和控制面 handler 故障归 Agent，不能仅因可重试而失去当前任务所有权。
- [ ] Credential-safe failure fingerprint 稳定绑定 adapter、category、code、stage、失败 revision 和 provider-contract version，不包含标题、URL、凭证、私有路径或原始异常文本。
- [ ] Append-only convergence ledger 能记录 first/last seen、same-sweep count、consecutive slots、当前 owner、repair receipt 和 closure，并能从中恢复当前权威状态。
- [ ] 一个 deterministic 内部故障从产生点到 writer 结果完整返回 `repair_required`；matching repair closure 前不得变成普通 waiting 或 terminal。
- [ ] 现有 clean/no-update、provider deadline 和 completed terminal 行为通过兼容投影保持不变，相关回归全绿。
