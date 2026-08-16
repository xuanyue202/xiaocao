# 03 — 补齐 ETF 数据与交易制度契约

**What to build:** 为 Python API/cache、行情、模拟成交和组合模型增加 ETF 的显式 instrument metadata，使 ETF 在已验证制度下可进入 v2 shadow，而不是沿用股票假设。

**Blocked by:** 02 — resolver output contract.

**Status:** planned

- [ ] 封装 `/stock/etf_info`，cache-first、限流并保留 trade-date/provenance；不得用 `stock_info()` 假装 ETF 目录。
- [ ] 验证 ETF realtime、minute、daily/settlement 数据 contract；分钟价继续只读 `trade` 字段。
- [ ] 增加 `instrument_type / lot_size / settlement_cycle`，未知值 fail closed。
- [ ] 模拟 fill、T+1/可卖性、整手与费用从 instrument metadata 读取，不写死股票规则。
- [ ] 用 fake/缓存 fixture 覆盖 ETF 行情缺失、目录陈旧、制度未知、停牌、流动性不足和可成交路径。
- [ ] 所有 live/paper OHLCV 仍遵守专有 API 边界，公共源只可进入带 provenance 的研究工具。

## Comments
