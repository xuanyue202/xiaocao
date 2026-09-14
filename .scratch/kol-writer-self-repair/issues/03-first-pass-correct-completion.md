# 03 — 让新内容首次处理就能正确完成

**What to build:** 让一个全新的 eligible KOL item 只基于当前 request、immutable evidence 和当前 market evidence 构建 canonical semantic artifact，经唯一完整 validator 后先持久化 receipt，再沿既有业务 identity 一次推进到报告或合法 low-density terminal、提醒、paper-only Book、知识效果和 ack。

**Blocked by:** 01 — 建立统一自修复状态模型

**Status:** ready-for-agent

- [ ] 普通调用者只使用 canonical build interface；legacy validation 只允许 reconciliation、migration 和只读 audit，不能成为新事件 builder。
- [ ] Semantic draft 只能表达当前判断并引用 request 已提供的 segment identity；不能输入旧 bundle、覆盖 evidence identity、生成第二套 segment ID、填写业务 idempotency key 或重复 market projection。
- [ ] 所有支持的 semantic entrypoint 使用同一组枚举、cross-field projection 和完整 validator，不再存在“前置通过、后段失败”的第二消费门。
- [ ] `ValidatedBundleReceipt` 在任何 publication prepare 或 side-effect claim 前原子持久化，并绑定 message/content、handoff/media、transcript、extraction contract、market evidence、bundle 和 validator identity。
- [ ] `longitudinal_projection.status="candidate"` 及 coverage、market、reader、knowledge、Book 不一致在任何 claim 前以稳定 typed error 失败。
- [ ] Bundle SHA 只证明 artifact integrity；外部 publication、recipient、Book、knowledge 和 ack identity 继续由既有业务 identity 构造。
- [ ] 一个 credential-free end-to-end fixture 从新 item 经过 validated receipt 到全部 fake terminals，publication → reminder/Book/knowledge → ack 顺序正确，每个 fake 外部 identity 恰好一次。
- [ ] Lv、subscription video、Xiaocao handoff 和公众号文章的正常 semantic 路径都通过同一最高 seam 验收，不触发真实发布、提醒、Book、知识或 mailbox 副作用。
