# 02 — 建立标准主题与标的解析器

**What to build:** 建立 `resolve_theme_instruments(snapshot, catalog) -> ThemeInstrumentUniverse`，把 KOL 原始主题表述映射为标准主题，再连接小草 block、ETF 目录和趋势股成分，输出带 provenance 的候选宇宙。

**Blocked by:** 01 — snapshot schema and evidence identities.

**Status:** implemented

- [x] 建立稳定 `theme_id` registry、别名审核和变更记录；禁止在策略代码里追加作者专属 aliases。
- [x] 主题到 block/category、ETF tracking universe 和股票 constituents 的每条边都带来源与版本。
- [x] 解析冲突、多义词、未知主题和低置信映射保持 `unresolved`，不猜 code。
- [x] 每个 instrument 输出 code、类型、主题、映射证据、流动性、趋势与表达角色。
- [x] Resolver 对相同 snapshot/catalog 产生确定性相同结果，目录顺序或展示名变化不改变主题 identity。
- [x] Contract tests 覆盖宽主题、窄主题、多 ETF、一主题多股、同股跨主题和 unresolved。

## Implementation

- `src/xiaocao/strategy/theme_instrument_resolver.py` exposes the hash-bound
  `resolve_theme_instruments(snapshot, catalog)` seam and keeps unresolved
  mappings/ineligible instrument contracts visible without touching the paper
  ledger.
- `tests/test_theme_instrument_resolver.py` covers registry aliases,
  provenance, deterministic replay, multiple ETF/stock expressions,
  cross-theme stock identity, ambiguity, low confidence, and ETF metadata
  fail-closed behavior.

## Comments
