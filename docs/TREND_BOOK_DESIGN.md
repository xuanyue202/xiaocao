# 趋势 Book (Book T) — Design Sketch

> 状态：**设计稿（未实现）**。本文只描述架构；任何改 `params.py`/确定性脊柱/实盘路径的动作都要走 `docs/OPERATING_CONTRACT.md` §10 人工门 + 两钥。
> 来源：2026-06-22 飞轮第二轮研究（XH-013/XH-017/XH-018）+ 多 agent 架构映射/对抗评审。

## 0. 一句话

> **一个道 → 长出短线 + 趋势两个体系 → 交易时汇合。**

把这句话落到本仓库：**道** = 共享的 `StateVector`/regime 市场判读核心；**两体系** = 既有的 `短线低吸 book`（rules.py）与新增的 `趋势主线 book T`（trend_rules.py）；**汇合** = 在执行层一个资金分配器（`paper_record.py:main`）+ 一本持仓账（`positions.jsonl`，带 `book:"T"` 标签）+ 一个安全门（`safety.require_capital_action`）。两体系各自用**互不相同的评估仪器**判好坏，只在**账户已实现 PnL** 处对账。

为什么需要它：本季研究证明系统 6 月踏空 +29.5% 的趋势，**不是**短线参数没调好，而是**根本没有一条趋势 book 在跑**。短线 book 是执行驱动、右偏、按 per-day 配对 t 评估；趋势 book 是低换手长持、复利驱动（+22~57%/yr，季度 rebalance 比 beta 多 +6~20pp），**用 per-day 护栏评它是错误仪器**。两套平行系统，两套评估。

---

## 1. 道（共享，不改）

- **`src/xiaocao/strategy/state.py:StateVector` / `build_state_index`** — 每日 mode-agnostic 的市场判读向量（reward/risk/continuity/duan_ban_recovery + momentum + limitup_density，∈[0,1]，cache-only）。趋势 book 原样消费它做 regime 条件（trend_strong/continuing vs divergence vs bear），**不新建一套判读**。
- 道级铁律（`docs/XIAOCAO_PLAYBOOK.md` L14）：**「趋势跟短线没关系」是两套独立体系** → 趋势 book 是一个**新 Mode**，不是对短线脊柱的 fork。
- 先问 regime 再问做什么（playbook 道层）：趋势 book 与短线 book 共享同一个「先定 regime」入口，只是 regime→动作的映射不同（短线评分差→不做短线；趋势线仍可做）。

---

## 2. 两体系

### 2a. 短线 book（既有，不动）
`rules.py`（check_dixi/check_lianban/pick_big_ones）→ book A（验证/次收）/ book B（实盘盘中纪律）。**本设计对短线脊柱零改动。**

### 2b. 趋势 book T（新增）
把本季已验证的研究原语**提升为生产模块**（promote，不重写）：

| 新文件 | 来源原语 | 职责 |
|---|---|---|
| `src/xiaocao/strategy/mainline_signal.py` | `research_rotation_mainline.py:rotation_freq` + `research_trend_longhold.py:trailing/cum` | 轮动频率主线 + 中长期趋势打分（cache-only） |
| `src/xiaocao/strategy/trend_rules.py` | 新（sibling of rules.py） | 主线 → 大票篮子选择（中军/核心大票，平铺 2-3） |
| 复用 `mainline.py:compute_mainline` | 既有 | sticky-top-K 主线集合原语 |
| 复用 `client.get_code_by_xiao_cao_block(categoryCodeList, tradeDate)` | 既有 | 主线概念 → 成分股 |

**必修 bug（评审发现，Phase 0 先修）：** `bigcap.py:bigcap_codes` 用 `row.get("type") != 1` 过滤大票，但 `stock_info` 的 `type` 为 null → **返回 0 个大票**（本人研究时已踩，被迫退化成全 `tradableAShare`）。正确口径是按 `statusType==1`（正常交易）+ `tradableAShare × close`（流通市值）排序取 top-20%。**先修这个，否则趋势 universe 是空的。**

---

## 3. 汇合（交易时）

汇合**只发生在两个已存在的 seam**，不新建执行通道：

