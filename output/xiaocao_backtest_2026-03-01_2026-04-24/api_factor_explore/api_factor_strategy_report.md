# 小草新 API 因子探索与策略完善验证

## 结论先行

- `xiao_cao_index_v2` 已经包含价位透视和特色因子，不需要另起接口才能用：`cgyk/htyk`、`position/finalPosition/openPosition/realPosition`、`trendGroup/mainStart/limitupGene/isWinner/shortLineScore` 等都在个股指数详情里。
- 探测了一批可能的独立“价位透视/特色因子”接口名，均为 404；当前可用入口应优先围绕 `xiao_cao_index_v2` 全字段挖掘。
- `sort_v2` 目前对传入的 `stockIds/stockCodes/date/tradeDate` 不做可靠子集排序，返回更像全市场当前排序；现有 CLI 过滤后经常退回原列表，因此策略里的“排序增强”实际不稳定。
- 用 28 笔原模拟盘闭环 case 做归因，最差贡献来自 `接力低弱转2`；只保留 `接力低弱转1 + 首红断低吸 + N字低吸`，样本内均值从 `0.49%` 提到 `3.54%`。再叠加 `openPctChangeRate <= 5`，样本内均值到 `5.22%`，胜率 `72.73%`。
- 用同一交易区间重跑“本地按 API 字段排序”的候选策略，`mode_v2_sort` 优于原始池顺序：平均 `1.02%` vs `0.50%`；`xcjw_sort + 模式优选 + open<=5` 达到平均 `1.68%`、胜率 `54.12%`，样本量 170 笔，比只看 28 个原 case 更有参考价值。

## API 字段能力

| 类别 | 已发现字段 |
| --- | --- |
| 模式分数 | xcjw/xcjwV2, jsjl/jsjlTest/jsjlBlock, cjs/cjsV2/cjsTest/cjsBlock/directionCjs/directionCjsV2, jssb/jssbV2/jssbTest |
| 价位透视 | position/finalPosition/openPosition/realPosition, cgyk/htyk/minuteCgyk/minuteHtyk 及 value 字段 |
| 形态标签 | isWeak/isBottom/isLow/isMeso/isMedium/isHigh/isHighest/isHalf/isGestationLine/isUpBroken/isDownBroken 等 |
| 开盘结构 | isSmallHighOpen/isMiddleHighOpen/isLargeHighOpen/isSmallLowOpen/isMiddleLowOpen/isLargeLowOpen, openPctChangeRate |
| 趋势/特色因子 | shortLineScore/shortLineScoreChange, trendGroup/trendBack/trendStart/trendGroup10, mainStart/mainFrequent, limitupGene, isWinner |
| 市值/活跃度 | marketValue/circulationMarketValue, atraderate10d/atraderate30d |

完整字段和 case 明细见 `cases_enriched.json/csv`。

## 原 case 分模式表现

| 模式 | 笔数 | 平均 | 中位数 | 胜率 | 最佳 | 最差 |
| --- | --- | --- | --- | --- | --- | --- |
| 首红断低吸 | 4 | 4.27% | 4.36% | 75.00% | 9.89% | -1.54% |
| N字低吸 | 1 | 3.69% | 3.69% | 100.00% | 3.69% | 3.69% |
| 接力低弱转1 | 8 | 3.16% | 0.65% | 50.00% | 19.95% | -9.44% |
| 接力低弱转2 | 14 | -1.86% | -2.64% | 35.71% | 10.55% | -12.27% |
| 孕线低吸 | 1 | -6.42% | -6.42% | 0.00% | -6.42% | -6.42% |

## 原 case 内规则验证

| 规则 | 笔数 | 平均 | 中位数 | 胜率 | 最佳 | 最差 |
| --- | --- | --- | --- | --- | --- | --- |
| htykValue>=0.03 | 3 | 9.95% | 9.89% | 66.67% | 19.95% | 0.00% |
| 接力只留低弱转1，低吸只留首红/N字，且cgyk>=0 | 9 | 5.78% | 3.69% | 66.67% | 19.95% | -1.90% |
| 模式优选+开盘涨幅<=5 | 11 | 5.22% | 4.00% | 72.73% | 19.95% | -5.22% |
| cgykValue>=0.05 | 3 | 4.57% | 3.69% | 100.00% | 9.89% | 0.14% |
| 模式优选+非强度衰减 | 9 | 3.91% | 1.30% | 55.56% | 19.95% | -9.44% |
| 仅接力低弱转1+首红断低吸+N字 | 13 | 3.54% | 3.69% | 61.54% | 19.95% | -9.44% |
| 排除接力低弱转2 | 14 | 2.83% | 2.49% | 57.14% | 19.95% | -9.44% |
| 剔除大高开 openPctChangeRate>5 | 24 | 1.51% | 0.72% | 54.17% | 19.95% | -12.27% |

## 原 case 内高价值因子线索

