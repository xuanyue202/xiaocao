# Market data and CLI queries

Read this file only for quotes, market state, pools, sectors, indices, indicators, calendar or catalog queries.

## Data-source rules

- Cache first (`output/.cache/xiaocao.db`). For more than a few symbols/dates, batch small, space requests roughly 0.5–1 second and keep concurrency at or below about 8. Empty/null responses after bursts can be silent throttling.
- Always use exchange suffixes: `.XSHG`, `.XSHE` or `.BJSE`.
- Minute-line price is `trade`; `open/high/low/close` may be null. Historical minute requests need both `trade_date=YYYYMMDD` and `count=241`.
- Recent `date_kline` may lag. For live/EOD work, reconstruct recent daily OHLC/VWAP from minute `trade` rather than swallowing an empty daily response.
- Historical concept ranks are deeper than concept returns: `prePctChangeRate` is zero before roughly 2024-05-13. Cross-cycle return research must use stock-level `date_kline` or constituent reconstruction.
- Use `table` for human inspection, `json` for analysis and `csv` for export. Report the actual date returned.

## Market overview and environment

```bash
PYTHONPATH=src python3 -m xiaocao market overview --format json
PYTHONPATH=src python3 -m xiaocao market environment --date latest --format table
PYTHONPATH=src python3 -m xiaocao market week-stats --format json
PYTHONPATH=src python3 -m xiaocao market env-selection --date latest --format json
PYTHONPATH=src python3 -m xiaocao market env-minute --code 9A0001.XCHJZS --date latest --format json
```

## Quotes, minute lines, K-lines and auctions

```bash
PYTHONPATH=src python3 -m xiaocao quote realtime --codes 000001.XSHG,399001.XSHE,399006.XSHE --format table
PYTHONPATH=src python3 -m xiaocao quote realtime --codes 300750.XSHE --format table
PYTHONPATH=src python3 -m xiaocao quote realtime --codes 000001.XSHG,399001.XSHE --raw-line --format json
PYTHONPATH=src python3 -m xiaocao quote minute --code 300750.XSHE --freq 1min --adj bfq --format json
PYTHONPATH=src python3 -m xiaocao quote minute --code 300750.XSHE --freq 1min --adj bfq --trade-date 2026-04-28 --count 241 --format json
PYTHONPATH=src python3 -m xiaocao quote history --code 300750.XSHE --count 120 --freq D --adj qfq --format table
PYTHONPATH=src python3 -m xiaocao quote history --codes 300750.XSHE,000001.XSHG --count 20 --freq D --adj qfq --format csv --output output/batch_kline.csv
PYTHONPATH=src python3 -m xiaocao quote auction --code 300750.XSHE --date latest --format json
PYTHONPATH=src python3 -m xiaocao market each-trade --code 300750.XSHE --count 20 --format table
```

Prefer `quote` for ordinary stock/index data. Use lower-level `market` compatibility commands only for uncovered endpoints.

## Pools and sorting

```bash
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group dixi --format table
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group jieli --format table
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group qibao --format table
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group jingwang --format table
PYTHONPATH=src python3 -m xiaocao data sort --date latest --from-pool dixi --sort-key xiaocaoCJS --format table
PYTHONPATH=src python3 -m xiaocao data sort --date latest --from-pool dixi --sort-key directionCjs --sort desc --format table
PYTHONPATH=src python3 -m xiaocao catalog sort-keys --format table
```

Aliases: `dixi` 低吸; `jieli`/`lianban` 接力; `qibao`/`hpqb` 红盘起爆; `jingwang` 竞王.

## Blocks and sectors

```bash
PYTHONPATH=src python3 -m xiaocao block rank --date latest --rank-model focus --format table
PYTHONPATH=src python3 -m xiaocao block category-rank --date latest --rank-model full --format table
PYTHONPATH=src python3 -m xiaocao block score --date latest --format json
PYTHONPATH=src python3 -m xiaocao block stocks --date latest --block-code 980338.ZHBK --format json
PYTHONPATH=src python3 -m xiaocao block stocks --date latest --category-code 000031.BKDL --format json
PYTHONPATH=src python3 -m xiaocao block detail --date latest --code T08.ZHBK --format json
PYTHONPATH=src python3 -m xiaocao block kline --code T08.ZHBK --count 60 --format table
```

Use `focus` for short-term strategy focus and `full` for broader reporting.

## Xiaocao and technical indicators

```bash
PYTHONPATH=src python3 -m xiaocao index stock --date latest --codes 300750.XSHE --format json
PYTHONPATH=src python3 -m xiaocao index stock --date latest --from-pool dixi --format table
PYTHONPATH=src python3 -m xiaocao index dynamic --date latest --index-name jinglong --format table
PYTHONPATH=src python3 -m xiaocao index industry-dynamic --date latest --index-name jinglong --format table
PYTHONPATH=src python3 -m xiaocao indicator smallgrass current --code 300750.XSHE --format json
PYTHONPATH=src python3 -m xiaocao indicator smallgrass current --codes 300750.XSHE,000001.XSHG --format json
PYTHONPATH=src python3 -m xiaocao indicator smallgrass history --code 300750.XSHE --freq D --count 120 --format json
PYTHONPATH=src python3 -m xiaocao indicator query current --code 300750.XSHE --indicator macd --format json
PYTHONPATH=src python3 -m xiaocao indicator query history --code 300750.XSHE --indicator boll --freq D --format json
```

Backend indicator names: `smallGrass`, `vol`, `amt`, `macd`, `rsi`, `kdj`, `boll`.

## Calendar, config and catalog

```bash
PYTHONPATH=src python3 -m xiaocao calendar latest --date today
PYTHONPATH=src python3 -m xiaocao calendar trade-days --start 2026-04-01 --end 2026-04-30 --format json
PYTHONPATH=src python3 -m xiaocao calendar next --date 2026-04-24
PYTHONPATH=src python3 -m xiaocao config show --format json
PYTHONPATH=src python3 -m xiaocao catalog list --format table
PYTHONPATH=src python3 -m xiaocao catalog groups --format table
PYTHONPATH=src python3 -m xiaocao catalog rank-models --format table
PYTHONPATH=src python3 -m xiaocao catalog freqs --format table
PYTHONPATH=src python3 -m xiaocao catalog adjs --format table
PYTHONPATH=src python3 -m xiaocao catalog indicators --format table
```

Live API health check: `PYTHONPATH=src python3 -m pytest tests/e2e -q`.
