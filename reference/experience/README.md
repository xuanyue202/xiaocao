# 小草知识库（Xiaocao Knowledge Base）

小草直播复盘蒸馏出的**判断先验 + 可证伪假设 + 飞轮裁决**的单一入口。任何 agent/人接手本项目，先读这页。

> **一条命令看现状**：`PYTHONPATH=src python3 scripts/xiaocao_knowledge.py`
> （现行 posture + 时效 + 候选/已测假设 + verdict 账本）

---

## 0. 红线（贯穿所有产物）

这些是**叙述/判断先验**，进 **agent 皮层**与**能力飞轮（当假设）**，**永不**进确定性脊柱、**永不**自动改参。一条小草的话在 `research_run.py` 给出 PASS 之前，对策略的权威 = 0。这正是小草本人的元规则：**标准 + 数据验证 + 当下行情适配，三缺一不可**。见 `docs/OPERATING_CONTRACT.md` §2、`docs/FLYWHEEL.md`「判断先验→候选假设」。

## 1. 产物地图（精华在哪儿）

| 文件 | 是什么 | 谁消费 / 何时 | 性质 |
|---|---|---|---|
| `June/*.md` | 原始转录（盘前+复盘，6/1–6/21，语音转文字有错别字） | 蒸馏输入 | 原料 |
| `distilled/<date>_<kind>.json` ×23 | 逐篇结构化提取（posture/方向/个股/方法/出场课/**decision_trace 实时判断链**/假设，已纠错） | 综合输入；按需回查 | 底料（append-only） |
| `docs/XIAOCAO_PLAYBOOK.md` | 道-法-术-纪律 + **第五节「实时盘面判断模型」**（盘前→竞价→9:31-9:35→盘中 的 if-then 表）。每条标 `[已编码]/[先验]/[待验]` | **agent 每日**：morning 看术/纪律framing，eod 用出场纪律做异常分诊 | 判断先验 |
| `REGIME_TIMELINE.md` | 逐日 dated posture（regime/龙头/valid_until/证伪条件）+ 现行 posture + 对小草本人的回测提醒 | morning 读现行 posture 定调 | 判断先验（会过期） |
| `posture_current.json` | 现行 posture 的**机器可读 SSOT**（as_of/valid_until/regime/falsifiers） | `xiaocao_knowledge.py` 读它判时效 | 判断先验 |
| `xiaocao_hypotheses.jsonl` | 17 条**可证伪候选**（XH-001..017），含 operationalization 配方 + status | 飞轮入口（candidate→护栏） | 候选假设（非 verdict） |
| `kronos_screen/HYPOTHESES.jsonl` | `research_run.py` 的 **verdict 账本**（PASS/REJECTED） | flywheel_selfcheck / 人工门③ | 裁决 |
| `output/research/*.jsonl` | 操作化某假设时建的逐笔 `{day,strat_ret,base_ret}` | research_run.py 输入 | 检验工件 |

## 2. 飞轮发现日志（hard-won 结论，别再走回头路）

> 这些是跑过护栏后**已确立**的认知。新发现往上加（保留日期）。

**2026-06-21 — 首轮飞轮（XH-016 / XH-001 / XH-011 全 REJECTED），收敛结论：**
1. **出场层中性**：逐笔配对归因 exit_timing **+0.10%/笔**（pnl_decompose.csv，realized=pick_alpha−entry_slippage+exit_timing）。出场不是漏点。
2. **「−4,602 出场漏点」是「真实的谎言」**：那是 book A（仅 6/15–17/9 笔，趋势期盈利）vs book B（6/2–18/38 笔，含早 6 月全部亏损）**不配对账本**的美元总和差，非出场质量差。（已 spawn 修 status.py headline。）
3. **真正可控的失血 = entry 追高（+1.2~1.7%/笔）+ 右尾未捕获**。追高直接对应小草第一铁律「买在 0-1%，不追高」。
4. **系统做的不是小草做的**：book B 持仓**零趋势龙头**，全是短线低吸 mode（首红断/绿断/红断/接力低弱转）。小草做趋势大票——这是最大结构性 gap（→ XH-013，**未测，需另搭主线回测**）。
5. **低吸 mode 全年正期望**（mode_history 335 天/4512 笔，mean **+2.3%**），即便坏 regime 也正（bear ~平 −0.02%、div +1.99%、trend_strong +4.17%）；**低胜率右偏**（median −2%，靠少数 +66% 拉正）。→ 「按 regime 一刀切禁低吸」**REJECTED**；lever 是**抓右尾**，不是禁用。
6. **June 亏损主因 = 低胜率策略在一段坏 regime 里的 variance**，不是任何单一可调参数。
7. **方法论沉淀**：mode 期望类假设可用 `mode_history` + `regime.derive_proxy_regime` **全年扩样**（已验证，XH-011 跑出 p=0.0003）；趋势主线类需用 cached `block_rank`+`date_kline` **另搭回测**；paper 实现账本类（出场归因）效应~0 已结论性、无需重跑。