| 因子切分 | 笔数 | 平均 | 中位数 | 胜率 | 均值提升 | 胜率提升 |
| --- | --- | --- | --- | --- | --- | --- |
| xcjwV2>=376.6 | 5 | 8.94% | 10.55% | 80.00% | 8.45% | 33.57% |
| marketValue<=3.6e+09 | 5 | 8.73% | 10.55% | 100.00% | 8.24% | 53.57% |
| circulationMarketValue<=3.524e+09 | 5 | 8.73% | 10.55% | 100.00% | 8.24% | 53.57% |
| htykValue>=0.0066 | 5 | 8.72% | 9.89% | 80.00% | 8.23% | 33.57% |
| minuteCgykValue>=0.01845 | 5 | 7.93% | 8.73% | 100.00% | 7.45% | 53.57% |
| xcjwV2>=324.8 | 6 | 7.45% | 10.30% | 66.67% | 6.96% | 20.24% |
| entityPctChangeRate>=2.055 | 6 | 7.29% | 6.79% | 83.33% | 6.80% | 36.90% |
| marketValue<=4.109e+09 | 6 | 7.02% | 5.92% | 83.33% | 6.53% | 36.90% |
| entityPctChangeRate>=3.335 | 5 | 6.73% | 3.69% | 80.00% | 6.25% | 33.57% |
| htykValue>=0.00235 | 7 | 6.60% | 3.69% | 85.71% | 6.11% | 39.29% |
| cgykValue>=0.02865 | 5 | 6.50% | 8.73% | 100.00% | 6.01% | 53.57% |
| entityPctChangeRate>=1.31 | 9 | 6.12% | 3.69% | 88.89% | 5.63% | 42.46% |

注意：这里是 28 笔小样本内切分，只能作为候选线索，不能直接当最终参数。

## 同区间策略变体重跑

| 变体 | 信号数 | 闭环数 | 平均 | 中位数 | 胜率 | 最佳 | 最差 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pool_order | 31 | 31 | 0.50% | 0.00% | 48.39% | 19.95% | -13.27% |
| xcjw_sort | 370 | 369 | 0.70% | 0.12% | 50.41% | 26.02% | -19.15% |
| mode_score_sort | 162 | 162 | 0.73% | 0.12% | 51.23% | 21.89% | -19.15% |
| mode_v2_sort | 167 | 167 | 1.02% | 0.12% | 51.50% | 21.91% | -19.15% |
| xcjw_sort + 排除接力低弱转2 | 311 | 311 | 0.91% | 0.26% | 52.09% | 26.02% | -19.15% |
| xcjw_sort + 模式优选 | 179 | 179 | 1.43% | 0.35% | 52.51% | 26.02% | -15.47% |
| xcjw_sort + 模式优选 + open<=5 | 170 | 170 | 1.68% | 0.61% | 54.12% | 26.02% | -15.47% |

变体说明：
- `pool_order`：尽量复刻当前池顺序逻辑。
- `xcjw_sort`：拿到池内个股详情后，按 `xcjw` 本地排序，再执行原规则。
- `mode_score_sort`：接力按 `jsjl+xcjw`，低吸/方向按 `cjs+xcjw` 本地排序。
- `mode_v2_sort`：优先使用新字段 `jsjlTest/cjsTest/directionCjsV2/xcjwV2` 排序。

## 建议策略改造

1. 先修正排序语义：不要依赖 `sort_v2` 对传入股票列表排序，改为取 `xiao_cao_index_v2` 全字段后在本地排序。
2. 接力不要把 `接力低弱转2` 作为同等权重默认买点；它在原 case 中均值 `-1.86%`，在当前样本中是主要拖累项。
3. 默认候选先用“模式优选”：`接力低弱转1 + 首红断低吸 + N字低吸`，暂不纳入 `孕线低吸` 和 `接力低弱转2`，除非有额外因子确认。
4. 加开盘结构过滤：`openPctChangeRate <= 5`，避免过高开买入；该规则在原 case 和扩展变体里都改善收益。
5. 把价位透视作为二级加分而不是硬过滤：`cgykValue/htykValue/minuteCgykValue` 在小样本里很强，但覆盖率低，适合做排序加分。
6. 建议下一版评分公式：`mode_score + xcjwV2 + directionCjsV2 + price_perspective_bonus - high_open_penalty`，按模式分池排名，控制每日最多 3-5 只。

## 输出文件

- case 全字段 JSON：`/Users/bytedance/coding/xiaocao/output/xiaocao_backtest_2026-03-01_2026-04-24/api_factor_explore/cases_enriched.json`
- case 全字段 CSV：`/Users/bytedance/coding/xiaocao/output/xiaocao_backtest_2026-03-01_2026-04-24/api_factor_explore/cases_enriched.csv`
- case 因子报告 JSON：`/Users/bytedance/coding/xiaocao/output/xiaocao_backtest_2026-03-01_2026-04-24/api_factor_explore/factor_report.json`
- 策略变体报告 JSON：`/Users/bytedance/coding/xiaocao/output/xiaocao_backtest_2026-03-01_2026-04-24/api_factor_explore/strategy_variant_report.json`
- `xcjw_sort` 变体明细：`/Users/bytedance/coding/xiaocao/output/xiaocao_backtest_2026-03-01_2026-04-24/api_factor_explore/variant_xcjw_sort_trades.csv`