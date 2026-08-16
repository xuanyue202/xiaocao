# 06 — 原地升级 Book T 并移除定制接入

**What to build:** 在研究消费门、人工门和运行契约全部通过后，用 v2 selector 原地替换现行 Book T 候选逻辑，并移除作者专属马车接入。

**Blocked by:** 05 — accepted research verdict and human approval.

**Status:** blocked-on-evidence

- [ ] Promotion 前必须有工程 burn-in、样本地板、可消费 PASS、人工批准和 rollback artifact。
- [ ] 更新 `docs/OPERATING_CONTRACT.md` 版本、回归不变量、xiaocao-trading skill 与相关 Automation contract。
- [ ] 首次 rollout 只接受 target revision、唯一 writer、依赖/私有配置、状态恢复和正式 selector readback 全部通过。
- [ ] 保留原 Book T account/positions/trades identity，不创建 Book T2，不补跑历史业务。
- [ ] 删除或废弃 `strategy/kol_reference.py` 的作者/alias 特判及 v1 静态方向权威，保留必要 migration readback。
- [ ] Cutover 后先验证一轮无重复成交、T+1、paired-switch、blocked-sell 和 account atomicity，再关闭 v1 compatibility。
- [ ] 任一 readback 不通过立即回滚到冻结 control，不允许两个 selector 同时写正式账。

## Comments