### (1) 资金分配 @ `kronos_screen/scripts/paper_record.py:main`
今天这里是**唯一**算 sizing/exposure 的地方（给 book B 算 `deployable_cash`/`exposure_budget`）。改成一个顶层 allocator：把组合权益按**冻结参数 `TREND_BUDGET_RATIO`**（`params.py`，frozen+range）切成 per-book 预算。
- **先例**：`paper_record.py:_kill_switch_factor`（book A 近 5 笔出场表现节流 book B 的 deploy）就是「一个 book 的表现影响另一个 book 的部署」——allocator 把它**泛化**成 per-book 预算。
- **唯一部署控制仍是 book A 业绩 kill-switch**（§8）。**禁止**新增 regime/趋势 deploy 闸（`backtest_deploy_gate.py` 已证 train+test 不一致）。**评审 RED：Design-3 加了「book T 自己的回撤 deploy 闸」= 第二个部署控制面 = 违反 §8，已剔除。**

### (2) 一本账 + 一个安全门
- **一本持仓账**：`positions.jsonl` 仍是唯一 append-only ledger；book T 行带 `book:"T"`。**陷阱**：缺 label 默认归 B → `live_monitor`/`paper_record`/`settle`/`data_health` 的每个 book 过滤器**必须同步**认 T，否则 T 静默并进 B 的对账。
- **账户文件**：`accounts.py:load_account/save_account(path,...)` 已 path 参数化 → 加 `paper_account_T.json` 不动 SSOT。
- **真实下单**（暂未接）：经**同一个** `safety.require_capital_action` 两钥 fail-closed 门。

### (3) 同一只票、两个时间维度（最硬的点）
短线要卖 X（次收/HARD_STOP），趋势仍持 X（方向还在就扛）——**不 net 成一个仓**，保留**两行**（book B 行 + book T 行），各自独立生命周期。schema 已支持（今天 book A/B 就同时持有同一只票）。
- **谁赢**：谁都不覆盖谁的 horizon。脊柱各跑各的纪律：B 在 14:55/HARD_STOP，T 在 rebalance/宽趋势止损。
- **评审 RED #1**：book T 的「方向还在就扛」强持有**绝不能**走短线的 `exit_policy.py:181 strong_hold_reason/is_trend_leader` 路径——否则 T 的判断会**压制 B 对同一只票的确定性止损**。→ book T 用**独立的冻结 exit profile**（如 `PROFILE_TREND_DD`，更宽 trailing），与短线 strong-hold 谓词**完全 disjoint**；趋势止损抑制只 key 在**冻结 trend 参数**上，**永不** key 在 cortex 的「方向还在」实时信号上。
- **真实经纪商**：allocator 在调 `require_capital_action` **之前** net 同 code 跨 book 的 BUY/SELL 意图，让 scope/notional 检查看到合并 size；并加一个**全局跨 book 持仓上限**（今天的 `max_total_exposure_ratio` 只管 book B），超限按冻结预算比例 pro-rata 削减——**判断永不越过上限**。

---

## 4. 评估（分离的仪器，账户处对账）

趋势 book 的物理与短线相反：每季 5-15 笔、多周持有、仓位级路径依赖。塞进 `guards.py`（`enough_days>=8` / `paired_ttest_by_day` n<2→p=1.0 / build_results 同日 leave-one-out take-all 基准）要么 fail 要么把一段走运的 8 天 launder 成 PASS。所以**另起一把尺**：

| 新/改 | seam | 测什么 |
|---|---|---|
| `src/xiaocao/research/trend_guards.py`（fork guards.py） | `guards.py:evaluate_hypothesis` | **复利收益、最大回撤、换手（10-20d churn 毁 edge → turnover 一等公民）、vs-beta alpha** |
| `scripts/trend_optimize.py`（平行于 continuous_optimize.py） | `continuous_optimize.py:build_results` | 发仓位级行 `{entry,exit,compounded_ret,beta_ret,peak_dd,hold_days}` 而非每日行 |
| `ledger.py:record_hypothesis`（扩 metrics 或并列 ledger） | 既有 | verdict 带 `compounded_ret/max_dd/turnover/alpha` |
| `forward_eval.py` 平行多日 realized feed | `forward_eval.py:net_realized_ret` | entry open → exit close N 日 + benchmark/beta |

**仍守的非协商项**：cache-only、walk-forward（train 前半/test 后半都过 min compounded-alpha 且 test≥retain·train）、Bonferroni n_tried——只是**证据单位是权益曲线/持仓**，不是交易日。
**对账（非污染）**：两把尺**永不共享逻辑**，只在 `status.py:build_digest` 的**已实现 PnL**处作为第三个账户对账（复刻 book A/B 的 `ab_realized_delta` 隔离模式）。`flywheel.py:check_flywheel` 注册**第二条 ② 能力腿**（trend），报自己的 复利/dd/换手/alpha 健康度；③ 策略门可消费**任一**轨的 PASS，但仍走人工 actuator。

---

## 5. 出脊柱 / 进脊柱（道-法-术-纪律边界）