**2026-06-22 — 第二轮飞轮（XH-017 连续广度恶化 / XH-013 趋势主线选股），两条都 REJECTED：**
8. **「死盘空仓」对低吸 book 不成立（三度证伪）**：XH-017 把小草的死盘信号精炼成**连续 N 天广度恶化**（不再是 XH-011 的单日 regime），全年 260 天、8 个变体（abs N∈{2,3}×tau∈{.35,.40,.45} + mono N∈{2,3}）无一通过，且**反向**（primary spread **−0.32%**, t=−3.0, p=0.003）。死窗内低吸收益 **≥** 非死窗（gap +0.3~+3.1%）——广度越烂，超卖反弹右尾越肥。**广度禁用低吸会误杀 winner。死盘空仓属于趋势龙头 book 的纪律，不是低吸 book 的。** 脚本 `scripts/research_breadth_filter.py`。
9. **「趋势主线」选股**（XH-013）：用户纠正定义——**不是龙头/高标/连板，是中长期趋势的主线（中军/核心大票），持有跟趋势**（playbook L14/28-31/59/108）。按**三个由浅入深、越来越忠实**的定义全跑了，**全部 ≈0 选股 alpha**：(i) 全市场 momentum-leader → 跑输市场（spread −0.04~−1.45，动量反转）；(ii) 60d 趋势**大票**（top-20% float-mktcap、平铺3、非重叠持有）→ 跑输大票市场（−0.42% vs **+2.64%**/10d）；(iii) **小草实际信号「轮动频率主线」**（block_category_rank 全年337日、概念在 top-K by num 的持续度、持有最持续主线）→ ≈ 平均题材（+1.03% vs +1.19%/10d，spread −0.16，p=0.247）。脚本 `research_leader_select.py`/`research_trend_mainline.py`/`research_rotation_mainline.py`。
10. **关键方法学纠错（又一个「真实的谎言」）**：v1 把 leader 的 1 日价格变化 vs 低吸的**执行加权 realized PnL**（mean +2.3% 但 **median −1.3%**，不 match 任何 date_kline 价格口径）直接比 → 不配对口径的伪差，已弃。改用**统一口径**（H 日 fwd close-to-close）后两个发现：(a) **低吸 picks 裸持有为负**（−0.43%/5d）→ 低吸的 +2.3% **100% 来自执行**（超卖入场 + 纪律出场），不是票好；(b) **市场（流动 top30%）+0.93%/5d 跑赢两个 universe 的选股** → 系统跑输主要是 **beta/参与度**（踏空上涨），呼应 6 月反事实。
11. **收敛结论（XH-013）**：这段样本里**「选对主线/龙头/趋势」没有可测的选股 alpha——三种忠实定义全收敛到 ~0**；6 月 +29.5% 反事实兑现的主要是 **beta + 题材参与 + 持有纪律**，不是机械选股因子。系统 6 月跑输的可复现 lever 是**参与度（别空仓/别用错 book 踏空趋势）**，不是「会挑主线」。**仍未被回测覆盖的 = 执行/择时 + 相机决策**（裸 fwd return 测不了，需系统真持有主线大票 + 小草进出纪律才能验证）。**修正上一版「忠实版无法从 cache 复现」——忠实版可测、已测=REJECTED**，缺的是执行层而非选股信号。

