---
status: accepted
---

# Use one remote runtime writer and one local WeChat capture node

`MacBook-Pro-6.local` is the target sole Xiaocao runtime node for trading Automations, mutable paper ledgers, KOL hourly coordination, 灰常亮 writes, and enterprise-WeChat Relay notifications; the current local machine retains session-dependent WeChat acquisition, development, Obsidian, and manual cold-standby capability. Xiaocao deliberately rejects active-active and automatic failover because duplicate writers can corrupt ledgers or repeat publications and notifications, while desktop WeChat cannot be safely shared across the two machines. A takeover is manual and is complete only after the former writer is quiescent, mutable state is consistently handed over, and the Codex Automation authority is switched and read back; matching Git commits or TOML mirrors do not prove runtime ownership.

Local-to-remote KOL evidence uses the registered Codex Xiaocao task described in ADR 0008; it does not require a shared filesystem inbox. Until runtime-state restoration and authoritative Automation readback succeed, the current local machine remains the sole writer.