- **进确定性脊柱（纯代码、回测=实盘、无 LLM）**：fill/stop/bookkeeping/allocator 的预算切分/safety 门/对账。趋势止损只认**冻结参数**。
- **出脊柱（agent 皮层 / 判断先验）**：**选哪条主线、何时认为趋势走坏（方向还在就扛 vs 该撤）、中长期 posture**——这是 discretionary 的，作为**候选仓**写进 audit log，喂给脊柱执行；**对 fill/stop/部署零权威**。
- **Design-3 被剔的两条**：(a) 第二部署控制面；(b) cortex「方向还在」实时信号进止损路径。两条都让判断先验有了脊柱权威 → 违反 §2 红线，**不要**。保留 Design-3 的好点子：趋势**选股属皮层判断**，执行属脊柱。

---

## 6. 升级路径（趋势先验 → edge，唯一合法通道）

趋势 book 的 [待验] playbook 项（`扩散/普涨是见顶前兆`、`行业轮动频率判主线生死`、XH-018）：
`reference/experience/xiaocao_hypotheses.jsonl` 候选（authority=0）→ cache-only 操作化 → **`trend_guards`**（不是短线 guards）→ `kronos_screen/HYPOTHESES.jsonl` verdict → §10 人工门 → 人改 `params.py`（frozen+range，唯一改值入口，不自动传播）。**agent 永不自动改参/自动接 actuator。**

## 7. 契约同步（必须）

book-namespaced 的快照/持仓口径变更（`data_health.py:49 duplicate_snapshots`、`contexts.py:25 load_signal_snapshot_map` 现按 `(date,code,is_live)` 去重，**未按 book 命名空间** → book T 与 book B 同 (date,code) 会**误判重复数据 CRITICAL**）：**必须把快照 key 按 book 命名空间化**，并作为 `OPERATING_CONTRACT.md` 版本号 + §12 修订记录的**口径 bump**（不是脚注），同步 `.codex/skills/xiaocao-trading/SKILL.md` + automations。

---

## 8. 分期（paper-only、sensor-safe、对短线脊柱零风险）

- **Phase 0（小）**：修 `bigcap.py` statusType bug + 测；加 book T 冻结 Params（`TREND_BUDGET_RATIO`/`PROFILE_TREND_DD`/L·R·M）于 `params.py`（仅注册，未启用）。
- **Phase 1**：promote `mainline_signal.py` + `trend_rules.py`；`trend_guards.py` + `trend_optimize.py` 跑出趋势 book 的**离线复利/dd/换手/alpha** 基线（就是本季 research_trend_longhold 的生产化）。
- **Phase 2**：book T **paper 写仓**（`paper_record.py` 加 `_record_book_t`，`paper_account_T.json`）；`live_monitor`/`settle_book_t` 按 target-book 参数路由 T 的宽趋势出场；快照 key 命名空间化 + 契约 §12 bump。
- **Phase 3**：`status.build_digest` 扩到 N book + allocator 资金切分上线（paper）；`flywheel` 第二 ② 腿；趋势 verdict 进 ledger。
- **实盘**：单独、最后，经两钥；在此之前全程 paper/sensor。**sensor（book A 记账/数据采集）永不停。**

---

## 9. 非协商项核对（全绿才动手）

- [ ] 无 LLM 进 fill/stop/bookkeeping/safety；皮层只出判断进 audit log。
- [ ] 趋势先验 authority=0；唯一晋级 = trend_guards → verdict → §10 人工门 → `params.py`。
- [ ] `params.py` 唯一改值入口，frozen+range，不自动传播；agent 永不自动改参。
- [ ] 回测=实盘同一脊柱；book T 与 A/B 对账无 drift（复刻 ab_realized_delta 隔离）。
- [ ] book A 业绩 kill-switch 仍是**唯一**部署控制；**无**新部署闸。
- [ ] 趋势止损抑制只认冻结参数，**永不**认 cortex 实时方向信号；book T exit profile 与短线 strong-hold disjoint。
- [ ] 实盘经唯一 `require_capital_action` 两钥门；新增全局跨 book 持仓上限。
- [ ] 快照 key 按 book 命名空间化 + 契约 §12 口径 bump + 同步 SKILL/automations。
- [ ] automations paper/sensor-safe；趋势用**分离**评估仪器（复利/dd/换手/alpha），只在已实现 PnL 处对账。
- [ ] **限度**：XH-018 的 +6~20pp alpha 是 1 段牛市样本，绝对大头是 beta；上线前需 bear/震荡 regime 的 trend_guards OOS 复核。
