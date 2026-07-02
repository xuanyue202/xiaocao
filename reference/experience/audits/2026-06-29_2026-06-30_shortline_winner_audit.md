# 2026-06-29/30 短线赢家覆盖审计

目的：复盘老师点名短线赢家、同日小草本地实盘/策略标杆股，判断它们是否在本地策略命中范围内；如果没有，解释是合理风控、执行时点不一致，还是规则盲区。

## 结论

`teacher_named_winners ∩ emitted_strategy/qibao = 0` 是旧规则下的事实起点，不是最终结论。补做最近一年 cache-only 验证后，真正结论是：

1. 五方光电不是老师 6/30 复盘点名股，但它是本地小草模式标杆：`emitted_strategy_hit + emitted_dixi_hit + paper_buy`。本地策略当天抓到的是光电/电子高低切里的低吸分支，而不是老师点名的红盘强攻分支。
2. 老师点名股整体并不“不合理”。它们作为盘后战果/方向强度样本是合理的，说明当日资金在打电子、光电、科创/20cm 的红盘起爆和强攻。
3. 但如果把老师点名股当成 9:25 必须买入清单，则需要分层：`open<=6/实体不过长` 可进入当前买入候选；`高开/长实体/近20cm` 不应被当成无效样本排除。2026-06-30 人工门后，`高开6%-10%` 子桶和 `limitlike` 子桶已升级为 **Book B 模拟盘** 买入模式，实盘仍无授权。
4. 真正不合理的是本地 qibao emitted 过度依赖绝对 `jssb`：多个老师赢家在 raw qibao 排名前列、行业/方向很强，但 `jssb` 低导致旧规则不能 emitted。最强盲点是金宏气体：raw rank #6、实体 3.70 在窗口内、`xcjw=277.23`、`shortLine=174.01`，主要被低 `jssb=8.20` 过滤。
5. 已验证并落地一个独立分支：`标杆短线起爆 = raw qibao rank <= 10 + 电子行业或20cm + open<=6 + 红盘 + 非涨停/非强实体`。这不是放宽原 `红盘起爆主攻` 的 jssb 阈值，而是新增 rank-based 标杆分支；同时新增 `benchmark/watchlist/research cohort` 中间层承接高开/强攻样本。

## 近一年验证与落地

- 数据：`output/.cache/xiaocao.db`，2025-07-01..2026-06-29，qibao 222 个交易日，pool index 覆盖 62074/62074，open->next-close 有收益 29294/62074。
- 旧严格 qibao：2 笔/2 天，spread -5.74pp，REJECTED。
- raw top10 + 电子/20cm + open<=6 + 红盘非涨停：164 笔/114 天，strat +4.98% vs qibao pool base +1.01%，spread +3.97pp，train +3.68pp / test +4.27pp，Bonferroni n=7 后 PASS。
- raw top10 + 电子/20cm + 高开>6 + 非涨停化：日线 open->next-close 72 笔/60 天，spread +3.50pp，Bonferroni n=6 后 PASS；进一步补齐 cohort 分钟线后，用日线开盘价换算到分钟 bfq 价格轴，再按 09:30-09:31 `open*1.005` 限价触价成交 -> 次日分钟收盘口径，110 笔/82 天，spread +2.96pp，train +2.57pp / test +3.34pp，Bonferroni n=8 后 PASS。说明“高开”不是无效样本；2026-06-30 人工门后，`open 6%-10%` 子桶升级为 Book B 模拟盘 `高开标杆起爆`，`open>10%` 仍留 watchlist。
- raw top10 + 电子/20cm + 近20cm/长实体：日线 open->next-close 155 笔/112 天，spread +12.10pp，Bonferroni n=6 后 PASS；进一步补齐 cohort 分钟线后，fill-aware 223 笔/141 天，spread +11.24pp，train +11.59pp / test +10.90pp，Bonferroni n=8 后 PASS。说明正帆/联得/聚和这类是强攻标杆，不应从复盘样本排除；2026-06-30 人工门后升级为 Book B 模拟盘 `强攻标杆起爆`，但不代表实盘追涨授权。
- 补数纪律：只补 `high_open_watch/limitlike_watch` 目标 code-day，614 个缺失分钟线请求中 613 成功、1 空、0 失败；未补整个 qibao 池。fill-aware base 使用同日 qibao 全池日线 open->next-close 均值，避免把只补的 watchlist 样本当 base。
- 代码落地：新增 `标杆短线起爆` emitted 分支；2026-06-30 追加 `高开标杆起爆`、`强攻标杆起爆` 两个 paper-only emitted 分支；新增 `rawQibaoRank/qibaoRankScore`，推荐层和 quality governor 用 rank score 而不是低 `jssb` 评分。
- cohort 落地：新增 `qibao_raw_top10_elec20_buyable`、`qibao_raw_top10_elec20_high_open_watch`、`qibao_raw_top10_elec20_limitlike_watch`，authority=0，写入 `output/cohorts/cohort_snapshots.jsonl`。
- 回放老师点名股：交集从 0 变为 4 只。6/29 命中怡达股份；6/30 命中雷曼光电、信濠光电、金宏气体。

