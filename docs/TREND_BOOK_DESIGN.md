# 趋势 Book (Book T) — Paper Implementation

> 状态：**MVP paper-only 已上线（Phase 0/1/2 + 趋势 verdict 记录路径）**。Book T 已能生成趋势候选、写入独立 paper 账户、按独立趋势出场监控/结算，并接入 morning/EOD automation；趋势评估可经 `trend_optimize.py --record` 写入 ledger。任何改 `params.py` 取值、趋势评估晋级、或实盘路径的动作必须走 `docs/OPERATING_CONTRACT.md` §10 的快速探索期 evidence rules；real-capital 仍需两钥。
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

### 2b. 趋势 book T（paper MVP）
当前实现先把趋势主线候选与 paper 生命周期打通；离线趋势评估仪器仍按 §4 分离推进：

| 新文件 | 来源原语 | 职责 |
|---|---|---|
| `src/xiaocao/strategy/mainline_signal.py` | `research_rotation_mainline.py:rotation_freq` + `research_trend_longhold.py:trailing/cum` | 后续生产化目标：轮动频率主线 + 中长期趋势打分（cache-only） |
| `src/xiaocao/strategy/trend_rules.py` | 新（sibling of rules.py） | 已实现：当前强势概念 → posture 对齐分层（aligned/neutral/external）→ 大票篮子选择（中军/核心大票，平铺 2-3） |
| 复用 `mainline.py:compute_mainline` | 既有 | sticky-top-K 主线集合原语 |
| 复用 `client.get_code_by_xiao_cao_block(categoryCodeList, tradeDate)` | 既有 | 主线概念 → 成分股 |

**Phase 0 已修**：`bigcap.py:bigcap_codes` 按 `statusType==1`（正常交易）+ `tradableAShare × close`（流通市值）排序取 top-20%，避免 `stock_info.type == null` 导致大票 universe 为空。

---

## 3. 汇合（交易时）

汇合**只发生在两个已存在的 seam**，不新建执行通道：

### (1) 资金分配 @ `kronos_screen/scripts/paper_record.py:main`
今天这里是**唯一**算 sizing/exposure 的地方（给 book B 算 `deployable_cash`/`exposure_budget`）。改成一个顶层 allocator：把组合权益按**冻结参数 `TREND_BUDGET_RATIO`**（`params.py`，frozen+range）切成 per-book 预算。
- **先例**：`paper_record.py:_kill_switch_factor`（book A 近 5 笔出场表现节流 book B 的 deploy）就是「一个 book 的表现影响另一个 book 的部署」——allocator 把它**泛化**成 per-book 预算。
- **唯一部署控制仍是 book A 业绩 kill-switch**（§8）。**禁止**新增 regime/趋势 deploy 闸（`backtest_deploy_gate.py` 已证 train+test 不一致）。**评审 RED：Design-3 加了「book T 自己的回撤 deploy 闸」= 第二个部署控制面 = 违反 §8，已剔除。**
- **Book T 的仓位目标**：趋势的本质是保持一个独立趋势袖子，不是每日追涨杀跌。新仓优先买与小草现行主线一致的 `aligned` 代表；如果没有足够 aligned，允许 `neutral` 兜底以维持趋势参与；银行/保险/证券/医药/白酒等外部旧方向为 `external`，只当风险/切换信号，不当趋势新买入。

### (2) 一本账 + 一个安全门
- **一本持仓账**：`positions.jsonl` 仍是唯一 append-only ledger；book T 行带 `book:"T"`。**陷阱**：缺 label 默认归 B → `live_monitor`/`paper_record`/`settle`/`data_health` 的每个 book 过滤器**必须同步**认 T，否则 T 静默并进 B 的对账。
- **账户文件**：`accounts.py:load_account/save_account(path,...)` 已 path 参数化 → 加 `paper_account_T.json` 不动 SSOT。
- **真实下单**（暂未接）：经**同一个** `safety.require_capital_action` 两钥 fail-closed 门。

