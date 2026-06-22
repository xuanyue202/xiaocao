# Data Quality & Governance — what's trustworthy for what

> Born from a research session that stepped on the same class of pothole three
> times. The root cause was always the same: **treating "the API/cache returned
> something for date D" as "there is valid data for date D".** There isn't,
> necessarily. Read this before backtesting across time.

## The one rule: request-reachable range ≠ data-valid range

Every endpoint has TWO date ranges, and **the bugs all live in the gap between them**:

- **Request-reachable** — the dates the `date`/`paramTime` param will accept without erroring.
- **Data-valid** — the dates whose response actually carries usable *content* (non-null, non-zero, non-empty).

The cache's param coverage shows request-reachable. It will happily hold rows for
dates where the API returned zeros / nulls / an error envelope. A backtest that
trusts param coverage silently trains on garbage. **Always validate content, not
param presence.**

## Trust map (data-valid ranges, verified by content inspection)

| data | endpoint | data-valid range | governance notes |
|---|---|---|---|
| **daily prices** (O/H/L/C, vol, amt, isLimitUp) | `date_kline` | **2019-10 → 2026-06** for fetched codes (495 deep, pre-2023) | the ONE deep, reliable foundation. Broad-universe cache is shallow (2025-05+, 260-bar). Fetch deep per-code with `count`. |
| **minute prices** | `minute_line` | 2025-07 → 2026-06 | per-minute price is in `trade` (O/H/L/C are null). Used to reconstruct daily bars when `date_kline` lags. |
| **per-stock 小草 signals** (xcjw, 竞王, 断板, isWeak…) | `xiao_cao_index_v2` | **2025-01 → 2026-05 ONLY** | params "reach" 2022-06 but return empty. This is why the **short-line book cannot be backtested before ~2025** — its signal inputs don't exist. |
| **concept/sector rankings** (`num`, name) | `xiao_cao_block_category_rank_v3` | rankings 2023-01 → 2026-05 | but see returns ↓ |
| **concept RETURNS** (`prePctChangeRate`) | same | **2024-05-13 → 2026-05 ONLY** | zero before that. Backtesting concept *returns* on pre-2024-05 ranks trains on zeros (it faked a +20~28pp cross-cycle alpha). |
| **industry block rank** | `xiao_cao_industry_block_rank` | 2025-01 → 2026-05 | only 7 coarse super-blocks, `blockName` null — too coarse for leader work. |
| **focus pool / sort / block constituents** | `focus_xiao_cao_index`, `sort_v2`, `get_code_by_xiao_cao_block` | 2025-01 → 2026-05 | opaque ranking metrics (e.g. `sortId=38`); not transparent enough for a defensible backtest. |
| **short-line trade outcomes** | `mode_history` (table) | 2025-01 → 2026-05 (bull only) | the short-line book's realized record. `return_pct` is execution-juiced realized PnL (mean +2.3% but **median −1.3%**), matches NO raw price convention — never compare it to a raw price change. |
| **stock master** (tradableAShare, statusType) | `stock_info` | current snapshot, no `type` field | filter big-caps on `statusType==1` (1=tradable, 99=index); `type` is always null (the old filter returned an empty pool). |

**The structural asymmetry that bounds everything:** *prices* go deep (2019/2021+),
but every *小草-derived signal* (per-stock metrics, concept returns, mode_history)
is shallow (~2025+). So **cross-cycle questions are answerable for price/beta
behavior, but NOT for the 小草 signal book** — that one is forward-data-gated.

## Caching gotchas (silent data loss)

- **`date_kline` with `param_time=""` is NOT persisted** — it's treated as volatile/latest (`is_historical=False` → `should_persist=False`). It fetches fine but caches nothing; re-reads find an empty/shallow cache. **Pass a past `param_time`** (e.g. last close) so `count=N` history persists.
- **Empty/error responses can be cached** for non-historical endpoints — don't count a cached row as data.
- **`bfq` (unadjusted) prices have split jumps** — a cross-split window shows a fake −14% (新易盛 6/1→6/19). Use `qfq` for multi-day return math; flag bfq with ⚠split.
- **`date_kline` daily feed can lag weeks** — froze at 2026-05-29 for ~3 weeks. `data_health.stale_market_cache` flags it at eod; reconstruct recent bars from `minute_line`.
- **Codes need the exchange suffix** (`.XSHG/.XSHE/.BJSE`); bare codes return empty.
- **Rate-limit**: ~10 sequential OK, ~60 burst → silent empty `[]`. Space calls (~0.7–1.2s), cache-first, ≤8 concurrent.

## Pre-backtest checklist (so this doesn't recur)

1. **Validate content, not coverage** — for the date range you'll use, confirm the response field you depend on is non-null/non-zero (not just present). One probe per endpoint at the OLDEST date you'll touch.
2. **Pin the data-valid floor** — restrict the backtest window to the data-valid range above; drop earlier days explicitly (see `research_trend_crosscycle.py:_real_return_panel`).
3. **Audit the return convention** — know whether a "return" field is a raw price change or an execution-juiced realized PnL before comparing two series (the −4,602 / +20pp traps).
4. **Lag every regime/feature** — a feature computed from a trailing window through day *i* must EXCLUDE day *i* if you act on day *i* (else lookahead; it faked a +0.78 Sharpe sit-out edge).
5. **Confirm it cached** — after a historical fetch, read it back from cache; if the deepest series isn't there, you hit the `param_time` persistence trap.

## The three artifacts this governance would have prevented (2026-06)
- **zero-data**: backfilled concept *ranks* 2023-24, but returns were 0 pre-2024-05 → fake +20~28pp.
- **bull-window**: +6~20pp trend alpha from a single bull sample, gone under walk-forward.
- **lookahead**: regime included the day's own return → fake cash-in-bear edge, reversed once lagged.

All three were caught before reaching the ledger — but each cost a round-trip. This doc is the cheaper path.
