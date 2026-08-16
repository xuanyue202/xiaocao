# 05 — 建立 v1 control / v2 shadow 与研究协议

**What to build:** 在同一冻结输入上运行现行 Book T control 和 v2 shadow，记录可执行模拟路径，并用 Book T 专属研究协议验收工程健康与策略增量。

**Blocked by:** 04 — deterministic selection plan.

**Status:** planned

- [ ] v2 artifacts 使用独立 namespace，禁止写正式 positions、account 或 trades。
- [ ] Control 与 shadow 绑定同日 market input、预算、费用、成交和流动性假设。
- [ ] 记录主题资格、未选原因、表达类型、模拟 fill、主题集中、换手、费用和 relative theme beta。
- [ ] 登记 Strategy Evolution Protocol，并由 `trend_guards`/`trend_optimize` 生成 research manifest/verdict。
- [ ] 20 个交易日 burn-in 只验工程；60 个交易日且 50 个有效主题决策才允许策略 promotion 判断。
- [ ] 报告复合收益、最大回撤、左尾、换手、集中度、walk-forward、非牛市留存和 ETF/股票条件结果。
- [ ] 单个赢家、单主题、单 KOL 或不可成交收益不能驱动 PASS；样本不足为 `pending_observation`。

## Comments