## 6/30 本地标杆：五方光电

| 股票 | 老师是否点名 | 本地状态 | 小草指标/证据 | 第一性原理判断 |
|---|---:|---|---|---|
| 五方光电 002962.XSHE | 否 | `emitted_strategy_hit`、`emitted_dixi_hit`、Book A/B 纸面买入 | `首红断低吸`；recommend `★KP2/★B2`；primary 398.8；rank 80.9；open -4.82；pct +4.87；entity +10.18；xcjw 285.9；cjs 141.12；directionCjs 1270.93；电子行业 1/66；Book A 800股 + Book B 400股，20.05 成交 | 这是本地低吸分支的有效样本：深水开、方向强、xcjw/cjs 结构强，买点是高低切环境里的低位光电补涨低吸，不是追老师点名的红盘扩张。此前只放在 local_evidence 不够，应作为本地模式标杆复盘。 |

## 6/30 老师点名短线赢家

| 股票 | raw qibao | 关键指标 | 是否 emitted | 过滤原因 | 是否合理 | 洞察 |
|---|---:|---|---:|---|---|---|
| 雷曼光电 300162.XSHE | #1 | pct +10.92；open +4.34；entity +6.31；xcjw 133.02；jssb 31.43；shortLine 168.15；电子 1/66 | 是：`标杆短线起爆` | 新分支命中 raw #1、电子/20cm、open<=6、红盘非涨停；旧规则因低 `jssb` 漏掉 | 合理纳入 | 这是老师点名样本里最直接的 rank-based qibao 标杆之一。 |
| 正帆科技 688596.XSHG | #2 | pct +19.88；open +7.07；entity +11.97；xcjw 163.24；jssb 28.82；shortLine 201.77；半导体方向 | `limitlike_watch` | 高开、20cm 强攻、实体过大；不进当前 buyable 分支 | 不自动买，但必须保留标杆 | 不是“应该排除”的无效样本。近一年同类 `raw_top10_elec20_limitlike_watch` PASS，正帆应作为科创/20cm 强攻 benchmark/watchlist，暂不直接变成 paper-buy。 |
| 信濠光电 301051.XSHE | #4 | pct +11.62；open +3.57；entity +7.78；xcjw 137.07；jssb 9.30；shortLine 145.0；电子 1/66 | 是：`标杆短线起爆` | 新分支命中 raw #4、电子/20cm、open<=6、红盘非涨停；旧规则因低 `jssb` 漏掉 | 合理纳入 | 与雷曼同属光电方向，验证“行业电子/光电 + raw rank”比绝对 jssb 更贴近老师短线标杆。 |
| 联得装备 300545.XSHE | #5 | pct +20.00；open +4.05；entity +15.33；xcjw 134.8；jssb 8.74；trendStart=1；20cm | `limitlike_watch` | 20cm 涨停化/强实体；不进当前 buyable 分支 | 不自动买，但必须保留标杆 | 作为“老师点名战果”合理，且同类历史 PASS；应进入强攻 watchlist，而不是从标杆样本里排除。 |
| 金宏气体 688106.XSHG | #6 | pct +5.90；open +2.12；entity +3.70；xcjw 277.23；jssb 8.20；shortLine 174.01；mainStart=1；电子/半导体 | 是：`标杆短线起爆` | 新分支命中 raw #6、电子/20cm、open<=6、红盘非涨停；旧规则主要被低 `jssb` 卡死 | **已修复盲点** | 这是本批最能证明规则不合理的样本：按第一性原理它是可执行窗口内的强方向标杆，新增分支后已覆盖。 |
| 聚和材料 688503.XSHG | #9 | pct +19.87；open +2.80；entity +16.61；xcjw 199.6；jssb 5.59；shortLine 174.88 | `limitlike_watch` | 强实体、接近 20cm；不进当前 buyable 分支 | 不自动买，但必须保留标杆 | 它不是高开问题，而是强实体/近20cm问题；同类历史 PASS，应作为强攻 benchmark/watchlist。 |
| 京东方A 000725.XSHE | 无 | pct +9.18；open +2.52；entity +6.50；xcjw 0；jssb 0；shortLine 180.22；大票/中军 | 否 | 不是短线 entry 模式，缺少 xcjiw/jssb/cjs 入口证据 | 合理不买 | 老师点它是玻璃基板/光电中军和方向确认，不是纯短线起爆。应进入方向/中军观察，不该要求 emitted。 |
| 富满微 300671.XSHE | 无 | pct +20.00；open -2.23；entity +22.74；xcjw 61.62；jssb 0；shortLine 158.84；盘中强攻 | 否 | 盘中后置强攻，不在 9:25 emitted 面 | 合理不买 | 暴露的是盘中方向扫描缺口，不是早盘 qibao 规则问题。 |

