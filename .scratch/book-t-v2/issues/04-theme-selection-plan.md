# 04 — 实现主题槽位选择计划

**What to build:** 建立 `select_book_t(portfolio, snapshot, universe) -> BookTSelectionPlan`，按层级资格选择最多三个主题及其 ETF/核心股表达，并每天重判 incumbents。

**Blocked by:** 01, 02, 03.

**Status:** implemented

- [x] 候选判断必须先于空槽计算；满仓时仍生成完整 snapshot/universe/plan。
- [x] 资格层级不可相互补偿，未选原因记录第一失败层级。
- [x] 一主题内 ETF、股票或组合合并计算预算、相关性和集中度；总预算不超过独立 T 账户 30%。
- [x] 主题表达选择使用广度、龙头清晰度、相对强度、流动性、成本和可交易性，不按 KOL 数量加权。
- [x] challenger 仅在连续两个有效评估中显著胜出且覆盖费用/风险差异时形成 paired-switch。
- [x] Snapshot/ledger/metadata 不可用时保留既有风险管理、暂停新买和主动换仓，不回退 v1 静态词表。
- [x] 保留 T+1、blocked sell、宽回撤、成对切换和原子 ledger seam；本 issue 只输出 plan，不写正式账。

## Implementation

- `src/xiaocao/strategy/book_t_selector.py` implements the hash-bound,
  deterministic `select_book_t` plan seam. It evaluates incumbents before
  filling empty theme slots, selects ETF/stock expressions inside a theme,
  applies the 30% / three-slot paper budget, and keeps all lower-layer
  rejections visible with their first failure layer.
- `tests/test_book_t_selector.py` covers the public seam for budget caps,
  ETF-plus-core-stock expressions, hierarchical fail-closed behavior, full
  portfolio reevaluation, two-evaluation challenger hysteresis, missing-input
  pause semantics, and plan hash binding.

- The selector is read-only: it emits no fills, ledger rows, account changes,
  or v1 static-strategy fallback.

## Comments
