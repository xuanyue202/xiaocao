# 05 — 建立 v1 control / v2 shadow 与研究协议

**What to build:** 在同一冻结输入上运行现行 Book T control 和 v2 shadow，记录可执行模拟路径，并用 Book T 专属研究协议验收工程健康与策略增量。

**Blocked by:** 04 — deterministic selection plan.

**Status:** implemented

- [x] v2 artifacts 使用 `book_t_v2_shadow` 独立 namespace，禁止写正式 positions、account 或 trades。
- [x] Control 与 shadow 绑定同日 market input、预算、费用、成交和流动性假设；混入不同 hash fail-closed。
- [x] 记录主题资格、未选原因、表达类型、模拟 fill、主题集中、换手、费用和 relative theme beta。
- [x] 登记 `trend-book-t-v2-shadow-v1` Strategy Evolution Protocol，由 `trend_guards` 生成结构化 verdict/manifest。
- [x] 20 个交易日 burn-in 只验工程；60 个交易日且 50 个有效主题决策才允许策略 promotion 判断；不足返回 `pending_observation`。
- [x] 报告复合收益、最大回撤、左尾、换手、集中度、walk-forward、非牛市留存和 ETF/股票条件结果。
- [x] 单个赢家、单主题、单 KOL 或不可成交收益不能驱动 PASS；v1 control 仍是明日正式 Book T 模拟消费者。

## Comments

## Implementation

- `src/xiaocao/research/book_t_shadow.py` provides the hash-bound daily runner,
  cross-day research gate, trend-guard verdict, anti-concentration coverage,
  and namespaced artifact writer.
  The control side also requires a canonical v1 trend-only receipt whose
  positions/account/trades hashes are verified against the current paper files
  before the shadow research result is consumed.
- `scripts/book_t_shadow.py` is the consumer CLI. `--runtime-check` is read-only;
  it confirms tomorrow's v1 `paper_record.py --trend-only` path and reports the
  v2 shadow as a separate research namespace. A dated frozen v2 input is
  optional in `scripts/auto_daily.sh`; if present, `morning-execute` consumes it
  and accumulates prior isolated frozen inputs without touching the formal T
  account. Shadow failure is supporting-layer degradation after the v1 control
  result, not a reason to report the formal consumer as failed.
- `reference/experience/research_protocols.yaml` registers the v2 shadow
  protocol. Issue 06 remains blocked until the burn-in, sample floor, research
  consumption gate, human approval, and rollback readback are all present.
- Valid-decision counts use a substantive selection fingerprint rather than
  counting repeated no-op plans. Historical control receipts are retained in
  immutable frozen-input artifacts; only a newly consumed day's receipt is
  checked against the current v1 files.
- `paper_record.py --trend-only` emits the dated receipt after the successful
  formal T result; a receipt-write issue is recorded as supporting degradation
  and does not rewrite the v1 account result.