### (3) 同一只票、两个时间维度（最硬的点）
短线要卖 X（次收/HARD_STOP），趋势仍持 X（方向还在就扛）——**不 net 成一个仓**，保留**两行**（book B 行 + book T 行），各自独立生命周期。schema 已支持（今天 book A/B 就同时持有同一只票）。
- **谁赢**：谁都不覆盖谁的 horizon。脊柱各跑各的纪律：B 在 14:55/HARD_STOP，T 在 rebalance/宽趋势止损。
- **个股可以换，但不能乱换**：T 的换股只在两种情况下发生：一是已有 T 仓被 `classify_trend_alignment` 识别为 `external` 且过了 T+1，按 `TREND_POSTURE_MISMATCH` 换出；二是到 `TREND_REBALANCE_R` 低换手周期。普通 category rank 日内/日间波动不换，避免手续费和“战略定力”被噪音打掉。换出后由下一次 morning 补回空 slot，继续保持趋势袖子仓位。
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

book-namespaced 的快照/持仓口径已落地：`capture_signals.py`、`data_health.py`、`contexts.py`、`forward_eval.py` 均按 `book` 区分；缺 label 的历史行默认归 B。该口径已同步到 `OPERATING_CONTRACT.md`、`.codex/skills/xiaocao-trading/SKILL.md` 和 `scripts/auto_daily.sh`。Book T 与 Book B 同日同票可以并存，不能再被误判为 duplicate snapshot。

---

## 8. 分期（paper-only、sensor-safe、对短线脊柱零风险）

- **Phase 0（已完成）**：修 `bigcap.py` statusType bug + 测；加 Book T paper-only 冻结默认值（`TREND_BUDGET_RATIO`/`TREND_TRAIL_DD`/L·R·M）于 `params.py`，不进 validated `REGISTRY`。
- **Phase 1（已完成到可运行仪器）**：`trend_rules.py` 已上线当前强势主线 → posture 对齐分层 → 大票篮子候选；`trend_guards.py` + `trend_optimize.py` 已提供离线复利/dd/换手/alpha 仪器，并可用 `--record` 将 changed verdict 写入 `kronos_screen/HYPOTHESES.jsonl`。趋势 edge 仍无策略授权，除非 §10 人工门确认。
- **Phase 2（已完成）**：Book T paper 写仓（`paper_record.py --trend-only` / `_record_book_t` / `paper_account_T.json`）；`live_monitor.py --book T` 与 `settle_book_t.py` 按 target-book 路由 T 的宽趋势出场；快照 key 命名空间化 + 契约 §12 bump。
- **Phase 3（部分完成）**：`status.build_digest` 已扩到 Book T；allocator 目前是独立 T 账户预算切分（paper）；趋势 verdict 已能进 ledger，`flywheel_selfcheck` 仍是通用 ledger/actuator 视角。
- **实盘**：单独、最后，经两钥；在此之前全程 paper/sensor。**sensor（book A 记账/数据采集）永不停。**

---

## 9. 非协商项核对（全绿才动手）

- [x] 无 LLM 进 fill/stop/bookkeeping/safety；皮层只出判断进 audit log。
- [x] 趋势先验 authority=0；唯一晋级 = trend_guards → verdict → §10 人工门 → `params.py`。
- [x] `params.py` 唯一改值入口，frozen+range，不自动传播；agent 永不自动改参。
- [x] 回测=实盘同一脊柱；book T 与 A/B 独立账户/持仓口径隔离。
- [x] book A 业绩 kill-switch 仍是**唯一**部署控制；**无**新部署闸。
- [x] 趋势止损抑制只认冻结参数，**永不**认 cortex 实时方向信号；book T exit profile 与短线 strong-hold disjoint。
- [ ] 实盘经唯一 `require_capital_action` 两钥门；新增全局跨 book 持仓上限。
- [x] 快照 key 按 book 命名空间化 + 契约 §12 口径 bump + 同步 SKILL/automations。
- [x] automations paper/sensor-safe；趋势用**分离**评估仪器（复利/dd/换手/alpha），只在已实现 PnL 处对账。
- [ ] **限度**：XH-018 的 +6~20pp alpha 是 1 段牛市样本，绝对大头是 beta；上线前需 bear/震荡 regime 的 trend_guards OOS 复核。
