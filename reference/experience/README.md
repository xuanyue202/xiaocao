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