**2026-06-22 晚 — 用户纠正 #2（关键，部分推翻上面的 REJECTED）：趋势是平行系统、要长期主义、不能每天买卖。**
12. **上面 9-11 的 REJECTED 测的是「churn 的短线化趋势」，不是趋势长期主义**：那些用 **10-20 日反复重选**（恰好是 A 股**动量反转**区）+ **相对平均题材** + **短线 per-day 护栏**判。换成**低换手、长持有、绝对复利**口径（`scripts/research_trend_longhold.py`）结论**反转**：(a) **趋势确实赚钱**——hold top-3 趋势概念全年复利 **+22~57%**（最强单概念 算力芯片 **+80%**）；(b) **持有越长，alpha 越正**：rebalance≈季度（R=60/120d）时 vs 平均题材(beta) spread **+6~+20pp**，而 churn（R=20d）spread −4~+1pp ≈ 无/负；**所有长持配置都跑赢 beta，所有 churn 配置都不**；换手越低相对越好（=长期主义）。
13. **方法学元结论**：**确定性脊柱的 per-day 配对 t 护栏是为短线 book 造的,是评趋势 book 的错误仪器**（趋势 book 持仓少、长持、该用复利收益/回撤/换手评，不是 per-day 显著性）。两套平行系统 → 两套评估。**系统 6 月踏空 +29.5% 的真 lever = 没有在跑一条平行的趋势 book（长持主线大票）**，不是调短线参数、也不是「会挑票」。（限度:1 段 ~1.4yr **牛市**样本,绝对收益大头是 beta、alpha +6~20pp 真但需更多 regime 验证;概念等权≠小草持有的主线中军大票。）→ 新候选 **XH-018**(趋势 book:低换手长持主线,独立评估轨)。