## 6/29 老师点名短线赢家

| 股票 | raw qibao | 关键指标 | 是否 emitted | 过滤原因 | 是否合理 | 洞察 |
|---|---:|---|---:|---|---|---|
| 太极实业 600667.XSHG | #3 | pct +7.89；open +3.57；entity +4.17；jssb 33.76 | 否 | `jssb` 不够，entity 略超 | 半合理 | raw #3 且老师明确命中，说明 rank 信息有价值；但实体/涨幅已经偏追，不能直接买。 |
| 宏微科技 688711.XSHG | #5 | pct +13.42；open +9.11；entity +3.95；jssb 20.72；电子 1/66 | `high_open_watch` | 高开执行风险；不进当前 buyable 分支 | 不自动买，但必须保留标杆 | 高开一刀切排除是错的。近一年 `raw_top10_elec20_high_open_watch` PASS；宏微应进高开强攻 watchlist/research cohort。 |
| 怡达股份 300721.XSHE | #10 | pct +11.72；open +2.03；entity +9.49；jssb 7.73 | 是：`标杆短线起爆` | 新分支命中 raw #10、20cm、open<=6、红盘非涨停；旧规则因低 `jssb` 和实体强漏掉 | 合理纳入但边缘 | 它处在 rank top10 尾部且实体较强，能纳入但不应继续放宽到 top10 之外或高开票。 |
| 南大光电 300346.XSHE | #11 | pct +15.21；open +6.09；jssb 7.54 | 否 | 高开/强攻，`jssb` 低 | 合理不买 | 更像方向延续和半导体材料样本，不应机械转买入。 |
| 士兰微 600460.XSHG | #21 | pct +4.39；open +4.98；entity -0.57；jssb 4.57 | 否 | 非红盘实体起爆，`jssb` 低 | 合理不买 | 更偏电子/半导体方向示例，不是本地 entry。 |
| 神工股份 688233.XSHG | #25 | pct +20.00；open +13.71；jssb 3.88；20cm | 否 | raw rank #25，超出 top10 cohort；高开/涨停追入风险极高 | 合理不买 | 老师作为强攻战果合理；但它不是当前 raw top10 qibao cohort 的样本，先不扩到 top25。 |

## 规则复盘

### 过滤与保留要分层

- 20cm/接近涨停且实体已经很大：联得装备、正帆科技、聚和材料。旧说法“应该排除”不准确；它们不适合作为当前低风险 paper-buy，但必须进入 `limitlike_watch`，因为近一年同类样本通过日线和 fill-aware 双重研究护栏。
- 高开但实体未涨停化：宏微科技。高开不是天然排除项；应进入 `high_open_watch`。fill-aware 后仍 PASS，但收益弱于 `limitlike_watch`，且 `open>10%` 胜率明显更差，应作为高开观察桶而非直接买入规则。
- raw rank 尾部且高开涨停化：神工股份。它是老师强攻战果合理样本，但不在当前 raw top10 cohort 内，暂不扩边界。
- 中军/方向确认但非 entry：京东方A。它是玻璃基板/光电方向和中军稳定性样本，不该进入短线命中统计。
- 盘中后置机会：富满微。不是 9:25 策略应该负责的范围。

### 最需要研究的规则问题

旧 qibao emitted 过度依赖绝对 `jssb`。在趋势尾声/高低切/短线增强环境下，老师赢家集中出现在 raw qibao 前排，但 `jssb` 普遍远低于 emitted floor。验证后落地的不是放宽主规则，而是新建独立 rank-based 分支：

```text
标杆短线起爆 = raw_qibao_rank <= 10
           + (行业电子 OR 20cm)
           + open_pct <= 6
           + entity_pct > 0
           + 非涨停/非接近涨停/非长实体
```

这个分支命中金宏气体、雷曼光电、信濠光电、怡达股份；正帆科技、联得装备、聚和材料进入 `limitlike_watch`；宏微科技进入 `high_open_watch`；神工股份因 raw rank #25 不进入当前 top10 cohort。

### 对老师点名本身的评价

老师点名短线赢家本身合理，但它的用途不是“全部转成早盘买入信号”。它更像三类标签：

1. 可执行标杆：低风险窗口内、raw rank 靠前、方向强，但未 emitted，例如金宏气体候选型。
2. 方向/赚钱效应标杆：已经强攻或涨停，例如联得、正帆、聚和；这类进入 watchlist/research cohort，不直接 paper-buy。
3. 中军/盘中/后置观察：京东方、富满微。

因此，“交集为 0”的真正洞察不是小草老师错，也不是本地全错，而是本地缺少一个从老师战果里学习的 rank-based 短线标杆分支，以及缺少 benchmark/watchlist/research cohort 中间层。XH-037 已用近一年本地数据 PASS 并落地；高开/强攻两组在补分钟线后的 fill-aware 研究里也 PASS，但先进入 authority=0 的 watchlist/research cohort，等 §10 人工门再决定是否升级为买入规则。