**2026-06-22 深夜 — Book T Phase 1：把 #12 的 +6~20pp 放进严格仪器（`trend_guards`），部分回撤上面的乐观。**
14. **XH-018 的「选股 alpha」过不了严格 OOS**：建了 `src/xiaocao/research/trend_guards.py`（**非重叠 hold 为单位**，测 复利/最大回撤/换手/walk-forward(train+test alpha 都正)/per-hold 配对 t/**survives-non-bull**，无法验证非牛市则 fail-closed）。`scripts/trend_optimize.py` 全配置 **REJECTED**：+6~20pp alpha **只在长 hold 出现**（R60: +10.5pp、mdd **0.8%**、walk-forward train+test 都正）——但**只有 3 个独立 hold**（过不了 enough_holds≥8，t=1.5 p=0.27 不显著）；R≤40 有足够 hold 时 alpha 归零/转负；**非牛市 regime 的 alpha 在每个能测的配置里都是负的**。
15. **修正 #12 的「alpha」措辞**：之前 `research_trend_longhold.py` 的 +6~20pp 是**单路径、跨配置比较**的口径；非重叠 walk-forward + 非牛 + 显著性下**不成立**——它是**牛市 + 独立 hold 太少**的产物。**站得住的只有：趋势长持复利强（+44~52%）且回撤低（R60 mdd 0.8%）——这是 beta/参与度,不是被验证的选股 alpha。** Book T 的 lever = **参与（长持捕捉趋势 beta，系统踏空的就是这块）,不是「跑赢平均题材」**。`trend_rules`(选股器)因此推迟——没有被验证的选股 edge 可建。**仪器起作用了:它拒绝把牛市样本 artifact 当 edge 放行。**

**2026-06-23 — 汇合 allocator Loop（目标:穿越牛熊、样本外稳、风险调整复利最大化）。三轮,每轮诚实落账。**
16. **短线是 Sharpe-0.68 的全天候引擎(measured,robust)**(`scripts/research_regime_profile.py`):低吸 per-trade 风险调整收益**随 regime 单调**——bear +0.06%(Sharpe 0.01)→ divergence +2.0% → recovery +2.4% → trend_continuing +3.1% → **trend_strong +4.2%(Sharpe 0.49)**;**唯一负 regime 是 neutral(−0.20%)**=唯一「空仓更好」的窄区。**短线是组合的核心资产,几乎全 regime 正期望**(印证 XH-011:不该按 regime 禁用)。趋势长持 regime profile 在验证 horizon 上**只有 3 个 hold,测不了**。
17. **短线的 regime-条件 SIZING 不过样本外(SHELVED)**(`scripts/research_regime_sizing.py`):按 regime 缩放敞口(prop/sharpe/binary,等均值敞口=择时非杠杆),walk-forward 双向。OOS Sharpe Δ 一个方向 +、另一个方向 −(+0.03/−0.05、+0.04/−0.06、0/+0.02),**没有一种在两个方向都改善**。regime→edge 关系样本内单调但**两个半段间不稳定、不可外推**。**还缺什么才能定论**:更稳/可迁移的 regime 特征,或跨真实熊市的数据。
18. **两 book 不相关(ρ≈0,好!)但趋势 Sharpe 太低→汇合的风险调整增益≈0(SHELVED)**(`scripts/research_book_blend.py`):短线/趋势日收益相关系数 **ρ≈0 且两半段稳定**(−0.02/−0.11/+0.05)——分散化**真实可得**。但等风险 50/50 blend Sharpe +0.55 **< 短线单独 +0.68**,因趋势单独 Sharpe 仅 ~0.1;即便**最优风险权重** blend ≈ √(0.68²+0.1²) ≈ **0.69,只比短线单独高 +0.01**(R∈{20,40,60,120} 全一致)。**结论:分散化可得但趋势太弱,blend 现在不值当;要让汇合在风险调整上有意义,必须先把趋势 Sharpe 抬上去**(更好选股/大票中军/regime择时)——而这需要前向/大票数据,本 cache 给不了。
19. **Loop 阶段性结论(诚实的墙)**:可复现的最大风险调整资产 = **短线 book(Sharpe 0.68,全天候)**;趋势 = 参与/beta 对冲(捕捉踏空的 beta),非 Sharpe 改善器。**穿越牛熊无法验证(样本无真实熊市)、趋势 regime/选股无法验证(慢 book→独立周期太少)、regime sizing 不可外推**。下一个真 edge 全部卡在**缺数据**(熊市样本、更多独立趋势周期、前向大票中军参与数据)→ 按「学不动了就停」停在 cache,等数据累积。**汇合 allocator 的实证底座 = #16-18:短线常开(全天候)、neutral 微缩、趋势作小卫星(参与非 Sharpe)。**

**2026-06-23 续 — 用户纠正 #3:「墙」是自设的,xiaocao API 有全历史。拉真实跨周期数据(date_kline 2021+,含 2022 熊+2024 崩),终于定论。**
20. **数据墙被推倒**:`date_kline(code,count=1300,param_time=<过去日>)` serves **2021-02→2026**(含 2022 熊市、2024-01/02 小盘崩)。两个 API 坑(已写进 AGENTS.md):①concept rank 只 serve 历史**排名**,`prePctChangeRate` 在 ~2024-05-13 前**全 0**(我一度据此报 +20~28pp 跨周期 alpha = 零数据假象,**已撤**);②date_kline `param_time=""` 是 volatile **不入缓存**,必须给过去日才持久化。
21. **趋势选股(动量/龙头)跨周期 = 无 edge,负,动量崩溃(DEFINITIVE)**(`scripts/research_trend_stock_crosscycle.py`,500 大票×1302 日):大票动量趋势 book vs 大票市场 **alpha −35~−119pp、最大回撤 66~77%**。逐年是教科书动量崩溃:**2021(趋势)+11~+19pp ✓,2022(熊)−3~−14pp ✗,2023(弱)−5~−13pp ✗**,2024-25 ~平/负。**+6~20pp/+20~28pp 全是牛市窗口/零数据假象,彻底坐实。settles XH-013/018/020:无稳健趋势选股 alpha。**
22. **唯一复利的是参与/beta**:**买入持有大票市场 2021-2026 复利 +204%、Sharpe(年化) 0.74、最大回撤 25%**——这就是系统踏空的 beta、真正的 lever(非选股技巧)。
23. **regime-择时参与 不过样本外(去前视后)**(`scripts/research_participation_crosscycle.py`):「熊市空仓」含前视时 Sharpe Δ +0.78/+0.24,**去前视(regime 用昨日前的尾随)后翻成 −0.25/−0.17 = 反而更差**(尾随广度报警时最坏已过、错过反弹,同 XH-011/017);regime_prop +0.03/+0.32 勉强但敞口不稳。**「有时空仓更好」事后真、但用尾随 regime 机械择时不可外推。** => **跨周期定论:广义always-on参与 > 任何我试过的择时/选股。别按已实现 regime 择时(太晚),别动量选股(崩溃)。两个 book 同理:广参与、别 gate。** 本 session 第三次自捕假象(零数据→牛窗→前视),诚实不变量守住。
24. **短线跨周期=真实数据墙(verified,非自设)**:系统低吸信号靠 `xiao_cao_index_v2`(xcjw/竞王/断板/isWeak…),但该 per-stock 信号 product **2022/2024-02 返回空、~2025 才有**(不同于 date_kline 价格有全历史)。所以 **mode_history 只能 ~2025+,短线「全天候」claim 只在 2025-26 牛市成立,熊市行为无法验证**(信号数据不存在)。这是 trend 问题(价格可得→已定论)与 short-line 问题(信号不可得→测不了)的关键非对称。**Loop 在此停**:可答的全答尽(且定论),唯一剩的(短线跨熊)是真实数据墙。**汇合定论:广义 always-on 参与 > 任何择时/选股;短线常开(牛市已证全天候,熊市未知);趋势仅作 beta 参与腿(非选股);别按已实现 regime 择时,别动量选股。**
25. **赚钱效应=真实持久状态,但属判断层不是机械择时器**(`scripts/research_money_effect.py`;用户反框「熊市不做/赚钱效应高才做/别屎上雕花」):**赚钱效应(大票>+5% 占比)自相关 lag1 +0.46 ≫ 均值收益 +0.05**——它是反身/持久的真信号(用户对)。但**机械门(滞后、等均敞口、双向 walk-forward)仍不过样本外**(一方向 +0.05、另一方向 −;持久性 lag5 已衰到 +0.13,不足以择时参与)。=> **赚钱效应是实时判断(你看见就做),不是滞后机械计时器;机械化它正是「屎上雕花」。它归 道-层/agent-cortex posture(playbook 已在那:regime=道、主跌空仓=小草 2023 被收割的纪律),不进确定性脊柱。** 数据证实用户反框:粗判断(高效应才做、明确熊市不做)对,细机械择时错。
26. **数据治理(`docs/DATA_QUALITY.md`)**:本 session 三次踩坑根因=「请求可达 range ≠ 数据有效 range」。审计后定:价格 date_kline 深(2019/2021+,可靠)、小草信号(index_v2/concept return/mode_history)浅(~2025+);两 range 不一致处全是坑。已写 governance doc + 回测前 checklist(验内容非覆盖/钉数据有效底/审收益口径/滞后每个特征/确认入缓存)。这是「数据治理不精细」的系统性修复。

## 3. 怎么保证「一直在 + 适时被吸收」

- **持久**：全部 checked-in 文件（非某个 agent 的私有记忆）。`CLAUDE.md` 与 `.codex/skills/xiaocao-trading/SKILL.md` 都指向本页 → 每个新上下文必然发现。
- **适时消费（机械化，非靠 agent 自觉）**：`scripts/xiaocao_knowledge.py` 把现行 posture 摆到面前；`auto_daily.sh` **morning 打印 posture 先验**、**eod 跑 `--check` 标时效**。posture 过期（valid_until 已过）→ STALE 告警，提示重蒸馏。
- **复利（新转录进来）**：放进 `reference/experience/<月份>/` → 跑蒸馏工作流（同首轮）→ append 新 `distilled/*.json`、更新 playbook/timeline/`posture_current.json`、追加假设 → 飞轮重测。
- **候选重测节奏**：候选/已测假设随数据增长**重评估**（镜像 `ledger.already_refuted`）：相关 regime 累积 **≥8 个新 OOS 交易日** 或相关子集**笔数翻倍**才重测（保证样本外、不重复 litigate）。绑数据增长，不绑日历。

## 4. 把一条候选喂进飞轮（操作化配方）

1. 选一条 `xiaocao_hypotheses.jsonl` 候选，按其 `operationalization` 从 **cache** 建逐笔 `{day,strat_ret,base_ret}`（cache-first，不发 API）。
2. `PYTHONPATH=src python3 scripts/research_run.py --trades <file> --n-tried <本轮所试假设数>`（护栏：cache-only / ≥8 天 / 逐笔非日度 / walk-forward train+test / 多重比较）。
3. 满意再 `--record --id XH-0xx --claim ... --method ...` 写 verdict 账本；回填候选 `status` 为 `tested:PASS/REJECTED`。
4. **PASS** 才进 ③ 人工门：人确认 → 改 `src/xiaocao/strategy/params.py`（唯一入口，冻结约束）或重训 → **再过 train+test**。agent 永不自动改参。
